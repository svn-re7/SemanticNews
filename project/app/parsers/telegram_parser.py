from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from app.config import Config
from app.parsers.parser_models import ExtractedArticle
from app.parsers.source_adapters import normalize_whitespace


ClientFactory = Callable[..., Any]
TELEGRAM_TITLE_MAX_LENGTH = 100


def normalize_telegram_message(channel: str, message: Any) -> ExtractedArticle | None:
    """Преобразовать Telegram-сообщение в общий parser model."""
    text = _extract_message_text(message)
    if not text:
        return None

    title = _build_title(text)
    message_id = getattr(message, "id")
    published_at = _to_naive_utc(getattr(message, "date", None))

    return ExtractedArticle(
        url=_build_message_url(channel, message_id),
        title=title,
        text=text,
        published_at=published_at if isinstance(published_at, datetime) else None,
        article_type_code="telegram_post",
    )


def collect_extracted_articles_from_telegram_channel(
    channel: str,
    *,
    limit: int = 100,
    stop_after_published_at: datetime | None = None,
    config_path: Path | None = None,
    session_path: Path | None = None,
    client_factory: ClientFactory | None = None,
) -> list[ExtractedArticle]:
    """Собрать сообщения Telegram-канала через готовую Telethon session."""
    parser = TelegramChannelParser(
        config_path=config_path,
        session_path=session_path,
        client_factory=client_factory,
    )
    return parser.collect(channel=channel, limit=limit, stop_after_published_at=stop_after_published_at)


class TelegramChannelParser:
    """Parser-адаптер для чтения Telegram-каналов через Telethon."""

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        session_path: Path | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        # Пути совпадают с TelegramAuthService, чтобы parser использовал уже созданную session.
        self.config_path = config_path if config_path is not None else Config.TELEGRAM_CONFIG_PATH
        self.session_path = session_path if session_path is not None else Config.TELEGRAM_SESSION_PATH
        self.client_factory = client_factory if client_factory is not None else self._create_telethon_client

    def collect(
        self,
        *,
        channel: str,
        limit: int = 100,
        stop_after_published_at: datetime | None = None,
    ) -> list[ExtractedArticle]:
        """Прочитать последние сообщения канала и вернуть только содержательные посты."""
        if limit <= 0:
            return []

        return asyncio.run(
            self._collect_async(
                channel=channel,
                limit=limit,
                stop_after_published_at=stop_after_published_at,
            )
        )

    async def _collect_async(
        self,
        *,
        channel: str,
        limit: int,
        stop_after_published_at: datetime | None,
    ) -> list[ExtractedArticle]:
        """Прочитать Telegram-канал внутри одного asyncio event loop."""
        config = self._read_config()
        cutoff = _to_naive_utc(stop_after_published_at)
        # Telethon session - SQLite-файл, поэтому папка session должна существовать заранее.
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        client = self.client_factory(str(self.session_path), config["api_id"], config["api_hash"], proxy=config.get("proxy"))

        try:
            await self._resolve_client_result(client.connect())
            is_authorized = await self._resolve_client_result(client.is_user_authorized())
            if not is_authorized:
                raise RuntimeError("Telegram session не авторизована. Сначала выполните авторизацию через UI.")
            messages = client.iter_messages(_normalize_channel(channel), limit=limit)

            articles: list[ExtractedArticle] = []
            async for message in messages:
                article = normalize_telegram_message(channel, message)
                if article is not None:
                    # Telegram отдает посты от новых к старым, поэтому по checkpoint можно остановиться сразу.
                    if cutoff is not None and article.published_at is not None and article.published_at <= cutoff:
                        break
                    articles.append(article)
            return articles
        finally:
            # Даже в локальном desktop-приложении сетевое соединение лучше закрывать явно.
            if hasattr(client, "disconnect"):
                await self._resolve_client_result(client.disconnect())

    def _read_config(self) -> dict[str, Any]:
        """Прочитать локальный Telegram config с api_id/api_hash."""
        if not self.config_path.exists():
            raise RuntimeError("Telegram config не найден. Сначала выполните авторизацию.")
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _run_client_call(self, client: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Вызвать sync/async метод клиента и вернуть обычный Python-результат."""
        method = getattr(client, method_name)
        result = method(*args, **kwargs)
        if inspect.isasyncgen(result) or hasattr(result, "__aiter__"):
            return asyncio.run(_collect_async_generator(result))
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result

    async def _resolve_client_result(self, result: Any) -> Any:
        """Дождаться coroutine или async-generator Telethon в текущем event loop."""
        if inspect.isasyncgen(result) or hasattr(result, "__aiter__"):
            return [item async for item in result]
        if inspect.isawaitable(result):
            return await result
        return result

    def _create_telethon_client(
        self,
        session_path: str,
        api_id: int,
        api_hash: str,
        *,
        proxy: dict[str, Any] | None = None,
    ) -> Any:
        """Создать настоящий TelethonClient лениво, чтобы тесты не требовали Telethon."""
        try:
            from telethon import TelegramClient
        except ImportError as error:
            raise RuntimeError("Библиотека Telethon не установлена.") from error

        Path(session_path).parent.mkdir(parents=True, exist_ok=True)
        return TelegramClient(session_path, api_id, api_hash, proxy=self._build_telethon_proxy(proxy))

    def _build_telethon_proxy(self, proxy: dict[str, Any] | None) -> dict[str, Any] | None:
        """Преобразовать сохраненный Telegram proxy-config в dict-формат для Telethon."""
        if not proxy:
            return None

        try:
            import python_socks  # noqa: F401
        except ImportError as error:
            raise RuntimeError("Для Telegram proxy нужно установить зависимость python-socks.") from error

        return {
            "proxy_type": proxy["type"],
            "addr": proxy["host"],
            "port": int(proxy["port"]),
            # DNS лучше отдавать proxy, чтобы прямой сетевой путь к Telegram не использовался.
            "rdns": True,
        }


async def _collect_async_generator(async_generator: Any) -> list[Any]:
    """Собрать async-generator Telethon в обычный список сообщений."""
    return [item async for item in async_generator]


def _extract_message_text(message: Any) -> str:
    """Достать текст Telegram-сообщения из распространенных полей Telethon."""
    raw_text = getattr(message, "text", None) or getattr(message, "message", None) or ""
    return normalize_whitespace(str(raw_text), preserve_newlines=True)


def _to_naive_utc(value: datetime | None) -> datetime | None:
    """Привести дату Telegram к naive UTC, как остальные даты в SQLite."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _build_title(text: str) -> str:
    """Взять первую содержательную строку Telegram-поста как заголовок."""
    for line in text.splitlines():
        normalized_line = line.strip()
        if normalized_line:
            if len(normalized_line) <= TELEGRAM_TITLE_MAX_LENGTH:
                return normalized_line
            # Заголовок нужен для UI, поэтому длинный первый абзац Telegram-поста аккуратно сокращаем.
            return normalized_line[:TELEGRAM_TITLE_MAX_LENGTH - 3].rstrip() + "..."
    return "Telegram-пост"


def _build_message_url(channel: str, message_id: int) -> str:
    """Построить прямую ссылку на сообщение публичного Telegram-канала."""
    channel_name = _normalize_channel(channel)
    return f"https://t.me/{channel_name}/{message_id}"


def _normalize_channel(channel: str) -> str:
    """Нормализовать `@channel`, `channel` или `https://t.me/channel` до имени канала."""
    normalized = channel.strip()
    normalized = normalized.removeprefix("https://t.me/")
    normalized = normalized.removeprefix("http://t.me/")
    normalized = normalized.removeprefix("@")
    return normalized.strip("/")
