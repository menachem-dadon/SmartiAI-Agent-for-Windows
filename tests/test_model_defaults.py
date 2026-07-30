import copy
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from smarti.common import (
    MODEL_SELECTION_PROVENANCE_VERSION,
    MODEL_SELECTION_SOURCE_DEFAULT,
    MODEL_SELECTION_SOURCE_USER,
    provider_default_model,
)
from smarti.config import DEFAULT_SETTINGS
from smarti.core import SmartiCore
from smarti.managers import SettingsManager
from smarti.ui_pages import SettingsPage


class _JsonResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


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


class ModelDefaultAndProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = SettingsManager(
            os.path.join(self.temp.name, "settings.json"),
            DEFAULT_SETTINGS,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_defaults_use_the_three_exact_models(self):
        expected = {
            "gemini": "gemini-3.6-flash",
            "openai": "gpt-5.6-sol",
            "anthropic": "claude-opus-5",
        }
        for provider, model in expected.items():
            self.assertEqual(provider_default_model(provider), model)
            self.assertEqual(DEFAULT_SETTINGS[f"selected_{provider}_model"], model)
            self.assertEqual(
                DEFAULT_SETTINGS["selected_model_source"][provider],
                MODEL_SELECTION_SOURCE_DEFAULT,
            )

    def test_missing_values_receive_new_defaults_without_marking_them_user_selected(self):
        loaded = {
            "settings_schema_version": 2,
            "ssl_trust_migration_version": 1,
            "ssl_trust_mode": "system",
            "allow_insecure_ssl_compat": False,
            "long_task_defaults_version": 1,
        }

        migrated, changed = self.manager.migrate_or_merge(loaded)

        self.assertTrue(changed)
        for provider in ("gemini", "openai", "anthropic"):
            self.assertEqual(
                migrated[f"selected_{provider}_model"],
                provider_default_model(provider),
            )
            self.assertEqual(
                migrated["selected_model_source"][provider],
                MODEL_SELECTION_SOURCE_DEFAULT,
            )

    def test_existing_nonempty_models_are_preserved_and_conservatively_marked_user(self):
        loaded = {
            "settings_schema_version": 2,
            "ssl_trust_migration_version": 1,
            "ssl_trust_mode": "system",
            "allow_insecure_ssl_compat": False,
            "long_task_defaults_version": 1,
            "selected_gemini_model": "gemini-3.1-flash-lite",
            "selected_openai_model": "gpt-5.4",
            "selected_anthropic_model": "claude-custom-manual",
        }

        migrated, _changed = self.manager.migrate_or_merge(loaded)

        self.assertEqual(migrated["selected_gemini_model"], "gemini-3.1-flash-lite")
        self.assertEqual(migrated["selected_openai_model"], "gpt-5.4")
        self.assertEqual(migrated["selected_anthropic_model"], "claude-custom-manual")
        for provider in ("gemini", "openai", "anthropic"):
            self.assertEqual(
                migrated["selected_model_source"][provider],
                MODEL_SELECTION_SOURCE_USER,
            )
        self.assertEqual(
            migrated["model_selection_provenance_version"],
            MODEL_SELECTION_PROVENANCE_VERSION,
        )

    def test_explicit_ui_commit_marks_provider_model_as_user_selected(self):
        page = SimpleNamespace(
            provider_combo=SimpleNamespace(currentText=lambda: "anthropic"),
            core=SimpleNamespace(settings=copy.deepcopy(DEFAULT_SETTINGS)),
            _ensure_model_favorite=mock.Mock(),
            _schedule_autosave=mock.Mock(),
        )

        SettingsPage._on_model_committed(page, "claude-opus-5")

        self.assertEqual(
            page.core.settings["selected_model_source"]["anthropic"],
            MODEL_SELECTION_SOURCE_USER,
        )
        page._schedule_autosave.assert_called_once_with()


class ExactProviderPayloadTests(unittest.TestCase):
    @staticmethod
    def _anthropic_response():
        return _JsonResponse({
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": 40,
                "cache_creation_input_tokens": 5,
                "output_tokens": 7,
            },
            "content": [
                {"type": "text", "text": "before tool"},
                {
                    "type": "tool_use",
                    "id": "toolu_opus5_1",
                    "name": "system_manager",
                    "input": {"action": "get_system_info"},
                },
                {"type": "text", "text": "after tool"},
            ],
        })

    def test_opus_5_payload_omits_sampling_and_uses_effort_and_capability_limit(self):
        core = _request_core("anthropic")
        payloads = []

        def post(_url, json=None, **_kwargs):
            payloads.append(copy.deepcopy(json))
            return self._anthropic_response()

        core._request_post = post
        text, usage = core._handle_api_request_with_retry(
            "claude-opus-5",
            [{"role": "user", "content": "inspect"}],
            retry_wait_times=[],
            request_options={
                "provider_mode": "anthropic",
                "reasoning_effort": "xhigh",
            },
        )

        payload = payloads[0]
        for field in ("temperature", "top_p", "top_k", "thinking"):
            self.assertNotIn(field, payload)
        self.assertEqual(payload["output_config"], {"effort": "xhigh"})
        self.assertEqual(payload["max_tokens"], 64_000)
        self.assertIn("before tool", text)
        self.assertIn("after tool", text)
        self.assertIn("toolu_opus5_1", text)
        self.assertIn('"name": "system_manager"', text)
        self.assertEqual(usage["prompt"], 55)
        self.assertEqual(usage["cached_prompt"], 40)
        self.assertEqual(usage["cache_write_prompt"], 5)

    def test_opus_5_output_limit_is_capped_by_remaining_smarti_token_budget(self):
        core = _request_core("anthropic")
        core.settings["budgets"]["daily_token_budget"] = 8_000
        core._daily_token_usage = lambda: 1_000
        core._estimate_request_tokens = lambda *args, **kwargs: 2_000
        payloads = []
        core._request_post = lambda _url, json=None, **_kwargs: (
            payloads.append(copy.deepcopy(json)) or self._anthropic_response()
        )

        core._handle_api_request_with_retry(
            "claude-opus-5",
            [{"role": "user", "content": "inspect"}],
            retry_wait_times=[],
            request_options={"provider_mode": "anthropic"},
        )

        self.assertEqual(payloads[0]["max_tokens"], 5_000)

    def test_gemini_3_6_omits_temperature_and_maps_thinking_with_tools(self):
        core = _request_core("gemini")
        payloads = []

        def post(_url, json=None, **_kwargs):
            payloads.append(copy.deepcopy(json))
            return _JsonResponse({
                "usageMetadata": {
                    "promptTokenCount": 20,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 30,
                    "thoughtsTokenCount": 5,
                },
                "candidates": [{"content": {"parts": [
                    {"functionCall": {
                        "id": "gemini_call_1",
                        "name": "file_manager",
                        "args": {"action": "read_document", "path": "C:\\a.txt"},
                    }},
                ]}}],
            })

        core._request_post = post
        text, _usage = core._handle_api_request_with_retry(
            "gemini-3.6-flash",
            [{"role": "user", "parts": [{"text": "read"}]}],
            retry_wait_times=[],
            request_options={
                "provider_mode": "gemini",
                "reasoning_effort": "high",
            },
        )

        payload = payloads[0]
        self.assertNotIn("temperature", payload["generationConfig"])
        self.assertEqual(
            payload["generationConfig"]["thinkingConfig"],
            {"thinkingLevel": "high"},
        )
        self.assertIn("tools", payload)
        self.assertIn("gemini_call_1", text)

    def test_gpt_5_6_sol_keeps_reasoning_cache_and_native_tools_without_temperature(self):
        core = _request_core("openai")
        calls = []

        def create(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            return SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=6,
                    total_tokens=106,
                    prompt_tokens_details=SimpleNamespace(
                        cached_tokens=50,
                        cache_write_tokens=10,
                    ),
                    completion_tokens_details=SimpleNamespace(reasoning_tokens=3),
                ),
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content="working",
                    tool_calls=[SimpleNamespace(
                        id="call_openai_1",
                        function=SimpleNamespace(
                            name="web_manager",
                            arguments='{"action":"search","query":"Smarti"}',
                        ),
                    )],
                ))],
            )

        core.universal_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        core._execution_context = SimpleNamespace(current_task_id="task-5-6")
        text, usage = core._handle_api_request_with_retry(
            "gpt-5.6-sol",
            [
                {"role": "system", "content": "stable"},
                {"role": "user", "content": "UNTRUSTED_TOOL_OUTPUT one"},
                {"role": "user", "content": "SMARTI_PARALLEL_TOOL_RESULTS two"},
            ],
            retry_wait_times=[],
            request_options={
                "provider_mode": "openai",
                "reasoning_effort": "high",
            },
        )

        payload = calls[0]
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["prompt_cache_options"], {"mode": "explicit"})
        self.assertEqual(payload["prompt_cache_key"], "smarti:task-5-6")
        self.assertIn("tools", payload)
        self.assertIn("call_openai_1", text)
        self.assertEqual(usage["cached_prompt"], 50)
        self.assertEqual(usage["cache_write_prompt"], 10)

    def test_generic_compatible_provider_gets_no_first_party_openai_fields(self):
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
        core._handle_api_request_with_retry(
            "gpt-5.6-sol",
            [{"role": "user", "content": "work"}],
            retry_wait_times=[],
            request_options={
                "provider_mode": "openrouter",
                "reasoning_effort": "max",
            },
        )

        for field in (
            "reasoning_effort",
            "prompt_cache_options",
            "prompt_cache_key",
        ):
            self.assertNotIn(field, calls[0])

    def test_unsupported_cache_parameter_fallback_does_not_change_manual_model(self):
        core = _request_core("openai")
        core.settings["selected_openai_model"] = "my-manual-openai-model"
        core.settings["selected_model_source"]["openai"] = MODEL_SELECTION_SOURCE_USER
        attempts = []

        def create(**kwargs):
            attempts.append(copy.deepcopy(kwargs))
            if len(attempts) == 1:
                raise TypeError("unexpected prompt_cache_options parameter")
            return SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(message=SimpleNamespace(
                    content="done",
                    tool_calls=[],
                ))],
            )

        core.universal_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        core._handle_api_request_with_retry(
            "gpt-5.6-sol",
            [{"role": "user", "content": "work"}],
            retry_wait_times=[],
            request_options={"provider_mode": "openai"},
        )

        self.assertEqual(len(attempts), 2)
        self.assertNotIn("prompt_cache_options", attempts[1])
        self.assertEqual(
            core.settings["selected_openai_model"],
            "my-manual-openai-model",
        )
        self.assertEqual(
            core.settings["selected_model_source"]["openai"],
            MODEL_SELECTION_SOURCE_USER,
        )

    def test_opus_5_context_window_matches_current_contract(self):
        core = _request_core("anthropic")
        self.assertEqual(
            core._model_context_window_tokens("claude-opus-5"),
            1_000_000,
        )

    def test_native_tool_call_id_survives_canonical_parser(self):
        core = _request_core("openai")
        core._normalize_tool_call_args = lambda _action, arguments: arguments
        core._tool_requires_info_before_use = (
            lambda _action, _arguments, _schemas: (False, "")
        )
        core._normalize_step_text = lambda text: text
        core._fallback_step_for_tool = lambda *_args, **_kwargs: "run tool"
        core._validate_tool_call = lambda _action, _arguments: (True, "")
        canonical = core._canonical_native_tool_response(
            [{
                "id": "provider-call-42",
                "name": "system_manager",
                "arguments": {"action": "get_system_info"},
            }],
            "inspect",
        )
        json_line = next(
            line for line in canonical.splitlines()
            if line.lstrip().startswith("{")
            and json.loads(line).get("method") == "tools/call"
        )

        decoded, error = core._decode_tool_call_entry(
            {"json_str": json_line, "tool_turn_text": canonical},
            "inspect",
            set(),
        )

        self.assertIsNone(error)
        self.assertEqual(decoded["provider_call_id"], "provider-call-42")


if __name__ == "__main__":
    unittest.main()
