"""Background task resume, recurrence, dedupe, and worker-thread scheduling."""
from .shared import *


class BackgroundRuntimeMixin:
    def resume_background_tasks(self):
        if self._background_resume_done:
            return
        self._background_resume_done = True
        self._resume_background_tasks()

    def _parse_background_datetime(self, value, fallback=None):
        try:
            text = str(value or "").strip()
            if not text:
                return fallback
            return datetime.fromisoformat(text.replace("Z", ""))
        except Exception:
            return fallback

    def _ensure_background_task_anchor(self, task):
        if not isinstance(task, dict):
            return None
        anchor = self._parse_background_datetime(task.get("anchor_run_at"))
        if anchor:
            return anchor
        anchor = self._parse_background_datetime(task.get("run_at")) or datetime.now()
        task["anchor_run_at"] = anchor.isoformat(timespec="seconds")
        return anchor

    def _background_task_interval_minutes(self, task):
        try:
            return max(1.0, float(task.get("interval_minutes") or task.get("delay_minutes") or 60))
        except Exception:
            return 60.0

    def _background_task_catch_up_window_minutes(self, task):
        raw = self.settings.get("background_recurring_catch_up_window_minutes", task.get("catch_up_window_minutes", 15))
        try:
            window_minutes = float(raw)
        except Exception:
            return 15.0
        if window_minutes < 0:
            return float("inf")
        return max(0.0, window_minutes)

    def _next_interval_run_after(self, task, after_dt):
        anchor = self._ensure_background_task_anchor(task) or after_dt
        interval_seconds = max(60.0, self._background_task_interval_minutes(task) * 60.0)
        if anchor <= after_dt:
            steps = int((after_dt - anchor).total_seconds() // interval_seconds) + 1
            anchor = anchor + timedelta(seconds=steps * interval_seconds)
        return anchor

    def _next_weekly_run_after(self, task, after_dt):
        anchor = self._ensure_background_task_anchor(task) or after_dt
        raw_days = task.get("days_of_week") or [anchor.weekday()]
        days = sorted({int(d) for d in raw_days if str(d).isdigit() and 0 <= int(d) <= 6})
        if not days:
            days = [anchor.weekday()]
        anchor_time = anchor.time().replace(microsecond=0)
        for offset in range(0, 15):
            candidate_date = after_dt.date() + timedelta(days=offset)
            candidate = datetime.combine(candidate_date, anchor_time)
            if candidate.weekday() in days and candidate > after_dt:
                return candidate
        return after_dt + timedelta(days=7)

    def _next_recurring_run_after(self, task, after_dt):
        repeat = str(task.get("repeat") or "once").strip().lower()
        if repeat == "interval":
            return self._next_interval_run_after(task, after_dt)
        if repeat == "weekly":
            return self._next_weekly_run_after(task, after_dt)
        return None

    def _reschedule_recurring_background_task(self, task, after_dt, result=None, history_status="scheduled"):
        next_dt = self._next_recurring_run_after(task, after_dt)
        if not next_dt:
            return False
        now = datetime.now()
        task["status"] = "scheduled"
        task["run_at"] = next_dt.isoformat(timespec="seconds")
        task["finished_at"] = now.isoformat(timespec="seconds")
        if result is not None:
            task["last_result"] = self._truncate_tool_output(result)
            task.setdefault("history", []).append({
                "time": now.isoformat(timespec="seconds"),
                "status": history_status,
                "result": self._truncate_tool_output(result or "")[:1200],
            })
            task["history"] = task["history"][-20:]
        self.settings["background_jobs"] = self.settings.get("background_tasks", [])
        self._save_settings()
        return True

    def _skip_missed_recurring_background_task(self, task, scheduled_dt, now):
        delay_minutes = max(0, int((now - scheduled_dt).total_seconds() // 60))
        message = (
            f"הרצה מחזורית שהוחמצה דולגה. הזמן המתוכנן היה {scheduled_dt.isoformat(timespec='seconds')} "
            f"והאיחור היה כ-{delay_minutes} דקות. ההרצה הבאה נשארה לפי השעה הקבועה."
        )
        return self._reschedule_recurring_background_task(task, now, message, history_status="skipped")

    def _should_skip_missed_recurring_background_task(self, task, scheduled_dt, now):
        repeat = str(task.get("repeat") or "once").strip().lower()
        if repeat not in {"interval", "weekly"} or now <= scheduled_dt:
            return False
        catch_up_minutes = self._background_task_catch_up_window_minutes(task)
        return (now - scheduled_dt).total_seconds() > catch_up_minutes * 60.0

    def _is_recurring_background_task(self, task):
        return str((task or {}).get("repeat") or "once").strip().lower() in {"interval", "weekly"}

    def _mark_duplicate_recurring_background_task_locked(self, task, now=None):
        if not isinstance(task, dict) or task.get("status") == "cancelled":
            return False
        now = now or datetime.now()
        message = "Skipped duplicate recurring background task with the same id; the primary schedule remains active."
        task["status"] = "cancelled"
        task["finished_at"] = now.isoformat(timespec="seconds")
        task["last_result"] = message
        task["deduplicated_at"] = now.isoformat(timespec="seconds")
        task.setdefault("history", []).append({
            "time": now.isoformat(timespec="seconds"),
            "status": "cancelled",
            "result": message,
        })
        task["history"] = task["history"][-20:]
        return True

    def _dedupe_recurring_background_tasks_locked(self, now=None):
        now = now or datetime.now()
        seen = set()
        changed = False
        active_statuses = {"scheduled", "running", "cancelling"}
        for task in self.settings.get("background_tasks", []):
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id") or "").strip()
            if not task_id or task.get("status") not in active_statuses or not self._is_recurring_background_task(task):
                continue
            if task_id in seen:
                changed = self._mark_duplicate_recurring_background_task_locked(task, now) or changed
                continue
            seen.add(task_id)
        return changed

    def _is_duplicate_recurring_background_task_locked(self, task):
        if not isinstance(task, dict) or not self._is_recurring_background_task(task):
            return False
        task_id = str(task.get("id") or "").strip()
        if not task_id or task.get("status") not in {"scheduled", "running", "cancelling"}:
            return False
        for candidate in self.settings.get("background_tasks", []):
            if candidate is task:
                return False
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("id") or "").strip() != task_id:
                continue
            if candidate.get("status") in {"scheduled", "running", "cancelling"} and self._is_recurring_background_task(candidate):
                return True
        return False

    def _resume_background_tasks(self):
        changed = False
        now = datetime.now()
        with self._background_lock:
            for task in self.settings.get("background_tasks", []):
                if task.get("status") in {"running", "cancelling"}:
                    task["status"] = "scheduled"
                    if str(task.get("repeat") or "once").strip().lower() in {"interval", "weekly"}:
                        self._ensure_background_task_anchor(task)
                        next_dt = self._next_recurring_run_after(task, now) or (now + timedelta(minutes=1))
                        task["run_at"] = next_dt.isoformat(timespec="seconds")
                    else:
                        task["run_at"] = (now + timedelta(minutes=1)).isoformat(timespec="seconds")
                    task["generation"] = int(task.get("generation", 0) or 0) + 1
                    task["recovered_at"] = now.isoformat(timespec="seconds")
                    task.setdefault("history", []).append({
                        "time": now.isoformat(timespec="seconds"),
                        "status": "scheduled",
                        "result": "Recovered after Smarti closed while the task was running.",
                    })
                    task["history"] = task["history"][-20:]
                    changed = True
            changed = self._dedupe_recurring_background_tasks_locked(now) or changed
        if changed:
            self.settings["background_jobs"] = self.settings.get("background_tasks", [])
            self._save_settings()
        for task in list(self.settings.get("background_tasks", [])):
            if task.get("status") == "scheduled":
                self._schedule_background_task_thread(task)

    def _mark_background_task(self, task_id, status, result=None):
        changed = False
        with self._background_lock:
            for task in self.settings.get("background_tasks", []):
                if task.get("id") == task_id:
                    task["status"] = status
                    task["finished_at"] = datetime.now().isoformat(timespec="seconds")
                    if result is not None: task["last_result"] = self._truncate_tool_output(result)
                    task.setdefault("history", []).append({
                        "time": datetime.now().isoformat(timespec="seconds"),
                        "status": status,
                        "result": self._truncate_tool_output(result or "")[:1200]
                    })
                    task["history"] = task["history"][-20:]
                    changed = True
                    break
        if changed:
            self.settings["background_jobs"] = self.settings.get("background_tasks", [])
            self._save_settings()

    def _get_background_task(self, task_id):
        with self._background_lock:
            for task in self.settings.get("background_tasks", []):
                if task.get("id") == task_id:
                    return task
        return None

    def _schedule_background_task_thread(self, task):
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            return
        with self._background_lock:
            if task_id in self._background_threads:
                return
            if self._is_duplicate_recurring_background_task_locked(task):
                if self._mark_duplicate_recurring_background_task_locked(task):
                    self.settings["background_jobs"] = self.settings.get("background_tasks", [])
                    self._save_settings()
                return
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

                current = self._get_background_task(task_id)
                if not current or current.get("status") != "scheduled" or int(current.get("generation", 0) or 0) != generation:
                    return
                scheduled_dt = self._parse_background_datetime(current.get("run_at"), run_at) or run_at
                now = datetime.now()
                if self._should_skip_missed_recurring_background_task(current, scheduled_dt, now):
                    if self._skip_missed_recurring_background_task(current, scheduled_dt, now):
                        if self._background_threads.get(task_id) is threading.current_thread():
                            self._background_threads.pop(task_id, None)
                        self._schedule_background_task_thread(current)
                        rescheduled = True
                    return

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
                                exists = self.chat_store.has_session(target_session_id)
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
                        res = f"{title}\n\n{message}".strip()
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
                            self._record_active_chat_turn(prompt_text, res, attachments=None, is_background_task=True, session_id=target_session_id)
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
                    
                    if success and current.get("repeat") in {"interval", "weekly"}:
                        if self._reschedule_recurring_background_task(current, datetime.now(), res, history_status="scheduled"):
                            if self._background_threads.get(task_id) is threading.current_thread():
                                self._background_threads.pop(task_id, None)
                            self._schedule_background_task_thread(current)
                            rescheduled = True
                        else:
                            self._mark_background_task(task_id, "done", res)
                    else:
                        self._mark_background_task(task_id, "done" if success else "failed", res)
                        
                    if res and "ERROR" not in res:
                        if self.settings.get("read_aloud_all"): self.speak_text(res)
                    if res and "ERROR" not in res:
                        self._emit_notification("background_task_finished", {"task": dict(current), "result": res, "session_id": target_session_id or ""})
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
        with self._background_lock:
            if task_id in self._background_threads:
                return
            self._background_threads[task_id] = t
        t.start()
