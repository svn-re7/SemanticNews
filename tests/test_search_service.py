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

from app.models.dto import SearchResultCreateDTO  # noqa: E402
from app.models.entities import Article, Request, SearchResult, Source  # noqa: E402
from app.services.search_service import SearchService  # noqa: E402


class FakeEmbeddingService:
    """Тестовый embedding-сервис, который не загружает реальную ML-модель."""

    def encode_query(self, query_text: str) -> np.ndarray:
        """Вернуть вектор запроса, ближайший к первой тестовой статье."""
        return np.array([1.0, 0.0, 0.0], dtype=np.float32)


class FakeNewsRepository:
    """Тестовый репозиторий статей без обращения к SQLite."""

    def __init__(self, articles: list[Article]) -> None:
        self.articles_by_id = {article.id: article for article in articles}

    def get_by_ids(self, article_ids: list[int]) -> list[Article]:
        """Вернуть статьи по id, имитируя репозиторий приложения."""
        return [self.articles_by_id[article_id] for article_id in article_ids]


class FakeRequestRepository:
    """Тестовый репозиторий поисковых запросов."""

    def __init__(
        self,
        saved_request: Request | None = None,
        saved_requests: list[Request] | None = None,
    ) -> None:
        self.created_query_text: str | None = None
        self.saved_request = saved_request
        self.saved_requests = saved_requests or []
        self.history_limit: int | None = None
        self.history_offset: int | None = None

    def create(self, query_data) -> int:
        """Запомнить созданный запрос и вернуть стабильный id."""
        self.created_query_text = query_data.query_text
        return 77

    def get_by_id(self, request_id: int) -> Request | None:
        """Вернуть сохраненный тестовый запрос по id."""
        return self.saved_request if self.saved_request and self.saved_request.id == request_id else None

    def list_requests(self, limit: int, offset: int = 0) -> list[Request]:
        """Вернуть последние запросы для истории поиска."""
        self.history_limit = limit
        self.history_offset = offset
        return self.saved_requests[offset : offset + limit]

    def count_requests(self) -> int:
        """Вернуть общее количество тестовых запросов."""
        return len(self.saved_requests)


class FakeSearchResultRepository:
    """Тестовый репозиторий результатов поиска."""

    def __init__(self, saved_results: list[SearchResult] | None = None) -> None:
        self.created_results: list[SearchResultCreateDTO] = []
        self.saved_results = saved_results or []

    def create_many(self, results_data: list[SearchResultCreateDTO]) -> list[int]:
        """Запомнить результаты, которые сервис должен сохранить в БД."""
        self.created_results = results_data
        return [100 + index for index, _ in enumerate(results_data)]

    def list_by_request_id(self, request_id: int) -> list[SearchResult]:
        """Вернуть сохраненные результаты конкретного запроса."""
        return [result for result in self.saved_results if result.request_id == request_id]


