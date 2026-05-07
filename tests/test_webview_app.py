from __future__ import annotations

import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from webview_app import build_app_url, find_free_port, wait_for_flask  # noqa: E402


class WebviewAppTest(unittest.TestCase):
    def test_find_free_port_returns_bindable_port(self) -> None:
        """Desktop launcher должен уметь выбирать свободный локальный порт."""
        port = find_free_port()

        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)

    def test_build_app_url_uses_host_and_port(self) -> None:
        """URL окна должен строиться из фактического host/port Flask-сервера."""
        self.assertEqual(build_app_url("127.0.0.1", 5055), "http://127.0.0.1:5055")

    def test_wait_for_flask_waits_until_health_is_ok(self) -> None:
        """Launcher должен ждать /health вместо фиксированного sleep."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            wait_for_flask("127.0.0.1", server.server_port, timeout_seconds=2.0, interval_seconds=0.05)
        finally:
            server.shutdown()
            server.server_close()

    def test_run_flask_starts_periodic_ingestion_scheduler(self) -> None:
        """Desktop entrypoint должен включать периодический scheduler автообновления."""
        import webview_app  # noqa: PLC0415

        with (
            patch.object(webview_app, "start_auto_ingestion_if_needed") as start_auto,
            patch.object(webview_app, "start_ingestion_scheduler") as start_scheduler,
            patch.object(webview_app.app, "run") as app_run,
        ):
            webview_app.run_flask("127.0.0.1", 5010)

        start_auto.assert_called_once_with()
        start_scheduler.assert_called_once_with(start_auto)
        app_run.assert_called_once_with(host="127.0.0.1", port=5010, debug=False, use_reloader=False)


class HealthHandler(BaseHTTPRequestHandler):
    """Минимальный HTTP handler для проверки ожидания Flask healthcheck."""

    def do_GET(self) -> None:
        """Ответить 200 только на /health."""
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Отключить шумный лог встроенного HTTPServer в тестах."""
        return None


if __name__ == "__main__":
    unittest.main()
