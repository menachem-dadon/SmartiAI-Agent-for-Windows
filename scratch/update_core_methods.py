import os

file_path = r"c:\Users\יהודית סיידון\Downloads\GitHub\SmartiAI-Agent-for-Windows\smarti\core.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace _record_active_chat_turn
target_record = """    def _record_active_chat_turn(self, user_text, final_response, attachments=None):
        if not getattr(self, "chat_store", None):
            return
        should_title = (
            self.chat_store.should_generate_title_for_next_turn()
            and str(final_response or "").strip()
            and not str(final_response or "").startswith("ERROR_USER:")
        )
        title = self.generate_conversation_title(user_text, final_response) if should_title else ""
        assistant_text = self._display_assistant_text_for_history(final_response)
        agent_process = self._current_agent_process_metadata()
        assistant_metadata = {"agent_process": agent_process} if agent_process else {}
        self.chat_store.add_turn(
            user_text,
            assistant_text,
            assistant_raw=final_response,
            is_error=str(final_response or "").startswith("ERROR_USER:"),
            title=title,
            context=self._chat_context_snapshot(),
            user_metadata={"attachments": normalize_attachments(attachments or [])},
            assistant_metadata=assistant_metadata,
            welcome_text=DEFAULT_WELCOME_MESSAGE,
        )"""

replacement_record = """    def _record_active_chat_turn(self, user_text, final_response, attachments=None, is_background_task=False):
        if not getattr(self, "chat_store", None):
            return
        should_title = (
            self.chat_store.should_generate_title_for_next_turn()
            and str(final_response or "").strip()
            and not str(final_response or "").startswith("ERROR_USER:")
        )
        title = self.generate_conversation_title(user_text, final_response) if should_title else ""
        assistant_text = self._display_assistant_text_for_history(final_response)
        agent_process = self._current_agent_process_metadata()
        assistant_metadata = {"agent_process": agent_process} if agent_process else {}
        user_metadata = {"attachments": normalize_attachments(attachments or [])}
        if is_background_task:
            user_metadata["triggered_by_background"] = True
            assistant_metadata["triggered_by_background"] = True
        self.chat_store.add_turn(
            user_text,
            assistant_text,
            assistant_raw=final_response,
            is_error=str(final_response or "").startswith("ERROR_USER:"),
            title=title,
            context=self._chat_context_snapshot(),
            user_metadata=user_metadata,
            assistant_metadata=assistant_metadata,
            welcome_text=DEFAULT_WELCOME_MESSAGE,
        )"""

