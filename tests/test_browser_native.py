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
from smarti.core import SmartiCore
from smarti.config import DEFAULT_SETTINGS
from smarti.history import ChatSessionStore
from smarti.browser_control import _HELPER_CODE
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

    def test_compact_state_retains_targets_options_paging_and_full_output(self):
        refs = {f'e{i}': {'ref': f'e{i}', 'role': 'link', 'name': 'A meaningful link', 'href': f'https://example.com/{i}',
                          'visible': True, 'enabled': True, 'tag': 'a', 'box': {'x': i, 'y': i, 'width': 100, 'height': 20}}
                for i in range(80)}
        refs['select'] = {'role': 'combobox', 'name': 'Sort', 'options': [{'value': 'price', 'label': 'Price', 'selected': False}], 'enabled': False}
        page = {'snapshotEpoch': 'document-a', 'url': 'https://example.com/', 'refs': refs, 'bodyText': 'page prose',
                'snapshot': 'duplicated names ' * 500, 'accessibility': [{'name': 'duplicate'}] * 300,
                'offset': 80, 'total': 180, 'hasMore': True}
        payload = {'ok': True, 'protocolVersion': 2, 'page': page, 'result': page}
        writer = mock.Mock(output_id='a' * 32)
        self.core._tool_output_writer_factory = lambda: lambda: writer
        compact = self.controller._json(payload)
        result = json.loads(compact.removeprefix(UNTRUSTED_BROWSER_PREFIX))
        self.assertLess(len(compact), len(json.dumps(payload)) * .4)
        self.assertEqual(set(result['page']['refs']), set(refs))
        self.assertEqual(result['page']['refs']['select']['options'], refs['select']['options'])
        self.assertFalse(result['page']['refs']['select']['enabled'])
        self.assertTrue(result['page']['hasMore'])
        self.assertEqual(result['page']['bodyText'], 'page prose')
        self.assertNotIn('result', result)
        self.assertEqual(result['fullOutput']['output_id'], writer.output_id)
        retained = json.loads(writer.write.call_args.args[0].removeprefix(UNTRUSTED_BROWSER_PREFIX))
        self.assertEqual(retained, payload)
        full = json.loads(self.controller._json(payload, detail='full').removeprefix(UNTRUSTED_BROWSER_PREFIX))
        self.assertEqual(full, payload)

    def test_archive_failure_returns_observation_without_claiming_action_failed(self):
        self.core._tool_output_writer_factory = lambda: lambda: mock.Mock(write=mock.Mock(side_effect=OSError('encryption unavailable')))
        self.core._truncate_tool_output = lambda text, **kwargs: text
        payload = {'protocolVersion': 2, 'ok': True, 'result': {'snapshotEpoch': 'epoch', 'refs': {}, 'snapshot': 'full observation'}}
        result = self.controller._json(payload)
        self.assertEqual(json.loads(result.removeprefix(UNTRUSTED_BROWSER_PREFIX)), payload)

    def test_default_body_excerpt_is_small_and_explicit_full_or_size_is_preserved(self):
        for arguments, expected in (({}, 2000), ({'bodyChars': 12345}, 12345), ({'detail': 'full'}, None)):
            with mock.patch('smarti.browser_control._open_native_request', return_value=self.response({'ok': True})) as opened:
                self.controller.run({'action': 'snapshot', **arguments})
            sent = json.loads(opened.call_args.args[0].data)
            self.assertEqual(sent.get('bodyChars'), expected)

    def test_browser_normalization_preserves_documented_arguments(self):
        core = SmartiCore.__new__(SmartiCore)
        core.settings = dict(DEFAULT_SETTINGS)
        calls = [
            {'action': 'snapshot', 'tabId': 'tab', 'offset': 80, 'textOffset': 2000, 'bodyChars': 2000, 'detail': 'full'},
            {'action': 'navigate', 'targetId': 'target', 'url': 'https://example.com/', 'presentation': 'visible'},
            {'action': 'select', 'tabId': 'tab', 'values': ['price'], 'ref': 'ref', 'requestId': 'receipt'},
            {'action': 'click', 'tabId': 'tab', 'ref': 'ref', 'nth': 2, 'snapshotEpoch': 'epoch', 'frameId': 'frame'},
        ]
        for arguments in calls:
            with self.subTest(arguments=arguments):
                normalized = core._normalize_tool_call_args('browser_automation_manager', arguments)
                self.assertEqual(normalized, arguments)
                self.assertEqual(core._validate_tool_call('browser_automation_manager', normalized), (True, None))
        normalized = core._normalize_tool_call_args('browser_automation_manager', {'action': 'snapshot', 'tab_id': 'tab', 'body_chars': 20})
        self.assertEqual(normalized, {'action': 'snapshot', 'tabId': 'tab', 'bodyChars': 20})
        invalid = core._normalize_tool_call_args('browser_automation_manager', {'action': 'snapshot', 'bogus': True})
        self.assertFalse(core._validate_tool_call('browser_automation_manager', invalid)[0])

    def test_legacy_helper_is_valid_python(self):
        compile(_HELPER_CODE, '<browser-helper>', 'exec')

    def test_full_observation_is_encrypted_and_retrievable_only_by_owning_conversation(self):
        core = SmartiCore.__new__(SmartiCore)
        core.settings = dict(DEFAULT_SETTINGS)
        core.chat_store = ChatSessionStore(str(Path(self.core.tempdir.name) / 'retention.json'))
        session = core.chat_store.active_session()['id']
        core._execution_context = types.SimpleNamespace(target_session_id=session)
        controller = SmartiBrowserController(core)
        payload = {'protocolVersion': 2, 'ok': True, 'result': {'snapshotEpoch': 'epoch', 'refs': {}, 'snapshot': 'complete untrusted fixture observation'}}
        value = json.loads(controller._json(payload).removeprefix(UNTRUSTED_BROWSER_PREFIX))
        handle = value['fullOutput']['output_id']
        full = core.read_tool_output({'output_id': handle, 'limit': 5000})
        self.assertEqual(json.loads(full.split('\n', 1)[1].removeprefix(UNTRUSTED_BROWSER_PREFIX)), payload)
        with core.chat_store._connect() as db:
            encrypted = db.execute('SELECT encrypted_text FROM tool_output_chunks WHERE output_id=?', (handle,)).fetchone()[0]
            self.assertNotIn(b'complete untrusted fixture', encrypted)
        core._execution_context.target_session_id = core.chat_store.create_session(set_active=False)['id']
        self.assertIn('not found in this conversation', core.read_tool_output({'output_id': handle}))


if __name__ == "__main__":
    unittest.main()
