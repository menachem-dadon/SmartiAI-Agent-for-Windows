"""Bounded private-runtime and notice checks on the already built portable tree."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.codex-local/ux-6'
m = json.loads((QA/'package-build.json').read_text(encoding='utf-8-sig'))
work, source = Path(m['work']).resolve(), Path(m['source']).resolve()
assert work.parent == Path('C:/') and work.name.startswith('SmartiAI-ux6-build-')
assert source == work/'source'
portable = work/'portable/SmartiAI'
runtime = portable/'package-resources/runtime'
profile = QA/('package-runtime-probe-'+uuid.uuid4().hex)
profile.mkdir()
env = os.environ.copy()
for key in ('OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY','DEEPSEEK_API_KEY','MISTRAL_API_KEY','XAI_API_KEY','HF_TOKEN','CODEX_API_KEY','CODEX_ACCESS_TOKEN','PYTHONPATH','PYTHONHOME'):
    env.pop(key, None)
env.update(SMARTI_DATA_DIR=str(profile), CODEX_HOME=str(profile/'codex-account'), PYTHON_KEYRING_BACKEND='keyring.backends.null.Keyring')
versions = {}
for name, args in [('python',['-I','-c','import sys; print(".".join(map(str,sys.version_info[:3])))']), ('node',['--version'])]:
    folder = runtime/name
    binary = folder/(name+'.exe')
    assert binary.is_file() and binary.resolve().is_relative_to(portable.resolve())
    versions[name] = subprocess.run([str(binary),*args],cwd=profile,env=env,capture_output=True,text=True,timeout=15,check=True).stdout.strip()
    probe = folder/('ux6-write-'+uuid.uuid4().hex+'.tmp')
    try:
        probe.write_bytes(b'isolated UX6 permission probe')
        assert probe.read_bytes() == b'isolated UX6 permission probe'
    finally:
        assert probe.resolve().is_relative_to(portable.resolve())
        probe.unlink(missing_ok=True)
notices = {}
for name, item, origin in [('repository PolyForm notice',portable/'LICENSE',ROOT/'LICENSE'), ('Tabler MIT',source/'desktop/dist/licenses/tabler-icons-MIT.txt',ROOT/'desktop/public/licenses/tabler-icons-MIT.txt'), ('Lobe Icons MIT',source/'desktop/dist/licenses/lobe-icons-MIT.txt',ROOT/'desktop/public/licenses/lobe-icons-MIT.txt'), ('private Python license',runtime/'python/LICENSE.txt',None), ('private Node license',runtime/'node/LICENSE',None)]:
    assert item.is_file()
    digest = hashlib.sha256(item.read_bytes()).hexdigest()
    if origin:
        assert digest == hashlib.sha256(origin.read_bytes()).hexdigest()
    notices[name] = {'sha256':digest,'bytes':item.stat().st_size}
spec=importlib.util.spec_from_file_location('checker',ROOT/'scripts/verify_ux6_acceptance.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
assert checker.source_fingerprint() == m['source_sha256']
report = {'source_sha256':m['source_sha256'],'checks':['private Python executes','private Node executes','both runtime folders writable using removed private probes','repository and frontend MIT notices match their source','Python and Node notices present'],'versions':versions,'notices':notices,'scope':'Actual owned portable resource tree and built frontend notices; no installation, network tool/package downloads or exhaustive third-party legal review. Runtime directory writability is measured here, not on a clean installed machine.'}
(QA/'package-runtime-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('Private packaged runtimes and notices passed; no installation or external download')
