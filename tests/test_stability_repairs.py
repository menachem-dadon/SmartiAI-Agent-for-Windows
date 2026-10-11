"""Fault injection for the urgent stability audit; isolated profile, no API calls."""
import copy
import json
import logging
import sqlite3
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
import urllib.error

from smarti import common
from smarti.common import SmartiCancelled, SmartiRedactingFilter
from smarti.config import DEFAULT_SETTINGS
from smarti.tool_output import ToolOutputWriter, read_tool_output
import re
from smarti.core import SmartiCore
from smarti.history import ChatSessionStore
from smarti.local_gateway import SmartiLocalGateway
from smarti.managers import SettingsManager, AgentRuntime
from smarti.run_manager import ConversationRunManager
from smarti.task_limits import TaskCancellation
from smarti.api_errors import ApiErrorAnalysis, ApiRequestError
from tests.test_conversation_runs import _FakeCore
from tests import test_conversation_runs as run_tests
from tests import test_background_routing as background_tests


class StabilityRepairTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.core = SmartiCore.__new__(SmartiCore)
        self.core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.core.mode = "local"
        self.core._execution_context = threading.local()
        self.core.cancel_event = threading.Event()
        self.core._foreground_cancel_event = None
        self.core._active_process_lock = threading.RLock()
        self.core._active_processes = set()
        self.core._active_processes_by_run = {}
        self.core._subprocess_env = lambda env=None: dict(os.environ, **(env or {}))
        self.core.chat_store = ChatSessionStore(str(self.root / "history.json"))
        self.usage_patch = mock.patch("smarti.agent.model_context.USAGE_FILE", str(self.root / "usage.json"))
        self.usage_patch.start()
        self.addCleanup(self.usage_patch.stop)

    def test_vault_failure_encrypts_instead_of_writing_plaintext(self):
        secret = "audit-secret-for-vault-failure"
        path = self.root / "settings.json"
        self.core.settings["openai_api_key"] = secret
        self.core.settings_manager = SettingsManager(str(path), DEFAULT_SETTINGS)
        self.core._sync_ssl_compat_env = mock.Mock()
        vault = mock.Mock()
        vault.set_password.side_effect = RuntimeError(secret)
        with mock.patch("smarti.agent.model_context.get_keyring_module", return_value=vault), \
             mock.patch("smarti.agent.model_context.dpapi_protect_text", return_value=common.SECRET_PREFIX + "ciphertext"):
            self.core._save_settings()
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn(secret, path.read_text(encoding="utf-8"))
        self.assertTrue(saved["openai_api_key"].startswith(common.SECRET_PREFIX))
        self.assertEqual(self.core.settings["openai_api_key"], secret)

    def test_vault_and_encryption_failure_preserve_previous_settings(self):
        path = self.root / "settings.json"
        path.write_text('{"previous":true}', encoding="utf-8")
        self.core.settings["openai_api_key"] = "audit-secret-no-storage"
        self.core.settings_manager = SettingsManager(str(path), DEFAULT_SETTINGS)
        self.core._sync_ssl_compat_env = mock.Mock()
        vault = mock.Mock()
        vault.set_password.side_effect = RuntimeError("vault unavailable")
        with mock.patch("smarti.agent.model_context.get_keyring_module", return_value=vault), \
             mock.patch("smarti.agent.model_context.dpapi_protect_text", return_value=None):
            with self.assertRaises(RuntimeError):
                self.core._save_settings()
        self.assertEqual(json.loads(path.read_text()), {"previous": True})

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI")
    def test_vault_failure_round_trips_real_windows_encryption(self):
        secret = "audit-only-real-dpapi-secret"
        path = self.root / "encrypted-settings.json"
        self.core.settings["openai_api_key"] = secret
        self.core.settings_manager = SettingsManager(str(path), DEFAULT_SETTINGS)
        self.core._sync_ssl_compat_env = mock.Mock()
        vault = mock.Mock()
        vault.set_password.side_effect = RuntimeError("backend unavailable")
        with mock.patch("smarti.agent.model_context.get_keyring_module", return_value=vault):
            self.core._save_settings()
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertNotIn(secret, path.read_text(encoding="utf-8"))
        self.assertEqual(common.dpapi_unprotect_text(saved["openai_api_key"]), secret)

    def test_events_context_messages_and_tracebacks_redact_credentials(self):
        secret = "audit-secret-for-all-persistence"
        settings = {"openai_api_key": secret, "privacy_redact_logs": False}
        with mock.patch.dict(common._CURRENT_SETTINGS_REF, {"settings": settings}):
            session = self.core.chat_store.active_session()["id"]
            run = self.core.chat_store.create_run(session, secret)
            self.core.chat_store.append_message("assistant", secret, {"password": "unknown-credential"}, session_id=session)
            self.core.chat_store.append_run_event(run, "run_step", {"value": {"text": secret}})
            self.core.chat_store.update_context({"result": secret}, session)
            with self.core.chat_store._connect() as db:
                dumped = "\n".join(db.iterdump())
            self.assertNotIn(secret, dumped)
            self.assertNotIn("unknown-credential", dumped)
            try:
                raise RuntimeError(secret)
            except RuntimeError:
                record = logging.LogRecord("audit", logging.ERROR, __file__, 1, secret, (), sys.exc_info())
            SmartiRedactingFilter().filter(record)
            output = logging.Formatter().format(record)
            self.assertNotIn(secret, output)
            self.assertIn("RuntimeError", output)

    def test_receipt_failure_rolls_back_run_and_worker_then_retry_is_unique(self):
        core = _FakeCore(self.root / "gateway.json")
        core.mode = "local"
        core.run_manager = ConversationRunManager(core)
        gateway = SmartiLocalGateway(core, "test-token", port=0)
        self.assertTrue(gateway.start())
        original = core.chat_store.save_idempotency_response
        calls = 0
        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("receipt write failed")
            return original(*args, **kwargs)
        try:
            session = core.chat_store.active_session()["id"]
            path = f"/v2/conversations/{session}/runs"
            options = dict(method="POST", payload={"text": "one request"}, headers={"Idempotency-Key": "durable-command"})
            with mock.patch.object(core.chat_store, "save_idempotency_response", side_effect=fail_once):
                with self.assertRaises(urllib.error.HTTPError) as failed:
                    run_tests.LocalGatewayTests._request(gateway, path, **options)
                self.assertEqual(failed.exception.code, 500)
                self.assertEqual(calls, 1)
                self.assertEqual(core.started, [])
                self.assertEqual(core.chat_store.messages(session), [])
                accepted = run_tests.LocalGatewayTests._request(gateway, path, **options)[2]["data"]
            replay = run_tests.LocalGatewayTests._request(gateway, path, **options)[2]["data"]
            self.assertEqual(accepted["run_id"], replay["run_id"])
            self.assertTrue(core.run_manager.handle(accepted["run_id"]).done_event.wait(2))
            self.assertEqual(len(core.started), 1)
            with self.assertRaises(urllib.error.HTTPError) as mismatch:
                run_tests.LocalGatewayTests._request(gateway, path, method="POST", payload={"text": "changed"}, headers=options["headers"])
            self.assertEqual(mismatch.exception.code, 409)
            with self.assertRaises(urllib.error.HTTPError) as missing:
                run_tests.LocalGatewayTests._request(gateway, path, method="POST", payload={"text": "missing"}, headers={"Idempotency-Key": ""})
            self.assertEqual(missing.exception.code, 400)
        finally:
            gateway.stop()
            core.run_manager.shutdown(wait=True)

    def test_checkpoints_are_scoped_and_transfer_atomically_on_resume(self):
        store = self.core.chat_store
        a = store.create_session(set_active=False)["id"]
        b = store.create_session(set_active=False)["id"]
        first, foreign = store.create_run(a), store.create_run(b)
        store.save_run_checkpoint(first, {"run_id": first, "task_id": "task-a", "current_messages": [{"role": "user", "content": "original instruction"}, {"role": "tool", "content": "completed result"}]})
        store.save_run_checkpoint(foreign, {"run_id": foreign, "task_id": "task-b", "current_messages": []})
        store.transition_run(first, "failed")
        store.transition_run(foreign, "failed")
        next_run = store.create_run(a, "continue")
        self.core._execution_context.run_id = next_run
        self.core._execution_context.target_session_id = a
        checkpoint = self.core._load_task_checkpoint(resume=True)
        self.assertEqual(checkpoint["run_id"], first)
        self.assertIn("completed result", json.dumps(checkpoint))
        checkpoint["run_id"] = next_run
        self.assertTrue(self.core._write_task_checkpoint(checkpoint))
        self.assertIsNone(store.load_run_checkpoint(run_id=first))
        self.assertIsNotNone(store.load_run_checkpoint(run_id=foreign))
        self.assertIsNone(store.load_run_checkpoint(session_id=a, task_id="task-b"))
        reopened = ChatSessionStore(str(self.root / "history.json"))
        self.assertEqual(reopened.load_run_checkpoint(run_id=next_run)["current_messages"], checkpoint["current_messages"])

    def test_sqlite_upgrade_backs_up_committed_wal_and_preserves_messages(self):
        store = self.core.chat_store
        session = store.active_session()["id"]
        store.append_message("user", "preserved migration message", session_id=session)
        with store._connect() as db:
            db.execute("UPDATE store_meta SET value='3' WHERE key='schema_version'")
            db.execute("DROP TABLE run_checkpoints")
            db.execute("ALTER TABLE idempotency_keys DROP COLUMN request_hash")
        reopened = ChatSessionStore(str(self.root / "history.json"))
        backups = list(self.root.glob("history.sqlite3.backup-v3-*"))
        self.assertEqual(len(backups), 1)
        from contextlib import closing
        with closing(sqlite3.connect(backups[0])) as saved:
            self.assertEqual(saved.execute("SELECT value FROM store_meta WHERE key='schema_version'").fetchone()[0], "3")
            self.assertEqual(saved.execute("SELECT content FROM messages").fetchone()[0], "preserved migration message")
        self.assertIn("preserved migration message", json.dumps(reopened.messages(session)))
        with reopened._connect() as db:
            self.assertEqual(db.execute("SELECT value FROM store_meta WHERE key='schema_version'").fetchone()[0], "5")

    def _managed_resume_fixture(self, phase="network_paused", *, elapsed_seconds=0, background=False):
        core = self.core
        core._execution_context.run_values = {}
        for name in ("status_callback", "step_callback", "print_callback", "ask_user_callback", "stream_callback", "api_key_callback", "agent_runtime", "memory_manager"):
            setattr(core, name, None)
        core.settings.update(prevent_sleep_during_active_task=False, api_mode="gemini")
        core.system_prompt = "Complete the original instruction."
        core.capture_run_model_snapshot = mock.Mock(return_value={"mode": "local"})
        core._ensure_active_provider_api_key = lambda: True
        core._conversation_lock = lambda _session: threading.RLock()
        core._compact_current_messages_if_needed = lambda *args, **kwargs: False
        core._compact_conversation_history = mock.Mock()
        core._record_context_token_usage = mock.Mock()
        core._handle_api_request_with_retry = mock.Mock(return_value=("Completed original task.", {}))
        core.execute_tool = mock.Mock(side_effect=AssertionError("A completed tool must not run twice"))
        session = core.chat_store.active_session()["id"]
        first = core.chat_store.create_run(session, "original instruction")
        checkpoint = {
            "run_id": first, "task_id": "background-a" if background else "original-task", "mode": "local", "current_model": "audit-model",
            "user_text": "original instruction", "history_user_text": "original instruction", "system_prompt": core.system_prompt,
            "phase": phase, "iteration": 1, "elapsed_seconds": elapsed_seconds,
            "current_messages": [{"role": "user", "content": "original instruction"}, {"role": "assistant", "content": "Tool completed"}, {"role": "user", "content": "completed tool result"}],
            "task_state": {"checkpoint_mutating_tools": phase == "tool_execution"}, "context": {},
        }
        core.chat_store.save_run_checkpoint(first, checkpoint)
        core.chat_store.transition_run(first, "failed")
        resumed = core.chat_store.create_run(session, "continue")
        core._execution_context.run_id = resumed
        core._execution_context.target_session_id = session
        if background:
            core._execution_context.current_task_id = "background-a"
        return session, first, resumed

    def test_managed_resume_keeps_instruction_and_result_without_replaying_tool(self):
        session, first, resumed = self._managed_resume_fixture()
        response = self.core.send_message("continue", session_id=session, run_id=resumed, persist_turn=False)
        self.assertEqual(response, "Completed original task.")
        submitted = json.dumps(self.core._handle_api_request_with_retry.call_args.args[1])
        self.assertIn("original instruction", submitted)
        self.assertIn("completed tool result", submitted)
        self.core.execute_tool.assert_not_called()
        self.assertEqual(self.core.settings["api_mode"], "gemini")
        self.assertIsNone(self.core.chat_store.load_run_checkpoint(run_id=first))
        self.assertIsNone(self.core.chat_store.load_run_checkpoint(run_id=resumed))

    def test_resume_refreshes_only_live_system_slot_and_preserves_saved_tool_content(self):
        session, first, resumed = self._managed_resume_fixture()
        checkpoint = self.core.chat_store.load_run_checkpoint(run_id=first)
        checkpoint["system_prompt"] = "הנחיית מערכת ישנה"
        checkpoint["current_messages"].insert(0, {"role": "system", "content": checkpoint["system_prompt"]})
        checkpoint["current_messages"][-1]["content"] = "בוצע בעבר"
        self.core.chat_store.save_run_checkpoint(first, checkpoint)
        old_messages = copy.deepcopy(self.core.chat_store.messages(session))
        self.core._load_system_prompt = mock.Mock(return_value="Current English system policy.")
        self.assertEqual(self.core.send_message("continue", session_id=session, run_id=resumed, persist_turn=False), "Completed original task.")
        sent = self.core._handle_api_request_with_retry.call_args.args[1]
        self.assertEqual(sent[0], {"role": "system", "content": "Current English system policy."})
        self.assertIn("בוצע בעבר", json.dumps(sent, ensure_ascii=False))
        self.assertNotIn("הנחיית מערכת ישנה", json.dumps(sent, ensure_ascii=False))
        self.assertEqual(self.core.chat_store.messages(session), old_messages)
        self.core.execute_tool.assert_not_called()

    def test_background_run_resumes_only_its_own_task(self):
        session, first, resumed = self._managed_resume_fixture(background=True)
        response = self.core.send_message("scheduled prompt", session_id=session, run_id=resumed, is_background_task=True, persist_turn=False)
        self.assertEqual(response, "Completed original task.")
        self.assertIn("completed tool result", json.dumps(self.core._handle_api_request_with_retry.call_args.args[1]))

    def test_unknown_mutation_is_held_for_review_instead_of_replayed(self):
        session, first, resumed = self._managed_resume_fixture("tool_execution")
        response = self.core.send_message("continue", session_id=session, run_id=resumed, persist_turn=False)
        self.assertTrue(response.startswith("ERROR_USER"), response)
        self.core.execute_tool.assert_not_called()
        self.core._handle_api_request_with_retry.assert_not_called()
        self.assertIsNotNone(self.core.chat_store.load_run_checkpoint(run_id=first))

    def test_network_loss_after_tool_result_resumes_saved_loop_without_duplicate_execution(self):
        session, old, first = self._managed_resume_fixture()
        core = self.core
        core.chat_store.clear_run_checkpoint(old)
        core.agent_runtime = AgentRuntime(core)
        core._load_system_prompt = lambda *args, **kwargs: "Complete the task."
        core.refresh_extension_catalogs_if_changed = lambda **kwargs: None
        call = json.dumps({"method": "tools/call", "params": {"name": "search_tools", "arguments": {"query": "files"}}})
        offline = ApiRequestError(ApiErrorAnalysis(category="network", reason="connection_error", user_message="network unavailable"))
        core._handle_api_request_with_retry = mock.Mock(side_effect=[(call, {}), offline])
        core._execute_tool_call_batch = mock.Mock(return_value=[{"action": "search_tools", "arguments": {}, "output": "completed once result", "feedback": "completed once result"}])
        response = core.send_message("original instruction", session_id=session, run_id=first, persist_turn=False)
        self.assertTrue(response.startswith("ERROR_USER"), response)
        checkpoint = core.chat_store.load_run_checkpoint(run_id=first)
        self.assertIsNotNone(checkpoint)
        self.assertIn("completed once result", json.dumps(checkpoint))
        core.chat_store.transition_run(first, "failed")
        resumed = core.chat_store.create_run(session, "continue")
        core._execution_context.run_id = resumed
        core._handle_api_request_with_retry = mock.Mock(return_value=("Completed with saved result.", {}))
        response = core.send_message("continue", session_id=session, run_id=resumed, persist_turn=False)
        self.assertEqual(response, "Completed with saved result.")
        core._execute_tool_call_batch.assert_called_once()
        self.assertIn("completed once result", json.dumps(core._handle_api_request_with_retry.call_args.args[1]))

    def test_resume_does_not_reset_total_time_budget(self):
        session, first, resumed = self._managed_resume_fixture(elapsed_seconds=5)
        self.core.settings["max_total_task_seconds"] = 1
        response = self.core.send_message("continue", session_id=session, run_id=resumed, persist_turn=False)
        self.assertTrue(response.startswith("ERROR_USER"), response)
        self.core._handle_api_request_with_retry.assert_not_called()

    def test_task_receipt_failure_and_restart_do_not_create_duplicate_task(self):
        core = background_tests._BackgroundCore(self.root)
        core._schedule_background_task_thread = mock.Mock()
        gateway = SmartiLocalGateway(core, "test-token", port=0)
        self.assertTrue(gateway.start())
        self.addCleanup(core.run_manager.shutdown, wait=True)
        self.addCleanup(gateway.stop)
        options = dict(method="POST", payload={"action": "create", "prompt": "one scheduled task", "delay_minutes": 10}, headers={"Idempotency-Key": "task-intent"})
        with mock.patch.object(core.chat_store, "save_idempotency_response", side_effect=RuntimeError("receipt failed")):
            with self.assertRaises(urllib.error.HTTPError) as failed:
                run_tests.LocalGatewayTests._request(gateway, "/v2/management/tasks", **options)
            self.assertEqual(failed.exception.code, 500)
        self.assertEqual(len(core.saved_tasks), 1)
        core.settings["background_tasks"] = copy.deepcopy(core.saved_tasks)  # Reload durable settings.
        core.settings["background_jobs"] = core.settings["background_tasks"]
        replay = run_tests.LocalGatewayTests._request(gateway, "/v2/management/tasks", **options)
        self.assertEqual(replay[0], 200)
        self.assertEqual(len(core.settings["background_tasks"]), 1)
        core._schedule_background_task_thread.assert_called_once()
        with mock.patch.object(core, "_save_settings", side_effect=RuntimeError("settings failed")):
            self.assertTrue(core.schedule_background_task({"prompt": "different task"}, request_key="different").startswith("ERROR:"))
        self.assertEqual(len(core.settings["background_tasks"]), 1)

    def test_parallel_requests_do_not_reserve_or_reduce_output_before_observed_limit(self):
        self.core.settings["budgets"]["daily_token_budget"] = 30
        messages = [{"role": "user", "content": "large prompt " * 10000}]
        def check():
            return self.core._prepare_messages_for_budget("audit-model", messages, "local")
        with ThreadPoolExecutor(2) as executor:
            self.assertTrue(all(value is messages for value in executor.map(lambda _: check(), range(2))))
        self.core._log_usage("audit-model", {"request_id": "actual", "total": 40, "_budget_eligible": True, "estimated_cost_usd": 0})
        with self.assertRaisesRegex(RuntimeError, "DAILY_TOKEN_BUDGET_EXCEEDED"):
            check()
        self.assertFalse((self.root / "usage.json.reservations.json").exists())

    def test_unknown_prices_are_excluded_and_known_cost_blocks_only_after_receipt(self):
        self.core.settings["budgets"].update(daily_cost_budget_usd=0.02, daily_token_budget=10)
        with mock.patch("smarti.agent.budgets.pricing_cache", return_value={}), mock.patch("smarti.agent.budgets.bundled_pricing", return_value={}):
            self.core._check_request_budget("unpriced-audit", "openai")
            self.core._log_usage("unpriced-audit", {"request_id": "unknown", "total": 10000, "_budget_eligible": False})
            self.assertEqual(self.core._daily_budget_usage(), (0, 0))
            rates = {"input": 0.000001, "output": 0.0001}
            with mock.patch("smarti.agent.budgets.model_rates", return_value=rates):
                self.core._check_request_budget("priced-audit", "openai")
                self.core._log_usage("priced-audit", {"request_id": "known", "total": 5, "_budget_eligible": True, "estimated_cost_usd": 0.025})
                with self.assertRaisesRegex(RuntimeError, "DAILY_COST_BUDGET_EXCEEDED"):
                    self.core._check_request_budget("priced-audit", "openai")
            # Exhausting the eligible budget still does not block an unknown model.
            self.core._check_request_budget("unpriced-audit", "openai")

    def test_usage_receipt_survives_restart_without_double_counting(self):
        usage = {"request_id": "same-observed-call", "prompt": 10, "completion": 5, "total": 15}
        self.core._log_usage("audit-model", usage)
        self.core._log_usage("audit-model", usage)
        data = json.loads((self.root / "usage.json").read_text())
        self.assertEqual(next(iter(data.values()))["audit-model"]["total"], 15)

    def test_codex_and_unbounded_routes_are_free_of_daily_budget_counters(self):
        self.core.settings["budgets"].update(daily_token_budget=1, daily_cost_budget_usd=0.001)
        self.core._log_usage("audit-model", {"total": 100, "estimated_cost_usd": 1, "_budget_eligible": True})
        self.core._check_request_budget("codex-model", "openai_codex_signin")
        self.assertFalse(self.core._request_counts_toward_budget("codex-model", "openai_codex_signin"))
        self.core._budget_unbounded_routes = {("openai", "unbounded-model")}
        self.core._check_request_budget("unbounded-model", "openai")
        self.assertFalse(self.core._request_counts_toward_budget("unbounded-model", "openai"))

    def test_budget_receipt_keeps_route_eligibility_with_same_model_name(self):
        for identifier, eligible, amount in [("paid", True, 0.01), ("subscription", False, 0), ("paid", True, 0.01)]:
            self.core._log_usage("shared-model", {"request_id": identifier, "total": 30, "_budget_eligible": eligible, "estimated_cost_usd": amount})
        self.assertEqual(self.core._daily_budget_usage(), (30, 0.01))
        data = json.loads((self.root / "usage.json").read_text())
        self.assertEqual(next(iter(data.values()))["shared-model"]["total"], 60)

    def test_old_unknown_usage_and_reservations_do_not_block_known_model(self):
        (self.root / "usage.json").write_text(json.dumps({time.strftime("%Y-%m-%d"): {"unpriced-old": {"total": 100000}}}))
        (self.root / "usage.json.reservations.json").write_text('{"old":{"tokens":999999999,"cost":999999}}')
        self.core.settings["budgets"].update(daily_token_budget=1, daily_cost_budget_usd=0.001)
        with mock.patch("smarti.agent.budgets.model_rates", side_effect=lambda name, *_: {"input": 1, "output": 1} if name == "known" else None):
            self.core._check_request_budget("known", "openai")

    def test_default_concurrency_is_unlimited_and_zero_releases_queued_work(self):
        core = _FakeCore(self.root / "unlimited.json")
        core.settings["max_concurrent_conversation_runs"] = 1
        manager = ConversationRunManager(core)
        self.addCleanup(manager.shutdown, wait=True)
        handles = [manager.submit(core.chat_store.create_session(set_active=False)["id"], "wait-work") for n in range(6)]
        self.assertEqual(len(manager._active_by_session), 1)
        core.settings["max_concurrent_conversation_runs"] = ""
        manager.refresh_limits()
        self.assertEqual(manager.max_concurrent, 0)
        self.assertEqual(len(manager._active_by_session), 6)
        core.release.set()
        for handle in handles:
            handle.wait(5)
            self.assertEqual(handle.status, "completed")
        self.assertEqual(DEFAULT_SETTINGS["max_concurrent_conversation_runs"], 0)

    def test_retained_output_survives_restart_and_is_scoped_and_encrypted(self):
        core = self.core
        session = core.chat_store.active_session()["id"]
        other = core.chat_store.create_session(set_active=False)["id"]
        writer = ToolOutputWriter(core.chat_store, session, core.settings)
        original = "Hebrew \u05e9\u05dc\u05d5\u05dd\n" * 5000 + "LAST_RESULT"
        writer.write(original)
        reopened = ChatSessionStore(str(self.root / "history.json"))
        restored, offset = [], 0
        while True:
            page = read_tool_output(reopened, session, writer.output_id, offset, 1000, core.settings)
            header, body = page.split("\n", 1)
            restored.append(body)
            following = re.search(r"next_offset=(\w+)", header)[1]
            if following == "end": break
            self.assertGreater(int(following), offset)
            offset = int(following)
        self.assertEqual("".join(restored), original)
        self.assertIn("ERROR", read_tool_output(reopened, other, writer.output_id, 0, 1000, core.settings))
        self.assertIn("ERROR", core.read_tool_output({"output_id": "../outside"}))
        with reopened._connect() as db:
            self.assertTrue(all(row[0].decode("ascii").startswith(common.SECRET_PREFIX) for row in db.execute("SELECT encrypted_text FROM tool_output_chunks")))
        self.assertNotIn(b"LAST_RESULT", Path(reopened.path).read_bytes())
        core.chat_store.delete_session(session)
        self.assertIn("ERROR", read_tool_output(reopened, session, writer.output_id, 0, 1000, core.settings))

    def test_retained_output_redacts_credentials_across_capture_and_page_boundaries(self):
        secret = "boundary-secret-not-for-model"
        self.core.settings["openai_api_key"] = secret
        session = self.core.chat_store.active_session()["id"]
        writer = ToolOutputWriter(self.core.chat_store, session, self.core.settings)
        writer.write("x" * 990 + secret[:10])
        writer.write(secret[10:] + "TAIL")
        first = read_tool_output(self.core.chat_store, session, writer.output_id, 0, 1000, self.core.settings)
        second = read_tool_output(self.core.chat_store, session, writer.output_id, 1000, 1000, self.core.settings)
        self.assertNotIn(secret, first + second)
        self.assertNotIn(secret[:10], first)
        self.assertIn("TAIL", second)

    def test_short_secret_does_not_corrupt_encrypted_output(self):
        self.core.settings["openai_api_key"] = "AQAA"
        common.redact_secret_values("", self.core.settings)
        session = self.core.chat_store.active_session()["id"]
        writer = ToolOutputWriter(self.core.chat_store, session, self.core.settings)
        writer.write("complete retained result")
        self.assertIn("complete retained result", self.core.read_tool_output({"output_id": writer.output_id}))

    def test_tool_context_preserves_retrieval_handle_and_error_status(self):
        self.core.settings["max_tool_output_chars"] = 1000
        self.core.tool_context_transcript = []
        output = self.core._truncate_tool_output("ERROR: " + "x" * 3000 + "IMPORTANT_END")
        output_id = re.search(r"output_id=([a-f0-9]{32})", output)[1]
        self.assertTrue(output.startswith("ERROR:"))
        self.core._record_tool_context_event("run_mcp", {}, "error", output)
        self.assertIn(output_id, self.core.tool_context_transcript[-1]["output"])
        self.assertIn("IMPORTANT_END", self.core.read_tool_output({"output_id": output_id, "offset": 2900}))

    def test_deadline_releases_blocked_model_wait_and_caps_transport(self):
        event = TaskCancellation(threading.Event(), 0.1)
        self.addCleanup(event.close)
        self.core._execution_context.cancel_event = event
        self.core._execution_context.task_deadline = event.deadline
        self.assertLessEqual(self.core._provider_transport_timeout("local")[1], 0.1)
        started = time.monotonic()
        with self.assertRaisesRegex(SmartiCancelled, "TASK_DEADLINE"):
            self.core._run_cancelable_callable(lambda: time.sleep(0.4), poll_interval=0.01)
        self.assertLess(time.monotonic() - started, 0.3)

    def test_internal_json_and_binary_outputs_are_not_damaged_by_model_preview_limits(self):
        self.core.settings["max_tool_output_chars"] = 1000
        result = self.core._run_cancelable_subprocess(
            [sys.executable, "-c", "import json; print(json.dumps({'data':'x'*10000}))"],
            timeout=10, preserve_output=True,
        )
        self.assertEqual(len(json.loads(result.stdout)["data"]), 10000)
        binary = self.core._run_cancelable_subprocess(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(bytes(range(256))*100)"],
            timeout=10, text=False,
        )
        self.assertEqual(binary.stdout, bytes(range(256))*100)

    def test_public_retained_output_reader_honors_policy_and_disable_switch(self):
        self.core.settings["policy_matrix"]["file_read"] = "deny"
        denied, _ = self.core.execute_tool("read_tool_output", {"output_id": "a"*32})
        self.assertIn("denied by policy", denied)
        self.core.settings["tools_config"]["read_tool_output"] = False
        disabled, _ = self.core.execute_tool("read_tool_output", {"output_id": "a"*32})
        self.assertIn("disabled", disabled)

    def test_unbounded_route_exclusion_survives_usage_reload(self):
        self.core._log_usage("uncapped", {"request_id": "uncapped-receipt", "total": 100, "_budget_eligible": False, "_budget_unbounded_provider": "openai"})
        self.core.settings["budgets"]["daily_token_budget"] = 1
        with mock.patch("smarti.agent.budgets.model_rates", return_value={"input": 1, "output": 1}):
            self.assertFalse(self.core._request_counts_toward_budget("uncapped", "openai"))
            self.core._check_request_budget("uncapped", "openai")

    def test_deadline_releases_approval_and_missing_key_waits(self):
        core = _FakeCore(self.root / "waits.json")
        core._execution_context = threading.local()
        manager = ConversationRunManager(core)
        self.addCleanup(manager.shutdown, wait=True)
        session = core.chat_store.active_session()["id"]
        run = core.chat_store.create_run(session)
        core.chat_store.transition_run(run, "running")
        for operation in ("approval", "key"):
            event = TaskCancellation(threading.Event(), 0.05)
            core._execution_context.cancel_event = event
            started = time.monotonic()
            try:
                if operation == "approval":
                    self.assertFalse(manager.request_approval(run, session, "approval", "details"))
                    self.assertEqual(core.chat_store.pending_approvals(), [])
                else:
                    self.assertEqual(manager.request_api_key(run, session, "openai_api_key", "OpenAI", "key", "missing"), "")
                self.assertLess(time.monotonic() - started, 0.7)
            finally:
                event.close()

    def test_subprocess_drains_large_output_with_bounded_capture_and_preserves_input(self):
        self.core.settings["max_tool_output_chars"] = 1000
        result = self.core._run_cancelable_subprocess(
            [sys.executable, "-c", "import sys; value=sys.stdin.read(); print(value); sys.stdout.write('x'*200000); sys.stderr.write('y'*200000)"],
            input="INPUT_OK", timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("INPUT_OK", result.stdout)
        self.assertIn("TRUNCATED", result.stdout)
        self.assertIn("TRUNCATED", result.stderr)
        self.assertLess(len(result.stdout), 1200)
        self.assertLess(len(result.stderr), 1200)
        stdout_id = re.search(r"output_id=([a-f0-9]{32})", result.stdout)[1]
        stderr_id = re.search(r"output_id=([a-f0-9]{32})", result.stderr)[1]
        self.assertIn("x" * 100, self.core.read_tool_output({"output_id": stdout_id, "offset": 199000}))
        self.assertIn("y" * 100, self.core.read_tool_output({"output_id": stderr_id, "offset": 199000}))


if __name__ == "__main__":
    unittest.main()
