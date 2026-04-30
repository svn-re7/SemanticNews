import threading
import time

import webview

from app.controllers.ingestion_controller import start_auto_ingestion_if_needed
from run import app


def run_flask() -> None:
    # Desktop-запуск тоже должен проверять свежесть новостей, но без блокировки окна приложения.
    start_auto_ingestion_if_needed()
    app.run(debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Даем Flask короткое время на старт перед открытием desktop-окна.
    time.sleep(1)
    webview.create_window("SemanticNews", "http://127.0.0.1:5000", width=1100, height=700)
    webview.start()
