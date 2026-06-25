"""Focused tests for the official Codex ChatGPT sign-in provider."""
import os
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from smarti.codex_signin import CodexConnectionStatus, CodexSignInError, CodexSignInProvider
from smarti.common import provider_fallback_models
from smarti.core import SmartiCore
from smarti.managers import AgentRuntime


class CodexSignInProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = CodexSignInProvider(self.temp.name, executable="codex-test")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _codex_jsonl_response(
        text="תשובה",
        input_tokens=10,
        output_tokens=4,
        reasoning_tokens=0,
        tool_name=None,
        tool_arguments=None,
        progress_report=None,
    ):
        if tool_name:
            text = json.dumps(
                {
                    "kind": "tool_calls",
                    "tool_calls": [{"name": tool_name, "arguments_json": json.dumps(tool_arguments or {}, ensure_ascii=False)}],
                    "final_answer": None,
                    "progress_report": progress_report,
                },
                ensure_ascii=False,
            )
        else:
            text = json.dumps(
                {
                    "kind": "final",
                    "tool_calls": None,
                    "final_answer": text,
                    "progress_report": None,
                },
                ensure_ascii=False,
            )
        return "\n".join(
            (
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}}, ensure_ascii=False),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "reasoning_output_tokens": reasoning_tokens,
                        },
                    }
                ),
            )
        )

    def test_environment_preserves_official_cli_home_without_api_credentials(self):
        with mock.patch.dict(
            os.environ,
            {
                "CODEX_HOME": r"C:\Users\test user\Codex Home",
                "OPENAI_API_KEY": "must-not-reach-codex",
                "CODEX_API_KEY": "must-not-reach-codex",
                "CODEX_ACCESS_TOKEN": "must-not-reach-codex",
            },
            clear=False,
        ):
            environment = self.provider._environment()

        self.assertEqual(environment["CODEX_HOME"], r"C:\Users\test user\Codex Home")
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("CODEX_API_KEY", environment)
        self.assertNotIn("CODEX_ACCESS_TOKEN", environment)

    def test_smarti_codex_cli_override_is_used_verbatim(self):
        path = r"C:\Users\יהודית סיידון\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe"
        with mock.patch.dict(os.environ, {"SMARTI_CODEX_CLI": path}):
            self.assertEqual(self.provider._find_executable(), path)

    def test_codex_model_choices_are_the_supported_curated_list(self):
        self.assertEqual(
            provider_fallback_models("openai_codex_signin"),
            ["codex default", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini"],
        )

    def test_windows_apps_desktop_path_is_not_treated_as_the_cli(self):
        desktop_path = r"C:\Program Files\WindowsApps\OpenAI.Codex\app\resources\codex.exe"
        self.assertTrue(self.provider._is_windows_apps_path(desktop_path))

    @mock.patch("smarti.codex_signin.subprocess.run")
    @mock.patch("smarti.codex_signin.shutil.which", return_value="codex-test")
    def test_status_uses_official_login_status_command(self, _which, run):
        run.return_value = mock.Mock(returncode=0, stdout="Logged in with ChatGPT", stderr="")

        status = self.provider.connection_status()

        self.assertEqual(status.state, "connected")
        command = run.call_args.args[0]
        self.assertEqual(command[1:], ["login", "status"])
        env = run.call_args.kwargs["env"]
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("CODEX_ACCESS_TOKEN", env)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_connection_status_distinguishes_missing_and_expired_credentials(self):
        self.provider._run = mock.Mock(return_value=(1, "Not logged in", ""))
        missing = self.provider.connection_status()
        self.assertEqual(missing.state, "not_connected")

        self.provider._run = mock.Mock(return_value=(1, "Access token expired", ""))
        expired = self.provider.connection_status()
        self.assertEqual(expired.state, "reauth_required")

    @mock.patch("smarti.codex_signin.subprocess.run", side_effect=PermissionError())
    @mock.patch("smarti.codex_signin.shutil.which", return_value="codex-test")
    def test_permission_denied_reports_a_runnable_cli_problem(self, _which, _run):
        status = self.provider.connection_status()

        self.assertEqual(status.state, "unavailable")
        self.assertIn("Windows אינו מאפשר", status.message)

    def test_complete_is_ephemeral_and_read_only(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, self._codex_jsonl_response("תשובה", 12, 5, 3), ""))

        response, usage = self.provider.complete(
            [
                {"role": "system", "content": "הנחיות"},
                {"role": "user", "content": "שלום"},
            ],
            model="gpt-5.5",
        )

        self.assertEqual(response, "תשובה")
        self.assertEqual(usage, {"prompt": 12, "completion": 8, "total": 20})
        args = self.provider._run.call_args.args[0]
        self.assertEqual(args[:2], ["exec", "--json"])
        self.assertIn("--json", args)
        self.assertIn("--ignore-user-config", args)
        self.assertIn("read-only", args)
        self.assertIn("--skip-git-repo-check", args)
        self.assertIn("--model", args)
        self.assertIn("gpt-5.5", args)
        self.assertEqual(args[-1], "-")
        self.assertIn("[USER]", self.provider._run.call_args.kwargs["input_text"])

    def test_codex_default_defers_model_selection_to_the_signed_in_account(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, self._codex_jsonl_response(), ""))

        self.provider.complete([{"role": "user", "content": "שלום"}], model="codex default")

        args = self.provider._run.call_args.args[0]
        self.assertNotIn("--model", args)

    def test_reasoning_effort_is_passed_as_an_official_cli_config_override(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, self._codex_jsonl_response(), ""))

        self.provider.complete(
            [{"role": "user", "content": "שלום"}],
            model="gpt-5.5",
            reasoning_effort="xhigh",
        )

        args = self.provider._run.call_args.args[0]
        config_values = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--config"]
        self.assertIn('model_reasoning_effort="xhigh"', config_values)
        self.assertEqual(args[args.index("--model") + 1], "gpt-5.5")

    def test_agent_prompt_preserves_system_tools_without_authorizing_native_codex_actions(self):
        messages = [
            {"role": "system", "content": "Use TOOL_CALL syntax when a tool is needed."},
            {"role": "user", "content": "צור קנבס."},
        ]
        instructions = self.provider._build_model_instructions(messages)
        prompt = self.provider._build_prompt(messages)

        self.assertIn("[SMARTIAI SYSTEM INSTRUCTIONS]", instructions)
        self.assertIn("Use TOOL_CALL syntax", instructions)
        self.assertIn("supplied JSON Schema", instructions)
        self.assertIn("legacy instruction", instructions)
        self.assertIn("Never claim that a tool, canvas", instructions)
        self.assertNotIn("Use TOOL_CALL syntax", prompt)
        self.assertIn("[USER]", prompt)

    def test_complete_uses_a_temporary_base_instruction_file_and_disables_native_tools(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        captured = {}

        def run(args, **kwargs):
            args = list(args)
            config_values = [args[index + 1] for index, value in enumerate(args[:-1]) if value == "--config"]
            instructions_config = next(value for value in config_values if value.startswith("model_instructions_file="))
            instructions_path = Path(json.loads(instructions_config.split("=", 1)[1]))
            captured["path"] = instructions_path
            captured["instructions"] = instructions_path.read_text(encoding="utf-8")
            schema_path = Path(args[args.index("--output-schema") + 1])
            captured["schema_path"] = schema_path
            captured["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
            captured["args"] = args
            captured["prompt"] = kwargs["input_text"]
            return 0, self._codex_jsonl_response(), ""

        self.provider._run = mock.Mock(side_effect=run)
        self.provider.complete(
            [
                {"role": "system", "content": "Smarti system rule."},
                {"role": "user", "content": "שלום"},
            ],
            model="gpt-5.5",
        )

        self.assertIn("Smarti system rule.", captured["instructions"])
        self.assertNotIn("Smarti system rule.", captured["prompt"])
        self.assertIn("--disable", captured["args"])
        self.assertIn("shell_tool", captured["args"])
        self.assertIn("--ignore-user-config", captured["args"])
        self.assertIn("--output-schema", captured["args"])
        self.assertIn('web_search="disabled"', captured["args"])
        self.assertFalse(captured["path"].exists())
        self.assertFalse(captured["schema_path"].exists())
        self.assertEqual(captured["schema"]["properties"]["kind"]["enum"], ["tool_calls", "final"])
        self.assertFalse(captured["schema"]["properties"]["tool_calls"]["items"]["additionalProperties"])
        self.assertEqual(
            captured["schema"]["properties"]["tool_calls"]["items"]["properties"]["arguments_json"]["type"],
            "string",
        )

    def test_schema_tool_turn_is_mapped_to_the_existing_smarti_tool_wire_format(self):
        response = self.provider._decode_structured_turn(json.dumps({
            "kind": "tool_calls",
            "tool_calls": [{"name": "web_manager", "arguments_json": '{"action":"search","query":"test"}'}],
            "final_answer": None,
            "progress_report": "אני בודק מידע עדכני ברשת.",
        }))

        report, wire_format = response.split("\n", 1)
        self.assertEqual(report, "אני בודק מידע עדכני ברשת.")
        self.assertEqual(json.loads(wire_format), {
            "tool_calls": [{"name": "web_manager", "arguments": {"action": "search", "query": "test"}}],
        })

        parsed = AgentRuntime(mock.Mock()).extract_tool_calls(response)
        self.assertEqual(parsed["pre_text"], "אני בודק מידע עדכני ברשת.")
        self.assertEqual(len(parsed["tool_calls"]), 1)

    def test_schema_rejects_non_object_tool_arguments(self):
        with self.assertRaises(CodexSignInError):
            self.provider._decode_structured_turn(json.dumps({
                "kind": "tool_calls",
                "tool_calls": [{"name": "web_manager", "arguments_json": "[]"}],
                "final_answer": None,
                "progress_report": None,
            }))

    def test_invalid_schema_turn_is_rejected_without_text_heuristics(self):
        with self.assertRaises(CodexSignInError):
            self.provider._decode_structured_turn('{"kind":"final","tool_calls":null,"final_answer":null,"progress_report":null}')

    def test_login_skips_interactive_command_when_already_connected(self):
        connected = CodexConnectionStatus("connected", "מחובר", "chatgpt")
        self.provider.connection_status = mock.Mock(return_value=connected)
        self.provider._run = mock.Mock()

        status = self.provider.login()

        self.assertIs(status, connected)
        self.provider._run.assert_not_called()

    def test_login_uses_a_new_console_after_a_not_connected_status(self):
        self.provider.connection_status = mock.Mock(
            side_effect=[CodexConnectionStatus("not_connected", "לא מחובר"), CodexConnectionStatus("connected", "מחובר")]
        )
        self.provider._run = mock.Mock(return_value=(0, "", ""))

        status = self.provider.login()

        self.assertEqual(status.state, "connected")
        self.provider._run.assert_called_once_with(
            ("login",), timeout=600, interactive_console=(os.name == "nt")
        )


class AgentReportTests(unittest.TestCase):
    def setUp(self):
        self.core = SmartiCore.__new__(SmartiCore)

    def test_first_agent_report_is_allowed(self):
        report = self.core._should_emit_agent_report("סטטוס: אני בודק את הקבצים הרלוונטיים.")

        self.assertEqual(report, "אני בודק את הקבצים הרלוונטיים.")

    def test_duplicate_agent_report_is_suppressed(self):
        report = self.core._should_emit_agent_report(
            "אני בודק את הקבצים הרלוונטיים עכשיו.",
            last_report="אני בודק את הקבצים הרלוונטיים עכשיו",
        )

        self.assertEqual(report, "")

    def test_distinct_agent_report_is_allowed_after_a_previous_report(self):
        report = self.core._should_emit_agent_report(
            "מצאתי את אזור הקוד הרלוונטי, ועכשיו אני בודק את הלוגים מולו.",
            last_report="אני בודק את הקבצים הרלוונטיים.",
        )

        self.assertEqual(report, "מצאתי את אזור הקוד הרלוונטי, ועכשיו אני בודק את הלוגים מולו.")

    def test_first_tool_turn_without_model_report_gets_a_fallback(self):
        report, source = self.core._select_agent_report_for_tool_turn(
            "",
            [{"action": "internet_search", "arguments": {"query": "example"}}],
            report_count=0,
        )

        self.assertTrue(report)
        self.assertEqual(source, "fallback")

    def test_later_tool_turn_without_model_report_does_not_force_fallback(self):
        report, source = self.core._select_agent_report_for_tool_turn(
            "",
            [{"action": "internet_search", "arguments": {"query": "example"}}],
            last_report="Checking current information.",
            report_count=1,
        )

        self.assertEqual(report, "")
        self.assertEqual(source, "")

    def test_later_tool_turn_with_useful_model_report_is_allowed(self):
        report, source = self.core._select_agent_report_for_tool_turn(
            "I found the relevant area and am checking the logs against it.",
            [{"action": "smart_file_search", "arguments": {"query": "logs"}}],
            last_report="Checking the relevant files.",
            report_count=1,
        )

        self.assertEqual(report, "I found the relevant area and am checking the logs against it.")
        self.assertEqual(source, "model")


if __name__ == "__main__":
    unittest.main()
