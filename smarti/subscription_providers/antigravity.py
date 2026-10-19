"""Read-only discovery for Antigravity; inference fails closed on known tool leakage."""
import os
from pathlib import Path
import re
import shutil

from .base import SubscriptionError, SubscriptionProvider, register_models


class AntigravityProvider(SubscriptionProvider):
    provider = "google_antigravity_signin"
    label = "Google Antigravity"
    install_url = "https://antigravity.google/docs/cli-getting-started"
    # SP-0 on official 1.4.2: tools: [] AND tools: [finish] still advertise
    # filesystem/shell/browser/MCP tools. Do not expose an unsafe inference path.
    isolation_message = (
        "Antigravity מותקן, אך בגרסה שנבדקה הכלים המובנים נשארים זמינים גם בסוכן מותאם. "
        "השימוש בשיחה חסום עד שתהיה דרך רשמית ומאומתת להעביר את כל הפעולות דרך סמארטי. "
        "הכניסה והמנוי שלך אינם נמחקים."
    )

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
            version = self.run([self.executable(), "--version"], timeout=10).strip()
            return self.state("policy_conflict", self.isolation_message, version=version, inference_available=False)
        except SubscriptionError as error:
            return self.state(error.reason, str(error), inference_available=False)

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

    def complete(self, *args, **kwargs):
        raise SubscriptionError(self.isolation_message, "policy_conflict")
