"""Settings, tools, usage, task-center, trace, and about pages."""
from .ui_common import *
from .config import *
from .ui_styles import *
from .ui_controls import *
from .visual_canvas import web_canvas_available
from .doctor import CheckResult, RepairAction
from .workers import (
    FetchModelsWorker,
    ApiKeyValidationWorker,
    TTSWorker,
    EmailConnectionTestWorker,
    DiagnosticCheckWorker,
    DiagnosticRepairWorker,
    SSLTrustTestWorker,
)
from PyQt6.QtCore import QRect, QStandardPaths, QUrl
from PyQt6.QtGui import QKeySequence, QShortcut, QDesktopServices


def _tail_text_file(path, max_lines=160, chunk_size=64 * 1024):
    """Read only the tail of a potentially large UTF-8 log file."""
    max_lines = max(1, int(max_lines or 1))
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            position = handle.tell()
            chunks = []
            newline_count = 0
            while position > 0 and newline_count <= max_lines:
                read_size = min(int(chunk_size), position)
                position -= read_size
                handle.seek(position)
                chunk = handle.read(read_size)
                chunks.append(chunk)
                newline_count += chunk.count(b"\n")
        text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
        return text.splitlines()[-max_lines:]
    except FileNotFoundError:
        return []


def _unified_log_lines(max_lines=500):
    """Read the unified log across rotations, newest tail only when bounded."""
    try:
        limit = int(max_lines or 0)
    except Exception:
        limit = 500
    paths = unified_log_paths()
    if not paths:
        return []
    if limit <= 0:
        rows = []
        for path in paths:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    rows.extend(handle.read().splitlines())
            except FileNotFoundError:
                pass
        return rows
    rows = []
    remaining = limit
    for path in reversed(paths):
        if remaining <= 0:
            break
        chunk = _tail_text_file(path, remaining)
        rows[0:0] = chunk
        remaining = limit - len(rows)
    return rows[-limit:]


_LOG_RECORD_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")
_PERSONAL_LOG_FIELDS = {
    "address", "args", "args_preview", "arguments", "body", "content", "details",
    "directory", "file", "files", "folder", "input", "instructions", "location",
    "memory", "message", "output", "path", "paths", "preview", "prompt", "query",
    "response", "stderr", "stdout", "text", "title", "url", "user_text", "value",
}
_TECHNICAL_LOG_FIELDS = {
    "action", "allowed", "args_hash", "attempt", "category", "changed", "code",
    "count", "duration_ms", "enabled", "error_code", "error_status", "error_type",
    "event", "files_count", "http_status", "id", "kind", "manager", "method",
    "model", "name", "operation", "outcome", "provider", "request_id", "retry",
    "risk", "skill", "stage", "status", "status_code", "success", "tool", "type",
}
_PERSONAL_KEY_VALUE_RE = re.compile(
    r"(?i)(\b(?:address|args|args_preview|arguments|body|content|details|directory|file|files|"
    r"folder|input|instructions|location|memory|message|output|path|paths|preview|prompt|"
    r"query|response|stderr|stdout|text|title|url|user_text|value)=).*?"
    r"(?=\s+\|\s+[A-Za-z_][\w.-]*=|$)"
)


def _scrub_personal_json(value, key=""):
    normalized_key = str(key or "").casefold()
    if normalized_key in _PERSONAL_LOG_FIELDS:
        return "[HIDDEN PERSONAL CONTENT]"
    if isinstance(value, dict):
        return {item_key: _scrub_personal_json(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_personal_json(item, key) for item in value]
    if isinstance(value, str) and normalized_key and normalized_key not in _TECHNICAL_LOG_FIELDS:
        return "[HIDDEN PERSONAL CONTENT]"
    return value


def sanitize_log_export_lines(lines, settings=None):
    """Remove conversational/user payloads while retaining diagnostic metadata."""
    output = []
    hiding_legacy_continuation = False
    for raw_line in lines or []:
        line = redact_sensitive_text(str(raw_line or ""), settings or {})
        starts_record = bool(_LOG_RECORD_PREFIX_RE.match(line))
        if hiding_legacy_continuation and not starts_record:
            if re.fullmatch(r"\s*=+\s*", line):
                hiding_legacy_continuation = False
            continue
        if starts_record:
            hiding_legacy_continuation = False

        if "PERSONAL |" in line:
            before, _, personal = line.partition("PERSONAL |")
            metadata = personal
            for marker in (" | content=", " | stdout=", " | stderr="):
                metadata = metadata.split(marker, 1)[0]
            output.append(f"{before}PERSONAL | {metadata.strip()} | [HIDDEN PERSONAL CONTENT]")
            continue

        if "בקשת משתמש חדשה:" in line or "תשובת מודל גולמית:" in line:
            marker = "בקשת משתמש חדשה:" if "בקשת משתמש חדשה:" in line else "תשובת מודל גולמית:"
            output.append(line.split(marker, 1)[0] + marker + " [HIDDEN PERSONAL CONTENT]")
            hiding_legacy_continuation = True
            continue

        if "TRACE |" in line:
            line = re.sub(
                r"(TRACE\s*\|\s*[^|]+\|).*",
                r"\1 [HIDDEN PERSONAL CONTENT]",
                line,
                count=1,
            )

        if "TOOL START" in line:
            line = re.sub(r"\s*\|\s*args=.*$", " | args=[HIDDEN PERSONAL CONTENT]", line)
        if "TOOL FINISH" in line:
            line = re.sub(r"\s*\|\s*preview=.*$", " | preview=[HIDDEN PERSONAL CONTENT]", line)
        if "API FAILURE" in line:
            line = re.sub(r"\s*\|\s*raw=.*$", " | raw=[HIDDEN PERSONAL CONTENT]", line)
            line = re.sub(r"message=.*?(?=\s\|\s|$)", "message=[HIDDEN PERSONAL CONTENT]", line)

        for event_marker in ("AUDIT |", "SKILL |"):
            if event_marker not in line:
                continue
            prefix, payload_text = line.split(event_marker, 1)
            try:
                payload = json.loads(payload_text.strip())
                scrubbed = json.dumps(_scrub_personal_json(payload), ensure_ascii=False, default=str)
                line = f"{prefix}{event_marker} {scrubbed}"
            except Exception:
                line = f"{prefix}{event_marker} [PERSONAL PAYLOAD HIDDEN]"
            break
        line = _PERSONAL_KEY_VALUE_RE.sub(r"\1[HIDDEN PERSONAL CONTENT]", line)
        output.append(line)
    return output


def doctor_action_button_css(primary=False):
    """A single 48px visual rhythm for diagnostic scan controls in every theme."""
    background = (
        f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_COLOR}, "
        f"stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR})"
        if primary else GLASS_STRONG_COLOR
    )
    hover = (
        f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {BRAND_ACCENT_COLOR}, "
        f"stop:0.52 {BRAND_PINK_COLOR}, stop:1 {BRAND_SECONDARY_COLOR})"
        if primary else HOVER_TINT
    )
    text_color = ACCENT_TEXT_COLOR if primary else TEXT_COLOR
    border = "rgba(255,255,255,0.18)" if primary else LINE_COLOR
    return f"""
        QPushButton {{
            min-height: 48px; max-height: 48px;
            background: {background}; color: {text_color};
            border: 1px solid {border}; border-radius: 24px;
            padding: 0 20px; font-size: 14px; font-weight: 800; outline: none;
        }}
        QPushButton:hover {{ background: {hover}; border-color: {LINE_COLOR}; }}
        QPushButton:pressed {{ background: {ACCENT_COLOR if primary else ACCENT_TINT_STRONG}; }}
        QPushButton:disabled {{ background: {PANEL_ELEVATED_COLOR}; color: {SUBTLE_TEXT_COLOR}; border-color: {SOFT_LINE_COLOR}; }}
    """


def doctor_stop_button_css():
    return f"""
        QPushButton {{
            min-height: 48px; max-height: 48px;
            background: rgba(240,90,110,0.13); color: {DANGER_COLOR};
            border: 1px solid rgba(255,95,126,0.34); border-radius: 24px;
            padding: 0 16px; font-size: 14px; font-weight: 800; outline: none;
        }}
        QPushButton:hover {{ background: rgba(255,95,126,0.21); border-color: rgba(255,95,126,0.50); }}
        QPushButton:pressed {{ background: rgba(255,95,126,0.29); }}
        QPushButton:disabled {{ background: {PANEL_ELEVATED_COLOR}; color: {SUBTLE_TEXT_COLOR}; border-color: {SOFT_LINE_COLOR}; }}
    """


