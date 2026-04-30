from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402
from app.controllers import ingestion_controller  # noqa: E402
from app.services.ingestion_service import IngestionResult, ScheduledIngestionResult  # noqa: E402


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
        self.assertIn("Остановить сбор", response.text)
        self.assertIn("/ingestion/start", response.text)
        self.assertIn("/ingestion/stop", response.text)

    def test_ingestion_status_endpoint_returns_json(self) -> None:
        """Endpoint статуса ingestion возвращает JSON для polling из UI."""
        response = self.client.get("/ingestion/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertIn("is_running", response.json)
        self.assertIn("should_stop", response.json)
        self.assertIn("stopped", response.json)

    def test_stop_endpoint_requests_background_task_stop(self) -> None:
        """Endpoint остановки выставляет флаг мягкой остановки для фоновой задачи."""
        with ingestion_controller._task_lock:
            ingestion_controller._task_state.is_running = True
            ingestion_controller._task_state.should_stop = False

        try:
            response = self.client.post("/ingestion/stop")
        finally:
            reset_ingestion_state()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["should_stop"])
        self.assertTrue(response.json["is_running"])

    def test_background_task_uses_scheduled_ingestion(self) -> None:
        """Фоновая задача запускает умный initial/incremental сценарий ingestion."""
        original_service = ingestion_controller.IngestionService
        fake_service = FakeScheduledIngestionService
        fake_service.was_called = False

        try:
            ingestion_controller.IngestionService = fake_service
            ingestion_controller._run_ingestion_task()
            payload = ingestion_controller._serialize_state()
        finally:
            ingestion_controller.IngestionService = original_service
            reset_ingestion_state()

        self.assertTrue(fake_service.was_called)
        self.assertTrue(fake_service.received_should_stop_callback)
        self.assertEqual(payload["mode"], "initial")
        self.assertEqual(payload["article_count_before"], 250)
        self.assertEqual(payload["results"][0]["saved"], 2)
        self.assertIn("skipped_low_quality_text", payload["results"][0])


class FakeScheduledIngestionService:
    """Подменный ingestion-сервис для проверки контроллера без реального парсинга."""

    was_called = False
    received_should_stop_callback = False

    def run_scheduled_ingestion(self, **kwargs) -> ScheduledIngestionResult:
        """Вернуть готовый результат планового сбора."""
        type(self).was_called = True
        type(self).received_should_stop_callback = callable(kwargs.get("should_stop"))
        return ScheduledIngestionResult(
            mode="initial",
            article_count_before=250,
            results=[
                IngestionResult(
                    source_id=5,
                    source_base_url="https://example.test/sitemap.xml",
                    found=2,
                    saved=2,
                    indexed=2,
                )
            ],
        )


def reset_ingestion_state() -> None:
    """Вернуть in-memory статус ingestion к безопасному начальному состоянию."""
    with ingestion_controller._task_lock:
        ingestion_controller._task_state.is_running = False
        ingestion_controller._task_state.started_at = None
        ingestion_controller._task_state.finished_at = None
        ingestion_controller._task_state.message = "Сбор новостей еще не запускался."
        ingestion_controller._task_state.results = []
        ingestion_controller._task_state.error = None
        ingestion_controller._task_state.mode = None
        ingestion_controller._task_state.article_count_before = None
        ingestion_controller._task_state.should_stop = False
        ingestion_controller._task_state.stopped = False


if __name__ == "__main__":
    unittest.main()
