from __future__ import annotations

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def resolve_runtime_base_dir(
    *,
    frozen: bool | None = None,
    executable: str | None = None,
    source_base_dir: Path = BASE_DIR,
    env_runtime_dir: str | None = None,
) -> Path:
    """Вернуть базовый каталог для runtime-файлов в source и PyInstaller-запуске."""
    if env_runtime_dir is None:
        env_runtime_dir = os.environ.get("SEMANTICNEWS_RUNTIME_DIR")
    if env_runtime_dir:
        return Path(env_runtime_dir).resolve()

    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if executable is None:
        executable = sys.executable

    # В frozen-режиме исходники могут лежать во временном _MEIPASS, а БД/индекс должны быть пишущимися.
    if frozen:
        return Path(executable).resolve().parent

    return source_base_dir.resolve()


RUNTIME_BASE_DIR = resolve_runtime_base_dir()


class Config:
    """Базовая конфигурация для Flask-приложения."""

    # Секретный ключ для защиты cookie и сессий
    SECRET_KEY = "dev-secret-key"
    # Путь к файлу базы данных SQLite
    DATABASE_PATH = RUNTIME_BASE_DIR / "instance" / "app.db"
    # Строка подключения для SQLAlchemy
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"

    # Параметры для компонентов поиска и адаптации embedding-модели.
    # Сам FAISS-файл хранит векторы, но не знает ничего про ORM-id статей.
    FAISS_INDEX_PATH = RUNTIME_BASE_DIR / "instance" / "news.index"
    # JSON-карта нужна, чтобы по позиции найденного FAISS-вектора вернуться к article_id в SQLite.
    FAISS_ID_MAP_PATH = RUNTIME_BASE_DIR / "instance" / "news_index_ids.json"
    # Базовая embedding-модель используется, пока нет локально дообученной версии.
    EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Каталог локально дообученной модели, которую провайдер сможет подхватить без смены остального кода.
    ADAPTED_EMBEDDING_MODEL_DIR = RUNTIME_BASE_DIR / "instance" / "models" / "news-embeddings"
    # Runtime-каталог для train/validation/test датасетов, собранных из локальной SQLite-базы.
    ML_DATASET_DIR = RUNTIME_BASE_DIR / "instance" / "ml_datasets"

    # Telegram runtime-файлы хранятся локально и не попадают в git.
    TELEGRAM_RUNTIME_DIR = RUNTIME_BASE_DIR / "instance" / "telegram"
    # Config содержит api_id/api_hash, которые пользователь вводит через UI один раз.
    TELEGRAM_CONFIG_PATH = TELEGRAM_RUNTIME_DIR / "config.json"
    # Session хранит авторизацию конкретного Telegram-аккаунта для Telethon.
    TELEGRAM_SESSION_PATH = TELEGRAM_RUNTIME_DIR / "semanticnews.session"
