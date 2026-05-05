from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.config import Config
from app.ml.embeddings import SentenceTransformerEmbeddingProvider
from app.ml.evaluation.search_baseline import DEFAULT_EVALUATION_OUTPUT_DIR
from app.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class HoldoutItem:
    """Один test-пример для проверки title -> own text retrieval."""

    article_id: int
    query: str
    positive: str


@dataclass(frozen=True)
class HoldoutCandidate:
    """Результат поиска для одного holdout-примера."""

    article_id: int
    found_article_ids: list[int]


@dataclass(frozen=True)
class HoldoutMetrics:
    """Агрегированные метрики holdout retrieval."""

    items_count: int
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    hit_at_10: float
    mean_mrr: float


@dataclass(frozen=True)
class HoldoutEvaluationReport:
    """Полный отчет holdout-проверки для одной embedding-модели."""

    created_at: str
    model_name: str
    dataset_path: str
    top_k: int
    metrics: HoldoutMetrics


def load_holdout_items(path: Path, *, limit: int | None = None) -> list[HoldoutItem]:
    """Прочитать test.jsonl и взять только поля, нужные для holdout retrieval."""
    items: list[HoldoutItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        items.append(
            HoldoutItem(
                article_id=int(payload["article_id"]),
                query=str(payload["query"]),
                positive=str(payload["positive"]),
            )
        )
        if limit is not None and len(items) >= limit:
            break
    return items


def calculate_holdout_metrics(candidates: list[HoldoutCandidate]) -> HoldoutMetrics:
    """Посчитать hit@k и MRR по позиции own article в найденных документах."""
    if not candidates:
        raise ValueError("Holdout-набор не должен быть пустым.")

    ranks: list[int | None] = []
    for candidate in candidates:
        rank = _first_rank(candidate.article_id, candidate.found_article_ids)
        ranks.append(rank)

    return HoldoutMetrics(
        items_count=len(candidates),
        hit_at_1=_mean_rank_at_k(ranks, 1),
        hit_at_3=_mean_rank_at_k(ranks, 3),
        hit_at_5=_mean_rank_at_k(ranks, 5),
        hit_at_10=_mean_rank_at_k(ranks, 10),
        mean_mrr=sum(0.0 if rank is None else 1.0 / rank for rank in ranks) / len(ranks),
    )


class HoldoutRetrievalEvaluator:
    """Оценщик способности модели находить текст статьи по ее заголовку."""

    def __init__(self, *, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service

    def evaluate(
        self,
        items: list[HoldoutItem],
        *,
        model_name: str,
        dataset_path: Path,
        top_k: int = 10,
    ) -> HoldoutEvaluationReport:
        """Построить временный FAISS по holdout-текстам и проверить заголовки как запросы."""
        if top_k <= 0:
            raise ValueError("top_k должен быть положительным.")
        if not items:
            raise ValueError("Holdout-набор не должен быть пустым.")

        positive_embeddings = self._prepare_embeddings(
            self.embedding_service.provider.encode_batch([item.positive for item in items])
        )
        query_embeddings = self._prepare_embeddings(
            self.embedding_service.provider.encode_batch([item.query for item in items])
        )

        # Индекс существует только в памяти: рабочий FAISS приложения здесь не используется.
        index = faiss.IndexFlatIP(positive_embeddings.shape[1])
        index.add(positive_embeddings)
        _, positions = index.search(query_embeddings, min(top_k, len(items)))

        candidates = [
            HoldoutCandidate(
                article_id=item.article_id,
                found_article_ids=[
                    items[int(position)].article_id
                    for position in positions[row_index]
                    if position >= 0
                ],
            )
            for row_index, item in enumerate(items)
        ]

        return HoldoutEvaluationReport(
            created_at=datetime.now().isoformat(timespec="seconds"),
            model_name=model_name,
            dataset_path=str(dataset_path),
            top_k=top_k,
            metrics=calculate_holdout_metrics(candidates),
        )

    def _prepare_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Проверить и привести embeddings к формату, который ожидает FAISS."""
        if embeddings.ndim != 2:
            raise ValueError("Holdout FAISS ожидает двумерный массив embeddings.")
        return np.ascontiguousarray(embeddings.astype(np.float32))


def build_embedding_service_for_model(
    *,
    model_name: str,
    use_adapted_model: bool,
) -> EmbeddingService:
    """Создать embedding service для base или adapted модели явно."""
    adapted_model_dir = Config.ADAPTED_EMBEDDING_MODEL_DIR if use_adapted_model else _missing_adapted_dir()
    provider = SentenceTransformerEmbeddingProvider(
        model_name=model_name,
        adapted_model_dir=adapted_model_dir,
    )
    return EmbeddingService(provider=provider)


def save_holdout_report(
    report: HoldoutEvaluationReport,
    *,
    output_dir: Path = DEFAULT_EVALUATION_OUTPUT_DIR,
    file_name: str,
) -> Path:
    """Сохранить holdout-отчет в runtime-папку evaluation."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name
    output_path.write_text(
        json.dumps(_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _missing_adapted_dir() -> Path:
    """Вернуть заведомо отсутствующий путь, чтобы provider не подхватил adapted-модель."""
    return Config.ADAPTED_EMBEDDING_MODEL_DIR.parent / "__disabled_adapted_model__"


def _first_rank(article_id: int, found_article_ids: list[int]) -> int | None:
    """Вернуть 1-based позицию правильной статьи в выдаче."""
    for position, found_article_id in enumerate(found_article_ids, start=1):
        if found_article_id == article_id:
            return position
    return None


def _mean_rank_at_k(ranks: list[int | None], k: int) -> float:
    """Посчитать долю запросов, где правильный документ найден не ниже top-k."""
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def _to_jsonable(value: Any) -> Any:
    """Преобразовать dataclass-отчет в JSON-совместимые dict/list."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value
