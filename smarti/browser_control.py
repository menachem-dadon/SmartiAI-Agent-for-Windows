"""Structured Playwright/CDP control plane for Smarti's persistent browser."""
import ipaddress
import importlib.metadata
import base64
import json
import os
import re
import sys
from pathlib import Path
import subprocess
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from .common import SMARTI_BROWSER_DEBUG_PORT, WIN_CREATE_NO_WINDOW


UNTRUSTED_BROWSER_PREFIX = "[UNTRUSTED_BROWSER_CONTENT]\n"
HELPER_RESULT_PREFIX = "SMARTI_BROWSER_RESULT="


class SmartiBrowserController:
    """Runs high-level browser actions against Smarti Browser through Playwright/CDP."""

    def __init__(self, core):
        self.core = core

    def run(self, payload):
        if not self.core.settings.get("enable_browser_automation", False):
            return "ERROR: Browser automation is disabled by the user in settings."
        args = dict(payload or {})
        action = self._normalize_action(args.get("action") or "snapshot")
        args["action"] = action
        if action == "run" or "code" in args:
            return (
                "ERROR: Raw Python browser code was removed. "
                "Use structured browser actions, action=evaluate for JavaScript, or action=cdp for Chrome DevTools Protocol."
            )

        if action == "profiles":
            return self._json(self._profiles_payload())
        if action == "doctor":
            return self._json(self._doctor_payload())

        profile, profile_error = self._normalize_profile(args.get("profile"))
        if profile_error:
            return profile_error
        args["profile"] = profile

        if self._tauri_bridge_available():
            effective_action, effective_args = self._effective_action(args)
            ok, err = self._preflight_policy(effective_action, effective_args)
            if not ok:
                return err
            prepared, err = self._prepare_paths(args, effective_action, effective_args)
            if err:
                return err
            return self._run_tauri_bridge(prepared)

        if action in {"close_browser", "stop", "close_all"}:
            return self.core._close_automation_browser()

        effective_action, effective_args = self._effective_action(args)
        ok, err = self._preflight_policy(effective_action, effective_args)
        if not ok:
            return err

        if action == "status" and not self.core._automation_browser_is_ready():
            return self._json({
                "ok": True,
                "ready": False,
                "profile": "smarti",
                "message": "Smarti browser is not running. Use action='start' to launch it.",
                "profiles": self._profiles_payload()["profiles"],
            })
        initial_url = "about:blank"
        if effective_action in {"navigate", "open", "start"}:
            initial_url = str(effective_args.get("url") or effective_args.get("targetUrl") or effective_args.get("query_or_url") or "about:blank")
        ok, err = self.core._ensure_automation_browser(initial_url)
        if not ok:
            return err

        prepared, err = self._prepare_paths(args, effective_action, effective_args)
        if err:
            return err
        result = self._run_helper(prepared)
        return result

    def _normalize_action(self, value):
        return str(value or "snapshot").strip().lower().replace("-", "_")

    def _effective_action(self, args):
        action = self._normalize_action(args.get("action") or "snapshot")
        if action == "act" and isinstance(args.get("request"), dict):
            request = dict(args.get("request") or {})
            for key, value in args.items():
                request.setdefault(key, value)
            return self._normalize_action(request.get("kind") or request.get("action") or ""), request
        return action, args

    def _normalize_profile(self, value):
        profile = str(value or "smarti").strip().lower()
        aliases = {
            "": "smarti",
            "default": "smarti",
            "isolated": "smarti",
            "managed": "smarti",
            "smarti": "smarti",
            "smarti_profile": "smarti",
            "chrome": "smarti",
        }
        if profile not in aliases:
            return None, f"ERROR: Unknown browser profile '{profile}'. Use 'smarti'."
        return aliases[profile], None

    def _json(self, payload):
        return self.core._truncate_tool_output(
            UNTRUSTED_BROWSER_PREFIX + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        )

    def _tauri_bridge_available(self):
        port = str(os.environ.get("SMARTI_TAURI_BROWSER_BROKER_PORT") or "").strip()
        token = str(os.environ.get("SMARTI_TAURI_BROWSER_BROKER_TOKEN") or "").strip()
        return port.isdigit() and 0 < int(port) < 65536 and len(token) >= 32

    def _run_tauri_bridge(self, payload):
        """Route the existing policy-approved action to the visible Tauri WebView2 tab."""
        port = int(os.environ["SMARTI_TAURI_BROWSER_BROKER_PORT"])
        token = os.environ["SMARTI_TAURI_BROWSER_BROKER_TOKEN"]
        body = json.dumps(dict(payload or {}), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/action",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        try:
            timeout = max(5, int(self.core._timeout("tool_timeout_seconds", 120)))
            with urllib.request.urlopen(request, timeout=timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error")
            except Exception:
                detail = str(exc)
            return f"ERROR: Tauri browser action failed: {detail}"
        except Exception as exc:
            return f"ERROR: Tauri browser bridge unavailable: {exc}"

        action = self._normalize_action(payload.get("action"))
        if action in {"screenshot", "pdf"} and payload.get("path"):
            encoded = (((parsed.get("result") or {}).get("data")) if isinstance(parsed, dict) else None)
            if encoded:
                try:
                    Path(payload["path"]).write_bytes(base64.b64decode(encoded, validate=True))
                    parsed["path"] = payload["path"]
                    parsed["result"] = {"saved": True, "bytes": os.path.getsize(payload["path"])}
                except Exception as exc:
                    return f"ERROR: Tauri browser capture could not be saved: {exc}"
        post_ok, parsed, post_err = self._postflight_policy(action, parsed)
        if not post_ok:
            return post_err
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            return "ERROR: Tauri browser action failed.\n" + self._json(parsed)
        return self._json(parsed)

    def _playwright_dependency(self):
        try:
            import playwright.sync_api  # noqa: F401
            try:
                version = importlib.metadata.version("playwright")
            except Exception:
                version = "unknown"
            return {"installed": True, "version": version, "error": ""}
        except Exception as exc:
            return {"installed": False, "version": "", "error": str(exc)}

    def _doctor_payload(self):
        profiles = self._profiles_payload()
        playwright = self._playwright_dependency()
        browser_path = ""
        try:
            browser_path = getattr(self.core, "_chrome_executable", lambda: "")() or ""
        except Exception:
            browser_path = ""
        ready = bool(self.core._automation_browser_is_ready())
        embedded = callable(getattr(self.core, "embedded_browser_activate_callback", None))
        checks = [
            {"id": "settings.enabled", "ok": bool(self.core.settings.get("enable_browser_automation", False))},
            {"id": "python.playwright", "ok": bool(playwright.get("installed")), "version": playwright.get("version", ""), "error": playwright.get("error", "")},
            {"id": "browser.runtime", "ok": bool(embedded or browser_path), "embedded": embedded, "fallbackPath": browser_path},
            {"id": "browser.cdp_ready", "ok": ready, "endpoint": self.core._automation_browser_endpoint("").rstrip("/")},
            {"id": "profile.smarti", "ok": True, "path": self.core._automation_browser_profile_dir()},
        ]
        return {
            "ok": all(item.get("ok") for item in checks[:3]),
            "ready": ready,
            "profile": "smarti",
            "dependencies": {
                "python": sys.executable,
                "playwright": playwright,
                "browser": {"embedded": embedded, "fallbackFound": bool(browser_path), "fallbackPath": browser_path},
            },
            "checks": checks,
            "profiles": profiles["profiles"],
            "verifyCommands": [
                "python -m pip install -r requirements.txt",
                "python -m pip check",
                "python -c \"from playwright.sync_api import sync_playwright; print('playwright ok')\"",
            ],
            "message": "Use action='start' to initialize Smarti Browser if dependencies are OK but cdp_ready is false.",
        }

    def _snapshot_defaults(self):
        def bounded(name, default, minimum, maximum):
            try:
                value = int(self.core.settings.get(name, default) or default)
            except Exception:
                value = default
            return max(minimum, min(maximum, value))

        return {
            "elementLimit": bounded("browser_snapshot_element_limit", 120, 20, 350),
            "bodyChars": bounded("browser_snapshot_body_chars", 8000, 1000, 25000),
            "htmlChars": bounded("browser_snapshot_html_chars", 600, 0, 2500),
            "maxChars": bounded("browser_snapshot_max_chars", 12000, 2000, 50000),
        }

    def _output_dir(self):
        try:
            base = self.core._sandbox_root() if self.core._sandbox_enabled() else self.core._default_output_dir()
        except Exception:
            base = os.getcwd()
        os.makedirs(base, exist_ok=True)
        return base

    def _artifact_dir(self, name):
        setting_name = "browser_download_dir" if name == "downloads" else "browser_capture_dir"
        configured = str(self.core.settings.get(setting_name) or "").strip()
        base = configured or os.path.join(self._output_dir(), "Browser_Downloads" if name == "downloads" else "Browser_Captures")
        path = os.path.abspath(os.path.expanduser(os.path.expandvars(base)))
        os.makedirs(path, exist_ok=True)
        return path

    def _profiles_payload(self):
        return {
            "ok": True,
            "defaultProfile": "smarti",
            "profiles": [
                {
                    "id": "smarti",
                    "label": "Smarti Browser",
                    "kind": "local-managed",
                    "default": True,
                    "ready": bool(self.core._automation_browser_is_ready()),
                    "cdpEndpoint": self.core._automation_browser_endpoint("").rstrip("/"),
                    "profileDir": self.core._automation_browser_profile_dir(),
                    "canLaunch": bool(
                        callable(getattr(self.core, "embedded_browser_activate_callback", None))
                        or getattr(self.core, "_chrome_executable", lambda: None)()
                    ),
                    "canStop": True,
                },
            ],
        }

    def _host_in_allowlist(self, host):
        configured = self.core.settings.get("browser_allowed_hosts") or []
        if isinstance(configured, str):
            configured = [item.strip() for item in configured.replace(";", ",").split(",")]
        host = (host or "").strip().lower().rstrip(".")
        for item in configured:
            rule = str(item or "").strip().lower().rstrip(".")
            if not rule:
                continue
            if rule.startswith("*.") and (host == rule[2:] or host.endswith("." + rule[2:])):
                return True
            if host == rule:
                return True
        return False

    def _url_allowed(self, url):
        value = str(url or "").strip()
        if not value:
            return True, None
        parsed = urlparse(value)
        scheme = (parsed.scheme or "").lower()
        if scheme == "about":
            if value.lower() == "about:blank":
                return True, None
            return False, f"Browser navigation to internal URL '{value}' is blocked."
        if scheme not in {"http", "https"}:
            return False, f"Browser navigation scheme '{scheme or '<none>'}' is blocked."
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return False, f"Browser navigation URL has no host: {value}"
        if self._host_in_allowlist(host) or self.core.settings.get("browser_allow_private_network", False):
            return True, None
        if host in {"localhost", "local", "ip6-localhost", "ip6-loopback"} or host.endswith(".local"):
            return False, f"Browser navigation to private/local host '{host}' is blocked by policy."
        try:
            ip = ipaddress.ip_address(host.strip("[]"))
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False, f"Browser navigation to private/local IP '{host}' is blocked by policy."
        except Exception:
            pass
        return True, None

    def _preflight_policy(self, action, args):
        if action in {"navigate", "open", "start"}:
            url = args.get("url") or args.get("targetUrl") or args.get("query_or_url")
            if url:
                ok, err = self._url_allowed(url)
                if not ok:
                    return False, "ERROR: " + err
        if (action == "cookies" or (action == "storage" and str(args.get("kind") or args.get("storage") or "").lower() == "cookies")) and args.get("includeValues"):
            ok, err = self._ensure_sensitive_allowed(
                "אישור חשיפת Cookies",
                "פעולת הדפדפן מבקשת לחשוף ערכי Cookies. העדף includeValues=false אלא אם המשתמש ביקש זאת במפורש.",
            )
            if not ok:
                return False, err
        if action in {"storage", "cookies"}:
            op = str(args.get("op") or args.get("operation") or "get").lower()
            if op in {"set", "add", "delete", "remove", "clear"}:
                ok, err = self._ensure_sensitive_allowed(
                    "אישור שינוי אחסון דפדפן",
                    f"פעולת הדפדפן מבקשת לשנות {action} עם op={op}.",
                )
                if not ok:
                    return False, err
        return True, None

    def _ensure_sensitive_allowed(self, title, details):
        checker = getattr(self.core, "_ensure_capability_allowed", None)
        if callable(checker):
            return checker("browser_automation", title, details, risk="high")
        return True, None

    def _result_page_urls(self, value):
        urls = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "url" and isinstance(item, str):
                    urls.append(item)
                elif key in {"page", "result", "tabs", "current"} or isinstance(item, (dict, list)):
                    urls.extend(self._result_page_urls(item))
        elif isinstance(value, list):
            for item in value:
                urls.extend(self._result_page_urls(item))
        return urls

    def _redact_blocked_urls(self, value):
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if key in {"url", "href", "src"} and isinstance(item, str):
                    ok, _ = self._url_allowed(item)
                    redacted[key] = item if ok else "[BLOCKED_BY_BROWSER_POLICY]"
                else:
                    redacted[key] = self._redact_blocked_urls(item)
            return redacted
        if isinstance(value, list):
            return [self._redact_blocked_urls(item) for item in value]
        return value

    def _postflight_policy(self, action, parsed):
        blocked = []
        for url in self._result_page_urls(parsed):
            ok, err = self._url_allowed(url)
            if not ok:
                blocked.append(err)
        if not blocked:
            return True, parsed, None
        if action in {"status", "doctor", "tabs", "trace", "console", "errors", "requests", "network"}:
            return True, self._redact_blocked_urls(parsed), None
        return False, None, "ERROR: Browser policy blocked the final page URL after the action. " + blocked[0]

    def _resolve_controlled_path(self, root, requested, suffix, default_prefix):
        root_path = Path(root).resolve()
        if requested:
            raw = str(requested).strip().strip('"\'')
            candidate = Path(os.path.expanduser(os.path.expandvars(raw)))
            if not candidate.is_absolute():
                candidate = root_path / candidate
            target = candidate.resolve()
            if target == root_path or target.is_dir():
                name = f"{default_prefix}_{int(time.time())}" + (f".{suffix}" if suffix else "")
                target = target / name
            if suffix and not target.suffix:
                target = target.with_suffix("." + suffix)
            if not (target == root_path or root_path in target.parents):
                return None, f"ERROR: Browser artifacts must stay inside the controlled directory: {root_path}"
            target.parent.mkdir(parents=True, exist_ok=True)
            return str(target), None
        name = f"{default_prefix}_{int(time.time())}" + (f".{suffix}" if suffix else "")
        target = root_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        return str(target), None

    def _prepare_upload_paths(self, args):
        paths = args.get("paths") or args.get("files") or args.get("path") or []
        if isinstance(paths, str):
            paths = [paths]
        resolved = []
        for path in paths:
            if not str(path or "").strip():
                continue
            target = self.core._abs_path(path)
            if not os.path.exists(target):
                return None, f"ERROR: Upload file not found: {target}"
            sandbox_ok, sandbox_err = self.core._ensure_sandbox_path_allowed(target, "read")
            if not sandbox_ok:
                return None, sandbox_err
            allowed, err = self.core._ensure_cloud_upload_allowed(target)
            if not allowed:
                return None, err
            resolved.append(target)
        return resolved, None

    def _prepare_paths(self, args, effective_action, effective_args):
        prepared = dict(args)
        captures = self._artifact_dir("captures")
        downloads = self._artifact_dir("downloads")
        prepared.setdefault("outputDir", captures)
        prepared.setdefault("downloadDir", downloads)

        if effective_action == "screenshot":
            path, err = self._resolve_controlled_path(captures, effective_args.get("path"), "png", "browser_screenshot")
            if err:
                return None, err
            prepared["path"] = path
        elif effective_action == "pdf":
            path, err = self._resolve_controlled_path(captures, effective_args.get("path"), "pdf", "browser_page")
            if err:
                return None, err
            prepared["path"] = path
        elif effective_action == "trace" and (effective_args.get("path") or effective_args.get("record") or effective_args.get("save")):
            path, err = self._resolve_controlled_path(captures, effective_args.get("path"), "json", "browser_trace")
            if err:
                return None, err
            prepared["path"] = path

        if effective_action == "download" or effective_args.get("expectDownload"):
            requested = effective_args.get("downloadPath") or effective_args.get("download_path")
            if not requested and effective_action == "download":
                requested = effective_args.get("path")
            if requested:
                path, err = self._resolve_controlled_path(downloads, requested, "", "download")
                if err:
                    return None, err
                prepared["downloadPath"] = path
            prepared["downloadDir"] = downloads

        if effective_action == "upload":
            paths, err = self._prepare_upload_paths(effective_args)
            if err:
                return None, err
            prepared["paths"] = paths
            prepared.pop("path", None)
        return prepared, None

    def _run_helper(self, payload):
        timeout = self.core._timeout("tool_timeout_seconds", 120)
        helper_payload = dict(payload or {})
        helper_payload.setdefault("action", "snapshot")
        helper_payload.setdefault("snapshot", self._snapshot_defaults())
        helper_payload.setdefault("outputDir", self._artifact_dir("captures"))
        helper_payload.setdefault("downloadDir", self._artifact_dir("downloads"))
        helper_payload.setdefault("debugPort", SMARTI_BROWSER_DEBUG_PORT)
        helper_payload.setdefault("timeoutMs", max(5000, int(timeout * 1000)))

        helper_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as fp:
                helper_path = fp.name
                fp.write(_HELPER_CODE)
            completed = self.core._run_cancelable_subprocess(
                [self.core._python_executable(), helper_path],
                input=json.dumps(helper_payload, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=WIN_CREATE_NO_WINDOW,
            )
            stdout = (completed.stdout or "").strip()
            stderr = (completed.stderr or "").strip()
            if completed.returncode != 0:
                detail = f"EXIT_CODE: {completed.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                return self.core._truncate_tool_output("ERROR: Browser action failed.\n" + detail)
            if not stdout:
                stdout = json.dumps({"ok": True, "message": "Browser action completed."}, ensure_ascii=False)
            result_lines = [line[len(HELPER_RESULT_PREFIX):] for line in stdout.splitlines() if line.startswith(HELPER_RESULT_PREFIX)]
            if result_lines:
                stdout = result_lines[-1].strip()
            else:
                detail = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                return self.core._truncate_tool_output("ERROR: Browser action returned no trusted result marker.\n" + detail)
            try:
                parsed = json.loads(stdout)
            except Exception:
                detail = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                return self.core._truncate_tool_output("ERROR: Browser action returned non-JSON output.\n" + detail)
            post_ok, parsed, post_err = self._postflight_policy(self._normalize_action(helper_payload.get("action")), parsed)
            if not post_ok:
                return post_err
            result_text = self._json(parsed)
            if isinstance(parsed, dict) and parsed.get("ok") is False:
                return "ERROR: Browser action failed.\n" + result_text
            return result_text
        except subprocess.TimeoutExpired:
            return f"ERROR: Browser action timeout after {timeout}s."
        except Exception as exc:
            return f"ERROR in browser action: {exc}"
        finally:
            if helper_path:
                try:
                    os.remove(helper_path)
                except Exception:
                    pass


_HELPER_CODE = textwrap.dedent(
    r'''
    import json
    import os
    import re
    import sys
    import time

    sys.stdin = open(sys.stdin.fileno(), mode="r", encoding="utf-8", errors="replace", closefd=False)
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)
    sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)

    RESULT_PREFIX = "SMARTI_BROWSER_RESULT="

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(RESULT_PREFIX + json.dumps({"ok": False, "error": f"Missing Playwright. Install requirements.txt: {exc}"}, ensure_ascii=False))
        sys.exit(1)

    MARK = "data-smarti-ref"

    INSTALL_JS = r"""
    (() => {
      if (window.__smartiHooksInstalled) return true;
      window.__smartiHooksInstalled = true;
      window.__smartiConsoleHistory = window.__smartiConsoleHistory || [];
      window.__smartiRequests = window.__smartiRequests || [];
      window.__smartiErrors = window.__smartiErrors || [];
      const pushBounded = (arr, item, max = 800) => {
        try {
          arr.push(item);
          while (arr.length > max) arr.shift();
        } catch (e) {}
      };
      const stringifyArg = (v) => {
        try {
          if (typeof v === 'string') return v;
          if (v instanceof Error) return v.stack || v.message || String(v);
          return JSON.stringify(v);
        } catch (e) {
          return String(v);
        }
      };
      for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
        const original = console[level] ? console[level].bind(console) : console.log.bind(console);
        console[level] = (...args) => {
          try {
            const item = {level, ts: Date.now(), text: args.map(stringifyArg).join(' ')};
            pushBounded(window.__smartiConsoleHistory, item, 600);
            if (level === 'error') pushBounded(window.__smartiErrors, item, 300);
          } catch (e) {}
          return original(...args);
        };
      }
      window.addEventListener('error', event => {
        try {
          const item = {
            level: 'pageerror',
            ts: Date.now(),
            text: event.message || String(event.error || ''),
            source: event.filename || '',
            line: event.lineno || 0,
            column: event.colno || 0
          };
          pushBounded(window.__smartiConsoleHistory, item, 600);
          pushBounded(window.__smartiErrors, item, 300);
        } catch (e) {}
      });
      window.addEventListener('unhandledrejection', event => {
        try {
          const item = {level: 'unhandledrejection', ts: Date.now(), text: stringifyArg(event.reason || '')};
          pushBounded(window.__smartiConsoleHistory, item, 600);
          pushBounded(window.__smartiErrors, item, 300);
        } catch (e) {}
      });
      const previewBody = (body) => {
        try {
          if (typeof body === 'string') return body.slice(0, 2000);
          if (body instanceof URLSearchParams) return body.toString().slice(0, 2000);
          if (body && typeof body === 'object' && !(body instanceof FormData)) return JSON.stringify(body).slice(0, 2000);
        } catch (e) {}
        return '';
      };
      if (window.fetch && !window.__smartiFetchWrapped) {
        window.__smartiFetchWrapped = true;
        const originalFetch = window.fetch.bind(window);
        window.fetch = async (...args) => {
          const started = Date.now();
          let url = '';
          let method = 'GET';
          let requestBodyPreview = '';
          try {
            const input = args[0];
            const init = args[1] || {};
            url = typeof input === 'string' ? input : (input && input.url) || '';
            method = (init.method || (input && input.method) || 'GET').toUpperCase();
            requestBodyPreview = previewBody(init.body);
          } catch (e) {}
          try {
            const response = await originalFetch(...args);
            let responseBodyPreview = '';
            try {
              const type = response.headers && response.headers.get('content-type') || '';
              if (/json|text|html|xml|javascript|x-www-form-urlencoded/i.test(type)) {
                responseBodyPreview = (await response.clone().text()).slice(0, 4000);
              }
            } catch (e) {}
            pushBounded(window.__smartiRequests, {
              kind: 'fetch',
              ts: started,
              durationMs: Date.now() - started,
              url,
              method,
              status: response.status,
              ok: response.ok,
              type: response.type,
              requestBodyPreview,
              responseBodyPreview
            });
            return response;
          } catch (err) {
            pushBounded(window.__smartiRequests, {
              kind: 'fetch',
              ts: started,
              durationMs: Date.now() - started,
              url,
              method,
              error: stringifyArg(err),
              requestBodyPreview
            });
            throw err;
          }
        };
      }
      if (window.XMLHttpRequest && !window.__smartiXhrWrapped) {
        window.__smartiXhrWrapped = true;
        const OriginalXHR = window.XMLHttpRequest;
        window.XMLHttpRequest = function() {
          const xhr = new OriginalXHR();
          let meta = {kind: 'xhr', ts: Date.now(), method: 'GET', url: ''};
          const open = xhr.open;
          xhr.open = function(method, url, ...rest) {
            meta.method = String(method || 'GET').toUpperCase();
            meta.url = String(url || '');
            return open.call(xhr, method, url, ...rest);
          };
          const send = xhr.send;
          xhr.send = function(body) {
            meta.ts = Date.now();
            meta.requestBodyPreview = previewBody(body);
            xhr.addEventListener('loadend', () => {
              let responseBodyPreview = '';
              try {
                const type = xhr.getResponseHeader('content-type') || '';
                if (/json|text|html|xml|javascript|x-www-form-urlencoded/i.test(type) && typeof xhr.responseText === 'string') {
                  responseBodyPreview = xhr.responseText.slice(0, 4000);
                }
              } catch (e) {}
              pushBounded(window.__smartiRequests, {
                ...meta,
                durationMs: Date.now() - meta.ts,
                status: xhr.status,
                ok: xhr.status >= 200 && xhr.status < 400,
                responseBodyPreview
              });
            });
            return send.call(xhr, body);
          };
          return xhr;
        };
      }
      return true;
    })();
    """

    COLLECT_JS = r"""
    (options) => {
      options = options || {};
      const limit = options.limit || 120;
      const bodyChars = options.bodyChars || 8000;
      const htmlLimit = options.htmlChars || 600;
      const maxChars = options.maxChars || 12000;
      const includeUrls = options.includeUrls !== false;
      const includeHidden = !!options.includeHidden;
      const MARK = 'data-smarti-ref';
      const selector = [
        'a','button','input','textarea','select','option','summary','label',
        'h1','h2','h3','h4','h5','h6','main','nav','header','footer',
        '[role]','[aria-label]','[tabindex]','[contenteditable="true"]',
        'iframe','video','audio','details','dialog'
      ].join(',');
      if (!window.__smartiRefSeq) window.__smartiRefSeq = 1;
      if (!window.__smartiSnapshotEpoch) window.__smartiSnapshotEpoch = 0;
      window.__smartiRefMapByEpoch = window.__smartiRefMapByEpoch || {};
      window.__smartiSnapshotEpoch += 1;
      const epoch = window.__smartiSnapshotEpoch;
      window.__smartiRefMap = {};

      function clean(text, max = 700) {
        return String(text || '').replace(/\s+/g, ' ').trim().slice(0, max);
      }
      function cssEscape(value) {
        if (window.CSS && CSS.escape) return CSS.escape(value);
        return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
      }
      function textOf(el) {
        const labelledBy = el.getAttribute('aria-labelledby');
        let labelled = '';
        if (labelledBy) {
          labelled = labelledBy.split(/\s+/).map(id => {
            const node = document.getElementById(id);
            return node ? node.innerText || node.textContent || '' : '';
          }).join(' ');
        }
        return clean(
          el.getAttribute('aria-label') || labelled || el.innerText || el.value ||
          el.getAttribute('title') || el.getAttribute('placeholder') || el.alt || ''
        );
      }
      function roleOf(el) {
        const explicit = el.getAttribute('role');
        if (explicit) return explicit;
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute('type') || '').toLowerCase();
        if (tag === 'a' && el.href) return 'link';
        if (tag === 'button' || type === 'button' || type === 'submit' || type === 'reset') return 'button';
        if (tag === 'select') return 'combobox';
        if (tag === 'textarea') return 'textbox';
        if (tag === 'input') {
          if (type === 'checkbox') return 'checkbox';
          if (type === 'radio') return 'radio';
          if (type === 'range') return 'slider';
          return 'textbox';
        }
        if (/^h[1-6]$/.test(tag)) return 'heading';
        if (tag === 'summary') return 'button';
        if (tag === 'iframe') return 'iframe';
        if (tag === 'dialog') return 'dialog';
        return tag;
      }
      function visible(el) {
        if (includeHidden) return true;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        if (!style || style.visibility === 'hidden' || style.display === 'none') return false;
        if (rect.width <= 0 || rect.height <= 0) return false;
        if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight * 2 || rect.left > window.innerWidth * 2) return false;
        return true;
      }
      function attrSelector(el) {
        const attrs = ['data-testid','data-test','aria-label','name','placeholder','title','type'];
        for (const name of attrs) {
          const value = el.getAttribute(name);
          if (value) return el.tagName.toLowerCase() + '[' + name + '="' + String(value).replace(/"/g, '\\"') + '"]';
        }
        return '';
      }
      function selectorFor(el) {
        if (el.id) return '#' + cssEscape(el.id);
        const attr = attrSelector(el);
        if (attr) return attr;
        let part = el.tagName.toLowerCase();
        if (el.className && typeof el.className === 'string') {
          const classes = el.className.trim().split(/\s+/).slice(0, 3).filter(Boolean);
          if (classes.length) part += '.' + classes.map(cssEscape).join('.');
        }
        return part;
      }
      function stableRef(el) {
        let ref = el.getAttribute(MARK);
        if (!ref) {
          ref = 'e' + (window.__smartiRefSeq++);
          try { el.setAttribute(MARK, ref); } catch (e) {}
        }
        return ref;
      }

      const seen = new Set();
      const nodes = Array.from(document.querySelectorAll(selector)).filter(el => {
        if (seen.has(el)) return false;
        seen.add(el);
        return visible(el);
      }).slice(0, limit);
      const elements = nodes.map((el, index) => {
        const ref = stableRef(el);
        const rect = el.getBoundingClientRect();
        const item = {
          ref, index, epoch,
          tag: el.tagName.toLowerCase(),
          role: roleOf(el),
          name: el.getAttribute('name') || '',
          id: el.id || '',
          type: el.getAttribute('type') || '',
          selector: selectorFor(el),
          text: textOf(el),
          value: clean(el.value || ''),
          placeholder: el.getAttribute('placeholder') || '',
          ariaLabel: el.getAttribute('aria-label') || '',
          title: el.getAttribute('title') || '',
          disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
          checked: !!el.checked || el.getAttribute('aria-checked') === 'true',
          selected: !!el.selected,
          editable: el.isContentEditable || ['input','textarea','select'].includes(el.tagName.toLowerCase()),
          rect: {
            x: Math.round(rect.x), y: Math.round(rect.y),
            width: Math.round(rect.width), height: Math.round(rect.height)
          },
          html: (el.outerHTML || '').slice(0, htmlLimit)
        };
        if (includeUrls) {
          item.href = el.href || '';
          item.src = el.src || '';
        }
        window.__smartiRefMap[ref] = {
          ref, epoch, role: item.role, name: item.text || item.ariaLabel || item.name,
          selector: item.selector, tag: item.tag, editable: item.editable,
          disabled: item.disabled, rect: item.rect, href: item.href || '', src: item.src || ''
        };
        return item;
      });

      const lines = [];
      let charCount = 0;
      let truncated = false;
      const pushLine = (line) => {
        if (truncated) return;
        const cleanLine = clean(line, 500);
        if (charCount + cleanLine.length + 1 > maxChars) {
          truncated = true;
          return;
        }
        lines.push(cleanLine);
        charCount += cleanLine.length + 1;
      };
      pushLine(`page "${clean(document.title, 120)}" ${location.href}`);
      for (const item of elements) {
        const name = clean(item.text || item.ariaLabel || item.placeholder || item.value || item.title || item.name, 180);
        const state = [
          item.disabled ? 'disabled' : '',
          item.checked ? 'checked' : '',
          item.editable ? 'editable' : ''
        ].filter(Boolean).join(' ');
        const href = item.href ? ` -> ${clean(item.href, 160)}` : '';
        pushLine(`- ${item.role || item.tag} "${name}" [ref=${item.ref}]${state ? ' [' + state + ']' : ''}${href}`);
      }
      const bodyText = document.body ? document.body.innerText || '' : '';
      const refs = {...window.__smartiRefMap};
      window.__smartiLatestSnapshotEpoch = epoch;
      window.__smartiRefMapByEpoch[String(epoch)] = refs;
      const retainedEpochs = Object.keys(window.__smartiRefMapByEpoch).map(Number).sort((a, b) => a - b);
      while (retainedEpochs.length > 8) {
        const stale = String(retainedEpochs.shift());
        delete window.__smartiRefMapByEpoch[stale];
      }
      return {
        url: location.href,
        title: document.title,
        readyState: document.readyState,
        epoch,
        snapshotEpoch: epoch,
        snapshot: lines.join('\n') + (truncated ? '\n[SNAPSHOT_TRUNCATED]' : ''),
        refs,
        refMapMeta: {latestEpoch: epoch, retainedEpochs: Object.keys(window.__smartiRefMapByEpoch).map(Number).sort((a, b) => a - b), refCount: Object.keys(refs).length},
        stats: {elements: elements.length, refs: Object.keys(refs).length, truncated},
        viewport: {width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio || 1},
        scroll: {x: Math.round(window.scrollX), y: Math.round(window.scrollY), maxY: Math.max(0, document.documentElement.scrollHeight - window.innerHeight)},
        bodyText: bodyText.replace(/\s+/g, ' ').trim().slice(0, bodyChars),
        elements
      };
    }
    """

    OVERLAY_JS = r"""
    ({elements, clearOnly, fullPage}) => {
      for (const old of Array.from(document.querySelectorAll('[data-smarti-overlay="true"]'))) old.remove();
      if (clearOnly) return true;
      const root = document.createElement('div');
      root.setAttribute('data-smarti-overlay', 'true');
      root.style.cssText = (fullPage
        ? 'position:absolute;left:0;top:0;width:100%;height:100%;'
        : 'position:fixed;left:0;top:0;right:0;bottom:0;') + 'z-index:2147483647;pointer-events:none;font:12px Arial,sans-serif;';
      const sx = fullPage ? window.scrollX : 0;
      const sy = fullPage ? window.scrollY : 0;
      for (const item of (elements || []).slice(0, 160)) {
        const r = item.rect || {};
        const box = document.createElement('div');
        box.style.cssText = `position:absolute;left:${Math.max(0, (r.x || 0) + sx)}px;top:${Math.max(0, (r.y || 0) + sy)}px;width:${Math.max(1, r.width || 1)}px;height:${Math.max(1, r.height || 1)}px;border:2px solid #ff2d55;background:rgba(255,45,85,.08);box-sizing:border-box;`;
        const badge = document.createElement('div');
        badge.textContent = String(item.number || '') + (item.ref ? ':' + item.ref : '');
        badge.style.cssText = 'position:absolute;left:-2px;top:-18px;background:#ff2d55;color:white;padding:1px 4px;border-radius:3px;font-weight:700;line-height:14px;';
        box.appendChild(badge);
        root.appendChild(box);
      }
      document.documentElement.appendChild(root);
      return true;
    }
    """

    def compact(value, limit=500):
        text = "" if value is None else str(value)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit] + ("..." if len(text) > limit else "")

    def to_int(value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    def timeout_ms(payload):
        return max(1000, to_int(payload.get("timeoutMs") or payload.get("timeout_ms") or payload.get("timeout") or 30000, 30000))

    def sanitize_name(value, default="browser_capture"):
        text = compact(value or default, 80)
        text = re.sub(r"[^\w.\-]+", "_", text, flags=re.UNICODE).strip("._-")
        return text or default

    def output_path(payload, suffix):
        path = payload.get("path")
        if path:
            return os.path.abspath(os.path.expanduser(str(path)))
        output_dir = payload.get("outputDir") or os.getcwd()
        os.makedirs(output_dir, exist_ok=True)
        title = payload.get("titleHint") or "browser"
        return os.path.join(output_dir, f"{sanitize_name(title)}_{int(time.time())}.{suffix}")

    def emit_result(payload):
        print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=False, default=str))

    def want_true(payload, *names):
        return any(payload.get(name) is True for name in names)

    def connect(payload):
        pw = sync_playwright().start()
        endpoint = payload.get("cdpEndpoint") or f"http://127.0.0.1:{payload.get('debugPort') or 49223}"
        browser = pw.chromium.connect_over_cdp(endpoint, timeout=timeout_ms(payload))
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        try:
            context.add_init_script(INSTALL_JS)
        except Exception:
            pass
        if not context.pages:
            context.new_page()
        return pw, browser, context

    def install_page_hooks(page):
        try:
            page.evaluate(INSTALL_JS)
        except Exception:
            pass

    def target_id(context, page):
        try:
            session = context.new_cdp_session(page)
            try:
                info = session.send("Target.getTargetInfo")
                tid = ((info or {}).get("targetInfo") or {}).get("targetId")
                if tid:
                    return str(tid)
            finally:
                try:
                    session.detach()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            return page.evaluate("""() => {
              try {
                let id = sessionStorage.getItem('__smarti_tab_id');
                if (!id) {
                  id = 'tab-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
                  sessionStorage.setItem('__smarti_tab_id', id);
                }
                return id;
              } catch (e) {
                if (!window.__smartiTabId) window.__smartiTabId = 'tab-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
                return window.__smartiTabId;
              }
            }""")
        except Exception:
            pages = context.pages
            try:
                return "p" + str(pages.index(page))
            except Exception:
                return "p0"

    def page_ref(context, page):
        return target_id(context, page)

    def tab_id_for(tid):
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "", str(tid or "tab"))
        return "tab_" + (safe[:16] or "current")

    def get_tab_label(page):
        try:
            return page.evaluate("""() => {
              try { return window.__smartiTabLabel || sessionStorage.getItem('__smarti_tab_label') || ''; }
              catch (e) { return window.__smartiTabLabel || ''; }
            }""") or ""
        except Exception:
            return ""

    def set_tab_label(page, label):
        if label is None:
            return
        text = compact(label, 80)
        try:
            page.evaluate("""label => {
              window.__smartiTabLabel = label || '';
              try { sessionStorage.setItem('__smarti_tab_label', label || ''); } catch (e) {}
            }""", text)
        except Exception:
            pass

    def tabs(context, current=None):
        result = []
        for index, page in enumerate(context.pages):
            try:
                tid = target_id(context, page)
                result.append({
                    "index": index,
                    "targetId": tid,
                    "tabId": tab_id_for(tid),
                    "legacyTargetId": f"p{index}",
                    "current": page == current,
                    "label": get_tab_label(page),
                    "title": page.title(),
                    "url": page.url,
                })
            except Exception as exc:
                result.append({"index": index, "targetId": f"p{index}", "error": str(exc)})
        return result

    def select_page(context, payload):
        target = str(payload.get("targetId") or payload.get("target_id") or payload.get("tabId") or payload.get("tab_id") or payload.get("target") or "").strip()
        pages = context.pages
        if target:
            lowered = target.lower()
            if lowered.startswith("p") and lowered[1:].isdigit():
                idx = int(lowered[1:])
                if 0 <= idx < len(pages):
                    return pages[idx]
            for page in pages:
                try:
                    tid = target_id(context, page)
                    candidates = {
                        tid.lower(),
                        tab_id_for(tid).lower(),
                        get_tab_label(page).lower(),
                        (page.url or "").lower(),
                        (page.title() or "").lower(),
                    }
                    if lowered in candidates or any(lowered and lowered in item for item in candidates):
                        return page
                except Exception:
                    pass
            raise ValueError(f"Target tab not found: {target}")
        return pages[-1] if pages else context.new_page()

    def validate_ref(page, payload):
        ref = str(payload.get("ref") or "").strip()
        if not ref:
            return {}
        expected_epoch = payload.get("snapshotEpoch", payload.get("snapshot_epoch", payload.get("epoch", payload.get("refEpoch", payload.get("ref_epoch")))))
        if payload.get("allowStaleRef"):
            expected_epoch = None
        info = page.evaluate(
            """([mark, ref, expectedEpoch]) => {
              const el = document.querySelector('[' + mark + '="' + String(ref).replace(/"/g, '\\"') + '"]');
              const latest = window.__smartiLatestSnapshotEpoch || 0;
              const byEpoch = window.__smartiRefMapByEpoch || {};
              const epochKey = expectedEpoch === null || expectedEpoch === undefined || expectedEpoch === '' ? '' : String(expectedEpoch);
              const inExpectedEpoch = epochKey ? !!((byEpoch[epochKey] || {})[ref]) : true;
              const inLatestEpoch = latest ? !!((byEpoch[String(latest)] || {})[ref]) : false;
              return {
                exists: !!el,
                ref,
                expectedEpoch: epochKey,
                latestEpoch: latest,
                inExpectedEpoch,
                inLatestEpoch,
                retainedEpochs: Object.keys(byEpoch).map(Number).filter(n => !Number.isNaN(n)).sort((a, b) => a - b)
              };
            }""",
            [MARK, ref, expected_epoch],
        )
        if not info.get("exists"):
            raise ValueError(f"Stale or missing browser ref '{ref}'. Take a fresh snapshot for the same targetId and retry with the new ref.")
        if info.get("expectedEpoch") and not info.get("inExpectedEpoch"):
            raise ValueError(
                f"Browser ref '{ref}' is not in snapshotEpoch {info.get('expectedEpoch')}. "
                f"Latest snapshotEpoch is {info.get('latestEpoch')}; resnapshot and retry."
            )
        return info

    def remember_snapshot_refs(page, state):
        try:
            refs = state.get("refs") or {}
            epoch = state.get("epoch") or state.get("snapshotEpoch")
            if not refs or not epoch:
                return
            page.evaluate(
                """({epoch, refs}) => {
                  window.__smartiRefMapByEpoch = window.__smartiRefMapByEpoch || {};
                  window.__smartiRefMap = Object.assign(window.__smartiRefMap || {}, refs || {});
                  window.__smartiRefMapByEpoch[String(epoch)] = Object.assign(window.__smartiRefMapByEpoch[String(epoch)] || {}, refs || {});
                  window.__smartiLatestSnapshotEpoch = epoch;
                }""",
                {"epoch": epoch, "refs": refs},
            )
        except Exception:
            pass

    def ax_value(node, key):
        value = node.get(key)
        if isinstance(value, dict):
            return value.get("value", "")
        return value or ""

    def ref_for_backend(session, backend_id):
        try:
            resolved = session.send("DOM.resolveNode", {"backendNodeId": int(backend_id)})
            obj = ((resolved or {}).get("object") or {})
            object_id = obj.get("objectId")
            if not object_id:
                return ""
            try:
                call = session.send("Runtime.callFunctionOn", {
                    "objectId": object_id,
                    "functionDeclaration": """
                    function(mark) {
                      if (!this || !this.getAttribute || !this.setAttribute) return '';
                      let ref = this.getAttribute(mark);
                      if (!ref) {
                        const root = this.ownerDocument && this.ownerDocument.defaultView || window;
                        if (!root.__smartiRefSeq) root.__smartiRefSeq = 1;
                        ref = 'e' + (root.__smartiRefSeq++);
                        this.setAttribute(mark, ref);
                      }
                      return ref;
                    }
                    """,
                    "arguments": [{"value": MARK}],
                    "returnByValue": True,
                    "silent": True,
                })
                return str(((call or {}).get("result") or {}).get("value") or "")
            finally:
                try:
                    session.send("Runtime.releaseObject", {"objectId": object_id})
                except Exception:
                    pass
        except Exception:
            return ""

    def accessibility_snapshot(context, page, payload):
        refs_mode = str(payload.get("refs") or payload.get("snapshotFormat") or payload.get("snapshot_format") or "aria").lower()
        if refs_mode in {"dom", "html"}:
            return {}
        snap = dict(payload.get("snapshot") or {})
        limit = to_int(payload.get("limit", snap.get("elementLimit", 120)), 120)
        max_chars = to_int(payload.get("maxChars", payload.get("max_chars", snap.get("maxChars", 12000))), 12000)
        session = None
        try:
            session = context.new_cdp_session(page)
            data = session.send("Accessibility.getFullAXTree", {})
            nodes = (data or {}).get("nodes") or []
            by_id = {str(n.get("nodeId")): n for n in nodes if n.get("nodeId") is not None}
            depth_cache = {}

            def depth(node):
                node_id = str(node.get("nodeId"))
                if node_id in depth_cache:
                    return depth_cache[node_id]
                parent_id = str(node.get("parentId") or "")
                if not parent_id or parent_id not in by_id:
                    depth_cache[node_id] = 0
                else:
                    depth_cache[node_id] = min(8, depth(by_id[parent_id]) + 1)
                return depth_cache[node_id]

            lines = []
            entries = []
            chars = 0
            for node in nodes:
                if len(entries) >= limit:
                    break
                if node.get("ignored"):
                    continue
                role = compact(ax_value(node, "role"), 80)
                name = compact(ax_value(node, "name") or ax_value(node, "value") or ax_value(node, "description"), 220)
                if not role or (not name and role in {"generic", "none", "RootWebArea", "StaticText"}):
                    continue
                backend = node.get("backendDOMNodeId")
                ref = ref_for_backend(session, backend) if backend else ""
                if not ref and role not in {"RootWebArea", "WebArea"}:
                    continue
                props = []
                for prop in node.get("properties") or []:
                    pname = prop.get("name")
                    pval = prop.get("value")
                    if pname in {"disabled", "focused", "checked", "selected", "expanded", "pressed", "required"}:
                        props.append(f"{pname}={ax_value(prop, 'value') if isinstance(prop, dict) else pval}")
                line = f"{'  ' * depth(node)}- {role} \"{name}\""
                if ref:
                    line += f" [ref={ref}]"
                if props:
                    line += " [" + ", ".join(compact(p, 40) for p in props[:4]) + "]"
                if chars + len(line) + 1 > max_chars:
                    lines.append("[AX_SNAPSHOT_TRUNCATED]")
                    break
                lines.append(line)
                chars += len(line) + 1
                entries.append({
                    "ref": ref,
                    "role": role,
                    "name": name,
                    "backendDOMNodeId": backend,
                    "depth": depth(node),
                })
            return {"snapshot": "\n".join(lines), "nodes": entries, "stats": {"nodes": len(entries), "totalNodes": len(nodes), "truncated": len(entries) >= limit}}
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            try:
                if session is not None:
                    session.detach()
            except Exception:
                pass

    def snapshot(page, payload, context=None):
        install_page_hooks(page)
        snap = dict(payload.get("snapshot") or {})
        limit = to_int(payload.get("limit", payload.get("max_elements", snap.get("elementLimit", 120))), 120)
        body_chars = to_int(payload.get("body_chars", payload.get("bodyChars", snap.get("bodyChars", 8000))), 8000)
        html_chars = to_int(payload.get("html_chars", payload.get("htmlChars", snap.get("htmlChars", 600))), 600)
        max_chars = to_int(payload.get("maxChars", payload.get("max_chars", snap.get("maxChars", 12000))), 12000)
        ax = accessibility_snapshot(context, page, payload) if context is not None else {}
        state = page.evaluate(COLLECT_JS, {
            "limit": limit,
            "bodyChars": body_chars,
            "htmlChars": html_chars,
            "maxChars": max_chars,
            "includeUrls": bool(payload.get("urls", payload.get("includeUrls", payload.get("include_urls", True)))),
            "includeHidden": bool(payload.get("includeHidden", False)),
        })
        if ax:
            state["accessibilityTree"] = ax
            if ax.get("snapshot"):
                dom_text = state.get("snapshot") or ""
                combined = (ax["snapshot"] + "\n\nDOM actionable refs:\n" + dom_text).strip()
                state["snapshot"] = combined[:max_chars] + ("\n[SNAPSHOT_TRUNCATED]" if len(combined) > max_chars else "")
            refs = state.setdefault("refs", {})
            for node in ax.get("nodes") or []:
                ref = node.get("ref")
                if ref and ref not in refs:
                    refs[ref] = {"ref": ref, "epoch": state.get("epoch"), "role": node.get("role"), "name": node.get("name"), "backendDOMNodeId": node.get("backendDOMNodeId")}
        try:
            body_locator = page.locator("body")
            aria_snapshot = getattr(body_locator, "aria_snapshot", None)
            if callable(aria_snapshot):
                state["playwrightAriaSnapshot"] = aria_snapshot(timeout=min(3000, timeout_ms(payload)))
        except Exception:
            pass
        state["targetId"] = page_ref(context, page) if context is not None else ""
        state["tabId"] = tab_id_for(state["targetId"])
        state["label"] = get_tab_label(page)
        meta = state.setdefault("refMapMeta", {})
        meta.update({"targetId": state["targetId"], "tabId": state["tabId"], "snapshotEpoch": state.get("epoch"), "refCount": len(state.get("refs") or {})})
        remember_snapshot_refs(page, state)
        return state or {}

    def locator(page, payload):
        ref = str(payload.get("ref") or "").strip()
        selector = str(payload.get("selector") or "").strip()
        role = str(payload.get("role") or "").strip()
        name = payload.get("name")
        text = payload.get("textSelector")
        if ref:
            validate_ref(page, payload)
            return page.locator(f'[{MARK}="{ref}"]').first
        if selector:
            return page.locator(selector).first
        if role:
            opts = {"name": name} if name not in (None, "") else {}
            return page.get_by_role(role, **opts).first
        if text:
            return page.get_by_text(str(text)).first
        raise ValueError("Action requires ref, selector, role+name, or textSelector.")

    def post(page, payload, result=None, context=None):
        if payload.get("noSnapshot"):
            return {"ok": True, "result": result}
        return {"ok": True, "result": result, "page": snapshot(page, payload, context)}

    def with_dialog(page, payload, action):
        dialog_result = {}
        wants_handler = any(k in payload for k in ("accept", "promptText", "expectDialog"))
        if not wants_handler:
            return action(), dialog_result

        def handler(dialog):
            dialog_result.update({"type": dialog.type, "message": dialog.message, "defaultValue": dialog.default_value})
            if payload.get("promptText") is not None:
                dialog.accept(str(payload.get("promptText")))
            elif payload.get("accept", True):
                dialog.accept()
            else:
                dialog.dismiss()

        page.once("dialog", handler)
        return action(), dialog_result

    def navigate(context, page, payload, new_tab=False):
        url = payload.get("url") or payload.get("targetUrl") or payload.get("target_url") or payload.get("query_or_url")
        if not url:
            raise ValueError("navigate/open requires url.")
        if new_tab:
            page = context.new_page()
            install_page_hooks(page)
        page.goto(str(url), wait_until=payload.get("waitUntil") or payload.get("wait_until") or "domcontentloaded", timeout=timeout_ms(payload))
        if payload.get("label") is not None:
            set_tab_label(page, payload.get("label"))
        return post(page, payload, {"targetId": page_ref(context, page), "tabId": tab_id_for(page_ref(context, page)), "url": page.url, "title": page.title(), "label": get_tab_label(page)}, context)

    def click(page, payload, context=None):
        if payload.get("x") is not None and payload.get("y") is not None and not (payload.get("ref") or payload.get("selector")):
            x, y = float(payload.get("x")), float(payload.get("y"))
            result, dialog = with_dialog(page, payload, lambda: page.mouse.click(x, y))
            return post(page, payload, {"clicked": "coords", "x": x, "y": y, "dialog": dialog}, context)
        loc = locator(page, payload)
        download_info = None
        if payload.get("expectDownload"):
            with page.expect_download(timeout=timeout_ms(payload)) as download_wait:
                _, dialog = with_dialog(page, payload, lambda: loc.click(timeout=timeout_ms(payload)))
            download = download_wait.value
            path = payload.get("downloadPath") or payload.get("download_path")
            if not path:
                output_dir = payload.get("downloadDir") or payload.get("outputDir") or os.getcwd()
                os.makedirs(output_dir, exist_ok=True)
                path = os.path.join(output_dir, sanitize_name(download.suggested_filename, "download"))
            elif os.path.isdir(path):
                path = os.path.join(path, sanitize_name(download.suggested_filename, "download"))
            download.save_as(path)
            download_info = {"path": path, "suggestedFilename": download.suggested_filename}
        else:
            _, dialog = with_dialog(page, payload, lambda: loc.click(timeout=timeout_ms(payload)))
        return post(page, payload, {"clicked": payload.get("ref") or payload.get("selector") or "locator", "dialog": dialog, "download": download_info}, context)

    def fill(page, payload, typing=False, context=None):
        loc = locator(page, payload)
        text = str(payload.get("text", payload.get("value", "")))
        loc.scroll_into_view_if_needed(timeout=timeout_ms(payload))
        loc.focus(timeout=timeout_ms(payload))
        delay_ms = to_int(payload.get("delayMs", payload.get("delay_ms", 0)), 0)
        if not delay_ms:
            delay_ms = max(0, int(float(payload.get("delay", 0.02)) * 1000))
        if typing and payload.get("clear") is False:
            try:
                loc.type(text, delay=delay_ms, timeout=timeout_ms(payload))
            except Exception:
                page.keyboard.insert_text(text)
        elif typing and payload.get("slowly"):
            loc.fill("", timeout=timeout_ms(payload))
            try:
                loc.type(text, delay=delay_ms or 40, timeout=timeout_ms(payload))
            except Exception:
                page.keyboard.insert_text(text)
        else:
            loc.fill(text, timeout=timeout_ms(payload))
        if payload.get("submit"):
            loc.press("Enter", timeout=timeout_ms(payload))
        return post(page, payload, {"typed": len(text), "target": payload.get("ref") or payload.get("selector")}, context)

    def press(page, payload, context=None):
        keys = payload.get("keys", payload.get("key", payload.get("text", "")))
        if not isinstance(keys, list):
            keys = [keys]
        if payload.get("ref") or payload.get("selector") or payload.get("role") or payload.get("textSelector"):
            loc = locator(page, payload)
            loc.focus(timeout=timeout_ms(payload))
            for key in keys:
                loc.press(str(key), timeout=timeout_ms(payload))
        else:
            for key in keys:
                page.keyboard.press(str(key))
        return post(page, payload, {"pressed": [str(k) for k in keys]}, context)

    def select_value(page, payload, context=None):
        loc = locator(page, payload)
        value = payload.get("value")
        label = payload.get("label") or payload.get("text")
        index = payload.get("index")
        option = {}
        if value is not None:
            option["value"] = str(value)
        elif label is not None:
            option["label"] = str(label)
        elif index is not None:
            option["index"] = to_int(index, 0)
        else:
            raise ValueError("select requires value, label/text, or index.")
        loc.select_option(**option, timeout=timeout_ms(payload))
        return post(page, payload, {"selected": option}, context)

    def upload(page, payload, context=None):
        loc = locator(page, payload)
        paths = payload.get("paths") or payload.get("files") or payload.get("path") or []
        if isinstance(paths, str):
            paths = [paths]
        paths = [os.path.abspath(os.path.expanduser(str(path))) for path in paths if str(path).strip()]
        missing = [path for path in paths if not os.path.exists(path)]
        if missing:
            raise FileNotFoundError("Missing upload files: " + ", ".join(missing))
        loc.set_input_files(paths, timeout=timeout_ms(payload))
        return post(page, payload, {"uploaded": paths}, context)

    def wait(page, payload, context=None):
        if payload.get("timeMs") or payload.get("time_ms") or payload.get("ms"):
            ms = to_int(payload.get("timeMs") or payload.get("time_ms") or payload.get("ms"), 0)
            page.wait_for_timeout(ms)
            return post(page, payload, {"waitedMs": ms}, context)
        if payload.get("selector"):
            page.wait_for_selector(str(payload.get("selector")), timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "selector", "selector": payload.get("selector")}, context)
        if payload.get("text"):
            page.get_by_text(str(payload.get("text"))).first.wait_for(timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "text", "text": payload.get("text")}, context)
        if payload.get("urlContains") or payload.get("url"):
            needle = str(payload.get("urlContains") or payload.get("url"))
            page.wait_for_url(lambda url: needle in url, timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "url", "url": needle}, context)
        if payload.get("function") or payload.get("script"):
            page.wait_for_function(str(payload.get("function") or payload.get("script")), timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "function"}, context)
        page.wait_for_load_state(payload.get("state") or "domcontentloaded", timeout=timeout_ms(payload))
        return post(page, payload, {"matched": "loadState"}, context)

    def evaluate(page, payload, context=None):
        source = str(payload.get("script") or payload.get("expression") or "")
        if not source.strip():
            raise ValueError("evaluate requires script or expression.")
        handle = None
        if payload.get("ref") or payload.get("selector") or payload.get("role") or payload.get("textSelector"):
            handle = locator(page, payload).element_handle(timeout=timeout_ms(payload))
        element_runner = """(arg, source) => {
          try {
            const candidate = (0, eval)('(' + source + ')');
            if (typeof candidate === 'function') return candidate(arg);
          } catch (err) {}
          return (new Function('el', source))(arg);
        }"""
        page_runner = """(source) => {
          const arg = null;
          try {
            const candidate = (0, eval)('(' + source + ')');
            if (typeof candidate === 'function') return candidate(arg);
          } catch (err) {}
          return (new Function('el', source))(arg);
        }"""
        try:
            if handle is not None:
                result = handle.evaluate(element_runner, source)
                handle.dispose()
            else:
                result = page.evaluate(page_runner, source)
        finally:
            try:
                if handle is not None:
                    handle.dispose()
            except Exception:
                pass
        return post(page, payload, {"value": result}, context)

    def cdp(context, page, payload):
        method = str(payload.get("method") or "").strip()
        params = payload.get("params") or {}
        if not method:
            raise ValueError("cdp requires method, for example Runtime.evaluate or Network.enable.")
        if not isinstance(params, dict):
            raise ValueError("cdp params must be an object.")
        session = context.new_cdp_session(page)
        result = session.send(method, params)
        try:
            session.detach()
        except Exception:
            pass
        return {"ok": True, "method": method, "result": result}

    def storage(context, page, payload):
        kind = str(payload.get("kind") or payload.get("storage") or "local").lower()
        op = str(payload.get("op") or payload.get("operation") or "get").lower()
        key = payload.get("key")
        value = payload.get("value")
        if kind == "cookies":
            if op in {"get", "list"}:
                cookies = context.cookies()
                if not payload.get("includeValues"):
                    cookies = [dict(cookie, value="[REDACTED]") for cookie in cookies]
                return {"ok": True, "cookies": cookies, "valuesRedacted": not bool(payload.get("includeValues"))}
            if op in {"set", "add"}:
                cookies = value if isinstance(value, list) else [value]
                context.add_cookies(cookies)
                return post(page, payload, {"cookiesSet": len(cookies)}, context)
            if op in {"delete", "remove", "clear"}:
                context.clear_cookies()
                return post(page, payload, {"cookiesCleared": True}, context)
            raise ValueError("cookies supports get/list, set/add, or clear/delete.")
        js_storage = "sessionStorage" if kind.startswith("session") else "localStorage"
        if op in {"get", "list"}:
            data = page.evaluate(f"() => {{ const out={{}}; for(let i=0;i<{js_storage}.length;i++){{const k={js_storage}.key(i); out[k]={js_storage}.getItem(k);}} return out; }}")
            return {"ok": True, "storage": kind, "items": data}
        if op in {"set", "add"}:
            page.evaluate(f"([key, value]) => {js_storage}.setItem(key, value)", [str(key), str(value)])
            return post(page, payload, {"storageSet": {"kind": kind, "key": key}}, context)
        if op in {"delete", "remove"}:
            page.evaluate(f"(key) => {js_storage}.removeItem(key)", str(key))
            return post(page, payload, {"storageDeleted": {"kind": kind, "key": key}}, context)
        if op == "clear":
            page.evaluate(f"() => {js_storage}.clear()")
            return post(page, payload, {"storageCleared": kind}, context)
        raise ValueError("storage op must be get/list, set/add, delete/remove, or clear.")

    def console_logs(page, payload):
        install_page_hooks(page)
        logs = page.evaluate("() => window.__smartiConsoleHistory || []")
        limit = to_int(payload.get("limit", 100), 100)
        return {"ok": True, "logs": logs[-limit:]}

    def page_errors(page, payload):
        install_page_hooks(page)
        logs = page.evaluate("() => window.__smartiErrors || []")
        limit = to_int(payload.get("limit", 100), 100)
        return {"ok": True, "errors": logs[-limit:]}

    def capture_cdp_requests(context, page, payload):
        capture_ms = to_int(payload.get("captureMs", payload.get("capture_ms", 0)), 0)
        reload_page = want_true(payload, "reload", "refresh")
        live = want_true(payload, "live", "capture")
        if context is None or (capture_ms <= 0 and not reload_page and not live):
            return []
        capture_ms = max(250, min(capture_ms or 1200, timeout_ms(payload)))
        include_body = bool(payload.get("includeBody", payload.get("include_body", payload.get("responseBody", payload.get("response_body", False)))))
        body_chars = to_int(payload.get("maxBodyChars", payload.get("max_body_chars", payload.get("bodyChars", payload.get("body_chars", 2000)))), 2000)
        session = context.new_cdp_session(page)
        requests = {}
        order = []

        def ensure_item(request_id):
            item = requests.setdefault(request_id, {"requestId": request_id})
            if request_id not in order:
                order.append(request_id)
            return item

        def on_request(event):
            request_id = str(event.get("requestId") or "")
            request = event.get("request") or {}
            item = ensure_item(request_id)
            item.update({
                "url": request.get("url", ""),
                "method": request.get("method", ""),
                "type": event.get("type", ""),
                "timestamp": event.get("timestamp"),
                "wallTime": event.get("wallTime"),
                "initiator": event.get("initiator", {}).get("type", ""),
            })
            if include_body and request.get("postData"):
                item["requestBodyPreview"] = compact(request.get("postData"), body_chars)

        def on_response(event):
            request_id = str(event.get("requestId") or "")
            response = event.get("response") or {}
            item = ensure_item(request_id)
            item.update({
                "url": response.get("url", item.get("url", "")),
                "status": response.get("status"),
                "statusText": response.get("statusText", ""),
                "mimeType": response.get("mimeType", ""),
                "fromDiskCache": response.get("fromDiskCache", False),
                "fromServiceWorker": response.get("fromServiceWorker", False),
                "encodedDataLength": response.get("encodedDataLength", 0),
                "responseHeaders": response.get("headers", {}),
            })

        def on_finished(event):
            request_id = str(event.get("requestId") or "")
            item = ensure_item(request_id)
            item["finished"] = True
            item["encodedDataLength"] = event.get("encodedDataLength", item.get("encodedDataLength", 0))

        def on_failed(event):
            request_id = str(event.get("requestId") or "")
            item = ensure_item(request_id)
            item["failed"] = True
            item["errorText"] = event.get("errorText", "")

        try:
            session.on("Network.requestWillBeSent", on_request)
            session.on("Network.responseReceived", on_response)
            session.on("Network.loadingFinished", on_finished)
            session.on("Network.loadingFailed", on_failed)
            session.send("Network.enable", {})
            if reload_page:
                page.reload(wait_until=payload.get("waitUntil") or payload.get("wait_until") or "domcontentloaded", timeout=timeout_ms(payload))
            page.wait_for_timeout(capture_ms)
            if include_body:
                for request_id in order:
                    item = requests.get(request_id) or {}
                    mime = str(item.get("mimeType") or "")
                    if not item.get("finished") or not re.search(r"json|text|html|xml|javascript|x-www-form-urlencoded", mime, re.I):
                        continue
                    try:
                        body = session.send("Network.getResponseBody", {"requestId": request_id})
                        text = body.get("body", "")
                        if body.get("base64Encoded"):
                            item["responseBodyBase64"] = True
                            item["responseBodyPreview"] = compact(text, body_chars)
                        else:
                            item["responseBodyPreview"] = compact(text, body_chars)
                    except Exception as exc:
                        item["responseBodyError"] = compact(str(exc), 220)
            return [requests[request_id] for request_id in order][-to_int(payload.get("limit", 120), 120):]
        finally:
            try:
                session.detach()
            except Exception:
                pass

    def request_log(page, payload, context=None):
        install_page_hooks(page)
        limit = to_int(payload.get("limit", 120), 120)
        include_body = bool(payload.get("includeBody", payload.get("include_body", payload.get("responseBody", payload.get("response_body", False)))))
        body_chars = to_int(payload.get("maxBodyChars", payload.get("max_body_chars", payload.get("bodyChars", payload.get("body_chars", 2000)))), 2000)
        records = page.evaluate("() => window.__smartiRequests || []")[-limit:]
        clean_records = []
        for item in records:
            copy = dict(item)
            for key in ("requestBodyPreview", "responseBodyPreview"):
                if not include_body:
                    copy.pop(key, None)
                elif copy.get(key):
                    copy[key] = compact(copy.get(key), body_chars)
            clean_records.append(copy)
        resources = page.evaluate(
            """() => performance.getEntriesByType('resource').slice(-300).map(e => ({
              name: e.name, initiatorType: e.initiatorType, startTime: Math.round(e.startTime),
              duration: Math.round(e.duration), transferSize: e.transferSize || 0,
              encodedBodySize: e.encodedBodySize || 0, decodedBodySize: e.decodedBodySize || 0
            }))"""
        )
        nav = page.evaluate("() => performance.getEntriesByType('navigation').map(e => ({name:e.name, type:e.type, duration:Math.round(e.duration), domContentLoadedEventEnd:Math.round(e.domContentLoadedEventEnd), loadEventEnd:Math.round(e.loadEventEnd)}))")
        cdp_records = capture_cdp_requests(context, page, payload)
        return {"ok": True, "navigation": nav, "requests": clean_records, "cdpRequests": cdp_records, "resources": resources}

    def network(page, payload, context=None):
        return request_log(page, dict(payload, includeBody=False), context)

    def record_cdp_trace(context, page, payload):
        if context is None:
            return {"ok": False, "error": "CDP trace requires a browser context."}
        path = output_path(dict(payload, titleHint=page.title() or "browser_trace"), "json")
        capture_ms = max(250, min(to_int(payload.get("captureMs", payload.get("capture_ms", payload.get("timeMs", payload.get("time_ms", 1200)))), 1200), timeout_ms(payload)))
        categories = str(payload.get("traceCategories") or payload.get("trace_categories") or "devtools.timeline,v8.execute,blink.user_timing,loading")
        events = []
        done = {"complete": False}
        session = context.new_cdp_session(page)

        def on_data(event):
            events.extend(event.get("value") or [])

        def on_complete(_event):
            done["complete"] = True

        try:
            session.on("Tracing.dataCollected", on_data)
            session.on("Tracing.tracingComplete", on_complete)
            session.send("Tracing.start", {"categories": categories, "transferMode": "ReportEvents"})
            if want_true(payload, "reload", "refresh"):
                page.reload(wait_until=payload.get("waitUntil") or payload.get("wait_until") or "domcontentloaded", timeout=timeout_ms(payload))
            page.wait_for_timeout(capture_ms)
            session.send("Tracing.end")
            deadline = time.time() + min(5, timeout_ms(payload) / 1000)
            while not done.get("complete") and time.time() < deadline:
                page.wait_for_timeout(100)
            with open(path, "w", encoding="utf-8") as fp:
                json.dump({"traceEvents": events, "metadata": {"url": page.url, "title": page.title(), "captureMs": capture_ms, "categories": categories}}, fp, ensure_ascii=False)
            return {"ok": True, "path": path, "events": len(events), "captureMs": capture_ms, "categories": categories}
        finally:
            try:
                session.detach()
            except Exception:
                pass

    def trace(context, page, payload):
        limit = to_int(payload.get("limit", 80), 80)
        result = {
            "ok": True,
            "profile": payload.get("profile") or "smarti",
            "currentTargetId": page_ref(context, page),
            "currentTabId": tab_id_for(page_ref(context, page)),
            "page": {"url": page.url, "title": page.title(), "label": get_tab_label(page)},
            "tabs": tabs(context, page),
            "console": console_logs(page, {"limit": min(limit, 80)}).get("logs", []),
            "errors": page_errors(page, {"limit": min(limit, 80)}).get("errors", []),
            "network": request_log(page, {"limit": min(limit, 80), "includeBody": False}, context),
        }
        if want_true(payload, "record", "save") or payload.get("path") or payload.get("captureMs") or payload.get("capture_ms"):
            result["devtoolsTrace"] = record_cdp_trace(context, page, payload)
        return result

    def build_annotations(state, payload, mode, clip_box=None, full_page=False):
        annotations = []
        scroll = state.get("scroll") or {}
        scroll_x = float(scroll.get("x") or 0)
        scroll_y = float(scroll.get("y") or 0)
        clip = clip_box or (payload.get("clip") if isinstance(payload.get("clip"), dict) else None)
        for item in (state.get("elements") or [])[:160]:
            rect = item.get("rect") or {}
            x = float(rect.get("x") or 0)
            y = float(rect.get("y") or 0)
            w = float(rect.get("width") or 0)
            h = float(rect.get("height") or 0)
            if w <= 0 or h <= 0:
                continue
            if clip:
                cx, cy = float(clip.get("x") or 0), float(clip.get("y") or 0)
                cw, ch = float(clip.get("width") or 0), float(clip.get("height") or 0)
                if x + w < cx or x > cx + cw or y + h < cy or y > cy + ch:
                    continue
                box = {
                    "x": round(max(0, x - cx)),
                    "y": round(max(0, y - cy)),
                    "width": round(min(w, max(0, cx + cw - x), max(0, x + w - cx))),
                    "height": round(min(h, max(0, cy + ch - y), max(0, y + h - cy))),
                }
                coordinate_space = "clip-css-pixels"
            elif full_page:
                box = {"x": round(x + scroll_x), "y": round(y + scroll_y), "width": round(w), "height": round(h)}
                coordinate_space = "document-css-pixels"
            else:
                box = {"x": round(x), "y": round(y), "width": round(w), "height": round(h)}
                coordinate_space = "viewport-css-pixels"
            if box["width"] <= 0 or box["height"] <= 0:
                continue
            number = len(annotations) + 1
            annotations.append({
                "number": number,
                "ref": item.get("ref") or "",
                "role": item.get("role") or item.get("tag") or "",
                "name": compact(item.get("text") or item.get("ariaLabel") or item.get("placeholder") or item.get("name") or "", 160),
                "box": box,
                "coordinateSpace": coordinate_space,
                "rect": rect,
            })
        return annotations

    def screenshot(page, payload, context=None):
        state = snapshot(page, payload, context)
        path = output_path(dict(payload, titleHint=page.title() or "browser"), "png")
        labels = bool(payload.get("labels", payload.get("annotate", False)))
        full_page = bool(payload.get("fullPage", payload.get("full_page", False)))
        clip_box = payload.get("clip") if isinstance(payload.get("clip"), dict) else None
        loc = None
        if payload.get("ref") or payload.get("selector") or payload.get("role") or payload.get("textSelector"):
            loc = locator(page, payload)
            loc.scroll_into_view_if_needed(timeout=timeout_ms(payload))
            if labels:
                clip_box = loc.bounding_box(timeout=timeout_ms(payload))
                if not clip_box:
                    raise ValueError("Target element has no visible bounding box for labeled element screenshot.")
        mode = "page"
        if clip_box:
            mode = "element" if loc is not None else "clip"
        annotations = build_annotations(state, payload, mode, clip_box=clip_box, full_page=full_page) if labels else []
        if labels:
            page.evaluate(OVERLAY_JS, {"elements": annotations or state.get("elements", []), "clearOnly": False, "fullPage": full_page})
            page.wait_for_timeout(120)
        try:
            if clip_box:
                clip = clip_box
                page.screenshot(path=path, clip={
                    "x": float(clip.get("x", 0)),
                    "y": float(clip.get("y", 0)),
                    "width": float(clip.get("width", 1)),
                    "height": float(clip.get("height", 1)),
                }, timeout=timeout_ms(payload))
            elif loc is not None:
                loc.screenshot(path=path, timeout=timeout_ms(payload))
                mode = "element"
            else:
                page.screenshot(path=path, full_page=full_page, timeout=timeout_ms(payload))
                mode = "page"
        finally:
            if labels:
                try:
                    page.evaluate(OVERLAY_JS, {"elements": [], "clearOnly": True, "fullPage": False})
                except Exception:
                    pass
        return {"ok": True, "path": path, "mode": mode, "labels": labels, "labelsCount": len(annotations), "annotations": annotations, "page": state}

    def pdf(page, payload):
        path = output_path(dict(payload, titleHint=page.title() or "browser"), "pdf")
        page.pdf(path=path, print_background=bool(payload.get("printBackground", True)), landscape=bool(payload.get("landscape", False)), timeout=timeout_ms(payload))
        return {"ok": True, "path": path}

    def scroll(page, payload, context=None):
        if payload.get("ref") or payload.get("selector") or payload.get("role") or payload.get("textSelector"):
            loc = locator(page, payload)
            loc.scroll_into_view_if_needed(timeout=timeout_ms(payload))
            return post(page, payload, {"scrolledTo": payload.get("ref") or payload.get("selector") or "locator"}, context)
        dx = float(payload.get("deltaX", payload.get("x", 0)) or 0)
        dy = float(payload.get("deltaY", payload.get("y", 800)) or 800)
        page.mouse.wheel(dx, dy)
        return post(page, payload, {"scrolledBy": {"x": dx, "y": dy}}, context)

    def resize(page, payload, context=None):
        width = to_int(payload.get("width"), 1280)
        height = to_int(payload.get("height"), 900)
        page.set_viewport_size({"width": width, "height": height})
        return post(page, payload, {"viewport": {"width": width, "height": height}}, context)

    def close_tab(context, page):
        ref = page_ref(context, page)
        page.close()
        current = context.pages[-1] if context.pages else context.new_page()
        return {"ok": True, "closedTargetId": ref, "tabs": tabs(context, current)}

    def focus_tab(context, page, payload):
        page.bring_to_front()
        if payload.get("label") is not None:
            set_tab_label(page, payload.get("label"))
        return {"ok": True, "focusedTargetId": page_ref(context, page), "focusedTabId": tab_id_for(page_ref(context, page)), "tabs": tabs(context, page)}

    def cleanup_tabs(context, current, payload):
        if payload.get("label") is not None:
            set_tab_label(current, payload.get("label"))
        if payload.get("closeOthers") or payload.get("close_others") or payload.get("cleanup"):
            for page in list(context.pages):
                if page != current:
                    try:
                        page.close()
                    except Exception:
                        pass
        return {"ok": True, "tabs": tabs(context, current), "currentTargetId": page_ref(context, current), "currentTabId": tab_id_for(page_ref(context, current))}

    def dialog(page, payload):
        return {"ok": False, "error": "Use accept/promptText/expectDialog on the action that triggers the dialog; Playwright handles dialogs during that action."}

    def main():
        payload = json.loads(sys.stdin.read() or "{}")
        action = str(payload.get("action") or "snapshot").strip()
        normalized = action.lower().replace("-", "_")
        if normalized == "act":
            request = dict(payload.get("request") or {})
            for key, value in payload.items():
                request.setdefault(key, value)
            payload = request
            normalized = str(request.get("kind") or request.get("action") or "").strip().lower().replace("-", "_")
        pw = browser = context = None
        try:
            pw, browser, context = connect(payload)
            page = select_page(context, payload)
            install_page_hooks(page)
            if normalized in {"status", "doctor", "start"}:
                result = {"ok": True, "ready": True, "profile": payload.get("profile") or "smarti", "tabs": tabs(context, page), "currentTargetId": page_ref(context, page), "currentTabId": tab_id_for(page_ref(context, page))}
            elif normalized == "tabs":
                result = cleanup_tabs(context, page, payload)
            elif normalized == "focus":
                result = focus_tab(context, page, payload)
            elif normalized == "open":
                result = navigate(context, page, payload, new_tab=bool(payload.get("newTab", True)))
            elif normalized == "navigate":
                result = navigate(context, page, payload, new_tab=bool(payload.get("newTab", False)))
            elif normalized == "snapshot":
                result = {"ok": True, "targetId": page_ref(context, page), "tabId": tab_id_for(page_ref(context, page)), "page": snapshot(page, payload, context)}
            elif normalized == "screenshot":
                result = screenshot(page, payload, context)
            elif normalized == "pdf":
                result = pdf(page, payload)
            elif normalized == "console":
                result = console_logs(page, payload)
            elif normalized == "errors":
                result = page_errors(page, payload)
            elif normalized in {"requests", "request_log"}:
                result = request_log(page, payload, context)
            elif normalized == "network":
                result = network(page, payload, context)
            elif normalized == "trace":
                result = trace(context, page, payload)
            elif normalized == "storage":
                result = storage(context, page, payload)
            elif normalized == "cookies":
                result = storage(context, page, dict(payload, kind="cookies"))
            elif normalized in {"click", "clickcoords", "click_coords"}:
                result = click(page, payload, context)
            elif normalized == "download":
                result = click(page, dict(payload, expectDownload=True), context)
            elif normalized == "hover":
                loc = locator(page, payload)
                loc.hover(timeout=timeout_ms(payload))
                result = post(page, payload, {"hovered": payload.get("ref") or payload.get("selector") or "locator"}, context)
            elif normalized == "type":
                result = fill(page, payload, typing=True, context=context)
            elif normalized == "fill":
                result = fill(page, payload, typing=False, context=context)
            elif normalized == "press":
                result = press(page, payload, context)
            elif normalized == "select":
                result = select_value(page, payload, context)
            elif normalized == "upload":
                result = upload(page, payload, context)
            elif normalized == "wait":
                result = wait(page, payload, context)
            elif normalized == "evaluate":
                result = evaluate(page, payload, context)
            elif normalized == "cdp":
                result = cdp(context, page, payload)
            elif normalized == "dialog":
                result = dialog(page, payload)
            elif normalized in {"scroll", "scrollintoview", "scroll_into_view"}:
                result = scroll(page, payload, context)
            elif normalized == "resize":
                result = resize(page, payload, context)
            elif normalized in {"close", "close_tab"}:
                result = close_tab(context, page)
            else:
                raise ValueError(f"Unsupported browser action: {action}")
            emit_result(result)
        except Exception as exc:
            emit_result({"ok": False, "error": str(exc), "action": action})
        finally:
            try:
                if pw is not None:
                    pw.stop()
            except Exception:
                pass

    if __name__ == "__main__":
        main()
    '''
)
