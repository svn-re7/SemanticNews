from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.parsers.telegram_parser import TelegramChannelParser, normalize_telegram_message  # noqa: E402


class TelegramParserTest(unittest.TestCase):
    def test_normalize_message_builds_extracted_article(self) -> None:
        """Telegram-сообщение нормализуется в общий parser model `ExtractedArticle`."""
        message = FakeMessage(
            id=42,
            text="Заголовок поста\nОсновной текст Telegram-поста.",
            date=datetime(2026, 5, 1, 12, 30),
        )

        article = normalize_telegram_message("@semantic_news", message)

        self.assertIsNotNone(article)
        self.assertEqual(article.url, "https://t.me/semantic_news/42")
        self.assertEqual(article.title, "Заголовок поста")
        self.assertEqual(article.text, "Заголовок поста\nОсновной текст Telegram-поста.")
        self.assertEqual(article.published_at, datetime(2026, 5, 1, 12, 30))
        self.assertEqual(article.article_type_code, "telegram_post")

    def test_normalize_message_skips_empty_text(self) -> None:
        """Пустые Telegram-сообщения не превращаются в статьи."""
        message = FakeMessage(id=42, text="   ", date=datetime(2026, 5, 1, 12, 30))

        article = normalize_telegram_message("semantic_news", message)

        self.assertIsNone(article)

    def test_collect_reads_config_connects_client_and_returns_articles(self) -> None:
        """Parser читает локальный config, подключает клиента и возвращает Telegram-посты."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            session_path = Path(temp_dir) / "semanticnews.session"
            config_path.write_text(
                json.dumps({"api_id": 12345, "api_hash": "hash-value"}),
                encoding="utf-8",
            )
            FakeTelegramClient.reset()

            parser = TelegramChannelParser(
                config_path=config_path,
                session_path=session_path,
                client_factory=FakeTelegramClient,
            )

            articles = parser.collect(channel="@semantic_news", limit=2)

        self.assertTrue(FakeTelegramClient.was_connected)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].url, "https://t.me/semantic_news/42")


@dataclass(slots=True)
class FakeMessage:
    """Минимальная fake-модель Telegram-сообщения для parser-теста."""

    id: int
    text: str
    date: datetime


class FakeTelegramClient:
    """Подменный Telegram-клиент для проверки parser-а без сети."""

    was_connected = False

    @classmethod
    def reset(cls) -> None:
        """Сбросить состояние fake-клиента перед тестом."""
        cls.was_connected = False

    def __init__(self, session_path: str, api_id: int, api_hash: str) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash

    async def connect(self) -> None:
        """Имитировать подключение к Telegram."""
        type(self).was_connected = True

    def iter_messages(self, channel: str, *, limit: int) -> "FakeAsyncMessages":
        """Вернуть async-итератор, как это делает Telethon."""
        messages = [
            FakeMessage(
                id=42,
                text="Заголовок поста\nОсновной текст Telegram-поста.",
                date=datetime(2026, 5, 1, 12, 30),
            ),
            FakeMessage(id=43, text=" ", date=datetime(2026, 5, 1, 12, 31)),
        ][:limit]
        return FakeAsyncMessages(messages)


class FakeAsyncMessages:
    """Минимальный async-итератор Telegram-сообщений."""

    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages

    def __aiter__(self):
        self._iterator = iter(self.messages)
        return self

    async def __anext__(self) -> FakeMessage:
        try:
            return next(self._iterator)
        except StopIteration as error:
            raise StopAsyncIteration from error


if __name__ == "__main__":
    unittest.main()
