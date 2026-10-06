"""Refresh action coverage conservatively; partial runtime proof never closes a gap."""
from pathlib import Path
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'docs/ux6_acceptance.json'
data = json.loads(path.read_text(encoding='utf-8'))
spec = importlib.util.spec_from_file_location('ux6_checker', ROOT / 'scripts/verify_ux6_acceptance.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
summary_path = ROOT / 'docs/ux6_evidence_summary.json'
summary = json.loads(summary_path.read_text(encoding='utf-8'))
current = checker.source_fingerprint()
assert summary['candidate_source_sha256'] == current
data['stage_status'] = 'ACCEPTANCE_PENDING'
data.pop('central_acceptance', None)
data['candidate_source_sha256'] = current
data['evidence'] = {}

source_groups = {
    'SHL': 'workspaceState, legacyUiParity, coreState, WindowTitleBar and ux5Management frontend tests; Rust placement/activation contracts',
    'CHT': 'chatState, chatUi, MessageTable, speechPlayback frontend tests; test_conversation_runs and test_api_provider_runtime',
    'CMP': 'composerModels, composerAttachments, chatUi frontend contracts',
    'ATT': 'test_attachments15 and composerAttachments; native picker is separate',
    'HIS': 'test_history_sqlite6, test_conversation_runs and conversationAttention',
    'RUN': 'test_conversation_runs33, test_background_routing6, conversationAttention and agentThinking',
    'APR': 'test_conversation_approvals8, test_api_provider_runtime33 and conversationApprovals',
    'GAT': 'test_conversation_runs authenticated/idempotent API and durable event contracts',
    'SET': 'test_settings_sync11, test_ssl_trust22, settingsSync, settingsLoading, ProviderPicker and ux5Management',
    'MGT': 'managementFocus, popupDismissal, ux5Management and settingsSync',
    'USE': 'test_usage_stats18 and UsageView',
    'MEM': 'test_memory_management29, test_memory_profile_policy5 and test_memory_quality_v2_11',
    'TSK': 'test_background_routing6 and TasksView; recurrence contract tests',
    'TOL': 'test_doctor34, test_file_manager25 and actual isolated local integration report; no external package connection claim',
    'DIA': 'test_doctor34 and test_logging_export_and_windows_ui19',
    'ABT': 'ux5Management legal text/version and test_settings_sync',
    'FIL': 'test_workspace18, test_document_manager16, WorkbenchFilesPicker and WorkbenchPanels; no Office GUI claim',
    'ART': 'WorkbenchArtifacts and test_workspace',
    'TRM': 'test_workspace and workbenchLifecycle; actual Core terminal integration',
    'CAN': 'test_visual_canvas12 and CanvasPanel',
    'BRW': 'browserState, BrowserPanel, browserViewport, useNativeBrowserSurface and Rust browser safety contracts',
    'VOC': '15 speech/recognition tests, nine focused Composer/overlay tests, current native creation and assisted trial; global shortcut is a separate scope',
    'TTS': 'test_speech13 and speechPlayback idle/status/owner regressions; actual audio is separate',
    'WIN': 'test_notification_policy12, test_logging_export_and_windows_ui19, WindowTitleBar and Rust31 contracts',
    'UPD': 'test_update_discovery9 and updates; no online update download/install',
    'PKG': 'Current source/config review, compiled GUI/Core and canonical smoke child environment; exact artifact/runtime/notices proofs in summary; no clean-machine install claim',
}
source_exclusions = {'BRW-004', 'BRW-006', 'BRW-007', 'PKG-005'}
user_gaps = {
    'UX6-LOAD': 'Original UX5 blank root and one built startup stall have no proved cause. Prior dev/HMR/relaunch evidence and final deliberate recovery are retained separately.',
    'UX6-A11Y': 'User explicitly confirmed spoken screen reader and Windows text enlargement in the earlier UX6 trial. Keep the exact scope in central review; final Composer source/browser correction is not yet in a matching native/package candidate. No broad repeat requested.',
    'UX6-DPI': 'Actual125% HWND measured; user explicitly confirmed Windows100/150/200% in the earlier trial. Current Composer correction is independently browser tested. Prior scale acceptance is retained, not relabeled as a new native run; extra monitor remains separate scope.',
    'UX6-PERF': 'Prior built-source measurements are in the summary with exact provenance. No further broad performance repeat after final startup-only delta, per user request; real provider latency still unmeasured.',
    'UX6-OWNERS': 'Prior16/26 native checks retained. Final candidate proves ordinary reload draft/Core retention only; full native approvals and all owner contexts remain acceptance review.',
    'UX6-MOTION': 'Prior actual native child bounds/reversal/live reduce passed26. Final browser motion passed; final native candidate is not relabeled as that prior binary.',
    'UX6-ACCOUNT': 'User chooses test provider and enters/login themselves in private QA. Real quota and conversation pending.',
    'UX6-AUDIO': 'Dictation failure corrected and all three function checks plus three requested refinements accepted by user. General positive trial retained. Exact global-shortcut/TTS/tray action details remain unspecified; no further voice retest requested.',
    'UX6-SSL': 'Localhost trust/rejection contracts pass in source. Actual Windows system trust/custom CA import pending user; no global insecure setting.',
    'UX6-TOOLS': 'Actual local Python/Skill install/trust/remove and unpinned MCP rejection tested through Core; external pinned MCP install/connection/permissions pending defined test target.',
    'UX6-DOCS': 'Real PDF bytes verified. Office display/system file dialogs/save/Open With actual application selection need user.',
    'UX6-PACKAGE': 'Existing unsigned local installer/ZIP and canonical smoke include accepted voice refinements but precede the final Composer-size correction. Matching corrected package is pending user-run build. Installation/signing/release are separate scope.'
}
def evidence(key, level, ids, artifact, scope):
    p = ROOT / artifact
    assert p.is_file()
    data['evidence'][key] = {'level': level, 'result': 'PASS', 'source_sha256': current,
        'capabilities': ids, 'artifact': artifact, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'scope': scope}

source_ids = []
for row in data['capabilities']:
    id = row['id']
    prefix = id.split('-')[0]
    if id in ('PKG-001', 'PKG-003'):
        row.setdefault('baseline_action', row['action'])
        row['action'] = 'Tauri GUI with Qt-free PyInstaller Core sidecar' if id == 'PKG-001' else 'Per-user NSIS installer, unsigned local QA artifact only'
        row['authority'] = 'Canonical scripts/build_tauri_release.ps1 and packaging/smarti-core.spec; personal install not authorized'
    row['source_coverage'] = source_groups.get(prefix, 'See final delta/source contracts in evidence summary')
    row['partial_evidence'] = ['docs/ux6_evidence_summary.json']
    for level in row['required_levels']:
        status = 'OPEN'
        gap = 'Per-action Windows or package proof still required; preserved functional source checks and prior native evidence are not substituted for it.'
        if id in user_gaps:
            gap = user_gaps[id]
            if level == 'windows' and id in {'UX6-A11Y','UX6-DPI','UX6-ACCOUNT','UX6-AUDIO','UX6-SSL','UX6-TOOLS','UX6-DOCS'}:
                status = 'NEEDS_USER'
        if id == 'PKG-005':
            status = 'OUT_OF_SCOPE'; gap = 'No clean VM/install/upgrade/uninstall target authorized; personal installation prohibited.'
        if level == 'source' and id not in source_exclusions and (prefix in source_groups or id in {'UX6-A11Y','UX6-OWNERS','UX6-MOTION','UX6-SSL','UX6-TOOLS','UX6-PACKAGE'}):
            source_ids.append(id)
            row['results'][level] = {'status': 'PASS', 'evidence': ['source-contract-review']}
        else:
            row['results'][level] = {'status': status, 'gap': gap, 'evidence': []}
    if id in {'SET-003','SET-004','VOC-001','VOC-002','TTS-001','WIN-003','WIN-006','FIL-004','ATT-001'}:
        row['results']['windows'] = {'status': 'NEEDS_USER', 'gap': 'Real provider/account/hardware/Windows dialog/scale or application selection is required; see user checklist.', 'evidence': []}
    central = summary.get('central_review', {})
    if central and id in {'UX6-A11Y','UX6-DPI','VOC-001'}:
        row['partial_evidence'].extend(['docs/ux6_assisted_acceptance.json','docs/ux6_central_review.json'])
        row['results']['windows'] = {'status':'OPEN','gap':user_gaps.get(id, 'Dictation function and refinements already accepted at recorded prior sources. Only Composer sizing changed; no repeated voice trial requested. Matching post-correction native/package candidate remains pending.'),'evidence':[]}

evidence('source-contract-review', 'source', source_ids, 'docs/ux6_evidence_summary.json',
    'Current-source contract review plus prior324 frontend, watchdog/voice,31 Rust and553 Python evidence at their recorded sources. Central review records329 frontend checks begun before the last Composer edit,14 focused post-edit Composer tests, typecheck,19 isolated Python checks and four rendered Composer cases. Scoped closure adds a verified recipe-only bridge, a production web build and11 isolated orchestration/checker tests (mock package payloads only). Native/package runs retain prior candidate identity. Per-action selectors are in each row; no external provider, fresh full Python or actual new package claim.')
a11y = ROOT / '.codex-local/ux-6/final/accessibility-final/report.json'
if a11y.is_file() and summary['browser_accessibility']['source_sha256'] == current:
    d = json.loads(a11y.read_text(encoding='utf-8'))
    assert not d['failures'] and not d['ordinaryErrors']
    evidence('browser-final-accessibility','browser',['UX6-A11Y','UX6-MOTION'],'.codex-local/ux-6/final/accessibility-final/report.json',
             'Final-source adapted native IPC, actual isolated Core; sampled contrast/keyboard/focus/Escape/reversals/live reduce. No native DPI, native child browser bounds or screen reader claim.')
    for row in data['capabilities']:
        if row['id'] in {'UX6-A11Y','UX6-MOTION'}:
            row['results']['browser'] = {'status':'PASS','evidence':['browser-final-accessibility']}
assisted=ROOT/'docs/ux6_assisted_acceptance.json'
if assisted.is_file():
    human=json.loads(assisted.read_text(encoding='utf-8'))
    bridge=summary.get('recipe_only_delta',{})
    same_voice_inputs=(human['dictation_refinement']['source_sha256']==current or
        (bridge.get('source_sha256')==current and bridge.get('compiled_executable_source_sha256')==human['dictation_refinement']['source_sha256'] and bridge.get('changed_paths')==['scripts/build_tauri_release.ps1']))
    if same_voice_inputs and human['dictation_refinement']['status']=='PASS':
        evidence('windows-assisted-dictation','windows',['VOC-001'],'docs/ux6_assisted_acceptance.json',
                 'Actual user microphone/transcription/overlay/cancel trial: three function cases on first async candidate, three refinements explicitly accepted on refined candidate; actual source identities preserved. Any later recipe-only delta is explicitly verified to change no GUI/Core/assets/config inputs. No global hotkey or package claim.')
        next(row for row in data['capabilities'] if row['id']=='VOC-001')['results']['windows']={'status':'PASS','evidence':['windows-assisted-dictation']}
package=summary.get('package',{})
if package.get('matches_current_candidate') and package.get('smokes',{}).get('passed'):
    ids=['PKG-001','PKG-002','PKG-003','PKG-004','UX6-PACKAGE']
    evidence('package-local-unsigned','package',ids,'docs/ux6_evidence_summary.json',
             'Actual unsigned local NSIS and portable ZIP 0.87.0, compiled GUI/Core source retained separately from recipe-only delta; exact hashes/signature and canonical supervisor/browser smoke. Private runtime execution/writability and matching notices audited separately. No installation, upgrade/uninstall, signing or exhaustive legal review.')
    for row in data['capabilities']:
        if row['id'] in ids:
            row['results']['package']={'status':'PASS','evidence':['package-local-unsigned']}
closure = summary.get('central_closure')
if closure:
    pending = sum(result['status'] != 'PASS' for row in data['capabilities'] for result in row['results'].values())
    assert closure['source_sha256'] == current and closure['pending_evidence_levels'] == pending
    assert closure['scope'] == 'source-and-accepted-ui' and closure['release_accepted'] is False
    artifact = ROOT / closure['artifact']
    data['stage_status'] = 'COMPLETE'
    data['central_acceptance'] = {'artifact':closure['artifact'], 'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}
errors = checker.validate(data)
assert not errors, '\n'.join(errors)
path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Acceptance refreshed: {len(source_ids)} source contracts; scoped closure, exact provenance and product/release gaps retained')
