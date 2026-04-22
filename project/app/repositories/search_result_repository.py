from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.models.dto import SearchResultCreateDTO
from app.models.entities import SearchResult
from app.orm import get_session, session_scope


class SearchResultRepository:
    """Репозиторий для операций чтения и сохранения результатов поиска."""

    def create(self, result_data: SearchResultCreateDTO) -> int:
        """Создать новую запись результата поиска и вернуть ее идентификатор."""
        # Репозиторий получает DTO и сам создает ORM-объект SearchResult.
        search_result = SearchResult(
            request_id=result_data.request_id,
            article_id=result_data.article_id,
            relevance=result_data.relevance,
            position=result_data.position,
        )

        with session_scope() as session:
            session.add(search_result)
            # flush нужен, чтобы база выдала id еще до завершения транзакции.
            session.flush()
            return search_result.id

    def create_many(self, results_data: list[SearchResultCreateDTO]) -> list[int]:
        """Сохранить список результатов поиска и вернуть их идентификаторы."""
        if not results_data:
            return []

        created_ids: list[int] = []

        with session_scope() as session:
            for result_data in results_data:
                search_result = SearchResult(
                    request_id=result_data.request_id,
                    article_id=result_data.article_id,
                    relevance=result_data.relevance,
                    position=result_data.position,
                )
                session.add(search_result)
                # flush нужен, чтобы после каждой вставки получить id текущей записи.
                session.flush()
                created_ids.append(search_result.id)

        return created_ids

    def get_by_id(self, result_id: int) -> Optional[SearchResult]:
        """Вернуть результат поиска по id или None, если запись не найдена."""
        with get_session() as session:
            stmt = select(SearchResult).where(SearchResult.id == result_id)
            return session.execute(stmt).scalar_one_or_none()

    def list_by_request_id(self, request_id: int) -> list[SearchResult]:
        """Вернуть все результаты поиска для одного запроса в порядке позиций выдачи."""
        with get_session() as session:
            stmt = (
                select(SearchResult)
                .where(SearchResult.request_id == request_id)
                .order_by(SearchResult.position.asc(), SearchResult.id.asc())
            )
            return session.execute(stmt).scalars().all()
