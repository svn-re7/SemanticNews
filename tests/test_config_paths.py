from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1] / "project"
sys.path.insert(0, str(PROJECT_DIR))

from app.config import resolve_runtime_base_dir  # noqa: E402


class ConfigPathsTest(unittest.TestCase):
    def test_resolve_runtime_base_dir_uses_source_dir_when_not_frozen(self) -> None:
        """В обычном запуске runtime-файлы остаются в project/instance."""
        source_dir = Path("C:/project").resolve()

        result = resolve_runtime_base_dir(
            frozen=False,
            executable="C:/dist/SemanticNews.exe",
            source_base_dir=source_dir,
        )

        self.assertEqual(result, source_dir)

    def test_resolve_runtime_base_dir_uses_exe_dir_when_frozen(self) -> None:
        """В PyInstaller-запуске runtime-файлы должны жить рядом с exe, а не в _MEIPASS."""
        result = resolve_runtime_base_dir(
            frozen=True,
            executable="C:/dist/SemanticNews/SemanticNews.exe",
            source_base_dir=Path("C:/tmp/_MEIPASS/project"),
        )

        self.assertEqual(result, Path("C:/dist/SemanticNews").resolve())

    def test_resolve_runtime_base_dir_allows_env_override(self) -> None:
        """Для отладки и переносимой сборки runtime-каталог можно явно задать через env."""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = resolve_runtime_base_dir(
                frozen=True,
                executable="C:/dist/SemanticNews.exe",
                source_base_dir=Path("C:/tmp/_MEIPASS/project"),
                env_runtime_dir=temp_dir,
            )

            self.assertEqual(result, Path(temp_dir).resolve())


if __name__ == "__main__":
    unittest.main()
