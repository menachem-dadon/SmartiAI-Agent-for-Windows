"""Settings, tools, usage, task-center, trace, and about pages."""
from .common import *
from .config import *
from .ui_styles import *
from .ui_controls import *
from .workers import FetchModelsWorker, ApiKeyValidationWorker
from PyQt6.QtGui import QKeySequence, QShortcut

def refresh_back_button_icon(btn):
    btn.setProperty("smartiBackButton", True)
    btn.setFixedSize(38, 38)
    set_themed_button_icon(btn, ("back_icon",), "<", 26, clear_text=True)
    btn.setStyleSheet(icon_button_css(38))

def create_back_button(target_page_func):
    btn = QPushButton()
    refresh_back_button_icon(btn)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.clicked.connect(target_page_func)
    return btn

def high_contrast_link_color():
    return "#FFF2A8" if CURRENT_THEME == "dark" else "#006DCC"

def high_contrast_link_markup(url, text):
    color = high_contrast_link_color()
    safe_url = html.escape(str(url or ""), quote=True)
    safe_text = html.escape(str(text or ""))
    style = f"color: {color}; text-decoration: underline; font-weight: 800;"
    return f'<a href="{safe_url}" style="{style}"><span style="{style}">{safe_text}</span></a>'

def apply_high_contrast_link_label(label, size=12):
    color = high_contrast_link_color()
    label.setProperty("smartiHighContrastLink", True)
    label.setStyleSheet(
        f"QLabel {{ background: transparent; color: {color}; font-size: {int(size)}px; font-weight: 800; }}"
        f"a {{ color: {color}; text-decoration: underline; font-weight: 800; }}"
    )
    palette = label.palette()
    palette.setColor(QPalette.ColorRole.Link, QColor(color))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(color))
    label.setPalette(palette)

BUILTIN_TOOL_DISPLAY_LABELS = {
    "get_tool_info": "מידע על כלי וסכמות",
    "system_manager": "ניהול מערכת",
    "software_manager": "ניהול תוכנות",
    "file_manager": "ניהול קבצים",
    "web_manager": "אינטרנט ואתרים",
    "screen_manager": "צילום וניתוח מסך",
    "background_task_manager": "משימות רקע",
    "notification_manager": "התראות ותזכורות",
    "memory_manager": "ניהול זיכרון",
    "email_manager": "ניהול דוא\"ל",
    "automation_manager": "אוטומציה בדפדפן ובמחשב",
    "extension_manager": "ניהול הרחבות, MCP ו-Skills",
    "create_python_tool": "יצירת כלי Python מותאם",
    "system_command": "הרצת פקודת מערכת",
    "git_status": "בדיקת מצב Git",
    "run_project_check": "בדיקת פרויקט",
    "list_processes": "רשימת תהליכים",
    "set_clipboard": "עדכון לוח העתקה",
    "set_volume": "שינוי עוצמת שמע",
    "open_software": "פתיחת תוכנה",
    "list_software": "רשימת תוכנות",
    "open_file_or_folder": "פתיחת קובץ או תיקייה",
    "save_text_file": "שמירת קובץ טקסט",
    "read_local_document": "קריאת מסמך מקומי",
    "smart_file_search": "חיפוש קבצים חכם",
    "deep_content_search": "חיפוש עמוק בתוכן",
    "extract_image_text": "חילוץ טקסט מתמונה",
    "internet_search": "חיפוש באינטרנט",
    "read_website": "קריאת אתר",
    "open_in_browser": "פתיחה בדפדפן",
    "get_weather": "בדיקת מזג אוויר",
    "capture_screen": "לכידת מסך",
    "save_screenshot_to_disk": "שמירת צילום מסך",
    "analyze_local_image": "ניתוח תמונה מקומית",
    "schedule_background_task": "תזמון משימת רקע",
    "list_background_tasks": "רשימת משימות רקע",
    "cancel_background_task": "ביטול משימת רקע",
    "retry_background_task": "הרצת משימת רקע מחדש",
    "search_memory": "חיפוש בזיכרון",
    "update_memory": "עדכון זיכרון",
    "search_mcp": "חיפוש כלי MCP",
    "install_mcp": "התקנת כלי MCP",
    "run_mcp": "הרצת כלי MCP",
    "list_skills": "רשימת מיומנויות",
    "search_skills": "חיפוש מיומנויות",
    "install_skill": "התקנת מיומנות",
    "install_skill_requirements": "התקנת דרישות מיומנות",
    "run_skill": "הרצת מיומנות",
    "browser_automation": "אוטומציית דפדפן",
    "close_automation_browser": "סגירת דפדפן אוטומציה",
    "computer_automation": "אוטומציית מחשב",
}

TOOL_CATEGORY_DISPLAY_LABELS = {
    "schema": "מידע ועזרה",
    "system": "מערכת",
    "software": "תוכנות",
    "files": "קבצים",
    "web": "אינטרנט",
    "screen": "מסך",
    "tasks": "משימות רקע",
    "memory": "זיכרון",
    "email": "דוא\"ל",
    "automation": "אוטומציה",
    "extensions": "הרחבות",
    "developer": "מפתחים",
}

