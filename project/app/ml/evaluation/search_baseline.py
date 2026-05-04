from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.config import Config
from app.repositories.news_repository import NewsRepository
from app.services.embedding_service import EmbeddingService


DEFAULT_EVALUATION_QUERIES_PATH = Path(__file__).with_name("queries.json")
DEFAULT_EVALUATION_OUTPUT_DIR = Config.DATABASE_PATH.parent / "evaluation"


@dataclass(frozen=True)
class EvaluationQuery:
    """Один ручной eval-запрос и ожидаемые смысловые маркеры релевантности."""

    query: str
    expected_terms: list[str]


@dataclass(frozen=True)
class EvaluationResultItem:
    """Один результат поиска внутри evaluation-отчета."""

    article_id: int
    title: str
    source_name: str
    relevance: float
    matched: bool
    direct_url: str = ""


@dataclass(frozen=True)
class QueryMetrics:
    """Метрики качества для одного eval-запроса."""

    hit_at_1: bool
    hit_at_3: bool
    hit_at_5: bool
    first_hit_rank: int | None
    mrr: float


@dataclass(frozen=True)
class QueryEvaluationResult:
    """Итог оценки одного запроса."""

    query: str
    expected_terms: list[str]
    metrics: QueryMetrics
    results: list[EvaluationResultItem]


@dataclass(frozen=True)
class BaselineEvaluationReport:
    """Полный baseline-отчет по текущей embedding-модели и FAISS-индексу."""

    created_at: str
    model_name: str
    top_k: int
    active_only: bool
    queries_count: int
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mean_mrr: float
    query_results: list[QueryEvaluationResult]


