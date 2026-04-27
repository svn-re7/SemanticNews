from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
# Скрипт лежит вне пакета app, поэтому добавляем project в sys.path перед импортами приложения.
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402
from app.services.search_service import SearchService  # noqa: E402


def main() -> int:
    """Выполнить ручную проверку семантического поиска из командной строки."""
    args = _parse_args()

    # create_app() инициализирует ORM, чтобы сервис мог сохранить Request и SearchResult.
    create_app()
    result = SearchService().search(args.query, top_k=args.top_k)

    print(f"Запрос сохранен: request_id={result.request_id}")
    print(f"Нормализованный запрос: {result.query_text}")

    if not result.items:
        print("Результаты не найдены. Проверьте, что FAISS-индекс пересобран по текущей базе.")
        return 0

    for item in result.items:
        print(
            "{position}. article_id={article_id}, relevance={relevance:.4f}, title={title}".format(
                position=item.position,
                article_id=item.article_id,
                relevance=item.relevance,
                title=item.title,
            )
        )

    return 0


def _parse_args() -> argparse.Namespace:
    """Прочитать параметры ручного запуска поиска."""
    parser = argparse.ArgumentParser(description="Ручная проверка семантического поиска.")
    parser.add_argument("query", help="Текст поискового запроса.")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Сколько ближайших статей вернуть.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
