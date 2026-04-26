from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.models.dto import ReferenceValueCreateDTO, ReferenceValueUpdateDTO
from app.models.entities import SourceType
from app.orm import get_session, session_scope


class SourceTypeRepository:
    """Репозиторий для операций чтения и сохранения типов источников."""

    def create(self, source_type_data: ReferenceValueCreateDTO) -> int:
        """Создать новый тип источника и вернуть его идентификатор."""
        source_type = SourceType(
            code=source_type_data.code,
            name=source_type_data.name,
            description=source_type_data.description,
        )

        with session_scope() as session:
            session.add(source_type)
            # flush нужен, чтобы база выдала id еще до завершения транзакции.
            session.flush()
            return source_type.id

    def get_by_id(self, source_type_id: int) -> Optional[SourceType]:
        """Вернуть тип источника по id или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(SourceType).where(SourceType.id == source_type_id)
            return session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> Optional[SourceType]:
        """Вернуть тип источника по машинному коду или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(SourceType).where(SourceType.code == code)
            return session.execute(stmt).scalar_one_or_none()

    def update_display_fields(self, update_data: ReferenceValueUpdateDTO) -> bool:
        """Обновить название и описание типа источника."""
        with session_scope() as session:
            stmt = select(SourceType).where(SourceType.id == update_data.value_id)
            source_type = session.execute(stmt).scalar_one_or_none()

            if source_type is None:
                return False

            # Репозиторий меняет только поля справочника, которые можно безопасно выравнивать через seed.
            source_type.name = update_data.name
            source_type.description = update_data.description
            return True

    def list_all(self) -> list[SourceType]:
        """Вернуть список всех типов источников."""
        with get_session() as session:
            stmt = select(SourceType).order_by(SourceType.name.asc(), SourceType.id.asc())
            return session.execute(stmt).scalars().all()
