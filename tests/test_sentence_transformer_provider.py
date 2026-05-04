from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.ml.embeddings import sentence_transformer_provider  # noqa: E402
from app.ml.embeddings.sentence_transformer_provider import (  # noqa: E402
    SentenceTransformerEmbeddingProvider,
)


class SentenceTransformerEmbeddingProviderTest(unittest.TestCase):
    def test_encode_batch_works_without_console_streams(self) -> None:
        """Провайдер embeddings работает, даже если приложение запущено без stdout/stderr."""
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        original_model_class = sentence_transformer_provider.SentenceTransformer

        try:
            sentence_transformer_provider.SentenceTransformer = FakeSentenceTransformer
            sys.stdout = None
            sys.stderr = None

            provider = SentenceTransformerEmbeddingProvider(model_name="fake-model")
            embeddings = provider.encode_batch(["Текст новости"])
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            sentence_transformer_provider.SentenceTransformer = original_model_class

        self.assertEqual(embeddings.dtype, np.float32)
        self.assertEqual(embeddings.shape, (1, 3))


class FakeSentenceTransformer:
    """Подменная модель, которая воспроизводит обращение библиотеки к stdout.isatty()."""

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        sys.stdout.isatty()

    def encode(
        self,
        texts: list[str],
        *,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
    ) -> np.ndarray:
        """Вернуть один тестовый вектор после проверки stdout."""
        sys.stdout.isatty()
        return np.array([[1.0, 0.0, 0.0]], dtype=np.float32)

    def get_embedding_dimension(self) -> int:
        """Вернуть размерность тестового embedding-вектора."""
        sys.stdout.isatty()
        return 3


if __name__ == "__main__":
    unittest.main()
