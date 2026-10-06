"""Read-only personal metadata/derived-config audit; no Smarti imports or secrets output."""
from pathlib import Path
import ast
import datetime
import json
import logging
import os
ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.codex-local/ux-6'
personal = Path(os.environ['APPDATA']) / 'SmartiAI'
settings = json.loads((personal / 'smarti_settings.json').read_text(encoding='utf-8-sig'))
actual = json.loads((personal / 'mcp_config.json').read_text(encoding='utf-8-sig'))
runtime = ast.parse((ROOT / 'smarti/agent/runtime_services.py').read_text(encoding='utf-8-sig'))
policy = ast.parse((ROOT / 'smarti/agent/execution_policy.py').read_text(encoding='utf-8-sig'))
methods = []
for module in (runtime, policy):
    for cls in (n for n in module.body if isinstance(n, ast.ClassDef)):
        methods.extend(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {'_ensure_mcp_config', '_get_mcp_allowed_dirs', '_sandbox_enabled', '_sandbox_root', '_abs_path'})
fixture = ast.ClassDef(name='PureConfig', bases=[], keywords=[], body=methods, decorator_list=[])
namespace = {'json': json, 'os': os, 'logging': logging, 'APP_DIR': str(ROOT), 'OUTPUTS_DIR': settings.get('default_output_dir', str(QA)), 'MCP_CONFIG_FILE': str(QA / 'derived-mcp-audit.json')}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fixture], type_ignores=[])), '<read-only config audit>', 'exec'), namespace)
instance = namespace['PureConfig']()
instance.settings = settings
instance._ensure_mcp_config()  # Destination is QA, never the personal file.
expected = json.loads((QA / 'derived-mcp-audit.json').read_text(encoding='utf-8'))
(QA / 'derived-mcp-audit.json').unlink()  # Do not retain personal config values in QA output.
report = {'unsafe_runner': 'unittest discover -s tests -v (missing -t .), excluded from acceptance', 'personal_file_metadata': [{ 'file': name, 'modified_utc': datetime.datetime.fromtimestamp((personal / name).stat().st_mtime, datetime.timezone.utc).isoformat() } for name in ('smarti_settings.json', 'smarti_chats.sqlite3', 'smarti_memory.json', 'smarti_memory.sqlite3', 'smarti_usage.json', 'mcp_config.json', 'smarti_agent.log')], 'derived_mcp_matches_current_canonical_settings': actual == expected, 'mcp_comparison_fields': {key: actual.get(key) == expected.get(key) for key in expected}, 'scope': 'Audit itself: no Smarti imports, no secure keyring or credential-store access, no personal writes; metadata plus semantic derived config comparison; no claim about unrecorded prior bytes. The excluded unsafe test run rewrote derived MCP config and appended personal log records; both retained.'}
(QA / 'isolation-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'derived_mcp_matches': report['derived_mcp_matches_current_canonical_settings'], 'fields_match': report['mcp_comparison_fields']}))
