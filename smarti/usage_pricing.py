"""Local usage pricing, without Qt, model calls or a LiteLLM network import."""
from __future__ import annotations

import importlib.util
import json
import math
from functools import lru_cache
from pathlib import Path

from .common import USER_DATA_DIR

# Shared with the legacy usage page; persisted/catalog rates take precedence.
USAGE_PRICING_FALLBACKS = {
    "gpt-5.6-sol": {
        "input": 0.000005, "output": 0.000030,
        "cache_read": 0.0000005, "cache_write": 0.00000625, "_source": "fallback",
    },
    "gemini/gemini-3.5-flash-lite": {
        "input": 0.0000003, "output": 0.0000025,
        "cache_read": 0.00000003, "cache_write": 0.0000003, "_source": "fallback",
    },
}


def _read_object(path):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def bundled_pricing():
    # Importing litellm itself can fetch a remote catalog and delay the page.
    try:
        spec = importlib.util.find_spec("litellm")
        if spec and spec.origin:
            return _read_object(Path(spec.origin).parent / "model_prices_and_context_window_backup.json")
    except (ImportError, ValueError):
        pass
    return {}


def pricing_cache():
    cached = _read_object(Path(USER_DATA_DIR) / "smarti_usage_cost_cache.json")
    models = cached.get("models")
    return models if cached.get("version") == 1 and isinstance(models, dict) else {}


def nonnegative_number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def token_count(stats, key, legacy=None):
    return int(nonnegative_number(stats.get(key, stats.get(legacy, 0))) or 0)


def normalize_tokens(stats):
    prompt = token_count(stats, "input_tokens", "prompt")
    completion = token_count(stats, "output_tokens", "completion")
    cached = min(prompt, token_count(stats, "cached_input_tokens", "cached_prompt"))
    written = min(prompt - cached, token_count(stats, "cache_write_tokens", "cache_write_prompt"))
    return {
        "input_tokens": prompt, "output_tokens": completion,
        "cached_input_tokens": cached, "cache_write_tokens": written,
        # Cache tokens are already part of prompt; reasoning is part of output.
        "tokens": max(prompt + completion, token_count(stats, "total_tokens", "total")),
    }


def _valid_rates(entry):
    if not isinstance(entry, dict) or entry.get("unpriced"):
        return None
    rates = {key: nonnegative_number(entry.get(key, entry.get("input") if key.startswith("cache_") else None))
             for key in ("input", "output", "cache_read", "cache_write")}
    return rates if all(value is not None for value in rates.values()) else None


def model_rates(model, cached, catalog):
    name = str(model).strip()
    lower = name.lower()
    if "gemini" in lower and not lower.startswith("gemini/"):
        name = f"gemini/{name}"
    elif "claude" in lower and not lower.startswith("anthropic/"):
        name = f"anthropic/{name}"
    candidates = [name]
    if "/" in name:
        candidates.append(name.split("/", 1)[1])
    # Only use exact catalog names (or their provider-qualified equivalent).
    for candidate in candidates:
        rates = _valid_rates(cached.get(candidate))
        if rates and cached[candidate].get("_source") != "fallback":
            return rates
    for candidate in candidates:
        info = catalog.get(candidate)
        if not isinstance(info, dict):
            continue
        input_rate = info.get("input_cost_per_token")
        read_rate = info.get("cache_read_input_token_cost")
        if read_rate is None:
            read_rate = info.get("input_cost_per_token_cache_hit")
        if read_rate is None:
            read_rate = input_rate
        write_rate = info.get("cache_creation_input_token_cost")
        if write_rate is None:
            write_rate = input_rate
        rates = _valid_rates({
            "input": input_rate, "output": info.get("output_cost_per_token"),
            "cache_read": read_rate, "cache_write": write_rate,
        })
        if rates:
            return rates
    return _valid_rates(cached.get(name)) or _valid_rates(USAGE_PRICING_FALLBACKS.get(name))


def usage_cost(model, stats, tokens, cached, catalog):
    for key in ("cost_usd", "estimated_cost_usd"):
        amount = nonnegative_number(stats.get(key))
        if amount is not None:
            return amount, "recorded" if key == "cost_usd" else "estimated"
    if str(model).lower().endswith(".gguf"):
        return 0.0, "local"
    rates = model_rates(model, cached, catalog)
    if rates is None:
        return None, "unavailable"
    read = tokens["cached_input_tokens"]
    written = tokens["cache_write_tokens"]
    amount = (
        (tokens["input_tokens"] - read - written) * rates["input"]
        + read * rates["cache_read"] + written * rates["cache_write"]
        + tokens["output_tokens"] * rates["output"]
    )
    return amount, "estimated"
