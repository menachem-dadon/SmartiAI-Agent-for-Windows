import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from smarti.config import DEFAULT_SETTINGS
from smarti.managers import SmartiMemoryManager


class _MemoryCore:
    def __init__(self):
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.logged_usage = []

    def _save_settings(self):
        return None

    def _log_usage(self, model, usage):
        self.logged_usage.append((model, usage))


class MemoryProfilePolicyTests(unittest.TestCase):
    def _model_add(self, manager, content, *, category="work", scope="global", source_type="user"):
        now = datetime.now().replace(microsecond=0).isoformat()
        result = manager.apply_model_memory_operations([{
            "action": "add", "content": content, "subject": content[:60],
            "category": category, "scope": scope,
            "memory_type": "user" if scope == "user" else "long_term",
            "importance": 4, "confidence": 0.9, "source_type": source_type,
            "created_at": now, "updated_at": now, "expires_at": None,
            "volatile": False, "tags": [category],
            "why_saved": "Reusable future context selected by the model.",
            "validity_basis": "Current turn evidence.", "evidence": [],
        }])
        self.assertTrue(result["changed"])
        return result["memory_ids"][0]

    def test_ambiguous_old_action_is_preserved_but_not_always_injected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            expired_at = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
            now_at = datetime.now().isoformat(timespec="seconds")
            payload = {
                "schema_version": 1,
                "entries": [{
                    "id": "mem_old_action",
                    "type": "user",
                    "scope": "global",
                    "subject": "old action",
                    "content": "User said: חשוב לי שתתקן עכשיו את הקובץ הכחול",
                    "tags": ["auto", "user"],
                    "importance": 5,
                    "confidence": 0.7,
                    "source": "conversation",
                    "created_at": now_at,
                    "updated_at": now_at,
                    "expires_at": None,
                    "fingerprint": "old-action",
                    "metadata": {},
                }, {
                    "id": "mem_identity",
                    "type": "user",
                    "scope": "global",
                    "subject": "User identity",
                    "content": "User identity: קוראים לי דנה",
                    "tags": ["auto", "critical", "identity"],
                    "importance": 5,
                    "confidence": 0.9,
                    "source": "critical_preflight",
                    "created_at": now_at,
                    "updated_at": now_at,
                    "expires_at": None,
                    "fingerprint": "identity",
                    "metadata": {"category": "identity"},
                }, {
                    "id": "mem_expired",
                    "type": "short_term",
                    "scope": "global",
                    "subject": "expired but preserved",
                    "content": "פרט רציפות ישן שאסור לאבד",
                    "tags": ["auto"],
                    "importance": 2,
                    "confidence": 0.6,
                    "source": "conversation",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                    "expires_at": expired_at,
                    "fingerprint": "expired",
                    "metadata": {},
                }],
                "stats": {},
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            manager = SmartiMemoryManager(_MemoryCore(), str(path))
            context = manager.build_prompt_context("שלום")

            self.assertNotIn("קוראים לי דנה", context)
            self.assertIn("קוראים לי דנה", manager.build_prompt_context("מה השם שלי?"))
            self.assertNotIn("הקובץ הכחול", context)
            self.assertTrue(any(
                entry.get("id") == "mem_old_action"
                for entry in manager.data["archive"]
            ))
            self.assertTrue(any(
                entry.get("id") == "mem_expired"
                for entry in manager.data["archive"]
            ))
            old_action = next(
                entry for entry in manager.data["archive"]
                if entry.get("id") == "mem_old_action"
            )
            self.assertEqual("legacy_conversation_or_tool_trace", old_action["archive_reason"])
            self.assertNotIn(
                "old action",
                manager.build_prompt_context("old action"),
            )

            self.assertEqual("NO_MEMORY_RESULTS", manager.tool_search_text("הקובץ הכחול"))

            self.assertTrue(manager.forget("mem_expired"))
            self.assertFalse(any(
                entry.get("id") == "mem_expired"
                for entry in manager.data["archive"]
            ))

    def test_future_durable_preference_is_active_without_review_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SmartiMemoryManager(
                _MemoryCore(),
                str(Path(directory) / "memory.json"),
            )
            self._model_add(
                manager, "המשתמשת מעדיפה שתמיד יענו לה בעברית",
                category="preference", scope="user",
            )
            manager.auto_capture_turn(
                "חשוב לי שתבדוק עכשיו את הקובץ הזה",
                "בדקתי.",
            )

            preference = [
                entry for entry in manager.data["entries"]
                if entry.get("type") == "user"
            ]
            self.assertTrue(any(
                "עברית" in manager._plain_content(entry)
                for entry in preference
            ))
            self.assertFalse(any(
                entry.get("type") == "user"
                and "הקובץ הזה" in entry.get("content", "")
                for entry in manager.data["entries"]
            ))
            self.assertEqual([], manager.data["pending"])

    def test_previous_one_time_exchange_requires_explicit_continuity(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _MemoryCore()
            manager = SmartiMemoryManager(
                core,
                str(Path(directory) / "memory.json"),
            )
            manager.auto_capture_turn(
                "מה מזג האוויר מחר באלעד? כתוב את התוצאה בקובץ בשולחן העבודה",
                "בדקתי את התחזית ושמרתי weather.txt בשולחן העבודה.",
                tool_records=[{
                    "tool": "web_manager",
                    "status": "ok",
                    "preview": "Weather for Elad tomorrow",
                }],
            )

            unrelated = manager.build_prompt_context(
                "צור תיקייה בשולחן העבודה ובנה בה אתר HTML של Windows 11"
            )
            continued = manager.build_prompt_context(
                "המשך את בקשת מזג האוויר הקודמת באלעד"
            )

            self.assertNotIn("מזג האוויר מחר באלעד", unrelated)
            self.assertNotIn("Weather for Elad", unrelated)
            self.assertNotIn("מזג האוויר מחר באלעד", continued)
            self.assertFalse(any(entry.get("type") in {"short_term", "tool"} for entry in manager.data["entries"]))
            self.assertEqual([], manager.data["pending"])

    def test_version_three_conversation_trace_is_reclassified_without_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            payload = {
                "schema_version": 2,
                "entries": [{
                    "id": "mem_weather_v3",
                    "type": "short_term",
                    "scope": "global",
                    "subject": "מזג אוויר באלעד",
                    "content": (
                        "Recent exchange. User request: מה מזג האוויר מחר באלעד? "
                        "כתוב את התוצאה בקובץ בשולחן העבודה"
                    ),
                    "tags": ["auto", "conversation"],
                    "importance": 2,
                    "confidence": 0.55,
                    "source": "conversation",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "expires_at": None,
                    "fingerprint": "weather-v3",
                    "metadata": {
                        "automatic_context_eligible": True,
                        "profile_policy_version": 3,
                    },
                }],
                "archive": [],
                "stats": {"profile_policy_version": 3},
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            manager = SmartiMemoryManager(_MemoryCore(), str(path))

            self.assertNotIn(
                "מזג האוויר מחר באלעד",
                manager.build_prompt_context("צור אתר HTML בשולחן העבודה"),
            )
            self.assertNotIn(
                "מזג האוויר מחר באלעד",
                manager.build_prompt_context("המשך את בקשת מזג האוויר הקודמת באלעד"),
            )
            migrated = next(
                entry for entry in manager.data["archive"]
                if entry.get("id") == "mem_weather_v3"
            )
            self.assertEqual("legacy_conversation_or_tool_trace", migrated["archive_reason"])
            self.assertEqual(manager._plain_content(migrated), payload["entries"][0]["content"])

    def test_durable_project_context_remains_automatically_retrievable(self):
        with tempfile.TemporaryDirectory() as directory:
            core = _MemoryCore()
            core.current_working_directory = directory
            manager = SmartiMemoryManager(
                core,
                str(Path(directory) / "memory.json"),
            )
            self._model_add(
                manager,
                "העבודה על Atlas מבוססת FastAPI והחלטת הארכיטקטורה היא מסד נתונים מקומי",
                category="work", scope="global", source_type="decision",
            )

            context = manager.build_prompt_context("מהי הארכיטקטורה של פרויקט Atlas?")

            self.assertIn("FastAPI", context)
            project_entry = next(
                entry for entry in manager.data["entries"]
                if "FastAPI" in manager._plain_content(entry)
            )
            self.assertTrue(project_entry["metadata"]["automatic_context_eligible"])
            self.assertEqual("model_semantic_decision", project_entry["metadata"]["capture"])
            self.assertEqual("global", project_entry["scope"])
            self.assertEqual([], manager.data["pending"])


if __name__ == "__main__":
    unittest.main()
