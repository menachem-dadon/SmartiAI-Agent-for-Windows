"""Smarti Workspace shell and its integrated work surfaces."""
from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QDateTime,
    QDir,
    QEvent,
    QObject,
    QProcess,
    QPoint,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    QEasingCurve,
    QVariantAnimation,
    QStringListModel,
    pyqtSignal,
)
from PyQt6.QtGui import QDesktopServices, QFileSystemModel, QIcon, QImage, QPixmap, QTextCursor, QCursor
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QCompleter,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QTabBar,
    QTabWidget,
    QTextBrowser,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from .browser_profile import discover_browser_profiles, import_profile_data
from .common import OUTPUTS_DIR, SMARTI_BROWSER_PROFILE_NAME, USER_DATA_DIR
from .native_browser import NativeChromiumHost
from .ui_controls import NoScrollComboBox
from .ui_styles import *
from .webengine_probe import probe_webengine_runtime


TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".py", ".pyw", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".xml",
    ".html", ".htm", ".css", ".scss", ".sql", ".sh", ".ps1", ".bat", ".cmd", ".csv",
    ".log", ".java", ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs", ".php",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".svg"}
MEDIA_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mkv", ".webm", ".mov", ".avi"}
OFFICE_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx"}


def classify_workspace_file(path):
    suffix = Path(str(path or "")).suffix.lower()
    if suffix in (".md", ".markdown"):
        return "markdown"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in MEDIA_EXTENSIONS:
        return "media"
    if suffix == ".pdf":
        return "pdf"
    if suffix in OFFICE_EXTENSIONS:
        return "office"
    return "unknown"


def resolve_workspace_root(core):
    """Prefer a session workspace, then the configured safe output root."""
    try:
        session = core.active_chat_session_metadata()
        workspace_id = str((session or {}).get("workspace_id") or "")
        if workspace_id:
            for workspace in core.chat_store.list_workspaces():
                if str(workspace.get("id") or "") == workspace_id:
                    candidate = os.path.abspath(os.path.expanduser(str(workspace.get("root_path") or "")))
                    if os.path.isdir(candidate):
                        return candidate
    except Exception:
        pass
    try:
        candidate = core._sandbox_root() if core._sandbox_enabled() else core._default_output_dir()
        candidate = os.path.abspath(os.path.expanduser(str(candidate or "")))
        if candidate:
            os.makedirs(candidate, exist_ok=True)
            return candidate
    except Exception:
        pass
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    return os.path.abspath(OUTPUTS_DIR)


class _WorkerSignals(QObject):
    ready = pyqtSignal(object, str)


class _PreviewWorker(QRunnable):
    def __init__(self, path, cache_dir):
        super().__init__()
        self.path = os.path.abspath(path)
        self.cache_dir = cache_dir
        self.signals = _WorkerSignals()

    def run(self):
        try:
            source = self.path
            if classify_workspace_file(source) == "office":
                source = self._office_to_pdf(source)
            pages = self._render_pdf(source)
            self.signals.ready.emit({"path": self.path, "pages": pages}, "")
        except Exception as exc:
            self.signals.ready.emit({"path": self.path, "pages": []}, str(exc))

    def _office_to_pdf(self, source):
        os.makedirs(self.cache_dir, exist_ok=True)
        stamp = int(os.path.getmtime(source))
        target = os.path.join(self.cache_dir, f"{Path(source).stem}-{stamp}.pdf")
        if os.path.isfile(target):
            return target
        try:
            import pythoncom
            import win32com.client
        except Exception as exc:
            raise RuntimeError("תצוגת מסמכי Office דורשת התקנת Office במחשב.") from exc
        pythoncom.CoInitialize()
        app = None
        document = None
        try:
            suffix = Path(source).suffix.lower()
            if suffix in {".doc", ".docx"}:
                app = win32com.client.DispatchEx("Word.Application")
                app.Visible = False
                document = app.Documents.Open(source, ReadOnly=True, AddToRecentFiles=False)
                document.ExportAsFixedFormat(target, 17)
            elif suffix in {".xls", ".xlsx", ".xlsm"}:
                app = win32com.client.DispatchEx("Excel.Application")
                app.Visible = False
                app.DisplayAlerts = False
                document = app.Workbooks.Open(source, UpdateLinks=0, ReadOnly=True)
                document.ExportAsFixedFormat(0, target)
            else:
                app = win32com.client.DispatchEx("PowerPoint.Application")
                document = app.Presentations.Open(source, ReadOnly=True, Untitled=False, WithWindow=False)
                document.SaveAs(target, 32)
            return target
        finally:
            try:
                if document is not None:
                    document.Close(False)
            except Exception:
                pass
            try:
                if app is not None:
                    app.Quit()
            except Exception:
                pass
            pythoncom.CoUninitialize()

    @staticmethod
    def _render_pdf(source):
        try:
            import fitz
        except Exception as exc:
            raise RuntimeError("רכיב תצוגת PDF אינו זמין.") from exc
        doc = fitz.open(source)
        result = []
        try:
            for page_index in range(min(len(doc), 10)):
                page = doc.load_page(page_index)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.45, 1.45), alpha=False)
                result.append(pixmap.tobytes("png"))
        finally:
            doc.close()
        return result


class _ArtifactScanWorker(QRunnable):
    def __init__(self, root, since_timestamp=0):
        super().__init__()
        self.root = root
        self.since_timestamp = float(since_timestamp or 0)
        self.signals = _WorkerSignals()

    def run(self):
        records = []
        try:
            for base, dirs, files in os.walk(self.root):
                dirs[:] = [name for name in dirs if name not in {".git", "__pycache__", ".venv", "node_modules"}]
                for name in files:
                    path = os.path.join(base, name)
                    try:
                        stat = os.stat(path)
                    except OSError:
                        continue
                    if self.since_timestamp and stat.st_mtime + 1 < self.since_timestamp:
                        continue
                    records.append((stat.st_mtime, stat.st_size, path))
                    if len(records) > 3000:
                        records.sort(reverse=True)
                        del records[800:]
            records.sort(reverse=True)
            self.signals.ready.emit(records[:250], "")
        except Exception as exc:
            self.signals.ready.emit([], str(exc))


class _BrowserImportWorker(QRunnable):
    def __init__(self, source, cookies, history, bookmarks):
        super().__init__()
        self.source = source
        self.cookies = cookies
        self.history = history
        self.bookmarks = bookmarks
        self.signals = _WorkerSignals()

    def run(self):
        try:
            payload = import_profile_data(
                self.source,
                include_cookies=self.cookies,
                include_history=self.history,
                include_bookmarks=self.bookmarks,
            )
            self.signals.ready.emit(payload, "")
        except Exception as exc:
            self.signals.ready.emit({}, str(exc))


class _WebEngineProbeWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = _WorkerSignals()

    def run(self):
        healthy = probe_webengine_runtime()
        self.signals.ready.emit(bool(healthy), "" if healthy else "Qt WebEngine failed its isolated startup check.")


class _BrowserCdpWorker(QRunnable):
    """Run one visible-browser command without blocking the Qt event loop."""

    def __init__(self, endpoint, target_id, action, value=None):
        super().__init__()
        self.endpoint = str(endpoint or "")
        self.target_id = str(target_id or "")
        self.action = str(action or "")
        self.value = value
        self.signals = _WorkerSignals()

    @staticmethod
    def _target_id(context, page):
        try:
            session = context.new_cdp_session(page)
            try:
                info = session.send("Target.getTargetInfo")
                return str(((info or {}).get("targetInfo") or {}).get("targetId") or "")
            finally:
                session.detach()
        except Exception:
            return ""

    def run(self):
        playwright = None
        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = playwright.chromium.connect_over_cdp(self.endpoint, timeout=9000)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            pages = list(context.pages)
            page = pages[-1] if pages else context.new_page()
            if self.target_id:
                for candidate in pages:
                    if self._target_id(context, candidate) == self.target_id:
                        page = candidate
                        break
            if self.action == "navigate":
                page.goto(str(self.value or "about:blank"), wait_until="domcontentloaded", timeout=30000)
            elif self.action == "back":
                page.go_back(wait_until="domcontentloaded", timeout=30000)
            elif self.action == "forward":
                page.go_forward(wait_until="domcontentloaded", timeout=30000)
            elif self.action == "reload":
                page.reload(wait_until="domcontentloaded", timeout=30000)
            elif self.action == "find":
                query = json.dumps(str(self.value or ""), ensure_ascii=False)
                found = page.evaluate(f"() => window.find({query}, false, false, true, false, false, false)")
            elif self.action == "zoom":
                session = context.new_cdp_session(page)
                try:
                    session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": float(self.value or 1.0)})
                finally:
                    session.detach()
            elif self.action == "device_mode":
                enabled = bool(self.value)
                session = context.new_cdp_session(page)
                try:
                    if enabled:
                        session.send(
                            "Emulation.setDeviceMetricsOverride",
                            {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True},
                        )
                        session.send(
                            "Network.setUserAgentOverride",
                            {"userAgent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"},
                        )
                    else:
                        session.send("Emulation.clearDeviceMetricsOverride")
                finally:
                    session.detach()
            elif self.action == "screenshot":
                page.screenshot(path=os.path.abspath(str(self.value or "browser.png")), full_page=True)
            elif self.action == "cookies":
                cookies = list(self.value or [])
                if cookies:
                    context.add_cookies(cookies)
            elif self.action == "clear":
                context.clear_cookies()
                session = context.new_cdp_session(page)
                try:
                    session.send("Network.clearBrowserCache")
                    session.send("Storage.clearDataForOrigin", {"origin": page.url, "storageTypes": "all"})
                finally:
                    session.detach()
            elif self.action == "download_dir":
                target = os.path.abspath(str(self.value or ""))
                os.makedirs(target, exist_ok=True)
                session = context.new_cdp_session(page)
                try:
                    session.send(
                        "Browser.setDownloadBehavior",
                        {"behavior": "allow", "downloadPath": target, "eventsEnabled": True},
                    )
                finally:
                    session.detach()
            payload = {
                "url": str(page.url or "about:blank"),
                "title": str(page.title() or "דפדפן"),
                "target_id": self._target_id(context, page),
                "count": len(self.value or []) if self.action == "cookies" else 0,
                "found": bool(locals().get("found", False)) if self.action == "find" else None,
            }
            self.signals.ready.emit(payload, "")
        except Exception as exc:
            self.signals.ready.emit({}, str(exc))
        finally:
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    pass


