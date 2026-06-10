"""Chat bubbles, notifications, main window, and splash screen."""
from .common import *
from .attachments import *
from .ui_styles import *
from .ui_controls import *
from .config import BUILT_IN_TOOLS, LEGACY_BUILTIN_TOOLS, PUBLIC_BUILTIN_TOOLS
from .workers import AgentWorker, VoiceWorker, TTSWorker
from .ui_pages import ActionConfirmDialog, ApiKeyRequiredDialog, UsageStatsPage, TaskCenterPage, DeveloperTracePage, ToolsSettingsPage, SettingsPage, AboutPage, refresh_back_button_icon
from .history import DEFAULT_CHAT_TITLE, DEFAULT_WELCOME_MESSAGE
from .windows_notifications import TaskbarAttentionController, WindowsNotificationCenter
from .updater import UpdateCheckWorker, UpdateDownloadWorker, UpdateInfo, human_size, launch_update_installer
from PyQt6.QtCore import QEvent, QEventLoop
from PyQt6.QtGui import QTextDocument, QTransform
from PyQt6.QtWidgets import QBoxLayout

WELCOME_MESSAGE = DEFAULT_WELCOME_MESSAGE

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
            f'<tr><td align="left" style="border:0; color:{muted}; font-family:Segoe UI, Arial; font-size:12px; font-weight:700;">{html.escape(language)}</td>'
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
            return _soft_break_rendered_text(rendered_html)
        except Exception:
            pass
    rendered_html = _render_markdown_links_fallback(text, link_color, clickable_links)
    return _sanitize_rendered_links(rendered_html, link_color, clickable_links)

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
        self.language_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
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
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(1)

        self.tool_icon_label = QLabel()
        self.tool_icon_label.setFixedSize(18, 18)
        self.tool_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tool_icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.status_label = StepsShimmerLabel()
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumWidth(max(150, self.max_w - 46))
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
        self.status_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 15px; background: transparent; padding-right: 6px; padding-left: 0px;")
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
        available = max(120, self.max_w - 46)
        text = str(self.status_label.text() or "")
        width = _fitted_plain_label_width(self.status_label, text, available, min_width=42, padding=8)
        self.status_label.setWordWrap(width >= available)
        self.status_label.setMinimumWidth(width)
        self.status_label.setMaximumWidth(width)

    def _refresh_tool_icon(self):
        set_themed_label_icon(self.tool_icon_label, AGENT_TOOL_GROUP_ICON_NAMES, "", 16)

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
        self._refresh_tool_icon()
        self.running = True
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

