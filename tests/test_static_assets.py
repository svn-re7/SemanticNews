from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app import create_app  # noqa: E402


class StaticAssetsTest(unittest.TestCase):
    def test_base_template_uses_local_bootstrap_css(self) -> None:
        """Desktop UI не должен зависеть от CDN для базовых Bootstrap-стилей."""
        app = create_app()
        app.config.update(TESTING=True)
        client = app.test_client()

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("/static/vendor/bootstrap/bootstrap.min.css", response.text)
        self.assertNotIn("cdn.jsdelivr.net", response.text)


if __name__ == "__main__":
    unittest.main()