class WorkspaceFilePanel(QWidget):
    file_opened = pyqtSignal(str)

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.root_path = resolve_workspace_root(core)
        self._preview_generation = 0
        self._preview_tasks = []
        self._media_player = None
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(9)

        top = QHBoxLayout()
        self.root_label = QLabel(self.root_path)
        self.root_label.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.root_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.root_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.root_label.setToolTip(self.root_path)
        top.addWidget(self.root_label, 1)
        self.choose_root_btn = QPushButton("תיקייה")
        self.choose_root_btn.setToolTip("בחירת תיקיית עבודה לתצוגה")
        self.choose_root_btn.clicked.connect(self.choose_root)
        top.addWidget(self.choose_root_btn)
        self.open_external_btn = QPushButton("פתיחה")
        self.open_external_btn.setEnabled(False)
        self.open_external_btn.clicked.connect(self.open_current_external)
        top.addWidget(self.open_external_btn)
        layout.addLayout(top)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        # In the RTL workspace the navigation tree sits on the right and the
        # larger preview surface opens to its left, mirroring the app shell.
        self.splitter.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.model = QFileSystemModel(self)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.model.setRootPath(self.root_path)
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self.root_path))
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for column in range(1, 4):
            self.tree.hideColumn(column)
        self.tree.doubleClicked.connect(self._tree_activated)
        self.tree.clicked.connect(self._tree_activated)
        self.splitter.addWidget(self.tree)

        self.preview_stack = QStackedWidget()
        self.empty_label = QLabel("בחר קובץ מתיקיית העבודה")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.preview_stack.addWidget(self.empty_label)
        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.preview_stack.addWidget(self.text_preview)
        self.markdown_preview = QTextBrowser()
        self.markdown_preview.setOpenExternalLinks(True)
        self.preview_stack.addWidget(self.markdown_preview)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_scroll.setWidget(self.image_label)
        self.preview_stack.addWidget(self.image_scroll)
        self.pages_scroll = QScrollArea()
        self.pages_scroll.setWidgetResizable(True)
        self.pages_host = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_host)
        self.pages_layout.setContentsMargins(14, 14, 14, 14)
        self.pages_layout.setSpacing(14)
        self.pages_layout.addStretch()
        self.pages_scroll.setWidget(self.pages_host)
        self.preview_stack.addWidget(self.pages_scroll)
        self.media_host = self._build_media_host()
        self.preview_stack.addWidget(self.media_host)
        self.splitter.addWidget(self.preview_stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([270, 720])
        layout.addWidget(self.splitter, 1)
        self.current_path = ""

    def _build_media_host(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(10, 10, 10, 10)
        try:
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtMultimediaWidgets import QVideoWidget
            self._media_player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._media_player.setAudioOutput(self._audio_output)
            self._video_widget = QVideoWidget()
            self._media_player.setVideoOutput(self._video_widget)
            layout.addWidget(self._video_widget, 1)
            controls = QHBoxLayout()
            play = QPushButton("נגן")
            pause = QPushButton("השהה")
            stop = QPushButton("עצור")
            play.clicked.connect(self._media_player.play)
            pause.clicked.connect(self._media_player.pause)
            stop.clicked.connect(self._media_player.stop)
            controls.addStretch()
            controls.addWidget(play)
            controls.addWidget(pause)
            controls.addWidget(stop)
            controls.addStretch()
            layout.addLayout(controls)
        except Exception:
            label = QLabel("תצוגת מדיה אינה זמינה בהתקנה זו. אפשר לפתוח את הקובץ בתוכנת ברירת המחדל.")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            layout.addWidget(label, 1)
        return host

    def choose_root(self):
        selected = QFileDialog.getExistingDirectory(self, "בחירת תיקיית עבודה", self.root_path)
        if not selected:
            return
        if self.set_root(selected):
            try:
                workspace_id = self.core.chat_store.create_workspace(
                    title=os.path.basename(selected.rstrip("\\/")) or "סביבת עבודה",
                    root_path=selected,
                    metadata={"source": "desktop_workspace"},
                )
                session_id = str((self.core.active_chat_session_metadata() or {}).get("id") or "")
                if session_id:
                    self.core.chat_store.assign_session_workspace(session_id, workspace_id)
            except Exception:
                pass

    def set_root(self, path):
        path = os.path.abspath(os.path.expanduser(str(path or "")))
        if not os.path.isdir(path):
            return False
        self.root_path = path
        self.root_label.setText(path)
        self.root_label.setToolTip(path)
        self.model.setRootPath(path)
        self.tree.setRootIndex(self.model.index(path))
        return True

    def _tree_activated(self, index):
        path = self.model.filePath(index)
        if os.path.isfile(path):
            self.open_file(path)

    def open_file(self, path):
        path = os.path.abspath(str(path or ""))
        if not os.path.isfile(path):
            return
        self.current_path = path
        self.open_external_btn.setEnabled(True)
        kind = classify_workspace_file(path)
        try:
            if kind == "markdown":
                text = self._read_text(path)
                self.markdown_preview.setMarkdown(text)
                self.preview_stack.setCurrentWidget(self.markdown_preview)
            elif kind == "text":
                self.text_preview.setPlainText(self._read_text(path))
                self.preview_stack.setCurrentWidget(self.text_preview)
            elif kind == "image":
                pixmap = QPixmap(path)
                if pixmap.isNull():
                    raise RuntimeError("לא ניתן לטעון את התמונה.")
                self.image_label.setPixmap(pixmap)
                self.image_label.resize(pixmap.size())
                self.preview_stack.setCurrentWidget(self.image_scroll)
            elif kind in {"pdf", "office"}:
                self._start_document_preview(path)
            elif kind == "media":
                if self._media_player is not None:
                    self._media_player.setSource(QUrl.fromLocalFile(path))
                self.preview_stack.setCurrentWidget(self.media_host)
            else:
                mime = mimetypes.guess_type(path)[0] or "סוג קובץ לא מזוהה"
                self.empty_label.setText(f"אין תצוגה מקדימה מובנית עבור {mime}.\nאפשר לפתוח את הקובץ בתוכנת ברירת המחדל.")
                self.preview_stack.setCurrentWidget(self.empty_label)
            self.file_opened.emit(path)
        except Exception as exc:
            self.empty_label.setText(str(exc))
            self.preview_stack.setCurrentWidget(self.empty_label)

    @staticmethod
    def _read_text(path):
        if os.path.getsize(path) > 4 * 1024 * 1024:
            raise RuntimeError("הקובץ גדול מדי לתצוגה מלאה. אפשר לפתוח אותו בתוכנת ברירת המחדל.")
        raw = Path(path).read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "windows-1255", "utf-16", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def _clear_pages(self):
        while self.pages_layout.count() > 1:
            item = self.pages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _start_document_preview(self, path):
        self._preview_generation += 1
        generation = self._preview_generation
        self._clear_pages()
        loading = QLabel("מכין תצוגה מקדימה…")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages_layout.insertWidget(0, loading)
        self.preview_stack.setCurrentWidget(self.pages_scroll)
        cache = os.path.join(USER_DATA_DIR, "workspace", "preview-cache")
        task = _PreviewWorker(path, cache)
        self._preview_tasks.append(task)

        def ready(payload, error):
            try:
                self._preview_tasks.remove(task)
            except ValueError:
                pass
            if generation != self._preview_generation or payload.get("path") != self.current_path:
                return
            self._clear_pages()
            if error:
                label = QLabel(error)
                label.setWordWrap(True)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.pages_layout.insertWidget(0, label)
                return
            for page_data in payload.get("pages") or []:
                image = QImage.fromData(page_data, "PNG")
                page = QLabel()
                page.setAlignment(Qt.AlignmentFlag.AlignCenter)
                page.setPixmap(QPixmap.fromImage(image))
                page.setStyleSheet(f"background: white; border: 1px solid {SOFT_LINE_COLOR};")
                self.pages_layout.insertWidget(self.pages_layout.count() - 1, page)

        task.signals.ready.connect(ready)
        QThreadPool.globalInstance().start(task)

    def open_current_external(self):
        if self.current_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.current_path))

    def apply_theme(self):
        self.setStyleSheet(f"background: {BG_ELEVATED_COLOR}; color: {TEXT_COLOR};")
        self.root_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px;")
        for button in (self.choose_root_btn, self.open_external_btn):
            button.setStyleSheet(SECONDARY_BUTTON_CSS)
        self.tree.setStyleSheet(
            f"QTreeView {{ background: {GLASS_COLOR}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 12px; padding: 6px; }}"
            f"QTreeView::item:hover {{ background: {HOVER_TINT}; }} QTreeView::item:selected {{ background: {ACCENT_TINT_STRONG}; }}"
        )
        editor_css = (
            f"background: {GLASS_COLOR}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 12px; padding: 12px;"
        )
        self.text_preview.setStyleSheet(editor_css)
        self.markdown_preview.setStyleSheet(editor_css)
        self.empty_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; padding: 30px;")


class BrowserLibraryDialog(QDialog):
    """Searchable imported history/bookmarks surface instead of nested menus."""

    def __init__(self, payload, navigate_callback, parent=None):
        super().__init__(parent)
        self._navigate_callback = navigate_callback
        self.setWindowTitle("ספריית הדפדפן")
        self.setMinimumSize(620, 470)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        title = QLabel("היסטוריה וסימניות מיובאות")
        title.setStyleSheet(page_title_css(19))
        layout.addWidget(title)
        self.search = QLineEdit()
        self.search.setPlaceholderText("חיפוש לפי שם או כתובת")
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(LINE_EDIT_CSS)
        layout.addWidget(self.search)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self._lists = []
        for label, key in (("סימניות", "bookmarks"), ("היסטוריה", "history")):
            items = list(payload.get(key) or [])
            widget = QListWidget()
            widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            widget.setWordWrap(True)
            widget.setSpacing(4)
            widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            for item in items:
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                title_text = str(item.get("title") or url).strip()
                row = QListWidgetItem(f"{title_text}\n{url}")
                row.setData(Qt.ItemDataRole.UserRole, url)
                row.setData(Qt.ItemDataRole.UserRole + 1, f"{title_text} {url}".casefold())
                row.setSizeHint(QSize(0, 58))
                widget.addItem(row)
            widget.itemActivated.connect(self._open_item)
            widget.itemDoubleClicked.connect(self._open_item)
            self._lists.append(widget)
            self.tabs.addTab(widget, label)
        layout.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("סגור")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._filter)
        self.setStyleSheet(
            dialog_stylesheet()
            + f"QTabWidget::pane {{ border: 1px solid {SOFT_LINE_COLOR}; border-radius: 14px; background: {GLASS_COLOR}; }}"
            + f"QTabBar::tab {{ padding: 9px 18px; border-radius: 10px; color: {MUTED_TEXT_COLOR}; }}"
            + f"QTabBar::tab:selected {{ background: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR}; }}"
            + f"QListWidget {{ background: transparent; border: none; padding: 8px; }}"
            + f"QListWidget::item {{ border-radius: 10px; padding: 8px 10px; color: {TEXT_COLOR}; }}"
            + f"QListWidget::item:hover {{ background: {HOVER_TINT}; }}"
            + f"QListWidget::item:selected {{ background: {ACCENT_TINT_STRONG}; color: {TEXT_COLOR}; }}"
        )

    def _filter(self, text):
        query = str(text or "").strip().casefold()
        for widget in self._lists:
            for index in range(widget.count()):
                item = widget.item(index)
                item.setHidden(bool(query and query not in str(item.data(Qt.ItemDataRole.UserRole + 1) or "")))

    def _open_item(self, item):
        url = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if url:
            self._navigate_callback(url)
            self.accept()


