from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select

from app.models.dto import SourceActiveUpdateDTO, SourceCreateDTO
from app.models.entities import Source
from app.orm import get_session, session_scope


class SourceRepository:
    """Репозиторий для операций чтения и сохранения источников."""

    def create(self, source_data: SourceCreateDTO) -> int:
        """Создать новый источник в базе данных и вернуть его идентификатор."""
        # Репозиторий получает DTO и сам создает ORM-объект Source.
        source = Source(
            source_type_id=source_data.source_type_id,
            base_url=source_data.base_url,
            name=source_data.name,
            is_active=source_data.is_active,
            last_indexed_at=source_data.last_indexed_at,
        )

        with session_scope() as session:
            session.add(source)
            # flush нужен, чтобы база выдала id еще до завершения транзакции.
            session.flush()
            return source.id

    def get_by_id(self, source_id: int) -> Optional[Source]:
        """Вернуть источник по id или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(Source).where(Source.id == source_id)
            return session.execute(stmt).scalar_one_or_none()

    def get_by_base_url(self, base_url: str) -> Optional[Source]:
        """Вернуть источник по базовому URL или None, если такой записи нет."""
        with get_session() as session:
            stmt = select(Source).where(Source.base_url == base_url)
            return session.execute(stmt).scalar_one_or_none()

    def list_sources(self, only_active: bool = False) -> list[Source]:
        """Вернуть список источников с возможной фильтрацией только по активным."""
        with get_session() as session:
            stmt = select(Source).order_by(Source.name.asc(), Source.id.asc())

            if only_active:
                stmt = stmt.where(Source.is_active.is_(True))

            return session.execute(stmt).scalars().all()

    def update_active_state(self, update_data: SourceActiveUpdateDTO) -> bool:
        """Обновить признак активности источника и вернуть факт успешного обновления."""
        with session_scope() as session:
            stmt = select(Source).where(Source.id == update_data.source_id)
            source = session.execute(stmt).scalar_one_or_none()

            if source is None:
                return False

            source.is_active = update_data.is_active
            return True

    def update_last_indexed_at(self, source_id: int, indexed_at: datetime) -> bool:
        """Обновить время последней индексации источника."""
        with session_scope() as session:
            stmt = select(Source).where(Source.id == source_id)
            source = session.execute(stmt).scalar_one_or_none()

            if source is None:
                return False

            source.last_indexed_at = indexed_at
            return True
