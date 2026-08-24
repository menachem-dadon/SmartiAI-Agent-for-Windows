import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request
import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from smarti.chat import ChatWindow
from smarti.history import ChatSessionStore
from smarti.local_gateway import SmartiLocalGateway
from smarti.run_manager import ConversationRunManager
from smarti.core_service import SmartiCoreService
from smarti.control_plane_contract import contract_document, typescript_definitions
from smarti.desktop_services import sanitize_desktop_log_lines, tools_snapshot
from smarti.canvas_model import new_canvas_artifact
from smarti.voice_service import VoiceSessionController


class _FakeCore:
    def __init__(self, path):
        self.chat_store = ChatSessionStore(str(path))
        self.settings = {
            "max_concurrent_conversation_runs": 3,
            "api_mode": "local",
            "selected_local_model": "model-a",
            "conversation_title_generation_mode": "local",
        }
        self._local = threading.local()
        self._execution_context = self._local
        self.started = []
        self.snapshots = []
        self.release = threading.Event()
        self.spoken = []
        self.speech_stopped = False

    @contextmanager
    def bind_run_context(
        self, run_id, session_id, cancel_event=None, callbacks=None,
        runtime_snapshot=None,
    ):
        self._local.run_id = run_id
        self._local.session_id = session_id
        self._local.callbacks = callbacks or {}
        self._local.runtime_snapshot = runtime_snapshot or {}
        yield {}

    def send_message(self, text, **kwargs):
        self.started.append((self._local.run_id, self._local.session_id, text, time.monotonic()))
        self.snapshots.append(dict(self._local.runtime_snapshot or {}))
        if str(text).startswith("wait"):
            self.release.wait(3)
        callback = (self._local.callbacks or {}).get("status_callback")
        if callback:
            callback("working")
        return f"answer:{text}"

    def _chat_context_snapshot(self):
        return {"run": getattr(self._local, "run_id", "")}

    def speak_text(self, text):
        self.spoken.append(str(text))

    def stop_speaking(self):
        self.speech_stopped = True

    def _record_run_assistant_message(self, session_id, run_id, user_text, response, **kwargs):
        self.chat_store.append_message(
            "assistant",
            response,
            {"run_id": run_id},
            session_id=session_id,
        )


class ConversationRunStoreTests(unittest.TestCase):
    def test_message_page_projects_persisted_attachments_for_desktop_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "history.json"))
            session_id = store.create_session(set_active=False)["id"]
            attachment = {"name": "preview.png", "path": str(Path(directory) / "preview.png"), "kind": "image"}
            store.append_message("user", "hello", {"attachments": [attachment]}, session_id=session_id)
            message = store.messages_page(session_id)["messages"][0]
            self.assertEqual(message["attachments"], [attachment])
            self.assertEqual(message["metadata"]["attachments"], [attachment])

    def test_workspace_association_flows_from_conversation_to_run(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "history.json"))
            workspace_id = store.create_workspace("Project", root_path=directory)
            session_id = store.create_session(set_active=False, workspace_id=workspace_id)["id"]
            run_id = store.create_run(session_id, "hello")
            self.assertEqual(store.session_metadata(session_id)["workspace_id"], workspace_id)
            self.assertEqual(store.run(run_id)["workspace_id"], workspace_id)

    def test_run_attention_and_read_receipt_are_durable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "history.json"))
            session_id = store.create_session(set_active=False)["id"]
            run_id = store.create_run(session_id, "hello")
            self.assertTrue(store.transition_run(run_id, "running"))
            self.assertTrue(store.transition_run(run_id, "completed", response_text="done"))
            store.create_attention(session_id, run_id)
            self.assertEqual(store.unread_count(session_id), 1)

            reopened = ChatSessionStore(str(Path(directory) / "history.json"))
            self.assertEqual(reopened.run(run_id)["status"], "completed")
            self.assertEqual(reopened.unread_count(), 1)
            self.assertEqual(reopened.mark_session_read(session_id), 1)
            self.assertEqual(reopened.unread_count(), 0)

    def test_sidebar_state_keeps_status_separate_from_unread(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "history.json"))
            session_id = store.create_session(set_active=False)["id"]
            run_id = store.create_run(session_id, "hello")
            record = next(item for item in store.list_sessions() if item["id"] == session_id)
            self.assertEqual(record["runtime_status"], "queued")
            self.assertEqual(record["unread_count"], 0)
            store.transition_run(run_id, "running")
            store.transition_run(run_id, "completed")
            store.create_attention(session_id, run_id)
            record = next(item for item in store.list_sessions() if item["id"] == session_id)
            self.assertEqual(record["runtime_status"], "idle")
            self.assertEqual(record["unread_count"], 1)

    def test_active_run_ui_replays_durable_tool_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "history.json"))
            session_id = store.create_session(set_active=False)["id"]
            run_id = store.create_run(session_id, "hello")
            first = {"event": "tool_start", "tools": [{"action": "search"}]}
            second = {"event": "tool_finish", "results": [{"action": "search", "status": "ok"}]}
            store.append_run_event(run_id, "run_step", {"value": first})
            store.append_run_event(run_id, "run_status", {"value": "חושב... (שלב 2)"})
            store.append_run_event(run_id, "run_step", {"value": second})

            replayed = []
            statuses = []
            bubble = SimpleNamespace(
                handle_agent_event=lambda value: replayed.append(value) or True,
            )
            host = SimpleNamespace(
                core=SimpleNamespace(chat_store=store),
                status_lbl=SimpleNamespace(setText=statuses.append),
            )

            view = {"last_sequence": 0}
            restored = ChatWindow._restore_run_progress(
                host, run_id, bubble, view=view
            )

            self.assertTrue(restored)
            self.assertEqual(replayed, [first, second])
            self.assertEqual(statuses, ["חושב... (שלב 2)"])
            self.assertEqual(
                view["last_sequence"],
                max(event["sequence"] for event in store.run_events(run_id)),
            )

    def test_offscreen_run_finish_does_not_clear_the_visible_run_widgets(self):
        visible_bubble = object()
        visible_container = object()
        host = SimpleNamespace(
            core=SimpleNamespace(
                chat_store=SimpleNamespace(run=lambda _run_id: {"source": "desktop"}),
                settings={},
            ),
            _active_session_id=lambda: "visible-session",
            sync_taskbar_unread_count=lambda **_kwargs: 1,
            _plain_notification_text=lambda value, _limit: value,
            _run_views={},
            current_agent_bubble=visible_bubble,
            current_agent_container=visible_container,
            refresh_chat_title=lambda: (_ for _ in ()).throw(
                AssertionError("offscreen completion must not refresh the visible title")
            ),
            _schedule_scroll_chat_to_bottom=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("offscreen completion must not scroll the visible chat")
            ),
        )

        ChatWindow._finish_managed_run(
            host,
            "offscreen-run",
            "other-session",
            {"response": "done"},
            None,
        )

        self.assertIs(host.current_agent_bubble, visible_bubble)
        self.assertIs(host.current_agent_container, visible_container)


