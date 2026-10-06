"""Snapshot current source into a separate local package checkout; no install."""
from pathlib import Path
import argparse
import importlib.util
import json
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / ".codex-local/ux-6"
spec = importlib.util.spec_from_file_location("ux6_checker", ROOT / "scripts/verify_ux6_acceptance.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--short-source", action="store_true", help="Use a fresh short ASCII checkout for NSIS")
args = parser.parse_args()
work = Path("C:/") / ("SmartiAI-ux6-build-" + uuid.uuid4().hex)
target = work / "source" if args.short_source else QA / ("package-source-" + uuid.uuid4().hex)
target.mkdir(parents=True)
raw = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT)
for name in set(raw.decode("utf-8").split("\0")) - {""}:
    source = ROOT / name
    destination = (target / name).resolve()
    if not destination.is_relative_to(target.resolve()):
        raise ValueError("Source path escapes package checkout")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
for local in ("AGENTS.md", ".codex-local/PROJECT_CONTEXT.md"):
    destination = target / local
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / local, destination)
fingerprint = checker.source_fingerprint(ROOT)
assert checker.source_fingerprint(target) == fingerprint
manifest = {"source": str(target), "source_sha256": fingerprint,
            "work": str(work),
            "data": str(QA / ("package-data-" + uuid.uuid4().hex)),
            "scope": "unsigned local NSIS/portable build; no installer execution"}
(QA / "package-build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Isolated package source ready; source fingerprint", fingerprint)
