"""Theme tokens, stylesheet snippets, and generated UI assets."""
from .common import *

# ==========================================
# Smarti premium UI design system
# ==========================================

THEME_OPTIONS = ("system", "dark", "light")
DEFAULT_THEME_MODE = "dark"

BRAND_ACCENT_COLOR = "#35D9FF"
BRAND_SECONDARY_COLOR = "#88FFB8"
BRAND_PINK_COLOR = "#FF4DDD"
BRAND_VIOLET_COLOR = "#8E6BFF"
BRAND_WARM_COLOR = BRAND_PINK_COLOR
DANGER_COLOR = "#FF5F7E"

THEME_PALETTES = {
    "dark": {
        "BG_COLOR": "#020412",
        "BG_ELEVATED_COLOR": "#050A1C",
        "PANEL_COLOR": "#071126",
        "PANEL_ELEVATED_COLOR": "#0B1A37",
        "FIELD_COLOR": "#0D1F3F",
        "FIELD_HOVER_COLOR": "#112B54",
        "TEXT_COLOR": "#F8FBFF",
        "MUTED_TEXT_COLOR": "#BAC8EA",
        "SUBTLE_TEXT_COLOR": "#8090B8",
        "ACCENT_COLOR": BRAND_ACCENT_COLOR,
        "ACCENT_SECONDARY_COLOR": BRAND_SECONDARY_COLOR,
        "ACCENT_PINK_COLOR": BRAND_PINK_COLOR,
        "ACCENT_WARM_COLOR": BRAND_PINK_COLOR,
        "ACCENT_TEXT_COLOR": "#04101C",
        "LINE_COLOR": "rgba(53,217,255,0.38)",
        "SOFT_LINE_COLOR": "rgba(142,107,255,0.34)",
        "GLASS_COLOR": "rgba(8,18,43,0.76)",
        "GLASS_STRONG_COLOR": "rgba(8,20,48,0.92)",
        "MESH_A": "#020412",
        "MESH_B": "#061133",
        "MESH_C": "#0A2050",
        "MESH_D": "#160627",
        "USER_BUBBLE_COLOR": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0899E8, stop:0.34 #22D8FF, stop:0.64 #34F5DF, stop:1 #78F7B1)",
        "USER_BUBBLE_BORDER": "rgba(136,255,184,0.62)",
        "INPUT_GRADIENT_END": "#0A2D56",
        "CARD_GRADIENT_END": "#0A1834",
        "TOP_GRADIENT_A": "#040819",
        "TOP_GRADIENT_B": "#081534",
        "TOP_GRADIENT_C": "#18082A",
        "MENU_BG_COLOR": "#091833",
        "BUBBLE_AGENT_END": "#0E1E3F",
        "BUBBLE_USER_TEXT": "#03101A",
        "CODE_BG_COLOR": "rgba(1,5,17,0.72)",
        "HOVER_TINT": "rgba(136,255,184,0.13)",
        "ACCENT_TINT": "rgba(53,217,255,0.13)",
        "ACCENT_TINT_STRONG": "rgba(255,77,221,0.20)",
        "FIELD_TEXT_COLOR": "#FFFFFF",
    },
    "light": {
        "BG_COLOR": "#F4F8FF",
        "BG_ELEVATED_COLOR": "#FFFFFF",
        "PANEL_COLOR": "#EDF5FF",
        "PANEL_ELEVATED_COLOR": "#DDEBFF",
        "FIELD_COLOR": "#E5F0FF",
        "FIELD_HOVER_COLOR": "#D7E8FF",
        "TEXT_COLOR": "#06162C",
        "MUTED_TEXT_COLOR": "#3F5579",
        "SUBTLE_TEXT_COLOR": "#6C7896",
        "ACCENT_COLOR": "#006D9B",
        "ACCENT_SECONDARY_COLOR": "#057D5D",
        "ACCENT_PINK_COLOR": "#B3198E",
        "ACCENT_WARM_COLOR": "#B3198E",
        "ACCENT_TEXT_COLOR": "#FFFFFF",
        "LINE_COLOR": "rgba(0,109,155,0.30)",
        "SOFT_LINE_COLOR": "rgba(142,107,255,0.26)",
        "GLASS_COLOR": "rgba(255,255,255,0.82)",
        "GLASS_STRONG_COLOR": "rgba(255,255,255,0.94)",
        "MESH_A": "#F4F8FF",
        "MESH_B": "#E9F4FF",
        "MESH_C": "#EAF7F1",
        "MESH_D": "#F7EFFF",
        "USER_BUBBLE_COLOR": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #006D9B, stop:0.36 #0079A8, stop:0.68 #047A68, stop:1 #057D5D)",
        "USER_BUBBLE_BORDER": "rgba(0,109,155,0.42)",
        "INPUT_GRADIENT_END": "#D7E8FF",
        "CARD_GRADIENT_END": "#F5F8FF",
        "TOP_GRADIENT_A": "#FDFEFF",
        "TOP_GRADIENT_B": "#EEF6FF",
        "TOP_GRADIENT_C": "#F8EEFF",
        "MENU_BG_COLOR": "#FFFFFF",
        "BUBBLE_AGENT_END": "#F8FBFF",
        "BUBBLE_USER_TEXT": "#FFFFFF",
        "CODE_BG_COLOR": "rgba(6,22,44,0.08)",
        "HOVER_TINT": "rgba(5,125,93,0.10)",
        "ACCENT_TINT": "rgba(0,109,155,0.12)",
        "ACCENT_TINT_STRONG": "rgba(179,25,142,0.15)",
        "FIELD_TEXT_COLOR": "#062033",
    },
}