# 2. Replace _schedule_background_task_thread
# We will match the method signature and worker setup using splitlines
target_schedule_lines = [
    "    def _schedule_background_task_thread(self, task):",
    "        task_id = task.get(\"id\")",
    "        if not task_id or task_id in self._background_threads: return",
    "        cancel_event = self._background_cancel_events.setdefault(task_id, threading.Event())",
    "        cancel_event.clear()",
    "        generation = int(task.get(\"generation\", 0) or 0)",
    "        def worker():",
    "            rescheduled = False",
    "            try:",
    "                run_at = datetime.fromisoformat(task[\"run_at\"])",
    "                delay = max(0, (run_at - datetime.now()).total_seconds())",
    "                while delay > 0:",
    "                    time.sleep(min(delay, 5))",
    "                    if cancel_event.is_set():",
    "                        current = self._get_background_task(task_id)",
    "                        if current and int(current.get(\"generation\", 0) or 0) == generation:",
    "                            self._mark_background_task(task_id, \"cancelled\", \"Cancelled before run.\")",
    "                        return",
    "                    current = self._get_background_task(task_id)",
    "                    if not current or current.get(\"status\") != \"scheduled\" or int(current.get(\"generation\", 0) or 0) != generation:",
    "                        return",
    "                    delay = max(0, (run_at - datetime.now()).total_seconds())",
    "                current = self._get_background_task(task_id)",
    "                if not current or current.get(\"status\") != \"scheduled\" or int(current.get(\"generation\", 0) or 0) != generation: return",
    "                current[\"status\"] = \"running\"",
    "                current[\"started_at\"] = datetime.now().isoformat(timespec=\"seconds\")",
    "                self._save_settings()",
    "                self._execution_context.policy_snapshot = current.get(\"policy_snapshot\", {})",
    "                if current.get(\"kind\") == \"reminder\":",
    "                    title = str(current.get(\"title\") or \"תזכורת מסמארטי\").strip()",
    "                    message = str(current.get(\"message\") or current.get(\"prompt\") or \"\").strip()",
    "                    res = f\"{title}\\n\\n{message}\".strip()",
    "                else:",
    "                    res = self.send_message(f\"[משימת רקע שקטה]: {current.get('prompt', '')}\", is_background_task=True, cancel_event=cancel_event)",
    "                current = self._get_background_task(task_id) or current",
    "                if int(current.get(\"generation\", 0) or 0) != generation:",
    "                    return",
    "                if cancel_event.is_set() or current.get(\"status\") == \"cancelling\":",
    "                    self._mark_background_task(task_id, \"cancelled\", res or \"Cancelled.\")",
    "                    return",
    "                success = bool(res and \"ERROR\" not in res)",
    "                if success and current.get(\"repeat\") == \"interval\":",
    "                    interval = max(1.0, float(current.get(\"interval_minutes\") or current.get(\"delay_minutes\") or 60))",
    "                    current[\"status\"] = \"scheduled\"",
    "                    current[\"run_at\"] = (datetime.now() + timedelta(minutes=interval)).isoformat(timespec=\"seconds\")",
    "                    current[\"finished_at\"] = datetime.now().isoformat(timespec=\"seconds\")",
    "                    current[\"last_result\"] = self._truncate_tool_output(res)",
    "                    self._save_settings()",
    "                    if self._background_threads.get(task_id) is threading.current_thread():",
    "                        self._background_threads.pop(task_id, None)",
    "                    self._schedule_background_task_thread(current)",
    "                    rescheduled = True",
    "                else:",
    "                    self._mark_background_task(task_id, \"done\" if success else \"failed\", res)",
    "                if res and \"ERROR\" not in res and self.print_callback:",
    "                    self.print_callback(res, False)",
    "                    if self.settings.get(\"read_aloud_all\"): self.speak_text(res)",
    "                if res and \"ERROR\" not in res:",
    "                    self._emit_notification(\"background_task_finished\", {\"task\": dict(current), \"result\": res})",
    "            except Exception as e:",
    "                logging.exception(\"Background task crashed unexpectedly.\")",
    "                self._recover_after_agent_crash()",
    "                self._mark_background_task(task_id, \"failed\", f\"ERROR: {e}\")",
    "            finally:",
    "                if not rescheduled:",
    "                    if self._background_threads.get(task_id) is threading.current_thread():",
    "                        self._background_threads.pop(task_id, None)",
    "                    if self._background_cancel_events.get(task_id) is cancel_event:",
    "                        self._background_cancel_events.pop(task_id, None)",
    "        t = threading.Thread(target=worker, daemon=True, name=f\"SmartiBackground-{task_id}\")",
    "        self._background_threads[task_id] = t",
    "        t.start()"
]

