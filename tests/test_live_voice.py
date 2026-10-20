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
                                    _ensure_secret_loaded=lambda key: self.settings.get(key, ""), stop_speaking=Mock())
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

    async def test_gpt_interleaved_transcripts_keep_independent_stable_ids(self):
        self.session.provider = "openai"
        for role, text, start in (("input", "I would", 100), ("output", "Sure", 120), ("input", " like", 200)):
            await self.session.receive({"type": f"session.{role}_transcript.delta", "delta": text, "start_ms": start, "end_ms": start + 50})
        rows = self.store.messages(self.conversation)
        self.assertEqual([row["content"] for row in rows], ["I would like", "Sure"])
        identity = rows[0]["message_id"]
        self.session.finish_transcript("user", True)
        self.session.transcript("user", " help", start=300, end=350)
        self.assertEqual(self.store.messages(self.conversation)[0]["message_id"], identity)
        self.session.transcript("user", "Another turn", start=4000, end=4100)
        self.assertEqual(len(self.store.messages(self.conversation)), 3)

    async def test_tool_replay_executes_once_and_approval_is_not_a_live_tool(self):
        def submit(*args, **kwargs):
            return SimpleNamespace(run_id=self.store.create_run(self.conversation, user_text=args[1], metadata=kwargs["metadata"]))
        self.runs.submit.side_effect = submit
        packet = {"toolCall": {"functionCalls": [{"id": "one", "name": "smarty_task", "args": {"action": "start", "instruction": "read"}}]}}
        await self.session.receive(packet); await self.session.receive(packet)
        self.runs.submit.assert_called_once()
        await self.session.receive({"toolCall": {"functionCalls": [{"id": "two", "name": "approve_tool", "args": {"approved": True}}]}})
        self.assertIn("error", self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]["response"])

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

    async def test_full_history_file_content_and_explicit_context_overflow(self):
        marker = "full file ending marker"
        path = Path(self.directory.name) / "example.txt"
        path.write_text("a" * 12000 + marker, encoding="utf-8")
        self.session.attachments = [{"path": str(path), "name": path.name, "kind": "file", "mime_type": "text/plain"}]
        self.store.append_message("user", "early detail", session_id=self.conversation)
        text = self.session.context()
        self.assertIn("early detail", text); self.assertIn(marker, text)
        self.store.append_message("user", "b" * 120000, session_id=self.conversation)
        with self.assertRaisesRegex(ValueError, "ההקשר המלא"):
            self.session.context()

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
        await asyncio.sleep(.02)
        response = self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertEqual(response["scheduling"], "SILENT")
        self.assertTrue(response["willContinue"])
        self.session.queue_run_event({"event_type": "run_finished", "run_id": task["run_id"], "payload": {"status": "completed", "response": "Done\n```py\nprint(42)\n```"}})
        await asyncio.sleep(.05)
        response = self.session.ws.sent[-1]["toolResponse"]["functionResponses"][0]
        self.assertEqual(response["scheduling"], "WHEN_IDLE")
        self.assertFalse(response["willContinue"])
        await self.session.receive({"serverContent": {"outputTranscription": {"text": "הסתיים"}, "turnComplete": True}})
        final = self.store.messages(self.conversation)[-1]
        self.assertEqual(final["metadata"]["live_task_id"], task["id"])
        self.assertIn("print(42)", final["content"])

    def test_legacy_tts_is_suspended_without_saving_settings(self):
        core = SimpleNamespace(_live_voice_owner="live", _tts_session=Mock())
        with self.assertRaises(RuntimeError): SpeechMixin.start_speaking(core, "text")
        SpeechMixin.speak_text(core, "text")
        core._tts_session.start.assert_not_called()
