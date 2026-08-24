"""Qt-free voice recognition shared by the legacy and Tauri desktops."""
from __future__ import annotations

import copy
import ctypes
import logging
import os
import threading
import time
import uuid

from .common import ASSETS_DIR, SPEECH_INSTALLED

try:
    import winsound
except ImportError:  # pragma: no cover - Windows is the product target.
    winsound = None


_SOUND_LOCK = threading.Lock()


def _bounded_float(settings, key, default, minimum, maximum):
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _bounded_int(settings, key, default, minimum, maximum):
    try:
        value = int(float(settings.get(key, default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _voice_sound_path(kind, extensions=(".mp3", ".wav")):
    names = {
        "start": ("voice_listen_start", "voice_start", "listen_start"),
        "end": ("voice_listen_end", "voice_end", "listen_end"),
        "timeout": ("voice_listen_timeout", "voice_timeout", "listen_timeout"),
    }
    for stem in names.get(str(kind or ""), ()):
        for extension in extensions:
            path = os.path.join(ASSETS_DIR, f"{stem}{extension}")
            if os.path.isfile(path):
                return path
    return ""


def _play_sound(kind, settings):
    if not bool(settings.get("voice_beep_enabled", True)) or winsound is None:
        return
    path = _voice_sound_path(kind)
    fallback = {
        "start": "SystemAsterisk",
        "end": "SystemNotification",
        "timeout": "SystemExclamation",
    }.get(str(kind or ""), "SystemNotification")
    try:
        with _SOUND_LOCK:
            if path and os.path.splitext(path)[1].lower() == ".mp3" and os.name == "nt":
                alias = f"smarti_voice_{uuid.uuid4().hex}"
                opened = False
                try:
                    result = ctypes.windll.winmm.mciSendStringW(
                        f'open "{path}" type mpegvideo alias {alias}', None, 0, None
                    )
                    if result:
                        raise OSError(f"MCI error {result}")
                    opened = True
                    result = ctypes.windll.winmm.mciSendStringW(
                        f"play {alias} wait", None, 0, None
                    )
                    if result:
                        raise OSError(f"MCI error {result}")
                finally:
                    if opened:
                        ctypes.windll.winmm.mciSendStringW(
                            f"close {alias}", None, 0, None
                        )
            elif path:
                winsound.PlaySound(
                    path, winsound.SND_FILENAME | winsound.SND_NOSTOP
                )
            else:
                winsound.PlaySound(
                    fallback, winsound.SND_ALIAS | winsound.SND_NOSTOP
                )
    except Exception as exc:
        logging.warning("Voice sound failed (%s): %s", kind, exc)


def _play_sound_background(kind, settings):
    if not bool(settings.get("voice_beep_enabled", True)):
        return
    threading.Thread(
        target=_play_sound,
        args=(kind, copy.deepcopy(settings)),
        name=f"SmartiVoiceSound-{kind}",
        daemon=True,
    ).start()


def recognize_voice(settings=None, cancel_event=None, status_callback=None):
    """Listen once and return Hebrew text while preserving legacy settings."""
    settings = copy.deepcopy(settings or {})
    cancel_event = cancel_event or threading.Event()
    status_callback = status_callback or (lambda _status: None)
    if not SPEECH_INSTALLED:
        raise RuntimeError("זיהוי קולי אינו מותקן")
    try:
        import speech_recognition as sr
    except ImportError as exc:  # pragma: no cover - guarded above.
        raise RuntimeError("זיהוי קולי אינו מותקן") from exc

    recognizer = sr.Recognizer()
    sensitivity = _bounded_int(settings, "voice_sensitivity", 70, 1, 100)
    ratio = (100 - sensitivity) / 99.0
    recognizer.energy_threshold = int(50 + (4000 - 50) * (ratio ** 2.3))
    recognizer.dynamic_energy_threshold = bool(
        settings.get("voice_dynamic_energy_threshold", False)
    )
    recognizer.pause_threshold = _bounded_float(
        settings, "voice_pause_threshold", 0.8, 0.3, 5.0
    )
    recognizer.non_speaking_duration = max(
        0.1, min(1.0, recognizer.pause_threshold / 2.0)
    )
    listen_timeout = _bounded_float(
        settings, "voice_listen_timeout", 6, 1, 30
    )
    ambient_duration = _bounded_float(
        settings, "voice_ambient_noise_duration", 0.0, 0.0, 3.0
    )

    status_callback("פותח מיקרופון...")
    with sr.Microphone() as source:
        if cancel_event.is_set():
            return ""
        if ambient_duration > 0:
            status_callback("מכוון רעש רקע...")
            recognizer.adjust_for_ambient_noise(source, duration=ambient_duration)
        if cancel_event.is_set():
            return ""
        status_callback("מקשיב...")
        _play_sound_background("start", settings)
        try:
            audio = recognizer.listen(source, timeout=listen_timeout)
        except sr.WaitTimeoutError:
            _play_sound("timeout", settings)
            return ""
        if cancel_event.is_set():
            return ""
        _play_sound("end", settings)
        status_callback("מתמלל...")
        text = recognizer.recognize_google(audio, language="he-IL")
        text = text.replace("סמרטי", "סמארטי").replace("סמארט", "סמארטי")
        return "" if cancel_event.is_set() else text


class VoiceSessionController:
    """Own one cancellable desktop dictation session with pollable state."""

    def __init__(self, settings_provider, recognizer=recognize_voice):
        self._settings_provider = settings_provider
        self._recognizer = recognizer
        self._lock = threading.RLock()
        self._cancel_event = None
        self._thread = None
        self._state = self._idle_state()

    @staticmethod
    def _idle_state():
        return {
            "session_id": "",
            "active": False,
            "status": "",
            "transcript": "",
            "error": "",
            "cancelled": False,
            "completed_at": 0.0,
        }

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return copy.deepcopy(self._state)
            session_id = uuid.uuid4().hex
            self._cancel_event = threading.Event()
            self._state = {
                **self._idle_state(),
                "session_id": session_id,
                "active": True,
                "status": "מפעיל האזנה...",
            }
            self._thread = threading.Thread(
                target=self._run,
                args=(session_id, self._cancel_event),
                name="SmartiDesktopVoice",
                daemon=True,
            )
            self._thread.start()
            return copy.deepcopy(self._state)

    def _set_status(self, session_id, value):
        with self._lock:
            if self._state["session_id"] == session_id:
                self._state["status"] = str(value or "")

    def _run(self, session_id, cancel_event):
        transcript = ""
        error = ""
        try:
            transcript = self._recognizer(
                copy.deepcopy(self._settings_provider() or {}),
                cancel_event,
                lambda value: self._set_status(session_id, value),
            )
        except Exception as exc:
            logging.exception("Voice recognition failed")
            error = str(exc) or "לא ניתן היה לזהות דיבור"
        with self._lock:
            if self._state["session_id"] != session_id:
                return
            cancelled = cancel_event.is_set()
            self._state.update(
                {
                    "active": False,
                    "status": "ההאזנה בוטלה" if cancelled else "",
                    "transcript": "" if cancelled else str(transcript or ""),
                    "error": "" if cancelled else error,
                    "cancelled": cancelled,
                    "completed_at": time.time(),
                }
            )

    def cancel(self):
        with self._lock:
            if self._cancel_event:
                self._cancel_event.set()
            if self._state["active"]:
                self._state["status"] = "מפסיק האזנה..."
            return copy.deepcopy(self._state)