class DiagnosticScanActionRow(QFrame):
    """A truly equal-width RTL action row, independent of button text hints."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DiagnosticScanActionRow")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._buttons = []
        self._spacing = 8

    def add_button(self, button):
        button.setParent(self)
        self._buttons.append(button)
        self.arrange_buttons()

    def arrange_buttons(self):
        visible = [button for button in self._buttons if not button.isHidden()]
        if not visible:
            return
        available = max(0, self.width() - self._spacing * (len(visible) - 1))
        base_width, remainder = divmod(available, len(visible))
        x = self.width()
        for index, button in enumerate(visible):
            width = base_width + (1 if index < remainder else 0)
            x -= width
            button.setGeometry(x, 1, width, 48)
            x -= self._spacing

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange_buttons()


def doctor_filter_css():
    return f"""
        QFrame#DiagnosticFilterControl {{
            min-height: 48px; max-height: 48px;
            background: {GLASS_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 24px;
        }}
        QFrame#DiagnosticFilterControl QPushButton {{
            min-height: 40px; max-height: 40px;
            background: transparent; border: none; border-radius: 20px;
            color: {MUTED_TEXT_COLOR}; margin: 0; padding: 0 14px;
            font-size: 13px; font-weight: 800; outline: none;
        }}
        QFrame#DiagnosticFilterControl QPushButton:hover {{ background: {HOVER_TINT}; color: {TEXT_COLOR}; }}
        QFrame#DiagnosticFilterControl QPushButton:checked {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {ACCENT_COLOR}, stop:0.58 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
            color: {ACCENT_TEXT_COLOR};
        }}
    """

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
    "search_tools": "חיפוש כלים ויכולות",
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
    "extension_manager": "ניהול הרחבות, MCP ומיומנויות",
    "canvas_manager": "קנבס חזותי",
    "browser_automation_manager": "אוטומציית דפדפן",
    "computer_automation_manager": "אוטומציית מחשב",
    "document_manager": "יצירה ועריכת מסמכים",
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
    "load_skill": "טעינת הוראות מיומנות",
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
    "visual": "קנבס חזותי",
    "email": "דוא\"ל",
    "automation": "אוטומציה",
    "documents": "מסמכים",
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

class SmartiDiagnosticPage(QWidget):
    """RTL health centre for diagnostics, explanations, and approved repairs."""

    STATUS_META = {
        "pass": ("תקין", "✓", ACCENT_SECONDARY_COLOR),
        "warning": ("דורש תשומת לב", "!", ACCENT_PINK_COLOR),
        "error": ("דורש טיפול", "×", DANGER_COLOR),
        "skipped": ("לא נבדק", "–", SUBTLE_TEXT_COLOR),
    }
    CATEGORY_ICONS = {
        "data": ("doctor_data_icon", "doctor_icon"),
        "providers": ("doctor_provider_icon", "doctor_icon"),
        "browser": ("doctor_browser_icon", "doctor_icon"),
        "email": ("doctor_email_icon", "doctor_icon"),
        "canvas": ("doctor_canvas_icon", "doctor_icon"),
        "voice": ("doctor_voice_icon", "doctor_icon"),
        "search": ("doctor_search_icon", "doctor_icon", "search_icon"),
        "storage": ("doctor_storage_icon", "doctor_icon", "folder_icon"),
        "automation": ("doctor_automation_icon", "doctor_icon", "agent_tool_screen_manager"),
        "tasks": ("doctor_tasks_icon", "doctor_icon", "task_center_icon"),
        "extensions": ("doctor_extensions_icon", "doctor_icon"),
        "security": ("doctor_security_icon", "doctor_icon", "policy_icon"),
        "system": ("doctor_system_icon", "doctor_icon"),
    }

    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.results = []
        self.current_filter = "all"
        self.log_path = ""
        self.doctor_worker = None
        self.repair_worker = None
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        back = create_back_button(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page))
        back.setToolTip("חזרה לצ'אט")
        top_bar.addWidget(back)

        self.page_icon = QLabel()
        self.page_icon.setFixedSize(38, 38)
        self.page_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_themed_label_icon(self.page_icon, ("doctor_icon",), "✦", 30)
        top_bar.addWidget(self.page_icon)

        heading_box = QVBoxLayout()
        heading_box.setSpacing(1)
        self.title_label = QLabel("Smarti Diagnostic")
        self.title_label.setObjectName("DiagnosticPageTitle")
        heading_box.addWidget(self.title_label)
        self.subtitle_label = QLabel("אבחון מונחה, הסבר אנושי ותיקון רק באישור שלך")
        self.subtitle_label.setWordWrap(True)
        heading_box.addWidget(self.subtitle_label)
        top_bar.addLayout(heading_box, 1)

        self.log_btn = QPushButton("יומן")
        self.log_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.log_btn.setToolTip("פתיחת יומן טכני מסונן של Smarti Diagnostic")
        self.log_btn.clicked.connect(self.open_log)
        top_bar.addWidget(self.log_btn)
        layout.addLayout(top_bar)

        self.hero = QFrame()
        self.hero.setObjectName("DiagnosticHero")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        hero_layout.setSpacing(14)

        score_box = QVBoxLayout()
        score_box.setSpacing(0)
        self.score_label = QLabel("—")
        self.score_label.setObjectName("DiagnosticScore")
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_box.addWidget(self.score_label)
        self.score_caption = QLabel("ציון מצב")
        self.score_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_box.addWidget(self.score_caption)
        hero_layout.addLayout(score_box, 0)

        hero_text = QVBoxLayout()
        hero_text.setSpacing(5)
        self.summary_label = QLabel("עוד לא בוצעה בדיקה. אפשר להתחיל בבדיקה מהירה או מלאה.")
        self.summary_label.setObjectName("DiagnosticSummary")
        self.summary_label.setWordWrap(True)
        hero_text.addWidget(self.summary_label)
        self.completion_label = QLabel("● מוכן לבדיקה")
        self.completion_label.setObjectName("DiagnosticCompletion")
        hero_text.addWidget(self.completion_label)
        self.progress_label = QLabel("בדיקה מהירה נשארת מקומית; בדיקה מלאה מאמתת חיבורי ספק ודוא\"ל. אם היא מפעילה דפדפן חלופי לצורך בדיקה, הוא נסגר מיד בסיום.")
        self.progress_label.setWordWrap(True)
        hero_text.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        hero_text.addWidget(self.progress_bar)
        hero_layout.addLayout(hero_text, 1)
        layout.addWidget(self.hero)

        self.scan_action_row = DiagnosticScanActionRow()
        self.quick_scan_btn = QPushButton("בדיקה מהירה")
        self.quick_scan_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.quick_scan_btn.setFixedHeight(48)
        self.quick_scan_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.quick_scan_btn.setToolTip("בדיקה מקומית של הגדרות, קבצים ורכיבים ללא התחברות לחשבונות")
        self.quick_scan_btn.clicked.connect(lambda: self.start_scan(False))
        self.scan_action_row.add_button(self.quick_scan_btn)
        self.full_scan_btn = QPushButton("בדיקה מלאה")
        self.full_scan_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.full_scan_btn.setFixedHeight(48)
        self.full_scan_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.full_scan_btn.setToolTip("מאמתת חיבור לספק ולדוא\"ל; עשויה להפעיל זמנית דפדפן חלופי של Smarti בלי לפתוח אתר, ואז לסגור אותו")
        self.full_scan_btn.clicked.connect(lambda: self.start_scan(True))
        self.scan_action_row.add_button(self.full_scan_btn)
        self.stop_scan_btn = QPushButton("הפסק")
        self.stop_scan_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.stop_scan_btn.setFixedHeight(48)
        self.stop_scan_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.stop_scan_btn.clicked.connect(self.stop_scan)
        self.stop_scan_btn.hide()
        self.scan_action_row.add_button(self.stop_scan_btn)
        layout.addWidget(self.scan_action_row)

        filter_row = QHBoxLayout()
        filter_hint = QLabel("הצגה:")
        filter_row.addWidget(filter_hint)
        self.filter_keys = ["all", "attention", "pass", "skipped"]
        self.filter_segment = QFrame()
        self.filter_segment.setObjectName("DiagnosticFilterControl")
        self.filter_segment.setFixedHeight(48)
        filter_buttons_layout = QHBoxLayout(self.filter_segment)
        filter_buttons_layout.setContentsMargins(4, 4, 4, 4)
        filter_buttons_layout.setSpacing(2)
        self.filter_buttons = []
        for index, text in enumerate(["הכול", "דורש טיפול", "תקין", "לא רלוונטי"]):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            button.setFixedHeight(40)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, i=index: self._on_filter_changed(i))
            self.filter_buttons.append(button)
            filter_buttons_layout.addWidget(button, 1)
        self.filter_buttons[0].setChecked(True)
        filter_row.addWidget(self.filter_segment, 1)
        layout.addLayout(filter_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.content = QWidget()
        self.content.setObjectName("DiagnosticResults")
        self.content.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2, 2, 2, 6)
        self.content_layout.setSpacing(10)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.render_results()

    def _on_filter_changed(self, index):
        if 0 <= index < len(self.filter_keys):
            for button_index, button in enumerate(getattr(self, "filter_buttons", [])):
                button.setChecked(button_index == index)
            self.current_filter = self.filter_keys[index]
            self.render_results()

    def apply_theme(self):
        self.STATUS_META = {
            "pass": ("תקין", "✓", ACCENT_SECONDARY_COLOR),
            "warning": ("דורש תשומת לב", "!", ACCENT_PINK_COLOR),
            "error": ("דורש טיפול", "×", DANGER_COLOR),
            "skipped": ("לא נבדק", "–", SUBTLE_TEXT_COLOR),
        }
        self.setStyleSheet("background: transparent;")
        self.title_label.setStyleSheet(page_title_css(20))
        self.subtitle_label.setStyleSheet(muted_label_css(12))
        self.score_caption.setStyleSheet(muted_label_css(11))
        self.summary_label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 15px; font-weight: 800; background: transparent;")
        self._set_scan_state(getattr(self, "scan_state", "idle"), refresh_only=True)
        self.progress_label.setStyleSheet(muted_label_css(11))
        self.log_btn.setStyleSheet(ghost_button_css())
        self.quick_scan_btn.setStyleSheet(doctor_action_button_css(primary=False))
        self.full_scan_btn.setStyleSheet(doctor_action_button_css(primary=True))
        # The row distributes available width evenly.  A hidden stop button
        # leaves two equal columns; while scanning all three are equal.
        for button in (self.quick_scan_btn, self.full_scan_btn):
            button.setMinimumWidth(0)
            button.setMaximumWidth(16_777_215)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setFixedHeight(48)
        self.stop_scan_btn.setMinimumWidth(0)
        self.stop_scan_btn.setMaximumWidth(16_777_215)
        self.stop_scan_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.stop_scan_btn.setFixedHeight(48)
        self.stop_scan_btn.setStyleSheet(doctor_stop_button_css())
        self.scan_action_row.arrange_buttons()
        self.filter_segment.setStyleSheet(doctor_filter_css())
        self.hero.setStyleSheet(
            f"QFrame#DiagnosticHero {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {GLASS_STRONG_COLOR}, stop:0.55 {PANEL_ELEVATED_COLOR}, stop:1 {CARD_GRADIENT_END}); "
            f"border: 1px solid {LINE_COLOR}; border-radius: 22px; }}"
            f"QProgressBar {{ background: {FIELD_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 5px; min-height: 8px; max-height: 8px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR}); border-radius: 4px; }}"
        )
        self.score_label.setStyleSheet(
            f"color: {ACCENT_TEXT_COLOR}; background: {ACCENT_COLOR}; border: 2px solid {ACCENT_SECONDARY_COLOR}; "
            "border-radius: 26px; min-width: 52px; min-height: 52px; font-size: 19px; font-weight: 900;"
        )
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        refresh_themed_widget_icons(self)
        self.render_results()

    def _set_scan_state(self, state, refresh_only=False):
        self.scan_state = state
        labels = {
            "idle": ("● מוכן לבדיקה", SUBTLE_TEXT_COLOR),
            "running": ("● הבדיקה פועלת", ACCENT_COLOR),
            "complete": ("✓ הבדיקה הושלמה", ACCENT_SECONDARY_COLOR),
            "cancelled": ("■ הבדיקה הופסקה", ACCENT_PINK_COLOR),
            "failed": ("× הסריקה לא הושלמה", DANGER_COLOR),
        }
        text, color = labels.get(state, labels["idle"])
        if hasattr(self, "completion_label"):
            self.completion_label.setText(text)
            self.completion_label.setStyleSheet(
                f"color: {color}; background: {ACCENT_TINT if state in {'running', 'complete'} else 'transparent'}; "
                f"border: 1px solid {color}; border-radius: 10px; padding: 3px 8px; font-size: 11px; font-weight: 900;"
            )

    def _clear_results_layout(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _visible_results(self):
        if self.current_filter == "attention":
            return [item for item in self.results if item.status in {"error", "warning"}]
        if self.current_filter in {"pass", "skipped"}:
            return [item for item in self.results if item.status == self.current_filter]
        return list(self.results)

    def render_results(self):
        if not hasattr(self, "content_layout"):
            return
        self._clear_results_layout()
        visible = self._visible_results()
        if not visible:
            empty = QFrame()
            empty.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            empty.setStyleSheet(card_css(18, 22))
            empty_layout = QVBoxLayout(empty)
            empty_layout.setSpacing(6)
            label = QLabel("Smarti Diagnostic מוכן לבדיקה")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(section_title_css(16))
            empty_layout.addWidget(label)
            note = QLabel("התוצאות יוצגו כאן עם הסבר פשוט, פרטים טכניים מסוננים ותיקון מוצע כשיש כזה.")
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setWordWrap(True)
            note.setStyleSheet(muted_label_css(12))
            empty_layout.addWidget(note)
            self.content_layout.addWidget(empty)
            return
        for result in visible:
            self.content_layout.addWidget(self._result_card(result))
        self.content_layout.addStretch(1)

    def _result_card(self, result):
        status_text, glyph, color = self.STATUS_META.get(result.status, self.STATUS_META["skipped"])
        card = QFrame()
        card.setObjectName("DiagnosticResultCard")
        card.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card.setStyleSheet(
            f"QFrame#DiagnosticResultCard {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {GLASS_STRONG_COLOR}, stop:1 {CARD_GRADIENT_END}); "
            f"border: 1px solid {color}; border-radius: 18px; }}"
            "QLabel { background: transparent; border: none; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 13)
        layout.setSpacing(8)
        layout.setDirection(QBoxLayout.Direction.TopToBottom)

        header = QHBoxLayout()
        header.setDirection(QBoxLayout.Direction.RightToLeft)
        header.setSpacing(8)
        category_icon = QLabel()
        category_icon.setFixedSize(26, 26)
        category_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_names = self.CATEGORY_ICONS.get(result.category, ("doctor_icon",))
        set_themed_label_icon(category_icon, icon_names, glyph, 22)
        category_icon.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: 900; border: none; background: transparent;")
        title = QLabel(result.title_he)
        title.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 800; border: none; background: transparent;")
        header.addWidget(category_icon)
        header.addWidget(title, 1)
        pill = QLabel(f" {glyph} {status_text} ")
        pill.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setStyleSheet(f"color: {color}; background: {ACCENT_TINT if result.status == 'pass' else ACCENT_TINT_STRONG}; border: 1px solid {color}; border-radius: 11px; padding: 3px 7px; font-size: 11px; font-weight: 800;")
        header.addWidget(pill)
        layout.addLayout(header)

        explanation = QLabel(result.explanation_he)
        explanation.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        explanation.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        explanation.setWordWrap(True)
        explanation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        explanation.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; line-height: 1.45; border: none; background: transparent;")
        layout.addWidget(explanation)

        details = QLabel(f"נתונים טכניים: {result.technical_detail}")
        details.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        details.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        details.setWordWrap(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; background: {FIELD_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 10px; padding: 8px; font-size: 11px; font-family: Consolas, monospace;")
        details.setVisible(False)
        layout.addWidget(details)

        footer = QHBoxLayout()
        footer.setDirection(QBoxLayout.Direction.RightToLeft)
        footer.setSpacing(8)
        details_btn = QPushButton("פרטים טכניים")
        details_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        details_btn.setStyleSheet(ghost_button_css())
        details_btn.clicked.connect(lambda _=False, label=details, btn=details_btn: self._toggle_details(label, btn))
        footer.addWidget(details_btn)
        footer.addStretch(1)
        if result.repair_action is not None:
            repair = result.repair_action
            repair_btn = QPushButton(repair.title_he)
            repair_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            repair_btn.setToolTip(repair.description_he)
            repair_btn.setStyleSheet(PRIMARY_BUTTON_CSS if repair.risk in {"medium", "high"} else SECONDARY_BUTTON_CSS)
            repair_btn.clicked.connect(lambda _=False, action=repair: self.request_repair(action))
            footer.addWidget(repair_btn)
        layout.addLayout(footer)
        return card

    def _toggle_details(self, details, button):
        visible = not details.isVisible()
        details.setVisible(visible)
        button.setText("הסתר פרטים" if visible else "פרטים טכניים")

    def _coerce_result(self, raw):
        if isinstance(raw, CheckResult):
            return raw
        data = dict(raw or {})
        repair = data.get("repair_action")
        if isinstance(repair, dict):
            data["repair_action"] = RepairAction(**repair)
        elif not isinstance(repair, RepairAction):
            data["repair_action"] = None
        fields = {"id", "status", "explanation_he", "technical_detail", "repair_action", "category", "title_he"}
        return CheckResult(**{key: data.get(key) for key in fields})

    def start_scan(self, include_network):
        if self.doctor_worker is not None and self.doctor_worker.isRunning():
            return
        if self.repair_worker is not None and self.repair_worker.isRunning():
            return
        if bool(getattr(self.main_window, "agent_running", False)):
            QMessageBox.information(self, "Smarti Diagnostic", "כדי למנוע התנגשות עם משימת סוכן פעילה, יש להמתין לסיום המשימה לפני הבדיקה.")
            return
        self.results = []
        self.log_path = ""
        self.progress_bar.setValue(0)
        self.summary_label.setText("Smarti Diagnostic בודק את המערכת…")
        self.progress_label.setText("מתחיל בדיקה מלאה…" if include_network else "מתחיל בדיקה מהירה ומקומית…")
        self._set_scan_state("running")
        self._set_busy(True)
        self.render_results()
        self.doctor_worker = DiagnosticCheckWorker(self.core, include_network=include_network)
        self.doctor_worker.progress_signal.connect(self._on_scan_progress)
        self.doctor_worker.result_signal.connect(self._on_scan_result)
        self.doctor_worker.finished_signal.connect(self._on_scan_finished)
        self.doctor_worker.failed_signal.connect(self._on_scan_failed)
        self.doctor_worker.start()

    def stop_scan(self):
        if self.doctor_worker is not None and self.doctor_worker.isRunning():
            self.doctor_worker.request_stop()
            self.stop_scan_btn.setEnabled(False)
            self.progress_label.setText("מבקש לעצור לאחר סיום הפעולה הפעילה…")

    def _on_scan_progress(self, current, total, label):
        percent = max(0, min(99, int(((current - 1) / max(1, total)) * 100)))
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"שלב {current} מתוך {total}: {label}")

    def _on_scan_result(self, raw):
        self.results.append(self._coerce_result(raw))
        self.render_results()

    def _on_scan_finished(self, raw_results, log_path, cancelled=False):
        self.results = [self._coerce_result(item) for item in (raw_results or [])]
        self.log_path = str(log_path or "")
        self.progress_bar.setValue(self.progress_bar.value() if cancelled else 100)
        self._set_busy(False)
        self._refresh_summary()
        if cancelled:
            self.summary_label.setText("הבדיקה הופסקה לפי בקשתך. התוצאות שכבר נאספו נשארו זמינות לעיון.")
            self.progress_label.setText("לא בוצעו השלבים שנותרו. אפשר להפעיל בדיקה חדשה בכל רגע.")
            self._set_scan_state("cancelled")
        else:
            self._set_scan_state("complete")
        self.render_results()
        self.doctor_worker = None

    def _on_scan_failed(self, message):
        self._set_busy(False)
        self._set_scan_state("failed")
        self.progress_label.setText("הבדיקה נעצרה בגלל תקלה פנימית.")
        self.summary_label.setText("לא ניתן להשלים את הבדיקה. אפשר לנסות שוב או לפתוח את יומן Diagnostic.")
        self.doctor_worker = None
        QMessageBox.warning(self, "Smarti Diagnostic", f"לא ניתן להשלים את הבדיקה:\n{message}")

    def _refresh_summary(self):
        counts = {status: sum(1 for item in self.results if item.status == status) for status in self.STATUS_META}
        checked = counts["pass"] + counts["warning"] + counts["error"]
        score = 100 if not checked else max(0, 100 - counts["error"] * 24 - counts["warning"] * 9)
        self.score_label.setText(str(score))
        if counts["error"]:
            summary = f"נמצאו {counts['error']} בעיות שדורשות טיפול ו‑{counts['warning']} ממצאים שדורשים תשומת לב."
        elif counts["warning"]:
            summary = f"לא נמצאו כשלים קריטיים. יש {counts['warning']} ממצאים שמומלץ לעבור עליהם."
        elif checked:
            summary = "הבדיקות שהושלמו תקינות. רכיבים שלא הופעלו מסומנים כלא רלוונטיים."
        else:
            summary = "הבדיקה הופסקה לפני שבוצעו בדיקות פעילות."
        self.summary_label.setText(summary)
        self.progress_label.setText(f"הבדיקה הסתיימה: {counts['pass']} תקינות, {counts['warning']} לתשומת לב, {counts['error']} לטיפול, {counts['skipped']} לא רלוונטיות.")

    def _set_busy(self, busy):
        self.quick_scan_btn.setEnabled(not busy)
        self.full_scan_btn.setEnabled(not busy)
        self.stop_scan_btn.setVisible(busy)
        self.stop_scan_btn.setEnabled(busy)
        self.scan_action_row.arrange_buttons()
        self.log_btn.setEnabled(not busy or bool(self.log_path))

    def request_repair(self, action):
        if self.doctor_worker is not None and self.doctor_worker.isRunning():
            QMessageBox.information(self, "Smarti Diagnostic", "המתיני לסיום הבדיקה לפני הפעלת תיקון.")
            return
        if bool(getattr(self.main_window, "agent_running", False)):
            QMessageBox.information(self, "Smarti Diagnostic", "כדי למנוע התנגשות עם משימת סוכן פעילה, יש להמתין לסיום המשימה לפני תיקון.")
            return
        if action.id in {"open_settings", "open_tools", "open_data_folder", "open_task_center", "open_diagnostic_log", "open_doctor_log"}:
            self._open_navigation_action(action.id)
            return
        title = f"אישור תיקון: {action.title_he}"
        details = (
            f"מה יקרה:\n{action.description_he}\n\n"
            "הפעולה לא בוצעה אוטומטית. לחיצה על אישור תבצע רק את התיקון המתואר כאן."
        )
        dialog = ActionConfirmDialog(title, details, risk=action.risk, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._set_repair_busy(True, action.title_he)
        self.repair_worker = DiagnosticRepairWorker(self.core, action.id)
        self.repair_worker.finished_signal.connect(self._on_repair_finished)
        self.repair_worker.failed_signal.connect(self._on_repair_failed)
        self.repair_worker.start()

    def _set_repair_busy(self, busy, title=""):
        self.quick_scan_btn.setEnabled(not busy)
        self.full_scan_btn.setEnabled(not busy)
        self.stop_scan_btn.setVisible(False)
        self.scan_action_row.arrange_buttons()
        if busy:
            self.progress_label.setText(f"מבצע תיקון מאושר: {title}…")
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)

    def _on_repair_finished(self, message):
        self._set_repair_busy(False)
        self.repair_worker = None
        QMessageBox.information(self, "Smarti Diagnostic", str(message))
        self.start_scan(False)

    def _on_repair_failed(self, message):
        self._set_repair_busy(False)
        self.repair_worker = None
        self.progress_label.setText("התיקון לא הושלם. לא בוצע ניסיון נוסף באופן אוטומטי.")
        QMessageBox.warning(self, "Smarti Diagnostic", f"התיקון לא הושלם:\n{message}")

    def _open_navigation_action(self, action_id):
        if action_id == "open_settings":
            self.main_window.show_settings_page()
        elif action_id == "open_tools":
            self.main_window.show_tools_page()
        elif action_id == "open_data_folder":
            QDesktopServices.openUrl(QUrl.fromLocalFile(USER_DATA_DIR))
        elif action_id == "open_task_center":
            self.main_window.show_task_center_page()
        elif action_id in {"open_diagnostic_log", "open_doctor_log"}:
            self.open_log()

    def open_log(self):
        path = self.log_path or os.path.join(USER_DATA_DIR, "smarti_diagnostic.log")
        if not os.path.exists(path):
            legacy_path = os.path.join(USER_DATA_DIR, "smarti_doctor.log")
            if os.path.exists(legacy_path):
                path = legacy_path
        if not os.path.exists(path):
            QMessageBox.information(self, "Smarti Diagnostic", "אין עדיין יומן Diagnostic. הריצי בדיקה כדי ליצור יומן טכני מסונן.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def _is_memory_usage_model_name(model_name):
    name = str(model_name or "").strip().lower()
    return name in {"memory-rag/local", "smarti-memory-rag/local"} or name.startswith("memory-rag/")


USAGE_COST_CACHE_FILE = os.path.join(USER_DATA_DIR, "smarti_usage_cost_cache.json")
USAGE_COST_CACHE_VERSION = 1
USAGE_COST_CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
# Small built-in first-paint safety net for Smarti's default models that can be
# newer than the LiteLLM wheel bundled with a release.  A successful background
# catalog refresh replaces these rates; they are never allowed to replace a
# newer persisted rate.
USAGE_PRICING_FALLBACKS = {
    "gpt-5.6-sol": {
        "input": 0.000005,
        "output": 0.000030,
        "cache_read": 0.0000005,
        "cache_write": 0.00000625,
        "_source": "fallback",
    },
    "gemini/gemini-3.5-flash-lite": {
        "input": 0.0000003,
        "output": 0.0000025,
        "cache_read": 0.00000003,
        "cache_write": 0.0000003,
        "_source": "fallback",
    },
}


class UsageStatsLoadWorker(QThread):
    ready = pyqtSignal(int, str, object)
    _litellm_module = None
    _litellm_unavailable = False

    def __init__(self, generation, timeframe, parent=None):
        super().__init__(parent)
        self.generation = int(generation)
        self.timeframe = str(timeframe or "today")

    @classmethod
    def _litellm(cls):
        if cls._litellm_unavailable:
            return None
        if cls._litellm_module is not None:
            return cls._litellm_module
        if not LITELLM_INSTALLED:
            cls._litellm_unavailable = True
            return None
        try:
            import litellm
            cls._litellm_module = litellm
            return litellm
        except Exception:
            cls._litellm_unavailable = True
            return None

    def run(self):
        self._pricing_cache = self._load_pricing_cache()
        self._pricing_cache_dirty = False
        self._pricing_cache_stale = self._pricing_cache_is_stale()
        self._bundled_model_costs = self._load_bundled_litellm_pricing()
        try:
            rows, memory_usage, missing_pricing = self._load_model_usage(allow_litellm=False)
            try:
                self._save_pricing_cache()
            except Exception as exc:
                logging.warning("Usage pricing cache save failed: %s", exc)
            payload = {
                "models": rows,
                "memory": self._load_memory_summary(memory_usage),
                "error": "",
            }
        except Exception as exc:
            self.ready.emit(
                self.generation,
                self.timeframe,
                {"models": [], "memory": None, "error": str(exc)},
            )
            return

        self.ready.emit(self.generation, self.timeframe, payload)

    def _load_model_usage(self, allow_litellm=False, force_pricing_refresh=False):
        usage_data = {}
        if os.path.exists(USAGE_FILE):
            try:
                with open(USAGE_FILE, "r", encoding="utf-8") as f:
                    usage_data = json.load(f)
            except Exception:
                usage_data = {}

        aggregated = {}
        memory_usage = {"prompt": 0, "completion": 0, "total": 0}
        now = datetime.now()
        for date_str, models in usage_data.items():
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                delta = (now - d).days
                if self.timeframe == "today" and delta != 0:
                    continue
                if self.timeframe == "week" and delta > 7:
                    continue
                if self.timeframe == "month" and delta > 30:
                    continue
                if not isinstance(models, dict):
                    continue
                for model_name, stats in models.items():
                    if not isinstance(stats, dict):
                        continue
                    if _is_memory_usage_model_name(model_name):
                        memory_usage["prompt"] += int(stats.get("prompt", 0) or 0)
                        memory_usage["completion"] += int(stats.get("completion", 0) or 0)
                        memory_usage["total"] += int(stats.get("total", 0) or 0)
                        continue
                    bucket = aggregated.setdefault(str(model_name), {
                        "prompt": 0,
                        "completion": 0,
                        "total": 0,
                        "cached_prompt": 0,
                        "cache_write_prompt": 0,
                    })
                    bucket["prompt"] += int(stats.get("prompt", 0) or 0)
                    bucket["completion"] += int(stats.get("completion", 0) or 0)
                    bucket["total"] += int(stats.get("total", 0) or 0)
                    bucket["cached_prompt"] += int(stats.get("cached_prompt", 0) or 0)
                    bucket["cache_write_prompt"] += int(stats.get("cache_write_prompt", 0) or 0)
            except Exception:
                continue

        rows = []
        missing_pricing = False
        for model_name, stats in sorted(aggregated.items(), key=lambda x: x[1]["total"], reverse=True):
            cost_suffix, pricing_missing = self._cost_suffix(
                model_name,
                stats,
                allow_litellm=allow_litellm,
                force_refresh=force_pricing_refresh,
            )
            missing_pricing = missing_pricing or pricing_missing
            rows.append({
                "model": model_name,
                "prompt": int(stats.get("prompt", 0) or 0),
                "completion": int(stats.get("completion", 0) or 0),
                "total": int(stats.get("total", 0) or 0),
                "cached_prompt": int(stats.get("cached_prompt", 0) or 0),
                "cache_write_prompt": int(stats.get("cache_write_prompt", 0) or 0),
                "cost_suffix": cost_suffix,
            })
        return rows, memory_usage, missing_pricing

    @staticmethod
    def _litellm_model_name(model_name):
        litellm_model = str(model_name or "")
        lower_name = litellm_model.lower()
        if "gemini" in lower_name and not lower_name.startswith("gemini/"):
            litellm_model = f"gemini/{litellm_model}"
        elif "claude" in lower_name and not lower_name.startswith("anthropic/"):
            litellm_model = f"anthropic/{litellm_model}"
        return litellm_model

    def _load_pricing_cache(self):
        empty = {"version": USAGE_COST_CACHE_VERSION, "updated_at": "", "models": {}}
        try:
            with open(USAGE_COST_CACHE_FILE, "r", encoding="utf-8") as handle:
                cached = json.load(handle)
            if not isinstance(cached, dict) or int(cached.get("version", 0)) != USAGE_COST_CACHE_VERSION:
                return empty
            if not isinstance(cached.get("models"), dict):
                return empty
            return cached
        except Exception:
            return empty

    @staticmethod
    def _load_bundled_litellm_pricing():
        if not LITELLM_INSTALLED:
            return {}
        try:
            spec = importlib.util.find_spec("litellm")
            origin = Path(spec.origin) if spec and spec.origin else None
            if origin is None:
                return {}
            backup_path = origin.parent / "model_prices_and_context_window_backup.json"
            with open(backup_path, "r", encoding="utf-8") as handle:
                prices = json.load(handle)
            return prices if isinstance(prices, dict) else {}
        except Exception:
            return {}

    def _pricing_cache_is_stale(self):
        if not (self._pricing_cache.get("models") or {}):
            return True
        try:
            updated = datetime.fromisoformat(str(self._pricing_cache.get("updated_at") or ""))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - updated).total_seconds() >= USAGE_COST_CACHE_MAX_AGE_SECONDS
        except Exception:
            return True

    def _save_pricing_cache(self, force=False):
        if not self._pricing_cache_dirty and not (force and getattr(self, "_pricing_refresh_succeeded", False)):
            return
        self._pricing_cache["version"] = USAGE_COST_CACHE_VERSION
        self._pricing_cache["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        os.makedirs(os.path.dirname(USAGE_COST_CACHE_FILE), exist_ok=True)
        temp_path = f"{USAGE_COST_CACHE_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(self._pricing_cache, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, USAGE_COST_CACHE_FILE)
            self._pricing_cache_dirty = False
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    @staticmethod
    def _normalized_cost_value(value):
        if isinstance(value, (tuple, list)):
            return sum(float(part or 0) for part in value)
        return float(value or 0)

    @staticmethod
    def _pricing_info(model_costs, litellm_model):
        info = (model_costs or {}).get(litellm_model)
        if not info and "/" in litellm_model:
            info = (model_costs or {}).get(litellm_model.split("/", 1)[1])
        return info if isinstance(info, dict) else None

    @staticmethod
    def _pricing_entry_from_info(info):
        if isinstance(info, dict):
            input_rate = info.get("input_cost_per_token")
            output_rate = info.get("output_cost_per_token")
            if input_rate is not None or output_rate is not None:
                cache_read_rate = info.get("cache_read_input_token_cost")
                if cache_read_rate is None:
                    cache_read_rate = info.get("input_cost_per_token_cache_hit")
                if cache_read_rate is None:
                    cache_read_rate = input_rate
                cache_write_rate = info.get("cache_creation_input_token_cost")
                if cache_write_rate is None:
                    cache_write_rate = input_rate
                return {
                    "input": float(input_rate or 0),
                    "output": float(output_rate or 0),
                    "cache_read": float(cache_read_rate or 0),
                    "cache_write": float(cache_write_rate or 0),
                }
        return None

    def _pricing_entry_from_litellm(self, litellm, litellm_model):
        model_costs = getattr(litellm, "model_cost", {}) or {}
        info_entry = self._pricing_entry_from_info(self._pricing_info(model_costs, litellm_model))
        if info_entry is not None:
            return info_entry
        try:
            calculator = litellm.cost_calculator.cost_per_token
            input_rate = self._normalized_cost_value(calculator(
                model=litellm_model, prompt_tokens=1, completion_tokens=0,
            ))
            output_rate = self._normalized_cost_value(calculator(
                model=litellm_model, prompt_tokens=0, completion_tokens=1,
            ))
            return {
                "input": input_rate,
                "output": output_rate,
                "cache_read": input_rate,
                "cache_write": input_rate,
            }
        except Exception:
            return {"unpriced": True}

    @staticmethod
    def _cost_from_pricing_entry(entry, stats):
        if not isinstance(entry, dict) or entry.get("unpriced"):
            return 0.0
        prompt_tokens = int(stats.get("prompt", 0) or 0)
        completion_tokens = int(stats.get("completion", 0) or 0)
        cached_prompt_tokens = min(prompt_tokens, max(0, int(stats.get("cached_prompt", 0) or 0)))
        cache_write_tokens = min(
            max(0, prompt_tokens - cached_prompt_tokens),
            max(0, int(stats.get("cache_write_prompt", 0) or 0)),
        )
        uncached_prompt_tokens = max(0, prompt_tokens - cached_prompt_tokens - cache_write_tokens)
        input_rate = float(entry.get("input", 0) or 0)
        return (
            uncached_prompt_tokens * input_rate
            + cached_prompt_tokens * float(entry.get("cache_read", input_rate) or 0)
            + cache_write_tokens * float(entry.get("cache_write", input_rate) or 0)
            + completion_tokens * float(entry.get("output", 0) or 0)
        )

    def _cost_suffix(self, model_name, stats, allow_litellm=False, force_refresh=False):
        suffix = " | מחיר מוערך: חינמי / לא במאגר"
        litellm_model = self._litellm_model_name(model_name)
        models = self._pricing_cache.setdefault("models", {})
        entry = models.get(litellm_model)
        # Older builds persisted negative lookups.  Treat them as misses so a
        # transient catalog failure cannot permanently suppress future costs.
        if isinstance(entry, dict) and entry.get("unpriced"):
            models.pop(litellm_model, None)
            self._pricing_cache_dirty = True
            entry = None
        bundled_info = self._pricing_info(
            getattr(self, "_bundled_model_costs", {}),
            litellm_model,
        )
        bundled_entry = self._pricing_entry_from_info(bundled_info)
        should_use_bundled = bundled_entry is not None and (
            entry is None
            or entry.get("_source") == "fallback"
            or bool(getattr(self, "_pricing_cache_stale", False))
        )
        if should_use_bundled:
            bundled_entry["_source"] = "bundled"
            if bundled_entry != entry:
                models[litellm_model] = bundled_entry
                self._pricing_cache_dirty = True
            entry = bundled_entry
        if entry is None:
            fallback = USAGE_PRICING_FALLBACKS.get(litellm_model)
            entry = dict(fallback) if isinstance(fallback, dict) else None
            if entry is not None:
                models[litellm_model] = entry
                self._pricing_cache_dirty = True
        needs_refresh = entry is None or entry.get("_source") == "fallback"
        if allow_litellm and (needs_refresh or force_refresh):
            litellm = self._litellm()
            if litellm is not None:
                self._pricing_refresh_succeeded = True
                refreshed = self._pricing_entry_from_litellm(litellm, litellm_model)
                # Never downgrade a valid persisted/bundled/fallback price to
                # an unpriced marker when a remote catalog refresh fails.
                if isinstance(refreshed, dict) and not refreshed.get("unpriced"):
                    refreshed.pop("_source", None)
                    models[litellm_model] = refreshed
                    if refreshed != entry:
                        self._pricing_cache_dirty = True
                    entry = refreshed
                    needs_refresh = False

        cost = self._cost_from_pricing_entry(entry, stats)
        if cost > 0:
            suffix = f" | עלות מוערכת: ${cost:.6f}" if cost < 0.0001 else f" | עלות מוערכת: ${cost:.4f}"
        return suffix, bool(needs_refresh)

    def _load_memory_summary(self, usage_stats):
        if not os.path.exists(MEMORY_FILE):
            return None
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memory_data = json.load(f)
        except Exception:
            return None
        entries = memory_data.get("entries", []) if isinstance(memory_data, dict) else []
        stats = memory_data.get("stats", {}) if isinstance(memory_data, dict) else {}
        now = datetime.now()
        active = 0
        active_by_type = {"user": 0, "long_term": 0, "short_term": 0, "tool": 0}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
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
        return {
            "active": active,
            "active_by_type": active_by_type,
            "injected": int(stats.get("injected_tokens_estimate", 0) or 0),
            "last_injected_tokens": int(stats.get("last_injected_tokens", 0) or 0),
            "last_results": int(stats.get("last_injected_results_count", stats.get("last_results_count", 0)) or 0),
            "search_count": int(stats.get("searches", 0) or 0),
            "usage_total": int((usage_stats or {}).get("total", 0) or 0),
            "last_injected_at": stats.get("last_injected_at"),
            "retriever": stats.get("last_retriever", "local"),
        }


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
        self._usage_generation = 0
        self._usage_workers = []
        layout.addWidget(self.scroll)

    def clear_data(self):
        if QMessageBox.question(self, "איפוס נתונים", "למחוק הכל?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try: os.remove(USAGE_FILE)
            except: pass
            self.load_data(self.current_timeframe)

    def _is_memory_usage_model(self, model_name):
        return _is_memory_usage_model_name(model_name)

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

        self._clear_content()
        self._add_usage_message("טוען נתוני שימוש...")
        self._usage_generation += 1
        # Keep long pricing refreshes owned by the main window so invalidating
        # this page during a theme change cannot destroy a running QThread.
        worker_owner = self.main_window if isinstance(self.main_window, QObject) else self
        worker = UsageStatsLoadWorker(self._usage_generation, timeframe, worker_owner)
        self._usage_workers.append(worker)
        worker.ready.connect(self._on_usage_data_ready)
        worker.finished.connect(lambda w=worker: self._forget_usage_worker(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _forget_usage_worker(self, worker):
        try:
            self._usage_workers.remove(worker)
        except ValueError:
            pass

    def _clear_content(self):
        for i in reversed(range(self.content_layout.count())):
            w = self.content_layout.itemAt(i).widget()
            if w: w.deleteLater()

    def _add_usage_message(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(muted_label_css(15) + " margin-top: 20px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(lbl)

    def _on_usage_data_ready(self, generation, timeframe, payload):
        if generation != self._usage_generation or timeframe != self.current_timeframe:
            return
        self._clear_content()
        payload = payload or {}
        if payload.get("error"):
            self._add_usage_message("לא ניתן היה לטעון את נתוני השימוש כרגע.")
            return
        rows = payload.get("models") or []
        if not rows:
            self._add_usage_message("אין נתוני שימוש במודלים בטווח הזמן שנבחר.")
        else:
            for row in rows:
                self._add_model_usage_card(row)

        self._add_memory_usage_card(payload.get("memory"))

    def _add_model_usage_card(self, row):
        card = QFrame()
        card.setStyleSheet(card_css(15, 8))
        card_layout = QVBoxLayout(card)

        m_name = str(row.get("model") or "")
        m_lbl = QLabel(m_name)
        m_lbl.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 700; font-size: 16px; border: none;")
        m_lbl.setWordWrap(True)
        card_layout.addWidget(m_lbl)

        total = int(row.get("total", 0) or 0)
        prompt = int(row.get("prompt", 0) or 0)
        completion = int(row.get("completion", 0) or 0)
        cached_prompt = int(row.get("cached_prompt", 0) or 0)
        cache_write_prompt = int(row.get("cache_write_prompt", 0) or 0)
        total_lbl = QLabel(f"סה\"כ טוקנים: {total:,}{row.get('cost_suffix') or ''}")
        total_lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 700; border: none;")
        total_lbl.setWordWrap(True)
        card_layout.addWidget(total_lbl)

        cache_suffix = ""
        if cached_prompt or cache_write_prompt:
            cache_suffix = f"  |  מטמון: {cached_prompt:,}"
            if cache_write_prompt:
                cache_suffix += f"  |  כתיבת מטמון: {cache_write_prompt:,}"
        details_lbl = QLabel(f"קלט: {prompt:,}  |  פלט: {completion:,}{cache_suffix}")
        details_lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 13px; border: none;")
        card_layout.addWidget(details_lbl)
        self.content_layout.addWidget(card)

    def _add_memory_usage_card(self, summary=None):
        if not summary:
            return
        active = int(summary.get("active", 0) or 0)
        active_by_type = summary.get("active_by_type", {}) if isinstance(summary, dict) else {}
        injected = int(summary.get("injected", 0) or 0)
        last_injected_tokens = int(summary.get("last_injected_tokens", 0) or 0)
        last_results = int(summary.get("last_results", 0) or 0)
        search_count = int(summary.get("search_count", 0) or 0)
        usage_total = int(summary.get("usage_total", 0) or 0)
        last_injected = self._format_usage_time(summary.get("last_injected_at"))
        retriever = summary.get("retriever", "local")
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

def format_interval_hebrew(interval_minutes):
    try:
        minutes = int(float(interval_minutes))
    except Exception:
        return f"כל {interval_minutes} דקות"
    
    if minutes <= 0:
        return "מיידית"
    
    if minutes == 1440:
        return "כל יום"
    if minutes == 60:
        return "כל שעה"
        
    days = minutes // 1440
    remaining_minutes = minutes % 1440
    hours = remaining_minutes // 60
    mins = remaining_minutes % 60
    
    parts = []
    if days > 0:
        if days == 1:
            parts.append("יום")
        elif days == 2:
            parts.append("יומיים")
        else:
            parts.append(f"{days} ימים")
            
    if hours > 0:
        if hours == 1:
            parts.append("שעה")
        elif hours == 2:
            parts.append("שעתיים")
        else:
            parts.append(f"{hours} שעות")
            
    if mins > 0:
        if mins == 1:
            parts.append("דקה")
        elif mins == 2:
            parts.append("שתי דקות")
        else:
            parts.append(f"{mins} דקות")
            
    if not parts:
        return "פחות מדקה"
        
    if len(parts) == 1:
        return f"כל {parts[0]}"
    
    last = parts[-1]
    if last[0].isdigit():
        prefix = "ו-"
    else:
        prefix = "ו"
        
    last_formatted = f"{prefix}{last}"
    
    if len(parts) == 2:
        return f"כל {parts[0]} {last_formatted}"
    else:
        return f"כל {', '.join(parts[:-1])} {last_formatted}"


class ResponsiveTaskCard(QFrame):
    """Word-wrapped task card whose height follows its current viewport width."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._height_sync_pending = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def _sync_height_for_width(self):
        self._height_sync_pending = False
        width = max(1, self.width())
        desired = self.heightForWidth(width) if self.hasHeightForWidth() else -1
        if desired < 0 and self.layout() is not None:
            desired = self.layout().sizeHint().height()
        desired = max(0, int(desired))
        if desired and self.minimumHeight() != desired:
            self.setMinimumHeight(desired)
            self.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._height_sync_pending:
            self._height_sync_pending = True
            QTimer.singleShot(0, self._sync_height_for_width)

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
            card = ResponsiveTaskCard()
            card.setStyleSheet(card_css(12, 8))
            card_layout = QVBoxLayout(card)
            
            repeat = task.get("repeat", "once")
            freq_str = "חד-פעמית"
            if repeat == "interval":
                interval = task.get("interval_minutes") or task.get("delay_minutes") or 1
                freq_str = format_interval_hebrew(interval)
            elif repeat == "weekly":
                days = task.get("days_of_week") or []
                day_names = {0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון"}
                days_list = [day_names.get(d, str(d)) for d in sorted(days)]
                freq_str = f"שבועית בימים: {', '.join(days_list)}"
            
            conv_mode = task.get("conversation_mode", "current")
            conv_names = {"current": "שיחת המקור", "new": "שיחה חדשה בכל פעם", "dedicated": "שיחה ייעודית קבועה"}
            conv_str = conv_names.get(conv_mode, "שיחת המקור")
            
            status_hebrew = {"scheduled": "מתוזמן", "running": "רץ כעת", "cancelling": "בביטול", "done": "הושלם", "failed": "נכשל", "cancelled": "בוטל"}
            status_str = status_hebrew.get(task.get("status", ""), task.get("status", ""))
            
            run_at_str = task.get('run_at', '')
            if "T" in run_at_str:
                run_at_str = run_at_str.replace("T", " ")
            
            title_text = f"מזהה: {task.get('id')} | סטטוס: {status_str} | תדירות: {freq_str} | ניתוב: {conv_str}\nזמן הרצה הבא: {run_at_str}"
            
            title = QLabel(title_text)
            title.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 700; font-size: 13px; line-height: 1.4; border: none;")
            title.setWordWrap(True)
            card_layout.addWidget(title)
            
            body = QLabel(str(task.get("prompt", "")))
            body.setWordWrap(True)
            body.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; border: none; margin-top: 4px;")
            card_layout.addWidget(body)
            
            if task.get("last_result"):
                result = QLabel(str(task.get("last_result", ""))[:500])
                result.setWordWrap(True)
                result.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px; border: none; margin-top: 4px;")
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
        lines = ["Unified Smarti log:"]
        try:
            lines.extend(_unified_log_lines(500) or ["אין עדיין רשומות לוג."])
        except Exception as e:
            lines.append(f"ERROR: {e}")
        self.text.setPlainText("\n".join(lines))

class ToolsSettingsPage(QWidget):
    def _make_header_icon_button(self, icon_names, tooltip, callback, fallback="+"):
        button = QPushButton()
        button.setFixedSize(36, 36)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        button.setToolTip(str(tooltip or ""))
        button.setStyleSheet(icon_button_css(36))
        set_themed_button_icon(button, icon_names, fallback, 22, clear_text=True)
        button.clicked.connect(callback)
        return button

    def _section_header_row(self, title, action_tooltip="", action_callback=None):
        row = QWidget()
        row.setStyleSheet(f"background: transparent; border-top: 1px solid {SOFT_LINE_COLOR};")
        row.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 16, 0, 0)
        row_layout.setSpacing(8)
        if action_callback is not None:
            row_layout.addWidget(
                self._make_header_icon_button(("plus_icon", "add_icon"), action_tooltip, action_callback, "+"),
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
        row_layout.addStretch(1)
        label = QLabel(title)
        label.setStyleSheet(section_title_css(16))
        row_layout.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

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
        self.refresh_btn = self._make_header_icon_button(
            ("check_updates_icon", "update_icon", "refresh_icon"),
            "רענון קטלוג הכלים",
            self.refresh_tools_page,
            "R",
        )
        top_bar.addWidget(self.refresh_btn)
        layout.addLayout(top_bar)
        hint = QLabel("כאן מנהלים אילו יכולות זמינות לסמארטי. התקנה ידנית זמינה מכפתור + ליד האזור המתאים.")
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
        
        self.form.addRow(self._section_header_row("כלים מובנים"))
        
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
            
        self.form.addRow(self._section_header_row("כלים חיצוניים", "התקנת כלי Python", self.install_python_tool_manually))
        
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

        self.form.addRow(self._section_header_row("כלי MCP מותקנים", "הוספת כלי MCP", self.install_mcp_manually))
        
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

        self.form.addRow(self._section_header_row("מיומנויות מותקנות", "התקנת מיומנות", self.install_skill_manually))
        has_skills = False
        registry = getattr(self.core, "skill_registry", {}) or self.core._load_skill_registry()
        for name, spec in sorted(registry.items()):
            has_skills = True
            key = f"skill_{name}"
            cb = SmartiCheckBox(self._skill_display_label(name, spec))
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
            lbl_no_skills = QLabel("אין מיומנויות מותקנות.")
            lbl_no_skills.setStyleSheet(muted_label_css(13))
            self.form.addRow(lbl_no_skills)

        scroll.setWidget(content)
        layout.addWidget(scroll)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(1800)
        self._refresh_timer.timeout.connect(self._refresh_if_catalog_changed)
        self._refresh_timer.start()
        self._refresh_spin_timer = QTimer(self)
        self._refresh_spin_timer.setInterval(18)
        self._refresh_spin_timer.timeout.connect(self._spin_refresh_icon)
        self._refresh_spin_angle = 0

    def _refresh_icon_pixmap(self):
        icon = themed_icon("check_updates_icon", "update_icon", "refresh_icon")
        return icon.pixmap(22, 22) if not icon.isNull() else QPixmap()

    def _pixmap_alpha_center(self, pixmap):
        image = pixmap.toImage()
        left = image.width()
        top = image.height()
        right = -1
        bottom = -1
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() <= 8:
                    continue
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
        if right < left or bottom < top:
            return pixmap.width() / 2, pixmap.height() / 2
        return (left + right + 1) / 2, (top + bottom + 1) / 2

    def _refresh_icon_canvas(self, pixmap, angle=0):
        if pixmap.isNull():
            return QPixmap()
        base = pixmap.scaled(22, 22, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        visual_x, visual_y = self._pixmap_alpha_center(base)
        canvas = QPixmap(26, 26)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(canvas.width() / 2, canvas.height() / 2)
        if angle:
            painter.rotate(float(angle))
        painter.drawPixmap(QRectF(-visual_x, -visual_y, base.width(), base.height()), base, QRectF(base.rect()))
        painter.end()
        return canvas

    def _start_refresh_spin(self):
        if not hasattr(self, "refresh_btn"):
            return
        self._refresh_spin_base_pixmap = self._refresh_icon_pixmap()
        if self._refresh_spin_base_pixmap.isNull():
            return
        self._refresh_spin_angle = 0
        self.refresh_btn.setIcon(QIcon(self._refresh_icon_canvas(self._refresh_spin_base_pixmap, 0)))
        self.refresh_btn.setIconSize(QSize(26, 26))
        self._refresh_spin_timer.start()

    def _spin_refresh_icon(self):
        pixmap = getattr(self, "_refresh_spin_base_pixmap", QPixmap())
        if pixmap.isNull() or not hasattr(self, "refresh_btn"):
            self._refresh_spin_timer.stop()
            return
        self._refresh_spin_angle += 24
        if self._refresh_spin_angle >= 360:
            self._refresh_spin_timer.stop()
            refresh_themed_button_icon(self.refresh_btn)
            return
        self.refresh_btn.setIcon(QIcon(self._refresh_icon_canvas(pixmap, self._refresh_spin_angle)))
        self.refresh_btn.setIconSize(QSize(26, 26))

    def rebuild_tools_content(self):
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
        main_window = self.main_window
        stack = main_window.stacked_widget
        old_page = self
        new_page = ToolsSettingsPage(self.core, main_window)
        main_window.tools_page = new_page
        stack.addWidget(new_page)
        QStackedWidget.setCurrentWidget(stack, new_page)
        stack.removeWidget(old_page)
        old_page.deleteLater()

    def refresh_tools_page(self):
        self._start_refresh_spin()
        try:
            self.core.refresh_extension_catalogs(force=True)
        except Exception:
            logging.exception("Failed to refresh extension catalogs from Tools page.")
        QTimer.singleShot(340, self.rebuild_tools_content)

    def _refresh_if_catalog_changed(self):
        try:
            if self.core.refresh_extension_catalogs_if_changed(rebuild_prompt=False):
                QTimer.singleShot(0, self.rebuild_tools_content)
        except RuntimeError:
            pass
        except Exception:
            logging.exception("Tools page catalog watcher failed.")

    def _show_install_result(self, title, result):
        if str(result).startswith("SUCCESS:"):
            QMessageBox.information(self, title, str(result))
            QTimer.singleShot(0, self.main_window.show_tools_page)
        else:
            QMessageBox.warning(self, title, str(result))

    def install_skill_manually(self):
        choice, ok = themed_item_input(
            self, "התקנת מיומנות", "מקור התקנה:", ["קובץ ZIP", "תיקייה"], 0, False,
        )
        if not ok:
            return
        if choice == "תיקייה":
            path = QFileDialog.getExistingDirectory(self, "בחירת תיקיית מיומנות", os.path.expanduser("~"))
        else:
            path, _ = QFileDialog.getOpenFileName(self, "בחירת קובץ מיומנות ZIP", os.path.expanduser("~"), "Skill ZIP (*.zip)")
        if not path:
            return
        result = self.core.install_local_skill_package(path)
        self._show_install_result("התקנת מיומנות", result)

    def install_python_tool_manually(self):
        path, _ = QFileDialog.getOpenFileName(self, "בחירת כלי Python", os.path.expanduser("~"), "Python Tool (*.py *.pyw *.zip)")
        if not path:
            return
        result = self.core.install_python_tool_from_path(path)
        self._show_install_result("התקנת כלי Python", result)

    def install_mcp_manually(self):
        choice, ok = themed_item_input(
            self, "הוספת MCP", "מקור התקנה:", ["חבילת npm נעולה", "קובץ JSON"], 0, False,
        )
        if not ok:
            return
        if choice == "קובץ JSON":
            path, _ = QFileDialog.getOpenFileName(self, "בחירת קובץ MCP JSON", os.path.expanduser("~"), "MCP JSON (*.json)")
            if not path:
                return
            result = self.core.install_mcp_manual(config_path=path)
        else:
            package, ok = themed_text_input(
                self, "הוספת MCP", "שם חבילה עם גרסה, למשל @scope/server@1.2.3:"
            )
            if not ok or not str(package).strip():
                return
            result = self.core.install_mcp_manual(package=str(package).strip())
        self._show_install_result("הוספת MCP", result)

    def _tool_label(self, tool_name):
        return BUILTIN_TOOL_DISPLAY_LABELS.get(tool_name, str(tool_name).replace("_", " "))

    def _skill_source_label(self, source):
        return {
            "builtin": "מובנה",
            "local": "הותקן ידנית",
            "clawhub": "ClawHub",
        }.get(str(source or "local").strip().lower(), "הותקן ידנית")

    def _skill_display_label(self, name, spec):
        spec = spec if isinstance(spec, dict) else {}
        source_label = self._skill_source_label(spec.get("source", "local"))
        return f"\u2066{str(name or '').strip()} ({source_label})\u2069"

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
            "skill": "מיומנות",
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

class SSLTrustSettingsCard(QFrame):
    """Theme-aware, inline TLS trust editor for Smarti's narrow settings page."""

    settingsChanged = pyqtSignal()
    MODE_OPTIONS = (
        (SSL_MODE_SYSTEM, "מאגר Windows"),
        (SSL_MODE_CUSTOM_CA, "תעודה"),
        (SSL_MODE_LEGACY_INSECURE, "ללא אימות"),
    )

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self._values = {
            "ssl_trust_mode": normalize_ssl_trust_mode(core.settings.get("ssl_trust_mode")),
            "ssl_custom_ca_path": str(core.settings.get("ssl_custom_ca_path") or ""),
            "ssl_filter_setup_completed": bool(core.settings.get("ssl_filter_setup_completed", False)),
            # Retained as an empty migration field for older settings files.
            "ssl_legacy_insecure_allowed_hosts": [],
            "ssl_trust_migration_version": SSL_TRUST_MIGRATION_VERSION,
            "allow_insecure_ssl_compat": bool(core.settings.get("allow_insecure_ssl_compat", False)),
        }
        self._test_worker = None
        self._editor_expanded = False
        self._pending_test_completed = bool(
            self._values.get("ssl_filter_setup_completed", False)
        )
        self.setObjectName("SSLTrustSettingsCard")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(10)
        summary = QVBoxLayout()
        summary.setSpacing(4)

        self.current_badge = QLabel("המצב הפעיל כעת")
        self.current_badge.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.mode_label = QLabel()
        self.mode_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.trust_detail_label = QLabel()
        self.trust_detail_label.setWordWrap(True)
        self.trust_detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        summary.addWidget(self.current_badge)
        summary.addWidget(self.mode_label)
        summary.addWidget(self.status_label)
        summary.addWidget(self.trust_detail_label)

        self.configure_btn = QPushButton()
        self.configure_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.configure_btn.setFixedWidth(96)
        self.configure_btn.clicked.connect(self.toggle_editor)
        header.addLayout(summary, 1)
        header.addWidget(self.configure_btn, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        self.editor = QFrame()
        self.editor.setObjectName("SSLTrustInlineEditor")
        self.editor.setMinimumHeight(680)
        editor_layout = QVBoxLayout(self.editor)
        editor_layout.setContentsMargins(12, 14, 12, 12)
        editor_layout.setSpacing(11)

        editor_title = QLabel("בחירת דרך החיבור המאובטח")
        editor_title.setObjectName("SSLTrustEditorTitle")
        editor_layout.addWidget(editor_title)
        editor_help = QLabel(
            "בכל חיבור HTTPS, סמארטי בודק את זהות השרת. ברשת עם סינון מומלץ להתחיל "
            "במאגר האישורים של Windows. רק אם האפשרות הזו אינה עובדת, אפשר לייבא "
            "תעודת שורש ציבורית שהתקבלה מספק הסינון."
        )
        editor_help.setObjectName("SSLTrustEditorHelp")
        editor_help.setWordWrap(True)
        editor_layout.addWidget(editor_help)

        self.mode_control = SegmentedControl([label for _, label in self.MODE_OPTIONS])
        editor_layout.addWidget(self.mode_control)

        self.mode_stack = QStackedWidget()
        self.mode_stack.setStyleSheet(
            "QStackedWidget { background: transparent; border: none; }"
        )
        self.mode_stack.setMinimumHeight(260)
        self.mode_stack.addWidget(self._build_system_page())
        self.mode_stack.addWidget(self._build_custom_page())
        self.mode_stack.addWidget(self._build_compat_page())
        editor_layout.addWidget(self.mode_stack)

        test_card = QFrame()
        test_card.setObjectName("SSLTrustTestCard")
        test_card.setMinimumHeight(155)
        test_layout = QVBoxLayout(test_card)
        test_layout.setContentsMargins(12, 11, 12, 11)
        test_layout.setSpacing(7)
        self.test_title = QLabel("בדיקת החיבור")
        test_layout.addWidget(self.test_title)
        self.test_explanation = QLabel(
            "הבדיקה מתחברת לכתובת ציבורית קבועה של Google בלי לשלוח מפתח API, "
            "תוכן שיחה או מידע אישי."
        )
        self.test_explanation.setWordWrap(True)
        test_layout.addWidget(self.test_explanation)
        self.test_endpoint = QLabel("https://www.gstatic.com/generate_204")
        self.test_endpoint.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.test_endpoint.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        test_layout.addWidget(self.test_endpoint)
        test_row = QHBoxLayout()
        test_row.setSpacing(8)
        self.test_btn = QPushButton("בדיקת חיבור")
        self.test_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.test_btn.setFixedSize(118, 40)
        self.test_status = QLabel("טרם בוצעה בדיקה עבור הבחירה הנוכחית.")
        self.test_status.setWordWrap(True)
        test_row.addWidget(self.test_btn, 0)
        test_row.addWidget(self.test_status, 1)
        test_layout.addLayout(test_row)
        editor_layout.addWidget(test_card)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()
        self.cancel_btn = QPushButton("ביטול")
        self.save_btn = QPushButton("שמירה והחלה")
        self.cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.save_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.cancel_btn.setFixedSize(132, 50)
        self.save_btn.setFixedSize(132, 50)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.save_btn)
        editor_layout.addLayout(actions)
        root.addWidget(self.editor)
        self.editor.hide()

        self.mode_control.currentIndexChanged.connect(self._on_mode_changed)
        self.test_btn.clicked.connect(self._run_test)
        self.cancel_btn.clicked.connect(self._cancel_editor)
        self.save_btn.clicked.connect(self._save_editor)
        self._load_editor_from_values()
        self._refresh_summary()
        self.apply_theme()

    def _mode_page(self, title, explanation):
        page = QFrame()
        page.setObjectName("SSLTrustModePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(7)
        heading = QLabel(title)
        heading.setProperty("smartiSSLModeTitle", True)
        heading.setWordWrap(True)
        body = QLabel(explanation)
        body.setProperty("smartiSSLModeBody", True)
        body.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(body)
        return page, layout

    def _build_system_page(self):
        page, layout = self._mode_page(
            "מומלץ: מאגר האישורים של Windows",
            "כדי לאמת את שרשרת האישורים, סמארטי משתמש במאגר של Windows. כך נעשה "
            "שימוש גם בתעודות של נטפרי, רימון וכדומה שכבר מותקנות במערכת, בלי לבחור קובץ.",
        )
        badge = QLabel("אימות זהות השרת נשאר פעיל")
        badge.setProperty("smartiSSLSafeBadge", True)
        badge.setWordWrap(True)
        layout.addWidget(badge)
        return page

    def _build_custom_page(self):
        page, layout = self._mode_page(
            "תעודת שורש ציבורית של ספק הסינון",
            "מיועד למקרה שבו מאגר Windows עדיין אינו מספיק. יש לבחור קובץ CER, CRT "
            "או PEM ציבורי שקיבלת מספק הסינון. Smarti דוחה מפתח פרטי ותעודת שרת רגילה.",
        )
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.custom_ca_path = QLineEdit()
        self.custom_ca_path.setReadOnly(True)
        self.custom_ca_path.setMinimumHeight(40)
        self.custom_ca_path.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.custom_ca_path.setPlaceholderText("לא נבחרה תעודה")
        self.browse_btn = QPushButton("בחירת תעודה")
        self.browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.browse_btn.setFixedSize(122, 40)
        path_row.addWidget(self.custom_ca_path, 1)
        path_row.addWidget(self.browse_btn, 0)
        layout.addLayout(path_row)
        self.custom_ca_status = QLabel("")
        self.custom_ca_status.setWordWrap(True)
        layout.addWidget(self.custom_ca_status)
        self.browse_btn.clicked.connect(self._choose_custom_ca)
        return page

    def _build_compat_page(self):
        page, layout = self._mode_page(
            "תאימות ישנה — חיבור ללא אימות תעודות",
            "אפשרות זו מחזירה את התנהגות ה-SSL הישנה של Smarti: אימות תעודות HTTPS "
            "מכובה באופן רחב ב-Smarti, בדפדפן האוטומציה ובכלי שורת הפקודה שמופעלים ממנו.",
        )
        warning = QLabel(
            "זהות השרת לא תיבדק, ולכן מסנן או גורם אחר ברשת עלולים להתחזות לשירות. "
            "יש להשתמש באפשרות זו רק אם מאגר Windows וייבוא תעודה אינם פותרים את הבעיה."
        )
        warning.setProperty("smartiSSLWarning", True)
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.compat_ack = SmartiCheckBox(
            "ברור לי שבמצב זה אימות תעודות HTTPS כבוי בכל רכיבי Smarti"
        )
        self.compat_ack.setWordWrap(True)
        layout.addWidget(self.compat_ack)
        return page

    def _mode_index(self, mode):
        return next(
            (
                index
                for index, (key, _label) in enumerate(self.MODE_OPTIONS)
                if key == normalize_ssl_trust_mode(mode)
            ),
            0,
        )

    def _current_mode(self):
        index = max(0, min(self.mode_control.currentIndex(), len(self.MODE_OPTIONS) - 1))
        return self.MODE_OPTIONS[index][0]

    def _apply_test_status_style(self):
        tone = self.test_status.property("smartiSSLTestStatusTone") or "muted"
        colors = {
            "muted": MUTED_TEXT_COLOR,
            "accent": ACCENT_SECONDARY_COLOR,
            "danger": DANGER_COLOR,
        }
        weight = 400 if tone == "muted" else 800
        self.test_status.setStyleSheet(
            f"color: {colors.get(tone, MUTED_TEXT_COLOR)}; font-size: 12px; "
            f"font-weight: {weight}; background: transparent;"
        )

    def _set_test_status(self, text, tone="muted"):
        self.test_status.setText(text)
        self.test_status.setProperty("smartiSSLTestStatusTone", tone)
        self._apply_test_status_style()

    def _load_editor_from_values(self):
        mode = normalize_ssl_trust_mode(self._values.get("ssl_trust_mode"))
        self.mode_control.setCurrentIndex(self._mode_index(mode), emit=False)
        self.mode_stack.setCurrentIndex(self._mode_index(mode))
        path = str(self._values.get("ssl_custom_ca_path") or "")
        self.custom_ca_path.setText(path)
        self.compat_ack.setChecked(False)
        self._pending_test_completed = bool(
            self._values.get("ssl_filter_setup_completed", False)
        )
        self._show_certificate_selection(path)
        self._set_test_status("טרם בוצעה בדיקה עבור הבחירה הנוכחית.")

    def _show_certificate_selection(self, path, validation_message=""):
        metadata = describe_custom_ca(path)
        if not path:
            text = "לא נבחר קובץ. אפשר לבחור את תעודת השורש הציבורית של ספק הסינון."
            color = MUTED_TEXT_COLOR
        elif metadata.get("name"):
            parts = [f"תעודה: {metadata['name']}"]
            if metadata.get("expires"):
                parts.append(f"בתוקף עד {metadata['expires']}")
            if metadata.get("fingerprint"):
                fingerprint = metadata["fingerprint"]
                parts.append(f"SHA-256 {fingerprint[:16]}…{fingerprint[-8:]}")
            if validation_message:
                parts.append(validation_message)
            text = " · ".join(parts)
            color = ACCENT_SECONDARY_COLOR
        else:
            text = validation_message or "נבחר קובץ, אך פרטי התעודה עדיין לא אומתו."
            color = MUTED_TEXT_COLOR
        self.custom_ca_status.setText(text)
        self.custom_ca_status.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 700; background: transparent;"
        )

    def _refresh_summary(self):
        mode = normalize_ssl_trust_mode(self._values.get("ssl_trust_mode"))
        completed = bool(self._values.get("ssl_filter_setup_completed"))
        if mode == SSL_MODE_CUSTOM_CA:
            metadata = describe_custom_ca(self._values.get("ssl_custom_ca_path"))
            cert_name = (
                metadata.get("name")
                or metadata.get("filename")
                or "לא נבחרה תעודה"
            )
            self.mode_label.setText("תעודת סינון מיובאת")
            self.status_label.setText(
                "אימות HTTPS פעיל · החיבור עבר את הבדיקה האחרונה"
                if completed
                else "אימות HTTPS פעיל · מומלץ לבצע בדיקת חיבור"
            )
            details = [f"תעודה בשימוש: {cert_name}"]
            if metadata.get("issuer") and metadata["issuer"] != metadata.get("name"):
                details.append(f"מנפיק: {metadata['issuer']}")
            if metadata.get("fingerprint"):
                fingerprint = metadata["fingerprint"]
                details.append(f"SHA-256 {fingerprint[:16]}…{fingerprint[-8:]}")
            self.trust_detail_label.setText(" · ".join(details))
            color = ACCENT_SECONDARY_COLOR if completed else MUTED_TEXT_COLOR
        elif mode == SSL_MODE_LEGACY_INSECURE:
            self.mode_label.setText("תאימות ישנה ללא אימות תעודות")
            self.status_label.setText("אזהרה: אימות HTTPS כבוי באופן רחב")
            self.trust_detail_label.setText(
                "אין תעודת CA בשימוש. Smarti וכלי הרשת שמופעלים ממנו מקבלים "
                "חיבורי HTTPS בלי לאמת את זהות השרת."
            )
            color = DANGER_COLOR
        else:
            self.mode_label.setText("מאגר האישורים של Windows")
            self.status_label.setText(
                "אימות HTTPS פעיל · החיבור עבר את הבדיקה האחרונה"
                if completed
                else "אימות HTTPS פעיל · האפשרות המומלצת לרשת מסוננת"
            )
            self.trust_detail_label.setText(
                "מקור האמון: מאגר האישורים המקומי של Windows, כולל תעודות סינון "
                "שמותקנות במערכת."
            )
            color = ACCENT_SECONDARY_COLOR
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: 12px; font-weight: 800; background: transparent;"
        )
        self.trust_detail_label.setStyleSheet(
            f"color: {MUTED_TEXT_COLOR}; font-size: 11px; background: transparent;"
        )
        self._update_expand_button()

    def _update_expand_button(self):
        self.configure_btn.setText(
            "ביטול" if self._editor_expanded else "הגדר"
        )
        icon = themed_icon(
            "message_collapse_arrow",
            "agent_process_chevron",
            "agent_tool_row_chevron",
        )
        if not icon.isNull():
            self.configure_btn.setIcon(icon)
            self.configure_btn.setIconSize(QSize(17, 17))

    def toggle_editor(self):
        self.set_expanded(not self._editor_expanded)

    def open_setup(self):
        """Compatibility entrypoint used by older callers and tests."""
        self.set_expanded(True)

    def set_expanded(self, expanded):
        expanded = bool(expanded)
        if expanded and not self._editor_expanded:
            self._load_editor_from_values()
        self._editor_expanded = expanded
        self.editor.setVisible(expanded)
        self._update_expand_button()
        self.updateGeometry()

    def is_expanded(self):
        return self._editor_expanded

    def _on_mode_changed(self, index):
        index = max(0, min(int(index), self.mode_stack.count() - 1))
        self.mode_stack.setCurrentIndex(index)
        self._pending_test_completed = False
        if self._current_mode() == SSL_MODE_LEGACY_INSECURE:
            message = "במצב ללא אימות, הבדיקה יכולה לאשר קישוריות בלבד — לא את זהות השרת."
        else:
            message = "הבדיקה תאשר ש-Smarti מצליח לזהות את שרשרת האישורים של השרת."
        self._set_test_status(message)

    def _choose_custom_ca(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "בחירת תעודת שורש ציבורית של ספק הסינון",
            os.path.expanduser("~"),
            "Certificates (*.pem *.crt *.cer);;All files (*)",
        )
        if not path:
            return
        try:
            managed_path = import_custom_ca(path, USER_DATA_DIR)
            ok, message = validate_custom_ca(managed_path)
            if not ok:
                raise ValueError(message)
            self.custom_ca_path.setText(managed_path)
            self._show_certificate_selection(managed_path, message)
            self._pending_test_completed = False
        except Exception as exc:
            self.custom_ca_path.clear()
            self._pending_test_completed = False
            self.custom_ca_status.setText(f"לא ניתן לייבא את התעודה: {exc}")
            self.custom_ca_status.setStyleSheet(
                f"color: {DANGER_COLOR}; font-size: 12px; font-weight: 800; background: transparent;"
            )

    def _pending_settings(self):
        mode = self._current_mode()
        return {
            "ssl_trust_mode": mode,
            "ssl_custom_ca_path": self.custom_ca_path.text().strip(),
            "ssl_filter_setup_completed": bool(self._pending_test_completed),
            "ssl_legacy_insecure_allowed_hosts": [],
            "ssl_trust_migration_version": SSL_TRUST_MIGRATION_VERSION,
            "allow_insecure_ssl_compat": mode == SSL_MODE_LEGACY_INSECURE,
            "_ssl_data_dir": USER_DATA_DIR,
        }

    def _run_test(self):
        # A non-None reference means one worker is still owned by the
        # QApplication. We never call into a QThread after deleteLater().
        if self._test_worker is not None:
            return
        settings = self._pending_settings()
        if settings["ssl_trust_mode"] == SSL_MODE_CUSTOM_CA:
            ok, message = validate_custom_ca(settings["ssl_custom_ca_path"])
            self._show_certificate_selection(settings["ssl_custom_ca_path"], message)
            if not ok:
                return
        if (
            settings["ssl_trust_mode"] == SSL_MODE_LEGACY_INSECURE
            and not self.compat_ack.isChecked()
        ):
            self._set_test_status(
                "יש לאשר תחילה שהמשמעות של חיבור ללא אימות תעודות ברורה.",
                "danger",
            )
            return
        self.test_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.configure_btn.setEnabled(False)
        self._set_test_status("בודק את החיבור ברקע…", "accent")
        worker = SSLTrustTestWorker(
            settings,
            "https://www.gstatic.com/generate_204",
            parent=QApplication.instance(),
        )
        self._test_worker = worker
        worker.finished_signal.connect(self._on_test_finished)
        worker.finished.connect(lambda current=worker: self._release_test_worker(current))
        worker.start()

    def _release_test_worker(self, worker):
        if self._test_worker is worker:
            self._test_worker = None
        worker.deleteLater()

    def _on_test_finished(self, ok, result, error):
        self.test_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.configure_btn.setEnabled(True)
        if not ok:
            self._pending_test_completed = False
            self._set_test_status(
                "הבדיקה נכשלה ולא בוצע מעבר אוטומטי למצב פחות בטוח: "
                + str(error or "שגיאה לא ידועה"),
                "danger",
            )
            return
        verified = bool((result or {}).get("verified"))
        self._pending_test_completed = verified
        if verified:
            self._set_test_status(
                f"החיבור אומת בהצלחה מול {(result or {}).get('host', '')} "
                f"(HTTP {(result or {}).get('status_code', '')}).",
                "accent",
            )
        else:
            self._set_test_status(
                "הקישוריות הצליחה, אך זהות השרת לא אומתה בגלל הבחירה במצב ללא אימות.",
                "danger",
            )

    def _cancel_editor(self):
        self._load_editor_from_values()
        self.set_expanded(False)

    def _save_editor(self):
        values = self._pending_settings()
        mode = values["ssl_trust_mode"]
        if mode == SSL_MODE_CUSTOM_CA:
            ok, message = validate_custom_ca(values["ssl_custom_ca_path"])
            self._show_certificate_selection(values["ssl_custom_ca_path"], message)
            if not ok:
                return
        if mode == SSL_MODE_LEGACY_INSECURE:
            if not self.compat_ack.isChecked():
                QMessageBox.warning(
                    self,
                    "נדרש אישור",
                    "יש לאשר שהמשמעות של כיבוי אימות תעודות HTTPS ברורה.",
                )
                return
            answer = QMessageBox.question(
                self,
                "הפעלת תאימות ללא אימות תעודות",
                "הבחירה מכבה באופן רחב את אימות תעודות HTTPS ב-Smarti ובכלים "
                "שמופעלים ממנו. להחיל את המצב הפחות בטוח?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.apply_values(values)
        self.set_expanded(False)

    def settings_values(self):
        return copy.deepcopy(self._values)

    def ssl_snapshot(self):
        snapshot = self.settings_values()
        snapshot["_ssl_data_dir"] = USER_DATA_DIR
        snapshot["_ssl_legacy_insecure_session_enabled"] = (
            normalize_ssl_trust_mode(snapshot.get("ssl_trust_mode"))
            == SSL_MODE_LEGACY_INSECURE
        )
        snapshot["_ssl_last_certificate_error"] = str(
            getattr(self.core, "_ssl_last_certificate_error", "") or ""
        )
        return snapshot

    def apply_values(self, values, *, legacy_session_enabled=False, emit=True):
        values = values if isinstance(values, dict) else {}
        mode = normalize_ssl_trust_mode(values.get("ssl_trust_mode"))
        self._values.update({
            "ssl_trust_mode": mode,
            "ssl_custom_ca_path": str(values.get("ssl_custom_ca_path") or "").strip(),
            "ssl_filter_setup_completed": bool(values.get("ssl_filter_setup_completed", False)),
            "ssl_legacy_insecure_allowed_hosts": [],
            "ssl_trust_migration_version": SSL_TRUST_MIGRATION_VERSION,
            "allow_insecure_ssl_compat": mode == SSL_MODE_LEGACY_INSECURE,
        })
        self.core._ssl_legacy_insecure_session_enabled = (
            mode == SSL_MODE_LEGACY_INSECURE
        )
        self._pending_test_completed = bool(
            self._values.get("ssl_filter_setup_completed", False)
        )
        self._refresh_summary()
        if emit:
            self.settingsChanged.emit()

    def apply_theme(self):
        self.setStyleSheet(
            f"""
            QFrame#SSLTrustSettingsCard {{
                background: {GLASS_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 18px;
            }}
            QFrame#SSLTrustInlineEditor {{
                background: {PANEL_ELEVATED_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 16px;
            }}
            QFrame#SSLTrustModePage, QFrame#SSLTrustTestCard {{
                background: {GLASS_STRONG_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 14px;
            }}
            """
        )
        self.current_badge.setStyleSheet(
            f"color: {ACCENT_SECONDARY_COLOR}; background: {ACCENT_TINT}; "
            "border-radius: 9px; padding: 4px 8px; font-size: 10px; font-weight: 900;"
        )
        self.mode_label.setStyleSheet(
            f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 900; background: transparent;"
        )
        for label in self.findChildren(QLabel):
            if label.property("smartiSSLModeTitle"):
                label.setStyleSheet(
                    f"color: {TEXT_COLOR}; font-size: 13px; font-weight: 900; background: transparent;"
                )
            elif label.property("smartiSSLModeBody"):
                label.setStyleSheet(
                    f"color: {MUTED_TEXT_COLOR}; font-size: 12px; background: transparent;"
                )
            elif label.property("smartiSSLSafeBadge"):
                label.setStyleSheet(
                    f"color: {ACCENT_SECONDARY_COLOR}; background: {ACCENT_TINT}; "
                    "border-radius: 10px; padding: 7px 9px; font-size: 11px; font-weight: 800;"
                )
            elif label.property("smartiSSLWarning"):
                label.setStyleSheet(
                    f"color: {DANGER_COLOR}; background: rgba(240,90,110,0.10); "
                    "border-radius: 10px; padding: 8px 9px; font-size: 11px; font-weight: 800;"
                )
        editor_title = self.findChild(QLabel, "SSLTrustEditorTitle")
        if editor_title:
            editor_title.setStyleSheet(
                f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 900; background: transparent;"
            )
        editor_help = self.findChild(QLabel, "SSLTrustEditorHelp")
        if editor_help:
            editor_help.setStyleSheet(
                f"color: {MUTED_TEXT_COLOR}; font-size: 12px; background: transparent;"
            )
        self.test_title.setStyleSheet(
            f"color: {TEXT_COLOR}; font-size: 13px; font-weight: 900; background: transparent;"
        )
        self.test_explanation.setStyleSheet(
            f"color: {MUTED_TEXT_COLOR}; font-size: 11px; background: transparent;"
        )
        self._apply_test_status_style()
        self.test_endpoint.setStyleSheet(
            f"color: {TEXT_COLOR}; background: {FIELD_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 10px; padding: 6px 8px; font-size: 11px;"
        )
        self.custom_ca_path.setStyleSheet(LINE_EDIT_CSS)
        self.configure_btn.setStyleSheet(doctor_action_button_css(primary=False))
        self.browse_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        self.test_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        self.cancel_btn.setStyleSheet(doctor_action_button_css(primary=False))
        self.save_btn.setStyleSheet(doctor_action_button_css(primary=True))
        self.compat_ack.setStyleSheet(CHECKBOX_CSS)
        self.mode_control.apply_theme()
        self._refresh_summary()


class SettingsPage(QWidget):
    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self._suppress_autosave = True
        self._settings_ready = False
        self._suppress_search = False
        self._settings_search_entries = []
        self._settings_entry_by_id = {}
        self._settings_field_containers = {}
        self._advanced_field_containers = []
        self._checkbox_info_buttons = {}
        self._info_popup = None
        self._last_settings_page_before_search = None
        self._settings_search_generation = 0
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
        self.tts_preview_worker = None
        self.email_test_worker = None
        self._save_status_angle = 0
        self._api_key_validation_generation = 0
        self._validated_api_keys = set()
        self.save_status_spin_timer = QTimer(self)
        self.save_status_spin_timer.setInterval(70)
        self.save_status_spin_timer.timeout.connect(self._spin_save_status_icon)
        
        top_bar = QHBoxLayout()
        self.back_btn = create_back_button(self.handle_back)
        top_bar.addWidget(self.back_btn)
        title = QLabel("הגדרות")
        self.settings_title = title
        title.setStyleSheet(page_title_css(20))
        top_bar.addWidget(title)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        header_controls = QWidget(self)
        header_controls.setStyleSheet("background: transparent;")
        header_controls.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        header_row = QHBoxLayout(header_controls)
        header_row.setContentsMargins(0, 0, 18, 2)
        header_row.setSpacing(0)
        self._build_save_status_widget(header_row)
        header_row.addStretch()
        self._build_advanced_toggle(header_row)
        layout.addWidget(header_controls)
        self._build_settings_toolbar(layout)
        
        self._init_widgets()
        self.settings_stack = AnimatedStackedWidget()
        self.settings_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._build_ui_sections()
        self._build_settings_search_index()
        self._apply_advanced_visibility()
        self.settings_stack.currentChanged.connect(self._on_settings_section_changed)
        layout.addWidget(self.settings_stack)
        
        self.fetch_worker = None
        self.models_loaded = False
        current_provider = normalize_provider_name(self.provider_combo.currentText())
        self.populate_models([self.core.settings.get(f"selected_{current_provider}_model", "")], current_provider)
        self._register_autosave_handlers()
        self._suppress_autosave = False
        QTimer.singleShot(0, self._mark_settings_ready)

    def _mark_settings_ready(self):
        self._settings_ready = True
        self._set_save_status("idle")

    def handle_back(self):
        if hasattr(self, "settings_stack") and self.settings_stack.currentWidget() is not self.settings_home_page:
            current = self.settings_stack.currentWidget()
            target = getattr(self, "_settings_back_targets", {}).get(current, self.settings_home_page)
            self.settings_stack.setCurrentWidget(target)
            self._reset_scrolls_in_widget(target)
        else:
            self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)

    def show_home(self):
        if hasattr(self, "settings_stack") and hasattr(self, "settings_home_page"):
            if hasattr(self, "settings_search_edit"):
                self._suppress_search = True
                self.settings_search_edit.clear()
                self._suppress_search = False
                self._clear_search_results()
            self.settings_stack.setCurrentWidget(self.settings_home_page)
            self._reset_scrolls_in_widget(self.settings_home_page)

    def set_management_embedded(self, embedded=True):
        """Remove the nested-page chrome when hosted by ManagementCenterPage."""
        embedded = bool(embedded)
        self.back_btn.setVisible(not embedded)
        self.settings_title.setVisible(not embedded)
        margins = 0 if embedded else 20
        self.layout().setContentsMargins(margins, 8 if embedded else margins, margins, margins)

    def show_management_section(self, key):
        target = getattr(self, "_management_section_pages", {}).get(str(key or ""))
        if target is None:
            target = getattr(self, "settings_home_page", None)
        self._set_settings_section(target)

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

    def _settings_toolbar_css(self):
        return f"""
            QFrame#SettingsToolbar {{
                background: transparent;
                border: none;
            }}
        """

    def _search_box_css(self):
        return f"""
            QLineEdit#SettingsSearchBox {{
                background: transparent;
                color: {FIELD_TEXT_COLOR};
                border: none;
                padding: 13px 4px 13px 10px;
                font-size: 14px;
                selection-background-color: {ACCENT_TINT_STRONG};
                selection-color: {TEXT_COLOR};
            }}
        """

    def _search_wrapper_css(self, focused=False):
        border = LINE_COLOR if focused else SOFT_LINE_COLOR
        background = FIELD_HOVER_COLOR if focused else GLASS_COLOR
        return f"""
            QFrame#SettingsSearchWrapper {{
                background: {background};
                border: 1px solid {border};
                border-radius: 20px;
            }}
        """

    def _advanced_toggle_css(self):
        return f"""
            QFrame#AdvancedTogglePill {{
                background: {GLASS_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 20px;
            }}
            QFrame#AdvancedTogglePill:hover {{
                background: {FIELD_HOVER_COLOR};
                border-color: {LINE_COLOR};
            }}
        """

    def _small_tool_button_css(self):
        return f"""
            QPushButton {{
                background-color: {ACCENT_TINT};
                color: {TEXT_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 16px;
                padding: 7px 10px;
                font-size: 12px;
                font-weight: 700;
                outline: none;
            }}
            QPushButton:hover {{ background-color: {HOVER_TINT}; border-color: {LINE_COLOR}; }}
            QPushButton:pressed {{ background-color: {ACCENT_TINT_STRONG}; border-color: {ACCENT_PINK_COLOR}; }}
        """

    def _field_container_css(self, highlighted=False):
        border = ACCENT_COLOR if highlighted else "transparent"
        background = ACCENT_TINT if highlighted else "transparent"
        return f"""
            QFrame#SettingsFieldContainer {{
                background: {background};
                border: 1px solid {border};
                border-radius: 16px;
            }}
        """

    def _build_settings_toolbar(self, parent_layout):
        toolbar = QFrame(self)
        toolbar.setObjectName("SettingsToolbar")
        toolbar.setStyleSheet(self._settings_toolbar_css())
        toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(0, 4, 0, 8)
        row.setSpacing(8)

        self.settings_search_wrapper = QFrame()
        self.settings_search_wrapper.setObjectName("SettingsSearchWrapper")
        self.settings_search_wrapper.setStyleSheet(self._search_wrapper_css(False))
        self.settings_search_wrapper.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        search_layout = QHBoxLayout(self.settings_search_wrapper)
        search_layout.setContentsMargins(14, 0, 12, 0)
        search_layout.setSpacing(8)
        self.settings_search_icon = QLabel()
        self.settings_search_icon.setFixedSize(30, 30)
        self.settings_search_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        set_themed_label_icon(self.settings_search_icon, ("search_icon",), "⌕", 26)
        search_layout.addWidget(self.settings_search_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        self.settings_search_edit = QLineEdit()
        self.settings_search_edit.setObjectName("SettingsSearchBox")
        self.settings_search_edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.settings_search_edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.settings_search_edit.setCursorMoveStyle(Qt.CursorMoveStyle.VisualMoveStyle)
        self.settings_search_edit.setPlaceholderText("חפש הגדרה")
        self.settings_search_edit.setClearButtonEnabled(True)
        self.settings_search_edit.setStyleSheet(self._search_box_css())
        self.settings_search_edit.installEventFilter(self)
        self.settings_search_edit.textChanged.connect(self._on_settings_search_changed)
        self.settings_search_edit.returnPressed.connect(self._activate_first_search_result)
        search_layout.addWidget(self.settings_search_edit, 1, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.settings_search_wrapper, 1)
        self._ensure_recent_search_popup()
        parent_layout.addWidget(toolbar)

    def _build_advanced_toggle(self, target_layout):
        self.advanced_toggle_widget = QFrame()
        self.advanced_toggle_widget.setObjectName("AdvancedTogglePill")
        self.advanced_toggle_widget.setStyleSheet(self._advanced_toggle_css())
        self.advanced_toggle_widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.advanced_toggle_widget.setFixedHeight(40)
        self.advanced_toggle_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self.advanced_toggle_widget)
        row.setContentsMargins(10, 0, 8, 0)
        row.setSpacing(6)
        label = QLabel("הצג הגדרות מתקדמות")
        label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; background: transparent;")
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.show_advanced_cb = SmartiCheckBox("")
        self.show_advanced_cb.setStyleSheet(CHECKBOX_CSS)
        self.show_advanced_cb.setFixedSize(56, 38)
        self.show_advanced_cb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.show_advanced_cb.setToolTip(self._tooltip_markup("מציג שדות טכניים כמו פורטים, SSL, מגבלות זמן, לוגים ומטריצת הרשאות."))
        self.show_advanced_cb.setChecked(bool(self.core.settings.get("ui_preferences", {}).get("settings_show_advanced", False)))
        self.show_advanced_cb.stateChanged.connect(self._on_advanced_visibility_changed)
        row.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.show_advanced_cb, 0, Qt.AlignmentFlag.AlignVCenter)
        target_layout.addWidget(self.advanced_toggle_widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def _build_save_status_widget(self, target_layout):
        self.save_status_widget = QWidget()
        self.save_status_widget.setStyleSheet("background: transparent;")
        self.save_status_widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.save_status_widget.setFixedHeight(40)
        self.save_status_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self.save_status_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.settings_save_icon = QLabel()
        self.settings_save_icon.setFixedSize(20, 20)
        self.settings_save_status = QLabel("אין שינויים חדשים")
        self.settings_save_status.setStyleSheet(muted_label_css(12))
        self.settings_save_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.settings_save_status.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row.addWidget(self.settings_save_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.settings_save_status, 0, Qt.AlignmentFlag.AlignVCenter)
        target_layout.addWidget(self.save_status_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        self._set_save_status("idle")

    def _save_status_icon_pixmap(self, status):
        if status == "saving":
            icon = themed_icon("check_updates_icon", "update_icon", "refresh_icon", "reset_icon")
        elif status == "saved":
            icon = themed_icon("save_done", "save_done_icon", "saved_icon", "checkmark_icon", CHECKMARK_SVG_PATH)
        else:
            icon = themed_icon("save_done", "save_idle_icon", "saved_icon", "checkmark_icon", CHECKMARK_SVG_PATH)
        return icon.pixmap(18, 18) if not icon.isNull() else QPixmap()

    def _pixmap_alpha_center(self, pixmap):
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        left, top = image.width(), image.height()
        right, bottom = -1, -1
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() <= 8:
                    continue
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)
        if right < left or bottom < top:
            return pixmap.width() / 2, pixmap.height() / 2
        return (left + right + 1) / 2, (top + bottom + 1) / 2

    def _save_status_icon_canvas(self, pixmap, angle=0):
        if pixmap.isNull():
            return QPixmap()
        base = pixmap.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        visual_x, visual_y = self._pixmap_alpha_center(base)
        canvas = QPixmap(20, 20)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(canvas.width() / 2, canvas.height() / 2)
        if angle:
            painter.rotate(float(angle))
        painter.drawPixmap(QRectF(-visual_x, -visual_y, base.width(), base.height()), base, QRectF(base.rect()))
        painter.end()
        return canvas

    def _set_save_status(self, status):
        if not hasattr(self, "settings_save_status"):
            return
        if hasattr(self, "_save_status_reset_timer"):
            self._save_status_reset_timer.stop()
        status = str(status or "idle")
        self._save_status = status
        if status == "saving":
            self.settings_save_status.setText("שומר שינויים...")
            self.settings_save_status.setStyleSheet(muted_label_css(12))
            self._save_status_base_pixmap = self._save_status_icon_pixmap("saving")
            self._save_status_angle = 0
            if not self._save_status_base_pixmap.isNull():
                self.settings_save_icon.setPixmap(self._save_status_icon_canvas(self._save_status_base_pixmap))
            self.save_status_spin_timer.start()
            return
        self.save_status_spin_timer.stop()
        if status == "saved":
            self.settings_save_status.setText("השינויים נשמרו!")
            self.settings_save_status.setStyleSheet(f"color: {ACCENT_SECONDARY_COLOR}; font-size: 12px; background: transparent;")
            pixmap = self._save_status_icon_pixmap("saved")
            if not pixmap.isNull():
                self.settings_save_icon.setPixmap(pixmap)
            self._save_status_reset_timer = QTimer(self)
            self._save_status_reset_timer.setSingleShot(True)
            self._save_status_reset_timer.timeout.connect(lambda: self._set_save_status("idle"))
            self._save_status_reset_timer.start(3000)
            return
        self.settings_save_status.setText("אין שינויים חדשים")
        self.settings_save_status.setStyleSheet(muted_label_css(12))
        pixmap = self._save_status_icon_pixmap("idle")
        if not pixmap.isNull():
            self.settings_save_icon.setPixmap(pixmap)
        else:
            self.settings_save_icon.clear()

    def _spin_save_status_icon(self):
        pixmap = getattr(self, "_save_status_base_pixmap", QPixmap())
        if pixmap.isNull() or not hasattr(self, "settings_save_icon"):
            return
        self._save_status_angle = (int(getattr(self, "_save_status_angle", 0)) + 30) % 360
        self.settings_save_icon.setPixmap(self._save_status_icon_canvas(pixmap, self._save_status_angle))

    def _make_info_button(self, text):
        btn = QPushButton("i")
        btn.setProperty("smartiInfoButton", True)
        btn.setProperty("smartiInfoText", str(text or "").strip())
        btn.setFixedSize(24, 24)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip("")
        btn.installEventFilter(self)
        btn.clicked.connect(lambda checked=False, b=btn: self._show_info_popup(b))
        btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT_TINT}; color: {ACCENT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 12px; padding: 0px; font-size: 12px; font-weight: 900; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; border-color: {LINE_COLOR}; color: {TEXT_COLOR}; }}"
        )
        return btn

    def _tooltip_markup(self, text, width=280):
        safe = html.escape(str(text or "").strip())
        if not safe:
            return ""
        return f"<div dir='rtl' style='white-space: normal; max-width: {int(width)}px;'>{safe}</div>"

    def _ensure_info_popup(self):
        if self._info_popup:
            return
        popup = QFrame(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        popup.setObjectName("SettingsInfoPopup")
        popup.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        popup.setStyleSheet(
            f"QFrame#SettingsInfoPopup {{ background: {MENU_BG_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 0px; padding: 0px; }}"
        )
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(14, 11, 14, 11)
        self._info_popup_label = QLabel()
        self._info_popup_label.setWordWrap(True)
        self._info_popup_label.setMaximumWidth(320)
        self._info_popup_label.setContentsMargins(0, 0, 0, 0)
        self._info_popup_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        self._info_popup_label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px; line-height: 1.35; background: transparent;")
        layout.addWidget(self._info_popup_label)
        self._info_popup = popup

    def _show_info_popup(self, button):
        text = str(button.property("smartiInfoText") or "").strip()
        if not text:
            return
        self._ensure_info_popup()
        self._info_popup_label.setText(text)
        natural_width = QFontMetrics(self._info_popup_label.font()).horizontalAdvance(text) + 6
        label_width = max(96, min(320, natural_width))
        wrapped_rect = QFontMetrics(self._info_popup_label.font()).boundingRect(
            QRect(0, 0, int(label_width), 10_000),
            Qt.TextFlag.TextWordWrap,
            text,
        )
        label_height = max(18, wrapped_rect.height() + 4)
        self._info_popup_label.setMinimumSize(0, 0)
        self._info_popup_label.setMaximumWidth(int(label_width))
        self._info_popup_label.resize(int(label_width), int(label_height))
        margins = self._info_popup.layout().contentsMargins()
        self._info_popup.resize(
            int(label_width + margins.left() + margins.right()),
            int(label_height + margins.top() + margins.bottom()),
        )
        pos = button.mapToGlobal(QPoint(button.width() - self._info_popup.width(), button.height() + 6))
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            window_rect = self.window().frameGeometry().adjusted(8, 8, -8, -8)
            if window_rect.isValid() and window_rect.width() > 80 and window_rect.height() > 80:
                available = available.intersected(window_rect)
            if pos.y() + self._info_popup.height() > available.bottom():
                pos = button.mapToGlobal(QPoint(button.width() - self._info_popup.width(), -self._info_popup.height() - 6))
            pos.setX(max(available.left(), min(pos.x(), available.right() - self._info_popup.width())))
            pos.setY(max(available.top(), min(pos.y(), available.bottom() - self._info_popup.height())))
        self._info_popup.move(pos)
        self._info_popup.show()

    def _hide_info_popup(self):
        if self._info_popup:
            self._info_popup.hide()

    def _attach_checkbox_info_button(self, widget, hint):
        if not isinstance(widget, SmartiCheckBox):
            return None
        btn = self._make_info_button(hint)
        btn.setParent(widget)
        btn.raise_()
        widget.setInfoButtonReserved(True)
        widget.installEventFilter(self)
        self._checkbox_info_buttons[widget] = btn
        self._position_checkbox_info_button(widget)
        return btn

    def _position_checkbox_info_button(self, widget):
        btn = self._checkbox_info_buttons.get(widget)
        if not btn:
            return
        text_width = widget.fontMetrics().horizontalAdvance(widget.text())
        x = max(58, widget.width() - text_width - btn.width() - 10)
        x = min(x, max(0, widget.width() - btn.width()))
        y = max(0, int((widget.height() - btn.height()) / 2))
        btn.move(x, y)
        btn.raise_()

    def _setting_entry_id(self, label_text, widget):
        raw = str(label_text or widget.objectName() or widget.__class__.__name__)
        slug = re.sub(r"[^0-9A-Za-zא-ת_]+", "_", raw).strip("_") or f"setting_{len(self._settings_search_entries) + 1}"
        candidate = slug
        counter = 2
        while candidate in self._settings_entry_by_id:
            candidate = f"{slug}_{counter}"
            counter += 1
        return candidate

    def _normalize_settings_search_text(self, text):
        text = unicodedata.normalize("NFKD", str(text or "")).lower()
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.translate(str.maketrans({
            "ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ",
            "-": " ", "_": " ", "/": " ", "\\": " ", ".": " ", ",": " ",
        }))
        text = re.sub(r"[^0-9a-zא-ת]+", " ", text)
        return " ".join(text.split())

    def _expanded_search_terms(self, query):
        base_terms = self._normalize_settings_search_text(query).split()
        groups = [
            ("api", "key", "token", "secret", "מפתח", "גישה", "סוד", "ספק", "מודל"),
            ("model", "models", "llm", "ai", "מודל", "מודלים", "דגם", "בינה", "ספק", "chat"),
            ("safe", "safety", "security", "privacy", "permission", "policy", "אבטחה", "בטיחות", "הרשאה", "הרשאות", "פרטיות", "אישור", "אישורים"),
            ("autonomy", "agent", "approval", "אוטונומיה", "אוטונומי", "סוכן", "שליטה", "אישור", "עצמאי"),
            ("sandbox", "folder", "directory", "path", "files", "ארגז", "חול", "תיקיה", "תיקייה", "נתיב", "קבצים", "פלט"),
            ("mail", "email", "imap", "smtp", "port", "ssl", "דואר", "אימייל", "מייל", "שרת", "פורט", "סיסמה"),
            ("voice", "tts", "audio", "microphone", "mic", "speech", "קול", "הקראה", "שמע", "מיקרופון", "דיבור", "האזנה"),
            ("theme", "appearance", "dark", "light", "display", "תצוגה", "מראה", "כהה", "בהיר", "ערכת", "רקע"),
            ("browser", "automation", "computer", "windows", "דפדפן", "אוטומציה", "מחשב", "חלונות", "שליטה"),
            ("mcp", "skills", "extensions", "tools", "כלים", "הרחבות", "מיומנויות", "חיצוניים"),
            ("timeout", "limit", "budget", "tokens", "cost", "loops", "זמן", "המתנה", "מגבלה", "תקציב", "טוקנים", "עלות", "סבבים"),
            ("log", "trace", "audit", "developer", "debug", "לוג", "לוגים", "יומן", "אודיט", "מפתחים", "דיבאג"),
            ("update", "version", "release", "עדכון", "עדכונים", "גרסה"),
        ]
        expanded = set(base_terms)
        for term in list(base_terms):
            for group in groups:
                normalized_group = {self._normalize_settings_search_text(item) for item in group}
                if term in normalized_group:
                    expanded.update(t for t in normalized_group if t)
        return [term for term in expanded if term]

    def _register_setting_entry(self, label_text, widget, container, hint="", keywords=None, advanced=False, setting_id=""):
        if widget is None or container is None:
            return
        layout = container.parentWidget().layout() if container.parentWidget() else None
        target_page = getattr(container, "smarti_target_page", None)
        section = getattr(container, "smarti_section_title", "") or ""
        entry_id = setting_id or self._setting_entry_id(label_text, widget)
        words = [
            label_text, hint, section, entry_id,
            "מתקדם advanced expert power user טכני מומחה" if advanced else "בסיסי פשוט מתחיל beginner",
        ]
        if keywords:
            if isinstance(keywords, (list, tuple, set)):
                words.extend(str(item) for item in keywords)
            else:
                words.append(str(keywords))
        search_text = " ".join(str(part or "") for part in words)
        entry = {
            "id": entry_id,
            "title": str(label_text or "").strip(),
            "hint": str(hint or "").strip(),
            "section": section,
            "target_page": target_page,
            "widget": widget,
            "container": container,
            "advanced": bool(advanced),
            "search_text": search_text,
            "search_text_norm": self._normalize_settings_search_text(search_text),
        }
        self._settings_search_entries.append(entry)
        self._settings_entry_by_id[entry_id] = entry
        self._settings_field_containers[entry_id] = container
        widget.setProperty("smartiSettingsEntryId", entry_id)
        container.setProperty("smartiSettingsEntryId", entry_id)
        if advanced:
            container.setProperty("smartiAdvancedSetting", True)
            self._advanced_field_containers.append(container)

    def _score_settings_entry(self, query, entry):
        query_norm = self._normalize_settings_search_text(query)
        if not query_norm:
            return 0
        text = entry.get("search_text_norm", "")
        title = self._normalize_settings_search_text(entry.get("title", ""))
        hint = self._normalize_settings_search_text(entry.get("hint", ""))
        score = 0
        if query_norm in title:
            score += 80
        elif query_norm in text:
            score += 44
        terms = self._expanded_search_terms(query)
        text_tokens = text.split()
        for term in terms:
            if not term:
                continue
            if term in title:
                score += 22
            elif term in hint:
                score += 13
            elif term in text:
                score += 10
            elif text_tokens:
                best = max((difflib.SequenceMatcher(None, term, token).ratio() for token in text_tokens), default=0)
                if best >= 0.82:
                    score += 7
                elif best >= 0.72 and len(term) >= 4:
                    score += 4
        if entry.get("advanced"):
            score -= 1
        return score

    def _build_settings_search_index(self):
        # Entries are registered while the fields are built. This method keeps the hook explicit
        # and leaves room for future generated/indexed settings without changing the UI builders.
        for entry in self._settings_search_entries:
            entry["search_text_norm"] = self._normalize_settings_search_text(entry.get("search_text", ""))

    def _on_settings_search_changed(self, text):
        if getattr(self, "_suppress_search", False) or not hasattr(self, "settings_stack"):
            return
        query = str(text or "").strip()
        if not query:
            if self.settings_stack.currentWidget() is getattr(self, "search_results_page", None):
                self.settings_stack.setCurrentWidget(self._last_settings_page_before_search or self.settings_home_page)
            self._clear_search_results()
            return
        if self.settings_stack.currentWidget() is not getattr(self, "search_results_page", None):
            self._last_settings_page_before_search = self.settings_stack.currentWidget()
        self._render_search_results(query)
        self.settings_stack.setCurrentWidget(self.search_results_page)

    def _clear_search_results(self):
        if hasattr(self, "search_results_list"):
            self.search_results_list.clear()
        if hasattr(self, "search_results_hint"):
            self.search_results_hint.setText("")

    def _render_search_results(self, query):
        if not hasattr(self, "search_results_list"):
            return
        self.search_results_list.clear()
        scored = []
        for entry in self._settings_search_entries:
            if (
                entry.get("id") == "local_fast_mode_enabled"
                and normalize_provider_name(self.provider_combo.currentText()) != "local"
            ):
                continue
            score = self._score_settings_entry(query, entry)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].get("section", ""), item[1].get("title", "")))
        if not scored:
            self.search_results_hint.setText("לא נמצאו הגדרות. נסה מילה קרובה כמו מודל, קול, אימייל, אבטחה או תיקייה.")
            return
        self.search_results_hint.setText(f"נמצאו {len(scored)} תוצאות. לחיצה תפתח ותסמן את ההגדרה.")
        for score, entry in scored[:40]:
            title = entry.get("title") or "הגדרה"
            section = entry.get("section") or "הגדרות"
            badge = "  ·  מתקדם" if entry.get("advanced") else ""
            item = QListWidgetItem("")
            item.setData(Qt.ItemDataRole.UserRole, entry.get("id"))
            item.setSizeHint(QSize(10, 58))
            self.search_results_list.addItem(item)
            self.search_results_list.setItemWidget(item, self._make_search_result_widget(title, section + badge))

    def _make_search_result_widget(self, title, section):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(3)
        title_lbl = QLabel(str(title or ""))
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute)
        title_lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 400; background: transparent;")
        section_lbl = QLabel(str(section or ""))
        section_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignAbsolute)
        section_lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px; background: transparent;")
        layout.addWidget(title_lbl)
        layout.addWidget(section_lbl)
        return row

    def _activate_first_search_result(self):
        if not hasattr(self, "search_results_list"):
            return
        if self.search_results_list.count() <= 0:
            return
        self._activate_search_result(self.search_results_list.item(0))

    def _activate_search_result(self, item):
        if item is None:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        entry = self._settings_entry_by_id.get(entry_id)
        if not entry:
            return
        if (
            entry.get("id") == "local_fast_mode_enabled"
            and normalize_provider_name(self.provider_combo.currentText()) != "local"
        ):
            return
        self._save_recent_settings_search(self.settings_search_edit.text())
        if entry.get("advanced") and not self._advanced_settings_visible():
            self.show_advanced_cb.setChecked(True)
        target_page = entry.get("target_page") or self.settings_home_page
        self.settings_stack.setCurrentWidget(target_page)
        self._reset_scrolls_in_widget(target_page)
        QTimer.singleShot(80, lambda e=entry: self._scroll_to_and_highlight_setting(e))

    def _scroll_to_and_highlight_setting(self, entry):
        container = entry.get("container")
        if not container:
            return
        for area in entry.get("target_page", self).findChildren(QScrollArea):
            try:
                area.ensureWidgetVisible(container, 30, 40)
            except Exception:
                pass
        self._highlight_setting_container(container)

    def _highlight_setting_container(self, container):
        if container is None:
            return
        self._settings_search_generation += 1
        generation = self._settings_search_generation
        container.setStyleSheet(self._field_container_css(highlighted=True))
        def restore():
            if generation == self._settings_search_generation and container:
                container.setStyleSheet(self._field_container_css(False))
        QTimer.singleShot(1700, restore)

    def _recent_settings_searches(self):
        values = self.core.settings.get("settings_recent_searches", [])
        if not isinstance(values, list):
            return []
        cleaned = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned[:10]

    def _save_recent_settings_search(self, query):
        query = str(query or "").strip()
        if not query:
            return
        current = [item for item in self._recent_settings_searches() if item != query]
        self.core.settings["settings_recent_searches"] = [query] + current[:9]
        self.core._save_settings()

    def _show_recent_search_menu(self):
        return

    def _ensure_recent_search_popup(self):
        if getattr(self, "recent_search_popup", None):
            return
        popup = QFrame(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        popup.setObjectName("SettingsRecentSearchPopup")
        popup.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        try:
            popup.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        except Exception:
            pass
        popup.setStyleSheet(
            f"QFrame#SettingsRecentSearchPopup {{ background: {MENU_BG_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 0px; padding: 6px; }}"
        )
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(0)
        self.recent_search_list = QListWidget()
        self.recent_search_list.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.recent_search_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.recent_search_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.recent_search_list.setStyleSheet(
            f"QListWidget {{ background: transparent; color: {TEXT_COLOR}; border: none; outline: none; }}"
            f"QListWidget::item {{ min-height: 28px; padding: 7px 10px; border-radius: 0px; }}"
            f"QListWidget::item:hover {{ background: {HOVER_TINT}; }}"
            f"QListWidget::item:selected {{ background: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR}; }}"
        )
        self.recent_search_list.itemClicked.connect(lambda item: self._apply_recent_search(item.text()))
        layout.addWidget(self.recent_search_list)
        popup.installEventFilter(self)
        self.recent_search_popup = popup

    def _apply_recent_search(self, query):
        self.settings_search_edit.setText(str(query or ""))
        self.settings_search_edit.setFocus()
        self._hide_recent_search_popup()

    def _filtered_recent_searches(self):
        query = self._normalize_settings_search_text(self.settings_search_edit.text())
        searches = self._recent_settings_searches()
        if not query:
            return searches
        return [item for item in searches if query in self._normalize_settings_search_text(item)]

    def _show_recent_search_popup(self):
        return
        self._ensure_recent_search_popup()
        searches = self._filtered_recent_searches()
        self.recent_search_list.clear()
        if not searches:
            self._hide_recent_search_popup()
            return
        for query in searches:
            self.recent_search_list.addItem(QListWidgetItem(query))
        row_h = self.recent_search_list.sizeHintForRow(0)
        row_h = row_h if row_h > 0 else 34
        height = min(260, max(42, row_h * min(len(searches), 8) + 18))
        width = max(280, self.settings_search_wrapper.width())
        self.recent_search_list.setFixedHeight(height)
        self.recent_search_popup.setFixedWidth(width)
        self.recent_search_popup.adjustSize()
        pos = self.settings_search_wrapper.mapToGlobal(QPoint(0, self.settings_search_wrapper.height() + 4))
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            window_rect = self.window().frameGeometry().adjusted(8, 8, -8, -8)
            if window_rect.isValid() and window_rect.width() > 80 and window_rect.height() > 80:
                available = available.intersected(window_rect)
            if pos.x() + width > available.right():
                pos.setX(max(available.left(), available.right() - width))
            if pos.y() + self.recent_search_popup.height() > available.bottom():
                pos = self.settings_search_wrapper.mapToGlobal(QPoint(0, -self.recent_search_popup.height() - 4))
            pos.setX(max(available.left(), min(pos.x(), available.right() - width)))
            pos.setY(max(available.top(), min(pos.y(), available.bottom() - self.recent_search_popup.height())))
        self.recent_search_popup.move(pos)
        self.recent_search_popup.show()

    def _hide_recent_search_popup(self):
        if getattr(self, "recent_search_popup", None):
            self.recent_search_popup.hide()

    def _hide_recent_search_popup_if_stale(self):
        popup = getattr(self, "recent_search_popup", None)
        edit = getattr(self, "settings_search_edit", None)
        if not popup or not popup.isVisible():
            return
        focused = QApplication.focusWidget()
        if focused is edit or (popup.isAncestorOf(focused) if focused else False):
            return
        cursor = QCursor.pos()
        if popup.geometry().contains(cursor) or (hasattr(self, "settings_search_wrapper") and self.settings_search_wrapper.rect().contains(self.settings_search_wrapper.mapFromGlobal(cursor))):
            return
        self._hide_recent_search_popup()

    def eventFilter(self, watched, event):
        if getattr(watched, "property", lambda *_: None)("smartiInfoButton"):
            if event.type() == QEvent.Type.Enter:
                self._show_info_popup(watched)
            elif event.type() == QEvent.Type.Leave:
                QTimer.singleShot(120, self._hide_info_popup)
        if watched in getattr(self, "_checkbox_info_buttons", {}):
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
                QTimer.singleShot(0, lambda w=watched: self._position_checkbox_info_button(w))
        if watched is getattr(self, "settings_search_edit", None):
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Up:
                    self.settings_search_edit.setCursorPosition(0)
                    return True
                if event.key() == Qt.Key.Key_Down:
                    self.settings_search_edit.setCursorPosition(len(self.settings_search_edit.text()))
                    return True
            if event.type() == QEvent.Type.FocusIn:
                if hasattr(self, "settings_search_wrapper"):
                    self.settings_search_wrapper.setStyleSheet(self._search_wrapper_css(True))
            elif event.type() == QEvent.Type.FocusOut:
                if hasattr(self, "settings_search_wrapper"):
                    self.settings_search_wrapper.setStyleSheet(self._search_wrapper_css(False))
        return super().eventFilter(watched, event)

    def _advanced_settings_visible(self):
        return bool(getattr(self, "show_advanced_cb", None) and self.show_advanced_cb.isChecked())

    def _on_advanced_visibility_changed(self, _state=None):
        self.core.settings.setdefault("ui_preferences", {})["settings_show_advanced"] = self._advanced_settings_visible()
        self.core._save_settings()
        self._apply_advanced_visibility()

    def _apply_advanced_visibility(self):
        visible = self._advanced_settings_visible()
        for container in getattr(self, "_advanced_field_containers", []):
            container.setVisible(visible)
        if hasattr(self, "advanced_home_card"):
            self.advanced_home_card.setVisible(visible)
        if (
            not visible
            and hasattr(self, "settings_stack")
            and self.settings_stack.currentWidget() is getattr(self, "developer_page", None)
            and hasattr(self, "settings_home_page")
        ):
            self.settings_stack.setCurrentWidget(self.settings_home_page)

    def _paste_into_settings_edit(self, edit):
        clipboard = QApplication.clipboard()
        text = str(clipboard.text() or "") if clipboard is not None else ""
        if not text.strip():
            QMessageBox.information(self, "הדבקה", "לוח ההעתקה אינו מכיל טקסט.")
            return
        if hasattr(edit, "clear_secret"):
            edit.clear_secret()
        else:
            edit.clear()
        edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        edit.setText(text.strip())

    def _make_paste_icon_button(self, edit, tooltip="הדבק מלוח ההעתקה"):
        button = QPushButton()
        button.setProperty("smartiPasteButton", True)
        button.setFixedSize(34, 34)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        button.setToolTip(tooltip)
        set_themed_button_icon(
            button,
            ("paste_icon", "clipboard_paste_icon", "copy_icon"),
            "P",
            19,
            clear_text=True,
        )
        button.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; border-radius: 17px; padding: 0px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; border: none; }}"
            f"QPushButton:pressed {{ background: {ACCENT_TINT}; border: none; }}"
        )
        button.clicked.connect(lambda _=False, target=edit: self._paste_into_settings_edit(target))
        return button

    def _make_paste_input_row(self, edit, tooltip="הדבק מלוח ההעתקה"):
        row = QWidget(self)
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        edit.setStyleSheet(LINE_EDIT_CSS)
        edit.setMinimumWidth(0)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(edit, 1)
        layout.addWidget(self._make_paste_icon_button(edit, tooltip), 0, Qt.AlignmentFlag.AlignVCenter)
        return row

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
        layout.addWidget(self._make_paste_icon_button(edit, "הדבק מפתח מלוח ההעתקה"), 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(link_label, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _make_tts_preview_row(self):
        row = QWidget(self)
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.tts_preview_text = QLineEdit("שלום, זו תצוגה מקדימה של הקול הנוכחי.")
        self.tts_preview_text.setStyleSheet(LINE_EDIT_CSS)
        self.tts_preview_text.setMinimumWidth(0)
        self.tts_preview_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.tts_preview_btn = QPushButton("השמע")
        self.tts_preview_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.tts_preview_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        set_themed_button_icon(self.tts_preview_btn, ("speaker_icon",), "A", 18, clear_text=False)
        self.tts_preview_btn.clicked.connect(self.preview_tts)
        layout.addWidget(self.tts_preview_text, 1)
        layout.addWidget(self.tts_preview_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _make_email_test_row(self):
        row = QWidget(self)
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.email_test_status = QLabel("הבדיקה תרוץ רק בלחיצה.")
        self.email_test_status.setWordWrap(True)
        self.email_test_status.setStyleSheet(muted_label_css(12))
        self.email_test_btn = QPushButton("בדוק חיבור")
        self.email_test_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.email_test_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.email_test_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        set_themed_button_icon(self.email_test_btn, ("connection_test_icon", "check_updates_icon", "check_icon"), self.email_test_btn.text(), 18, clear_text=False)
        self.email_test_btn.clicked.connect(self.test_email_connection)
        layout.addWidget(self.email_test_status, 1)
        layout.addWidget(self.email_test_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _make_model_picker_row(self):
        row = QWidget(self)
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.model_combo.setMinimumWidth(0)
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if hasattr(self.model_combo, "set_favorite_callbacks"):
            self.model_combo.set_favorite_callbacks(
                lambda model: self._is_model_favorite(self.provider_combo.currentText(), model),
                self._toggle_model_favorite_from_picker,
            )
        layout.addWidget(self.model_combo, 1)
        return row

    def _make_codex_signin_row(self):
        row = QWidget(self)
        row.setStyleSheet("background: transparent;")
        row.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.codex_signin_status = QLabel("יש לבחור OpenAI Codex Sign-in כדי להתחבר.")
        self.codex_signin_status.setWordWrap(True)
        self.codex_signin_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.codex_signin_status.setStyleSheet(muted_label_css(12))
        self.codex_login_btn = QPushButton("התחבר עם\nChatGPT / Codex")
        self.codex_check_btn = QPushButton("בדוק\nחיבור")
        self.codex_logout_btn = QPushButton("התנתק")
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(10)
        compact_button_padding = "QPushButton { padding: 7px 8px; }"
        for button in (self.codex_login_btn, self.codex_check_btn, self.codex_logout_btn):
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setStyleSheet(SECONDARY_BUTTON_CSS + compact_button_padding)
            # The sign-in and check labels intentionally use two lines.  The
            # shared button style has generous padding, so 56px clips their
            # second line on Windows/RTL fonts.
            button.setFixedHeight(74)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.codex_login_btn.setStyleSheet(PRIMARY_BUTTON_CSS + compact_button_padding)
        self.codex_login_btn.clicked.connect(lambda: self._start_codex_signin_action("login"))
        self.codex_check_btn.clicked.connect(lambda: self._start_codex_signin_action("check"))
        self.codex_logout_btn.clicked.connect(lambda: self._start_codex_signin_action("logout"))
        buttons.addWidget(self.codex_login_btn, 1)
        buttons.addWidget(self.codex_check_btn, 1)
        buttons.addWidget(self.codex_logout_btn, 1)
        layout.addWidget(self.codex_signin_status)
        layout.addLayout(buttons)
        return row

    def _codex_provider_is_selected(self):
        return normalize_provider_name(self.provider_combo.currentText()) == "openai_codex_signin"

    def _set_codex_signin_buttons(self, busy=False):
        selected = self._codex_provider_is_selected()
        for button in (self.codex_login_btn, self.codex_check_btn, self.codex_logout_btn):
            button.setEnabled(selected and not busy)

    def _set_codex_signin_status(self, state, message):
        colors = {
            "connected": ACCENT_SECONDARY_COLOR,
            "not_connected": MUTED_TEXT_COLOR,
            "reauth_required": DANGER_COLOR,
            "unavailable": DANGER_COLOR,
        }
        self.codex_signin_status.setText(str(message or "לא ידוע מצב החיבור."))
        self.codex_signin_status.setStyleSheet(
            f"color: {colors.get(state, MUTED_TEXT_COLOR)}; font-size: 12px; background: transparent;"
        )

    def _start_codex_signin_action(self, action):
        if not self._codex_provider_is_selected():
            return
        worker = getattr(self, "codex_signin_worker", None)
        if worker and worker.isRunning():
            return
        from .workers import CodexSignInWorker

        labels = {
            "login": "פותח את ההתחברות הרשמית של Codex בדפדפן…",
            "check": "בודק חיבור מול Codex…",
            "logout": "מתנתק מ-Codex…",
            "status": "בודק את מצב החיבור…",
        }
        self._set_codex_signin_status("not_connected", labels.get(action, "בודק חיבור…"))
        self._set_codex_signin_buttons(busy=True)
        worker = CodexSignInWorker(action)
        self.codex_signin_worker = worker
        worker.finished_signal.connect(self._on_codex_signin_finished, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_codex_signin_finished(self, action, state, message):
        worker = self.sender()
        if worker is not getattr(self, "codex_signin_worker", None):
            return
        self.codex_signin_worker = None
        self._set_codex_signin_status(state, message)
        self._set_codex_signin_buttons(busy=False)
        if action == "login" and state == "connected" and self._codex_provider_is_selected():
            self.core.settings["api_mode"] = "openai_codex_signin"
            self.core._save_settings()
            self.core.system_prompt = self.core._load_system_prompt()
            self.core.setup_model()
            self._schedule_autosave()

    def _favorite_model_key(self, provider, model):
        return (normalize_provider_name(provider), str(model or "").strip())

    def _current_provider_and_model(self):
        provider = normalize_provider_name(self.provider_combo.currentText()) if hasattr(self, "provider_combo") else ""
        model = self.model_combo.selected_model() if hasattr(self.model_combo, "selected_model") else self.model_combo.currentText()
        return provider, str(model or "").strip()

    def _normalized_favorite_models(self):
        seen = set()
        favorites = []
        for item in self.core.settings.get("favorite_models", []) or []:
            if not isinstance(item, dict):
                continue
            provider = normalize_provider_name(item.get("provider", ""))
            model = str(item.get("model", "") or "").strip()
            if not provider or not model:
                continue
            key = self._favorite_model_key(provider, model)
            if key in seen:
                continue
            seen.add(key)
            favorites.append({"provider": provider, "model": model})
        self.core.settings["favorite_models"] = favorites[:60]
        return self.core.settings["favorite_models"]

    def _is_model_favorite(self, provider, model):
        key = self._favorite_model_key(provider, model)
        return any(self._favorite_model_key(item.get("provider"), item.get("model")) == key for item in self._normalized_favorite_models())

    def _ensure_model_favorite(self, provider, model, *, save=False):
        provider, model = self._favorite_model_key(provider, model)
        if not provider or not model:
            return False
        favorites = self._normalized_favorite_models()
        if not any(self._favorite_model_key(item.get("provider"), item.get("model")) == (provider, model) for item in favorites):
            favorites.insert(0, {"provider": provider, "model": model})
            self.core.settings["favorite_models"] = favorites[:60]
            if save:
                self.core._save_settings()
            if hasattr(self.main_window, "refresh_favorite_model_controls"):
                self.main_window.refresh_favorite_model_controls()
            return True
        return False

    def _remove_model_favorite(self, provider, model, *, save=False):
        provider, model = self._favorite_model_key(provider, model)
        favorites = [
            item for item in self._normalized_favorite_models()
            if self._favorite_model_key(item.get("provider"), item.get("model")) != (provider, model)
        ]
        self.core.settings["favorite_models"] = favorites
        if save:
            self.core._save_settings()
        if hasattr(self.main_window, "refresh_favorite_model_controls"):
            self.main_window.refresh_favorite_model_controls()

    def _toggle_model_favorite_from_picker(self, model):
        provider = normalize_provider_name(self.provider_combo.currentText())
        model = str(model or "").strip()
        if not model:
            return
        if self._is_model_favorite(provider, model):
            self._remove_model_favorite(provider, model, save=True)
        else:
            self._ensure_model_favorite(provider, model, save=True)
        if hasattr(self.model_combo, "_refresh_result_star_buttons"):
            self.model_combo._refresh_result_star_buttons()

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

    def _last_update_check_datetime(self):
        raw = str(self.core.settings.get("updates_last_checked_at", "") or "").strip()
        if not raw:
            return None
        try:
            text = raw[:-1] if raw.endswith("Z") else raw
            checked_at = datetime.fromisoformat(text)
            offset = checked_at.utcoffset() if checked_at.tzinfo else None
            if offset is not None:
                checked_at = (checked_at - offset).replace(tzinfo=None)
            return checked_at
        except Exception:
            return None

    def _relative_update_check_text(self):
        checked_at = self._last_update_check_datetime()
        if not checked_at:
            return ""
        seconds = max(0, int((datetime.utcnow() - checked_at).total_seconds()))
        if seconds < 60:
            return "עכשיו"
        minutes = seconds // 60
        if minutes < 60:
            return "לפני דקה" if minutes == 1 else f"לפני {minutes} דקות"
        hours = minutes // 60
        if hours < 24:
            return "לפני שעה" if hours == 1 else f"לפני {hours} שעות"
        days = hours // 24
        return "אתמול" if days == 1 else f"לפני {days} ימים"

    def _update_status_tooltip(self):
        checked_at = self._last_update_check_datetime()
        if not checked_at:
            return ""
        return f"בדיקה אחרונה: {checked_at.strftime('%d.%m.%Y %H:%M:%S')} UTC"

    def _update_status_text(self):
        available = str(self.core.settings.get("updates_last_available_version", "") or "").strip()
        if available:
            return f"עדכון זמין: גרסה {available}"
        relative = self._relative_update_check_text()
        if relative:
            return f"בדיקה אחרונה: {relative}"
        return "עדיין לא בוצעה בדיקת עדכונים."

    def _update_status_label_css(self):
        return (
            f"QLabel {{ background: {GLASS_COLOR}; color: {TEXT_COLOR}; "
            f"border: 1px solid {SOFT_LINE_COLOR}; border-radius: 12px; "
            "padding: 8px 12px; font-size: 12px; font-weight: 700; text-align: right; "
            "qproperty-wordWrap: false; }}"
        )

    def _style_update_status_label(self):
        if not hasattr(self, "update_status_lbl"):
            return
        self.update_status_lbl.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.update_status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.update_status_lbl.setWordWrap(False)
        self.update_status_lbl.setMinimumHeight(40)
        self.update_status_lbl.setStyleSheet(self._update_status_label_css())

    def refresh_update_status_label(self):
        if getattr(self, "_update_status_temporary", False):
            return
        if hasattr(self, "update_status_lbl"):
            self._style_update_status_label()
            self.update_status_lbl.setText(self._update_status_text())
            self.update_status_lbl.setToolTip(self._update_status_tooltip())

    def begin_update_check(self):
        self._update_status_temporary = True
        if hasattr(self, "check_updates_btn"):
            self.check_updates_btn.setEnabled(False)
        if hasattr(self, "update_status_lbl"):
            self._style_update_status_label()
            self.update_status_lbl.setText("בודק עדכונים...")

    def finish_update_check(self, message, reset_after_ms=0):
        if hasattr(self, "check_updates_btn"):
            self.check_updates_btn.setEnabled(True)
        if hasattr(self, "update_status_lbl"):
            if message:
                self._update_status_temporary = bool(reset_after_ms)
                self.update_status_lbl.setText(str(message))
                self.update_status_lbl.setToolTip(self._update_status_tooltip())
            else:
                self._update_status_temporary = False
                self.refresh_update_status_label()
            if reset_after_ms:
                expected = str(message or "")

                def restore_update_status():
                    if hasattr(self, "update_status_lbl") and self.update_status_lbl.text() == expected:
                        self._update_status_temporary = False
                        self.refresh_update_status_label()

                QTimer.singleShot(int(reset_after_ms), restore_update_status)

    def check_updates_now(self):
        if hasattr(self.main_window, "check_for_updates_manual"):
            self.main_window.check_for_updates_manual(self)

    def _init_widgets(self):
        self.core.ensure_provider_secret(self.core.settings.get("api_mode", "gemini"))
        for secret_key in ("tavily_api_key", "email_address", "email_password"):
            self.core._ensure_secret_loaded(secret_key)

        self.provider_combo = NoScrollComboBox()
        for provider in MODEL_PROVIDER_ORDER:
            if provider == "openai_codex_signin":
                self.provider_combo.addItem(provider_display_name(provider), provider)
            else:
                self.provider_combo.addItem(provider)
        selected_provider = normalize_provider_name(self.core.settings.get("api_mode", "gemini"))
        selected_index = self.provider_combo.findData(selected_provider)
        if selected_index >= 0:
            self.provider_combo.setCurrentIndex(selected_index)
        else:
            self.provider_combo.setCurrentText(selected_provider)
        self.provider_combo.setStyleSheet(COMBOBOX_CSS)
        self.provider_combo.currentTextChanged.connect(self.on_provider_change)
        
        self.model_combo = SearchableModelComboBox()
        self.model_combo.setStyleSheet(COMBOBOX_CSS)
        self.model_picker_row = self._make_model_picker_row()
        self.reasoning_effort_combo = NoScrollComboBox()
        # Compatibility alias for existing integrations and tests.
        self.codex_reasoning_effort_combo = self.reasoning_effort_combo
        self.reasoning_effort_combo.setStyleSheet(COMBOBOX_CSS)
        self.conversation_title_mode_combo = NoScrollComboBox()
        self.conversation_title_mode_combo.addItem("המודל יוצר כותרת יפה וייחודית", "ai")
        self.conversation_title_mode_combo.addItem("כותרת מיידית ללא פנייה למודל", "local")
        title_mode = str(
            self.core.settings.get("conversation_title_generation_mode", "ai") or "ai"
        ).strip().lower()
        title_mode_index = self.conversation_title_mode_combo.findData(
            title_mode if title_mode in {"ai", "local"} else "ai"
        )
        self.conversation_title_mode_combo.setCurrentIndex(max(0, title_mode_index))
        self.conversation_title_mode_combo.setStyleSheet(COMBOBOX_CSS)
        
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
        self.codex_signin_worker = None
        self.codex_signin_row = self._make_codex_signin_row()
        self.codex_signin_warning = QLabel(
            "חיבור זה משתמש ב-Codex sign-in הרשמי של OpenAI, כפוף למגבלות החשבון והתוכנית שלך, ועלול להשתנות לפי מדיניות OpenAI.",
            self,
        )
        self.codex_signin_warning.setWordWrap(True)
        self.codex_signin_warning.setStyleSheet(muted_label_css(12))
        self.tavily_key = MaskedSecretLineEdit(self.core.settings.get("tavily_api_key", ""))
        self.tavily_key_help_link = QLabel(self)
        self.tavily_key_row = self._make_secret_link_row(self.tavily_key, self.tavily_key_help_link)
        self.tavily_key_help_hint = QLabel(provider_key_instructions(secret_key="tavily_api_key"), self)
        self.tavily_key_help_hint.setWordWrap(True)
        self.tavily_key_help_hint.setStyleSheet(muted_label_css(12))
        self._set_external_link(self.tavily_key_help_link, provider_help_url(secret_key="tavily_api_key"), "קבל מפתח")
        self._update_provider_key_help()
        self.local_url = QLineEdit(self.core.settings.get("local_server_url", "http://localhost:1234/v1"))
        self.local_fast_mode_cb = SmartiCheckBox("הפעל FastMode למודלים מקומיים")
        self.local_fast_mode_cb.setChecked(
            bool(self.core.settings.get("local_fast_mode_enabled", False))
        )
        self.local_fast_mode_cb.setStyleSheet(CHECKBOX_CSS)

        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        
        self.permission_combo = SegmentedControl()
        self.permission_combo.addItems(["בטוח", "מאוזן", "אוטונומי"])
        self.permission_combo.setItemIconNames(0, ("autonomy_safe", "autonomy_safe_icon", "security_safe_icon", "shield_safe_icon"))
        self.permission_combo.setItemIconNames(1, ("autonomy_balanced", "autonomy_balanced_icon", "security_balanced_icon", "balance_icon"))
        self.permission_combo.setItemIconNames(2, ("autonomy_full", "autonomy_full_icon", "security_full_icon", "full_access_icon"))
        custom_permissions_enabled = bool(self.core.settings.get("custom_permission_profile_enabled", False))
        if custom_permissions_enabled:
            self.permission_combo.clearSelection(emit=False)
        else:
            self.permission_combo.setCurrentIndex(max(0, min(2, self.core.settings.get("permission_level", 2) - 1)))
        self.custom_permissions_cb = SmartiCheckBox("התאמה אישית של הרשאות")
        self.custom_permissions_cb.setChecked(custom_permissions_enabled)
        self.custom_permissions_cb.setStyleSheet(CHECKBOX_CSS)

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
            ("dark", "כהה"),
            ("system", "מערכת"),
            ("light", "בהיר")
        ]
        self.theme_combo.addItems([label for _, label in self.theme_options])
        self.theme_combo.setToolTip("בחר ערכת נושא. השינוי מוחל מיד על חלונות, תפריטים ואייקונים.")
        self.theme_combo.setItemIconNames(0, ("theme_dark", "dark_theme", "moon_icon", "settings_icon"))
        self.theme_combo.setItemIconNames(1, ("theme_system", "system_theme", "monitor_icon", "settings_icon"))
        self.theme_combo.setItemIconNames(2, ("theme_light", "light_theme", "sun_icon", "settings_icon"))
        current_theme = self.core.settings.get("ui_preferences", {}).get("theme_mode", DEFAULT_THEME_MODE)
        theme_keys = [key for key, _ in self.theme_options]
        self.theme_combo.setCurrentIndex(theme_keys.index(current_theme) if current_theme in theme_keys else 0)

        self.update_auto_cb = SmartiCheckBox("בדוק עדכונים אוטומטית")
        self.update_auto_cb.setToolTip("")
        self.update_auto_cb.setChecked(bool(self.core.settings.get("updates_auto_check", True)))
        self.update_auto_cb.setStyleSheet(CHECKBOX_CSS)
        self.check_updates_btn = QPushButton("בדוק עדכונים עכשיו")
        self.check_updates_btn.setToolTip("")
        self.check_updates_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.check_updates_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        set_themed_button_icon(self.check_updates_btn, ("check_updates_icon",), self.check_updates_btn.text(), 18, clear_text=False)
        self.check_updates_btn.clicked.connect(self.check_updates_now)
        self.update_status_lbl = QLabel(self._update_status_text())
        self.update_status_lbl.setProperty("smartiUpdateStatusPill", True)
        self.update_status_lbl.setWordWrap(False)
        self.update_status_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.update_status_lbl.setToolTip(self._update_status_tooltip())
        self._style_update_status_label()
        self._update_status_temporary = False
        self._update_status_refresh_timer = QTimer(self)
        self._update_status_refresh_timer.setInterval(30000)
        self._update_status_refresh_timer.timeout.connect(self.refresh_update_status_label)
        self._update_status_refresh_timer.start()

        self.policy_combos = {}
        policy = self.core._normalize_policy_matrix()
        for cap, label in CAPABILITY_LABELS.items():
            combo = SegmentedControl()
            combo.addItems(["אפשר", "שאל בכל פעם", "חסום"])
            value = policy.get(cap, DEFAULT_POLICY_MATRIX.get(cap, "ask"))
            combo.setCurrentIndex({"allow": 0, "ask": 1, "deny": 2}.get(value, 1))
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
            dialog_title="בחר תיקייה לכלי MCP",
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
        self.marketplace_approval_cb = SmartiCheckBox("דרוש אישור להתקנת MCP ומיומנויות")
        self.marketplace_approval_cb.setChecked(self.core.settings.get("marketplace_install_requires_approval", True))
        self.marketplace_approval_cb.setStyleSheet(CHECKBOX_CSS)

        self.browser_auto_cb = SmartiCheckBox("שליטה בדפדפן")
        self.browser_auto_cb.setChecked(self.core.settings.get("enable_browser_automation", False))
        self.browser_auto_cb.setStyleSheet(CHECKBOX_CSS)
        self.computer_control_cb = SmartiCheckBox("שליטה במחשב")
        self.computer_control_cb.setChecked(self.core.settings.get("enable_computer_control", False))
        self.computer_control_cb.setStyleSheet(CHECKBOX_CSS)
        self.mcp_cb = SmartiCheckBox("חבילות MCP")
        self.mcp_cb.setChecked(self.core.settings.get("enable_mcp_clawhub", False))
        self.mcp_cb.setStyleSheet(CHECKBOX_CSS)
        self.skills_beta_cb = SmartiCheckBox("מיומנויות")
        self.skills_beta_cb.setChecked(self.core.settings.get("enable_skills_beta", True))
        self.skills_beta_cb.setStyleSheet(CHECKBOX_CSS)
        self.tool_search_catalog_cb = SmartiCheckBox("קטלוג חיפוש כלים חכם")
        self.tool_search_catalog_cb.setChecked(self.core.settings.get("enable_tool_search_catalog", True))
        self.tool_search_catalog_cb.setStyleSheet(CHECKBOX_CSS)
        self.skills_load_watch_cb = SmartiCheckBox("רענון אוטומטי של מיומנויות וכלים")
        self.skills_load_watch_cb.setChecked(self.core.settings.get("skills_load_watch", True))
        self.skills_load_watch_cb.setStyleSheet(CHECKBOX_CSS)
        self.skill_unknown_scan_combo = SegmentedControl()
        self.skill_unknown_scan_options = [("allow_with_warning", "אפשר עם אזהרה"), ("block", "חסום")]
        self.skill_unknown_scan_combo.addItems([label for _, label in self.skill_unknown_scan_options])
        current_unknown_policy = str(self.core.settings.get("skill_install_unknown_scan_policy", "allow_with_warning"))
        self.skill_unknown_scan_combo.setCurrentIndex(1 if current_unknown_policy == "block" else 0)
        self.web_canvas_cb = SmartiCheckBox("קנבס חזותי")
        self.web_canvas_cb.setChecked(
            bool(self.core.settings.get("enable_visual_surfaces", False) and self.core.settings.get("enable_web_canvas", False))
        )
        self.web_canvas_cb.setStyleSheet(CHECKBOX_CSS)
        self.web_canvas_cb.setEnabled(web_canvas_available())
        if not web_canvas_available():
            self.web_canvas_cb.setToolTip("נדרש PyQt6-WebEngine. התקן/י את requirements.txt כדי להפעיל קנבס.")
        self.web_canvas_remote_images_cb = SmartiCheckBox("אפשר תמונות HTTPS מהרשת בתוך קנבס")
        self.web_canvas_remote_images_cb.setChecked(bool(self.core.settings.get("enable_canvas_remote_images", False)))
        self.web_canvas_remote_images_cb.setStyleSheet(CHECKBOX_CSS)
        self.web_canvas_remote_images_cb.setToolTip(
            "מתיר לקנבס לטעון תמונות HTTPS שהמודל בחר. הקנבס עדיין חוסם ניווט, הורדות, קבצים, חלונות קופצים וקריאות רשת אחרות."
        )

        def refresh_remote_canvas_images_enabled(_checked=None):
            self.web_canvas_remote_images_cb.setEnabled(web_canvas_available() and self.web_canvas_cb.isChecked())

        self.web_canvas_cb.toggled.connect(refresh_remote_canvas_images_enabled)
        refresh_remote_canvas_images_enabled()

        self.email = QLineEdit(self.core.settings.get("email_address", ""))
        self.pwd = QLineEdit(self.core.settings.get("email_password", ""))
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.email_password_row = self._make_paste_input_row(
            self.pwd,
            "הדבק סיסמת אפליקציה מלוח ההעתקה",
        )
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
        self.email_test_row = self._make_email_test_row()

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
        self.tts_preview_row = self._make_tts_preview_row()
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
        self.voice_beep_cb = SmartiCheckBox("צליל בתחילת וסיום האזנה")
        self.voice_beep_cb.setChecked(bool(self.core.settings.get("voice_beep_enabled", True)))
        self.voice_beep_cb.setStyleSheet(CHECKBOX_CSS)

        self.ssl_trust_card = SSLTrustSettingsCard(self.core)
        self.cloud_upload_cb = SmartiCheckBox("אישור לפני שליחת נתונים למודל חיצוני")
        self.cloud_upload_cb.setChecked(self.core.settings.get("require_approval_for_cloud_upload", True))
        self.cloud_upload_cb.setStyleSheet(CHECKBOX_CSS)
        self.write_outside_dirs_approval_cb = SmartiCheckBox("אישור לפני כתיבה מחוץ לתיקיית הפלט")
        self.write_outside_dirs_approval_cb.setChecked(self.core.settings.get("write_outside_allowed_dirs_requires_approval", True))
        self.write_outside_dirs_approval_cb.setStyleSheet(CHECKBOX_CSS)
        self.mcp_pin_cb = SmartiCheckBox("דרוש גרסה קבועה לכלי MCP")
        self.mcp_pin_cb.setChecked(self.core.settings.get("mcp_require_pinned_versions", True))
        self.mcp_pin_cb.setStyleSheet(CHECKBOX_CSS)
        self.prevent_sleep_cb = SmartiCheckBox("מנע שינה של המחשב בזמן משימה פעילה")
        self.prevent_sleep_cb.setChecked(self.core.settings.get("prevent_sleep_during_active_task", True))
        self.prevent_sleep_cb.setStyleSheet(CHECKBOX_CSS)

        self.cmd_timeout = QLineEdit(str(self.core.settings.get("command_timeout_seconds", 60)))
        self.tool_timeout = QLineEdit(str(self.core.settings.get("tool_timeout_seconds", 120)))
        self.mcp_timeout = QLineEdit(str(self.core.settings.get("mcp_timeout_seconds", 60)))
        self.max_chars_edit = QLineEdit(str(self.core.settings.get("max_tool_output_chars", 100000)))
        self.total_timeout = QLineEdit(str(self.core.settings.get("max_total_task_seconds", 0)))
        self.codex_request_timeout = QLineEdit(str(self.core.settings.get("codex_request_timeout_seconds", 1800)))
        self.permission_notification_timeout = QLineEdit(str(self.core.settings.get("permission_notification_timeout_seconds", 0)))
        budgets = self.core.settings.get("budgets", {})
        self.daily_token_budget = QLineEdit(str(budgets.get("daily_token_budget", 0)))
        self.daily_cost_budget = QLineEdit(str(budgets.get("daily_cost_budget_usd", 0)))
        
        self.loops_slider = RtlFillSlider(Qt.Orientation.Horizontal)
        self.loops_slider.setRange(4, 31)
        saved_loops = self.core.settings.get("max_agent_loops", 0)
        try:
            saved_loops = int(saved_loops)
        except Exception:
            saved_loops = 0
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
        self.loops_control = QWidget()
        self.loops_control.setStyleSheet("background: transparent;")
        loops_control_layout = QHBoxLayout(self.loops_control)
        loops_control_layout.setContentsMargins(0, 0, 0, 0)
        loops_control_layout.setSpacing(10)
        loops_control_layout.addWidget(self.loops_slider, 1)
        loops_control_layout.addWidget(self.loops_val_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        catch_up_value = self.core.settings.get("background_recurring_catch_up_window_minutes", 15)
        try:
            catch_up_value = int(round(float(catch_up_value)))
        except Exception:
            catch_up_value = 15
        catch_up_value = 181 if catch_up_value < 0 else max(0, min(180, catch_up_value))
        self.background_catch_up_control, self.background_catch_up_slider, self.background_catch_up_lbl = self._make_labeled_slider(
            0, 181, catch_up_value, self._catch_up_window_label_text
        )

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
        label.setMinimumSize(122, 30)
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
            self.tts_voice_combo.addItem("טקסט לדיבור לא זמין", "co.il")
        selected_voice = str(self.core.settings.get("tts_voice_id", "co.il") or "co.il")
        index = self.tts_voice_combo.findData(selected_voice)
        if index < 0 and selected_voice in {"com", "co.uk", "com.au", "ca", "co.in"}:
            index = self.tts_voice_combo.findData("co.il")
        self.tts_voice_combo.setCurrentIndex(index if index >= 0 else 0)

    def preview_tts(self):
        worker = getattr(self, "tts_preview_worker", None)
        if worker and worker.isRunning():
            self.core.stop_speaking()
            return
        if not TTS_INSTALLED:
            QMessageBox.information(self, "תצוגה מקדימה", "לא מותקן מנוע טקסט לדיבור.")
            return
        self.autosave_timer.stop()
        self.core.settings["tts_voice_id"] = self.tts_voice_combo.currentData() or "co.il"
        self.core.settings["tts_volume"] = int(self.tts_volume_slider.value())
        text = self.tts_preview_text.text().strip() if hasattr(self, "tts_preview_text") else ""
        text = text or "שלום, זו תצוגה מקדימה של הקול הנוכחי."
        self.tts_preview_btn.setText("עצור")
        self.tts_preview_btn.setEnabled(True)
        worker = TTSWorker(self.core, text)
        self.tts_preview_worker = worker
        worker.finished.connect(lambda w=worker: self._on_tts_preview_finished(w))
        worker.start()

    def _on_tts_preview_finished(self, worker):
        if getattr(self, "tts_preview_worker", None) is worker:
            self.tts_preview_worker = None
        if hasattr(self, "tts_preview_btn"):
            self.tts_preview_btn.setText("השמע")
            self.tts_preview_btn.setEnabled(True)
            refresh_themed_button_icon(self.tts_preview_btn)
        worker.deleteLater()

    def _loop_label_text(self, val):
        return "ללא הגבלה" if val > 30 else f"{val} סבבים"

    def _catch_up_window_label_text(self, val):
        try:
            val = int(round(float(val or 0)))
        except Exception:
            val = 0
        if val >= 181:
            return "ללא הגבלה"
        if val <= 0:
            return "לא להריץ באיחור"
        if val == 1:
            return "דקה אחת"
        if val < 60:
            return f"{val} דקות"
        if val == 60:
            return "שעה"
        if val == 120:
            return "שעתיים"
        if val == 180:
            return "3 שעות"
        if val % 60 == 0:
            return f"{val // 60} שעות"
        return f"{val / 60:.1f} שעות"

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

    def _setting_needs_info(self, label_text, hint, advanced=False, info=None):
        if info is not None:
            return bool(info)
        if advanced:
            return True
        text = f"{label_text or ''} {hint or ''}".lower()
        technical_terms = [
            "api", "imap", "smtp", "ssl", "mcp", "shell", "tavily", "token", "port",
            "מפתח", "סיסמת", "שרת", "פורט", "ארגז חול", "הרשאות", "אוטונומי",
            "אישור", "חיבור", "כלים חיצוניים", "תאימות", "לוג", "trace", "אודיט",
        ]
        return any(term in text for term in technical_terms)

    def _add_checkbox(self, widget, target_layout=None, hint=None, *, keywords=None, setting_id="", advanced=False, info=None):
        layout = target_layout
        if layout is None: return
        container = QFrame()
        container.setObjectName("SettingsFieldContainer")
        container.setStyleSheet(self._field_container_css(False))
        container.setProperty("smartiSettingsFieldContainer", True)
        container.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        container.smarti_target_page = getattr(layout, "smarti_target_page", None)
        container.smarti_section_title = getattr(layout, "smarti_section_title", "")
        inner = QHBoxLayout(container)
        inner.setContentsMargins(8, 6, 8, 6)
        inner.setSpacing(8)
        widget.setMinimumWidth(1)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_text = hint if info is True or info is None else str(info or "")
        show_info = bool(info_text and self._setting_needs_info(widget.text() if hasattr(widget, "text") else "", hint, advanced, info))
        embedded_info = self._attach_checkbox_info_button(widget, info_text) if show_info else None
        if show_info and embedded_info is None:
            inner.addWidget(self._make_info_button(info_text), 0, Qt.AlignmentFlag.AlignTop)
        inner.addWidget(widget, 1)
        layout.addWidget(container)
        self._register_setting_entry(widget.text() if hasattr(widget, "text") else "", widget, container, hint or "", keywords, advanced, setting_id)
        return container

    def _add_field(self, label_text, widget, target_layout=None, hint=None, *, keywords=None, setting_id="", advanced=False, info=None):
        layout = target_layout
        if layout is None: return
        if widget is getattr(self, "background_catch_up_control", None):
            label_text = "הרצת משימה מחזורית אחרי פספוס"
            hint = (
                "כמה זמן אחרי השעה המתוכננת עדיין מותר לסמארטי להריץ משימה שהוחמצה. "
                "בקצה הסליידר: ללא הגבלה. לאחר מכן המשימה חוזרת לשעה הקבועה."
            )
        container = QFrame()
        container.setObjectName("SettingsFieldContainer")
        container.setStyleSheet(self._field_container_css(False))
        container.setProperty("smartiSettingsFieldContainer", True)
        container.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        container.smarti_target_page = getattr(layout, "smarti_target_page", None)
        container.smarti_section_title = getattr(layout, "smarti_section_title", "")
        inner = QVBoxLayout(container)
        inner.setContentsMargins(8, 6, 8, 6)
        inner.setSpacing(6)
        label_row = QHBoxLayout()
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.setSpacing(6)
        label_group = QWidget()
        label_group.setStyleSheet("background: transparent;")
        label_group.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        group_layout = QHBoxLayout(label_group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setWordWrap(False)
        lbl.setMinimumWidth(1)
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 13px; font-weight: 700; margin-top: 4px;")
        group_layout.addWidget(lbl, 0)
        info_text = hint if info is True or info is None else str(info or "")
        if info_text and self._setting_needs_info(label_text, hint, advanced, info):
            group_layout.addWidget(self._make_info_button(info_text), 0, Qt.AlignmentFlag.AlignTop)
        label_row.addWidget(label_group, 0, Qt.AlignmentFlag.AlignRight)
        label_row.addStretch()
        inner.addLayout(label_row)
        if isinstance(widget, QLineEdit): widget.setStyleSheet(LINE_EDIT_CSS)
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        inner.addWidget(widget)
        layout.addWidget(container)
        self._register_setting_entry(label_text, widget, container, hint or "", keywords, advanced, setting_id)
        layout.addSpacing(10)
        return container

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
        vbox.smarti_target_page = page
        vbox.smarti_section_title = ""
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.settings_stack.addWidget(page)
        return page, vbox

    def _add_internal_back(self, target_layout, title):
        target_layout.smarti_section_title = title
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
        self.search_results_page, search_results = self._make_scroll_page()
        ai_page, ai = self._make_scroll_page()
        safety_page, safety = self._make_scroll_page()
        policy_page, policy_layout = self._make_scroll_page()
        self._settings_back_targets = {policy_page: safety_page}
        tools_page, tools = self._make_scroll_page()
        app_page, app_settings = self._make_scroll_page()
        advanced_page, advanced = self._make_scroll_page()
        self.developer_page = advanced_page
        self._management_section_pages = {
            "ai": ai_page,
            "safety": safety_page,
            "tools": tools_page,
            "appearance": app_page,
            "advanced": advanced_page,
        }

        self.search_results_hint = QLabel("")
        self.search_results_hint.setWordWrap(True)
        self.search_results_hint.setStyleSheet(muted_label_css(13))
        search_results.addWidget(self.search_results_hint)
        self.search_results_list = QListWidget()
        self.search_results_list.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.search_results_list.setWordWrap(True)
        self.search_results_list.setSpacing(8)
        self.search_results_list.setMinimumWidth(0)
        self.search_results_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.search_results_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.search_results_list.itemActivated.connect(self._activate_search_result)
        self.search_results_list.itemClicked.connect(self._activate_search_result)
        self.search_results_list.setStyleSheet(
            f"QListWidget {{ background: transparent; color: {TEXT_COLOR}; border: none; outline: none; }}"
            f"QListWidget::item {{ background: {GLASS_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 16px; padding: 10px 12px; }}"
            f"QListWidget::item:hover {{ background: {HOVER_TINT}; border-color: {LINE_COLOR}; }}"
            f"QListWidget::item:selected {{ background: {ACCENT_TINT_STRONG}; border-color: {ACCENT_COLOR}; color: {TEXT_COLOR}; }}"
        )
        search_results.addWidget(self.search_results_list, 1)
        search_results.addStretch()

        home.addWidget(self._nav_card("מודלי AI וספקים", "ספק מודל, מודל פעיל, מפתחות גישה וחיפוש אינטרנט", ai_page))
        home.addWidget(self._nav_card("אבטחה ופרטיות", "פרופיל בטיחות, אישורים, ארגז חול וקבצים", safety_page))
        home.addWidget(self._nav_card("כלים ותקשורת", "דפדפן, מחשב, אימייל, MCP ומיומנויות", tools_page))
        home.addWidget(self._nav_card("קול, מראה ומערכת", "ערכת נושא, הקראה, האזנה ועדכונים", app_page))
        self.advanced_home_card = self._nav_card("מתקדם ומפתחים", "זמני המתנה, תקציבים, תאימות, Trace ולוגים", advanced_page)
        home.addWidget(self.advanced_home_card)
        home.addSpacing(8)
        home.addWidget(self._make_reset_button())
        home.addStretch()

        self._add_internal_back(ai, "מודלי AI וספקים")
        self._add_field("ספק המודל", self.provider_combo, ai, "בחר את שירות ה-AI שסמארטי ישתמש בו לתשובות ולתכנון פעולות.", keywords="provider vendor engine gemini openai anthropic local openrouter groq nvidia cerebras huggingface deepseek qwen zhipu moonshot mistral together perplexity xai")
        self.api_key_field_container = self._add_field(
            "מפתח גישה לספק המודל",
            self.api_key_row,
            ai,
            "מפתח API הוא קוד גישה אישי שמאפשר לסמארטי לשלוח בקשות מאובטחות לספק המודל. הוא נדרש לספקים חיצוניים, נבדק מול הספק לפני שמירה ונשמר כמפתח מוסתר שלא מוצג בלוגים.",
            keywords="api key token secret validate connection authentication login billing",
            info=True
        )
        ai.addWidget(self.api_key_status)
        ai.addWidget(self.api_key_help_hint)
        self.codex_signin_field_container = self._add_field(
            "חיבור ChatGPT / Codex",
            self.codex_signin_row,
            ai,
            "התחברות רשמית עם חשבון ChatGPT או Codex. לא נשמרים סיסמה, API key או token בהגדרות של סמארטי.",
            keywords="openai codex chatgpt sign in oauth login connect disconnect token credential manager",
            info=True,
        )
        ai.addWidget(self.codex_signin_warning)
        self.codex_signin_field_container.setVisible(False)
        self.codex_signin_warning.setVisible(False)
        self._add_field("מודל", self.model_picker_row, ai, "בחירת המודל הפעיל לשיחה. בחירה נשמרת גם כמועדף כדי שאפשר יהיה להחליף אליו במהירות מהצ'אט.", keywords="favorite favourite star quick switch chat model picker spinner llm")
        self.codex_reasoning_effort_field_container = self._add_field(
            "עוצמת חשיבה",
            self.reasoning_effort_combo,
            ai,
            "קובעת את עוצמת החשיבה של המודל הפעיל. האפשרויות מותאמות אוטומטית לחוזה של משפחת המודל; בחירה באוטומטית משאירה את השדה ריק ומשתמשת בברירת הספק.",
            keywords="codex openai gemini anthropic reasoning effort thinking level budget",
        )
        self.codex_reasoning_effort_field_container.setVisible(False)
        self._add_field(
            "יצירת כותרת לשיחה",
            self.conversation_title_mode_combo,
            ai,
            "כבר בתחילת השיחה סמארטי מציג שם זמני ייחודי. כברירת מחדל המודל יוצר במקביל כותרת יפה ומדויקת על בסיס הבקשה הראשונה; אפשר לבחור בכותרת מקומית כדי לחסוך פנייה נוספת למודל.",
            keywords="conversation chat title ai automatic local unique כותרת שיחה אוטומטית מודל",
            setting_id="conversation_title_generation_mode",
        )
        self._add_field("כתובת שרת מקומי למודל מקומי", self.local_url, ai, "רלוונטי כשמשתמשים במודל מקומי, למשל דרך LM Studio או שרת תואם OpenAI.", keywords="local server url lm studio ollama localhost endpoint base url")
        self.local_fast_mode_field_container = self._add_checkbox(
            self.local_fast_mode_cb,
            ai,
            "מצמצם את חוזה המערכת ואת קטלוג הכלים הקבוע, וטוען סכמות רק לפי צורך. כל היכולות נשארות זמינות. המצב אינו מופעל כברירת מחדל.",
            keywords="local fast mode small model weak hardware context tokens speed",
            setting_id="local_fast_mode_enabled",
        )
        self.local_fast_mode_field_container.setVisible(
            normalize_provider_name(self.provider_combo.currentText()) == "local"
        )
        self._add_field("מפתח חיפוש באינטרנט (Tavily)", self.tavily_key_row, ai, "מאפשר לסמארטי לבצע חיפוש אינטרנט כאשר נדרש מידע עדכני.", keywords="web search internet tavily live current latest")
        ai.addWidget(self.tavily_key_help_hint)
        ai.addStretch()

        self._add_internal_back(safety, "אבטחה ופרטיות")
        self._add_field("פרופיל בטיחות", self.permission_combo, safety, "קובע כמה סמארטי יכול לפעול לבד: בטוח מבקש יותר אישורים, מאוזן מתאים לרוב העבודה, ואוטונומי מאפשר יותר רצף פעולה.", keywords="safe balanced autonomous full access permission autonomy approval security", info=True)
        self._add_checkbox(self.custom_permissions_cb, safety, "מאפשר להגדיר הרשאות פרטניות במקום לבחור פרופיל בטיחות כללי.", keywords="custom permissions profile policy matrix granular allow ask deny הרשאות מותאמות אישית פרופיל מדיניות יכולות שאל חסום אפשר", info=True)
        self.policy_btn = QPushButton("הגדרת התאמה אישית")
        self.policy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.policy_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        set_themed_button_icon(self.policy_btn, ("policy_icon", "security_icon", "settings_icon"), self.policy_btn.text(), 18, clear_text=False)
        self.policy_btn.clicked.connect(lambda: self._set_settings_section(policy_page))
        self.policy_field_container = self._add_field("טבלת יכולות מפורטת", self.policy_btn, safety, "לוח מתקדם לקביעה פרטנית אם סמארטי ישאל, ירשה או יחסום כל יכולת.", keywords="matrix capability policy allow ask deny granular custom permissions טבלת יכולות הרשאות מותאמות אישית מדיניות שאל חסום אפשר")
        self.policy_field_container.setVisible(self.custom_permissions_cb.isChecked())
        self._add_section_header("ארגז חול", safety)
        self._add_checkbox(self.sandbox_cb, safety, "מגביל את סמארטי לתיקייה אחת. מצב זה מתאים לעבודה בטוחה על פרויקט או תיקייה מוגדרת.", keywords="sandbox project folder safe workspace", info=True)
        self._add_field("תיקיית ארגז החול", self.sandbox_root_picker, safety, "בחר את התיקייה שבה סמארטי רשאי לעבוד כאשר ארגז החול פעיל.", keywords="workspace root allowed folder path", info=True)
        self._add_checkbox(self.sandbox_read_outside_cb, safety, "מאפשר לסמארטי לקרוא קבצים מחוץ לארגז החול, אך עדיין חוסם כתיבה, שינוי ומחיקה מחוץ אליו.", keywords="read outside sandbox files privacy", advanced=True, info=True)
        self._add_section_header("קבצים ונתונים", safety)
        self._add_field("תיקיית ברירת מחדל ליצירת קבצים", self.default_output_dir_picker, safety, "כאשר ביקשת ליצור או לשמור קובץ בלי לציין מיקום, סמארטי ישמור אותו כאן. זו לא מגבלת הרשאה ולא ארגז חול.", keywords="output save export write folder default", info=True)
        self._add_checkbox(self.write_outside_dirs_approval_cb, safety, "כאשר האפשרות פעילה, סמארטי יבקש אישור לפני כתיבה מחוץ לתיקיית הפלט. באוטונומיה מלאה האפשרות נכבית אוטומטית, אלא אם ארגז חול פעיל.", keywords="write outside approval delete modify file safety")
        self._add_checkbox(self.cloud_upload_cb, safety, "כאשר האפשרות פעילה, סמארטי יבקש אישור לפני שליחת קבצים, צילום מסך או אימייל למודל חיצוני.", keywords="cloud upload external model privacy screenshot email", info=True)
        self._add_checkbox(self.mcp_pin_cb, safety, "מחייב התקנת כלים חיצוניים בגרסה קבועה, כדי למנוע שינוי לא צפוי בהתנהגות הכלי.", keywords="pinned versions mcp supply chain", advanced=True)
        self._add_checkbox(self.raw_shell_approval_cb, safety, "גם במצב אוטונומי, פקודות מערכת בסיכון גבוה יעצרו לאישור משתמש.", keywords="shell command dangerous powershell cmd terminal approval", advanced=True)
        self._add_checkbox(self.marketplace_approval_cb, safety, "מונע התקנה שקטה של קוד חיצוני חדש ממאגרי MCP או מיומנויות.", keywords="marketplace install approval mcp skills external code מיומנויות התקנה קוד חיצוני", advanced=True)
        safety.addStretch()

        self._add_internal_back(policy_layout, "שליטה מתקדמת ביכולות")
        self._add_hint("הפרופיל הראשי מספיק לרוב השימושים. כאן אפשר לדייק יכולות בודדות בלי להפוך את כל מסך האבטחה למסובך.", policy_layout)
        for cap, label in CAPABILITY_LABELS.items():
            self._add_field(label, self.policy_combos[cap], policy_layout, "בחר אם סמארטי יוכל להשתמש ביכולת הזו, יבקש אישור בכל פעם, או יחסום אותה לחלוטין.", keywords=f"capability policy matrix allow ask deny {cap}")
        policy_layout.addStretch()

        self._add_internal_back(tools, "כלים ותקשורת")
        self._add_section_header("כלים מקומיים ותצוגות", tools)
        self._add_checkbox(
            self.browser_auto_cb,
            tools,
            "שולט ב-Smarti Browser המובנה דרך Playwright/CDP. הפרופיל נפרד מדפדפנים אחרים במחשב ושומר התחברויות שבוצעו בו או יובאו אליו.",
            keywords="browser web automation embedded smarti profile page click"
        )
        self._add_checkbox(self.computer_control_cb, tools, "קריאת עץ הנגישות של Windows ופעולה על רכיבים מזוהים.", keywords="computer control windows accessibility ui automation mouse keyboard")
        self._add_checkbox(self.tool_search_catalog_cb, tools, "מאפשר לסוכן לחפש בקטלוג הכלים הפנימי לפני בחירה, התקנה או יצירת כלי חדש.", keywords="tool search catalog tools python mcp skills selection", info=True)
        self._add_checkbox(self.web_canvas_cb, tools, "מוסיף קנבס HTML מקומי ומבודד לצד הצ'אט עבור בקשות חזותיות מפורשות בלבד. רכיב WebEngine נדרש; הקנבס חוסם רשת, קבצים חיצוניים, הורדות וחלונות קופצים.", keywords="canvas visual dashboard graph form chart mermaid webengine html interactive", info=True)
        self._add_checkbox(self.web_canvas_remote_images_cb, tools, "מאפשר רק טעינת תמונות HTTPS שנבחרו לקנבס. ניווט, הורדות, קבצים, חלונות קופצים ושאר בקשות הרשת נותרים חסומים.", keywords="canvas remote image https web image visual", info=True)
        self._add_section_header("מיומנויות", tools)
        self._add_checkbox(self.skills_beta_cb, tools, "תהליכי עבודה שמכוונים את סמארטי איך להשתמש בכלים קיימים וב-MCP.", keywords="skills workflows instructions", info=True)
        self._add_field("מדיניות סריקה לא חד-משמעית של מיומנות", self.skill_unknown_scan_combo, tools, "מה לעשות כאשר ClawHub לא מחזיר תשובת סריקה חד-משמעית: לאפשר התקנה עם אזהרה או לחסום.", keywords="skill skills מיומנות מיומנויות scan clawhub safety unknown policy סריקה מדיניות", advanced=True)
        self._add_section_header("MCP", tools)
        self._add_checkbox(self.mcp_cb, tools, "שימוש בחבילות MCP שמרחיבות את סמארטי, בכפוף להרשאות.", keywords="mcp packages protocol external tools extensions", info=True)
        # Google Drive settings section is intentionally hidden for now.
        self._add_section_header("אימייל", tools)
        self._add_field("כתובת אימייל", self.email, tools, "כתובת האימייל שממנה סמארטי יקרא או ישלח הודעות, אם אישרת שימוש באימייל.", keywords="email address account username login")
        self._add_field("סיסמת אפליקציה לאימייל", self.email_password_row, tools, "סיסמת אפליקציה ייעודית לחשבון האימייל. אל תשתמש בסיסמה הראשית של החשבון.", keywords="app password mail secret credentials paste clipboard הדבקה")
        self._add_field("בדיקת חיבור אימייל", self.email_test_row, tools, "בודק התחברות ל-IMAP ול-SMTP לפי הפרטים שהוזנו. הבדיקה לא שולחת הודעה.", keywords="test validate email connection imap smtp login check")
        self._add_field("שם שולח", self.email_from_name, tools, "שם תצוגה אופציונלי שיופיע בשדה From.", keywords="from sender display name")
        self._add_field("IMAP host", self.email_imap_host, tools, "ריק = זיהוי אוטומטי לפי כתובת האימייל.", keywords="incoming mail server gmail outlook yahoo", advanced=True)
        self._add_field("IMAP port", self.email_imap_port, tools, "ברירת מחדל נפוצה: 993.", keywords="incoming port server", advanced=True)
        self._add_checkbox(self.email_imap_ssl_cb, tools, "מומלץ להשאיר פעיל לרוב ספקי האימייל.", keywords="imap ssl tls encrypted", advanced=True)
        self._add_field("SMTP host", self.email_smtp_host, tools, "ריק = זיהוי אוטומטי לפי כתובת האימייל.", keywords="outgoing mail server gmail outlook yahoo", advanced=True)
        self._add_field("SMTP port", self.email_smtp_port, tools, "ברירת מחדל נפוצה: 587.", keywords="outgoing port server", advanced=True)
        self._add_checkbox(self.email_smtp_starttls_cb, tools, "מומלץ להשאיר פעיל עבור SMTP בפורט 587.", keywords="smtp starttls encryption", advanced=True)
        self._add_checkbox(self.email_smtp_ssl_cb, tools, "הפעל רק אם הספק דורש SMTP SSL ישיר, לרוב בפורט 465.", keywords="smtp ssl direct port 465", advanced=True)
        self._add_field("גודל מצורף מקסימלי (MB)", self.email_max_attachment_mb, tools, "מגבלת בטיחות לשליחת קבצים מצורפים.", keywords="attachment size limit mb files", advanced=True)
        tools.addStretch()

        self._add_internal_back(app_settings, "קול, מראה ומערכת")
        self._add_section_header("מראה", app_settings)
        self._add_field("מצב תצוגה", self.theme_combo, app_settings, "בחר מצב כהה, בהיר או התאמה אוטומטית להגדרת המערכת של Windows.", keywords="theme dark light system appearance background colors")
        self._add_section_header("קול", app_settings)
        self._add_checkbox(self.tts_cb, app_settings, "כאשר האפשרות פעילה, סמארטי יקריא בקול את כל התשובות.", keywords="tts read aloud speech voice speaker")
        self._add_checkbox(self.tts_voice_cb, app_settings, "כאשר האפשרות פעילה, הקריאה הקולית תופעל בעיקר לאחר פנייה קולית מצד המשתמש.", keywords="voice only read aloud after dictation", advanced=True)
        self._add_field("קול הקראה", self.tts_voice_combo, app_settings, "בחירת קול עברי. קולות Edge זמינים כאשר חבילת edge-tts מותקנת; Google TTS נשאר כגיבוי.", keywords="voice tts edge gtts hebrew")
        self._add_field("עוצמת הקראה", self.tts_volume_control, app_settings, "שולט בעוצמת השמע בזמן ההקראה.", keywords="volume sound loudness")
        self._add_field("תצוגה מקדימה", self.tts_preview_row, app_settings, "משמיע את הטקסט לפי הקול והעוצמה שמוגדרים כרגע.", keywords="preview test voice listen")
        self._add_section_header("האזנה", app_settings)
        self._add_field("רגישות מיקרופון", self.voice_sensitivity_control, app_settings, "ערך גבוה מזהה דיבור חלש מהר יותר; בסביבה רועשת כדאי להוריד מעט.", keywords="microphone sensitivity speech recognition")
        self._add_field("סיום אחרי שקט", self.voice_pause_control, app_settings, "כמה זמן של שקט יסיים את ההאזנה וישלח את התמלול לעיבוד.", keywords="pause silence threshold", advanced=True)
        self._add_field("המתנה לתחילת דיבור", self.voice_timeout_control, app_settings, "כמה זמן לחכות לדיבור אחרי הפעלת ההאזנה לפני ביטול.", keywords="listen timeout speech start wait", advanced=True)
        self._add_field("כיול רעש רקע לפני האזנה", self.voice_ambient_control, app_settings, "0 מתחיל הכי מהר. הגדלה משפרת דיוק בסביבה רועשת אבל מוסיפה השהיה.", keywords="ambient noise calibration background", advanced=True)
        self._add_checkbox(self.voice_dynamic_energy_cb, app_settings, "מאפשר לספריית הזיהוי לשנות את סף הרגישות תוך כדי עבודה לפי רעש הרקע.", keywords="dynamic energy threshold noise", advanced=True)
        self._add_checkbox(self.voice_beep_cb, app_settings, "משמיע צלילי האזנה קצרים מהנכסים בתחילת האזנה, בסיום האזנה ובביטול מחוסר דיבור.", keywords="beep sound start stop listening timeout", advanced=True)
        self._add_section_header("עדכונים", app_settings)
        self._add_checkbox(
            self.update_auto_cb,
            app_settings,
            "כשאפשרות זו פעילה, סמארטי בודק עדכונים ברקע אחרי הפתיחה ולאחר מכן פעם בשעה. אם נמצאה גרסה חדשה, כפתור העדכון מופיע בראש הצ'אט.",
            keywords="updates release github version auto check",
            info=True,
        )
        app_settings.addWidget(self.update_status_lbl)
        app_settings.addWidget(self.check_updates_btn)
        app_settings.addStretch()

        self._add_internal_back(advanced, "מתקדם ומפתחים")
        self._add_field(
            "אמון HTTPS ורשת מסוננת",
            self.ssl_trust_card,
            advanced,
            "המצב הפעיל ומקור האמון מוצגים כאן תמיד. אפשר להשתמש במאגר Windows, לייבא "
            "תעודת שורש ציבורית של ספק הסינון, או לבחור במפורש תאימות ישנה ללא אימות תעודות.",
            keywords="ssl tls certificate ca windows trust network filter proxy תעודה סינון רשת",
            advanced=True,
            info=True,
        )
        self._add_checkbox(self.prevent_sleep_cb, advanced, "משאיר את Windows ער בזמן שסמארטי מבצע משימה פעילה, ומשחרר את הבקשה מיד בסיום או בביטול. המסך עדיין יכול להיכבות.", keywords="prevent sleep keep awake long running task hours windows", advanced=True)
        self._add_field("זמן המתנה לפקודות מחשב (שניות)", self.cmd_timeout, advanced, "משך הזמן המקסימלי שסמארטי ימתין לפקודת מערכת לפני עצירה.", keywords="command timeout shell seconds", advanced=True)
        self._add_field("זמן המתנה לכלים מותאמים אישית (שניות)", self.tool_timeout, advanced, "משך הזמן המקסימלי להרצת כלי מותאם אישית לפני שסמארטי מפסיק אותו.", keywords="custom tool timeout seconds", advanced=True)
        self._add_field("זמן המתנה לכלי MCP (שניות)", self.mcp_timeout, advanced, "משך הזמן המקסימלי שסמארטי ימתין לתשובה מכלי MCP.", keywords="mcp timeout external tool seconds", advanced=True)
        self._add_field("זמן כולל מקסימלי למשימה (שניות)", self.total_timeout, advanced, "0 פירושו ללא מגבלת זמן כוללת, כך שמשימות יכולות להימשך שעות. ערך חיובי עוצר את המשימה לאחר מספר השניות שהוגדר.", keywords="task timeout total max seconds unlimited long running hours", advanced=True)
        self._add_field("זמן המתנה לתשובת Codex יחידה (שניות)", self.codex_request_timeout, advanced, "מתאים גם לרמות חשיבה עמוקות. ברירת המחדל היא 30 דקות; אפשר להגדיל למשימות חריגות.", keywords="codex request timeout max reasoning seconds", advanced=True)
        self._add_field("זמן הצגת התראת הרשאה (שניות)", self.permission_notification_timeout, advanced, "0 פירושו ללא הגבלה: כאשר סמארטי ברקע, חלון ההרשאה הרגיל ייפתח בסמארטי וגם תופיע התראת Windows, והם יישארו מסונכרנים עד שתאשר או תדחה. מספר חיובי מבטל רק את התראת Windows אחרי הזמן הזה; חלון ההרשאה הרגיל נשאר פתוח.", keywords="permission approval notification timeout unlimited toast dialog", advanced=True)
        self._add_field("מגבלת תווים בתוצאת כלי", self.max_chars_edit, advanced, "מגביל את אורך פלט הכלים שנשלח חזרה למודל, כדי לשמור על יציבות ועל עלויות נמוכות.", keywords="tool output chars limit context token", advanced=True)
        self._add_field("תקציב טוקנים יומי", self.daily_token_budget, advanced, "0 פירושו ללא מגבלה קשיחה כרגע; הנתון נשמר לשימוש במדיניות תקציב.", keywords="daily token budget usage cost", advanced=True)
        self._add_field("תקציב עלות יומי בדולר", self.daily_cost_budget, advanced, "0 פירושו ללא מגבלה קשיחה כרגע; מוצג למעקב ובקרת עלויות.", keywords="daily cost budget usd money usage", advanced=True)
        self._add_field(
            "מספר סבבי פעולה מקסימלי",
            self.loops_control,
            advanced,
            "קובע כמה פעמים סמארטי יכול לחשוב, לבחור כלי ולעבד תוצאה באותה בקשה. הערך העליון מאפשר עבודה ללא מגבלת סבבים.",
            keywords="agent loops iterations max unlimited planning tool calls",
            advanced=True
        )
        self._add_field(
            "הרצת משימה מחזורית אחרי פספוס",
            self.background_catch_up_control,
            advanced,
            "כמה זמן אחרי השעה המתוכננת עדיין מותר לסמארטי להריץ משימה שהוחמצה. אחרי החלון הזה המשימה תדלג לפעם הבאה.",
            keywords="background recurring catch up missed scheduled task",
            advanced=True
        )
        self._add_section_header("מפתחים ולוגים", advanced)
        self._add_checkbox(self.developer_trace_cb, advanced, "שומר Trace פנימי של תכנון, בחירת כלים, תוצאות ביניים ותשובה סופית.", keywords="developer trace debug planning tool calls", advanced=True)
        self._add_checkbox(self.audit_log_cb, advanced, "שומר יומן אודיט מקומי של החלטות הרשאה, התחלת כלים וסיום כלים.", keywords="audit log policy tool execution", advanced=True)
        self._add_checkbox(self.redact_logs_cb, advanced, "מסתיר מפתחות, סיסמאות ופרטים רגישים מקובצי הלוג ככל האפשר.", keywords="redact logs secrets password privacy", advanced=True)
        self._add_field("תיקיות גישה לכלי MCP", self.mcp_allowed_dirs, advanced, "שורשי תיקיות שמותר להעביר לכלי MCP כתיאום גישה. זו אינה מגבלת כתיבה של סמארטי; כאשר ארגז חול פעיל, ארגז החול גובר על ההגדרה הזו.", keywords="mcp allowed directories folders roots external tools", advanced=True)
        refresh_logs_btn = QPushButton("רענן לוגים")
        refresh_logs_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        refresh_logs_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_logs_btn.clicked.connect(self.load_developer_logs)
        load_older_logs_btn = QPushButton("טען 500 שורות קודמות")
        load_older_logs_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        load_older_logs_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        load_older_logs_btn.clicked.connect(self.load_older_developer_logs)
        export_logs_btn = QPushButton()
        export_logs_btn.setFixedSize(36, 36)
        export_logs_btn.setStyleSheet(icon_button_css(36))
        export_logs_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        export_logs_btn.setToolTip("ייצוא הלוג לקובץ טקסט")
        set_themed_button_icon(
            export_logs_btn,
            ("export_log_icon", "export_json_icon", "save_done"),
            "E",
            20,
            clear_text=True,
        )
        export_logs_btn.clicked.connect(self.export_developer_log)
        clear_logs_btn = QPushButton("נקה לוג")
        clear_logs_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        clear_logs_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        clear_logs_btn.clicked.connect(self.clear_selected_developer_log)
        self.developer_log_line_limit = 500
        developer_log_panel = QWidget()
        developer_log_panel.setStyleSheet("background: transparent;")
        developer_log_panel_layout = QVBoxLayout(developer_log_panel)
        developer_log_panel_layout.setContentsMargins(0, 0, 0, 0)
        developer_log_panel_layout.setSpacing(8)
        log_actions = QGridLayout()
        log_actions.setHorizontalSpacing(8)
        log_actions.setVerticalSpacing(8)
        refresh_logs_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        load_older_logs_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        clear_logs_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        log_actions.addWidget(refresh_logs_btn, 0, 0)
        log_actions.addWidget(load_older_logs_btn, 0, 1)
        log_actions.addWidget(clear_logs_btn, 1, 0)
        log_actions.addWidget(export_logs_btn, 1, 1, Qt.AlignmentFlag.AlignLeft)
        log_actions.setColumnStretch(0, 1)
        log_actions.setColumnStretch(1, 1)
        developer_log_panel_layout.addLayout(log_actions)
        export_options = QGridLayout()
        export_options.setHorizontalSpacing(8)
        export_options.setVerticalSpacing(6)
        export_options.addWidget(QLabel("טווח ייצוא:"), 0, 0)
        self.export_log_lines_combo = NoScrollComboBox()
        for label, value in (
            ("500 שורות אחרונות", 500),
            ("1,000 שורות אחרונות", 1000),
            ("2,500 שורות אחרונות", 2500),
            ("5,000 שורות אחרונות", 5000),
            ("10,000 שורות אחרונות", 10000),
            ("כל הלוגים השמורים", 0),
        ):
            self.export_log_lines_combo.addItem(label, value)
        self.export_log_lines_combo.setCurrentIndex(1)
        self.export_log_lines_combo.setStyleSheet(COMBOBOX_CSS)
        self.export_log_lines_combo.setMinimumWidth(190)
        export_options.addWidget(self.export_log_lines_combo, 0, 1)
        self.export_redact_personal_cb = SmartiCheckBox("הסתר תוכן אישי")
        self.export_redact_personal_cb.setChecked(True)
        self.export_redact_personal_cb.setStyleSheet(CHECKBOX_CSS)
        self.export_redact_personal_cb.setToolTip(
            "מסיר מהעותק הודעות, פלטי כלים, זיכרונות ותוכן אישי אחר; נתונים טכניים וקודי שגיאה נשארים."
        )
        export_options.addWidget(self.export_redact_personal_cb, 1, 0, 1, 2)
        export_options.setColumnStretch(1, 1)
        developer_log_panel_layout.addLayout(export_options)
        self.developer_log_status = QLabel("")
        self.developer_log_status.setStyleSheet(muted_label_css(12))
        developer_log_panel_layout.addWidget(self.developer_log_status)
        self.developer_log_text = QTextEdit()
        self.developer_log_text.setReadOnly(True)
        self.developer_log_text.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
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
        developer_log_panel_layout.addWidget(self.developer_log_text)
        self._add_field("לוג מאוחד", developer_log_panel, advanced, "צפייה עצלה וייצוא של אירועי הסוכן, ספקי ה-AI, זמן הריצה, האבטחה, האבחון והמיומנויות מקובץ מתחלף אחד.", keywords="logs trace audit skills agent developer debug export privacy יומן לוגים מיומנויות אבטחה ייצוא", advanced=True)
        advanced.addStretch()
        self.load_developer_logs()

        self.settings_stack.setCurrentWidget(self.settings_home_page)

    def on_provider_change(self, text):
        text = normalize_provider_name(text)
        if hasattr(self, "local_fast_mode_field_container"):
            self.local_fast_mode_field_container.setVisible(text == "local")
        current_provider = normalize_provider_name(self.core.settings.get("api_mode", "gemini"))
        self._favorite_model_on_populate_provider = text if text != current_provider else None
        is_codex_signin = text == "openai_codex_signin"
        codex_worker = getattr(self, "codex_signin_worker", None)
        self._set_codex_signin_buttons(busy=bool(codex_worker and codex_worker.isRunning()))
        self._update_provider_key_help()
        if is_codex_signin:
            self.api_key_edit.set_secret("")
            self.api_key_edit.setPlaceholderText("לא נדרש מפתח עבור Codex sign-in")
            self.api_key_edit.setEnabled(False)
            self.api_key_field_container.setVisible(False)
            self.api_key_row.setVisible(False)
            self.api_key_help_link.setVisible(False)
            self.api_key_help_hint.setVisible(False)
            self.api_key_status.setVisible(False)
            self.codex_signin_field_container.setVisible(True)
            self.codex_signin_warning.setVisible(True)
            self.populate_models(provider_fallback_models(text), text)
            self._refresh_reasoning_effort_control(text)
            self._schedule_autosave()
            self._start_codex_signin_action("status")
            return
        self.api_key_field_container.setVisible(True)
        self.api_key_row.setVisible(True)
        self.api_key_status.setVisible(True)
        self.codex_signin_field_container.setVisible(False)
        self.codex_signin_warning.setVisible(False)
        self._refresh_reasoning_effort_control(text)
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
            self._ssl_settings_from_ui(),
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
        provider = normalize_provider_name(provider)
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
        if getattr(self, "_favorite_model_on_populate_provider", None) == provider:
            selected_model = self.model_combo.selected_model() if hasattr(self.model_combo, "selected_model") else self.model_combo.currentText()
            self._ensure_model_favorite(provider, selected_model, save=False)
            self._favorite_model_on_populate_provider = None
        if hasattr(self, "_refresh_reasoning_effort_control"):
            self._refresh_reasoning_effort_control(provider)
        self._schedule_autosave()

    def _reasoning_model_for_ui(self, provider=None):
        provider = normalize_provider_name(provider or self.provider_combo.currentText())
        selected = (
            self.model_combo.selected_model()
            if hasattr(self.model_combo, "selected_model")
            else self.model_combo.currentText()
        )
        selected = str(selected or "").strip()
        if not selected or "..." in selected:
            selected = str(
                self.core.settings.get(f"selected_{provider}_model")
                or provider_default_model(provider)
                or ""
            ).strip()
        return selected

    def _refresh_reasoning_effort_control(self, provider=None):
        if not hasattr(self, "reasoning_effort_combo"):
            return
        provider = normalize_provider_name(provider or self.provider_combo.currentText())
        model = self._reasoning_model_for_ui(provider)
        contract = model_reasoning_contract(provider, model)
        options = model_reasoning_options(provider, model)
        previous = self.reasoning_effort_combo.blockSignals(True)
        try:
            self.reasoning_effort_combo.clear()
            provider_default = str(contract.get("provider_default", "") or "")
            for value, label in options:
                if value == "auto":
                    if provider_default == "dynamic":
                        label = "אוטומטית — חשיבה דינמית של הספק"
                    elif provider_default == "provider":
                        label = "אוטומטית — ברירת הספק"
                    elif provider_default in MODEL_REASONING_LEVEL_LABELS:
                        default_label = MODEL_REASONING_LEVEL_LABELS[provider_default]
                        label = f"אוטומטית — ברירת הספק ({default_label})"
                self.reasoning_effort_combo.addItem(label, value)
            saved = model_reasoning_setting(self.core.settings, provider, model)
            index = self.reasoning_effort_combo.findData(saved)
            if index < 0 and self.reasoning_effort_combo.count():
                index = 0
            self.reasoning_effort_combo.setCurrentIndex(index)
        finally:
            self.reasoning_effort_combo.blockSignals(previous)
        if hasattr(self, "codex_reasoning_effort_field_container"):
            self.codex_reasoning_effort_field_container.setVisible(bool(options))

    def refresh_google_drive_status(self):
        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        return

    def connect_google_drive(self):
        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        return

    def disconnect_google_drive(self):
        # Google Drive settings UI is parked until OAuth sign-in is reworked.
        return

    def _email_provider_from_address(self, address):
        domain = str(address or "").lower().rsplit("@", 1)[-1] if "@" in str(address or "") else ""
        if domain in {"gmail.com", "googlemail.com"}:
            return "gmail"
        if domain in {"outlook.com", "hotmail.com", "live.com", "msn.com"}:
            return "outlook"
        if domain in {"yahoo.com", "ymail.com", "rocketmail.com"}:
            return "yahoo"
        return "custom"

    def _email_test_config_from_ui(self):
        user = self.email.text().strip() if hasattr(self, "email") else ""
        password = self.pwd.text().replace(" ", "") if hasattr(self, "pwd") else ""
        provider = self._email_provider_from_address(user)
        defaults = {
            "gmail": {"imap_host": "imap.gmail.com", "imap_port": 993, "smtp_host": "smtp.gmail.com", "smtp_port": 587},
            "outlook": {"imap_host": "outlook.office365.com", "imap_port": 993, "smtp_host": "smtp.office365.com", "smtp_port": 587},
            "yahoo": {"imap_host": "imap.mail.yahoo.com", "imap_port": 993, "smtp_host": "smtp.mail.yahoo.com", "smtp_port": 587},
            "custom": {"imap_host": "imap.gmail.com", "imap_port": 993, "smtp_host": "smtp.gmail.com", "smtp_port": 587},
        }.get(provider, {})

        def as_int(widget, fallback):
            try:
                return int(widget.text().strip())
            except Exception:
                return int(fallback)

        cfg = {
            "user": user,
            "password": password,
            "provider": provider,
            "imap_host": self.email_imap_host.text().strip() or defaults.get("imap_host", "imap.gmail.com"),
            "imap_port": as_int(self.email_imap_port, defaults.get("imap_port", 993)),
            "imap_ssl": bool(self.email_imap_ssl_cb.isChecked()),
            "smtp_host": self.email_smtp_host.text().strip() or defaults.get("smtp_host", "smtp.gmail.com"),
            "smtp_port": as_int(self.email_smtp_port, defaults.get("smtp_port", 587)),
            "smtp_ssl": bool(self.email_smtp_ssl_cb.isChecked()),
            "smtp_starttls": bool(self.email_smtp_starttls_cb.isChecked()),
        }
        if not cfg["user"] or not cfg["password"]:
            raise ValueError("חסרים כתובת אימייל או סיסמת אפליקציה.")
        return cfg

    def _ssl_settings_from_ui(self):
        if hasattr(self, "ssl_trust_card"):
            return self.ssl_trust_card.ssl_snapshot()
        snapshot = copy.deepcopy(self.core.settings or {})
        snapshot["_ssl_data_dir"] = USER_DATA_DIR
        snapshot["_ssl_legacy_insecure_session_enabled"] = bool(
            getattr(self.core, "_ssl_legacy_insecure_session_enabled", False)
        )
        return snapshot

    def test_email_connection(self):
        worker = getattr(self, "email_test_worker", None)
        if worker and worker.isRunning():
            return
        if hasattr(self, "email_test_status"):
            self.email_test_status.setText("בודק חיבור לאימייל...")
        if hasattr(self, "email_test_btn"):
            self.email_test_btn.setEnabled(False)
            self.email_test_btn.clearFocus()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        try:
            email_cfg = self._email_test_config_from_ui()
            ssl_settings = self._ssl_settings_from_ui()
        except Exception as exc:
            if hasattr(self, "email_test_btn"):
                self.email_test_btn.setEnabled(True)
            if hasattr(self, "email_test_status"):
                self.email_test_status.setText(f"החיבור נכשל: {exc}")
                self.email_test_status.setStyleSheet(
                    f"color: {DANGER_COLOR}; font-size: 12px; background: transparent;"
                )
            return
        worker = EmailConnectionTestWorker(email_cfg, ssl_settings)
        self.email_test_worker = worker
        worker.finished_signal.connect(
            self._on_email_test_finished_current,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_email_test_finished_current(self, ok, message):
        self._on_email_test_finished(self.sender(), ok, message)

    def _on_email_test_finished(self, worker, ok, message):
        if getattr(self, "email_test_worker", None) is worker:
            self.email_test_worker = None
        if hasattr(self, "email_test_btn"):
            self.email_test_btn.setEnabled(True)
        text = str(message or "").strip()
        if hasattr(self, "email_test_status"):
            self.email_test_status.setText(text if ok else f"החיבור נכשל: {text or 'לא התקבלה שגיאה מפורטת'}")
            self.email_test_status.setStyleSheet(
                f"color: {ACCENT_SECONDARY_COLOR if ok else DANGER_COLOR}; font-size: 12px; background: transparent;"
            )

    def _register_autosave_handlers(self):
        combos = [
            self.provider_combo,
            self.tts_voice_combo,
            self.codex_reasoning_effort_combo,
            self.conversation_title_mode_combo,
            self.skill_unknown_scan_combo,
        ]
        combos.extend(self.policy_combos.values())
        for combo in combos:
            combo.currentIndexChanged.connect(lambda _=None: self._schedule_autosave())
        if hasattr(self.model_combo, "modelCommitted"):
            self.model_combo.modelCommitted.connect(self._on_model_committed)
        else:
            self.model_combo.currentIndexChanged.connect(lambda _=None: self._schedule_autosave())
        self.theme_combo.currentIndexChanged.connect(self.on_theme_mode_change)
        self.autonomy_combo.currentIndexChanged.connect(self.on_autonomy_profile_change)
        self.permission_combo.currentIndexChanged.connect(self.on_permission_profile_change)

        for cb in [
            self.sandbox_cb, self.sandbox_read_outside_cb, self.redact_logs_cb, self.audit_log_cb,
            self.developer_trace_cb, self.raw_shell_approval_cb, self.marketplace_approval_cb,
            self.browser_auto_cb, self.computer_control_cb, self.mcp_cb, self.skills_beta_cb,
            self.tool_search_catalog_cb,
            self.web_canvas_cb, self.web_canvas_remote_images_cb,
            self.update_auto_cb,
            self.tts_cb, self.tts_voice_cb, self.cloud_upload_cb,
            self.write_outside_dirs_approval_cb, self.mcp_pin_cb, self.prevent_sleep_cb,
            self.email_imap_ssl_cb, self.email_smtp_ssl_cb, self.email_smtp_starttls_cb,
            self.voice_dynamic_energy_cb, self.voice_beep_cb, self.local_fast_mode_cb
        ]:
            cb.stateChanged.connect(lambda _=None: self._schedule_autosave())
        self.ssl_trust_card.settingsChanged.connect(self._schedule_autosave)
        self.custom_permissions_cb.stateChanged.connect(lambda _=None: self.on_custom_permissions_change())

        self.api_key_edit.secretEdited.connect(self._on_api_key_edited)
        self.api_key_edit.editingFinished.connect(self._validate_current_api_key_before_save)
        self.tavily_key.secretEdited.connect(lambda _=None: self._schedule_autosave())

        for edit in [
            self.tavily_key, self.local_url, self.email, self.pwd,
            self.email_from_name, self.email_imap_host, self.email_imap_port,
            self.email_smtp_host, self.email_smtp_port, self.email_max_attachment_mb,
            self.cmd_timeout, self.tool_timeout, self.mcp_timeout, self.max_chars_edit,
            self.total_timeout, self.codex_request_timeout, self.permission_notification_timeout, self.daily_token_budget, self.daily_cost_budget
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
            self.voice_ambient_slider, self.background_catch_up_slider
        ]:
            slider.valueChanged.connect(lambda _=None: self._schedule_autosave())

    def _on_model_committed(self, model):
        provider = normalize_provider_name(self.provider_combo.currentText())
        self.core.settings.setdefault("selected_model_source", {})[provider] = (
            MODEL_SELECTION_SOURCE_USER
        )
        self.core.settings["model_selection_provenance_version"] = (
            MODEL_SELECTION_PROVENANCE_VERSION
        )
        self._ensure_model_favorite(provider, model, save=False)
        if hasattr(self, "_refresh_reasoning_effort_control"):
            self._refresh_reasoning_effort_control(provider)
        self._schedule_autosave()

    def _schedule_autosave(self):
        if getattr(self, "_suppress_autosave", False) or not getattr(self, "_settings_ready", False):
            return
        self._set_save_status("saving")
        self.autosave_timer.start()

    def _on_api_key_edited(self, _text=""):
        if getattr(self, "_suppress_autosave", False):
            return
        provider = normalize_provider_name(self.provider_combo.currentText())
        if provider in {"local", "openai_codex_signin"}:
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
        if provider in {"local", "openai_codex_signin"}:
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
            self._ssl_settings_from_ui(),
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
        index = self.permission_combo.currentIndex()
        if index < 0:
            return "custom"
        return {1: "locked_down", 2: "balanced", 3: "max_autonomy"}.get(index + 1, "balanced")

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
            if label.property("smartiUpdateStatusPill"):
                self._style_update_status_label()
                continue
            if label.property("smartiHighContrastLink"):
                apply_high_contrast_link_label(label)
                continue
            if label.property("smartiInfoBubble"):
                label.setStyleSheet(muted_label_css(12) + f" padding: 10px 12px; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 14px; background: {GLASS_COLOR};")
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
            if hasattr(combo, "apply_theme"):
                combo.apply_theme()
            else:
                combo.setStyleSheet(COMBOBOX_CSS)
        for model_picker in self.findChildren(SearchableModelComboBox):
            model_picker.apply_theme()
        for segment in self.findChildren(SegmentedControl):
            segment.apply_theme()
        for edit in self.findChildren(QLineEdit):
            if edit.objectName() == "SettingsSearchBox":
                edit.setStyleSheet(self._search_box_css())
            else:
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
            if button.property("smartiInfoButton"):
                button.setStyleSheet(
                    f"QPushButton {{ background: {ACCENT_TINT}; color: {ACCENT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
                    "border-radius: 12px; padding: 0px; font-size: 12px; font-weight: 900; }}"
                    f"QPushButton:hover {{ background: {HOVER_TINT}; border-color: {LINE_COLOR}; color: {TEXT_COLOR}; }}"
                )
                continue
            parent = button.parent()
            if parent and parent.objectName() == "SegmentedControl":
                continue
            button.setStyleSheet(SECONDARY_BUTTON_CSS)
        if hasattr(self, "settings_search_edit"):
            self.settings_search_edit.setStyleSheet(self._search_box_css())
        if hasattr(self, "settings_search_wrapper"):
            self.settings_search_wrapper.setStyleSheet(self._search_wrapper_css(False))
        if hasattr(self, "advanced_toggle_widget"):
            self.advanced_toggle_widget.setStyleSheet(self._advanced_toggle_css())
        for container in getattr(self, "_settings_field_containers", {}).values():
            container.setStyleSheet(self._field_container_css(False))
        if hasattr(self, "search_results_list"):
            self.search_results_list.setStyleSheet(
                f"QListWidget {{ background: transparent; color: {TEXT_COLOR}; border: none; outline: none; }}"
                f"QListWidget::item {{ background: {GLASS_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 16px; padding: 10px 12px; }}"
                f"QListWidget::item:hover {{ background: {HOVER_TINT}; border-color: {LINE_COLOR}; }}"
                f"QListWidget::item:selected {{ background: {ACCENT_TINT_STRONG}; border-color: {ACCENT_COLOR}; color: {TEXT_COLOR}; }}"
            )
        for toolbar in self.findChildren(QFrame, "SettingsToolbar"):
            toolbar.setStyleSheet(self._settings_toolbar_css())
        refresh_themed_widget_icons(self)
        for toggle in self.findChildren(SmartiCheckBox):
            toggle.update()
        for card in self.findChildren(SettingsNavCard):
            card.apply_theme()
        for slider in self.findChildren(RtlFillSlider):
            slider.setStyleSheet(SLIDER_CSS)
        for label in self.findChildren(QLabel):
            if label.property("smartiUpdateStatusPill"):
                self._style_update_status_label()
                continue
            if label.property("smartiValuePill"):
                label.setStyleSheet(self._value_pill_css())
        if hasattr(self, "developer_log_text"):
            self.developer_log_text.setStyleSheet(LOG_TEXT_CSS)
        if hasattr(self, "settings_save_status"):
            self._set_save_status(getattr(self, "_save_status", "idle"))
        if hasattr(self, "api_key_help_link"):
            self._update_provider_key_help()
        if hasattr(self, "tavily_key_help_link"):
            self._set_external_link(self.tavily_key_help_link, provider_help_url(secret_key="tavily_api_key"), "קבל מפתח")
        if hasattr(self, "ssl_trust_card"):
            self.ssl_trust_card.apply_theme()
        self._refresh_developer_log_buttons()

    def _apply_profile_to_widgets(self, profile_key):
        profile = AUTONOMY_PROFILES.get(profile_key, AUTONOMY_PROFILES["balanced"])
        self.permission_combo.setCurrentIndex(max(0, min(2, profile["permission_level"] - 1)))
        action_index = {"allow": 0, "ask": 1, "deny": 2}
        for cap, combo in self.policy_combos.items():
            combo.setCurrentIndex(action_index.get(profile["policy_matrix"].get(cap, "ask"), 1))
        self.raw_shell_approval_cb.setChecked(bool(profile["raw_shell_requires_approval"]))
        self.marketplace_approval_cb.setChecked(bool(profile["marketplace_install_requires_approval"]))
        self.cloud_upload_cb.setChecked(bool(profile["require_approval_for_cloud_upload"]))
        self.write_outside_dirs_approval_cb.setChecked(bool(profile["write_outside_allowed_dirs_requires_approval"]))

    def _set_custom_permissions_ui(self, enabled):
        enabled = bool(enabled)
        if hasattr(self, "policy_field_container"):
            self.policy_field_container.setVisible(enabled)
        if enabled:
            self.permission_combo.clearSelection(emit=False)
        elif self.permission_combo.currentIndex() < 0:
            self.permission_combo.setCurrentIndex(1, emit=False)

    def on_custom_permissions_change(self):
        if getattr(self, "_suppress_autosave", False):
            return
        enabled = self.custom_permissions_cb.isChecked()
        self._suppress_autosave = True
        try:
            self._set_custom_permissions_ui(enabled)
            if not enabled:
                profile_key = self._permission_profile_key()
                profile_keys = [key for key, _ in self.autonomy_options]
                if profile_key in profile_keys:
                    self.autonomy_combo.setCurrentIndex(profile_keys.index(profile_key))
                self._apply_profile_to_widgets(profile_key)
        finally:
            self._suppress_autosave = False
        self._schedule_autosave()

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
        if profile_key == "custom":
            return
        profile_keys = [key for key, _ in self.autonomy_options]
        self._suppress_autosave = True
        try:
            if hasattr(self, "custom_permissions_cb"):
                self.custom_permissions_cb.setChecked(False)
                self._set_custom_permissions_ui(False)
            if profile_key in profile_keys:
                self.autonomy_combo.setCurrentIndex(profile_keys.index(profile_key))
            self._apply_profile_to_widgets(profile_key)
        finally:
            self._suppress_autosave = False
        self._schedule_autosave()

    def _save_from_ui(self):
        if getattr(self, "_suppress_autosave", False) or not getattr(self, "_settings_ready", False):
            return
        before = copy.deepcopy(self.core.settings)
        provider = normalize_provider_name(self.provider_combo.currentText())
        selected_model = self.model_combo.selected_model() if hasattr(self.model_combo, "selected_model") else self.model_combo.currentText()
        self.core.settings["api_mode"] = provider
        reasoning_model = str(selected_model or "").strip()
        if not reasoning_model or "..." in reasoning_model:
            reasoning_model = str(
                self.core.settings.get(f"selected_{provider}_model")
                or provider_default_model(provider)
                or ""
            ).strip()
        if model_reasoning_contract(provider, reasoning_model):
            set_model_reasoning_setting(
                self.core.settings,
                provider,
                reasoning_model,
                self.reasoning_effort_combo.currentData(),
            )
        custom_permissions_enabled = bool(self.custom_permissions_cb.isChecked())
        self.core.settings["custom_permission_profile_enabled"] = custom_permissions_enabled
        self.core.settings["autonomy_mode"] = "custom" if custom_permissions_enabled else self._autonomy_profile_key()
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
        title_mode = str(self.conversation_title_mode_combo.currentData() or "ai").strip().lower()
        self.core.settings["conversation_title_generation_mode"] = (
            title_mode if title_mode in {"ai", "local"} else "ai"
        )
        self.core.settings["local_fast_mode_enabled"] = self.local_fast_mode_cb.isChecked()
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
        self.core.settings["enable_tool_search_catalog"] = self.tool_search_catalog_cb.isChecked()
        self.core.settings["skills_load_watch"] = True
        scan_policy_index = max(0, min(self.skill_unknown_scan_combo.currentIndex(), len(self.skill_unknown_scan_options) - 1))
        self.core.settings["skill_install_unknown_scan_policy"] = self.skill_unknown_scan_options[scan_policy_index][0]
        self.core.settings["enable_visual_surfaces"] = self.web_canvas_cb.isChecked()
        self.core.settings["enable_web_canvas"] = self.web_canvas_cb.isChecked()
        self.core.settings["enable_canvas_remote_images"] = bool(
            self.web_canvas_cb.isChecked() and self.web_canvas_remote_images_cb.isChecked()
        )
        self.core.settings["updates_auto_check"] = self.update_auto_cb.isChecked()
        self.core.settings["updates_check_interval_hours"] = 1
        self.core.settings["enable_browser_automation"] = self.browser_auto_cb.isChecked()
        self.core.settings["enable_computer_control"] = self.computer_control_cb.isChecked()
        self.core.settings["privacy_redact_logs"] = self.redact_logs_cb.isChecked()
        self.core.settings.setdefault("privacy", {})["redact_logs"] = self.redact_logs_cb.isChecked()
        self.core.settings["audit_log_enabled"] = self.audit_log_cb.isChecked()
        self.core.settings.setdefault("privacy", {})["audit_enabled"] = self.audit_log_cb.isChecked()
        self.core.settings["enable_developer_trace"] = self.developer_trace_cb.isChecked()
        self.core.settings["raw_shell_requires_approval"] = self.raw_shell_approval_cb.isChecked()
        self.core.settings["marketplace_install_requires_approval"] = self.marketplace_approval_cb.isChecked()
        if custom_permissions_enabled:
            try:
                previous_level = int(before.get("permission_level", 2) or 2)
            except Exception:
                previous_level = 2
            self.core.settings["permission_level"] = previous_level if previous_level in {1, 2, 3} else 2
        else:
            self.core.settings["permission_level"] = max(0, self.permission_combo.currentIndex()) + 1
        action_by_index = {0: "allow", 1: "ask", 2: "deny"}
        self.core.settings["policy_matrix"] = {cap: action_by_index.get(combo.currentIndex(), "ask") for cap, combo in self.policy_combos.items()}
        self.core.settings["require_approval_for_cloud_upload"] = self.cloud_upload_cb.isChecked()
        self.core.settings["write_outside_allowed_dirs_requires_approval"] = self.write_outside_dirs_approval_cb.isChecked()
        self.core.settings["mcp_require_pinned_versions"] = self.mcp_pin_cb.isChecked()
        ssl_values = self.ssl_trust_card.settings_values()
        for key in (
            "ssl_trust_mode",
            "ssl_custom_ca_path",
            "ssl_filter_setup_completed",
            "ssl_legacy_insecure_allowed_hosts",
            "ssl_trust_migration_version",
            "allow_insecure_ssl_compat",
        ):
            self.core.settings[key] = copy.deepcopy(ssl_values[key])
        self.core.settings["prevent_sleep_during_active_task"] = self.prevent_sleep_cb.isChecked()
        self.core.settings["sandbox_enabled"] = self.sandbox_cb.isChecked()
        self.core.settings["sandbox_root_dir"] = self.sandbox_root_picker.path() or OUTPUTS_DIR
        self.core.settings["sandbox_allow_read_outside"] = self.sandbox_read_outside_cb.isChecked()
        default_output_dir = self.default_output_dir_picker.path() or OUTPUTS_DIR
        self.core.settings["default_output_dir"] = default_output_dir
        self.core.settings["allowed_write_dirs"] = [default_output_dir]
        self.core.settings["mcp_allowed_directories"] = self.mcp_allowed_dirs.paths() or [APP_DIR]
        for key, widget, default in [("command_timeout_seconds", self.cmd_timeout, 60), ("tool_timeout_seconds", self.tool_timeout, 120), ("mcp_timeout_seconds", self.mcp_timeout, 60), ("max_tool_output_chars", self.max_chars_edit, 100000), ("codex_request_timeout_seconds", self.codex_request_timeout, 1800)]:
            try: self.core.settings[key] = max(5, int(widget.text().strip()))
            except: self.core.settings[key] = default
        try:
            self.core.settings["max_total_task_seconds"] = max(0, int(self.total_timeout.text().strip()))
        except Exception:
            self.core.settings["max_total_task_seconds"] = 0
        try:
            self.core.settings["permission_notification_timeout_seconds"] = max(0, int(self.permission_notification_timeout.text().strip()))
        except Exception:
            self.core.settings["permission_notification_timeout_seconds"] = 0
        self.core.settings.setdefault("budgets", {})
        for key, widget in [("daily_token_budget", self.daily_token_budget), ("daily_cost_budget_usd", self.daily_cost_budget)]:
            try:
                value = float(widget.text().strip())
                self.core.settings["budgets"][key] = max(0, int(value) if key == "daily_token_budget" else value)
            except Exception:
                self.core.settings["budgets"][key] = 0
        slider_loops = self.loops_slider.value()
        self.core.settings["max_agent_loops"] = 0 if slider_loops > 30 else slider_loops
        catch_up_slider_value = int(self.background_catch_up_slider.value())
        self.core.settings["background_recurring_catch_up_window_minutes"] = -1 if catch_up_slider_value >= 181 else catch_up_slider_value
        changed = [key for key in sorted(set(before.keys()) | set(self.core.settings.keys())) if before.get(key) != self.core.settings.get(key)]
        if selected_model and selected_model != "טוען מודלים...":
            self.main_window.subtitle.setText(self.main_window.format_model_name(selected_model))
        if not changed:
            self._set_save_status("idle")
            return
        self.core._save_settings()
        ssl_reload_keys = {
            "ssl_trust_mode",
            "ssl_custom_ca_path",
            "ssl_filter_setup_completed",
            "ssl_legacy_insecure_allowed_hosts",
            "ssl_trust_migration_version",
            "allow_insecure_ssl_compat",
        }
        model_reload_keys = {"api_mode", "local_server_url"} | model_provider_secret_keys() | ssl_reload_keys
        needs_model_reload = any(key in model_reload_keys or key.startswith("selected_") for key in changed)
        needs_canvas_prompt_refresh = any(
            key in {"enable_visual_surfaces", "enable_web_canvas", "enable_canvas_remote_images"}
            for key in changed
        )
        needs_fast_mode_prompt_refresh = "local_fast_mode_enabled" in changed
        needs_mcp_refresh = any(key in {
            "enable_mcp_clawhub", "enable_skills_beta", "mcp_require_pinned_versions",
            "mcp_allowed_directories",
            *ssl_reload_keys,
        } for key in changed)
        if needs_mcp_refresh:
            self.core._sync_ssl_compat_env()
            self.core._sync_trusted_mcp_packages()
            self.core._ensure_mcp_config()
        if needs_model_reload or needs_canvas_prompt_refresh or needs_fast_mode_prompt_refresh:
            self.core.system_prompt = self.core._load_system_prompt()
        if needs_model_reload:
            self.core.setup_model()
        logging.info(f"SETTINGS | auto_saved | changed={', '.join(changed[:16])}{'...' if len(changed) > 16 else ''}")
        if getattr(self.core, "audit_logger", None):
            self.core.audit_logger.record("settings_auto_save", {"changed": changed}, self.core.settings)
        self._set_save_status("saved")
        if hasattr(self.main_window, "refresh_favorite_model_controls"):
            self.main_window.refresh_favorite_model_controls()
        if hasattr(self.main_window, "refresh_quick_autonomy_controls"):
            self.main_window.refresh_quick_autonomy_controls()
        if hasattr(self.main_window, "refresh_local_fast_mode_control"):
            self.main_window.refresh_local_fast_mode_control()

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
            return _tail_text_file(path, max_lines)
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
        # Compatibility shim for old navigation actions: all event families
        # now share the unified log.
        self.load_developer_logs()

    def _selected_developer_log_label(self):
        return "הלוג המאוחד של סמארטי"

    def clear_selected_developer_log(self):
        label = self._selected_developer_log_label()
        dlg = QMessageBox(self)
        dlg.setWindowTitle("ניקוי לוג")
        dlg.setText(f"לנקות את {label}?")
        dlg.setInformativeText("הפעולה תמחק את הקובץ הפעיל בלבד. קובצי סבב ישנים יישארו עד להחלפתם האוטומטית.")
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dlg.button(QMessageBox.StandardButton.Yes).setText("נקה")
        dlg.button(QMessageBox.StandardButton.No).setText("בטל")
        if dlg.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            clear_unified_log_file()
            logging.info("DEVELOPER_LOG | cleared | selected=unified")
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
        limit = max(100, int(getattr(self, "developer_log_line_limit", 500) or 500))
        log_rows = _unified_log_lines(limit)
        lines = ["=== SmartiAI Unified Log ==="]
        lines.extend(log_rows or ["אין עדיין רשומות לוג."])
        if hasattr(self, "developer_log_text"):
            self.developer_log_text.setPlainText("\n".join(lines))
            if hasattr(self, "developer_log_status"):
                self.developer_log_status.setText(
                    f"מוצגות {len(log_rows):,} השורות האחרונות. קבצים ישנים יותר נטענים רק לפי דרישה."
                )
            QTimer.singleShot(0, self._reset_developer_log_view)

    def load_older_developer_logs(self):
        self.developer_log_line_limit = min(
            20_000,
            max(500, int(getattr(self, "developer_log_line_limit", 500) or 500)) + 500,
        )
        self.load_developer_logs()

    def export_developer_log(self):
        selected_lines = 1000
        if hasattr(self, "export_log_lines_combo"):
            selected_lines = int(self.export_log_lines_combo.currentData() or 0)
        default_name = f"SmartiAI-log-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}.txt"
        documents_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        default_path = os.path.join(documents_dir or os.path.expanduser("~"), default_name)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "ייצוא הלוג של SmartiAI",
            default_path,
            "קובץ טקסט (*.txt);;כל הקבצים (*.*)",
        )
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".txt"
        hide_personal = bool(
            hasattr(self, "export_redact_personal_cb")
            and self.export_redact_personal_cb.isChecked()
        )
        try:
            rows = _unified_log_lines(selected_lines)
            if hide_personal:
                rows = sanitize_log_export_lines(rows, self.core.settings)
            header = [
                "SmartiAI Unified Diagnostic Log Export",
                f"Exported: {datetime.now().isoformat(timespec='seconds')}",
                f"Application version: {APP_VERSION}",
                f"Requested lines: {'all retained logs' if selected_lines <= 0 else selected_lines}",
                f"Exported lines: {len(rows)}",
                f"Personal content hidden: {'yes' if hide_personal else 'no'}",
                "",
            ]
            with open(path, "w", encoding="utf-8-sig", newline="\n") as handle:
                handle.write("\n".join(header + rows))
                handle.write("\n")
            logging.info(
                "DEVELOPER_LOG | exported | lines=%s | personal_hidden=%s",
                len(rows),
                hide_personal,
            )
            logging.info("PERSONAL | kind=log_export_path | content=%s", path)
            QMessageBox.information(self, "ייצוא לוג", f"הלוג נשמר בהצלחה:\n{path}")
        except Exception as exc:
            logging.exception("Developer log export failed: %s", exc)
            QMessageBox.warning(self, "שגיאה בייצוא לוג", str(exc))

    def _reset_developer_log_view(self):
        if not hasattr(self, "developer_log_text"):
            return
        self.scroll_developer_log("bottom")
        hbar = self.developer_log_text.horizontalScrollBar()
        hbar.setValue(hbar.minimum())

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
        hbar = self.developer_log_text.horizontalScrollBar()
        hbar.setValue(hbar.minimum())

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
        scroll_canvas = QWidget()
        scroll_canvas.setStyleSheet("background: transparent;")
        scroll_canvas_layout = QHBoxLayout(scroll_canvas)
        scroll_canvas_layout.setDirection(QBoxLayout.Direction.LeftToRight)
        scroll_canvas_layout.setContentsMargins(24, 0, 24, 0)
        scroll_canvas_layout.addStretch(1)
        content = QWidget()
        content.setMaximumWidth(960)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 8, 0, 8)
        content_layout.setSpacing(16)
        scroll_canvas_layout.addWidget(content, 10)
        scroll_canvas_layout.addStretch(1)
        self.scroll.setWidget(scroll_canvas)
        layout.addWidget(self.scroll)

        hero = QFrame()
        hero.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {GLASS_STRONG_COLOR}, stop:0.55 {PANEL_ELEVATED_COLOR}, stop:1 {CARD_GRADIENT_END}); "
            f"border: 1px solid {SOFT_LINE_COLOR}; border-radius: 20px; }}"
            "QLabel { border: none; background: transparent; }"
        )
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 16, 18, 18)
        hero_layout.setSpacing(12)

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
            logo_lbl.setFont(app_font(46, QFont.Weight.Bold))
            logo_lbl.setStyleSheet(f"color: {ACCENT_COLOR}; border: none; background: transparent;")

        hero_text = QVBoxLayout()
        hero_text.setSpacing(7)
        app_name = QLabel("Smarti AI Agent for Windows")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_name.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 20px; font-weight: 800; border: none;")
        app_name.setWordWrap(True)
        tagline = QLabel("סוכן עבודה אישי ל-Windows שמחבר צ'אט, כלים מקומיים, קבצים, דפדפן, אימייל, קנבס חי, זיכרון שימושי ומשימות רקע תחת בקרות בטיחות ברורות.")
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
            "סמארטי בנוי לעבודה יומיומית שבה מודל לא רק עונה, אלא גם עוזר לבצע: הוא יכול לפרק משימה, להפעיל כלים, לעבוד מול מקורות מקומיים ורשתיים, לשמור הקשר בזיכרון, להציג תוצרים חזותיים בקנבס ולחזור עם תוצאה שאפשר להשתמש בה מיד. רמות האוטונומיה, ההרשאות והלוגים נשארות בשליטת המשתמש."
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
            ("מודלים וספקים", "בחירה בין ספקי מודלים, Codex sign-in, מודלים מועדפים ועוצמת חשיבה למשימות שדורשות יותר עומק."),
            ("קבצים ומסמכים", "חיפוש, קריאה, סיכום, OCR, יצירת קבצי טקסט ועבודה עם תיקיות בלי לאבד את הקשר השיחה."),
            ("קנבס חי", "יצירת תוצרים חזותיים ואינטראקטיביים מקומיים: דשבורדים, תרשימים, טפסים, מצגות קטנות וממשקי בדיקה."),
            ("אינטרנט ודפדפן", "חיפוש מידע עדכני, קריאת אתרים ואוטומציה בדפדפן ייעודי כאשר המשימה דורשת פעולה באתר."),
            ("משימות רקע ואימייל", "תזכורות, בדיקות מחזוריות, חיפוש וקריאת מיילים, טיוטות, שליחה וניהול קבצים מצורפים."),
            ("בטיחות, זיכרון ו-Diagnostic", "פרופיל בטיחות, טבלת יכולות פרטנית, זיכרון RAG מקומי, נתוני שימוש ובדיקות Diagnostic לתקלות נפוצות."),
        ]
        for heading, body in feature_items:
            features.addWidget(self._feature_card(heading, body))
        content_layout.addLayout(features)

        content_layout.addWidget(self._section_title("דוגמאות יומיומיות"))
        examples = [
            "קרא מסמך ארוך, חלץ סעיפים לביצוע, צור סיכום קצר והכן טיוטת מייל המשך.",
            "בנה קנבס עם תרשים, טבלת נתונים או טופס קטן מתוך מידע שנאסף בשיחה.",
            "בדוק פעם ביום תחזית, עומסי תנועה, מחיר מוצר או תיבת מייל וסכם רק כשיש שינוי חשוב.",
            "סרוק תיקייה של קבלות או מסמכים, מצא כפילויות, ארגן שמות קבצים והכן תקציר.",
            "אבחן למה כלי, מודל, דפדפן או קנבס לא עובדים דרך Smarti Diagnostic לפני שמתחילים לחפש ידנית.",
        ]
        for example in examples:
            content_layout.addWidget(self._example_row(example))

        note = QFrame()
        note.setStyleSheet(card_css(12, 8))
        note_layout = QVBoxLayout(note)
        note_layout.setSpacing(6)
        note_title = QLabel("פרטיות ובטיחות")
        note_title.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 15px; font-weight: 800; border: none;")
        note_body = QLabel("פעולות רגישות נשלטות דרך פרופיל הבטיחות ומדיניות הכלים. אפשר להגדיר אישורים פרטניים, ארגז חול, מגבלות כתיבה ושליחה לענן. מחיקת קבצים עוברת לסל המחזור, וסודות נשמרים במנגנוני האחסון המאובטחים של Windows כשהם זמינים.")
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
        card.setStyleSheet(
            f"QFrame {{ background: {GLASS_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 12px; }}"
            f"QFrame:hover {{ background: {HOVER_TINT}; border-color: {LINE_COLOR}; }}"
            "QLabel { border: none; background: transparent; }"
        )
        card.setMinimumHeight(98)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
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
