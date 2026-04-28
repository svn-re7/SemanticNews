from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from app.models.dto import QueryLogCreateDTO, SourceLogCreateDTO
from app.repositories.event_type_repository import EventTypeRepository
from app.repositories.query_log_repository import QueryLogRepository
from app.repositories.source_log_repository import SourceLogRepository


class LoggingService:
    """Сервис записи технических событий в SourceLog и QueryLog."""

    def __init__(
        self,
        *,
        event_type_repository: EventTypeRepository | None = None,
        source_log_repository: SourceLogRepository | None = None,
        query_log_repository: QueryLogRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        # Зависимости подменяются в тестах, а в приложении используются реальные репозитории.
        self.event_type_repository = (
            event_type_repository if event_type_repository is not None else EventTypeRepository()
        )
        self.source_log_repository = (
            source_log_repository if source_log_repository is not None else SourceLogRepository()
        )
        self.query_log_repository = (
            query_log_repository if query_log_repository is not None else QueryLogRepository()
        )
        self.now_provider = now_provider if now_provider is not None else datetime.now

    def log_source_event(self, *, source_id: int, event_code: str) -> int:
        """Записать событие, связанное с источником."""
        event_type_id = self._resolve_event_type_id(event_code)
        return self.source_log_repository.create(
            SourceLogCreateDTO(
                source_id=source_id,
                event_type_id=event_type_id,
                logged_at=self.now_provider(),
            )
        )

    def log_query_event(self, *, request_id: int, event_code: str) -> int:
        """Записать событие, связанное с поисковым запросом."""
        event_type_id = self._resolve_event_type_id(event_code)
        return self.query_log_repository.create(
            QueryLogCreateDTO(
                request_id=request_id,
                event_type_id=event_type_id,
                logged_at=self.now_provider(),
            )
        )

    def _resolve_event_type_id(self, event_code: str) -> int:
        """Найти id типа события по стабильному машинному коду."""
        event_type = self.event_type_repository.get_by_code(event_code)
        if event_type is None:
            raise ValueError(f"Тип события с code={event_code} не найден. Запустите seed_reference_data.py.")
        return event_type.id
