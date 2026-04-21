from flask import Flask

from app.orm import Base, get_engine


def init_extensions(app: Flask) -> None:
    """
    Инициализация расширений приложения Flask.
    Здесь подключаются инфраструктурные компоненты: ORM, кэш, и т.п.
    """
    # Инициализация SQLAlchemy ORM и создание таблиц при первом запуске
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
