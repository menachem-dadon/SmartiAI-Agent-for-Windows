"""Internet search, local search, app/web opening, reminders, notifications, background task public APIs, and memory tools."""
from .shared import *


class ProductivityToolsMixin:
    def search_internet(self, query):
        api = self._ensure_secret_loaded("tavily_api_key")
        if not api:
            if not self._ensure_api_key_available(
                "tavily_api_key",
                "Tavily",
                title="חסר מפתח API של Tavily",
                message="סמארטי מנסה לבצע חיפוש אינטרנט דרך Tavily, אבל לא נשמר מפתח API של Tavily. הזן מפתח כדי להמשיך את החיפוש.",
                help_url=self._api_key_help_url("tavily_api_key", "tavily"),
            ):
                return "ERROR_USER: חסר מפתח API של Tavily. הזן מפתח Tavily כדי להשתמש בחיפוש האינטרנט."
            api = self._ensure_secret_loaded("tavily_api_key")
        try:
            payload = {"query": query, "include_answer": "advanced"}
            headers = {"Authorization": f"Bearer {api}", "Content-Type": "application/json"}
            res = self._run_cancelable_callable(lambda: self._request_post(get_url(URL_TAVILY), json=payload, headers=headers, timeout=20))
            if res.status_code in {400, 401, 403}:
                legacy_payload = dict(payload)
                legacy_payload["api_key"] = api
                legacy_res = self._run_cancelable_callable(lambda: self._request_post(get_url(URL_TAVILY), json=legacy_payload, timeout=20))
                if legacy_res.status_code < 400 or res.status_code in {401, 403}:
                    res = legacy_res
            res.raise_for_status()
            d = res.json()
            urls = [str(r.get("url") or "") for r in d.get("results", []) if isinstance(r, dict) and r.get("url")]
            return "[UNTRUSTED_WEB_CONTENT]\n" + str(d.get("answer", "")) + "\nURLs:\n" + "\n".join(urls)
        except SmartiCancelled:
            raise
        except Exception as e: return f"Error: {e}"

    def smart_file_search(self, query):
        query_terms = [t.lower() for t in query.replace('"', '').replace("'", "").split()]
        if not query_terms: return "ERROR: Empty query."
        found_files = []
        skip_dirs = {'appdata', 'windows', 'program files', 'program files (x86)', 'node_modules', '.git', '.idea', '.vscode', 'venv', 'env', '__pycache__', 'site-packages', 'temp', '$recycle.bin', 'system volume information', 'build', 'dist', '.cache', '.nuget', '.cargo', 'perflogs', 'programdata', 'windows.old', 'recovery'}
        user_profile = os.environ.get('USERPROFILE', '')
        sandbox_only = self._sandbox_enabled() and not self.settings.get("sandbox_allow_read_outside", False)

        def scan_dir(target_dir, skip_paths):
            sandbox_ok, _ = self._ensure_sandbox_path_allowed(target_dir, "read")
            if not sandbox_ok:
                return False
            try:
                for root, dirs, files in os.walk(target_dir):
                    self._raise_if_cancelled()
                    dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith('.') and os.path.join(root, d) not in skip_paths]
                    for file in files:
                        self._raise_if_cancelled()
                        if all(term in file.lower() for term in query_terms):
                            found_files.append(os.path.join(root, file))
                            if len(found_files) >= 50: return True 
            except SmartiCancelled:
                raise
            except: pass
            return False

        reached_limit = False
        scanned_roots = set()

        if sandbox_only:
            root = self._sandbox_root()
            if not os.path.isdir(root):
                return "ERROR: ארגז החול פעיל, אך תיקיית ארגז החול אינה קיימת."
            scan_dir(root, skip_paths=scanned_roots)
            scanned_roots.add(root)
            reached_limit = True
        
        if not reached_limit and user_profile and os.path.exists(user_profile):
            for folder in ['Desktop', 'Documents', 'Downloads', 'Pictures', 'Music', 'Videos']:
                folder_path = os.path.join(user_profile, folder)
                if os.path.exists(folder_path):
                    if scan_dir(folder_path, skip_paths=scanned_roots):
                        reached_limit = True
                        break
                    scanned_roots.add(folder_path)

        if not reached_limit and len(found_files) < 50 and user_profile and os.path.exists(user_profile):
            reached_limit = scan_dir(user_profile, skip_paths=scanned_roots)
            scanned_roots.add(user_profile)

        if not reached_limit and len(found_files) < 50:
            for d in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
                drive = f"{d}:\\"
                if os.path.exists(drive):
                    if scan_dir(drive, skip_paths=scanned_roots): break

        if not found_files: return f"לא נמצאו קבצים העונים לשם: {query}"
        found_files.sort(key=lambda x: len(os.path.basename(x)))
        return "תוצאות חיפוש שמות קבצים:\n" + "\n".join(found_files[:30])

    def smart_content_search(self, target_dir, text_query):
        found = []
        target_dir = target_dir.strip(' "\'')
        if not os.path.exists(target_dir): target_dir = os.environ.get('USERPROFILE', 'C:\\')
        sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(target_dir, "read")
        if not sandbox_ok: return sandbox_err
        valid_ext = {'.txt', '.csv', '.md', '.py', '.json', '.log', '.ini', '.xml', '.html'}
        text_query_lower = text_query.lower().strip(' "\'')
        if not text_query_lower: return "ERROR: Empty query."
        count = 0
        skip_dirs = {'node_modules', '.git', 'temp', '$recycle.bin', 'appdata', '.idea', '.vscode', 'venv', 'env', '__pycache__', 'build', 'dist', '.cache', 'windows', 'program files', 'program files (x86)', 'programdata', 'windows.old'}

        for root, dirs, files in os.walk(target_dir):
            self._raise_if_cancelled()
            dirs[:] = [d for d in dirs if not d.startswith('.') and d.lower() not in skip_dirs]
            for f in files:
                self._raise_if_cancelled()
                if os.path.splitext(f)[1].lower() in valid_ext:
                    path = os.path.join(root, f)
                    try:
                        with open(path, 'r', encoding='utf-8') as file_obj:
                            content = file_obj.read(500000) 
                            if text_query_lower in content.lower():
                                idx = content.lower().find(text_query_lower)
                                start = max(0, idx - 40)
                                end = min(len(content), idx + len(text_query) + 40)
                                found.append(f"נמצא בקובץ: {path}\nהקשר: ...{content[start:end].replace(chr(10), ' ')}...")
                                count += 1
                    except: pass
            if count >= 15: break

        if not found: return f"לא נמצא '{text_query}' בתיקייה: {target_dir}"
        return "תוצאות סריקת טקסט:\n" + "\n\n".join(found)

    def smart_open_app(self, params):
        query = str(params[0] if params else "").strip()
        if not query:
            return "ERROR: Missing software name."

        direct_path = self._abs_path(query) if re.match(r"^[A-Za-z]:\\|^\\\\|^[~%]", query) else ""
        if direct_path and os.path.exists(direct_path):
            ext = os.path.splitext(direct_path)[1].lower()
            if ext and ext not in EXECUTABLE_OPEN_EXTENSIONS and ext != ".exe":
                return "ERROR: software_manager opens applications only. Use file_manager action=open for files/folders."
            subprocess.Popen([direct_path], env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            return f"SUCCESS: Opened application path: {direct_path}"

        resolved = shutil.which(query)
        if resolved:
            subprocess.Popen([resolved], env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            return f"SUCCESS: Opened command: {resolved}"

        matches = self._find_software_matches(query, limit=8, refresh=False)
        if not matches:
            matches = self._find_software_matches(query, limit=8, refresh=True)
        if not matches:
            return f"ERROR: Software not found: {query}. Use software_manager action=list to inspect installed apps."

        best = matches[0]
        if float(best.get("score", 1.0)) < 0.55:
            suggestions = ", ".join(item["name"] for item in matches[:6])
            return f"ERROR: No confident app match for '{query}'. Closest matches: {suggestions}"

        launch = best.get("launch", "")
        launch_type = best.get("launch_type", "path")
        try:
            if launch_type == "appx":
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{launch}"], env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            elif launch_type == "shortcut" or launch.lower().endswith(".lnk"):
                subprocess.Popen(["explorer.exe", launch], env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            else:
                subprocess.Popen([launch], env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
            return f"SUCCESS: Opened {best.get('name')} via {best.get('source')}."
        except Exception as e:
            suggestions = ", ".join(item["name"] for item in matches[:6])
            return f"ERROR: Failed to open {best.get('name')}: {e}. Matches: {suggestions}"

    def open_direct_website(self, query):
        query = query.strip()
        is_url = query.startswith("http") or query.startswith("www.") or ('.' in query and ' ' not in query)
        if is_url:
            url = query if query.startswith("http") else "https" + f"://{query}"
            if urllib.parse.urlparse(url).scheme not in {"http", "https"}: return "ERROR: Invalid URL."
            if self.settings.get("enable_browser_automation", False):
                return self._open_in_automation_browser(url)
            webbrowser.open(url)
            return f"האתר נפתח."
        search_url = get_url(URL_DDG) + urllib.parse.quote(query)
        if self.settings.get("enable_browser_automation", False):
            return self._open_in_automation_browser(search_url)
        webbrowser.open(search_url)
        return f"בוצע חיפוש."

    def schedule_background_task(self, params):
        try:
            if isinstance(params, dict):
                args_dict = params
            else:
                args_dict = {
                    "delay_minutes": params[0] if len(params) > 0 else 0,
                    "prompt": params[1] if len(params) > 1 else "",
                    "repeat": params[2] if len(params) > 2 else "once",
                    "interval_minutes": params[3] if len(params) > 3 else ""
                }
            
            delay = float(args_dict.get("delay_minutes") or 0)
            if delay < 0: return "ERROR: Delay must be positive."
            
            repeat = str(args_dict.get("repeat") or "once").strip().lower()
            if repeat not in {"once", "interval", "weekly"}: repeat = "once"
            
            interval_raw = args_dict.get("interval_minutes") or ""
            interval = float(interval_raw) if str(interval_raw).strip() else delay
            if repeat == "interval" and interval < 1: return "ERROR: Interval must be at least 1 minute."
            
            days_of_week = args_dict.get("days_of_week") or []
            if repeat == "weekly":
                if not isinstance(days_of_week, list):
                    days_of_week = []
                days_of_week = [int(d) for d in days_of_week if str(d).isdigit() and 0 <= int(d) <= 6]
                if not days_of_week:
                    return "ERROR: At least one valid day of the week (0-6) must be specified for weekly repeat."
            
            conversation_mode = str(args_dict.get("conversation_mode") or "current").strip().lower()
            if conversation_mode not in {"current", "new", "dedicated"}:
                conversation_mode = "current"

            run_at_dt = datetime.now() + timedelta(minutes=delay)
            task = {
                "id": str(uuid.uuid4())[:8],
                "prompt": args_dict.get("prompt", ""),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "run_at": run_at_dt.isoformat(timespec="seconds"),
                "anchor_run_at": run_at_dt.isoformat(timespec="seconds"),
                "repeat": repeat,
                "interval_minutes": interval if repeat == "interval" else None,
                "days_of_week": days_of_week if repeat == "weekly" else None,
                "conversation_mode": conversation_mode,
                "target_conversation_id": None,
                "policy_snapshot": self.background_scheduler.policy_snapshot() if getattr(self, "background_scheduler", None) else self._normalize_policy_matrix(),
                "history": [],
                "status": "scheduled",
                "generation": 0
            }
            self.settings.setdefault("background_tasks", []).append(task)
            self.settings["background_jobs"] = self.settings["background_tasks"]
            self._save_settings()
            self._schedule_background_task_thread(task)
            return f"SUCCESS: משימה תוכננה בהצלחה (מזהה: {task['id']}). המשימה תורץ ברקע בזמן המבוקש. אל תבצע את הפעולה בעצמך כעת בשיחה זו, אלא רק הודע למשתמש שהמשימה תוכננה בהצלחה ברקע."
        except Exception as e: return f"ERROR: {e}"

    def schedule_reminder(self, delay_minutes, message, title="", repeat="once", interval_minutes=""):
        try:
            delay = float(delay_minutes or 0)
            if delay < 0:
                return "ERROR: Delay must be positive."
            repeat = str(repeat or "once").strip().lower()
            if repeat not in {"once", "interval"}:
                repeat = "once"
            interval = float(interval_minutes) if str(interval_minutes or "").strip() else delay
            if repeat == "interval" and interval < 1:
                return "ERROR: Interval must be at least 1 minute."
            title = str(title or "תזכורת מסמארטי").strip()
            message = str(message or "").strip()
            if not message:
                return "ERROR: Missing reminder message."
            run_at_dt = datetime.now() + timedelta(minutes=delay)
            task = {
                "id": str(uuid.uuid4())[:8],
                "kind": "reminder",
                "title": title,
                "message": message,
                "prompt": message,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "run_at": run_at_dt.isoformat(timespec="seconds"),
                "anchor_run_at": run_at_dt.isoformat(timespec="seconds"),
                "repeat": repeat,
                "interval_minutes": interval if repeat == "interval" else None,
                "policy_snapshot": self.background_scheduler.policy_snapshot() if getattr(self, "background_scheduler", None) else self._normalize_policy_matrix(),
                "history": [],
                "status": "scheduled",
                "generation": 0
            }
            self.settings.setdefault("background_tasks", []).append(task)
            self.settings["background_jobs"] = self.settings["background_tasks"]
            self._save_settings()
            self._schedule_background_task_thread(task)
            return f"SUCCESS: תזכורת תוכננה. מזהה: {task['id']}"
        except Exception as e:
            return f"ERROR: {e}"

    def list_reminders(self):
        tasks = [
            task for task in self.settings.get("background_tasks", [])
            if task.get("kind") == "reminder" and task.get("status") in {"scheduled", "running", "cancelling"}
        ]
        if not tasks:
            return "אין תזכורות פעילות."
        lines = ["תזכורות פעילות:"]
        for task in tasks[-30:]:
            repeat = "מחזורית" if task.get("repeat") == "interval" else "חד-פעמית"
            lines.append(f"- {task.get('id')} | {task.get('status')} | {repeat} | זמן: {task.get('run_at')} | {task.get('title', '')}: {task.get('message', '')[:140]}")
        return "\n".join(lines)

    def _open_windows_uri(self, *uris):
        if platform.system() != "Windows":
            return "ERROR: פתיחת אפליקציות Windows זמינה רק ב-Windows."
        last_error = ""
        for uri in uris:
            if not uri:
                continue
            try:
                os.startfile(str(uri))
                return f"SUCCESS: נפתח {uri}"
            except Exception as e:
                last_error = str(e)
        return f"ERROR: לא ניתן לפתוח את היעד. {last_error}"

    def _ics_escape(self, value):
        text = str(value or "")
        return text.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")

    def _parse_event_datetime(self, value):
        text = str(value or "").strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt

    def _prepare_calendar_event_file(self, args):
        try:
            title = str(args.get("title") or args.get("summary") or "אירוע מסמארטי").strip()
            start = self._parse_event_datetime(args.get("start") or args.get("start_time"))
            if not start:
                return None, "ERROR: Missing event start time. Use ISO format like 2026-06-03T15:30:00."
            end = self._parse_event_datetime(args.get("end") or args.get("end_time"))
            if not end:
                duration = float(args.get("duration_minutes") or 30)
                end = start + timedelta(minutes=max(1, duration))
            if end <= start:
                return None, "ERROR: Event end time must be after its start time."
            location = str(args.get("location") or "").strip()
            notes = str(args.get("notes") or args.get("description") or "").strip()
            uid = f"{uuid.uuid4()}@smartiai"
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            fmt = lambda dt: dt.strftime("%Y%m%dT%H%M%S")
            ics = "\r\n".join([
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//SmartiAI//Windows Agent//HE",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART:{fmt(start)}",
                f"DTEND:{fmt(end)}",
                f"SUMMARY:{self._ics_escape(title)}",
                f"DESCRIPTION:{self._ics_escape(notes)}",
                f"LOCATION:{self._ics_escape(location)}",
                "END:VEVENT",
                "END:VCALENDAR",
                ""
            ])
            path = os.path.join(OUTPUTS_DIR, f"{safe_filename(title, 'smartiai_event')}.ics")
            suffix = 1
            base, ext = os.path.splitext(path)
            while os.path.exists(path):
                suffix += 1
                path = f"{base}_{suffix}{ext}"
            return {
                "title": title,
                "start": start,
                "end": end,
                "location": location,
                "notes": notes,
                "path": os.path.abspath(path),
                "content": ics,
            }, None
        except Exception as e:
            return None, f"ERROR: {e}"

    def _write_calendar_event_file(self, prepared, *, open_file=True):
        path = str(prepared.get("path") or "")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "x", encoding="utf-8", newline="") as f:
                f.write(str(prepared.get("content") or ""))
            open_error = ""
            if open_file:
                try:
                    os.startfile(path)
                except Exception as e:
                    open_error = str(e)
            result = f"SUCCESS: נוצר קובץ אירוע ליומן: {path}"
            if open_error:
                result += f"\nWARNING: הקובץ נוצר, אך לא ניתן היה לפתוח אותו: {open_error}"
            return result
        except FileExistsError:
            return f"ERROR: Calendar event path changed before creation; no file was overwritten: {path}"
        except Exception as e:
            return f"ERROR: {e}"

    def create_calendar_event_file(self, args):
        prepared, error = self._prepare_calendar_event_file(args or {})
        if error:
            return error
        return self._write_calendar_event_file(
            prepared,
            open_file=normalize_bool_text((args or {}).get("open", True)),
        )

    def _canonicalize_notification_request(self, args):
        if not isinstance(args, dict):
            return None, None, "ERROR: notification_manager arguments must be an object."
        normalized = copy.deepcopy(args)
        raw_action = str(normalized.get("action") or "send_toast").strip().lower()
        if raw_action in NOTIFICATION_TARGET_BY_ACTION and not str(normalized.get("target") or "").strip():
            normalized["target"] = NOTIFICATION_TARGET_BY_ACTION[raw_action]
        action = NOTIFICATION_ACTION_ALIASES.get(raw_action, raw_action)
        if action not in NOTIFICATION_ACTION_POLICY:
            return None, None, f"ERROR: Unsupported notification_manager action: {raw_action or '(empty)'}."
        normalized["action"] = action

        prepared = None
        if action == "send_toast":
            normalized["title"] = str(normalized.get("title") or SMARTI_APP_DISPLAY_NAME).strip()
            normalized["body"] = str(normalized.get("body") or normalized.get("message") or "").strip()
            normalized["kind"] = str(normalized.get("kind") or "default").strip().lower()
            if normalized["kind"] not in {"default", "reminder", "alarm", "important"}:
                return None, None, f"ERROR: Unsupported notification kind: {normalized['kind']}."
            normalized["open_button"] = normalize_bool_text(normalized.get("open_button", True))
        elif action == "schedule_reminder":
            normalized["title"] = str(normalized.get("title") or "תזכורת מסמארטי").strip()
            normalized["message"] = str(normalized.get("message") or normalized.get("prompt") or "").strip()
            if not normalized["message"]:
                return None, None, "ERROR: Missing reminder message."
            try:
                normalized["delay_minutes"] = float(normalized.get("delay_minutes") or 0)
            except Exception:
                return None, None, "ERROR: Reminder delay must be a number."
            if normalized["delay_minutes"] < 0:
                return None, None, "ERROR: Delay must be positive."
            normalized["repeat"] = str(normalized.get("repeat") or "once").strip().lower()
            if normalized["repeat"] not in {"once", "interval"}:
                return None, None, f"ERROR: Unsupported reminder repeat mode: {normalized['repeat']}."
            interval_raw = normalized.get("interval_minutes")
            try:
                normalized["interval_minutes"] = (
                    float(interval_raw)
                    if str(interval_raw or "").strip()
                    else normalized["delay_minutes"]
                )
            except Exception:
                return None, None, "ERROR: Reminder interval must be a number."
            if normalized["repeat"] == "interval" and normalized["interval_minutes"] < 1:
                return None, None, "ERROR: Interval must be at least 1 minute."
        elif action == "cancel_reminder":
            normalized["id"] = str(normalized.get("id") or "").strip()
            if not normalized["id"]:
                return None, None, "ERROR: Missing reminder id."
            task = self._get_background_task(normalized["id"])
            if not task:
                return None, None, f"ERROR: Reminder not found: {normalized['id']}"
            if task.get("kind") != "reminder":
                return None, None, f"ERROR: Task is not a reminder: {normalized['id']}"
            prepared = {"task": task}
        elif action == "create_calendar_event":
            normalized["open"] = normalize_bool_text(normalized.get("open", True))
            prepared, error = self._prepare_calendar_event_file(normalized)
            if error:
                return None, None, error
        elif action == "open_windows_app":
            normalized["target"] = str(normalized.get("target") or "").strip().lower()
            if normalized["target"] not in NOTIFICATION_TARGET_URIS:
                return None, None, f"ERROR: Unsupported Windows notification target: {normalized['target'] or '(empty)'}."
        return normalized, prepared, None

    def _notification_policy_requirements(self, args):
        action = args["action"]
        policy = NOTIFICATION_ACTION_POLICY[action]
        capabilities = list(policy.get("capabilities") or ())
        for field, capability in (policy.get("optional_capabilities") or {}).items():
            if args.get(field):
                capabilities.append(capability)
        target_capabilities = policy.get("target_capabilities") or {}
        if target_capabilities:
            capabilities.append(target_capabilities[args["target"]])
        return capabilities, str(policy.get("risk") or "medium")

    def _notification_approval_details(self, args, prepared):
        action = args["action"]
        if action == "send_toast":
            return (
                f"כותרת: {args['title']}\n"
                f"תוכן: {args['body'][:800] or '(ריק)'}\n"
                f"סוג: {args['kind']}"
            )
        if action == "schedule_reminder":
            interval = (
                f"\nמרווח חזרה: {args['interval_minutes']} דקות"
                if args["repeat"] == "interval"
                else ""
            )
            return (
                f"כותרת: {args['title']}\n"
                f"דחייה: {args['delay_minutes']} דקות\n"
                f"חזרה: {args['repeat']}{interval}\n"
                f"הודעה: {args['message'][:800]}"
            )
        if action == "cancel_reminder":
            task = prepared["task"]
            return (
                f"מזהה: {args['id']}\n"
                f"זמן מתוכנן: {task.get('run_at', '')}\n"
                f"חזרה: {task.get('repeat', 'once')}\n"
                f"הודעה: {str(task.get('message') or '')[:800]}"
            )
        if action == "create_calendar_event":
            return (
                f"כותרת: {prepared['title']}\n"
                f"התחלה: {prepared['start'].isoformat(timespec='seconds')}\n"
                f"סיום: {prepared['end'].isoformat(timespec='seconds')}\n"
                f"נתיב: {prepared['path']}\n"
                f"פתיחה לאחר יצירה: {'כן' if args['open'] else 'לא'}"
            )
        uris = ", ".join(NOTIFICATION_TARGET_URIS[args["target"]])
        return f"יעד: {args['target']}\nכתובות Windows מדויקות: {uris}"

    def _audit_notification_safe_read(self):
        if getattr(self, "audit_logger", None):
            self.audit_logger.record(
                "policy_decision",
                {
                    "manager": "notification_manager",
                    "sub_action": "list_reminders",
                    "capability": NOTIFICATION_ACTION_POLICY["list_reminders"]["audit_capability"],
                    "decision": "allow",
                    "risk": "low",
                    "outcome": "allowed",
                },
                self.settings,
            )

    def notification_manager(self, args):
        args, prepared, error = self._canonicalize_notification_request(args or {})
        if error:
            return error
        action = args["action"]
        if action == "list_reminders":
            self._audit_notification_safe_read()
            return self.list_reminders()

        capabilities, risk = self._notification_policy_requirements(args)
        approval_titles = {
            "send_toast": "אישור שליחת התראת Windows",
            "schedule_reminder": "אישור תזמון תזכורת",
            "cancel_reminder": "אישור ביטול תזכורת",
            "create_calendar_event": "אישור יצירת אירוע יומן",
            "open_windows_app": "אישור פתיחת יעד ב-Windows",
        }
        allowed, error = self._ensure_capabilities_allowed(
            capabilities,
            approval_titles[action],
            self._notification_approval_details(args, prepared),
            risk=risk,
            audit_context={
                "manager": "notification_manager",
                "sub_action": action,
            },
        )
        if not allowed:
            return error

        if action == "send_toast":
            if self._emit_notification("toast", {
                "title": args["title"],
                "body": args["body"],
                "kind": args["kind"],
                "open_button": args["open_button"],
            }):
                return "SUCCESS: התראת Windows נשלחה."
            return "ERROR: ערוץ ההתראות של הממשק אינו זמין כרגע."
        if action == "schedule_reminder":
            return self.schedule_reminder(
                args["delay_minutes"],
                args["message"],
                args["title"],
                args["repeat"],
                args["interval_minutes"],
            )
        if action == "cancel_reminder":
            return self.cancel_background_task(args["id"])
        if action == "create_calendar_event":
            return self._write_calendar_event_file(prepared, open_file=args["open"])
        return self._open_windows_uri(*NOTIFICATION_TARGET_URIS[args["target"]])

    def list_background_tasks(self):
        tasks = [
            task for task in self.settings.get("background_tasks", [])
            if task.get("status") in {"scheduled", "running", "cancelling"}
        ]
        if not tasks:
            return "אין משימות רקע פעילות."
        lines = ["משימות רקע:"]
        for task in tasks[-30:]:
            repeat = "מחזורית" if task.get("repeat") == "interval" else "חד-פעמית"
            kind = "תזכורת" if task.get("kind") == "reminder" else "משימה"
            prompt = task.get("message") if task.get("kind") == "reminder" else task.get("prompt", "")
            result = (task.get("last_result") or "").replace("\n", " ")[:220]
            lines.append(f"- {task.get('id')} | {kind} | {task.get('status')} | {repeat} | ריצה: {task.get('run_at')} | {str(prompt or '')[:120]} | {result}")
        return "\n".join(lines)

    def cancel_background_task(self, task_id):
        task_id = str(task_id or "").strip()
        if not task_id: return "ERROR: Missing task id."
        task = self._get_background_task(task_id)
        if not task: return f"ERROR: Task not found: {task_id}"
        if task.get("status") not in {"scheduled", "running"}:
            return f"ERROR: Task is already {task.get('status')}."
        event = self._background_cancel_events.get(task_id)
        if event:
            event.set()
        if task.get("status") == "running":
            task["status"] = "cancelling"
        else:
            task["status"] = "cancelled"
        task["finished_at"] = datetime.now().isoformat(timespec="seconds")
        task.setdefault("history", []).append({"time": datetime.now().isoformat(timespec="seconds"), "status": task["status"], "result": "User requested cancellation."})
        self.settings["background_jobs"] = self.settings.get("background_tasks", [])
        self._save_settings()
        return f"SUCCESS: משימת הרקע {task_id} בוטלה."

    def retry_background_task(self, task_id, delay_minutes=0):
        task_id = str(task_id or "").strip()
        if not task_id: return "ERROR: Missing task id."
        task = self._get_background_task(task_id)
        if not task: return f"ERROR: Task not found: {task_id}"
        if task.get("status") in {"running", "cancelling"}:
            return f"ERROR: Task is currently {task.get('status')}; cancel it first."
        try:
            delay = max(0.0, float(delay_minutes or 0))
        except Exception:
            delay = 0.0
        old_event = self._background_cancel_events.get(task_id)
        if old_event:
            old_event.set()
        self._background_threads.pop(task_id, None)
        self._background_cancel_events.pop(task_id, None)
        if str(task.get("repeat") or "once").strip().lower() in {"interval", "weekly"}:
            self._ensure_background_task_anchor(task)
        task["generation"] = int(task.get("generation", 0) or 0) + 1
        task["status"] = "scheduled"
        task["run_at"] = (datetime.now() + timedelta(minutes=delay)).isoformat(timespec="seconds")
        task.pop("finished_at", None)
        task["policy_snapshot"] = self.background_scheduler.policy_snapshot() if getattr(self, "background_scheduler", None) else self._normalize_policy_matrix()
        self.settings["background_jobs"] = self.settings.get("background_tasks", [])
        self._save_settings()
        self._schedule_background_task_thread(task)
        return f"SUCCESS: משימת הרקע {task_id} תורצה מחדש."

    def edit_background_task(self, params):
        try:
            if not isinstance(params, dict):
                return "ERROR: Params must be a dictionary."
            
            task_id = str(params.get("id") or "").strip()
            if not task_id: return "ERROR: Missing task id."
            
            task = self._get_background_task(task_id)
            if not task: return f"ERROR: Task not found: {task_id}"
            
            # Cancel old execution thread safely first
            old_event = self._background_cancel_events.get(task_id)
            if old_event:
                old_event.set()
            self._background_threads.pop(task_id, None)
            self._background_cancel_events.pop(task_id, None)
            
            # Update fields if provided
            if "prompt" in params:
                task["prompt"] = str(params["prompt"])
            
            if "repeat" in params:
                repeat = str(params["repeat"]).strip().lower()
                if repeat in {"once", "interval", "weekly"}:
                    task["repeat"] = repeat
                else:
                    return f"ERROR: Invalid repeat value: {repeat}"
            
            if "interval_minutes" in params:
                try:
                    val = float(params["interval_minutes"])
                    task["interval_minutes"] = val
                except ValueError:
                    task["interval_minutes"] = None
                    
            if "days_of_week" in params:
                days = params["days_of_week"]
                if isinstance(days, list):
                    task["days_of_week"] = [int(d) for d in days if str(d).isdigit() and 0 <= int(d) <= 6]
                else:
                    task["days_of_week"] = None
                    
            if "conversation_mode" in params:
                mode = str(params["conversation_mode"]).strip().lower()
                if mode in {"current", "new", "dedicated"}:
                    task["conversation_mode"] = mode
                else:
                    return f"ERROR: Invalid conversation_mode: {mode}"
            
            # If delay_minutes is provided, reschedule run_at
            if "delay_minutes" in params:
                try:
                    delay = float(params["delay_minutes"])
                    if delay >= 0:
                        run_at_dt = datetime.now() + timedelta(minutes=delay)
                        task["run_at"] = run_at_dt.isoformat(timespec="seconds")
                        task["anchor_run_at"] = run_at_dt.isoformat(timespec="seconds")
                        task.pop("finished_at", None)
                except ValueError:
                    pass
            elif str(task.get("repeat") or "once").strip().lower() in {"interval", "weekly"}:
                self._ensure_background_task_anchor(task)
            
            # Reset status and increment generation so new thread can take over
            task["generation"] = int(task.get("generation", 0) or 0) + 1
            task["status"] = "scheduled"
            task["policy_snapshot"] = self.background_scheduler.policy_snapshot() if getattr(self, "background_scheduler", None) else self._normalize_policy_matrix()
            
            self.settings["background_jobs"] = self.settings.get("background_tasks", [])
            self._save_settings()
            
            self._schedule_background_task_thread(task)
            return f"SUCCESS: משימת הרקע {task_id} עודכנה בהצלחה ותוזמנה מחדש."
        except Exception as e:
            return f"ERROR: {e}"

    def _legacy_update_memory_tool(self, mode, content):
        mode = str(mode or "").strip().lower()
        content = str(content or "").strip()
        if mode == "clear":
            self.settings["user_memory"] = ""
        elif mode == "append":
            current = self.settings.get("user_memory", "").strip()
            self.settings["user_memory"] = (current + "\n" + content).strip() if current else content
        elif mode == "replace":
            self.settings["user_memory"] = content
        else:
            return "ERROR: mode must be replace, append, or clear."
        self._save_settings()
        self.system_prompt = self._load_system_prompt()
        return "SUCCESS: הזיכרון עודכן."

    def search_memory_tool(self, query, memory_type="any", max_results=6):
        if not getattr(self, "memory_manager", None):
            return "ERROR: Memory manager is not available."
        try:
            max_results = max(1, min(20, int(max_results or 6)))
        except Exception:
            max_results = 6
        return self.memory_manager.tool_search_text(query, memory_type=memory_type or "any", max_results=max_results)

    def update_memory_tool(self, mode, content, memory_type="long_term", subject="", ttl_hours=None,
                           importance=3, tags=None, memory_id=""):
        if not getattr(self, "memory_manager", None):
            return "ERROR: Memory manager is not available."
        mode = str(mode or "").strip().lower()
        content = str(content or "").strip()
        memory_type = self.memory_manager._normalize_type(memory_type)
        if mode == "clear":
            removed = self.memory_manager.clear(memory_type if memory_type else None)
            self.settings["user_memory"] = ""
            self._save_settings()
            self.system_prompt = self._load_system_prompt()
            return f"SUCCESS: cleared {removed} memory entries."
        if mode == "forget":
            ok = self.memory_manager.forget(memory_id)
            self.system_prompt = self._load_system_prompt()
            return "SUCCESS: memory forgotten." if ok else "ERROR: memory_id not found."
        if mode == "replace":
            self.memory_manager.clear(memory_type)
        elif mode not in {"append", "add"}:
            return "ERROR: mode must be add, append, replace, clear, or forget."
        if not content:
            return "ERROR: content is required for add/append/replace."
        volatile = self.memory_manager._looks_live_or_temporal(content)
        if volatile and memory_type in {"long_term", "user"} and ttl_hours in (None, ""):
            memory_type = "short_term"
            ttl_hours = self.settings.get("memory", {}).get("short_term_default_ttl_hours", 12)
        entry_id = self.memory_manager.add(
            memory_type,
            content,
            subject=subject,
            ttl_hours=ttl_hours,
            importance=importance,
            tags=tags,
            source="explicit_tool",
            confidence=0.8,
            volatile=volatile,
        )
        self.settings["user_memory"] = ""
        self._save_settings()
        self.system_prompt = self._load_system_prompt()
        return f"SUCCESS: memory updated ({entry_id})."

    def memory_manager_tool(self, action, args=None):
        """Canonical management API. Sensitive values are never revealed to the model."""
        manager = getattr(self, "memory_manager", None)
        if not manager:
            return "ERROR: Memory manager is not available."
        args = dict(args or {})
        action = str(action or "").strip().lower()
        try:
            if action == "list":
                rows = manager.list_entries(
                    query=args.get("query", ""),
                    memory_type=args.get("memory_type", "any"),
                    status=args.get("status", "active"),
                    category=args.get("category", ""),
                    sensitivity=args.get("sensitivity", "any"),
                    source=args.get("source", ""),
                    date_range=args.get("date_range", "any"),
                    expiry=args.get("expiry", "any"),
                    max_results=args.get("max_results", 100),
                )
                return json.dumps({"ok": True, "entries": rows}, ensure_ascii=False)
            if action == "get":
                entry = manager.get_entry(args.get("memory_id", ""))
                return json.dumps({"ok": bool(entry), "entry": entry}, ensure_ascii=False)
            if action == "search":
                return self.search_memory_tool(
                    args.get("query", ""),
                    args.get("memory_type", "any"),
                    args.get("max_results", 6),
                )
            if action == "stats":
                return json.dumps({"ok": True, "stats": manager.memory_stats()}, ensure_ascii=False)
            if action == "add":
                entry_id = manager.add(
                    args.get("memory_type", "long_term"),
                    args.get("content", ""),
                    subject=args.get("subject", ""),
                    tags=args.get("tags", []),
                    ttl_hours=args.get("ttl_hours"),
                    importance=args.get("importance", 3),
                    source="explicit_tool",
                    confidence=0.8,
                    category=args.get("category", ""),
                    consent_state="approved",
                    cloud_allowed=True,
                    pinned=bool(args.get("pinned", False)),
                )
                return json.dumps({"ok": True, "memory_id": entry_id}, ensure_ascii=False)
            if action == "edit":
                editable = {
                    key: args[key] for key in (
                        "content", "memory_type", "subject", "ttl_hours", "importance",
                        "tags", "category", "pinned"
                    ) if key in args
                }
                entry = manager.edit_entry(
                    args.get("memory_id", ""),
                    expected_version=args.get("expected_version"),
                    user_authorized=False,
                    **editable,
                )
                return json.dumps({"ok": True, "entry": entry}, ensure_ascii=False)
            if action == "archive":
                return json.dumps({"ok": manager.archive_entry(args.get("memory_id", ""))}, ensure_ascii=False)
            if action == "restore":
                return json.dumps({"ok": manager.restore_entry(args.get("memory_id", ""))}, ensure_ascii=False)
            if action == "forget":
                return json.dumps({"ok": manager.forget(args.get("memory_id", ""))}, ensure_ascii=False)
            if action == "clear":
                removed = manager.clear(args.get("memory_type") if args.get("memory_type") not in {"", "any"} else None)
                return json.dumps({"ok": True, "removed": removed}, ensure_ascii=False)
            if action == "export":
                path = manager.export_memory(
                    args.get("path", ""),
                    encrypted=bool(args.get("encrypted", True)),
                    include_sensitive=bool(args.get("encrypted", True)),
                )
                return json.dumps({"ok": True, "path": path}, ensure_ascii=False)
            if action == "import":
                result = manager.import_memory(args.get("path", ""), user_authorized=False)
                return json.dumps({"ok": True, **result}, ensure_ascii=False)
            return f"ERROR: Unsupported memory action: {action}"
        except Exception as e:
            return f"ERROR: {e}"
