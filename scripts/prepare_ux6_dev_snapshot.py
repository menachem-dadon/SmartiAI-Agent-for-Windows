"""Freeze only tracked frontend plus current new source into an owned HMR root."""
from pathlib import Path
import shutil
import re
import subprocess
ROOT = Path(__file__).resolve().parents[1]
target = ROOT / '.codex-local/ux-6/frozen-after/desktop'
target.mkdir(parents=True, exist_ok=False)
names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', 'desktop'], cwd=ROOT).decode().split('\0')
for name in set(names) - {''}:
    source = ROOT / name
    relative = Path(name).relative_to('desktop')
    if source.is_file() and relative.parts[0] not in {'src-tauri', 'node_modules', 'dist'}:
        destination = (target / relative).resolve()
        assert destination.is_relative_to(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
for source in (ROOT / 'desktop/src').rglob('*'):
    if source.is_file() and source.suffix in {'.ts', '.tsx', '.css'}:
        for name in re.findall(r'[\"\'](\.\./\.\./assets/[^\"\']+)[\"\']', source.read_text(encoding='utf-8')):
            asset = (source.parent / name).resolve()
            assert asset.is_relative_to(ROOT / 'assets') and asset.is_file()
            destination = target.parent / asset.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(asset, destination)
print('Owned dev snapshot ready')
