"""Reusable PyQt controls used across Smarti screens."""
from .common import *
from .ui_styles import *

# ==========================================
# פונקציות עזר UI
# ==========================================
def make_circular_pixmap(image_path, size, border_color=None, border_width=0, bg_color=None):
    original = QPixmap(image_path)
    if original.isNull(): return None
    img_size = size - 2 * border_width
    scaled = original.scaled(img_size, img_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    dim = min(scaled.width(), scaled.height())
    cropped = scaled.copy((scaled.width() - dim) // 2, (scaled.height() - dim) // 2, dim, dim)
    target = QPixmap(size, size)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addEllipse(border_width, border_width, img_size, img_size)
    painter.setClipPath(path)
    if bg_color: painter.fillPath(path, QColor(bg_color))
    painter.drawPixmap(border_width, border_width, cropped)
    if border_color and border_width > 0:
        painter.setClipping(False)
        pen = QPen(QColor(border_color))
        pen.setWidth(border_width)
        painter.setPen(pen)
        offset = border_width / 2.0
        painter.drawEllipse(int(offset), int(offset), int(size - border_width), int(size - border_width))
    painter.end()
    return target

def apply_soft_shadow(widget, *, blur=28, y=8, alpha=46, color=None):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    shadow = QColor(color or "#00111C")
    shadow.setAlpha(alpha)
    effect.setColor(shadow)
    widget.setGraphicsEffect(effect)
    return effect

class MeshGradientWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.00, qcolor_from_css(MESH_A))
        base.setColorAt(0.46, qcolor_from_css(MESH_B))
        base.setColorAt(0.74, qcolor_from_css(MESH_C))
        base.setColorAt(1.00, qcolor_from_css(MESH_D))
        painter.fillRect(rect, QBrush(base))
        painter.end()

class NoScrollComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMaxVisibleItems(8)
        self.view().setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.view().setTextElideMode(Qt.TextElideMode.ElideRight)
        self.view().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._apply_popup_theme()

    def wheelEvent(self, e): e.ignore()

    def _apply_popup_theme(self):
        view = self.view()
        if not view:
            return
        view.setAutoFillBackground(True)
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        if view.viewport():
            view.viewport().setAutoFillBackground(True)
            view.viewport().setStyleSheet(f"background-color: {MENU_BG_COLOR};")
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, qcolor_from_css(MENU_BG_COLOR))
        palette.setColor(QPalette.ColorRole.Text, qcolor_from_css(TEXT_COLOR))
        palette.setColor(QPalette.ColorRole.Highlight, qcolor_from_css(ACCENT_TINT_STRONG))
        palette.setColor(QPalette.ColorRole.HighlightedText, qcolor_from_css(TEXT_COLOR))
        view.setPalette(palette)
        view.setStyleSheet(
            f"QAbstractItemView {{ background-color: {MENU_BG_COLOR}; color: {TEXT_COLOR}; "
            f"border: 1px solid {SOFT_LINE_COLOR}; border-radius: 0px; padding: 8px; outline: 0px; "
            f"selection-background-color: {ACCENT_TINT_STRONG}; selection-color: {TEXT_COLOR}; "
            f"font-family: {ui_popup_font_family_css()}; font-size: 14px; font-weight: 500; }}"
            f"QAbstractItemView::item {{ min-height: 28px; padding: 7px 10px; border-radius: 0px; }}"
            f"QAbstractItemView::item:hover {{ background-color: {HOVER_TINT}; }}"
            f"QAbstractItemView::item:selected {{ background-color: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR}; }}"
        )

    def showPopup(self):
        self._apply_popup_theme()
        self.view().setMinimumWidth(max(180, self.width()))
        self.view().setMaximumWidth(max(220, self.width()))
        popup_win = self.view().window()
        if popup_win:
            popup_win.setWindowFlags(popup_win.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
            popup_win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            popup_win.setAutoFillBackground(True)
            popup_win.setStyleSheet(f"background-color: {MENU_BG_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 0px;")
        super().showPopup()

class ModelSearchLineEdit(QLineEdit):
    navigateRequested = pyqtSignal(int)
    commitRequested = pyqtSignal()
    dismissRequested = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Down:
            self.navigateRequested.emit(1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Up:
            self.navigateRequested.emit(-1)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.commitRequested.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.dismissRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

class SearchableModelComboBox(NoScrollComboBox):
    modelCommitted = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._all_models = []
        self._selected_model = ""
        self._placeholder_text = "לא נמצאו מודלים"
        self._loading = False
        self._popup = None
        self._suppress_next_show = False
        self._suppress_next_release = False
        self._app_filter_installed = False
        self._favorite_state_callback = None
        self._favorite_toggle_callback = None
        self._ignore_next_item_activation = False
        self.search_edit = None
        self.results_list = None
        self.setEditable(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(COMBOBOX_CSS)
        if self.search_edit:
            self.search_edit.setStyleSheet(LINE_EDIT_CSS)
        if self.results_list:
            self.results_list.setStyleSheet(
                f"QListWidget {{ background-color: {MENU_BG_COLOR}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
                f"border-radius: 0px; padding: 4px; outline: none; "
                f"font-family: {ui_popup_font_family_css()}; font-size: 14px; font-weight: 500; }}"
                f"QListWidget viewport {{ background-color: {MENU_BG_COLOR}; }}"
                f"QListWidget::item {{ padding: 4px 6px; border-radius: 0px; }}"
                f"QListWidget::item:hover {{ background-color: {HOVER_TINT}; }}"
                f"QListWidget::item:selected {{ background-color: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR}; }}"
            )
        if self._popup:
            self._popup.setStyleSheet(
                f"QFrame#ModelPickerPopup {{ background-color: {MENU_BG_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
                f"border-radius: 0px; padding: 6px; }}"
            )
        self._refresh_result_star_buttons()

    def set_favorite_callbacks(self, state_callback=None, toggle_callback=None):
        self._favorite_state_callback = state_callback
        self._favorite_toggle_callback = toggle_callback
        self._refresh_result_star_buttons()

    def set_loading_text(self, text):
        self._all_models = []
        self._selected_model = ""
        self._loading = True
        self.setEnabled(False)
        previous = self.blockSignals(True)
        self.clear()
        self.addItem(str(text or ""))
        self.setCurrentIndex(0)
        self.blockSignals(previous)
        self.hidePopup()

    def set_models(self, models, selected_model=""):
        seen = set()
        cleaned = []
        for model in models or []:
            model = str(model or "").strip()
            if model and model not in seen:
                cleaned.append(model)
                seen.add(model)
        selected_model = str(selected_model or "").strip()
        if selected_model and selected_model not in seen:
            cleaned.insert(0, selected_model)
        self._all_models = cleaned
        self._loading = False
        self.setEnabled(True)
        previous = self.blockSignals(True)
        self.clear()
        self.addItems(cleaned or ([selected_model] if selected_model else []))
        self.blockSignals(previous)
        self.set_current_model(selected_model if selected_model in cleaned else (cleaned[0] if cleaned else selected_model))

    def selected_model(self):
        return self._selected_model

    def currentText(self):
        return self._selected_model or super().currentText()

    def set_current_model(self, model):
        model = str(model or "").strip()
        if not model:
            return
        previous = self.blockSignals(True)
        if self.findText(model) < 0:
            self.addItem(model)
        self.setCurrentText(model)
        self.blockSignals(previous)
        self._selected_model = model
        self.hidePopup()

    def _ensure_popup(self):
        if self._popup:
            return
        self._popup = QFrame(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self._popup.setObjectName("ModelPickerPopup")
        self._popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._popup.setAutoFillBackground(True)
        self._popup.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._popup.installEventFilter(self)
        layout = QVBoxLayout(self._popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.search_edit = ModelSearchLineEdit()
        self.search_edit.setPlaceholderText("חפש מודל")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textEdited.connect(self._on_search_text_edited)
        self.search_edit.navigateRequested.connect(self._move_highlight)
        self.search_edit.commitRequested.connect(self._commit_from_keyboard)
        self.search_edit.dismissRequested.connect(self.hidePopup)
        self.results_list = QListWidget()
        self.results_list.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.results_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_list.itemClicked.connect(self._commit_item)
        self.results_list.itemActivated.connect(self._commit_item)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.results_list)
        self.apply_theme()

    def _clear_popup_toggle_guard(self):
        self._suppress_next_show = False

    def _combo_contains_global_pos(self, pos):
        return self.rect().contains(self.mapFromGlobal(pos))

    def _cursor_is_over_combo(self):
        return self._combo_contains_global_pos(QCursor.pos())

    def _event_global_pos(self, event):
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        if hasattr(event, "globalPos"):
            return event.globalPos()
        return QCursor.pos()

    def _install_popup_event_filter(self):
        if self._app_filter_installed:
            return
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
            self._app_filter_installed = True

    def _remove_popup_event_filter(self):
        if not self._app_filter_installed:
            return
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)
        self._app_filter_installed = False

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and self._popup
            and self._popup.isVisible()
            and self._combo_contains_global_pos(self._event_global_pos(event))
        ):
            self._suppress_next_show = True
            self._suppress_next_release = True
            self._popup.hide()
            self._remove_popup_event_filter()
            QTimer.singleShot(220, self._clear_popup_toggle_guard)
            return True
        if watched is self._popup and event.type() == QEvent.Type.Hide:
            if self._cursor_is_over_combo():
                self._suppress_next_show = True
                QTimer.singleShot(220, self._clear_popup_toggle_guard)
            self._remove_popup_event_filter()
        return super().eventFilter(watched, event)

    def _normalize_search_text(self, text):
        return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()

    def _tokens_for_search(self, text):
        normalized = self._normalize_search_text(text)
        raw_tokens = re.findall(r"[a-z0-9]+", normalized)
        tokens = []
        for index, token in enumerate(raw_tokens):
            match = re.fullmatch(r"(\d+)([a-z]+)", token)
            if match:
                tokens.extend([match.group(1), match.group(2)])
            elif token:
                tokens.append(token)
            if token.isdigit() and index + 1 < len(raw_tokens) and raw_tokens[index + 1] in {"b", "bn", "m", "k"}:
                tokens.append(token + raw_tokens[index + 1])
        seen = set()
        return [token for token in tokens if not (token in seen or seen.add(token))]

    def _score_model(self, query, model):
        query_tokens = self._tokens_for_search(query)
        if not query_tokens:
            return 1.0
        model_text = self._normalize_search_text(model)
        model_tokens = self._tokens_for_search(model)
        compact_model = model_text.replace(" ", "")
        compact_query = self._normalize_search_text(query).replace(" ", "")
        score = 0.0
        for token in query_tokens:
            token_score = 0.0
            for candidate in model_tokens:
                if candidate == token:
                    token_score = max(token_score, 1.0)
                elif candidate.startswith(token):
                    token_score = max(token_score, 0.92)
                elif token.startswith(candidate) and len(candidate) >= 3:
                    token_score = max(token_score, 0.86)
                elif len(token) >= 3 and token in candidate:
                    token_score = max(token_score, 0.82)
                elif len(token) >= 4:
                    token_score = max(token_score, difflib.SequenceMatcher(None, token, candidate).ratio())
            if len(token) >= 3 and token in compact_model:
                token_score = max(token_score, 0.78)
            threshold = 0.88 if token.isdigit() else (0.72 if len(token) >= 4 else 0.82)
            if token_score < threshold:
                return 0.0
            score += token_score
        if compact_query and compact_query in compact_model:
            score += 1.25
        if model_text.startswith(self._normalize_search_text(query)):
            score += 0.7
        return score / max(1, len(query_tokens))

    def _filtered_models(self, query):
        query = str(query or "").strip()
        if not query:
            return self._all_models[:]
        scored = []
        for model in self._all_models:
            score = self._score_model(query, model)
            if score > 0:
                scored.append((score, len(model), model))
        scored.sort(key=lambda item: (-item[0], item[1], item[2].lower()))
        return [model for _, _, model in scored[:250]]

    def _on_search_text_edited(self, text):
        if self._loading:
            return
        matches = self._filtered_models(text)
        self._show_results(matches)

    def _show_results(self, matches):
        self._ensure_popup()
        self.results_list.clear()
        if not matches:
            item = QListWidgetItem(self._placeholder_text)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.results_list.addItem(item)
        else:
            for model in matches:
                item = QListWidgetItem("")
                item.setData(Qt.ItemDataRole.UserRole, model)
                item.setSizeHint(QSize(10, 42))
                self.results_list.addItem(item)
                self.results_list.setItemWidget(item, self._make_model_result_row(model))
        self.results_list.clearSelection()
        current_row = self._row_for_model(self._selected_model)
        self.results_list.setCurrentRow(current_row if current_row >= 0 else -1)

    def _model_is_favorite(self, model):
        if not self._favorite_state_callback:
            return False
        try:
            return bool(self._favorite_state_callback(str(model or "").strip()))
        except Exception:
            return False

    def _star_button_css(self):
        return (
            f"QPushButton {{ background: transparent; color: {ACCENT_COLOR}; border: 1px solid transparent; "
            "border-radius: 14px; padding: 0px; font-size: 17px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {ACCENT_TINT}; border-color: {SOFT_LINE_COLOR}; }}"
        )

    def _set_star_button_icon(self, button, model):
        favorite = self._model_is_favorite(model)
        names = ("star_filled", "star_filled_icon", "favorite_model_on_icon", "favorite_on_icon") if favorite else ("star_empty", "star_empty_icon", "favorite_model_off_icon", "favorite_off_icon")
        fallback = "★" if favorite else "☆"
        set_themed_button_icon(button, names, fallback, 18, clear_text=True)
        button.setToolTip("הסר מהמועדפים" if favorite else "הוסף למועדפים")
        button.setStyleSheet(self._star_button_css())

    def _make_model_result_row(self, model):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)
        star_btn = QPushButton()
        star_btn.setProperty("smartiModelFavoriteStar", True)
        star_btn.setProperty("smartiModelName", str(model or ""))
        star_btn.setFixedSize(30, 30)
        star_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._set_star_button_icon(star_btn, model)
        star_btn.clicked.connect(lambda checked=False, m=str(model or ""), b=star_btn: self._toggle_model_favorite_from_popup(m, b))
        label = QLabel(str(model or ""))
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; background: transparent;")
        label.setWordWrap(False)
        layout.addWidget(star_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(label, 1, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _toggle_model_favorite_from_popup(self, model, button):
        if not self._favorite_toggle_callback:
            return
        self._ignore_next_item_activation = True
        try:
            self._favorite_toggle_callback(str(model or "").strip())
        except Exception:
            QTimer.singleShot(160, lambda: setattr(self, "_ignore_next_item_activation", False))
            return
        self._set_star_button_icon(button, model)
        self._refresh_result_star_buttons()
        QTimer.singleShot(160, lambda: setattr(self, "_ignore_next_item_activation", False))

    def _refresh_result_star_buttons(self):
        if not self.results_list:
            return
        for button in self.results_list.findChildren(QPushButton):
            if button.property("smartiModelFavoriteStar"):
                self._set_star_button_icon(button, button.property("smartiModelName") or "")

    def _row_for_model(self, model):
        model = str(model or "")
        if not model or not self.results_list:
            return -1
        for row in range(self.results_list.count()):
            item = self.results_list.item(row)
            if self._model_from_item(item) == model:
                return row
        return -1

    def _model_from_item(self, item):
        if not item:
            return ""
        value = item.data(Qt.ItemDataRole.UserRole)
        return str(value if value is not None else item.text() or "").strip()

    def _commit_item(self, item):
        if self._ignore_next_item_activation:
            self._ignore_next_item_activation = False
            return
        self._commit_model(self._model_from_item(item))

    def _move_highlight(self, direction):
        self._ensure_popup()
        selectable = [
            row for row in range(self.results_list.count())
            if self.results_list.item(row).flags() & Qt.ItemFlag.ItemIsSelectable
        ]
        if not selectable:
            return
        current = self.results_list.currentRow()
        if current not in selectable:
            next_row = selectable[0] if direction > 0 else selectable[-1]
        else:
            pos = selectable.index(current)
            next_row = selectable[(pos + direction) % len(selectable)]
        self.results_list.setCurrentRow(next_row)

    def _commit_from_keyboard(self):
        typed = str(self.search_edit.text() or "").strip()
        if typed in self._all_models:
            self._commit_model(typed)
            return
        row = self.results_list.currentRow()
        if row >= 0:
            item = self.results_list.item(row)
            if item and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                self._commit_model(self._model_from_item(item))

    def _commit_model(self, model):
        model = str(model or "").strip()
        if not model or model == self._placeholder_text:
            return
        self.set_current_model(model)
        self.modelCommitted.emit(model)

    def showPopup(self):
        if self._loading:
            return
        if self._popup and self._popup.isVisible():
            self.hidePopup()
            return
        if self._suppress_next_show:
            self._suppress_next_show = False
            return
        self._ensure_popup()
        previous = self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(previous)
        self._show_results(self._all_models)
        popup_w = max(1, self.width())
        row_h = self.results_list.sizeHintForRow(0)
        row_h = row_h if row_h > 0 else 34
        list_h = min(360, max(180, row_h * min(max(1, self.results_list.count()), 10) + 24))
        self.results_list.setFixedHeight(list_h)
        self._popup.setFixedWidth(popup_w)
        self._popup.adjustSize()
        pos = self.mapToGlobal(QPoint(0, self.height()))
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            window = self.window()
            if window:
                window_rect = window.frameGeometry().adjusted(8, 8, -8, -8)
                if window_rect.isValid() and window_rect.width() > 80 and window_rect.height() > 80:
                    available = available.intersected(window_rect)
            if pos.x() + popup_w > available.right():
                pos.setX(max(available.left(), available.right() - popup_w))
            if pos.y() + self._popup.height() > available.bottom():
                pos = self.mapToGlobal(QPoint(0, -self._popup.height()))
            pos.setX(max(available.left(), min(pos.x(), available.right() - popup_w)))
            pos.setY(max(available.top(), min(pos.y(), available.bottom() - self._popup.height())))
        self._popup.move(pos)
        self._popup.show()
        self._popup.move(pos)
        self._install_popup_event_filter()
        self.search_edit.setFocus()

    def hidePopup(self):
        if self._popup:
            self._popup.hide()
        self._remove_popup_event_filter()

    def mousePressEvent(self, event):
        if self._popup and self._popup.isVisible():
            self.hidePopup()
            self._suppress_next_release = True
            event.accept()
            return
        if self._suppress_next_show:
            self._suppress_next_show = False
            self._suppress_next_release = True
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._suppress_next_release:
            self._suppress_next_release = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

class MaskedSecretLineEdit(QLineEdit):
    secretEdited = pyqtSignal(str)

    def __init__(self, secret="", parent=None):
        super().__init__(parent)
        self._secret_value = ""
        self._editing_secret = False
        self.setClearButtonEnabled(True)
        self.textChanged.connect(self._on_text_edited)
        self.set_secret(secret)

    def set_secret(self, value):
        self._secret_value = sanitize_secret_value(value)
        self._editing_secret = False
        previous = self.blockSignals(True)
        self.setEchoMode(QLineEdit.EchoMode.Normal)
        super().setText(mask_secret_value(self._secret_value))
        self.blockSignals(previous)
        self.setModified(False)

    def secret(self):
        if self._editing_secret:
            return sanitize_secret_value(self.text())
        return self._secret_value

    def has_pending_secret(self):
        return self._editing_secret

    def clear_secret(self):
        self._secret_value = ""
        self._editing_secret = True
        previous = self.blockSignals(True)
        self.setEchoMode(QLineEdit.EchoMode.Normal)
        super().setText("")
        self.blockSignals(previous)
        self.setModified(True)
        self.secretEdited.emit("")

    def _on_text_edited(self, text):
        self._editing_secret = True
        cleaned = sanitize_secret_value(text)
        if cleaned != str(text or ""):
            cursor = min(self.cursorPosition(), len(cleaned))
            previous = self.blockSignals(True)
            super().setText(cleaned)
            self.setCursorPosition(cursor)
            self.blockSignals(previous)
        self.secretEdited.emit(cleaned)

    def focusInEvent(self, event):
        self.setEchoMode(QLineEdit.EchoMode.Password)
        if not self._editing_secret and self._secret_value:
            tail = self._secret_value[-4:]
            previous = self.blockSignals(True)
            super().setText("")
            self.blockSignals(previous)
            self.setPlaceholderText(f"הדבק מפתח חדש (הקיים מסתיים ב-{tail})")
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        if self._editing_secret and not sanitize_secret_value(self.text()):
            self.set_secret("")
        elif not self._editing_secret:
            self.set_secret(self._secret_value)
        else:
            self.setEchoMode(QLineEdit.EchoMode.Password)
        super().focusOutEvent(event)

class SegmentedControl(QWidget):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self.setObjectName("SegmentedControl")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._items = []
        self._buttons = []
        self._button_icon_names = {}
        self._current_index = -1
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(0)
        self.addItems(items or [])
        self.apply_theme()

    def addItems(self, items):
        for item in items:
            self.addItem(item)
        if self._items and self._current_index < 0:
            self.setCurrentIndex(0, emit=False)

    def addItem(self, text):
        index = len(self._items)
        self._items.append(str(text))
        btn = QPushButton(str(text))
        btn.setCheckable(True)
        btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setMinimumHeight(34)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda checked=False, i=index: self.setCurrentIndex(i))
        self._buttons.append(btn)
        self._layout.addWidget(btn)
        self.apply_theme()

    def currentIndex(self):
        return self._current_index

    def currentText(self):
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return ""

    def setCurrentIndex(self, index, emit=True):
        if not self._items:
            self._current_index = -1
            return
        index = max(0, min(int(index), len(self._items) - 1))
        if index == self._current_index:
            for i, btn in enumerate(self._buttons):
                btn.setChecked(i == index)
                self._apply_button_icon(i)
            return
        self._current_index = index
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
            self._apply_button_icon(i)
        if emit:
            self.currentIndexChanged.emit(index)

    def setCurrentText(self, text):
        text = str(text)
        if text in self._items:
            self.setCurrentIndex(self._items.index(text))

    def setItemIconNames(self, index, names, fallback_text=""):
        try:
            index = int(index)
        except Exception:
            return
        if not (0 <= index < len(self._buttons)):
            return
        if isinstance(names, str):
            names = (names,)
        self._button_icon_names[index] = (tuple(names or ()), str(fallback_text or ""))
        self._apply_button_icon(index)

    def _apply_button_icon(self, index):
        data = self._button_icon_names.get(index)
        if not data or not (0 <= index < len(self._buttons)):
            return
        names, fallback_text = data
        button = self._buttons[index]
        candidates = []
        if button.isChecked():
            selected_theme = "light" if CURRENT_THEME == "dark" else "dark"
            for name in names:
                raw = str(name or "").strip()
                if not raw or os.path.isabs(raw) or os.path.dirname(raw):
                    continue
                stem, ext = os.path.splitext(raw)
                if ext:
                    candidates.append(f"{stem}_{selected_theme}{ext}")
                else:
                    candidates.extend([f"{raw}_{selected_theme}.png", f"{raw}_{selected_theme}.svg"])
        icon = themed_icon(*(candidates + list(names)))
        if not icon.isNull():
            button.setIcon(icon)
            button.setIconSize(QSize(18, 18))
        else:
            button.setIcon(QIcon())

    def apply_theme(self):
        self.setStyleSheet(segmented_control_css())
        for index in range(len(self._buttons)):
            self._apply_button_icon(index)

class DropdownPillButton(QPushButton):
    def __init__(self, *args, arrow_names=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._arrow_icon_names = tuple(arrow_names or ("message_collapse_arrow", "message_collapse_arrow_icon", "dropdown"))
        self._arrow_size = 13
        self._content_gap = 6

    def setArrowIconNames(self, names):
        self._arrow_icon_names = tuple(names or ())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        option = QStyleOptionButton()
        option.initFrom(self)
        option.rect = self.rect().adjusted(1, 1, -1, -1)
        option.text = ""
        option.icon = QIcon()
        if self.isDown():
            option.state |= QStyle.StateFlag.State_Sunken
        if self.isChecked():
            option.state |= QStyle.StateFlag.State_On
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        arrow_icon = themed_icon(*self._arrow_icon_names)
        arrow_pixmap = QPixmap()
        if not arrow_icon.isNull():
            mode = QIcon.Mode.Disabled if not self.isEnabled() else QIcon.Mode.Normal
            arrow_pixmap = arrow_icon.pixmap(self._arrow_size, self._arrow_size, mode)

        main_icon = self.icon()
        icon_size = self.iconSize()
        icon_pixmap = QPixmap()
        if not main_icon.isNull() and icon_size.width() > 0 and icon_size.height() > 0:
            mode = QIcon.Mode.Disabled if not self.isEnabled() else QIcon.Mode.Normal
            icon_pixmap = main_icon.pixmap(icon_size, mode)

        text = str(self.text() or "")
        metrics = QFontMetrics(self.font())
        text_width = metrics.horizontalAdvance(text) if text else 0
        gap = int(self._content_gap)
        icon_w = 0 if icon_pixmap.isNull() else icon_pixmap.width()
        arrow_w = 0 if arrow_pixmap.isNull() else arrow_pixmap.width()
        group_width = icon_w + text_width + arrow_w
        if icon_w and text_width:
            group_width += gap
        if arrow_w and (text_width or icon_w):
            group_width += gap

        content = option.rect.adjusted(8, 0, -8, 0)
        if group_width > content.width():
            text_budget = max(12, content.width() - icon_w - arrow_w - (gap if icon_w else 0) - (gap if arrow_w else 0))
            text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, text_budget)
            text_width = metrics.horizontalAdvance(text)
            group_width = icon_w + text_width + arrow_w
            if icon_w and text_width:
                group_width += gap
            if arrow_w and (text_width or icon_w):
                group_width += gap

        x = int(content.x() + max(0, (content.width() - group_width) / 2))
        center_y = int(option.rect.center().y())

        if not icon_pixmap.isNull():
            painter.drawPixmap(x, center_y - icon_pixmap.height() // 2, icon_pixmap)
            x += icon_pixmap.width() + (gap if text_width else 0)

        painter.setPen(self.palette().color(QPalette.ColorRole.ButtonText))
        if text_width:
            text_bounds = metrics.tightBoundingRect(text)
            baseline_y = center_y - (text_bounds.top() + text_bounds.bottom()) / 2.0
            painter.drawText(int(round(x - text_bounds.left())), int(round(baseline_y)), text)
            x += text_width + (gap if arrow_w else 0)

        if not arrow_pixmap.isNull():
            painter.drawPixmap(x, center_y - arrow_pixmap.height() // 2, arrow_pixmap)
        painter.end()

class SmartiCheckBox(QCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._smarti_info_reserved = False
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(38)
        self.setStyleSheet("background: transparent;")

    def setInfoButtonReserved(self, reserved=True):
        self._smarti_info_reserved = bool(reserved)
        self.update()

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(max(hint.width() + 40, 180), max(hint.height(), 38))

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        switch_w, switch_h = 52, 30
        margin = 2
        y = int((self.height() - switch_h) / 2)
        switch_x = margin
        switch_rect = QRectF(switch_x, y, switch_w, switch_h)

        track = QLinearGradient(switch_rect.topLeft(), switch_rect.bottomRight())
        if self.isChecked():
            track.setColorAt(0.0, qcolor_from_css(ACCENT_COLOR))
            track.setColorAt(0.56, qcolor_from_css(ACCENT_PINK_COLOR))
            track.setColorAt(1.0, qcolor_from_css(ACCENT_SECONDARY_COLOR))
        else:
            track.setColorAt(0.0, qcolor_from_css(FIELD_COLOR))
            track.setColorAt(1.0, qcolor_from_css(FIELD_HOVER_COLOR))
        pen = QPen(qcolor_from_css(LINE_COLOR if self.isChecked() else "rgba(142,107,255,0.62)"))
        pen.setWidth(1 if self.isChecked() else 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(track))
        painter.drawRoundedRect(switch_rect, switch_h / 2, switch_h / 2)

        knob_d = 24
        knob_margin = 3
        knob_x = switch_x + switch_w - knob_d - knob_margin if not self.isChecked() else switch_x + knob_margin
        knob_rect = QRectF(knob_x, y + knob_margin, knob_d, knob_d)
        painter.setBrush(QBrush(qcolor_from_css(TEXT_COLOR if self.isChecked() else BG_ELEVATED_COLOR)))
        painter.setPen(QPen(qcolor_from_css("rgba(255,255,255,0.46)" if self.isChecked() else SOFT_LINE_COLOR), 1))
        painter.drawEllipse(knob_rect)

        text_left = switch_w + (44 if self._smarti_info_reserved else 16)
        text_rect = QRectF(text_left, 0, max(1, self.width() - text_left - 2), self.height())
        painter.setPen(qcolor_from_css(TEXT_COLOR if self.isEnabled() else SUBTLE_TEXT_COLOR))
        painter.setFont(self.font())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute, self.text())
        painter.end()

class RtlFillSlider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)
        self.setMinimumHeight(48)
        self.setPageStep(1)

    def _track_rect(self):
        track_h = 30
        margin_x = 4
        return QRectF(margin_x, (self.height() - track_h) / 2, max(1, self.width() - margin_x * 2), track_h)

    def _value_from_x(self, x):
        rect = self._track_rect()
        ratio = (rect.right() - float(x)) / max(1.0, rect.width())
        ratio = max(0.0, min(1.0, ratio))
        return self.minimum() + round(ratio * (self.maximum() - self.minimum()))

    def _ancestor_scroll_area(self):
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def _forward_wheel_to_scroll_area(self, event):
        scroll_area = self._ancestor_scroll_area()
        if not scroll_area:
            return False
        bar = scroll_area.verticalScrollBar()
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()
        if not pixel_delta.isNull() and pixel_delta.y():
            delta = pixel_delta.y()
        elif angle_delta.y():
            delta = (angle_delta.y() / 120.0) * max(24, bar.singleStep() * 3)
        else:
            return False
        bar.setValue(bar.value() - int(delta))
        event.accept()
        return True

    def event(self, event):
        if event.type() == QEvent.Type.Wheel and self._forward_wheel_to_scroll_area(event):
            return True
        return super().event(event)

    def wheelEvent(self, event):
        if not self._forward_wheel_to_scroll_area(event):
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setSliderDown(True)
            self.setValue(self._value_from_x(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown() and self.isEnabled():
            self.setValue(self._value_from_x(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setValue(self._value_from_x(event.position().x()))
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self._track_rect()
        radius = rect.height() / 2

        track_path = QPainterPath()
        track_path.addRoundedRect(rect, radius, radius)
        painter.fillPath(track_path, qcolor_from_css(PANEL_ELEVATED_COLOR if self.isEnabled() else FIELD_COLOR))

        span = max(1, self.maximum() - self.minimum())
        ratio = (self.value() - self.minimum()) / span
        fill_w = rect.width() * max(0.0, min(1.0, ratio))
        if fill_w > 0:
            fill_rect = QRectF(rect.right() - fill_w, rect.top(), fill_w, rect.height())
            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill_rect, radius, radius)
            gradient = QLinearGradient(fill_rect.topRight(), fill_rect.topLeft())
            gradient.setColorAt(0.0, qcolor_from_css(ACCENT_COLOR))
            gradient.setColorAt(0.56, qcolor_from_css(ACCENT_PINK_COLOR))
            gradient.setColorAt(1.0, qcolor_from_css(ACCENT_SECONDARY_COLOR))
            painter.fillPath(fill_path.intersected(track_path), QBrush(gradient))

        pen = QPen(qcolor_from_css(SOFT_LINE_COLOR))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(track_path)
        painter.end()

class SettingsNavCard(QFrame):
    def __init__(self, title, subtitle, callback):
        super().__init__()
        self.callback = callback
        self.setObjectName("SettingsNavCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumHeight(86)
        self.setStyleSheet(NAV_CARD_CSS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)
        self.title_lbl = QLabel(title)
        self.title_lbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.title_lbl.setMinimumWidth(1)
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.subtitle_lbl = QLabel(subtitle)
        self.subtitle_lbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.subtitle_lbl.setMinimumWidth(1)
        self.subtitle_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.subtitle_lbl.setWordWrap(True)
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.subtitle_lbl)
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(NAV_CARD_CSS)
        self.title_lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 15px; font-weight: 700; background: transparent; border: none;")
        self.subtitle_lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px; background: transparent; border: none;")
        apply_soft_shadow(self, blur=24, y=7, alpha=32)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.callback:
            self.callback()
        super().mousePressEvent(event)

class AnimatedStackedWidget(QStackedWidget):
    def __init__(self, *args, duration=330, **kwargs):
        super().__init__(*args, **kwargs)
        self._transition_duration = duration
        self._transition_animations = []

    def setCurrentWidget(self, widget):
        if widget is self.currentWidget():
            return
        super().setCurrentWidget(widget)
        self._animate_current_widget()

    def setCurrentIndex(self, index):
        if index == self.currentIndex():
            return
        super().setCurrentIndex(index)
        self._animate_current_widget()

    def _animate_current_widget(self):
        widget = self.currentWidget()
        if not widget:
            return
        end_pos = widget.pos()
        slide_offset = -26 if self.layoutDirection() == Qt.LayoutDirection.RightToLeft else 26
        widget.move(end_pos + QPoint(slide_offset, 0))

        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

        fade_anim = QPropertyAnimation(effect, b"opacity", widget)
        fade_anim.setDuration(self._transition_duration)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        slide_anim = QPropertyAnimation(widget, b"pos", widget)
        slide_anim.setDuration(self._transition_duration)
        slide_anim.setStartValue(widget.pos())
        slide_anim.setEndValue(end_pos)
        slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._transition_animations.extend([fade_anim, slide_anim])

        def cleanup():
            widget.move(end_pos)
            widget.setGraphicsEffect(None)
            for anim in (fade_anim, slide_anim):
                try:
                    self._transition_animations.remove(anim)
                except ValueError:
                    pass

        fade_anim.finished.connect(cleanup)
        fade_anim.start()
        slide_anim.start()

class ShimmerLabel(QLabel):
    def __init__(self, text=""):
        super().__init__("")
        self._shimmer_clock = QElapsedTimer()
        self._shimmer_cycle_ms = 1550
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(16)
        self._shimmer_timer.timeout.connect(self._advance_shimmer)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        if str(text or "").strip():
            if not self._shimmer_timer.isActive():
                self._shimmer_clock.restart()
                self._shimmer_timer.start()
        else:
            self._shimmer_timer.stop()
        self.update()

    def _advance_shimmer(self):
        self.update()

    def paintEvent(self, event):
        text = self.text()
        if not text or not self._shimmer_timer.isActive():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self.font())
        rect = self.contentsRect()
        flags = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter
        painter.setPen(QColor(ACCENT_COLOR))
        painter.drawText(rect, flags, text)

        shimmer_width = max(78, int(rect.width() * 0.34))
        phase = (self._shimmer_clock.elapsed() % self._shimmer_cycle_ms) / self._shimmer_cycle_ms
        distance = rect.width() + shimmer_width * 2
        x = rect.right() + shimmer_width - int(distance * phase)
        clip = rect.adjusted(0, 0, 0, 0)
        clip.setLeft(x)
        clip.setWidth(shimmer_width)
        painter.setClipRect(clip)
        gradient = QLinearGradient(float(x), 0.0, float(x + shimmer_width), 0.0)
        gradient.setColorAt(0.00, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.24, QColor(255, 255, 255, 70))
        gradient.setColorAt(0.50, QColor(255, 255, 255, 225))
        gradient.setColorAt(0.76, QColor(255, 255, 255, 70))
        gradient.setColorAt(1.00, QColor(255, 255, 255, 0))
        painter.setPen(QPen(QBrush(gradient), 1))
        painter.drawText(rect, flags, text)
        painter.end()

class StepsShimmerEffect(QGraphicsEffect):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._shimmer_clock = QElapsedTimer()
        self._shimmer_cycle_ms = 1650
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(16)
        self._shimmer_timer.timeout.connect(self.update)
        self._is_active = False
        self._mask_cache_key = None
        self._mask_cache = QPixmap()

    def start_shimmer(self):
        self._is_active = True
        if not self._shimmer_timer.isActive():
            self._shimmer_clock.restart()
            self._shimmer_timer.start()
        self.update()

    def stop_shimmer(self):
        self._is_active = False
        if self._shimmer_timer.isActive():
            self._shimmer_timer.stop()
        self.update()

    def _text_mask_from_source(self, source):
        cache_key = source.cacheKey()
        if self._mask_cache_key == cache_key and not self._mask_cache.isNull():
            return self._mask_cache

        image = source.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        mask_image = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
        mask_image.fill(Qt.GlobalColor.transparent)

        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                if color.alpha() > 0 and (color.red() + color.green() + color.blue()) > 120:
                    mask_image.setPixelColor(x, y, QColor(255, 255, 255, color.alpha()))

        self._mask_cache_key = cache_key
        self._mask_cache = QPixmap.fromImage(mask_image)
        self._mask_cache.setDevicePixelRatio(source.devicePixelRatio())
        return self._mask_cache

    def draw(self, painter):
        source, offset = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates)
        if source.isNull():
            return
        painter.drawPixmap(offset, source)

        if not self._is_active:
            return

        rect = source.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        mask = self._text_mask_from_source(source)
        if mask.isNull():
            return

        dpr = source.devicePixelRatio()
        logical_size = source.deviceIndependentSize()
        logical_rect = QRectF(0.0, 0.0, logical_size.width(), logical_size.height())
        shimmer_width = max(88, int(logical_rect.width() * 0.36))
        phase = (self._shimmer_clock.elapsed() % self._shimmer_cycle_ms) / self._shimmer_cycle_ms
        distance = logical_rect.width() + shimmer_width * 2
        x = logical_rect.right() + shimmer_width - (distance * phase)

        gradient = QLinearGradient(float(x), 0.0, float(x + shimmer_width), 0.0)
        gradient.setColorAt(0.00, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.18, QColor(255, 255, 255, 24))
        gradient.setColorAt(0.50, QColor(255, 255, 255, 155))
        gradient.setColorAt(0.82, QColor(255, 255, 255, 24))
        gradient.setColorAt(1.00, QColor(255, 255, 255, 0))

        overlay = QPixmap(source.size())
        overlay.setDevicePixelRatio(dpr)
        overlay.fill(Qt.GlobalColor.transparent)
        overlay_painter = QPainter(overlay)
        overlay_painter.fillRect(logical_rect, QBrush(gradient))
        overlay_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        overlay_painter.drawPixmap(0, 0, mask)
        overlay_painter.end()

        painter.drawPixmap(offset, overlay)

class StepsShimmerLabel(QLabel):
    def __init__(self):
        super().__init__()
        self._shimmer_effect = StepsShimmerEffect(self)
        self.setGraphicsEffect(self._shimmer_effect)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignTop)

    def start_shimmer(self):
        if str(self.text() or "").strip():
            self._shimmer_effect.start_shimmer()

    def stop_shimmer(self):
        self._shimmer_effect.stop_shimmer()

class DirectoryPicker(QWidget):
    pathsChanged = pyqtSignal()

    def __init__(self, paths=None, *, allow_multiple=False, dialog_title="בחר תיקייה", default_path=""):
        super().__init__()
        self.allow_multiple = allow_multiple
        self.dialog_title = dialog_title
        self.default_path = default_path or os.path.expanduser("~")
        self._paths = []
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.path_frame = QFrame()
        self.path_frame.setObjectName("DirectoryPickerPathFrame")
        self.path_frame.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        path_layout = QHBoxLayout(self.path_frame)
        path_layout.setContentsMargins(10, 6, 6, 6)
        path_layout.setSpacing(8)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.path_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.path_edit.setMinimumWidth(1)
        self.path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.path_label = self.path_edit
        path_layout.addWidget(self.path_edit, 1)

        self.choose_btn = QPushButton()
        self.choose_btn.setFixedSize(34, 34)
        self.choose_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.choose_btn.setToolTip("בחר תיקייה" if not allow_multiple else "הוסף תיקייה")
        self.choose_btn.clicked.connect(self.choose_directory)
        path_layout.addWidget(self.choose_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.path_frame)

        if allow_multiple:
            self.clear_btn = QPushButton("נקה")
            self.clear_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
            self.clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.clear_btn.clicked.connect(self.clear_paths)
            layout.addWidget(self.clear_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.apply_theme()
        self.set_paths(paths or [])

    def apply_theme(self):
        self.path_frame.setStyleSheet(f"""
            QFrame#DirectoryPickerPathFrame {{
                background: {GLASS_COLOR}; color: {FIELD_TEXT_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 20px;
            }}
        """)
        self.path_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {FIELD_TEXT_COLOR};
                border: none;
                padding: 6px 4px;
                font-size: 13px;
            }}
        """)
        set_themed_button_icon(
            self.choose_btn,
            ("folder_icon", "directory_icon", "choose_folder_icon", "open_folder_icon", "file_icon"),
            "",
            20,
            clear_text=True,
        )
        self.choose_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 17px; padding: 0px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; border: none; }}"
            f"QPushButton:pressed {{ background: {ACCENT_TINT}; border: none; }}"
        )
        if hasattr(self, "clear_btn"):
            self.clear_btn.setStyleSheet(SECONDARY_BUTTON_CSS)

    def set_paths(self, paths):
        if isinstance(paths, str):
            paths = [paths]
        cleaned = []
        for path in paths or []:
            path = str(path or "").strip()
            if path and path not in cleaned:
                cleaned.append(path)
        self._paths = cleaned[:1] if not self.allow_multiple else cleaned
        self._refresh_label()

    def paths(self):
        return list(self._paths)

    def path(self):
        return self._paths[0] if self._paths else ""

    def choose_directory(self):
        start = self.path() or self.default_path
        selected = QFileDialog.getExistingDirectory(self, self.dialog_title, start)
        if selected:
            if self.allow_multiple:
                if selected not in self._paths:
                    self._paths.append(selected)
            else:
                self._paths = [selected]
            self._refresh_label()
            self.pathsChanged.emit()

    def clear_paths(self):
        self._paths = []
        self._refresh_label()
        self.pathsChanged.emit()

    def _refresh_label(self):
        if self._paths:
            display_paths = [
                path.replace("\\", "\\\u200b").replace("/", "/\u200b")
                for path in self._paths
            ]
            self.path_edit.setText("   ".join(display_paths))
        else:
            self.path_edit.setText("לא נבחרה תיקייה")

class ExpandingTextEdit(QTextEdit):
    send_signal = pyqtSignal()
    files_pasted = pyqtSignal(list)
    image_pasted = pyqtSignal(object)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_aligning = False
        self._placeholder_text = ""
        self.setAcceptRichText(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setCursorWidth(2)
        self.setViewportMargins(0, 4, 0, 0)
        doc = self.document()
        option = doc.defaultTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignLeft)
        option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        doc.setDefaultTextOption(option)
        self.viewport().setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cursor = self.textCursor()
        fmt = cursor.blockFormat()
        fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        fmt.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        cursor.setBlockFormat(fmt)
        self.setTextCursor(cursor)
        self.document().setDocumentMargin(16)
        self.document().documentLayout().documentSizeChanged.connect(self.adjust_height)
        self.max_height = 156
        self.min_height = 64
        self.setFixedHeight(self.min_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.textChanged.connect(self._force_rtl_alignment)
        self.textChanged.connect(lambda: QTimer.singleShot(0, self.adjust_height))

    def setPlaceholderText(self, text):
        self._placeholder_text = str(text or "")
        super().setPlaceholderText("")
        self.viewport().update()

    def placeholderText(self):
        return self._placeholder_text

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.toPlainText() or not self._placeholder_text:
            return
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(QColor(SUBTLE_TEXT_COLOR))
        painter.setFont(self.font())
        margin = int(self.document().documentMargin())
        rect = self.viewport().rect().adjusted(margin, 2, -margin, 0)
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter,
            self._placeholder_text
        )
        painter.end()

    def _force_rtl_alignment(self):
        if getattr(self, '_is_aligning', False): return
        self._is_aligning = True
        doc = self.document()
        previous_widget_signal_state = self.blockSignals(True)
        previous_doc_signal_state = doc.blockSignals(True)
        try:
            self.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.viewport().setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            option = doc.defaultTextOption()
            if (
                option.alignment() != Qt.AlignmentFlag.AlignLeft
                or option.textDirection() != Qt.LayoutDirection.RightToLeft
                or option.wrapMode() != QTextOption.WrapMode.WordWrap
            ):
                option.setAlignment(Qt.AlignmentFlag.AlignLeft)
                option.setTextDirection(Qt.LayoutDirection.RightToLeft)
                option.setWrapMode(QTextOption.WrapMode.WordWrap)
                doc.setDefaultTextOption(option)

            original_cursor = self.textCursor()
            format_cursor = QTextCursor(doc)
            needs_cursor_restore = False
            block = doc.firstBlock()
            while block.isValid():
                fmt = block.blockFormat()
                if fmt.layoutDirection() != Qt.LayoutDirection.RightToLeft or fmt.alignment() != Qt.AlignmentFlag.AlignLeft:
                    format_cursor.setPosition(block.position())
                    fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    fmt.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                    format_cursor.setBlockFormat(fmt)
                    needs_cursor_restore = True
                block = block.next()
            if needs_cursor_restore:
                self.setTextCursor(original_cursor)
        finally:
            doc.blockSignals(previous_doc_signal_state)
            self.blockSignals(previous_widget_signal_state)
            self._is_aligning = False

    def clear(self):
        super().clear()
        self._force_rtl_alignment()
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
        self.setFixedHeight(self.min_height)
        QTimer.singleShot(0, self.adjust_height)
        
    def adjust_height(self):
        doc_height = int(self.document().size().height())
        margins = self.contentsMargins()
        target_height = doc_height + margins.top() + margins.bottom()
        if target_height < self.min_height: target_height = self.min_height
        needs_scroll = target_height > self.max_height
        if needs_scroll:
            target_height = self.max_height
        desired_policy = (
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if needs_scroll
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if self.verticalScrollBarPolicy() != desired_policy:
            self.setVerticalScrollBarPolicy(desired_policy)
        if not needs_scroll:
            self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
        if self.height() != target_height: self.setFixedHeight(target_height)
        self.viewport().update()
            
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier: super().keyPressEvent(event)
            else: self.send_signal.emit()
        elif event.key() == Qt.Key.Key_Down:
            cursor = self.textCursor()
            old_pos = cursor.position()
            cursor.movePosition(cursor.MoveOperation.Down)
            if cursor.position() == old_pos: cursor.movePosition(cursor.MoveOperation.End)
            self.setTextCursor(cursor)
        elif event.key() == Qt.Key.Key_Up:
            cursor = self.textCursor()
            old_pos = cursor.position()
            cursor.movePosition(cursor.MoveOperation.Up)
            if cursor.position() == old_pos: cursor.movePosition(cursor.MoveOperation.Start)
            self.setTextCursor(cursor)
        else:
            super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        handled_attachment = False
        try:
            if source.hasUrls():
                paths = []
                for url in source.urls():
                    if url.isLocalFile():
                        path = url.toLocalFile()
                        if path and os.path.isfile(path):
                            paths.append(path)
                if paths:
                    self.files_pasted.emit(paths)
                    handled_attachment = True
            if source.hasImage():
                image = source.imageData()
                if isinstance(image, QImage) and not image.isNull():
                    self.image_pasted.emit(image)
                    handled_attachment = True
        except Exception as e:
            logging.warning(f"Paste attachment handling failed: {e}")
        if source.hasText() and not handled_attachment:
            super().insertFromMimeData(source)
        elif not handled_attachment:
            super().insertFromMimeData(source)


__all__ = [name for name in globals() if not name.startswith("__")]
