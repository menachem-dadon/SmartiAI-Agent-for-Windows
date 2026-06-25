"""Structured control plane for Smarti's persistent automation browser."""
import json
import os
import subprocess
import tempfile
import textwrap
import time

from .common import SMARTI_BROWSER_DEBUG_PORT, WIN_CREATE_NO_WINDOW


UNTRUSTED_BROWSER_PREFIX = "[UNTRUSTED_BROWSER_CONTENT]\n"


class SmartiBrowserController:
    """Runs high-level browser actions against the existing Selenium/Chrome runtime."""

    def __init__(self, core):
        self.core = core

    def run(self, payload):
        if not self.core.settings.get("enable_browser_automation", False):
            return "ERROR: Browser automation is disabled by the user in settings."
        args = dict(payload or {})
        action = str(args.get("action") or "snapshot").strip().lower()
        if action == "run":
            code = str(args.get("code", "") or "")
            if not code.strip():
                return "ERROR: browser_automation action=run requires code."
            return self.core.run_browser_automation(code)
        if action in {"close_browser", "stop", "close_all"}:
            return self.core._close_automation_browser()
        if action in {"start", "doctor", "status", "tabs"}:
            ok, err = self.core._ensure_automation_browser(args.get("url") or "about:blank")
            if not ok:
                return err
        elif action in {"open", "navigate"}:
            url = args.get("url") or args.get("targetUrl") or args.get("query_or_url")
            if not url:
                return "ERROR: Browser action requires url."
            initial_url = "about:blank" if action == "open" else str(url)
            ok, err = self.core._ensure_automation_browser(initial_url)
            if not ok:
                return err
        else:
            ok, err = self.core._ensure_automation_browser()
            if not ok:
                return err

        if action in {"status", "doctor"}:
            return self._status(action)
        return self._run_helper(args)

    def _status(self, action):
        payload = {
            "ok": True,
            "action": action,
            "debugPort": SMARTI_BROWSER_DEBUG_PORT,
            "endpoint": self.core._automation_browser_endpoint(),
            "ready": self.core._automation_browser_is_ready(),
        }
        try:
            response = self.core._request_get(self.core._automation_browser_endpoint("/json/version"), timeout=2)
            payload["browser"] = response.json()
        except Exception as exc:
            payload["browserError"] = str(exc)
        tabs_result = self._run_helper({"action": "tabs"})
        try:
            payload["tabs"] = json.loads(self._strip_untrusted(tabs_result)).get("tabs", [])
        except Exception:
            payload["tabsText"] = tabs_result
        return self._json(payload)

    def _strip_untrusted(self, text):
        text = str(text or "")
        if text.startswith(UNTRUSTED_BROWSER_PREFIX):
            return text[len(UNTRUSTED_BROWSER_PREFIX):]
        return text

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
            "elementLimit": bounded("browser_snapshot_element_limit", 100, 20, 300),
            "bodyChars": bounded("browser_snapshot_body_chars", 6000, 1000, 20000),
            "htmlChars": bounded("browser_snapshot_html_chars", 600, 0, 2000),
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
        helper_payload.setdefault("timestamp", int(time.time()))

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
    import base64
    import json
    import os
    import re
    import sys
    import time

    sys.stdin = open(sys.stdin.fileno(), mode="r", encoding="utf-8", errors="replace", closefd=False)
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)
    sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)

    try:
        from selenium import webdriver
        from selenium.common.exceptions import NoAlertPresentException, NoSuchElementException, TimeoutException
        from selenium.webdriver import ActionChains
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import Select, WebDriverWait
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Missing required browser libraries: {exc}"}, ensure_ascii=False))
        sys.exit(1)

    MARK = "data-smarti-ref"

    def compact(value, limit=500):
        text = "" if value is None else str(value)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > limit:
            return text[:limit] + "..."
        return text

    def to_int(value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    def sanitize_name(value, default="browser_capture"):
        text = compact(value or default, 80)
        text = re.sub(r"[^\w.\-]+", "_", text, flags=re.UNICODE).strip("._-")
        return text or default

    def normalize_key(key):
        raw = str(key or "").strip()
        if not raw:
            return ""
        name = raw.upper().replace(" ", "_").replace("-", "_")
        mapping = {
            "ENTER": Keys.ENTER, "RETURN": Keys.RETURN, "TAB": Keys.TAB, "ESC": Keys.ESCAPE,
            "ESCAPE": Keys.ESCAPE, "BACKSPACE": Keys.BACKSPACE, "DELETE": Keys.DELETE,
            "ARROW_LEFT": Keys.ARROW_LEFT, "LEFT": Keys.ARROW_LEFT,
            "ARROW_RIGHT": Keys.ARROW_RIGHT, "RIGHT": Keys.ARROW_RIGHT,
            "ARROW_UP": Keys.ARROW_UP, "UP": Keys.ARROW_UP,
            "ARROW_DOWN": Keys.ARROW_DOWN, "DOWN": Keys.ARROW_DOWN,
            "HOME": Keys.HOME, "END": Keys.END, "PAGE_UP": Keys.PAGE_UP, "PAGE_DOWN": Keys.PAGE_DOWN,
            "SPACE": Keys.SPACE, "CTRL": Keys.CONTROL, "CONTROL": Keys.CONTROL,
            "ALT": Keys.ALT, "SHIFT": Keys.SHIFT, "META": Keys.META, "COMMAND": Keys.COMMAND,
        }
        return mapping.get(name, raw)

    def connect(debug_port):
        options = webdriver.ChromeOptions()
        options.debugger_address = f"127.0.0.1:{debug_port}"
        return webdriver.Chrome(options=options)

    def switch_target(driver, target):
        target = str(target or "").strip()
        if not target:
            return
        if target in driver.window_handles:
            driver.switch_to.window(target)
            return
        lowered = target.lower()
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if lowered in (driver.title or "").lower() or lowered in (driver.current_url or "").lower():
                return
        raise ValueError(f"Target tab not found: {target}")

    def tabs(driver):
        current = None
        try:
            current = driver.current_window_handle
        except Exception:
            pass
        result = []
        for index, handle in enumerate(driver.window_handles):
            try:
                driver.switch_to.window(handle)
                result.append({
                    "index": index,
                    "targetId": handle,
                    "current": handle == current,
                    "title": driver.title,
                    "url": driver.current_url,
                })
            except Exception as exc:
                result.append({"index": index, "targetId": handle, "error": str(exc)})
        if current in driver.window_handles:
            driver.switch_to.window(current)
        return result

    COLLECT_JS = r"""
    const options = arguments[0] || {};
    const limit = options.limit || 100;
    const bodyChars = options.bodyChars || 6000;
    const htmlLimit = options.htmlChars || 600;
    const includeUrls = !!options.includeUrls;
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
    """

    OVERLAY_JS = r"""
    const elements = arguments[0] || [];
    const clearOnly = !!arguments[1];
    for (const old of Array.from(document.querySelectorAll('[data-smarti-overlay="true"]'))) old.remove();
    if (clearOnly) return true;
    const root = document.createElement('div');
    root.setAttribute('data-smarti-overlay', 'true');
    root.style.cssText = 'position:fixed;left:0;top:0;right:0;bottom:0;z-index:2147483647;pointer-events:none;font:12px Arial,sans-serif;';
    for (const item of elements.slice(0, 120)) {
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
    """

    def snapshot(driver, payload):
        snap = dict(payload.get("snapshot") or {})
        limit = to_int(payload.get("limit", payload.get("max_elements", snap.get("elementLimit", 100))), 100)
        body_chars = to_int(payload.get("body_chars", payload.get("bodyChars", snap.get("bodyChars", 6000))), 6000)
        html_chars = to_int(payload.get("html_chars", payload.get("htmlChars", snap.get("htmlChars", 600))), 600)
        include_urls = bool(payload.get("urls", payload.get("includeUrls", True)))
        include_hidden = bool(payload.get("includeHidden", False))
        state = driver.execute_script(COLLECT_JS, {
            "limit": limit,
            "bodyChars": body_chars,
            "htmlChars": html_chars,
            "includeUrls": include_urls,
            "includeHidden": include_hidden,
        })
        return state or {}

    def resolve(driver, payload):
        ref = str(payload.get("ref") or "").strip()
        selector = str(payload.get("selector") or "").strip()
        if ref:
            try:
                return driver.find_element(By.CSS_SELECTOR, f'[{MARK}="{ref}"]')
            except Exception:
                raise NoSuchElementException(f"STALE_REF: {ref}. Take a fresh snapshot and retry.")
        if selector:
            return driver.find_element(By.CSS_SELECTOR, selector)
        raise ValueError("Action requires ref or selector.")

    def after(driver, payload, action_result=None):
        if payload.get("noSnapshot"):
            return {"ok": True, "result": action_result}
        return {"ok": True, "result": action_result, "page": snapshot(driver, payload)}

    def navigate(driver, payload):
        url = payload.get("url") or payload.get("targetUrl") or payload.get("query_or_url")
        if not url:
            raise ValueError("navigate/open requires url.")
        if payload.get("newTab") or str(payload.get("action")).lower() == "open":
            driver.switch_to.new_window("tab")
        driver.get(str(url))
        return after(driver, payload, {"targetId": driver.current_window_handle, "url": driver.current_url, "title": driver.title})

    def click(driver, payload):
        if payload.get("x") is not None and payload.get("y") is not None and not (payload.get("ref") or payload.get("selector")):
            x = float(payload.get("x"))
            y = float(payload.get("y"))
            result = driver.execute_script("const el=document.elementFromPoint(arguments[0], arguments[1]); if(!el) return null; el.click(); return {tag:el.tagName.toLowerCase(), text:(el.innerText||el.value||'').slice(0,300)};", x, y)
            return after(driver, payload, {"clicked": "coords", "x": x, "y": y, "element": result})
        el = resolve(driver, payload)
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
        return after(driver, payload, {"clicked": payload.get("ref") or payload.get("selector")})

    def hover(driver, payload):
        el = resolve(driver, payload)
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
        ActionChains(driver).move_to_element(el).perform()
        return after(driver, payload, {"hovered": payload.get("ref") or payload.get("selector")})

    def fill_or_type(driver, payload):
        el = resolve(driver, payload)
        text = str(payload.get("text", payload.get("value", "")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
        if payload.get("clear", True):
            try:
                el.clear()
            except Exception:
                driver.execute_script("if('value' in arguments[0]) arguments[0].value=''; else arguments[0].textContent='';", el)
        if payload.get("slowly"):
            delay = max(0.01, min(0.5, float(payload.get("delay", 0.04) or 0.04)))
            for char in text:
                el.send_keys(char)
                time.sleep(delay)
        else:
            el.send_keys(text)
        if payload.get("submit"):
            el.send_keys(Keys.ENTER)
        return after(driver, payload, {"typed": len(text), "target": payload.get("ref") or payload.get("selector")})

    def press(driver, payload):
        keys = payload.get("keys", payload.get("key", payload.get("text", "")))
        if not isinstance(keys, list):
            keys = [keys]
        target = None
        if payload.get("ref") or payload.get("selector"):
            target = resolve(driver, payload)
            target.click()
        element = target or driver.switch_to.active_element
        element.send_keys(*[normalize_key(k) for k in keys])
        return after(driver, payload, {"pressed": [str(k) for k in keys]})

    def select_value(driver, payload):
        el = resolve(driver, payload)
        sel = Select(el)
        value = payload.get("value")
        label = payload.get("label") or payload.get("text")
        index = payload.get("index")
        if value is not None:
            sel.select_by_value(str(value))
        elif index is not None:
            sel.select_by_index(to_int(index, 0))
        elif label is not None:
            sel.select_by_visible_text(str(label))
        else:
            raise ValueError("select requires value, label/text, or index.")
        return after(driver, payload, {"selected": value if value is not None else label if label is not None else index})

    def upload(driver, payload):
        el = resolve(driver, payload)
        paths = payload.get("paths") or payload.get("files") or payload.get("path") or []
        if isinstance(paths, str):
            paths = [paths]
        paths = [os.path.abspath(os.path.expanduser(str(path))) for path in paths if str(path).strip()]
        missing = [path for path in paths if not os.path.exists(path)]
        if missing:
            raise FileNotFoundError("Missing upload files: " + ", ".join(missing))
        el.send_keys("\n".join(paths))
        return after(driver, payload, {"uploaded": paths})

    def wait(driver, payload):
        timeout = max(0.1, float(payload.get("timeoutMs", payload.get("timeout", 10000)) or 10000) / 1000.0)
        selector = payload.get("selector")
        text = payload.get("text")
        url = payload.get("urlContains") or payload.get("url")
        fn = payload.get("function") or payload.get("script")
        time_ms = payload.get("timeMs") or payload.get("ms")
        if time_ms:
            time.sleep(max(0, float(time_ms) / 1000.0))
            return after(driver, payload, {"waitedMs": int(time_ms)})
        end = time.time() + timeout
        while time.time() < end:
            if selector:
                try:
                    if driver.find_elements(By.CSS_SELECTOR, str(selector)):
                        return after(driver, payload, {"matched": "selector", "selector": selector})
                except Exception:
                    pass
            if text:
                try:
                    if str(text) in (driver.execute_script("return document.body ? document.body.innerText : ''") or ""):
                        return after(driver, payload, {"matched": "text", "text": text})
                except Exception:
                    pass
            if url and str(url) in (driver.current_url or ""):
                return after(driver, payload, {"matched": "url", "url": url})
            if fn:
                try:
                    if driver.execute_script("return !!((new Function(arguments[0]))())", str(fn)):
                        return after(driver, payload, {"matched": "function"})
                except Exception:
                    pass
            if not any([selector, text, url, fn]):
                try:
                    if driver.execute_script("return document.readyState") == "complete":
                        return after(driver, payload, {"matched": "loadState", "state": "complete"})
                except Exception:
                    pass
            time.sleep(0.2)
        raise TimeoutException("Timed out waiting for requested browser condition.")

    def evaluate(driver, payload):
        source = str(payload.get("script") or payload.get("code") or payload.get("expression") or "")
        if not source.strip():
            raise ValueError("evaluate requires script/code/expression.")
        el = None
        if payload.get("ref") or payload.get("selector"):
            el = resolve(driver, payload)
        result = driver.execute_script(
            """
            const source = arguments[0];
            const el = arguments[1] || null;
            try {
              const candidate = (0, eval)('(' + source + ')');
              if (typeof candidate === 'function') return candidate(el);
            } catch (err) {}
            return (new Function('el', source))(el);
            """,
            source,
            el,
        )
        return after(driver, payload, {"value": result})

    def storage(driver, payload):
        kind = str(payload.get("kind") or payload.get("storage") or "local").lower()
        op = str(payload.get("op") or payload.get("operation") or "get").lower()
        key = payload.get("key")
        value = payload.get("value")
        if kind == "cookies":
            if op in {"get", "list"}:
                return {"ok": True, "cookies": driver.get_cookies()}
            if op == "delete":
                if key:
                    driver.delete_cookie(str(key))
                else:
                    driver.delete_all_cookies()
                return after(driver, payload, {"cookiesDeleted": key or "all"})
            if op in {"set", "add"} and isinstance(value, dict):
                driver.add_cookie(value)
                return after(driver, payload, {"cookieSet": value.get("name")})
            raise ValueError("cookies storage supports get/list, set/add with value object, or delete.")
        js_storage = "sessionStorage" if kind.startswith("session") else "localStorage"
        if op in {"get", "list"}:
            data = driver.execute_script(f"const out={{}}; for(let i=0;i<{js_storage}.length;i++){{const k={js_storage}.key(i); out[k]={js_storage}.getItem(k);}} return out;")
            return {"ok": True, "storage": kind, "items": data}
        if op in {"set", "add"}:
            driver.execute_script(f"{js_storage}.setItem(arguments[0], arguments[1]);", str(key), str(value))
            return after(driver, payload, {"storageSet": {"kind": kind, "key": key}})
        if op in {"delete", "remove"}:
            driver.execute_script(f"{js_storage}.removeItem(arguments[0]);", str(key))
            return after(driver, payload, {"storageDeleted": {"kind": kind, "key": key}})
        if op == "clear":
            driver.execute_script(f"{js_storage}.clear();")
            return after(driver, payload, {"storageCleared": kind})
        raise ValueError("storage op must be get/list, set/add, delete/remove, or clear.")

    def console_logs(driver, payload):
        try:
            logs = driver.get_log("browser")
            return {"ok": True, "logs": logs[-to_int(payload.get("limit", 100), 100):]}
        except Exception as exc:
            return {"ok": False, "error": f"Console logs are unavailable from this Chrome session: {exc}"}

    def screenshot(driver, payload):
        state = snapshot(driver, payload)
        labels = bool(payload.get("labels", payload.get("annotate", False)))
        path = payload.get("path")
        output_dir = payload.get("outputDir") or os.getcwd()
        os.makedirs(output_dir, exist_ok=True)
        if not path:
            base = sanitize_name(driver.title or "browser")
            path = os.path.join(output_dir, f"{base}_{int(time.time())}.png")
        if labels:
            driver.execute_script(OVERLAY_JS, state.get("elements", []), False)
            time.sleep(0.15)
        try:
            full_page = bool(payload.get("fullPage", payload.get("full_page", False)))
            if full_page:
                try:
                    data = driver.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
                    with open(path, "wb") as fh:
                        fh.write(base64.b64decode(data["data"]))
                except Exception:
                    driver.save_screenshot(path)
            else:
                driver.save_screenshot(path)
        finally:
            if labels:
                try:
                    driver.execute_script(OVERLAY_JS, [], True)
                except Exception:
                    pass
        return {"ok": True, "path": path, "page": state}

    def pdf(driver, payload):
        path = payload.get("path")
        output_dir = payload.get("outputDir") or os.getcwd()
        os.makedirs(output_dir, exist_ok=True)
        if not path:
            base = sanitize_name(driver.title or "browser")
            path = os.path.join(output_dir, f"{base}_{int(time.time())}.pdf")
        result = driver.execute_cdp_cmd("Page.printToPDF", {
            "printBackground": bool(payload.get("printBackground", True)),
            "landscape": bool(payload.get("landscape", False)),
        })
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(result["data"]))
        return {"ok": True, "path": path}

    def dialog(driver, payload):
        try:
            alert = driver.switch_to.alert
            text = alert.text
            if payload.get("promptText") is not None:
                alert.send_keys(str(payload.get("promptText")))
            if payload.get("accept", True):
                alert.accept()
                handled = "accepted"
            else:
                alert.dismiss()
                handled = "dismissed"
            return after(driver, payload, {"dialog": handled, "text": text})
        except NoAlertPresentException:
            return {"ok": False, "error": "No browser dialog is currently open."}

    def cdp(driver, payload):
        method = str(payload.get("method") or "").strip()
        params = payload.get("params") or {}
        if not method:
            raise ValueError("cdp requires method, for example Runtime.evaluate or Network.enable.")
        if not isinstance(params, dict):
            raise ValueError("cdp params must be an object.")
        result = driver.execute_cdp_cmd(method, params)
        return {"ok": True, "method": method, "result": result}

    def scroll(driver, payload):
        if payload.get("ref") or payload.get("selector"):
            el = resolve(driver, payload)
            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
            return after(driver, payload, {"scrolledTo": payload.get("ref") or payload.get("selector")})
        dx = float(payload.get("deltaX", payload.get("x", 0)) or 0)
        dy = float(payload.get("deltaY", payload.get("y", 800)) or 800)
        driver.execute_script("window.scrollBy(arguments[0], arguments[1]);", dx, dy)
        return after(driver, payload, {"scrolledBy": {"x": dx, "y": dy}})

    def resize(driver, payload):
        width = to_int(payload.get("width"), 1280)
        height = to_int(payload.get("height"), 900)
        driver.set_window_size(width, height)
        return after(driver, payload, {"viewport": {"width": width, "height": height}})

    def close_tab(driver, payload):
        closed = driver.current_window_handle
        driver.close()
        if driver.window_handles:
            driver.switch_to.window(driver.window_handles[-1])
        return {"ok": True, "closedTargetId": closed, "tabs": tabs(driver)}

    DISPATCH = {
        "tabs": lambda driver, payload: {"ok": True, "tabs": tabs(driver), "currentTargetId": driver.current_window_handle},
        "start": lambda driver, payload: {"ok": True, "tabs": tabs(driver), "currentTargetId": driver.current_window_handle},
        "open": navigate,
        "navigate": navigate,
        "snapshot": lambda driver, payload: {"ok": True, "page": snapshot(driver, payload)},
        "screenshot": screenshot,
        "pdf": pdf,
        "console": console_logs,
        "storage": storage,
        "cookies": lambda driver, payload: storage(driver, dict(payload, kind="cookies")),
        "click": click,
        "clickcoords": click,
        "type": fill_or_type,
        "fill": fill_or_type,
        "press": press,
        "hover": hover,
        "select": select_value,
        "upload": upload,
        "wait": wait,
        "evaluate": evaluate,
        "dialog": dialog,
        "cdp": cdp,
        "scroll": scroll,
        "scrollintoview": scroll,
        "resize": resize,
        "close": close_tab,
        "close_tab": close_tab,
    }

    def main():
        payload = json.loads(sys.stdin.read() or "{}")
        action = str(payload.get("action") or "snapshot").strip().lower()
        if action == "act":
            request = dict(payload.get("request") or {})
            for key, value in payload.items():
                request.setdefault(key, value)
            action = str(request.get("kind") or request.get("action") or "").strip().lower()
            payload = request
        action = action.replace("-", "_")
        action_key = action.replace("_", "")
        driver = None
        try:
            driver = connect(payload.get("debugPort") or 49223)
            switch_target(driver, payload.get("targetId") or payload.get("tabId") or payload.get("target"))
            handler = DISPATCH.get(action) or DISPATCH.get(action_key)
            if not handler:
                raise ValueError(f"Unsupported browser action: {action}")
            result = handler(driver, payload)
            print(json.dumps(result, ensure_ascii=False, default=str))
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc), "action": action}, ensure_ascii=False, default=str))
        finally:
            if driver is not None:
                try:
                    if getattr(driver, "service", None):
                        driver.service.stop()
                except Exception:
                    pass

    if __name__ == "__main__":
        main()
    '''
)
