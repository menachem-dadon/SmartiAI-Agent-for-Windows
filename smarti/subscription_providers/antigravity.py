"""Official Antigravity CLI with a private, minimal custom agent per request."""
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import base64
import io

from .base import SubscriptionError, SubscriptionProvider, register_models, safe_failure
from ..codex_signin import CodexProtocolError, SMARTI_TURN_OUTPUT_SCHEMA
from ..common import SmartiCancelled

# The CLI translates this schema for different model families. Non-nullable
# inactive fields avoid stringified "null" in Claude/GPT finish calls. Core's
# existing nullable contract is restored before its strict local validation.
ANTIGRAVITY_TURN_SCHEMA = json.loads(json.dumps(SMARTI_TURN_OUTPUT_SCHEMA))
for _field in ("progress_report", "final_answer"):
    ANTIGRAVITY_TURN_SCHEMA["properties"][_field]["type"] = "string"
ANTIGRAVITY_TURN_SCHEMA["properties"]["tool_calls"]["type"] = "array"

EFFORTS = ("low", "medium", "high", "xhigh", "max")


class _TurnComplete(Exception):
    """A validated Smarti packet ends this process before the CLI agent retries."""

    def __init__(self, output, usage):
        self.output = output
        self.usage = usage


def split_model(model):
    """Suffixes are presentation/control metadata; the raw ID stays persisted."""
    base, separator, effort = str(model).rpartition("-")
    return (base, effort) if separator and effort in EFFORTS else (str(model), "")


