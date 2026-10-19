"""Small bounded login operations; no credentials, auth URLs, or console output cross UI."""
import subprocess
import threading
import time
import uuid

from . import CLAUDE, get_provider
from .base import SubscriptionError


class Connections:
    def __init__(self, core):
        self.core = core
        self.operations = {}
        self.lock = threading.RLock()
        self.snapshots = {}

    def close(self):
        with self.lock:
            for operation in list(self.operations.values()):
                if operation["state"] == "running":
                    self.cancel(operation["provider"], operation["id"])

    def status(self, name):
        with self.lock:
            running = next((operation for operation in self.operations.values()
                if operation["provider"] == name and operation["state"] == "running"), None)
            if running:
                return get_provider(self.core, name).state("login_in_progress", running["message"], operation_id=running["id"])
            provider = get_provider(self.core, name)
            snapshot = self.snapshots.get((name, provider.strategy))
            return dict(snapshot) if snapshot else provider.state("unchecked", "טרם נבדק")

    def operation(self, name, identifier):
        with self.lock:
            operation = self.operations.get(identifier)
            if not operation or operation["provider"] != name:
                raise KeyError(identifier)
            return {key: value for key, value in operation.items() if key not in {"process", "created"}}

    def cancel(self, name, identifier):
        with self.lock:
            operation = self.operations.get(identifier)
            if not operation or operation["provider"] != name:
                raise KeyError(identifier)
            if operation["state"] == "running":
                operation["state"] = "cancelled"
                process = operation.get("process")
                if process:
                    get_provider(self.core, name).terminate(process)
                operation["message"] = "ההתחברות בוטלה."
                provider = get_provider(self.core, name)
                snapshot = self.snapshots.get((name, provider.strategy))
                if snapshot:
                    operation["connection"] = dict(snapshot)
            return self.operation(name, identifier)

    def action(self, name, action, *, automatic=False):
        provider = get_provider(self.core, name)
        if automatic and self.core.settings.get("subscription_provider_connections", {}).get(name) is False:
            return self.status(name)
        if action == "disconnect":
            with self.lock:
                for operation in list(self.operations.values()):
                    if operation["provider"] == name and operation["state"] == "running":
                        self.cancel(name, operation["id"])
            result = provider.disconnect()
            with self.lock:
                self.snapshots[(name, provider.strategy)] = result
            self.core.settings.setdefault("subscription_provider_connections", {})[name] = False
            self.core._save_settings()
            return result
        if action == "check":
            with self.lock:
                for item in self.operations.values():
                    if item["provider"] == name and item["state"] == "running":
                        return self.operation(name, item["id"])
                self.operations = {key: value for key, value in self.operations.items()
                    if value["state"] == "running" or time.monotonic() - value["created"] < 1800}
                if len(self.operations) >= 24:
                    raise SubscriptionError("יש להשלים את הפעולות הקודמות.", "busy")
                identifier = uuid.uuid4().hex
                operation = {"id": identifier, "provider": name, "state": "running",
                    "message": "בודק את מצב רכיב החיבור…", "created": time.monotonic()}
                self.operations[identifier] = operation
                def check():
                    try:
                        provider.disconnected = False
                        result = provider.connection_status()
                        if result["state"] in {"connected", "configured"} and not provider.models:
                            try:
                                provider.catalog()
                            except SubscriptionError:
                                pass  # Connection and catalog availability are separate.
                        with self.lock:
                            if operation["state"] != "running":
                                return
                            operation.update(state="completed", message=result["message"], connection=result)
                            self.snapshots[(name, provider.strategy)] = result
                            if result["state"] in {"connected", "configured"}:
                                self.core.settings.setdefault("subscription_provider_connections", {})[name] = True
                                self.core._save_settings()
                    except Exception:
                        with self.lock:
                            if operation["state"] == "running":
                                operation.update(state="failed", message="בדיקת החיבור לא הושלמה.")
                threading.Thread(target=check, daemon=True).start()
                return self.operation(name, identifier)
        if action != "login":
            raise ValueError("unknown_connection_action")
        if name == CLAUDE and provider.strategy != "claude_login":
            return provider.state("wrong_auth_mode", "במסלול האסימון יש להגדיר את סביבת ההפעלה ולבדוק חיבור, או לבחור כניסה רגילה.")
        executable = provider.executable()
        with self.lock:
            for operation in self.operations.values():
                if operation["provider"] == name and operation["state"] == "running":
                    return self.operation(name, operation["id"])
            # Completed operations expire; active operations have their own deadline.
            self.operations = {key: value for key, value in self.operations.items()
                               if value["state"] == "running" or time.monotonic() - value["created"] < 1800}
            if len(self.operations) >= 24:
                raise SubscriptionError("יש להשלים או לבטל את פעולת ההתחברות הקודמת.", "busy")
            identifier = uuid.uuid4().hex
            operation = {"id": identifier, "provider": name, "state": "running",
                "message": "יש להשלים כניסה בחלון הרשמי של Claude Code." if name == CLAUDE else
                    "יש להשלים כניסה בחלון Antigravity הרשמי, ואז לצאת ממנו בעזרת Ctrl+D.", "created": time.monotonic()}
            self.operations[identifier] = operation
            provider.workspace.mkdir(parents=True, exist_ok=True)
            command = [executable, "auth", "login"] if name == CLAUDE else [executable]
            operation["process"] = subprocess.Popen(command, cwd=provider.workspace,
                env=provider.environment(), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            def finish():
                process = operation["process"]
                try:
                    code = process.wait(timeout=600)
                    with self.lock:
                        if operation["state"] != "running":
                            return
                        provider.disconnected = False
                        result = provider.connection_status() if code == 0 or name != CLAUDE else provider.state("disconnected", "ההתחברות לא הושלמה. אפשר לנסות שוב.")
                        provider.models = []
                        operation.update(state="completed", message=result["message"], connection=result)
                        self.snapshots[(name, provider.strategy)] = result
                        if result["state"] == "connected":
                            self.core.settings.setdefault("subscription_provider_connections", {})[name] = True
                            self.core._save_settings()
                except subprocess.TimeoutExpired:
                    provider.terminate(process)
                    with self.lock:
                        if operation["state"] == "running":
                            operation.update(state="failed", message="זמן ההתחברות הסתיים. אפשר לנסות שוב.")
                except Exception:
                    with self.lock:
                        if operation["state"] == "running":
                            operation.update(state="failed", message="לא ניתן היה לאמת את ההתחברות.")
            threading.Thread(target=finish, daemon=True).start()
            return self.operation(name, identifier)
