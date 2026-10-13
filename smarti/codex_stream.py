"""Run-scoped, incremental model-only turns over official Codex App Server."""
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tomllib


def isolated_overrides(environment):
    """Disable tools in every known user layer without changing its auth store."""
    overrides = {"web_search": "disabled", "mcp_servers": {}, "hooks": {},
                 "features.shell_tool": False, "features.code_mode": False,
                 "features.code_mode_host": False, "features.apps": False,
                 "features.hooks": False, "features.skill_search": False,
                 "features.skill_mcp_dependency_install": False,
                 "features.skip_host_skill_discovery": True,
                 "memories.use_memories": False, "memories.generate_memories": False}
    home = Path(environment.get("CODEX_HOME") or Path.home() / ".codex")
    for path in [home / "config.toml", *home.glob("*.config.toml")]:
        try:
            with path.open("rb") as handle:
                config = tomllib.load(handle)
            for group in ("mcp_servers", "plugins"):
                for name in (config.get(group) or {}):
                    # CLI dotted overrides split on periods without parsing
                    # quoted segments. Keep literal names in the TOML value so
                    # quotes/dots cannot create phantom transportless servers.
                    overrides.setdefault(group, {})[name] = {"enabled": False}
        except (OSError, ValueError):
            continue
    return overrides


def _toml_override(value):
    """Encode inline policy tables without including user transport secrets."""
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(name, ensure_ascii=False) + "=" + _toml_override(item)
                              for name, item in value.items()) + "}"
    return json.dumps(value, ensure_ascii=False)


