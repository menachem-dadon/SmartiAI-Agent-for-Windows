"""Optional, local-only Web Canvas support for Smarti chat sessions.

The persisted canvas format deliberately contains the complete rendered source and
the latest measured button layout.  The WebEngine renderer is optional so that a
missing Chromium runtime never prevents the ordinary chat UI from starting.
"""
from __future__ import annotations

import html as html_lib
import http.server
import importlib.util
import json
import os
import re
import threading
import uuid

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStackedLayout, QVBoxLayout, QWidget

from . import ui_styles
from .common import SMARTI_BROWSER_DEBUG_PORT
from .native_browser import NativeChromiumHost
from .ui_styles import set_themed_button_icon


_CANVAS_SCHEME_REGISTERED = False


def web_canvas_available():
    """Return whether the optional PyQt WebEngine wheel is installed."""
    return importlib.util.find_spec("PyQt6.QtWebEngineWidgets") is not None


def prepare_webengine_runtime():
    """Load WebEngine before QApplication so Chromium can initialize correctly."""
    if not web_canvas_available():
        return False
    try:
        # Smarti's embedded browser is the primary automation surface.  Qt
        # exposes its Chromium target only on loopback so the existing
        # Playwright/CDP controller can use the same visible, persistent page.
        os.environ.setdefault(
            "QTWEBENGINE_REMOTE_DEBUGGING",
            f"127.0.0.1:{SMARTI_BROWSER_DEBUG_PORT}",
        )
        chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "--remote-debugging-address=" not in chromium_flags:
            chromium_flags = (chromium_flags + " --remote-debugging-address=127.0.0.1").strip()
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = chromium_flags
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        # Qt requires this import (or the shared OpenGL attribute) before the
        # first Q(Core)Application instance. Do both for PyQt runtime variants.
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return True
    except Exception:
        return False


def register_canvas_scheme():
    """Register the local-only canvas origin before QApplication is created.

    The document is still delivered directly with ``setHtml``.  Giving it a
    dedicated origin prevents it from inheriting a user browser/file origin and
    leaves room for a strictly scoped scheme handler in a future artifact store.
    """
    global _CANVAS_SCHEME_REGISTERED
    if _CANVAS_SCHEME_REGISTERED:
        return True
    if os.name == "nt":
        return False
    if not web_canvas_available():
        return False
    try:
        from PyQt6.QtWebEngineCore import QWebEngineUrlScheme

        scheme = QWebEngineUrlScheme(b"smarti-canvas")
        scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
        scheme.setFlags(
            QWebEngineUrlScheme.Flag.SecureScheme
            | QWebEngineUrlScheme.Flag.LocalScheme
        )
        QWebEngineUrlScheme.registerScheme(scheme)
        _CANVAS_SCHEME_REGISTERED = True
        return True
    except Exception:
        # Duplicate registration and unavailable WebEngine must both degrade to
        # the normal chat path rather than turning startup into a fatal error.
        return False


from .canvas_model import (
    canvas_artifacts_from_messages,
    canvas_context_for_model,
    materialize_canvas_html,
    new_canvas_artifact,
    normalize_canvas_artifact,
)


