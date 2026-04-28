from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select

from app.models.dto import SearchQueryDTO
from app.models.entities import Request
from app.orm import get_session, session_scope


class RequestRepository:
    """Репозиторий для операций чтения и сохранения поисковых запросов."""

    def create(self, query_data: SearchQueryDTO) -> int:
        """Создать новый поисковый запрос в базе данных и вернуть его идентификатор."""
        # Репозиторий получает DTO и сам создает ORM-объект Request.
        request = Request(
            query_text=query_data.query_text,
            executed_at=query_data.executed_at,
        )

        with session_scope() as session:
            session.add(request)
            # flush нужен, чтобы база выдала id еще до завершения транзакции.
            session.flush()
            return request.id

    def get_by_id(self, request_id: int) -> Optional[Request]:
        """Вернуть запрос по id или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(Request).where(Request.id == request_id)
            return session.execute(stmt).scalar_one_or_none()

    def list_requests(self, limit: int, offset: int = 0) -> list[Request]:
        """Вернуть список запросов с сортировкой от новых к старым."""
        with get_session() as session:
            stmt = (
                select(Request)
                .order_by(Request.executed_at.desc(), Request.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return session.execute(stmt).scalars().all()

    def count_requests(self) -> int:
        """Вернуть общее количество сохраненных поисковых запросов."""
        with get_session() as session:
            stmt = select(func.count(Request.id))
            return session.execute(stmt).scalar_one()
