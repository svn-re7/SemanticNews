from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402
from app.models.dto import SearchResponseDTO, SearchResultItemDTO  # noqa: E402


class SearchControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        """Создать тестовый Flask-клиент для проверки HTTP-маршрутов поиска."""
        app = create_app()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_search_page_without_query_shows_form(self) -> None:
        """Страница поиска без q показывает форму и не запускает семантический поиск."""
        response = self.client.get("/search")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Семантический поиск", response.text)
        self.assertIn('name="q"', response.text)

    def test_search_page_with_query_shows_results(self) -> None:
        """Страница поиска с q выводит результаты, полученные из SearchService."""
        fake_service = FakeSearchService(
            SearchResponseDTO(
                request_id=15,
                query_text="экономика",
                items=[
                    SearchResultItemDTO(
                        article_id=10,
                        title="Экономическая новость",
                        direct_url="https://example.test/news",
                        source_name="Тестовый источник",
                        published_at=datetime(2026, 1, 1, 12, 0),
                        relevance=0.91,
                        position=1,
                    )
                ],
            )
        )

        with patch("app.controllers.search_controller.SearchService", return_value=fake_service):
            response = self.client.get("/search?q=экономика")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_service.last_query, "экономика")
        self.assertEqual(fake_service.last_top_k, 10)
        self.assertIn("Экономическая новость", response.text)
        self.assertIn("/news/10", response.text)
        self.assertIn("return_to=search", response.text)
        self.assertIn("search_q=", response.text)
        self.assertIn("0.9100", response.text)


@dataclass
class FakeSearchService:
    """Подменный сервис поиска для теста контроллера без FAISS и ML-модели."""

    result: SearchResponseDTO
    last_query: str | None = None
    last_top_k: int | None = None

    def search(self, query_text: str, top_k: int) -> SearchResponseDTO:
        """Запомнить аргументы вызова и вернуть заранее подготовленный результат."""
        self.last_query = query_text
        self.last_top_k = top_k
        return self.result


if __name__ == "__main__":
    unittest.main()
