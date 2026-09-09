"""One cancellable, pollable speech session shared by both desktops."""
from __future__ import annotations

import logging
import threading
import uuid


def _mci(command):
    import ctypes
    result = ctypes.create_unicode_buffer(256)
    error = ctypes.windll.winmm.mciSendStringW(command, result, len(result), None)
    if error:
        ctypes.windll.winmm.mciGetErrorStringW(error, result, len(result))
        raise RuntimeError(result.value or f"Windows audio error {error}")
    return result.value


def play_windows_mp3(audio, cancel, volume):
    """Use Windows' audio device without importing SDL/numpy on a worker thread."""
    import os
    import tempfile
    alias = f"smarti_tts_{uuid.uuid4().hex}"
    path = ""
    opened = False
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
            path = handle.name
            handle.write(audio)
        if cancel.is_set():
            return
        _mci(f'open "{path}" type mpegvideo alias {alias}')
        opened = True
        _mci(f"setaudio {alias} volume to {round(volume() * 1000)}")
        if cancel.is_set():
            return
        _mci(f"play {alias}")
        while not cancel.wait(0.1) and _mci(f"status {alias} mode").strip().lower() == "playing":
            _mci(f"setaudio {alias} volume to {round(volume() * 1000)}")
    finally:
        if opened:
            try:
                _mci(f"close {alias}")
            except Exception:
                logging.warning("Could not close Windows speech device", exc_info=True)
        if path:
            try:
                os.remove(path)
            except OSError:
                logging.warning("Could not remove temporary speech audio")


class TtsSessionController:
    def __init__(self, speaker, status_callback):
        self._speaker = speaker
        self._status_callback = status_callback
        self._lock = threading.RLock()
        self._playback_lock = threading.Lock()
        self._cancel = threading.Event()
        self._state = {"protocol_version": 1, "request_id": "", "owner_id": "", "is_playing": False, "error": ""}

    def snapshot(self):
        with self._lock:
            return dict(self._state)

    def _notify(self, playing):
        try:
            self._status_callback(playing)
        except Exception:
            logging.exception("TTS status callback failed")

    def _prepare(self, owner_id):
        with self._lock:
            self._cancel.set()
            self._cancel = threading.Event()
            self._state = {"protocol_version": 1, "request_id": uuid.uuid4().hex, "owner_id": owner_id, "is_playing": True, "error": ""}
            self._notify(True)
            return dict(self._state), self._cancel

    def start(self, text, *, background=True, owner_id=""):
        state, cancel = self._prepare(owner_id)
        args = (state["request_id"], text, cancel)
        if background:
            threading.Thread(target=self._run, args=args, name="SmartiDesktopTTS", daemon=True).start()
        else:
            self._run(*args)
        return state

    def stop(self, request_id=None):
        with self._lock:
            if request_id and self._state["request_id"] != request_id:
                return dict(self._state)
            self._cancel.set()
            self._state.update(is_playing=False, error="")
            self._notify(False)
            return dict(self._state)

    def _run(self, request_id, text, cancel):
        error = ""
        try:
            with self._playback_lock:
                if not cancel.is_set():
                    self._speaker(text, cancel)
        except Exception as exc:
            if not cancel.is_set():
                logging.exception("TTS playback failed")
                error = f"לא ניתן להשמיע את ההקראה: {exc}"
        finally:
            with self._lock:
                if self._state["request_id"] == request_id:
                    self._state.update(is_playing=False, error="" if cancel.is_set() else error)
                    self._notify(False)
