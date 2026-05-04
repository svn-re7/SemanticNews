from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.parsers.source_adapters import normalize_whitespace  # noqa: E402


class SourceAdaptersTest(unittest.TestCase):
    def test_normalize_whitespace_removes_service_brackets_links_and_markdown(self) -> None:
        """Общая нормализация текста убирает служебные вставки, ссылки и markdown-разметку."""
        text = (
            "Это **важный** текст [в приложении.] "
            "Подробнее (https://plms.adj.st/r/example) в материале."
        )

        normalized_text = normalize_whitespace(text)

        self.assertEqual(normalized_text, "Это важный текст Подробнее в материале.")


if __name__ == "__main__":
    unittest.main()
