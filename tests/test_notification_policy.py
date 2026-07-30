import copy
import os
import tempfile
import threading
import unittest
from unittest import mock

from smarti.agent.execution_policy import ExecutionPolicyMixin
from smarti.agent.productivity_tools import ProductivityToolsMixin
from smarti.agent.tool_calls import ToolCallMixin
from smarti.common import DEFAULT_POLICY_MATRIX


class _AuditRecorder:
    def __init__(self):
        self.records = []

    def record(self, event, payload=None, settings=None):
        self.records.append((event, dict(payload or {})))


class _NotificationCore(ExecutionPolicyMixin, ToolCallMixin, ProductivityToolsMixin):
    def __init__(self, *, approval=True):
        self.settings = {
            "permission_level": 2,
            "policy_matrix": copy.deepcopy(DEFAULT_POLICY_MATRIX),
            "audit_log_enabled": True,
            "background_tasks": [],
            "background_jobs": [],
        }
        self.policy_engine = None
        self.audit_logger = _AuditRecorder()
        self._execution_context = threading.local()
        self.status_callback = None
        self.approval_requests = []
        self.ask_user_callback = self._approve if approval is not None else None
        self._approval_result = approval
        self.emitted_notifications = []
        self.opened_uris = []
        self.scheduled_threads = []
        self.settings_save_count = 0
        self.background_scheduler = None
        self._background_cancel_events = {}
        self._background_threads = {}

    def _approve(self, title, details, risk):
        self.approval_requests.append((title, details, risk))
        return bool(self._approval_result)

    def _emit_notification(self, kind, payload=None):
        self.emitted_notifications.append((kind, dict(payload or {})))
        return True

    def _save_settings(self):
        self.settings_save_count += 1

    def _schedule_background_task_thread(self, task):
        self.scheduled_threads.append(task["id"])

    def _get_background_task(self, task_id):
        return next(
            (task for task in self.settings.get("background_tasks", []) if task.get("id") == task_id),
            None,
        )

    def _open_windows_uri(self, *uris):
        self.opened_uris.append(tuple(uris))
        return f"SUCCESS: opened {uris[0]}"

    def add_reminder(self, reminder_id="rem-1"):
        task = {
            "id": reminder_id,
            "kind": "reminder",
            "title": "בדיקה",
            "message": "להתקשר",
            "prompt": "להתקשר",
            "run_at": "2026-08-01T10:00:00",
            "repeat": "once",
            "status": "scheduled",
            "history": [],
        }
        self.settings["background_tasks"].append(task)
        self.settings["background_jobs"] = self.settings["background_tasks"]
        return task


