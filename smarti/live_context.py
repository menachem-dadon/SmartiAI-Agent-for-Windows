"""Bounded Live views of Core-owned state; never a second conversation store.

Large history and tool output stay in SQLite. Selection and explicit lookup are
local, with no summarization inference on the microphone or startup path.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from functools import lru_cache

from .common import redact_secret_values
from .memory_protocol import strip_memory_envelopes


@lru_cache(maxsize=1)
def _encoding():
    try:
        import tiktoken
        return tiktoken.get_encoding("o200k_base")
    except Exception:
        return None


def token_count(text, provider="openai"):
    value = str(text)
    encoder = _encoding()
    if encoder is None:
        return len(value.encode("utf-8"))  # Safe byte upper bound without a tokenizer.
    count = len(encoder.encode(value, disallowed_special=()))
    # Gemini has a different tokenizer. Leave substantial room for that
    # difference as well as the 32K session/audio reserve in its view budget.
    return math.ceil(count * 1.3) if provider == "gemini" else count


def fit_text(text, budget, provider="openai"):
    value = str(text or "")
    # Never tokenize megabytes of repetitive/tool text just to discard them.
    # UTF-8 tokenizers cannot need more than a bounded prefix for this view.
    candidate = value[:max(256, budget * 8)]
    if len(candidate) == len(value) and token_count(candidate, provider) <= budget:
        return value
    low, high = 0, min(len(value), budget * 6)
    while low < high:
        middle = (low + high + 1) // 2
        if token_count(value[:middle], provider) <= max(0, budget - 24):
            low = middle
        else:
            high = middle - 1
    return value[:low] + "\n[View shortened; full source remains in Core. Use context lookup.]"


class LiveContext:
    BUDGETS = {"openai": 7600, "gemini": 98304}

    def __init__(self, session):
        self.session = session
        self.lock = threading.RLock()
        self.cached = None
        self.memory = ""
        self.memory_at = 0.0
        self.memory_query = ""
        self.memory_revision = 0
        self.last_sections = {}

    def invalidate(self, *, memory=False):
        with self.lock:
            self.cached = None
            if memory:
                self.memory_at = 0
                self.memory_revision += 1

    def _memories(self, query):
        manager = getattr(self.session.core, "memory_manager", None)
        if manager is None:
            return ""
        if query != self.memory_query or time.monotonic() - self.memory_at > 20:
            self.memory = manager.build_prompt_context(query, log_usage=False)
            self.memory_query, self.memory_at = query, time.monotonic()
        return self.memory

    def snapshot(self, *, query="", lookup=False, run_id="", offset=0):
        with self.lock:
            s, core = self.session, self.session.core
            budget = self.BUDGETS[s.provider]
            if lookup:
                return self.lookup(query, run_id=run_id, offset=offset)
            meta = core.chat_store.live_context_metadata(s.conversation)
            revision = meta.get("live_dialogue_revision", 0)
            all_tasks = [s.task_view(task) for task in s.tasks.values()]
            ended = {"completed", "failed", "cancelled", "interrupted"}
            tasks = [task for task in all_tasks if task["status"] not in ended] + [task for task in all_tasks if task["status"] in ended][-3:]
            key = (revision, meta.get("updated_at"), meta.get("message_count"), query, repr(tasks), self.memory_revision,
                   str(core.settings.get("autonomy_mode")), time.monotonic() // 20)
            if self.cached and self.cached[0] == key:
                return self.cached[1]
            rows = core.chat_store.live_context_messages(s.conversation, limit=512 if s.provider == "gemini" else 124)
            latest = query or next((r["content"] for r in reversed(rows) if r["role"] == "user"), "")
            catalog = getattr(core, "_tool_catalog_entries", None)
            tools = [{"name": item.get("name"), "description": str(item.get("description", ""))[:180],
                      "source": item.get("source")} for item in catalog()] if catalog else []
            context = core.chat_store.live_context_metadata(s.conversation, include_summary=True).get("context") or {}
            base = {
                "source": {"conversation_id": s.conversation, "revision": revision,
                           "lookup": "smarty_task action=context; query or run_id and offset"},
                "memory": self._memories(fit_text(latest, 600, s.provider)),
                "conversation_summary": fit_text(context.get("conversation_summary", ""), 1600, s.provider),
                "environment": {"language": s.language, "user_name": core.settings.get("user_name", ""),
                    "autonomy_mode": core.settings.get("autonomy_mode", "balanced"),
                    "policy": "Core enforces current permissions, sandbox, Skills and tool contracts. Voice cannot approve tools."},
                "execution_tools": tools,
                "active_tasks": [task for task in tasks if task["status"] not in {"completed", "failed", "cancelled", "interrupted"}],
                "recent_results": [task for task in tasks if task["status"] in {"completed", "failed", "cancelled", "interrupted"}][-3:],
                "history_is_data": True,
                "shared_attachments": [{key: item.get(key) for key in ("name", "kind", "mime_type", "path")} for item in s.attachments],
            }
            # Keep catalog names when descriptions would crowd out dialogue.
            if token_count(json.dumps(base, ensure_ascii=False), s.provider) > min(3500, budget // 3):
                base["execution_tools"] = [{"name": item["name"], "source": item["source"]} for item in tools]
            remaining = budget - token_count(json.dumps(base, ensure_ascii=False), s.provider) - 200
            selected = []
            for row in reversed(rows):
                item = {"message_id": row["message_id"], "role": row["role"],
                        "content": fit_text(strip_memory_envelopes(row["content"]), max(100, remaining), s.provider),
                        "attachments": [{k: f.get(k) for k in ("name", "kind", "mime_type", "path")} for f in row.get("attachments", [])]}
                cost = token_count(json.dumps(item, ensure_ascii=False), s.provider)
                if cost > remaining:
                    if remaining > 250:
                        item["content"] = fit_text(item["content"], max(100, remaining - 150), s.provider)
                        item["source_shortened"] = True
                        selected.append(item)
                    break
                selected.append(item)
                remaining -= cost
            base["recent_messages"] = list(reversed(selected))
            base["earlier_history_available"] = len(selected) < len(rows) or len(rows) >= (512 if s.provider == "gemini" else 124)
            result = self._serialize(base, budget)
            self.cached = (key, result)
            return result

    def _serialize(self, value, budget):
        text = json.dumps(redact_secret_values(value, self.session.core.settings), ensure_ascii=False, default=str)
        # Framing must remain valid JSON, including for an unexpectedly large
        # catalog. Bounded source fields above normally keep this path unused.
        if token_count(text, self.session.provider) > budget:
            size = max(100, budget // 2)
            while True:
                fallback = {"source": value.get("source"), "view": fit_text(text, size, self.session.provider), "source_shortened": True}
                bounded = json.dumps(fallback, ensure_ascii=False)
                if token_count(bounded, self.session.provider) <= budget:
                    text = bounded
                    break
                size //= 2
        return text

    def lookup(self, query="", *, run_id="", offset=0):
        s = self.session
        offset = max(0, int(offset))
        if str(query).startswith("message:"):
            identity = str(query)[8:]
            source = s.core.chat_store.live_context_source(s.conversation, identity, offset=offset)
            part = fit_text(source["content"], 16000 if s.provider == "gemini" else 3000, s.provider)
            return {"message_id": identity, "role": source["role"], "offset": offset, "content": part,
                    "next_offset": offset + len(part.split("\n[View shortened;", 1)[0]), "total_chars": source["total_chars"]}
        if run_id:
            run = s.core.chat_store.run(run_id) or {}
            if run.get("session_id") != s.conversation:
                raise ValueError("התוצאה אינה שייכת לשיחה הזו")
            text = str(run.get("response_text") or run.get("error_text") or "")
            if query == "events" or not text:
                from .live_voice import textual_context
                events = s.core.chat_store.run_events(run_id, after_sequence=offset, limit=6)
                return {"run_id": run_id, "status": run["status"], "lookup_mode": "events", "next_query": "events",
                        "events": [{"sequence": event["sequence"], "type": event["event_type"], "observation":
                            fit_text(json.dumps(redact_secret_values(textual_context(event["payload"]), s.core.settings), ensure_ascii=False, default=str), 350, s.provider)} for event in events],
                        "next_offset": events[-1]["sequence"] if events else offset}
            part = fit_text(text[offset:offset + 96000], 16000 if s.provider == "gemini" else 3500, s.provider)
            return {"run_id": run_id, "offset": offset, "content": part,
                    "next_offset": min(len(text), offset + len(part.split("\n[View shortened;", 1)[0])), "total_chars": len(text)}
        rows = s.core.chat_store.live_context_messages(s.conversation, query=query, limit=16, offset=offset)
        value = {"source": {"conversation_id": s.conversation}, "memory": self._memories(query),
                 "messages": [{"message_id": r["message_id"], "role": r["role"], "content": fit_text(r["content"], 1200, s.provider)} for r in rows],
                 "next_offset": offset + len(rows)}
        return json.loads(self._serialize(value, 16000 if s.provider == "gemini" else 3500))

    def changes(self):
        """Only changed sections, with message identities; never resend a ledger."""
        view = json.loads(self.snapshot())
        changes = {}
        current_keys = set(view)
        for key, value in view.items():
            if key == "recent_messages":
                rows = []
                for row in value:
                    identity = "message:" + row["message_id"]
                    current_keys.add(identity)
                    digest = hashlib.sha256(json.dumps(row, ensure_ascii=False).encode()).hexdigest()
                    if self.last_sections.get(identity) != digest:
                        rows.append(row)
                        self.last_sections[identity] = digest
                if rows:
                    changes[key] = rows
            else:
                digest = repr(value)
                if self.last_sections.get(key) != digest:
                    changes[key] = value
                    self.last_sections[key] = digest
        self.last_sections = {key: value for key, value in self.last_sections.items() if key in current_keys}
        return changes