class ActionConfirmDialog(QDialog):
    def __init__(self, title, details, risk="medium", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setModal(True)
        width, height = self._initial_size(parent)
        self.setMinimumSize(min(340, width), min(300, height))
        self.resize(width, height)
        self.setStyleSheet(self._stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ActionConfirmCard")
        apply_soft_shadow(card, blur=24, y=7, alpha=36)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(8)
        layout.addWidget(card)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon = QLabel("!")
        icon.setObjectName("ActionConfirmIcon")
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)

        eyebrow = QLabel("בקשת הרשאה")
        eyebrow.setObjectName("ActionConfirmEyebrow")
        header_text.addWidget(eyebrow)

        header = QLabel(str(title or "אישור פעולה"))
        header.setObjectName("ActionConfirmTitle")
        header.setWordWrap(True)
        header_text.addWidget(header)

        risk_text, risk_tone = self._risk_display(risk)
        risk_lbl = QLabel(risk_text)
        risk_lbl.setObjectName("ActionConfirmRisk")
        risk_lbl.setStyleSheet(self._risk_badge_css(risk_tone))
        header_text.addWidget(risk_lbl, 0, Qt.AlignmentFlag.AlignRight)

        header_row.addLayout(header_text, 1)
        card_layout.addLayout(header_row)

        details_title = QLabel("פרטי הפעולה")
        details_title.setObjectName("ActionConfirmSectionTitle")
        card_layout.addWidget(details_title)

        preview = QTextEdit()
        preview.setObjectName("ActionConfirmDetails")
        preview.setReadOnly(True)
        preview.setMinimumHeight(105)
        preview.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        preview.setPlainText(str(details or ""))
        preview.verticalScrollBar().setStyleSheet(SCROLLBAR_CSS)
        preview.horizontalScrollBar().setStyleSheet(SCROLLBAR_CSS)
        card_layout.addWidget(preview, 1)

        hint_frame = QFrame()
        hint_frame.setObjectName("ActionConfirmHintFrame")
        hint_layout = QHBoxLayout(hint_frame)
        hint_layout.setContentsMargins(10, 7, 10, 7)
        hint_layout.setSpacing(6)
        hint = QLabel("אשר רק אם הפעולה תואמת למה שביקשת מסמארטי לבצע.")
        hint.setObjectName("ActionConfirmHint")
        hint.setWordWrap(True)
        hint_layout.addWidget(hint)
        card_layout.addWidget(hint_frame)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(8)
        actions.addStretch()

        self.reject_btn = QPushButton("דחה")
        self.reject_btn.setObjectName("ActionConfirmRejectButton")
        self.reject_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.reject_btn.setAutoDefault(False)
        self.reject_btn.clicked.connect(self.reject)
        actions.addWidget(self.reject_btn)

        self.accept_btn = QPushButton("אשר")
        self.accept_btn.setObjectName("ActionConfirmAcceptButton")
        self.accept_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.accept_btn.setDefault(True)
        self.accept_btn.setAutoDefault(True)
        self.accept_btn.clicked.connect(self.accept)
        actions.addWidget(self.accept_btn)

        card_layout.addLayout(actions)
        self.accept_btn.setFocus(Qt.FocusReason.OtherFocusReason)

        self._enter_shortcuts = []
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(self.accept)
            self._enter_shortcuts.append(shortcut)

    def _initial_size(self, parent):
        width, height = 430, 340
        if parent is None:
            return width, height
        try:
            parent_size = parent.size()
            parent_w = int(parent_size.width())
            parent_h = int(parent_size.height())
            if parent_w > 0:
                width = min(width, max(350, int(parent_w * 0.86)))
            if parent_h > 0:
                height = min(height, max(310, int(parent_h * 0.78)))
        except Exception:
            pass
        return width, height

    def _risk_display(self, risk):
        risk = str(risk or "medium").strip().lower()
        if risk == "high":
            return "סיכון גבוה", "high"
        if risk == "low":
            return "סיכון נמוך", "low"
        return "סיכון בינוני", "medium"

    def _risk_badge_css(self, tone):
        if tone == "high":
            color = DANGER_COLOR
            bg = "rgba(240,90,110,0.16)"
            border = "rgba(240,90,110,0.38)"
        elif tone == "low":
            color = ACCENT_SECONDARY_COLOR
            bg = "rgba(90,242,194,0.13)"
            border = "rgba(90,242,194,0.30)"
        else:
            color = ACCENT_WARM_COLOR
            bg = "rgba(255,184,107,0.15)"
            border = "rgba(255,184,107,0.34)"
        return f"""
            QLabel#ActionConfirmRisk {{
                color: {color};
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 4px 9px;
                font-size: 11px;
                font-weight: 800;
            }}
        """

    def _stylesheet(self):
        return dialog_stylesheet() + f"""
            QFrame#ActionConfirmCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {GLASS_STRONG_COLOR}, stop:1 {CARD_GRADIENT_END});
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 20px;
            }}
            QLabel#ActionConfirmIcon {{
                color: {ACCENT_TEXT_COLOR};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
                border: none;
                border-radius: 17px;
                font-size: 18px;
                font-weight: 900;
            }}
            QLabel#ActionConfirmEyebrow {{
                color: {ACCENT_SECONDARY_COLOR};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0px;
                background: transparent;
            }}
            QLabel#ActionConfirmTitle {{
                color: {TEXT_COLOR};
                font-size: 17px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#ActionConfirmSectionTitle {{
                color: {TEXT_COLOR};
                font-size: 12px;
                font-weight: 800;
                background: transparent;
            }}
            QTextEdit#ActionConfirmDetails {{
                background: {GLASS_COLOR};
                color: {FIELD_TEXT_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 14px;
                padding: 8px;
                font-size: 12px;
                selection-background-color: {ACCENT_TINT_STRONG};
                selection-color: {TEXT_COLOR};
            }}
            QTextEdit#ActionConfirmDetails:focus {{
                background: {FIELD_HOVER_COLOR};
                border-color: {ACCENT_COLOR};
            }}
            QTextEdit#ActionConfirmDetails viewport {{
                background: transparent;
                color: {FIELD_TEXT_COLOR};
            }}
            QFrame#ActionConfirmHintFrame {{
                background: {ACCENT_TINT};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 12px;
            }}
            QLabel#ActionConfirmHint {{
                color: {MUTED_TEXT_COLOR};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
            QPushButton#ActionConfirmAcceptButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
                color: {ACCENT_TEXT_COLOR};
                border: none;
                border-radius: 16px;
                padding: 9px 15px;
                min-width: 88px;
                font-size: 13px;
                font-weight: 800;
            }}
            QPushButton#ActionConfirmAcceptButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {BRAND_ACCENT_COLOR}, stop:0.52 {BRAND_PINK_COLOR}, stop:1 {BRAND_SECONDARY_COLOR});
            }}
            QPushButton#ActionConfirmAcceptButton:pressed {{
                background: {ACCENT_COLOR};
                padding-top: 10px;
                padding-bottom: 8px;
            }}
            QPushButton#ActionConfirmRejectButton {{
                background: rgba(240,90,110,0.13);
                color: {DANGER_COLOR};
                border: none;
                border-radius: 16px;
                padding: 9px 14px;
                min-width: 74px;
                font-size: 13px;
                font-weight: 800;
            }}
            QPushButton#ActionConfirmRejectButton:hover {{
                background: rgba(240,90,110,0.20);
            }}
            QPushButton#ActionConfirmRejectButton:pressed {{
                background: rgba(240,90,110,0.28);
                padding-top: 10px;
                padding-bottom: 8px;
            }}
        """

class ToolDeleteConfirmDialog(QDialog):
    def __init__(self, title, details, artifact_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setModal(True)
        width, height = self._initial_size(parent)
        self.setMinimumSize(min(340, width), min(280, height))
        self.resize(width, height)
        self.setStyleSheet(self._stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ToolDeleteCard")
        apply_soft_shadow(card, blur=24, y=7, alpha=38)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(9)
        layout.addWidget(card)

        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon = QLabel()
        icon.setObjectName("ToolDeleteIcon")
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_themed_label_icon(icon, ("delete_icon",), "X", 20)
        header_row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        header_text = QVBoxLayout()
        header_text.setSpacing(3)
        eyebrow = QLabel("מחיקת פריט חיצוני")
        eyebrow.setObjectName("ToolDeleteEyebrow")
        header_text.addWidget(eyebrow)

        header = QLabel(str(title or "מחיקת כלי"))
        header.setObjectName("ToolDeleteTitle")
        header.setWordWrap(True)
        header_text.addWidget(header)

        if artifact_name:
            name_lbl = QLabel(str(artifact_name))
            name_lbl.setObjectName("ToolDeleteName")
            name_lbl.setWordWrap(True)
            header_text.addWidget(name_lbl)

        header_row.addLayout(header_text, 1)
        card_layout.addLayout(header_row)

        warning = QLabel("הפעולה תמחק קבצים ורישומי אמון/הפעלה של הפריט. אי אפשר לשחזר אותה מתוך סמארטי.")
        warning.setObjectName("ToolDeleteWarning")
        warning.setWordWrap(True)
        card_layout.addWidget(warning)

        details_title = QLabel("מה יימחק")
        details_title.setObjectName("ToolDeleteSectionTitle")
        card_layout.addWidget(details_title)

        preview = QTextEdit()
        preview.setObjectName("ToolDeleteDetails")
        preview.setReadOnly(True)
        preview.setMinimumHeight(105)
        preview.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        preview.setPlainText(str(details or ""))
        preview.verticalScrollBar().setStyleSheet(SCROLLBAR_CSS)
        preview.horizontalScrollBar().setStyleSheet(SCROLLBAR_CSS)
        card_layout.addWidget(preview, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 0)
        actions.setSpacing(8)
        actions.addStretch()

        self.reject_btn = QPushButton("בטל")
        self.reject_btn.setObjectName("ToolDeleteCancelButton")
        self.reject_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.reject_btn.setAutoDefault(False)
        self.reject_btn.clicked.connect(self.reject)
        actions.addWidget(self.reject_btn)

        self.accept_btn = QPushButton("מחק")
        self.accept_btn.setObjectName("ToolDeleteAcceptButton")
        self.accept_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.accept_btn.setDefault(True)
        self.accept_btn.setAutoDefault(True)
        self.accept_btn.clicked.connect(self.accept)
        actions.addWidget(self.accept_btn)

        card_layout.addLayout(actions)
        self.reject_btn.setFocus(Qt.FocusReason.OtherFocusReason)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_inside_parent_window()

    def _parent_window(self):
        parent = self.parent()
        if parent is None:
            return None
        try:
            return parent.window()
        except Exception:
            return parent

    def _parent_bounds(self):
        parent_window = self._parent_window()
        if parent_window is None:
            return None
        try:
            return parent_window.frameGeometry() if parent_window.isVisible() else parent_window.geometry()
        except Exception:
            return None

    def _initial_size(self, parent):
        width, height = 460, 360
        if parent is None:
            return width, height
        try:
            parent_window = parent.window()
            parent_size = parent_window.size() if parent_window is not None else parent.size()
            parent_w = int(parent_size.width())
            parent_h = int(parent_size.height())
            if parent_w > 0:
                width = min(width, max(260, parent_w - 36))
            if parent_h > 0:
                height = min(height, max(240, parent_h - 36))
        except Exception:
            pass
        return width, height

    def _fit_inside_parent_window(self):
        bounds = self._parent_bounds()
        if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
            return

        margin = 12
        max_width = max(240, int(bounds.width()) - (margin * 2))
        max_height = max(220, int(bounds.height()) - (margin * 2))
        if self.width() > max_width or self.height() > max_height:
            self.resize(min(self.width(), max_width), min(self.height(), max_height))

        x = bounds.x() + max(margin, (bounds.width() - self.width()) // 2)
        y = bounds.y() + max(margin, (bounds.height() - self.height()) // 2)
        min_x = bounds.x() + margin
        min_y = bounds.y() + margin
        max_x = bounds.x() + bounds.width() - self.width() - margin
        max_y = bounds.y() + bounds.height() - self.height() - margin
        if max_x >= min_x:
            x = max(min_x, min(x, max_x))
        if max_y >= min_y:
            y = max(min_y, min(y, max_y))
        self.move(x, y)

    def _stylesheet(self):
        return dialog_stylesheet() + f"""
            QFrame#ToolDeleteCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {GLASS_STRONG_COLOR}, stop:1 {CARD_GRADIENT_END});
                border: 1px solid rgba(240,90,110,0.34);
                border-radius: 20px;
            }}
            QLabel#ToolDeleteIcon {{
                background: rgba(240,90,110,0.16);
                border: 1px solid rgba(240,90,110,0.38);
                border-radius: 18px;
            }}
            QLabel#ToolDeleteEyebrow {{
                color: {DANGER_COLOR};
                font-size: 11px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#ToolDeleteTitle {{
                color: {TEXT_COLOR};
                font-size: 17px;
                font-weight: 800;
                background: transparent;
            }}
            QLabel#ToolDeleteName {{
                color: {MUTED_TEXT_COLOR};
                font-size: 12px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#ToolDeleteWarning {{
                color: {DANGER_COLOR};
                background: rgba(240,90,110,0.12);
                border: 1px solid rgba(240,90,110,0.28);
                border-radius: 12px;
                padding: 8px 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#ToolDeleteSectionTitle {{
                color: {TEXT_COLOR};
                font-size: 12px;
                font-weight: 800;
                background: transparent;
            }}
            QTextEdit#ToolDeleteDetails {{
                background: {GLASS_COLOR};
                color: {FIELD_TEXT_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 14px;
                padding: 8px;
                font-size: 12px;
                selection-background-color: {ACCENT_TINT_STRONG};
                selection-color: {TEXT_COLOR};
            }}
            QTextEdit#ToolDeleteDetails viewport {{
                background: transparent;
                color: {FIELD_TEXT_COLOR};
            }}
            QPushButton#ToolDeleteAcceptButton {{
                background: rgba(240,90,110,0.18);
                color: {DANGER_COLOR};
                border: none;
                border-radius: 16px;
                padding: 9px 15px;
                min-width: 88px;
                font-size: 13px;
                font-weight: 800;
            }}
            QPushButton#ToolDeleteAcceptButton:hover {{
                background: rgba(240,90,110,0.26);
            }}
            QPushButton#ToolDeleteAcceptButton:pressed {{
                background: rgba(240,90,110,0.34);
                padding-top: 10px;
                padding-bottom: 8px;
            }}
            QPushButton#ToolDeleteCancelButton {{
                background: {ACCENT_TINT};
                color: {TEXT_COLOR};
                border: none;
                border-radius: 16px;
                padding: 9px 14px;
                min-width: 74px;
                font-size: 13px;
                font-weight: 800;
            }}
            QPushButton#ToolDeleteCancelButton:hover {{
                background: {HOVER_TINT};
            }}
            QPushButton#ToolDeleteCancelButton:pressed {{
                background: {ACCENT_TINT_STRONG};
                padding-top: 10px;
                padding-bottom: 8px;
            }}
        """

class ApiKeyRequiredDialog(QDialog):
    def __init__(self, secret_key, provider_label, title, message, help_url="", parent=None):
        super().__init__(parent)
        self.secret_key = secret_key
        self.help_url = help_url
        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(460)
        self.setStyleSheet(dialog_stylesheet() + LINE_EDIT_CSS)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        header = QLabel(title)
        header.setWordWrap(True)
        header.setStyleSheet(section_title_css(18))
        layout.addWidget(header)

        body = QLabel(str(message or ""))
        body.setWordWrap(True)
        body.setStyleSheet(muted_label_css(13))
        layout.addWidget(body)

        provider_hint = QLabel(f"ספק פעיל: {provider_label}")
        provider_hint.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; font-weight: 700;")
        layout.addWidget(provider_hint)

        self.api_key_edit = MaskedSecretLineEdit()
        self.api_key_edit.setPlaceholderText("הדבק כאן את מפתח ה-API")
        self.api_key_edit.setClearButtonEnabled(True)
        layout.addWidget(self.api_key_edit)

        if help_url:
            link = QLabel(high_contrast_link_markup(help_url, "פתח דף הנפקת מפתחות API"))
            link.setOpenExternalLinks(True)
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            apply_high_contrast_link_label(link)
            layout.addWidget(link)

        instructions = provider_key_instructions(secret_key=secret_key)
        if instructions:
            help_text = QLabel(instructions)
            help_text.setWordWrap(True)
            help_text.setStyleSheet(muted_label_css(12))
            layout.addWidget(help_text)

        note = QLabel("המפתח יישמר כמו שאר המפתחות של סמארטי, ולא יוצג בלוגים.")
        note.setWordWrap(True)
        note.setStyleSheet(muted_label_css(12))
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        ok_btn.setText("שמירה והמשך")
        ok_btn.setEnabled(False)
        cancel_btn.setText("ביטול")
        self.api_key_edit.secretEdited.connect(lambda text: ok_btn.setEnabled(bool(sanitize_secret_value(text))))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def api_key(self):
        return sanitize_secret_value(self.api_key_edit.secret())

class UsageStatsPage(QWidget):
    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        top_bar = QHBoxLayout()
        top_bar.addWidget(create_back_button(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)))
        title = QLabel("נתוני שימוש (טוקנים)")
        title.setStyleSheet(page_title_css(18))
        top_bar.addWidget(title)
        top_bar.addStretch()
        layout.addLayout(top_bar)
        
        filter_layout = QHBoxLayout()
        self.clear_btn = QPushButton("נקה נתונים")
        self.clear_btn.setStyleSheet(DANGER_BUTTON_CSS)
        self.clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clear_btn.clicked.connect(self.clear_data)
        filter_layout.addWidget(self.clear_btn)
        filter_layout.addStretch()
        
        self.timeframe_values = ['today', 'week', 'month', 'all']
        self.timeframe_segment = SegmentedControl(["היום", "השבוע", "החודש", "כל הזמן"])
        self.timeframe_segment.currentIndexChanged.connect(lambda idx: self.load_data(self.timeframe_values[idx]))
        filter_layout.addWidget(self.timeframe_segment, 1)
        layout.addLayout(filter_layout)
        
        disclaimer = QLabel("לתשומת ליבך: העלות מוערכת דרך ספריית litellm ומתבססת על תעריפי מנויי Paid.")
        disclaimer.setStyleSheet(muted_label_css(11) + " margin-top: 5px; margin-bottom: 5px;")
        layout.addWidget(disclaimer)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        
        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setSpacing(14)
        self.scroll.setWidget(self.content)
        self.current_timeframe = 'today'
        layout.addWidget(self.scroll)

    def clear_data(self):
        if QMessageBox.question(self, "איפוס נתונים", "למחוק הכל?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try: os.remove(USAGE_FILE)
            except: pass
            self.load_data(self.current_timeframe)

    def _is_memory_usage_model(self, model_name):
        name = str(model_name or "").strip().lower()
        return name in {"memory-rag/local", "smarti-memory-rag/local"} or name.startswith("memory-rag/")

    def _format_usage_time(self, value):
        if not value:
            return "טרם נרשם"
        try:
            dt = datetime.fromisoformat(str(value))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(value)

    def load_data(self, timeframe):
        self.current_timeframe = timeframe
        if hasattr(self, "timeframe_segment") and timeframe in self.timeframe_values:
            self.timeframe_segment.setCurrentIndex(self.timeframe_values.index(timeframe), emit=False)
                
        for i in reversed(range(self.content_layout.count())):
            w = self.content_layout.itemAt(i).widget()
            if w: w.deleteLater()
            
        usage_data = {}
        if os.path.exists(USAGE_FILE):
            try:
                with open(USAGE_FILE, 'r', encoding='utf-8') as f: usage_data = json.load(f)
            except: pass
        
        aggregated = {}
        memory_usage = {"prompt": 0, "completion": 0, "total": 0}
        now = datetime.now()
        for date_str, models in usage_data.items():
            try:
                d = datetime.strptime(date_str, '%Y-%m-%d')
                delta = (now - d).days
                if timeframe == 'today' and delta != 0: continue
                if timeframe == 'week' and delta > 7: continue
                if timeframe == 'month' and delta > 30: continue
                for m_name, stats in models.items():
                    if self._is_memory_usage_model(m_name):
                        memory_usage["prompt"] += stats.get("prompt", 0)
                        memory_usage["completion"] += stats.get("completion", 0)
                        memory_usage["total"] += stats.get("total", 0)
                        continue
                    if m_name not in aggregated: aggregated[m_name] = {"prompt": 0, "completion": 0, "total": 0}
                    aggregated[m_name]["prompt"] += stats.get("prompt", 0)
                    aggregated[m_name]["completion"] += stats.get("completion", 0)
                    aggregated[m_name]["total"] += stats.get("total", 0)
            except: pass
            
        if not aggregated:
            lbl = QLabel("אין נתוני שימוש במודלים בטווח הזמן שנבחר.")
            lbl.setStyleSheet(muted_label_css(15) + " margin-top: 20px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(lbl)
        else:
            for m_name, stats in sorted(aggregated.items(), key=lambda x: x[1]['total'], reverse=True):
                card = QFrame()
                card.setStyleSheet(card_css(15, 8))
                card_layout = QVBoxLayout(card)
                
                m_lbl = QLabel(m_name)
                m_lbl.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 700; font-size: 16px; border: none;")
                m_lbl.setWordWrap(True)
                card_layout.addWidget(m_lbl)
                
                cost_str = " | מחיר מוערך: חינמי / לא במאגר"
                if LITELLM_INSTALLED:
                    try:
                        import litellm
                        l_model = m_name
                        if "gemini" in m_name.lower(): l_model = f"gemini/{m_name}"
                        elif "claude" in m_name.lower(): l_model = f"anthropic/{m_name}"
                        cost = litellm.cost_calculator.cost_per_token(model=l_model, prompt_tokens=stats['prompt'], completion_tokens=stats['completion'])
                        if cost and cost > 0: cost_str = f" | עלות מוערכת: ${cost:.6f}" if cost < 0.0001 else f" | עלות מוערכת: ${cost:.4f}"
                    except: pass
                
                total_lbl = QLabel(f"סה\"כ טוקנים: {stats['total']:,}{cost_str}")
                total_lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 700; border: none;")
                total_lbl.setWordWrap(True)
                card_layout.addWidget(total_lbl)
                
                details_lbl = QLabel(f"קלט: {stats['prompt']:,}  |  פלט: {stats['completion']:,}")
                details_lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 13px; border: none;")
                card_layout.addWidget(details_lbl)
                self.content_layout.addWidget(card)

        self._add_memory_usage_card(memory_usage)

    def _add_memory_usage_card(self, usage_stats=None):
        if not os.path.exists(MEMORY_FILE):
            return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
        except Exception:
            return
        entries = memory_data.get("entries", []) if isinstance(memory_data, dict) else []
        stats = memory_data.get("stats", {}) if isinstance(memory_data, dict) else {}
        now = datetime.now()
        active = 0
        active_by_type = {"user": 0, "long_term": 0, "short_term": 0, "tool": 0}
        for entry in entries:
            expires = entry.get("expires_at")
            is_active = False
            if not expires:
                is_active = True
            else:
                try:
                    is_active = datetime.fromisoformat(str(expires)) > now
                except Exception:
                    is_active = True
            if is_active:
                active += 1
                memory_type = entry.get("type", "long_term")
                active_by_type[memory_type] = active_by_type.get(memory_type, 0) + 1
        injected = int(stats.get("injected_tokens_estimate", 0) or 0)
        last_injected_tokens = int(stats.get("last_injected_tokens", 0) or 0)
        last_results = int(stats.get("last_injected_results_count", stats.get("last_results_count", 0)) or 0)
        search_count = int(stats.get("searches", 0) or 0)
        usage_total = int((usage_stats or {}).get("total", 0) or 0)
        last_injected = self._format_usage_time(stats.get("last_injected_at"))
        retriever = stats.get("last_retriever", "local")
        type_labels = {"user": "משתמש", "long_term": "ארוך טווח", "short_term": "קצר טווח", "tool": "כלים"}
        type_text = "  |  ".join(f"{type_labels.get(k, k)}: {v}" for k, v in active_by_type.items() if v)
        if not type_text:
            type_text = "אין זיכרונות פעילים"
        card = QFrame()
        card.setStyleSheet(card_css(15, 8))
        card_layout = QVBoxLayout(card)
        title = QLabel("זיכרון מקומי ו-RAG")
        title.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 700; font-size: 16px; border: none;")
        card_layout.addWidget(title)
        total_lbl = QLabel(f"זיכרונות פעילים: {active:,}  |  טוקנים שנשלפו לטווח הנבחר: {usage_total:,}  |  עלות שליפה מקומית: $0")
        total_lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 700; border: none;")
        total_lbl.setWordWrap(True)
        card_layout.addWidget(total_lbl)
        details_lbl = QLabel(
            f"{type_text}\n"
            f"שליפה אחרונה: {last_injected}  |  תוצאות בהזרקה האחרונה: {last_results}  |  טוקנים בהזרקה האחרונה: {last_injected_tokens:,}\n"
            f"סה\"כ טוקנים שהוזרקו: {injected:,}  |  חיפושים מקומיים: {search_count:,}  |  מנוע: {retriever}"
        )
        details_lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 13px; border: none;")
        details_lbl.setWordWrap(True)
        card_layout.addWidget(details_lbl)
        self.content_layout.addWidget(card)

class TaskCenterPage(QWidget):
    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        top_bar = QHBoxLayout()
        top_bar.addWidget(create_back_button(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)))
        title = QLabel("מרכז משימות")
        title.setStyleSheet(page_title_css(18))
        top_bar.addWidget(title)
        top_bar.addStretch()
        refresh_btn = QPushButton("רענן")
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.setStyleSheet(PRIMARY_BUTTON_CSS)
        apply_soft_shadow(refresh_btn, blur=24, y=7, alpha=30)
        refresh_btn.clicked.connect(self.load_tasks)
        top_bar.addWidget(refresh_btn)
        layout.addLayout(top_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setSpacing(14)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)

    def load_tasks(self):
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item and item.widget(): item.widget().deleteLater()
        tasks = [
            task for task in self.core.settings.get("background_tasks", [])
            if task.get("status") in {"scheduled", "running", "cancelling"}
        ]
        if not tasks:
            empty = QLabel("אין משימות רקע פעילות.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(muted_label_css(15) + " margin-top: 20px;")
            self.content_layout.addWidget(empty)
            return
        for task in reversed(tasks[-40:]):
            card = QFrame()
            card.setStyleSheet(card_css(12, 8))
            card_layout = QVBoxLayout(card)
            title = QLabel(f"{task.get('id')} | {task.get('status')} | {task.get('run_at', '')}")
            title.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 700; font-size: 14px; border: none;")
            title.setWordWrap(True)
            card_layout.addWidget(title)
            body = QLabel(str(task.get("prompt", "")))
            body.setWordWrap(True)
            body.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; border: none;")
            card_layout.addWidget(body)
            if task.get("last_result"):
                result = QLabel(str(task.get("last_result", ""))[:500])
                result.setWordWrap(True)
                result.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px; border: none;")
                card_layout.addWidget(result)
            actions = QHBoxLayout()
            cancel_btn = QPushButton("בטל")
            retry_btn = QPushButton("הרץ שוב")
            for btn in (cancel_btn, retry_btn):
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet(SECONDARY_BUTTON_CSS)
            task_id = task.get("id", "")
            status = str(task.get("status", ""))
            cancel_btn.setEnabled(status in {"scheduled", "running"})
            retry_btn.setEnabled(status not in {"running", "cancelling"})
            cancel_btn.clicked.connect(lambda checked=False, tid=task_id: self._cancel_task(tid))
            retry_btn.clicked.connect(lambda checked=False, tid=task_id: self._retry_task(tid))
            actions.addWidget(cancel_btn)
            actions.addWidget(retry_btn)
            actions.addStretch()
            card_layout.addLayout(actions)
            self.content_layout.addWidget(card)

    def _cancel_task(self, task_id):
        result = self.core.cancel_background_task(task_id)
        if str(result).startswith("ERROR"):
            QMessageBox.warning(self, "ביטול משימה", result)
        self.load_tasks()

    def _retry_task(self, task_id):
        result = self.core.retry_background_task(task_id, 0)
        if str(result).startswith("ERROR"):
            QMessageBox.warning(self, "הרצת משימה מחדש", result)
        self.load_tasks()

class DeveloperTracePage(QWidget):
    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        top_bar = QHBoxLayout()
        top_bar.addWidget(create_back_button(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)))
        title = QLabel("Developer Trace")
        title.setStyleSheet(page_title_css(18))
        top_bar.addWidget(title)
        top_bar.addStretch()
        refresh = QPushButton("רענן")
        refresh.setStyleSheet(SECONDARY_BUTTON_CSS)
        refresh.clicked.connect(self.load_trace)
        top_bar.addWidget(refresh)
        layout.addLayout(top_bar)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(TEXT_EDIT_CSS + SCROLLBAR_CSS)
        layout.addWidget(self.text)

    def load_trace(self):
        lines = ["Runtime trace:"]
        for item in self.core.settings.get("_runtime_trace", [])[-60:]:
            lines.append(f"{item.get('time')} | {item.get('stage')} | {item.get('detail')}")
        lines.append("\nAudit tail:")
        try:
            if os.path.exists(AUDIT_LOG_FILE):
                with open(AUDIT_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    audit_lines = f.readlines()[-60:]
                lines.extend([ln.rstrip("\n") for ln in audit_lines])
            else:
                lines.append("אין עדיין יומן אודיט.")
        except Exception as e:
            lines.append(f"ERROR: {e}")
        self.text.setPlainText("\n".join(lines))

class ToolsSettingsPage(QWidget):
    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        top_bar = QHBoxLayout()
        top_bar.addWidget(create_back_button(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)))
        title = QLabel("ניהול כלים")
        title.setStyleSheet(page_title_css(18))
        top_bar.addWidget(title)
        top_bar.addStretch()
        layout.addLayout(top_bar)
        hint = QLabel("השינויים במסך זה נשמרים מיד.")
        hint.setWordWrap(True)
        hint.setStyleSheet(muted_label_css(12))
        layout.addWidget(hint)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self.form = QFormLayout(content)
        self.form.setContentsMargins(4, 4, 4, 4)
        self.form.setVerticalSpacing(8)
        self.form.setHorizontalSpacing(10)
        
        self.checkboxes = {}
        self.checkbox_kinds = {}
        config = self.core.settings.get("tools_config", {})
        
        lbl1 = QLabel("כלים מובנים (Built-in):")
        lbl1.setStyleSheet(section_title_css(16) + " margin-top: 10px;")
        self.form.addRow(lbl1)
        
        public_tools = [tool for tool in PUBLIC_BUILTIN_TOOLS if tool in BUILTIN_TOOL_SCHEMAS]
        grouped_tools = {}
        for tool in public_tools:
            grouped_tools.setdefault(TOOL_CATEGORIES.get(tool, "developer"), []).append(tool)
        for category, label in TOOL_CATEGORY_LABELS.items():
            tools = grouped_tools.get(category, [])
            if not tools:
                continue
            cat_lbl = QLabel(TOOL_CATEGORY_DISPLAY_LABELS.get(category, label))
            cat_lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-weight: 700; font-size: 13px; margin-top: 8px;")
            self.form.addRow(cat_lbl)
            for tool in tools:
                cb = SmartiCheckBox(self._tool_label(tool))
                cb.setChecked(config.get(tool, True))
                cb.setStyleSheet(CHECKBOX_CSS)
                self.checkboxes[tool] = cb
                self.checkbox_kinds[tool] = ("builtin", tool)
                cb.stateChanged.connect(lambda _=None, key=tool: self._apply_tool_checkbox(key))
                self.form.addRow(cb)

        for tool in sorted(t for t in LEGACY_BUILTIN_TOOLS if t in config and t not in public_tools and config.get(t, True) is False):
            cb = SmartiCheckBox(self._tool_label(tool))
            cb.setChecked(config.get(tool, True))
            cb.setStyleSheet(CHECKBOX_CSS)
            self.checkboxes[tool] = cb
            self.checkbox_kinds[tool] = ("builtin", tool)
            cb.stateChanged.connect(lambda _=None, key=tool: self._apply_tool_checkbox(key))
            self.form.addRow(cb)
            
        lbl2 = QLabel("כלים חיצוניים (custom_tools):")
        lbl2.setStyleSheet(section_title_css(16) + " margin-top: 20px;")
        self.form.addRow(lbl2)
        
        has_custom = False
        if os.path.exists(TOOLS_DIR):
            for f in os.listdir(TOOLS_DIR):
                if f.endswith('.pyw'):
                    has_custom = True
                    t_name = f.replace('.pyw', '')
                    cb = SmartiCheckBox(t_name)
                    cb.setChecked(config.get(t_name, True))
                    cb.setStyleSheet(CHECKBOX_CSS)
                    self.checkboxes[t_name] = cb
                    self.checkbox_kinds[t_name] = ("custom", t_name)
                    cb.stateChanged.connect(lambda _=None, key=t_name: self._apply_tool_checkbox(key))
                    self.form.addRow(self._external_artifact_row(cb, "custom", t_name))
                    
        if not has_custom:
            lbl_no_tools = QLabel("אין כלים חיצוניים מותקנים.")
            lbl_no_tools.setStyleSheet(muted_label_css(13))
            self.form.addRow(lbl_no_tools)

        # --- הוספת אזור למיומנויות MCP ---
        lbl3 = QLabel("מיומנויות MCP מותקנות:")
        lbl3.setStyleSheet(section_title_css(16) + " margin-top: 20px;")
        self.form.addRow(lbl3)
        
        has_mcp = False
        if os.path.exists(MCP_TOOLS_DIR):
            for f in os.listdir(MCP_TOOLS_DIR):
                if f.endswith('.txt'):
                    has_mcp = True
                    t_name = f.replace('.txt', '')
                    cb = SmartiCheckBox(t_name)
                    cb.setChecked(config.get(f"mcp_{t_name}", True))
                    cb.setStyleSheet(CHECKBOX_CSS)
                    self.checkboxes[f"mcp_{t_name}"] = cb
                    self.checkbox_kinds[f"mcp_{t_name}"] = ("mcp", t_name)
                    cb.stateChanged.connect(lambda _=None, key=f"mcp_{t_name}": self._apply_tool_checkbox(key))
                    self.form.addRow(self._external_artifact_row(cb, "mcp", t_name))
                    
        if not has_mcp:
            lbl_no_mcp = QLabel("אין חבילות MCP מותקנות.")
            lbl_no_mcp.setStyleSheet(muted_label_css(13))
            self.form.addRow(lbl_no_mcp)

        lbl4 = QLabel("מיומנויות (Skills) מותקנות:")
        lbl4.setStyleSheet(section_title_css(16) + " margin-top: 20px;")
        self.form.addRow(lbl4)
        has_skills = False
        registry = getattr(self.core, "skill_registry", {}) or self.core._load_skill_registry()
        for name, spec in sorted(registry.items()):
            has_skills = True
            key = f"skill_{name}"
            cb = SmartiCheckBox(f"{name} ({spec.get('source', 'local')})")
            cb.setChecked(self.core._skill_enabled(name))
            cb.setStyleSheet(CHECKBOX_CSS)
            self.checkboxes[key] = cb
            self.checkbox_kinds[key] = ("skill", name)
            cb.stateChanged.connect(lambda _=None, key=key: self._apply_tool_checkbox(key))
            if spec.get("source") == "builtin":
                self.form.addRow(cb)
            else:
                self.form.addRow(self._external_artifact_row(cb, "skill", name))
        if not has_skills:
            lbl_no_skills = QLabel("אין מיומנויות (Skills) מותקנות.")
            lbl_no_skills.setStyleSheet(muted_label_css(13))
            self.form.addRow(lbl_no_skills)

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _tool_label(self, tool_name):
        return BUILTIN_TOOL_DISPLAY_LABELS.get(tool_name, str(tool_name).replace("_", " "))

    def _external_artifact_row(self, checkbox, kind, name):
        label_text = checkbox.text()
        checkbox.setText("")
        checkbox.setToolTip(label_text)
        checkbox.setAccessibleName(f"הפעל {name}")
        checkbox.setFixedWidth(60)
        checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        row = QWidget()
        row.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        delete_btn = QPushButton()
        delete_btn.setFixedSize(30, 30)
        delete_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        delete_btn.setToolTip("מחק לחלוטין")
        delete_btn.setAccessibleName(f"מחק {name}")
        delete_btn.setStyleSheet(icon_button_css(30, danger=True))
        set_themed_button_icon(delete_btn, ("delete_icon",), "X", 17, clear_text=True)
        delete_btn.clicked.connect(lambda _=False, k=kind, n=name: self.confirm_delete_external_artifact(k, n))
        row_layout.addWidget(delete_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        label = QLabel(label_text)
        label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setWordWrap(True)
        label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; background: transparent;")
        label.mousePressEvent = lambda event, cb=checkbox: (cb.toggle(), event.accept())
        row_layout.addWidget(label, 1)
        return row

    def _artifact_kind_label(self, kind):
        return {
            "custom": "כלי Python מותאם",
            "mcp": "חבילת MCP",
            "skill": "Skill",
        }.get(kind, "פריט חיצוני")

    def _delete_confirmation_details(self, kind, name):
        kind_label = self._artifact_kind_label(kind)
        details = [
            f"סוג: {kind_label}",
            f"שם: {name}",
            "",
            "המחיקה תסיר את הפריט מהדיסק ותנקה את רישומי ההרשאות/אמון שלו מהגדרות סמארטי.",
        ]
        if kind == "custom":
            details.append(f"תיקייה: {TOOLS_DIR}")
        elif kind == "mcp":
            details.append(f"תיקייה: {MCP_TOOLS_DIR}")
            details.append("בנוסף ינוקו aliases, allowed packages וקובץ תצורת MCP.")
        elif kind == "skill":
            spec = (getattr(self.core, "skill_registry", {}) or {}).get(name, {})
            details.append(f"תיקייה: {spec.get('path') or os.path.join(SKILLS_DIR, name)}")
        details.append("")
        details.append("לא ניתן לשחזר את הפריט מתוך סמארטי אחרי המחיקה.")
        return "\n".join(details)

    def confirm_delete_external_artifact(self, kind, name):
        kind_label = self._artifact_kind_label(kind)
        dlg = ToolDeleteConfirmDialog(
            f"מחיקת {kind_label}",
            self._delete_confirmation_details(kind, name),
            artifact_name=name,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        result = self.core.delete_external_tool_artifact(kind, name)
        if str(result).startswith("SUCCESS:"):
            logging.info(f"SETTINGS | external_artifact_deleted | kind={kind} | name={name}")
            QTimer.singleShot(0, self.main_window.show_tools_page)
        else:
            QMessageBox.warning(self, "שגיאה במחיקה", str(result))

    def _apply_tool_checkbox(self, name):
        cb = self.checkboxes.get(name)
        if cb is None:
            return
        trusted = cb.isChecked()
        self.core.settings.setdefault("tools_config", {})[name] = trusted
        kind, real_name = self.checkbox_kinds.get(name, ("builtin", name))
        if kind in {"custom", "mcp", "skill"} and getattr(self.core, "tool_registry", None):
            self.core.set_tool_trust(kind, real_name, trusted, metadata={"trusted_from_ui": True})
        else:
            self.core._save_settings()
        logging.info(f"SETTINGS | tool_permission_changed | kind={kind} | name={real_name} | enabled={trusted}")
        if getattr(self.core, "audit_logger", None):
            self.core.audit_logger.record("tool_permission_changed", {"kind": kind, "name": real_name, "enabled": trusted}, self.core.settings)

    def save_and_close(self):
        for name, cb in self.checkboxes.items():
            self.core.settings.setdefault("tools_config", {})[name] = cb.isChecked()
            kind, real_name = self.checkbox_kinds.get(name, ("builtin", name))
            if kind in {"custom", "mcp", "skill"} and getattr(self.core, "tool_registry", None):
                self.core.tool_registry.set_trust(kind, real_name, cb.isChecked(), metadata={"trusted_from_ui": True})
                if kind == "skill":
                    self.core.settings.setdefault("skills_config", {})[real_name] = cb.isChecked()
        self.core._sync_trusted_mcp_packages()
        self.core._ensure_mcp_config()
        self.core._save_settings()
        self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)

class SettingsPage(QWidget):
    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self._suppress_autosave = True
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.setInterval(350)
        self.autosave_timer.timeout.connect(self._save_from_ui)
        self.api_key_validation_timer = QTimer(self)
        self.api_key_validation_timer.setSingleShot(True)
        self.api_key_validation_timer.setInterval(900)
        self.api_key_validation_timer.timeout.connect(self._validate_current_api_key_before_save)
        self.api_key_validation_worker = None
        self._api_key_validation_generation = 0
        self._validated_api_keys = set()
        
        top_bar = QHBoxLayout()
        self.back_btn = create_back_button(self.handle_back)
        top_bar.addWidget(self.back_btn)
        title = QLabel("הגדרות")
        title.setStyleSheet(page_title_css(20))
        top_bar.addWidget(title)
        top_bar.addStretch()
        layout.addLayout(top_bar)
        
        self._init_widgets()
        self.settings_stack = AnimatedStackedWidget()
        self.settings_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._build_ui_sections()
        self.settings_stack.currentChanged.connect(self._on_settings_section_changed)
        layout.addWidget(self.settings_stack)
        
        self.fetch_worker = None
        self.models_loaded = False
        self.populate_models([self.core.settings.get(f"selected_{self.provider_combo.currentText()}_model", "")], self.provider_combo.currentText())
        self._register_autosave_handlers()
        self._suppress_autosave = False

    def handle_back(self):
        if hasattr(self, "settings_stack") and self.settings_stack.currentWidget() is not self.settings_home_page:
            self.settings_stack.setCurrentWidget(self.settings_home_page)
            self._reset_scrolls_in_widget(self.settings_home_page)
        else:
            self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)

    def show_home(self):
        if hasattr(self, "settings_stack") and hasattr(self, "settings_home_page"):
            self.settings_stack.setCurrentWidget(self.settings_home_page)
            self._reset_scrolls_in_widget(self.settings_home_page)

    def _set_settings_section(self, target_page):
        if not hasattr(self, "settings_stack") or target_page is None:
            return
        self.settings_stack.setCurrentWidget(target_page)
        self._reset_scrolls_in_widget(target_page)
        if target_page is getattr(self, "developer_page", None):
            QTimer.singleShot(0, self.load_developer_logs)

    def _reset_scrolls_in_widget(self, widget):
        if widget is None:
            return

        def reset():
            for area in widget.findChildren(QScrollArea):
                area.verticalScrollBar().setValue(area.verticalScrollBar().minimum())
                area.horizontalScrollBar().setValue(area.horizontalScrollBar().minimum())

        QTimer.singleShot(0, reset)

    def _on_settings_section_changed(self, index):
        if not hasattr(self, "settings_stack"):
            return
        self._reset_scrolls_in_widget(self.settings_stack.widget(index))
        if self.settings_stack.widget(index) is getattr(self, "developer_page", None):
            QTimer.singleShot(0, self.load_developer_logs)

    def _make_secret_link_row(self, edit, link_label):
        row = QWidget(self)
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        edit.setStyleSheet(LINE_EDIT_CSS)
        edit.setMinimumWidth(0)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        link_label.setTextFormat(Qt.TextFormat.RichText)
        link_label.setOpenExternalLinks(True)
        link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        apply_high_contrast_link_label(link_label)
        clear_btn = QPushButton()
        clear_btn.setProperty("smartiSecretClearButton", True)
        clear_btn.setFixedSize(34, 34)
        clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_btn.setToolTip("מחק מפתח שמור")
        clear_btn.setStyleSheet(icon_button_css(34, danger=True))
        set_themed_button_icon(clear_btn, ("delete_icon",), "X", 17, clear_text=True)
        clear_btn.clicked.connect(edit.clear_secret if hasattr(edit, "clear_secret") else edit.clear)
        layout.addWidget(edit, 1)
        layout.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(link_label, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _set_external_link(self, label, url, text):
        apply_high_contrast_link_label(label)
        label.setText(high_contrast_link_markup(url, text) if url else "")
        label.setVisible(bool(url))

    def _update_provider_key_help(self):
        if not hasattr(self, "api_key_help_link"):
            return
        provider = normalize_provider_name(self.provider_combo.currentText()) if hasattr(self, "provider_combo") else ""
        url = provider_help_url(provider)
        self._set_external_link(self.api_key_help_link, url, "קבל מפתח")
        instructions = provider_key_instructions(provider)
        self.api_key_help_hint.setText(instructions)
        self.api_key_help_hint.setVisible(bool(instructions and provider != "local"))

    def _update_status_text(self):
        last = str(self.core.settings.get("updates_last_checked_at", "") or "").strip()
        available = str(self.core.settings.get("updates_last_available_version", "") or "").strip()
        if available:
            return f"נמצא עדכון זמין: {available}"
        if last:
            return f"בדיקה אחרונה: {last}"
        return "עדיין לא בוצעה בדיקת עדכונים."

    def begin_update_check(self):
        if hasattr(self, "check_updates_btn"):
            self.check_updates_btn.setEnabled(False)
        if hasattr(self, "update_status_lbl"):
            self.update_status_lbl.setText("בודק עדכונים...")

    def finish_update_check(self, message):
        if hasattr(self, "check_updates_btn"):
            self.check_updates_btn.setEnabled(True)
        if hasattr(self, "update_status_lbl"):
            self.update_status_lbl.setText(str(message or self._update_status_text()))

    def check_updates_now(self):
        if hasattr(self.main_window, "check_for_updates_manual"):
            self.main_window.check_for_updates_manual(self)

    def _init_widgets(self):
        self.core.ensure_provider_secret(self.core.settings.get("api_mode", "gemini"))
        for secret_key in ("tavily_api_key", "email_address", "email_password"):
            self.core._ensure_secret_loaded(secret_key)

        self.provider_combo = NoScrollComboBox()
        self.provider_combo.addItems(MODEL_PROVIDER_ORDER)
        self.provider_combo.setCurrentText(self.core.settings.get("api_mode", "gemini"))
        self.provider_combo.setStyleSheet(COMBOBOX_CSS)
        self.provider_combo.currentTextChanged.connect(self.on_provider_change)
        
        self.model_combo = SearchableModelComboBox()
        self.model_combo.setStyleSheet(COMBOBOX_CSS)
        
        self.api_key_edit = MaskedSecretLineEdit()
        self.api_key_edit.setPlaceholderText("מפתח גישה לספק המודל")
        self.api_key_help_link = QLabel(self)
        self.api_key_row = self._make_secret_link_row(self.api_key_edit, self.api_key_help_link)
        self.api_key_status = QLabel("", self)
        self.api_key_status.setWordWrap(True)
        self.api_key_status.setStyleSheet(muted_label_css(12))
        self.api_key_help_hint = QLabel("", self)
        self.api_key_help_hint.setWordWrap(True)
        self.api_key_help_hint.setStyleSheet(muted_label_css(12))
        self.tavily_key = MaskedSecretLineEdit(self.core.settings.get("tavily_api_key", ""))
        self.tavily_key_help_link = QLabel(self)
        self.tavily_key_row = self._make_secret_link_row(self.tavily_key, self.tavily_key_help_link)
        self.tavily_key_help_hint = QLabel(provider_key_instructions(secret_key="tavily_api_key"), self)
        self.tavily_key_help_hint.setWordWrap(True)
        self.tavily_key_help_hint.setStyleSheet(muted_label_css(12))
        self._set_external_link(self.tavily_key_help_link, provider_help_url(secret_key="tavily_api_key"), "קבל מפתח")
        self._update_provider_key_help()
        self.local_url = QLineEdit(self.core.settings.get("local_server_url", "http://localhost:1234/v1"))

        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        
        self.permission_combo = SegmentedControl()
        self.permission_combo.addItems(["בטוח", "מאוזן", "אוטונומי"])
        self.permission_combo.setCurrentIndex(max(0, min(2, self.core.settings.get("permission_level", 1) - 1)))

        self.autonomy_combo = SegmentedControl()
        self.autonomy_options = [
            ("max_autonomy", "אוטונומיה מקסימלית"),
            ("balanced", "מאוזן"),
            ("locked_down", "בטיחות קשיחה")
        ]
        self.autonomy_combo.addItems([label for _, label in self.autonomy_options])
        current_autonomy = self.core.settings.get("autonomy_mode", "max_autonomy")
        self.autonomy_combo.setCurrentIndex(max(0, [key for key, _ in self.autonomy_options].index(current_autonomy) if current_autonomy in [key for key, _ in self.autonomy_options] else 0))

        self.theme_combo = SegmentedControl()
        self.theme_options = [
            ("system", "מערכת"),
            ("dark", "כהה"),
            ("light", "בהיר")
        ]
        self.theme_combo.addItems([label for _, label in self.theme_options])
        current_theme = self.core.settings.get("ui_preferences", {}).get("theme_mode", DEFAULT_THEME_MODE)
        theme_keys = [key for key, _ in self.theme_options]
        self.theme_combo.setCurrentIndex(theme_keys.index(current_theme) if current_theme in theme_keys else 0)

        self.update_auto_cb = SmartiCheckBox("בדוק עדכונים אוטומטית")
        self.update_auto_cb.setChecked(bool(self.core.settings.get("updates_auto_check", True)))
        self.update_auto_cb.setStyleSheet(CHECKBOX_CSS)
        self.check_updates_btn = QPushButton("בדוק עדכונים עכשיו")
        self.check_updates_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.check_updates_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        set_themed_button_icon(self.check_updates_btn, ("check_updates_icon",), self.check_updates_btn.text(), 18, clear_text=False)
        self.check_updates_btn.clicked.connect(self.check_updates_now)
        self.update_status_lbl = QLabel(self._update_status_text())
        self.update_status_lbl.setWordWrap(True)
        self.update_status_lbl.setStyleSheet(muted_label_css(12))

        self.policy_combos = {}
        policy = self.core._normalize_policy_matrix()
        for cap, label in CAPABILITY_LABELS.items():
            combo = SegmentedControl()
            combo.addItems(["שאל בכל פעם", "אפשר", "חסום"])
            value = policy.get(cap, DEFAULT_POLICY_MATRIX.get(cap, "ask"))
            combo.setCurrentIndex({"ask": 0, "allow": 1, "deny": 2}.get(value, 0))
            self.policy_combos[cap] = combo

        self.default_output_dir_picker = DirectoryPicker(
            [self.core.settings.get("default_output_dir", OUTPUTS_DIR)],
            allow_multiple=False,
            dialog_title="בחר תיקיית ברירת מחדל",
            default_path=OUTPUTS_DIR
        )
        self.mcp_allowed_dirs = DirectoryPicker(
            self.core.settings.get("mcp_allowed_directories", [APP_DIR]),
            allow_multiple=True,
            dialog_title="בחר תיקייה לכלים חיצוניים",
            default_path=APP_DIR
        )
        self.sandbox_root_picker = DirectoryPicker(
            [self.core.settings.get("sandbox_root_dir", OUTPUTS_DIR)],
            allow_multiple=False,
            dialog_title="בחר תיקיית ארגז חול",
            default_path=OUTPUTS_DIR
        )
        self.sandbox_cb = SmartiCheckBox("הפעל ארגז חול")
        self.sandbox_cb.setChecked(self.core.settings.get("sandbox_enabled", False))
        self.sandbox_cb.setStyleSheet(CHECKBOX_CSS)
        self.sandbox_read_outside_cb = SmartiCheckBox("אפשר קריאה מחוץ לארגז החול")
        self.sandbox_read_outside_cb.setChecked(self.core.settings.get("sandbox_allow_read_outside", False))
        self.sandbox_read_outside_cb.setStyleSheet(CHECKBOX_CSS)
        self.redact_logs_cb = SmartiCheckBox("הסתר מפתחות וסיסמאות בקובצי הלוג")
        self.redact_logs_cb.setChecked(self.core.settings.get("privacy_redact_logs", True))
        self.redact_logs_cb.setStyleSheet(CHECKBOX_CSS)
        self.audit_log_cb = SmartiCheckBox("שמור יומן אודיט לפעולות כלים")
        self.audit_log_cb.setChecked(self.core.settings.get("audit_log_enabled", True))
        self.audit_log_cb.setStyleSheet(CHECKBOX_CSS)
        self.developer_trace_cb = SmartiCheckBox("הצג Trace למפתחים")
        self.developer_trace_cb.setChecked(self.core.settings.get("enable_developer_trace", True))
        self.developer_trace_cb.setStyleSheet(CHECKBOX_CSS)
        self.raw_shell_approval_cb = SmartiCheckBox("דרוש אישור לפקודות Shell בסיכון גבוה")
        self.raw_shell_approval_cb.setChecked(self.core.settings.get("raw_shell_requires_approval", True))
        self.raw_shell_approval_cb.setStyleSheet(CHECKBOX_CSS)
        self.marketplace_approval_cb = SmartiCheckBox("דרוש אישור להתקנת MCP ו-Skills")
        self.marketplace_approval_cb.setChecked(self.core.settings.get("marketplace_install_requires_approval", True))
        self.marketplace_approval_cb.setStyleSheet(CHECKBOX_CSS)

        self.browser_auto_cb = SmartiCheckBox("אפשר שליטה בדפדפן לצורך אוטומציה")
        self.browser_auto_cb.setChecked(self.core.settings.get("enable_browser_automation", False))
        self.browser_auto_cb.setStyleSheet(CHECKBOX_CSS)
        self.computer_control_cb = SmartiCheckBox("אפשר אוטומציית מחשב דרך עץ הנגישות של Windows")
        self.computer_control_cb.setChecked(self.core.settings.get("enable_computer_control", False))
        self.computer_control_cb.setStyleSheet(CHECKBOX_CSS)
        self.mcp_cb = SmartiCheckBox("אפשר שימוש בכלים חיצוניים (MCP)")
        self.mcp_cb.setChecked(self.core.settings.get("enable_mcp_clawhub", False))
        self.mcp_cb.setStyleSheet(CHECKBOX_CSS)
        self.skills_beta_cb = SmartiCheckBox("אפשר Skills בטא")
        self.skills_beta_cb.setChecked(self.core.settings.get("enable_skills_beta", True))
        self.skills_beta_cb.setStyleSheet(CHECKBOX_CSS)

        self.email = QLineEdit(self.core.settings.get("email_address", ""))
        self.pwd = QLineEdit(self.core.settings.get("email_password", ""))
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.email_from_name = QLineEdit(self.core.settings.get("email_from_name", ""))
        self.email_imap_host = QLineEdit(self.core.settings.get("email_imap_host", ""))
        self.email_imap_port = QLineEdit(str(self.core.settings.get("email_imap_port", 993)))
        self.email_smtp_host = QLineEdit(self.core.settings.get("email_smtp_host", ""))
        self.email_smtp_port = QLineEdit(str(self.core.settings.get("email_smtp_port", 587)))
        self.email_max_attachment_mb = QLineEdit(str(self.core.settings.get("email_max_attachment_mb", 20)))
        self.email_imap_ssl_cb = SmartiCheckBox("Email IMAP SSL")
        self.email_imap_ssl_cb.setChecked(bool(self.core.settings.get("email_imap_ssl", True)))
        self.email_imap_ssl_cb.setStyleSheet(CHECKBOX_CSS)
        self.email_smtp_ssl_cb = SmartiCheckBox("Email SMTP SSL")
        self.email_smtp_ssl_cb.setChecked(bool(self.core.settings.get("email_smtp_ssl", False)))
        self.email_smtp_ssl_cb.setStyleSheet(CHECKBOX_CSS)
        self.email_smtp_starttls_cb = SmartiCheckBox("Email SMTP STARTTLS")
        self.email_smtp_starttls_cb.setChecked(bool(self.core.settings.get("email_smtp_starttls", True)))
        self.email_smtp_starttls_cb.setStyleSheet(CHECKBOX_CSS)

        self.tts_cb = SmartiCheckBox("הקראה קולית לכל התשובות")
        self.tts_cb.setChecked(self.core.settings.get("read_aloud_all", False))
        self.tts_cb.setStyleSheet(CHECKBOX_CSS)
        self.tts_voice_cb = SmartiCheckBox("הקראה קולית רק לאחר זיהוי קולי")
        self.tts_voice_cb.setChecked(self.core.settings.get("read_aloud_voice_only", True))
        self.tts_voice_cb.setStyleSheet(CHECKBOX_CSS)
        self.tts_cb.stateChanged.connect(lambda state: self.tts_voice_cb.setChecked(True) if state == 2 else None)

        self.tts_voice_combo = NoScrollComboBox()
        self.tts_voice_combo.setStyleSheet(COMBOBOX_CSS)
        self._populate_tts_voice_combo()
        self.tts_volume_control, self.tts_volume_slider, self.tts_volume_lbl = self._make_labeled_slider(
            0, 100, self.core.settings.get("tts_volume", 100), lambda value: f"{value}%"
        )

        self.voice_sensitivity_control, self.voice_sensitivity_slider, self.voice_sensitivity_lbl = self._make_labeled_slider(
            1, 100, self.core.settings.get("voice_sensitivity", 70), lambda value: f"{value}%"
        )
        pause_value = int(round(float(self.core.settings.get("voice_pause_threshold", 0.8)) * 10))
        self.voice_pause_control, self.voice_pause_slider, self.voice_pause_lbl = self._make_labeled_slider(
            3, 50, pause_value, lambda value: f"{value / 10:.1f} שניות"
        )
        self.voice_timeout_control, self.voice_timeout_slider, self.voice_timeout_lbl = self._make_labeled_slider(
            1, 30, self.core.settings.get("voice_listen_timeout", 6), lambda value: f"{value} שניות"
        )
        ambient_value = int(round(float(self.core.settings.get("voice_ambient_noise_duration", 0.0)) * 10))
        self.voice_ambient_control, self.voice_ambient_slider, self.voice_ambient_lbl = self._make_labeled_slider(
            0, 30, ambient_value, lambda value: "כבוי" if value <= 0 else f"{value / 10:.1f} שניות"
        )
        self.voice_dynamic_energy_cb = SmartiCheckBox("התאמת רגישות אוטומטית לרעש רקע")
        self.voice_dynamic_energy_cb.setChecked(bool(self.core.settings.get("voice_dynamic_energy_threshold", False)))
        self.voice_dynamic_energy_cb.setStyleSheet(CHECKBOX_CSS)
        self.voice_beep_cb = SmartiCheckBox("צפצוף בתחילת וסיום האזנה")
        self.voice_beep_cb.setChecked(bool(self.core.settings.get("voice_beep_enabled", True)))
        self.voice_beep_cb.setStyleSheet(CHECKBOX_CSS)

        self.insecure_ssl_cb = SmartiCheckBox("אפשר תאימות SSL לכלים חיצוניים (פחות בטוח)")
        self.insecure_ssl_cb.setChecked(self.core.settings.get("allow_insecure_ssl_compat", True))
        self.insecure_ssl_cb.setStyleSheet(CHECKBOX_CSS)
        self.cloud_upload_cb = SmartiCheckBox("אישור לפני שליחת נתונים למודל חיצוני")
        self.cloud_upload_cb.setChecked(self.core.settings.get("require_approval_for_cloud_upload", True))
        self.cloud_upload_cb.setStyleSheet(CHECKBOX_CSS)
        self.write_outside_dirs_approval_cb = SmartiCheckBox("אישור לפני כתיבה מחוץ לתיקיית הפלט")
        self.write_outside_dirs_approval_cb.setChecked(self.core.settings.get("write_outside_allowed_dirs_requires_approval", True))
        self.write_outside_dirs_approval_cb.setStyleSheet(CHECKBOX_CSS)
        self.mcp_pin_cb = SmartiCheckBox("דרוש גרסה קבועה לכלים חיצוניים")
        self.mcp_pin_cb.setChecked(self.core.settings.get("mcp_require_pinned_versions", True))
        self.mcp_pin_cb.setStyleSheet(CHECKBOX_CSS)

        self.cmd_timeout = QLineEdit(str(self.core.settings.get("command_timeout_seconds", 60)))
        self.tool_timeout = QLineEdit(str(self.core.settings.get("tool_timeout_seconds", 120)))
        self.mcp_timeout = QLineEdit(str(self.core.settings.get("mcp_timeout_seconds", 60)))
        self.max_chars_edit = QLineEdit(str(self.core.settings.get("max_tool_output_chars", 100000)))
        self.total_timeout = QLineEdit(str(self.core.settings.get("max_total_task_seconds", 900)))
        budgets = self.core.settings.get("budgets", {})
        self.daily_token_budget = QLineEdit(str(budgets.get("daily_token_budget", 0)))
        self.daily_cost_budget = QLineEdit(str(budgets.get("daily_cost_budget_usd", 0)))
        
        self.loops_slider = RtlFillSlider(Qt.Orientation.Horizontal)
        self.loops_slider.setRange(4, 31)
        saved_loops = self.core.settings.get("max_agent_loops", 15)
        try:
            saved_loops = int(saved_loops)
        except Exception:
            saved_loops = 15
        self.loops_slider.setValue(31 if saved_loops <= 0 or saved_loops > 30 else saved_loops)
        self.loops_slider.setStyleSheet(SLIDER_CSS)
        self.loops_val_lbl = QLabel(self._loop_label_text(self.loops_slider.value()))
        self.loops_val_lbl.setStyleSheet(f"""
            background-color: {GLASS_COLOR};
            color: {TEXT_COLOR}; font-weight: 700; font-size: 13px;
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 999px; padding: 7px 12px;
        """)
        self.loops_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loops_val_lbl.setProperty("smartiValuePill", True)
        self.loops_val_lbl.setMinimumSize(96, 30)
        self.loops_slider.valueChanged.connect(lambda val: self.loops_val_lbl.setText(self._loop_label_text(val)))

    def _value_pill_css(self):
        return f"""
            background-color: {GLASS_COLOR};
            color: {TEXT_COLOR}; font-weight: 700; font-size: 13px;
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 999px; padding: 7px 12px;
        """

    def _make_labeled_slider(self, minimum, maximum, value, formatter):
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        slider = RtlFillSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(minimum), int(maximum))
        try:
            value = int(round(float(value)))
        except Exception:
            value = int(minimum)
        slider.setValue(max(int(minimum), min(int(maximum), value)))
        slider.setStyleSheet(SLIDER_CSS)
        label = QLabel(formatter(slider.value()))
        label.setProperty("smartiValuePill", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(104, 30)
        label.setStyleSheet(self._value_pill_css())
        slider.valueChanged.connect(lambda val: label.setText(formatter(val)))
        layout.addWidget(slider, 1)
        layout.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        return container, slider, label

    def _populate_tts_voice_combo(self):
        self.tts_voice_combo.clear()
        voices = list_tts_voices()
        for voice in voices:
            label = voice.get("name") or voice.get("id") or "Voice"
            self.tts_voice_combo.addItem(label, voice.get("id", ""))
        if not voices:
            self.tts_voice_combo.addItem("Google TTS לא זמין", "co.il")
        selected_voice = str(self.core.settings.get("tts_voice_id", "co.il") or "co.il")
        index = self.tts_voice_combo.findData(selected_voice)
        self.tts_voice_combo.setCurrentIndex(index if index >= 0 else 0)

    def _loop_label_text(self, val):
        return "ללא הגבלה" if val > 30 else f"{val} סבבים"

    def _add_section_header(self, title_text, target_layout=None):
        layout = target_layout
        if layout is None: return
        layout.addSpacing(10)
        lbl = QLabel(title_text)
        lbl.setStyleSheet(section_title_css(16))
        layout.addWidget(lbl)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {LINE_COLOR}; max-height: 1px; margin-bottom: 8px;")
        layout.addWidget(line)

    def _add_hint(self, text, target_layout=None):
        layout = target_layout
        if layout is None: return
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        lbl.setMinimumWidth(1)
        lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px; line-height: 1.35; padding: 0px 2px 4px 2px;")
        layout.addWidget(lbl)

    def _add_checkbox(self, widget, target_layout=None, hint=None):
        layout = target_layout
        if layout is None: return
        widget.setMinimumWidth(1)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(widget)
        if hint:
            self._add_hint(hint, layout)

    def _add_field(self, label_text, widget, target_layout=None, hint=None):
        layout = target_layout
        if layout is None: return
        lbl = QLabel(label_text)
        lbl.setWordWrap(True)
        lbl.setMinimumWidth(1)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 13px; font-weight: 700; margin-top: 4px;")
        layout.addWidget(lbl)
        if isinstance(widget, QLineEdit): widget.setStyleSheet(LINE_EDIT_CSS)
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(widget)
        if hint:
            self._add_hint(hint, layout)
        layout.addSpacing(10)

    def _make_scroll_page(self):
        page = QWidget()
        page.setMinimumWidth(0)
        page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        page.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setMinimumWidth(0)
        scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        content = QWidget()
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        content.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(16)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.settings_stack.addWidget(page)
        return page, vbox

    def _add_internal_back(self, target_layout, title):
        row = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setStyleSheet(page_title_css(18))
        row.addWidget(lbl)
        row.addStretch()
        target_layout.addLayout(row)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {LINE_COLOR}; max-height: 1px; margin: 4px 0px 8px 0px;")
        target_layout.addWidget(line)

    def _nav_card(self, title, subtitle, target_page):
        return SettingsNavCard(title, subtitle, lambda: self._set_settings_section(target_page))

    def _make_reset_button(self):
        btn = QPushButton("אפס הגדרות")
        set_themed_button_icon(btn, ("reset_icon", RESET_SVG_PATH), btn.text(), 20, clear_text=False)
        btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(self.confirm_reset_settings)
        return btn

    def _build_ui_sections(self):
        self.settings_home_page, home = self._make_scroll_page()
        ai_page, ai = self._make_scroll_page()
        safety_page, safety = self._make_scroll_page()
        policy_page, policy_layout = self._make_scroll_page()
        tools_page, tools = self._make_scroll_page()
        voice_page, voice = self._make_scroll_page()
        updates_page, updates = self._make_scroll_page()
        advanced_page, advanced = self._make_scroll_page()
        developer_page, developer = self._make_scroll_page()
        self.developer_page = developer_page

        home.addWidget(self._nav_card("מודלי AI", "בחירת ספק, מודל ומפתחות גישה", ai_page))
        home.addWidget(self._nav_card("אבטחה והרשאות", "פרופיל אישורים, ארגז חול וברירת מחדל לקבצים", safety_page))
        home.addWidget(self._nav_card("שליטה מתקדמת ביכולות", "בחירה אם לאפשר, לשאול או לחסום כל יכולת", policy_page))
        home.addWidget(self._nav_card("כלים ואוטומציה", "דפדפן, מחשב, אימייל וכלים חיצוניים", tools_page))
        home.addWidget(self._nav_card("קול ותצוגה", "אפשרויות הקראה ושימוש בקול", voice_page))
        home.addWidget(self._nav_card("מתקדם", "זמני המתנה, לולאות ותאימות חיבור", advanced_page))
        home.addWidget(self._nav_card("הגדרות מפתחים", "לוגים, Trace והרשאות נמוכות-רמה לכלים חיצוניים", developer_page))
        home.addWidget(self._nav_card("עדכונים", "בדיקה אוטומטית וידנית מול GitHub Releases", updates_page))
        home.addSpacing(8)
        home.addWidget(self._make_reset_button())
        home.addStretch()

        self._add_internal_back(ai, "מודלי AI")
        self._add_field("ספק המודל", self.provider_combo, ai, "בחר את שירות ה-AI שסמארטי ישתמש בו לתשובות ולתכנון פעולות.")
        self._add_field("מפתח גישה לספק המודל", self.api_key_row, ai, "נדרש רק לספקים חיצוניים. המפתח נבדק מול הספק לפני שמירה, נשמר בצורה מוגנת ומוצג רק בסיומת מוסתרת.")
        ai.addWidget(self.api_key_status)
        ai.addWidget(self.api_key_help_hint)
        self._add_field("מודל", self.model_combo, ai, "אפשר להקליד חיפוש חופשי כמו 70b llama instruct; הסינון סלחני לסדר מילים, מקפים ושמות ספקים.")
        self._add_field("כתובת שרת מקומי למודל מקומי", self.local_url, ai, "רלוונטי רק כשמשתמשים במודל מקומי, למשל דרך LM Studio או שרת תואם OpenAI.")
        self._add_field("מפתח חיפוש באינטרנט (Tavily)", self.tavily_key_row, ai, "מאפשר לסמארטי לבצע חיפוש אינטרנט כאשר נדרש מידע עדכני.")
        ai.addWidget(self.tavily_key_help_hint)
        ai.addStretch()

        self._add_internal_back(safety, "אבטחה והרשאות")
        self._add_field("פרופיל הרשאות", self.permission_combo, safety, "הפרופיל המאוזן משתמש בטבלת היכולות: פעולות רגילות רצות מהר, ופעולות רגישות עוצרות לאישור.")
        self._add_section_header("ארגז חול", safety)
        self._add_checkbox(self.sandbox_cb, safety, "מגביל את סמארטי לתיקייה אחת. מצב זה מתאים לעבודה בטוחה על פרויקט או תיקייה מוגדרת.")
        self._add_hint("כאשר ארגז חול פעיל, סמארטי וכלים מסוכנים מוגבלים לתיקייה שנבחרה. כתיבה או שינוי מחוץ אליה ייחסמו.", safety)
        self._add_field("תיקיית ארגז החול", self.sandbox_root_picker, safety, "בחר את התיקייה שבה סמארטי רשאי לעבוד כאשר ארגז החול פעיל.")
        self._add_checkbox(self.sandbox_read_outside_cb, safety, "מאפשר לסמארטי לקרוא קבצים מחוץ לארגז החול, אך עדיין חוסם כתיבה, שינוי ומחיקה מחוץ אליו.")
        self._add_hint("אפשרות זו מתירה קריאה בלבד מחוץ לארגז החול. כתיבה, שינוי ומחיקה מחוץ לתיקייה עדיין חסומים.", safety)
        self._add_section_header("קבצים ונתונים", safety)
        self._add_field("תיקיית ברירת מחדל ליצירת קבצים", self.default_output_dir_picker, safety, "כאשר ביקשת ליצור או לשמור קובץ בלי לציין מיקום, סמארטי ישמור אותו כאן. זו לא מגבלת הרשאה ולא ארגז חול.")
        self._add_checkbox(self.write_outside_dirs_approval_cb, safety, "כאשר האפשרות פעילה, סמארטי יבקש אישור לפני כתיבה מחוץ לתיקיית הפלט. באוטונומיה מלאה האפשרות נכבית אוטומטית, אלא אם ארגז חול פעיל.")
        self._add_checkbox(self.cloud_upload_cb, safety, "כאשר האפשרות פעילה, סמארטי יבקש אישור לפני שליחת קבצים, צילום מסך או אימייל למודל חיצוני.")
        self._add_checkbox(self.mcp_pin_cb, safety, "מחייב התקנת כלים חיצוניים בגרסה קבועה, כדי למנוע שינוי לא צפוי בהתנהגות הכלי.")
        self._add_checkbox(self.raw_shell_approval_cb, safety, "גם במצב אוטונומי, פקודות מערכת בסיכון גבוה יעצרו לאישור משתמש.")
        self._add_checkbox(self.marketplace_approval_cb, safety, "מונע התקנה שקטה של קוד חיצוני חדש ממאגרי MCP או Skills.")
        safety.addStretch()

        self._add_internal_back(policy_layout, "שליטה מתקדמת ביכולות")
        self._add_hint("הפרופיל הראשי מספיק לרוב השימושים. כאן אפשר לדייק יכולות בודדות בלי להפוך את כל מסך האבטחה למסובך.", policy_layout)
        for cap, label in CAPABILITY_LABELS.items():
            self._add_field(label, self.policy_combos[cap], policy_layout, "בחר אם סמארטי יוכל להשתמש ביכולת הזו, יבקש אישור בכל פעם, או יחסום אותה לחלוטין.")
        policy_layout.addStretch()

        self._add_internal_back(tools, "כלים ואוטומציה")
        self._add_checkbox(self.browser_auto_cb, tools, "מאפשר לסמארטי לפתוח דפדפן אוטומטי ולבצע פעולות בדפי אינטרנט, לאחר אישור לפי רמת ההרשאות.")
        self._add_checkbox(self.computer_control_cb, tools, "מאפשר לסמארטי לקרוא את עץ הנגישות של Windows ולפעול על אלמנטים מזוהים. מקלדת/עכבר הם fallback מבוקר בלבד.")
        self._add_checkbox(self.mcp_cb, tools, "מאפשר שימוש בכלים חיצוניים שמרחיבים את יכולות סמארטי, בכפוף להרשאות שהוגדרו.")
        self._add_checkbox(self.skills_beta_cb, tools, "מאפשר שכבת Skills בטא: תהליכי עבודה גבוהים שמכוונים את סמארטי איך להשתמש בכלים קיימים וב-MCP.")
        # Google Drive settings section is intentionally hidden for now.
        self._add_section_header("אימייל", tools)
        self._add_field("כתובת אימייל", self.email, tools, "כתובת האימייל שממנה סמארטי יקרא או ישלח הודעות, אם אישרת שימוש באימייל.")
        self._add_field("סיסמת אפליקציה לאימייל", self.pwd, tools, "סיסמת אפליקציה ייעודית לחשבון האימייל. אל תשתמש בסיסמה הראשית של החשבון.")
        self._add_field("שם שולח", self.email_from_name, tools, "שם תצוגה אופציונלי שיופיע בשדה From.")
        self._add_field("IMAP host", self.email_imap_host, tools, "ריק = זיהוי אוטומטי לפי כתובת האימייל.")
        self._add_field("IMAP port", self.email_imap_port, tools, "ברירת מחדל נפוצה: 993.")
        self._add_checkbox(self.email_imap_ssl_cb, tools, "מומלץ להשאיר פעיל לרוב ספקי האימייל.")
        self._add_field("SMTP host", self.email_smtp_host, tools, "ריק = זיהוי אוטומטי לפי כתובת האימייל.")
        self._add_field("SMTP port", self.email_smtp_port, tools, "ברירת מחדל נפוצה: 587.")
        self._add_checkbox(self.email_smtp_starttls_cb, tools, "מומלץ להשאיר פעיל עבור SMTP בפורט 587.")
        self._add_checkbox(self.email_smtp_ssl_cb, tools, "הפעל רק אם הספק דורש SMTP SSL ישיר, לרוב בפורט 465.")
        self._add_field("גודל מצורף מקסימלי (MB)", self.email_max_attachment_mb, tools, "מגבלת בטיחות לשליחת קבצים מצורפים.")
        tools.addStretch()

        self._add_internal_back(voice, "קול ותצוגה")
        self._add_section_header("מראה", voice)
        self._add_field("מצב תצוגה", self.theme_combo, voice, "בחר מצב כהה, בהיר או התאמה אוטומטית להגדרת המערכת של Windows.")
        self._add_section_header("קול", voice)
        self._add_checkbox(self.tts_cb, voice, "כאשר האפשרות פעילה, סמארטי יקריא בקול את כל התשובות.")
        self._add_checkbox(self.tts_voice_cb, voice, "כאשר האפשרות פעילה, הקריאה הקולית תופעל בעיקר לאחר פנייה קולית מצד המשתמש.")
        self._add_field("קול הקראה", self.tts_voice_combo, voice, "בחירת נקודת קול של Google TTS לעברית.")
        self._add_field("עוצמת הקראה", self.tts_volume_control, voice, "שולט בעוצמת השמע בזמן ההקראה.")
        self._add_section_header("האזנה", voice)
        self._add_field("רגישות מיקרופון", self.voice_sensitivity_control, voice, "ערך גבוה מזהה דיבור חלש מהר יותר; בסביבה רועשת כדאי להוריד מעט.")
        self._add_field("סיום אחרי שקט", self.voice_pause_control, voice, "כמה זמן של שקט יסיים את ההאזנה וישלח את התמלול לעיבוד.")
        self._add_field("המתנה לתחילת דיבור", self.voice_timeout_control, voice, "כמה זמן לחכות לדיבור אחרי הפעלת ההאזנה לפני ביטול.")
        self._add_field("כיול רעש רקע לפני האזנה", self.voice_ambient_control, voice, "0 מתחיל הכי מהר. הגדלה משפרת דיוק בסביבה רועשת אבל מוסיפה השהיה.")
        self._add_checkbox(self.voice_dynamic_energy_cb, voice, "מאפשר לספריית הזיהוי לשנות את סף הרגישות תוך כדי עבודה לפי רעש הרקע.")
        self._add_checkbox(self.voice_beep_cb, voice, "כבוי כברירת מחדל כדי שההאזנה תתחיל מהר ככל האפשר.")
        voice.addStretch()

        self._add_internal_back(updates, "עדכונים")
        self._add_checkbox(self.update_auto_cb, updates, "כשאפשרות זו פעילה, סמארטי יבדוק ברקע אם פורסמה גרסה חדשה ב-GitHub Releases.")
        updates.addWidget(self.update_status_lbl)
        updates.addWidget(self.check_updates_btn)
        updates.addStretch()

        self._add_internal_back(advanced, "מתקדם")
        self._add_checkbox(self.insecure_ssl_cb, advanced, "הגדרת תאימות SSL שמרפה אימות תעודות עבור סביבות שבהן חיבורי HTTPS נחסמים או מוחלפים, למשל בסינוני רשת. פעיל כברירת מחדל כדי לצמצם תקלות חיבור בסביבות מסוננות.")
        self._add_field("זמן המתנה לפקודות מחשב (שניות)", self.cmd_timeout, advanced, "משך הזמן המקסימלי שסמארטי ימתין לפקודת מערכת לפני עצירה.")
        self._add_field("זמן המתנה לכלים מותאמים אישית (שניות)", self.tool_timeout, advanced, "משך הזמן המקסימלי להרצת כלי מותאם אישית לפני שסמארטי מפסיק אותו.")
        self._add_field("זמן המתנה לכלים חיצוניים (שניות)", self.mcp_timeout, advanced, "משך הזמן המקסימלי שסמארטי ימתין לתשובה מכלי חיצוני.")
        self._add_field("זמן כולל מקסימלי למשימה (שניות)", self.total_timeout, advanced, "מונע מלולאת הסוכן להיתקע זמן רב מדי בבקשה אחת.")
        self._add_field("מגבלת תווים בתוצאת כלי", self.max_chars_edit, advanced, "מגביל את אורך פלט הכלים שנשלח חזרה למודל, כדי לשמור על יציבות ועל עלויות נמוכות.")
        self._add_field("תקציב טוקנים יומי", self.daily_token_budget, advanced, "0 פירושו ללא מגבלה קשיחה כרגע; הנתון נשמר לשימוש במדיניות תקציב.")
        self._add_field("תקציב עלות יומי בדולר", self.daily_cost_budget, advanced, "0 פירושו ללא מגבלה קשיחה כרגע; מוצג למעקב ובקרת עלויות.")
        lbl_loops = QLabel("מספר סבבי פעולה מקסימלי")
        lbl_loops.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 13px; font-weight: 700;")
        advanced.addWidget(lbl_loops)
        self._add_hint("קובע כמה פעמים סמארטי יכול לחשוב, לבחור כלי ולעבד תוצאה באותה בקשה. הערך העליון מאפשר עבודה ללא מגבלת סבבים.", advanced)
        loops_layout = QHBoxLayout()
        loops_layout.addWidget(self.loops_slider)
        loops_layout.addWidget(self.loops_val_lbl)
        advanced.addLayout(loops_layout)
        advanced.addStretch()

        self._add_internal_back(developer, "הגדרות מפתחים")
        self._add_checkbox(self.developer_trace_cb, developer, "שומר Trace פנימי של תכנון, בחירת כלים, תוצאות ביניים ותשובה סופית.")
        self._add_checkbox(self.audit_log_cb, developer, "שומר יומן אודיט מקומי של החלטות הרשאה, התחלת כלים וסיום כלים.")
        self._add_checkbox(self.redact_logs_cb, developer, "מסתיר מפתחות, סיסמאות ופרטים רגישים מקובצי הלוג ככל האפשר.")
        self._add_field("תיקיות גישה לכלים חיצוניים (MCP)", self.mcp_allowed_dirs, developer, "שורשי תיקיות שמותר להעביר לכלי MCP כתיאום גישה. זו אינה מגבלת כתיבה של סמארטי; כאשר ארגז חול פעיל, ארגז החול גובר על ההגדרה הזו.")
        refresh_logs_btn = QPushButton("רענן לוגים")
        refresh_logs_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        refresh_logs_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_logs_btn.clicked.connect(self.load_developer_logs)
        clear_logs_btn = QPushButton("נקה לוג")
        clear_logs_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        clear_logs_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_logs_btn.clicked.connect(self.clear_selected_developer_log)
        self.selected_developer_log = getattr(self, "selected_developer_log", "agent")
        self.developer_log_buttons = {}
        log_actions = QHBoxLayout()
        log_actions.setSpacing(8)
        log_actions.addWidget(refresh_logs_btn)
        log_actions.addWidget(clear_logs_btn)
        log_actions.addStretch()
        developer.addLayout(log_actions)
        log_switcher = QHBoxLayout()
        log_switcher.setSpacing(8)
        for key, label in [("agent", "Agent Log"), ("trace", "Runtime Trace"), ("audit", "Audit Log"), ("skills", "Skills Log")]:
            btn = QPushButton(label)
            btn.setMinimumWidth(0)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(lambda _=None, log_key=key: self.show_developer_log(log_key))
            self.developer_log_buttons[key] = btn
            log_switcher.addWidget(btn)
        developer.addLayout(log_switcher)
        self.developer_log_text = QTextEdit()
        self.developer_log_text.setReadOnly(True)
        self.developer_log_text.setMinimumWidth(0)
        self.developer_log_text.setMinimumHeight(360)
        self.developer_log_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.developer_log_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.developer_log_text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.developer_log_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        log_palette = self.developer_log_text.palette()
        log_palette.setColor(QPalette.ColorRole.Text, QColor(TEXT_COLOR))
        log_palette.setColor(QPalette.ColorRole.Base, QColor(FIELD_COLOR))
        self.developer_log_text.setPalette(log_palette)
        self.developer_log_text.setStyleSheet(LOG_TEXT_CSS)
        developer.addWidget(self.developer_log_text)
        self.load_developer_logs()

        self.settings_stack.setCurrentWidget(self.settings_home_page)

    def on_provider_change(self, text):
        text = normalize_provider_name(text)
        self._update_provider_key_help()
        if text == "local":
            self.api_key_edit.set_secret("")
            self.api_key_edit.setPlaceholderText("לא נדרש מפתח למודל מקומי")
            self.api_key_edit.setEnabled(False)
            self.api_key_help_link.setVisible(False)
            self.api_key_help_hint.setVisible(False)
            self.api_key_status.setText("")
        else:
            self.core.ensure_provider_secret(text)
            secret_key = provider_secret_key(text)
            saved_key = self.core.settings.get(secret_key, "") if secret_key else ""
            self.api_key_edit.setEnabled(True)
            self.api_key_help_link.setVisible(bool(provider_help_url(text)))
            self.api_key_help_hint.setVisible(bool(provider_key_instructions(text)))
            self.api_key_edit.setPlaceholderText("מפתח גישה לספק המודל")
            self.api_key_edit.set_secret(saved_key)
            self._validated_api_keys.add((text, sanitize_secret_value(saved_key)))
            self.api_key_status.setText(f"מפתח שמור: {mask_secret_value(saved_key)}" if saved_key else "")
        if hasattr(self.model_combo, "set_loading_text"):
            self.model_combo.set_loading_text("טוען מודלים...")
        else:
            self.model_combo.clear()
            self.model_combo.addItem("טוען מודלים...")
        self.fetch_worker = FetchModelsWorker(
            text,
            self.api_key_edit.secret(),
            self.core.settings.get("local_server_url", ""),
            self.core.settings.get("allow_insecure_ssl_compat", True)
        )
        self.fetch_worker.finished_signal.connect(lambda models: self.populate_models(models, text))
        self.fetch_worker.start()
        self._schedule_autosave()

    def ensure_models_loaded(self):
        if self.models_loaded:
            return
        self.models_loaded = True
        self.on_provider_change(self.provider_combo.currentText())

    def populate_models(self, models, provider):
        previous_suppress = getattr(self, "_suppress_autosave", False)
        self._suppress_autosave = True
        if models:
            saved_model = self.core.settings.get(f"selected_{provider}_model", "")
            if hasattr(self.model_combo, "set_models"):
                self.model_combo.set_models(models, saved_model)
            else:
                self.model_combo.clear()
                self.model_combo.addItems(models)
                if saved_model in models: self.model_combo.setCurrentText(saved_model)
        else:
            fallback = self.core.settings.get(f"selected_{provider}_model", "") or provider_default_model(provider)
            if hasattr(self.model_combo, "set_models"):
                self.model_combo.set_models([fallback], fallback)
            else:
                self.model_combo.clear()
                self.model_combo.addItem(fallback)
        self._suppress_autosave = previous_suppress
        self._schedule_autosave()

    def refresh_google_drive_status(self):
        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        return

    def connect_google_drive(self):
        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        return

    def disconnect_google_drive(self):
        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        return

    def _register_autosave_handlers(self):
        combos = [self.provider_combo, self.tts_voice_combo]
        combos.extend(self.policy_combos.values())
        for combo in combos:
            combo.currentIndexChanged.connect(lambda _=None: self._schedule_autosave())
        if hasattr(self.model_combo, "modelCommitted"):
            self.model_combo.modelCommitted.connect(lambda _=None: self._schedule_autosave())
        else:
            self.model_combo.currentIndexChanged.connect(lambda _=None: self._schedule_autosave())
        self.theme_combo.currentIndexChanged.connect(self.on_theme_mode_change)
        self.autonomy_combo.currentIndexChanged.connect(self.on_autonomy_profile_change)
        self.permission_combo.currentIndexChanged.connect(self.on_permission_profile_change)

        for cb in [
            self.sandbox_cb, self.sandbox_read_outside_cb, self.redact_logs_cb, self.audit_log_cb,
            self.developer_trace_cb, self.raw_shell_approval_cb, self.marketplace_approval_cb,
            self.browser_auto_cb, self.computer_control_cb, self.mcp_cb, self.skills_beta_cb,
            self.update_auto_cb,
            self.tts_cb, self.tts_voice_cb, self.insecure_ssl_cb, self.cloud_upload_cb,
            self.write_outside_dirs_approval_cb, self.mcp_pin_cb,
            self.email_imap_ssl_cb, self.email_smtp_ssl_cb, self.email_smtp_starttls_cb,
            self.voice_dynamic_energy_cb, self.voice_beep_cb
        ]:
            cb.stateChanged.connect(lambda _=None: self._schedule_autosave())

        self.api_key_edit.secretEdited.connect(self._on_api_key_edited)
        self.api_key_edit.editingFinished.connect(self._validate_current_api_key_before_save)
        self.tavily_key.secretEdited.connect(lambda _=None: self._schedule_autosave())

        for edit in [
            self.tavily_key, self.local_url, self.email, self.pwd,
            self.email_from_name, self.email_imap_host, self.email_imap_port,
            self.email_smtp_host, self.email_smtp_port, self.email_max_attachment_mb,
            self.cmd_timeout, self.tool_timeout, self.mcp_timeout, self.max_chars_edit,
            self.total_timeout, self.daily_token_budget, self.daily_cost_budget
        ]:
            edit.textEdited.connect(lambda _=None: self._schedule_autosave())
            edit.editingFinished.connect(self._schedule_autosave)

        self.default_output_dir_picker.pathsChanged.connect(self._schedule_autosave)
        self.mcp_allowed_dirs.pathsChanged.connect(self._schedule_autosave)
        self.sandbox_root_picker.pathsChanged.connect(self._schedule_autosave)
        self.loops_slider.valueChanged.connect(lambda _=None: self._schedule_autosave())
        for slider in [
            self.tts_volume_slider, self.voice_sensitivity_slider,
            self.voice_pause_slider, self.voice_timeout_slider,
            self.voice_ambient_slider
        ]:
            slider.valueChanged.connect(lambda _=None: self._schedule_autosave())

    def _schedule_autosave(self):
        if getattr(self, "_suppress_autosave", False):
            return
        self.autosave_timer.start()

    def _on_api_key_edited(self, _text=""):
        if getattr(self, "_suppress_autosave", False):
            return
        provider = normalize_provider_name(self.provider_combo.currentText())
        if provider == "local":
            return
        key = sanitize_secret_value(self.api_key_edit.secret())
        if key:
            self.api_key_status.setText("המפתח ייבדק לפני שמירה...")
            self.api_key_validation_timer.start()
        else:
            self._api_key_validation_generation += 1
            self.api_key_validation_timer.stop()
            self.api_key_status.setText("המפתח יימחק בשמירה.")
            self._schedule_autosave()

    def _api_key_is_validated(self, provider, key):
        key = sanitize_secret_value(key)
        return not key or (normalize_provider_name(provider), key) in self._validated_api_keys

    def _validate_current_api_key_before_save(self):
        if getattr(self, "_suppress_autosave", False):
            return
        provider = normalize_provider_name(self.provider_combo.currentText())
        if provider == "local":
            return
        key = sanitize_secret_value(self.api_key_edit.secret())
        secret_key = provider_secret_key(provider)
        if not secret_key:
            return
        if not key:
            self.api_key_status.setText("המפתח יימחק בשמירה.")
            self._schedule_autosave()
            return
        saved_key = sanitize_secret_value(self.core.settings.get(secret_key, ""))
        if key == saved_key or self._api_key_is_validated(provider, key):
            self.api_key_status.setText(f"מפתח שמור: {mask_secret_value(key)}")
            self._schedule_autosave()
            return
        self._api_key_validation_generation += 1
        generation = self._api_key_validation_generation
        self.api_key_status.setText(f"בודק מפתח מול {provider_display_name(provider)}...")
        worker = ApiKeyValidationWorker(
            provider,
            key,
            self.local_url.text().strip() or self.core.settings.get("local_server_url", ""),
            self.insecure_ssl_cb.isChecked() if hasattr(self, "insecure_ssl_cb") else self.core.settings.get("allow_insecure_ssl_compat", True),
        )
        self.api_key_validation_worker = worker
        worker.finished_signal.connect(lambda p, k, ok, msg, models, gen=generation: self._on_api_key_validation_finished(gen, p, k, ok, msg, models))
        worker.start()

    def _on_api_key_validation_finished(self, generation, provider, key, ok, message, models):
        if generation != self._api_key_validation_generation:
            return
        provider = normalize_provider_name(provider)
        current_provider = normalize_provider_name(self.provider_combo.currentText())
        if provider != current_provider or sanitize_secret_value(self.api_key_edit.secret()) != sanitize_secret_value(key):
            return
        if not ok:
            self.api_key_status.setText(f"המפתח לא נשמר: {message or 'בדיקת תקינות נכשלה'}.")
            return
        secret_key = provider_secret_key(provider)
        self._validated_api_keys.add((provider, sanitize_secret_value(key)))
        self.core.settings["api_mode"] = provider
        self.core.settings[secret_key] = sanitize_secret_value(key)
        self.core._save_settings()
        self.api_key_edit.set_secret(key)
        self.api_key_status.setText(f"מפתח תקין ושמור: {mask_secret_value(key)}")
        if models:
            self.populate_models(models, provider)
        self.core.system_prompt = self.core._load_system_prompt()
        self.core.setup_model()
        self._schedule_autosave()

    def _permission_profile_key(self):
        return {1: "locked_down", 2: "balanced", 3: "max_autonomy"}.get(self.permission_combo.currentIndex() + 1, "balanced")

    def _autonomy_profile_key(self):
        idx = max(0, min(self.autonomy_combo.currentIndex(), len(self.autonomy_options) - 1))
        return self.autonomy_options[idx][0]

    def _theme_mode_key(self):
        idx = max(0, min(self.theme_combo.currentIndex(), len(self.theme_options) - 1))
        return self.theme_options[idx][0]

    def on_theme_mode_change(self):
        if getattr(self, "_suppress_autosave", False):
            return
        theme_mode = self._theme_mode_key()
        self.autosave_timer.stop()
        self.core.settings.setdefault("ui_preferences", {})["theme_mode"] = theme_mode
        self.core._save_settings()
        self.main_window.apply_theme(theme_mode, refresh_messages=False)
        self._refresh_live_theme_styles()
        self.main_window.refresh_chat_messages_async()
        QTimer.singleShot(120, self.main_window.invalidate_themed_pages)

    def _refresh_live_theme_styles(self):
        self.setStyleSheet("background: transparent;")
        self.settings_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        refresh_back_button_icon(self.back_btn)
        for label in self.findChildren(QLabel):
            if label.property("smartiHighContrastLink"):
                apply_high_contrast_link_label(label)
                continue
            if label.property("smartiValuePill"):
                label.setStyleSheet(self._value_pill_css())
                continue
            style = label.styleSheet() or ""
            if "color:" not in style:
                continue
            size_match = re.search(r"font-size:\s*(\d+)px", style)
            size = int(size_match.group(1)) if size_match else 13
            is_bold = "font-weight: 700" in style
            if size >= 18:
                label.setStyleSheet(page_title_css(size))
            elif size >= 16 and is_bold:
                label.setStyleSheet(section_title_css(size))
            elif is_bold:
                label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: {size}px; font-weight: 700; background: transparent;")
            else:
                label.setStyleSheet(muted_label_css(size))
        for combo in self.findChildren(NoScrollComboBox):
            combo.setStyleSheet(COMBOBOX_CSS)
        for model_picker in self.findChildren(SearchableModelComboBox):
            model_picker.apply_theme()
        for segment in self.findChildren(SegmentedControl):
            segment.apply_theme()
        for edit in self.findChildren(QLineEdit):
            edit.setStyleSheet(LINE_EDIT_CSS)
        for picker in self.findChildren(DirectoryPicker):
            picker.apply_theme()
        log_buttons = set(getattr(self, "developer_log_buttons", {}).values())
        for button in self.findChildren(QPushButton):
            if button is self.back_btn or button in log_buttons:
                continue
            if button.property("smartiSecretClearButton"):
                button.setStyleSheet(icon_button_css(34, danger=True))
                continue
            parent = button.parent()
            if parent and parent.objectName() == "SegmentedControl":
                continue
            button.setStyleSheet(SECONDARY_BUTTON_CSS)
        refresh_themed_widget_icons(self)
        for toggle in self.findChildren(SmartiCheckBox):
            toggle.update()
        for card in self.findChildren(SettingsNavCard):
            card.apply_theme()
        for slider in self.findChildren(RtlFillSlider):
            slider.setStyleSheet(SLIDER_CSS)
        for label in self.findChildren(QLabel):
            if label.property("smartiValuePill"):
                label.setStyleSheet(self._value_pill_css())
        if hasattr(self, "developer_log_text"):
            self.developer_log_text.setStyleSheet(LOG_TEXT_CSS)
        if hasattr(self, "api_key_help_link"):
            self._update_provider_key_help()
        if hasattr(self, "tavily_key_help_link"):
            self._set_external_link(self.tavily_key_help_link, provider_help_url(secret_key="tavily_api_key"), "קבל מפתח")
        self._refresh_developer_log_buttons()

    def _apply_profile_to_widgets(self, profile_key):
        profile = AUTONOMY_PROFILES.get(profile_key, AUTONOMY_PROFILES["balanced"])
        self.permission_combo.setCurrentIndex(max(0, min(2, profile["permission_level"] - 1)))
        action_index = {"ask": 0, "allow": 1, "deny": 2}
        for cap, combo in self.policy_combos.items():
            combo.setCurrentIndex(action_index.get(profile["policy_matrix"].get(cap, "ask"), 0))
        self.raw_shell_approval_cb.setChecked(bool(profile["raw_shell_requires_approval"]))
        self.marketplace_approval_cb.setChecked(bool(profile["marketplace_install_requires_approval"]))
        self.cloud_upload_cb.setChecked(bool(profile["require_approval_for_cloud_upload"]))
        self.write_outside_dirs_approval_cb.setChecked(bool(profile["write_outside_allowed_dirs_requires_approval"]))

    def on_autonomy_profile_change(self):
        if getattr(self, "_suppress_autosave", False):
            return
        profile_key = self._autonomy_profile_key()
        self._suppress_autosave = True
        try:
            self._apply_profile_to_widgets(profile_key)
        finally:
            self._suppress_autosave = False
        self._schedule_autosave()

    def on_permission_profile_change(self):
        if getattr(self, "_suppress_autosave", False):
            return
        profile_key = self._permission_profile_key()
        profile_keys = [key for key, _ in self.autonomy_options]
        self._suppress_autosave = True
        try:
            if profile_key in profile_keys:
                self.autonomy_combo.setCurrentIndex(profile_keys.index(profile_key))
            self._apply_profile_to_widgets(profile_key)
        finally:
            self._suppress_autosave = False
        self._schedule_autosave()

    def _save_from_ui(self):
        if getattr(self, "_suppress_autosave", False):
            return
        before = copy.deepcopy(self.core.settings)
        provider = self.provider_combo.currentText()
        selected_model = self.model_combo.selected_model() if hasattr(self.model_combo, "selected_model") else self.model_combo.currentText()
        self.core.settings["api_mode"] = provider
        self.core.settings["autonomy_mode"] = self._autonomy_profile_key()
        self.core.settings.setdefault("ui_preferences", {})["theme_mode"] = self._theme_mode_key()
        if selected_model and selected_model != "טוען מודלים...":
            self.core.settings[f"selected_{provider}_model"] = selected_model
        if provider != "local":
            secret_key = provider_secret_key(provider)
            candidate_key = sanitize_secret_value(self.api_key_edit.secret())
            previous_key = sanitize_secret_value(before.get(secret_key, "")) if secret_key else ""
            if secret_key and not candidate_key:
                self.core.mark_secret_for_deletion(secret_key)
            elif secret_key and (candidate_key == previous_key or self._api_key_is_validated(provider, candidate_key)):
                self.core.settings[secret_key] = candidate_key
            elif secret_key and candidate_key:
                self.core.settings[secret_key] = previous_key
                self._validate_current_api_key_before_save()
            elif secret_key:
                self.core.settings[secret_key] = previous_key
        tavily_key = sanitize_secret_value(self.tavily_key.secret() if hasattr(self.tavily_key, "secret") else self.tavily_key.text())
        if tavily_key:
            self.core.settings["tavily_api_key"] = tavily_key
        else:
            self.core.mark_secret_for_deletion("tavily_api_key")
        self.core.settings["local_server_url"] = self.local_url.text().strip() or "http://localhost:1234/v1"
        self.core.settings["email_address"] = self.email.text()
        self.core.settings["email_password"] = self.pwd.text().replace(" ", "")
        self.core.settings["email_from_name"] = self.email_from_name.text().strip()
        self.core.settings["email_imap_host"] = self.email_imap_host.text().strip()
        self.core.settings["email_smtp_host"] = self.email_smtp_host.text().strip()
        self.core.settings["email_imap_ssl"] = self.email_imap_ssl_cb.isChecked()
        self.core.settings["email_smtp_ssl"] = self.email_smtp_ssl_cb.isChecked()
        self.core.settings["email_smtp_starttls"] = self.email_smtp_starttls_cb.isChecked()
        for key, widget, default in [("email_imap_port", self.email_imap_port, 993), ("email_smtp_port", self.email_smtp_port, 587), ("email_max_attachment_mb", self.email_max_attachment_mb, 20)]:
            try:
                self.core.settings[key] = max(1, int(widget.text().strip()))
            except Exception:
                self.core.settings[key] = default
        self.core.settings["read_aloud_all"] = self.tts_cb.isChecked()
        self.core.settings["read_aloud_voice_only"] = self.tts_voice_cb.isChecked()
        self.core.settings["tts_voice_id"] = self.tts_voice_combo.currentData() or "co.il"
        self.core.settings["tts_volume"] = int(self.tts_volume_slider.value())
        self.core.settings["voice_sensitivity"] = int(self.voice_sensitivity_slider.value())
        self.core.settings["voice_pause_threshold"] = round(self.voice_pause_slider.value() / 10.0, 1)
        self.core.settings["voice_listen_timeout"] = int(self.voice_timeout_slider.value())
        self.core.settings["voice_ambient_noise_duration"] = round(self.voice_ambient_slider.value() / 10.0, 1)
        self.core.settings["voice_dynamic_energy_threshold"] = self.voice_dynamic_energy_cb.isChecked()
        self.core.settings["voice_beep_enabled"] = self.voice_beep_cb.isChecked()
        self.core.settings["enable_mcp_clawhub"] = self.mcp_cb.isChecked()
        self.core.settings["enable_skills_beta"] = self.skills_beta_cb.isChecked()
        self.core.settings["updates_auto_check"] = self.update_auto_cb.isChecked()
        self.core.settings["enable_browser_automation"] = self.browser_auto_cb.isChecked()
        self.core.settings["enable_computer_control"] = self.computer_control_cb.isChecked()
        self.core.settings["privacy_redact_logs"] = self.redact_logs_cb.isChecked()
        self.core.settings.setdefault("privacy", {})["redact_logs"] = self.redact_logs_cb.isChecked()
        self.core.settings["audit_log_enabled"] = self.audit_log_cb.isChecked()
        self.core.settings.setdefault("privacy", {})["audit_enabled"] = self.audit_log_cb.isChecked()
        self.core.settings["enable_developer_trace"] = self.developer_trace_cb.isChecked()
        self.core.settings["raw_shell_requires_approval"] = self.raw_shell_approval_cb.isChecked()
        self.core.settings["marketplace_install_requires_approval"] = self.marketplace_approval_cb.isChecked()
        self.core.settings["permission_level"] = self.permission_combo.currentIndex() + 1
        action_by_index = {0: "ask", 1: "allow", 2: "deny"}
        self.core.settings["policy_matrix"] = {cap: action_by_index.get(combo.currentIndex(), "ask") for cap, combo in self.policy_combos.items()}
        self.core.settings["require_approval_for_cloud_upload"] = self.cloud_upload_cb.isChecked()
        self.core.settings["write_outside_allowed_dirs_requires_approval"] = self.write_outside_dirs_approval_cb.isChecked()
        self.core.settings["mcp_require_pinned_versions"] = self.mcp_pin_cb.isChecked()
        self.core.settings["allow_insecure_ssl_compat"] = self.insecure_ssl_cb.isChecked()
        self.core.settings["sandbox_enabled"] = self.sandbox_cb.isChecked()
        self.core.settings["sandbox_root_dir"] = self.sandbox_root_picker.path() or OUTPUTS_DIR
        self.core.settings["sandbox_allow_read_outside"] = self.sandbox_read_outside_cb.isChecked()
        default_output_dir = self.default_output_dir_picker.path() or OUTPUTS_DIR
        self.core.settings["default_output_dir"] = default_output_dir
        self.core.settings["allowed_write_dirs"] = [default_output_dir]
        self.core.settings["mcp_allowed_directories"] = self.mcp_allowed_dirs.paths() or [APP_DIR]
        for key, widget, default in [("command_timeout_seconds", self.cmd_timeout, 60), ("tool_timeout_seconds", self.tool_timeout, 120), ("mcp_timeout_seconds", self.mcp_timeout, 60), ("max_tool_output_chars", self.max_chars_edit, 100000), ("max_total_task_seconds", self.total_timeout, 900)]:
            try: self.core.settings[key] = max(5, int(widget.text().strip()))
            except: self.core.settings[key] = default
        self.core.settings.setdefault("budgets", {})
        for key, widget in [("daily_token_budget", self.daily_token_budget), ("daily_cost_budget_usd", self.daily_cost_budget)]:
            try:
                value = float(widget.text().strip())
                self.core.settings["budgets"][key] = max(0, int(value) if key == "daily_token_budget" else value)
            except Exception:
                self.core.settings["budgets"][key] = 0
        slider_loops = self.loops_slider.value()
        self.core.settings["max_agent_loops"] = 0 if slider_loops > 30 else slider_loops
        changed = [key for key in sorted(set(before.keys()) | set(self.core.settings.keys())) if before.get(key) != self.core.settings.get(key)]
        if not changed:
            return
        self.core._save_settings()
        model_reload_keys = {"api_mode", "local_server_url"} | model_provider_secret_keys()
        needs_model_reload = any(key in model_reload_keys or key.startswith("selected_") for key in changed)
        needs_mcp_refresh = any(key in {
            "enable_mcp_clawhub", "enable_skills_beta", "mcp_require_pinned_versions",
            "mcp_allowed_directories", "allow_insecure_ssl_compat",
        } for key in changed)
        if needs_mcp_refresh:
            self.core._sync_trusted_mcp_packages()
            self.core._ensure_mcp_config()
        if needs_model_reload:
            self.core.system_prompt = self.core._load_system_prompt()
            self.core.setup_model()
        if selected_model and selected_model != "טוען מודלים...":
            self.main_window.subtitle.setText(self.main_window.format_model_name(selected_model))
        logging.info(f"SETTINGS | auto_saved | changed={', '.join(changed[:16])}{'...' if len(changed) > 16 else ''}")
        if getattr(self.core, "audit_logger", None):
            self.core.audit_logger.record("settings_auto_save", {"changed": changed}, self.core.settings)

    def save(self):
        self._save_from_ui()

    def confirm_reset_settings(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle("איפוס הגדרות")
        dlg.setText("לאפס את כל ההגדרות וההרשאות לברירת המחדל של סמארטי?")
        dlg.setInformativeText("הפעולה תאפס גם מפתחות, הרשאות כלים, טבלת יכולות, תיקיות והגדרות מפתחים. ייווצר גיבוי לקובץ ההגדרות הנוכחי.")
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dlg.button(QMessageBox.StandardButton.Yes).setText("אפס")
        dlg.button(QMessageBox.StandardButton.No).setText("בטל")
        if dlg.exec() != QMessageBox.StandardButton.Yes:
            return
        backup_path = self.core.reset_settings_to_defaults()
        QMessageBox.information(self, "ההגדרות אופסו", f"ההגדרות אופסו לברירת המחדל.\nגיבוי: {backup_path or 'לא נוצר גיבוי'}")
        self.main_window.rebuild_settings_page()

    def _tail_file(self, path, max_lines=160):
        try:
            if not os.path.exists(path):
                return []
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return [line.rstrip("\n") for line in f.readlines()[-max_lines:]]
        except Exception as e:
            return [f"ERROR reading {os.path.basename(path)}: {e}"]

    def _format_audit_tail(self, max_lines=120):
        rows = []
        for line in self._tail_file(AUDIT_LOG_FILE, max_lines):
            try:
                record = json.loads(line)
                payload = record.get("payload", {}) or {}
                preview = payload.get("preview") or payload.get("details") or payload.get("error") or ""
                compact_payload = ", ".join(f"{k}={v}" for k, v in payload.items() if k != "preview")
                row = f"{record.get('time', '')} | {record.get('event', '')}"
                if compact_payload:
                    row += f" | {compact_payload}"
                if preview:
                    row += f"\n    {str(preview).replace(chr(10), chr(10) + '    ')[:900]}"
                rows.append(row)
            except Exception:
                rows.append(line)
        return rows or ["אין עדיין רשומות אודיט."]

    def _developer_log_button_style(self, active=False):
        if active:
            return f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
                    color: {ACCENT_TEXT_COLOR};
                    border: 1px solid rgba(255,255,255,0.18); border-radius: 18px;
                    padding: 9px 14px; font-size: 13px; font-weight: 700;
                }}
            """
        return SECONDARY_BUTTON_CSS

    def _refresh_developer_log_buttons(self):
        for key, btn in getattr(self, "developer_log_buttons", {}).items():
            btn.setStyleSheet(self._developer_log_button_style(key == getattr(self, "selected_developer_log", "agent")))

    def show_developer_log(self, key):
        self.selected_developer_log = key
        self.load_developer_logs()

    def _selected_developer_log_label(self):
        return {
            "agent": "Agent Log",
            "trace": "Runtime Trace",
            "audit": "Audit Log",
            "skills": "Skills Log"
        }.get(getattr(self, "selected_developer_log", "agent"), "Agent Log")

    def clear_selected_developer_log(self):
        selected = getattr(self, "selected_developer_log", "agent")
        label = self._selected_developer_log_label()
        dlg = QMessageBox(self)
        dlg.setWindowTitle("ניקוי לוג")
        dlg.setText(f"לנקות את {label}?")
        dlg.setInformativeText("הפעולה תמחק את תוכן הלוג הנוכחי בלבד.")
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dlg.button(QMessageBox.StandardButton.Yes).setText("נקה")
        dlg.button(QMessageBox.StandardButton.No).setText("בטל")
        if dlg.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            if selected == "trace":
                self.core.settings["_runtime_trace"] = []
                self.core._save_settings()
            else:
                path_by_log = {
                    "agent": AGENT_LOG_FILE,
                    "audit": AUDIT_LOG_FILE,
                    "skills": SKILL_LOG_FILE
                }
                path = path_by_log.get(selected, AGENT_LOG_FILE)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("")
            logging.info(f"DEVELOPER_LOG | cleared | selected={selected}")
        except Exception as e:
            QMessageBox.warning(self, "שגיאה בניקוי לוג", str(e))
        self.load_developer_logs()

    def _runtime_trace_lines(self):
        rows = ["=== Runtime Trace ==="]
        trace = self.core.settings.get("_runtime_trace", [])[-120:]
        if trace:
            for item in trace:
                rows.append(f"{item.get('time')} | {item.get('stage')} | {item.get('detail')}")
        else:
            rows.append("אין עדיין Trace בזיכרון.")
        return rows

    def load_developer_logs(self):
        self._refresh_developer_log_buttons()
        selected = getattr(self, "selected_developer_log", "agent")
        if selected == "trace":
            lines = self._runtime_trace_lines()
        elif selected == "audit":
            lines = ["=== Audit Log ==="]
            lines.extend(self._format_audit_tail(180))
        elif selected == "skills":
            lines = ["=== Skills Log ==="]
            lines.extend(self._tail_file(SKILL_LOG_FILE, 180) or ["אין עדיין רשומות Skills."])
        else:
            self.selected_developer_log = "agent"
            lines = ["=== Agent Log ==="]
            lines.extend(self._tail_file(AGENT_LOG_FILE, 300) or ["אין עדיין רשומות Agent Log."])
        if hasattr(self, "developer_log_text"):
            self.developer_log_text.setPlainText("\n".join(lines))
            QTimer.singleShot(0, lambda: self.scroll_developer_log("bottom"))

    def scroll_developer_log(self, where):
        if not hasattr(self, "developer_log_text"):
            return
        bar = self.developer_log_text.verticalScrollBar()
        if where == "top":
            bar.setValue(bar.minimum())
        elif where == "middle":
            bar.setValue((bar.maximum() + bar.minimum()) // 2)
        else:
            bar.setValue(bar.maximum())

class AboutPage(QWidget):
    def __init__(self, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.main_window = main_window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        
        top_bar = QHBoxLayout()
        top_bar.addWidget(create_back_button(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)))
        title = QLabel("אודות")
        title.setStyleSheet(page_title_css(18))
        top_bar.addWidget(title)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 8)
        content_layout.setSpacing(16)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll)

        hero = QFrame()
        hero.setStyleSheet(card_css(18, 8))
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 16)
        hero_layout.setSpacing(10)

        logo_lbl = QLabel()
        logo_lbl.setFixedSize(184, 184)
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_lbl.setStyleSheet("border: none; background: transparent;")
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                canvas = QPixmap(184, 184)
                canvas.fill(Qt.GlobalColor.transparent)
                scaled_logo = pixmap.scaled(146, 146, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                painter = QPainter(canvas)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawPixmap((canvas.width() - scaled_logo.width()) // 2, (canvas.height() - scaled_logo.height()) // 2, scaled_logo)
                painter.end()
                logo_lbl.setPixmap(canvas)
        else:
            logo_lbl.setText("S")
            logo_lbl.setFont(QFont("Segoe UI", 46, QFont.Weight.Bold))
            logo_lbl.setStyleSheet(f"color: {ACCENT_COLOR}; border: none; background: transparent;")

        hero_text = QVBoxLayout()
        hero_text.setSpacing(7)
        app_name = QLabel("Smarti AI Agent for Windows")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_name.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 20px; font-weight: 800; border: none;")
        app_name.setWordWrap(True)
        tagline = QLabel("סוכן עבודה אישי ל-Windows שמבין משימות, מפעיל כלים מקומיים, עובד עם קבצים, אינטרנט, דפדפן, אימייל ומשימות רקע, ומסכם תוצאות בעברית.")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(muted_label_css(13) + " border: none;")
        tagline.setWordWrap(True)
        version = QLabel(f"גרסה {APP_VERSION}")
        version.setStyleSheet(
            f"background: {GLASS_COLOR}; color: {ACCENT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 14px; padding: 6px 10px; font-size: 12px; font-weight: 800;"
        )
        version.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        hero_text.addWidget(app_name)
        hero_text.addWidget(tagline)
        hero_text.addWidget(version, 0, Qt.AlignmentFlag.AlignCenter)

        hero_layout.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignHCenter)
        hero_layout.addLayout(hero_text)
        content_layout.addWidget(hero)

        overview = QLabel(
            "סמארטי בנוי כשותף עבודה מקומי: הוא יכול לתכנן, לבצע, לבדוק ולחזור עם תוצאה שימושית, תוך שמירה על מדיניות הרשאות, לוגים ואוטונומיה שניתנת לשליטה מההגדרות."
        )
        overview.setWordWrap(True)
        overview.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; line-height: 1.5;")
        content_layout.addWidget(overview)

        github_btn = QPushButton("פתח את מאגר GitHub")
        github_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        github_btn.setToolTip("פתיחת מאגר הפרויקט ב-GitHub")
        github_btn.setMinimumWidth(0)
        github_btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        github_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT_TINT}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 18px; padding: 11px 14px; font-size: 13px; font-weight: 800; text-align: center; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; color: {ACCENT_COLOR}; border-color: {LINE_COLOR}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_TINT_STRONG}; border-color: {ACCENT_PINK_COLOR}; }}"
        )
        github_btn.clicked.connect(lambda: webbrowser.open("https://github.com/menachem-dadon/SmartiAI-Agent-for-Windows"))
        content_layout.addWidget(github_btn)

        content_layout.addWidget(self._section_title("יכולות מרכזיות"))
        features = QVBoxLayout()
        features.setSpacing(10)
        feature_items = [
            ("קבצים ומסמכים", "חיפוש, קריאה, סיכום, יצירת קבצי טקסט, OCR ותיקיות עבודה."),
            ("אינטרנט ודפדפן", "חיפוש מידע עדכני, קריאת אתרים ואוטומציה בדפדפן ייעודי."),
            ("משימות רקע", "תזמון בדיקות, תזכורות, משימות מחזוריות והרצה מחדש."),
            ("אימייל", "חיפוש, קריאה, טיוטות, שליחה, ארכוב וניהול קבצים מצורפים."),
            ("זיכרון שימושי", "שמירת העדפות ופרטי הקשר שחוזרים על עצמם כדי לעבוד מהר יותר."),
            ("שליטה במחשב", "פתיחת תוכנות, עבודה עם חלונות ופעולות UI כשמאשרים זאת בהגדרות."),
        ]
        for heading, body in feature_items:
            features.addWidget(self._feature_card(heading, body))
        content_layout.addLayout(features)

        content_layout.addWidget(self._section_title("דוגמאות יומיומיות"))
        examples = [
            "מצא מדריך אמין לתיקון קטן בבית, חלץ רשימת ציוד וצור קובץ קניות.",
            "בדוק פעם ביום תחזית, עומסי תנועה או מחיר מוצר, וסכם רק כשיש שינוי חשוב.",
            "קרא מסמך ארוך, מצא סעיפים לביצוע והכן טיוטת מייל המשך.",
            "סרוק תיקייה של קבלות או מסמכים, ארגן שמות קבצים והכן תקציר.",
            "פתח אתר עבודה קבוע, אסוף נתונים שחוזרים על עצמם והדבק אותם לקובץ מעקב.",
        ]
        for example in examples:
            content_layout.addWidget(self._example_row(example))

        note = QFrame()
        note.setStyleSheet(card_css(12, 8))
        note_layout = QVBoxLayout(note)
        note_layout.setSpacing(6)
        note_title = QLabel("פרטיות ובטיחות")
        note_title.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 15px; font-weight: 800; border: none;")
        note_body = QLabel("פעולות רגישות נשלטות דרך פרופיל האוטונומיה ומדיניות הכלים. מחיקת קבצים עוברת לסל המחזור, וסודות נשמרים במנגנוני האחסון המאובטחים של Windows כשהם זמינים.")
        note_body.setWordWrap(True)
        note_body.setStyleSheet(muted_label_css(13) + " border: none;")
        note_layout.addWidget(note_title)
        note_layout.addWidget(note_body)
        content_layout.addWidget(note)

        footer = QLabel("פותח ע\"י א.מ.ד. | 2026 | em0548438097@gmail.com")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setWordWrap(True)
        footer.setStyleSheet(muted_label_css(12))
        content_layout.addWidget(footer)
        content_layout.addStretch()

    def _section_title(self, text):
        label = QLabel(text)
        label.setStyleSheet(section_title_css(16))
        return label

    def _feature_card(self, heading, body):
        card = QFrame()
        card.setStyleSheet(card_css(12, 8))
        card.setMinimumHeight(108)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)
        title = QLabel(heading)
        title.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 800; border: none;")
        title.setWordWrap(True)
        desc = QLabel(body)
        desc.setStyleSheet(muted_label_css(12) + " border: none;")
        desc.setWordWrap(True)
        card_layout.addWidget(title)
        card_layout.addWidget(desc)
        card_layout.addStretch()
        return card

    def _example_row(self, text):
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {GLASS_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 16px; }}"
            "QLabel { border: none; background: transparent; }"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(14, 10, 14, 10)
        marker = QLabel("✓")
        marker.setStyleSheet(f"color: {ACCENT_SECONDARY_COLOR}; font-size: 15px; font-weight: 900;")
        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px;")
        row_layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignTop)
        row_layout.addWidget(body, 1)
        return row


__all__ = [name for name in globals() if not name.startswith("__")]
