import copy
import json
import tempfile
import unittest
from unittest import mock

from smarti.common import default_model_reasoning_level, model_reasoning_options, model_reasoning_setting, set_model_reasoning_setting
from smarti.config import DEFAULT_SETTINGS
from smarti.subscription_providers import ANTIGRAVITY
from smarti.subscription_providers.antigravity import AntigravityProvider, split_model
from smarti.subscription_providers.base import SubscriptionError


class AntigravityReasoningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = AntigravityProvider(self.temp.name, "google_login")
        self.catalog = "\n".join([
            "gemini-3.8-flash-low Gemini Flash Low", "gemini-3.8-flash-high Gemini Flash High",
            "claude-sonnet-5-5-medium Claude Sonnet Medium", "gpt-oss-120b-medium GPT OSS Medium",
            "unknown-new-model New Model",
        ])
        with mock.patch.object(self.provider, "executable", return_value="agy"), mock.patch.object(self.provider, "run", return_value=self.catalog):
            self.provider.catalog()

    def tearDown(self):
        self.temp.cleanup()

    def test_metadata_only_offers_reported_siblings_and_preserves_raw_ids(self):
        self.assertEqual([value for value, _ in model_reasoning_options(ANTIGRAVITY, "gemini-3.8-flash-high")], ["low", "high"])
        self.assertEqual(default_model_reasoning_level(ANTIGRAVITY, "gemini-3.8-flash-high"), "high")
        self.assertEqual(default_model_reasoning_level(ANTIGRAVITY, "gemini-3.8-flash-low"), "low")
        self.assertEqual(model_reasoning_options(ANTIGRAVITY, "unknown-new-model"), [])
        self.assertEqual(split_model("claude-sonnet-5-5-medium"), ("claude-sonnet-5-5", "medium"))
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        set_model_reasoning_setting(settings, ANTIGRAVITY, "gemini-3.8-flash-high", "low")
        self.assertEqual(model_reasoning_setting(settings, ANTIGRAVITY, "gemini-3.8-flash-high"), "low")
        self.assertEqual(settings["selected_google_antigravity_signin_model"], "gemini-3.8-flash-high")

    def test_unknown_models_or_efforts_never_synthesize_a_transport_id(self):
        for model, effort in (("gemini-3.8-flash", "low"), ("gemini-3.8-flash-high", "medium"),
                ("unknown-new-model", "high"), ("gpt-oss-120b-medium", "high")):
            with self.subTest(model=model, effort=effort), self.assertRaises(SubscriptionError):
                self.provider.resolve_model(model, effort)
        self.assertEqual(self.provider.resolve_model("unknown-new-model"), "unknown-new-model")

    def test_wire_model_and_usage_follow_the_effort_without_changing_requested_identity(self):
        def run(command, **options):
            if command[-1] == "--version": return "1.4.2"
            wire_model = command[command.index("--model") + 1]
            self.assertEqual(wire_model, "gemini-3.8-flash-low")
            name = command[command.index("--agent") + 1]
            options["event"](json.dumps({"event": "init", "init": {"agent": name, "model": wire_model}}))
            options["event"](json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": json.dumps({
                "kind": "final", "progress_report": "", "final_answer": "done", "tool_calls": []})}}))
            return ""
        with mock.patch.object(self.provider, "executable", return_value="agy"), mock.patch.object(self.provider, "run", side_effect=run):
            answer, usage = self.provider.complete([{"role": "user", "content": "test"}], "gemini-3.8-flash-high", reasoning_effort="low")
        self.assertEqual(answer, "done")
        self.assertEqual(usage["requested_model"], "gemini-3.8-flash-high")
        self.assertEqual(usage["effective_model"], "gemini-3.8-flash-low")
