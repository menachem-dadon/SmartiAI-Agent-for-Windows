"""Validate redesign acceptance without rewriting historical parity statuses."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEVELS = {"source", "browser", "windows", "package"}
STATUSES = {"OPEN", "PASS", "FAIL", "NEEDS_USER", "OUT_OF_SCOPE"}


_spec = importlib.util.spec_from_file_location("tauri_source_manifest", ROOT / "scripts/tauri_source_manifest.py")
_manifest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_manifest)
source_inputs, source_fingerprint = _manifest.source_inputs, _manifest.source_fingerprint


def validate(data: dict, root: Path = ROOT, final: bool = False) -> list[str]:
    problems: list[str] = []
    stable = set(re.findall(r"^\|\s*([A-Z]{3}-\d{3})\s*\|", (root / "docs/tauri_migration_baseline.md").read_text(encoding="utf-8"), re.M))
    rows = data.get("capabilities", [])
    ids = [row.get("id") for row in rows]
    if len(stable) != 97 or len(ids) != len(set(ids)) or not stable.issubset(ids):
        problems.append("97 stable unique capability IDs must all be retained")
    if not {"UX6-LOAD", "UX6-A11Y", "UX6-DPI", "UX6-PERF", "UX6-OWNERS", "UX6-MOTION"}.issubset(ids):
        problems.append("Redesign acceptance requirements are missing")
    if data.get("design_decision") != "D58":
        problems.append("D58 must be retained")
    evidence = data.get("evidence", {})
    current_source = source_fingerprint(root)
    if data.get("stage_status") == "COMPLETE":
        # Closing the accepted source/UI project is distinct from the strict
        # all-level product/release gate below. Preserve every unresolved level.
        closure = data.get("central_acceptance", {})
        artifact = (root / closure.get("artifact", "")).resolve()
        if not artifact.is_relative_to(root.resolve()) or not artifact.is_file():
            problems.append("Source/UI completion requires a central acceptance receipt")
        elif hashlib.sha256(artifact.read_bytes()).hexdigest() != closure.get("sha256"):
            problems.append("Central acceptance receipt hash mismatch")
        else:
            receipt = json.loads(artifact.read_text(encoding="utf-8"))
            pending = sum(result.get("status") != "PASS" for row in rows for result in row.get("results", {}).values())
            if (receipt.get("scope") != "source-and-accepted-ui" or receipt.get("source_sha256") != current_source
                    or receipt.get("user_authorized_closure") is not True or receipt.get("result") != "PASS"
                    or receipt.get("pending_evidence_levels") != pending or receipt.get("release_accepted") is not False):
                problems.append("Central receipt must bind scoped completion to current source and preserve remaining evidence gaps")
    for row in rows:
        if not row.get("owner") or not row.get("action") or not row.get("authority"):
            problems.append(f"{row.get('id')}: action, authority and owner required")
        if not row.get("required_levels") or not set(row["required_levels"]).issubset(LEVELS):
            problems.append(f"{row.get('id')}: explicit required evidence levels required")
        for level in row.get("required_levels", []):
            result = row.get("results", {}).get(level, {})
            status = result.get("status")
            if status not in STATUSES:
                problems.append(f"{row['id']}/{level}: invalid status")
            if status != "PASS" and not result.get("gap"):
                problems.append(f"{row['id']}/{level}: unresolved scope needs a reason")
            if final and status != "PASS":
                problems.append(f"{row['id']}/{level}: {status} blocks final acceptance")
            if status == "PASS":
                refs = result.get("evidence", [])
                if not refs:
                    problems.append(f"{row['id']}/{level}: PASS without evidence")
                for ref in refs:
                    item = evidence.get(ref, {})
                    if item.get("level") != level or item.get("result") != "PASS" or not item.get("scope") or not item.get("source_sha256"):
                        problems.append(f"{row['id']}/{level}: invalid or cross-level evidence {ref}")
                    if item.get("source_sha256") != current_source:
                        problems.append(f"{ref}: evidence belongs to different source")
                    if row["id"] not in item.get("capabilities", []):
                        problems.append(f"{ref}: does not cover capability {row['id']}")
                    artifact = (root / item.get("artifact", "")).resolve()
                    if not artifact.is_relative_to(root.resolve()) or not artifact.is_file():
                        problems.append(f"{ref}: evidence artifact missing or outside checkout")
                    elif hashlib.sha256(artifact.read_bytes()).hexdigest() != item.get("sha256"):
                        problems.append(f"{ref}: evidence hash mismatch")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", help="Require all evidence levels to pass; never closes UX-6")
    parser.add_argument("--fingerprint", action="store_true", help="Print current executable source/config/assets identity")
    parser.add_argument("--map", type=Path, default=ROOT / "docs/ux6_acceptance.json")
    args = parser.parse_args()
    if args.fingerprint:
        print(source_fingerprint())
        return 0
    data = json.loads(args.map.read_text(encoding="utf-8"))
    errors = validate(data, final=args.final)
    if errors:
        print("\n".join(errors))
        return 1
    pending = sum(r["status"] != "PASS" for row in data["capabilities"] for r in row["results"].values())
    stage = "source/UI complete; full product/release gate separate" if data.get("stage_status") == "COMPLETE" else "central acceptance pending"
    print(f"UX-6 map valid: {len(data['capabilities'])} capabilities/requirements; {pending} evidence-level gaps; {stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
