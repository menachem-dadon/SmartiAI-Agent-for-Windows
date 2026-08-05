import copy
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from smarti.config import DEFAULT_SETTINGS
from smarti.managers import SmartiMemoryManager


class _ChatStore:
    def active_session(self):
        return {"id": "chat-quality"}


class _Core:
    def __init__(self, project_dir):
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.current_working_directory = str(project_dir)
        self.chat_store = _ChatStore()
        self.audit_logger = None
        self.usage = []

    def _save_settings(self):
        return None

    def _log_usage(self, model, usage):
        self.usage.append((model, usage))


class MemoryQualityV2Tests(unittest.TestCase):
    def _manager(self, directory):
        core = _Core(directory)
        manager = SmartiMemoryManager(core, str(Path(directory) / "memory.json"))
        core.memory_manager = manager
        return core, manager

    def _seed_quality_memories(self, manager):
        manager.add(
            "long_term", "הפרויקט משתמש ב-SQLite עבור מסד הנתונים המקומי",
            subject="מסד נתונים", category="project", scope=manager._project_scope(),
            source="manual_ui", metadata={"automatic_context_eligible": True},
        )
        manager.add(
            "long_term", "Old weather observation: it rained in London yesterday",
            subject="weather", scope=manager._project_scope(), source="manual_ui",
            volatile=True, metadata={"automatic_context_eligible": True},
        )
        manager.add(
            "user", "אני מעדיפה שממשק המשתמש יהיה בעברית",
            subject="שפת ממשק", category="preference", scope="user:default",
            source="manual_ui", metadata={"automatic_context_eligible": True},
        )

    def test_quality_corpus_has_precise_bounded_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            self._seed_quality_memories(manager)
            fixture = Path(__file__).parent / "fixtures" / "memory_quality_queries.jsonl"
            cases = [json.loads(line) for line in fixture.read_text(encoding="utf-8").splitlines() if line]
            for case in cases:
                with self.subTest(query=case["query"]):
                    context = manager.build_prompt_context(case["query"])
                    if case["expected"] is None:
                        self.assertNotIn("Semantically relevant saved memory", context)
                        self.assertIn("Always-applied response preferences", context)
                    else:
                        self.assertIn(case["expected"], context)
                    self.assertNotIn(case["forbidden"], context)
                    self.assertLessEqual(len(context), 1200)
                    self.assertLessEqual(context.count("\n- id="), 3)

    def test_legacy_birthday_category_is_recovered_and_retrievable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            now = datetime.now().isoformat(timespec="seconds")
            path.write_text(json.dumps({
                "schema_version": 3,
                "entries": [{
                    "id": "mem_birthday", "type": "user", "scope": "user:default",
                    "subject": "birthday", "content": "יום ההולדת שלי הוא ביוני",
                    "category": "general", "source": "explicit_tool", "importance": 5,
                    "confidence": 0.8, "created_at": now, "updated_at": now,
                    "metadata": {"automatic_context_eligible": True},
                }],
                "archive": [], "pending": [], "stats": {"quality_policy_version": 2},
            }, ensure_ascii=False), encoding="utf-8")
            manager = SmartiMemoryManager(_Core(directory), str(path))

            entry = manager.get_entry("mem_birthday")
            self.assertEqual("birthday", entry["category"])
            self.assertIn("ביוני", manager.build_prompt_context("מה יום ההולדת שלי?"))

    def test_search_is_read_only_and_usage_is_one_sqlite_event_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            self._seed_quality_memories(manager)
            json_mtime = Path(manager.path).stat().st_mtime_ns
            with closing(sqlite3.connect(manager.store.path)) as db:
                before_events = db.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
            self.assertTrue(manager.search("מסד הנתונים בפרויקט", for_prompt=True))
            self.assertEqual(json_mtime, Path(manager.path).stat().st_mtime_ns)
            with closing(sqlite3.connect(manager.store.path)) as db:
                self.assertEqual(before_events, db.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0])

            context = manager.build_prompt_context("מסד הנתונים בפרויקט", log_usage=True)
            self.assertIn("SQLite", context)
            self.assertEqual(json_mtime, Path(manager.path).stat().st_mtime_ns)
            with closing(sqlite3.connect(manager.store.path)) as db:
                events = db.execute("SELECT event FROM memory_events ORDER BY id").fetchall()
            self.assertGreaterEqual(len(events), 2)
            self.assertEqual(len(events) // 2, sum(event == ("selected",) for event in events))
            self.assertEqual(len(events) // 2, sum(event == ("injected",) for event in events))

    def test_mechanical_capture_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            ids = manager.auto_capture_turn(
                "I prefer concise answers in English",
                "Assistant output that must stay only in chat history",
                tool_records=[{"tool": "file_manager", "status": "ok", "preview": "tool output must not persist"}],
            )
            self.assertEqual([], ids)
            serialized = json.dumps(manager.data, ensure_ascii=False)
            self.assertNotIn("I prefer concise answers", serialized)
            self.assertNotIn("Assistant output", serialized)
            self.assertNotIn("tool output must not persist", serialized)

    def test_model_decision_can_save_user_and_assistant_derived_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            now = datetime.now().isoformat(timespec="seconds")
            result = manager.apply_model_memory_operations([{
                "action": "add",
                "content": "The user prefers short release summaries",
                "subject": "Release summary style",
                "category": "preference",
                "scope": "user",
                "memory_type": "user",
                "importance": 4,
                "confidence": 0.94,
                "source_type": "user",
                "created_at": now,
                "updated_at": now,
                "expires_at": None,
                "volatile": False,
                "tags": ["release", "preference"],
                "why_saved": "A durable presentation preference.",
                "validity_basis": "Direct user statement.",
                "evidence": [{"type": "conversation", "reference": "chat-quality"}],
            }, {
                "action": "add",
                "content": "Release verification uses python -m unittest",
                "subject": "Release verification command",
                "category": "work",
                "scope": "global",
                "memory_type": "long_term",
                "importance": 4,
                "confidence": 0.91,
                "source_type": "decision",
                "created_at": now,
                "updated_at": now,
                "expires_at": None,
                "volatile": False,
                "tags": ["release", "tests"],
                "why_saved": "A reusable command selected by the assistant.",
                "validity_basis": "Verified during the task.",
                "evidence": [{"type": "tool", "reference": "shell_command"}],
            }], session_id="chat-quality")
            self.assertTrue(result["changed"])
            self.assertEqual(2, result["count"])
            entries = [manager.get_entry(memory_id) for memory_id in result["memory_ids"]]
            self.assertTrue(all(entry["status"] == "active" for entry in entries))
            self.assertTrue(all(entry["metadata"]["capture"] == "model_semantic_decision" for entry in entries))
            self.assertEqual([], manager.data["pending"])

    def test_only_global_memory_controls_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            self._seed_quality_memories(manager)
            manager._settings()["rag_enabled"] = False
            self.assertEqual(
                "Saved memory is disabled.",
                manager.build_prompt_context("Which database does this project use?"),
            )
            manager._settings()["auto_capture"] = False
            self.assertEqual([], manager.auto_capture_turn("I prefer very short answers", "okay"))
            manager._settings()["auto_capture"] = True
            self.assertEqual([], manager.auto_capture_turn("Please remember that release checks use unittest", "okay"))

    def test_normalized_and_near_duplicate_capture_consolidates(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            first = manager.add(
                "long_term", "The Atlas project uses SQLite as its local database",
                scope=manager._project_scope(), category="project", source="manual_ui",
            )
            second = manager.add(
                "long_term", "Atlas project uses SQLite as the local database",
                scope=manager._project_scope(), category="project", source="manual_ui",
            )
            self.assertEqual(first, second)
            self.assertEqual(1, manager.memory_stats()["active"])
            self.assertEqual(1, manager.get_entry(first)["duplicate_count"])

    def test_scope_evidence_archive_and_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            current = manager.add(
                "long_term", "Atlas uses PostgreSQL for analytics",
                scope=manager._project_scope(), category="project", source="manual_ui",
                metadata={"automatic_context_eligible": True},
            )
            manager.add(
                "long_term", "Another project uses MySQL for analytics",
                scope="project:C:/other-project", category="project", source="manual_ui",
                metadata={"automatic_context_eligible": True},
            )
            self.assertTrue(all(entry["scope"] == "global" for entry in manager.data["entries"]))
            self.assertIn("PostgreSQL", manager.build_prompt_context("Which database does the project use for analytics?"))

            missing = manager.add(
                "long_term", "The build artifact is signed by release-key.pem",
                scope=manager._project_scope(), category="project", source="manual_ui",
                metadata={
                    "automatic_context_eligible": True,
                    "evidence": [{"type": "file", "reference": str(Path(directory) / "missing.txt")}],
                },
            )
            self.assertNotIn("release-key.pem", manager.build_prompt_context("Which build artifact key does the project use?"))
            evidence_file = Path(directory) / "evidence.txt"
            evidence_file.write_text("current value", encoding="utf-8")
            manager.add(
                "long_term", "The project signing mode is hardware-backed",
                scope=manager._project_scope(), category="project", source="manual_ui",
                metadata={
                    "automatic_context_eligible": True,
                    "evidence": [{
                        "type": "file", "reference": str(evidence_file),
                        "digest": "sha256:" + ("0" * 64),
                    }],
                },
            )
            self.assertNotIn("hardware-backed", manager.build_prompt_context("What signing mode does the project use?"))
            self.assertTrue(manager.archive_entry(current, reason="manual"))
            self.assertEqual("archive", manager.get_entry(current)["status"])

            noisy = manager.add(
                "long_term", "The project uses an obsolete packaging hint",
                scope=manager._project_scope(), category="project", source="inferred_user_statement",
                metadata={"inferred": True},
            )
            raw = next(item for item in manager.data["entries"] if item["id"] == noisy)
            raw["created_at"] = (datetime.now() - timedelta(days=3)).isoformat(timespec="seconds")
            raw["updated_at"] = raw["created_at"]
            manager._settings()["inferred_memory_unused_days"] = 1
            manager.prune_unused()
            self.assertEqual("archive", manager.get_entry(noisy)["status"])
            self.assertEqual("unused_inferred_memory", manager.get_entry(noisy)["archive_reason"])

    def test_hidden_envelope_update_delete_and_noop_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            created_at = datetime.now().replace(microsecond=0).isoformat()
            response = (
                "Done for the user.\n"
                "<smarti_memory>{\"operations\":[{\"action\":\"add\","
                "\"content\":\"Atlas uses SQLite\",\"subject\":\"Atlas database\","
                "\"category\":\"work\",\"scope\":\"global\",\"memory_type\":\"long_term\","
                "\"importance\":4,\"confidence\":0.9,\"source_type\":\"tool\","
                f"\"created_at\":\"{created_at}\",\"updated_at\":\"{created_at}\","
                "\"expires_at\":null,\"volatile\":false,\"tags\":[\"atlas\"],"
                "\"why_saved\":\"Reusable verified architecture fact\","
                "\"validity_basis\":\"Verified from repository configuration\","
                "\"evidence\":[{\"type\":\"tool\",\"reference\":\"file_manager\"}]}]}"
                "</smarti_memory>"
            )
            cleaned, operations = manager.extract_model_memory_decision(response)
            self.assertEqual("Done for the user.", cleaned)
            self.assertNotIn("smarti_memory", cleaned)
            added = manager.apply_model_memory_operations(operations, session_id="chat-quality")
            self.assertTrue(added["changed"])
            memory_id = added["memory_ids"][0]
            original = manager.get_entry(memory_id)
            self.assertEqual(created_at, original["created_at"])
            self.assertEqual("tool", original["metadata"]["source_type"])

            duplicate = manager.apply_model_memory_operations(operations, session_id="chat-quality")
            self.assertFalse(duplicate["changed"])
            self.assertEqual(original["version"], manager.get_entry(memory_id)["version"])
            self.assertEqual(original["updated_at"], manager.get_entry(memory_id)["updated_at"])

            updated_at = (datetime.now() + timedelta(seconds=1)).replace(microsecond=0).isoformat()
            updated = manager.apply_model_memory_operations([{
                "action": "update", "memory_id": memory_id,
                "content": "Atlas uses PostgreSQL", "subject": "Atlas database",
                "category": "work", "updated_at": updated_at,
                "source_type": "decision", "why_saved": "The architecture decision changed.",
                "validity_basis": "Confirmed by the completed migration.",
                "evidence": [{"type": "tool", "reference": "shell_command"}],
            }], session_id="chat-quality")
            self.assertTrue(updated["changed"])
            self.assertIn("PostgreSQL", manager.get_entry(memory_id)["content"])
            self.assertEqual(updated_at, manager.get_entry(memory_id)["updated_at"])

            deleted = manager.apply_model_memory_operations([{
                "action": "delete", "memory_id": memory_id,
                "updated_at": updated_at, "reason": "The stored decision was explicitly withdrawn.",
            }], session_id="chat-quality")
            self.assertTrue(deleted["changed"])
            self.assertIsNone(manager.get_entry(memory_id))

    def test_volatile_model_memory_requires_model_supplied_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            _core, manager = self._manager(directory)
            now = datetime.now().replace(microsecond=0)
            base = {
                "action": "add", "content": "Current service status is degraded",
                "subject": "Service status", "category": "work", "scope": "global",
                "memory_type": "long_term", "importance": 2, "confidence": 0.8,
                "source_type": "web", "created_at": now.isoformat(),
                "updated_at": now.isoformat(), "volatile": True,
                "why_saved": "May matter during the next follow-up.",
                "validity_basis": "Current status page.",
                "evidence": [{"type": "web", "reference": "https://status.example.test"}],
            }
            skipped = manager.apply_model_memory_operations([base])
            self.assertFalse(skipped["changed"])
            accepted = manager.apply_model_memory_operations([{
                **base, "expires_at": (now + timedelta(hours=2)).isoformat(),
            }])
            self.assertTrue(accepted["changed"])
            self.assertIsNotNone(manager.get_entry(accepted["memory_ids"][0])["expires_at"])

    def test_legacy_migration_backs_up_collapses_duplicates_and_archives_tool_traces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            now = datetime.now().isoformat(timespec="seconds")
            base = {
                "type": "long_term", "scope": "global", "subject": "Atlas database",
                "content": "Atlas uses SQLite", "category": "project", "tags": ["auto"],
                "importance": 3, "confidence": 0.7, "source": "conversation",
                "created_at": now, "updated_at": now, "expires_at": None, "metadata": {},
            }
            tool = {
                **base, "id": "mem_tool", "type": "tool", "subject": "file_manager ok",
                "content": "Tool file_manager returned status=ok. Preview: lots of output",
                "source": "tool_observation",
            }
            payload = {
                "schema_version": 1,
                "entries": [{**base, "id": "mem_a"}, {**base, "id": "mem_b"}, tool],
                "archive": [], "pending": [], "stats": {},
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            manager = SmartiMemoryManager(_Core(directory), str(path))
            self.assertEqual(0, manager.memory_stats()["active"])
            self.assertEqual(2, manager.memory_stats()["archive"])
            self.assertTrue(Path(manager.store.path).exists())
            self.assertEqual(1, len(list(Path(directory).glob("memory.pre-memory-v2-*.json"))))
            reasons = {item.get("archive_reason") for item in manager.data["archive"]}
            self.assertEqual({"legacy_conversation_or_tool_trace"}, reasons)


if __name__ == "__main__":
    unittest.main()
