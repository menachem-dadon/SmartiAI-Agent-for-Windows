"""Provider-independent live presentation. Never executes streamed tool input."""
import json
import re
import time
import uuid
from types import SimpleNamespace
from ..config import BUILTIN_TOOL_SCHEMAS
from ..memory_protocol import MEMORY_ENVELOPE_RE, strip_memory_envelopes


class ToolEnvelopeScanner:
    """Small JSON lexer: recognizes call headers, never names inside arguments."""
    def __init__(self):
        self.stack = []
        self.string = False
        self.escape = False
        self.value = ""
        self.path = ()
        self.key_string = False
        self.root = -1
        self.call_index = 0
        self.intent = False
        self.first_key = None
        self.complete = False
        self.methods = {}
        self.param_names = {}

    def call_scope(self, path):
        if len(path) == 1:
            return self.root * 8, path
        if len(path) >= 3 and path[0] == "tool_calls" and isinstance(path[1], int):
            return self.root * 8 + path[1], path[2:]
        return self.root * 8, path

    def feed(self, fragment):
        found = []
        for char in fragment:
            if self.string:
                if self.escape:
                    self.escape = False
                    if len(self.value) < 128:
                        self.value += "\\" + char
                elif char == "\\":
                    self.escape = True
                elif char == '"':
                    self.string = False
                    if self.key_string:
                        self.stack[-1]["key"] = self.value
                        self.stack[-1]["keys"] = False
                        if len(self.stack) == 1 and self.first_key is None:
                            self.first_key = self.value
                    else:
                        index, field = self.call_scope(self.path)
                        if field == ("method",) and (self.value == "tools/call" or self.path == ("method",) and self.value in BUILTIN_TOOL_SCHEMAS):
                            self.intent = True
                            self.call_index = index
                            self.methods[index] = self.value
                            found.append((index, self.param_names.get(index, "") if self.value == "tools/call" else self.value))
                        elif field == ("params", "name"):
                            self.param_names[index] = self.value
                            # In a direct builtin call params.name names an
                            # argument (e.g. a newly created tool), not the call.
                            if self.methods.get(index) == "tools/call":
                                self.call_index = index
                                found.append((index, self.value))
                        elif self.path[:1] == ("tool_calls",) and field in {("name",), ("tool",), ("action",), ("function", "name")}:
                            self.intent = True
                            self.call_index = index
                            found.append((index, self.value))
                elif len(self.value) < 128:
                    self.value += char
                continue
            frame = self.stack[-1] if self.stack else None
            path = (frame["path"] + ((frame["key"],) if frame["kind"] == "{" else (frame["index"],))) if frame else ()
            if char == '"':
                self.string, self.escape, self.value = True, False, ""
                self.key_string = bool(frame and frame["kind"] == "{" and frame["keys"])
                self.path = path
            elif char in "{[":
                if not self.stack:
                    self.root += 1
                    path = ()
                    self.first_key = None
                    self.complete = False
                if char == "[" and path == ("tool_calls",):
                    self.intent = True
                if char == "{" and len(path) == 2 and path[0] == "tool_calls":
                    self.call_index = self.root * 8 + path[1]
                    found.append((self.call_index, ""))
                self.stack.append({"kind": char, "path": path, "key": None, "keys": char == "{", "index": 0})
            elif char in "}]" and self.stack:
                self.stack.pop()
                if not self.stack:
                    self.complete = True
            elif char == "," and frame:
                if frame["kind"] == "{":
                    frame.update(key=None, keys=True)
                else:
                    frame["index"] += 1
        return found


