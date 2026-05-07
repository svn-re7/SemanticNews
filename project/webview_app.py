from __future__ import annotations

import socket
import threading
import time
import urllib.error
import urllib.request

import webview

from app.controllers.ingestion_controller import start_auto_ingestion_if_needed
from run import app


DEFAULT_HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 15.0
STARTUP_POLL_INTERVAL_SECONDS = 0.2


def find_free_port(host: str = DEFAULT_HOST) -> int:
    """Найти свободный локальный порт для desktop-запуска Flask."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def build_app_url(host: str, port: int) -> str:
    """Собрать URL, который будет открыт внутри pywebview-окна."""
    return f"http://{host}:{port}"


def wait_for_flask(
    host: str,
    port: int,
    *,
    timeout_seconds: float = STARTUP_TIMEOUT_SECONDS,
    interval_seconds: float = STARTUP_POLL_INTERVAL_SECONDS,
) -> None:
    """Дождаться готовности Flask по /health вместо фиксированного sleep."""
    health_url = f"{build_app_url(host, port)}/health"
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    while time.monotonic() < deadline:
        try:
            with opener.open(health_url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError) as error:
            last_error = error
        time.sleep(interval_seconds)

    raise RuntimeError(f"Flask не стартовал за {timeout_seconds:.1f} сек. Последняя ошибка: {last_error}")


def run_flask(host: str, port: int) -> None:
    """Запустить Flask-сервер для desktop-окна."""
    # Desktop-запуск тоже должен проверять свежесть новостей, но без блокировки окна приложения.
    start_auto_ingestion_if_needed()
    app.run(host=host, port=port, debug=False, use_reloader=False)


def _startup_error_html(error: Exception) -> str:
    """Собрать простую HTML-страницу ошибки старта для desktop-окна."""
    return f"""
    <!doctype html>
    <html lang=\"ru\">
    <meta charset=\"utf-8\">
    <body style=\"font-family: sans-serif; padding: 24px;\">
        <h1>SemanticNews не удалось запустить</h1>
        <p>Flask-сервер не ответил на healthcheck.</p>
        <pre>{error}</pre>
    </body>
    </html>
    """


if __name__ == "__main__":
    host = DEFAULT_HOST
    port = find_free_port(host)
    flask_thread = threading.Thread(target=run_flask, args=(host, port), daemon=True)
    flask_thread.start()

    try:
        wait_for_flask(host, port)
        webview.create_window("SemanticNews", build_app_url(host, port), width=1100, height=700)
    except RuntimeError as error:
        webview.create_window("SemanticNews - ошибка запуска", html=_startup_error_html(error), width=900, height=500)
    webview.start()
