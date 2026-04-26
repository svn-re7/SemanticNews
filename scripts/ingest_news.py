from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy.exc import OperationalError


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
# Скрипт лежит вне пакета app, поэтому добавляем project в sys.path перед импортами приложения.
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app
from app.services.ingestion_service import IngestionResult, IngestionService 


def main() -> int:
    """Запустить ручной сценарий ingestion из командной строки."""
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Фабрика приложения создает недостающие таблицы через init_extensions().
    create_app()
    service = IngestionService()

    try:
        # Если указан конкретный источник, запускаем узкий сценарий для отладки одного pipeline.
        if args.source_id is not None:
            results = [
                service.ingest_source_by_id(
                    args.source_id,
                    sitemap_limit=args.sitemap_limit,
                    max_articles=args.max_articles,
                )
            ]
        else:
            # Без source-id обрабатываем все активные источники из БД.
            results = service.ingest_active_sources(
                sitemap_limit=args.sitemap_limit,
                max_articles_per_source=args.max_articles,
            )
    except OperationalError as error:
        print(
            "Не удалось выполнить ingestion: текущая SQLite-база не соответствует ORM-схеме. "
            "Проверьте структуру таблиц и справочники перед запуском."
        )
        print(f"Техническая причина: {error}")
        return 1

    _print_results(results)
    return 0


def _parse_args() -> argparse.Namespace:
    """Прочитать параметры ручного запуска ingestion."""
    parser = argparse.ArgumentParser(description="Запуск сбора новостей в SQLite.")
    parser.add_argument(
        "--source-id",
        type=int,
        default=None,
        help="Идентификатор источника. Если не указан, обрабатываются все активные источники.",
    )
    parser.add_argument(
        "--sitemap-limit",
        type=int,
        default=5,
        help="Сколько вложенных sitemap-файлов читать из sitemap-индекса.",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=10,
        help="Максимальное количество статей на один источник.",
    )
    return parser.parse_args()


def _print_results(results: list[IngestionResult]) -> None:
    """Вывести краткий итог работы ingestion."""
    if not results:
        print("Активные источники для ingestion не найдены.")
        return

    # Выводим только итоговые счетчики, чтобы ручной запуск был удобен для проверки сценария.
    for result in results:
        print(
            "Источник {source_id}: найдено={found}, сохранено={saved}, "
            "дубли={duplicates}, без текста={empty}, без типа={missing_type}".format(
                source_id=result.source_id,
                found=result.found,
                saved=result.saved,
                duplicates=result.skipped_duplicates,
                empty=result.skipped_empty_text,
                missing_type=result.skipped_missing_type,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