class ConversationRunManagerTests(unittest.TestCase):
    def test_api_key_interruption_is_durable_and_unblocks_without_persisting_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            manager = ConversationRunManager(core)
            core.run_manager = manager
            session_id = core.chat_store.create_session(set_active=False)["id"]
            run_id = core.chat_store.create_run(session_id, "needs key")
            result = []
            worker = threading.Thread(
                target=lambda: result.append(manager.request_api_key(
                    run_id, session_id, "openai_api_key", "OpenAI",
                    "חסר מפתח", "הזן מפתח", "https://example.test/key",
                )),
                daemon=True,
            )
            worker.start()
            for _ in range(100):
                if any(item["event_type"] == "api_key_required" for item in core.chat_store.run_events(run_id)):
                    break
                time.sleep(0.01)
            self.assertTrue(manager.resolve_api_key_request(run_id, "openai_api_key", "super-secret"))
            worker.join(2)
            self.assertEqual(result, ["super-secret"])
            serialized = json.dumps(core.chat_store.run_events(run_id), ensure_ascii=False)
            self.assertIn("api_key_required", serialized)
            self.assertIn("api_key_submitted", serialized)
            required = next(
                item for item in core.chat_store.run_events(run_id)
                if item["event_type"] == "api_key_required"
            )
            self.assertIn("Create new secret key", required["payload"]["key_instructions"])
            self.assertEqual(required["payload"]["provider"], "openai")
            self.assertNotIn("super-secret", serialized)
            manager.shutdown(wait=True)

    def test_restart_marks_executing_run_interrupted_and_keeps_attention(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            session_id = core.chat_store.create_session(set_active=False)["id"]
            run_id = core.chat_store.create_run(session_id, "unfinished")
            self.assertTrue(core.chat_store.transition_run(run_id, "running"))

            manager = ConversationRunManager(core)
            core.run_manager = manager
            try:
                self.assertEqual(core.chat_store.run(run_id)["status"], "interrupted")
                self.assertEqual(core.chat_store.unread_count(session_id), 1)
                events = core.chat_store.run_events(run_id)
                self.assertEqual(events[-1]["event_type"], "run_interrupted")
                self.assertEqual(events[-1]["payload"]["reason"], "runtime_restart")
            finally:
                manager.shutdown(wait=True)

    def test_different_sessions_run_concurrently_and_one_session_is_serial(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            manager = ConversationRunManager(core)
            core.run_manager = manager
            first = core.chat_store.create_session(set_active=False)["id"]
            second = core.chat_store.create_session(set_active=False)["id"]
            run_a = manager.submit(first, "wait-a")
            run_b = manager.submit(first, "queued-b")
            run_c = manager.submit(second, "wait-c")

            deadline = time.monotonic() + 2
            while len(core.started) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual({item[1] for item in core.started[:2]}, {first, second})
            self.assertNotIn("queued-b", [item[2] for item in core.started])

            core.release.set()
            self.assertTrue(run_a.done_event.wait(2))
            self.assertTrue(run_b.done_event.wait(2))
            self.assertTrue(run_c.done_event.wait(2))
            first_texts = [item[2] for item in core.started if item[1] == first]
            self.assertEqual(first_texts, ["wait-a", "queued-b"])
            self.assertEqual(core.chat_store.unread_count(), 3)
            manager.shutdown(wait=True)

    def test_legacy_three_run_setting_does_not_cap_independent_conversations(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            manager = ConversationRunManager(core)
            core.run_manager = manager
            try:
                handles = []
                for index in range(6):
                    session_id = core.chat_store.create_session(set_active=False)["id"]
                    handles.append(manager.submit(session_id, f"wait-{index}"))

                deadline = time.monotonic() + 10
                while len(core.started) < 6 and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(len(core.started), 6)
                self.assertIsNone(manager.max_concurrent)

                core.release.set()
                self.assertTrue(all(handle.done_event.wait(10) for handle in handles))
            finally:
                core.release.set()
                manager.shutdown(wait=True)

    def test_first_user_message_assigns_an_immediate_unique_title(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            manager = ConversationRunManager(core)
            core.run_manager = manager
            first = core.chat_store.create_session(set_active=False)["id"]
            second = core.chat_store.create_session(set_active=False)["id"]

            first_run = manager.submit(first, "same opening request")
            second_run = manager.submit(second, "same opening request")

            first_title = core.chat_store.session_metadata(first)["title"]
            second_title = core.chat_store.session_metadata(second)["title"]
            self.assertEqual(first_title, "same opening request")
            self.assertEqual(second_title, "same opening request (2)")
            self.assertTrue(core.chat_store.session_metadata(first)["title_generated"])
            self.assertTrue(core.chat_store.session_metadata(second)["title_generated"])

            core.release.set()
            self.assertTrue(first_run.done_event.wait(2))
            self.assertTrue(second_run.done_event.wait(2))
            manager.shutdown(wait=True)

    def test_ai_title_starts_with_a_unique_provisional_title_then_replaces_it(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.settings["conversation_title_generation_mode"] = "ai"
            observed = {}

            def schedule_title(session_id, user_text, assistant_text, **kwargs):
                metadata = core.chat_store.session_metadata(session_id)
                observed.update({
                    "title": metadata["title"],
                    "generated": metadata["title_generated"],
                    "assistant_text": assistant_text,
                    "provider_mode": kwargs.get("provider_mode"),
                    "current_model": kwargs.get("current_model"),
                })
                return bool(core.chat_store.apply_initial_title(session_id, "הדגמת יכולות במסמך Word"))

            core._schedule_conversation_title = schedule_title
            manager = ConversationRunManager(core)
            session_id = core.chat_store.create_session(set_active=False)["id"]

            handle = manager.submit(session_id, "צור לי מסמך וורד שמדגים את יכולותיך")

            self.assertEqual(observed["title"], "צור לי מסמך וורד שמדגים את יכולותיך")
            self.assertFalse(observed["generated"])
            self.assertEqual(observed["assistant_text"], "")
            self.assertEqual(observed["provider_mode"], "local")
            self.assertEqual(observed["current_model"], "model-a")
            self.assertEqual(
                core.chat_store.session_metadata(session_id)["title"],
                "הדגמת יכולות במסמך Word",
            )
            self.assertTrue(core.chat_store.session_metadata(session_id)["title_generated"])
            self.assertTrue(handle.done_event.wait(2))
            manager.shutdown(wait=True)

    def test_empty_model_response_is_persisted_as_a_visible_failed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.send_message = lambda *_args, **_kwargs: ""
            manager = ConversationRunManager(core)
            session_id = core.chat_store.create_session(set_active=False)["id"]

            handle = manager.submit(session_id, "continue")

            self.assertTrue(handle.done_event.wait(2))
            self.assertEqual(handle.status, "failed")
            self.assertIn("בלי להחזיר תשובה", handle.response)
            messages = core.chat_store.messages(session_id)
            self.assertIn("בלי להחזיר תשובה", messages[-1]["content"])
            self.assertEqual(messages[-1]["metadata"]["run_id"], handle.run_id)
            manager.shutdown(wait=True)

    def test_queued_run_keeps_the_model_selected_when_it_was_submitted(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            manager = ConversationRunManager(core)
            core.run_manager = manager
            session_id = core.chat_store.create_session(set_active=False)["id"]
            first = manager.submit(session_id, "wait-first")
            second = manager.submit(session_id, "second")
            core.settings["selected_local_model"] = "model-b"
            core.release.set()

            self.assertTrue(first.done_event.wait(2))
            self.assertTrue(second.done_event.wait(2))
            self.assertEqual([item.get("model_name") for item in core.snapshots], ["model-a", "model-a"])
            manager.shutdown(wait=True)


class DesktopToolSnapshotTests(unittest.TestCase):
    def test_skills_are_structured_registry_rows_and_never_split_into_characters(self):
        class Registry:
            def trust_status(self, kind, name):
                return "trusted" if name != "disabled-skill" else "disabled"

        core = SimpleNamespace(
            settings={
                "tools_config": {"sample_tool": True, "mcp_demo": False},
                "skills_config": {"skill-one": True, "disabled-skill": False},
            },
            tool_registry=Registry(),
            skill_registry={
                "skill-one": {"description": "מדריך מלא", "source": "local"},
                "disabled-skill": {"description": "כבוי", "source": "builtin"},
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            tools_dir = Path(directory) / "tools"
            mcp_dir = Path(directory) / "mcp"
            tools_dir.mkdir(); mcp_dir.mkdir()
            (tools_dir / "sample_tool.pyw").write_text("", encoding="utf-8")
            (mcp_dir / "demo.txt").write_text("{}", encoding="utf-8")
            with mock.patch("smarti.desktop_services.TOOLS_DIR", str(tools_dir)), mock.patch("smarti.desktop_services.MCP_TOOLS_DIR", str(mcp_dir)):
                snapshot = tools_snapshot(core)

        rows = {(item["kind"], item["name"]): item for item in snapshot["extensions"]}
        self.assertEqual(set(rows), {
            ("custom", "sample_tool"), ("mcp", "demo"),
            ("skill", "skill-one"), ("skill", "disabled-skill"),
        })
        self.assertTrue(rows[("skill", "skill-one")]["enabled"])
        self.assertFalse(rows[("skill", "disabled-skill")]["enabled"])
        self.assertFalse(rows[("skill", "disabled-skill")]["removable"])


class LocalGatewayTests(unittest.TestCase):
    def test_desktop_log_filter_hides_personal_payloads_but_keeps_diagnostics(self):
        rows = sanitize_desktop_log_lines([
            '2026-08-23 03:00:00 | INFO | PERSONAL | kind=user_message | content=סוד',
            '2026-08-23 03:00:01 | INFO | AUDIT | {"event":"tool", "path":"C:/Users/name/file.txt", "status":"ok"}',
        ])
        joined = "\n".join(rows)
        self.assertNotIn("סוד", joined)
        self.assertNotIn("C:/Users/name", joined)
        self.assertIn('"status": "ok"', joined)

    @staticmethod
    def _request(gateway, path, *, method="GET", payload=None, headers=None):
        request_headers = {"Authorization": "Bearer test-token"}
        request_headers.update(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{gateway.port}{path}",
            data=body,
            method=method,
            headers=request_headers,
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))

    def test_tools_route_uses_persistent_core_trust_and_surfaces_install_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.run_manager = ConversationRunManager(core)
            core.skill_registry = {}
            core.tool_registry = SimpleNamespace(trust_status=lambda _kind, _name: "trusted")
            trust_calls = []
            core.set_tool_trust = lambda kind, name, trusted, metadata=None: trust_calls.append((kind, name, trusted, metadata))
            core.install_local_skill_package = lambda _path: "ERROR: invalid Skill bundle"
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            try:
                status, _, _ = self._request(
                    gateway, "/v2/management/tools", method="POST",
                    payload={"action": "set_trust", "kind": "skill", "name": "demo", "trusted": True},
                    headers={"Idempotency-Key": "trust-demo"},
                )
                self.assertEqual(status, 200)
                self.assertEqual(trust_calls[0][:3], ("skill", "demo", True))
                with self.assertRaises(urllib.error.HTTPError) as install_error:
                    self._request(
                        gateway, "/v2/management/tools", method="POST",
                        payload={"action": "install_skill", "path": str(Path(directory) / "bad.zip")},
                        headers={"Idempotency-Key": "install-bad"},
                    )
                self.assertEqual(install_error.exception.code, 400)
                body = json.loads(install_error.exception.read().decode("utf-8"))
                self.assertIn("invalid Skill bundle", body["detail"])
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_active_provider_secret_change_rebuilds_the_runtime_model(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.settings["api_mode"] = "openai"
            core.run_manager = ConversationRunManager(core)
            core._save_settings = lambda: None
            core.setup_count = 0
            core.setup_model = lambda: setattr(core, "setup_count", core.setup_count + 1)
            core.mark_secret_for_deletion = lambda key: core.settings.__setitem__(key, "")
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            try:
                self._request(
                    gateway, "/v2/settings/secrets/openai_api_key", method="PUT",
                    payload={"value": "new-secret"}, headers={"Idempotency-Key": "secret-set"},
                )
                self._request(
                    gateway, "/v2/settings/secrets/openai_api_key", method="DELETE",
                    headers={"Idempotency-Key": "secret-delete"},
                )
                self.assertEqual(core.setup_count, 2)
                self.assertEqual(core.settings["openai_api_key"], "")
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_diagnostic_refuses_to_compete_with_an_active_agent_run(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.run_manager = ConversationRunManager(core)
            session_id = core.chat_store.create_session(set_active=False)["id"]
            core.chat_store.create_run(session_id, "still queued")
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    self._request(
                        gateway, "/v2/management/diagnostics", method="POST",
                        payload={"action": "scan", "include_network": False},
                        headers={"Idempotency-Key": "diagnostic-active-run"},
                    )
                self.assertEqual(error.exception.code, 400)
                body = json.loads(error.exception.read().decode("utf-8"))
                self.assertEqual(body["detail"], "diagnostic_blocked_while_agent_running")
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_gateway_requires_token_and_deduplicates_message_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.release.set()
            core.run_manager = ConversationRunManager(core)
            session_id = core.chat_store.create_session(set_active=False)["id"]
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            base = f"http://127.0.0.1:{gateway.port}/v1"
            try:
                with self.assertRaises(urllib.error.HTTPError) as context:
                    urllib.request.urlopen(f"{base}/sessions", timeout=10)
                self.assertEqual(context.exception.code, 401)

                body = json.dumps({"text": "remote"}).encode("utf-8")
                request = urllib.request.Request(
                    f"{base}/sessions/{session_id}/messages",
                    data=body,
                    method="POST",
                    headers={
                        "Authorization": "Bearer test-token",
                        "Content-Type": "application/json",
                        "Idempotency-Key": "same-request",
                    },
                )
                first = json.loads(urllib.request.urlopen(request, timeout=10).read().decode("utf-8"))
                second = json.loads(urllib.request.urlopen(request, timeout=10).read().decode("utf-8"))
                self.assertEqual(first["run_id"], second["run_id"])
                self.assertEqual(len(core.chat_store.list_runs(session_id=session_id)), 1)
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_v2_contract_artifacts_are_generated_from_the_authoritative_schema(self):
        document = contract_document()
        operation_ids = {item["operation_id"] for item in document["operations"]}
        self.assertTrue({
            "submitRun", "cancelRun", "resolveApproval", "listConversations",
            "getSettings", "registerAttachment", "subscribeEvents", "readCodexQuota",
            "getModelReasoning", "setModelReasoning", "manageTask", "manageMemory",
            "manageTools", "diagnostics", "workspaceTree", "createTerminal",
            "legalStatus", "acceptLegal", "settingsAction", "manageMemories", "clearUsage",
            "diagnosticProgress", "listTtsVoices",
        }.issubset(operation_ids))
        generated_json = json.loads(Path("desktop-contract/v2.contract.json").read_text(encoding="utf-8"))
        generated_types = Path("desktop-contract/v2.generated.d.ts").read_text(encoding="utf-8")
        self.assertEqual(generated_json, document)
        self.assertEqual(generated_types, typescript_definitions())

    def test_v2_rejects_bad_auth_origin_schema_and_oversized_body(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            try:
                with self.assertRaises(urllib.error.HTTPError) as auth_error:
                    urllib.request.urlopen(f"http://127.0.0.1:{gateway.port}/v2/bootstrap", timeout=10)
                self.assertEqual(auth_error.exception.code, 401)

                with self.assertRaises(urllib.error.HTTPError) as origin_error:
                    self._request(gateway, "/v2/bootstrap", headers={"Origin": "https://evil.example"})
                self.assertEqual(origin_error.exception.code, 403)

                with self.assertRaises(urllib.error.HTTPError) as schema_error:
                    self._request(
                        gateway, "/v2/conversations", method="POST",
                        payload={"unexpected": True},
                    )
                self.assertEqual(schema_error.exception.code, 400)
                details = json.loads(schema_error.exception.read().decode("utf-8"))
                self.assertEqual(details["error"], "invalid_request")

                oversized = b"{" + (b" " * (gateway.MAX_BODY_BYTES + 1)) + b"}"
                request = urllib.request.Request(
                    f"http://127.0.0.1:{gateway.port}/v2/conversations",
                    data=oversized, method="POST",
                    headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
                )
                with self.assertRaises(urllib.error.HTTPError) as size_error:
                    urllib.request.urlopen(request, timeout=10)
                self.assertEqual(size_error.exception.code, 413)
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_v2_conversation_attachment_settings_approval_and_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.settings["openai_api_key"] = "plain-secret-must-not-leak"
            core.release.set()
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            try:
                _, _, created = self._request(
                    gateway, "/v2/conversations", method="POST",
                    payload={"title": "בדיקת חוזה"}, headers={"Idempotency-Key": "conversation-1"},
                )
                session_id = created["data"]["conversation"]["id"]
                _, _, listed = self._request(gateway, "/v2/conversations")
                self.assertIn(session_id, {item["id"] for item in listed["data"]["items"]})
                _, replay_headers, replayed = self._request(
                    gateway, "/v2/conversations", method="POST",
                    payload={"title": "לא אמור להיווצר"}, headers={"Idempotency-Key": "conversation-1"},
                )
                self.assertEqual(replayed["data"]["conversation"]["id"], session_id)
                self.assertEqual(replay_headers["Idempotency-Replayed"], "true")

                core.chat_store.append_message("assistant", "שלום", {}, session_id=session_id)
                _, _, exported = self._request(
                    gateway, f"/v2/conversations/{session_id}/export"
                )
                self.assertIn("schema_version", exported["data"])
                self.assertEqual(exported["data"]["session"]["id"], session_id)
                self.assertEqual(exported["data"]["session"]["messages"][-1]["content"], "שלום")

                key_run_id = core.chat_store.create_run(session_id, "key")
                supplied = []
                key_waiter = threading.Thread(
                    target=lambda: supplied.append(core.run_manager.request_api_key(
                        key_run_id, session_id, "openai_api_key", "OpenAI",
                        "חסר מפתח", "הזן מפתח", "https://example.test/key",
                    )),
                    daemon=True,
                )
                key_waiter.start()
                for _ in range(100):
                    if any(item["event_type"] == "api_key_required" for item in core.chat_store.run_events(key_run_id)):
                        break
                    time.sleep(0.01)
                _, _, key_reply = self._request(
                    gateway, f"/v2/runs/{key_run_id}/api-key", method="POST",
                    payload={"secret_key": "openai_api_key", "value": "route-secret"},
                )
                key_waiter.join(2)
                self.assertTrue(key_reply["data"]["accepted"])
                self.assertEqual(supplied, ["route-secret"])
                self.assertNotIn("route-secret", json.dumps(core.chat_store.run_events(key_run_id)))

                attachment_path = Path(directory) / "שלום.txt"
                attachment_path.write_text("attachment-data", encoding="utf-8")
                _, _, registered = self._request(
                    gateway, "/v2/attachments", method="POST",
                    payload={"path": str(attachment_path), "session_id": session_id},
                )
                attachment = registered["data"]["attachment"]
                self.assertNotIn("path", attachment)

                _, _, submitted = self._request(
                    gateway, f"/v2/conversations/{session_id}/runs", method="POST",
                    payload={
                        "text": "hello", "attachment_handles": [attachment["handle"]],
                        "provider_mode": "local", "model_name": "model-b",
                    },
                    headers={"X-Request-ID": "request-correlation-1"},
                )
                run_id = submitted["data"]["run_id"]
                for _ in range(100):
                    _, _, run_payload = self._request(gateway, f"/v2/runs/{run_id}")
                    if run_payload["data"]["run"]["status"] == "completed":
                        break
                    time.sleep(0.02)
                self.assertEqual(run_payload["data"]["run"]["status"], "completed")
                self.assertEqual(run_payload["data"]["run"]["metadata"]["request_id"], "request-correlation-1")
                self.assertEqual(run_payload["data"]["run"]["metadata"]["provider_mode"], "local")
                self.assertEqual(run_payload["data"]["run"]["metadata"]["model_name"], "model-b")

                _, _, replay = self._request(gateway, "/v2/events/replay?after_event_id=0")
                self.assertTrue(any(item["run_id"] == run_id for item in replay["data"]["items"]))

                self._request(gateway, "/v2/audio/tts", method="POST", payload={"text": "שלום"})
                for _ in range(50):
                    if core.spoken:
                        break
                    time.sleep(0.01)
                self.assertEqual(core.spoken, ["שלום"])
                self._request(gateway, "/v2/audio/tts/stop", method="POST", payload={})
                self.assertTrue(core.speech_stopped)

                statuses = []
                gateway._voice = VoiceSessionController(
                    lambda: core.settings,
                    recognizer=lambda _settings, _cancel, status: (
                        status("מקשיב..."), statuses.append("מקשיב..."), "שלום סמארטי"
                    )[-1],
                )
                _, _, voice_started = self._request(
                    gateway, "/v2/audio/voice", method="POST", payload={}
                )
                voice_session = voice_started["data"]["session_id"]
                for _ in range(100):
                    _, _, voice = self._request(gateway, "/v2/audio/voice/status")
                    if not voice["data"]["active"]:
                        break
                    time.sleep(0.01)
                self.assertEqual(voice["data"]["session_id"], voice_session)
                self.assertEqual(voice["data"]["transcript"], "שלום סמארטי")
                self.assertEqual(statuses, ["מקשיב..."])

                quota_payload = {
                    "available": True, "plan_type": "plus",
                    "five_hour": {"remaining_percent": 63, "window_minutes": 300},
                    "weekly": {"remaining_percent": 94, "window_minutes": 10080},
                }
                with mock.patch("smarti.codex_signin.CodexSignInProvider.read_rate_limits", return_value=quota_payload):
                    _, _, quota = self._request(gateway, "/v2/providers/openai_codex_signin/quota")
                self.assertEqual(quota["data"]["five_hour"]["remaining_percent"], 63)
                self.assertEqual(quota["data"]["weekly"]["remaining_percent"], 94)

                _, _, reasoning = self._request(
                    gateway,
                    "/v2/providers/openai_codex_signin/reasoning?model=Codex%20default",
                )
                self.assertEqual(reasoning["data"]["reasoning_effort"], "auto")
                self.assertIn("high", {item["value"] for item in reasoning["data"]["reasoning_options"]})
                _, _, selected_reasoning = self._request(
                    gateway, "/v2/providers/openai_codex_signin/reasoning", method="POST",
                    payload={"model": "Codex default", "effort": "high"},
                )
                self.assertEqual(selected_reasoning["data"]["reasoning_effort"], "high")
                self.assertEqual(core.settings["codex_reasoning_effort"], "high")

                _, _, settings = self._request(gateway, "/v2/settings")
                serialized = json.dumps(settings, ensure_ascii=False)
                self.assertNotIn("plain-secret-must-not-leak", serialized)
                self.assertTrue(settings["data"]["secrets"]["openai_api_key"]["configured"])

                _, _, autonomy = self._request(
                    gateway, "/v2/settings", method="PATCH",
                    payload={"values": {"autonomy_mode": "max_autonomy"}},
                )
                self.assertEqual(autonomy["data"]["values"]["permission_level"], 3)
                self.assertFalse(autonomy["data"]["values"]["raw_shell_requires_approval"])

                approval_id = core.chat_store.create_approval(run_id, session_id, title="Approve")
                _, _, resolved = self._request(
                    gateway, f"/v2/approvals/{approval_id}/resolve", method="POST",
                    payload={"approved": False},
                )
                self.assertTrue(resolved["data"]["resolved"])
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_v2_websocket_reconnect_replays_exactly_the_missed_durable_events(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.release.set()
            core.run_manager = ConversationRunManager(core)
            session_id = core.chat_store.create_session(set_active=False)["id"]
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            try:
                _, _, submitted = self._request(
                    gateway, f"/v2/conversations/{session_id}/runs", method="POST",
                    payload={"text": "websocket"}, headers={"X-Request-ID": "ws-request"},
                )
                run_id = submitted["data"]["run_id"]
                for _ in range(100):
                    events = core.chat_store.events_after(0, session_id=session_id)
                    event_types = {item["event_type"] for item in events}
                    if (
                        "command_accepted" in event_types
                        and "run_completed" in event_types
                        and core.chat_store.run(run_id)["status"] == "completed"
                    ):
                        break
                    time.sleep(0.02)
                expected_missed = events[1:]

                async def receive(url, count):
                    import aiohttp
                    headers = {"Authorization": "Bearer test-token", "Origin": "tauri://localhost"}
                    async with aiohttp.ClientSession() as client:
                        async with client.ws_connect(url, headers=headers) as socket:
                            return [await socket.receive_json(timeout=5) for _ in range(count)]

                base = f"http://127.0.0.1:{gateway.port}/v2/events"
                first_batch = asyncio.run(receive(
                    f"{base}?session_id={session_id}&after_event_id={events[0]['event_id']}",
                    len(expected_missed),
                ))
                self.assertEqual(
                    [item["event_id"] for item in first_batch],
                    [item["event_id"] for item in expected_missed],
                )
                last_cursor = first_batch[-1]["event_id"]
                persisted = core.chat_store.append_run_event(run_id, "diagnostic_test", {"value": 1})
                second_batch = asyncio.run(receive(
                    f"{base}?session_id={session_id}&after_event_id={last_cursor}", 1,
                ))
                self.assertEqual(second_batch[0]["event_id"], persisted["id"])
                self.assertEqual(second_batch[0]["request_id"], "ws-request")
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_v2_management_schema_and_scoped_workbench_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "תיקיית עבודה"
            root.mkdir()
            (root / "שלום.md").write_text("# שלום\nתוכן", encoding="utf-8")
            outside = Path(directory) / "outside.txt"
            outside.write_text("blocked", encoding="utf-8")
            core = _FakeCore(Path(directory) / "history.json")
            core.settings["ui_preferences"] = {}
            core._save_settings = lambda: None
            core._sandbox_enabled = lambda: False
            core._default_output_dir = lambda: str(root)
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            try:
                _, _, legal = self._request(gateway, "/v2/management/legal")
                self.assertFalse(legal["data"]["accepted"])
                with self.assertRaises(urllib.error.HTTPError) as wrong_legal:
                    self._request(
                        gateway, "/v2/management/legal", method="POST",
                        payload={"accepted": True, "version": "old-version"},
                    )
                self.assertEqual(wrong_legal.exception.code, 400)
                _, _, accepted = self._request(
                    gateway, "/v2/management/legal", method="POST",
                    payload={"accepted": True, "version": legal["data"]["version"]},
                )
                self.assertTrue(accepted["data"]["accepted"])

                _, _, diagnostic_progress = self._request(gateway, "/v2/management/diagnostics")
                self.assertEqual(diagnostic_progress["data"]["status"], "idle")
                self.assertFalse(diagnostic_progress["data"]["running"])

                _, _, schema = self._request(gateway, "/v2/settings/schema")
                self.assertIn("providers", {item["id"] for item in schema["data"]["groups"]})
                self.assertTrue(schema["data"]["fields"]["openai_api_key"]["secret"])
                openai_provider = next(
                    item for item in schema["data"]["providers"]
                    if item["id"] == "openai"
                )
                self.assertEqual(openai_provider["secret_key"], "openai_api_key")
                self.assertEqual(openai_provider["help_url"], "https://platform.openai.com/api-keys")
                self.assertIn("Create new secret key", openai_provider["key_instructions"])
                self.assertEqual(
                    schema["data"]["secret_help"]["tavily_api_key"]["help_url"],
                    "https://app.tavily.com/home",
                )
                self.assertNotIn("plain", json.dumps(schema, ensure_ascii=False))

                with mock.patch(
                    "smarti.local_gateway.list_tts_voices",
                    return_value=[{"id": "he-IL-HilaNeural", "name": "הילה"}],
                ):
                    _, _, voices = self._request(gateway, "/v2/audio/tts/voices")
                self.assertEqual(
                    voices["data"]["items"],
                    [{"id": "he-IL-HilaNeural", "name": "הילה"}],
                )

                ssl_response = mock.MagicMock()
                ssl_response.__enter__.return_value.status = 204
                original_urlopen = urllib.request.urlopen
                def selective_urlopen(target, *args, **kwargs):
                    url = str(getattr(target, "full_url", target))
                    if url == "https://www.gstatic.com/generate_204":
                        return ssl_response
                    return original_urlopen(target, *args, **kwargs)
                with mock.patch("smarti.ssl_compat.create_ssl_context", return_value=object()) as create_context, mock.patch(
                    "urllib.request.urlopen", side_effect=selective_urlopen,
                ):
                    _, _, ssl_test = self._request(
                        gateway, "/v2/management/settings/actions", method="POST",
                        payload={"action": "ssl_test", "ssl_trust_mode": "legacy_insecure", "ssl_custom_ca_path": ""},
                    )
                self.assertTrue(ssl_test["data"]["ok"])
                self.assertFalse(ssl_test["data"]["verified"])
                pending_ssl_settings = create_context.call_args.args[0]
                self.assertEqual(pending_ssl_settings["ssl_trust_mode"], "legacy_insecure")
                self.assertTrue(pending_ssl_settings["allow_insecure_ssl_compat"])

                managed_ca = str(root / "managed-ca.pem")
                with mock.patch("smarti.ssl_compat.import_custom_ca", return_value=managed_ca), mock.patch(
                    "smarti.ssl_compat.validate_custom_ca", return_value=(True, "תעודה תקינה"),
                ), mock.patch(
                    "smarti.ssl_compat.describe_custom_ca", return_value={"name": "Filter Root"},
                ):
                    _, _, imported_ca = self._request(
                        gateway, "/v2/management/settings/actions", method="POST",
                        payload={"action": "ssl_import_ca", "source_path": str(root / "filter.crt")},
                    )
                self.assertEqual(imported_ca["data"]["path"], managed_ca)
                self.assertEqual(imported_ca["data"]["metadata"]["name"], "Filter Root")

                with self.assertRaises(urllib.error.HTTPError) as unconfirmed_log_clear:
                    self._request(
                        gateway, "/v2/management/settings/actions", method="POST",
                        payload={"action": "log_clear", "confirmation": "לא"},
                    )
                self.assertEqual(unconfirmed_log_clear.exception.code, 400)
                with mock.patch("smarti.common.clear_unified_log_file") as clear_log:
                    _, _, cleared_log = self._request(
                        gateway, "/v2/management/settings/actions", method="POST",
                        payload={"action": "log_clear", "confirmation": "נקה לוג"},
                    )
                clear_log.assert_called_once_with()
                self.assertTrue(cleared_log["data"]["cleared"])

                self._request(gateway, "/v2/workbench/root", method="PATCH", payload={"path": str(root)})
                _, _, tree = self._request(gateway, "/v2/workbench/tree?depth=2")
                self.assertEqual(tree["data"]["root"]["path"], str(root.resolve()))
                self.assertEqual(tree["data"]["items"][0]["name"], "שלום.md")
                _, _, preview = self._request(gateway, "/v2/workbench/file?path=%D7%A9%D7%9C%D7%95%D7%9D.md")
                self.assertIn("# שלום", preview["data"]["text"])
                with self.assertRaises(urllib.error.HTTPError) as traversal:
                    self._request(gateway, "/v2/workbench/file?path=../outside.txt")
                self.assertEqual(traversal.exception.code, 400)
                core._sandbox_enabled = lambda: True
                core._sandbox_root = lambda: str(root)
                with self.assertRaises(urllib.error.HTTPError) as outside_root:
                    self._request(gateway, "/v2/workbench/root", method="PATCH", payload={"path": str(Path(directory))})
                self.assertEqual(outside_root.exception.code, 400)

                _, _, created = self._request(gateway, "/v2/workbench/terminals", method="POST", payload={})
                terminal_id = created["data"]["id"]
                self._request(
                    gateway, f"/v2/workbench/terminals/{terminal_id}", method="POST",
                    payload={"action": "write", "text": "Write-Output SMARTI_TERMINAL_OK; Write-Output (Get-Location).Path"},
                )
                output = ""
                # Cold Windows PowerShell startup can exceed 1.5s on busy CI hosts.
                for _ in range(120):
                    _, _, polled = self._request(gateway, f"/v2/workbench/terminals/{terminal_id}")
                    output += polled["data"]["output"]
                    if "SMARTI_TERMINAL_OK" in output and "תיקיית עבודה" in output:
                        break
                    time.sleep(0.05)
                self.assertIn("SMARTI_TERMINAL_OK", output)
                self.assertIn("תיקיית עבודה", output)
                _, _, closed = self._request(gateway, f"/v2/workbench/terminals/{terminal_id}", method="DELETE")
                self.assertTrue(closed["data"]["closed"])

                session = core.chat_store.ensure_active_session()
                canvas = new_canvas_artifact({
                    "canvas_id": "safe-canvas", "title": "בדיקת קנבס",
                    "html": "<button id='go'>המשך</button><script>window.open('file:///C:/secret')</script>",
                    "buttons": [{"id": "go", "label": "המשך", "action": "continue"}],
                })
                core.chat_store.append_message("assistant", "Canvas", {"canvases": [canvas]}, session["id"])
                _, _, canvases = self._request(gateway, f"/v2/conversations/{session['id']}/canvases")
                self.assertEqual(canvases["data"]["items"][0]["id"], "safe-canvas")
                _, _, rendered = self._request(gateway, f"/v2/conversations/{session['id']}/canvases/safe-canvas")
                self.assertIn("<button id='go'>", rendered["data"]["canvas"]["document"])
                self.assertNotIn("images", rendered["data"]["canvas"])
                _, _, patched = self._request(
                    gateway, f"/v2/conversations/{session['id']}/canvases/safe-canvas", method="PATCH",
                    payload={"action": "layout", "button_positions": [{"id": "go", "x": 4, "y": 8, "width": 80, "height": 30}]},
                )
                self.assertTrue(patched["data"]["changed"])

                source = SimpleNamespace(browser_id="edge", browser_name="Microsoft Edge", profile_name="בדיקה")
                imported = {
                    "history": [{"url": "https://example.test", "title": "Example"}],
                    "bookmarks": [{"url": "https://example.test", "title": "Example"}],
                    "cookies": [{"name": "safe", "value": "temporary", "domain": "example.test", "path": "/"}],
                    "cookie_stats": {"read": 1, "skipped_encrypted": 2}, "imported_at": "2026-08-23T00:00:00Z",
                }
                with mock.patch("smarti.local_gateway.discover_browser_profiles", return_value=[source]), mock.patch("smarti.local_gateway.import_profile_data", return_value=imported):
                    _, _, discovered = self._request(gateway, "/v2/browser/import/sources")
                    self.assertEqual(discovered["data"]["items"][0]["id"], "edge:0")
                    _, _, report = self._request(
                        gateway, "/v2/browser/import", method="POST",
                        payload={"source_id": "edge:0", "history": True, "bookmarks": True, "cookies": True},
                    )
                    self.assertEqual(len(report["data"]["history"]), 1)
                    self.assertEqual(report["data"]["cookie_stats"]["skipped_encrypted"], 2)
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_v2_diagnostic_progress_and_cancellation_are_live(self):
        class Result:
            def to_dict(self):
                return {"id": "test.progress", "status": "pass", "title_he": "בדיקה"}

        started = threading.Event()
        instances = []

        class SlowDiagnostic:
            def __init__(self, _core):
                self.stopped = False
                instances.append(self)

            def request_stop(self):
                self.stopped = True

            def run(self, _include_network, progress_callback, result_callback):
                progress_callback(1, 3, "בדיקה ראשונה")
                result = Result()
                result_callback(result)
                started.set()
                time.sleep(0.35)
                if self.stopped:
                    return [result]
                progress_callback(2, 3, "בדיקה שנייה")
                return [result]

            def perform_repair(self, _action_id):
                return "ok"

        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.json")
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            responses = []
            failures = []

            def run_scan():
                try:
                    responses.append(self._request(
                        gateway, "/v2/management/diagnostics", method="POST",
                        payload={"action": "scan", "include_network": False},
                    ))
                except Exception as exc:
                    failures.append(exc)

            try:
                with mock.patch("smarti.doctor.SmartiDiagnostic", SlowDiagnostic):
                    worker = threading.Thread(target=run_scan, daemon=True)
                    worker.start()
                    self.assertTrue(started.wait(5))
                    _, _, progress = self._request(gateway, "/v2/management/diagnostics")
                    self.assertTrue(progress["data"]["running"])
                    self.assertEqual(progress["data"]["current"], 1)
                    self.assertEqual(progress["data"]["total"], 3)
                    self.assertEqual(progress["data"]["label"], "בדיקה ראשונה")
                    _, _, cancelled = self._request(
                        gateway, "/v2/management/diagnostics", method="POST",
                        payload={"action": "cancel"},
                    )
                    self.assertTrue(cancelled["data"]["cancel_requested"])
                    worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertFalse(failures)
                self.assertEqual(len(responses), 1)
                self.assertTrue(instances[0].stopped)
                _, _, final = self._request(gateway, "/v2/management/diagnostics")
                self.assertFalse(final["data"]["running"])
                self.assertEqual(final["data"]["status"], "cancelled")
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)


class HeadlessCoreServiceTests(unittest.TestCase):
    def test_fatal_startup_is_an_explicit_service_state(self):
        events = []

        def fail_factory(**_kwargs):
            raise RuntimeError("startup failed")

        service = SmartiCoreService(core_factory=fail_factory, token="test", port=0)
        service.subscribe(events.append)
        with self.assertRaisesRegex(RuntimeError, "startup failed"):
            service.start()

        self.assertEqual(service.state, "fatal")
        self.assertFalse(service.health()["ready"])
        self.assertIn("RuntimeError", service.health()["fatal_error"])
        self.assertEqual(
            [event["event_type"] for event in events],
            ["service_starting", "service_fatal"],
        )

    def test_fresh_process_smoke_is_qt_free_and_persists_a_fake_run(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["SMARTI_DATA_DIR"] = directory
            completed = subprocess.run(
                [
                    sys.executable,
                    "smarti_core_service.py",
                    "--smoke",
                    "--data-dir",
                    directory,
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            messages = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
            self.assertEqual([item["type"] for item in messages], [
                "smarti_core_ready",
                "smarti_core_smoke",
            ])
            ready, result = messages
            self.assertEqual(ready["state"], "ready")
            self.assertTrue(ready["health"]["ready"])
            self.assertFalse(ready["health"]["qt_loaded"])
            self.assertTrue(all(ready["health"]["components"].values()))
            self.assertTrue(result["ok"])
            self.assertEqual(result["run_status"], "completed")
            self.assertEqual(result["response"], "deterministic:hello")
            self.assertEqual(result["final_state"], "stopped")

    def test_parent_pipe_requests_graceful_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "smarti_core_service.py",
                    "--data-dir",
                    directory,
                ],
                cwd=str(Path(__file__).resolve().parents[1]),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                ready = json.loads(process.stdout.readline())
                self.assertEqual(ready["state"], "ready")
                process.stdin.write('{"command":"shutdown"}\n')
                process.stdin.flush()
                remaining_stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr or remaining_stdout)
                stopped = json.loads(remaining_stdout.strip())
                self.assertEqual(stopped["type"], "smarti_core_stopped")
                self.assertEqual(stopped["state"], "stopped")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
