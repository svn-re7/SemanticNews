from __future__ import annotations

from app.models.dto import NewsDetailDTO, NewsListItemDTO
from app.models.entities import Article
from app.repositories.news_repository import NewsRepository


class NewsService:
    """Сервис подготовки новостей для интерфейса."""

    def __init__(self, news_repository: NewsRepository | None = None) -> None:
        # Репозиторий можно подменить в тестах, а в обычном запуске используется рабочий доступ к SQLite.
        self.news_repository = news_repository if news_repository is not None else NewsRepository()

    def get_news_list(self, *, limit: int = 50, offset: int = 0) -> list[NewsListItemDTO]:
        """Получить список последних новостей для страницы просмотра."""
        articles = self.news_repository.list_articles(limit=limit, offset=offset)

        # Сервис превращает ORM-сущности в DTO, чтобы шаблон не зависел от структуры SQLAlchemy-моделей.
        return [self._to_list_item(article) for article in articles]

    def get_news_detail(self, article_id: int) -> NewsDetailDTO | None:
        """Получить данные одной новости для карточки."""
        article = self.news_repository.get_by_id(article_id)
        if article is None:
            return None

        return NewsDetailDTO(
            article_id=article.id,
            title=article.title,
            text=article.text,
            direct_url=article.direct_url,
            source_name=self._source_name(article),
            published_at=article.published_at,
        )

    def _to_list_item(self, article: Article) -> NewsListItemDTO:
        """Собрать краткое представление статьи для списка."""
        return NewsListItemDTO(
            article_id=article.id,
            title=article.title,
            source_name=self._source_name(article),
            published_at=article.published_at,
            preview=self._make_preview(article.text),
        )

    def _source_name(self, article: Article) -> str:
        """Получить имя источника из уже загруженной связи Article.source."""
        if article.source is None:
            return "Неизвестный источник"

        return article.source.name

    def _make_preview(self, text: str, max_length: int = 220) -> str:
        """Сделать короткий фрагмент текста для списка новостей."""
        normalized_text = " ".join(text.split())
        if len(normalized_text) <= max_length:
            return normalized_text

        return f"{normalized_text[:max_length].rstrip()}..."
