"""Real provider fragment contracts, persistence and cancellation without charges."""
import json
from pathlib import Path
import tempfile
import queue
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from smarti.agent.streaming import LiveResponse, collect_http_stream, sse_objects
from smarti.agent.local_streaming import local_progress_response
from smarti.common import MODEL_PROVIDER_ORDER, is_openai_compatible_provider
from smarti.history import ChatSessionStore
from tests.test_api_provider_runtime import RequestCore
from tests.test_conversation_runs import _FakeCore
from smarti.run_manager import ConversationRunManager
from smarti.local_gateway import SmartiLocalGateway
from smarti.managers import AgentRuntime
from smarti.codex_stream import _read_turn, isolated_overrides


class Response:
    status_code = 200
    headers = {"Content-Type": "text/event-stream"}
    def __init__(self, frames):
        self.frames = frames
        self.closed = False
    def iter_lines(self, **_kwargs):
        for frame in self.frames:
            yield "data: " + json.dumps(frame, ensure_ascii=False)
            yield ""
    def close(self):
        self.closed = True


class ChatStreamingTests(unittest.TestCase):
    def live(self, **options):
        batches = []
        live = LiveResponse(batches.append, **options)
        return live, batches

    def test_textual_tool_header_is_visible_before_long_arguments_and_no_json_leaks(self):
        live, batches = self.live()
        payload = 'בודק קובץ\n{"method":"tools/call","params":{"name":"canvas_manager","arguments":{"content":"' + "a" * 150000 + '"}}}'
        for offset in range(0, len(payload), 19):
            live.text(payload[offset:offset + 19])
        live.finish(has_tools=True)
        events = [event for batch in batches for event in batch["events"]]
        self.assertTrue(any(event.get("name") == "canvas_manager" for event in events))
        self.assertEqual(live.visible.strip(), "בודק קובץ")
        self.assertLessEqual(len(live.calls["0"]["arguments"]), 12000)
        self.assertNotIn("tools/call", "".join(event.get("text", "") for event in events))
        self.assertLess(len(events), 200)

    def test_nested_argument_names_are_not_mistaken_for_tools(self):
        live, _ = self.live()
        value = json.dumps({"tool_calls": [{"name": "file_manager", "arguments": {"name": "private.txt"}}, {"name": "web_manager", "arguments": {"name": "another"}}]})
        for char in value:
            live.text(char)
        self.assertEqual([call["name"] for call in live.calls.values()], ["file_manager", "web_manager"])

    def test_split_thinking_and_memory_do_not_enter_visible_text(self):
        live, batches = self.live()
        for char in "<think>private reasoning</think>שלום %%\u0025private memory%%\u0025 עולם":
            live.text(char)
        live.finish()
        self.assertEqual(live.visible, "שלום  עולם")
        self.assertNotIn("private", "".join(event.get("text", "") for batch in batches for event in batch["events"]))

    def test_known_secret_prefix_is_withheld_across_token_boundaries(self):
        live, batches = self.live(secrets=["super-secret-value"], redact=lambda text: text.replace("super-secret-value", "[REDACTED]"))
        for char in "answer: super-secret-value done":
            live.text(char)
        live.finish()
        snapshots = [event.get("text", "") for batch in batches for event in batch["events"]]
        self.assertNotIn("super-secret-value", "".join(snapshots))
        self.assertEqual(live.visible, "answer: [REDACTED] done")

    def test_codex_json_envelope_reveals_only_decoded_answer(self):
        live, batches = self.live()
        value = json.dumps({"kind": "final", "tool_calls": None, "final_answer": "שלום\nworld", "progress_report": None}, ensure_ascii=False)
        for char in value:
            live.text(char)
        live.finish()
        self.assertEqual(live.visible, "שלום\nworld")
        self.assertNotIn("final_answer", "".join(event.get("text", "") for batch in batches for event in batch["events"]))

    def test_code_example_is_markdown_not_a_tool(self):
        live, _ = self.live()
        value = 'דוגמה לקריאה:\n```json\n{"method":"tools/call","params":{"name":"example"}}\n```'
        for char in value:
            live.text(char)
        live.finish()
        self.assertFalse(live.calls)
        self.assertEqual(live.visible, value)

    def test_every_compatible_provider_publishes_real_deltas_and_final_usage(self):
        providers = [name for name in MODEL_PROVIDER_ORDER if name == "local" or is_openai_compatible_provider(name)]
        for name in providers:
            with self.subTest(provider=name):
                core = RequestCore(name)
                batches = []
                core.stream_callback = batches.append
                chunks = [NS(choices=[NS(index=0, delta=NS(content="שלום "), finish_reason=None)], usage=None),
                          NS(choices=[NS(index=0, delta=NS(content="עולם"), finish_reason="stop")], usage=NS(prompt_tokens=10, completion_tokens=2, total_tokens=12))]
                create = Mock(return_value=iter(chunks))
                core._openai_compatible_client_for_request = lambda _name: NS(chat=NS(completions=NS(create=create)))
                text, usage = core._handle_api_request_with_retry("model-a", [{"role": "user", "content": "hello"}], retry_wait_times=[])
                self.assertEqual(text, "שלום עולם")
                self.assertEqual(usage["total"], 12)
                self.assertTrue(create.call_args.kwargs["stream"])
                self.assertTrue(any(event["kind"] == "text_delta" for batch in batches for event in batch["events"]))

    def test_claude_tool_start_and_partial_json_are_distinct_and_validated(self):
        live, batches = self.live()
        response = Response([
            {"type": "message_start", "message": {"usage": {"input_tokens": 20}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "call", "name": "canvas_manager", "input": {}}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": '{"content":"hi"}'}},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 3}},
            {"type": "message_stop"},
        ])
        result = collect_http_stream(response, "anthropic", live, lambda: None).json()
        self.assertEqual(result["content"][0]["input"], {"content": "hi"})
        self.assertEqual(result["usage"], {"input_tokens": 20, "output_tokens": 3})
        self.assertTrue(response.closed)
        self.assertEqual(batches[1]["events"][0]["kind"], "tool_preparing")

    def test_malformed_native_arguments_cannot_become_an_empty_executable_call(self):
        core = RequestCore("openai")
        with self.assertRaises(ValueError):
            core._canonical_native_tool_response([{"name": "file_manager", "arguments": '{"path":'}])

    def test_stream_snapshot_is_durable_and_deduplicated_by_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "history.sqlite"))
            session = store.create_session(set_active=False)["id"]
            run = store.create_run(session)
            live = LiveResponse(lambda value: store.append_run_event(run, "run_stream", {"value": value}))
            live.text("first ")
            live.text("second")
            live.finish()
            state = store.run(run)["metadata"]["stream"]
            self.assertEqual(state["blocks"][live.request_id]["text"], "first second")
            self.assertEqual(state["cursor"], store.run_events(run)[-1]["id"])

    def test_lmstudio_prefill_is_real_and_reasoning_is_not_visible(self):
        core = RequestCore("local")
        live, batches = self.live()
        core._current_stream = live
        core._request_get = lambda _url, **_kwargs: NS(status_code=200, json=lambda: {"models": [{"type": "llm", "key": "local"}]})
        response = Response([{ "type": "prompt_processing.progress", "progress": .37 },
            {"type": "reasoning.delta", "content": "secret thought"}, {"type": "message.delta", "content": "answer"},
            {"type": "chat.end", "result": {"output": [{"type": "message", "content": "answer"}], "stats": {"input_tokens": 5, "total_output_tokens": 3}}}])
        core._request_post = Mock(return_value=response)
        result = local_progress_response(core, "http://localhost:54321/v1", "local", [{"role": "assistant", "content": "prior answer"}, {"role": "user", "content": "continue"}], "system", {}, "auto")
        self.assertEqual(result[0], "answer")
        payload = core._request_post.call_args.kwargs["json"]
        self.assertFalse(payload["store"])
        self.assertEqual(payload["integrations"], [])
        self.assertIn("prior answer", payload["input"][0]["content"])
        self.assertTrue(any(event.get("percent") == 37 for batch in batches for event in batch["events"]))
        self.assertNotIn("secret thought", live.visible)

    def test_cancellation_closes_the_http_stream(self):
        response = Response([{"content": "partial"}])
        def cancelled():
            raise RuntimeError("CANCELLED_BY_USER")
        with self.assertRaisesRegex(RuntimeError, "CANCELLED"):
            list(sse_objects(response, cancelled))
        self.assertTrue(response.closed)

    def test_truncated_http_streams_fail_and_keep_live_partial_text(self):
        for provider, frames in [("gemini", [{"candidates": [{"content": {"parts": [{"text": "partial"}]}}]}]),
                                 ("anthropic", [{"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "partial"}}])]:
            with self.subTest(provider=provider):
                live, _ = self.live()
                response = Response(frames)
                with self.assertRaisesRegex(RuntimeError, "disconnected"):
                    collect_http_stream(response, provider, live, lambda: None)
                self.assertTrue(response.closed)
                self.assertEqual(live.visible, "partial")

    def test_gemini_stream_preserves_usage_and_hides_thoughts(self):
        live, _ = self.live()
        response = Response([
            {"candidates": [{"content": {"parts": [{"text": "private", "thought": True}, {"text": "שלום "}]}}]},
            {"candidates": [{"content": {"parts": [{"text": "עולם"}]}, "finishReason": "STOP"}], "usageMetadata": {"totalTokenCount": 15}},
        ])
        data = collect_http_stream(response, "gemini", live, lambda: None).json()
        self.assertEqual(live.visible, "שלום עולם")
        self.assertEqual(data["usageMetadata"]["totalTokenCount"], 15)
        self.assertEqual(data["candidates"][0]["finishReason"], "STOP")

    def test_gemini_live_tools_use_an_early_text_header_without_changing_history_api(self):
        core = RequestCore("gemini")
        batches = []
        core.stream_callback = batches.append
        core._native_tool_specs_for_request = lambda: [{"name": "file_manager", "description": "file", "parameters": {"type": "object"}}]
        payload = '{"method":"tools/call","params":{"name":"file_manager","arguments":{"path":"test"}}}'
        frames = [{"candidates": [{"content": {"parts": [{"text": payload[:50]}]}}]},
                  {"candidates": [{"content": {"parts": [{"text": payload[50:]}]}, "finishReason": "STOP"}]}]
        core._request_post = Mock(return_value=Response(frames))
        text, _ = core._handle_api_request_with_retry("gemini-test", [{"role": "user", "parts": [{"text": "read"}]}], retry_wait_times=[])
        self.assertEqual(text, payload)
        kwargs = core._request_post.call_args.kwargs
        self.assertNotIn("tools", kwargs["json"])
        self.assertIn("streamGenerateContent", core._request_post.call_args.args[0])
        self.assertTrue(any(event.get("name") == "file_manager" for batch in batches for event in batch["events"]))

    def test_responses_api_native_call_header_precedes_argument_completion(self):
        core = RequestCore("openai")
        live, batches = self.live()
        core._current_stream = live
        completed = NS(status="completed")
        events = [NS(type="response.output_text.delta", delta="בודק"),
                  NS(type="response.output_item.added", output_index=1, item=NS(type="function_call", name="canvas_manager", call_id="native")),
                  NS(type="response.function_call_arguments.delta", output_index=1, delta='{"content":"'),
                  NS(type="response.function_call_arguments.delta", output_index=1, delta='value"}'),
                  NS(type="response.completed", response=completed)]
        self.assertIs(core._collect_responses_stream(iter(events)), completed)
        self.assertEqual(live.calls["1"]["arguments"], '{"content":"value"}')
        self.assertEqual(live.calls["1"]["provider_call_id"], "native")
        self.assertTrue(any(event["kind"] == "tool_preparing" for batch in batches for event in batch["events"]))
        with self.assertRaisesRegex(RuntimeError, "completion"):
            core._collect_responses_stream(iter(events[:-1]))

    def test_codex_app_server_deltas_are_live_and_tools_stay_with_core(self):
        incoming, sent = queue.Queue(), []
        value = {"kind": "final", "final_answer": "שלום", "tool_calls": None, "progress_report": None}
        raw = json.dumps(value, ensure_ascii=False)
        packets = [{"method": "turn/started", "params": {"turn": {"id": "turn"}}},
                   {"method": "item/started", "params": {"item": {"id": "comment", "type": "agentMessage", "phase": "commentary"}}},
                   {"method": "item/agentMessage/delta", "params": {"itemId": "comment", "delta": "בודק את הנתונים"}},
                   {"method": "item/completed", "params": {"item": {"id": "comment", "type": "agentMessage", "phase": "commentary", "text": "בודק את הנתונים"}}},
                   {"method": "item/reasoning/textDelta", "params": {"delta": "hidden"}},
                   {"method": "item/commandExecution/requestApproval", "id": 8, "params": {}},
                   *({"method": "item/agentMessage/delta", "params": {"delta": char}} for char in raw),
                   {"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"last": {"inputTokens": 5, "outputTokens": 3, "totalTokens": 8}}}},
                   {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}]
        for packet in packets:
            incoming.put(json.dumps(packet))
        provider = NS(_decode_structured_turn=lambda text: json.loads(text)["final_answer"])
        live, _ = self.live()
        text, usage = _read_turn(provider, None, incoming, sent.append, time.monotonic() + 5, "thread", threading.Event(), live, "model")
        self.assertEqual(text, "שלום")
        self.assertEqual(live.visible, "שלום")
        self.assertEqual(list(live.report_visible.values()), ["בודק את הנתונים"])
        self.assertEqual(usage["total"], 8)
        self.assertEqual(sent[0]["error"]["code"], -32601)

    def test_codex_envelope_ignores_names_inside_long_argument_json(self):
        live, _ = self.live()
        raw = json.dumps({"kind": "tool_calls", "progress_report": "בודק", "tool_calls": [{"name": "canvas_manager", "arguments_json": json.dumps({"name": "document", "content": "x" * 150000})}], "final_answer": None}, ensure_ascii=False)
        for offset in range(0, len(raw), 19):
            live.text(raw[offset:offset + 19])
        self.assertEqual([call["name"] for call in live.calls.values()], ["canvas_manager"])
        self.assertEqual(live.visible, "בודק")

    def test_codex_overrides_disable_account_tools_without_writing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            original = '[mcp_servers.personal]\ncommand="server"\n[plugins."example@source"]\nenabled=true\n'
            path.write_text(original, encoding="utf-8")
            config = isolated_overrides({"CODEX_HOME": directory})
            self.assertFalse(config['mcp_servers."personal".enabled'])
            self.assertFalse(config['plugins."example@source".enabled'])
            self.assertFalse(config["features.shell_tool"])
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_llama_progress_preserves_server_chat_template_and_cached_usage(self):
        core = RequestCore("local")
        live, batches = self.live()
        core._current_stream = live
        core._request_get = lambda url, **_: NS(status_code=200, json=lambda: {"default_generation_settings": {}, "chat_template": "template"} if url.endswith("/props") else {})
        frames = [{"prompt_progress": {"total": 100, "processed": 42}}, {"content": "answer", "stop": True, "tokens_cached": 30, "timings": {"prompt_n": 70, "predicted_n": 3}}]
        core._request_post = Mock(side_effect=[NS(status_code=200, json=lambda: {"prompt": "SERVER_FORMATTED_HISTORY"}), Response(frames)])
        messages = [{"role": "system", "content": "system"}, {"role": "assistant", "content": "prior"}, {"role": "user", "content": "continue"}]
        result = local_progress_response(core, "http://localhost:54322/v1", "local", messages, "system", {}, "auto")
        self.assertEqual(core._request_post.call_args_list[0].kwargs["json"]["messages"], messages)
        self.assertEqual(core._request_post.call_args.kwargs["json"]["prompt"], "SERVER_FORMATTED_HISTORY")
        self.assertEqual(result[1]["prompt"], 100)
        self.assertTrue(any(event.get("percent") == 42 for batch in batches for event in batch["events"]))

    def test_local_custom_routes_and_multimodal_llama_use_existing_compatible_api(self):
        core = RequestCore("local")
        core._current_stream, _ = self.live()
        core._request_get = Mock(side_effect=AssertionError("custom route must not be probed"))
        self.assertIsNone(local_progress_response(core, "http://localhost:54323/custom/v1", "local", [], "", {}, "auto"))
        core._request_get = lambda url, **_: NS(status_code=200, json=lambda: {"default_generation_settings": {}, "chat_template": "template"} if url.endswith("/props") else {})
        core._request_post = Mock(side_effect=AssertionError("multimodal must use compatible API"))
        messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}}]}]
        self.assertIsNone(local_progress_response(core, "http://localhost:54324/v1", "local", messages, "", {}, "auto"))

    def test_code_examples_and_nested_json_never_execute_as_tools(self):
        runtime = AgentRuntime(Mock())
        call = '{"method":"tools/call","params":{"name":"file_manager","arguments":{}}}'
        for text in ['דוגמה:\n```json\n' + call + '\n```', 'Example: `' + call + '`', '{"example":' + call + '}']:
            self.assertFalse(runtime.extract_tool_calls(text)["is_tool_call_intent"])
        self.assertTrue(runtime.extract_tool_calls('בודק\n' + call)["is_tool_call_intent"])

    def test_authenticated_live_transport_wakes_and_replays_from_its_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _FakeCore(Path(directory) / "history.sqlite")
            core.run_manager = ConversationRunManager(core)
            session = core.chat_store.create_session(set_active=False)["id"]
            run = core.chat_store.create_run(session)
            gateway = SmartiLocalGateway(core, "isolated-token", port=0)
            self.assertTrue(gateway.start())
            initial_cursor = core.chat_store.events_after(0)[-1]["event_id"]
            url = f"http://127.0.0.1:{gateway.port}/v2/events/live?after_event_id={initial_cursor}"
            def request(target=url):
                with urllib.request.urlopen(urllib.request.Request(target, headers={"Authorization": "Bearer isolated-token"}), timeout=4) as response:
                    return json.loads(response.read())["data"]["items"]
            try:
                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(url, timeout=2)
                self.assertEqual(denied.exception.code, 401)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pending = pool.submit(request)
                    time.sleep(.15)
                    core.run_manager._emit("run_stream", run, session, {"value": {"events": [{"kind": "request_start", "request_id": "r"}]}})
                    first = pending.result(timeout=4)
                cursor = first[-1]["event_id"]
                core.run_manager._emit("run_stream", run, session, {"value": {"events": [{"kind": "text_delta", "request_id": "r", "block_id": "r", "text": "live"}]}})
                replay = request(url.replace(f"after_event_id={initial_cursor}", f"after_event_id={cursor}"))
                self.assertTrue(all(item["event_id"] > cursor for item in replay))
                self.assertEqual(replay[-1]["payload"]["value"]["events"][0]["text"], "live")
            finally:
                gateway.stop()
                core.run_manager.shutdown(wait=True)

    def test_sensitive_parameter_preview_stays_hidden_after_the_header_leaves_the_tail(self):
        live, batches = self.live()
        live.tool(0, "file_manager")
        value = '{"password":"' + "private" * 5000 + '"}'
        for offset in range(0, len(value), 19):
            live.tool(0, arguments=value[offset:offset + 19])
        live.flush()
        previews = [event.get("arguments_text", "") for batch in batches for event in batch["events"]]
        self.assertNotIn("private", "".join(previews))
        self.assertIn("[פרמטרים רגישים הוסתרו]", previews)

    def test_user_facing_stream_preserves_email_and_paths_while_redacting_credentials(self):
        core = RequestCore("local")
        core.settings["openai_api_key"] = "sk-private-credential"
        self.assertEqual(core._redact_stream_text('user@example.org C:\\Users\\Someone\\file.txt sk-private-credential'),
                         'user@example.org C:\\Users\\Someone\\file.txt [REDACTED:openai_api_key]')

    def test_runtime_failure_and_cancellation_preserve_the_durable_partial_answer(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as directory:
                core = _FakeCore(Path(directory) / "history.sqlite")
                core.run_manager = ConversationRunManager(core)
                session = core.chat_store.create_session(set_active=False)["id"]
                def generate(_text, **_kwargs):
                    live = LiveResponse(core._local.callbacks["stream_callback"])
                    live.text("partial answer")
                    live.flush()
                    if cancel:
                        core.run_manager.handle(core._local.run_id).cancel_event.set()
                    raise RuntimeError("fixture disconnected")
                core.send_message = generate
                try:
                    handle = core.run_manager.submit(session, "test")
                    self.assertTrue(handle.done_event.wait(5))
                    self.assertEqual(handle.status, "cancelled" if cancel else "failed")
                    message = core.chat_store.messages_page(session)["messages"][-1]
                    self.assertIn("partial answer", message["content"])
                    self.assertEqual(message["metadata"]["run_status"], handle.status)
                finally:
                    core.run_manager.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
