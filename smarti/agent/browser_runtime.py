"""Persistent browser process helpers used by Smarti browser automation."""
from .shared import *


class BrowserRuntimeMixin:
    def _automation_browser_profile_dir(self):
        return os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), SMARTI_BROWSER_PROFILE_NAME)

    def _automation_browser_endpoint(self, path="/json/version"):
        return f"http://127.0.0.1:{SMARTI_BROWSER_DEBUG_PORT}{path}"

    def _automation_browser_is_ready(self):
        try:
            res = self._request_get(self._automation_browser_endpoint(), timeout=0.7)
            return res.ok
        except Exception:
            return False

    def _automation_browser_ssl_mode_matches(self):
        try:
            profile_dir = self._automation_browser_profile_dir().replace("'", "''")
            ps = (
                f"$profile = '{profile_dir}'; "
                f"$port = '{SMARTI_BROWSER_DEBUG_PORT}'; "
                "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                "Where-Object { ($_.CommandLine -like \"*--remote-debugging-port=$port*\") -or ($_.CommandLine -like \"*--user-data-dir=$profile*\") } | "
                "Select-Object -First 1 -ExpandProperty CommandLine"
            )
            completed = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=5, env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            command_line = (completed.stdout or "").lower()
            if not command_line:
                return True
            bypass_present = "--ignore-certificate-errors" in command_line
            return bypass_present == self._allow_insecure_ssl()
        except Exception:
            return True

    def _chrome_executable(self):
        candidates = [
            shutil.which("chrome"),
            shutil.which("chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return None

    def _automation_browser_args(self, initial_url="about:blank"):
        profile_dir = self._automation_browser_profile_dir()
        args = [
            self._chrome_executable(),
            f"--remote-debugging-port={SMARTI_BROWSER_DEBUG_PORT}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-popup-blocking",
        ]
        if self._allow_insecure_ssl():
            args.extend([
                "--ignore-certificate-errors",
                "--allow-running-insecure-content",
                "--test-type",
            ])
        args.append(initial_url or "about:blank")
        return args

    def _ensure_automation_browser(self, initial_url="about:blank"):
        if self._automation_browser_is_ready():
            if self._automation_browser_ssl_mode_matches():
                return True, None
            self._close_automation_browser()
        chrome = self._chrome_executable()
        if not chrome:
            return False, "ERROR: Chrome was not found. Install Google Chrome to use browser automation."
        profile_dir = self._automation_browser_profile_dir()
        try:
            os.makedirs(profile_dir, exist_ok=True)
            args = self._automation_browser_args(initial_url)
            self.browser_process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            deadline = time.time() + 12
            while time.time() < deadline:
                if self._automation_browser_is_ready():
                    return True, None
                time.sleep(0.25)
            return False, f"ERROR: Smarti browser did not become ready on port {SMARTI_BROWSER_DEBUG_PORT}. If a Chrome profile warning is open, close it and retry."
        except Exception as e:
            return False, f"ERROR: Failed to start Smarti browser: {e}"

    def _open_in_automation_browser(self, url):
        ok, err = self._ensure_automation_browser("about:blank")
        if not ok:
            return err
        result = self.run_browser_action({"action": "navigate", "url": url, "noSnapshot": True})
        if str(result or "").startswith("ERROR"):
            return result
        return f"SUCCESS: Opened in Smarti browser: {url}"

    def _close_automation_browser(self):
        self.browser_process = None
        profile_dir = self._automation_browser_profile_dir().replace("'", "''")
        ps = (
            f"$profile = '{profile_dir}'; "
            f"$port = '{SMARTI_BROWSER_DEBUG_PORT}'; "
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            "Where-Object { ($_.CommandLine -like \"*--remote-debugging-port=$port*\") -or ($_.CommandLine -like \"*--user-data-dir=$profile*\") } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=10, env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            return "SUCCESS: Smarti browser closed."
        except Exception as e:
            return f"ERROR: Failed to close Smarti browser: {e}"
