import json
import os
import tempfile
import unittest
import zipfile

from smarti.agent.document_tools import DocumentToolsMixin
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
                {"type": "content_control", "title": "שדה", "tag": "field1", "text": "ערך"},
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

    def test_schema_catalog_and_skill_expose_workflow(self):
        schema = BUILTIN_TOOL_SCHEMAS["document_manager"]["inputSchema"]
        self.assertEqual(schema["properties"]["action"]["enum"], (
            "doctor", "create", "edit", "inspect", "render", "export", "compare",
        ))
        self.assertIn("document_manager", PUBLIC_BUILTIN_TOOLS)
        self.assertEqual(TOOL_CATEGORIES["document_manager"], "documents")
        self.assertIn("advanced_com", DOCUMENT_MANAGER_ACTION_GUIDANCE["edit"])
        self.assertIn("render_after", TOOL_ACTION_FIELDS["document_manager"]["create"])

        skill = _ExtensionHarness()._builtin_skill_specs()["document_authoring"]
        self.assertEqual(skill["handler"], "instructions")
        self.assertIn("Visual QA loop", skill["instructions"])
        self.assertIn("he-IL", skill["instructions"])
        self.assertIn("UI automation", skill["instructions"])

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


if __name__ == "__main__":
    unittest.main()
