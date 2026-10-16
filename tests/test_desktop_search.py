import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from smarti.desktop_services import WorkspaceScope
from smarti.history import ChatSessionStore, _search_preview


class DesktopSearchTests(unittest.TestCase):
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
