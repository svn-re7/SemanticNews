from __future__ import annotations

import numpy as np

from app.ml.embeddings import SentenceTransformerEmbeddingProvider
from app.models.entities import Article
from app.models.ml_interfaces import EmbeddingProvider


class EmbeddingService:
    """Сервис построения эмбеддингов для статей и поисковых запросов."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        # Провайдер можно подменить в тестах или при подключении дообученной модели.
        self.provider = provider if provider is not None else SentenceTransformerEmbeddingProvider()

    def encode_article(self, article: Article) -> np.ndarray:
        """Построить embedding для одной статьи."""
        return self.provider.encode_text(self._article_text_for_embedding(article))

    def encode_articles(self, articles: list[Article]) -> np.ndarray:
        """Построить embeddings для набора статей."""
        texts = [self._article_text_for_embedding(article) for article in articles]
        return self.provider.encode_batch(texts)

    def encode_query(self, query_text: str) -> np.ndarray:
        """Построить embedding для пользовательского запроса."""
        return self.provider.encode_text(query_text.strip())

    @property
    def vector_size(self) -> int:
        """Вернуть размерность вектора текущей embedding-модели."""
        return self.provider.vector_size

    def _article_text_for_embedding(self, article: Article) -> str:
        """Собрать текст статьи в виде, пригодном для embedding-модели."""
        # Заголовок добавляем перед текстом, потому что он часто содержит краткую смысловую формулировку новости.
        return f"{article.title}\n\n{article.text}".strip()
