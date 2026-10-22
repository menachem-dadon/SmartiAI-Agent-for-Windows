import asyncio
import base64
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock
from aiohttp import WSMessage, WSMsgType

from smarti.history import ChatSessionStore
from smarti.live_voice import LiveSession, LiveVoiceManager, context_chunks, packed_context, visual_blocks
from smarti.local_gateway import ScopedAttachmentRegistry
from smarti.run_control import RunControl
from smarti.agent.speech import SpeechMixin
from smarti.agent.model_context import ModelContextMixin
from smarti.task_limits import TaskCancellation


class RunControlTests(unittest.TestCase):
    def test_paused_time_does_not_expire_the_execution_deadline(self):
        deadline = TaskCancellation(threading.Event(), .15)
        try:
            deadline.suspend()
            time.sleep(.2)
            self.assertFalse(deadline.is_set())
            deadline.resume()
            self.assertTrue(deadline.expired.wait(1))
        finally:
            deadline.close()

    def test_real_agent_discards_stale_inference_before_dispatching_a_tool(self):
        from tests.test_stability_repairs import StabilityRepairTests
        fixture = StabilityRepairTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        conversation, _, run = fixture._managed_resume_fixture()
        core = fixture.core
        control = RunControl()
        core._execution_context.run_control = control
        observed = []
        def infer(model, messages):
            observed.append(json.loads(json.dumps(messages)))
            if len(observed) == 1:
                control.change("update", "Use destination B instead of A")
                return json.dumps({"method": "tools/call", "params": {"name": "file_manager", "arguments": {"action": "atomic_write_text", "path": "A", "content": "stale"}}}), {}
            return "Completed updated task.", {}
        core._handle_api_request_with_retry = infer
        result = core.send_message("continue", session_id=conversation, run_id=run, persist_turn=False)
        self.assertEqual(result, "Completed updated task.")
        self.assertEqual(len(observed), 2)
        self.assertIn("destination B", json.dumps(observed[-1]))
        self.assertIn("completed tool result", json.dumps(observed[-1]))
        core.execute_tool.assert_not_called()

    def test_pause_preserves_same_worker_and_delivers_correction_once(self):
        control, cancelled = RunControl(), threading.Event()
        paused, resumed, finished = threading.Event(), threading.Event(), threading.Event()
        effects, received = [], []
        control.change("pause")
        def work():
            effects.append("tool already completed")
            received.extend(control.boundary(cancelled.is_set, paused.set, resumed.set))
            effects.append("next tool")
            finished.set()
        worker = threading.Thread(target=work)
        worker.start()
        self.assertTrue(paused.wait(1))
        self.assertFalse(finished.is_set())
        control.change("update", "change destination", [{"path": "original.png"}])
        control.change("resume")
        worker.join(2)
        self.assertTrue(resumed.is_set())
        self.assertEqual(effects, ["tool already completed", "next tool"])
        self.assertEqual(received[0]["attachments"], [{"path": "original.png"}])
        self.assertEqual(control.boundary(cancelled.is_set, lambda: None, lambda: None), [])

    def test_real_agent_resumes_after_entering_a_pause_boundary(self):
        from tests.test_stability_repairs import StabilityRepairTests
        fixture = StabilityRepairTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        conversation, _, run = fixture._managed_resume_fixture()
        core, control = fixture.core, RunControl()
        core._execution_context.run_control = control
        entered, resumed = threading.Event(), threading.Event()
        boundary = control.boundary
        def observed_boundary(cancelled, on_pause, on_resume):
            def pause():
                on_pause(); entered.set()
            def resume():
                on_resume(); resumed.set()
            return boundary(cancelled, pause, resume)
        control.boundary = observed_boundary
        def infer(model, messages):
            control.change("pause")
            return "Completed after the actual pause.", {}
        core._handle_api_request_with_retry = infer
        def resume_after_pause():
            if entered.wait(3): control.change("resume")
        resumer = threading.Thread(target=resume_after_pause)
        resumer.start()
        result = core.send_message("continue", session_id=conversation, run_id=run, persist_turn=False)
        resumer.join(4)
        self.assertTrue(entered.is_set())
        self.assertTrue(resumed.is_set())
        self.assertEqual(result, "Completed after the actual pause.")
        core.execute_tool.assert_not_called()

    def test_cancellation_releases_pause_without_resume(self):
        control, cancelled, paused = RunControl(), threading.Event(), threading.Event()
        resume = Mock()
        control.change("pause")
        worker = threading.Thread(target=lambda: control.boundary(cancelled.is_set, paused.set, resume))
        worker.start()
        self.assertTrue(paused.wait(1))
        cancelled.set(); worker.join(2)
        self.assertFalse(worker.is_alive())
        resume.assert_not_called()


class LiveVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = ChatSessionStore(str(Path(self.directory.name) / "history.json"))
        self.conversation = self.store.create_session(set_active=False)["id"]
        self.settings = {"live_provider": "gemini", "gemini_api_key": "test-secret-shared", "live_gemini_voice": "Kore"}
        self.runs = SimpleNamespace(subscribe=Mock(return_value="subscription"), unsubscribe=Mock(), control_run=Mock(), cancel=Mock(), submit=Mock())
        self.core = SimpleNamespace(settings=self.settings, chat_store=self.store, run_manager=self.runs,
                                    _ensure_secret_loaded=lambda key: self.settings.get(key, ""), stop_speaking=Mock(),
                                    _local_fast_conversation_title=ModelContextMixin._local_fast_conversation_title,
                                    _schedule_conversation_title=Mock(return_value=True), _emit_notification=Mock())
        self.manager = LiveVoiceManager(self.core, ScopedAttachmentRegistry())
        self.session = LiveSession(self.manager, self.conversation, "gemini", {"provider_mode": "local", "model_name": "test"}, [])
        self.session.phase = "ready"
        self.manager.owner = self.session
        self.core._live_voice_owner = self.session.id
        class Socket:
            closed = False
            def __init__(self): self.sent = []
            async def send_json(self, data): self.sent.append(data)
            async def close(self): self.closed = True
        self.session.ws = Socket()

    async def asyncTearDown(self):
        await self.session.close()
        self.directory.cleanup()

    def make_task(self, instruction="read files"):
        def submit(conversation, text, attachments, source, metadata):
            run_id = self.store.create_run(conversation, user_text=text, metadata=metadata)
            return SimpleNamespace(run_id=run_id)
        self.runs.submit.side_effect = submit
        return self.session.control("start", instruction)

    def test_key_inheritance_override_and_delete_are_live_only(self):
        original = dict(self.settings)
        shared = self.manager.config()["items"][1]
        self.assertTrue(shared["inherited"])
        self.assertNotIn("test-secret-shared", json.dumps(shared))
        self.settings["live_gemini_api_key"] = "separate-secret"
        self.assertFalse(self.manager.config()["items"][1]["inherited"])
        del self.settings["live_gemini_api_key"]
        self.assertEqual(original, self.settings)

    def test_disabled_live_preserves_provider_and_shared_secret(self):
        self.settings["live_enabled"] = False
        config = self.manager.config()
        self.assertFalse(config["available"])
        self.assertEqual(config["provider"], "gemini")
        self.assertTrue(config["items"][1]["inherited"])
        self.settings["live_enabled"] = True
        self.assertTrue(self.manager.config()["available"])

    async def test_language_is_snapshotted_and_uses_provider_native_contract(self):
        setup = self.session.connection_setup()["setup"]
        self.assertEqual(setup["inputAudioTranscription"], {"languageCodes": ["he-IL"]})
        self.assertNotIn("languageCode", setup["generationConfig"]["speechConfig"])
        vad = setup["realtimeInputConfig"]["automaticActivityDetection"]
        self.assertEqual(vad["endOfSpeechSensitivity"], "END_SENSITIVITY_LOW")
        self.assertEqual(vad["silenceDurationMs"],1200)
        self.assertEqual(vad["startOfSpeechSensitivity"], "START_SENSITIVITY_LOW")
        self.assertEqual(vad["prefixPaddingMs"], 300)
        self.assertIn("Hebrew", setup["systemInstruction"]["parts"][0]["text"])
        self.settings["live_language"] = "en"
        self.assertEqual(self.session.connection_setup()["setup"]["inputAudioTranscription"], {"languageCodes": ["he-IL"]})
        other = LiveSession(self.manager, self.conversation, "openai", {}, [])
        try:
            config = other.connection_setup()["session"]
            self.assertIn("English", config["instructions"])
            self.assertNotIn("input", config["audio"])
        finally:
            await other.close()
        self.settings["live_language"] = "auto"
        other = LiveSession(self.manager, self.conversation, "gemini", {}, [])
        try:
            self.assertEqual(other.connection_setup()["setup"]["inputAudioTranscription"], {})
            self.assertNotIn("default language of the user's microphone", other.instructions)
        finally:
            await other.close()

    def test_enabled_migration_keeps_existing_live_but_new_profiles_disabled(self):
        from smarti.config import DEFAULT_SETTINGS
        from smarti.managers import SettingsManager
        manager = SettingsManager(str(Path(self.directory.name) / "settings.json"), DEFAULT_SETTINGS)
        for old, expected in (({"live_provider": "gemini"}, True), ({}, False), ({"live_provider": "gemini", "live_enabled": False}, False)):
            merged, _ = manager.migrate_or_merge({"settings_schema_version": DEFAULT_SETTINGS["settings_schema_version"], **old})
            self.assertEqual(merged["live_enabled"], expected)

    async def test_audio_sequence_replay_and_mute_never_duplicate_audio(self):
        packet = {"sequence": 0, "audio": base64.b64encode(b"\0\0" * 256).decode()}
        await self.session.input(packet)
        await self.session.input(packet)
        self.assertEqual(len(self.session.ws.sent), 1)
        self.assertEqual(self.session.ws.sent[0]["realtimeInput"]["audio"]["mimeType"], "audio/pcm;rate=24000")
        await self.session.input({"sequence": 1, "mic_muted": True})
        await self.session.input({**packet, "sequence": 2})
        self.assertEqual(len(self.session.ws.sent), 2)
        self.assertTrue(self.session.ws.sent[-1]["realtimeInput"]["audioStreamEnd"])
        with self.assertRaises(ValueError):
            await self.session.input({"sequence": 3, "audio": "broken!"})

    async def test_native_resumption_reuses_handle_without_restarting_executor(self):
        task = self.make_task()
        previous = self.session.ws
        replacement = type(previous)()
        replacement.receive = AsyncMock(return_value=WSMessage(WSMsgType.BINARY, b'{"setupComplete":{}}', None))
        self.session.http = SimpleNamespace(ws_connect=AsyncMock(return_value=replacement), close=AsyncMock())
        self.session.gemini_setup = {"setup": {"model": "models/gemini-3.8-live", "sessionResumption": {}}}
        await self.session.receive({"sessionResumptionUpdate": {"resumable": True, "newHandle": "resume-original"}, "goAway": {"timeLeft": "10s"}})
        self.assertTrue(previous.closed)
        self.assertIs(self.session.ws, replacement)
        self.assertEqual(replacement.sent[0]["setup"]["sessionResumption"], {"handle": "resume-original"})
        self.assertEqual(self.session.tasks[task["id"]]["run_id"], task["run_id"])
        self.runs.submit.assert_called_once()

    async def test_abrupt_disconnect_resumes_same_task_without_replaying_execution(self):
        task = self.make_task()
        previous = self.session.ws
        previous.receive = AsyncMock(return_value=WSMessage(WSMsgType.CLOSE, 1011, "Internal error"))
        replacement = type(previous)()
        reads = 0
        async def read():
            nonlocal reads
            reads += 1
            if reads == 1: return WSMessage(WSMsgType.BINARY, b'{"setupComplete":{}}', None)
            self.session.closed_ack.set()
            return WSMessage(WSMsgType.TEXT, '{"serverContent":{"outputTranscription":{"text":"Still here"},"turnComplete":true}}', None)
        replacement.receive = read
        self.session.http = SimpleNamespace(ws_connect=AsyncMock(return_value=replacement), close=AsyncMock())
        self.session.gemini_setup = self.session.connection_setup()
        self.session.resume_handle = "safe-resume"
        await self.session.read_transport()
        self.assertEqual(self.session.phase, "ready")
        self.assertEqual(self.session.tasks[task["id"]]["run_id"], task["run_id"])
        replay = self.session.control("start", "repeat", call_id="after-reconnect")
        self.assertEqual(replay["id"], task["id"])
        self.assertTrue(replay["resumed_existing"])
        self.assertEqual(self.runs.submit.call_count, 1)
        self.assertEqual(self.store.messages(self.conversation)[-1]["content"], "Still here")
        self.session.tasks[task["id"]]["status"] = "completed"
        self.assertEqual(self.session.control("start", "repeat finished work", call_id="late-replay")["id"], task["id"])
        self.runs.submit.assert_called_once()
        self.session.user_input_revision += 1
        new_task = self.session.control("start", "new user request", call_id="new-request")
        self.assertNotEqual(new_task["id"], task["id"])
        self.assertEqual(self.runs.submit.call_count, 2)

    async def test_policy_close_is_reported_with_code_and_does_not_reconnect(self):
        self.session.ws.receive = AsyncMock(return_value=WSMessage(WSMsgType.CLOSE, 1008, "Policy violation"))
        self.session.resume_handle = "not-for-policy-retry"
        self.session.http = SimpleNamespace(ws_connect=AsyncMock(), close=AsyncMock())
        with self.assertRaisesRegex(RuntimeError, "1008"):
            await self.session.read_transport()
        self.session.http.ws_connect.assert_not_called()

    async def test_resume_preface_is_dispatched_after_writer_unlock_and_releases_old_speech(self):
        task = self.make_task()
        self.session.transcript("assistant", "Working on it")
        self.session.voice_idle.clear()
        previous = self.session.ws
        disconnect, status_seen = asyncio.Event(), threading.Event()
        async def old_read():
            await disconnect.wait()
            return WSMessage(WSMsgType.CLOSED, None, None)
        async def old_close():
            previous.closed = True
            disconnect.set()
            while not status_seen.is_set(): await asyncio.sleep(.005)
        previous.receive, previous.close = old_read, old_close
        replacement = type(previous)()
        replacement.receive = AsyncMock(side_effect=[
            WSMessage(WSMsgType.TEXT, json.dumps({"toolCall": {"functionCalls": [
                {"id": "resumed-status", "name": "smarty_task", "args": {"action": "status", "task_id": task["id"]}}
            ]}}), None),
            WSMessage(WSMsgType.TEXT, '{"setupComplete":{}}', None),
        ])
        self.session.http = SimpleNamespace(ws_connect=AsyncMock(return_value=replacement), close=AsyncMock())
        self.session.gemini_setup = self.session.connection_setup()
        self.session.resume_handle = "preface-handle"
        original_control = self.session.control
        def control(action, *args, **kwargs):
            if action == "status": status_seen.set()
            return original_control(action, *args, **kwargs)
        self.session.control = control
        send = replacement.send_json
        async def reply(data):
            await send(data)
            if "toolResponse" in data: self.session.closed_ack.set()
        replacement.send_json = reply
        reader = asyncio.create_task(self.session.read_transport())
        await asyncio.sleep(0)  # Reader is waiting on the original socket.
        async with self.session.send_lock:
            await asyncio.wait_for(self.session.resume_gemini(), 1)
        self.assertTrue(self.session.voice_idle.is_set())
        self.assertFalse(self.store.messages(self.conversation)[-1]["metadata"]["live_partial"])
        await asyncio.wait_for(reader, 1)
        self.assertTrue(status_seen.is_set())
        response = replacement.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertEqual(response["id"], "resumed-status")
        self.assertEqual(response["response"]["run_id"], task["run_id"])
        self.runs.submit.assert_called_once()

    async def test_resume_rejection_is_redacted_and_does_not_loop(self):
        previous = self.session.ws
        replacement = type(previous)()
        self.session.connection_key = "secret-only-in-connection"
        replacement.receive = AsyncMock(return_value=WSMessage(WSMsgType.TEXT,
            '{"error":{"code":403,"message":"Rejected secret-only-in-connection"}}', None))
        self.session.http = SimpleNamespace(ws_connect=AsyncMock(return_value=replacement), close=AsyncMock())
        self.session.gemini_setup = self.session.connection_setup()
        self.session.resume_handle = "rejected-handle"
        with self.assertRaisesRegex(ValueError, r"Rejected \[redacted\]"):
            await self.session.resume_gemini()
        self.assertIs(self.session.ws, previous)
        self.assertTrue(replacement.closed)
        self.assertTrue(self.session.transport_ready.is_set())
        self.session.http.ws_connect.assert_awaited_once()

    async def test_status_needs_no_context_and_keeps_audio_available(self):
        task = self.make_task()
        self.session.context = Mock(side_effect=AssertionError("status must not export history"))
        await self.session.receive({"toolCall":{"functionCalls":[{"id":"status-check","name":"smarty_task","args":{"action":"status","task_id":task["id"]}}]}})
        response = self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]["response"]
        self.assertNotIn("full_canonical_context", response)
        await asyncio.wait_for(self.session.input({"sequence":0,"audio":base64.b64encode(b"\0\0"*256).decode()}), .2)
        self.session.context.assert_not_called()

    async def test_reattach_restores_input_cursor_and_accepts_next_frame(self):
        encoded = base64.b64encode(b"\0\0" * 256).decode()
        await self.session.input({"sequence": 500, "audio": encoded})
        opened = await self.manager.start({"conversation_id": self.conversation})
        self.assertEqual(opened["next_input_sequence"], 501)
        await self.session.input({"sequence": opened["next_input_sequence"], "audio": encoded})
        self.assertEqual(len(self.session.ws.sent), 2)

    async def test_reconnecting_audio_is_dropped_promptly_instead_of_buffered_for_later(self):
        self.session.phase = "reconnecting"
        self.session.transport_ready.clear()
        encoded = base64.b64encode(b"\0\0" * 256).decode()
        receipt = await asyncio.wait_for(self.session.input({"sequence": 0, "audio": encoded}), .1)
        self.assertTrue(receipt["dropped"])
        self.assertEqual(self.session.ws.sent, [])
        self.session.phase = "ready"; self.session.transport_ready.set()
        await self.session.input({"sequence": 1, "audio": encoded})
        self.assertEqual(len(self.session.ws.sent), 1)

    async def test_resumable_false_discards_old_handle_and_fresh_connection_keeps_task(self):
        task = self.make_task()
        self.session.resume_handle = "stale"
        await self.session.receive({"sessionResumptionUpdate": {"resumable": False}})
        self.assertEqual(self.session.resume_handle, "")
        replacement = type(self.session.ws)()
        replacement.receive = AsyncMock(return_value=WSMessage(WSMsgType.TEXT, '{"setupComplete":{}}', None))
        self.session.http = SimpleNamespace(ws_connect=AsyncMock(return_value=replacement), close=AsyncMock())
        await self.session.resume_gemini()
        self.assertNotIn("handle", replacement.sent[0]["setup"]["sessionResumption"])
        self.assertIn(task["run_id"], json.dumps(replacement.sent))
        self.assertEqual(self.session.tasks[task["id"]]["run_id"], task["run_id"])
        self.runs.submit.assert_called_once()

    async def test_controls_do_not_read_context_or_historical_files(self):
        task = self.make_task()
        self.session.context = Mock(side_effect=AssertionError("context unavailable"))
        self.session.gather_files = Mock(side_effect=AssertionError("old file deleted"))
        for action in ("pause", "resume", "cancel"):
            self.session.control(action, task_id=task["id"])
        self.runs.cancel.assert_called_once_with(task["run_id"])
        self.assertEqual(self.runs.control_run.call_count, 2)

    async def test_text_retry_during_inflight_and_after_audio_keeps_one_turn(self):
        original = self.session.apply_text
        async def slow(text, attachments):
            await asyncio.sleep(.02)
            await original(text, attachments)
        self.session.apply_text = slow
        payload = {"sequence": 2, "text": "One explicit request"}
        await asyncio.gather(self.session.input(payload), self.session.input(payload))
        encoded = base64.b64encode(b"\0\0" * 256).decode()
        for sequence in range(3, 75):
            await self.session.input({"sequence": sequence, "audio": encoded})
        await self.session.input(payload)
        self.assertEqual([r["content"] for r in self.store.messages(self.conversation) if r["role"] == "user"], [payload["text"]])

    async def test_memory_uses_shared_manager_and_only_actual_changes_emit(self):
        memory = SimpleNamespace(build_prompt_context=Mock(return_value="Saved preference: brief Hebrew replies"),
            extract_model_memory_decision=Mock(return_value=("", [{"action": "add", "content": "brief replies"}])),
            apply_model_memory_operations=Mock(side_effect=[{"changed": True, "count": 1}, {"changed": False, "count": 0}]))
        self.core.memory_manager = memory
        self.assertIn("Saved preference", self.session.context())
        for _ in range(2):
            result = await asyncio.to_thread(self.session.control, "memory", '{"operations":[{"action":"add","content":"brief replies"}]}')
        await asyncio.sleep(0)
        memory.apply_model_memory_operations.assert_called_with([{"action": "add", "content": "brief replies"}], session_id=self.conversation)
        self.assertEqual(sum(e["type"] == "memory" for e in self.session.events), 1)
        self.assertFalse(result["changed"])

    async def test_gpt_close_reader_keeps_final_ack_and_cumulative_usage(self):
        self.session.provider = "openai"
        self.core._log_usage = Mock(return_value=True)
        async def read():
            while not any(item.get("type") == "session.close" for item in self.session.ws.sent): await asyncio.sleep(.001)
            self.assertFalse(self.session.closed)
            await self.session.receive({"type": "session.closed", "usage": {"seconds": 15}, "reason": "close_requested"})
        self.session.worker = asyncio.create_task(read())
        await asyncio.wait_for(self.session.close(), .5)
        self.assertTrue(self.session.closed_ack.is_set())
        self.assertEqual(sum(call.args[1]["voice_seconds"] for call in self.core._log_usage.call_args_list), 15)

    async def test_gemini_usage_sums_turns_without_double_counting_one_turn(self):
        self.core._log_usage = Mock(return_value=True)
        await self.session.receive({"usageMetadata": {"promptTokenCount": 10, "responseTokenCount": 2, "totalTokenCount": 12}})
        await self.session.receive({"serverContent": {"turnComplete": True}, "usageMetadata": {"promptTokenCount": 20, "responseTokenCount": 3, "totalTokenCount": 23}})
        await self.session.receive({"serverContent": {"turnComplete": True}, "usageMetadata": {"promptTokenCount": 10, "responseTokenCount": 2, "totalTokenCount": 12}})
        await self.session.record_usage({}, final=True)
        calls = self.core._log_usage.call_args_list
        self.assertEqual(sum(call.args[1].get("prompt", 0) for call in calls), 30)
        self.assertEqual(sum(call.args[1].get("completion", 0) for call in calls), 5)
        self.assertEqual(sum(call.args[1].get("total", 0) for call in calls), 35)

    async def test_gpt_correlated_append_rejection_is_nonfatal(self):
        self.session.provider = "openai"
        await self.session.inject("New background")
        event = self.session.ws.sent[-1]["event_id"]
        await self.session.receive({"type": "error", "error": {"client_event_id": event, "message": "Rejected update"}})
        self.assertFalse(self.session.closed)
        self.assertNotIn(event, self.session.pending_appends)
        self.assertEqual(self.session.events[-1]["type"], "notice")

    async def test_playback_drop_cannot_become_spoken_receipt(self):
        task = self.make_task()
        self.session.output_audio_ms = 1000
        self.session.delivery_receipts[task["run_id"]] = {"task": task, "start_ms": 0, "end_ms": 1000}
        self.session.coordinator.set_delivery = Mock()
        await self.session.input({"sequence": 0, "playback_ms": 1000, "dropped_audio": [[200, 1000]]})
        self.session.coordinator.set_delivery.assert_called_once_with(task, "truncated")

    async def test_context_delta_is_empty_until_core_changes(self):
        self.session.context_changes()
        self.assertEqual(self.session.context_changes(), {})
        self.store.append_message("user", "A later text turn", session_id=self.conversation)
        delta = self.session.context_changes()
        self.assertEqual(delta["recent_messages"][-1]["content"], "A later text turn")
        self.assertEqual(self.session.context_changes(), {})

    async def test_expired_resume_handle_falls_back_to_fresh_context_once(self):
        self.session.resume_handle = "expired"
        rejected, replacement = type(self.session.ws)(), type(self.session.ws)()
        rejected.receive = AsyncMock(return_value=WSMessage(WSMsgType.TEXT, '{"error":{"code":400,"message":"Invalid session handle"}}', None))
        replacement.receive = AsyncMock(return_value=WSMessage(WSMsgType.TEXT, '{"setupComplete":{}}', None))
        self.session.http = SimpleNamespace(ws_connect=AsyncMock(side_effect=[rejected, replacement]), close=AsyncMock())
        await self.session.resume_gemini()
        self.assertEqual(self.session.http.ws_connect.await_count, 2)
        self.assertTrue(rejected.closed)
        self.assertNotIn("handle", replacement.sent[0]["setup"]["sessionResumption"])

    async def test_gpt_delivery_fast_path_requires_correlated_ack_and_timeline_boundary(self):
        task = self.make_task()
        self.store.transition_run(task["run_id"], "completed", response_text="Verified 7319")
        task["status"] = "completed"
        self.session.provider = "openai"
        self.session.delivery_task = task
        self.session.route_client_intent = Mock(return_value={"action": "status"})
        await self.session.send_task_result(task, "Verified 7319")
        for identity in list(self.session.delivery_claim["events"]):
            await self.session.receive({"type": "session.commentary.appended", "client_event_id": identity, "end_ms": 500})
        await self.session.receive({"type": "session.delegation.created", "delegation": {"id": "presentation", "offset_ms": 501}})
        await asyncio.gather(*self.session.commands)
        self.session.route_client_intent.assert_not_called()
        self.assertEqual(self.session.calls["presentation"]["delivery"], "accepted")

    async def test_gpt_native_append_contract_keeps_delegation_identity(self):
        self.session.provider = "openai"
        await self.session.inject("confirmed result", delegation_id="delegate-one")
        await self.session.inject("final prose", speak=True, delegation_id="delegate-one")
        self.assertEqual([item["type"] for item in self.session.ws.sent], ["session.thinking.append", "session.commentary.append"])
        self.assertTrue(all(item["delegation_id"] == "delegate-one" for item in self.session.ws.sent))
        self.assertTrue(all(item.get("event_id") for item in self.session.ws.sent))

    async def test_gemini_combined_audio_transcription_and_turn_complete(self):
        await self.session.receive({"serverContent": {
            "inputTranscription": {"text": "שלום"}, "outputTranscription": {"text": "היי"},
            "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": "AAA="}}]}, "turnComplete": True}})
        rows = self.store.messages(self.conversation)
        self.assertEqual([(row["role"], row["content"]) for row in rows], [("user", "שלום"), ("assistant", "היי")])
        self.assertTrue(all(not row["metadata"]["live_partial"] for row in rows))
        self.assertTrue(any(event["type"] == "audio" for event in self.session.events))

    def use_title_scheduler(self):
        pending = []
        self.core._title_executor = SimpleNamespace(submit=pending.append)
        self.core._pending_title_lock = threading.RLock()
        self.core._pending_title_sessions = set()
        self.core.generate_conversation_title = Mock(return_value="תכנון טיול לירושלים")
        self.core._schedule_conversation_title = ModelContextMixin._schedule_conversation_title.__get__(self.core)
        return pending

    async def test_live_first_final_transcript_uses_shared_ai_title_scheduler(self):
        pending = self.use_title_scheduler()
        other = self.store.create_session()["id"]
        self.session.attachments = [{"name": "מסלול.pdf", "path": "route.pdf"}]
        # A later picker change must not change the Live session's title provider.
        self.settings.update(api_mode="gemini", selected_gemini_model="different")
        await self.session.receive({"serverContent": {"interimInputTranscription": {"text": "תכנן"}}})
        self.assertEqual(self.store.session_metadata(self.conversation)["title"], "שיחה חדשה")
        self.assertFalse(pending)
        await self.session.receive({"serverContent": {"inputTranscription": {"text": "תכנן טיול לירושלים"}, "turnComplete": True}})
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.store.session_metadata(self.conversation)["title"], "תכנן טיול לירושלים")
        self.assertFalse(self.store.session_metadata(self.conversation)["title_generated"])
        self.assertEqual(self.store.messages(self.conversation)[0]["content"], "תכנן טיול לירושלים")
        self.core.generate_conversation_title.assert_not_called()
        pending.pop()()
        self.core.generate_conversation_title.assert_called_once_with(
            "תכנן טיול לירושלים", "", attachment_names=["מסלול.pdf"], provider_mode="local", current_model="test")
        self.assertEqual(self.store.session_metadata(self.conversation)["title"], "תכנון טיול לירושלים")
        self.assertTrue(self.store.session_metadata(self.conversation)["title_generated"])
        self.assertEqual(self.store.session_metadata(other)["title"], "שיחה חדשה")
        self.core._emit_notification.assert_called_with("chat_title_updated", {"session_id": self.conversation, "title": "תכנון טיול לירושלים"})
        self.session.transcript("user", "ועכשיו חיפה")
        self.session.finish_transcript("user")
        self.assertFalse(pending)

    async def test_live_local_title_needs_no_assistant_or_model_request(self):
        self.use_title_scheduler()
        self.settings["conversation_title_generation_mode"] = "local"
        await self.session.apply_text("מצא מסמכים על ירושלים", [])
        self.assertEqual(self.store.session_metadata(self.conversation)["title"], "מצא מסמכים על ירושלים")
        self.assertTrue(self.store.session_metadata(self.conversation)["title_generated"])
        self.core.generate_conversation_title.assert_not_called()

    async def test_live_title_preserves_existing_manual_or_generated_name(self):
        for manual in (True, False):
            with self.subTest(manual=manual):
                title = "שם ידני קיים" if manual else "שם אוטומטי קיים"
                if manual:
                    self.store.rename_session(self.conversation, title)
                else:
                    self.store.apply_initial_title(self.conversation, title)
                self.session.transcript("user", "בקשה חדשה")
                self.session.finish_transcript("user")
                self.assertEqual(self.store.session_metadata(self.conversation)["title"], title)
                self.core._schedule_conversation_title.assert_not_called()
                self.conversation = self.store.create_session(set_active=False)["id"]
                self.session.conversation = self.conversation

    async def test_live_ai_title_cannot_overwrite_rename_while_pending(self):
        pending = self.use_title_scheduler()
        self.session.transcript("user", "תכנן טיול לירושלים")
        self.session.finish_transcript("user")
        self.store.rename_session(self.conversation, "שם ידני")
        pending.pop()()
        self.assertEqual(self.store.session_metadata(self.conversation)["title"], "שם ידני")
        self.assertFalse(self.core._pending_title_sessions)

    async def test_live_title_failure_preserves_transcript_and_provisional_name(self):
        pending = self.use_title_scheduler()
        self.core.generate_conversation_title.return_value = ""
        self.session.transcript("user", "תכנן טיול לירושלים")
        self.session.finish_transcript("user")
        pending.pop()()
        self.assertEqual(self.store.session_metadata(self.conversation)["title"], "תכנן טיול לירושלים")
        self.assertEqual(self.store.messages(self.conversation)[0]["content"], "תכנן טיול לירושלים")
        self.assertFalse(self.core._pending_title_sessions)

    async def test_gpt_title_is_scheduled_once_despite_delayed_adjacent_fragments(self):
        self.session.provider = "openai"
        self.session.transcript("user", "תכנן טיול", start=100, end=200)
        self.core._schedule_conversation_title.assert_not_called()
        self.session.finish_transcript("user", retain=True)
        self.session.transcript("user", " לירושלים", start=300, end=400)
        self.session.finish_transcript("user", retain=True)
        self.session.transcript("user", "עוד בקשה", start=4000, end=4100)
        self.session.finish_transcript("user")
        self.core._schedule_conversation_title.assert_called_once_with(
            self.conversation, "תכנן טיול", "", attachment_names=[], provider_mode="local", current_model="test")
        self.assertEqual(self.store.messages(self.conversation)[0]["content"], "תכנן טיול לירושלים")

    async def test_gpt_interleaved_transcripts_keep_independent_stable_ids(self):
        self.session.provider = "openai"
        for role, text, start in (("input", "I would", 100), ("output", "Sure", 120), ("input", " like", 200)):
            await self.session.receive({"type": f"session.{role}_transcript.delta", "delta": text, "start_ms": start, "end_ms": start + 50})
        await asyncio.sleep(.04)
        rows = self.store.messages(self.conversation)
        self.assertEqual([row["content"] for row in rows], ["I would like", "Sure"])
        identity = rows[0]["message_id"]
        self.session.finish_transcript("user", True)
        self.session.transcript("user", " help", start=300, end=350)
        self.assertEqual(self.store.messages(self.conversation)[0]["message_id"], identity)
        self.session.transcript("user", "Another turn", start=4000, end=4100)
        self.assertEqual(len(self.store.messages(self.conversation)), 3)

    async def test_interim_input_updates_one_bubble_and_final_does_not_repeat_it(self):
        for text in ("אני רו", "אני רוצה"):
            await self.session.receive({"serverContent": {"interimInputTranscription": {"text": text, "startOffset": ".2s", "endOffset": "1s"}}})
        await asyncio.sleep(.04)
        before = self.store.messages(self.conversation)
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0]["content"], "אני רוצה")
        await self.session.receive({"serverContent": {"inputTranscription": {"text": "אני רוצה סיפור", "startOffset": ".2s", "endOffset": "2.1s"}}})
        self.session.finish_transcript("user")
        after = self.store.messages(self.conversation)
        self.assertEqual(after[0]["message_id"], before[0]["message_id"])
        self.assertEqual(after[0]["content"], "אני רוצה סיפור")
        self.assertEqual(after[0]["metadata"]["start_ms"], 200)
        self.assertEqual(after[0]["metadata"]["end_ms"], 2100)

    async def test_captions_carry_audio_clock_cues_independent_of_packet_arrival(self):
        pcm = base64.b64encode(b"\0\0" * 24000).decode()
        await self.session.receive({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": pcm}}]}, "outputTranscription": {"text": "שלום "}}})
        await self.session.receive({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": pcm}}]}, "outputTranscription": {"text": "לך"}, "turnComplete": True}})
        first = self.store.messages(self.conversation)[0]["metadata"]
        self.assertEqual(first["live_audio_start_ms"], 0)
        self.assertEqual(first["live_audio_end_ms"], 2000)
        self.assertEqual(first["live_audio_cues"], [{"text_end": 5, "audio_end_ms": 1000}, {"text_end": 7, "audio_end_ms": 2000}])
        self.assertEqual(first["live_spoken_length"], 7)
        self.session.transcript("assistant", "תשובה נוספת")
        self.assertEqual(self.store.messages(self.conversation)[1]["metadata"]["live_audio_start_ms"], 2000)

    async def test_tool_replay_executes_once_and_approval_is_not_a_live_tool(self):
        self.session.transcript("user", "read the file"); self.session.finish_transcript("user")
        self.session.transcript("assistant", "Starting now"); self.session.finish_transcript("assistant")
        def submit(*args, **kwargs):
            return SimpleNamespace(run_id=self.store.create_run(self.conversation, user_text=args[1], metadata=kwargs["metadata"]))
        self.runs.submit.side_effect = submit
        packet = {"toolCall": {"functionCalls": [{"id": "one", "name": "smarty_task", "args": {"action": "start", "instruction": "read"}}]}}
        await self.session.receive(packet); await self.session.receive(packet)
        self.runs.submit.assert_called_once()
        initial = self.session.ws.sent[0]["toolResponse"]["functionResponses"][0]
        self.assertEqual(initial["scheduling"], "SILENT")
        self.assertTrue(initial["willContinue"])
        await self.session.receive({"toolCall": {"functionCalls": [{"id": "two", "name": "approve_tool", "args": {"approved": True}}]}})
        self.assertIn("error", self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]["response"])

    async def test_start_acknowledges_once_when_no_spoken_introduction_exists(self):
        def submit(*args, **kwargs):
            return SimpleNamespace(run_id=self.store.create_run(self.conversation,user_text=args[1],metadata=kwargs["metadata"]))
        self.runs.submit.side_effect=submit
        packet={"toolCall":{"functionCalls":[{"id":"start-without-intro","name":"smarty_task","args":{"action":"start","instruction":"read"}}]}}
        await self.session.receive(packet)
        first=self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertTrue(first["response"]["acknowledge_start"])
        self.assertEqual(first["scheduling"],"WHEN_IDLE")
        await self.session.receive(packet)
        self.assertEqual(self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]["scheduling"],"SILENT")

    async def test_close_preserves_executor_restores_tts_and_persists_final(self):
        task = self.make_task()
        self.session.control("pause", task_id=task["id"])
        await self.session.close()
        self.runs.cancel.assert_not_called()
        self.assertFalse(any(call.args[1] == "resume" for call in self.runs.control_run.call_args_list))
        self.assertIsNone(self.core._live_voice_owner)
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"], "payload": {"status": "completed", "response": "done\n```py\nprint(1)\n```"}})
        final = self.store.messages(self.conversation)[-1]
        self.assertTrue(final["metadata"]["live_final"])
        self.assertIn("print(1)", final["content"])

    async def test_persistence_failure_still_releases_socket_and_legacy_tts(self):
        self.session.transcript("user", "unsaved tail")
        self.store.upsert_live_message = Mock(side_effect=OSError("disk unavailable"))
        await self.session.close()
        self.assertTrue(self.session.ws.closed)
        self.assertIsNone(self.core._live_voice_owner)
        self.assertTrue(self.session.cleanup_complete.is_set())
        self.assertTrue(self.session.error)

    async def test_large_history_uses_bounded_view_and_missing_historical_file_does_not_block(self):
        marker = "full file ending marker"
        path = Path(self.directory.name) / "example.txt"
        path.write_text("a" * 12000 + marker, encoding="utf-8")
        self.session.attachments = [{"path": str(path), "name": path.name, "kind": "file", "mime_type": "text/plain"}]
        self.store.append_message("user", "early detail", {"attachments": self.session.attachments}, session_id=self.conversation)
        text = self.session.context()
        self.assertIn("early detail", text); self.assertIn("example.txt", text)
        self.assertNotIn(marker, text)  # Files remain in Core, behind its tools/policy.
        path.unlink()
        self.session.attachments = []
        self.store.append_message("user", "topic " * 50000 + marker, session_id=self.conversation)
        source = self.store.messages(self.conversation)[-1]
        from smarti.live_context import token_count
        self.session.provider = "openai"
        self.session.context_view.invalidate()
        self.assertLessEqual(token_count(self.session.context()), 7600)
        tail = self.session.control("context", query="message:" + source["message_id"], offset=len("topic ") * 50000)
        self.assertIn(marker, tail["content"])
        self.session.provider = "gemini"
        self.session.context_view.invalidate()
        self.assertGreater(token_count(self.session.context(), "gemini"), 8192)
        self.assertEqual(self.session.gather_files(), [])

    async def test_cursor_gap_does_not_replay_old_audio(self):
        for _ in range(1500): self.session.emit("audio", audio="AAA=")
        result = await self.session.poll(0)
        self.assertTrue(result["gap"])
        self.assertEqual(result["events"], [])

    async def test_unapproved_file_is_not_sent_to_provider(self):
        path = Path(self.directory.name) / "private.txt"
        path.write_text("must not leave Core", encoding="utf-8")
        self.core._policy_decision = lambda capability: "ask"
        self.runs.request_approval = Mock(return_value=False)
        await self.session.admit_message("admission", "read", [{"path": str(path), "name": path.name}])
        self.runs.request_approval.assert_called_once()
        self.assertEqual(self.session.ws.sent, [])
        self.assertEqual(self.store.messages(self.conversation), [])
        self.assertIn("error", self.session.events[-1])

    async def test_live_transcription_never_displays_partial_internal_memory_envelopes(self):
        for delta in ("Done.", "<smarti_", 'memory>{"operations":[]}', "</smarti_memory>"):
            self.session.transcript("assistant", delta)
            self.assertNotIn("smarti_", self.store.messages(self.conversation)[0]["content"])
        self.session.finish_transcript("assistant")
        self.assertEqual(self.store.messages(self.conversation)[0]["content"], "Done.")

    def test_distinct_tasks_have_distinct_persisted_process_ids(self):
        first, second = self.make_task("first"), self.make_task("second")
        self.assertNotEqual(first["id"], second["id"])
        process = [message for message in self.store.messages(self.conversation) if message["metadata"].get("live_process")]
        self.assertEqual(len(process), 2)

    def test_prose_and_rich_blocks_are_separate(self):
        text = "Finished\n```python\nprint(42)\n```\n\n|a|b|\n|---|---|\n|1|2|\nMore prose"
        blocks = visual_blocks(text)
        self.assertIn("print(42)", blocks); self.assertIn("|1|2|", blocks)
        self.assertNotIn("More prose", blocks)

    def test_gfm_tables_without_outer_pipes_and_artifact_links_survive(self):
        text = "Summary\nName | Value\n--- | ---\none | 42\n\n[Download](file:///C:/result.txt)\n![Preview](https://example.com/result.png)"
        blocks = visual_blocks(text)
        self.assertIn("Name | Value\n--- | ---\none | 42", blocks)
        self.assertIn("[Download](file:///C:/result.txt)", blocks)
        self.assertIn("![Preview](https://example.com/result.png)", blocks)
        self.assertNotIn("Summary", blocks)

    def test_lossless_context_frames_and_shared_text_references(self):
        value = "שלום 🌍" * 1000
        chunks = list(context_chunks(value))
        self.assertEqual("".join(chunks), value)
        self.assertTrue(all(len(chunk.encode("utf-8")) <= 450 for chunk in chunks))
        packed = packed_context({"first": value, "same": value})
        self.assertEqual(len(packed["full_texts"]), 1)
        self.assertEqual(packed["full_texts"][packed["context"]["first"]["full_text_ref"]], value)

    async def test_async_progress_is_silent_and_final_is_scheduled_when_idle(self):
        task = self.make_task()
        self.session.tasks[task["id"]]["call_id"] = "native-call"
        self.session.forwarder = asyncio.create_task(self.session.forward_events())
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_step", "run_id": task["run_id"], "payload": {"value": "tool finished"}})
        for _ in range(200):
            if self.session.ws.sent: break
            await asyncio.sleep(.01)
        response = self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertEqual(response["scheduling"], "SILENT")
        self.assertTrue(response["willContinue"])
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"], "payload": {"status": "completed", "response": "Done\n```py\nprint(42)\n```"}})
        for _ in range(200):
            if any(not item.get("willContinue", True) for sent in self.session.ws.sent for item in sent.get("toolResponse", {}).get("functionResponses", [])): break
            await asyncio.sleep(.01)
        response = self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertEqual(response["scheduling"], "WHEN_IDLE")
        self.assertFalse(response["willContinue"])
        self.session.control("deliver", task_id=task["id"], run_id=task["run_id"])
        await self.session.receive({"serverContent": {"outputTranscription": {"text": "הסתיים"}, "turnComplete": True}})
        final = self.store.messages(self.conversation)[-1]
        self.assertEqual(final["metadata"]["live_task_id"], task["id"])
        self.assertIn("print(42)", final["content"])

    async def test_progress_bursts_keep_all_facts_in_one_silent_update(self):
        task = self.make_task()
        self.session.tasks[task["id"]]["call_id"] = "native-call"
        self.session.forwarder = asyncio.create_task(self.session.forward_events())
        for i in range(25):
            self.session.queue_run_event({"event_type":"run_step", "run_id":task["run_id"], "payload":{"value":f"confirmed-{i}"}})
        for _ in range(200):
            if self.session.ws.sent: break
            await asyncio.sleep(.01)
        self.assertEqual(len(self.session.ws.sent), 1)
        result = self.session.ws.sent[0]["toolResponse"]["functionResponses"][0]
        self.assertEqual(result["scheduling"], "SILENT")
        facts = json.loads(result["response"]["progress"])
        self.assertEqual(len(facts["context"]["progress_events"]),25)
        self.assertIn("context_changes", facts["context"])
        self.assertNotIn("full_canonical_context", facts["context"])

    async def test_native_update_requires_new_user_input_but_accepts_a_spoken_correction(self):
        task = self.make_task()
        async def update(call):
            await self.session.receive({"toolCall":{"functionCalls":[{"id":call,"name":"smarty_task","args":{"action":"update","task_id":task["id"],"instruction":"Use destination B"}}]}})
        await update("redundant")
        self.runs.control_run.assert_not_called()
        ack = self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertTrue(ack["response"]["unchanged"])
        self.assertEqual(ack["scheduling"],"SILENT")
        self.session.transcript("user","Actually use B")
        await update("correction")
        self.runs.control_run.assert_called_once()
        self.assertIn("Use destination B",self.runs.control_run.call_args.args[2])

    def test_legacy_tts_is_suspended_without_saving_settings(self):
        core = SimpleNamespace(_live_voice_owner="live", _tts_session=Mock())
        with self.assertRaises(RuntimeError): SpeechMixin.start_speaking(core, "text")
        SpeechMixin.speak_text(core, "text")
        core._tts_session.start.assert_not_called()

    def test_terminal_result_is_durable_before_voice_callback_and_regular_chat_is_unchanged(self):
        task = self.make_task()
        self.store.transition_run(task["run_id"], "completed", response_text="Full answer\n```py\nprint(1)\n```")
        row = self.session.coordinator.result(task)
        self.assertTrue(row["metadata"]["live_result_pending"])
        self.assertIn("print(1)", row["metadata"]["live_result_text"])
        self.store.mark_live_backend(task["run_id"], task["id"])
        self.assertFalse(self.session.coordinator.result(task)["metadata"].get("live_backend"))
        normal = self.store.create_run(self.conversation, user_text="ordinary")
        before = len(self.store.messages(self.conversation))
        self.store.transition_run(normal, "completed", response_text="ordinary answer")
        self.assertEqual(len(self.store.messages(self.conversation)), before)

    async def test_stalled_voice_replaces_same_reserved_answer_without_waiting_for_idle(self):
        task = self.make_task()
        self.session.voice_idle.clear()  # Missing provider turnComplete used to stall forever.
        self.session.delivery_timeout = .05
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"],
            "payload": {"status": "completed", "response": "Confirmed complete answer"}})
        identity = self.session.coordinator.result(task)["message_id"]
        for _ in range(100):
            row = self.session.coordinator.result(task)
            if row["metadata"]["live_delivery"] == "fallback": break
            await asyncio.sleep(.01)
        self.assertEqual(row["content"], "Confirmed complete answer")
        self.assertEqual(row["message_id"], identity)
        self.assertTrue(self.session.ws.sent)
        self.session.transcript("assistant", "late duplicate")
        self.assertEqual(len([r for r in self.store.messages(self.conversation) if r["metadata"].get("live_final")]), 1)
        self.assertFalse(self.session.closed)
        self.session.transcript("user", "new question")
        self.assertFalse(self.session.output_suppressed)

    async def test_old_speech_is_not_bound_to_the_next_final_and_playback_has_its_own_ack(self):
        task = self.make_task()
        self.session.transcript("assistant", "Still working")
        self.session.voice_idle.clear()
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"],
            "payload": {"status": "completed", "response": "Complete"}})
        for _ in range(100):
            if self.session.ws.sent: break
            await asyncio.sleep(.01)
        await self.session.receive({"serverContent": {"outputTranscription": {"text": " now"}, "turnComplete": True}})
        self.assertEqual(self.session.coordinator.result(task)["content"], "")
        self.session.control("deliver", task_id=task["id"], run_id=task["run_id"])
        self.session.output_audio(base64.b64encode(b"\0\0" * 24000).decode())
        await self.session.receive({"serverContent": {"outputTranscription": {"text": "Complete"}, "turnComplete": True}})
        row = self.session.coordinator.result(task)
        self.assertEqual(row["content"], "Complete")
        self.assertEqual(row["metadata"]["live_delivery"], "generated")
        await self.session.input({"sequence": 0, "playback_ms": 1000})
        self.assertEqual(self.session.coordinator.result(task)["metadata"]["live_delivery"], "spoken")

    async def test_partial_delivery_stall_replaces_one_answer_and_new_session_does_not_replay_it(self):
        task = self.make_task()
        self.session.delivery_timeout = .05
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"],
            "payload": {"status": "completed", "response": "Whole result"}})
        for _ in range(100):
            if self.session.ws.sent: break
            await asyncio.sleep(.01)
        self.session.control("deliver", task_id=task["id"], run_id=task["run_id"])
        self.session.transcript("assistant", "Whole")
        for _ in range(100):
            if self.session.coordinator.result(task)["metadata"]["live_delivery"] == "fallback": break
            await asyncio.sleep(.01)
        self.assertEqual(self.session.coordinator.result(task)["content"], "Whole result")
        await self.session.close()
        reopened = LiveSession(self.manager, self.conversation, "gemini", self.session.executor, [])
        try:
            self.assertIn(task["run_id"], reopened.queued_results)
            self.assertTrue(reopened.final_queue.empty())
        finally: await reopened.close()

    def test_ai_read_only_followup_keeps_segment_and_continuation_creates_another_run(self):
        task = self.make_task()
        original = self.session.tasks[task["id"]]["segments"][0]["id"]
        self.session.control("answer", task_id=task["id"])
        self.runs.submit.assert_called_once()
        self.assertEqual(self.session.tasks[task["id"]]["segments"][0]["id"], original)
        self.session.tasks[task["id"]]["status"] = "completed"
        self.store.transition_run(task["run_id"], "completed", response_text="Done")
        again = self.session.control("continue", "Do further work", task_id=task["id"])
        self.assertEqual(again["id"], task["id"])
        self.assertNotEqual(again["run_id"], task["run_id"])
        self.assertNotEqual(self.session.tasks[task["id"]]["segments"][0]["id"], original)
        self.assertEqual(len([r for r in self.store.messages(self.conversation) if r["metadata"].get("live_process")]), 2)

    def test_ai_revision_splits_at_the_applied_boundary_and_replayed_command_never_reexecutes(self):
        task = self.make_task()
        self.runs.control_run.return_value = {"revision": 1}
        self.session.transcript("user", "Use another destination")
        self.session.control("update", "Use B", task_id=task["id"], call_id="one")
        self.session.control("update", "Use B", task_id=task["id"], call_id="two")
        self.runs.control_run.assert_called_once()
        self.session.queue_run_event({"event_type": "run_revision_applied", "run_id": task["run_id"], "sequence": 9,
            "payload": {"revision": 1}})
        segments = self.session.tasks[task["id"]]["segments"]
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["before"], 9)
        self.assertEqual(segments[0]["status"], "completed")
        self.assertEqual(segments[1]["after"], 9)

    def test_explicit_rich_blocks_keep_their_anchors_without_a_formatting_inference(self):
        from smarti.live_content import compose_transcript, display_content
        source = "Here is code.<!--smarti-display-->```py\nprint(1)\n```<!--/smarti-display-->Then a table.<!--smarti-display-->|A|B|\n|---|---|\n|1|2|<!--/smarti-display-->Done."
        spoken = "Here is code.Then a table.Done."
        displayed = compose_transcript(spoken, source)
        self.assertLess(displayed.index("print(1)"), displayed.index("Then a table."))
        self.assertLess(displayed.index("|1|2|"), displayed.index("Done."))
        self.assertNotIn("smarti-display", display_content(source))
        paraphrased = compose_transcript("Finished.", source)
        self.assertLess(paraphrased.index("print(1)"), paraphrased.index("|1|2|"))

    async def test_lease_recovers_a_missed_terminal_callback_and_reopening_recovers_pending_text_quietly(self):
        task = self.make_task()
        self.store.transition_run(task["run_id"], "completed", response_text="Durable result")
        self.session.lease = asyncio.create_task(self.session.watch_lease())
        await asyncio.sleep(1.1)
        self.assertEqual(self.session.final_queue.qsize(), 1)
        await self.session.close()
        self.assertEqual(self.session.coordinator.result(task)["content"], "Durable result")
        # Simulate a completed run whose voice owner disappeared before delivery.
        self.session.coordinator.set_delivery(task, "ready", content="", live_result_pending=True)
        reopened = LiveSession(self.manager, self.conversation, "gemini", self.session.executor, [])
        try:
            self.assertEqual(reopened.coordinator.result(task)["content"], "Durable result")
            self.assertTrue(reopened.final_queue.empty())
        finally: await reopened.close()

    async def test_gpt_delayed_adjacent_final_fragments_keep_rich_content_and_one_result(self):
        self.session.provider = "openai"
        task = self.make_task()
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"],
            "payload": {"status": "completed", "response": "Done\n```py\nprint(42)\n```"}})
        for _ in range(100):
            if any(frame.get("type") == "session.commentary.append" for frame in self.session.ws.sent): break
            await asyncio.sleep(.01)
        self.session.control("deliver", task_id=task["id"], run_id=task["run_id"])
        self.session.transcript("assistant", "First", start=0, end=200)
        self.session.finish_transcript("assistant", True)
        await asyncio.sleep(.01)
        self.session.transcript("assistant", " second", start=300, end=500)
        self.session.finish_transcript("assistant", True)
        row = self.session.coordinator.result(task)
        self.assertIn("First second", row["content"])
        self.assertIn("print(42)", row["content"])
        self.assertEqual(len([row for row in self.store.messages(self.conversation) if row["metadata"].get("live_final")]), 1)
        self.assertEqual(sum(frame.get("type") == "session.commentary.append" for frame in self.session.ws.sent), 1)

    async def test_progress_transport_failure_does_not_close_voice_or_lose_the_terminal_result(self):
        task = self.make_task()
        self.session.tasks[task["id"]]["call_id"] = "native-call"
        original = self.session.ws.send_json
        self.session.ws.send_json = AsyncMock(side_effect=ConnectionError("temporary progress failure"))
        self.session.forwarder = asyncio.create_task(self.session.forward_events())
        self.session.queue_run_event({"event_type": "run_step", "run_id": task["run_id"], "payload": {"value": "progress"}})
        await asyncio.sleep(1.1)
        self.assertFalse(self.session.closed)
        self.session.ws.send_json = original
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"], "payload": {"status": "completed", "response": "Ready"}})
        self.assertEqual(self.session.final_queue.qsize(), 1)
        self.assertEqual(self.session.coordinator.result(task)["metadata"]["live_result_text"], "Ready")

    async def test_late_progress_speech_cannot_complete_result_before_explicit_delivery_claim(self):
        task = self.make_task()
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"], "payload": {"status": "completed", "response": "Verified final"}})
        for _ in range(100):
            if self.session.ws.sent: break
            await asyncio.sleep(.01)
        await self.session.receive({"serverContent": {"outputTranscription": {"text": "Still working"}, "turnComplete": True}})
        self.assertEqual(self.session.coordinator.result(task)["content"], "")
        self.assertFalse(self.session.final_delivered.is_set())
        with self.assertRaises(ValueError): self.session.control("deliver", run_id="another-run")
        self.session.control("deliver", task_id=task["id"], run_id=task["run_id"])
        await self.session.receive({"serverContent": {"outputTranscription": {"text": "Verified final"}, "turnComplete": True}})
        self.assertEqual(self.session.coordinator.result(task)["content"], "Verified final")

    async def test_provider_tool_cancellation_never_cancels_execution_and_barge_in_keeps_one_truncated_result(self):
        task = self.make_task()
        self.session.tasks[task["id"]]["call_id"] = "old-call"
        await self.session.receive({"toolCallCancellation": {"ids": ["old-call"]}})
        self.assertEqual(self.session.tasks[task["id"]]["call_id"], "")
        self.runs.cancel.assert_not_called()
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"], "payload": {"status": "completed", "response": "Complete original result"}})
        for _ in range(100):
            if self.session.ws.sent: break
            await asyncio.sleep(.01)
        self.session.control("deliver", task_id=task["id"], run_id=task["run_id"])
        self.session.transcript("assistant", "Complete")
        await self.session.receive({"serverContent": {"interrupted": True}})
        row = self.session.coordinator.result(task)
        self.assertEqual(row["content"], "Complete")
        self.assertEqual(row["metadata"]["live_delivery"], "truncated")
        await self.session.close()
        self.assertEqual(self.session.coordinator.result(task)["message_id"], row["message_id"])
        self.assertEqual(self.session.coordinator.result(task)["content"], "Complete")

    async def test_progress_misrouted_as_continue_keeps_one_execution_and_delivers_its_spoken_result(self):
        task = self.make_task("Create the complete file, including all remaining steps")
        execution = self.session.tasks[task["id"]]
        execution["call_id"] = "original-execution"
        self.store.transition_run(task["run_id"], "running")
        self.session.transcript("user", "מתקדם")
        packet = {"toolCall": {"functionCalls": [{"id": "misrouted-progress", "name": "smarty_task",
            "args": {"action": "continue", "task_id": task["id"], "instruction": "Finish creating the same file"}}]}}
        await self.session.receive(packet)
        response = self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertTrue(response["response"]["already_running"])
        self.assertFalse(response["willContinue"])
        self.assertEqual(response["scheduling"], "WHEN_IDLE")
        self.runs.submit.assert_called_once()
        self.runs.control_run.assert_not_called()
        self.assertEqual(self.session.tasks[task["id"]]["run_id"], task["run_id"])
        self.assertEqual(len(execution["segments"]), 1)
        await self.session.receive(packet)
        self.runs.submit.assert_called_once()
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"],
            "payload": {"status": "completed", "response": "The file was created"}})
        for _ in range(100):
            if self.session.delivery_task: break
            await asyncio.sleep(.01)
        for _ in range(100):
            if any(frame.get("toolResponse", {}).get("functionResponses", [{}])[0].get("id") == "original-execution" for frame in self.session.ws.sent): break
            await asyncio.sleep(.01)
        self.session.control("deliver", task_id=task["id"], run_id=task["run_id"])
        await self.session.receive({"serverContent": {"modelTurn": {"parts": [{"inlineData": {
            "mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(b"\0\0" * 24000).decode()}}]},
            "outputTranscription": {"text": "The file was created"}, "turnComplete": True}})
        self.assertEqual(self.session.coordinator.result(task)["metadata"]["live_delivery"], "generated")
        self.assertTrue(any(event["type"] == "audio" for event in self.session.events))
        self.assertEqual(len([row for row in self.store.messages(self.conversation) if row["metadata"].get("live_process")]), 1)
        self.assertEqual(len(self.store.list_runs(session_id=self.conversation)), 1)

    def test_continuation_cannot_queue_behind_any_active_durable_execution(self):
        for state in ("queued", "running", "waiting_for_approval", "waiting_for_input", "cancelling"):
            with self.subTest(state=state):
                task = self.make_task()
                self.store.transition_run(task["run_id"], state)
                self.session.tasks[task["id"]]["status"] = "completed"  # A stale callback must not authorize work.
                before = self.runs.submit.call_count
                result = self.session.control("continue", "Carry on", task_id=task["id"])
                self.assertTrue(result["already_running"])
                self.assertEqual(result["status"], state)
                self.assertEqual(self.runs.submit.call_count, before)

    async def test_pending_final_keeps_its_transport_and_speech_after_a_valid_continuation_starts(self):
        first = self.make_task()
        first_execution = self.session.tasks[first["id"]]
        first_execution["call_id"] = "first-call"
        self.store.transition_run(first["run_id"], "completed", response_text="First result")
        # A valid continuation may start before the asynchronous finish callback.
        second = self.session.control("continue", "Additional work", task_id=first["id"], call_id="second-call")
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertIs(self.session.task_for_run(first["run_id"]), first_execution)
        self.assertEqual(self.session.task_for_run(first["run_id"])["call_id"], "first-call")
        self.session.finalizer = asyncio.create_task(self.session.deliver_finals())
        self.session.queue_run_event({"event_type": "run_finished", "run_id": first["run_id"],
            "payload": {"status": "completed", "response": "First result"}})
        for _ in range(100):
            if self.session.ws.sent: break
            await asyncio.sleep(.01)
        self.assertEqual(self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]["id"], "first-call")
        self.session.control("deliver", task_id=first["id"], run_id=first["run_id"])
        await self.session.receive({"serverContent": {"outputTranscription": {"text": "First result"}, "turnComplete": True}})
        self.assertEqual(self.session.coordinator.result(first)["metadata"]["live_delivery"], "generated")
        self.assertEqual(self.session.tasks[first["id"]]["run_id"], second["run_id"])
        self.assertEqual(self.session.tasks[first["id"]]["status"], "queued")
        self.assertEqual(len(self.store.list_runs(session_id=self.conversation)), 2)

    async def test_gemini_result_without_native_call_uses_gemini_delivery_claim(self):
        await self.session.send_task_result({"call_id": ""}, "Verified terminal evidence")
        request = self.session.ws.sent[-1]["clientContent"]
        self.assertTrue(request["turnComplete"])
        prompt = request["turns"][0]["parts"][0]["text"]
        self.assertIn("smarty_task action=deliver", prompt)
        self.assertNotIn("client delegation", prompt)
