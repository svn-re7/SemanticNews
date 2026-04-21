import threading
import time

import webview

from run import app


def run_flask() -> None:
    app.run(debug=False, use_reloader=False)


if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Give Flask a moment to start before opening the desktop window.
    time.sleep(1)
    webview.create_window("SemanticNews", "http://127.0.0.1:5000", width=1100, height=700)
    webview.start()
