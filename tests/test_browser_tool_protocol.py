"""The reported Gemini browser turn must reach real agent dispatch, not final text."""
import copy
import json
import threading
import unittest
from unittest import mock

from smarti.core import SmartiCore
from smarti.config import DEFAULT_SETTINGS
from smarti.managers import AgentRuntime


class BrowserToolProtocolTests(unittest.TestCase):
    def setUp(self):
        core = self.core = SmartiCore.__new__(SmartiCore)
        core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        core.settings.update(max_agent_iterations=5, prevent_sleep_during_active_task=False)
        core.mode = 'gemini'
        core.system_prompt = 'Use the built-in browser.'
        core.gemini_history = []
        core.conversation_attachments = []
        core._execution_context = threading.local()
        core.agent_runtime = AgentRuntime(core)
        core.status_callback = core.step_callback = core.print_callback = None
        core._ensure_secret_loaded = lambda key: 'test-key'
        core._conversation_lock = lambda session: threading.RLock()
        core._raise_if_cancelled = lambda: None
        core._load_system_prompt = lambda *args, **kwargs: core.system_prompt
        core._save_active_task_checkpoint = mock.Mock()
        core._clear_task_checkpoint = mock.Mock()
        core._load_task_checkpoint = lambda: None
        core._log_usage = mock.Mock()
        core._record_context_token_usage = mock.Mock()
        core._compact_current_messages_if_needed = lambda *args, **kwargs: False
        core._compact_conversation_history = mock.Mock()
        core._record_tool_observation = mock.Mock()
        core.execute_tool = mock.Mock(return_value=('Browser observation: opened', None))

    @staticmethod
    def call(name, arguments):
        return json.dumps({'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}})

    def test_reported_response_fetches_schema_then_dispatches_browser_and_continues(self):
        reported = '<smarti_report>פותח את המידע על כלי אוטומציית הדפדפן...</smarti_report>{"method":"tools/call","params":{"name":"get_tool_info","arguments":{"tool_name":"browser_automation_manager","action":"full"}}}'
        navigate = self.call('browser_automation_manager', {'action': 'navigate', 'url': 'https://example.com/', 'presentation': 'visible'})
        self.core._handle_api_request_with_retry = mock.Mock(side_effect=[(reported, {}), (navigate, {}), ('הדפדפן נפתח.', {})])
        answer = self.core.send_message('פתח את הדפדפן המובנה', persist_turn=False)
        self.assertEqual(answer, 'הדפדפן נפתח.')
        self.assertEqual([call.args[0] for call in self.core.execute_tool.call_args_list], ['get_tool_info', 'browser_automation_manager'])
        self.assertEqual(self.core.execute_tool.call_args_list[1].args[1]['url'], 'https://example.com/')
        self.assertEqual(self.core._handle_api_request_with_retry.call_count, 3)

    def test_incomplete_call_or_report_alone_gets_repair_feedback_without_execution(self):
        for first in ['<smarti_report>פותח</smarti_report>', '<smarti_report>פותח</smarti_report>{"method":"tools/call","params":']:
            with self.subTest(first=first):
                self.setUp()
                self.core._handle_api_request_with_retry = mock.Mock(side_effect=[(first, {}), ('לא בוצעה פעולה בדפדפן.', {})])
                answer = self.core.send_message('פתח את הדפדפן המובנה', persist_turn=False)
                self.assertEqual(answer, 'לא בוצעה פעולה בדפדפן.')
                self.core.execute_tool.assert_not_called()
                submitted = self.core._handle_api_request_with_retry.call_args.args[1]
                self.assertIn('ERROR:', json.dumps(submitted))


if __name__ == '__main__':
    unittest.main()
