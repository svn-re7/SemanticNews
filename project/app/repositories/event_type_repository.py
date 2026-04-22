from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.models.dto import ReferenceValueCreateDTO
from app.models.entities import EventType
from app.orm import get_session, session_scope


class EventTypeRepository:
    """Репозиторий для операций чтения и сохранения типов технических событий."""

    def create(self, event_type_data: ReferenceValueCreateDTO) -> int:
        """Создать новый тип события и вернуть его идентификатор."""
        event_type = EventType(
            code=event_type_data.code,
            name=event_type_data.name,
            description=event_type_data.description,
        )

        with session_scope() as session:
            session.add(event_type)
            # flush нужен, чтобы база выдала id еще до завершения транзакции.
            session.flush()
            return event_type.id

    def get_by_id(self, event_type_id: int) -> Optional[EventType]:
        """Вернуть тип события по id или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(EventType).where(EventType.id == event_type_id)
            return session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> Optional[EventType]:
        """Вернуть тип события по машинному коду или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(EventType).where(EventType.code == code)
            return session.execute(stmt).scalar_one_or_none()

    def list_all(self) -> list[EventType]:
        """Вернуть список всех типов технических событий."""
        with get_session() as session:
            stmt = select(EventType).order_by(EventType.name.asc(), EventType.id.asc())
            return session.execute(stmt).scalars().all()
