import tempfile
import copy
import json
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

from smarti.local_gateway import SmartiLocalGateway
from smarti.run_manager import ConversationRunManager
from smarti.config import DEFAULT_SETTINGS
from smarti.managers import SettingsManager
from tests import test_conversation_runs as fixtures


class SettingsSynchronizationTests(unittest.TestCase):
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
