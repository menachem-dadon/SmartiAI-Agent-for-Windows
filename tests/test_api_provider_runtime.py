"""Request, retry, stop-reason and protocol regressions without cloud charges."""
import copy
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest import mock

import httpx
import openai

from smarti.agent.model_context import ModelContextMixin
from smarti.api_errors import ApiRequestError
from smarti.common import MODEL_PROVIDER_ORDER, SmartiCancelled
from smarti.config import DEFAULT_SETTINGS
from tests.test_api_errors import google_quota, response


class RequestCore(ModelContextMixin):
    def __init__(self, provider):
        self.mode = provider
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.system_prompt = "system instructions"
        self.status_callback = None
        self._universal_client_key = "lm-studio" if provider == "local" else "test-key"
        self.waits = []
        self._raise_if_cancelled = lambda: None
        self._native_tool_specs_for_request = lambda: []
        self._ensure_secret_loaded = lambda _key: "test-key"
        self._prepare_messages_for_budget = lambda _model, messages, **_kwargs: messages
        self._run_cancelable_callable = lambda callback: callback()
        self._network_auto_resume_enabled = lambda: False
        self._ssl_context = lambda _url: True

    def _message_text_for_budget(self, message):
        return str(message.get("content") or message.get("parts") or "")

    def _sleep_with_cancel(self, seconds, tick=None):
        self.waits.append(seconds)
        return True

    def call(self, *, retries=None, model="test-model", options=None):
        messages = [{"role": "user", "parts": [{"text": "hello"}]}] if self.mode == "gemini" else [{"role": "user", "content": "hello"}]
        return self._handle_api_request_with_retry(model, messages, retry_wait_times=retries, request_options=options)


def completion(text="answer", *, finish="stop", refusal=None, calls=None):
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=text, refusal=refusal, tool_calls=calls or []))])


