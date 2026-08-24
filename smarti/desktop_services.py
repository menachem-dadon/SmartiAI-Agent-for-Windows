"""Qt-free services exposed only through the authenticated desktop control plane."""
from __future__ import annotations

import copy
import base64
import hashlib
import json
import mimetypes
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .common import (
    APP_VERSION, MCP_TOOLS_DIR, TOOLS_DIR, UNIFIED_LOG_FILE, USER_DATA_DIR,
    redact_sensitive_text, unified_log_paths,
)
from .config import (
    BUILTIN_DYNAMIC_TOOLS, BUILTIN_TOOL_SCHEMAS, DEFAULT_SETTINGS,
    PUBLIC_BUILTIN_TOOLS, TOOL_CATEGORIES,
)


SETTING_GROUPS = (
    ("providers", "ספקים ומודלים", ("api_mode", "selected_", "local_", "codex_", "gemini", "openai", "anthropic", "deepseek", "groq", "mistral", "openrouter", "xai")),
    ("email", "דוא״ל", ("email_", "smtp_", "imap_")),
    ("security", "אבטחה וחיבורים", ("ssl_", "allow_insecure", "certificate", "autonomy", "permission", "sandbox", "approval", "trusted_")),
    ("appearance", "מראה ומרחב עבודה", ("theme", "language", "direction", "ui_", "workspace", "font", "window")),
    ("voice", "קול, הקראה והתראות", ("voice", "tts", "speech", "read_aloud", "notification", "hotkey")),
    ("browser", "דפדפן ואינטרנט", ("browser", "web_", "search_", "download", "profile")),
    ("context", "קבצים, הקשר ועלויות", ("attachment", "context", "token", "cost", "budget", "memory", "output")),
    ("extensions", "כלים והרחבות", ("tool", "mcp", "skill", "clawhub", "custom_")),
    ("updates", "עדכונים ומפתחים", ("update", "developer", "debug", "log", "trace")),
)

SETTING_LABELS = {
    "api_mode": "ספק המודל הפעיל", "autonomy_mode": "רמת האוטונומיה",
    "local_server_url": "כתובת שרת מודל מקומי", "local_fast_mode_enabled": "FastMode למודל מקומי",
    "read_aloud_all": "הקראת כל התשובות", "read_aloud_voice_only": "הקראה לאחר קלט קולי בלבד",
    "tts_voice_id": "קול להקראה", "tts_volume": "עוצמת הקראה", "voice_hotkey": "קיצור מקלדת לקול",
    "keep_running_in_tray": "המשך פעולה באזור ההתראות", "updates_auto_check": "בדיקה אוטומטית לעדכונים",
    "enable_browser_automation": "אוטומציה בדפדפן", "enable_computer_control": "שליטה בממשק Windows",
    "privacy_redact_logs": "הסתרת תוכן אישי בלוגים", "ssl_trust_mode": "מצב אמון SSL",
    "ssl_custom_ca_path": "קובץ תעודה מותאם", "allow_insecure_ssl_compat": "תאימות SSL לא מאובטחת (ישן)",
    "sandbox_enabled": "ארגז חול לקבצים", "sandbox_root_dir": "תיקיית שורש לארגז החול",
    "default_output_dir": "תיקיית תוצרים ברירת מחדל", "attachment_inline_max_mb": "גודל מרבי לקובץ מצורף",
    "max_concurrent_agents": "מספר סוכנים במקביל", "max_parallel_tool_calls": "מספר כלים במקביל",
    "enable_mcp_clawhub": "הפעלת MCP ו-ClawHub", "enable_skills_beta": "הפעלת Skills",
    "require_approval_for_cloud_upload": "דרוש אישור להעלאה לענן", "raw_shell_requires_approval": "דרוש אישור לפקודת Shell",
}

