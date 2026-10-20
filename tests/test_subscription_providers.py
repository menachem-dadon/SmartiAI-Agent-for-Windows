"""Subscription adapters without personal credentials, model calls or paid requests."""
import copy
import base64
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from smarti.common import MODEL_PROVIDER_ORDER, SmartiCancelled, model_reasoning_options, provider_requires_api_key
from smarti.config import DEFAULT_SETTINGS
from smarti.subscription_providers import CLAUDE, ANTIGRAVITY, get_provider
from smarti.subscription_providers.base import SubscriptionError, SubscriptionProvider, register_models, safe_failure
from smarti.subscription_providers.claude import ClaudeProvider
from smarti.subscription_providers.antigravity import AntigravityProvider
from smarti.subscription_providers.connections import Connections
from smarti.agent.streaming import LiveResponse
from tests.test_api_provider_runtime import RequestCore


class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = ClaudeProvider(self.temp.name, "claude_login")

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_keeps_subscription_routes_without_api_secrets_and_requested_defaults(self):
        for name in (CLAUDE, ANTIGRAVITY):
            self.assertIn(name, MODEL_PROVIDER_ORDER)
            self.assertFalse(provider_requires_api_key(name))
            self.assertEqual(DEFAULT_SETTINGS[f"selected_{name}_model"],
                "claude-sonnet-5-5" if name == CLAUDE else "gemini-3.8-flash-high")

    def test_environment_uses_only_explicit_token_strategy_and_keeps_parent_unchanged(self):
        inherited = {"CLAUDE_CODE_OAUTH_TOKEN": "test-subscription-secret", "ANTHROPIC_API_KEY": "test-api-key",
            "ANTHROPIC_AUTH_TOKEN": "other-auth", "ANTHROPIC_BASE_URL": "https://invalid.example",
            "CLAUDE_CODE_USE_VERTEX": "1", "ANTHROPIC_MODEL": "another-model"}
        with mock.patch.dict(os.environ, inherited):
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", self.provider.environment())
            token = ClaudeProvider(self.temp.name, "setup_token_env").environment()
            self.assertEqual(token["CLAUDE_CODE_OAUTH_TOKEN"], "test-subscription-secret")
            for key in inherited:
                self.assertEqual(os.environ[key], inherited[key])
                if key != "CLAUDE_CODE_OAUTH_TOKEN":
                    self.assertNotIn(key, token)

    def test_logged_out_exit_is_disconnected_and_never_an_api_key_prompt(self):
        with mock.patch.object(self.provider, "command", return_value=["node", "bridge"]), \
             mock.patch.object(self.provider, "executable", return_value="claude"), \
             mock.patch.object(self.provider, "run", return_value=json.dumps({"loggedIn": False, "authMethod": "none"})) as run:
            result = self.provider.connection_status()
        self.assertEqual(result["state"], "disconnected")
        self.assertEqual(run.call_args.kwargs["ok_codes"], (0, 1))

    def test_free_plan_is_not_a_connected_subscription(self):
        raw = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "free"}
        with mock.patch.object(self.provider, "command"), mock.patch.object(self.provider, "executable"), \
             mock.patch.object(self.provider, "run", return_value=json.dumps(raw)):
            self.assertEqual(self.provider.connection_status()["state"], "account_ineligible")

    def test_api_or_wrong_oauth_mode_is_not_accepted(self):
        for mode in ("api_key", "api_key_helper", "third_party", "oauth_token"):
            with self.subTest(mode=mode), mock.patch.object(self.provider, "command"), \
                 mock.patch.object(self.provider, "executable"), mock.patch.object(self.provider, "run",
                    return_value=json.dumps({"loggedIn": True, "authMethod": mode, "apiProvider": "firstParty"})):
                self.assertEqual(self.provider.connection_status()["state"], "wrong_auth_mode")

    def test_missing_environment_token_does_not_fall_back_to_saved_login(self):
        self.provider.strategy = "setup_token_env"
        with mock.patch.object(self.provider, "command"), mock.patch.object(self.provider, "environment", return_value={}), \
             mock.patch.object(self.provider, "run") as run:
            self.assertEqual(self.provider.connection_status()["state"], "disconnected")
            run.assert_not_called()

    def test_catalog_uses_official_metadata_and_does_not_invent_effort(self):
        def metadata(command, **options):
            request = json.loads(options["payload"])
            self.assertEqual(request["method"], "metadata")
            self.assertNotIn("content", request)
            options["event"](json.dumps({"type": "metadata", "account": {"tokenSource": "none"}, "models": [
                {"value": "sonnet", "resolvedModel": "claude-test", "supportsEffort": True,
                 "supportedEffortLevels": ["low", "high", "not-real"]}, {"value": "plain"}]}))
        with mock.patch.object(self.provider, "command", return_value=[]), \
             mock.patch.object(self.provider, "executable", return_value="claude"), \
             mock.patch.object(self.provider, "run", side_effect=metadata):
            rows = self.provider.catalog()
        self.assertEqual(rows[0]["availability"], "unknown")
        self.assertEqual([value for value, _ in model_reasoning_options(CLAUDE, "sonnet")], ["low", "high"])
        self.assertEqual(model_reasoning_options(CLAUDE, "plain"), [])

    def turn(self, events, *, purpose="agent", stream=None, messages=None, inspect=None):
        self.provider.models = [{"id": "sonnet", "resolved_model": "claude-test", "efforts": ["low"]}]
        def run(command, **options):
            request = json.loads(options["payload"])
            self.assertNotIn("token", request)
            self.assertEqual("schema" in request, purpose == "agent")
            self.assertIn("Smarti system", Path(request["prompt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(request["effort"], "low")
            self.assertNotIn("--bare", command)
            if inspect:
                inspect(request)
            sequence = events if events and events[0].get("type") == "init" else [{"type": "init", "model": "claude-test"}, *events]
            for event in sequence:
                options["event"](json.dumps(event))
        with mock.patch.object(self.provider, "connection_status", return_value={"state": "connected"}), \
             mock.patch.object(self.provider, "command", return_value=["node", "bridge"]), \
             mock.patch.object(self.provider, "executable", return_value="claude"), \
             mock.patch.object(self.provider, "run", side_effect=run):
            return self.provider.complete(messages or [{"role": "system", "content": "Smarti system"},
                {"role": "user", "content": "שלום"}], "sonnet", reasoning_effort="low", purpose=purpose, stream=stream)

    def test_full_tool_turn_preserves_core_ownership_and_normalizes_usage(self):
        envelope = {"kind": "tool_calls", "progress_report": "בודק", "final_answer": None,
            "tool_calls": [{"name": "file_manager", "arguments_json": '{"action":"read"}'}]}
        response, usage = self.turn([{"type": "init", "model": "claude-test"},
            {"type": "result", "ok": True, "output": envelope,
             "usage": {"input_tokens": 10, "cache_read_input_tokens": 4, "cache_creation_input_tokens": 3, "output_tokens": 5}}])
        self.assertEqual(json.loads(response.split("\n", 1)[1])["tool_calls"][0]["name"], "file_manager")
        self.assertEqual(usage["total"], 22)
        self.assertIsNone(usage["estimated_cost_usd"])
        self.assertEqual(usage["effective_model"], "claude-test")

    def test_live_envelope_never_displays_wire_json_or_tool_arguments_as_answer(self):
        events = []
        live = LiveResponse(emit=lambda value: events.extend(value["events"]))
        envelope = {"kind": "final", "tool_calls": None, "final_answer": "תשובה", "progress_report": None}
        raw = json.dumps(envelope, ensure_ascii=False)
        response, _ = self.turn([{"type": "text", "text": raw[:30]}, {"type": "text", "text": raw[30:]},
            {"type": "result", "ok": True, "output": envelope}], stream=live)
        live.finish(response)
        visible = "".join(event.get("text", "") for event in events if event.get("kind") == "text_delta")
        self.assertNotIn('"kind"', visible)
        self.assertEqual(visible, "תשובה")

    def test_failed_missing_and_duplicate_results_cannot_be_success(self):
        final = {"type": "result", "ok": True, "output": {"kind": "final", "tool_calls": None,
            "final_answer": "ready", "progress_report": None}}
        for sequence in ([], [{"type": "result", "ok": False, "errors": ["usage limit"]}], [final, final],
                [{"type": "failure", "reason": "provider_contract_violation"}],
                [{"type": "init", "model": "wrong-model"}, final]):
            with self.subTest(sequence=sequence), self.assertRaises(SubscriptionError):
                self.turn(sequence)

    def test_title_has_no_tool_schema_and_returns_text(self):
        response, _ = self.turn([{"type": "result", "ok": True, "text": "כותרת"}], purpose="title")
        self.assertEqual(response, "כותרת")

    def test_images_and_pdfs_remain_next_to_their_own_conversation_turn(self):
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}}
        document = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": "cGRm"}}
        messages = [{"role": "system", "content": "Smarti system"},
            {"role": "user", "content": [{"type": "text", "text": "first image"}, image]},
            {"role": "assistant", "content": "earlier answer"},
            {"role": "user", "content": [{"type": "text", "text": "latest PDF"}, document]}]
        def inspect(request):
            self.assertEqual([block["type"] for block in request["content"]], ["text", "image", "text", "text", "document"])
            self.assertTrue(request["content"][2]["text"].startswith("[ASSISTANT]"))
            self.assertNotIn("cGRm", request["content"][3]["text"])
        self.turn([{"type": "result", "ok": True, "output": {"kind": "final", "tool_calls": None,
            "progress_report": None, "final_answer": "ok"}}], messages=messages, inspect=inspect)

    def test_antigravity_connection_requires_supported_version_and_readonly_account_metadata(self):
        provider = AntigravityProvider(self.temp.name, "google_login")
        quota = {"status": "SUCCESS", "num_turns": 0, "command": {"name": "usage", "data": {"groups": [
            {"name": "Gemini", "buckets": [{"window": "5h", "remaining_fraction": .75, "reset_time": "2026-10-19T12:00:00Z"}]}]}}}
        with mock.patch.object(provider, "executable", return_value="agy"), \
             mock.patch.object(provider, "run", side_effect=["1.4.2", json.dumps(quota), "gemini-test-high\tTest model\n"]):
            status = provider.connection_status()
            self.assertEqual(status["state"], "connected")
            self.assertEqual(status["quota"]["groups"][0]["buckets"][0]["remaining_fraction"], .75)
            self.assertEqual(provider.read_models(), ["gemini-test-high"])
        with mock.patch.object(provider, "executable", return_value="agy"), mock.patch.object(provider, "run", return_value="1.2.0"):
            self.assertEqual(provider.connection_status()["state"], "incompatible_version")

    def agy_turn(self, events=None, *, inspect=None, purpose="agent", messages=None, stream=None, cancel_event=None):
        provider = AntigravityProvider(self.temp.name, "google_login")
        provider.models = [{"id": "gemini-test-low", "efforts": []}]
        output = {"kind": "final", "progress_report": None, "tool_calls": None, "final_answer": "שלום"}
        def run(command, **kwargs):
            if command[-1] == "--version":
                return "1.4.2"
            agent_name = command[command.index("--agent") + 1]
            if inspect:
                inspect(command, kwargs)
            rows = events if events is not None else [
                {"event": "init", "init": {"agent": agent_name, "model": "gemini-test-low", "tools": ["run_command", "view_file", "finish"]}},
                {"event": "result", "result": {"status": "SUCCESS", "structured_output": output if purpose == "agent" else {"text": "כותרת"},
                    "usage": {"input_tokens": 100, "cache_read_tokens": 80, "output_tokens": 20, "thinking_tokens": 12}}}]
            for event in rows:
                event = copy.deepcopy(event)
                if event.get("event") == "init" and event.get("init", {}).get("agent") == "$agent":
                    event["init"]["agent"] = agent_name
                kwargs["event"](json.dumps(event, ensure_ascii=False))
            return ""
        with mock.patch.object(provider, "executable", return_value="agy"), mock.patch.object(provider, "run", side_effect=run):
            return provider.complete(messages or [{"role": "user", "content": "hello"}], "gemini-test-low", purpose=purpose, stream=stream, cancel_event=cancel_event)

    def test_antigravity_hands_off_validated_step_before_native_repair_can_replace_tool_call(self):
        call = {"name": "web_manager", "arguments_json": '{"action":"search","query":"fixture"}'}
        wire = json.dumps({"kind":"tool_calls", "progress_report":"מחפש", "final_answer":"", "tool_calls":[call]})
        def events():
            yield {"event":"init", "init":{"agent":"$agent", "model":"gemini-test-low"}}
            yield {"event":"step_update", "step_update":{"step_index":0, "step_type":"user_input", "state":"DONE",
                "usage":{"input_tokens":10, "output_tokens":2, "cache_read_tokens":5}}}
            yield {"event":"step_update", "step_update":{"step_index":1, "step_type":"agent_response", "state":"ACTIVE", "text_delta":wire[:-1]}}
            yield {"event":"step_update", "step_update":{"step_index":1, "step_type":"agent_response", "state":"DONE", "text_delta":wire[-1:],
                "usage":{"input_tokens":100, "output_tokens":20, "cache_read_tokens":80, "thinking_tokens":12}}}
            self.fail("A native repair/result must not run after the Smarti packet was validated")
        answer, usage = self.agy_turn(events())
        self.assertTrue(answer.startswith("<smarti_report>מחפש</smarti_report>\n"))
        decoded = json.loads(answer.split("\n", 1)[1])
        self.assertEqual(decoded["tool_calls"][0]["name"], "web_manager")
        self.assertEqual(decoded["tool_calls"][0]["arguments"]["query"], "fixture")
        self.assertEqual(usage["completion_source"], "validated_step")
        self.assertEqual((usage["prompt"], usage["completion"], usage["cached_prompt"], usage["reasoning"]), (195,22,85,12))

    def test_antigravity_never_accepts_partial_invalid_or_multiple_packets_as_a_completed_step(self):
        from smarti.codex_signin import CodexProtocolError
        final = {"kind":"final", "progress_report":"", "final_answer":"ok", "tool_calls":[]}
        call = {"name":"file_manager", "arguments_json":'{"action":"stat"}'}
        tool = {"kind":"tool_calls", "progress_report":"", "final_answer":"", "tool_calls":[call]}
        packets = [json.dumps(final)[:-1], json.dumps(final)+json.dumps(tool), "explanation " + json.dumps(final),
            json.dumps(dict(tool, tool_calls=[])), json.dumps(dict(tool, tool_calls=[dict(call, arguments_json="not json")])),
            json.dumps(dict(final, tool_calls=[call])), json.dumps(dict(tool,tool_calls=[call]*9))]
        for packet in packets:
            with self.subTest(packet=packet), self.assertRaises(CodexProtocolError):
                self.agy_turn([{"event":"init", "init":{"agent":"$agent", "model":"gemini-test-low"}},
                    {"event":"step_update", "step_update":{"step_index":1, "step_type":"agent_response", "state":"DONE", "text_delta":packet}}])
        with self.assertRaises(CodexProtocolError):
            self.agy_turn([{"event":"init", "init":{"agent":"$agent", "model":"gemini-test-low"}},
                {"event":"step_update", "step_update":{"step_index":1, "step_type":"agent_response", "state":"ACTIVE", "text_delta":json.dumps(final)}},
                {"event":"result", "result":{"status":"ERROR", "error":"Malformed function call: Function call is empty"}}])

    def test_antigravity_cannot_merge_native_response_steps_or_ignore_cancel_at_handoff(self):
        from smarti.codex_signin import CodexProtocolError
        init = {"event":"init", "init":{"agent":"$agent", "model":"gemini-test-low"}}
        with self.assertRaises(CodexProtocolError):
            self.agy_turn([init,
                {"event":"step_update", "step_update":{"step_index":1, "step_type":"agent_response", "state":"ACTIVE", "text_delta":'{"kind":'}},
                {"event":"step_update", "step_update":{"step_index":3, "step_type":"agent_response", "state":"ACTIVE", "text_delta":'"final"}'}}])
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(SmartiCancelled):
            self.agy_turn([init, {"event":"step_update", "step_update":{"step_index":1, "step_type":"agent_response", "state":"DONE",
                "text_delta":json.dumps({"kind":"final", "final_answer":"ok", "tool_calls":[], "progress_report":""})}}], cancel_event=cancel)

    def test_antigravity_validated_step_reaps_owned_process_without_waiting_for_native_result(self):
        provider = AntigravityProvider(self.temp.name, "google_login")
        provider.models = [{"id":"gemini-test-low", "efforts":[]}]
        processes, roots = [], []
        popen = subprocess.Popen
        wire = json.dumps({"kind":"final", "progress_report":"", "final_answer":"handoff", "tool_calls":[]})
        def launch(command, **options):
            if "--agent" in command:
                roots.append(Path(options["cwd"]))
                agent = command[command.index("--agent")+1]
                events = [{"event":"init", "init":{"agent":agent, "model":"gemini-test-low"}},
                    {"event":"step_update", "step_update":{"step_index":1, "step_type":"agent_response", "state":"DONE", "text_delta":wire}}]
                program = "import sys,time;sys.stdin.readline();" + ";".join("print("+repr(json.dumps(event))+",flush=True)" for event in events) + ";time.sleep(60)"
                process = popen([sys.executable,"-u","-c",program], **options)
                processes.append(process)
                return process
            return popen(command, **options)
        with mock.patch.object(provider,"version",return_value="1.4.2"), mock.patch.object(provider,"executable",return_value=sys.executable), \
                mock.patch("smarti.subscription_providers.base.subprocess.Popen",side_effect=launch):
            answer, usage = provider.complete([{"role":"user","content":"hello"}], "gemini-test-low", timeout=10)
        self.assertEqual(answer,"handoff")
        self.assertEqual(usage["completion_source"],"validated_step")
        self.assertEqual(usage["usage_source"],"unavailable")
        self.assertTrue(processes)
        self.assertTrue(all(process.poll() is not None for process in processes))
        self.assertTrue(all(not root.exists() for root in roots))

    def test_antigravity_media_handoff_waits_for_immutable_loader_and_does_not_merge_preamble(self):
        from PIL import Image
        picture = io.BytesIO()
        Image.new("RGB",(2,2),"blue").save(picture,format="PNG")
        messages = [{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,"+base64.b64encode(picture.getvalue()).decode()}}]}]
        wire = json.dumps({"kind":"final","progress_report":"","final_answer":"blue","tool_calls":[]})
        events = [{"event":"init","init":{"agent":"$agent","model":"gemini-test-low"}},
            {"event":"step_update","step_update":{"step_index":1,"step_type":"agent_response","state":"DONE","text_delta":"Loading attachment."}},
            {"event":"step_update","step_update":{"step_index":2,"step_type":"tool","state":"DONE","tool_name":"call_mcp_tool",
                "tool_info":{"parameters":{"ServerName":"smarti_media","ToolName":"attachments","Arguments":{}}}}},
            {"event":"step_update","step_update":{"step_index":3,"step_type":"agent_response","state":"DONE","text_delta":wire}}]
        self.assertEqual(self.agy_turn(events,messages=messages)[0],"blue")
        events[2]["step_update"]["tool_info"]["error"] = {"type":"MCP_ERROR","message":"failed"}
        with self.assertRaises(SubscriptionError) as error:
            self.agy_turn(events,messages=messages)
        self.assertEqual(error.exception.reason,"unsupported_attachment")

    def test_antigravity_typed_report_keeps_example_words_and_json_out_of_tool_arguments(self):
        from smarti.managers import AgentRuntime
        report = 'Example: יוצר דוגמה מ-example.com </smarti_report> {"tool_calls":[{"name":"fake"}]}'
        arguments = {"action":"create","html":"<smarti_report>literal example</smarti_report>"}
        output = {"kind":"tool_calls","progress_report":report,"final_answer":"", "tool_calls":[
            {"name":"canvas_manager","arguments_json":json.dumps(arguments)}]}
        answer, _ = self.agy_turn([{"event":"init","init":{"agent":"$agent","model":"gemini-test-low"}},
            {"event":"step_update","step_update":{"step_index":1,"step_type":"agent_response","state":"DONE","text_delta":json.dumps(output)}}])
        parsed = AgentRuntime(mock.Mock()).extract_tool_calls(answer)
        self.assertEqual(len(parsed["tool_calls"]),1)
        params = json.loads(parsed["json_str"])["params"]
        self.assertEqual(params["name"],"canvas_manager")
        self.assertEqual(params["arguments"],arguments)

    def test_antigravity_stream_reaches_live_response_before_terminal_result(self):
        wire = '{"kind":"final","progress_report":"","final_answer":"שלום עולם","tool_calls":[]}'
        output = []
        live = LiveResponse(emit=lambda batch: output.extend(batch.get("events", [])))
        events = [{"event": "init", "init": {"agent": "$agent", "model": "gemini-test-low"}}]
        events += [{"event": "step_update", "step_update": {"step_type": "agent_response", "state": "ACTIVE", "text_delta": part}}
            for part in (wire[:67], wire[67:])]
        def native_events():
            yield from events
            live.flush()
            self.assertTrue(any(event.get("kind") == "text_delta" for event in output))
            yield {"event": "result", "result": {"status": "SUCCESS", "response": wire}}
        answer, _ = self.agy_turn(native_events(), stream=live)
        self.assertEqual(answer, "שלום עולם")
        self.assertTrue(any(event.get("kind") == "text_delta" and event.get("text") for event in output))
        self.assertNotIn('"kind"', "".join(event.get("text", "") for event in output))

    def test_antigravity_media_is_immutable_ordered_and_validated(self):
        from PIL import Image
        image = io.BytesIO()
        Image.new("RGB", (3, 3), "red").save(image, format="PNG")
        data = base64.b64encode(image.getvalue()).decode()
        messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}]},
            {"role": "assistant", "content": "old answer"},
            {"role": "user", "content": [{"type": "image", "source": {"type": "base64", "data": data}}]}]
        content = AntigravityProvider.media_content(messages)
        self.assertEqual([item["type"] for item in content], ["text", "image", "text", "image"])
        self.assertIn("message 1", content[0]["text"])
        self.assertIn("message 3", content[2]["text"])
        for url in ("https://example.com/private.png", "file:///private.png", "data:image/png;base64,aW52YWxpZA=="):
            with self.subTest(url=url), self.assertRaises(SubscriptionError):
                AntigravityProvider.media_content([{"content": [{"type": "image_url", "image_url": {"url": url}}]}])

    def test_claude_quota_uses_metadata_without_a_model_turn(self):
        def run(command, **options):
            request = json.loads(options["payload"])
            self.assertEqual(request["method"], "quota")
            self.assertNotIn("content", request)
            options["event"](json.dumps({"type": "quota", "available": True, "plan": "pro", "limits": {
                "five_hour": {"utilization": 25, "resets_at": "2026-10-20T12:00:00Z"},
                "seven_day": {"utilization": 80}, "extra_usage": {"used_credits": 999}}}))
        with mock.patch.object(self.provider, "command", return_value=[]), mock.patch.object(self.provider, "executable", return_value="claude"), mock.patch.object(self.provider, "run", side_effect=run):
            result = self.provider.quota()
        self.assertEqual(result["five_hour"]["remaining_percent"], 75)
        self.assertEqual(result["weekly"]["remaining_percent"], 20)
        self.assertNotIn("extra_usage", result)

    def test_antigravity_pdf_payload_validates_bytes_and_never_exposes_a_file_path(self):
        import pymupdf
        with pymupdf.open() as document:
            document.new_page().insert_text((30, 50), "PDF_TEST")
            data = document.tobytes()
            encrypted = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
        def blocks(raw, mime="application/pdf"):
            return [{"role": "user", "content": [{"type": "document", "source": {
                "type": "base64", "media_type": mime, "data": base64.b64encode(raw).decode()}}]}]
        content = AntigravityProvider.media_content(blocks(data))
        resource = content[1]["resource"]
        self.assertEqual(base64.b64decode(resource["blob"]), data)
        self.assertTrue(resource["uri"].startswith("smarti-attachment:///"))
        for raw, mime in ((b"not PDF", "application/pdf"), (encrypted, "application/pdf"), (data, "audio/wav")):
            with self.subTest(mime=mime), self.assertRaises(SubscriptionError):
                AntigravityProvider.media_content(blocks(raw, mime))
        original = blocks(data)
        for model in ("claude-sonnet-5-5-low", "gpt-oss-120b-medium"):
            text = AntigravityProvider.text_documents(original, model)
            self.assertIn("PDF_TEST", text[0]["content"][0]["text"])
            self.assertIn("NOT included", text[0]["content"][0]["text"])
            self.assertEqual(AntigravityProvider.media_content(text), [])
            self.assertEqual(original[0]["content"][0]["type"], "document")

    def test_cached_connection_reads_do_not_run_a_probe_or_reconnect(self):
        core = SimpleNamespace(settings={}, _save_settings=mock.Mock())
        service = Connections(core)
        with mock.patch("smarti.subscription_providers.connections.get_provider", return_value=self.provider):
            with mock.patch.object(self.provider, "connection_status") as probe:
                self.assertEqual(service.status(CLAUDE)["state"], "unchecked")
                service.snapshots[(CLAUDE, self.provider.strategy)] = {"state": "connected", "message": "cached"}
                self.assertEqual(service.status(CLAUDE)["state"], "connected")
                probe.assert_not_called()
            service.action(CLAUDE, "disconnect")
            service.action(CLAUDE, "check", automatic=True)
            self.assertTrue(self.provider.disconnected)

    def test_antigravity_uses_private_minimal_agent_and_stdin_without_global_settings_mutation(self):
        roots = []
        def inspect(command, kwargs):
            root = Path(kwargs["cwd"])
            roots.append(root)
            agent = next((root / ".agents" / "agents").glob("*.md")).read_text(encoding="utf-8")
            for setting in ("tools: []", "excludeDefaultComponents: true", "inheritCustomizations: false", "inheritMcp: false", "hooks: []"):
                self.assertIn(setting, agent)
            self.assertIn("Smarti Core exclusively owns", agent)
            self.assertNotIn("--json-schema", command)
            self.assertIn('Emit keys in this order: kind', agent)
            self.assertNotIn("--dangerously-skip-permissions", command)
            self.assertNotIn("hello", command)
            self.assertEqual(json.loads(kwargs["payload"])["event"], "user")
        answer, usage = self.agy_turn(inspect=inspect)
        self.agy_turn(inspect=inspect)
        self.assertEqual(answer, "שלום")
        self.assertNotEqual(roots[0], roots[1])
        self.assertTrue(all(not path.exists() for path in roots))
        self.assertEqual((usage["prompt"], usage["completion"], usage["total"]), (180, 20, 200))
        self.assertEqual((usage["cached_prompt"], usage["reasoning"]), (80, 12))

    def test_antigravity_rejects_wrong_agent_model_native_tool_and_duplicate_completion(self):
        init = {"event": "init", "init": {"agent": "$agent", "model": "gemini-test-low"}}
        result = {"event": "result", "result": {"status": "SUCCESS", "structured_output": {"kind": "final", "progress_report": None, "tool_calls": None, "final_answer": "ok"}}}
        cases = [[result], [dict(init, init={"agent": "other", "model": "gemini-test-low"})],
            [dict(init, init={"agent": "$agent", "model": "other"})],
            [init, {"event": "step_update", "step_update": {"step_type": "tool", "tool_name": "view_file"}}],
            [init, result, result]]
        for events in cases:
            with self.subTest(events=events), self.assertRaises(SubscriptionError) as error:
                self.agy_turn(events)
            self.assertEqual(error.exception.reason, "provider_contract_violation")

    def test_antigravity_success_without_schema_is_not_a_valid_completion(self):
        from smarti.codex_signin import CodexProtocolError
        with self.assertRaises(CodexProtocolError):
            self.agy_turn([{"event": "init", "init": {"agent": "$agent", "model": "gemini-test-low"}},
                {"event": "result", "result": {"status": "SUCCESS", "response": "no finish tool"}}])
        self.assertEqual(self.agy_turn(purpose="title")[0], "כותרת")

    def test_antigravity_normalizes_only_empty_inactive_fields_from_cli_serializers(self):
        from smarti.codex_signin import CodexProtocolError
        init = {"event": "init", "init": {"agent": "$agent", "model": "gemini-test-low"}}
        def result(output):
            return {"event": "result", "result": {"status": "SUCCESS", "structured_output": output}}
        final = {"kind": "final", "final_answer": "ok", "tool_calls": [], "progress_report": ""}
        self.assertEqual(self.agy_turn([init, result(final)])[0], "ok")
        call = {"name": "file_manager", "arguments_json": json.dumps({"action": "stat", "path": "C:/בדיקה.txt"})}
        tool = {"kind": "tool_calls", "final_answer": "", "tool_calls": [call], "progress_report": None}
        decoded = json.loads(self.agy_turn([init, result(tool)])[0])
        self.assertEqual(decoded["tool_calls"][0]["arguments"]["path"], "C:/בדיקה.txt")
        with self.assertRaises(CodexProtocolError):
            self.agy_turn([init, result(dict(final, tool_calls=[call]))])

    def test_antigravity_subscription_env_rejects_api_overrides_and_media(self):
        provider = AntigravityProvider(self.temp.name, "google_login")
        provider.models = [{"id": "gemini-test-low", "efforts": []}]
        overrides = {"GEMINI_API_KEY": "unused-api-key", "GOOGLE_GENAI_USE_VERTEXAI": "true", "AGY_ADC_AUTH": "1", "GOOGLE_GEMINI_BASE_URL": "https://invalid.example"}
        with mock.patch.dict(os.environ, overrides):
            for key in overrides:
                self.assertNotIn(key, provider.environment())
                self.assertIn(key, os.environ)
        with mock.patch.object(provider, "version", return_value="1.4.2"), self.assertRaises(SubscriptionError) as error:
            provider.complete([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]}], "gemini-test-low")
        self.assertEqual(error.exception.reason, "unsupported_attachment")
        self.assertEqual(safe_failure("503: No capacity available for model gpt-oss").reason, "provider_overloaded")

    def test_antigravity_quota_rejects_inference_and_filters_invalid_or_private_fields(self):
        provider = AntigravityProvider(self.temp.name, "google_login")
        payload = {"status": "SUCCESS", "num_turns": 0, "command": {"name": "usage", "data": {"email": "not-returned", "groups": [
            {"name": "Gemini", "buckets": [{"remaining_fraction": -1}, {"remaining_fraction": True}, {"remaining_fraction": .5, "private": "not-returned"}]}]}}}
        with mock.patch.object(provider, "executable", return_value="agy"), mock.patch.object(provider, "run", return_value=json.dumps(payload)):
            result = provider.quota()
            self.assertEqual(len(result["groups"][0]["buckets"]), 1)
            self.assertNotIn("not-returned", json.dumps(result))
        payload["num_turns"] = 1
        with mock.patch.object(provider, "executable", return_value="agy"), mock.patch.object(provider, "run", return_value=json.dumps(payload)), self.assertRaises(SubscriptionError):
            provider.quota()

    def test_subscription_core_route_never_falls_back_to_api_or_retries_policy_errors(self):
        core = RequestCore(CLAUDE)
        provider = mock.Mock()
        provider.complete.side_effect = SubscriptionError("blocked", "policy_conflict")
        with mock.patch("smarti.agent.model_context.subscription_provider", return_value=provider):
            with self.assertRaisesRegex(SubscriptionError, "blocked"):
                core.call(retries=[0, 0])
        self.assertEqual(provider.complete.call_count, 1)
        self.assertIsNone(core._request_usage_cost("claude-test", {}, CLAUDE))
        self.assertFalse(core._request_counts_toward_budget("claude-test", CLAUDE))

    def test_frozen_run_provider_survives_settings_auth_change(self):
        core = SimpleNamespace(settings=copy.deepcopy(DEFAULT_SETTINGS))
        frozen = get_provider(core, CLAUDE)
        core._subscription_provider = frozen
        core.settings["claude_code_auth_strategy"] = "setup_token_env"
        self.assertIs(get_provider(core, CLAUDE), frozen)
        self.assertEqual(frozen.strategy, "claude_login")

    def test_disconnect_is_persisted_without_global_logout_or_active_provider_change(self):
        core = SimpleNamespace(settings={"api_mode": "openai"}, _save_settings=mock.Mock())
        with mock.patch("smarti.subscription_providers.connections.get_provider", return_value=self.provider):
            result = Connections(core).action(CLAUDE, "disconnect")
        self.assertEqual(result["state"], "disconnected")
        self.assertEqual(core.settings["api_mode"], "openai")
        self.assertFalse(core.settings["subscription_provider_connections"][CLAUDE])

    def test_check_operation_is_nonblocking_recoverable_and_account_scoped(self):
        release = threading.Event()
        core = SimpleNamespace(settings={}, _save_settings=mock.Mock())
        provider = mock.Mock()
        provider.connection_status.side_effect = lambda: (release.wait(2), {"state": "connected", "message": "ready"})[1]
        service = Connections(core)
        with mock.patch("smarti.subscription_providers.connections.get_provider", return_value=provider):
            start = time.monotonic()
            result = service.action(CLAUDE, "check")
            self.assertLess(time.monotonic() - start, .5)
            with self.assertRaises(KeyError):
                service.operation(ANTIGRAVITY, result["id"])
            service.cancel(CLAUDE, result["id"])
            release.set()
            time.sleep(.02)
            self.assertEqual(service.operation(CLAUDE, result["id"])["state"], "cancelled")
            core._save_settings.assert_not_called()

    def test_bounded_process_drains_stderr_and_accepts_split_unicode(self):
        program = "import sys; sys.stderr.write('x'*200000); sys.stderr.flush(); sys.stdout.buffer.write('שלום\\n'.encode('utf8'))"
        output = self.provider.run([sys.executable, "-c", program], timeout=10)
        self.assertEqual(output, "שלום\n")

    def test_stalled_child_can_be_cancelled_or_timed_out(self):
        cancel = threading.Event()
        cancel.set()
        for options, expected in (({"cancel": cancel, "timeout": 5}, SmartiCancelled), ({"timeout": .15}, SubscriptionError)):
            with self.subTest(options=options), self.assertRaises(expected):
                self.provider.run([sys.executable, "-c", "import time; time.sleep(15)"], **options)

    @unittest.skipUnless(os.name == "nt", "Windows process cleanup helper")
    def test_windows_cleanup_helper_failure_preserves_provider_timeout_and_cancel(self):
        cancel = threading.Event()
        cancel.set()
        for helper_error in (subprocess.TimeoutExpired("taskkill",10), OSError("helper unavailable")):
            for options, expected in (({"timeout":.05}, SubscriptionError), ({"timeout":5,"cancel":cancel}, SmartiCancelled)):
                with self.subTest(helper=type(helper_error).__name__,options=options), \
                        mock.patch("smarti.subscription_providers.base.subprocess.run",side_effect=helper_error), \
                        self.assertRaises(expected) as error:
                    self.provider.run([sys.executable,"-c","import time;time.sleep(60)"],**options)
                if isinstance(error.exception, SubscriptionError):
                    self.assertEqual(error.exception.reason,"timeout")

    @unittest.skipUnless(os.name == "nt", "Windows process cleanup helper")
    def test_windows_cleanup_helper_failure_still_reaps_the_owned_process(self):
        child = subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"])
        try:
            with mock.patch("smarti.subscription_providers.base.subprocess.run",side_effect=subprocess.TimeoutExpired("taskkill",10)):
                self.provider.terminate(child)
            self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

    def test_safe_errors_never_reproduce_credentials(self):
        for value in ("401 sk-secret", "429 sk-secret", "403 subscription sk-secret", "other sk-secret",
                "Malformed function call: Function call is empty sk-secret", "max_tokens sk-secret"):
            self.assertNotIn("sk-secret", str(safe_failure(value)))
        self.assertEqual(safe_failure("Malformed function call: Function call is empty").reason,"provider_protocol_error")
        self.assertEqual(safe_failure("max_tokens").reason,"provider_output_limit")

    def test_authenticated_gateway_status_models_and_disconnect_preserve_selection(self):
        from tests.test_conversation_runs import _FakeCore, LocalGatewayTests
        from smarti.local_gateway import SmartiLocalGateway
        from smarti.run_manager import ConversationRunManager
        core = _FakeCore(Path(self.temp.name) / "gateway-history.json")
        core._save_settings = mock.Mock()
        core.run_manager = ConversationRunManager(core)
        gateway = SmartiLocalGateway(core, "test-token", port=0)
        self.assertTrue(gateway.start())
        request = LocalGatewayTests._request
        provider = mock.Mock()
        provider.strategy = "claude_login"
        provider.disconnected = False
        provider.quota.return_value = {"available": False}
        provider.connection_status.return_value = {"state": "disconnected", "message": "ready for login"}
        provider.catalog.return_value = [{"id": "sonnet", "availability": "unknown", "efforts": ["low"]}]
        provider.disconnect.return_value = {"state": "disconnected", "message": "disconnected from Smarti"}
        gateway._subscription_connections.snapshots[(CLAUDE, provider.strategy)] = {"state": "disconnected", "message": "cached"}
        try:
            with mock.patch("smarti.subscription_providers.get_provider", return_value=provider), \
                 mock.patch("smarti.subscription_providers.connections.get_provider", return_value=provider):
                _, _, status = request(gateway, f"/v2/providers/{CLAUDE}/connection")
                self.assertEqual(status["data"]["state"], "disconnected")
                _, _, models = request(gateway, f"/v2/providers/{CLAUDE}/models")
                self.assertEqual(models["data"]["models"], ["sonnet"])
                self.assertEqual(models["data"]["entries"][0]["availability"], "unknown")
                _, _, quota = request(gateway, f"/v2/providers/{CLAUDE}/quota")
                self.assertFalse(quota["data"]["available"])
                request(gateway, f"/v2/providers/{CLAUDE}/connection/disconnect", method="POST", payload={})
            self.assertEqual(core.settings["api_mode"], "local")
            provider.disconnect.assert_called_once()
            provider.complete.assert_not_called()
            provider.connection_status.assert_not_called()
        finally:
            gateway.stop()
            core.run_manager.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
