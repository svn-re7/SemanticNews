from __future__ import annotations

from app.models.dto import QueryLogCreateDTO
from app.models.entities import QueryLog
from app.orm import session_scope


class QueryLogRepository:
    """Репозиторий для записи технических событий поисковых запросов."""

    def create(self, log_data: QueryLogCreateDTO) -> int:
        """Создать запись QueryLog и вернуть ее идентификатор."""
        # Репозиторий не знает про event_code, он работает только с внешними ключами таблиц.
        query_log = QueryLog(
            request_id=log_data.request_id,
            event_type_id=log_data.event_type_id,
            logged_at=log_data.logged_at,
        )

        with session_scope() as session:
            session.add(query_log)
            # flush нужен, чтобы получить id до commit.
            session.flush()
            return query_log.id
