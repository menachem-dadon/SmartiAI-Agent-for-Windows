"""Real HTTP response objects and wire fixtures for provider error diagnosis."""
import json
import socket
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx
import openai
import requests

from smarti.api_errors import (
    analyze_api_error, api_error_for_reason, api_retry_exhausted_analysis,
    api_technical_details, api_user_technical_details,
)
from smarti.api_error_catalog import ERROR_REASONS
from smarti.common import MODEL_PROVIDER_ORDER, fetch_text_models_for_provider


def response(status, payload, headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode()
    result.headers.update(headers or {})
    return result


def google_quota(quota_id, quota_value=None):
    violation = {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests", "quotaId": quota_id}
    if quota_value is not None:
        violation["quotaValue"] = quota_value
    return {"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED",
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [violation]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "12.5s"},
        ],
    }}


class ApiErrorDiagnosisTests(unittest.TestCase):
    def test_real_failed_requests_response_keeps_body_headers_and_request_id(self):
        failed = response(429, {"error": {"code": "credit_balance_exhausted", "type": "insufficient_quota", "message": "Credits exhausted"}}, {"x-request-id": "req-123", "Retry-After": "30"})
        self.assertFalse(failed)
        analysis = analyze_api_error("openai", "test", response=failed)
        self.assertEqual((analysis.status_code, analysis.reason, analysis.request_id, analysis.retry_after), (429, "credits_exhausted", "req-123", 30))
        self.assertFalse(analysis.retryable)

    def test_every_provider_has_a_name_and_handles_standard_http_errors(self):
        cases = {401: "invalid_key", 402: "credits_exhausted", 403: "permission_denied", 408: "timeout", 413: "payload_too_large", 429: "rate_limit", 498: "server_overloaded", 500: "server_error", 502: "upstream_error", 503: "service_unavailable", 504: "gateway_timeout", 524: "gateway_timeout", 529: "server_overloaded"}
        for provider in MODEL_PROVIDER_ORDER:
            for status, reason in cases.items():
                with self.subTest(provider=provider, status=status):
                    analysis = analyze_api_error(provider, "example", response=response(status, {"error": {"message": "Request failed"}}))
                    self.assertEqual(analysis.reason, reason)
                    self.assertIn(analysis.provider_label, analysis.user_message)
                    self.assertNotEqual(analysis.provider_label, provider)

    def test_catalog_reasons_have_individual_guidance(self):
        messages = []
        for reason in ERROR_REASONS:
            analysis = api_error_for_reason("gemini", "example", reason)
            self.assertEqual(analysis.reason, reason)
            self.assertIn("reason=" + reason, api_technical_details(analysis))
            messages.append(analysis.user_message)
        self.assertEqual(len(messages), len(set(messages)))

    def test_google_free_minute_limits_are_retryable_despite_billing_boilerplate(self):
        for quota_id, reason in (("GenerateRequestsPerModelPerMinute-FreeTier", "request_rate"), ("GenerateInputTokensPerModelPerMinute-FreeTier", "token_rate")):
            analysis = analyze_api_error("gemini", response=response(429, google_quota(quota_id)))
            self.assertEqual(analysis.reason, reason)
            self.assertTrue(analysis.retryable)
            self.assertEqual(analysis.retry_after, 12.5)
            self.assertEqual(analysis.quota_id, quota_id)

    def test_google_daily_and_zero_quota_stop_even_with_retry_info(self):
        for quota_id, value, reason in (("GenerateRequestsPerDay-FreeTier", "20", "daily_quota"), ("GenerateRequestsPerMinute-FreeTier", "0", "quota_unavailable")):
            analysis = analyze_api_error("gemini", response=response(429, google_quota(quota_id, value)))
            self.assertEqual(analysis.reason, reason)
            self.assertFalse(analysis.retryable)
            self.assertIn(quota_id, " ".join(api_user_technical_details(analysis)))

    def test_google_error_info_identifies_expired_or_leaked_key(self):
        for code, reason in (("API_KEY_EXPIRED", "expired_key"), ("API_KEY_SERVICE_BLOCKED", "revoked_key")):
            payload = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Bad key", "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": code}]}}
            self.assertEqual(analyze_api_error("gemini", response=response(400, payload)).reason, reason)

    def test_insufficient_quota_has_provider_specific_meaning(self):
        payload = {"error": {"code": "insufficient_quota", "message": "You exceeded your current quota, please check your plan and billing details."}}
        self.assertEqual(analyze_api_error("openai", response=response(429, payload)).reason, "quota_exhausted")
        self.assertEqual(analyze_api_error("qwen", response=response(429, payload)).reason, "token_rate")

    def test_openai_billing_wire_codes_are_not_retried(self):
        for code, reason in (("organization_spend_limit_exceeded", "organization_spend_limit"), ("project_spend_limit_exceeded", "project_spend_limit"), ("organization_usage_limit_exceeded", "account_usage_limit")):
            analysis = analyze_api_error("openai", response=response(429, {"error": {"code": code, "type": "insufficient_quota", "message": "Limit exceeded"}}))
            self.assertEqual(analysis.reason, reason)
            self.assertFalse(analysis.retryable)

    def test_openrouter_inflight_budget_is_transient_even_with_http_402(self):
        payload = {"error": {"code": 402, "message": "Payment required", "metadata": {"limit_source": "openrouter_in_flight_budget"}}}
        analysis = analyze_api_error("openrouter", response=response(402, payload, {"Retry-After": "3"}))
        self.assertEqual(analysis.reason, "in_flight_budget")
        self.assertTrue(analysis.retryable)

    def test_openrouter_http_200_keeps_typed_upstream_error(self):
        payload = {"error": {"code": 400, "message": "Provider returned error", "metadata": {"error_type": "context_length_exceeded"}}, "choices": []}
        analysis = analyze_api_error("openrouter", response=response(200, payload))
        self.assertEqual((analysis.status_code, analysis.reason), (200, "context_length"))

    def test_together_context_error_overrides_http_403(self):
        analysis = analyze_api_error("together", response=response(403, {"error": {"message": "Input tokens plus max_tokens exceed the context length"}}))
        self.assertEqual(analysis.reason, "context_length")

    def test_qwen_free_only_exhaustion_overrides_http_403(self):
        analysis = analyze_api_error("qwen", response=response(403, {"code": "AllocationQuota.FreeTierOnly", "message": "Access denied"}))
        self.assertEqual(analysis.reason, "free_quota_exhausted")
        self.assertFalse(analysis.retryable)

    def test_zhipu_business_codes_are_not_http_status_codes(self):
        for code, reason in (("1113", "credits_exhausted"), ("1301", "content_policy"), ("1302", "rate_limit"), ("1305", "server_overloaded"), ("1211", "model_not_found"), ("1309", "subscription_expired"), ("1310", "weekly_monthly_quota"), ("1311", "model_permission")):
            self.assertEqual(analyze_api_error("zhipu", response=response(400, {"error": {"code": code, "message": "业务错误"}})).reason, reason)

    def test_network_root_cause_survives_sdk_wrapper(self):
        for cause, reason in ((socket.gaierror(11001, "getaddrinfo failed"), "dns_failure"), (ConnectionRefusedError("connection refused"), "connection_refused"), (ConnectionResetError("connection reset"), "connection_reset"), (httpx.ConnectTimeout(""), "connect_timeout"), (httpx.ReadTimeout(""), "read_timeout"), (httpx.WriteTimeout(""), "write_timeout"), (httpx.PoolTimeout(""), "pool_timeout"), (httpx.ProxyError(""), "proxy_failure")):
            error = openai.APIConnectionError(request=httpx.Request("POST", "https://example.test"))
            error.__cause__ = cause
            with self.subTest(reason=reason):
                self.assertEqual(analyze_api_error("openai", error=error).reason, reason)

    def test_tls_failures_are_distinct_and_not_retried(self):
        for message, reason in (("certificate has expired", "certificate_expired"), ("hostname mismatch", "certificate_hostname"), ("certificate verify failed", "certificate_untrusted"), ("TLS handshake failed", "tls_failure")):
            analysis = analyze_api_error("gemini", error=requests.exceptions.SSLError(message))
            self.assertEqual(analysis.reason, reason)
            self.assertFalse(analysis.retryable)

    def test_sdk_body_string_and_request_id_are_preserved(self):
        error = RuntimeError("failure")
        error.body = json.dumps({"error": {"code": "unsupported_parameter", "param": "temperature", "message": "Parameter unsupported"}})
        error.request_id = "req-sdk"
        analysis = analyze_api_error("openai", error=error)
        self.assertEqual((analysis.reason, analysis.param, analysis.request_id), ("unsupported_parameter", "temperature", "req-sdk"))

    def test_retry_after_date_and_milliseconds(self):
        from datetime import datetime, timedelta, timezone
        from email.utils import format_datetime
        for header, value, expected in (("Retry-After", "0", 0), ("retry-after-ms", "1250", 1.25)):
            analysis = analyze_api_error("groq", response=response(429, {}, {header: value}))
            self.assertEqual(analysis.retry_after, expected)
        date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=80))
        analysis = analyze_api_error("groq", response=response(429, {}, {"retry-after": date}))
        self.assertGreater(analysis.retry_after, 78)
        self.assertLessEqual(analysis.retry_after, 80)

    def test_retry_exhaustion_keeps_concrete_cause_and_waiting_stops(self):
        analysis = api_error_for_reason("local", "test", "connection_refused")
        exhausted = api_retry_exhausted_analysis(analysis)
        self.assertIn(analysis.user_message, exhausted.user_message)
        self.assertEqual(exhausted.reason, analysis.reason)
        self.assertFalse(exhausted.retryable)

    def test_error_message_keywords_do_not_override_server_code(self):
        analysis = analyze_api_error("gemini", response=response(503, {"error": {"message": "backend timeout for safety model"}}))
        self.assertEqual(analysis.reason, "service_unavailable")


