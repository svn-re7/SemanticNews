# Откладывает вычисление аннотаций типов, чтобы корректно работали ссылки вперед.
from __future__ import annotations

# Типы для аннотаций сигнатур методов.
from typing import List, Optional

# Конструктор SQL-запроса SELECT из SQLAlchemy.
from sqlalchemy import select

# ORM-сущность, представляющая запись статьи в БД.
from app.models.entities import Article
# Фабрика/контекстный менеджер сессии для работы с БД.
from app.orm import get_session


class NewsRepository:
    """Репозиторий для операций чтения/сохранения новостных статей."""

    def add_news(self, article: Article) -> int:
        """Сохранить статью и вернуть сгенерированный ID."""
        # Открываем область сессии/транзакции БД.
        with get_session() as session:
            # Добавляем объект статьи в сессию для вставки.
            session.add(article)
            # Принудительно отправляем SQL, чтобы сразу получить автосгенерированный PK.
            session.flush()
            # Возвращаем первичный ключ, присвоенный базой данных.
            return article.article_id

    def get_news_by_id(self, news_id: int) -> Optional[Article]:
        """Вернуть статью по ID или None, если запись не найдена."""
        # Открываем сессию БД для чтения.
        with get_session() as session:
            # Формируем SELECT ... WHERE article_id = :news_id
            stmt = select(Article).where(Article.article_id == news_id)
            # Получаем 0 или 1 запись и преобразуем в ORM-объект или None.
            result = session.execute(stmt).scalar_one_or_none()
            # Возвращаем найденную статью (или None).
            return result

    def search_news(self, query: str, limit: int = 10) -> List[Article]:
        """Поиск статей по заголовку/тексту через регистронезависимый ILIKE."""
        # Оборачиваем запрос в wildcard-шаблон для поиска по подстроке.
        pattern = f"%{query}%"
        # Открываем сессию БД для выполнения поиска.
        with get_session() as session:
            # Собираем запрос: title ILIKE pattern ИЛИ text ILIKE pattern + лимит строк.
            stmt = (
                select(Article)
                .where(
                    (Article.title.ilike(pattern)) | (Article.text.ilike(pattern))
                )
                .limit(limit)
            )
            # Выполняем запрос и получаем все подходящие ORM-объекты.
            result = session.execute(stmt).scalars().all()
            # Возвращаем обычный Python-список объектов Article.
            return list(result)
