"""One ephemeral, model-only turn over official Codex App Server stdio."""
import json
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
                 "features.skip_host_skill_discovery": True}
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


def complete_stream(provider, messages, model, timeout, effort, cancel_event, live, schema):
    from .codex_signin import CodexSignInError, CODEX_SIGNIN_PROVIDER
    from .common import SmartiCancelled
    from .api_errors import analyze_api_error
    environment = provider._environment()
    command = [provider._find_executable(), "app-server", "--stdio"]
    for name, value in isolated_overrides(environment).items():
        # Nested policy values merge with existing valid transports; {} alone
        # does not disable inherited servers in the CLI config merger.
        encoded = _toml_override(value)
        command.extend(("--config", f"{name}={encoded}"))
    provider.workspace_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command, cwd=str(provider.workspace_dir), env=environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    incoming = queue.Queue(maxsize=1024)
    errors = []
    closing = threading.Event()
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
        finally:
            enqueue(None)
    def read_stderr():
        for line in process.stderr:
            errors.append(line)
            del errors[:-40]
    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()
    def send(message):
        process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        process.stdin.flush()
    deadline, thread_id, turn_id = time.monotonic() + timeout, "", ""
    answer, usage, started = "", {}, False
    try:
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "SmartiAI", "version": "1.0"}, "capabilities": {}}})
        while time.monotonic() < deadline:
            if cancel_event and cancel_event.is_set():
                if thread_id and turn_id:
                    send({"id": 9, "method": "turn/interrupt", "params": {"threadId": thread_id, "turnId": turn_id}})
                raise SmartiCancelled("CANCELLED_BY_USER")
            try:
                line = incoming.get(timeout=.1)
            except queue.Empty:
                continue
            if line is None:
                detail = provider._redact_cli_output("".join(errors), 600)
                unsupported = any(value in detail.lower() for value in ("unrecognized subcommand", "unrecognized argument", "unexpected argument '--stdio'"))
                raise CodexSignInError("Codex App Server stopped: " + detail, reason="stream_unsupported" if unsupported else "")
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("error"):
                if event["error"].get("code") == -32601:
                    raise CodexSignInError("Codex App Server streaming is unavailable", reason="stream_unsupported")
                error = CodexSignInError("Codex request failed", body={"error": event["error"]})
                analysis = analyze_api_error(CODEX_SIGNIN_PROVIDER, model, error=error)
                raise CodexSignInError(analysis.user_message, reason=analysis.reason, body=error.body)
            if event.get("id") == 1:
                send({"method": "initialized"})
                params = {"cwd": str(provider.workspace_dir.resolve()), "ephemeral": True,
                          "sandbox": "read-only", "approvalPolicy": "never",
                          "baseInstructions": provider._build_model_instructions(messages, purpose="agent") + "\nFor streaming tool turns, serialize fields in this order: kind, progress_report, tool_calls, final_answer. Emit each tool name before arguments_json."}
                if model.lower() not in {"codex default", "default", ""}:
                    params["model"] = model
                send({"id": 2, "method": "thread/start", "params": params})
            elif event.get("id") == 2:
                thread_id = event["result"]["thread"]["id"]
                params = {"threadId": thread_id, "input": [{"type": "text", "text": provider._build_prompt(messages, purpose="agent")}], "outputSchema": schema}
                if effort != "auto":
                    params["effort"] = effort
                # Image inputs remain separate from textual conversation context.
                import tempfile
                with tempfile.TemporaryDirectory(prefix="smarti-codex-stream-images-") as images:
                    prompt_messages, image_paths = provider._prepare_image_inputs(messages, images)
                    params["input"][0]["text"] = provider._build_prompt(prompt_messages, purpose="agent")
                    params["input"].extend({"type": "localImage", "path": path} for path in image_paths)
                    # App-server copies local inputs while accepting turn/start.
                    send({"id": 3, "method": "turn/start", "params": params})
                    # Keep image files alive for the complete turn, not just send.
                    return _read_turn(provider, process, incoming, send, deadline, thread_id, cancel_event, live, model)
        raise CodexSignInError("Codex לא סיים בזמן.", reason="timeout")
    finally:
        closing.set()
        provider._terminate_process(process)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                stream.close()


def _read_turn(provider, process, incoming, send, deadline, thread_id, cancel_event, live, model):
    from .common import SmartiCancelled
    from .codex_signin import CodexSignInError, CODEX_SIGNIN_PROVIDER
    from .api_errors import analyze_api_error
    text, usage, turn_id, phases = "", {}, "", {}
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
            totals = (params.get("tokenUsage") or {}).get("last") or {}
            usage = {"prompt": totals.get("inputTokens", 0), "completion": totals.get("outputTokens", 0),
                     "total": totals.get("totalTokens", 0), "cached_prompt": totals.get("cachedInputTokens", 0),
                     "reasoning": totals.get("reasoningOutputTokens", 0)}
        elif kind == "turn/completed":
            turn = params.get("turn") or {}
            if turn.get("status") != "completed":
                raise CodexSignInError(str((turn.get("error") or {}).get("message") or "Codex turn failed"))
            return provider._decode_structured_turn(text), usage
        elif "id" in event and "method" in event:
            # Core owns all tools and all approvals. Fail closed on an unexpected
            # server request rather than letting account-configured tools run.
            send({"id": event["id"], "error": {"code": -32601, "message": "Smarti owns tools; model-only request"}})
    raise CodexSignInError("Codex לא סיים בזמן.", reason="timeout")
