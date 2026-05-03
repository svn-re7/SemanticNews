from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.config import Config


ClientFactory = Callable[[str, int, str], Any]


@dataclass(slots=True)
class TelegramAuthStatus:
    """Текущий статус локальной Telegram-авторизации."""

    # Есть ли локальный config с api_id/api_hash.
    has_config: bool
    # Подтверждена ли Telethon session для текущего аккаунта.
    is_authorized: bool
    # Краткая ошибка, если статус не удалось проверить.
    error: str | None = None


@dataclass(slots=True)
class TelegramAuthResult:
    """Результат одного шага Telegram-авторизации."""

    # Машинный статус шага: code_sent, authorized, password_required или error.
    status: str
    # Человекочитаемое сообщение для UI.
    message: str


@dataclass(slots=True)
class PendingTelegramAuth:
    """Временные данные между отправкой кода и подтверждением авторизации."""

    # Telegram api_id приложения.
    api_id: int
    # Telegram api_hash приложения.
    api_hash: str
    # Телефон аккаунта, на который отправлен код.
    phone: str
    # Хеш запроса кода, который Telethon требует при подтверждении.
    phone_code_hash: str | None


class TelegramAuthService:
    """Сервис создания локальной Telethon session через UI-авторизацию."""

    _pending_auth: PendingTelegramAuth | None = None

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        session_path: Path | None = None,
        client_factory: ClientFactory | None = None,
        password_error_class: type[Exception] | None = None,
    ) -> None:
        # Пути можно подменить в тестах, а в приложении используются runtime-файлы из instance.
        self.config_path = config_path if config_path is not None else Config.TELEGRAM_CONFIG_PATH
        self.session_path = session_path if session_path is not None else Config.TELEGRAM_SESSION_PATH
        self.client_factory = client_factory if client_factory is not None else self._create_telethon_client
        self.password_error_class = (
            password_error_class if password_error_class is not None else self._load_password_error_class()
        )

    def get_status(self) -> TelegramAuthStatus:
        """Проверить, есть ли config и авторизована ли локальная Telethon session."""
        if not self.config_path.exists():
            return TelegramAuthStatus(has_config=False, is_authorized=False)

        try:
            config = self._read_config()
            client = self._build_client(config["api_id"], config["api_hash"])
            is_authorized = self._run_client_call(client, "is_user_authorized")
        except Exception as error:
            return TelegramAuthStatus(has_config=True, is_authorized=False, error=str(error))

        return TelegramAuthStatus(has_config=True, is_authorized=bool(is_authorized))

    def request_code(self, *, api_id: str, api_hash: str, phone: str) -> TelegramAuthResult:
        """Отправить Telegram-код и сохранить данные во временном pending-состоянии."""
        normalized_api_id = self._normalize_api_id(api_id)
        normalized_api_hash = api_hash.strip()
        normalized_phone = phone.strip()

        if not normalized_api_hash:
            raise ValueError("api_hash не должен быть пустым.")
        if not normalized_phone:
            raise ValueError("Телефон Telegram не должен быть пустым.")

        client = self._build_client(normalized_api_id, normalized_api_hash)
        sent_code = self._run_client_call(client, "send_code_request", normalized_phone)
        phone_code_hash = getattr(sent_code, "phone_code_hash", None)

        # Config пишем только после успешного sign_in, поэтому до ввода кода держим данные в памяти.
        type(self)._pending_auth = PendingTelegramAuth(
            api_id=normalized_api_id,
            api_hash=normalized_api_hash,
            phone=normalized_phone,
            phone_code_hash=phone_code_hash,
        )
        return TelegramAuthResult(status="code_sent", message="Код отправлен в Telegram.")

    def confirm_code(self, code: str) -> TelegramAuthResult:
        """Подтвердить Telegram-код и создать session либо запросить 2FA-пароль."""
        pending = self._require_pending_auth()
        normalized_code = code.strip()
        if not normalized_code:
            raise ValueError("Код подтверждения не должен быть пустым.")

        client = self._build_client(pending.api_id, pending.api_hash)
        try:
            self._run_client_call(
                client,
                "sign_in",
                phone=pending.phone,
                code=normalized_code,
                phone_code_hash=pending.phone_code_hash,
            )
        except self.password_error_class:
            return TelegramAuthResult(
                status="password_required",
                message="Telegram требует пароль двухфакторной защиты.",
            )

        self._write_config(api_id=pending.api_id, api_hash=pending.api_hash)
        type(self)._pending_auth = None
        return TelegramAuthResult(status="authorized", message="Telegram-авторизация сохранена.")

    def confirm_password(self, password: str) -> TelegramAuthResult:
        """Подтвердить 2FA-пароль и сохранить config после успешного входа."""
        pending = self._require_pending_auth()
        normalized_password = password.strip()
        if not normalized_password:
            raise ValueError("Пароль двухфакторной защиты не должен быть пустым.")

        client = self._build_client(pending.api_id, pending.api_hash)
        self._run_client_call(client, "sign_in", password=normalized_password)

        self._write_config(api_id=pending.api_id, api_hash=pending.api_hash)
        type(self)._pending_auth = None
        return TelegramAuthResult(status="authorized", message="Telegram-авторизация сохранена.")

    def _build_client(self, api_id: int, api_hash: str) -> Any:
        """Создать Telethon-клиент или тестовую подмену и подключить его."""
        client = self.client_factory(str(self.session_path), api_id, api_hash)
        self._run_client_call(client, "connect")
        return client

    def _run_client_call(self, client: Any, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Вызвать sync/async метод клиента и корректно закрыть coroutine."""
        method = getattr(client, method_name)
        result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result

    def _read_config(self) -> dict[str, Any]:
        """Прочитать локальный Telegram config из instance."""
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def _write_config(self, *, api_id: int, api_hash: str) -> None:
        """Сохранить api_id/api_hash локально после успешной авторизации."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"api_id": api_id, "api_hash": api_hash}
        self.config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _require_pending_auth(self) -> PendingTelegramAuth:
        """Вернуть pending-состояние или объяснить, что код сначала нужно запросить."""
        if type(self)._pending_auth is None:
            raise ValueError("Сначала нужно запросить код Telegram.")
        return type(self)._pending_auth

    def _normalize_api_id(self, value: str) -> int:
        """Проверить и преобразовать api_id из формы в число."""
        try:
            return int(value)
        except ValueError as error:
            raise ValueError("api_id должен быть числом.") from error

    def _create_telethon_client(self, session_path: str, api_id: int, api_hash: str) -> Any:
        """Создать настоящий TelethonClient лениво, чтобы тесты не требовали Telethon."""
        try:
            from telethon import TelegramClient
        except ImportError as error:
            raise RuntimeError("Библиотека Telethon не установлена.") from error

        return TelegramClient(session_path, api_id, api_hash)

    def _load_password_error_class(self) -> type[Exception]:
        """Получить класс ошибки 2FA от Telethon или fallback для понятной ошибки."""
        try:
            from telethon.errors import SessionPasswordNeededError
        except ImportError:
            return RuntimeError

        return SessionPasswordNeededError
