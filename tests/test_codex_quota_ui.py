"""Focused visual-geometry tests for the Codex quota model menu."""
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QPushButton, QWidgetAction

from smarti.chat import ChatWindow


class _PopupHost(QMainWindow):
    _add_codex_quota_menu_item = ChatWindow._add_codex_quota_menu_item
    _current_model_provider = ChatWindow._current_model_provider
    _on_codex_quota_refreshed = ChatWindow._on_codex_quota_refreshed
    _refresh_codex_quota_if_active = ChatWindow._refresh_codex_quota_if_active
    _popup_menu_near_button = ChatWindow._popup_menu_near_button
    _clear_quick_menu_reopen_guard = ChatWindow._clear_quick_menu_reopen_guard
    _clear_open_quick_menu = ChatWindow._clear_open_quick_menu
    _on_quick_menu_about_to_hide = ChatWindow._on_quick_menu_about_to_hide

    def __init__(self, provider="openai_codex_signin"):
        super().__init__()
        self.core = SimpleNamespace(settings={"api_mode": provider}, mode=provider)
        self._open_quick_menu = None
        self._open_quick_menu_button = None
        self._suppress_quick_menu_button = None
        self._codex_quota_worker = None
        self._codex_quota_widget = None
        self._codex_quota_cache = None
        self._codex_quota_cache_at = 0.0

    @staticmethod
    def _quick_menu_button_contains_cursor(_button):
        return False


class CodexQuotaMenuUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.host = _PopupHost()
        self.host.resize(570, 700)
        self.host.move(100, 40)

    def tearDown(self):
        current = self.host._open_quick_menu
        self.host._open_quick_menu = None
        if current is not None:
            current.hide()
            current.deleteLater()
        self.host.hide()
        self.host.deleteLater()
        self.app.processEvents()

    def test_model_menu_is_centered_on_window_width(self):
        button = QPushButton("gpt 5.6 sol", self.host)
        button.setGeometry(167, 20, 236, 48)
        self.host.show()
        self.app.processEvents()
        menu = QMenu(self.host)
        menu.setMinimumWidth(398)
        for label in ("עוצמת חשיבה", "נמוכה", "בינונית", "גבוהה", "מקסימלית"):
            menu.addAction(label)

        opened = self.host._popup_menu_near_button(menu, button, center_horizontally=True)
        self.app.processEvents()

        self.assertTrue(opened)
        self.assertLessEqual(
            abs(self.host.frameGeometry().center().x() - menu.frameGeometry().center().x()),
            1,
        )

    def test_quota_widget_is_added_only_for_the_active_codex_provider(self):
        self.host._start_codex_quota_refresh = mock.Mock()
        non_codex_menu = QMenu(self.host)
        self.host.core.settings["api_mode"] = "gemini"
        self.assertFalse(self.host._add_codex_quota_menu_item(non_codex_menu))
        self.assertFalse(any(isinstance(action, QWidgetAction) for action in non_codex_menu.actions()))

        self.host.core.settings["api_mode"] = "openai_codex_signin"
        self.host._codex_quota_cache = {
            "available": True,
            "five_hour": {"remaining_percent": 63},
            "weekly": {"remaining_percent": 94},
        }
        self.host._codex_quota_cache_at = time.monotonic()
        codex_menu = QMenu(self.host)
        self.assertTrue(self.host._add_codex_quota_menu_item(codex_menu))
        self.assertEqual(
            sum(isinstance(action, QWidgetAction) for action in codex_menu.actions()),
            1,
        )

    def test_external_usage_poll_runs_only_while_codex_is_active(self):
        self.host._start_codex_quota_refresh = mock.Mock()
        self.host.core.settings["api_mode"] = "gemini"
        self.assertFalse(self.host._refresh_codex_quota_if_active())
        self.host._start_codex_quota_refresh.assert_not_called()

        self.host.core.settings["api_mode"] = "openai_codex_signin"
        self.assertTrue(self.host._refresh_codex_quota_if_active())
        self.host._start_codex_quota_refresh.assert_called_once_with()

        self.host._codex_quota_cache = {"available": True}
        self.host._codex_quota_cache_at = time.monotonic()
        self.assertFalse(self.host._refresh_codex_quota_if_active(min_age=15))

    def test_external_poll_result_updates_an_open_quota_widget(self):
        self.host._start_codex_quota_refresh = mock.Mock()
        self.host._codex_quota_cache = {
            "available": True,
            "five_hour": {"remaining_percent": 63},
            "weekly": {"remaining_percent": 94},
        }
        self.host._codex_quota_cache_at = time.monotonic()
        menu = QMenu(self.host)
        self.host._add_codex_quota_menu_item(menu)
        worker = object()
        self.host._codex_quota_worker = worker

        self.host._on_codex_quota_refreshed(worker, {
            "available": True,
            "five_hour": {"remaining_percent": 52},
            "weekly": {"remaining_percent": 83},
        }, "")

        self.assertEqual(self.host._codex_quota_widget.rows["five_hour"][0].text(), "52% נותרו")
        self.assertEqual(self.host._codex_quota_widget.rows["weekly"][0].text(), "83% נותרו")


if __name__ == "__main__":
    unittest.main()
