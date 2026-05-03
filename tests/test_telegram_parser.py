from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
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

    def test_normalize_message_converts_aware_datetime_to_naive_utc(self) -> None:
        """Telegram aware datetime приводится к naive UTC для безопасной записи в SQLite."""
        message = FakeMessage(
            id=42,
            text="Заголовок поста\nОсновной текст Telegram-поста.",
            date=datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        )

        article = normalize_telegram_message("semantic_news", message)

        self.assertIsNotNone(article)
        self.assertEqual(article.published_at, datetime(2026, 5, 1, 12, 30))

    def test_collect_reads_config_connects_client_and_returns_articles(self) -> None:
        """Parser читает локальный config, подключает клиента и возвращает Telegram-посты."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            session_path = Path(temp_dir) / "semanticnews.session"
            config_path.write_text(
                json.dumps(
                    {
                        "api_id": 12345,
                        "api_hash": "hash-value",
                        "proxy": {"type": "socks5", "host": "127.0.0.1", "port": 2080},
                    }
                ),
                encoding="utf-8",
            )
            FakeTelegramClient.reset()

            parser = TelegramChannelParser(
                config_path=config_path,
                session_path=session_path,
                client_factory=FakeTelegramClient,
            )

            articles = parser.collect(channel="@semantic_news", limit=1)

        self.assertTrue(FakeTelegramClient.was_connected)
        self.assertEqual(FakeTelegramClient.last_proxy, {"type": "socks5", "host": "127.0.0.1", "port": 2080})
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].url, "https://t.me/semantic_news/42")

    def test_collect_stops_after_checkpoint(self) -> None:
        """Parser останавливается на первом Telegram-посте старше или равном checkpoint."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            session_path = Path(temp_dir) / "semanticnews.session"
            config_path.write_text(
                json.dumps({"api_id": 12345, "api_hash": "hash-value", "proxy": None}),
                encoding="utf-8",
            )
            FakeTelegramClient.reset()

            parser = TelegramChannelParser(
                config_path=config_path,
                session_path=session_path,
                client_factory=FakeTelegramClient,
            )

            articles = parser.collect(
                channel="@semantic_news",
                limit=3,
                stop_after_published_at=datetime(2026, 5, 1, 12, 29),
            )

        self.assertEqual([article.url for article in articles], ["https://t.me/semantic_news/42"])

    def test_collect_requires_authorized_session(self) -> None:
        """Без авторизованной Telethon session parser падает понятной ошибкой."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            session_path = Path(temp_dir) / "semanticnews.session"
            config_path.write_text(
                json.dumps({"api_id": 12345, "api_hash": "hash-value", "proxy": None}),
                encoding="utf-8",
            )

            parser = TelegramChannelParser(
                config_path=config_path,
                session_path=session_path,
                client_factory=UnauthorizedTelegramClient,
            )

            with self.assertRaisesRegex(RuntimeError, "session не авторизована"):
                parser.collect(channel="@semantic_news", limit=1)


@dataclass(slots=True)
class FakeMessage:
    """Минимальная fake-модель Telegram-сообщения для parser-теста."""

    id: int
    text: str
    date: datetime


class FakeTelegramClient:
    """Подменный Telegram-клиент для проверки parser-а без сети."""

    was_connected = False
    last_proxy: dict | None = None

    @classmethod
    def reset(cls) -> None:
        """Сбросить состояние fake-клиента перед тестом."""
        cls.was_connected = False
        cls.last_proxy = None

    def __init__(self, session_path: str, api_id: int, api_hash: str, *, proxy: dict | None = None) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        type(self).last_proxy = proxy

    async def connect(self) -> None:
        """Имитировать подключение к Telegram."""
        type(self).was_connected = True

    async def is_user_authorized(self) -> bool:
        """Имитировать уже созданную Telegram session."""
        return True

    def iter_messages(self, channel: str, *, limit: int) -> "FakeAsyncMessages":
        """Вернуть async-итератор, как это делает Telethon."""
        messages = [
            FakeMessage(
                id=42,
                text="Заголовок поста\nОсновной текст Telegram-поста.",
                date=datetime(2026, 5, 1, 12, 30),
            ),
            FakeMessage(
                id=43,
                text="Старый пост\nСодержательный текст старого Telegram-поста.",
                date=datetime(2026, 5, 1, 12, 29),
            ),
            FakeMessage(
                id=44,
                text="Еще более старый пост\nСодержательный текст.",
                date=datetime(2026, 5, 1, 12, 28),
            ),
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


class UnauthorizedTelegramClient(FakeTelegramClient):
    """Fake-клиент без авторизованной Telegram session."""

    async def is_user_authorized(self) -> bool:
        return False


if __name__ == "__main__":
    unittest.main()
