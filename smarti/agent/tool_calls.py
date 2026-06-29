"""Tool-call normalization, validation, batching, planner state, and model feedback."""
from .shared import *


class ToolCallMixin:
    def _normalize_tool_call_args(self, action, args_dict):
        if not isinstance(args_dict, dict):
            return args_dict
        args = copy.deepcopy(args_dict)

        if action == "search_tools":
            if "query" not in args and "q" in args:
                args["query"] = args.get("q")
            return {k: v for k, v in args.items() if k in {"query", "kind", "include_disabled", "limit"}}

        if action == "load_skill":
            if "name" not in args:
                for alias in ("skill", "skill_name"):
                    if alias in args:
                        args["name"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k in {"name", "task"}}

        if action == "system_command":
            if "command" not in args and "cmd" in args:
                args["command"] = args.get("cmd")
            if "cwd" not in args:
                for alias in ("working_directory", "directory", "dir"):
                    if alias in args:
                        args["cwd"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k in {"command", "cwd", "timeout_seconds", "require_approval", "explanation"}}

        if action == "system_manager":
            if "action" not in args:
                if "command" in args or "cmd" in args:
                    args["action"] = "run_command"
                elif "text" in args:
                    args["action"] = "set_clipboard"
            if "command" not in args and "cmd" in args:
                args["command"] = args.get("cmd")
            if "cwd" not in args:
                for alias in ("working_directory", "directory", "dir"):
                    if alias in args:
                        args["cwd"] = args.get(alias)
                        break
            if "volume_action" not in args and "volume" in args:
                args["volume_action"] = args.get("volume")
            return {k: v for k, v in args.items() if k in {
                "action", "command", "cwd", "timeout_seconds", "require_approval", "explanation",
                "path", "operation", "ref", "text", "volume_action"
            }}

        if action == "software_manager":
            if "action" not in args:
                args["action"] = "open" if any(k in args for k in ("name", "app", "application", "program", "software_name")) else "list"
            if "name" not in args:
                for alias in ("software_name", "app_name", "app", "application", "program"):
                    if alias in args:
                        args["name"] = args.get(alias)
                        break
            if "query" not in args and "q" in args:
                args["query"] = args.get("q")
            return {k: v for k, v in args.items() if k in {"action", "name", "query", "limit", "refresh", "include_paths", "format"}}

        if action == "open_software":
            if "name" not in args:
                for alias in ("software_name", "app_name", "app", "application", "program"):
                    if alias in args:
                        args["name"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k == "name"}

        if action == "open_file_or_folder":
            if "path" not in args:
                for alias in ("file_path", "folder_path", "filepath", "target"):
                    if alias in args:
                        args["path"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k == "path"}

        if action == "file_manager":
            if "action" not in args:
                if "content" in args:
                    args["action"] = "save_text"
                elif "query" in args:
                    args["action"] = "search_files"
                elif "directory" in args and "text" in args:
                    args["action"] = "search_content"
                elif "path" in args:
                    args["action"] = "open"
            if str(args.get("action", "") or "").strip().lower() in {"delete", "remove", "recycle"}:
                args["action"] = "trash"
            if "path" not in args:
                for alias in ("file_path", "folder_path", "filepath", "target", "filename", "file_name"):
                    if alias in args:
                        args["path"] = args.get(alias)
                        break
            if "content" not in args and "body" in args:
                args["content"] = args.get("body")
            if "text" not in args and "search_text" in args:
                args["text"] = args.get("search_text")
            return {k: v for k, v in args.items() if k in {"action", "path", "content", "query", "directory", "text"}}

        # google_drive_manager argument normalization is parked with the Drive integration.

        if action == "trash_file_or_folder":
            if "path" not in args:
                for alias in ("file_path", "folder_path", "filepath", "target"):
                    if alias in args:
                        args["path"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k == "path"}

        if action == "save_text_file":
            if "path" not in args:
                for alias in ("filename", "file_name", "file_path"):
                    if alias in args:
                        args["path"] = args.get(alias)
                        break
            if "content" not in args and "text" in args:
                args["content"] = args.get("text")
            return {k: v for k, v in args.items() if k in {"path", "content"}}

        if action == "web_manager":
            if "action" not in args:
                if "location" in args:
                    args["action"] = "weather"
                elif "url" in args:
                    args["action"] = "read"
                else:
                    args["action"] = "search"
            if "query" not in args:
                for alias in ("q", "search", "term"):
                    if alias in args:
                        args["query"] = args.get(alias)
                        break
            if "location" not in args and args.get("action") == "weather":
                args["location"] = args.get("query") or args.get("query_or_url")
            if "query_or_url" not in args and args.get("action") == "open":
                args["query_or_url"] = args.get("url") or args.get("query")
            return {k: v for k, v in args.items() if k in {
                "action", "query", "url", "query_or_url", "location", "days", "units",
                "mode", "max_pages", "max_depth", "max_total_chars", "max_page_chars",
                "include_links", "max_links", "same_domain", "include_subdomains",
                "include_patterns", "exclude_patterns", "respect_robots_txt",
                "use_sitemap", "delay_seconds", "timeout_seconds", "user_agent"
            }}

        if action == "screen_manager":
            if "action" not in args:
                args["action"] = "analyze_image" if "path" in args else "capture"
            return {k: v for k, v in args.items() if k in {"action", "path"}}

        if action == "background_task_manager":
            if "action" not in args:
                if "id" in args:
                    args["action"] = "cancel"
                elif "prompt" in args:
                    args["action"] = "schedule"
                else:
                    args["action"] = "list"
            return {k: v for k, v in args.items() if k in {
                "action", "delay_minutes", "prompt", "repeat", "interval_minutes", "days_of_week", "conversation_mode", "id"
            }}

        if action == "notification_manager":
            if "action" not in args:
                if "delay_minutes" in args:
                    args["action"] = "schedule_reminder"
                elif "start" in args or "start_time" in args:
                    args["action"] = "create_calendar_event"
                elif "target" in args:
                    args["action"] = "open_windows_app"
                else:
                    args["action"] = "send_toast"
            if "message" not in args and "prompt" in args:
                args["message"] = args.get("prompt")
            if "body" not in args and "message" in args and args.get("action") == "send_toast":
                args["body"] = args.get("message")
            return {k: v for k, v in args.items() if k in {
                "action", "title", "body", "message", "kind", "open_button",
                "delay_minutes", "repeat", "interval_minutes", "id", "target",
                "start", "start_time", "end", "end_time", "duration_minutes",
                "location", "notes", "description", "open"
            }}

        if action == "memory_manager":
            if "action" not in args:
                args["action"] = "search" if "query" in args and "content" not in args else "update"
            if "memory_type" not in args and "type" in args:
                args["memory_type"] = args.get("type")
            return {k: v for k, v in args.items() if k in {
                "action", "query", "mode", "content", "memory_type", "subject",
                "ttl_hours", "importance", "tags", "memory_id", "max_results"
            }}

        if action == "email_manager":
            if "action" not in args and "operation" in args:
                args["action"] = args.get("operation")
            if "target_mailbox" not in args and "destination" in args:
                args["target_mailbox"] = args.get("destination")
            if "uid" not in args and "message_id" in args:
                args["uid"] = args.get("message_id")
            return args

        if action == "get_weather":
            if "location" not in args:
                for alias in ("city", "place", "query", "q", "area"):
                    if alias in args:
                        args["location"] = args.get(alias)
                        break
            if "days" in args:
                try:
                    args["days"] = int(args.get("days"))
                except Exception:
                    args["days"] = 2
            if "units" in args:
                args["units"] = str(args.get("units", "metric")).lower()
            return {k: v for k, v in args.items() if k in {"location", "days", "units"}}

        if action == "read_website":
            if "url" not in args:
                for alias in ("query", "query_or_url", "href", "link"):
                    if alias in args:
                        args["url"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k in {
                "url", "mode", "max_pages", "max_depth", "max_total_chars",
                "max_page_chars", "include_links", "max_links", "same_domain",
                "include_subdomains", "include_patterns", "exclude_patterns",
                "respect_robots_txt", "use_sitemap", "delay_seconds",
                "timeout_seconds", "user_agent"
            }}

        if action == "install_skill":
            if "id" not in args:
                for alias in ("name", "skill_name", "slug"):
                    if alias in args:
                        args["id"] = args.get(alias)
                        break
            if "source" not in args and args.get("id"):
                args["source"] = "clawhub"
            return {k: v for k, v in args.items() if k in {"source", "id", "path"}}

        if action == "install_skill_requirements":
            if "name" not in args:
                for alias in ("skill_name", "skill", "id", "slug"):
                    if alias in args:
                        args["name"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k in {"name", "reason"}}

        if action == "run_skill":
            if "name" not in args:
                for alias in ("skill_name", "skill", "id", "tool_name"):
                    if alias in args:
                        args["name"] = args.get(alias)
                        break
            if "arguments" not in args:
                for alias in ("params", "parameters", "input", "payload"):
                    if isinstance(args.get(alias), dict):
                        args["arguments"] = args.get(alias)
                        break
            if "arguments" not in args:
                extras = {k: v for k, v in args.items() if k not in {"name", "skill_name", "skill", "id", "tool_name"}}
                if extras:
                    args["arguments"] = extras
            clean = {k: v for k, v in args.items() if k in {"name", "arguments"}}
            if "arguments" in clean and not isinstance(clean["arguments"], dict):
                clean["arguments"] = {"task": str(clean["arguments"])}
            return clean

        if action == "run_mcp":
            if "package" not in args:
                for alias in ("pkg", "package_name", "server"):
                    if alias in args:
                        args["package"] = args.get(alias)
                        break
            if "function" not in args:
                for alias in ("tool", "tool_name", "function_name", "name"):
                    if alias in args:
                        args["function"] = args.get(alias)
                        break
            if "arguments" not in args:
                for alias in ("params", "parameters", "input", "payload"):
                    if isinstance(args.get(alias), dict):
                        args["arguments"] = args.get(alias)
                        break
            if isinstance(args.get("arguments"), str):
                try:
                    parsed_args = json.loads(args["arguments"])
                    if isinstance(parsed_args, dict):
                        args["arguments"] = parsed_args
                except Exception:
                    pass
            return {k: v for k, v in args.items() if k in {"package", "function", "arguments"}}

        if action == "extension_manager":
            if "action" not in args:
                if "package" in args and "function" in args:
                    args["action"] = "run_mcp"
                elif "package" in args:
                    args["action"] = "install_mcp"
                elif "name" in args and "arguments" in args:
                    args["action"] = "run_skill"
                elif "query" in args:
                    args["action"] = "search_skills"
            if "package" not in args:
                for alias in ("pkg", "package_name", "server"):
                    if alias in args:
                        args["package"] = args.get(alias)
                        break
            if "function" not in args:
                for alias in ("tool", "tool_name", "function_name"):
                    if alias in args:
                        args["function"] = args.get(alias)
                        break
            if "arguments" not in args:
                for alias in ("params", "parameters", "input", "payload"):
                    if isinstance(args.get(alias), dict):
                        args["arguments"] = args.get(alias)
                        break
            if isinstance(args.get("arguments"), str):
                try:
                    parsed_args = json.loads(args["arguments"])
                    if isinstance(parsed_args, dict):
                        args["arguments"] = parsed_args
                except Exception:
                    pass
            if "name" not in args:
                for alias in ("skill", "skill_name"):
                    if alias in args:
                        args["name"] = args.get(alias)
                        break
            return {k: v for k, v in args.items() if k in {
                "action", "query", "package", "function", "arguments",
                "source", "id", "path", "name", "reason"
            }}

        if action == "browser_automation_manager":
            if "targetId" in args and "target_id" not in args:
                args["target_id"] = args.get("targetId")
            if "tabId" in args and "tab_id" not in args:
                args["tab_id"] = args.get("tabId")
            if "targetUrl" in args and "target_url" not in args:
                args["target_url"] = args.get("targetUrl")
            if "timeoutMs" in args and "timeout_ms" not in args:
                args["timeout_ms"] = args.get("timeoutMs")
            if "timeMs" in args and "time_ms" not in args:
                args["time_ms"] = args.get("timeMs")
            if "fullPage" in args and "full_page" not in args:
                args["full_page"] = args.get("fullPage")
            if "bodyChars" in args and "body_chars" not in args:
                args["body_chars"] = args.get("bodyChars")
            if "htmlChars" in args and "html_chars" not in args:
                args["html_chars"] = args.get("htmlChars")
            if "includeUrls" in args and "include_urls" not in args:
                args["include_urls"] = args.get("includeUrls")
            if "downloadPath" in args and "download_path" not in args:
                args["download_path"] = args.get("downloadPath")
            if "maxChars" in args and "max_chars" not in args:
                args["max_chars"] = args.get("maxChars")
            if "maxBodyChars" in args and "max_body_chars" not in args:
                args["max_body_chars"] = args.get("maxBodyChars")
            if "snapshotEpoch" in args and "snapshot_epoch" not in args:
                args["snapshot_epoch"] = args.get("snapshotEpoch")
            if "refEpoch" in args and "ref_epoch" not in args:
                args["ref_epoch"] = args.get("refEpoch")
            if "captureMs" in args and "capture_ms" not in args:
                args["capture_ms"] = args.get("captureMs")
            if "traceCategories" in args and "trace_categories" not in args:
                args["trace_categories"] = args.get("traceCategories")
            if "includeBody" in args and "include_body" not in args:
                args["include_body"] = args.get("includeBody")
            if "responseBody" in args and "response_body" not in args:
                args["response_body"] = args.get("responseBody")
            if "delayMs" in args and "delay_ms" not in args:
                args["delay_ms"] = args.get("delayMs")
            if "closeOthers" in args and "close_others" not in args:
                args["close_others"] = args.get("closeOthers")
            allowed = {
                "action", "profile", "url", "targetUrl", "target_url", "query_or_url",
                "targetId", "target_id", "tabId", "tab_id", "ref", "selector",
                "snapshotEpoch", "snapshot_epoch", "refEpoch", "ref_epoch", "allowStaleRef",
                "refs", "snapshotFormat", "snapshot_format", "role", "name", "textSelector", "request", "kind", "text", "value",
                "keys", "key", "label", "index", "x", "y", "deltaX", "deltaY",
                "width", "height", "path", "paths", "files", "timeoutMs",
                "timeout_ms", "timeMs", "time_ms", "timeout", "limit", "bodyChars",
                "body_chars", "maxChars", "max_chars", "maxBodyChars", "max_body_chars",
                "htmlChars", "html_chars", "urls", "includeUrls",
                "include_urls", "includeHidden", "fullPage", "full_page", "labels",
                "annotate", "clip", "includeBody", "include_body", "responseBody", "response_body",
                "captureMs", "capture_ms", "reload", "live", "record", "save", "traceCategories", "trace_categories",
                "includeValues", "storage", "op", "operation", "script", "expression",
                "function", "method", "params", "urlContains", "waitUntil", "state",
                "accept", "expectDialog", "promptText", "expectDownload",
                "downloadPath", "download_path", "submit", "clear", "slowly",
                "delay", "delayMs", "delay_ms", "newTab", "cleanup", "closeOthers",
                "close_others", "noSnapshot", "printBackground", "landscape"
            }
            return {k: v for k, v in args.items() if k in allowed}

        if action == "computer_automation_manager":
            if "window" not in args:
                for alias in ("window_name", "app", "application", "program"):
                    if alias in args:
                        args["window"] = args.get(alias)
                        break
            if "automation_id" not in args:
                for alias in ("automationId", "id"):
                    if alias in args:
                        args["automation_id"] = args.get(alias)
                        break
            if "class_name" not in args and "className" in args:
                args["class_name"] = args.get("className")
            if "control_type" not in args:
                for alias in ("controlType", "role", "type"):
                    if alias in args:
                        args["control_type"] = args.get(alias)
                        break
            if "text" not in args and "param1" in args:
                args["text"] = args.get("param1")
            if "keys" not in args:
                for alias in ("key_sequence", "shortcut", "param2"):
                    if alias in args:
                        args["keys"] = args.get(alias)
                        break
            legacy_code = self._computer_action_to_code(args) if "code" not in args else ""
            if legacy_code:
                return {"code": legacy_code}
            allowed = {
                "action", "code", "window", "name", "automation_id", "class_name",
                "control_type", "path", "text", "keys", "max_depth", "limit",
                "timeout", "include_offscreen", "dry_run", "allow_mouse_fallback",
                "allow_clipboard_fallback", "allow_global_keys", "allow_destructive"
            }
            return {k: v for k, v in args.items() if k in allowed}

        if action not in BUILTIN_TOOL_SCHEMAS:
            if args.get("action") in {"type_text", "write_text"}:
                args["action"] = "type"
            if "param1" not in args and "text" in args:
                args["param1"] = args.get("text")
            if action == "DesktopAutomator":
                return {k: v for k, v in args.items() if k in {"action", "param1", "param2"}}
        return args

    def _require_unified_fields(self, op, args, fields, allow_empty=None):
        allow_empty = set(allow_empty or [])
        missing = [
            field for field in fields
            if args.get(field) is None or (args.get(field) == "" and field not in allow_empty)
        ]
        if missing:
            raise ValueError(f"{op} requires: {', '.join(missing)}")

    def _route_unified_tool(self, action, args_dict):
        args = args_dict if isinstance(args_dict, dict) else {}
        op = str(args.get("action", "") or "").strip().lower()

        if action == "system_manager":
            if op == "run_command":
                self._require_unified_fields(op, args, ["command"])
                routed = {
                    "command": args.get("command"),
                    "cwd": args.get("cwd", ""),
                    "require_approval": args.get("require_approval", False),
                    "explanation": args.get("explanation", ""),
                }
                if args.get("timeout_seconds") not in (None, ""):
                    routed["timeout_seconds"] = args.get("timeout_seconds")
                return "system_command", routed
            if op == "git_status":
                return "git_status", {"path": args.get("path") or args.get("cwd") or os.getcwd(), "operation": args.get("operation", "status"), "ref": args.get("ref", "")}
            if op == "run_project_check":
                self._require_unified_fields(op, args, ["command"])
                return "run_project_check", {"path": args.get("path") or args.get("cwd") or os.getcwd(), "command": args.get("command")}
            if op == "list_processes":
                return "list_processes", {}
            if op == "set_clipboard":
                self._require_unified_fields(op, args, ["text"])
                return "set_clipboard", {"text": args.get("text")}
            if op == "set_volume":
                self._require_unified_fields(op, args, ["volume_action"])
                return "set_volume", {"action": str(args.get("volume_action") or "MUTE").upper()}
            raise ValueError("system_manager action must be one of run_command, git_status, run_project_check, list_processes, set_clipboard, set_volume.")

        if action == "software_manager":
            if op == "open":
                self._require_unified_fields(op, args, ["name"])
                return "open_software", {"name": args.get("name")}
            if op in {"list", "find", "refresh"}:
                routed = {
                    "query": args.get("query", ""),
                    "limit": args.get("limit", 150),
                    "refresh": bool(args.get("refresh")) or op == "refresh",
                    "include_paths": bool(args.get("include_paths")),
                    "format": args.get("format", "text"),
                }
                return "list_software", routed
            raise ValueError("software_manager action must be list, find, open, or refresh.")

        if action == "file_manager":
            if op == "open":
                self._require_unified_fields(op, args, ["path"])
                return "open_file_or_folder", {"path": args.get("path")}
            if op == "save_text":
                self._require_unified_fields(op, args, ["path", "content"], allow_empty={"content"})
                return "save_text_file", {"path": args.get("path"), "content": args.get("content")}
            if op == "read_document":
                self._require_unified_fields(op, args, ["path"])
                return "read_local_document", {"path": args.get("path")}
            if op == "search_files":
                self._require_unified_fields(op, args, ["query"])
                return "smart_file_search", {"query": args.get("query")}
            if op == "search_content":
                self._require_unified_fields(op, args, ["directory", "text"])
                return "deep_content_search", {"directory": args.get("directory"), "text": args.get("text")}
            if op == "extract_image_text":
                self._require_unified_fields(op, args, ["path"])
                return "extract_image_text", {"path": args.get("path")}
            if op == "attach":
                self._require_unified_fields(op, args, ["path"])
                return "attach_local_file", {"path": args.get("path")}
            if op in {"trash", "recycle", "delete", "remove"}:
                self._require_unified_fields(op, args, ["path"])
                return "trash_file_or_folder", {"path": args.get("path")}
            raise ValueError("Unsupported file_manager action.")

        if action == "web_manager":
            if op == "search":
                self._require_unified_fields(op, args, ["query"])
                return "internet_search", {"query": args.get("query")}
            if op == "read":
                routed = {k: args.get(k) for k in (
                    "mode", "max_pages", "max_depth", "max_total_chars", "max_page_chars",
                    "include_links", "max_links", "same_domain", "include_subdomains",
                    "include_patterns", "exclude_patterns", "respect_robots_txt",
                    "use_sitemap", "delay_seconds", "timeout_seconds", "user_agent"
                ) if args.get(k) not in (None, "")}
                routed["url"] = args.get("url") or args.get("query")
                return "read_website", routed
            if op == "open":
                return "open_in_browser", {"query_or_url": args.get("query_or_url") or args.get("url") or args.get("query")}
            if op == "weather":
                return "get_weather", {"location": args.get("location") or args.get("query"), "days": args.get("days", 2), "units": args.get("units", "metric")}
            raise ValueError("Unsupported web_manager action.")

        if action == "screen_manager":
            if op == "capture":
                return "capture_screen", {}
            if op == "save_screenshot":
                return "save_screenshot_to_disk", {}
            if op == "analyze_image":
                self._require_unified_fields(op, args, ["path"])
                return "analyze_local_image", {"path": args.get("path")}
            raise ValueError("Unsupported screen_manager action.")

        if action == "background_task_manager":
            if op == "schedule":
                self._require_unified_fields(op, args, ["delay_minutes", "prompt"])
                routed = {k: args.get(k) for k in ("delay_minutes", "prompt", "repeat", "interval_minutes", "days_of_week", "conversation_mode") if args.get(k) not in (None, "")}
                return "schedule_background_task", routed
            if op == "list":
                return "list_background_tasks", {}
            if op == "cancel":
                self._require_unified_fields(op, args, ["id"])
                return "cancel_background_task", {"id": args.get("id")}
            if op == "edit":
                self._require_unified_fields(op, args, ["id"])
                routed = {k: args.get(k) for k in ("id", "delay_minutes", "prompt", "repeat", "interval_minutes", "days_of_week", "conversation_mode") if args.get(k) not in (None, "")}
                return "edit_background_task", routed
            if op == "retry":
                self._require_unified_fields(op, args, ["id"])
                return "retry_background_task", {"id": args.get("id"), "delay_minutes": args.get("delay_minutes", 0)}
            raise ValueError("Unsupported background_task_manager action.")

        if action == "memory_manager":
            if op == "search":
                self._require_unified_fields(op, args, ["query"])
                return "search_memory", {"query": args.get("query"), "memory_type": args.get("memory_type", "any"), "max_results": args.get("max_results", 6)}
            if op == "update":
                return "update_memory", {k: v for k, v in args.items() if k in {"mode", "content", "memory_type", "subject", "ttl_hours", "importance", "tags", "memory_id"}}
            raise ValueError("memory_manager action must be search or update.")

        if action == "extension_manager":
            if op in {"search_mcp", "install_mcp", "run_mcp", "list_skills", "search_skills", "install_skill", "install_skill_requirements", "load_skill", "run_skill"}:
                routed = {k: v for k, v in args.items() if k != "action"}
                return op, routed
            raise ValueError("Unsupported extension_manager action.")

        return action, args_dict

    def _computer_action_to_code(self, args):
        action = str(args.get("action", "")).strip().lower()
        text = args.get("text", args.get("param1", ""))
        keys = args.get("keys", args.get("key_sequence", args.get("shortcut", "")))
        structured_actions = {
            "inspect", "list_windows", "find", "get_focused", "focus_window",
            "focus", "invoke", "click", "set_text", "toggle", "select",
            "expand", "collapse", "send_keys", "press", "hotkey"
        }
        if action in structured_actions:
            return ""
        if action in {"type", "type_text", "write", "write_text"} and text:
            return f"paste_text({json.dumps(str(text), ensure_ascii=False)})\nprint('SUCCESS: הטקסט הודבק דרך Clipboard ותומך בעברית/Unicode.')"
        if action in {"auto", "keys", "send_keys", "type_keys"} and keys:
            if isinstance(keys, list):
                safe_keys = [str(k) for k in keys if str(k)]
                if len(safe_keys) > 1:
                    return f"hotkey(*{json.dumps(safe_keys, ensure_ascii=False)})\nprint('SUCCESS: key sequence sent.')"
                if safe_keys:
                    return f"press({json.dumps(safe_keys[0], ensure_ascii=False)})\nprint('SUCCESS: key sent.')"
            return f"send_keys({json.dumps(str(keys), ensure_ascii=False)})\nprint('SUCCESS: keys sent.')"
        if action in {"press", "key"} and text:
            return f"press({json.dumps(str(text), ensure_ascii=False)})\nprint('SUCCESS: המקש נלחץ.')"
        if action == "hotkey":
            if isinstance(keys, list) and keys:
                safe_keys = [str(k) for k in keys]
            else:
                safe_keys = [str(args.get("param1", ""))]
                if args.get("param2"):
                    safe_keys.append(str(args.get("param2")))
            if all(safe_keys):
                return f"hotkey(*{json.dumps(safe_keys, ensure_ascii=False)})\nprint('SUCCESS: קיצור המקלדת הופעל.')"
        if action in {"focus_window", "activate_window"} and text:
            return f"activate_window({json.dumps(str(text), ensure_ascii=False)})\nprint('SUCCESS: focus attempted.')"
        if action in {"click", "move_click"}:
            x = args.get("x", args.get("param1", ""))
            y = args.get("y", args.get("param2", ""))
            try:
                x_val, y_val = int(x), int(y)
                return f"pa.click({x_val}, {y_val})\nprint('SUCCESS: click sent.')"
            except Exception:
                return ""
        if action in {"list_windows", "list"}:
            return "print('\\n'.join(list_windows()))"
        return ""

    def _prepare_automation_code(self, code):
        safe_code = strip_code_fences(code)
        safe_code = safe_code.encode("utf-8", "replace").decode("utf-8", "replace")
        safe_code = safe_code.replace("pyautogui.", "pa.")
        safe_code = safe_code.replace("uiautomation.", "auto.")
        safe_code = safe_code.replace("pyperclip.", "clip.")
        cleaned_lines = []
        allowed_import_re = re.compile(
            r"^\s*(import\s+(time|pyautogui(\s+as\s+pa)?|uiautomation(\s+as\s+auto)?|pyperclip(\s+as\s+clip)?)|from\s+(time|pyautogui|uiautomation|pyperclip)\s+import\s+[\w*, ]+)\s*$",
            re.IGNORECASE
        )
        for line in safe_code.splitlines():
            if allowed_import_re.match(line):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    def _tool_requires_info_before_use(self, action, args_dict, schemas_seen):
        schemas_seen = schemas_seen or set()
        settings = getattr(self, "settings", {}) or {}
        inline_schema_tools = {
            "agent_planner",
            "get_tool_info",
            "search_tools",
            "load_skill",
            "system_manager",
            "software_manager",
            "file_manager",
            "web_manager",
            "screen_manager",
            "background_task_manager",
            "notification_manager",
            "memory_manager",
            "browser_automation_manager",
            "computer_automation_manager",
            "extension_manager",
        }
        if not settings.get("enable_tool_search_catalog", True):
            inline_schema_tools.discard("search_tools")
        if action == "extension_manager":
            try:
                routed_action, routed_args = self._route_unified_tool(action, args_dict)
                return self._tool_requires_info_before_use(routed_action, routed_args, schemas_seen)
            except ValueError:
                return False, None
        if action == "canvas_manager":
            # Its compact call contract lives in the system instructions. Do
            # not require a full schema round-trip for every visual request.
            return False, None
        if action == "run_skill":
            skill_name = safe_filename(args_dict.get("name", ""))
            if skill_name and skill_name not in schemas_seen:
                return True, f"לפני הפעלת Skill חובה לקרוא `get_tool_info` על שם ה-Skill עצמו: {skill_name}."
        if action == "run_mcp":
            pkg = str(args_dict.get("package", "")).strip()
            resolved = self._resolve_mcp_package(pkg) if pkg else ""
            keys = {pkg, resolved, mcp_pkg_to_file_stem(pkg), mcp_pkg_to_file_stem(resolved)}
            if pkg and not (keys & schemas_seen):
                return True, f"לפני הפעלת MCP חובה לקרוא `get_tool_info` על שם החבילה: {pkg}."
        if action not in BUILTIN_TOOL_SCHEMAS:
            tool_key = safe_filename(action)
            if os.path.exists(os.path.join(TOOLS_DIR, f"{tool_key}.txt")) and tool_key not in schemas_seen:
                return True, f"לפני הפעלת כלי פייתון מותאם אישית חובה לקרוא `get_tool_info`: {tool_key}."
        if action in BUILTIN_TOOL_SCHEMAS and action not in inline_schema_tools and action not in schemas_seen:
            return True, f"לפני הפעלת הכלי `{action}` חובה לקרוא `get_tool_info` כי הסכמה המלאה שלו אינה מופיעה בהנחיית המערכת."
        return False, None

    def _get_mcp_function_schema(self, pkg_name, func_name):
        stem = mcp_pkg_to_file_stem(self._resolve_mcp_package(pkg_name))
        for candidate in [os.path.join(MCP_TOOLS_DIR, f"{stem}.txt"), os.path.join(MCP_TOOLS_DIR, f"{mcp_pkg_to_file_stem(pkg_name)}.txt")]:
            if not os.path.exists(candidate):
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    tools = json.loads(f.read().strip())
                for tool in tools:
                    if tool.get("name") == func_name:
                        return tool.get("inputSchema", {})
            except Exception:
                pass
        return None

    def _validate_tool_call(self, action, args_dict):
        if not isinstance(args_dict, dict):
            return False, "arguments must be a JSON object."
        if action in {"system_manager", "software_manager", "file_manager", "web_manager", "screen_manager", "background_task_manager", "memory_manager", "extension_manager"}:
            ok, err = self._validate_json_schema(BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {}), args_dict)
            if not ok:
                return ok, err
            try:
                routed_action, routed_args = self._route_unified_tool(action, args_dict)
            except ValueError as e:
                return False, str(e)
            return self._validate_tool_call(routed_action, self._normalize_tool_call_args(routed_action, routed_args))
        if action == "run_mcp":
            ok, err = self._validate_json_schema(BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {}), args_dict)
            if not ok:
                return ok, err
            schema = self._get_mcp_function_schema(args_dict.get("package", ""), args_dict.get("function", ""))
            if schema:
                mcp_args = args_dict.get("arguments", {}) or {}
                return self._validate_json_schema(schema, mcp_args, "arguments.arguments")
        if action == "run_skill":
            ok, err = self._validate_json_schema(BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {}), args_dict)
            if not ok:
                return ok, err
            registry = getattr(self, "skill_registry", None) or self._load_skill_registry()
            spec = registry.get(safe_filename(args_dict.get("name", "")))
            if spec:
                return self._validate_json_schema(spec.get("parameters", {"type": "object"}), args_dict.get("arguments", {}) or {}, "arguments.arguments")
        if action in BUILTIN_TOOL_SCHEMAS:
            schema = BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {})
            return self._validate_json_schema(schema, args_dict)
        doc_path = os.path.join(TOOLS_DIR, f"{safe_filename(action)}.txt")
        if os.path.exists(doc_path):
            try:
                with open(doc_path, "r", encoding="utf-8") as f:
                    schema = json.loads(f.read().strip())
                return self._validate_json_schema(schema, args_dict)
            except Exception as e:
                return False, f"custom tool schema is invalid: {e}"
        return True, None

    def _tool_schema_hint(self, action, args_dict=None):
        try:
            schema = None
            if action in BUILTIN_TOOL_SCHEMAS:
                schema = BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {})
            if action == "extension_manager" and isinstance(args_dict, dict):
                routed_action, routed_args = self._route_unified_tool(action, args_dict)
                if routed_action != action and routed_action in BUILTIN_TOOL_SCHEMAS:
                    schema = {
                        "unified_schema": BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {}),
                        "routed_to": routed_action,
                        "routed_schema": BUILTIN_TOOL_SCHEMAS[routed_action].get("inputSchema", {})
                    }
            if action == "run_mcp" and isinstance(args_dict, dict):
                mcp_schema = self._get_mcp_function_schema(args_dict.get("package", ""), args_dict.get("function", ""))
                if mcp_schema:
                    schema = {"run_mcp": BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {}), "function_arguments_schema": mcp_schema}
            if action == "run_skill" and isinstance(args_dict, dict):
                registry = getattr(self, "skill_registry", None) or self._load_skill_registry()
                spec = registry.get(safe_filename(args_dict.get("name", "")))
                if spec:
                    schema = {"run_skill": BUILTIN_TOOL_SCHEMAS[action].get("inputSchema", {}), "skill_arguments_schema": spec.get("parameters", {})}
            if not schema:
                return ""
            return json.dumps(schema, ensure_ascii=False, indent=2)[:5000]
        except Exception:
            return ""

    def _inline_tool_feedback_limit(self, is_error=False):
        key = "max_inline_tool_error_chars" if is_error else "max_inline_tool_feedback_chars"
        default = 8000 if is_error else 16000
        try:
            return max(2000, int(self.settings.get(key, default) or default))
        except Exception:
            return default

    def _compact_tool_feedback_for_model(self, action, feedback_for_ai, is_error=False):
        if feedback_for_ai is None:
            return ""
        text = str(feedback_for_ai)
        if text.startswith("IMAGE_BASE64:"):
            return text
        limit = self._inline_tool_feedback_limit(is_error=is_error)
        if action == "get_tool_info":
            limit = max(limit, 18000)
        if len(text) <= limit:
            return text
        head_len = max(1000, int(limit * 0.68))
        tail_len = max(700, limit - head_len - 260)
        head = text[:head_len].rstrip()
        tail = text[-tail_len:].lstrip() if tail_len > 0 else ""
        return (
            f"{head}\n\n"
            f"[SMARTI_TOOL_OUTPUT_COMPACTED: omitted {len(text) - len(head) - len(tail)} chars from the middle. "
            "Full redacted output is retained in the internal tool transcript.]\n\n"
            f"{tail}"
        )

    def _append_tool_feedback(self, current_messages, ai_response_text, action, feedback_for_ai):
        is_error = str(feedback_for_ai).startswith("ERROR:")
        if not is_error and str(feedback_for_ai).startswith("ATTACHMENT_JSON:"):
            self._append_attachment_tool_feedback(current_messages, ai_response_text, action, str(feedback_for_ai).split(":", 1)[1])
            return
        raw_feedback_for_ai = feedback_for_ai
        feedback_for_ai = self._compact_tool_feedback_for_model(action, feedback_for_ai, is_error=is_error)
        if is_error:
            feedback_payload = (
                self._wrap_tool_output_for_model(action, feedback_for_ai, is_error=True)
                + "\n\n[הנחיית מערכת: הפעולה נכשלה. אל תחזור על אותה קריאה זהה. אם המשתמש ביקש במפורש אפליקציה, כלי או דרך ביצוע מסוימת, אל תוותר אחרי כשל ראשון: אבחן את השגיאה, שלוף סכמה אם צריך, ונסה דרך בטוחה אחרת בתוך אותה מטרה. מעבר לפתרון חלופי מותר רק אחרי כשל חוזר ברור, כלי כבוי, חסימת הרשאות או דחיית משתמש, ואז יש להסביר זאת למשתמש בקצרה.]"
            )
        else:
            feedback_payload = self._wrap_tool_output_for_model(action, feedback_for_ai, is_error=False)

        if not is_error and str(raw_feedback_for_ai).startswith("IMAGE_BASE64:"):
            parts = str(raw_feedback_for_ai).split(":", 2)
            if len(parts) == 3:
                mime_type, b64_data = parts[1], parts[2]
            else:
                mime_type, b64_data = "image/png", str(raw_feedback_for_ai).split(":", 1)[1]
            image_text = self._wrap_tool_output_for_model(action, "[תמונה צורפה לניתוח]", is_error=False)
            if self.mode == "gemini":
                current_messages.append({"role": "model", "parts": [{"text": ai_response_text}]})
                current_messages.append({"role": "user", "parts": [{"text": image_text}, {"inlineData": {"mimeType": mime_type, "data": b64_data}}]})
            elif self.mode == "anthropic":
                current_messages.append({"role": "assistant", "content": ai_response_text})
                current_messages.append({"role": "user", "content": [
                    {"type": "text", "text": image_text},
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64_data}}
                ]})
            else:
                current_messages.append({"role": "assistant", "content": ai_response_text})
                current_messages.append({"role": "user", "content": [
                    {"type": "text", "text": image_text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
                ]})
            return

        if self.mode == "gemini":
            current_messages.append({"role": "model", "parts": [{"text": ai_response_text}]})
            current_messages.append({"role": "user", "parts": [{"text": feedback_payload}]})
        else:
            current_messages.append({"role": "assistant", "content": ai_response_text})
            current_messages.append({"role": "user", "content": feedback_payload})

    def _estimate_agent_task_complexity(self, user_text):
        return 0

    def _fallback_task_plan(self, objective):
        return [
            "להבין את המטרה והאילוצים",
            "לאסוף את המידע או המצב הדרוש לפני פעולה",
            "לבצע את הצעדים הנדרשים לפי התוצאות שהתקבלו",
            "לאמת שהתוצאה תואמת לבקשה",
            "להחזיר סיכום קצר וברור למשתמש",
        ]

    def _fallback_verification_points(self):
        return [
            "Verify that the latest observable state or output matches the requested result.",
            "If the result depends on files, UI, system state, web data, or command output, inspect that source directly before the final answer.",
        ]

    def _fallback_contingencies(self):
        return [
            "If a tool schema is unclear or validation fails, call get_tool_info before retrying.",
            "If a check disproves progress, retry with corrected parameters or call agent_planner with intent=replan.",
            "Ask the user only when required information or permission cannot be obtained with safe discovery tools.",
        ]

    def _extract_first_json_object_text(self, text):
        text = (text or "").strip()
        fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        decoder = json.JSONDecoder()
        for idx, ch in enumerate(text):
            if ch != "{":
                continue
            try:
                obj, end = decoder.raw_decode(text[idx:])
            except Exception:
                continue
            if isinstance(obj, dict):
                return text[idx:idx + end].strip()
        return ""

    def _model_task_plan(self, objective, current_model, context=""):
        context_block = f"\n\nמידע קיים לתכנון מחדש/המשך:\n{context[:2200]}" if str(context or "").strip() else ""
        planner_prompt = (
            "אתה Planner פנימי של סמארטי. אל תפעיל כלים ואל תענה למשתמש.\n"
            "Create a practical, detailed workflow for the task. Return JSON only in this exact shape:\n"
            "{\"steps\":[\"...\"],\"verification_points\":[\"...\"],\"contingencies\":[\"...\"],\"risk\":\"low|medium|high\",\"notes\":\"...\"}\n"
            "The workflow must include concrete discovery/setup steps when environment, files, UI state, previous output, or tool schema are uncertain.\n"
            "verification_points must define what evidence proves partial/final success, including tool-based checks when needed.\n"
            "contingencies must cover likely failures, schema errors, missing permissions, unavailable files/UI, and when to retry, replan, or ask the user.\n"
            "Use 4-9 operational steps when useful; avoid generic filler and do not expose hidden reasoning.\n"
            "אם מדובר בתכנון מחדש/המשך, התבסס על המידע הקיים ושנה אסטרטגיה במקום לחזור מכנית על אותה דרך.\n"
            "אם יש אי-ודאות לגבי סביבת העבודה, קבצים, קוד, חלונות, מצב מערכת, סכמת כלי, תוכן קיים או תוצאה קודמת, "
            "אל תנחש: התחל בשלב discovery קצר ללמידת הסביבה, כגון בדיקת סכמה, חיפוש/קריאת קובץ, git status, בדיקת מסך/חלון, "
            "בדיקת תהליכים או איסוף מצב רלוונטי. רק אחר כך תכנן פעולה משנה.\n\n"
            f"משימה:\n{objective}"
            f"{context_block}"
        )
        if self.mode == "gemini":
            messages = [{"role": "user", "parts": [{"text": planner_prompt}]}]
        else:
            messages = [
                {"role": "system", "content": "Internal planner. Return compact JSON only."},
                {"role": "user", "content": planner_prompt}
            ]
        try:
            self._trace_agent_phase("planner", f"model_request model={current_model}")
            raw, usage_dict = self._handle_api_request_with_retry(current_model, messages)
            self._log_usage(current_model, usage_dict)
            json_text = self._extract_first_json_object_text(raw)
            data = json.loads(json_text) if json_text else {}
            steps = [re.sub(r'\s+', ' ', str(step)).strip() for step in data.get("steps", []) if str(step).strip()]
            if steps:
                risk = str(data.get("risk", "medium") or "medium")
                verification_points = [
                    re.sub(r'\s+', ' ', str(point)).strip()
                    for point in data.get("verification_points", [])
                    if str(point).strip()
                ]
                contingencies = [
                    re.sub(r'\s+', ' ', str(item)).strip()
                    for item in data.get("contingencies", [])
                    if str(item).strip()
                ]
                self._trace_agent_phase("planner", f"model_result steps={len(steps[:7])} risk={risk} raw_chars={len(raw or '')}")
                return (
                    steps[:9],
                    verification_points[:8] or self._fallback_verification_points(),
                    contingencies[:8] or self._fallback_contingencies(),
                    risk,
                    str(data.get("notes", "") or "")[:500],
                    True,
                )
        except Exception as e:
            if "CANCELLED_BY_USER" in str(e):
                raise SmartiCancelled("CANCELLED_BY_USER")
            if self._is_budget_exception(e):
                raise
            self._trace_agent_phase("planner", f"model_skipped error={redact_sensitive_text(str(e), self.settings)[:300]}")
            logging.warning(f"Task planner skipped: {e}")
        return self._fallback_task_plan(objective), self._fallback_verification_points(), self._fallback_contingencies(), "medium", "", False

    def _base_task_state(self, objective, planner_enabled=False):
        return {
            "objective": objective,
            "complexity_score": 0,
            "planner_enabled": bool(planner_enabled),
            "used_model_planner": False,
            "planner_source": "none",
            "planner_request_reason": "",
            "risk": "medium" if planner_enabled else "low",
            "planner_notes": "",
            "plan_steps": [],
            "verification_points": [],
            "contingencies": [],
            "planner_revisions": 0,
            "current_step_idx": 0,
            "completed_steps": [],
            "observations": [],
            "failures": [],
            "evaluations": 0,
            "last_evaluation": "",
            "compactions": 0,
        }

    def _initialize_direct_task_state(self, objective):
        state = self._base_task_state(objective, planner_enabled=False)
        self._trace_agent_phase(
            "planner",
            "available_for_model_decision auto_start=false"
        )
        return state

    def _planner_context_for_replan(self, task_state, reason=""):
        if not task_state:
            return ""
        current_plan = "\n".join(
            f"{idx}. {step}"
            for idx, step in enumerate((task_state.get("plan_steps") or [])[:9], start=1)
        ) or "אין תוכנית קודמת."
        verification_points = "\n".join(
            f"- {point}" for point in (task_state.get("verification_points") or [])[:8]
        ) or "אין נקודות אימות קודמות."
        contingencies = "\n".join(
            f"- {item}" for item in (task_state.get("contingencies") or [])[:8]
        ) or "אין תרחישי כשל קודמים."
        recent_obs = "\n".join(task_state.get("observations", [])[-8:]) or "אין תצפיות."
        failures = "\n".join(task_state.get("failures", [])[-6:]) or "אין כשלים."
        return (
            f"סיבת התכנון/תכנון מחדש: {reason or 'לא צוינה'}\n"
            f"תוכנית קודמת:\n{current_plan}\n"
            f"נקודות אימות קודמות:\n{verification_points}\n"
            f"תרחישי כשל קודמים:\n{contingencies}\n"
            f"תצפיות אחרונות:\n{recent_obs}\n"
            f"כשלים/אזהרות:\n{failures}\n"
            f"הערכת Evaluator אחרונה: {task_state.get('last_evaluation', '') or 'אין'}"
        )

    def _activate_model_requested_planner(self, task_state, planner_args, current_model, is_background_task=False, show_step=True):
        task_state = task_state or self._base_task_state("", planner_enabled=False)
        if not self.settings.get("enable_hierarchical_agent", True):
            self._trace_agent_phase("planner", "model_request_ignored reason=disabled")
            return task_state, "Planner disabled by settings. Continue without a hierarchical plan."

        args = planner_args if isinstance(planner_args, dict) else {}
        objective = task_state.get("objective", "")
        reason = re.sub(r'\s+', ' ', str(args.get("reason", "") or "")).strip()[:500]
        intent = str(args.get("intent", "") or "").strip().lower()
        mode = str(args.get("mode", "auto") or "auto").strip().lower()
        risk = str(args.get("risk", "medium") or "medium").strip().lower()
        if risk not in {"low", "medium", "high"}:
            risk = "medium"
        replanning = bool(task_state.get("planner_enabled"))
        if intent not in {"initial_plan", "continue_plan", "replan"}:
            intent = "replan" if replanning else "initial_plan"
        provided_steps = [
            re.sub(r'\s+', ' ', str(step)).strip()
            for step in (args.get("steps") or [])
            if str(step).strip()
        ]
        provided_verification_points = [
            re.sub(r'\s+', ' ', str(point)).strip()
            for point in (args.get("verification_points") or [])
            if str(point).strip()
        ]
        provided_contingencies = [
            re.sub(r'\s+', ' ', str(item)).strip()
            for item in (args.get("contingencies") or [])
            if str(item).strip()
        ]

        self._emit_agent_phase(
            "planner",
            f"requested_by_model intent={intent} mode={mode} provided_steps={len(provided_steps)} reason={reason[:250]}",
            status_text="מעדכן תוכנית..." if replanning else "מתכנן שלבי ביצוע...",
            show_step=bool(show_step) and not is_background_task,
        )

        notes = reason
        used_model_planner = False
        source = "replan_controller" if replanning else "controller"
        if provided_steps and mode != "ask_planner":
            steps = provided_steps[:9]
            verification_points = provided_verification_points[:8] or self._fallback_verification_points()
            contingencies = provided_contingencies[:8] or self._fallback_contingencies()
        elif not is_background_task:
            replan_context = self._planner_context_for_replan(task_state, reason=reason) if replanning else ""
            steps, verification_points, contingencies, risk, notes, used_model_planner = self._model_task_plan(objective, current_model, context=replan_context)
            source = "replan_model" if replanning else "model"
        else:
            steps = self._fallback_task_plan(objective)
            verification_points = self._fallback_verification_points()
            contingencies = self._fallback_contingencies()
            source = "replan_local" if replanning else "local"

        if not steps:
            steps = self._fallback_task_plan(objective)
            verification_points = verification_points or self._fallback_verification_points()
            contingencies = contingencies or self._fallback_contingencies()
            source = "replan_local" if replanning else "local"

        task_state.update({
            "planner_enabled": True,
            "used_model_planner": bool(used_model_planner),
            "planner_source": source,
            "planner_request_reason": reason,
            "risk": risk,
            "planner_notes": notes,
            "plan_steps": steps[:9],
            "verification_points": verification_points[:8],
            "contingencies": contingencies[:8],
            "planner_revisions": int(task_state.get("planner_revisions", 0) or 0) + (1 if replanning else 0),
            "current_step_idx": 0,
            "completed_steps": [],
            "evaluations": 0,
            "last_evaluation": "",
        })
        self._trace_agent_phase(
            "planner",
            f"complete intent={intent} source={source} steps={len(task_state.get('plan_steps', []))} risk={risk} revisions={task_state.get('planner_revisions', 0)}"
        )
        return task_state, "Planner updated." if replanning else "Planner activated."

    def _task_state_summary(self, task_state, include_guidance=True):
        if not task_state or not task_state.get("planner_enabled"):
            return ""
        steps = task_state.get("plan_steps", []) or []
        current_idx = min(max(0, int(task_state.get("current_step_idx", 0) or 0)), max(0, len(steps) - 1)) if steps else 0
        plan_lines = []
        for idx, step in enumerate(steps[:9], start=1):
            marker = "current" if idx - 1 == current_idx else ("done" if step in task_state.get("completed_steps", []) else "pending")
            plan_lines.append(f"{idx}. [{marker}] {step}")
        verification_lines = "\n".join(
            f"- {point}" for point in (task_state.get("verification_points") or [])[:8]
        ) or "- Verify observable progress and final state before answering."
        contingency_lines = "\n".join(
            f"- {item}" for item in (task_state.get("contingencies") or [])[:8]
        ) or "- On schema errors, call get_tool_info; on failed checks, retry or replan."
        recent_obs = "\n".join(task_state.get("observations", [])[-5:]) or "אין עדיין תצפיות."
        failures = "\n".join(task_state.get("failures", [])[-3:]) or "אין כשלים משמעותיים."
        guidance = (
            "\nהנחיות: פעל לפי התוכנית בגמישות. אם עובדות חדשות משנות את הדרך, עדכן אסטרטגיה. "
            "הרץ במקביל רק כלים עצמאיים לקריאה בלבד; פעולות כתיבה, מערכת, אימייל, GUI או הרשאות רצות אחת-אחת."
            if include_guidance else ""
        )
        return (
            "[SMARTI_TASK_STATE_BEGIN]\n"
            f"Objective: {task_state.get('objective', '')[:900]}\n"
            f"Mode: {'hierarchical' if task_state.get('planner_enabled') else 'direct'} | Risk: {task_state.get('risk', 'medium')} | Planner: {task_state.get('planner_source') or ('model' if task_state.get('used_model_planner') else 'local')}\n"
            f"Plan:\n" + ("\n".join(plan_lines) if plan_lines else "אין תוכנית נפרדת.") + "\n"
            f"Verification points:\n{verification_lines}\n"
            f"Contingencies:\n{contingency_lines}\n"
            f"Recent observations:\n{recent_obs}\n"
            f"Recent failures:\n{failures}"
            f"{guidance}\n"
            "[SMARTI_TASK_STATE_END]"
        )

    def _append_internal_planner_feedback(self, current_messages, tool_turn_text, task_state, planner_feedback):
        payload = (
            "[SMARTI_PLANNER_BEGIN]\n"
            f"{planner_feedback}\n"
            "המשך כעת לפי מצב המשימה. אל תציג את מצב המשימה או את הודעת ה-Planner למשתמש.\n"
            "[SMARTI_PLANNER_END]\n\n"
            f"{self._task_state_summary(task_state, include_guidance=True)}"
        )
        if self.mode == "gemini":
            current_messages.append({"role": "model", "parts": [{"text": tool_turn_text}]})
            current_messages.append({"role": "user", "parts": [{"text": payload}]})
        else:
            current_messages.append({"role": "assistant", "content": tool_turn_text})
            current_messages.append({"role": "user", "content": payload})

    def _append_task_state_message(self, current_messages, task_state, include_guidance=True):
        summary = self._task_state_summary(task_state, include_guidance=include_guidance)
        if summary:
            if self.mode == "gemini" and current_messages and current_messages[-1].get("role") == "user":
                current_messages[-1].setdefault("parts", []).append({"text": summary})
            elif self.mode != "gemini" and current_messages and current_messages[-1].get("role") == "user" and isinstance(current_messages[-1].get("content"), str):
                current_messages[-1]["content"] = current_messages[-1].get("content", "") + "\n\n" + summary
            else:
                self._append_user_feedback_message(current_messages, summary)

    def _message_text_for_budget(self, message):
        if not isinstance(message, dict):
            return str(message)
        if "content" in message:
            content = message.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if "text" in block:
                        parts.append(str(block.get("text", "")))
                    elif block.get("type") in {"image", "document", "input_file", "image_url"}:
                        parts.append(f"[{block.get('type')} attachment]")
                return "\n".join(parts)
            return str(content)
        parts = message.get("parts", [])
        if isinstance(parts, list):
            text_parts = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                if "text" in part:
                    text_parts.append(str(part.get("text", "")))
                elif "inlineData" in part or "fileData" in part:
                    text_parts.append("[attachment]")
            return "\n".join(text_parts)
        return str(message)

    def _messages_char_budget(self, messages):
        return sum(len(self._message_text_for_budget(msg)) for msg in messages or [])

    def _compact_current_messages_if_needed(self, current_messages, task_state, iteration):
        if not current_messages or not task_state:
            return
        if self.settings.get("preserve_current_task_tool_context", True):
            task_state["compactions_skipped"] = int(task_state.get("compactions_skipped", 0) or 0) + 1
            logging.info(
                f"Agent inline context compaction skipped at iteration {iteration}; "
                "current task tool context is preserved by settings."
            )
            return
        try:
            compact_after = int(self.settings.get("agent_context_compact_after_loops", 4) or 4)
            max_messages = int(self.settings.get("agent_inline_history_message_limit", 24) or 24)
            max_chars = int(self.settings.get("agent_inline_history_chars", 52000) or 52000)
        except Exception:
            compact_after, max_messages, max_chars = 4, 24, 52000
        if iteration < max(2, compact_after):
            return
        if len(current_messages) <= max_messages and self._messages_char_budget(current_messages) <= max_chars:
            return
        tail_keep = 10 if task_state.get("planner_enabled") else 8
        progress = (
            "[SMARTI_PROGRESS_BEGIN]\n"
            "היסטוריית הכלים הישנה קוצרה כדי לחסוך טוקנים. המשך לפי מצב המשימה והתצפיות האחרונות.\n"
            f"{self._task_state_summary(task_state, include_guidance=True)}\n"
            "[SMARTI_PROGRESS_END]"
        )
        if self.mode == "gemini":
            tail = current_messages[-tail_keep:]
            current_messages[:] = [{"role": "user", "parts": [{"text": progress}]}] + tail
        else:
            system_messages = [m for m in current_messages if m.get("role") == "system"][:1]
            non_system = [m for m in current_messages if m.get("role") != "system"]
            tail = non_system[-tail_keep:]
            current_messages[:] = system_messages + [{"role": "user", "content": progress}] + tail
        task_state["compactions"] = int(task_state.get("compactions", 0) or 0) + 1
        logging.info(f"Agent inline context compacted at iteration {iteration}; messages={len(current_messages)}")

    def _decode_tool_call_entry(self, call_entry, pre_text, schemas_seen, call_index=0):
        json_str = (call_entry or {}).get("json_str", "")
        tool_turn_text = (call_entry or {}).get("tool_turn_text", "") or ""
        try:
            tool_call = json.loads(json_str)
            if tool_call.get("method") != "tools/call":
                return None, "ERROR: Invalid JSON Tool Call. Missing 'method': 'tools/call' inside JSON root."
            action = tool_call.get("params", {}).get("name", "")
            args_dict = tool_call.get("params", {}).get("arguments", {})
            args_dict = self._normalize_tool_call_args(action, args_dict)
        except json.JSONDecodeError as e:
            return None, f"ERROR: Invalid JSON Tool Call. Details: {e}. You MUST output exactly valid JSON objects representing tools/call requests."
        except Exception as e:
            return None, f"ERROR: Invalid tool call structure. Details: {e}"

        local_pre_text = pre_text if call_index == 0 else (call_entry or {}).get("pre_text", "")

        needs_info, info_error = self._tool_requires_info_before_use(action, args_dict, schemas_seen)
        step_text = self._normalize_step_text(local_pre_text)
        if not step_text:
            step_text = self._fallback_step_for_tool(action, args_dict, schema_check=needs_info)
        if needs_info:
            return None, f"SCHEMA_REQUIRED: {info_error} הפעל קודם get_tool_info עם tool_name מתאים, ואז המשך."

        valid_call, validation_error = self._validate_tool_call(action, args_dict)
        if not valid_call:
            schema_hint = self._tool_schema_hint(action, args_dict)
            feedback = f"ERROR: Tool call schema validation failed for '{action}'. Details: {validation_error}. Retry once with exactly the documented schema below; do not guess extra fields."
            if schema_hint:
                feedback += f"\nSCHEMA:\n{schema_hint}"
            return None, feedback

        return {
            "action": action,
            "arguments": args_dict,
            "step_text": step_text,
            "tool_turn_text": tool_turn_text,
            "index": call_index,
        }, None

    def _tool_call_attempt_for_event(self, call_entry, fallback_action="tool_parser"):
        json_str = (call_entry or {}).get("json_str", "")
        action = fallback_action
        args_dict = {}
        try:
            tool_call = json.loads(json_str)
            if isinstance(tool_call, dict):
                params = tool_call.get("params", {}) if isinstance(tool_call.get("params"), dict) else {}
                action = params.get("name") or tool_call.get("name") or tool_call.get("tool") or fallback_action
                args_dict = params.get("arguments", tool_call.get("arguments", {}))
                if not isinstance(args_dict, dict):
                    args_dict = {}
                try:
                    args_dict = self._normalize_tool_call_args(action, args_dict)
                except Exception:
                    pass
        except Exception:
            args_dict = {"raw": str(json_str or "")[:1200]} if json_str else {}
        return str(action or fallback_action), args_dict

    def _preview_step_for_tool_call_entry(self, call_entry, pre_text, schemas_seen=None, call_index=0):
        try:
            tool_call = json.loads((call_entry or {}).get("json_str", ""))
            action = tool_call.get("params", {}).get("name", "")
            args_dict = tool_call.get("params", {}).get("arguments", {})
            args_dict = self._normalize_tool_call_args(action, args_dict)
            local_pre_text = pre_text if call_index == 0 else (call_entry or {}).get("pre_text", "")
            step_text = self._normalize_step_text(local_pre_text)
            if step_text:
                return step_text
            needs_info, _ = self._tool_requires_info_before_use(action, args_dict, schemas_seen or set())
            return self._fallback_step_for_tool(action, args_dict, schema_check=needs_info)
        except Exception:
            return ""

    def _reserve_tool_call(self, call, tool_call_counts, similar_tool_signatures, allow_similar_repeat=False):
        action = call.get("action", "")
        args_dict = call.get("arguments", {}) or {}
        if getattr(self, "agent_runtime", None):
            similar_sig = self.agent_runtime.similarity_signature(action, args_dict)
            if not allow_similar_repeat and self.agent_runtime.is_similar_repeat(similar_tool_signatures, similar_sig):
                return f"ERROR: Similar repeated tool call blocked for '{action}'. שנה אסטרטגיה או סיים עם הסבר ברור."
            similar_tool_signatures.append(similar_sig)
        call_sig = hashlib.sha256(f"{action}\0{json.dumps(args_dict, sort_keys=True, ensure_ascii=False)}".encode("utf-8")).hexdigest()
        tool_call_counts[call_sig] = tool_call_counts.get(call_sig, 0) + 1
        if tool_call_counts[call_sig] > 2:
            return f"ERROR: Repeated identical tool call blocked for '{action}'. בחר אסטרטגיה אחרת או סיים עם הסבר."
        return None

    def _effective_tool_action(self, action, args_dict):
        if action in {"system_manager", "software_manager", "file_manager", "web_manager", "screen_manager", "background_task_manager", "memory_manager", "extension_manager"}:
            try:
                routed_action, routed_args = self._route_unified_tool(action, args_dict)
                return routed_action, routed_args
            except Exception:
                return action, args_dict
        return action, args_dict

    def _is_parallel_safe_tool_call(self, call):
        action, args = self._effective_tool_action(call.get("action", ""), call.get("arguments", {}) or {})
        safe_actions = {
            "get_tool_info", "search_tools", "load_skill", "smart_file_search", "git_status", "list_processes",
            "list_software", "search_memory", "internet_search", "read_website",
            "get_weather"
        }
        if action not in safe_actions:
            return False
        capability = self._capability_for_action(action)
        decision = self._policy_decision(capability)
        if decision == "ask":
            return False
        if action in {"internet_search", "read_website", "get_weather"} and decision != "allow":
            return False
        return True

    def _tool_is_mutating_or_control(self, action, args_dict):
        effective, _ = self._effective_tool_action(action, args_dict or {})
        return effective in {
            "system_command", "run_project_check", "create_python_tool", "install_mcp",
            "run_mcp", "install_skill", "install_skill_requirements", "run_skill",
            "save_text_file", "save_screenshot_to_disk", "email_manager",
            "browser_automation_manager", "computer_automation_manager",
            "schedule_background_task", "cancel_background_task", "retry_background_task",
            "open_software", "open_file_or_folder", "open_in_browser", "set_clipboard",
            "set_volume", "update_memory"
        }

    def _project_check_command_allowed(self, command):
        cmd = str(command or "").strip()
        if re.search(r'(&&|\|\||\||;|`|\$\(|>|>>)', cmd):
            return False
        allowed = [
            r"^pytest(\s|$)", r"^python(?:\.exe)?\s+-m\s+pytest(\s|$)",
            r"^npm\s+test(\s|$)", r"^npm\s+run\s+(?:test|build|lint)(\s|$)",
            r"^pnpm\s+(?:test|build|lint)(\s|$)", r"^yarn\s+(?:test|build|lint)(\s|$)"
        ]
        return any(re.match(pattern, cmd, flags=re.IGNORECASE) for pattern in allowed)

    def _execute_prepared_tool_call(self, call, schemas_seen):
        action = call.get("action", "")
        args_dict = call.get("arguments", {}) or {}
        effective_action, _ = self._effective_tool_action(action, args_dict)
        try:
            self._raise_if_cancelled()
            feedback_for_ai, message_for_user = self.execute_tool(action, args_dict)
            self._raise_if_cancelled()
        except SmartiCancelled:
            raise
        except Exception as e:
            logging.exception(f"Tool execution recovered after crash: {action}")
            feedback_for_ai, message_for_user = f"ERROR: Tool '{action}' crashed internally: {redact_sensitive_text(str(e), self.settings)}", None
        if action == "get_tool_info" and not str(feedback_for_ai).startswith("ERROR:"):
            info_name = str(args_dict.get("tool_name", "")).strip(" []'\"")
            for key in {info_name, safe_filename(info_name), self._resolve_mcp_package(info_name), mcp_pkg_to_file_stem(info_name)}:
                if key:
                    schemas_seen.add(key)
        output = feedback_for_ai if feedback_for_ai is not None else message_for_user
        status = "error" if str(output or "").startswith("ERROR") else "ok"
        if output:
            obs = "[תמונה צורפה]" if str(output).startswith("IMAGE_BASE64:") else self._truncate_tool_output(output)[:1200]
            self._record_tool_observation(action, args_dict, status, obs)
        return {
            "action": action,
            "effective_action": effective_action,
            "arguments": args_dict,
            "event_id": str(call.get("_agent_process_event_id") or ""),
            "feedback": feedback_for_ai,
            "message": message_for_user,
            "status": status,
            "step_text": call.get("step_text", ""),
            "output": output,
        }

    def _execute_tool_call_batch(self, calls, schemas_seen, parallel=False):
        if not parallel or len(calls) <= 1:
            return [self._execute_prepared_tool_call(calls[0], schemas_seen)]
        background_flag = getattr(self._execution_context, "is_background", False)
        policy_snapshot = getattr(self._execution_context, "policy_snapshot", None)
        loop_iteration = getattr(self._execution_context, "loop_iteration", None)

        def run_one(call):
            self._execution_context.is_background = background_flag
            self._execution_context.loop_iteration = loop_iteration
            if policy_snapshot is not None:
                self._execution_context.policy_snapshot = policy_snapshot
            return self._execute_prepared_tool_call(call, schemas_seen)

        max_workers = min(len(calls), max(1, int(self.settings.get("max_parallel_tool_calls", 4) or 4)))
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(run_one, call): call for call in calls}
            for future in concurrent.futures.as_completed(future_map):
                try:
                    results.append(future.result())
                except SmartiCancelled:
                    raise
                except Exception as e:
                    call = future_map[future]
                    action = call.get("action", "")
                    results.append({
                        "action": action,
                        "effective_action": self._effective_tool_action(action, call.get("arguments", {}) or {})[0],
                        "arguments": call.get("arguments", {}) or {},
                        "event_id": str(call.get("_agent_process_event_id") or ""),
                        "feedback": f"ERROR: Tool '{action}' crashed internally: {redact_sensitive_text(str(e), self.settings)}",
                        "message": None,
                        "status": "error",
                        "step_text": call.get("step_text", ""),
                        "output": str(e),
                    })
        results.sort(key=lambda item: next((
            idx for idx, call in enumerate(calls)
            if (
                str(call.get("_agent_process_event_id") or "")
                and str(call.get("_agent_process_event_id") or "") == str(item.get("event_id") or "")
            ) or (
                not str(item.get("event_id") or "")
                and call.get("action") == item.get("action")
                and call.get("arguments") == item.get("arguments")
            )
        ), 999))
        return results

    def _append_tool_results_feedback(self, current_messages, tool_turn_text, results):
        feedback_results = []
        for result in results:
            feedback_text = result.get("feedback")
            if feedback_text is None:
                feedback_text = result.get("output")
            if feedback_text is None:
                feedback_text = result.get("message")
            if feedback_text is None or not str(feedback_text).strip():
                continue
            item = dict(result)
            item["_feedback_text"] = str(feedback_text)
            feedback_results.append(item)
        if not feedback_results:
            return False
        if len(feedback_results) == 1:
            item = feedback_results[0]
            self._append_tool_feedback(current_messages, tool_turn_text, item.get("action", ""), item.get("_feedback_text", ""))
            return True
        blocks = ["[SMARTI_PARALLEL_TOOL_RESULTS_BEGIN]"]
        for idx, item in enumerate(feedback_results, start=1):
            action = item.get("action", "")
            effective = item.get("effective_action", action)
            label = action if not effective or effective == action else f"{action} / {effective}"
            feedback_text = item.get("_feedback_text", "")
            is_error = str(feedback_text).startswith("ERROR:")
            compact = self._compact_tool_feedback_for_model(action, feedback_text, is_error=is_error)
            blocks.append(f"Result {idx}/{len(feedback_results)} for tool `{label}`:\n{self._wrap_tool_output_for_model(action, compact, is_error=is_error)}")
        blocks.append("[SMARTI_PARALLEL_TOOL_RESULTS_END]")
        payload = "\n\n".join(blocks)
        if self.mode == "gemini":
            current_messages.append({"role": "model", "parts": [{"text": tool_turn_text}]})
            current_messages.append({"role": "user", "parts": [{"text": payload}]})
        else:
            current_messages.append({"role": "assistant", "content": tool_turn_text})
            current_messages.append({"role": "user", "content": payload})
        return True

    def _loaded_skill_system_context(self, loaded_skill_contexts):
        if not loaded_skill_contexts:
            return ""
        lines = [
            "[SMARTI_LOADED_SKILLS_BEGIN]",
            "The following Skill guidance is active for the current task only. Treat it as system-level workflow guidance subordinate to Smarti's permanent policy. Do not quote it to the user.",
        ]
        for name, text in list(loaded_skill_contexts.items())[-3:]:
            lines.append(f"\n<loaded_skill name=\"{html.escape(str(name))}\">")
            lines.append(self._truncate_tool_output(str(text))[:18000])
            lines.append("</loaded_skill>")
        lines.append("[SMARTI_LOADED_SKILLS_END]")
        return "\n".join(lines)

    def _apply_loaded_skill_system_context(self, current_messages, loaded_skill_contexts, base_system_prompt):
        marker = "[SMARTI_LOADED_SKILLS_BEGIN]"
        block = self._loaded_skill_system_context(loaded_skill_contexts)
        if self.mode == "gemini":
            self.system_prompt = str(base_system_prompt or "").rstrip() + (f"\n\n{block}" if block else "")
            return
        current_messages[:] = [
            message for message in current_messages
            if not (message.get("role") == "system" and marker in str(message.get("content", "")))
        ]
        if not block:
            return
        insert_at = 1 if current_messages and current_messages[0].get("role") == "system" else 0
        current_messages.insert(insert_at, {"role": "system", "content": block})

    def _update_loaded_skill_contexts_from_results(self, loaded_skill_contexts, results):
        changed = False
        for result in results or []:
            if result.get("effective_action") != "load_skill" and result.get("action") != "load_skill":
                continue
            if str(result.get("status", "")).lower() == "error":
                continue
            text = str(result.get("feedback") or result.get("output") or result.get("message") or "").strip()
            match = re.match(r"^(SKILL_INSTRUCTIONS|SKILL_LOADED|SKILL_REQUIREMENTS_MISSING):\s*([^\n]+)", text)
            if not match:
                continue
            name = safe_filename(match.group(2), "skill")
            loaded_skill_contexts[name] = text[:18000]
            changed = True
        while len(loaded_skill_contexts) > 3:
            loaded_skill_contexts.pop(next(iter(loaded_skill_contexts)))
        return changed

    def _record_results_in_task_state(self, task_state, results):
        if not task_state:
            return
        for item in results:
            action = item.get("action", "")
            effective = item.get("effective_action", action)
            status = item.get("status", "")
            step = item.get("step_text", "")
            preview = self._truncate_tool_output(item.get("output", ""))[:500].replace("\n", " ")
            line = f"- {action} | {status}"
            if effective and effective != action:
                line += f" | effective={effective}"
            if step:
                line += f" | step={step}"
            if preview:
                line += f" | {preview}"
            task_state.setdefault("observations", []).append(line[:900])
            task_state["observations"] = task_state["observations"][-18:]
            if status == "error":
                task_state.setdefault("failures", []).append(line[:700])
                task_state["failures"] = task_state["failures"][-8:]

    def _maybe_evaluate_task_progress(self, task_state, results, current_model, iteration):
        if not task_state or not task_state.get("planner_enabled") or not results:
            self._trace_agent_phase("evaluator", f"skipped iteration={iteration} reason=no_planner_or_results")
            return ""
        try:
            max_evals = int(self.settings.get("max_agent_evaluations_per_task", 4) or 4)
        except Exception:
            max_evals = 4
        unlimited_evals = bool(self.settings.get("allow_unlimited_agent_evaluations", True)) or max_evals <= 0
        if not unlimited_evals and int(task_state.get("evaluations", 0) or 0) >= max(0, max_evals):
            self._trace_agent_phase("evaluator", f"skipped iteration={iteration} reason=max_evaluations count={task_state.get('evaluations', 0)}")
            return ""
        meaningful = any(r.get("status") == "error" or self._tool_is_mutating_or_control(r.get("action", ""), r.get("arguments", {}) or {}) for r in results)
        if not meaningful and iteration % 4 != 0:
            self._trace_agent_phase("evaluator", f"skipped iteration={iteration} reason=low_signal results={len(results)}")
            return ""
        self._emit_agent_phase(
            "evaluator",
            f"start iteration={iteration} results={len(results)} meaningful={meaningful}",
            status_text="מעריך התקדמות...",
        )
        recent_results = "\n".join(
            f"- {r.get('action')} | {r.get('status')} | {self._truncate_tool_output(r.get('output', ''))[:700].replace(chr(10), ' ')}"
            for r in results[-4:]
        )
        plan = "\n".join(f"{idx}. {step}" for idx, step in enumerate(task_state.get("plan_steps", [])[:7], start=1))
        verification_points = "\n".join(
            f"- {point}" for point in (task_state.get("verification_points") or [])[:8]
        ) or "- Verify observable progress and final state before accepting completion."
        contingencies = "\n".join(
            f"- {item}" for item in (task_state.get("contingencies") or [])[:8]
        ) or "- If evidence is missing or a check fails, request a verification/discovery step or replan."
        evaluator_prompt = (
            "You are Smarti's internal progress evaluator. Do not answer the user and do not call tools directly.\n"
            "Evaluate actual evidence, not whether a tool merely ran. If evidence is insufficient, require the main agent to run a concrete verification/discovery tool next.\n"
            "Return JSON only:\n"
            "{\"status\":\"continue|verify|retry|done|ask_user\",\"step_done\":true|false,\"next_step_index\":null|1,\"evidence\":\"...\",\"guidance\":\"...\"}\n"
            "Use status=verify when another tool-based check is needed before declaring progress or completion. guidance must tell the main agent what to verify and what evidence to collect, without naming a tool unless that tool is clearly appropriate.\n"
            "Use status=retry when the last action failed or produced the wrong state. Use ask_user only when safe discovery cannot obtain the missing information or permission.\n\n"
            f"מטרה:\n{task_state.get('objective', '')[:900]}\n\n"
            f"תוכנית:\n{plan}\n\n"
            f"נקודות אימות מתוכננות:\n{verification_points}\n\n"
            f"תרחישי כשל/הסתעפויות:\n{contingencies}\n\n"
            f"תוצאות אחרונות:\n{recent_results}"
        )
        if self.mode == "gemini":
            messages = [{"role": "user", "parts": [{"text": evaluator_prompt}]}]
        else:
            messages = [
                {"role": "system", "content": "Internal evaluator. Return compact JSON only."},
                {"role": "user", "content": evaluator_prompt}
            ]
        try:
            raw, usage_dict = self._handle_api_request_with_retry(current_model, messages)
            self._log_usage(current_model, usage_dict)
            json_text = self._extract_first_json_object_text(raw)
            data = json.loads(json_text) if json_text else {}
            task_state["evaluations"] = int(task_state.get("evaluations", 0) or 0) + 1
            guidance = re.sub(r'\s+', ' ', str(data.get("guidance", "") or "")).strip()[:500]
            evidence = re.sub(r'\s+', ' ', str(data.get("evidence", "") or "")).strip()[:500]
            status = str(data.get("status", "continue") or "continue").strip().lower()
            step_done = bool(data.get("step_done"))
            next_idx = data.get("next_step_index", None)
            if data.get("step_done") and task_state.get("plan_steps"):
                idx = int(task_state.get("current_step_idx", 0) or 0)
                if 0 <= idx < len(task_state["plan_steps"]):
                    step = task_state["plan_steps"][idx]
                    if step not in task_state["completed_steps"]:
                        task_state["completed_steps"].append(step)
                if isinstance(next_idx, int) and next_idx > 0:
                    task_state["current_step_idx"] = min(next_idx - 1, max(0, len(task_state["plan_steps"]) - 1))
                else:
                    task_state["current_step_idx"] = min(idx + 1, max(0, len(task_state["plan_steps"]) - 1))
            if status in {"verify", "retry", "ask_user"} and guidance:
                task_state.setdefault("failures", []).append(f"Evaluator: {guidance}")
                task_state["failures"] = task_state["failures"][-8:]
            task_state["last_evaluation"] = guidance or evidence
            self._trace_agent_phase(
                "evaluator",
                f"result iteration={iteration} status={status} step_done={step_done} next_step_index={next_idx} evidence={evidence[:180]} guidance={guidance[:250]}"
            )
            if guidance or evidence:
                return (
                    "[SMARTI_EVALUATOR_BEGIN]\n"
                    f"status={status}\n"
                    f"evidence={evidence}\n"
                    f"guidance={guidance}\n"
                    "If status=verify, run the needed verification/discovery tool before giving a final answer.\n"
                    "[SMARTI_EVALUATOR_END]"
                )
        except Exception as e:
            if "CANCELLED_BY_USER" in str(e):
                raise SmartiCancelled("CANCELLED_BY_USER")
            if self._is_budget_exception(e):
                raise
            self._trace_agent_phase("evaluator", f"skipped iteration={iteration} error={redact_sensitive_text(str(e), self.settings)[:300]}")
            logging.warning(f"Task evaluator skipped: {e}")
        return ""

    def _should_run_final_verifier_for_task(self, task_state, final_response, tool_call_counts, iteration):
        if not final_response or str(final_response).startswith("ERROR_USER") or self._is_background_context():
            return False
        text = str(final_response).strip()
        if self._looks_like_internal_artifact(text):
            return True
        if tool_call_counts:
            return True
        if task_state and task_state.get("planner_enabled"):
            return True
        return False

    def _static_code_safety_check(self, code, capability):
        banned_calls = {"eval", "exec", "compile", "__import__", "open", "input", "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr"}
        banned_modules = {"os", "sys", "subprocess", "shutil", "socket", "requests", "urllib", "ctypes", "winreg", "pathlib"}
        source = strip_code_fences(code).encode("utf-8", "replace").decode("utf-8", "replace")
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if capability in {"computer_control", "browser_automation"}:
                    return False, "Do not use import in automation code. The allowed objects are already available in the tool environment."
                names = [alias.name.split(".")[0] for alias in getattr(node, "names", [])]
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.append(node.module.split(".")[0])
                blocked = sorted(set(names) & banned_modules)
                if blocked:
                    return False, f"ייבוא מודול חסום בקוד אוטומציה: {', '.join(blocked)}"
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if func_name in banned_calls:
                    return False, f"קריאה חסומה בקוד אוטומציה: {func_name}"
            if isinstance(node, ast.Attribute) and str(node.attr).startswith("__"):
                return False, "גישה לשדות dunder חסומה בקוד אוטומציה."
            if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
                return False, "לולאת while True חסומה כדי למנוע תקיעה."
        return True, None
