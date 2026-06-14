"""User-facing API error diagnosis and retry decisions for model providers."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import ast
import json
import re


PROVIDER_LABELS = {
    "gemini": "Google Gemini",
    "openai": "OpenAI",
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
        return int(value)
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
        return response.json(), _response_text(response)
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
    message = _find_first(error_obj, ("message", "detail", "error_message", "msg")) or fallback_text
    error_type = _find_first(error_obj, ("type", "error_type"))
    error_code = _find_first(error_obj, ("code", "error_code"))
    error_status = _find_first(error_obj, ("status",))
    param = _find_first(error_obj, ("param", "parameter", "field"))
    request_id = _find_first(payload, ("request_id", "requestId", "id")) if isinstance(payload, dict) else ""
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
    for key in ("retry-after", "x-retry-after"):
        seconds = _parse_retry_delay(headers.get(key))
        if seconds is not None:
            return seconds
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


def _contains_any(text, words):
    return any(word in text for word in words)


def _status_note(status_code):
    return f" (קוד {status_code})" if status_code else ""


def _message_for(category, label, status_code=None):
    note = _status_note(status_code)
    if category == "auth":
        return f"מפתח ה-API של {label} נדחה. בדרך כלל זה אומר שהמפתח שגוי, נמחק, פג תוקף או שייך לחשבון אחר. פתח את ההגדרות והדבק מפתח תקין{note}."
    if category == "permission":
        return f"לחשבון או למפתח של {label} אין הרשאה להשתמש במודל, באזור או במשאב שנבחר. בדוק הרשאות אצל הספק או בחר מודל אחר{note}."
    if category == "billing_quota":
        return f"לחשבון של {label} אין כרגע יתרת שימוש זמינה, או שמכסת החיוב/הקרדיט נוצלה. צריך להוסיף קרדיט, להפעיל חיוב או להמתין לאיפוס המכסה{note}."
    if category == "rate_limit":
        return f"{label} מגביל כרגע את קצב הבקשות. סמארטי ימתין וינסה שוב אוטומטית{note}."
    if category == "server_overload":
        return f"יש עומס או תקלה זמנית בצד {label}. סמארטי ימתין וינסה שוב אוטומטית{note}."
    if category == "timeout":
        return f"השרת של {label} לא החזיר תשובה בזמן. זה יכול לקרות בגלל עומס זמני או חיבור איטי/מסונן{note}."
    if category == "network":
        return f"החיבור אל {label} נכשל. לרוב זה קשור לרשת, VPN/Proxy, סינון, חומת אש או אנטי-וירוס{note}."
    if category == "ssl":
        return f"שגיאת SSL מול {label}. בדרך כלל זה מצביע על סינון רשת, Proxy או אנטי-וירוס שמחליף תעודות."
    if category == "request_too_large":
        return f"הבקשה גדולה מדי עבור {label}. נסה לפתוח שיחה חדשה, לקצר את ההודעה או לבחור מודל עם חלון הקשר גדול יותר{note}."
    if category == "model_unavailable":
        return f"המודל שנבחר לא זמין בחשבון של {label}, לא קיים, או לא נתמך כרגע. בחר מודל אחר בהגדרות{note}."
    if category == "invalid_request":
        return f"הבקשה שנשלחה אל {label} לא התקבלה. לרוב זה קורה כשמודל לא תומך בפרמטר מסוים או כשהיסטוריית השיחה בפורמט לא מתאים. נסה לבחור מודל אחר או לפתוח שיחה חדשה{note}."
    if category == "content_blocked":
        return f"{label} חסם את הבקשה בגלל מדיניות בטיחות או תוכן. נסה לנסח את הבקשה אחרת{note}."
    if category == "provider_setup":
        return f"החשבון של {label} צריך הגדרת ספק נוספת, כמו הפעלת חיוב, אזור נתמך או הרשאה למודל שנבחר{note}."
    return f"התקבלה שגיאת API מ-{label}. נסה שוב, ואם זה חוזר בדוק את המפתח, המודל והחיבור לרשת{note}."


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
        parts.append(f"message={fields['message'][:300]}")
    return " ".join(parts)


def _classify(status_code, blob, retry_after):
    account_billing = _contains_any(blob, (
        "insufficient_quota", "insufficient quota", "insufficient credits", "insufficient credit",
        "insufficient balance", "out of balance", "balance too low", "run out of credits",
        "no credits", "billing", "payment", "monthly spend", "spending limit", "top up",
        "credit balance", "free_tier", "余额", "充值", "余额已用完",
    ))
    quota_exhausted = _contains_any(blob, (
        "quota has been exceeded", "current quota", "per day", "daily quota", "rpd",
    ))
    auth_terms = (
        "authentication", "unauthorized", "incorrect api key", "invalid api key", "invalid_api_key",
        "invalid api-key", "invalidapikey", "api key invalid", "wrong api key", "no api key",
        "missing api key", "no authorization header",
        "authorization token", "invalid authorization", "invalid token", "token非法", "鉴权失败",
    )
    permission_terms = (
        "permission", "permissiondeniederror", "forbidden", "not allowed", "not authorized", "ip not authorized",
        "country", "region", "territory", "unsupported location", "blocked", "guardrail",
        "moderation", "权限", "账户异常", "违规", "暂无 api 权限",
    )
    too_large_terms = (
        "request too large", "requesttoolargeerror", "context length", "context_length", "maximum context", "max context",
        "too many tokens", "token limit", "input is too long", "prompt is too long",
        "exceeds the max", "exceed context", "413", "文件大小超过",
    )
    model_terms = (
        "model not found", "notfounderror", "unknown_model", "unknown model", "invalid model", "model_not_found",
        "model is unavailable", "model unavailable", "not support this model", "does not support",
        "requested resource was not found", "not_found_error",
    )
    setup_terms = (
        "failed_precondition", "free tier is not available", "enable billing", "setup a paid plan",
        "billing account", "project", "api key doesn't have the required permissions",
    )
    rate_terms = (
        "rate limit", "rate_limit", "ratelimiterror", "too many requests", "resource_exhausted",
        "requests too quickly", "throttle", "concurrency", "rpm", "tpm", "rpd",
        "接口请求并发超额", "频率过快",
    )
    server_terms = (
        "overload", "overloaded", "server error", "internal server error", "internalservererror", "service unavailable",
        "temporarily unavailable", "bad gateway", "gateway timeout", "capacity", "server_error",
        "api_error", "backend", "upstream", "try again later",
    )
    timeout_terms = ("timeout", "apitimeouterror", "timed out", "read timed out", "request timed out", "response timeout")
    network_terms = (
        "connection error", "apiconnectionerror", "connection aborted", "connection reset",
        "remote disconnected", "dns", "name resolution", "proxy", "firewall", "network",
        "failed to establish a new connection", "max retries exceeded",
    )

    if _contains_any(blob, ("ssl", "certificate verify failed", "certificateverifyfailed")):
        return "ssl", "none"
    if _contains_any(blob, timeout_terms):
        return "timeout", "delayed"
    if status_code in {408, 499, 504}:
        return "timeout", "delayed"
    if status_code == 401 or _contains_any(blob, auth_terms):
        return "auth", "none"
    if _contains_any(blob, ("content policy", "safety", "moderation", "guardrail", "safety filter")):
        return "content_blocked", "none"
    if status_code == 403 or _contains_any(blob, permission_terms):
        return "permission", "none"
    if status_code == 402:
        return "billing_quota", "none"
    if status_code == 429 or _contains_any(blob, rate_terms):
        return "rate_limit", "delayed"
    if account_billing or quota_exhausted:
        return "billing_quota", "none"
    if status_code == 413 or _contains_any(blob, too_large_terms):
        return "request_too_large", "none"
    if _contains_any(blob, setup_terms):
        return "provider_setup", "none"
    if status_code == 404 or _contains_any(blob, model_terms):
        return "model_unavailable", "none"
    if status_code in {498, 500, 502, 503, 529} or _contains_any(blob, server_terms):
        return "server_overload", "delayed"
    if status_code in {400, 422} or _contains_any(blob, ("badrequesterror", "invalid_request", "invalid argument", "invalid_argument", "validation error", "unprocessable")):
        return "invalid_request", "none"
    if _contains_any(blob, network_terms):
        return "network", "immediate"
    return "unknown", "none"


def analyze_api_error(provider, model="", response=None, error=None, user_message_override=None):
    provider = str(provider or "").strip().lower()
    label = _provider_label(provider)
    response = response or getattr(error, "response", None)
    headers = _headers_dict(getattr(response, "headers", None))
    payload, text = _response_payload(response)
    if payload is None and error is not None:
        payload, text = _payload_from_exception(error)

    fields = _extract_error_fields(payload if isinstance(payload, dict) else {}, text or str(error or ""))
    status_code = _safe_status(getattr(response, "status_code", None))
    if status_code is None:
        status_code = _safe_status(getattr(error, "status_code", None))
    if status_code is None:
        status_code = _payload_status(payload)

    retry_after = _retry_after_seconds(headers, payload, fields.get("message", ""))
    class_name = error.__class__.__name__ if error is not None else ""
    blob = " ".join(
        str(value or "")
        for value in (
            fields.get("message"),
            fields.get("type"),
            fields.get("code"),
            fields.get("status"),
            fields.get("param"),
            class_name,
            text,
            str(error or ""),
        )
    ).lower()
    category, retry_action = _classify(status_code, blob, retry_after)
    user_message = user_message_override or _message_for(category, label, status_code)
    request_id = fields.get("request_id") or headers.get("request-id") or headers.get("x-request-id") or ""
    return ApiErrorAnalysis(
        provider=provider,
        provider_label=label,
        model=str(model or ""),
        category=category,
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
        return f"{label}: מנסה שוב מיד{suffix}..."
    return f"{label}: ממתין {wait_seconds} שנ׳{suffix}"


def api_retry_exhausted_analysis(analysis, wait_too_long=False):
    label = analysis.provider_label
    note = _status_note(analysis.status_code)
    if wait_too_long and analysis.retry_after:
        minutes = max(1, int(round(float(analysis.retry_after) / 60.0)))
        message = f"{label} ביקש להמתין בערך {minutes} דקות לפני ניסיון נוסף. כדי לא להשאיר את סמארטי תקוע, עצרתי כאן. נסה שוב מאוחר יותר או בחר מודל/ספק אחר{note}."
    elif analysis.category == "rate_limit":
        message = f"{label} עדיין מגביל את קצב הבקשות גם אחרי כמה ניסיונות. נסה שוב בעוד כמה דקות, או בחר מודל/ספק אחר{note}."
    elif analysis.category == "server_overload":
        message = f"השרת של {label} עדיין עמוס או מחזיר תקלה זמנית גם אחרי כמה ניסיונות. נסה שוב מאוחר יותר או בחר ספק אחר{note}."
    elif analysis.category in {"timeout", "network"}:
        message = f"החיבור אל {label} עדיין נכשל אחרי כמה ניסיונות. בדוק VPN/Proxy, סינון רשת, חומת אש או אנטי-וירוס ונסה שוב{note}."
    else:
        message = analysis.user_message
    return replace(analysis, retry_action="none", user_message=message)


def api_technical_details(analysis, limit=420):
    if not analysis:
        return ""
    parts = [
        analysis.provider_label,
        f"category={analysis.category}",
        f"retry={analysis.retry_action}",
    ]
    if analysis.model:
        parts.insert(1, f"model={analysis.model}")
    if analysis.retry_after is not None and analysis.category in {"rate_limit", "server_overload", "timeout", "network"}:
        try:
            parts.append(f"retry_after={int(round(float(analysis.retry_after)))}s")
        except Exception:
            parts.append(f"retry_after={analysis.retry_after}")
    if analysis.technical_summary:
        parts.append(analysis.technical_summary)
    if analysis.request_id:
        parts.append(f"request_id={analysis.request_id}")
    compact = re.sub(r"\s+", " ", " | ".join(str(part or "").strip() for part in parts if str(part or "").strip())).strip()
    if len(compact) > limit:
        compact = compact[:limit].rstrip() + "..."
    return compact


def api_validation_message(analysis):
    label = analysis.provider_label
    if analysis.category == "auth":
        return "המפתח נדחה: הוא שגוי, נמחק או פג תוקף."
    if analysis.category == "permission":
        return f"המפתח לא מורשה להשתמש ב-{label} או במודל שנבחר."
    if analysis.category == "billing_quota":
        return "המפתח תקין אולי, אבל אין לחשבון קרדיט/חיוב פעיל או שהמכסה נוצלה."
    if analysis.category == "rate_limit":
        return f"{label} הגביל זמנית את הבדיקה. נסה שוב בעוד רגע."
    if analysis.category == "server_overload":
        return f"{label} לא זמין כרגע לבדיקה. נסה שוב מאוחר יותר."
    if analysis.category == "network":
        return "בדיקת המפתח נכשלה בגלל בעיית רשת, Proxy, סינון או חומת אש."
    if analysis.category == "ssl":
        return "בדיקת המפתח נכשלה בגלל שגיאת SSL או סינון HTTPS."
    return analysis.user_message