THEME_EXPORT_NAMES = (
    "CURRENT_THEME_MODE", "CURRENT_THEME",
    "BG_COLOR", "BG_ELEVATED_COLOR", "PANEL_COLOR", "PANEL_ELEVATED_COLOR",
    "FIELD_COLOR", "FIELD_HOVER_COLOR", "TEXT_COLOR", "MUTED_TEXT_COLOR",
    "SUBTLE_TEXT_COLOR", "ACCENT_COLOR", "ACCENT_SECONDARY_COLOR",
    "ACCENT_PINK_COLOR", "ACCENT_WARM_COLOR", "ACCENT_TEXT_COLOR", "LINE_COLOR", "SOFT_LINE_COLOR",
    "INPUT_GRADIENT_END", "CARD_GRADIENT_END", "TOP_GRADIENT_A",
    "TOP_GRADIENT_B", "TOP_GRADIENT_C", "MENU_BG_COLOR", "BUBBLE_AGENT_END",
    "GLASS_COLOR", "GLASS_STRONG_COLOR", "MESH_A", "MESH_B", "MESH_C",
    "MESH_D", "USER_BUBBLE_COLOR", "USER_BUBBLE_BORDER",
    "BUBBLE_USER_TEXT", "CODE_BG_COLOR", "HOVER_TINT", "ACCENT_TINT",
    "ACCENT_TINT_STRONG", "FIELD_TEXT_COLOR", "CHECKMARK_SVG_PATH",
    "DROPDOWN_SVG_PATH", "RESET_SVG_PATH", "CHECKBOX_CSS", "COMBOBOX_CSS",
    "LINE_EDIT_CSS", "TEXT_EDIT_CSS", "PRIMARY_BUTTON_CSS",
    "SECONDARY_BUTTON_CSS", "DANGER_BUTTON_CSS", "NAV_CARD_CSS",
    "INPUT_FRAME_CSS", "SCROLLBAR_CSS", "SLIDER_CSS", "LOG_TEXT_CSS",
)


def _normalize_theme_mode(mode):
    mode = str(mode or DEFAULT_THEME_MODE).strip().lower()
    return mode if mode in THEME_OPTIONS else DEFAULT_THEME_MODE


def _read_theme_mode_from_disk():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            prefs = data.get("ui_preferences", {}) if isinstance(data, dict) else {}
            return _normalize_theme_mode(prefs.get("theme_mode", DEFAULT_THEME_MODE))
    except Exception:
        pass
    return DEFAULT_THEME_MODE