replacement_schedule = """    def _schedule_background_task_thread(self, task):
        task_id = task.get("id")
        if not task_id or task_id in self._background_threads: return
        cancel_event = self._background_cancel_events.setdefault(task_id, threading.Event())
        cancel_event.clear()
        generation = int(task.get("generation", 0) or 0)
        def worker():
            rescheduled = False
            target_session_id = None
            try:
                run_at = datetime.fromisoformat(task["run_at"])
                delay = max(0, (run_at - datetime.now()).total_seconds())
                while delay > 0:
                    time.sleep(min(delay, 5))
                    if cancel_event.is_set():
                        current = self._get_background_task(task_id)
                        if current and int(current.get("generation", 0) or 0) == generation:
                            self._mark_background_task(task_id, "cancelled", "Cancelled before run.")
                        return
                    current = self._get_background_task(task_id)
                    if not current or current.get("status") != "scheduled" or int(current.get("generation", 0) or 0) != generation:
                        return
                    delay = max(0, (run_at - datetime.now()).total_seconds())
                
                # Sleep is done, now we attempt to run!
                # Let's acquire the agent lock with timeout.
                acquired = self._agent_lock.acquire(timeout=60)
                if not acquired:
                    self._mark_background_task(task_id, "failed", "ERROR: Could not acquire agent lock (agent busy).")
                    return
                try:
                    current = self._get_background_task(task_id)
                    if not current or current.get("status") != "scheduled" or int(current.get("generation", 0) or 0) != generation:
                        return
                    current["status"] = "running"
                    current["started_at"] = datetime.now().isoformat(timespec="seconds")
                    self._save_settings()
                    
                    self._execution_context.policy_snapshot = current.get("policy_snapshot", {})
                    self._execution_context.current_task_id = task_id
                    
                    # 1. Resolve target conversation session ID
                    mode = current.get("conversation_mode") or "current"
                    if mode == "current":
                        active_sess = self.chat_store.active_session()
                        target_session_id = active_sess.get("id") if active_sess else None
                    elif mode == "new":
                        session = self.chat_store.create_session(set_active=False)
                        target_session_id = session.get("id")
                    elif mode == "dedicated":
                        target_session_id = current.get("target_conversation_id")
                        exists = False
                        if target_session_id:
                            with self.chat_store._lock:
                                exists = any(s.get("id") == target_session_id for s in self.chat_store.data.get("sessions", []))
                        if not exists:
                            session = self.chat_store.create_session(set_active=False)
                            target_session_id = session.get("id")
                            current["target_conversation_id"] = target_session_id
                            self._save_settings()
                    
                    # Store target_session_id in execution context so step callback can use it!
                    self._execution_context.target_session_id = target_session_id
                    
                    # Backup original active session
                    original_sess = self.chat_store.active_session()
                    original_session_id = original_sess.get("id") if original_sess else None
                    
                    # If target is different from active session, activate it!
                    if target_session_id and target_session_id != original_session_id:
                        self.activate_chat_session(target_session_id)
                    
                    if current.get("kind") == "reminder":
                        title = str(current.get("title") or "תזכורת מסמארטי").strip()
                        message = str(current.get("message") or current.get("prompt") or "").strip()
                        res = f"{title}\\n\\n{message}".strip()
                    else:
                        prompt_text = current.get('prompt', '')
                        # Emit start callback/signal
                        if getattr(self, "background_task_start_callback", None):
                            try:
                                self.background_task_start_callback(target_session_id or "", task_id, prompt_text)
                            except Exception:
                                pass
                        
                        res = self.send_message(prompt_text, is_background_task=True, cancel_event=cancel_event)
                        
                        # Record the active chat turn manually for background task!
                        try:
                            self._record_active_chat_turn(prompt_text, res, attachments=None, is_background_task=True)
                        except Exception as e:
                            logging.warning(f"Failed to record background chat turn: {e}")
                    
                    # Restore original active session
                    if original_session_id and original_session_id != self.chat_store.active_session().get("id"):
                        self.activate_chat_session(original_session_id)
                    
                    current = self._get_background_task(task_id) or current
                    if int(current.get("generation", 0) or 0) != generation:
                        return
                    if cancel_event.is_set() or current.get("status") == "cancelling":
                        self._mark_background_task(task_id, "cancelled", res or "Cancelled.")
                        if getattr(self, "background_task_finish_callback", None):
                            try: self.background_task_finish_callback(target_session_id or "", task_id, "Cancelled.", False)
                            except Exception: pass
                        return
                    
                    success = bool(res and "ERROR" not in res)
                    
                    # Emit finish callback/signal
                    if getattr(self, "background_task_finish_callback", None):
                        try:
                            self.background_task_finish_callback(target_session_id or "", task_id, res, success)
                        except Exception:
                            pass
                    
                    if success and current.get("repeat") == "interval":
                        interval = max(1.0, float(current.get("interval_minutes") or current.get("delay_minutes") or 60))
                        current["status"] = "scheduled"
                        current["run_at"] = (datetime.now() + timedelta(minutes=interval)).isoformat(timespec="seconds")
                        current["finished_at"] = datetime.now().isoformat(timespec="seconds")
                        current["last_result"] = self._truncate_tool_output(res)
                        self._save_settings()
                        if self._background_threads.get(task_id) is threading.current_thread():
                            self._background_threads.pop(task_id, None)
                        self._schedule_background_task_thread(current)
                        rescheduled = True
                    elif success and current.get("repeat") == "weekly":
                        days_of_week = current.get("days_of_week") or []
                        base_dt = datetime.fromisoformat(current["run_at"])
                        next_dt = base_dt
                        for d in range(1, 8):
                            candidate = base_dt + timedelta(days=d)
                            if candidate.weekday() in days_of_week:
                                next_dt = candidate
                                break
                        if next_dt <= base_dt:
                            next_dt = base_dt + timedelta(days=7)
                        while next_dt <= datetime.now():
                            next_dt += timedelta(days=7)
                        
                        current["status"] = "scheduled"
                        current["run_at"] = next_dt.isoformat(timespec="seconds")
                        current["finished_at"] = datetime.now().isoformat(timespec="seconds")
                        current["last_result"] = self._truncate_tool_output(res)
                        self._save_settings()
                        if self._background_threads.get(task_id) is threading.current_thread():
                            self._background_threads.pop(task_id, None)
                        self._schedule_background_task_thread(current)
                        rescheduled = True
                    else:
                        self._mark_background_task(task_id, "done" if success else "failed", res)
                        
                    if res and "ERROR" not in res and self.print_callback:
                        self.print_callback(res, False)
                        if self.settings.get("read_aloud_all"): self.speak_text(res)
                    if res and "ERROR" not in res:
                        self._emit_notification("background_task_finished", {"task": dict(current), "result": res})
                finally:
                    self._agent_lock.release()
            except Exception as e:
                logging.exception("Background task crashed unexpectedly.")
                self._recover_after_agent_crash()
                self._mark_background_task(task_id, "failed", f"ERROR: {e}")
                if getattr(self, "background_task_finish_callback", None):
                    try: self.background_task_finish_callback(target_session_id or "", task_id, f"ERROR: {e}", False)
                    except Exception: pass
            finally:
                if not rescheduled:
                    if self._background_threads.get(task_id) is threading.current_thread():
                        self._background_threads.pop(task_id, None)
                    if self._background_cancel_events.get(task_id) is cancel_event:
                        self._background_cancel_events.pop(task_id, None)
        t = threading.Thread(target=worker, daemon=True, name=f"SmartiBackground-{task_id}")
        self._background_threads[task_id] = t
        t.start()"""

