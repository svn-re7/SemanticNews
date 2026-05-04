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
    collect_article_references,
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
            batches = list(
                iter_extracted_article_batches_from_sitemap_index(
                    "https://example.test/sitemap-index.xml",
                    stop_after_published_at=datetime(2026, 1, 2),
                    stop_after_old_articles=2,
                )
            )

        articles = [article for batch in batches for article in batch]
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

    def test_iter_extracted_article_batches_waits_between_article_requests(self) -> None:
        """Sitemap-парсер делает паузу между скачиваниями HTML-страниц статей."""
        references = [
            ArticleReference(url="https://example.test/1", lastmod=datetime(2026, 1, 1)),
            ArticleReference(url="https://example.test/2", lastmod=datetime(2026, 1, 2)),
            ArticleReference(url="https://example.test/3", lastmod=datetime(2026, 1, 3)),
        ]
        sleep_calls: list[float] = []

        with (
            patch(
                "app.parsers.sitemap_parser.extract_sitemap_entries",
                return_value=[SitemapEntry(url="https://example.test/sitemap.xml")],
            ),
            patch("app.parsers.sitemap_parser.collect_article_references", return_value=references),
            patch("app.parsers.sitemap_parser.extract_article", side_effect=fake_extract_article),
        ):
            list(
                iter_extracted_article_batches_from_sitemap_index(
                    "https://example.test/sitemap-index.xml",
                    max_articles=3,
                    article_request_delay_seconds=0.5,
                    sleep_function=sleep_calls.append,
                )
            )

        self.assertEqual(sleep_calls, [0.5, 0.5])

    def test_collect_article_references_reverses_old_to_new_sitemap_order(self) -> None:
        """Sitemap со ссылками от старых к новым разворачивается перед дальнейшим обходом."""
        references = [
            ArticleReference(url="https://example.test/old", lastmod=datetime(2026, 1, 1)),
            ArticleReference(url="https://example.test/middle", lastmod=datetime(2026, 1, 2)),
            ArticleReference(url="https://example.test/new", lastmod=datetime(2026, 1, 3)),
        ]

        with patch(
            "app.parsers.sitemap_parser.extract_article_references_from_sitemap",
            return_value=references,
        ):
            collected = collect_article_references(
                [SitemapEntry(url="https://example.test/sitemap.xml")],
                max_articles=3,
            )

        self.assertEqual(
            [reference.url for reference in collected],
            [
                "https://example.test/new",
                "https://example.test/middle",
                "https://example.test/old",
            ],
        )

    def test_date_only_lastmod_on_checkpoint_day_is_checked_by_article_date(self) -> None:
        """Date-only lastmod за день checkpoint не должен останавливать parser до чтения HTML."""
        references = [
            ArticleReference(url="https://example.test/same-day", lastmod=datetime(2026, 1, 3)),
        ]

        with (
            patch(
                "app.parsers.sitemap_parser.extract_sitemap_entries",
                return_value=[SitemapEntry(url="https://example.test/sitemap.xml")],
            ),
            patch("app.parsers.sitemap_parser.collect_article_references", return_value=references),
            patch(
                "app.parsers.sitemap_parser.extract_article",
                side_effect=fake_extract_same_day_new_article,
            ) as extract_mock,
        ):
            batches = list(
                iter_extracted_article_batches_from_sitemap_index(
                    "https://example.test/sitemap-index.xml",
                    stop_after_published_at=datetime(2026, 1, 3, 12, 0),
                )
            )

        articles = [article for batch in batches for article in batch]
        self.assertEqual([article.url for article in articles], ["https://example.test/same-day"])
        self.assertEqual(extract_mock.call_count, 1)


def fake_extract_article(url: str, **kwargs) -> ExtractedArticle:
    """Вернуть тестовую статью по ссылке без сетевого запроса."""
    return ExtractedArticle(
        url=url,
        title="Новая статья",
        text="Текст статьи",
        published_at=datetime(2026, 1, 3),
    )


def fake_extract_same_day_new_article(url: str, **kwargs) -> ExtractedArticle:
    """Вернуть статью, которая новее checkpoint внутри того же календарного дня."""
    return ExtractedArticle(
        url=url,
        title="Новая статья",
        text="Текст статьи",
        published_at=datetime(2026, 1, 3, 13, 0),
    )


if __name__ == "__main__":
    unittest.main()
