from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.evaluation.search_baseline import (  # noqa: E402
    EvaluationResultItem,
    calculate_query_metrics,
)


class SearchEvaluationTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
