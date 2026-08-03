import base64
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QStackedWidget, QWidget

from smarti.agent.productivity_tools import ProductivityToolsMixin
from smarti.agent.tool_calls import ToolCallMixin
from smarti.config import BUILTIN_TOOL_SCHEMAS, DEFAULT_SETTINGS
from smarti.managers import SmartiMemoryManager
from smarti.memory_ui import (
    MemoryEditDialog,
    MemoryFilterDialog,
    MemoryManagementPage,
)
from smarti.ui_controls import NoScrollComboBox
from smarti.ui_styles import themed_icon


def _protect(value):
    return "DPAPI:" + base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _unprotect(value):
    if not str(value).startswith("DPAPI:"):
        return value
    return base64.b64decode(str(value)[6:]).decode("utf-8")


class _Core(ProductivityToolsMixin):
    def __init__(self):
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.saved_settings = 0
        self.logged_usage = []
        self.audit_logger = None

    def _save_settings(self):
        self.saved_settings += 1

    def _log_usage(self, model, usage):
        self.logged_usage.append((model, usage))


class _Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        self.chat_page = QWidget()
        self.stacked_widget.addWidget(self.chat_page)


class MemoryManagementTests(unittest.TestCase):
    def setUp(self):
        self.protect = patch("smarti.managers.dpapi_protect_text", side_effect=_protect)
        self.unprotect = patch("smarti.managers.dpapi_unprotect_text", side_effect=_unprotect)
        self.protect.start()
        self.unprotect.start()

    def tearDown(self):
        self.unprotect.stop()
        self.protect.stop()

    def _manager(self, directory):
        core = _Core()
        manager = SmartiMemoryManager(core, str(Path(directory) / "memory.json"))
        core.memory_manager = manager
        return core, manager

    def test_sensitive_auto_capture_is_active_encrypted_cloud_ready_and_masked(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_ids = manager.capture_critical_user_details("My email is yael@example.com")

            self.assertEqual(1, len(memory_ids))
            raw_json = Path(manager.path).read_text(encoding="utf-8")
            raw_markdown = Path(manager.export_path).read_text(encoding="utf-8")
            self.assertNotIn("yael@example.com", raw_json)
            self.assertNotIn("yael@example.com", raw_markdown)
            self.assertEqual(0, manager.memory_stats()["pending"])
            stored = manager.get_entry(memory_ids[0])
            self.assertEqual("active", stored["status"])
            self.assertTrue(stored["cloud_allowed"])
            self.assertTrue(stored["masked"])
            self.assertNotIn("yael@example.com", stored["content"])
            revealed = manager.get_entry(
                memory_ids[0], reveal_sensitive=True, user_authorized=True
            )
            self.assertIn("yael@example.com", revealed["content"])

    def test_secret_is_never_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            with self.assertRaises(ValueError):
                manager.add("user", "My password is VerySecret123", source="manual_ui")
            self.assertEqual(0, manager.memory_stats()["active"])
            self.assertEqual(0, manager.memory_stats()["pending"])
            self.assertFalse(
                manager.classify_content("כרטיס האשראי שלי הוא 4111111111111111")["store_allowed"]
            )

    def test_multilingual_address_and_health_are_stored_without_review(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_ids = manager.capture_critical_user_details(
                "הכתובת שלי היא רחוב הרצל 12. אני אלרגית לפניצילין."
            )
            self.assertEqual(2, len(memory_ids))
            rows = manager.list_entries(status="active")
            categories = {item["category"] for item in rows}
            self.assertEqual({"address", "health"}, categories)
            self.assertEqual(0, manager.memory_stats()["pending"])
            self.assertTrue(all(item["cloud_allowed"] for item in rows))
            self.assertTrue(all(item["status"] == "active" for item in rows))

    def test_decryption_failure_preserves_protected_record_without_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text(json.dumps({
                "schema_version": 3,
                "entries": [],
                "archive": [],
                "pending": [{
                    "id": "pending_locked",
                    "type": "user",
                    "subject": "locked email",
                    "content": _protect("locked@example.com"),
                    "category": "email",
                    "sensitivity": "sensitive",
                    "created_at": "2026-08-01T00:00:00",
                    "updated_at": "2026-08-01T00:00:00",
                    "metadata": {"encrypted": True, "consent_state": "pending_review"},
                }],
                "stats": {
                    "privacy_policy_version": 1,
                    "automatic_use_policy_version": 1,
                },
            }, ensure_ascii=False), encoding="utf-8")
            core = _Core()
            with patch("smarti.managers.dpapi_unprotect_text", return_value=""):
                manager = SmartiMemoryManager(core, str(path))
                item = manager.get_entry(
                    "pending_locked", reveal_sensitive=True, user_authorized=True
                )
            self.assertIsNotNone(item)
            self.assertEqual("active", item["status"])
            self.assertTrue(item["cloud_allowed"])
            self.assertEqual(0, manager.memory_stats()["pending"])
            self.assertEqual("", item["content"])
            self.assertIn("DPAPI:", path.read_text(encoding="utf-8"))

    def test_sensitive_injection_requires_relevance_but_not_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = manager.capture_critical_user_details(
                "My email is yael@example.com"
            )[0]
            self.assertNotIn(
                "yael@example.com", manager.build_prompt_context("What project am I using?")
            )
            self.assertIn(
                "yael@example.com", manager.build_prompt_context("What is my email?")
            )

    def test_crud_archive_restore_undo_and_version_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = manager.add(
                "long_term", "Project Atlas uses FastAPI", subject="Atlas", source="manual_ui"
            )
            current = manager.get_entry(memory_id, reveal_sensitive=True, user_authorized=True)
            manager.edit_entry(
                memory_id,
                expected_version=current["version"],
                user_authorized=True,
                content="Project Atlas uses Django",
            )
            with self.assertRaises(RuntimeError):
                manager.edit_entry(
                    memory_id,
                    expected_version=current["version"],
                    user_authorized=True,
                    content="stale overwrite",
                )
            self.assertTrue(manager.undo_last())
            self.assertIn("FastAPI", manager.get_entry(memory_id)["content"])
            self.assertTrue(manager.archive_entry(memory_id))
            self.assertEqual("archive", manager.get_entry(memory_id)["status"])
            self.assertTrue(manager.restore_entry(memory_id))
            self.assertEqual("active", manager.get_entry(memory_id)["status"])

    def test_encrypted_export_import_does_not_emit_sensitive_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = manager.capture_critical_user_details(
                "My phone is +1 202 555 0187"
            )[0]
            self.assertTrue(manager.get_entry(memory_id)["cloud_allowed"])
            export_path = Path(directory) / "export.json"
            manager.export_memory(str(export_path), encrypted=True, include_sensitive=True)
            raw = export_path.read_text(encoding="utf-8")
            self.assertNotIn("202 555 0187", raw)
            self.assertIn("DPAPI:", raw)

            second_core = _Core()
            second = SmartiMemoryManager(second_core, str(Path(directory) / "second.json"))
            result = second.import_memory(str(export_path), user_authorized=True)
            self.assertEqual(1, result["imported"])
            imported = second.list_entries(status="active")[0]
            self.assertTrue(imported["masked"])

    def test_legacy_pending_capture_entry_point_stores_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            memory_id = manager.queue_pending_capture(
                "user", "My email is yael@example.com", category="email"
            )
            self.assertTrue(memory_id.startswith("mem_"))
            self.assertEqual("active", manager.get_entry(memory_id)["status"])
            self.assertEqual(0, manager.memory_stats()["pending"])
            self.assertTrue(manager.get_entry(memory_id)["cloud_allowed"])

    def test_public_schema_and_router_cover_management_contract(self):
        actions = set(
            BUILTIN_TOOL_SCHEMAS["memory_manager"]["inputSchema"]["properties"]["action"]["enum"]
        )
        self.assertTrue({
            "list", "get", "search", "add", "edit", "archive", "restore", "forget",
            "clear", "export", "import", "stats",
        }.issubset(actions))
        self.assertTrue({"review_pending", "approve_pending", "reject_pending"}.isdisjoint(actions))
        properties = BUILTIN_TOOL_SCHEMAS["memory_manager"]["inputSchema"]["properties"]
        self.assertNotIn("cloud_allowed", properties)
        self.assertNotIn("pending_id", properties)
        calls = ToolCallMixin()
        routed, args = calls._route_unified_tool(
            "memory_manager", {"action": "archive", "memory_id": "mem_123"}
        )
        self.assertEqual("memory_operation", routed)
        self.assertEqual("archive", args["action"])
        self.assertTrue(calls._tool_is_mutating_or_control(
            "memory_manager", {"action": "archive", "memory_id": "mem_123"}
        ))
        self.assertFalse(calls._tool_is_mutating_or_control(
            "memory_manager", {"action": "stats"}
        ))

    def test_rtl_page_uses_masked_canonical_state(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            memory_id = manager.capture_critical_user_details(
                "My email is yael@example.com"
            )[0]
            self.assertTrue(memory_id)
            app = QApplication.instance() or QApplication([])
            window = _Window()
            page = MemoryManagementPage(core, window)
            page.status_filter.setCurrentIndex(page.status_filter.findData("active"))
            page.resize(450, 760)
            page.show()
            page.load_data(force=True)
            app.processEvents()

            self.assertEqual(Qt.LayoutDirection.RightToLeft, page.layoutDirection())
            self.assertEqual(1, page.content_layout.count())
            card = page.content_layout.itemAt(0).widget()
            labels = " ".join(label.text() for label in card.findChildren(type(page.stats_label)))
            self.assertNotIn("yael@example.com", labels)

    def test_user_work_artifact_is_migrated_and_cannot_be_created_again(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text(json.dumps({
                "schema_version": 3,
                "entries": [{
                    "id": "mem_work",
                    "type": "long_term",
                    "subject": "User work",
                    "content": "User work: User work User work: User work: נתח את הקובץ",
                    "source": "critical_backfill",
                    "created_at": "2026-08-01T00:00:00",
                    "updated_at": "2026-08-01T00:00:00",
                    "metadata": {},
                }],
                "archive": [], "pending": [],
                "stats": {"privacy_policy_version": 1},
            }, ensure_ascii=False), encoding="utf-8")
            core = _Core()
            manager = SmartiMemoryManager(core, str(path))
            raw = path.read_text(encoding="utf-8")
            markdown = Path(manager.export_path).read_text(encoding="utf-8")
            self.assertNotIn("User work", raw)
            self.assertNotIn("User work", markdown)
            item = manager.get_entry("mem_work", reveal_sensitive=True, user_authorized=True)
            self.assertEqual("נתח את הקובץ", item["content"])
            created = manager.add("long_term", "User work: פרט עתידי", subject="User work")
            future = manager.get_entry(created, reveal_sensitive=True, user_authorized=True)
            self.assertNotIn("User work", future["content"])
            self.assertNotIn("User work", future["subject"])
            self.assertEqual([], manager.extract_critical_user_memories("שולחן העבודה שלי מסודר"))

    def test_critical_backfill_never_reprocesses_its_own_generated_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            manager.add(
                "long_term",
                "User work: נתח את הקובץ",
                subject="User work",
                source="critical_backfill",
                tags=["auto", "critical", "work"],
                metadata={"capture": "deterministic_preflight"},
            )
            before = len(manager.data["entries"])
            manager.data["stats"]["critical_backfill_version"] = 0

            self.assertEqual([], manager.backfill_critical_user_details())
            self.assertEqual(before, len(manager.data["entries"]))

    def test_simplified_page_defers_list_build_until_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            app = QApplication.instance() or QApplication([])
            window = _Window()
            with patch.object(manager, "list_entries", wraps=manager.list_entries) as list_entries:
                page = MemoryManagementPage(core, window)
                app.processEvents()
                self.assertEqual(0, list_entries.call_count)
                self.assertFalse(page.selection_bar.isVisible())

    def test_long_list_is_paged_without_timed_card_flicker(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            for index in range(30):
                manager.add(
                    "long_term", f"פרט שימושי מספר {index}",
                    subject=f"זיכרון {index}", source="manual_ui",
                )
            app = QApplication.instance() or QApplication([])
            window = _Window()
            page = MemoryManagementPage(core, window)
            page.resize(420, 720)
            page.show()
            page.load_data(force=True)
            app.processEvents()
            self.assertEqual(page.PAGE_SIZE, page.content_layout.count())
            self.assertEqual(page.PAGE_SIZE, page._page_cursor)
            page._maybe_load_more(page.scroll.verticalScrollBar().maximum())
            app.processEvents()
            self.assertEqual(page.PAGE_SIZE * 2, page.content_layout.count())
            while page._page_cursor < len(page._rows):
                page._maybe_load_more(page.scroll.verticalScrollBar().maximum())
                app.processEvents()
            self.assertEqual(30, page.content_layout.count())
            self.assertEqual(30, page._page_cursor)

    def test_narrow_layout_has_consistent_controls_and_no_horizontal_list_scroll(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            manager.add(
                "long_term",
                "word" * 900,
                subject="A very long unbroken subject" * 20,
                source="manual_ui",
            )
            app = QApplication.instance() or QApplication([])

            filters = MemoryFilterDialog({}, None)
            self.assertGreaterEqual(filters.source_filter.minimumHeight(), 40)
            self.assertTrue(all(
                isinstance(combo, NoScrollComboBox)
                for combo in filters.findChildren(NoScrollComboBox)
            ))
            filter_buttons = filters.findChildren(QPushButton)
            self.assertEqual(1, len({button.height() for button in filter_buttons}))
            filters.close()

            editor = MemoryEditDialog(parent=None, title="זיכרון חדש")
            self.assertTrue(editor.advanced_scroll.isHidden())
            self.assertLessEqual(editor.content.maximumHeight(), 170)
            self.assertFalse(hasattr(editor, "cloud_allowed"))
            self.assertIsInstance(editor.category, NoScrollComboBox)
            save_cancel = [
                button for button in editor.findChildren(QPushButton)
                if button.text() in {"שמור", "ביטול"}
            ]
            self.assertEqual(2, len(save_cancel))
            self.assertEqual(1, len({button.height() for button in save_cancel}))
            editor.close()

            window = _Window()
            page = MemoryManagementPage(core, window)
            self.assertIsInstance(page.status_filter, NoScrollComboBox)
            page.resize(360, 700)
            page.show()
            page.load_data(force=True)
            for _ in range(4):
                app.processEvents()
            self.assertEqual(0, page.scroll.horizontalScrollBar().maximum())
            card = page.content_layout.itemAt(0).widget()
            self.assertLessEqual(card.width(), page.scroll.viewport().width())
            direct_action_buttons = [
                child for child in card.findChildren(QPushButton)
                if child.parent() is card
            ]
            self.assertEqual([""], [button.text() for button in direct_action_buttons])
            self.assertFalse(direct_action_buttons[0].icon().isNull())
            self.assertEqual((30, 30), (direct_action_buttons[0].width(), direct_action_buttons[0].height()))
            self.assertLessEqual(direct_action_buttons[0].y(), 12)
            self.assertLessEqual(card.height(), 112)
            badge = next(label for label in card.findChildren(QLabel) if label.text() == "פעיל")
            self.assertEqual((52, 24), (badge.width(), badge.height()))
            preview = next(label for label in card.findChildren(QLabel) if label.objectName().startswith("MemoryPreview_"))
            self.assertTrue(preview.text().startswith("תוכן הזיכרון:"))
            self.assertTrue(preview.alignment() & Qt.AlignmentFlag.AlignRight)
            self.assertFalse(themed_icon("memory_management_icon").isNull())


if __name__ == "__main__":
    unittest.main()
