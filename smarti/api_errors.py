"""User-facing API error diagnosis and retry decisions for model providers."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import ast
import json
import math
import re
from .api_error_catalog import CODE_REASONS, ERROR_REASONS, PROVIDER_CODE_REASONS


PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI",
    "openai_codex_signin": "OpenAI Codex / ChatGPT",
    "anthropic": "Anthropic",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "nvidia": "NVIDIA NIM",
    "cerebras": "Cerebras",
    "huggingface": "Hugging Face",
    "deepseek": "DeepSeek",
    "qwen": "Alibaba Qwen",
    "zhipu": "Zhipu GLM",
    "moonshot": "Moonshot Kimi",
    "mistral": "Mistral AI",
    "together": "Together AI",
    "perplexity": "Perplexity",
    "xai": "xAI",
    "local": "השרת המקומי",
}


PROVIDER_CODE_HINTS = {
    "invalid_api_key": "המפתח עצמו לא התקבל אצל הספק",
    "authentication_error": "האימות מול הספק נכשל",
    "permission_error": "החשבון אומת אך אינו מורשה לבצע את הבקשה",
    "permission_denied": "החשבון אומת אך אינו מורשה לבצע את הבקשה",
    "insufficient_quota": "מכסת החשבון או יתרת החיוב הסתיימה",
    "resource_exhausted": "מכסת המשאב או קצב הבקשות נוצלו",
    "rate_limit_exceeded": "מגבלת הקצב של הספק נחצתה",
    "rate_limit_error": "מגבלת הקצב של הספק נחצתה",
    "model_not_found": "המודל המבוקש לא נמצא או אינו זמין לחשבון",
    "not_found_error": "המודל או המשאב המבוקש לא נמצא",
    "context_length_exceeded": "מספר הטוקנים עבר את חלון ההקשר של המודל",
    "request_too_large": "גודל הבקשה עבר את המגבלה של הספק",
    "invalid_argument": "הספק דחה פרמטר או מבנה בבקשה",
    "invalid_request_error": "הספק דחה פרמטר או מבנה בבקשה",
    "failed_precondition": "נדרשת הגדרה נוספת בחשבון או בפרויקט אצל הספק",
    "unsupported_parameter": "המודל אינו תומך באחד הפרמטרים שנשלחו",
    "overloaded_error": "השרת של הספק עמוס כרגע",
    "service_unavailable": "השירות של הספק אינו זמין כרגע",
    "internal_server_error": "הספק נתקל בתקלה פנימית",
}


@dataclass
class ApiErrorAnalysis:
    provider: str = ""
    provider_label: str = "ספק ה-AI"
    model: str = ""
    category: str = "unknown"
    retry_action: str = "none"  # none, immediate, delayed
    user_message: str = ""
    status_code: int = None
    error_type: str = ""
    error_code: str = ""
    error_status: str = ""
    param: str = ""
    raw_message: str = ""
    retry_after: float = None
    request_id: str = ""
    technical_summary: str = ""
    reason: str = "unknown"
    quota_metric: str = ""
    quota_id: str = ""
    quota_limit: str = ""
    partial_response: str = ""

    @property
    def retryable(self):
        return self.retry_action in {"immediate", "delayed"}


class ApiRequestError(Exception):
    """Exception carrying a diagnosed, user-facing API failure."""

    def __init__(self, analysis):
        self.analysis = analysis
        super().__init__(analysis.user_message)


def _provider_label(provider):
    return PROVIDER_LABELS.get(str(provider or "").strip().lower(), str(provider or "").strip() or "ספק ה-AI")


def _safe_status(value):
    try:
        if value is None or value == "":
            return None
        number = int(value)
        return number if 100 <= number <= 599 else None
    except Exception:
        return None


def _headers_dict(headers):
    if not headers:
        return {}
    try:
        return {str(k).lower(): str(v) for k, v in dict(headers).items()}
    except Exception:
        result = {}
        for key in ("retry-after", "request-id", "x-request-id", "x-ratelimit-reset"):
            try:
                value = headers.get(key)
            except Exception:
                value = None
            if value is not None:
                result[key] = str(value)
        return result


def _response_text(response):
    if response is None:
        return ""
    text = getattr(response, "text", "")
    if callable(text):
        try:
            text = text()
        except Exception:
            text = ""
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    return str(text or "")


def _response_payload(response):
    if response is None:
        return None, ""
    try:
        payload = response.json()
        if isinstance(payload, str):
            payload = json.loads(payload)
        return payload, _response_text(response)
    except Exception:
        text = _response_text(response)
        try:
            return json.loads(text), text
        except Exception:
            return None, text


def _payload_from_exception(error):
    body = getattr(error, "body", None)
    if isinstance(body, (dict, list)):
        return body, ""
    if isinstance(body, (str, bytes)):
        try:
            return json.loads(body), ""
        except (ValueError, TypeError):
            pass
    response = getattr(error, "response", None)
    payload, text = _response_payload(response)
    if payload is not None:
        return payload, text
    text = str(error or "")
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(candidate)
                if isinstance(parsed, (dict, list)):
                    return parsed, text
            except Exception:
                pass
    return None, text


def _find_first(obj, keys):
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj.get(key) not in (None, ""):
                return str(obj.get(key))
        for value in obj.values():
            found = _find_first(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_first(value, keys)
            if found:
                return found
    return ""


def _extract_error_fields(payload, fallback_text=""):
    error_obj = payload.get("error") if isinstance(payload, dict) and isinstance(payload.get("error"), dict) else payload
    # Do not search arbitrary request/response content for diagnostic fields.
    # OpenRouter's stable upstream type is in metadata.error_type; Google uses
    # ErrorInfo.reason in details, separately from its numeric HTTP code.
    error_obj = error_obj if isinstance(error_obj, dict) else {}
    metadata = error_obj.get("metadata") or {}
    metadata = metadata if isinstance(metadata, dict) else {}
    message = str(error_obj.get("message") or error_obj.get("detail") or error_obj.get("error_message") or error_obj.get("msg") or (payload.get("error") if isinstance(payload, dict) and isinstance(payload.get("error"), str) else "") or fallback_text)
    error_type = metadata.get("error_type") or error_obj.get("type") or error_obj.get("error_type") or ""
    error_code = error_obj.get("code") or error_obj.get("error_code") or ""
    error_status = _find_first(error_obj, ("status",))
    param = _find_first(error_obj, ("param", "parameter", "field"))
    request_id = (payload.get("request_id") or payload.get("requestId") or "") if isinstance(payload, dict) else ""
    return {
        "message": str(message or "").strip(),
        "type": str(error_type or "").strip(),
        "code": str(error_code or "").strip(),
        "status": str(error_status or "").strip(),
        "param": str(param or "").strip(),
        "request_id": str(request_id or "").strip(),
    }


def _payload_status(payload):
    if isinstance(payload, dict):
        status = _safe_status(payload.get("status"))
        if status is not None:
            return status
        code = _find_first(payload, ("status_code", "statusCode"))
        if not code and isinstance(payload.get("error"), dict):
            code = payload["error"].get("code")
        return _safe_status(code)
    return None


def _walk_values(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from _walk_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_values(value)
    elif obj is not None:
        yield str(obj)


def _parse_retry_delay(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    number_match = re.fullmatch(r"(\d+(?:\.\d+)?)", text)
    if number_match:
        return float(number_match.group(1))
    duration_match = re.fullmatch(r"(\d+(?:\.\d+)?)(?:\s*)(ms|s|sec|secs|second|seconds|m|min|minute|minutes)?", text, re.I)
    if duration_match:
        number = float(duration_match.group(1))
        unit = (duration_match.group(2) or "s").lower()
        if unit == "ms":
            return max(1.0, number / 1000.0)
        if unit.startswith("m"):
            return number * 60.0
        return number
    try:
        retry_date = parsedate_to_datetime(text)
        if retry_date.tzinfo is None:
            retry_date = retry_date.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_date - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


def _retry_after_seconds(headers, payload, message):
    headers = headers or {}
    for key in ("retry-after", "x-retry-after", "retry-after-ms"):
        seconds = _parse_retry_delay(headers.get(key))
        if seconds is not None and math.isfinite(seconds):
            return seconds / 1000.0 if key == "retry-after-ms" else seconds
    if payload is not None:
        values = list(_walk_values(payload))
        for index, value in enumerate(values):
            if value == "retryDelay" and index + 1 < len(values):
                seconds = _parse_retry_delay(values[index + 1])
                if seconds is not None:
                    return seconds
        for value in values:
            if "retry" in value.lower():
                seconds = _parse_retry_delay(value)
                if seconds is not None:
                    return seconds
    match = re.search(r"retry\s+(?:after|in)\s+(\d+(?:\.\d+)?)\s*(s|sec|seconds|m|min|minutes)?", str(message or ""), re.I)
    if match:
        unit = (match.group(2) or "s").lower()
        seconds = float(match.group(1))
        return seconds * 60.0 if unit.startswith("m") else seconds
    return None


def _exception_chain(error):
    seen, pending = set(), [error]
    while pending and len(seen) < 20:
        item = pending.pop(0)
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        yield item
        pending.extend([getattr(item, "__cause__", None), getattr(item, "__context__", None), getattr(item, "reason", None)])
        pending.extend(arg for arg in getattr(item, "args", ()) if isinstance(arg, BaseException))


def _diagnose_reason(provider, status, fields, payload, error, operation=""):
    explicit = getattr(error, "reason", "")
    if isinstance(explicit, str) and explicit in ERROR_REASONS:
        return explicit
    message = fields.get("message", "").casefold()
    if provider == "openai_codex_signin" and "model" in message and "not supported" in message and "chatgpt account" in message:
        return "signin_model_unsupported"
    codes = [str(fields.get(key, "")).casefold().replace("-", "_") for key in ("code", "status", "type")]
    details = payload.get("error", payload) if isinstance(payload, dict) else {}
    details = details if isinstance(details, dict) else {}
    # Only documented diagnostic objects; never search generated content.
    extra = details.get("details") or []
    for item in extra if isinstance(extra, list) else []:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("ErrorInfo"):
            codes.insert(0, str(item.get("reason", "")).casefold())
    metadata = details.get("metadata") or {}
    metadata = metadata if isinstance(metadata, dict) else {}
    limit_source = metadata.get("limit_source")
    if provider == "openrouter" and limit_source:
        mapped = {"openrouter_in_flight_budget": "in_flight_budget", "openrouter_key_limit": "key_spend_limit", "openrouter_credits": "credits_exhausted"}.get(limit_source)
        if mapped:
            return mapped
    provider_rules = PROVIDER_CODE_REASONS.get(provider, {})
    mapped = next((provider_rules[code] for code in codes if code in provider_rules), None)
    if mapped and mapped not in {"rate_limit", "invalid_parameter", "permission_denied"}:
        return mapped
    mapped = mapped or next((CODE_REASONS[code] for code in codes if code in CODE_REASONS), None)
    if mapped and mapped not in {"invalid_request", "permission_denied", "rate_limit", "quota_exhausted", "invalid_parameter"}:
        return mapped

    if provider == "gemini" and (status == 429 or "resource_exhausted" in codes):
        violations = []
        for item in extra if isinstance(extra, list) else []:
            if isinstance(item, dict) and str(item.get("@type", "")).endswith("QuotaFailure"):
                violations.extend(v for v in item.get("violations", []) if isinstance(v, dict))
        if any(str(v.get("quotaValue", "")) in {"0", "0.0"} for v in violations) or re.search(r"\blimit\s*:\s*0(?:\D|$)", message):
            return "quota_unavailable"
        quota_text = " ".join(str(v.get(k, "")) for v in violations for k in ("quotaId", "quotaMetric", "description")).casefold()
        if any(word in quota_text + " " + message for word in ("perday", "per_day", "per day", "daily quota", "requests per day", "tokens per day")):
            return "daily_quota"
        if "perminute" in quota_text or "per_minute" in quota_text:
            return "token_rate" if any(term in quota_text for term in ("token", "tokens")) else "request_rate"
        # Google's generic 429 text mentions billing even for minute limits.
        # Neither that boilerplate nor free_tier alone proves depleted credit.
        return "rate_limit"

    # Network exceptions usually wrap the actual DNS/TLS/socket exception.
    if status is None:
        chain = list(_exception_chain(error))
        network = " ".join(type(item).__name__ + " " + str(item) for item in chain).casefold()
        if "ssltrustconfigurationerror" in network:
            return "tls_configuration"
        if any(term in network for term in ("certificate has expired", "certificate expired")):
            return "certificate_expired"
        if any(term in network for term in ("hostname mismatch", "ip address mismatch", "not valid for")):
            return "certificate_hostname"
        if any(term in network for term in ("certificate verify failed", "certificateverifyfailed", "self signed certificate", "unable to get local issuer")):
            return "certificate_untrusted"
        if any(term in network for term in ("sslerror", "tls", "ssl:")):
            return "tls_failure"
        for kind in ("connect", "read", "write", "pool"):
            if kind + "timeout" in network or kind + " timed out" in network:
                return kind + "_timeout"
        if any(term in network for term in ("timeout", "timed out")):
            return "timeout"
        if "proxy authentication" in network or "407" in network and "proxy" in network:
            return "proxy_auth_required"
        if any(term in network for term in ("proxyerror", "proxy authentication", "tunnel connection failed")):
            return "proxy_failure"
        if any(term in network for term in ("gaierror", "nameresolutionerror", "name resolution", "getaddrinfo failed", "name or service not known", "nodename nor servname")):
            return "dns_failure"
        if any(term in network for term in ("connectionrefusederror", "connection refused", "actively refused", "winerror 10061")):
            return "connection_refused"
        if any(term in network for term in ("connectionreseterror", "connection reset", "remotedisconnected", "remoteprotocolerror", "connection aborted")):
            return "connection_reset"
        if any(term in network for term in ("apiconnectionerror", "connecterror", "connectionerror", "network is unreachable", "max retries exceeded")):
            return "network_failure"
        if any(term in network for term in ("invalidurl", "missingschema", "invalidschema", "unsupportedprotocol", "invalid url")):
            return "invalid_server_url"
        if any(term in network for term in ("jsondecodeerror", "apivalidationerror")):
            return "invalid_response"
        if any(term in network for term in ("importerror", "modulenotfounderror", "install the openai")):
            return "client_dependency"

    # Refine broad wire types by specific facts in the provider error message.
    # HTTP status wins over generic prose such as a model named "safety".
    patterns = (
        ("ip_restricted", ("ip not authorized", "ip address is not allowed", "ip allowlist")),
        ("region_restricted", ("unsupported country", "country, region", "unsupported location", "not available in your country")),
        ("expired_key", ("api key expired", "api key has expired", "key is expired")),
        ("revoked_key", ("key was revoked", "api key has been revoked", "api key was reported as leaked")),
        ("signin_usage_limit", ("usage limit", "usage_limit_reached")) if provider == "openai_codex_signin" else ("account_usage_limit", ("usage_limit_reached",)),
        ("credits_exhausted", ("insufficient balance", "insufficient credit", "credit balance exhausted", "out of credits", "余额不足")),
        ("organization_spend_limit", ("organization spend limit", "organization spending limit")),
        ("project_spend_limit", ("project spend limit", "workspace spend limit")),
        ("billing_required", ("enable billing", "free tier is not available", "set up billing", "setup a paid plan")),
        ("daily_quota", ("daily quota", "per day", "perday", "requests per day", "tokens per day")),
        ("context_length", ("context_length", "context length", "context window", "maximum context", "too many input tokens", "prompt is too long", "input is too long")),
        ("payload_too_large", ("request too large", "payload too large", "request size exceeds")),
        ("service_tier", ("invalid service_tier", "service tier is not allowed")),
        ("model_retired", ("decommissioned", "model has been deprecated", "model was retired")),
        ("model_permission", ("access to this model", "access to the model", "model is gated", "model access denied")),
        ("unsupported_modality", ("does not support image", "does not support audio", "does not support video", "unsupported content type")),
        ("invalid_attachment", ("invalid image", "image download failed", "unsupported image format", "could not process image", "invalid base64")),
        ("invalid_tool_schema", ("invalid schema for function", "invalid tool schema", "function_declarations", "input_schema", "tool schema")),
        ("invalid_history", ("tool_call_id", "messages must", "roles must", "messages: roles", "thought signature", "thought_signature", "function response", "tool_use_id")),
        ("unsupported_parameter", ("unsupported parameter", "unknown parameter", "unrecognized request argument", "not supported with this model", "unexpected keyword argument")),
        ("responses_required", ("only supported in the responses", "only supports the responses", "responses api only", "not supported in the v1/chat/completions endpoint")),
        ("stream_required", ("only support stream", "only supports stream", "only support with stream=true", "only support streaming", "enable_thinking only support stream", "enable_thinking must be set to false for non-streaming")),
        ("output_limit", ("max_tokens must", "max_completion_tokens must", "maxoutputtokens", "budget_tokens must", "thinking budget")),
        ("content_policy", ("content policy", "content_policy", "safety filter", "blocked by safety", "guardrail", "moderation")),
        ("concurrency_limit", ("concurrent request", "concurrency limit")),
        ("token_rate", ("tokens per minute", "tokens per second", "tokens per min", "limit on tokens", "tpm")),
        ("request_rate", ("requests per minute", "requests per second", "rpm", "slow down")),
        ("local_model_unloaded", ("no model loaded", "no models loaded", "model is not loaded")),
        ("model_not_found", ("model not found", "unknown model", "invalid model", "model does not exist")),
    )
    if status not in {500, 502, 503, 504, 529}:
        for reason, terms in patterns:
            if any(term in message for term in terms):
                return reason
    if mapped:
        return mapped
    if status == 401:
        return "invalid_key"
    if status == 402:
        return "credits_exhausted"
    if status == 403:
        return "permission_denied"
    if status == 404:
        return "endpoint_not_found" if operation == "models" or "endpoint" in message or "route" in message else "model_not_found"
    if status == 410:
        return "model_retired"
    if status == 407:
        return "proxy_auth_required"
    if status == 424:
        return "tool_dependency_failure"
    if status == 413:
        return "payload_too_large"
    if status in {408, 499}:
        return "timeout"
    if status in {504, 524}:
        return "gateway_timeout"
    if status == 429:
        return "rate_limit"
    if status in {498, 529}:
        return "server_overloaded"
    if status == 502:
        return "upstream_error"
    if status == 503:
        return "service_unavailable"
    if status is not None and status >= 500:
        return "server_error"
    if status in {400, 422}:
        return "invalid_request"
    return "unknown"


def api_error_for_reason(provider, model, reason, *, raw_message="", param=""):
    """Diagnose local preflight or an HTTP-200 generation failure."""
    category, retry_action, template = ERROR_REASONS[reason]
    label = _provider_label(provider)
    return ApiErrorAnalysis(
        provider=provider, provider_label=label, model=str(model or ""),
        reason=reason, category=category, retry_action=retry_action,
        user_message=template.format(label=label, model=model or "שנבחר"),
        raw_message=str(raw_message or ""), param=param,
        technical_summary=f"reason={reason} param={param} message={str(raw_message or '')}",
    )


def _status_note(status_code):
    return f" (קוד {status_code})" if status_code else ""


def _provider_code_note(fields):
    fields = fields or {}
    for key in ("status", "code", "type"):
        value = str(fields.get(key, "") or "").strip()
        normalized = value.casefold().replace("-", "_").replace(" ", "_")
        hint = PROVIDER_CODE_HINTS.get(normalized)
        if hint:
            return f" קוד הספק {value} מציין ש{hint}."
    return ""


def _technical_summary(status_code, fields, class_name):
    parts = []
    if status_code:
        parts.append(f"status={status_code}")
    for key in ("type", "code", "status", "param"):
        if fields.get(key):
            parts.append(f"{key}={fields[key]}")
    if class_name:
        parts.append(f"exception={class_name}")
    if fields.get("message"):
        parts.append(f"message={fields['message']}")
    return " ".join(parts)


def analyze_api_error(provider, model="", response=None, error=None, user_message_override=None, operation=""):
    provider = str(provider or "").strip().lower()
    label = _provider_label(provider)
    if isinstance(error, ApiRequestError):
        return error.analysis
    # requests.Response is false for 4xx/5xx. Preserve it and its diagnostics.
    if response is None:
        response = getattr(error, "response", None)
    headers = _headers_dict(getattr(response, "headers", None) or getattr(error, "headers", None))
    payload, text = _response_payload(response)
    if not isinstance(payload, (dict, list)) and error is not None:
        payload, text = _payload_from_exception(error)

    fields = _extract_error_fields(payload if isinstance(payload, dict) else {}, text or str(error or ""))
    status_code = _safe_status(getattr(response, "status_code", None))
    if status_code is None:
        status_code = _safe_status(getattr(error, "status_code", None))
    if status_code is None:
        status_code = _payload_status(payload)

    retry_after = _retry_after_seconds(headers, payload, fields.get("message", ""))
    class_name = error.__class__.__name__ if error is not None else ""
    diagnostic_status = status_code
    if status_code is not None and status_code < 400:
        diagnostic_status = _payload_status(payload)
    reason = _diagnose_reason(provider, diagnostic_status, fields, payload, error, operation)
    category, retry_action, template = ERROR_REASONS[reason]
    user_message = user_message_override or template.format(label=label, model=model or "שנבחר")
    user_message += _status_note(status_code) + "." if status_code else ""
    # Legacy broad code hints must not contradict the provider-specific reason
    # (e.g. Qwen's insufficient_quota denotes transient token throughput).
    if reason in {"invalid_request", "invalid_key", "permission_denied", "quota_exhausted", "rate_limit", "server_error", "context_length", "model_not_found"}:
        user_message += _provider_code_note(fields)
    if retry_after is not None and not math.isfinite(retry_after):
        retry_after = None
    request_id = headers.get("request-id") or headers.get("x-request-id") or getattr(error, "request_id", "") or fields.get("request_id") or headers.get("x-generation-id") or ""
    quota_metric = _find_first(payload, ("quotaMetric",))
    quota_id = _find_first(payload, ("quotaId",))
    quota_limit = _find_first(payload, ("quotaValue",))
    return ApiErrorAnalysis(
        provider=provider,
        provider_label=label,
        model=str(model or ""),
        category=category,
        reason=reason,
        quota_metric=quota_metric,
        quota_id=quota_id,
        quota_limit=quota_limit,
        retry_action=retry_action,
        user_message=user_message,
        status_code=status_code,
        error_type=fields.get("type", ""),
        error_code=fields.get("code", ""),
        error_status=fields.get("status", ""),
        param=fields.get("param", ""),
        raw_message=fields.get("message", ""),
        retry_after=retry_after,
        request_id=request_id,
        technical_summary=_technical_summary(status_code, fields, class_name),
    )


def api_retry_status_message(analysis, wait_seconds=0, next_attempt=1):
    label = analysis.provider_label
    wait_seconds = int(round(wait_seconds or 0))
    suffix = f" | ניסיון {next_attempt}" if next_attempt else ""
    if wait_seconds <= 0:
        return f"{analysis.user_message} {label}: מנסה שוב{suffix}..."
    return f"{analysis.user_message} ממתין {wait_seconds} שנ׳{suffix}"


def api_retry_exhausted_analysis(analysis, wait_too_long=False):
    if wait_too_long and analysis.retry_after:
        minutes = max(1, int(round(float(analysis.retry_after) / 60.0)))
        message = f"{analysis.user_message} הספק ביקש להמתין בערך {minutes} דקות. הניסיון האוטומטי נעצר; יש לנסות שוב לאחר ההמתנה."
    elif analysis.retryable:
        message = f"{analysis.user_message} הניסיונות האוטומטיים הסתיימו ללא הצלחה."
    else:
        message = analysis.user_message
    return replace(analysis, retry_action="none", user_message=message)


def api_technical_details(analysis, limit=420):
    if not analysis:
        return ""
    parts = [
        analysis.provider_label,
        f"category={analysis.category}",
        f"reason={analysis.reason}",
        f"retry={analysis.retry_action}",
    ]
    if analysis.model:
        parts.insert(1, f"model={analysis.model}")
    if analysis.retry_after is not None and analysis.category in {"rate_limit", "server_overload", "timeout", "network"}:
        try:
            parts.append(f"retry_after={int(round(float(analysis.retry_after)))}s")
        except Exception:
            parts.append(f"retry_after={analysis.retry_after}")
    if analysis.request_id:
        parts.append(f"request_id={analysis.request_id}")
    if analysis.quota_metric:
        parts.append(f"quota_metric={analysis.quota_metric}")
    if analysis.quota_id:
        parts.append(f"quota_id={analysis.quota_id}")
    if analysis.quota_limit:
        parts.append(f"quota_limit={analysis.quota_limit}")
    if analysis.technical_summary:
        parts.append(analysis.technical_summary)
    compact = re.sub(r"\s+", " ", " | ".join(str(part or "").strip() for part in parts if str(part or "").strip())).strip()
    if len(compact) > limit:
        compact = compact[:limit].rstrip() + "..."
    return compact


def api_redacted_analysis(analysis, redact):
    """Redact before truncation, which might otherwise cut a key in half."""
    return replace(analysis, **{
        name: redact(value)
        for name, value in vars(analysis).items()
        if isinstance(value, str)
    })


def api_user_technical_details(analysis):
    """Readable provider diagnostics for chat without exposing request content."""
    if not analysis:
        return []
    provider_line = f"ספק: {analysis.provider_label}"
    if analysis.model:
        provider_line += f" | מודל: {analysis.model}"
    provider_line += f" | קטגוריה: {analysis.category}"
    provider_line += f" | אבחון: {analysis.reason}"
    codes = []
    if analysis.status_code:
        codes.append(f"HTTP {analysis.status_code}")
    if analysis.error_code:
        codes.append(f"קוד ספק: {analysis.error_code}")
    if analysis.error_status:
        codes.append(f"סטטוס ספק: {analysis.error_status}")
    if analysis.error_type:
        codes.append(f"סוג שגיאה: {analysis.error_type}")
    if analysis.param:
        codes.append(f"פרמטר: {analysis.param}")
    rows = [provider_line]
    if codes:
        rows.append(" | ".join(codes))
    if analysis.request_id:
        rows.append(f"מזהה בקשה אצל הספק: {analysis.request_id}")
    if analysis.quota_metric or analysis.quota_id:
        rows.append(f"מכסה: {analysis.quota_id or analysis.quota_metric}" + (f" | מגבלה: {analysis.quota_limit}" if analysis.quota_limit else ""))
    if analysis.raw_message:
        rows.append("הסבר הספק: " + re.sub(r"\s+", " ", analysis.raw_message)[:350])
    if analysis.retry_after is not None:
        try:
            rows.append(f"המתנה שהתבקשה: {int(round(float(analysis.retry_after)))} שניות")
        except Exception:
            rows.append(f"המתנה שהתבקשה: {analysis.retry_after}")
    return rows


def api_validation_message(analysis):
    return analysis.user_message + "\n" + "\n".join(api_user_technical_details(analysis))
