import tempfile
import copy
import json
import urllib.error
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.agent.model_context import ModelContextMixin
from smarti.common import LEGAL_AGREEMENT_VERSION
from smarti.local_gateway import SmartiLocalGateway
from smarti.run_manager import ConversationRunManager
from smarti.config import DEFAULT_SETTINGS
from smarti.managers import SettingsManager
from tests import test_conversation_runs as fixtures


class SettingsPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "smarti_settings.json"
        self.manager = SettingsManager(str(self.path), DEFAULT_SETTINGS)
        self.core = SimpleNamespace(settings_manager=self.manager)
        self.core._save_settings = lambda: self.manager.save(self.core.settings)
        patcher = mock.patch("smarti.agent.model_context.SETTINGS_FILE", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_custom_settings_and_consent_survive_migration_save_and_reload(self):
        original = {
            "settings_schema_version": 2,
            "api_mode": "openai_codex_signin",
            "favorite_models": [{"provider": "openai", "model": "chosen-model"}],
            "ui_preferences": {"theme_mode": "light", "custom_preference": True},
            "legal_acceptance": {"accepted": True, "version": LEGAL_AGREEMENT_VERSION},
        }
        self.path.write_text(json.dumps(original), encoding="utf-8")
        loaded = ModelContextMixin._load_settings(self.core)
        reloaded = ModelContextMixin._load_settings(self.core)
        for values in (loaded, reloaded, json.loads(self.path.read_text(encoding="utf-8"))):
            self.assertEqual(values["api_mode"], original["api_mode"])
            self.assertEqual(values["favorite_models"], original["favorite_models"])
            self.assertTrue(values["ui_preferences"]["custom_preference"])
            self.assertTrue(values["legal_acceptance"]["accepted"])
            self.assertEqual(values["legal_acceptance"]["version"], LEGAL_AGREEMENT_VERSION)
        backups = list(self.path.parent.glob("smarti_settings.backup.*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), original)

    def test_invalid_file_stops_loading_and_preserves_its_exact_contents(self):
        for invalid in (b'{"truncated":', b"null", b"[]", b"invalid utf8 \xff"):
            with self.subTest(invalid=invalid):
                self.path.write_bytes(invalid)
                with self.assertRaises(RuntimeError):
                    ModelContextMixin._load_settings(self.core)
                self.assertEqual(self.path.read_bytes(), invalid)

    def test_migration_save_failure_does_not_return_defaults(self):
        original = b'{"settings_schema_version": 2, "api_mode": "openai"}'
        self.path.write_bytes(original)
        self.core._save_settings = mock.Mock(side_effect=PermissionError("locked"))
        with self.assertRaises(RuntimeError):
            ModelContextMixin._load_settings(self.core)
        self.assertEqual(self.path.read_bytes(), original)

    def test_interrupted_replace_keeps_original_and_backup_and_cleans_temp_file(self):
        original = b'{"user_setting": "keep"}'
        self.path.write_bytes(original)

        def fail_replace(source, destination):
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(json.loads(Path(source).read_text(encoding="utf-8")), {"new": True})
            raise PermissionError("interrupted replace")

        with mock.patch("smarti.managers.os.replace", side_effect=fail_replace):
            with self.assertRaises(PermissionError):
                self.manager.save({"new": True})
        self.assertEqual(self.path.read_bytes(), original)
        backups = list(self.path.parent.glob("smarti_settings.backup.*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".smarti-settings-*.tmp")), [])

    def test_later_saves_do_not_replace_the_startup_backup(self):
        self.path.write_text('{"original": true}', encoding="utf-8")
        self.manager.save({"first": True})
        self.manager.save({"second": True})
        backups = list(self.path.parent.glob("smarti_settings.backup.*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), {"original": True})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"second": True})

    def test_save_refuses_to_overwrite_damaged_settings(self):
        self.path.write_bytes(b"{broken")
        with self.assertRaises(ValueError):
            self.manager.save(DEFAULT_SETTINGS)
        self.assertEqual(self.path.read_bytes(), b"{broken")

    def test_runtime_save_uses_atomic_manager_and_preserves_consent(self):
        self.path.write_text('{"original": true}', encoding="utf-8")
        self.core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.core.settings["legal_acceptance"] = {"accepted": True, "version": LEGAL_AGREEMENT_VERSION}
        self.core._sync_ssl_compat_env = mock.Mock()
        with mock.patch("smarti.agent.model_context.get_keyring_module", return_value=None):
            ModelContextMixin._save_settings(self.core)
        self.assertTrue(json.loads(self.path.read_text(encoding="utf-8"))["legal_acceptance"]["accepted"])
        self.assertEqual(len(list(self.path.parent.glob("smarti_settings.backup.*.json"))), 1)

    def test_first_run_still_creates_defaults_without_accepted_consent(self):
        loaded = ModelContextMixin._load_settings(self.core)
        self.assertFalse(loaded["legal_acceptance"]["accepted"])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), loaded)


class SettingsSynchronizationTests(unittest.TestCase):
    def test_codex_check_uses_selected_model_and_does_not_save_failed_connection(self):
        from smarti.codex_signin import CodexConnectionStatus
        with tempfile.TemporaryDirectory() as directory:
            core = fixtures._FakeCore(Path(directory) / "history.json")
            core.settings["selected_openai_codex_signin_model"] = "gpt-6-luna"
            core._save_settings = mock.Mock()
            core.setup_model = mock.Mock()
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            request = fixtures.LocalGatewayTests._request
            provider = mock.Mock()
            provider.check_connection.side_effect = [
                CodexConnectionStatus("unavailable", "Model rejected", "chatgpt"),
                CodexConnectionStatus("connected", "OK", "chatgpt"),
            ]
            try:
                with mock.patch("smarti.codex_signin.CodexSignInProvider", return_value=provider):
                    _, _, failed = request(gateway, "/v2/management/settings/actions", method="POST",
                                           payload={"action": "codex_check"})
                    self.assertEqual(failed["data"]["state"], "unavailable")
                    self.assertEqual(core.settings["api_mode"], "local")
                    core._save_settings.assert_not_called()
                    core.setup_model.assert_not_called()
                    _, _, checked = request(gateway, "/v2/management/settings/actions", method="POST",
                                            payload={"action": "codex_check"})
                    self.assertEqual(checked["data"]["state"], "connected")
                provider.check_connection.assert_has_calls([mock.call(model="gpt-6-luna")] * 2)
                self.assertEqual(core.settings["api_mode"], "openai_codex_signin")
                core._save_settings.assert_called_once()
                core.setup_model.assert_called_once()
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_voice_numeric_settings_privacy_alias_and_nested_fields_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            core = fixtures._FakeCore(Path(directory) / "history.json")
            core.settings = copy.deepcopy(DEFAULT_SETTINGS)
            core.settings["ui_preferences"]["keep"] = "existing"
            path = Path(directory) / "settings.json"
            manager = SettingsManager(str(path), DEFAULT_SETTINGS)

            def save():
                manager.sync_legacy_aliases(core.settings)
                path.write_text(json.dumps(core.settings), encoding="utf-8")

            core._save_settings = save
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            request = fixtures.LocalGatewayTests._request
            try:
                for values in [
                    {"voice_pause_threshold": 1, "voice_ambient_noise_duration": 0, "tts_volume": 1},
                    {"ui_preferences": {"theme_mode": "light"}, "budgets": {"daily_token_budget": 5000}},
                    {"ui_preferences": {"settings_show_advanced": True}, "budgets": {"daily_cost_budget_usd": 2.5}},
                    {"privacy_redact_logs": False, "read_aloud_all": True, "read_aloud_voice_only": False},
                ]:
                    request(gateway, "/v2/settings", method="PATCH", payload={"values": values})
                saved = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(saved["voice_pause_threshold"], 1.0)
                self.assertEqual(saved["voice_ambient_noise_duration"], 0.0)
                self.assertEqual(saved["tts_volume"], 1)
                self.assertTrue(saved["read_aloud_all"])
                self.assertFalse(saved["read_aloud_voice_only"])
                self.assertFalse(manager.sync_legacy_aliases(saved)["privacy_redact_logs"])
                self.assertEqual(saved["ui_preferences"]["theme_mode"], "light")
                self.assertEqual(saved["ui_preferences"]["keep"], "existing")
                self.assertTrue(saved["ui_preferences"]["settings_show_advanced"])
                self.assertEqual(saved["budgets"]["daily_token_budget"], 5000)
                self.assertEqual(saved["budgets"]["daily_cost_budget_usd"], 2.5)
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    request(gateway, "/v2/settings", method="PATCH", payload={"values": {"tts_volume": True}})
                self.assertEqual(rejected.exception.code, 400)
                self.assertEqual(core.settings["tts_volume"], 1)
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_bootstrap_uses_saved_provider_and_model_before_and_after_settings_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            core = fixtures._FakeCore(Path(directory) / "history.json")
            # A cached runtime provider must not override the configured choice.
            core.mode = "gemini"
            core._save_settings = mock.Mock()
            core.setup_model = mock.Mock()
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            request = fixtures.LocalGatewayTests._request
            try:
                _, _, initial = request(gateway, "/v2/bootstrap")
                self.assertEqual(initial["data"]["chat_models"]["provider"], "local")
                self.assertEqual(initial["data"]["chat_models"]["model"], "model-a")
                _, _, saved = request(
                    gateway, "/v2/settings", method="PATCH",
                    payload={"values": {
                        "api_mode": "openai_codex_signin",
                        "selected_openai_codex_signin_model": "gpt-6-astra",
                    }}, headers={"Idempotency-Key": "settings-provider-model"},
                )
                core._save_settings.assert_called_once()
                core.setup_model.assert_called_once()
                request(
                    gateway, "/v2/providers/openai_codex_signin/reasoning", method="POST",
                    payload={"model": "gpt-6-astra", "effort": "high"},
                    headers={"Idempotency-Key": "settings-reasoning"},
                )
                _, _, refreshed = request(gateway, "/v2/bootstrap")
                chat = refreshed["data"]["chat_models"]
                self.assertEqual(chat["provider"], saved["data"]["values"]["api_mode"])
                self.assertEqual(chat["model"], "gpt-6-astra")
                self.assertEqual(chat["reasoning_effort"], "high")
                self.assertIn("high", {item["value"] for item in chat["reasoning_options"]})
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