class LiveResponse:
    """An attempt-scoped stream; its completed result still uses Core validation."""
    def __init__(self, emit=None, redact=lambda value: value, request_id=None, attempt=1, secrets=()):
        self.emit = emit or (lambda event: None)
        self.redact = redact
        self.secrets = tuple(str(value) for value in secrets if len(str(value or "")) >= 4)
        self.request_id = f"{request_id or uuid.uuid4().hex}:{attempt}"
        self.attempt = attempt
        self.raw = ""
        self.visible = ""
        self.calls = {}
        self.reports = {}
        self.report_visible = {}
        self.stage = "waiting"
        self.last_flush = 0.0
        self.pending = []
        self.text_tool = False
        self.tool_header = ""
        self.tool_scanner = ToolEnvelopeScanner()
        self.tool_candidate = None
        self.tool_candidate_size = 0
        self.tool_candidate_headers = []
        self.event("request_start", provider_stage="waiting")

    def safe(self, raw, final=False):
        if not final:
            for secret in self.secrets:
                for length in range(min(len(raw), len(secret) - 1), 0, -1):
                    if raw.endswith(secret[:length]):
                        raw = raw[:-length]
                        break
            raw = re.sub(r'(?:sk-|Bearer\s+|(?:api[_-]?key|token|secret)\s*[:=]\s*)\S*$', '', raw, flags=re.I)
        return self.redact(raw)

    def event(self, kind, **payload):
        event = {"kind": kind, "request_id": self.request_id, "attempt": self.attempt, **payload}
        if kind == "tool_preparing":
            self.pending = [value for value in self.pending if value.get("kind") != kind or value.get("call_id") != payload.get("call_id")]
        self.pending.append(event)
        # Coalesce fast tokens without a playback queue or a producer/UI handshake.
        if time.monotonic() - self.last_flush >= .024 or kind not in {"text_delta", "tool_preparing"}:
            self.flush()

    def flush(self):
        if self.pending:
            events, self.pending = self.pending, []
            for event in events:
                if event.get("kind") == "tool_preparing":
                    call = next((value for value in self.calls.values() if value["call_id"] == event["call_id"]), None)
                    event["arguments_text"] = ("[פרמטרים רגישים הוסתרו]" if call.get("sensitive_arguments") else self.safe(call["arguments"])) if call else ""
            self.emit({"events": events})
            self.last_flush = time.monotonic()

    def status(self, stage, percent=None):
        if stage != self.stage or percent is not None:
            self.stage = stage
            self.event("stage", provider_stage=stage, **({"percent": max(0, min(100, round(percent)))} if percent is not None else {}))

    def tool(self, index, name="", arguments="", provider_id="", name_delta=False):
        first = str(index) not in self.calls
        call = self.calls.setdefault(str(index), {"call_id": f"{self.request_id}:{index}", "name": "", "arguments": ""})
        call["name"] = call["name"] + name if name_delta else (name or call["name"])
        call["arguments_length"] = call.get("arguments_length", 0) + len(arguments)
        header = call.get("argument_header", "") + arguments
        if re.search(r'(?:\\?"|\b)(?:[\w-]*(?:password|secret|token|api[_-]?key|authorization)[\w-]*)(?:\\?"|\b)\s*:', header, re.I):
            call["sensitive_arguments"] = True
        call["argument_header"] = header[-512:]
        call["arguments"] = (call["arguments"] + arguments)[-12000:]
        if provider_id:
            call["provider_call_id"] = provider_id
        self.event("tool_preparing", block_id=call["call_id"], call_id=call["call_id"],
                   name=call["name"], arguments_length=call["arguments_length"])
        if first:
            self.event("text_role", block_id=self.request_id, role="report")
            self.flush()

    def report(self, delta, block_id, replacement=False):
        """Typed provider commentary stays separate from the final answer."""
        raw = str(delta or "") if replacement else self.reports.get(block_id, "") + str(delta or "")
        self.reports[block_id] = raw
        raw = re.sub(r'<think>.*?(?:</think>|$)|%%%.*?(?:%%%|$)', '', raw, flags=re.S)
        raw = re.sub(r'<(?:t(?:h(?:i(?:n(?:k)?)?)?)?)?$|%{1,2}$', '', raw)
        safe, previous = self.safe(strip_memory_envelopes(raw)), self.report_visible.get(block_id, "")
        if safe != previous:
            self.event("text_delta" if safe.startswith(previous) else "text_replace", block_id=block_id,
                       text=safe[len(previous):] if safe.startswith(previous) else safe, role="report")
            self.report_visible[block_id] = safe

    @staticmethod
    def _json_string(raw, key):
        match = re.search(r'"' + re.escape(key) + r'"\s*:\s*"', raw)
        if not match:
            return None
        value = raw[match.end():]
        # Decode a possibly incomplete JSON string without showing JSON framing.
        end = re.search(r'(?<!\\)(?:\\\\)*"', value)
        if end:
            value = value[:end.end() - 1]
        while value.endswith("\\"):
            value = value[:-1]
        value = re.sub(r'\\u[0-9a-fA-F]{0,3}$', '', value)
        try:
            return json.loads('"' + value + '"')
        except ValueError:
            return ""

    def text(self, delta, final=False):
        if self.text_tool:
            for index, name in self.tool_scanner.feed(str(delta or "")):
                self.tool(index, name)
            self.tool(self.tool_scanner.call_index, arguments=str(delta or ""))
            return
        self.raw += str(delta or "")
        raw = self.raw
        if re.search(r'<think>|<\|channel>thought', raw) and not re.search(r'</think>|<channel\|>|<\|channel>model', raw):
            self.status("thinking")
        # Framing is withheld from its first ambiguous byte, including split tags.
        raw = re.sub(r'<think>.*?(?:</think>|$)', '', raw, flags=re.S)
        raw = re.sub(r'<\|channel>thought.*?(?:<channel\|>|<\|channel>model|$)', '', raw, flags=re.S)
        raw = re.sub(r'<(?:t(?:h(?:i(?:n(?:k)?)?)?)?|\|channel[^>]*)?$', '', raw)
        raw = re.sub(r'%%%.*?(?:%%%|$)', '', raw, flags=re.S)
        raw = re.sub(r'%{1,2}$', '', raw)
        structured = re.match(r'\s*\{\s*"(?:kind|final_answer|progress_report)"\s*:', raw)
        if structured:
            # Codex's constrained output envelope identifies kind before content.
            value = self._json_string(raw, "final_answer")
            if value is None or re.search(r'"kind"\s*:\s*"tool_calls"', raw):
                value = self._json_string(raw, "progress_report") or ""
            if re.search(r'"kind"\s*:\s*"tool_calls"', raw) and re.search(r'"tool_calls"\s*:\s*\[', raw):
                self.tool_scanner = ToolEnvelopeScanner()
                for index, name in self.tool_scanner.feed(raw):
                    self.tool(index, name)
                self.text_tool = True
            raw = value or ""
        else:
            # A tool envelope must start at a line boundary. Code examples remain
            # ordinary Markdown unless the entire fenced response is a tool call.
            # Internal memory JSON is never a tool candidate. Keep raw tool
            # arguments intact, including literal memory tags in their content.
            memory_spans = list(MEMORY_ENVELOPE_RE.finditer(raw))
            match = next((candidate for candidate in re.finditer(r'(?:^|\n)(?:```(?:json)?\s*\n?)?\s*\{', raw)
                          if not any(span.start() <= candidate.end() - 1 < span.end() for span in memory_spans)), None)
            if match:
                tail = raw[match.start():]
                example = bool(re.search(r'(?:example|דוגמ[אה])', raw[:match.start()], re.I))
                if self.tool_candidate != match.start():
                    self.tool_candidate = match.start()
                    self.tool_candidate_size = 0
                    self.tool_candidate_headers = []
                    self.tool_scanner = ToolEnvelopeScanner()
                self.tool_candidate_headers.extend(self.tool_scanner.feed(tail[self.tool_candidate_size:]))
                self.tool_candidate_size = len(tail)
                is_call = self.tool_scanner.intent and not example
                undecided = not self.tool_scanner.complete and self.tool_scanner.first_key in {None, "method", "params", "jsonrpc", "id", "tool_calls"}
                if is_call:
                    if not self.calls and not self.tool_candidate_headers:
                        self.tool(0)
                    for index, name in self.tool_candidate_headers:
                        self.tool(index, name)
                    self.text_tool = True
                    self.tool_header = tail[-4096:]
                    self.tool(self.tool_scanner.call_index, arguments=tail)
                # Do not release an undecided JSON prefix. Once classified as a
                # non-tool object, let normal code/table rendering handle it.
                if is_call or (not final and undecided and not example):
                    raw = raw[:match.start()]
            elif not final:
                raw = re.sub(r'(?:^|\n)\s*`{1,3}(?:j(?:s(?:o(?:n)?)?)?)?\s*$', '', raw)
        # Filter decoded structured answers too, including JSON-escaped tags.
        safe = self.safe(strip_memory_envelopes(raw), final)
        if safe != self.visible:
            if safe.startswith(self.visible):
                self.event("text_delta", block_id=self.request_id, text=safe[len(self.visible):])
            else:
                self.event("text_replace", block_id=self.request_id, text=safe)
            self.visible = safe
            if self.calls:
                self.event("text_role", block_id=self.request_id, role="report")

    def finish(self, text="", has_tools=False):
        self.text("", final=True)
        self.event("request_end", block_id=self.request_id, role="report" if has_tools else "answer")
        self.flush()


