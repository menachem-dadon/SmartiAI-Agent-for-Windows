"""Recover the owned build in a short ASCII checkout, reusing its exact Core/runtime."""
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.codex-local/ux-6'
manifest = json.loads((QA / 'package-build.json').read_text(encoding='utf-8-sig'))
work = Path(manifest['work']).resolve()
assert work.parent == Path('C:/') and work.name.startswith('SmartiAI-ux6-build-')
assert (work / 'dist/smarti-core/smarti-core.exe').is_file()
target = work / 'source'
target.mkdir(exist_ok=False)
names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode().split('\0')
for name in set(names) - {''}:
    source = ROOT / name
    destination = (target / name).resolve()
    assert destination.is_relative_to(target)
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
for name in ('AGENTS.md', '.codex-local/PROJECT_CONTEXT.md'):
    (target / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / name, target / name)
spec = importlib.util.spec_from_file_location('ux6_checker', ROOT / 'scripts/verify_ux6_acceptance.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
assert checker.source_fingerprint(ROOT) == checker.source_fingerprint(target)
manifest['failed_source'] = manifest['source']
manifest['source'] = str(target)
manifest['source_sha256'] = checker.source_fingerprint(target)
manifest['recovery'] = 'short ASCII checkout after NSIS deep resource path failure; same completed Core/runtime; canonical build and package smokes still required'
(QA / 'package-build.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Owned short package checkout ready')
