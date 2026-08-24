"""Verify the durable Point 16C feature/parity acceptance ledgers."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FEATURE_MATRIX = ROOT / "docs" / "tauri_migration_baseline.md"
PARITY_MATRIX = ROOT / "docs" / "tauri_ui_source_parity.md"
ACCEPTANCE = ROOT / "docs" / "tauri_point16c_acceptance.md"
SOURCE_AUDIT = ROOT / "docs" / "tauri_point16c_source_audit.md"

FEATURE_ROW = re.compile(
    r"^\|\s*([A-Z]{3}-\d{3})\s*\|.*\|\s*([^|]+?)\s*\|\s*$",
    re.MULTILINE,
)
ALLOWED_FINAL_STATUSES = {
    "IMPLEMENTED",
    "IMPLEMENTED + APPROVED TAURI ARCHITECTURE",
    "USER-APPROVED CURRENT-MACHINE SCOPE",
}


def _current_rows(text: str, start: str, end: str) -> list[str]:
    section = text.split(start, 1)[1].split(end, 1)[0]
    return [
        line
        for line in section.splitlines()
        if line.startswith("|")
        and not line.startswith("|---")
        and "Control/state" not in line
    ]


def main() -> int:
    audit_text = SOURCE_AUDIT.read_text(encoding="utf-8")
    open_audit_rows = [
        line for line in audit_text.splitlines()
        if line.startswith("|") and ("`AUDIT OPEN`" in line or "`BLOCKING GAP`" in line)
    ]
    if open_audit_rows:
        raise SystemExit(
            "Point 16C source parity remains open: "
            f"{len(open_audit_rows)} audit/blocking rows in {SOURCE_AUDIT.name}"
        )
    feature_text = FEATURE_MATRIX.read_text(encoding="utf-8")
    rows = FEATURE_ROW.findall(feature_text)
    feature_ids = [feature_id for feature_id, _status in rows]
    if len(rows) != 97 or len(set(feature_ids)) != 97:
        raise SystemExit(
            f"Expected 97 unique stable feature IDs; found {len(rows)} rows and "
            f"{len(set(feature_ids))} unique IDs"
        )
    unresolved = {
        feature_id: status.strip()
        for feature_id, status in rows
        if status.strip() not in ALLOWED_FINAL_STATUSES
    }
    if unresolved:
        raise SystemExit(f"Unresolved feature statuses: {unresolved}")

    parity_text = PARITY_MATRIX.read_text(encoding="utf-8")
    daily_rows = _current_rows(
        parity_text,
        "## Point 16A current daily control/state/action mapping",
        "### Point 16A evidence boundary",
    )
    management_rows = _current_rows(
        parity_text,
        "## Point 16B current Settings and management control/state/action mapping",
        "Point 16B evidence boundaries:",
    )
    current_rows = daily_rows + management_rows
    if len(daily_rows) != 53 or len(management_rows) != 13:
        raise SystemExit(
            "Expected 53 daily and 13 management granular parity rows; found "
            f"{len(daily_rows)} and {len(management_rows)}"
        )
    unmatched = [line for line in current_rows if "CURRENT MATCHED" not in line]
    if unmatched:
        raise SystemExit(f"Current parity rows without a resolution: {unmatched}")

    acceptance_text = ACCEPTANCE.read_text(encoding="utf-8")
    missing_from_acceptance = [
        feature_id for feature_id in feature_ids if feature_id not in acceptance_text
    ]
    if missing_from_acceptance:
        raise SystemExit(
            "Point 16C acceptance evidence omits IDs: "
            + ", ".join(missing_from_acceptance)
        )

    for relative in (
        "smarti_core.pyw",
        "smarti/app.py",
        "desktop/src/App.tsx",
        "desktop/src-tauri/src/lib.rs",
        "docs/architecture.md",
        "desktop/README.md",
        "packaging/README.md",
    ):
        if not (ROOT / relative).is_file():
            raise SystemExit(f"Required transition/source file is missing: {relative}")

    release_evidence = (ROOT / "docs" / "tauri_point16_release_evidence.md").read_text(
        encoding="utf-8"
    )
    for required in ("NotSigned", "current-machine", "packageSmoke"):
        if required not in release_evidence:
            raise SystemExit(f"Release evidence omits required boundary: {required}")

    approved = sum(
        status.strip() == "IMPLEMENTED + APPROVED TAURI ARCHITECTURE"
        for _feature_id, status in rows
    )
    scoped = sum(
        status.strip() == "USER-APPROVED CURRENT-MACHINE SCOPE"
        for _feature_id, status in rows
    )
    print(
        "Point 16C ledgers OK: "
        f"97 features (approved architecture={approved}, scoped={scoped}); "
        f"{len(current_rows)} granular current parity rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