def sse_objects(response, cancelled=lambda: None):
    """Read UTF-8 SSE frames independently of requests' HTTP charset guess."""
    data = []
    first_line = True
    try:
        # text/event-stream is UTF-8. requests guesses ISO-8859-1 for text/*
        # without a charset; decoding there corrupts non-ASCII text and may
        # split frames at Unicode separators inside JSON string values.
        for line in response.iter_lines(chunk_size=1, decode_unicode=False):
            cancelled()
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if first_line:
                line = line.removeprefix("\ufeff")
                first_line = False
            if not line:
                if data:
                    value = "\n".join(data)
                    data = []
                    if value != "[DONE]":
                        yield json.loads(value)
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data and "\n".join(data) != "[DONE]":
            yield json.loads("\n".join(data))
    finally:
        response.close()


def collect_http_stream(response, provider, live, cancelled):
    """Return the same full response shape used by existing budget/error checks."""
    if response.status_code >= 400 or not hasattr(response, "iter_lines"):
        return response
    if "text/event-stream" not in str(response.headers.get("Content-Type", "")):
        return response
    result, blocks, completed = {}, {}, False
    for event in sse_objects(response, cancelled):
        if event.get("error") or event.get("type") == "error":
            raise RuntimeError(json.dumps(event, ensure_ascii=False))
        if provider == "gemini":
            result.update({key: value for key, value in event.items() if key != "candidates"})
            candidate = (event.get("candidates") or [{}])[0]
            completed = completed or bool(candidate.get("finishReason") or (event.get("promptFeedback") or {}).get("blockReason"))
            dest = result.setdefault("candidates", [{"content": {"parts": []}}])[0]
            dest.update({key: value for key, value in candidate.items() if key != "content"})
            for part in (candidate.get("content") or {}).get("parts", []):
                if part.get("thought"):
                    live.status("thinking")
                elif "text" in part:
                    live.text(part["text"])
                elif "functionCall" in part:
                    call = part["functionCall"]
                    live.tool(len(live.calls), call.get("name", ""), json.dumps(call.get("args", {}), ensure_ascii=False), call.get("id", ""))
                dest["content"]["parts"].append(part)
        else:
            kind, index = event.get("type"), event.get("index", 0)
            if kind == "message_start":
                result = event.get("message") or {}
            elif kind == "content_block_start":
                block = dict(event.get("content_block") or {})
                blocks[index] = block
                if block.get("type") == "tool_use":
                    block["_args"] = ""
                    live.tool(index, block.get("name", ""), provider_id=block.get("id", ""))
                elif block.get("type") == "thinking":
                    live.status("thinking")
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                block = blocks.setdefault(index, {})
                if delta.get("type") == "text_delta":
                    block["text"] = block.get("text", "") + delta.get("text", "")
                    live.text(delta.get("text", ""))
                elif delta.get("type") == "input_json_delta":
                    block["_args"] = block.get("_args", "") + delta.get("partial_json", "")
                    live.tool(index, arguments=delta.get("partial_json", ""))
                elif delta.get("type") == "thinking_delta":
                    live.status("thinking")
            elif kind == "message_delta":
                result.update(event.get("delta") or {})
                result.setdefault("usage", {}).update(event.get("usage") or {})
            elif kind == "message_stop":
                completed = True
    if not completed:
        raise RuntimeError("Provider stream disconnected before completion")
    if provider != "gemini":
        for block in blocks.values():
            if "_args" in block:
                args = block.pop("_args")
                block["input"] = json.loads(args) if args else block.get("input", {})
        result["content"] = list(blocks.values())
    return SimpleNamespace(status_code=response.status_code, headers=response.headers,
                           text=json.dumps(result), json=lambda: result)
