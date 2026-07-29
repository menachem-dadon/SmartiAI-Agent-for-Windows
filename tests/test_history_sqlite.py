import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from smarti.history import ChatSessionStore, DEFAULT_CHAT_TITLE


class ChatHistorySqliteTests(unittest.TestCase):
    def test_legacy_json_is_imported_once_and_left_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy_path = Path(directory) / "smarti_chats.json"
            payload = {
                "schema_version": 1,
                "active_session_id": "session-a",
                "future_root_field": {"kept": True},
                "sessions": [{
                    "id": "session-a",
                    "title": "כותרת ישנה",
                    "created_at": "2026-01-01T10:00:00",
                    "updated_at": "2026-01-01T10:01:00",
                    "pinned": True,
                    "title_generated": True,
                    "title_user_edited": False,
                    "future_session_field": {"version": 7},
                    "context": {"provider": "gemini", "future_context": [1, 2, 3]},
                    "messages": [{
                        "role": "user",
                        "content": "שלום",
                        "created_at": "2026-01-01T10:00:00",
                        "metadata": {"attachments": [{"name": "מסמך.txt"}]},
                        "future_message_field": "preserved",
                    }, {
                        "role": "assistant",
                        "content": "שלום גם לך",
                        "created_at": "2026-01-01T10:01:00",
                        "metadata": {},
                    }],
                }],
            }
            legacy_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            original_bytes = legacy_path.read_bytes()

            store = ChatSessionStore(str(legacy_path))
            active = store.active_session()

            self.assertEqual(active["id"], "session-a")
            self.assertEqual(active["future_session_field"], {"version": 7})
            self.assertEqual(active["messages"][0]["future_message_field"], "preserved")
            self.assertEqual(active["context"]["future_context"], [1, 2, 3])
            self.assertTrue(Path(store.path).is_file())
            self.assertEqual(legacy_path.read_bytes(), original_bytes)
            with closing(sqlite3.connect(store.path)) as connection:
                root_extra = json.loads(connection.execute(
                    "SELECT value FROM store_meta WHERE key='legacy_root_extra_json'"
                ).fetchone()[0])
            self.assertEqual(root_extra["future_root_field"], {"kept": True})

            reopened = ChatSessionStore(str(legacy_path))
            self.assertEqual(len(reopened.messages("session-a")), 2)
            self.assertEqual(legacy_path.read_bytes(), original_bytes)

    def test_concurrent_turn_writes_are_serialized_without_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            session_id = store.active_session()["id"]
            threads = [
                threading.Thread(
                    target=store.add_turn,
                    args=(f"user-{index}", f"assistant-{index}"),
                    kwargs={
                        "session_id": session_id,
                        "context": {"last_index": index, "future": {"ok": True}},
                    },
                )
                for index in range(12)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            messages = store.messages(session_id)
            self.assertEqual(len(messages), 24)
            self.assertEqual(
                {message["content"] for message in messages if message["role"] == "user"},
                {f"user-{index}" for index in range(12)},
            )
            self.assertTrue(store.active_session()["context"]["future"]["ok"])

    def test_background_title_never_overwrites_user_title(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            session_id = store.active_session()["id"]
            store.add_turn("בקשה", "תשובה", session_id=session_id)
            self.assertEqual(store.active_session()["title"], DEFAULT_CHAT_TITLE)
            self.assertTrue(store.apply_generated_title(session_id, "כותרת מודל"))
            self.assertEqual(store.active_session()["title"], "כותרת מודל")

            self.assertTrue(store.rename_session(session_id, "כותרת המשתמש"))
            self.assertFalse(store.apply_generated_title(session_id, "אסור לדרוס"))
            self.assertEqual(store.active_session()["title"], "כותרת המשתמש")

    def test_message_pages_return_latest_then_older_without_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            session_id = store.active_session()["id"]
            for index in range(60):
                store.add_turn(
                    f"user-{index:03d}",
                    f"assistant-{index:03d}",
                    session_id=session_id,
                )

            metadata = store.active_session_metadata()
            latest = store.messages_page(session_id, limit=32)
            older = store.messages_page(
                session_id,
                before_ordinal=latest["next_before_ordinal"],
                limit=24,
            )

            self.assertEqual(metadata["message_count"], 120)
            self.assertEqual(len(metadata["messages"]), 0)
            self.assertEqual(len(latest["messages"]), 32)
            self.assertEqual(latest["messages"][0]["content"], "user-044")
            self.assertEqual(latest["messages"][-1]["content"], "assistant-059")
            self.assertTrue(latest["has_older"])
            self.assertEqual(latest["older_count"], 88)
            self.assertEqual(len(older["messages"]), 24)
            self.assertEqual(older["messages"][0]["content"], "user-032")
            self.assertEqual(older["messages"][-1]["content"], "assistant-043")
            self.assertEqual(len(store.messages(session_id)), 120)


if __name__ == "__main__":
    unittest.main()
