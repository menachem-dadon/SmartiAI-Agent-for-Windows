import base64
import copy
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QPushButton, QStackedWidget, QWidget

from smarti.agent.productivity_tools import ProductivityToolsMixin
from smarti.agent.tool_calls import ToolCallMixin
from smarti.config import BUILTIN_TOOL_SCHEMAS, DEFAULT_SETTINGS
from smarti.managers import SettingsManager, SmartiMemoryManager
from smarti.memory_ui import (
    MemoryEditDialog,
    MemoryFilterDialog,
    MemoryManagementPage,
)
from smarti.ui_controls import NoScrollComboBox
from smarti.ui_styles import themed_icon
from smarti.chat import ChatMessageContainer


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

    def _model_add(
        self,
        manager,
        content,
        *,
        category="general",
        scope="global",
        recall_policy="relevant",
        retrieval_hints=None,
    ):
        now = datetime.now().replace(microsecond=0).isoformat()
        result = manager.apply_model_memory_operations([{
            "action": "add", "content": content, "subject": "Saved fact",
            "category": category, "scope": scope,
            "memory_type": "user" if scope == "user" else "long_term",
            "importance": 4, "confidence": 0.95, "source_type": "user",
            "created_at": now, "updated_at": now, "expires_at": None,
            "volatile": False, "tags": [category],
            "recall_policy": recall_policy,
            "retrieval_hints": list(retrieval_hints or []),
            "why_saved": "The model selected a durable reusable fact.",
            "validity_basis": "Direct user statement.",
            "evidence": [{"type": "conversation", "reference": "test-chat"}],
        }])
        self.assertTrue(result["changed"])
        return result["memory_ids"][0]

    def test_legacy_retrieval_score_and_prompt_limits_are_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = str(Path(directory) / "settings.json")
            manager = SettingsManager(settings_path, DEFAULT_SETTINGS)
            loaded = {
                "settings_schema_version": 2,
                "memory": {
                    "min_relevance_score": 4.2,
                    "max_results": 8,
                    "max_injected_chars": 4200,
                    "user_memory_max_results": 8,
                    "user_memory_max_injected_chars": 2200,
                    "non_tool_memory_max_results": 8,
                    "tool_memory_prompt_max_results": 3,
                    "tool_memory_prompt_max_chars": 1400,
                },
            }

            migrated, changed = manager.migrate_or_merge(loaded)

            self.assertTrue(changed)
            memory = migrated["memory"]
            self.assertEqual(1, memory["retrieval_settings_version"])
            self.assertEqual(0.62, memory["min_relevance_score"])
            self.assertEqual(3, memory["max_results"])
            self.assertEqual(1200, memory["max_injected_chars"])
            self.assertEqual(0, memory["tool_memory_prompt_max_results"])
            self.assertEqual(0, memory["tool_memory_prompt_max_chars"])

    def test_custom_bounded_retrieval_settings_survive_migration(self):
        settings = {
            "memory": {
                "min_relevance_score": 0.73,
                "max_results": 5,
                "max_injected_chars": 1800,
            },
        }

        migrated, changed = SettingsManager.migrate_memory_retrieval_defaults(settings)

        self.assertTrue(changed)
        self.assertEqual(0.73, migrated["memory"]["min_relevance_score"])
        self.assertEqual(5, migrated["memory"]["max_results"])
        self.assertEqual(1800, migrated["memory"]["max_injected_chars"])
        self.assertEqual(1, migrated["memory"]["retrieval_settings_version"])

    def test_model_selected_sensitive_memory_is_active_encrypted_and_masked(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = self._model_add(
                manager, "My email is yael@example.com",
                category="email", scope="user",
            )

            raw_json = Path(manager.path).read_text(encoding="utf-8")
            raw_markdown = Path(manager.export_path).read_text(encoding="utf-8")
            self.assertNotIn("yael@example.com", raw_json)
            self.assertNotIn("yael@example.com", raw_markdown)
            stored = manager.get_entry(memory_id)
            self.assertEqual("active", stored["status"])
            self.assertTrue(stored["cloud_allowed"])
            self.assertTrue(stored["masked"])
            self.assertNotIn("yael@example.com", stored["content"])
            revealed = manager.get_entry(
                memory_id, reveal_sensitive=True, user_authorized=True
            )
            self.assertIn("yael@example.com", revealed["content"])

    def test_secret_is_never_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            with self.assertRaises(ValueError):
                manager.add("user", "My password is VerySecret123", source="manual_ui")
            self.assertEqual(0, manager.memory_stats()["active"])
            self.assertNotIn("pending", manager.memory_stats())
            self.assertFalse(
                manager.classify_content("כרטיס האשראי שלי הוא 4111111111111111")["store_allowed"]
            )
            self.assertFalse(manager.classify_content("token: abcdefghijklmnop")["store_allowed"])
            self.assertFalse(manager.classify_content("IBAN: DE89370400440532013000")["store_allowed"])

    def test_inferred_sensitive_details_are_skipped_without_consent(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_ids = manager.capture_critical_user_details(
                "הכתובת שלי היא רחוב הרצל 12. אני אלרגית לפניצילין."
            )
            self.assertEqual([], memory_ids)
            self.assertEqual([], manager.list_entries(status="active"))
            self.assertNotIn("pending", manager.memory_stats())

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
                item = manager.list_entries(
                    status="archive", reveal_sensitive=True, user_authorized=True
                )[0]
            self.assertIsNotNone(item)
            self.assertEqual("archive", item["status"])
            self.assertFalse(item["cloud_allowed"])
            self.assertEqual(1, manager.memory_stats()["archive"])
            self.assertNotIn("pending", manager.memory_stats())
            self.assertEqual("", item["content"])
            self.assertIn("DPAPI:", path.read_text(encoding="utf-8"))

    def test_sensitive_injection_requires_relevance_but_no_separate_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = self._model_add(
                manager, "My email is yael@example.com",
                category="email", scope="user",
            )
            self.assertNotIn(
                "yael@example.com", manager.build_prompt_context("What project am I using?")
            )
            self.assertIn("yael@example.com", manager.build_prompt_context("What is my email?"))

    def test_address_is_saved_without_explicit_remember_request_and_recalled(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            address = "המשתמש גר ברחוב הרי״ף 7 באלעד"
            memory_id = self._model_add(
                manager, address, category="address", scope="user",
            )

            raw = Path(manager.path).read_text(encoding="utf-8")
            self.assertNotIn(address, raw)
            self.assertTrue(manager.get_entry(memory_id)["masked"])
            self.assertIn(address, manager.build_prompt_context("איפה אני גר?"))

    def test_observed_malformed_add_envelopes_are_repaired_without_mechanical_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            now = datetime.now().replace(microsecond=0).isoformat()
            wrapped = {
                "operations": [{"add": {
                    "content": "המשתמש אוהב פסטה מוקרמת.",
                    "subject": "העדפות אוכל", "category": "preferences",
                    "scope": "user", "memory_type": "user", "importance": 2,
                    "confidence": 1, "source_type": "user", "created_at": now,
                    "updated_at": now, "expires_at": None, "volatile": False,
                    "tags": ["אוכל"], "why_saved": "העדפה יציבה",
                    "validity_basis": "אמירה ישירה", "evidence": [],
                }}],
            }
            with self.assertLogs(level="WARNING") as captured:
                _cleaned, operations = manager.extract_model_memory_decision(
                    f"תשובה\n<smarti_memory>{json.dumps(wrapped, ensure_ascii=False)}</smarti_memory>"
                )
            self.assertEqual("add", operations[0]["action"])
            self.assertIn("flattened wrapped 'add'", "\n".join(captured.output))
            pasta = manager.apply_model_memory_operations(operations)
            self.assertTrue(pasta["changed"])
            self.assertEqual("preference", manager.get_entry(pasta["memory_ids"][0])["category"])

            flat_address = {
                "operations": [{
                    "content": "המשתמש מתגורר ברחוב הרי״ף 7, אלעד.",
                    "subject": "כתובת מגורים", "category": "personal_details",
                    "scope": "user", "memory_type": "user", "importance": 4,
                    "confidence": 1, "source_type": "user", "created_at": now,
                    "updated_at": now, "expires_at": None, "volatile": False,
                    "tags": ["כתובת"], "why_saved": "כתובת יציבה ושימושית",
                    "validity_basis": "נמסר ישירות", "evidence": [],
                }],
            }
            with self.assertLogs(level="WARNING") as captured:
                _cleaned, operations = manager.extract_model_memory_decision(
                    f"תשובה\n<smarti_memory>{json.dumps(flat_address, ensure_ascii=False)}</smarti_memory>"
                )
            self.assertEqual("add", operations[0]["action"])
            self.assertIn("missing 'action=add'", "\n".join(captured.output))
            address = manager.apply_model_memory_operations(operations)
            self.assertTrue(address["changed"])
            address_entry = manager.get_entry(address["memory_ids"][0])
            self.assertEqual("address", address_entry["category"])
            self.assertTrue(address_entry["masked"])
            self.assertIn("הרי״ף 7", manager.build_prompt_context("איפה אני גר?"))
            self.assertIn(
                "הרי״ף 7",
                manager.build_prompt_context("מהי כתובת המגורים שלי?"),
            )
            self.assertNotIn(
                "address",
                manager._query_memory_categories("איך המערכת שומרת כתובות בזיכרון?"),
            )

            # Exact broad category observed from the configured live model.
            # It must not hide an address from intent-aware retrieval or its
            # sensitive-data classification.
            live_classification = manager.classify_content(
                "המשתמש מתגורר ברחוב בדיקה 42 בעיר הבדיקה.",
                "personal_information",
            )
            self.assertEqual("address", live_classification["category"])
            self.assertEqual("sensitive", live_classification["sensitivity"])

    def test_malformed_update_and_delete_are_repaired_only_when_unambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = self._model_add(
                manager, "Atlas uses SQLite", category="work", scope="global",
            )
            update_payload = {
                "operations": [{
                    "memory_id": memory_id, "content": "Atlas uses PostgreSQL",
                    "updated_at": datetime.now().replace(microsecond=0).isoformat(),
                    "reason": "The architecture changed.",
                }],
            }
            _cleaned, operations = manager.extract_model_memory_decision(
                f"ok<smarti_memory>{json.dumps(update_payload)}</smarti_memory>"
            )
            self.assertEqual("update", operations[0]["action"])
            self.assertTrue(manager.apply_model_memory_operations(operations)["changed"])
            self.assertIn("PostgreSQL", manager.get_entry(memory_id)["content"])

            delete_payload = {
                "operations": [{"delete": {
                    "memory_id": memory_id, "reason": "Decision was withdrawn.",
                }}],
            }
            _cleaned, operations = manager.extract_model_memory_decision(
                f"ok<smarti_memory>{json.dumps(delete_payload)}</smarti_memory>"
            )
            self.assertEqual("delete", operations[0]["action"])
            self.assertTrue(manager.apply_model_memory_operations(operations)["changed"])
            self.assertIsNone(manager.get_entry(memory_id))

            ambiguous = {"operations": [{"memory_id": "mem_unknown", "reason": "unclear"}]}
            with self.assertLogs(level="WARNING") as captured:
                _cleaned, operations = manager.extract_model_memory_decision(
                    f"ok<smarti_memory>{json.dumps(ambiguous)}</smarti_memory>"
                )
            self.assertEqual([], operations)
            self.assertIn("no safe action inference", "\n".join(captured.output))

    def test_food_preference_query_routes_profile_category_and_legacy_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            pasta_id = self._model_add(
                manager,
                "המשתמש אוהב פסטה מוקרמת.",
                category="preference",
                scope="user",
            )
            deli_id = self._model_add(
                manager,
                "המשתמש אוהב במיוחד את הסנדוויצ׳ים של ניו דלי.",
                category="preference",
                scope="user",
            )
            # Simulate the plural category emitted by the older live model and
            # already present in the user's persisted store.
            pasta = next(entry for entry in manager.data["entries"] if entry["id"] == pasta_id)
            pasta["category"] = "preferences"
            pasta.setdefault("metadata", {})["category"] = "preferences"

            query = "מה אני הכי אוהב לאכול?"
            results = manager.search(
                query,
                memory_types={"user", "long_term"},
                max_results=10,
                max_chars=8000,
                for_prompt=True,
            )

            self.assertEqual("preference", manager._entry_category(pasta))
            self.assertEqual({pasta_id, deli_id}, {result["entry"]["id"] for result in results})
            context = manager.build_prompt_context(query)
            self.assertIn("פסטה מוקרמת", context)
            self.assertIn("ניו דלי", context)
            indirect_context = manager.build_prompt_context(
                "איזו ארוחת ערב עשויה להתאים לטעם שלי?"
            )
            self.assertIn("פסטה מוקרמת", indirect_context)
            self.assertIn("ניו דלי", indirect_context)

    def test_model_authored_retrieval_hints_bridge_semantic_wording(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = self._model_add(
                manager,
                "The user uses compact artifact summaries.",
                category="general",
                scope="global",
                retrieval_hints=["shipping checklist", "release handoff", "delivery summary"],
            )

            results = manager.search(
                "What should the shipping checklist mention?",
                memory_types={"user", "long_term"},
                max_results=5,
                max_chars=4000,
                for_prompt=True,
            )

            self.assertEqual([memory_id], [result["entry"]["id"] for result in results])

    def test_always_style_preferences_are_injected_without_query_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            style_id = self._model_add(
                manager,
                "המשתמש מעדיף תשובות תמציתיות בעברית.",
                category="preference",
                scope="user",
                recall_policy="always",
                retrieval_hints=["סגנון תשובה", "שפת תשובה"],
            )
            food_id = self._model_add(
                manager,
                "המשתמש אוהב פסטה מוקרמת.",
                category="preference",
                scope="user",
                recall_policy="relevant",
                retrieval_hints=["אוכל אהוב", "המלצות אוכל"],
            )

            context = manager.build_prompt_context("כמה זה 2 ועוד 2?")

            self.assertIn("Always-applied response preferences", context)
            self.assertIn("תשובות תמציתיות בעברית", context)
            self.assertNotIn("פסטה מוקרמת", context)
            self.assertIn(style_id, context)
            self.assertNotIn(food_id, context)

    def test_legacy_style_preference_gets_always_lane_without_promoting_food(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            style_id = self._model_add(
                manager,
                "המשתמש מעדיף תשובות קצרות וללא אימוג׳י.",
                category="preference",
                scope="user",
            )
            food_id = self._model_add(
                manager,
                "המשתמש אוהב מרק עדשים.",
                category="preference",
                scope="user",
            )
            for entry in manager.data["entries"]:
                entry.setdefault("metadata", {}).pop("recall_policy", None)

            context = manager.build_prompt_context("כמה זה 3 ועוד 4?")

            self.assertIn(style_id, context)
            self.assertNotIn(food_id, context)
            self.assertIn("תשובות קצרות", context)
            self.assertNotIn("מרק עדשים", context)

    def test_sensitive_fact_cannot_become_unconditionally_injected(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            memory_id = self._model_add(
                manager,
                "My address is 14 Test Street.",
                category="address",
                scope="user",
                recall_policy="always",
                retrieval_hints=["home address"],
            )

            entry = manager.get_entry(memory_id, reveal_sensitive=True, user_authorized=True)
            self.assertEqual("relevant", entry["metadata"]["recall_policy"])
            self.assertNotIn("14 Test Street", manager.build_prompt_context("What is two plus two?"))

    def test_global_memory_switch_retains_existing_data_but_blocks_use_and_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            memory_id = self._model_add(
                manager, "The user prefers concise answers",
                category="preference", scope="user",
            )
            before = manager.memory_stats()["active"]
            core.settings["memory"]["enabled"] = False

            self.assertEqual("Saved memory is disabled.", manager.build_prompt_context("How should you answer?"))
            self.assertEqual("MEMORY_DISABLED", manager.tool_search_text("concise"))
            self.assertIn("disabled by the user", core.memory_manager_tool("search", {"query": "concise"}))
            blocked = manager.apply_model_memory_operations([{
                "action": "delete", "memory_id": memory_id,
            }])
            self.assertFalse(blocked["changed"])
            self.assertEqual(before, manager.memory_stats()["active"])
            self.assertIsNotNone(manager.get_entry(memory_id))

            core.settings["memory"]["enabled"] = True
            self.assertIn("concise", manager.build_prompt_context("What is my preference for answers?"))

    def test_all_persistent_memory_content_is_encrypted_in_every_local_store(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            content = "Atlas uses PostgreSQL for durable storage"
            self._model_add(manager, content, category="work", scope="global")

            self.assertNotIn(content, Path(manager.path).read_text(encoding="utf-8"))
            self.assertNotIn(content, Path(manager.export_path).read_text(encoding="utf-8"))
            with closing(sqlite3.connect(manager.store.path)) as db:
                row = db.execute(
                    "SELECT content, record_json FROM memory_records LIMIT 1"
                ).fetchone()
                fts_count = db.execute("SELECT count(*) FROM memory_fts").fetchone()[0]
            self.assertTrue(str(row[0]).startswith("DPAPI:"))
            self.assertNotIn(content, str(row[1]))
            self.assertEqual(0, fts_count)

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
            memory_id = self._model_add(
                manager, "My phone is +1 202 555 0187",
                category="phone", scope="user",
            )
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

    def test_mechanical_inferred_capture_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            self.assertEqual([], manager.capture_critical_user_details("I prefer compact answers"))
            self.assertEqual([], manager.auto_capture_turn("I prefer compact answers", "okay"))
            self.assertEqual(0, manager.memory_stats()["active"])
            self.assertNotIn("pending", manager.memory_stats())

    def test_public_schema_and_router_cover_management_contract(self):
        actions = set(
            BUILTIN_TOOL_SCHEMAS["memory_manager"]["inputSchema"]["properties"]["action"]["enum"]
        )
        self.assertEqual({"list", "get", "search", "export", "import", "stats"}, actions)
        self.assertTrue({
            "add", "edit", "archive", "restore", "forget", "clear", "update",
            "approve", "reject", "feedback",
        }.isdisjoint(actions))
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

    def test_rtl_page_shows_plaintext_to_local_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            memory_id = self._model_add(
                manager, "My email is yael@example.com",
                category="email", scope="user",
            )
            self.assertTrue(memory_id)
            app = QApplication.instance() or QApplication([])
            window = _Window()
            page = MemoryManagementPage(core, window)
            page.resize(450, 760)
            page.show()
            page.load_data(force=True)
            app.processEvents()

            self.assertEqual(Qt.LayoutDirection.RightToLeft, page.layoutDirection())
            self.assertEqual(1, page.content_layout.count())
            card = page.content_layout.itemAt(0).widget()
            labels = " ".join(label.text() for label in card.findChildren(type(page.stats_label)))
            self.assertIn("yael@example.com", labels)
            self.assertNotIn("מוגן", labels)

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
            long_subject = "כותרת זיכרון ארוכה שצריכה להישבר לכמה שורות ולהופיע במלואה בלי חיתוך מלמעלה או מלמטה"
            manager.add(
                "long_term",
                "word" * 900,
                subject=long_subject,
                source="manual_ui",
            )
            app = QApplication.instance() or QApplication([])

            filters = MemoryFilterDialog({}, None)
            self.assertFalse(hasattr(filters, "source_filter"))
            self.assertFalse(hasattr(filters, "type_filter"))
            self.assertEqual(
                {"category", "sensitivity", "date_range", "expiry", "sort_by"},
                set(filters.values()),
            )
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
            self.assertEqual(
                ["active", "archive", "all"],
                [page.status_filter.itemData(index) for index in range(page.status_filter.count())],
            )
            self.assertNotIn("לשיחה הנוכחית", [
                page.status_filter.itemText(index) for index in range(page.status_filter.count())
            ])
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
            subject_label = next(
                label for label in card.findChildren(QLabel)
                if label.toolTip() == long_subject
            )
            self.assertEqual(long_subject, subject_label.text())
            self.assertGreater(subject_label.height(), 40)
            badge = next(label for label in card.findChildren(QLabel) if label.text() == "פעיל")
            self.assertEqual((60, 24), (badge.width(), badge.height()))
            preview = next(label for label in card.findChildren(QLabel) if label.objectName().startswith("MemoryPreview_"))
            self.assertTrue(preview.text().startswith("תוכן הזיכרון:"))
            self.assertTrue(preview.alignment() & Qt.AlignmentFlag.AlignRight)
            self.assertFalse(themed_icon("memory_management_icon").isNull())

    def test_assistant_message_memory_indicator_uses_theme_icon_next_to_actions(self):
        app = QApplication.instance() or QApplication([])
        container = ChatMessageContainer("Answer", is_user=False, parent_width=500)
        app.processEvents()
        self.assertTrue(container.memory_updated_indicator.isHidden())
        container.set_memory_updated(True)
        app.processEvents()
        self.assertFalse(container.memory_updated_indicator.isHidden())
        self.assertEqual("הזיכרון עודכן", container.memory_updated_label.text())
        self.assertIsNotNone(container.memory_updated_icon.pixmap())
        self.assertFalse(container.memory_updated_icon.pixmap().isNull())
        container.apply_theme()
        self.assertIn("font-size: 11px", container.memory_updated_label.styleSheet())
        container.close()

    def test_memory_page_global_switch_is_default_on_and_does_not_delete_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            core, manager = self._manager(directory)
            self._model_add(
                manager, "The user prefers Hebrew", category="preference", scope="user",
            )
            before = manager.memory_stats()["active"]
            app = QApplication.instance() or QApplication([])
            page = MemoryManagementPage(core, _Window())

            self.assertTrue(page.memory_enabled_checkbox.isChecked())
            self.assertEqual("שימוש בזיכרון מתמשך", page.memory_enabled_checkbox.text())
            self.assertIn("אינו מוחק זיכרונות קיימים", page.memory_enabled_description.text())
            visible_copy = " ".join((
                page.memory_enabled_checkbox.text(),
                page.memory_enabled_checkbox.toolTip(),
                page.memory_enabled_description.text(),
                page.status_filter.toolTip(),
            ))
            for gendered_word in ("כתבי", "בחרי", "השתמשי"):
                self.assertNotIn(gendered_word, visible_copy)
            page.memory_enabled_checkbox.click()
            app.processEvents()

            self.assertFalse(core.settings["memory"]["enabled"])
            self.assertGreater(core.saved_settings, 0)
            self.assertEqual(before, manager.memory_stats()["active"])
            page.close()


if __name__ == "__main__":
    unittest.main()