class AntigravityProvider(SubscriptionProvider):
    provider = "google_antigravity_signin"
    label = "Google Antigravity"
    install_url = "https://www.antigravity.google/docs/cli/install/"
    minimum_version = (1, 4, 2)

    def environment(self):
        env = super().environment()
        # Never turn a subscription request into an API/Cloud billed request.
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI",
                    "AGY_ADC_AUTH", "GOOGLE_GEMINI_BASE_URL"):
            env.pop(key, None)
        return env

    def executable(self):
        override = os.environ.get("SMARTI_AGY_CLI")
        if override:
            if Path(override).is_file():
                return override
            raise SubscriptionError("נתיב Antigravity שהוגדר אינו קיים.", "missing_dependency")
        for candidate in (
                str(Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"), shutil.which("agy")):
            if candidate and Path(candidate).is_file():
                return candidate
        raise SubscriptionError("רכיב Antigravity אינו מותקן. יש לפתוח את ההתקנה הרשמית.", "missing_dependency")

    def connection_status(self):
        if self.disconnected:
            return self.state("disconnected", "Antigravity מנותק מ-Smarti.")
        try:
            version = self.version()
            quota = self.quota()
            return self.state("connected", "Antigravity מחובר דרך הכלי הרשמי. Smarti מנהל את הכלים וההרשאות.",
                version=version, inference_available=True, quota_available=quota["available"], quota=quota,
                text_only=False)
        except SubscriptionError as error:
            return self.state(error.reason, str(error), inference_available=False)

    def version(self):
        value = self.run([self.executable(), "--version"], timeout=10).strip()
        match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", value)
        version = tuple(map(int, match.groups())) if match else ()
        if not version or version < self.minimum_version or version[0] != 1:
            raise SubscriptionError("נדרשת גרסת Antigravity CLI תואמת, 1.4.2 ומעלה, עם בידוד הסוכן המותאם.", "incompatible_version")
        return match.group(0)

    def quota(self):
        raw = self.run([self.executable(), "-p", "/usage", "--output-format", "json"], timeout=30)
        try:
            data = json.loads(raw)
            command = data.get("command", {})
            if data.get("status") != "SUCCESS":
                raise safe_failure(data.get("error"))
            if command.get("name") != "usage" or data.get("num_turns") != 0:
                raise ValueError("not a read-only usage command")
            groups = []
            for group in command.get("data", {}).get("groups", []):
                buckets = []
                for bucket in group.get("buckets", []):
                    fraction = bucket.get("remaining_fraction")
                    if isinstance(fraction, (int, float)) and not isinstance(fraction, bool) and 0 <= fraction <= 1:
                        buckets.append({"name": str(bucket.get("name", ""))[:128],
                            "window": str(bucket.get("window", ""))[:32], "remaining_fraction": fraction,
                            "reset_time": str(bucket.get("reset_time", ""))[:64]})
                if buckets:
                    groups.append({"name": str(group.get("name", ""))[:128], "buckets": buckets})
            return {"available": bool(groups), "source": "reported", "groups": groups}
        except (ValueError, TypeError, AttributeError) as error:
            raise SubscriptionError("פלט אימות החשבון והמכסה אינו תואם. יש לבדוק את גרסת Antigravity ולהתחבר בכלי הרשמי.", "incompatible_version") from error

    def catalog(self):
        with self._lock:
            output = self.run([self.executable(), "models"], timeout=30)
            rows = []
            for line in output.splitlines():
                match = re.match(r"^([a-z0-9][a-z0-9._/-]+)\s+(.+)$", line.strip())
                if match:
                    base, effort = split_model(match[1])
                    rows.append({"id": match[1], "label": match[2].strip(), "base_model": base,
                        "model_effort": effort, "availability": "unknown"})
            for row in rows:
                row["efforts"] = [level for level in EFFORTS if any(
                    other["base_model"] == row["base_model"] and other["model_effort"] == level for other in rows)]
            self.models = rows
            register_models(self.provider, rows)
            return rows

    def ensure_catalog(self):
        with self._lock:
            return self.models or self.catalog()

    def resolve_model(self, model, effort=""):
        rows = self.ensure_catalog()
        selected = next((row for row in rows if row["id"] == model), None)
        if not selected:
            raise SubscriptionError("יש לבחור מודל מתוך הרשימה הרשמית של Antigravity.", "model_unavailable")
        if not effort:
            return model
        base, suffix = split_model(model)
        match = next((row for row in rows if split_model(row["id"]) == (base, effort)), None)
        if not suffix or not match:
            raise SubscriptionError("רמת החשיבה שנבחרה אינה זמינה למודל בקטלוג Antigravity.", "unsupported_reasoning_effort")
        return match["id"]

    @staticmethod
    def text_documents(messages, model):
        """CLI third-party models need PDF text in the prompt, not PDF blobs.

        Keep original history immutable, and explicitly identify visual loss.
        Gemini retains the full PDF transport below.
        """
        if not model.startswith(("claude-", "gpt-")):
            return messages
        prepared = []
        for message in messages:
            blocks = message.get("content")
            if not isinstance(blocks, list):
                prepared.append(message)
                continue
            content = []
            for block in blocks:
                source = block.get("source", {}) if isinstance(block, dict) else {}
                if not isinstance(block, dict) or block.get("type") != "document" or source.get("type") != "base64" or source.get("media_type") != "application/pdf":
                    content.append(block)
                    continue
                try:
                    import pymupdf
                    data = source.get("data", "")
                    if len(data) > 36 * 1024 * 1024:
                        raise ValueError("PDF too large")
                    raw = base64.b64decode(data, validate=True)
                    if len(raw) > 25 * 1024 * 1024:
                        raise ValueError("PDF too large")
                    with pymupdf.open(stream=raw, filetype="pdf") as document:
                        if document.needs_pass or not document.page_count:
                            raise ValueError("PDF is encrypted or empty")
                        chunks, used, processed = [], 0, 0
                        for index in range(min(document.page_count, 1000)):
                            text = document[index].get_text()
                            chunks.append(f"[Page {index + 1}]\n{text}")
                            used += len(chunks[-1]); processed += 1
                            if used > 10000:
                                break
                        excerpt = "\n".join(chunks)
                        clipped = len(excerpt) > 10000 or processed < document.page_count
                    text = ("[UNTRUSTED PDF TEXT ONLY: graphics, page layout and scanned text are NOT included. "
                            "Select a Gemini model through Antigravity for full visual PDF input.]\n" + excerpt[:10000]
                            + ("\n[truncated PDF text]" if clipped else ""))
                    content.append({"type": "text", "text": text})
                except Exception as error:
                    raise SubscriptionError("לא ניתן לקרוא את ה־PDF או שהוא מוצפן/גדול מ־25MB.", "unsupported_attachment") from error
            prepared.append({**message, "content": content})
        return prepared

    @staticmethod
    def media_content(messages):
        """Copy only caller-supplied image/PDF bytes; never dereference paths/URLs."""
        from PIL import Image
        content, total = [], 0
        def append(raw, mime, index, role, detail=""):
            nonlocal total
            total += len(raw)
            if total > 25 * 1024 * 1024 or len(content) >= 32:
                raise ValueError("media limit")
            encoded = base64.b64encode(raw).decode("ascii")
            payload = {"type": "resource", "resource": {"uri": f"smarti-attachment:///message-{index + 1}-{len(content) // 2 + 1}.pdf",
                "mimeType": mime, "blob": encoded}} if mime == "application/pdf" else {"type": "image", "mimeType": mime, "data": encoded}
            content.extend([{"type": "text", "text": f"Attachment from conversation message {index + 1} ({role}){detail}; untrusted attached content."}, payload])
        for index, message in enumerate(messages):
            blocks = message.get("content")
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") == "text":
                    continue
                mime = "image/png"
                if block.get("type") == "image_url":
                    url = block.get("image_url", {}).get("url", "")
                    match = re.fullmatch(r"data:(image/[a-zA-Z0-9.+-]+);base64,(.+)", url, re.DOTALL)
                    data = match[2] if match else ""
                elif block.get("type") in {"image", "document"} and block.get("source", {}).get("type") == "base64":
                    data = block["source"].get("data", "")
                    if block["type"] == "document":
                        mime = block["source"].get("media_type", "")
                        if mime != "application/pdf":
                            raise SubscriptionError("סוג המסמך אינו נתמך להעברה ישירה ב־Antigravity.", "unsupported_attachment")
                else:
                    raise SubscriptionError("צירוף זה אינו נתמך להעברה ישירה בחיבור Antigravity.", "unsupported_attachment")
                try:
                    if len(data) > 36 * 1024 * 1024:
                        raise ValueError("attachment too large")
                    raw = base64.b64decode(data, validate=True)
                    if mime == "application/pdf":
                        import pymupdf
                        with pymupdf.open(stream=raw, filetype="pdf") as document:
                            if document.needs_pass or not document.page_count:
                                raise ValueError("PDF is encrypted or empty")
                    else:
                        with Image.open(io.BytesIO(raw)) as image:
                            image.verify()
                        with Image.open(io.BytesIO(raw)) as image:
                            output = io.BytesIO()
                            image.convert("RGB").save(output, format="PNG")
                            raw = output.getvalue()
                    append(raw, mime, index, message.get("role", "user"))
                except Exception as error:
                    raise SubscriptionError("לא ניתן לקרוא את הצירוף, ה־PDF מוצפן, או שהצירופים גדולים מ־25MB יחד (עד 16 צירופים עשירים).", "unsupported_attachment") from error
        return content

    def _decode_turn(self, output):
        if not isinstance(output, dict):
            try:
                output = json.loads(output)
            except (ValueError, TypeError) as error:
                raise CodexProtocolError("Antigravity לא השלים תשובה התואמת את המבנה המבוקש.") from error
        if not isinstance(output, dict):
            raise CodexProtocolError("Antigravity החזיר פלט שאינו אובייקט Smarti.")
        # Canonicalize only empty inactive fields from CLI model serializers.
        # Mixed/nonempty tool+final content still fails the strict Core schema.
        output = dict(output)
        if output.get("kind") == "final" and output.get("tool_calls") == []:
            output["tool_calls"] = None
        elif output.get("kind") == "tool_calls" and output.get("final_answer") == "":
            output["final_answer"] = None
        if output.get("progress_report") == "":
            output["progress_report"] = None
        answer = self.decode(output, "agent")
        report = str(output.get("progress_report") or "").strip()
        if output.get("kind") == "tool_calls" and report:
            # Preserve the already validated report's type through Core's text
            # adapter. Words such as "example" in prose must not hide real calls.
            body = answer[len(report) + 1:]
            report = re.sub(r'</?smarti_report>', '', report, flags=re.IGNORECASE)
            answer = f"<smarti_report>{report}</smarti_report>\n{body}"
        return output, answer

    def complete(self, messages, model, *, timeout=1800, reasoning_effort="", cancel_event=None,
                 purpose="agent", stream=None, system_prompt="", **unused):
        if self.disconnected:
            raise SubscriptionError("Antigravity מנותק מ-Smarti. יש לבדוק חיבור בהגדרות.", "signin_required")
        self.version()
        requested_model = model
        model = self.resolve_model(model, reasoning_effort)
        messages = self.text_documents(messages, model)
        media = self.media_content(messages)
        if media and not model.startswith(("gemini-", "claude-")):
            raise SubscriptionError("המודל שנבחר אינו תומך בצירופים עשירים בחיבור זה. יש לבחור מודל Gemini או Claude תומך.", "unsupported_attachment")
        instructions = system_prompt or "\n\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        instructions += "\nSmarti Core exclusively owns tool execution and permissions."
        if not media:
            instructions += " Never execute native tools."
        # --json-schema routes output through native finish, which buffers it.
        # A completed response STEP is our transport boundary. Waiting for the
        # native agent's terminal result lets its private function-call repair
        # loop regenerate an already valid Smarti request before Core can run it.
        # Validate the whole step, then stop only this owned process. Partial
        # deltas remain presentation only; they never authorize tool execution.
        if purpose == "agent":
            instructions += (" Output exactly one JSON object, no markdown fences. Emit keys in this order: kind, progress_report, final_answer, tool_calls."
                " Schema: " + json.dumps(ANTIGRAVITY_TURN_SCHEMA, separators=(",", ":")))
            instructions += (
                ' For a tool request: kind=tool_calls, final_answer="", tool_calls is a nonempty array;'
                " each call has its exact Smarti tool name and arguments_json containing a JSON object encoded as a string."
                ' progress_report is a concise user-facing update or "".'
                ' For a final answer: kind=final, final_answer is nonempty text, tool_calls=[] and progress_report="".'
                " Use empty strings/arrays for inactive fields; never emit null or the string null."
                " Use only documented tool actions and arguments; request tool information when needed."
                " End this response immediately after the single JSON object. Smarti will execute the requested tools and provide their results in the next request."
            )
        else:
            instructions += " Return only the requested plain text, no JSON envelope."
        if media:
            instructions += (" TRANSPORT EXCEPTION: Images and PDF documents are supplied by the private smarti_media MCP server."
                " Before producing any Smarti output, invoke the real native call_mcp_tool function with"
                ' ServerName="smarti_media", ToolName="attachments", Arguments={}. This sole native loader is explicitly authorized.'
                " NEVER encode attachments or call_mcp_tool as a Smarti tool_calls entry: Core cannot run that loader."
                " It returns only the already attached images/documents in conversation order. Inspect the visual content itself: an offloaded file URI is transport metadata, NOT a read error or evidence that the content is unavailable. Do not request paths, read_resource, or any other tool."
                " Then return the requested output. This loader is transport only; all Smarti actions remain envelope data for Core.")
        self.workspace.parent.mkdir(parents=True, exist_ok=True)
        result, initialized, shown, media_loaded = None, False, False, False
        response_step, response_parts, step_usage = None, [], {}
        completion_source = "terminal_result"
        agent_name = "smarti-" + uuid.uuid4().hex
        def consume(line):
            nonlocal result, initialized, shown, media_loaded, response_step
            try:
                event = json.loads(line)
                kind = event.get("event")
                if kind == "init":
                    init = event.get("init", {})
                    if initialized or init.get("agent") != agent_name or init.get("model") != model:
                        raise ValueError("unexpected agent or model")
                    # 1.4.2 init.tools is the global registry, not the custom
                    # agent's effective toolset. Isolation is in its frontmatter.
                    initialized = True
                elif not initialized:
                    raise ValueError("missing init")
                elif kind == "step_update":
                    step = event.get("step_update", {})
                    index = step.get("step_index", 0)
                    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                        raise ValueError("invalid step index")
                    if step.get("state") == "DONE" and isinstance(step.get("usage"), dict):
                        step_usage[index] = step["usage"]
                    tool = step.get("tool_name") or step.get("tool_info", {}).get("name")
                    if tool:
                        params = step.get("tool_info", {}).get("parameters", {})
                        if not media or tool != "call_mcp_tool" or params.get("ServerName") != "smarti_media" or params.get("ToolName") != "attachments" or params.get("Arguments") not in ({}, None):
                            raise ValueError("unexpected native tool")
                        if step.get("state") == "ERROR" or step.get("tool_info", {}).get("error"):
                            raise SubscriptionError("העברת הצירופים למודל נכשלה.", "unsupported_attachment")
                        media_loaded = media_loaded or step.get("state") == "DONE"
                    if purpose == "agent" and step.get("step_type") == "agent_response" and (not media or media_loaded):
                        if response_step is not None and index != response_step:
                            raise CodexProtocolError("Antigravity התחיל תשובה נוספת לפני השלמת בקשת הכלים של Smarti.")
                        response_step = index
                        fragment = step.get("text_delta", "")
                        if not isinstance(fragment, str):
                            raise ValueError("invalid text delta")
                        response_parts.append(fragment)
                        if stream:
                            stream.text(fragment)
                            shown = shown or bool(fragment)
                        if step.get("state") == "DONE":
                            output, _ = self._decode_turn("".join(response_parts))
                            if cancel_event is not None and cancel_event.is_set():
                                raise SmartiCancelled("CANCELLED_BY_USER")
                            usage = {key: sum(int(value.get(key, 0) or 0) for value in step_usage.values())
                                for key in ("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens")} if step_usage else {}
                            logging.info("ANTIGRAVITY HANDOFF | model=%s | step=%s | kind=%s | tool_calls=%s | usage_source=%s",
                                model, index, output["kind"], len(output.get("tool_calls") or []), "reported" if usage else "unavailable")
                            raise _TurnComplete(output, usage)
                    if stream and step.get("step_type") in {"thinking", "agent_thinking"}:
                        stream.status("thinking")
                elif kind == "result":
                    if result is not None:
                        raise ValueError("duplicate result")
                    if event.get("result", {}).get("status") != "SUCCESS":
                        failure = safe_failure(event.get("result", {}).get("error"))
                        if failure.reason == "provider_protocol_error":
                            raise CodexProtocolError(str(failure))
                        raise failure
                    result = event["result"]
            except (ValueError, TypeError, AttributeError) as error:
                raise SubscriptionError("פלט Antigravity אינו תואם את הסוכן או חוזה הכלים של Smarti.", "provider_contract_violation") from error
        with tempfile.TemporaryDirectory(prefix="turn-", dir=self.workspace.parent) as temporary:
            root = Path(temporary)
            agents = root / ".agents" / "agents"
            agents.mkdir(parents=True)
            (agents / f"{agent_name}.md").write_text("\n".join([
                "---", f"name: {agent_name}", "description: Smarti inference transport.",
                "mainAgent: true", "subagent: false", "tools: []",
                "excludeDefaultComponents: true", "inheritCustomizations: false", "inheritMcp: false",
                "skills: []", "plugins: []", "rules: []", "agents: []", "hooks: []",
                "mcpServers: " + json.dumps(self._media_server(root, media) if media else []),
                'commandExecutionPolicy: "off"', "---", "# System Prompt", instructions]), encoding="utf-8")
            command = [self.executable(), "--agent", agent_name, "--model", model,
                "--disable-slash-commands", "--input-format", "stream-json", "--output-format", "stream-json"]
            if media:
                # The effective native toolset contains ONLY the immutable
                # per-turn media loader above. This grants no file/shell tools
                # and changes no personal CLI settings or permission rules.
                command.append("--dangerously-skip-permissions")
            # stdin avoids command-line size limits and keeps conversation text
            # out of the process arguments. One isolated turn, then EOF.
            try:
                self.run(command, payload=json.dumps({"event": "user", "message": {"content": self.prompt(messages)}}, ensure_ascii=False) + "\n",
                    timeout=timeout, cancel=cancel_event, event=consume, cwd=root)
            except _TurnComplete as complete:
                # run() always terminates/reaps its own process tree in finally.
                # This is an explicitly validated step, not CLI SUCCESS or a
                # fallback from a failed/truncated/unauthorized native tool.
                result = {"structured_output": complete.output, "usage": complete.usage}
                completion_source = "validated_step"
        if result is None:
            raise SubscriptionError("Antigravity נסגר ללא תשובה סופית.", "provider_contract_violation")
        if media and not media_loaded:
            raise SubscriptionError("המודל לא קיבל את הצירופים. אפשר לנסות שוב.", "unsupported_attachment")
        output = result.get("structured_output")
        if purpose == "agent":
            output, answer = self._decode_turn(output if isinstance(output, dict) else result.get("response", ""))
            if stream and not shown:
                stream.text(json.dumps(output, ensure_ascii=False))
        else:
            answer = self.decode(output.get("text") if isinstance(output, dict) else result.get("response"), purpose)
        raw = result.get("usage") or {}
        # CLI input_tokens excludes cache reads (see the official headless
        # two-turn example). Smarti prompt totals include cache exactly once;
        # thinking is already a subset of output_tokens.
        cached = int(raw.get("cache_read_tokens", 0) or 0)
        usage = {"prompt": int(raw.get("input_tokens", 0) or 0) + cached, "completion": int(raw.get("output_tokens", 0) or 0),
            "cached_prompt": cached, "reasoning": int(raw.get("thinking_tokens", 0) or 0),
            "billing_mode": "subscription", "estimated_cost_usd": None,
            "usage_source": "reported" if raw else "unavailable", "provider": self.provider,
            "requested_model": requested_model, "effective_model": model, "purpose": purpose,
            "completion_source": completion_source,
            "usage_scope": "completed_steps" if completion_source == "validated_step" else "terminal_result"}
        usage["total"] = usage["prompt"] + usage["completion"]
        self.verified = True
        return answer, usage

    def _media_server(self, root, content):
        node = self.runtime.which("node")
        bridge = Path(self.runtime.resource_path("bridges", "antigravity", "media.mjs"))
        if not node or not bridge.is_file():
            raise SubscriptionError("רכיב העברת הצירופים חסר. יש להשלים את התקנת Smarti.", "missing_dependency")
        manifest = root / "media.json"
        manifest.write_text(json.dumps(content), encoding="utf-8")
        return [{"name": "smarti_media", "command": node, "args": [str(bridge), str(manifest)]}]