BUILTIN_TOOL_DISPLAY_LABELS = {
    "get_tool_info": "מידע על כלי וסכמות",
    "search_tools": "חיפוש כלים ויכולות",
    "system_manager": "ניהול מערכת",
    "software_manager": "ניהול תוכנות",
    "file_manager": "ניהול קבצים",
    "web_manager": "אינטרנט ואתרים",
    "screen_manager": "צילום וניתוח מסך",
    "background_task_manager": "משימות רקע",
    "notification_manager": "התראות ותזכורות",
    "memory_manager": "ניהול זיכרון",
    "email_manager": "ניהול דוא\"ל",
    "automation_manager": "אוטומציה בדפדפן ובמחשב",
    "extension_manager": "ניהול הרחבות, MCP ומיומנויות",
    "canvas_manager": "קנבס חזותי",
    "browser_automation_manager": "אוטומציית דפדפן",
    "computer_automation_manager": "אוטומציית מחשב",
    "document_manager": "יצירה ועריכת מסמכים",
    "create_python_tool": "יצירת כלי Python מותאם",
}

TOOL_CATEGORY_DISPLAY_LABELS = {
    "schema": "מידע ועזרה", "system": "מערכת", "software": "תוכנות",
    "files": "קבצים", "web": "אינטרנט", "screen": "מסך",
    "tasks": "משימות רקע", "memory": "זיכרון", "visual": "קנבס חזותי",
    "email": "דוא\"ל", "automation": "אוטומציה", "documents": "מסמכים",
    "extensions": "הרחבות", "developer": "מפתחים",
}

TOKEN_LABELS = {
    "selected": "מודל נבחר", "model": "מודל", "api": "API", "key": "מפתח", "email": "דוא״ל",
    "enabled": "מופעל", "enable": "הפעלת", "max": "מרבי", "timeout": "זמן המתנה", "seconds": "שניות",
    "minutes": "דקות", "hours": "שעות", "browser": "דפדפן", "memory": "זיכרון", "tool": "כלי",
    "tools": "כלים", "context": "הקשר", "output": "פלט", "directory": "תיקייה", "dir": "תיקייה",
    "allowed": "מורשה", "approval": "אישור", "require": "דרוש", "privacy": "פרטיות", "default": "ברירת מחדל",
}

_LOG_RECORD_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")
_PERSONAL_LOG_FIELDS = {"address", "args", "arguments", "body", "content", "details", "directory", "file", "files", "folder", "input", "instructions", "location", "memory", "message", "output", "path", "paths", "preview", "prompt", "query", "response", "stderr", "stdout", "text", "title", "url", "user_text", "value"}
_TECHNICAL_LOG_FIELDS = {"action", "allowed", "args_hash", "attempt", "category", "changed", "code", "count", "duration_ms", "enabled", "error_code", "error_status", "error_type", "event", "files_count", "http_status", "id", "kind", "manager", "method", "model", "name", "operation", "outcome", "provider", "request_id", "retry", "risk", "skill", "stage", "status", "status_code", "success", "tool", "type"}
_PERSONAL_KEY_VALUE_RE = re.compile(r"(?i)(\b(?:address|args|args_preview|arguments|body|content|details|directory|file|files|folder|input|instructions|location|memory|message|output|path|paths|preview|prompt|query|response|stderr|stdout|text|title|url|user_text|value)=).*?(?=\s+\|\s+[A-Za-z_][\w.-]*=|$)")


