from __future__ import annotations

from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import Config
from app.models.ml_interfaces import EmbeddingProvider


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Провайдер эмбеддингов на базе sentence-transformers."""

    def __init__(
        self,
        *,
        model_name: str = Config.EMBEDDING_MODEL_NAME,
        adapted_model_dir: Path = Config.ADAPTED_EMBEDDING_MODEL_DIR,
    ) -> None:
        self.model_name = model_name
        self.adapted_model_dir = adapted_model_dir
        self._model: SentenceTransformer | None = None

    def encode_text(self, text: str) -> np.ndarray:
        """Построить один embedding-вектор для текста."""
        embeddings = self.encode_batch([text])
        return embeddings[0]

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Построить embedding-векторы для набора текстов."""
        if not texts:
            return np.empty((0, self.vector_size), dtype=np.float32)

        # normalize_embeddings сразу готовит векторы к cosine similarity и будущему FAISS-поиску.
        return self._get_model().encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
        ).astype(np.float32)

    @property
    def vector_size(self) -> int:
        """Вернуть размерность embedding-вектора."""
        return self._get_model().get_embedding_dimension()

    def _get_model(self) -> SentenceTransformer:
        """Загрузить модель при первом реальном обращении к эмбеддингам."""
        if self._model is None:
            # Если позже появится локально дообученная модель, приложение подхватит ее без смены сервиса.
            model_path = self.adapted_model_dir if self.adapted_model_dir.exists() else self.model_name
            self._model = SentenceTransformer(str(model_path))

        return self._model
