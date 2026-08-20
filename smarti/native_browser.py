"""Windows Chromium child-window host used when Qt WebEngine is unavailable.

The host launches a dedicated app-mode Chromium window and reparents its native
window into a Qt widget.  The browser keeps a normal CDP endpoint, so Smarti's
existing Playwright control plane and the visible browser share one session.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from ctypes import wintypes

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from .common import SMARTI_BROWSER_DEBUG_PORT, USER_DATA_DIR, WIN_CREATE_NO_WINDOW


IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    _user32.SetParent.restype = wintypes.HWND
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL


GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
WM_CLOSE = 0x0010


def _chromium_windows():
    if not IS_WINDOWS:
        return set()
    handles = set()

    @_EnumWindowsProc
    def visit(hwnd, _lparam):
        buffer = ctypes.create_unicode_buffer(128)
        _user32.GetClassNameW(hwnd, buffer, len(buffer))
        if buffer.value.startswith("Chrome_WidgetWin_"):
            handles.add(int(hwnd))
        return True

    _user32.EnumWindows(visit, 0)
    return handles


def _reserve_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _window_process_id(hwnd):
    if not IS_WINDOWS:
        return 0
    process_id = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(process_id))
    return int(process_id.value)


def _targets(endpoint):
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/json/list", timeout=0.55) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        return [item for item in payload if isinstance(item, dict) and item.get("type") == "page"]
    except Exception:
        return []


class NativeChromiumHost(QWidget):
    """Embed one Chromium app window inside this QWidget."""

    ready = pyqtSignal(bool, str)
    target_ready = pyqtSignal(str)

    def __init__(self, core, profile_mode="persistent", parent=None):
        super().__init__(parent)
        self.core = core
        self.profile_mode = str(profile_mode or "persistent")
        self.endpoint = ""
        self.target_id = ""
        self.current_url = "about:blank"
        self._hwnd = 0
        self._process = None
        self._guest_profile_dir = ""
        self._windows_before = set()
        self._candidate_windows = set()
        self._targets_before = set()
        self._poll_started = 0.0
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(90)
        self._poll_timer.timeout.connect(self._poll_for_window)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def is_ready(self):
        return bool(self._hwnd and (not IS_WINDOWS or _user32.IsWindow(self._hwnd)))

    def start(self, initial_url="about:blank"):
        if self.is_ready():
            self._resize_child()
            return True
        if self._poll_timer.isActive():
            return True
        if not IS_WINDOWS:
            self.ready.emit(False, "הדפדפן המוטמע זמין ב-Windows בלבד.")
            return False
        executable = getattr(self.core, "_chrome_executable", lambda: None)() if self.core is not None else None
        if not executable:
            candidates = [
                os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ]
            executable = next((candidate for candidate in candidates if os.path.isfile(candidate)), None)
        if not executable:
            self.ready.emit(False, "לא נמצא במחשב מנוע Chromium תואם.")
            return False
        self.current_url = str(initial_url or "about:blank")
        self._windows_before = _chromium_windows()
        if self.profile_mode == "persistent":
            port = SMARTI_BROWSER_DEBUG_PORT
            profile_dir = (
                getattr(self.core, "_automation_browser_profile_dir")()
                if self.core is not None
                else os.path.join(USER_DATA_DIR, "browser", "native-profile")
            )
        else:
            port = _reserve_port()
            guest_root = os.path.join(USER_DATA_DIR, "browser", "guest")
            os.makedirs(guest_root, exist_ok=True)
            self._guest_profile_dir = tempfile.mkdtemp(prefix="session-", dir=guest_root)
            profile_dir = self._guest_profile_dir
        self.endpoint = f"http://127.0.0.1:{port}"
        self._targets_before = {str(item.get("id") or "") for item in _targets(self.endpoint)}
        args = [
            executable,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-session-crashed-bubble",
            "--disable-popup-blocking",
            "--disable-extensions",
            "--disable-blink-features=AutomationControlled",
            "--window-position=-32000,-32000",
            "--window-size=1100,800",
            "--new-window",
            f"--app={self.current_url}",
        ]
        try:
            allow_insecure = bool(getattr(self.core, "_allow_insecure_ssl", lambda: False)()) if self.core is not None else False
            if allow_insecure:
                args.extend(["--ignore-certificate-errors", "--allow-running-insecure-content", "--test-type"])
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=getattr(self.core, "_subprocess_env", lambda: os.environ.copy())() if self.core is not None else os.environ.copy(),
                creationflags=WIN_CREATE_NO_WINDOW,
            )
        except Exception as exc:
            self.ready.emit(False, f"הפעלת הדפדפן המוטמע נכשלה: {exc}")
            return False
        self._poll_started = time.monotonic()
        self._poll_timer.start()
        return True

    def _poll_for_window(self):
        if self._hwnd and not _user32.IsWindow(self._hwnd):
            self._hwnd = 0
        if not self._hwnd:
            candidates = list(_chromium_windows() - self._windows_before)
            self._candidate_windows.update(candidates)
            candidates = [hwnd for hwnd in candidates if _user32.IsWindowVisible(hwnd)] or candidates
            if candidates:
                process_id = int(getattr(self._process, "pid", 0) or 0)
                owned = [hwnd for hwnd in candidates if process_id and _window_process_id(hwnd) == process_id]
                self._attach(sorted(owned or candidates)[-1])
        if not self.target_id:
            targets = _targets(self.endpoint)
            fresh = [item for item in targets if str(item.get("id") or "") not in self._targets_before]
            selected = fresh[-1] if fresh else (targets[-1] if targets else None)
            if selected:
                self.target_id = str(selected.get("id") or "")
                self.current_url = str(selected.get("url") or self.current_url)
                self.target_ready.emit(self.target_id)
        if self._hwnd and (self.target_id or time.monotonic() - self._poll_started > 2.5):
            self._poll_timer.stop()
            self.ready.emit(True, "")
            return
        if time.monotonic() - self._poll_started > 14:
            self._poll_timer.stop()
            self._close_unattached_windows()
            self.ready.emit(False, "מנוע הדפדפן הופעל, אך לא ניתן היה לעגן את החלון בתוך סמארטי.")

    def _close_unattached_windows(self):
        for hwnd in tuple(self._candidate_windows):
            if hwnd != self._hwnd and IS_WINDOWS and _user32.IsWindow(hwnd):
                _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        self._candidate_windows.clear()

    def _attach(self, hwnd):
        self._hwnd = int(hwnd)
        self._candidate_windows.discard(self._hwnd)
        host = int(self.winId())
        style = int(_user32.GetWindowLongPtrW(self._hwnd, GWL_STYLE))
        style &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
        style |= WS_CHILD | WS_VISIBLE
        exstyle = int(_user32.GetWindowLongPtrW(self._hwnd, GWL_EXSTYLE))
        exstyle &= ~WS_EX_APPWINDOW
        exstyle |= WS_EX_TOOLWINDOW
        _user32.SetWindowLongPtrW(self._hwnd, GWL_STYLE, style)
        _user32.SetWindowLongPtrW(self._hwnd, GWL_EXSTYLE, exstyle)
        _user32.SetParent(self._hwnd, host)
        self._resize_child(frame_changed=True)

    def _resize_child(self, frame_changed=False):
        if not self.is_ready():
            return
        flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW
        if frame_changed:
            flags |= SWP_FRAMECHANGED
        _user32.SetWindowPos(self._hwnd, 0, 0, 0, max(1, self.width()), max(1, self.height()), flags)

    def capture(self):
        if not self.is_ready():
            return self.grab()
        center = self.mapToGlobal(self.rect().center())
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        if screen is None:
            return self.grab()
        pixmap = screen.grabWindow(int(self._hwnd))
        return pixmap if not pixmap.isNull() else self.grab()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_child()

    def showEvent(self, event):
        super().showEvent(event)
        self._resize_child()

    def stop(self):
        self._poll_timer.stop()
        self._close_unattached_windows()
        if self._hwnd and IS_WINDOWS and _user32.IsWindow(self._hwnd):
            _user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        self._hwnd = 0
        if self.profile_mode != "persistent" and self._process is not None:
            try:
                self._process.wait(timeout=1.5)
            except Exception:
                try:
                    self._process.terminate()
                except Exception:
                    pass
        self._process = None
        if self._guest_profile_dir:
            shutil.rmtree(self._guest_profile_dir, ignore_errors=True)
            self._guest_profile_dir = ""

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
