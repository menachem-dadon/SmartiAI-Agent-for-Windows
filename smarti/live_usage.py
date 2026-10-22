"""Voice accounting is independent from execution-model token accounting."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime

from .common import USAGE_FILE


def daily_voice_seconds():
    try:
        with open(USAGE_FILE, encoding="utf-8") as stream:
            day = json.load(stream).get(datetime.now().strftime("%Y-%m-%d"), {})
        return sum(float(stats.get("voice_seconds", 0) or 0) for stats in day.values() if isinstance(stats, dict))
    except (OSError, ValueError, TypeError):
        return 0.0


def usage_snapshot(session, usage):
    totals = session.usage_totals
    def number(value):
        try:
            parsed = float(value or 0)
            return max(0, parsed) if math.isfinite(parsed) else 0
        except (TypeError, ValueError):
            return 0
    if session.provider == "openai":
        totals["voice_seconds"] = max(number(totals.get("voice_seconds")),
                                      number(getattr(session, "usage_base", {}).get("voice_seconds")) + number(usage.get("seconds")))
    else:
        # Local connected duration is explicitly an estimate, not billed duration.
        connected = getattr(session, "connected_at", None)
        totals["voice_seconds"] = max(float(totals.get("voice_seconds", 0)), time.monotonic() - connected if connected else 0)
        turn = getattr(session, "gemini_turn_usage", None)
        if turn is None: turn = session.gemini_turn_usage = {}
        for source, target in (("promptTokenCount", "prompt"), ("responseTokenCount", "completion"), ("totalTokenCount", "total")):
            turn[target] = max(int(turn.get(target, 0)), int(number(usage.get(source))))
            totals[target] = int(number(getattr(session, "usage_base", {}).get(target))) + turn[target]
    return totals
