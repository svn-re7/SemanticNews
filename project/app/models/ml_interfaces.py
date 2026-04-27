from __future__ import annotations

from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    """Контракт провайдера эмбеддингов для поиска и индексации."""

    def encode_text(self, text: str) -> np.ndarray:
        """Построить один embedding-вектор для текста."""
        ...

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Построить embedding-векторы для набора текстов."""
        ...

    @property
    def vector_size(self) -> int:
        """Вернуть размерность embedding-вектора."""
        ...
