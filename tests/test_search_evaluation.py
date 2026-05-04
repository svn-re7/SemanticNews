from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.evaluation.search_baseline import (  # noqa: E402
    EvaluationQuery,
    EvaluationResultItem,
    calculate_query_metrics,
)
from app.ml.evaluation.model_comparison import (  # noqa: E402
    comparison_models,
    evaluate_embedding_model,
    safe_model_file_stem,
)
from app.config import Config  # noqa: E402
from app.models.entities import Article  # noqa: E402


class FakeNewsRepository:
    """Тестовый репозиторий статей без обращения к SQLite."""

    def __init__(self, articles: list[Article]) -> None:
        self.articles = articles
        self.articles_by_id = {article.id: article for article in articles}

    def count_articles(self) -> int:
        """Вернуть количество тестовых статей."""
        return len(self.articles)

    def list_articles(self, limit: int, offset: int = 0) -> list[Article]:
        """Вернуть статьи в порядке, который попадет во временный FAISS-индекс."""
        return self.articles[offset : offset + limit]

    def get_by_ids(self, article_ids: list[int]) -> list[Article]:
        """Вернуть статьи по id в тестовом режиме."""
        return [self.articles_by_id[article_id] for article_id in article_ids]


class FakeEmbeddingService:
    """Тестовый embedding-сервис с фиксированными векторами."""

    def encode_articles(self, articles: list[Article]) -> np.ndarray:
        """Вернуть векторы статей без загрузки реальной ML-модели."""
        vectors_by_id = {
            10: [1.0, 0.0],
            20: [0.0, 1.0],
        }
        return np.array([vectors_by_id[article.id] for article in articles], dtype=np.float32)

    def encode_query(self, query_text: str) -> np.ndarray:
        """Вернуть вектор запроса, который ближе к статье про экономику."""
        return np.array([1.0, 0.0], dtype=np.float32)


class SearchEvaluationTest(unittest.TestCase):
    def test_comparison_models_uses_defaults_without_explicit_models(self) -> None:
        """Без явного списка evaluation сравнивает текущую модель и эталонные кандидаты."""
        models = comparison_models([])

        self.assertIn(Config.EMBEDDING_MODEL_NAME, models)
        self.assertIn("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", models)
        self.assertEqual(len(models), len(set(models)))

    def test_safe_model_file_stem_removes_path_separators(self) -> None:
        """Имя модели преобразуется в безопасный stem для runtime-файлов отчета."""
        self.assertEqual(
            safe_model_file_stem("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
            "sentence-transformers_paraphrase-multilingual-MiniLM-L12-v2",
        )

    def test_evaluate_embedding_model_uses_temporary_index_and_model_report(self) -> None:
        """Оценка модели строит отдельный FAISS-индекс и сохраняет отдельный JSON-отчет."""
        articles = [
            self._article(article_id=10, title="Экономика и банки"),
            self._article(article_id=20, title="Футбольный матч"),
        ]
        queries = [EvaluationQuery(query="экономика", expected_terms=["экономика"])]

        with tempfile.TemporaryDirectory() as temp_dir:
            result = evaluate_embedding_model(
                model_name="test/model",
                queries=queries,
                output_dir=Path(temp_dir),
                news_repository=FakeNewsRepository(articles),
                embedding_service=FakeEmbeddingService(),
            )

            self.assertEqual(result.report.model_name, "test/model")
            self.assertEqual(result.report.hit_at_1, 1.0)
            self.assertEqual(result.report_path.name, "baseline_test_model.json")
            self.assertTrue(result.report_path.exists())
            self.assertTrue(result.index_path.exists())
            self.assertTrue(result.id_map_path.exists())

    def test_calculate_query_metrics_uses_first_matching_rank(self) -> None:
        """Метрики запроса считаются по первой позиции, где найден ожидаемый термин."""
        items = [
            EvaluationResultItem(
                article_id=1,
                title="Новость про спорт",
                source_name="РИА Новости",
                relevance=0.8,
                matched=False,
            ),
            EvaluationResultItem(
                article_id=2,
                title="Банки обсуждают регулирование ИИ",
                source_name="Коммерсантъ",
                relevance=0.7,
                matched=True,
            ),
        ]

        metrics = calculate_query_metrics(items)

        self.assertFalse(metrics.hit_at_1)
        self.assertTrue(metrics.hit_at_3)
        self.assertTrue(metrics.hit_at_5)
        self.assertEqual(metrics.first_hit_rank, 2)
        self.assertEqual(metrics.mrr, 0.5)

    def test_calculate_query_metrics_handles_empty_hits(self) -> None:
        """Если в выдаче нет ожидаемых терминов, hit-метрики равны нулю."""
        items = [
            EvaluationResultItem(
                article_id=1,
                title="Нерелевантная статья",
                source_name="РИА Новости",
                relevance=0.8,
                matched=False,
            )
        ]

        metrics = calculate_query_metrics(items)

        self.assertFalse(metrics.hit_at_1)
        self.assertFalse(metrics.hit_at_3)
        self.assertFalse(metrics.hit_at_5)
        self.assertIsNone(metrics.first_hit_rank)
        self.assertEqual(metrics.mrr, 0.0)

    def _article(self, article_id: int, title: str) -> Article:
        """Собрать минимальную статью для evaluation-теста."""
        article = Article(
            source_id=1,
            article_type_id=1,
            direct_url=f"https://example.test/{article_id}",
            title=title,
            text=f"Полный текст: {title}",
            published_at=datetime(2026, 1, 1),
            added_at=datetime(2026, 1, 1),
        )
        article.id = article_id
        return article


if __name__ == "__main__":
    unittest.main()
