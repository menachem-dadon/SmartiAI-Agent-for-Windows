"""Crash-isolated health check for the optional Qt WebEngine runtime."""
from __future__ import annotations

import os
import json
import importlib.metadata
import subprocess
import sys
import threading
import time
from pathlib import Path


_HEALTH_LOCK = threading.Lock()
_HEALTH_RESULT = None


def _runtime_key():
    def version(name):
        try:
            return importlib.metadata.version(name)
        except Exception:
            return "missing"
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "pyqt": version("PyQt6"),
        "webengine": version("PyQt6-WebEngine"),
    }


def _health_cache_path():
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SmartiAI"
    return root / "webengine-health.json"


def _read_cached_health():
    try:
        payload = json.loads(_health_cache_path().read_text(encoding="utf-8"))
        if payload.get("runtime") != _runtime_key():
            return None
        if time.time() - float(payload.get("checked_at") or 0) > 30 * 24 * 60 * 60:
            return None
        return bool(payload.get("healthy"))
    except Exception:
        return None


def _write_cached_health(healthy):
    try:
        path = _health_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"runtime": _runtime_key(), "healthy": bool(healthy), "checked_at": time.time()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def run_probe():
    """Initialize a real profile in this process; intended for a child process."""
    try:
        from .visual_canvas import prepare_webengine_runtime

        if not prepare_webengine_runtime():
            return 2
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        app = QApplication.instance() or QApplication([])
        app.setApplicationName("SmartiAI WebEngine Probe")
        view = QWebEngineView()
        profile = view.page().profile()
        if profile is None:
            return 3
        app.processEvents()
        view.deleteLater()
        app.processEvents()
        return 0
    except Exception:
        return 4


def cached_webengine_runtime_health():
    return _HEALTH_RESULT


def probe_webengine_runtime(timeout=6, force=False):
    """Return runtime health without allowing a Chromium crash to kill Smarti."""
    global _HEALTH_RESULT
    with _HEALTH_LOCK:
        if _HEALTH_RESULT is not None and not force:
            return bool(_HEALTH_RESULT)
        if not force:
            cached = _read_cached_health()
            if cached is not None:
                _HEALTH_RESULT = bool(cached)
                return bool(_HEALTH_RESULT)
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--smarti-webengine-probe"]
        else:
            command = [sys.executable, "-m", "smarti.webengine_probe"]
        env = os.environ.copy()
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(3, int(timeout)),
                env=env,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            _HEALTH_RESULT = completed.returncode == 0
        except Exception:
            _HEALTH_RESULT = False
        _write_cached_health(_HEALTH_RESULT)
        return bool(_HEALTH_RESULT)


if __name__ == "__main__":
    raise SystemExit(run_probe())
