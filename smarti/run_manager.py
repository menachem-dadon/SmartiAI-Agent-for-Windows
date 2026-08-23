"""Conversation-scoped concurrent run scheduler and durable event fan-out."""
from .common import *
from .attachments import normalize_attachments

from collections import deque


TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})
ACTIVE_RUN_STATUSES = frozenset({"queued", "running", "waiting_for_approval", "cancelling"})


class RunHandle:
    def __init__(self, run_id, session_id, cancel_event):
        self.run_id = str(run_id)
        self.session_id = str(session_id)
        self.cancel_event = cancel_event
        self.done_event = threading.Event()
        self.response = ""
        self.error = ""
        self.status = "queued"

    def wait(self, timeout=None):
        self.done_event.wait(timeout)
        return self.response


class ConversationRunManager:
    """Serialize work per conversation while allowing conversations in parallel."""

    def __init__(self, core):
        self.core = core
        # There is intentionally no process-wide conversation cap. Each
        # conversation is still serialized below, while independent sessions
        # receive their own lightweight worker and are bounded naturally by
        # the provider, OS and the user's machine.
        self.max_concurrent = None
        self._lock = threading.RLock()
        self._queues = {}
        self._active_by_session = {}
        self._threads = {}
        self._handles = {}
        self._subscribers = {}
        self._approval_waiters = {}
        self._closed = False
        for run in self.core.chat_store.recover_incomplete_runs():
            self._enqueue_existing(run)

    def subscribe(self, callback):
        token = uuid.uuid4().hex
        with self._lock:
            self._subscribers[token] = callback
        return token

    def unsubscribe(self, token):
        with self._lock:
            return self._subscribers.pop(str(token or ""), None) is not None

    def _emit(self, event_type, run_id, session_id, payload=None, persist=True):
        body = copy.deepcopy(payload if isinstance(payload, dict) else {})
        event = {
            "event_type": str(event_type),
            "run_id": str(run_id or ""),
            "session_id": str(session_id or ""),
            "payload": body,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        if persist and run_id:
            try:
                persisted = self.core.chat_store.append_run_event(
                    run_id, event_type, body
                )
                if isinstance(persisted, dict):
                    event["event_id"] = int(persisted.get("id", 0) or 0)
                    event["sequence"] = int(persisted.get("sequence", 0) or 0)
            except Exception:
                logging.exception("Could not persist run event %s", event_type)
        with self._lock:
            callbacks = list(self._subscribers.values())
        for callback in callbacks:
            try:
                callback(copy.deepcopy(event))
            except Exception:
                logging.exception("Run event subscriber failed")
        return event

    def submit(
        self, session_id, user_text, attachments=None, source="desktop",
        is_background_task=False, callbacks=None, metadata=None, cancel_event=None,
        workspace_id=None,
    ):
        if self._closed:
            raise RuntimeError("Run manager is shut down")
        target = str(session_id or "")
        if not target or not self.core.chat_store.has_session(target):
            target = str(self.core.chat_store.create_session(set_active=not bool(session_id))["id"])
        should_title = self.core.chat_store.should_generate_title_for_next_turn(target)
        run_metadata = copy.deepcopy(metadata if isinstance(metadata, dict) else {})
        provider_mode = normalize_provider_name(
            run_metadata.get("provider_mode")
            or self.core.settings.get("api_mode", getattr(self.core, "mode", "gemini"))
            or "gemini"
        )
        model_name = str(
            run_metadata.get("model_name")
            or self.core.settings.get(f"selected_{provider_mode}_model")
            or provider_default_model(provider_mode)
            or "Local"
        )
        capture_snapshot = getattr(self.core, "capture_run_model_snapshot", None)
        runtime_snapshot = (
            capture_snapshot(provider_mode=provider_mode, model_name=model_name)
            if callable(capture_snapshot)
            else {"mode": provider_mode, "model_name": model_name}
        )
        run_metadata.update({
            "is_background_task": bool(is_background_task),
            "should_generate_title": bool(should_title),
            "provider_mode": provider_mode,
            "model_name": model_name,
        })
        normalized_attachments = normalize_attachments(attachments or [])
        title_request = None
        if should_title:
            attachment_names = [
                item.get("name", "")
                for item in normalized_attachments
                if isinstance(item, dict) and item.get("name")
            ]
            make_title = getattr(self.core, "_local_fast_conversation_title", None)
            candidate = (
                make_title(user_text, attachment_names)
                if callable(make_title)
                else str(user_text or "").strip()
            )
            title_mode = str(
                self.core.settings.get("conversation_title_generation_mode", "ai") or "ai"
            ).strip().lower()
            if title_mode == "local":
                applied_title = self.core.chat_store.apply_initial_title(target, candidate)
            else:
                applied_title = self.core.chat_store.apply_provisional_title(target, candidate)
                title_request = {
                    "user_text": str(user_text or ""),
                    "attachment_names": attachment_names,
                    "provider_mode": provider_mode,
                    "current_model": model_name,
                }
                run_metadata["should_generate_title"] = False
            if applied_title:
                run_metadata["should_generate_title"] = False
                run_metadata["initial_title"] = applied_title
                emit_notification = getattr(self.core, "_emit_notification", None)
                if callable(emit_notification):
                    emit_notification(
                        "chat_title_updated",
                        {"session_id": target, "title": applied_title},
                    )
        run_id = self.core.chat_store.create_run(
            target,
            user_text=user_text,
            attachments=normalized_attachments,
            source=source,
            metadata=run_metadata,
            workspace_id=workspace_id,
        )
        user_metadata = {
            "attachments": normalized_attachments,
            "run_id": run_id,
            "run_status": "queued",
        }
        if is_background_task:
            user_metadata.update({"is_background_task": True, "triggered_by_background": True})
        self.core.chat_store.append_message("user", user_text, user_metadata, session_id=target)
        handle = RunHandle(run_id, target, cancel_event or threading.Event())
        work = {
            "run_id": run_id,
            "session_id": target,
            "user_text": str(user_text or ""),
            "attachments": normalized_attachments,
            "source": str(source or "desktop"),
            "is_background_task": bool(is_background_task),
            "callbacks": dict(callbacks or {}),
            "metadata": run_metadata,
            "runtime_snapshot": runtime_snapshot,
            "handle": handle,
        }
        with self._lock:
            self._handles[run_id] = handle
            self._queues.setdefault(target, deque()).append(work)
            self._schedule_next_locked(target)
        if title_request:
            schedule_title = getattr(self.core, "_schedule_conversation_title", None)
            if callable(schedule_title):
                try:
                    schedule_title(
                        target,
                        title_request["user_text"],
                        "",
                        attachment_names=title_request["attachment_names"],
                        provider_mode=title_request["provider_mode"],
                        current_model=title_request["current_model"],
                    )
                except Exception:
                    logging.exception("Could not start first-turn title generation.")
        self._emit("run_available", run_id, target, {"status": "queued"}, persist=False)
        return handle

    def _enqueue_existing(self, run):
        target = str(run.get("session_id") or "")
        run_id = str(run.get("id") or "")
        if not target or not run_id:
            return
        handle = RunHandle(run_id, target, threading.Event())
        work = {
            "run_id": run_id,
            "session_id": target,
            "user_text": str(run.get("user_text") or ""),
            "attachments": normalize_attachments(run.get("attachments") or []),
            "source": str(run.get("source") or "recovery"),
            "is_background_task": bool((run.get("metadata") or {}).get("is_background_task")),
            "callbacks": {},
            "metadata": copy.deepcopy(run.get("metadata") or {}),
            "runtime_snapshot": self._runtime_snapshot_for_metadata(run.get("metadata") or {}),
            "handle": handle,
        }
        with self._lock:
            self._handles[run_id] = handle
            self._queues.setdefault(target, deque()).append(work)
            self._schedule_next_locked(target)

    def complete_immediate(self, session_id, response, source="runtime", metadata=None):
        """Record a non-model event (for example a reminder) in the same run ledger."""
        target = str(session_id or "")
        if not target or not self.core.chat_store.has_session(target):
            target = str(self.core.chat_store.create_session(set_active=False)["id"])
        run_id = self.core.chat_store.create_run(
            target,
            user_text="",
            source=source,
            metadata=metadata,
        )
        handle = RunHandle(run_id, target, threading.Event())
        with self._lock:
            self._handles[run_id] = handle
        self.core.chat_store.transition_run(run_id, "running", expected_statuses={"queued"})
        self.core.chat_store.append_message(
            "assistant",
            str(response or ""),
            {"run_id": run_id, "is_background_task": True, "triggered_by_background": True},
            session_id=target,
        )
        handle.response = str(response or "")
        handle.status = "completed"
        self.core.chat_store.transition_run(run_id, "completed", response_text=handle.response)
        self.core.chat_store.create_attention(target, run_id, "response")
        handle.done_event.set()
        self._emit(
            "run_finished",
            run_id,
            target,
            {"status": "completed", "response": handle.response},
            persist=False,
        )
        return handle

    def _schedule_next_locked(self, session_id):
        if self._closed or session_id in self._active_by_session:
            return
        queue = self._queues.get(session_id)
        while queue:
            work = queue.popleft()
            handle = work["handle"]
            current = self.core.chat_store.run(handle.run_id)
            if not current or current.get("status") == "cancelled":
                handle.status = "cancelled"
                handle.done_event.set()
                continue
            self._active_by_session[session_id] = handle.run_id
            worker = threading.Thread(
                target=self._execute,
                args=(work,),
                name=f"smarti-run-{handle.run_id[:8]}",
                daemon=True,
            )
            self._threads[handle.run_id] = worker
            worker.start()
            break
        if queue is not None and not queue:
            self._queues.pop(session_id, None)

    def _runtime_snapshot_for_metadata(self, metadata):
        metadata = metadata if isinstance(metadata, dict) else {}
        provider_mode = normalize_provider_name(
            metadata.get("provider_mode")
            or self.core.settings.get("api_mode", getattr(self.core, "mode", "gemini"))
            or "gemini"
        )
        model_name = str(
            metadata.get("model_name")
            or self.core.settings.get(f"selected_{provider_mode}_model")
            or provider_default_model(provider_mode)
            or "Local"
        )
        capture_snapshot = getattr(self.core, "capture_run_model_snapshot", None)
        if callable(capture_snapshot):
            return capture_snapshot(provider_mode=provider_mode, model_name=model_name)
        return {"mode": provider_mode, "model_name": model_name}

    def _callback_bundle(self, work):
        external = work.get("callbacks") or {}
        run_id = work["run_id"]
        session_id = work["session_id"]

        def combine(name, event_type):
            def callback(*args):
                value = args[0] if len(args) == 1 else list(args)
                self._emit(event_type, run_id, session_id, {"value": value})
                target = external.get(name)
                if target:
                    return target(*args)
                return None
            return callback

        return {
            "status_callback": combine("status_callback", "run_status"),
            "print_callback": combine("print_callback", "run_output"),
            "step_callback": combine("step_callback", "run_step"),
            "api_key_callback": external.get("api_key_callback"),
            "ask_user_callback": external.get("ask_user_callback"),
        }

    def _execute(self, work):
        handle = work["handle"]
        run_id = handle.run_id
        session_id = handle.session_id
        response = ""
        error = ""
        try:
            if handle.cancel_event.is_set():
                self.core.chat_store.transition_run(run_id, "cancelled")
                handle.status = "cancelled"
                return
            transitioned = self.core.chat_store.transition_run(
                run_id,
                "running",
                expected_statuses={"queued"},
            )
            if not transitioned:
                current = self.core.chat_store.run(run_id) or {}
                handle.status = str(current.get("status") or "cancelled")
                return
            handle.status = "running"
            self._emit("run_started", run_id, session_id, {"status": "running"}, persist=False)
            with self.core.bind_run_context(
                run_id,
                session_id,
                cancel_event=handle.cancel_event,
                callbacks=self._callback_bundle(work),
                runtime_snapshot=work.get("runtime_snapshot"),
            ):
                self.core._execution_context.policy_snapshot = copy.deepcopy(
                    work["metadata"].get("policy_snapshot") or {}
                )
                if work["metadata"].get("task_id"):
                    self.core._execution_context.current_task_id = str(work["metadata"]["task_id"])
                response = self.core.send_message(
                    work["user_text"],
                    is_background_task=work["is_background_task"],
                    cancel_event=handle.cancel_event,
                    attachments=work["attachments"],
                    session_id=session_id,
                    run_id=run_id,
                    persist_turn=False,
                )
                if not str(response or "").strip() and not handle.cancel_event.is_set():
                    response = (
                        "ERROR_USER: המודל סיים את הבקשה בלי להחזיר תשובה. "
                        "אפשר לנסות שוב; פרטי הריצה נשמרו בלוגים."
                    )
                context = self.core._chat_context_snapshot()
                self.core._record_run_assistant_message(
                    session_id,
                    run_id,
                    work["user_text"],
                    response,
                    attachments=work["attachments"],
                    is_background_task=work["is_background_task"],
                    should_title=bool(work["metadata"].get("should_generate_title")),
                )
                self.core.chat_store.update_context(context, session_id)
            handle.response = str(response or "")
            if handle.cancel_event.is_set():
                handle.status = "cancelled"
                self.core.chat_store.transition_run(run_id, "cancelled", response_text=response)
            elif str(response or "").startswith("ERROR_USER:"):
                handle.status = "failed"
                self.core.chat_store.transition_run(run_id, "failed", response_text=response, error_text=response)
            else:
                handle.status = "completed"
                self.core.chat_store.transition_run(run_id, "completed", response_text=response)
            self.core.chat_store.create_attention(session_id, run_id, "response")
            self._emit(
                "run_finished",
                run_id,
                session_id,
                {"status": handle.status, "response": handle.response},
                persist=False,
            )
        except Exception as exc:
            error = str(exc)
            handle.error = error
            handle.status = "failed"
            logging.exception("Conversation run %s failed", run_id)
            try:
                if not str(response or "").strip():
                    response = (
                        "ERROR_USER: אירעה תקלה פנימית במהלך הריצה. "
                        "הפרטים נשמרו בלוגים ואפשר לנסות שוב."
                    )
                    display_error = getattr(
                        self.core, "_display_assistant_text_for_history", None
                    )
                    self.core.chat_store.append_message(
                        "assistant",
                        (
                            display_error(response)
                            if callable(display_error)
                            else f"שגיאה: {response.replace('ERROR_USER:', '').strip()}"
                        ),
                        {"run_id": run_id, "run_status": "failed", "is_error": True},
                        session_id=session_id,
                    )
                handle.response = str(response or "")
                self.core.chat_store.transition_run(
                    run_id,
                    "failed",
                    response_text=handle.response,
                    error_text=error,
                )
                self.core.chat_store.create_attention(session_id, run_id, "response", {"failed": True})
            except Exception:
                logging.exception("Could not persist failed run %s", run_id)
            self._emit(
                "run_finished",
                run_id,
                session_id,
                {"status": "failed", "error": error, "response": handle.response},
                persist=False,
            )
        finally:
            handle.done_event.set()
            with self._lock:
                self._threads.pop(run_id, None)
                if self._active_by_session.get(session_id) == run_id:
                    self._active_by_session.pop(session_id, None)
                self._schedule_next_locked(session_id)

    def handle(self, run_id):
        with self._lock:
            return self._handles.get(str(run_id or ""))

    def active_run_id(self, session_id):
        with self._lock:
            return str(self._active_by_session.get(str(session_id or ""), ""))

    def session_is_busy(self, session_id):
        target = str(session_id or "")
        with self._lock:
            return target in self._active_by_session or bool(self._queues.get(target))

    def cancel(self, run_id):
        identifier = str(run_id or "")
        with self._lock:
            handle = self._handles.get(identifier)
            if not handle:
                return self.core.chat_store.request_run_cancel(identifier)
            handle.cancel_event.set()
            self.core.chat_store.request_run_cancel(identifier)
            if handle.status == "queued":
                handle.status = "cancelled"
            return True

    def cancel_session(self, session_id):
        target = str(session_id or "")
        cancelled = False
        with self._lock:
            identifiers = [
                run_id for run_id, handle in self._handles.items()
                if handle.session_id == target and not handle.done_event.is_set()
            ]
        for run_id in identifiers:
            cancelled = self.cancel(run_id) or cancelled
        return cancelled

    def request_approval(self, run_id, session_id, title, prompt, risk_level="medium", callback=None):
        payload_hash = hashlib.sha256(
            json.dumps(
                {"title": str(title or ""), "prompt": str(prompt or ""), "risk": str(risk_level or "")},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        approval_id = self.core.chat_store.create_approval(
            run_id,
            session_id,
            title=title,
            prompt=prompt,
            risk_level=risk_level,
            payload_hash=payload_hash,
        )
        waiter = {"event": threading.Event(), "approved": False}
        with self._lock:
            self._approval_waiters[approval_id] = waiter
        self.core.chat_store.transition_run(
            run_id,
            "waiting_for_approval",
            expected_statuses={"running"},
        )
        self.core.chat_store.create_attention(
            session_id,
            run_id,
            "approval",
            {"approval_id": approval_id, "risk_level": str(risk_level or "medium")},
        )
        self._emit(
            "approval_requested",
            run_id,
            session_id,
            {
                "approval_id": approval_id,
                "title": str(title or ""),
                "prompt": str(prompt or ""),
                "risk_level": str(risk_level or "medium"),
                "payload_hash": payload_hash,
                "interactive_callback": bool(callback),
            },
            persist=True,
        )
        if callback:
            try:
                self.resolve_approval(approval_id, bool(callback(title, prompt, risk_level)))
            except Exception:
                logging.exception("Approval callback failed")
                self.resolve_approval(approval_id, False)
        else:
            try:
                timeout = max(1, int(self.core.settings.get("approval_wait_timeout_seconds", 86400) or 86400))
            except (TypeError, ValueError):
                timeout = 86400
            deadline = time.monotonic() + timeout
            handle = self.handle(run_id)
            while not waiter["event"].wait(0.25):
                if (handle and handle.cancel_event.is_set()) or time.monotonic() >= deadline:
                    self.resolve_approval(approval_id, False, status="expired" if time.monotonic() >= deadline else "cancelled")
                    break
        approved = bool(waiter.get("approved"))
        with self._lock:
            self._approval_waiters.pop(approval_id, None)
        if approved:
            self.core.chat_store.transition_run(
                run_id,
                "running",
                expected_statuses={"waiting_for_approval"},
            )
        return approved

    def resolve_approval(self, approval_id, approved, status=None):
        decision = str(status or ("approved" if approved else "denied"))
        changed = self.core.chat_store.resolve_approval(
            approval_id,
            decision,
            {"source": "runtime", "approved": bool(approved)},
        )
        with self._lock:
            waiter = self._approval_waiters.get(str(approval_id or ""))
            if waiter:
                waiter["approved"] = bool(approved) and decision == "approved"
                waiter["event"].set()
        return bool(changed)

    def shutdown(self, wait=False):
        with self._lock:
            self._closed = True
            handles = list(self._handles.values())
            workers = list(self._threads.values())
        for handle in handles:
            if not handle.done_event.is_set():
                handle.cancel_event.set()
        if wait:
            for worker in workers:
                if worker is not threading.current_thread():
                    worker.join()
