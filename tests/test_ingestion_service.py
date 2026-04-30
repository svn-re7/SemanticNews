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
            sitemap_batch_parser=fake_sitemap_batch_parser,
        )

        result = service.ingest_source(source, sitemap_limit=1, max_articles=2)

        self.assertEqual(result.saved, 2)
        self.assertEqual(result.indexed, 2)
        self.assertEqual(indexing_service.appended_article_ids, [101, 102])
        self.assertEqual(indexing_service.append_calls, [[101, 102]])
        self.assertEqual(
            logging_service.source_events,
            [(5, "ingestion_started"), (5, "ingestion_finished")],
        )

    def test_ingest_source_indexes_articles_by_batches(self) -> None:
        """Большая загрузка сохраняет и индексирует статьи пачками, а не одним финальным блоком."""
        indexing_service = FakeIndexingService()
        source = Source(
            source_type_id=1,
            base_url="https://example.test/sitemap.xml",
            name="Тестовый источник",
            is_active=True,
        )
        source.id = 5

        service = IngestionService(
            source_repository=FakeSourceRepository(source),
            news_repository=FakeNewsRepository(created_ids=[101, 102, 103]),
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=indexing_service,
            logging_service=FakeLoggingService(),
            sitemap_batch_parser=fake_sitemap_batch_parser,
        )

        result = service.ingest_source(source, sitemap_limit=1, max_articles=3, batch_size=2)

        self.assertEqual(result.found, 3)
        self.assertEqual(result.saved, 3)
        self.assertEqual(result.indexed, 3)
        self.assertEqual(indexing_service.append_calls, [[101, 102], [103]])

    def test_ingest_source_skips_too_short_article_text(self) -> None:
        """Ingestion не сохраняет статьи, у которых вместо полноценного текста короткий фрагмент."""
        indexing_service = FakeIndexingService()
        source = build_fake_source()

        service = IngestionService(
            source_repository=FakeSourceRepository(source),
            news_repository=FakeNewsRepository(created_ids=[101]),
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=indexing_service,
            logging_service=FakeLoggingService(),
            sitemap_batch_parser=fake_short_article_batch_parser,
        )

        result = service.ingest_source(source, sitemap_limit=1, max_articles=1)

        self.assertEqual(result.found, 1)
        self.assertEqual(result.saved, 0)
        self.assertEqual(result.skipped_low_quality_text, 1)
        self.assertEqual(indexing_service.append_calls, [])

    def test_ingest_source_stops_between_batches(self) -> None:
        """Остановка между пачками сохраняет уже обработанную пачку и не начинает следующую."""
        indexing_service = FakeIndexingService()
        source_repository = FakeSourceRepository(build_fake_source())
        service = IngestionService(
            source_repository=source_repository,
            news_repository=FakeNewsRepository(created_ids=[101, 102, 103]),
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=indexing_service,
            logging_service=FakeLoggingService(),
            sitemap_batch_parser=fake_sitemap_batch_parser,
        )

        result = service.ingest_source(
            source_repository.source,
            max_articles=3,
            batch_size=2,
            should_stop=lambda: True,
        )

        self.assertTrue(result.stopped)
        self.assertEqual(result.saved, 2)
        self.assertEqual(indexing_service.append_calls, [[101, 102]])
        self.assertIsNone(source_repository.last_indexed_source_id)

    def test_ingest_source_passes_article_delay_to_batch_parser(self) -> None:
        """Ingestion передает parser-слою настройку паузы между HTML-запросами."""
        parser_kwargs: dict = {}
        source = Source(
            source_type_id=1,
            base_url="https://example.test/sitemap.xml",
            name="Тестовый источник",
            is_active=True,
        )
        source.id = 5

        def fake_parser(*args, **kwargs):
            """Запомнить параметры parser-вызова и вернуть пустой результат."""
            parser_kwargs.update(kwargs)
            return iter([])

        service = IngestionService(
            source_repository=FakeSourceRepository(source),
            news_repository=FakeNewsRepository(created_ids=[]),
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=FakeIndexingService(),
            logging_service=FakeLoggingService(),
            sitemap_batch_parser=fake_parser,
        )

        service.ingest_source(source, article_request_delay_seconds=1.25)

        self.assertEqual(parser_kwargs["article_request_delay_seconds"], 1.25)

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
            sitemap_batch_parser=failing_sitemap_batch_parser,
        )

        with self.assertRaises(RuntimeError):
            service.ingest_source(source, sitemap_limit=1, max_articles=2)

        self.assertEqual(
            logging_service.source_events,
            [(5, "ingestion_started"), (5, "ingestion_failed")],
        )

    def test_run_scheduled_ingestion_uses_initial_mode_when_database_is_small(self) -> None:
        """Если в БД меньше 1000 статей, плановый сбор запускает тяжелую первичную загрузку."""
        parser_kwargs: dict = {}
        source = build_fake_source()

        service = IngestionService(
            source_repository=FakeSourceRepository(source),
            news_repository=FakeNewsRepository(created_ids=[], articles_count=250),
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=FakeIndexingService(),
            logging_service=FakeLoggingService(),
            sitemap_batch_parser=build_empty_recording_parser(parser_kwargs),
        )

        result = service.run_scheduled_ingestion()

        self.assertEqual(result.mode, "initial")
        self.assertEqual(result.article_count_before, 250)
        self.assertEqual(parser_kwargs["max_articles"], 1000)
        self.assertEqual(parser_kwargs["batch_size"], 100)
        self.assertIsNone(parser_kwargs["stop_after_published_at"])

    def test_run_scheduled_ingestion_uses_incremental_mode_when_database_has_enough_articles(self) -> None:
        """Если первичный корпус уже собран, плановый сбор запускает инкрементальное обновление."""
        parser_kwargs: dict = {}
        source = build_fake_source()

        service = IngestionService(
            source_repository=FakeSourceRepository(source),
            news_repository=FakeNewsRepository(created_ids=[], articles_count=1000),
            article_type_repository=FakeArticleTypeRepository(),
            indexing_service=FakeIndexingService(),
            logging_service=FakeLoggingService(),
            sitemap_batch_parser=build_empty_recording_parser(parser_kwargs),
        )

        result = service.run_scheduled_ingestion()

        self.assertEqual(result.mode, "incremental")
        self.assertEqual(result.article_count_before, 1000)
        self.assertEqual(parser_kwargs["max_articles"], 5000)
        self.assertEqual(parser_kwargs["batch_size"], 100)
        self.assertEqual(parser_kwargs["stop_after_published_at"], source.last_indexed_at)


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

    def __init__(self, created_ids: list[int], articles_count: int = 0) -> None:
        self.created_ids = created_ids
        self.created_index = 0
        self.articles_count = articles_count

    def get_by_direct_url(self, direct_url: str):
        """В тесте считаем, что дублей нет."""
        return None

    def create(self, article_data) -> int:
        """Вернуть id созданной статьи без записи в SQLite."""
        created_id = self.created_ids[self.created_index]
        self.created_index += 1
        return created_id

    def count_articles(self) -> int:
        """Вернуть тестовое количество статей в БД."""
        return self.articles_count


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
        self.append_calls: list[list[int]] = []

    def append_articles_by_ids(self, article_ids: list[int]):
        """Запомнить id статей, которые ingestion отправил в FAISS."""
        self.appended_article_ids = article_ids
        self.append_calls.append(article_ids)
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


