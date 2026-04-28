from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.models.dto import QueryLogCreateDTO, SourceLogCreateDTO  # noqa: E402
from app.services.logging_service import LoggingService  # noqa: E402


class LoggingServiceTest(unittest.TestCase):
    def test_log_source_event_resolves_event_code_and_writes_source_log(self) -> None:
        """Сервис логирования пишет SourceLog по человекочитаемому коду события."""
        event_type_repository = FakeEventTypeRepository()
        source_log_repository = FakeSourceLogRepository()
        now = datetime(2026, 1, 1, 12, 0)
        service = LoggingService(
            event_type_repository=event_type_repository,
            source_log_repository=source_log_repository,
            query_log_repository=FakeQueryLogRepository(),
            now_provider=lambda: now,
        )

        log_id = service.log_source_event(source_id=5, event_code="ingestion_started")

        self.assertEqual(log_id, 101)
        self.assertEqual(event_type_repository.requested_code, "ingestion_started")
        self.assertEqual(
            source_log_repository.created_log,
            SourceLogCreateDTO(source_id=5, event_type_id=10, logged_at=now),
        )

    def test_log_query_event_resolves_event_code_and_writes_query_log(self) -> None:
        """Сервис логирования пишет QueryLog по человекочитаемому коду события."""
        event_type_repository = FakeEventTypeRepository()
        query_log_repository = FakeQueryLogRepository()
        now = datetime(2026, 1, 1, 12, 0)
        service = LoggingService(
            event_type_repository=event_type_repository,
            source_log_repository=FakeSourceLogRepository(),
            query_log_repository=query_log_repository,
            now_provider=lambda: now,
        )

        log_id = service.log_query_event(request_id=7, event_code="search_executed")

        self.assertEqual(log_id, 201)
        self.assertEqual(event_type_repository.requested_code, "search_executed")
        self.assertEqual(
            query_log_repository.created_log,
            QueryLogCreateDTO(request_id=7, event_type_id=20, logged_at=now),
        )

    def test_unknown_event_code_raises_clear_error(self) -> None:
        """Неизвестный код события должен давать понятную ошибку до записи лога."""
        service = LoggingService(
            event_type_repository=FakeEventTypeRepository(),
            source_log_repository=FakeSourceLogRepository(),
            query_log_repository=FakeQueryLogRepository(),
            now_provider=lambda: datetime(2026, 1, 1),
        )

        with self.assertRaisesRegex(ValueError, "unknown_event"):
            service.log_source_event(source_id=5, event_code="unknown_event")


@dataclass(slots=True)
class FakeEventType:
    """Минимальная подмена EventType для тестов сервиса логирования."""

    id: int
    code: str


class FakeEventTypeRepository:
    """Подменный репозиторий типов событий."""

    def __init__(self) -> None:
        self.requested_code: str | None = None

    def get_by_code(self, code: str) -> FakeEventType | None:
        """Вернуть тип события по известному тестовому коду."""
        self.requested_code = code
        if code == "ingestion_started":
            return FakeEventType(id=10, code=code)
        if code == "search_executed":
            return FakeEventType(id=20, code=code)
        return None


class FakeSourceLogRepository:
    """Подменный репозиторий source_log."""

    def __init__(self) -> None:
        self.created_log: SourceLogCreateDTO | None = None

    def create(self, log_data: SourceLogCreateDTO) -> int:
        """Запомнить создаваемый лог источника."""
        self.created_log = log_data
        return 101


class FakeQueryLogRepository:
    """Подменный репозиторий query_log."""

    def __init__(self) -> None:
        self.created_log: QueryLogCreateDTO | None = None

    def create(self, log_data: QueryLogCreateDTO) -> int:
        """Запомнить создаваемый лог запроса."""
        self.created_log = log_data
        return 201


if __name__ == "__main__":
    unittest.main()
