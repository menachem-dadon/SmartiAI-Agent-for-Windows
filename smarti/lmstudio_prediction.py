"""Cancelable private SDK bridge for LM Studio's structured reasoning budget."""
import json
import queue
import subprocess
import threading
import time
from pathlib import Path

from .local_reasoning import BUDGETS
from .runtime import SMARTI_RUNTIME


def predict(core, control, messages, system, options):
    node = SMARTI_RUNTIME.which("node")
    bridge = Path(__file__).with_name("local_lmstudio_sdk.cjs")
    if not node or not bridge.is_file():
        raise RuntimeError("מתאם תקציב החשיבה של LM Studio אינו זמין. יש להכין את סביבת Smarti מחדש.")
    payload = {"root": control["contract"]["root"], "model": control["model"],
               "identifier": control["contract"].get("identifier", control["model"]),
               "budget": BUDGETS[control["effort"].removeprefix("budget:")],
               "messages": messages, "system": system}
    if options.get("max_output_tokens"):
        payload["maxTokens"] = int(options["max_output_tokens"])
    proc = subprocess.Popen([node, str(bridge)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            env=SMARTI_RUNTIME.subprocess_env())
    register = getattr(core, "_register_active_process", None)
    unregister = getattr(core, "_unregister_active_process", None)
    if callable(register):
        register(proc)
    events = queue.Queue(maxsize=256)
    stop_reader = threading.Event()

    def read():
        try:
            for line in proc.stdout:
                while not stop_reader.is_set():
                    try:
                        events.put(line, timeout=.1)
                        break
                    except queue.Full:
                        pass
        finally:
            while not stop_reader.is_set():
                try:
                    events.put(None, timeout=.1)
                    break
                except queue.Full:
                    pass

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    live = getattr(core, "_current_stream", None)
    chunks, done, usage = [], False, {}
    timeout = core._provider_transport_timeout("local")
    timeout = timeout[-1] if isinstance(timeout, (tuple, list)) else timeout
    deadline = time.monotonic() + (timeout or 600)
    try:
        proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        while True:
            core._raise_if_cancelled()
            if time.monotonic() >= deadline:
                raise TimeoutError("LM Studio SDK prediction timed out")
            try:
                line = events.get(timeout=.1)
            except queue.Empty:
                continue
            if line is None:
                break
            event = json.loads(line)
            kind = event.get("type")
            if kind == "error":
                raise RuntimeError(event.get("message") or "LM Studio SDK prediction failed")
            if kind == "prefill" and live:
                live.status("prefill", event.get("percent"))
            elif kind == "thinking" and live:
                live.status("thinking")
            elif kind == "text":
                chunks.append(event.get("content", ""))
                if live:
                    live.text(event.get("content", ""))
            elif kind == "done":
                stats = event.get("stats") or {}
                if stats.get("stopReason") in {"maxPredictedTokensReached", "contextLengthReached", "userStopped", "modelUnloaded", "failed"}:
                    raise RuntimeError("LM Studio prediction stopped before a complete answer: " + stats["stopReason"])
                usage = {"prompt": stats.get("promptTokensCount", 0), "completion": stats.get("predictedTokensCount", 0)}
                done = True
                break
        if not done:
            raise RuntimeError("LM Studio SDK disconnected before completion")
        text = "".join(chunks).strip()
        core._check_generated_response("local", control["model"], text, [])
        usage["total"] = usage.get("prompt", 0) + usage.get("completion", 0)
        return text, usage
    finally:
        stop_reader.set()
        if proc.poll() is None:
            try:
                proc.stdin.write('{"cancel":true}\n')
                proc.stdin.flush()
                proc.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        for stream in (proc.stdin, proc.stdout):
            if stream:
                stream.close()
        if callable(unregister):
            unregister(proc)
