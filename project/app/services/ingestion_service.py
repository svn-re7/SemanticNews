from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

from sqlalchemy.exc import IntegrityError

from app.models.dto import ArticleCreateDTO, ParsedArticleDTO
from app.models.entities import Source
from app.parsers import (
    ExtractedArticle,
    iter_extracted_article_batches_from_sitemap_index,
)
from app.repositories.article_type_repository import ArticleTypeRepository
from app.repositories.news_repository import NewsRepository
from app.repositories.source_repository import SourceRepository
from app.services.indexing_service import IndexingService
from app.services.logging_service import LoggingService


logger = logging.getLogger(__name__)


MIN_ARTICLE_TEXT_LENGTH = 300
AUTO_INGESTION_REFRESH_INTERVAL = timedelta(hours=1)


@dataclass(slots=True)
class IngestionResult:
    """Итог одного запуска сбора статей из источника."""

    source_id: int
    source_base_url: str
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


class IngestionService:
    """Сервис, который связывает парсер, DTO, репозитории и SQLite."""

    def __init__(
        self,
        *,
        source_repository: SourceRepository | None = None,
        news_repository: NewsRepository | None = None,
        article_type_repository: ArticleTypeRepository | None = None,
        indexing_service: IndexingService | None = None,
        logging_service: LoggingService | None = None,
        sitemap_batch_parser: Callable[..., Iterable[list[ExtractedArticle]]] | None = None,
        write_lock: AbstractContextManager | None = None,
    ) -> None:
        # Зависимости можно передать снаружи для тестов, а в обычном запуске сервис сам создает рабочие репозитории.
        self.source_repository = (
            source_repository if source_repository is not None else SourceRepository()
        )
        self.news_repository = news_repository if news_repository is not None else NewsRepository()
        self.article_type_repository = (
            article_type_repository
            if article_type_repository is not None
            else ArticleTypeRepository()
        )
        # Индексатор отделен от ingestion, но ingestion знает момент, когда появились новые article_id.
        self.indexing_service = (
            indexing_service if indexing_service is not None else IndexingService()
        )
        self.logging_service = logging_service if logging_service is not None else LoggingService()
        # Parser заменяемый для тестов, но контракт теперь один: статьи приходят пачками.
        self.sitemap_batch_parser = (
            sitemap_batch_parser
            if sitemap_batch_parser is not None
            else iter_extracted_article_batches_from_sitemap_index
        )
        # SQLite и FAISS/id_map остаются общими runtime-ресурсами, поэтому запись пачки сериализуем.
        self.write_lock = write_lock if write_lock is not None else Lock()

    def run_scheduled_ingestion(
        self,
        *,
        initial_article_threshold: int = 1000,
        initial_articles_per_source: int = 1000,
        initial_sitemap_limit: int = 20,
        incremental_safety_max_articles_per_source: int = 5000,
        incremental_sitemap_limit: int = 5,
        batch_size: int = 100,
        article_request_delay_seconds: float = 0.5,
        max_workers: int = 1,
        should_stop: Callable[[], bool] | None = None,
    ) -> ScheduledIngestionResult:
        """Запустить плановый сбор и выбрать initial или incremental режим по размеру БД."""
        if initial_article_threshold < 0:
            raise ValueError("initial_article_threshold не может быть отрицательным")
        if initial_articles_per_source <= 0:
            raise ValueError("initial_articles_per_source должен быть положительным числом")
        if incremental_safety_max_articles_per_source <= 0:
            raise ValueError("incremental_safety_max_articles_per_source должен быть положительным числом")

        article_count_before = self.news_repository.count_articles()
        if article_count_before < initial_article_threshold:
            # Первичный режим нужен, чтобы быстро набрать стартовый корпус для поиска и будущего ML.
            mode = "initial"
            results = self.ingest_active_sources(
                sitemap_limit=initial_sitemap_limit,
                max_articles_per_source=initial_articles_per_source,
                batch_size=batch_size,
                article_request_delay_seconds=article_request_delay_seconds,
                ignore_last_indexed_at=True,
                max_workers=max_workers,
                should_stop=should_stop,
            )
        else:
            # В incremental-режиме основной стоппер - last_indexed_at и серия старых статей.
            # Большой лимит здесь остается техническим предохранителем, а не целевым размером загрузки.
            mode = "incremental"
            results = self.ingest_active_sources(
                sitemap_limit=incremental_sitemap_limit,
                max_articles_per_source=incremental_safety_max_articles_per_source,
                batch_size=batch_size,
                article_request_delay_seconds=article_request_delay_seconds,
                max_workers=max_workers,
                should_stop=should_stop,
            )

        stopped = any(result.stopped for result in results)
        if not results and should_stop is not None and should_stop():
            stopped = True

        return ScheduledIngestionResult(
            mode=mode,
            article_count_before=article_count_before,
            results=results,
            stopped=stopped,
        )

    def should_run_auto_ingestion(
        self,
        *,
        initial_article_threshold: int = 1000,
        refresh_interval: timedelta = AUTO_INGESTION_REFRESH_INTERVAL,
        now_provider: Callable[[], datetime] | None = None,
    ) -> bool:
        """Проверить, нужно ли запускать автоматический сбор при старте приложения."""
        if initial_article_threshold < 0:
            raise ValueError("initial_article_threshold не может быть отрицательным")
        if refresh_interval.total_seconds() <= 0:
            raise ValueError("refresh_interval должен быть положительным")

        # Если стартовый корпус еще маленький, запускаем initial-режим без проверки дат источников.
        if self.news_repository.count_articles() < initial_article_threshold:
            return True

        now = now_provider() if now_provider is not None else datetime.now()
        active_sources = self.source_repository.list_sources(only_active=True)
        for source in active_sources:
            if source.last_indexed_at is None:
                return True
            if now - source.last_indexed_at >= refresh_interval:
                return True

        return False

    def ingest_source_by_id(
        self,
        source_id: int,
        *,
        sitemap_limit: int = 5,
        max_articles: int = 10,
        batch_size: int = 100,
        article_request_delay_seconds: float = 0.5,
        ignore_last_indexed_at: bool = False,
        should_stop: Callable[[], bool] | None = None,
    ) -> IngestionResult:
        """Собрать статьи из одного источника и сохранить новые записи в SQLite."""
        # Сервис принимает простой id, но дальше работает с полноценной ORM-сущностью источника.
        source = self.source_repository.get_by_id(source_id)
        if source is None:
            raise ValueError(f"Источник с id={source_id} не найден")

        return self.ingest_source(
            source,
            sitemap_limit=sitemap_limit,
            max_articles=max_articles,
            batch_size=batch_size,
            article_request_delay_seconds=article_request_delay_seconds,
            ignore_last_indexed_at=ignore_last_indexed_at,
            should_stop=should_stop,
        )

    def ingest_active_sources(
        self,
        *,
        sitemap_limit: int = 5,
        max_articles_per_source: int = 10,
        batch_size: int = 100,
        article_request_delay_seconds: float = 0.5,
        ignore_last_indexed_at: bool = False,
        max_workers: int = 1,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[IngestionResult]:
        """Собрать статьи из всех активных источников."""
        if max_workers <= 0:
            raise ValueError("max_workers должен быть положительным числом")

        # Репозиторий отвечает только за выборку активных источников, а сам сценарий сбора остается в сервисе.
        sources = self.source_repository.list_sources(only_active=True)
        if max_workers == 1 or len(sources) <= 1:
            return self._ingest_active_sources_sequentially(
                sources,
                sitemap_limit=sitemap_limit,
                max_articles_per_source=max_articles_per_source,
                batch_size=batch_size,
                article_request_delay_seconds=article_request_delay_seconds,
                ignore_last_indexed_at=ignore_last_indexed_at,
                should_stop=should_stop,
            )

        return self._ingest_active_sources_in_parallel(
            sources,
            sitemap_limit=sitemap_limit,
            max_articles_per_source=max_articles_per_source,
            batch_size=batch_size,
            article_request_delay_seconds=article_request_delay_seconds,
            ignore_last_indexed_at=ignore_last_indexed_at,
            max_workers=max_workers,
            should_stop=should_stop,
        )

    def _ingest_active_sources_sequentially(
        self,
        sources: list[Source],
        *,
        sitemap_limit: int,
        max_articles_per_source: int,
        batch_size: int,
        article_request_delay_seconds: float,
        ignore_last_indexed_at: bool,
        should_stop: Callable[[], bool] | None,
    ) -> list[IngestionResult]:
        """Собрать источники по старому последовательному сценарию."""
        results: list[IngestionResult] = []
        for source in sources:
            if should_stop is not None and should_stop():
                break

            results.append(
                self.ingest_source(
                    source,
                    sitemap_limit=sitemap_limit,
                    max_articles=max_articles_per_source,
                    batch_size=batch_size,
                    article_request_delay_seconds=article_request_delay_seconds,
                    ignore_last_indexed_at=ignore_last_indexed_at,
                    should_stop=should_stop,
                )
            )
            if results[-1].stopped:
                break

        return results

    def _ingest_active_sources_in_parallel(
        self,
        sources: list[Source],
        *,
        sitemap_limit: int,
        max_articles_per_source: int,
        batch_size: int,
        article_request_delay_seconds: float,
        ignore_last_indexed_at: bool,
        max_workers: int,
        should_stop: Callable[[], bool] | None,
    ) -> list[IngestionResult]:
        """Собрать разные источники параллельно, сохранив порядок результатов как в списке источников."""
        ordered_results: list[IngestionResult | None] = [None] * len(sources)
        futures_by_index: dict[Future[IngestionResult], int] = {}

        # Потоки ускоряют сетевой parser-участок. Запись пачек внутри ingest_source защищена write_lock.
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for source_index, source in enumerate(sources):
                if should_stop is not None and should_stop():
                    break

                future = executor.submit(
                    self.ingest_source,
                    source,
                    sitemap_limit=sitemap_limit,
                    max_articles=max_articles_per_source,
                    batch_size=batch_size,
                    article_request_delay_seconds=article_request_delay_seconds,
                    ignore_last_indexed_at=ignore_last_indexed_at,
                    should_stop=should_stop,
                )
                futures_by_index[future] = source_index

            for future in as_completed(futures_by_index):
                if future.cancelled():
                    continue

                source_index = futures_by_index[future]
                result = future.result()
                ordered_results[source_index] = result
                if result.stopped:
                    # Уже запущенные источники завершатся мягко сами, а не стартовавшие задачи отменяем.
                    for pending_future in futures_by_index:
                        if pending_future is not future:
                            pending_future.cancel()

        return [result for result in ordered_results if result is not None]

    def ingest_source(
        self,
        source: Source,
        *,
        sitemap_limit: int = 5,
        max_articles: int = 10,
        batch_size: int = 100,
        article_request_delay_seconds: float = 0.5,
        ignore_last_indexed_at: bool = False,
        should_stop: Callable[[], bool] | None = None,
    ) -> IngestionResult:
        """Выполнить полный сценарий ingestion для уже найденного источника."""
        if sitemap_limit <= 0:
            raise ValueError("sitemap_limit должен быть положительным числом")
        if max_articles <= 0:
            raise ValueError("max_articles должен быть положительным числом")
        if batch_size <= 0:
            raise ValueError("batch_size должен быть положительным числом")
        if article_request_delay_seconds < 0:
            raise ValueError("article_request_delay_seconds не может быть отрицательным")

        self._log_source_event(source.id, "ingestion_started")
        try:
            result = IngestionResult(
                source_id=source.id,
                source_base_url=source.base_url,
            )

            # Parser теперь отдает готовые статьи частями, чтобы длинная загрузка не ждала финала всего обхода.
            stop_after_published_at = None if ignore_last_indexed_at else source.last_indexed_at
            for extracted_articles in self.sitemap_batch_parser(
                source.base_url,
                sitemap_limit=sitemap_limit,
                max_articles=max_articles,
                stop_after_published_at=stop_after_published_at,
                batch_size=batch_size,
                article_request_delay_seconds=article_request_delay_seconds,
            ):
                result.found += len(extracted_articles)
                with self.write_lock:
                    saved_article_ids = self._save_extracted_article_batch(source, extracted_articles, result)

                    if saved_article_ids:
                        # FAISS обновляем после каждой успешной пачки SQLite-записей, чтобы поиск видел статьи постепенно.
                        append_result = self.indexing_service.append_articles_by_ids(saved_article_ids)
                        result.indexed += append_result.articles_count

                    # При мягкой остановке финальный блок ниже не выполнится, поэтому фиксируем
                    # безопасный checkpoint после каждой уже обработанной пачки.
                    self._update_last_indexed_at_after_batch(source, extracted_articles)

                if should_stop is not None and should_stop():
                    # Остановка мягкая: уже сохраненная пачка остается в SQLite/FAISS, следующую пачку не начинаем.
                    result.stopped = True
                    break

            if result.stopped:
                logger.info("Ingestion source_id=%s остановлен пользователем после текущей пачки.", source.id)
                return result

            with self.write_lock:
                # Фиксируем время попытки ingestion для источника, чтобы потом можно было показывать его в UI.
                self.source_repository.update_last_indexed_at(source.id, datetime.now())
                self.logging_service.log_source_event(source_id=source.id, event_code="ingestion_finished")
            logger.info(
                "Ingestion source_id=%s: найдено=%s, сохранено=%s, проиндексировано=%s, дубли=%s, без текста=%s",
                result.source_id,
                result.found,
                result.saved,
                result.indexed,
                result.skipped_duplicates,
                result.skipped_empty_text,
            )
            return result
        except Exception:
            self._log_source_event(source.id, "ingestion_failed")
            raise

    def _to_parsed_article(
        self,
        source_base_url: str,
        extracted_article: ExtractedArticle,
    ) -> ParsedArticleDTO:
        """Преобразовать результат parser-слоя в DTO для ingestion-сервиса."""
        # DTO отделяет внешний результат парсера от данных, которые сервис готовит к сохранению.
        return ParsedArticleDTO(
            source_base_url=source_base_url,
            direct_url=extracted_article.url.strip(),
            title=(extracted_article.title or "").strip(),
            text=extracted_article.text.strip(),
            published_at=extracted_article.published_at,
            article_type_code=extracted_article.article_type_code,
        )

    def _save_parsed_article(
        self,
        source: Source,
        parsed_article: ParsedArticleDTO,
        result: IngestionResult,
    ) -> int | None:
        """Проверить статью и сохранить ее, если она проходит правила ingestion."""
        # По архитектурному решению статьи без текста не попадают в базу.
        if not parsed_article.text:
            result.skipped_empty_text += 1
            return None

        # Короткие фрагменты почти всегда оказываются служебными блоками страницы, а не полноценной статьей.
        if not self._has_enough_article_text(parsed_article.text):
            result.skipped_low_quality_text += 1
            return None

        # Дубли отсекаются на уровне сервиса до записи, потому что это бизнес-правило ingestion.
        if self.news_repository.get_by_direct_url(parsed_article.direct_url) is not None:
            result.skipped_duplicates += 1
            return None

        # В БД хранится ссылка на справочник ArticleType, поэтому код типа нужно превратить в id.
        article_type_id = self._resolve_article_type_id(parsed_article.article_type_code)
        if article_type_id is None:
            result.skipped_missing_type += 1
            return None

        # Если дата публикации не найдена парсером, подставляем текущее время 
        now = datetime.now()
        article_data = ArticleCreateDTO(
            source_id=source.id,
            article_type_id=article_type_id,
            direct_url=parsed_article.direct_url,
            title=parsed_article.title or "Без заголовка",
            text=parsed_article.text,
            published_at=parsed_article.published_at or now,
            added_at=now,
        )

        try:
            # Репозиторий создает ORM-объект и выполняет запись, сервис получает только id/ошибку операции.
            article_id = self.news_repository.create(article_data)
        except IntegrityError:
            # Защита от гонки или старого дубля: если UNIQUE по URL сработал в БД, считаем статью дублем.
            result.skipped_duplicates += 1
            logger.info("Статья уже есть в БД: %s", parsed_article.direct_url)
            return None

        result.saved += 1
        return article_id

    def _has_enough_article_text(self, text: str) -> bool:
        """Проверить, что текст похож на полноценную статью, а не на короткий служебный фрагмент."""
        return len(text.strip()) >= MIN_ARTICLE_TEXT_LENGTH

    def _resolve_article_type_id(self, article_type_code: str) -> int | None:
        """Найти идентификатор типа материала по коду с безопасным fallback на other."""
        # Сначала пробуем использовать точный тип, который определил parser/adapter.
        article_type = self.article_type_repository.get_by_code(article_type_code)
        if article_type is not None:
            return article_type.id

        # Если конкретный тип не найден, используем согласованное безопасное значение other.
        fallback_article_type = self.article_type_repository.get_by_code("other")
        if fallback_article_type is None:
            logger.warning("Не найден тип материала для кода %s", article_type_code)
            return None

        return fallback_article_type.id

    def _save_extracted_article_batch(
        self,
        source: Source,
        extracted_articles: list[ExtractedArticle],
        result: IngestionResult,
    ) -> list[int]:
        """Сохранить пачку parser-моделей в SQLite и вернуть id новых статей."""
        saved_article_ids: list[int] = []

        # Каждая статья проходит одинаковый путь: parser model -> DTO -> проверка правил -> repository -> SQLite.
        for extracted_article in extracted_articles:
            parsed_article = self._to_parsed_article(source.base_url, extracted_article)
            saved_article_id = self._save_parsed_article(source, parsed_article, result)
            if saved_article_id is not None:
                saved_article_ids.append(saved_article_id)

        return saved_article_ids

    def _update_last_indexed_at_after_batch(
        self,
        source: Source,
        extracted_articles: list[ExtractedArticle],
    ) -> None:
        """Обновить checkpoint источника после пачки, которая уже прошла SQLite/FAISS."""
        # Для частичного сбора нельзя ставить datetime.now(): это скажет parser-у,
        # что источник полностью проверен до текущего момента, хотя пользователь мог нажать stop.
        processed_dates = [
            extracted_article.published_at
            for extracted_article in extracted_articles
            if extracted_article.published_at is not None
        ]
        if not processed_dates:
            return

        # Самая старая дата в обработанной пачке означает: до этой точки мы уже дошли безопасно.
        batch_checkpoint = min(processed_dates)
        if source.last_indexed_at is not None and source.last_indexed_at >= batch_checkpoint:
            return

        self.source_repository.update_last_indexed_at(source.id, batch_checkpoint)
        source.last_indexed_at = batch_checkpoint

    def _log_source_event(self, source_id: int, event_code: str) -> None:
        """Записать SourceLog под общим ingestion-lock, чтобы потоки не писали в SQLite одновременно."""
        with self.write_lock:
            self.logging_service.log_source_event(source_id=source_id, event_code=event_code)
