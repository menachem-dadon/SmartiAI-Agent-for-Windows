"""Provider-independent ownership of Live tasks, execution segments and answers.

Natural-language decisions arrive from a model. This module only validates and
applies those explicit commands through Core's existing execution authority.
"""
from __future__ import annotations

import uuid
import hashlib
from datetime import datetime
from .live_content import PRESENTATION_INSTRUCTIONS

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
ACTIONS = {"start", "continue", "update", "pause", "resume", "cancel", "status", "answer", "deliver"}


class LiveTaskCoordinator:
    def __init__(self, core, conversation, session_id, emit):
        self.core, self.store = core, core.chat_store
        self.conversation, self.session_id, self.emit = conversation, session_id, emit
        self.tasks = {}
        self.executions = {}
        self.active = ""
        self.commands = {}
        for run in reversed(self.store.list_runs(session_id=conversation, limit=1000)):
            meta = run.get("metadata", {})
            task_id = meta.get("live_task_id")
            if not task_id: continue
            self.tasks[task_id] = {"id": task_id, "run_id": run["id"], "status": run["status"],
                "segments": meta.get("live_segments", []), "call_id": "", "user_input_revision": -1,
                "pause_requested": meta.get("pause_requested", False)}
            self.executions[run["id"]] = self.tasks[task_id]
            self.active = task_id
            if meta.get("live_session_id") == session_id and meta.get("live_command_key"):
                self.commands[meta["live_command_key"]] = run["id"]

    @staticmethod
    def view(task):
        return {key: task[key] for key in ("id", "run_id", "status", "pause_requested", "paused") if key in task}

    def answer(self, task):
        run = self.store.run(task["run_id"]) or {}
        if run: task["status"] = run["status"]
        return {**self.view(task), "result": run.get("response_text") or run.get("error_text") or "",
                "reason": "This is existing execution evidence, not a new execution request."}

    def command(self, action, instruction, task_id, call_id, *, context, attachments, executor,
                user_revision, recovered_revision):
        if action not in ACTIONS: raise ValueError("פעולת משימה לא מוכרת")
        command_key = hashlib.sha256(f"{self.session_id}:{user_revision}:{action}:{task_id}:{instruction}".encode()).hexdigest()
        if call_id and command_key in self.commands:
            prior = self.executions.get(self.commands[command_key])
            if prior: return {**self.view(prior), "unchanged": True, "acknowledge_start": False}
        task_id = task_id or self.active
        task = self.tasks.get(task_id)
        if task:
            run = self.store.run(task["run_id"]) or {}
            if run: task["status"] = run["status"]
        if action == "start" and call_id and recovered_revision >= user_revision and task:
            return {**self.view(task), "resumed_existing": True, "acknowledge_start": False}
        if action in {"status", "answer"}:
            if not task: return {"status": "idle", "full_canonical_context": context}
            return {**self.answer(task), "full_canonical_context": context}
        if action == "continue" and task and task["status"] not in TERMINAL:
            # A continuation is a new execution only after the previous one
            # ended. Native model mistakes must not queue a copy of live work.
            return {**self.answer(task), "already_running": True, "execution_started": False,
                    "full_canonical_context": context,
                    "reason": "This execution is still active. No new run or instruction change was applied. "
                              "Answer the user from the current progress. Use update only if the user actually changed execution instructions; "
                              "never continue/restart merely to report progress or carry out the remaining steps of the original request."}
        if action == "continue" or (action == "update" and task and task["status"] in TERMINAL):
            if not task: raise ValueError("אין משימה כזו להמשך")
            action = "start"  # New execution, linked to the same logical task.
        elif action == "start":
            task_id, task = uuid.uuid4().hex, None
        if action == "start":
            if not str(instruction).strip(): raise ValueError("חסרה בקשת המשתמש להפעלת הסוכן")
            segment = {"id": uuid.uuid4().hex, "status": "running", "after": 0}
            prompt = "Live user request:\n" + instruction + "\n\n" + PRESENTATION_INSTRUCTIONS + "\n\nFull canonical conversation and task context:\n" + context
            metadata = {**executor, "channel": "live", "live_schema": 2, "live_task_id": task_id,
                        "live_segment_id": segment["id"], "live_segments": [segment], "live_session_id": self.session_id,
                        "live_command_key": command_key}
            handle = self.core.run_manager.submit(self.conversation, prompt, attachments=attachments,
                                                  source="smarty_live", metadata=metadata)
            task = {"id": task_id, "run_id": handle.run_id, "status": "queued", "segments": [segment],
                    "call_id": call_id, "user_input_revision": user_revision}
            self.tasks[task_id] = task
            self.executions[task["run_id"]] = task
            self.active = task_id
            self.persist_segments(task)
        else:
            if not task: raise ValueError("אין משימה כזו בשיחת הלייב")
            if action == "update" and call_id and task.get("user_input_revision") == user_revision:
                return {**self.view(task), "unchanged": True}
            if action == "cancel": self.core.run_manager.cancel(task["run_id"])
            else:
                result = self.core.run_manager.control_run(task["run_id"], action,
                    instruction + "\nUpdated full voice context:\n" + context if action == "update" else instruction,
                    attachments=attachments if action == "update" else None)
                if action == "update":
                    segments = task.setdefault("segments", [])
                    latest_user = next((row for row in reversed(self.store.messages(self.conversation))
                                        if row["role"] == "user" and not row.get("metadata", {}).get("live_backend")), None)
                    if segments and latest_user:
                        segments[-1]["until_message"] = latest_user.get("metadata", {}).get("live_message_id") or latest_user["message_id"]
                    segments.append({"id": uuid.uuid4().hex, "status": "queued", "after": None,
                                     "revision": result.get("revision") if isinstance(result, dict) else None})
                    task["user_input_revision"] = user_revision
                    self.save_task(task)
                    self.persist_segments(task)
            if action in {"pause", "resume"}: task["pause_requested"] = action == "pause"
        self.emit("task", task=self.view(task))
        if action not in {"status", "answer"}: self.commands[command_key] = task["run_id"]
        return {**self.view(task), **({"acknowledge_start": True, "execution_started": True} if action == "start" else {})}

    def save_task(self, task):
        run = self.store.run(task["run_id"]) or {}
        if run:
            self.store.transition_run(run["id"], run["status"], metadata_patch={"live_segments": task["segments"]})

    def apply_revision(self, task, revision, sequence):
        segments = task.get("segments", [])
        pending = next((s for s in segments if s.get("revision") == revision and s.get("after") is None), None)
        if not pending: return
        for segment in segments:
            if segment is pending: break
            if segment["status"] not in TERMINAL:
                segment.update(status="completed", before=sequence)
        pending.update(status="running", after=sequence)
        self.save_task(task)
        self.persist_segments(task)

    def persist_segments(self, task):
        run = self.store.run(task["run_id"]) or {}
        backend = next((row for row in reversed(self.store.messages(self.conversation))
                        if row["role"] == "assistant" and row.get("metadata", {}).get("run_id") == task["run_id"]
                        and not row.get("metadata", {}).get("live_process") and not row.get("metadata", {}).get("live_final")), {})
        process = backend.get("metadata", {}).get("agent_process")
        events, cursor = [], 0
        while True:
            page = self.store.run_events(task["run_id"], after_sequence=cursor, limit=2000)
            events.extend(page)
            if len(page) < 2000: break
            cursor = page[-1]["sequence"]
        for segment in task.get("segments", []):
            status = task["status"] if segment["status"] not in TERMINAL and task["status"] in TERMINAL else segment["status"]
            ids = {event.get("payload", {}).get("value", {}).get("id") for event in events
                   if event["event_type"] == "run_step" and isinstance(event.get("payload", {}).get("value"), dict)
                   and segment.get("after") is not None and event["sequence"] > segment["after"]
                   and (segment.get("before") is None or event["sequence"] < segment["before"])}
            sliced = {**process, "events": [event for event in process.get("events", []) if event.get("id") in ids]} if isinstance(process, dict) else None
            if sliced is not None:
                start = next((event["created_at"] for event in events if event["sequence"] == segment.get("after")), run.get("started_at"))
                end = next((event["created_at"] for event in events if event["sequence"] == segment.get("before")), run.get("finished_at"))
                if start and end:
                    sliced["elapsed_seconds"] = max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
            row = self.store.upsert_live_message(self.conversation, "process-" + segment["id"], "assistant", "",
                {"live_schema": 2, "live_process": True, "live_task_id": task["id"], "run_id": task["run_id"],
                 "live_segment_id": segment["id"], "live_segment_after": segment.get("after"),
                 "live_segment_before": segment.get("before"), "live_run_status": status,
                 "live_segment_until_message": segment.get("until_message"),
                 "live_session_id": self.session_id, "agent_process": sliced})
            self.emit("message", message=row)

    def result(self, task):
        return next((row for row in self.store.messages(self.conversation)
                     if row.get("metadata", {}).get("live_message_id") == "final-" + task["run_id"]), None)

    def set_delivery(self, task, state, *, content=None, **metadata):
        row = self.result(task)
        if not row: return None
        meta = row["metadata"]
        row = self.store.upsert_live_message(self.conversation, meta["live_message_id"], "assistant",
            row["content"] if content is None else content,
            {"live_delivery": state, **metadata})
        self.emit("message", message=row)
        return row

    def fallback(self, task):
        row = self.result(task)
        if not row: return None
        # The same reserved message is used by both speech and fallback. Never
        # append a second answer, new controls, or an alternative display panel.
        return self.set_delivery(task, "fallback", content=row["metadata"]["live_result_text"],
            live_result_pending=False, live_partial=False, live_presenting=False,
            live_audio_start_ms=0, live_audio_end_ms=0, live_audio_cues=[], live_spoken_length=0, live_spoken_text=None)