def _scrub_personal_json(value, key=""):
    normalized = str(key or "").casefold()
    if normalized in _PERSONAL_LOG_FIELDS:
        return "[HIDDEN PERSONAL CONTENT]"
    if isinstance(value, dict):
        return {item_key: _scrub_personal_json(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_personal_json(item, key) for item in value]
    if isinstance(value, str) and normalized and normalized not in _TECHNICAL_LOG_FIELDS:
        return "[HIDDEN PERSONAL CONTENT]"
    return value


def sanitize_desktop_log_lines(lines, settings=None):
    output, hiding = [], False
    for raw in lines or []:
        line = redact_sensitive_text(str(raw or ""), settings or {})
        starts_record = bool(_LOG_RECORD_PREFIX_RE.match(line))
        if hiding and not starts_record:
            if re.fullmatch(r"\s*=+\s*", line): hiding = False
            continue
        if starts_record: hiding = False
        if "PERSONAL |" in line:
            before, _, personal = line.partition("PERSONAL |")
            metadata = personal
            for marker in (" | content=", " | stdout=", " | stderr="): metadata = metadata.split(marker, 1)[0]
            output.append(f"{before}PERSONAL | {metadata.strip()} | [HIDDEN PERSONAL CONTENT]"); continue
        if "בקשת משתמש חדשה:" in line or "תשובת מודל גולמית:" in line:
            marker = "בקשת משתמש חדשה:" if "בקשת משתמש חדשה:" in line else "תשובת מודל גולמית:"
            output.append(line.split(marker, 1)[0] + marker + " [HIDDEN PERSONAL CONTENT]"); hiding = True; continue
        if "TRACE |" in line: line = re.sub(r"(TRACE\s*\|\s*[^|]+\|).*", r"\1 [HIDDEN PERSONAL CONTENT]", line, count=1)
        if "TOOL START" in line: line = re.sub(r"\s*\|\s*args=.*$", " | args=[HIDDEN PERSONAL CONTENT]", line)
        if "TOOL FINISH" in line: line = re.sub(r"\s*\|\s*preview=.*$", " | preview=[HIDDEN PERSONAL CONTENT]", line)
        if "API FAILURE" in line:
            line = re.sub(r"\s*\|\s*raw=.*$", " | raw=[HIDDEN PERSONAL CONTENT]", line)
            line = re.sub(r"message=.*?(?=\s\|\s|$)", "message=[HIDDEN PERSONAL CONTENT]", line)
        for marker in ("AUDIT |", "SKILL |"):
            if marker in line:
                prefix, payload = line.split(marker, 1)
                try: line = f"{prefix}{marker} {json.dumps(_scrub_personal_json(json.loads(payload.strip())), ensure_ascii=False, default=str)}"
                except Exception: line = f"{prefix}{marker} [PERSONAL PAYLOAD HIDDEN]"
                break
        output.append(_PERSONAL_KEY_VALUE_RE.sub(r"\1[HIDDEN PERSONAL CONTENT]", line))
    return output


def _setting_label(key):
    if key in SETTING_LABELS:
        return SETTING_LABELS[key]
    words = [TOKEN_LABELS.get(word, word) for word in key.split("_")]
    return " ".join(words)


def _setting_group(key: str) -> tuple[str, str]:
    lowered = key.lower()
    for group, label, prefixes in SETTING_GROUPS:
        if any(lowered.startswith(prefix) or prefix in lowered for prefix in prefixes):
            return group, label
    return "general", "כללי"


def settings_schema_document():
    groups = {"general": {"id": "general", "label": "כללי", "order": 0}}
    for order, (group, label, _prefixes) in enumerate(SETTING_GROUPS, start=1):
        groups[group] = {"id": group, "label": label, "order": order}
    fields = {}
    for key, default in DEFAULT_SETTINGS.items():
        group, group_label = _setting_group(key)
        fields[key] = {
            "key": key, "label": _setting_label(key), "group": group,
            "group_label": group_label, "type": type(default).__name__,
            "default": copy.deepcopy(default), "writable": key != "_runtime_trace",
            "restart_required": key in {"language", "ui_language", "update_channel"},
            "advanced": group in {"security", "updates"} or key.startswith(("mcp_", "debug_", "developer_")),
        }
    return {"groups": sorted(groups.values(), key=lambda item: item["order"]), "fields": fields}


def safe_task_rows(core):
    return [copy.deepcopy(item) for item in core.settings.get("background_tasks", [])][-100:][::-1]


def task_action(core, action, payload):
    task_id = str(payload.get("id") or "").strip()
    if action == "create":
        result = core.schedule_background_task(payload)
    elif action == "edit":
        result = core.edit_background_task(payload)
    elif action == "cancel":
        result = core.cancel_background_task(task_id)
    elif action in {"retry", "resume"}:
        result = core.retry_background_task(task_id, payload.get("delay_minutes", 0))
    elif action == "delete":
        task = core._get_background_task(task_id)
        if not task:
            result = f"ERROR: Task not found: {task_id}"
        elif task.get("status") in {"running", "cancelling"}:
            result = "ERROR: Running tasks must be cancelled before deletion."
        else:
            core.settings["background_tasks"] = [item for item in core.settings.get("background_tasks", []) if str(item.get("id")) != task_id]
            core.settings["background_jobs"] = core.settings["background_tasks"]
            core._save_settings()
            result = "SUCCESS: task deleted."
    else:
        raise ValueError("unknown_task_action")
    if str(result).startswith("ERROR"):
        raise ValueError(str(result))
    return {"message": str(result), "items": safe_task_rows(core)}


def memory_rows(core, query="", status="active", memory_type="any", *, category="", sensitivity="any",
                date_range="any", expiry="any", sort_by="updated_desc", page=1, page_size=8):
    manager = getattr(core, "memory_manager", None)
    if not manager:
        return {"items": [], "stats": {}, "available": False}
    try:
        page = max(1, int(page or 1))
        page_size = max(1, min(50, int(page_size or 8)))
    except (TypeError, ValueError):
        page, page_size = 1, 8
    rows = manager.list_entries(
        query=query, status=status, memory_type=memory_type, category=category,
        sensitivity=sensitivity, date_range=date_range, expiry=expiry,
        sort_by=sort_by, max_results=1000,
    )
    start = (page - 1) * page_size
    return {
        "items": rows[start:start + page_size], "total": len(rows), "page": page,
        "page_size": page_size, "pages": max(1, (len(rows) + page_size - 1) // page_size),
        "stats": manager.memory_stats(), "available": True,
    }


def memory_action(core, action, memory_id, payload):
    manager = getattr(core, "memory_manager", None)
    if not manager:
        raise ValueError("memory_manager_unavailable")
    if action == "details":
        return manager.get_entry(memory_id, reveal_sensitive=False, user_authorized=False)
    if action == "reveal":
        return manager.get_entry(memory_id, reveal_sensitive=True, user_authorized=True)
    if action == "edit":
        allowed = {key: payload[key] for key in ("subject", "content", "category", "sensitivity", "tags", "importance", "pinned", "memory_type", "ttl_hours") if key in payload}
        return manager.edit_entry(memory_id, user_authorized=True, **allowed)
    if action == "pin":
        return manager.edit_entry(memory_id, user_authorized=True, pinned=bool(payload.get("pinned")))
    if action == "archive":
        return {"changed": manager.archive_entry(memory_id, reason="desktop_user")}
    if action == "restore":
        return {"changed": manager.restore_entry(memory_id)}
    if action == "delete":
        return {"changed": manager.forget(memory_id)}
    raise ValueError("unknown_memory_action")


def tools_snapshot(core):
    builtins = []
    config = core.settings.get("tools_config", {}) or {}
    for name in PUBLIC_BUILTIN_TOOLS:
        if name not in BUILTIN_TOOL_SCHEMAS:
            continue
        schema = BUILTIN_TOOL_SCHEMAS[name]
        category = TOOL_CATEGORIES.get(name, "developer")
        builtins.append({
            "name": name,
            "label": BUILTIN_TOOL_DISPLAY_LABELS.get(name, name.replace("_", " ")),
            "description": str(schema.get("description") or BUILTIN_DYNAMIC_TOOLS.get(name) or ""),
            "category": category,
            "category_label": TOOL_CATEGORY_DISPLAY_LABELS.get(category, category),
            "enabled": bool(config.get(name, True)),
        })
    external = []
    registry = getattr(core, "tool_registry", None)
    for kind, directory, suffix, setting_prefix in (
        ("custom", TOOLS_DIR, ".pyw", ""),
        ("mcp", MCP_TOOLS_DIR, ".txt", "mcp_"),
    ):
        names = []
        try:
            names = sorted(item[:-len(suffix)] for item in os.listdir(directory) if item.endswith(suffix))
        except OSError:
            pass
        for name in names:
            trust = registry.trust_status(kind, name) if registry else "trusted"
            enabled = bool(config.get(f"{setting_prefix}{name}", True)) and trust == "trusted"
            external.append({
                "kind": kind, "name": name, "label": name, "enabled": enabled,
                "trust": trust,
                "removable": True,
            })
    skills = getattr(core, "skill_registry", None)
    if not isinstance(skills, dict):
        loader = getattr(core, "_load_skill_registry", None)
        skills = loader() if callable(loader) else {}
    skills_config = core.settings.get("skills_config", {}) or {}
    skill_enabled = getattr(core, "_skill_enabled", None)
    for name, raw_spec in sorted((skills or {}).items()):
        spec = raw_spec if isinstance(raw_spec, dict) else {}
        source = str(spec.get("source") or "local")
        enabled = bool(skill_enabled(name)) if callable(skill_enabled) else bool(skills_config.get(name, True))
        external.append({
            "kind": "skill", "name": name, "label": name,
            "description": str(spec.get("description") or ""), "source": source,
            "source_label": {"builtin": "מובנה", "local": "הותקן ידנית", "clawhub": "ClawHub"}.get(source, "הותקן ידנית"),
            "enabled": enabled,
            "trust": registry.trust_status("skill", name) if registry else ("trusted" if enabled else "disabled"),
            "removable": source != "builtin",
        })
    return {"builtins": builtins, "extensions": external}


def usage_snapshot(core, timeframe="all"):
    from .common import USAGE_FILE
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        raw = {}
    normalized = str(timeframe or "all").lower()
    cutoff = {
        "today": datetime.now().date(), "week": (datetime.now() - timedelta(days=6)).date(),
        "month": (datetime.now() - timedelta(days=29)).date(),
    }.get(normalized)
    totals = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0, "cache_write_tokens": 0, "cost_usd": 0.0}
    models = {}
    for date, rows in raw.items() if isinstance(raw, dict) else []:
        if not isinstance(rows, dict):
            continue
        if cutoff:
            try:
                if datetime.fromisoformat(str(date)).date() < cutoff:
                    continue
            except ValueError:
                continue
        for model, item in rows.items():
            if not isinstance(item, dict):
                continue
            target = models.setdefault(model, {"model": model, **{key: 0 for key in totals}})
            for key in totals:
                value = float(item.get(key, item.get("estimated_cost_usd", 0) if key == "cost_usd" else 0) or 0)
                totals[key] += value
                target[key] += value
    total_tokens = sum(totals[key] for key in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens"))
    for item in models.values():
        item["tokens"] = sum(item[key] for key in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens"))
    return {
        "timeframe": normalized, "total_tokens": int(total_tokens), **totals,
        "models": sorted(models.values(), key=lambda row: row["tokens"], reverse=True),
        "memory": getattr(getattr(core, "memory_manager", None), "memory_stats", lambda: {})(),
    }


def clear_usage(core):
    from .common import USAGE_FILE
    backup = ""
    if os.path.exists(USAGE_FILE):
        backup = f"{USAGE_FILE}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        import shutil
        shutil.copy2(USAGE_FILE, backup)
    os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
    with open(USAGE_FILE, "w", encoding="utf-8") as handle:
        json.dump({}, handle)
    return {"cleared": True, "backup_path": backup, **usage_snapshot(core, "all")}


def test_email_settings(settings):
    """Test IMAP and SMTP login without reading or sending a message."""
    from .email_service import test_email_connection
    cfg = {
        "user": str(settings.get("email_address") or "").strip(),
        "password": str(settings.get("email_password") or ""),
        "imap_host": str(settings.get("email_imap_host") or "").strip(),
        "imap_port": int(settings.get("email_imap_port") or 993),
        "imap_ssl": bool(settings.get("email_imap_ssl", True)),
        "smtp_host": str(settings.get("email_smtp_host") or "").strip(),
        "smtp_port": int(settings.get("email_smtp_port") or 587),
        "smtp_ssl": bool(settings.get("email_smtp_ssl", False)),
        "smtp_starttls": bool(settings.get("email_smtp_starttls", True)),
    }
    if not cfg["user"] or not cfg["password"] or not cfg["imap_host"] or not cfg["smtp_host"]:
        return False, "חסרים כתובת אימייל, סיסמת אפליקציה או פרטי השרתים."
    return test_email_connection(cfg, settings)


def log_snapshot(limit=500, redact_personal=True):
    try:
        requested = int(limit)
    except (TypeError, ValueError):
        requested = 500
    bounded = min(20_000, max(1, requested)) if requested > 0 else 0
    lines = []
    try:
        for path in unified_log_paths():
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines.extend(handle.read().splitlines())
    except OSError:
        lines = []
    if bounded:
        lines = lines[-bounded:]
    if redact_personal:
        lines = sanitize_desktop_log_lines(lines)
    return {"lines": lines, "path": UNIFIED_LOG_FILE, "personal_content_hidden": bool(redact_personal)}


class WorkspaceScope:
    TEXT_LIMIT = 2 * 1024 * 1024
    BINARY_LIMIT = 25 * 1024 * 1024

    def __init__(self, core):
        self.core = core
        self._lock = threading.RLock()
        self._root = ""

    def _default_root(self):
        candidate = self.core._sandbox_root() if self.core._sandbox_enabled() else self.core._default_output_dir()
        return os.path.realpath(os.path.abspath(os.path.expanduser(str(candidate))))

    def set_root(self, path):
        root = os.path.realpath(os.path.abspath(os.path.expanduser(str(path or ""))))
        if not os.path.isdir(root):
            raise ValueError("workspace_root_not_found")
        if self.core._sandbox_enabled():
            sandbox = os.path.realpath(os.path.abspath(os.path.expanduser(str(self.core._sandbox_root()))))
            try:
                inside_sandbox = os.path.commonpath([sandbox, root]) == sandbox
            except ValueError:
                inside_sandbox = False
            if not inside_sandbox:
                raise ValueError("workspace_root_outside_sandbox")
        with self._lock:
            self._root = root
        preferences = copy.deepcopy(self.core.settings.get("ui_preferences", {}))
        preferences["tauri_workspace_root"] = root
        self.core.settings["ui_preferences"] = preferences
        self.core._save_settings()
        return self.root_info()

    def root(self):
        configured = str((self.core.settings.get("ui_preferences", {}) or {}).get("tauri_workspace_root") or "")
        candidate = self._root or configured or self._default_root()
        root = os.path.realpath(os.path.abspath(os.path.expanduser(candidate)))
        if self.core._sandbox_enabled():
            sandbox = os.path.realpath(os.path.abspath(os.path.expanduser(str(self.core._sandbox_root()))))
            try:
                inside_sandbox = os.path.commonpath([sandbox, root]) == sandbox
            except ValueError:
                inside_sandbox = False
            if not inside_sandbox:
                root = sandbox
        if not os.path.isdir(root):
            os.makedirs(root, exist_ok=True)
        return root

    def root_info(self):
        root = self.root()
        return {"name": os.path.basename(root.rstrip("\\/")) or "Smarti", "path": root}

    def resolve(self, relative=""):
        root = self.root()
        candidate = os.path.realpath(os.path.abspath(os.path.join(root, str(relative or ""))))
        try:
            inside = os.path.commonpath([root, candidate]) == root
        except ValueError:
            inside = False
        if not inside:
            raise ValueError("workspace_path_outside_root")
        return root, candidate

    def tree(self, relative="", depth=2):
        root, start = self.resolve(relative)
        if not os.path.isdir(start):
            raise ValueError("workspace_directory_not_found")
        depth = max(0, min(4, int(depth or 2)))
        def visit(path, remaining):
            rows = []
            try:
                entries = sorted(os.scandir(path), key=lambda item: (not item.is_dir(follow_symlinks=False), item.name.lower()))
            except OSError:
                return rows
            for entry in entries[:500]:
                full = entry.path
                if entry.is_symlink() or bool(getattr(os.path, "isjunction", lambda _path: False)(full)):
                    continue
                relative_path = os.path.relpath(full, root).replace("\\", "/")
                is_dir = entry.is_dir(follow_symlinks=False)
                item = {"name": entry.name, "path": relative_path, "kind": "directory" if is_dir else "file"}
                if not is_dir:
                    try: item["size"] = entry.stat(follow_symlinks=False).st_size
                    except OSError: item["size"] = 0
                elif remaining > 0:
                    item["children"] = visit(full, remaining - 1)
                rows.append(item)
            return rows
        return {"root": self.root_info(), "items": visit(start, depth)}

    def file(self, relative):
        root, path = self.resolve(relative)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError("workspace_file_not_found")
        size = os.path.getsize(path)
        suffix = Path(path).suffix.lower()
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        kind = "unknown"
        if mime.startswith("text/") or suffix in {".md", ".json", ".py", ".ts", ".tsx", ".js", ".css", ".html", ".xml", ".yaml", ".yml", ".csv", ".log"}: kind = "markdown" if suffix == ".md" else "text"
        elif mime.startswith("image/"): kind = "image"
        elif mime.startswith(("audio/", "video/")): kind = "media"
        elif suffix == ".pdf": kind = "pdf"
        elif suffix in {".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx"}: kind = "office"
        result = {"name": os.path.basename(path), "path": os.path.relpath(path, root).replace("\\", "/"), "kind": kind, "mime_type": mime, "size": size}
        if kind in {"text", "markdown"}:
            if size > self.TEXT_LIMIT: raise ValueError("workspace_text_file_too_large")
            with open(path, "r", encoding="utf-8", errors="replace") as handle: result["text"] = handle.read(self.TEXT_LIMIT + 1)
        elif kind == "office":
            path = self._office_to_pdf(path)
            size, mime, kind = os.path.getsize(path), "application/pdf", "pdf"
            result.update({"kind": kind, "mime_type": mime, "size": size, "converted_from": suffix})
            if size <= 8 * 1024 * 1024:
                with open(path, "rb") as handle:
                    result["data_url"] = f"data:{mime};base64,{base64.b64encode(handle.read()).decode('ascii')}"
        elif size > self.BINARY_LIMIT:
            raise ValueError("workspace_binary_file_too_large")
        else:
            result["handle"] = hashlib.sha256(path.encode("utf-8")).hexdigest()[:24]
            if size <= 8 * 1024 * 1024 and kind in {"image", "media", "pdf"}:
                with open(path, "rb") as handle:
                    result["data_url"] = f"data:{mime};base64,{base64.b64encode(handle.read()).decode('ascii')}"
        return result

    def _office_to_pdf(self, source):
        cache = os.path.join(USER_DATA_DIR, "workbench-preview")
        os.makedirs(cache, exist_ok=True)
        stamp = f"{os.path.getmtime(source):.0f}-{os.path.getsize(source)}"
        target = os.path.join(cache, f"{hashlib.sha256((source + stamp).encode('utf-8')).hexdigest()[:24]}.pdf")
        if os.path.isfile(target):
            return target
        try:
            import pythoncom
            import win32com.client
        except Exception as exc:
            raise ValueError("office_preview_runtime_unavailable") from exc
        pythoncom.CoInitialize()
        app = document = None
        try:
            suffix = Path(source).suffix.lower()
            if suffix in {".doc", ".docx"}:
                app = win32com.client.DispatchEx("Word.Application"); app.Visible = False
                document = app.Documents.Open(source, ReadOnly=True, AddToRecentFiles=False)
                document.ExportAsFixedFormat(target, 17)
            elif suffix in {".xls", ".xlsx", ".xlsm"}:
                app = win32com.client.DispatchEx("Excel.Application"); app.Visible = False; app.DisplayAlerts = False
                document = app.Workbooks.Open(source, UpdateLinks=0, ReadOnly=True)
                document.ExportAsFixedFormat(0, target)
            else:
                app = win32com.client.DispatchEx("PowerPoint.Application")
                document = app.Presentations.Open(source, ReadOnly=True, Untitled=False, WithWindow=False)
                document.SaveAs(target, 32)
            return target
        except Exception as exc:
            raise ValueError("office_preview_conversion_failed") from exc
        finally:
            try:
                if document is not None: document.Close(False)
            except Exception: pass
            try:
                if app is not None: app.Quit()
            except Exception: pass
            pythoncom.CoUninitialize()

    def open_external(self, relative):
        _root, path = self.resolve(relative)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError("workspace_file_not_found")
        os.startfile(path)
        return {"opened": True, "path": os.path.relpath(path, self.root()).replace("\\", "/")}

    def artifacts(self):
        root = self.root()
        rows = []
        for directory, names, files in os.walk(root):
            names[:] = [name for name in names if not os.path.islink(os.path.join(directory, name))][:50]
            for name in files[:500]:
                path = os.path.join(directory, name)
                try:
                    stat = os.stat(path, follow_symlinks=False)
                    rows.append({"name": name, "path": os.path.relpath(path, root).replace("\\", "/"), "size": stat.st_size, "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")})
                except OSError:
                    pass
            if len(rows) >= 500: break
        rows.sort(key=lambda item: item["modified_at"], reverse=True)
        return {"items": rows[:200], "root": self.root_info()}


class TerminalRegistry:
    def __init__(self, workspace):
        self.workspace = workspace
        self._lock = threading.RLock()
        self._sessions = {}

    def create(self):
        identifier = uuid.uuid4().hex[:12]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(["powershell.exe", "-NoLogo", "-NoProfile", "-NoExit", "-Command", "-"], cwd=self.workspace.root(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=creationflags)
        process.stdin.write("$utf8 = [Text.UTF8Encoding]::new($false); [Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8\n")
        process.stdin.flush()
        record = {"id": identifier, "process": process, "queue": queue.Queue(), "created_at": time.time(), "closed": False, "cwd": self.workspace.root()}
        def reader():
            for line in process.stdout:
                record["queue"].put(line)
            record["closed"] = True
        threading.Thread(target=reader, daemon=True, name=f"SmartiTerminal-{identifier}").start()
        with self._lock: self._sessions[identifier] = record
        return self.public(record)

    @staticmethod
    def public(record):
        process = record["process"]
        return {"id": record["id"], "running": process.poll() is None, "exit_code": process.poll(), "cwd": record["cwd"]}

    def _get(self, identifier):
        with self._lock: record = self._sessions.get(str(identifier or ""))
        if not record: raise ValueError("terminal_session_not_found")
        return record

    def write(self, identifier, text):
        record = self._get(identifier)
        if record["process"].poll() is not None: raise ValueError("terminal_session_exited")
        record["process"].stdin.write(str(text or "") + "\n")
        record["process"].stdin.flush()
        return self.read(identifier)

    def read(self, identifier):
        record = self._get(identifier); output = []
        while len(output) < 500:
            try: output.append(record["queue"].get_nowait())
            except queue.Empty: break
        return {**self.public(record), "output": "".join(output)}

    def close(self, identifier):
        record = self._get(identifier); process = record["process"]
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=1.5)
            except subprocess.TimeoutExpired: process.kill()
        with self._lock: self._sessions.pop(record["id"], None)
        return {"id": record["id"], "closed": True}

    def close_all(self):
        with self._lock: identifiers = list(self._sessions)
        for identifier in identifiers:
            try: self.close(identifier)
            except Exception: pass
