from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from app.models.entities import Source
from app.services.ingestion_models import IngestionResult


class SourceIngestionRunner:
    """Выбирает стратегию обхода источников и запускает ingestion по каждому источнику."""

    def __init__(
        self,
        *,
        ingest_source: Callable[..., IngestionResult],
        is_telegram_source: Callable[[Source], bool],
    ) -> None:
        # Runner не знает про SQLite/FAISS напрямую: он только решает, в каком порядке вызвать ingest_source.
        self.ingest_source = ingest_source
        self.is_telegram_source = is_telegram_source

    def run(
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
        """Запустить сбор активных источников подходящей стратегией."""
        if max_workers == 1 or len(sources) <= 1:
            return self._run_sequentially(
                sources,
                sitemap_limit=sitemap_limit,
                max_articles_per_source=max_articles_per_source,
                batch_size=batch_size,
                article_request_delay_seconds=article_request_delay_seconds,
                ignore_last_indexed_at=ignore_last_indexed_at,
                should_stop=should_stop,
            )
        if self._has_telegram_sources(sources):
            return self._run_mixed_parallel(
                sources,
                sitemap_limit=sitemap_limit,
                max_articles_per_source=max_articles_per_source,
                batch_size=batch_size,
                article_request_delay_seconds=article_request_delay_seconds,
                ignore_last_indexed_at=ignore_last_indexed_at,
                max_workers=max_workers,
                should_stop=should_stop,
            )

        return self._run_parallel(
            sources,
            sitemap_limit=sitemap_limit,
            max_articles_per_source=max_articles_per_source,
            batch_size=batch_size,
            article_request_delay_seconds=article_request_delay_seconds,
            ignore_last_indexed_at=ignore_last_indexed_at,
            max_workers=max_workers,
            should_stop=should_stop,
        )

    def _run_sequentially(
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
        """Собрать источники последовательно, без запуска дополнительных worker-ов."""
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

    def _run_parallel(
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
        """Собрать web-источники параллельно, сохранив порядок результатов как в списке источников."""
        ordered_results: list[IngestionResult | None] = [None] * len(sources)
        futures_by_index: dict[Future[IngestionResult], int] = {}

        # Потоки ускоряют сетевой parser-участок. Запись пачек внутри ingest_source защищена write_lock сервиса.
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

    def _run_mixed_parallel(
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
        """Собрать web-источники параллельно, а Telegram-каналы последовательно в одном worker."""
        ordered_results: list[IngestionResult | None] = [None] * len(sources)
        telegram_sources: list[tuple[int, Source]] = []
        web_sources: list[tuple[int, Source]] = []

        for source_index, source in enumerate(sources):
            if self.is_telegram_source(source):
                telegram_sources.append((source_index, source))
            else:
                web_sources.append((source_index, source))

        futures_by_index: dict[Future[IngestionResult], int] = {}
        telegram_future: Future[list[tuple[int, IngestionResult]]] | None = None
        worker_count = min(max_workers, len(web_sources) + (1 if telegram_sources else 0))

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            if telegram_sources:
                # Telethon session общая для приложения, поэтому все Telegram-каналы идут строго последовательно.
                telegram_future = executor.submit(
                    self._run_indexed_sources_sequentially,
                    telegram_sources,
                    sitemap_limit=sitemap_limit,
                    max_articles_per_source=max_articles_per_source,
                    batch_size=batch_size,
                    article_request_delay_seconds=article_request_delay_seconds,
                    ignore_last_indexed_at=ignore_last_indexed_at,
                    should_stop=should_stop,
                )

            for source_index, source in web_sources:
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

            futures = list(futures_by_index)
            if telegram_future is not None:
                futures.append(telegram_future)

            for future in as_completed(futures):
                if future.cancelled():
                    continue

                if future is telegram_future:
                    for source_index, result in future.result():
                        ordered_results[source_index] = result
                    if any(result is not None and result.stopped for result in ordered_results):
                        for pending_future in futures_by_index:
                            pending_future.cancel()
                    continue

                source_index = futures_by_index[future]
                result = future.result()
                ordered_results[source_index] = result
                if result.stopped and telegram_future is not None:
                    telegram_future.cancel()

        return [result for result in ordered_results if result is not None]

    def _run_indexed_sources_sequentially(
        self,
        indexed_sources: list[tuple[int, Source]],
        *,
        sitemap_limit: int,
        max_articles_per_source: int,
        batch_size: int,
        article_request_delay_seconds: float,
        ignore_last_indexed_at: bool,
        should_stop: Callable[[], bool] | None,
    ) -> list[tuple[int, IngestionResult]]:
        """Собрать заранее пронумерованные источники последовательно и сохранить их исходные позиции."""
        results: list[tuple[int, IngestionResult]] = []
        for source_index, source in indexed_sources:
            if should_stop is not None and should_stop():
                break

            result = self.ingest_source(
                source,
                sitemap_limit=sitemap_limit,
                max_articles=max_articles_per_source,
                batch_size=batch_size,
                article_request_delay_seconds=article_request_delay_seconds,
                ignore_last_indexed_at=ignore_last_indexed_at,
                should_stop=should_stop,
            )
            results.append((source_index, result))
            if result.stopped:
                break

        return results

    def _has_telegram_sources(self, sources: list[Source]) -> bool:
        """Проверить, есть ли среди источников Telegram-каналы."""
        return any(self.is_telegram_source(source) for source in sources)
