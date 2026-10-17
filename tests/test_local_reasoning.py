"""Local capability, preference and request contracts without personal servers."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from smarti import local_reasoning as lr
from smarti import lmstudio_prediction
from smarti.agent.local_streaming import local_progress_response, ollama_response
from smarti.local_gateway import SmartiLocalGateway
from smarti.run_manager import ConversationRunManager
from tests.test_api_provider_runtime import RequestCore, completion
from tests import test_conversation_runs as fixtures


def contract(kind="llamacpp", native=("low", "medium", "xhigh"), budget=True):
    return {"kind": kind, "base": "http://localhost:1234/v1", "root": "http://localhost:1234",
            "native": list(native), "default": "xhigh" if "xhigh" in native else next(iter(native), ""),
            "budget": budget, "thinking": True}


class LocalReasoningTests(unittest.TestCase):
    def setUp(self):
        lr._cache.clear()
        self.core = RequestCore("local")

    def test_native_default_and_independent_budget_identity(self):
        c = contract()
        self.assertEqual(lr.selection(self.core, "model", c), "xhigh")
        lr.save(self.core, "model", "budget:max", c)
        self.assertEqual(lr.selection(self.core, "model", c), "budget:max")
        self.assertEqual(lr.closest("budget:max", c["native"]), "xhigh")
        self.assertEqual(lr.closest("budget:high", ["medium", "xhigh"]), "medium")

    def test_preferences_are_isolated_by_endpoint_full_model_id_and_persist(self):
        c = contract()
        model = r"C:\Models\Vendor\Qwen3.8.gguf"
        lr.save(self.core, model, "budget:high", c)
        self.core.settings = copy.deepcopy(self.core.settings)
        self.assertEqual(lr.selection(self.core, model, c), "budget:high")
        self.assertEqual(lr.selection(self.core, model.lower(), c), "xhigh")
        self.core.settings["local_server_url"] = "http://localhost:8080/v1"
        self.assertEqual(lr.selection(self.core, model, c), "xhigh")

    def test_budget_only_default_binary_preference_and_capability_loss(self):
        for native in ([], ["none", "on"]):
            c = contract(native=native)
            self.assertEqual(lr.selection(self.core, "model", c), "budget:medium")
            self.assertTrue(all(o["value"].startswith("budget:") for o in lr.options(c)))
        lr.save(self.core, "model", "budget:max", contract())
        self.assertEqual(lr.selection(self.core, "model", contract(budget=False)), "xhigh")
        self.assertEqual(lr.selection(self.core, "other", contract(native=[], budget=False)), "")

    def test_invalid_effort_does_not_mutate_settings(self):
        before = copy.deepcopy(self.core.settings)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            lr.save(self.core, "model", "unlimited", contract())
        self.assertEqual(before, self.core.settings)

    def test_llama_budget_keeps_native_effort_constant_and_has_no_output_cap(self):
        for level, tokens in lr.BUDGETS.items():
            result = lr.parameters({"contract": contract(), "effort": "budget:" + level})
            self.assertEqual(result["thinking_budget_tokens"], tokens)
            self.assertEqual(result["reasoning_effort"], "none" if level == "none" else "xhigh")
            self.assertNotIn("max_tokens", result)
        self.assertNotIn("thinking_budget_tokens", lr.parameters({"contract": contract(), "effort": "low"}))

    def test_frozen_request_does_not_follow_server_or_effort_changes(self):
        with patch.object(lr, "discover", return_value=contract()):
            frozen = lr.request_control(self.core, "model")
            self.core._execution_context = NS(run_values={"local_reasoning_snapshot": frozen})
            self.core.settings["local_server_url"] = "http://localhost:8080/v1"
            self.core.settings["local_model_reasoning"] = {}
            self.assertEqual(lr.request_control(self.core, "model"), frozen)
            self.assertEqual(lr.run_base(self.core), "http://localhost:1234/v1")

    def test_lmstudio_discovers_model_alias_metadata_without_loading(self):
        self.core._request_get = Mock(return_value=NS(status_code=200, json=lambda: {"models": [{"key": "vendor/model", "type": "llm", "format": "gguf", "loaded_instances": [{"id": "alias"}], "capabilities": {"reasoning": {"allowed_options": ["off", "low", "high"], "default": "high"}}}]}))
        c = lr.discover(self.core, "alias")
        self.assertEqual(c["native"], ["none", "low", "high"])
        self.assertEqual(c["default"], "high")
        self.assertTrue(c["budget"])
        lr.discover(self.core, "alias")
        self.core._request_get.assert_called_once()
        self.assertFalse(hasattr(self.core, "_request_post"))

    def test_llama_props_metrics_omit_budget_but_verified_build_supports_it(self):
        def get(url, **kwargs):
            data = {"default_generation_settings": {"params": {}}, "build_info": "b9982-abcdef", "chat_template": "<think> enable_thinking reasoning_effort </think>"} if "/props?" in url else {}
            return NS(status_code=200, json=lambda: data)
        self.core._request_get = Mock(side_effect=get)
        c = lr.discover(self.core, "Qwen3.8-27B")
        self.assertEqual(c["kind"], "llamacpp")
        self.assertEqual(c["native"], ["none", "low", "medium", "xhigh"])
        self.assertTrue(c["budget"])
        self.assertIn("autoload=false", self.core._request_get.call_args.args[0])

    def test_old_or_unknown_server_does_not_claim_numeric_support(self):
        self.core._request_get = lambda url, **_: NS(status_code=200, json=lambda: {"default_generation_settings": {}, "build_info": "b7000", "chat_template": "<think> enable_thinking </think>"} if "/props?" in url else {})
        self.assertFalse(lr.discover(self.core, "Qwen3")["budget"])
        lr._cache.clear()
        self.core._request_get = Mock(side_effect=OSError("offline"))
        self.assertEqual(lr.describe(self.core, "Qwen3.8")["reasoning_options"], [])

    def test_llama_runtime_sends_budget_on_chat_path_with_actual_template(self):
        self.core.universal_client = NS(chat=NS(completions=NS(create=Mock(return_value=completion()))))
        c = contract()
        lr.save(self.core, "test-model", "budget:medium", c)
        with patch.object(lr, "discover", return_value=c):
            self.assertEqual(self.core.call(retries=[])[0], "answer")
        body = self.core.universal_client.chat.completions.create.call_args.kwargs
        self.assertEqual(body["extra_body"]["thinking_budget_tokens"], 4096)
        self.assertEqual(body["extra_body"]["reasoning_effort"], "xhigh")
        self.assertNotIn("max_tokens", body)

    def test_lmstudio_numeric_uses_official_sdk_adapter_even_without_stream(self):
        c = contract("lmstudio")
        lr.save(self.core, "test-model", "budget:low", c)
        with patch.object(lr, "discover", return_value=c), patch("smarti.lmstudio_prediction.predict", return_value=("answer", {})) as predict:
            self.assertEqual(self.core.call(retries=[])[0], "answer")
        self.assertEqual(predict.call_args.args[1]["effort"], "budget:low")
        self.assertNotIn("max_output_tokens", predict.call_args.args[4])

    def test_llama_reasoning_does_not_use_uncontrolled_raw_completion(self):
        self.core._current_stream = Mock()
        self.core._request_post = Mock(side_effect=AssertionError("must use chat API"))
        control = {"contract": contract(), "effort": "budget:high"}
        self.assertIsNone(local_progress_response(self.core, "http://localhost:1234/v1", "model", [], "system", {"local_reasoning_control": control}, "budget:high"))

    def test_gateway_validates_persists_and_bootstraps_the_same_local_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            core = fixtures._FakeCore(Path(directory) / "history.json")
            core._save_settings = Mock()
            core.run_manager = ConversationRunManager(core)
            gateway = SmartiLocalGateway(core, "test-token", port=0)
            with patch.object(lr, "discover", return_value=contract()):
                self.assertTrue(gateway.start())
                request = fixtures.LocalGatewayTests._request
                try:
                    _, _, data = request(gateway, "/v2/providers/local/reasoning?model=model-a")
                    self.assertEqual(data["data"]["reasoning_effort"], "xhigh")
                    _, _, saved = request(gateway, "/v2/providers/local/reasoning", method="POST", payload={"model": "model-a", "effort": "budget:max"})
                    _, _, refreshed = request(gateway, "/v2/bootstrap")
                    self.assertEqual(saved["data"]["reasoning_effort"], "budget:max")
                    self.assertEqual(refreshed["data"]["chat_models"]["reasoning_effort"], "budget:max")
                    core._save_settings.assert_called_once()
                finally:
                    gateway.stop()
                    core.run_manager.shutdown(wait=True)

    def test_positive_budget_enables_a_model_whose_native_default_is_off(self):
        c = contract(native=["none", "on"])
        c["default"] = "none"
        result = lr.parameters({"contract": c, "effort": "budget:medium"})
        self.assertTrue(result["chat_template_kwargs"]["enable_thinking"])
        self.assertNotEqual(result.get("reasoning_effort"), "none")

    def test_ollama_native_levels_do_not_get_translated_to_budget_or_output_limit(self):
        c = contract("ollama", native=["low", "medium", "high"], budget=False)
        control = {"contract": c, "model": "gpt-oss", "effort": "high"}
        response = NS(status_code=200, iter_lines=lambda: iter([
            json.dumps({"message": {"thinking": "PRIVATE"}}).encode(),
            json.dumps({"message": {"content": "תשובה"}, "done": True, "done_reason": "stop", "eval_count": 4}).encode(),
        ]), close=Mock())
        self.core._request_post = Mock(return_value=response)
        self.core._current_stream = Mock()
        self.assertEqual(ollama_response(self.core, control, [{"role": "user", "content": "hello"}], {})[0], "תשובה")
        payload = self.core._request_post.call_args.kwargs["json"]
        self.assertEqual(payload["think"], "high")
        self.assertNotIn("options", payload)
        self.core._current_stream.text.assert_called_with("תשובה")
        response.close.assert_called_once()

    @unittest.skipUnless(shutil.which("node"), "Node runtime required for prediction process test")
    def test_prediction_launches_node_through_real_runtime_and_reads_frames(self):
        # Keep the real runtime and Python process/stream lifecycle. Only the
        # SDK-facing bridge is replaced, so a nonexistent runtime method cannot hide
        # behind a mocked predict() or a direct Node invocation.
        source = r'''
require('node:readline').createInterface({input:process.stdin}).once('line', line => {
  const input = JSON.parse(line);
  const emit = value => process.stdout.write(JSON.stringify(value)+'\n');
  if (input.budget !== 256 || input.messages[0].content !== 'hello' || 'maxTokens' in input) {
    emit({type:'error',message:'incorrect prediction payload'}); process.exit(1);
  }
  emit({type:'prefill',percent:50});
  emit({type:'thinking'});
  emit({type:'text',content:'answer'});
  emit({type:'done',stats:{stopReason:'eosFound',promptTokensCount:3,predictedTokensCount:5}});
  process.exit(0);
});
'''
        core = NS(_raise_if_cancelled=Mock(), _provider_transport_timeout=lambda _: 5,
                  _check_generated_response=Mock(), _current_stream=Mock(),
                  _register_active_process=Mock(), _unregister_active_process=Mock())
        control = {"contract": contract("lmstudio"), "model": "model", "effort": "budget:minimal"}
        with tempfile.TemporaryDirectory() as directory:
            bridge = Path(directory) / "bridge.cjs"
            bridge.write_text(source, encoding="utf-8")
            with patch.object(lmstudio_prediction, "Path", return_value=NS(with_name=lambda _: bridge)):
                text, usage = lmstudio_prediction.predict(core, control, [{"role": "user", "content": "hello"}], "system", {})
        self.assertEqual(text, "answer")
        self.assertEqual(usage, {"prompt": 3, "completion": 5, "total": 8})
        core._current_stream.text.assert_called_once_with("answer")
        core._current_stream.status.assert_any_call("prefill", 50)
        core._current_stream.status.assert_any_call("thinking")
        core._check_generated_response.assert_called_once_with("local", "model", "answer", [])
        process = core._register_active_process.call_args.args[0]
        core._unregister_active_process.assert_called_once_with(process)
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed and process.stdout.closed)

    @unittest.skipUnless(shutil.which("node"), "Node runtime required for SDK bridge protocol test")
    def test_sdk_bridge_consolidates_systems_preserves_turns_images_and_budget(self):
        source = (Path(__file__).resolve().parents[1] / "scripts/lmstudio_bridge.mjs").read_text(encoding="utf-8")
        # Exercise the real adapter against the public SDK shape. This is not
        # an LM Studio inference test and does not load a personal model.
        fake = r'''
const messages = [];
class Chat { static empty() { return { append(role, content, opts) { messages.push({role, content, images:opts?.images?.length||0}); } }; } }
class LMStudioClient {
  constructor() {
    this.system = { getLMStudioVersion: async () => ({ version:'0.4.24' }) };
    this.files = { prepareImageBase64: async () => ({}) };
    this.llm = { createDynamicHandle: () => ({ getModelInfo: async () => ({}), respond: (chat,opts) => {
      if (messages.some((m,i) => m.role === 'system' && i !== 0)) throw new Error('System message must be at the beginning.');
      process.stdout.write(JSON.stringify({type:'observed', budget:opts.reasoningBudget, enabled:opts.enableThinking, hasMaxTokens:'maxTokens' in opts, messages})+'\n');
      opts.onPromptProcessingProgress(.5);
      const result=Promise.resolve({stats:{stopReason:'eosFound',promptTokensCount:3,predictedTokensCount:5}});
      result[Symbol.asyncIterator]=async function*(){yield {reasoningType:'reasoning',content:'PRIVATE'};yield {reasoningType:'none',content:'תשובה'};};return result;
    } }) };
  }
}
'''
        source = source.replace("import { LMStudioClient, Chat } from '@lmstudio/sdk';", fake)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.mjs"
            path.write_text(source, encoding="utf-8")
            for budget, expected, enabled in [(4096, 4096, True), (0, 0, False), (-1, False, True)]:
                with self.subTest(budget=budget):
                    payload = {"root": "http://localhost:1234", "model": "model", "budget": budget, "system": "system",
                               "messages": [{"role": "system", "content": "system"},
                                            {"role": "system", "content": [{"type": "text", "text": "stream contract"}]},
                                            {"role": "assistant", "content": "prior"},
                                            {"role": "system", "content": "turn context"},
                                            {"role": "user", "content": [{"type": "text", "text": "hello"},
                                                {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGVsbG8="}}]}]}
                    result = subprocess.run([shutil.which("node"), str(path)], input=json.dumps(payload)+"\n", capture_output=True,
                                            text=True, encoding="utf-8", timeout=5, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    frames = [json.loads(line) for line in result.stdout.splitlines()]
                    self.assertEqual(frames[0], {"type": "observed", "budget": expected, "enabled": enabled, "hasMaxTokens": False,
                                                 "messages": [{"role": "system", "content": "system\n\nstream contract\n\nturn context", "images": 0},
                                                              {"role": "assistant", "content": "prior", "images": 0},
                                                              {"role": "user", "content": "hello", "images": 1}]})
                    self.assertNotIn("PRIVATE", result.stdout)
                    self.assertTrue(any(frame.get("content") == "תשובה" for frame in frames))


if __name__ == "__main__":
    unittest.main()
