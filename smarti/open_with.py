"""Show the Windows application chooser for one local file."""

import ctypes
import os
from ctypes import wintypes


class _OpenAsInfo(ctypes.Structure):
    _fields_ = [
        ("pcszFile", wintypes.LPCWSTR),
        ("pcszClass", wintypes.LPCWSTR),
        ("oaifInFlags", wintypes.DWORD),
    ]


def open_with_dialog(path, parent_hwnd=None):
    """Ask Windows to choose an app and open the selected file with it."""
    if os.name != "nt":
        raise OSError("Windows Open With is unavailable on this platform")

    ole32 = ctypes.WinDLL("ole32")
    initialize = ole32.CoInitializeEx
    initialize.argtypes = (ctypes.c_void_p, wintypes.DWORD)
    initialize.restype = ctypes.c_long
    result = initialize(None, 0x2)  # COINIT_APARTMENTTHREADED
    if result not in (0, 1):  # S_OK or S_FALSE; both require CoUninitialize.
        raise OSError(f"CoInitializeEx failed: HRESULT 0x{result & 0xFFFFFFFF:08X}")

    try:
        if parent_hwnd is None:
            user32 = ctypes.WinDLL("user32")
            foreground = user32.GetForegroundWindow
            foreground.argtypes = ()
            foreground.restype = wintypes.HWND
            parent_hwnd = foreground()

        shell32 = ctypes.WinDLL("shell32")
        show = shell32.SHOpenWithDialog
        show.argtypes = (wintypes.HWND, ctypes.POINTER(_OpenAsInfo))
        show.restype = ctypes.c_long
        info = _OpenAsInfo(str(path), None, 0x4)  # OAIF_EXEC
        result = show(parent_hwnd or None, ctypes.byref(info))
        if result == 0:
            return True
        if result & 0xFFFFFFFF in {0x800704C7, 0x80004004}:  # Cancelled.
            return False
        raise OSError(f"SHOpenWithDialog failed: HRESULT 0x{result & 0xFFFFFFFF:08X}")
    finally:
        ole32.CoUninitialize()