class NotificationManagerPolicyTests(unittest.TestCase):
    ACTION_CASES = (
        ("send_toast", "notification_send", {"action": "send_toast", "title": "כותרת", "body": "תוכן"}),
        (
            "schedule_reminder",
            "background_task",
            {"action": "schedule_reminder", "message": "להתקשר", "delay_minutes": 5},
        ),
        ("cancel_reminder", "background_task_cancel", {"action": "cancel_reminder", "id": "rem-1"}),
        (
            "create_calendar_event",
            "calendar_write",
            {
                "action": "create_calendar_event",
                "title": "פגישה",
                "start": "2026-08-01T10:00:00",
                "open": False,
            },
        ),
        ("open_windows_app", "app_open", {"action": "open_windows_app", "target": "calendar"}),
        (
            "open_windows_settings",
            "settings_open",
            {"action": "open_windows_app", "target": "notification_settings"},
        ),
    )

    def _invoke_case(self, core, case_name, args):
        if case_name == "cancel_reminder":
            core.add_reminder()
        if case_name == "create_calendar_event":
            writer = mock.Mock(return_value="SUCCESS: calendar")
            core._write_calendar_event_file = writer
        result = core.notification_manager(args)
        return result

    def test_each_mutating_action_honors_allow_ask_and_deny(self):
        for case_name, capability, args in self.ACTION_CASES:
            for decision in ("allow", "ask", "deny"):
                with self.subTest(action=case_name, decision=decision):
                    core = _NotificationCore(approval=True)
                    core.settings["policy_matrix"][capability] = decision
                    result = self._invoke_case(core, case_name, copy.deepcopy(args))

                    if decision == "deny":
                        self.assertTrue(result.startswith("ERROR:"), result)
                        self.assertEqual(core.approval_requests, [])
                    else:
                        self.assertTrue(result.startswith("SUCCESS:"), result)
                        self.assertEqual(len(core.approval_requests), 1 if decision == "ask" else 0)

                    policy_records = [
                        payload
                        for event, payload in core.audit_logger.records
                        if event == "policy_decision" and payload.get("capability") == capability
                    ]
                    self.assertEqual(len(policy_records), 1)
                    self.assertEqual(policy_records[0]["manager"], "notification_manager")
                    expected_sub_action = "open_windows_app" if case_name == "open_windows_settings" else case_name
                    self.assertEqual(policy_records[0]["sub_action"], expected_sub_action)
                    self.assertEqual(
                        policy_records[0]["outcome"],
                        "denied_policy" if decision == "deny" else "allowed",
                    )

    def test_denied_actions_have_no_side_effect(self):
        cases = (
            ("notification_send", {"action": "send_toast", "body": "בדיקה"}),
            ("background_task", {"action": "schedule_reminder", "message": "בדיקה", "delay_minutes": 1}),
            ("app_open", {"action": "open_windows_app", "target": "clock"}),
            ("settings_open", {"action": "open_windows_app", "target": "focus_settings"}),
        )
        for capability, args in cases:
            with self.subTest(capability=capability):
                core = _NotificationCore()
                core.settings["policy_matrix"][capability] = "deny"
                before_tasks = copy.deepcopy(core.settings["background_tasks"])
                result = core.notification_manager(args)
                self.assertTrue(result.startswith("ERROR:"), result)
                self.assertEqual(core.emitted_notifications, [])
                self.assertEqual(core.opened_uris, [])
                self.assertEqual(core.scheduled_threads, [])
                self.assertEqual(core.settings["background_tasks"], before_tasks)

        core = _NotificationCore()
        task = core.add_reminder()
        core.settings["policy_matrix"]["background_task_cancel"] = "deny"
        result = core.notification_manager({"action": "cancel_reminder", "id": task["id"]})
        self.assertTrue(result.startswith("ERROR:"), result)
        self.assertEqual(task["status"], "scheduled")
        self.assertEqual(core.settings_save_count, 0)

    def test_list_is_a_safe_read_without_an_approval_prompt(self):
        core = _NotificationCore(approval=False)
        core.add_reminder()
        core.settings["policy_matrix"] = {
            capability: "ask" for capability in DEFAULT_POLICY_MATRIX
        }
        result = core.notification_manager({"action": "list_reminders"})
        self.assertIn("rem-1", result)
        self.assertEqual(core.approval_requests, [])
        policy_records = [
            payload for event, payload in core.audit_logger.records if event == "policy_decision"
        ]
        self.assertEqual(
            policy_records,
            [{
                "manager": "notification_manager",
                "sub_action": "list_reminders",
                "capability": "safe_read",
                "decision": "allow",
                "risk": "low",
                "outcome": "allowed",
            }],
        )

    def test_calendar_write_and_open_use_one_combined_approval(self):
        core = _NotificationCore(approval=True)
        core.settings["policy_matrix"]["calendar_write"] = "ask"
        core.settings["policy_matrix"]["file_open"] = "ask"
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch("smarti.agent.productivity_tools.OUTPUTS_DIR", temp_dir),
                mock.patch("smarti.agent.productivity_tools.os.startfile", create=True) as startfile,
            ):
                result = core.notification_manager({
                    "action": "create_calendar_event",
                    "title": "פגישה משולבת",
                    "start": "2026-08-01T10:00:00",
                    "duration_minutes": 45,
                    "open": True,
                })
                created = list(os.scandir(temp_dir))

        self.assertTrue(result.startswith("SUCCESS:"), result)
        self.assertEqual(len(core.approval_requests), 1)
        self.assertEqual(len(created), 1)
        startfile.assert_called_once()
        approval_details = core.approval_requests[0][1]
        self.assertIn("פגישה משולבת", approval_details)
        self.assertIn("2026-08-01T10:00:00", approval_details)
        self.assertIn(".ics", approval_details)
        self.assertIn("כן", approval_details)
        capabilities = {
            payload["capability"]
            for event, payload in core.audit_logger.records
            if event == "policy_decision" and payload.get("sub_action") == "create_calendar_event"
        }
        self.assertEqual(capabilities, {"calendar_write", "file_open"})

    def test_denied_calendar_open_prevents_both_write_and_open(self):
        core = _NotificationCore()
        core.settings["policy_matrix"]["calendar_write"] = "allow"
        core.settings["policy_matrix"]["file_open"] = "deny"
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch("smarti.agent.productivity_tools.OUTPUTS_DIR", temp_dir),
                mock.patch("smarti.agent.productivity_tools.os.startfile", create=True) as startfile,
            ):
                result = core.notification_manager({
                    "action": "create_calendar_event",
                    "title": "אירוע חסום",
                    "start": "2026-08-01T10:00:00",
                    "open": True,
                })
                created = list(os.scandir(temp_dir))

        self.assertTrue(result.startswith("ERROR:"), result)
        self.assertEqual(created, [])
        startfile.assert_not_called()
        self.assertEqual(core.approval_requests, [])

    def test_calendar_without_open_does_not_consult_file_open_policy(self):
        core = _NotificationCore()
        core.settings["policy_matrix"]["calendar_write"] = "allow"
        core.settings["policy_matrix"]["file_open"] = "deny"
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                mock.patch("smarti.agent.productivity_tools.OUTPUTS_DIR", temp_dir),
                mock.patch("smarti.agent.productivity_tools.os.startfile", create=True) as startfile,
            ):
                result = core.notification_manager({
                    "action": "create_calendar_event",
                    "title": "אירוע ללא פתיחה",
                    "start": "2026-08-01T10:00:00",
                    "open": False,
                })

        self.assertTrue(result.startswith("SUCCESS:"), result)
        startfile.assert_not_called()
        capabilities = [
            payload["capability"]
            for event, payload in core.audit_logger.records
            if event == "policy_decision"
        ]
        self.assertEqual(capabilities, ["calendar_write"])

    def test_settings_alias_is_canonicalized_before_policy_and_cannot_bypass(self):
        core = _NotificationCore()
        normalized = core._normalize_tool_call_args(
            "notification_manager",
            {"action": "open_notification_settings"},
        )
        self.assertEqual(normalized["action"], "open_windows_app")
        self.assertEqual(normalized["target"], "notification_settings")

        core.settings["policy_matrix"]["settings_open"] = "deny"
        result = core.notification_manager({"action": "open_notification_settings"})
        self.assertTrue(result.startswith("ERROR:"), result)
        self.assertEqual(core.opened_uris, [])

    def test_invalid_action_and_target_are_rejected_before_policy(self):
        core = _NotificationCore()
        for args in (
            {"action": "something_else"},
            {"action": "open_windows_app", "target": "ms-settings:privacy"},
        ):
            with self.subTest(args=args):
                result = core.notification_manager(args)
                self.assertTrue(result.startswith("ERROR:"), result)
        self.assertEqual(core.approval_requests, [])
        self.assertEqual(core.audit_logger.records, [])
        self.assertEqual(core.opened_uris, [])

    def test_cancel_reminder_cannot_cancel_a_non_reminder_background_task(self):
        core = _NotificationCore()
        task = {
            "id": "job-1",
            "kind": "agent",
            "status": "scheduled",
            "history": [],
        }
        core.settings["background_tasks"].append(task)
        result = core.notification_manager({"action": "cancel_reminder", "id": "job-1"})
        self.assertTrue(result.startswith("ERROR:"), result)
        self.assertEqual(task["status"], "scheduled")
        self.assertEqual(core.approval_requests, [])
        self.assertEqual(core.audit_logger.records, [])

    def test_notification_actions_are_loop_guarded_but_listing_is_safe_to_repeat(self):
        core = _NotificationCore()
        self.assertTrue(core._tool_is_mutating_or_control(
            "notification_manager",
            {"action": "send_toast"},
        ))
        self.assertTrue(core._tool_is_mutating_or_control(
            "notification_manager",
            {"action": "open_notification_settings"},
        ))
        self.assertFalse(core._tool_is_mutating_or_control(
            "notification_manager",
            {"action": "list_reminders"},
        ))


if __name__ == "__main__":
    unittest.main()
