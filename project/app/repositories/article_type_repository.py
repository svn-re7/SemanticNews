from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.models.dto import ReferenceValueCreateDTO, ReferenceValueUpdateDTO
from app.models.entities import ArticleType
from app.orm import get_session, session_scope


class ArticleTypeRepository:
    """Репозиторий для операций чтения и сохранения типов материалов."""

    def create(self, article_type_data: ReferenceValueCreateDTO) -> int:
        """Создать новый тип материала и вернуть его идентификатор."""
        article_type = ArticleType(
            code=article_type_data.code,
            name=article_type_data.name,
            description=article_type_data.description,
        )

        with session_scope() as session:
            session.add(article_type)
            # flush нужен, чтобы база выдала id еще до завершения транзакции.
            session.flush()
            return article_type.id

    def get_by_id(self, article_type_id: int) -> Optional[ArticleType]:
        """Вернуть тип материала по id или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(ArticleType).where(ArticleType.id == article_type_id)
            return session.execute(stmt).scalar_one_or_none()

    def get_by_code(self, code: str) -> Optional[ArticleType]:
        """Вернуть тип материала по машинному коду или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(ArticleType).where(ArticleType.code == code)
            return session.execute(stmt).scalar_one_or_none()

    def update_display_fields(self, update_data: ReferenceValueUpdateDTO) -> bool:
        """Обновить название и описание типа материала."""
        with session_scope() as session:
            stmt = select(ArticleType).where(ArticleType.id == update_data.value_id)
            article_type = session.execute(stmt).scalar_one_or_none()

            if article_type is None:
                return False

            # Репозиторий меняет только поля справочника, которые можно безопасно выравнивать через seed.
            article_type.name = update_data.name
            article_type.description = update_data.description
            return True

    def list_all(self) -> list[ArticleType]:
        """Вернуть список всех типов материалов."""
        with get_session() as session:
            stmt = select(ArticleType).order_by(ArticleType.name.asc(), ArticleType.id.asc())
            return session.execute(stmt).scalars().all()
