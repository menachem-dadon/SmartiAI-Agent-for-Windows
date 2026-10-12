"""Regression boundaries between Python policy, native transport and model input."""
import base64
import json
import os
import types
import unittest
from pathlib import Path
from unittest import mock

from smarti.browser_control import SmartiBrowserController, UNTRUSTED_BROWSER_PREFIX
from smarti.agent.browser_runtime import BrowserRuntimeMixin
from tests.test_doctor import _BrowserAutomationCore


class NativeBrowserTests(unittest.TestCase):
    def setUp(self):
        self.core = _BrowserAutomationCore()
        self.core._execution_context = types.SimpleNamespace(target_session_id="conversation-a", run_id="run-a")
        self.controller = SmartiBrowserController(self.core)
        self.env = mock.patch.dict(os.environ, {
            "SMARTI_TAURI_BROWSER_BROKER_PORT": "54321",
            "SMARTI_TAURI_BROWSER_BROKER_TOKEN": "a" * 64,
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.core.cleanup()

    def response(self, value):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(value).encode()
        return response

    def test_doctor_and_profiles_use_actual_native_transport(self):
        for action in ("doctor", "profiles", "status", "start"):
            with mock.patch("smarti.browser_control._open_native_request", return_value=self.response({"ok": True, "protocolVersion": 2})) as opened:
                result = self.controller.run({"action": action})
            self.assertTrue(result.startswith(UNTRUSTED_BROWSER_PREFIX))
            sent = json.loads(opened.call_args.args[0].data)
            self.assertEqual(sent["action"], action)
            self.assertEqual(sent["sessionId"], "conversation-a")
            self.assertFalse(self.core.ensure_called)

    def test_nested_act_aliases_and_ownership_are_normalized(self):
        with mock.patch("smarti.browser_control._open_native_request", return_value=self.response({"ok": True})) as opened:
            self.controller.run({"action": "act", "userControl": True, "tabId": "tab-a", "request": {"kind": "scrollIntoView", "ref": "ref-a"}})
        sent = json.loads(opened.call_args.args[0].data)
        self.assertEqual(sent["action"], "scroll_into_view")
        self.assertEqual(sent["tabId"], "tab-a")
        self.assertNotIn("userControl", sent)
        self.assertEqual(sent["ref"], "ref-a")
        self.assertTrue(sent["requestId"])

    def test_snapshot_does_not_create_artifact_directories(self):
        with mock.patch.object(self.controller, "_artifact_dir", side_effect=AssertionError("unexpected persistence")), mock.patch("smarti.browser_control._open_native_request", return_value=self.response({"ok": True})):
            self.assertFalse(self.controller.run({"action": "snapshot"}).startswith("ERROR"))

    def test_screenshot_attaches_image_with_observation_and_no_base64_transcript(self):
        encoded = base64.b64encode(b"native-png-image").decode()
        with mock.patch("smarti.browser_control._open_native_request", return_value=self.response({"ok": True, "tabId": "tab-a", "result": {"data": encoded, "annotations": {"ref-a": {"name": "Target"}}}})):
            result = self.controller.run({"action": "screenshot"})
        self.assertTrue(result.startswith("ATTACHMENT_JSON:"))
        envelope = json.loads(result.removeprefix("ATTACHMENT_JSON:"))
        self.assertEqual(Path(envelope["attachments"][0]["path"]).read_bytes(), b"native-png-image")
        self.assertEqual(envelope["tool_result"]["result"]["annotations"]["ref-a"]["name"], "Target")
        self.assertNotIn(encoded, result)

    def test_expected_download_waits_and_saves_in_controlled_directory(self):
        source = Path(self.core.tempdir.name, 'native-download.txt')
        source.write_text('completed download', encoding='utf-8')
        native = {'ok': True, 'result': {'success': True, 'path': str(source), 'url': 'https://example.com/file'}}
        with mock.patch('smarti.browser_control._open_native_request', return_value=self.response(native)) as opened:
            result = self.controller.run({'action': 'click', 'selector': '#download', 'expectDownload': True, 'downloadPath': 'saved.txt'})
        sent = json.loads(opened.call_args.args[0].data)
        self.assertEqual(sent['action'], 'download')
        parsed = json.loads(result.removeprefix(UNTRUSTED_BROWSER_PREFIX))
        target = Path(parsed['path'])
        self.assertEqual(target.read_text(encoding='utf-8'), 'completed download')
        self.assertEqual(target.name, 'saved.txt')
        self.assertTrue(source.exists())

    def test_private_navigation_in_nested_request_is_blocked_before_native_action(self):
        with mock.patch("smarti.browser_control._open_native_request") as opened:
            result = self.controller.run({"action": "act", "request": {"kind": "navigate", "url": "http://127.0.0.1/private"}})
        self.assertTrue(result.startswith("ERROR"))
        opened.assert_not_called()

    def test_native_exception_is_not_reported_as_success(self):
        with mock.patch("smarti.browser_control._open_native_request", return_value=self.response({"ok": False, "error": "STALE_REF"})):
            self.assertTrue(self.controller.run({"action": "click", "ref": "old"}).startswith("ERROR"))

    def test_missing_response_preserves_uncertain_outcome(self):
        with mock.patch("smarti.browser_control._open_native_request", side_effect=TimeoutError("lost response")):
            result = self.controller.run({"action": "click", "ref": "x", "requestId": "stable-id"})
        self.assertIn("outcome is unknown", result)
        self.assertIn("stable-id", result)

    def test_native_start_never_launches_legacy_chrome(self):
        runtime = BrowserRuntimeMixin()
        runtime.browser_controller = self.controller
        runtime.run_browser_action = mock.Mock(return_value='{"ok":true}')
        runtime._chrome_executable = mock.Mock(side_effect=AssertionError("external Chrome"))
        self.assertEqual(runtime._ensure_automation_browser(), (True, None))
        runtime.run_browser_action.assert_called_once_with({"action": "start", "url": "about:blank", "noSnapshot": True})


if __name__ == "__main__":
    unittest.main()
