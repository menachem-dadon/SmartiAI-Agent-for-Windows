"""Chat bubbles, notifications, main window, and splash screen."""
import math
import random

from .common import *
from .attachments import *
from .ui_styles import *
from .ui_controls import *
from .config import BUILT_IN_TOOLS, LEGACY_BUILTIN_TOOLS, PUBLIC_BUILTIN_TOOLS
from .workers import AgentWorker, VoiceWorker, TTSWorker
from .ui_pages import ActionConfirmDialog, ApiKeyRequiredDialog, SmartiDoctorPage, UsageStatsPage, TaskCenterPage, DeveloperTracePage, ToolsSettingsPage, SettingsPage, AboutPage, refresh_back_button_icon
from .history import DEFAULT_CHAT_TITLE
from .windows_notifications import TaskbarAttentionController, WindowsNotificationCenter
from .updater import UpdateCheckWorker, UpdateDownloadWorker, UpdateInfo, human_size, launch_update_installer
from .visual_canvas import VisualCanvasPanel, normalize_canvas_artifact, web_canvas_available
from PyQt6.QtCore import QEvent, QEventLoop
from PyQt6.QtGui import QTextDocument, QTransform
from PyQt6.QtWidgets import QBoxLayout, QSplitter

_LEGACY_WELCOME_PROMPTS = [
    "היי {name}, איך אוכל לעזור לך היום? אפשר לסכם קובץ, לחפש מידע או לארגן משימה.",
    "היי {name}, במה תרצה שנתקדם? אני יכול לעזור עם מיילים, קבצים ותכנון צעדים.",
    "היי {name}, איך אפשר להקל על היום שלך? אפשר לתזמן תזכורת, לבדוק מידע או לסדר קבצים.",
    "היי {name}, מה כדאי לטפל בו עכשיו? אני יכול לחפש ברשת, להשוות מקורות ולחזור עם תשובה מסודרת.",
    "היי {name}, צריך עזרה עם משהו יומיומי? אפשר לנסח הודעה, למצוא קובץ או להכין סיכום קצר.",
    "היי {name}, איך אוכל לסייע? אפשר להפוך רעיון למסמך, רשימה או תוכנית פעולה.",
    "היי {name}, במה נתחיל? אני יכול לעזור לסדר תיקיות, לשנות שמות קבצים ולמצוא מה חסר.",
    "היי {name}, מה תרצה שאבדוק עבורך? אפשר לבדוק מיילים, שטח אחסון, קבצים או מידע עדכני.",
    "היי {name}, איך אפשר לעזור היום? אפשר להכין תזכורת, משימת רקע או בדיקה חוזרת.",
    "היי {name}, יש משהו שתרצה לקדם? אני יכול לאסוף מידע, לסכם אותו ולהציע המשך פעולה.",
    "היי {name}, במה אוכל לעזור? אפשר לקרוא מסמך, לחלץ ממנו נקודות ולסדר משימות להמשך.",
    "היי {name}, רוצה לקצר תהליך? אפשר לפתוח כלים, לחבר פעולות ולחסוך עבודה ידנית.",
    "היי {name}, מה על הפרק? אני יכול לעזור במייל, בקובץ, בתזמון או בחיפוש מידע.",
    "היי {name}, איך אוכל לעזור לך לעבוד יותר מסודר היום? אפשר לארגן קבצים ולבנות רשימת פעולות.",
    "היי {name}, יש משהו שצריך לזכור או לבדוק בהמשך? אפשר ליצור תזכורת או משימת רקע.",
    "היי {name}, במה תרצה שאטפל? אפשר לנסח מכתב, לסכם מסמך או למצוא מידע ברשת.",
    "היי {name}, איך אפשר לעזור? אני יכול לעבור על מידע ארוך ולהחזיר לך רק את העיקר.",
    "היי {name}, צריך יד עם סדר וארגון? אפשר למיין קבצים, להכין שמות ברורים ולרכז תוצרים.",
    "היי {name}, מה תרצה שאעשה עבורך? אפשר לבדוק נתונים, להכין סיכום או לתזמן מעקב.",
    "היי {name}, איך אוכל לסייע היום? אפשר לנתח תמונה או מסמך ולהפוך אותם לטקסט שימושי.",
    "היי {name}, במה אפשר לעזור עכשיו? אני יכול להכין טיוטה, רשימת קניות, תזכורת או סיכום.",
    "היי {name}, יש משימה שחוזרת על עצמה? אפשר להפוך אותה לאוטומציה עדינה ומבוקרת.",
    "היי {name}, מה תרצה לברר? אפשר לחפש מידע עדכני, לאמת פרטים ולנסח תשובה ברורה.",
    "היי {name}, איך נתקדם? אני יכול לחלק משימה מורכבת לצעדים קטנים ולבצע אותם איתך.",
    "היי {name}, צריך להכין משהו לשיחה, לפגישה או למייל? אפשר לבנות תקציר ונקודות פעולה.",
    "היי {name}, במה אוכל לעזור לך? אפשר לעבוד עם קבצים, מיילים, תזכורות וחיפוש באינטרנט.",
    "היי {name}, רוצה שאסדר את זה עבורך? אפשר לקחת תוכן מבולגן ולהפוך אותו למסמך נקי.",
    "היי {name}, יש משהו שדורש מעקב? אפשר להגדיר בדיקה מחזורית בלי להזיז את השעה הקבועה.",
    "היי {name}, צריך עזרה טכנית קטנה? אפשר לבדוק קוד, לוג או שגיאה בלי להיכנס לפרויקט שלם.",
    "היי {name}, איך אוכל לעזור לך לסיים את הדבר הבא? אפשר להתחיל מרעיון קצר ולהגיע לתוצאה מוכנה.",
]

_RECENT_WELCOME_PROMPTS = [
    "היי {name}, איך אוכל לעזור היום?",
    "היי {name}, במה נתחיל?",
    "היי {name}, רוצה שאסכם משהו?",
    "היי {name}, צריך עזרה במייל?",
    "היי {name}, אשמח לסדר את זה.",
    "היי {name}, מה תרצה לקדם?",
    "היי {name}, שאבדוק משהו ברשת?",
    "היי {name}, שאסדר קבצים?",
    "היי {name}, צריך תזכורת?",
    "היי {name}, שאנסח הודעה?",
    "היי {name}, יש מסמך לסיכום?",
    "היי {name}, איך אקל על היום?",
    "היי {name}, לחפש לך מידע?",
    "היי {name}, לבנות רשימת צעדים?",
    "היי {name}, להגדיר בדיקה חוזרת?",
    "היי {name}, לטפל בקבצים או מיילים?",
    "היי {name}, להפוך רעיון לרשימה?",
    "היי {name}, לברר או לאמת משהו?",
    "היי {name}, לארגן משימות להיום?",
    "היי {name}, להכין תקציר קצר?",
    "היי {name}, לבדוק קוד קטן?",
    "היי {name}, במה תרצה שאטפל קודם?",
    "היי {name}, לחפש, לסכם או לתזמן?",
    "היי {name}, לבדוק מצב מערכת?",
    "היי {name}, לקרוא קובץ עבורך?",
    "היי {name}, לנסח מייל קצר?",
    "היי {name}, לבנות תזכורת חכמה?",
    "היי {name}, להפוך בלגן לסדר?",
    "היי {name}, איזו משימה נסיים עכשיו?",
    "היי {name}, להתחיל מחיפוש או סיכום?",
]

WELCOME_PROMPTS = [
    "היי {name}, איך אוכל לעזור היום?",
    "היי {name}, במה אוכל לעזור?",
    "היי {name}, אשמח לעזור.",
    "היי {name}, במה נתחיל?",
    "היי {name}, אני כאן לעזור.",
    "היי {name}, מה תרצה לעשות עכשיו?",
    "היי {name}, במה תרצה שאתמקד?",
    "היי {name}, איך אפשר להתקדם?",
    "היי {name}, מה חשוב לך עכשיו?",
    "היי {name}, איך אוכל להקל עליך?",
]

GENERIC_USER_NAMES = {
    "user", "owner", "admin", "administrator", "defaultuser", "defaultuser0",
    "guest", "pc", "computer", "windows", "desktop", "laptop",
}


def _clean_system_display_name(value):
    name = str(value or "").strip()
    if not name:
        return ""
    if "\\" in name:
        name = name.rsplit("\\", 1)[-1]
    if "@" in name:
        name = name.split("@", 1)[0]
    name = re.sub(r"[_\-.]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\d+$", "", name).strip()
    folded = re.sub(r"\s+", "", name).lower()
    if len(name) < 2 or folded in GENERIC_USER_NAMES or folded.startswith("defaultuser"):
        return ""
    if not re.search(r"[A-Za-z\u0590-\u05ff]", name):
        return ""
    return name[:36].rstrip()


def _system_display_name():
    candidates = []
    if os.name == "nt":
        try:
            size = ctypes.c_ulong(0)
            ctypes.windll.secur32.GetUserNameExW(3, None, ctypes.byref(size))
            if size.value:
                buffer = ctypes.create_unicode_buffer(size.value)
                if ctypes.windll.secur32.GetUserNameExW(3, buffer, ctypes.byref(size)):
                    candidates.append(buffer.value)
        except Exception:
            pass
        try:
            size = ctypes.c_ulong(256)
            buffer = ctypes.create_unicode_buffer(size.value)
            if ctypes.windll.advapi32.GetUserNameW(buffer, ctypes.byref(size)):
                candidates.append(buffer.value)
        except Exception:
            pass
    candidates.extend(os.environ.get(key, "") for key in ("USERNAME", "USER", "LOGNAME"))
    try:
        candidates.append(Path.home().name)
    except Exception:
        pass
    for candidate in candidates:
        cleaned = _clean_system_display_name(candidate)
        if cleaned:
            return cleaned
    return ""


def _welcome_prompt():
    prompt = random.choice(WELCOME_PROMPTS)
    name = _system_display_name()
    if name:
        return prompt.format(name=name)
    generic = prompt.format(name="")
    generic = re.sub(r"\s+([,?.!])", r"\1", generic)
    generic = re.sub(r"\s{2,}", " ", generic)
    return generic.strip()

def _asset_icon(*filenames):
    return themed_icon(*filenames)

def _asset_path(*filenames):
    return themed_asset_path(*filenames)

def _transparent_icon(size=22):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    return QIcon(pixmap)

def _rotated_themed_icon(names, degrees=0, size=18):
    if isinstance(names, str):
        names = (names,)
    icon = themed_icon(*tuple(names or ()))
    if icon.isNull() or int(degrees) % 360 == 0:
        return icon
    pixmap = icon.pixmap(size, size)
    if pixmap.isNull():
        return icon
    rotated = pixmap.transformed(
        QTransform().rotate(float(degrees)),
        Qt.TransformationMode.SmoothTransformation,
    )
    return QIcon(rotated)

def _fitted_plain_label_width(label, text, available, min_width=42, padding=10):
    available = max(min_width, int(available or min_width))
    text = str(text or "")
    metrics = QFontMetrics(label.font())
    raw_width = metrics.horizontalAdvance(text) + padding
    if raw_width <= available:
        return max(min_width, raw_width)
    try:
        doc = QTextDocument()
        doc.setDefaultFont(label.font())
        doc.setPlainText(text)
        doc.setTextWidth(available)
        ideal_width = int(doc.idealWidth() + 0.5) + padding
        if ideal_width > 0:
            return max(min_width, min(available, ideal_width))
    except Exception:
        pass
    return available

def _soft_break_escaped_token(token):
    token = html.escape(str(token or ""))
    for marker in ("\\", "/", "_", "-", ".", ":", "="):
        token = token.replace(marker, marker + "\u200b")
    return token

def _escape_plain_text_with_soft_breaks(text):
    raw = str(text or "")
    token_re = re.compile(r'(?:[A-Za-z]:\\|\\\\|/|https?://|www\.)[^\s<>{}]{12,}|[^\s<>{}]{42,}')
    parts = []
    last = 0
    for match in token_re.finditer(raw):
        parts.append(html.escape(raw[last:match.start()]))
        parts.append(_soft_break_escaped_token(match.group(0)))
        last = match.end()
    parts.append(html.escape(raw[last:]))
    return "".join(parts)

def _find_local_link_in_text(raw, start):
    limit = min(len(raw), start + 900)
    end = limit
    for marker in ("\n", "\r", "<", ">", "{", "}"):
        pos = raw.find(marker, start, limit)
        if pos != -1:
            end = min(end, pos)
    chunk = raw[start:end]
    if not chunk:
        return None
    trailing = " \t.,;:!?)]}'\"`׳״"
    seen = set()
    for size in range(len(chunk), 2, -1):
        candidate_text = chunk[:size].rstrip(trailing)
        if not candidate_text or candidate_text in seen:
            continue
        seen.add(candidate_text)
        following = chunk[len(candidate_text):]
        next_char = following[:1]
        if (
            next_char in {"\\", "/"} or
            (next_char and candidate_text.endswith(("\\", "/"))) or
            (next_char and (next_char.isalnum() or next_char in "._-%")) or
            (next_char == " " and re.match(r" [^\\/]{1,120}[\\/]", following))
        ):
            continue
        path = _local_path_from_href(candidate_text) or _clean_local_path(candidate_text)
        if _is_safe_local_link_path(path):
            return candidate_text, path, start + len(candidate_text)
    return None

def _escape_with_soft_breaks(text):
    raw = html.unescape(str(text or ""))
    path_start_re = re.compile(r"(?i)(?:[A-Za-z]:[\\/]|\\\\|file:/+)")
    parts = []
    pos = 0
    while pos < len(raw):
        match = path_start_re.search(raw, pos)
        if not match:
            parts.append(_escape_plain_text_with_soft_breaks(raw[pos:]))
            break
        parts.append(_escape_plain_text_with_soft_breaks(raw[pos:match.start()]))
        local_link = _find_local_link_in_text(raw, match.start())
        if not local_link:
            parts.append(_escape_plain_text_with_soft_breaks(raw[match.start():match.end()]))
            pos = match.end()
            continue
        display_text, path, link_end = local_link
        href = html.escape(_local_href_for_path(path), quote=True)
        label = _soft_break_escaped_token(display_text)
        parts.append(f'<a href="{href}">{label}</a>')
        pos = link_end
    return "".join(parts)

def _clean_href(value):
    href = html.unescape(str(value or "")).replace("\u200b", "").strip()
    return href

def _strip_href_wrappers(value):
    href = _clean_href(value)
    if len(href) >= 2 and href[0] == "<" and href[-1] == ">":
        href = href[1:-1].strip()
    return href

def _normalize_href(value):
    href = _strip_href_wrappers(value)
    return f"https://{href}" if href.startswith("www.") else href

def _looks_like_windows_abs_path(value):
    value = str(value or "")
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", value) or
        re.match(r"^[\\/]{2}[^\\/]+[\\/][^\\/]+", value)
    )

def _clean_local_path(value):
    path = urllib.parse.unquote(str(value or "")).strip()
    if re.match(r"^/[A-Za-z]:[\\/]", path):
        path = path[1:]
    if not (_looks_like_windows_abs_path(path) or os.path.isabs(path)):
        return ""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path)))

def _local_path_from_href(value):
    href = _strip_href_wrappers(value)
    if not href:
        return ""
    decoded = urllib.parse.unquote(href)
    if _looks_like_windows_abs_path(decoded):
        return _clean_local_path(decoded)
    if not href.lower().startswith("file:"):
        return ""
    url_path = ""
    try:
        url_path = QUrl(href).toLocalFile()
    except Exception:
        url_path = ""
    if not url_path:
        parsed = urllib.parse.urlparse(href)
        netloc = urllib.parse.unquote(parsed.netloc or "")
        path_part = urllib.parse.unquote(parsed.path or "")
        url_path = f"//{netloc}{path_part}" if netloc and path_part else path_part
    return _clean_local_path(url_path)

def _is_safe_local_link_path(path):
    path = str(path or "")
    if not path or not os.path.exists(path):
        return False
    if os.path.isfile(path) and os.path.splitext(path)[1].lower() in EXECUTABLE_OPEN_EXTENSIONS:
        return False
    return True

def _local_href_for_path(path):
    try:
        return bytes(QUrl.fromLocalFile(path).toEncoded()).decode("ascii")
    except Exception:
        return "file:///" + urllib.parse.quote(str(path).replace("\\", "/"), safe="/:")

def _canonical_display_href(value):
    href = _normalize_href(value)
    local_path = _local_path_from_href(href)
    if _is_safe_local_link_path(local_path):
        return _local_href_for_path(local_path)
    return href

def _display_label_for_href(value):
    local_path = _local_path_from_href(value)
    if local_path:
        return os.path.basename(local_path.rstrip("\\/")) or local_path
    return value

def _is_valid_display_href(value):
    href = _normalize_href(value)
    if not href or href in {"#", "about:blank"}:
        return False
    if _is_safe_local_link_path(_local_path_from_href(href)):
        return True
    parsed = urllib.parse.urlparse(href)
    return parsed.scheme.lower() in {"http", "https", "mailto"} and bool(parsed.netloc or parsed.scheme == "mailto")

def _repair_markdown_links(text):
    def repl(match):
        label = str(match.group(1) or "").strip()
        href = _canonical_display_href(match.group(2))
        if not _is_valid_display_href(href):
            return label
        return f"[{label or _display_label_for_href(href)}]({href})"
    return re.sub(r"\[([^\]]*)\]\(([^)]*)\)", repl, str(text or ""))

def _sanitize_rendered_links(rendered_html, link_color=None, clickable=True):
    style = ""
    if link_color:
        style = (
            f' style="color: {html.escape(str(link_color), quote=True)}; '
            'text-decoration: underline; font-weight: 800;"'
        )

    def repl(match):
        quote = match.group(1)
        href = _canonical_display_href(match.group(2))
        inner = match.group(3) or ""
        if not _is_valid_display_href(href):
            return inner
        display_inner = inner.strip() or html.escape(_display_label_for_href(href))
        if not clickable:
            return f'<span{style}>{display_inner}</span>'
        return f'<a href={quote}{html.escape(href, quote=True)}{quote}{style}>{display_inner}</a>'
    rendered_html = re.sub(r'<a\s+[^>]*href=(["\'])(.*?)\1[^>]*>(.*?)</a>', repl, str(rendered_html or ""), flags=re.IGNORECASE | re.DOTALL)
    rendered_html = re.sub(r'<a\s+[^>]*href\s*=\s*[^>]*>\s*</a>', '', rendered_html, flags=re.IGNORECASE | re.DOTALL)
    return rendered_html

def _code_language_from_attrs(attrs):
    attrs = str(attrs or "")
    match = re.search(r'class=(["\'])([^"\']*?language-([^"\']+))\1', attrs, flags=re.IGNORECASE)
    if not match:
        return "text"
    lang = html.unescape(match.group(3)).strip()
    lang = re.sub(r"[^A-Za-z0-9_+#.\-]+", "", lang)
    return lang.lower() or "text"

def _code_copy_icon_src():
    return _asset_path(
        "code_copy_icon",
        "copy_icon",
    )

CODE_LANGUAGE_EXTENSIONS = {
    "bash": ".sh", "shell": ".sh", "sh": ".sh", "zsh": ".sh",
    "powershell": ".ps1", "pwsh": ".ps1", "ps1": ".ps1",
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "tsx": ".tsx", "jsx": ".jsx",
    "html": ".html", "css": ".css", "scss": ".scss",
    "json": ".json", "jsonc": ".jsonc",
    "yaml": ".yaml", "yml": ".yml",
    "xml": ".xml", "sql": ".sql",
    "java": ".java", "kotlin": ".kt", "kt": ".kt",
    "c": ".c", "cpp": ".cpp", "c++": ".cpp", "cc": ".cc", "h": ".h", "hpp": ".hpp",
    "csharp": ".cs", "cs": ".cs",
    "go": ".go", "rust": ".rs", "rs": ".rs",
    "php": ".php", "ruby": ".rb", "rb": ".rb",
    "swift": ".swift", "dart": ".dart", "r": ".r",
    "markdown": ".md", "md": ".md",
    "text": ".txt", "txt": ".txt",
}

def _clean_code_language(value):
    lang = html.unescape(str(value or "")).strip().split()[0] if str(value or "").strip() else "text"
    lang = re.sub(r"[^A-Za-z0-9_+#.\-]+", "", lang).lower()
    return lang or "text"

def _code_extension(language):
    language = _clean_code_language(language)
    return CODE_LANGUAGE_EXTENSIONS.get(language, ".txt")

def _code_display_language(language):
    language = _clean_code_language(language)
    display = {
        "py": "Python",
        "js": "JavaScript",
        "ts": "TypeScript",
        "tsx": "TSX",
        "jsx": "JSX",
        "csharp": "C#",
        "cs": "C#",
        "cpp": "C++",
        "c++": "C++",
        "json": "JSON",
        "html": "HTML",
        "css": "CSS",
        "sql": "SQL",
        "xml": "XML",
        "yaml": "YAML",
        "yml": "YAML",
        "md": "Markdown",
        "markdown": "Markdown",
        "powershell": "PowerShell",
        "pwsh": "PowerShell",
        "bash": "Bash",
        "sh": "Shell",
        "shell": "Shell",
    }.get(language)
    return display or language.replace("-", " ").replace("_", " ").title()

def _split_markdown_code_blocks(text):
    text = str(text or "")
    pattern = re.compile(r"```([^\n`]*)\n?(.*?)```", re.DOTALL)
    parts = []
    last = 0
    for match in pattern.finditer(text):
        if match.start() > last:
            parts.append(("text", text[last:match.start()], ""))
        language = _clean_code_language(match.group(1))
        code = match.group(2)
        if code.endswith("\n"):
            code = code[:-1]
        parts.append(("code", code, language))
        last = match.end()
    if last < len(text):
        parts.append(("text", text[last:], ""))
    return parts or [("text", text, "")]

def _style_markdown_blocks(rendered_html, is_user=False, code_blocks=None):
    fg = BUBBLE_USER_TEXT if is_user else TEXT_COLOR
    muted = BUBBLE_USER_TEXT if is_user else MUTED_TEXT_COLOR
    code_bg = "rgba(3,19,29,0.18)" if is_user else CODE_BG_COLOR
    header_bg = "rgba(3,19,29,0.16)" if is_user else ACCENT_TINT
    border = "rgba(3,19,29,0.24)" if is_user else SOFT_LINE_COLOR

    html_text = str(rendered_html or "")
    copy_icon = _code_copy_icon_src()

    def repl_code_block(match):
        attrs = match.group(1) or ""
        code_html = match.group(2) or ""
        language = _code_language_from_attrs(attrs)
        clean_code = html.unescape(code_html).replace("\u200b", "")
        copy_index = None
        if isinstance(code_blocks, list):
            copy_index = len(code_blocks)
            code_blocks.append(clean_code)
        copy_link = ""
        if copy_index is not None:
            if copy_icon:
                copy_link = (
                    f'<a href="smarti-copy-code:{copy_index}" style="text-decoration:none;">'
                    f'<img src="{html.escape(copy_icon, quote=True)}" width="16" height="16" /></a>'
                )
            else:
                copy_link = f'<a href="smarti-copy-code:{copy_index}" style="color:{fg}; text-decoration:none; font-weight:800;">Copy</a>'
        header = (
            f'<div dir="ltr" align="left" style="background-color:{header_bg}; color:{muted}; '
            f'border:1px solid {border}; border-bottom:0; padding:7px 12px; margin:8px 0 0 0;">'
            '<table width="100%" cellspacing="0" cellpadding="0" style="border:0; margin:0;">'
            f'<tr><td align="left" style="border:0; color:{muted}; font-family:{ui_font_family_css()}; font-size:12px; font-weight:700;">{html.escape(language)}</td>'
            f'<td align="right" style="border:0;">{copy_link}</td></tr></table></div>'
        )
        body = (
            f'<pre dir="ltr" align="left" style="background-color:{code_bg}; color:{fg}; '
            f'border:1px solid {border}; border-top:0; padding:16px 18px; margin:0 0 9px 0; '
            'white-space:pre-wrap; text-align:left; direction:ltr; unicode-bidi:embed;">'
            f'<code{attrs} style="font-family:Consolas, Courier New, monospace; font-size:13px; '
            f'line-height:1.45; color:{fg}; background:transparent; text-align:left; direction:ltr; unicode-bidi:embed;">'
            f'{code_html}</code></pre>'
        )
        return header + body

    html_text = re.sub(
        r"<pre><code([^>]*)>(.*?)</code></pre>",
        repl_code_block,
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    html_text = re.sub(
        r"<code(?![^>]*style=)([^>]*)>",
        (
            f'<code\\1 style="font-family:Consolas, Courier New, monospace; font-size:13px; '
            f'background-color:{code_bg}; color:{fg}; padding:2px 4px; border-radius:4px;">'
        ),
        html_text,
        flags=re.IGNORECASE,
    )
    html_text = re.sub(
        r"<table>",
        (
            f'<table cellspacing="0" cellpadding="6" style="border-collapse:collapse; '
            f'border:1px solid {border}; margin:7px 0; color:{fg};">'
        ),
        html_text,
        flags=re.IGNORECASE,
    )
    html_text = re.sub(
        r"<th>",
        f'<th style="background-color:{header_bg}; color:{fg}; border:1px solid {border}; font-weight:700;">',
        html_text,
        flags=re.IGNORECASE,
    )
    html_text = re.sub(
        r"<td>",
        f'<td style="border:1px solid {border}; color:{fg};">',
        html_text,
        flags=re.IGNORECASE,
    )
    html_text = re.sub(
        r"<blockquote>",
        f'<blockquote style="border-right:3px solid {border}; color:{muted}; margin:6px 0; padding:3px 10px;">',
        html_text,
        flags=re.IGNORECASE,
    )
    return html_text

def _soft_break_rendered_text(rendered_html):
    segments = re.split(r"(<pre\b.*?</pre>|<a\b.*?</a>|<code\b.*?</code>)", str(rendered_html or ""), flags=re.IGNORECASE | re.DOTALL)
    rendered = []
    for segment in segments:
        if re.match(r"<(?:pre|a|code)\b", segment or "", flags=re.IGNORECASE):
            rendered.append(segment)
            continue
        parts = re.split(r"(<[^>]+>)", segment)
        rendered.append("".join(part if part.startswith("<") and part.endswith(">") else _escape_with_soft_breaks(part) for part in parts))
    return "".join(rendered)

def _trim_text_for_preview(text, limit=170):
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."

def _strip_broken_markdown_link_syntax(text):
    text = str(text or "")
    text = re.sub(r"\[([^\]\n]{1,240})\]\([^)]*$", r"\1", text)
    text = re.sub(r"\[([^\]\n]{1,240})$", r"\1", text)
    return text

def _render_markdown_links_fallback(text, link_color=None, clickable=True):
    style = ""
    if link_color:
        style = (
            f' style="color: {html.escape(str(link_color), quote=True)}; '
            'text-decoration: underline; font-weight: 800;"'
        )
    link_re = re.compile(r"\[([^\]\n]{0,240})\]\(([^)\n]{1,1000})\)")
    parts = []
    last = 0
    for match in link_re.finditer(str(text or "")):
        parts.append(_escape_with_soft_breaks(text[last:match.start()]).replace('\n', '<br>'))
        label = str(match.group(1) or "").strip()
        href = _canonical_display_href(match.group(2))
        display_label = label or _display_label_for_href(href)
        inner = _escape_with_soft_breaks(display_label)
        if _is_valid_display_href(href):
            if clickable:
                parts.append(f'<a href="{html.escape(href, quote=True)}"{style}>{inner}</a>')
            else:
                parts.append(f'<span{style}>{inner}</span>')
        else:
            parts.append(inner)
        last = match.end()
    parts.append(_escape_with_soft_breaks(str(text or "")[last:]).replace('\n', '<br>'))
    return "".join(parts)

def _markdown_preview_source(text, limit=170):
    source = re.sub(r"\s+", " ", str(text or "")).strip()
    if not source:
        return ""
    link_re = re.compile(r"\[([^\]\n]{0,240})\]\(([^)\n]{1,1000})\)")
    parts = []
    used = 0
    last = 0

    def append_plain(value):
        nonlocal used
        if used >= limit:
            return False
        remaining = limit - used
        value = str(value or "")
        if len(value) <= remaining:
            parts.append(value)
            used += len(value)
            return True
        parts.append(_trim_text_for_preview(value, remaining))
        used = limit
        return False

    for match in link_re.finditer(source):
        if not append_plain(source[last:match.start()]):
            break
        label = str(match.group(1) or "").strip()
        href = _canonical_display_href(match.group(2))
        display_label = label or _display_label_for_href(href)
        if _is_valid_display_href(href):
            if used + len(display_label) <= limit:
                parts.append(f"[{display_label}]({href})")
                used += len(display_label)
            else:
                append_plain(display_label)
                break
        else:
            if not append_plain(display_label):
                break
        last = match.end()
    else:
        append_plain(source[last:])

    return _strip_broken_markdown_link_syntax("".join(parts).strip())

def _render_markdown_html(text, link_color=None, is_user=False, style_blocks=True, clickable_links=True):
    text = _repair_markdown_links(html.unescape(str(text or "")))
    if not text.strip():
        return ""
    if MARKDOWN_INSTALLED:
        try:
            import markdown
            safe_markdown = html.escape(text, quote=False)
            rendered_html = markdown.markdown(safe_markdown, extensions=['tables', 'nl2br', 'sane_lists'])
            rendered_html = _sanitize_rendered_links(rendered_html, link_color, clickable_links)
            if style_blocks:
                rendered_html = _style_markdown_blocks(rendered_html, is_user, None)
            rendered_html = _suppress_asset_font_italic_html(rendered_html)
            return _soft_break_rendered_text(rendered_html)
        except Exception:
            pass
    rendered_html = _render_markdown_links_fallback(text, link_color, clickable_links)
    rendered_html = _suppress_asset_font_italic_html(rendered_html)
    return _sanitize_rendered_links(rendered_html, link_color, clickable_links)


def _suppress_asset_font_italic_html(rendered_html):
    if not app_uses_asset_font():
        return rendered_html
    html_text = str(rendered_html or "")
    html_text = re.sub(r"font-style\s*:\s*italic\s*;?", "font-style:normal;", html_text, flags=re.IGNORECASE)
    html_text = re.sub(r"<(/?)(?:em|i)(\b[^>]*)>", r"<\1span\2>", html_text, flags=re.IGNORECASE)
    return html_text

def _clean_step_for_display(text):
    clean = html.unescape(str(text or "")).strip()
    clean = re.sub(r'```.*?```', '', clean, flags=re.DOTALL).strip()
    if "tools/call" in clean or re.search(r'(?i)"method"\s*:\s*"(?:tools/call|agent_[^"]*|agent_planner)"', clean):
        clean = clean.split("{", 1)[0].strip()
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def _split_technical_details(text):
    main_lines = []
    detail_lines = []
    for line in str(text or "").splitlines():
        clean = line.strip()
        if clean.startswith("פרטים טכניים:"):
            detail_lines.append(clean)
        else:
            main_lines.append(line)
    main_text = "\n".join(main_lines).strip()
    detail_text = " ".join(detail_lines).strip()
    return main_text, detail_text


class WelcomeWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("WelcomeWidget")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMaximumWidth(860)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(0)

        self.title_lbl = QLabel()
        self.title_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.title_lbl)

        self.refresh_text()
        self.apply_theme()

    def refresh_text(self):
        self.title_lbl.setText(_welcome_prompt())
        self._sync_text_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_text_height()

    def _sync_text_height(self):
        margins = self.layout().contentsMargins()
        width = self.width() - margins.left() - margins.right()
        if width <= 0:
            width = self.title_lbl.width() or min(self.maximumWidth(), 720)
        width = max(240, width)
        doc = QTextDocument()
        doc.setDefaultFont(self.title_lbl.font())
        doc.setPlainText(self.title_lbl.text())
        doc.setTextWidth(max(1, width))
        text_height = int(math.ceil(doc.size().height())) + 8
        self.title_lbl.setMinimumHeight(text_height)
        self.setMinimumHeight(text_height + margins.top() + margins.bottom())
        self.updateGeometry()

    def apply_theme(self):
        self.setStyleSheet("QFrame#WelcomeWidget { background: transparent; border: none; }")
        font = app_font(26, QFont.Weight.Bold)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.title_lbl.setFont(font)
        self.title_lbl.setStyleSheet(
            f"color: {TEXT_COLOR}; background: transparent; border: none; "
        )
        self._sync_text_height()


