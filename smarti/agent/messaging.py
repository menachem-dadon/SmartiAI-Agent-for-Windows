"""Attachment payload handling and the main send_message agent loop."""
from .shared import *


class MessagingMixin:
    def _queue_codex_protocol_repair(self, current_messages, error, attempt):
        try:
            max_repairs = max(0, int(self.settings.get("codex_protocol_repair_attempts", 2) or 0))
        except Exception:
            max_repairs = 2
        logging.warning(
            "Codex protocol response rejected; repair attempt %s/%s: %s",
            attempt,
            max_repairs,
            error,
        )
        if attempt > max_repairs:
            return False
        self._append_user_feedback_message(current_messages, error.feedback_for_model())
        return True

    def _attachment_inline_max_bytes(self):
        try:
            mb = float(self.settings.get("attachment_inline_max_mb", 20) or 20)
        except Exception:
            mb = 20
        return max(1, int(mb * 1024 * 1024))

    def _attachment_text_excerpt_chars(self):
        try:
            return max(1000, int(self.settings.get("attachment_text_excerpt_chars", 10000) or 10000))
        except Exception:
            return 10000

    def _attachment_warning_text(self, warnings):
        warnings = [str(item).strip() for item in warnings or [] if str(item).strip()]
        if not warnings:
            return ""
        return "[SMARTI_ATTACHMENT_WARNINGS]\n" + "\n".join(f"- {item}" for item in warnings) + "\n[/SMARTI_ATTACHMENT_WARNINGS]"

    def _attachment_text_block(self, item):
        excerpt = attachment_text_excerpt(item, self._attachment_text_excerpt_chars())
        if not excerpt:
            return ""
        return (
            f"[UNTRUSTED_ATTACHED_TEXT_FILE_BEGIN name={item.get('name')} path={item.get('path')}]\n"
            f"{excerpt}\n"
            "[UNTRUSTED_ATTACHED_TEXT_FILE_END]"
        )

    def _provider_attachment_blocks(self, item):
        item = normalize_attachment(item)
        if not item:
            return [], ["Invalid attachment."]
        supported, reason = provider_attachment_support(self.mode, item)
        text_block = self._attachment_text_block(item)
        if text_block and not (item.get("kind") in {"image", "audio", "video"} or item.get("mime_type") == "application/pdf"):
            supported = True
        if not supported:
            return [], [reason]
        if text_block and self.mode == "gemini" and is_text_attachment(item):
            return [{"text": text_block}], []
        if text_block and self.mode != "gemini":
            if self.mode == "anthropic":
                return [{"type": "text", "text": text_block}], []
            return [{"type": "text", "text": text_block}], []
        max_bytes = self._attachment_inline_max_bytes()
        data, error = read_attachment_bytes(item, max_bytes=max_bytes)
        if error:
            if text_block:
                if self.mode == "gemini":
                    return [{"text": text_block}], [error]
                return [{"type": "text", "text": text_block}], [error]
            return [], [error]
        mime_type = str(item.get("mime_type") or "application/octet-stream")
        b64_data = base64.b64encode(data).decode("ascii")
        if self.mode == "gemini":
            if text_block and is_text_attachment(item):
                return [{"text": text_block}], []
            return [{"inlineData": {"mimeType": mime_type, "data": b64_data}}], []
        if self.mode == "anthropic":
            if item.get("kind") == "image":
                return [{"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64_data}}], []
            if mime_type == "application/pdf":
                return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64_data}}], []
            if text_block:
                return [{"type": "text", "text": text_block}], []
            return [], [f"Claude does not support inline upload for {mime_type} in this adapter."]
        if self.mode == "openai" or is_openai_compatible_provider(self.mode) or self.mode == "local":
            if item.get("kind") == "image":
                data_url = f"data:{mime_type};base64,{b64_data}"
                return [{"type": "image_url", "image_url": {"url": data_url}}], []
            if text_block:
                return [{"type": "text", "text": text_block}], []
            return [], [f"OpenAI-compatible Chat Completions does not support inline upload for {mime_type} in this adapter."]
        return [], [f"No attachment adapter for provider {self.mode}."]

    def _build_user_message_with_attachments(self, user_text, attachments):
        attachments = normalize_attachments(attachments)
        manifest = attachment_manifest_text(attachments)
        text = str(user_text or "").strip()
        if manifest:
            text = (text + "\n\n" + manifest).strip()
        if not attachments:
            return (
                {"role": "user", "parts": [{"text": text}]} if self.mode == "gemini" else {"role": "user", "content": text}
            )
        warnings = []
        if self.mode == "gemini":
            parts = []
            for item in attachments:
                blocks, errs = self._provider_attachment_blocks(item)
                warnings.extend(errs)
                parts.extend(blocks)
            warning_text = self._attachment_warning_text(warnings)
            final_text = (text + ("\n\n" + warning_text if warning_text else "")).strip()
            parts.append({"text": final_text or "Attached files."})
            return {"role": "user", "parts": parts}
        content = []
        for item in attachments:
            blocks, errs = self._provider_attachment_blocks(item)
            warnings.extend(errs)
            content.extend(blocks)
        warning_text = self._attachment_warning_text(warnings)
        final_text = (text + ("\n\n" + warning_text if warning_text else "")).strip()
        content.append({"type": "text", "text": final_text or "Attached files."})
        return {"role": "user", "content": content}

    def _attachment_tool_payload(self, path):
        item = attachment_from_path(path, source="agent_tool")
        if not item:
            return f"ERROR: Attachment file not found: {path}"
        return "ATTACHMENT_JSON:" + json.dumps(item, ensure_ascii=False)

    def attach_local_file_tool(self, path):
        path = os.path.abspath(str(path or "").strip(' "\''))
        if not os.path.isfile(path):
            return f"ERROR: Attachment file not found: {path}"
        allowed, err = self._ensure_cloud_upload_allowed(path)
        if not allowed:
            return err
        return self._attachment_tool_payload(path)

    def google_drive_manager(self, args):
        # Google Drive manager is parked until OAuth sign-in is reworked and re-enabled.
        return "ERROR: Google Drive integration is currently disabled."

        from .google_drive import GoogleDriveClient

        args = args if isinstance(args, dict) else {}
        action = str(args.get("action", "status") or "status").strip().lower()
        drive = getattr(self, "google_drive", None) or GoogleDriveClient(self)
        if action == "status":
            connected = bool(drive._setting("google_drive_refresh_token"))
            return json.dumps({
                "configured": drive.configured(),
                "connected": connected,
                "connected_at": self.settings.get("google_drive_connected_at", ""),
                "setup_message": "" if drive.configured() else drive.missing_setup_message(),
                "safety": "Permanent deletion is not available; trash only moves files to Google Drive trash.",
            }, ensure_ascii=False, indent=2)

        missing = drive.missing_setup_message()
        if missing:
            return f"ERROR: {missing}"

        read_actions = {"about", "list", "search", "metadata", "download", "open_web"}
        write_actions = {"upload", "update_content", "rename", "move", "copy", "create_folder", "trash", "untrash"}
        if action in read_actions:
            allowed, err = self._ensure_capability_allowed(
                "network",
                "אישור גישה ל-Google Drive",
                f"פעולה: {action}",
                risk="medium",
            )
            if not allowed:
                return err
        if action in write_actions:
            allowed, err = self._ensure_capability_allowed(
                "file_write",
                "אישור שינוי ב-Google Drive",
                f"פעולה: {action}\nקובץ: {args.get('file_id', '')}\nשם/נתיב: {args.get('name') or args.get('path') or ''}\n\nמחיקה לצמיתות חסומה; פעולת trash מעבירה לאשפה בלבד.",
                risk="high",
            )
            if not allowed:
                return err

        try:
            if action == "about":
                return json.dumps(drive.about(), ensure_ascii=False, indent=2)
            if action in {"list", "search"}:
                files = drive.list_files(
                    query=args.get("query", "") if action == "search" else args.get("query", ""),
                    page_size=args.get("page_size", 25),
                    include_trashed=bool(args.get("include_trashed", False)),
                    folder_id=str(args.get("folder_id", "") or ""),
                )
                return json.dumps({"count": len(files), "files": files}, ensure_ascii=False, indent=2)
            if action == "metadata":
                file_id = str(args.get("file_id", "") or "")
                if not file_id:
                    return "ERROR: metadata requires file_id."
                return json.dumps(drive.get_metadata(file_id), ensure_ascii=False, indent=2)
            if action == "download":
                file_id = str(args.get("file_id", "") or "")
                if not file_id:
                    return "ERROR: download requires file_id."
                output_dir = str(args.get("output_dir", "") or "").strip()
                if output_dir:
                    output_dir = os.path.abspath(output_dir)
                    allowed, err = self._ensure_write_allowed(output_dir, "שמירת קובץ שהורד מ-Google Drive")
                    if not allowed:
                        return err
                result = drive.download_file(file_id, output_dir or attachment_cache_dir(getattr(self, "active_chat_session_id", "") or "drive"))
                attachment = result.get("attachment")
                if not attachment:
                    return json.dumps(result, ensure_ascii=False, indent=2, default=str)
                return "ATTACHMENT_JSON:" + json.dumps(attachment, ensure_ascii=False)
            if action == "upload":
                path = str(args.get("path", "") or "")
                if not path:
                    return "ERROR: upload requires path."
                allowed, err = self._ensure_cloud_upload_allowed(path)
                if not allowed:
                    return err
                return json.dumps(drive.upload_file(path, parent_id=str(args.get("folder_id", "") or ""), name=str(args.get("name", "") or "")), ensure_ascii=False, indent=2)
            if action == "update_content":
                file_id = str(args.get("file_id", "") or "")
                path = str(args.get("path", "") or "")
                if not file_id or not path:
                    return "ERROR: update_content requires file_id and path."
                allowed, err = self._ensure_cloud_upload_allowed(path)
                if not allowed:
                    return err
                return json.dumps(drive.update_file_content(file_id, path, name=str(args.get("name", "") or "")), ensure_ascii=False, indent=2)
            if action == "rename":
                if not args.get("file_id") or not args.get("name"):
                    return "ERROR: rename requires file_id and name."
                return json.dumps(drive.rename(args.get("file_id"), args.get("name")), ensure_ascii=False, indent=2)
            if action == "move":
                if not args.get("file_id") or not args.get("folder_id"):
                    return "ERROR: move requires file_id and folder_id."
                return json.dumps(drive.move(args.get("file_id"), args.get("folder_id")), ensure_ascii=False, indent=2)
            if action == "copy":
                if not args.get("file_id"):
                    return "ERROR: copy requires file_id."
                return json.dumps(drive.copy(args.get("file_id"), name=str(args.get("name", "") or ""), parent_id=str(args.get("folder_id", "") or "")), ensure_ascii=False, indent=2)
            if action == "create_folder":
                if not args.get("name"):
                    return "ERROR: create_folder requires name."
                return json.dumps(drive.create_folder(args.get("name"), parent_id=str(args.get("folder_id", "") or "")), ensure_ascii=False, indent=2)
            if action == "trash":
                if not args.get("file_id"):
                    return "ERROR: trash requires file_id."
                return json.dumps(drive.trash(args.get("file_id"), True), ensure_ascii=False, indent=2)
            if action == "untrash":
                if not args.get("file_id"):
                    return "ERROR: untrash requires file_id."
                return json.dumps(drive.trash(args.get("file_id"), False), ensure_ascii=False, indent=2)
            if action == "open_web":
                if not args.get("file_id"):
                    return "ERROR: open_web requires file_id."
                return json.dumps(drive.open_web(args.get("file_id")), ensure_ascii=False, indent=2)
            return f"ERROR: Unsupported google_drive_manager action: {action}"
        except Exception as e:
            return f"ERROR: Google Drive {action} failed: {e}"

    def _append_attachment_tool_feedback(self, current_messages, ai_response_text, action, payload):
        try:
            item = normalize_attachment(json.loads(str(payload or "")))
        except Exception as e:
            self._append_tool_feedback(current_messages, ai_response_text, action, f"ERROR: Invalid attachment payload: {e}")
            return
        manifest = attachment_manifest_text([item])
        self.conversation_attachments = merge_conversation_attachments(
            getattr(self, "conversation_attachments", []),
            [item],
            self.settings.get("conversation_attachments_limit", 80),
        )
        if self.mode == "gemini":
            message = self._build_user_message_with_attachments(f"Tool attached a local file for analysis.\n\n{manifest}", [item])
            current_messages.append({"role": "model", "parts": [{"text": ai_response_text}]})
            current_messages.append(message)
        else:
            message = self._build_user_message_with_attachments(f"Tool attached a local file for analysis.\n\n{manifest}", [item])
            current_messages.append({"role": "assistant", "content": ai_response_text})
            current_messages.append(message)

    def send_message(self, user_text, is_background_task=False, cancel_event=None, attachments=None):
        lock_acquired = self._agent_lock.acquire(blocking=False)
        if not lock_acquired:
            return "ERROR_USER: סמארטי כבר מבצע משימה אחרת. נסה שוב בעוד רגע או בטל את הפעולה הפעילה."
        missing_context_value = object()
        previous_background_flag = getattr(self._execution_context, "is_background", False)
        previous_policy_snapshot = getattr(self._execution_context, "policy_snapshot", None)
        previous_cancel_event = getattr(self._execution_context, "cancel_event", missing_context_value)
        previous_task_id = getattr(self._execution_context, "current_task_id", missing_context_value)
        previous_task_objective = getattr(self._execution_context, "current_task_objective", missing_context_value)
        run_cancel_event = cancel_event if cancel_event is not None else threading.Event()
        iteration = 0
        final_response = ""
        final_response_verified = False
        final_verification_tool_requests = 0
        chat_turn_recorded = False
        current_model = ""
        task_state = None
        codex_protocol_repair_streak = 0
        sleep_prevention_active = False
        resume_checkpoint = None
        checkpoint_should_keep = False
        checkpoint_task_id = ""
        runtime_base_system_prompt = getattr(self, "system_prompt", "")
        loaded_skill_contexts = {}
        self._current_agent_process_events = []
        self._current_agent_process_started_at = time.time()
        self._pending_canvas_artifacts = []
        try:
            if self.settings.get("prevent_sleep_during_active_task", True):
                sleep_prevention_active = self._set_system_sleep_prevention(True)
            user_text = str(user_text or "")
            attachments = normalize_attachments(attachments or [])
            if not is_background_task and not attachments and self._is_resume_request(user_text):
                resume_checkpoint = self._load_task_checkpoint()
                if resume_checkpoint:
                    if self.status_callback:
                        self.status_callback("ממשיך מהנקודה האחרונה שנשמרה...")
                    self._restore_task_checkpoint_context(resume_checkpoint)
                    user_text = str(resume_checkpoint.get("user_text") or user_text)
                    attachments = normalize_attachments(resume_checkpoint.get("attachments") or [])
            if attachments:
                self.conversation_attachments = merge_conversation_attachments(
                    getattr(self, "conversation_attachments", []),
                    attachments,
                    self.settings.get("conversation_attachments_limit", 80),
                )
            if resume_checkpoint:
                history_user_text = str(resume_checkpoint.get("history_user_text") or user_text).strip()
            else:
                current_manifest = attachment_manifest_text(attachments, title="Files attached to this turn")
                history_user_text = (user_text + ("\n\n" + current_manifest if current_manifest else "")).strip()
            if is_background_task:
                history_user_text = f"[משימת רקע שהופעלה אוטומטית ברקע / Background task executed automatically]:\n{history_user_text}"
            self._execution_context.is_background = is_background_task
            self._execution_context.cancel_event = run_cancel_event
            if is_background_task and getattr(self._execution_context, "current_task_id", None):
                checkpoint_task_id = self._execution_context.current_task_id
            else:
                self._execution_context.current_task_id = str((resume_checkpoint or {}).get("task_id") or uuid.uuid4().hex[:12])
                checkpoint_task_id = self._execution_context.current_task_id
            self._execution_context.current_task_objective = (history_user_text or user_text)[:700]
            if not is_background_task:
                self._foreground_cancel_event = run_cancel_event
                self.cancel_event = run_cancel_event
            if not self._ensure_active_provider_api_key():
                provider_label = self._provider_display_name(self.settings.get("api_mode", getattr(self, "mode", "")))
                if normalize_provider_name(self.settings.get("api_mode", "")) == CODEX_SIGNIN_PROVIDER:
                    detail = str(getattr(self, "_codex_connection_message", "") or "לא מחובר עם ChatGPT / Codex.")
                    final_response = f"ERROR_USER: {detail} יש לפתוח את ההגדרות וללחוץ על 'התחבר עם ChatGPT / Codex'."
                else:
                    final_response = f"ERROR_USER: חסר מפתח API של {provider_label}. הזן מפתח בהגדרות או בחלון שנפתח כדי להמשיך."
                return final_response
            try:
                if getattr(self, "memory_manager", None):
                    self.memory_manager.capture_critical_user_details(history_user_text or user_text, source="critical_preflight")
            except Exception as e:
                logging.warning(f"Critical memory capture skipped: {e}")

            if resume_checkpoint:
                self.system_prompt = str(resume_checkpoint.get("system_prompt") or getattr(self, "system_prompt", "") or self._load_system_prompt(user_text, log_memory_usage=True))
            else:
                self.refresh_extension_catalogs_if_changed(rebuild_prompt=False)
                self.system_prompt = self._load_system_prompt(user_text, log_memory_usage=True)
            runtime_base_system_prompt = self.system_prompt
            try:
                configured_iterations = int(self.settings.get("max_agent_loops", 0))
            except Exception:
                configured_iterations = 0
            MAX_ITERATIONS = None if configured_iterations <= 0 or configured_iterations > 30 else max(1, configured_iterations)
            tool_call_counts = {}
            similar_tool_signatures = []
            tool_observation_start = len(getattr(self, "tool_observations", []) or [])
            schemas_seen = set()
            internal_artifact_replies = 0
            process_report_count = 0
            last_process_report = ""
            task_started = time.time()
            try:
                configured_total_timeout = int(self.settings.get("max_total_task_seconds", 0) or 0)
            except Exception:
                configured_total_timeout = 0
            total_timeout = None if configured_total_timeout <= 0 else max(5, configured_total_timeout)
            current_model = self.settings.get(f'selected_{self.mode}_model') or provider_default_model(self.mode) or "Local"
            if resume_checkpoint:
                current_model = str(resume_checkpoint.get("current_model") or current_model)
                try:
                    iteration = max(0, int(resume_checkpoint.get("iteration", 0) or 0))
                except Exception:
                    iteration = 0
                if str(resume_checkpoint.get("phase") or "") == "model_request":
                    iteration = max(0, iteration - 1)
                saved_counts = resume_checkpoint.get("tool_call_counts", {})
                tool_call_counts = dict(saved_counts) if isinstance(saved_counts, dict) else {}
                saved_signatures = resume_checkpoint.get("similar_tool_signatures", [])
                similar_tool_signatures = list(saved_signatures) if isinstance(saved_signatures, list) else []
                schemas_seen = set(str(item) for item in resume_checkpoint.get("schemas_seen", []) or [])
                try:
                    internal_artifact_replies = max(0, int(resume_checkpoint.get("internal_artifact_replies", 0) or 0))
                except Exception:
                    internal_artifact_replies = 0
                try:
                    tool_observation_start = max(0, int(resume_checkpoint.get("tool_observation_start", tool_observation_start) or tool_observation_start))
                except Exception:
                    pass

            logging.info(f"\n{'='*40}\nבקשת משתמש חדשה: {user_text}\n{'='*40}")
            if getattr(self, "agent_runtime", None):
                self.agent_runtime.trace("plan", (history_user_text or user_text)[:1000])

            if resume_checkpoint and isinstance(resume_checkpoint.get("task_state"), dict):
                task_state = copy.deepcopy(resume_checkpoint.get("task_state") or {})
            else:
                task_state = self._initialize_direct_task_state(history_user_text or user_text)

            if resume_checkpoint and isinstance(resume_checkpoint.get("current_messages"), list):
                current_messages = copy.deepcopy(resume_checkpoint.get("current_messages") or [])
            elif self.mode == "gemini":
                current_messages = [{"role": msg["role"], "parts": [{"text": msg["content"]}]} for msg in getattr(self, 'gemini_history', [])]
                current_messages.append(self._build_user_message_with_attachments(user_text, attachments))
            else:
                history_without_system = [m for m in getattr(self, 'universal_history', []) if m.get("role") != "system"]
                current_messages = [{"role": "system", "content": self.system_prompt}] + history_without_system
                current_messages.append(self._build_user_message_with_attachments(user_text, attachments))

            def checkpoint(phase, status="running", reason=""):
                return self._save_active_task_checkpoint(
                    user_text=user_text,
                    history_user_text=history_user_text,
                    attachments=attachments,
                    current_messages=current_messages,
                    iteration=iteration,
                    task_state=task_state,
                    tool_call_counts=tool_call_counts,
                    similar_tool_signatures=similar_tool_signatures,
                    schemas_seen=schemas_seen,
                    internal_artifact_replies=internal_artifact_replies,
                    current_model=current_model,
                    tool_observation_start=tool_observation_start,
                    phase=phase,
                    status=status,
                    reason=reason,
                    is_background_task=is_background_task,
                )

            def process_reports_enabled():
                return bool(
                    (self.step_callback or getattr(self, "background_task_step_callback", None))
                    and (not self._is_background_context() or getattr(self, "background_task_step_callback", None))
                )

            def emit_process_report(report, source="model", force=False):
                nonlocal process_report_count, last_process_report
                if not process_reports_enabled():
                    return False
                normalized_report = self._should_emit_agent_report(
                    report,
                    last_process_report,
                    force=force,
                )
                if not normalized_report:
                    return False
                self._emit_agent_process_event("report", text=normalized_report, source=source)
                last_process_report = normalized_report
                process_report_count += 1
                return True

            def emit_tool_process_report(model_report, calls, source="model"):
                # The first tool turn must orient the user. Later turns are
                # model-discretionary: if the model stays quiet, Smarti should
                # not invent a report for every small sequential tool step.
                report, report_source = self._select_agent_report_for_tool_turn(
                    model_report,
                    calls,
                    last_report=last_process_report,
                    report_count=process_report_count,
                    task_state=task_state,
                    iteration=iteration,
                )
                if not report:
                    return False
                return emit_process_report(
                    report,
                    source=source if report_source == "model" else "fallback",
                    force=process_report_count == 0,
                )

            checkpoint("resume_ready" if resume_checkpoint else "ready")

            while MAX_ITERATIONS is None or iteration < MAX_ITERATIONS:
                if run_cancel_event.is_set():
                    final_response = "הפעולה נעצרה לבקשת המשתמש."
                    break
                if total_timeout is not None and time.time() - task_started > total_timeout:
                    final_response = "ERROR_USER: המשימה הופסקה כי עברה את זמן הביצוע הכולל שהוגדר."
                    break
                iteration += 1
                self._execution_context.loop_iteration = iteration
                logging.info(f"--- תחילת לולאה {iteration}/{MAX_ITERATIONS if MAX_ITERATIONS is not None else 'ללא הגבלה'} ---")

                if self.status_callback:
                    self.status_callback("חושב..." if iteration == 1 else f"חושב... (שלב {iteration})")
                self._emit_agent_process_event("thinking")

                try:
                    if getattr(self, "agent_runtime", None):
                        self.agent_runtime.trace("model_request", f"iteration={iteration}, model={current_model}")
                    checkpoint("model_request")
                    ai_response_text, usage_dict = self._handle_api_request_with_retry(current_model, current_messages)
                    codex_protocol_repair_streak = 0
                    self._log_usage(current_model, usage_dict)
                    logging.info(f"תשובת מודל גולמית:\n{ai_response_text}")
                except Exception as e:
                    if isinstance(e, CodexProtocolError):
                        codex_protocol_repair_streak += 1
                        if self._queue_codex_protocol_repair(current_messages, e, codex_protocol_repair_streak):
                            if self.status_callback:
                                self.status_callback("Codex החזיר פלט לא תקין; מבקש תיקון…")
                            checkpoint("codex_protocol_repair")
                            continue
                        final_response = (
                            "ERROR_USER: Codex החזיר שוב פלט כלי בתבנית שגויה גם לאחר בקשות תיקון. "
                            "סמארטי שמר נקודת המשך כדי שלא לאבד את המשימה."
                        )
                        checkpoint_should_keep = True
                    elif "TIMEOUT" in str(e):
                        checkpoint_should_keep = True
                        final_response = "ERROR_USER: השרתים אינם מגיבים."
                    elif "CANCELLED_BY_USER" in str(e):
                        final_response = "הפעולה נעצרה לבקשת המשתמש."
                    elif isinstance(e, ApiRequestError):
                        checkpoint_should_keep = e.analysis.category in {"network", "timeout"}
                        if checkpoint_should_keep:
                            checkpoint("network_paused", status="paused_network", reason=e.analysis.category)
                        final_response = self._api_error_user_response(e.analysis)
                    elif self._is_budget_exception(e):
                        final_response = self._budget_exception_user_message(e)
                    elif "RATE_LIMIT_ABORTED" in str(e):
                        final_response = "ERROR_USER: שרתי ה-AI עמוסים מידי או שחרגת ממגבלת הקצב."
                    else:
                        final_response = f"ERROR_USER: שגיאת חיבור מול ה-API: {e}"
                    break

                ai_response_text = re.sub(r'<\|channel>thought.*?<channel\|>', '', ai_response_text, flags=re.DOTALL)
                ai_response_text = re.sub(r'<\|channel>thought.*?<\|channel>model', '', ai_response_text, flags=re.DOTALL)
                ai_response_text = re.sub(r'<think>.*?</think>', '', ai_response_text, flags=re.DOTALL).strip()

                if "%%%" in ai_response_text:
                    ai_response_text = ai_response_text.replace("%%%", "")

                parsed_tool = self.agent_runtime.extract_tool_calls(ai_response_text) if getattr(self, "agent_runtime", None) else {}
                pre_text = parsed_tool.get("pre_text", "").replace("##", "").strip()
                is_tool_call_intent = parsed_tool.get("is_tool_call_intent", False)
                tool_turn_text = parsed_tool.get("tool_turn_text", ai_response_text)
                raw_tool_calls = parsed_tool.get("tool_calls", []) or []

                if is_tool_call_intent and raw_tool_calls:
                    first_call, feedback_for_ai = self._decode_tool_call_entry(raw_tool_calls[0], pre_text, schemas_seen, call_index=0)
                    if feedback_for_ai or not first_call:
                        preview_step = self._preview_step_for_tool_call_entry(raw_tool_calls[0], pre_text, schemas_seen, call_index=0)
                        logging.warning(feedback_for_ai)
                        failed_action, failed_args = self._tool_call_attempt_for_event(raw_tool_calls[0])
                        try:
                            emit_tool_process_report(pre_text or preview_step, [{"action": failed_action, "arguments": failed_args}], source="tool_parser")
                        except Exception:
                            pass
                        failed_output = feedback_for_ai or "ERROR: Invalid tool call."
                        failed_result = {
                            "action": failed_action,
                            "arguments": failed_args,
                            "status": "error",
                            "output": failed_output,
                            "feedback": failed_output,
                        }
                        failed_event_id = uuid.uuid4().hex
                        self._emit_agent_process_event(
                            "tool_start",
                            tools=[self._agent_tool_event_item(failed_action, failed_args, event_id=failed_event_id)],
                            parallel=False,
                        )
                        self._emit_agent_process_event(
                            "tool_finish",
                            results=[self._agent_tool_event_item(
                                failed_action,
                                failed_args,
                                status="error",
                                output=failed_output,
                                feedback=failed_output,
                                event_id=failed_event_id,
                            )],
                        )
                        self._record_results_in_task_state(task_state, [failed_result])
                        self._append_tool_feedback(current_messages, tool_turn_text, "tool_parser", feedback_for_ai or "ERROR: Invalid tool call.")
                        checkpoint("tool_parser_feedback")
                        continue

                    if first_call.get("action") == "agent_planner":
                        planner_event_id = uuid.uuid4().hex
                        emit_tool_process_report(pre_text, [first_call], source="model")
                        self._emit_agent_process_event(
                            "tool_start",
                            tools=[self._agent_tool_event_item("agent_planner", first_call.get("arguments", {}) or {}, event_id=planner_event_id)],
                            parallel=False,
                        )
                        if getattr(self, "agent_runtime", None):
                            self.agent_runtime.trace(
                                "select_tool",
                                f"agent_planner {json.dumps(first_call.get('arguments', {}), ensure_ascii=False)[:1200]}"
                            )
                        task_state, planner_feedback = self._activate_model_requested_planner(
                            task_state,
                            first_call.get("arguments", {}) or {},
                            current_model,
                            is_background_task=is_background_task,
                            show_step=False,
                        )
                        self._emit_agent_process_event(
                            "tool_finish",
                            results=[self._agent_tool_event_item(
                                "agent_planner",
                                first_call.get("arguments", {}) or {},
                                status="ok",
                                output=planner_feedback,
                                event_id=planner_event_id,
                            )],
                        )
                        self._append_internal_planner_feedback(current_messages, tool_turn_text, task_state, planner_feedback)
                        if len(raw_tool_calls) > 1:
                            self._append_user_feedback_message(
                                current_messages,
                                "הנחיית מערכת: `agent_planner` הופעל. קריאות כלי נוספות מאותה תגובה לא בוצעו. "
                                "בחר עכשיו את הפעולה הבאה לפי התוכנית."
                            )
                        self._compact_current_messages_if_needed(current_messages, task_state, iteration)
                        checkpoint("planner_feedback")
                        continue

                    selected_calls = [first_call]
                    parallel = False
                    skipped_extra_calls = max(0, len(raw_tool_calls) - 1)
                    try:
                        max_parallel = max(1, int(self.settings.get("max_parallel_tool_calls", 4) or 4))
                    except Exception:
                        max_parallel = 4

                    if len(raw_tool_calls) > 1:
                        candidate_calls = [first_call]
                        extras_ok = len(raw_tool_calls) <= max_parallel
                        for idx, raw_call in enumerate(raw_tool_calls[1:max_parallel], start=1):
                            extra_call, extra_feedback = self._decode_tool_call_entry(raw_call, pre_text, schemas_seen, call_index=idx)
                            if extra_feedback or not extra_call:
                                extras_ok = False
                                break
                            candidate_calls.append(extra_call)
                        if extras_ok and len(candidate_calls) > 1 and all(self._is_parallel_safe_tool_call(call) for call in candidate_calls):
                            selected_calls = candidate_calls
                            parallel = True
                            skipped_extra_calls = max(0, len(raw_tool_calls) - len(candidate_calls))

                    parallel = parallel and len(selected_calls) > 1

                    reserve_feedback = None
                    candidate_tool_call_counts = dict(tool_call_counts)
                    candidate_similar_tool_signatures = list(similar_tool_signatures)
                    for call in selected_calls:
                        reserve_feedback = self._reserve_tool_call(
                            call,
                            candidate_tool_call_counts,
                            candidate_similar_tool_signatures,
                            allow_similar_repeat=parallel and self._is_parallel_safe_tool_call(call),
                        )
                        if reserve_feedback:
                            break
                    if reserve_feedback:
                        self._append_tool_feedback(current_messages, tool_turn_text, selected_calls[0].get("action", "tool"), reserve_feedback)
                        checkpoint("tool_reserve_feedback")
                        continue
                    tool_call_counts = candidate_tool_call_counts
                    similar_tool_signatures = candidate_similar_tool_signatures
                    for call in selected_calls:
                        call["_agent_process_event_id"] = str(call.get("_agent_process_event_id") or uuid.uuid4().hex)

                    emit_tool_process_report(pre_text, selected_calls, source="model")
                    self._emit_agent_process_event(
                        "tool_start",
                        tools=[
                            self._agent_tool_event_item(
                                call.get("action", ""),
                                call.get("arguments", {}) or {},
                                event_id=call.get("_agent_process_event_id"),
                            )
                            for call in selected_calls
                        ],
                        parallel=parallel,
                    )

                    if getattr(self, "agent_runtime", None):
                        for call in selected_calls:
                            self.agent_runtime.trace("select_tool", f"{call.get('action')} {json.dumps(call.get('arguments', {}), ensure_ascii=False)[:1200]}")

                    if self.status_callback:
                        if parallel and len(selected_calls) > 1:
                            self.status_callback(f"מפעיל {len(selected_calls)} כלים במקביל...")
                        else:
                            action = selected_calls[0].get("action", "")
                            if action == "get_tool_info":
                                self.status_callback(f"מאתחל טעינה דינמית: {selected_calls[0].get('arguments', {}).get('tool_name', '')}...")
                            else:
                                self.status_callback(f"מפעיל כלי: {action}...")

                    checkpoint("tool_execution", reason=",".join(str(call.get("action", "")) for call in selected_calls))
                    try:
                        results = self._execute_tool_call_batch(selected_calls, schemas_seen, parallel=parallel)
                    except SmartiCancelled:
                        final_response = "הפעולה נעצרה לבקשת המשתמש."
                        break
                    self._emit_agent_process_event(
                        "tool_finish",
                        results=[
                            self._agent_tool_event_item(
                                result.get("action", ""),
                                result.get("arguments", {}) or {},
                                status=result.get("status", ""),
                                output=result.get("output"),
                                feedback=result.get("feedback"),
                                message=result.get("message"),
                                event_id=result.get("event_id"),
                            )
                            for result in results
                        ],
                    )

                    if getattr(self, "agent_runtime", None):
                        for result in results:
                            self.agent_runtime.trace("observe", f"{result.get('action')}: {str(result.get('output') or '')[:1200]}")
                    self._record_results_in_task_state(task_state, results)
                    if self._update_loaded_skill_contexts_from_results(loaded_skill_contexts, results):
                        self._apply_loaded_skill_system_context(current_messages, loaded_skill_contexts, runtime_base_system_prompt)
                    checkpoint("tool_results_observed")

                    if any(result.get("feedback") or result.get("output") or result.get("message") for result in results):
                        if self.status_callback:
                            self.status_callback("מעבד תוצאות...")
                        self._append_tool_results_feedback(current_messages, tool_turn_text, results)
                        if skipped_extra_calls:
                            self._append_user_feedback_message(
                                current_messages,
                                "הנחיית מערכת: בתגובה הקודמת הופיעו קריאות כלי נוספות שלא בוצעו. "
                                "המערכת מריצה במקביל רק פעולות עצמאיות לקריאה בלבד שאינן דורשות אישור. "
                                "אם נדרש שלב נוסף, הפעל אותו עכשיו לפי התוצאות שכבר התקבלו."
                            )
                        evaluator_feedback = self._maybe_evaluate_task_progress(task_state, results, current_model, iteration)
                        if evaluator_feedback:
                            self._append_user_feedback_message(current_messages, evaluator_feedback)
                        self._compact_current_messages_if_needed(current_messages, task_state, iteration)
                        checkpoint("tool_results_feedback")
                        continue

                    final_messages = [result.get("message") for result in results if result.get("message")]
                    if final_messages:
                        final_response = str(final_messages[0])
                        break
                    final_response = "הפעולה האחרונה הושלמה, אך לא התקבל פלט להמשך."
                    break

                else:
                    if self._looks_like_internal_artifact(ai_response_text):
                        internal_artifact_replies += 1
                        cleaned = self._strip_internal_artifacts(ai_response_text)
                        if cleaned and len(cleaned) >= 12 and not self._looks_like_internal_artifact(cleaned):
                            final_response = cleaned.replace("##", "").strip()
                            logging.info("נוקה פלט פנימי מתוך תשובה סופית.")
                            break
                        if internal_artifact_replies >= 2:
                            final_response = self._fallback_final_response(user_text)
                            logging.warning("Internal artifact leaked twice; using fallback final response.")
                            break
                        logging.warning("Internal artifact leaked as final response; requesting clean user-facing answer.")
                        assistant_marker = "Internal artifact was blocked. Rewrite a clean final answer for the user only."
                        if self.mode == "gemini":
                            current_messages.append({"role": "model", "parts": [{"text": assistant_marker}]})
                        else:
                            current_messages.append({"role": "assistant", "content": assistant_marker})
                        self._append_user_feedback_message(
                            current_messages,
                            "ERROR: התגובה האחרונה חשפה פלט כלי/הנחיות פנימיות. אסור להציג למשתמש [UNTRUSTED_*], SKILL_* או tools/call. "
                            "ענה עכשיו בעברית פשוטה בתשובה סופית קצרה שמבוססת רק על תצפיות הכלים, בלי תגים פנימיים."
                        )
                        checkpoint("internal_artifact_feedback")
                        continue
                    final_response = ai_response_text.replace("##", "").strip()
                    should_verify_candidate = self._should_run_final_verifier_for_task(task_state, final_response, tool_call_counts, iteration)
                    if should_verify_candidate and not run_cancel_event.is_set():
                        allow_verification_tool = (
                            final_verification_tool_requests < 2
                            and (MAX_ITERATIONS is None or iteration < MAX_ITERATIONS)
                        )
                        try:
                            verified_response, verifier_feedback = self._verify_final_response(
                                history_user_text or user_text,
                                final_response,
                                force=bool(tool_call_counts or (task_state and task_state.get("planner_enabled"))),
                                return_continue_feedback=True,
                                allow_tool_request=allow_verification_tool,
                            )
                        except SmartiCancelled:
                            final_response = "הפעולה נעצרה לבקשת המשתמש."
                            break
                        if verifier_feedback and allow_verification_tool:
                            final_verification_tool_requests += 1
                            final_response = ""
                            self._append_user_feedback_message(current_messages, verifier_feedback)
                            checkpoint("final_verifier_requested_tool")
                            continue
                        final_response = self._strip_internal_artifacts(verified_response)
                        final_response = re.sub(r'\n+\s*בדיקת אמינות\s*:.*$', '', final_response, flags=re.DOTALL).strip()
                        if not final_response or self._looks_like_internal_artifact(final_response):
                            final_response = self._fallback_final_response(user_text)
                        final_response_verified = True
                    logging.info("לא זוהה אובייקט JSON תקין לקריאת כלי, מסיים לולאה (טקסט חופשי).")
                    break

            if MAX_ITERATIONS is not None and iteration >= MAX_ITERATIONS and not final_response:
                final_response = "ERROR_USER: סמארטי ביצע יותר מדי פעולות ברצף והופסק."

            should_verify_final = (not final_response_verified) and self._should_run_final_verifier_for_task(task_state, final_response, tool_call_counts, iteration)
            if should_verify_final and not run_cancel_event.is_set():
                try:
                    final_response = self._verify_final_response(history_user_text or user_text, final_response, force=bool(tool_call_counts or (task_state and task_state.get("planner_enabled"))))
                except SmartiCancelled:
                    final_response = "הפעולה נעצרה לבקשת המשתמש."
                final_response = self._strip_internal_artifacts(final_response)
                final_response = re.sub(r'\n+\s*בדיקת אמינות\s*:.*$', '', final_response, flags=re.DOTALL).strip()
                if not final_response or self._looks_like_internal_artifact(final_response):
                    final_response = self._fallback_final_response(user_text)
            elif not should_verify_final:
                self._trace_agent_phase("verifier", "skipped reason=not_needed_for_final_response")

            if loaded_skill_contexts:
                self._apply_loaded_skill_system_context(current_messages, {}, runtime_base_system_prompt)

            if final_response and not final_response.startswith("ERROR_USER") and not run_cancel_event.is_set():
                try:
                    new_tool_observations = list((getattr(self, "tool_observations", []) or [])[tool_observation_start:])
                    if getattr(self, "memory_manager", None):
                        self.memory_manager.auto_capture_turn(
                            history_user_text or user_text,
                            final_response,
                            tool_records=new_tool_observations,
                            is_background_task=is_background_task,
                        )
                except Exception as e:
                    logging.warning(f"Memory auto-capture skipped: {e}")

            if final_response and not final_response.startswith("ERROR_USER"):
                if self.mode == "gemini":
                    self.gemini_history.append({"role": "user", "content": history_user_text or user_text})
                    self.gemini_history.append({"role": "model", "content": final_response})
                else:
                    self.universal_history = [m for m in self.universal_history if m.get("role") != "system"]
                    self.universal_history.insert(0, {"role": "system", "content": self.system_prompt})
                    self.universal_history.append({"role": "user", "content": history_user_text or user_text})
                    self.universal_history.append({"role": "assistant", "content": final_response})
                self._compact_conversation_history()

            return final_response
        except SmartiCancelled:
            final_response = "הפעולה נעצרה לבקשת המשתמש."
            return final_response
        except Exception as e:
            if self._is_budget_exception(e):
                final_response = self._budget_exception_user_message(e)
                return final_response
            if isinstance(e, ApiRequestError):
                checkpoint_should_keep = e.analysis.category in {"network", "timeout"}
                final_response = self._api_error_user_response(e.analysis)
                return final_response
            logging.exception("Agent loop crashed unexpectedly inside send_message.")
            checkpoint_should_keep = True
            final_response = f"ERROR_USER: אירעה תקלה פנימית במהלך ביצוע הפעולה. הפרטים נשמרו בלוגים לצורך בדיקה.\n{redact_sensitive_text(str(e), self.settings)}"
            return final_response
        finally:
            if not is_background_task and final_response and not chat_turn_recorded:
                try:
                    self._record_active_chat_turn(user_text, final_response, attachments=attachments)
                    chat_turn_recorded = True
                except Exception as e:
                    logging.warning(f"Chat turn persistence failed: {e}")
            if not is_background_task and checkpoint_task_id and not checkpoint_should_keep:
                self._clear_task_checkpoint(checkpoint_task_id)
            if self.status_callback:
                self.status_callback("")
            if getattr(self, "agent_runtime", None):
                try:
                    self.agent_runtime.trace("final", str(final_response or "")[:1000])
                except Exception:
                    pass
            try:
                if runtime_base_system_prompt:
                    self.system_prompt = runtime_base_system_prompt
            except Exception:
                pass
            self._execution_context.is_background = previous_background_flag
            try:
                delattr(self._execution_context, "loop_iteration")
            except Exception:
                pass
            if previous_task_id is missing_context_value:
                try:
                    delattr(self._execution_context, "current_task_id")
                except Exception:
                    pass
            else:
                self._execution_context.current_task_id = previous_task_id
            if previous_task_objective is missing_context_value:
                try:
                    delattr(self._execution_context, "current_task_objective")
                except Exception:
                    pass
            else:
                self._execution_context.current_task_objective = previous_task_objective
            if previous_policy_snapshot is None:
                try:
                    delattr(self._execution_context, "policy_snapshot")
                except Exception:
                    pass
            else:
                self._execution_context.policy_snapshot = previous_policy_snapshot
            if previous_cancel_event is missing_context_value:
                try:
                    delattr(self._execution_context, "cancel_event")
                except Exception:
                    pass
            else:
                self._execution_context.cancel_event = previous_cancel_event
            if not is_background_task and self._foreground_cancel_event is run_cancel_event:
                self._foreground_cancel_event = None
            if sleep_prevention_active:
                self._set_system_sleep_prevention(False)
            if lock_acquired:
                try:
                    self._agent_lock.release()
                except RuntimeError:
                    pass
