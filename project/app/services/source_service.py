from __future__ import annotations

from urllib.parse import urlparse

from app.models.dto import (
    SourceActiveUpdateDTO,
    SourceCreateDTO,
    SourceListItemDTO,
    SourceManagementPageDTO,
    SourceTypeOptionDTO,
)
from app.models.entities import Source
from app.repositories.source_repository import SourceRepository
from app.repositories.source_type_repository import SourceTypeRepository
from app.services.indexing_service import IndexingService
from app.services.logging_service import LoggingService


class SourceService:
    """Сервис управления источниками новостей для UI."""

    def __init__(
        self,
        *,
        source_repository: SourceRepository | None = None,
        source_type_repository: SourceTypeRepository | None = None,
        logging_service: LoggingService | None = None,
        indexing_service: IndexingService | None = None,
    ) -> None:
        # Репозитории можно подменить в тестах, а в приложении используются реальные SQLAlchemy-репозитории.
        self.source_repository = source_repository if source_repository is not None else SourceRepository()
        self.source_type_repository = (
            source_type_repository if source_type_repository is not None else SourceTypeRepository()
        )
        self.logging_service = logging_service if logging_service is not None else LoggingService()
        self.indexing_service = indexing_service if indexing_service is not None else IndexingService()

    def get_sources_page(self) -> SourceManagementPageDTO:
        """Подготовить данные для страницы управления источниками."""
        sources = self.source_repository.list_sources()
        source_types = self.source_type_repository.list_all()

        return SourceManagementPageDTO(
            sources=[self._to_source_item(source) for source in sources],
            source_types=[
                SourceTypeOptionDTO(source_type_id=source_type.id, name=source_type.name)
                for source_type in source_types
            ],
        )

    def create_source(self, *, name: str, base_url: str, source_type_id: int) -> int:
        """Создать пользовательский источник новостей."""
        normalized_base_url = base_url.strip()
        normalized_name = name.strip() or self._fallback_source_name(normalized_base_url)

        if not normalized_base_url:
            raise ValueError("URL источника не должен быть пустым.")
        if not self._is_valid_url(normalized_base_url):
            raise ValueError("URL источника должен начинаться с http:// или https://.")
        if self.source_type_repository.get_by_id(source_type_id) is None:
            raise ValueError("Выбранный тип источника не найден.")
        if self.source_repository.get_by_base_url(normalized_base_url) is not None:
            raise ValueError("Источник с таким URL уже существует.")

        source_id = self.source_repository.create(
            SourceCreateDTO(
                source_type_id=source_type_id,
                base_url=normalized_base_url,
                name=normalized_name,
                is_active=True,
            )
        )
        self.logging_service.log_source_event(source_id=source_id, event_code="source_created")
        return source_id

    def update_source_activity(self, *, source_id: int, is_active: bool) -> bool:
        """Включить или выключить источник."""
        updated = self.source_repository.update_active_state(
            SourceActiveUpdateDTO(source_id=source_id, is_active=is_active)
        )
        if updated:
            event_code = "source_enabled" if is_active else "source_disabled"
            self.logging_service.log_source_event(source_id=source_id, event_code=event_code)
        return updated

    def delete_source(self, *, source_id: int) -> bool:
        """Удалить источник вместе с его статьями и связанными поисковыми результатами."""
        deleted = self.source_repository.delete_with_articles(source_id)
        if deleted:
            # После физического удаления статей старые FAISS-векторы нельзя оставить в индексе.
            self.indexing_service.rebuild_full_index()
        return deleted

    def _to_source_item(self, source: Source) -> SourceListItemDTO:
        """Преобразовать ORM-источник в DTO для шаблона."""
        return SourceListItemDTO(
            source_id=source.id,
            name=source.name,
            base_url=source.base_url,
            source_type_name=source.source_type.name if source.source_type is not None else "Неизвестный тип",
            is_active=source.is_active,
            last_indexed_at=source.last_indexed_at,
        )

    def _fallback_source_name(self, base_url: str) -> str:
        """Собрать имя источника из домена, если пользователь не ввел имя."""
        parsed_url = urlparse(base_url)
        return parsed_url.netloc or "Новый источник"

    def _is_valid_url(self, value: str) -> bool:
        """Проверить, что URL имеет поддерживаемую HTTP-схему и домен."""
        parsed_url = urlparse(value)
        return parsed_url.scheme in {"http", "https"} and bool(parsed_url.netloc)
