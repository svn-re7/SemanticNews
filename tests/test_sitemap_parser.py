from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.parsers.parser_models import ArticleReference, ExtractedArticle, SitemapEntry  # noqa: E402
from app.parsers.sitemap_parser import (  # noqa: E402
    collect_extracted_articles_from_sitemap_index,
    iter_extracted_article_batches_from_sitemap_index,
)


class SitemapParserTest(unittest.TestCase):
    def test_collect_extracted_articles_stops_after_consecutive_old_references(self) -> None:
        """Sitemap-парсер останавливается, когда дальше идут старые статьи."""
        references = [
            ArticleReference(url="https://example.test/new", lastmod=datetime(2026, 1, 3)),
            ArticleReference(url="https://example.test/old-1", lastmod=datetime(2026, 1, 1)),
            ArticleReference(url="https://example.test/old-2", lastmod=datetime(2026, 1, 1)),
            ArticleReference(url="https://example.test/should-not-read", lastmod=datetime(2026, 1, 4)),
        ]

        with (
            patch(
                "app.parsers.sitemap_parser.extract_sitemap_entries",
                return_value=[SitemapEntry(url="https://example.test/sitemap.xml")],
            ),
            patch("app.parsers.sitemap_parser.collect_article_references", return_value=references),
            patch("app.parsers.sitemap_parser.extract_article", side_effect=fake_extract_article) as extract_mock,
        ):
            articles = collect_extracted_articles_from_sitemap_index(
                "https://example.test/sitemap-index.xml",
                stop_after_published_at=datetime(2026, 1, 2),
                stop_after_old_articles=2,
            )

        self.assertEqual([article.url for article in articles], ["https://example.test/new"])
        self.assertEqual(extract_mock.call_count, 1)

    def test_iter_extracted_article_batches_yields_configured_batch_size(self) -> None:
        """Batch-API sitemap-парсера отдает статьи частями во время обхода ссылок."""
        references = [
            ArticleReference(url="https://example.test/1", lastmod=datetime(2026, 1, 1)),
            ArticleReference(url="https://example.test/2", lastmod=datetime(2026, 1, 2)),
            ArticleReference(url="https://example.test/3", lastmod=datetime(2026, 1, 3)),
        ]

        with (
            patch(
                "app.parsers.sitemap_parser.extract_sitemap_entries",
                return_value=[SitemapEntry(url="https://example.test/sitemap.xml")],
            ),
            patch("app.parsers.sitemap_parser.collect_article_references", return_value=references),
            patch("app.parsers.sitemap_parser.extract_article", side_effect=fake_extract_article),
        ):
            batches = list(
                iter_extracted_article_batches_from_sitemap_index(
                    "https://example.test/sitemap-index.xml",
                    max_articles=3,
                    batch_size=2,
                )
            )

        self.assertEqual([[article.url for article in batch] for batch in batches], [
            ["https://example.test/1", "https://example.test/2"],
            ["https://example.test/3"],
        ])


def fake_extract_article(url: str, **kwargs) -> ExtractedArticle:
    """Вернуть тестовую статью по ссылке без сетевого запроса."""
    return ExtractedArticle(
        url=url,
        title="Новая статья",
        text="Текст статьи",
        published_at=datetime(2026, 1, 3),
    )


if __name__ == "__main__":
    unittest.main()
