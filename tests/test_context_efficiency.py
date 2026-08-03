import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

from smarti.codex_signin import CodexSignInProvider
from smarti.common import markdown_to_plain_text
from smarti.config import (
    BUILTIN_TOOL_SCHEMAS,
    DEFAULT_SETTINGS,
    PUBLIC_BUILTIN_TOOLS,
    TOOL_ACTION_FIELDS,
)
from smarti.core import SmartiCore
from smarti.history import ChatSessionStore


class _MemoryPromptStub:
    def build_prompt_context(self, query, log_usage=False):
        return "Memory policy: no relevant active memory was retrieved."


class _InlineExecutor:
    def submit(self, callback):
        callback()


class _JsonResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def _prompt_core(active_tools):
    core = SmartiCore.__new__(SmartiCore)
    core.settings = copy.deepcopy(DEFAULT_SETTINGS)
    core.settings["api_mode"] = "openai_codex_signin"
    core.settings["enable_visual_surfaces"] = True
    core.settings["enable_web_canvas"] = True
    core.settings["enable_browser_automation"] = True
    core.settings["enable_computer_control"] = True
    core.settings["enable_hierarchical_agent"] = "agent_planner" in active_tools
    core.settings["tools_config"] = {
        name: name in active_tools
        for name in PUBLIC_BUILTIN_TOOLS
    }
    core.memory_manager = _MemoryPromptStub()
    core.conversation_attachments = []
    core.recent_tool_observations = []
    core.mode = "openai_codex_signin"
    core.active_canvas_artifacts = lambda: []
    core._tool_context_prompt = lambda query: "No retained tool transcript."
    core._default_output_dir = lambda: "C:\\SmartiOutput"
    core._available_skills_block = lambda: "<available_skills><none /></available_skills>"
    core._get_existing_python_tools = lambda: []
    core._get_existing_mcp_tools = lambda: []
    core._get_existing_skills = lambda: []
    core._is_background_context = lambda: False
    return core


def _request_core(mode):
    core = SmartiCore.__new__(SmartiCore)
    core.mode = mode
    core.settings = copy.deepcopy(DEFAULT_SETTINGS)
    core.system_prompt = "stable system"
    core.status_callback = None
    core._raise_if_cancelled = lambda: None
    core._prepare_messages_for_budget = lambda model, messages, **kwargs: messages
    core._run_cancelable_callable = lambda callback: callback()
    core._ensure_secret_loaded = lambda key: "test-key"
    core._universal_client_key = "test-key"
    return core


