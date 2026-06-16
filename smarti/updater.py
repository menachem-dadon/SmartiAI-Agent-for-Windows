"""GitHub release update checks and installer handoff for SmartiAI."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
import os
import re
import subprocess
import sys
try:
    import winreg
except Exception:
    winreg = None

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
SETUP_ASSET_RE = re.compile(r"(?i)\bsetup\b.*\.exe$")
PORTABLE_ASSET_RE = re.compile(r"(?i)(portable|win[-_ ]?x64).*\.zip$")
INNO_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{2F7748B6-3D46-4E9C-B187-0F5C2E9F38E1}_is1"


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
    asset_kind: str = "installer"
    installation_kind: str = "installer"
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
            asset_kind=str(data.get("asset_kind") or "installer"),
            installation_kind=str(data.get("installation_kind") or "installer"),
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


def _norm_dir(path):
    try:
        return os.path.normcase(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path or ""))))).rstrip("\\/")
    except Exception:
        return os.path.normcase(str(path or "")).rstrip("\\/")


def _installer_install_locations():
    if os.name != "nt" or winreg is None:
        return []
    locations = []
    roots = [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]
    views = [0]
    for flag_name in ("KEY_WOW64_64KEY", "KEY_WOW64_32KEY"):
        flag = getattr(winreg, flag_name, 0)
        if flag:
            views.append(flag)
    for root in roots:
        for view in views:
            try:
                with winreg.OpenKey(root, INNO_UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                    install_location = winreg.QueryValueEx(key, "InstallLocation")[0]
                    if install_location:
                        locations.append(str(install_location))
            except Exception:
                continue
    return locations


def detect_installation_kind():
    """Return source, installer, or portable for update asset selection."""
    if not getattr(SMARTI_RUNTIME, "is_frozen", False):
        return "source"
    install_dir = _norm_dir(SMARTI_RUNTIME.install_dir)
    for location in _installer_install_locations():
        if _norm_dir(location) == install_dir:
            return "installer"
    local_appdata = os.environ.get("LOCALAPPDATA") or ""
    installer_like_dirs = [
        os.path.join(local_appdata, "SmartiAI"),
        os.path.join(local_appdata, "Programs", "SmartiAI"),
    ] if local_appdata else []
    if any(_norm_dir(path) == install_dir for path in installer_like_dirs):
        return "installer"
    if os.path.exists(os.path.join(SMARTI_RUNTIME.install_dir, "release_manifest.json")):
        return "portable"
    return "portable"


def _asset_kind(asset):
    name = str((asset or {}).get("name") or "").lower()
    if name.endswith(".zip"):
        return "portable"
    if name.endswith(".exe"):
        return "installer"
    return ""


def _select_update_asset(release, preferred_kind="installer"):
    assets = release.get("assets") or []
    if not isinstance(assets, list):
        return {}
    setup_assets = []
    exe_assets = []
    portable_assets = []
    zip_assets = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        lower = name.lower()
        if lower.endswith(".exe"):
            exe_assets.append(asset)
            if SETUP_ASSET_RE.search(name) or "setup" in lower:
                setup_assets.append(asset)
        elif lower.endswith(".zip"):
            zip_assets.append(asset)
            if PORTABLE_ASSET_RE.search(name) or "portable" in lower:
                portable_assets.append(asset)
    if preferred_kind == "portable":
        return (portable_assets or zip_assets or [{}])[0]
    return (setup_assets or exe_assets or [{}])[0]


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

    installation_kind = detect_installation_kind()
    preferred_asset_kind = "portable" if installation_kind == "portable" else "installer"
    asset = _select_update_asset(release, preferred_asset_kind)
    asset_kind = _asset_kind(asset) or preferred_asset_kind
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
        asset_kind=asset_kind,
        installation_kind=installation_kind,
        prerelease=bool(release.get("prerelease")),
    )


def _safe_asset_name(name, version):
    name = os.path.basename(str(name or "").strip())
    if not name:
        name = f"SmartiAI-Agent-for-Windows-{version}-Setup.exe"
    return re.sub(r"[^A-Za-z0-9_.() -]+", "-", name)[:180]


def _expected_sha256(digest):
    value = str(digest or "").strip()
    match = re.match(r"(?i)^sha256:([a-f0-9]{64})$", value)
    return match.group(1).lower() if match else ""


def download_update(update_info, settings=None, progress_callback=None):
    info = UpdateInfo.from_dict(update_info)
    if not info.asset_url:
        expected = "portable ZIP" if info.asset_kind == "portable" else "Windows Setup EXE"
        raise RuntimeError(f"No {expected} was attached to the GitHub release.")

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
        raise RuntimeError("Downloaded update package failed SHA-256 verification.")

    os.replace(temp_path, target_path)
    return target_path


def _ps_quote(value):
    return "'" + str(value or "").replace("'", "''") + "'"


def _default_app_exe():
    candidate = os.path.join(SMARTI_RUNTIME.install_dir, "SmartiAI.exe")
    if os.path.exists(candidate) or not getattr(sys, "frozen", False):
        return candidate
    return sys.executable


def launch_portable_update(archive_path, app_pid=None, app_exe=None):
    archive_path = os.path.abspath(archive_path)
    if not os.path.exists(archive_path):
        raise FileNotFoundError(archive_path)

    app_exe = os.path.abspath(app_exe or _default_app_exe())
    app_pid = int(app_pid or os.getpid())
    script_dir = os.path.join(USER_DATA_DIR, "updates")
    os.makedirs(script_dir, exist_ok=True)
    script_path = os.path.join(script_dir, f"apply_portable_update_{app_pid}.ps1")
    log_path = os.path.join(script_dir, "last_update.log")

    script = f"""