def load_evaluation_queries(path: Path = DEFAULT_EVALUATION_QUERIES_PATH) -> list[EvaluationQuery]:
    """Прочитать ручной набор eval-запросов из JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries: list[EvaluationQuery] = []
    for item in payload:
        queries.append(
            EvaluationQuery(
                query=str(item["query"]),
                expected_terms=[str(term).lower() for term in item["expected_terms"]],
            )
        )
    return queries


def calculate_query_metrics(items: list[EvaluationResultItem]) -> QueryMetrics:
    """Посчитать hit@k и MRR для одного eval-запроса."""
    first_hit_rank = None
    for position, item in enumerate(items, start=1):
        if item.matched:
            first_hit_rank = position
            break

    return QueryMetrics(
        hit_at_1=first_hit_rank == 1,
        hit_at_3=first_hit_rank is not None and first_hit_rank <= 3,
        hit_at_5=first_hit_rank is not None and first_hit_rank <= 5,
        first_hit_rank=first_hit_rank,
        mrr=0.0 if first_hit_rank is None else 1.0 / first_hit_rank,
    )


class SearchBaselineEvaluator:
    """Read-only evaluator семантического поиска без записи в историю запросов."""

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService | None = None,
        news_repository: NewsRepository | None = None,
        index_path: Path | None = None,
        id_map_path: Path | None = None,
    ) -> None:
        self.embedding_service = embedding_service if embedding_service is not None else EmbeddingService()
        self.news_repository = news_repository if news_repository is not None else NewsRepository()
        self.index_path = index_path if index_path is not None else Config.FAISS_INDEX_PATH
        self.id_map_path = id_map_path if id_map_path is not None else Config.FAISS_ID_MAP_PATH

    def evaluate(
        self,
        queries: list[EvaluationQuery],
        *,
        top_k: int = 5,
        active_only: bool = False,
        model_name: str = Config.EMBEDDING_MODEL_NAME,
    ) -> BaselineEvaluationReport:
        """Оценить текущий FAISS-поиск на ручном наборе запросов."""
        if top_k <= 0:
            raise ValueError("top_k должен быть положительным числом")

        index = faiss.read_index(str(self.index_path))
        article_ids = self._read_article_id_map()
        if index.ntotal != len(article_ids):
            raise ValueError("FAISS-индекс и JSON-карта article_id рассинхронизированы.")

        query_results = [
            self._evaluate_query(
                evaluation_query,
                index=index,
                article_ids=article_ids,
                top_k=top_k,
                active_only=active_only,
            )
            for evaluation_query in queries
        ]

        return _build_report(
            query_results=query_results,
            top_k=top_k,
            active_only=active_only,
            model_name=model_name,
        )

    def _evaluate_query(
        self,
        evaluation_query: EvaluationQuery,
        *,
        index: Any,
        article_ids: list[int],
        top_k: int,
        active_only: bool,
    ) -> QueryEvaluationResult:
        """Оценить один запрос через текущие embedding-и и FAISS."""
        query_vector = self._prepare_query_vector(self.embedding_service.encode_query(evaluation_query.query))
        candidate_limit = min(max(top_k * 5, top_k), index.ntotal)
        distances, positions = index.search(query_vector, candidate_limit)
        found_pairs = self._collect_found_pairs(
            distances=distances[0],
            positions=positions[0],
            article_ids=article_ids,
        )
        articles_by_id = {
            article.id: article
            for article in self.news_repository.get_by_ids([article_id for article_id, _ in found_pairs])
        }

        result_items: list[EvaluationResultItem] = []
        for article_id, relevance in found_pairs:
            article = articles_by_id.get(article_id)
            if article is None:
                continue
            if active_only and (article.source is None or not article.source.is_active):
                continue

            source_name = article.source.name if article.source is not None else "unknown"
            result_items.append(
                EvaluationResultItem(
                    article_id=article.id,
                    title=article.title,
                    direct_url=article.direct_url,
                    source_name=source_name,
                    relevance=relevance,
                    matched=_matches_expected_terms(
                        text_parts=[
                            article.title,
                            article.text,
                            article.direct_url,
                            source_name,
                        ],
                        expected_terms=evaluation_query.expected_terms,
                    ),
                )
            )
            if len(result_items) >= top_k:
                break

        return QueryEvaluationResult(
            query=evaluation_query.query,
            expected_terms=evaluation_query.expected_terms,
            metrics=calculate_query_metrics(result_items),
            results=result_items,
        )

    def _read_article_id_map(self) -> list[int]:
        """Прочитать JSON-карту позиции FAISS -> article_id."""
        payload = json.loads(self.id_map_path.read_text(encoding="utf-8"))
        article_ids = payload.get("article_ids")
        if not isinstance(article_ids, list):
            raise ValueError("Карта article_id имеет неверный формат.")
        return [int(article_id) for article_id in article_ids]

    def _prepare_query_vector(self, query_vector: np.ndarray) -> np.ndarray:
        """Подготовить embedding запроса к FAISS-поиску."""
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        if query_vector.ndim != 2 or query_vector.shape[0] != 1:
            raise ValueError("Eval-запрос должен давать один embedding-вектор.")
        return np.ascontiguousarray(query_vector.astype(np.float32))

    def _collect_found_pairs(
        self,
        *,
        distances: np.ndarray,
        positions: np.ndarray,
        article_ids: list[int],
    ) -> list[tuple[int, float]]:
        """Перевести FAISS-позиции в пары article_id/relevance."""
        found_pairs: list[tuple[int, float]] = []
        for distance, position in zip(distances, positions):
            if position < 0:
                continue
            found_pairs.append((article_ids[int(position)], float(distance)))
        return found_pairs


def save_baseline_report(
    report: BaselineEvaluationReport,
    *,
    output_dir: Path = DEFAULT_EVALUATION_OUTPUT_DIR,
) -> Path:
    """Сохранить baseline-отчет в runtime-папку instance/evaluation."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "baseline_current.json"
    output_path.write_text(
        json.dumps(_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _matches_expected_terms(*, text_parts: list[str], expected_terms: list[str]) -> bool:
    """Проверить, содержит ли результат хотя бы один ожидаемый маркер темы."""
    haystack = " ".join(text_parts).lower()
    return any(term.lower() in haystack for term in expected_terms)


def _build_report(
    *,
    query_results: list[QueryEvaluationResult],
    top_k: int,
    active_only: bool,
    model_name: str,
) -> BaselineEvaluationReport:
    """Собрать агрегированный baseline-отчет."""
    queries_count = len(query_results)
    if queries_count == 0:
        raise ValueError("Набор eval-запросов не должен быть пустым.")

    return BaselineEvaluationReport(
        created_at=datetime.now().isoformat(timespec="seconds"),
        model_name=model_name,
        top_k=top_k,
        active_only=active_only,
        queries_count=queries_count,
        hit_at_1=_mean([result.metrics.hit_at_1 for result in query_results]),
        hit_at_3=_mean([result.metrics.hit_at_3 for result in query_results]),
        hit_at_5=_mean([result.metrics.hit_at_5 for result in query_results]),
        mean_mrr=sum(result.metrics.mrr for result in query_results) / queries_count,
        query_results=query_results,
    )


def _mean(values: list[bool]) -> float:
    """Посчитать долю True-значений."""
    if not values:
        return 0.0
    return sum(1 for value in values if value) / len(values)


def _to_jsonable(value: Any) -> Any:
    """Преобразовать dataclass-структуры baseline в JSON-совместимый dict/list."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value
