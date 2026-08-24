"""Read-only health diagnostics and explicitly approved repairs for SmartiAI.

Smarti Diagnostic deliberately keeps diagnosis separate from repair.  A scan may make
short, local connectivity checks when the user asks for a full scan, but it
never changes settings, deletes profiles, or restores data by itself.
"""
from __future__ import annotations

import glob
import importlib.util
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable, Optional

from .common import (
    ACTIVE_TASK_CHECKPOINT_FILE,
    APP_DIR,
    ATTACHMENTS_DIR,
    AUDIT_LOG_FILE,
    CHAT_HISTORY_DB_FILE,
    CHAT_HISTORY_FILE,
    EDGE_TTS_INSTALLED,
    GTTS_INSTALLED,
    KEYBOARD_INSTALLED,
    MCP_CONFIG_FILE,
    MCP_TOOLS_DIR,
    MEMORY_FILE,
    OUTPUTS_DIR,
    SECRET_PREFIX,
    SETTINGS_FILE,
    SENSITIVE_SETTING_KEYS,
    SKILLS_DIR,
    SMARTI_BROWSER_DEBUG_PORT,
    SPEECH_INSTALLED,
    TTS_INSTALLED,
    TOOLS_DIR,
    USAGE_FILE,
    USER_DATA_DIR,
    UNIFIED_LOG_FILE,
    SSL_MODE_CUSTOM_CA,
    SSL_MODE_LEGACY_INSECURE,
    SSL_MODE_SYSTEM,
    fetch_text_models_for_provider,
    normalize_ssl_trust_mode,
    normalize_provider_name,
    provider_config,
    provider_default_model,
    provider_display_name,
    provider_requires_api_key,
    provider_secret_key,
    validate_custom_ca,
)
from .codex_signin import CODEX_SIGNIN_PROVIDER, CodexSignInProvider
from .config import BUILTIN_TOOL_SCHEMAS, DEFAULT_POLICY_MATRIX, SETTINGS_SCHEMA_VERSION
from .runtime import SMARTI_RUNTIME
from .canvas_model import new_canvas_artifact, web_canvas_available
from .email_service import test_email_connection


STATUS_PASS = "pass"
STATUS_WARNING = "warning"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"


@dataclass(frozen=True)
class RepairAction:
    """One safe, named repair proposal attached to a finding."""

    id: str
    title_he: str
    description_he: str
    risk: str = "medium"


@dataclass(frozen=True)
class CheckResult:
    """Structured diagnostic result, matching the product-plan contract."""

    id: str
    status: str
    explanation_he: str
    technical_detail: str
    repair_action: Optional[RepairAction] = None
    category: str = "system"
    title_he: str = "בדיקה"

    def to_dict(self):
        data = asdict(self)
        return data


