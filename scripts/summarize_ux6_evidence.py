"""Publish only aggregate QA evidence; preserve raw failures and their provenance."""
from pathlib import Path
import hashlib
import importlib.util
import json
import statistics

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / '.codex-local/ux-6'
spec = importlib.util.spec_from_file_location('ux6_checker', ROOT / 'scripts/verify_ux6_acceptance.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

def read(relative):
    p = QA / relative
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else None

def record(relative, source, scope):
    d = read(relative)
    if d is None:
        return {'status': 'MISSING', 'artifact': '.codex-local/ux-6/' + relative}
    count = len(d.get('checks', d.get('results', [])))
    result = {'artifact': '.codex-local/ux-6/' + relative,
              'sha256': hashlib.sha256((QA / relative).read_bytes()).hexdigest(),
              'source_sha256': d.get('source_sha256', source), 'scope': scope, 'checks': count,
              'failures': len(d.get('failures', [])), 'errors': len(d.get('errors', d.get('ordinaryErrors', [])))}
    result['executable_sha256'] = d.get('executableHash', d.get('executable_sha256'))
    timings = []
    for m in d.get('metrics', []):
        if m.get('kind') == 'native reload':
            timings.append(m['ms'])
        if m.get('kind') == 'native all messages loaded':
            raf = sorted(v for v in m['rAF'] if isinstance(v, (int, float)) and v > 0)
            result.setdefault('history', []).append({'messages': m['count'], 'pages': m['pages'],
                'load_all_ms': m['loadAllMs'], 'raf_samples': len(raf),
                'raf_p95_ms': raf[min(len(raf)-1, int(len(raf)*.95))]})
        if m.get('kind') == 'native paged selection':
            result.setdefault('selection', []).append({'messages': m['count'], 'ms': m['ms']})
        if 'process' in m.get('kind', '').lower():
            result['process_sample'] = {k: v for k, v in m.items() if k != 'processes'}
    if timings:
        ordered = sorted(timings)
        result['reload_ms'] = {'n': len(timings), 'median': statistics.median(timings), 'p95': ordered[min(len(ordered)-1, int(len(ordered)*.95))]}
    if 'contrast' in d:
        result['contrast'] = [{'theme': c['theme'], 'width': c['width'], 'samples': c['samples'], 'minimum': c['min'], 'failures': len(c['failures'])} for c in d['contrast']]
    if 'geometry' in d:
        result['geometry_cases'] = len(d['geometry'])
    if 'ms' in d:
        result['ms'] = d['ms']
    for key in ('versions','notices'):
        if key in d:
            result[key] = d[key]
    return result

current = checker.source_fingerprint()
prior = '0c969c975670165ad16a1d4dc198b9f348e26153f87e3adbae6138b1e0f509ed'
recovery = 'c159c81034ff3958ed13379e3fb48ce81012ca885728523883e6813ad8d8a3ab'
refined = '44717c6c938d74884e1c017c52eda54bec640f60b97c0266700c91aaf75ee360'
summary = {
    'stage_status': 'ACCEPTANCE_PENDING', 'base_commit': '6e13caf235d816c243cdbfc843e597d28964c767',
    'design_decision': 'D58', 'candidate_source_sha256': current,
    'evidence_boundary': 'Prior measurements retain measured source and binary identity. Recovery/voice candidates and the later recipe-only delta remain separate. Any central Composer-only delta has its own reviewed input comparison and focused browser/source evidence; no relabeling of older native or package runs.',
    'source': {'frontend_full': {'passed': 324, 'files': 45, 'source_sha256': prior, 'artifact': '.codex-local/ux-6/final/frontend-delivery.json'},
        'frontend_last_delta': {'passed': 1, 'artifact': '.codex-local/ux-6/final/watchdog.log', 'scope': 'targeted watchdog regression; not a 325-test full-suite result'},
        'frontend_voice': {'passed': 7, 'artifact': '.codex-local/ux-6/voice-composer.log', 'scope': 'five existing attachment/voice owner/hotkey checks plus two real-text/silence completion regressions; not a new full-suite result'},
        'frontend_voice_refinement': {'passed': 9, 'artifact': '.codex-local/ux-6/voice-refinement-frontend-r2.log', 'scope': 'focused Composer draft/speech/silence plus direct overlay rendering/button/Escape cancellation; two earlier test setup failures retained and corrected to use the real hotkey when a draft hides the mic button'},
        'frontend_full_final_attempts': 'incomplete, stopped after no completion; logs retained; not acceptance evidence',
        'python': {'passed': 553, 'seconds': 77.533, 'artifact': '.codex-local/ux-6/final/python-isolated.log', 'command': 'python -m unittest discover -s tests -t . -v', 'scope': 'Full suite before voice-only recognition change; preserved, not relabeled as a current full-suite rerun'},
        'python_voice_refinement': {'passed': 15, 'artifact': '.codex-local/ux-6/voice-refinement-python.log', 'command': 'python -m unittest tests.test_speech -v', 'scope': '13 existing speech tests plus two new recognition regressions: unknown audio is empty completion, real network failure remains an error'},
        'rust': {'passed': 31, 'source_sha256': recovery, 'artifact': '.codex-local/ux-6/final/rust-delivery.log', 'scope': 'includes isolated-smoke routing gate, before async voice command; current voice source separately compiled and tested in native QA'},
        'rust_current': {'passed': 31, 'source_sha256': refined, 'artifact': '.codex-local/ux-6/voice-refinement-rust.log', 'scope': 'voice transparency/async command and blank launch-override correction; complete existing31 Rust contracts. Later change affects only canonical child smoke environment, no Rust inputs changed'},
        'checker': {'passed': 4, 'artifact': '.codex-local/ux-6/final/checker-final.log'}},
    'windows_history': record('final/native-current/report.json', prior, 'actual built Tauri, WebView2 and source Core; Windows125%; deterministic model; before last recovery/smoke delta'),
    'windows_owners': record('final/native-workspace-current-r2/report.json', prior, 'actual native child browser ownership/motion/terminal/files at125%; before last recovery/smoke delta'),
    'windows_recovery_delta': record('final/lastchanges.json', recovery, 'actual recovery candidate; ordinary reload with fresh-document marker and retained owner draft/Core. Native fault injection ineffective, excluded; watchdog unit test only'),
    'windows_voice_delta': record('voice-native.json', current, 'actual first asynchronous native overlay creation, existing Core and close; fresh deterministic QA. No microphone capture by automation; user retest required'),
    'windows_voice_refinement': record('voicefinal-native.json', current, 'actual current built Windows overlay creation/close and same Core; rounded transparent native window, direct voice entry, silence handling covered by focused source tests and separately accepted user trial'),
    'package_runtime_audit': record('package-runtime-audit.json', current, 'actual private portable Python/Node execution and removed write probes; matching repository/frontend notices and runtime licenses; no installed-machine or exhaustive legal-audit claim'),
    'package_zip_audit': record('package-zip-audit.json', current, 'actual final ZIP opens and six essential archived payloads match exact tested portable files; no extraction or exhaustive dependency CRC pass'),
    'browser_accessibility': record('final/accessibility-final/report.json', recovery, 'adapted native IPC, actual isolated Core; unchanged frontend since this run, sampled contrast/AX/keyboard, no spoken screen reader'),
    'integrations': record('final/integrations/report.json', prior, 'actual unchanged Core custom/Skill install/trust/remove, unpinned MCP rejection, PDF bytes and terminal; not Windows choosers'),
    'dev_stability': record('final/dev-stability/report.json', prior, 'actual dev WebView, ten reloads and CSS/React HMR; original UX5 blank root not reproduced'),
    'relaunch_built': record('final/relaunch-built/report.json', prior, 'three actual owned quit/reopen cycles; observed times include helper/CDP probe overhead'),
    'relaunch_dev': record('final/relaunch-dev/report.json', prior, 'three actual owned quit/reopen cycles'),
    'known_failures': ['original UX5 blank root not reproduced', 'one built startup stall recovered on reload, cause unproved; 20 later reloads passed, invoke trace empty because native invoke is read-only', 'native stall injection ineffective and excluded; final watchdog unit test passed', 'earlier CSS zoom overflow fixed; final layout-only matrix27 passed', 'legacy native management verifier stopped at startup, no management PASS claimed', 'first NSIS deep resource path failed; short ASCII snapshot used', 'first packaged smoke exited0 without proof while personal instance was running; isolated-smoke routing corrected'],
    'isolation_incident': {'excluded_run': 'unittest discover -s tests -v, missing -t .', 'effect': 'derived personal MCP config rewritten with semantically unchanged four fields; test records appended to personal log; retained, no rollback', 'settings_and_chat_files': 'audit timestamps predate excluded test run; no prior byte-for-byte baseline claim', 'audit': '.codex-local/ux-6/isolation-audit.json'},
    'assisted_trial': {'artifact': 'docs/ux6_assisted_acceptance.json', 'voice_status': 'Initial dictation failure corrected. User accepted all three function checks and all three requested refinements. No further voice retest requested.', 'scope': 'Positive general report outside dictation retained without inventing provider/scale details; stage central acceptance remains pending'},
    'needs_user': ['central review/acceptance; no more voice testing requested', 'per-provider/per-DPI or exact action details remain unspecified; no new broad repeat requested', 'external MCP pinned package/trust/live connection requires chosen target'],
    'separate_scope': ['clean Windows install/upgrade/uninstall/VM', 'signed production package/update/release', 'multi-monitor physical restore'],
    'not_performed': ['push', 'publish', 'personal installer execution', 'PyQt removal', 'Point17', 'final commit', 'stage completion']
}
package_manifest = read('package-build.json')
if package_manifest and package_manifest.get('recipe_only_delta'):
    summary['recipe_only_delta'] = package_manifest['recipe_only_delta'] | {'artifact':'.codex-local/ux-6/package-recipe-delta.json'}
if package_manifest:
    package_report = Path(package_manifest['source']) / 'release/SmartiAI-Agent-for-Windows-0.87.0-manifest.json'
    if package_report.is_file():
        report = json.loads(package_report.read_text(encoding='utf-8-sig'))
        summary['package'] = {'source_sha256': package_manifest['source_sha256'], 'compiled_executable_source_sha256':report.get('compiled_executable_source_sha256'),'artifacts': [{k: item[k] for k in ('bytes', 'sha256')} | {'name': Path(item['path']).name} for item in report['artifacts']],
            'updaterSigned': report['updaterSigned'], 'authenticode': report['authenticode']['status'],
            'smokes': {name: report['packageSmoke'][name].get('ok') for name in ('supervisor', 'browser')} | {'passed': report['packageSmoke']['passed']},
            'recipe_overrides': package_manifest.get('recipe_overrides'),
            'matches_current_candidate': package_manifest['source_sha256'] == current,
            'scope': 'unsigned local NSIS/portable; no installation; raw report in owned ASCII build checkout. If source differs, this is retained prior-artifact evidence, not current voice candidate packaging.'}
    else:
        summary['package'] = {'status': 'PENDING', 'source_sha256': package_manifest['source_sha256']}
central_path = ROOT / 'docs/ux6_central_review.json'
closure_path = ROOT / 'docs/ux6_closure.json'
closure = json.loads(closure_path.read_text(encoding='utf-8')) if closure_path.is_file() else None
if central_path.is_file():
    central = json.loads(central_path.read_text(encoding='utf-8'))
    if central['source_sha256'] != current:
        assert closure and closure['source_sha256'] == current, 'Central review belongs to another candidate'
        bridge = closure['reviewed_source_recipe_delta']
        assert bridge['reviewed_source_sha256'] == central['source_sha256']
        assert bridge['projected_source_sha256'] == central['source_sha256']
        inputs = checker.source_inputs()
        for name in bridge['added_paths']:
            assert name in {'scripts/build_and_package.ps1', 'scripts/prepare_tauri_package.py', 'scripts/tauri_source_manifest.py'}
            del inputs[name]
        assert set(bridge['previous_input_hashes']) == {'scripts/build_tauri_release.ps1'}
        inputs.update(bridge['previous_input_hashes'])
        digest = hashlib.sha256()
        for name, content_hash in sorted(inputs.items()):
            digest.update(name.encode()); digest.update(b'\0'); digest.update(bytes.fromhex(content_hash))
        assert digest.hexdigest() == central['source_sha256'], 'Review bridge changes product inputs'
        summary['reviewed_source_recipe_delta'] = bridge
    summary['central_review'] = central | {'artifact':'docs/ux6_central_review.json'}
    summary['assisted_trial']['scope'] = 'Voice function/refinements and user-confirmed actual Windows100/150/200%, enlarged text and spoken reader retained at the candidate scopes recorded in the assisted/central receipts. Latest Composer correction is source/browser tested; not yet in a matching package.'
    summary['needs_user'] = ['Build the corrected candidate with scripts/build_ux6_package.ps1 -Fresh; agent was explicitly asked not to rebuild', 'Formal per-action and release-scope decisions remain explicit; no repeated voice or broad scale matrix requested', 'External MCP target/clean installation/signing remain separate authorized scope']
if closure:
    assert closure['source_sha256'] == current and closure['result'] == 'PASS'
    assert closure['scope'] == 'source-and-accepted-ui' and closure['user_authorized_closure'] is True
    assert closure['release_accepted'] is False
    summary['central_closure'] = closure | {'artifact':'docs/ux6_closure.json'}
    summary['stage_status'] = 'COMPLETE'
    summary['stage_scope'] = 'source-and-accepted-ui; strict all-level product/release acceptance remains separate'
    summary['source']['universal_packaging_checks'] = closure['packaging_checks']
    summary['source']['web_build'] = closure['web_build']
    summary['needs_user'] = ['When a new package is wanted, run scripts/build_and_package.ps1 with optional Version/Label; no actual new package built by this closure', 'Review matching package manifest and smokes before package acceptance; keep clean installation/signing/release separate', 'External provider/MCP/Office/extra-monitor evidence needs its own defined target; no repeated broad voice/scale trial requested']
    summary['not_performed'] = ['push', 'publish', 'personal installer execution', 'PyQt removal', 'Point17', 'new full native/package build during closure', 'full product/release acceptance']
(ROOT / 'docs/ux6_evidence_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print('Aggregate evidence saved; raw provenance and gaps retained')