$ErrorActionPreference = 'Stop'
$archive = {_ps_quote(archive_path)}
$appPid = {app_pid}
$appExe = {_ps_quote(app_exe)}
$scriptDir = {_ps_quote(script_dir)}
$logPath = {_ps_quote(log_path)}
$extractRoot = Join-Path $scriptDir {_ps_quote(f"portable_extract_{app_pid}")}
function Write-UpdateLog([string]$message) {{
    $stamp = (Get-Date).ToUniversalTime().ToString('o')
    Add-Content -LiteralPath $logPath -Value "$stamp $message" -Encoding UTF8
}}
try {{
    Write-UpdateLog "Waiting for SmartiAI to exit before portable update."
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
    if (Test-Path -LiteralPath $extractRoot) {{ Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue }}
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    Write-UpdateLog "Extracting portable package: $archive"
    Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force

    $sourceRoot = $null
    if (Test-Path -LiteralPath (Join-Path $extractRoot 'SmartiAI.exe')) {{
        $sourceRoot = $extractRoot
    }} else {{
        $manifest = Get-ChildItem -Path $extractRoot -Filter 'release_manifest.json' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($manifest) {{ $sourceRoot = Split-Path -Parent $manifest.FullName }}
        if (-not $sourceRoot) {{
            $payloadExe = Get-ChildItem -Path $extractRoot -Filter 'SmartiAI.exe' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($payloadExe) {{ $sourceRoot = Split-Path -Parent $payloadExe.FullName }}
        }}
    }}
    if (-not $sourceRoot) {{ throw "Portable update payload does not contain SmartiAI.exe." }}
    $payloadExe = Join-Path $sourceRoot 'SmartiAI.exe'
    if (-not (Test-Path -LiteralPath $payloadExe)) {{ throw "Portable update payload is missing SmartiAI.exe." }}

    $appDir = Split-Path -Parent $appExe
    if (-not (Test-Path -LiteralPath $appDir)) {{ New-Item -ItemType Directory -Force -Path $appDir | Out-Null }}
    Write-UpdateLog "Copying portable update from $sourceRoot to $appDir"
    $robocopy = Join-Path $env:SystemRoot 'System32\\robocopy.exe'
    if (Test-Path -LiteralPath $robocopy) {{
        & $robocopy $sourceRoot $appDir /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP
        $copyExit = $LASTEXITCODE
        Write-UpdateLog "Robocopy exit code: $copyExit"
        if ($copyExit -ge 8) {{ throw "Portable file copy failed with robocopy exit code $copyExit." }}
    }} else {{
        Copy-Item -Path (Join-Path $sourceRoot '*') -Destination $appDir -Recurse -Force
    }}
    Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $appExe) {{
        Write-UpdateLog "Relaunching SmartiAI portable: $appExe"
        Start-Process -FilePath $appExe -WorkingDirectory $appDir
    }} else {{
        Write-UpdateLog "Portable relaunch skipped; executable was not found: $appExe"
    }}
}} catch {{
    Write-UpdateLog "Portable update failed: $($_.Exception.Message)"
    try {{
        $appDir = Split-Path -Parent $appExe
        if (Test-Path -LiteralPath $appExe) {{ Start-Process -FilePath $appExe -WorkingDirectory $appDir }}
    }} catch {{}}
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


def launch_update_installer(installer_path, app_pid=None, app_exe=None):
    installer_path = os.path.abspath(installer_path)
    if not os.path.exists(installer_path):
        raise FileNotFoundError(installer_path)
    if installer_path.lower().endswith(".zip"):
        return launch_portable_update(installer_path, app_pid=app_pid, app_exe=app_exe)

    app_exe = os.path.abspath(app_exe or _default_app_exe())
    app_pid = int(app_pid or os.getpid())
    script_dir = os.path.join(USER_DATA_DIR, "updates")
    os.makedirs(script_dir, exist_ok=True)
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