class SmartiDiagnostic:
    """Runs bounded diagnostics against the active SmartiCore instance."""

    LOG_FILENAME = os.path.basename(UNIFIED_LOG_FILE)
    _SECRET_VALUE_RE = re.compile(
        r"(?i)(api[_ -]?key|token|password|secret|authorization)\s*[:=]\s*([^\s,;]+)"
    )
    _BEARER_RE = re.compile(r"(?i)bearer\s+[^\s,;]+")
    _URL_CREDENTIAL_RE = re.compile(r"(https?://)([^/@\s]+)@")

    def __init__(self, core):
        self.core = core
        self.log_path = AUDIT_LOG_FILE
        self._cancel_event = threading.Event()

    def request_stop(self):
        self._cancel_event.set()

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")

    def _redact(self, value):
        text = str(value or "")
        for key in SENSITIVE_SETTING_KEYS:
            raw = str(getattr(self.core, "settings", {}).get(key, "") or "")
            if raw and len(raw) >= 4:
                text = text.replace(raw, "[REDACTED]")
        text = self._SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
        text = self._BEARER_RE.sub("Bearer [REDACTED]", text)
        text = self._URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", text)
        return text[:4_000]

    def _log(self, result):
        try:
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            payload = {
                "at": self._now(),
                "id": result.id,
                "status": result.status,
                "category": result.category,
                "detail": self._redact(result.technical_detail),
            }
            line = json.dumps(payload, ensure_ascii=False)
            if os.path.abspath(self.log_path) == os.path.abspath(UNIFIED_LOG_FILE):
                logging.info("DIAGNOSTIC | %s", line)
            else:
                with open(self.log_path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except Exception:
            # A broken log must never make a repair diagnosis fail.
            logging.exception("Diagnostic result logging failed for id=%s", result.id)

    def _result(self, *args, **kwargs):
        if len(args) >= 4:
            args = list(args)
            args[3] = self._redact(args[3])
        elif "technical_detail" in kwargs:
            kwargs["technical_detail"] = self._redact(kwargs["technical_detail"])
        result = CheckResult(*args, **kwargs)
        self._log(result)
        return result

    def _cancelled(self):
        return self._cancel_event.is_set()

    def _run_check(self, check):
        if self._cancelled():
            return self._result(
                f"{check.__name__}.cancelled", STATUS_SKIPPED,
                "הבדיקה הופסקה לבקשתך.", "Cancelled by user before this check ran.",
                category="system", title_he="בדיקה שהופסקה",
            )
        try:
            return check()
        except Exception as exc:
            self._log(
                CheckResult(
                    f"{check.__name__}.unexpected",
                    "internal_error",
                    "",
                    f"Unexpected diagnostic check failure: {type(exc).__name__}: {self._redact(exc)}",
                    category="system",
                    title_he="internal diagnostic exception",
                )
            )
            return None

    def run(
        self,
        include_network=False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        result_callback: Optional[Callable[[CheckResult], None]] = None,
    ):
        """Run local checks, and optional explicit network checks, in a stable order."""
        checks = [
            ("סביבת ההרצה ותיקיית הנתונים", self.check_runtime_and_data_dir),
            ("תקינות סביבת Python של Smarti", self.check_runtime_environment),
            ("קובצי נתונים וגיבויים", self.check_data_files),
            ("מבנה הגדרות והעברת גרסה", self.check_settings_schema),
            ("זיכרון מקומי ותוקף מידע", self.check_memory_health),
            ("אחסון קבצים ותוצרים", self.check_storage),
            ("ספק המודל הפעיל", lambda: self.check_provider(include_network)),
            ("חיפוש אינטרנט וקבצים", self.check_search),
            ("דפדפן האוטומציה", lambda: self.check_browser(include_network)),
            ("אוטומציית מחשב", self.check_computer_control),
            ("דוא\"ל", lambda: self.check_email(include_network)),
            ("קנבס ורכיבים חזותיים", self.check_canvas),
            ("קול והקראה", self.check_voice),
            ("סביבת Node.js ו־MCP", self.check_mcp_node_runtime),
            ("קטלוג חבילות MCP", self.check_mcp_catalog),
            ("כלים מותאמים", self.check_custom_tools),
            ("Skills ותלויות", self.check_skill_dependencies),
            ("מדיניות בחירת כלים ו-Skills", self.check_tool_catalog_policy),
            ("משימות רקע והתאוששות", self.check_background_tasks),
            ("שמירת סודות", self.check_secret_storage),
            ("מדיניות ואבטחה", self.check_security),
        ]
        results = []
        total = len(checks)
        for index, (label, check) in enumerate(checks, start=1):
            if progress_callback:
                progress_callback(index, total, label)
            result = self._run_check(check)
            if result is None:
                continue
            results.append(result)
            if result_callback:
                result_callback(result)
            if self._cancelled():
                break
        return results

    def check_runtime_and_data_dir(self):
        issues = []
        if not os.path.isdir(USER_DATA_DIR):
            return self._result(
                "data.user_data_dir", STATUS_ERROR,
                "תיקיית הנתונים של Smarti אינה זמינה, ולכן אי אפשר לשמור הגדרות ושיחות בבטחה.",
                f"Missing user data directory: {USER_DATA_DIR}",
                RepairAction("create_data_dir", "יצירת תיקיית נתונים", "תיווצר רק תיקיית הנתונים החסרה של Smarti.", "low"),
                category="data", title_he="תיקיית נתונים",
            )
        try:
            fd, probe_path = tempfile.mkstemp(prefix=".smarti_diagnostic_", suffix=".tmp", dir=USER_DATA_DIR)
            os.close(fd)
            os.remove(probe_path)
        except Exception as exc:
            return self._result(
                "data.user_data_dir", STATUS_ERROR,
                "אין ל‑Smarti הרשאת כתיבה תקינה לתיקיית הנתונים. שמירה, גיבוי ועדכון מצב עלולים להיכשל.",
                f"Write probe failed in {USER_DATA_DIR}: {type(exc).__name__}: {self._redact(exc)}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "בדקי הרשאות Windows, שטח פנוי או סנכרון ענן בתיקייה הזאת.", "low"),
                category="data", title_he="תיקיית נתונים",
            )
        python_version = ".".join(map(str, __import__("sys").version_info[:3]))
        if not os.path.isdir(APP_DIR):
            issues.append("תיקיית היישום אינה מזוהה")
        explanation = "סביבת ההרצה ותיקיית הנתונים זמינות לכתיבה."
        status = STATUS_PASS if not issues else STATUS_WARNING
        if issues:
            explanation = "תיקיית הנתונים זמינה, אבל נמצאה חריגה בסביבת ההרצה."
        return self._result(
            "data.user_data_dir", status, explanation,
            f"Python {python_version}; data_dir writable; app_dir_exists={os.path.isdir(APP_DIR)}; " + "; ".join(issues),
            category="data", title_he="תיקיית נתונים",
        )

    def check_runtime_environment(self):
        """Verify the Python executable Smarti would actually use, without installing anything."""
        try:
            python_exe = str(SMARTI_RUNTIME.python_executable(prefer_console=True) or "").strip()
        except Exception as exc:
            python_exe = ""
            resolution_error = f"{type(exc).__name__}: {self._redact(exc)}"
        else:
            resolution_error = ""
        resolved = python_exe if python_exe and os.path.exists(python_exe) else (shutil.which(python_exe) if python_exe else None)
        if not resolved:
            return self._result(
                "runtime.python", STATUS_ERROR,
                "המערכת לא מצאה את Python שבו Smarti אמור להשתמש, ולכן כלים מקומיים עלולים לא לפעול.",
                f"python_executable={python_exe or '<empty>'}; resolved=false; {resolution_error}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "בדקי את יומן ההתקנה או הפעילי מחדש את מתקין Smarti; Diagnostic לא מוריד או מחליף רכיבי הרצה בעצמו.", "low"),
                category="system", title_he="סביבת Python של Smarti",
            )
        try:
            completed = subprocess.run(
                [resolved, "--version"], capture_output=True, text=True, timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            version = (completed.stdout or completed.stderr or "").strip()
            if completed.returncode != 0:
                raise RuntimeError(f"exit={completed.returncode}")
        except Exception as exc:
            return self._result(
                "runtime.python", STATUS_ERROR,
                "נמצא Python עבור Smarti, אך הוא לא הגיב לבדיקת ההרצה. כלים מקומיים עלולים להיכשל.",
                f"python_executable={resolved}; probe={type(exc).__name__}: {self._redact(exc)}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "הפעילי מחדש את Smarti. אם הבעיה נשארת, הריצי תיקון התקנה; Diagnostic לא משנה את סביבת ההרצה אוטומטית.", "low"),
                category="system", title_he="סביבת Python של Smarti",
            )
        return self._result(
            "runtime.python", STATUS_PASS,
            "סביבת Python שבה Smarti משתמש זמינה ומגיבה.",
            f"python_executable={resolved}; version={version or 'unknown'}; frozen={bool(getattr(SMARTI_RUNTIME, 'is_frozen', False))}",
            category="system", title_he="סביבת Python של Smarti",
        )

    def check_data_files(self):
        expected = {
            SETTINGS_FILE: dict,
            MEMORY_FILE: dict,
            USAGE_FILE: dict,
            ACTIVE_TASK_CHECKPOINT_FILE: dict,
            MCP_CONFIG_FILE: dict,
        }
        valid, missing, invalid = [], [], []
        for path, expected_type in expected.items():
            label = os.path.basename(path)
            if not os.path.exists(path):
                missing.append(label)
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if not isinstance(payload, expected_type):
                    raise ValueError(f"root is {type(payload).__name__}, expected {expected_type.__name__}")
                valid.append(label)
            except Exception as exc:
                invalid.append(f"{label}: {type(exc).__name__}")

        chat_db = CHAT_HISTORY_DB_FILE
        if os.path.exists(chat_db):
            try:
                with closing(sqlite3.connect(chat_db, timeout=5.0)) as connection:
                    quick_check = connection.execute("PRAGMA quick_check").fetchone()
                    tables = {
                        row[0]
                        for row in connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
                if not quick_check or quick_check[0] != "ok" or not {"sessions", "messages"} <= tables:
                    raise ValueError("SQLite chat store failed integrity/schema validation")
                valid.append(os.path.basename(chat_db))
            except Exception as exc:
                invalid.append(f"{os.path.basename(chat_db)}: {type(exc).__name__}")
        elif os.path.exists(CHAT_HISTORY_FILE):
            try:
                with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as handle:
                    legacy_history = json.load(handle)
                if not isinstance(legacy_history, dict):
                    raise ValueError("legacy chat root is not an object")
                valid.append(os.path.basename(CHAT_HISTORY_FILE))
            except Exception as exc:
                invalid.append(f"{os.path.basename(CHAT_HISTORY_FILE)}: {type(exc).__name__}")
        else:
            missing.append(os.path.basename(chat_db))

        backups = sorted(glob.glob(os.path.join(USER_DATA_DIR, "smarti_settings.backup.*.json")), reverse=True)
        if invalid:
            action = RepairAction(
                "restore_latest_settings_backup" if os.path.basename(SETTINGS_FILE) in " ".join(invalid) and backups else "open_data_folder",
                "שחזור גיבוי הגדרות" if os.path.basename(SETTINGS_FILE) in " ".join(invalid) and backups else "פתיחת תיקיית הנתונים",
                "הפעולה תשמור עותק של הקובץ הפגום לפני שחזור הגיבוי האחרון." if backups else "אפשר לבחור גיבוי ידני או להעביר את הקובץ לבדיקה.",
                "high" if backups else "low",
            )
            return self._result(
                "data.json", STATUS_ERROR,
                "לפחות אחד מקובצי הנתונים אינו JSON תקין. Smarti לא יתקן אותו בלי אישור מפורש.",
                f"valid={len(valid)}; missing={missing or 'none'}; invalid={invalid}; settings_backups={len(backups)}",
                action, category="data", title_he="קובצי נתונים וגיבויים",
            )
        if missing:
            return self._result(
                "data.json", STATUS_WARNING,
                "חלק מקובצי הנתונים עדיין לא נוצרו או חסרים. זה תקין בהתקנה חדשה, אך כדאי ליצור גיבוי לפני שינוי משמעותי.",
                f"valid={len(valid)}; missing={missing}; settings_backups={len(backups)}",
                RepairAction("create_backup", "יצירת גיבוי עכשיו", "ייווצר קובץ ZIP מקומי של נתוני Smarti הקיימים.", "low"),
                category="data", title_he="קובצי נתונים וגיבויים",
            )
        return self._result(
            "data.json", STATUS_PASS,
            "קובצי הנתונים הקיימים תקינים וניתנים לקריאה.",
            f"valid={len(valid)}; settings_backups={len(backups)}",
            RepairAction("create_backup", "יצירת גיבוי עכשיו", "גיבוי מקומי לפני שינוי גדול הוא תמיד רעיון טוב.", "low"),
            category="data", title_he="קובצי נתונים וגיבויים",
        )

    def check_settings_schema(self):
        if not os.path.exists(SETTINGS_FILE):
            return self._result(
                "settings.schema", STATUS_SKIPPED,
                "קובץ ההגדרות עדיין לא נוצר, ולכן אין מבנה ישן להעביר גרסה.",
                f"settings_file_exists=false; expected_schema={SETTINGS_SCHEMA_VERSION}",
                category="data", title_he="מבנה הגדרות והעברת גרסה",
            )
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
                persisted = json.load(handle)
        except Exception as exc:
            return self._result(
                "settings.schema", STATUS_WARNING,
                "לא ניתן לבדוק את גרסת מבנה ההגדרות כי הקובץ אינו קריא. Diagnostic לא משנה אותו אוטומטית.",
                f"settings_schema_read={type(exc).__name__}: {self._redact(exc)}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "אפשר לגבות את קובץ ההגדרות או לשחזר גיבוי קיים לפני ניסיון תיקון.", "low"),
                category="data", title_he="מבנה הגדרות והעברת גרסה",
            )
        if not isinstance(persisted, dict):
            return self._result(
                "settings.schema", STATUS_WARNING,
                "קובץ ההגדרות אינו אובייקט JSON תקין ולכן אי אפשר לאמת את גרסת המבנה שלו.",
                f"settings_root={type(persisted).__name__}; expected_schema={SETTINGS_SCHEMA_VERSION}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "פתחי את תיקיית הנתונים כדי לגבות או לשחזר את קובץ ההגדרות.", "low"),
                category="data", title_he="מבנה הגדרות והעברת גרסה",
            )
        current = persisted.get("settings_schema_version")
        try:
            schema_ok = int(current) == int(SETTINGS_SCHEMA_VERSION)
        except (TypeError, ValueError):
            schema_ok = False
        if not schema_ok:
            return self._result(
                "settings.schema", STATUS_WARNING,
                f"נמצאה גרסת הגדרות ישנה או חסרה ({current!s}). אפשר לבצע נרמול בטוח: Smarti ייצור גיבוי ואז ישמור את המבנה הפעיל מחדש.",
                f"persisted_schema={current!r}; expected_schema={SETTINGS_SCHEMA_VERSION}",
                RepairAction("normalize_settings_schema", "גיבוי ונרמול הגדרות", "לפני השמירה ייווצר גיבוי ZIP מקומי. Smarti יסנכרן רק שדות תאימות וגרסת מבנה; סודות יישמרו באחסון המאובטח הרגיל.", "medium"),
                category="data", title_he="מבנה הגדרות והעברת גרסה",
            )
        return self._result(
            "settings.schema", STATUS_PASS,
            "מבנה ההגדרות תואם לגרסה הפעילה של Smarti.",
            f"persisted_schema={current}; expected_schema={SETTINGS_SCHEMA_VERSION}",
            category="data", title_he="מבנה הגדרות והעברת גרסה",
        )

    @staticmethod
    def _memory_expiry_state(value, now):
        """Return True/False for a parseable expiry, or None for malformed input."""
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed <= now
        except (TypeError, ValueError, OverflowError):
            return None

    def check_memory_health(self):
        if not os.path.exists(MEMORY_FILE):
            return self._result(
                "memory.health", STATUS_SKIPPED,
                "עדיין לא נוצר זיכרון מקומי. זה תקין בהתקנה חדשה.",
                "memory_file_exists=false",
                category="data", title_he="זיכרון מקומי ותוקף מידע",
            )
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            return self._result(
                "memory.health", STATUS_ERROR,
                "לא ניתן לקרוא את הזיכרון המקומי. Smarti לא ישנה אותו בלי אישור מפורש.",
                f"memory_read={type(exc).__name__}: {self._redact(exc)}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "אפשר לשמור עותק של קובץ הזיכרון ולשחזר אותו מגיבוי אם צריך.", "low"),
                category="data", title_he="זיכרון מקומי ותוקף מידע",
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("entries", []), list):
            return self._result(
                "memory.health", STATUS_ERROR,
                "מבנה הזיכרון המקומי אינו תקין. Diagnostic לא מאפס מידע אישי אוטומטית.",
                f"memory_root={type(payload).__name__}; entries_type={type(payload.get('entries') if isinstance(payload, dict) else None).__name__}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "פתחי את תיקיית הנתונים כדי לגבות את הקובץ או לשחזר גיבוי קודם.", "low"),
                category="data", title_he="זיכרון מקומי ותוקף מידע",
            )
        now = datetime.now()
        entries = payload["entries"]
        malformed = [index for index, entry in enumerate(entries) if not isinstance(entry, dict)]
        invalid_expiries = []
        expired = 0
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            expiry = self._memory_expiry_state(entry.get("expires_at"), now)
            if expiry is True:
                expired += 1
            elif expiry is None:
                invalid_expiries.append(index)
        technical = (
            f"entries={len(entries)}; expired={expired}; malformed_entries={malformed or 'none'}; "
            f"invalid_expiries={invalid_expiries or 'none'}"
        )
        if malformed or invalid_expiries:
            return self._result(
                "memory.health", STATUS_WARNING,
                "חלק מרשומות הזיכרון אינן במבנה הצפוי. הזיכרון התקין נשמר, אך כדאי לעבור על הקובץ לפני המשך שימוש.",
                technical,
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "פתחי את תיקיית הנתונים כדי לגבות או לבדוק את קובץ הזיכרון; Diagnostic אינו מוחק רשומות חריגות.", "low"),
                category="data", title_he="זיכרון מקומי ותוקף מידע",
            )
        if expired:
            return self._result(
                "memory.health", STATUS_WARNING,
                f"נמצאו {expired} פריטי זיכרון שפג תוקפם. אפשר לנקות רק אותם; שאר הזיכרון יישאר ללא שינוי.",
                technical,
                RepairAction("prune_expired_memory", "ניקוי מידע שפג תוקפו", "יימחקו רק רשומות שהוגדר להן תוקף שכבר חלף. מידע ללא תוקף ורשומות פעילות לא ייפגעו.", "medium"),
                category="data", title_he="זיכרון מקומי ותוקף מידע",
            )
        return self._result(
            "memory.health", STATUS_PASS,
            "הזיכרון המקומי במבנה תקין ואין בו מידע שפג תוקפו.",
            technical,
            category="data", title_he="זיכרון מקומי ותוקף מידע",
        )

    def check_storage(self):
        settings = getattr(self.core, "settings", {}) or {}
        configured_output = str(settings.get("default_output_dir") or OUTPUTS_DIR).strip() or OUTPUTS_DIR
        paths = {
            "תיקיית תוצרים": configured_output,
            "תיקיית קבצים מצורפים": ATTACHMENTS_DIR,
        }
        missing = [label for label, path in paths.items() if not os.path.isdir(path)]
        unwritable = []
        for label, path in paths.items():
            if not os.path.isdir(path):
                continue
            try:
                fd, probe_path = tempfile.mkstemp(prefix=".smarti_diagnostic_", suffix=".tmp", dir=path)
                os.close(fd)
                os.remove(probe_path)
            except Exception:
                unwritable.append(label)
        try:
            free_bytes = shutil.disk_usage(USER_DATA_DIR).free
        except Exception:
            free_bytes = 0
        free_mb = int(free_bytes / (1024 * 1024))
        if missing or unwritable:
            return self._result(
                "storage.files", STATUS_WARNING,
                "אחת מתיקיות העבודה של Smarti חסרה או אינה ניתנת לכתיבה. שמירת תוצרים או קבצים מצורפים עלולה להיכשל.",
                f"output_dir={configured_output}; missing={missing or 'none'}; unwritable={unwritable or 'none'}; free_mb={free_mb}",
                RepairAction("create_storage_dirs", "יצירת תיקיות העבודה", "תיווצרנה רק תיקיות Smarti החסרות. קבצים קיימים לא יימחקו.", "low"),
                category="storage", title_he="אחסון קבצים ותוצרים",
            )
        if free_mb and free_mb < 512:
            return self._result(
                "storage.files", STATUS_WARNING,
                "שטח האחסון הפנוי נמוך. פעולות עם קבצים, צילומי מסך או תוצרים גדולים עלולות להיכשל.",
                f"output_dir={configured_output}; attachments_dir={ATTACHMENTS_DIR}; free_mb={free_mb}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "פני מקום בדיסק לפני עבודה עם קבצים גדולים.", "low"),
                category="storage", title_he="אחסון קבצים ותוצרים",
            )
        return self._result(
            "storage.files", STATUS_PASS,
            "תיקיות התוצרים והקבצים המצורפים זמינות לכתיבה, ויש מספיק מקום פנוי לעבודה רגילה.",
            f"output_dir={configured_output}; attachments_dir={ATTACHMENTS_DIR}; free_mb={free_mb}",
            category="storage", title_he="אחסון קבצים ותוצרים",
        )

    def _selected_model(self, provider):
        return str(getattr(self.core, "settings", {}).get(f"selected_{provider}_model", "") or "").strip()

    def _check_codex_provider(self, model, include_network=False):
        """Diagnose the official Codex sign-in flow without an API-key probe."""
        try:
            codex = CodexSignInProvider(USER_DATA_DIR)
            connection = codex.check_connection() if include_network else codex.connection_status()
        except Exception as exc:
            return self._result(
                "provider.active", STATUS_ERROR,
                "לא ניתן היה להפעיל את בדיקת החיבור של Codex.",
                f"provider={CODEX_SIGNIN_PROVIDER}; selected_model={model}; codex_check_error={self._redact(exc)}",
                RepairAction(
                    "open_settings",
                    "פתיחת הגדרות Codex",
                    "יש לפתוח את הגדרות ספק Codex ולבדוק את ההתחברות הרשמית.",
                    "low",
                ),
                category="providers", title_he="ספק המודל הפעיל",
            )

        state = str(getattr(connection, "state", "unavailable") or "unavailable")
        message = str(getattr(connection, "message", "") or "")
        check_name = "codex_exec" if include_network else "login_status"
        detail = (
            f"provider={CODEX_SIGNIN_PROVIDER}; selected_model={model}; "
            f"auth_state={state}; connection_check={check_name}; message={self._redact(message)}"
        )
        if state == "connected":
            explanation = (
                "החיבור ל-ChatGPT / Codex אומת בבדיקת Codex הרשמית."
                if include_network
                else "נמצא סשן ChatGPT / Codex פעיל. הבדיקה המהירה הריצה codex login status בלבד."
            )
            return self._result(
                "provider.active", STATUS_PASS, explanation, detail,
                category="providers", title_he="ספק המודל הפעיל",
            )

        if state == "reauth_required":
            explanation = "סשן ChatGPT / Codex פג או דורש התחברות מחדש."
        elif state == "not_connected":
            explanation = "לא נמצא חיבור פעיל ל-ChatGPT / Codex."
        else:
            explanation = "Codex CLI אינו זמין לבדיקת החיבור."
        return self._result(
            "provider.active", STATUS_ERROR, explanation, detail,
            RepairAction(
                "open_settings",
                "התחברות ל-Codex",
                "יש לפתוח את הגדרות ספק Codex ולהשלים את ההתחברות הרשמית.",
                "low",
            ),
            category="providers", title_he="ספק המודל הפעיל",
        )

    def check_provider(self, include_network=False):
        settings = getattr(self.core, "settings", {}) or {}
        provider = normalize_provider_name(settings.get("api_mode", ""))
        config = provider_config(provider)
        if not config:
            return self._result(
                "provider.active", STATUS_ERROR,
                "ספק המודל הפעיל אינו מוכר ל‑Smarti.", f"api_mode={provider or '<empty>'}",
                RepairAction("open_settings", "פתיחת הגדרות ספק", "בחרי ספק מודל מוכר והגדירי אותו מחדש.", "low"),
                category="providers", title_he="ספק המודל הפעיל",
            )
        model = self._selected_model(provider)
        if provider == CODEX_SIGNIN_PROVIDER:
            return self._check_codex_provider(model or provider_default_model(provider), include_network)
        secret_key = provider_secret_key(provider)
        secret = ""
        if secret_key:
            # Credentials can live in Windows Credential Manager and are loaded
            # lazily by SmartiCore rather than kept in the settings JSON.
            loader = getattr(self.core, "ensure_provider_secret", None)
            try:
                secret = loader(provider) if callable(loader) else settings.get(secret_key, "")
            except Exception:
                secret = settings.get(secret_key, "")
        has_key = bool(secret) if secret_key else True
        if not model:
            return self._result(
                "provider.active", STATUS_WARNING,
                f"הספק {provider_display_name(provider)} מוגדר, אך לא נבחר מודל פעיל.",
                f"provider={provider}; api_key_configured={has_key}; selected_model=empty",
                RepairAction("open_settings", "בחירת מודל", "פתחי את הגדרות הספק ובחרי מודל פעיל.", "low"),
                category="providers", title_he="ספק המודל הפעיל",
            )
        if provider_requires_api_key(provider) and not has_key:
            return self._result(
                "provider.active", STATUS_ERROR,
                f"הספק {provider_display_name(provider)} נבחר, אך לא נמצא מפתח API שמור.",
                f"provider={provider}; api_key_configured=false; selected_model={model}",
                RepairAction("open_settings", "הזנת מפתח API", "פתחי את הגדרות הספק והזיני מפתח. המפתח לא יוצג ב‑Diagnostic או ביומן.", "low"),
                category="providers", title_he="ספק המודל הפעיל",
            )
        if not include_network:
            return self._result(
                "provider.active", STATUS_PASS,
                f"הספק {provider_display_name(provider)} והמודל שנבחר נראים מוגדרים כראוי. בדיקה מהירה לא פונה לרשת.",
                f"provider={provider}; api_key_configured={has_key}; selected_model={model}; network_check=skipped",
                category="providers", title_he="ספק המודל הפעיל",
            )
        ssl_snapshot = getattr(self.core, "_ssl_settings_snapshot", lambda: copy.deepcopy(settings))()
        models, ok, message = fetch_text_models_for_provider(
            provider,
            secret,
            settings.get("local_server_url", ""),
            ssl_snapshot,
            validate_key=True,
        )
        if not ok:
            return self._result(
                "provider.active", STATUS_ERROR,
                f"המערכת לא הצליחה לאמת את החיבור ל‑{provider_display_name(provider)}. ההגדרות עצמן לא שונו.",
                f"provider={provider}; selected_model={model}; validation={self._redact(message)}",
                RepairAction("open_settings", "בדיקת חיבור בהגדרות", "פתחי את הגדרות הספק כדי לעדכן כתובת, מפתח או מודל.", "low"),
                category="providers", title_he="ספק המודל הפעיל",
            )
        model_note = "המודל הנבחר הופיע ברשימה." if model in models else "החיבור תקין; המודל הנבחר לא הופיע ברשימה שחזרה מהספק."
        status = STATUS_PASS if model in models or not models else STATUS_WARNING
        return self._result(
            "provider.active", status,
            f"החיבור ל‑{provider_display_name(provider)} אומת. {model_note}",
            f"provider={provider}; selected_model={model}; returned_text_models={len(models)}",
            RepairAction("open_settings", "בחירת מודל אחר", "בחרי מודל שמופיע ברשימת המודלים הזמינים.", "low") if status == STATUS_WARNING else None,
            category="providers", title_he="ספק המודל הפעיל",
        )

    def check_search(self):
        settings = getattr(self.core, "settings", {}) or {}
        tools_config = settings.get("tools_config", {}) if isinstance(settings.get("tools_config"), dict) else {}
        web_enabled = bool(tools_config.get("internet_search", True))
        file_enabled = bool(tools_config.get("smart_file_search", True))
        content_enabled = bool(tools_config.get("deep_content_search", True))
        secret_loader = getattr(self.core, "_ensure_secret_loaded", None)
        try:
            tavily_key = secret_loader("tavily_api_key") if callable(secret_loader) else settings.get("tavily_api_key", "")
        except Exception:
            tavily_key = settings.get("tavily_api_key", "")
        sandbox_enabled = bool(getattr(self.core, "_sandbox_enabled", lambda: False)())
        sandbox_root = str(getattr(self.core, "_sandbox_root", lambda: "")() or "") if sandbox_enabled else ""
        user_profile = os.environ.get("USERPROFILE", "")
        local_root_ready = bool(sandbox_root and os.path.isdir(sandbox_root)) if sandbox_enabled else bool(user_profile and os.path.isdir(user_profile))
        technical = (
            f"internet_search_enabled={web_enabled}; tavily_key_loaded={bool(tavily_key)}; "
            f"file_search_enabled={file_enabled}; content_search_enabled={content_enabled}; "
            f"sandbox_enabled={sandbox_enabled}; local_root_ready={local_root_ready}"
        )
        if not local_root_ready:
            return self._result(
                "search.runtime", STATUS_ERROR,
                "חיפוש הקבצים אינו יכול לגשת לתיקיית העבודה המותרת. Smarti לא יסרוק נתיבים אחרים ללא מדיניות מתאימה.",
                technical,
                RepairAction("open_settings", "פתיחת הגדרות הרשאות", "בדקי את תיקיית ארגז החול או את הרשאות הקריאה של Windows.", "low"),
                category="search", title_he="חיפוש אינטרנט וקבצים",
            )
        if not (web_enabled or file_enabled or content_enabled):
            return self._result(
                "search.runtime", STATUS_SKIPPED,
                "כל יכולות החיפוש מושבתות כרגע בהגדרות הכלים.", technical,
                RepairAction("open_tools", "פתיחת מסך הכלים", "אפשר להפעיל רק את סוגי החיפוש שנחוצים לך.", "low"),
                category="search", title_he="חיפוש אינטרנט וקבצים",
            )
        if web_enabled and not tavily_key:
            return self._result(
                "search.runtime", STATUS_WARNING,
                "חיפוש קבצים מקומי מוכן, אך חיפוש האינטרנט אינו זמין כי לא נמצא מפתח Tavily שמור.", technical,
                RepairAction("open_settings", "הגדרת מפתח Tavily", "פתחי את ההגדרות והזיני מפתח Tavily כדי להפעיל חיפוש אינטרנט.", "low"),
                category="search", title_he="חיפוש אינטרנט וקבצים",
            )
        if not web_enabled:
            return self._result(
                "search.runtime", STATUS_PASS,
                "חיפוש הקבצים המקומי מוכן. חיפוש האינטרנט מושבת לפי בחירתך.", technical,
                RepairAction("open_tools", "פתיחת מסך הכלים", "אפשר להפעיל חיפוש אינטרנט בעת הצורך.", "low"),
                category="search", title_he="חיפוש אינטרנט וקבצים",
            )
        return self._result(
            "search.runtime", STATUS_PASS,
            "חיפוש קבצים וחיפוש אינטרנט מוגדרים. הבדיקה לא שלחה שאילתת חיפוש שעלולה לצרוך מכסה.", technical,
            RepairAction("test_search_connection", "בדיקת חיפוש חיה", "תישלח שאילתת Tavily קצרה בלבד כדי לאמת את החיבור. הפעולה עשויה לצרוך מכסת API.", "medium"),
            category="search", title_he="חיפוש אינטרנט וקבצים",
        )

    def check_computer_control(self):
        settings = getattr(self.core, "settings", {}) or {}
        enabled = bool(settings.get("enable_computer_control", False))
        dependencies = {
            "uiautomation": importlib.util.find_spec("uiautomation") is not None,
            "pyautogui": importlib.util.find_spec("pyautogui") is not None,
            "pyperclip": importlib.util.find_spec("pyperclip") is not None,
        }
        missing = [name for name, available in dependencies.items() if not available]
        if not enabled:
            return self._result(
                "automation.computer", STATUS_SKIPPED,
                "אוטומציית המחשב כבויה לפי ההגדרות. לא נבדקה שליטה בחלונות או בקלט.",
                f"enabled=false; dependencies={dependencies}",
                RepairAction("open_settings", "פתיחת הגדרות אוטומציה", "אפשר להפעיל את השליטה במחשב רק כאשר היא נחוצה לך.", "low"),
                category="automation", title_he="אוטומציית מחשב",
            )
        if missing:
            return self._result(
                "automation.computer", STATUS_ERROR,
                "שליטת המחשב מופעלת, אך חסרים רכיבי מערכת נדרשים ולכן הפעולות עלולות להיכשל.",
                f"enabled=true; missing_dependencies={missing}",
                RepairAction("open_settings", "פתיחת הגדרות אוטומציה", "אפשר לכבות זמנית את היכולת או לשחזר את התקנת Smarti.", "medium"),
                category="automation", title_he="אוטומציית מחשב",
            )
        return self._result(
            "automation.computer", STATUS_PASS,
            "רכיבי אוטומציית המחשב זמינים. Diagnostic לא שלט בעכבר, במקלדת או בחלון כלשהו.",
            f"enabled=true; dependencies={dependencies}",
            category="automation", title_he="אוטומציית מחשב",
        )

    def check_browser(self, include_network=False):
        settings = getattr(self.core, "settings", {}) or {}
        enabled = bool(settings.get("enable_browser_automation", False))
        chrome = getattr(self.core, "_chrome_executable", lambda: None)()
        embedded_available = callable(getattr(self.core, "embedded_browser_activate_callback", None))
        playwright_available = importlib.util.find_spec("playwright") is not None
        profile_dir = getattr(self.core, "_automation_browser_profile_dir", lambda: "")()
        if not chrome and not embedded_available:
            return self._result(
                "browser.automation", STATUS_ERROR if enabled else STATUS_SKIPPED,
                "אוטומציית הדפדפן אינה זמינה כי Google Chrome לא נמצא." if enabled else "אוטומציית הדפדפן כבויה, ו‑Google Chrome לא נמצא לבדיקת מוכנות.",
                f"enabled={enabled}; chrome_found=false; playwright_available={playwright_available}",
                RepairAction("open_settings", "פתיחת הגדרות אוטומציה", "לאחר התקנת Chrome אפשר להפעיל ולבדוק את אוטומציית הדפדפן.", "low"),
                category="browser", title_he="דפדפן האוטומציה",
            )
        if not playwright_available:
            return self._result(
                "browser.automation", STATUS_ERROR if enabled else STATUS_WARNING,
                "ספריית Playwright חסרה, ולכן Smarti לא יכול להתחבר לדפדפן המובנה דרך CDP.",
                f"enabled={enabled}; embedded_available={embedded_available}; fallback_browser={chrome}; playwright_available=false; profile_exists={os.path.isdir(profile_dir)}",
                RepairAction("open_settings", "פתיחת הגדרות אוטומציה", "בדקי את התקנת Smarti או הפעילי מחדש את המתקין כדי לשחזר רכיבים חסרים.", "medium"),
                category="browser", title_he="דפדפן האוטומציה",
            )
        browser_ready = False
        ready_probe = getattr(self.core, "_automation_browser_is_ready", None)
        if callable(ready_probe):
            try:
                browser_ready = bool(ready_probe())
            except Exception:
                browser_ready = False
        if not enabled and browser_ready:
            return self._result(
                "browser.automation", STATUS_WARNING,
                "אוטומציית הדפדפן כבויה, אך Smarti Browser עדיין מוכן ברקע.",
                f"enabled=false; embedded_available={embedded_available}; fallback_browser={bool(chrome)}; playwright_available=true; profile_exists={os.path.isdir(profile_dir)}; smarti_browser_ready=true",
                RepairAction("close_orphaned_browser", "סגירת דפדפן האוטומציה", "ייסגר רק דפדפן חלופי שהופעל בידי Smarti; פרופילי דפדפן אישיים אינם חלק מהפעולה.", "medium"),
                category="browser", title_he="דפדפן האוטומציה",
            )
        if not enabled:
            return self._result(
                "browser.automation", STATUS_SKIPPED,
                "רכיבי Smarti Browser ו‑Playwright זמינים, אבל אוטומציית הדפדפן כבויה לפי בחירתך. לא הופעל דפדפן בבדיקה זו.",
                f"enabled=false; embedded_available={embedded_available}; fallback_browser={bool(chrome)}; playwright_available=true; profile_exists={os.path.isdir(profile_dir)}; smarti_browser_ready=false",
                RepairAction("open_settings", "פתיחת הגדרות אוטומציה", "אפשר להפעיל את היכולת רק אם היא נחוצה לך.", "low"),
                category="browser", title_he="דפדפן האוטומציה",
            )
        if not include_network:
            return self._result(
                "browser.automation", STATUS_PASS,
                "רכיבי Smarti Browser ו‑Playwright זמינים. בדיקה מהירה לא מפעילה את פרופיל האוטומציה.",
                f"enabled=true; embedded_available={embedded_available}; fallback_browser={bool(chrome)}; playwright_available=true; profile_dir={profile_dir or '<unknown>'}; connection_check=skipped",
                category="browser", title_he="דפדפן האוטומציה",
            )
        pw = None
        browser = None
        was_ready = bool(getattr(self.core, "_automation_browser_is_ready", lambda: False)())
        started_by_doctor = not was_ready
        try:
            ok, error = getattr(self.core, "_ensure_automation_browser")()
            if not ok:
                raise RuntimeError(error or "Browser did not become ready")
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{SMARTI_BROWSER_DEBUG_PORT}", timeout=8000)
            version = getattr(browser, "version", "unknown")
            if callable(version):
                version = version()
            lifecycle_note = (
                "דפדפן האוטומציה אותחל רק לצורך הבדיקה."
                if started_by_doctor else "Smarti Browser כבר היה מוכן לפני הבדיקה ונשאר פעיל."
            )
            return self._result(
                "browser.automation", STATUS_PASS,
                f"המערכת התחברה ל‑Smarti Browser דרך Playwright/CDP בהצלחה. לא נפתח אתר ולא נקרא תוכן משתמש. {lifecycle_note}",
                f"enabled=true; browser_version={version}; profile_dir={profile_dir or '<unknown>'}; playwright_cdp=ok; started_by_doctor={started_by_doctor}",
                category="browser", title_he="דפדפן האוטומציה",
            )
        except Exception as exc:
            return self._result(
                "browser.automation", STATUS_ERROR,
                "Smarti לא הצליח להתחבר לפרופיל הדפדפן המובנה דרך Playwright/CDP.",
                f"enabled=true; profile_dir={profile_dir or '<unknown>'}; playwright_cdp={type(exc).__name__}: {self._redact(exc)}",
                RepairAction("reset_browser_profile", "איפוס פרופיל האוטומציה", "פרופיל Smarti יועבר לתיקיית גיבוי וייבנה מחדש; פרופילי דפדפן אחרים במחשב לא ישתנו.", "high"),
                category="browser", title_he="דפדפן האוטומציה",
            )
        finally:
            if pw is not None:
                try:
                    pw.stop()
                except Exception:
                    pass
            # Keep an already active user automation session intact, but never
            # leave a fallback browser process behind when Diagnostic opened it
            # only for this probe. The embedded profile remains owned by the UI.
            if started_by_doctor:
                try:
                    getattr(self.core, "_close_automation_browser")()
                except Exception:
                    pass

    def _email_config(self):
        resolver = getattr(self.core, "_email_config", None)
        if callable(resolver):
            # This is the canonical configuration path: it lazy-loads secrets
            # from Credential Manager and fills provider-specific IMAP/SMTP
            # defaults exactly as the mail tool does.
            try:
                resolved = resolver()
                if isinstance(resolved, dict):
                    return resolved
            except Exception:
                pass
        settings = getattr(self.core, "settings", {}) or {}
        return {
            "user": settings.get("email_address", ""),
            "password": settings.get("email_password", ""),
            "imap_host": settings.get("email_imap_host", ""),
            "imap_port": settings.get("email_imap_port", 993),
            "imap_ssl": bool(settings.get("email_imap_ssl", True)),
            "smtp_host": settings.get("email_smtp_host", ""),
            "smtp_port": settings.get("email_smtp_port", 587),
            "smtp_ssl": bool(settings.get("email_smtp_ssl", False)),
            "smtp_starttls": bool(settings.get("email_smtp_starttls", True)),
        }

    def check_email(self, include_network=False):
        cfg = self._email_config()
        configured_fields = [key for key in ("user", "password", "imap_host", "smtp_host") if cfg.get(key)]
        if not configured_fields:
            return self._result(
                "email.connection", STATUS_SKIPPED,
                "דוא\"ל אינו מוגדר כרגע, ולכן לא בוצעה התחברות לשרתים.",
                "email configuration is empty; network_check=skipped",
                RepairAction("open_settings", "פתיחת הגדרות דוא\"ל", "אפשר להגדיר IMAP ו‑SMTP כאשר תרצי לחבר תיבת דוא\"ל.", "low"),
                category="email", title_he="דוא\"ל",
            )
        missing = [key for key in ("user", "password", "imap_host", "smtp_host") if not cfg.get(key)]
        if missing:
            return self._result(
                "email.connection", STATUS_ERROR,
                "הגדרות הדוא\"ל אינן מלאות, ולכן Smarti לא ינסה להתחבר.",
                f"configured_fields={configured_fields}; missing_fields={missing}",
                RepairAction("open_settings", "השלמת הגדרות דוא\"ל", "השלימי את פרטי החשבון, סיסמת האפליקציה ושרתי IMAP/SMTP.", "low"),
                category="email", title_he="דוא\"ל",
            )
        if not include_network:
            return self._result(
                "email.connection", STATUS_PASS,
                "פרטי IMAP ו‑SMTP נראים מלאים. בדיקה מהירה לא מתחברת לתיבת הדוא\"ל.",
                f"imap={cfg['imap_host']}:{cfg['imap_port']}; smtp={cfg['smtp_host']}:{cfg['smtp_port']}; network_check=skipped",
                category="email", title_he="דוא\"ל",
            )
        settings = getattr(self.core, "settings", {}) or {}
        ssl_snapshot = getattr(self.core, "_ssl_settings_snapshot", lambda: copy.deepcopy(settings))()
        ok, message = test_email_connection(cfg, ssl_snapshot)
        if not ok:
            return self._result(
                "email.connection", STATUS_ERROR,
                "המערכת לא הצליחה לאמת את חיבור הדוא\"ל. לא נשלחה או שונתה אף הודעה.",
                f"imap={cfg['imap_host']}:{cfg['imap_port']}; smtp={cfg['smtp_host']}:{cfg['smtp_port']}; result={self._redact(message)}",
                RepairAction("open_settings", "בדיקת הגדרות דוא\"ל", "בדקי שרתים, פורטים, SSL/STARTTLS וסיסמת אפליקציה.", "low"),
                category="email", title_he="דוא\"ל",
            )
        return self._result(
            "email.connection", STATUS_PASS,
            "חיבור הדוא\"ל תקין: IMAP ו‑SMTP זמינים. Diagnostic לא שלח הודעה.",
            f"imap={cfg['imap_host']}:{cfg['imap_port']}; smtp={cfg['smtp_host']}:{cfg['smtp_port']}; result=ok",
            category="email", title_he="דוא\"ל",
        )

    def check_canvas(self):
        settings = getattr(self.core, "settings", {}) or {}
        visual_enabled = bool(settings.get("enable_visual_surfaces", False))
        web_enabled = bool(settings.get("enable_web_canvas", False))
        try:
            new_canvas_artifact({"title": "Diagnostic", "html": "<p>ok</p>"})
            schema_ok = True
        except Exception as exc:
            schema_ok = False
            schema_error = f"{type(exc).__name__}: {self._redact(exc)}"
        web_available = web_canvas_available()
        if not schema_ok:
            return self._result(
                "canvas.runtime", STATUS_ERROR,
                "רכיב הקנבס המקומי לא עבר אימות סכימה. הצ'אט הרגיל נשאר זמין.",
                f"schema_validation_failed={schema_error}",
                RepairAction("disable_visual_surfaces", "כיבוי הקנבס", "הקנבס יכובה עד לתיקון הרכיב, ללא מחיקת שיחות קיימות.", "medium"),
                category="canvas", title_he="קנבס ורכיבים חזותיים",
            )
        if web_enabled and not web_available:
            return self._result(
                "canvas.runtime", STATUS_ERROR,
                "הקנבס המתקדם מופעל, אבל רכיב WebEngine האופציונלי אינו מותקן.",
                "visual_schema=ok; web_canvas_enabled=true; webengine_available=false",
                RepairAction("disable_web_canvas", "כיבוי הקנבס המתקדם", "הקנבס המתקדם יכובה והצ'אט הרגיל ימשיך לעבוד.", "low"),
                category="canvas", title_he="קנבס ורכיבים חזותיים",
            )
        if not visual_enabled and not web_enabled:
            return self._result(
                "canvas.runtime", STATUS_SKIPPED,
                "יכולות הקנבס כבויות לפי ההגדרות. רכיב הסכימה המקומי זמין אם יופעל בעתיד.",
                f"visual_enabled=false; web_enabled=false; webengine_available={web_available}; schema_validation=ok",
                RepairAction("open_settings", "פתיחת הגדרות קנבס", "אפשר להפעיל את הקנבס רק כאשר הוא נחוץ לך.", "low"),
                category="canvas", title_he="קנבס ורכיבים חזותיים",
            )
        return self._result(
            "canvas.runtime", STATUS_PASS,
            "רכיבי הקנבס הפעילים עברו בדיקת סכימה והיכולת מוגדרת באופן עקבי.",
            f"visual_enabled={visual_enabled}; web_enabled={web_enabled}; webengine_available={web_available}; schema_validation=ok",
            category="canvas", title_he="קנבס ורכיבים חזותיים",
        )

    def check_voice(self):
        settings = getattr(self.core, "settings", {}) or {}
        voice_used = bool(settings.get("voice_hotkey", "")) or bool(settings.get("read_aloud_all", False))
        stt_ok = bool(SPEECH_INSTALLED)
        tts_ok = bool(TTS_INSTALLED)
        hotkey_ok = bool(KEYBOARD_INSTALLED)
        if voice_used and not stt_ok:
            return self._result(
                "voice.runtime", STATUS_ERROR,
                "קלט קולי מוגדר, אבל רכיב זיהוי הדיבור חסר. אפשר עדיין להשתמש בצ'אט רגיל.",
                f"speech_recognition={stt_ok}; keyboard={hotkey_ok}; tts={tts_ok}",
                RepairAction("open_settings", "פתיחת הגדרות קול", "בדקי את התקנת Smarti או בטלי זמנית את הקלט הקולי.", "medium"),
                category="voice", title_he="קול והקראה",
            )
        if voice_used and not hotkey_ok:
            return self._result(
                "voice.runtime", STATUS_WARNING,
                "זיהוי הדיבור זמין, אבל קיצור המקלדת לקול אינו זמין. אפשר להפעיל האזנה מהכפתור בממשק.",
                f"speech_recognition={stt_ok}; keyboard={hotkey_ok}; tts={tts_ok}",
                RepairAction("open_settings", "פתיחת הגדרות קול", "אפשר לשנות קיצור מקלדת או לבדוק את התקנת הרכיב.", "low"),
                category="voice", title_he="קול והקראה",
            )
        if not voice_used:
            return self._result(
                "voice.runtime", STATUS_SKIPPED,
                "קול והקראה אינם פעילים כרגע. לא נפתחה גישה למיקרופון בבדיקה זו.",
                f"speech_recognition={stt_ok}; keyboard={hotkey_ok}; edge_tts={EDGE_TTS_INSTALLED}; gtts={GTTS_INSTALLED}",
                RepairAction("open_settings", "פתיחת הגדרות קול", "אפשר להגדיר קול או קיצור מקלדת כשתרצי.", "low"),
                category="voice", title_he="קול והקראה",
            )
        return self._result(
            "voice.runtime", STATUS_PASS,
            "רכיבי הקול הזמינים תואמים להגדרות. Diagnostic לא הקליט, לא שלח ולא שמר אודיו.",
            f"speech_recognition={stt_ok}; keyboard={hotkey_ok}; edge_tts={EDGE_TTS_INSTALLED}; gtts={GTTS_INSTALLED}",
            category="voice", title_he="קול והקראה",
        )

    def _mcp_environment(self):
        builder = getattr(self.core, "_mcp_env", None)
        if callable(builder):
            try:
                env = builder()
                if isinstance(env, dict):
                    return env
            except Exception:
                pass
        return SMARTI_RUNTIME.subprocess_env(os.environ.copy())

    @staticmethod
    def _find_in_env(env, variable, *names):
        explicit = str((env or {}).get(variable, "") or "").strip()
        if explicit and os.path.exists(explicit):
            return explicit
        path = (env or {}).get("PATH") or (env or {}).get("Path") or os.environ.get("PATH", "")
        for name in names:
            found = shutil.which(name, path=path)
            if found:
                return found
        return ""

    def _probe_runtime_version(self, executable, env):
        if not executable:
            return False, "not found"
        try:
            completed = subprocess.run(
                [executable, "--version"], capture_output=True, text=True, timeout=5, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = (completed.stdout or completed.stderr or "").strip()
            if completed.returncode != 0:
                return False, f"exit={completed.returncode}; {output[:300]}"
            return bool(output), output[:300] or "no version output"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {self._redact(exc)}"

    def check_mcp_node_runtime(self):
        settings = getattr(self.core, "settings", {}) or {}
        mcp_enabled = bool(settings.get("enable_mcp_clawhub", False))
        mcp_count = len(glob.glob(os.path.join(MCP_TOOLS_DIR, "*.txt"))) if os.path.isdir(MCP_TOOLS_DIR) else 0
        if not mcp_enabled:
            return self._result(
                "mcp.node_runtime", STATUS_SKIPPED,
                "שירות MCP כבוי לפי ההגדרות, ולכן סביבת Node לא נדרשת כרגע.",
                f"mcp_enabled=false; installed_mcp_descriptors={mcp_count}",
                RepairAction("open_tools", "פתיחת מסך הכלים", "אפשר להפעיל MCP רק כאשר יש בו צורך, ואז להפעיל מחדש את הבדיקה.", "low"),
                category="extensions", title_he="סביבת Node.js ו־MCP",
            )
        env = self._mcp_environment()
        node = self._find_in_env(env, "SMARTI_NODE_EXE", "node.exe", "node")
        npm = self._find_in_env(env, "SMARTI_NPM_EXE", "npm.cmd", "npm")
        npx = self._find_in_env(env, "SMARTI_NPX_EXE", "npx.cmd", "npx")
        node_ok, node_version = self._probe_runtime_version(node, env)
        npm_ok, npm_version = self._probe_runtime_version(npm, env)
        npx_ok, npx_version = self._probe_runtime_version(npx, env)
        technical = (
            f"node_found={bool(node)}; node_probe={node_version}; npm_found={bool(npm)}; npm_probe={npm_version}; "
            f"npx_found={bool(npx)}; npx_probe={npx_version}; installed_mcp_descriptors={mcp_count}; "
            f"runtime_mode={'bundled' if bool(getattr(SMARTI_RUNTIME, 'is_frozen', False)) else 'development'}"
        )
        missing = [name for name, ok in (("Node.js", node_ok), ("npm", npm_ok), ("npx", npx_ok)) if not ok]
        if missing:
            return self._result(
                "mcp.node_runtime", STATUS_ERROR,
                f"שירות MCP פעיל, אך סביבת ההרצה שלו אינה שלמה: חסר או לא מגיב {', '.join(missing)}. לא הורץ שרת MCP ולא נעשה שימוש ברשת בבדיקה זו.",
                technical,
                RepairAction("disable_mcp", "כיבוי MCP זמנית", "MCP יכובה עד לתיקון סביבת Node או להרצת מתקין התיקון של Smarti. חבילות והגדרות מותקנות לא יימחקו.", "medium"),
                category="extensions", title_he="סביבת Node.js ו־MCP",
            )
        return self._result(
            "mcp.node_runtime", STATUS_PASS,
            "סביבת MCP תקינה: Node.js, npm ו־npx זמינים ומגיבים. Diagnostic לא הפעיל חבילת MCP ולא הוריד דבר.",
            technical,
            category="extensions", title_he="סביבת Node.js ו־MCP",
        )

    def check_mcp_catalog(self):
        settings = getattr(self.core, "settings", {}) or {}
        mcp_enabled = bool(settings.get("enable_mcp_clawhub", False))
        protocol_version = str(settings.get("mcp_protocol_version", "2025-11-25") or "").strip()
        descriptor_paths = sorted(glob.glob(os.path.join(MCP_TOOLS_DIR, "*.txt"))) if os.path.isdir(MCP_TOOLS_DIR) else []
        wrapper_paths = sorted(glob.glob(os.path.join(MCP_TOOLS_DIR, "*.pyw"))) if os.path.isdir(MCP_TOOLS_DIR) else []
        invalid_descriptors = []
        for path in descriptor_paths:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                if not isinstance(payload, list):
                    raise ValueError("descriptor root is not a list")
            except Exception as exc:
                invalid_descriptors.append(f"{os.path.basename(path)} ({type(exc).__name__})")
        descriptor_stems = {os.path.splitext(os.path.basename(path))[0] for path in descriptor_paths}
        orphan_wrappers = [os.path.basename(path) for path in wrapper_paths if os.path.splitext(os.path.basename(path))[0] not in descriptor_stems]
        configured = settings.get("tools_config", {}) if isinstance(settings.get("tools_config"), dict) else {}
        enabled_without_descriptor = sorted(
            key[4:] for key, value in configured.items()
            if str(key).startswith("mcp_") and bool(value) and key[4:] not in descriptor_stems
        )
        config_problem = ""
        config_exists = os.path.exists(MCP_CONFIG_FILE)
        if config_exists:
            try:
                with open(MCP_CONFIG_FILE, "r", encoding="utf-8") as handle:
                    config = json.load(handle)
                if not isinstance(config, dict) or not isinstance(config.get("allowed_directories"), list):
                    config_problem = "מבנה לא תקין"
            except Exception as exc:
                config_problem = type(exc).__name__
        elif mcp_enabled:
            config_problem = "קובץ חסר"
        technical = (
            f"mcp_enabled={mcp_enabled}; descriptors={len(descriptor_paths)}; invalid_descriptors={invalid_descriptors or 'none'}; "
            f"orphan_wrappers={orphan_wrappers or 'none'}; enabled_without_descriptor={enabled_without_descriptor or 'none'}; "
            f"mcp_config_exists={config_exists}; mcp_config_problem={config_problem or 'none'}; "
            f"mcp_protocol_version={protocol_version or 'empty'}"
        )
        if invalid_descriptors or orphan_wrappers or enabled_without_descriptor:
            parts = []
            if invalid_descriptors:
                parts.append("תיאורי MCP לא תקינים: " + ", ".join(invalid_descriptors))
            if orphan_wrappers:
                parts.append("מעטפות הרצה ללא חבילה: " + ", ".join(orphan_wrappers))
            if enabled_without_descriptor:
                parts.append("חבילות מסומנות כפעילות ללא תיאור: " + ", ".join(enabled_without_descriptor))
            return self._result(
                "mcp.catalog", STATUS_WARNING,
                "נמצאה אי־התאמה בקטלוג MCP. " + "\n• ".join([""] + parts) + "\nהפעולה הבטוחה היא לבדוק או להתקין מחדש רק את החבילה המצוינת; Diagnostic לא מוחק חבילות אוטומטית.",
                technical,
                RepairAction("open_tools", "פתיחת מסך ההרחבות", "במסך הכלים אפשר לראות את שם החבילה, רמת האמון שלה, ולמחוק או להתקין מחדש רק את הפריט הבעייתי.", "low"),
                category="extensions", title_he="קטלוג חבילות MCP",
            )
        if config_problem:
            return self._result(
                "mcp.catalog", STATUS_WARNING,
                "קטלוג ה־MCP תקין, אך קובץ התיאום המקומי חסר או אינו תקין. אפשר לבנות אותו מחדש בלי לגעת בחבילות מותקנות.",
                technical,
                RepairAction("refresh_mcp_config", "בניית תצורת MCP מחדש", "ייווצר מחדש קובץ תצורה נגזר מההגדרות הקיימות. הוא לא יתקין, ימחק או יפעיל חבילות MCP.", "low"),
                category="extensions", title_he="קטלוג חבילות MCP",
            )
        status = STATUS_PASS if mcp_enabled or descriptor_paths else STATUS_SKIPPED
        explanation = "קטלוג ה־MCP והתצורה המקומית עקביים." if status == STATUS_PASS else "אין חבילות MCP פעילות או מותקנות לבדיקה כרגע."
        return self._result(
            "mcp.catalog", status, explanation, technical,
            category="extensions", title_he="קטלוג חבילות MCP",
        )

    def check_custom_tools(self):
        tool_paths = sorted(glob.glob(os.path.join(TOOLS_DIR, "*.py")) + glob.glob(os.path.join(TOOLS_DIR, "*.pyw"))) if os.path.isdir(TOOLS_DIR) else []
        syntax_errors = []
        for path in tool_paths:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    source = handle.read(1_500_000)
                compile(source, path, "exec")
            except (OSError, UnicodeError, SyntaxError) as exc:
                syntax_errors.append(f"כלי {os.path.basename(path)}: שגיאת {type(exc).__name__}")
        technical = f"custom_tools={len(tool_paths)}; syntax_errors={syntax_errors or 'none'}"
        if syntax_errors:
            return self._result(
                "extensions.custom_tools", STATUS_WARNING,
                "כלים מותאמים שדורשים תיקון תחבירי:\n• " + "\n• ".join(syntax_errors) + "\nה־Diagnostic קרא את הקוד בלבד ולא הפעיל אותו. תיקון אוטומטי עלול לשנות לוגיקה אישית, לכן פתיחת הכלי לעריכה היא האפשרות הבטוחה.",
                technical,
                RepairAction("open_tools", "פתיחת הכלים המותאמים", "אפשר לפתוח או להשבית רק את הכלי המופיע ברשימה. Diagnostic לא משנה את הקוד האישי שלך ללא בחירה מפורשת.", "low"),
                category="extensions", title_he="כלים מותאמים",
            )
        if not tool_paths:
            return self._result(
                "extensions.custom_tools", STATUS_SKIPPED,
                "לא הותקנו כלים מותאמים לבדיקה.", technical,
                category="extensions", title_he="כלים מותאמים",
            )
        return self._result(
            "extensions.custom_tools", STATUS_PASS,
            "כל הכלים המותאמים עברו בדיקת תחביר מקומית. הם לא הורצו בבדיקה זו.", technical,
            category="extensions", title_he="כלים מותאמים",
        )

    def check_skill_dependencies(self):
        settings = getattr(self.core, "settings", {}) or {}
        if not bool(settings.get("enable_skills_beta", True)):
            return self._result(
                "extensions.skills", STATUS_SKIPPED,
                "שכבת ה־Skills כבויה לפי ההגדרות.", "skills_enabled=false",
                RepairAction("open_tools", "פתיחת מסך ההרחבות", "אפשר להפעיל Skills רק כאשר יש בהם צורך.", "low"),
                category="extensions", title_he="תלויות של Skills",
            )
        registry = getattr(self.core, "skill_registry", {}) or {}
        dependency_checker = getattr(self.core, "_skill_dependency_status", None)
        if not registry:
            return self._result(
                "extensions.skills", STATUS_SKIPPED,
                "לא נמצאו Skills מותקנים לבדיקה.", "skills_enabled=true; skills=0",
                category="extensions", title_he="תלויות של Skills",
            )
        missing = []
        for name, spec in sorted(registry.items()):
            if not isinstance(spec, dict) or not callable(dependency_checker):
                continue
            try:
                state = dependency_checker(spec) or {}
                missing_bins = [str(item) for item in state.get("missing_bins", []) or []]
                install_entries = state.get("install_entries", []) or []
            except Exception:
                continue
            if missing_bins:
                missing.append({"name": str(name), "bins": missing_bins, "installable": bool(install_entries)})
        technical = f"skills_enabled=true; skills={len(registry)}; missing_dependencies={missing or 'none'}"
        if missing:
            lines = [f"יכולת {item['name']}: חסר {', '.join(item['bins'])}" for item in missing]
            installable = [item for item in missing if item["installable"]]
            action = RepairAction(
                f"install_skill_requirements:{installable[0]['name']}",
                f"התקנת דרישות: {installable[0]['name']}",
                f"Smarti יריץ רק את הוראות ההתקנה שה־Skill '{installable[0]['name']}' מפרסם. הפעולה עשויה להוריד חבילות, דורשת אישור, ותאומת מחדש לאחר מכן.",
                "high",
            ) if len(missing) == 1 and installable else RepairAction(
                "open_tools", "פתיחת מסך ההרחבות", "בחרי כל Skill בנפרד כדי לעיין בתלויות ובהוראות ההתקנה שלו. כך לא יותקנו חבילות לא קשורות יחד.", "low"
            )
            return self._result(
                "extensions.skills", STATUS_WARNING,
                "יכולות Skills שאינן מוכנות להרצה:\n• " + "\n• ".join(lines) + "\nלא הורץ ולא הותקן דבר בבדיקה. " + ("אפשר לאשר התקנה של הדרישות המוצעות עבור ה־Skill היחיד הזה." if len(missing) == 1 and installable else "לכל Skill יש לבחור תיקון בנפרד במסך ההרחבות."),
                technical, action,
                category="extensions", title_he="תלויות של Skills",
            )
        return self._result(
            "extensions.skills", STATUS_PASS,
            "כל ה־Skills המותקנים עומדים בתלויות ההרצה שלהם.", technical,
            category="extensions", title_he="תלויות של Skills",
        )

    def check_tool_catalog_policy(self):
        settings = getattr(self.core, "settings", {}) or {}
        search_enabled = bool(settings.get("enable_tool_search_catalog", True))
        watch_enabled = bool(settings.get("skills_load_watch", True))
        unknown_policy = str(settings.get("skill_install_unknown_scan_policy", "allow_with_warning") or "").strip().lower()
        protocol_version = str(settings.get("mcp_protocol_version", "2025-11-25") or "").strip()
        schema_missing = [
            name for name in ("search_tools", "load_skill", "get_tool_info", "run_skill")
            if name not in BUILTIN_TOOL_SCHEMAS
        ]
        custom_tools = getattr(self.core, "custom_tools", None)
        registry_service = getattr(self.core, "tool_registry", None)
        if custom_tools is not None and hasattr(custom_tools, "__len__"):
            tool_count = len(custom_tools)
        elif hasattr(registry_service, "__len__"):
            # Compatibility with small test/legacy registry collections. The
            # production ToolRegistry service deliberately has no collection length.
            tool_count = len(registry_service)
        else:
            tool_count = 0
        mcp_count = len(getattr(self.core, "mcp_registry", {}) or {})
        skill_count = len(getattr(self.core, "skill_registry", {}) or {})
        catalog_stale = False
        signature_problem = ""
        signature_getter = getattr(self.core, "_extension_dirs_signature", None)
        if callable(signature_getter):
            try:
                current_signature = signature_getter()
                loaded_signature = getattr(self.core, "_extension_catalog_signature", None)
                catalog_stale = bool(watch_enabled and loaded_signature and current_signature and current_signature != loaded_signature)
            except Exception as exc:
                signature_problem = type(exc).__name__
        technical = (
            f"tool_search_enabled={search_enabled}; skills_load_watch={watch_enabled}; "
            f"unknown_skill_scan_policy={unknown_policy or 'empty'}; mcp_protocol_version={protocol_version or 'empty'}; "
            f"schema_missing={schema_missing or 'none'}; python_tools={tool_count}; mcp_tools={mcp_count}; "
            f"skills={skill_count}; catalog_stale={catalog_stale}; signature_problem={signature_problem or 'none'}"
        )
        if schema_missing:
            return self._result(
                "extensions.tool_policy", STATUS_ERROR,
                "חסרות סכמות לכלי בחירה וטעינת Skills. הסוכן עלול לא לראות את קטלוג הכלים המלא.",
                technical,
                RepairAction("open_diagnostic_log", "פתיחת יומן Diagnostic", "פתחי את היומן המסונן כדי לראות אילו סכמות חסרות לפני תיקון קוד.", "low"),
                category="extensions", title_he="מדיניות בחירת כלים ו-Skills",
            )
        if unknown_policy not in {"allow_with_warning", "block"} or not protocol_version:
            return self._result(
                "extensions.tool_policy", STATUS_WARNING,
                "נמצאה הגדרת מדיניות לא תקינה עבור התקנת Skills או גרסת MCP.",
                technical,
                RepairAction("open_settings", "פתיחת הגדרות", "בדקי את מדיניות סריקת Skills ואת גרסת פרוטוקול MCP תחת כלים ותקשורת.", "low"),
                category="extensions", title_he="מדיניות בחירת כלים ו-Skills",
            )
        if catalog_stale:
            return self._result(
                "extensions.tool_policy", STATUS_WARNING,
                "קטלוג הכלים המקומי נראה מיושן מול הקבצים בתיקיות ההרחבות. רענון מסך הכלים אמור לסנכרן אותו.",
                technical,
                RepairAction("open_tools", "פתיחת מסך הכלים", "פתחי את מסך הכלים והשתמשי בכפתור רענון כדי לסנכרן Skills, כלי Python ו-MCP.", "low"),
                category="extensions", title_he="מדיניות בחירת כלים ו-Skills",
            )
        if not search_enabled:
            return self._result(
                "extensions.tool_policy", STATUS_SKIPPED,
                "קטלוג חיפוש הכלים כבוי בהגדרות, ולכן הסוכן ישתמש ברשימת הכלים הרגילה בלי חיפוש מקדים.",
                technical,
                RepairAction("open_settings", "פתיחת הגדרות", "אפשרי את קטלוג חיפוש הכלים אם תרצי בחירה עשירה יותר בין כלי מערכת, Python, MCP ו-Skills.", "low"),
                category="extensions", title_he="מדיניות בחירת כלים ו-Skills",
            )
        return self._result(
            "extensions.tool_policy", STATUS_PASS,
            "מדיניות בחירת הכלים פעילה, הסכמות זמינות והקטלוגים המקומיים עקביים.",
            technical,
            category="extensions", title_he="מדיניות בחירת כלים ו-Skills",
        )

    def check_background_tasks(self):
        settings = getattr(self.core, "settings", {}) or {}
        tasks = settings.get("background_tasks", [])
        jobs_alias = settings.get("background_jobs", [])
        scheduler_ready = getattr(self.core, "background_scheduler", None) is not None
        if not isinstance(tasks, list):
            return self._result(
                "tasks.background", STATUS_ERROR,
                "מאגר משימות הרקע אינו בפורמט תקין. Smarti לא ישנה אותו אוטומטית כדי לא לאבד תזמונים.",
                f"background_tasks_type={type(tasks).__name__}; scheduler_ready={scheduler_ready}",
                RepairAction("open_task_center", "פתיחת מרכז המשימות", "אפשר לעבור על המשימות ולבטל או ליצור מחדש רק את הפריטים הבעייתיים.", "low"),
                category="tasks", title_he="משימות רקע והתאוששות",
            )
        invalid = [index for index, task in enumerate(tasks) if not isinstance(task, dict)]
        ids = [str(task.get("id") or "").strip() for task in tasks if isinstance(task, dict)]
        duplicate_ids = sorted({task_id for task_id in ids if task_id and ids.count(task_id) > 1})
        active_count = sum(1 for task in tasks if isinstance(task, dict) and task.get("status") in {"scheduled", "running", "cancelling"})
        aliases_match = jobs_alias == tasks if isinstance(jobs_alias, list) else False
        technical = (
            f"tasks={len(tasks)}; active={active_count}; invalid_entries={invalid or 'none'}; "
            f"duplicate_ids={duplicate_ids or 'none'}; alias_matches={aliases_match}; scheduler_ready={scheduler_ready}"
        )
        if invalid or duplicate_ids:
            return self._result(
                "tasks.background", STATUS_WARNING,
                "נמצאו פריטי משימות רקע לא תקינים או מזהים כפולים. עדיף לעבור עליהם במרכז המשימות לפני שירוצו שוב.",
                technical,
                RepairAction("open_task_center", "פתיחת מרכז המשימות", "אפשר לבטל או ליצור מחדש רק את המשימות הבעייתיות.", "low"),
                category="tasks", title_he="משימות רקע והתאוששות",
            )
        if not scheduler_ready:
            return self._result(
                "tasks.background", STATUS_WARNING,
                "משימות הרקע שמורות, אך מתזמן המשימות אינו מוכן כרגע בזיכרון.",
                technical,
                RepairAction("open_task_center", "פתיחת מרכז המשימות", "אם המצב נמשך לאחר הפעלה מחדש, בדקי את המשימות הפעילות.", "low"),
                category="tasks", title_he="משימות רקע והתאוששות",
            )
        if not tasks:
            return self._result(
                "tasks.background", STATUS_SKIPPED,
                "אין משימות רקע או תזכורות פעילות כרגע.", technical,
                category="tasks", title_he="משימות רקע והתאוששות",
            )
        explanation = "משימות הרקע במבנה תקין והמתזמן מוכן."
        if not aliases_match:
            explanation += " רשומת התאימות תתעדכן בעת השמירה הבאה של משימה."
        return self._result(
            "tasks.background", STATUS_WARNING if not aliases_match else STATUS_PASS,
            explanation, technical,
            RepairAction("open_task_center", "פתיחת מרכז המשימות", "אפשר לעבור על המשימות הפעילות וההיסטוריה שלהן.", "low") if active_count else None,
            category="tasks", title_he="משימות רקע והתאוששות",
        )

    def check_secret_storage(self):
        """Audit the on-disk settings representation without reading secret values into output."""
        if not os.path.exists(SETTINGS_FILE):
            return self._result(
                "security.secrets", STATUS_SKIPPED,
                "קובץ ההגדרות עדיין לא נוצר, ולכן אין מה לבדוק באחסון הסודות המקומי.",
                "settings_file_exists=false",
                category="security", title_he="שמירת סודות",
            )
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
                persisted = json.load(handle)
        except Exception as exc:
            return self._result(
                "security.secrets", STATUS_WARNING,
                "לא ניתן לבדוק את צורת שמירת הסודות בקובץ ההגדרות. הערכים עצמם לא נקראו ולא הוצגו.",
                f"settings_secret_audit={type(exc).__name__}: {self._redact(exc)}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "אפשר לגבות את קובץ ההגדרות ולבדוק מדוע הוא אינו קריא.", "low"),
                category="security", title_he="שמירת סודות",
            )
        if not isinstance(persisted, dict):
            return self._result(
                "security.secrets", STATUS_WARNING,
                "קובץ ההגדרות אינו במבנה הצפוי, ולכן לא ניתן לאמת את אחסון הסודות.",
                f"settings_root={type(persisted).__name__}",
                RepairAction("open_data_folder", "פתיחת תיקיית הנתונים", "פתחי את תיקיית הנתונים כדי לגבות או לשחזר את קובץ ההגדרות.", "low"),
                category="security", title_he="שמירת סודות",
            )
        plaintext_keys = []
        protected_keys = []
        for key in sorted(SENSITIVE_SETTING_KEYS):
            value = persisted.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.startswith(SECRET_PREFIX):
                protected_keys.append(key)
            else:
                plaintext_keys.append(key)
        technical = (
            f"plaintext_secret_fields={plaintext_keys or 'none'}; "
            f"dpapi_secret_fields={protected_keys or 'none'}; "
            "credential_manager_fields_are_intentionally_not_enumerated"
        )
        if plaintext_keys:
            return self._result(
                "security.secrets", STATUS_WARNING,
                "נמצאו סודות השמורים כטקסט בקובץ ההגדרות. אפשר להעביר אותם לאחסון המאובטח של Windows או להצפנת DPAPI, בלי לחשוף אותם ב‑Diagnostic.",
                technical,
                RepairAction("secure_plaintext_secrets", "אבטחת הסודות השמורים", "Smarti ישמור את הסודות דרך Windows Credential Manager כאשר הוא זמין, או בהצפנת Windows מקומית. הערכים לא יוצגו ולא יישלחו לרשת.", "medium"),
                category="security", title_he="שמירת סודות",
            )
        storage_note = "ב‑Windows Credential Manager" if not protected_keys else "ב‑Credential Manager או בהצפנת DPAPI המקומית"
        return self._result(
            "security.secrets", STATUS_PASS,
            f"לא נמצאו סודות גלויים בקובץ ההגדרות. סודות שמורים נמצאים {storage_note}.",
            technical,
            category="security", title_he="שמירת סודות",
        )

    def check_security(self):
        settings = getattr(self.core, "settings", {}) or {}
        policy = settings.get("policy_matrix", {})
        invalid_policy = [key for key in DEFAULT_POLICY_MATRIX if str(policy.get(key, "")).lower() not in {"allow", "ask", "deny"}]
        ssl_mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
        insecure_ssl = bool(getattr(self.core, "_allow_insecure_ssl", lambda: False)())
        trust = settings.get("tool_trust", {})
        if not isinstance(trust, dict):
            trust = {}
        privacy = settings.get("privacy", {}) if isinstance(settings.get("privacy"), dict) else {}
        redact_logs = bool(privacy.get("redact_logs", settings.get("privacy_redact_logs", True)))
        risky_allow = [key for key, value in policy.items() if str(value).lower() == "allow" and key in {"shell", "file_write", "email", "mcp_run", "computer_control"}]
        if invalid_policy:
            return self._result(
                "security.policy", STATUS_ERROR,
                "מדיניות ההרשאות אינה שלמה. Smarti צריך לחזור לברירות מחדל בטוחות רק באישור שלך.",
                f"invalid_policy_keys={invalid_policy}; ssl_mode={ssl_mode}; global_insecure={insecure_ssl}; trust_entries={len(trust)}; redact_logs={redact_logs}",
                RepairAction("restore_safe_policy", "שחזור מדיניות בטוחה", "רק ערכי מדיניות לא תקינים יוחזרו לברירות המחדל הבטוחות.", "medium"),
                category="security", title_he="מדיניות ואבטחה",
            )
        if ssl_mode == SSL_MODE_CUSTOM_CA:
            ca_ok, ca_message = validate_custom_ca(settings.get("ssl_custom_ca_path", ""))
            if not ca_ok:
                return self._result(
                    "security.policy", STATUS_ERROR,
                    "מצב תעודת סינון נבחר, אך קובץ ה-CA אינו תקין. Smarti לא יעבור אוטומטית לחיבור לא מאובטח.",
                    f"policy_valid=true; ssl_mode={ssl_mode}; custom_ca_valid=false; reason={self._redact(ca_message)}; trust_entries={len(trust)}",
                    RepairAction("open_settings", "תיקון אמון HTTPS", "יש לפתוח את הגדרות האמון, לבחור תעודת CA תקינה ולהריץ בדיקת חיבור.", "medium"),
                    category="security", title_he="מדיניות ואבטחה",
                )
        if ssl_mode == SSL_MODE_LEGACY_INSECURE:
            return self._result(
                "security.policy", STATUS_WARNING,
                "תאימות ישנה ללא אימות תעודות פעילה באופן רחב. זהות שרתי HTTPS אינה נבדקת ב-Smarti ובכלים שמופעלים ממנו. עדיף להשתמש במאגר Windows או בתעודת CA של ספק הסינון.",
                f"policy_valid=true; risky_allow={risky_allow}; ssl_mode={ssl_mode}; global_insecure={str(insecure_ssl).lower()}; trust_entries={len(trust)}; redact_logs={redact_logs}; audit_log_exists={os.path.exists(AUDIT_LOG_FILE)}",
                RepairAction("disable_insecure_ssl", "חזרה לאמון Windows", "התאימות ללא אימות תכובה והאימות המאובטח ישתמש שוב במאגר האישורים של Windows.", "medium"),
                category="security", title_he="מדיניות ואבטחה",
            )
        if not redact_logs:
            return self._result(
                "security.policy", STATUS_WARNING,
                "הסתרת סודות בקובצי הלוג כבויה. מומלץ להפעיל אותה כדי לצמצם חשיפה מקרית של מפתחות, סיסמאות ופרטי חיבור.",
                f"policy_valid=true; risky_allow={risky_allow or 'none'}; insecure_ssl=false; trust_entries={len(trust)}; redact_logs=false; audit_log_exists={os.path.exists(AUDIT_LOG_FILE)}",
                RepairAction("enable_log_redaction", "הפעלת הסתרת סודות בלוגים", "החל מהשמירה הבאה Smarti יסמן את האפשרות להגנת הפרטיות. קובצי לוג קיימים לא ישוכתבו או יימחקו.", "low"),
                category="security", title_he="מדיניות ואבטחה",
            )
        explanation = "מדיניות ההרשאות תקינה, ואימות SSL פחות בטוח אינו פעיל."
        if risky_allow:
            explanation += " חלק מהיכולות הרגישות מוגדרות להרצה ישירה; זו בחירה שראוי לבדוק."
        return self._result(
            "security.policy", STATUS_WARNING if risky_allow else STATUS_PASS,
            explanation,
            f"policy_valid=true; risky_allow={risky_allow or 'none'}; insecure_ssl=false; trust_entries={len(trust)}; redact_logs=true; audit_log_exists={os.path.exists(AUDIT_LOG_FILE)}",
            RepairAction("open_settings", "פתיחת הגדרות הרשאות", "אפשר לעבור על רמת האוטונומיה ומדיניות הפעולות.", "low") if risky_allow else None,
            category="security", title_he="מדיניות ואבטחה",
        )

    def latest_settings_backup(self):
        candidates = sorted(glob.glob(os.path.join(USER_DATA_DIR, "smarti_settings.backup.*.json")), reverse=True)
        return candidates[0] if candidates else ""

    def _save_settings(self):
        save = getattr(self.core, "_save_settings", None)
        if not callable(save):
            raise RuntimeError("Smarti settings save API is unavailable")
        save()

    def perform_repair(self, action_id):
        """Execute one action *after* GUI confirmation. Returns a Hebrew outcome."""
        action_id = str(action_id or "").strip()
        if action_id == "create_data_dir":
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            return "תיקיית הנתונים של Smarti קיימת כעת."
        if action_id == "create_backup":
            return self._create_backup()
        if action_id == "normalize_settings_schema":
            backup = self._create_backup()
            manager = getattr(self.core, "settings_manager", None)
            sync = getattr(manager, "sync_legacy_aliases", None)
            if callable(sync):
                self.core.settings = sync(getattr(self.core, "settings", {}) or {})
            self.core.settings["settings_schema_version"] = SETTINGS_SCHEMA_VERSION
            self._save_settings()
            return f"מבנה ההגדרות נורמל לגרסה {SETTINGS_SCHEMA_VERSION}. {backup}"
        if action_id == "restore_latest_settings_backup":
            return self._restore_latest_settings_backup()
        if action_id == "create_storage_dirs":
            settings = getattr(self.core, "settings", {}) or {}
            output_dir = str(settings.get("default_output_dir") or OUTPUTS_DIR).strip() or OUTPUTS_DIR
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
            return "תיקיות התוצרים והקבצים המצורפים של Smarti זמינות כעת."
        if action_id == "prune_expired_memory":
            manager = getattr(self.core, "memory_manager", None)
            prune = getattr(manager, "prune_expired", None)
            if not callable(prune):
                raise RuntimeError("מנוע הזיכרון של Smarti אינו זמין כרגע")
            removed = int(prune() or 0)
            return f"נוקו {removed} פריטי זיכרון שפג תוקפם. מידע פעיל וללא תוקף לא שונה."
        if action_id == "test_search_connection":
            return self._test_search_connection()
        if action_id == "close_orphaned_browser":
            close = getattr(self.core, "_close_automation_browser", None)
            if not callable(close):
                raise RuntimeError("ממשק סגירת דפדפן האוטומציה אינו זמין")
            close()
            return "דפדפן האוטומציה של Smarti נסגר. פרופילי דפדפן אישיים אינם חלק מפעולה זו."
        if action_id == "reset_browser_profile":
            return self._reset_browser_profile()
        if action_id == "disable_web_canvas":
            self.core.settings["enable_web_canvas"] = False
            self._save_settings()
            return "הקנבס המתקדם כובה. הצ'אט הרגיל ממשיך לעבוד."
        if action_id == "disable_visual_surfaces":
            self.core.settings["enable_visual_surfaces"] = False
            self.core.settings["enable_web_canvas"] = False
            self._save_settings()
            return "יכולות הקנבס כובו עד לתיקון הרכיב."
        if action_id == "disable_mcp":
            self.core.settings["enable_mcp_clawhub"] = False
            self._save_settings()
            return "MCP כובה זמנית. חבילות מותקנות לא נמחקו."
        if action_id == "refresh_mcp_config":
            refresh = getattr(self.core, "_ensure_mcp_config", None)
            if not callable(refresh):
                raise RuntimeError("ממשק בניית תצורת MCP אינו זמין")
            refresh()
            return "קובץ תצורת MCP נבנה מחדש מההגדרות הקיימות. לא הותקנה, הופעלה או נמחקה חבילה."
        if action_id.startswith("install_skill_requirements:"):
            skill_name = action_id.partition(":")[2].strip()
            registry = getattr(self.core, "skill_registry", {}) or {}
            if not skill_name or skill_name not in registry:
                raise RuntimeError("ה־Skill שנבחר אינו קיים עוד ברישום Smarti")
            installer = getattr(self.core, "install_skill_requirements", None)
            if not callable(installer):
                raise RuntimeError("ממשק התקנת דרישות Skill אינו זמין")
            outcome = str(installer(skill_name, reason="Smarti Diagnostic approved repair") or "")
            if outcome.lstrip().startswith("ERROR:"):
                raise RuntimeError(self._redact(outcome))
            return f"דרישות ה־Skill '{skill_name}' טופלו.\n{self._redact(outcome)}"
        if action_id == "disable_insecure_ssl":
            self.core.settings["ssl_trust_mode"] = SSL_MODE_SYSTEM
            self.core.settings["allow_insecure_ssl_compat"] = False
            if hasattr(self.core, "_set_legacy_ssl_session_enabled"):
                self.core._set_legacy_ssl_session_enabled(False)
            self._save_settings()
            return "התאימות ללא אימות תעודות כובתה. Smarti חזר לאמון המאומת של Windows."
        if action_id == "enable_log_redaction":
            self.core.settings["privacy_redact_logs"] = True
            self.core.settings.setdefault("privacy", {})["redact_logs"] = True
            self._save_settings()
            return "הסתרת סודות בלוגים הופעלה להמשך העבודה. קובצי לוג קיימים לא שונו."
        if action_id == "secure_plaintext_secrets":
            self._save_settings()
            return "ההגדרות נשמרו מחדש. סודות הועברו לאחסון המאובטח הזמין ב‑Windows או הוצפנו ב‑DPAPI המקומי."
        if action_id == "restore_safe_policy":
            policy = self.core.settings.setdefault("policy_matrix", {})
            repaired = []
            for key, default in DEFAULT_POLICY_MATRIX.items():
                if str(policy.get(key, "")).lower() not in {"allow", "ask", "deny"}:
                    policy[key] = default
                    repaired.append(key)
            self._save_settings()
            return "שוחזרו ערכי מדיניות לא תקינים: " + (", ".join(repaired) if repaired else "לא נדרשו שינויים")
        raise ValueError(f"Unsupported Diagnostic repair action: {action_id}")

    def _test_search_connection(self):
        search = getattr(self.core, "search_internet", None)
        if not callable(search):
            raise RuntimeError("מנוע חיפוש האינטרנט של Smarti אינו זמין")
        result = str(search("Smarti Diagnostic connectivity check") or "")
        if result.startswith("Error:") or result.startswith("ERROR"):
            raise RuntimeError(self._redact(result))
        return "חיפוש האינטרנט אומת בהצלחה. נשלחה שאילתת בדיקה קצרה אחת ל‑Tavily."

    def _create_backup(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive = os.path.join(USER_DATA_DIR, f"smarti_diagnostic_backup.{stamp}.zip")
        chat_db = CHAT_HISTORY_DB_FILE
        candidates = [
            SETTINGS_FILE, MEMORY_FILE, CHAT_HISTORY_FILE, USAGE_FILE,
            ACTIVE_TASK_CHECKPOINT_FILE, MCP_CONFIG_FILE,
        ]
        written = []
        sqlite_snapshot = ""
        if os.path.isfile(chat_db):
            handle = tempfile.NamedTemporaryFile(
                prefix="smarti-chat-backup-",
                suffix=".sqlite3",
                delete=False,
            )
            sqlite_snapshot = handle.name
            handle.close()
            try:
                with closing(sqlite3.connect(chat_db, timeout=15.0)) as source:
                    with closing(sqlite3.connect(sqlite_snapshot)) as destination:
                        source.backup(destination)
            except Exception:
                try:
                    os.remove(sqlite_snapshot)
                except OSError:
                    pass
                sqlite_snapshot = ""
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in candidates:
                if os.path.isfile(path):
                    bundle.write(path, arcname=os.path.basename(path))
                    written.append(os.path.basename(path))
            if sqlite_snapshot:
                bundle.write(sqlite_snapshot, arcname=os.path.basename(chat_db))
                written.append(os.path.basename(chat_db))
        if sqlite_snapshot:
            try:
                os.remove(sqlite_snapshot)
            except OSError:
                pass
        if not written:
            os.remove(archive)
            raise RuntimeError("No Smarti data files were available to back up")
        return f"נוצר גיבוי מקומי עם {len(written)} קבצים: {os.path.basename(archive)}"

    def _restore_latest_settings_backup(self):
        backup = self.latest_settings_backup()
        if not backup:
            raise RuntimeError("לא נמצא גיבוי הגדרות לשחזור")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if os.path.exists(SETTINGS_FILE):
            corrupt_copy = os.path.join(USER_DATA_DIR, f"smarti_settings.before_restore.{stamp}.json")
            shutil.copy2(SETTINGS_FILE, corrupt_copy)
        shutil.copy2(backup, SETTINGS_FILE)
        self.core.settings = self.core._load_settings()
        self.core.setup_model()
        return f"ההגדרות שוחזרו מהגיבוי {os.path.basename(backup)}. נשמר גם עותק של הקובץ הקודם כאשר היה קיים."

    def _reset_browser_profile(self):
        profile_dir = getattr(self.core, "_automation_browser_profile_dir", lambda: "")()
        if not profile_dir:
            raise RuntimeError("נתיב פרופיל האוטומציה אינו זמין")
        close = getattr(self.core, "_close_automation_browser", None)
        if callable(close):
            close()
        if not os.path.exists(profile_dir):
            return "לא נמצא פרופיל אוטומציה קיים, ולכן אין מה לאפס."
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = f"{profile_dir}.backup.{stamp}"
        shutil.move(profile_dir, backup_dir)
        return "פרופיל האוטומציה הועבר לגיבוי ונבנה מחדש בפעם הבאה שתופעל אוטומציית דפדפן."
