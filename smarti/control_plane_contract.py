"""Authoritative, UI-independent schema source for the desktop `/v2` API."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


CONTRACT_VERSION = "2.0.0"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _object(properties=None, required=()):
    return {
        "type": "object",
        "properties": copy.deepcopy(properties or {}),
        "required": list(required),
        "additionalProperties": False,
    }


STRING = {"type": "string"}
IDENTIFIER = {"type": "string", "minLength": 1, "maxLength": 200}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 500}


REQUEST_SCHEMAS = {
    "createWorkspace": _object({
        "title": {"type": "string", "maxLength": 200},
        "root_path": {"type": "string", "maxLength": 32767},
        "metadata": {"type": "object"},
    }),
    "patchWorkspace": _object({
        "title": {"type": "string", "maxLength": 200},
        "root_path": {"type": "string", "maxLength": 32767},
        "metadata": {"type": "object"},
    }),
    "createConversation": _object({
        "title": {"type": "string", "maxLength": 200},
        "workspace_id": {"type": "string", "maxLength": 200},
    }),
    "patchConversation": _object({
        "title": {"type": "string", "maxLength": 200},
        "workspace_id": {"type": "string", "maxLength": 200},
        "pinned": {"type": "boolean"},
    }),
    "submitRun": _object({
        "text": {"type": "string", "maxLength": 1000000},
        "attachment_handles": {
            "type": "array", "maxItems": 80, "items": IDENTIFIER,
        },
        "workspace_id": {"type": "string", "maxLength": 200},
        "source": {"type": "string", "maxLength": 100},
        "provider_mode": {"type": "string", "maxLength": 100},
        "model_name": {"type": "string", "maxLength": 300},
    }),
    "markRead": _object({
        "actor_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "attention_ids": {"type": "array", "maxItems": 10000, "items": IDENTIFIER},
    }),
    "resolveApproval": _object({
        "approved": {"type": "boolean"},
    }, ("approved",)),
    "patchSettings": _object({
        "values": {"type": "object", "minProperties": 1},
    }, ("values",)),
    "setSecret": _object({
        "value": {"type": "string", "minLength": 1, "maxLength": 65536},
    }, ("value",)),
    "legalAcceptance": _object({
        "accepted": {"type": "boolean", "const": True},
        "version": {"type": "string", "minLength": 1, "maxLength": 200},
    }, ("accepted", "version")),
    "settingsAction": _object({
        "action": {"type": "string", "enum": ["reset", "codex_status", "codex_check", "codex_login", "codex_logout", "email_test", "ssl_test", "ssl_import_ca", "log_clear"]},
        "ssl_trust_mode": {"type": "string", "enum": ["system", "custom_ca", "legacy_insecure"]},
        "ssl_custom_ca_path": {"type": "string", "maxLength": 32767},
        "source_path": {"type": "string", "maxLength": 32767},
        "confirmation": {"type": "string", "maxLength": 100},
    }, ("action",)),
    "validateProvider": _object({
        "secret": {"type": "string", "maxLength": 65536},
        "local_url": {"type": "string", "maxLength": 4096},
    }),
    "setModelReasoning": _object({
        "model": {"type": "string", "minLength": 1, "maxLength": 300},
        "effort": {"type": "string", "minLength": 1, "maxLength": 40},
    }, ("model", "effort")),
    "registerAttachment": _object({
        "path": {"type": "string", "minLength": 1, "maxLength": 32767},
        "session_id": {"type": "string", "maxLength": 200},
        "ttl_seconds": {"type": "integer", "minimum": 30, "maximum": 86400},
    }, ("path",)),
    "startTts": _object({
        "text": {"type": "string", "minLength": 1, "maxLength": 100000},
    }, ("text",)),
    "provideRunApiKey": _object({
        "secret_key": {"type": "string", "minLength": 1, "maxLength": 100},
        "value": {"type": "string", "minLength": 1, "maxLength": 65536},
    }, ("secret_key", "value")),
    "taskAction": _object({
        "action": {"type": "string", "enum": ["create", "edit", "cancel", "retry", "resume", "delete"]},
        "id": {"type": "string", "maxLength": 200}, "prompt": {"type": "string", "maxLength": 100000},
        "delay_minutes": {"type": "number", "minimum": 0}, "repeat": {"type": "string", "enum": ["once", "interval", "weekly"]},
        "interval_minutes": {"type": "number", "minimum": 1}, "days_of_week": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6}},
        "conversation_mode": {"type": "string", "enum": ["current", "new", "dedicated"]},
    }, ("action",)),
    "memoryAction": _object({
        "action": {"type": "string", "enum": ["details", "reveal", "edit", "pin", "archive", "restore", "delete"]},
        "subject": STRING, "content": {"type": "string", "maxLength": 6000}, "category": STRING,
        "sensitivity": STRING, "tags": {"type": "array", "items": STRING}, "importance": {"type": "integer", "minimum": 1, "maximum": 5}, "pinned": {"type": "boolean"},
        "memory_type": STRING, "ttl_hours": {"type": "number", "minimum": 0},
    }, ("action",)),
    "memoryCollectionAction": _object({
        "action": {"type": "string", "enum": ["create", "bulk_archive", "bulk_restore", "bulk_delete", "import", "export", "clear"]},
        "ids": {"type": "array", "maxItems": 1000, "items": IDENTIFIER},
        "subject": STRING, "content": {"type": "string", "maxLength": 6000}, "category": STRING,
        "memory_type": STRING, "tags": {"type": "array", "items": STRING},
        "importance": {"type": "integer", "minimum": 1, "maximum": 5}, "ttl_hours": {"type": "number", "minimum": 0},
        "pinned": {"type": "boolean"}, "path": {"type": "string", "maxLength": 32767},
        "confirmation": {"type": "string", "maxLength": 100},
    }, ("action",)),
    "toolAction": _object({
        "action": {"type": "string", "enum": ["set_trust", "set_enabled", "refresh", "install_skill", "install_custom", "install_mcp", "delete"]},
        "kind": {"type": "string", "enum": ["builtin", "custom", "mcp", "skill"]}, "name": STRING, "trusted": {"type": "boolean"}, "enabled": {"type": "boolean"},
        "path": {"type": "string", "maxLength": 32767}, "package": {"type": "string", "maxLength": 1000},
    }, ("action",)),
    "diagnosticAction": _object({
        "action": {"type": "string", "enum": ["scan", "repair", "cancel"]}, "include_network": {"type": "boolean"}, "repair_id": IDENTIFIER,
    }),
    "setWorkspaceRoot": _object({"path": {"type": "string", "minLength": 1, "maxLength": 32767}}, ("path",)),
    "openWorkspaceFile": _object({"path": {"type": "string", "minLength": 1, "maxLength": 32767}}, ("path",)),
    "terminalAction": _object({
        "action": {"type": "string", "enum": ["write", "restart"]}, "text": {"type": "string", "maxLength": 100000},
    }, ("action",)),
    "canvasAction": _object({
        "action": {"type": "string", "enum": ["layout", "close", "reopen"]},
        "button_positions": {
            "type": "array", "maxItems": 64,
            "items": _object({
                "id": {"type": "string", "minLength": 1, "maxLength": 96},
                "label": {"type": "string", "maxLength": 300},
                "x": {"type": "number", "minimum": -100000, "maximum": 100000},
                "y": {"type": "number", "minimum": -100000, "maximum": 100000},
                "width": {"type": "number", "minimum": 0, "maximum": 100000},
                "height": {"type": "number", "minimum": 0, "maximum": 100000},
            }, ("id", "x", "y")),
        },
    }, ("action",)),
    "browserImport": _object({
        "source_id": {"type": "string", "minLength": 3, "maxLength": 200},
        "history": {"type": "boolean"}, "bookmarks": {"type": "boolean"}, "cookies": {"type": "boolean"},
    }, ("source_id",)),
    "legacyBrowserMigration": _object({
        "action": {"type": "string", "enum": ["applied"]},
    }, ("action",)),
}


OPERATIONS = [
    ("GET", "/v2/health", "health", "בדיקת חיות מינימלית", None),
    ("GET", "/v2/version", "version", "גרסת חוזה וגרסת מוצר", None),
    ("GET", "/v2/capabilities", "capabilities", "יכולות זמינות ב-Core", None),
    ("GET", "/v2/bootstrap", "bootstrap", "תמונת אתחול בטוחה לשולחן העבודה", None),
    ("GET", "/v2/workspaces", "listWorkspaces", "רשימת סביבות עבודה", None),
    ("POST", "/v2/workspaces", "createWorkspace", "יצירת סביבת עבודה", "createWorkspace"),
    ("PATCH", "/v2/workspaces/{workspace_id}", "patchWorkspace", "עדכון סביבת עבודה", "patchWorkspace"),
    ("DELETE", "/v2/workspaces/{workspace_id}", "deleteWorkspace", "מחיקת סביבת עבודה", None),
    ("GET", "/v2/conversations", "listConversations", "רשימה וחיפוש שיחות", None),
    ("POST", "/v2/conversations", "createConversation", "יצירת שיחה", "createConversation"),
    ("GET", "/v2/conversations/{session_id}", "getConversation", "פרטי שיחה", None),
    ("PATCH", "/v2/conversations/{session_id}", "patchConversation", "שינוי שם, שיוך או נעיצה", "patchConversation"),
    ("DELETE", "/v2/conversations/{session_id}", "deleteConversation", "מחיקת שיחה", None),
    ("GET", "/v2/conversations/{session_id}/messages", "listMessages", "הודעות בעימוד", None),
    ("GET", "/v2/conversations/{session_id}/export", "exportConversation", "ייצוא JSON בסמכות היסטוריית Smarti", None),
    ("POST", "/v2/conversations/{session_id}/runs", "submitRun", "שליחת בקשה לסוכן", "submitRun"),
    ("POST", "/v2/conversations/{session_id}/read", "markRead", "סימון תשומת לב כנקראה", "markRead"),
    ("GET", "/v2/runs", "listRuns", "רשימת ריצות", None),
    ("GET", "/v2/runs/{run_id}", "getRun", "מצב ריצה", None),
    ("POST", "/v2/runs/{run_id}/cancel", "cancelRun", "בקשת ביטול", None),
    ("GET", "/v2/runs/{run_id}/events", "replayRunEvents", "שחזור אירועי ריצה", None),
    ("POST", "/v2/runs/{run_id}/api-key", "provideRunApiKey", "מענה להפרעת מפתח API של ריצה", "provideRunApiKey"),
    ("GET", "/v2/events/replay", "replayEventsHttp", "שחזור אירועים עמיד דרך מארח Tauri", None),
    ("GET", "/v2/approvals", "listApprovals", "אישורים ממתינים", None),
    ("POST", "/v2/approvals/{approval_id}/resolve", "resolveApproval", "אישור או דחייה", "resolveApproval"),
    ("GET", "/v2/settings/schema", "settingsSchema", "סכמת הגדרות בטוחה", None),
    ("GET", "/v2/settings", "getSettings", "ערכים לא סודיים ומצב סודות ממוסך", None),
    ("PATCH", "/v2/settings", "patchSettings", "עדכון הגדרות לא סודיות", "patchSettings"),
    ("PUT", "/v2/settings/secrets/{secret_key}", "setSecret", "שמירת סוד", "setSecret"),
    ("DELETE", "/v2/settings/secrets/{secret_key}", "deleteSecret", "מחיקת סוד", None),
    ("GET", "/v2/management/legal", "legalStatus", "מצב שער ההסכמה המשפטית", None),
    ("POST", "/v2/management/legal", "acceptLegal", "הסכמה מפורשת למסמך המשפטי הנוכחי", "legalAcceptance"),
    ("POST", "/v2/management/settings/actions", "settingsAction", "זרימות הגדרות ייעודיות ובדיקות חיבור", "settingsAction"),
    ("POST", "/v2/providers/{provider}/validate", "validateProvider", "בדיקת ספק וגילוי מודלים", "validateProvider"),
    ("GET", "/v2/providers/{provider}/models", "discoverModels", "גילוי מודלים", None),
    ("GET", "/v2/providers/{provider}/reasoning", "getModelReasoning", "קריאת רמות חשיבה למודל", None),
    ("POST", "/v2/providers/{provider}/reasoning", "setModelReasoning", "עדכון רמת חשיבה למודל הפעיל", "setModelReasoning"),
    ("GET", "/v2/providers/openai_codex_signin/quota", "readCodexQuota", "קריאת מכסת Codex שנותרה", None),
    ("GET", "/v2/audio/tts/voices", "listTtsVoices", "רשימת קולות ההקראה הזמינים ב-Core", None),
    ("POST", "/v2/attachments", "registerAttachment", "רישום קובץ לידית זמנית", "registerAttachment"),
    ("GET", "/v2/attachments/{handle}", "readAttachment", "קריאת קובץ דרך ידית תחומה", None),
    ("POST", "/v2/audio/tts", "startTts", "התחלת הקראה דרך Core", "startTts"),
    ("POST", "/v2/audio/tts/stop", "stopTts", "עצירת הקראה דרך Core", None),
    ("GET", "/v2/audio/tts/status", "ttsStatus", "מצב הקראה של Core", None),
    ("POST", "/v2/audio/voice", "startVoice", "התחלת האזנה דרך שירות הקול של Core", None),
    ("POST", "/v2/audio/voice/stop", "stopVoice", "ביטול האזנה של Core", None),
    ("GET", "/v2/audio/voice/status", "voiceStatus", "מצב ותמלול האזנה של Core", None),
    ("GET", "/v2/management/tasks", "listTasks", "רשימת משימות רקע", None),
    ("POST", "/v2/management/tasks", "manageTask", "יצירה ופעולות במשימת רקע", "taskAction"),
    ("GET", "/v2/management/memories", "listMemories", "ניהול זיכרון ממוסך", None),
    ("POST", "/v2/management/memories", "manageMemories", "יצירה, פעולות מרובות, ייבוא, ייצוא וניקוי זיכרון", "memoryCollectionAction"),
    ("GET", "/v2/management/memories/{memory_id}", "getMemory", "פרטי זיכרון ממוסכים", None),
    ("PATCH", "/v2/management/memories/{memory_id}", "manageMemory", "עריכה, חשיפה, ארכוב ושחזור זיכרון", "memoryAction"),
    ("DELETE", "/v2/management/memories/{memory_id}", "deleteMemory", "מחיקת זיכרון", None),
    ("GET", "/v2/management/tools", "listTools", "כלים, MCP ו-Skills", None),
    ("POST", "/v2/management/tools", "manageTools", "רענון, התקנה ואמון הרחבות", "toolAction"),
    ("GET", "/v2/management/usage", "usage", "נתוני שימוש מקומיים", None),
    ("DELETE", "/v2/management/usage", "clearUsage", "ניקוי נתוני שימוש מקומיים עם גיבוי", None),
    ("GET", "/v2/management/logs", "logs", "לוג מאוחד עם סינון פרטיות", None),
    ("GET", "/v2/management/about", "about", "גרסה ומידע על היישום", None),
    ("GET", "/v2/management/diagnostics", "diagnosticProgress", "התקדמות בדיקה פעילה", None),
    ("POST", "/v2/management/diagnostics", "diagnostics", "בדיקה או תיקון מאושר", "diagnosticAction"),
    ("GET", "/v2/workbench/root", "workspaceRoot", "שורש Workbench התחום", None),
    ("PATCH", "/v2/workbench/root", "setWorkspaceRoot", "בחירת שורש Workbench", "setWorkspaceRoot"),
    ("GET", "/v2/workbench/tree", "workspaceTree", "עץ קבצים תחום", None),
    ("GET", "/v2/workbench/file", "workspaceFile", "תצוגה מקדימה תחומה", None),
    ("GET", "/v2/workbench/artifacts", "artifacts", "תוצרים בתיקיית העבודה", None),
    ("GET", "/v2/conversations/{session_id}/canvases", "canvases", "רשימת Canvas לשיחה", None),
    ("GET", "/v2/conversations/{session_id}/canvases/{canvas_id}", "canvas", "מסמך Canvas מבודד", None),
    ("PATCH", "/v2/conversations/{session_id}/canvases/{canvas_id}", "canvasAction", "עדכון פריסת או מצב Canvas", "canvasAction"),
    ("GET", "/v2/browser/import/sources", "browserImportSources", "פרופילי Chromium זמינים לייבוא יזום", None),
    ("POST", "/v2/browser/import", "browserImport", "ייבוא מבוסס עותק ללא סיסמאות", "browserImport"),
    ("GET", "/v2/browser/legacy-migration", "legacyBrowserMigrationStatus", "מיגרציית דפדפן ישן מגובה", None),
    ("POST", "/v2/browser/legacy-migration", "completeLegacyBrowserMigration", "אישור החלת מיגרציית הדפדפן", "legacyBrowserMigration"),
    ("POST", "/v2/workbench/open", "openWorkspaceFile", "פתיחה חיצונית של קובץ תחום", "openWorkspaceFile"),
    ("POST", "/v2/workbench/terminals", "createTerminal", "יצירת מסוף PowerShell בבעלות Core", None),
    ("GET", "/v2/workbench/terminals/{terminal_id}", "readTerminal", "קריאת פלט מסוף", None),
    ("POST", "/v2/workbench/terminals/{terminal_id}", "writeTerminal", "קלט או אתחול מסוף", "terminalAction"),
    ("DELETE", "/v2/workbench/terminals/{terminal_id}", "closeTerminal", "סגירת מסוף", None),
    ("GET", "/v2/events", "subscribeEvents", "WebSocket מאומת עם replay", None),
]


def validate_request(schema_name, payload):
    schema = REQUEST_SCHEMAS.get(str(schema_name or ""))
    if schema is None:
        return []
    validator = Draft202012Validator(schema)
    return sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))


def contract_document():
    return {
        "$schema": SCHEMA_DIALECT,
        "contract": "Smarti Desktop Control Plane",
        "version": CONTRACT_VERSION,
        "base_path": "/v2",
        "security": {
            "transport": "loopback-only",
            "authentication": "Authorization: Bearer <per-launch-token>",
            "allowed_origins": ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"],
            "secrets": "masked metadata only; plaintext is accepted only by explicit set/validate commands",
        },
        "requests": copy.deepcopy(REQUEST_SCHEMAS),
        "operations": [
            {
                "method": method,
                "path": path,
                "operation_id": operation_id,
                "summary_he": summary,
                "request_schema": schema_name,
            }
            for method, path, operation_id, summary, schema_name in OPERATIONS
        ],
        "event": {
            "cursor": "event_id",
            "ordering": "strictly increasing durable event_id",
            "fields": ["event_id", "sequence", "event_type", "request_id", "session_id", "run_id", "payload", "created_at"],
        },
    }


def _typescript_type(schema):
    if "enum" in schema:
        return " | ".join(json.dumps(value, ensure_ascii=False) for value in schema["enum"])
    kind = schema.get("type")
    if kind == "string":
        return "string"
    if kind in {"integer", "number"}:
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "array":
        return f"Array<{_typescript_type(schema.get('items', {}))}>"
    if kind == "object":
        return "Record<string, unknown>"
    return "unknown"


def typescript_definitions():
    lines = [
        "// Generated from smarti/control_plane_contract.py. Do not edit by hand.",
        f"export const SMARTI_DESKTOP_CONTRACT_VERSION = {json.dumps(CONTRACT_VERSION)} as const;",
        "export interface ApiEnvelope<T> { request_id: string; data: T }",
        "export interface ApiError { request_id: string; error: string; detail?: string; fields?: string[] }",
        "export interface DesktopEvent { event_id: number; sequence: number; event_type: string; request_id: string; session_id: string; run_id: string; payload: Record<string, unknown>; created_at: string }",
    ]
    for name, schema in REQUEST_SCHEMAS.items():
        required = set(schema.get("required", []))
        lines.append(f"export interface {name[0].upper() + name[1:]}Request {{")
        for key, prop in schema.get("properties", {}).items():
            optional = "" if key in required else "?"
            lines.append(f"  {key}{optional}: {_typescript_type(prop)};")
        lines.append("}")
    lines.append("")
    return "\n".join(lines)


def write_generated_contracts(repository_root):
    root = Path(repository_root)
    generated = root / "desktop-contract"
    generated.mkdir(parents=True, exist_ok=True)
    json_path = generated / "v2.contract.json"
    ts_path = generated / "v2.generated.d.ts"
    json_path.write_text(
        json.dumps(contract_document(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ts_path.write_text(typescript_definitions(), encoding="utf-8")
    return json_path, ts_path
