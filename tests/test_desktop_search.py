import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.desktop_services import WorkspaceScope
from smarti.history import ChatSessionStore, _search_preview
from smarti.local_gateway import SmartiLocalGateway


class DesktopSearchTests(unittest.TestCase):
    def test_gateway_message_projection_keeps_legacy_conversation_list_and_limits_separate_hits(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            store.add_turn("budget first", "budget second")
            gateway = object.__new__(SmartiLocalGateway)
            gateway.core = SimpleNamespace(chat_store=store)
            gateway._ok = lambda request, data: data
            legacy = asyncio.run(gateway._conversations(SimpleNamespace(method="GET", query={"q": "budget"})))
            separate = asyncio.run(gateway._conversations(SimpleNamespace(method="GET", query={"q": "budget", "matches": "messages", "limit": "9"})))
            self.assertEqual(len(legacy["items"]), 1)
            self.assertEqual(len(separate["items"]), 2)
            self.assertEqual(separate["attention_items"], [])
            self.assertEqual({row["match_ordinal"] for row in separate["items"]}, {0, 1})

    def test_message_search_returns_separate_hits_with_addressable_ordinals_and_title_only_hit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            session = store.active_session()["id"]
            store.rename_session(session, "תקציב")
            store.add_turn("תקציב לרבעון הראשון", "בנינו תקציב חדש", session_id=session)
            store.add_turn("עוד תקציב להמשך", "סיכום", session_id=session)
            with mock.patch.object(store, "_session", side_effect=AssertionError("search must not load whole sessions")):
                rows = store.search_messages("תקציב")
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["match_kind"], "title")
            self.assertIsInstance(rows[0]["pinned"], bool)
            self.assertEqual(rows[0]["search_preview"], "")
            messages = [row for row in rows if row["match_kind"] == "content"]
            self.assertEqual({row["match_ordinal"] for row in messages}, {0, 1, 2})
            self.assertEqual(len({row["match_id"] for row in rows}), 4)
            self.assertEqual(len(store.list_sessions("תקציב")), 1)

    def test_message_search_caps_at_nine_prioritizes_exact_titles_and_diversifies_equal_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            exact = store.active_session()["id"]
            store.rename_session(exact, "budget")
            for index in range(8):
                store.add_turn(f"budget item {index}", f"budget result {index}", session_id=exact)
            other = store.create_session(False)["id"]
            store.rename_session(other, "Other conversation")
            store.add_turn("budget for a different project", "ready", session_id=other)
            rows = store.search_messages("budget", limit=100)
            self.assertEqual(len(rows), 9)
            self.assertEqual(rows[0]["id"], exact)
            self.assertEqual(rows[0]["match_kind"], "title")
            self.assertIn(other, [row["id"] for row in rows[:3]])
            self.assertEqual(store.search_messages(""), [])

    def test_message_search_matches_reordered_words_and_uses_conservative_title_typo_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            store.rename_session(store.active_session()["id"], "Release planning")
            store.add_turn("פתיחה " * 80 + "תקציב לפרויקט שנתי", "הושלם")
            rows = store.search_messages("שנתי תקציב")
            self.assertEqual(rows[0]["match_kind"], "content")
            self.assertIn("תקציב", rows[0]["search_preview"])
            self.assertEqual(store.search_messages("plannng")[0]["match_kind"], "title")
            self.assertEqual(store.search_messages("z"), [])

    def test_message_search_does_not_return_matches_from_internal_metadata_or_ui_only_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            store.add_turn("visible", "reply", user_metadata={"internal": "private-needle-725"})
            store.add_turn("ui-only-needle-729", "reply", user_metadata={"ui_only": True})
            self.assertEqual(store.search_messages("private-needle-725"), [])
            self.assertEqual(store.search_messages("ui-only-needle-729"), [])

    def test_search_preview_finds_older_content_without_changing_last_message_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            session = store.active_session()["id"]
            text = "פתיחה " * 80 + "תקציב-מיוחד" + " הסבר" * 80
            store.add_turn(text, "תשובה ראשונה", session_id=session)
            store.add_turn("בקשה מאוחרת", "הודעה אחרונה", session_id=session)
            with mock.patch.object(store, "_session", side_effect=AssertionError("literal search must stay batched")):
                rows = store.list_sessions("תקציב-מיוחד")
            self.assertEqual(rows[0]["id"], session)
            self.assertIn("תקציב-מיוחד", rows[0]["search_preview"])
            self.assertTrue(rows[0]["search_preview"].startswith("…"))
            self.assertLess(len(rows[0]["search_preview"]), 215)
            self.assertEqual(rows[0]["preview"], "הודעה אחרונה")
            self.assertEqual(store.messages(session)[0]["content"], text)

    def test_search_preview_includes_attachment_names_and_literal_punctuation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChatSessionStore(str(Path(directory) / "chats.json"))
            store.add_turn("מצורף", "תשובה", user_metadata={"attachments": [{"name": "budget[2026]+.xlsx"}]})
            self.assertIn("budget[2026]+.xlsx", store.list_sessions("budget[2026]+")[0]["search_preview"])
            self.assertEqual(_search_preview("א" * 300, "א" * 230), "א" * 230 + "…")

    def test_artifact_search_reaches_beyond_recent_200_and_matches_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(230):
                (root / f"recent-{index:03}.txt").write_text("recent", encoding="utf-8")
            target = root / "reports" / "תקציב[2026]+.xlsx"
            target.parent.mkdir()
            target.write_bytes(b"fixture")
            os.utime(target, (1, 1))
            scope = WorkspaceScope(SimpleNamespace(settings={}, _sandbox_enabled=lambda: False, _default_output_dir=lambda: directory))
            self.assertNotIn("reports/תקציב[2026]+.xlsx", [item["path"] for item in scope.artifacts()["items"]])
            result = scope.artifacts("תקציב[2026]+")
            self.assertEqual([item["path"] for item in result["items"]], ["reports/תקציב[2026]+.xlsx"])
            self.assertEqual(scope.artifacts("REPORTS/")["items"], result["items"])
            self.assertFalse(result["truncated"])
            self.assertEqual(scope.artifacts("missing")["items"], [])

    def test_artifact_search_skips_links_and_bounds_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scope = WorkspaceScope(SimpleNamespace(settings={}, _sandbox_enabled=lambda: False, _default_output_dir=lambda: directory))
            (root / "report.txt").write_text("safe", encoding="utf-8")
            with mock.patch("smarti.desktop_services.os.path.islink", side_effect=lambda path: str(path).endswith("report.txt")):
                self.assertEqual(scope.artifacts("report")["items"], [])
            with mock.patch("smarti.desktop_services.os.walk", return_value=iter([(directory, [], ["missing"] * 10001)])):
                self.assertTrue(scope.artifacts("absent")["truncated"])


if __name__ == "__main__":
    unittest.main()
