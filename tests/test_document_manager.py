import json
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from smarti.agent.document_tools import (
    DocumentToolsMixin,
    _WordComSession,
    _friendly_enum,
    _literal_match_spans,
    _WORD_CHART_TYPES,
)
from smarti.agent.extensions import ExtensionsMixin
from smarti.agent.tool_dispatch import ToolDispatchMixin
from smarti.agent.tool_calls import ToolCallMixin
from smarti.config import (
    BUILTIN_TOOL_SCHEMAS,
    DOCUMENT_MANAGER_ACTION_GUIDANCE,
    PUBLIC_BUILTIN_TOOLS,
    TOOL_ACTION_FIELDS,
    TOOL_CATEGORIES,
)


class _DocumentHarness(DocumentToolsMixin):
    def _sandbox_enabled(self):
        return False

    def _sandbox_root(self):
        return os.getcwd()

    def _ensure_sandbox_path_allowed(self, path, mode):
        return True, None

    def _ensure_capabilities_allowed(self, *args, **kwargs):
        return True, None

    def _ensure_cloud_upload_allowed(self, *args, **kwargs):
        return True, None


class _ExtensionHarness(ExtensionsMixin):
    pass


class DocumentManagerTests(unittest.TestCase):
    def setUp(self):
        self.tool = _DocumentHarness()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _path(self, name):
        return os.path.join(self.temp_dir.name, name)

    def _basic_plan(self):
        return {
            "metadata": {"title": "דו״ח בדיקה", "author": "Smarti", "language": "he-IL"},
            "defaults": {"font": "Arial", "font_size_pt": 11},
            "page": {
                "size": "A4",
                "orientation": "portrait",
                "margins_cm": {"top": 2.5, "bottom": 2.5, "left": 2.0, "right": 2.0},
            },
            "header": {"text": "כותרת עליונה"},
            "footer": {"text": "עמוד", "page_number": True, "alignment": "center"},
            "blocks": [
                {"type": "title", "text": "דו״ח בדיקה"},
                {"type": "heading", "level": 1, "text": "מבוא"},
                {
                    "type": "paragraph",
                    "runs": [
                        {"text": "שלום בעברית "},
                        {"text": "English", "rtl": False, "italic": True},
                    ],
                },
                {
                    "type": "table",
                    "header_rows": 1,
                    "column_widths_cm": [4, 10],
                    "rows": [["נושא", "פירוט"], ["בדיקה", "תוכן בעברית"]],
                },
                {"type": "toc"},
                {
                    "type": "content_control", "control_type": "checkbox",
                    "title": "אישור", "tag": "approved", "checked": True,
                },
            ],
        }

    def test_python_create_is_hebrew_rtl_and_structured(self):
        path = self._path("hebrew.docx")
        result = self.tool._python_create_document(path, "", self._basic_plan())
        self.assertEqual(result["status"], "created")
        self.assertTrue(os.path.isfile(path))

        inspected = self.tool._python_inspect_document(path, {"include_text": True})
        self.assertEqual(inspected["table_count"], 1)
        self.assertEqual(inspected["section_count"], 1)
        self.assertGreater(inspected["rtl_paragraph_count"], 0)
        self.assertGreater(inspected["field_count"], 0)
        self.assertEqual(inspected["paragraphs"][0]["text"], "דו״ח בדיקה")

        api = self.tool._python_imports()
        document = api["docx"].Document(path)
        self.assertIsNotNone(document.sections[0]._sectPr.find(api["qn"]("w:bidi")))

        with zipfile.ZipFile(path, "r") as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
            styles_xml = archive.read("word/styles.xml").decode("utf-8")
        self.assertIn("w:bidi", document_xml)
        # Word mirrors physical left/right justification for bidi paragraphs.
        # The independent engine therefore emits w:jc=left for visual right.
        self.assertIn('w:jc w:val="left"', document_xml)
        self.assertIn("he-IL", document_xml)
        self.assertIn("Arial", styles_xml)
        self.assertIn("w:tblHeader", document_xml)
        self.assertIn("w:sdt", document_xml)
        self.assertIn("w14:checkbox", document_xml)
        self.assertIn("TOC1", styles_xml)
        self.assertIn("w:tabs", styles_xml)

    def test_public_edit_creates_backup_and_preserves_output(self):
        path = self._path("editable.docx")
        created = json.loads(self.tool.document_manager_tool({
            "action": "create",
            "engine": "python",
            "output_path": path,
            "document": self._basic_plan(),
        }))
        self.assertEqual(created["status"], "created")

        edited = json.loads(self.tool.document_manager_tool({
            "action": "edit",
            "engine": "python",
            "path": path,
            "operations": [
                {"op": "replace_text", "find": "שלום", "replace": "ברוכים הבאים"},
                {"op": "append_blocks", "blocks": [{"type": "heading", "level": 1, "text": "נספח"}]},
            ],
        }))
        self.assertEqual(edited["status"], "edited")
        self.assertTrue(os.path.isfile(edited["backup_path"]))
        self.assertTrue(os.path.isfile(path))
        inspected = self.tool._python_inspect_document(path, {"include_text": True})
        text = "\n".join(item["text"] for item in inspected["paragraphs"])
        self.assertIn("ברוכים הבאים", text)
        self.assertIn("נספח", text)

    def test_python_lists_merges_and_cross_run_replace_preserve_structure(self):
        api = self.tool._python_imports()
        document = api["docx"].Document()
        paragraph = document.add_paragraph()
        first = paragraph.add_run("alpha ")
        first.bold = True
        second = paragraph.add_run("beta")
        second.italic = True
        self.assertEqual(self.tool._python_replace_text(document, "ha be", "X"), 1)
        self.assertEqual(paragraph.text, "alpXta")
        self.assertTrue(first.bold)
        self.assertTrue(second.italic)

        path = self._path("list-and-merge.docx")
        result = self.tool._python_create_document(path, "", {
            "blocks": [
                {"type": "list", "ordered": True, "items": ["ראשון", {"text": "שני", "level": 1}]},
                {
                    "type": "table",
                    "rows": [["כותרת", ""], ["א", "ב"]],
                    "merges": [{"from_row": 0, "from_column": 0, "to_row": 0, "to_column": 1}],
                },
            ],
        })
        self.assertEqual(result["status"], "created")
        created = api["docx"].Document(path)
        self.assertEqual(created.paragraphs[0].style.name, "List Number")
        self.assertEqual(created.tables[0].cell(0, 0)._tc, created.tables[0].cell(0, 1)._tc)

    def test_long_literal_matching_and_com_range_replacement_bypass_word_find(self):
        old = "Alpha " * 60
        new = "Beta " * 80
        text = f"prefix {old} middle {old} suffix"
        self.assertEqual(len(_literal_match_spans(text, old)), 2)
        self.assertEqual(_literal_match_spans("cat scatter cat", "cat", whole_word=True), [(0, 3), (12, 15)])

        class MutableRange:
            def __init__(self, storage, start, end):
                self.storage = storage
                self.Start = start
                self.End = end

            @property
            def Duplicate(self):
                return MutableRange(self.storage, self.Start, self.End)

            @property
            def Text(self):
                return self.storage["text"][self.Start:self.End]

            @Text.setter
            def Text(self, value):
                current = self.storage["text"]
                self.storage["text"] = current[:self.Start] + value + current[self.End:]
                self.End = self.Start + len(value)

            def SetRange(self, start, end):
                self.Start, self.End = start, end

        storage = {"text": text}
        target = MutableRange(storage, 0, len(text))
        count = self.tool._com_replace_long_literal(target, old, new)
        self.assertEqual(count, 2)
        self.assertEqual(storage["text"], f"prefix {new} middle {new} suffix")

    def test_python_edit_accepts_model_friendly_aliases_and_positioned_blocks(self):
        api = self.tool._python_imports()
        source = self._path("source.docx")
        output = self._path("edited.docx")
        document = api["docx"].Document()
        document.add_paragraph("ראשון")
        document.add_paragraph("אחרון")
        document.save(source)

        result = self.tool._python_edit_document(source, output, [
            {
                "op": "set_page_layout",
                "layout": {"page_size": "A4", "mirror_margins": True},
            },
            {
                "op": "define_style",
                "name": "גוף מותאם",
                "format": {"style_type": "paragraph", "font_name": "Arial", "font_size": 13, "bold": True},
            },
            {
                "op": "format_paragraph",
                "selector": {"paragraph_index": 0},
                "format": {"style": "גוף מותאם", "space_after": 8},
            },
            {
                "op": "insert_blocks",
                "selector": {"paragraph_index": 1},
                "position": "before",
                "blocks": [{"type": "paragraph", "text": "באמצע"}],
            },
            {
                "op": "set_header",
                "content": {"text": "כותרת", "font_name": "Arial", "font_size": 9},
            },
        ])

        self.assertEqual(result["operation_counts"]["insert_blocks"], 1)
        edited = api["docx"].Document(output)
        self.assertEqual([paragraph.text for paragraph in edited.paragraphs], ["ראשון", "באמצע", "אחרון"])
        self.assertEqual(edited.paragraphs[0].style.name, "גוף מותאם")
        self.assertEqual(edited.styles["גוף מותאם"].font.size.pt, 13)
        self.assertEqual(edited.sections[0].header.paragraphs[0].text, "כותרת")
        self.assertIsNotNone(edited.settings.element.find(api["qn"]("w:mirrorMargins")))

    def test_auto_engine_uses_capability_map_instead_of_forcing_com(self):
        with mock.patch.object(self.tool, "_word_com_available", return_value=True):
            portable = self.tool._document_choose_engine("edit", {
                "path": "sample.docx",
                "operations": [{"op": "insert_blocks", "blocks": [{"type": "paragraph", "text": "x"}]}],
            })
            word_only = self.tool._document_choose_engine("edit", {
                "path": "sample.docx",
                "operations": [{"op": "format_range", "selector": {"start": 0, "end": 1}}],
            })
        self.assertEqual(portable, "python")
        self.assertEqual(word_only, "com")

    def test_internal_bookmark_hyperlink_and_friendly_fields(self):
        path = self._path("links-and-fields.docx")
        self.tool._python_create_document(path, "", {
            "blocks": [
                {"type": "bookmark", "name": "summary_bookmark", "text": "סיכום"},
                {"type": "hyperlink", "text": "לסיכום", "anchor": "summary_bookmark"},
                {"type": "field", "field_type": "DATE", "format": "dd/MM/yyyy", "text": "05/08/2026"},
                {"type": "field", "field_type": "FILENAME", "text": "document.docx"},
            ],
        })
        with zipfile.ZipFile(path, "r") as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn('w:name="summary_bookmark"', document_xml)
        self.assertIn('w:anchor="summary_bookmark"', document_xml)
        self.assertIn('DATE \\@ "dd/MM/yyyy"', document_xml)
        self.assertIn("FILENAME", document_xml)

    def test_friendly_com_enums_validate_before_word_launch(self):
        self.assertEqual(_friendly_enum("column_clustered", _WORD_CHART_TYPES, "chart_type", 51), 51)
        self.tool._document_validate_blocks([
            {"type": "content_control", "control_type": "checkbox"},
            {
                "type": "chart", "chart_type": "column_clustered",
                "categories": ["א", "ב"], "series": [{"name": "נתונים", "values": [1, 2]}],
            },
        ], "com")
        with self.assertRaisesRegex(ValueError, "Unsupported chart_type"):
            self.tool._document_validate_blocks([{"type": "chart", "chart_type": "guess"}], "com")

    def test_post_action_failure_keeps_created_document(self):
        path = self._path("created-with-render-warning.docx")
        with mock.patch.object(self.tool, "_document_render", side_effect=RuntimeError("render unavailable")):
            result = self.tool._document_create({
                "engine": "python",
                "output_path": path,
                "document": {"blocks": [{"type": "paragraph", "text": "נשמר"}]},
                "render_after": True,
            }, "python")
        self.assertEqual(result["status"], "created_with_warnings")
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(result["post_action_errors"][0]["stage"], "render")
        self.assertIn("instead of recreating", result["warnings"][0])

    def test_word_session_layout_printer_is_instance_local(self):
        session = _WordComSession()
        client = mock.MagicMock()
        app = mock.MagicMock()
        app.ActivePrinter = "Microsoft Print to PDF"
        client.DispatchEx.return_value = app
        ole = app.Dialogs.return_value._oleobj_
        ole.GetIDsOfNames.side_effect = {
            "Printer": 1, "DoNotSetAsSysDefault": 4, "Execute": 32001,
        }.get
        with (
            mock.patch(
                "smarti.agent.document_tools._safe_layout_printer",
                return_value="Microsoft Print to PDF on PORTPROMPT:",
            ),
            mock.patch("win32print.GetDefaultPrinter", side_effect=["Network printer", "Network printer"]),
            mock.patch("win32print.SetDefaultPrinter") as set_default,
        ):
            result = session._launch_word_with_layout_printer(client)
            session.app = result
            session._configure_layout_printer()
        self.assertTrue(session.printer_isolated)
        self.assertIs(result, app)
        self.assertEqual(ole.Invoke.call_count, 3)
        set_default.assert_not_called()

    def test_schema_catalog_and_skill_expose_workflow(self):
        schema = BUILTIN_TOOL_SCHEMAS["document_manager"]["inputSchema"]
        self.assertEqual(schema["properties"]["action"]["enum"], (
            "doctor", "create", "edit", "inspect", "render", "visual_qa", "export", "compare",
        ))
        self.assertIn("document_manager", PUBLIC_BUILTIN_TOOLS)
        self.assertEqual(TOOL_CATEGORIES["document_manager"], "documents")
        self.assertIn("advanced_com", DOCUMENT_MANAGER_ACTION_GUIDANCE["edit"])
        self.assertIn("255-character", DOCUMENT_MANAGER_ACTION_GUIDANCE["edit"])
        self.assertIn("insert_blocks", schema["properties"]["operations"]["description"])
        self.assertIn("column_clustered", DOCUMENT_MANAGER_ACTION_GUIDANCE["create"])
        block_schema = schema["properties"]["document"]["properties"]["blocks"]["items"]
        self.assertIn("checkbox", block_schema["properties"]["control_type"]["description"])
        self.assertIn("render_after", TOOL_ACTION_FIELDS["document_manager"]["create"])
        self.assertEqual(TOOL_ACTION_FIELDS["document_manager"]["visual_qa"], ("path",))

        skill = _ExtensionHarness()._builtin_skill_specs()["document_authoring"]
        self.assertEqual(skill["handler"], "instructions")
        self.assertIn("Visual QA loop", skill["instructions"])
        self.assertIn("document_manager visual_qa", skill["instructions"])
        self.assertIn("screen_manager remains fully available", skill["instructions"])
        self.assertIn("not a prohibition", skill["instructions"])
        self.assertIn("he-IL", skill["instructions"])
        self.assertIn("UI automation", skill["instructions"])
        self.assertIn("Prefer engine=auto", skill["instructions"])
        self.assertIn("Long text replacement alone", skill["instructions"])

    def test_com_escape_hatch_blocks_dangerous_members(self):
        self.tool._validate_com_member("PageSetup")
        with self.assertRaises(PermissionError):
            self.tool._validate_com_member("VBProject")
        with self.assertRaises(PermissionError):
            self.tool._validate_com_member("PrintOut")
        with self.assertRaises(ValueError):
            self.tool._validate_com_member("Bad.Name")
        with self.assertRaises(PermissionError):
            self.tool._validate_com_member("Save")
        with self.assertRaises(PermissionError):
            self.tool._validate_com_member("WordBasic")

    def test_mutating_document_actions_are_not_parallel_safe(self):
        harness = ToolCallMixin()
        self.assertTrue(harness._tool_is_mutating_or_control("document_manager", {"action": "create"}))
        self.assertTrue(harness._tool_is_mutating_or_control("document_manager", {"action": "export"}))
        self.assertFalse(harness._tool_is_mutating_or_control("document_manager", {"action": "doctor"}))
        self.assertFalse(harness._tool_is_mutating_or_control("document_manager", {"action": "inspect"}))

    def test_sensitive_document_arguments_are_redacted_from_audit_preview(self):
        redacted = ToolDispatchMixin._redact_tool_args_for_audit({
            "path": "report.docx",
            "password": "secret-value",
            "operations": [{"op": "protect", "password": "nested-secret"}],
        })
        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["operations"][0]["password"], "[REDACTED]")
        self.assertEqual(redacted["path"], "report.docx")

    @unittest.skipUnless(__import__("importlib").util.find_spec("fitz"), "PyMuPDF is not installed in this test environment")
    def test_pdf_render_produces_one_png_per_page(self):
        import fitz

        pdf_path = self._path("source.pdf")
        pdf = fitz.open()
        for text in ("עמוד ראשון", "עמוד שני"):
            page = pdf.new_page()
            page.insert_text((72, 72), text)
        pdf.save(pdf_path)
        pdf.close()

        result = self.tool._document_render({
            "path": pdf_path,
            "output_dir": self._path("rendered"),
            "dpi": 96,
            "page_limit": 10,
        }, "python")
        self.assertEqual(result["page_count"], 2)
        self.assertTrue(all(os.path.isfile(page["path"]) for page in result["pages"]))
        self.assertTrue(result["visual_qa_required"])
        self.assertIn("document_manager action=visual_qa", result["next_step"])

    def test_visual_qa_returns_rendered_page_to_the_model(self):
        page_path = self._path("page-001.png")
        with open(page_path, "wb") as image_file:
            image_file.write(b"\x89PNG\r\n\x1a\nvisual-qa-test")

        result = self.tool.document_manager_tool({"action": "visual_qa", "path": page_path})

        self.assertTrue(result.startswith("IMAGE_BASE64:image/png:"))


if __name__ == "__main__":
    unittest.main()
