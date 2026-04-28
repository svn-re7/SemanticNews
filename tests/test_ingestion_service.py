from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.models.entities import ArticleType, Source  # noqa: E402
from app.parsers import ExtractedArticle  # noqa: E402
from app.services.ingestion_service import IngestionService  # noqa: E402


class IngestionServiceTest(unittest.TestCase):
    def test_ingest_source_appends_saved_article_ids_to_faiss_index(self) -> None:
        """После сохранения новых статей ingestion передает их id в индексатор."""
        indexing_service = FakeIndexingService()
        logging_service = FakeLoggingService()
        news_repository = FakeNewsRepository(created_ids=[101, 102])
        source = Source(
            source_type_id=1,
            base_url="https://example.test/sitemap.xml",
            name="Тестовый источник",
            is_active=True,
        )
        source.id = 5

        service = IngestionService(
            source_repository=FakeSourceRepository(source),
            news_repository=news_repository,
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=indexing_service,
            logging_service=logging_service,
            sitemap_parser=fake_sitemap_parser,
        )

        result = service.ingest_source(source, sitemap_limit=1, max_articles=2)

        self.assertEqual(result.saved, 2)
        self.assertEqual(result.indexed, 2)
        self.assertEqual(indexing_service.appended_article_ids, [101, 102])
        self.assertEqual(
            logging_service.source_events,
            [(5, "ingestion_started"), (5, "ingestion_finished")],
        )

    def test_ingest_source_logs_failed_event_when_parser_fails(self) -> None:
        """Если parser падает, ingestion пишет событие ingestion_failed и пробрасывает ошибку."""
        logging_service = FakeLoggingService()
        source = Source(
            source_type_id=1,
            base_url="https://example.test/sitemap.xml",
            name="Тестовый источник",
            is_active=True,
        )
        source.id = 5

        service = IngestionService(
            source_repository=FakeSourceRepository(source),
            news_repository=FakeNewsRepository(created_ids=[]),
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=FakeIndexingService(),
            logging_service=logging_service,
            sitemap_parser=failing_sitemap_parser,
        )

        with self.assertRaises(RuntimeError):
            service.ingest_source(source, sitemap_limit=1, max_articles=2)

        self.assertEqual(
            logging_service.source_events,
            [(5, "ingestion_started"), (5, "ingestion_failed")],
        )


class FakeSourceRepository:
    """Тестовый репозиторий источников без обращения к SQLite."""

    def __init__(self, source: Source) -> None:
        self.source = source
        self.last_indexed_source_id: int | None = None

    def get_by_id(self, source_id: int) -> Source | None:
        """Вернуть тестовый источник по id."""
        return self.source if source_id == self.source.id else None

    def list_sources(self, only_active: bool = False) -> list[Source]:
        """Вернуть единственный тестовый источник."""
        return [self.source]

    def update_last_indexed_at(self, source_id: int, indexed_at: datetime) -> bool:
        """Запомнить обновление времени последнего ingestion."""
        self.last_indexed_source_id = source_id
        return True


class FakeNewsRepository:
    """Тестовый репозиторий статей, который выдает заранее заданные id."""

    def __init__(self, created_ids: list[int]) -> None:
        self.created_ids = created_ids
        self.created_index = 0

    def get_by_direct_url(self, direct_url: str):
        """В тесте считаем, что дублей нет."""
        return None

    def create(self, article_data) -> int:
        """Вернуть id созданной статьи без записи в SQLite."""
        created_id = self.created_ids[self.created_index]
        self.created_index += 1
        return created_id


class FakeArticleTypeRepository:
    """Тестовый репозиторий типов материалов."""

    def get_by_code(self, code: str) -> ArticleType | None:
        """Вернуть web_article для любого тестового кода."""
        article_type = ArticleType(code=code, name=code)
        article_type.id = 7
        return article_type


class FakeIndexingService:
    """Тестовый индексатор, который запоминает id переданных статей."""

    def __init__(self) -> None:
        self.appended_article_ids: list[int] = []

    def append_articles_by_ids(self, article_ids: list[int]):
        """Запомнить id статей, которые ingestion отправил в FAISS."""
        self.appended_article_ids = article_ids
        return FakeIndexAppendResult(articles_count=len(article_ids))


class FakeIndexAppendResult:
    """Минимальный результат append-операции для теста ingestion."""

    def __init__(self, articles_count: int) -> None:
        self.articles_count = articles_count


class FakeLoggingService:
    """Подменный сервис логирования ingestion-событий."""

    def __init__(self) -> None:
        self.source_events: list[tuple[int, str]] = []

    def log_source_event(self, *, source_id: int, event_code: str) -> int:
        """Запомнить событие источника."""
        self.source_events.append((source_id, event_code))
        return len(self.source_events)


def fake_sitemap_parser(*args, **kwargs) -> list[ExtractedArticle]:
    """Вернуть две тестовые статьи без сетевых запросов."""
    return [
        ExtractedArticle(
            url="https://example.test/1",
            title="Первая статья",
            text="Текст первой статьи",
            published_at=datetime(2026, 1, 1),
        ),
        ExtractedArticle(
            url="https://example.test/2",
            title="Вторая статья",
            text="Текст второй статьи",
            published_at=datetime(2026, 1, 2),
        ),
    ]


def failing_sitemap_parser(*args, **kwargs) -> list[ExtractedArticle]:
    """Имитировать ошибку parser-слоя."""
    raise RuntimeError("parser failed")


if __name__ == "__main__":
    unittest.main()
