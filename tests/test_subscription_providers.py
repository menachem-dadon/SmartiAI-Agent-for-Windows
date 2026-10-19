"""Subscription adapters without personal credentials, model calls or paid requests."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from smarti.common import MODEL_PROVIDER_ORDER, SmartiCancelled, model_reasoning_options, provider_requires_api_key
from smarti.config import DEFAULT_SETTINGS
from smarti.subscription_providers import CLAUDE, ANTIGRAVITY, get_provider
from smarti.subscription_providers.base import SubscriptionError, SubscriptionProvider, register_models, safe_failure
from smarti.subscription_providers.claude import ClaudeProvider
from smarti.subscription_providers.antigravity import AntigravityProvider
from smarti.subscription_providers.connections import Connections
from smarti.agent.streaming import LiveResponse
from tests.test_api_provider_runtime import RequestCore


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = ClaudeProvider(self.temp.name, "claude_login")

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_keeps_separate_subscription_routes_without_api_secrets_or_defaults(self):
        for name in (CLAUDE, ANTIGRAVITY):
            self.assertIn(name, MODEL_PROVIDER_ORDER)
            self.assertFalse(provider_requires_api_key(name))
            self.assertEqual(DEFAULT_SETTINGS[f"selected_{name}_model"], "")

    def test_environment_uses_only_explicit_token_strategy_and_keeps_parent_unchanged(self):
        inherited = {"CLAUDE_CODE_OAUTH_TOKEN": "test-subscription-secret", "ANTHROPIC_API_KEY": "test-api-key",
            "ANTHROPIC_AUTH_TOKEN": "other-auth", "ANTHROPIC_BASE_URL": "https://invalid.example",
            "CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_MODEL": "another-model"}
        with mock.patch.dict(os.environ, inherited):
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", self.provider.environment())
            token = ClaudeProvider(self.temp.name, "setup_token_env").environment()
            self.assertEqual(token["CLAUDE_CODE_OAUTH_TOKEN"], "test-subscription-secret")
            for key in inherited:
                self.assertEqual(os.environ[key], inherited[key])
                if key != "CLAUDE_CODE_OAUTH_TOKEN":
                    self.assertNotIn(key, token)

    def test_logged_out_exit_is_disconnected_and_never_an_api_key_prompt(self):
        with mock.patch.object(self.provider, "command", return_value=["node", "bridge"]), \
             mock.patch.object(self.provider, "executable", return_value="claude"), \
             mock.patch.object(self.provider, "run", return_value=json.dumps({"loggedIn": False, "authMethod": "none"})) as run:
            result = self.provider.connection_status()
        self.assertEqual(result["state"], "disconnected")
        self.assertEqual(run.call_args.kwargs["ok_codes"], (0, 1))

    def test_free_plan_is_not_a_connected_subscription(self):
        raw = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "free"}
        with mock.patch.object(self.provider, "command"), mock.patch.object(self.provider, "executable"), \
             mock.patch.object(self.provider, "run", return_value=json.dumps(raw)):
            self.assertEqual(self.provider.connection_status()["state"], "account_ineligible")

    def test_api_or_wrong_oauth_mode_is_not_accepted(self):
        for mode in ("api_key", "api_key_helper", "third_party", "oauth_token"):
            with self.subTest(mode=mode), mock.patch.object(self.provider, "command"), \
                 mock.patch.object(self.provider, "executable"), mock.patch.object(self.provider, "run",
                    return_value=json.dumps({"loggedIn": True, "authMethod": mode, "apiProvider": "firstParty"})):
                self.assertEqual(self.provider.connection_status()["state"], "wrong_auth_mode")

    def test_missing_environment_token_does_not_fall_back_to_saved_login(self):
        self.provider.strategy = "setup_token_env"
        with mock.patch.object(self.provider, "command"), mock.patch.object(self.provider, "environment", return_value={}), \
             mock.patch.object(self.provider, "run") as run:
            self.assertEqual(self.provider.connection_status()["state"], "disconnected")
            run.assert_not_called()

    def test_catalog_uses_official_metadata_and_does_not_invent_effort(self):
        def metadata(command, **options):
            request = json.loads(options["payload"])
            self.assertEqual(request["method"], "metadata")
            self.assertNotIn("content", request)
            options["event"](json.dumps({"type": "metadata", "account": {"tokenSource": "none"}, "models": [
                {"value": "sonnet", "resolvedModel": "claude-test", "supportsEffort": True,
                 "supportedEffortLevels": ["low", "high", "not-real"]}, {"value": "plain"}]}))
        with mock.patch.object(self.provider, "command", return_value=[]), \
             mock.patch.object(self.provider, "executable", return_value="claude"), \
             mock.patch.object(self.provider, "run", side_effect=metadata):
            rows = self.provider.catalog()
        self.assertEqual(rows[0]["availability"], "unknown")
        self.assertEqual([value for value, _ in model_reasoning_options(CLAUDE, "sonnet")], ["low", "high"])
        self.assertEqual(model_reasoning_options(CLAUDE, "plain"), [])

    def turn(self, events, *, purpose="agent", stream=None, messages=None, inspect=None):
        self.provider.models = [{"id": "sonnet", "resolved_model": "claude-test", "efforts": ["low"]}]
        def run(command, **options):
            request = json.loads(options["payload"])
            self.assertNotIn("token", request)
            self.assertEqual("schema" in request, purpose == "agent")
            self.assertIn("Smarti system", Path(request["prompt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(request["effort"], "low")
            self.assertNotIn("--bare", command)
            if inspect:
                inspect(request)
            sequence = events if events and events[0].get("type") == "init" else [{"type": "init", "model": "claude-test"}, *events]
            for event in sequence:
                options["event"](json.dumps(event))
        with mock.patch.object(self.provider, "connection_status", return_value={"state": "connected"}), \
             mock.patch.object(self.provider, "command", return_value=["node", "bridge"]), \
             mock.patch.object(self.provider, "executable", return_value="claude"), \
             mock.patch.object(self.provider, "run", side_effect=run):
            return self.provider.complete(messages or [{"role": "system", "content": "Smarti system"},
                {"role": "user", "content": "שלום"}], "sonnet", reasoning_effort="low", purpose=purpose, stream=stream)

    def test_full_tool_turn_preserves_core_ownership_and_normalizes_usage(self):
        envelope = {"kind": "tool_calls", "progress_report": "בודק", "final_answer": None,
            "tool_calls": [{"name": "file_manager", "arguments_json": '{"action":"read"}'}]}
        response, usage = self.turn([{"type": "init", "model": "claude-test"},
            {"type": "result", "ok": True, "output": envelope,
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 4, "cache_creation_input_tokens": 3, "output_tokens": 5}}])
        self.assertEqual(json.loads(response.split("\n", 1)[1])["tool_calls"][0]["name"], "file_manager")
        self.assertEqual(usage["total"], 22)
        self.assertIsNone(usage["estimated_cost_usd"])
        self.assertEqual(usage["effective_model"], "claude-test")

    def test_live_envelope_never_displays_wire_json_or_tool_arguments_as_answer(self):
        events = []
        live = LiveResponse(emit=lambda value: events.extend(value["events"]))
        envelope = {"kind": "final", "tool_calls": None, "final_answer": "תשובה", "progress_report": None}
        raw = json.dumps(envelope, ensure_ascii=False)
        response, _ = self.turn([{"type": "text", "text": raw[:30]}, {"type": "text", "text": raw[30:]},
            {"type": "result", "ok": True, "output": envelope}], stream=live)
        live.finish(response)
        visible = "".join(event.get("text", "") for event in events if event.get("kind") == "text_delta")
        self.assertNotIn('"kind"', visible)
        self.assertEqual(visible, "תשובה")

    def test_failed_missing_and_duplicate_results_cannot_be_success(self):
        final = {"type": "result", "ok": True, "output": {"kind": "final", "tool_calls": None,
            "final_answer": "ready", "progress_report": None}}
        for sequence in ([], [{"type": "result", "ok": False, "errors": ["usage limit"]}], [final, final],
                [{"type": "failure", "reason": "provider_contract_violation"}],
                [{"type": "init", "model": "wrong-model"}, final]):
            with self.subTest(sequence=sequence), self.assertRaises(SubscriptionError):
                self.turn(sequence)

    def test_title_has_no_tool_schema_and_returns_text(self):
        response, _ = self.turn([{"type": "result", "ok": True, "text": "כותרת"}], purpose="title")
        self.assertEqual(response, "כותרת")

    def test_images_and_pdfs_remain_next_to_their_own_conversation_turn(self):
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}}
        document = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "cGRm"}}
        messages = [{"role": "system", "content": "Smarti system"},
            {"role": "user", "content": [{"type": "text", "text": "first image"}, image]},
            {"role": "assistant", "content": "earlier answer"},
            {"role": "user", "content": [{"type": "text", "text": "latest PDF"}, document]}]
        def inspect(request):
            self.assertEqual([block["type"] for block in request["content"]], ["text", "image", "text", "text", "document"])
            self.assertTrue(request["content"][2]["text"].startswith("[ASSISTANT]"))
            self.assertNotIn("cGRm", request["content"][3]["text"])
        self.turn([{"type": "result", "ok": True, "output": {"kind": "final", "tool_calls": None,
            "progress_report": None, "final_answer": "ok"}}], messages=messages, inspect=inspect)

    def test_antigravity_catalog_is_not_readiness_or_tool_isolation_evidence(self):
        provider = AntigravityProvider(self.temp.name, "google_login")
        with mock.patch.object(provider, "executable", return_value="agy"), \
             mock.patch.object(provider, "run", side_effect=["1.4.2", "gemini-test-high\tTest model\n"]):
            self.assertEqual(provider.connection_status()["state"], "policy_conflict")
            self.assertEqual(provider.read_models(), ["gemini-test-high"])
        with self.assertRaises(SubscriptionError) as error:
            provider.complete([], "gemini-test-high")
        self.assertEqual(error.exception.reason, "policy_conflict")

    def test_subscription_core_route_never_falls_back_to_api_or_retries_policy_errors(self):
        core = RequestCore(CLAUDE)
        provider = mock.Mock()
        provider.complete.side_effect = SubscriptionError("blocked", "policy_conflict")
        with mock.patch("smarti.agent.model_context.subscription_provider", return_value=provider):
            with self.assertRaisesRegex(SubscriptionError, "blocked"):
                core.call(retries=[0, 0])
        self.assertEqual(provider.complete.call_count, 1)
        self.assertIsNone(core._request_usage_cost("claude-test", {}, CLAUDE))
        self.assertFalse(core._request_counts_toward_budget("claude-test", CLAUDE))

    def test_frozen_run_provider_survives_settings_auth_change(self):
        core = SimpleNamespace(settings=copy.deepcopy(DEFAULT_SETTINGS))
        frozen = get_provider(core, CLAUDE)
        core._subscription_provider = frozen
        core.settings["claude_code_auth_strategy"] = "setup_token_env"
        self.assertIs(get_provider(core, CLAUDE), frozen)
        self.assertEqual(frozen.strategy, "claude_login")

    def test_disconnect_is_persisted_without_global_logout_or_active_provider_change(self):
        core = SimpleNamespace(settings={"api_mode": "openai"}, _save_settings=mock.Mock())
        with mock.patch("smarti.subscription_providers.connections.get_provider", return_value=self.provider):
            result = Connections(core).action(CLAUDE, "disconnect")
        self.assertEqual(result["state"], "disconnected")
        self.assertEqual(core.settings["api_mode"], "openai")
        self.assertFalse(core.settings["subscription_provider_connections"][CLAUDE])

    def test_check_operation_is_nonblocking_recoverable_and_account_scoped(self):
        release = threading.Event()
        core = SimpleNamespace(settings={}, _save_settings=mock.Mock())
        provider = mock.Mock()
        provider.connection_status.side_effect = lambda: (release.wait(2), {"state": "connected", "message": "ready"})[1]
        service = Connections(core)
        with mock.patch("smarti.subscription_providers.connections.get_provider", return_value=provider):
            start = time.monotonic()
            result = service.action(CLAUDE, "check")
            self.assertLess(time.monotonic() - start, .5)
            with self.assertRaises(KeyError):
                service.operation(ANTIGRAVITY, result["id"])
            service.cancel(CLAUDE, result["id"])
            release.set()
            time.sleep(.02)
            self.assertEqual(service.operation(CLAUDE, result["id"])["state"], "cancelled")
            core._save_settings.assert_not_called()

    def test_bounded_process_drains_stderr_and_accepts_split_unicode(self):
        program = "import sys; sys.stderr.write('x'*200000); sys.stderr.flush(); sys.stdout.buffer.write('שלום\\n'.encode('utf8'))"
        output = self.provider.run([sys.executable, "-c", program], timeout=10)
        self.assertEqual(output, "שלום\n")

    def test_stalled_child_can_be_cancelled_or_timed_out(self):
        cancel = threading.Event()
        cancel.set()
        for options, expected in (({"cancel": cancel, "timeout": 5}, SmartiCancelled), ({"timeout": .15}, SubscriptionError)):
            with self.subTest(options=options), self.assertRaises(expected):
                self.provider.run([sys.executable, "-c", "import time; time.sleep(15)"], **options)

    def test_safe_errors_never_reproduce_credentials(self):
        for value in ("401 sk-secret", "429 sk-secret", "403 subscription sk-secret", "other sk-secret"):
            self.assertNotIn("sk-secret", str(safe_failure(value)))

    def test_authenticated_gateway_status_models_and_disconnect_preserve_selection(self):
        from tests.test_conversation_runs import _FakeCore, LocalGatewayTests
        from smarti.local_gateway import SmartiLocalGateway
        from smarti.run_manager import ConversationRunManager
        core = _FakeCore(Path(self.temp.name) / "gateway-history.json")
        core._save_settings = mock.Mock()
        core.run_manager = ConversationRunManager(core)
        gateway = SmartiLocalGateway(core, "test-token", port=0)
        self.assertTrue(gateway.start())
        request = LocalGatewayTests._request
        provider = mock.Mock()
        provider.connection_status.return_value = {"state": "disconnected", "message": "ready for login"}
        provider.catalog.return_value = [{"id": "sonnet", "availability": "unknown", "efforts": ["low"]}]
        provider.disconnect.return_value = {"state": "disconnected", "message": "disconnected from Smarti"}
        try:
            with mock.patch("smarti.subscription_providers.get_provider", return_value=provider), \
                 mock.patch("smarti.subscription_providers.connections.get_provider", return_value=provider):
                _, _, status = request(gateway, f"/v2/providers/{CLAUDE}/connection")
                self.assertEqual(status["data"]["state"], "disconnected")
                _, _, models = request(gateway, f"/v2/providers/{CLAUDE}/models")
                self.assertEqual(models["data"]["models"], ["sonnet"])
                self.assertEqual(models["data"]["entries"][0]["availability"], "unknown")
                _, _, quota = request(gateway, f"/v2/providers/{CLAUDE}/quota")
                self.assertFalse(quota["data"]["available"])
                request(gateway, f"/v2/providers/{CLAUDE}/connection/disconnect", method="POST", payload={})
            self.assertEqual(core.settings["api_mode"], "local")
            provider.disconnect.assert_called_once()
            provider.complete.assert_not_called()
        finally:
            gateway.stop()
            core.run_manager.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
