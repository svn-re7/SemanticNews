from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from contextlib import nullcontext
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from requests import Session

from .article_extractor import extract_article
from .exceptions import ParserError, ParserXmlError
from .http_client import create_retry_session, fetch_document
from .parser_models import ArticleReference, ExtractedArticle, SitemapEntry


logger = logging.getLogger(__name__)


# Этот модуль отвечает только за pipeline вокруг sitemap:
# индекс sitemap -> ссылки на статьи -> извлечение HTML-контента статей.
def extract_sitemap_entries(
    sitemap_index_url: str,
    *,
    limit: int = 10,
    session: Session | None = None,
) -> list[SitemapEntry]:
    """Извлечь записи вложенных sitemap-файлов из sitemap-индекса."""
    with _session_context(session) as active_session:
        # На этом шаге только загружаем и разбираем XML индекса,
        # без попытки парсить сами статьи.
        document = fetch_document(sitemap_index_url, session=active_session)
        root = _parse_xml(document.text, sitemap_index_url)

        sitemap_entries: list[SitemapEntry] = []
        for url_value in _find_tag_values(root, "loc"):
            sitemap_entries.append(
                SitemapEntry(
                    url=url_value,
                    date_start=_extract_date_from_query(url_value, "date_start"),
                    date_end=_extract_date_from_query(url_value, "date_end"),
                )
            )
            if len(sitemap_entries) >= limit:
                break

        return sitemap_entries


def extract_article_references_from_sitemap(
    sitemap_url: str,
    *,
    session: Session | None = None,
) -> list[ArticleReference]:
    """Извлечь ссылки на статьи и lastmod из конкретного sitemap-файла."""
    with _session_context(session) as active_session:
        # Здесь уже работаем с вложенным sitemap и строим список ссылок на статьи,
        # который затем будет использоваться слоем извлечения HTML.
        document = fetch_document(sitemap_url, session=active_session)
        root = _parse_xml(document.text, sitemap_url)

        article_references: list[ArticleReference] = []
        for url_element in _find_elements(root, "url"):
            article_url = _find_first_child_text(url_element, "loc")
            if not article_url:
                continue

            lastmod = _parse_sitemap_datetime(_find_first_child_text(url_element, "lastmod"))
            article_references.append(ArticleReference(url=article_url, lastmod=lastmod))

        return article_references


def collect_article_references(
    sitemap_entries: list[SitemapEntry],
    *,
    max_articles: int = 100,
    session: Session | None = None,
) -> list[ArticleReference]:
    """Собрать ссылки на статьи из набора sitemap-файлов."""
    with _session_context(session) as active_session:
        # На этом этапе объединяем ссылки из нескольких sitemap-файлов,
        # но еще не ходим в HTML конкретных статей.
        article_references: list[ArticleReference] = []
        for sitemap_entry in sitemap_entries:
            article_references.extend(
                extract_article_references_from_sitemap(sitemap_entry.url, session=active_session)
            )
            if len(article_references) >= max_articles:
                break

        return article_references[:max_articles]


def collect_extracted_articles_from_sitemap_index(
    sitemap_index_url: str,
    *,
    sitemap_limit: int = 5,
    max_articles: int = 10,
    session: Session | None = None,
) -> list[ExtractedArticle]:
    """Собрать статьи, начиная с sitemap-индекса и заканчивая извлечением HTML-контента."""
    with _session_context(session) as active_session:
        # Это основной end-to-end сценарий парсинга:
        # индекс -> sitemap -> ссылки -> реальные статьи.
        sitemap_entries = extract_sitemap_entries(
            sitemap_index_url,
            limit=sitemap_limit,
            session=active_session,
        )
        if not sitemap_entries:
            return []

        article_references = collect_article_references(
            sitemap_entries,
            max_articles=max_articles,
            session=active_session,
        )
        if not article_references:
            return []

        extracted_articles: list[ExtractedArticle] = []
        for article_reference in article_references:
            try:
                article = extract_article(article_reference.url, session=active_session)
            except ParserError as error:
                logger.warning("Не удалось извлечь статью %s: %s", article_reference.url, error)
                continue

            if article.published_at is None:
                article.published_at = article_reference.lastmod

            extracted_articles.append(article)
            if len(extracted_articles) >= max_articles:
                break

        return extracted_articles


def _parse_xml(xml_text: str, source_url: str) -> ET.Element:
    """Разобрать XML sitemap-документа и при ошибке выбросить понятное исключение."""
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ParserXmlError(f"Не удалось разобрать XML sitemap: {error}", url=source_url) from error


def _session_context(session: Session | None):
    """Вернуть контекст общего или локального HTTP-сеанса."""
    # Если сессия передана снаружи, переиспользуем ее.
    # Иначе создаем локальную retry-session на время текущего сценария.
    if session is not None:
        return nullcontext(session)

    created_session = create_retry_session()
    return created_session


def _find_elements(root: ET.Element, tag_name: str) -> list[ET.Element]:
    """Найти элементы по локальному имени XML-тега вне зависимости от namespace."""
    return [element for element in root.iter() if _local_tag_name(element.tag) == tag_name]


def _find_tag_values(root: ET.Element, tag_name: str) -> list[str]:
    """Найти текстовые значения тегов по локальному имени."""
    values: list[str] = []
    for element in _find_elements(root, tag_name):
        if element.text:
            values.append(element.text.strip())
    return values


def _find_first_child_text(element: ET.Element, tag_name: str) -> str | None:
    """Найти текст первого дочернего тега по локальному имени."""
    for child in element:
        if _local_tag_name(child.tag) == tag_name and child.text:
            return child.text.strip()
    return None


def _local_tag_name(tag_name: str) -> str:
    """Вернуть локальное имя XML-тега без namespace."""
    if "}" in tag_name:
        return tag_name.rsplit("}", 1)[1]
    return tag_name


def _extract_date_from_query(url: str, param_name: str) -> datetime | None:
    """Извлечь дату из query-параметра sitemap URL, если она есть."""
    parsed_url = urlparse(url)
    value = parse_qs(parsed_url.query).get(param_name, [None])[0]
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None


def _parse_sitemap_datetime(value: str | None) -> datetime | None:
    """Преобразовать lastmod из sitemap в datetime с поддержкой нескольких форматов."""
    # Сайты присылают lastmod в немного разных форматах,
    # поэтому поддерживаем несколько типовых вариантов.
    if not value:
        return None

    candidates = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
    ]

    normalized_value = value.replace("Z", "+0000") if value.endswith("Z") else value
    normalized_value = normalized_value.replace(":", "", 1) if normalized_value.endswith(("+0000", "+0300", "-0300")) else normalized_value

    for pattern in candidates:
        try:
            parsed_datetime = datetime.strptime(normalized_value, pattern)
        except ValueError:
            continue

        if parsed_datetime.tzinfo is not None:
            return parsed_datetime.astimezone(timezone.utc).replace(tzinfo=None)

        return parsed_datetime

    try:
        parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed_datetime.tzinfo is not None:
        return parsed_datetime.astimezone(timezone.utc).replace(tzinfo=None)

    return parsed_datetime
