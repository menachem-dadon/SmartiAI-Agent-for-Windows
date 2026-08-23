"""Safe Point 6 profile-import feasibility report (counts only, no secrets/URLs)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from smarti.browser_profile import discover_browser_profiles, read_bookmarks, read_cookies, read_history


def profile_counts(source, profile_alias):
    errors = []
    try:
        history = len(read_history(source))
    except Exception as exc:
        history = 0
        errors.append(f"history:{type(exc).__name__}")
    try:
        bookmarks = len(read_bookmarks(source))
    except Exception as exc:
        bookmarks = 0
        errors.append(f"bookmarks:{type(exc).__name__}")
    try:
        cookies, cookie_stats = read_cookies(source)
        compatible_cookies = len(cookies)
    except Exception as exc:
        compatible_cookies = 0
        cookie_stats = {"read": 0, "skipped_encrypted": 0}
        errors.append(f"cookies:{type(exc).__name__}")
    return {
        "browser": source.browser_name,
        "profile": profile_alias,
        "history_readable": history,
        "bookmarks_readable": bookmarks,
        "cookies_compatible_current_user": compatible_cookies,
        "cookies_examined": int(cookie_stats.get("read") or 0),
        "cookies_skipped_encrypted": int(cookie_stats.get("skipped_encrypted") or 0),
        "errors": errors,
    }


def build_report(local_app_data=None):
    sources = discover_browser_profiles(local_app_data)
    ordinals = {}
    rows = []
    for source in sources:
        ordinals[source.browser_id] = ordinals.get(source.browser_id, 0) + 1
        rows.append(profile_counts(source, f"profile-{ordinals[source.browser_id]}"))
    detected = {row["browser"] for row in rows}
    expected = ["Google Chrome", "Microsoft Edge", "Brave", "Chromium", "Vivaldi"]
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "safe_copy_read": True,
        "source_profiles_modified": False,
        "passwords_read": False,
        "sensitive_urls_or_cookie_values_reported": False,
        "profiles": rows,
        "not_detected": [name for name in expected if name not in detected],
        "cookie_note": "v20/App-Bound or otherwise unavailable cookies are skipped; Smarti does not bypass browser encryption.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-app-data")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.local_app_data)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