class ProviderRuntimeTests(unittest.TestCase):
    def sdk_core(self, provider, create):
        core = RequestCore(provider)
        core.universal_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        return core

    def test_every_openai_compatible_provider_uses_a_compatible_request(self):
        providers = [p for p in MODEL_PROVIDER_ORDER if p not in {"gemini", "anthropic", "openai_codex_signin"}]
        for provider in providers:
            with self.subTest(provider=provider):
                create = mock.Mock(return_value=completion())
                core = self.sdk_core(provider, create)
                result, _usage = core.call(retries=[])
                self.assertEqual(result, "answer")
                self.assertEqual(create.call_args.kwargs["model"], "test-model")
                self.assertNotIn("temperature", create.call_args.kwargs)
                self.assertNotIn("reasoning_effort", create.call_args.kwargs)

    def test_sdk_does_not_add_its_own_hidden_retries(self):
        core = RequestCore("groq")
        with mock.patch("openai.OpenAI") as client:
            core._openai_compatible_client_for_request("groq")
        self.assertEqual(client.call_args.kwargs["max_retries"], 0)

    def test_qwen_endpoint_change_replaces_a_cached_client(self):
        core = self.sdk_core("qwen", mock.Mock(return_value=completion()))
        old_client = core.universal_client
        core._universal_client_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        core.settings["qwen_base_url"] = "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
        with mock.patch("openai.OpenAI") as factory:
            client = core._openai_compatible_client_for_request("qwen")
        self.assertIsNot(client, old_client)
        self.assertEqual(factory.call_args.kwargs["base_url"], core.settings["qwen_base_url"])

    def test_invalid_endpoint_is_rejected_even_if_a_client_is_cached(self):
        core = self.sdk_core("qwen", mock.Mock(return_value=completion()))
        core.settings["qwen_base_url"] = "https://example.test:invalid/v1"
        with self.assertRaises(ApiRequestError) as failed:
            core._openai_compatible_client_for_request("qwen")
        self.assertEqual(failed.exception.analysis.reason, "invalid_server_url")

    def test_malformed_responses_output_has_a_protocol_diagnosis(self):
        core = RequestCore("openai")
        core.universal_client = SimpleNamespace(responses=SimpleNamespace(create=mock.Mock(return_value={"status": "completed", "output": ["bad"]})))
        with self.assertRaises(ApiRequestError) as failed:
            core.call(model="gpt-5-pro", retries=[])
        self.assertEqual(failed.exception.analysis.reason, "invalid_response")

    def test_current_sdk_sends_cache_options_without_an_unsupported_keyword(self):
        bodies = []
        def serve(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "chat-test", "object": "chat.completion", "created": 0, "model": "gpt-5.6", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "done"}}]})
        client = openai.OpenAI(api_key="test-key", max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(serve)))
        try:
            core = RequestCore("openai")
            core.universal_client = client
            text, _usage = core.call(model="gpt-5.6", retries=[])
            self.assertEqual(text, "done")
            self.assertEqual(len(bodies), 1)
            self.assertEqual(bodies[0]["prompt_cache_options"], {"mode": "explicit"})
        finally:
            client.close()

    def test_connection_timeouts_are_bounded_without_shortening_generation(self):
        core = RequestCore("openai")
        timeout = core._sdk_transport_timeout("openai")
        self.assertEqual((timeout.connect, timeout.read, timeout.write, timeout.pool), (15, 1800, 60, 15))
        self.assertEqual(core._provider_transport_timeout("gemini"), (15, 1800))
        self.assertIsNone(core._sdk_transport_timeout("local").read)

    def test_temporary_provider_client_is_closed_on_failure(self):
        core = RequestCore("openai")
        client = mock.Mock()
        client._smarti_request_owned = True
        client.chat.completions.create.side_effect = openai.BadRequestError("Bad request", response=httpx.Response(400, request=httpx.Request("POST", "https://example.test")), body={"error": {"code": "invalid_request_error"}})
        core._openai_compatible_client_for_request = mock.Mock(return_value=client)
        with self.assertRaises(ApiRequestError):
            core.call(retries=[])
        client.close.assert_called_once()

    def test_openai_pro_uses_responses_with_native_fields_and_image_conversion(self):
        core = RequestCore("openai")
        create = mock.Mock(return_value={"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}], "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}})
        core.universal_client = SimpleNamespace(responses=SimpleNamespace(create=create))
        messages = [{"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]}]
        result, usage = core._handle_api_request_with_retry("gpt-5-pro", messages, retry_wait_times=[], request_options={"reasoning_effort": "high", "max_output_tokens": 500})
        self.assertEqual((result, usage["total"]), ("done", 5))
        options = create.call_args.kwargs
        self.assertEqual(options["reasoning"], {"effort": "high"})
        self.assertEqual(options["max_output_tokens"], 500)
        self.assertEqual(options["input"][0]["content"][1]["type"], "input_image")
        self.assertFalse(options["store"])
        self.assertNotIn("messages", options)

    def test_incomplete_responses_output_is_preserved_with_reason(self):
        core = RequestCore("openai")
        create = mock.Mock(return_value={"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": [{"type": "message", "content": [{"type": "output_text", "text": "partial answer"}]}]})
        core.universal_client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with self.assertRaises(ApiRequestError) as failed:
            core.call(model="o3-pro", retries=[])
        self.assertEqual(failed.exception.analysis.reason, "response_token_limit")
        self.assertIn("partial answer", core._api_error_user_response(failed.exception.analysis))

    def test_anthropic_manual_thinking_budget_cannot_exceed_output_limit(self):
        core = RequestCore("anthropic")
        core._request_post = mock.Mock(return_value=response(200, {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn"}))
        core.call(model="claude-sonnet-4-5", retries=[], options={"reasoning_effort": "high", "max_output_tokens": 2000})
        payload = core._request_post.call_args.kwargs["json"]
        self.assertEqual((payload["max_tokens"], payload["thinking"]["budget_tokens"]), (2000, 1999))
        core._request_post.reset_mock()
        with self.assertRaises(ApiRequestError) as failed:
            core.call(model="claude-sonnet-4-5", retries=[], options={"reasoning_effort": "high", "max_output_tokens": 1000})
        self.assertEqual(failed.exception.analysis.reason, "output_limit")
        core._request_post.assert_not_called()

    def test_daily_quota_fails_without_retry_and_logs_same_message(self):
        core = RequestCore("gemini")
        post = mock.Mock(return_value=response(429, google_quota("GenerateRequestsPerDay-FreeTier", "20")))
        core._request_post = post
        with self.assertLogs(level="ERROR") as logs, self.assertRaises(ApiRequestError) as failed:
            core.call()
        self.assertEqual(failed.exception.analysis.reason, "daily_quota")
        self.assertEqual(post.call_count, 1)
        self.assertEqual(core.waits, [])
        self.assertIn(failed.exception.analysis.user_message, " ".join(logs.output))

    def test_minute_quota_retries_using_google_retry_delay(self):
        core = RequestCore("gemini")
        post = mock.Mock(side_effect=[response(429, google_quota("GenerateRequestsPerModelPerMinute-FreeTier")), response(200, {"candidates": [{"content": {"parts": [{"text": "done"}]}, "finishReason": "STOP"}]})])
        core._request_post = post
        self.assertEqual(core.call(retries=[1])[0], "done")
        self.assertEqual(core.waits, [12.5])
        self.assertEqual(post.call_count, 2)

    def test_zero_retry_delay_does_not_create_hot_retry_loop(self):
        create = mock.Mock(side_effect=openai.RateLimitError("Slow down", response=httpx.Response(429, headers={"retry-after": "0"}, request=httpx.Request("POST", "https://example.test")), body={"error": {"code": "rate_limit_exceeded"}}))
        core = self.sdk_core("groq", create)
        with self.assertRaises(ApiRequestError):
            core.call(retries=[1, 2])
        self.assertEqual(core.waits, [1, 1])
        self.assertEqual(create.call_count, 3)

    def test_excessive_retry_after_stops_without_shortening_server_wait(self):
        core = RequestCore("gemini")
        core._request_post = mock.Mock(return_value=response(429, google_quota("GenerateRequestsPerMinute-FreeTier"), {"retry-after": "3600"}))
        with self.assertRaises(ApiRequestError) as failed:
            core.call()
        self.assertFalse(failed.exception.analysis.retryable)
        self.assertEqual(core.waits, [])
        self.assertIn("60", str(failed.exception))

    def test_gemini_http_200_safety_and_recitation_are_diagnosed(self):
        for payload, reason in (({"promptFeedback": {"blockReason": "SAFETY"}}, "safety_blocked"), ({"candidates": [{"finishReason": "RECITATION"}]}, "recitation")):
            core = RequestCore("gemini")
            core._request_post = mock.Mock(return_value=response(200, payload))
            with self.assertRaises(ApiRequestError) as failed:
                core.call(retries=[])
            self.assertEqual(failed.exception.analysis.reason, reason)

    def test_generation_truncation_is_not_success(self):
        for provider in ("openai", "gemini", "anthropic"):
            if provider == "gemini":
                core = RequestCore(provider)
                core._request_post = mock.Mock(return_value=response(200, {"candidates": [{"content": {"parts": [{"text": "partial"}]}, "finishReason": "MAX_TOKENS"}]}))
            elif provider == "anthropic":
                core = RequestCore(provider)
                core._request_post = mock.Mock(return_value=response(200, {"content": [{"type": "text", "text": "partial"}], "stop_reason": "max_tokens"}))
            else:
                core = self.sdk_core(provider, mock.Mock(return_value=completion("partial", finish="length")))
            with self.subTest(provider=provider), self.assertRaises(ApiRequestError) as failed:
                core.call(retries=[])
            self.assertEqual(failed.exception.analysis.reason, "response_token_limit")
            self.assertIn("partial", core._api_error_user_response(failed.exception.analysis))

    def test_all_documented_gemini_stop_failures_have_distinct_reasons(self):
        codes = {"SAFETY": "safety_blocked", "BLOCKLIST": "blocklisted_terms", "PROHIBITED_CONTENT": "prohibited_content", "SPII": "sensitive_personal_data", "IMAGE_SAFETY": "image_safety", "IMAGE_PROHIBITED_CONTENT": "image_prohibited", "IMAGE_RECITATION": "image_recitation", "LANGUAGE": "unsupported_language", "NO_IMAGE": "image_missing", "IMAGE_OTHER": "image_generation_error", "UNEXPECTED_TOOL_CALL": "unexpected_tool_call", "TOO_MANY_TOOL_CALLS": "too_many_tool_calls", "MISSING_THOUGHT_SIGNATURE": "missing_thought_signature", "MALFORMED_RESPONSE": "invalid_response", "ESCALATION": "policy_escalation", "PUP_LIMITED_DISABLED": "account_disabled", "OTHER": "generation_interrupted"}
        for code, reason in codes.items():
            core = RequestCore("gemini")
            core._request_post = mock.Mock(return_value=response(200, {"candidates": [{"content": {"parts": [{"text": "partial"}]}, "finishReason": code}]}))
            with self.subTest(code=code), self.assertRaises(ApiRequestError) as failed:
                core.call(retries=[])
            self.assertEqual(failed.exception.analysis.reason, reason)

    def test_malformed_native_call_is_never_executed_even_if_present(self):
        core = RequestCore("gemini")
        core._request_post = mock.Mock(return_value=response(200, {"candidates": [{"content": {"parts": [{"functionCall": {"name": "tool", "args": {}}}]}, "finishReason": "MALFORMED_FUNCTION_CALL"}]}))
        with self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        self.assertEqual(failed.exception.analysis.reason, "malformed_tool_call")

    def test_empty_sdk_response_is_retried_then_stopped(self):
        create = mock.Mock(return_value=completion(""))
        core = self.sdk_core("local", create)
        with self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[1])
        self.assertEqual(failed.exception.analysis.reason, "empty_response")
        self.assertEqual(create.call_count, 2)

    def test_missing_sdk_choices_are_diagnosed(self):
        core = self.sdk_core("openrouter", mock.Mock(return_value=SimpleNamespace(usage=None, choices=[])))
        with self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        self.assertEqual(failed.exception.analysis.reason, "empty_response")

    def test_http_200_error_envelope_in_sdk_response_survives(self):
        from openai.types.chat import ChatCompletion
        error_response = ChatCompletion.model_validate({"id": "gen-1", "object": "chat.completion", "created": 1, "model": "test-model", "choices": [], "error": {"code": 402, "message": "No credits", "metadata": {"limit_source": "openrouter_key_limit"}}})
        core = self.sdk_core("openrouter", mock.Mock(return_value=error_response))
        with self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        self.assertEqual(failed.exception.analysis.reason, "key_spend_limit")

    def test_network_reconnect_can_only_reset_request_once(self):
        error = openai.APIConnectionError(request=httpx.Request("POST", "https://example.test"))
        create = mock.Mock(side_effect=error)
        core = self.sdk_core("openai", create)
        core._network_auto_resume_enabled = lambda: True
        core._network_probe_available = lambda: False
        core._wait_for_network_reconnect = mock.Mock(return_value=True)
        with self.assertRaises(ApiRequestError):
            core.call()
        self.assertEqual(core._wait_for_network_reconnect.call_count, 1)
        self.assertEqual(create.call_count, 5)

    def test_cancellation_during_retry_is_not_reclassified_as_api_failure(self):
        core = RequestCore("gemini")
        core._request_post = mock.Mock(return_value=response(503, {"error": {"message": "Unavailable"}}))
        core._sleep_with_cancel = mock.Mock(return_value=False)
        with self.assertRaisesRegex(Exception, "CANCELLED_BY_USER"):
            core.call()
        self.assertEqual(core._request_post.call_count, 1)

    def test_missing_key_is_caught_before_any_network_request(self):
        core = RequestCore("gemini")
        core._ensure_secret_loaded = lambda _key: ""
        core._request_post = mock.Mock()
        with self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        self.assertEqual(failed.exception.analysis.reason, "missing_key")
        core._request_post.assert_not_called()

    def test_non_json_success_body_is_a_protocol_failure(self):
        core = RequestCore("anthropic")
        core._request_post = mock.Mock(return_value=SimpleNamespace(status_code=200, json=mock.Mock(side_effect=ValueError("html"))))
        with self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        self.assertEqual(failed.exception.analysis.reason, "invalid_response")

    def test_malformed_response_shape_is_diagnosed(self):
        for provider, payload in (("gemini", {"candidates": [None]}), ("gemini", {"candidates": [{"content": "bad"}]}), ("anthropic", {"content": [None]})):
            core = RequestCore(provider)
            core._request_post = mock.Mock(return_value=response(200, payload))
            with self.subTest(provider=provider), self.assertRaises(ApiRequestError) as failed:
                core.call(retries=[])
            self.assertEqual(failed.exception.analysis.reason, "invalid_response")

    def test_invalid_native_arguments_do_not_turn_into_empty_tool_arguments(self):
        call = SimpleNamespace(id="call-1", function=SimpleNamespace(name="tool", arguments='{"unfinished":'))
        core = self.sdk_core("openai", mock.Mock(return_value=completion("", finish="tool_calls", calls=[call])))
        with self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        self.assertEqual(failed.exception.analysis.reason, "malformed_tool_call")

    def test_empty_array_arguments_in_rest_native_calls_are_rejected(self):
        for provider, body in (
            ("gemini", {"candidates": [{"content": {"parts": [{"functionCall": {"name": "read_file", "args": []}}]}, "finishReason": "STOP"}]}),
            ("anthropic", {"content": [{"type": "tool_use", "name": "read_file", "input": []}], "stop_reason": "tool_use"}),
        ):
            with self.subTest(provider=provider):
                core = RequestCore(provider)
                core._request_post = mock.Mock(return_value=response(200, body))
                with self.assertRaises(ApiRequestError) as failed:
                    core.call(retries=[])
                self.assertEqual(failed.exception.analysis.reason, "malformed_tool_call")

    def test_qwen_stream_required_error_switches_protocol_and_closes_stream(self):
        error = openai.BadRequestError("This model only supports stream mode", response=httpx.Response(400, request=httpx.Request("POST", "https://example.test")), body={"error": {"code": "InvalidParameter", "message": "This model only supports stream mode"}})
        stream = mock.MagicMock()
        stream.__iter__.return_value = iter([
            SimpleNamespace(choices=[SimpleNamespace(index=0, finish_reason=None, delta=SimpleNamespace(content="hel"))], usage=None),
            SimpleNamespace(choices=[SimpleNamespace(index=0, finish_reason="stop", delta=SimpleNamespace(content="lo"))], usage=None),
        ])
        create = mock.Mock(side_effect=[error, stream])
        core = self.sdk_core("qwen", create)
        result, _usage = core.call(retries=[])
        self.assertEqual(result, "hello")
        self.assertTrue(create.call_args.kwargs["stream"])
        stream.close.assert_called_once()

    def test_specific_failure_is_redacted_in_chat_and_logs_even_without_global_filter(self):
        core = RequestCore("gemini")
        core.settings["gemini_api_key"] = "test-secret-abcdef"
        core._request_post = mock.Mock(return_value=response(400, {"error": {"code": "INVALID_ARGUMENT", "message": "Bad test-secret-abcdef"}}))
        with self.assertLogs(level="ERROR") as logs, self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        rendered = core._api_error_user_response(failed.exception.analysis)
        self.assertNotIn("test-secret-abcdef", rendered + " ".join(logs.output))
        self.assertIn("INVALID_ARGUMENT", rendered)

    def test_redaction_precedes_diagnostic_truncation(self):
        core = RequestCore("gemini")
        secret = "private-key-123456789012345678901234567890"
        core.settings["gemini_api_key"] = secret
        core._request_post = mock.Mock(return_value=response(400, {"error": {"code": "INVALID_ARGUMENT", "message": "x" * 335 + secret}}))
        with self.assertLogs(level="ERROR") as logs, self.assertRaises(ApiRequestError) as failed:
            core.call(retries=[])
        rendered = core._api_error_user_response(failed.exception.analysis)
        self.assertNotIn("private-key", rendered + " ".join(logs.output))

    def test_real_loopback_sdk_http_error_reaches_chat_and_log(self):
        class Handler(BaseHTTPRequestHandler):
            requests_seen = 0

            def do_POST(self):
                type(self).requests_seen += 1
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("x-request-id", "loopback-request-123")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"code": "credit_balance_exhausted", "message": "Credits exhausted"}}).encode())

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = openai.OpenAI(base_url=f"http://127.0.0.1:{server.server_port}/v1", api_key="test-key", max_retries=0, timeout=5)
        try:
            core = RequestCore("openai")
            core.universal_client = client
            with self.assertLogs(level="ERROR") as logs, self.assertRaises(ApiRequestError) as failed:
                core.call()
            self.assertEqual(Handler.requests_seen, 1)
            self.assertEqual(failed.exception.analysis.reason, "credits_exhausted")
            self.assertIn("loopback-request-123", core._api_error_user_response(failed.exception.analysis))
            self.assertIn("credits_exhausted", " ".join(logs.output))
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