class DiscoveryDiagnosisTests(unittest.TestCase):
    @mock.patch("smarti.common.requests.get")
    def test_failed_key_validation_logs_and_shows_reason_without_exposing_key(self, get):
        get.return_value = response(401, {"error": {"code": "invalid_api_key", "message": "Bad key sk-test-secret-987654"}})
        with self.assertLogs(level="WARNING") as logs:
            _models, ok, message = fetch_text_models_for_provider("openai", "sk-test-secret-987654", validate_key=True)
        self.assertFalse(ok)
        self.assertIn("invalid_key", message)
        self.assertNotIn("sk-test-secret-987654", message + " ".join(logs.output))

    @mock.patch("smarti.common.requests.get")
    def test_google_models_are_paginated(self, get):
        get.side_effect = [response(200, {"models": [{"name": "models/gemini-one", "supportedGenerationMethods": ["generateContent"]}], "nextPageToken": "next"}), response(200, {"models": [{"name": "models/gemini-two", "supportedGenerationMethods": ["generateContent"]}]})]
        models, ok, message = fetch_text_models_for_provider("gemini", "test-key")
        self.assertTrue(ok)
        self.assertEqual(set(models), {"gemini-one", "gemini-two"})
        self.assertEqual(get.call_args.kwargs["params"], {"pageToken": "next"})

    @mock.patch("smarti.common.requests.get")
    def test_huggingface_token_uses_authenticated_identity_endpoint(self, get):
        get.side_effect = [response(200, {"name": "test-user"}), response(200, {"data": [{"id": "test-model"}]})]
        _models, ok, _message = fetch_text_models_for_provider("huggingface", "test-key", validate_key=True)
        self.assertTrue(ok)
        self.assertEqual(get.call_args_list[0].args[0], "https://huggingface.co/api/whoami-v2")

    @mock.patch("smarti.common.requests.get")
    def test_qwen_discovery_and_validation_use_the_selected_endpoint(self, get):
        get.return_value = response(200, {"data": [{"id": "qwen-test"}]})
        url = "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
        _models, ok, _message = fetch_text_models_for_provider("qwen", "test-key", ssl_settings={"qwen_base_url": url}, validate_key=True)
        self.assertTrue(ok)
        self.assertEqual(get.call_args.args[0], url + "/models")

    def test_qt_validation_uses_qwen_endpoint_draft_and_retains_tls_settings(self):
        from smarti.ui_pages import SettingsPage
        harness = SimpleNamespace(
            core=SimpleNamespace(settings={"qwen_base_url": "https://old.test/v1"}),
            ssl_trust_card=SimpleNamespace(ssl_snapshot=lambda: {"ssl_trust_mode": "custom_ca", "ssl_custom_ca_path": "certificate.pem"}),
            qwen_url=SimpleNamespace(text=lambda: " https://workspace.test/v1/ "),
        )
        snapshot = SettingsPage._ssl_settings_from_ui(harness)
        self.assertEqual(snapshot["qwen_base_url"], "https://workspace.test/v1")
        self.assertEqual(snapshot["ssl_custom_ca_path"], "certificate.pem")

    @mock.patch("smarti.common.requests.get")
    def test_public_catalog_failure_is_not_hidden_after_authentication(self, get):
        get.side_effect = [response(200, {"data": {"label": "key"}}), response(503, {"error": {"message": "Unavailable"}})]
        _models, ok, message = fetch_text_models_for_provider("openrouter", "test-key", validate_key=True)
        self.assertTrue(ok)
        self.assertIn("service_unavailable", message)

    @mock.patch("smarti.common.requests.get")
    def test_catalog_network_failure_does_not_revoke_verified_authentication(self, get):
        get.side_effect = [response(200, {"data": {"label": "key"}}), requests.exceptions.ReadTimeout("catalog timeout")]
        _models, ok, message = fetch_text_models_for_provider("openrouter", "test-key", validate_key=True)
        self.assertTrue(ok)
        self.assertIn("read_timeout", message)

    @mock.patch("smarti.common.requests.get")
    def test_empty_local_catalog_is_not_success(self, get):
        get.return_value = response(200, {"data": []})
        _models, ok, message = fetch_text_models_for_provider("local")
        self.assertFalse(ok)
        self.assertIn("local_model_unloaded", message)

    @mock.patch("smarti.common.requests.get")
    def test_repeated_catalog_cursor_stops(self, get):
        get.return_value = response(200, {"models": [{"name": "models/gemini-one", "supportedGenerationMethods": ["generateContent"]}], "nextPageToken": "same"})
        _models, ok, message = fetch_text_models_for_provider("gemini", "test-key")
        self.assertFalse(ok)
        self.assertEqual(get.call_count, 2)
        self.assertIn("invalid_response", message)


if __name__ == "__main__":
    unittest.main()
