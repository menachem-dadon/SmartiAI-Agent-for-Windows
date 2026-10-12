import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.config import BUILTIN_TOOL_SCHEMAS
from smarti.codex_signin import CodexProtocolError, CodexSignInProvider
from smarti.api_errors import ApiRequestError, api_error_for_reason
from smarti.history import ChatSessionStore
from smarti.prompt_language import LANGUAGE_POLICY, model_error_text
from smarti.user_language import conversation_language, user_description, user_text
from tests.test_context_efficiency import _prompt_core
from tests.test_prompt_language import without_annotations


class EnglishToolLayerTests(unittest.TestCase):
    def core(self, language="he"):
        core = _prompt_core({"get_tool_info", "web_manager", "system_manager", "extension_manager"})
        core._current_user_language = language
        core.status_callback = None
        core.step_callback = None
        core._current_agent_process_events = []
        core._current_agent_process_started_at = 0
        core._truncate_tool_output = lambda value, **kwargs: str(value)
        return core

    def assertEnglish(self, value):
        self.assertNotRegex(str(value), r"[\u0590-\u05ff]")

    def test_schema_contract_tracks_reviewed_browser_extensions(self):
        # D88 native browser fields and D89's optional compact/full detail are
        # authorized contract additions. Prose annotations remain excluded.
        encoded = json.dumps(without_annotations(BUILTIN_TOOL_SCHEMAS), sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),
                         "f40d892fc693d52c962fc7c461dafef7d2bcc532ca75dffc514b530a142541a1")

    def test_security_wrappers_are_english_and_keep_markers_and_payloads(self):
        core = self.core()
        for action in ("web_manager", "load_skill", "run_skill"):
            for error in (False, True):
                with self.subTest(action=action, error=error):
                    text = core._wrap_tool_output_for_model(action, "completed", is_error=error)
                    self.assertEnglish(text)
                    marker = "UNTRUSTED_TOOL_ERROR" if error else "SKILL_OBSERVATION" if action in {"load_skill", "run_skill"} else "UNTRUSTED_TOOL_OUTPUT"
                    self.assertIn(marker + "_BEGIN", text)
                    self.assertIn(marker + "_END", text)
                    dynamic = "נתון חיצוני בעברית {0} C:\\קבצים\\דוח.txt"
                    self.assertIn(dynamic, core._wrap_tool_output_for_model(action, dynamic, is_error=error))

    def test_tool_feedback_is_english_in_native_and_local_requests(self):
        for provider in ("openai", "gemini", "local", "openai_codex_signin"):
            core = self.core()
            core.mode = provider
            messages = []
            core._append_tool_feedback(messages, "", "web_manager", "SUCCESS: Website opened.")
            self.assertEnglish(json.dumps(messages, ensure_ascii=False))
            self.assertIn("SUCCESS: Website opened.", json.dumps(messages))
            self.assertIn("UNTRUSTED_TOOL_OUTPUT", json.dumps(messages))

    def test_web_and_clipboard_results_are_english_with_exact_user_content(self):
        core = self.core()
        core.settings["enable_browser_automation"] = False
        with mock.patch("smarti.agent.productivity_tools.webbrowser.open") as opened:
            self.assertEqual(core.open_direct_website("https://example.com"), "Website opened.")
            self.assertEqual(core.open_direct_website("מילות חיפוש"), "Search completed.")
            self.assertEqual(opened.call_count, 2)
        core._run_cancelable_subprocess = mock.Mock(return_value=SimpleNamespace(returncode=0, stderr=""))
        self.assertEnglish(core.set_clipboard_tool("תוכן משתמש מדויק {0}"))
        self.assertEqual(core._run_cancelable_subprocess.call_args.kwargs["input"], "תוכן משתמש מדויק {0}")

    def test_empty_catalogs_and_validation_errors_are_english(self):
        core = self.core()
        core.settings["background_tasks"] = []
        core.skill_registry = {}
        core._background_lock = __import__("threading").RLock()
        for result in (core.list_background_tasks(), core.list_reminders(), core.list_skills(),
                       core.install_mcp("unversioned-package"), core.run_project_check_tool(".", "unknown command")):
            self.assertEnglish(result)
        core._sandbox_enabled = lambda: True
        core._sandbox_root = lambda: ""
        self.assertEnglish(core._ensure_sandbox_path_allowed("outside.txt", "read")[1])
        self.assertEnglish(core._sandbox_blocks_unconstrained_tool("system_command")[1])
        self.assertEqual(core._static_code_safety_check("while True:\n    pass", "computer_control")[0], False)
        self.assertEnglish(core._static_code_safety_check("while True:\n    pass", "computer_control")[1])

    def test_builtin_skill_results_are_english_and_progress_uses_hebrew_ui(self):
        with tempfile.TemporaryDirectory(prefix="smarti-english-") as directory:
            Path(directory, "sample.txt").write_text("source data", encoding="utf-8")
            for language in ("he", "en"):
                core = self.core(language)
                core._ensure_sandbox_path_allowed = lambda *args: (True, None)
                steps = []
                core.status_callback = steps.append
                result = core._run_builtin_skill("analyze_project", {"path": directory})
                self.assertEnglish(result)
                self.assertIn("Choose key files to read or run tests/build as needed.", result)
                self.assertTrue(steps)
                for step in steps:
                    self.assertRegex(step, r"[\u0590-\u05ff]")

    def test_generated_automation_success_text_and_stdout_are_english(self):
        core = self.core()
        for action, args in (("type", {"text": "Exact text"}), ("keys", {"keys": ["ctrl", "s"]})):
            code = core._computer_action_to_code(dict(args, action=action))
            self.assertEnglish(code)
            self.assertIn("SUCCESS:", code)
        code = core._computer_action_to_code({"action": "type", "text": "טקסט למשתמש"})
        self.assertIn("טקסט למשתמש", code)

    def test_generated_mcp_wrapper_is_english_and_preserves_external_payloads(self):
        core = self.core()
        with tempfile.TemporaryDirectory() as directory, mock.patch("smarti.agent.system_tools.MCP_TOOLS_DIR", directory):
            source = Path(core._write_mcp_wrapper("example@1.0.0")).read_text(encoding="utf-8")
            self.assertEnglish(source)
            self.assertIn('print(c.get("text", json.dumps(c, ensure_ascii=False)))', source)
            compile(source, "wrapper.py", "exec")

    def test_owned_provider_errors_are_machine_english_and_user_errors_stay_hebrew(self):
        core = self.core()
        analysis = api_error_for_reason("openai", "model", "rate_limit")
        error = ApiRequestError(analysis)
        self.assertEnglish(model_error_text(error))
        hebrew_response = core._api_error_user_response(analysis)
        self.assertRegex(hebrew_response, r"[\u0590-\u05ff]")
        core._current_user_language = "en"
        self.assertEqual(core._api_error_user_response(analysis), hebrew_response)
        self.assertEqual(core._display_assistant_text_for_history("ERROR_USER: Request failed."), "שגיאה: Request failed.")
        dynamic = ValueError("שגיאה חיצונית")
        self.assertEqual(model_error_text(dynamic), str(dynamic))

    def test_protocol_repair_diagnostics_are_english(self):
        provider = CodexSignInProvider.__new__(CodexSignInProvider)
        with self.assertRaises(CodexProtocolError) as caught:
            provider._decode_structured_turn('{"kind":"unexpected"}')
        self.assertEnglish(caught.exception.feedback_for_model())

    def test_tool_frames_and_logs_keep_real_result_and_hebrew_headings(self):
        core = self.core()
        data = "SUCCESS: completed\nנתון אמיתי"
        event = core._agent_tool_event_item("web_manager", {"action": "open", "query": "תוכן אמיתי"}, output=data)
        self.assertEqual(event["output_text"], data)
        self.assertEqual(json.loads(event["arguments_text"])["query"], "תוכן אמיתי")
        self.assertRegex(core._fallback_step_for_tool("web_manager", {"action": "open"}), r"[\u0590-\u05ff]")
        self.assertRegex(core._fallback_agent_report_for_tools([]), r"[\u0590-\u05ff]")
        core._current_user_language = "en"
        self.assertRegex(core._fallback_step_for_tool("web_manager", {"action": "open"}), r"[\u0590-\u05ff]")
        self.assertRegex(core._fallback_agent_report_for_tools([]), r"[\u0590-\u05ff]")

    def test_fixed_ui_text_ignores_conversation_language_and_model_reports_stay_exact(self):
        self.assertEnglish(LANGUAGE_POLICY)
        self.assertIn("interface language independently of the conversation language", LANGUAGE_POLICY)
        report = "I am checking the current page."
        for language in ("he", "en"):
            core = self.core(language)
            self.assertEqual(user_text(core, "חושב...", "Thinking..."), "חושב...")
            self.assertRegex(core._budget_exception_user_message("DAILY_COST_BUDGET"), r"[\u0590-\u05ff]")
            analysis = api_error_for_reason("openai", "model", "rate_limit")
            self.assertRegex(core._api_retry_user_status(analysis, 2, 1), r"[\u0590-\u05ff]")
            chosen, source = core._select_agent_report_for_tool_turn(
                report, [{"action": "web_manager", "arguments": {}}])
            self.assertEqual((chosen, source), (report, "model"))

    def test_audit_log_and_retained_context_keep_the_real_english_result(self):
        core = self.core()
        result = "SUCCESS: completed\nתוכן דינמי אמיתי"
        core._execute_tool_impl = lambda action, args: (result, None)
        records = []
        core._record_tool_context_event = lambda *args: records.append(args)
        core.audit_logger = None
        with mock.patch("smarti.agent.tool_dispatch.logging.info") as logged:
            feedback, message = core._execute_tool_with_audit("web_manager", {"query": "שאילתת משתמש"})
        self.assertEqual((feedback, message), (result, None))
        self.assertEqual(records[0][-1], result)
        self.assertTrue(any(call.args[-1] == result for call in logged.call_args_list))

    def test_presentation_language_ignores_system_tools_and_translation_content(self):
        history = [{"role": "user", "content": "תוכל לעזור לי בבקשה?"},
                   {"role": "assistant", "content": "English internal text"},
                   {"role": "tool", "content": "SUCCESS: completed"}]
        before = copy.deepcopy(history)
        self.assertEqual(conversation_language(history, "תרגם את הטקסט לאנגלית"), "he")
        self.assertEqual(conversation_language(history, 'תסביר את "completed successfully"'), "he")
        self.assertEqual(conversation_language(history, "ענה לי באנגלית"), "en")
        self.assertEqual(conversation_language(history, "Please explain the result"), "en")
        self.assertEqual(conversation_language(history, "web_manager"), "he")
        self.assertEqual(conversation_language([], "Hello"), "en")
        requested = history + [{"role": "user", "content": "מעתה ענה באנגלית"}]
        self.assertEqual(conversation_language(requested, "תסביר את התוצאה בבקשה"), "en")
        self.assertEqual(conversation_language(requested, "כעת ענה בעברית"), "he")
        self.assertEqual(history, before)

    def test_hebrew_ui_descriptions_do_not_enter_model_schemas(self):
        description = BUILTIN_TOOL_SCHEMAS["get_tool_info"]["description"]
        self.assertEnglish(description)
        self.assertRegex(user_description(description), r"[\u0590-\u05ff]")
        self.assertEqual(user_description(description, "en"), description)

    def test_new_prompt_construction_does_not_rewrite_stored_messages_or_tool_history(self):
        core = self.core()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "history.json")
            store = ChatSessionStore(str(path))
            store.ensure_active_session()
            store.add_turn("הודעת עבר", "תשובת עבר", assistant_metadata={"agent_process": {"events": [
                {"type": "tool_finish", "results": [{"output_text": "בוצע"}]}]}})
            path = Path(store.path)
            before = path.read_bytes()
            core.chat_store = store
            with mock.patch("smarti.agent.model_context.os.getcwd", return_value="C:\\Example"):
                self.assertEnglish(core._load_system_prompt())
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