class MessageBubble(QFrame):
    user_collapse_changed = pyqtSignal(bool, bool)

    USER_COLLAPSED_LINES = 6
    WIDGET_MAX_HEIGHT = 16777215
    PROCESS_CHEVRON_ICON_NAMES = ("agent_process_chevron", "message_collapse_arrow")

    def __init__(self, text, is_user=False, parent_width=450, attachments=None):
        super().__init__()
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
        self.code_blocks = []
        self._user_message_collapsible = False
        self._user_message_collapsed = True
        
        self.steps_container = QWidget()
        self.steps_container.setStyleSheet("background: transparent; border: none;")
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 8)
        self.steps_layout.setSpacing(8)

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
        self.steps_layout.addWidget(self.process_header)
        self.steps_layout.addWidget(self.process_details)
        self.steps_container.hide()
        
        self.final_label = QLabel()
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
        for group in getattr(self, "agent_process_groups", []):
            group.apply_theme()
        for label in self.findChildren(QLabel):
            self._apply_link_palette(label)
        self.setStyleSheet(
            f"MessageBubble {{ background: {bg}; border: {border}; border-radius: {radius}; margin: {margin}; }}"
            f"QLabel {{ color: {color}; font-size: 15px; font-family: 'Segoe UI', Arial; background: transparent; }}"
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
                widget.setParent(None)
                if widget is not self.final_label:
                    widget.deleteLater()

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
        return (
            f'<div dir="rtl" align="right" style="color:{MUTED_TEXT_COLOR}; '
            'font-size:12px; font-style:italic; line-height:1.35; '
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
        self.agent_process_started = True
        self.agent_process_finalized = False
        self.agent_process_start_time = time.time()
        self.agent_process_elapsed_seconds = 0
        self.is_expanded = True
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
                return True
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
            self.final_label.show()
            self.final_layout.addWidget(self.final_label)
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

    ACTION_BUTTON_SIZE = 36
    ACTION_ICON_SIZE = 22
    ACTION_ROW_HEIGHT = 40

    def __init__(self, text, is_user=False, parent_width=450, show_actions=True, attachments=None, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("background: transparent;")
        self.bubble = MessageBubble(text, is_user, parent_width, attachments=attachments)
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

        end_pos = self.content_wrap.pos()
        start_pos = end_pos + QPoint(0, 18)
        self.content_wrap.move(start_pos)
        self._enter_slide_anim = QPropertyAnimation(self.content_wrap, b"pos", self)
        self._enter_slide_anim.setDuration(360)
        self._enter_slide_anim.setStartValue(start_pos)
        self._enter_slide_anim.setEndValue(end_pos)
        self._enter_slide_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def cleanup():
            self.content_wrap.move(end_pos)
            self.content_wrap.setGraphicsEffect(None)
            self._actions_can_show = True
            if self.show_actions:
                self.actions_opacity.setOpacity(1.0)
            self.updateGeometry()

        self._enter_anim.finished.connect(cleanup)
        self._enter_slide_anim.start()
        self._enter_anim.start()

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
                font-family: 'Segoe UI', Arial;
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

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("חיפוש לפי שם או תוכן")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(LINE_EDIT_CSS)
        self.search_edit.textChanged.connect(self.load_sessions)
        layout.addWidget(self.search_edit)

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
        self.search_edit.setStyleSheet(LINE_EDIT_CSS)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS)
        self.load_sessions()

    def _format_time(self, value):
        try:
            dt = datetime.fromisoformat(str(value or ""))
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(value or "")

    def _clear_rows(self):
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

    def _session_row(self, record, active_id):
        session_id = record.get("id")
        row = ClickableSessionFrame(session_id)
        row.clicked.connect(self.open_session)
        row.setMinimumWidth(0)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.setStyleSheet(card_css(10, 8))
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(12, 10, 12, 10)
        row_layout.setSpacing(7)

        title_row = QHBoxLayout()
        title = QLabel()
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title.setText(_escape_plain_text_with_soft_breaks(record.get("title") or DEFAULT_CHAT_TITLE))
        title.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 15px; font-weight: 800; border: none;")
        title_row.addWidget(title, 1)

        if record.get("id") == active_id:
            active = QLabel("פעילה")
            active.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            active.setStyleSheet(
                f"background: {GLASS_COLOR}; color: {ACCENT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
                "border-radius: 10px; padding: 3px 8px; font-size: 11px; font-weight: 800;"
            )
            title_row.addWidget(active)
        row_layout.addLayout(title_row)

        preview = QLabel()
        preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        preview.setTextFormat(Qt.TextFormat.RichText)
        preview.setWordWrap(True)
        preview.setMinimumWidth(0)
        preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        preview_source = record.get("preview_source") or record.get("preview", "")
        preview.setText(_render_markdown_html(_markdown_preview_source(preview_source), ACCENT_COLOR, style_blocks=False, clickable_links=False))
        preview.setStyleSheet(muted_label_css(12) + " border: none;")
        row_layout.addWidget(preview)

        meta = QLabel(f"{self._format_time(record.get('updated_at'))} · {record.get('message_count', 0)} הודעות")
        meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        meta.setMinimumWidth(0)
        meta.setStyleSheet(f"color: {SUBTLE_TEXT_COLOR}; font-size: 11px; border: none;")
        row_layout.addWidget(meta)

        actions = QGridLayout()
        actions.setHorizontalSpacing(6)
        actions.setVerticalSpacing(6)
        pin_btn = self._icon_button(
            "בטל הצמדה" if record.get("pinned") else "הצמד שיחה",
            (
                "unpin_icon" if record.get("pinned") else "pin_icon",
            ),
            fallback_text="★" if record.get("pinned") else "☆",
        )
        pin_btn.clicked.connect(lambda checked=False, sid=session_id, pinned=not record.get("pinned"): self.set_pinned(sid, pinned))
        rename_btn = self._icon_button(
            "שנה שם",
            ("rename_icon",),
            fallback_text="✎",
        )
        rename_btn.clicked.connect(lambda checked=False, sid=session_id, current=record.get("title", ""): self.rename_session(sid, current))
        export_btn = self._icon_button(
            "יצוא JSON",
            ("export_json_icon", "export_icon"),
            fallback_text="{}",
        )
        export_btn.clicked.connect(lambda checked=False, sid=session_id, title=record.get("title", ""): self.export_session(sid, title))
        delete_btn = self._icon_button(
            "מחק שיחה",
            ("delete_icon",),
            fallback_text="×",
            danger=True,
        )
        delete_btn.clicked.connect(lambda checked=False, sid=session_id: self.delete_session(sid))
        for index, btn in enumerate((pin_btn, rename_btn, export_btn, delete_btn)):
            actions.addWidget(btn, 0, index)
        for col in range(4):
            actions.setColumnStretch(col, 1)
        row_layout.addLayout(actions)
        return row

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
            f"body {{ direction: rtl; text-align: right; color: {TEXT_COLOR}; font-family: 'Segoe UI', Arial; font-size: 13px; }}"
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
            self.status_lbl.setText("לא נמצא קובץ התקנה מסוג Setup.exe בפוסט השחרור בגיטהאב.")
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


class ChatWindow(QMainWindow):
    gui_message_signal = pyqtSignal(str, bool)
    tts_status_signal = pyqtSignal(bool)
    core_notification_signal = pyqtSignal(str, object)
    voice_hotkey_signal = pyqtSignal()

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
        self.available_update = None
        self.update_check_worker = None
        self.update_download_worker = None
        self._update_dialog = None
        self._update_check_source = None
        self.pending_attachments = []
        self.taskbar_attention = TaskbarAttentionController(self)
        self.notifications = WindowsNotificationCenter(self)
        self.notifications.reply_requested.connect(self.handle_notification_reply)
        self.notifications.activate_requested.connect(self.handle_notification_activation)
        self.notifications.attention_cleared.connect(self._clear_taskbar_attention)
        self.core_notification_signal.connect(self.handle_core_notification)
        self.core.notification_callback = lambda kind, payload=None: self.core_notification_signal.emit(kind, payload or {})
        
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
                available.y() + max(0, (available.height() - target_h) // 2)
            )
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
        self.about_page = None
        
        logging.info(f"\n{'='*50}\n--- תחילת שיחה חדשה (הפעלת תוכנה) ---\n{'='*50}")
        self.load_active_chat_session()
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
        self.tray_menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.tray_menu.setStyleSheet(menu_stylesheet())
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
        self.bring_to_front()
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
        self.bring_to_front()
        if start_listening and not self.agent_running:
            QTimer.singleShot(150, self.start_voice)

    def _utc_now_iso(self):
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def _auto_update_check_due(self):
        if not bool(self.core.settings.get("updates_auto_check", True)):
            return False
        try:
            interval_hours = max(1, int(self.core.settings.get("updates_check_interval_hours", 12) or 12))
        except Exception:
            interval_hours = 12
        last_value = str(self.core.settings.get("updates_last_checked_at", "") or "").strip().replace("Z", "")
        if not last_value:
            return True
        try:
            last_dt = datetime.fromisoformat(last_value)
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
            self.core._save_settings()
        except Exception:
            pass

    def _finish_update_source(self, message):
        source = getattr(self, "_update_check_source", None)
        self._update_check_source = None
        if source and hasattr(source, "finish_update_check"):
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
        self._finish_update_source("אין עדכון חדש.")
        if manual:
            self.show_update_notice("סמארטי מעודכן", "אין עדכון חדש. הגרסה הנוכחית כבר מעודכנת.")

    def _handle_update_check_failed(self, message, manual=False):
        self._record_update_check(None)
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
            f"padding: 4px 10px; font-size: 17px; font-family: 'Segoe UI'; outline: none; text-align: left; }}"
            f"QTextEdit:disabled {{ color: {SUBTLE_TEXT_COLOR}; }}"
            f"QTextEdit viewport {{ background-color: transparent; border: none; }}"
            f"{SCROLLBAR_CSS}"
        )

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
        if hasattr(self, "top_bar"):
            self.top_bar.setStyleSheet(self._top_bar_stylesheet())
        if hasattr(self, "menu_btn"):
            self.menu_btn.setStyleSheet(self._menu_button_stylesheet())
        if hasattr(self, "update_btn"):
            self.update_btn.setStyleSheet(self._update_button_stylesheet())
            apply_soft_shadow(self.update_btn, blur=26, y=7, alpha=72)
            self._set_update_button_icon()
        if hasattr(self, "menu"):
            self.menu.setStyleSheet(menu_stylesheet())
        if hasattr(self, "title_label"):
            self.title_label.setStyleSheet(page_title_css(19))
            self.refresh_chat_title()
        if hasattr(self, "subtitle"):
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
        if hasattr(self, "attach_btn"):
            self._set_attach_button_icon()
        if hasattr(self, "attachment_preview"):
            self.attachment_preview.apply_theme()
        if hasattr(self, "attach_menu"):
            self.attach_menu.setStyleSheet(menu_stylesheet())
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
        if getattr(self, "history_page", None) is not None:
            self.history_page.apply_theme()
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
        top_bar.setFixedHeight(64)
        top_bar.setStyleSheet(self._top_bar_stylesheet())
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 7, 15, 7)
        top_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        self.menu_btn = QPushButton("⋮")
        self.menu_btn.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self.menu_btn.setFixedSize(48, 48)
        self.menu_btn.setToolTip("תפריט")
        self.menu_btn.setStyleSheet(self._menu_button_stylesheet())
        self.menu_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.menu = QMenu(self)
        self.menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        if hasattr(self.menu, "setIconSize"):
            self.menu.setIconSize(QSize(22, 22))
        self.menu.setStyleSheet(menu_stylesheet())
        self.menu.aboutToHide.connect(self._guard_menu_reopen_from_button)
        self._menu_actions = []
        self._add_menu_action("שיחה חדשה", self.start_new_chat, "new_chat_icon", "plus_icon")
        self._add_menu_action("היסטוריית שיחות", self.show_history_page, "chat_history_icon", "history_icon")
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
        titles_layout.setContentsMargins(8, 0, 8, 0)
        titles_layout.setSpacing(0)
        self.title_label = EndElideLabel(self.active_chat_title())
        self.title_label.setStyleSheet(page_title_css(19))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        raw_model = self.core.settings.get(f"selected_{self.core.mode}_model", "Gemini")
        self.subtitle = EndElideLabel(self.format_model_name(raw_model))
        self.subtitle.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 12px; font-weight: 700;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titles_layout.addWidget(self.title_label)
        titles_layout.addWidget(self.subtitle)
        
        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(50, 50)
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            circular_pixmap = make_circular_pixmap(logo_path, 50)
            if circular_pixmap: self.logo_lbl.setPixmap(circular_pixmap)
            self.logo_lbl.setStyleSheet("border: none; background-color: transparent;")
        else:
            self.logo_lbl.setText("S")
            self.logo_lbl.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
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
        self.chat_body.setStyleSheet("background: transparent;")
        body_layout = QGridLayout(self.chat_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }" + SCROLLBAR_CSS) 
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_widget = QWidget()
        self.chat_widget.setStyleSheet("background: transparent;")
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setContentsMargins(12, 14, 12, 128)
        self.chat_layout.setSpacing(8)
        self.scroll.setWidget(self.chat_widget)
        body_layout.addWidget(self.scroll, 0, 0)
        
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
        self.input_frame.setMinimumHeight(82)
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

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(8)

        self.input_field = ExpandingTextEdit()
        self.input_field.setPlaceholderText("הודעה")
        self.input_field.setStyleSheet(self._chat_input_stylesheet())
        self.input_field.textChanged.connect(self.on_text_change)
        self.input_field.send_signal.connect(self.send_text)
        self.input_field.files_pasted.connect(self.add_attachment_paths)
        self.input_field.image_pasted.connect(self.add_pasted_image)
        input_row.addWidget(self.input_field, 1, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.attach_btn = QPushButton("+")
        self.attach_btn.setFixedSize(42, 42)
        self.attach_btn.setToolTip("הוספת קבצים")
        self.attach_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._set_attach_button_icon()
        # Google Drive upload is parked for now; the plus button opens the local file picker directly.
        self.attach_btn.clicked.connect(self.choose_local_attachments)
        input_row.addWidget(self.attach_btn, 0, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        self.action_btn = QPushButton()
        self.action_btn.setFixedSize(52, 52)
        self.action_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.refresh_themed_icons()
        self.update_action_btn_visuals()
        self.action_btn_host = PinnedActionButtonHost(self.action_btn)
        input_row.insertWidget(0, self.action_btn_host, 0)
        input_frame_layout.addLayout(input_row)
        
        # Keep the action button visually on the left even inside the RTL chat.
        bottom_layout.addWidget(self.input_frame, alignment=Qt.AlignmentFlag.AlignVCenter)
        overlay_layout.addLayout(bottom_layout)
        body_layout.addWidget(self.input_overlay, 0, 0, Qt.AlignmentFlag.AlignBottom)
        main_layout.addWidget(self.chat_body, 1)
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
        if self.usage_page is None:
            self.usage_page = UsageStatsPage(self.core, self)
            self.stacked_widget.addWidget(self.usage_page)
        self.usage_page.load_data('today')
        self.stacked_widget.setCurrentWidget(self.usage_page)
        self._reset_page_scrolls(self.usage_page)

    def show_settings_page(self):
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
        if self.tools_page is not None:
            self.stacked_widget.removeWidget(self.tools_page)
            self.tools_page.deleteLater()
        self.tools_page = ToolsSettingsPage(self.core, self)
        self.stacked_widget.addWidget(self.tools_page)
        self.stacked_widget.setCurrentWidget(self.tools_page)
        self._reset_page_scrolls(self.tools_page)

    def show_task_center_page(self):
        if self.task_center_page is None:
            self.task_center_page = TaskCenterPage(self.core, self)
            self.stacked_widget.addWidget(self.task_center_page)
        self.task_center_page.load_tasks()
        self.stacked_widget.setCurrentWidget(self.task_center_page)
        self._reset_page_scrolls(self.task_center_page)

    def show_trace_page(self):
        if self.trace_page is None:
            self.trace_page = DeveloperTracePage(self.core, self)
            self.stacked_widget.addWidget(self.trace_page)
        self.trace_page.load_trace()
        self.stacked_widget.setCurrentWidget(self.trace_page)
        self._reset_page_scrolls(self.trace_page)

    def show_history_page(self):
        if self.history_page is None:
            self.history_page = ChatHistoryPage(self.core, self)
            self.stacked_widget.addWidget(self.history_page)
        self.history_page.load_sessions()
        self.stacked_widget.setCurrentWidget(self.history_page)
        self._reset_page_scrolls(self.history_page)

    def show_about_page(self):
        if self.about_page is None:
            self.about_page = AboutPage(self)
            self.stacked_widget.addWidget(self.about_page)
        self.stacked_widget.setCurrentWidget(self.about_page)
        self._reset_page_scrolls(self.about_page)

    def bring_to_front(self):
        self._clear_taskbar_attention()
        if hasattr(self, "quick_reply_toast"):
            self.quick_reply_toast.hide()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.show()
        self.activateWindow()
        self.raise_()

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

    def closeEvent(self, event):
        if getattr(self, "_quit_requested", False) or not self.core.settings.get("keep_running_in_tray", True):
            self.unregister_voice_hotkey()
            if hasattr(self, "tray_icon"):
                self.tray_icon.hide()
            event.accept()
            return
        event.ignore()
        self.hide()

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
            if not is_reminder and not self._should_notify_user():
                return
            self._request_taskbar_attention()
            title = task.get("title") or ("תזכורת מסמארטי" if is_reminder else "משימת רקע הסתיימה")
            body = result or task.get("message") or task.get("prompt") or "המשימה הסתיימה."
            self.notifications.show_notice(title, body, kind="reminder" if is_reminder else "default")

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
            available_width = self.scroll.viewport().width() or self.width()
            for bubble in self.findChildren(MessageBubble):
                bubble.update_parent_width(available_width)
            self._update_chat_bottom_padding()
        except Exception:
            pass

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
        text = container.bubble.plain_text()
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
            self.action_btn.setToolTip("")
            has_text = bool(self.input_field.toPlainText().strip()) or bool(getattr(self, "pending_attachments", []))
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

    def add_message(self, text, is_user, show_actions=True, attachments=None, anchor_user=False):
        attachments = normalize_attachments(attachments or [])
        if not text and is_user and not attachments: return
        available_width = self.scroll.viewport().width() or self.width()
        container = ChatMessageContainer(
            text,
            is_user,
            available_width,
            show_actions=show_actions,
            attachments=attachments,
            parent=self.chat_widget,
        )
        self._wire_message_container(container)
        self.chat_layout.addWidget(container)
        QTimer.singleShot(0, container.start_entry_animation)
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
        self.bring_to_front()
        QTimer.singleShot(0, self.start_voice)

    def start_voice(self):
        if self.agent_running:
            return
        if getattr(self, "voice_thread", None) and self.voice_thread.isRunning():
            return
        self.core.stop_speaking() 
        self.status_lbl.setText("מפעיל האזנה...")
        self.input_field.setEnabled(False)
        self.action_btn.setEnabled(False)
        self.voice_thread = VoiceWorker(self.core.settings)
        self.voice_thread.status_signal.connect(lambda s: self.status_lbl.setText(s))
        self.voice_thread.finished_signal.connect(self.on_voice_finished)
        self.voice_thread.start()

    def on_voice_finished(self, text):
        self.voice_thread = None
        self.status_lbl.setText("")
        self.input_field.setEnabled(True)
        self.action_btn.setEnabled(True)
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
        
        self.agent_thread = AgentWorker(self.core, text, attachments=attachments)
        self.agent_thread.status_signal.connect(lambda s: self.status_lbl.setText(s))
        self.agent_thread.ask_confirm_signal.connect(self.show_confirm_dialog) 
        self.agent_thread.api_key_required_signal.connect(self.show_api_key_dialog)
        self.agent_thread.step_signal.connect(self.on_agent_step)
        self.agent_thread.finished_signal.connect(self.on_agent_finished)
        self.agent_thread.start()

    def on_agent_step(self, step_text):
        if self.current_agent_bubble:
            changed = self.current_agent_bubble.handle_agent_event(step_text)
            if changed and self.current_agent_container:
                self.current_agent_bubble.show()
                self.current_agent_container.reveal_with_entry_animation()
                self._schedule_scroll_last_user_to_view_top(delays=(50, 160))

    def show_confirm_dialog(self, title, text, risk="medium"):
        decision = None
        if self._should_notify_user() and hasattr(self, "notifications"):
            decision = self._request_permission_from_notification(title, text, risk)
        if decision is not None:
            self.agent_thread.confirm_result = bool(decision)
            self.agent_thread.confirm_event.set()
            return
        dlg = ActionConfirmDialog(title, text, risk, self)
        self.agent_thread.confirm_result = (dlg.exec() == QDialog.DialogCode.Accepted)
        self.agent_thread.confirm_event.set()

    def _request_permission_from_notification(self, title, text, risk="medium"):
        decision = {"value": "pending"}

        def answered(value):
            self._clear_taskbar_attention()
            decision["value"] = value

        self._request_taskbar_attention()
        shown = self.notifications.show_permission_request(title, text, risk, callback=answered)
        if not shown:
            self._clear_taskbar_attention()
            return None

        loop = QEventLoop(self)
        poll = QTimer(self)

        def maybe_finish():
            if decision["value"] != "pending":
                loop.quit()
                return
            try:
                if self.core._is_cancel_requested():
                    decision["value"] = False
                    self._clear_taskbar_attention()
                    loop.quit()
            except Exception:
                pass

        poll.timeout.connect(maybe_finish)
        poll.start(100)
        loop.exec()
        poll.stop()
        poll.deleteLater()
        return decision["value"]

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
                if self.current_agent_container:
                    self.current_agent_container.reveal_with_entry_animation()
                response_container = self.current_agent_container
            else:
                response_container = self.add_message(response, is_user=False)
                
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
        self._clear_chat_widgets()
        messages = self.core.active_chat_messages()
        if not messages:
            self.add_message(WELCOME_MESSAGE, is_user=False, show_actions=False)
            self.refresh_chat_title()
            return
        if not any(self._is_welcome_history_message(message) for message in messages):
            self.add_message(WELCOME_MESSAGE, is_user=False, show_actions=False)
        for message in messages:
            role = message.get("role")
            content = str(message.get("content", "") or "")
            metadata = message.get("metadata", {}) if isinstance(message.get("metadata", {}), dict) else {}
            attachments = normalize_attachments(metadata.get("attachments", []))
            if role not in {"user", "assistant"} or (not content.strip() and not attachments):
                continue
            is_welcome = self._is_welcome_history_message(message)
            container = self.add_message(content, is_user=(role == "user"), show_actions=not is_welcome, attachments=attachments)
            if role == "assistant" and container and isinstance(metadata.get("agent_process"), dict):
                container.bubble.restore_agent_process(metadata.get("agent_process"))
        self.refresh_chat_title()
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

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
    def __init__(self, anim_path, fallback_path, size, border_color, border_width, radius, bg_color):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFixedSize(size, size)
        self.border_width, self.border_color, self.radius, self.bg_color = border_width, QColor(border_color), radius, QColor(bg_color)
        
        mask_pixmap = QPixmap(size, size)
        mask_pixmap.fill(Qt.GlobalColor.transparent)
        mask_painter = QPainter(mask_pixmap)
        mask_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        mask_path = QPainterPath()
        mask_path.addRoundedRect(0.0, 0.0, float(size), float(size), float(radius), float(radius))
        mask_painter.fillPath(mask_path, Qt.GlobalColor.black)
        mask_painter.end()
        self.setMask(mask_pixmap.mask())
        
        self.lbl = QLabel(self)
        self.lbl.setGeometry(border_width, border_width, size - 2*border_width, size - 2*border_width)
        self.lbl.setScaledContents(True) 
        self.lbl.setStyleSheet(f"background-color: {bg_color};")
        
        if os.path.exists(anim_path):
            self.movie = QMovie(anim_path)
            self.lbl.setMovie(self.movie)
            self.movie.start()
        elif os.path.exists(fallback_path): self.lbl.setPixmap(QPixmap(fallback_path))
        else:
            self.lbl.setText("S")
            self.lbl.setFont(QFont("Segoe UI", int(size/3), QFont.Weight.Bold))
            self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lbl.setStyleSheet(f"color: {border_color}; background-color: {bg_color};")

    def center_on_screen(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.move(
                available.x() + max(0, (available.width() - self.width()) // 2),
                available.y() + max(0, (available.height() - self.height()) // 2),
            )

    def showEvent(self, event):
        self.center_on_screen()
        super().showEvent(event)
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), float(self.radius), float(self.radius))
        painter.fillPath(path, self.bg_color)
        pen = QPen(self.border_color)
        pen.setWidth(self.border_width * 2) 
        painter.setPen(pen)
        painter.drawPath(path)

    def finish(self, window): self.close()


__all__ = [name for name in globals() if not name.startswith("__")]
