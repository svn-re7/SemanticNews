from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402


class IngestionControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        """Создать тестовый Flask-клиент для проверки UI ingestion."""
        app = create_app()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_ingestion_page_shows_start_button(self) -> None:
        """Страница ingestion показывает кнопку запуска сбора новостей."""
        response = self.client.get("/ingestion")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Запустить сбор новостей", response.text)
        self.assertIn("/ingestion/start", response.text)

    def test_ingestion_status_endpoint_returns_json(self) -> None:
        """Endpoint статуса ingestion возвращает JSON для polling из UI."""
        response = self.client.get("/ingestion/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertIn("is_running", response.json)


if __name__ == "__main__":
    unittest.main()