class PillInputFrame(QFrame):
    CORNER_RADIUS = 40.5

    def __init__(self):
        super().__init__()
        self.setObjectName("InputFrame")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._hovered = False

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def apply_theme(self):
        self.setStyleSheet("background: transparent; border: none;")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(self.CORNER_RADIUS, rect.height() / 2.0, rect.width() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        if self._hovered:
            painter.fillPath(path, qcolor_from_css(FIELD_HOVER_COLOR))
            border_color = qcolor_from_css(LINE_COLOR)
        else:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, qcolor_from_css(GLASS_STRONG_COLOR))
            gradient.setColorAt(0.64, qcolor_from_css(INPUT_GRADIENT_END))
            gradient.setColorAt(1.0, qcolor_from_css("#170A2C" if CURRENT_THEME == "dark" else TOP_GRADIENT_C))
            painter.fillPath(path, QBrush(gradient))
            border_color = qcolor_from_css(SOFT_LINE_COLOR)

        painter.setPen(QPen(border_color, 1))
        painter.drawPath(path)
        painter.end()

class PinnedActionButtonHost(QWidget):
    BOTTOM_GAP = 7

    def __init__(self, button):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFixedWidth(button.width())
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, self.BOTTOM_GAP)
        layout.setSpacing(0)
        layout.addStretch(1)
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)

class CodeBlockWidget(QFrame):
    def __init__(self, code, language="text", parent_width=450):
        super().__init__()
        self.code = str(code or "")
        self.language = _clean_code_language(language)
        self.max_w = max(220, int(parent_width or 450))
        self.setObjectName("CodeBlockWidget")
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMaximumWidth(self.max_w)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 16)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.copy_btn = self._make_icon_button(
            "העתק קוד",
            (
                "code_copy_icon",
                "copy_icon",
            ),
            "⧉",
        )
        self.copy_btn.clicked.connect(self.copy_code)
        self.download_btn = self._make_icon_button(
            "הורד קובץ",
            (
                "code_download_icon",
                "download_icon",
            ),
            "↓",
        )
        self.download_btn.clicked.connect(self.download_code)
        header.addWidget(self.copy_btn)
        header.addWidget(self.download_btn)
        header.addStretch(1)

        self.language_lbl = QLabel(_code_display_language(self.language))
        self.language_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.language_lbl.setFont(app_font(10, QFont.Weight.Bold))
        self.language_lbl.setStyleSheet("border: none; background: transparent;")
        header.addWidget(self.language_lbl)
        layout.addLayout(header)

        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlainText(self.code)
        self.code_edit.setReadOnly(True)
        self.code_edit.setFrameShape(QFrame.Shape.NoFrame)
        self.code_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.code_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.code_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.code_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.code_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        option = self.code_edit.document().defaultTextOption()
        option.setTextDirection(Qt.LayoutDirection.LeftToRight)
        option.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.code_edit.document().setDefaultTextOption(option)
        layout.addWidget(self.code_edit)

        self.apply_theme()
        self._sync_height()

    def _make_icon_button(self, tooltip, filenames, fallback):
        btn = QPushButton()
        btn.setFixedSize(28, 28)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip(tooltip)
        set_themed_button_icon(btn, filenames, fallback, 18, clear_text=True)
        return btn

    def _button_css(self):
        return (
            "QPushButton { background: transparent; border: 1px solid transparent; border-radius: 14px; "
            f"color: {TEXT_COLOR}; padding: 0px; font-size: 18px; font-weight: 800; outline: none; }}"
            f"QPushButton:hover {{ background: {ACCENT_TINT}; border-color: {SOFT_LINE_COLOR}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_TINT_STRONG}; border-color: {LINE_COLOR}; }}"
        )

    def apply_theme(self):
        code_bg = "rgba(2,6,18,0.82)" if CURRENT_THEME == "dark" else "#F7FAFF"
        code_border = "rgba(53,217,255,0.22)" if CURRENT_THEME == "dark" else SOFT_LINE_COLOR
        code_text = "#F8FBFF" if CURRENT_THEME == "dark" else "#062033"
        muted = "#F6F7FA" if CURRENT_THEME == "dark" else TEXT_COLOR
        selection = "rgba(255,77,221,0.22)" if CURRENT_THEME == "dark" else ACCENT_TINT_STRONG
        self.setStyleSheet(
            f"QFrame#CodeBlockWidget {{ background: {code_bg}; border: 1px solid {code_border}; border-radius: 22px; }}"
        )
        refresh_themed_button_icon(self.copy_btn)
        refresh_themed_button_icon(self.download_btn)
        self.copy_btn.setStyleSheet(self._button_css())
        self.download_btn.setStyleSheet(self._button_css())
        self.language_lbl.setStyleSheet(
            f"color: {muted}; font-size: 13px; font-weight: 800; border: none; background: transparent;"
        )
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.code_edit.setFont(font)
        self.code_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; color: {code_text}; border: none; "
            "padding: 6px 0px 0px 0px; font-family: Consolas, 'Courier New', monospace; "
            "font-size: 13px; line-height: 1.45; selection-background-color: "
            f"{selection}; selection-color: {code_text}; }}"
            "QPlainTextEdit viewport { background: transparent; }"
            f"{SCROLLBAR_CSS}"
        )

    def _sync_height(self):
        font_metrics = QFontMetrics(self.code_edit.font())
        line_count = max(1, self.code.count("\n") + 1)
        line_height = max(18, font_metrics.lineSpacing() + 3)
        height = min(max(58, line_count * line_height + 20), 340)
        self.code_edit.setFixedHeight(height)
        self.setFixedHeight(height + 66)

    def update_parent_width(self, parent_width):
        self.max_w = max(220, int(parent_width or 450))
        self.setMaximumWidth(self.max_w)
        self._sync_height()

    def copy_code(self):
        QApplication.clipboard().setText(self.code)

    def download_code(self):
        ext = _code_extension(self.language)
        default_path = os.path.join(OUTPUTS_DIR, f"smarti_code{ext}")
        filter_label = f"{_code_display_language(self.language)} (*{ext});;All files (*.*)"
        path, _ = QFileDialog.getSaveFileName(self, "שמירת קוד", default_path, filter_label)
        if not path:
            return
        root, suffix = os.path.splitext(path)
        if not suffix:
            path = root + ext
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(self.code)
        except Exception as e:
            QMessageBox.warning(self, "שגיאה בשמירת קוד", str(e))

def _open_attachment_path(path):
    path = os.path.abspath(str(path or "").strip(' "\''))
    if path and os.path.exists(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return True
    return False

def _open_local_link_path(path):
    path = _clean_local_path(path)
    if not _is_safe_local_link_path(path):
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(path))

def _attachment_icon_text(item):
    kind = str(item.get("kind", "document") or "document")
    ext = os.path.splitext(str(item.get("name") or item.get("path") or ""))[1].upper().lstrip(".")
    if kind == "image":
        return "IMG"
    if kind == "video":
        return "VID"
    if kind == "audio":
        return "AUD"
    return ext[:4] or "DOC"

def _set_button_icon_or_text(button, icon_names, fallback_text="", icon_size=20):
    set_themed_button_icon(button, icon_names, fallback_text, icon_size, clear_text=True)