class CodexStreamSession:
    """One model-only app-server/thread per Smarti run; no stored Codex chat."""

    def __init__(self, provider):
        self.provider = provider
        self.incoming = queue.Queue(maxsize=1024)
        self.errors = []
        self.closing = threading.Event()
        self.process = None
        self.thread_id = ""
        self.instructions = ""
        self.model = ""
        self.sent = ()
        self.rpc_id = 0
        self.usage_totals = {}
        self.lock = threading.RLock()

    def close(self):
        self.closing.set()
        process, self.process = self.process, None
        if process:
            self.provider._terminate_process(process)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe:
                    pipe.close()

    def _launch(self, context_window_tokens=None):
        environment = self.provider._environment()
        command = [self.provider._find_executable(), "app-server", "--stdio"]
        overrides = isolated_overrides(environment)
        if context_window_tokens:
            window = max(1, int(context_window_tokens))
            overrides.update(model_context_window=window,
                model_auto_compact_token_limit=int(window * 0.85),
                model_auto_compact_token_limit_scope="total")
        for name, value in overrides.items():
            command.extend(("--config", f"{name}={_toml_override(value)}"))
        self.provider.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(command, cwd=str(self.provider.workspace_dir), env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        process = self.process
        closing, incoming, errors = self.closing, self.incoming, self.errors
        def enqueue(value):
            while not closing.is_set():
                try:
                    incoming.put(value, timeout=.1)
                    return
                except queue.Full:
                    continue
        def read_stdout():
            try:
                for line in process.stdout:
                    if closing.is_set():
                        break
                    enqueue(line)
            except (OSError, ValueError):
                pass  # Owned pipe closed during cancellation/rebase.
            finally:
                enqueue(None)
        def read_stderr():
            try:
                for line in process.stderr:
                    errors.append(line)
                    del errors[:-40]
            except (OSError, ValueError):
                pass
        threading.Thread(target=read_stdout, daemon=True).start()
        threading.Thread(target=read_stderr, daemon=True).start()

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def _request(self, method, params, deadline, cancel_event):
        from .codex_signin import CodexSignInError, CODEX_SIGNIN_PROVIDER
        from .common import SmartiCancelled
        from .api_errors import analyze_api_error
        self.rpc_id += 1
        identity = self.rpc_id
        self.send({"id": identity, "method": method, "params": params})
        while time.monotonic() < deadline:
            if cancel_event and cancel_event.is_set():
                raise SmartiCancelled("CANCELLED_BY_USER")
            try:
                line = self.incoming.get(timeout=.1)
            except queue.Empty:
                continue
            if line is None:
                detail = self.provider._redact_cli_output("".join(self.errors), 600)
                unsupported = any(v in detail.lower() for v in ("unrecognized subcommand", "unrecognized argument", "unexpected argument '--stdio'"))
                raise CodexSignInError("Codex App Server stopped: " + detail, reason="stream_unsupported" if unsupported else "")
            event = json.loads(line)
            if event.get("id") == identity and "method" not in event:
                if event.get("error"):
                    if event["error"].get("code") == -32601:
                        raise CodexSignInError("Codex App Server streaming is unavailable", reason="stream_unsupported")
                    error = CodexSignInError("Codex request failed", body={"error": event["error"]})
                    analysis = analyze_api_error(CODEX_SIGNIN_PROVIDER, self.model, error=error)
                    raise CodexSignInError(analysis.user_message, reason=analysis.reason, body=error.body)
                return event.get("result", {})
            if "id" in event and "method" in event:
                self.send({"id": event["id"], "error": {"code": -32601, "message": "Smarti owns tools; model-only request"}})
        raise CodexSignInError("Codex לא סיים בזמן.", reason="timeout")

    @staticmethod
    def fingerprints(messages):
        import hashlib
        return tuple(hashlib.sha256(json.dumps(m, ensure_ascii=False, sort_keys=True).encode()).digest() for m in messages)

    def complete(self, messages, model, timeout, effort, cancel_event, live, schema, context_window_tokens=None):
        import tempfile
        from .codex_signin import CodexSignInError
        with self.lock:
            instructions = self.provider._build_model_instructions(messages, purpose="agent") + "\nFor streaming tool turns, serialize fields in this order: kind, progress_report, tool_calls, final_answer. Emit each tool name before arguments_json."
            conversation = [m for m in messages if str(m.get("role", "")).lower() != "system"]
            fingerprints = self.fingerprints(conversation)
            continuing = bool(self.thread_id and self.model == model and self.instructions == instructions and fingerprints[:len(self.sent)] == self.sent and len(fingerprints) > len(self.sent))
            if self.thread_id and not continuing:
                # Core compaction, changed instructions/model or edited history:
                # replay the authoritative context, never silently keep old state.
                self.close()
                self.closing = threading.Event()
                self.incoming = queue.Queue(maxsize=1024)
                self.errors = []
                self.thread_id, self.sent, self.rpc_id = "", (), 0
                self.usage_totals = {}
            deadline = time.monotonic() + timeout
            self.model = model
            if not self.thread_id:
                self._launch(context_window_tokens)
                self._request("initialize", {"clientInfo": {"name": "SmartiAI", "version": "1.0"}, "capabilities": {}}, deadline, cancel_event)
                self.send({"method": "initialized"})
                params = {"cwd": str(self.provider.workspace_dir.resolve()), "ephemeral": True,
                          "sandbox": "read-only", "approvalPolicy": "never", "baseInstructions": instructions}
                if model.lower() not in {"codex default", "default", ""}:
                    params["model"] = model
                result = self._request("thread/start", params, deadline, cancel_event)
                self.thread_id = result["thread"]["id"]
                self.instructions = instructions
            delta = conversation[len(self.sent):] if continuing else conversation
            # The server already holds its own structured assistant response.
            # Core adds a translated copy before tool feedback; do not replay it.
            if continuing and delta and delta[0].get("role") in {"assistant", "model"}:
                delta = delta[1:]
            if not delta:
                raise CodexSignInError("No new Smarti tool feedback for Codex")
            with tempfile.TemporaryDirectory(prefix="smarti-codex-stream-images-") as images:
                prompt_messages, image_paths = self.provider._prepare_image_inputs(delta, images)
                logging.info("CODEX SESSION | reused=%s | context_messages=%s | sent_messages=%s | new_images=%s",
                             continuing, len(conversation), len(delta), len(image_paths))
                params = {"threadId": self.thread_id, "input": [{"type": "text", "text": self.provider._build_prompt(prompt_messages, purpose="agent")}], "outputSchema": schema}
                params["input"].extend({"type": "localImage", "path": str(path)} for path in image_paths)
                if effort != "auto":
                    params["effort"] = effort
                self.rpc_id += 1
                self.send({"id": self.rpc_id, "method": "turn/start", "params": params})
                result = _read_turn(self.provider, self.process, self.incoming, self.send, deadline, self.thread_id, cancel_event, live, model, usage_totals=self.usage_totals)
            self.sent = fingerprints
            return result


def complete_stream(provider, messages, model, timeout, effort, cancel_event, live, schema, session_key=None, context_window_tokens=None):
    with provider._stream_sessions_lock:
        session = provider._stream_sessions.get(session_key) if session_key else None
        if session is None:
            session = CodexStreamSession(provider)
            if session_key:
                provider._stream_sessions[session_key] = session
    try:
        return session.complete(messages, model, timeout, effort, cancel_event, live, schema, context_window_tokens)
    except BaseException:
        provider.close_stream_session(session_key, session)
        raise
    finally:
        if not session_key:
            session.close()


def _read_turn(provider, process, incoming, send, deadline, thread_id, cancel_event, live, model, *, usage_totals=None):
    from .common import SmartiCancelled
    from .codex_signin import CodexSignInError, CODEX_SIGNIN_PROVIDER
    from .api_errors import analyze_api_error
    text, usage, turn_id, phases = "", {}, "", {}
    baseline = dict(usage_totals or {})
    latest_totals = {}
    while time.monotonic() < deadline:
        if cancel_event and cancel_event.is_set():
            if turn_id:
                send({"id": 9, "method": "turn/interrupt", "params": {"threadId": thread_id, "turnId": turn_id}})
            raise SmartiCancelled("CANCELLED_BY_USER")
        try:
            line = incoming.get(timeout=.1)
        except queue.Empty:
            continue
        if line is None:
            raise CodexSignInError("Codex App Server stopped unexpectedly")
        event = json.loads(line)
        if event.get("error"):
            error = CodexSignInError("Codex request failed", body={"error": event["error"]})
            analysis = analyze_api_error(CODEX_SIGNIN_PROVIDER, model, error=error)
            raise CodexSignInError(analysis.user_message, reason=analysis.reason, body=error.body)
        params, kind = event.get("params") or {}, event.get("method", "")
        if event.get("result", {}).get("turn", {}).get("id"):
            turn_id = event["result"]["turn"]["id"]
        if kind == "turn/started":
            turn_id = params["turn"]["id"]
        elif kind == "item/started" and params.get("item", {}).get("type") == "agentMessage":
            item = params["item"]
            phases[item["id"]] = item.get("phase")
        elif kind == "item/agentMessage/delta":
            delta = params.get("delta", "")
            if phases.get(params.get("itemId")) == "commentary":
                live.report(delta, f'{live.request_id}:report:{params["itemId"]}')
            else:
                text += delta
                live.text(delta)
        elif kind.startswith("item/reasoning") and (kind.endswith("/delta") or kind.endswith("Delta")):
            live.status("thinking")
        elif kind == "item/completed" and params.get("item", {}).get("type") == "agentMessage":
            item = params["item"]
            if (item.get("phase") or phases.get(item.get("id"))) == "commentary":
                live.report(item.get("text", ""), f'{live.request_id}:report:{item["id"]}', replacement=True)
            else:
                text = item.get("text", text)
        elif kind == "thread/tokenUsage/updated":
            token_usage = params.get("tokenUsage") or {}
            totals = token_usage.get("last") or {}
            if usage_totals is not None and token_usage.get("total"):
                latest_totals = token_usage["total"]
                # A turn can contain several inference requests. Cumulative
                # thread deltas count all of them without charging old turns.
                totals = {k: max(0, int(v or 0) - int(baseline.get(k, 0) or 0))
                          for k, v in latest_totals.items() if isinstance(v, (int, float))}
            usage = {"prompt": totals.get("inputTokens", 0), "completion": totals.get("outputTokens", 0),
                     "total": totals.get("totalTokens", 0), "cached_prompt": totals.get("cachedInputTokens", 0),
                     "reasoning": totals.get("reasoningOutputTokens", 0)}
            if (token_usage.get("last") or {}).get("inputTokens"):
                # Billing sums all inference requests; context calibration must
                # use the last request, not that sum.
                usage["context_prompt"] = token_usage["last"]["inputTokens"]
        elif kind == "turn/completed":
            turn = params.get("turn") or {}
            if turn.get("status") != "completed":
                raise CodexSignInError(str((turn.get("error") or {}).get("message") or "Codex turn failed"))
            if usage_totals is not None and latest_totals:
                usage_totals.update(latest_totals)
            return provider._decode_structured_turn(text), usage
        elif "id" in event and "method" in event:
            # Core owns all tools and all approvals. Fail closed on an unexpected
            # server request rather than letting account-configured tools run.
            send({"id": event["id"], "error": {"code": -32601, "message": "Smarti owns tools; model-only request"}})
    raise CodexSignInError("Codex לא סיים בזמן.", reason="timeout")
