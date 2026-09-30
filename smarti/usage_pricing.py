"""Offline usage pricing with an independent background catalog refresh."""
from __future__ import annotations

import importlib.util
import json
import logging
import math
import os
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .common import USER_DATA_DIR
from .ssl_compat import create_ssl_context

PRICING_CATALOG_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
PRICING_CATALOG_MAX_AGE = 24 * 60 * 60
PRICING_RETRY_DELAY = 5 * 60
PRICING_MAX_BYTES = 8 * 1024 * 1024

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
    models = dict(models) if cached.get("version") == 1 and isinstance(models, dict) else {}
    # Keep the downloaded catalog separate from the legacy page's mutable cache.
    # Its current rates take precedence, even with an older LiteLLM installation.
    models.update(pricing_catalog().document().get("models", {}))
    return models


class UsagePricingCatalog:
    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._worker = None
        self._last_attempt = None
        self._refresh_failed = False

    def document(self):
        document = _read_object(self.path)
        if document.get("version") != 1 or not isinstance(document.get("models"), dict):
            return {}
        models = {
            name: {**rates, "_source": "remote"}
            for name, entry in document["models"].items()
            if (rates := _valid_rates(entry)) is not None
        }
        return {**document, "models": models} if models else {}

    def status(self):
        document = self.document()
        with self._lock:
            refreshing = self._worker is not None
            failed = self._refresh_failed
        return {
            "refreshing": refreshing, "refresh_failed": failed,
            "updated_at": document.get("updated_at", ""),
            "cached": bool(document.get("models")),
        }

    def request_refresh(self, ssl_settings=None):
        document = self.document()
        try:
            updated = datetime.fromisoformat(document.get("updated_at", ""))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - updated).total_seconds()
            if 0 <= age < PRICING_CATALOG_MAX_AGE:
                return False
        except (TypeError, ValueError):
            pass
        settings = {key: value for key, value in (ssl_settings or {}).items()
                    if key in {"ssl_trust_mode", "ssl_custom_ca_path", "_ssl_data_dir"}}
        with self._lock:
            now = time.monotonic()
            if self._worker is not None or (
                self._last_attempt is not None and now - self._last_attempt < PRICING_RETRY_DELAY
            ):
                return False
            self._last_attempt = now
            self._refresh_failed = False
            self._worker = threading.Thread(
                target=self._refresh, args=(settings,), daemon=True, name="SmartiUsagePricing",
            )
            try:
                self._worker.start()
            except Exception:
                self._worker = None
                self._refresh_failed = True
                return False
        return True

    def _download(self, settings):
        request = urllib.request.Request(PRICING_CATALOG_URL, headers={
            "Accept": "application/json", "User-Agent": "SmartiAI-UsagePricing",
        })
        context = create_ssl_context(
            settings, url=PRICING_CATALOG_URL, data_dir=self.path.parent, allow_legacy=False,
        )
        deadline = time.monotonic() + 20
        content = bytearray()
        with urllib.request.urlopen(request, timeout=8, context=context) as response:
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Pricing catalog download timed out")
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > PRICING_MAX_BYTES:
                    raise ValueError("Pricing catalog is too large")
        catalog = json.loads(content)
        if not isinstance(catalog, dict):
            raise ValueError("Invalid pricing catalog")
        models = {
            name: {**rates, "_source": "remote"}
            for name, info in catalog.items()
            if (rates := _catalog_rates(info)) is not None
        }
        if not models:
            raise ValueError("Pricing catalog contains no valid token rates")
        return models

    def _refresh(self, settings):
        temporary = None
        succeeded = False
        try:
            models = self._download(settings)
            # Retired or temporarily missing entries remain available offline.
            existing = self.document().get("models", {})
            existing.update(models)
            document = {
                "version": 1, "source": PRICING_CATALOG_URL,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "models": existing,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=".usage-pricing-", suffix=".tmp", delete=False,
            ) as handle:
                temporary = handle.name
                json.dump(document, handle, ensure_ascii=False, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            succeeded = True
        except Exception as exc:
            logging.debug("Usage pricing refresh unavailable; keeping local rates (%s)", type(exc).__name__)
        finally:
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
            with self._lock:
                self._worker = None
                self._refresh_failed = not succeeded


@lru_cache(maxsize=1)
def pricing_catalog():
    return UsagePricingCatalog(Path(USER_DATA_DIR) / "smarti_usage_price_catalog.json")


def request_pricing_refresh(ssl_settings=None):
    catalog = pricing_catalog()
    catalog.request_refresh(ssl_settings)
    return catalog.status()


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


def _catalog_rates(info):
    if not isinstance(info, dict):
        return None
    input_rate = info.get("input_cost_per_token")
    read_rate = info.get("cache_read_input_token_cost")
    if read_rate is None:
        read_rate = info.get("input_cost_per_token_cache_hit")
    if read_rate is None:
        read_rate = input_rate
    write_rate = info.get("cache_creation_input_token_cost")
    if write_rate is None:
        write_rate = input_rate
    return _valid_rates({
        "input": input_rate, "output": info.get("output_cost_per_token"),
        "cache_read": read_rate, "cache_write": write_rate,
    })


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
        rates = _catalog_rates(catalog.get(candidate))
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
