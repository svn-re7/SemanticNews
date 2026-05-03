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

    # Параметры для компонентов поиска и адаптации embedding-модели.
    # Сам FAISS-файл хранит векторы, но не знает ничего про ORM-id статей.
    FAISS_INDEX_PATH = BASE_DIR / "instance" / "news.index"
    # JSON-карта нужна, чтобы по позиции найденного FAISS-вектора вернуться к article_id в SQLite.
    FAISS_ID_MAP_PATH = BASE_DIR / "instance" / "news_index_ids.json"
    # Базовая embedding-модель используется, пока нет локально дообученной версии.
    EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    # Каталог локально дообученной модели, которую провайдер сможет подхватить без смены остального кода.
    ADAPTED_EMBEDDING_MODEL_DIR = BASE_DIR / "instance" / "models" / "news-embeddings"

    # Telegram runtime-файлы хранятся локально и не попадают в git.
    TELEGRAM_RUNTIME_DIR = BASE_DIR / "instance" / "telegram"
    # Config содержит api_id/api_hash, которые пользователь вводит через UI один раз.
    TELEGRAM_CONFIG_PATH = TELEGRAM_RUNTIME_DIR / "config.json"
    # Session хранит авторизацию конкретного Telegram-аккаунта для Telethon.
    TELEGRAM_SESSION_PATH = TELEGRAM_RUNTIME_DIR / "semanticnews.session"
