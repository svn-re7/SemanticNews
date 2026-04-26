from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ParsedArticleDTO:
    """Нормализованный результат работы парсера до подготовки к сохранению в БД."""

    # Базовый URL источника, по которому ingestion-слой находит Source в базе данных.
    source_base_url: str
    # Прямой URL конкретной статьи или документа.
    direct_url: str
    # Заголовок материала, извлеченный парсером.
    title: str
    # Полный текст материала, извлеченный парсером.
    text: str
    # Дата публикации, которая может отсутствовать в исходных данных.
    published_at: datetime | None
    # Код типа материала, например web_article или pdf_document.
    article_type_code: str


@dataclass(slots=True)
class ArticleCreateDTO:
    """Готовые данные для создания записи Article в базе данных."""

    # Внутренний идентификатор источника из таблицы Source.
    source_id: int
    # Внутренний идентификатор типа материала из таблицы ArticleType.
    article_type_id: int
    # Прямой URL статьи, который должен быть уникальным.
    direct_url: str
    # Заголовок статьи, уже прошедший базовую проверку.
    title: str
    # Текст статьи, уже прошедший базовую проверку.
    text: str
    # Дата публикации в финальном виде, готовом к записи в БД.
    published_at: datetime
    # Время добавления статьи в систему.
    added_at: datetime


@dataclass(slots=True)
class SearchQueryDTO:
    """Входные данные для сценария семантического поиска."""

    # Текст поискового запроса пользователя.
    query_text: str
    # Время выполнения поискового запроса.
    executed_at: datetime
    # Максимальное количество результатов, которое нужно вернуть.
    limit: int


@dataclass(slots=True)
class SearchResultItemDTO:
    """Одна позиция поисковой выдачи, подготовленная для сервиса и интерфейса."""

    # Идентификатор статьи в таблице Article.
    article_id: int
    # Заголовок статьи для отображения в интерфейсе.
    title: str
    # Прямой URL статьи.
    direct_url: str
    # Имя источника, из которого получен материал.
    source_name: str
    # Дата публикации статьи.
    published_at: datetime
    # Числовая оценка релевантности статьи для конкретного запроса.
    relevance: float
    # Позиция статьи в выдаче.
    position: int


@dataclass(slots=True)
class SearchResultCreateDTO:
    """Готовые данные для создания записи SearchResult в базе данных."""

    # Идентификатор поискового запроса из таблицы Request.
    request_id: int
    # Идентификатор статьи из таблицы Article.
    article_id: int
    # Числовая оценка релевантности статьи для данного запроса.
    relevance: float
    # Позиция статьи в выдаче.
    position: int


@dataclass(slots=True)
class SourceCreateDTO:
    """Готовые данные для создания записи Source в базе данных."""

    # Внутренний идентификатор типа источника из таблицы SourceType.
    source_type_id: int
    # Базовый URL источника, который должен быть уникальным.
    base_url: str
    # Отображаемое имя источника.
    name: str
    # Признак активности источника.
    is_active: bool
    # Время последней индексации. Для нового источника отсутствует.
    last_indexed_at: datetime | None = None


@dataclass(slots=True)
class SourceActiveUpdateDTO:
    """Данные для изменения признака активности источника."""

    # Идентификатор источника, который нужно обновить.
    source_id: int
    # Новое значение признака активности.
    is_active: bool


@dataclass(slots=True)
class SourceSeedUpdateDTO:
    """Данные для выравнивания стартового источника при повторном seed."""

    # Идентификатор существующего источника.
    source_id: int
    # Идентификатор типа источника из справочника SourceType.
    source_type_id: int
    # Человекочитаемое имя источника.
    name: str
    # Признак активности источника.
    is_active: bool


@dataclass(slots=True)
class ReferenceValueCreateDTO:
    """Готовые данные для создания записи в справочнике."""

    # Стабильный машинный код значения справочника.
    code: str
    # Человекочитаемое имя значения справочника.
    name: str
    # Дополнительное пояснение значения справочника.
    description: str | None = None


@dataclass(slots=True)
class ReferenceValueUpdateDTO:
    """Данные для обновления человекочитаемых полей записи справочника."""

    # Идентификатор существующей записи справочника.
    value_id: int
    # Новое человекочитаемое имя.
    name: str
    # Новое пояснение значения справочника.
    description: str | None = None
