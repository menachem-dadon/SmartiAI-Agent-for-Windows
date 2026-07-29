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
    def test_ambiguous_old_action_is_preserved_but_not_always_injected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            expired_at = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
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
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
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
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
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

            self.assertIn("קוראים לי דנה", context)
            self.assertNotIn("הקובץ הכחול", context)
            self.assertTrue(any(
                entry.get("id") == "mem_old_action"
                for entry in manager.data["entries"]
            ))
            self.assertTrue(any(
                entry.get("id") == "mem_expired"
                for entry in manager.data["archive"]
            ))
            old_action = next(
                entry for entry in manager.data["entries"]
                if entry.get("id") == "mem_old_action"
            )
            self.assertFalse(old_action["metadata"]["profile_eligible"])
            self.assertFalse(old_action["metadata"]["automatic_context_eligible"])
            self.assertNotIn(
                "old action",
                manager.build_prompt_context("old action"),
            )

            searchable = manager.tool_search_text("הקובץ הכחול")
            self.assertIn("הקובץ הכחול", searchable)

            self.assertTrue(manager.forget("mem_expired"))
            self.assertFalse(any(
                entry.get("id") == "mem_expired"
                for entry in manager.data["archive"]
            ))

    def test_future_durable_preference_is_profile_eligible_without_raw_request_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SmartiMemoryManager(
                _MemoryCore(),
                str(Path(directory) / "memory.json"),
            )
            manager.capture_critical_user_details(
                "מעכשיו תמיד תענה לי בעברית",
                source="critical_preflight",
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
                entry.get("metadata", {}).get("profile_eligible")
                and "עברית" in entry.get("content", "")
                for entry in preference
            ))
            self.assertFalse(any(
                entry.get("type") == "user"
                and "הקובץ הזה" in entry.get("content", "")
                for entry in manager.data["entries"]
            ))
            self.assertTrue(any(
                entry.get("type") == "long_term"
                and "הקובץ הזה" in entry.get("content", "")
                for entry in manager.data["entries"]
            ))

    def test_previous_one_time_exchange_requires_explicit_continuity(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SmartiMemoryManager(
                _MemoryCore(),
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
            self.assertIn("מזג האוויר מחר באלעד", continued)
            self.assertTrue(any(
                entry.get("metadata", {}).get("continuity_only")
                for entry in manager.data["entries"]
                if entry.get("type") in {"short_term", "tool"}
            ))

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
            self.assertIn(
                "מזג האוויר מחר באלעד",
                manager.build_prompt_context("המשך את בקשת מזג האוויר הקודמת באלעד"),
            )
            migrated = next(
                entry for entry in manager.data["entries"]
                if entry.get("id") == "mem_weather_v3"
            )
            self.assertFalse(migrated["metadata"]["automatic_context_eligible"])
            self.assertTrue(migrated["metadata"]["continuity_only"])
            self.assertEqual(migrated["content"], payload["entries"][0]["content"])

    def test_durable_project_context_remains_automatically_retrievable(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = SmartiMemoryManager(
                _MemoryCore(),
                str(Path(directory) / "memory.json"),
            )
            manager.auto_capture_turn(
                "הפרויקט Atlas מבוסס FastAPI והחלטת הארכיטקטורה היא מסד נתונים מקומי",
                "הבנתי את מבנה הפרויקט והארכיטקטורה.",
            )

            context = manager.build_prompt_context("מהי הארכיטקטורה של פרויקט Atlas?")

            self.assertIn("FastAPI", context)
            project_entry = next(
                entry for entry in manager.data["entries"]
                if "FastAPI" in entry.get("content", "")
            )
            self.assertTrue(project_entry["metadata"]["automatic_context_eligible"])
            self.assertFalse(project_entry["metadata"]["continuity_only"])


if __name__ == "__main__":
    unittest.main()
