"""GitHub release update checks and installer handoff for SmartiAI."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
import os
import re
import subprocess
import sys
import platform

import requests
from PyQt6.QtCore import QThread, pyqtSignal

from .common import (
    APP_VERSION,
    SMARTI_APP_DISPLAY_NAME,
    SMARTI_RUNTIME,
    USER_DATA_DIR,
    WIN_CREATE_NO_WINDOW,
    ssl_request_kwargs,
)


GITHUB_OWNER = "menachem-dadon"
GITHUB_REPO = "SmartiAI-Agent-for-Windows"
GITHUB_API_RELEASE_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
if platform.system() == "Windows":
    SETUP_ASSET_RE = re.compile(r"(?i)\bsetup\b.*\.exe$")
else:
    SETUP_ASSET_RE = re.compile(r"(?i)\b(macos|osx|darwin)\b.*\.(dmg|zip|pkg)$")


@dataclass
class UpdateInfo:
    current_version: str
    version: str
    tag_name: str
    name: str
    html_url: str
    published_at: str
    release_notes: str
    asset_name: str
    asset_url: str
    asset_size: int = 0
    asset_digest: str = ""
    prerelease: bool = False

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, cls):
            return data
        return cls(
            current_version=str(data.get("current_version") or APP_VERSION),
            version=str(data.get("version") or ""),
            tag_name=str(data.get("tag_name") or ""),
            name=str(data.get("name") or ""),
            html_url=str(data.get("html_url") or ""),
            published_at=str(data.get("published_at") or ""),
            release_notes=str(data.get("release_notes") or ""),
            asset_name=str(data.get("asset_name") or ""),
            asset_url=str(data.get("asset_url") or ""),
            asset_size=int(data.get("asset_size") or 0),
            asset_digest=str(data.get("asset_digest") or ""),
            prerelease=bool(data.get("prerelease")),
        )


def _version_parts(value):
    raw = str(value or "").strip()
    if not raw or raw.lower() == "dev":
        return ()
    raw = re.sub(r"^[vV]", "", raw)
    parts = [int(part.lstrip("0") or "0") for part in re.findall(r"\d+", raw)[:4]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer_version(candidate, current=APP_VERSION):
    candidate_parts = _version_parts(candidate)
    current_parts = _version_parts(current)
    if not candidate_parts:
        return False
    if not current_parts:
        return True
    length = max(len(candidate_parts), len(current_parts))
    return candidate_parts + (0,) * (length - len(candidate_parts)) > current_parts + (0,) * (length - len(current_parts))


def _headers():
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{SMARTI_APP_DISPLAY_NAME}/{APP_VERSION}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _request_kwargs(settings=None):
    settings = settings or {}
    kwargs = ssl_request_kwargs(bool(settings.get("allow_insecure_ssl_compat", True)))
    kwargs["timeout"] = 25
    return kwargs


def _select_setup_asset(release):
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        return {}
    setup_assets = []
    fallback_assets = []
    is_windows = platform.system() == "Windows"
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        lower = name.lower()
        if is_windows:
            if lower.endswith(".exe"):
                fallback_assets.append(asset)
                if SETUP_ASSET_RE.search(name) or "setup" in lower:
                    setup_assets.append(asset)
        else:
            if lower.endswith(".dmg") or lower.endswith(".pkg") or lower.endswith(".zip"):
                fallback_assets.append(asset)
                if SETUP_ASSET_RE.search(name) or "macos" in lower or "darwin" in lower or "osx" in lower:
                    setup_assets.append(asset)
    return (setup_assets or fallback_assets or [{}])[0]


def check_for_updates(settings=None):
    response = requests.get(GITHUB_API_RELEASE_LATEST, headers=_headers(), **_request_kwargs(settings))
    response.raise_for_status()
    release = response.json()
    if not isinstance(release, dict):
        raise RuntimeError("GitHub returned an unexpected release payload.")

    tag_name = str(release.get("tag_name") or release.get("name") or "").strip()
    version = re.sub(r"^[vV]", "", tag_name).strip() or tag_name
    if not is_newer_version(version, APP_VERSION):
        return None

    asset = _select_setup_asset(release)
    return UpdateInfo(
        current_version=APP_VERSION,
        version=version,
        tag_name=tag_name,
        name=str(release.get("name") or tag_name or f"SmartiAI {version}"),
        html_url=str(release.get("html_url") or GITHUB_RELEASES_URL),
        published_at=str(release.get("published_at") or ""),
        release_notes=str(release.get("body") or ""),
        asset_name=str(asset.get("name") or ""),
        asset_url=str(asset.get("browser_download_url") or ""),
        asset_size=int(asset.get("size") or 0),
        asset_digest=str(asset.get("digest") or ""),
        prerelease=bool(release.get("prerelease")),
    )


def _safe_asset_name(name, version):
    name = os.path.basename(str(name or "").strip())
    if not name:
        ext = ".exe" if platform.system() == "Windows" else ".zip"
        name = f"SmartiAI-Agent-{platform.system()}-{version}{ext}"
    return re.sub(r"[^A-Za-z0-9_.() -]+", "-", name)[:180]


def _expected_sha256(digest):
    value = str(digest or "").strip()
    match = re.match(r"(?i)^sha256:([a-f0-9]{64})$", value)
    return match.group(1).lower() if match else ""


def download_update(update_info, settings=None, progress_callback=None):
    info = UpdateInfo.from_dict(update_info)
    if not info.asset_url:
        ext_desc = "Windows Setup EXE" if platform.system() == "Windows" else "macOS DMG/ZIP package"
        raise RuntimeError(f"No {ext_desc} was attached to the GitHub release.")

    target_dir = os.path.join(USER_DATA_DIR, "updates", _safe_asset_name(info.version, info.version))
    os.makedirs(target_dir, exist_ok=True)
    target_path = os.path.join(target_dir, _safe_asset_name(info.asset_name, info.version))
    temp_path = target_path + ".part"

    request_kwargs = _request_kwargs(settings)
    request_kwargs["timeout"] = (10, 120)
    with requests.get(info.asset_url, headers={"User-Agent": _headers()["User-Agent"]}, stream=True, **request_kwargs) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or info.asset_size or 0)
        received = 0
        sha256 = hashlib.sha256()
        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if not chunk:
                    continue
                f.write(chunk)
                sha256.update(chunk)
                received += len(chunk)
                if progress_callback:
                    progress_callback(received, total)

    expected = _expected_sha256(info.asset_digest)
    actual = sha256.hexdigest().lower()
    if expected and actual != expected:
        try:
            os.remove(temp_path)
        except Exception:
            pass
        raise RuntimeError("Downloaded installer failed SHA-256 verification.")

    os.replace(temp_path, target_path)
    return target_path


def _ps_quote(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _default_app_exe():
    if platform.system() == "Windows":
        candidate = os.path.join(SMARTI_RUNTIME.install_dir, "SmartiAI.exe")
        if os.path.exists(candidate) or not getattr(sys, "frozen", False):
            return candidate
        return sys.executable
    else:
        exe = sys.executable
        if getattr(sys, "frozen", False) and platform.system() == "Darwin":
            if ".app/Contents/MacOS/" in exe:
                app_dir = exe.split(".app/Contents/MacOS/")[0] + ".app"
                if os.path.exists(app_dir):
                    return app_dir
        return exe


def launch_update_installer(installer_path, app_pid=None, app_exe=None):
    installer_path = os.path.abspath(installer_path)
    if not os.path.exists(installer_path):
        raise FileNotFoundError(installer_path)

    app_exe = os.path.abspath(app_exe or _default_app_exe())
    app_pid = int(app_pid or os.getpid())
    script_dir = os.path.join(USER_DATA_DIR, "updates")
    os.makedirs(script_dir, exist_ok=True)

    if platform.system() == "Windows":
        script_path = os.path.join(script_dir, f"apply_update_{app_pid}.ps1")
        log_path = os.path.join(script_dir, "last_update.log")
        script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$installer = {_ps_quote(installer_path)}
$appPid = {app_pid}
$appExe = {_ps_quote(app_exe)}
$logPath = {_ps_quote(log_path)}
function Write-UpdateLog([string]$message) {{
    $stamp = (Get-Date).ToUniversalTime().ToString('o')
    Add-Content -LiteralPath $logPath -Value "$stamp $message" -Encoding UTF8
}}
Write-UpdateLog "Waiting for SmartiAI to exit."
if ($appPid -gt 0) {{
    $proc = Get-Process -Id $appPid -ErrorAction SilentlyContinue
    if ($proc) {{ Wait-Process -Id $appPid -Timeout 25 -ErrorAction SilentlyContinue }}
    $proc = Get-Process -Id $appPid -ErrorAction SilentlyContinue
    if ($proc) {{
        Write-UpdateLog "Forcing old SmartiAI process $appPid to stop."
        Stop-Process -Id $appPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }}
}}
Get-Process -Name 'SmartiAI' -ErrorAction SilentlyContinue | Where-Object {{ $_.Id -ne $PID }} | ForEach-Object {{
    Write-UpdateLog "Stopping extra SmartiAI process $($_.Id)."
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}}
Write-UpdateLog "Starting installer: $installer"
$args = @('/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', '/MERGETASKS=!desktopicon')
$setup = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
Write-UpdateLog "Installer exit code: $($setup.ExitCode)"
function Add-LaunchCandidate([System.Collections.Generic.List[string]]$items, [string]$path) {{
    if ([string]::IsNullOrWhiteSpace($path)) {{ return }}
    if (-not $items.Contains($path)) {{ $items.Add($path) | Out-Null }}
}}
function Resolve-SmartiExe {{
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($key in @(
        'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{2F7748B6-3D46-4E9C-B187-0F5C2E9F38E1}}_is1',
        'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{2F7748B6-3D46-4E9C-B187-0F5C2E9F38E1}}_is1',
        'HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{{2F7748B6-3D46-4E9C-B187-0F5C2E9F38E1}}_is1'
    )) {{
        $entry = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
        if ($entry -and $entry.InstallLocation) {{
            Add-LaunchCandidate $candidates (Join-Path $entry.InstallLocation 'SmartiAI.exe')
        }}
    }}
    Add-LaunchCandidate $candidates $appExe
    if ($env:LOCALAPPDATA) {{
        Add-LaunchCandidate $candidates (Join-Path $env:LOCALAPPDATA 'SmartiAI\\SmartiAI.exe')
        Add-LaunchCandidate $candidates (Join-Path $env:LOCALAPPDATA 'Programs\\SmartiAI\\SmartiAI.exe')
    }}
    foreach ($candidate in $candidates) {{
        if (Test-Path -LiteralPath $candidate) {{ return $candidate }}
    }}
    return $appExe
}}
if ($null -eq $setup.ExitCode -or $setup.ExitCode -eq 0 -or $setup.ExitCode -eq 3010) {{
    $resolvedAppExe = Resolve-SmartiExe
    if (Test-Path -LiteralPath $resolvedAppExe) {{
        Write-UpdateLog "Relaunching SmartiAI: $resolvedAppExe"
        Start-Process -FilePath $resolvedAppExe -WorkingDirectory (Split-Path -Parent $resolvedAppExe)
    }} else {{
        Write-UpdateLog "SmartiAI relaunch skipped; executable was not found. Last candidate: $resolvedAppExe"
    }}
}}
"""
        with open(script_path, "w", encoding="utf-8-sig") as f:
            f.write(script.lstrip())

        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
            cwd=script_dir,
            creationflags=WIN_CREATE_NO_WINDOW,
        )
        return script_path
    else:
        script_path = os.path.join(script_dir, f"apply_update_{app_pid}.sh")
        log_path = os.path.join(script_dir, "last_update.log")
        script = f"""#!/bin/bash
log_file='{log_path}'
echo "Starting update process..." > "$log_file"
APP_PID={app_pid}
INSTALLER='{installer_path}'
APP_EXE='{app_exe}'

if [ "$APP_PID" -gt 0 ]; then
    for i in {{1..25}}; do
        if ! kill -0 "$APP_PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    kill -9 "$APP_PID" 2>/dev/null
fi

if [[ "$INSTALLER" == *.zip ]]; then
    echo "Extracting ZIP update..." >> "$log_file"
    tmp_dir="/tmp/smarti_update"
    rm -rf "$tmp_dir"
    mkdir -p "$tmp_dir"
    unzip -o "$INSTALLER" -d "$tmp_dir" >> "$log_file" 2>&1
    new_app=$(find "$tmp_dir" -name "SmartiAI.app" -type d | head -n 1)
    if [ -n "$new_app" ]; then
        dest_dir=$(dirname "$APP_EXE")
        echo "Copying $new_app to $dest_dir..." >> "$log_file"
        rm -rf "$APP_EXE"
        cp -R "$new_app" "$dest_dir" >> "$log_file" 2>&1
        echo "Update applied successfully." >> "$log_file"
        open "$APP_EXE"
    else
        echo "ERROR: SmartiAI.app not found in zip." >> "$log_file"
    fi
elif [[ "$INSTALLER" == *.dmg ]]; then
    echo "Mounting DMG update..." >> "$log_file"
    mount_point=$(hdiutil attach "$INSTALLER" -nobrowse | grep -o '/Volumes/.*' | head -n 1)
    if [ -n "$mount_point" ]; then
        new_app=$(find "$mount_point" -name "SmartiAI.app" -type d | head -n 1)
        if [ -n "$new_app" ]; then
            dest_dir=$(dirname "$APP_EXE")
            echo "Copying $new_app to $dest_dir..." >> "$log_file"
            rm -rf "$APP_EXE"
            cp -R "$new_app" "$dest_dir" >> "$log_file" 2>&1
            echo "Update applied successfully." >> "$log_file"
            hdiutil detach "$mount_point"
            open "$APP_EXE"
        else
            echo "ERROR: SmartiAI.app not found in DMG." >> "$log_file"
            hdiutil detach "$mount_point"
        fi
    else
        echo "ERROR: Failed to mount DMG." >> "$log_file"
    fi
fi
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script.lstrip())
        os.chmod(script_path, 0o755)
        subprocess.Popen(
            ["/bin/bash", script_path],
            cwd=script_dir,
        )
        return script_path


def human_size(num_bytes):
    try:
        value = float(num_bytes or 0)
    except Exception:
        value = 0
    units = ["B", "KB", "MB", "GB"]
    unit = 0
    while value >= 1024 and unit < len(units) - 1:
        value /= 1024
        unit += 1
    return f"{value:.1f} {units[unit]}" if unit else f"{int(value)} {units[unit]}"


class UpdateCheckWorker(QThread):
    found = pyqtSignal(object)
    no_update = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = dict(settings or {})

    def run(self):
        try:
            info = check_for_updates(self.settings)
            if info:
                self.found.emit(info)
            else:
                self.no_update.emit("אין עדכון חדש.")
        except Exception as exc:
            logging.warning("Update check failed: %s", exc)
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    downloaded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, update_info, settings=None, parent=None):
        super().__init__(parent)
        self.update_info = UpdateInfo.from_dict(update_info)
        self.settings = dict(settings or {})

    def run(self):
        try:
            path = download_update(
                self.update_info,
                settings=self.settings,
                progress_callback=lambda received, total: self.progress.emit(int(received), int(total)),
            )
            self.downloaded.emit(path)
        except Exception as exc:
            logging.warning("Update download failed: %s", exc)
            self.failed.emit(str(exc))
