"""Focused tests for the official Codex ChatGPT sign-in provider."""
import os
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from smarti.codex_signin import CodexConnectionStatus, CodexSignInProvider
from smarti.common import provider_fallback_models


class CodexSignInProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = CodexSignInProvider(self.temp.name, executable="codex-test")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _codex_jsonl_response(text="תשובה", input_tokens=10, output_tokens=4, reasoning_tokens=0):
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
        self.assertIn("emit exactly the SmartiAI tool-call syntax", instructions)
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
        self.assertIn('web_search="disabled"', captured["args"])
        self.assertFalse(captured["path"].exists())

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


if __name__ == "__main__":
    unittest.main()
