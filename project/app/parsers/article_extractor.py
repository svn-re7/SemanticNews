from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from htmldate import find_date
from requests import Session
import trafilatura

from .exceptions import ParserContentError
from .http_client import fetch_document
from .parser_models import ExtractedArticle
from .source_adapters import detect_article_type_code, normalize_whitespace


logger = logging.getLogger(__name__)


# Это главный модуль извлечения статьи из HTML.
# 1. trafilatura отвечает за основной текст;
# 2. htmldate отвечает за дату публикации;
# 3. BeautifulSoup оставляем только для извлечения заголовка и JSON-LD fallback для даты.
def extract_article(
    article_url: str,
    *,
    session: Session | None = None,
    timeout: int = 20,
) -> ExtractedArticle:
    """Скачать страницу статьи и извлечь из нее заголовок, текст и дату публикации."""
    # Сетевой слой отделен в http_client, поэтому здесь мы работаем уже
    # с текстом документа и метаданными ответа, а не с requests.Response.
    document = fetch_document(article_url, session=session, timeout=timeout)
    html = document.text
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title_from_html(soup, document.url)
    text = _extract_text_from_html(html, soup, document.url)
    published_at = _extract_published_at_from_html(html, soup, document.url)

    if not text:
        raise ParserContentError("Не удалось извлечь основной текст статьи", url=document.url)

    return ExtractedArticle(
        url=document.url,
        title=title,
        text=text,
        published_at=published_at,
        article_type_code=detect_article_type_code(document.url, document.content_type),
    )


def _extract_title_from_html(soup: BeautifulSoup, article_url: str) -> str | None:
    """Извлечь заголовок статьи из HTML по общим и source-specific правилам."""
    # Заголовок берем напрямую из разметки страницы,
    # потому что trafilatura не всегда надежно отдает title.
    title_candidates = [
        soup.find("meta", attrs={"property": "og:title"}),
        soup.find("meta", attrs={"name": "twitter:title"}),
        soup.find("meta", attrs={"name": "title"}),
    ]

    for candidate in title_candidates:
        if candidate and candidate.get("content"):
            title = normalize_whitespace(candidate["content"])
            if title:
                return title

    h1_tag = soup.find("h1")
    if h1_tag:
        title = normalize_whitespace(h1_tag.get_text(" ", strip=True))
        if title:
            return title

    if soup.title and soup.title.string:
        title = normalize_whitespace(soup.title.string)
        if title:
            return title

    return None


def _extract_text_from_html(html: str, soup: BeautifulSoup, article_url: str) -> str:
    """Извлечь основной текст статьи с каскадом общих и source-specific стратегий."""
    # Для известных источников сначала берем точный контейнер статьи.
    # Это уменьшает риск захватить меню, похожие материалы или продублированные блоки страницы.
    source_specific_text = _extract_text_with_source_specific_rules(soup, article_url)
    if source_specific_text is not None:
        return source_specific_text

    # Если специальных правил нет или разметка изменилась, оставляем общий fallback через trafilatura.
    return _extract_text_with_trafilatura(html, article_url)


def _extract_text_with_source_specific_rules(soup: BeautifulSoup, article_url: str) -> str | None:
    """Извлечь текст по точным CSS-правилам для поддержанных новостных источников."""
    host = urlparse(article_url).netloc.lower()

    if host.endswith("kommersant.ru"):
        # У Коммерсанта полный текст лежит в общем wrapper, а отдельные абзацы размечены doc__text.
        return _extract_text_from_first_matching_selector(
            soup,
            [
                ".article_text_wrapper",
                ".doc__text",
            ],
        )

    if host.endswith("iz.ru"):
        # У Известий основное тело статьи размечено как articleBody.
        text = _extract_text_from_first_matching_selector(
            soup,
            [
                '[itemprop="articleBody"]',
                ".text-article",
                "article",
            ],
        )
        text = _remove_known_text_prefix(text, "Выделить главное Вкл Выкл")
        if _is_service_only_text(text):
            return ""
        return text

    return None