class ContextEfficiencyTests(unittest.TestCase):
    def test_get_tool_info_action_is_model_required_but_backward_compatible(self):
        schema = BUILTIN_TOOL_SCHEMAS["get_tool_info"]["inputSchema"]

        self.assertIn("action", schema["properties"])
        self.assertEqual(schema["required"], ["tool_name"])
        self.assertIn("המודל חייב לשלוח", schema["properties"]["action"]["description"])

    def test_get_tool_info_missing_or_full_returns_the_original_full_schema(self):
        core = _prompt_core({"get_tool_info", "file_manager"})

        legacy = core.get_tool_info("file_manager")
        explicit_full = core.get_tool_info("file_manager", "full")

        self.assertEqual(legacy, explicit_full)
        self.assertIn("סכמת JSON חוקית ומלאה", legacy)
        self.assertIn('"operations"', legacy)

    def test_get_tool_info_returns_a_small_action_scoped_schema(self):
        core = _prompt_core({"get_tool_info", "file_manager"})

        full = core.get_tool_info("file_manager", "full")
        scoped = core.get_tool_info("file_manager", "read_chunk")

        self.assertIn("action=read_chunk", scoped)
        self.assertIn('"enum": [\n        "read_chunk"', scoped)
        self.assertIn('"encoding"', scoped)
        self.assertIn('"offset"', scoped)
        self.assertNotIn('"operations"', scoped)
        self.assertLess(len(scoped), len(full) // 5)

    def test_every_registered_manager_action_has_a_valid_scoped_field_map(self):
        for tool_name, action_map in TOOL_ACTION_FIELDS.items():
            schema = BUILTIN_TOOL_SCHEMAS[tool_name]["inputSchema"]
            properties = schema["properties"]
            actions = set(properties["action"]["enum"])
            self.assertEqual(actions, set(action_map), tool_name)
            for action, fields in action_map.items():
                with self.subTest(tool=tool_name, action=action):
                    self.assertTrue(set(fields).issubset(properties))

    def test_get_tool_info_rejects_unknown_action_instead_of_silently_returning_full(self):
        core = _prompt_core({"get_tool_info", "file_manager"})

        info = core.get_tool_info("file_manager", "not_a_real_action")

        self.assertTrue(info.startswith("ERROR:"))
        self.assertIn("search_files", info)
        self.assertIn("action='full'", info)

    def test_get_tool_info_selects_one_mcp_function_by_action(self):
        core = SmartiCore.__new__(SmartiCore)
        core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        core.settings["enable_mcp_clawhub"] = True
        core.tool_registry = SimpleNamespace(trust_status=lambda *args: "trusted")
        core._resolve_mcp_package = lambda requested: str(requested)
        payload = [
            {"name": "lookup", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}},
            {"name": "publish", "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}}},
        ]

        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "demo-package.txt").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            with mock.patch("smarti.agent.model_context.MCP_TOOLS_DIR", directory):
                scoped = core.get_tool_info("demo-package", "lookup")
                full = core.get_tool_info("demo-package", "full")

        self.assertIn("function=lookup", scoped)
        self.assertIn('"lookup"', scoped)
        self.assertNotIn('"publish"', scoped)
        self.assertIn('"publish"', full)

    def test_system_prompt_requires_tool_name_and_action_for_every_schema_lookup(self):
        core = _prompt_core({"get_tool_info", "file_manager"})

        prompt = core._load_system_prompt("מצא קובץ")

        self.assertIn("בכל קריאת `get_tool_info` חובה לשלוח גם `tool_name` וגם `action`", prompt)
        self.assertIn("השמטת action עדיין מחזירה את הסכמה המלאה", prompt)

    def test_local_fast_mode_halves_the_fixed_contract_without_hiding_capabilities(self):
        active = set(PUBLIC_BUILTIN_TOOLS) | {"agent_planner"}
        core = _prompt_core(active)
        core.settings["api_mode"] = "local"
        core.mode = "local"
        core._get_existing_python_tools = lambda: ["csv_helper", "image_helper"]
        core._get_existing_mcp_tools = lambda: ["demo-mcp"]
        core._get_existing_skills = lambda: ["special-workflow"]

        core.settings["local_fast_mode_enabled"] = False
        normal_prompt = core._load_system_prompt("בצע משימה")
        core.settings["local_fast_mode_enabled"] = True
        fast_prompt = core._load_system_prompt("בצע משימה")

        self.assertLess(len(fast_prompt), len(normal_prompt) * 0.60)
        self.assertIn("FastMode פעיל", fast_prompt)
        self.assertIn("`get_tool_info` schema", fast_prompt)
        self.assertIn("`search_tools` schema", fast_prompt)
        self.assertIn("action=full", fast_prompt)
        self.assertIn("Python tools: 2 installed", fast_prompt)
        self.assertNotIn("csv_helper", fast_prompt)
        self.assertNotIn("special-workflow", fast_prompt)
        for name in PUBLIC_BUILTIN_TOOLS:
            if core._builtin_tool_context_enabled(name):
                self.assertIn(f"`{name}`", fast_prompt)

    def test_fast_mode_never_activates_for_a_nonlocal_provider(self):
        core = _prompt_core({"get_tool_info", "search_tools", "file_manager"})
        core.settings["local_fast_mode_enabled"] = True
        core.settings["api_mode"] = "openai"
        core.mode = "openai"

        self.assertFalse(core._local_fast_mode_enabled())
        self.assertNotIn("FastMode פעיל", core._load_system_prompt("שלום"))

    def test_fast_mode_lists_extension_names_when_catalog_search_is_disabled(self):
        core = _prompt_core({"get_tool_info", "extension_manager"})
        core.settings["api_mode"] = "local"
        core.mode = "local"
        core.settings["local_fast_mode_enabled"] = True
        core.settings["enable_tool_search_catalog"] = False
        core._get_existing_python_tools = lambda: ["csv_helper"]
        core._get_existing_mcp_tools = lambda: ["demo-mcp"]
        core._get_existing_skills = lambda: ["special-workflow"]

        prompt = core._load_system_prompt("בצע משימה")

        self.assertIn("Python tools: csv_helper", prompt)
        self.assertIn("MCP packages: demo-mcp", prompt)
        self.assertIn("Skills: special-workflow", prompt)
        self.assertNotIn("`search_tools` schema", prompt)

    def test_disabled_tool_policies_and_schemas_are_absent(self):
        core = _prompt_core({
            "get_tool_info",
            "system_manager",
            "file_manager",
            "web_manager",
        })

        prompt = core._load_system_prompt("שלום")

        self.assertIn("`system_manager`", prompt)
        self.assertIn("`file_manager`", prompt)
        self.assertIn("`web_manager`", prompt)
        self.assertNotIn("`canvas_manager`", prompt)
        self.assertNotIn("Browser Automation:", prompt)
        self.assertNotIn("`computer_automation_manager`", prompt)
        self.assertNotIn("`background_task_manager`", prompt)
        self.assertNotIn("`notification_manager`", prompt)
        self.assertNotIn("sefaria-mcp-server", prompt)
        self.assertNotIn("למזג אוויר ותחזית השתמש קודם", prompt)
        self.assertNotIn("אל תשתמש ב-`agent_planner` לברכה", prompt)
        self.assertIn("Available Skills Catalog", prompt)
        self.assertLess(len(prompt), 18000)

    def test_canvas_uses_compact_base_policy_but_full_policy_remains_on_demand(self):
        core = _prompt_core({
            "get_tool_info",
            "system_manager",
            "file_manager",
            "web_manager",
            "canvas_manager",
        })
        core.settings["enable_canvas_remote_images"] = False

        prompt = core._load_system_prompt("בנה דשבורד")
        info = core.get_tool_info("canvas_manager")

        self.assertIn("קנבס הוא תוצר חזותי/אינטראקטיבי אופציונלי", prompt)
        self.assertNotIn("אינה פותחת סבב מודל", prompt)
        self.assertIn("אינה פותחת סבב מודל", info)

    def test_codex_microtasks_do_not_receive_the_agent_contract(self):
        provider = CodexSignInProvider.__new__(CodexSignInProvider)
        messages = [
            {"role": "system", "content": "כותרת קצרה בלבד."},
            {"role": "user", "content": "הודעת משתמש ותשובה."},
        ]

        instructions = provider._build_model_instructions(messages, purpose="title")
        prompt = provider._build_prompt(messages, purpose="title")

        self.assertEqual(instructions, "כותרת קצרה בלבד.")
        self.assertEqual(prompt, "הודעת משתמש ותשובה.")
        self.assertNotIn("SMARTIAI AGENT CONTRACT", instructions)
        self.assertNotIn("tools/call", instructions)

    def test_title_request_has_only_title_context_and_no_local_fallback(self):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "gemini"
        core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        core.settings["selected_gemini_model"] = "gemini-test"
        captured = {}
        core._log_usage = lambda *args: None

        def complete(model, messages, retry_wait_times=None, request_options=None):
            captured["model"] = model
            captured["messages"] = messages
            captured["options"] = request_options
            return "  כותרת מדויקת  ", {"prompt": 10, "completion": 2, "total": 12}

        core._handle_api_request_with_retry = complete
        title = core.generate_conversation_title(
            "הודעת משתמש מלאה",
            "תשובה סופית מלאה",
            attachment_names=["מסמך א.docx"],
        )

        self.assertEqual(title, "כותרת מדויקת")
        payload = captured["messages"][0]["parts"][0]["text"]
        self.assertIn("הודעת משתמש מלאה", payload)
        self.assertIn("תשובה סופית מלאה", payload)
        self.assertIn("מסמך א.docx", payload)
        self.assertEqual(captured["options"]["reasoning_effort"], "low")
        self.assertFalse(captured["options"]["native_tools"])

        core._handle_api_request_with_retry = lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("offline")
        )
        self.assertEqual(core.generate_conversation_title("טקסט שאסור להפוך לכותרת מקומית", "תשובה"), "")

    def test_title_is_scheduled_after_storage_and_user_edits_are_protected(self):
        with tempfile.TemporaryDirectory() as directory:
            core = SmartiCore.__new__(SmartiCore)
            core.mode = "gemini"
            core.settings = copy.deepcopy(DEFAULT_SETTINGS)
            core.settings["selected_gemini_model"] = "gemini-test"
            core.chat_store = ChatSessionStore(str(Path(directory) / "chats.json"))
            core._title_executor = _InlineExecutor()
            core._pending_title_lock = threading.RLock()
            core._pending_title_sessions = set()
            notifications = []
            core._emit_notification = lambda name, payload: notifications.append((name, payload))
            core.generate_conversation_title = lambda *args, **kwargs: "כותרת רקע"
            core._current_agent_process_metadata = lambda: {}
            core._chat_context_snapshot = lambda: {}
            core._pending_canvas_artifacts = []

            session_id = core.chat_store.active_session()["id"]
            core._record_active_chat_turn("בקשה", "תשובה", session_id=session_id)

            self.assertEqual(core.chat_store.active_session()["title"], "כותרת רקע")
            self.assertEqual(notifications[0][0], "chat_title_updated")
            core.chat_store.rename_session(session_id, "כותרת ידנית")
            self.assertFalse(core.chat_store.apply_generated_title(session_id, "אסור לדרוס"))
            self.assertEqual(core.chat_store.active_session()["title"], "כותרת ידנית")

    def test_local_fast_mode_titles_are_local_and_do_not_call_the_model(self):
        with tempfile.TemporaryDirectory() as directory:
            core = SmartiCore.__new__(SmartiCore)
            core.mode = "local"
            core.settings = copy.deepcopy(DEFAULT_SETTINGS)
            core.settings["api_mode"] = "local"
            core.settings["local_fast_mode_enabled"] = True
            core.chat_store = ChatSessionStore(str(Path(directory) / "chats.json"))
            core.generate_conversation_title = mock.Mock(
                side_effect=AssertionError("FastMode must not request a title")
            )
            notifications = []
            core._emit_notification = lambda name, payload: notifications.append((name, payload))
            session_id = core.chat_store.active_session()["id"]

            applied = core._schedule_conversation_title(
                session_id,
                "מצא את כל המסמכים הרלוונטיים וסכם אותם לפי נושא",
                "תשובה",
            )

            self.assertTrue(applied)
            self.assertEqual(
                core.chat_store.active_session()["title"],
                "מצא את כל המסמכים הרלוונטיים וסכם אותם",
            )
            core.generate_conversation_title.assert_not_called()
            self.assertEqual(notifications[0][0], "chat_title_updated")

    def test_local_clients_have_no_request_timeout_but_cloud_compatible_clients_keep_it(self):
        created = []
        openai_module = ModuleType("openai")

        def fake_openai(**kwargs):
            created.append(kwargs)
            return SimpleNamespace()

        openai_module.OpenAI = fake_openai
        core = _request_core("local")
        core.settings["api_mode"] = "local"
        core.settings["local_server_url"] = "http://local.example/v1"
        core._sync_ssl_compat_env = lambda: None
        with mock.patch.dict("sys.modules", {"openai": openai_module}):
            with mock.patch(
                "smarti.agent.model_context.provider_base_url",
                side_effect=lambda mode, local_url: f"http://{mode}.example/v1",
            ):
                core.setup_model()
                core.mode = "unused"
                core.universal_client = None
                core._openai_compatible_client_for_request("local")
                core._openai_compatible_client_for_request("openrouter")

        self.assertIsNone(created[0]["timeout"])
        self.assertIsNone(created[1]["timeout"])
        self.assertEqual(created[2]["timeout"], 1800)

    def test_provider_request_timeout_default_is_thirty_minutes_except_local(self):
        core = SmartiCore.__new__(SmartiCore)

        self.assertIsNone(core._provider_request_timeout("local"))
        for provider in ("gemini", "openai", "anthropic", "openrouter", "groq"):
            with self.subTest(provider=provider):
                self.assertEqual(core._provider_request_timeout(provider), 1800)

    def test_local_fast_mode_planner_uses_same_call_steps_or_a_local_fallback(self):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "local"
        core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        core.settings["api_mode"] = "local"
        core.settings["local_fast_mode_enabled"] = True
        core._trace_agent_phase = mock.Mock()
        core._emit_agent_phase = mock.Mock()
        core._model_task_plan = mock.Mock(
            side_effect=AssertionError("FastMode must not start a second planner request")
        )
        state = core._base_task_state("בדוק וסכם את התיקייה", planner_enabled=False)

        planned, _feedback = core._activate_model_requested_planner(
            state,
            {"intent": "initial_plan", "reason": "משימה מורכבת"},
            "local-model",
        )

        self.assertEqual(planned["planner_source"], "fast_local")
        self.assertTrue(planned["plan_steps"])
        self.assertFalse(planned["used_model_planner"])
        core._model_task_plan.assert_not_called()

    def test_local_fast_mode_suppresses_even_an_explicit_evaluator_microtask(self):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "local"
        core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        core.settings["api_mode"] = "local"
        core.settings["local_fast_mode_enabled"] = True
        core._trace_agent_phase = mock.Mock()
        core._handle_api_request_with_retry = mock.Mock(
            side_effect=AssertionError("FastMode must not start an evaluator request")
        )

        result = core._maybe_evaluate_task_progress(
            {"planner_enabled": True},
            [{"action": "file_manager", "status": "ok", "arguments": {"action": "read"}}],
            "local-model",
            1,
            requested_by_model=True,
        )

        self.assertEqual(result, "")
        core._handle_api_request_with_retry.assert_not_called()

    def test_microtask_budget_estimate_uses_its_own_small_system_prompt(self):
        core = SmartiCore.__new__(SmartiCore)
        core.mode = "gemini"
        core.system_prompt = "large agent prompt " * 5000
        estimate = core._estimate_request_tokens(
            [{"role": "user", "parts": [{"text": "first turn only"}]}],
            provider_mode="gemini",
            system_prompt="short title instruction",
        )
        self.assertLess(estimate, 30)

    def test_verification_is_main_loop_policy_with_enabled_tools(self):
        core = _prompt_core({
            "get_tool_info",
            "system_manager",
            "file_manager",
            "web_manager",
        })

        prompt = core._load_system_prompt("צור קובץ")
        native_names = {
            item["name"]
            for item in core._native_tool_specs_for_request()
        }

        self.assertIn("אימות הוא מדיניות בתוך לולאת העבודה", prompt)
        self.assertIn("אחרי יצירת קובץ קרא או אתר אותו", prompt)
        self.assertIn("אם בדיקה נכשלת", prompt)
        self.assertNotIn("agent_verifier", prompt)
        self.assertNotIn("agent_verifier", native_names)
        self.assertTrue({"system_manager", "file_manager", "web_manager"}.issubset(native_names))

    def test_native_calls_are_canonicalized_for_the_existing_loop(self):
        core = SmartiCore.__new__(SmartiCore)
        text = core._canonical_native_tool_response([
            {"name": "web_manager", "arguments": {"action": "search", "query": "Smarti"}},
        ], "בודק מידע עדכני.")

        self.assertIn("בודק מידע עדכני.", text)
        self.assertIn('"method": "tools/call"', text)
        self.assertIn('"name": "web_manager"', text)


    def test_openai_native_tools_and_unsupported_fallback_preserve_the_loop(self):
        core = _request_core("openai")
        calls = []
        tool_response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=20,
                completion_tokens=4,
                total_tokens=24,
                prompt_tokens_details=SimpleNamespace(cached_tokens=12),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=2),
            ),
            choices=[SimpleNamespace(message=SimpleNamespace(
                content="בודק",
                tool_calls=[SimpleNamespace(function=SimpleNamespace(
                    name="web_manager",
                    arguments='{"action":"search","query":"Smarti"}',
                ))],
            ))],
        )

        def create(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            return tool_response

        core.universal_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        text, usage = core._handle_api_request_with_retry(
            "gpt-5.1",
            [{"role": "user", "content": "חפש"}],
            retry_wait_times=[],
            request_options={"provider_mode": "openai", "reasoning_effort": "low"},
        )

        self.assertIn('"name": "web_manager"', text)
        self.assertIn("tools", calls[0])
        self.assertEqual(calls[0]["reasoning_effort"], "low")
        self.assertEqual(usage["cached_prompt"], 12)
        self.assertEqual(usage["reasoning"], 2)

        attempts = []

        def fallback_create(**kwargs):
            attempts.append(copy.deepcopy(kwargs))
            if len(attempts) == 1:
                raise ValueError("tools are not supported")
            return SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content="fallback answer",
                    tool_calls=[],
                ))],
            )

        core.universal_client.chat.completions.create = fallback_create
        text, _usage = core._handle_api_request_with_retry(
            "compatible-model",
            [{"role": "user", "content": "answer"}],
            retry_wait_times=[],
            request_options={"provider_mode": "openai"},
        )
        self.assertEqual(text, "fallback answer")
        self.assertIn("tools", attempts[0])
        self.assertNotIn("tools", attempts[1])

        cache_calls = []

        def cache_create(**kwargs):
            cache_calls.append(copy.deepcopy(kwargs))
            return SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=2,
                    total_tokens=102,
                    prompt_tokens_details=SimpleNamespace(
                        cached_tokens=60,
                        cache_write_tokens=20,
                    ),
                    completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
                ),
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content="done",
                    tool_calls=[],
                ))],
            )

        core.universal_client.chat.completions.create = cache_create
        core._execution_context = SimpleNamespace(current_task_id="task-1")
        _text, usage = core._handle_api_request_with_retry(
            "gpt-5.6",
            [
                {"role": "system", "content": "stable prompt"},
                {"role": "user", "content": "simple"},
            ],
            retry_wait_times=[],
            request_options={"provider_mode": "openai"},
        )
        self.assertEqual(cache_calls[-1]["prompt_cache_options"], {"mode": "explicit"})
        self.assertNotIn("prompt_cache_key", cache_calls[-1])
        self.assertEqual(usage["cache_write_prompt"], 20)

        core._handle_api_request_with_retry(
            "gpt-5.6",
            [
                {"role": "system", "content": "stable prompt"},
                {"role": "user", "content": "UNTRUSTED_TOOL_OUTPUT one"},
                {"role": "user", "content": "SMARTI_PARALLEL_TOOL_RESULTS two"},
            ],
            retry_wait_times=[],
            request_options={"provider_mode": "openai"},
        )
        self.assertEqual(cache_calls[-1]["prompt_cache_key"], "smarti:task-1")
        self.assertEqual(
            cache_calls[-1]["messages"][0]["content"][0]["prompt_cache_breakpoint"],
            {"mode": "explicit"},
        )

        cache_fallback_attempts = []

        def cache_fallback_create(**kwargs):
            cache_fallback_attempts.append(copy.deepcopy(kwargs))
            if len(cache_fallback_attempts) == 1:
                raise TypeError("unexpected prompt_cache_options parameter")
            return SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content="title",
                    tool_calls=[],
                ))],
            )

        core.universal_client.chat.completions.create = cache_fallback_create
        text, _usage = core._handle_api_request_with_retry(
            "gpt-5.6",
            [{"role": "user", "content": "microtask"}],
            retry_wait_times=[],
            request_options={"provider_mode": "openai", "purpose": "title"},
        )
        self.assertEqual(text, "title")
        self.assertIn("prompt_cache_options", cache_fallback_attempts[0])
        self.assertNotIn("prompt_cache_options", cache_fallback_attempts[1])

    def test_generic_compatible_provider_never_receives_cache_controls(self):
        core = _request_core("openrouter")
        calls = []

        def create(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            return SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content="done",
                    tool_calls=[],
                ))],
            )

        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        core._openai_compatible_client_for_request = lambda _mode: client

        text, _usage = core._handle_api_request_with_retry(
            "gpt-5.6",
            [
                {"role": "system", "content": "stable"},
                {"role": "user", "content": "UNTRUSTED_TOOL_OUTPUT one"},
                {"role": "user", "content": "SMARTI_PARALLEL_TOOL_RESULTS two"},
            ],
            retry_wait_times=[],
            request_options={"provider_mode": "openrouter"},
        )

        self.assertEqual(text, "done")
        self.assertEqual(len(calls), 1)
        self.assertFalse(core._prompt_cache_controls_allowed("openrouter"))
        self.assertFalse(core._prompt_cache_controls_allowed("openai_codex_signin"))
        self.assertTrue(core._prompt_cache_controls_allowed("openai"))
        for key in ("prompt_cache_options", "prompt_cache_key", "cache_control"):
            self.assertNotIn(key, calls[0])

    def test_notification_markdown_is_removed_without_losing_content(self):
        source = (
            "# הושלם\n"
            "- **הקובץ** נשמר ב-[שולחן העבודה](file:///C:/Users/Test/Desktop/result.md).\n"
            "> אפשר לפתוח את `result.md` כעת.\n"
            "![תצוגה](https://example.test/image.png)\n"
            "```python\nprint('hidden')\n```"
        )

        plain = markdown_to_plain_text(source)

        self.assertIn("הושלם", plain)
        self.assertIn("הקובץ", plain)
        self.assertIn("שולחן העבודה", plain)
        self.assertIn("result.md", plain)
        self.assertIn("תצוגה", plain)
        self.assertIn("קטע קוד", plain)
        for marker in ("#", "**", "[שולחן", "](", "`", "![", "```", ">"):
            self.assertNotIn(marker, plain)
        self.assertEqual(markdown_to_plain_text("", fallback="מוכן"), "מוכן")
        shortened = markdown_to_plain_text("**" + ("א" * 100) + "**", limit=20)
        self.assertEqual(len(shortened), 20)
        self.assertTrue(shortened.endswith("..."))

    def test_gemini_and_anthropic_native_tool_blocks_are_canonicalized(self):
        gemini = _request_core("gemini")
        gemini_payloads = []

        def gemini_post(_url, json=None, **_kwargs):
            gemini_payloads.append(copy.deepcopy(json))
            return _JsonResponse({
                "usageMetadata": {
                    "promptTokenCount": 30,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 35,
                    "cachedContentTokenCount": 8,
                    "thoughtsTokenCount": 3,
                },
                "candidates": [{"content": {"parts": [
                    {"text": "בודק"},
                    {"functionCall": {
                        "name": "file_manager",
                        "args": {"action": "read_file", "path": "C:\\a.txt"},
                    }},
                ]}}],
            })

        gemini._request_post = gemini_post
        text, usage = gemini._handle_api_request_with_retry(
            "gemini-2.5-flash",
            [{"role": "user", "parts": [{"text": "קרא"}]}],
            retry_wait_times=[],
            request_options={"provider_mode": "gemini", "reasoning_effort": "low"},
        )
        self.assertIn('"name": "file_manager"', text)
        self.assertIn("tools", gemini_payloads[0])
        self.assertEqual(
            gemini_payloads[0]["generationConfig"]["thinkingConfig"]["thinkingBudget"],
            1_024,
        )
        self.assertEqual(usage["cached_prompt"], 8)
        self.assertEqual(usage["reasoning"], 3)

        anthropic = _request_core("anthropic")
        anthropic_payloads = []

        def anthropic_post(_url, json=None, **_kwargs):
            anthropic_payloads.append(copy.deepcopy(json))
            return _JsonResponse({
                "usage": {
                    "input_tokens": 10,
                    "cache_read_input_tokens": 40,
                    "cache_creation_input_tokens": 5,
                    "output_tokens": 7,
                },
                "content": [
                    {"type": "text", "text": "בודק"},
                    {"type": "tool_use", "name": "system_manager", "input": {"action": "get_system_info"}},
                ],
            })

        anthropic._request_post = anthropic_post
        text, usage = anthropic._handle_api_request_with_retry(
            "claude-test",
            [{"role": "user", "content": "בדוק"}],
            retry_wait_times=[],
            request_options={"provider_mode": "anthropic"},
        )
        self.assertIn('"name": "system_manager"', text)
        self.assertIn("tools", anthropic_payloads[0])
        self.assertIsInstance(anthropic_payloads[0]["system"], str)
        self.assertEqual(usage["prompt"], 55)
        self.assertEqual(usage["cached_prompt"], 40)
        self.assertEqual(usage["cache_write_prompt"], 5)


if __name__ == "__main__":
    unittest.main()
