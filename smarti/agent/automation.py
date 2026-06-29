"""Browser entrypoint and Windows UI/computer automation helpers."""
from .shared import *


class AutomationMixin:
    def run_browser_action(self, payload):
        return self.browser_controller.run(payload if isinstance(payload, dict) else {"action": "snapshot"})

    def run_computer_automation(self, payload):
        if not self.settings.get("enable_computer_control", False):
            return "ERROR: Computer automation is disabled."
        if isinstance(payload, dict):
            args = copy.deepcopy(payload)
            if str(args.get("code", "") or "").strip() and not str(args.get("action", "") or "").strip():
                return self._run_computer_automation_code(str(args.get("code", "")))
            return self._run_computer_automation_action(args)
        return self._run_computer_automation_code(str(payload or ""))

    def _run_computer_automation_code(self, code):
        safe_code = self._prepare_automation_code(code)
        if not safe_code:
            return "ERROR: Empty computer automation code after normalization."
        ok, err = self._static_code_safety_check(safe_code, "computer_control")
        if not ok:
            return f"ERROR: {err}"
        timeout = self._timeout("tool_timeout_seconds", 120)
        helper_code = r'''
import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
try:
    import pyautogui as pa
    import uiautomation as auto
    import pyperclip as clip
    pa.FAILSAFE = True
except Exception as e:
    print(f"ERROR: Missing libraries or automation init failed: {e}")
    sys.exit(1)

safe_builtins = {
    "print": print, "len": len, "range": range, "str": str, "repr": repr,
    "int": int, "float": float, "bool": bool, "list": list, "dict": dict,
    "set": set, "tuple": tuple, "enumerate": enumerate, "min": min,
    "max": max, "sum": sum, "abs": abs, "all": all, "any": any,
    "sorted": sorted, "isinstance": isinstance, "hasattr": hasattr,
    "Exception": Exception
}

def paste_text(text):
    old = None
    try:
        old = clip.paste()
    except Exception:
        old = None
    clip.copy(str(text))
    time.sleep(0.1)
    pa.hotkey("ctrl", "v")
    time.sleep(0.1)
    if old is not None:
        try:
            clip.copy(old)
        except Exception:
            pass

def list_windows():
    names = []
    root = auto.GetRootControl()
    for win in root.GetChildren():
        name = win.Name or ""
        if name:
            names.append(name)
    return names

def find_window(name, timeout=5):
    needle = str(name or "").lower()
    end_at = time.time() + float(timeout or 5)
    while time.time() < end_at:
        root = auto.GetRootControl()
        for win in root.GetChildren():
            title = win.Name or ""
            if needle and needle in title.lower():
                return win
        time.sleep(0.25)
    return None

def activate_window(name, timeout=5):
    win = find_window(name, timeout)
    if not win:
        print("ERROR: window not found: " + str(name))
        return None
    try:
        win.SetActive()
    except Exception:
        try:
            win.SetFocus()
        except Exception:
            pass
    print("SUCCESS: activated window: " + str(win.Name or name))
    return win

def send_keys(keys):
    pa.write(str(keys))

def press(key):
    pa.press(str(key))

def hotkey(*keys):
    pa.hotkey(*[str(k) for k in keys])

env = {
    "__builtins__": safe_builtins,
    "pa": pa,
    "auto": auto,
    "clip": clip,
    "paste_text": paste_text,
    "time": time,
    "list_windows": list_windows,
    "find_window": find_window,
    "activate_window": activate_window,
    "send_keys": send_keys,
    "press": press,
    "hotkey": hotkey,
}
exec(sys.stdin.read(), env)
sys.exit(0)

def _rect_dict(control):
    try:
        rect = control.BoundingRectangle
        return {
            "left": int(rect.left), "top": int(rect.top),
            "right": int(rect.right), "bottom": int(rect.bottom),
            "width": int(rect.width()), "height": int(rect.height())
        }
    except Exception:
        return {}

def _pattern_names(control):
    names = []
    for pid in [
        auto.PatternId.InvokePattern, auto.PatternId.ValuePattern,
        auto.PatternId.TogglePattern, auto.PatternId.SelectionItemPattern,
        auto.PatternId.ExpandCollapsePattern, auto.PatternId.RangeValuePattern,
        auto.PatternId.ScrollPattern, auto.PatternId.TextPattern,
        auto.PatternId.WindowPattern
    ]:
        try:
            if control.GetPattern(pid):
                names.append(auto.PatternIdNames.get(pid, str(pid)))
        except Exception:
            pass
    return names

def describe_control(control, path="", depth=0):
    def read_attr(name, default=""):
        try:
            return getattr(control, name)
        except Exception:
            return default
    return {
        "path": path,
        "depth": depth,
        "name": read_attr("Name", "") or "",
        "control_type": read_attr("ControlTypeName", "") or "",
        "automation_id": read_attr("AutomationId", "") or "",
        "class_name": read_attr("ClassName", "") or "",
        "is_enabled": bool(read_attr("IsEnabled", False)),
        "is_offscreen": bool(read_attr("IsOffscreen", False)),
        "rect": _rect_dict(control),
        "patterns": _pattern_names(control),
    }

def walk_controls(root, max_depth=2, limit=120, include_offscreen=False, include_root=True):
    max_depth = max(0, int(max_depth or 0))
    limit = max(1, int(limit or 120))
    items = []
    stack = [(root, "", 0)]
    while stack and len(items) < limit:
        control, path, depth = stack.pop(0)
        if include_root or path:
            try:
                offscreen = bool(getattr(control, "IsOffscreen", False))
            except Exception:
                offscreen = False
            if include_offscreen or not offscreen:
                items.append(describe_control(control, path, depth))
        if depth >= max_depth:
            continue
        try:
            children = control.GetChildren()
        except Exception:
            children = []
        for index, child in enumerate(children):
            child_path = str(index) if not path else path + "/" + str(index)
            stack.append((child, child_path, depth + 1))
    return items

def normalize_text(value):
    return str(value or "").strip().lower()

def type_matches(actual, expected):
    actual = normalize_text(actual).replace("control", "")
    expected = normalize_text(expected).replace("control", "")
    return not expected or actual == expected

def match_control(control, criteria):
    name = normalize_text(criteria.get("name") or criteria.get("text"))
    automation_id = normalize_text(criteria.get("automation_id"))
    class_name = normalize_text(criteria.get("class_name"))
    control_type = normalize_text(criteria.get("control_type"))
    try:
        if name and name not in normalize_text(control.Name):
            return False
        if automation_id and automation_id != normalize_text(control.AutomationId):
            return False
        if class_name and class_name not in normalize_text(control.ClassName):
            return False
        if control_type and not type_matches(control.ControlTypeName, control_type):
            return False
        return True
    except Exception:
        return False

def control_by_path(path, root=None):
    control = root or auto.GetRootControl()
    if path in (None, ""):
        return control
    for raw in str(path).split("/"):
        if raw == "":
            continue
        index = int(raw)
        children = control.GetChildren()
        control = children[index]
    return control

def find_window(value="", class_name="", automation_id="", timeout=5):
    end_at = time.time() + float(timeout or 5)
    criteria = {
        "name": value,
        "class_name": class_name,
        "automation_id": automation_id,
        "control_type": "Window"
    }
    while time.time() < end_at:
        for index, win in enumerate(auto.GetRootControl().GetChildren()):
            if match_control(win, criteria) or (value and value.lower() in normalize_text(win.Name)):
                return win, str(index)
        time.sleep(0.2)
    return None, ""

def search_controls(args, require_match=True):
    limit = int(args.get("limit") or 40)
    max_depth = int(args.get("max_depth") or 5)
    root = auto.GetRootControl()
    root_path = ""
    window = str(args.get("window") or "").strip()
    if window:
        win, win_path = find_window(window, "", "", args.get("timeout", 5))
        if not win:
            fail("window not found: " + window)
        root, root_path = win, win_path
    if args.get("path") not in (None, ""):
        return [(control_by_path(args.get("path"), auto.GetRootControl()), str(args.get("path")))], str(args.get("path"))
    criteria = {
        "name": args.get("name", ""),
        "text": args.get("text", "") if not args.get("name") else "",
        "automation_id": args.get("automation_id", ""),
        "class_name": args.get("class_name", ""),
        "control_type": args.get("control_type", ""),
    }
    has_criteria = any(str(value or "").strip() for value in criteria.values())
    if not has_criteria:
        if require_match and window:
            return [(root, root_path)], root_path
        if require_match:
            fail("missing target: provide path, window, name, automation_id, class_name, or control_type")
        return [], ""
    matches = []
    for item in walk_controls(root, max_depth=max_depth, limit=max(200, limit * 6), include_offscreen=False, include_root=True):
        try:
            control = control_by_path(item["path"], auto.GetRootControl()) if item["path"] else root
        except Exception:
            continue
        if match_control(control, criteria):
            matches.append(control)
            if len(matches) >= limit:
                break
    if require_match and not matches:
        fail("target element not found")
    return matches, root_path

def focus_control(control):
    try:
        control.SetFocus()
        return True
    except Exception:
        try:
            control.SetActive()
            return True
        except Exception:
            return False

def paste_text(text):
    old = None
    try:
        old = clip.paste()
    except Exception:
        old = None
    clip.copy(str(text))
    time.sleep(0.1)
    pa.hotkey("ctrl", "v")
    time.sleep(0.1)
    if old is not None:
        try:
            clip.copy(old)
        except Exception:
            pass

def print_payload(payload):
    print("SMARTI_UI_STATE:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

def fail(message, extra=None):
    payload = {"status": "error", "message": str(message)}
    if extra:
        payload.update(extra)
    print_payload(payload)
    sys.exit(1)

def success(action, message, **extra):
    payload = {"status": "ok", "action": action, "message": message}
    payload.update(extra)
    print_payload(payload)

def action_inspect(args):
    root = auto.GetRootControl()
    root_path = ""
    if args.get("window"):
        root, root_path = find_window(str(args.get("window")), "", "", args.get("timeout", 5))
        if not root:
            fail("window not found: " + str(args.get("window")))
    elements = walk_controls(
        root,
        max_depth=args.get("max_depth", 2),
        limit=args.get("limit", 120),
        include_offscreen=bool(args.get("include_offscreen", False)),
        include_root=True
    )
    if root_path:
        for item in elements:
            if item["path"]:
                item["path"] = root_path + "/" + item["path"]
            else:
                item["path"] = root_path
    success("inspect", "accessibility tree collected", root=describe_control(root, root_path, 0), elements=elements)

def action_list_windows(args):
    windows = []
    for index, win in enumerate(auto.GetRootControl().GetChildren()):
        windows.append(describe_control(win, str(index), 1))
    success("list_windows", "windows collected", windows=windows[:int(args.get("limit") or 80)])

def action_find(args):
    matches, _ = search_controls(args, require_match=False)
    elements = [describe_control(control, args.get("path", ""), 0) for control in matches]
    success("find", "matches collected", count=len(elements), elements=elements)

def action_focus_window(args):
    window = str(args.get("window") or args.get("name") or "").strip()
    if not window:
        fail("focus_window requires window or name")
    win, path = find_window(window, args.get("class_name", ""), args.get("automation_id", ""), args.get("timeout", 5))
    if not win:
        fail("window not found: " + window)
    focus_control(win)
    success("focus_window", "window focused", target=describe_control(win, path, 0))

def first_target(args):
    matches, _ = search_controls(args, require_match=True)
    return matches[0]

def invoke_pattern(control):
    pattern = control.GetPattern(auto.PatternId.InvokePattern)
    if not pattern:
        return False
    pattern.Invoke()
    return True

DESTRUCTIVE_TERMS = {
    "delete", "remove", "uninstall", "format", "reset", "discard",
    "trash", "erase", "wipe", "מחק", "מחיקה", "הסר", "הסרה",
    "איפוס", "פרמוט"
}

def require_destructive_opt_in(args, target_info):
    label = normalize_text(
        str(target_info.get("name", "")) + " " +
        str(target_info.get("automation_id", "")) + " " +
        str(target_info.get("class_name", ""))
    )
    if any(term in label for term in DESTRUCTIVE_TERMS) and not bool(args.get("allow_destructive", False)):
        fail("target looks destructive; rerun with dry_run first and set allow_destructive=true only after user approval", {"target": target_info})

def action_on_target(args):
    action = normalize_text(args.get("action"))
    target = first_target(args)
    before = describe_control(target, args.get("path", ""), 0)
    if bool(args.get("dry_run", False)):
        success(action, "dry run: target resolved, no action performed", target=before)
        return
    if action in {"invoke", "click", "toggle", "select", "expand", "collapse"}:
        require_destructive_opt_in(args, before)
    if action == "focus":
        focus_control(target)
        success(action, "target focused", target=before)
        return
    if action == "invoke":
        if not invoke_pattern(target):
            if bool(args.get("allow_mouse_fallback", False)):
                target.Click()
            else:
                fail("target does not expose InvokePattern; set allow_mouse_fallback=true only when a bounded element click is acceptable", {"target": before})
        success(action, "target invoked", target=before)
        return
    if action == "click":
        try:
            if not invoke_pattern(target):
                target.Click()
        except Exception as e:
            fail("element click failed: " + str(e), {"target": before})
        success(action, "target clicked by resolved UIA element", target=before)
        return
    if action == "set_text":
        text = str(args.get("text") or "")
        focus_control(target)
        try:
            pattern = target.GetPattern(auto.PatternId.ValuePattern)
            if pattern and not bool(pattern.IsReadOnly):
                pattern.SetValue(text)
                success(action, "text set with ValuePattern", target=before)
                return
        except Exception:
            pass
        if bool(args.get("allow_clipboard_fallback", True)):
            paste_text(text)
            success(action, "text pasted after focusing target", target=before)
            return
        fail("target does not expose writable ValuePattern and clipboard fallback is disabled", {"target": before})
    if action == "toggle":
        pattern = target.GetPattern(auto.PatternId.TogglePattern)
        if not pattern:
            fail("target does not expose TogglePattern", {"target": before})
        pattern.Toggle()
        success(action, "target toggled", target=before)
        return
    if action == "select":
        pattern = target.GetPattern(auto.PatternId.SelectionItemPattern)
        if not pattern:
            fail("target does not expose SelectionItemPattern", {"target": before})
        pattern.Select()
        success(action, "target selected", target=before)
        return
    if action in {"expand", "collapse"}:
        pattern = target.GetPattern(auto.PatternId.ExpandCollapsePattern)
        if not pattern:
            fail("target does not expose ExpandCollapsePattern", {"target": before})
        if action == "expand":
            pattern.Expand()
        else:
            pattern.Collapse()
        success(action, "target " + action + "ed", target=before)
        return
    fail("unsupported target action: " + action)

def focus_for_keys(args):
    has_target = any(str(args.get(k) or "").strip() for k in ["path", "window", "name", "automation_id", "class_name", "control_type"])
    if has_target:
        target = first_target(args)
        focus_control(target)
        return describe_control(target, args.get("path", ""), 0)
    if not bool(args.get("allow_global_keys", False)):
        fail("keyboard actions require a target/window or allow_global_keys=true")
    return {}

def action_keyboard(args):
    action = normalize_text(args.get("action"))
    target = focus_for_keys(args)
    if bool(args.get("dry_run", False)):
        success(action, "dry run: keyboard target resolved, no keys sent", target=target)
        return
    if action == "send_keys":
        keys = args.get("keys", args.get("text", ""))
        if isinstance(keys, list):
            pa.hotkey(*[str(k) for k in keys])
        else:
            pa.write(str(keys))
        success(action, "keys sent", target=target)
        return
    if action == "press":
        key = str(args.get("keys") or args.get("text") or "")
        if not key:
            fail("press requires keys or text")
        pa.press(key)
        success(action, "key pressed", target=target)
        return
    if action == "hotkey":
        keys = args.get("keys")
        if not isinstance(keys, list):
            keys = [part.strip() for part in str(keys or "").replace("+", ",").split(",") if part.strip()]
        if not keys:
            fail("hotkey requires keys as a list or plus/comma separated string")
        pa.hotkey(*[str(k) for k in keys])
        success(action, "hotkey sent", target=target)
        return
    fail("unsupported keyboard action: " + action)

args = json.loads(sys.stdin.read() or "{}")
action = normalize_text(args.get("action") or "inspect")
if action == "inspect":
    action_inspect(args)
elif action == "list_windows":
    action_list_windows(args)
elif action == "find":
    action_find(args)
elif action == "get_focused":
    focused = auto.GetFocusedControl()
    success(action, "focused control collected", focused=describe_control(focused, "", 0))
elif action == "focus_window":
    action_focus_window(args)
elif action in {"focus", "invoke", "click", "set_text", "toggle", "select", "expand", "collapse"}:
    action_on_target(args)
elif action in {"send_keys", "press", "hotkey"}:
    action_keyboard(args)
else:
    fail("unknown action: " + action)
'''
        helper_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as fp:
                helper_path = fp.name
                fp.write(helper_code)
            completed = self._run_cancelable_subprocess([self._python_executable(), helper_path], input=safe_code, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=WIN_CREATE_NO_WINDOW)
            stdout = (completed.stdout or '').strip()
            stderr = (completed.stderr or '').strip()
            body = f"EXIT_CODE: {completed.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
            if completed.returncode != 0:
                return self._truncate_tool_output("ERROR: Computer automation failed.\n" + body)
            if not stdout and not stderr:
                return self._truncate_tool_output("ERROR: Computer automation ended without printed verification. Re-run with explicit UI verification and print a clear result.")
            output = "SUCCESS: Computer automation completed.\n" + body
            return self._truncate_tool_output(output)
        except subprocess.TimeoutExpired:
            return f"ERROR: Computer automation timeout after {timeout}s."
        except SmartiCancelled:
            raise
        except Exception as e:
            return f"ERROR in automation script: {e}"
        finally:
            if helper_path:
                try: os.remove(helper_path)
                except: pass

    def _run_computer_automation_action(self, args):
        action = str(args.get("action", "") or "").strip().lower()
        if not action:
            return "ERROR: Missing computer automation action. Use action='inspect' to read the UIA tree, or provide legacy code."
        if str(args.get("code", "") or "").strip():
            args = {k: v for k, v in args.items() if k != "code"}
        timeout = self._timeout("tool_timeout_seconds", 120)
        helper_code = r'''
import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
try:
    import pyautogui as pa
    import uiautomation as auto
    import pyperclip as clip
    pa.FAILSAFE = True
except Exception as e:
    print("SMARTI_UI_STATE:")
    print(json.dumps({"status": "error", "message": "Missing libraries or automation init failed: " + str(e)}, ensure_ascii=False, indent=2))
    sys.exit(1)

def _rect_dict(control):
    try:
        rect = control.BoundingRectangle
        return {
            "left": int(rect.left), "top": int(rect.top),
            "right": int(rect.right), "bottom": int(rect.bottom),
            "width": int(rect.width()), "height": int(rect.height())
        }
    except Exception:
        return {}

def _pattern_names(control):
    names = []
    for pid in [
        auto.PatternId.InvokePattern, auto.PatternId.ValuePattern,
        auto.PatternId.TogglePattern, auto.PatternId.SelectionItemPattern,
        auto.PatternId.ExpandCollapsePattern, auto.PatternId.RangeValuePattern,
        auto.PatternId.ScrollPattern, auto.PatternId.TextPattern,
        auto.PatternId.WindowPattern
    ]:
        try:
            if control.GetPattern(pid):
                names.append(auto.PatternIdNames.get(pid, str(pid)))
        except Exception:
            pass
    return names

def describe_control(control, path="", depth=0):
    def read_attr(name, default=""):
        try:
            return getattr(control, name)
        except Exception:
            return default
    return {
        "path": path,
        "depth": depth,
        "name": read_attr("Name", "") or "",
        "control_type": read_attr("ControlTypeName", "") or "",
        "automation_id": read_attr("AutomationId", "") or "",
        "class_name": read_attr("ClassName", "") or "",
        "is_enabled": bool(read_attr("IsEnabled", False)),
        "is_offscreen": bool(read_attr("IsOffscreen", False)),
        "rect": _rect_dict(control),
        "patterns": _pattern_names(control),
    }

def walk_controls(root, max_depth=2, limit=120, include_offscreen=False, include_root=True):
    max_depth = max(0, int(max_depth or 0))
    limit = max(1, int(limit or 120))
    items = []
    stack = [(root, "", 0)]
    while stack and len(items) < limit:
        control, path, depth = stack.pop(0)
        if include_root or path:
            try:
                offscreen = bool(getattr(control, "IsOffscreen", False))
            except Exception:
                offscreen = False
            if include_offscreen or not offscreen:
                items.append(describe_control(control, path, depth))
        if depth >= max_depth:
            continue
        try:
            children = control.GetChildren()
        except Exception:
            children = []
        for index, child in enumerate(children):
            child_path = str(index) if not path else path + "/" + str(index)
            stack.append((child, child_path, depth + 1))
    return items

def normalize_text(value):
    return str(value or "").strip().lower()

def type_matches(actual, expected):
    actual = normalize_text(actual).replace("control", "")
    expected = normalize_text(expected).replace("control", "")
    return not expected or actual == expected

def match_control(control, criteria):
    name = normalize_text(criteria.get("name") or criteria.get("text"))
    automation_id = normalize_text(criteria.get("automation_id"))
    class_name = normalize_text(criteria.get("class_name"))
    control_type = normalize_text(criteria.get("control_type"))
    try:
        if name and name not in normalize_text(control.Name):
            return False
        if automation_id and automation_id != normalize_text(control.AutomationId):
            return False
        if class_name and class_name not in normalize_text(control.ClassName):
            return False
        if control_type and not type_matches(control.ControlTypeName, control_type):
            return False
        return True
    except Exception:
        return False

def control_by_path(path, root=None):
    control = root or auto.GetRootControl()
    if path in (None, ""):
        return control
    for raw in str(path).split("/"):
        if raw == "":
            continue
        index = int(raw)
        children = control.GetChildren()
        control = children[index]
    return control

def find_window(value="", class_name="", automation_id="", timeout=5):
    value = str(value or "")
    end_at = time.time() + float(timeout or 5)
    criteria = {
        "name": value,
        "class_name": class_name,
        "automation_id": automation_id,
        "control_type": "Window"
    }
    while time.time() < end_at:
        for index, win in enumerate(auto.GetRootControl().GetChildren()):
            if match_control(win, criteria) or (value and value.lower() in normalize_text(win.Name)):
                return win, str(index)
        time.sleep(0.2)
    return None, ""

def search_controls(args, require_match=True):
    limit = int(args.get("limit") or 40)
    max_depth = int(args.get("max_depth") or 5)
    root = auto.GetRootControl()
    root_path = ""
    window = str(args.get("window") or "").strip()
    if window:
        win, win_path = find_window(window, "", "", args.get("timeout", 5))
        if not win:
            fail("window not found: " + window)
        root, root_path = win, win_path
    if args.get("path") not in (None, ""):
        return [(control_by_path(args.get("path"), auto.GetRootControl()), str(args.get("path")))], str(args.get("path"))
    criteria = {
        "name": args.get("name", ""),
        "text": args.get("text", "") if not args.get("name") else "",
        "automation_id": args.get("automation_id", ""),
        "class_name": args.get("class_name", ""),
        "control_type": args.get("control_type", ""),
    }
    has_criteria = any(str(value or "").strip() for value in criteria.values())
    if not has_criteria:
        if require_match and window:
            return [(root, root_path)], root_path
        if require_match:
            fail("missing target: provide path, window, name, automation_id, class_name, or control_type")
        return [], ""
    matches = []
    for item in walk_controls(root, max_depth=max_depth, limit=max(200, limit * 6), include_offscreen=False, include_root=True):
        try:
            control = control_by_path(item["path"], root) if item["path"] else root
        except Exception:
            continue
        if match_control(control, criteria):
            matches.append((control, (root_path + "/" + item["path"]) if root_path and item["path"] else (root_path or item["path"])))
            if len(matches) >= limit:
                break
    if require_match and not matches:
        fail("target element not found")
    return matches, root_path

def focus_control(control):
    try:
        control.SetFocus()
        return True
    except Exception:
        try:
            control.SetActive()
            return True
        except Exception:
            return False

def paste_text(text):
    old = None
    try:
        old = clip.paste()
    except Exception:
        old = None
    clip.copy(str(text))
    time.sleep(0.1)
    pa.hotkey("ctrl", "v")
    time.sleep(0.1)
    if old is not None:
        try:
            clip.copy(old)
        except Exception:
            pass

def print_payload(payload):
    print("SMARTI_UI_STATE:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

def fail(message, extra=None):
    payload = {"status": "error", "message": str(message)}
    if extra:
        payload.update(extra)
    print_payload(payload)
    sys.exit(1)

def success(action, message, **extra):
    payload = {"status": "ok", "action": action, "message": message}
    payload.update(extra)
    print_payload(payload)

def action_inspect(args):
    root = auto.GetRootControl()
    root_path = ""
    if args.get("window"):
        root, root_path = find_window(str(args.get("window")), "", "", args.get("timeout", 5))
        if not root:
            fail("window not found: " + str(args.get("window")))
    elements = walk_controls(
        root,
        max_depth=args.get("max_depth", 2),
        limit=args.get("limit", 120),
        include_offscreen=bool(args.get("include_offscreen", False)),
        include_root=True
    )
    if root_path:
        for item in elements:
            item["path"] = root_path + (("/" + item["path"]) if item["path"] else "")
    success("inspect", "accessibility tree collected", root=describe_control(root, root_path, 0), elements=elements)

def action_list_windows(args):
    windows = []
    for index, win in enumerate(auto.GetRootControl().GetChildren()):
        windows.append(describe_control(win, str(index), 1))
    success("list_windows", "windows collected", windows=windows[:int(args.get("limit") or 80)])

def action_find(args):
    matches, _ = search_controls(args, require_match=False)
    elements = [describe_control(control, path, 0) for control, path in matches]
    success("find", "matches collected", count=len(elements), elements=elements)

def action_focus_window(args):
    window = str(args.get("window") or args.get("name") or "").strip()
    if not window:
        fail("focus_window requires window or name")
    win, path = find_window(window, args.get("class_name", ""), args.get("automation_id", ""), args.get("timeout", 5))
    if not win:
        fail("window not found: " + window)
    focus_control(win)
    success("focus_window", "window focused", target=describe_control(win, path, 0))

def first_target(args):
    matches, _ = search_controls(args, require_match=True)
    control, path = matches[0]
    return control, path

def invoke_pattern(control):
    pattern = control.GetPattern(auto.PatternId.InvokePattern)
    if not pattern:
        return False
    pattern.Invoke()
    return True

DESTRUCTIVE_TERMS = {
    "delete", "remove", "uninstall", "format", "reset", "discard",
    "trash", "erase", "wipe", "מחק", "מחיקה", "הסר", "הסרה",
    "איפוס", "פרמוט"
}

def require_destructive_opt_in(args, target_info):
    label = normalize_text(
        str(target_info.get("name", "")) + " " +
        str(target_info.get("automation_id", "")) + " " +
        str(target_info.get("class_name", ""))
    )
    if any(term in label for term in DESTRUCTIVE_TERMS) and not bool(args.get("allow_destructive", False)):
        fail("target looks destructive; rerun with dry_run first and set allow_destructive=true only after user approval", {"target": target_info})

def action_on_target(args):
    action = normalize_text(args.get("action"))
    target, path = first_target(args)
    before = describe_control(target, path, 0)
    if bool(args.get("dry_run", False)):
        success(action, "dry run: target resolved, no action performed", target=before)
        return
    if action in {"invoke", "click", "toggle", "select", "expand", "collapse"}:
        require_destructive_opt_in(args, before)
    if action == "focus":
        focus_control(target)
        success(action, "target focused", target=before)
        return
    if action == "invoke":
        if not invoke_pattern(target):
            if bool(args.get("allow_mouse_fallback", False)):
                target.Click()
            else:
                fail("target does not expose InvokePattern; set allow_mouse_fallback=true only when a bounded element click is acceptable", {"target": before})
        success(action, "target invoked", target=before)
        return
    if action == "click":
        try:
            if not invoke_pattern(target):
                target.Click()
        except Exception as e:
            fail("element click failed: " + str(e), {"target": before})
        success(action, "target clicked by resolved UIA element", target=before)
        return
    if action == "set_text":
        text = str(args.get("text") or "")
        focus_control(target)
        try:
            pattern = target.GetPattern(auto.PatternId.ValuePattern)
            if pattern and not bool(pattern.IsReadOnly):
                pattern.SetValue(text)
                success(action, "text set with ValuePattern", target=before)
                return
        except Exception:
            pass
        if bool(args.get("allow_clipboard_fallback", True)):
            paste_text(text)
            success(action, "text pasted after focusing target", target=before)
            return
        fail("target does not expose writable ValuePattern and clipboard fallback is disabled", {"target": before})
    if action == "toggle":
        pattern = target.GetPattern(auto.PatternId.TogglePattern)
        if not pattern:
            fail("target does not expose TogglePattern", {"target": before})
        pattern.Toggle()
        success(action, "target toggled", target=before)
        return
    if action == "select":
        pattern = target.GetPattern(auto.PatternId.SelectionItemPattern)
        if not pattern:
            fail("target does not expose SelectionItemPattern", {"target": before})
        pattern.Select()
        success(action, "target selected", target=before)
        return
    if action in {"expand", "collapse"}:
        pattern = target.GetPattern(auto.PatternId.ExpandCollapsePattern)
        if not pattern:
            fail("target does not expose ExpandCollapsePattern", {"target": before})
        if action == "expand":
            pattern.Expand()
        else:
            pattern.Collapse()
        success(action, "target " + action + "ed", target=before)
        return
    fail("unsupported target action: " + action)

def focus_for_keys(args):
    has_target = any(str(args.get(k) or "").strip() for k in ["path", "window", "name", "automation_id", "class_name", "control_type"])
    if has_target:
        target, path = first_target(args)
        focus_control(target)
        return describe_control(target, path, 0)
    if not bool(args.get("allow_global_keys", False)):
        fail("keyboard actions require a target/window or allow_global_keys=true")
    return {}

def action_keyboard(args):
    action = normalize_text(args.get("action"))
    target = focus_for_keys(args)
    if bool(args.get("dry_run", False)):
        success(action, "dry run: keyboard target resolved, no keys sent", target=target)
        return
    if action == "send_keys":
        keys = args.get("keys", args.get("text", ""))
        if isinstance(keys, list):
            pa.hotkey(*[str(k) for k in keys])
        else:
            pa.write(str(keys))
        success(action, "keys sent", target=target)
        return
    if action == "press":
        key = str(args.get("keys") or args.get("text") or "")
        if not key:
            fail("press requires keys or text")
        pa.press(key)
        success(action, "key pressed", target=target)
        return
    if action == "hotkey":
        keys = args.get("keys")
        if not isinstance(keys, list):
            keys = [part.strip() for part in str(keys or "").replace("+", ",").split(",") if part.strip()]
        if not keys:
            fail("hotkey requires keys as a list or plus/comma separated string")
        pa.hotkey(*[str(k) for k in keys])
        success(action, "hotkey sent", target=target)
        return
    fail("unsupported keyboard action: " + action)

args = json.loads(sys.stdin.read() or "{}")
action = normalize_text(args.get("action") or "inspect")
if action == "inspect":
    action_inspect(args)
elif action == "list_windows":
    action_list_windows(args)
elif action == "find":
    action_find(args)
elif action == "get_focused":
    focused = auto.GetFocusedControl()
    success(action, "focused control collected", focused=describe_control(focused, "", 0))
elif action == "focus_window":
    action_focus_window(args)
elif action in {"focus", "invoke", "click", "set_text", "toggle", "select", "expand", "collapse"}:
    action_on_target(args)
elif action in {"send_keys", "press", "hotkey"}:
    action_keyboard(args)
else:
    fail("unknown action: " + action)
'''
        helper_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py", delete=False) as fp:
                helper_path = fp.name
                fp.write(helper_code)
            payload_json = json.dumps(args, ensure_ascii=False)
            completed = self._run_cancelable_subprocess([self._python_executable(), helper_path], input=payload_json, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=WIN_CREATE_NO_WINDOW)
            stdout = (completed.stdout or '').strip()
            stderr = (completed.stderr or '').strip()
            body = f"EXIT_CODE: {completed.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
            if completed.returncode != 0:
                return self._truncate_tool_output("ERROR: Computer automation failed.\n" + body)
            if not stdout and not stderr:
                return self._truncate_tool_output("ERROR: Computer automation ended without UIA output.")
            output = "SUCCESS: Computer automation completed.\n" + body
            return self._truncate_tool_output(output)
        except subprocess.TimeoutExpired:
            return f"ERROR: Computer automation timeout after {timeout}s."
        except SmartiCancelled:
            raise
        except Exception as e:
            return f"ERROR in automation action: {e}"
        finally:
            if helper_path:
                try: os.remove(helper_path)
                except: pass