class AttachmentTile(QFrame):
    remove_requested = pyqtSignal(object)

    def __init__(self, attachment, removable=False, compact=False):
        super().__init__()
        self.attachment = normalize_attachment(attachment) or {}
        self.removable = bool(removable)
        self.compact = bool(compact)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._is_image = self.attachment.get("kind") == "image"
        if self._is_image:
            self._build_image_tile()
        else:
            self._build_file_tile()

    def _remove_button(self, size=22):
        btn = QPushButton()
        btn.setFixedSize(size, size)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip("הסר קובץ")
        btn.setStyleSheet(
            "QPushButton { background: rgba(0,0,0,180); color: white; border: none; "
            f"border-radius: {size // 2}px; padding: 0px; font-weight: 800; }}"
            "QPushButton:hover { background: rgba(0,0,0,220); }"
        )
        _set_button_icon_or_text(btn, ("attachment_remove_icon", "remove_attachment_icon", "close_icon", "x_icon"), "X", max(12, size - 8))
        btn.clicked.connect(lambda: self.remove_requested.emit(self.attachment))
        return btn

    def apply_theme(self):
        refresh_themed_widget_icons(self)
        if not self._is_image:
            self.setStyleSheet(
                f"AttachmentTile {{ background: {GLASS_COLOR}; border: 1px solid {LINE_COLOR}; "
                f"border-radius: 16px; }}"
                f"QLabel {{ background: transparent; color: {TEXT_COLOR}; }}"
            )

    def _build_image_tile(self):
        path = self.attachment.get("path", "")
        pixmap = QPixmap(path) if os.path.exists(path) else QPixmap()
        if self.removable:
            side = 68
            self.setFixedSize(side, side)
            self.setStyleSheet("AttachmentTile { background: transparent; border: none; }")
            layout = QGridLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            label = QLabel()
            label.setFixedSize(side, side)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(f"background: {GLASS_COLOR}; border: 1px solid {LINE_COLOR}; border-radius: 16px;")
            if not pixmap.isNull():
                label.setPixmap(pixmap.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            else:
                label.setText("IMG")
            layout.addWidget(label, 0, 0)
            layout.addWidget(self._remove_button(22), 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
            return

        max_w = max(180, min(360, self.maximumWidth() if self.maximumWidth() < 16777215 else 320))
        if pixmap.isNull():
            width, height = 220, 140
        else:
            width = min(max_w, max(180, pixmap.width()))
            height = max(90, int(width * pixmap.height() / max(1, pixmap.width())))
        self.setFixedSize(width, height)
        self.setStyleSheet("AttachmentTile { background: transparent; border: none; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel()
        label.setFixedSize(width, height)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background: transparent; border: none;")
        if not pixmap.isNull():
            label.setPixmap(pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            label.setText("IMG")
        layout.addWidget(label)

    def _build_file_tile(self):
        self.setMinimumWidth(270 if self.compact else 300)
        self.setMaximumWidth(430)
        self.setFixedHeight(68 if self.compact else 72)
        self.setStyleSheet(
            f"AttachmentTile {{ background: {GLASS_COLOR}; border: 1px solid {LINE_COLOR}; "
            f"border-radius: 16px; }}"
            f"QLabel {{ background: transparent; color: {TEXT_COLOR}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(10)

        layout.addWidget(self._preview_widget(), 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(3)
        name = QLabel(str(self.attachment.get("name") or os.path.basename(self.attachment.get("path", "")) or "קובץ"))
        name.setWordWrap(True)
        name.setMaximumWidth(250 if self.compact else 300)
        name.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; font-weight: 800;")
        info.addWidget(name)
        meta = QLabel(f"File · {human_file_size(self.attachment.get('size'))}")
        meta.setStyleSheet(muted_label_css(12))
        info.addWidget(meta)
        layout.addLayout(info, 1)
        if self.removable:
            layout.addWidget(self._remove_button(22), 0, Qt.AlignmentFlag.AlignTop)

    def _preview_widget(self):
        label = QLabel(_attachment_icon_text(self.attachment))
        label.setFixedSize(50, 50)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"background: {ACCENT_TINT}; color: {ACCENT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            f"border-radius: 14px; font-size: 11px; font-weight: 800;"
        )
        set_themed_label_icon(label, ("file_attachment_icon", "attachment_file_icon", "file_icon"), _attachment_icon_text(self.attachment), 28)
        return label

    def open_attachment(self):
        if not _open_attachment_path(self.attachment.get("path", "")):
            QMessageBox.warning(self, "קובץ לא נמצא", "הקובץ המצורף לא נמצא במיקום המקומי שלו.")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_attachment()
            event.accept()
            return
        super().mousePressEvent(event)

class AttachmentPreviewStrip(QWidget):
    remove_requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(82)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        self.layout = QHBoxLayout(self.content)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(8)
        self.layout.addStretch()
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)
        self.hide()

    def set_attachments(self, attachments):
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        attachments = normalize_attachments(attachments)
        for item in attachments:
            tile = AttachmentTile(item, removable=True, compact=True)
            tile.remove_requested.connect(self.remove_requested.emit)
            self.layout.addWidget(tile)
        self.layout.addStretch()
        self.setVisible(bool(attachments))

    def apply_theme(self):
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.content.setStyleSheet("background: transparent;")
        for tile in self.findChildren(AttachmentTile):
            tile.apply_theme()

# Google Drive picker UI is parked until OAuth sign-in is reworked.

AGENT_TOOL_DEFAULT_ICON_NAMES = ("agent_tool_row_status",)
AGENT_TOOL_GROUP_ICON_NAMES = ("agent_tool_status", "agent_tool_icon", "tools_icon")
AGENT_TOOL_MCP_ACTIONS = {"search_mcp", "install_mcp", "run_mcp"}
AGENT_TOOL_SKILL_ACTIONS = {"list_skills", "search_skills", "install_skill", "install_skill_requirements", "run_skill"}
AGENT_TOOL_BUILTIN_ACTIONS = set(BUILT_IN_TOOLS) | set(LEGACY_BUILTIN_TOOLS) | set(PUBLIC_BUILTIN_TOOLS) | {"agent_planner"}

def _agent_tool_asset_stem(name):
    stem = re.sub(r"[^0-9a-zA-Z]+", "_", str(name or "").strip().lower()).strip("_")
    return stem

def _agent_tool_unique_icon_names(names):
    result = []
    seen = set()
    for name in names:
        value = str(name or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)

def _agent_tool_icon_names(tool):
    tool = tool if isinstance(tool, dict) else {}
    action = str(tool.get("action") or "").strip()
    effective = str(tool.get("effective_action") or "").strip()
    args = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else {}
    manager_action = str(args.get("action") or "").strip()
    target = str(args.get("target") or "").strip()
    action_names = {name for name in (action, effective, manager_action) if name}
    candidates = []

    if action == "extension_manager":
        if manager_action in AGENT_TOOL_MCP_ACTIONS:
            candidates.extend(("agent_tool_mcp", "agent_tool_extension_manager"))
        elif manager_action in AGENT_TOOL_SKILL_ACTIONS:
            candidates.extend(("agent_tool_skill", "agent_tool_extension_manager"))
    if action_names & AGENT_TOOL_MCP_ACTIONS:
        candidates.append("agent_tool_mcp")
    if action_names & AGENT_TOOL_SKILL_ACTIONS:
        candidates.append("agent_tool_skill")

    if action == "automation_manager" and target:
        target_stem = _agent_tool_asset_stem(target)
        if target_stem:
            candidates.append(f"agent_tool_automation_manager_{target_stem}")
    if action and manager_action:
        action_stem = _agent_tool_asset_stem(action)
        manager_stem = _agent_tool_asset_stem(manager_action)
        if action_stem and manager_stem:
            candidates.append(f"agent_tool_{action_stem}_{manager_stem}")

    for name in (effective, action):
        if name in AGENT_TOOL_BUILTIN_ACTIONS:
            stem = _agent_tool_asset_stem(name)
            if stem:
                candidates.append(f"agent_tool_{stem}")

    candidates.extend(AGENT_TOOL_DEFAULT_ICON_NAMES)
    return _agent_tool_unique_icon_names(candidates)

def _agent_tool_display_name(tool):
    tool = tool if isinstance(tool, dict) else {}
    action = str(tool.get("action") or "").strip()
    effective = str(tool.get("effective_action") or "").strip()
    args = tool.get("arguments") if isinstance(tool.get("arguments"), dict) else {}
    manager_action = str(args.get("action") or "").strip()
    name = action or effective or "tool"
    if manager_action and manager_action != name:
        name = f"{name} / {manager_action}"
    elif effective and effective != action:
        name = f"{name} / {effective}"
    return re.sub(r"\s+", " ", name).strip()

def _agent_tool_payload_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str).strip()
    except Exception:
        return str(value or "").strip()

def _agent_tool_query_text(tool):
    tool = tool if isinstance(tool, dict) else {}
    return (
        _agent_tool_payload_text(tool.get("arguments_text"))
        or _agent_tool_payload_text(tool.get("arguments"))
        or _agent_tool_display_name(tool)
    )

def _agent_tool_output_text(tool):
    tool = tool if isinstance(tool, dict) else {}
    for key in ("output_text", "output", "feedback", "message"):
        text = _agent_tool_payload_text(tool.get(key))
        if text:
            return text
    return ""

def _agent_tool_status_text(status):
    status = str(status or "").strip().lower()
    if status in {"running", "active", "started"}:
        return "רץ"
    if status in {"ok", "success", "done", "completed"}:
        return "הצליח"
    if status in {"cancelled", "canceled", "stopped"}:
        return "בוטל"
    if status:
        return "נכשל"
    return ""

class AgentToolDetailWidget(QWidget):
    CHEVRON_ICON_NAMES = ("agent_tool_row_chevron", "agent_tool_detail_chevron", "agent_process_chevron", "message_collapse_arrow")
    QUERY_TITLE = "קלט ופרמטרי הפעלה"
    OUTPUT_TITLE = "פלט הכלי"

    def __init__(self, tool, parent_width=450):
        super().__init__()
        self.tool = dict(tool if isinstance(tool, dict) else {"action": str(tool or "")})
        self.max_w = max(220, int(parent_width or 450))
        self.expanded = False
        self.setStyleSheet("background: transparent; border: none;")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(self.max_w)
        self.setMaximumWidth(self.max_w)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.row = QFrame()
        self.row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.row.installEventFilter(self)
        self.row.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        row_layout = QHBoxLayout(self.row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(1)

        self.arrow_label = QLabel()
        self.arrow_label.setFixedSize(14, 16)
        self.arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.tool_icon_label = QLabel()
        self.tool_icon_label.setFixedSize(16, 16)
        self.tool_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tool_icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.name_label = QLabel()
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumWidth(max(150, self.max_w - 42))
        self.name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.name_label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        row_layout.addStretch(1)
        row_layout.addWidget(self.arrow_label, 0, Qt.AlignmentFlag.AlignVCenter)
        row_layout.addWidget(self.name_label, 0)
        row_layout.addWidget(self.tool_icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.row)

        self.panel = QFrame()
        self.panel.setObjectName("AgentToolDetailPanel")
        self.panel.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.panel.setMinimumWidth(self.max_w)
        self.panel.setMaximumWidth(self.max_w)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(10, 9, 10, 8)
        panel_layout.setSpacing(5)

        self.query_title = QLabel(self.QUERY_TITLE)
        self.query_title.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.query_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.query_box = self._make_text_box()
        self.output_title = QLabel(self.OUTPUT_TITLE)
        self.output_title.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.output_title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.output_box = self._make_text_box()
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        panel_layout.addWidget(self.query_title)
        panel_layout.addWidget(self.query_box)
        panel_layout.addWidget(self.output_title)
        panel_layout.addWidget(self.output_box)
        panel_layout.addWidget(self.status_label)
        self.panel.hide()
        layout.addWidget(self.panel)

        self.update_tool(self.tool)
        self.apply_theme()

    def _make_text_box(self):
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setFrameShape(QFrame.Shape.NoFrame)
        box.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        box.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        box.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        box.setMinimumHeight(34)
        box.setMaximumHeight(34)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return box

    def _apply_dynamic_text_box_height(self, box, text, min_lines=1, max_lines=7):
        text = str(text or "")
        line_count = max(1, len(text.splitlines()) if text else 1)
        visible_lines = min(max_lines, max(min_lines, line_count))
        metrics = QFontMetrics(box.font())
        height = (metrics.lineSpacing() * visible_lines) + 18
        if line_count > max_lines:
            height += 8
            box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        box.setMinimumHeight(height)
        box.setMaximumHeight(height)

    def eventFilter(self, obj, event):
        if obj is self.row and event.type() == QEvent.Type.MouseButtonPress:
            self.set_expanded(not self.expanded)
            return True
        return super().eventFilter(obj, event)

    def update_parent_width(self, parent_width):
        self.max_w = max(220, int(parent_width or 450))
        self.setMinimumWidth(self.max_w)
        self.setMaximumWidth(self.max_w)
        self._fit_name_label_width()
        self.panel.setMinimumWidth(self.max_w)
        self.panel.setMaximumWidth(self.max_w)
        self._apply_dynamic_text_box_height(self.query_box, self.query_box.toPlainText(), min_lines=1, max_lines=5)
        if not self.output_box.isHidden():
            self._apply_dynamic_text_box_height(self.output_box, self.output_box.toPlainText(), min_lines=1, max_lines=8)

    def _fit_name_label_width(self):
        available = max(120, self.max_w - 42)
        text = str(self.name_label.text() or "")
        width = _fitted_plain_label_width(self.name_label, text, available, min_width=42, padding=8)
        self.name_label.setWordWrap(width >= available)
        self.name_label.setMinimumWidth(width)
        self.name_label.setMaximumWidth(width)

    def _refresh_tool_icon(self):
        set_themed_label_icon(self.tool_icon_label, _agent_tool_icon_names(self.tool), "", 15)

    def update_tool(self, tool):
        if isinstance(tool, dict):
            self.tool.update(tool)
        name = _agent_tool_display_name(self.tool)
        status_text = _agent_tool_status_text(self.tool.get("status"))
        self.name_label.setText(f"{status_text} · {name}" if status_text else name)
        self._fit_name_label_width()
        query_text = _agent_tool_query_text(self.tool)
        output_text = _agent_tool_output_text(self.tool)
        is_running = str(self.tool.get("status") or "").strip().lower() in {"running", "active", "started"}
        self.query_box.setPlainText(query_text)
        self._apply_dynamic_text_box_height(self.query_box, query_text, min_lines=1, max_lines=5)
        show_output = bool(output_text) or not is_running
        self.output_title.setVisible(show_output)
        self.output_box.setVisible(show_output)
        if show_output:
            output_display = output_text or "אין פלט."
            self.output_box.setPlainText(output_display)
            self._apply_dynamic_text_box_height(self.output_box, output_display, min_lines=1, max_lines=8)
        self.status_label.setText(status_text)
        self._refresh_tool_icon()
        self._set_chevron_icon()

    def set_expanded(self, expanded):
        self.expanded = bool(expanded)
        self.panel.setVisible(self.expanded)
        self._set_chevron_icon()
        self.updateGeometry()

    def _set_chevron_icon(self):
        icon_size = 14
        icon = _rotated_themed_icon(self.CHEVRON_ICON_NAMES, 90 if self.expanded else 0, icon_size)
        if icon.isNull():
            icon = _transparent_icon(icon_size)
        self.arrow_label.setPixmap(icon.pixmap(icon_size, icon_size))
        self.arrow_label.setText("")

    def apply_theme(self):
        self.row.setStyleSheet("background: transparent; border: none;")
        self.name_label.setStyleSheet(f"color: {SUBTLE_TEXT_COLOR}; font-size: 15px; background: transparent; padding-right: 5px; padding-left: 0px;")
        self.arrow_label.setStyleSheet(f"color: {SUBTLE_TEXT_COLOR}; background: transparent;")
        self.tool_icon_label.setStyleSheet("background: transparent; border: none;")
        self._refresh_tool_icon()
        self.panel.setStyleSheet(
            f"QFrame#AgentToolDetailPanel {{ background: {FIELD_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 8px; }}"
            f"QPlainTextEdit {{ background: transparent; color: {SUBTLE_TEXT_COLOR}; border: none; "
            "font-size: 13px; font-family: Consolas, 'Courier New'; padding: 0px; }"
            "QPlainTextEdit viewport { background: transparent; }"
            f"QLabel {{ color: {MUTED_TEXT_COLOR}; font-size: 13px; background: transparent; }}"
            f"{SCROLLBAR_CSS}"
        )
        self._set_chevron_icon()

class AgentToolGroupWidget(QWidget):
    CHEVRON_ICON_NAMES = ("agent_process_chevron", "message_collapse_arrow")
    TOOL_ROW_INDENT = 34

    def __init__(self, parent_width=450):
        super().__init__()
        self.max_w = max(220, int(parent_width or 450))
        self.tools = []
        self.tool_widgets = []
        self.run_count = 0
        self.details_expanded = False
        self.running = False
        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumWidth(self.max_w)
        self.setMaximumWidth(self.max_w)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(4)

        self.status_row = QFrame()
        self.status_row.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.status_row.installEventFilter(self)
        self.status_row.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        status_layout = QHBoxLayout(self.status_row)
        status_layout.setContentsMargins(0, 0, 3, 0)
        status_layout.setSpacing(7)
        self.status_row.setToolTip("לחץ להצגת פרטי הכלים")

        self.tool_icon_label = QLabel()
        self.tool_icon_label.setFixedSize(18, 18)
        self.tool_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tool_icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.status_label = StepsShimmerLabel()
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumWidth(1)
        self.status_label.setMaximumWidth(max(150, self.max_w - 72))
        self.status_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.status_label.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.arrow_label = QLabel()
        self.arrow_label.setFixedSize(16, 18)
        self.arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        status_layout.addStretch(1)
        status_layout.addWidget(self.arrow_label, 0, Qt.AlignmentFlag.AlignVCenter)
        status_layout.addWidget(self.status_label, 0)
        status_layout.addWidget(self.tool_icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.status_row)

        self.details_label = QLabel()
        self.details_label.setTextFormat(Qt.TextFormat.RichText)
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_label.setMaximumWidth(self.max_w)
        self.details_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignTop)
        self.details_label.hide()
        layout.addWidget(self.details_label)

        self.tools_container = QWidget()
        self.tools_container.setStyleSheet("background: transparent; border: none;")
        self.tools_container.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.tools_container.setMaximumWidth(self.max_w)
        self.tools_layout = QVBoxLayout(self.tools_container)
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(5)
        self.tools_container.hide()
        layout.addWidget(self.tools_container)

        self.thinking_label = StepsShimmerLabel()
        self.thinking_label.setTextFormat(Qt.TextFormat.PlainText)
        self.thinking_label.setWordWrap(True)
        self.thinking_label.setMaximumWidth(self.max_w)
        self.thinking_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.thinking_label.hide()
        layout.addWidget(self.thinking_label)

        self.hide()
        self.apply_theme()

    def eventFilter(self, obj, event):
        if obj is self.status_row and event.type() == QEvent.Type.MouseButtonPress:
            self.toggle_details()
            return True
        return super().eventFilter(obj, event)

    def apply_theme(self):
        self.status_row.setStyleSheet("background: transparent; border: none;")
        self.status_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 15px; background: transparent; padding-right: 12px; padding-left: 0px;")
        self.arrow_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 15px; background: transparent;")
        self.tool_icon_label.setStyleSheet("background: transparent; border: none;")
        self.details_label.setStyleSheet(f"color: {SUBTLE_TEXT_COLOR}; font-size: 15px; background: transparent; padding: 0px 0px 3px 0px;")
        self.thinking_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 15px; background: transparent;")
        self._refresh_tool_icon()
        self._set_chevron_icon()
        for widget in getattr(self, "tool_widgets", []):
            widget.apply_theme()

    def update_parent_width(self, parent_width):
        self.max_w = max(220, int(parent_width or 450))
        self.setMinimumWidth(self.max_w)
        self.setMaximumWidth(self.max_w)
        self._fit_status_label_width()
        self.details_label.setMaximumWidth(self.max_w)
        self.tools_container.setMaximumWidth(self.max_w)
        self.thinking_label.setMaximumWidth(self.max_w)
        for widget in getattr(self, "tool_widgets", []):
            widget.update_parent_width(max(220, self.max_w - self.TOOL_ROW_INDENT))

    def _fit_status_label_width(self):
        available = max(120, self.max_w - 72)
        text = str(self.status_label.text() or "")
        width = _fitted_plain_label_width(self.status_label, text, available, min_width=48, padding=22)
        self.status_label.setWordWrap(width >= available)
        self.status_label.setMinimumWidth(width)
        self.status_label.setMaximumWidth(width)

    def _refresh_tool_icon(self):
        icon_names = AGENT_TOOL_GROUP_ICON_NAMES
        if self.running:
            running_tools = [tool for tool in self.tools if str(tool.get("status") or "").strip().lower() in {"running", "active", "started"}]
            if len(running_tools) == 1:
                icon_names = _agent_tool_icon_names(running_tools[0])
        set_themed_label_icon(self.tool_icon_label, icon_names, "", 16)

    def _add_tool_widget(self, item):
        widget = AgentToolDetailWidget(item, max(220, self.max_w - self.TOOL_ROW_INDENT))
        self.tool_widgets.append(widget)
        self.tools_layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)
        widget.apply_theme()
        return widget

    def _update_tool_widget(self, index, item):
        if 0 <= index < len(self.tool_widgets):
            self.tool_widgets[index].update_tool(item)

    def _tool_detail_html(self):
        rows = []
        for tool in self.tools:
            name = _escape_with_soft_breaks(_agent_tool_display_name(tool))
            status = str(tool.get("status") or "").lower()
            status_text = "רץ" if status == "running" else ("שגיאה" if status in {"error", "crash", "cancelled"} else "הסתיים")
            rows.append(
                f"<div style='margin: 2px 0; color:{SUBTLE_TEXT_COLOR}; font-size:15px;'>"
                f"• {name} · {html.escape(status_text)}</div>"
            )
        return "".join(rows)

    def _refresh_details(self):
        self.details_label.hide()
        self.tools_container.setVisible(self.details_expanded and bool(self.tools))
        self._set_chevron_icon()

    def _set_chevron_icon(self):
        icon = _rotated_themed_icon(self.CHEVRON_ICON_NAMES, -90 if self.details_expanded else 0, 16)
        if icon.isNull():
            icon = _transparent_icon(16)
        self.arrow_label.setPixmap(icon.pixmap(16, 16))
        self.arrow_label.setText("")

    def collapse_details(self):
        self.details_expanded = False
        for widget in getattr(self, "tool_widgets", []):
            widget.set_expanded(False)
        self._refresh_details()

    def toggle_details(self):
        if not self.tools:
            return
        self.details_expanded = not self.details_expanded
        self._refresh_details()
        self.updateGeometry()

    def hide_thinking(self):
        self.thinking_label.stop_shimmer()
        self.thinking_label.hide()

    def show_thinking(self):
        if not str(self.status_label.text() or "").strip() or self.running:
            return
        self.thinking_label.setText("חושב...")
        self.thinking_label.show()
        self.thinking_label.start_shimmer()
        self.show()

    def start_tools(self, tools, parallel=False):
        tools = [tool if isinstance(tool, dict) else {"action": str(tool or "")} for tool in (tools or [])]
        if not tools:
            return
        self.hide_thinking()
        for tool in tools:
            item = dict(tool)
            item["status"] = "running"
            self.tools.append(item)
            self._add_tool_widget(item)
        self.running = True
        self._refresh_tool_icon()
        if parallel and len(tools) > 1:
            text = f"מריץ: {len(tools)} כלים במקביל"
        else:
            text = f"מריץ: כלי {_agent_tool_display_name(tools[0])}"
        self.status_label.setText(text)
        self._fit_status_label_width()
        self.status_label.start_shimmer()
        self._refresh_details()
        self.show()

    def finish_tools(self, results):
        results = [result if isinstance(result, dict) else {"action": str(result or "")} for result in (results or [])]
        for result in results:
            updated = False
            updated_index = -1
            result_action = str(result.get("action") or "")
            result_event_id = str(result.get("event_id") or result.get("call_id") or "").strip()
            result_args = result.get("arguments") if isinstance(result.get("arguments"), dict) else None
            for index in range(len(self.tools) - 1, -1, -1):
                item = self.tools[index]
                if item.get("status") != "running":
                    continue
                item_event_id = str(item.get("event_id") or item.get("call_id") or "").strip()
                if result_event_id or item_event_id:
                    if result_event_id != item_event_id:
                        continue
                elif str(item.get("action") or "") != result_action:
                    continue
                else:
                    item_args = item.get("arguments") if isinstance(item.get("arguments"), dict) else None
                    if result_args is not None and item_args is not None and item_args != result_args:
                        continue
                item.update(result)
                item["status"] = str(result.get("status") or "ok")
                updated = True
                updated_index = index
                break
            if not updated:
                item = dict(result)
                item["status"] = str(result.get("status") or "ok")
                self.tools.append(item)
                self._add_tool_widget(item)
            else:
                self._update_tool_widget(updated_index, item)
        self.run_count += len(results)
        for index, item in enumerate(self.tools):
            if item.get("status") == "running":
                item["status"] = "ok"
                self._update_tool_widget(index, item)
        self.running = False
        if self.run_count:
            self.status_label.setText(f"הורצו {self.run_count} כלים")
            self._fit_status_label_width()
        self.status_label.stop_shimmer()
        self._refresh_tool_icon()
        self._refresh_details()
        self.show_thinking()
        self.show()

class CanvasOpenButton(QPushButton):
    """A themed canvas trigger that wraps naturally, with a strict two-line cap."""

    MAX_LINES = 2

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAccessibleName(str(text or "פתח קנבס"))

    def _display_lines(self, width):
        available = max(80, int(width) - 32)
        words = str(self.text() or "").split()
        if not words:
            return [""]
        metrics = QFontMetrics(self.font())
        lines = []
        current = ""
        for index, word in enumerate(words):
            candidate = f"{current} {word}".strip()
            if not current or metrics.horizontalAdvance(candidate) <= available:
                current = candidate
                continue
            lines.append(current)
            current = word
            if len(lines) == self.MAX_LINES - 1:
                remainder = " ".join([current, *words[index + 1:]])
                lines.append(metrics.elidedText(remainder, Qt.TextElideMode.ElideRight, available))
                return lines
        if current:
            lines.append(current)
        return lines[:self.MAX_LINES]

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        line_count = max(1, len(self._display_lines(width)))
        return max(44, line_count * QFontMetrics(self.font()).lineSpacing() + 20)

    def sizeHint(self):
        width = min(420, max(260, super().sizeHint().width()))
        return QSize(width, self.heightForWidth(width))

    def minimumSizeHint(self):
        return QSize(200, self.heightForWidth(240))

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        painter.setPen(option.palette.buttonText().color())
        text_rect = self.contentsRect().adjusted(16, 8, -16, -8)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            "\n".join(self._display_lines(text_rect.width())),
        )
        painter.end()


class MessageBubble(QFrame):
    user_collapse_changed = pyqtSignal(bool, bool)
    canvas_open_requested = pyqtSignal(object)

    USER_COLLAPSED_LINES = 6
    WIDGET_MAX_HEIGHT = 16777215
    PROCESS_CHEVRON_ICON_NAMES = ("agent_process_chevron", "message_collapse_arrow")

    def __init__(self, text, is_user=False, parent_width=450, attachments=None, canvases=None, is_background_task=False):
        super().__init__()
        self.is_background_task = is_background_task
        self.is_user = is_user
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum if self.is_user else QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.main_layout = QVBoxLayout(self)
        if self.is_user:
            self.main_layout.setContentsMargins(20, 16, 20, 16)
            self.max_w = max(220, int(parent_width * 0.76) - 30)
        else:
            self.main_layout.setContentsMargins(10, 8, 10, 8)
            self.max_w = max(240, int(parent_width or 450) - 52)
        self.copy_text = str(text or "")
        self.attachments = normalize_attachments(attachments or [])
        self.canvas_artifacts = [artifact for item in (canvases or []) if (artifact := normalize_canvas_artifact(item))]
        self._canvas_buttons = []
        self.code_blocks = []
        self._user_message_collapsible = False
        self._user_message_collapsed = True
        
        self.steps_container = QWidget()
        self.steps_container.setStyleSheet("background: transparent; border: none;")
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 8)
        self.steps_layout.setSpacing(8)

        # Kept separate from the agent-process groups so a direct model answer
        # can show the familiar shimmer before there are tools or reports.
        self.initial_thinking_label = StepsShimmerLabel()
        self.initial_thinking_label.setTextFormat(Qt.TextFormat.PlainText)
        self.initial_thinking_label.setWordWrap(True)
        self.initial_thinking_label.setMaximumWidth(self.max_w)
        self.initial_thinking_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter
        )
        self.initial_thinking_label.hide()

        self.process_header = QFrame()
        self.process_header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.process_header.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.process_header.setMaximumWidth(self.max_w)
        process_header_layout = QHBoxLayout(self.process_header)
        process_header_layout.setContentsMargins(0, 0, 0, 0)
        process_header_layout.setSpacing(2)

        self.process_arrow_label = QLabel()
        self.process_arrow_label.setFixedSize(16, 18)
        self.process_arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.process_arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.toggle_btn = QLabel("")
        self.toggle_btn.setTextFormat(Qt.TextFormat.PlainText)
        self.toggle_btn.setWordWrap(True)
        self.toggle_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.toggle_btn.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.toggle_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.toggle_btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        process_header_layout.addStretch(1)
        process_header_layout.addWidget(self.process_arrow_label, 0, Qt.AlignmentFlag.AlignVCenter)
        process_header_layout.addWidget(self.toggle_btn, 0)

        self.process_details = QWidget()
        self.process_details.setStyleSheet("background: transparent; border: none;")
        self.process_details_layout = QVBoxLayout(self.process_details)
        self.process_details_layout.setContentsMargins(0, 0, 0, 0)
        self.process_details_layout.setSpacing(8)

        self.steps_label = QLabel()
        self.steps_label.hide()
        self.steps_layout.addWidget(self.initial_thinking_label)
        self.steps_layout.addWidget(self.process_header)
        self.steps_layout.addWidget(self.process_details)
        self.process_header.hide()
        self.process_details.hide()
        self.steps_container.hide()
        
        self.final_label = QLabel(self)
        self.final_label.setTextFormat(Qt.TextFormat.RichText)
        self.final_label.setWordWrap(True)
        self.final_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction | Qt.TextInteractionFlag.TextSelectableByMouse)
        self.final_label.setOpenExternalLinks(False)
        self.final_label.linkActivated.connect(self._handle_link_activated)
        self.final_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.final_label.setMaximumWidth(self.max_w)
        self.final_label.hide()
        self.final_label.installEventFilter(self)
        self._final_label_fade_effect = None

        self.final_content = QWidget()
        self.final_content.setStyleSheet("background: transparent; border: none;")
        self.final_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.final_layout = QVBoxLayout(self.final_content)
        self.final_layout.setContentsMargins(0, 0, 0, 0)
        self.final_layout.setSpacing(8)
        
        self.main_layout.addWidget(self.steps_container)
        self.main_layout.addWidget(self.final_content)
        
        self.steps_text_html = ""
        self.is_expanded = True
        self.agent_process_started = False
        self.agent_process_finalized = False
        self.agent_process_start_time = 0.0
        self.agent_process_elapsed_seconds = 0
        self.agent_report_labels = []
        self.agent_process_groups = []
        self.current_process_group = None
        self.process_copy_text_parts = []
        self.agent_process_timer = QTimer(self)
        self.agent_process_timer.setInterval(1000)
        self.agent_process_timer.timeout.connect(self._update_agent_process_timer)
        self.process_header.installEventFilter(self)
        
        if text:
            self.set_final_text(text)
        elif self.attachments:
            self._clear_final_layout()
            self._add_attachment_widgets()
            self.final_content.show()
            self.final_label.hide()
        else:
            self.final_label.hide()
        self.apply_theme()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "process_header", None) and event.type() == QEvent.Type.MouseButtonPress:
            self.toggle_steps()
            return True
        if obj is self.final_label and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            QTimer.singleShot(0, self._update_user_text_fade_mask)
        return super().eventFilter(obj, event)

    def _link_color(self):
        if CURRENT_THEME == "light":
            return "#006DCC"
        if self.is_user:
            return BUBBLE_USER_TEXT
        return ACCENT_PINK_COLOR

    def _apply_link_palette(self, label):
        link_color = QColor(self._link_color())
        palette = label.palette()
        palette.setColor(QPalette.ColorRole.Link, link_color)
        palette.setColor(QPalette.ColorRole.LinkVisited, link_color)
        label.setPalette(palette)

    def apply_theme(self):
        if self.is_background_task and self.is_user:
            if not hasattr(self, "badge_label"):
                self.badge_label = QLabel("⚡ משימת רקע")
                self.badge_label.setStyleSheet("color: #FF9F0A; font-weight: bold; font-size: 11px; margin-bottom: 4px;")
                self.main_layout.insertWidget(0, self.badge_label)
            self.main_layout.setContentsMargins(20, 16, 20, 16)
            bg = "rgba(255, 159, 10, 15)"
            color = TEXT_COLOR
            link_color = self._link_color()
            radius = "22px"
            border = "1px solid rgba(255, 159, 10, 70)"
            margin = "5px 0px"
        else:
            if hasattr(self, "badge_label"):
                try:
                    self.badge_label.deleteLater()
                except Exception:
                    pass
                delattr(self, "badge_label")
            if self.is_user:
                self.main_layout.setContentsMargins(20, 16, 20, 16)
            else:
                self.main_layout.setContentsMargins(10, 8, 10, 8)
            bg = USER_BUBBLE_COLOR if self.is_user else "transparent"
            color = BUBBLE_USER_TEXT if self.is_user else TEXT_COLOR
            link_color = self._link_color()
            radius = "22px" if self.is_user else "0px"
            border = f"1px solid {USER_BUBBLE_BORDER}" if self.is_user else "none"
            margin = "5px 0px" if self.is_user else "2px 0px"

        self.process_header.setStyleSheet("background: transparent; border: none;")
        self.process_arrow_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; background: transparent;")
        self.toggle_btn.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 15px; background: transparent; padding: 0px;")
        self.steps_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 15px; background: transparent;")
        self.initial_thinking_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 15px; background: transparent;")
        for group in getattr(self, "agent_process_groups", []):
            group.apply_theme()
        for label in self.findChildren(QLabel):
            self._apply_link_palette(label)
        self.setStyleSheet(
            f"MessageBubble {{ background: {bg}; border: {border}; border-radius: {radius}; margin: {margin}; }}"
            f"QLabel {{ color: {color}; font-size: 15px; font-family: {ui_font_family_css()}; background: transparent; }}"
            f"a {{ color: {link_color}; text-decoration: underline; font-weight: 700; }}"
            f"code {{ background-color: {CODE_BG_COLOR}; padding: 2px 4px; border-radius: 4px; font-family: Consolas; }}"
            f"pre {{ background-color: {CODE_BG_COLOR}; padding: 12px; border-radius: 14px; margin: 0; }}"
            f"p {{ margin: 0 0 5px 0; }}"
        )
        self._set_process_header_icon()
        for block in self.findChildren(CodeBlockWidget):
            block.apply_theme()
        for tile in self.findChildren(AttachmentTile):
            tile.apply_theme()
        for button in getattr(self, "_canvas_buttons", []):
            button.setStyleSheet(self._canvas_button_stylesheet())
            button.ensurePolished()
            button.setFixedHeight(button.heightForWidth(button.width() or self.max_w))
        self._apply_user_message_collapse_state()
        if self.is_user:
            apply_soft_shadow(self, blur=22, y=7, alpha=30)
        else:
            self.setGraphicsEffect(None)

    def update_parent_width(self, parent_width):
        if self.is_user:
            self.max_w = max(220, int(parent_width * 0.76) - 30)
        else:
            self.max_w = max(240, int(parent_width or 450) - 52)
        self.process_header.setMaximumWidth(self.max_w)
        self._fit_process_header_label_width()
        self.steps_label.setMaximumWidth(self.max_w)
        self.initial_thinking_label.setMaximumWidth(self.max_w)
        self.final_label.setMaximumWidth(self.max_w)
        for label in getattr(self, "agent_report_labels", []):
            label.setMaximumWidth(self.max_w)
        for group in getattr(self, "agent_process_groups", []):
            group.update_parent_width(self.max_w)
        self._update_user_message_collapse_state()
        for block in self.findChildren(CodeBlockWidget):
            block.update_parent_width(self.max_w)
        for tile in self.findChildren(AttachmentTile):
            tile.setMaximumWidth(self.max_w)
        for button in getattr(self, "_canvas_buttons", []):
            button.setFixedWidth(self.max_w)
            button.ensurePolished()
            button.setFixedHeight(button.heightForWidth(self.max_w))
        self._apply_agent_process_width_lock()
        self._refresh_layout()

    def _fit_process_header_label_width(self):
        if not hasattr(self, "toggle_btn"):
            return
        available = max(120, self.max_w - 20)
        text = str(self.toggle_btn.text() or "")
        width = _fitted_plain_label_width(self.toggle_btn, text, available, min_width=42, padding=8)
        self.toggle_btn.setWordWrap(width >= available)
        self.toggle_btn.setMinimumWidth(width)
        self.toggle_btn.setMaximumWidth(width)

    def _refresh_layout(self):
        self.updateGeometry()
        parent = self.parentWidget()
        if parent:
            parent.updateGeometry()

    def _handle_link_activated(self, href):
        href = str(href or "")
        if href.startswith("smarti-copy-code:"):
            try:
                index = int(href.split(":", 1)[1])
                QApplication.clipboard().setText(self.code_blocks[index])
            except Exception as e:
                logging.warning(f"Copy code block failed: {e}")
            return
        href = _normalize_href(href)
        local_path = _local_path_from_href(href)
        if local_path:
            if not _open_local_link_path(local_path):
                QMessageBox.warning(self, "Local link unavailable", f"Could not open:\n{local_path}")
            return
        if _is_valid_display_href(href):
            webbrowser.open(href)

    def _clear_final_layout(self):
        while self.final_layout.count():
            item = self.final_layout.takeAt(0)
            widget = item.widget()
            if widget:
                self.final_layout.removeWidget(widget)
                if widget is not self.final_label:
                    widget.setParent(None)
                    widget.deleteLater()
                else:
                    widget.setParent(self)

    def _user_collapsed_label_height(self):
        metrics = QFontMetrics(self.final_label.font())
        return max(1, metrics.lineSpacing() * self.USER_COLLAPSED_LINES + 6)

    def _user_text_fade_height(self):
        metrics = QFontMetrics(self.final_label.font())
        return min(self._user_collapsed_label_height(), max(40, metrics.lineSpacing() * 2 + 12))

    def _clear_user_text_fade_mask(self):
        if self._final_label_fade_effect is not None and self.final_label.graphicsEffect() is self._final_label_fade_effect:
            self.final_label.setGraphicsEffect(None)
        self._final_label_fade_effect = None

    def _update_user_text_fade_mask(self):
        show_fade = (
            self.is_user
            and self._user_message_collapsible
            and self._user_message_collapsed
            and self.final_label.isVisible()
        )
        if not show_fade:
            self._clear_user_text_fade_mask()
            return
        label_height = max(1, self.final_label.height() or self._user_collapsed_label_height())
        fade_height = min(label_height, self._user_text_fade_height())
        fade_start = max(0.0, min(0.92, (label_height - fade_height) / label_height))
        fade_mid = fade_start + ((1.0 - fade_start) * 0.58)

        opaque = QColor(0, 0, 0, 255)
        soft = QColor(0, 0, 0, 150)
        faint = QColor(0, 0, 0, 36)
        gradient = QLinearGradient(0, 0, 0, label_height)
        gradient.setColorAt(0.0, opaque)
        gradient.setColorAt(fade_start, opaque)
        gradient.setColorAt(fade_mid, soft)
        gradient.setColorAt(1.0, faint)

        effect = self._final_label_fade_effect
        if effect is None or self.final_label.graphicsEffect() is not effect:
            effect = QGraphicsOpacityEffect(self.final_label)
            effect.setOpacity(1.0)
            self._final_label_fade_effect = effect
            self.final_label.setGraphicsEffect(effect)
        effect.setOpacityMask(QBrush(gradient))

    def _final_label_natural_height(self):
        label_text = str(self.final_label.text() or "").strip()
        if not label_text:
            return 0
        try:
            doc = QTextDocument()
            doc.setDefaultFont(self.final_label.font())
            doc.setTextWidth(max(1, self.max_w))
            doc.setHtml(label_text if label_text.lstrip().startswith("<") else f"<span>{label_text}</span>")
            height = doc.size().height()
            if height and height > 0:
                return int(height + 0.5)
        except Exception:
            pass
        try:
            height = self.final_label.heightForWidth(max(1, self.max_w))
            if height and height > 0:
                return int(height)
        except Exception:
            pass
        return int(self.final_label.sizeHint().height())

    def _should_collapse_user_message(self):
        if not self.is_user or not str(self.final_label.text() or "").strip():
            return False
        if not str(self.copy_text or "").strip():
            return False
        if len(str(self.copy_text).splitlines()) > self.USER_COLLAPSED_LINES:
            return True
        return self._final_label_natural_height() > self._user_collapsed_label_height() + 2

    def _apply_user_message_collapse_state(self):
        if not self._user_message_collapsible:
            self.final_label.setMaximumHeight(self.WIDGET_MAX_HEIGHT)
            self._update_user_text_fade_mask()
            self.user_collapse_changed.emit(False, True)
            return
        self.final_label.setMaximumHeight(
            self._user_collapsed_label_height()
            if self._user_message_collapsed else self.WIDGET_MAX_HEIGHT
        )
        self._update_user_text_fade_mask()
        self.user_collapse_changed.emit(True, self._user_message_collapsed)
        QTimer.singleShot(0, self._update_user_text_fade_mask)

    def user_collapse_state(self):
        return self._user_message_collapsible, self._user_message_collapsed

    def _update_user_message_collapse_state(self):
        collapsible = self._should_collapse_user_message()
        if collapsible and not self._user_message_collapsible:
            self._user_message_collapsed = True
        elif not collapsible:
            self._user_message_collapsed = True
        self._user_message_collapsible = collapsible
        self._apply_user_message_collapse_state()
        self._refresh_layout()

    def toggle_user_message_collapse(self):
        if not self._user_message_collapsible:
            return
        self._user_message_collapsed = not self._user_message_collapsed
        self._apply_user_message_collapse_state()
        self._refresh_layout()

    def _add_attachment_widgets(self):
        for item in self.attachments:
            tile = AttachmentTile(item, removable=False, compact=False)
            tile.setMaximumWidth(self.max_w)
            self.final_layout.addWidget(tile)

    def _canvas_button_stylesheet(self):
        border = ACCENT_PINK_COLOR if CURRENT_THEME == "dark" else ACCENT_COLOR
        return (
            f"QPushButton {{ background: {ACCENT_TINT}; color: {TEXT_COLOR}; border: 1px solid {border}; "
            f"border-radius: 17px; padding: 9px 16px; font-size: 14px; font-weight: 800; text-align: center; }}"
            f"QPushButton:hover {{ background: {ACCENT_TINT_STRONG}; border-color: {ACCENT_COLOR}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_COLOR}; color: {ACCENT_TEXT_COLOR}; }}"
        )

    def _add_canvas_buttons(self):
        for button in self._canvas_buttons:
            try:
                self.final_layout.removeWidget(button)
                button.setParent(None)
                button.deleteLater()
            except RuntimeError:
                pass
        self._canvas_buttons = []
        if self.is_user:
            return
        for artifact in self.canvas_artifacts:
            if artifact.get("closed"):
                continue
            button = CanvasOpenButton(f"פתח קנבס  •  {artifact.get('title', 'קנבס של סמארטי')}")
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            button.setStyleSheet(self._canvas_button_stylesheet())
            button.ensurePolished()
            button.setFixedWidth(self.max_w)
            button.setFixedHeight(button.heightForWidth(self.max_w))
            button.setToolTip("פתיחת הקנבס לצד השיחה")
            button.clicked.connect(lambda checked=False, item=copy.deepcopy(artifact): self.canvas_open_requested.emit(item))
            self.final_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignRight)
            self._canvas_buttons.append(button)

    def set_canvas_artifacts(self, canvases):
        self.canvas_artifacts = [artifact for item in (canvases or []) if (artifact := normalize_canvas_artifact(item))]
        if self.final_content.isVisible():
            self._add_canvas_buttons()
            self._refresh_layout()

    def _render_markdown_segment(self, segment):
        text = str(segment or "").strip("\n")
        return _render_markdown_html(text, self._link_color(), self.is_user, style_blocks=True)

    def _new_text_label(self, rendered_html):
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction | Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self._handle_link_activated)
        label.setMaximumWidth(self.max_w)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self._apply_link_palette(label)
        if not str(rendered_html or "").lstrip().startswith("<"):
            rendered_html = f"<span>{rendered_html}</span>"
        label.setText(rendered_html)
        return label

    def _technical_details_html(self, details):
        safe_details = _escape_with_soft_breaks(details)
        font_style = "normal" if app_uses_asset_font() else "italic"
        return (
            f'<div dir="rtl" align="right" style="color:{MUTED_TEXT_COLOR}; '
            f'font-size:12px; font-style:{font_style}; line-height:1.35; '
            'margin-top:8px; padding-top:2px;">'
            f'{safe_details}</div>'
        )

    def _format_agent_duration(self, seconds):
        seconds = max(0, int(seconds or 0))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            hour_label = "שעה" if hours == 1 else "שעות"
            return f"{hours} {hour_label} {minutes:02d} דק' {secs:02d} שנ'"
        if minutes:
            return f"{minutes} דק' {secs:02d} שנ'"
        return f"{secs} שנ'"

    def _set_process_header_icon(self):
        if not hasattr(self, "process_arrow_label"):
            return
        icon = _rotated_themed_icon(self.PROCESS_CHEVRON_ICON_NAMES, -90 if self.is_expanded else 0, 16)
        if icon.isNull():
            icon = _transparent_icon(16)
        self.process_arrow_label.setPixmap(icon.pixmap(16, 16))
        self.process_arrow_label.setText("")

    def _update_agent_process_header(self):
        if not self.agent_process_started:
            return
        prefix = "סמארטי עבד" if self.agent_process_finalized else "סמארטי עובד"
        self.toggle_btn.setText(f"{prefix} {self._format_agent_duration(self.agent_process_elapsed_seconds)}")
        self._fit_process_header_label_width()
        self._set_process_header_icon()

    def _apply_agent_process_width_lock(self):
        if self.is_user:
            return
        if self.agent_process_started:
            target = max(260, int(self.max_w) + 20)
            self.setMinimumWidth(target)
            self.setMaximumWidth(target)

    def _update_agent_process_timer(self):
        if not self.agent_process_started:
            return
        if not self.agent_process_finalized:
            self.agent_process_elapsed_seconds = int(time.time() - self.agent_process_start_time)
        self._update_agent_process_header()

    def _ensure_agent_process_started(self):
        if self.agent_process_started:
            return
        self.hide_initial_thinking()
        self.agent_process_started = True
        self.agent_process_finalized = False
        self.agent_process_start_time = time.time()
        self.agent_process_elapsed_seconds = 0
        self.is_expanded = True
        self.process_header.show()
        self.process_details.show()
        self.steps_container.show()
        self.agent_process_timer.start()
        self._apply_agent_process_width_lock()
        self._update_agent_process_header()

    def _hide_current_process_thinking(self):
        if self.current_process_group:
            self.current_process_group.hide_thinking()

    def _new_agent_process_group(self):
        group = AgentToolGroupWidget(self.max_w)
        self.agent_process_groups.append(group)
        self.process_details_layout.addWidget(group)
        self.current_process_group = group
        group.apply_theme()
        return group

    def _current_or_new_process_group(self):
        self._ensure_agent_process_started()
        if self.current_process_group is None:
            return self._new_agent_process_group()
        return self.current_process_group

    def show_initial_thinking(self):
        """Show the delayed waiting state before a direct model response arrives."""
        if self.is_user or self.agent_process_started or self.copy_text or self.final_layout.count():
            return False
        self.initial_thinking_label.setText("חושב...")
        self.initial_thinking_label.show()
        self.initial_thinking_label.start_shimmer()
        self.steps_container.show()
        self._refresh_layout()
        return True

    def hide_initial_thinking(self):
        self.initial_thinking_label.stop_shimmer()
        self.initial_thinking_label.hide()
        if not self.agent_process_started:
            self.steps_container.hide()

    def add_agent_report(self, text):
        display_text = _repair_markdown_links(html.unescape(str(text or ""))).strip()
        if not display_text:
            return
        self._ensure_agent_process_started()
        self._hide_current_process_thinking()
        rendered_html = self._render_markdown_segment(display_text)
        label = self._new_text_label(rendered_html)
        label.setMaximumWidth(self.max_w)
        self.agent_report_labels.append(label)
        self.process_copy_text_parts.append(display_text)
        self.process_details_layout.addWidget(label)
        self._new_agent_process_group()
        self.steps_text_html = "\n".join(self.process_copy_text_parts)
        self._refresh_layout()

    def handle_agent_event(self, event):
        if isinstance(event, str):
            self.add_agent_report(event)
            return bool(str(event or "").strip())
        if not isinstance(event, dict):
            return False
        event_type = str(event.get("type") or "").strip()
        if event_type == "report":
            before = len(self.agent_report_labels)
            self.add_agent_report(event.get("text", ""))
            return len(self.agent_report_labels) > before
        elif event_type == "thinking":
            if self.agent_process_started and self.current_process_group:
                self.current_process_group.show_thinking()
                self._refresh_layout()
                # This is a transient spinner update, not new user-visible
                # process content. Do not make it trigger chat auto-scroll.
                return False
        elif event_type == "tool_start":
            group = self._current_or_new_process_group()
            group.start_tools(event.get("tools") or [], parallel=bool(event.get("parallel")))
            self.steps_text_html = "\n".join(self.process_copy_text_parts) or "agent process"
            self._refresh_layout()
            return True
        elif event_type == "tool_finish":
            group = self._current_or_new_process_group()
            group.finish_tools(event.get("results") or [])
            self._refresh_layout()
            return True
        return False

    def finalize_agent_process(self):
        if not self.agent_process_started:
            return
        self.agent_process_finalized = True
        self.agent_process_elapsed_seconds = int(time.time() - self.agent_process_start_time)
        self.agent_process_timer.stop()
        if self.current_process_group:
            self.current_process_group.hide_thinking()
        self.collapse_steps()

    def restore_agent_process(self, process_data):
        if not isinstance(process_data, dict):
            return
        events = process_data.get("events", [])
        if not isinstance(events, list) or not events:
            return
        for event in events:
            self.handle_agent_event(event)
        try:
            elapsed = int(process_data.get("elapsed_seconds", self.agent_process_elapsed_seconds) or 0)
        except Exception:
            elapsed = self.agent_process_elapsed_seconds
        self.agent_process_elapsed_seconds = max(0, elapsed)
        self.agent_process_finalized = True
        self.agent_process_timer.stop()
        if self.current_process_group:
            self.current_process_group.hide_thinking()
        self.collapse_steps()
        self._apply_agent_process_width_lock()

    def add_step(self, step_text):
        self.add_agent_report(_clean_step_for_display(str(step_text or "").replace('\n', ' ')))
            
    def set_final_text(self, final_text):
        self.hide_initial_thinking()
        if not final_text: return
        display_text = _repair_markdown_links(html.unescape(str(final_text)))
        render_text, technical_details = _split_technical_details(display_text)
        self.copy_text = display_text
        self.code_blocks = []
        self.finalize_agent_process()
        self.stop_steps_shimmer()
        self._clear_final_layout()
        self.final_content.show()
        self._add_attachment_widgets()
        parts = _split_markdown_code_blocks(render_text)
        has_code = any(kind == "code" for kind, _, _ in parts)
        if not has_code:
            rendered_html = self._render_markdown_segment(render_text)
            if technical_details:
                rendered_html = f"{rendered_html}{self._technical_details_html(technical_details)}"
            self.final_label.setMaximumWidth(self.max_w)
            self.final_label.setMaximumHeight(self.WIDGET_MAX_HEIGHT)
            self.final_label.setText(rendered_html if rendered_html.lstrip().startswith("<") else f"<span>{rendered_html}</span>")
            self.final_layout.addWidget(self.final_label)
            self.final_label.show()
            self._update_user_message_collapse_state()
            QTimer.singleShot(0, self._update_user_message_collapse_state)
        else:
            self.final_label.hide()
            self.final_label.setMaximumHeight(self.WIDGET_MAX_HEIGHT)
            self._user_message_collapsible = False
            self._user_message_collapsed = True
            self._update_user_text_fade_mask()
            self.user_collapse_changed.emit(False, True)
            for kind, content, language in parts:
                if kind == "code":
                    self.code_blocks.append(content)
                    self.final_layout.addWidget(CodeBlockWidget(content, language, self.max_w))
                else:
                    rendered_html = self._render_markdown_segment(content)
                    if rendered_html.strip():
                        self.final_layout.addWidget(self._new_text_label(rendered_html))
            if technical_details:
                self.final_layout.addWidget(self._new_text_label(self._technical_details_html(technical_details)))
        self._add_canvas_buttons()
        if self.steps_text_html: self.collapse_steps()
        self._refresh_layout()

    def toggle_steps(self):
        if not self.agent_process_started:
            return
        self.is_expanded = not self.is_expanded
        self.process_details.setVisible(self.is_expanded)
        self._update_agent_process_header()
        self._refresh_layout()

    def collapse_steps(self):
        if not self.agent_process_started:
            return
        self.is_expanded = False
        for group in getattr(self, "agent_process_groups", []):
            group.collapse_details()
        self.process_details.hide()
        self._update_agent_process_header()
        self._refresh_layout()

    def start_steps_shimmer(self):
        if self.current_process_group:
            self.current_process_group.show_thinking()

    def stop_steps_shimmer(self):
        for group in getattr(self, "agent_process_groups", []):
            group.status_label.stop_shimmer()
            group.thinking_label.stop_shimmer()

    def plain_text(self):
        attachment_text = attachment_manifest_text(self.attachments)
        process_text = "\n".join(getattr(self, "process_copy_text_parts", []) or [])
        final_text = self.copy_text or self.final_label.text() or self.steps_label.text()
        base = "\n\n".join(part for part in (process_text, final_text) if str(part or "").strip())
        return (str(base or "") + ("\n\n" + attachment_text if attachment_text else "")).strip()

    def final_plain_text(self):
        attachment_text = attachment_manifest_text(self.attachments)
        final_text = self.copy_text or self.final_label.text()
        return (str(final_text or "") + ("\n\n" + attachment_text if attachment_text else "")).strip()

