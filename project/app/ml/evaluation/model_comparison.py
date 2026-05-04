from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Config
from app.ml.embeddings import SentenceTransformerEmbeddingProvider
from app.ml.evaluation.search_baseline import (
    BaselineEvaluationReport,
    DEFAULT_EVALUATION_OUTPUT_DIR,
    EvaluationQuery,
    SearchBaselineEvaluator,
    save_baseline_report,
)
from app.repositories.news_repository import NewsRepository
from app.services.embedding_service import EmbeddingService
from app.services.indexing_service import IndexingService


DEFAULT_COMPARISON_MODELS = (
    Config.EMBEDDING_MODEL_NAME,
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)


@dataclass(frozen=True)
class ModelEvaluationRunResult:
    """Итог evaluation-прогона одной embedding-модели."""

    model_name: str
    index_path: Path
    id_map_path: Path
    report_path: Path
    report: BaselineEvaluationReport


def comparison_models(explicit_models: list[str]) -> list[str]:
    """Вернуть список моделей для сравнения с текущим baseline."""
    models = explicit_models if explicit_models else list(DEFAULT_COMPARISON_MODELS)
    unique_models: list[str] = []
    for model_name in models:
        if model_name not in unique_models:
            unique_models.append(model_name)
    return unique_models


def evaluate_embedding_model(
    *,
    model_name: str,
    queries: list[EvaluationQuery],
    output_dir: Path = DEFAULT_EVALUATION_OUTPUT_DIR,
    top_k: int = 5,
    active_only: bool = False,
    news_repository: NewsRepository | None = None,
    embedding_service: Any | None = None,
) -> ModelEvaluationRunResult:
    """Построить временный FAISS-индекс для модели и оценить ее на eval-наборе."""
    model_stem = safe_model_file_stem(model_name)
    model_output_dir = output_dir / "models" / model_stem
    index_path = model_output_dir / "news.index"
    id_map_path = model_output_dir / "news_index_ids.json"

    repository = news_repository if news_repository is not None else NewsRepository()
    service = (
        embedding_service
        if embedding_service is not None
        else _build_embedding_service_for_model(model_name=model_name, output_dir=output_dir)
    )

    # Индекс строим в runtime-папке evaluation, чтобы не перезаписать рабочий FAISS приложения.
    IndexingService(
        news_repository=repository,
        embedding_service=service,
        index_path=index_path,
        id_map_path=id_map_path,
    ).rebuild_full_index()

    report = SearchBaselineEvaluator(
        embedding_service=service,
        news_repository=repository,
        index_path=index_path,
        id_map_path=id_map_path,
    ).evaluate(
        queries,
        top_k=top_k,
        active_only=active_only,
        model_name=model_name,
    )
    report_path = save_baseline_report(
        report,
        output_dir=output_dir,
        file_name=f"baseline_{model_stem}.json",
    )

    return ModelEvaluationRunResult(
        model_name=model_name,
        index_path=index_path,
        id_map_path=id_map_path,
        report_path=report_path,
        report=report,
    )


def safe_model_file_stem(model_name: str) -> str:
    """Преобразовать имя модели Hugging Face в безопасную часть имени файла."""
    normalized_name = model_name.strip().replace("/", "_").replace("\\", "_")
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", normalized_name).strip("_")


def _build_embedding_service_for_model(*, model_name: str, output_dir: Path) -> EmbeddingService:
    """Создать embedding-сервис строго для выбранной модели, без подхвата adapted-модели."""
    provider = SentenceTransformerEmbeddingProvider(
        model_name=model_name,
        adapted_model_dir=output_dir / "_disabled_adapted_model",
    )
    return EmbeddingService(provider=provider)