class WorkspaceBrowserPanel(QWidget):
    activity_changed = pyqtSignal(str, str, int)
    availability_changed = pyqtSignal(bool)
    settings_requested = pyqtSignal()

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self._available = False
        self._backend = ""
        self._initialization_started = False
        self._import_tasks = []
        self._probe_tasks = []
        self._command_tasks = []
        self._native_host = None
        self._pending_initial_url = ""
        self._persistent_profile = None
        self._persistent_page = None
        self._guest_profile = None
        self._guest_page = None
        self._zoom_factor = 1.0
        self._device_mode = False
        self._library_dialog = None
        self._build_shell()
        self._status_poll_timer = QTimer(self)
        self._status_poll_timer.setInterval(1500)
        self._status_poll_timer.timeout.connect(self._poll_native_status)
        self.apply_theme()

    def _build_shell(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(8)
        self.toolbar_frame = QFrame()
        self.toolbar_frame.setObjectName("BrowserToolbar")
        toolbar = QHBoxLayout(self.toolbar_frame)
        toolbar.setDirection(QBoxLayout.Direction.LeftToRight)
        toolbar.setContentsMargins(8, 7, 8, 7)
        toolbar.setSpacing(5)
        self.back_btn = QPushButton()
        self.forward_btn = QPushButton()
        self.reload_btn = QPushButton()
        self.home_btn = QPushButton()
        tooltips = ("חזרה", "קדימה", "רענון", "דף פתיחה")
        for button, tooltip in zip((self.back_btn, self.forward_btn, self.reload_btn, self.home_btn), tooltips):
            button.setFixedSize(36, 36)
            button.setToolTip(tooltip)
            toolbar.addWidget(button)
        self.back_btn.clicked.connect(lambda: self._run_browser_command("back"))
        self.forward_btn.clicked.connect(lambda: self._run_browser_command("forward"))
        self.reload_btn.clicked.connect(lambda: self._run_browser_command("reload"))
        self.home_btn.clicked.connect(self.show_home)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("כתובת אתר או חיפוש")
        self.url_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.url_edit.returnPressed.connect(self._navigate_from_bar)
        self._navigation_model = QStringListModel(self)
        self._navigation_completer = QCompleter(self._navigation_model, self)
        self._navigation_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._navigation_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._navigation_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._navigation_completer.activated[str].connect(self._navigate_suggestion)
        self.url_edit.setCompleter(self._navigation_completer)
        self._refresh_imported_navigation_suggestions()
        toolbar.addWidget(self.url_edit, 1)
        self.profile_combo = NoScrollComboBox()
        self.profile_combo.addItem("פרופיל סמארטי", "persistent")
        self.profile_combo.addItem("אורח זמני", "guest")
        self.profile_combo.setFixedWidth(160)
        self.profile_combo.setFixedHeight(38)
        self.profile_combo.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.profile_combo.currentIndexChanged.connect(self._switch_profile)
        toolbar.addWidget(self.profile_combo)
        self.more_btn = QPushButton()
        self.more_btn.setFixedSize(36, 36)
        self.more_btn.setToolTip("אפשרויות דפדפן")
        self.more_btn.clicked.connect(self._show_more_menu)
        toolbar.addWidget(self.more_btn)
        layout.addWidget(self.toolbar_frame)
        self.web_host = QStackedWidget()
        self.unavailable = QLabel("מכין את הדפדפן המובנה…")
        self.unavailable.setWordWrap(True)
        self.unavailable.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.web_host.addWidget(self.unavailable)
        layout.addWidget(self.web_host, 1)

    def _start_webengine_probe(self):
        if self._initialization_started:
            return
        self._initialization_started = True
        task = _WebEngineProbeWorker()
        self._probe_tasks.append(task)

        def ready(healthy, _error):
            try:
                self._probe_tasks.remove(task)
            except ValueError:
                pass
            if not healthy:
                self._initialize_native_browser()
                return
            self._initialize_webengine()

        task.signals.ready.connect(ready)
        QThreadPool.globalInstance().start(task)

    def _initialize_webengine(self):
        try:
            from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except Exception:
            self.availability_changed.emit(False)
            return
        profile_root = os.path.join(os.environ.get("LOCALAPPDATA", USER_DATA_DIR), SMARTI_BROWSER_PROFILE_NAME)
        storage = os.path.join(profile_root, "Profile")
        cache = os.path.join(profile_root, "Cache")
        os.makedirs(storage, exist_ok=True)
        os.makedirs(cache, exist_ok=True)
        self._persistent_profile = QWebEngineProfile("SmartiBrowser", self)
        self._persistent_profile.setPersistentStoragePath(storage)
        self._persistent_profile.setCachePath(cache)
        self._persistent_profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self._persistent_profile.downloadRequested.connect(self._handle_download)
        self._default_user_agent = self._persistent_profile.httpUserAgent()
        self._persistent_page = QWebEnginePage(self._persistent_profile, self)
        self.view = QWebEngineView()
        self.view.setPage(self._persistent_page)
        self.web_host.addWidget(self.view)
        self.web_host.setCurrentWidget(self.view)
        self.view.urlChanged.connect(self._on_url_changed)
        self.view.titleChanged.connect(self._on_title_changed)
        self.view.loadProgress.connect(self._on_progress)
        self._available = True
        self._backend = "webengine"
        self.availability_changed.emit(True)
        self.show_home()

    def show_home(self):
        if self._backend == "webengine" and hasattr(self, "view"):
            text_color = TEXT_COLOR
            muted = MUTED_TEXT_COLOR
            background = BG_ELEVATED_COLOR
            accent = ACCENT_COLOR
            html_text = f"""
                <!doctype html><html dir='rtl'><head><meta charset='utf-8'>
                <style>
                  html,body{{height:100%;margin:0;background:{background};color:{text_color};font-family:'Segoe UI',Arial}}
                  main{{height:100%;display:flex;align-items:center;justify-content:center;text-align:center}}
                  .globe{{font-size:58px;color:{accent};line-height:1;margin-bottom:22px}}
                  h1{{font-size:24px;margin:0 0 12px}} p{{font-size:15px;color:{muted};margin:0}}
                </style></head><body><main><section><div class='globe'>◎</div>
                <h1>מתחילים לגלוש</h1><p>הקלד כתובת או חיפוש בשורת הכתובת</p></section></main></body></html>
            """
            self.view.setHtml(html_text, QUrl("about:blank"))
            self.url_edit.clear()
            return
        self.navigate("about:blank")

    def _initialize_native_browser(self, profile_mode="persistent"):
        self.unavailable.setText("מפעיל את הדפדפן המוטמע של Windows…")
        host = NativeChromiumHost(self.core, profile_mode=profile_mode, parent=self.web_host)
        self._native_host = host
        self.web_host.addWidget(host)
        self.web_host.setCurrentWidget(host)

        def ready(ok, error):
            if host is not self._native_host:
                return
            if not ok:
                self._available = False
                self._backend = ""
                self.web_host.setCurrentWidget(self.unavailable)
                self.unavailable.setText(error or "לא ניתן היה להפעיל את הדפדפן המוטמע.")
                self.availability_changed.emit(False)
                return
            self._available = True
            self._backend = "native"
            self.url_edit.setText(host.current_url if host.current_url != "about:blank" else "")
            self.activity_changed.emit("דפדפן", host.current_url, 100)
            self.availability_changed.emit(True)
            self._status_poll_timer.start()
            configured = str(self.core.settings.get("browser_download_dir") or "").strip()
            download_dir = configured if configured and os.path.isdir(configured) else resolve_workspace_root(self.core)
            self._run_browser_command("download_dir", download_dir)
            if self._pending_initial_url and self._pending_initial_url != host.current_url:
                pending = self._pending_initial_url
                self._pending_initial_url = ""
                self.navigate(pending)

        host.ready.connect(ready)
        host.start(self._pending_initial_url or "about:blank")

    def _run_browser_command(self, action, value=None, callback=None):
        if self._backend == "webengine" and hasattr(self, "view"):
            if action == "back":
                self.view.back()
            elif action == "forward":
                self.view.forward()
            elif action == "reload":
                self.view.reload()
            elif action == "navigate":
                self.view.setUrl(QUrl.fromUserInput(str(value or "about:blank")))
            return
        host = self._native_host
        if host is None or not host.is_ready():
            if action == "navigate":
                self._pending_initial_url = str(value or "about:blank")
            return
        task = _BrowserCdpWorker(host.endpoint, host.target_id, action, value)
        self._command_tasks.append(task)

        def ready(payload, error):
            try:
                self._command_tasks.remove(task)
            except ValueError:
                pass
            if payload:
                host.target_id = str(payload.get("target_id") or host.target_id)
                host.current_url = str(payload.get("url") or host.current_url)
                self.url_edit.setText("" if host.current_url == "about:blank" else host.current_url)
                self.activity_changed.emit(
                    str(payload.get("title") or "דפדפן"), host.current_url, 100
                )
            if error:
                self.unavailable.setToolTip(error)
            if callable(callback):
                callback(payload or {}, error)

        task.signals.ready.connect(ready)
        QThreadPool.globalInstance().start(task)

    def _poll_native_status(self):
        if self._backend != "native" or not self._available:
            return
        if any(getattr(task, "action", "") == "status" for task in self._command_tasks):
            return
        self._run_browser_command("status")

    def is_available(self):
        return self._available

    def ensure_background_ready(self, initial_url=""):
        if not self._initialization_started:
            if initial_url and initial_url != "about:blank":
                self._pending_initial_url = str(initial_url)
            self._start_webengine_probe()
            return True
        if initial_url and initial_url != "about:blank":
            self._pending_initial_url = str(initial_url)
        if self._backend == "native" and self._native_host is not None and not self._native_host.is_ready():
            self._available = False
            self._native_host.start(self._pending_initial_url or initial_url or "about:blank")
            return True
        if not self._available:
            return self._native_host is not None
        if self.profile_combo.currentData() != "persistent":
            self.profile_combo.setCurrentIndex(0)
        if (
            self._backend == "webengine"
            and initial_url and initial_url != "about:blank"
            and self._persistent_page.url().toString() in {"", "about:blank"}
        ):
            self._persistent_page.setUrl(QUrl.fromUserInput(initial_url))
        elif self._backend == "native" and initial_url and initial_url != "about:blank":
            self.navigate(initial_url)
        return True

    def navigate(self, value):
        value = str(value or "").strip()
        if not value:
            return
        if "://" not in value and not value.startswith(("about:", "file:")):
            if "." in value and " " not in value:
                value = "https://" + value
            else:
                from urllib.parse import quote_plus
                value = "https://www.google.com/search?q=" + quote_plus(value)
        if not self._initialization_started:
            self._pending_initial_url = value
            self._start_webengine_probe()
            return
        if not self._available:
            self._pending_initial_url = value
            if self._native_host is not None and not self._native_host.is_ready():
                self._native_host.start(value)
            return
        self._run_browser_command("navigate", value)

    def _navigate_from_bar(self):
        self.navigate(self.url_edit.text())

    def _navigate_suggestion(self, value):
        value = str(value or "")
        self.navigate(value.rsplit(" — ", 1)[-1])

    def _on_url_changed(self, url):
        text = url.toString()
        self.url_edit.setText(text)
        self.activity_changed.emit(self.view.title() or "דפדפן", text, 100)

    def _on_title_changed(self, title):
        self.activity_changed.emit(str(title or "דפדפן"), self.view.url().toString(), 100)

    def _on_progress(self, progress):
        self.activity_changed.emit(self.view.title() or "טוען…", self.view.url().toString(), int(progress))

    def current_preview(self):
        if not self._available:
            return QPixmap()
        try:
            if self._backend == "webengine":
                return self.view.grab()
            return self._native_host.capture()
        except Exception:
            return QPixmap()

    def _switch_profile(self, _index):
        mode = self.profile_combo.currentData()
        if self._backend == "native" or self._native_host is not None:
            old_host = self._native_host
            current_url = old_host.current_url if old_host is not None else "about:blank"
            if old_host is not None:
                old_host.stop()
                self.web_host.removeWidget(old_host)
                old_host.deleteLater()
            self._available = False
            self._backend = ""
            self._native_host = None
            self._pending_initial_url = current_url
            self._initialize_native_browser(profile_mode=mode)
            return
        if not self._available:
            return
        if mode == "persistent":
            self.view.setPage(self._persistent_page)
            return
        if self._guest_page is None:
            from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
            self._guest_profile = QWebEngineProfile(self)
            self._guest_profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
            self._guest_page = QWebEnginePage(self._guest_profile, self)
        self.view.setPage(self._guest_page)
        if self._guest_page.url().isEmpty():
            self._guest_page.setUrl(QUrl("about:blank"))

    def _show_more_menu(self):
        menu = QMenu(self)
        prepare_popup_menu(menu)

        def add_action(label, callback, *icon_names):
            action = menu.addAction(label)
            icon = themed_icon(*icon_names)
            if not icon.isNull():
                action.setIcon(icon)
            action.triggered.connect(callback)
            return action

        add_action("חיפוש בדף…", self._find_in_page, "browser_find_icon")
        zoom_icon = themed_icon("browser_zoom_icon")
        zoom = menu.addMenu(zoom_icon, "מרחק תצוגה") if not zoom_icon.isNull() else menu.addMenu("מרחק תצוגה")
        prepare_popup_menu(zoom)
        for label, factor in (("80%", 0.8), ("90%", 0.9), ("100%", 1.0), ("110%", 1.1), ("125%", 1.25)):
            action = zoom.addAction(label)
            action.setCheckable(True)
            action.setChecked(abs(self._zoom_factor - factor) < 0.01)
            action.triggered.connect(lambda checked=False, value=factor: self._set_zoom(value))
        device = add_action("הצגת סרגל מכשיר", self._toggle_device_mode, "browser_device_icon")
        device.setCheckable(True)
        device.setChecked(self._device_mode)
        add_action("צילום מסך", self._take_screenshot, "browser_screenshot_icon")
        menu.addSeparator()
        add_action("ייבוא חד-פעמי מדפדפן קיים", self._show_import_dialog, "browser_import_icon")
        add_action("סיסמאות ומילוי אוטומטי", self._show_passwords_autofill_info, "browser_passwords_icon")
        add_action("הורדות", self._open_downloads, "browser_downloads_icon")
        add_action("היסטוריה וסימניות", self._show_browser_library, "browser_history_icon")
        add_action("פתיחה בדפדפן ברירת המחדל", self._open_external, "browser_external_icon")
        menu.addSeparator()
        add_action("ניקוי נתוני גלישה…", self._clear_browsing_data, "browser_clear_data_icon")
        add_action("הגדרות דפדפן", self.settings_requested.emit, "browser_settings_icon")
        menu.popup(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))

    def _find_in_page(self):
        query, accepted = themed_text_input(self, "חיפוש בדף", "טקסט לחיפוש:")
        if not accepted or not str(query or "").strip():
            return
        if self._backend == "webengine" and hasattr(self, "view"):
            self.view.findText(str(query))
        else:
            self._run_browser_command("find", str(query))

    def _set_zoom(self, factor):
        self._zoom_factor = max(0.5, min(2.0, float(factor or 1.0)))
        if self._backend == "webengine" and hasattr(self, "view"):
            self.view.setZoomFactor(self._zoom_factor)
        else:
            self._run_browser_command("zoom", self._zoom_factor)

    def _toggle_device_mode(self, enabled):
        self._device_mode = bool(enabled)
        if self._backend == "webengine" and self._persistent_profile is not None:
            user_agent = (
                "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"
                if self._device_mode else str(getattr(self, "_default_user_agent", "") or "")
            )
            self._persistent_profile.setHttpUserAgent(user_agent)
            if hasattr(self, "view"):
                self.view.reload()
        else:
            self._run_browser_command("device_mode", self._device_mode)

    def _take_screenshot(self):
        capture_dir = os.path.join(resolve_workspace_root(self.core), "Browser_Captures")
        os.makedirs(capture_dir, exist_ok=True)
        default_path = os.path.join(capture_dir, datetime.now().strftime("browser-%Y%m%d-%H%M%S.png"))
        path, _ = QFileDialog.getSaveFileName(self, "שמירת צילום מסך", default_path, "PNG (*.png)")
        if not path:
            return
        if self._backend == "webengine" and hasattr(self, "view"):
            if not self.view.grab().save(path, "PNG"):
                QMessageBox.warning(self, "צילום מסך", "שמירת צילום המסך נכשלה.")
        else:
            self._run_browser_command("screenshot", path)

    def _show_browser_library(self):
        payload = self._read_imported_navigation()
        if not (payload.get("history") or payload.get("bookmarks")):
            QMessageBox.information(self, "ספריית הדפדפן", "עדיין לא יובאו היסטוריה או סימניות.")
            return
        self._library_dialog = BrowserLibraryDialog(payload, self.navigate, self)
        self._library_dialog.exec()
        self._library_dialog = None

    def _show_passwords_autofill_info(self):
        QMessageBox.information(
            self,
            "סיסמאות ומילוי אוטומטי",
            "Smarti Browser שומר עוגיות והתחברויות בפרופיל המבודד שלו. סיסמאות שמורות אינן מועתקות "
            "מדפדפנים אחרים; אפשר להיכנס ידנית לאתר והחיבור יישמר בפרופיל סמארטי.",
        )

    def _open_downloads(self):
        configured = str(self.core.settings.get("browser_download_dir") or "").strip()
        target = configured if configured else resolve_workspace_root(self.core)
        os.makedirs(target, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _clear_browsing_data(self):
        answer = QMessageBox.question(
            self,
            "ניקוי נתוני גלישה",
            "למחוק עוגיות, מטמון, היסטוריה וסימניות שיובאו לפרופיל Smarti Browser?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self._persistent_profile is not None:
            self._persistent_profile.cookieStore().deleteAllCookies()
            self._persistent_profile.clearHttpCache()
        if self._backend == "native":
            self._run_browser_command("clear")
        try:
            os.remove(self._navigation_path())
        except FileNotFoundError:
            pass
        self._refresh_imported_navigation_suggestions()

    @staticmethod
    def _navigation_path():
        return os.path.join(USER_DATA_DIR, "browser", "imported_navigation.json")

    def _read_imported_navigation(self):
        try:
            with open(self._navigation_path(), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _refresh_imported_navigation_suggestions(self):
        payload = self._read_imported_navigation()
        suggestions = []
        for item in (payload.get("bookmarks") or []) + (payload.get("history") or [])[:1000]:
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if url:
                suggestions.append(f"{title} — {url}" if title else url)
        self._navigation_model.setStringList(list(dict.fromkeys(suggestions))[:1500])

    def _add_imported_navigation_menus(self, menu):
        payload = self._read_imported_navigation()
        for label, key, limit in (("סימניות מיובאות", "bookmarks", 40), ("היסטוריה מיובאת", "history", 30)):
            records = payload.get(key) or []
            if not records:
                continue
            submenu = menu.addMenu(label)
            for item in records[:limit]:
                url = str(item.get("url") or "")
                title = str(item.get("title") or url or "אתר")[:64]
                submenu.addAction(title, lambda checked=False, target=url: self.navigate(target))

    def _open_external(self):
        if not self._available:
            return
        if self._backend == "webengine":
            QDesktopServices.openUrl(self.view.url())
        elif self._native_host is not None:
            QDesktopServices.openUrl(QUrl.fromUserInput(self._native_host.current_url))

    def _clear_guest(self):
        if self._guest_profile is not None:
            self._guest_profile.cookieStore().deleteAllCookies()
            self._guest_profile.clearHttpCache()
        if self._backend == "native" and self.profile_combo.currentData() == "guest":
            self._run_browser_command("clear")

    def _show_import_dialog(self):
        sources = discover_browser_profiles()
        if not sources:
            QMessageBox.information(self, "ייבוא נתוני גלישה", "לא נמצא במחשב פרופיל דפדפן נתמך לייבוא.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("ייבוא חד-פעמי ל-Smarti Browser")
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        explanation = QLabel(
            "הייבוא מעתיק נתונים לפרופיל הנפרד של סמארטי ואינו משנה את הדפדפן המקורי. "
            "סיסמאות אינן מיובאות; עוגיות מוגנות שאינן ניתנות לפענוח יידלגו."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        source_combo = QComboBox()
        for source in sources:
            source_combo.addItem(source.label, source)
        layout.addWidget(source_combo)
        cookies = QCheckBox("עוגיות והתחברויות פעילות")
        history = QCheckBox("היסטוריית גלישה")
        bookmarks = QCheckBox("סימניות")
        cookies.setChecked(True)
        history.setChecked(True)
        bookmarks.setChecked(True)
        layout.addWidget(cookies)
        layout.addWidget(history)
        layout.addWidget(bookmarks)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("ייבוא")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = source_combo.currentData()
        task = _BrowserImportWorker(source, cookies.isChecked(), history.isChecked(), bookmarks.isChecked())
        self._import_tasks.append(task)
        self.more_btn.setEnabled(False)
        self.more_btn.setToolTip("מייבא נתוני גלישה…")

        def ready(payload, error):
            self.more_btn.setEnabled(True)
            self.more_btn.setToolTip("")
            try:
                self._import_tasks.remove(task)
            except ValueError:
                pass
            if error:
                QMessageBox.warning(self, "ייבוא נתוני גלישה", error)
                return
            self._apply_import_payload(payload)

        task.signals.ready.connect(ready)
        QThreadPool.globalInstance().start(task)

    def show_import_dialog(self):
        self._show_import_dialog()

    def _apply_import_payload(self, payload):
        source_cookies = list(payload.get("cookies") or [])
        imported_cookies = 0
        if self._backend == "webengine" and self._persistent_profile is not None:
            store = self._persistent_profile.cookieStore()
            for item in source_cookies:
                try:
                    cookie = QNetworkCookie(item["name"].encode("utf-8"), str(item.get("value") or "").encode("utf-8"))
                    cookie.setDomain(str(item.get("domain") or ""))
                    cookie.setPath(str(item.get("path") or "/"))
                    cookie.setSecure(bool(item.get("secure")))
                    cookie.setHttpOnly(bool(item.get("http_only")))
                    expires = str(item.get("expires_at") or "")
                    if expires:
                        cookie.setExpirationDate(QDateTime.fromString(expires, Qt.DateFormat.ISODate))
                    scheme = "https" if item.get("secure") else "http"
                    origin = QUrl(f"{scheme}://{str(item.get('domain') or '').lstrip('.')}/")
                    store.setCookie(cookie, origin)
                    imported_cookies += 1
                except Exception:
                    continue
        elif self._backend == "native" and self._native_host is not None:
            playwright_cookies = []
            for item in source_cookies:
                domain = str(item.get("domain") or "").strip()
                name = str(item.get("name") or "").strip()
                if not domain or not name:
                    continue
                cookie = {
                    "name": name,
                    "value": str(item.get("value") or ""),
                    "domain": domain,
                    "path": str(item.get("path") or "/"),
                    "secure": bool(item.get("secure")),
                    "httpOnly": bool(item.get("http_only")),
                }
                expires = QDateTime.fromString(str(item.get("expires_at") or ""), Qt.DateFormat.ISODate)
                if expires.isValid() and expires.toSecsSinceEpoch() > 0:
                    cookie["expires"] = float(expires.toSecsSinceEpoch())
                playwright_cookies.append(cookie)
            imported_cookies = len(playwright_cookies)
            self._run_browser_command("cookies", playwright_cookies)
        navigation_path = self._navigation_path()
        os.makedirs(os.path.dirname(navigation_path), exist_ok=True)
        with open(navigation_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "source": payload.get("source") or {},
                    "history": payload.get("history") or [],
                    "bookmarks": payload.get("bookmarks") or [],
                    "imported_at": payload.get("imported_at") or "",
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        self.core.settings["browser_profile_import"] = {
            "completed_at": payload.get("imported_at") or "",
            "source": payload.get("source") or {},
            "history_count": len(payload.get("history") or []),
            "bookmark_count": len(payload.get("bookmarks") or []),
            "cookie_count": imported_cookies,
        }
        self.core._save_settings()
        self._refresh_imported_navigation_suggestions()
        stats = payload.get("cookie_stats") or {}
        skipped = int(stats.get("unrecovered_encrypted", stats.get("skipped_encrypted", 0)) or 0)
        recovered = int(stats.get("recovered_via_source_browser") or 0)
        extra = f" {recovered} עוגיות מוגנות שוחזרו דרך מנוע הדפדפן המקורי." if recovered else ""
        if skipped:
            extra += f" {skipped} עוגיות מוגנות לא היו ניתנות להעברה."
        QMessageBox.information(
            self,
            "הייבוא הושלם",
            f"יובאו {imported_cookies} עוגיות, {len(payload.get('history') or [])} רשומות היסטוריה "
            f"ו-{len(payload.get('bookmarks') or [])} סימניות.{extra}",
        )

    def shutdown(self):
        self._status_poll_timer.stop()
        if self._native_host is not None:
            self._native_host.stop()

    def _handle_download(self, item):
        configured = str(self.core.settings.get("browser_download_dir") or "").strip()
        target_dir = configured if configured and os.path.isdir(configured) else resolve_workspace_root(self.core)
        item.setDownloadDirectory(target_dir)
        item.accept()

    def apply_theme(self):
        self.setStyleSheet(f"background: {BG_ELEVATED_COLOR}; color: {TEXT_COLOR};")
        self.toolbar_frame.setStyleSheet(
            f"QFrame#BrowserToolbar {{ background: {GLASS_COLOR}; border: none; border-radius: 17px; }}"
        )
        button_css = (
            f"QPushButton {{ background: transparent; color: {TEXT_COLOR}; border: none; "
            "border-radius: 10px; padding: 0px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; }}"
        )
        for button in (self.back_btn, self.forward_btn, self.reload_btn, self.home_btn, self.more_btn):
            button.setStyleSheet(button_css)
        set_themed_button_icon(self.back_btn, ("workspace_browser_back_icon", "back_icon"), "‹", 18, clear_text=True)
        set_themed_button_icon(self.forward_btn, ("workspace_browser_forward_icon",), "›", 18, clear_text=True)
        set_themed_button_icon(self.reload_btn, ("workspace_browser_reload_icon", "reset_icon"), "↻", 18, clear_text=True)
        set_themed_button_icon(self.home_btn, ("workspace_browser_home_icon",), "⌂", 18, clear_text=True)
        set_themed_button_icon(self.more_btn, ("browser_more_icon",), "⋮", 18, clear_text=True)
        self.url_edit.setStyleSheet(
            f"QLineEdit {{ background: {FIELD_COLOR}; color: {FIELD_TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 18px; padding: 8px 14px; selection-background-color: " + ACCENT_TINT_STRONG + "; }}"
        )
        self.profile_combo.setStyleSheet(
            f"QComboBox {{ background: {FIELD_COLOR}; color: {FIELD_TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 18px; padding: 7px 13px; font-size: 12px; font-weight: 700; }}"
            f"QComboBox:hover {{ background: {FIELD_HOVER_COLOR}; border-color: {LINE_COLOR}; }}"
            f"QComboBox::drop-down {{ border: none; width: 24px; }}"
            f"QComboBox QAbstractItemView {{ background: {MENU_BG_COLOR}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "selection-background-color: " + ACCENT_TINT_STRONG + "; padding: 5px; }}"
        )
        self.unavailable.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; padding: 30px;")


class WorkspaceTerminalPanel(QWidget):
    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.root_path = resolve_workspace_root(core)
        self._started = False
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._process_finished)
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.output, 1)
        row = QHBoxLayout()
        row.setDirection(QBoxLayout.Direction.LeftToRight)
        self.prompt = QLabel("PS ›")
        row.addWidget(self.prompt)
        self.input = QLineEdit()
        self.input.setPlaceholderText("הקלד פקודה ולחץ Enter")
        self.input.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.input.returnPressed.connect(self.send_command)
        row.addWidget(self.input, 1)
        self.restart_btn = QPushButton("הפעלה מחדש")
        self.restart_btn.clicked.connect(self.start_shell)
        row.addWidget(self.restart_btn)
        layout.addLayout(row)

    def start_shell(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1500)
        self.output.clear()
        self.output.appendPlainText(f"Smarti Terminal — {self.root_path}\n")
        self.process.setWorkingDirectory(self.root_path)
        executable = shutil.which("pwsh.exe") or shutil.which("powershell.exe") or "powershell.exe"
        self.process.start(executable, ["-NoLogo", "-NoProfile", "-NoExit", "-Command", "-"])
        self._started = True

    def ensure_started(self):
        if not self._started or self.process.state() == QProcess.ProcessState.NotRunning:
            self.start_shell()

    def send_command(self):
        command = self.input.text().rstrip()
        if not command:
            return
        self.output.appendPlainText(f"PS › {command}")
        self.process.write((command + "\r\n").encode("utf-8"))
        self.input.clear()

    def _read_output(self):
        data = bytes(self.process.readAllStandardOutput())
        for encoding in ("utf-8", "cp1255", "cp1252"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = data.decode("utf-8", errors="replace")
        self.output.moveCursor(QTextCursor.MoveOperation.End)
        self.output.insertPlainText(text)
        self.output.moveCursor(QTextCursor.MoveOperation.End)

    def _process_finished(self):
        self.output.appendPlainText("\nהמסוף הסתיים. אפשר להפעיל אותו מחדש.")

    def shutdown(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.process.terminate()
        if not self.process.waitForFinished(1200):
            self.process.kill()
            self.process.waitForFinished(1200)

    def apply_theme(self):
        self.setStyleSheet(f"background: {BG_ELEVATED_COLOR}; color: {TEXT_COLOR};")
        self.output.setStyleSheet(
            f"background: {CODE_BG_COLOR}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 12px; padding: 10px; font-family: Consolas; font-size: 12px;"
        )
        self.input.setStyleSheet(
            f"background: {FIELD_COLOR}; color: {FIELD_TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 12px; padding: 9px; font-family: Consolas;"
        )
        self.prompt.setStyleSheet(f"color: {ACCENT_COLOR}; font-weight: 800;")
        self.restart_btn.setStyleSheet(SECONDARY_BUTTON_CSS)


class WorkspaceArtifactsPanel(QWidget):
    open_requested = pyqtSignal(str)

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.root_path = resolve_workspace_root(core)
        self._scan_tasks = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        header = QHBoxLayout()
        title = QLabel("תוצרים שנוצרו או עודכנו בשיחה")
        title.setStyleSheet(page_title_css(17))
        header.addWidget(title)
        header.addStretch()
        self.refresh_btn = QPushButton("רענון")
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda item: self.open_requested.emit(str(item.data(Qt.ItemDataRole.UserRole) or "")))
        layout.addWidget(self.list, 1)
        self.apply_theme()

    def refresh(self):
        self.root_path = resolve_workspace_root(self.core)
        self.list.clear()
        self.list.addItem("סורק את תיקיית העבודה…")
        since_timestamp = 0
        try:
            created_at = str((self.core.active_chat_session_metadata() or {}).get("created_at") or "")
            if created_at:
                since_timestamp = datetime.fromisoformat(created_at).timestamp()
        except Exception:
            since_timestamp = 0
        task = _ArtifactScanWorker(self.root_path, since_timestamp=since_timestamp)
        self._scan_tasks.append(task)

        def ready(records, error):
            try:
                self._scan_tasks.remove(task)
            except ValueError:
                pass
            self.list.clear()
            if error:
                self.list.addItem(error)
                return
            if not records:
                self.list.addItem("עדיין אין תוצרים בתיקיית העבודה")
                return
            for modified, size, path in records:
                relative = os.path.relpath(path, self.root_path)
                stamp = datetime.fromtimestamp(modified).strftime("%d/%m/%Y %H:%M")
                item = QListWidgetItem(f"{relative}\n{stamp} · {self._format_size(size)}")
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                self.list.addItem(item)

        task.signals.ready.connect(ready)
        QThreadPool.globalInstance().start(task)

    @staticmethod
    def _format_size(value):
        size = float(value or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024

    def apply_theme(self):
        self.setStyleSheet(f"background: {BG_ELEVATED_COLOR}; color: {TEXT_COLOR};")
        self.refresh_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        self.list.setStyleSheet(
            f"QListWidget {{ background: {GLASS_COLOR}; color: {TEXT_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; "
            "border-radius: 12px; padding: 6px; }}"
            f"QListWidget::item {{ padding: 9px; border-radius: 9px; }} QListWidget::item:hover {{ background: {HOVER_TINT}; }}"
            f"QListWidget::item:selected {{ background: {ACCENT_TINT_STRONG}; }}"
        )


class WorkspaceWorkbench(QFrame):
    close_requested = pyqtSignal()
    visibility_changed = pyqtSignal(bool)
    panel_closed = pyqtSignal(str)
    browser_settings_requested = pyqtSignal()

    PANEL_KEYS = ("files", "browser", "terminal", "canvas", "artifacts")

    def __init__(self, core, canvas_widget, parent=None, browser_panel=None):
        super().__init__(parent)
        self.core = core
        self.setObjectName("WorkspaceWorkbench")
        self._open = False
        self._panels = {}
        self._panel_kinds = {}
        self._panel_counters = {}
        self._terminals = []
        self._canvas_widget = canvas_widget
        self.browser_panel = browser_panel or WorkspaceBrowserPanel(self.core)
        if hasattr(self.browser_panel, "settings_requested"):
            self.browser_panel.settings_requested.connect(self.browser_settings_requested.emit)
        self.files_panel = None
        self.terminal_panel = None
        self.artifacts_panel = None
        self._build_ui(canvas_widget, browser_panel=browser_panel)
        self.apply_theme()

    def _build_ui(self, canvas_widget, browser_panel=None):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setDirection(QBoxLayout.Direction.LeftToRight)
        header.setContentsMargins(4, 2, 4, 8)
        header.setSpacing(6)
        self.context_label = QLabel(Path(resolve_workspace_root(self.core)).name or "Smarti")
        self.context_label.setToolTip(resolve_workspace_root(self.core))
        self.context_label.setMaximumWidth(190)
        self.context_label.setMinimumWidth(76)
        header.addWidget(self.context_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(False)
        self.tabs.setDrawBase(False)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        header.addWidget(self.tabs, 1)
        self.add_tab_btn = QPushButton("+")
        self.add_tab_btn.setFixedSize(36, 36)
        self.add_tab_btn.setToolTip("פתיחת לשונית")
        self.add_tab_btn.clicked.connect(self._show_add_menu)
        header.addWidget(self.add_tab_btn)
        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.setToolTip("סגירת סביבת העבודה")
        self.close_btn.clicked.connect(self.close_requested)
        self.close_btn.hide()
        layout.addLayout(header)
        self.stack = QStackedWidget()
        self.stack.setObjectName("WorkspaceTabStack")
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setContentsMargins(28, 28, 28, 28)
        empty_layout.addStretch()
        self.empty_title = QLabel("מה תרצה לפתוח?")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_actions = QWidget()
        action_layout = QVBoxLayout(self.empty_actions)
        action_layout.setContentsMargins(0, 12, 0, 12)
        action_layout.setSpacing(5)
        for kind, label, icons, fallback in (
            ("files", "קבצים", ("folder_icon", "file_icon"), "▣"),
            ("browser", "דפדפן", ("workspace_browser_icon",), "◎"),
            ("terminal", "מסוף", ("workspace_terminal_icon",), ">_"),
        ):
            button = QPushButton(label)
            button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda checked=False, panel_kind=kind: self.add_panel(panel_kind, force_new=True))
            button.setProperty("workspaceIconNames", icons)
            self._refresh_optional_button_icon(button)
            action_layout.addWidget(button)
        empty_layout.addWidget(self.empty_actions, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        self.stack.addWidget(self.empty_page)
        layout.addWidget(self.stack, 1)
        self.stack.setCurrentWidget(self.empty_page)
        self._refresh_tabs_visibility()

    def _tab_changed(self, index):
        tab_id = str(self.tabs.tabData(index) or "")
        panel = self._panels.get(tab_id)
        if panel is not None:
            self.stack.setCurrentWidget(panel)
        else:
            self.stack.setCurrentWidget(self.empty_page)
            return
        kind = self._panel_kinds.get(tab_id, "")
        if kind == "artifacts" and hasattr(panel, "refresh"):
            panel.refresh()
        elif kind == "terminal" and hasattr(panel, "ensure_started"):
            panel.ensure_started()

    def _next_title(self, kind):
        labels = {"files": "קבצים", "browser": "דפדפן", "terminal": "מסוף", "canvas": "קנבס", "artifacts": "תוצרים"}
        base = labels.get(kind, kind)
        used = set()
        for index in range(self.tabs.count()):
            tab_id = str(self.tabs.tabData(index) or "")
            if self._panel_kinds.get(tab_id) != kind:
                continue
            label = str(self.tabs.tabText(index) or "")
            if label == base:
                used.add(1)
            elif label.startswith(base + " ") and label[len(base) + 1:].isdigit():
                used.add(int(label[len(base) + 1:]))
        count = 1
        while count in used:
            count += 1
        return base, count

    def _panel_for_kind(self, kind, force_new=False):
        if kind == "canvas":
            return self._canvas_widget
        if kind == "browser":
            primary_attached = any(panel is self.browser_panel for panel in self._panels.values())
            panel = WorkspaceBrowserPanel(self.core) if force_new and primary_attached else self.browser_panel
            if panel is not self.browser_panel:
                panel.settings_requested.connect(self.browser_settings_requested.emit)
            return panel
        if kind == "files":
            return WorkspaceFilePanel(self.core)
        if kind == "terminal":
            panel = WorkspaceTerminalPanel(self.core)
            self._terminals.append(panel)
            return panel
        if kind == "artifacts":
            panel = WorkspaceArtifactsPanel(self.core)
            panel.open_requested.connect(self._open_artifact)
            return panel
        return None

    def add_panel(self, kind, force_new=False, title=""):
        kind = str(kind or "").strip().lower()
        if kind not in self.PANEL_KEYS:
            return None
        if kind in {"canvas", "artifacts"}:
            for index in range(self.tabs.count()):
                tab_id = str(self.tabs.tabData(index) or "")
                if self._panel_kinds.get(tab_id) == kind:
                    self.tabs.setCurrentIndex(index)
                    return self._panels.get(tab_id)
        panel = self._panel_for_kind(kind, force_new=force_new)
        if panel is None:
            return None
        label, count = self._next_title(kind)
        if title:
            label = str(title)
        elif count > 1 and kind in {"files", "browser", "terminal"}:
            label = f"{label} {count}"
        tab_id = f"{kind}:{id(panel)}"
        self._panels[tab_id] = panel
        self._panel_kinds[tab_id] = kind
        self.stack.addWidget(panel)
        tab_icons = {
            "files": ("workspace_files_icon", "folder_icon"),
            "browser": ("workspace_browser_icon",),
            "terminal": ("workspace_terminal_icon",),
            "canvas": ("workspace_canvas_icon", "canvas_card_icon"),
            "artifacts": ("workspace_artifacts_icon",),
        }
        icon = themed_icon(*(tab_icons.get(kind) or ()))
        index = self.tabs.addTab(icon, label) if not icon.isNull() else self.tabs.addTab(label)
        self.tabs.setTabData(index, tab_id)
        self._install_tab_close_button(index, tab_id)
        self.tabs.setCurrentIndex(index)
        # Adding the first tab changes QTabBar's current index before its data
        # is attached, so currentChanged can briefly select the empty page.
        self.stack.setCurrentWidget(panel)
        if kind == "files" and self.files_panel is None:
            self.files_panel = panel
        elif kind == "terminal":
            self.terminal_panel = panel
            panel.ensure_started()
        elif kind == "artifacts":
            self.artifacts_panel = panel
            panel.refresh()
        elif kind == "browser":
            panel.ensure_background_ready()
        self._refresh_tabs_visibility()
        return panel

    @staticmethod
    def _refresh_optional_button_icon(button):
        names = tuple(button.property("workspaceIconNames") or ())
        icon = themed_icon(*names)
        button.setIcon(icon)
        if not icon.isNull():
            button.setIconSize(QSize(19, 19))

    def _install_tab_close_button(self, index, tab_id):
        button = QPushButton("×", self.tabs)
        button.setFixedSize(22, 22)
        button.setToolTip("סגירת לשונית")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {MUTED_TEXT_COLOR}; border: none; "
            "border-radius: 11px; padding: 0px; font-size: 16px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; color: {TEXT_COLOR}; }}"
        )
        set_themed_button_icon(button, ("workspace_tab_close_icon",), "×", 13, clear_text=True)
        button.clicked.connect(lambda checked=False, target=tab_id: self._close_tab_by_id(target))
        self.tabs.setTabButton(index, QTabBar.ButtonPosition.LeftSide, button)

    def _close_tab_by_id(self, tab_id):
        for index in range(self.tabs.count()):
            if str(self.tabs.tabData(index) or "") == str(tab_id or ""):
                self.close_tab(index)
                return

    def close_tab(self, index):
        if index < 0 or index >= self.tabs.count():
            return
        tab_id = str(self.tabs.tabData(index) or "")
        panel = self._panels.pop(tab_id, None)
        kind = self._panel_kinds.pop(tab_id, "")
        self.tabs.removeTab(index)
        if panel is not None:
            self.stack.removeWidget(panel)
            panel.hide()
            if kind == "terminal":
                try:
                    panel.shutdown()
                finally:
                    if panel in self._terminals:
                        self._terminals.remove(panel)
                    panel.deleteLater()
            elif kind == "browser" and panel is not self.browser_panel:
                panel.shutdown()
                panel.deleteLater()
            elif panel not in {self.browser_panel, self._canvas_widget}:
                panel.deleteLater()
        self.panel_closed.emit(kind)
        self._refresh_tabs_visibility()
        if self.tabs.count():
            self.tabs.setCurrentIndex(min(index, self.tabs.count() - 1))
        else:
            self.stack.setCurrentWidget(self.empty_page)

    def close_kind(self, kind):
        for index in range(self.tabs.count()):
            tab_id = str(self.tabs.tabData(index) or "")
            if self._panel_kinds.get(tab_id) == kind:
                self.close_tab(index)
                return True
        return False

    def _refresh_tabs_visibility(self):
        self.tabs.setVisible(self.tabs.count() > 0)

    def _artifacts_available(self):
        try:
            if self.core.active_canvas_artifacts():
                return True
        except Exception:
            pass
        root = resolve_workspace_root(self.core)
        try:
            created = str((self.core.active_chat_session_metadata() or {}).get("created_at") or "")
            since = datetime.fromisoformat(created).timestamp() if created else 0
            pending = [(root, 0)]
            inspected = 0
            while pending and inspected < 500:
                folder, depth = pending.pop(0)
                for entry in os.scandir(folder):
                    inspected += 1
                    if entry.is_file(follow_symlinks=False) and entry.stat().st_mtime >= since:
                        return True
                    if depth < 1 and entry.is_dir(follow_symlinks=False):
                        pending.append((entry.path, depth + 1))
                    if inspected >= 500:
                        break
        except Exception:
            pass
        return False

    def _show_add_menu(self):
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        prepare_popup_menu(menu)
        for kind, label, icons in (
            ("files", "קבצים", ("folder_icon", "file_icon")),
            ("browser", "דפדפן", ("workspace_browser_icon",)),
            ("terminal", "מסוף", ("workspace_terminal_icon",)),
        ):
            action = menu.addAction(label)
            icon = themed_icon(*icons)
            if not icon.isNull():
                action.setIcon(icon)
            action.triggered.connect(lambda checked=False, panel_kind=kind: self.add_panel(panel_kind, force_new=True))
        if self._artifacts_available():
            action = menu.addAction("תוצרים")
            icon = themed_icon("workspace_artifacts_icon")
            if not icon.isNull():
                action.setIcon(icon)
            action.triggered.connect(lambda: self.add_panel("artifacts"))
        menu.adjustSize()
        size = menu.sizeHint()
        anchor = self.add_tab_btn.mapToGlobal(self.add_tab_btn.rect().bottomRight())
        menu.popup(anchor - QPoint(size.width(), 0))

    def _open_artifact(self, path):
        if not path:
            return
        panel = self.add_panel("files", force_new=True, title=Path(path).name)
        if panel is not None:
            panel.open_file(path)

    def open_panel(self, key):
        key = str(key or "").strip().lower()
        if key:
            existing = None
            for index in range(self.tabs.count()):
                tab_id = str(self.tabs.tabData(index) or "")
                if self._panel_kinds.get(tab_id) == key:
                    self.tabs.setCurrentIndex(index)
                    existing = self._panels.get(tab_id)
                    break
            if existing is None:
                self.add_panel(key)
        self._open = True
        self.show()
        self.visibility_changed.emit(True)

    def close_panel(self):
        self._open = False
        self.hide()
        self.visibility_changed.emit(False)

    def is_open(self):
        return self._open and self.isVisible()

    def refresh_context(self):
        root = resolve_workspace_root(self.core)
        self.context_label.setText(Path(root).name or "Smarti")
        self.context_label.setToolTip(root)
        for tab_id, panel in self._panels.items():
            kind = self._panel_kinds.get(tab_id)
            if kind == "files":
                panel.set_root(root)
            elif kind == "artifacts":
                panel.root_path = root
            elif kind == "terminal" and panel.root_path != root:
                panel.root_path = root

    def shutdown(self):
        for terminal in list(self._terminals):
            terminal.shutdown()
        if hasattr(self._canvas_widget, "shutdown"):
            self._canvas_widget.shutdown()
        seen = set()
        for panel in list(self._panels.values()) + [self.browser_panel]:
            if id(panel) in seen:
                continue
            seen.add(id(panel))
            if isinstance(panel, WorkspaceBrowserPanel):
                panel.shutdown()

    def apply_theme(self):
        self.setStyleSheet(
            f"QFrame#WorkspaceWorkbench {{ background: {GLASS_STRONG_COLOR}; border: none; border-radius: 18px; }}"
        )
        self.empty_title.setStyleSheet(page_title_css(18))
        self.context_label.setStyleSheet(
            f"color: {MUTED_TEXT_COLOR}; background: transparent; border: none; font-size: 12px; padding: 0 8px;"
        )
        empty_button_css = (
            f"QPushButton {{ text-align: right; background: transparent; color: {TEXT_COLOR}; border: none; "
            "border-radius: 10px; padding: 9px 14px; font-size: 14px; font-weight: 650; min-width: 240px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; }}"
        )
        for button in self.empty_actions.findChildren(QPushButton):
            button.setStyleSheet(empty_button_css)
            self._refresh_optional_button_icon(button)
        self.close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {MUTED_TEXT_COLOR}; border: none; border-radius: 18px; font-size: 24px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; color: {TEXT_COLOR}; }}"
        )
        set_themed_button_icon(self.close_btn, ("close", "close_icon"), "×", 18, clear_text=True)
        self.add_tab_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_COLOR}; border: none; border-radius: 18px; font-size: 23px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; color: {ACCENT_COLOR}; }}"
        )
        set_themed_button_icon(self.add_tab_btn, ("workspace_add_tab_icon", "plus_icon"), "+", 18, clear_text=True)
        self.tabs.setStyleSheet(
            f"QTabBar {{ background: transparent; color: {MUTED_TEXT_COLOR}; }}"
            f"QTabBar::tab {{ background: transparent; color: {MUTED_TEXT_COLOR}; min-height: 24px; "
            f"padding: 7px 14px; margin: 0 2px; border: none; border-radius: 12px; }} "
            f"QTabBar::tab:selected {{ color: {TEXT_COLOR}; background: {FIELD_COLOR}; }}"
            f"QTabBar::tab:hover:!selected {{ background: {HOVER_TINT}; }}"
        )
        self.stack.setStyleSheet("QStackedWidget#WorkspaceTabStack { background: transparent; border: none; }")
        for panel in set(self._panels.values()) | {self.browser_panel}:
            if hasattr(panel, "apply_theme"):
                panel.apply_theme()


