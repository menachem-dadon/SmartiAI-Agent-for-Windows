"""Structured Playwright/CDP control plane for Smarti's persistent browser."""
import json
import os
import subprocess
import tempfile
import textwrap
import time

from .common import SMARTI_BROWSER_DEBUG_PORT, WIN_CREATE_NO_WINDOW


UNTRUSTED_BROWSER_PREFIX = "[UNTRUSTED_BROWSER_CONTENT]\n"


class SmartiBrowserController:
    """Runs high-level browser actions against Smarti Chrome through Playwright/CDP."""

    def __init__(self, core):
        self.core = core

    def run(self, payload):
        if not self.core.settings.get("enable_browser_automation", False):
            return "ERROR: Browser automation is disabled by the user in settings."
        args = dict(payload or {})
        action = str(args.get("action") or "snapshot").strip().lower()
        if action == "run" or "code" in args:
            return (
                "ERROR: Raw Python browser code was removed. "
                "Use structured browser actions, action=evaluate for JavaScript, or action=cdp for Chrome DevTools Protocol."
            )
        if action in {"close_browser", "stop", "close_all"}:
            return self.core._close_automation_browser()

        initial_url = "about:blank"
        if action == "navigate":
            initial_url = str(args.get("url") or args.get("targetUrl") or args.get("query_or_url") or "about:blank")
        ok, err = self.core._ensure_automation_browser(initial_url)
        if not ok:
            return err
        return self._run_helper(args)

    def _json(self, payload):
        return self.core._truncate_tool_output(
            UNTRUSTED_BROWSER_PREFIX + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        )

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
        }

    def _output_dir(self):
        try:
            base = self.core._sandbox_root() if self.core._sandbox_enabled() else self.core._default_output_dir()
        except Exception:
            base = os.getcwd()
        os.makedirs(base, exist_ok=True)
        return base

    def _run_helper(self, payload):
        timeout = self.core._timeout("tool_timeout_seconds", 120)
        helper_payload = dict(payload or {})
        helper_payload.setdefault("action", "snapshot")
        helper_payload.setdefault("snapshot", self._snapshot_defaults())
        helper_payload.setdefault("outputDir", self._output_dir())
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
            try:
                parsed = json.loads(stdout)
            except Exception:
                detail = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                return self.core._truncate_tool_output("ERROR: Browser action returned non-JSON output.\n" + detail)
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

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Missing Playwright. Install requirements.txt: {exc}"}, ensure_ascii=False))
        sys.exit(1)

    MARK = "data-smarti-ref"

    INSTALL_JS = r"""
    (() => {
      if (window.__smartiConsoleInstalled) return true;
      window.__smartiConsoleInstalled = true;
      window.__smartiConsoleHistory = window.__smartiConsoleHistory || [];
      for (const level of ['log', 'info', 'warn', 'error', 'debug']) {
        const original = console[level] ? console[level].bind(console) : console.log.bind(console);
        console[level] = (...args) => {
          try {
            window.__smartiConsoleHistory.push({
              level,
              ts: Date.now(),
              text: args.map(v => {
                try { return typeof v === 'string' ? v : JSON.stringify(v); }
                catch (e) { return String(v); }
              }).join(' ')
            });
            if (window.__smartiConsoleHistory.length > 500) window.__smartiConsoleHistory.shift();
          } catch (e) {}
          return original(...args);
        };
      }
      window.addEventListener('error', event => {
        try {
          window.__smartiConsoleHistory.push({level: 'pageerror', ts: Date.now(), text: event.message || String(event.error || '')});
        } catch (e) {}
      });
      window.addEventListener('unhandledrejection', event => {
        try {
          window.__smartiConsoleHistory.push({level: 'unhandledrejection', ts: Date.now(), text: String(event.reason || '')});
        } catch (e) {}
      });
      return true;
    })();
    """

    COLLECT_JS = r"""
    (options) => {
      options = options || {};
      const limit = options.limit || 120;
      const bodyChars = options.bodyChars || 8000;
      const htmlLimit = options.htmlChars || 600;
      const includeUrls = options.includeUrls !== false;
      const includeHidden = !!options.includeHidden;
      const selector = [
        'a','button','input','textarea','select','option','summary','label',
        '[role]','[aria-label]','[tabindex]','[contenteditable="true"]',
        'iframe','video','audio','details','dialog'
      ].join(',');
      if (!window.__smartiRefSeq) window.__smartiRefSeq = 1;
      function textOf(el) {
        return (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') ||
          el.getAttribute('placeholder') || el.alt || '').replace(/\s+/g, ' ').trim();
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
      function cssEscape(value) {
        if (window.CSS && CSS.escape) return CSS.escape(value);
        return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
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
      const seen = new Set();
      const nodes = Array.from(document.querySelectorAll(selector)).filter(el => {
        if (seen.has(el)) return false;
        seen.add(el);
        return visible(el);
      }).slice(0, limit);
      const elements = nodes.map((el, index) => {
        let ref = el.getAttribute('data-smarti-ref');
        if (!ref) {
          ref = 'e' + (window.__smartiRefSeq++);
          try { el.setAttribute('data-smarti-ref', ref); } catch (e) {}
        }
        const rect = el.getBoundingClientRect();
        const item = {
          ref, index,
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute('role') || '',
          name: el.getAttribute('name') || '',
          id: el.id || '',
          type: el.getAttribute('type') || '',
          selector: selectorFor(el),
          text: textOf(el).slice(0, 700),
          value: (el.value || '').slice(0, 700),
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
        return item;
      });
      const bodyText = document.body ? document.body.innerText || '' : '';
      return {
        url: location.href,
        title: document.title,
        readyState: document.readyState,
        viewport: {width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio || 1},
        scroll: {x: Math.round(window.scrollX), y: Math.round(window.scrollY), maxY: Math.max(0, document.documentElement.scrollHeight - window.innerHeight)},
        bodyText: bodyText.replace(/\s+/g, ' ').trim().slice(0, bodyChars),
        elements
      };
    }
    """

    OVERLAY_JS = r"""
    ({elements, clearOnly}) => {
      for (const old of Array.from(document.querySelectorAll('[data-smarti-overlay="true"]'))) old.remove();
      if (clearOnly) return true;
      const root = document.createElement('div');
      root.setAttribute('data-smarti-overlay', 'true');
      root.style.cssText = 'position:fixed;left:0;top:0;right:0;bottom:0;z-index:2147483647;pointer-events:none;font:12px Arial,sans-serif;';
      for (const item of (elements || []).slice(0, 140)) {
        const r = item.rect || {};
        const box = document.createElement('div');
        box.style.cssText = `position:absolute;left:${Math.max(0, r.x || 0)}px;top:${Math.max(0, r.y || 0)}px;width:${Math.max(1, r.width || 1)}px;height:${Math.max(1, r.height || 1)}px;border:2px solid #ff2d55;background:rgba(255,45,85,.08);box-sizing:border-box;`;
        const badge = document.createElement('div');
        badge.textContent = item.ref || '';
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
        return max(1000, to_int(payload.get("timeoutMs") or payload.get("timeout") or 30000, 30000))

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

    def connect(payload):
        pw = sync_playwright().start()
        endpoint = f"http://127.0.0.1:{payload.get('debugPort') or 49223}"
        browser = pw.chromium.connect_over_cdp(endpoint, timeout=timeout_ms(payload))
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        try:
            context.add_init_script(INSTALL_JS)
        except Exception:
            pass
        if not context.pages:
            context.new_page()
        return pw, browser, context

    def page_ref(context, page):
        pages = context.pages
        try:
            return "p" + str(pages.index(page))
        except Exception:
            return "p0"

    def tabs(context, current=None):
        result = []
        for index, page in enumerate(context.pages):
            try:
                result.append({
                    "index": index,
                    "targetId": f"p{index}",
                    "tabId": f"p{index}",
                    "current": page == current,
                    "title": page.title(),
                    "url": page.url,
                })
            except Exception as exc:
                result.append({"index": index, "targetId": f"p{index}", "error": str(exc)})
        return result

    def select_page(context, payload):
        target = str(payload.get("targetId") or payload.get("tabId") or payload.get("target") or "").strip()
        pages = context.pages
        if target:
            lowered = target.lower()
            if lowered.startswith("p") and lowered[1:].isdigit():
                idx = int(lowered[1:])
                if 0 <= idx < len(pages):
                    return pages[idx]
            for page in pages:
                try:
                    if lowered in (page.url or "").lower() or lowered in (page.title() or "").lower():
                        return page
                except Exception:
                    pass
            raise ValueError(f"Target tab not found: {target}")
        return pages[-1] if pages else context.new_page()

    def install_page_hooks(page):
        try:
            page.evaluate(INSTALL_JS)
        except Exception:
            pass

    def snapshot(page, payload):
        install_page_hooks(page)
        snap = dict(payload.get("snapshot") or {})
        limit = to_int(payload.get("limit", payload.get("max_elements", snap.get("elementLimit", 120))), 120)
        body_chars = to_int(payload.get("body_chars", payload.get("bodyChars", snap.get("bodyChars", 8000))), 8000)
        html_chars = to_int(payload.get("html_chars", payload.get("htmlChars", snap.get("htmlChars", 600))), 600)
        state = page.evaluate(COLLECT_JS, {
            "limit": limit,
            "bodyChars": body_chars,
            "htmlChars": html_chars,
            "includeUrls": bool(payload.get("urls", payload.get("includeUrls", True))),
            "includeHidden": bool(payload.get("includeHidden", False)),
        })
        try:
            body_locator = page.locator("body")
            aria_snapshot = getattr(body_locator, "aria_snapshot", None)
            if callable(aria_snapshot):
                state["ariaSnapshot"] = aria_snapshot(timeout=min(3000, timeout_ms(payload)))
        except Exception:
            pass
        return state or {}

    def locator(page, payload):
        ref = str(payload.get("ref") or "").strip()
        selector = str(payload.get("selector") or "").strip()
        role = str(payload.get("role") or "").strip()
        name = payload.get("name")
        text = payload.get("textSelector")
        if ref:
            return page.locator(f'[{MARK}="{ref}"]').first
        if selector:
            return page.locator(selector).first
        if role:
            opts = {"name": name} if name not in (None, "") else {}
            return page.get_by_role(role, **opts).first
        if text:
            return page.get_by_text(str(text)).first
        raise ValueError("Action requires ref, selector, role+name, or textSelector.")

    def post(page, payload, result=None):
        if payload.get("noSnapshot"):
            return {"ok": True, "result": result}
        return {"ok": True, "result": result, "page": snapshot(page, payload)}

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
        url = payload.get("url") or payload.get("targetUrl") or payload.get("query_or_url")
        if not url:
            raise ValueError("navigate/open requires url.")
        if new_tab:
            page = context.new_page()
        page.goto(str(url), wait_until=payload.get("waitUntil") or "domcontentloaded", timeout=timeout_ms(payload))
        return post(page, payload, {"targetId": page_ref(context, page), "url": page.url, "title": page.title()})

    def click(page, payload):
        if payload.get("x") is not None and payload.get("y") is not None and not (payload.get("ref") or payload.get("selector")):
            x, y = float(payload.get("x")), float(payload.get("y"))
            result, dialog = with_dialog(page, payload, lambda: page.mouse.click(x, y))
            return post(page, payload, {"clicked": "coords", "x": x, "y": y, "dialog": dialog})
        loc = locator(page, payload)
        download_info = None
        if payload.get("expectDownload"):
            with page.expect_download(timeout=timeout_ms(payload)) as download_wait:
                _, dialog = with_dialog(page, payload, lambda: loc.click(timeout=timeout_ms(payload)))
            download = download_wait.value
            path = payload.get("downloadPath")
            if not path:
                output_dir = payload.get("outputDir") or os.getcwd()
                os.makedirs(output_dir, exist_ok=True)
                path = os.path.join(output_dir, sanitize_name(download.suggested_filename, "download"))
            download.save_as(path)
            download_info = {"path": path, "suggestedFilename": download.suggested_filename}
        else:
            _, dialog = with_dialog(page, payload, lambda: loc.click(timeout=timeout_ms(payload)))
        return post(page, payload, {"clicked": payload.get("ref") or payload.get("selector") or "locator", "dialog": dialog, "download": download_info})

    def fill(page, payload, typing=False):
        loc = locator(page, payload)
        text = str(payload.get("text", payload.get("value", "")))
        loc.scroll_into_view_if_needed(timeout=timeout_ms(payload))
        loc.focus(timeout=timeout_ms(payload))
        if typing and payload.get("clear") is False:
            try:
                loc.type(text, delay=max(0, int(float(payload.get("delay", 0.02)) * 1000)), timeout=timeout_ms(payload))
            except Exception:
                page.keyboard.insert_text(text)
        elif typing and payload.get("slowly"):
            loc.fill("", timeout=timeout_ms(payload))
            try:
                loc.type(text, delay=max(0, int(float(payload.get("delay", 0.04)) * 1000)), timeout=timeout_ms(payload))
            except Exception:
                page.keyboard.insert_text(text)
        else:
            loc.fill(text, timeout=timeout_ms(payload))
        if payload.get("submit"):
            loc.press("Enter", timeout=timeout_ms(payload))
        return post(page, payload, {"typed": len(text), "target": payload.get("ref") or payload.get("selector")})

    def press(page, payload):
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
        return post(page, payload, {"pressed": [str(k) for k in keys]})

    def select_value(page, payload):
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
        return post(page, payload, {"selected": option})

    def upload(page, payload):
        loc = locator(page, payload)
        paths = payload.get("paths") or payload.get("files") or payload.get("path") or []
        if isinstance(paths, str):
            paths = [paths]
        paths = [os.path.abspath(os.path.expanduser(str(path))) for path in paths if str(path).strip()]
        missing = [path for path in paths if not os.path.exists(path)]
        if missing:
            raise FileNotFoundError("Missing upload files: " + ", ".join(missing))
        loc.set_input_files(paths, timeout=timeout_ms(payload))
        return post(page, payload, {"uploaded": paths})

    def wait(page, payload):
        if payload.get("timeMs") or payload.get("ms"):
            ms = to_int(payload.get("timeMs") or payload.get("ms"), 0)
            page.wait_for_timeout(ms)
            return post(page, payload, {"waitedMs": ms})
        if payload.get("selector"):
            page.wait_for_selector(str(payload.get("selector")), timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "selector", "selector": payload.get("selector")})
        if payload.get("text"):
            page.get_by_text(str(payload.get("text"))).first.wait_for(timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "text", "text": payload.get("text")})
        if payload.get("urlContains") or payload.get("url"):
            needle = str(payload.get("urlContains") or payload.get("url"))
            page.wait_for_url(lambda url: needle in url, timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "url", "url": needle})
        if payload.get("function") or payload.get("script"):
            page.wait_for_function(str(payload.get("function") or payload.get("script")), timeout=timeout_ms(payload))
            return post(page, payload, {"matched": "function"})
        page.wait_for_load_state(payload.get("state") or "domcontentloaded", timeout=timeout_ms(payload))
        return post(page, payload, {"matched": "loadState"})

    def evaluate(page, payload):
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
        return post(page, payload, {"value": result})

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
                return {"ok": True, "cookies": context.cookies()}
            if op in {"set", "add"}:
                cookies = value if isinstance(value, list) else [value]
                context.add_cookies(cookies)
                return post(page, payload, {"cookiesSet": len(cookies)})
            if op in {"delete", "remove", "clear"}:
                context.clear_cookies()
                return post(page, payload, {"cookiesCleared": True})
            raise ValueError("cookies supports get/list, set/add, or clear/delete.")
        js_storage = "sessionStorage" if kind.startswith("session") else "localStorage"
        if op in {"get", "list"}:
            data = page.evaluate(f"() => {{ const out={{}}; for(let i=0;i<{js_storage}.length;i++){{const k={js_storage}.key(i); out[k]={js_storage}.getItem(k);}} return out; }}")
            return {"ok": True, "storage": kind, "items": data}
        if op in {"set", "add"}:
            page.evaluate(f"([key, value]) => {js_storage}.setItem(key, value)", [str(key), str(value)])
            return post(page, payload, {"storageSet": {"kind": kind, "key": key}})
        if op in {"delete", "remove"}:
            page.evaluate(f"(key) => {js_storage}.removeItem(key)", str(key))
            return post(page, payload, {"storageDeleted": {"kind": kind, "key": key}})
        if op == "clear":
            page.evaluate(f"() => {js_storage}.clear()")
            return post(page, payload, {"storageCleared": kind})
        raise ValueError("storage op must be get/list, set/add, delete/remove, or clear.")

    def console_logs(page, payload):
        install_page_hooks(page)
        logs = page.evaluate("() => window.__smartiConsoleHistory || []")
        limit = to_int(payload.get("limit", 100), 100)
        return {"ok": True, "logs": logs[-limit:]}

    def network(page, payload):
        entries = page.evaluate(
            """() => performance.getEntriesByType('resource').slice(-300).map(e => ({
              name: e.name, initiatorType: e.initiatorType, startTime: Math.round(e.startTime),
              duration: Math.round(e.duration), transferSize: e.transferSize || 0,
              encodedBodySize: e.encodedBodySize || 0, decodedBodySize: e.decodedBodySize || 0
            }))"""
        )
        nav = page.evaluate("() => performance.getEntriesByType('navigation').map(e => ({name:e.name, type:e.type, duration:Math.round(e.duration), domContentLoadedEventEnd:Math.round(e.domContentLoadedEventEnd), loadEventEnd:Math.round(e.loadEventEnd)}))")
        return {"ok": True, "navigation": nav, "resources": entries}

    def screenshot(page, payload):
        state = snapshot(page, payload)
        path = output_path(dict(payload, titleHint=page.title() or "browser"), "png")
        labels = bool(payload.get("labels", payload.get("annotate", False)))
        if labels:
            page.evaluate(OVERLAY_JS, {"elements": state.get("elements", []), "clearOnly": False})
            page.wait_for_timeout(120)
        try:
            page.screenshot(path=path, full_page=bool(payload.get("fullPage", payload.get("full_page", False))), timeout=timeout_ms(payload))
        finally:
            if labels:
                try:
                    page.evaluate(OVERLAY_JS, {"elements": [], "clearOnly": True})
                except Exception:
                    pass
        return {"ok": True, "path": path, "page": state}

    def pdf(page, payload):
        path = output_path(dict(payload, titleHint=page.title() or "browser"), "pdf")
        page.pdf(path=path, print_background=bool(payload.get("printBackground", True)), landscape=bool(payload.get("landscape", False)), timeout=timeout_ms(payload))
        return {"ok": True, "path": path}

    def scroll(page, payload):
        if payload.get("ref") or payload.get("selector") or payload.get("role") or payload.get("textSelector"):
            loc = locator(page, payload)
            loc.scroll_into_view_if_needed(timeout=timeout_ms(payload))
            return post(page, payload, {"scrolledTo": payload.get("ref") or payload.get("selector") or "locator"})
        dx = float(payload.get("deltaX", payload.get("x", 0)) or 0)
        dy = float(payload.get("deltaY", payload.get("y", 800)) or 800)
        page.mouse.wheel(dx, dy)
        return post(page, payload, {"scrolledBy": {"x": dx, "y": dy}})

    def resize(page, payload):
        width = to_int(payload.get("width"), 1280)
        height = to_int(payload.get("height"), 900)
        page.set_viewport_size({"width": width, "height": height})
        return post(page, payload, {"viewport": {"width": width, "height": height}})

    def close_tab(context, page):
        ref = page_ref(context, page)
        page.close()
        current = context.pages[-1] if context.pages else context.new_page()
        return {"ok": True, "closedTargetId": ref, "tabs": tabs(context, current)}

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
                result = {"ok": True, "ready": True, "tabs": tabs(context, page), "currentTargetId": page_ref(context, page)}
            elif normalized == "tabs":
                result = {"ok": True, "tabs": tabs(context, page), "currentTargetId": page_ref(context, page)}
            elif normalized == "open":
                result = navigate(context, page, payload, new_tab=bool(payload.get("newTab", True)))
            elif normalized == "navigate":
                result = navigate(context, page, payload, new_tab=bool(payload.get("newTab", False)))
            elif normalized == "snapshot":
                result = {"ok": True, "targetId": page_ref(context, page), "page": snapshot(page, payload)}
            elif normalized == "screenshot":
                result = screenshot(page, payload)
            elif normalized == "pdf":
                result = pdf(page, payload)
            elif normalized == "console":
                result = console_logs(page, payload)
            elif normalized == "network":
                result = network(page, payload)
            elif normalized == "storage":
                result = storage(context, page, payload)
            elif normalized == "cookies":
                result = storage(context, page, dict(payload, kind="cookies"))
            elif normalized in {"click", "clickcoords", "click_coords"}:
                result = click(page, payload)
            elif normalized == "hover":
                loc = locator(page, payload)
                loc.hover(timeout=timeout_ms(payload))
                result = post(page, payload, {"hovered": payload.get("ref") or payload.get("selector") or "locator"})
            elif normalized == "type":
                result = fill(page, payload, typing=True)
            elif normalized == "fill":
                result = fill(page, payload, typing=False)
            elif normalized == "press":
                result = press(page, payload)
            elif normalized == "select":
                result = select_value(page, payload)
            elif normalized == "upload":
                result = upload(page, payload)
            elif normalized == "wait":
                result = wait(page, payload)
            elif normalized == "evaluate":
                result = evaluate(page, payload)
            elif normalized == "cdp":
                result = cdp(context, page, payload)
            elif normalized == "dialog":
                result = dialog(page, payload)
            elif normalized in {"scroll", "scrollintoview", "scroll_into_view"}:
                result = scroll(page, payload)
            elif normalized == "resize":
                result = resize(page, payload)
            elif normalized in {"close", "close_tab"}:
                result = close_tab(context, page)
            else:
                raise ValueError(f"Unsupported browser action: {action}")
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc), "action": action}, ensure_ascii=False, default=str))
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
