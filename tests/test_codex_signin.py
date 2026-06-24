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

    def test_secure_config_uses_keyring_and_rejects_plaintext_auth(self):
        self.provider._ensure_secure_store_config()

        config = self.provider.config_path.read_text(encoding="utf-8")
        self.assertIn('cli_auth_credentials_store = "keyring"', config)
        self.assertFalse(self.provider.insecure_auth_path.exists())

        self.provider.insecure_auth_path.write_text('{"tokens":"never allowed"}', encoding="utf-8")
        status = self.provider.connection_status()
        self.assertEqual(status.state, "reauth_required")

    @mock.patch("smarti.codex_signin.subprocess.run")
    @mock.patch("smarti.codex_signin.shutil.which", return_value="codex-test")
    def test_status_uses_official_login_status_command(self, _which, run):
        run.return_value = mock.Mock(returncode=0, stdout="Logged in with ChatGPT", stderr="")

        status = self.provider.connection_status()

        self.assertEqual(status.state, "connected")
        command = run.call_args.args[0]
        self.assertEqual(command[1:], ["login", "status"])
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["CODEX_HOME"], str(self.provider.home_dir))
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("CODEX_API_KEY", env)
        self.assertNotIn("CODEX_ACCESS_TOKEN", env)

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


if __name__ == "__main__":
    unittest.main()
