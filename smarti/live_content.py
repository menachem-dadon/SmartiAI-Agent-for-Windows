"""Explicit rich presentation from the executor's existing response, no extra inference."""
import re

OPEN, CLOSE = "<!--smarti-display-->", "<!--/smarti-display-->"
PRESENTATION_INSTRUCTIONS = (
    "Voice presentation only: preserve all normal execution rules and tool protocols. "
    "In your final response, surround visual-only Markdown (code, tables, exact links or diagrams) "
    "with <!--smarti-display--> and <!--/smarti-display-->. Keep each block in its intended document order. "
    "Write the explanatory prose normally. Do not add these markers to tool calls or memory envelopes. "
    "The app displays these blocks; the voice model speaks the surrounding explanation."
)


def display_content(text):
    return str(text).replace(OPEN, "").replace(CLOSE, "")


def presentation_blocks(text):
    """Explicit spans plus unmarked legacy Markdown, once and in source order."""
    explicit = [(m.start(), m.end(), m.group(1).strip()) for m in
                re.finditer(re.escape(OPEN) + r"(.*?)" + re.escape(CLOSE), str(text), re.S)]
    pattern = (r"```[^\n]*\n[\s\S]*?(?:```|\Z)"
        r"|^[^\n]*\|[^\n]*\n[ \t]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)+\|?[ \t]*(?:\n[^\n]*\|[^\n]*)*"
        r"|!?\[[^\]\n]+\]\([^\n)]+\)")
    spans = list(explicit)
    for match in re.finditer(pattern, str(text), re.MULTILINE):
        if not any(start < match.end() and end > match.start() for start, end, _ in spans):
            spans.append((match.start(), match.end(), match.group()))
    return sorted(spans)


def compose_transcript(spoken, source, fallback_blocks=""):
    """Place explicit blocks next to unchanged prose without another model.

    If the voice paraphrases an anchor, retain every block at the end rather
    than guessing a semantic position or replacing what the user actually heard.
    """
    matches = presentation_blocks(source)
    if not matches:
        return spoken + ("\n\n" + fallback_blocks if fallback_blocks else "")
    result, previous, cursor, remaining = spoken, 0, 0, []
    unplaced = False
    for start, end, block in matches:
        anchor = display_content(source[previous:start]).strip()
        index = result.find(anchor, cursor) if anchor else -1
        if index >= 0 and block and not unplaced:
            position = index + len(anchor)
            result = result[:position] + "\n\n" + block + "\n\n" + result[position:].lstrip()
            cursor = position + len(block) + 4
        elif block:
            unplaced = True
            remaining.append(block)
        previous = end
    return result + ("\n\n" + "\n\n".join(remaining) if remaining else "")