def _secured_document(html, allow_remote_images=False):
    """Add a restrictive CSP and a small, schema-only bridge around model HTML."""
    image_sources = "data: blob: https:" if allow_remote_images else "data: blob:"
    csp = (
        f"default-src 'none'; img-src {image_sources}; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline' qrc:; connect-src 'none'; media-src 'none'; "
        "font-src data:; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"
    )
    bridge = """
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
(() => {
  let bridge = null;
  let userGestureUntil = 0;
  const compact = value => JSON.stringify(value || {});
  window.SmartiCanvas = Object.freeze({
    send: (action, data) => {
      if (bridge && Date.now() <= userGestureUntil) bridge.submit(compact({action: String(action || 'submit'), data: data || {}}));
    }
  });
  const positions = () => {
    if (!bridge) return;
    const root = document.documentElement.getBoundingClientRect();
    const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'))
      .slice(0, 80).map((node, index) => {
        const rect = node.getBoundingClientRect();
        return {id: node.id || ('dom-button-' + (index + 1)), label: (node.innerText || node.getAttribute('aria-label') || '').trim().slice(0, 160), x: Math.round(rect.left - root.left), y: Math.round(rect.top - root.top), width: Math.round(rect.width), height: Math.round(rect.height)};
      });
    bridge.reportLayout(compact({buttons}));
  };
  new QWebChannel(qt.webChannelTransport, channel => {
    bridge = channel.objects.smartiCanvasBridge;
    window.dispatchEvent(new Event('smartiCanvasReady'));
    positions();
    new ResizeObserver(positions).observe(document.documentElement);
    new MutationObserver(positions).observe(document.documentElement, {subtree: true, childList: true, attributes: true});
  });
  window.open = () => null;
  for (const eventName of ['click', 'submit', 'change']) {
    document.addEventListener(eventName, event => {
      if (event.isTrusted) userGestureUntil = Date.now() + 1000;
    }, true);
  }
  document.addEventListener('click', event => {
    const link = event.target && event.target.closest && event.target.closest('a[href]');
    if (link) event.preventDefault();
  }, true);
})();
</script>
""".replace("__CSP__", csp)
    if re.search(r"<head[^>]*>", html, flags=re.IGNORECASE):
        return re.sub(r"<head[^>]*>", lambda match: match.group(0) + bridge, html, count=1, flags=re.IGNORECASE)
    return bridge + html


def _secured_native_document(html, token, allow_remote_images=False):
    """Render model HTML in a sandboxed iframe behind a loopback bridge."""
    image_sources = "data: blob: https:" if allow_remote_images else "data: blob:"
    inner_csp = (
        f"default-src 'none'; img-src {image_sources}; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; connect-src 'none'; media-src 'none'; "
        "font-src data:; object-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'"
    )
    inner_bridge = """
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<script>
(() => {
  let userGestureUntil = 0;
  const compact = value => JSON.stringify(value || {});
  const send = (kind, payload) => parent.postMessage({channel: 'smarti-canvas-v1', kind, payload}, '*');
  window.SmartiCanvas = Object.freeze({
    send: (action, data) => {
      if (Date.now() <= userGestureUntil) send('action', compact({action: String(action || 'submit'), data: data || {}}));
    }
  });
  const positions = () => {
    const root = document.documentElement.getBoundingClientRect();
    const buttons = Array.from(document.querySelectorAll('button, [role="button"], a'))
      .slice(0, 80).map((node, index) => {
        const rect = node.getBoundingClientRect();
        return {id: node.id || ('dom-button-' + (index + 1)), label: (node.innerText || node.getAttribute('aria-label') || '').trim().slice(0, 160), x: Math.round(rect.left - root.left), y: Math.round(rect.top - root.top), width: Math.round(rect.width), height: Math.round(rect.height)};
      });
    send('layout', compact({buttons}));
  };
  const ready = () => {
    window.dispatchEvent(new Event('smartiCanvasReady'));
    positions();
    if (window.ResizeObserver) new ResizeObserver(positions).observe(document.documentElement);
    new MutationObserver(positions).observe(document.documentElement, {subtree: true, childList: true, attributes: true});
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, {once: true});
  else ready();
  window.open = () => null;
  for (const eventName of ['click', 'submit', 'change']) {
    document.addEventListener(eventName, event => {
      if (event.isTrusted) userGestureUntil = Date.now() + 1000;
    }, true);
  }
  document.addEventListener('click', event => {
    const link = event.target && event.target.closest && event.target.closest('a[href]');
    if (link) event.preventDefault();
  }, true);
})();
</script>
""".replace("__CSP__", inner_csp)
    if re.search(r"<head[^>]*>", html, flags=re.IGNORECASE):
        inner = re.sub(
            r"<head[^>]*>", lambda match: match.group(0) + inner_bridge,
            html, count=1, flags=re.IGNORECASE,
        )
    else:
        inner = inner_bridge + html
    encoded_inner = html_lib.escape(inner, quote=True)
    outer_csp = (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; frame-src 'self' data: blob:; object-src 'none'; base-uri 'none'"
    )
    return """<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="__OUTER_CSP__">
<meta name="referrer" content="no-referrer">
<style>html,body{width:100%;height:100%;margin:0;overflow:hidden;background:transparent}iframe{width:100%;height:100%;border:0;display:block;background:white}</style>
</head><body><iframe id="canvas" sandbox="allow-scripts" referrerpolicy="no-referrer" srcdoc="__INNER__"></iframe>
<script>(() => {
  const frame = document.getElementById('canvas');
  window.addEventListener('message', event => {
    const data = event.data || {};
    if (event.source !== frame.contentWindow || data.channel !== 'smarti-canvas-v1') return;
    if (!['action', 'layout'].includes(data.kind) || typeof data.payload !== 'string') return;
    fetch('/__TOKEN__/' + data.kind, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: data.payload,
      credentials: 'omit', cache: 'no-store'
    }).catch(() => null);
  });
})();</script></body></html>""".replace("__OUTER_CSP__", outer_csp).replace("__INNER__", encoded_inner).replace("__TOKEN__", token)