class SearchServiceTest(unittest.TestCase):
    def test_search_returns_articles_in_faiss_order_and_saves_request_results(self) -> None:
        """Сервис возвращает статьи в порядке FAISS и сохраняет историю поиска."""
        articles = [
            self._article(article_id=10, title="Экономика"),
            self._article(article_id=20, title="Спорт"),
        ]
        request_repository = FakeRequestRepository()
        result_repository = FakeSearchResultRepository()

        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "news.index"
            id_map_path = Path(temp_dir) / "news_index_ids.json"
            self._write_test_index(index_path)
            self._write_test_id_map(id_map_path)

            service = SearchService(
                embedding_service=FakeEmbeddingService(),
                news_repository=FakeNewsRepository(articles),
                request_repository=request_repository,
                search_result_repository=result_repository,
                index_path=index_path,
                id_map_path=id_map_path,
            )

            result = service.search("экономика", top_k=2)

            self.assertEqual(result.request_id, 77)
            self.assertEqual(result.query_text, "экономика")
            self.assertEqual([item.article_id for item in result.items], [10, 20])
            self.assertEqual([item.position for item in result.items], [1, 2])
            self.assertGreater(result.items[0].relevance, result.items[1].relevance)

            self.assertEqual(request_repository.created_query_text, "экономика")
            self.assertEqual(
                [(item.request_id, item.article_id, item.position) for item in result_repository.created_results],
                [(77, 10, 1), (77, 20, 2)],
            )

    def test_search_skips_inactive_sources_and_keeps_requested_result_count(self) -> None:
        """Поиск не возвращает статьи из выключенных источников и добирает активные кандидаты из FAISS."""
        articles = [
            self._article(article_id=10, title="Выключенный источник", is_active=False),
            self._article(article_id=20, title="Активная экономика"),
            self._article(article_id=30, title="Активные финансы"),
        ]
        result_repository = FakeSearchResultRepository()

        with tempfile.TemporaryDirectory() as temp_dir:
            index_path = Path(temp_dir) / "news.index"
            id_map_path = Path(temp_dir) / "news_index_ids.json"
            self._write_three_article_index(index_path)
            self._write_three_article_id_map(id_map_path)

            service = SearchService(
                embedding_service=FakeEmbeddingService(),
                news_repository=FakeNewsRepository(articles),
                request_repository=FakeRequestRepository(),
                search_result_repository=result_repository,
                index_path=index_path,
                id_map_path=id_map_path,
            )

            result = service.search("экономика", top_k=2)

            self.assertEqual([item.article_id for item in result.items], [20, 30])
            self.assertEqual([item.position for item in result.items], [1, 2])
            self.assertEqual(
                [(item.article_id, item.position) for item in result_repository.created_results],
                [(20, 1), (30, 2)],
            )

    def test_get_saved_results_returns_persisted_results_without_embedding_search(self) -> None:
        """Сохраненная выдача читается из SQLite-слоя без повторного FAISS-поиска."""
        articles = [
            self._article(article_id=10, title="Экономика"),
            self._article(article_id=20, title="Спорт"),
        ]
        request = Request(query_text="экономика", executed_at=datetime(2026, 1, 1))
        request.id = 77
        saved_results = [
            self._search_result(request_id=77, article_id=20, relevance=0.7, position=1),
            self._search_result(request_id=77, article_id=10, relevance=0.5, position=2),
        ]
        embedding_service = FailingEmbeddingService()

        service = SearchService(
            embedding_service=embedding_service,
            news_repository=FakeNewsRepository(articles),
            request_repository=FakeRequestRepository(saved_request=request),
            search_result_repository=FakeSearchResultRepository(saved_results=saved_results),
        )

        result = service.get_saved_results(77)

        self.assertEqual(result.request_id, 77)
        self.assertEqual(result.query_text, "экономика")
        self.assertEqual([item.article_id for item in result.items], [20, 10])
        self.assertEqual([item.position for item in result.items], [1, 2])
        self.assertFalse(embedding_service.was_called)

    def test_get_search_history_returns_paginated_request_dtos_without_embedding_search(self) -> None:
        """История поиска читается постранично из RequestRepository и не запускает embedding/FAISS."""
        first_request = self._request(request_id=77, query_text="экономика", executed_at=datetime(2026, 1, 1, 12, 0))
        second_request = self._request(request_id=76, query_text="спорт", executed_at=datetime(2026, 1, 1, 11, 0))
        third_request = self._request(request_id=75, query_text="политика", executed_at=datetime(2026, 1, 1, 10, 0))
        request_repository = FakeRequestRepository(saved_requests=[first_request, second_request, third_request])
        embedding_service = FailingEmbeddingService()

        service = SearchService(
            embedding_service=embedding_service,
            news_repository=FakeNewsRepository([]),
            request_repository=request_repository,
            search_result_repository=FakeSearchResultRepository(),
        )

        history = service.get_search_history(page=2, per_page=2)

        self.assertEqual(request_repository.history_limit, 2)
        self.assertEqual(request_repository.history_offset, 2)
        self.assertEqual([item.request_id for item in history.items], [75])
        self.assertEqual(history.page, 2)
        self.assertEqual(history.per_page, 2)
        self.assertEqual(history.total_count, 3)
        self.assertTrue(history.has_previous)
        self.assertFalse(history.has_next)
        self.assertFalse(embedding_service.was_called)

    def _write_test_index(self, index_path: Path) -> None:
        """Создать маленький FAISS-индекс для теста поискового сценария."""
        embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float32,
        )
        index = faiss.IndexFlatIP(3)
        index.add(embeddings)
        faiss.write_index(index, str(index_path))

    def _write_test_id_map(self, id_map_path: Path) -> None:
        """Создать карту соответствия позиций FAISS и id тестовых статей."""
        id_map_path.write_text(
            json.dumps({"article_ids": [10, 20], "vector_size": 3, "index_size": 2}),
            encoding="utf-8",
        )

    def _write_three_article_index(self, index_path: Path) -> None:
        """Создать FAISS-индекс, где ближайшая статья принадлежит выключенному источнику."""
        embeddings = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.9, 0.1, 0.0],
                [0.8, 0.2, 0.0],
            ],
            dtype=np.float32,
        )
        index = faiss.IndexFlatIP(3)
        index.add(embeddings)
        faiss.write_index(index, str(index_path))

    def _write_three_article_id_map(self, id_map_path: Path) -> None:
        """Создать карту FAISS-позиций для сценария с выключенным источником."""
        id_map_path.write_text(
            json.dumps({"article_ids": [10, 20, 30], "vector_size": 3, "index_size": 3}),
            encoding="utf-8",
        )

    def _article(self, article_id: int, title: str, *, is_active: bool = True) -> Article:
        """Собрать минимальную статью с источником для результата поиска."""
        source = Source(source_type_id=1, base_url="https://example.test", name="Тест", is_active=is_active)
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
        article.source = source
        return article

    def _search_result(
        self,
        *,
        request_id: int,
        article_id: int,
        relevance: float,
        position: int,
    ) -> SearchResult:
        """Собрать ORM-объект сохраненного результата поиска."""
        search_result = SearchResult(
            request_id=request_id,
            article_id=article_id,
            relevance=relevance,
            position=position,
        )
        search_result.id = position
        return search_result

    def _request(self, *, request_id: int, query_text: str, executed_at: datetime) -> Request:
        """Собрать ORM-объект поискового запроса для теста истории."""
        request = Request(query_text=query_text, executed_at=executed_at)
        request.id = request_id
        return request


class FailingEmbeddingService:
    """Embedding-сервис, который не должен вызываться при чтении сохраненной выдачи."""

    def __init__(self) -> None:
        self.was_called = False

    def encode_query(self, query_text: str) -> np.ndarray:
        """Зафиксировать ошибочный вызов embedding при чтении истории."""
        self.was_called = True
        raise AssertionError("Saved results must not call embeddings")


if __name__ == "__main__":
    unittest.main()