class ChatMessageContainer(QWidget):
    tts_button_clicked = pyqtSignal(object)
    canvas_open_requested = pyqtSignal(object)

    ACTION_BUTTON_SIZE = 36
    ACTION_ICON_SIZE = 22
    ACTION_ROW_HEIGHT = 40

    def __init__(self, text, is_user=False, parent_width=450, show_actions=True, attachments=None, canvases=None, is_background_task=False, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("background: transparent;")
        self.bubble = MessageBubble(text, is_user, parent_width, attachments=attachments, canvases=canvases, is_background_task=is_background_task)
        self.is_user = is_user
        self.show_actions = bool(show_actions)
        self._tts_active = False
        self._tts_blocked = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.content_wrap = QWidget()
        self.content_wrap.setStyleSheet("background: transparent;")
        self.content_wrap.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.content_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.content_wrap)

        layout = QVBoxLayout(self.content_wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)
        bubble_row.setDirection(QBoxLayout.Direction.LeftToRight)
        if is_user:
            bubble_row.addWidget(self.bubble, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute)
            bubble_row.addStretch()
        else:
            bubble_row.addWidget(self.bubble, 1)
        layout.addLayout(bubble_row)

        self.actions_container = QWidget()
        self.actions_container.setMouseTracking(True)
        self.actions_container.setFixedHeight(self.ACTION_ROW_HEIGHT)
        self.actions_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.actions_container.setStyleSheet("background: transparent;")
        actions_layout = QHBoxLayout(self.actions_container)
        actions_layout.setContentsMargins(12, 0, 12, 0)
        actions_layout.setSpacing(6)

        self.copy_btn = None
        if self.show_actions:
            self.copy_btn = QPushButton()
            self.copy_btn.setFixedSize(self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE)
            self.copy_btn.setToolTip("העתק")
            self.copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            set_themed_button_icon(self.copy_btn, ("copy_icon",), "⧉", self.ACTION_ICON_SIZE, clear_text=True)
            self.copy_btn.clicked.connect(self.copy_message_text)

        self.user_collapse_btn = None
        if self.show_actions and is_user:
            self.user_collapse_btn = QPushButton()
            self.user_collapse_btn.setFixedSize(self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE)
            self.user_collapse_btn.setToolTip("הרחב הודעה")
            self.user_collapse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.user_collapse_btn.clicked.connect(self.toggle_user_message_collapse)
            self.user_collapse_btn.hide()

        self.tts_btn = None
        if self.show_actions and not is_user:
            self.tts_btn = QPushButton()
            self.tts_btn.setFixedSize(self.ACTION_BUTTON_SIZE, self.ACTION_BUTTON_SIZE)
            self.tts_btn.setToolTip("Read aloud")
            self.tts_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.tts_btn.clicked.connect(lambda checked=False: self.tts_button_clicked.emit(self))

        if not self.show_actions:
            self.actions_container.setFixedHeight(0)
            self.actions_container.hide()
        elif is_user:
            actions_layout.addWidget(self.copy_btn)
            actions_layout.addWidget(self.user_collapse_btn)
            actions_layout.addStretch()
        else:
            actions_layout.addStretch()
            actions_layout.addWidget(self.copy_btn)
            actions_layout.addWidget(self.tts_btn)

        self.actions_opacity = QGraphicsOpacityEffect(self.actions_container)
        self.actions_opacity.setOpacity(0.0 if self.show_actions else 1.0)
        self.actions_container.setGraphicsEffect(self.actions_opacity)
        layout.addWidget(self.actions_container)

        self.opacity_anim = QPropertyAnimation(self.actions_opacity, b"opacity", self)
        self.opacity_anim.setDuration(240)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._actions_can_show = not self.show_actions
        self._entry_started = False
        self._entry_pending = False
        self._enter_opacity = None
        self._enter_anim = None
        self._enter_slide_anim = None
        self.bubble.user_collapse_changed.connect(self.update_user_collapse_button_state)
        self.bubble.canvas_open_requested.connect(lambda artifact: self.canvas_open_requested.emit(artifact))
        self.apply_theme()
        self.update_user_collapse_button_state(*self.bubble.user_collapse_state())

    def _button_css(self, active=False):
        color = DANGER_COLOR if active else MUTED_TEXT_COLOR
        hover = "rgba(240,90,110,0.16)" if active else ACCENT_TINT
        pressed = "rgba(240,90,110,0.24)" if active else ACCENT_TINT_STRONG
        radius = max(1, int(self.ACTION_BUTTON_SIZE / 2))
        return (
            f"QPushButton {{ background: transparent; color: {color}; border: none; "
            f"padding: 0px; border-radius: {radius}px; font-size: 15px; font-weight: 700; outline: none; }}"
            f"QPushButton:hover {{ background: {hover}; color: {TEXT_COLOR}; }}"
            f"QPushButton:pressed {{ background: {pressed}; }}"
            f"QPushButton:disabled {{ background: transparent; color: {SUBTLE_TEXT_COLOR}; }}"
        )

    def apply_theme(self):
        self.setStyleSheet("background: transparent;")
        self.actions_container.setStyleSheet("background: transparent;")
        if self.copy_btn:
            refresh_themed_button_icon(self.copy_btn)
            self.copy_btn.setStyleSheet(self._button_css(False))
        if self.user_collapse_btn:
            self.user_collapse_btn.setStyleSheet(self._button_css(False))
            self.update_user_collapse_button_state(*self.bubble.user_collapse_state())
        self.update_tts_button_state(self._tts_active, self._tts_blocked)
        if hasattr(self, "bubble") and self.bubble:
            self.bubble.apply_theme()

    def _set_user_collapse_button_icon(self, collapsed=None):
        if not self.user_collapse_btn:
            return
        if collapsed is None:
            _, collapsed = self.bubble.user_collapse_state()
        icon_size = self.ACTION_ICON_SIZE
        icon_names = (
            "message_collapse_arrow_icon",
            "message_collapse_arrow",
            "collapse_arrow_icon",
            "collapse_arrow",
            "dropdown",
        )
        icon = _rotated_themed_icon(icon_names, 0 if collapsed else 180, icon_size)
        self.user_collapse_btn.setIcon(icon if not icon.isNull() else _transparent_icon(icon_size))
        self.user_collapse_btn.setIconSize(QSize(icon_size, icon_size))
        self.user_collapse_btn.setText("")

    def update_user_collapse_button_state(self, collapsible=None, collapsed=None):
        if not self.user_collapse_btn:
            return
        if collapsible is None or collapsed is None:
            collapsible, collapsed = self.bubble.user_collapse_state()
        collapsible = bool(collapsible)
        collapsed = bool(collapsed)
        self.user_collapse_btn.setVisible(collapsible)
        self.user_collapse_btn.setEnabled(collapsible)
        self.user_collapse_btn.setToolTip("הרחב הודעה" if collapsed else "כווץ הודעה")
        self._set_user_collapse_button_icon(collapsed)

    def update_tts_button_state(self, active=False, blocked=False):
        if not self.tts_btn:
            return
        self._tts_active = bool(active)
        self._tts_blocked = bool(blocked)
        self.tts_btn.setEnabled(not blocked or active)
        icon_names = (
            ("stop_reading_icon", "stop_audio_icon", "stop_icon")
            if active else
            ("read_aloud_icon", "speaker_icon", "tts_icon")
        )
        set_themed_button_icon(self.tts_btn, icon_names, "X" if active else "A", self.ACTION_ICON_SIZE, clear_text=True)
        self.tts_btn.setToolTip("Stop reading" if active else "Read aloud")
        self.tts_btn.setStyleSheet(self._button_css(active))

    def start_entry_animation(self):
        self._entry_pending = False
        if self._entry_started or not self.isVisible():
            return
        self._entry_started = True
        if self.show_actions:
            self._actions_can_show = False
            self.actions_opacity.setOpacity(0.0)

        self._enter_opacity = QGraphicsOpacityEffect(self.content_wrap)
        self._enter_opacity.setOpacity(0.0)
        self.content_wrap.setGraphicsEffect(self._enter_opacity)

        self._enter_anim = QPropertyAnimation(self._enter_opacity, b"opacity", self)
        self._enter_anim.setDuration(360)
        self._enter_anim.setStartValue(0.0)
        self._enter_anim.setEndValue(1.0)
        self._enter_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def cleanup():
            self.content_wrap.setGraphicsEffect(None)
            self._actions_can_show = True
            if self.show_actions:
                self.actions_opacity.setOpacity(1.0)
            self.updateGeometry()

        self._enter_anim.finished.connect(cleanup)
        self._enter_anim.start()

    def finish_entry_without_animation(self):
        self._entry_pending = False
        self._entry_started = True
        self.content_wrap.setGraphicsEffect(None)
        self._actions_can_show = True
        if self.show_actions:
            self.actions_opacity.setOpacity(1.0)
        self.updateGeometry()

    def reveal_with_entry_animation(self):
        self.show()
        if self._entry_started or self._entry_pending:
            return
        self._entry_pending = True
        QTimer.singleShot(0, self.start_entry_animation)

    def enterEvent(self, event):
        self._set_actions_visible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_actions_visible(True)
        super().leaveEvent(event)

    def _set_actions_visible(self, visible):
        if not self.show_actions:
            return
        self.opacity_anim.stop()
        self.actions_opacity.setOpacity(1.0 if self._actions_can_show else 0.0)

    def copy_message_text(self):
        if not self.copy_btn:
            return
        text = self.bubble.plain_text() if self.is_user else self.bubble.final_plain_text()
        QApplication.clipboard().setText(text)

    def toggle_user_message_collapse(self):
        if self.user_collapse_btn:
            self.bubble.toggle_user_message_collapse()

