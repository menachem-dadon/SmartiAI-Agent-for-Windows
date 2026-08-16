import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from smarti.chat import ChatWindow
from smarti.history import ChatSessionStore
from smarti.local_gateway import SmartiLocalGateway
from smarti.run_manager import ConversationRunManager


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

    def _record_run_assistant_message(self, session_id, run_id, user_text, response, **kwargs):
        self.chat_store.append_message(
            "assistant",
            response,
            {"run_id": run_id},
            session_id=session_id,
        )


class ConversationRunStoreTests(unittest.TestCase):
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


class LocalGatewayTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
