"""Claude Code through the pinned official Agent SDK, with native tools denied."""
import json
import os
from pathlib import Path
import shutil
import tempfile

from .base import SubscriptionError, SubscriptionProvider, register_models, safe_failure
from ..codex_signin import SMARTI_TURN_OUTPUT_SCHEMA


class ClaudeProvider(SubscriptionProvider):
    provider = "anthropic_claude_code_signin"
    label = "Claude Code"
    install_url = "https://code.claude.com/docs/en/quickstart"

    def bridge(self):
        return Path(self.runtime.resource_path("bridges", "claude-code", "bridge.mjs"))

    def executable(self):
        override = os.environ.get("SMARTI_CLAUDE_CLI")
        if override:
            if Path(override).is_file():
                return override
            raise SubscriptionError("נתיב Claude Code שהוגדר אינו קיים. יש לתקן את נתיב רכיב החיבור.", "missing_dependency")
        candidates = [str(self.bridge().parent / "node_modules" / "@anthropic-ai" /
            "claude-agent-sdk-win32-x64" / "claude.exe"),
            str(Path.home() / ".local" / "bin" / "claude.exe"), shutil.which("claude")]
        for path in candidates:
            if path and Path(path).is_file():
                return path
        raise SubscriptionError("רכיב Claude Code חסר. יש להתקין את רכיב החיבור הרשמי.", "missing_dependency")

    def command(self):
        node = self.runtime.private_node_executable() or shutil.which("node")
        if not node or not self.bridge().is_file() or not (self.bridge().parent / "node_modules" / "@anthropic-ai" / "claude-agent-sdk").is_dir():
            raise SubscriptionError("ערכת החיבור הרשמית של Claude חסרה. יש להתקין את תלויות החיבור של סמארטי.", "missing_dependency")
        return [node, str(self.bridge())]

    def connection_status(self):
        if self.disconnected:
            return self.state("disconnected", "Claude Code מנותק מסמארטי.")
        try:
            self.command()
            if self.strategy == "setup_token_env" and not self.environment().get("CLAUDE_CODE_OAUTH_TOKEN"):
                return self.state("disconnected", "לא הוגדר אסימון בסביבת ההפעלה. אפשר להתחבר בכניסה הרגילה.")
            raw = json.loads(self.run([self.executable(), "auth", "status"], timeout=15, ok_codes=(0, 1)))
            if not isinstance(raw, dict):
                raise ValueError("invalid auth status")
            mode = raw.get("authMethod")
            if not raw.get("loggedIn") or mode == "none":
                return self.state("disconnected", "יש להתחבר לחשבון Claude עם מנוי מתאים.")
            expected = "oauth_token" if self.strategy == "setup_token_env" else "claude.ai"
            if mode != expected or raw.get("apiProvider") != "firstParty":
                return self.state("wrong_auth_mode", "הכלי הרשמי משתמש במסלול אימות אחר. יש לבחור חיבור Claude דרך המנוי.")
            plan = str(raw.get("subscriptionType") or "").lower()
            if plan in {"free", "none"}:
                return self.state("account_ineligible", "חשבון Claude חינמי אינו כולל שימוש ב־Claude Code דרך מנוי.")
            if self.strategy == "setup_token_env" and not self.verified:
                return self.state("configured", "אסימון זוהה בסביבת ההפעלה. תוקפו וזכאות המודל יאומתו בבקשת המודל הראשונה.", auth_mode=mode, verified=False)
            return self.state("connected", "Claude Code מחובר במסלול המנוי; זמינות המודל והמכסה נקבעת אצל הספק.", auth_mode=mode)
        except SubscriptionError as error:
            # auth status exits 1 for logged-out users; that is a state, not an API key failure.
            return self.state("disconnected" if error.reason == "signin_required" else error.reason, str(error))
        except (ValueError, TypeError):
            return self.state("incompatible_version", "פלט האימות של Claude Code אינו תואם. יש לעדכן את הרכיב.")

    def catalog(self):
        events = []
        self.run(self.command(), payload=json.dumps({"method": "metadata", "cwd": str(self.workspace),
            "executable": self.executable()}) + "\n", timeout=30,
            event=lambda line: events.append(json.loads(line)))
        metadata = next((event for event in events if event.get("type") == "metadata"), None)
        if not metadata:
            raise SubscriptionError("רשימת המודלים אינה זמינה כרגע.")
        plan = str((metadata.get("account") or {}).get("subscriptionType") or "").lower()
        if plan == "free":
            raise SubscriptionError("חשבון Claude חינמי אינו כולל שימוש ב־Claude Code דרך מנוי.", "account_ineligible")
        rows = []
        for model in metadata.get("models", []):
            if not isinstance(model, dict) or not model.get("value"):
                continue
            efforts = [level for level in model.get("supportedEffortLevels", [])
                       if level in {"low", "medium", "high", "xhigh", "max"}] if model.get("supportsEffort") else []
            rows.append({"id": model["value"], "label": model.get("displayName", model["value"]),
                "resolved_model": model.get("resolvedModel", ""), "efforts": efforts,
                "availability": "unknown"})
        self.models = rows
        register_models(self.provider, rows)
        return rows

    def complete(self, messages, model, *, timeout=1800, reasoning_effort="", cancel_event=None,
                 purpose="agent", stream=None, system_prompt="", **unused):
        state = self.connection_status()
        if state["state"] not in {"connected", "configured"}:
            raise SubscriptionError(state["message"], state["state"])
        rows = self.models or self.catalog()
        selected = next((row for row in rows if row["id"] == model or row.get("resolved_model") == model), None)
        if not selected:
            raise SubscriptionError("יש לבחור מודל מתוך הרשימה הרשמית של Claude Code.", "model_unavailable")
        if reasoning_effort and reasoning_effort not in selected["efforts"]:
            raise SubscriptionError("רמת החשיבה שנבחרה אינה נתמכת במודל.", "unsupported_reasoning_effort")
        instructions = system_prompt or "\n\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
        instructions += "\nSmarti Core owns all tools and permissions. Never call native Claude tools."
        instructions += " Return the supplied Smarti JSON envelope." if purpose == "agent" else " Return only the requested text."
        content = []
        for message in messages:
            if message.get("role") == "system":
                continue
            text = self.prompt([message])
            if text:
                content.append({"type": "text", "text": text})
            if not isinstance(message.get("content"), list):
                continue
            for block in message["content"]:
                if block.get("type") in {"image", "document"} and block.get("source", {}).get("type") == "base64":
                    content.append(block)
                    continue
                if block.get("type") == "image_url":
                    url = block.get("image_url", {}).get("url", "")
                    if not url.startswith("data:image/") or ";base64," not in url:
                        raise SubscriptionError("החיבור תומך בתמונות מצורפות מקומיות בלבד.", "unsupported_attachment")
                    mime, encoded = url[5:].split(";base64,", 1)
                    content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": encoded}})
        result, effective, initialized = None, model, False
        def consume(line):
            nonlocal result, effective, initialized
            try:
                event = json.loads(line)
            except ValueError as error:
                raise SubscriptionError("פלט רכיב Claude אינו תקין.", "provider_contract_violation") from error
            kind = event.get("type")
            if kind == "failure":
                raise safe_failure(event.get("reason"))
            if kind == "init":
                if initialized:
                    raise SubscriptionError("רכיב Claude החזיר אתחול כפול.", "provider_contract_violation")
                initialized = True
                effective = event.get("model") or model
            elif kind in {"text", "thinking", "result"} and not initialized:
                raise SubscriptionError("לא התקבל אישור אתחול מבודד של רכיב Claude.", "provider_contract_violation")
            elif kind == "text" and stream:
                stream.text(event.get("text", ""))
            elif kind == "thinking" and stream:
                stream.status("thinking")
            elif kind == "result":
                if result is not None:
                    raise SubscriptionError("רכיב Claude החזיר סיום כפול.", "provider_contract_violation")
                if not event.get("ok"):
                    raise safe_failure(" ".join(event.get("errors") or []) + " " + str(event.get("subtype", "")))
                result = event
        self.workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="turn-", dir=self.workspace.parent) as temporary:
            prompt_path = Path(temporary) / "system.txt"
            prompt_path.write_text(instructions, encoding="utf-8")
            request = {"method": "complete", "cwd": str(self.workspace), "prompt_path": str(prompt_path),
                "executable": self.executable(), "model": model, "effort": reasoning_effort,
                "content": content, **({"schema": SMARTI_TURN_OUTPUT_SCHEMA} if purpose == "agent" else {})}
            self.run(self.command(), payload=json.dumps(request, ensure_ascii=False) + "\n", timeout=timeout,
                cancel=cancel_event, event=consume)
        if result is None:
            raise SubscriptionError("Claude Code נסגר ללא תשובה סופית.", "provider_contract_violation")
        if effective not in {model, selected.get("resolved_model")}:
            raise SubscriptionError("הספק הפעיל מודל שונה מהבחירה. התשובה לא התקבלה כהשלמה תקינה.", "model_unavailable")
        answer = self.decode(result.get("output") if purpose == "agent" else result.get("text"), purpose)
        usage = self.usage(result.get("usage"))
        usage.update(provider=self.provider, requested_model=model, effective_model=effective, purpose=purpose)
        self.verified = True
        return answer, usage
