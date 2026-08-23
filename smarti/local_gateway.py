"""Authenticated loopback HTTP/WebSocket control plane for Smarti Core."""
from __future__ import annotations

import asyncio
import getpass
import copy
import json
import logging
import mimetypes
import os
import secrets
import threading
import time
import uuid
from datetime import datetime

from aiohttp import WSMsgType, web

from .attachments import attachment_from_path
from .common import (
    APP_VERSION, AUTONOMY_PROFILES, MODEL_PROVIDER_ORDER, SENSITIVE_SETTING_KEYS,
    USER_DATA_DIR, fetch_text_models_for_provider, mask_secret_value,
    model_reasoning_options, model_reasoning_setting, normalize_provider_name,
    provider_secret_key, sanitize_secret_value, set_model_reasoning_setting,
)
from .config import DEFAULT_SETTINGS, PUBLIC_BUILTIN_TOOLS
from .control_plane_contract import CONTRACT_VERSION, contract_document, validate_request
from .canvas_model import (
    canvas_artifacts_from_messages,
    materialize_canvas_html,
    normalize_canvas_artifact,
)
from .browser_profile import discover_browser_profiles, import_profile_data
from .tauri_migration import legacy_browser_migration_payload, mark_legacy_browser_migration_applied
from .desktop_services import (
    TerminalRegistry, WorkspaceScope, log_snapshot, memory_action, memory_rows,
    safe_task_rows, settings_schema_document, task_action, tools_snapshot,
    usage_snapshot,
)


class RequestValidationError(ValueError):
    def __init__(self, detail, fields=None):
        super().__init__(detail)
        self.fields = list(fields or [])


class ScopedAttachmentRegistry:
    """Keep native-selected paths behind short-lived opaque handles."""

    def __init__(self, max_handles=256):
        self.max_handles = max(8, int(max_handles or 256))
        self._lock = threading.RLock()
        self._items = {}

    def _prune(self):
        now = time.monotonic()
        for key in [key for key, item in self._items.items() if item["expires_at"] <= now]:
            self._items.pop(key, None)
        overflow = len(self._items) - self.max_handles
        if overflow > 0:
            oldest = sorted(self._items, key=lambda key: self._items[key]["created_at"])
            for key in oldest[:overflow]:
                self._items.pop(key, None)

    def register(self, path, *, session_id="", ttl_seconds=3600):
        absolute = os.path.abspath(str(path or "").strip(' "\''))
        if not absolute or not os.path.isfile(absolute):
            raise RequestValidationError("attachment_file_not_found", ["path"])
        item = attachment_from_path(absolute, source="desktop_handle")
        if not item:
            raise RequestValidationError("attachment_registration_failed", ["path"])
        handle = secrets.token_urlsafe(24)
        now = time.monotonic()
        record = {
            "handle": handle,
            "session_id": str(session_id or ""),
            "attachment": item,
            "created_at": now,
            "expires_at": now + max(30, min(86400, int(ttl_seconds or 3600))),
        }
        with self._lock:
            self._items[handle] = record
            self._prune()
        return self.public(record)

    @staticmethod
    def public(record):
        item = record["attachment"]
        return {
            "handle": record["handle"], "session_id": record["session_id"],
            "name": str(item.get("name") or "attachment"),
            "mime_type": str(item.get("mime_type") or "application/octet-stream"),
            "kind": str(item.get("kind") or "document"),
            "size": int(item.get("size") or 0), "sha256": str(item.get("sha256") or ""),
        }

    def get(self, handle, *, session_id=""):
        with self._lock:
            self._prune()
            record = self._items.get(str(handle or ""))
            if not record:
                return None
            scoped = str(record.get("session_id") or "")
            if scoped and session_id and scoped != str(session_id):
                return None
            return copy.deepcopy(record)

    def resolve_many(self, handles, *, session_id=""):
        result = []
        for handle in handles or []:
            record = self.get(handle, session_id=session_id)
            if not record:
                raise RequestValidationError(
                    "invalid_or_expired_attachment_handle", ["attachment_handles"]
                )
            result.append(record["attachment"])
        return result