class BrowserPreviewCard(QFrame):
    expand_requested = pyqtSignal()

    def __init__(self, browser_panel, parent=None):
        super().__init__(parent)
        self.browser_panel = browser_panel
        self.setObjectName("BrowserPreviewCard")
        self.setFixedSize(236, 142)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 9)
        layout.setSpacing(5)
        row = QHBoxLayout()
        self.title = QLabel("דפדפן")
        self.title.setMaximumWidth(170)
        row.addWidget(self.title, 1)
        self.expand_btn = QPushButton("↗")
        self.expand_btn.setFixedSize(28, 28)
        self.expand_btn.setToolTip("הרחבת תצוגת הדפדפן")
        self.expand_btn.clicked.connect(self.expand_requested)
        row.addWidget(self.expand_btn)
        layout.addLayout(row)
        self.thumbnail = QLabel()
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setMinimumHeight(66)
        layout.addWidget(self.thumbnail, 1)
        self.url = QLabel("")
        self.url.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addWidget(self.url)
        self._timer = QTimer(self)
        self._timer.setInterval(1800)
        self._timer.timeout.connect(self.refresh_thumbnail)
        self._timer.start()
        self.apply_theme()

    def update_activity(self, title, url, progress):
        self.title.setText(str(title or "דפדפן")[:42])
        self.title.setToolTip(str(title or ""))
        self.url.setText(str(url or "")[:52])
        self.url.setToolTip(str(url or ""))
        self.refresh_thumbnail()

    def refresh_thumbnail(self):
        pixmap = self.browser_panel.current_preview()
        if not pixmap.isNull():
            self.thumbnail.setPixmap(
                pixmap.scaled(214, 70, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )

    def apply_theme(self):
        self.setStyleSheet(
            f"QFrame#BrowserPreviewCard {{ background: {GLASS_STRONG_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 16px; }}"
        )
        self.title.setStyleSheet(f"color: {TEXT_COLOR}; font-size: 12px; font-weight: 800;")
        self.url.setStyleSheet(f"color: {SUBTLE_TEXT_COLOR}; font-size: 9px;")
        self.thumbnail.setStyleSheet(f"background: {PANEL_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 8px;")
        self.expand_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT_TINT}; color: {ACCENT_COLOR}; border: none; border-radius: 14px; font-weight: 800; }}"
            f"QPushButton:hover {{ background: {ACCENT_TINT_STRONG}; }}"
        )


