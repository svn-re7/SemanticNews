from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Базовая конфигурация для Flask-приложения."""

    # Секретный ключ для защиты cookie и сессий
    SECRET_KEY = "dev-secret-key"
    # Путь к файлу базы данных SQLite
    DATABASE_PATH = BASE_DIR / "instance" / "app.db"
    # Строка подключения для SQLAlchemy
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"

    # Параметры для компонентов поиска и адаптации embedding-модели
    FAISS_INDEX_PATH = BASE_DIR / "instance" / "news.index"  # Путь к индекс-файлу FAISS для поиска
    EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # Базовая embedding-модель
    ADAPTED_EMBEDDING_MODEL_DIR = BASE_DIR / "instance" / "models" / "news-embeddings"  # Каталог локально дообученной модели
