"""Optional, local-only Web Canvas support for Smarti chat sessions.

The persisted canvas format deliberately contains the complete rendered source and
the latest measured button layout.  The WebEngine renderer is optional so that a
missing Chromium runtime never prevents the ordinary chat UI from starting.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, Qt, pyqtSignal, pyqtSlot, QUrl
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStackedLayout, QVBoxLayout, QWidget


CANVAS_SCHEMA_VERSION = 1
MAX_CANVAS_HTML_CHARS = 220_000
MAX_CANVAS_CSS_CHARS = 48_000
MAX_CANVAS_JAVASCRIPT_CHARS = 72_000
MAX_CANVAS_BUTTONS = 80
MAX_CANVAS_CONTEXT_CHARS = 350_000
# Images are kept in the conversation and fed back to the model with the rest
# of the canvas.  Keep them compact enough that a valid new artifact always
# fits in the model context rather than silently dropping the whole canvas.
MAX_CANVAS_IMAGE_DATA_URL_CHARS = 120_000
_CANVAS_SCHEME_REGISTERED = False


def web_canvas_available():
    """Return whether the optional PyQt WebEngine wheel is installed."""
    return importlib.util.find_spec("PyQt6.QtWebEngineWidgets") is not None


def prepare_webengine_runtime():
    """Load WebEngine before QApplication so Chromium can initialize correctly."""
    if not web_canvas_available():
        return False
    try:
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


def _clip_text(value, limit, field_name):
    value = str(value or "")
    if len(value) > limit:
        raise ValueError(f"{field_name} is too large (maximum {limit:,} characters).")
    return value


def _clean_button(item, index):
    if not isinstance(item, dict):
        return None
    result = {
        "id": re.sub(r"[^A-Za-z0-9_.:-]", "_", str(item.get("id") or f"button-{index + 1}"))[:80],
        "label": str(item.get("label") or item.get("text") or f"פעולה {index + 1}")[:160],
    }
    for name in ("x", "y", "width", "height"):
        if item.get(name) is None:
            continue
        try:
            result[name] = round(float(item[name]), 2)
        except (TypeError, ValueError):
            continue
    for name in ("action", "target"):
        if item.get(name) not in (None, ""):
            result[name] = str(item[name])[:2_000]
    return result


def _clean_image(item, index, allow_remote_images=False):
    if not isinstance(item, dict):
        return None
    image = {
        "id": re.sub(r"[^A-Za-z0-9_.:-]", "_", str(item.get("id") or f"image-{index + 1}"))[:80],
        "alt": str(item.get("alt") or "תמונה בקנבס")[:300],
        "caption": str(item.get("caption") or "")[:600],
    }
    data_url = str(item.get("data_url") or "")
    if not data_url and str(item.get("src") or "").lower().startswith("data:image/"):
        data_url = str(item.get("src") or "")
    if data_url:
        if not re.match(r"^data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+$", data_url, flags=re.IGNORECASE):
            return None
        if len(data_url) > MAX_CANVAS_IMAGE_DATA_URL_CHARS:
            return None
        image["data_url"] = data_url
        return image
    remote_url = str(item.get("url") or item.get("src") or "").strip()
    parsed = urlparse(remote_url)
    if (
        allow_remote_images
        and parsed.scheme.lower() == "https"
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        and len(remote_url) <= 2_048
    ):
        image["url"] = remote_url
        return image
    return None


def _complete_html(html, css, javascript):
    html = str(html or "")
    css = str(css or "")
    javascript = str(javascript or "")
    if re.search(r"<html[\s>]", html, flags=re.IGNORECASE):
        return html
    return (
        "<!doctype html><html lang=\"he\" dir=\"rtl\"><head><meta charset=\"utf-8\">"
        f"<style>{css}</style></head><body>{html}<script>{javascript}</script></body></html>"
    )


def new_canvas_artifact(payload, allow_remote_images=False):
    """Validate a tool payload and return a JSON-safe persisted canvas artifact."""
    if not isinstance(payload, dict):
        raise ValueError("Canvas payload must be an object.")
    html = _clip_text(payload.get("html", ""), MAX_CANVAS_HTML_CHARS, "html")
    css = _clip_text(payload.get("css", ""), MAX_CANVAS_CSS_CHARS, "css")
    javascript = _clip_text(payload.get("javascript", ""), MAX_CANVAS_JAVASCRIPT_CHARS, "javascript")
    if not html.strip():
        raise ValueError("Canvas html is required.")
    buttons = payload.get("buttons", [])
    if not isinstance(buttons, list):
        raise ValueError("buttons must be an array.")
    if len(buttons) > MAX_CANVAS_BUTTONS:
        raise ValueError(f"Too many canvas buttons (maximum {MAX_CANVAS_BUTTONS}).")
    images = payload.get("images", [])
    if not isinstance(images, list):
        raise ValueError("images must be an array.")
    cleaned_images = [
        image for index, item in enumerate(images)
        if (image := _clean_image(item, index, allow_remote_images=allow_remote_images))
    ]
    if len(cleaned_images) != len(images):
        image_source = "a valid base64 data:image URL"
        if allow_remote_images:
            image_source += " or an HTTPS URL"
        raise ValueError(f"Each canvas image must be {image_source} within the size limit.")
    # Preserve smarti-image references in history/context.  The renderer
    # materializes them only at display time, avoiding a duplicate copy of every
    # image in both ``html`` and ``images``.
    document_html = _complete_html(html, css, javascript)
    artifact = {
        "schema_version": CANVAS_SCHEMA_VERSION,
        "id": re.sub(r"[^A-Za-z0-9_.:-]", "_", str(payload.get("canvas_id") or uuid.uuid4().hex))[:96],
        "title": str(payload.get("title") or "קנבס של סמארטי").strip()[:160] or "קנבס של סמארטי",
        "html": document_html,
        "images": cleaned_images,
        "buttons": [button for index, item in enumerate(buttons) if (button := _clean_button(item, index))],
        "button_positions": [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "closed": False,
    }
    serialized = json.dumps({"active_canvases": [artifact]}, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > MAX_CANVAS_CONTEXT_CHARS:
        raise ValueError(
            "Canvas is too large to preserve completely in the model context; reduce the HTML, script, buttons, or images."
        )
    return artifact


def normalize_canvas_artifact(item):
    """Read older or malformed history safely without discarding useful canvas data."""
    if not isinstance(item, dict):
        return None
    try:
        # Preserve a saved HTTPS image even while remote rendering is currently
        # off; the renderer, not history parsing, enforces the user's setting.
        artifact = new_canvas_artifact(item, allow_remote_images=True)
    except ValueError:
        return None
    artifact["id"] = str(item.get("id") or artifact["id"])
    artifact["created_at"] = str(item.get("created_at") or artifact["created_at"])
    artifact["closed"] = bool(item.get("closed", False))
    positions = item.get("button_positions", [])
    if isinstance(positions, list):
        artifact["button_positions"] = [button for index, item in enumerate(positions) if (button := _clean_button(item, index))]
    return artifact


def canvas_artifacts_from_messages(messages, include_closed=False):
    """Return latest versions of canvases in a session, ordered by their last update."""
    by_id = {}
    order = []
    for message in messages or []:
        metadata = message.get("metadata", {}) if isinstance(message, dict) else {}
        canvases = metadata.get("canvases", []) if isinstance(metadata, dict) else []
        if not isinstance(canvases, list):
            continue
        for item in canvases:
            artifact = normalize_canvas_artifact(item)
            if not artifact:
                continue
            canvas_id = artifact["id"]
            if canvas_id not in by_id:
                order.append(canvas_id)
            by_id[canvas_id] = artifact
    result = [by_id[canvas_id] for canvas_id in order]
    return result if include_closed else [item for item in result if not item.get("closed")]


def canvas_context_for_model(canvases):
    """Serialize the active canvas in full so the next model turn can continue it."""
    active = [normalize_canvas_artifact(item) for item in canvases or []]
    active = [item for item in active if item and not item.get("closed")]
    if not active:
        return "אין קנבס חזותי פעיל בשיחה זו."
    payload = {"active_canvases": active}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > MAX_CANVAS_CONTEXT_CHARS:
        # The tool refuses oversized documents. This guard protects old hand-edited
        # history without silently producing a partial canvas description.
        return "קנבס פעיל נשמר בהיסטוריה אך גדול מדי להזרקה בטוחה להקשר המודל."
    return encoded


def materialize_canvas_html(artifact, allow_remote_images=False):
    """Resolve locally persisted image references immediately before rendering."""
    html = str((artifact or {}).get("html") or "")
    for image in (artifact or {}).get("images", []):
        if not isinstance(image, dict) or not image.get("id"):
            continue
        source = image.get("data_url")
        if not source and allow_remote_images:
            source = image.get("url")
        html = html.replace(f"smarti-image://{image['id']}", str(source or "about:blank"))
    return html


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
    """A lazy WebEngine panel with an unavailable-state fallback."""
    canvas_action_requested = pyqtSignal(dict)
    canvas_layout_captured = pyqtSignal(dict)
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._canvas_id = ""
        self._web_view = None
        self._profile = None
        self._bridge = None
        self._allow_remote_images = False
        self._web_settings = None
        self._remote_urls_attribute = None
        self._unavailable_label = QLabel()
        self._unavailable_label.setWordWrap(True)
        self._unavailable_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel("קנבס")
        self.close_button = QPushButton("סגור קנבס")
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
        colors = colors or {}
        text = colors.get("text", "#ffffff")
        muted = colors.get("muted", "#a8b4ca")
        accent = colors.get("accent", "#35d9ff")
        line = colors.get("line", "rgba(255,255,255,0.16)")
        glass = colors.get("glass", "rgba(9,18,38,0.70)")
        self.setStyleSheet(
            f"QFrame {{ background: {glass}; border: 1px solid {line}; border-radius: 20px; }}"
            f"QLabel {{ color: {text}; background: transparent; border: none; font-size: 14px; }}"
            f"QPushButton {{ color: {text}; background: transparent; border: 1px solid {line}; border-radius: 14px; padding: 7px 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ border-color: {accent}; background: rgba(53,217,255,0.12); }}"
        )
        self.title_label.setStyleSheet(f"color: {text}; font-size: 16px; font-weight: 800; background: transparent; border: none;")
        self._unavailable_label.setStyleSheet(f"color: {muted}; background: transparent; border: none; padding: 24px;")

    def _show_unavailable(self, message):
        self._unavailable_label.setText(message)
        self.content_stack.setCurrentWidget(self._unavailable_label)

    def _ensure_web_view(self):
        if self._web_view is not None:
            return True
        if not web_canvas_available():
            self._show_unavailable("קנבס מתקדם זקוק לרכיב PyQt6-WebEngine. הצ׳אט ממשיך לפעול כרגיל.")
            return False
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
            self._web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._web_view.setPage(page)
            self.content_stack.addWidget(self._web_view)
            return True
        except Exception as exc:
            self._show_unavailable(f"לא ניתן היה לאתחל את הקנבס המתקדם. הצ׳אט לא נפגע.\n{exc}")
            return False

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