# Replace _record_active_chat_turn
# Let's clean the target string to be line-ending agnostic
target_rec_lines = [line.strip() for line in target_record.splitlines()]
content_lines = content.splitlines()
rec_found = -1
for i in range(len(content_lines) - len(target_rec_lines) + 1):
    match = True
    for j in range(len(target_rec_lines)):
        if content_lines[i+j].strip() != target_rec_lines[j]:
            match = False
            break
    if match:
        rec_found = i
        break

if rec_found != -1:
    print(f"Found _record_active_chat_turn at line {rec_found}")
    content_lines[rec_found:rec_found+len(target_rec_lines)] = replacement_record.splitlines()
    content = "\\n".join(content_lines) # temp join
else:
    print("Could not find _record_active_chat_turn!")
    exit(1)

# Now, match _schedule_background_task_thread in the updated content
content_lines = content.split("\\n")
sched_found = -1
for i in range(len(content_lines) - len(target_schedule_lines) + 1):
    match = True
    for j in range(len(target_schedule_lines)):
        if content_lines[i+j].strip() != target_schedule_lines[j].strip():
            match = False
            break
    if match:
        sched_found = i
        break

if sched_found != -1:
    print(f"Found _schedule_background_task_thread at line {sched_found}")
    content_lines[sched_found:sched_found+len(target_schedule_lines)] = replacement_schedule.splitlines()
    line_ending = "\\r\\n" if "\\r\\n" in content else "\\n"
    new_content = line_ending.join(content_lines)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Replaced both methods successfully.")
else:
    print("Could not find _schedule_background_task_thread!")
    exit(1)
