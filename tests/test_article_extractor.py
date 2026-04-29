from __future__ import annotations

import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.parsers.article_extractor import _extract_text_from_html  # noqa: E402


class ArticleExtractorTest(unittest.TestCase):
    def test_extracts_kommersant_article_text_from_source_specific_container(self) -> None:
        """HTML Коммерсанта читается из контейнера текста статьи, если общий extractor не помог."""
        html = """
        <html>
            <body>
                <div class="article_text_wrapper">
                    <p>Первый абзац материала Коммерсанта.</p>
                    <p>Второй абзац с важными деталями.</p>
                </div>
                <div class="adv">Рекламный блок не должен попасть в текст.</div>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        text = _extract_text_from_html(html, soup, "https://www.kommersant.ru/doc/123")

        self.assertEqual(text, "Первый абзац материала Коммерсанта. Второй абзац с важными деталями.")

    def test_extracts_izvestia_article_text_from_source_specific_container(self) -> None:
        """HTML Известий читается из articleBody, если общий extractor не помог."""
        html = """
        <html>
            <body>
                <article itemprop="articleBody">
                    <p>Первый абзац материала Известий.</p>
                    <p>Второй абзац без лишних блоков страницы.</p>
                </article>
                <aside>Похожая статья не должна попасть в текст.</aside>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        text = _extract_text_from_html(html, soup, "https://iz.ru/123/2026-04-29/example")

        self.assertEqual(text, "Первый абзац материала Известий. Второй абзац без лишних блоков страницы.")

    def test_removes_izvestia_article_ui_prefix_from_source_specific_text(self) -> None:
        """Служебные переключатели Известий не попадают в сохраненный текст статьи."""
        html = """
        <html>
            <body>
                <article>
                    <div>Выделить главное</div>
                    <div>Вкл</div>
                    <div>Выкл</div>
                    <p>Дом из фильма выставлен на продажу.</p>
                </article>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        text = _extract_text_from_html(html, soup, "https://iz.ru/123/video/example")

        self.assertEqual(text, "Дом из фильма выставлен на продажу.")

    def test_ignores_izvestia_video_page_without_real_article_text(self) -> None:
        """Видео-страница Известий без текста статьи считается пустой."""
        html = """
        <html>
            <body>
                <article>
                    <div>Выделить главное</div>
                    <div>Вкл</div>
                    <div>Выкл</div>
                    <div>Поделиться:</div>
                    <div>Читайте также</div>
                </article>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        text = _extract_text_from_html(html, soup, "https://iz.ru/123/video/example")

        self.assertEqual(text, "")


if __name__ == "__main__":
    unittest.main()
