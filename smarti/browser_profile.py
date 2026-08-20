"""Safe, user-initiated import helpers for Smarti's embedded browser profile.

The import is deliberately copy based: browser databases are never opened in
place and the source profile is never modified. Passwords are outside the
scope of this module. Cookies are imported only when Windows can decrypt them
for the current user. Modern application-bound cookies are skipped by the
direct database reader; a user-initiated import may recover compatible entries
by launching the source browser against a disposable copy of that profile.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:  # pragma: no cover - dependency is optional at import time.
    AESGCM = None


@dataclass(frozen=True)
class BrowserProfileSource:
    browser_id: str
    browser_name: str
    profile_name: str
    user_data_dir: str
    profile_dir: str

    @property
    def label(self):
        return f"{self.browser_name} — {self.profile_name}"


def _browser_roots(local_app_data=None):
    local = Path(local_app_data or os.environ.get("LOCALAPPDATA", ""))
    return (
        ("chrome", "Google Chrome", local / "Google" / "Chrome" / "User Data"),
        ("edge", "Microsoft Edge", local / "Microsoft" / "Edge" / "User Data"),
        ("brave", "Brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
        ("chromium", "Chromium", local / "Chromium" / "User Data"),
        ("vivaldi", "Vivaldi", local / "Vivaldi" / "User Data"),
    )


def _profile_display_name(profile_dir, user_data_dir=None):
    profile_key = Path(profile_dir).name
    if user_data_dir:
        try:
            state = json.loads((Path(user_data_dir) / "Local State").read_text(encoding="utf-8"))
            cached = ((state.get("profile") or {}).get("info_cache") or {}).get(profile_key) or {}
            for key in ("gaia_name", "name", "user_name", "shortcut_name"):
                name = str(cached.get(key) or "").strip()
                if name:
                    return name
        except Exception:
            pass
    preferences = Path(profile_dir) / "Preferences"
    try:
        data = json.loads(preferences.read_text(encoding="utf-8"))
        name = str((data.get("profile") or {}).get("name") or "").strip()
        if name:
            return name
    except Exception:
        pass
    return "ברירת מחדל" if Path(profile_dir).name == "Default" else Path(profile_dir).name


def _profile_sort_key(path):
    name = Path(path).name
    match = re.fullmatch(r"Profile\s+(\d+)", name, flags=re.IGNORECASE)
    if name.casefold() == "default":
        return (0, 0, "")
    if match:
        return (1, int(match.group(1)), "")
    return (2, 0, name.casefold())


def discover_browser_profiles(local_app_data=None):
    """Return supported local Chromium profiles without touching their data."""
    sources = []
    for browser_id, browser_name, root in _browser_roots(local_app_data):
        if not root.is_dir():
            continue
        candidates = []
        default = root / "Default"
        if default.is_dir():
            candidates.append(default)
        try:
            candidates.extend(
                sorted(
                    (path for path in root.iterdir() if path.is_dir() and path.name.startswith("Profile ")),
                    key=_profile_sort_key,
                )
            )
        except OSError:
            pass
        browser_sources = []
        for profile in candidates:
            if not any((profile / name).exists() for name in ("Preferences", "History", "Network")):
                continue
            browser_sources.append(
                BrowserProfileSource(
                    browser_id=browser_id,
                    browser_name=browser_name,
                    profile_name=_profile_display_name(profile, root),
                    user_data_dir=str(root),
                    profile_dir=str(profile),
                )
            )
        duplicate_names = {
            source.profile_name.casefold()
            for source in browser_sources
            if sum(1 for item in browser_sources if item.profile_name.casefold() == source.profile_name.casefold()) > 1
        }
        for source in browser_sources:
            if source.profile_name.casefold() not in duplicate_names:
                sources.append(source)
                continue
            folder_name = Path(source.profile_dir).name
            sources.append(
                BrowserProfileSource(
                    browser_id=source.browser_id,
                    browser_name=source.browser_name,
                    profile_name=f"{source.profile_name} ({folder_name})",
                    user_data_dir=source.user_data_dir,
                    profile_dir=source.profile_dir,
                )
            )
    return sources


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_unprotect(payload):
    if os.name != "nt" or not payload:
        return None
    source = ctypes.create_string_buffer(bytes(payload), len(payload))
    source_blob = _DataBlob(len(payload), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    target_blob = _DataBlob()
    try:
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source_blob), None, None, None, None, 0, ctypes.byref(target_blob)
        )
        if not ok:
            return None
        return ctypes.string_at(target_blob.pbData, target_blob.cbData)
    except Exception:
        return None
    finally:
        if target_blob.pbData:
            try:
                ctypes.windll.kernel32.LocalFree(target_blob.pbData)
            except Exception:
                pass


def _profile_aes_key(user_data_dir):
    try:
        state = json.loads((Path(user_data_dir) / "Local State").read_text(encoding="utf-8"))
        encoded = str((state.get("os_crypt") or {}).get("encrypted_key") or "")
        raw = base64.b64decode(encoded)
        if raw.startswith(b"DPAPI"):
            raw = raw[5:]
        return _dpapi_unprotect(raw)
    except Exception:
        return None


def _decrypt_chromium_cookie_bytes(encrypted_value, aes_key=None):
    blob = bytes(encrypted_value or b"")
    if not blob:
        return b""
    if blob.startswith(b"v20"):
        return None
    if blob[:3] in (b"v10", b"v11") and aes_key and AESGCM is not None:
        try:
            nonce = blob[3:15]
            return AESGCM(aes_key).decrypt(nonce, blob[15:], None)
        except Exception:
            return None
    return _dpapi_unprotect(blob)


def decrypt_chromium_cookie(encrypted_value, aes_key=None):
    """Best-effort decryption for current-user DPAPI/AES cookies.

    Chromium's ``v20`` application-bound encryption intentionally cannot be
    decrypted by an unrelated desktop process. It is therefore skipped here;
    the complete import flow can try the disposable source-browser path.
    """
    clear = _decrypt_chromium_cookie_bytes(encrypted_value, aes_key)
    if clear is None:
        return None
    try:
        return clear.decode("utf-8")
    except UnicodeDecodeError:
        return clear.decode("utf-8", errors="replace")


def _copied_sqlite(path):
    temp_dir = tempfile.mkdtemp(prefix="smarti-browser-import-")
    target = os.path.join(temp_dir, os.path.basename(path))
    shutil.copy2(path, target)
    for suffix in ("-wal", "-shm"):
        source_sidecar = str(path) + suffix
        if os.path.exists(source_sidecar):
            try:
                shutil.copy2(source_sidecar, target + suffix)
            except OSError:
                pass
    return temp_dir, target


def _chrome_time_to_iso(value):
    try:
        micros = int(value or 0)
        if micros <= 0:
            return ""
        moment = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=micros)
        return moment.isoformat()
    except Exception:
        return ""


def read_history(source, limit=5000):
    history_path = Path(source.profile_dir) / "History"
    if not history_path.is_file():
        return []
    temp_dir, copied = _copied_sqlite(history_path)
    try:
        with sqlite3.connect(copied) as db:
            rows = db.execute(
                "SELECT url, title, visit_count, last_visit_time FROM urls "
                "WHERE hidden=0 ORDER BY last_visit_time DESC LIMIT ?",
                (max(1, min(int(limit), 20000)),),
            ).fetchall()
        return [
            {
                "url": str(url or ""),
                "title": str(title or ""),
                "visit_count": int(visit_count or 0),
                "last_visit_at": _chrome_time_to_iso(last_visit_time),
            }
            for url, title, visit_count, last_visit_time in rows
            if str(url or "").startswith(("http://", "https://"))
        ]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _walk_bookmark_nodes(node, result):
    if not isinstance(node, dict):
        return
    if node.get("type") == "url" and str(node.get("url") or "").startswith(("http://", "https://")):
        result.append({"title": str(node.get("name") or ""), "url": str(node.get("url") or "")})
    for child in node.get("children") or []:
        _walk_bookmark_nodes(child, result)


def read_bookmarks(source):
    path = Path(source.profile_dir) / "Bookmarks"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    result = []
    for root in (data.get("roots") or {}).values():
        _walk_bookmark_nodes(root, result)
    return result


def read_cookies(source, limit=20000):
    cookie_path = Path(source.profile_dir) / "Network" / "Cookies"
    if not cookie_path.is_file():
        cookie_path = Path(source.profile_dir) / "Cookies"
    if not cookie_path.is_file():
        return [], {"skipped_encrypted": 0, "read": 0}
    key = _profile_aes_key(source.user_data_dir)
    temp_dir, copied = _copied_sqlite(cookie_path)
    imported = []
    skipped = 0
    try:
        with sqlite3.connect(copied) as db:
            columns = {str(row[1]) for row in db.execute("PRAGMA table_info(cookies)").fetchall()}
            try:
                meta_row = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
                database_version = int(meta_row[0]) if meta_row else 0
            except Exception:
                database_version = 0
            wanted = [
                "host_key", "name", "value", "encrypted_value", "path", "expires_utc",
                "is_secure", "is_httponly",
            ]
            selected = [name for name in wanted if name in columns]
            rows = db.execute(
                f"SELECT {', '.join(selected)} FROM cookies ORDER BY last_access_utc DESC LIMIT ?",
                (max(1, min(int(limit), 50000)),),
            ).fetchall()
        for row in rows:
            item = dict(zip(selected, row))
            value = str(item.get("value") or "")
            if not value and item.get("encrypted_value"):
                clear = _decrypt_chromium_cookie_bytes(item.get("encrypted_value"), key)
                if clear is None:
                    skipped += 1
                    continue
                # Cookie DB version 24+ authenticates the host by prefixing a
                # SHA-256 digest to the decrypted value.
                if database_version >= 24 and len(clear) >= 32:
                    clear = clear[32:]
                value = clear.decode("utf-8", errors="replace")
            domain = str(item.get("host_key") or "").strip()
            name = str(item.get("name") or "")
            if not domain or not name:
                continue
            imported.append(
                {
                    "domain": domain,
                    "name": name,
                    "value": value,
                    "path": str(item.get("path") or "/"),
                    "expires_at": _chrome_time_to_iso(item.get("expires_utc")),
                    "secure": bool(item.get("is_secure")),
                    "http_only": bool(item.get("is_httponly")),
                }
            )
        return imported, {"skipped_encrypted": skipped, "read": len(rows)}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _source_browser_executable(source):
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", "")
    program_x86 = os.environ.get("PROGRAMFILES(X86)", "")
    candidates = {
        "chrome": [
            os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(program_x86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
        ],
        "edge": [
            os.path.join(program_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
        ],
        "brave": [os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")],
        "vivaldi": [os.path.join(local, "Vivaldi", "Application", "vivaldi.exe")],
        "chromium": [shutil.which("chromium.exe") or ""],
    }.get(source.browser_id, [])
    return next((path for path in candidates if path and os.path.isfile(path)), "")


def _free_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def read_cookies_via_source_browser(source):
    """Ask a disposable copy of the source browser to decrypt its own cookies.

    This is the best-effort path for modern application-bound cookie
    encryption.  The real profile is not launched or modified.
    """
    executable = _source_browser_executable(source)
    if not executable:
        return []
    temp_root = tempfile.mkdtemp(prefix="smarti-browser-profile-copy-")
    process = None
    playwright = None
    browser = None
    try:
        local_state = Path(source.user_data_dir) / "Local State"
        if local_state.is_file():
            shutil.copy2(local_state, os.path.join(temp_root, "Local State"))
        profile_directory = Path(source.profile_dir).name or "Default"
        target_profile = Path(temp_root) / profile_directory
        target_network = target_profile / "Network"
        target_network.mkdir(parents=True, exist_ok=True)
        for name in ("Preferences", "Secure Preferences"):
            candidate = Path(source.profile_dir) / name
            if candidate.is_file():
                shutil.copy2(candidate, target_profile / name)
        source_cookie = Path(source.profile_dir) / "Network" / "Cookies"
        if not source_cookie.is_file():
            source_cookie = Path(source.profile_dir) / "Cookies"
        if not source_cookie.is_file():
            return []
        shutil.copy2(source_cookie, target_network / "Cookies")
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(source_cookie) + suffix)
            if sidecar.is_file():
                try:
                    shutil.copy2(sidecar, Path(str(target_network / "Cookies") + suffix))
                except OSError:
                    pass
        port = _free_loopback_port()
        args = [
            executable,
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={temp_root}",
            f"--profile-directory={profile_directory}",
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            "about:blank",
        ]
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        deadline = time.time() + 12
        endpoint = f"http://127.0.0.1:{port}/json/version"
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(endpoint, timeout=0.5) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.2)
        else:
            return []
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=8000)
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            return []
        result = []
        raw_cookies = []
        try:
            pages = list(context.pages)
            page = pages[0] if pages else context.new_page()
            session = context.new_cdp_session(page)
            try:
                raw_cookies = list((session.send("Storage.getCookies") or {}).get("cookies") or [])
            finally:
                session.detach()
        except Exception:
            raw_cookies = list(context.cookies())
        for item in raw_cookies:
            expires = float(item.get("expires") or -1)
            expires_at = ""
            if expires > 0:
                expires_at = datetime.fromtimestamp(expires, timezone.utc).isoformat()
            result.append(
                {
                    "domain": str(item.get("domain") or ""),
                    "name": str(item.get("name") or ""),
                    "value": str(item.get("value") or ""),
                    "path": str(item.get("path") or "/"),
                    "expires_at": expires_at,
                    "secure": bool(item.get("secure")),
                    "http_only": bool(item.get("httpOnly")),
                }
            )
        return result
    except Exception:
        return []
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        shutil.rmtree(temp_root, ignore_errors=True)


def import_profile_data(source, *, include_cookies=True, include_history=True, include_bookmarks=True):
    """Read selected data and return a portable payload for the UI layer."""
    result = {
        "source": {
            "browser_id": source.browser_id,
            "browser_name": source.browser_name,
            "profile_name": source.profile_name,
        },
        "cookies": [],
        "history": [],
        "bookmarks": [],
        "cookie_stats": {"skipped_encrypted": 0, "read": 0},
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    if include_cookies:
        result["cookies"], result["cookie_stats"] = read_cookies(source)
        if result["cookie_stats"].get("skipped_encrypted"):
            browser_cookies = read_cookies_via_source_browser(source)
            merged = {
                (item.get("domain"), item.get("name"), item.get("path")): item
                for item in result["cookies"]
            }
            for item in browser_cookies:
                merged[(item.get("domain"), item.get("name"), item.get("path"))] = item
            recovered = max(0, len(merged) - len(result["cookies"]))
            result["cookies"] = list(merged.values())
            result["cookie_stats"]["recovered_via_source_browser"] = recovered
            result["cookie_stats"]["unrecovered_encrypted"] = max(
                0, int(result["cookie_stats"].get("skipped_encrypted") or 0) - recovered
            )
    if include_history:
        result["history"] = read_history(source)
    if include_bookmarks:
        result["bookmarks"] = read_bookmarks(source)
    return result