class _CanvasHttpBridge(QObject):
    action_received = pyqtSignal(dict)
    layout_received = pyqtSignal(dict)


class _CanvasHttpHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        owner = self.server.canvas_owner
        if self.path != f"/{owner._http_token}/canvas":
            self.send_error(404)
            return
        body = owner._native_document.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        owner = self.server.canvas_owner
        expected = f"/{owner._http_token}/"
        if not self.path.startswith(expected) or self.path[len(expected):] not in {"action", "layout"}:
            self.send_error(404)
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 128_000)
            payload = json.loads(self.rfile.read(length).decode("utf-8", errors="replace") or "{}")
        except Exception:
            self.send_error(400)
            return
        if isinstance(payload, dict):
            if self.path.endswith("/action"):
                owner._http_bridge.action_received.emit(payload)
            else:
                owner._http_bridge.layout_received.emit(payload)
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, _format, *_args):
        return


class _CanvasBridge(QObject):
    action_received = pyqtSignal(dict)
    layout_received = pyqtSignal(dict)

    @pyqtSlot(str)
    def submit(self, raw):
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self.action_received.emit(payload)

    @pyqtSlot(str)
    def reportLayout(self, raw):
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self.layout_received.emit(payload)


class VisualCanvasPanel(QFrame):
    """A lazy local canvas with Qt WebEngine and native-Chromium renderers."""
    canvas_action_requested = pyqtSignal(dict)
    canvas_layout_captured = pyqtSignal(dict)
    close_requested = pyqtSignal()

    def __init__(self, core=None, parent=None):
        super().__init__(parent)
        self.core = core
        self._canvas_id = ""
        self._web_view = None
        self._renderer = ""
        self._profile = None
        self._bridge = None
        self._allow_remote_images = False
        self._web_settings = None
        self._remote_urls_attribute = None
        self._native_document = ""
        self._native_host = None
        self._http_server = None
        self._http_thread = None
        self._http_token = uuid.uuid4().hex
        self._http_bridge = _CanvasHttpBridge(self)
        self._http_bridge.action_received.connect(self.canvas_action_requested)
        self._http_bridge.layout_received.connect(self.canvas_layout_captured)
        self._unavailable_label = QLabel()
        self._unavailable_label.setWordWrap(True)
        self._unavailable_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel("קנבס")
        self.close_button = QPushButton()
        self.close_button.setObjectName("CanvasCloseButton")
        self.close_button.setFixedSize(38, 38)
        self.close_button.setToolTip("סגירת הקנבס")
        self.close_button.setAccessibleName("סגירת הקנבס")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.close_requested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignLeft)
        header.addStretch(1)
        header.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)
        self.content = QWidget()
        self.content_stack = QStackedLayout(self.content)
        self.content_stack.addWidget(self._unavailable_label)
        layout.addWidget(self.content, 1)
        self.apply_theme()

    def apply_theme(self, colors=None):
        colors = colors or {
            "text": ui_styles.TEXT_COLOR,
            "muted": ui_styles.MUTED_TEXT_COLOR,
            "accent": ui_styles.ACCENT_COLOR,
            "line": ui_styles.SOFT_LINE_COLOR,
            "glass": ui_styles.GLASS_STRONG_COLOR,
        }
        text = colors.get("text", ui_styles.TEXT_COLOR)
        muted = colors.get("muted", ui_styles.MUTED_TEXT_COLOR)
        accent = colors.get("accent", ui_styles.ACCENT_COLOR)
        line = colors.get("line", ui_styles.SOFT_LINE_COLOR)
        glass = colors.get("glass", ui_styles.GLASS_STRONG_COLOR)
        set_themed_button_icon(
            self.close_button,
            ("canvas_close_icon", "close"),
            "×",
            20,
            clear_text=True,
        )
        self.setStyleSheet(
            f"QFrame {{ background: {glass}; border: 1px solid {line}; border-radius: 20px; }}"
            f"QLabel {{ color: {text}; background: transparent; border: none; font-size: 14px; }}"
            f"QPushButton#CanvasCloseButton {{ color: {text}; background: transparent; border: 1px solid {line}; "
            "border-radius: 19px; padding: 0px; }"
            f"QPushButton#CanvasCloseButton:hover {{ border-color: {accent}; background: rgba(53,217,255,0.12); }}"
        )
        self.title_label.setStyleSheet(f"color: {text}; font-size: 16px; font-weight: 800; background: transparent; border: none;")
        self._unavailable_label.setStyleSheet(f"color: {muted}; background: transparent; border: none; padding: 24px;")

    def _show_unavailable(self, message):
        self._unavailable_label.setText(message)
        self.content_stack.setCurrentWidget(self._unavailable_label)

    def _ensure_web_view(self):
        if self._web_view is not None:
            return True
        if os.name == "nt":
            return self._ensure_native_view()
        if not web_canvas_available():
            return self._ensure_native_view()
        # Some incomplete Windows WebEngine installations terminate the whole
        # process while creating a Chromium profile.  Probe that step in a
        # disposable child process before attempting it in the desktop.
        from .webengine_probe import cached_webengine_runtime_health, probe_webengine_runtime
        health = cached_webengine_runtime_health()
        if health is None:
            health = probe_webengine_runtime()
        if not health:
            return self._ensure_native_view()
        try:
            from PyQt6.QtWebChannel import QWebChannel
            from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            class RequestBlocker(QWebEngineUrlRequestInterceptor):
                def interceptRequest(self, info):
                    scheme = info.requestUrl().scheme().lower()
                    is_remote_image = (
                        self.panel._allow_remote_images
                        and scheme == "https"
                        and info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage
                    )
                    if scheme not in {"data", "about", "qrc", "smarti-canvas"} and not is_remote_image:
                        info.block(True)

                def __init__(self, panel, parent=None):
                    super().__init__(parent)
                    self.panel = panel

            class CanvasPage(QWebEnginePage):
                def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
                    return url.scheme().lower() in {"data", "about", "qrc", "smarti-canvas"}

            self._profile = QWebEngineProfile(self)  # Parent-only profiles are off-the-record.
            self._profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            self._blocker = RequestBlocker(self, self._profile)
            self._profile.setUrlRequestInterceptor(self._blocker)
            self._profile.downloadRequested.connect(lambda download: download.cancel())
            page = CanvasPage(self._profile, self)
            page.featurePermissionRequested.connect(
                lambda origin, feature: page.setFeaturePermission(
                    origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
                )
            )
            settings = page.settings()
            self._web_settings = settings
            self._remote_urls_attribute = getattr(
                QWebEngineSettings.WebAttribute, "LocalContentCanAccessRemoteUrls", None
            )
            for name, enabled in (
                ("JavascriptEnabled", True),
                ("JavascriptCanOpenWindows", False),
                ("LocalContentCanAccessRemoteUrls", False),
                ("LocalContentCanAccessFileUrls", False),
                ("PluginsEnabled", False),
                ("FullScreenSupportEnabled", False),
                ("ScreenCaptureEnabled", False),
            ):
                attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
                if attribute is not None:
                    settings.setAttribute(attribute, enabled)
            self._bridge = _CanvasBridge(self)
            self._bridge.action_received.connect(self.canvas_action_requested)
            self._bridge.layout_received.connect(self.canvas_layout_captured)
            channel = QWebChannel(page)
            channel.registerObject("smartiCanvasBridge", self._bridge)
            page.setWebChannel(channel)
            self._channel = channel
            self._web_view = QWebEngineView(self.content)
            self._renderer = "webengine"
            self._web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._web_view.setPage(page)
            self.content_stack.addWidget(self._web_view)
            return True
        except Exception as exc:
            return self._ensure_native_view(str(exc))

    def _ensure_native_view(self, previous_error=""):
        if self._native_host is not None:
            return True
        try:
            if self._http_server is None:
                self._http_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CanvasHttpHandler)
                self._http_server.daemon_threads = True
                self._http_server.canvas_owner = self
                self._http_thread = threading.Thread(
                    target=self._http_server.serve_forever,
                    name="SmartiCanvasBridge",
                    daemon=True,
                )
                self._http_thread.start()
            self._native_host = NativeChromiumHost(self.core, profile_mode="guest", parent=self.content)
            self._native_host.ready.connect(self._on_native_ready)
            self._web_view = self._native_host
            self._renderer = "native"
            self.content_stack.addWidget(self._native_host)
            return True
        except Exception as exc:
            detail = str(exc or previous_error).strip()
            suffix = f"\n{detail}" if detail else ""
            self._show_unavailable(f"לא ניתן היה לאתחל את הקנבס המקומי.{suffix}")
            return False

    def _on_native_ready(self, ok, error):
        if ok:
            self.content_stack.setCurrentWidget(self._native_host)
            return
        self._show_unavailable(error or "לא ניתן היה לעגן את הקנבס בתוך סמארטי.")

    def show_canvas(self, artifact, allow_remote_images=False):
        artifact = normalize_canvas_artifact(artifact)
        if not artifact:
            self._show_unavailable("נתוני הקנבס בהיסטוריית השיחה אינם תקינים.")
            return False
        self._canvas_id = artifact["id"]
        self.title_label.setText(artifact["title"])
        self._allow_remote_images = bool(allow_remote_images)
        if not self._ensure_web_view():
            return False
        if self._renderer == "native":
            self._native_document = _secured_native_document(
                materialize_canvas_html(artifact, allow_remote_images=self._allow_remote_images),
                self._http_token,
                allow_remote_images=self._allow_remote_images,
            )
            port = int(self._http_server.server_address[1])
            url = f"http://127.0.0.1:{port}/{self._http_token}/canvas"
            if self._native_host.is_ready():
                old_host = self._native_host
                old_host.stop()
                self.content_stack.removeWidget(old_host)
                old_host.deleteLater()
                self._native_host = NativeChromiumHost(self.core, profile_mode="guest", parent=self.content)
                self._native_host.ready.connect(self._on_native_ready)
                self._web_view = self._native_host
                self.content_stack.addWidget(self._native_host)
            self.content_stack.setCurrentWidget(self._native_host)
            return bool(self._native_host.start(url))
        if self._web_settings is not None and self._remote_urls_attribute is not None:
            self._web_settings.setAttribute(self._remote_urls_attribute, self._allow_remote_images)
        self.content_stack.setCurrentWidget(self._web_view)
        base_url = (
            QUrl(f"smarti-canvas://canvas/{artifact['id']}/")
            if _CANVAS_SCHEME_REGISTERED else QUrl("data:text/html,")
        )
        self._web_view.setHtml(
            _secured_document(
                materialize_canvas_html(artifact, allow_remote_images=self._allow_remote_images),
                allow_remote_images=self._allow_remote_images,
            ),
            base_url,
        )
        return True

    def canvas_id(self):
        return self._canvas_id

    def shutdown(self):
        if self._native_host is not None:
            self._native_host.stop()
        if self._http_server is not None:
            try:
                self._http_server.shutdown()
                self._http_server.server_close()
            except Exception:
                pass
            self._http_server = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
