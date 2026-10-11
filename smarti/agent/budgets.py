"""Observed daily budget estimates; never reserve or reduce a request's output."""
import json
import logging
import math
import os
import threading
import time
from datetime import datetime

from ..usage_pricing import bundled_pricing, model_rates, normalize_tokens, pricing_cache, usage_cost

_INITIALIZE_LOCK = threading.Lock()


class RequestBudgetMixin:
    def _remaining_task_seconds(self):
        deadline = getattr(getattr(self, "_execution_context", None), "task_deadline", None)
        if deadline is None:
            return None
        self._raise_if_cancelled()
        return max(0.01, deadline - time.monotonic())

    def _bounded_task_timeout(self, seconds):
        remaining = self._remaining_task_seconds()
        return seconds if remaining is None else min(float(seconds), remaining) if seconds is not None else remaining

    def _request_budget_lock(self):
        with _INITIALIZE_LOCK:
            if not getattr(self, "_usage_lock", None):
                self._usage_lock = threading.RLock()
        return self._usage_lock

    def _request_counts_toward_budget(self, model, mode):
        # Unknown prices and transports without an output contract are excluded
        # from both budget counters. General usage statistics remain available.
        from ..common import MODEL_PROVIDER_ORDER
        if mode == "openai_codex_signin" or mode not in MODEL_PROVIDER_ORDER:
            return False
        if (mode, model) in getattr(self, "_budget_unbounded_routes", set()):
            return False
        from . import model_context
        try:
            with open(model_context.USAGE_FILE, encoding="utf-8") as handle:
                history = json.load(handle)
            if any(mode in day[model].get("_unbounded_providers", []) for day in history.values() if isinstance(day, dict) and isinstance(day.get(model), dict)):
                return False
        except (OSError, ValueError, TypeError):
            pass
        return mode == "local" or model_rates(model, pricing_cache(), bundled_pricing()) is not None

    def _budget_stats(self, model, stats, cached, catalog):
        if "_budget_total" in stats:
            return int(stats["_budget_total"]), float(stats.get("_budget_cost_usd", 0))
        tokens = normalize_tokens(stats)
        if (str(model).lower().startswith("memory-rag/") or str(model).lower() == "smarti-memory-rag/local") or model_rates(model, cached, catalog) is None:
            return 0, 0.0
        cost, _ = usage_cost(model, stats, tokens, cached, catalog)
        # Existing free/subscription receipts do not consume a paid budget.
        return (tokens["tokens"], cost) if cost else (0, 0.0)

    def _daily_budget_usage(self, date_str=None):
        from . import model_context
        try:
            if not os.path.exists(model_context.USAGE_FILE):
                return 0, 0.0
            with open(model_context.USAGE_FILE, encoding="utf-8") as handle:
                data = json.load(handle)
            cached, catalog = pricing_cache(), bundled_pricing()
            tokens, cost = 0, 0.0
            for model, stats in data.get(date_str or datetime.now().strftime("%Y-%m-%d"), {}).items():
                if isinstance(stats, dict):
                    count, amount = self._budget_stats(model, stats, cached, catalog)
                    tokens += count
                    cost += amount
            return max(0, tokens), max(0.0, cost)
        except (OSError, ValueError, TypeError):
            logging.warning("Daily budget usage estimate is unavailable")
            return 0, 0.0

    def _check_request_budget(self, model, mode):
        budgets = self.settings.get("budgets") or {}
        tokens = max(0, int(budgets.get("daily_token_budget", 0) or 0))
        cost = float(budgets.get("daily_cost_budget_usd", 0) or 0)
        if not math.isfinite(cost) or cost < 0:
            raise RuntimeError("DAILY_COST_BUDGET_INVALID")
        if not (tokens or cost) or not self._request_counts_toward_budget(model, mode):
            return
        with self._request_budget_lock():
            used_tokens, used_cost = self._daily_budget_usage()
            if tokens and used_tokens >= tokens:
                raise RuntimeError("DAILY_TOKEN_BUDGET_EXCEEDED")
            if cost and used_cost >= cost:
                raise RuntimeError("DAILY_COST_BUDGET_EXCEEDED")

    def _request_usage_cost(self, model, usage, mode):
        if mode in {"local", "openai_codex_signin"}:
            return 0.0
        cost, _source = usage_cost(model, usage, normalize_tokens(usage), pricing_cache(), bundled_pricing())
        return cost
