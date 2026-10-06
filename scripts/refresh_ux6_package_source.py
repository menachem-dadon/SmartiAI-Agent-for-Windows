"""Refresh only changed executable source after preserving the previous build inputs."""
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import uuid
ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.codex-local/ux-6'
manifest = json.loads((QA / 'package-build.json').read_text(encoding='utf-8-sig'))
target = Path(manifest['source']).resolve()
assert target == Path(manifest['work']).resolve() / 'source'
assert target.parent.name.startswith('SmartiAI-ux6-build-') and target.parent.parent == Path('C:/')
spec = importlib.util.spec_from_file_location('ux6_checker', ROOT / 'scripts/verify_ux6_acceptance.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
prior = QA / ('package-prior-inputs-' + uuid.uuid4().hex)
prior.mkdir(exist_ok=False)
manifest['prior_executable_source_sha256'] = checker.source_fingerprint(target)
previous = QA / ('package-build-before-' + uuid.uuid4().hex + '.json')
previous.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode().split('\0')
for name in set(names) - {''}:
    source = ROOT / name
    destination = (target / name).resolve()
    assert destination.is_relative_to(target)
    if source.is_file() and (not destination.is_file() or source.read_bytes() != destination.read_bytes()):
        if destination.is_file():
            backup = prior / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, backup)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
assert checker.source_fingerprint(target) == checker.source_fingerprint(ROOT)
manifest['source_sha256'] = checker.source_fingerprint(ROOT)
manifest['recipe_overrides'] = ['unsigned local artifacts', 'NSIS zlib compression for local QA only; production default unchanged']
(QA / 'package-build.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Current executable source ready for final local package rebuild')
