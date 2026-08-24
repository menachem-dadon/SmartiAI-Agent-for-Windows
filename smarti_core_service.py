"""Source entrypoint for the headless Smarti Core sidecar."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import tempfile
import threading
import time
import urllib.request


def _write_message(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the headless Smarti Core service")
    parser.add_argument("--port", type=int, default=0, help="Loopback port; 0 selects a free port")
    parser.add_argument("--token", default="", help="Per-launch bearer token")
    parser.add_argument("--data-dir", default="", help="Override the Smarti data directory")
    parser.add_argument("--smoke", action="store_true", help="Run a deterministic lifecycle smoke and exit")
    return parser.parse_args(argv)


def _health_request(handshake, token):
    request = urllib.request.Request(
        f"http://127.0.0.1:{handshake['port']}/v1/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _v2_request(handshake, token, path, *, method="GET", payload=None, request_id="smoke-request"):
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Request-ID": request_id,
    }
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{handshake['port']}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


async def _v2_websocket_replay(handshake, token, after_event_id, expected_count):
    import aiohttp
    url = (
        f"http://127.0.0.1:{handshake['port']}/v2/events"
        f"?after_event_id={int(after_event_id)}"
    )
    headers = {"Authorization": f"Bearer {token}", "Origin": "tauri://localhost"}
    async with aiohttp.ClientSession() as client:
        async with client.ws_connect(url, headers=headers) as socket:
            return [await socket.receive_json(timeout=5) for _ in range(expected_count)]


def _monitor_stdin(service):
    """Accept a narrow parent-process shutdown command over the inherited pipe."""
    try:
        for line in sys.stdin:
            text = str(line or "").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = text
            command = payload.get("command") if isinstance(payload, dict) else payload
            if str(command or "").strip().lower() == "shutdown":
                service.request_shutdown()
                return
    finally:
        # A closed supervisor pipe means there is no trusted desktop parent left
        # to own this user-session sidecar.
        service.request_shutdown()


def main(argv=None):
    args = _parse_args(argv)
    temporary_data = None
    if args.data_dir:
        os.environ["SMARTI_DATA_DIR"] = os.path.abspath(args.data_dir)
    elif args.smoke:
        temporary_data = tempfile.TemporaryDirectory(prefix="smarti-core-smoke-")
        os.environ["SMARTI_DATA_DIR"] = temporary_data.name

    from smarti.core_service import SmartiCoreService

    token = str(args.token or os.environ.get("SMARTI_CORE_LAUNCH_TOKEN") or "")
    service = SmartiCoreService(token=token or None, port=args.port)
    token = service._token

    def stop_handler(_signum, _frame):
        service.request_shutdown()

    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        candidate = getattr(signal, signal_name, None)
        if candidate is not None:
            try:
                signal.signal(candidate, stop_handler)
            except (OSError, ValueError):
                pass

    try:
        handshake = service.start()
        deterministic_product_smoke = (
            args.smoke
            or os.environ.get("SMARTI_DETERMINISTIC_PRODUCT_SMOKE", "").strip() == "1"
        )
        if deterministic_product_smoke:
            # The desktop/package smoke must exercise the real durable run loop
            # without consuming provider credentials or making a paid request.
            service.core.settings["conversation_title_generation_mode"] = "local"
            service.core.send_message = lambda text, **_kwargs: f"deterministic:{text}"
        _write_message(handshake)
        if args.smoke:
            health = _health_request(handshake, token)
            bootstrap = _v2_request(handshake, token, "/v2/bootstrap")
            session = _v2_request(
                handshake, token, "/v2/conversations", method="POST",
                payload={"title": "Headless smoke"},
            )["data"]["conversation"]
            attachment_path = os.path.join(os.environ["SMARTI_DATA_DIR"], "smoke-attachment.txt")
            with open(attachment_path, "w", encoding="utf-8") as destination:
                destination.write("desktop-control-plane-smoke")
            attachment = _v2_request(
                handshake, token, "/v2/attachments", method="POST",
                payload={"path": attachment_path, "session_id": session["id"]},
            )["data"]["attachment"]
            submitted = _v2_request(
                handshake, token, f"/v2/conversations/{session['id']}/runs",
                method="POST", payload={"text": "hello", "attachment_handles": [attachment["handle"]]},
            )["data"]
            deadline = time.monotonic() + 15
            persisted = {}
            while time.monotonic() < deadline:
                persisted = _v2_request(
                    handshake, token, f"/v2/runs/{submitted['run_id']}",
                )["data"]["run"]
                if persisted.get("status") in {"completed", "failed", "cancelled", "interrupted"}:
                    break
                time.sleep(0.02)
            messages = _v2_request(
                handshake, token, f"/v2/conversations/{session['id']}/messages",
            )["data"]["messages"]
            if persisted.get("status") != "completed":
                raise RuntimeError(f"Unexpected run state: {persisted.get('status')}")
            if not any(item.get("role") == "assistant" and item.get("content") == "deterministic:hello" for item in messages):
                raise RuntimeError("Deterministic response was not persisted")
            events = _v2_request(
                handshake, token, f"/v2/runs/{submitted['run_id']}/events",
            )["data"]["items"]
            if len(events) < 2:
                raise RuntimeError("The durable event replay did not contain the run lifecycle")
            websocket_events = asyncio.run(_v2_websocket_replay(
                handshake, token, events[0]["event_id"], len(events) - 1,
            ))
            if [item["event_id"] for item in websocket_events] != [item["event_id"] for item in events[1:]]:
                raise RuntimeError("WebSocket replay did not exactly match the missed durable events")
            approval_id = service.core.chat_store.create_approval(
                submitted["run_id"], session["id"], title="Smoke approval",
            )
            approval = _v2_request(
                handshake, token, f"/v2/approvals/{approval_id}/resolve",
                method="POST", payload={"approved": False},
            )["data"]
            if not approval.get("resolved"):
                raise RuntimeError("Approval was not resolved through the desktop contract")
            service.shutdown()
            _write_message({
                "type": "smarti_core_smoke",
                "schema_version": 1,
                "ok": True,
                "health": health,
                "session_id": session["id"],
                "run_id": submitted["run_id"],
                "run_status": persisted.get("status"),
                "response": "deterministic:hello",
                "control_plane": {
                    "api": handshake["api"],
                    "contract": bootstrap["data"]["version"]["contract"],
                    "attachment_handle_path_hidden": "path" not in attachment,
                    "event_count": len(events),
                    "websocket_replay_count": len(websocket_events),
                    "approval_resolved": approval.get("resolved"),
                },
                "final_state": service.state,
            })
            return 0
        threading.Thread(
            target=_monitor_stdin,
            args=(service,),
            daemon=True,
            name="smarti-core-stdin-control",
        ).start()
        service.wait()
        service.shutdown()
        _write_message({
            "type": "smarti_core_stopped",
            "schema_version": 1,
            "state": service.state,
            "pid": os.getpid(),
        })
        return 0
    except Exception as exc:
        try:
            service.shutdown()
        except Exception:
            pass
        _write_message({
            "type": "smarti_core_fatal",
            "schema_version": 1,
            "state": service.state,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        })
        return 1
    finally:
        if temporary_data is not None:
            logging.shutdown()
            temporary_data.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
