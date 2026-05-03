from __future__ import annotations

from flask import Blueprint, render_template, request

from app.services.telegram_auth_service import TelegramAuthResult, TelegramAuthService


telegram_bp = Blueprint("telegram", __name__, url_prefix="/telegram")


@telegram_bp.get("/auth")
def telegram_auth_page():
    """Показать страницу Telegram-авторизации."""
    return _render_auth_page()


@telegram_bp.post("/auth/request-code")
def request_telegram_code():
    """Отправить код подтверждения Telegram на телефон пользователя."""
    service = TelegramAuthService()
    try:
        result = service.request_code(
            api_id=request.form.get("api_id", ""),
            api_hash=request.form.get("api_hash", ""),
            phone=request.form.get("phone", ""),
            proxy_enabled=request.form.get("proxy_enabled"),
            proxy_type=request.form.get("proxy_type", ""),
            proxy_host=request.form.get("proxy_host", ""),
            proxy_port=request.form.get("proxy_port", ""),
        )
    except ValueError as error:
        return _render_auth_page(error_message=str(error)), 400

    return _render_auth_page(result=result, show_code_form=result.status == "code_sent")


@telegram_bp.post("/auth/confirm-code")
def confirm_telegram_code():
    """Подтвердить код из Telegram и сохранить session."""
    service = TelegramAuthService()
    try:
        result = service.confirm_code(request.form.get("code", ""))
    except ValueError as error:
        return _render_auth_page(error_message=str(error), show_code_form=True), 400

    show_password_form = result.status == "password_required"
    return _render_auth_page(result=result, show_code_form=result.status == "error", show_password_form=show_password_form)


@telegram_bp.post("/auth/confirm-password")
def confirm_telegram_password():
    """Подтвердить пароль двухфакторной защиты Telegram."""
    service = TelegramAuthService()
    try:
        result = service.confirm_password(request.form.get("password", ""))
    except ValueError as error:
        return _render_auth_page(error_message=str(error), show_password_form=True), 400

    return _render_auth_page(result=result, show_password_form=result.status == "error")


def _render_auth_page(
    *,
    result: TelegramAuthResult | None = None,
    error_message: str | None = None,
    show_code_form: bool = False,
    show_password_form: bool = False,
):
    """Подготовить данные страницы Telegram-авторизации для шаблона."""
    service = TelegramAuthService()
    status = service.get_status()
    return render_template(
        "telegram/auth.html",
        status=status,
        result=result,
        error_message=error_message,
        show_code_form=show_code_form,
        show_password_form=show_password_form,
    )