def _system_prefers_dark():
    if os.name != "nt":
        return True
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
    except Exception:
        return True


def resolve_theme_mode(mode=None, settings=None):
    if mode is None and isinstance(settings, dict):
        mode = settings.get("ui_preferences", {}).get("theme_mode", DEFAULT_THEME_MODE)
    if mode is None:
        mode = _read_theme_mode_from_disk()
    mode = _normalize_theme_mode(mode)
    if mode == "system":
        return "dark" if _system_prefers_dark() else "light"
    return mode


def _svg_asset(filename, svg_text):
    path = ensure_ui_svg_asset(filename, svg_text)
    return path.replace("\\", "/") if path else ""


def themed_asset_candidates(*names):
    candidates = []
    alternate_theme = "light" if CURRENT_THEME == "dark" else "dark"
    for name in names:
        raw = str(name or "").strip()
        if not raw:
            continue
        if os.path.isabs(raw) or os.path.dirname(raw):
            candidates.append(raw)
            continue
        stem, ext = os.path.splitext(raw)
        if ext:
            candidates.append(f"{stem}_{CURRENT_THEME}{ext}")
            candidates.append(f"{stem}_{CURRENT_THEME} {ext}")
            candidates.append(raw)
            candidates.append(f"{stem} {ext}")
            candidates.append(f"{stem}_{alternate_theme}{ext}")
            candidates.append(f"{stem}_{alternate_theme} {ext}")
        else:
            for suffix in (".png", ".svg"):
                candidates.append(f"{raw}_{CURRENT_THEME}{suffix}")
                candidates.append(f"{raw}_{CURRENT_THEME} {suffix}")
            for suffix in (".png", ".svg"):
                candidates.append(f"{raw}{suffix}")
                candidates.append(f"{raw} {suffix}")
            for suffix in (".png", ".svg"):
                candidates.append(f"{raw}_{alternate_theme}{suffix}")
                candidates.append(f"{raw}_{alternate_theme} {suffix}")
    return list(dict.fromkeys(candidates))


def themed_asset_path(*names):
    for filename in themed_asset_candidates(*names):
        path = filename if os.path.isabs(filename) or os.path.dirname(filename) else os.path.join(ASSETS_DIR, filename)
        if os.path.exists(path):
            return path.replace("\\", "/")
    return ""


def themed_icon(*names):
    for filename in themed_asset_candidates(*names):
        path = filename if os.path.isabs(filename) or os.path.dirname(filename) else os.path.join(ASSETS_DIR, filename)
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


def qcolor_from_css(value, fallback="#000000", alpha=None):
    text = str(value or "").strip()
    match = re.fullmatch(r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)", text)
    if match:
        r, g, b = [max(0, min(255, int(float(part)))) for part in match.group(1, 2, 3)]
        raw_alpha = match.group(4)
        if raw_alpha is None:
            a = 255
        else:
            parsed = float(raw_alpha)
            a = int(max(0.0, min(1.0, parsed)) * 255) if parsed <= 1 else max(0, min(255, int(parsed)))
        color = QColor(r, g, b, a)
    else:
        color = QColor(text)
        if not color.isValid():
            color = QColor(fallback)
    if alpha is not None:
        color.setAlpha(max(0, min(255, int(alpha))))
    return color


def set_themed_button_icon(button, names, fallback_text="", icon_size=20, clear_text=True):
    if isinstance(names, str):
        names = (names,)
    names = tuple(str(name) for name in (names or ()) if str(name or "").strip())
    button.setProperty("smartiIconNames", names)
    button.setProperty("smartiIconFallbackText", fallback_text)
    button.setProperty("smartiIconSize", int(icon_size))
    button.setProperty("smartiIconClearText", bool(clear_text))
    refresh_themed_button_icon(button)


def refresh_themed_button_icon(button):
    names = button.property("smartiIconNames")
    if not names:
        return
    fallback_text = button.property("smartiIconFallbackText")
    icon_size = int(button.property("smartiIconSize") or 20)
    clear_text = bool(button.property("smartiIconClearText"))
    icon = themed_icon(*tuple(names))
    if not icon.isNull():
        button.setIcon(icon)
        button.setIconSize(QSize(icon_size, icon_size))
        if clear_text:
            button.setText("")
    else:
        button.setIcon(QIcon())
        if fallback_text is not None:
            button.setText(str(fallback_text))


