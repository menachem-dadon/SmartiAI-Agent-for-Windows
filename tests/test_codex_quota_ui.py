"""Focused visual-geometry tests for the Codex quota model menu."""
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMenu, QPushButton, QStackedWidget, QWidgetAction

from smarti import chat as chat_module
from smarti.chat import ChatHistoryPage, ChatWindow, CodexQuotaWidget
from smarti.ui_controls import SearchableModelComboBox
from smarti.ui_pages import SettingsPage


class _PopupHost(QMainWindow):
    _add_codex_quota_menu_item = ChatWindow._add_codex_quota_menu_item
    _current_model_provider = ChatWindow._current_model_provider
    _on_codex_quota_refreshed = ChatWindow._on_codex_quota_refreshed
    _refresh_codex_quota_if_active = ChatWindow._refresh_codex_quota_if_active
    _popup_menu_near_button = ChatWindow._popup_menu_near_button
    _clear_quick_menu_reopen_guard = ChatWindow._clear_quick_menu_reopen_guard
    _clear_open_quick_menu = ChatWindow._clear_open_quick_menu
    _on_quick_menu_about_to_hide = ChatWindow._on_quick_menu_about_to_hide
    _normalized_favorite_models = ChatWindow._normalized_favorite_models
    refresh_favorite_model_controls = ChatWindow.refresh_favorite_model_controls

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

    def test_header_model_menu_stays_anchored_below_its_button(self):
        button = QPushButton("gpt 5.6 sol", self.host)
        button.setGeometry(167, 20, 236, 48)
        self.host.show()
        self.app.processEvents()
        menu = QMenu(self.host)
        menu.setMinimumWidth(398)
        for index in range(30):
            menu.addAction(f"model {index}")
        expected_y = button.mapToGlobal(QPoint(0, button.height() + 4)).y()

        opened = self.host._popup_menu_near_button(
            menu,
            button,
            center_horizontally=True,
            anchor_below=True,
        )
        self.app.processEvents()

        self.assertTrue(opened)
        self.assertEqual(menu.pos().y(), expected_y)
        self.assertLessEqual(menu.frameGeometry().bottom(), self.host.frameGeometry().bottom() - 8)

    def test_absent_five_hour_window_is_hidden(self):
        widget = CodexQuotaWidget()
        widget.show()
        widget.set_quota_data({
            "available": True,
            "plan_type": "plus",
            "five_hour": None,
            "weekly": {"remaining_percent": 90, "window_minutes": 10080},
        })
        self.app.processEvents()

        self.assertTrue(widget.row_widgets["five_hour"].isHidden())
        self.assertFalse(widget.row_widgets["weekly"].isHidden())
        widget.deleteLater()

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

    def test_refresh_does_not_restore_an_unfavorited_current_model(self):
        self.host.core.settings.update({
            "api_mode": "gemini",
            "selected_gemini_model": "gemini-current",
            "favorite_models": [],
        })
        self.host.favorite_model_btn = QPushButton(self.host)
        self.host.favorite_model_btn.setProperty("smartiModelPickerLocation", "header")
        self.host._favorite_model_label = lambda _provider, model: model
        self.host._fit_header_model_button = mock.Mock()

        self.host.refresh_favorite_model_controls()

        self.assertEqual(self.host.core.settings["favorite_models"], [])
        self.assertTrue(self.host.favorite_model_btn.isHidden())


class ChatHistoryRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.stack = QStackedWidget()
        self.main_window = SimpleNamespace(stacked_widget=self.stack)
        self.page = ChatHistoryPage(SimpleNamespace(), self.main_window)

    def tearDown(self):
        self.page.deleteLater()
        self.stack.deleteLater()
        self.app.processEvents()

    def test_splash_labels_installer_and_portable_builds_separately(self):
        with mock.patch.object(chat_module, "detect_installation_kind", return_value="installer"):
            self.assertEqual(chat_module._splash_runtime_label(), "מותקן")
        with mock.patch.object(chat_module, "detect_installation_kind", return_value="portable"):
            self.assertEqual(chat_module._splash_runtime_label(), "נייד")
        with mock.patch.object(chat_module, "detect_installation_kind", return_value="source"):
            self.assertEqual(chat_module._splash_runtime_label(), "מקור")

    def test_pinned_history_row_has_a_persistent_pin_indicator(self):
        pinned = self.page._compact_session_row(
            {
                "id": "pinned-session",
                "title": "שיחה מוצמדת",
                "updated_at": "2026-07-21T12:00:00",
                "message_count": 3,
                "pinned": True,
            },
            active_id="",
        )
        unpinned = self.page._compact_session_row(
            {
                "id": "ordinary-session",
                "title": "שיחה רגילה",
                "updated_at": "2026-07-21T12:00:00",
                "message_count": 1,
                "pinned": False,
            },
            active_id="",
        )

        indicator = pinned.findChild(QLabel, "PinnedSessionIndicator")
        menu_button = pinned.findChild(QPushButton, "SessionActionsButton")
        self.assertIsNotNone(indicator)
        self.assertIsNotNone(menu_button)
        self.assertEqual(indicator.toolTip(), "שיחה מוצמדת")
        self.assertTrue(indicator.text() or (indicator.pixmap() and not indicator.pixmap().isNull()))
        self.assertIsNone(unpinned.findChild(QLabel, "PinnedSessionIndicator"))

        pinned.resize(520, pinned.sizeHint().height())
        pinned.show()
        self.app.processEvents()
        self.assertLessEqual(abs(indicator.geometry().center().y() - menu_button.geometry().center().y()), 1)


class ContextCompactionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_compaction_uses_a_named_tool_row_and_theme_aware_icon_stem(self):
        tool = {"action": "context_compaction", "arguments": {"scope": "active_task"}}

        self.assertEqual(chat_module._agent_tool_display_name(tool), "דחיסת הקשר")
        self.assertIn("agent_tool_context_compaction", chat_module._agent_tool_icon_names(tool))

    def test_compaction_group_is_visible_without_expandable_tool_details(self):
        group = chat_module.AgentToolGroupWidget(450)
        activity = {
            "action": "context_compaction",
            "event_id": "compact-1",
            "status": "running",
        }

        group.start_standalone_activity(activity, "דוחס את ההקשר…")

        self.assertTrue(group.standalone_activity)
        self.assertTrue(group.isVisible())
        self.assertEqual(group.status_label.text(), "דוחס את ההקשר…")
        self.assertFalse(group.arrow_label.isVisible())
        self.assertFalse(group.tools_container.isVisible())
        self.assertEqual(group.tool_widgets, [])
        group.toggle_details()
        self.assertFalse(group.details_expanded)

        group.finish_standalone_activity(
            {**activity, "status": "ok"},
            "דחיסת ההקשר הושלמה",
        )
        self.assertEqual(group.status_label.text(), "דחיסת ההקשר הושלמה")
        self.assertFalse(group.arrow_label.isVisible())
        group.deleteLater()

    def test_compaction_event_gets_its_own_group_before_later_tools(self):
        bubble = chat_module.MessageBubble("", is_user=False, parent_width=500)
        activity = {
            "action": "context_compaction",
            "event_id": "compact-2",
            "status": "running",
        }

        bubble.handle_agent_event({
            "type": "tool_group_start",
            "group": activity,
            "text": "דוחס את ההקשר…",
        })
        bubble.handle_agent_event({
            "type": "tool_group_finish",
            "group": {**activity, "status": "ok"},
            "text": "דחיסת ההקשר הושלמה",
        })
        bubble.handle_agent_event({
            "type": "tool_start",
            "tools": [{"action": "email_manager", "event_id": "tool-1"}],
        })

        self.assertEqual(len(bubble.agent_process_groups), 2)
        self.assertTrue(bubble.agent_process_groups[0].standalone_activity)
        self.assertFalse(bubble.agent_process_groups[1].standalone_activity)
        self.assertEqual(bubble.agent_process_groups[0].tool_widgets, [])
        self.assertEqual(len(bubble.agent_process_groups[1].tool_widgets), 1)
        bubble.deleteLater()


class FavoriteModelRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_explicit_model_commit_marks_that_model_as_favorite(self):
        page = SimpleNamespace(
            core=SimpleNamespace(settings={}),
            provider_combo=SimpleNamespace(currentText=lambda: "groq"),
            _ensure_model_favorite=mock.Mock(),
            _schedule_autosave=mock.Mock(),
        )

        SettingsPage._on_model_committed(page, "llama-current")

        page._ensure_model_favorite.assert_called_once_with("groq", "llama-current", save=False)
        page._schedule_autosave.assert_called_once_with()

    def test_provider_selection_favorites_its_automatically_selected_model(self):
        combo = SearchableModelComboBox()
        page = SimpleNamespace(
            core=SimpleNamespace(settings={"selected_groq_model": "llama-default"}),
            model_combo=combo,
            _suppress_autosave=False,
            _favorite_model_on_populate_provider="groq",
            _ensure_model_favorite=mock.Mock(),
            _schedule_autosave=mock.Mock(),
        )

        SettingsPage.populate_models(page, ["llama-default", "llama-other"], "groq")

        page._ensure_model_favorite.assert_called_once_with("groq", "llama-default", save=False)
        self.assertIsNone(page._favorite_model_on_populate_provider)
        page._schedule_autosave.assert_called_once_with()
        combo.deleteLater()

    def test_favorite_model_commit_marks_selection_as_user_owned(self):
        host = SimpleNamespace(
            core=SimpleNamespace(
                settings={
                    "api_mode": "gemini",
                    "selected_gemini_model": "gemini-old",
                },
                _save_settings=mock.Mock(),
                _load_system_prompt=mock.Mock(return_value="prompt"),
                setup_model=mock.Mock(),
            ),
            _favorite_model_key=lambda provider, model: (
                str(provider or "").strip().lower(),
                str(model or "").strip(),
            ),
            _ensure_current_model_favorite=mock.Mock(),
            format_model_name=lambda model: model,
            refresh_favorite_model_controls=mock.Mock(),
            settings_page=None,
        )

        ChatWindow._select_favorite_model(host, "gemini", "gemini-3.6-flash")

        self.assertEqual(
            host.core.settings["selected_model_source"]["gemini"],
            "user",
        )
        host.core._save_settings.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
