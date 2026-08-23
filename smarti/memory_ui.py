"""Simple, privacy-aware RTL controls for Smarti's local memory."""

from .ui_common import *
from .ui_styles import *
from .ui_controls import *


MEMORY_TYPE_LABELS = {
    "any": "כל סוגי הזיכרון",
    "user": "פרטים והעדפות שלי",
    "long_term": "זיכרון לטווח ארוך",
    "short_term": "הקשר משיחות אחרונות",
    "tool": "תוצאות מכלים",
}
MEMORY_STATUS_LABELS = {
    "active": "זיכרונות פעילים",
    "archive": "ארכיון",
    "all": "כל הזיכרונות",
}
MEMORY_STATUS_BADGES = {
    "active": "פעיל",
    "archive": "ארכיון",
    "session": "לשיחה זו",
}
MEMORY_TYPE_SHORT_LABELS = {
    "user": "פרטים והעדפות",
    "long_term": "טווח ארוך",
    "short_term": "שיחות אחרונות",
    "tool": "תוצאות כלים",
}
MEMORY_CATEGORY_LABELS = {
    "": "כל הקטגוריות",
    "general": "כללי",
    "identity": "זהות",
    "preference": "העדפה",
    "project": "פרויקט",
    "address": "כתובת",
    "phone": "טלפון",
    "email": "דוא״ל",
    "health": "בריאות",
    "work": "עבודה",
    "family": "משפחה",
    "birthday": "יום הולדת",
}
SENSITIVITY_LABELS = {
    "any": "כל רמות הפרטיות",
    "ordinary": "זיכרון רגיל",
    "sensitive": "מידע רגיש ומוצפן",
}
SORT_LABELS = {
    "updated_desc": "עודכנו לאחרונה",
    "created_desc": "נוצרו לאחרונה",
    "importance_desc": "החשובים קודם",
    "updated_asc": "הישנים קודם",
}
DATE_LABELS = {
    "any": "כל התאריכים",
    "7d": "7 הימים האחרונים",
    "30d": "30 הימים האחרונים",
    "90d": "90 הימים האחרונים",
}
EXPIRY_LABELS = {
    "any": "כל מועדי התפוגה",
    "expiring": "יפוגו בשבוע הקרוב",
    "never": "ללא תפוגה",
    "expired": "פגי תוקף",
}


def _memory_button_css(kind="secondary"):
    if kind == "danger":
        return DANGER_BUTTON_CSS
    if kind == "primary":
        return PRIMARY_BUTTON_CSS
    return SECONDARY_BUTTON_CSS


def _style_memory_button(button, kind="secondary", height=44, radius=20):
    """Give adjacent memory-page actions one predictable geometry."""
    button.setFixedHeight(height)
    button.setStyleSheet(
        _memory_button_css(kind)
        + f"QPushButton {{ min-height: {height}px; max-height: {height}px; "
          f"border-radius: {radius}px; padding: 0 16px; }} "
          f"QPushButton:pressed {{ padding: 0 16px; }}"
    )
    return button


def _style_memory_icon_button(button, icon_names, tooltip, fallback, size=40):
    button.setFixedSize(size, size)
    button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    button.setToolTip(tooltip)
    set_themed_button_icon(button, tuple(icon_names), fallback, 21, clear_text=True)
    button.setStyleSheet(icon_button_css(size))
    return button


def _memory_entry_card_css():
    return f"""
        QFrame#MemoryEntryCard {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {GLASS_STRONG_COLOR}, stop:1 {CARD_GRADIENT_END});
            border: 1px solid {SOFT_LINE_COLOR}; border-radius: 18px;
        }}
        QFrame#MemoryEntryCard QLabel, QFrame#MemoryEntryCard QCheckBox {{
            background: transparent; border: none; padding: 0;
        }}
    """


def _make_combo(values, current=None):
    combo = NoScrollComboBox()
    combo.setMinimumHeight(40)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    for value, label in values.items():
        combo.addItem(label, value)
    if current is not None:
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
    return combo


def _field_title(text, help_text=""):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; font-weight: 700; background: transparent;")
    if help_text:
        label.setToolTip(help_text)
        label.setAccessibleDescription(help_text)
    return label


