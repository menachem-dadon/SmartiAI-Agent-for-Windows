"""File contents must reach the same agent request in direct and tool flows."""
import base64
import copy
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.attachments import attachment_from_path, normalize_attachment, normalize_attachments, read_attachment_bytes
from smarti.codex_signin import CodexConnectionStatus, CodexSignInProvider
from smarti.config import DEFAULT_SETTINGS, BUILTIN_TOOL_SCHEMAS, BUILTIN_DYNAMIC_TOOLS, FILE_MANAGER_ACTIONS, TOOL_ACTION_FIELDS
from smarti.core import SmartiCore
from smarti.local_gateway import ScopedAttachmentRegistry
from smarti.managers import AgentRuntime


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.core = SmartiCore.__new__(SmartiCore)
        self.core.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.core._ensure_secret_loaded = mock.Mock(return_value="test-key")
        self.core._save_settings = mock.Mock()
        self.core.mode = "gemini"
        self.core.conversation_attachments = []
        self.core._execution_context = threading.local()
        self.core._raise_if_cancelled = lambda: None
        self.core._ensure_cloud_upload_allowed = lambda path: (True, None)
        self.core._ensure_sandbox_path_allowed = lambda *args: (True, None)
        self.image = self.file("תמונה.png", base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6LxkAAAAASUVORK5CYII="))
        self.text = self.file("נתונים.csv", "name,value\nשלום,42\n".encode("utf-8"))

    def file(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return attachment_from_path(str(path))

    def archive(self, name, members):
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            for member, content in members.items():
                archive.writestr(member, content)
        return attachment_from_path(str(path))

    def parts(self, message):
        return message["parts" if self.core.mode == "gemini" else "content"]

    def test_direct_and_tool_mixed_files_reach_provider_content(self):
        for mode, key in [("gemini", "inlineData"), ("anthropic", "source"),
                          ("openai", "image_url"), ("openrouter", "image_url"),
                          ("local", "image_url"), ("openai_codex_signin", "image_url")]:
            with self.subTest(mode=mode):
                self.core.mode = mode
                direct = self.core._build_user_message_with_attachments("Describe", [self.image, self.text])
                self.assertEqual(sum(key in block for block in self.parts(direct)), 1)
                self.assertIn("שלום,42", json.dumps(direct, ensure_ascii=False))
                result, error = self.core.execute_tool("file_manager", {"action": "attach", "paths": [self.image["path"], self.text["path"]]})
                self.assertIsNone(error)
                messages = []
                self.core._append_tool_results_feedback(messages, "tool call", [{"action": "file_manager", "feedback": result}])
                self.assertEqual(len(messages), 2)
                self.assertEqual(sum(key in block for block in self.parts(messages[-1])), 1)
                self.assertIn("שלום,42", json.dumps(messages[-1], ensure_ascii=False))
                self.assertNotIn("ATTACHMENT_JSON", json.dumps(messages[-1]))
                self.assertEqual(len(self.core.conversation_attachments), 2)

    def test_multi_result_feedback_keeps_media_and_normal_tool_results(self):
        for mode in ("gemini", "anthropic", "openai", "openai_codex_signin"):
            self.core.mode = mode
            messages = []
            self.core._append_tool_results_feedback(messages, "calls", [
                {"action": "file_manager", "feedback": self.core._attachment_tool_payload(self.image["path"])},
                {"action": "file_manager", "feedback": self.core._attachment_tool_payload(self.text["path"])},
                {"action": "search_tools", "feedback": "ordinary-result"},
                {"action": "screen_manager", "feedback": "IMAGE_BASE64:image/png:YWJj"},
            ])
            self.assertEqual(len(messages), 2)
            content = self.parts(messages[-1])
            self.assertEqual(sum("inlineData" in b or b.get("type") in {"image", "image_url"} for b in content), 2)
            self.assertIn("ordinary-result", json.dumps(content))
            self.assertNotIn("ATTACHMENT_JSON", json.dumps(content))
            self.assertIn("שלום,42", json.dumps(content, ensure_ascii=False))

    def test_partial_failure_and_duplicate_paths_keep_valid_files(self):
        self.core._ensure_cloud_upload_allowed = lambda p: (False, "ERROR: denied") if p == self.text["path"] else (True, None)
        result = self.core.attach_local_file_tool(self.image["path"], paths=[self.image["path"], self.text["path"], str(self.root / "missing")])
        payload = json.loads(result.split(":", 1)[1])
        self.assertEqual(len(payload["attachments"]), 1)
        self.assertEqual(len(payload["errors"]), 2)
        messages = []
        self.core._append_tool_feedback(messages, "call", "file_manager", result)
        self.assertIn("denied", json.dumps(messages))
        self.assertIn("inlineData", json.dumps(messages))

    def test_invalid_payloads_and_metadata_do_not_fabricate_attachments(self):
        self.assertIsNone(normalize_attachment({}))
        self.assertEqual(len(normalize_attachments(self.image)), 1)
        self.assertEqual(len(normalize_attachments(self.image["path"])), 1)
        self.assertEqual(normalize_attachment({**self.image, "size": "bad"})["size"], 0)
        for payload in ("{}", "null", "[]", "invalid"):
            messages = []
            self.core._append_attachment_tool_feedback(messages, "call", "file_manager", payload)
            self.assertIn("ERROR:", json.dumps(messages))
            self.assertNotIn("inlineData", json.dumps(messages))

    def test_missing_unreadable_empty_oversize_and_unknown_files_are_per_file(self):
        empty = self.file("empty.txt", b"")
        unknown = self.file("unknown.bin", b"\x00\xff")
        missing = {**self.image, "path": str(self.root / "missing.png")}
        message = self.core._build_user_message_with_attachments("inspect", [missing, empty, unknown, self.text])
        serialized = json.dumps(message)
        self.assertIn("empty file", serialized)
        self.assertIn("NOT included", serialized)
        self.assertIn("File not found", serialized)
        self.assertIn("name,value", serialized)
        with mock.patch("builtins.open", side_effect=PermissionError("locked")):
            self.assertIn("Cannot read", read_attachment_bytes(self.image)[1])
        self.core.settings["attachment_inline_max_mb"] = 0.000001
        self.assertIn("too large", json.dumps(self.core._build_user_message_with_attachments("inspect", [self.image])))

    def test_text_encodings_and_truncation_are_explicit(self):
        item = self.file("utf16.txt", ("שלום\n" * 1000).encode("utf-16"))
        self.core.settings["attachment_text_excerpt_chars"] = 1000
        value = json.dumps(self.core._build_user_message_with_attachments("read", [item]), ensure_ascii=False)
        self.assertIn("שלום", value)
        self.assertIn("truncated", value)
        self.assertNotIn("\ufffd", value)

    def test_office_text_tables_slides_and_archives_enter_context(self):
        docx = self.archive("notes.docx", {"word/document.xml": '<document><p>Paragraph</p><tbl><tr><tc><p>TableCell</p></tc></tr></tbl></document>'})
        pptx = self.archive("slides.pptx", {"ppt/slides/slide1.xml": '<slide><p>SlideText</p></slide>'})
        xlsx = self.archive("sheet.xlsx", {
            "xl/sharedStrings.xml": '<sst><si><t>Heading</t></si></sst>',
            "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="B1"><f>2+3</f><v>5</v></c></row></sheetData></worksheet>'})
        archive = self.archive("bundle.zip", {"member.txt": "not extracted"})
        for mode in ("gemini", "anthropic", "openai", "openai_codex_signin"):
            self.core.mode = mode
            value = json.dumps(self.core._build_user_message_with_attachments("read", [docx, xlsx, pptx, archive]))
            for expected in ("Paragraph", "TableCell", "SlideText", "Heading", "B1=5", "formula: 2+3", "Archive inventory only", "member.txt"):
                self.assertIn(expected, value)

    def test_gemini_pdf_audio_video_and_openai_pdf_are_native(self):
        files = [self.file("doc.pdf", b"%PDF-1.4"), self.file("audio.wav", b"RIFF"), self.file("video.mp4", b"video")]
        message = self.core._build_user_message_with_attachments("analyze", files)
        self.assertEqual([p["inlineData"]["mimeType"] for p in self.parts(message) if "inlineData" in p], ["application/pdf", "audio/wav", "video/mp4"])
        self.core.mode = "openai"
        message = self.core._build_user_message_with_attachments("analyze", files)
        self.assertEqual(sum(p.get("type") == "file" for p in self.parts(message)), 1)
        self.assertIn("NOT included", json.dumps(message))

    def test_corrupt_office_and_xml_entities_are_isolated(self):
        broken = self.file("broken.docx", b"not a zip")
        entities = self.archive("entities.docx", {"word/document.xml": '<!DOCTYPE doc [<!ENTITY a "x">]><doc><p>&a;</p></doc>'})
        value = json.dumps(self.core._build_user_message_with_attachments("read", [broken, entities, self.text]))
        self.assertIn("Cannot extract", value)
        self.assertIn("entities are not supported", value)
        self.assertIn("name,value", value)

    def test_ocr_is_removed_and_stale_calls_cannot_execute_it(self):
        self.assertNotIn("extract_image_text", BUILTIN_TOOL_SCHEMAS)
        self.assertNotIn("extract_image_text", BUILTIN_DYNAMIC_TOOLS)
        self.assertNotIn("extract_image_text", FILE_MANAGER_ACTIONS)
        self.assertNotIn("extract_image_text", TOOL_ACTION_FIELDS["file_manager"])
        self.assertNotIn("OCR", BUILTIN_TOOL_SCHEMAS["file_manager"]["description"])
        self.assertFalse(hasattr(self.core, "extract_image_text_tool"))
        self.core._run_cancelable_subprocess = mock.Mock(side_effect=AssertionError("No OCR process may run"))
        self.core._handle_api_request_with_retry = mock.Mock(side_effect=AssertionError("No separate AI task may run"))
        for action, arguments in [
            ("extract_image_text", {"path": self.image["path"]}),
            ("file_manager", {"action": "extract_image_text", "path": self.image["path"]}),
        ]:
            result, _ = self.core.execute_tool(action, arguments)
            self.assertTrue(result.startswith("ERROR:"))
            self.assertIn("action=attach", result)
        self.core._run_cancelable_subprocess.assert_not_called()
        self.core._handle_api_request_with_retry.assert_not_called()

    def test_codex_sends_multiple_ephemeral_images_and_cleans_up_on_failure(self):
        self.core.mode = "openai_codex_signin"
        messages = [self.core._build_user_message_with_attachments("inspect", [self.image, self.text]),
                    self.core._build_user_message_with_attachments("inspect again", [self.image])]
        provider = CodexSignInProvider(self.temp.name, executable="codex-test")
        original = copy.deepcopy(messages)
        staged = []

        def run(args, **kwargs):
            paths = [Path(args[index + 1]) for index, arg in enumerate(args) if arg == "--image"]
            self.assertEqual(len(paths), 2)
            self.assertTrue(all(p.read_bytes() == Path(self.image["path"]).read_bytes() for p in paths))
            self.assertIn("Image 2", kwargs["input_text"])
            self.assertIn("שלום,42", kwargs["input_text"])
            self.assertNotIn("base64", kwargs["input_text"])
            staged.extend(paths)
            raise RuntimeError("CLI failed")

        with mock.patch.object(provider, "connection_status", return_value=CodexConnectionStatus("connected", "ok")), mock.patch.object(provider, "_run", side_effect=run):
            with self.assertRaisesRegex(RuntimeError, "CLI failed"):
                provider.complete(messages)
        self.assertTrue(all(not p.exists() for p in staged))
        self.assertEqual(messages, original)

    def test_scoped_direct_handles_preserve_multiple_file_types(self):
        registry = ScopedAttachmentRegistry()
        handles = [registry.register(item["path"], session_id="chat-a")["handle"] for item in (self.image, self.text)]
        items = registry.resolve_many(handles, session_id="chat-a")
        self.assertEqual([item["kind"] for item in items], ["image", "document"])
        self.assertEqual([item["path"] for item in items], [self.image["path"], self.text["path"]])
        with self.assertRaises(ValueError):
            registry.resolve_many(handles, session_id="chat-b")

    def test_real_provider_request_adapters_preserve_direct_and_tool_content(self):
        from tests.test_context_efficiency import _request_core, _JsonResponse
        for mode in ("gemini", "anthropic", "openai"):
            with self.subTest(mode=mode):
                core = _request_core(mode)
                core.conversation_attachments = []
                captured = []
                if mode == "openai":
                    def create(**kwargs):
                        captured.append(copy.deepcopy(kwargs))
                        return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content="analysis", tool_calls=[]))])
                    core._openai_compatible_client_for_request = lambda mode: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
                else:
                    def post(url, json=None, **kwargs):
                        captured.append(copy.deepcopy(json))
                        return _JsonResponse({"candidates": [{"content": {"parts": [{"text": "analysis"}]}}]} if mode == "gemini" else {"content": [{"type": "text", "text": "analysis"}], "usage": {}})
                    core._request_post = post
                messages = [core._build_user_message_with_attachments("Describe the files", [self.image, self.text])]
                for stage in ("direct", "after tool"):
                    if stage == "after tool":
                        core._append_tool_feedback(messages, "attach call", "file_manager", core._attachment_tool_payload(self.image["path"]))
                    answer, _ = core._handle_api_request_with_retry("test-model", messages, retry_wait_times=[], request_options={"native_tools": False})
                    self.assertEqual(answer, "analysis")
                    payload = captured[-1]
                    submitted = payload["contents" if mode == "gemini" else "messages"]
                    self.assertIn(base64.b64encode(Path(self.image["path"]).read_bytes()).decode("ascii"), json.dumps(submitted))
                    self.assertIn("שלום,42", json.dumps(submitted, ensure_ascii=False))
                    self.assertNotIn("ATTACHMENT_JSON", json.dumps(submitted))

    def test_bmp_is_converted_losslessly_for_vision(self):
        from PIL import Image
        data = io.BytesIO()
        Image.new("RGB", (2, 2), "red").save(data, format="BMP")
        item = self.file("image.bmp", data.getvalue())
        for mode in ("gemini", "anthropic", "openai", "openai_codex_signin"):
            self.core.mode = mode
            message = self.core._build_user_message_with_attachments("describe", [item])
            serialized = json.dumps(message)
            self.assertIn("image/png", serialized)
            self.assertNotIn("Cannot decode", serialized)

    def test_agent_loop_analyzes_direct_content_then_continues_after_multi_attach(self):
        core = self.core
        core.system_prompt = "Inspect supplied content."
        core.agent_runtime = AgentRuntime(core)
        core.gemini_history = []
        core.status_callback = core.step_callback = core.print_callback = None
        core.settings.update({"max_agent_iterations": 4, "prevent_sleep_during_active_task": False})
        core._conversation_lock = lambda session_id: threading.RLock()
        core._load_system_prompt = lambda *args, **kwargs: core.system_prompt
        core._save_active_task_checkpoint = mock.Mock()
        core._clear_task_checkpoint = mock.Mock()
        core._load_task_checkpoint = lambda: None
        core._log_usage = mock.Mock()
        core._record_context_token_usage = mock.Mock()
        core._compact_current_messages_if_needed = lambda *args, **kwargs: False
        core._compact_conversation_history = mock.Mock()
        core._record_tool_observation = mock.Mock()
        snapshots = []
        core._handle_api_request_with_retry = mock.Mock(return_value=("Direct image answer.", {}))
        with mock.patch.object(core, "execute_tool", side_effect=AssertionError("Direct image analysis needs no tool")):
            direct = core.send_message("Read the Hebrew text in this image", attachments=[self.image], persist_turn=False)
        self.assertEqual(direct, "Direct image answer.")
        core._handle_api_request_with_retry.assert_called_once()
        self.assertIn("inlineData", json.dumps(core._handle_api_request_with_retry.call_args.args[1]))
        core.gemini_history = []
        tool = {"method": "tools/call", "params": {"name": "file_manager", "arguments": {
            "action": "attach", "paths": [self.image["path"], self.text["path"]]}}}

        def request(model, messages):
            snapshots.append(copy.deepcopy(messages))
            return (json.dumps(tool) if len(snapshots) == 1 else "The supplied files were analyzed."), {}

        core._handle_api_request_with_retry = request
        result = core.send_message("Analyze the files", attachments=[self.image], persist_turn=False)
        self.assertEqual(result, "The supplied files were analyzed.")
        self.assertEqual(len(snapshots), 2)
        self.assertIn("inlineData", json.dumps(snapshots[0]))
        self.assertIn("שלום,42", json.dumps(snapshots[1], ensure_ascii=False))
        self.assertNotIn("ATTACHMENT_JSON", json.dumps(snapshots[1]))


if __name__ == "__main__":
    unittest.main()
