from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.models.entities import Article  # noqa: E402
from app.services.indexing_service import IndexingService  # noqa: E402


class FakeNewsRepository:
    """Тестовый репозиторий, который возвращает статьи без обращения к SQLite."""

    def __init__(self, articles: list[Article]) -> None:
        self.articles = articles

    def count_articles(self) -> int:
        """Вернуть количество тестовых статей."""
        return len(self.articles)

    def list_articles(self, limit: int, offset: int = 0) -> list[Article]:
        """Вернуть тестовые статьи в том порядке, который должен попасть в индекс."""
        return self.articles[offset : offset + limit]


class FakeEmbeddingService:
    """Тестовый сервис embeddings с заранее известными векторами."""

    def encode_articles(self, articles: list[Article]) -> np.ndarray:
        """Вернуть нормализованные векторы без загрузки ML-модели."""
        return np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )[: len(articles)]


class IndexingServiceTest(unittest.TestCase):
    def test_rebuild_full_index_writes_faiss_index_and_article_id_map(self) -> None:
        """Полная пересборка индекса сохраняет FAISS-файл и карту article_id."""
        articles = [
            self._article(article_id=10, title="Первая новость"),
            self._article(article_id=20, title="Вторая новость"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "news.index"
            id_map_path = Path(temp_dir) / "news_index_ids.json"
            service = IndexingService(
                news_repository=FakeNewsRepository(articles),
                embedding_service=FakeEmbeddingService(),
                index_path=index_path,
                id_map_path=id_map_path,
            )

            result = service.rebuild_full_index()

            self.assertEqual(result.articles_count, 2)
            self.assertEqual(result.vector_size, 3)
            self.assertTrue(index_path.exists())
            self.assertTrue(id_map_path.exists())

            index = faiss.read_index(str(index_path))
            self.assertEqual(index.ntotal, 2)
            self.assertEqual(index.d, 3)

            id_map = json.loads(id_map_path.read_text(encoding="utf-8"))
            self.assertEqual(id_map["article_ids"], [10, 20])
            self.assertEqual(id_map["vector_size"], 3)
            self.assertEqual(id_map["index_size"], 2)

    def _article(self, article_id: int, title: str) -> Article:
        """Собрать минимальный ORM-объект статьи для теста сервиса."""
        article = Article(
            source_id=1,
            article_type_id=1,
            direct_url=f"https://example.test/{article_id}",
            title=title,
            text="Текст новости",
            published_at=datetime(2026, 1, 1),
            added_at=datetime(2026, 1, 1),
        )
        article.id = article_id
        return article


if __name__ == "__main__":
    unittest.main()
