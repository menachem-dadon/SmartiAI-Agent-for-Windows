"""Hash executable source, referenced assets and build recipes without importing Smarti."""
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parents[1]


def source_inputs(root: Path = ROOT) -> dict[str, str]:
    files = []
    for base in ("desktop/src", "desktop/public", "desktop/src-tauri/src", "desktop/src-tauri/capabilities", "smarti", "packaging"):
        files.extend(p for p in (root / base).rglob("*") if p.is_file()
                     and p.suffix in {".ts", ".tsx", ".css", ".json", ".rs", ".py", ".spec", ".svg", ".png", ".gif"}
                     and ".test." not in p.name and "__pycache__" not in p.parts)
    for source in (root / "desktop/src").rglob("*"):
        if source.is_file() and source.suffix in {".ts", ".tsx", ".css"}:
            for name in re.findall(r'''["'](\.\./\.\./assets/[^"']+)["']''', source.read_text(encoding="utf-8")):
                asset = (source.parent / name).resolve()
                if asset.is_relative_to((root / "assets").resolve()) and asset.is_file():
                    files.append(asset)
    files.extend(root / p for p in (
        "desktop/index.html", "desktop/package.json", "desktop/package-lock.json", "desktop/vite.config.ts",
        "desktop/src-tauri/Cargo.toml", "desktop/src-tauri/Cargo.lock", "desktop/src-tauri/tauri.conf.json",
        "desktop/src-tauri/build.rs", "requirements-core.txt", "requirements-build.txt", "smarti_core_service.py",
        "scripts/build_tauri_release.ps1", "scripts/prepare_runtime.ps1", "scripts/build_and_package.ps1",
        "scripts/prepare_tauri_package.py", "scripts/tauri_source_manifest.py",
    ) if (root / p).is_file())
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(files), key=lambda item: item.relative_to(root).as_posix())}


def source_fingerprint(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for name, content_hash in source_inputs(root).items():
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(content_hash))
    return digest.hexdigest()


if __name__ == "__main__":
    print(source_fingerprint())
