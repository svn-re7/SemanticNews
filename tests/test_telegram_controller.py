from __future__ import annotations

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402


class TelegramControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        """Создать тестовый Flask-клиент для проверки Telegram UI."""
        app = create_app()
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def test_auth_page_shows_credentials_form(self) -> None:
        """Страница Telegram-авторизации показывает поля `api_id`, `api_hash` и телефона."""
        with patch("app.controllers.telegram_controller.TelegramAuthService", return_value=FakeTelegramAuthService()):
            response = self.client.get("/telegram/auth")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Telegram", response.text)
        self.assertIn('name="api_id"', response.text)
        self.assertIn('name="api_hash"', response.text)
        self.assertIn('name="phone"', response.text)

    def test_request_code_posts_credentials_to_service(self) -> None:
        """POST запроса кода передает данные формы в TelegramAuthService."""
        fake_service = FakeTelegramAuthService()

        with patch("app.controllers.telegram_controller.TelegramAuthService", return_value=fake_service):
            response = self.client.post(
                "/telegram/auth/request-code",
                data={
                    "api_id": "12345",
                    "api_hash": "hash-value",
                    "phone": "+79990000000",
                    "proxy_enabled": "1",
                    "proxy_type": "socks5",
                    "proxy_host": "127.0.0.1",
                    "proxy_port": "2080",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            fake_service.requested_code,
            ("12345", "hash-value", "+79990000000", "1", "socks5", "127.0.0.1", "2080"),
        )
        self.assertIn("Код отправлен", response.text)

    def test_confirm_code_posts_code_to_service(self) -> None:
        """POST подтверждения кода передает код в TelegramAuthService."""
        fake_service = FakeTelegramAuthService()

        with patch("app.controllers.telegram_controller.TelegramAuthService", return_value=fake_service):
            response = self.client.post("/telegram/auth/confirm-code", data={"code": "11111"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_service.confirmed_code, "11111")
        self.assertIn("авторизация сохранена", response.text)


@dataclass(slots=True)
class FakeStatus:
    """Подменный статус Telegram-авторизации для шаблона."""

    has_config: bool = False
    is_authorized: bool = False
    error: str | None = None


@dataclass(slots=True)
class FakeAuthResult:
    """Подменный результат шага Telegram-авторизации."""

    status: str
    message: str


class FakeTelegramAuthService:
    """Подменный сервис Telegram-авторизации для тестов контроллера."""

    def __init__(self) -> None:
        self.requested_code: tuple[str, str, str, str | None, str, str, str] | None = None
        self.confirmed_code: str | None = None

    def get_status(self) -> FakeStatus:
        """Вернуть fake-статус без подключения к Telegram."""
        return FakeStatus()

    def request_code(
        self,
        *,
        api_id: str,
        api_hash: str,
        phone: str,
        proxy_enabled: str | None = None,
        proxy_type: str = "",
        proxy_host: str = "",
        proxy_port: str = "",
    ) -> FakeAuthResult:
        """Запомнить данные запроса кода."""
        self.requested_code = (api_id, api_hash, phone, proxy_enabled, proxy_type, proxy_host, proxy_port)
        return FakeAuthResult(status="code_sent", message="Код отправлен в Telegram.")

    def confirm_code(self, code: str) -> FakeAuthResult:
        """Запомнить код подтверждения."""
        self.confirmed_code = code
        return FakeAuthResult(status="authorized", message="Telegram-авторизация сохранена.")

    def confirm_password(self, password: str) -> FakeAuthResult:
        """Имитировать подтверждение 2FA-пароля."""
        return FakeAuthResult(status="authorized", message="Telegram-авторизация сохранена.")


if __name__ == "__main__":
    unittest.main()