# Disabled fallback prototype for a custom PyQt quick-reply popup.
# Smarti no longer instantiates or shows this widget; it is kept as a reference
# in case we ever want an app-drawn notification instead of native Windows input.
class QuickReplyToast(QWidget):
    reply_submitted = pyqtSignal(str)

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedWidth(390)
        self.setStyleSheet(f"""
            QWidget {{
                background: {GLASS_STRONG_COLOR};
                color: {TEXT_COLOR};
                font-family: {ui_font_family_css()};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 22px;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
            QLineEdit {{
                background: {GLASS_COLOR};
                color: {FIELD_TEXT_COLOR};
                border: 1px solid {SOFT_LINE_COLOR};
                border-radius: 18px;
                padding: 10px 12px;
                font-size: 13px;
                selection-background-color: {ACCENT_TINT_STRONG};
                selection-color: {TEXT_COLOR};
            }}
            QLineEdit:focus {{
                border-color: {ACCENT_PINK_COLOR};
                background: {FIELD_HOVER_COLOR};
            }}
            QPushButton {{
                background: transparent;
                color: {ACCENT_COLOR};
                border: 1px solid transparent;
                border-radius: 18px;
                padding: 9px 14px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {ACCENT_TINT};
                border-color: {SOFT_LINE_COLOR};
            }}
            QPushButton#CloseToast {{
                border: none;
                padding: 0;
                font-size: 18px;
                color: {MUTED_TEXT_COLOR};
            }}
            QPushButton#CloseToast:hover {{
                background: {ACCENT_TINT};
                color: {TEXT_COLOR};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel(SMARTI_APP_DISPLAY_NAME)
        title.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 13px; font-weight: 700;")
        title.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        close_btn = QPushButton("×")
        close_btn.setObjectName("CloseToast")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self.hide)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(close_btn)
        layout.addLayout(header)

        self.response_label = QLabel()
        self.response_label.setTextFormat(Qt.TextFormat.PlainText)
        self.response_label.setWordWrap(True)
        self.response_label.setMaximumHeight(112)
        self.response_label.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 13px; line-height: 1.35;")
        layout.addWidget(self.response_label)

        reply_row = QHBoxLayout()
        reply_row.setContentsMargins(0, 0, 0, 0)
        reply_row.setSpacing(8)
        self.reply_edit = QLineEdit()
        self.reply_edit.setPlaceholderText("תגובה לסמארטי")
        self.reply_edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.reply_edit.returnPressed.connect(self.submit_reply)
        self.send_btn = QPushButton("שלח")
        self.send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.send_btn.clicked.connect(self.submit_reply)
        reply_row.addWidget(self.reply_edit)
        reply_row.addWidget(self.send_btn)
        layout.addLayout(reply_row)

    def show_response(self, text):
        self.response_label.setText(str(text or "").strip())
        self.reply_edit.clear()
        self.adjustSize()
        self._move_to_notification_corner()
        self.show()
        self.raise_()

    def _move_to_notification_corner(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        margin = 18
        size = self.sizeHint()
        width = min(self.width(), max(300, available.width() - margin * 2))
        height = min(size.height(), max(160, available.height() - margin * 2))
        self.resize(width, height)
        self.move(
            available.right() - self.width() - margin,
            available.bottom() - self.height() - margin
        )

    def submit_reply(self):
        text = self.reply_edit.text().strip()
        if not text:
            return
        self.hide()
        self.reply_submitted.emit(text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

class ClickableSessionFrame(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, session_id):
        super().__init__()
        self.session_id = session_id
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.session_id)
        super().mouseReleaseEvent(event)

class EndElideLabel(QLabel):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text):
        self._full_text = str(text or "")
        self._apply_elide()

    def fullText(self):
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self):
        full_text = getattr(self, "_full_text", "")
        width = max(0, self.contentsRect().width())
        if not full_text or width <= 0:
            QLabel.setText(self, full_text)
            self.setToolTip("")
            return
        metrics = QFontMetrics(self.font())
        if metrics.horizontalAdvance(full_text) <= width:
            QLabel.setText(self, full_text)
            self.setToolTip("")
            return
        suffix = "..."
        if metrics.horizontalAdvance(suffix) >= width:
            QLabel.setText(self, suffix)
            self.setToolTip(full_text)
            return
        low, high = 0, len(full_text)
        while low < high:
            mid = (low + high + 1) // 2
            candidate = full_text[:mid].rstrip() + suffix
            if metrics.horizontalAdvance(candidate) <= width:
                low = mid
            else:
                high = mid - 1
        QLabel.setText(self, full_text[:low].rstrip() + suffix)
        self.setToolTip(full_text)

class ChatHistoryPage(QWidget):
    def __init__(self, core, main_window):
        super().__init__(getattr(main_window, "stacked_widget", None))
        self.core = core
        self.main_window = main_window
        self._open_session_menu = None
        self._open_session_menu_button = None
        self._suppress_session_menu_button = None
        self.search_icon_label = None
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        self.back_btn = QPushButton()
        back_btn = self.back_btn
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        back_btn.setToolTip("חזרה לצ'אט")
        refresh_back_button_icon(back_btn)
        back_btn.clicked.connect(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page))
        top_bar.addWidget(back_btn)

        title = QLabel("שיחות")
        title.setStyleSheet(page_title_css(19))
        top_bar.addWidget(title)
        top_bar.addStretch()

        self.new_chat_btn = QPushButton("שיחה חדשה")
        self.new_chat_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.new_chat_btn.setStyleSheet(PRIMARY_BUTTON_CSS)
        self.new_chat_btn.clicked.connect(self.start_new_chat)
        top_bar.addWidget(self.new_chat_btn)
        layout.addLayout(top_bar)

        self.search_frame = QFrame()
        self.search_frame.setObjectName("HistorySearchFrame")
        self.search_frame.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.search_frame.setStyleSheet(self._search_frame_stylesheet())
        search_layout = QHBoxLayout(self.search_frame)
        search_layout.setContentsMargins(14, 0, 12, 0)
        search_layout.setSpacing(8)

        self.search_icon_label = QLabel()
        self.search_icon_label.setFixedSize(30, 30)
        self.search_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        search_layout.addWidget(self.search_icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.search_edit = QLineEdit()
        self._apply_search_edit_rtl()
        self.search_edit.setPlaceholderText("חיפוש לפי שם או תוכן")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(self._search_line_edit_stylesheet())
        self._refresh_search_icon()
        self.search_edit.textChanged.connect(self.load_sessions)
        search_layout.addWidget(self.search_edit, 1)
        layout.addWidget(self.search_frame)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 4, 0, 4)
        self.content_layout.setSpacing(10)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)

    def apply_theme(self):
        refresh_back_button_icon(self.back_btn)
        self.new_chat_btn.setStyleSheet(PRIMARY_BUTTON_CSS)
        self.search_frame.setStyleSheet(self._search_frame_stylesheet())
        self.search_edit.setStyleSheet(self._search_line_edit_stylesheet())
        self._apply_search_edit_rtl()
        self._refresh_search_icon()
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.load_sessions()

    def _apply_search_edit_rtl(self):
        if not hasattr(self, "search_edit") or self.search_edit is None:
            return
        self.search_edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.search_edit.setAlignment(
            Qt.AlignmentFlag.AlignRight |
            Qt.AlignmentFlag.AlignAbsolute |
            Qt.AlignmentFlag.AlignVCenter
        )
        self.search_edit.setCursorMoveStyle(Qt.CursorMoveStyle.VisualMoveStyle)

    def _search_frame_stylesheet(self):
        return f"""
            QFrame#HistorySearchFrame {{
                background: {GLASS_COLOR};
                border-radius: 20px;
                border: 1px solid {SOFT_LINE_COLOR};
            }}
            QFrame#HistorySearchFrame:hover {{
                background: {FIELD_HOVER_COLOR};
                border-color: {LINE_COLOR};
            }}
        """

    def _search_line_edit_stylesheet(self):
        return f"""
            QLineEdit {{
                background: transparent;
                color: {FIELD_TEXT_COLOR};
                border: none;
                padding: 13px 4px 13px 10px;
                font-size: 14px;
                selection-background-color: {ACCENT_TINT_STRONG};
                selection-color: {TEXT_COLOR};
            }}
        """

    def _refresh_search_icon(self):
        icon = themed_icon("search_icon", "search")
        if icon.isNull():
            if self.search_icon_label:
                self.search_icon_label.hide()
            return
        if self.search_icon_label:
            self.search_icon_label.setPixmap(icon.pixmap(26, 26))
            self.search_icon_label.show()

    def _format_time(self, value):
        try:
            dt = datetime.fromisoformat(str(value or ""))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(value or "")

    def _clear_rows(self):
        open_menu = self._open_session_menu
        self._open_session_menu = None
        self._open_session_menu_button = None
        if open_menu and open_menu.isVisible():
            open_menu.hide()
        if open_menu:
            open_menu.deleteLater()
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def load_sessions(self):
        self._clear_rows()
        query = self.search_edit.text().strip() if hasattr(self, "search_edit") else ""
        records = self.core.list_chat_sessions(query)
        if not records:
            empty = QLabel("לא נמצאו שיחות")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(muted_label_css(14) + " padding: 24px;")
            self.content_layout.addWidget(empty)
            self.content_layout.addStretch()
            return
        active_id = self.core.active_chat_session().get("id", "")
        for record in records:
            self.content_layout.addWidget(self._session_row(record, active_id))
        self.content_layout.addStretch()

    def _icon_button(self, tooltip, filenames, fallback_text="", danger=False):
        btn = QPushButton()
        btn.setFixedSize(30, 30)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip(tooltip)
        color = DANGER_COLOR if danger else ACCENT_COLOR
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {color}; "
            "padding: 0px; font-size: 17px; font-weight: 800; }}"
            "QPushButton:hover { background: transparent; border: none; }"
            "QPushButton:pressed { background: transparent; border: none; }"
        )
        set_themed_button_icon(btn, filenames, fallback_text, 18, clear_text=True)
        return btn

    def _compact_session_row(self, record, active_id):
        session_id = record.get("id")
        row = ClickableSessionFrame(session_id)
        row.clicked.connect(self.open_session)
        row.setMinimumWidth(0)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.setStyleSheet(card_css(4, 8))
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 7, 8, 7)
        row_layout.setSpacing(8)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title = EndElideLabel(record.get("title") or DEFAULT_CHAT_TITLE)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 800; border: none;")
        title_row.addWidget(title, 1)

        if record.get("id") == active_id:
            active = QLabel("פעילה")
            active.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            active.setStyleSheet(
                f"background: {GLASS_COLOR}; color: {ACCENT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
                "border-radius: 9px; padding: 2px 7px; font-size: 10px; font-weight: 800;"
            )
            title_row.addWidget(active)
        content_layout.addLayout(title_row)

        # Last-message preview is intentionally omitted to keep history rows compact.
        meta = QLabel(f"{self._format_time(record.get('updated_at'))} · {record.get('message_count', 0)} הודעות")
        meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        meta.setMinimumWidth(0)
        meta.setStyleSheet(f"color: {SUBTLE_TEXT_COLOR}; font-size: 11px; border: none;")
        content_layout.addWidget(meta)
        row_layout.addLayout(content_layout, 1)

        menu_btn = self._icon_button("פעולות", ("menu_icon",), fallback_text="⋮")
        menu_btn.setFixedSize(28, 28)
        menu_btn.pressed.connect(lambda rec=record, btn=menu_btn: self.show_session_menu(rec, btn))
        row_layout.addWidget(menu_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _add_session_menu_action(self, menu, text, icon_names, callback):
        action = menu.addAction(text)
        icon = themed_icon(*tuple(icon_names or ()))
        if not icon.isNull():
            action.setIcon(icon)
        action.triggered.connect(callback)
        return action

    def _clear_open_session_menu(self, menu):
        if self._open_session_menu is menu:
            self._open_session_menu = None
            self._open_session_menu_button = None
            menu.deleteLater()

    def _clear_session_menu_reopen_guard(self):
        self._suppress_session_menu_button = None

    def _session_menu_button_contains_cursor(self, button):
        return bool(button and button.rect().contains(button.mapFromGlobal(QCursor.pos())))

    def _on_session_menu_about_to_hide(self, menu):
        button = self._open_session_menu_button if self._open_session_menu is menu else None
        if self._session_menu_button_contains_cursor(button):
            self._suppress_session_menu_button = button
            QTimer.singleShot(220, self._clear_session_menu_reopen_guard)
        QTimer.singleShot(0, lambda m=menu: self._clear_open_session_menu(m))

    def show_session_menu(self, record, button):
        if self._suppress_session_menu_button is button:
            self._suppress_session_menu_button = None
            return
        current = self._open_session_menu
        if current and current.isVisible():
            if self._open_session_menu_button is button:
                self._open_session_menu = None
                self._open_session_menu_button = None
                current.hide()
                current.deleteLater()
                return
            self._open_session_menu = None
            self._open_session_menu_button = None
            current.hide()
            current.deleteLater()

        session_id = record.get("id")
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        if hasattr(menu, "setIconSize"):
            menu.setIconSize(QSize(20, 20))
        prepare_popup_menu(menu)
        self._add_session_menu_action(
            menu,
            "בטל הצמדה" if record.get("pinned") else "הצמד שיחה",
            ("unpin_icon",) if record.get("pinned") else ("pin_icon",),
            lambda checked=False, sid=session_id, pinned=not record.get("pinned"): self.set_pinned(sid, pinned),
        )
        self._add_session_menu_action(
            menu,
            "שנה שם",
            ("rename_icon",),
            lambda checked=False, sid=session_id, current_title=record.get("title", ""): self.rename_session(sid, current_title),
        )
        self._add_session_menu_action(
            menu,
            "יצוא JSON",
            ("export_json_icon", "export_icon"),
            lambda checked=False, sid=session_id, title=record.get("title", ""): self.export_session(sid, title),
        )
        menu.addSeparator()
        self._add_session_menu_action(
            menu,
            "מחק שיחה",
            ("delete_icon",),
            lambda checked=False, sid=session_id: self.delete_session(sid),
        )
        self._open_session_menu = menu
        self._open_session_menu_button = button
        menu.aboutToHide.connect(lambda m=menu: self._on_session_menu_about_to_hide(m))
        menu.popup(button.mapToGlobal(QPoint(0, button.height())))

    def _session_row(self, record, active_id):
        return self._compact_session_row(record, active_id)

    def start_new_chat(self):
        self.main_window.start_new_chat()
        self.load_sessions()

    def open_session(self, session_id):
        if self.main_window.agent_running:
            QMessageBox.information(self, "שיחה פעילה", "אי אפשר להחליף שיחה בזמן שסמארטי עדיין עובד.")
            return
        if self.core.activate_chat_session(session_id):
            self.main_window.load_active_chat_session()
            self.main_window.refresh_chat_title()
            self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page)

    def set_pinned(self, session_id, pinned):
        self.core.set_chat_session_pinned(session_id, pinned)
        self.load_sessions()

    def rename_session(self, session_id, current_title):
        title, ok = QInputDialog.getText(self, "שינוי שם שיחה", "שם חדש:", text=current_title or DEFAULT_CHAT_TITLE)
        if ok and title.strip():
            self.core.rename_chat_session(session_id, title.strip())
            if self.core.active_chat_session().get("id") == session_id:
                self.main_window.refresh_chat_title()
            self.load_sessions()

    def export_session(self, session_id, title):
        default_name = safe_filename(title or "smarti_chat", "smarti_chat") + ".json"
        default_path = os.path.join(OUTPUTS_DIR, default_name)
        path, _ = QFileDialog.getSaveFileName(self, "יצוא שיחה ל-JSON", default_path, "JSON (*.json)")
        if not path:
            return
        try:
            self.core.export_chat_session(session_id, path)
            QMessageBox.information(self, "היצוא הושלם", f"השיחה יוצאה אל:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "שגיאת יצוא", str(e))

    def delete_session(self, session_id):
        if self.main_window.agent_running and self.core.active_chat_session().get("id") == session_id:
            QMessageBox.information(self, "שיחה פעילה", "אי אפשר למחוק את השיחה הפעילה בזמן שסמארטי עובד.")
            return
        answer = QMessageBox.question(
            self,
            "מחיקת שיחה",
            "למחוק את השיחה הזו לצמיתות?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        was_active = self.core.active_chat_session().get("id") == session_id
        if self.core.delete_chat_session(session_id):
            if was_active:
                self.main_window.load_active_chat_session()
            self.load_sessions()


def _fit_dialog_to_parent(dialog, parent=None, min_size=(340, 260), max_size=(620, 640)):
    parent = parent or dialog.parentWidget()
    bounds = None
    try:
        if parent is not None:
            bounds = parent.frameGeometry()
    except Exception:
        bounds = None
    if bounds is None or bounds.width() <= 0 or bounds.height() <= 0:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else None
    if bounds is None:
        dialog.resize(*max_size)
        return

    margin = 16
    available_w = max(1, int(bounds.width()) - margin * 2)
    available_h = max(1, int(bounds.height()) - margin * 2)
    min_w = min(int(min_size[0]), available_w)
    min_h = min(int(min_size[1]), available_h)
    target_w = max(min_w, min(int(max_size[0]), available_w))
    target_h = max(min_h, min(int(max_size[1]), available_h))

    dialog.setMinimumSize(min_w, min_h)
    dialog.setMaximumSize(max(min_w, available_w), max(min_h, available_h))
    dialog.resize(target_w, target_h)

    x = int(bounds.x()) + max(margin, (int(bounds.width()) - target_w) // 2)
    y = int(bounds.y()) + max(margin, (int(bounds.height()) - target_h) // 2)
    right_limit = int(bounds.x()) + int(bounds.width()) - target_w - margin
    bottom_limit = int(bounds.y()) + int(bounds.height()) - target_h - margin
    if right_limit >= int(bounds.x()) + margin:
        x = min(max(x, int(bounds.x()) + margin), right_limit)
    if bottom_limit >= int(bounds.y()) + margin:
        y = min(max(y, int(bounds.y()) + margin), bottom_limit)
    dialog.move(x, y)


def _style_release_note_images(rendered_html):
    def repl(match):
        attrs = (match.group(1) or "").strip()
        if attrs.endswith("/"):
            attrs = attrs[:-1].rstrip()
        lower = attrs.lower()
        attrs = f" {attrs}" if attrs else ""
        if "style=" not in lower:
            attrs += (
                f' style="max-width:100%; height:auto; border:1px solid {SOFT_LINE_COLOR}; '
                'border-radius:8px; margin:8px 0;"'
            )
        if "alt=" not in lower:
            attrs += ' alt=""'
        return f"<img{attrs}>"
    return re.sub(r"<img\b([^>]*)>", repl, str(rendered_html or ""), flags=re.IGNORECASE)


class ReleaseNotesBrowser(QTextBrowser):
    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self._request_settings = dict(settings or {})
        self._image_cache = {}
        option = self.document().defaultTextOption()
        option.setTextDirection(Qt.LayoutDirection.RightToLeft)
        option.setAlignment(Qt.AlignmentFlag.AlignRight)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        self.document().setDefaultTextOption(option)

    def set_release_html(self, html_text, base_url=""):
        self._image_cache.clear()
        if base_url:
            self.document().setBaseUrl(QUrl(str(base_url)))
        self.setHtml(html_text)

    def loadResource(self, resource_type, name):
        image_type = QTextDocument.ResourceType.ImageResource
        resource_value = getattr(resource_type, "value", resource_type)
        image_value = getattr(image_type, "value", image_type)
        if resource_type == image_type or resource_value == image_value:
            try:
                url = name if isinstance(name, QUrl) else QUrl(str(name))
                if url.isRelative():
                    url = self.document().baseUrl().resolved(url)
                if url.scheme().lower() in {"http", "https"}:
                    # QTextBrowser calls loadResource on the GUI thread. Skip
                    # remote images so release notes cannot freeze the dialog.
                    return QImage()
            except Exception as exc:
                logging.debug("Failed to load release note image %s: %s", name, exc)
        return super().loadResource(resource_type, name)


class UpdateNoticeDialog(QDialog):
    def __init__(self, title, message, parent=None, tone="info"):
        super().__init__(parent)
        self.setWindowTitle(str(title or "עדכונים"))
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(dialog_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)
        icon = QLabel("!" if tone == "warning" else "✓")
        icon.setFixedSize(38, 38)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_color = DANGER_COLOR if tone == "warning" else ACCENT_COLOR
        icon.setStyleSheet(
            f"QLabel {{ background: {ACCENT_TINT}; color: {icon_color}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 19px; font-size: 20px; font-weight: 900; }}"
        )
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(5)
        title_lbl = QLabel(str(title or "עדכונים"))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(page_title_css(18))
        text_col.addWidget(title_lbl)
        message_lbl = QLabel(str(message or ""))
        message_lbl.setWordWrap(True)
        message_lbl.setStyleSheet(muted_label_css(13))
        text_col.addWidget(message_lbl)
        header.addLayout(text_col, 1)
        layout.addLayout(header)

        actions = QHBoxLayout()
        actions.addStretch()
        close_btn = QPushButton("סגור")
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.setMinimumWidth(112)
        close_btn.setMinimumHeight(42)
        close_btn.setStyleSheet(PRIMARY_BUTTON_CSS if tone != "warning" else SECONDARY_BUTTON_CSS)
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

        _fit_dialog_to_parent(self, parent, min_size=(320, 210), max_size=(440, 260))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: _fit_dialog_to_parent(self, self.parentWidget(), min_size=(320, 210), max_size=(440, 260)))


class UpdateDialog(QDialog):
    install_requested = pyqtSignal()

    def __init__(self, update_info, parent=None):
        super().__init__(parent)
        self.update_info = UpdateInfo.from_dict(update_info)
        self._request_settings = dict(getattr(getattr(parent, "core", None), "settings", {}) or {})
        self.setWindowTitle("עדכון חדש לסמארטי")
        self.setModal(True)
        self.setMinimumSize(340, 430)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel(f"עדכון חדש זמין: {self.update_info.version}")
        title.setWordWrap(True)
        title.setStyleSheet(page_title_css(20))
        layout.addWidget(title)

        meta = QLabel(f"גרסה נוכחית: {self.update_info.current_version}")
        asset_label = "ZIP נייד" if self.update_info.asset_kind == "portable" else "מתקין Setup"
        meta.setText(f"{meta.text()} | סוג עדכון: {asset_label}")
        if self.update_info.asset_size:
            meta.setText(f"{meta.text()} | גודל הורדה: {human_size(self.update_info.asset_size)}")
        meta.setWordWrap(True)
        meta.setStyleSheet(muted_label_css(12))
        layout.addWidget(meta)

        notes_title = QLabel("מה חדש")
        notes_title.setStyleSheet(section_title_css(15))
        layout.addWidget(notes_title)

        self.notes_browser = ReleaseNotesBrowser(self._request_settings, self)
        self.notes_browser.setOpenExternalLinks(True)
        self.notes_browser.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.notes_browser.setStyleSheet(
            f"QTextBrowser {{ background: {GLASS_COLOR}; color: {TEXT_COLOR}; "
            f"border: 1px solid {SOFT_LINE_COLOR}; border-radius: 16px; padding: 12px; "
            "font-size: 13px; }}"
            f"QTextBrowser viewport {{ background: transparent; }}"
            f"{SCROLLBAR_CSS}"
        )
        notes = self.update_info.release_notes.strip() or "לא צורפו הערות שחרור לגרסה הזו."
        notes_html = _style_release_note_images(_render_markdown_html(notes, ACCENT_COLOR, style_blocks=True, clickable_links=True))
        self.notes_browser.set_release_html(
            "<html><head><style>"
            f"body {{ direction: rtl; text-align: right; color: {TEXT_COLOR}; font-family: {ui_font_family_css()}; font-size: 13px; }}"
            f"{asset_font_normal_italic_html_css()}"
            "p, li { line-height: 1.45; } ul, ol { margin-right: 18px; padding-right: 18px; margin-left: 0; padding-left: 0; }"
            "pre, code { direction: ltr; text-align: left; unicode-bidi: embed; }"
            "img { max-width: 100%; height: auto; }"
            "</style></head><body dir='rtl'>"
            f"{notes_html}"
            "</body></html>",
            self.update_info.html_url,
        )
        layout.addWidget(self.notes_browser, 1)

        self.status_lbl = QLabel("")
        self.status_lbl.setWordWrap(True)
        self.status_lbl.setStyleSheet(muted_label_css(12))
        layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {PANEL_COLOR}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 9px; height: 18px; text-align: center; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_COLOR}, stop:0.56 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR}); border-radius: 9px; }}"
        )
        layout.addWidget(self.progress_bar)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.install_btn = QPushButton("הורד והתקן")
        self.install_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.install_btn.setStyleSheet(PRIMARY_BUTTON_CSS)
        self.install_btn.clicked.connect(self.install_requested.emit)
        self.close_btn = QPushButton("אחר כך")
        self.close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.close_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        self.close_btn.clicked.connect(self.reject)
        for button in (self.close_btn, self.install_btn):
            button.setMinimumHeight(44)
            button.setMinimumWidth(136)
        row.addWidget(self.close_btn, 1)
        row.addWidget(self.install_btn, 1)
        layout.addLayout(row)

        if not self.update_info.asset_url:
            self.install_btn.setEnabled(False)
            expected = "ZIP נייד" if self.update_info.asset_kind == "portable" else "Setup.exe"
            self.status_lbl.setText(f"לא נמצא קובץ עדכון מתאים מסוג {expected} בפוסט השחרור בגיטהאב.")
        _fit_dialog_to_parent(self, parent, min_size=(340, 430), max_size=(620, 640))

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: _fit_dialog_to_parent(self, self.parentWidget(), min_size=(340, 430), max_size=(620, 640)))

    def set_downloading(self):
        self.install_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("מוריד את העדכון...")

    def set_progress(self, received, total):
        received = int(received or 0)
        total = int(total or 0)
        if total > 0:
            value = max(0, min(100, int(received * 100 / total)))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
            self.status_lbl.setText(f"מוריד את העדכון... {human_size(received)} מתוך {human_size(total)}")
        else:
            self.progress_bar.setRange(0, 0)
            self.status_lbl.setText(f"מוריד את העדכון... {human_size(received)}")

    def set_installing(self):
        self.progress_bar.setRange(0, 0)
        self.status_lbl.setText("ההתקנה מתחילה עכשיו. סמארטי ייסגר, יעדכן את עצמו וייפתח מחדש.")

    def set_error(self, message):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.install_btn.setEnabled(bool(self.update_info.asset_url))
        self.close_btn.setEnabled(True)
        self.status_lbl.setText(f"שגיאת עדכון: {message}")


class VoicePulseWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._movie = None
        self._movie_path = ""
        self.setFixedSize(42, 42)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")
        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._tick)
        self._load_animation_asset()

    def _animation_asset_path(self):
        candidates = themed_asset_candidates(
            "voice_listening.gif",
            "listen_animation.gif",
            "smarti_listening.gif",
            "voice_listening",
            "listen_animation",
            "smarti_listening",
        )
        for filename in candidates:
            if not str(filename).lower().endswith(".gif"):
                continue
            path = filename if os.path.isabs(filename) or os.path.dirname(filename) else os.path.join(ASSETS_DIR, filename)
            if os.path.exists(path):
                return path
        return ""

    def _load_animation_asset(self):
        path = self._animation_asset_path()
        if path == self._movie_path:
            return
        if self._movie is not None:
            try:
                self._movie.stop()
                self._movie.frameChanged.disconnect()
            except Exception:
                pass
            self._movie = None
        self._movie_path = path
        if not path:
            return
        movie = QMovie(path)
        movie.setCacheMode(QMovie.CacheMode.CacheAll)
        movie.setScaledSize(QSize(40, 40))
        movie.frameChanged.connect(lambda _=None: self.update())
        self._movie = movie

    def start(self):
        self._load_animation_asset()
        if self._movie is not None and self._movie.isValid():
            self._movie.start()
        elif not self._timer.isActive():
            self._timer.start()
        self.show()

    def stop(self):
        self._timer.stop()
        if self._movie is not None:
            self._movie.stop()
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.16) % (math.pi * 2)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), qcolor_from_css(GLASS_STRONG_COLOR))
        badge_rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.setPen(QPen(qcolor_from_css(LINE_COLOR), 1.4))
        painter.setBrush(qcolor_from_css(ACCENT_TINT))
        painter.drawEllipse(badge_rect)

        if self._movie is not None and self._movie.isValid():
            pixmap = self._movie.currentPixmap()
            if not pixmap.isNull():
                clip = QPainterPath()
                clip.addEllipse(badge_rect.adjusted(4, 4, -4, -4))
                painter.save()
                painter.setClipPath(clip)
                target = badge_rect.adjusted(0.5, 0.5, -0.5, -0.5).toRect()
                painter.drawPixmap(target, pixmap)
                painter.restore()
                painter.setPen(QPen(qcolor_from_css(LINE_COLOR), 2.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(badge_rect.adjusted(1.3, 1.3, -1.3, -1.3))
                painter.end()
                return

        center = self.rect().center()
        accent = qcolor_from_css(ACCENT_COLOR)
        pink = qcolor_from_css(ACCENT_PINK_COLOR)
        secondary = qcolor_from_css(ACCENT_SECONDARY_COLOR)

        for index, base_radius in enumerate((9, 14, 18)):
            pulse = (math.sin(self._phase + index * 0.8) + 1.0) / 2.0
            color = QColor(accent)
            color.setAlpha(int(42 + pulse * 50))
            painter.setPen(QPen(color, 1.2))
            radius = base_radius + pulse * 2.0
            painter.drawEllipse(center, int(radius), int(radius))

        painter.setPen(Qt.PenStyle.NoPen)
        core = QColor(pink)
        core.setAlpha(225)
        painter.setBrush(core)
        painter.drawEllipse(center, 8, 8)

        bar_width = 3
        gap = 3
        start_x = center.x() - bar_width - gap
        for index, color in enumerate((secondary, accent, secondary)):
            level = (math.sin(self._phase * 1.7 + index * 1.25) + 1.0) / 2.0
            height = 7 + level * 12
            rect = QRectF(start_x + index * (bar_width + gap), center.y() - height / 2, bar_width, height)
            bar_color = QColor(color)
            bar_color.setAlpha(235)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(rect, 2, 2)
        painter.end()


class VoiceListeningOverlay(QWidget):
    open_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, owner=None):
        super().__init__(None)
        self.owner = owner
        self.setObjectName("VoiceListeningOverlay")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._expanded_width = 342
        self._compact_width = 298
        self._overlay_height = 70
        self.setFixedSize(self._expanded_width, self._overlay_height)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("VoiceOverlayCard")
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_layout = QHBoxLayout(self.card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(8)

        self.cancel_btn = QPushButton()
        self.cancel_btn.setFixedSize(36, 36)
        self.cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.cancel_btn.setToolTip("בטל האזנה")
        self.cancel_btn.clicked.connect(lambda checked=False: self.cancel_requested.emit())

        self.open_btn = QPushButton()
        self.open_btn.setFixedSize(36, 36)
        self.open_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.open_btn.setToolTip("פתח את סמארטי")
        self.open_btn.clicked.connect(lambda checked=False: self.open_requested.emit())

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.setContentsMargins(0, 0, 0, 0)
        self.title_lbl = QLabel("האזנה פעילה")
        self.title_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        self.status_lbl = QLabel("אפשר לדבר עכשיו")
        self.status_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
        self.status_lbl.setWordWrap(True)
        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.status_lbl)

        self.pulse = VoicePulseWidget()
        card_layout.addWidget(self.cancel_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        card_layout.addWidget(self.open_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        card_layout.addLayout(text_col, 1)
        card_layout.addWidget(self.pulse, 0, Qt.AlignmentFlag.AlignVCenter)

        root_layout.addWidget(self.card)
        self.apply_theme()
        self.hide()

    def apply_theme(self):
        self.setStyleSheet(
            f"QWidget#VoiceListeningOverlay {{ background: {GLASS_STRONG_COLOR}; border: 1px solid {LINE_COLOR}; }}"
        )
        self.card.setStyleSheet(
            f"QFrame#VoiceOverlayCard {{ background: {GLASS_STRONG_COLOR}; border: none; border-radius: 0px; }}"
        )
        self.title_lbl.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 14px; font-weight: 900; background: transparent; border: none;")
        self.status_lbl.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px; font-weight: 700; background: transparent; border: none;")
        button_css = (
            f"QPushButton {{ background: {ACCENT_TINT}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 18px; padding: 0px 10px; font-size: 12px; font-weight: 800; outline: none; }}"
            f"QPushButton:hover {{ background: {FIELD_HOVER_COLOR}; color: {TEXT_COLOR}; border-color: {LINE_COLOR}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR}; }}"
            f"QPushButton:disabled {{ background: {PANEL_ELEVATED_COLOR}; color: {SUBTLE_TEXT_COLOR}; border-color: {SOFT_LINE_COLOR}; }}"
        )
        self.open_btn.setStyleSheet(button_css)
        self.cancel_btn.setStyleSheet(button_css)
        set_themed_button_icon(
            self.open_btn,
            ("voice_overlay_open", "open_smarti_icon", "open_icon", "logo"),
            "פתח",
            18,
            clear_text=True,
        )
        set_themed_button_icon(
            self.cancel_btn,
            ("voice_overlay_cancel", "cancel_listening_icon", CLOSE_SVG_PATH, "close_icon", "stop_agent_icon"),
            "×",
            18,
            clear_text=True,
        )
        self.pulse.update()

    def _owner_is_foreground(self):
        owner = self.owner
        try:
            if not owner or not owner.isVisible() or owner.isMinimized():
                return False
            active = QApplication.activeWindow()
            return bool(owner.isActiveWindow() or active is owner or (active is not None and owner.isAncestorOf(active)))
        except Exception:
            return False

    def update_open_button_visibility(self):
        show_open = not self._owner_is_foreground()
        self.open_btn.setVisible(show_open)
        target_width = self._expanded_width if show_open else self._compact_width
        if self.width() != target_width or self.height() != self._overlay_height:
            self.setFixedSize(target_width, self._overlay_height)

    def set_status(self, text):
        text = str(text or "").strip()
        if not text:
            return
        if "מקשיב" in text:
            self.title_lbl.setText("האזנה פעילה")
            self.status_lbl.setText("אפשר לדבר עכשיו")
        elif "מפעיל" in text or "פותח" in text:
            self.title_lbl.setText("מפעיל האזנה")
            self.status_lbl.setText(text)
        elif "מתמלל" in text:
            self.title_lbl.setText("מעבד קול")
            self.status_lbl.setText(text)
        elif "מפסיק" in text:
            self.title_lbl.setText("מפסיק האזנה")
            self.status_lbl.setText("מסיים את ההאזנה...")
        else:
            self.status_lbl.setText(text)

    def set_cancel_enabled(self, enabled):
        self.cancel_btn.setEnabled(bool(enabled))

    def show_listening(self, owner=None):
        if owner is not None:
            self.owner = owner
        self.apply_theme()
        self.set_cancel_enabled(True)
        self.update_open_button_visibility()
        self.pulse.start()
        self.adjustSize()
        self.position_near_owner()
        self.show()
        self.raise_()

    def hide_listening(self):
        self.pulse.stop()
        self.hide()

    def position_near_owner(self):
        self.update_open_button_visibility()
        size = self.size()
        owner = self.owner
        screen = None
        owner_visible = False
        try:
            owner_visible = bool(owner and owner.isVisible() and not owner.isMinimized())
        except Exception:
            owner_visible = False
        if owner_visible:
            geom = owner.frameGeometry()
            screen = QApplication.screenAt(geom.center()) or QApplication.primaryScreen()
        else:
            screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            geom = screen.availableGeometry() if screen else QRectF(0, 0, 800, 600).toRect()
        available = screen.availableGeometry() if screen else geom
        if owner_visible:
            x = geom.x() + max(0, (geom.width() - size.width()) // 2)
            y = geom.y() - size.height() - 12
            if y < available.top() + 8:
                y = geom.y() + 12
        else:
            x = available.x() + max(0, (available.width() - size.width()) // 2)
            y = available.bottom() - size.height() - 34
        x = max(available.left() + 8, min(x, available.right() - size.width() - 8))
        y = max(available.top() + 8, min(y, available.bottom() - size.height() - 8))
        self.move(int(x), int(y))


class ChatWindow(QMainWindow):
    gui_message_signal = pyqtSignal(str, bool)
    tts_status_signal = pyqtSignal(bool)
    core_notification_signal = pyqtSignal(str, object)
    INITIAL_THINKING_DELAY_MS = 1200
    voice_hotkey_signal = pyqtSignal()
    background_task_start_signal = pyqtSignal(str, str, str)
    background_task_step_signal = pyqtSignal(str, object)
    background_task_finish_signal = pyqtSignal(str, str, str, bool)

    def format_model_name(self, name):
        name = str(name).replace("-", " ").replace("_", " ")
        return " ".join(name.split())

    def active_chat_title(self):
        try:
            session = self.core.active_chat_session()
            title = str(session.get("title", "") or "").strip()
            if session.get("messages") and title and title != DEFAULT_CHAT_TITLE:
                return title
        except Exception:
            pass
        return SMARTI_APP_DISPLAY_NAME

    def refresh_chat_title(self):
        title = self.active_chat_title()
        if hasattr(self, "title_label"):
            self.title_label.setText(title)
        self.setWindowTitle(f"{SMARTI_APP_DISPLAY_NAME} - {title}" if title != SMARTI_APP_DISPLAY_NAME else SMARTI_APP_DISPLAY_NAME)

    def __init__(self, core):
        super().__init__()
        self.core = core
        self.core.start_new_chat_session()
        self.agent_running = False
        self.current_agent_bubble = None
        self.current_agent_container = None
        self._last_user_anchor_container = None
        self.active_tts_container = None
        self.tts_active = False
        self.tts_thread = None
        self._tts_workers = []
        self.voice_thread = None
        self._voice_hotkey_handle = None
        self._quit_requested = False
        self._tray_close_hint_shown = False
        self._suppress_menu_open_once = False
        self._open_quick_menu = None
        self._open_quick_menu_button = None
        self._suppress_quick_menu_button = None
        self.available_update = None
        self.update_check_worker = None
        self.update_download_worker = None
        self._update_dialog = None
        self._update_check_source = None
        self.pending_attachments = []
        self._canvas_expanded = False
        self._compact_window_size = None
        self._pending_canvas_layout = None
        self._canvas_layout_save_scheduled = False
        self._canvas_taskbar_alignment_scheduled = False
        self._background_task_containers = {}
        self.taskbar_attention = TaskbarAttentionController(self)
        self.notifications = WindowsNotificationCenter(self)
        self.notifications.reply_requested.connect(self.handle_notification_reply)
        self.notifications.activate_requested.connect(self.handle_notification_activation)
        self.notifications.attention_cleared.connect(self._clear_taskbar_attention)
        self.notifications.conversation_switch_requested.connect(self.handle_conversation_switch_requested)
        self.core_notification_signal.connect(self.handle_core_notification)
        self.core.notification_callback = lambda kind, payload=None: self.core_notification_signal.emit(kind, payload or {})
        self.voice_overlay = VoiceListeningOverlay(self)
        self.voice_overlay.open_requested.connect(self.bring_to_front)
        self.voice_overlay.cancel_requested.connect(self.cancel_voice)
        
        self.background_task_start_signal.connect(self.handle_background_task_start)
        self.background_task_step_signal.connect(self.handle_background_task_step)
        self.background_task_finish_signal.connect(self.handle_background_task_finish)
        
        self.core.background_task_start_callback = lambda sess_id, task_id, prompt: self.background_task_start_signal.emit(sess_id, task_id, prompt)
        self.core.background_task_step_callback = lambda task_id, event: self.background_task_step_signal.emit(task_id, event)
        self.core.background_task_finish_callback = lambda sess_id, task_id, res, ok: self.background_task_finish_signal.emit(sess_id, task_id, res, ok)
        
        icon_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(icon_path): self.tray_icon.setIcon(QIcon(icon_path))
        else:
            dummy_pixmap = QPixmap(32, 32)
            dummy_pixmap.fill(QColor(ACCENT_COLOR))
            self.tray_icon.setIcon(QIcon(dummy_pixmap))
            
        self.tray_icon.messageClicked.connect(self.bring_to_front)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.setToolTip(SMARTI_APP_DISPLAY_NAME)
        self._setup_tray_menu()
        self.tray_icon.show()
        # Custom QuickReplyToast fallback is intentionally disabled.
        # self.quick_reply_toast = QuickReplyToast()
        # self.quick_reply_toast.reply_submitted.connect(self.submit_quick_reply)
        
        self.gui_message_signal.connect(self.add_message)
        self.core.print_callback = lambda txt, is_user: self.gui_message_signal.emit(txt, is_user)
        self.tts_status_signal.connect(self.on_tts_status)
        self.voice_hotkey_signal.connect(self.trigger_voice_from_hotkey)
        self.core.tts_status_callback = lambda is_playing: self.tts_status_signal.emit(is_playing)
        
        self.setWindowTitle(SMARTI_APP_DISPLAY_NAME)
        self.setMinimumSize(380, 680)
        available = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        if available:
            target_w = min(450, max(380, available.width() - 40))
            target_h = min(760, max(680, available.height() - 60))
            self.resize(target_w, target_h)
            self.move(
                available.x() + max(0, (available.width() - target_w) // 2),
                available.bottom() - target_h + 1
            )
            self._schedule_canvas_taskbar_alignment()
        else:
            self.resize(450, 760) 
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        apply_app_theme(QApplication.instance(), settings=self.core.settings)
        self.setStyleSheet(
            f"QMainWindow {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {MESH_A}, stop:0.45 {MESH_B}, stop:0.72 {MESH_C}, stop:1 {MESH_D}); }}"
        )
        
        self.stacked_widget = AnimatedStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self.chat_page = MeshGradientWidget()
        self.setup_chat_page()
        self.stacked_widget.addWidget(self.chat_page)
        
        self.settings_page = None
        self.tools_page = None
        self.usage_page = None
        self.task_center_page = None
        self.trace_page = None
        self.history_page = None
        self.doctor_page = None
        self.about_page = None
        
        logging.info(f"\n{'='*50}\n--- תחילת שיחה חדשה (הפעלת תוכנה) ---\n{'='*50}")
        self.load_active_chat_session()
        self._ensure_hourly_update_interval()
        self.update_check_timer = QTimer(self)
        self.update_check_timer.setInterval(60 * 60 * 1000)
        self.update_check_timer.timeout.connect(self.maybe_check_for_updates)
        self.update_check_timer.start()
        QTimer.singleShot(1200, self.core.resume_background_tasks)
        QTimer.singleShot(2600, self.maybe_check_for_updates)
        
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.unregister_voice_hotkey)

        if SPEECH_INSTALLED and KEYBOARD_INSTALLED:
            QTimer.singleShot(1500, self.register_voice_hotkey)

    def register_voice_hotkey(self):
        try:
            if self._voice_hotkey_handle is not None:
                self.unregister_voice_hotkey()
            import keyboard
            hotkey = str(self.core.settings.get("voice_hotkey", "alt+v") or "alt+v")
            self._voice_hotkey_handle = keyboard.add_hotkey(hotkey, lambda: self.voice_hotkey_signal.emit())
        except Exception as e:
            logging.warning(f"Voice hotkey registration failed: {e}")

    def unregister_voice_hotkey(self):
        handle = getattr(self, "_voice_hotkey_handle", None)
        if handle is None:
            return
        try:
            import keyboard
            keyboard.remove_hotkey(handle)
        except Exception:
            pass
        self._voice_hotkey_handle = None

    def _setup_tray_menu(self):
        self.tray_menu = QMenu()
        self.tray_menu.setWindowFlags(self.tray_menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.tray_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.tray_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        prepare_popup_menu(self.tray_menu)
        self.tray_open_action = self.tray_menu.addAction("פתח את SmartiAI")
        self.tray_open_action.triggered.connect(self.bring_to_front)
        self.tray_listen_action = self.tray_menu.addAction("התחל האזנה")
        self.tray_listen_action.triggered.connect(self.start_voice_from_tray)
        self.tray_stop_tts_action = self.tray_menu.addAction("עצור הקראה")
        self.tray_stop_tts_action.triggered.connect(self.stop_tts_from_tray)
        self.tray_menu.addSeparator()
        self.tray_new_chat_action = self.tray_menu.addAction("שיחה חדשה")
        self.tray_new_chat_action.triggered.connect(self.start_new_chat_from_tray)
        self.tray_settings_action = self.tray_menu.addAction("הגדרות")
        self.tray_settings_action.triggered.connect(self.show_settings_from_tray)
        self.tray_tasks_action = self.tray_menu.addAction("מרכז משימות")
        self.tray_tasks_action.triggered.connect(self.show_task_center_from_tray)
        self.tray_menu.addSeparator()
        self.tray_quit_action = self.tray_menu.addAction("יציאה")
        self.tray_quit_action.triggered.connect(self.quit_from_tray)
        self.tray_menu.aboutToShow.connect(self._refresh_tray_menu)
        self.tray_icon.setContextMenu(self.tray_menu)

    def _refresh_tray_menu(self):
        voice_running = bool(getattr(self, "voice_thread", None) and self.voice_thread.isRunning())
        self.tray_listen_action.setEnabled(not self.agent_running and not voice_running and SPEECH_INSTALLED)
        self.tray_stop_tts_action.setEnabled(bool(self.tts_active))

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.bring_to_front()

    def start_voice_from_tray(self):
        self.trigger_voice_from_hotkey()

    def stop_tts_from_tray(self):
        self.core.stop_speaking()
        self.tts_active = False
        self.active_tts_container = None
        self._refresh_message_tts_buttons()

    def start_new_chat_from_tray(self):
        self.bring_to_front()
        self.start_new_chat()

    def show_settings_from_tray(self):
        self.bring_to_front()
        self.show_settings_page()

    def show_task_center_from_tray(self):
        self.bring_to_front()
        self.show_task_center_page()

    def quit_from_tray(self):
        self._quit_requested = True
        self.core.stop_speaking()
        self.unregister_voice_hotkey()
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        app = QApplication.instance()
        if app:
            app.quit()

    def attach_instance_server(self, server):
        self._instance_server = server
        server.newConnection.connect(self._handle_instance_command)

    def _handle_instance_command(self):
        server = getattr(self, "_instance_server", None)
        if not server:
            return
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            if socket.waitForReadyRead(250):
                command = bytes(socket.readAll()).decode("utf-8", "ignore").strip()
            else:
                command = "show_new_chat"
            socket.disconnectFromServer()
            if command == "voice":
                self.open_new_chat_from_activation(start_listening=True)
            elif command == "quit_for_update":
                self.quit_for_update()
            else:
                self.open_new_chat_from_activation(start_listening=False)

    def open_new_chat_from_activation(self, start_listening=False):
        if not self.agent_running:
            self.start_new_chat()
        self.stacked_widget.setCurrentWidget(self.chat_page)
        if start_listening and not self.agent_running:
            QTimer.singleShot(150, self.start_voice)
        else:
            self.bring_to_front()

    def _utc_now_iso(self):
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def _ensure_hourly_update_interval(self):
        try:
            if int(self.core.settings.get("updates_check_interval_hours", 1) or 1) != 1:
                self.core.settings["updates_check_interval_hours"] = 1
                self.core._save_settings()
        except Exception:
            self.core.settings["updates_check_interval_hours"] = 1

    def _auto_update_check_due(self):
        if not bool(self.core.settings.get("updates_auto_check", True)):
            return False
        try:
            interval_hours = max(1, int(self.core.settings.get("updates_check_interval_hours", 1) or 1))
        except Exception:
            interval_hours = 1
        last_value = str(self.core.settings.get("updates_last_checked_at", "") or "").strip()
        if not last_value:
            return True
        try:
            text = last_value[:-1] if last_value.endswith("Z") else last_value
            last_dt = datetime.fromisoformat(text)
            offset = last_dt.utcoffset() if last_dt.tzinfo else None
            if offset is not None:
                last_dt = (last_dt - offset).replace(tzinfo=None)
            return (datetime.utcnow() - last_dt).total_seconds() >= interval_hours * 3600
        except Exception:
            return True

    def maybe_check_for_updates(self):
        if self._auto_update_check_due():
            self.check_for_updates(manual=False)

    def check_for_updates_manual(self, source_widget=None):
        self.check_for_updates(manual=True, source_widget=source_widget)

    def check_for_updates(self, manual=False, source_widget=None):
        worker = getattr(self, "update_check_worker", None)
        if worker is not None and worker.isRunning():
            if manual:
                if source_widget and hasattr(source_widget, "finish_update_check"):
                    source_widget.finish_update_check("בדיקת עדכונים כבר מתבצעת.")
                else:
                    self.show_update_notice("בדיקת עדכונים", "בדיקת עדכונים כבר מתבצעת.")
            return

        self._update_check_source = source_widget
        if source_widget and hasattr(source_widget, "begin_update_check"):
            source_widget.begin_update_check()

        worker = UpdateCheckWorker(self.core.settings, self)
        self.update_check_worker = worker
        worker.found.connect(lambda info: self._handle_update_found(info, manual))
        worker.no_update.connect(lambda message: self._handle_update_not_found(message, manual))
        worker.failed.connect(lambda message: self._handle_update_check_failed(message, manual))
        worker.finished.connect(lambda: self._cleanup_update_check_worker(worker))
        worker.start()

    def _record_update_check(self, available_version=None):
        try:
            self.core.settings["updates_last_checked_at"] = self._utc_now_iso()
            if available_version is not None:
                self.core.settings["updates_last_available_version"] = available_version
            self.core.settings["updates_check_interval_hours"] = 1
            self.core._save_settings()
        except Exception:
            pass
        self._refresh_settings_update_status()

    def _refresh_settings_update_status(self):
        page = getattr(self, "settings_page", None)
        if page and hasattr(page, "refresh_update_status_label"):
            try:
                page.refresh_update_status_label()
            except Exception:
                pass

    def _finish_update_source(self, message, reset_after_ms=0):
        source = getattr(self, "_update_check_source", None)
        self._update_check_source = None
        if source and hasattr(source, "finish_update_check"):
            try:
                source.finish_update_check(message, reset_after_ms=reset_after_ms)
            except TypeError:
                source.finish_update_check(message)

    def _cleanup_update_check_worker(self, worker):
        if getattr(self, "update_check_worker", None) is worker:
            self.update_check_worker = None
        worker.deleteLater()

    def show_update_notice(self, title, message, tone="info"):
        dialog = UpdateNoticeDialog(title, message, self, tone=tone)
        dialog.exec()

    def _handle_update_found(self, info, manual=False):
        self.available_update = UpdateInfo.from_dict(info)
        self._record_update_check(self.available_update.version)
        self._refresh_update_button()
        self._finish_update_source(f"נמצא עדכון חדש: {self.available_update.version}")
        if manual:
            self.show_update_dialog(update_info=self.available_update)

    def _handle_update_not_found(self, message, manual=False):
        self.available_update = None
        self._record_update_check("")
        self._refresh_update_button()
        self._finish_update_source("אין עדכון חדש.", reset_after_ms=7000)

    def _handle_update_check_failed(self, message, manual=False):
        self._finish_update_source(f"שגיאה בבדיקת עדכונים: {message}")
        if manual:
            self.show_update_notice("בדיקת העדכונים נכשלה", f"לא הצלחתי לבדוק עדכונים:\n{message}", tone="warning")

    def _refresh_update_button(self):
        if not hasattr(self, "update_btn"):
            return
        info = getattr(self, "available_update", None)
        self.update_btn.setVisible(bool(info))
        if info:
            self.update_btn.setToolTip(f"יש עדכון חדש לסמארטי: {info.version}. לחץ להורדה והתקנה.")
            self.update_btn.raise_()

    def show_update_dialog(self, _checked=False, update_info=None):
        info = UpdateInfo.from_dict(update_info or getattr(self, "available_update", None) or {})
        if not info.version:
            self.check_for_updates(manual=True)
            return
        dialog = UpdateDialog(info, self)
        self._update_dialog = dialog
        dialog.install_requested.connect(lambda: self.start_update_download(info, dialog))
        dialog.exec()
        if self._update_dialog is dialog:
            self._update_dialog = None

    def start_update_download(self, update_info, dialog=None):
        worker = getattr(self, "update_download_worker", None)
        if worker is not None and worker.isRunning():
            return
        info = UpdateInfo.from_dict(update_info)
        dialog = dialog or getattr(self, "_update_dialog", None)
        if dialog:
            dialog.set_downloading()
        worker = UpdateDownloadWorker(info, self.core.settings, self)
        self.update_download_worker = worker
        if dialog:
            worker.progress.connect(dialog.set_progress)
        worker.downloaded.connect(lambda path: self._handle_update_downloaded(path, dialog))
        worker.failed.connect(lambda message: self._handle_update_download_failed(message, dialog))
        worker.finished.connect(lambda: self._cleanup_update_download_worker(worker))
        worker.start()

    def _cleanup_update_download_worker(self, worker):
        if getattr(self, "update_download_worker", None) is worker:
            self.update_download_worker = None
        worker.deleteLater()

    def _handle_update_downloaded(self, installer_path, dialog=None):
        if dialog:
            dialog.set_installing()
        try:
            launch_update_installer(installer_path, app_pid=os.getpid())
        except Exception as exc:
            if dialog:
                dialog.set_error(str(exc))
            return
        QTimer.singleShot(450, self.quit_for_update)

    def _handle_update_download_failed(self, message, dialog=None):
        if dialog:
            dialog.set_error(message)
        else:
            self.show_update_notice("הורדת העדכון נכשלה", f"לא הצלחתי להוריד את העדכון:\n{message}", tone="warning")

    def quit_for_update(self):
        self._quit_requested = True
        try:
            self.core.request_cancel()
        except Exception:
            pass
        try:
            self.core.stop_speaking()
        except Exception:
            pass
        try:
            self.core._close_automation_browser()
        except Exception:
            pass
        self.unregister_voice_hotkey()
        if hasattr(self, "tray_icon"):
            self.tray_icon.hide()
        app = QApplication.instance()
        if app:
            app.quit()

    def _chat_page_stylesheet(self):
        return f"""
            QWidget#ChatPage {{
                background: transparent;
            }}
        """

    def _top_bar_stylesheet(self):
        return f"""
            QWidget#TopBar {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {TOP_GRADIENT_A}, stop:0.62 {TOP_GRADIENT_B}, stop:1 {TOP_GRADIENT_C});
                border: none;
                border-bottom: 1px solid {SOFT_LINE_COLOR};
            }}
        """

    def _menu_button_stylesheet(self):
        return (
            f"QPushButton {{ color: {TEXT_COLOR}; background: transparent; border: 1px solid transparent; "
            f"border-radius: 24px; padding-bottom: 3px; outline: none; }}"
            f"QPushButton:hover {{ background: {ACCENT_TINT}; border-color: {SOFT_LINE_COLOR}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_TINT_STRONG}; border-color: {LINE_COLOR}; }}"
        )

    def _update_button_stylesheet(self):
        return (
            "QPushButton#UpdateButton {"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});"
            f"color: {ACCENT_TEXT_COLOR}; border: 2px solid {ACCENT_WARM_COLOR}; border-radius: 24px;"
            "font-size: 20px; font-weight: 900; padding: 0px; outline: none;"
            "}"
            "QPushButton#UpdateButton:hover {"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {BRAND_ACCENT_COLOR}, stop:0.52 {BRAND_PINK_COLOR}, stop:1 {BRAND_SECONDARY_COLOR});"
            f"border-color: {TEXT_COLOR};"
            "}"
            f"QPushButton#UpdateButton:pressed {{ background: {ACCENT_COLOR}; }}"
        )

    def _set_menu_button_icon(self):
        if not hasattr(self, "menu_btn"):
            return
        set_themed_button_icon(self.menu_btn, ("menu_icon",), "⋮", 26, clear_text=True)
        if self.menu_btn.text():
            self.menu_btn.setFont(QFont("Arial", 28, QFont.Weight.Bold))

    def _set_update_button_icon(self):
        if not hasattr(self, "update_btn"):
            return
        set_themed_button_icon(self.update_btn, ("update_icon", "download_update_icon", "download_icon", "reset_icon"), "!", 26, clear_text=True)

    def _add_menu_action(self, text, callback, *icon_names):
        action = self.menu.addAction(text)
        action.setIconVisibleInMenu(True)
        action.triggered.connect(callback)
        self._menu_actions.append((action, icon_names))
        self._refresh_menu_action_icon(action, icon_names)
        return action

    def _refresh_menu_action_icon(self, action, icon_names):
        icon = _asset_icon(*icon_names)
        action.setIcon(icon if not icon.isNull() else _transparent_icon(22))

    def _refresh_menu_action_icons(self):
        for action, icon_names in getattr(self, "_menu_actions", []):
            self._refresh_menu_action_icon(action, icon_names)

    def _chat_input_stylesheet(self):
        return (
            f"QTextEdit {{ background-color: transparent; color: {FIELD_TEXT_COLOR}; border: none; "
            f"padding: 4px 10px; font-size: 17px; font-family: {ui_font_family_css()}; outline: none; text-align: left; }}"
            f"QTextEdit:disabled {{ color: {SUBTLE_TEXT_COLOR}; }}"
            f"QTextEdit viewport {{ background-color: transparent; border: none; }}"
            f"{SCROLLBAR_CSS}"
        )

    def _quick_input_button_stylesheet(self):
        return f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_COLOR};
                border: 1px solid transparent;
                border-radius: 16px;
                padding: 7px 40px 7px 14px;
                font-size: 12px;
                font-weight: 700;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background: {ACCENT_TINT};
                border-color: {SOFT_LINE_COLOR};
            }}
            QPushButton:pressed {{
                background: {ACCENT_TINT_STRONG};
                border-color: {ACCENT_PINK_COLOR};
            }}
        """

    def _autonomy_items(self):
        return [
            ("locked_down", "בטוח"),
            ("balanced", "מאוזן"),
            ("max_autonomy", "אוטונומי"),
        ]

    def _favorite_model_key(self, provider, model):
        return (normalize_provider_name(provider), str(model or "").strip())

    def _normalized_favorite_models(self):
        seen = set()
        favorites = []
        for item in self.core.settings.get("favorite_models", []) or []:
            if not isinstance(item, dict):
                continue
            provider, model = self._favorite_model_key(item.get("provider"), item.get("model"))
            if not provider or not model or (provider, model) in seen:
                continue
            seen.add((provider, model))
            favorites.append({"provider": provider, "model": model})
        self.core.settings["favorite_models"] = favorites[:60]
        return self.core.settings["favorite_models"]

    def _ensure_current_model_favorite(self, *, save=False):
        provider = normalize_provider_name(self.core.settings.get("api_mode", getattr(self.core, "mode", "gemini")) or "gemini")
        model = str(self.core.settings.get(f"selected_{provider}_model") or provider_default_model(provider) or "").strip()
        if not provider or not model:
            return
        favorites = self._normalized_favorite_models()
        key = self._favorite_model_key(provider, model)
        if any(self._favorite_model_key(item.get("provider"), item.get("model")) == key for item in favorites):
            return
        favorites.insert(0, {"provider": provider, "model": model})
        self.core.settings["favorite_models"] = favorites[:60]
        if save:
            self.core._save_settings()

    def _favorite_model_label(self, provider, model):
        return self.format_model_name(model)

    def _codex_reasoning_options(self):
        return [
            ("low", "נמוכה"),
            ("medium", "בינונית"),
            ("high", "גבוהה"),
            ("xhigh", "גבוהה מאוד"),
        ]

    def _current_model_provider(self):
        return normalize_provider_name(self.core.settings.get("api_mode", getattr(self.core, "mode", "gemini")) or "gemini")

    def _current_codex_reasoning_effort(self):
        effort = str(self.core.settings.get("codex_reasoning_effort", "medium") or "medium").strip().lower()
        return effort if effort in {value for value, _ in self._codex_reasoning_options()} else "medium"

    def _add_menu_header(self, menu, text):
        action = menu.addAction(str(text or ""))
        action.setEnabled(False)
        font = app_font(10, QFont.Weight.Bold)
        font.setItalic(False)
        action.setFont(font)
        return action

    def _reasoning_selected_icon(self):
        return themed_icon(
            "reasoning_effort_selected_icon",
            "reasoning_effort_selected",
            "reasoning_selected_icon",
            "reasoning_selected",
            "codex_reasoning_selected_icon",
            "codex_reasoning_selected",
        )

    def _add_codex_reasoning_menu_items(self, menu):
        if self._current_model_provider() != "openai_codex_signin":
            return False
        self._add_menu_header(menu, "עוצמת חשיבה")
        current_effort = self._current_codex_reasoning_effort()
        check_icon = self._reasoning_selected_icon()
        for value, label in self._codex_reasoning_options():
            action = menu.addAction(label)
            if value == current_effort and not check_icon.isNull():
                action.setIcon(check_icon)
                action.setIconVisibleInMenu(True)
            action.triggered.connect(lambda checked=False, effort=value: self._select_codex_reasoning_effort(effort))
        menu.addSeparator()
        return True

    def _select_codex_reasoning_effort(self, effort):
        effort = str(effort or "medium").strip().lower()
        if effort not in {value for value, _ in self._codex_reasoning_options()}:
            effort = "medium"
        if effort == self._current_codex_reasoning_effort():
            return
        self.core.settings["codex_reasoning_effort"] = effort
        self.core._save_settings()
        if getattr(self, "settings_page", None) is not None and hasattr(self.settings_page, "codex_reasoning_effort_combo"):
            combo = self.settings_page.codex_reasoning_effort_combo
            index = combo.findData(effort)
            if index >= 0:
                previous = combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(previous)

    def _fit_quick_input_button(self, button, text, base_width=150, max_width=320, min_width=92):
        try:
            text = str(text or "")
            button.setProperty("smartiFullQuickText", text)
            text_width = button.fontMetrics().horizontalAdvance(str(text or ""))
            icon_extra = 28 if not button.icon().isNull() else 0
            arrow_extra = int(getattr(button, "_arrow_size", 13) or 13) + 28
            padding_extra = 54
            width = max(int(base_width), int(text_width) + icon_extra + arrow_extra + padding_extra)
            width = max(int(min_width), min(width, int(max_width)))
            text_budget = max(36, width - icon_extra - arrow_extra - padding_extra)
            if text_width > text_budget:
                button.setText(button.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, text_budget))
            else:
                button.setText(text)
            button.setFixedWidth(width)
        except Exception:
            button.setFixedWidth(int(min_width))

    def _quick_input_available_width(self):
        if not all(hasattr(self, attr) for attr in ("input_frame", "quick_control_row", "action_btn_host", "attach_btn")):
            return 0
        model_in_input = bool(
            hasattr(self, "favorite_model_btn")
            and self.favorite_model_btn.property("smartiModelPickerLocation") != "header"
        )
        row_width = int(self.quick_control_row.geometry().width() or 0)
        if row_width <= 0:
            row_width = int(self.input_frame.width() or 0)
            layout = self.input_frame.layout()
            if layout is not None:
                margins = layout.contentsMargins()
                row_width -= int(margins.left() + margins.right())
        spacing = max(0, int(self.quick_control_row.spacing()))
        fixed_width = int(self.action_btn_host.width() or self.action_btn_host.sizeHint().width() or 52)
        fixed_width += int(self.attach_btn.width() or self.attach_btn.sizeHint().width() or 42)
        gap_count = 4 if model_in_input else 3
        return max(0, row_width - fixed_width - (spacing * gap_count))

    def _quick_input_button_widths(self):
        available = self._quick_input_available_width()
        model_in_input = bool(
            hasattr(self, "favorite_model_btn")
            and self.favorite_model_btn.property("smartiModelPickerLocation") != "header"
        )
        if not model_in_input:
            if available <= 0:
                return 0, 220
            return 0, max(128, min(available, 260))
        if available <= 0:
            return 168, 168
        if available < 216:
            autonomy_width = max(86, int(available * 0.54))
            return max(48, available - autonomy_width), autonomy_width
        autonomy_width = min(152, max(128, int(available * 0.42)))
        model_width = max(88, available - autonomy_width)
        if model_width > 210:
            extra = model_width - 210
            model_width = 210
            autonomy_width = min(152, autonomy_width + extra)
        if model_width + autonomy_width > available:
            autonomy_width = max(104, min(autonomy_width, available - 72))
            model_width = max(48, available - autonomy_width)
        return int(model_width), int(autonomy_width)

    def _resize_quick_input_controls(self):
        if hasattr(self, "favorite_model_btn"):
            text = self.favorite_model_btn.property("smartiFullQuickText") or self.favorite_model_btn.text()
            if self.favorite_model_btn.property("smartiModelPickerLocation") == "header":
                self._fit_header_model_button(text)
            else:
                model_width, _ = self._quick_input_button_widths()
                self._fit_quick_input_button(self.favorite_model_btn, text, model_width, model_width, min(model_width, 88))
        if hasattr(self, "autonomy_quick_btn"):
            _, autonomy_width = self._quick_input_button_widths()
            text = self.autonomy_quick_btn.property("smartiFullQuickText") or self.autonomy_quick_btn.text()
            self._fit_quick_input_button(
                self.autonomy_quick_btn,
                text,
                min(152, autonomy_width),
                autonomy_width,
                min(118, autonomy_width),
            )

    def _fit_header_model_button(self, label):
        if not hasattr(self, "favorite_model_btn"):
            return
        available = 248
        if hasattr(self, "titles_widget"):
            available = max(132, min(292, int(self.titles_widget.width() or 248) - 6))
        self._fit_quick_input_button(self.favorite_model_btn, label, min(190, available), available, min(124, available))

    def refresh_favorite_model_controls(self):
        if not hasattr(self, "favorite_model_btn"):
            return
        self._ensure_current_model_favorite(save=False)
        favorites = self._normalized_favorite_models()
        current_provider = normalize_provider_name(self.core.settings.get("api_mode", getattr(self.core, "mode", "gemini")) or "gemini")
        current_model = str(self.core.settings.get(f"selected_{current_provider}_model") or provider_default_model(current_provider) or "").strip()
        self.favorite_model_btn.setVisible(bool(favorites))
        label = self._favorite_model_label(current_provider, current_model) or "מודל"
        self.favorite_model_btn.setText(label)
        self.favorite_model_btn.setIcon(QIcon())
        if self.favorite_model_btn.property("smartiModelPickerLocation") == "header":
            self._fit_header_model_button(label)
        else:
            model_width, _ = self._quick_input_button_widths()
            self._fit_quick_input_button(self.favorite_model_btn, label, model_width, model_width, min(model_width, 88))
        self.favorite_model_btn.setToolTip("מודלים מועדפים")

    def _favorites_by_provider(self):
        grouped = {}
        for item in self._normalized_favorite_models():
            grouped.setdefault(item["provider"], []).append(item["model"])
        ordered = []
        for provider in MODEL_PROVIDER_ORDER:
            if provider in grouped:
                ordered.append((provider, grouped.pop(provider)))
        ordered.extend(sorted(grouped.items(), key=lambda item: provider_display_name(item[0]).lower()))
        return ordered

    def show_favorite_model_menu(self):
        if not hasattr(self, "favorite_model_btn"):
            return
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        prepare_popup_menu(menu)
        self._add_codex_reasoning_menu_items(menu)
        for provider, models in self._favorites_by_provider():
            sub = menu.addMenu(provider_display_name(provider))
            sub.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            prepare_popup_menu(sub)
            for model in models:
                action = sub.addAction(self.format_model_name(model))
                action.triggered.connect(lambda checked=False, p=provider, m=model: self._select_favorite_model(p, m))
        if not menu.actions():
            action = menu.addAction("אין מודלים מועדפים")
            action.setEnabled(False)
        self._popup_menu_near_button(menu, self.favorite_model_btn)

    def _select_favorite_model(self, provider, model):
        provider, model = self._favorite_model_key(provider, model)
        if not provider or not model:
            return
        previous_provider = normalize_provider_name(self.core.settings.get("api_mode", getattr(self.core, "mode", "gemini")))
        previous_model = str(self.core.settings.get(f"selected_{provider}_model", "") or "")
        if provider == previous_provider and model == previous_model:
            return
        self.core.settings["api_mode"] = provider
        self.core.settings[f"selected_{provider}_model"] = model
        self._ensure_current_model_favorite(save=False)
        self.core._save_settings()
        self.core.system_prompt = self.core._load_system_prompt()
        self.core.setup_model()
        if hasattr(self, "subtitle"):
            self.subtitle.setText(self.format_model_name(model))
        self.refresh_favorite_model_controls()
        if getattr(self, "settings_page", None) is not None:
            self.stacked_widget.removeWidget(self.settings_page)
            self.settings_page.deleteLater()
            self.settings_page = None

    def _apply_autonomy_profile_to_settings(self, profile_key):
        profile = AUTONOMY_PROFILES.get(profile_key, AUTONOMY_PROFILES["balanced"])
        self.core.settings["autonomy_mode"] = profile_key
        self.core.settings["permission_level"] = profile["permission_level"]
        self.core.settings["policy_matrix"] = copy.deepcopy(profile["policy_matrix"])
        self.core.settings["raw_shell_requires_approval"] = bool(profile["raw_shell_requires_approval"])
        self.core.settings["marketplace_install_requires_approval"] = bool(profile["marketplace_install_requires_approval"])
        self.core.settings["require_approval_for_cloud_upload"] = bool(profile["require_approval_for_cloud_upload"])
        self.core.settings["write_outside_allowed_dirs_requires_approval"] = bool(profile["write_outside_allowed_dirs_requires_approval"])

    def refresh_quick_autonomy_controls(self):
        if not hasattr(self, "autonomy_quick_btn"):
            return
        current = str(self.core.settings.get("autonomy_mode", "balanced") or "balanced")
        icon_names = {
            "locked_down": ("autonomy_safe", "autonomy_safe_icon", "security_safe_icon", "shield_safe_icon"),
            "balanced": ("autonomy_balanced", "autonomy_balanced_icon", "security_balanced_icon", "balance_icon"),
            "max_autonomy": ("autonomy_full", "autonomy_full_icon", "security_full_icon", "full_access_icon"),
        }
        labels = dict(self._autonomy_items())
        label = labels.get(current, labels["balanced"])
        self.autonomy_quick_btn.setText(label)
        icon = themed_icon(*icon_names.get(current, ()))
        if not icon.isNull():
            self.autonomy_quick_btn.setIcon(icon)
            self.autonomy_quick_btn.setIconSize(QSize(18, 18))
        else:
            self.autonomy_quick_btn.setIcon(QIcon())
        _, autonomy_width = self._quick_input_button_widths()
        self._fit_quick_input_button(
            self.autonomy_quick_btn,
            label,
            min(152, autonomy_width),
            autonomy_width,
            min(118, autonomy_width),
        )
        self.autonomy_quick_btn.setToolTip("פרופיל בטיחות")

    def show_quick_autonomy_menu(self):
        if not hasattr(self, "autonomy_quick_btn"):
            return
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        prepare_popup_menu(menu)
        icon_names = {
            "locked_down": ("autonomy_safe", "autonomy_safe_icon", "security_safe_icon", "shield_safe_icon"),
            "balanced": ("autonomy_balanced", "autonomy_balanced_icon", "security_balanced_icon", "balance_icon"),
            "max_autonomy": ("autonomy_full", "autonomy_full_icon", "security_full_icon", "full_access_icon"),
        }
        for key, label in self._autonomy_items():
            action = menu.addAction(label)
            icon = themed_icon(*icon_names.get(key, ()))
            if not icon.isNull():
                action.setIcon(icon)
            action.triggered.connect(lambda checked=False, profile=key: self._select_quick_autonomy(profile))
        self._popup_menu_near_button(menu, self.autonomy_quick_btn)

    def _select_quick_autonomy(self, profile_key):
        if profile_key not in AUTONOMY_PROFILES:
            profile_key = "balanced"
        if str(self.core.settings.get("autonomy_mode", "")) == profile_key:
            return
        self._apply_autonomy_profile_to_settings(profile_key)
        self.core._save_settings()
        self.refresh_quick_autonomy_controls()
        if getattr(self, "settings_page", None) is not None:
            self.stacked_widget.removeWidget(self.settings_page)
            self.settings_page.deleteLater()
            self.settings_page = None

    def _quick_menu_button_contains_cursor(self, button):
        return bool(button and button.rect().contains(button.mapFromGlobal(QCursor.pos())))

    def _clear_quick_menu_reopen_guard(self):
        self._suppress_quick_menu_button = None

    def _clear_open_quick_menu(self, menu):
        if self._open_quick_menu is menu:
            self._open_quick_menu = None
            self._open_quick_menu_button = None
            menu.deleteLater()

    def _on_quick_menu_about_to_hide(self, menu):
        button = self._open_quick_menu_button if self._open_quick_menu is menu else None
        if button is not None:
            self._suppress_quick_menu_button = button
            QTimer.singleShot(360, self._clear_quick_menu_reopen_guard)
        QTimer.singleShot(0, lambda m=menu: self._clear_open_quick_menu(m))

    def _popup_menu_near_button(self, menu, button):
        if self._suppress_quick_menu_button is button:
            self._suppress_quick_menu_button = None
            menu.deleteLater()
            return False
        current = self._open_quick_menu
        if current and current.isVisible():
            current_button = self._open_quick_menu_button
            self._open_quick_menu = None
            self._open_quick_menu_button = None
            current.hide()
            current.deleteLater()
            if current_button is button and self._quick_menu_button_contains_cursor(button):
                self._suppress_quick_menu_button = button
                QTimer.singleShot(360, self._clear_quick_menu_reopen_guard)
                menu.deleteLater()
                return False
        menu.adjustSize()
        pos = button.mapToGlobal(QPoint(0, button.height() + 4))
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            window_rect = self.frameGeometry().adjusted(8, 8, -8, -8)
            if window_rect.isValid() and window_rect.width() > 80 and window_rect.height() > 80:
                available = available.intersected(window_rect)
            size = menu.sizeHint()
            if pos.x() + size.width() > available.right():
                pos.setX(max(available.left(), available.right() - size.width()))
            if pos.y() + size.height() > available.bottom():
                pos = button.mapToGlobal(QPoint(0, -size.height() - 4))
            pos.setX(max(available.left(), min(pos.x(), available.right() - size.width())))
            pos.setY(max(available.top(), min(pos.y(), available.bottom() - size.height())))
        self._open_quick_menu = menu
        self._open_quick_menu_button = button
        menu.aboutToHide.connect(lambda m=menu: self._on_quick_menu_about_to_hide(m))
        menu.popup(pos)
        return True

    def refresh_themed_icons(self):
        self._set_menu_button_icon()
        self._set_update_button_icon()
        self._set_attach_button_icon()
        self._refresh_menu_action_icons()

    def _set_attach_button_icon(self):
        if not hasattr(self, "attach_btn"):
            return
        _set_button_icon_or_text(
            self.attach_btn,
            ("attachment_add_icon", "attach_icon", "add_attachment_icon", "plus_icon"),
            "+",
            24,
        )
        self.attach_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_COLOR}; border: 1px solid transparent; "
            f"border-radius: 21px; padding: 0px; font-size: 28px; font-weight: 300; outline: none; }}"
            f"QPushButton:hover {{ color: {ACCENT_COLOR}; background: {ACCENT_TINT}; border-color: {SOFT_LINE_COLOR}; }}"
            f"QPushButton:pressed {{ color: {ACCENT_PINK_COLOR}; background: {ACCENT_TINT_STRONG}; border-color: {LINE_COLOR}; }}"
        )

    def apply_theme(self, mode=None, refresh_messages=True):
        apply_app_theme(QApplication.instance(), mode=mode, settings=self.core.settings)
        refresh_themed_widget_icons(self)
        self.setStyleSheet(
            f"QMainWindow {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {MESH_A}, stop:0.45 {MESH_B}, stop:0.72 {MESH_C}, stop:1 {MESH_D}); }}"
        )
        if hasattr(self, "chat_page"):
            self.chat_page.setStyleSheet(self._chat_page_stylesheet())
        if hasattr(self, "chat_splitter"):
            self.chat_splitter.setStyleSheet(f"QSplitter::handle {{ background: {SOFT_LINE_COLOR}; margin: 18px 0; border-radius: 3px; }}")
        if hasattr(self, "canvas_panel"):
            self.canvas_panel.apply_theme({
                "text": TEXT_COLOR,
                "muted": MUTED_TEXT_COLOR,
                "accent": ACCENT_COLOR,
                "line": SOFT_LINE_COLOR,
                "glass": GLASS_STRONG_COLOR,
            })
        if hasattr(self, "top_bar"):
            self.top_bar.setStyleSheet(self._top_bar_stylesheet())
        if hasattr(self, "menu_btn"):
            self.menu_btn.setStyleSheet(self._menu_button_stylesheet())
        if hasattr(self, "update_btn"):
            self.update_btn.setStyleSheet(self._update_button_stylesheet())
            apply_soft_shadow(self.update_btn, blur=26, y=7, alpha=72)
            self._set_update_button_icon()
        if hasattr(self, "menu"):
            prepare_popup_menu(self.menu)
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(page_title_css(19))
            self.refresh_chat_title()
        if hasattr(self, "subtitle") and self.subtitle is not getattr(self, "favorite_model_btn", None):
            self.subtitle.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 12px; font-weight: 700;")
            if hasattr(self.subtitle, "fullText"):
                self.subtitle.setText(self.subtitle.fullText())
        if hasattr(self, "header_line"):
            self.header_line.setStyleSheet("background: transparent; max-height: 0px;")
        if hasattr(self, "scroll"):
            self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        if hasattr(self, "status_lbl"):
            self.status_lbl.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 13px; font-weight: 700; padding: 0px 15px 5px 15px;")
        if hasattr(self, "input_frame"):
            if hasattr(self.input_frame, "apply_theme"):
                self.input_frame.apply_theme()
            else:
                self.input_frame.setStyleSheet(INPUT_FRAME_CSS)
            apply_soft_shadow(self.input_frame, blur=42, y=12, alpha=42)
        if hasattr(self, "input_field"):
            self.input_field.setStyleSheet(self._chat_input_stylesheet())
        if hasattr(self, "favorite_model_btn"):
            self.favorite_model_btn.setStyleSheet(self._quick_input_button_stylesheet())
            self.refresh_favorite_model_controls()
        if hasattr(self, "autonomy_quick_btn"):
            self.autonomy_quick_btn.setStyleSheet(self._quick_input_button_stylesheet())
            self.refresh_quick_autonomy_controls()
        if hasattr(self, "attach_btn"):
            self._set_attach_button_icon()
        if hasattr(self, "attachment_preview"):
            self.attachment_preview.apply_theme()
        if hasattr(self, "attach_menu"):
            prepare_popup_menu(self.attach_menu)
        if hasattr(self, "welcome_widget"):
            self.welcome_widget.apply_theme()
        if hasattr(self, "logo_lbl"):
            logo_path = os.path.join(ASSETS_DIR, "logo.png")
            if os.path.exists(logo_path):
                pixmap = make_circular_pixmap(logo_path, 50)
                if pixmap:
                    self.logo_lbl.setPixmap(pixmap)
            self.logo_lbl.setStyleSheet("border: none; background-color: transparent;")
        if hasattr(self, "action_btn"):
            self.refresh_themed_icons()
            self.update_action_btn_visuals()
        if hasattr(self, "voice_overlay"):
            self.voice_overlay.apply_theme()
            if self.voice_overlay.isVisible():
                self.voice_overlay.position_near_owner()
        if getattr(self, "history_page", None) is not None:
            self.history_page.apply_theme()
        if getattr(self, "doctor_page", None) is not None:
            self.doctor_page.apply_theme()
        if refresh_messages:
            for container in self.findChildren(ChatMessageContainer):
                container.apply_theme()
            self._refresh_message_tts_buttons()
        QTimer.singleShot(0, self._update_chat_bottom_padding)

    def refresh_chat_messages_async(self, batch_size=18):
        containers = list(self.findChildren(ChatMessageContainer))
        if not containers:
            return

        def apply_batch(index=0):
            for container in containers[index:index + batch_size]:
                container.apply_theme()
            next_index = index + batch_size
            if next_index < len(containers):
                QTimer.singleShot(16, lambda: apply_batch(next_index))

        QTimer.singleShot(0, apply_batch)

    def invalidate_themed_pages(self):
        for attr in ("tools_page", "usage_page", "task_center_page", "trace_page", "history_page", "about_page"):
            page = getattr(self, attr, None)
            if page is not None:
                self.stacked_widget.removeWidget(page)
                page.deleteLater()
                setattr(self, attr, None)

    def setup_chat_page(self):
        self.chat_page.setObjectName("ChatPage")
        self.chat_page.setStyleSheet(self._chat_page_stylesheet())
        main_layout = QVBoxLayout(self.chat_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        top_bar = QWidget()
        self.top_bar = top_bar
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(88)
        top_bar.setStyleSheet(self._top_bar_stylesheet())
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 7, 15, 14)
        top_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.menu_btn = QPushButton("⋮")
        self.menu_btn.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self.menu_btn.setFixedSize(48, 48)
        self.menu_btn.setToolTip("תפריט")
        self.menu_btn.setStyleSheet(self._menu_button_stylesheet())
        self.menu_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.menu = QMenu(self)
        self.menu.setWindowFlags(self.menu.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        if hasattr(self.menu, "setIconSize"):
            self.menu.setIconSize(QSize(22, 22))
        prepare_popup_menu(self.menu)
        self.menu.aboutToHide.connect(self._guard_menu_reopen_from_button)
        self._menu_actions = []
        self._add_menu_action("שיחה חדשה", self.start_new_chat, "new_chat_icon", "plus_icon")
        self._add_menu_action("היסטוריית שיחות", self.show_history_page, "chat_history_icon", "history_icon")
        self._add_menu_action("Smarti Doctor", self.show_doctor_page, "doctor_icon", "policy_icon", "connection_test_icon")
        self._add_menu_action("כלים", self.show_tools_page, "tools_icon", "toolbox_icon")
        self._add_menu_action("הגדרות", self.show_settings_page, "settings_icon")
        self._add_menu_action("מרכז משימות", self.show_task_center_page, "task_center_icon", "tasks_icon")
        self._add_menu_action("נתוני שימוש", self.show_usage_page, "usage_icon", "usage_stats_icon", "chart_icon")
        self._add_menu_action("אודות", self.show_about_page, "about_icon", "info_icon")
        self.menu_btn.clicked.connect(self.show_menu)
        self._set_menu_button_icon()

        self.update_btn = QPushButton("!")
        self.update_btn.setObjectName("UpdateButton")
        self.update_btn.setFixedSize(48, 48)
        self.update_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.update_btn.setToolTip("יש עדכון חדש לסמארטי. לחץ להורדה והתקנה.")
        self.update_btn.setStyleSheet(self._update_button_stylesheet())
        set_themed_button_icon(self.update_btn, ("update_icon", "download_update_icon", "download_icon", "reset_icon"), "!", 26, clear_text=True)
        apply_soft_shadow(self.update_btn, blur=26, y=7, alpha=72)
        self.update_btn.clicked.connect(self.show_update_dialog)
        self.update_btn.setVisible(False)
        
        titles_widget = QWidget()
        self.titles_widget = titles_widget
        titles_widget.setMinimumWidth(0)
        titles_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        titles_widget.setStyleSheet("background: transparent; border: none;")
        titles_layout = QVBoxLayout(titles_widget)
        titles_layout.setContentsMargins(8, 0, 8, 3)
        titles_layout.setSpacing(2)
        self.title_label = EndElideLabel(self.active_chat_title())
        self.title_label.setStyleSheet(page_title_css(19))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.favorite_model_btn = DropdownPillButton("מודל")
        self.favorite_model_btn.setProperty("smartiModelPickerLocation", "header")
        self.favorite_model_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.favorite_model_btn.setFixedWidth(172)
        self.favorite_model_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.favorite_model_btn.setStyleSheet(self._quick_input_button_stylesheet())
        self.favorite_model_btn.clicked.connect(self.show_favorite_model_menu)
        self.subtitle = self.favorite_model_btn
        titles_layout.addWidget(self.title_label)
        titles_layout.addWidget(self.favorite_model_btn, 0, Qt.AlignmentFlag.AlignCenter)
        
        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(50, 50)
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            circular_pixmap = make_circular_pixmap(logo_path, 50)
            if circular_pixmap: self.logo_lbl.setPixmap(circular_pixmap)
            self.logo_lbl.setStyleSheet("border: none; background-color: transparent;")
        else:
            self.logo_lbl.setText("S")
            self.logo_lbl.setFont(app_font(20, QFont.Weight.Bold))
            self.logo_lbl.setStyleSheet(f"border: none; border-radius: 25px; background-color: transparent; color: {ACCENT_COLOR};")
            self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
        top_layout.addWidget(self.logo_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(titles_widget, 1)
        top_layout.addWidget(self.update_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(self.menu_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        main_layout.addWidget(top_bar)
        
        self.header_line = QFrame()
        self.header_line.setFrameShape(QFrame.Shape.HLine)
        self.header_line.setFixedHeight(0)
        self.header_line.setStyleSheet("background: transparent; max-height: 0px;")
        main_layout.addWidget(self.header_line)

        self.chat_body = QWidget()
        self.chat_body.setMinimumWidth(0)
        self.chat_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chat_body.setStyleSheet("background: transparent;")
        body_layout = QGridLayout(self.chat_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumWidth(0)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS) 
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_widget = QWidget()
        self.chat_widget.setMinimumWidth(0)
        self.chat_widget.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setContentsMargins(12, 14, 12, 128)
        self.chat_layout.setSpacing(8)
        self.scroll.setWidget(self.chat_widget)
        body_layout.addWidget(self.scroll, 0, 0)

        self.welcome_overlay = QWidget()
        self.welcome_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.welcome_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.welcome_overlay.setStyleSheet("background: transparent; border: none;")
        welcome_layout = QVBoxLayout(self.welcome_overlay)
        welcome_layout.setContentsMargins(24, 42, 24, 146)
        welcome_layout.setSpacing(0)
        welcome_layout.addStretch(1)
        self.welcome_widget = WelcomeWidget()
        welcome_layout.addWidget(self.welcome_widget, 0, Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addStretch(1)
        self.welcome_overlay.hide()
        body_layout.addWidget(self.welcome_overlay, 0, 0)
        
        self.input_overlay = QWidget()
        self.input_overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.input_overlay.setStyleSheet("background: transparent;")
        overlay_layout = QVBoxLayout(self.input_overlay)
        overlay_layout.setContentsMargins(18, 0, 18, 18)
        overlay_layout.setSpacing(4)

        self.status_lbl = QLabel("")
        self.status_lbl.setParent(self.input_overlay)
        self.status_lbl.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 13px; font-weight: 700; padding: 0px 15px 5px 15px;")
        self.status_lbl.setFixedHeight(0)
        self.status_lbl.hide()
        
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)
        
        self.input_frame = PillInputFrame()
        self.input_frame.setMinimumHeight(112)
        self.input_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.input_frame.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.input_frame.apply_theme()
        apply_soft_shadow(self.input_frame, blur=42, y=12, alpha=42)
        input_frame_layout = QVBoxLayout(self.input_frame)
        input_frame_layout.setContentsMargins(10, 8, 12, 8)
        input_frame_layout.setSpacing(4)

        self.attachment_preview = AttachmentPreviewStrip()
        self.attachment_preview.remove_requested.connect(self.remove_pending_attachment)
        input_frame_layout.addWidget(self.attachment_preview)

        self.input_field = ExpandingTextEdit()
        self.input_field.setPlaceholderText("בקש כל דבר")
        self.input_field.setStyleSheet(self._chat_input_stylesheet())
        self.input_field.textChanged.connect(self.on_text_change)
        self.input_field.send_signal.connect(self.send_text)
        self.input_field.files_pasted.connect(self.add_attachment_paths)
        self.input_field.image_pasted.connect(self.add_pasted_image)
        input_frame_layout.addWidget(self.input_field)

        control_row = QHBoxLayout()
        self.quick_control_row = control_row
        control_row.setDirection(QBoxLayout.Direction.LeftToRight)
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(10)

        self.attach_btn = QPushButton("+")
        self.attach_btn.setFixedSize(42, 42)
        self.attach_btn.setToolTip("הוספת קבצים")
        self.attach_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._set_attach_button_icon()
        # Google Drive upload is parked for now; the plus button opens the local file picker directly.
        self.attach_btn.clicked.connect(self.choose_local_attachments)
        
        self.action_btn = QPushButton()
        self.action_btn.setFixedSize(52, 52)
        self.action_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.refresh_themed_icons()
        self.update_action_btn_visuals()
        self.action_btn_host = PinnedActionButtonHost(self.action_btn)
        control_row.addWidget(self.action_btn_host, 0, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Restore the chat-box model picker here if you want it back inside the input controls:
        # self.favorite_model_btn = DropdownPillButton("מודל")
        # self.favorite_model_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        # self.favorite_model_btn.setFixedWidth(168)
        # self.favorite_model_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # self.favorite_model_btn.setStyleSheet(self._quick_input_button_stylesheet())
        # self.favorite_model_btn.clicked.connect(self.show_favorite_model_menu)
        # control_row.addWidget(self.favorite_model_btn, 0, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.autonomy_quick_btn = DropdownPillButton("מאוזן")
        self.autonomy_quick_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.autonomy_quick_btn.setFixedWidth(152)
        self.autonomy_quick_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.autonomy_quick_btn.setStyleSheet(self._quick_input_button_stylesheet())
        self.autonomy_quick_btn.clicked.connect(self.show_quick_autonomy_menu)
        control_row.addWidget(self.autonomy_quick_btn, 0, alignment=Qt.AlignmentFlag.AlignVCenter)

        control_row.addStretch(1)
        control_row.addWidget(self.attach_btn, 0, alignment=Qt.AlignmentFlag.AlignVCenter)
        input_frame_layout.addLayout(control_row)
        self.refresh_quick_autonomy_controls()
        self.refresh_favorite_model_controls()
        QTimer.singleShot(0, self._resize_quick_input_controls)
        
        bottom_layout.addWidget(self.input_frame, alignment=Qt.AlignmentFlag.AlignVCenter)
        overlay_layout.addLayout(bottom_layout)
        body_layout.addWidget(self.input_overlay, 0, 0, Qt.AlignmentFlag.AlignBottom)
        self.input_overlay.raise_()
        self.chat_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.chat_splitter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.chat_splitter.setChildrenCollapsible(False)
        self.chat_splitter.setHandleWidth(7)
        self.canvas_panel = VisualCanvasPanel(self.chat_splitter)
        self.canvas_panel.close_requested.connect(self.close_canvas)
        self.canvas_panel.canvas_action_requested.connect(self.handle_canvas_action)
        self.canvas_panel.canvas_layout_captured.connect(self.handle_canvas_layout)
        self.chat_splitter.addWidget(self.canvas_panel)
        self.chat_splitter.addWidget(self.chat_body)
        self.chat_splitter.splitterMoved.connect(lambda _position, _index: self._schedule_chat_width_refresh())
        self.canvas_panel.hide()
        self.chat_splitter.setSizes([0, max(1, self.width())])
        main_layout.addWidget(self.chat_splitter, 1)
        QTimer.singleShot(0, self._update_chat_bottom_padding)

    def _reset_page_scrolls(self, page):
        if page is None:
            return

        def reset():
            for area in page.findChildren(QScrollArea):
                if area is self.scroll:
                    continue
                area.verticalScrollBar().setValue(area.verticalScrollBar().minimum())
                area.horizontalScrollBar().setValue(area.horizontalScrollBar().minimum())

        QTimer.singleShot(0, reset)

    def show_usage_page(self):
        self._close_canvas_for_secondary_page()
        if self.usage_page is None:
            self.usage_page = UsageStatsPage(self.core, self)
            self.stacked_widget.addWidget(self.usage_page)
        self.usage_page.load_data('today')
        self.stacked_widget.setCurrentWidget(self.usage_page)
        self._reset_page_scrolls(self.usage_page)

    def show_settings_page(self):
        self._close_canvas_for_secondary_page()
        if self.settings_page is None:
            self.settings_page = SettingsPage(self.core, self)
            self.stacked_widget.addWidget(self.settings_page)
        self.settings_page.show_home()
        self.settings_page.ensure_models_loaded()
        self.stacked_widget.setCurrentWidget(self.settings_page)
        self._reset_page_scrolls(self.settings_page)

    def rebuild_settings_page(self):
        if self.settings_page is not None:
            self.stacked_widget.removeWidget(self.settings_page)
            self.settings_page.deleteLater()
            self.settings_page = None
        self.show_settings_page()

    def show_tools_page(self):
        self._close_canvas_for_secondary_page()
        if self.tools_page is not None:
            self.stacked_widget.removeWidget(self.tools_page)
            self.tools_page.deleteLater()
        self.tools_page = ToolsSettingsPage(self.core, self)
        self.stacked_widget.addWidget(self.tools_page)
        self.stacked_widget.setCurrentWidget(self.tools_page)
        self._reset_page_scrolls(self.tools_page)

    def show_task_center_page(self):
        self._close_canvas_for_secondary_page()
        if self.task_center_page is None:
            self.task_center_page = TaskCenterPage(self.core, self)
            self.stacked_widget.addWidget(self.task_center_page)
        self.task_center_page.load_tasks()
        self.stacked_widget.setCurrentWidget(self.task_center_page)
        self._reset_page_scrolls(self.task_center_page)

    def show_trace_page(self):
        self._close_canvas_for_secondary_page()
        if self.trace_page is None:
            self.trace_page = DeveloperTracePage(self.core, self)
            self.stacked_widget.addWidget(self.trace_page)
        self.trace_page.load_trace()
        self.stacked_widget.setCurrentWidget(self.trace_page)
        self._reset_page_scrolls(self.trace_page)

    def show_history_page(self):
        self._close_canvas_for_secondary_page()
        if self.history_page is None:
            self.history_page = ChatHistoryPage(self.core, self)
            self.stacked_widget.addWidget(self.history_page)
        self.history_page.load_sessions()
        self.stacked_widget.setCurrentWidget(self.history_page)
        self._reset_page_scrolls(self.history_page)

    def show_doctor_page(self):
        self._close_canvas_for_secondary_page()
        if self.doctor_page is None:
            self.doctor_page = SmartiDoctorPage(self.core, self)
            self.stacked_widget.addWidget(self.doctor_page)
        self.stacked_widget.setCurrentWidget(self.doctor_page)
        self._reset_page_scrolls(self.doctor_page)

    def show_about_page(self):
        self._close_canvas_for_secondary_page()
        if self.about_page is None:
            self.about_page = AboutPage(self)
            self.stacked_widget.addWidget(self.about_page)
        self.stacked_widget.setCurrentWidget(self.about_page)
        self._reset_page_scrolls(self.about_page)

    def _canvas_screen_geometry(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        # The available work area ends exactly at the Windows taskbar line.
        return screen.availableGeometry() if screen else None

    def _canvas_window_target_geometry(self, size=None):
        available = self._canvas_screen_geometry()
        if not available:
            return None
        target = size or self.size()
        width = min(max(380, target.width()), available.width())
        height = min(max(420, target.height()), available.height())
        geometry = self.geometry()
        frame = self.frameGeometry()
        frame_left_offset = frame.x() - geometry.x()
        frame_top_offset = frame.y() - geometry.y()
        frame_width = width + max(0, frame.width() - geometry.width())
        frame_height = height + max(0, frame.height() - geometry.height())
        desired_frame_x = available.x() + max(0, (available.width() - frame_width) // 2)
        desired_frame_y = available.bottom() - frame_height + 1
        geometry.setWidth(width)
        geometry.setHeight(height)
        geometry.moveTo(desired_frame_x - frame_left_offset, desired_frame_y - frame_top_offset)
        return geometry

    def _schedule_canvas_taskbar_alignment(self):
        if self._canvas_taskbar_alignment_scheduled:
            return
        self._canvas_taskbar_alignment_scheduled = True

        def align():
            self._canvas_taskbar_alignment_scheduled = False
            self._align_canvas_frame_to_taskbar()

        # On Windows frame margins are finalized just after a top-level window
        # becomes visible or changes size. A delayed correction makes the outer
        # frame, not merely the client area, sit on the work-area edge.
        QTimer.singleShot(0, align)
        QTimer.singleShot(120, align)

    def _align_canvas_frame_to_taskbar(self):
        if self.isMaximized() or self.isFullScreen():
            return
        available = self._canvas_screen_geometry()
        if not available:
            return
        frame = self.frameGeometry()
        desired_x = available.x() + max(0, (available.width() - frame.width()) // 2)
        desired_y = available.bottom() - frame.height() + 1
        dx = desired_x - frame.x()
        dy = desired_y - frame.y()
        if dx or dy:
            self.move(self.x() + dx, self.y() + dy)

    def _pin_window_bottom_center(self, size=None):
        target = self._canvas_window_target_geometry(size)
        if target is None:
            return
        self.setGeometry(target)
        self._align_canvas_frame_to_taskbar()

    def open_canvas(self, artifact):
        artifact = normalize_canvas_artifact(artifact)
        if not artifact:
            QMessageBox.warning(self, "קנבס מתקדם", "נתוני הקנבס שנשמרו בשיחה אינם תקינים.")
            return
        if not web_canvas_available():
            QMessageBox.information(self, "קנבס מתקדם", "כדי לפתוח את הקנבס יש להתקין את PyQt6-WebEngine. השיחה נשארת זמינה.")
            return
        if not self._canvas_expanded:
            self._compact_window_size = QSize(self.width(), self.height())
            self.setUpdatesEnabled(False)
            try:
                self._canvas_expanded = True
                self.canvas_panel.show()
                available = self._canvas_screen_geometry()
                if available:
                    width = min(1220, max(820, available.width() - 32))
                    height = min(760, max(620, available.height() - 32))
                    self._pin_window_bottom_center(QSize(width, height))
                self._set_expanded_canvas_sizes()
            finally:
                self.setUpdatesEnabled(True)
                self.update()
        allow_remote_images = bool(
            self.core.settings.get("enable_visual_surfaces", False)
            and self.core.settings.get("enable_web_canvas", False)
            and self.core.settings.get("enable_canvas_remote_images", False)
        )
        self.canvas_panel.show_canvas(artifact, allow_remote_images=allow_remote_images)
        self.canvas_panel.show()
        self._schedule_chat_width_refresh()
        self._schedule_scroll_last_user_to_view_top(delays=(0, 100))

    def close_canvas(self):
        if not getattr(self, "_canvas_expanded", False):
            return
        self.setUpdatesEnabled(False)
        try:
            self.canvas_panel.hide()
            self._canvas_expanded = False
            compact = self._compact_window_size or QSize(450, 760)
            self._pin_window_bottom_center(compact)
            self._set_compact_chat_sizes()
        finally:
            self.setUpdatesEnabled(True)
            self.update()
        self._schedule_chat_width_refresh()

    def _close_canvas_for_secondary_page(self):
        if self._canvas_expanded:
            self.close_canvas()

    def _set_expanded_canvas_sizes(self):
        if not hasattr(self, "chat_splitter"):
            return
        self.chat_splitter.setSizes([int(self.width() * 0.62), int(self.width() * 0.38)])
        self._schedule_chat_width_refresh()

    def _set_compact_chat_sizes(self):
        if not hasattr(self, "chat_splitter"):
            return
        self.chat_splitter.setSizes([0, max(1, self.width())])
        self._schedule_chat_width_refresh()

    def handle_canvas_action(self, payload):
        if not isinstance(payload, dict):
            return
        try:
            encoded = json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError):
            return
        if len(encoded) > 20_000:
            QMessageBox.warning(self, "קנבס מתקדם", "הפעולה מהקנבס גדולה מדי לשליחה לסוכן.")
            return
        canvas_id = self.canvas_panel.canvas_id() if hasattr(self, "canvas_panel") else ""
        message = f"[נתוני משתמש מהקנבס {canvas_id}]\n{encoded}"
        if self.agent_running:
            self.input_field.setPlainText(message)
            self.input_field.setFocus()
            return
        self.add_message(message, is_user=True, anchor_user=True)
        self.process_request(message)

    def handle_canvas_layout(self, payload):
        if not isinstance(payload, dict) or not hasattr(self, "canvas_panel"):
            return
        buttons = payload.get("buttons")
        canvas_id = self.canvas_panel.canvas_id()
        if not canvas_id or not isinstance(buttons, list):
            return
        cleaned_buttons = []
        for index, button in enumerate(buttons[:80]):
            if not isinstance(button, dict):
                continue
            item = {
                "id": str(button.get("id") or f"dom-button-{index + 1}")[:80],
                "label": str(button.get("label") or "")[:160],
            }
            for key in ("x", "y", "width", "height"):
                try:
                    item[key] = round(float(button.get(key, 0)), 2)
                except (TypeError, ValueError):
                    item[key] = 0.0
            cleaned_buttons.append(item)
        self._pending_canvas_layout = (canvas_id, cleaned_buttons)
        if self._canvas_layout_save_scheduled:
            return
        self._canvas_layout_save_scheduled = True
        QTimer.singleShot(450, self._save_canvas_layout)

    def _save_canvas_layout(self):
        self._canvas_layout_save_scheduled = False
        item = self._pending_canvas_layout
        self._pending_canvas_layout = None
        if not item:
            return
        canvas_id, buttons = item
        try:
            self.core.update_canvas_layout(canvas_id, buttons)
        except Exception as exc:
            logging.warning("Canvas layout persistence failed: %s", exc)

    def _latest_assistant_canvases(self):
        for message in reversed(self.core.active_chat_messages()):
            if message.get("role") != "assistant":
                continue
            metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
            canvases = metadata.get("canvases", []) if isinstance(metadata, dict) else []
            return canvases if isinstance(canvases, list) else []
        return []

    def bring_to_front(self):
        self._clear_taskbar_attention()
        if hasattr(self, "quick_reply_toast"):
            self.quick_reply_toast.hide()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.show()
        self.activateWindow()
        self.raise_()
        if hasattr(self, "voice_overlay") and self.voice_overlay.isVisible():
            QTimer.singleShot(0, self.voice_overlay.position_near_owner)

    def _request_taskbar_attention(self):
        if self._should_notify_user() and hasattr(self, "taskbar_attention"):
            self.taskbar_attention.request_attention()

    def _clear_taskbar_attention(self):
        if hasattr(self, "taskbar_attention"):
            self.taskbar_attention.stop()

    def handle_notification_reply(self, text):
        self._clear_taskbar_attention()
        self.submit_quick_reply(text)

    def handle_notification_activation(self):
        self._clear_taskbar_attention()
        self.bring_to_front()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._clear_taskbar_attention()
        if event.type() in (QEvent.Type.ActivationChange, QEvent.Type.WindowStateChange):
            if hasattr(self, "voice_overlay") and self.voice_overlay.isVisible():
                QTimer.singleShot(0, self.voice_overlay.position_near_owner)

    def closeEvent(self, event):
        if getattr(self, "_quit_requested", False) or not self.core.settings.get("keep_running_in_tray", True):
            self.unregister_voice_hotkey()
            if hasattr(self, "voice_overlay"):
                self.voice_overlay.hide()
            if hasattr(self, "tray_icon"):
                self.tray_icon.hide()
            event.accept()
            return
        event.ignore()
        self.hide()
        if hasattr(self, "voice_overlay") and self.voice_overlay.isVisible():
            QTimer.singleShot(0, self.voice_overlay.position_near_owner)

    def _plain_notification_text(self, text, limit=520):
        cleaned = html.unescape(str(text or ""))
        cleaned = re.sub(r"```.*?```", "קטע קוד", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > limit:
            cleaned = cleaned[:max(0, limit - 3)].rstrip() + "..."
        return cleaned or "סמארטי השיב."

    def show_response_notification(self, response):
        tray_preview = self._plain_notification_text(response, 240)
        self._request_taskbar_attention()
        try:
            if hasattr(self, "notifications"):
                self.notifications.show_response(response)
                return
            self.tray_icon.showMessage(SMARTI_APP_DISPLAY_NAME, tray_preview, QSystemTrayIcon.MessageIcon.Information, 7000)
        except Exception as e:
            logging.warning(f"Tray notification failed: {e}")

    def handle_core_notification(self, kind, payload):
        payload = payload or {}
        if not hasattr(self, "notifications"):
            return
        if kind == "toast":
            self._request_taskbar_attention()
            self.notifications.show_notice(
                payload.get("title") or SMARTI_APP_DISPLAY_NAME,
                payload.get("body") or payload.get("message") or "",
                kind=payload.get("kind") or "default",
                open_button=payload.get("open_button", True),
            )
            return
        if kind == "background_task_finished":
            task = payload.get("task") or {}
            result = payload.get("result") or task.get("last_result") or ""
            is_reminder = task.get("kind") == "reminder"
            session_id = payload.get("session_id") or ""
            active_session = self.core.active_chat_session()
            active_sess_id = active_session.get("id") if active_session else None
            
            if not is_reminder and active_sess_id == session_id and not self._should_notify_user():
                return
            
            self._request_taskbar_attention()
            title = task.get("title") or ("תזכורת מסמארטי" if is_reminder else "משימת רקע הסתיימה")
            body = result or task.get("message") or task.get("prompt") or "המשימה הסתיימה."
            if not is_reminder and session_id:
                self.notifications.show_background_task_notification(title, body, session_id)
            else:
                self.notifications.show_notice(title, body, kind="reminder" if is_reminder else "default")

    def handle_background_task_start(self, session_id, task_id, prompt):
        active_sess = self.core.active_chat_session()
        active_sess_id = active_sess.get("id") if active_sess else None
        if active_sess_id == session_id:
            user_container = self.add_message(prompt, is_user=True, is_background_task=True)
            available_width = self.scroll.viewport().width() or self.width()
            container = ChatMessageContainer(
                "",
                is_user=False,
                parent_width=available_width,
                is_background_task=True,
                parent=self.chat_widget,
            )
            self._wire_message_container(container)
            self.chat_layout.addWidget(container)
            self._background_task_containers[task_id] = (user_container, container)
            self._schedule_scroll_last_user_to_view_top()

    def handle_background_task_step(self, task_id, event):
        if task_id in self._background_task_containers:
            _, container = self._background_task_containers[task_id]
            changed = container.bubble.handle_agent_event(event)
            if changed:
                container.bubble.show()
                container.reveal_with_entry_animation()
                self._schedule_scroll_last_user_to_view_top(delays=(50, 160))

    def handle_background_task_finish(self, session_id, task_id, result, success):
        if task_id in self._background_task_containers:
            _, container = self._background_task_containers.pop(task_id, (None, None))
            if container:
                container.bubble.set_final_text(result)
                container.bubble.apply_theme()
                container.reveal_with_entry_animation()
                self._schedule_scroll_last_user_to_view_top(delays=(50, 160))

    def handle_conversation_switch_requested(self, session_id):
        if self.agent_running:
            QMessageBox.information(self, "שיחה פעילה", "אי אפשר להחליף שיחה בזמן שסמארטי עדיין עובד.")
            return
        if self.core.activate_chat_session(session_id):
            self.load_active_chat_session()
            self.refresh_chat_title()
            self.stacked_widget.setCurrentWidget(self.chat_page)
            self.bring_to_front()

    def submit_quick_reply(self, text):
        text = str(text or "").strip()
        if not text:
            return
        if self.agent_running:
            self.input_field.setPlainText(text)
            self.bring_to_front()
            return
        self.core.stop_speaking()
        self.add_message(text, is_user=True, anchor_user=True)
        self.process_request(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self._schedule_chat_width_refresh()
            self._resize_quick_input_controls()
            self._update_chat_bottom_padding()
            if hasattr(self, "voice_overlay") and self.voice_overlay.isVisible():
                self.voice_overlay.position_near_owner()
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        # The native frame margins only become final after the first show on
        # Windows. Align once more then so no edge can slip under the taskbar.
        self._schedule_canvas_taskbar_alignment()

    def _schedule_chat_width_refresh(self):
        QTimer.singleShot(0, self._refresh_chat_message_widths)
        QTimer.singleShot(100, self._refresh_chat_message_widths)

    def _refresh_chat_message_widths(self):
        if not hasattr(self, "scroll"):
            return
        available_width = self.scroll.viewport().width() or getattr(self, "chat_body", self).width() or self.width()
        if available_width <= 0:
            return
        for bubble in self.findChildren(MessageBubble):
            bubble.update_parent_width(available_width)
        if hasattr(self, "chat_widget"):
            self.chat_widget.updateGeometry()
            self.chat_widget.adjustSize()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "voice_overlay") and self.voice_overlay.isVisible():
            QTimer.singleShot(0, self.voice_overlay.position_near_owner)

    def _set_welcome_visible(self, visible, refresh_text=False):
        if not hasattr(self, "welcome_overlay") or not hasattr(self, "welcome_widget"):
            return
        if visible and refresh_text:
            self.welcome_widget.refresh_text()
        self.welcome_overlay.setVisible(bool(visible))
        if visible:
            self.welcome_overlay.raise_()
            if hasattr(self, "input_overlay"):
                self.input_overlay.raise_()

    def _update_chat_bottom_padding(self):
        if not hasattr(self, "chat_layout") or not hasattr(self, "input_overlay"):
            return
        margins = self.chat_layout.contentsMargins()
        overlay_h = max(112, self.input_overlay.sizeHint().height() + 22)
        if margins.bottom() != overlay_h:
            self.chat_layout.setContentsMargins(margins.left(), margins.top(), margins.right(), overlay_h)

    def _scroll_container_to_view_top(self, container):
        if not container or not hasattr(self, "scroll") or not hasattr(self, "chat_widget"):
            return
        try:
            self._update_chat_bottom_padding()
            self.chat_widget.adjustSize()
            bar = self.scroll.verticalScrollBar()
            y = container.mapTo(self.chat_widget, QPoint(0, 0)).y()
            bar.setValue(max(bar.minimum(), min(y, bar.maximum())))
        except RuntimeError:
            pass
        except Exception as exc:
            logging.debug("Failed to align chat scroll anchor: %s", exc)

    def _schedule_scroll_container_to_view_top(self, container, delays=(0, 60, 180)):
        if not container:
            return
        for delay in delays:
            QTimer.singleShot(int(delay), lambda c=container: self._scroll_container_to_view_top(c))

    def _schedule_scroll_last_user_to_view_top(self, delays=(0, 60, 180)):
        self._schedule_scroll_container_to_view_top(getattr(self, "_last_user_anchor_container", None), delays)

    def on_tts_status(self, is_playing):
        self.tts_active = bool(is_playing)
        if not is_playing and not (self.tts_thread and self.tts_thread.isRunning()):
            self.active_tts_container = None
        self._refresh_message_tts_buttons()

    def _wire_message_container(self, container):
        container.tts_button_clicked.connect(self.handle_message_tts_button)
        container.canvas_open_requested.connect(self.open_canvas)
        container.update_tts_button_state(False, self.tts_active)

    def _refresh_message_tts_buttons(self):
        for container in self.findChildren(ChatMessageContainer):
            if container.is_user:
                continue
            active = self.tts_active and container is self.active_tts_container
            blocked = self.tts_active and container is not self.active_tts_container
            container.update_tts_button_state(active, blocked)

    def handle_message_tts_button(self, container):
        if container is self.active_tts_container and self.tts_active:
            self.core.stop_speaking()
            self.tts_active = False
            self.active_tts_container = None
            self._refresh_message_tts_buttons()
            return
        if self.tts_active:
            return
        self.start_message_tts(container)

    def start_message_tts(self, container):
        if not container or container.is_user:
            return
        text = container.bubble.final_plain_text()
        if not str(text or "").strip():
            return
        self.active_tts_container = container
        self.tts_active = True
        self._refresh_message_tts_buttons()
        worker = TTSWorker(self.core, text)
        self.tts_thread = worker
        self._tts_workers.append(worker)
        worker.finished.connect(lambda w=worker: self._on_message_tts_finished(w))
        worker.start()

    def _on_message_tts_finished(self, worker):
        try:
            self._tts_workers.remove(worker)
        except ValueError:
            pass
        if worker is self.tts_thread:
            self.tts_thread = None
            self.tts_active = False
            self.active_tts_container = None
            self._refresh_message_tts_buttons()

    def _clear_menu_reopen_guard(self):
        self._suppress_menu_open_once = False

    def _menu_button_contains_cursor(self):
        return self.menu_btn.rect().contains(self.menu_btn.mapFromGlobal(QCursor.pos()))

    def _guard_menu_reopen_from_button(self):
        if self._menu_button_contains_cursor():
            self._suppress_menu_open_once = True
            QTimer.singleShot(220, self._clear_menu_reopen_guard)

    def show_menu(self):
        if self._suppress_menu_open_once:
            self._suppress_menu_open_once = False
            return
        if self.menu.isVisible():
            self._suppress_menu_open_once = True
            self.menu.hide()
            QTimer.singleShot(220, self._clear_menu_reopen_guard)
            return
        self.menu.exec(self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height())))

    def show_attachment_menu(self):
        # Kept as a compatibility shim for older signal wiring; no menu is shown.
        self.choose_local_attachments()

    def _active_attachment_dir(self):
        try:
            session = self.core.active_chat_session() or {}
            return attachment_cache_dir(session.get("id", "current"))
        except Exception:
            return attachment_cache_dir("current")

    def add_attachment_paths(self, paths):
        new_items = []
        for path in paths or []:
            item = attachment_from_path(path, source="local")
            if item:
                new_items.append(item)
        if not new_items:
            return
        self.pending_attachments = merge_conversation_attachments(self.pending_attachments, new_items, 30)
        self.refresh_pending_attachments()

    def add_pasted_image(self, image):
        try:
            if image is None or image.isNull():
                return
            directory = self._active_attachment_dir()
            path = os.path.join(directory, f"pasted-{int(time.time())}-{uuid.uuid4().hex[:6]}.png")
            os.makedirs(directory, exist_ok=True)
            if image.save(path, "PNG"):
                item = attachment_from_path(path, source="clipboard", original_name=os.path.basename(path))
                if item:
                    self.pending_attachments = merge_conversation_attachments(self.pending_attachments, [item], 30)
                    self.refresh_pending_attachments()
        except Exception as e:
            QMessageBox.warning(self, "שגיאה בהדבקת תמונה", str(e))

    def remove_pending_attachment(self, attachment):
        item = normalize_attachment(attachment)
        if not item:
            return
        remove_id = item.get("id")
        remove_path = item.get("path", "").lower()
        self.pending_attachments = [
            current for current in normalize_attachments(self.pending_attachments)
            if current.get("id") != remove_id and current.get("path", "").lower() != remove_path
        ]
        self.refresh_pending_attachments()

    def refresh_pending_attachments(self):
        self.pending_attachments = normalize_attachments(self.pending_attachments)
        if hasattr(self, "attachment_preview"):
            self.attachment_preview.set_attachments(self.pending_attachments)
        self.update_action_btn_visuals()
        QTimer.singleShot(0, self._update_chat_bottom_padding)

    def choose_local_attachments(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "הוסף תמונות וקבצים",
            os.path.expanduser("~"),
            "All files (*.*)"
        )
        self.add_attachment_paths(paths)

    def _show_drive_setup_message(self, text, offer_settings=True):
        # Google Drive upload is parked until OAuth sign-in is reworked.
        return

    def ensure_google_drive_connected(self):
        # Google Drive upload is parked until OAuth sign-in is reworked.
        return False

    def choose_drive_attachments(self):
        # Google Drive upload is parked until OAuth sign-in is reworked.
        return

    def update_action_btn_visuals(self):
        try: self.action_btn.clicked.disconnect()
        except: pass

        if self.agent_running:
            self.action_btn.setToolTip("עצור פעולה")
            set_themed_button_icon(self.action_btn, ("stop_agent_icon",), "■", 28, clear_text=True)
            border_css = "border: 1px solid rgba(136,255,184,0.44); border-radius: 26px;"
            bg_color = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR})"
            fg_color = ACCENT_TEXT_COLOR
            hover_bg = f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR})"
            pressed_bg = ACCENT_PINK_COLOR
            self.action_btn.clicked.connect(self.cancel_agent)
        else:
            has_text = bool(self.input_field.toPlainText().strip()) or bool(getattr(self, "pending_attachments", []))
            self.action_btn.setToolTip("שלח הודעה" if has_text else "התחל האזנה")
            fallback_text = "שלח" if has_text else "קול"

            set_themed_button_icon(self.action_btn, ("send_icon",) if has_text else ("mic_icon",), fallback_text, 28, clear_text=True)
            border_css = f"border: 1px solid {LINE_COLOR if has_text else SOFT_LINE_COLOR}; border-radius: 26px;"
            bg_color = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_COLOR}, stop:0.58 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR})"
                if has_text else GLASS_COLOR
            )
            fg_color = ACCENT_TEXT_COLOR if has_text else ACCENT_COLOR
            hover_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {BRAND_ACCENT_COLOR}, stop:0.58 {BRAND_PINK_COLOR}, stop:1 {BRAND_SECONDARY_COLOR})"
                if has_text else HOVER_TINT
            )
            pressed_bg = ACCENT_TINT_STRONG
            
            if has_text: self.action_btn.clicked.connect(self.send_text)
            else: self.action_btn.clicked.connect(self.start_voice)

        self.action_btn.setStyleSheet(
            f"QPushButton {{ background: {bg_color}; {border_css} padding: 0px; "
            f"color: {fg_color}; font-size: 18px; font-weight: 700; outline: none; }}"
            f"QPushButton:hover {{ background: {hover_bg}; }}"
            f"QPushButton:pressed {{ background: {pressed_bg}; }}"
            f"QPushButton:disabled {{ color: {SUBTLE_TEXT_COLOR}; background: transparent; }}"
        )
        self.action_btn.setGraphicsEffect(None)

    def cancel_agent(self):
        self.core.request_cancel()
        self.status_lbl.setText("עוצר מיד...")
        self.action_btn.setEnabled(False)
        self.update_action_btn_visuals()

    def on_text_change(self):
        self.update_action_btn_visuals()
        QTimer.singleShot(0, self._update_chat_bottom_padding)

    def add_message(self, text, is_user, show_actions=True, attachments=None, canvases=None, anchor_user=False, is_background_task=False, animate=True):
        attachments = normalize_attachments(attachments or [])
        if not text and is_user and not attachments: return
        self._set_welcome_visible(False)
        available_width = self.scroll.viewport().width() or self.width()
        container = ChatMessageContainer(
            text,
            is_user,
            available_width,
            show_actions=show_actions,
            attachments=attachments,
            canvases=canvases,
            is_background_task=is_background_task,
            parent=self.chat_widget,
        )
        self._wire_message_container(container)
        self.chat_layout.addWidget(container)
        if animate:
            QTimer.singleShot(0, container.start_entry_animation)
        else:
            container.finish_entry_without_animation()
        if is_user and anchor_user:
            self._last_user_anchor_container = container
            self._schedule_scroll_container_to_view_top(container)
        return container

    def send_text(self):
        text = self.input_field.toPlainText().strip()
        attachments = normalize_attachments(getattr(self, "pending_attachments", []))
        if not text and not attachments: return
        self.input_field.clear()
        self.pending_attachments = []
        self.refresh_pending_attachments()
        self.core.stop_speaking() 
        self.add_message(text, is_user=True, attachments=attachments, anchor_user=True)
        self.process_request(text, attachments=attachments)

    def trigger_voice_from_hotkey(self):
        if self.agent_running:
            return
        was_hidden = not self.isVisible()
        if was_hidden:
            self.start_new_chat()
        QTimer.singleShot(0, self.start_voice)

    def on_voice_status(self, status):
        status = str(status or "")
        self.status_lbl.setText(status)
        if hasattr(self, "voice_overlay"):
            self.voice_overlay.set_status(status)
            self.voice_overlay.position_near_owner()

    def cancel_voice(self):
        worker = getattr(self, "voice_thread", None)
        if worker and worker.isRunning():
            try:
                worker.request_stop()
            except Exception:
                pass
            if hasattr(self, "voice_overlay"):
                self.voice_overlay.set_status("מפסיק האזנה...")
                self.voice_overlay.set_cancel_enabled(False)
            self.status_lbl.setText("מפסיק האזנה...")
        else:
            if hasattr(self, "voice_overlay"):
                self.voice_overlay.hide_listening()

    def start_voice(self):
        if self.agent_running:
            return
        if getattr(self, "voice_thread", None) and self.voice_thread.isRunning():
            return
        self.core.stop_speaking() 
        self.status_lbl.setText("מפעיל האזנה...")
        if hasattr(self, "voice_overlay"):
            self.voice_overlay.set_status("מפעיל האזנה...")
            self.voice_overlay.show_listening(self)
        self.input_field.setEnabled(False)
        self.action_btn.setEnabled(False)
        self.voice_thread = VoiceWorker(self.core.settings)
        self.voice_thread.status_signal.connect(self.on_voice_status)
        self.voice_thread.finished_signal.connect(self.on_voice_finished)
        self.voice_thread.start()

    def on_voice_finished(self, text):
        self.voice_thread = None
        self.status_lbl.setText("")
        if hasattr(self, "voice_overlay"):
            self.voice_overlay.hide_listening()
        self.input_field.setEnabled(True)
        self.action_btn.setEnabled(True)
        self.update_action_btn_visuals()
        if text:
            self.add_message(text, is_user=True, anchor_user=True)
            self.process_request(text, is_voice=True)

    def process_request(self, text, is_voice=False, attachments=None):
        self.current_request_is_voice = is_voice
        self.status_lbl.setText("חושב...")
        self.input_field.setEnabled(False)
        self.agent_running = True
        self.update_action_btn_visuals()
        
        available_width = self.scroll.viewport().width() or self.width()
        self.current_agent_container = ChatMessageContainer(
            "",
            is_user=False,
            parent_width=available_width,
            parent=self.chat_widget,
        )
        self._wire_message_container(self.current_agent_container)
        self.current_agent_bubble = self.current_agent_container.bubble
        self.chat_layout.addWidget(self.current_agent_container)
        self.current_agent_container.hide() 
        self._schedule_scroll_last_user_to_view_top()
        pending_bubble = self.current_agent_bubble
        QTimer.singleShot(
            self.INITIAL_THINKING_DELAY_MS,
            lambda bubble=pending_bubble: self._show_delayed_initial_thinking(bubble),
        )
        
        self.agent_thread = AgentWorker(self.core, text, attachments=attachments)
        self.agent_thread.status_signal.connect(lambda s: self.status_lbl.setText(s))
        self.agent_thread.ask_confirm_signal.connect(self.show_confirm_dialog) 
        self.agent_thread.api_key_required_signal.connect(self.show_api_key_dialog)
        self.agent_thread.step_signal.connect(self.on_agent_step)
        self.agent_thread.finished_signal.connect(self.on_agent_finished)
        self.agent_thread.start()

    def _show_delayed_initial_thinking(self, bubble):
        """Reveal a non-blocking response indicator only for a still-running request."""
        if (
            not self.agent_running
            or bubble is None
            or bubble is not self.current_agent_bubble
            or not self.current_agent_container
        ):
            return
        if bubble.show_initial_thinking():
            bubble.show()
            self.current_agent_container.reveal_with_entry_animation()
            self._schedule_scroll_last_user_to_view_top(delays=(50, 160))

    def on_agent_step(self, step_text):
        if self.current_agent_bubble:
            changed = self.current_agent_bubble.handle_agent_event(step_text)
            if changed and self.current_agent_container:
                self.current_agent_bubble.show()
                self.current_agent_container.reveal_with_entry_animation()
                self._schedule_scroll_last_user_to_view_top(delays=(50, 160))

    def show_confirm_dialog(self, title, text, risk="medium"):
        dlg = ActionConfirmDialog(title, text, risk, self)
        notify_user = self._should_notify_user() and hasattr(self, "notifications")
        if notify_user:
            dlg.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        loop = QEventLoop(self)
        state = {"settled": False, "result": False, "notification_value": "pending"}
        notification_handle = {"value": None}
        try:
            timeout_seconds = max(0, int(self.core.settings.get("permission_notification_timeout_seconds", 0) or 0))
        except Exception:
            timeout_seconds = 0
        deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None

        def cancel_notification():
            handle = notification_handle.get("value")
            if handle:
                try:
                    handle.cancel()
                except Exception:
                    pass
                notification_handle["value"] = None

        def finish(approved, source):
            if state["settled"]:
                return
            state["settled"] = True
            state["result"] = bool(approved)
            self._clear_taskbar_attention()
            if source != "notification":
                cancel_notification()
            if source != "dialog":
                try:
                    dlg.done(QDialog.DialogCode.Accepted if approved else QDialog.DialogCode.Rejected)
                except Exception:
                    pass
            loop.quit()

        def dialog_accepted():
            finish(True, "dialog")

        def dialog_rejected():
            finish(False, "dialog")

        dlg.accepted.connect(dialog_accepted)
        dlg.rejected.connect(dialog_rejected)

        def answered(value):
            state["notification_value"] = value

        if notify_user:
            self._request_taskbar_attention()
            try:
                notification_handle["value"] = self.notifications.show_permission_request(title, text, risk, callback=answered)
            except Exception:
                notification_handle["value"] = None

        poll = QTimer(self)

        def maybe_finish():
            notification_value = state.get("notification_value", "pending")
            if notification_value != "pending":
                state["notification_value"] = "pending"
                if notification_value is not None:
                    finish(bool(notification_value), "notification")
                    return
            try:
                if self.core._is_cancel_requested():
                    finish(False, "cancel")
                    return
            except Exception:
                pass
            if deadline is not None and notification_handle.get("value") and time.monotonic() >= deadline:
                cancel_notification()

        poll.timeout.connect(maybe_finish)
        poll.start(100)
        dlg.open()
        loop.exec()
        poll.stop()
        poll.deleteLater()
        cancel_notification()
        self.agent_thread.confirm_result = bool(state["result"])
        self.agent_thread.confirm_event.set()

    def _should_notify_user(self):
        return (not self.isVisible()) or self.isMinimized() or (not self.isActiveWindow())

    def show_api_key_dialog(self, secret_key, provider_label, title, message, help_url):
        if self._should_notify_user() and hasattr(self, "notifications"):
            self._request_taskbar_attention()
            self.notifications.show_notice(
                title or "נדרשת הגדרת מפתח API",
                message or f"סמארטי צריך מפתח עבור {provider_label}.",
                kind="important",
            )
        dlg = ApiKeyRequiredDialog(secret_key, provider_label, title, message, help_url, self)
        self.agent_thread.api_key_result = dlg.api_key() if dlg.exec() == QDialog.DialogCode.Accepted else ""
        self.agent_thread.api_key_event.set()

    def on_agent_finished(self, response):
        should_notify = self._should_notify_user()
        self.agent_running = False
        self.action_btn.setEnabled(True)
        self.update_action_btn_visuals()
        self.status_lbl.setText("")
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        response_container = None
        response_canvases = self._latest_assistant_canvases() if not response.startswith("ERROR_USER:") else []
        
        if response.startswith("ERROR_USER:"):
            msg = f"שגיאה: {response.replace('ERROR_USER:', '').strip()}"
            if self.current_agent_bubble:
                self.current_agent_bubble.show()
                self.current_agent_bubble.set_final_text(msg)
                if self.current_agent_container:
                    self.current_agent_container.reveal_with_entry_animation()
            else: self.add_message(msg, is_user=False)
        else:
            if self.current_agent_bubble:
                self.current_agent_bubble.show()
                self.current_agent_bubble.set_final_text(response)
                self.current_agent_bubble.set_canvas_artifacts(response_canvases)
                if self.current_agent_container:
                    self.current_agent_container.reveal_with_entry_animation()
                response_container = self.current_agent_container
            else:
                response_container = self.add_message(response, is_user=False, canvases=response_canvases)
                
            if should_notify:
                self.show_response_notification(response)
                
            if self.core.settings.get("read_aloud_all", False) or (self.core.settings.get("read_aloud_voice_only", True) and getattr(self, 'current_request_is_voice', False)):
                self.start_message_tts(response_container)
                
        self.current_agent_bubble = None
        self.current_agent_container = None
        if self.history_page is not None:
            self.history_page.load_sessions()
        self.refresh_chat_title()
        self._schedule_scroll_last_user_to_view_top(delays=(0, 80, 220))

    def _clear_chat_widgets(self):
        self.core.stop_speaking()
        self.tts_active = False
        self.active_tts_container = None
        self._last_user_anchor_container = None
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            layout = item.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget:
                        child_widget.deleteLater()
                layout.deleteLater()

    def _is_welcome_history_message(self, message):
        if not isinstance(message, dict):
            return False
        metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
        return metadata.get("kind") == "welcome" or metadata.get("ui_only") is True

    def load_active_chat_session(self):
        self._chat_load_generation = int(getattr(self, "_chat_load_generation", 0) or 0) + 1
        generation = self._chat_load_generation
        self._clear_chat_widgets()
        messages = self.core.active_chat_messages()
        visible_messages = []
        for message in messages:
            role = message.get("role")
            content = str(message.get("content", "") or "")
            metadata = message.get("metadata", {}) if isinstance(message.get("metadata", {}), dict) else {}
            attachments = normalize_attachments(metadata.get("attachments", []))
            if role not in {"user", "assistant"} or self._is_welcome_history_message(message):
                continue
            if not content.strip() and not attachments:
                continue
            visible_messages.append((role, content, metadata, attachments))

        if not visible_messages:
            self._set_welcome_visible(True, refresh_text=True)
            self.refresh_chat_title()
            return

        self._set_welcome_visible(False)
        self.refresh_chat_title()

        def add_batch(index=0, batch_size=8):
            if generation != getattr(self, "_chat_load_generation", None):
                return
            for role, content, metadata, attachments in visible_messages[index:index + batch_size]:
                is_bg = bool(metadata.get("triggered_by_background"))
                container = self.add_message(
                    content,
                    is_user=(role == "user"),
                    attachments=attachments,
                    canvases=metadata.get("canvases", []) if role == "assistant" else None,
                    is_background_task=is_bg,
                    animate=False,
                )
                if role == "assistant" and container and isinstance(metadata.get("agent_process"), dict):
                    container.bubble.restore_agent_process(metadata.get("agent_process"))
            next_index = index + batch_size
            if next_index < len(visible_messages):
                QTimer.singleShot(8, lambda: add_batch(next_index, batch_size))
            else:
                QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

        QTimer.singleShot(0, add_batch)

    def start_new_chat(self):
        if self.agent_running:
            QMessageBox.information(self, "שיחה פעילה", "אי אפשר להתחיל שיחה חדשה בזמן שסמארטי עדיין עובד.")
            return
        self.core.start_new_chat_session()
        logging.info(f"\n{'='*50}\n--- תחילת שיחה חדשה ---\n{'='*50}")
        self.load_active_chat_session()
        self.stacked_widget.setCurrentWidget(self.chat_page)
        self.refresh_chat_title()
        if self.history_page is not None:
            self.history_page.load_sessions()

    def clear_chat(self):
        self.start_new_chat()

