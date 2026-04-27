from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402
from app.models.dto import NewsDetailDTO  # noqa: E402


class NewsControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        """Создать тестовый Flask-клиент для проверки карточки новости."""
        app = create_app()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_detail_page_from_search_has_back_link_to_search_results(self) -> None:
        """Карточка новости умеет возвращать пользователя к результатам поиска."""
        fake_service = FakeNewsService()

        with patch("app.controllers.news_controller.NewsService", return_value=fake_service):
            response = self.client.get("/news/10?return_to=search&search_q=экономика")

        self.assertEqual(response.status_code, 200)
        self.assertIn("К результатам поиска", response.text)
        self.assertIn("/search/?q=", response.text)


class FakeNewsService:
    """Подменный сервис новости для теста контроллера без SQLite."""

    def get_news_detail(self, article_id: int) -> NewsDetailDTO:
        """Вернуть готовую карточку новости."""
        return NewsDetailDTO(
            article_id=article_id,
            title="Тестовая новость",
            text="Текст новости",
            direct_url="https://example.test/news",
            source_name="Тестовый источник",
            published_at=datetime(2026, 1, 1, 12, 0),
        )


if __name__ == "__main__":
    unittest.main()
