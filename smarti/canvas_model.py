"""Pure persisted Canvas artifact model.

This module contains no Qt, renderer, native-window, or HTTP bridge imports so
the agent runtime can validate, persist, and materialize Canvas state headlessly.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import re
import uuid
from datetime import datetime
from urllib.parse import urlparse


CANVAS_SCHEMA_VERSION = 1
MAX_CANVAS_HTML_CHARS = 220_000
MAX_CANVAS_CSS_CHARS = 48_000
MAX_CANVAS_JAVASCRIPT_CHARS = 72_000
MAX_CANVAS_BUTTONS = 80
MAX_CANVAS_CONTEXT_CHARS = 350_000
MAX_CANVAS_IMAGE_DATA_URL_CHARS = 120_000


def web_canvas_available():
    """Return whether the optional legacy Qt renderer can be activated.

    ``find_spec`` on a dotted module imports its parent package.  Query the
    parent search locations explicitly so a headless Core capability check does
    not load ``PyQt6`` merely because the legacy renderer is installed.
    """
    parent = importlib.util.find_spec("PyQt6")
    locations = getattr(parent, "submodule_search_locations", None) if parent else None
    return bool(locations and importlib.machinery.PathFinder.find_spec("PyQt6.QtWebEngineWidgets", locations))


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
        '<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
        f"<style>{css}</style></head><body>{html}<script>{javascript}</script></body></html>"
    )


def new_canvas_artifact(payload, allow_remote_images=False):
    """Validate a tool payload and return a JSON-safe persisted artifact."""
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
    artifact = {
        "schema_version": CANVAS_SCHEMA_VERSION,
        "id": re.sub(r"[^A-Za-z0-9_.:-]", "_", str(payload.get("canvas_id") or uuid.uuid4().hex))[:96],
        "title": str(payload.get("title") or "קנבס של סמארטי").strip()[:160] or "קנבס של סמארטי",
        "html": _complete_html(html, css, javascript),
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
    """Read older or malformed history without discarding valid Canvas data."""
    if not isinstance(item, dict):
        return None
    try:
        artifact = new_canvas_artifact(item, allow_remote_images=True)
    except ValueError:
        return None
    artifact["id"] = str(item.get("id") or artifact["id"])
    artifact["created_at"] = str(item.get("created_at") or artifact["created_at"])
    artifact["closed"] = bool(item.get("closed", False))
    positions = item.get("button_positions", [])
    if isinstance(positions, list):
        artifact["button_positions"] = [
            button for index, position in enumerate(positions)
            if (button := _clean_button(position, index))
        ]
    return artifact


def canvas_artifacts_from_messages(messages, include_closed=False):
    """Return latest Canvas versions in last-update order."""
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
    """Serialize active Canvas state in full for the next model turn."""
    active = [normalize_canvas_artifact(item) for item in canvases or []]
    active = [item for item in active if item and not item.get("closed")]
    if not active:
        return "אין קנבס חזותי פעיל בשיחה זו."
    encoded = json.dumps({"active_canvases": active}, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > MAX_CANVAS_CONTEXT_CHARS:
        return "קנבס פעיל נשמר בהיסטוריה אך גדול מדי להזרקה בטוחה להקשר המודל."
    return encoded


def materialize_canvas_html(artifact, allow_remote_images=False):
    """Resolve persisted image references immediately before rendering."""
    html = str((artifact or {}).get("html") or "")
    for image in (artifact or {}).get("images", []):
        if not isinstance(image, dict) or not image.get("id"):
            continue
        source = image.get("data_url")
        if not source and allow_remote_images:
            source = image.get("url")
        html = html.replace(f"smarti-image://{image['id']}", str(source or "about:blank"))
    return html


__all__ = [
    "CANVAS_SCHEMA_VERSION",
    "MAX_CANVAS_HTML_CHARS",
    "MAX_CANVAS_CSS_CHARS",
    "MAX_CANVAS_JAVASCRIPT_CHARS",
    "MAX_CANVAS_BUTTONS",
    "MAX_CANVAS_CONTEXT_CHARS",
    "MAX_CANVAS_IMAGE_DATA_URL_CHARS",
    "web_canvas_available",
    "new_canvas_artifact",
    "normalize_canvas_artifact",
    "canvas_artifacts_from_messages",
    "canvas_context_for_model",
    "materialize_canvas_html",
]
