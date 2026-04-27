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
from app.models.dto import SourceListItemDTO, SourceManagementPageDTO, SourceTypeOptionDTO  # noqa: E402


class SourceControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        """Создать тестовый Flask-клиент для проверки UI источников."""
        app = create_app()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_sources_page_shows_sources_and_create_form(self) -> None:
        """Страница источников показывает список, типы источников и форму добавления."""
        fake_service = FakeSourceService()

        with patch("app.controllers.source_controller.SourceService", return_value=fake_service):
            response = self.client.get("/sources")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Источники", response.text)
        self.assertIn("РИА Новости", response.text)
        self.assertIn('name="base_url"', response.text)
        self.assertIn("Новостное СМИ", response.text)

    def test_create_source_posts_form_to_service(self) -> None:
        """POST формы добавления источника передает данные в SourceService."""
        fake_service = FakeSourceService()

        with patch("app.controllers.source_controller.SourceService", return_value=fake_service):
            response = self.client.post(
                "/sources",
                data={
                    "name": "Новый источник",
                    "base_url": "https://example.test/sitemap.xml",
                    "source_type_id": "1",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            fake_service.created_source,
            ("Новый источник", "https://example.test/sitemap.xml", 1),
        )

    def test_update_source_activity_posts_state_to_service(self) -> None:
        """POST переключения активности передает новый флаг активности в SourceService."""
        fake_service = FakeSourceService()

        with patch("app.controllers.source_controller.SourceService", return_value=fake_service):
            response = self.client.post("/sources/5/active", data={"is_active": "false"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(fake_service.updated_activity, (5, False))


class FakeSourceService:
    """Подменный сервис источников для тестов контроллера без SQLite."""

    def __init__(self) -> None:
        self.created_source: tuple[str, str, int] | None = None
        self.updated_activity: tuple[int, bool] | None = None

    def get_sources_page(self) -> SourceManagementPageDTO:
        """Вернуть готовые данные страницы источников."""
        return SourceManagementPageDTO(
            sources=[
                SourceListItemDTO(
                    source_id=5,
                    name="РИА Новости",
                    base_url="https://ria.ru/sitemap_article_index.xml",
                    source_type_name="Новостное СМИ",
                    is_active=True,
                    last_indexed_at=datetime(2026, 1, 1, 12, 0),
                )
            ],
            source_types=[
                SourceTypeOptionDTO(source_type_id=1, name="Новостное СМИ"),
            ],
        )

    def create_source(self, *, name: str, base_url: str, source_type_id: int) -> int:
        """Запомнить данные нового источника."""
        self.created_source = (name, base_url, source_type_id)
        return 10

    def update_source_activity(self, *, source_id: int, is_active: bool) -> bool:
        """Запомнить изменение активности источника."""
        self.updated_activity = (source_id, is_active)
        return True


if __name__ == "__main__":
    unittest.main()
