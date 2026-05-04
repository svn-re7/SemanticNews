from __future__ import annotations

import re
from urllib.parse import urlparse


# В этом модуле оставляем только легкие правила,
# которые не относятся к извлечению текста и даты.
def normalize_whitespace(text: str, *, preserve_newlines: bool = False) -> str:
    """Нормализовать пробелы и переносы строк в текстовом фрагменте."""
    # Убираем служебные подсказки и рекламные deep-link ссылки, которые попадают в текст статьи.
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\(\s*https?://[^)\s]+[^)]*\)", " ", text)
    # Markdown-разметка из Telegram и некоторых HTML-фрагментов не должна попадать в embeddings.
    text = text.replace("**", "")
    if preserve_newlines:
        # Для Telegram сохраняем границу первой строки, потому что из нее строится UI-заголовок.
        return "\n".join(
            normalized_line
            for line in text.splitlines()
            if (normalized_line := " ".join(line.split()).strip())
        )
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