class AnimatedSplash(QWidget):
    STATUS_MESSAGES = [
        "מכין את חלון הפתיחה...",
    ]

    def __init__(self, fallback_path, size, border_color, border_width, radius, bg_color):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setWindowOpacity(1.0)

        if isinstance(size, QSize):
            splash_size = size
        else:
            base = max(220, int(size or 220))
            splash_size = QSize(max(460, base * 2 + 42), max(286, base + 84))
        self.setFixedSize(splash_size)
        self._window_radius = max(1, int(radius or 30))

        self._status_index = 0
        self._status_timer = None
        self._finish_window = None
        self._finishing = False
        self._finish_progress_anim = None
        self._fade_anim = None
        self._progress_ticks = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("SplashCard")
        self.card.setFrameShape(QFrame.Shape.NoFrame)
        self.card.setLineWidth(0)
        self.card.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(36, 30, 36, 30)
        card_layout.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(16)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(76, 76)
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_splash_logo(fallback_path, border_color)
        top_row.addWidget(self.logo_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)
        self.title_lbl = QLabel(SMARTI_APP_DISPLAY_NAME)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.subtitle_lbl = QLabel("סוכן AI חכם ל-Windows")
        self.subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.meta_lbl = QLabel(self._meta_text())
        self.meta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_col.addStretch(1)
        title_col.addWidget(self.title_lbl)
        title_col.addWidget(self.subtitle_lbl)
        title_col.addWidget(self.meta_lbl)
        title_col.addStretch(1)
        top_row.addLayout(title_col, 1)
        card_layout.addLayout(top_row)

        card_layout.addStretch(1)

        self.status_lbl = QLabel(self.STATUS_MESSAGES[0])
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(7)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(7)
        apply_soft_shadow(self.progress_bar, blur=18, y=0, alpha=105, color=ACCENT_PINK_COLOR)
        card_layout.addWidget(self.progress_bar)

        self.apply_theme()

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_timer.start(90)

    def _meta_text(self):
        runtime_label = "מקור"
        try:
            if SMARTI_RUNTIME.is_frozen:
                runtime_label = "נייד" if os.path.exists(os.path.join(SMARTI_RUNTIME.install_dir, "release_manifest.json")) else "מותקן"
        except Exception:
            runtime_label = "ארוז" if getattr(SMARTI_RUNTIME, "is_frozen", False) else "מקור"
        return f"גרסה {APP_VERSION} • {runtime_label} • Windows"

    def set_status(self, text):
        text = str(text or "").strip()
        if text:
            self.status_lbl.setText(text)
            QApplication.processEvents()

    def _set_splash_logo(self, fallback_path, border_color):
        if os.path.exists(fallback_path):
            pixmap = make_circular_pixmap(fallback_path, 76, border_color=border_color, border_width=2, bg_color=BG_COLOR)
            if pixmap:
                self.logo_lbl.setPixmap(pixmap)
                self.logo_lbl.setStyleSheet("background: transparent; border: none;")
                return
        self.logo_lbl.setText("S")
        self.logo_lbl.setFont(app_font(28, QFont.Weight.Bold))
        self.logo_lbl.setStyleSheet(
            f"QLabel {{ color: {ACCENT_COLOR}; background: {PANEL_COLOR}; border: 2px solid {border_color}; border-radius: 38px; }}"
        )

    def apply_theme(self):
        card_mid = "#101C42" if CURRENT_THEME == "dark" else "#F1F7FF"
        card_end = "#231038" if CURRENT_THEME == "dark" else "#FFF4FD"
        self.card.setStyleSheet(
            "QFrame#SplashCard {"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {BG_ELEVATED_COLOR}, stop:0.55 {card_mid}, stop:1 {card_end});"
            "border: none; border-radius: 0px;"
            "}"
        )
        self.title_lbl.setStyleSheet(
            f"color: {TEXT_COLOR}; background: transparent; border: none; "
            "font-size: 28px; font-weight: 800; letter-spacing: 0px;"
        )
        self.subtitle_lbl.setStyleSheet(
            f"color: {MUTED_TEXT_COLOR}; background: transparent; border: none; "
            "font-size: 13px; font-weight: 700; letter-spacing: 0px;"
        )
        self.meta_lbl.setStyleSheet(
            f"color: {SUBTLE_TEXT_COLOR}; background: transparent; border: none; "
            "font-size: 11px; font-weight: 700; letter-spacing: 0px;"
        )
        self.status_lbl.setStyleSheet(
            f"color: {MUTED_TEXT_COLOR}; background: transparent; border: none; "
            "font-size: 13px; font-weight: 700; letter-spacing: 0px;"
        )
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {PANEL_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 4px; padding: 0px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {ACCENT_PINK_COLOR}, stop:0.52 {BRAND_VIOLET_COLOR}, stop:1 {ACCENT_COLOR}); "
            "border-radius: 3px; }}"
        )

    def _advance_status(self):
        self._status_index = (self._status_index + 1) % len(self.STATUS_MESSAGES)
        self.status_lbl.setText(self.STATUS_MESSAGES[self._status_index])

    def _tick_progress(self):
        if self._finishing:
            return
        self._progress_ticks += 1
        current = int(self.progress_bar.value())
        if current < 52:
            step = 2
        elif current < 78:
            step = 1 if self._progress_ticks % 2 else 2
        elif current < 91:
            step = 1 if self._progress_ticks % 3 == 0 else 0
        else:
            step = 1 if self._progress_ticks % 9 == 0 else 0
        if step:
            self.progress_bar.setValue(min(94, current + step))

    def center_on_screen(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.move(
                available.x() + max(0, (available.width() - self.width()) // 2),
                available.y() + max(0, (available.height() - self.height()) // 2),
            )

    def _apply_window_mask(self):
        self.clearMask()

    def showEvent(self, event):
        self._apply_window_mask()
        self.center_on_screen()
        super().showEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_window_mask()

    def finish(self, window):
        if self._finishing:
            return
        self._finishing = True
        self._finish_window = window
        if self._status_timer:
            self._status_timer.stop()
        if getattr(self, "_progress_timer", None):
            self._progress_timer.stop()
        self.status_lbl.setText("סמארטי מוכן לעבודה.")
        self._finish_progress_anim = QPropertyAnimation(self.progress_bar, b"value", self)
        self._finish_progress_anim.setDuration(160)
        self._finish_progress_anim.setStartValue(self.progress_bar.value())
        self._finish_progress_anim.setEndValue(100)
        self._finish_progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._finish_progress_anim.finished.connect(self._start_fade_out)
        self._finish_progress_anim.start()

    def _start_fade_out(self):
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.finished.connect(self._finish_close)
        self._fade_anim.start()

    def _finish_close(self):
        self.close()
        if self._finish_window:
            try:
                self._finish_window.raise_()
                self._finish_window.activateWindow()
            except Exception:
                pass


__all__ = [name for name in globals() if not name.startswith("__")]
