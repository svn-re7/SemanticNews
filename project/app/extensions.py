from flask import Flask

import app.models.entities
from app.orm import Base, get_engine


def init_extensions(app: Flask) -> None:
    """
    Инициализация расширений приложения Flask.
    Здесь подключаются инфраструктурные компоненты: ORM, кэш, и т.п.
    """
    # Импорт моделей выше гарантирует, что все таблицы уже зарегистрированы в Base.metadata.
    # После этого можно безопасно создать отсутствующие таблицы в базе данных.
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
