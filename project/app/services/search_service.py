from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np

from app.config import Config
from app.models.dto import (
    SearchQueryDTO,
    SearchResponseDTO,
    SearchResultCreateDTO,
    SearchResultItemDTO,
)
from app.models.entities import Article
from app.repositories.news_repository import NewsRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.search_result_repository import SearchResultRepository
from app.services.embedding_service import EmbeddingService


class SearchService:
    """Сервис семантического поиска по FAISS с возвратом статей из SQLite."""

    def __init__(
        self,
        *,
        embedding_service: EmbeddingService | None = None,
        news_repository: NewsRepository | None = None,
        request_repository: RequestRepository | None = None,
        search_result_repository: SearchResultRepository | None = None,
        index_path: Path | None = None,
        id_map_path: Path | None = None,
    ) -> None:
        # Подменяемые зависимости делают сервис проверяемым без Flask, SQLite и реальной ML-модели.
        self.embedding_service = embedding_service if embedding_service is not None else EmbeddingService()
        self.news_repository = news_repository if news_repository is not None else NewsRepository()
        self.request_repository = request_repository if request_repository is not None else RequestRepository()
        self.search_result_repository = (
            search_result_repository
            if search_result_repository is not None
            else SearchResultRepository()
        )
        self.index_path = index_path if index_path is not None else Config.FAISS_INDEX_PATH
        self.id_map_path = id_map_path if id_map_path is not None else Config.FAISS_ID_MAP_PATH

    def search(self, query_text: str, top_k: int = 5) -> SearchResponseDTO:
        """Выполнить семантический поиск и сохранить историю запроса."""
        normalized_query = query_text.strip()
        if not normalized_query:
            raise ValueError("Поисковый запрос не должен быть пустым.")
        if top_k <= 0:
            raise ValueError("Количество результатов поиска должно быть положительным.")

        index = self._read_index()
        article_ids = self._read_article_id_map()
        if index.ntotal != len(article_ids):
            raise ValueError("FAISS-индекс и карта article_id рассинхронизированы.")

        query_vector = self._prepare_query_vector(self.embedding_service.encode_query(normalized_query))
        distances, positions = index.search(query_vector, min(top_k, index.ntotal))
        found_pairs = self._collect_found_pairs(distances=distances[0], positions=positions[0], article_ids=article_ids)

        request_id = self.request_repository.create(
            SearchQueryDTO(
                query_text=normalized_query,
                executed_at=datetime.now(),
                limit=top_k,
            )
        )

        found_article_ids = [article_id for article_id, _ in found_pairs]
        articles_by_id = self._load_articles_by_id(found_article_ids)
        items = self._build_result_items(found_pairs=found_pairs, articles_by_id=articles_by_id)

        # Историю поиска сохраняем уже после чтения статей, чтобы в БД не попадали битые позиции индекса.
        self.search_result_repository.create_many(
            [
                SearchResultCreateDTO(
                    request_id=request_id,
                    article_id=item.article_id,
                    relevance=item.relevance,
                    position=item.position,
                )
                for item in items
            ]
        )

        return SearchResponseDTO(request_id=request_id, query_text=normalized_query, items=items)

    def _read_index(self):
        """Прочитать FAISS-индекс с диска."""
        if not self.index_path.exists():
            raise FileNotFoundError("FAISS-индекс не найден. Сначала выполните scripts/rebuild_index.py.")
        return faiss.read_index(str(self.index_path))

    def _read_article_id_map(self) -> list[int]:
        """Прочитать карту соответствия позиций FAISS и article_id."""
        if not self.id_map_path.exists():
            raise FileNotFoundError("Карта article_id не найдена. Сначала выполните scripts/rebuild_index.py.")

        payload = json.loads(self.id_map_path.read_text(encoding="utf-8"))
        article_ids = payload.get("article_ids")
        if not isinstance(article_ids, list):
            raise ValueError("Карта article_id имеет неверный формат.")
        return [int(article_id) for article_id in article_ids]

    def _prepare_query_vector(self, query_vector: np.ndarray) -> np.ndarray:
        """Подготовить embedding запроса к поиску в FAISS."""
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        if query_vector.ndim != 2 or query_vector.shape[0] != 1:
            raise ValueError("Embedding запроса должен быть одним вектором.")

        # FAISS ожидает float32 и непрерывный массив, как и при построении индекса.
        return np.ascontiguousarray(query_vector.astype(np.float32))

    def _collect_found_pairs(
        self,
        *,
        distances: np.ndarray,
        positions: np.ndarray,
        article_ids: list[int],
    ) -> list[tuple[int, float]]:
        """Перевести позиции FAISS в пары article_id и relevance."""
        found_pairs: list[tuple[int, float]] = []
        for distance, position in zip(distances, positions):
            # FAISS возвращает -1, если результата для позиции нет.
            if position < 0:
                continue
            found_pairs.append((article_ids[int(position)], float(distance)))
        return found_pairs

    def _load_articles_by_id(self, article_ids: list[int]) -> dict[int, Article]:
        """Загрузить найденные статьи из SQLite и разложить их по id."""
        articles = self.news_repository.get_by_ids(article_ids)
        return {article.id: article for article in articles}

    def _build_result_items(
        self,
        *,
        found_pairs: list[tuple[int, float]],
        articles_by_id: dict[int, Article],
    ) -> list[SearchResultItemDTO]:
        """Собрать DTO выдачи в том же порядке, который вернул FAISS."""
        items: list[SearchResultItemDTO] = []
        for position, (article_id, relevance) in enumerate(found_pairs, start=1):
            article = articles_by_id.get(article_id)
            if article is None:
                # Если статья удалена из SQLite после пересборки индекса, пропускаем битую ссылку.
                continue

            items.append(
                SearchResultItemDTO(
                    article_id=article.id,
                    title=article.title,
                    direct_url=article.direct_url,
                    source_name=article.source.name if article.source is not None else "unknown",
                    published_at=article.published_at,
                    relevance=relevance,
                    position=position,
                )
            )
        return items
