"""Freeze a working tree and synchronize a package version in its isolated copy only."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid

_spec = importlib.util.spec_from_file_location("smarti_tauri_manifest", Path(__file__).with_name("tauri_source_manifest.py"))
_manifest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_manifest)
source_fingerprint = _manifest.source_fingerprint

ROOT = Path(__file__).resolve().parents[1]
UTF8 = "utf-8"
VERSION_FILES = ("smarti/common.py", "desktop/package.json", "desktop/package-lock.json",
                 "desktop/src-tauri/tauri.conf.json", "desktop/src-tauri/Cargo.toml", "desktop/src-tauri/Cargo.lock")


def normalize_version(value: str) -> str:
    value = value.strip().removeprefix("V").removeprefix("v")
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("Version must be major.minor.patch, e.g. 0.88.0; use Label for a release name")
    if any(int(n) > 65535 for n in value.split(".")):
        raise ValueError("Windows version components must not exceed 65535")
    return value


def validate_label(value: str) -> str:
    if value and (value != value.strip() or value.endswith(".") or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)):
        raise ValueError("Label must be a valid single Windows filename component")
    if len(value) > 64:
        raise ValueError("Label must be at most 64 characters")
    return value


def text(path: Path) -> str:
    return path.read_bytes().decode(UTF8)


def replace_once(path: Path, pattern: str, version: str) -> None:
    original = text(path)
    matches = list(re.finditer(pattern, original, re.M))
    if len(matches) != 1:
        raise ValueError(f"Expected one application version in {path}")
    match = matches[0]
    changed = original[:match.start(2)] + version + original[match.end(2):]
    if changed != original:
        path.write_bytes(changed.encode(UTF8))


def set_json_version(path: Path, version: str, lock: bool = False) -> None:
    original = text(path)
    data = json.loads(original)
    changed = data.get("version") != version
    data["version"] = version
    if lock:
        app = data["packages"][""]
        changed |= app.get("version") != version
        app["version"] = version
    if changed:
        output = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if "\r\n" in original:
            output = output.replace("\n", "\r\n")
        path.write_bytes(output.encode(UTF8))


def synchronize_version(root: Path, version: str) -> None:
    replace_once(root / "smarti/common.py", r'^(APP_VERSION\s*=\s*["\'])([^"\']+)(["\'])', "V" + version)
    set_json_version(root / "desktop/package.json", version)
    set_json_version(root / "desktop/package-lock.json", version, lock=True)
    set_json_version(root / "desktop/src-tauri/tauri.conf.json", version)
    replace_once(root / "desktop/src-tauri/Cargo.toml", r'(\[package\][\s\S]*?^version\s*=\s*")([^"]+)(")', version)
    replace_once(root / "desktop/src-tauri/Cargo.lock", r'(\[\[package\]\]\r?\nname = "smarti-desktop"\r?\nversion = ")([^"]+)(")', version)


def prepare(root: Path, work_root: Path, output_directory: Path, version: str = "", label: str = "") -> Path:
    root, work_root, output_directory = root.resolve(), work_root.resolve(), output_directory.resolve()
    label = validate_label(label)
    declared = json.loads(text(root / "desktop/package.json"))["version"]
    version = normalize_version(version or declared)
    if not str(work_root).isascii() or len(str(work_root)) > 64:
        raise ValueError("WorkRoot must be a short ASCII path, e.g. C:\\SmartiAI-builds")
    if work_root.is_relative_to(root):
        raise ValueError("WorkRoot must be outside the repository")
    raw = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root)
    names = sorted(set(raw.decode(UTF8).split("\0")) - {""})
    before = source_fingerprint(root)
    run = uuid.uuid4().hex[:12]
    work = work_root / ("build-" + run)
    work.mkdir(parents=True, exist_ok=False)
    source = work / "source"
    source.mkdir()
    for name in names:
        origin, destination = root / name, (source / name).resolve()
        if not destination.is_relative_to(source.resolve()):
            raise ValueError("Source path escapes the snapshot")
        if origin.is_file():
            if not origin.resolve().is_relative_to(root):
                raise ValueError("External file links are not part of the isolated source snapshot")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin, destination)
    if source_fingerprint(source) != before or source_fingerprint(root) != before:
        raise ValueError("Working source changed while preparing the snapshot; start another build")
    # A requested version changes only the frozen copy. Missing/ambiguous fields abort.
    synchronize_version(source, version)
    package_source = source_fingerprint(source)
    name = version + ("-" + label if label else "") + "-" + run
    result = {
        "schema_version": 1, "version": version, "label": label,
        "source": str(source), "work": str(work), "data": str(work / "private-data"),
        "output": str(output_directory / name), "source_sha256": package_source,
        "working_tree_source_sha256": before,
        "version_files_changed": [p for p in VERSION_FILES if (root / p).read_bytes() != (source / p).read_bytes()],
        "scope": "Frozen working source; version overrides only in snapshot. No build, installer execution or publication implied.",
    }
    path = work / "source-manifest.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding=UTF8)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--version", default="")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    print(prepare(args.root, args.work_root, args.output_directory, args.version, args.label))


if __name__ == "__main__":
    main()
