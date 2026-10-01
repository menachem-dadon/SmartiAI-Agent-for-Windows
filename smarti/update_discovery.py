"""Qt-free GitHub release discovery shared by the desktop and legacy updater."""
import re
from urllib.parse import quote

import requests

from .common import APP_VERSION, SMARTI_APP_DISPLAY_NAME, USER_DATA_DIR, ssl_request_kwargs


GITHUB_OWNER = "menachem-dadon"
GITHUB_REPO = "SmartiAI-Agent-for-Windows"
GITHUB_API_RELEASE_LATEST = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"


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


def _request_kwargs(settings=None, url=GITHUB_API_RELEASE_LATEST):
    # Transport follows the user's trust settings; installation verification
    # remains the responsibility of the updater that downloads the artifact.
    kwargs = ssl_request_kwargs(settings or {}, url=url, allow_legacy=True, data_dir=USER_DATA_DIR)
    kwargs["timeout"] = 25
    return kwargs


def fetch_latest_release(settings=None):
    response = requests.get(GITHUB_API_RELEASE_LATEST, headers=_headers(), **_request_kwargs(settings))
    response.raise_for_status()
    release = response.json()
    if not isinstance(release, dict):
        raise RuntimeError("GitHub returned an unexpected release payload.")
    return release


def discover_update(settings=None, current_version=APP_VERSION):
    release = fetch_latest_release(settings)
    tag = str(release.get("tag_name") or "")
    if not re.fullmatch(r"[vV]?\d+(?:\.\d+){1,3}", tag):
        raise RuntimeError("GitHub returned an unexpected release payload.")
    version = re.sub(r"^[vV]", "", tag)
    if release.get("draft") or release.get("prerelease") or not is_newer_version(version, current_version):
        return None
    return {
        "version": version,
        "body": str(release.get("body") or ""),
        "releaseUrl": f"{GITHUB_RELEASES_URL}/tag/{quote(tag, safe='')}",
    }
