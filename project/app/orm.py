from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import Config


# Базовый класс, от которого наследуются все ORM-модели проекта.
Base = declarative_base()

# Движок SQLAlchemy, через который приложение подключается к SQLite.
_engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    future=True,
)

# Фабрика ORM-сессий.
SessionLocal = sessionmaker(
    bind=_engine,  # Привязываем все создаваемые сессии к общему engine приложения.
    autoflush=False,  # Не отправляем изменения в БД автоматически перед каждым запросом.
    autocommit=False,  # Не фиксируем транзакции автоматически, commit делается явно.
    expire_on_commit=False,  # Не исчезает из пользования ORM-объекты сразу после commit, чтобы ими можно было пользоваться дальше.
    future=True,  # Включаем современный стиль работы SQLAlchemy 2.x.
)


def get_engine():
    """Вернуть объект engine для работы с базой данных."""
    return _engine


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Открыть ORM-сессию для чтения или простых операций и гарантированно закрыть ее.

    Эта функция не выполняет commit автоматически.
    Для сценариев записи с commit/rollback нужно использовать session_scope().
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Открыть ORM-сессию в рамках транзакции.

    Если код внутри блока выполняется успешно, изменения фиксируются через commit.
    Если возникает ошибка, выполняется rollback.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
