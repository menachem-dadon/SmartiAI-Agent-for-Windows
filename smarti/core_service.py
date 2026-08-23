"""Lifecycle-controlled, UI-independent Smarti Core service.

This module deliberately contains no desktop UI imports.  The versioned desktop
HTTP/WebSocket contract is introduced in migration Point 4; Point 3 owns only
the process lifecycle and the existing authenticated loopback health surface.
"""
from __future__ import annotations

import copy
import os
import secrets
import sys
import threading
from datetime import datetime, timezone


SERVICE_STATES = frozenset({"starting", "ready", "stopping", "stopped", "fatal"})


class SmartiCoreService:
    """Own one SmartiCore instance and expose a supervisor-friendly lifecycle."""

    def __init__(self, *, core_factory=None, token=None, port=0):
        self._core_factory = core_factory
        self._token = str(token or secrets.token_urlsafe(32))
        self._port = max(0, min(65535, int(port or 0)))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._subscribers = {}
        self._run_subscription = None
        self._started_at = None
        self._fatal_error = ""
        self.core = None
        self.state = "stopped"

    def subscribe(self, callback):
        token = secrets.token_hex(16)
        with self._lock:
            self._subscribers[token] = callback
        return token

    def unsubscribe(self, token):
        with self._lock:
            return self._subscribers.pop(str(token or ""), None) is not None

    def _emit(self, event_type, payload=None):
        event = {
            "event_type": str(event_type),
            "payload": copy.deepcopy(payload if isinstance(payload, dict) else {}),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            callbacks = list(self._subscribers.values())
        for callback in callbacks:
            try:
                callback(copy.deepcopy(event))
            except Exception:
                # Presentation/event consumers must never take the Core down.
                pass
        return event

    def _set_state(self, state, payload=None):
        if state not in SERVICE_STATES:
            raise ValueError(f"Unsupported Core service state: {state}")
        with self._lock:
            self.state = state
        return self._emit(f"service_{state}", payload)

    def _make_core(self):
        if self._core_factory is not None:
            return self._core_factory(
                local_gateway_token=self._token,
                local_gateway_port=self._port,
                local_gateway_required=True,
            )
        from .core import SmartiCore
        return SmartiCore(
            local_gateway_token=self._token,
            local_gateway_port=self._port,
            local_gateway_required=True,
        )

    def start(self):
        with self._lock:
            if self.state == "ready":
                return self.readiness_handshake()
            if self.state in {"starting", "stopping"}:
                raise RuntimeError(f"Core service is currently {self.state}")
            self._stop_event.clear()
            self._fatal_error = ""
        self._set_state("starting")
        try:
            core = self._make_core()
            self.core = core
            core.service_health_callback = self.health
            core.notification_callback = (
                lambda kind, payload=None: self._emit(
                    "notification_intent",
                    {"kind": str(kind or ""), "data": copy.deepcopy(payload or {})},
                )
            )
            core.tts_status_callback = (
                lambda is_playing: self._emit("tts_status", {"is_playing": bool(is_playing)})
            )
            core.embedded_browser_activate_callback = (
                lambda url="": self._emit("browser_activation_requested", {"url": str(url or "")})
            )
            core.background_task_start_callback = (
                lambda session_id, task_id, prompt: self._emit(
                    "background_task_started",
                    {"session_id": session_id, "task_id": task_id, "prompt": prompt},
                )
            )
            core.background_task_step_callback = (
                lambda session_id, task_id, step: self._emit(
                    "background_task_step",
                    {"session_id": session_id, "task_id": task_id, "step": step},
                )
            )
            core.background_task_finish_callback = (
                lambda session_id, task_id, result, success: self._emit(
                    "background_task_finished",
                    {
                        "session_id": session_id,
                        "task_id": task_id,
                        "result": result,
                        "success": bool(success),
                    },
                )
            )
            self._run_subscription = core.run_manager.subscribe(self._forward_run_event)
            core.resume_background_tasks()
            self._started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._set_state("ready")
            return self.readiness_handshake()
        except Exception as exc:
            self._fatal_error = f"{type(exc).__name__}: {exc}"[:500]
            self._set_state("fatal", {"error": self._fatal_error})
            self._shutdown_partial_core()
            raise

    def _forward_run_event(self, event):
        self._emit("core_event", event if isinstance(event, dict) else {})

    def readiness_handshake(self):
        health = self.health()
        gateway = getattr(self.core, "local_gateway", None) if self.core else None
        return {
            "type": "smarti_core_ready" if self.state == "ready" else "smarti_core_state",
            "schema_version": 1,
            "state": self.state,
            "pid": os.getpid(),
            "host": "127.0.0.1",
            "port": int(getattr(gateway, "port", 0) or 0),
            "api": str(getattr(gateway, "API_VERSION", "v1") or "v1"),
            "health": health,
        }

    def health(self):
        core = self.core
        gateway = getattr(core, "local_gateway", None) if core else None
        manager = getattr(core, "run_manager", None) if core else None
        return {
            "service": "smarti-core",
            "state": self.state,
            "ready": self.state == "ready",
            "started_at": self._started_at,
            "fatal_error": self._fatal_error,
            "qt_loaded": any(
                name == "PyQt6" or name.startswith("PyQt6.")
                for name in sys.modules
            ),
            "components": {
                "core": core is not None,
                "run_manager": manager is not None and not getattr(manager, "_closed", True),
                "background_scheduler": getattr(core, "_background_resume_done", False) if core else False,
                "control_plane": bool(gateway and getattr(gateway, "port", 0)),
            },
        }

    def create_session(self, *, title=""):
        self._require_ready()
        session = self.core.chat_store.create_session(set_active=False)
        if str(title or "").strip():
            self.core.chat_store.rename_session(session["id"], str(title).strip())
            session = self.core.chat_store.session_metadata(session["id"])
        return session

    def submit(self, session_id, text, *, attachments=None, source="headless_service"):
        self._require_ready()

        def api_key_requested(secret_key, provider_label, title, message, help_url=""):
            self._emit(
                "api_key_requested",
                {
                    "session_id": str(session_id or ""),
                    "secret_key": str(secret_key or ""),
                    "provider_label": str(provider_label or ""),
                    "title": str(title or ""),
                    "message": str(message or ""),
                    "help_url": str(help_url or ""),
                },
            )
            return ""

        return self.core.run_manager.submit(
            session_id,
            text,
            attachments=attachments or [],
            source=source,
            callbacks={"api_key_callback": api_key_requested},
        )

    def _require_ready(self):
        if self.state != "ready" or self.core is None:
            raise RuntimeError(f"Core service is not ready (state={self.state})")

    def request_shutdown(self):
        self._stop_event.set()

    def wait(self, timeout=None):
        return self._stop_event.wait(timeout)

    def _shutdown_partial_core(self):
        core = self.core
        if core is None:
            return
        try:
            core.shutdown_runtime(wait=True)
        except Exception:
            pass

    def shutdown(self):
        with self._lock:
            if self.state == "stopped":
                self._stop_event.set()
                return
            fatal = self.state == "fatal"
        if not fatal:
            self._set_state("stopping")
        core = self.core
        try:
            if core is not None:
                if self._run_subscription:
                    core.run_manager.unsubscribe(self._run_subscription)
                    self._run_subscription = None
                core.shutdown_runtime(wait=True)
        finally:
            self.core = None
            self._stop_event.set()
            if not fatal:
                self._set_state("stopped")


__all__ = ["SERVICE_STATES", "SmartiCoreService"]