def _extract_text_from_first_matching_selector(soup: BeautifulSoup, selectors: list[str]) -> str:
    """Вернуть нормализованный текст первого непустого CSS-селектора."""
    for selector in selectors:
        node = soup.select_one(selector)
        if node is None:
            continue

        text = normalize_whitespace(node.get_text(" ", strip=True))
        if text:
            return text

    return ""


def _remove_known_text_prefix(text: str, prefix: str) -> str:
    """Убрать известный служебный префикс из текста статьи."""
    if text.startswith(prefix):
        return text.removeprefix(prefix).strip()

    return text


def _is_service_only_text(text: str) -> bool:
    """Проверить, что вместо статьи извлечены только служебные элементы страницы."""
    service_phrases = {
        "Поделиться: Читайте также",
    }
    return text in service_phrases


def _extract_text_with_trafilatura(html: str, article_url: str) -> str:
    """Извлечь основной текст статьи через trafilatura."""
    try:
        extracted_text = trafilatura.extract(
            html,
            url=article_url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception as error:
        logger.warning("Trafilatura не смогла извлечь текст статьи %s: %s", article_url, error)
        return ""

    if not extracted_text:
        return ""

    return normalize_whitespace(extracted_text)


def _extract_published_at_from_html(html: str, soup: BeautifulSoup, article_url: str) -> datetime | None:
    """Попытаться извлечь дату публикации статьи из HTML."""
    candidate_values: list[str] = []

    # Дополнительно смотрим JSON-LD, потому что там иногда есть более точное значение
    meta_selectors = [
        ("property", "article:published_time"),
        ("property", "article:modified_time"),
        ("name", "pubdate"),
        ("name", "publish_date"),
        ("name", "date"),
        ("name", "datePublished"),
        ("name", "parsely-pub-date"),
        ("itemprop", "datePublished"),
        ("itemprop", "dateModified"),
    ]

    for attr_name, attr_value in meta_selectors:
        tag = soup.find("meta", attrs={attr_name: attr_value})
        if tag and tag.get("content"):
            candidate_values.append(tag["content"])

    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        candidate_values.append(time_tag["datetime"])
    elif time_tag and time_tag.get_text(strip=True):
        candidate_values.append(time_tag.get_text(strip=True))

    candidate_values.extend(_extract_dates_from_json_ld(soup))

    # htmldate оставляем последним кандидатом: он надежно восстанавливает сам факт даты,
    # но обычно не хранит точное время публикации.
    try:
        detected_date = find_date(html, extensive_search=True)
    except Exception as error:  # pragma: no cover - сторонняя библиотека
        logger.warning("htmldate не смогла определить дату статьи %s: %s", article_url, error)
    else:
        if detected_date:
            candidate_values.append(detected_date)

    for value in candidate_values:
        parsed_datetime = _parse_datetime(value)
        if parsed_datetime is not None:
            return parsed_datetime

    return None


def _extract_dates_from_json_ld(soup: BeautifulSoup) -> list[str]:
    """Извлечь кандидаты на дату публикации из блоков JSON-LD."""
    candidate_values: list[str] = []
    for script_tag in soup.find_all("script", type="application/ld+json"):
        raw_json = script_tag.string or script_tag.get_text(strip=True)
        if not raw_json:
            continue

        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for key in ("datePublished", "dateModified", "uploadDate"):
                value = node.get(key)
                if isinstance(value, str):
                    candidate_values.append(value)

    return candidate_values


def _parse_datetime(value: str | None) -> datetime | None:
    """Преобразовать строковое представление даты в naive datetime."""
    # Даты приводим к naive datetime; для date-only значений htmldate
    # получим полночь соответствующего дня.
    if not value:
        return None

    try:
        parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed_datetime.tzinfo is not None:
        return parsed_datetime.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed_datetime