def fake_sitemap_batch_parser(*args, **kwargs):
    """Вернуть тестовые статьи двумя пачками без сетевых запросов."""
    max_articles = kwargs.get("max_articles", 3)
    text = " ".join(["Содержательный текст тестовой статьи."] * 20)
    articles = [
        ExtractedArticle(
            url="https://example.test/1",
            title="Первая статья",
            text=text,
            published_at=datetime(2026, 1, 1),
        ),
        ExtractedArticle(
            url="https://example.test/2",
            title="Вторая статья",
            text=text,
            published_at=datetime(2026, 1, 2),
        ),
        ExtractedArticle(
            url="https://example.test/3",
            title="Третья статья",
            text=text,
            published_at=datetime(2026, 1, 3),
        ),
    ]

    selected_articles = articles[:max_articles]
    yield selected_articles[:2]
    if len(selected_articles) > 2:
        yield selected_articles[2:]


def fake_short_article_batch_parser(*args, **kwargs):
    """Вернуть статью с коротким текстом, похожим на служебный фрагмент страницы."""
    yield [
        ExtractedArticle(
            url="https://example.test/short",
            title="Короткая статья",
            text="Поделиться: Читайте также",
            published_at=datetime(2026, 1, 1),
        )
    ]


def failing_sitemap_batch_parser(*args, **kwargs):
    """Имитировать ошибку parser-слоя."""
    raise RuntimeError("parser failed")


def build_fake_source() -> Source:
    """Собрать тестовый источник для сценариев ingestion."""
    source = Source(
        source_type_id=1,
        base_url="https://example.test/sitemap.xml",
        name="Тестовый источник",
        is_active=True,
    )
    source.id = 5
    source.last_indexed_at = datetime(2026, 4, 29, 22, 49, 20)
    return source


def build_empty_recording_parser(parser_kwargs: dict):
    """Создать parser-заглушку, которая запоминает параметры и не возвращает статей."""

    def fake_parser(*args, **kwargs):
        """Запомнить параметры parser-вызова и вернуть пустой iterator пачек."""
        parser_kwargs.update(kwargs)
        return iter([])

    return fake_parser


if __name__ == "__main__":
    unittest.main()
