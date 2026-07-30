"""MCP config, SSL/network helpers, command classification, status text, and cancellation recovery."""
from .shared import *


class RuntimeServicesMixin:
    def _ensure_mcp_config(self):
        allowed = self._get_mcp_allowed_dirs()
        try:
            with open(MCP_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "allowed_directories": allowed,
                    "trusted_packages": self.settings.get("allowed_mcp_packages", []),
                    "package_configs": self.settings.get("mcp_package_configs", {}),
                    "note": "MCP roots are coordination hints for external tools, not Smarti write permissions. Smarti still enforces local policy before install/run."
                }, f, ensure_ascii=False, indent=2)
        except Exception as e: logging.error(f"Failed to write MCP config: {e}")

    def _get_mcp_allowed_dirs(self):
        if self._sandbox_enabled():
            root = self._sandbox_root()
            return [root] if os.path.exists(root) else []
        configured = self.settings.get("mcp_allowed_directories") or [APP_DIR]
        allowed = []
        for path in configured:
            try:
                resolved = self._abs_path(path)
                if os.path.exists(resolved): allowed.append(resolved)
            except Exception: pass
        return allowed or [APP_DIR]

    def _ssl_settings_snapshot(self):
        snapshot = {
            key: copy.deepcopy((self.settings or {}).get(key))
            for key in (
                "ssl_trust_mode",
                "ssl_custom_ca_path",
                "ssl_filter_setup_completed",
                "ssl_legacy_insecure_allowed_hosts",
                "ssl_trust_migration_version",
                "allow_insecure_ssl_compat",
            )
        }
        snapshot["_ssl_legacy_insecure_session_enabled"] = bool(
            getattr(self, "_ssl_legacy_insecure_session_enabled", False)
        )
        snapshot["_ssl_data_dir"] = USER_DATA_DIR
        return snapshot

    def _ssl_trust_mode(self):
        return normalize_ssl_trust_mode(self.settings.get("ssl_trust_mode"))

    def _allow_insecure_ssl(self, url_or_host=""):
        """Compatibility name for the explicit global verification bypass."""
        return self._ssl_trust_mode() == SSL_MODE_LEGACY_INSECURE

    def _set_legacy_ssl_session_enabled(self, enabled):
        # Kept as a compatibility method for older UI/extensions. The selected
        # mode itself is now persistent and global, exactly like Smarti's
        # historical SSL compatibility switch.
        self._ssl_legacy_insecure_session_enabled = (
            self._ssl_trust_mode() == SSL_MODE_LEGACY_INSECURE
        )
        self._sync_ssl_compat_env()
        return self._ssl_legacy_insecure_session_enabled

    def _add_ssl_sitecustomize_path(self, env):
        existing = env.get("PYTHONPATH", "")
        parts = [p for p in str(existing).split(os.pathsep) if p]
        for support_dir in reversed(SMARTI_RUNTIME.python_support_dirs()):
            support_norm = os.path.normcase(os.path.abspath(support_dir))
            if not any(os.path.normcase(os.path.abspath(p)) == support_norm for p in parts):
                parts.insert(0, support_dir)
        env["PYTHONPATH"] = os.pathsep.join(parts)
        return env

    def _sync_ssl_compat_env(self, env=None):
        target = os.environ if env is None else dict(env)
        apply_ssl_trust_environment(
            self._ssl_settings_snapshot(),
            target,
            data_dir=USER_DATA_DIR,
        )
        if env is None:
            configure_ssl_from_environment()
        self._add_ssl_sitecustomize_path(target)
        return target

    def _subprocess_env(self, env=None):
        target = SMARTI_RUNTIME.subprocess_env(env)
        target.setdefault("PYTHONIOENCODING", "utf-8")
        target.setdefault("PYTHONUTF8", "1")
        return self._sync_ssl_compat_env(target)

    def _ssl_request_kwargs(self, url="", *, allow_legacy=True):
        self._sync_ssl_compat_env()
        return ssl_request_kwargs(
            self._ssl_settings_snapshot(),
            url=url,
            allow_legacy=allow_legacy,
            data_dir=USER_DATA_DIR,
        )

    def _with_ssl_request_kwargs(self, url, kwargs, *, allow_legacy=True):
        merged = dict(kwargs or {})
        merged.update(self._ssl_request_kwargs(url, allow_legacy=allow_legacy))
        return merged

    def _request_get(self, url, **kwargs):
        return requests.get(url, **self._with_ssl_request_kwargs(url, kwargs))

    def _request_post(self, url, **kwargs):
        return requests.post(url, **self._with_ssl_request_kwargs(url, kwargs))

    def _ssl_context(self, url="", *, allow_legacy=True):
        self._sync_ssl_compat_env()
        return create_ssl_context(
            self._ssl_settings_snapshot(),
            url=url,
            data_dir=USER_DATA_DIR,
            allow_legacy=allow_legacy,
        )

    def _network_auto_resume_enabled(self):
        return bool(self.settings.get("network_auto_resume_enabled", True))

    def _network_probe_available(self):
        probe_urls = (
            "https://www.gstatic.com/generate_204",
            "https://api.github.com",
        )
        for url in probe_urls:
            try:
                response = self._request_get(url, timeout=5)
                if getattr(response, "status_code", 599) < 500:
                    return True
            except requests.exceptions.SSLError:
                return True
            except Exception:
                pass
        try:
            with socket.create_connection(("1.1.1.1", 53), timeout=3):
                return True
        except Exception:
            return False

    def _wait_for_network_reconnect(self, analysis=None):
        if not self._network_auto_resume_enabled():
            return False
        try:
            minutes = int(self.settings.get("network_reconnect_wait_minutes", 180) or 180)
        except Exception:
            minutes = 180
        max_wait = max(1, minutes) * 60
        deadline = time.time() + max_wait
        label = getattr(analysis, "provider_label", "") or self._provider_display_name(getattr(self, "mode", ""))
        while time.time() < deadline:
            self._raise_if_cancelled()
            if self._network_probe_available():
                if self.status_callback:
                    self.status_callback(f"{label}: החיבור חזר, ממשיך אוטומטית...")
                return True
            remaining_minutes = max(1, int((deadline - time.time() + 59) // 60))
            if self.status_callback:
                self.status_callback(f"{label}: החיבור לרשת נותק. ממתין לחיבור מחדש ({remaining_minutes} דק׳)...")
            if not self._sleep_with_cancel(10):
                raise SmartiCancelled("CANCELLED_BY_USER")
        return False

    def _friendly_ssl_error(self, error):
        self._ssl_last_certificate_error = str(error or "")[:600]
        mode = self._ssl_trust_mode()
        if mode == SSL_MODE_CUSTOM_CA:
            return (
                "אימות תעודת ה-HTTPS נכשל גם עם תעודת הסינון שנבחרה. "
                "יש לפתוח הגדרות ← מתקדם ← אמון HTTPS, לבדוק שהתעודה בתוקף ולהריץ בדיקת חיבור מאומתת. "
                "Smarti לא עבר למצב לא מאובטח."
            )
        if mode == SSL_MODE_LEGACY_INSECURE:
            return (
                "חיבור ה-HTTPS נכשל גם כאשר התאימות הישנה ללא אימות תעודות פעילה. "
                "במצב זה אימות זהות השרת כבר כבוי, ולכן הסיבה כנראה היא חסימת רשת, "
                "פרוקסי שאינו זמין או תקלה זמנית בשירות."
            )
        return (
            "אימות תעודת ה-HTTPS נכשל. Smarti משתמש במאגר האישורים של Windows ולא החליש את האימות. "
            "אם פועל סינון רשת, יש לפתוח הגדרות ← מתקדם ← אמון HTTPS ולייבא את תעודת השורש "
            "הציבורית של ספק הסינון או לבדוק שהיא מותקנת ב-Windows."
        )

    def _mcp_env(self):
        allowlist = self.settings.get("mcp_env_allowlist") or DEFAULT_MCP_ENV_ALLOWLIST
        env = {}
        for key in allowlist:
            if key in os.environ:
                env[key] = os.environ[key]
        if "PATH" not in env and "Path" not in env:
            env["PATH"] = os.environ.get("PATH", os.environ.get("Path", ""))
        if self._sandbox_enabled():
            env["SMARTI_SANDBOX_ROOT"] = self._sandbox_root()
            env["SMARTI_SANDBOX_READ_OUTSIDE"] = "1" if self.settings.get("sandbox_allow_read_outside", False) else "0"
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env = SMARTI_RUNTIME.subprocess_env(env)
        return self._sync_ssl_compat_env(env)

    def _mcp_launch_args(self, pkg_name):
        configs = self.settings.get("mcp_package_configs", {})
        config = configs.get(pkg_name, {}) or configs.get(mcp_pkg_to_file_stem(pkg_name), {})
        args = config.get("server_args", []) if isinstance(config, dict) else []
        return args if isinstance(args, list) else []

    def _classify_system_command(self, cmd):
        cmd = str(cmd or "").strip()
        cmd_lower = f" {cmd.lower()} "
        if re.search(r'(&&|\|\||`|\$\(|\bstart-job\b|\bstart-process\b)', cmd_lower):
            return "high"
        if ";" in cmd and not re.match(r'^\s*git\s+(?:status|log|show|diff)\b', cmd, flags=re.IGNORECASE):
            return "high"
        destructive = any(hint in cmd_lower for hint in DESTRUCTIVE_COMMAND_HINTS)
        self_targeted = any(name in cmd_lower for name in SELF_PROTECTED_NAMES)
        if destructive and self_targeted:
            return "blocked_self_destructive"

        blocked_tokens = [
            "-encodedcommand", "frombase64string", "invoke-expression", " iex ", "add-type",
            "start-process", "new-service", "schtasks", "reg add", "reg delete",
            "set-executionpolicy", "downloadstring", "downloadfile", "bitsadmin",
            "certutil", "mshta", "wscript", "cscript", "rundll32", "powershell -",
            "pwsh -", "cmd /c", "cmd.exe", "python -c", "python.exe -c",
            "node -e", "npm install", "npm i ", "pip install", "pipx install"
        ]
        if destructive or any(token in cmd_lower for token in blocked_tokens):
            return "high"
        if re.search(r'(^|[\s;|&])(?:curl|wget|irm|iwr|invoke-webrequest)\b', cmd_lower):
            return "high"
        if re.search(r'(>|>>|\|\s*(?:set-content|out-file|add-content|remove-item|del|erase|move-item|copy-item)\b)', cmd_lower):
            return "high"

        alias_map = {
            "ls": "get-childitem", "dir": "get-childitem", "gci": "get-childitem",
            "cat": "get-content", "type": "get-content", "gc": "get-content",
            "pwd": "get-location", "ps": "get-process", "sls": "select-string"
        }
        read_only = {
            "get-childitem", "get-content", "select-string", "get-location", "get-process",
            "get-date", "get-command", "get-item", "get-itemproperty", "test-path", "resolve-path",
            "whoami", "hostname", "ipconfig", "tasklist", "where", "where.exe", "findstr",
            "rg", "rg.exe", "git", "python", "python.exe", "node", "node.exe", "npm", "npm.cmd"
        }
        segments = [seg.strip() for seg in re.split(r'\|', cmd) if seg.strip()]
        for seg in segments:
            token_match = re.match(r'^(?:&\s*)?([A-Za-z0-9_.\\:-]+)', seg)
            if not token_match:
                return "high"
            token = os.path.basename(token_match.group(1)).lower()
            token = alias_map.get(token, token)
            if token not in read_only:
                return "high"
            seg_l = seg.lower().strip()
            if token == "git" and not re.match(r'^git\s+(?:status|log|show|diff)(?:\s+[-\w./:=]+)*\s*$', seg_l):
                return "high"
            if token in {"python", "python.exe"} and not re.match(r'^(?:python|python\.exe)\s+(?:--version|-v|-V)\s*$', seg_l):
                return "high"
            if token in {"node", "node.exe"} and not re.match(r'^(?:node|node\.exe)\s+(?:--version|-v)\s*$', seg_l):
                return "high"
            if token in {"npm", "npm.cmd"} and not re.match(r'^(?:npm|npm\.cmd)\s+(?:--version|-v)\s*$', seg_l):
                return "high"
        return "low"

    def _normalize_step_text(self, text):
        raw = (text or "").replace("##", "").strip()
        if not raw:
            return ""
        raw = re.sub(r'```.*?```', '', raw, flags=re.DOTALL).strip()
        lines = [ln.strip(" \t-–:") for ln in raw.splitlines() if ln.strip()]
        if not lines:
            return ""

        candidate = ""
        for line in reversed(lines):
            stripped = re.sub(r'^(סטטוס|שלב|פעולה)\s*[:：]\s*', '', line, flags=re.IGNORECASE).strip()
            if stripped and stripped != line:
                candidate = stripped
                break
        if not candidate:
            candidate = lines[-1].strip()
            candidate = re.sub(r'^(סטטוס|שלב|פעולה)\s*[:：]\s*', '', candidate, flags=re.IGNORECASE).strip()

        candidate = candidate.strip(" .:()[]")
        candidate = re.sub(r'\s+', ' ', candidate).strip()
        candidate = re.split(r'\s+(?:כדי|בשביל|לצורך|לשם|במטרה|על מנת)\b', candidate, maxsplit=1)[0].strip()
        candidate = re.split(r'\s+(?:ואז|ולאחר מכן|ואחר כך|לאחר מכן|אחר כך)\b', candidate, maxsplit=1)[0].strip()
        candidate = re.split(
            r'[,;]\s*(?:ו?רשימת|ו?כתיבת|ו?סיכום|ו?שמירת|ו?יצירת|ו?בדיקת|ו?קריאת|ו?שליפת|ו?חיפוש|ו?איתור|ו?הרצת)\b',
            candidate,
            maxsplit=1,
        )[0].strip()
        candidate = re.split(
            r'\s+ו(?:לסכם|לכתוב|לשמור|ליצור|לבנות|לתקן|לשלוח|לפתוח|להדביק|להחזיר|לאמת|להכין|לעדכן|להמשיך|להמיר|לנתח)\b',
            candidate,
            maxsplit=1,
        )[0].strip()
        candidate = re.split(
            r'\s+ו(?:סיכום|כתיבת|שמירת|יצירת|בניית|תיקון|שליחת|פתיחת|הדבקת|החזרת|אימות|הכנת|עדכון|המרת|ניתוח)\b',
            candidate,
            maxsplit=1,
        )[0].strip()
        candidate = re.split(
            r'\s+ל(?:וודא|וודא|ווידא|וידוא|ווידוא|וידוי|ווידוי|אמת|סכם|כתוב|שמור|יצור|צור|שלוח|פתוח|הכין|עדכן|המיר|נתח)\b',
            candidate,
            maxsplit=1,
        )[0].strip()
        candidate = re.sub(r'\bשליפת\s+(?:אימייל|מייל)\s+אחרון\b', "שליפת האימייל האחרון", candidate)
        candidate = re.sub(r'\bקריאת\s+(?:אימייל|מייל)\s+אחרון\b', "קריאת האימייל האחרון", candidate)
        candidate = candidate.strip(" .:()[]")
        bad_fragments = [
            "שלום", "תודה", "סליחה", "אני סמארטי", "איך אוכל לעזור",
            "כעת כשאני", "כעת כשה", "האם תרצה", "המתן", "עבורך",
            "מזג האוויר", "התוצאה היא"
        ]
        action_step_prefixes = (
            "בודק", "מחפש", "מאתר", "קורא", "מריץ", "מפעיל", "שומר", "פותח", "טוען", "מתקין", "יוצר",
            "מתכנן", "מעריך", "מאמת", "מעדכן", "מכין", "שולף",
            "בדיקת", "חיפוש", "איתור", "קריאת", "שליפת", "שמירת", "יצירת", "פתיחת", "הרצת", "אימות", "תכנון", "הערכת"
        )
        if any(fragment in candidate for fragment in bad_fragments) and not candidate.startswith(action_step_prefixes):
            return ""
        if len(candidate) > 95 or len(candidate.split()) > 9:
            return ""
        return candidate

    def _short_step_value(self, value, limit=32):
        text = str(value or "").strip()
        text = re.sub(r'[\r\n\t{}\[\]"`]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip(" .,:;")
        if len(text) > limit:
            text = text[:limit].rstrip() + "..."
        return text

    def _fallback_step_for_tool(self, action, args_dict, schema_check=False):
        action = str(action or "").strip()
        args = args_dict if isinstance(args_dict, dict) else {}
        if not action:
            return ""

        tool_name = self._short_step_value(
            args.get("tool_name") or args.get("name") or args.get("tool") or
            args.get("function") or args.get("function_name")
        )
        package_name = self._short_step_value(
            args.get("package") or args.get("pkg") or args.get("package_name") or args.get("server")
        )
        target = self._short_step_value(
            args.get("location") or args.get("path") or args.get("url") or
            args.get("query") or args.get("filename") or args.get("app")
        )

        if schema_check:
            return f"בודק סכמת {package_name or tool_name or action}"
        if action == "system_manager":
            manager_op = str(args.get("action") or "").strip()
            if manager_op == "git_status":
                return "בודק מצב Git"
            if manager_op == "list_processes":
                return "בודק תהליכים פעילים"
            if manager_op == "run_project_check":
                return "מריץ בדיקת פרויקט"
            if manager_op == "set_clipboard":
                return "מעדכן את הלוח"
            if manager_op == "set_volume":
                return "מעדכן עוצמת שמע"
            return "מריץ פקודת מערכת" if manager_op == "run_command" else "מפעיל כלי מערכת"
        if action == "file_manager":
            manager_op = str(args.get("action") or "").strip()
            if manager_op == "save_text":
                return f"שומר {target}" if target else "שומר קובץ טקסט"
            if manager_op == "read_document":
                return f"קורא {target}" if target else "קורא קובץ"
            if manager_op == "search_files":
                return f"מחפש {target}" if target else "מחפש קבצים"
            if manager_op == "search_content":
                return "מחפש בתוך קבצים"
            if manager_op == "extract_image_text":
                return "מחלץ טקסט מתמונה"
            if manager_op == "open":
                return f"פותח {target}" if target else "פותח קובץ"
            if manager_op in {"trash", "recycle", "delete", "remove"}:
                return f"מעביר לסל המחזור {target}" if target else "מעביר לסל המחזור"
            return "מפעיל כלי קבצים"
        if action == "web_manager":
            manager_op = str(args.get("action") or "").strip()
            if manager_op == "search":
                return "מחפש מידע עדכני"
            if manager_op == "read":
                if str(args.get("mode") or "").strip().lower() == "crawl":
                    return f"סורק אתר {target}" if target else "סורק אתר"
                return f"קורא אתר {target}" if target else "קורא אתר"
            if manager_op == "open":
                return f"פותח {target}" if target else "פותח דפדפן"
            if manager_op == "weather":
                return f"שולף תחזית עבור {target}" if target else "שולף תחזית מזג אוויר"
            return "מפעיל כלי רשת"
        if action == "screen_manager":
            manager_op = str(args.get("action") or "").strip()
            if manager_op == "capture":
                return "מצלם את המסך"
            if manager_op == "save_screenshot":
                return "שומר צילום מסך"
            if manager_op == "analyze_image":
                return "מנתח תמונה"
            return "מפעיל כלי מסך"
        if action == "email_manager":
            email_op = str(args.get("action") or "").strip()
            if email_op == "list_folders":
                return "בודק תיקיות אימייל"
            if email_op == "search":
                if args.get("count") == 1 and not any(args.get(k) for k in ("query", "from", "subject_filter", "to_filter")):
                    return "שליפת האימייל האחרון"
                return "מחפש אימיילים"
            if email_op == "read":
                return "קורא אימייל"
            if email_op in {"send", "reply", "forward"}:
                return "מכין שליחת אימייל"
            if email_op == "draft":
                return "שומר טיוטת אימייל"
            if email_op in {"mark_read", "mark_unread", "star", "unstar"}:
                return "מעדכן סימון אימייל"
            if email_op in {"archive", "trash", "delete", "move", "copy"}:
                return "מעדכן מיקום אימייל"
            if email_op == "save_attachments":
                return "שומר קבצים מצורפים"
            return "מפעיל כלי אימייל"
        if action == "background_task_manager":
            manager_op = str(args.get("action") or "").strip()
            if manager_op == "schedule":
                return "מתזמן משימה"
            if manager_op == "list":
                return "בודק משימות רקע"
            if manager_op == "cancel":
                return "מבטל משימת רקע"
            if manager_op == "retry":
                return "מריץ משימה מחדש"
            return "מפעיל משימת רקע"
        if action == "notification_manager":
            manager_op = str(args.get("action") or "").strip()
            if manager_op == "schedule_reminder":
                return "מתזמן תזכורת"
            if manager_op == "send_toast":
                return "שולח התראה"
            if manager_op == "create_calendar_event":
                return "יוצר אירוע ליומן"
            if manager_op == "open_windows_app":
                return "פותח כלי זמן של Windows"
            return "מנהל התראות ותזכורות"
        if action == "memory_manager":
            return "מחפש בזיכרון" if str(args.get("action") or "") == "search" else "מעדכן זיכרון"
        if action == "agent_planner":
            return "מתכנן את שלבי המשימה"
        if action in {"software_manager", "extension_manager"}:
            manager_op = self._short_step_value(args.get("action") or args.get("target") or "", 24)
            return f"מפעיל {self._short_step_value(action.replace('_', ' '), 30)} {manager_op}".strip()
        if action == "get_tool_info":
            return f"בודק סכמת {tool_name or 'כלי'}"
        if action == "get_weather":
            return f"שולף תחזית עבור {target}" if target else "שולף תחזית מזג אוויר"
        if action == "trash_file_or_folder":
            return f"מעביר לסל המחזור {target}" if target else "מעביר לסל המחזור"
        if action == "run_mcp":
            return f"מריץ MCP: {tool_name or package_name}" if (tool_name or package_name) else "מריץ כלי MCP"
        if action == "internet_search":
            return "מחפש מידע עדכני"
        if action == "read_website":
            if str(args.get("mode") or "").strip().lower() == "crawl":
                return f"סורק אתר {target}" if target else "סורק אתר"
            return f"קורא אתר {target}" if target else "קורא אתר"
        if action == "browser_automation_manager":
            return ""
        if action == "computer_automation_manager":
            return ""
        if action == "open_software":
            return f"פותח {target}" if target else "פותח תוכנה"
        if action == "open_file_or_folder":
            return f"פותח {target}" if target else "פותח קובץ או תיקיה"
        if action == "open_in_browser":
            return f"פותח {target}" if target else "פותח קישור בדפדפן"
        if action == "save_text_file":
            return f"שומר {target}" if target else "שומר קובץ טקסט"
        if action == "create_python_tool":
            return f"יוצר כלי {tool_name}" if tool_name else "יוצר כלי Python"
        if action == "run_skill":
            return f"מריץ Skill: {tool_name}" if tool_name else "מריץ Skill"
        if action == "install_skill":
            return f"מתקין Skill: {tool_name}" if tool_name else "מתקין Skill"
        if action == "install_mcp":
            return f"מתקין MCP: {package_name or tool_name or target}" if (package_name or tool_name or target) else "מתקין MCP"

        display_action = self._short_step_value(action.replace("_", " "), 36)
        return f"מפעיל {display_action}"

    def request_cancel(self):
        self.cancel_event.set()
        if self._foreground_cancel_event:
            self._foreground_cancel_event.set()
        self._terminate_active_processes()

    def _recover_after_agent_crash(self):
        self._foreground_cancel_event = None
        self.cancel_event.clear()
        try:
            self._execution_context.is_background = False
            if hasattr(self._execution_context, "loop_iteration"):
                delattr(self._execution_context, "loop_iteration")
            if hasattr(self._execution_context, "policy_snapshot"):
                delattr(self._execution_context, "policy_snapshot")
        except Exception:
            pass
        try:
            self._agent_lock.release()
            logging.warning("Recovered agent lock after an unexpected worker crash.")
        except RuntimeError:
            pass
