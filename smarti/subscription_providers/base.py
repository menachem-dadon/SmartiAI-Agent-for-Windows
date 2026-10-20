"""Bounded owned processes, safe errors, and subscription metadata."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from ..common import SmartiCancelled
from ..codex_signin import CodexProtocolError, CodexSignInProvider, SMARTI_TURN_OUTPUT_SCHEMA
from ..runtime import SmartiRuntime
from jsonschema import Draft202012Validator, ValidationError

_catalogs = {}
_catalog_lock = threading.RLock()


class SubscriptionError(RuntimeError):
    def __init__(self, message, reason="unavailable"):
        super().__init__(message)
        self.reason = reason


def model_efforts(provider, model):
    with _catalog_lock:
        return tuple(_catalogs.get(provider, {}).get(model, ()))


def register_models(provider, rows):
    with _catalog_lock:
        _catalogs[provider] = {name: tuple(row.get("efforts", ())) for row in rows
            for name in [row["id"], row.get("resolved_model"), *row.get("aliases", [])] if name}


def safe_failure(raw):
    text = str(raw or "").lower()
    if any(word in text for word in ("401", "unauthorized", "authentication required", "not logged", "login required", "token expired", "invalid token")):
        return SubscriptionError("החשבון אינו מחובר או שהחיבור פג. יש להתחבר מחדש בהגדרות הספק.", "signin_required")
    if any(word in text for word in ("quota", "usage limit", "rate_limit", "rate limit", "429")):
        return SubscriptionError("מכסת החשבון או קצב הבקשות הוגבלו. יש לבדוק את המכסה אצל הספק ולנסות מאוחר יותר.", "signin_usage_limit")
    if any(word in text for word in ("503", "no capacity", "high traffic", "temporarily unavailable", "overloaded")):
        return SubscriptionError("שרת הספק עמוס או שאין כרגע קיבולת למודל שנבחר. אפשר לנסות שוב מאוחר יותר או לבחור מודל אחר.", "provider_overloaded")
    if any(word in text for word in ("subscription", "upgrade", "pro plan", "403", "not eligible")):
        return SubscriptionError("החשבון או המנוי אינם זכאים לבקשה. יש לבדוק את התוכנית והרשאות המודל אצל הספק.", "account_ineligible")
    if any(word in text for word in ("unknown model", "model not", "not supported")):
        return SubscriptionError("המודל שנבחר אינו זמין בחשבון או בגרסת רכיב החיבור. יש לבחור מודל זמין.", "model_unavailable")
    if "provider_contract_violation" in text:
        return SubscriptionError("רכיב הספק הציע כלים שאינם בשליטת Smarti. הבקשה נעצרה לשמירת הרשאות הכלים.", "provider_contract_violation")
    if any(word in text for word in ("malformed function call", "function call is empty", "invalid json", "structured output")):
        return SubscriptionError("הספק החזיר קריאת כלי בפורמט שגוי. Smarti לא ביצע את הקריאה.", "provider_protocol_error")
    if any(word in text for word in ("max_tokens", "max output tokens", "output token limit")):
        return SubscriptionError("תשובת הספק נקטעה במגבלת הפלט. יש לפצל את הבקשה או לקצר את התוצר.", "provider_output_limit")
    return SubscriptionError("רכיב החיבור לא השלים את הבקשה. יש לבדוק חיבור, רשת וגרסת רכיב בהגדרות הספק.")


class SubscriptionProvider:
    provider = ""
    label = ""
    install_url = ""

    def __init__(self, data_dir, strategy):
        self.data_dir = Path(data_dir).resolve()
        self.strategy = strategy
        self.workspace = self.data_dir / "subscription_providers" / self.provider / "workspace"
        self.runtime = SmartiRuntime()
        self.disconnected = False
        self.verified = False
        self.models = []
        self.operations = {}
        self._lock = threading.RLock()

    def environment(self):
        env = dict(os.environ)
        for key in tuple(env):
            if key in {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_PROFILE", "ANTHROPIC_IDENTITY_TOKEN_FILE", "ANTHROPIC_FEDERATION_IDENTITY", "ANTHROPIC_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SIMPLE"} or key.startswith(("CLAUDE_CODE_USE_", "ANTHROPIC_DEFAULT_")):
                env.pop(key, None)
        if self.strategy != "setup_token_env":
            env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        env["NODE_TLS_REJECT_UNAUTHORIZED"] = "1"
        env["AGY_CLI_DISABLE_AUTO_UPDATE"] = "true"
        return env

    @staticmethod
    def terminate(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            except (OSError, subprocess.TimeoutExpired) as error:
                # Keep the original cancellation, provider timeout or handoff.
                logging.warning("SUBSCRIPTION CLEANUP | pid=%s | helper_failure=%s | fallback=direct_kill",
                    process.pid, type(error).__name__)
                if process.poll() is None:
                    process.kill()
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def run(self, command, *, payload=None, cancel=None, timeout=30, event=None, cwd=None, ok_codes=(0,)):
        self.workspace.mkdir(parents=True, exist_ok=True)
        try:
            process = subprocess.Popen(command, cwd=str(cwd or self.workspace), env=self.environment(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            raise SubscriptionError("רכיב החיבור אינו מותקן או שאינו ניתן להפעלה. יש לפתוח את התקנת הספק.", "missing_dependency") from error
        incoming = queue.Queue(maxsize=8)
        closing = threading.Event()
        stderr = []
        def put(value):
            while not closing.is_set():
                try:
                    incoming.put(value, timeout=.1)
                    return
                except queue.Full:
                    pass
        def read():
            try:
                while True:
                    line = process.stdout.readline(4 * 1024 * 1024 + 1)
                    if not line:
                        break
                    put(line)
            except (OSError, ValueError):
                pass
            finally:
                put(None)
        def read_errors():
            try:
                for line in process.stderr:
                    stderr.append(line[:4096])
                    del stderr[:-8]
            except (OSError, ValueError):
                pass
        readers = [threading.Thread(target=read, daemon=True), threading.Thread(target=read_errors, daemon=True)]
        for reader in readers:
            reader.start()
        output, size, deadline = [], 0, time.monotonic() + timeout
        def write():
            try:
                if payload is not None:
                    process.stdin.write(payload)
                    process.stdin.flush()
                process.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
        writer = threading.Thread(target=write, daemon=True)
        writer.start()
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    raise SmartiCancelled("CANCELLED_BY_USER")
                if time.monotonic() >= deadline:
                    raise SubscriptionError("רכיב החיבור לא סיים בזמן. אפשר לנסות שוב לאחר בדיקת החיבור.", "timeout")
                try:
                    line = incoming.get(timeout=.1)
                except queue.Empty:
                    continue
                if line is None:
                    break
                frame_size = len(line.encode("utf-8"))
                size += frame_size
                if frame_size > 4 * 1024 * 1024 or size > 24 * 1024 * 1024:
                    raise SubscriptionError("פלט רכיב החיבור חרג מהמגבלה.", "provider_contract_violation")
                if event:
                    event(line)
                else:
                    output.append(line)
            try:
                process.wait(timeout=max(.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired as error:
                raise SubscriptionError("רכיב החיבור לא סיים בזמן.", "timeout") from error
            if process.returncode not in ok_codes:
                raise safe_failure("".join(output + stderr))
            return "".join(output)
        finally:
            closing.set()
            try:
                self.terminate(process)
            finally:
                writer.join(timeout=1)
                for reader in readers:
                    reader.join(timeout=1)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe and not pipe.closed:
                        pipe.close()

    def state(self, state, message, **extra):
        return {"state": state, "message": message, "provider": self.provider,
                "auth_strategy": self.strategy, "install_url": self.install_url,
                "quota_available": False, **extra}

    def disconnect(self):
        self.disconnected, self.verified = True, False
        self.models = []
        register_models(self.provider, [])
        return self.state("disconnected", "הספק נותק מ-Smarti. הכניסה בכלי הרשמי נשמרה.")

    def read_models(self):
        return [row["id"] for row in self.catalog()]

    @staticmethod
    def decode(value, purpose):
        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)
        if purpose == "agent":
            try:
                payload = json.loads(value)
                Draft202012Validator(SMARTI_TURN_OUTPUT_SCHEMA).validate(payload)
                if len(payload.get("tool_calls") or []) > 8:
                    raise ValueError("too many tool calls")
            except (ValueError, TypeError, ValidationError) as error:
                raise CodexProtocolError("תשובת הספק אינה תואמת את חוזה Smarti.") from error
            return CodexSignInProvider._decode_structured_turn(value)
        text = str(value or "").strip()
        if not text:
            raise CodexProtocolError("הספק לא החזיר תשובה.")
        return text

    @staticmethod
    def usage(raw):
        raw = raw if isinstance(raw, dict) else {}
        cached = int(raw.get("cache_read_input_tokens", 0) or 0)
        written = int(raw.get("cache_creation_input_tokens", 0) or 0)
        prompt = int(raw.get("input_tokens", 0) or 0) + cached + written
        completion = int(raw.get("output_tokens", 0) or 0)
        return {"prompt": prompt, "completion": completion, "total": prompt + completion,
                "cached_prompt": cached, "cache_write_prompt": written, "billing_mode": "subscription",
                "estimated_cost_usd": None, "usage_source": "reported" if raw else "unavailable"}

    @staticmethod
    def prompt(messages):
        return "\n\n".join(f"[{str(message.get('role', 'user')).upper()}]\n" +
            CodexSignInProvider._message_text(message.get("content"))
            for message in messages if message.get("role") != "system")
