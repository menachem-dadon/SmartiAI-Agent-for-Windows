"""Authenticated loopback API for UI-independent Smarti control."""
from .common import *


class SmartiLocalGateway:
    API_VERSION = "v1"
    MAX_BODY_BYTES = 1024 * 1024

    def __init__(self, core, token, port=8765):
        self.core = core
        self.token = str(token or "")
        self.requested_port = max(0, min(65535, int(port or 0)))
        self.port = 0
        self._server = None
        self._thread = None
        self._runtime_file = os.path.join(USER_DATA_DIR, "local-gateway.json")

    def start(self):
        if not self.token or self._server is not None:
            return bool(self._server)
        gateway = self

        class Handler(http.server.BaseHTTPRequestHandler):
            server_version = "SmartiLocalGateway/1"

            def log_message(self, format_text, *args):
                logging.info("LOCAL_GATEWAY | " + format_text, *args)

            def _send(self, status, payload):
                encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                try:
                    self.send_response(int(status))
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    self.wfile.write(encoded)
                    return True
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError):
                    # A remote/local client can disappear while its background
                    # request keeps running. That is a normal disconnect, not
                    # an internal gateway failure worth a second write attempt.
                    logging.debug("Local gateway client disconnected before response delivery")
                    return False

            def _authorized(self):
                supplied = str(self.headers.get("Authorization") or "")
                expected = f"Bearer {gateway.token}"
                return secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))

            def _require_auth(self):
                if self._authorized():
                    return True
                self._send(401, {"error": "unauthorized"})
                return False

            def _body(self):
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    length = 0
                if length < 0 or length > gateway.MAX_BODY_BYTES:
                    raise ValueError("request_body_too_large")
                if not length:
                    return {}
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request_body_must_be_an_object")
                return payload

            def _route(self):
                parsed = urllib.parse.urlparse(self.path)
                path = [urllib.parse.unquote(item) for item in parsed.path.strip("/").split("/") if item]
                query = urllib.parse.parse_qs(parsed.query)
                return path, query

            def do_GET(self):
                path, query = self._route()
                if path == ["v1", "health"]:
                    self._send(200, {"ok": True, "api": gateway.API_VERSION, "pid": os.getpid()})
                    return
                if not self._require_auth():
                    return
                try:
                    if path == ["v1", "sessions"]:
                        self._send(200, {"sessions": gateway.core.chat_store.list_sessions(query.get("q", [""])[0])})
                        return
                    if path == ["v1", "workspaces"]:
                        self._send(200, {"workspaces": gateway.core.chat_store.list_workspaces()})
                        return
                    if path == ["v1", "runs"]:
                        statuses = [item for item in query.get("status", []) if item]
                        self._send(200, {"runs": gateway.core.chat_store.list_runs(
                            session_id=query.get("session_id", [""])[0],
                            statuses=statuses or None,
                        )})
                        return
                    if len(path) == 4 and path[:2] == ["v1", "runs"] and path[3] == "events":
                        self._send(200, {"events": gateway.core.chat_store.run_events(
                            path[2],
                            after_sequence=query.get("after", [0])[0],
                        )})
                        return
                    if path == ["v1", "approvals"]:
                        self._send(200, {"approvals": gateway.core.chat_store.pending_approvals(
                            session_id=query.get("session_id", [""])[0] or None
                        )})
                        return
                    self._send(404, {"error": "not_found"})
                except Exception as exc:
                    logging.exception("Local gateway GET failed")
                    self._send(500, {"error": "internal_error", "detail": str(exc)[:300]})

            def do_POST(self):
                if not self._require_auth():
                    return
                try:
                    path, _query = self._route()
                    payload = self._body()
                    idempotency_key = str(self.headers.get("Idempotency-Key") or "").strip()[:200]
                    scope = "/".join(path)
                    if idempotency_key:
                        cached = gateway.core.chat_store.idempotency_response(scope, idempotency_key)
                        if cached is not None:
                            self._send(200, cached)
                            return

                    response = None
                    status = 202
                    if path == ["v1", "sessions"]:
                        workspace_id = str(payload.get("workspace_id") or "")
                        session = gateway.core.chat_store.create_session(
                            set_active=False,
                            workspace_id=workspace_id or None,
                        )
                        if str(payload.get("title") or "").strip():
                            gateway.core.chat_store.rename_session(session["id"], payload["title"])
                            session = gateway.core.chat_store.session_metadata(session["id"])
                        response = {"session": session}
                        status = 201
                    elif path == ["v1", "workspaces"]:
                        workspace_id = gateway.core.chat_store.create_workspace(
                            title=str(payload.get("title") or "Workspace"),
                            root_path=str(payload.get("root_path") or ""),
                            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
                        )
                        response = {
                            "workspace": next(
                                item for item in gateway.core.chat_store.list_workspaces()
                                if item["id"] == workspace_id
                            )
                        }
                        status = 201
                    elif len(path) == 4 and path[:2] == ["v1", "sessions"] and path[3] == "messages":
                        session_id = path[2]
                        if not gateway.core.chat_store.has_session(session_id):
                            self._send(404, {"error": "session_not_found"})
                            return
                        text_value = str(payload.get("text") or "")
                        attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
                        if not text_value.strip() and not attachments:
                            self._send(400, {"error": "text_or_attachments_required"})
                            return
                        handle = gateway.core.run_manager.submit(
                            session_id,
                            text_value,
                            attachments=attachments,
                            source=str(payload.get("source") or "local_gateway"),
                            metadata={"channel": str(payload.get("channel") or "local_api")},
                            workspace_id=str(payload.get("workspace_id") or "") or None,
                        )
                        response = {"run_id": handle.run_id, "session_id": session_id, "status": "queued"}
                    elif len(path) == 4 and path[:2] == ["v1", "runs"] and path[3] == "cancel":
                        changed = gateway.core.run_manager.cancel(path[2])
                        response = {"run_id": path[2], "cancel_requested": bool(changed)}
                        status = 200 if changed else 404
                    elif len(path) == 4 and path[:2] == ["v1", "sessions"] and path[3] == "read":
                        count = gateway.core.chat_store.mark_session_read(path[2], actor_id=str(payload.get("actor_id") or "local_gateway"))
                        response = {"session_id": path[2], "marked_read": int(count)}
                        status = 200
                    elif len(path) == 4 and path[:2] == ["v1", "approvals"] and path[3] == "resolve":
                        approved = bool(payload.get("approved"))
                        changed = gateway.core.run_manager.resolve_approval(path[2], approved)
                        response = {"approval_id": path[2], "resolved": bool(changed), "approved": approved}
                        status = 200 if changed else 409
                    elif len(path) == 4 and path[:2] == ["v1", "channels"] and path[3] == "messages":
                        channel = path[2]
                        session_id = str(payload.get("session_id") or "")
                        if not session_id:
                            session_id = str(gateway.core.chat_store.create_session(set_active=False)["id"])
                        handle = gateway.core.run_manager.submit(
                            session_id,
                            str(payload.get("text") or ""),
                            attachments=payload.get("attachments") or [],
                            source=f"channel:{channel}",
                            metadata={
                                "channel": channel,
                                "remote_sender": str(payload.get("sender") or "")[:200],
                            },
                            workspace_id=str(payload.get("workspace_id") or "") or None,
                        )
                        response = {"run_id": handle.run_id, "session_id": session_id, "status": "queued"}
                    else:
                        self._send(404, {"error": "not_found"})
                        return
                    if idempotency_key and response is not None:
                        gateway.core.chat_store.save_idempotency_response(scope, idempotency_key, response)
                    self._send(status, response or {})
                except (ValueError, json.JSONDecodeError) as exc:
                    self._send(400, {"error": "invalid_request", "detail": str(exc)[:300]})
                except Exception as exc:
                    logging.exception("Local gateway POST failed")
                    self._send(500, {"error": "internal_error", "detail": str(exc)[:300]})

        try:
            server_type = type(
                "SmartiThreadingHTTPServer",
                (http.server.ThreadingHTTPServer,),
                {"daemon_threads": True, "allow_reuse_address": True},
            )
            try:
                self._server = server_type(("127.0.0.1", self.requested_port), Handler)
            except OSError:
                self._server = server_type(("127.0.0.1", 0), Handler)
            self.port = int(self._server.server_address[1])
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="SmartiLocalGateway",
            )
            self._thread.start()
            self._write_runtime_info()
            logging.info("Local gateway listening on 127.0.0.1:%s", self.port)
            return True
        except Exception:
            logging.exception("Could not start the Smarti local gateway")
            self._server = None
            return False

    def _write_runtime_info(self):
        try:
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            payload = {
                "schema_version": 1,
                "host": "127.0.0.1",
                "port": self.port,
                "pid": os.getpid(),
                "api": self.API_VERSION,
                "started_at": datetime.now().isoformat(timespec="seconds"),
            }
            temporary = self._runtime_file + ".tmp"
            with open(temporary, "w", encoding="utf-8") as destination:
                json.dump(payload, destination, ensure_ascii=False, indent=2)
            os.replace(temporary, self._runtime_file)
        except Exception:
            logging.exception("Could not write local gateway runtime metadata")

    def stop(self):
        server = self._server
        self._server = None
        thread = self._thread
        self._thread = None
        if server:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                logging.exception("Could not stop local gateway cleanly")
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)
        try:
            if os.path.isfile(self._runtime_file):
                os.remove(self._runtime_file)
        except Exception:
            pass
