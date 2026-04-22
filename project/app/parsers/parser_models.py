from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# Модели ниже описывают результат каждого шага парсинга:
# sitemap-индекс -> ссылка на статью -> извлеченная статья.
@dataclass
class SitemapEntry:
    """Запись sitemap-индекса с URL вложенного sitemap-файла и диапазоном дат."""

    # URL вложенного sitemap-файла.
    url: str
    # Дата начала диапазона, если она зашита в URL sitemap.
    date_start: datetime | None = None
    # Дата конца диапазона, если она зашита в URL sitemap.
    date_end: datetime | None = None


@dataclass
class ArticleReference:
    """Ссылка на статью, извлеченная из sitemap-файла."""

    # Прямой URL статьи.
    url: str
    # Время последнего изменения из sitemap, если оно указано.
    lastmod: datetime | None = None


@dataclass
class ExtractedArticle:
    """Нормализованный результат извлечения статьи из HTML-страницы."""

    # Прямой URL статьи после возможных редиректов.
    url: str
    # Заголовок статьи, если он найден.
    title: str | None
    # Основной текст статьи.
    text: str
    # Дата публикации, если ее удалось определить.
    published_at: datetime | None
    # Код типа материала по формату или каналу публикации.
    article_type_code: str = "web_article"
