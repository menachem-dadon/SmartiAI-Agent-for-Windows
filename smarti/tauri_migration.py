"""One-time, backed-up migration from the legacy desktop installation.

This module is deliberately Qt-free.  It never points WebView2 at the old
Chromium directory and never removes user data or the old installation.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

from .browser_profile import BrowserProfileSource, import_profile_data


MIGRATION_VERSION = 1
MIGRATION_FILE = "point16-legacy-migration.json"
IMPORT_FILE = "legacy-browser-import.json"


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _copy_browser_backup(source_root: Path, backup_root: Path) -> list[str]:
    copied: list[str] = []
    candidates = (
        "Local State", "Default/History", "Default/Bookmarks",
        "Default/Preferences", "Default/Network/Cookies",
    )
    for relative in candidates:
        source = source_root / Path(relative)
        if not source.is_file():
            continue
        destination = backup_root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative.replace("\\", "/"))
    return copied


def prepare_legacy_tauri_migration(user_data_dir: str, local_app_data: str | None = None) -> dict:
    """Prepare an idempotent import payload and a recoverable source backup."""
    data_root = Path(user_data_dir).resolve()
    migration_root = data_root / "migration"
    state_path = migration_root / MIGRATION_FILE
    if state_path.is_file():
        try:
            existing = json.loads(state_path.read_text(encoding="utf-8"))
            if int(existing.get("version") or 0) == MIGRATION_VERSION:
                return existing
        except Exception:
            pass

    local = Path(local_app_data or os.environ.get("LOCALAPPDATA") or data_root)
    source_root = local / "SmartiChromeProfile"
    source_profile = source_root / "Default"
    now = datetime.now(timezone.utc)
    state = {
        "version": MIGRATION_VERSION,
        "status": "no_source",
        "prepared_at": now.isoformat(),
        "source": str(source_root),
        "backup": "",
        "copied": [],
        "import_file": "",
    }
    if not source_profile.is_dir():
        _atomic_json(state_path, state)
        return state

    backup_root = migration_root / "backups" / now.strftime("%Y%m%dT%H%M%SZ") / "SmartiChromeProfile"
    copied = _copy_browser_backup(source_root, backup_root)
    source = BrowserProfileSource(
        browser_id="smarti_legacy",
        browser_name="Smarti Browser הישן",
        profile_name="ברירת מחדל",
        user_data_dir=str(source_root),
        profile_dir=str(source_profile),
    )
    imported = import_profile_data(
        source, include_cookies=True, include_history=True, include_bookmarks=True,
    )
    import_path = migration_root / IMPORT_FILE
    _atomic_json(import_path, imported)
    state.update({
        "status": "prepared",
        "backup": str(backup_root),
        "copied": copied,
        "import_file": str(import_path),
        "counts": {
            "history": len(imported.get("history") or []),
            "bookmarks": len(imported.get("bookmarks") or []),
            "cookies": len(imported.get("cookies") or []),
        },
    })
    _atomic_json(state_path, state)
    return state


def legacy_browser_migration_payload(user_data_dir: str) -> dict:
    migration_root = Path(user_data_dir).resolve() / "migration"
    state_path = migration_root / MIGRATION_FILE
    if not state_path.is_file():
        return {"status": "not_prepared"}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("status") != "prepared":
        return state
    import_path = Path(str(state.get("import_file") or migration_root / IMPORT_FILE))
    payload = json.loads(import_path.read_text(encoding="utf-8")) if import_path.is_file() else {}
    return {**state, **payload}


def mark_legacy_browser_migration_applied(user_data_dir: str) -> dict:
    migration_root = Path(user_data_dir).resolve() / "migration"
    state_path = migration_root / MIGRATION_FILE
    if not state_path.is_file():
        return {"status": "not_prepared"}
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    persisted["status"] = "applied"
    persisted["applied_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(state_path, persisted)
    return persisted
