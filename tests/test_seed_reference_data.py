from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(ROOT_DIR))

from app.models.dto import ReferenceValueCreateDTO, ReferenceValueUpdateDTO  # noqa: E402
from scripts.seed_reference_data import (  # noqa: E402
    EVENT_TYPES,
    STARTER_SOURCES,
    _seed_default_sources,
    _seed_reference_values,
)


class SeedReferenceDataTest(unittest.TestCase):
    def test_event_types_include_mvp_logging_events(self) -> None:
        """Seed содержит минимальный набор типов событий для source/query логов."""
        codes = {item.code for item in EVENT_TYPES}

        self.assertEqual(
            codes,
            {
                "ingestion_started",
                "ingestion_finished",
                "ingestion_failed",
                "source_created",
                "source_deleted",
                "source_enabled",
                "source_disabled",
                "search_executed",
                "search_results_opened",
            },
        )

    def test_seed_reference_values_creates_missing_event_types(self) -> None:
        """Общий seed-helper создает отсутствующие значения справочника событий."""
        repository = FakeReferenceRepository()

        ids_by_code = _seed_reference_values(repository, EVENT_TYPES)

        self.assertEqual(set(ids_by_code), {item.code for item in EVENT_TYPES})
        self.assertEqual(len(repository.created_values), len(EVENT_TYPES))

    def test_seed_reference_values_updates_existing_event_type(self) -> None:
        """Повторный seed выравнивает имя и описание существующего типа события."""
        repository = FakeReferenceRepository(existing_code="ingestion_started")

        ids_by_code = _seed_reference_values(repository, EVENT_TYPES)

        self.assertEqual(ids_by_code["ingestion_started"], 42)
        self.assertEqual(repository.updated_values[0].value_id, 42)

    def test_seed_default_sources_creates_all_starter_news_sources(self) -> None:
        """Seed добавляет все стартовые новостные источники и сохраняет их активными."""
        repository = FakeSourceRepository()

        source_ids = _seed_default_sources(
            source_repository=repository,
            source_type_id=7,
        )

        self.assertEqual(set(source_ids), {source.url for source in STARTER_SOURCES})
        self.assertIn("https://www.kommersant.ru/sitemaps/news.xml", source_ids)
        self.assertIn("https://iz.ru/sitemap.xml", source_ids)
        self.assertTrue(all(source.is_active for source in repository.sources.values()))


class FakeReferenceValue:
    """Минимальная подмена ORM-значения справочника."""

    def __init__(self, value_id: int) -> None:
        self.id = value_id


class FakeReferenceRepository:
    """Подменный репозиторий справочника для проверки seed-helper."""

    def __init__(self, existing_code: str | None = None) -> None:
        self.existing_code = existing_code
        self.created_values: list[ReferenceValueCreateDTO] = []
        self.updated_values: list[ReferenceValueUpdateDTO] = []

    def get_by_code(self, code: str) -> FakeReferenceValue | None:
        """Вернуть существующее значение только для заранее заданного кода."""
        if code == self.existing_code:
            return FakeReferenceValue(42)
        return None

    def create(self, value_data: ReferenceValueCreateDTO) -> int:
        """Запомнить создаваемое значение справочника."""
        self.created_values.append(value_data)
        return len(self.created_values)

    def update_display_fields(self, update_data: ReferenceValueUpdateDTO) -> bool:
        """Запомнить обновление человекочитаемых полей справочника."""
        self.updated_values.append(update_data)
        return True


@dataclass
class FakeSource:
    """Минимальная модель источника для проверки seed без настоящей SQLite."""

    id: int
    base_url: str
    name: str
    is_active: bool


class FakeSourceRepository:
    """Подменный репозиторий источников для unit-теста seed-логики."""

    def __init__(self) -> None:
        self.sources: dict[str, FakeSource] = {}
        self.next_id = 1

    def get_by_base_url(self, base_url: str) -> FakeSource | None:
        """Вернуть источник из памяти по URL."""
        return self.sources.get(base_url)

    def create(self, source_data) -> int:
        """Создать источник в памяти и вернуть его id."""
        source_id = self.next_id
        self.next_id += 1
        self.sources[source_data.base_url] = FakeSource(
            id=source_id,
            base_url=source_data.base_url,
            name=source_data.name,
            is_active=source_data.is_active,
        )
        return source_id

    def update_seed_data(self, update_data) -> bool:
        """Обновить источник в памяти, имитируя реальный репозиторий."""
        for source in self.sources.values():
            if source.id == update_data.source_id:
                source.name = update_data.name
                source.is_active = update_data.is_active
                return True
        return False


if __name__ == "__main__":
    unittest.main()
