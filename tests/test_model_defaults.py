import copy
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QComboBox

from smarti.common import (
    MODEL_SELECTION_PROVENANCE_VERSION,
    MODEL_SELECTION_SOURCE_DEFAULT,
    MODEL_SELECTION_SOURCE_USER,
    model_reasoning_api_parameters,
    model_reasoning_contract,
    model_reasoning_options,
    model_reasoning_setting,
    provider_default_model,
    set_model_reasoning_setting,
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


class ProviderFamilyReasoningContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_gemini_active_families_resolve_to_native_contracts(self):
        expected = {
            "gemini-2.5-pro": "gemini_25_pro",
            "gemini-2.5-flash": "gemini_25_flash",
            "gemini-2.5-flash-lite": "gemini_25_flash_lite",
            "gemini-3-flash-preview": "gemini_3_flash",
            "gemini-3.1-flash-image": "gemini_current_flash_image",
            "gemini-3.1-pro-preview": "gemini_current_pro",
            "gemini-3.5-flash-lite": "gemini_current_flash_lite",
            "gemini-3.6-flash": "gemini_current_flash",
        }
        for model, contract_id in expected.items():
            with self.subTest(model=model):
                self.assertEqual(
                    model_reasoning_contract("gemini", model)["contract_id"],
                    contract_id,
                )

    def test_anthropic_active_families_resolve_to_native_contracts(self):
        expected = {
            "claude-haiku-4-5-20251001": "anthropic_manual_45",
            "claude-sonnet-4-5-20250929": "anthropic_manual_45",
            "claude-opus-4-5-20251101": "anthropic_manual_opus_45",
            "claude-sonnet-4-6": "anthropic_adaptive_46",
            "claude-opus-4-7": "anthropic_adaptive_47_48",
            "claude-opus-4-8": "anthropic_adaptive_47_48",
            "claude-opus-5": "anthropic_current_default_on",
            "claude-sonnet-5": "anthropic_current_default_on",
            "claude-fable-5": "anthropic_current_always_on",
        }
        for model, contract_id in expected.items():
            with self.subTest(model=model):
                self.assertEqual(
                    model_reasoning_contract("anthropic", model)["contract_id"],
                    contract_id,
                )

    def test_openai_active_families_resolve_to_native_contracts(self):
        expected = {
            "gpt-5": "openai_5",
            "gpt-5-pro": "openai_5_pro",
            "gpt-5.1": "openai_51",
            "gpt-5.2": "openai_54_52",
            "gpt-5.2-pro": "openai_52_pro",
            "gpt-5.3-codex": "openai_codex_53",
            "gpt-5.4-mini": "openai_54_52",
            "gpt-5.4-pro": "openai_54_pro",
            "gpt-5.5": "openai_55",
            "gpt-5.5-pro": "openai_55_pro",
            "gpt-5.6-terra": "openai_current",
            "o3": "openai_o3",
            "o3-pro": "openai_o3_pro",
        }
        for model, contract_id in expected.items():
            with self.subTest(model=model):
                self.assertEqual(
                    model_reasoning_contract("openai", model)["contract_id"],
                    contract_id,
                )
        self.assertEqual(model_reasoning_contract("openai", "gpt-4.1"), {})

    def test_unknown_future_models_inherit_each_provider_current_contract(self):
        self.assertEqual(
            model_reasoning_contract("gemini", "gemini-4.2-flash")["contract_id"],
            "gemini_current_flash",
        )
        self.assertEqual(
            model_reasoning_contract("anthropic", "claude-next-2027")["contract_id"],
            "anthropic_current_default_on",
        )
        self.assertEqual(
            model_reasoning_contract("openai", "gpt-5.9-sol")["contract_id"],
            "openai_current",
        )

    def test_none_and_minimal_follow_the_resolved_family(self):
        self.assertNotIn(
            "none",
            model_reasoning_contract("gemini", "gemini-2.5-pro")["supported_levels"],
        )
        self.assertIn(
            "none",
            model_reasoning_contract("gemini", "gemini-2.5-flash")["supported_levels"],
        )
        self.assertIn(
            "minimal",
            model_reasoning_contract("gemini", "gemini-3.6-flash")["supported_levels"],
        )
        self.assertEqual(
            model_reasoning_contract("openai", "gpt-5")["supported_levels"][0],
            "minimal",
        )
        self.assertEqual(
            model_reasoning_contract("openai", "gpt-5.1")["supported_levels"][0],
            "none",
        )
        self.assertNotIn(
            "none",
            model_reasoning_contract("anthropic", "claude-fable-5")["supported_levels"],
        )

    def test_reasoning_preference_is_saved_per_provider_and_model(self):
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        set_model_reasoning_setting(settings, "gemini", "gemini-2.5-flash", "none")
        set_model_reasoning_setting(settings, "gemini", "gemini-3.6-flash", "high")

        self.assertEqual(
            model_reasoning_setting(settings, "gemini", "gemini-2.5-flash"),
            "none",
        )
        self.assertEqual(
            model_reasoning_setting(settings, "gemini", "gemini-3.6-flash"),
            "high",
        )
        self.assertEqual(
            model_reasoning_setting(settings, "openai", "gpt-5.6-sol"),
            "auto",
        )

    def test_auto_is_a_ui_choice_but_never_an_api_value(self):
        options = dict(model_reasoning_options("openai", "gpt-5.6-sol"))
        self.assertIn("auto", options)
        self.assertEqual(
            model_reasoning_api_parameters("openai", "gpt-5.6-sol", "auto"),
            {},
        )
        codex_options = dict(
            model_reasoning_options("openai_codex_signin", "Codex default")
        )
        self.assertIn("auto", codex_options)
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.assertEqual(
            model_reasoning_setting(
                settings,
                "openai_codex_signin",
                "Codex default",
            ),
            "auto",
        )
        self.assertEqual(
            set_model_reasoning_setting(
                settings,
                "openai_codex_signin",
                "Codex default",
                "auto",
            ),
            "auto",
        )
        self.assertEqual(settings["codex_reasoning_effort"], "auto")

    def test_settings_control_rebuilds_options_for_the_selected_family(self):
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        state = {"model": "gemini-2.5-flash"}
        visibility = []
        page = SimpleNamespace(
            core=SimpleNamespace(settings=settings),
            provider_combo=SimpleNamespace(currentText=lambda: "gemini"),
            reasoning_effort_combo=QComboBox(),
            codex_reasoning_effort_field_container=SimpleNamespace(
                setVisible=lambda value: visibility.append(bool(value))
            ),
        )
        page._reasoning_model_for_ui = lambda _provider=None: state["model"]

        SettingsPage._refresh_reasoning_effort_control(page, "gemini")
        self.assertGreaterEqual(page.reasoning_effort_combo.findData("none"), 0)
        self.assertEqual(page.reasoning_effort_combo.findData("minimal"), -1)

        state["model"] = "gemini-3.6-flash"
        SettingsPage._refresh_reasoning_effort_control(page, "gemini")
        self.assertEqual(page.reasoning_effort_combo.findData("none"), -1)
        self.assertGreaterEqual(page.reasoning_effort_combo.findData("minimal"), 0)
        self.assertEqual(page.reasoning_effort_combo.currentData(), "auto")
        self.assertTrue(all(visibility))


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
                "temperature": 0.2,
                "top_p": 0.8,
                "top_k": 20,
                "seed": 42,
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
                "temperature": 0.2,
                "top_p": 0.8,
                "top_k": 20,
                "seed": 42,
                "reasoning_effort": "high",
            },
        )

        payload = payloads[0]
        for field in ("temperature", "topP", "topK", "seed"):
            self.assertNotIn(field, payload["generationConfig"])
        self.assertEqual(
            payload["generationConfig"]["thinkingConfig"],
            {"thinkingLevel": "high"},
        )
        self.assertIn("tools", payload)
        self.assertIn("gemini_call_1", text)

    def test_gemini_25_uses_budget_contract_and_never_temperature(self):
        core = _request_core("gemini")
        payloads = []
        core._request_post = lambda _url, json=None, **_kwargs: (
            payloads.append(copy.deepcopy(json))
            or _JsonResponse({
                "usageMetadata": {},
                "candidates": [{"content": {"parts": [{"text": "done"}]}}],
            })
        )

        core._handle_api_request_with_retry(
            "gemini-2.5-pro",
            [{"role": "user", "parts": [{"text": "work"}]}],
            retry_wait_times=[],
            request_options={
                "provider_mode": "gemini",
                "temperature": 0.2,
                "reasoning_effort": "high",
            },
        )

        generation = payloads[0]["generationConfig"]
        self.assertNotIn("temperature", generation)
        self.assertEqual(
            generation["thinkingConfig"],
            {"thinkingBudget": 32_768},
        )

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
                "temperature": 0.2,
                "top_p": 0.8,
                "top_k": 20,
                "seed": 42,
                "reasoning_effort": "high",
            },
        )

        payload = calls[0]
        for field in ("temperature", "top_p", "top_k", "seed"):
            self.assertNotIn(field, payload)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["prompt_cache_options"], {"mode": "explicit"})
        self.assertEqual(payload["prompt_cache_key"], "smarti:task-5-6")
        self.assertIn("tools", payload)
        self.assertIn("call_openai_1", text)
        self.assertEqual(usage["cached_prompt"], 50)
        self.assertEqual(usage["cache_write_prompt"], 10)

    def test_future_openai_model_uses_current_contract_and_saved_chat_setting(self):
        core = _request_core("openai")
        set_model_reasoning_setting(
            core.settings,
            "openai",
            "gpt-5.9-sol",
            "max",
        )
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

        core.universal_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        core._handle_api_request_with_retry(
            "gpt-5.9-sol",
            [{"role": "user", "content": "work"}],
            retry_wait_times=[],
            request_options={"provider_mode": "openai"},
        )

        self.assertEqual(calls[0]["reasoning_effort"], "max")
        self.assertNotIn("temperature", calls[0])

    def test_anthropic_manual_and_adaptive_families_build_different_payloads(self):
        cases = (
            (
                "claude-sonnet-4-5-20250929",
                "high",
                {
                    "thinking": {
                        "type": "enabled",
                        "budget_tokens": 16_384,
                        "display": "omitted",
                    },
                },
            ),
            (
                "claude-opus-4-8",
                "xhigh",
                {
                    "thinking": {"type": "adaptive", "display": "omitted"},
                    "output_config": {"effort": "xhigh"},
                },
            ),
            (
                "claude-sonnet-6",
                "low",
                {"output_config": {"effort": "low"}},
            ),
        )
        for model, level, expected_fields in cases:
            with self.subTest(model=model):
                core = _request_core("anthropic")
                payloads = []
                core._request_post = lambda _url, json=None, **_kwargs: (
                    payloads.append(copy.deepcopy(json))
                    or self._anthropic_response()
                )
                core._handle_api_request_with_retry(
                    model,
                    [{"role": "user", "content": "work"}],
                    retry_wait_times=[],
                    request_options={
                        "provider_mode": "anthropic",
                        "temperature": 0.2,
                        "reasoning_effort": level,
                    },
                )
                payload = payloads[0]
                self.assertNotIn("temperature", payload)
                for field, value in expected_fields.items():
                    self.assertEqual(payload[field], value)

    def test_all_compatible_providers_omit_sampling_and_first_party_fields(self):
        for provider in ("local", "openrouter"):
            with self.subTest(provider=provider):
                core = _request_core(provider)
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
                        "provider_mode": provider,
                        "temperature": 0.2,
                        "top_p": 0.8,
                        "top_k": 20,
                        "min_p": 0.1,
                        "typical_p": 0.9,
                        "frequency_penalty": 0.5,
                        "presence_penalty": 0.5,
                        "repetition_penalty": 1.1,
                        "seed": 42,
                        "reasoning_effort": "max",
                    },
                )

                for field in (
                    "temperature",
                    "top_p",
                    "top_k",
                    "min_p",
                    "typical_p",
                    "frequency_penalty",
                    "presence_penalty",
                    "repetition_penalty",
                    "seed",
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
