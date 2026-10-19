"""Official Antigravity CLI with a private, minimal custom agent per request."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from .base import SubscriptionError, SubscriptionProvider, register_models, safe_failure
from ..codex_signin import CodexProtocolError, SMARTI_TURN_OUTPUT_SCHEMA

# The CLI translates this schema for different model families. Non-nullable
# inactive fields avoid stringified "null" in Claude/GPT finish calls. Core's
# existing nullable contract is restored before its strict local validation.
ANTIGRAVITY_TURN_SCHEMA = json.loads(json.dumps(SMARTI_TURN_OUTPUT_SCHEMA))
for _field in ("progress_report", "final_answer"):
    ANTIGRAVITY_TURN_SCHEMA["properties"][_field]["type"] = "string"
ANTIGRAVITY_TURN_SCHEMA["properties"]["tool_calls"]["type"] = "array"


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
            return self.state("disconnected", "Antigravity מנותק מסמארטי.")
        try:
            version = self.version()
            quota = self.quota()
            return self.state("connected", "Antigravity מחובר דרך הכלי הרשמי. סמארטי מנהל את הכלים וההרשאות.",
                version=version, inference_available=True, quota_available=quota["available"], quota=quota,
                text_only=True)
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
        output = self.run([self.executable(), "models"], timeout=30)
        rows = []
        for line in output.splitlines():
            match = re.match(r"^([a-z0-9][a-z0-9._/-]+)\s+(.+)$", line.strip())
            if match:
                rows.append({"id": match[1], "label": match[2].strip(), "efforts": [], "availability": "unknown"})
        self.models = rows
        register_models(self.provider, rows)
        return rows

    def complete(self, messages, model, *, timeout=1800, reasoning_effort="", cancel_event=None,
                 purpose="agent", stream=None, system_prompt="", **unused):
        if self.disconnected:
            raise SubscriptionError("Antigravity מנותק מסמארטי. יש לבדוק חיבור בהגדרות.", "signin_required")
        self.version()
        selected = next((row for row in (self.models or self.catalog()) if row["id"] == model), None)
        if not selected:
            raise SubscriptionError("יש לבחור מודל מתוך הרשימה הרשמית של Antigravity.", "model_unavailable")
        if reasoning_effort:
            raise SubscriptionError("בחיבור Antigravity רמת החשיבה נבחרת כחלק משם המודל.", "unsupported_reasoning_effort")
        for message in messages:
            content = message.get("content")
            if isinstance(content, list) and any(block.get("type") != "text" for block in content if isinstance(block, dict)):
                raise SubscriptionError("חיבור Antigravity CLI תומך כרגע בטקסט ובקבצי טקסט בלבד.", "unsupported_attachment")
        instructions = system_prompt or "\n\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        instructions += "\nSmarti Core exclusively owns tool execution and permissions. Never execute native tools."
        schema = ANTIGRAVITY_TURN_SCHEMA if purpose == "agent" else {
            "type": "object", "properties": {"text": {"type": "string"}},
            "required": ["text"], "additionalProperties": False}
        instructions += " Use finish only to serialize the supplied JSON schema. Tool calls inside the Smarti envelope are data for Core."
        if purpose == "agent":
            instructions += (
                ' For a tool request: kind=tool_calls, final_answer="", tool_calls is a nonempty array;'
                " each call has its exact Smarti tool name and arguments_json containing a JSON object encoded as a string."
                ' progress_report is a concise user-facing update or "".'
                ' For a final answer: kind=final, final_answer is nonempty text, tool_calls=[] and progress_report="".'
                " Use empty strings/arrays for inactive fields; never emit null or the string null."
                " Use only documented tool actions and arguments; request tool information when needed."
            )
        self.workspace.parent.mkdir(parents=True, exist_ok=True)
        result, initialized, shown = None, False, False
        agent_name = "smarti-" + uuid.uuid4().hex
        def consume(line):
            nonlocal result, initialized, shown
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
                    tool = step.get("tool_name") or step.get("tool_info", {}).get("name")
                    if tool and tool != "finish":
                        raise ValueError("unexpected native tool")
                    if stream and purpose == "agent" and step.get("step_type") == "agent_response":
                        stream.text(step.get("text_delta", ""))
                        shown = shown or bool(step.get("text_delta"))
                    if stream and step.get("step_type") in {"thinking", "agent_thinking"}:
                        stream.status("thinking")
                elif kind == "result":
                    if result is not None:
                        raise ValueError("duplicate result")
                    if event.get("result", {}).get("status") != "SUCCESS":
                        raise safe_failure(event.get("result", {}).get("error"))
                    result = event["result"]
            except (ValueError, TypeError, AttributeError) as error:
                raise SubscriptionError("פלט Antigravity אינו תואם את הסוכן או חוזה הכלים של סמארטי.", "provider_contract_violation") from error
        with tempfile.TemporaryDirectory(prefix="turn-", dir=self.workspace.parent) as temporary:
            root = Path(temporary)
            agents = root / ".agents" / "agents"
            agents.mkdir(parents=True)
            (agents / f"{agent_name}.md").write_text("\n".join([
                "---", f"name: {agent_name}", "description: Smarti inference transport.",
                "mainAgent: true", "subagent: false", "tools: [finish]",
                "excludeDefaultComponents: true", "inheritCustomizations: false", "inheritMcp: false",
                "skills: []", "plugins: []", "rules: []", "agents: []", "hooks: []", "mcpServers: []",
                'commandExecutionPolicy: "off"', "---", "# System Prompt", instructions]), encoding="utf-8")
            schema_path = root / "schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [self.executable(), "--agent", agent_name, "--model", model,
                "--disable-slash-commands", "--input-format", "stream-json", "--output-format", "stream-json",
                "--json-schema", str(schema_path)]
            # stdin avoids command-line size limits and keeps conversation text
            # out of the process arguments. One isolated turn, then EOF.
            self.run(command, payload=json.dumps({"event": "user", "message": {"content": self.prompt(messages)}}, ensure_ascii=False) + "\n",
                timeout=timeout, cancel=cancel_event, event=consume, cwd=root)
        if result is None:
            raise SubscriptionError("Antigravity נסגר ללא תשובה סופית.", "provider_contract_violation")
        output = result.get("structured_output")
        if not isinstance(output, dict):
            raise CodexProtocolError("Antigravity לא השלים תשובה התואמת את המבנה המבוקש.")
        if purpose == "agent":
            # Some CLI model serializers emit []/"" for the inactive nullable
            # member. Canonicalize only empty inactive fields; mixed/nonempty
            # tool+final content still fails the strict Core protocol.
            output = dict(output)
            if output.get("kind") == "final" and output.get("tool_calls") == []:
                output["tool_calls"] = None
            elif output.get("kind") == "tool_calls" and output.get("final_answer") == "":
                output["final_answer"] = None
            if output.get("progress_report") == "":
                output["progress_report"] = None
            answer = self.decode(output, purpose)
            if stream and not shown:
                stream.text(json.dumps(output, ensure_ascii=False))
        else:
            answer = self.decode(output.get("text"), purpose)
        raw = result.get("usage") or {}
        # CLI input_tokens excludes cache reads (see the official headless
        # two-turn example). Smarti prompt totals include cache exactly once;
        # thinking is already a subset of output_tokens.
        cached = int(raw.get("cache_read_tokens", 0) or 0)
        usage = {"prompt": int(raw.get("input_tokens", 0) or 0) + cached, "completion": int(raw.get("output_tokens", 0) or 0),
            "cached_prompt": cached, "reasoning": int(raw.get("thinking_tokens", 0) or 0),
            "billing_mode": "subscription", "estimated_cost_usd": None,
            "usage_source": "reported" if raw else "unavailable", "provider": self.provider,
            "requested_model": model, "effective_model": model, "purpose": purpose}
        usage["total"] = usage["prompt"] + usage["completion"]
        self.verified = True
        return answer, usage
