from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models.dto import ArticleCreateDTO
from app.models.entities import Article
from app.orm import get_session, session_scope


class NewsRepository:
    """Репозиторий для операций чтения и сохранения статей."""

    def create(self, article_data: ArticleCreateDTO) -> int:
        """Создать новую статью в базе данных и вернуть ее идентификатор."""
        # Репозиторий получает DTO, а ORM-объект создает уже внутри себя.
        article = Article(
            source_id=article_data.source_id,
            article_type_id=article_data.article_type_id,
            direct_url=article_data.direct_url,
            title=article_data.title,
            text=article_data.text,
            published_at=article_data.published_at,
            added_at=article_data.added_at,
        )

        # Для записи используем транзакционный контекст с commit/rollback.
        with session_scope() as session:
            session.add(article)
            # flush нужен, чтобы база выдала id еще до завершения блока.
            session.flush()
            return article.id

    def get_by_id(self, article_id: int) -> Optional[Article]:
        """Вернуть статью по id или None, если запись не найдена."""
        with get_session() as session:
            stmt = (
                select(Article)
                .options(joinedload(Article.source))
                .where(Article.id == article_id)
            )
            return session.execute(stmt).scalar_one_or_none()

    def get_by_direct_url(self, direct_url: str) -> Optional[Article]:
        """Вернуть статью по прямому URL или None, если такой записи нет."""
        with get_session() as session:
            stmt = select(Article).where(Article.direct_url == direct_url)
            return session.execute(stmt).scalar_one_or_none()

    def list_articles(self, limit: int, offset: int = 0) -> list[Article]:
        """Вернуть список статей с сортировкой по дате публикации от новых к старым."""
        with get_session() as session:
            stmt = (
                select(Article)
                .options(joinedload(Article.source))
                .order_by(Article.published_at.desc(), Article.id.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(session.execute(stmt).scalars().all())

    def count_articles(self) -> int:
        """Вернуть общее количество сохраненных статей."""
        with get_session() as session:
            stmt = select(func.count(Article.id))
            return session.execute(stmt).scalar_one()

    def get_by_ids(self, article_ids: list[int]) -> list[Article]:
        """Вернуть список статей по набору идентификаторов."""
        # Если список пустой, запрос в базу делать не нужно.
        if not article_ids:
            return []

        with get_session() as session:
            stmt = (
                select(Article)
                .options(joinedload(Article.source))
                .where(Article.id.in_(article_ids))
            )
            return list(session.execute(stmt).scalars().all())
