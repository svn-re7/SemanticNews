from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.services.telegram_auth_service import TelegramAuthService  # noqa: E402


class TelegramAuthServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        """Подготовить временные runtime-файлы Telegram для изолированного теста."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name)
        self.config_path = self.runtime_dir / "config.json"
        self.session_path = self.runtime_dir / "semanticnews.session"
        FakeTelegramClient.reset()

    def tearDown(self) -> None:
        """Удалить временные runtime-файлы после теста."""
        self.temp_dir.cleanup()

    def test_request_code_keeps_credentials_pending_until_confirm_code(self) -> None:
        """Запрос кода не пишет ключи в config до успешного подтверждения Telegram-кода."""
        service = TelegramAuthService(
            config_path=self.config_path,
            session_path=self.session_path,
            client_factory=FakeTelegramClient,
            password_error_class=FakePasswordRequired,
        )

        result = service.request_code(
            api_id="12345",
            api_hash="hash-value",
            phone="+79990000000",
            proxy_enabled="1",
            proxy_type="socks5",
            proxy_host="127.0.0.1",
            proxy_port="2080",
        )

        self.assertEqual(result.status, "code_sent")
        self.assertEqual(FakeTelegramClient.last_phone, "+79990000000")
        self.assertEqual(
            FakeTelegramClient.last_proxy,
            {"type": "socks5", "host": "127.0.0.1", "port": 2080},
        )
        self.assertEqual(FakeTelegramClient.disconnect_count, 1)
        self.assertFalse(self.config_path.exists())

    def test_request_code_creates_session_directory_before_telethon_client(self) -> None:
        """Перед созданием Telethon-клиента сервис создает папку для SQLite session."""
        missing_dir_session_path = self.runtime_dir / "missing" / "semanticnews.session"
        service = TelegramAuthService(
            config_path=self.config_path,
            session_path=missing_dir_session_path,
            client_factory=DirectoryCheckingTelegramClient,
            password_error_class=FakePasswordRequired,
        )

        result = service.request_code(api_id="12345", api_hash="hash-value", phone="+79990000000")

        self.assertEqual(result.status, "code_sent")
        self.assertTrue(missing_dir_session_path.parent.exists())

    def test_request_code_returns_error_when_telegram_connection_fails(self) -> None:
        """Сетевая ошибка Telegram возвращается как результат, а не пробрасывается во Flask."""
        service = TelegramAuthService(
            config_path=self.config_path,
            session_path=self.session_path,
            client_factory=ConnectionFailingTelegramClient,
            password_error_class=FakePasswordRequired,
        )

        result = service.request_code(api_id="12345", api_hash="hash-value", phone="+79990000000")

        self.assertEqual(result.status, "error")
        self.assertIn("Telegram", result.message)
        self.assertFalse(self.config_path.exists())

    def test_confirm_code_saves_config_after_successful_authorization(self) -> None:
        """Успешное подтверждение кода сохраняет `api_id/api_hash` в локальный config."""
        service = TelegramAuthService(
            config_path=self.config_path,
            session_path=self.session_path,
            client_factory=FakeTelegramClient,
            password_error_class=FakePasswordRequired,
        )

        service.request_code(api_id="12345", api_hash="hash-value", phone="+79990000000")
        result = service.confirm_code("11111")

        self.assertEqual(result.status, "authorized")
        self.assertEqual(FakeTelegramClient.disconnect_count, 2)
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["api_id"], 12345)
        self.assertEqual(payload["api_hash"], "hash-value")

    def test_confirm_code_reports_password_required_without_saving_config(self) -> None:
        """Если Telegram требует 2FA, сервис оставляет pending-состояние до ввода пароля."""
        FakeTelegramClient.require_password = True
        service = TelegramAuthService(
            config_path=self.config_path,
            session_path=self.session_path,
            client_factory=FakeTelegramClient,
            password_error_class=FakePasswordRequired,
        )

        service.request_code(api_id="12345", api_hash="hash-value", phone="+79990000000")
        result = service.confirm_code("11111")

        self.assertEqual(result.status, "password_required")
        self.assertEqual(FakeTelegramClient.disconnect_count, 2)
        self.assertFalse(self.config_path.exists())

    def test_confirm_password_saves_config_after_two_factor_authorization(self) -> None:
        """После успешного 2FA-пароля сервис сохраняет config для следующих запусков."""
        FakeTelegramClient.require_password = True
        service = TelegramAuthService(
            config_path=self.config_path,
            session_path=self.session_path,
            client_factory=FakeTelegramClient,
            password_error_class=FakePasswordRequired,
        )

        service.request_code(api_id="12345", api_hash="hash-value", phone="+79990000000")
        service.confirm_code("11111")
        result = service.confirm_password("secret-password")

        self.assertEqual(result.status, "authorized")
        self.assertEqual(FakeTelegramClient.last_password, "secret-password")
        self.assertEqual(FakeTelegramClient.disconnect_count, 3)
        self.assertTrue(self.config_path.exists())


class FakePasswordRequired(Exception):
    """Подменная ошибка Telethon для сценария двухфакторной защиты."""


class FakeSentCode:
    """Подменный результат отправки Telegram-кода."""

    phone_code_hash = "phone-code-hash"


class FakeTelegramClient:
    """Подменный Telethon-клиент без реального подключения к Telegram."""

    last_phone: str | None = None
    last_password: str | None = None
    last_proxy: dict | None = None
    disconnect_count = 0
    require_password = False

    def __init__(self, session_path: str, api_id: int, api_hash: str, *, proxy: dict | None = None) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        type(self).last_proxy = proxy

    @classmethod
    def reset(cls) -> None:
        """Сбросить состояние fake-клиента между тестами."""
        cls.last_phone = None
        cls.last_password = None
        cls.last_proxy = None
        cls.disconnect_count = 0
        cls.require_password = False

    async def connect(self) -> None:
        """Имитировать подключение к Telegram."""

    async def disconnect(self) -> None:
        """Имитировать отключение от Telegram."""
        type(self).disconnect_count += 1

    async def send_code_request(self, phone: str) -> FakeSentCode:
        """Запомнить телефон и вернуть fake-хеш кода."""
        type(self).last_phone = phone
        return FakeSentCode()

    async def sign_in(
        self,
        *,
        phone: str | None = None,
        code: str | None = None,
        password: str | None = None,
        phone_code_hash: str | None = None,
    ) -> None:
        """Имитировать подтверждение кода или 2FA-пароля."""
        if password is not None:
            type(self).last_password = password
            type(self).require_password = False
            return
        if type(self).require_password:
            raise FakePasswordRequired()


class DirectoryCheckingTelegramClient(FakeTelegramClient):
    """Fake-клиент, который падает, если папка session еще не создана."""

    def __init__(self, session_path: str, api_id: int, api_hash: str, *, proxy: dict | None = None) -> None:
        if not Path(session_path).parent.exists():
            raise RuntimeError("session directory does not exist")
        super().__init__(session_path, api_id, api_hash, proxy=proxy)


class ConnectionFailingTelegramClient(FakeTelegramClient):
    """Fake-клиент, который имитирует недоступность серверов Telegram."""

    async def connect(self) -> None:
        raise ConnectionError("Connection to Telegram failed 5 time(s)")


if __name__ == "__main__":
    unittest.main()
