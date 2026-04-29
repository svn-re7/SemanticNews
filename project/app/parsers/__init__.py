"""Пакет парсеров внешних источников."""

# Наружу экспортируем только актуальный typed API парсера.
from .article_extractor import extract_article
from .parser_models import ArticleReference, ExtractedArticle, SitemapEntry
from .sitemap_parser import (
    collect_article_references,
    extract_article_references_from_sitemap,
    extract_sitemap_entries,
    iter_extracted_article_batches_from_sitemap_index,
)

__all__ = [
    "ArticleReference",
    "ExtractedArticle",
    "SitemapEntry",
    "collect_article_references",
    "extract_article",
    "extract_article_references_from_sitemap",
    "extract_sitemap_entries",
    "iter_extracted_article_batches_from_sitemap_index",
]