class SmartiLocalGateway:
    API_VERSION = "v2"
    LEGACY_API_VERSION = "v1"
    MAX_BODY_BYTES = 1024 * 1024
    MAX_WS_BATCH = 250
    ALLOWED_ORIGINS = frozenset({
        "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
    })

    def __init__(self, core, token, port=8765):
        self.core = core
        self.token = str(token or "")
        self.requested_port = max(0, min(65535, int(port or 0)))
        self.port = 0
        self._thread = None
        self._loop = None
        self._runner = None
        self._site = None
        self._started = threading.Event()
        self._startup_error = None
        self._attachments = ScopedAttachmentRegistry()
        self._workspace = WorkspaceScope(core)
        self._terminal_sessions = TerminalRegistry(self._workspace)
        self._idempotency_lock = threading.RLock()
        self._runtime_file = os.path.join(USER_DATA_DIR, "local-gateway.json")

    @staticmethod
    def _request_id(request):
        supplied = str(request.headers.get("X-Request-ID") or "").strip()
        return supplied[:200] if supplied else uuid.uuid4().hex

    def _authorized(self, request):
        supplied = str(request.headers.get("Authorization") or "")
        expected = f"Bearer {self.token}"
        return secrets.compare_digest(supplied.encode(), expected.encode())

    def _origin_allowed(self, request):
        origin = str(request.headers.get("Origin") or "").strip()
        return not origin or origin in self.ALLOWED_ORIGINS

    async def _auth_middleware(self, request, handler):
        request["request_id"] = self._request_id(request)
        if not self._origin_allowed(request):
            return self._error(request, 403, "origin_forbidden")
        if request.path not in {"/v1/health", "/v2/health"} and not self._authorized(request):
            return self._error(request, 401, "unauthorized")
        try:
            return await handler(request)
        except RequestValidationError as exc:
            status = 413 if str(exc) == "request_body_too_large" else 400
            return self._error(request, status, "invalid_request", str(exc), exc.fields)
        except web.HTTPException as exc:
            return self._error(request, exc.status, exc.reason.lower().replace(" ", "_"))
        except Exception as exc:
            logging.exception("Desktop control-plane request failed")
            return self._error(request, 500, "internal_error", str(exc)[:300])

    @staticmethod
    def _security_headers():
        return {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}

    def _error(self, request, status, error, detail="", fields=None):
        payload = {"request_id": request.get("request_id", ""), "error": str(error)}
        if detail:
            payload["detail"] = str(detail)[:500]
        if fields:
            payload["fields"] = list(fields)
        return web.json_response(payload, status=int(status), headers=self._security_headers())

    def _ok(self, request, data, status=200, headers=None):
        combined = self._security_headers()
        combined.update(headers or {})
        return web.json_response(
            {"request_id": request["request_id"], "data": data}, status=int(status), headers=combined,
        )

    async def _body(self, request, schema_name=None):
        if request.content_length is not None and request.content_length > self.MAX_BODY_BYTES:
            raise RequestValidationError("request_body_too_large")
        if not request.can_read_body:
            payload = {}
        else:
            try:
                payload = await request.json(loads=json.loads)
            except Exception as exc:
                raise RequestValidationError("request_body_must_be_valid_json") from exc
        if not isinstance(payload, dict):
            raise RequestValidationError("request_body_must_be_an_object")
        errors = validate_request(schema_name, payload)
        if errors:
            fields = [".".join(str(part) for part in error.absolute_path) for error in errors]
            raise RequestValidationError(errors[0].message, fields)
        return payload

    async def _idempotent(self, request, schema_name, action):
        payload = await self._body(request, schema_name)
        key = str(request.headers.get("Idempotency-Key") or "").strip()[:200]
        scope = f"{request.method}:{request.path}"
        with self._idempotency_lock:
            if key:
                cached = self.core.chat_store.idempotency_response(scope, key)
                if cached is not None:
                    return self._ok(request, cached, 200, {"Idempotency-Replayed": "true"})
            data, status = action(payload)
            if key:
                self.core.chat_store.save_idempotency_response(scope, key, data)
        return self._ok(request, data, status)

    async def _idempotent_empty(self, request, action):
        return await self._idempotent(request, None, lambda _payload: action())

    @staticmethod
    def _query_int(request, name, default, minimum, maximum):
        raw = request.query.get(name)
        if raw in (None, ""):
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise RequestValidationError("invalid_pagination", [name]) from exc
        return max(minimum, min(maximum, value))

    def _health_payload(self):
        provider = getattr(self.core, "service_health_callback", None)
        payload = provider() if callable(provider) else {}
        if not isinstance(payload, dict):
            payload = {}
        payload.update({"ok": True, "api": "v2", "contract_version": CONTRACT_VERSION, "pid": os.getpid()})
        return payload

    # `/v1` remains wire-compatible with the pre-migration local/channel API.
    async def _v1_health(self, request):
        payload = self._health_payload()
        payload["api"] = "v1"
        return web.json_response(payload, headers=self._security_headers())

    async def _v1_get(self, request):
        resource = request.match_info["resource"]
        store = self.core.chat_store
        if resource == "sessions":
            data = {"sessions": store.list_sessions(request.query.get("q", ""))}
        elif resource == "workspaces":
            data = {"workspaces": store.list_workspaces()}
        elif resource == "runs":
            data = {"runs": store.list_runs(
                session_id=request.query.get("session_id", ""),
                statuses=request.query.getall("status", []) or None,
            )}
        elif resource == "approvals":
            data = {"approvals": store.pending_approvals(request.query.get("session_id") or None)}
        else:
            raise web.HTTPNotFound()
        return web.json_response(data, headers=self._security_headers())

    async def _v1_run_events(self, request):
        return web.json_response({"events": self.core.chat_store.run_events(
            request.match_info["run_id"], after_sequence=request.query.get("after", 0),
        )}, headers=self._security_headers())

    async def _v1_post(self, request):
        payload = await self._body(request)
        store = self.core.chat_store
        route = request.match_info.route.resource.canonical
        key = str(request.headers.get("Idempotency-Key") or "").strip()[:200]
        scope = request.path.strip("/")
        if key:
            cached = store.idempotency_response(scope, key)
            if cached is not None:
                return web.json_response(cached)
        status = 202
        if route == "/v1/sessions":
            session = store.create_session(set_active=False, workspace_id=str(payload.get("workspace_id") or "") or None)
            if str(payload.get("title") or "").strip():
                store.rename_session(session["id"], payload["title"])
                session = store.session_metadata(session["id"])
            data, status = {"session": session}, 201
        elif route == "/v1/workspaces":
            identifier = store.create_workspace(
                title=str(payload.get("title") or "Workspace"), root_path=str(payload.get("root_path") or ""),
                metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            )
            data, status = {"workspace": store.workspace(identifier)}, 201
        elif route.endswith("/messages"):
            session_id = request.match_info["session_id"]
            if not store.has_session(session_id):
                return web.json_response({"error": "session_not_found"}, status=404)
            text = str(payload.get("text") or "")
            attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
            if not text.strip() and not attachments:
                return web.json_response({"error": "text_or_attachments_required"}, status=400)
            handle = self.core.run_manager.submit(
                session_id, text, attachments=attachments, source=str(payload.get("source") or "local_gateway"),
                metadata={"channel": str(payload.get("channel") or "local_api")},
                workspace_id=str(payload.get("workspace_id") or "") or None,
            )
            data = {"run_id": handle.run_id, "session_id": session_id, "status": "queued"}
        elif route.endswith("/cancel"):
            run_id = request.match_info["run_id"]
            changed = self.core.run_manager.cancel(run_id)
            data, status = {"run_id": run_id, "cancel_requested": bool(changed)}, 200 if changed else 404
        elif route.endswith("/read"):
            session_id = request.match_info["session_id"]
            count = store.mark_session_read(session_id, str(payload.get("actor_id") or "local_gateway"))
            data, status = {"session_id": session_id, "marked_read": int(count)}, 200
        elif route.endswith("/resolve"):
            approval_id = request.match_info["approval_id"]
            approved = bool(payload.get("approved"))
            changed = self.core.run_manager.resolve_approval(approval_id, approved)
            data, status = {"approval_id": approval_id, "resolved": bool(changed), "approved": approved}, 200 if changed else 409
        elif "/channels/" in route:
            channel, session_id = request.match_info["channel"], str(payload.get("session_id") or "")
            if not session_id:
                session_id = str(store.create_session(set_active=False)["id"])
            handle = self.core.run_manager.submit(
                session_id, str(payload.get("text") or ""), attachments=payload.get("attachments") or [],
                source=f"channel:{channel}", metadata={"channel": channel, "remote_sender": str(payload.get("sender") or "")[:200]},
                workspace_id=str(payload.get("workspace_id") or "") or None,
            )
            data = {"run_id": handle.run_id, "session_id": session_id, "status": "queued"}
        else:
            raise web.HTTPNotFound()
        if key:
            store.save_idempotency_response(scope, key, data)
        return web.json_response(data, status=status, headers=self._security_headers())

    async def _v2_health(self, request):
        return self._ok(request, self._health_payload())

    async def _v2_version(self, request):
        return self._ok(request, {"product": APP_VERSION, "contract": CONTRACT_VERSION, "api": "v2"})

    async def _v2_capabilities(self, request):
        return self._ok(request, {
            "operations": [item["operation_id"] for item in contract_document()["operations"]],
            "websocket": True, "event_replay": True, "legacy_v1": True,
        })

    async def _v2_bootstrap(self, request):
        current_provider = normalize_provider_name(getattr(self.core, "mode", "") or self.core.settings.get("mode") or "gemini")
        current_model = str(self.core.settings.get(f"selected_{current_provider}_model") or "")
        return self._ok(request, {
            "version": {"product": APP_VERSION, "contract": CONTRACT_VERSION},
            "health": self._health_payload(), "conversations": self.core.chat_store.list_sessions(include_empty="latest")[:50],
            "workspaces": self.core.chat_store.list_workspaces(),
            "pending_approvals": self.core.chat_store.pending_approvals(),
            "unread_count": self.core.chat_store.unread_count(), "settings": self._safe_settings(),
            "display_name": str(getpass.getuser() or "").strip()[:80],
            "chat_models": {
                "providers": list(MODEL_PROVIDER_ORDER),
                "provider": current_provider,
                "model": current_model,
                "reasoning_effort": model_reasoning_setting(self.core.settings, current_provider, current_model),
                "reasoning_options": [
                    {"value": value, "label": label}
                    for value, label in model_reasoning_options(current_provider, current_model)
                ],
            },
        })

    async def _workspaces(self, request):
        store = self.core.chat_store
        if request.method == "GET":
            return self._ok(request, {"items": store.list_workspaces()})
        return await self._idempotent(request, "createWorkspace", lambda payload: ({"workspace": store.workspace(
            store.create_workspace(payload.get("title") or "Workspace", payload.get("root_path") or "", payload.get("metadata") or {})
        )}, 201))

    async def _workspace_item(self, request):
        store, identifier = self.core.chat_store, request.match_info["workspace_id"]
        if request.method == "PATCH":
            return await self._idempotent(request, "patchWorkspace", lambda payload: (
                {"workspace": store.update_workspace(identifier, **payload)}, 200,
            ))
        return await self._idempotent_empty(request, lambda: (
            {"workspace_id": identifier, "deleted": store.delete_workspace(identifier)}, 200,
        ))

    async def _conversations(self, request):
        store = self.core.chat_store
        if request.method == "GET":
            items = store.list_sessions(request.query.get("q", ""), include_empty="latest")
            limit = self._query_int(request, "limit", 50, 1, 200)
            offset = self._query_int(request, "offset", 0, 0, 1000000)
            return self._ok(request, {"items": items[offset:offset + limit], "total": len(items), "offset": offset, "limit": limit})
        def create(payload):
            session = store.create_session(False, payload.get("workspace_id") or None)
            if str(payload.get("title") or "").strip():
                store.rename_session(session["id"], payload["title"])
            return {"conversation": store.session_metadata(session["id"])}, 201
        return await self._idempotent(request, "createConversation", create)

    async def _conversation_item(self, request):
        store, session_id = self.core.chat_store, request.match_info["session_id"]
        if request.method == "GET":
            item = store.session_metadata(session_id)
            return self._ok(request, {"conversation": item}, 200 if item else 404)
        if request.method == "PATCH":
            def patch(payload):
                if "title" in payload:
                    store.rename_session(session_id, payload["title"])
                if "workspace_id" in payload:
                    store.assign_session_workspace(session_id, payload["workspace_id"] or None)
                if "pinned" in payload:
                    store.set_pinned(session_id, payload["pinned"])
                return {"conversation": store.session_metadata(session_id)}, 200
            return await self._idempotent(request, "patchConversation", patch)
        return await self._idempotent_empty(request, lambda: (
            {"session_id": session_id, "deleted": store.delete_session(session_id)}, 200,
        ))

    async def _messages(self, request):
        return self._ok(request, self.core.chat_store.messages_page(
            request.match_info["session_id"], request.query.get("before"),
            self._query_int(request, "limit", 32, 1, 500),
        ))

    async def _submit_run(self, request):
        session_id = request.match_info["session_id"]
        if not self.core.chat_store.has_session(session_id):
            return self._error(request, 404, "session_not_found")
        def submit(payload):
            text = str(payload.get("text") or "")
            attachments = self._attachments.resolve_many(payload.get("attachment_handles") or [], session_id=session_id)
            if not text.strip() and not attachments:
                raise RequestValidationError("text_or_attachments_required", ["text", "attachment_handles"])
            provider_mode = normalize_provider_name(payload.get("provider_mode") or getattr(self.core, "mode", "") or "gemini")
            if provider_mode not in MODEL_PROVIDER_ORDER:
                raise RequestValidationError("unknown_provider", ["provider_mode"])
            model_name = str(payload.get("model_name") or self.core.settings.get(f"selected_{provider_mode}_model") or "").strip()
            handle = self.core.run_manager.submit(
                session_id, text, attachments=attachments, source=str(payload.get("source") or "desktop_v2"),
                metadata={"channel": "desktop", "request_id": request["request_id"], "provider_mode": provider_mode, "model_name": model_name},
                workspace_id=str(payload.get("workspace_id") or "") or None,
            )
            self.core.chat_store.append_run_event(handle.run_id, "command_accepted", {"request_id": request["request_id"]})
            return {"run_id": handle.run_id, "session_id": session_id, "status": "queued"}, 202
        return await self._idempotent(request, "submitRun", submit)

    async def _mark_read(self, request):
        session_id = request.match_info["session_id"]
        return await self._idempotent(request, "markRead", lambda payload: ({
            "session_id": session_id,
            "marked_read": self.core.chat_store.mark_session_read(session_id, payload.get("actor_id") or "desktop_v2"),
        }, 200))

    async def _runs(self, request):
        return self._ok(request, {"items": self.core.chat_store.list_runs(
            request.query.get("session_id") or None, request.query.getall("status", []) or None, request.query.get("limit", 100),
        )})

    async def _run_item(self, request):
        run = self.core.chat_store.run(request.match_info["run_id"])
        return self._ok(request, {"run": run}, 200 if run else 404)

    async def _cancel_run(self, request):
        run_id = request.match_info["run_id"]
        def cancel():
            changed = self.core.run_manager.cancel(run_id)
            return {"run_id": run_id, "cancel_requested": changed}, 200 if changed else 409
        return await self._idempotent_empty(request, cancel)

    async def _run_events(self, request):
        run_id = request.match_info["run_id"]
        run = self.core.chat_store.run(run_id) or {}
        request_id = str((run.get("metadata") or {}).get("request_id") or "")
        items = self.core.chat_store.run_events(run_id, request.query.get("after_sequence", 0), request.query.get("limit", 500))
        for item in items:
            item["event_id"], item["session_id"], item["request_id"] = item.pop("id", 0), str(run.get("session_id") or ""), request_id
        return self._ok(request, {"items": items})

    async def _events_replay(self, request):
        cursor = self._query_int(request, "after_event_id", 0, 0, 2_000_000_000)
        session_id = str(request.query.get("session_id") or "")
        return self._ok(request, {"items": self.core.chat_store.events_after(cursor, session_id or None, self.MAX_WS_BATCH)})

    async def _tts_start(self, request):
        payload = await self._body(request, "startTts")
        text = str(payload.get("text") or "").strip()
        if not text or len(text) > 100_000:
            raise RequestValidationError("tts_text_required", ["text"])
        threading.Thread(target=self.core.speak_text, args=(text,), daemon=True, name="SmartiDesktopTTS").start()
        return self._ok(request, {"started": True}, 202)

    async def _tts_stop(self, request):
        self.core.stop_speaking()
        return self._ok(request, {"stopped": True})

    async def _tts_status(self, request):
        return self._ok(request, {"is_playing": bool(getattr(self.core, "_tts_is_playing", False))})

    async def _approvals(self, request):
        return self._ok(request, {"items": self.core.chat_store.pending_approvals(request.query.get("session_id") or None)})

    async def _resolve_approval(self, request):
        approval_id = request.match_info["approval_id"]
        def resolve(payload):
            approved = bool(payload["approved"])
            changed = self.core.run_manager.resolve_approval(approval_id, approved)
            return {"approval_id": approval_id, "resolved": changed, "approved": approved}, 200 if changed else 409
        return await self._idempotent(request, "resolveApproval", resolve)

    def _safe_settings(self):
        values = {key: copy.deepcopy(value) for key, value in self.core.settings.items() if key not in SENSITIVE_SETTING_KEYS and key != "_runtime_trace"}
        secret_state = {}
        for key in sorted(SENSITIVE_SETTING_KEYS):
            value = sanitize_secret_value(self.core.settings.get(key))
            secret_state[key] = {"configured": bool(value), "masked": mask_secret_value(value) if value else ""}
        return {"values": values, "secrets": secret_state}

    async def _settings_schema(self, request):
        schema = settings_schema_document()
        if "api_mode" in schema["fields"]:
            schema["fields"]["api_mode"]["options"] = list(MODEL_PROVIDER_ORDER)
        if "ssl_trust_mode" in schema["fields"]:
            schema["fields"]["ssl_trust_mode"]["options"] = ["system", "custom_ca", "legacy_insecure"]
        for key, state in self._safe_settings()["secrets"].items():
            existing = schema["fields"].get(key, {})
            schema["fields"][key] = {
                "key": key, "label": existing.get("label", key.replace("_", " ")), "group": existing.get("group", "providers"),
                "group_label": existing.get("group_label", "ספקים ומודלים"), "type": "secret", "secret": True,
                "writable": True, "restart_required": False, "advanced": False,
                "configured": state["configured"], "masked": state["masked"],
            }
        return self._ok(request, schema)

    async def _tasks(self, request):
        if request.method == "GET":
            return self._ok(request, {"items": safe_task_rows(self.core)})
        payload = await self._body(request, "taskAction")
        action = str(payload.get("action") or "").strip().lower()
        return self._ok(request, task_action(self.core, action, payload))

    async def _memories(self, request):
        return self._ok(request, memory_rows(
            self.core, request.query.get("query", ""), request.query.get("status", "active"),
            request.query.get("memory_type", "any"),
        ))

    async def _memory_item(self, request):
        payload = await self._body(request, "memoryAction") if request.can_read_body else {}
        action = str(payload.get("action") or ("delete" if request.method == "DELETE" else "details")).lower()
        return self._ok(request, memory_action(self.core, action, request.match_info["memory_id"], payload))

    async def _tools(self, request):
        if request.method == "GET":
            return self._ok(request, tools_snapshot(self.core))
        payload = await self._body(request, "toolAction")
        action, kind, name = (str(payload.get(key) or "").strip() for key in ("action", "kind", "name"))
        if action == "set_trust" and kind in {"custom", "mcp", "skill"} and name:
            self.core.tool_registry.set_trust(kind, name, bool(payload.get("trusted")), metadata={"trusted_from": "tauri_desktop"})
        elif action == "set_enabled" and kind == "builtin" and name in PUBLIC_BUILTIN_TOOLS:
            config = copy.deepcopy(self.core.settings.get("tools_config", {}))
            config[name] = bool(payload.get("enabled"))
            self.core.settings["tools_config"] = config
            self.core._save_settings()
            load_prompt = getattr(self.core, "_load_system_prompt", None)
            if callable(load_prompt):
                self.core.system_prompt = load_prompt()
        elif action == "refresh":
            self.core.refresh_extension_catalogs(force=True, rebuild_prompt=True)
        elif action == "install_skill":
            self.core.install_local_skill_package(str(payload.get("path") or ""))
        elif action == "install_custom":
            self.core.install_python_tool_from_path(str(payload.get("path") or ""))
        elif action == "install_mcp":
            self.core.install_mcp_manual(package=str(payload.get("package") or ""), config_path=str(payload.get("path") or ""))
        else:
            raise RequestValidationError("unknown_tool_action", ["action"])
        return self._ok(request, tools_snapshot(self.core))

    async def _usage(self, request):
        return self._ok(request, usage_snapshot(self.core))

    async def _logs(self, request):
        return self._ok(request, log_snapshot(request.query.get("limit", 500), request.query.get("personal", "hidden") != "shown"))

    async def _about(self, request):
        return self._ok(request, {
            "name": "Smarti AI Agent for Windows", "version": APP_VERSION,
            "contract_version": CONTRACT_VERSION, "python": __import__("sys").version.split()[0],
            "data_dir": USER_DATA_DIR,
            "description": "סוכן עבודה אישי ל-Windows שמחבר צ'אט, כלים מקומיים, קבצים, דפדפן, זיכרון ומשימות רקע תחת בקרות בטיחות.",
        })

    async def _diagnostics(self, request):
        from .doctor import SmartiDiagnostic
        payload = await self._body(request, "diagnosticAction")
        if payload.get("action") == "repair":
            action_id = str(payload.get("repair_id") or "")
            message = await asyncio.to_thread(SmartiDiagnostic(self.core).perform_repair, action_id)
            return self._ok(request, {"message": str(message)})
        results = await asyncio.to_thread(SmartiDiagnostic(self.core).run, bool(payload.get("include_network")))
        return self._ok(request, {"items": [item.to_dict() for item in results]})

    async def _workspace_root(self, request):
        if request.method == "GET":
            return self._ok(request, self._workspace.root_info())
        payload = await self._body(request, "setWorkspaceRoot")
        try:
            value = self._workspace.set_root(payload.get("path"))
        except ValueError as exc:
            raise RequestValidationError(str(exc), ["path"]) from exc
        return self._ok(request, value)

    async def _canvases(self, request):
        session_id = request.match_info["session_id"]
        if not self.core.chat_store.has_session(session_id):
            return self._error(request, 404, "session_not_found")
        items = canvas_artifacts_from_messages(
            self.core.chat_store.messages(session_id), include_closed=True,
        )
        return self._ok(request, {"items": [{
            "id": item["id"], "title": item["title"],
            "created_at": item["created_at"], "closed": bool(item.get("closed")),
        } for item in items]})

    async def _canvas_item(self, request):
        session_id, canvas_id = request.match_info["session_id"], request.match_info["canvas_id"]
        if not self.core.chat_store.has_session(session_id):
            return self._error(request, 404, "session_not_found")
        items = canvas_artifacts_from_messages(
            self.core.chat_store.messages(session_id), include_closed=True,
        )
        artifact = next((item for item in items if item["id"] == canvas_id), None)
        if artifact is None:
            return self._error(request, 404, "canvas_not_found")
        if request.method == "GET":
            allow_remote = str(request.query.get("allow_remote_images") or "").lower() in {"1", "true", "yes"}
            result = copy.deepcopy(artifact)
            result["document"] = materialize_canvas_html(result, allow_remote_images=allow_remote)
            result.pop("html", None)
            result.pop("images", None)
            result["remote_images_enabled"] = allow_remote
            return self._ok(request, {"canvas": result})
        payload = await self._body(request, "canvasAction")
        action = str(payload.get("action") or "layout").strip().lower()
        if action == "layout":
            positions = payload.get("button_positions")
            candidate = normalize_canvas_artifact({**artifact, "button_positions": positions})
            if candidate is None or not isinstance(positions, list) or len(positions) > 64:
                raise RequestValidationError("invalid_canvas_layout", ["button_positions"])
            changed = self.core.chat_store.update_canvas_layout(
                canvas_id, candidate.get("button_positions", []), session_id,
            )
        elif action in {"close", "reopen"}:
            changed = self.core.chat_store.update_canvas_state(
                canvas_id, closed=action == "close", session_id=session_id,
            )
        else:
            raise RequestValidationError("unknown_canvas_action", ["action"])
        return self._ok(request, {"canvas_id": canvas_id, "changed": bool(changed), "action": action})

    async def _browser_import_sources(self, request):
        items = discover_browser_profiles()
        return self._ok(request, {"items": [{
            "id": f"{item.browser_id}:{index}", "browser_id": item.browser_id,
            "browser_name": item.browser_name, "profile_name": item.profile_name,
        } for index, item in enumerate(items)]})

    async def _browser_import(self, request):
        payload = await self._body(request, "browserImport")
        sources = discover_browser_profiles()
        try:
            browser_id, raw_index = str(payload.get("source_id") or "").rsplit(":", 1)
            source = sources[int(raw_index)]
            if source.browser_id != browser_id:
                raise ValueError
        except (ValueError, IndexError):
            raise RequestValidationError("browser_import_source_not_found", ["source_id"])
        result = await asyncio.to_thread(
            import_profile_data, source,
            include_cookies=bool(payload.get("cookies", False)),
            include_history=bool(payload.get("history", True)),
            include_bookmarks=bool(payload.get("bookmarks", True)),
        )
        return self._ok(request, {
            "source": {"browser_name": source.browser_name, "profile_name": source.profile_name},
            "history": result.get("history", []), "bookmarks": result.get("bookmarks", []),
            "cookies": result.get("cookies", []), "cookie_stats": result.get("cookie_stats", {}),
            "imported_at": result.get("imported_at", ""),
        })

    async def _legacy_browser_migration(self, request):
        if request.method == "GET":
            return self._ok(request, legacy_browser_migration_payload(USER_DATA_DIR))
        payload = await self._body(request, "legacyBrowserMigration")
        if str(payload.get("action") or "").strip().lower() != "applied":
            raise RequestValidationError("invalid_migration_action", ["action"])
        return self._ok(request, mark_legacy_browser_migration_applied(USER_DATA_DIR))

    async def _workspace_tree(self, request):
        try:
            value = self._workspace.tree(request.query.get("path", ""), request.query.get("depth", 2))
        except ValueError as exc:
            raise RequestValidationError(str(exc), ["path"]) from exc
        return self._ok(request, value)

    async def _workspace_file(self, request):
        try:
            value = self._workspace.file(request.query.get("path", ""))
        except ValueError as exc:
            raise RequestValidationError(str(exc), ["path"]) from exc
        return self._ok(request, value)

    async def _artifacts(self, request):
        return self._ok(request, self._workspace.artifacts())

    async def _workspace_open(self, request):
        payload = await self._body(request, "openWorkspaceFile")
        try:
            value = self._workspace.open_external(payload.get("path"))
        except ValueError as exc:
            raise RequestValidationError(str(exc), ["path"]) from exc
        return self._ok(request, value)

    async def _terminals(self, request):
        if request.method == "POST":
            return self._ok(request, self._terminal_sessions.create(), 201)
        raise RequestValidationError("method_not_allowed")

    async def _terminal_item(self, request):
        identifier = request.match_info["terminal_id"]
        if request.method == "GET":
            return self._ok(request, self._terminal_sessions.read(identifier))
        if request.method == "DELETE":
            return self._ok(request, self._terminal_sessions.close(identifier))
        payload = await self._body(request, "terminalAction")
        action = str(payload.get("action") or "write")
        if action == "write":
            return self._ok(request, self._terminal_sessions.write(identifier, payload.get("text", "")))
        if action == "restart":
            self._terminal_sessions.close(identifier)
            return self._ok(request, self._terminal_sessions.create(), 201)
        raise RequestValidationError("unknown_terminal_action", ["action"])

    async def _settings(self, request):
        if request.method == "GET":
            return self._ok(request, self._safe_settings())
        def patch(payload):
            values = payload["values"]
            bad = [key for key in values if key not in DEFAULT_SETTINGS or key in SENSITIVE_SETTING_KEYS or key == "_runtime_trace"]
            if bad:
                raise RequestValidationError("unknown_or_secret_setting", bad)
            for key, value in values.items():
                default = DEFAULT_SETTINGS[key]
                if default is not None and not isinstance(value, type(default)):
                    raise RequestValidationError("setting_type_mismatch", [key])
            self.core.settings.update(copy.deepcopy(values))
            autonomy_mode = str(values.get("autonomy_mode") or "")
            if autonomy_mode in AUTONOMY_PROFILES:
                profile = AUTONOMY_PROFILES[autonomy_mode]
                self.core.settings["custom_permission_profile_enabled"] = False
                for key, value in profile.items():
                    self.core.settings[key] = copy.deepcopy(value)
            save_settings = getattr(self.core, "_save_settings", None)
            if callable(save_settings):
                save_settings()
            if any(key.startswith("ssl_") or key == "allow_insecure_ssl_compat" for key in values):
                sync_ssl = getattr(self.core, "_sync_ssl_compat_env", None)
                if callable(sync_ssl):
                    sync_ssl()
            if any(key in {"api_mode", "local_server_url", "local_llm_url"} or key.startswith("selected_") for key in values):
                setup_model = getattr(self.core, "setup_model", None)
                if callable(setup_model):
                    setup_model()
            if any(key.startswith(("mcp_", "enable_mcp", "enable_skills")) for key in values):
                refresh = getattr(self.core, "refresh_extension_catalogs", None)
                if callable(refresh):
                    refresh(force=True, rebuild_prompt=True)
            elif any(key in {"autonomy_mode", "local_fast_mode_enabled", "enable_visual_surfaces", "enable_web_canvas"} for key in values):
                load_prompt = getattr(self.core, "_load_system_prompt", None)
                if callable(load_prompt):
                    self.core.system_prompt = load_prompt()
            return self._safe_settings(), 200
        return await self._idempotent(request, "patchSettings", patch)

    async def _secret(self, request):
        key = request.match_info["secret_key"]
        if key not in SENSITIVE_SETTING_KEYS:
            return self._error(request, 404, "unknown_secret")
        if request.method == "PUT":
            def set_value(payload):
                self.core.settings[key] = sanitize_secret_value(payload["value"])
                self.core._save_settings()
                return {"secret_key": key, "configured": True, "masked": mask_secret_value(self.core.settings[key])}, 200
            return await self._idempotent(request, "setSecret", set_value)
        def delete_secret():
            self.core.mark_secret_for_deletion(key)
            self.core._save_settings()
            return {"secret_key": key, "configured": False, "deleted": True}, 200
        return await self._idempotent_empty(request, delete_secret)

    def _provider_models(self, provider, payload=None, *, validate=False):
        provider, payload = normalize_provider_name(provider), payload or {}
        if provider not in MODEL_PROVIDER_ORDER:
            raise RequestValidationError("unknown_provider", ["provider"])
        supplied = sanitize_secret_value(payload.get("secret"))
        secret = supplied or (self.core.ensure_provider_secret(provider) if provider_secret_key(provider) else "")
        local_url = str(payload.get("local_url") or self.core.settings.get("local_llm_url") or "")
        models, ok, message = fetch_text_models_for_provider(
            provider, api_key=secret, local_url=local_url, ssl_settings=self.core.settings, validate_key=validate,
        )
        return {"provider": provider, "ok": bool(ok), "message": str(message or ""), "models": models}

    async def _validate_provider(self, request):
        return self._ok(request, self._provider_models(
            request.match_info["provider"], await self._body(request, "validateProvider"), validate=True,
        ))

    async def _discover_models(self, request):
        return self._ok(request, self._provider_models(request.match_info["provider"]))

    async def _set_model_reasoning(self, request):
        provider = normalize_provider_name(request.match_info["provider"])

        if request.method == "GET":
            model = str(request.query.get("model") or "").strip()
            if not model:
                return self._error(request, 400, "missing_model", "model")
            options = model_reasoning_options(provider, model)
            return self._ok(request, {
                "provider": provider,
                "model": model,
                "reasoning_effort": model_reasoning_setting(self.core.settings, provider, model),
                "reasoning_options": [
                    {"value": value, "label": label} for value, label in options
                ],
            })

        def update(payload):
            model = str(payload["model"]).strip()
            available = dict(model_reasoning_options(provider, model))
            effort = str(payload["effort"]).strip().lower()
            if effort not in available:
                raise RequestValidationError("unsupported_reasoning_effort", ["effort"])
            selected = set_model_reasoning_setting(self.core.settings, provider, model, effort)
            save_settings = getattr(self.core, "_save_settings", None)
            if callable(save_settings):
                save_settings()
            return {
                "provider": provider,
                "model": model,
                "reasoning_effort": selected,
                "reasoning_options": [
                    {"value": value, "label": label} for value, label in available.items()
                ],
            }, 200

        return await self._idempotent(request, "setModelReasoning", update)

    async def _codex_quota(self, request):
        from .codex_signin import CodexSignInProvider

        try:
            quota = await asyncio.to_thread(
                CodexSignInProvider(USER_DATA_DIR).read_rate_limits,
                12,
            )
        except Exception as exc:
            logging.warning("Could not refresh Codex quota through the control plane: %s", exc)
            return self._error(request, 503, "codex_quota_unavailable", str(exc))
        return self._ok(request, quota)

    async def _register_attachment(self, request):
        return await self._idempotent(request, "registerAttachment", lambda payload: ({"attachment": self._attachments.register(
            payload["path"], session_id=payload.get("session_id") or "", ttl_seconds=payload.get("ttl_seconds", 3600),
        )}, 201))

    async def _read_attachment(self, request):
        record = self._attachments.get(request.match_info["handle"])
        if not record:
            return self._error(request, 404, "attachment_handle_not_found")
        item = record["attachment"]
        response = web.FileResponse(item["path"], headers=self._security_headers())
        response.content_type = item.get("mime_type") or mimetypes.guess_type(item["path"])[0] or "application/octet-stream"
        safe_name = str(item.get("name") or "attachment").replace('"', "")
        response.headers["Content-Disposition"] = f'inline; filename="{safe_name}"'
        return response

    async def _events(self, request):
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=65536, compress=False)
        await ws.prepare(request)
        try:
            cursor = max(0, int(request.query.get("after_event_id", 0)))
        except (TypeError, ValueError):
            await ws.send_json({"error": "invalid_cursor", "request_id": request["request_id"]})
            await ws.close(code=1008)
            return ws
        session_id = str(request.query.get("session_id") or "")
        try:
            while not ws.closed:
                items = self.core.chat_store.events_after(cursor, session_id or None, self.MAX_WS_BATCH)
                for item in items:
                    await asyncio.wait_for(ws.send_json(item), timeout=5)
                    cursor = int(item["event_id"])
                try:
                    message = await asyncio.wait_for(ws.receive(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue
                if message.type == WSMsgType.TEXT and message.data == "ping":
                    await ws.send_str("pong")
                elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
                    break
        except (asyncio.TimeoutError, ConnectionError, RuntimeError):
            await ws.close(code=1013, message=b"slow_or_disconnected_client")
        return ws

    def _application(self):
        @web.middleware
        async def auth_middleware(request, handler):
            return await self._auth_middleware(request, handler)

        app = web.Application(middlewares=[auth_middleware], client_max_size=self.MAX_BODY_BYTES)
        app.router.add_get("/v1/health", self._v1_health)
        app.router.add_get("/v1/{resource:sessions|workspaces|runs|approvals}", self._v1_get)
        app.router.add_get("/v1/runs/{run_id}/events", self._v1_run_events)
        for path in ("/v1/sessions", "/v1/workspaces", "/v1/sessions/{session_id}/messages", "/v1/runs/{run_id}/cancel", "/v1/sessions/{session_id}/read", "/v1/approvals/{approval_id}/resolve", "/v1/channels/{channel}/messages"):
            app.router.add_post(path, self._v1_post)
        app.router.add_get("/v2/health", self._v2_health)
        app.router.add_get("/v2/version", self._v2_version)
        app.router.add_get("/v2/capabilities", self._v2_capabilities)
        app.router.add_get("/v2/bootstrap", self._v2_bootstrap)
        app.router.add_get("/v2/workspaces", self._workspaces)
        app.router.add_post("/v2/workspaces", self._workspaces)
        app.router.add_patch("/v2/workspaces/{workspace_id}", self._workspace_item)
        app.router.add_delete("/v2/workspaces/{workspace_id}", self._workspace_item)
        app.router.add_get("/v2/conversations", self._conversations)
        app.router.add_post("/v2/conversations", self._conversations)
        app.router.add_get("/v2/conversations/{session_id}", self._conversation_item)
        app.router.add_patch("/v2/conversations/{session_id}", self._conversation_item)
        app.router.add_delete("/v2/conversations/{session_id}", self._conversation_item)
        app.router.add_get("/v2/conversations/{session_id}/messages", self._messages)
        app.router.add_post("/v2/conversations/{session_id}/runs", self._submit_run)
        app.router.add_post("/v2/conversations/{session_id}/read", self._mark_read)
        app.router.add_get("/v2/runs", self._runs)
        app.router.add_get("/v2/runs/{run_id}", self._run_item)
        app.router.add_post("/v2/runs/{run_id}/cancel", self._cancel_run)
        app.router.add_get("/v2/runs/{run_id}/events", self._run_events)
        app.router.add_get("/v2/events/replay", self._events_replay)
        app.router.add_get("/v2/approvals", self._approvals)
        app.router.add_post("/v2/approvals/{approval_id}/resolve", self._resolve_approval)
        app.router.add_get("/v2/settings/schema", self._settings_schema)
        app.router.add_get("/v2/settings", self._settings)
        app.router.add_patch("/v2/settings", self._settings)
        app.router.add_put("/v2/settings/secrets/{secret_key}", self._secret)
        app.router.add_delete("/v2/settings/secrets/{secret_key}", self._secret)
        app.router.add_get("/v2/management/tasks", self._tasks)
        app.router.add_post("/v2/management/tasks", self._tasks)
        app.router.add_get("/v2/management/memories", self._memories)
        app.router.add_get("/v2/management/memories/{memory_id}", self._memory_item)
        app.router.add_patch("/v2/management/memories/{memory_id}", self._memory_item)
        app.router.add_delete("/v2/management/memories/{memory_id}", self._memory_item)
        app.router.add_get("/v2/management/tools", self._tools)
        app.router.add_post("/v2/management/tools", self._tools)
        app.router.add_get("/v2/management/usage", self._usage)
        app.router.add_get("/v2/management/logs", self._logs)
        app.router.add_get("/v2/management/about", self._about)
        app.router.add_post("/v2/management/diagnostics", self._diagnostics)
        app.router.add_get("/v2/workbench/root", self._workspace_root)
        app.router.add_patch("/v2/workbench/root", self._workspace_root)
        app.router.add_get("/v2/workbench/tree", self._workspace_tree)
        app.router.add_get("/v2/workbench/file", self._workspace_file)
        app.router.add_get("/v2/workbench/artifacts", self._artifacts)
        app.router.add_get("/v2/conversations/{session_id}/canvases", self._canvases)
        app.router.add_get("/v2/conversations/{session_id}/canvases/{canvas_id}", self._canvas_item)
        app.router.add_patch("/v2/conversations/{session_id}/canvases/{canvas_id}", self._canvas_item)
        app.router.add_get("/v2/browser/import/sources", self._browser_import_sources)
        app.router.add_post("/v2/browser/import", self._browser_import)
        app.router.add_get("/v2/browser/legacy-migration", self._legacy_browser_migration)
        app.router.add_post("/v2/browser/legacy-migration", self._legacy_browser_migration)
        app.router.add_post("/v2/workbench/open", self._workspace_open)
        app.router.add_post("/v2/workbench/terminals", self._terminals)
        app.router.add_get("/v2/workbench/terminals/{terminal_id}", self._terminal_item)
        app.router.add_post("/v2/workbench/terminals/{terminal_id}", self._terminal_item)
        app.router.add_delete("/v2/workbench/terminals/{terminal_id}", self._terminal_item)
        app.router.add_post("/v2/providers/{provider}/validate", self._validate_provider)
        app.router.add_get("/v2/providers/{provider}/models", self._discover_models)
        app.router.add_get("/v2/providers/{provider}/reasoning", self._set_model_reasoning)
        app.router.add_post("/v2/providers/{provider}/reasoning", self._set_model_reasoning)
        app.router.add_get("/v2/providers/openai_codex_signin/quota", self._codex_quota)
        app.router.add_post("/v2/attachments", self._register_attachment)
        app.router.add_get("/v2/attachments/{handle}", self._read_attachment)
        app.router.add_post("/v2/audio/tts", self._tts_start)
        app.router.add_post("/v2/audio/tts/stop", self._tts_stop)
        app.router.add_get("/v2/audio/tts/status", self._tts_status)
        app.router.add_get("/v2/events", self._events)
        return app

    async def _start_async(self):
        self._runner = web.AppRunner(self._application(), access_log=None)
        await self._runner.setup()
        ports = [self.requested_port] if self.requested_port == 0 else [self.requested_port, 0]
        last_error = None
        for port in ports:
            try:
                self._site = web.TCPSite(self._runner, "127.0.0.1", port)
                await self._site.start()
                self.port = int(self._site._server.sockets[0].getsockname()[1])
                self._write_runtime_info()
                return
            except OSError as exc:
                last_error = exc
        raise last_error or RuntimeError("control_plane_start_failed")

    def _thread_main(self):
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._start_async())
        except Exception as exc:
            self._startup_error = exc
            logging.exception("Could not start the Smarti local gateway")
            self._started.set()
            return
        self._started.set()
        loop.run_forever()
        if self._runner:
            loop.run_until_complete(self._runner.cleanup())
        loop.close()

    def start(self):
        if not self.token or (self._thread and self._thread.is_alive()):
            return bool(self._thread and self._thread.is_alive())
        self._started.clear()
        self._startup_error = None
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="SmartiLocalGateway")
        self._thread.start()
        self._started.wait(timeout=10)
        if self._startup_error or not self.port:
            self.stop()
            return False
        logging.info("Local gateway listening on 127.0.0.1:%s", self.port)
        return True

    def _write_runtime_info(self):
        try:
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            payload = {
                "schema_version": 2, "host": "127.0.0.1", "port": self.port,
                "pid": os.getpid(), "api": "v2", "legacy_api": "v1",
                "contract_version": CONTRACT_VERSION, "started_at": datetime.now().isoformat(timespec="seconds"),
            }
            temporary = self._runtime_file + ".tmp"
            with open(temporary, "w", encoding="utf-8") as destination:
                json.dump(payload, destination, ensure_ascii=False, indent=2)
            os.replace(temporary, self._runtime_file)
        except Exception:
            logging.exception("Could not write local gateway runtime metadata")

    def stop(self):
        self._terminal_sessions.close_all()
        loop, thread = self._loop, self._thread
        self._thread = None
        if loop and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)
        self._loop = self._runner = self._site = None
        self.port = 0
        try:
            if os.path.isfile(self._runtime_file):
                os.remove(self._runtime_file)
        except Exception:
            pass