def _add_help(layout, text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(muted_label_css(11))
    layout.addWidget(label)
    return label


class MemoryEditDialog(QDialog):
    """A short editor with uncommon controls hidden under an optional section."""

    TTL_PRESETS = {
        "none": ("ללא תפוגה", None),
        "day": ("יום אחד", 24.0),
        "week": ("שבוע", 168.0),
        "month": ("30 יום", 720.0),
        "custom": ("תקופה אחרת…", "custom"),
    }

    def __init__(self, entry=None, parent=None, title="עריכת זיכרון"):
        super().__init__(parent)
        self.entry = dict(entry or {})
        self.setWindowTitle(title)
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(430, 540)
        self.setMinimumSize(350, 450)
        self.setStyleSheet(f"QDialog {{ background: {BG_COLOR}; color: {TEXT_COLOR}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(9)

        heading = QLabel(title)
        heading.setStyleSheet(page_title_css(19))
        root.addWidget(heading)

        root.addWidget(_field_title("מה סמארטי צריך לזכור?"))
        _add_help(root, "אפשר להזין עובדה או העדפה קצרה ושימושית. סודות, סיסמאות וקודי אימות אינם נשמרים.")
        self.content = QTextEdit()
        self.content.setPlainText(str(self.entry.get("content") or ""))
        self.content.setMinimumHeight(130)
        self.content.setMaximumHeight(170)
        self.content.setAcceptRichText(False)
        self.content.setStyleSheet(TEXT_EDIT_CSS + SCROLLBAR_CSS)
        self.content.setToolTip("זהו תוכן הזיכרון שסמארטי יוכל למצוא ולהשתמש בו בעת הצורך.")
        root.addWidget(self.content)

        root.addWidget(_field_title(
            "קטגוריה",
            "הקטגוריה עוזרת לסינון וקובעת כללי פרטיות למידע כגון כתובת, טלפון ובריאות.",
        ))
        self.category = _make_combo({k: v for k, v in MEMORY_CATEGORY_LABELS.items() if k}, self.entry.get("category", "general"))
        self.category.setToolTip("בחירת הנושא שמתאר את הזיכרון בצורה הטובה ביותר.")
        root.addWidget(self.category)

        self.advanced_toggle = QPushButton("אפשרויות נוספות")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setStyleSheet(_memory_button_css())
        root.addWidget(self.advanced_toggle)

        self.advanced_frame = QFrame()
        advanced = QVBoxLayout(self.advanced_frame)
        advanced.setContentsMargins(0, 6, 0, 0)
        advanced.setSpacing(7)

        advanced.addWidget(_field_title("כותרת קצרה", "שם קצר שמקל לזהות את הזיכרון ברשימה. אפשר להשאיר ריק."))
        self.subject = QLineEdit(str(self.entry.get("subject") or ""))
        self.subject.setPlaceholderText("לא חובה")
        self.subject.setMinimumHeight(40)
        self.subject.setStyleSheet(LINE_EDIT_CSS)
        advanced.addWidget(self.subject)

        row = QGridLayout()
        row.setSpacing(8)
        row.addWidget(_field_title("סוג זיכרון", "קובע אם זה פרט קבוע, הקשר זמני או תוצאת כלי."), 0, 0)
        row.addWidget(_field_title("חשיבות", "משמשת רק לדירוג; 5 היא החשיבות הגבוהה ביותר."), 0, 1)
        self.memory_type = _make_combo({k: v for k, v in MEMORY_TYPE_LABELS.items() if k != "any"}, self.entry.get("type", "long_term"))
        importance_values = {value: f"{value} מתוך 5" for value in range(1, 6)}
        self.importance = _make_combo(importance_values, int(self.entry.get("importance", 3) or 3))
        row.addWidget(self.memory_type, 1, 0)
        row.addWidget(self.importance, 1, 1)
        advanced.addLayout(row)

        advanced.addWidget(_field_title("לכמה זמן לשמור?", "בסיום התקופה הזיכרון מוסר אוטומטית."))
        self.ttl = _make_combo({key: label for key, (label, _value) in self.TTL_PRESETS.items()})
        self.custom_ttl = QLineEdit()
        self.custom_ttl.setPlaceholderText("מספר שעות חיובי")
        self.custom_ttl.setMinimumHeight(40)
        self.custom_ttl.setStyleSheet(LINE_EDIT_CSS)
        self.custom_ttl.hide()
        self.ttl.currentIndexChanged.connect(self._ttl_changed)
        advanced.addWidget(self.ttl)
        advanced.addWidget(self.custom_ttl)
        self._set_existing_ttl()

        advanced.addWidget(_field_title("תגיות", "מילים קצרות שמקלות על חיפוש. יש להפריד בפסיקים."))
        self.tags = QLineEdit(", ".join(self.entry.get("tags") or []))
        self.tags.setPlaceholderText("למשל: פרויקט, כתיבה")
        self.tags.setMinimumHeight(40)
        self.tags.setStyleSheet(LINE_EDIT_CSS)
        advanced.addWidget(self.tags)

        self.pinned = SmartiCheckBox("הצג את הזיכרון בראש הרשימה")
        self.pinned.setChecked(bool(self.entry.get("pinned", False)))
        self.pinned.setToolTip("נעיצה משפיעה על סדר התצוגה בלבד.")
        advanced.addWidget(self.pinned)

        advanced_scroll = QScrollArea()
        advanced_scroll.setWidgetResizable(True)
        advanced_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        advanced_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        advanced_scroll.setWidget(self.advanced_frame)
        advanced_scroll.setMinimumHeight(235)
        advanced_scroll.hide()
        self.advanced_scroll = advanced_scroll
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        root.addWidget(advanced_scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("שמור")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        _style_memory_button(buttons.button(QDialogButtonBox.StandardButton.Save), "primary")
        _style_memory_button(buttons.button(QDialogButtonBox.StandardButton.Cancel))
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _toggle_advanced(self, expanded):
        self.advanced_scroll.setVisible(bool(expanded))
        self.advanced_toggle.setText("סגור אפשרויות נוספות" if expanded else "אפשרויות נוספות")
        self.resize(self.width(), 690 if expanded else 540)

    def _set_existing_ttl(self):
        expires_at = self.entry.get("expires_at")
        if not expires_at:
            self.ttl.setCurrentIndex(self.ttl.findData("none"))
            return
        try:
            hours = max(1.0, (datetime.fromisoformat(str(expires_at)) - datetime.now()).total_seconds() / 3600.0)
        except Exception:
            hours = None
        matched = None
        if hours is not None:
            for key, (_label, value) in self.TTL_PRESETS.items():
                if isinstance(value, float) and abs(value - hours) <= 1.0:
                    matched = key
                    break
        key = matched or "custom"
        self.ttl.setCurrentIndex(self.ttl.findData(key))
        if key == "custom" and hours is not None:
            self.custom_ttl.setText(str(max(1, int(round(hours)))))
        self._ttl_changed()

    def _ttl_changed(self, _index=None):
        self.custom_ttl.setVisible(self.ttl.currentData() == "custom")

    def _validate_and_accept(self):
        if not self.content.toPlainText().strip():
            QMessageBox.warning(self, "שמירת זיכרון", "יש לכתוב מה סמארטי צריך לזכור.")
            return
        if self.ttl.currentData() == "custom":
            try:
                if float(self.custom_ttl.text().strip()) <= 0:
                    raise ValueError()
            except Exception:
                QMessageBox.warning(self, "שמירת זיכרון", "יש להזין מספר שעות חיובי, או לבחור תקופה מוכנה.")
                return
        self.accept()

    def values(self):
        ttl_key = self.ttl.currentData()
        ttl_value = self.TTL_PRESETS.get(ttl_key, ("", None))[1]
        if ttl_key == "custom":
            ttl_value = float(self.custom_ttl.text().strip())
        return {
            "subject": self.subject.text().strip(),
            "content": self.content.toPlainText().strip(),
            "memory_type": self.memory_type.currentData(),
            "category": self.category.currentData(),
            "importance": self.importance.currentData(),
            "ttl_hours": ttl_value,
            "tags": [value.strip() for value in self.tags.text().split(",") if value.strip()],
            "pinned": self.pinned.isChecked(),
        }


class MemoryFilterDialog(QDialog):
    def __init__(self, filters, parent=None):
        super().__init__(parent)
        self.setWindowTitle("סינון ומיון זיכרונות")
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(410, 500)
        self.setMinimumWidth(350)
        self.setStyleSheet(f"QDialog {{ background: {BG_COLOR}; color: {TEXT_COLOR}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(8)
        title = QLabel("סינון ומיון")
        title.setStyleSheet(page_title_css(19))
        root.addWidget(title)
        _add_help(root, "המסננים מצמצמים את הרשימה בלבד ואינם משנים או מוחקים זיכרונות.")

        self.category_filter = self._add_combo(root, "קטגוריה", MEMORY_CATEGORY_LABELS, filters.get("category", ""))
        self.sensitivity_filter = self._add_combo(root, "פרטיות", SENSITIVITY_LABELS, filters.get("sensitivity", "any"))
        self.date_filter = self._add_combo(root, "מועד עדכון", DATE_LABELS, filters.get("date_range", "any"))
        self.expiry_filter = self._add_combo(root, "תפוגה", EXPIRY_LABELS, filters.get("expiry", "any"))
        self.sort_filter = self._add_combo(root, "סדר הרשימה", SORT_LABELS, filters.get("sort_by", "updated_desc"))

        buttons = QHBoxLayout()
        apply_btn = QPushButton("החל")
        reset_btn = QPushButton("נקה סינון")
        cancel_btn = QPushButton("ביטול")
        _style_memory_button(apply_btn, "primary")
        _style_memory_button(reset_btn)
        _style_memory_button(cancel_btn)
        apply_btn.clicked.connect(self.accept)
        reset_btn.clicked.connect(self._reset)
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(apply_btn)
        buttons.addWidget(reset_btn)
        buttons.addWidget(cancel_btn)
        root.addLayout(buttons)

    def _add_combo(self, layout, title, values, current):
        layout.addWidget(_field_title(title))
        combo = _make_combo(values, current)
        layout.addWidget(combo)
        return combo

    def _reset(self):
        for combo, value in (
            (self.category_filter, ""),
            (self.sensitivity_filter, "any"),
            (self.date_filter, "any"),
            (self.expiry_filter, "any"),
            (self.sort_filter, "updated_desc"),
        ):
            combo.setCurrentIndex(max(0, combo.findData(value)))

    def values(self):
        return {
            "category": self.category_filter.currentData(),
            "sensitivity": self.sensitivity_filter.currentData(),
            "date_range": self.date_filter.currentData(),
            "expiry": self.expiry_filter.currentData(),
            "sort_by": self.sort_filter.currentData(),
        }


class MemoryDetailsDialog(QDialog):
    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("פרטי הזיכרון")
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(430, 520)
        self.setMinimumSize(350, 420)
        self.setStyleSheet(f"QDialog {{ background: {BG_COLOR}; color: {TEXT_COLOR}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(9)
        title = QLabel("פרטי הזיכרון")
        title.setStyleSheet(page_title_css(19))
        root.addWidget(title)
        _add_help(root, "הפרטים מסבירים מתי ולמה הזיכרון נוצר. שינוי התוכן נעשה דרך עריכה.")

        category = MEMORY_CATEGORY_LABELS.get(entry.get("category"), entry.get("category") or "כללי")
        memory_type = MEMORY_TYPE_LABELS.get(entry.get("type"), entry.get("type") or "לא ידוע")
        status = MEMORY_STATUS_LABELS.get(entry.get("status"), entry.get("status") or "לא ידוע")
        metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
        evidence = metadata.get("evidence") if isinstance(metadata.get("evidence"), list) else []
        rows = (
            ("מצב", status),
            ("סוג", memory_type),
            ("קטגוריה", category),
            ("תחום", entry.get("scope") or "כללי"),
            ("פרטיות", "מידע רגיש ומוצפן" if entry.get("sensitivity") == "sensitive" else "זיכרון רגיל"),
            ("למה נשמר", metadata.get("why_saved") or entry.get("source") or "לא תועד"),
            ("מקור", entry.get("source") or "לא תועד"),
            ("נוצר", entry.get("created_at") or "לא תועד"),
            ("עודכן", entry.get("updated_at") or "לא תועד"),
            ("שימוש אחרון", entry.get("last_used_at") or "טרם"),
            ("צורף לאחרונה לבקשה", entry.get("last_injected_at") or "טרם"),
            ("נבחר / צורף", f"{entry.get('selected_count', 0)} / {entry.get('injection_count', 0)}"),
            ("מצב אימות", entry.get("validation_state") or metadata.get("validation_state") or "לא אומת"),
            ("אסמכתאות", str(len(evidence))),
            ("תפוגה", entry.get("expires_at") or "ללא תפוגה"),
            ("חשיבות", f"{entry.get('importance', 3)} מתוך 5"),
            ("מזהה פנימי", entry.get("id") or "לא תועד"),
            ("שיחת מקור", entry.get("source_conversation_id") or "לא תועדה"),
            ("הודעת מקור", entry.get("source_message_id") or "לא תועדה"),
        )
        browser = QTextBrowser()
        browser.setPlainText("\n\n".join(f"{label}\n{value}" for label, value in rows))
        browser.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setStyleSheet(TEXT_EDIT_CSS + SCROLLBAR_CSS)
        root.addWidget(browser, 1)
        close = QPushButton("סגור")
        _style_memory_button(close, "primary")
        close.clicked.connect(self.accept)
        root.addWidget(close)


class MemoryManagementPage(QWidget):
    """A compact list first; rare and destructive controls stay out of the way."""

    PAGE_SIZE = 8

    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self.manager = getattr(core, "memory_manager", None)
        self.selected_ids = set()
        self.selection_mode = False
        self._last_signature = None
        self._loaded_once = False
        self._rows = []
        self._page_cursor = 0
        self._activation_scheduled = False
        self._filters = {
            "category": "",
            "sensitivity": "any",
            "date_range": "any",
            "expiry": "any",
            "sort_by": "updated_desc",
        }
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.back_btn = QPushButton()
        self.back_btn.setFixedSize(38, 38)
        self.back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        set_themed_button_icon(self.back_btn, ("back_icon",), "<", 24, clear_text=True)
        self.back_btn.setStyleSheet(icon_button_css(38))
        self.back_btn.setToolTip("חזרה לשיחה")
        self.back_btn.clicked.connect(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page))
        top.addWidget(self.back_btn)
        title = QLabel("ניהול הזיכרון")
        title.setStyleSheet(page_title_css(20))
        top.addWidget(title)
        top.addStretch()
        self.add_btn = QPushButton()
        _style_memory_icon_button(
            self.add_btn, ("plus_icon",), "הוספת זיכרון חדש", "+", 40,
        )
        self.add_btn.clicked.connect(self._add_memory)
        top.addWidget(self.add_btn)
        self.more_btn = QPushButton()
        _style_memory_icon_button(
            self.more_btn, ("menu_icon",), "פעולות נוספות", "⋮", 40,
        )
        self.more_btn.clicked.connect(self._show_page_menu)
        top.addWidget(self.more_btn)
        root.addLayout(top)

        self.stats_label = QLabel("טוען את הזיכרונות…")
        self.stats_label.setWordWrap(False)
        self.stats_label.setMinimumWidth(1)
        self.stats_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.stats_label.setStyleSheet(muted_label_css(12))
        self.stats_label.setToolTip("מספר הזיכרונות בכל מצב. כל המידע נשמר מקומית.")
        root.addWidget(self.stats_label)

        self.memory_permission_card = QFrame()
        self.memory_permission_card.setObjectName("MemoryPermissionCard")
        self.memory_permission_card.setStyleSheet(card_css(10, 12))
        permission_layout = QVBoxLayout(self.memory_permission_card)
        permission_layout.setContentsMargins(12, 8, 12, 9)
        permission_layout.setSpacing(2)
        self.memory_enabled_checkbox = SmartiCheckBox("שימוש בזיכרון מתמשך")
        self.memory_enabled_checkbox.setChecked(
            bool(self.core.settings.get("memory", {}).get("enabled", True))
        )
        self.memory_enabled_checkbox.setStyleSheet(CHECKBOX_CSS)
        self.memory_enabled_checkbox.setToolTip(
            "הפעלה או השבתה של שליפה וניהול אוטומטי של זיכרונות לפי שיקול דעת המודל"
        )
        permission_layout.addWidget(self.memory_enabled_checkbox)
        self.memory_enabled_description = QLabel(
            "כשהאפשרות פעילה, סמארטי יכול לשמור, לעדכן, למחוק ולשלוף מידע שימושי לפי "
            "שיקול דעת המודל. כיבוי האפשרות מפסיק את השימוש בזיכרון ועדכונים חדשים, אך "
            "אינו מוחק זיכרונות קיימים. למחיקה ניתן להשתמש ברשימה במסך זה או באפשרות "
            "״מחיקת כל הזיכרונות״ שבתפריט הפעולות."
        )
        self.memory_enabled_description.setWordWrap(True)
        self.memory_enabled_description.setStyleSheet(muted_label_css(11))
        self.memory_enabled_description.setToolTip(self.memory_enabled_description.text())
        permission_layout.addWidget(self.memory_enabled_description)
        self.memory_enabled_checkbox.toggled.connect(self._set_memory_enabled)
        root.addWidget(self.memory_permission_card)

        self.search = QLineEdit()
        self.search.setPlaceholderText("חיפוש בזיכרונות")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(42)
        self.search.setStyleSheet(LINE_EDIT_CSS)
        self.search.setToolTip("חיפוש בתוכן, בכותרת, בקטגוריה ובתגיות")
        root.addWidget(self.search)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.status_filter = _make_combo(MEMORY_STATUS_LABELS, "active")
        self.status_filter.setToolTip("בחירת הזיכרונות שיוצגו לפי מצבם")
        filter_row.addWidget(self.status_filter, 1)
        self.filter_btn = QPushButton("סינון ומיון")
        self.filter_btn.setStyleSheet(_memory_button_css())
        self.filter_btn.setToolTip("סינון לפי קטגוריה, פרטיות, מועד עדכון או תפוגה")
        self.filter_btn.clicked.connect(self._open_filters)
        filter_row.addWidget(self.filter_btn)
        root.addLayout(filter_row)

        self.selection_bar = QFrame()
        self.selection_bar.setStyleSheet(card_css(8, 8))
        selection_layout = QHBoxLayout(self.selection_bar)
        selection_layout.setContentsMargins(10, 6, 10, 6)
        self.selection_label = QLabel("מצב בחירה")
        self.selection_label.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 700; background: transparent; border: none;")
        selection_layout.addWidget(self.selection_label, 1)
        selection_actions = QPushButton()
        _style_memory_icon_button(
            selection_actions, ("menu_icon",), "פעולה בזיכרונות שנבחרו", "⋮", 38,
        )
        selection_actions.clicked.connect(self._show_selection_menu)
        selection_layout.addWidget(selection_actions)
        cancel_selection = QPushButton("סיום")
        _style_memory_button(cancel_selection, height=38, radius=18)
        cancel_selection.clicked.connect(self._leave_selection_mode)
        selection_layout.addWidget(cancel_selection)
        self.selection_bar.hide()
        root.addWidget(self.selection_bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.content = QWidget()
        self.content.setMinimumWidth(1)
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.content_layout.setSpacing(8)
        self.scroll.setWidget(self.content)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_load_more)
        root.addWidget(self.scroll, 1)

        self.search_reload_timer = QTimer(self)
        self.search_reload_timer.setSingleShot(True)
        self.search_reload_timer.setInterval(220)
        self.search_reload_timer.timeout.connect(lambda: self.load_data(force=True))
        self.search.textChanged.connect(lambda _text: self.search_reload_timer.start())
        self.status_filter.currentIndexChanged.connect(lambda _index: self.load_data(force=True))

        refresh_seconds = int(self.core.settings.get("memory", {}).get("memory_management_refresh_seconds", 3) or 3)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(max(2, refresh_seconds) * 1000)
        self.refresh_timer.timeout.connect(self._refresh_if_changed)
        self.refresh_timer.start()

    def activate(self, force=False):
        """Let the stack transition begin before list construction starts."""
        enabled = bool(self.core.settings.get("memory", {}).get("enabled", True))
        if self.memory_enabled_checkbox.isChecked() != enabled:
            self.memory_enabled_checkbox.blockSignals(True)
            self.memory_enabled_checkbox.setChecked(enabled)
            self.memory_enabled_checkbox.blockSignals(False)
        if self._loaded_once and not force and self._signature() == self._last_signature:
            return
        if self._activation_scheduled:
            return
        self._activation_scheduled = True
        QTimer.singleShot(360, lambda: self._finish_activation(force))

    def _finish_activation(self, force):
        self._activation_scheduled = False
        if self.isVisible():
            self.load_data(force=force)

    def showEvent(self, event):
        super().showEvent(event)
        self.activate(force=False)

    def _signature(self):
        if not self.manager:
            return ()
        stats = self.manager.memory_stats()
        try:
            modified = os.stat(self.manager.path).st_mtime_ns if os.path.exists(self.manager.path) else 0
        except Exception:
            modified = 0
        return tuple(stats.get(key, 0) for key in ("active", "archive", "session", "storage_bytes")) + (modified,)

    def _refresh_if_changed(self):
        if self.isVisible() and self.manager and self._signature() != self._last_signature:
            self.load_data(force=True)

    def _set_memory_enabled(self, enabled):
        memory_settings = self.core.settings.setdefault("memory", {})
        enabled = bool(enabled)
        if bool(memory_settings.get("enabled", True)) == enabled:
            return
        memory_settings["enabled"] = enabled
        try:
            self.core._save_settings()
        except Exception as exc:
            logging.warning("Failed saving memory permission setting: %s", exc)

    def _clear_cards(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()

    def load_data(self, force=True):
        if not self.manager:
            self._clear_cards()
            message = QLabel("מנהל הזיכרון אינו זמין.")
            message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(message)
            return
        signature = self._signature()
        if self._loaded_once and not force and signature == self._last_signature:
            return
        stats = self.manager.memory_stats()
        self._last_signature = signature
        self._loaded_once = True
        self.stats_label.setText(
            f"{stats.get('active', 0)} פעילים  ·  {stats.get('archive', 0)} בארכיון"
        )
        self._rows = self.manager.list_entries(
            query=self.search.text(),
            status=self.status_filter.currentData(),
            category=self._filters["category"],
            sensitivity=self._filters["sensitivity"],
            date_range=self._filters["date_range"],
            expiry=self._filters["expiry"],
            max_results=500,
            sort_by=self._filters["sort_by"],
            # This is the user's local management page. Persisted payloads
            # remain DPAPI-encrypted and programmatic/model-facing reads stay
            # masked by default, but the owner should not have to reveal their
            # own data one card at a time. Generic programmatic reads remain
            # masked; model context still passes through relevance and
            # sensitive-category routing before any provider request.
            reveal_sensitive=True,
            user_authorized=True,
        )
        visible_ids = {str(row.get("id")) for row in self._rows}
        self.selected_ids.intersection_update(visible_ids)
        self._update_selection_bar()
        self.setUpdatesEnabled(False)
        self._clear_cards()
        self._page_cursor = 0
        self.scroll.verticalScrollBar().setValue(0)
        if not self._rows:
            empty = QLabel("לא נמצאו זיכרונות מתאימים.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(muted_label_css(14) + " margin-top: 24px;")
            self.content_layout.addWidget(empty)
            self.setUpdatesEnabled(True)
            return
        self._append_page()
        self.setUpdatesEnabled(True)
        self.update()

    def _append_page(self):
        if self._page_cursor >= len(self._rows):
            return
        end = min(len(self._rows), self._page_cursor + self.PAGE_SIZE)
        viewport = self.scroll.viewport()
        viewport.setUpdatesEnabled(False)
        for row in self._rows[self._page_cursor:end]:
            self.content_layout.addWidget(self._entry_card(row))
        self._page_cursor = end
        self.content.adjustSize()
        viewport.setUpdatesEnabled(True)
        viewport.update()

    def _maybe_load_more(self, value):
        bar = self.scroll.verticalScrollBar()
        if self._page_cursor < len(self._rows) and value >= max(0, bar.maximum() - 180):
            self._append_page()

    def _active_filter_count(self):
        defaults = {
            "category": "", "sensitivity": "any",
            "date_range": "any", "expiry": "any", "sort_by": "updated_desc",
        }
        return sum(self._filters.get(key) != value for key, value in defaults.items())

    def _open_filters(self):
        dialog = MemoryFilterDialog(self._filters, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._filters = dialog.values()
        count = self._active_filter_count()
        self.filter_btn.setText(f"סינון ומיון ({count})" if count else "סינון ומיון")
        self.load_data(force=True)

    def _show_page_menu(self):
        menu = prepare_popup_menu(QMenu(self))
        select_many = menu.addAction("בחירת כמה זיכרונות")
        menu.addSeparator()
        export = menu.addAction("ייצוא מוצפן")
        import_action = menu.addAction("ייבוא")
        menu.addSeparator()
        clear = menu.addAction("מחיקת כל הזיכרונות")
        chosen = menu.exec(self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height() + 4)))
        if chosen is select_many:
            self._enter_selection_mode()
        elif chosen is export:
            self._export()
        elif chosen is import_action:
            self._import()
        elif chosen is clear:
            self._clear_all()

    @staticmethod
    def _display_subject(entry):
        subject = str(entry.get("subject") or "").strip()
        if subject.lower() == "user work":
            return "בקשה קודמת שנשמרה אוטומטית"
        return subject or "זיכרון ללא כותרת"

    @staticmethod
    def _display_content(entry, content=None):
        text = str(entry.get("content") if content is None else content or "").strip()
        source = str(entry.get("source") or "").lower()
        subject = str(entry.get("subject") or "").lower()
        if subject == "user work" or source in {"critical_backfill", "critical_preflight"}:
            cleaned = re.sub(r"(?:(?:user\s+work)\s*:?\s*)+", "", text, flags=re.IGNORECASE).strip()
            if cleaned:
                text = cleaned
        text = re.sub(r"\s+", " ", text)
        replacements = (
            (r"^User request:\s*", "בקשת המשתמש: "),
            (r"^Explicit memory request:\s*", "בקשה מפורשת לזכור: "),
            (r"^Recent temporal context:\s*", "הקשר זמני אחרון: "),
            (r"^Recent exchange:\s*", "שיחה אחרונה: "),
            (r"^Outcome:\s*", "תוצאה: "),
        )
        for pattern, replacement in replacements:
            text, count = re.subn(pattern, replacement, text, count=1, flags=re.IGNORECASE)
            if count:
                break
        first = re.search(r"[A-Za-z\u0590-\u05FF]", text)
        if text and (not first or not re.match(r"[\u0590-\u05FF]", first.group(0))):
            text = f"תוכן הזיכרון: {text}"
        return text if len(text) <= 280 else text[:277].rstrip() + "…"

    @staticmethod
    def _format_updated(value):
        try:
            parsed = datetime.fromisoformat(str(value or ""))
        except Exception:
            return "מועד לא ידוע"
        if parsed.date() == datetime.now().date():
            return f"עודכן היום {parsed.strftime('%H:%M')}"
        return f"עודכן {parsed.strftime('%d.%m.%Y')}"

    def _entry_card(self, entry):
        card = QFrame()
        card.setObjectName("MemoryEntryCard")
        card.setMinimumWidth(1)
        card.setMinimumHeight(104)
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        card.setStyleSheet(_memory_entry_card_css())
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 7, 11, 7)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.setAlignment(Qt.AlignmentFlag.AlignTop)
        if self.selection_mode:
            checkbox = QCheckBox()
            checkbox.setChecked(str(entry.get("id")) in self.selected_ids)
            checkbox.setToolTip("בחירת הזיכרון לפעולה מרובה")
            checkbox.stateChanged.connect(lambda state, mid=str(entry.get("id")): self._selection_changed(mid, bool(state)))
            header.addWidget(checkbox)
        full_subject = ("★ " if entry.get("pinned") else "") + self._display_subject(entry)
        subject = QLabel(full_subject)
        subject.setMinimumWidth(1)
        subject.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        subject.setWordWrap(True)
        subject.setToolTip(full_subject)
        subject.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 800; border: none;")
        header.addWidget(subject, 1)
        badge_text = MEMORY_STATUS_BADGES.get(entry.get("status"), entry.get("status", ""))
        badge = QLabel(badge_text)
        badge.setFixedSize(60, 24)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {ACCENT_TINT_STRONG}; color: {ACCENT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 9px; padding: 0; font-size: 10px; font-weight: 800;"
        )
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        more = QPushButton()
        _style_memory_icon_button(
            more, ("menu_icon",), "פעולות בזיכרון", "⋮", 30,
        )
        more.setToolTip("הצגת פרטים, נעיצה, ארכוב או מחיקה")
        more.clicked.connect(lambda _checked=False, e=entry, b=more: self._show_entry_menu(e, b))
        header.addWidget(more, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        preview = QLabel(self._display_content(entry))
        preview.setObjectName(f"MemoryPreview_{entry.get('id')}")
        preview.setMinimumWidth(1)
        preview.setMaximumHeight(52)
        preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        preview.setWordWrap(True)
        preview.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        preview.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTop
            | Qt.AlignmentFlag.AlignAbsolute
        )
        preview.setTextFormat(Qt.TextFormat.PlainText)
        preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; border: none;")
        layout.addWidget(preview)

        category = MEMORY_CATEGORY_LABELS.get(entry.get("category"), entry.get("category") or "כללי")
        meta = QLabel(
            f"{category}  ·  {MEMORY_TYPE_SHORT_LABELS.get(entry.get('type'), entry.get('type'))}  ·  "
            f"{self._format_updated(entry.get('updated_at'))}"
        )
        meta.setMinimumWidth(1)
        meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        meta.setStyleSheet(muted_label_css(10))
        meta.setToolTip("קטגוריה · סוג זיכרון · מועד עדכון אחרון")
        layout.addWidget(meta)

        return card

    def _show_entry_menu(self, entry, button):
        menu = prepare_popup_menu(QMenu(self))
        edit = menu.addAction("עריכת הזיכרון")
        details = menu.addAction("פרטים: למה ומתי נשמר")
        pin = None
        if entry.get("status") != "session":
            pin = menu.addAction("בטל נעיצה" if entry.get("pinned") else "נעץ בראש הרשימה")
        menu.addSeparator()
        state_action = None
        if entry.get("status") == "archive":
            state_action = menu.addAction("שחזור מהארכיון")
        elif entry.get("status") != "session":
            state_action = menu.addAction("העברה לארכיון")
        forget = menu.addAction("מחיקה לצמיתות")
        chosen = menu.exec(button.mapToGlobal(QPoint(0, button.height() + 2)))
        if edit is not None and chosen is edit:
            self._edit_memory(entry)
        elif chosen is details:
            MemoryDetailsDialog(entry, self).exec()
        elif pin is not None and chosen is pin:
            self._toggle_pin(entry)
        elif state_action is not None and chosen is state_action:
            if entry.get("status") == "archive":
                self._restore_one(entry.get("id"))
            else:
                self._archive_one(entry.get("id"))
        elif chosen is forget:
            self._forget_one(entry.get("id"))

    def _toggle_pin(self, entry):
        current = self.manager.get_entry(entry.get("id"), reveal_sensitive=True, user_authorized=True)
        if not current:
            return
        try:
            self.manager.edit_entry(
                entry.get("id"), expected_version=current.get("version"),
                user_authorized=True, pinned=not bool(current.get("pinned")),
            )
            self.load_data(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "נעיצת זיכרון", str(exc))

    def _add_memory(self):
        dialog = MemoryEditDialog(parent=self, title="זיכרון חדש")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            classification = self.manager.classify_content(values["content"], values["category"])
            if not classification.get("store_allowed", True):
                raise ValueError(classification.get("reason"))
            self.manager.add(
                values.pop("memory_type"), values.pop("content"), source="manual_ui",
                consent_state="approved", storage_mode="persistent", cloud_allowed=True,
                metadata={"why_saved": "נשמר ידנית בדף ניהול הזיכרון."}, **values,
            )
            self.load_data(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "שמירת זיכרון", str(exc))

    def _edit_memory(self, entry):
        current = self.manager.get_entry(entry.get("id"), reveal_sensitive=True, user_authorized=True)
        if not current:
            return
        dialog = MemoryEditDialog(current, self, "עריכת זיכרון")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.manager.edit_entry(
                entry.get("id"), expected_version=current.get("version"),
                user_authorized=True, **dialog.values(),
            )
            self.load_data(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "עריכת זיכרון", str(exc))

    def _archive_one(self, memory_id):
        self.manager.archive_entry(memory_id)
        self.load_data(force=True)

    def _restore_one(self, memory_id):
        self.manager.restore_entry(memory_id)
        self.load_data(force=True)

    def _forget_one(self, memory_id):
        if QMessageBox.warning(
            self, "מחיקת זיכרון", "הזיכרון יימחק לצמיתות. להמשיך?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self.manager.forget(memory_id)
        self.load_data(force=True)

    def _enter_selection_mode(self):
        self.selection_mode = True
        self.selection_bar.show()
        self.load_data(force=True)

    def _leave_selection_mode(self):
        self.selection_mode = False
        self.selected_ids.clear()
        self.selection_bar.hide()
        self.load_data(force=True)

    def _selection_changed(self, memory_id, selected):
        if selected:
            self.selected_ids.add(memory_id)
        else:
            self.selected_ids.discard(memory_id)
        self._update_selection_bar()

    def _update_selection_bar(self):
        if hasattr(self, "selection_label"):
            self.selection_label.setText(f"נבחרו {len(self.selected_ids)} זיכרונות")

    def _show_selection_menu(self):
        if not self.selected_ids:
            QMessageBox.information(self, "בחירת זיכרונות", "יש לבחור לפחות זיכרון אחד מהרשימה.")
            return
        menu = prepare_popup_menu(QMenu(self))
        archive = menu.addAction("העברה לארכיון")
        restore = menu.addAction("שחזור מהארכיון")
        menu.addSeparator()
        forget = menu.addAction("מחיקה לצמיתות")
        chosen = menu.exec(self.selection_bar.mapToGlobal(QPoint(0, self.selection_bar.height())))
        if chosen is archive:
            self._bulk_archive()
        elif chosen is restore:
            self._bulk_restore()
        elif chosen is forget:
            self._bulk_forget()

    def _bulk_archive(self):
        for memory_id in list(self.selected_ids):
            self.manager.archive_entry(memory_id)
        self._leave_selection_mode()

    def _bulk_restore(self):
        for memory_id in list(self.selected_ids):
            self.manager.restore_entry(memory_id)
        self._leave_selection_mode()

    def _bulk_forget(self):
        if QMessageBox.warning(
            self, "מחיקת זיכרונות", f"למחוק לצמיתות {len(self.selected_ids)} זיכרונות?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        for memory_id in list(self.selected_ids):
            self.manager.forget(memory_id)
        self._leave_selection_mode()

    def _clear_all(self):
        text, ok = QInputDialog.getText(
            self, "מחיקת כל הזיכרונות",
            "הפעולה מוחקת לצמיתות את כל הזיכרונות הפעילים ואת הארכיון.\nכדי לאשר יש להקליד: מחק הכול",
        )
        if not ok or text.strip() != "מחק הכול":
            return
        removed = self.manager.clear()
        QMessageBox.information(self, "מחיקת כל הזיכרונות", f"נמחקו {removed} זיכרונות.")
        self.load_data(force=True)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "ייצוא זיכרונות מוצפן", "smarti-memory-export.json", "JSON (*.json)")
        if not path:
            return
        try:
            saved = self.manager.export_memory(path, encrypted=True, include_sensitive=True)
            QMessageBox.information(self, "ייצוא זיכרונות", f"הקובץ נשמר בהצלחה:\n{saved}")
        except Exception as exc:
            QMessageBox.warning(self, "ייצוא זיכרונות", str(exc))

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "ייבוא זיכרונות", "", "JSON (*.json)")
        if not path:
            return
        if QMessageBox.question(self, "ייבוא זיכרונות", "למזג את הקובץ עם הזיכרונות הקיימים?") != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self.manager.import_memory(path, user_authorized=True)
            QMessageBox.information(
                self, "ייבוא זיכרונות",
                f"יובאו {result.get('imported', 0)} זיכרונות; דולגו {result.get('skipped', 0)}.",
            )
            self.load_data(force=True)
        except Exception as exc:
            QMessageBox.warning(self, "ייבוא זיכרונות", str(exc))
