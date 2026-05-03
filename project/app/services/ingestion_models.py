from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IngestionResult:
    """Итог одного запуска сбора статей из источника."""

    source_id: int
    source_base_url: str
    source_name: str | None = None
    found: int = 0
    saved: int = 0
    skipped_duplicates: int = 0
    skipped_empty_text: int = 0
    skipped_low_quality_text: int = 0
    skipped_missing_type: int = 0
    indexed: int = 0
    stopped: bool = False


@dataclass(slots=True)
class ScheduledIngestionResult:
    """Итог планового запуска ingestion с выбранным режимом загрузки."""

    mode: str
    article_count_before: int
    results: list[IngestionResult]
    stopped: bool = False
