"""Shared presentation framing for model-selected internal memory decisions."""
import re


MEMORY_TAGS = ("<smarti_memory>", "</smarti_memory>")
MODEL_MEMORY_BLOCK_RE = re.compile(
    r"<smarti_memory>\s*(.*?)\s*</smarti_memory>", re.IGNORECASE | re.DOTALL,
)
MEMORY_ENVELOPE_RE = re.compile(
    r"<smarti_memory>.*?(?:</smarti_memory>|$)|</smarti_memory>",
    re.IGNORECASE | re.DOTALL,
)


def strip_memory_envelopes(text):
    """Hide complete/incomplete blocks and split tags, without parsing operations."""
    visible = MEMORY_ENVELOPE_RE.sub("", str(text or ""))
    start = visible.rfind("<")
    if start >= 0 and any(tag.startswith(visible[start:].lower()) for tag in MEMORY_TAGS):
        visible = visible[:start]
    return visible
