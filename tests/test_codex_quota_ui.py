"""Focused visual-geometry tests for the Codex quota model menu."""
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QMenu, QPushButton, QStackedWidget, QWidgetAction

from smarti import chat as chat_module
from smarti import ui_pages
from smarti import ui_styles
from smarti.chat import ChatHistoryPage, ChatWindow, CodexQuotaWidget
from smarti.ui_controls import SearchableModelComboBox
from smarti.ui_pages import ResponsiveTaskCard, SettingsPage, TaskCenterPage


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

    def test_composer_model_menu_flips_above_and_stays_attached_to_button(self):
        button = QPushButton("gpt 5.6 luna", self.host)
        button.setGeometry(250, 635, 190, 44)
        self.host.show()
        self.app.processEvents()
        menu = QMenu(self.host)
        provider = menu.addMenu("OpenAI")
        for label in ("gpt 5.6 luna", "gpt 5.6 sol", "gpt 5.5"):
            provider.addAction(label)
        for label in ("עוצמת חשיבה", "מאוזנת", "גבוהה"):
            menu.addAction(label)

        opened = self.host._popup_menu_near_button(
            menu, button, center_horizontally=False, anchor_below=False
        )
        self.app.processEvents()

        self.assertTrue(opened)
        self.assertLessEqual(menu.frameGeometry().bottom(), button.mapToGlobal(QPoint(0, 0)).y())

    def test_autonomy_label_is_not_elided_when_the_control_has_room(self):
        button = chat_module.DropdownPillButton("אוטונומי")
        ChatWindow._fit_quick_input_button(
            self.host, button, "אוטונומי", base_width=152, max_width=204, min_width=118
        )
        self.assertEqual(button.text(), "אוטונומי")
        self.assertGreaterEqual(button.width(), 152)
        button.deleteLater()

    def test_popup_menu_is_opaque_for_windows_text_antialiasing(self):
        menu = QMenu(self.host)

        ui_styles.prepare_popup_menu(menu)

        self.assertFalse(menu.testAttribute(chat_module.Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(menu.testAttribute(chat_module.Qt.WidgetAttribute.WA_OpaquePaintEvent))
        self.assertEqual(menu.font().family(), ui_styles.resolve_app_font_family())
        self.assertEqual(
            menu.font().hintingPreference(),
            chat_module.QFont.HintingPreference.PreferNoHinting,
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

    def test_history_rows_share_active_geometry_and_activity_sits_by_ellipsis(self):
        active = self.page._compact_session_row(
            {
                "id": "running-session",
                "title": "כותרת רצה",
                "updated_at": "2026-08-13T20:00:00",
                "message_count": 3,
                "runtime_status": "running",
                "unread_count": 0,
            },
            active_id="running-session",
        )
        quiet = self.page._compact_session_row(
            {
                "id": "quiet-session",
                "title": "כותרת שקטה",
                "updated_at": "2026-08-13T20:00:00",
                "message_count": 2,
                "runtime_status": "idle",
                "unread_count": 0,
            },
            active_id="running-session",
        )
        for row in (active, quiet):
            row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            row.resize(520, 68)
            row.show()
        self.app.processEvents()

        active_title = next(label for label in active.findChildren(QLabel) if label.text() == "כותרת רצה")
        quiet_title = next(label for label in quiet.findChildren(QLabel) if label.text() == "כותרת שקטה")
        activity = active.findChild(chat_module.ConversationActivityIndicator)
        quiet_activity = quiet.findChild(chat_module.ConversationActivityIndicator)
        menu = active.findChild(QPushButton, "SessionActionsButton")

        self.assertEqual(active.height(), 68)
        self.assertEqual(quiet.height(), 68)
        self.assertIn("border-radius: 12px", active.styleSheet())
        self.assertIn("border-radius: 12px", quiet.styleSheet())
        self.assertGreater(activity.geometry().left(), menu.geometry().right())
        self.assertLess(activity.geometry().right(), active_title.geometry().left())
        self.assertEqual(active_title.geometry().right(), quiet_title.geometry().right())
        self.assertFalse(quiet_activity.isVisible())

        active.deleteLater()
        quiet.deleteLater()

    def test_typing_history_search_is_debounced_and_runs_once(self):
        records = []
        self.page.core = SimpleNamespace(
            list_chat_sessions=mock.Mock(return_value=records),
            active_chat_session=lambda: {"id": ""},
        )
        self.assertEqual(self.page._search_timer.interval(), 40)

        self.page.search_edit.setText("א")
        self.page.search_edit.setText("אב")
        self.page.search_edit.setText("אבג")
        self.assertEqual(self.page.core.list_chat_sessions.call_count, 0)
        self.assertFalse(self.page.loading_frame.isHidden())
        self.assertIs(self.page.history_stack.currentWidget(), self.page.loading_frame)

        deadline = time.monotonic() + 2.0
        while self.page.core.list_chat_sessions.call_count < 1 and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)

        self.assertEqual(self.page.core.list_chat_sessions.call_count, 1)
        self.assertEqual(self.page.core.list_chat_sessions.call_args.args, ("אבג",))
        deadline = time.monotonic() + 2.0
        while not self.page.loading_frame.isHidden() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertTrue(self.page.loading_frame.isHidden())
        self.assertIs(self.page.history_stack.currentWidget(), self.page.scroll)

    def test_history_rows_are_built_behind_loading_page_then_revealed_together(self):
        records = [
            {
                "id": f"session-{index}",
                "title": f"שיחה {index}",
                "updated_at": "2026-08-15T12:00:00",
                "message_count": 1,
                "runtime_status": "idle",
                "unread_count": 0,
            }
            for index in range(55)
        ]
        self.page.core = SimpleNamespace(active_chat_session=lambda: {"id": ""})
        self.page.loading_frame.show()
        self.page.history_stack.setCurrentWidget(self.page.loading_frame)

        self.page._render_sessions(records)

        self.assertIs(self.page.history_stack.currentWidget(), self.page.loading_frame)
        deadline = time.monotonic() + 2.0
        while self.page.history_stack.currentWidget() is not self.page.scroll and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertIs(self.page.history_stack.currentWidget(), self.page.scroll)
        self.assertEqual(
            len(self.page.content.findChildren(chat_module.ClickableSessionFrame)),
            len(records),
        )

    def test_task_center_card_expands_to_all_wrapped_content(self):
        task = {
            "id": "long-task",
            "status": "scheduled",
            "repeat": "interval",
            "interval_minutes": 1440,
            "conversation_mode": "dedicated",
            "run_at": "2026-08-16T12:00:00",
            "prompt": "הוראה מפורטת מאוד למשימת רקע מחזורית. " * 18,
            "last_result": "תוצאת ההרצה הקודמת נשמרת כאן במלואה לצורך בדיקה. " * 7,
        }
        core = SimpleNamespace(
            settings={"background_tasks": [task]},
            cancel_background_task=lambda _task_id: "OK",
            retry_background_task=lambda _task_id, _delay: "OK",
        )
        task_page = TaskCenterPage(core, self.main_window)
        self.stack.addWidget(task_page)
        self.stack.setCurrentWidget(task_page)
        self.stack.resize(535, 542)
        self.stack.show()
        task_page.load_tasks()
        for _ in range(30):
            self.app.processEvents()

        card = task_page.content.findChild(ResponsiveTaskCard)
        labels = card.findChildren(QLabel)
        body = next(label for label in labels if label.text().startswith("הוראה מפורטת"))
        result = next(label for label in labels if label.text().startswith("תוצאת ההרצה"))

        self.assertGreater(card.minimumHeight(), 320)
        self.assertGreaterEqual(body.height(), body.heightForWidth(body.width()))
        self.assertGreaterEqual(result.height(), result.heightForWidth(result.width()))
        self.assertGreater(task_page.scroll.verticalScrollBar().maximum(), 0)
        task_page.deleteLater()


class ThemeAndCanvasRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self):
        ui_styles.set_ui_theme("dark")
        self.app.processEvents()

    def test_light_user_bubble_uses_high_contrast_link_color(self):
        ui_styles.set_ui_theme("light")
        bubble = chat_module.MessageBubble("[מסמך](https://example.test)", is_user=True)

        self.assertEqual(bubble._link_color(), "#FFFFFF")
        self.assertIn("#FFFFFF", bubble.styleSheet())
        self.assertIn("color: #FFFFFF", bubble.final_label.text())
        bubble.deleteLater()

    def test_light_user_file_link_receives_the_same_high_contrast_color(self):
        ui_styles.set_ui_theme("light")
        with tempfile.NamedTemporaryFile(suffix=".docx") as handle:
            bubble = chat_module.MessageBubble(
                f"מסמך לבדיקה: {handle.name}",
                is_user=True,
            )

        self.assertIn('href="file:///', bubble.final_label.text())
        self.assertIn("color: #FFFFFF", bubble.final_label.text())
        bubble.deleteLater()

    def test_canvas_card_keeps_full_content_and_reflects_open_state(self):
        ui_styles.set_ui_theme("light")
        card = chat_module.CanvasOpenButton({
            "id": "canvas-1",
            "title": "חבורה בנימינוש — מהדורה תורנית מועשרת",
            "created_at": "2026-08-06T12:59:00",
        })
        card.resize(420, card.sizeHint().height())
        card.show()
        self.app.processEvents()

        self.assertGreaterEqual(card.sizeHint().height(), 108)
        self.assertEqual(card.title_label.text(), "חבורה בנימינוש — מהדורה תורנית מועשרת")
        self.assertIn("6 באוגוסט", card.meta_label.text())
        self.assertIn("12:59", card.meta_label.text())
        self.assertFalse(card.open_button.isHidden())
        self.assertEqual(card.open_button.height(), 38)
        self.assertIn("border-radius: 19px", card.styleSheet())
        self.assertTrue(card.testAttribute(chat_module.Qt.WidgetAttribute.WA_StyledBackground))

        card.set_active(True)
        self.assertTrue(card.open_button.isHidden())
        self.assertTrue(card.is_active())
        card.set_active(False)
        self.assertFalse(card.open_button.isHidden())
        card.deleteLater()

    def test_canvas_panel_close_control_is_a_theme_icon_button(self):
        panel = chat_module.VisualCanvasPanel()

        self.assertEqual(panel.close_button.size().width(), 38)
        self.assertEqual(panel.close_button.size().height(), 38)
        self.assertEqual(panel.close_button.accessibleName(), "סגירת הקנבס")
        self.assertTrue(panel.close_button.text() == "" or panel.close_button.text() == "×")
        panel.deleteLater()

    def test_canvas_panel_initial_light_theme_uses_light_frame_colors(self):
        ui_styles.set_ui_theme("light")
        panel = chat_module.VisualCanvasPanel()

        self.assertIn(ui_styles.GLASS_STRONG_COLOR, panel.styleSheet())
        self.assertIn(ui_styles.SOFT_LINE_COLOR, panel.styleSheet())
        panel.deleteLater()

    def test_application_stylesheet_is_stable_across_palette_changes(self):
        ui_styles.set_ui_theme("dark")
        dark_stylesheet = ui_styles.application_stylesheet()
        ui_styles.set_ui_theme("light")
        light_stylesheet = ui_styles.application_stylesheet()

        self.assertEqual(dark_stylesheet, light_stylesheet)

    def test_configured_asset_font_remains_the_application_font(self):
        self.assertEqual(ui_styles.resolve_app_font_family(), "Noto Sans Hebrew")
        self.assertTrue(ui_styles.APP_FONT_SOURCE_PATH.endswith("NotoSansHebrew-VariableFont_wdth,wght.ttf"))

    def test_input_dialog_styles_text_fields_with_theme_contrast(self):
        dialog = chat_module.QInputDialog()
        ui_styles.set_ui_theme("dark")
        ui_styles.prepare_themed_input_dialog(dialog)

        self.assertIn(ui_styles.FIELD_TEXT_COLOR, dialog.styleSheet())
        self.assertIn(ui_styles.GLASS_COLOR, dialog.styleSheet())
        dialog.deleteLater()


class UsageStatsPricingCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self.temp_dir.name, "usage_cost_cache.json")
        self.cache_patch = mock.patch.object(ui_pages, "USAGE_COST_CACHE_FILE", self.cache_path)
        self.cache_patch.start()
        self.original_module = ui_pages.UsageStatsLoadWorker._litellm_module
        self.original_unavailable = ui_pages.UsageStatsLoadWorker._litellm_unavailable

    def tearDown(self):
        ui_pages.UsageStatsLoadWorker._litellm_module = self.original_module
        ui_pages.UsageStatsLoadWorker._litellm_unavailable = self.original_unavailable
        self.cache_patch.stop()
        self.temp_dir.cleanup()

    def test_pricing_rates_persist_and_apply_to_new_token_totals(self):
        fake_litellm = SimpleNamespace(model_cost={
            "gpt-test": {
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000002,
                "cache_read_input_token_cost": 0.0000002,
                "cache_creation_input_token_cost": 0.00000125,
            },
        })
        ui_pages.UsageStatsLoadWorker._litellm_module = fake_litellm
        ui_pages.UsageStatsLoadWorker._litellm_unavailable = False
        first = ui_pages.UsageStatsLoadWorker(1, "all")
        first._pricing_cache = first._load_pricing_cache()
        first._pricing_cache_dirty = False

        suffix, missing = first._cost_suffix(
            "gpt-test",
            {"prompt": 1000, "completion": 500, "cached_prompt": 0, "cache_write_prompt": 0},
            allow_litellm=True,
        )
        first._save_pricing_cache()

        self.assertFalse(missing)
        self.assertIn("$0.0020", suffix)
        self.assertTrue(os.path.exists(self.cache_path))

        second = ui_pages.UsageStatsLoadWorker(2, "all")
        second._pricing_cache = second._load_pricing_cache()
        second._pricing_cache_dirty = False
        with mock.patch.object(second, "_litellm", side_effect=AssertionError("cache should avoid import")):
            updated_suffix, updated_missing = second._cost_suffix(
                "gpt-test",
                {"prompt": 2000, "completion": 1000, "cached_prompt": 0, "cache_write_prompt": 0},
                allow_litellm=False,
            )

        self.assertFalse(updated_missing)
        self.assertIn("$0.0040", updated_suffix)

    def test_bundled_pricing_produces_first_paint_without_importing_litellm(self):
        worker = ui_pages.UsageStatsLoadWorker(1, "all")
        worker._pricing_cache = {"version": 1, "updated_at": "", "models": {}}
        worker._pricing_cache_dirty = False
        worker._pricing_cache_stale = True
        worker._bundled_model_costs = {
            "gpt-bundled": {
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000002,
            },
        }

        with mock.patch.object(worker, "_litellm", side_effect=AssertionError("first paint must stay local")):
            suffix, needs_refresh = worker._cost_suffix(
                "gpt-bundled",
                {"prompt": 1000, "completion": 500},
                allow_litellm=False,
            )

        self.assertFalse(needs_refresh)
        self.assertIn("$0.0020", suffix)

    def test_stale_cached_rate_is_refreshed_from_local_bundled_catalog(self):
        worker = ui_pages.UsageStatsLoadWorker(1, "all")
        worker._pricing_cache = {
            "version": 1,
            "updated_at": "2025-01-01T00:00:00+00:00",
            "models": {
                "gpt-bundled": {
                    "input": 0.0000001,
                    "output": 0.0000002,
                },
            },
        }
        worker._pricing_cache_dirty = False
        worker._pricing_cache_stale = True
        worker._bundled_model_costs = {
            "gpt-bundled": {
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000002,
            },
        }

        suffix, needs_refresh = worker._cost_suffix(
            "gpt-bundled",
            {"prompt": 1000, "completion": 500},
            allow_litellm=False,
        )

        self.assertFalse(needs_refresh)
        self.assertIn("$0.0020", suffix)
        self.assertEqual(worker._pricing_cache["models"]["gpt-bundled"]["_source"], "bundled")
        self.assertTrue(worker._pricing_cache_dirty)

    def test_default_future_model_has_priced_first_paint_with_empty_cache(self):
        worker = ui_pages.UsageStatsLoadWorker(1, "today")
        worker._pricing_cache = {"version": 1, "updated_at": "", "models": {}}
        worker._pricing_cache_dirty = False
        worker._pricing_cache_stale = True
        worker._bundled_model_costs = {}

        suffix, needs_refresh = worker._cost_suffix(
            "gpt-5.6-sol",
            {"prompt": 1000, "completion": 100, "cached_prompt": 0},
            allow_litellm=False,
        )

        self.assertTrue(needs_refresh)
        self.assertIn("$0.0080", suffix)

    def test_unpriced_cache_entry_does_not_permanently_suppress_refresh(self):
        worker = ui_pages.UsageStatsLoadWorker(1, "today")
        worker._pricing_cache = {
            "version": 1,
            "updated_at": "",
            "models": {"unknown-cloud-model": {"unpriced": True}},
        }
        worker._pricing_cache_dirty = False
        worker._pricing_cache_stale = True
        worker._bundled_model_costs = {}

        suffix, needs_refresh = worker._cost_suffix(
            "unknown-cloud-model",
            {"prompt": 1000, "completion": 100},
            allow_litellm=False,
        )

        self.assertTrue(needs_refresh)
        self.assertIn("לא במאגר", suffix)
        self.assertNotIn("unknown-cloud-model", worker._pricing_cache["models"])


