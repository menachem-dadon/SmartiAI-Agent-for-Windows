"""Local reasoning contracts. Discovery is read-only; controls are per prediction.

Native effort and hard budgets deliberately use different wire identities. This
keeps the existing ordered reasoning-write API atomic, including mode changes.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
from urllib.parse import urlsplit, urlunsplit

LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
LABELS = ("None", "Minimal", "Low", "Medium", "High", "XHigh", "Max")
BUDGETS = dict(zip(LEVELS, (0, 256, 1024, 4096, 8192, 16384, -1)))
_cache = {}
_lock = threading.Lock()


def endpoint(settings):
    return str(settings.get("local_server_url") or "http://localhost:1234/v1").strip().rstrip("/")


def endpoint_key(base):
    parsed = urlsplit(base)
    # Credentials are never copied to the preference identity or returned to UI.
    host = (parsed.hostname or "").lower()
    if ":" in host:
        host = "[" + host + "]"
    host += (":" + str(parsed.port)) if parsed.port else ""
    return urlunsplit((parsed.scheme.lower(), host, parsed.path.rstrip("/"), "", ""))


def run_base(core):
    context = getattr(core, "_execution_context", None)
    values = getattr(context, "run_values", None)
    frozen = values.get("local_reasoning_snapshot") if isinstance(values, dict) else None
    return frozen["base"] if frozen else endpoint(core.settings)


def _get(core, url):
    response = core._request_get(url, timeout=(1, 2))
    try:
        return response.json() if response.status_code == 200 else {}
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def _family(model, template=""):
    """Only documented families; an arbitrary 'reasoning' name proves nothing."""
    name = str(model).lower()
    if re.search(r"qwen[-_. ]?3[_. ]?8", name):
        return ["low", "medium", "xhigh"], "xhigh", True
    if "gpt-oss" in name or "gpt_oss" in name:
        return ["low", "medium", "high"], "medium", True
    thinking = any(token in name for token in ("qwen3", "qwen-3", "qwen3.5", "qwen3.6", "deepseek-r1", "deepseek-r", "gemma-4", "gemma4", "seed-oss", "nemotron", "thinking", "reasoning"))
    thinking = thinking or any(token in template for token in ("<think>", "thinking", "analysis", "<seed:think>"))
    return [], "", thinking


def _reasoning_parser(data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return False
    if not isinstance(data, dict):
        return False
    return bool(data.get("reasoning_parser")) or any(_reasoning_parser(value) for value in data.values() if isinstance(value, (dict, str)))


def discover(core, model, base=None):
    base = str(base or endpoint(core.settings)).rstrip("/")
    key = (endpoint_key(base), str(model))
    with _lock:
        cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < cached[2]:
        return copy.deepcopy(cached[1])
    parsed = urlsplit(base)
    root_path = parsed.path.rstrip("/")
    if root_path.endswith("/v1"):
        root_path = root_path[:-3]
    root = urlunsplit((parsed.scheme, parsed.netloc, root_path, "", ""))
    contract = {"kind": "compatible", "base": base, "root": root,
                "native": [], "default": "", "budget": False, "thinking": False}
    if callable(getattr(core, "_request_get", None)):
        try:
            data = _get(core, root + "/api/v1/models")
            models = data.get("models")
            if isinstance(models, list) and any(m.get("type") == "llm" and m.get("key") for m in models):
                contract["kind"] = "lmstudio"
                item = next((m for m in models if m.get("key") == model or any(i.get("id") == model for i in m.get("loaded_instances", []))), {})
                loaded = item.get("loaded_instances") or []
                contract["identifier"] = next((i["id"] for i in loaded if i.get("id") == model), loaded[0].get("id", model) if loaded else model)
                reasoning = (item.get("capabilities") or {}).get("reasoning") or {}
                native = [{"off": "none"}.get(v, v) for v in reasoning.get("allowed_options", [])]
                contract.update(native=native, default={"off": "none"}.get(reasoning.get("default"), reasoning.get("default", "")),
                                thinking=bool(reasoning) or _family(model)[2])
                # The official SDK's structured-chat budget supports GGUF runtimes
                # with usable reasoning delimiters. Never assume MLX has this.
                contract["budget"] = contract["thinking"] and item.get("format") == "gguf"
            else:
                # autoload=false matters on llama.cpp router servers.
                from urllib.parse import urlencode
                props = _get(core, root + "/props?" + urlencode({"model": model, "autoload": "false"}))
                if "default_generation_settings" in props and "chat_template" in props:
                    levels, default, thinking = _family(str(model) + " " + str(props.get("model_path") or ""), str(props.get("chat_template") or ""))
                    caps = props.get("chat_template_caps") or {}
                    template = str(props.get("chat_template") or "")
                    native = list(levels) if caps.get("supports_reasoning_effort") or "reasoning_effort" in template else []
                    if "enable_thinking" in template:
                        native = ["none", *native] if native else ["none", "on"]
                    generation = props.get("default_generation_settings") or {}
                    sampling = generation.get("params") or generation
                    reported_effort = sampling.get("reasoning_effort")
                    if reported_effort in native:
                        default = reported_effort
                    build = re.search(r"\bb?(\d{4,})\b", str(props.get("build_info") or ""))
                    # /props serializes sampling metrics, which omit the budget
                    # even on current builds. b8500 is a verified upstream floor
                    # with per-request thinking_budget_tokens support.
                    budget_supported = "reasoning_budget_tokens" in sampling or bool(build and int(build[1]) >= 8500)
                    # Builds before native budget support must not get fake stops.
                    contract.update(kind="llamacpp", native=native, default=default if default in native else ("on" if "on" in native else ""),
                                    budget=thinking and budget_supported, thinking=thinking)
                else:
                    version = _get(core, root + "/api/version")
                    if version.get("version"):
                        shown = {}
                        # Ollama show uses POST for model metadata; the API has no
                        # side effects (it never loads a model).
                        if not shown and callable(getattr(core, "_request_post", None)):
                            response = core._request_post(root + "/api/show", json={"model": model}, timeout=(1, 2))
                            try:
                                shown = response.json() if response.status_code == 200 else {}
                            finally:
                                if callable(getattr(response, "close", None)):
                                    response.close()
                        thinking = shown.get("thinking") or {}
                        values = thinking.get("values")
                        if values is None:
                            levels, default, capable = _family(model)
                            values = levels or ([False, True] if "thinking" in shown.get("capabilities", []) and capable else [])
                        native = ["on" if v is True else "none" if v is False else v for v in values]
                        if native == ["none"]:
                            native = []
                        default = thinking.get("default", _family(model)[1] or "on")
                        contract.update(kind="ollama", native=native, default="on" if default is True else "none" if default is False else default,
                                        thinking=bool(native))
                    else:
                        info = _get(core, root + "/get_server_info")
                        version_info = _get(core, root + "/version") if not info else {}
                        levels, default, thinking = _family(model)
                        if info.get("version") and ("server_args" in info or "enable_strict_thinking" in info):
                            args = info.get("server_args") or info
                            contract.update(kind="sglang", native=levels, default=default, thinking=thinking,
                                            budget=thinking and bool(args.get("enable_strict_thinking")))
                        elif version_info.get("version"):
                            schema = _get(core, root + "/openapi.json")
                            if "vllm" in str(schema.get("info", {})).lower():
                                server = _get(core, root + "/server_info")
                                schema_text = str(schema)
                                contract.update(kind="vllm", native=levels, default=default, thinking=thinking,
                                                budget=thinking and "thinking_token_budget" in schema_text and _reasoning_parser(server))
                            elif "localai" in str(schema.get("info", {})).lower():
                                # LocalAI's numeric cap is a load-time option,
                                # not a portable per-request budget control.
                                contract.update(kind="localai", native=levels, default=default, thinking=thinking)
        except Exception:
            # Offline/unknown is deliberately not a made-up reasoning contract.
            pass
    contract["native"] = [v for v in contract["native"] if v in (*LEVELS, "on")]
    if contract["default"] not in contract["native"]:
        contract["default"] = closest("medium", contract["native"])
    with _lock:
        if len(_cache) >= 128:
            _cache.pop(next(iter(_cache)), None)
        _cache[key] = (time.monotonic(), copy.deepcopy(contract), 300 if contract["kind"] != "compatible" else 5)
    return contract


def invalidate(core):
    base = endpoint_key(endpoint(core.settings))
    with _lock:
        for key in list(_cache):
            if key[0] == base:
                del _cache[key]


def options(contract):
    native = [{"value": value, "label": "On" if value == "on" else LABELS[LEVELS.index(value)]} for value in contract["native"]]
    budgets = [{"value": "budget:" + value, "label": label} for value, label in zip(LEVELS, LABELS)] if contract["budget"] else []
    # A binary toggle is not a native effort scale. Prefer budgets in that case.
    if native and not any(v["value"] not in {"none", "on"} for v in native) and budgets:
        return budgets
    return native + budgets


def selection(core, model, contract=None, base=None):
    base = base or endpoint(core.settings)
    contract = contract or discover(core, model, base)
    available = options(contract)
    all_values = core.settings.get("local_model_reasoning")
    server_values = all_values.get(endpoint_key(base)) if isinstance(all_values, dict) else None
    stored = server_values.get(str(model), "") if isinstance(server_values, dict) else ""
    if stored in {v["value"] for v in available}:
        return stored
    native = [v["value"] for v in available if not v["value"].startswith("budget:")]
    if native:
        # Capability changes remap a saved choice, not reset it to the default.
        return closest(stored, native) if stored else contract["default"]
    if available:
        return closest(stored, [v["value"] for v in available]) if stored else "budget:medium"
    return ""


def closest(value, candidates):
    level = str(value).removeprefix("budget:")
    rank = LEVELS.index(level) if level in LEVELS else 3
    def order(candidate):
        item = candidate.removeprefix("budget:")
        position = LEVELS.index(item) if item in LEVELS else 3
        return abs(position - rank), position
    return min(candidates, key=order) if candidates else ""


def describe(core, model, base=None):
    contract = discover(core, model, base)
    return {"provider": "local", "model": model, "reasoning_effort": selection(core, model, contract, base),
            "reasoning_options": [{**option, "endpoint": endpoint_key(contract["base"])} for option in options(contract)]}


def save(core, model, effort, contract=None):
    contract = contract or discover(core, model)
    if endpoint_key(contract["base"]) != endpoint_key(endpoint(core.settings)):
        raise ValueError("local_server_changed")
    if effort not in {v["value"] for v in options(contract)}:
        raise ValueError("unsupported_reasoning_effort")
    values = core.settings.setdefault("local_model_reasoning", {}).setdefault(endpoint_key(endpoint(core.settings)), {})
    values[str(model)] = effort
    return effort


def request_control(core, model, override=None):
    context = getattr(core, "_execution_context", None)
    values = getattr(context, "run_values", None)
    frozen = values.get("local_reasoning_snapshot") if isinstance(values, dict) else None
    if frozen and frozen.get("model") == model:
        result = copy.deepcopy(frozen)
    else:
        base = endpoint(core.settings)
        contract = discover(core, model, base)
        result = {"model": model, "base": base, "contract": contract, "effort": selection(core, model, contract, base)}
    if override is not None:
        candidates = [v["value"] for v in options(result["contract"])]
        result["effort"] = override if override in candidates else closest(override, candidates)
    return result


def parameters(control):
    contract, effort = control["contract"], control["effort"]
    if not effort:
        return {}
    budget = BUDGETS[effort[7:]] if effort.startswith("budget:") else None
    native = contract["default"] if budget is not None else effort
    if budget is not None and budget != 0 and native == "none":
        enabled = [v for v in contract["native"] if v != "none"]
        native = closest("medium", enabled) or "on"
    if budget == 0:
        native = "none"
    kind = contract["kind"]
    if kind == "lmstudio":
        return {"reasoning": "off" if native == "none" else native} if budget is None and native else {}
    if kind == "ollama":
        return {"think": True if native == "on" else False if native == "none" else native}
    result = {}
    if native and native != "on":
        result["reasoning_effort"] = native
    if native or budget is not None:
        result["chat_template_kwargs"] = {"enable_thinking": native != "none"}
    if budget is not None:
        if kind == "llamacpp":
            result["thinking_budget_tokens"] = budget
        elif kind == "vllm" and budget >= 0:
            result["thinking_token_budget"] = budget
        elif kind == "sglang" and budget >= 0:
            result["custom_params"] = {"thinking_budget": budget}
    return result
