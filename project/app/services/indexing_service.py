from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from app.config import Config
from app.repositories.news_repository import NewsRepository
from app.services.embedding_service import EmbeddingService


@dataclass(frozen=True)
class IndexRebuildResult:
    """Краткий итог полной пересборки FAISS-индекса."""

    articles_count: int
    vector_size: int
    index_path: Path
    id_map_path: Path


class IndexingService:
    """Сервис построения FAISS-индекса по статьям из SQLite."""

    def __init__(
        self,
        *,
        news_repository: NewsRepository | None = None,
        embedding_service: EmbeddingService | None = None,
        index_path: Path | None = None,
        id_map_path: Path | None = None,
    ) -> None:
        # Зависимости можно подменять в тестах, а в приложении используются штатные реализации.
        self.news_repository = news_repository if news_repository is not None else NewsRepository()
        self.embedding_service = embedding_service if embedding_service is not None else EmbeddingService()
        self.index_path = index_path if index_path is not None else Config.FAISS_INDEX_PATH
        self.id_map_path = id_map_path if id_map_path is not None else Config.FAISS_ID_MAP_PATH

    def rebuild_full_index(self) -> IndexRebuildResult:
        """Полностью пересобрать FAISS-индекс по всем статьям из базы."""
        articles_count = self.news_repository.count_articles()
        self._ensure_output_directories()

        if articles_count == 0:
            # При пустой базе старый индекс опасен: он будет ссылаться на уже неактуальные статьи.
            self._remove_old_index_files()
            self._write_id_map(article_ids=[], vector_size=0)
            return IndexRebuildResult(
                articles_count=0,
                vector_size=0,
                index_path=self.index_path,
                id_map_path=self.id_map_path,
            )

        articles = self.news_repository.list_articles(limit=articles_count, offset=0)
        embeddings = self._prepare_embeddings(self.embedding_service.encode_articles(articles))
        vector_size = embeddings.shape[1]

        # IndexFlatIP хранит все векторы без сжатия и ищет по inner product.
        # Так как embeddings нормализованы, inner product эквивалентен cosine similarity.
        index = faiss.IndexFlatIP(vector_size)
        index.add(embeddings)
        faiss.write_index(index, str(self.index_path))

        # FAISS хранит только позиции векторов, поэтому отдельно сохраняем связь позиции с article_id.
        self._write_id_map(
            article_ids=[article.id for article in articles],
            vector_size=vector_size,
        )

        return IndexRebuildResult(
            articles_count=articles_count,
            vector_size=vector_size,
            index_path=self.index_path,
            id_map_path=self.id_map_path,
        )

    def _prepare_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """Проверить и подготовить массив векторов к записи в FAISS."""
        if embeddings.ndim != 2:
            raise ValueError("FAISS-индекс ожидает двумерный массив embeddings.")

        # FAISS надежнее работает с float32 и непрерывным массивом памяти.
        return np.ascontiguousarray(embeddings.astype(np.float32))

    def _ensure_output_directories(self) -> None:
        """Создать каталоги для файлов индекса и карты идентификаторов."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.id_map_path.parent.mkdir(parents=True, exist_ok=True)

    def _remove_old_index_files(self) -> None:
        """Удалить старые файлы индекса, когда в базе нет статей."""
        for path in (self.index_path, self.id_map_path):
            if path.exists():
                path.unlink()

    def _write_id_map(self, *, article_ids: list[int], vector_size: int) -> None:
        """Сохранить карту соответствия позиции FAISS-вектора и article_id."""
        payload = {
            "article_ids": article_ids,
            "vector_size": vector_size,
            "index_size": len(article_ids),
        }
        self.id_map_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
