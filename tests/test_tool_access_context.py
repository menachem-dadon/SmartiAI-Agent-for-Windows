"""Effective Core capability facts, independent of provider-native tool availability."""
import copy
import json
import unittest
from unittest import mock

from tests.test_context_efficiency import _prompt_core


def snapshot(text):
    return json.loads(text.split("[SMARTI_TOOL_ACCESS]\n", 1)[1].split("\n[/SMARTI_TOOL_ACCESS]", 1)[0])


def policy(data, capability):
    baseline = data["policy_baseline"]
    return baseline["overrides"].get(capability, baseline["default"])


class ToolAccessContextTests(unittest.TestCase):
    def test_autonomous_core_reports_write_and_shell_despite_codex_provider(self):
        core = _prompt_core({"get_tool_info", "file_manager", "system_manager"})
        core.settings.update(permission_level=3, autonomy_mode="max_autonomy", sandbox_enabled=False)
        before = copy.deepcopy(core.settings)
        data = snapshot(core._load_system_prompt())
        self.assertEqual(data["executor"], "SmartiAI Core")
        self.assertEqual(set(data["enabled_builtin_tools"]), {"get_tool_info", "file_manager", "system_manager"})
        self.assertEqual(policy(data, "file_write"), "allow")
        self.assertEqual(policy(data, "shell"), "allow")
        self.assertEqual(data["filesystem_scope"], {"sandbox_enabled": False})
        self.assertEqual(core.settings, before)

    def test_safe_mode_and_explicit_denial_are_preserved(self):
        core = _prompt_core({"get_tool_info", "file_manager"})
        core.settings.update(permission_level=1, policy_matrix={"file_write": "allow", "shell": "deny"})
        data = snapshot(core._tool_access_context())
        self.assertEqual(policy(data, "file_write"), "ask")
        self.assertEqual(policy(data, "shell"), "deny")

    def test_effective_runtime_policy_is_used_instead_of_settings_only(self):
        core = _prompt_core({"get_tool_info", "file_manager"})
        core.settings.update(permission_level=3, policy_matrix={"file_write": "allow"})
        core.policy_engine = mock.Mock()
        core.policy_engine.decision.side_effect = lambda capability: "deny" if capability == "file_write" else "ask"
        self.assertEqual(policy(snapshot(core._tool_access_context()), "file_write"), "deny")

    def test_scope_and_disabled_tools_refresh_in_all_prompt_profiles(self):
        core = _prompt_core({"get_tool_info", "search_tools", "file_manager", "system_manager"})
        for provider, fast in (("openai_codex_signin", False), ("openai", False), ("local", True)):
            with self.subTest(provider=provider, fast=fast):
                core.settings.update(api_mode=provider, local_fast_mode_enabled=fast,
                                     sandbox_enabled=True, sandbox_root_dir="C:\\SmartiSandbox",
                                     sandbox_allow_read_outside=True)
                with mock.patch.object(core, "_sandbox_root", return_value="C:\\SmartiSandbox"):
                    data = snapshot(core._load_system_prompt())
                self.assertEqual(data["filesystem_scope"], {
                    "sandbox_enabled": True, "root": "C:\\SmartiSandbox", "allow_read_outside": True,
                })
                core.settings["tools_config"]["file_manager"] = False
                self.assertNotIn("file_manager", snapshot(core._load_system_prompt())["enabled_builtin_tools"])
                core.settings["tools_config"]["file_manager"] = True


if __name__ == "__main__":
    unittest.main()
