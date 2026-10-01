import copy
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest import mock

from smarti.agent.background_runtime import BackgroundRuntimeMixin
from smarti.agent.productivity_tools import ProductivityToolsMixin
from smarti.desktop_services import task_action
from smarti.history import ChatSessionStore
from smarti.run_manager import ConversationRunManager


class _BackgroundCore(BackgroundRuntimeMixin, ProductivityToolsMixin):
    def __init__(self, directory):
        self.chat_store = ChatSessionStore(str(Path(directory) / "history.json"))
        self.settings = {
            "background_tasks": [], "background_jobs": [],
            "api_mode": "local", "conversation_title_generation_mode": "local",
        }
        self._execution_context = threading.local()
        self._background_lock = threading.RLock()
        self._background_threads = {}
        self._background_cancel_events = {}
        self.notifications = []
        self.run_manager = ConversationRunManager(self)

    @contextmanager
    def bind_run_context(self, run_id, session_id, **kwargs):
        self._execution_context.target_session_id = session_id
        try:
            yield {}
        finally:
            del self._execution_context.target_session_id

    def send_message(self, text, **kwargs):
        return f"answer:{text}"

    def _record_run_assistant_message(self, session_id, run_id, text, response, **kwargs):
        self.chat_store.append_message("assistant", response, {"run_id": run_id}, session_id=session_id)

    def _chat_context_snapshot(self):
        return {}

    def _save_settings(self):
        self.saved_tasks = copy.deepcopy(self.settings["background_tasks"])

    def _normalize_policy_matrix(self):
        return {}

    def _truncate_tool_output(self, text):
        return str(text)

    def _emit_notification(self, kind, payload):
        self.notifications.append((kind, payload))


class BackgroundRoutingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.core = _BackgroundCore(self.directory.name)
        self.active = self.core.chat_store.active_session_metadata()["id"]

    def tearDown(self):
        self.core.run_manager.shutdown(wait=True)
        self.directory.cleanup()

    def _run(self, task, *, retry=False):
        # Capture the real scheduler thread before it removes itself on completion.
        threads = []
        start_thread = threading.Thread.start

        def start(thread):
            if thread.name.startswith("SmartiBackground-"):
                threads.append(thread)
            start_thread(thread)

        with mock.patch.object(threading.Thread, "start", start):
            if retry:
                result = self.core.retry_background_task(task["id"])
                self.assertTrue(result.startswith("SUCCESS:"), result)
            else:
                self.core._schedule_background_task_thread(task)
        self.assertEqual(len(threads), 1)
        threads[0].join(timeout=5)
        self.assertFalse(threads[0].is_alive(), "scheduler did not finish")
        self.assertEqual(task["status"], "done", task.get("last_result"))
        self.assertEqual(self.core.chat_store.active_session_metadata()["id"], self.active)
        return self.core.notifications[-1][1]["session_id"]

    def _scheduled_task(self, mode, target=None):
        task = {
            "id": "test-task", "prompt": "monitor", "repeat": "once",
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "status": "scheduled", "conversation_mode": mode,
            "target_conversation_id": target,
        }
        self.core.settings["background_tasks"] = [task]
        return task

    def test_management_creation_without_source_never_captures_active_chat(self):
        for mode in (None, "current", "dedicated", "new"):
            with self.subTest(mode=mode), mock.patch.object(self.core, "_schedule_background_task_thread"):
                payload = {"delay_minutes": 0, "prompt": "monitor"}
                if mode is not None:
                    payload["conversation_mode"] = mode
                response = task_action(self.core, "create", payload)
                task = response["items"][0]
                self.assertEqual(task["conversation_mode"], "new" if mode == "new" else "dedicated")
                self.assertIsNone(task["target_conversation_id"])

    def test_management_created_task_runs_in_its_own_chat(self):
        with mock.patch.object(self.core, "_schedule_background_task_thread"):
            task_action(self.core, "create", {"delay_minutes": 0, "prompt": "monitor", "conversation_mode": "current"})
        task = self.core.settings["background_tasks"][0]
        target = self._run(task)
        self.assertNotEqual(target, self.active)
        self.assertEqual(task["target_conversation_id"], target)
        self.assertEqual(self.core.chat_store.messages_page(self.active)["messages"], [])
        self.assertEqual(len(self.core.chat_store.messages_page(target)["messages"]), 2)

    def test_current_creation_and_edit_keep_the_run_source(self):
        source = self.core.chat_store.create_session(set_active=False)["id"]
        self.core._execution_context.target_session_id = source
        with mock.patch.object(self.core, "_schedule_background_task_thread"):
            self.core.schedule_background_task({"delay_minutes": 0, "prompt": "monitor"})
            task = self.core.settings["background_tasks"][0]
            self.assertEqual(task["conversation_mode"], "current")
            self.assertEqual(task["target_conversation_id"], source)
            self.core._execution_context.target_session_id = self.active
            task_action(self.core, "edit", {"id": task["id"], "conversation_mode": "current", "prompt": "updated"})
            del self.core._execution_context.target_session_id
            task_action(self.core, "edit", {"id": task["id"], "conversation_mode": "current"})
        self.assertEqual(task["target_conversation_id"], source)
        self.assertEqual(self._run(task), source)
        self.assertEqual(self.core.chat_store.messages_page(self.active)["messages"], [])

    def test_missing_or_deleted_source_creates_and_reuses_a_persisted_replacement(self):
        for deleted in (False, True):
            with self.subTest(deleted=deleted):
                source = None
                if deleted:
                    source = self.core.chat_store.create_session(set_active=False)["id"]
                    self.core.chat_store.delete_session(source)
                task = self._scheduled_task("current", source)
                replacement = self._run(task)
                self.assertNotEqual(replacement, self.active)
                self.assertNotEqual(replacement, source)
                self.assertEqual(task["conversation_mode"], "dedicated")
                self.assertEqual(self.core.saved_tasks[0]["target_conversation_id"], replacement)
                # Reload the saved task to verify the target survives retries.
                restored = copy.deepcopy(self.core.saved_tasks[0])
                self.core.settings["background_tasks"] = [restored]
                self.assertEqual(self._run(restored, retry=True), replacement)
                self.assertEqual(len(self.core.chat_store.messages_page(replacement)["messages"]), 4)
        self.assertEqual(self.core.chat_store.messages_page(self.active)["messages"], [])

    def test_new_mode_uses_a_different_chat_for_each_execution(self):
        task = self._scheduled_task("new")
        first = self._run(task)
        second = self._run(task, retry=True)
        self.assertNotEqual(first, second)
        self.assertNotIn(self.active, (first, second))
        self.assertIsNone(task["target_conversation_id"])

    def test_switching_to_current_without_source_keeps_a_dedicated_target(self):
        target = self.core.chat_store.create_session(set_active=False)["id"]
        task = self._scheduled_task("dedicated", target)
        with mock.patch.object(self.core, "_schedule_background_task_thread"):
            task_action(self.core, "edit", {"id": task["id"], "conversation_mode": "current"})
        self.assertEqual(task["conversation_mode"], "dedicated")
        self.assertEqual(task["target_conversation_id"], target)


if __name__ == "__main__":
    unittest.main()
