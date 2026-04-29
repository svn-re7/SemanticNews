from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

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


@dataclass(slots=True)
class IngestionResult:
    """Итог одного запуска сбора статей из источника."""

    source_id: int
    source_base_url: str
    found: int = 0
    saved: int = 0
    skipped_duplicates: int = 0
    skipped_empty_text: int = 0
    skipped_missing_type: int = 0
    indexed: int = 0


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

    def ingest_source_by_id(
        self,
        source_id: int,
        *,
        sitemap_limit: int = 5,
        max_articles: int = 10,
        batch_size: int = 100,
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
        )

    def ingest_active_sources(
        self,
        *,
        sitemap_limit: int = 5,
        max_articles_per_source: int = 10,
        batch_size: int = 100,
    ) -> list[IngestionResult]:
        """Собрать статьи из всех активных источников."""
        results: list[IngestionResult] = []

        # Репозиторий отвечает только за выборку активных источников, а сам сценарий сбора остается в сервисе.
        for source in self.source_repository.list_sources(only_active=True):
            results.append(
                self.ingest_source(
                    source,
                    sitemap_limit=sitemap_limit,
                    max_articles=max_articles_per_source,
                    batch_size=batch_size,
                )
            )

        return results

    def ingest_source(
        self,
        source: Source,
        *,
        sitemap_limit: int = 5,
        max_articles: int = 10,
        batch_size: int = 100,
    ) -> IngestionResult:
        """Выполнить полный сценарий ingestion для уже найденного источника."""
        if sitemap_limit <= 0:
            raise ValueError("sitemap_limit должен быть положительным числом")
        if max_articles <= 0:
            raise ValueError("max_articles должен быть положительным числом")
        if batch_size <= 0:
            raise ValueError("batch_size должен быть положительным числом")

        self.logging_service.log_source_event(source_id=source.id, event_code="ingestion_started")
        try:
            result = IngestionResult(
                source_id=source.id,
                source_base_url=source.base_url,
            )

            # Parser теперь отдает готовые статьи частями, чтобы длинная загрузка не ждала финала всего обхода.
            for extracted_articles in self.sitemap_batch_parser(
                source.base_url,
                sitemap_limit=sitemap_limit,
                max_articles=max_articles,
                stop_after_published_at=source.last_indexed_at,
                batch_size=batch_size,
            ):
                result.found += len(extracted_articles)
                saved_article_ids = self._save_extracted_article_batch(source, extracted_articles, result)

                if saved_article_ids:
                    # FAISS обновляем после каждой успешной пачки SQLite-записей, чтобы поиск видел статьи постепенно.
                    append_result = self.indexing_service.append_articles_by_ids(saved_article_ids)
                    result.indexed += append_result.articles_count

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
            self.logging_service.log_source_event(source_id=source.id, event_code="ingestion_failed")
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
