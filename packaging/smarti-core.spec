# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


spec_path = Path(globals().get("__file__", Path(SPECPATH) / "smarti-core.spec")).resolve()
repo_root = spec_path.parent.parent

datas = [
    (str(repo_root / "assets"), "assets"),
    (str(repo_root / "sitecustomize.py"), "."),
]
for package in ("certifi", "keyring", "truststore"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass

hiddenimports = []
for package in (
    "aiohttp", "bs4", "cryptography", "docx", "edge_tts", "gtts",
    "keyring", "litellm", "markdown", "openai", "PIL", "fitz",
    "pymupdf", "pyaudio", "playwright", "PyPDF2", "pyautogui",
    "pygame", "pytesseract", "send2trash", "speech_recognition",
    "truststore", "uiautomation", "windows_toasts", "win32com", "winrt",
):
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        pass

a = Analysis(
    [str(repo_root / "smarti_core_service.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt6", "smarti.app", "smarti.chat", "smarti.ui_pages", "smarti.workspace_ui", "smarti.visual_canvas"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="smarti-core",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="smarti-core")
