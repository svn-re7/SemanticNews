from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from sentence_transformers import InputExample, SentenceTransformer
from sentence_transformers import util as sentence_transformer_util
from sentence_transformers.sentence_transformer import losses
from sentence_transformers.sentence_transformer.evaluation import InformationRetrievalEvaluator

from app.config import Config


@dataclass(frozen=True)
class TrainingConfig:
    """Настройки fine-tuning embedding-модели на новостных парах title -> text."""

    base_model_name: str = Config.EMBEDDING_MODEL_NAME
    train_path: Path = Config.ML_DATASET_DIR / "train.jsonl"
    validation_path: Path = Config.ML_DATASET_DIR / "validation.jsonl"
    output_dir: Path = Config.ADAPTED_EMBEDDING_MODEL_DIR
    batch_size: int = 16
    epochs: int = 1
    learning_rate: float = 2e-5
    warmup_ratio: float = 0.1
    evaluation_steps: int = 500
    max_train_examples: int | None = None
    max_validation_examples: int | None = None
    overwrite_output: bool = False
    show_progress_bar: bool = True
    max_grad_norm: float = 1.0


@dataclass(frozen=True)
class TrainingRunResult:
    """Краткий итог запуска fine-tuning."""

    base_model_name: str
    train_examples: int
    validation_examples: int
    batch_size: int
    epochs: int
    warmup_steps: int
    output_dir: Path


def load_training_pairs(path: Path, *, limit: int | None = None) -> list[InputExample]:
    """Прочитать JSONL-пары и подготовить InputExample для sentence-transformers."""
    examples: list[InputExample] = []
    for item in _read_jsonl(path, limit=limit):
        examples.append(InputExample(texts=[str(item["query"]), str(item["positive"])]))
    return examples


def build_validation_retrieval_data(
    path: Path,
    *,
    limit: int | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, set[str]]]:
    """Собрать validation-данные в формате query/corpus/relevant_docs для retrieval-оценки."""
    queries: dict[str, str] = {}
    corpus: dict[str, str] = {}
    relevant_docs: dict[str, set[str]] = {}

    for item in _read_jsonl(path, limit=limit):
        article_id = int(item["article_id"])
        query_id = f"q_{article_id}"
        document_id = f"a_{article_id}"

        queries[query_id] = str(item["query"])
        corpus[document_id] = str(item["positive"])
        relevant_docs[query_id] = {document_id}

    return queries, corpus, relevant_docs


def calculate_warmup_steps(*, examples_count: int, config: TrainingConfig) -> int:
    """Посчитать число warmup-шагов как долю от общего количества шагов обучения."""
    if examples_count <= 0:
        return 0

    steps_per_epoch = math.ceil(examples_count / config.batch_size)
    total_steps = steps_per_epoch * config.epochs
    return max(1, math.ceil(total_steps * config.warmup_ratio))