class LogTailRegressionTests(unittest.TestCase):
    def test_log_tail_reads_only_the_requested_final_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
            path = handle.name
            for index in range(5000):
                handle.write(f"שורה {index}\n")
        try:
            lines = ui_pages._tail_text_file(path, 3, chunk_size=128)
        finally:
            os.remove(path)

        self.assertEqual(lines, ["שורה 4997", "שורה 4998", "שורה 4999"])


class ContextCompactionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_compaction_uses_a_named_tool_row_and_theme_aware_icon_stem(self):
        tool = {"action": "context_compaction", "arguments": {"scope": "active_task"}}

        self.assertEqual(chat_module._agent_tool_display_name(tool), "דחיסת הקשר")
        self.assertIn("agent_tool_context_compaction", chat_module._agent_tool_icon_names(tool))

    def test_document_manager_tool_row_stays_in_catalog_english(self):
        tool = {"action": "document_manager", "arguments": {"action": "create"}}

        self.assertEqual(chat_module._agent_tool_display_name(tool), "document_manager / create")
        self.assertIn("agent_tool_document_manager", chat_module._agent_tool_icon_names(tool))

    def test_malformed_inline_output_uri_is_repaired_to_clickable_artifact(self):
        with tempfile.TemporaryDirectory() as output_dir:
            artifact = os.path.join(output_dir, "result.docx")
            with open(artifact, "wb") as output_file:
                output_file.write(b"docx")
            broken = "`file:///C:/Users/%D7%ห/Documents/Smarti_Outputs/result.docx`"

            with mock.patch.object(chat_module, "OUTPUTS_DIR", output_dir):
                repaired = chat_module._repair_markdown_links(broken)
                rendered = chat_module._render_markdown_html(broken)

            self.assertNotIn("`", repaired)
            self.assertIn("[result.docx](file:", repaired)
            self.assertIn("<a href=", rendered)

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


class ChatRtlLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _laid_out_message(self, is_user):
        container = chat_module.ChatMessageContainer(
            "זוהי הודעת בדיקה קצרה",
            is_user=is_user,
            parent_width=900,
        )
        container.resize(900, container.sizeHint().height())
        container.show()
        self.app.processEvents()
        return container

    def test_user_bubble_and_actions_are_anchored_to_the_right(self):
        container = self._laid_out_message(is_user=True)
        try:
            self.assertGreater(container.bubble.geometry().center().x(), container.width() // 2)
            self.assertGreater(container.copy_btn.geometry().center().x(), container.width() // 2)
            self.assertLessEqual(
                container.actions_container.width() - container.copy_btn.geometry().right(),
                20,
            )
        finally:
            container.close()

    def test_agent_content_and_actions_are_anchored_to_the_right(self):
        container = self._laid_out_message(is_user=False)
        try:
            self.assertGreater(container.bubble.geometry().center().x(), container.width() // 2)
            self.assertGreater(container.copy_btn.geometry().center().x(), container.width() // 2)
            self.assertGreater(container.tts_btn.geometry().center().x(), container.width() // 2)
            self.assertGreater(container.copy_btn.x(), container.tts_btn.x())
        finally:
            container.close()


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
