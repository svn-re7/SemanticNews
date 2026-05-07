# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


ROOT_DIR = Path(SPECPATH).resolve()
PROJECT_DIR = ROOT_DIR / "project"
ENTRYPOINT = PROJECT_DIR / "webview_app.py"  # project/webview_app.py

# В desktop-сборку обязательно кладем Flask templates/static, иначе Jinja2 и CSS не найдут файлы.
datas = [
    (str(PROJECT_DIR / "app" / "templates"), "app/templates"),
    (str(PROJECT_DIR / "app" / "static"), "app/static"),
]

# Часть библиотек подгружается динамически, поэтому PyInstaller лучше явно подсказать imports.
hiddenimports = [
    "webview",
    "webview.platforms.winforms",
    "faiss",
    "sentence_transformers",
    "transformers",
    "torch",
    "telethon",
    "python_socks",
]

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SemanticNews",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SemanticNews",
)
