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
        self.assertIn("Полный сбор", response.text)
        self.assertIn("Остановить сбор", response.text)
        self.assertIn("/ingestion/start", response.text)
        self.assertIn("/ingestion/start-full", response.text)
        self.assertIn("/ingestion/stop", response.text)
        self.assertIn("ingestion-results-table", response.text)

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
        self.assertEqual(fake_service.received_max_workers, ingestion_controller.INGESTION_MAX_WORKERS)
        self.assertEqual(payload["mode"], "initial")
        self.assertEqual(payload["article_count_before"], 250)
        self.assertEqual(payload["results"][0]["source_name"], "Тестовый источник")
        self.assertEqual(payload["results"][0]["saved"], 2)
        self.assertIn("skipped_low_quality_text", payload["results"][0])

    def test_full_background_task_forces_initial_ingestion(self) -> None:
        """Полный сбор запускает initial-режим независимо от текущего размера базы."""
        original_service = ingestion_controller.IngestionService
        fake_service = FakeScheduledIngestionService
        fake_service.received_initial_article_threshold = None
        fake_service.received_initial_articles_per_source = None

        try:
            ingestion_controller.IngestionService = fake_service
            with ingestion_controller._task_lock:
                ingestion_controller._task_state.run_kind = "full"

            ingestion_controller._run_ingestion_task()
            payload = ingestion_controller._serialize_state()
        finally:
            ingestion_controller.IngestionService = original_service
            reset_ingestion_state()

        self.assertEqual(fake_service.received_initial_article_threshold, 10**12)
        self.assertEqual(fake_service.received_initial_articles_per_source, 1000)
        self.assertEqual(payload["run_kind"], "full")

    def test_auto_ingestion_starts_background_task_when_sources_need_refresh(self) -> None:
        """Автостарт запускает фоновую задачу, если сервис видит устаревшие источники."""
        original_service = ingestion_controller.IngestionService
        original_thread = ingestion_controller.Thread

        try:
            ingestion_controller.IngestionService = FakeAutoStartIngestionService
            ingestion_controller.Thread = FakeThread
            FakeAutoStartIngestionService.should_run = True
            FakeThread.was_started = False

            started = ingestion_controller.start_auto_ingestion_if_needed()
            payload = ingestion_controller._serialize_state()
        finally:
            ingestion_controller.IngestionService = original_service
            ingestion_controller.Thread = original_thread
            reset_ingestion_state()

        self.assertTrue(started)
        self.assertTrue(FakeThread.was_started)
        self.assertTrue(payload["is_running"])
        self.assertIn("Автообновление", payload["message"])

    def test_auto_ingestion_does_not_start_when_sources_are_fresh(self) -> None:
        """Автостарт не запускает задачу, если свежие данные уже есть."""
        original_service = ingestion_controller.IngestionService

        try:
            ingestion_controller.IngestionService = FakeAutoStartIngestionService
            FakeAutoStartIngestionService.should_run = False

            started = ingestion_controller.start_auto_ingestion_if_needed()
            payload = ingestion_controller._serialize_state()
        finally:
            ingestion_controller.IngestionService = original_service
            reset_ingestion_state()

        self.assertFalse(started)
        self.assertFalse(payload["is_running"])


class FakeScheduledIngestionService:
    """Подменный ingestion-сервис для проверки контроллера без реального парсинга."""

    was_called = False
    received_should_stop_callback = False
    received_max_workers = None
    received_initial_article_threshold = None
    received_initial_articles_per_source = None

    def run_scheduled_ingestion(self, **kwargs) -> ScheduledIngestionResult:
        """Вернуть готовый результат планового сбора."""
        type(self).was_called = True
        type(self).received_should_stop_callback = callable(kwargs.get("should_stop"))
        type(self).received_max_workers = kwargs.get("max_workers")
        type(self).received_initial_article_threshold = kwargs.get("initial_article_threshold")
        type(self).received_initial_articles_per_source = kwargs.get("initial_articles_per_source")
        return ScheduledIngestionResult(
            mode="initial",
            article_count_before=250,
            results=[
                IngestionResult(
                    source_id=5,
                    source_base_url="https://example.test/sitemap.xml",
                    source_name="Тестовый источник",
                    found=2,
                    saved=2,
                    indexed=2,
                )
            ],
        )


class FakeAutoStartIngestionService:
    """Подменный ingestion-сервис для проверки решения об автостарте."""

    should_run = False

    def should_run_auto_ingestion(self) -> bool:
        """Вернуть заранее заданное решение об автообновлении."""
        return type(self).should_run


class FakeThread:
    """Подменный поток, который не запускает реальную фоновую задачу."""

    was_started = False

    def __init__(self, *, target, daemon: bool) -> None:
        self.target = target
        self.daemon = daemon

    def start(self) -> None:
        """Зафиксировать запуск без выполнения target."""
        type(self).was_started = True


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
        ingestion_controller._task_state.run_kind = "scheduled"


if __name__ == "__main__":
    unittest.main()
