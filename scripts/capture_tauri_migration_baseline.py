"""Capture the legacy PyQt Workspace baseline used by migration Point 1.

The command uses an isolated Smarti data directory and writes generated QA
evidence below ``.codex-local/tauri-baseline`` by default.  It never reads or
changes the user's normal Smarti profile.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".codex-local/tauri-baseline"),
    )
    parser.add_argument("--idle-seconds", type=float, default=5.0)
    return parser.parse_args()


def _process_metrics() -> dict[str, int | float | None]:
    try:
        import psutil

        info = psutil.Process().memory_info()
        return {
            "working_set_bytes": int(info.rss),
            "private_bytes": int(getattr(info, "private", 0) or 0),
        }
    except Exception:
        return {"working_set_bytes": None, "private_bytes": None}


def _pump_events(app, seconds: float) -> None:
    deadline = time.perf_counter() + max(0.0, seconds)
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    args = _arguments()
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    output_dir = args.output_dir.resolve()
    data_dir = output_dir / "isolated-data"
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    os.environ["SMARTI_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    settings_path = data_dir / "smarti_settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "local_gateway_enabled": False,
                "check_updates_automatically": False,
                "ui_preferences": {
                    "theme_mode": "dark",
                    "workspace_start_maximized": False,
                    "workspace_sidebar_collapsed": False,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    started_at = time.perf_counter()
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from smarti.chat import ChatWindow
    from smarti.core import SmartiCore
    from smarti.ui_styles import apply_app_theme, app_font

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(app_font(10))

    core_started_at = time.perf_counter()
    core = SmartiCore()
    core_seconds = time.perf_counter() - core_started_at
    core.settings.setdefault("ui_preferences", {})["workspace_start_maximized"] = False
    core.settings["local_gateway_enabled"] = False
    apply_app_theme(app, settings=core.settings)

    window_started_at = time.perf_counter()
    window = ChatWindow(core)
    window.showNormal()
    window.resize(1180, 760)
    window.show()
    _pump_events(app, 1.0)
    window_seconds = time.perf_counter() - window_started_at
    ready_seconds = time.perf_counter() - started_at

    captures = [
        ("dark", "narrow", 720, 560),
        ("dark", "wide", 1440, 900),
        ("light", "narrow", 720, 560),
        ("light", "wide", 1440, 900),
    ]
    screenshot_records = []
    for theme, size_name, width, height in captures:
        core.settings.setdefault("ui_preferences", {})["theme_mode"] = theme
        window.apply_theme(theme)
        window.showNormal()
        window.resize(width, height)
        _pump_events(app, 0.35)
        path = output_dir / f"legacy-workspace-{theme}-{size_name}-{width}x{height}.png"
        if not window.grab().save(str(path), "PNG"):
            raise RuntimeError(f"Could not save screenshot: {path}")
        screenshot_records.append(
            {
                "theme": theme,
                "state": size_name,
                "logical_size": [width, height],
                "device_pixel_ratio": float(window.devicePixelRatioF()),
                "path": str(path),
                "size_bytes": path.stat().st_size,
            }
        )

    before_cpu = time.process_time()
    before_wall = time.perf_counter()
    _pump_events(app, args.idle_seconds)
    idle_wall = time.perf_counter() - before_wall
    idle_cpu = time.process_time() - before_cpu
    idle_cpu_percent_one_core = (idle_cpu / idle_wall * 100.0) if idle_wall else 0.0

    metrics = {
        "python": sys.version,
        "source_startup_to_workspace_ready_seconds": round(ready_seconds, 6),
        "core_initialization_seconds": round(core_seconds, 6),
        "chat_window_initialization_seconds": round(window_seconds, 6),
        "idle_sample_seconds": round(idle_wall, 6),
        "idle_process_cpu_percent_one_core": round(idle_cpu_percent_one_core, 4),
        **_process_metrics(),
        "screenshots": screenshot_records,
    }
    metrics_path = output_dir / "legacy-source-metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    window._quit_requested = True
    window.close()
    core.shutdown_runtime()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