def train_embedding_model(config: TrainingConfig | None = None) -> TrainingRunResult:
    """Дообучить SentenceTransformer на train.jsonl и сохранить локальную модель."""
    config = config if config is not None else TrainingConfig()
    _validate_training_config(config)
    _prepare_output_dir(config.output_dir, overwrite=config.overwrite_output)

    train_examples = load_training_pairs(config.train_path, limit=config.max_train_examples)
    if not train_examples:
        raise ValueError("Train dataset пустой, обучение запускать нельзя.")

    validation_queries, validation_corpus, validation_relevant_docs = build_validation_retrieval_data(
        config.validation_path,
        limit=config.max_validation_examples,
    )

    model = SentenceTransformer(config.base_model_name)
    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=config.batch_size,
        collate_fn=model.smart_batching_collate,
    )
    train_loss = losses.MultipleNegativesRankingLoss(model)
    evaluator = InformationRetrievalEvaluator(
        validation_queries,
        validation_corpus,
        validation_relevant_docs,
        name="semanticnews-validation",
        show_progress_bar=False,
        batch_size=config.batch_size,
    )
    warmup_steps = calculate_warmup_steps(examples_count=len(train_examples), config=config)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    scheduler = _build_linear_warmup_scheduler(
        optimizer=optimizer,
        total_steps=len(train_dataloader) * config.epochs,
        warmup_steps=warmup_steps,
    )

    # MultipleNegativesRankingLoss считает остальные элементы batch негативами для текущей пары.
    global_step = 0
    best_score: float | None = None
    for epoch in range(config.epochs):
        model.train()
        for sentence_features, labels in train_dataloader:
            sentence_features = [
                sentence_transformer_util.batch_to_device(features, model.device)
                for features in sentence_features
            ]
            labels = labels.to(model.device)

            loss_value = train_loss(sentence_features, labels)
            loss_value.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            global_step += 1

            if config.show_progress_bar and global_step % max(1, config.evaluation_steps) == 0:
                print(f"epoch={epoch + 1} step={global_step} loss={loss_value.item():.4f}")

        metrics = evaluator(model, output_path=str(config.output_dir), epoch=epoch, steps=global_step)
        current_score = _main_validation_score(metrics)
        if best_score is None or current_score >= best_score:
            best_score = current_score
            model.save(str(config.output_dir))

    return TrainingRunResult(
        base_model_name=config.base_model_name,
        train_examples=len(train_examples),
        validation_examples=len(validation_queries),
        batch_size=config.batch_size,
        epochs=config.epochs,
        warmup_steps=warmup_steps,
        output_dir=config.output_dir,
    )


def _read_jsonl(path: Path, *, limit: int | None = None) -> list[dict]:
    """Прочитать JSONL-файл построчно, не требуя общего JSON-массива."""
    if not path.exists():
        raise FileNotFoundError(f"Файл датасета не найден: {path}")

    items: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        items.append(json.loads(line))
        if limit is not None and len(items) >= limit:
            break
    return items


def _validate_training_config(config: TrainingConfig) -> None:
    """Проверить параметры обучения до загрузки тяжелой ML-модели."""
    if config.batch_size <= 1:
        raise ValueError("batch_size должен быть больше 1 для MultipleNegativesRankingLoss.")
    if config.epochs <= 0:
        raise ValueError("epochs должен быть положительным.")
    if config.learning_rate <= 0:
        raise ValueError("learning_rate должен быть положительным.")
    if not 0 <= config.warmup_ratio <= 1:
        raise ValueError("warmup_ratio должен быть в диапазоне от 0 до 1.")


def _prepare_output_dir(output_dir: Path, *, overwrite: bool) -> None:
    """Подготовить каталог модели и защитить существующую adapted-модель от случайной перезаписи."""
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Каталог модели уже существует: {output_dir}. "
                "Передайте --overwrite-output, если хотите заменить модель."
            )
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)


def _build_linear_warmup_scheduler(
    *,
    optimizer: torch.optim.Optimizer,
    total_steps: int,
    warmup_steps: int,
) -> torch.optim.lr_scheduler.LambdaLR:
    """Создать простой warmup + linear decay scheduler без лишних зависимостей."""
    if total_steps <= 0:
        total_steps = 1

    def lr_lambda(current_step: int) -> float:
        """Вернуть множитель learning rate для текущего шага обучения."""
        if current_step < warmup_steps:
            return float(current_step + 1) / float(max(1, warmup_steps))
        remaining_steps = max(1, total_steps - warmup_steps)
        return max(0.0, float(total_steps - current_step) / float(remaining_steps))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


def _main_validation_score(metrics: dict[str, float]) -> float:
    """Выбрать главную retrieval-метрику validation для сохранения лучшей модели."""
    for key in (
        "semanticnews-validation_cosine_mrr@10",
        "semanticnews-validation_dot_mrr@10",
        "semanticnews-validation_mrr@10",
    ):
        if key in metrics:
            return float(metrics[key])
    if metrics:
        return float(next(iter(metrics.values())))
    return 0.0
