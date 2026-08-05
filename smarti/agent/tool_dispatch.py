"""Audited built-in tool dispatch."""
from .shared import *


class ToolDispatchMixin:
    @classmethod
    def _redact_tool_args_for_audit(cls, value, key=""):
        sensitive = ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization")
        if key and any(marker in str(key).casefold() for marker in sensitive):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(item_key): cls._redact_tool_args_for_audit(item, str(item_key)) for item_key, item in value.items()}
        if isinstance(value, list):
            return [cls._redact_tool_args_for_audit(item, key) for item in value]
        if isinstance(value, tuple):
            return tuple(cls._redact_tool_args_for_audit(item, key) for item in value)
        return value

    def _execute_tool_with_audit(self, action, args_dict):
        started = time.time()
        safe_args = self._redact_tool_args_for_audit(args_dict or {})
        try:
            serialized_args = json.dumps(safe_args, sort_keys=True, ensure_ascii=False, default=str)
            args_hash = hashlib.sha256(serialized_args.encode("utf-8")).hexdigest()[:12]
            args_preview = self._truncate_tool_output(json.dumps(safe_args, ensure_ascii=False, default=str))[:1200]
        except Exception:
            args_hash = "unknown"
            args_preview = str(safe_args or "")[:1200]
        logging.info(f"TOOL START | {action} | args_hash={args_hash} | args={args_preview}")
        if getattr(self, "audit_logger", None):
            self.audit_logger.record("tool_start", {"tool": action, "args_hash": args_hash, "args_preview": args_preview}, self.settings)
        try:
            feedback, message = self._execute_tool_impl(action, args_dict)
            status = "error" if str(feedback or message or "").startswith("ERROR") else "ok"
            duration_ms = int((time.time() - started) * 1000)
            preview = self._truncate_tool_output(str(feedback or message or ""))[:1200]
            logging.info(f"TOOL FINISH | {action} | status={status} | duration_ms={duration_ms} | preview={preview}")
            if getattr(self, "audit_logger", None):
                self.audit_logger.record(
                    "tool_finish",
                    {
                        "tool": action,
                        "args_hash": args_hash,
                        "status": status,
                        "duration_ms": duration_ms,
                        "preview": preview
                    },
                    self.settings
                )
            context_output = feedback if feedback is not None else message
            if isinstance(context_output, str) and context_output.startswith("IMAGE_BASE64:"):
                context_output = "[IMAGE_BASE64 omitted from persistent tool context]"
            self._record_tool_context_event(action, safe_args, status, context_output)
            return feedback, message
        except SmartiCancelled:
            duration_ms = int((time.time() - started) * 1000)
            logging.info(f"TOOL FINISH | {action} | status=cancelled | duration_ms={duration_ms} | preview=CANCELLED_BY_USER")
            if getattr(self, "audit_logger", None):
                self.audit_logger.record(
                    "tool_finish",
                    {
                        "tool": action,
                        "args_hash": args_hash,
                        "status": "cancelled",
                        "duration_ms": duration_ms,
                        "preview": "CANCELLED_BY_USER"
                    },
                    self.settings
                )
            self._record_tool_context_event(action, safe_args, "cancelled", "CANCELLED_BY_USER")
            raise
        except Exception as e:
            logging.exception(f"TOOL CRASH | {action} | args_hash={args_hash}")
            if getattr(self, "audit_logger", None):
                self.audit_logger.record("tool_crash", {"tool": action, "args_hash": args_hash, "error": str(e)}, self.settings)
            self._record_tool_context_event(action, safe_args, "crash", str(e))
            raise

    def execute_tool(self, action, args_dict):
        if not isinstance(args_dict, dict):
            args_dict = {}
        args_dict = self._normalize_tool_call_args(action, args_dict)
        unified_tools = {"system_manager", "software_manager", "file_manager", "web_manager", "screen_manager", "background_task_manager", "memory_manager", "extension_manager"}
        routed_from_unified = False
        if action in unified_tools:
            if action in self.settings.get("tools_config", {}) and not self.settings["tools_config"][action]:
                return (f"ERROR: Tool '{action}' is disabled by user.", None)
            try:
                routed_action, routed_args = self._route_unified_tool(action, args_dict)
            except ValueError as e:
                return (f"ERROR: {e}", None)
            action = routed_action
            args_dict = self._normalize_tool_call_args(action, routed_args)
            routed_from_unified = True
        sandbox_blocked, sandbox_err = self._sandbox_blocks_unconstrained_tool(action)
        if sandbox_blocked:
            return (sandbox_err, None)
        if action == "filesystem_operation":
            return (self.file_manager_operation(args_dict), None)
        if action == "attach_local_file":
            return (self.attach_local_file_tool(args_dict.get("path", "")), None)
        if action in {"search_mcp", "install_mcp", "run_mcp"} and not self.settings.get("enable_mcp_clawhub", False):
            return ("ERROR: MCP is disabled by user settings. Do not use MCP unless the user enables it.", None)
        if action in {"list_skills", "search_skills", "install_skill", "install_skill_requirements", "load_skill", "run_skill"} and not self.settings.get("enable_skills_beta", True):
            return ("ERROR: Skills are disabled by user settings. Do not use Skills unless the user enables them.", None)
        if action in BUILTIN_TOOL_SCHEMAS or action in BUILTIN_DYNAMIC_TOOLS:
            if not routed_from_unified and action in self.settings.get("tools_config", {}) and not self.settings["tools_config"][action]:
                return (f"ERROR: Tool '{action}' is disabled by user.", None)
                
            if action == "canvas_manager":
                return (self.canvas_manager_tool(args_dict), None)
            elif action == "document_manager":
                return (self.document_manager_tool(args_dict), None)
            elif action == "search_tools":
                return (self.search_tools(
                    query=args_dict.get("query", ""),
                    kind=args_dict.get("kind", "any"),
                    include_disabled=bool(args_dict.get("include_disabled", False)),
                    limit=args_dict.get("limit", 12),
                ), None)
            elif action == "system_command":
                cmd = str(args_dict.get("command", ""))
                confirm = args_dict.get("require_approval", False)
                expl = str(args_dict.get("explanation", ""))
                if self._looks_like_permanent_file_delete_command(cmd) and not self._looks_like_temp_cleanup_delete_command(cmd):
                    return ("ERROR: מחיקה קבועה דרך shell חסומה. עבור קבצי משתמש השתמש ב-file_manager action=trash, או בסקריפט שמעביר לסל המחזור באמצעות Windows Recycle Bin API. מחיקת Temp מזוהה מותרת.", None)
                skill_install_target = self._skill_requirement_install_target(cmd)
                if skill_install_target:
                    return (f"ERROR: זוהתה פקודת התקנת דרישות עבור Skill '{skill_install_target}'. יש להשתמש בכלי install_skill_requirements עם name='{skill_install_target}' במקום להריץ התקנה ידנית דרך system_command.", None)
                risk = self._classify_system_command(cmd)
                if risk == "blocked_self_destructive": return (None, "ERROR_USER: [הגנה עצמית]: פקודה הרסנית נחסמה.")
                allowed, err = self._ensure_capability_allowed("shell", "אישור הרצת פקודה", f"פקודה:\n{cmd}\n\nסיווג סיכון: {risk}\nהסבר: {expl}", risk=("high" if risk == "high" or confirm else "medium"))
                if not allowed: return (err, None)
                return (self.run_system_command([cmd], cwd=args_dict.get("cwd", ""), timeout_seconds=args_dict.get("timeout_seconds", None)), None)
                
            elif action == "create_python_tool":
                try:
                    json.loads(str(args_dict.get("description", "")).strip())
                except Exception as e:
                    return (f"ERROR: Tool description must be valid JSON Schema. {e}", None)
                allowed, err = self._ensure_capability_allowed("python_tool_create", "אישור יצירת כלי פייתון", f"שם: {args_dict.get('name', '')}\n\n{args_dict.get('description', '')}", risk="high")
                if not allowed: return (err, None)
                return (self.manage_python_tools(["save", str(args_dict.get("name", "")), args_dict.get("require_approval", False), str(args_dict.get("description", "")), str(args_dict.get("code", ""))]), None)
                
            elif action == "search_mcp":
                allowed, err = self._ensure_capability_allowed("mcp_search", "אישור חיפוש MCP", str(args_dict.get("query", "")), risk="low")
                if not allowed: return (err, None)
                return (self.search_mcp(str(args_dict.get("query", ""))), None)
            elif action == "install_mcp":
                allowed, err = self._ensure_capability_allowed("mcp_install", "אישור התקנת MCP", str(args_dict.get("package", "")), risk="high")
                if not allowed: return (err, None)
                return (self.install_mcp(str(args_dict.get("package", ""))), None)
            elif action == "run_mcp":
                pkg = str(args_dict.get("package", ""))
                func = str(args_dict.get("function", ""))
                mcp_args = args_dict.get("arguments", {})
                if not pkg or not func: return ("ERROR: Missing 'package' or 'function'.", None)
                allowed, err = self._ensure_capability_allowed("mcp_run", "אישור הרצת MCP", f"חבילה: {pkg}\nפונקציה: {func}", risk="high")
                if not allowed: return (err, None)
                
                stem = mcp_pkg_to_file_stem(pkg)
                if not self.settings.get("tools_config", {}).get(f"mcp_{stem}", True):
                    return (f"ERROR: MCP package '{pkg}' is disabled by user. Please inform the user.", None)
                     
                return (self.run_mcp([pkg, func, json.dumps(mcp_args, ensure_ascii=False)]), None)
            elif action == "list_skills":
                return (self.list_skills(), None)
            elif action == "search_skills":
                allowed, err = self._ensure_capability_allowed("skill_search", "אישור חיפוש Skills", str(args_dict.get("query", "")), risk="low")
                if not allowed: return (err, None)
                return (self.search_skills(str(args_dict.get("query", ""))), None)
            elif action == "install_skill":
                source = str(args_dict.get("source", "clawhub"))
                details = f"מקור: {source}\nמזהה: {args_dict.get('id', '')}\nנתיב: {args_dict.get('path', '')}"
                allowed, err = self._ensure_capability_allowed("skill_install", "אישור התקנת Skill", details, risk="high")
                if not allowed: return (err, None)
                return (self.install_skill(source, str(args_dict.get("id", "")), str(args_dict.get("path", ""))), None)
            elif action == "install_skill_requirements":
                name = str(args_dict.get("name", ""))
                details = f"Skill: {name}\nסיבה: {args_dict.get('reason', '')}\n\nפעולה זו עשויה להתקין חבילת CLI או Python חיצונית."
                allowed, err = self._ensure_capability_allowed("skill_install", "אישור התקנת דרישות Skill", details, risk="high")
                if not allowed: return (err, None)
                return (self.install_skill_requirements(name, str(args_dict.get("reason", ""))), None)
            elif action == "load_skill":
                return (self.load_skill(str(args_dict.get("name", "")), str(args_dict.get("task", ""))), None)
            elif action == "run_skill":
                return (self.run_skill(str(args_dict.get("name", "")), args_dict.get("arguments", {}) or {}), None)
            elif action == "read_website":
                allowed, err = self._ensure_capability_allowed("network", "אישור קריאת אתר", str(args_dict.get("url", "")), risk="medium")
                if not allowed: return (err, None)
                return (self.scrape_website(str(args_dict.get("url", "")), args_dict), None)
            elif action == "analyze_local_image":
                allowed, err = self._ensure_cloud_upload_allowed(str(args_dict.get("path", "")))
                if not allowed: return (err, None)
                return (self.read_local_image(str(args_dict.get("path", ""))), None)
            elif action == "schedule_background_task":
                allowed, err = self._ensure_capability_allowed("background_task", "אישור תזמון משימת רקע", f"דחייה: {args_dict.get('delay_minutes', 0)} דקות\n\n{args_dict.get('prompt', '')}", risk="medium")
                if not allowed: return (err, None)
                return (self.schedule_background_task(args_dict), None)
            elif action == "edit_background_task":
                allowed, err = self._ensure_capability_allowed("background_task", "אישור עריכת משימת רקע", f"מזהה: {args_dict.get('id', '')}\n\nשינויים: {args_dict}", risk="medium")
                if not allowed: return (err, None)
                return (self.edit_background_task(args_dict), None)
            elif action == "list_background_tasks": return (self.list_background_tasks(), None)
            elif action == "cancel_background_task": return (self.cancel_background_task(str(args_dict.get("id", ""))), None)
            elif action == "retry_background_task": return (self.retry_background_task(str(args_dict.get("id", "")), args_dict.get("delay_minutes", 0)), None)
            elif action == "notification_manager": return (self.notification_manager(args_dict), None)
            elif action == "open_software":
                allowed, err = self._ensure_capability_allowed("software_open", "אישור פתיחת תוכנה", str(args_dict.get("name", "")), risk="low")
                if not allowed: return (err, None)
                return (self.smart_open_app([str(args_dict.get("name", ""))]), None)
            elif action == "open_file_or_folder":
                path = str(args_dict.get("path", "")).strip(' "\'')
                if not os.path.isabs(path) and ("\\" not in path and "/" not in path):
                    output_candidate = os.path.join(self._sandbox_root() if self._sandbox_enabled() else OUTPUTS_DIR, path)
                    if os.path.exists(output_candidate):
                        path = output_candidate
                if not os.path.exists(path): return (f"ERROR: Not found: {path}", None)
                sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(path, "read")
                if not sandbox_ok: return (sandbox_err, None)
                ext = os.path.splitext(path)[1].lower() if os.path.isfile(path) else ""
                if os.path.isfile(path) and ext in EXECUTABLE_OPEN_EXTENSIONS:
                    return (f"ERROR: פתיחת קובץ מסוג {ext} נחסמה. להרצת תוכנה השתמש ב-open_software או בפקודה מאושרת מפורשת.", None)
                if os.path.isfile(path) and ext and ext not in SAFE_OPEN_EXTENSIONS:
                    allowed, err = self._ensure_capability_allowed("software_run", "אישור פתיחת קובץ לא מוכר", f"נתיב:\n{path}\n\nסיומת לא מוכרת: {ext}", risk="high")
                else:
                    allowed, err = self._ensure_capability_allowed("file_open", "אישור פתיחת קובץ או תיקייה", path, risk="medium")
                if not allowed: return (err, None)
                try:
                    os.startfile(path)
                    return ("SUCCESS: נפתח במסך המשתמש.", None)
                except Exception as e: return (f"ERROR: {e}", None)
            elif action == "list_software":
                return (self._get_installed_apps(
                    query=args_dict.get("query", ""),
                    limit=args_dict.get("limit", 150),
                    refresh=bool(args_dict.get("refresh", False)),
                    include_paths=bool(args_dict.get("include_paths", False)),
                    output_format=args_dict.get("format", "text"),
                ), None)
            elif action == "internet_search":
                allowed, err = self._ensure_capability_allowed("network", "אישור חיפוש אינטרנט", str(args_dict.get("query", "")), risk="medium")
                if not allowed: return (err, None)
                return (self.search_internet(str(args_dict.get("query", ""))), None)
            elif action == "get_weather":
                allowed, err = self._ensure_capability_allowed("network", "אישור בדיקת מזג אוויר", str(args_dict.get("location", "")), risk="medium")
                if not allowed: return (err, None)
                return (self.get_weather_tool(args_dict.get("location", ""), args_dict.get("days", 2), args_dict.get("units", "metric")), None)
            elif action == "smart_file_search": 
                if self.status_callback: self.status_callback("סורק קבצים במחשב...")
                return (self.smart_file_search(str(args_dict.get("query", ""))), None)
            elif action == "deep_content_search": 
                if self.status_callback: self.status_callback("סורק תוכן עמוק...")
                allowed, err = self._ensure_cloud_upload_allowed(str(args_dict.get("directory", "")))
                if not allowed: return (err, None)
                return (self.smart_content_search(str(args_dict.get("directory", "")), str(args_dict.get("text", ""))), None)
            elif action == "capture_screen":
                allowed, err = self._ensure_capability_allowed("screenshot", "אישור צילום מסך", "צילום המסך יישלח למודל כדי להבין את ההקשר.", risk="high")
                if not allowed: return (err, None)
                allowed, err = self._ensure_cloud_upload_allowed("צילום מסך נוכחי")
                if not allowed: return (err, None)
                try:
                    from PIL import ImageGrab
                    path = os.path.join(os.environ['TEMP'], f'vis_{int(time.time())}.png')
                    ImageGrab.grab().save(path)
                    with open(path, "rb") as img: b64 = base64.b64encode(img.read()).decode('utf-8')
                    try: os.remove(path)
                    except: pass
                    return (f"IMAGE_BASE64:image/png:{b64}", None)
                except Exception as e: return (f"ERROR: {e}", None)
            elif action == "save_screenshot_to_disk":
                allowed, err = self._ensure_capability_allowed("screenshot", "אישור צילום מסך", "צילום המסך יישמר כקובץ.", risk="medium")
                if not allowed: return (err, None)
                try:
                    from PIL import ImageGrab
                    base_dir = self._sandbox_root() if self._sandbox_enabled() else self._default_output_dir()
                    path = os.path.join(base_dir, f'Screen_{int(time.time())}.png')
                    allowed, err = self._ensure_write_allowed(path, "שמירת צילום מסך")
                    if not allowed: return (err, None)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    ImageGrab.grab().save(path)
                    return (f"SUCCESS: נשמר ב: {path}", None)
                except Exception as e: return (f"ERROR: {e}", None)
            elif action == "set_volume":
                allowed, err = self._ensure_capability_allowed("audio", "אישור שינוי שמע", str(args_dict.get('action', '')), risk="low")
                if not allowed: return (err, None)
                subprocess.Popen(["powershell", "-Command", f"Set-Volume -Mute {'$true' if str(args_dict.get('action', '')).upper()=='MUTE' else '$false'}"], env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
                return ("SUCCESS: ווליום עודכן.", None)
            elif action == "open_in_browser":
                allowed, err = self._ensure_capability_allowed("browser_open", "אישור פתיחה בדפדפן", str(args_dict.get("query_or_url", "")), risk="low")
                if not allowed: return (err, None)
                return (self.open_direct_website(str(args_dict.get("query_or_url", ""))), None)
            elif action == "get_tool_info":
                return (
                    self.get_tool_info(
                        str(args_dict.get("tool_name", "")),
                        str(args_dict.get("action", "")),
                    ),
                    None,
                )
            elif action == "email_manager":
                email_action = str(args_dict.get("action", "") or "").strip()
                details = json.dumps({k: v for k, v in args_dict.items() if k not in {"body", "html_body"}}, ensure_ascii=False, default=str)[:1200]
                body_preview = str(args_dict.get("body", "") or args_dict.get("html_body", ""))[:500]
                if body_preview:
                    details += f"\n\nBody preview:\n{body_preview}"
                allowed, err = self._ensure_capability_allowed("email", "אישור פעולת אימייל", f"פעולה: {email_action}\n{details}", risk="high")
                if not allowed: return (err, None)
                if email_action in {"search", "read"}:
                    allowed, err = self._ensure_cloud_upload_allowed("תוכן אימיילים")
                    if not allowed: return (err, None)
                return (self.email_manager_tool(args_dict), None)
            elif action == "browser_automation_manager":
                automation_details = json.dumps(args_dict, ensure_ascii=False, default=str)[:1200]
                allowed, err = self._ensure_capability_allowed("browser_automation", "אישור אוטומציית דפדפן", automation_details, risk="high")
                if not allowed: return (err, None)
                return (self.run_browser_action(args_dict), None)
            elif action == "computer_automation_manager":
                automation_details = json.dumps(args_dict, ensure_ascii=False, default=str)[:1200]
                allowed, err = self._ensure_capability_allowed("computer_control", "אישור שליטה במחשב", automation_details, risk="high")
                if not allowed: return (err, None)
                return (self.run_computer_automation(args_dict), None)
            elif action == "save_text_file":
                path = str(args_dict.get("path", "")).strip(' "\'')
                output_root = self._sandbox_root() if self._sandbox_enabled() else self._default_output_dir()
                if not path:
                    path = os.path.join(output_root, f"smarti_output_{int(time.time())}.txt")
                elif not os.path.isabs(path):
                    path = os.path.join(output_root, path)
                ext = os.path.splitext(path)[1].lower()
                if not ext:
                    path += ".txt"
                    ext = ".txt"
                if ext in BLOCKED_WRITE_EXTENSIONS or ext not in SAFE_TEXT_EXTENSIONS:
                    return (f"ERROR: save_text_file מורשה לשמור רק קבצי טקסט בטוחים. סיומת חסומה/לא נתמכת: {ext}", None)
                allowed, err = self._ensure_write_allowed(path, "שמירת קובץ")
                if not allowed: return (err, None)
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f: f.write(str(args_dict.get("content", "")))
                return (f"SUCCESS: נשמר ב: {path}", None)
            elif action == "trash_file_or_folder":
                path = str(args_dict.get("path", "")).strip(' "\'')
                if not path:
                    return ("ERROR: Missing path.", None)
                if not os.path.isabs(path) and ("\\" not in path and "/" not in path):
                    output_candidate = os.path.join(self._sandbox_root() if self._sandbox_enabled() else self._default_output_dir(), path)
                    if os.path.exists(output_candidate):
                        path = output_candidate
                path = self._abs_path(path)
                if not os.path.exists(path):
                    return (f"ERROR: Not found: {path}", None)
                sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(path, "write")
                if not sandbox_ok:
                    return (sandbox_err, None)
                allowed, err = self._ensure_capability_allowed("file_write", "אישור העברה לסל המחזור", f"נתיב:\n{path}\n\nהפעולה תעביר לסל המחזור ולא תמחק לצמיתות.", risk="high")
                if not allowed:
                    return (err, None)
                return (self._move_path_to_recycle_bin(path), None)
            elif action == "read_local_document":
                allowed, err = self._ensure_cloud_upload_allowed(str(args_dict.get("path", "")))
                if not allowed: return (err, None)
                return (self.read_local_document(str(args_dict.get("path", ""))), None)
            elif action == "git_status":
                return (self.git_status_tool(args_dict.get("path", ""), args_dict.get("operation", "status"), args_dict.get("ref", "")), None)
            elif action == "run_project_check":
                allowed, err = self._ensure_capability_allowed("shell", "אישור הרצת בדיקות בפרויקט", f"תיקייה: {args_dict.get('path', '')}\nפקודה: {args_dict.get('command', '')}", risk="medium")
                if not allowed: return (err, None)
                return (self.run_project_check_tool(args_dict.get("path", ""), args_dict.get("command", "")), None)
            elif action == "list_processes":
                return (self.list_processes_tool(), None)
            elif action == "set_clipboard":
                allowed, err = self._ensure_capability_allowed("computer_control", "אישור העתקה ללוח", str(args_dict.get("text", ""))[:500], risk="medium")
                if not allowed: return (err, None)
                return (self.set_clipboard_tool(args_dict.get("text", "")), None)
            elif action == "extract_image_text":
                allowed, err = self._ensure_cloud_upload_allowed(str(args_dict.get("path", "")))
                if not allowed: return (err, None)
                return (self.extract_image_text_tool(args_dict.get("path", "")), None)
            elif action == "search_memory":
                return (self.search_memory_tool(args_dict.get("query", ""), args_dict.get("memory_type", "any"), args_dict.get("max_results", 6)), None)
            elif action == "memory_operation":
                operation = str(args_dict.get("action", "")).strip().lower()
                read_actions = {"list", "get", "stats"}
                if operation not in read_actions:
                    if operation in {"export", "import"}:
                        path = self._abs_path(str(args_dict.get("path", "")))
                        access = "write" if operation == "export" else "read"
                        sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(path, access)
                        if not sandbox_ok:
                            return (sandbox_err, None)
                        args_dict["path"] = path
                    detail = f"פעולת זיכרון: {operation}"
                    if args_dict.get("memory_id"):
                        detail += f"\nמזהה: {args_dict.get('memory_id')}"
                    if args_dict.get("subject"):
                        detail += f"\nנושא: {str(args_dict.get('subject'))[:160]}"
                    if args_dict.get("path"):
                        detail += f"\nנתיב: {args_dict.get('path')}"
                    risk = "high" if operation in {"clear", "forget", "import"} else "medium"
                    allowed, err = self._ensure_capability_allowed(
                        "file_write", "אישור ניהול זיכרון", detail, risk=risk
                    )
                    if not allowed:
                        return (err, None)
                return (self.memory_manager_tool(operation, args_dict), None)
            elif action == "update_memory":
                allowed, err = self._ensure_capability_allowed("file_write", "אישור עדכון זיכרון", str(args_dict.get("content", ""))[:800], risk="medium")
                if not allowed: return (err, None)
                return (self.update_memory_tool(
                    str(args_dict.get("mode", "")),
                    str(args_dict.get("content", "")),
                    memory_type=args_dict.get("memory_type", "long_term"),
                    subject=args_dict.get("subject", ""),
                    ttl_hours=args_dict.get("ttl_hours", None),
                    importance=args_dict.get("importance", 3),
                    tags=args_dict.get("tags", []),
                    memory_id=args_dict.get("memory_id", ""),
                ), None)

        if os.path.exists(os.path.join(TOOLS_DIR, f"{action}.pyw")):
            if self._sandbox_enabled():
                return ("ERROR: ארגז חול פעיל. כלי מותאם אישית חסום כי אי אפשר להגביל אותו בוודאות לתיקיית ארגז החול.", None)
            if self.settings.get("external_code_requires_trust", True) and getattr(self, "tool_registry", None) and not self.tool_registry.is_trusted("custom", action):
                return (f"ERROR: Custom tool '{action}' is not trusted yet. אשר אותו במסך הכלים לפני הרצה.", None)
            allowed, err = self._ensure_capability_allowed("python_tool_run", "אישור הרצת כלי פייתון", action, risk="medium")
            if not allowed: return (err, None)
            return (self.manage_python_tools(["run", action, False, "", json.dumps(args_dict, ensure_ascii=False)]), None)

        return (f"ERROR: Tool '{action}' not found. Did you forget to use get_tool_info or check the tool name?", None)
