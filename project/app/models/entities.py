# Откладывает вычисление type hints, чтобы можно было ссылаться на классы,
# объявленные ниже в этом же файле.
from __future__ import annotations

# Импортирует тип даты и времени для колонок с временными метками.
from datetime import datetime

# Импортирует типы колонок и ограничения из SQLAlchemy.
from sqlalchemy import (
    # Целочисленный тип колонки в базе данных.
    Integer,
    # Строковый тип колонки для короткого текста.
    String,
    # Текстовый тип колонки для длинного текста.
    Text,
    # Тип колонки для чисел с плавающей точкой.
    Float,
    # Тип колонки для даты и времени.
    DateTime,
    # Описание внешнего ключа между таблицами.
    ForeignKey,
    # Ограничение уникальности по одной или нескольким колонкам.
    UniqueConstraint,
)
# Mapped описывает тип ORM-поля, mapped_column создает колонку,
# relationship описывает связь между ORM-моделями.
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Базовый класс для всех ORM-моделей проекта.
from app.orm import Base


# Модель таблицы с кодами ошибок.
class Error(Base):
    # Имя таблицы в базе данных.
    __tablename__ = "error"

    # Код ошибки: строковый первичный ключ таблицы error.
    error_code: Mapped[str] = mapped_column(String, primary_key=True)
    # Описание ошибки: длинный текст, может быть пустым.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


# Модель источника новостей.
class Source(Base):
    # Имя таблицы в базе данных.
    __tablename__ = "source"

    # Уникальный идентификатор источника, создается базой автоматически.
    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Базовый URL источника; должен быть уникальным и обязательным.
    base_url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Человекочитаемое название источника; может отсутствовать.
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Время последней индексации источника; может отсутствовать.
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Связь один-ко-многим: один источник может иметь много статей.
    articles: Mapped[list["Article"]] = relationship("Article", back_populates="source")
    # Связь один-ко-многим: один источник может иметь много записей логов.
    logs: Mapped[list["SourceLog"]] = relationship("SourceLog", back_populates="source")


# Модель новостной статьи.
class Article(Base):
    # Имя таблицы в базе данных.
    __tablename__ = "article"

    # Уникальный идентификатор статьи, создается базой автоматически.
    article_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Прямая ссылка на статью; должна быть уникальной и обязательной.
    direct_url: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Заголовок статьи; может отсутствовать.
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    # Полный текст статьи; может отсутствовать.
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Идентификатор источника, к которому относится статья.
    source_id: Mapped[int] = mapped_column(
        # Внешний ключ на source.source_id; при удалении источника удаляются его статьи.
        Integer, ForeignKey("source.source_id", ondelete="CASCADE"), nullable=False
    )
    # Дата публикации статьи; может отсутствовать.
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Дата добавления статьи в систему; может отсутствовать.
    added_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ORM-связь многие-к-одному: статья принадлежит одному источнику.
    source: Mapped["Source"] = relationship("Source", back_populates="articles")
    # ORM-связь один-ко-многим: статья может встречаться в разных результатах поиска.
    search_results: Mapped[list["SearchResult"]] = relationship(
        # Связывает Article с SearchResult и синхронизирует обратное поле article.
        "SearchResult", back_populates="article"
    )


# Модель пользовательского поискового запроса.
class Request(Base):
    # Имя таблицы в базе данных.
    __tablename__ = "request"

    # Уникальный идентификатор запроса, создается базой автоматически.
    request_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Время выполнения запроса; может отсутствовать.
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Текст поискового запроса; обязательное поле.
    query_text: Mapped[str] = mapped_column(Text, nullable=False)

    # ORM-связь один-ко-многим: один запрос имеет много найденных результатов.
    results: Mapped[list["SearchResult"]] = relationship(
        # Связывает Request с SearchResult и синхронизирует обратное поле request.
        "SearchResult", back_populates="request"
    )
    # ORM-связь один-ко-многим: один запрос может иметь много записей логов.
    logs: Mapped[list["QueryLog"]] = relationship("QueryLog", back_populates="request")


# Модель результата поиска для конкретного запроса и конкретной статьи.
class SearchResult(Base):
    # Имя таблицы в базе данных.
    __tablename__ = "search_result"
    # Дополнительные настройки таблицы.
    __table_args__ = (
        # Запрещает дублировать одну и ту же статью внутри одного и того же запроса.
        UniqueConstraint("request_id", "article_id", name="pk_search_result"),
    )

    # Технический первичный ключ результата поиска, создается базой автоматически.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Идентификатор запроса, которому принадлежит результат.
    request_id: Mapped[int] = mapped_column(
        # Внешний ключ на request.request_id; при удалении запроса удаляются его результаты.
        Integer, ForeignKey("request.request_id", ondelete="CASCADE"), nullable=False
    )
    # Идентификатор статьи, найденной по запросу.
    article_id: Mapped[int] = mapped_column(
        # Внешний ключ на article.article_id; при удалении статьи удаляются ее результаты поиска.
        Integer, ForeignKey("article.article_id", ondelete="CASCADE"), nullable=False
    )
    # Оценка релевантности статьи для запроса; обязательное число.
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    # Позиция статьи в выдаче поиска; обязательное число.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    # ORM-связь многие-к-одному: результат поиска относится к одному запросу.
    request: Mapped["Request"] = relationship("Request", back_populates="results")
    # ORM-связь многие-к-одному: результат поиска относится к одной статье.
    article: Mapped["Article"] = relationship("Article", back_populates="search_results")


# Модель лога ошибок, связанных с поисковыми запросами.
class QueryLog(Base):
    # Имя таблицы в базе данных.
    __tablename__ = "query_log"

    # Уникальный идентификатор записи лога, создается базой автоматически.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Время записи лога; может отсутствовать.
    logged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Идентификатор запроса, к которому относится запись лога.
    request_id: Mapped[int] = mapped_column(
        # Внешний ключ на request.request_id; при удалении запроса удаляются его логи.
        Integer, ForeignKey("request.request_id", ondelete="CASCADE"), nullable=False
    )
    # Код ошибки, сохраненный в таблице error.
    error_code: Mapped[str] = mapped_column(
        # Внешний ключ на error.error_code; ошибка должна существовать в справочнике ошибок.
        String, ForeignKey("error.error_code"), nullable=False
    )

    # ORM-связь многие-к-одному: лог относится к одному поисковому запросу.
    request: Mapped["Request"] = relationship("Request", back_populates="logs")
    # ORM-связь многие-к-одному: лог ссылается на одну ошибку.
    error: Mapped["Error"] = relationship("Error")


# Модель лога ошибок, связанных с источниками новостей.
class SourceLog(Base):
    # Имя таблицы в базе данных.
    __tablename__ = "source_log"

    # Уникальный идентификатор записи лога, создается базой автоматически.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Время записи лога; может отсутствовать.
    logged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Идентификатор источника, к которому относится запись лога.
    source_id: Mapped[int] = mapped_column(
        # Внешний ключ на source.source_id; при удалении источника удаляются его логи.
        Integer, ForeignKey("source.source_id", ondelete="CASCADE"), nullable=False
    )
    # Код ошибки, сохраненный в таблице error.
    error_code: Mapped[str] = mapped_column(
        # Внешний ключ на error.error_code; ошибка должна существовать в справочнике ошибок.
        String, ForeignKey("error.error_code"), nullable=False
    )

    # ORM-связь многие-к-одному: лог относится к одному источнику.
    source: Mapped["Source"] = relationship("Source", back_populates="logs")
    # ORM-связь многие-к-одному: лог ссылается на одну ошибку.
    error: Mapped["Error"] = relationship("Error")

