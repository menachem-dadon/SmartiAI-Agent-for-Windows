"""Focused tests for the official Codex ChatGPT sign-in provider."""
import os
import tempfile
import unittest
from unittest import mock

from smarti.codex_signin import CodexConnectionStatus, CodexSignInProvider


class CodexSignInProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = CodexSignInProvider(self.temp.name, executable="codex-test")

    def tearDown(self):
        self.temp.cleanup()

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
        self.provider._run = mock.Mock(return_value=(0, "תשובה", ""))

        response, usage = self.provider.complete(
            [
                {"role": "system", "content": "הנחיות"},
                {"role": "user", "content": "שלום"},
            ],
            model="gpt-5.5",
        )

        self.assertEqual(response, "תשובה")
        self.assertEqual(usage, {})
        args = self.provider._run.call_args.args[0]
        self.assertEqual(args[:2], ["exec", "--ephemeral"])
        self.assertIn("read-only", args)
        self.assertIn("--skip-git-repo-check", args)
        self.assertIn("--model", args)
        self.assertIn("gpt-5.5", args)
        self.assertIn("[USER]", self.provider._run.call_args.kwargs["input_text"])

    def test_codex_default_defers_model_selection_to_the_signed_in_account(self):
        self.provider.connection_status = mock.Mock(
            return_value=CodexConnectionStatus("connected", "מחובר", "chatgpt")
        )
        self.provider._run = mock.Mock(return_value=(0, "תשובה", ""))

        self.provider.complete([{"role": "user", "content": "שלום"}], model="Codex default")

        args = self.provider._run.call_args.args[0]
        self.assertNotIn("--model", args)

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
