from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import faiss
import numpy as np

from app.config import Config
from app.models.dto import (
    SearchHistoryItemDTO,
    SearchHistoryPageDTO,
    SearchQueryDTO,
    SearchResponseDTO,
    SearchResultCreateDTO,
    SearchResultItemDTO,
)
from app.models.entities import Article, SearchResult
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
        # В обычном запуске сюда ничего не передают, и сервис сам берет реальные зависимости приложения.
        self.embedding_service = embedding_service if embedding_service is not None else EmbeddingService()
        self.news_repository = news_repository if news_repository is not None else NewsRepository()
        self.request_repository = request_repository if request_repository is not None else RequestRepository()
        self.search_result_repository = (
            search_result_repository
            if search_result_repository is not None
            else SearchResultRepository()
        )
        # Пути тоже можно подменить в тестах, чтобы не трогать рабочие файлы из project/instance.
        self.index_path = index_path if index_path is not None else Config.FAISS_INDEX_PATH
        self.id_map_path = id_map_path if id_map_path is not None else Config.FAISS_ID_MAP_PATH

    def search(self, query_text: str, top_k: int = 5) -> SearchResponseDTO:
        """Выполнить семантический поиск и сохранить историю запроса."""
        # На входе убираем случайные пробелы, чтобы в историю не попадали варианты одного запроса.
        normalized_query = query_text.strip()
        if not normalized_query:
            raise ValueError("Поисковый запрос не должен быть пустым.")
        if top_k <= 0:
            raise ValueError("Количество результатов поиска должно быть положительным.")

        # FAISS и JSON-карта читаются вместе, потому что индекс сам хранит только позиции векторов.
        index = self._read_index()
        article_ids = self._read_article_id_map()
        if index.ntotal != len(article_ids):
            raise ValueError("FAISS-индекс и карта article_id рассинхронизированы.")

        # Текстовый запрос превращаем в embedding того же типа, что и статьи при индексации.
        query_vector = self._prepare_query_vector(self.embedding_service.encode_query(normalized_query))
        # У FAISS берем кандидатов с запасом: часть ближайших статей может принадлежать выключенным источникам.
        candidate_limit = self._candidate_limit(top_k=top_k, index_size=index.ntotal)
        distances, positions = index.search(query_vector, candidate_limit)
        # FAISS возвращает позиции внутри индекса, а не id статей из SQLite.
        found_pairs = self._collect_found_pairs(distances=distances[0], positions=positions[0], article_ids=article_ids)

        # Запрос сохраняем отдельно, чтобы потом можно было показать историю поиска или анализировать выдачу.
        request_id = self.request_repository.create(
            SearchQueryDTO(
                query_text=normalized_query,
                executed_at=datetime.now(),
                limit=top_k,
            )
        )

        # После FAISS возвращаемся в SQLite: только база хранит заголовки, ссылки, даты и источник.
        found_article_ids = [article_id for article_id, _ in found_pairs]
        articles_by_id = self._load_articles_by_id(found_article_ids)
        # DTO собираем в порядке FAISS, потому что именно этот порядок отражает релевантность.
        items = self._build_result_items(
            found_pairs=found_pairs,
            articles_by_id=articles_by_id,
            limit=top_k,
        )

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

    def get_saved_results(self, request_id: int) -> SearchResponseDTO:
        """Вернуть ранее сохраненную поисковую выдачу без повторного FAISS-поиска."""
        request = self.request_repository.get_by_id(request_id)
        if request is None:
            raise ValueError(f"Поисковый запрос с id={request_id} не найден.")

        # Здесь принципиально не строим embedding и не читаем FAISS: выдача уже сохранена в SQLite.
        saved_results = self.search_result_repository.list_by_request_id(request_id)
        saved_article_ids = [saved_result.article_id for saved_result in saved_results]
        articles_by_id = self._load_articles_by_id(saved_article_ids)
        items = self._build_saved_result_items(
            saved_results=saved_results,
            articles_by_id=articles_by_id,
        )

        return SearchResponseDTO(
            request_id=request.id,
            query_text=request.query_text,
            items=items,
        )

    def get_search_history(self, *, page: int = 1, per_page: int = 20) -> SearchHistoryPageDTO:
        """Вернуть страницу истории поисковых запросов."""
        if page <= 0:
            raise ValueError("Номер страницы истории должен быть положительным.")
        if per_page <= 0:
            raise ValueError("Количество запросов на странице должно быть положительным.")

        # Offset считает, сколько более новых запросов нужно пропустить перед текущей страницей.
        offset = (page - 1) * per_page
        total_count = self.request_repository.count_requests()
        # История строится только по таблице Request: сами результаты уже открываются отдельным route по request_id.
        requests = self.request_repository.list_requests(limit=per_page, offset=offset)

        return SearchHistoryPageDTO(
            items=[
                SearchHistoryItemDTO(
                    request_id=saved_request.id,
                    query_text=saved_request.query_text,
                    executed_at=saved_request.executed_at,
                )
                for saved_request in requests
            ],
            page=page,
            per_page=per_page,
            total_count=total_count,
            has_previous=page > 1,
            has_next=page * per_page < total_count,
        )

    def _read_index(self):
        """Прочитать FAISS-индекс с диска."""
        if not self.index_path.exists():
            raise FileNotFoundError("FAISS-индекс не найден. Сначала выполните scripts/rebuild_index.py.")
        # FAISS использует свой бинарный формат, поэтому читаем индекс через библиотечную функцию.
        return faiss.read_index(str(self.index_path))

    def _read_article_id_map(self) -> list[int]:
        """Прочитать карту соответствия позиций FAISS и article_id."""
        if not self.id_map_path.exists():
            raise FileNotFoundError("Карта article_id не найдена. Сначала выполните scripts/rebuild_index.py.")

        # JSON-карта создается indexing_service и должна содержать список article_ids в порядке векторов FAISS.
        payload = json.loads(self.id_map_path.read_text(encoding="utf-8"))
        article_ids = payload.get("article_ids")
        if not isinstance(article_ids, list):
            raise ValueError("Карта article_id имеет неверный формат.")
        # Приведение к int защищает от ситуации, когда JSON был отредактирован руками и id стали строками.
        return [int(article_id) for article_id in article_ids]

    def _prepare_query_vector(self, query_vector: np.ndarray) -> np.ndarray:
        """Подготовить embedding запроса к поиску в FAISS."""
        # Один пользовательский запрос обычно приходит как одномерный вектор вида (384,).
        # FAISS ищет пачками, поэтому даже один запрос должен иметь форму (1, 384).
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        # Сервис search() рассчитан на один запрос за раз, а не на batch из нескольких запросов.
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
            # position — это индекс в JSON-списке, а значение списка — настоящий Article.id из SQLite.
            found_pairs.append((article_ids[int(position)], float(distance)))
        return found_pairs

    def _candidate_limit(self, *, top_k: int, index_size: int) -> int:
        """Посчитать, сколько кандидатов нужно запросить у FAISS до фильтрации по активности источников."""
        # После FAISS есть прикладной фильтр по Source.is_active, поэтому запрашиваем больше top_k.
        # Это повышает шанс вернуть пользователю нужное число результатов, даже если часть кандидатов выключена.
        return min(top_k * 3, index_size)

    def _load_articles_by_id(self, article_ids: list[int]) -> dict[int, Article]:
        """Загрузить найденные статьи из SQLite и разложить их по id."""
        articles = self.news_repository.get_by_ids(article_ids)
        # Словарь нужен, чтобы быстро собрать выдачу в порядке FAISS, а не в порядке ответа базы.
        return {article.id: article for article in articles}

    def _build_result_items(
        self,
        *,
        found_pairs: list[tuple[int, float]],
        articles_by_id: dict[int, Article],
        limit: int,
    ) -> list[SearchResultItemDTO]:
        """Собрать DTO выдачи в том же порядке, который вернул FAISS."""
        items: list[SearchResultItemDTO] = []
        for article_id, relevance in found_pairs:
            article = articles_by_id.get(article_id)
            if article is None:
                # Если статья удалена из SQLite после пересборки индекса, пропускаем битую ссылку.
                continue
            if not self._is_article_from_active_source(article):
                # FAISS не знает про состояние Source.is_active, поэтому бизнес-фильтр делаем здесь.
                continue

            # В DTO кладем только данные, которые нужны контроллеру, CLI или будущему шаблону поиска.
            items.append(
                SearchResultItemDTO(
                    article_id=article.id,
                    title=article.title,
                    direct_url=article.direct_url,
                    source_name=article.source.name if article.source is not None else "unknown",
                    published_at=article.published_at,
                    relevance=relevance,
                    position=len(items) + 1,
                )
            )
            if len(items) >= limit:
                break
        return items

    def _is_article_from_active_source(self, article: Article) -> bool:
        """Проверить, что статья принадлежит активному источнику."""
        # Если связь со Source не загрузилась или источник удален, такую статью безопаснее не показывать в поиске.
        return article.source is not None and article.source.is_active

    def _build_saved_result_items(
        self,
        *,
        saved_results: list[SearchResult],
        articles_by_id: dict[int, Article],
    ) -> list[SearchResultItemDTO]:
        """Собрать DTO выдачи из сохраненных SearchResult-строк."""
        items: list[SearchResultItemDTO] = []
        for saved_result in saved_results:
            article = articles_by_id.get(saved_result.article_id)
            if article is None:
                # Если статья была удалена, сохраненный результат больше нельзя показать корректно.
                continue

            items.append(
                SearchResultItemDTO(
                    article_id=article.id,
                    title=article.title,
                    direct_url=article.direct_url,
                    source_name=article.source.name if article.source is not None else "unknown",
                    published_at=article.published_at,
                    relevance=saved_result.relevance,
                    position=saved_result.position,
                )
            )
        return items
