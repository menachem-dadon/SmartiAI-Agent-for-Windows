"""Focused regressions for unified logs, export privacy and Windows attention UI."""
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication, QWidget

from smarti import common, ui_pages, ui_styles, windows_notifications
from smarti.api_errors import analyze_api_error, api_user_technical_details
from smarti.ui_controls import MaskedSecretLineEdit


class _Response:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class UnifiedLoggingTests(unittest.TestCase):
    def test_all_runtime_event_families_share_the_same_file(self):
        self.assertEqual(common.AGENT_LOG_FILE, common.AUDIT_LOG_FILE)
        self.assertEqual(common.AGENT_LOG_FILE, common.SKILL_LOG_FILE)
        self.assertEqual(common.AGENT_LOG_FILE, common.UNIFIED_LOG_FILE)

    def test_formatter_keeps_multiline_records_on_one_physical_line(self):
        formatter = common.SmartiLogFormatter("%(levelname)s | %(message)s")
        record = logging.LogRecord("smarti.test", logging.INFO, __file__, 1, "first\nsecond", (), None)

        rendered = formatter.format(record)

        self.assertEqual(rendered.count("\n"), 0)
        self.assertIn(r"first\nsecond", rendered)

    def test_unified_tail_crosses_rotated_files_without_loading_unrequested_history(self):
        with tempfile.TemporaryDirectory() as directory:
            older = os.path.join(directory, "smarti_agent.log.1")
            active = os.path.join(directory, "smarti_agent.log")
            Path(older).write_text("old-1\nold-2\n", encoding="utf-8")
            Path(active).write_text("new-1\nnew-2\n", encoding="utf-8")
            with mock.patch.object(ui_pages, "unified_log_paths", return_value=[older, active]):
                rows = ui_pages._unified_log_lines(3)

        self.assertEqual(rows, ["old-2", "new-1", "new-2"])

    def test_personal_export_filter_keeps_codes_and_removes_payloads(self):
        rows = [
            "2026-08-11 10:00:00 | INFO | PERSONAL | kind=user_message | chars=12 | content=הכתובת שלי סודית",
            "2026-08-11 10:00:01 | ERROR | API FAILURE | status=429 | code=rate_limit | raw=echoed prompt",
            "2026-08-11 10:00:02 | INFO | AUDIT | " + json.dumps({
                "event": "tool_finish",
                "payload": {"tool": "memory_manager", "status": "ok", "preview": "זיכרון פרטי"},
            }, ensure_ascii=False),
            "2026-08-11 10:00:03 | INFO | TRACE | observe | פלט כלי אישי",
        ]

        sanitized = "\n".join(ui_pages.sanitize_log_export_lines(rows, {}))

        self.assertNotIn("הכתובת שלי סודית", sanitized)
        self.assertNotIn("echoed prompt", sanitized)
        self.assertNotIn("זיכרון פרטי", sanitized)
        self.assertNotIn("פלט כלי אישי", sanitized)
        self.assertIn("status=429", sanitized)
        self.assertIn("rate_limit", sanitized)
        self.assertIn("memory_manager", sanitized)
        self.assertIn("tool_finish", sanitized)

    def test_personal_export_filter_removes_paths_and_unknown_json_strings(self):
        rows = [
            r"2026-08-11 10:00:00 | INFO | DEVELOPER_LOG | path=C:\Users\Someone\Documents\medical.txt | status=ok",
            "2026-08-11 10:00:01 | INFO | AUDIT | " + json.dumps({
                "event": "memory_saved",
                "payload": {"fact": "private address", "status": "ok", "count": 1},
            }),
        ]

        sanitized = "\n".join(ui_pages.sanitize_log_export_lines(rows, {}))

        self.assertNotIn("medical.txt", sanitized)
        self.assertNotIn("private address", sanitized)
        self.assertIn("status=ok", sanitized)
        self.assertIn('"event": "memory_saved"', sanitized)
        self.assertIn('"count": 1', sanitized)

    def test_clear_unified_log_removes_retained_rotations(self):
        with tempfile.TemporaryDirectory() as directory:
            active = os.path.join(directory, "smarti_agent.log")
            Path(active).write_text("active\n", encoding="utf-8")
            Path(active + ".1").write_text("old\n", encoding="utf-8")
            Path(active + ".2").write_text("older\n", encoding="utf-8")

            common.clear_unified_log_file(active)

            self.assertEqual(Path(active).read_text(encoding="utf-8"), "")
            self.assertFalse(Path(active + ".1").exists())
            self.assertFalse(Path(active + ".2").exists())


