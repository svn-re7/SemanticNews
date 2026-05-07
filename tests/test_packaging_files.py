from __future__ import annotations

import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class PackagingFilesTest(unittest.TestCase):
    def test_pyinstaller_spec_uses_webview_entrypoint_and_static_data(self) -> None:
        """Spec-файл должен собирать desktop entrypoint и Flask templates/static."""
        spec_path = ROOT_DIR / "semanticnews.spec"
        content = spec_path.read_text(encoding="utf-8")

        self.assertIn("project/webview_app.py", content.replace("\\", "/"))
        self.assertIn("app/templates", content.replace("\\", "/"))
        self.assertIn("app/static", content.replace("\\", "/"))

    def test_desktop_build_script_runs_pyinstaller_spec(self) -> None:
        """Build-скрипт должен запускать PyInstaller по подготовленному spec."""
        script_path = ROOT_DIR / "scripts" / "build_desktop.ps1"
        content = script_path.read_text(encoding="utf-8")

        self.assertIn("semanticnews.spec", content)
        self.assertIn("PyInstaller", content)
        self.assertIn("project\\instance\\app.db", content)
        self.assertIn("project\\instance\\news.index", content)
        self.assertIn("project\\instance\\news_index_ids.json", content)
        self.assertIn("project\\instance\\models\\news-embeddings", content)
        self.assertIn("Telegram runtime", content)


if __name__ == "__main__":
    unittest.main()
