from __future__ import annotations

from urllib.parse import urlparse


# В этом модуле оставляем только легкие правила,
# которые не относятся к извлечению текста и даты.
def normalize_whitespace(text: str) -> str:
    """Нормализовать пробелы и переносы строк в текстовом фрагменте."""
    return " ".join(text.split()).strip()


def detect_article_type_code(article_url: str, content_type: str | None = None) -> str:
    """Определить код типа материала по URL и Content-Type."""
    parsed_url = urlparse(article_url)
    path = parsed_url.path.lower()
    content_type = (content_type or "").lower()

    if path.endswith(".pdf") or "application/pdf" in content_type:
        return "pdf_document"
    if path.endswith(".ppt") or path.endswith(".pptx"):
        return "presentation"

    return "web_article"
