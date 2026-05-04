from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.training.dataset_builder import (  # noqa: E402
    DatasetBuildConfig,
    TrainingDatasetBuilder,
)
from app.models.entities import Article, Source  # noqa: E402


class FakeNewsRepository:
    """Тестовый репозиторий статей без обращения к SQLite."""

    def __init__(self, articles: list[Article]) -> None:
        self.articles = articles

    def count_articles(self) -> int:
        """Вернуть количество тестовых статей."""
        return len(self.articles)

    def list_articles(self, limit: int, offset: int = 0) -> list[Article]:
        """Вернуть тестовые статьи для сборки датасета."""
        return self.articles[offset : offset + limit]


class TrainingDatasetBuilderTest(unittest.TestCase):
    def test_build_writes_split_jsonl_files_without_article_overlap(self) -> None:
        """Сборщик пишет train/validation/test и не смешивает статьи между split."""
        articles = [
            self._article(article_id=index, title=f"Заголовок новости {index}", text="абв " * 50)
            for index in range(1, 11)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            builder = TrainingDatasetBuilder(
                news_repository=FakeNewsRepository(articles),
                config=DatasetBuildConfig(
                    output_dir=Path(temp_dir),
                    train_ratio=0.6,
                    validation_ratio=0.2,
                    random_seed=7,
                    max_text_chars=40,
                    min_title_chars=5,
                    min_text_chars=10,
                ),
            )

            result = builder.build()

            self.assertEqual(result.total_articles, 10)
            self.assertEqual(result.accepted_articles, 10)
            self.assertEqual(result.split_counts, {"train": 6, "validation": 2, "test": 2})
            self.assertTrue(result.train_path.exists())
            self.assertTrue(result.validation_path.exists())
            self.assertTrue(result.test_path.exists())
            self.assertTrue(result.stats_path.exists())

            split_article_ids = {
                split_name: {
                    item["article_id"] for item in self._read_jsonl(path)
                }
                for split_name, path in {
                    "train": result.train_path,
                    "validation": result.validation_path,
                    "test": result.test_path,
                }.items()
            }

            self.assertTrue(split_article_ids["train"].isdisjoint(split_article_ids["validation"]))
            self.assertTrue(split_article_ids["train"].isdisjoint(split_article_ids["test"]))
            self.assertTrue(split_article_ids["validation"].isdisjoint(split_article_ids["test"]))

            all_items = (
                self._read_jsonl(result.train_path)
                + self._read_jsonl(result.validation_path)
                + self._read_jsonl(result.test_path)
            )
            self.assertTrue(all(len(item["positive"]) <= 40 for item in all_items))
            self.assertTrue(all(item["query"].startswith("Заголовок новости") for item in all_items))

    def test_build_skips_articles_with_short_title_or_text(self) -> None:
        """Сборщик отбрасывает статьи, которые не годятся для пары title -> text."""
        articles = [
            self._article(article_id=1, title="Коротко", text="полезный текст " * 20),
            self._article(article_id=2, title="Нормальный заголовок", text="мало"),
            self._article(article_id=3, title="Нормальный заголовок", text="полезный текст " * 20),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            builder = TrainingDatasetBuilder(
                news_repository=FakeNewsRepository(articles),
                config=DatasetBuildConfig(
                    output_dir=Path(temp_dir),
                    min_title_chars=10,
                    min_text_chars=30,
                ),
            )

            result = builder.build()
            stats = json.loads(result.stats_path.read_text(encoding="utf-8"))
            all_items = (
                self._read_jsonl(result.train_path)
                + self._read_jsonl(result.validation_path)
                + self._read_jsonl(result.test_path)
            )

            self.assertEqual(result.accepted_articles, 1)
            self.assertEqual(stats["skipped"]["short_title"], 1)
            self.assertEqual(stats["skipped"]["short_text"], 1)
            self.assertEqual([item["article_id"] for item in all_items], [3])

    def _article(self, *, article_id: int, title: str, text: str) -> Article:
        """Собрать минимальную ORM-статью для тестов ML-датасета."""
        article = Article(
            source_id=1,
            article_type_id=1,
            direct_url=f"https://example.test/{article_id}",
            title=title,
            text=text,
            published_at=datetime(2026, 1, 1),
            added_at=datetime(2026, 1, 1),
        )
        article.id = article_id
        article.source = Source(
            id=1,
            source_type_id=1,
            base_url="https://example.test/sitemap.xml",
            name="Тестовый источник",
            is_active=True,
        )
        return article

    def _read_jsonl(self, path: Path) -> list[dict]:
        """Прочитать JSONL-файл в список словарей."""
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


if __name__ == "__main__":
    unittest.main()
