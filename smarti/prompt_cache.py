"""Provider cache controls and content-free measurements for growing agent history."""
import copy
import re


def openai_cache_controls(options, model, purpose, task_id, *, message_field="messages"):
    """Use native implicit caching plus reusable system/tool-result boundaries.

    Older models keep their native implicit cache. Standalone title/summary
    requests avoid paid writes on models supporting explicit-only mode.
    The source conversation is never mutated by wire-format annotations.
    """
    match = re.match(r"^gpt-(\d+)(?:\.(\d+))?(?:-|$)", str(model).lower())
    modern = bool(match and (int(match[1]), int(match[2] or 0)) >= (5, 6))
    if task_id and purpose == "agent":
        options["prompt_cache_key"] = f"smarti:{task_id}"
    if not modern:
        return
    options.setdefault("extra_body", {})["prompt_cache_options"] = {
        "mode": "implicit" if purpose == "agent" else "explicit"
    }
    if purpose != "agent":
        return
    messages = copy.deepcopy(options[message_field])
    initial = next((i for i, m in enumerate(messages) if m.get("role") in {"system", "developer"}), None)
    feedback = [i for i, m in enumerate(messages) if m.get("role") == "tool" or any(
        marker in str(m.get("content", "")) for marker in ("UNTRUSTED_TOOL_OUTPUT", "SMARTI_PARALLEL_TOOL_RESULTS")
    )]
    # One implicit + at most three explicit writes. Recent tool boundaries
    # preserve history, including browser prose, not merely system instructions.
    selected = ([initial] if initial is not None else []) + feedback[-2:]
    for index in dict.fromkeys(selected):
        message = messages[index]
        content = message.get("content")
        block_type = "input_text" if message_field == "input" else "text"
        if isinstance(content, str):
            content = message["content"] = [{"type": block_type, "text": content}]
        if isinstance(content, list):
            block = next((b for b in reversed(content) if isinstance(b, dict) and b.get("type") in {"text", "input_text"}), None)
            if block is not None:
                block["prompt_cache_breakpoint"] = {"mode": "explicit"}
    options[message_field] = messages


def remove_openai_cache_controls(options, *, message_field="messages"):
    """Retry unsupported controls without losing any message text or images."""
    options.pop("prompt_cache_key", None)
    body = options.get("extra_body", {})
    body.pop("prompt_cache_options", None)
    if not body:
        options.pop("extra_body", None)
    messages = copy.deepcopy(options.get(message_field, []))
    for message in messages:
        if isinstance(message.get("content"), list):
            for block in message["content"]:
                if isinstance(block, dict):
                    block.pop("prompt_cache_breakpoint", None)
    options[message_field] = messages


def cache_usage_metrics(usage, totals=None):
    """Aggregate counts; report hits, not an assumed discount or quota saving."""
    totals = totals if totals is not None else {}
    prompt = max(0, int(usage.get("prompt", 0) or 0))
    cached = min(prompt, max(0, int(usage.get("cached_prompt", 0) or 0)))
    written = min(prompt - cached, max(0, int(usage.get("cache_write_prompt", 0) or 0)))
    current = {"prompt": prompt, "cached": cached, "written": written,
               "uncached": prompt - cached - written,
               "completion": max(0, int(usage.get("completion", 0) or 0))}
    for key, value in current.items():
        totals[key] = totals.get(key, 0) + value
    totals["requests"] = totals.get("requests", 0) + 1
    return {**current, "hit_percent": round(100 * cached / prompt, 2) if prompt else 0,
            "sequence_hit_percent": round(100 * totals["cached"] / totals["prompt"], 2) if totals["prompt"] else 0,
            "sequence": dict(totals)}
