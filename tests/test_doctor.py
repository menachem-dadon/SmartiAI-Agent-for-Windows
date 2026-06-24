"""Focused contract tests for Smarti Doctor's local diagnostics."""
import copy
import json
import os
import tempfile
import unittest
from unittest import mock

from smarti import doctor
from smarti.config import DEFAULT_POLICY_MATRIX


class _Core:
    def __init__(self):
        self.settings = {
            "api_mode": "local",
            "selected_local_model": "local-test-model",
            "local_server_url": "http://127.0.0.1:1234/v1",
            "enable_browser_automation": False,
            "enable_visual_surfaces": False,
            "enable_web_canvas": False,
            "voice_hotkey": "",
            "read_aloud_all": False,
            "enable_mcp_clawhub": False,
            "enable_skills_beta": False,
            "policy_matrix": copy.deepcopy(DEFAULT_POLICY_MATRIX),
            "tool_trust": {},
        }

    def _allow_insecure_ssl(self):
        return False

    def _save_settings(self):
        return None

    def setup_model(self):
        return None


class SmartiDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.originals = {
            name: getattr(doctor, name)
            for name in (
                "USER_DATA_DIR", "SETTINGS_FILE", "MEMORY_FILE", "CHAT_HISTORY_FILE",
                "USAGE_FILE", "ACTIVE_TASK_CHECKPOINT_FILE", "MCP_CONFIG_FILE", "AUDIT_LOG_FILE",
                "MCP_TOOLS_DIR", "SKILLS_DIR", "TOOLS_DIR", "ATTACHMENTS_DIR", "OUTPUTS_DIR",
            )
        }
        root = self.temp.name
        doctor.USER_DATA_DIR = root
        doctor.SETTINGS_FILE = os.path.join(root, "smarti_settings.json")
        doctor.MEMORY_FILE = os.path.join(root, "smarti_memory.json")
        doctor.CHAT_HISTORY_FILE = os.path.join(root, "smarti_chats.json")
        doctor.USAGE_FILE = os.path.join(root, "smarti_usage.json")
        doctor.ACTIVE_TASK_CHECKPOINT_FILE = os.path.join(root, "active_task_checkpoint.json")
        doctor.MCP_CONFIG_FILE = os.path.join(root, "mcp_config.json")
        doctor.AUDIT_LOG_FILE = os.path.join(root, "smarti_audit.log")
        doctor.MCP_TOOLS_DIR = os.path.join(root, "mcp_tools")
        doctor.SKILLS_DIR = os.path.join(root, "skills")
        doctor.TOOLS_DIR = os.path.join(root, "custom_tools")
        doctor.ATTACHMENTS_DIR = os.path.join(root, "attachments")
        doctor.OUTPUTS_DIR = os.path.join(root, "outputs")
        os.makedirs(doctor.ATTACHMENTS_DIR)
        os.makedirs(doctor.OUTPUTS_DIR)
        self.core = _Core()

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(doctor, name, value)
        self.temp.cleanup()

    def _write_json(self, path, payload):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_check_result_serializes_without_secret_values(self):
        instance = doctor.SmartiDoctor(self.core)
        result = instance._result(
            "provider.test", doctor.STATUS_ERROR, "תקלה", "api_key=very-secret-value",
            category="providers", title_he="ספק",
        )
        self.assertEqual(result.to_dict()["id"], "provider.test")
        with open(instance.log_path, "r", encoding="utf-8") as handle:
            logged = handle.read()
        self.assertNotIn("very-secret-value", logged)
        self.assertIn("[REDACTED]", logged)

    def test_invalid_json_is_reported_with_an_explicit_repair(self):
        with open(doctor.SETTINGS_FILE, "w", encoding="utf-8") as handle:
            handle.write("{broken")
        result = doctor.SmartiDoctor(self.core).check_data_files()
        self.assertEqual(result.status, doctor.STATUS_ERROR)
        self.assertIsNotNone(result.repair_action)
        self.assertEqual(result.repair_action.id, "open_data_folder")

    def test_backup_repair_creates_a_local_zip(self):
        self._write_json(doctor.SETTINGS_FILE, {"settings_schema_version": 2})
        self._write_json(doctor.MEMORY_FILE, {"entries": []})
        message = doctor.SmartiDoctor(self.core).perform_repair("create_backup")
        self.assertIn("נוצר גיבוי", message)
        self.assertTrue(any(name.endswith(".zip") for name in os.listdir(self.temp.name)))

    def test_provider_check_loads_a_secret_from_the_canonical_core_path(self):
        class ProviderCore(_Core):
            def __init__(self):
                super().__init__()
                self.settings.update({
                    "api_mode": "openai",
                    "selected_openai_model": "gpt-test",
                    "openai_api_key": "",
                })
                self.loaded_provider = ""

            def ensure_provider_secret(self, provider):
                self.loaded_provider = provider
                return "credential-manager-secret"

        core = ProviderCore()
        result = doctor.SmartiDoctor(core).check_provider(include_network=False)
        self.assertEqual(result.status, doctor.STATUS_PASS)
        self.assertEqual(core.loaded_provider, "openai")
        self.assertIn("api_key_configured=True", result.technical_detail)

    def test_email_check_uses_the_same_resolved_config_as_the_mail_tool(self):
        class EmailCore(_Core):
            def _email_config(self):
                return {
                    "user": "person@example.com",
                    "password": "app-password",
                    "imap_host": "imap.example.com",
                    "imap_port": 993,
                    "imap_ssl": True,
                    "smtp_host": "smtp.example.com",
                    "smtp_port": 587,
                    "smtp_ssl": False,
                    "smtp_starttls": True,
                }

        result = doctor.SmartiDoctor(EmailCore()).check_email(include_network=False)
        self.assertEqual(result.status, doctor.STATUS_PASS)
        self.assertNotIn("app-password", result.technical_detail)

    def test_browser_probe_closes_a_browser_started_only_for_doctor(self):
        class BrowserCore(_Core):
            def __init__(self):
                super().__init__()
                self.settings["enable_browser_automation"] = True
                self.closed = False

            def _chrome_executable(self):
                return "C:/Program Files/Google/Chrome/Application/chrome.exe"

            def _automation_browser_profile_dir(self):
                return os.path.join(tempfile.gettempdir(), "SmartiDoctorTestProfile")

            def _automation_browser_is_ready(self):
                return False

            def _ensure_automation_browser(self):
                return False, "test startup failure"

            def _close_automation_browser(self):
                self.closed = True

        core = BrowserCore()
        with mock.patch.object(doctor.importlib.util, "find_spec", return_value=object()):
            result = doctor.SmartiDoctor(core).check_browser(include_network=True)
        self.assertEqual(result.status, doctor.STATUS_ERROR)
        self.assertTrue(core.closed)

    def test_search_check_offers_a_separate_live_probe_without_spending_quota(self):
        class SearchCore(_Core):
            def __init__(self):
                super().__init__()
                self.settings["tools_config"] = {
                    "internet_search": True,
                    "smart_file_search": True,
                    "deep_content_search": True,
                }

            def _ensure_secret_loaded(self, key):
                return "tavily-secret" if key == "tavily_api_key" else ""

            def _sandbox_enabled(self):
                return False

        result = doctor.SmartiDoctor(SearchCore()).check_search()
        self.assertEqual(result.status, doctor.STATUS_PASS)
        self.assertEqual(result.repair_action.id, "test_search_connection")

    def test_memory_expiry_is_reported_and_uses_the_memory_manager_for_repair(self):
        self._write_json(doctor.MEMORY_FILE, {
            "entries": [{"id": "expired", "type": "short_term", "expires_at": "2001-01-01T00:00:00"}],
        })

        class MemoryManager:
            def __init__(self):
                self.called = False

            def prune_expired(self):
                self.called = True
                return 1

        self.core.memory_manager = MemoryManager()
        instance = doctor.SmartiDoctor(self.core)
        result = instance.check_memory_health()
        self.assertEqual(result.status, doctor.STATUS_WARNING)
        self.assertEqual(result.repair_action.id, "prune_expired_memory")
        instance.perform_repair("prune_expired_memory")
        self.assertTrue(self.core.memory_manager.called)

    def test_plaintext_secret_audit_never_includes_the_secret_value(self):
        self._write_json(doctor.SETTINGS_FILE, {"openai_api_key": "very-secret-value"})
        result = doctor.SmartiDoctor(self.core).check_secret_storage()
        self.assertEqual(result.status, doctor.STATUS_WARNING)
        self.assertEqual(result.repair_action.id, "secure_plaintext_secrets")
        self.assertNotIn("very-secret-value", result.technical_detail)

    def test_disabled_browser_with_a_running_smarti_profile_offers_a_scoped_close(self):
        class BrowserCore(_Core):
            def _chrome_executable(self):
                return "C:/Program Files/Google/Chrome/Application/chrome.exe"

            def _automation_browser_profile_dir(self):
                return tempfile.gettempdir()

            def _automation_browser_is_ready(self):
                return True

        with mock.patch.object(doctor.importlib.util, "find_spec", return_value=object()):
            result = doctor.SmartiDoctor(BrowserCore()).check_browser(include_network=False)
        self.assertEqual(result.status, doctor.STATUS_WARNING)
        self.assertEqual(result.repair_action.id, "close_orphaned_browser")

    def test_mcp_node_runtime_requires_node_npm_and_npx_from_the_mcp_environment(self):
        class McpCore(_Core):
            def __init__(self):
                super().__init__()
                self.settings["enable_mcp_clawhub"] = True

            def _mcp_env(self):
                return {"PATH": ""}

        with mock.patch.object(doctor.shutil, "which", return_value=None):
            result = doctor.SmartiDoctor(McpCore()).check_mcp_node_runtime()
        self.assertEqual(result.status, doctor.STATUS_ERROR)
        self.assertEqual(result.repair_action.id, "disable_mcp")
        self.assertIn("npx_found=False", result.technical_detail)

    def test_mcp_catalog_names_the_specific_broken_descriptor(self):
        os.makedirs(doctor.MCP_TOOLS_DIR)
        with open(os.path.join(doctor.MCP_TOOLS_DIR, "broken-package.txt"), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        result = doctor.SmartiDoctor(self.core).check_mcp_catalog()
        self.assertEqual(result.status, doctor.STATUS_WARNING)
        self.assertIn("broken-package.txt", result.explanation_he)
        self.assertEqual(result.repair_action.id, "open_tools")

    def test_custom_tool_syntax_result_names_the_specific_tool(self):
        os.makedirs(doctor.TOOLS_DIR)
        with open(os.path.join(doctor.TOOLS_DIR, "my_tool.py"), "w", encoding="utf-8") as handle:
            handle.write("def broken(:\n")
        result = doctor.SmartiDoctor(self.core).check_custom_tools()
        self.assertEqual(result.status, doctor.STATUS_WARNING)
        self.assertIn("my_tool.py", result.explanation_he)
        self.assertTrue(result.explanation_he.startswith("כלים"))

    def test_single_skill_with_published_requirements_offers_explicit_install(self):
        class SkillCore(_Core):
            def __init__(self):
                super().__init__()
                self.settings["enable_skills_beta"] = True
                self.skill_registry = {"calendar": {"name": "calendar"}}
                self.installed = ""

            def _skill_dependency_status(self, spec):
                return {"missing_bins": ["cal-bin"], "install_entries": [{"kind": "pip", "package": "cal-bin"}]}

            def install_skill_requirements(self, name, reason=""):
                self.installed = f"{name}:{reason}"
                return "SUCCESS: installed"

        core = SkillCore()
        instance = doctor.SmartiDoctor(core)
        result = instance.check_skill_dependencies()
        self.assertEqual(result.status, doctor.STATUS_WARNING)
        self.assertEqual(result.repair_action.id, "install_skill_requirements:calendar")
        self.assertTrue(result.title_he.startswith("תלויות"))
        self.assertIn("יכולת calendar", result.explanation_he)
        instance.perform_repair(result.repair_action.id)
        self.assertIn("calendar", core.installed)

    def test_security_flags_disabled_log_redaction_with_a_safe_repair(self):
        self.core.settings["privacy_redact_logs"] = False
        self.core.settings["privacy"] = {"redact_logs": False}
        result = doctor.SmartiDoctor(self.core).check_security()
        self.assertEqual(result.status, doctor.STATUS_WARNING)
        self.assertEqual(result.repair_action.id, "enable_log_redaction")
        doctor.SmartiDoctor(self.core).perform_repair("enable_log_redaction")
        self.assertTrue(self.core.settings["privacy_redact_logs"])

    def test_full_local_run_has_no_sqlite_check(self):
        results = doctor.SmartiDoctor(self.core).run(include_network=False)
        result_ids = {result.id for result in results}
        self.assertIn("search.runtime", result_ids)
        self.assertIn("memory.health", result_ids)
        self.assertIn("runtime.python", result_ids)
        self.assertIn("settings.schema", result_ids)
        self.assertIn("security.secrets", result_ids)
        self.assertIn("mcp.node_runtime", result_ids)
        self.assertIn("mcp.catalog", result_ids)
        self.assertIn("extensions.custom_tools", result_ids)
        self.assertIn("extensions.skills", result_ids)
        self.assertNotIn("data.sqlite", result_ids)


if __name__ == "__main__":
    unittest.main()