def set_themed_label_icon(label, names, fallback_text="", icon_size=28):
    if isinstance(names, str):
        names = (names,)
    names = tuple(str(name) for name in (names or ()) if str(name or "").strip())
    label.setProperty("smartiIconNames", names)
    label.setProperty("smartiIconFallbackText", fallback_text)
    label.setProperty("smartiIconSize", int(icon_size))
    refresh_themed_label_icon(label)


def refresh_themed_label_icon(label):
    names = label.property("smartiIconNames")
    if not names:
        return
    fallback_text = label.property("smartiIconFallbackText")
    icon_size = int(label.property("smartiIconSize") or 28)
    icon = themed_icon(*tuple(names))
    if not icon.isNull():
        label.setPixmap(icon.pixmap(icon_size, icon_size))
        label.setText("")
    else:
        label.setPixmap(QPixmap())
        if fallback_text is not None:
            label.setText(str(fallback_text))


def refresh_themed_widget_icons(root):
    widgets = [root] if root is not None else []
    try:
        widgets += root.findChildren(QWidget) if root is not None else []
    except Exception:
        pass
    for widget in widgets:
        if isinstance(widget, QPushButton):
            refresh_themed_button_icon(widget)
        elif isinstance(widget, QLabel):
            refresh_themed_label_icon(widget)


