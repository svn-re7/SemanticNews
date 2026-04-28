from __future__ import annotations

from app.models.dto import SourceLogCreateDTO
from app.models.entities import SourceLog
from app.orm import session_scope


class SourceLogRepository:
    """Репозиторий для записи технических событий источников."""

    def create(self, log_data: SourceLogCreateDTO) -> int:
        """Создать запись SourceLog и вернуть ее идентификатор."""
        # Репозиторий получает уже готовые id, а выбор типа события остается в сервисном слое.
        source_log = SourceLog(
            source_id=log_data.source_id,
            event_type_id=log_data.event_type_id,
            logged_at=log_data.logged_at,
        )

        with session_scope() as session:
            session.add(source_log)
            # flush нужен, чтобы получить id до выхода из транзакции.
            session.flush()
            return source_log.id
