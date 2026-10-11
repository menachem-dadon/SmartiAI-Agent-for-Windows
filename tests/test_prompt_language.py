import copy
import ast
import json
import re
import string
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.config import BUILTIN_TOOL_SCHEMAS, DEFAULT_SETTINGS, PUBLIC_BUILTIN_TOOLS, TOOL_ACTION_FIELDS
from smarti.local_gateway import SmartiLocalGateway
from smarti.desktop_services import settings_schema_document
from smarti.managers import SettingsManager
from smarti.prompt_language import ENGLISH, LANGUAGE_POLICY, builtin_schemas, prompt_language
from smarti.run_manager import ConversationRunManager
from tests.test_context_efficiency import _prompt_core
from tests import test_conversation_runs as fixtures


def without_annotations(value):
    if isinstance(value, dict):
        return {key: without_annotations(item) for key, item in value.items()
                if not (key in {"description", "title"} and isinstance(item, str))}
    if isinstance(value, list):
        return [without_annotations(item) for item in value]
    return value


class PromptLanguageTests(unittest.TestCase):
    def test_system_language_is_fixed_and_migration_discards_obsolete_preference(self):
        self.assertNotIn("system_prompt_language", DEFAULT_SETTINGS)
        self.assertEqual(prompt_language({}), "en")
        with tempfile.TemporaryDirectory() as directory:
            manager = SettingsManager(str(Path(directory) / "settings.json"), DEFAULT_SETTINGS)
            for language in ("en", "he"):
                settings, changed = manager.migrate_or_merge({"system_prompt_language": language})
                self.assertNotIn("system_prompt_language", settings)
                self.assertTrue(changed)
                self.assertEqual(prompt_language({"system_prompt_language": language}), "en")

    def test_all_owned_templates_are_english_with_valid_interpolation_slots(self):
        formatter = string.Formatter()
        for key, english in ENGLISH.items():
            with self.subTest(template=key):
                self.assertNotRegex(english, r"[\u0590-\u05ff]")
                if re.search(r"\{\d+(?:[!}:])", english):
                    fields = [name for _, name, _, _ in formatter.parse(english) if name is not None]
                    self.assertTrue(all(name.isdigit() for name in fields))

    def test_all_prompt_calls_have_both_translations_including_error_paths(self):
        root = Path(__file__).resolve().parents[1] / "smarti" / "agent"
        for path in root.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_prompt_text":
                    key = node.args[0].value
                    self.assertIn(key, ENGLISH, str(path))
        core = _prompt_core({"get_tool_info"}, "en")
        self.assertEqual(core._schema_for_requested_action("custom", {"properties": []}, "full"),
                         ({"properties": []}, "full", None))
        core._canonical_schema_action = lambda *args: ("read", None)
        _, _, error = core._schema_for_requested_action("custom", {"properties": []}, "read")
        self.assertEqual(error, ENGLISH["schema_for_requested_action_text_1"])

    def test_complete_schema_structures_and_action_scopes_are_unchanged(self):
        original = copy.deepcopy(BUILTIN_TOOL_SCHEMAS)
        core = _prompt_core(set(PUBLIC_BUILTIN_TOOLS) | {"agent_planner"}, "en")
        for language in ("en", "he"):
            localized = builtin_schemas(language)
            self.assertEqual(without_annotations(localized), without_annotations(original))
            for name, action_map in TOOL_ACTION_FIELDS.items():
                for action in action_map:
                    with self.subTest(language=language, tool=name, action=action):
                        translated, actual, error = core._schema_for_requested_action(name, localized[name]["inputSchema"], action)
                        expected, expected_action, expected_error = core._schema_for_requested_action(name, original[name]["inputSchema"], action)
                        self.assertEqual((actual, error), (expected_action, expected_error))
                        self.assertEqual(without_annotations(translated), without_annotations(expected))
        self.assertEqual(BUILTIN_TOOL_SCHEMAS, original)
        self.assertNotRegex(json.dumps(builtin_schemas("en"), ensure_ascii=False), r"[\u0590-\u05ff]")

    def test_all_prompt_branches_are_english_and_keep_language_policy_and_capabilities(self):
        active = set(PUBLIC_BUILTIN_TOOLS) | {"agent_planner"}
        core = _prompt_core(active, "en")
        core.settings["enable_mcp_clawhub"] = True
        core._get_existing_python_tools = lambda: ["sample_python"]
        core._get_existing_mcp_tools = lambda: ["sample_mcp"]
        core._get_existing_skills = lambda: ["sample_skill"]
        core._is_background_context = lambda: True
        with mock.patch("smarti.agent.model_context.os.getcwd", return_value="C:\\Example"):
            for provider in ("openai", "gemini", "anthropic", "openai_codex_signin", "openrouter", "local"):
                for fast in (False, True):
                    for skills in (False, True):
                        for remote_images in (False, True):
                            with self.subTest(provider=provider, fast=fast, skills=skills, remote_images=remote_images):
                                core.mode = provider
                                core.settings.update(api_mode=provider, local_fast_mode_enabled=fast,
                                                     enable_skills_beta=skills, enable_canvas_remote_images=remote_images)
                                prompt = core._load_system_prompt()
                                self.assertNotRegex(prompt, r"[\u0590-\u05ff]")
                                self.assertTrue(prompt.startswith(LANGUAGE_POLICY))
                                self.assertIn("Switch only when the user", prompt)
                                self.assertIn("progress reports", prompt)
                                for tool in active:
                                    self.assertIn(f"`{tool}`", prompt)
                                if provider != "local" or not fast:
                                    self.assertIn('<smarti_memory>{"operations":[]}</smarti_memory>', prompt)
                                else:
                                    self.assertNotIn('<smarti_memory>', prompt)

    def test_runtime_user_data_and_external_skill_text_remain_exact(self):
        core = _prompt_core({"get_tool_info", "file_manager"}, "en")
        data = 'המשתמש מעדיף עברית; {0}; C:\\מסמכים\\קובץ.txt; "action":"read_chunk"'
        core.conversation_summary = data
        core.memory_manager = SimpleNamespace(build_prompt_context=lambda *args, **kwargs: data)
        core.recent_tool_observations = [data]
        core._tool_context_prompt = lambda *args: data
        prompt = core._load_system_prompt()
        self.assertEqual(prompt.count(data), 4)
        external = {"source": "clawhub", "description": "תיקיית הפרויקט", "instructions": data,
                    "parameters": {"type": "object", "properties": {"שדה": {"type": "string", "enum": ["ערך"]}}}}
        self.assertIs(core._prompt_skill_spec(external), external)
        block = core._loaded_skill_system_context({"sample": data})
        self.assertIn(data, block)

    def test_obsolete_preferences_cannot_restore_hebrew_system_text(self):
        core = _prompt_core(set(PUBLIC_BUILTIN_TOOLS) | {"agent_planner"}, "en")
        state = (core.settings["tools_config"].copy(), core.memory_manager)
        for language in ("en", "he", "en"):
            core.settings["system_prompt_language"] = language
            prompt = core._load_system_prompt()
            self.assertTrue(prompt.startswith(LANGUAGE_POLICY))
            self.assertIn("**Additional tool rules:**", prompt)
            specs = core._native_tool_specs_for_request()
            self.assertEqual(specs[0]["name"], "agent_planner")
            info = core.get_tool_info("get_tool_info", "full")
            self.assertNotRegex(json.dumps(specs, ensure_ascii=False) + info, r"[\u0590-\u05ff]")
        self.assertEqual((core.settings["tools_config"], core.memory_manager), state)

    def test_builtin_skill_catalog_and_guidance_are_english(self):
        core = _prompt_core({"get_tool_info", "extension_manager"}, "en")
        core.skill_registry = core._builtin_skill_specs()
        core._skill_dependency_status = lambda spec: {"missing_bins": [], "installed_bins": [], "install_entries": []}
        for name in core.skill_registry:
            self.assertNotRegex(core.get_skill_info(name, "full"), r"[\u0590-\u05ff]")
        self.assertNotRegex(core._available_skills_block(), r"[\u0590-\u05ff]")
        self.assertNotRegex("\n".join(core._get_existing_skills()), r"[\u0590-\u05ff]")

    def test_memory_envelope_examples_keep_their_json_contract(self):
        envelopes = [json.loads(value) for value in re.findall(r"<smarti_memory>(.*?)</smarti_memory>", ENGLISH["load_system_prompt_memory_policy_1"])]
        self.assertEqual(envelopes[0], {"operations": []})
        operation = envelopes[1]["operations"][0]
        self.assertEqual(operation["action"], "add")
        self.assertEqual(operation["category"], "preference")
        self.assertEqual(operation["scope"], "user")
        self.assertEqual(operation["memory_type"], "user")
        self.assertEqual(operation["recall_policy"], "always")
        self.assertEqual(operation["evidence"], [])

    def test_title_and_internal_output_repair_follow_user_language(self):
        core = _prompt_core({"get_tool_info"}, "en")
        core._handle_api_request_with_retry = mock.Mock(return_value=("Travel itinerary", {}))
        self.assertEqual(core.generate_conversation_title("Plan my trip", "Here is the itinerary"), "Travel itinerary")
        options = core._handle_api_request_with_retry.call_args.kwargs["request_options"]
        self.assertIn("user's conversation language", options["system_prompt"])
        self.assertNotRegex(options["system_prompt"], r"[\u0590-\u05ff]")
        self.assertIn("user language", core._prompt_text("internal_output_repair"))

    def test_replanning_context_is_english_and_preserves_existing_observations(self):
        core = _prompt_core({"agent_planner"}, "en")
        state = core._base_task_state("Review files")
        self.assertNotRegex(core._planner_context_for_replan(state), r"[\u0590-\u05ff]")
        self.assertNotRegex("\n".join(core._fallback_task_plan("Review files")), r"[\u0590-\u05ff]")
        state["observations"] = ["שם הקובץ הוא מסמך.txt {0}"]
        self.assertIn(state["observations"][0], core._planner_context_for_replan(state))
        core.settings["system_prompt_language"] = "he"
        self.assertIn("Planning/replanning reason", core._planner_context_for_replan(state))
        self.assertNotIn("system_prompt_language", settings_schema_document()["fields"])

    def test_gateway_rejects_obsolete_language_setting_without_partial_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            core = fixtures._FakeCore(Path(directory) / "history.json")
            core.settings = copy.deepcopy(DEFAULT_SETTINGS)
            path = Path(directory) / "settings.json"
            manager = SettingsManager(str(path), DEFAULT_SETTINGS)
            core._save_settings = lambda: manager.save(core.settings)
            core._save_settings()
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            self.assertTrue(gateway.start())
            request = fixtures.LocalGatewayTests._request
            before = path.read_bytes()
            old_values = copy.deepcopy(core.settings)
            try:
                for language in ("he", "en", "fr"):
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        request(gateway, "/v2/settings", method="PATCH",
                                payload={"values": {"system_prompt_language": language, "max_agent_loops": 12}})
                    self.assertEqual(rejected.exception.code, 400)
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(core.settings, old_values)
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)
