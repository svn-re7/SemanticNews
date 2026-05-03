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

        result = service.request_code(api_id="12345", api_hash="hash-value", phone="+79990000000")

        self.assertEqual(result.status, "code_sent")
        self.assertEqual(FakeTelegramClient.last_phone, "+79990000000")
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
    require_password = False

    def __init__(self, session_path: str, api_id: int, api_hash: str) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash

    @classmethod
    def reset(cls) -> None:
        """Сбросить состояние fake-клиента между тестами."""
        cls.last_phone = None
        cls.last_password = None
        cls.require_password = False

    async def connect(self) -> None:
        """Имитировать подключение к Telegram."""

    async def disconnect(self) -> None:
        """Имитировать отключение от Telegram."""

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


if __name__ == "__main__":
    unittest.main()
