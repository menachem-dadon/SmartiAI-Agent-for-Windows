import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock
from pathlib import Path
from types import SimpleNamespace

from smarti.history import ChatSessionStore
from smarti.agent.execution_policy import ExecutionPolicyMixin
from smarti.run_manager import ConversationRunManager


class ConversationApprovalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "history.json")
        self.store = ChatSessionStore(self.path)
        self.core = SimpleNamespace(chat_store=self.store, settings={})
        self.manager = ConversationRunManager(self.core)
        self.events = queue.Queue()
        self.manager.subscribe(lambda event: self.events.put(event) if event["event_type"] == "approval_requested" else None)
        self.workers = []
        self.results = {}

    def tearDown(self):
        self.manager.shutdown(wait=True)
        for worker in self.workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.directory.cleanup()

    def run_pair(self):
        session = self.store.create_session(set_active=False)["id"]
        run = self.store.create_run(session, "test approvals")
        self.store.transition_run(run, "running")
        return run, session

    def ask(self, pair, title):
        def request():
            self.results[title] = self.manager.request_approval(*pair, title, "details")
        worker = threading.Thread(target=request, daemon=True)
        self.workers.append(worker)
        worker.start()
        event = self.events.get(timeout=2)
        return event["payload"]["approval_id"], worker

    def test_parallel_requests_are_durable_and_resolve_independently_across_conversations(self):
        first, other = self.run_pair(), self.run_pair()
        a, wa = self.ask(first, "a")
        b, wb = self.ask(first, "b")
        c, wc = self.ask(other, "c")
        # Reading a conversation and reconnecting the UI cannot consume requests.
        self.store.mark_session_read(first[1])
        reopened = ChatSessionStore(self.path)
        self.assertEqual({item["id"] for item in reopened.pending_approvals()}, {a, b, c})
        self.assertEqual({item["id"] for item in reopened.pending_approvals(first[1])}, {a, b})
        self.assertTrue(self.manager.resolve_approval(b, True))
        wb.join(2)
        self.assertEqual(self.results, {"b": True})
        self.assertEqual(self.store.run(first[0])["status"], "waiting_for_approval")
        self.assertEqual(self.store.run(other[0])["status"], "waiting_for_approval")
        self.assertTrue(wa.is_alive())
        self.assertTrue(wc.is_alive())
        self.assertTrue(self.manager.resolve_approval(a, False))
        wa.join(2)
        self.assertFalse(self.results["a"])
        self.assertEqual(self.store.run(first[0])["status"], "running")
        self.assertEqual([item["id"] for item in reopened.pending_approvals()], [c])
        self.assertTrue(self.manager.resolve_approval(c, True))
        wc.join(2)
        self.assertTrue(self.results["c"])
        self.assertEqual(self.store.run(other[0])["status"], "running")
        resolved = [event for event in self.store.run_events(first[0]) if event["event_type"] == "approval_resolved"]
        self.assertEqual([event["payload"]["approval_id"] for event in resolved], [b, a])
        self.assertFalse(any(event["event_type"] in {"run_status", "run_step"} for event in self.store.run_events(first[0])))

    def test_immediate_duplicate_decisions_cannot_overwrite_the_first_answer(self):
        for first_decision in (False, True):
            pair = self.run_pair()
            def resolve(event):
                if event["event_type"] != "approval_requested":
                    return
                approval = event["payload"]["approval_id"]
                self.assertTrue(self.manager.resolve_approval(approval, first_decision))
                self.assertFalse(self.manager.resolve_approval(approval, not first_decision))
            token = self.manager.subscribe(resolve)
            try:
                self.assertEqual(self.manager.request_approval(*pair, "instant", "details"), first_decision)
                self.assertEqual(self.store.run(pair[0])["status"], "running")
            finally:
                self.manager.unsubscribe(token)

    def test_cancellation_removes_only_its_own_requests_and_never_revives_the_run(self):
        first, other = self.run_pair(), self.run_pair()
        a, wa = self.ask(first, "a")
        b, wb = self.ask(first, "b")
        c, wc = self.ask(other, "c")
        self.assertTrue(self.manager.cancel(first[0]))
        wa.join(2)
        wb.join(2)
        self.assertEqual(self.results, {"a": False, "b": False})
        self.assertEqual(self.store.run(first[0])["status"], "cancelling")
        self.assertEqual([item["id"] for item in self.store.pending_approvals()], [c])
        self.assertFalse(self.manager.resolve_approval(a, True))
        self.assertFalse(self.manager.resolve_approval(b, True))
        self.assertFalse(self.manager.request_approval(*first, "too late", "details"))
        self.assertTrue(wc.is_alive())

    def test_timeout_releases_wait_without_leaving_the_run_waiting(self):
        self.core.settings["approval_wait_timeout_seconds"] = 1
        pair = self.run_pair()
        approval, worker = self.ask(pair, "timeout")
        worker.join(3)
        self.assertEqual(self.results, {"timeout": False})
        self.assertEqual(self.store.pending_approvals(), [])
        self.assertEqual(self.store.run(pair[0])["status"], "running")
        event = next(event for event in self.store.run_events(pair[0]) if event["event_type"] == "approval_resolved")
        self.assertEqual(event["payload"]["status"], "expired")
        self.assertFalse(self.manager.resolve_approval(approval, True))

    def test_shutdown_releases_all_pending_requests(self):
        a, wa = self.ask(self.run_pair(), "a")
        b, wb = self.ask(self.run_pair(), "b")
        self.manager.shutdown()
        wa.join(2)
        wb.join(2)
        self.assertEqual(self.results, {"a": False, "b": False})
        self.assertEqual(self.store.pending_approvals(), [])
        self.assertFalse(self.manager.resolve_approval(a, True))
        self.assertFalse(self.manager.resolve_approval(b, True))

    def test_permission_after_run_completion_is_rejected_without_creating_a_request(self):
        pair = self.run_pair()
        self.store.transition_run(pair[0], "completed")
        self.assertFalse(self.manager.request_approval(*pair, "late", "details"))
        self.assertEqual(self.store.pending_approvals(), [])

    def test_core_permission_adapter_does_not_emit_a_tool_or_status_report(self):
        run, session = self.run_pair()
        host = SimpleNamespace(
            _execution_context=SimpleNamespace(run_id=run, target_session_id=session),
            run_manager=self.manager, status_callback=Mock(),
            ask_user_callback=lambda *_: False,
        )
        self.assertFalse(ExecutionPolicyMixin._request_user_approval(host, "action", "details"))
        host.status_callback.assert_not_called()
        self.assertEqual(self.store.pending_approvals(), [])
        self.assertEqual(self.store.run(run)["status"], "running")

    def test_api_key_input_and_approval_keep_their_independent_waits(self):
        for key_first in (False, True):
            for resolve_key_first in (False, True):
                with self.subTest(key_first=key_first, resolve_key_first=resolve_key_first):
                    pair = self.run_pair()
                    key_ready = threading.Event()
                    token = self.manager.subscribe(lambda event: key_ready.set() if event["event_type"] == "api_key_required" else None)
                    key_worker = threading.Thread(target=lambda: self.manager.request_api_key(
                        *pair, "openai_api_key", "OpenAI", "API key", "Enter key",
                    ), daemon=True)
                    self.workers.append(key_worker)
                    try:
                        if key_first:
                            key_worker.start()
                            self.assertTrue(key_ready.wait(2))
                        approval, worker = self.ask(pair, "mixed")
                        if not key_first:
                            key_worker.start()
                            self.assertTrue(key_ready.wait(2))
                        if resolve_key_first:
                            self.assertTrue(self.manager.resolve_api_key_request(pair[0], "openai_api_key", "test-key"))
                            key_worker.join(2)
                            self.assertEqual(self.store.run(pair[0])["status"], "waiting_for_approval")
                            self.assertTrue(self.manager.resolve_approval(approval, False))
                        else:
                            self.assertTrue(self.manager.resolve_approval(approval, False))
                            worker.join(2)
                            self.assertEqual(self.store.run(pair[0])["status"], "waiting_for_input")
                            self.assertTrue(self.manager.resolve_api_key_request(pair[0], "openai_api_key", "test-key"))
                        worker.join(2)
                        key_worker.join(2)
                        self.assertEqual(self.store.run(pair[0])["status"], "running")
                    finally:
                        self.manager.resolve_api_key_request(pair[0], "openai_api_key", "test-key")
                        self.manager.unsubscribe(token)
