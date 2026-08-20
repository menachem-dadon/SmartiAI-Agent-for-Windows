import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from smarti.agent.browser_runtime import BrowserRuntimeMixin
import smarti.browser_profile as browser_profile
from smarti.browser_profile import (
    BrowserProfileSource,
    discover_browser_profiles,
    import_profile_data,
    read_bookmarks,
    read_cookies,
    read_history,
)
from smarti.config import DEFAULT_SETTINGS
from smarti.chat import ChatWindow
from smarti.workspace_ui import WorkspaceSidebar, WorkspaceWorkbench, classify_workspace_file


class WorkspaceClassificationTests(unittest.TestCase):
    def test_workbench_consolidates_file_types_into_five_viewers(self):
        self.assertEqual(classify_workspace_file("notes.md"), "markdown")
        self.assertEqual(classify_workspace_file("app.py"), "text")
        self.assertEqual(classify_workspace_file("photo.webp"), "image")
        self.assertEqual(classify_workspace_file("meeting.mp4"), "media")
        self.assertEqual(classify_workspace_file("report.pdf"), "pdf")
        self.assertEqual(classify_workspace_file("budget.xlsx"), "office")

    def test_workspace_defaults_to_maximized_with_collapsed_workbench(self):
        preferences = DEFAULT_SETTINGS["ui_preferences"]
        self.assertTrue(preferences["workspace_start_maximized"])
        self.assertTrue(preferences["workspace_workbench_collapsed"])
        self.assertFalse(preferences["workspace_sidebar_collapsed"])
        self.assertTrue(DEFAULT_SETTINGS["browser_embedded_primary"])


class WorkspaceShellUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_work_area_starts_empty_and_accepts_repeated_dynamic_tabs(self):
        class BrowserStub(QWidget):
            def apply_theme(self):
                pass

            def shutdown(self):
                pass

        work_area = WorkspaceWorkbench(object(), QWidget(), browser_panel=BrowserStub())
        self.assertEqual(work_area.tabs.count(), 0)
        self.assertFalse(work_area.tabs.isVisible())
        labels = {button.text() for button in work_area.empty_actions.findChildren(QWidget) if hasattr(button, "text")}
        self.assertTrue({"קבצים", "דפדפן", "מסוף"}.issubset(labels))
        self.assertNotIn("קנבס", labels)
        self.assertNotIn("תוצרים", labels)
        work_area._panel_for_kind = lambda _kind, force_new=False: QWidget()
        work_area.add_panel("files", force_new=True)
        self.assertIsNot(work_area.stack.currentWidget(), work_area.empty_page)
        work_area.add_panel("files", force_new=True)
        self.assertEqual(work_area.tabs.count(), 2)
        work_area.shutdown()
        work_area.deleteLater()

    def test_browser_tab_numbers_reuse_the_lowest_available_number(self):
        class BrowserStub(QWidget):
            def ensure_background_ready(self):
                pass

            def shutdown(self):
                pass

        work_area = WorkspaceWorkbench(object(), QWidget(), browser_panel=BrowserStub())
        work_area._panel_for_kind = lambda _kind, force_new=False: BrowserStub()
        work_area.add_panel("browser", force_new=True)
        work_area.add_panel("browser", force_new=True)
        self.assertEqual([work_area.tabs.tabText(i) for i in range(2)], ["דפדפן", "דפדפן 2"])
        work_area.close_tab(0)
        work_area.add_panel("browser", force_new=True)
        self.assertEqual(
            {work_area.tabs.tabText(i) for i in range(work_area.tabs.count())},
            {"דפדפן", "דפדפן 2"},
        )
        work_area.shutdown()
        work_area.deleteLater()

    def test_collapsed_sidebar_keeps_primary_icons_at_their_open_heights(self):
        history = QWidget()
        history_layout = QVBoxLayout(history)
        history_layout.addWidget(QLabel("history"))
        sidebar = WorkspaceSidebar(history)
        sidebar.resize(286, 800)
        sidebar.show()
        self.app.processEvents()
        open_positions = (
            sidebar.header_host.y(), sidebar.new_chat_btn.y(), sidebar.profile_btn.y()
        )
        open_right_margin = sidebar.width() - (
            sidebar.new_chat_btn.x() + sidebar.new_chat_btn.width()
        )
        sidebar.set_collapsed(True)
        sidebar.resize(58, 800)
        self.app.processEvents()
        self.assertEqual(
            (sidebar.header_host.y(), sidebar.new_chat_btn.y(), sidebar.profile_btn.y()),
            open_positions,
        )
        self.assertEqual(
            sidebar.width() - (sidebar.new_chat_btn.x() + sidebar.new_chat_btn.width()),
            open_right_margin,
        )
        self.assertIn("border: 1px", sidebar.profile_btn.styleSheet())
        sidebar.deleteLater()

    def test_frameless_resize_uses_qt_edges_without_native_message_access(self):
        from PyQt6.QtCore import QPoint, Qt

        self.assertEqual(
            ChatWindow._resize_edges_for_point(QPoint(2, 2), 900, 600),
            Qt.Edge.LeftEdge | Qt.Edge.TopEdge,
        )
        self.assertEqual(
            ChatWindow._resize_edges_for_point(QPoint(898, 598), 900, 600),
            Qt.Edge.RightEdge | Qt.Edge.BottomEdge,
        )
        self.assertEqual(
            ChatWindow._resize_edges_for_point(QPoint(450, 300), 900, 600),
            Qt.Edge(0),
        )
        self.assertNotIn("nativeEvent", ChatWindow.__dict__)


class BrowserProfileImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.local = Path(self.temp.name)
        self.user_data = self.local / "Google" / "Chrome" / "User Data"
        self.profile = self.user_data / "Default"
        (self.profile / "Network").mkdir(parents=True)
        (self.profile / "Preferences").write_text(
            json.dumps({"profile": {"name": "עבודה"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.source = BrowserProfileSource(
            "chrome", "Google Chrome", "עבודה", str(self.user_data), str(self.profile)
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_discovers_named_local_profiles_without_modifying_them(self):
        sources = discover_browser_profiles(str(self.local))
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].profile_name, "עבודה")
        self.assertEqual(sources[0].profile_dir, str(self.profile))

    def test_local_state_names_and_duplicate_profiles_are_disambiguated(self):
        profile_two = self.user_data / "Profile 2"
        profile_two.mkdir()
        (profile_two / "Preferences").write_text(
            json.dumps({"profile": {"name": "Person 1"}}), encoding="utf-8"
        )
        (self.user_data / "Local State").write_text(
            json.dumps(
                {
                    "profile": {
                        "info_cache": {
                            "Default": {"gaia_name": "משתמש 1"},
                            "Profile 2": {"name": "משתמש 1"},
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        sources = discover_browser_profiles(str(self.local))
        self.assertEqual(
            [source.profile_name for source in sources],
            ["משתמש 1 (Default)", "משתמש 1 (Profile 2)"],
        )

    def test_reads_history_bookmarks_and_plaintext_cookies_from_copies(self):
        db = sqlite3.connect(self.profile / "History")
        try:
            db.execute(
                "CREATE TABLE urls(url TEXT, title TEXT, visit_count INTEGER, last_visit_time INTEGER, hidden INTEGER)"
            )
            db.execute(
                "INSERT INTO urls VALUES(?,?,?,?,?)",
                ("https://example.test", "Example", 3, 13380163200000000, 0),
            )
            db.commit()
        finally:
            db.close()
        (self.profile / "Bookmarks").write_text(
            json.dumps(
                {"roots": {"bookmark_bar": {"children": [{"type": "url", "name": "Example", "url": "https://example.test"}]}}}
            ),
            encoding="utf-8",
        )
        db = sqlite3.connect(self.profile / "Network" / "Cookies")
        try:
            db.execute("CREATE TABLE meta(key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY, value LONGVARCHAR)")
            db.execute("INSERT INTO meta VALUES('version','24')")
            db.execute(
                "CREATE TABLE cookies(host_key TEXT, name TEXT, value TEXT, encrypted_value BLOB, path TEXT, "
                "expires_utc INTEGER, is_secure INTEGER, is_httponly INTEGER, last_access_utc INTEGER)"
            )
            db.execute(
                "INSERT INTO cookies VALUES(?,?,?,?,?,?,?,?,?)",
                (".example.test", "session", "plain", b"", "/", 0, 1, 1, 1),
            )
            db.commit()
        finally:
            db.close()

        self.assertEqual(read_history(self.source)[0]["title"], "Example")
        self.assertEqual(read_bookmarks(self.source)[0]["url"], "https://example.test")
        cookies, stats = read_cookies(self.source)
        self.assertEqual(cookies[0]["value"], "plain")
        self.assertEqual(stats["skipped_encrypted"], 0)

        payload = import_profile_data(self.source)
        self.assertEqual(len(payload["history"]), 1)
        self.assertEqual(len(payload["bookmarks"]), 1)
        self.assertEqual(len(payload["cookies"]), 1)

    def test_source_browser_recovery_updates_protected_cookie_counts(self):
        direct = [{"domain": ".example.test", "name": "plain", "path": "/", "value": "1"}]
        recovered = direct + [
            {"domain": ".example.test", "name": "protected", "path": "/", "value": "2"}
        ]
        with (
            patch.object(browser_profile, "read_cookies", return_value=(direct, {"read": 3, "skipped_encrypted": 2})),
            patch.object(browser_profile, "read_cookies_via_source_browser", return_value=recovered),
        ):
            payload = import_profile_data(
                self.source, include_cookies=True, include_history=False, include_bookmarks=False
            )
        self.assertEqual(len(payload["cookies"]), 2)
        self.assertEqual(payload["cookie_stats"]["recovered_via_source_browser"], 1)
        self.assertEqual(payload["cookie_stats"]["unrecovered_encrypted"], 1)


class EmbeddedBrowserRuntimeTests(unittest.TestCase):
    def test_embedded_browser_is_requested_before_external_fallback(self):
        class Core(BrowserRuntimeMixin):
            def __init__(self):
                self.ready = False
                self.requested = []
                self.embedded_browser_activate_callback = self.activate

            def activate(self, url):
                self.requested.append(url)
                self.ready = True

            def _automation_browser_is_ready(self):
                return self.ready

            def _chrome_executable(self):
                raise AssertionError("external fallback should not be queried")

        core = Core()
        ok, error = core._ensure_automation_browser("https://example.test")
        self.assertTrue(ok)
        self.assertIsNone(error)
        self.assertEqual(core.requested, ["https://example.test"])


if __name__ == "__main__":
    unittest.main()
