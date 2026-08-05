# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


spec_path = Path(globals().get("__file__", Path(SPECPATH) / "smarti.spec")).resolve()
repo_root = spec_path.parent.parent
app_icon = repo_root / "assets" / "smarti.ico"

datas = [
    (str(repo_root / "assets"), "assets"),
    (str(repo_root / "sitecustomize.py"), "."),
]

for package in ("certifi", "keyring", "truststore"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

hiddenimports = [
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
]
for package in (
    "bs4",
    "docx",
    "edge_tts",
    "gtts",
    "keyring",
    "litellm",
    "markdown",
    "PIL",
    "fitz",
    "pymupdf",
    "pyaudio",
    "PyPDF2",
    "pyautogui",
    "pygame",
    "pytesseract",
    "send2trash",
    "selenium",
    "speech_recognition",
    "truststore",
    "uiautomation",
    "windows_toasts",
    "win32com",
    "winrt",
):
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        pass


a = Analysis(
    [str(repo_root / "smarti_core.pyw")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SmartiAI",
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
    icon=str(app_icon),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SmartiAI",
)
