from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.models.dto import SourceActiveUpdateDTO, SourceCreateDTO  # noqa: E402
from app.services.source_service import SourceService  # noqa: E402


class SourceServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        """Подготовить сервис с подменными репозиториями без обращения к SQLite."""
        self.source_repository = FakeSourceRepository()
        self.source_type_repository = FakeSourceTypeRepository()
        self.logging_service = FakeLoggingService()
        self.indexing_service = FakeIndexingService()
        self.service = SourceService(
            source_repository=self.source_repository,
            source_type_repository=self.source_type_repository,
            logging_service=self.logging_service,
            indexing_service=self.indexing_service,
        )

    def test_get_sources_page_returns_sources_and_type_options(self) -> None:
        """Сервис собирает DTO страницы из источников и справочника типов."""
        page = self.service.get_sources_page()

        self.assertEqual(len(page.sources), 1)
        self.assertEqual(page.sources[0].name, "РИА Новости")
        self.assertEqual(page.sources[0].source_type_name, "Новостное СМИ")
        self.assertEqual(len(page.source_types), 1)
        self.assertEqual(page.source_types[0].name, "Новостное СМИ")

    def test_create_source_rejects_invalid_url(self) -> None:
        """Источник без http/https URL не должен попадать в репозиторий."""
        with self.assertRaises(ValueError):
            self.service.create_source(name="Bad", base_url="example.test/sitemap.xml", source_type_id=1)

        self.assertIsNone(self.source_repository.created_source)

    def test_create_source_rejects_duplicate_url(self) -> None:
        """Дубликат base_url запрещен на уровне сервиса до записи в БД."""
        with self.assertRaises(ValueError):
            self.service.create_source(
                name="РИА Дубль",
                base_url="https://ria.ru/sitemap_article_index.xml",
                source_type_id=1,
            )

        self.assertIsNone(self.source_repository.created_source)

    def test_create_source_uses_domain_as_fallback_name(self) -> None:
        """Если пользователь не указал имя, сервис берет домен из URL."""
        created_id = self.service.create_source(
            name="",
            base_url="https://example.test/sitemap.xml",
            source_type_id=1,
        )

        self.assertEqual(created_id, 10)
        self.assertIsNotNone(self.source_repository.created_source)
        self.assertEqual(self.source_repository.created_source.name, "example.test")
        self.assertTrue(self.source_repository.created_source.is_active)
        self.assertEqual(self.logging_service.source_events, [(10, "source_created")])

    def test_update_source_activity_passes_dto_to_repository(self) -> None:
        """Переключение активности передается в репозиторий отдельным DTO."""
        updated = self.service.update_source_activity(source_id=5, is_active=False)

        self.assertTrue(updated)
        self.assertEqual(
            self.source_repository.updated_activity,
            SourceActiveUpdateDTO(source_id=5, is_active=False),
        )
        self.assertEqual(self.logging_service.source_events, [(5, "source_disabled")])

    def test_update_source_activity_logs_enabled_event(self) -> None:
        """Включение источника пишет событие source_enabled."""
        updated = self.service.update_source_activity(source_id=5, is_active=True)

        self.assertTrue(updated)
        self.assertEqual(self.logging_service.source_events, [(5, "source_enabled")])

    def test_delete_source_delegates_to_repository(self) -> None:
        """Удаление источника передается в репозиторий отдельным сценарием."""
        deleted = self.service.delete_source(source_id=5)

        self.assertTrue(deleted)
        self.assertEqual(self.source_repository.deleted_source_id, 5)
        self.assertEqual(self.indexing_service.rebuild_count, 1)

    def test_delete_source_does_not_rebuild_index_when_source_was_not_deleted(self) -> None:
        """FAISS не пересобирается, если репозиторий не нашел источник для удаления."""
        self.source_repository.delete_result = False

        deleted = self.service.delete_source(source_id=404)

        self.assertFalse(deleted)
        self.assertEqual(self.source_repository.deleted_source_id, 404)
        self.assertEqual(self.indexing_service.rebuild_count, 0)


@dataclass(slots=True)
class FakeSourceType:
    """Минимальная подмена ORM-типа источника для сервисных тестов."""

    id: int
    name: str


@dataclass(slots=True)
class FakeSource:
    """Минимальная подмена ORM-источника для сервисных тестов."""

    id: int
    name: str
    base_url: str
    source_type: FakeSourceType
    is_active: bool
    last_indexed_at: datetime | None


class FakeSourceRepository:
    """Подменный репозиторий источников, который хранит вызовы в памяти."""

    def __init__(self) -> None:
        self.existing_source = FakeSource(
            id=5,
            name="РИА Новости",
            base_url="https://ria.ru/sitemap_article_index.xml",
            source_type=FakeSourceType(id=1, name="Новостное СМИ"),
            is_active=True,
            last_indexed_at=datetime(2026, 1, 1, 12, 0),
        )
        self.created_source: SourceCreateDTO | None = None
        self.updated_activity: SourceActiveUpdateDTO | None = None
        self.deleted_source_id: int | None = None
        self.delete_result = True

    def list_sources(self) -> list[FakeSource]:
        """Вернуть фиксированный список источников."""
        return [self.existing_source]

    def get_by_base_url(self, base_url: str) -> FakeSource | None:
        """Найти источник по URL среди подменных данных."""
        if base_url == self.existing_source.base_url:
            return self.existing_source
        return None

    def create(self, source_data: SourceCreateDTO) -> int:
        """Запомнить DTO создаваемого источника."""
        self.created_source = source_data
        return 10

    def update_active_state(self, update_data: SourceActiveUpdateDTO) -> bool:
        """Запомнить DTO обновления активности."""
        self.updated_activity = update_data
        return True

    def delete_with_articles(self, source_id: int) -> bool:
        """Запомнить удаление источника со связанными статьями."""
        self.deleted_source_id = source_id
        return self.delete_result


class FakeSourceTypeRepository:
    """Подменный репозиторий типов источников."""

    def __init__(self) -> None:
        self.source_type = FakeSourceType(id=1, name="Новостное СМИ")

    def list_all(self) -> list[FakeSourceType]:
        """Вернуть доступные типы источников для формы."""
        return [self.source_type]

    def get_by_id(self, source_type_id: int) -> FakeSourceType | None:
        """Найти тип источника по идентификатору."""
        if source_type_id == self.source_type.id:
            return self.source_type
        return None


class FakeLoggingService:
    """Подменный сервис логирования действий с источниками."""

    def __init__(self) -> None:
        self.source_events: list[tuple[int, str]] = []

    def log_source_event(self, *, source_id: int, event_code: str) -> int:
        """Запомнить событие источника."""
        self.source_events.append((source_id, event_code))
        return len(self.source_events)


class FakeIndexingService:
    """Подменный сервис индексации, который считает пересборки FAISS."""

    def __init__(self) -> None:
        self.rebuild_count = 0

    def rebuild_full_index(self) -> None:
        """Запомнить, что сервис источников запросил полную пересборку индекса."""
        self.rebuild_count += 1


if __name__ == "__main__":
    unittest.main()