class WorkspaceWindowTitleBar(QFrame):
    """Minimal frameless title bar: draggable surface plus native-like controls."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setObjectName("WorkspaceWindowTitleBar")
        self.setFixedHeight(36)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)
        self.minimize_btn = QPushButton()
        self.restore_btn = QPushButton()
        self.close_btn = QPushButton()
        for button in (self.minimize_btn, self.restore_btn, self.close_btn):
            button.setFixedSize(46, 36)
            button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            layout.addWidget(button)
        self.minimize_btn.setToolTip("מזער")
        self.restore_btn.setToolTip("שחזר")
        self.close_btn.setToolTip("סגור")
        self.minimize_btn.clicked.connect(self.window.showMinimized)
        self.restore_btn.clicked.connect(self.toggle_maximized)
        self.close_btn.clicked.connect(self.window.close)
        self.apply_theme()

    def toggle_maximized(self):
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()
        QTimer.singleShot(0, self.sync_state)

    def sync_state(self):
        maximized = self.window.isMaximized()
        self.restore_btn.setToolTip("שחזר" if maximized else "הגדל")
        set_themed_button_icon(
            self.restore_btn,
            ("window_restore_icon",) if maximized else ("window_maximize_icon",),
            "❐" if maximized else "□",
            13,
            clear_text=True,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window.windowHandle()
            if handle is not None and hasattr(handle, "startSystemMove"):
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def apply_theme(self):
        self.setStyleSheet(
            f"QFrame#WorkspaceWindowTitleBar {{ background: {BG_ELEVATED_COLOR}; border: none; }}"
        )
        button_css = (
            f"QPushButton {{ background: transparent; color: {MUTED_TEXT_COLOR}; border: none; border-radius: 0px; padding: 0px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; color: {TEXT_COLOR}; }}"
        )
        self.minimize_btn.setStyleSheet(button_css)
        self.restore_btn.setStyleSheet(button_css)
        self.close_btn.setStyleSheet(
            button_css + "QPushButton:hover { background: #C42B1C; color: white; }"
        )
        set_themed_button_icon(self.minimize_btn, ("window_minimize_icon",), "—", 13, clear_text=True)
        set_themed_button_icon(self.close_btn, ("window_close_icon", "close_icon"), "×", 14, clear_text=True)
        self.sync_state()


class SidebarNavButton(QPushButton):
    """Paint an RTL sidebar item on a stable right-side icon rail."""

    def paintEvent(self, _event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        label = str(option.text or "")
        icon = QIcon(self.icon())
        option.text = ""
        option.icon = QIcon()
        painter = QStylePainter(self)
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)
        content = self.rect().adjusted(10, 0, -10, 0)
        collapsed = bool(self.property("sidebarCollapsed"))
        icon_size = self.iconSize()
        has_icon = not icon.isNull()
        if collapsed:
            if has_icon:
                pixmap = icon.pixmap(icon_size)
                x = (self.width() - pixmap.width()) // 2
                y = (self.height() - pixmap.height()) // 2
                painter.drawPixmap(x, y, pixmap)
            elif label:
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, label)
            return
        icon_left = content.right() + 1
        if has_icon:
            pixmap = icon.pixmap(icon_size)
            icon_left = content.right() - pixmap.width() + 1
            y = (self.height() - pixmap.height()) // 2
            painter.drawPixmap(icon_left, y, pixmap)
        text_right = icon_left - (8 if has_icon else 0)
        text_rect = content.adjusted(0, 0, text_right - content.right(), 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            label,
        )


class WorkspaceSidebar(QFrame):
    new_chat_requested = pyqtSignal()
    workbench_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()
    usage_requested = pyqtSignal()
    diagnostic_requested = pyqtSignal()
    about_requested = pyqtSignal()
    collapsed_changed = pyqtSignal(bool)

    def __init__(self, history_widget, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkspaceSidebar")
        self.history_widget = history_widget
        self._collapsed = False
        self._nav_buttons = []
        self._width_animation = None
        self._build_ui()
        self.apply_theme()

    def _nav_button(self, text, icon_names, callback):
        button = SidebarNavButton(text)
        button.setProperty("fullText", text)
        button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        button.setFixedHeight(42)
        button.clicked.connect(callback)
        set_themed_button_icon(button, icon_names, text[:1], 19, clear_text=False)
        if themed_icon(*icon_names).isNull():
            button.setText(text)
        self._nav_buttons.append((button, icon_names))
        return button

    def _build_ui(self):
        self.setMinimumWidth(58)
        self.setMaximumWidth(304)
        self.setFixedWidth(286)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setDirection(QBoxLayout.Direction.RightToLeft)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(7)
        self.brand_logo_btn = QPushButton()
        self.brand_logo_btn.setFixedSize(34, 34)
        self.brand_logo_btn.setToolTip("SmartiAI")
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.isfile(logo_path):
            self.brand_logo_btn.setIcon(QIcon(logo_path))
            self.brand_logo_btn.setIconSize(QSize(30, 30))
        else:
            self.brand_logo_btn.setText("S")
        self.brand_logo_btn.clicked.connect(lambda: self.set_collapsed(not self._collapsed, manual=True))
        self.brand_logo_btn.installEventFilter(self)
        header.addWidget(self.brand_logo_btn)
        self.brand = QLabel("SmartiAI")
        self.brand.setStyleSheet(page_title_css(19))
        header.addWidget(self.brand)
        header.addStretch(1)
        self.collapse_btn = QPushButton()
        self.collapse_btn.setFixedSize(34, 34)
        self.collapse_btn.setToolTip("כיווץ תפריט הצד")
        self.collapse_btn.clicked.connect(lambda: self.set_collapsed(not self._collapsed, manual=True))
        header.addWidget(self.collapse_btn)
        self.header_host = QWidget()
        self.header_host.setFixedHeight(38)
        self.header_host.setLayout(header)
        layout.addWidget(self.header_host)
        self.new_chat_btn = self._nav_button("שיחה חדשה", ("new_chat_icon", "plus_icon"), self.new_chat_requested)
        layout.addWidget(self.new_chat_btn)
        self.history_widget.setParent(self)
        if hasattr(self.history_widget, "back_btn"):
            self.history_widget.back_btn.hide()
        if hasattr(self.history_widget, "new_chat_btn"):
            self.history_widget.new_chat_btn.hide()
        if hasattr(self.history_widget, "title_label"):
            self.history_widget.title_label.hide()
        history_layout = self.history_widget.layout()
        if history_layout is not None:
            history_layout.setContentsMargins(0, 4, 0, 4)
            history_layout.setSpacing(8)
        layout.addWidget(self.history_widget, 1)
        self.collapsed_spacer = QWidget()
        self.collapsed_spacer.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.collapsed_spacer.setStyleSheet("background: transparent; border: none;")
        self.collapsed_spacer.hide()
        layout.addWidget(self.collapsed_spacer, 1)
        self.profile_btn = SidebarNavButton("פרופיל משתמש")
        self.profile_btn.setProperty("fullText", "פרופיל משתמש")
        self.profile_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.profile_btn.setFixedHeight(46)
        self.profile_btn.clicked.connect(self._show_profile_menu)
        set_themed_button_icon(self.profile_btn, ("profile_icon", "account_icon"), "●", 19, clear_text=False)
        if themed_icon("profile_icon", "account_icon").isNull():
            self.profile_btn.setText("פרופיל משתמש")
        layout.addWidget(self.profile_btn)

    def _show_profile_menu(self):
        menu = QMenu(self)
        menu.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        prepare_popup_menu(menu)
        self._menu_action(menu, "נתוני שימוש", ("usage_icon",), self.usage_requested)
        self._menu_action(menu, "הגדרות וניהול", ("settings_icon",), self.settings_requested)
        self._menu_action(menu, "Smarti Diagnostic", ("doctor_icon",), self.diagnostic_requested)
        menu.addSeparator()
        self._menu_action(menu, "אודות", ("about_icon", "info_icon"), self.about_requested)
        menu.adjustSize()
        size = menu.sizeHint()
        button_top_right = self.profile_btn.mapToGlobal(self.profile_btn.rect().topRight())
        pos = QPoint(button_top_right.x() - size.width(), button_top_right.y() - size.height())
        screen = QApplication.screenAt(button_top_right) or QApplication.primaryScreen()
        if screen:
            bounds = screen.availableGeometry()
            pos.setX(max(bounds.left() + 6, min(pos.x(), bounds.right() - size.width() - 6)))
            pos.setY(max(bounds.top() + 6, pos.y()))
        menu.popup(pos)

    @staticmethod
    def _menu_action(menu, text, icon_names, signal):
        action = menu.addAction(text)
        icon = themed_icon(*icon_names)
        if not icon.isNull():
            action.setIcon(icon)
        action.triggered.connect(signal.emit)

    def set_collapsed(self, collapsed, manual=False):
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.brand.setVisible(not collapsed)
        self.history_widget.setVisible(not collapsed)
        self.collapsed_spacer.setVisible(collapsed)
        self.collapse_btn.setVisible(not collapsed)
        self.collapse_btn.setToolTip("פתיחת תפריט הצד" if collapsed else "כיווץ תפריט הצד")
        for button, icon_names in self._nav_buttons:
            button.setProperty("sidebarCollapsed", collapsed)
            full = str(button.property("fullText") or "")
            button.setText("" if collapsed else full)
            button.setToolTip(full if collapsed else "")
            set_themed_button_icon(button, icon_names, full[:1], 19, clear_text=collapsed)
            if not collapsed and themed_icon(*icon_names).isNull():
                button.setText(full)
        self.profile_btn.setText("" if collapsed else str(self.profile_btn.property("fullText") or ""))
        self.profile_btn.setProperty("sidebarCollapsed", collapsed)
        self.profile_btn.setToolTip("פרופיל משתמש" if collapsed else "")
        set_themed_button_icon(self.profile_btn, ("profile_icon", "account_icon"), "●", 19, clear_text=collapsed)
        if not collapsed and themed_icon("profile_icon", "account_icon").isNull():
            self.profile_btn.setText(str(self.profile_btn.property("fullText") or ""))
        self.apply_theme()
        self._refresh_brand_button(False)
        start_width = max(58, int(self.width() or (286 if not collapsed else 58)))
        target_width = 58 if collapsed else 286
        if self._width_animation is not None:
            self._width_animation.stop()
        if manual and self.isVisible() and start_width != target_width:
            animation = QVariantAnimation(self)
            self._width_animation = animation
            animation.setDuration(300)
            animation.setStartValue(start_width)
            animation.setEndValue(target_width)
            animation.setEasingCurve(QEasingCurve.Type.OutQuart)
            animation.valueChanged.connect(lambda value: self._set_animated_width(int(value)))
            animation.finished.connect(lambda: self._finish_width_animation(target_width))
            animation.start()
        else:
            self._finish_width_animation(target_width)
        self.collapsed_changed.emit(collapsed)

    def _set_animated_width(self, width):
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)

    def _finish_width_animation(self, width):
        self._set_animated_width(int(width))
        self._width_animation = None

    def is_collapsed(self):
        return self._collapsed

    def _refresh_brand_button(self, show_expand=False):
        if self._collapsed and show_expand:
            set_themed_button_icon(
                self.brand_logo_btn,
                ("sidebar_expand_icon", "workspace_sidebar_expand_icon"),
                "←",
                19,
                clear_text=True,
            )
            return
        self.brand_logo_btn.setProperty("smartiIconNames", None)
        self.brand_logo_btn.setIcon(QIcon())
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.isfile(logo_path):
            self.brand_logo_btn.setText("")
            self.brand_logo_btn.setIcon(QIcon(logo_path))
            self.brand_logo_btn.setIconSize(QSize(30, 30))
        else:
            self.brand_logo_btn.setText("S")

    def eventFilter(self, watched, event):
        if watched is self.brand_logo_btn and self._collapsed:
            if event.type() == QEvent.Type.Enter:
                self._refresh_brand_button(True)
            elif event.type() in {QEvent.Type.Leave, QEvent.Type.MouseButtonRelease}:
                self._refresh_brand_button(False)
        return super().eventFilter(watched, event)

    def apply_theme(self):
        self.setStyleSheet(
            f"QFrame#WorkspaceSidebar {{ background: {BG_ELEVATED_COLOR}; border: none; }}"
        )
        self.brand.setStyleSheet(page_title_css(19))
        self.brand_logo_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_COLOR}; border: none; border-radius: 9px; font-weight: 800; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; }}"
        )
        nav_css = (
            f"QPushButton {{ text-align: right; background: transparent; color: {TEXT_COLOR}; border: 1px solid transparent; "
            "border-radius: 11px; padding: 8px 10px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; border-color: {SOFT_LINE_COLOR}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_TINT_STRONG}; }}"
        )
        for button, icon_names in self._nav_buttons:
            button.setStyleSheet(nav_css if not self._collapsed else nav_css + "QPushButton { text-align: center; padding: 0px; }")
            full = str(button.property("fullText") or "")
            set_themed_button_icon(button, icon_names, full[:1], 19, clear_text=self._collapsed)
            if not self._collapsed and themed_icon(*icon_names).isNull():
                button.setText(full)
        profile_css = nav_css + (
            f"QPushButton {{ border: 1px solid {SOFT_LINE_COLOR}; border-radius: 12px; "
            f"background: {GLASS_COLOR}; }}"
            f"QPushButton:hover {{ border-color: {LINE_COLOR}; background: {HOVER_TINT}; }}"
        )
        if self._collapsed:
            profile_css += "QPushButton { text-align: center; padding: 0px; }"
        self.profile_btn.setStyleSheet(profile_css)
        self.collapse_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {MUTED_TEXT_COLOR}; border: none; border-radius: 17px; font-size: 20px; }}"
            f"QPushButton:hover {{ background: {HOVER_TINT}; color: {TEXT_COLOR}; }}"
        )
        set_themed_button_icon(
            self.collapse_btn,
            ("sidebar_collapse_icon", "workspace_sidebar_collapse_icon"),
            "→",
            18,
            clear_text=True,
        )
        if hasattr(self.history_widget, "apply_theme"):
            self.history_widget.apply_theme()


class WorkspacePreferencesPage(QWidget):
    """Human-readable controls for the Workspace shell and browser profile."""

    def __init__(self, core, main_window, parent=None):
        super().__init__(parent)
        self.core = core
        self.main_window = main_window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(14)
        title = QLabel("סביבת עבודה ודפדפן")
        self.title = title
        layout.addWidget(title)
        intro = QLabel(
            "כאן מגדירים את אופן פתיחת Smarti Workspace ואת פרופיל הגלישה הנפרד של סמארטי."
        )
        intro.setWordWrap(True)
        self.intro = intro
        layout.addWidget(intro)
        self.card = QFrame()
        self.card.setObjectName("WorkspacePreferencesCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)
        preferences = self.core.settings.setdefault("ui_preferences", {})
        self.maximized = QCheckBox("פתיחת החלון הראשי בגודל מרבי")
        self.maximized.setChecked(bool(preferences.get("workspace_start_maximized", True)))
        self.sidebar_expanded = QCheckBox("פתיחת תפריט השיחות במצב מורחב")
        self.sidebar_expanded.setChecked(not bool(preferences.get("workspace_sidebar_collapsed", False)))
        self.workbench_collapsed = QCheckBox("פתיחת אזור העבודה במצב מכווץ")
        self.workbench_collapsed.setChecked(True)
        self.workbench_collapsed.setEnabled(False)
        for check in (self.maximized, self.sidebar_expanded):
            check.stateChanged.connect(self._save)
        card_layout.addWidget(self.maximized)
        card_layout.addWidget(self.sidebar_expanded)
        card_layout.addWidget(self.workbench_collapsed)
        layout.addWidget(self.card)

        self.browser_card = QFrame()
        self.browser_card.setObjectName("BrowserPreferencesCard")
        browser_layout = QVBoxLayout(self.browser_card)
        browser_layout.setContentsMargins(18, 16, 18, 16)
        browser_layout.setSpacing(10)
        browser_title = QLabel("Smarti Browser")
        self.browser_title = browser_title
        browser_layout.addWidget(browser_title)
        browser_text = QLabel(
            "הדפדפן המובנה משתמש בפרופיל נפרד ומתמשך. אפשר לגלוש כאורח או לייבא פעם אחת "
            "עוגיות, היסטוריה וסימניות מפרופיל קיים. סיסמאות אינן מועתקות."
        )
        browser_text.setWordWrap(True)
        self.browser_text = browser_text
        browser_layout.addWidget(browser_text)
        self.import_status = QLabel()
        self.import_status.setWordWrap(True)
        browser_layout.addWidget(self.import_status)
        actions = QHBoxLayout()
        self.open_browser_btn = QPushButton("פתיחת הדפדפן")
        self.open_browser_btn.clicked.connect(lambda: self.main_window.open_workbench("browser"))
        actions.addWidget(self.open_browser_btn)
        self.import_btn = QPushButton("ייבוא נתוני גלישה")
        self.import_btn.clicked.connect(self._open_import)
        actions.addWidget(self.import_btn)
        self.data_folder_btn = QPushButton("תיקיית נתוני הדפדפן")
        self.data_folder_btn.clicked.connect(self._open_data_folder)
        actions.addWidget(self.data_folder_btn)
        actions.addStretch()
        browser_layout.addLayout(actions)
        layout.addWidget(self.browser_card)
        layout.addStretch()
        self.refresh()
        self.apply_theme()

    def _save(self, *_args):
        preferences = self.core.settings.setdefault("ui_preferences", {})
        preferences["workspace_start_maximized"] = self.maximized.isChecked()
        preferences["workspace_sidebar_collapsed"] = not self.sidebar_expanded.isChecked()
        preferences["workspace_workbench_collapsed"] = True
        preferences.pop("workspace_default_panel", None)
        self.core._save_settings()
        self.main_window.workspace_sidebar.set_collapsed(not self.sidebar_expanded.isChecked(), manual=True)

    def _open_import(self):
        self.main_window.open_workbench("browser")
        self.main_window.workspace_browser_panel.show_import_dialog()
        QTimer.singleShot(500, self.refresh)

    @staticmethod
    def _browser_data_root():
        return os.path.join(os.environ.get("LOCALAPPDATA", USER_DATA_DIR), SMARTI_BROWSER_PROFILE_NAME)

    def _open_data_folder(self):
        root = self._browser_data_root()
        os.makedirs(root, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(root))

    def refresh(self):
        imported = self.core.settings.get("browser_profile_import") or {}
        if imported.get("completed_at"):
            source = imported.get("source") or {}
            self.import_status.setText(
                f"ייבוא אחרון: {source.get('browser_name') or 'דפדפן מקומי'} — "
                f"{source.get('profile_name') or 'פרופיל'}"
            )
        else:
            self.import_status.setText("טרם יובאו נתוני גלישה. אפשר להמשיך גם ללא ייבוא.")

    def apply_theme(self):
        self.setStyleSheet(f"background: {BG_COLOR}; color: {TEXT_COLOR};")
        self.title.setStyleSheet(page_title_css(22))
        self.intro.setStyleSheet(muted_label_css(13))
        card_css = (
            f"QFrame {{ background: {GLASS_STRONG_COLOR}; border: 1px solid {SOFT_LINE_COLOR}; border-radius: 16px; }}"
            "QFrame QLabel, QFrame QCheckBox { background: transparent; border: none; }"
        )
        self.card.setStyleSheet(card_css)
        self.browser_card.setStyleSheet(card_css)
        self.browser_title.setStyleSheet(page_title_css(17))
        self.browser_text.setStyleSheet(muted_label_css(13))
        self.import_status.setStyleSheet(f"color: {ACCENT_COLOR}; font-size: 12px; font-weight: 700;")
        for check in (self.maximized, self.sidebar_expanded, self.workbench_collapsed):
            check.setStyleSheet(CHECKBOX_CSS)
        self.open_browser_btn.setStyleSheet(PRIMARY_BUTTON_CSS)
        self.import_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        self.data_folder_btn.setStyleSheet(SECONDARY_BUTTON_CSS)


class ManagementCenterPage(QWidget):
    """Large, lazy settings-and-management hub for Smarti's existing pages."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._entries = {}
        self._buttons = {}
        self._page_containers = {}
        self._current_key = ""
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(18, 12, 18, 10)
        self.back_btn = QPushButton()
        self.back_btn.setFixedSize(42, 42)
        self.back_btn.setToolTip("חזרה לצ'אט")
        set_themed_button_icon(self.back_btn, ("back_icon",), "→", 21, clear_text=True)
        self.back_btn.clicked.connect(lambda: self.main_window.stacked_widget.setCurrentWidget(self.main_window.chat_page))
        top.addWidget(self.back_btn)
        self.title = QLabel("הגדרות וניהול")
        self.title.setStyleSheet(page_title_css(21))
        top.addWidget(self.title)
        top.addStretch()
        outer.addLayout(top)
        self.body = QSplitter(Qt.Orientation.Horizontal)
        self.body.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.content = QStackedWidget()
        self.body.addWidget(self.content)
        self.nav = QFrame()
        self.nav.setObjectName("ManagementNavigation")
        self.nav.setFixedWidth(250)
        self.nav_layout = QVBoxLayout(self.nav)
        self.nav_layout.setContentsMargins(12, 14, 12, 14)
        self.nav_layout.setSpacing(6)
        self.body.addWidget(self.nav)
        self.body.setStretchFactor(0, 1)
        self.body.setStretchFactor(1, 0)
        outer.addWidget(self.body, 1)

    def add_group(self, label):
        group = QLabel(str(label or ""))
        group.setProperty("managementGroup", True)
        group.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        group.setStyleSheet(
            f"color: {SUBTLE_TEXT_COLOR}; background: transparent; border: none; "
            "font-size: 11px; font-weight: 700; padding: 10px 8px 3px 8px;"
        )
        self.nav_layout.addWidget(group)
        return group

    def register_section(self, key, label, icon_names, factory, activate=None):
        self._entries[key] = {"label": label, "icons": tuple(icon_names), "factory": factory, "activate": activate, "page": None}
        button = SidebarNavButton(label)
        button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        button.setProperty("managementKey", key)
        button.setMinimumHeight(42)
        button.clicked.connect(lambda checked=False, section=key: self.select_section(section))
        set_themed_button_icon(button, tuple(icon_names), label[:1], 19, clear_text=False)
        if themed_icon(*tuple(icon_names)).isNull():
            button.setText(label)
        self._buttons[key] = button
        self.nav_layout.addWidget(button)

    def finish_sections(self):
        self.nav_layout.addStretch()

    def select_section(self, key):
        entry = self._entries.get(key)
        if not entry:
            return None
        page = entry.get("page")
        if page is None:
            page = entry["factory"]()
            entry["page"] = page
            container = self._page_containers.get(id(page))
            if container is None:
                page.setMaximumWidth(980)
                container = QWidget()
                centered = QHBoxLayout(container)
                centered.setDirection(QBoxLayout.Direction.LeftToRight)
                centered.setContentsMargins(22, 10, 22, 22)
                centered.addStretch(1)
                centered.addWidget(page, 8)
                centered.addStretch(1)
                self._page_containers[id(page)] = container
                self.content.addWidget(container)
            entry["container"] = container
        self.content.setCurrentWidget(entry.get("container") or page)
        self._current_key = key
        for item_key, button in self._buttons.items():
            button.setProperty("active", item_key == key)
            button.style().unpolish(button)
            button.style().polish(button)
        activate = entry.get("activate")
        if callable(activate):
            activate(page)
        self.apply_theme()
        return page

    def page_for(self, key):
        entry = self._entries.get(key) or {}
        return entry.get("page")

    def apply_theme(self):
        self.setStyleSheet(f"background: {BG_COLOR}; color: {TEXT_COLOR};")
        self.title.setStyleSheet(page_title_css(21))
        self.back_btn.setStyleSheet(SECONDARY_BUTTON_CSS)
        set_themed_button_icon(self.back_btn, ("back_icon",), "→", 21, clear_text=True)
        self.nav.setStyleSheet(
            f"QFrame#ManagementNavigation {{ background: {BG_ELEVATED_COLOR}; border: none; }}"
        )
        for key, button in self._buttons.items():
            active = key == self._current_key
            button.setStyleSheet(
                f"QPushButton {{ text-align: right; background: {'%s' % ACCENT_TINT_STRONG if active else 'transparent'}; "
                f"color: {TEXT_COLOR}; border: 1px solid {'%s' % LINE_COLOR if active else 'transparent'}; "
                "border-radius: 11px; padding: 8px 10px; font-size: 13px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: {HOVER_TINT}; border-color: {SOFT_LINE_COLOR}; }}"
            )
            entry = self._entries.get(key) or {}
            set_themed_button_icon(button, entry.get("icons") or (), str(entry.get("label") or "")[:1], 19, clear_text=False)
            if themed_icon(*(entry.get("icons") or ())).isNull():
                button.setText(str(entry.get("label") or ""))
        for entry in self._entries.values():
            page = entry.get("page")
            if page is not None and hasattr(page, "apply_theme"):
                try:
                    page.apply_theme()
                except TypeError:
                    pass
