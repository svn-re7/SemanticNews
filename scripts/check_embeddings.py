from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
# Скрипт лежит вне пакета app, поэтому явно подключаем проектное приложение.
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402
from app.repositories.news_repository import NewsRepository  # noqa: E402
from app.services.embedding_service import EmbeddingService  # noqa: E402


def main() -> int:
    """Проверить построение эмбеддингов для статей из SQLite."""
    args = _parse_args()

    # create_app() гарантирует, что ORM и таблицы приложения инициализированы перед чтением статей.
    create_app()

    articles = NewsRepository().list_articles(limit=args.limit)
    if not articles:
        print("В базе нет статей для проверки embeddings. Сначала запустите ingestion.")
        return 1

    embedding_service = EmbeddingService()
    embeddings = embedding_service.encode_articles(articles)

    print(f"Статей обработано: {len(articles)}")
    print(f"Форма массива embeddings: {embeddings.shape}")
    print(f"Размерность модели: {embedding_service.vector_size}")

    for index, article in enumerate(articles, start=1):
        print(f"{index}. article_id={article.id}, title={article.title}")

    return 0


def _parse_args() -> argparse.Namespace:
    """Прочитать параметры ручной проверки embeddings."""
    parser = argparse.ArgumentParser(description="Проверка построения embeddings для статей.")
    parser.add_argument(
        "--limit",
        type=int,
        default=2,
        help="Сколько последних статей взять из SQLite.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
