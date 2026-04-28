from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.models.dto import ReferenceValueCreateDTO, ReferenceValueUpdateDTO  # noqa: E402
from scripts.seed_reference_data import EVENT_TYPES, _seed_reference_values  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