class ProviderErrorDetailTests(unittest.TestCase):
    def test_openai_insufficient_quota_is_not_misreported_as_transient_rate_limit(self):
        response = _Response(
            429,
            {"error": {
                "message": "You exceeded your current quota",
                "type": "insufficient_quota",
                "code": "insufficient_quota",
            }},
            {"x-request-id": "req-test-123"},
        )

        analysis = analyze_api_error("openai", "gpt-test", response=response)
        details = "\n".join(api_user_technical_details(analysis))

        self.assertEqual(analysis.category, "billing_quota")
        self.assertEqual(analysis.retry_action, "none")
        self.assertIn("מכסת החשבון", analysis.user_message)
        self.assertIn("HTTP 429", details)
        self.assertIn("insufficient_quota", details)
        self.assertIn("req-test-123", details)

    def test_gemini_status_code_gets_provider_specific_reason(self):
        response = _Response(
            400,
            {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "bad generation config"}},
        )

        analysis = analyze_api_error("gemini", "gemini-test", response=response)

        self.assertEqual(analysis.category, "invalid_request")
        self.assertIn("INVALID_ARGUMENT", analysis.user_message)
        self.assertIn("פרמטר או מבנה", analysis.user_message)


class PasteButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_paste_icon_button_fills_masked_secret_without_exposing_old_value(self):
        class Host(QWidget):
            _paste_into_settings_edit = ui_pages.SettingsPage._paste_into_settings_edit
            _make_paste_icon_button = ui_pages.SettingsPage._make_paste_icon_button

        host = Host()
        edit = MaskedSecretLineEdit("old-secret")
        button = host._make_paste_icon_button(edit)
        self.app.clipboard().setText("  new-api-key  ")

        button.click()

        self.assertEqual(edit.secret(), "new-api-key")
        self.assertEqual(tuple(button.property("smartiIconNames"))[0], "paste_icon")
        host.deleteLater()


class WindowsAttentionAndPackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_taskbar_badge_counts_notifications_and_clears_on_attention_stop(self):
        class Window(QObject):
            def isActiveWindow(self):
                return False

            def windowHandle(self):
                return SimpleNamespace(winId=lambda: 123)

        window = Window()
        controller = windows_notifications.TaskbarAttentionController(window)
        controller._cached_hwnd = 123
        with (
            mock.patch.object(windows_notifications.platform, "system", return_value="Windows"),
            mock.patch.object(controller, "_set_overlay_badge", return_value=True) as overlay,
            mock.patch.object(controller, "_flash", return_value=True),
        ):
            controller.request_attention()
            controller.request_attention()
            self.assertEqual(controller.unread_count, 2)
            controller.acknowledge_one()
            self.assertEqual(controller.unread_count, 1)
            controller.stop()

        self.assertEqual(controller.unread_count, 0)
        self.assertEqual([call.args[1] for call in overlay.call_args_list], [1, 2, 1, 0])

    def test_taskbar_projection_does_not_force_native_window_creation(self):
        state = {"created": False, "widget_win_id_calls": 0, "window_win_id_calls": 0}

        class WindowHandle:
            def winId(self):
                state["window_win_id_calls"] += 1
                return 123

        class Window(QObject):
            def testAttribute(self, _attribute):
                return state["created"]

            def winId(self):
                state["widget_win_id_calls"] += 1
                raise AssertionError("QWidget.winId must never be called by taskbar projection")

            def windowHandle(self):
                if not state["created"]:
                    return None
                return WindowHandle()

        controller = windows_notifications.TaskbarAttentionController(Window())
        with (
            mock.patch.object(windows_notifications.platform, "system", return_value="Windows"),
            mock.patch.object(controller, "_set_overlay_badge", return_value=True) as overlay,
        ):
            self.assertFalse(controller.sync_unread_count(4))
            self.assertEqual(controller.unread_count, 4)
            self.assertEqual(state["widget_win_id_calls"], 0)
            self.assertEqual(state["window_win_id_calls"], 0)
            overlay.assert_not_called()

            state["created"] = True
            self.assertEqual(controller.capture_window_handle(), 123)
            self.assertTrue(controller.sync_unread_count(4))

        self.assertEqual(state["widget_win_id_calls"], 0)
        self.assertEqual(state["window_win_id_calls"], 1)
        overlay.assert_called_once_with(123, 4)

    def test_fallback_toast_dismissal_does_not_clear_unread_badge(self):
        center = windows_notifications.WindowsNotificationCenter()
        acknowledged = []
        center.attention_cleared.connect(lambda: acknowledged.append(True))

        toast = center._show_fallback("title", "body")
        toast.dismissed.emit()
        self.assertEqual(acknowledged, [])

        toast.activated.emit()
        self.assertEqual(acknowledged, [True])
        toast.deleteLater()

    def test_fallback_toast_opens_its_source_conversation(self):
        center = windows_notifications.WindowsNotificationCenter()
        opened = []
        generic = []
        center.conversation_switch_requested.connect(opened.append)
        center.activate_requested.connect(lambda: generic.append(True))

        toast = center._show_fallback(
            "title", "body", conversation_id="source-session"
        )
        toast.activated.emit()

        self.assertEqual(opened, ["source-session"])
        self.assertEqual(generic, [])
        toast.deleteLater()

    def test_fallback_quick_reply_is_bound_to_its_source_conversation(self):
        center = windows_notifications.WindowsNotificationCenter()
        routed = []
        generic = []
        center.conversation_reply_requested.connect(
            lambda session_id, text: routed.append((session_id, text))
        )
        center.reply_requested.connect(generic.append)

        toast = center._show_fallback(
            "title", "body", reply=True, conversation_id="source-session"
        )
        toast.reply_submitted.emit("continue")

        self.assertEqual(routed, [("source-session", "continue")])
        self.assertEqual(generic, [])
        toast.deleteLater()

    def test_fallback_permission_answer_acknowledges_only_once(self):
        center = windows_notifications.WindowsNotificationCenter()
        acknowledged = []
        answers = []
        center.attention_cleared.connect(lambda: acknowledged.append(True))
        with mock.patch.object(center, "_ensure_native", return_value=False):
            center.show_permission_request("title", "details", callback=answers.append)
        toast = center._fallback_toasts[-1]

        toast.permission_answered.emit(True)

        self.assertEqual(acknowledged, [True])
        self.assertEqual(answers, [True])
        toast.deleteLater()

    def test_rounded_corner_controller_applies_to_top_level_windows(self):
        widget = QWidget()
        controller = ui_styles.WindowsRoundedCornerController(self.app)
        with (
            mock.patch.object(ui_styles, "_safe_top_level_hwnd", return_value=123),
            mock.patch.object(ui_styles, "apply_windows_rounded_corners", return_value=True) as apply,
        ):
            controller.apply_to(widget)
            controller.apply_to(widget)

        apply.assert_called_once_with(widget, hwnd=123)
        widget.deleteLater()

    def test_rounded_corner_projection_never_calls_qwidget_win_id(self):
        class GuardedWidget(QWidget):
            def winId(self):
                raise AssertionError("QWidget.winId must never be called")

        widget = GuardedWidget()
        widget.show()
        self.app.processEvents()
        with mock.patch.object(ui_styles.platform, "system", return_value="Windows"):
            hwnd = ui_styles._safe_top_level_hwnd(widget)

        self.assertGreater(hwnd, 0)
        widget.close()
        widget.deleteLater()

    def test_rounded_corner_projection_skips_short_lived_tool_windows(self):
        widget = QWidget(None, ui_styles.Qt.WindowType.Tool)
        widget.show()
        self.app.processEvents()
        with mock.patch.object(ui_styles.platform, "system", return_value="Windows"):
            self.assertEqual(ui_styles._safe_top_level_hwnd(widget), 0)
        widget.close()
        widget.deleteLater()

    def test_packaged_executable_embeds_modern_windows_manifest(self):
        repo_root = Path(__file__).resolve().parents[1]
        manifest = (repo_root / "packaging" / "smarti.manifest").read_text(encoding="utf-8")
        spec = (repo_root / "packaging" / "smarti.spec").read_text(encoding="utf-8")

        self.assertIn("8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a", manifest)
        self.assertIn("PerMonitorV2", manifest)
        self.assertIn("manifest=str(app_manifest)", spec)


if __name__ == "__main__":
    unittest.main()
