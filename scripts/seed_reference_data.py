from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
# Скрипт находится в корне scripts, поэтому явно подключаем пакет приложения.
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app
from app.models.dto import (
    ReferenceValueCreateDTO,
    ReferenceValueUpdateDTO,
    SourceCreateDTO,
    SourceSeedUpdateDTO,
)
from app.repositories.article_type_repository import ArticleTypeRepository
from app.repositories.event_type_repository import EventTypeRepository
from app.repositories.source_repository import SourceRepository
from app.repositories.source_type_repository import SourceTypeRepository


@dataclass(frozen=True, slots=True)
class ReferenceSeedItem:
    """Одна стартовая запись справочника."""

    code: str
    name: str
    description: str | None = None


SOURCE_TYPES = [
    ReferenceSeedItem(
        code="news_media",
        name="Новостное медиа",
        description="Обычный новостной сайт или редакционное СМИ.",
    ),
    ReferenceSeedItem(
        code="organization_site",
        name="Сайт организации",
        description="Официальный сайт компании, университета или ведомства.",
    ),
    ReferenceSeedItem(
        code="personal_page",
        name="Персональная страница",
        description="Личный сайт или публичная страница автора.",
    ),
    ReferenceSeedItem(
        code="telegram_channel",
        name="Telegram-канал",
        description="Источник материалов из Telegram, поддержка будет добавлена позже.",
    ),
]

ARTICLE_TYPES = [
    ReferenceSeedItem(
        code="web_article",
        name="Веб-статья",
        description="Обычная HTML-страница со статьей.",
    ),
    ReferenceSeedItem(
        code="telegram_post",
        name="Пост Telegram",
        description="Материал из Telegram, поддержка будет добавлена позже.",
    ),
    ReferenceSeedItem(
        code="pdf_document",
        name="PDF-документ",
        description="Материал в формате PDF.",
    ),
    ReferenceSeedItem(
        code="presentation",
        name="Презентация",
        description="Материал в формате презентации.",
    ),
    ReferenceSeedItem(
        code="other",
        name="Другое",
        description="Безопасное значение по умолчанию для неизвестного формата.",
    ),
]

EVENT_TYPES = [
    ReferenceSeedItem(
        code="ingestion_started",
        name="Сбор источника запущен",
        description="Начало сценария сбора статей для конкретного источника.",
    ),
    ReferenceSeedItem(
        code="ingestion_finished",
        name="Сбор источника завершен",
        description="Сбор источника завершился без критической ошибки.",
    ),
    ReferenceSeedItem(
        code="ingestion_failed",
        name="Ошибка сбора источника",
        description="Сбор источника завершился ошибкой парсинга, сети или внутреннего сервиса.",
    ),
    ReferenceSeedItem(
        code="source_created",
        name="Источник добавлен",
        description="Пользователь добавил новый источник новостей.",
    ),
    ReferenceSeedItem(
        code="source_deleted",
        name="Источник удален",
        description="Пользователь удалил источник вместе с его статьями.",
    ),
    ReferenceSeedItem(
        code="source_enabled",
        name="Источник включен",
        description="Пользователь включил источник для сбора и поиска.",
    ),
    ReferenceSeedItem(
        code="source_disabled",
        name="Источник выключен",
        description="Пользователь выключил источник из активного набора.",
    ),
    ReferenceSeedItem(
        code="search_executed",
        name="Поиск выполнен",
        description="Пользователь выполнил новый семантический поиск.",
    ),
    ReferenceSeedItem(
        code="search_results_opened",
        name="Сохраненная выдача открыта",
        description="Пользователь открыл ранее сохраненные результаты поиска.",
    ),
]

DEFAULT_SOURCE_URL = "https://ria.ru/sitemap_article_index.xml"
DEFAULT_SOURCE_NAME = "РИА Новости"


def main() -> int:
    """Заполнить стартовые справочники и источник для первого ingestion."""
    # Создаем недостающие таблицы до обращения к репозиториям.
    create_app()

    source_type_repository = SourceTypeRepository()
    article_type_repository = ArticleTypeRepository()
    event_type_repository = EventTypeRepository()
    source_repository = SourceRepository()

    source_type_ids = _seed_reference_values(source_type_repository, SOURCE_TYPES)
    article_type_ids = _seed_reference_values(article_type_repository, ARTICLE_TYPES)
    event_type_ids = _seed_reference_values(event_type_repository, EVENT_TYPES)

    # Стартовый источник использует тип news_media, потому что РИА является новостным медиа.
    source_id = _seed_default_source(
        source_repository=source_repository,
        source_type_id=source_type_ids["news_media"],
    )

    print("Seed завершен.")
    print(f"Типы источников: {source_type_ids}")
    print(f"Типы материалов: {article_type_ids}")
    print(f"Типы событий: {event_type_ids}")
    print(f"Стартовый источник: id={source_id}, url={DEFAULT_SOURCE_URL}")
    return 0


def _seed_reference_values(repository, items: list[ReferenceSeedItem]) -> dict[str, int]:
    """Создать отсутствующие записи справочника и вернуть их id по коду."""
    ids_by_code: dict[str, int] = {}

    for item in items:
        # Seed должен быть идемпотентным: повторный запуск не создает дубли, а выравнивает существующие значения.
        existing_value = repository.get_by_code(item.code)
        if existing_value is not None:
            _update_reference_value(repository, existing_value.id, item)
            ids_by_code[item.code] = existing_value.id
            continue

        created_id = repository.create(
            ReferenceValueCreateDTO(
                code=item.code,
                name=item.name,
                description=item.description,
            )
        )
        ids_by_code[item.code] = created_id

    return ids_by_code


def _update_reference_value(repository, value_id: int, item: ReferenceSeedItem) -> None:
    """Обновить название и описание существующей записи справочника."""
    # Это нужно после ручных запусков из PowerShell, где кириллица могла попасть в БД с неверной кодировкой.
    repository.update_display_fields(
        ReferenceValueUpdateDTO(
            value_id=value_id,
            name=item.name,
            description=item.description,
        )
    )


def _seed_default_source(
    *,
    source_repository: SourceRepository,
    source_type_id: int,
) -> int:
    """Создать стартовый источник РИА, если он еще не добавлен в БД."""
    existing_source = source_repository.get_by_base_url(DEFAULT_SOURCE_URL)
    if existing_source is not None:
        _update_default_source(source_repository, existing_source.id, source_type_id)
        return existing_source.id

    return source_repository.create(
        SourceCreateDTO(
            source_type_id=source_type_id,
            base_url=DEFAULT_SOURCE_URL,
            name=DEFAULT_SOURCE_NAME,
            is_active=True,
        )
    )


def _update_default_source(
    source_repository: SourceRepository,
    source_id: int,
    source_type_id: int,
) -> None:
    """Обновить стартовый источник, если он уже существовал до запуска seed."""
    # Источник тоже выравниваем, чтобы повторный запуск seed исправлял имя и активность записи.
    source_repository.update_seed_data(
        SourceSeedUpdateDTO(
            source_id=source_id,
            source_type_id=source_type_id,
            name=DEFAULT_SOURCE_NAME,
            is_active=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
