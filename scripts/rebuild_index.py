from __future__ import annotations

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
# Скрипт лежит вне пакета app, поэтому добавляем project в sys.path перед импортами приложения.
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402
from app.services.indexing_service import IndexingService  # noqa: E402


def main() -> int:
    """Пересобрать FAISS-индекс по всем статьям из SQLite."""
    # create_app() инициализирует ORM и гарантирует доступность таблиц перед чтением статей.
    create_app()

    result = IndexingService().rebuild_full_index()
    if result.articles_count == 0:
        print("В базе нет статей. Старый FAISS-индекс удален, карта ID очищена.")
        return 0

    print(f"Статей проиндексировано: {result.articles_count}")
    print(f"Размерность векторов: {result.vector_size}")
    print(f"FAISS-индекс: {result.index_path}")
    print(f"Карта article_id: {result.id_map_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
