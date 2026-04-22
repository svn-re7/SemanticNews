from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.orm import Base


class SourceType(Base):
    """Справочник типов источников."""

    __tablename__ = "source_type"

    # Технический суррогатный ключ записи справочника.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Стабильный машинный код типа источника
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Нзвание, которое можно показывать в интерфейсе.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Пояснение значения справочника для интерфейса и документации.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Один тип источника может использоваться во многих записях Source.
    sources: Mapped[list["Source"]] = relationship("Source", back_populates="source_type")


class ArticleType(Base):
    """Справочник типов материалов по формату или каналу публикации."""

    __tablename__ = "article_type"

    # Технический суррогатный ключ записи справочника.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Машинный код типа материала, например web_article или pdf_document.
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Отображаемое название типа материала.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Дополнительное пояснение значения справочника.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Один тип материала может соответствовать многим статьям.
    articles: Mapped[list["Article"]] = relationship("Article", back_populates="article_type")


class EventType(Base):
    """Справочник типов технических событий для логов."""

    __tablename__ = "event_type"

    # Технический суррогатный ключ записи справочника.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Бизнес-код события
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Отображаемое название события.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Пояснение назначения события.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Один тип события может встречаться в логах источников и запросов.
    source_logs: Mapped[list["SourceLog"]] = relationship("SourceLog", back_populates="event_type")
    query_logs: Mapped[list["QueryLog"]] = relationship("QueryLog", back_populates="event_type")


class Source(Base):
    """Источник материалов, из которого приложение выполняет сбор данных."""

    __tablename__ = "source"

    # Технический суррогатный ключ источника.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ссылка на тип источника из справочника SourceType.
    source_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("source_type.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Базовый URL источника, по которому определяется уникальность записи.
    base_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    # Имя источника
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Признак активности источника в системе.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Время последней индексации или попытки индексации.
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Источник относится к одному типу источника.
    source_type: Mapped["SourceType"] = relationship("SourceType", back_populates="sources")
    # Один источник может содержать много статей.
    articles: Mapped[list["Article"]] = relationship("Article", back_populates="source")
    # Один источник может иметь много технических записей в логе.
    logs: Mapped[list["SourceLog"]] = relationship("SourceLog", back_populates="source")


class Article(Base):
    """Материал, сохраненный в базе после успешного сбора."""

    __tablename__ = "article"

    # Технический суррогатный ключ статьи.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ссылка на источник, из которого получена статья.
    source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("source.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Ссылка на тип материала из справочника ArticleType.
    article_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("article_type.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Прямой URL конкретной статьи или документа.
    direct_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    # Заголовок статьи, обязательный для сохранения.
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # Полный текст статьи, обязательный для сохранения.
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Время публикации статьи. Если исходная дата отсутствует, подставляется текущее время.
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Время добавления статьи в систему.
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Статья относится к одному источнику.
    source: Mapped["Source"] = relationship("Source", back_populates="articles")
    # Статья относится к одному типу материала.
    article_type: Mapped["ArticleType"] = relationship("ArticleType", back_populates="articles")
    # Статья может присутствовать во многих сохраненных результатах поиска.
    search_results: Mapped[list["SearchResult"]] = relationship(
        "SearchResult",
        back_populates="article",
    )


class Request(Base):
    """Поисковый запрос пользователя, сохраняемый в истории поиска."""

    __tablename__ = "request"

    # Технический суррогатный ключ поискового запроса.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Текст поискового запроса, введенного пользователем.
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Время выполнения поискового запроса.
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Один запрос может иметь много сохраненных результатов.
    results: Mapped[list["SearchResult"]] = relationship("SearchResult", back_populates="request")
    # Один запрос может иметь много записей технического лога.
    logs: Mapped[list["QueryLog"]] = relationship("QueryLog", back_populates="request")


class SearchResult(Base):
    """Сохраненный результат семантического поиска для конкретного запроса."""

    __tablename__ = "search_result"
    __table_args__ = (
        # Одна и та же статья не должна повторяться в рамках одного запроса.
        UniqueConstraint("request_id", "article_id", name="uq_search_result_request_article"),
        # В рамках одного запроса каждая позиция выдачи должна быть уникальной.
        UniqueConstraint("request_id", "position", name="uq_search_result_request_position"),
    )

    # Технический суррогатный ключ результата поиска.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ссылка на запрос, которому принадлежит результат.
    request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("request.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Ссылка на статью, попавшую в результаты поиска.
    article_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("article.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Числовая оценка релевантности статьи для конкретного запроса.
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    # Позиция статьи в выдаче.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # Результат относится к одному запросу.
    request: Mapped["Request"] = relationship("Request", back_populates="results")
    # Результат относится к одной статье.
    article: Mapped["Article"] = relationship("Article", back_populates="search_results")


class SourceLog(Base):
    """Технический лог событий, связанных с источниками и ingestion."""

    __tablename__ = "source_log"

    # Технический суррогатный ключ записи лога.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ссылка на источник, к которому относится запись.
    source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("source.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Ссылка на тип события из справочника EventType.
    event_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("event_type.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Время записи события в лог.
    logged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Запись лога относится к одному источнику.
    source: Mapped["Source"] = relationship("Source", back_populates="logs")
    # Запись лога относится к одному типу технического события.
    event_type: Mapped["EventType"] = relationship("EventType", back_populates="source_logs")


class QueryLog(Base):
    """Технический лог событий, связанных с поисковыми запросами."""

    __tablename__ = "query_log"

    # Технический суррогатный ключ записи лога.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ссылка на запрос, к которому относится запись.
    request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("request.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Ссылка на тип события из справочника EventType.
    event_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("event_type.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Время записи события в лог.
    logged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Запись лога относится к одному поисковому запросу.
    request: Mapped["Request"] = relationship("Request", back_populates="logs")
    # Запись лога относится к одному типу технического события.
    event_type: Mapped["EventType"] = relationship("EventType", back_populates="query_logs")