def _refresh_theme_exports(mode=None, settings=None):
    global CURRENT_THEME_MODE, CURRENT_THEME
    global BG_COLOR, BG_ELEVATED_COLOR, PANEL_COLOR, PANEL_ELEVATED_COLOR
    global FIELD_COLOR, FIELD_HOVER_COLOR, TEXT_COLOR, MUTED_TEXT_COLOR
    global SUBTLE_TEXT_COLOR, ACCENT_COLOR, ACCENT_SECONDARY_COLOR
    global ACCENT_PINK_COLOR, ACCENT_WARM_COLOR, ACCENT_TEXT_COLOR, LINE_COLOR, SOFT_LINE_COLOR
    global INPUT_GRADIENT_END, CARD_GRADIENT_END, TOP_GRADIENT_A
    global TOP_GRADIENT_B, TOP_GRADIENT_C, MENU_BG_COLOR, BUBBLE_AGENT_END
    global GLASS_COLOR, GLASS_STRONG_COLOR, MESH_A, MESH_B, MESH_C, MESH_D
    global USER_BUBBLE_COLOR, USER_BUBBLE_BORDER
    global BUBBLE_USER_TEXT, CODE_BG_COLOR, HOVER_TINT, ACCENT_TINT
    global ACCENT_TINT_STRONG, FIELD_TEXT_COLOR
    global CHECKMARK_SVG_PATH, DROPDOWN_SVG_PATH, RESET_SVG_PATH
    global CHECKBOX_CSS, COMBOBOX_CSS, LINE_EDIT_CSS, TEXT_EDIT_CSS
    global PRIMARY_BUTTON_CSS, SECONDARY_BUTTON_CSS, DANGER_BUTTON_CSS
    global NAV_CARD_CSS, INPUT_FRAME_CSS, SCROLLBAR_CSS, SLIDER_CSS, LOG_TEXT_CSS

    requested = mode
    if requested is None and isinstance(settings, dict):
        requested = settings.get("ui_preferences", {}).get("theme_mode", DEFAULT_THEME_MODE)
    if requested is None:
        requested = _read_theme_mode_from_disk()

    CURRENT_THEME_MODE = _normalize_theme_mode(requested)
    CURRENT_THEME = resolve_theme_mode(CURRENT_THEME_MODE, settings)
    palette = THEME_PALETTES[CURRENT_THEME]
    globals().update(palette)

    CHECKMARK_SVG_PATH = _svg_asset(
        f"checkmark_{CURRENT_THEME}.svg",
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{ACCENT_TEXT_COLOR}" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L19 7"/></svg>'
    )
    DROPDOWN_SVG_PATH = _svg_asset(
        f"dropdown_{CURRENT_THEME}.svg",
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{ACCENT_COLOR}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>'
    )
    RESET_SVG_PATH = _svg_asset(
        f"reset_{CURRENT_THEME}.svg",
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{ACCENT_COLOR}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v6h6"/></svg>'
    )

    CHECKBOX_CSS = f"""
        QCheckBox {{
            color: {TEXT_COLOR}; font-size: 14px; spacing: 11px;
            padding: 6px 2px; background: transparent;
        }}
        QCheckBox:disabled {{ color: {SUBTLE_TEXT_COLOR}; }}
        QCheckBox::indicator {{
            width: 22px; height: 22px;
            border-radius: 11px;
            border: 1px solid {SOFT_LINE_COLOR};
            background: {GLASS_COLOR};
        }}
        QCheckBox::indicator:hover {{
            border-color: {LINE_COLOR};
            background: {FIELD_HOVER_COLOR};
        }}
        QCheckBox::indicator:checked {{
            image: url("{CHECKMARK_SVG_PATH}");
            border-color: {ACCENT_COLOR};
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
        }}
    """

    COMBOBOX_CSS = f"""
        QComboBox {{
            background: {GLASS_COLOR}; color: {FIELD_TEXT_COLOR};
            border-radius: 20px; padding: 13px 16px 13px 46px; font-size: 14px;
            border: 1px solid {SOFT_LINE_COLOR};
            min-height: 26px;
            selection-background-color: {ACCENT_TINT_STRONG};
            selection-color: {TEXT_COLOR};
        }}
        QComboBox:hover {{
            background: {FIELD_HOVER_COLOR};
            border-color: {LINE_COLOR};
        }}
        QComboBox:focus {{
            background: {FIELD_HOVER_COLOR};
            border-color: {ACCENT_PINK_COLOR};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: center left;
            width: 38px; border: none;
            margin: 5px 0px 5px 6px;
        }}
        QComboBox::down-arrow {{
            image: url("{DROPDOWN_SVG_PATH}");
            width: 17px; height: 17px;
        }}
        QComboBox QAbstractItemView {{
            background: {MENU_BG_COLOR}; background-color: {MENU_BG_COLOR}; color: {TEXT_COLOR};
            selection-background-color: {ACCENT_TINT_STRONG}; selection-color: {TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR}; border-radius: 16px; outline: 0px;
            padding: 8px;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 28px; padding: 7px 10px; border-radius: 10px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {HOVER_TINT};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR};
        }}
    """

    LINE_EDIT_CSS = f"""
        QLineEdit {{
            background: {GLASS_COLOR}; color: {FIELD_TEXT_COLOR};
            border-radius: 20px; padding: 13px 16px;
            border: 1px solid {SOFT_LINE_COLOR};
            font-size: 14px;
            selection-background-color: {ACCENT_TINT_STRONG};
            selection-color: {TEXT_COLOR};
        }}
        QLineEdit:hover {{ background: {FIELD_HOVER_COLOR}; border-color: {LINE_COLOR}; }}
        QLineEdit:focus {{ background: {FIELD_HOVER_COLOR}; border-color: {ACCENT_PINK_COLOR}; }}
        QLineEdit:disabled {{ color: {SUBTLE_TEXT_COLOR}; background: {PANEL_ELEVATED_COLOR}; }}
    """

    TEXT_EDIT_CSS = f"""
        QTextEdit {{
            background: {GLASS_COLOR}; color: {FIELD_TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 20px; padding: 13px;
            selection-background-color: {ACCENT_TINT_STRONG};
            selection-color: {TEXT_COLOR};
        }}
        QTextEdit:focus {{ background: {FIELD_HOVER_COLOR}; border-color: {ACCENT_PINK_COLOR}; }}
        QTextEdit viewport {{ background: transparent; color: {FIELD_TEXT_COLOR}; }}
    """

    PRIMARY_BUTTON_CSS = f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
            color: {ACCENT_TEXT_COLOR}; font-weight: 700;
            padding: 14px 22px; border-radius: 22px; font-size: 15px;
            border: 1px solid rgba(255,255,255,0.18);
            outline: none;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {BRAND_ACCENT_COLOR}, stop:0.52 {BRAND_PINK_COLOR}, stop:1 {BRAND_SECONDARY_COLOR});
        }}
        QPushButton:pressed {{ background: {ACCENT_COLOR}; padding-top: 15px; padding-bottom: 13px; }}
        QPushButton:disabled {{ background: {PANEL_ELEVATED_COLOR}; color: {SUBTLE_TEXT_COLOR}; }}
    """

    SECONDARY_BUTTON_CSS = f"""
        QPushButton {{
            background-color: {ACCENT_TINT}; color: {TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR}; border-radius: 20px;
            padding: 11px 17px; font-size: 13px; font-weight: 700;
            outline: none;
        }}
        QPushButton:hover {{ background-color: {HOVER_TINT}; border-color: {LINE_COLOR}; }}
        QPushButton:pressed {{ background-color: {ACCENT_TINT_STRONG}; border-color: {ACCENT_PINK_COLOR}; }}
        QPushButton:checked {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
            color: {ACCENT_TEXT_COLOR};
            border-color: {ACCENT_COLOR};
        }}
        QPushButton:disabled {{ color: {SUBTLE_TEXT_COLOR}; background: transparent; border-color: transparent; }}
    """

    DANGER_BUTTON_CSS = f"""
        QPushButton {{
            background-color: rgba(240,90,110,0.13); color: {DANGER_COLOR};
            border: 1px solid rgba(255,95,126,0.30);
            border-radius: 20px; padding: 11px 17px; font-weight: 700;
            outline: none;
        }}
        QPushButton:hover {{ background-color: rgba(255,95,126,0.20); border-color: rgba(255,95,126,0.44); }}
        QPushButton:pressed {{ background-color: rgba(255,95,126,0.28); }}
    """

    NAV_CARD_CSS = f"""
        QFrame#SettingsNavCard {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {GLASS_STRONG_COLOR}, stop:1 {CARD_GRADIENT_END});
            color: {TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 22px;
        }}
        QFrame#SettingsNavCard:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {PANEL_ELEVATED_COLOR}, stop:1 {FIELD_HOVER_COLOR});
            border-color: {LINE_COLOR};
        }}
    """

    INPUT_FRAME_CSS = f"""
        QFrame#InputFrame {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {GLASS_STRONG_COLOR}, stop:1 {INPUT_GRADIENT_END});
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 42px;
        }}
        QFrame#InputFrame:hover {{
            background: {FIELD_HOVER_COLOR};
            border-color: {LINE_COLOR};
        }}
    """

    SCROLLBAR_CSS = f"""
        QScrollBar:vertical {{ background: transparent; width: 7px; border-radius: 3px; margin: 2px 0px; }}
        QScrollBar::handle:vertical {{ background: {ACCENT_TINT_STRONG}; min-height: 22px; border-radius: 3px; }}
        QScrollBar::handle:vertical:hover {{ background: {ACCENT_COLOR}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QScrollBar:horizontal {{ background: transparent; height: 7px; border-radius: 3px; margin: 0px 2px; }}
        QScrollBar::handle:horizontal {{ background: {ACCENT_TINT_STRONG}; min-width: 22px; border-radius: 3px; }}
        QScrollBar::handle:horizontal:hover {{ background: {ACCENT_COLOR}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
    """

    SLIDER_CSS = f"""
        QSlider {{ min-height: 54px; }}
        QSlider::groove:horizontal {{
            height: 32px; border-radius: 16px;
            background: {PANEL_ELEVATED_COLOR};
        }}
        QSlider::sub-page:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {ACCENT_COLOR}, stop:0.56 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
            border-radius: 16px;
        }}
        QSlider::add-page:horizontal {{
            background: {PANEL_ELEVATED_COLOR};
            border-radius: 16px;
        }}
        QSlider::handle:horizontal {{
            background: transparent;
            border: none;
            width: 0px; height: 0px; margin: 0px;
        }}
        QSlider::handle:horizontal:hover {{
            background: transparent;
        }}
    """

    LOG_TEXT_CSS = f"""
        QTextEdit {{
            background: {FIELD_COLOR}; color: {FIELD_TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 20px; padding: 12px;
            font-family: Consolas, 'Courier New';
            font-size: 12px;
            selection-background-color: {ACCENT_TINT_STRONG};
            selection-color: {TEXT_COLOR};
        }}
        QTextEdit viewport {{ background: {FIELD_COLOR}; color: {FIELD_TEXT_COLOR}; }}
    """ + SCROLLBAR_CSS


def _publish_theme_to_importers():
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("smarti.") or module_name == __name__:
            continue
        module_dict = getattr(module, "__dict__", {})
        for name in THEME_EXPORT_NAMES:
            if name in module_dict and name in globals():
                module_dict[name] = globals()[name]


def set_ui_theme(mode=None, settings=None):
    """Apply a theme to exported design tokens and already-imported Smarti modules."""
    _refresh_theme_exports(mode, settings)
    _publish_theme_to_importers()
    return CURRENT_THEME


def build_qt_palette():
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG_COLOR))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_COLOR))
    palette.setColor(QPalette.ColorRole.Base, QColor(FIELD_COLOR))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL_ELEVATED_COLOR))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(PANEL_COLOR))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT_COLOR))
    palette.setColor(QPalette.ColorRole.Text, QColor(FIELD_TEXT_COLOR))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL_ELEVATED_COLOR))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_COLOR))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_COLOR))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(ACCENT_TEXT_COLOR))
    return palette


def apply_app_theme(app=None, mode=None, settings=None):
    set_ui_theme(mode, settings)
    app = app or QApplication.instance()
    if app:
        app.setPalette(build_qt_palette())
        app.setStyleSheet(application_stylesheet())
    return CURRENT_THEME


def application_stylesheet():
    return f"""
        QWidget {{
            font-family: 'Segoe UI', Arial;
            color: {TEXT_COLOR};
            selection-background-color: {ACCENT_TINT_STRONG};
            selection-color: {TEXT_COLOR};
        }}
        QMainWindow, QDialog, QMessageBox {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {MESH_A}, stop:0.45 {MESH_B}, stop:0.72 {MESH_C}, stop:1 {MESH_D});
            color: {TEXT_COLOR};
        }}
        QLabel {{
            color: {TEXT_COLOR};
            background: transparent;
        }}
        QTextEdit {{ cursor-move-style: logical; }}
        QLineEdit {{ cursor-move-style: logical; }}
        QPushButton, QToolButton, QCheckBox, QComboBox, QLineEdit, QTextEdit,
        QPlainTextEdit, QListWidget, QTreeWidget, QMenu, QAbstractItemView {{
            outline: none;
        }}
        QToolTip {{
            background: {MENU_BG_COLOR};
            color: {TEXT_COLOR};
            border: 0px solid transparent;
            border-radius: 14px;
            padding: 6px 8px;
            font-size: 12px;
        }}
        QMenu {{
            background-color: {MENU_BG_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 18px;
            font-family: 'Segoe UI';
            font-size: 14px;
            padding: 7px;
        }}
        QMenu::item {{
            padding: 9px 30px 9px 10px;
            border-radius: 14px;
            min-width: 118px;
        }}
        QMenu::icon {{
            padding-right: 4px;
        }}
        QMenu::item:selected {{
            background-color: {ACCENT_TINT_STRONG};
            color: {TEXT_COLOR};
        }}
        QMenu::separator {{
            height: 1px;
            background: {SOFT_LINE_COLOR};
            margin: 7px 10px;
        }}
        QDialogButtonBox QPushButton {{
            background-color: {ACCENT_TINT};
            color: {TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 20px;
            padding: 10px 16px;
            font-weight: 700;
        }}
        QDialogButtonBox QPushButton:hover {{
            background-color: {HOVER_TINT};
            border-color: {LINE_COLOR};
        }}
    """


def dialog_stylesheet():
    return f"""
        QDialog {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {MESH_A}, stop:0.48 {MESH_B}, stop:1 {MESH_C});
            color: {TEXT_COLOR};
        }}
        QLabel {{ color: {TEXT_COLOR}; background: transparent; }}
    """ + TEXT_EDIT_CSS


def menu_stylesheet():
    return f"""
        QMenu {{
            background-color: {MENU_BG_COLOR};
            color: {TEXT_COLOR};
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 18px;
            font-family: 'Segoe UI';
            font-size: 14px;
            padding: 7px;
        }}
        QMenu::item {{ padding: 9px 30px 9px 10px; border-radius: 14px; min-width: 118px; }}
        QMenu::icon {{ padding-right: 4px; }}
        QMenu::item:selected {{ background-color: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR}; }}
        QMenu::separator {{ height: 1px; background: {SOFT_LINE_COLOR}; margin: 7px 10px; }}
    """

def prepare_popup_menu(menu):
    if menu is None:
        return menu
    try:
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        menu.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        menu.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
    except Exception:
        pass
    menu.setStyleSheet(menu_stylesheet())
    return menu


def page_title_css(size=18):
    return f"color: {TEXT_COLOR}; font-size: {int(size)}px; font-weight: 700; background: transparent;"


def section_title_css(size=16):
    return f"color: {ACCENT_COLOR}; font-size: {int(size)}px; font-weight: 700; background: transparent;"


def muted_label_css(size=12):
    return f"color: {MUTED_TEXT_COLOR}; font-size: {int(size)}px; background: transparent;"


def card_css(padding=14, radius=8):
    radius = max(20, int(radius))
    return f"""
        QFrame {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {GLASS_STRONG_COLOR}, stop:1 {CARD_GRADIENT_END});
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: {radius}px;
            padding: {int(padding)}px;
        }}
        QLabel {{ border: none; background: transparent; }}
    """


def icon_button_css(size=48, danger=False):
    color = DANGER_COLOR if danger else ACCENT_COLOR
    tint = "rgba(240,90,110,0.16)" if danger else ACCENT_TINT
    hover = "rgba(240,90,110,0.24)" if danger else HOVER_TINT
    radius = max(1, int(size / 2))
    return f"""
        QPushButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: {radius}px;
            padding: 0px;
            color: {color};
            font-size: 20px;
            font-weight: 700;
            outline: none;
        }}
        QPushButton:hover {{ background-color: {hover}; border-color: {SOFT_LINE_COLOR}; }}
        QPushButton:pressed {{ background-color: {tint}; border-color: {LINE_COLOR}; }}
        QPushButton:disabled {{ color: {SUBTLE_TEXT_COLOR}; }}
    """


def ghost_button_css():
    return f"""
        QPushButton {{
            background: transparent;
            border: 1px solid transparent;
            color: {TEXT_COLOR};
            border-radius: 20px;
            padding: 10px 14px;
            font-weight: 700;
            outline: none;
        }}
        QPushButton:hover {{ background: {ACCENT_TINT}; border-color: {SOFT_LINE_COLOR}; }}
        QPushButton:pressed {{ background: {ACCENT_TINT_STRONG}; border-color: {LINE_COLOR}; }}
    """


def segmented_control_css():
    return f"""
        QWidget#SegmentedControl {{
            background: {GLASS_COLOR};
            border: 1px solid {SOFT_LINE_COLOR};
            border-radius: 23px;
        }}
        QPushButton {{
            background: transparent;
            border: none;
            color: {MUTED_TEXT_COLOR};
            border-radius: 18px;
            margin: 2px;
            padding: 9px 14px;
            font-size: 13px;
            font-weight: 700;
            outline: none;
            min-height: 34px;
        }}
        QPushButton:hover {{
            background: {HOVER_TINT};
            color: {TEXT_COLOR};
        }}
        QPushButton:checked {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {ACCENT_COLOR}, stop:0.58 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
            color: {ACCENT_TEXT_COLOR};
        }}
    """


_refresh_theme_exports()

__all__ = [name for name in globals() if not name.startswith("__")]
