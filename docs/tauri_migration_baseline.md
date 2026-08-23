# SmartiAI legacy baseline and feature-parity inventory

Baseline date: 2026-08-21  
Migration plan: [tauri_migration_execution_plan.md](tauri_migration_execution_plan.md)  
Product target: `V0.87.0`

This document is the comparison boundary for the Tauri migration. It describes
the current Python/PyQt product without changing its behavior. Evidence levels
are intentionally separate; a source test or an older package is not package
proof for the current checkout.

## 1. Source and dirty-state boundary

- Branch: `main`.
- Commit: `c88af74f5d4353cdd6e8ca5e04800e77a582aa87`.
- The first `git status --short` call reported nine files as untracked: the
  migration plan plus eight theme icons:
  `docs/tauri_migration_execution_plan.md`,
  `assets/sidebar_{collapse,expand}_icon_{dark,light}.png`, and
  `assets/workbench_{close,open}_icon_{dark,light}.png`. A later index/HEAD
  refresh at the same commit confirmed all nine are tracked by `c88af74`; the
  current status therefore does not treat them as dirty. Point 1 did not alter
  their contents.
- Point 1 adds this document and
  [`scripts/capture_tauri_migration_baseline.py`](../scripts/capture_tauri_migration_baseline.py).
- Generated screenshots, isolated runtime data, and metrics are under
  `.codex-local/tauri-baseline/`, which is excluded by `.git/info/exclude`.
- No commit, push, publication, database migration, Tauri scaffold, or product
  behavior change was made.

## 2. Machine and toolchain snapshot

| Item | Baseline |
|---|---|
| OS | Windows 11 Home x64, `10.0.26200`, build `26200` |
| Physical RAM | 16,849,293,312 bytes (15.69 GiB) |
| Free disk before package attempt | 31,992,541,184 bytes (29.80 GiB) on `C:` |
| Developer Python | CPython 3.13.5 x64, `C:\Python313\python.exe` |
| PyQt | PyQt6 6.11 / Qt 6.11 family installed |
| PyInstaller | Host 6.14.2; cached build environment upgraded to 6.21.0 |
| Git | 2.53.0.windows.1 |
| Node/npm | Node 22.18.0 / npm 10.9.3 |
| Pinned private runtimes | Python 3.12.10 and Node 22.23.2; see [`packaging/runtime-versions.json`](../packaging/runtime-versions.json) |
| Inno Setup | Not on `PATH`; the release script searches normal Inno Setup 6 install locations |
| Rust/Tauri toolchain | `cargo` and `rustc` not installed at this baseline; not required before Point 5 |

The release version is synchronized in [`smarti/common.py`](../smarti/common.py),
[`README.md`](../README.md), [`packaging/smarti.iss`](../packaging/smarti.iss),
and [`scripts/build_release.ps1`](../scripts/build_release.ps1).

## 3. Reproducible measurements

### 3.1 Import boundary

Fresh-process `import smarti.core` took `0.949815 s` and loaded:

```text
PyQt6
PyQt6.QtCore
PyQt6.QtGui
PyQt6.QtWidgets
PyQt6.sip
smarti.visual_canvas
```

This is the expected failing boundary that Point 2 must remove. The coupling is
visible in [`smarti/agent/shared.py`](../smarti/agent/shared.py),
[`smarti/common.py`](../smarti/common.py), and
[`smarti/visual_canvas.py`](../smarti/visual_canvas.py).

### 3.2 Source startup, memory, and idle CPU

The reproducible capture command is:

```powershell
python scripts/capture_tauri_migration_baseline.py
```

It uses a new isolated `SMARTI_DATA_DIR`, disables the local gateway and update
check, constructs the real `SmartiCore` and `ChatWindow`, and never reads the
normal user profile. On the machine above at 125% display scale:

| Metric | Result |
|---|---:|
| Source process start to populated Workspace | 4.963685 s |
| `SmartiCore` construction | 1.176030 s |
| `ChatWindow` construction/show sample | 3.248072 s |
| Working set after capture | 203,157,504 bytes (193.75 MiB) |
| Private bytes after capture | 117,309,440 bytes (111.88 MiB) |
| Idle sample | 5.004727 s |
| Process CPU during idle | 2.1854% of one logical core |

These are source-process measurements with an empty isolated profile, not a
packaged cold-start benchmark and not total memory including a managed browser.
Later points must use the same scope or explain the difference.

### 3.3 Artifact size boundary

The user explicitly stopped and waived a new Point 1 build on 2026-08-21. The
following existing V0.87.0 files were built on 2026-08-06, before the baseline
commit, and are recorded only as historical size/hash data. They are not package
evidence for the current checkout and were not installed or smoke-tested here.

| Historical artifact | Bytes | MiB | SHA-256 | Signature |
|---|---:|---:|---|---|
| `release/SmartiAI-Agent-for-Windows-0.87.0-Setup.exe` | 576,497,220 | 549.79 | `F05EE3813F4E03F44E9E0D793E397E59775D2C9077B33BC2F9342CDFF8BE2DFB` | NotSigned |
| `release/SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip` | 828,358,293 | 789.98 | `858061495C3EEFC8CD225A78C0703F70BD27F41EA777494AF891ADC4C4E7308A` | n/a |
| `C:\SmartiAI-build\dist\SmartiAI\SmartiAI.exe` | 32,887,729 | 31.36 | `F5B8D3C294BB24C5911E8B2D43B9DE37F2F8FF80BFA3FCA7D3C08F54E941E684` | NotSigned |

The historical `onedir` tree contains 18,873 files totaling 2,028,976,408
bytes (1,934.98 MiB). A new build was interrupted during PyInstaller Analysis
at the user's request; it produced no new release artifact.

## 4. Current architecture and dependency map

### 4.1 Process and module ownership

```text
smarti_core.pyw
  -> smarti.app (QApplication, legal gate, splash, single instance)
     -> smarti.core.SmartiCore compatibility facade
        -> smarti.agent.* runtime mixins
        -> ConversationRunManager + ChatSessionStore + local /v1 gateway
     -> smarti.chat.ChatWindow
        -> central chat + right conversation drawer
        -> on-demand left WorkspaceWorkbench
        -> management center and Windows desktop projections
```

| Domain | Current authority and important links |
|---|---|
| Launch/lifecycle | [`smarti/app.py`](../smarti/app.py), [`smarti_core.pyw`](../smarti_core.pyw) |
| Core composition | [`smarti/core.py`](../smarti/core.py), [`smarti/agent/lifecycle.py`](../smarti/agent/lifecycle.py) |
| Agent/model loop | [`smarti/agent/messaging.py`](../smarti/agent/messaging.py), [`smarti/agent/model_context.py`](../smarti/agent/model_context.py) |
| Tool policy/routing | [`smarti/agent/execution_policy.py`](../smarti/agent/execution_policy.py), [`smarti/agent/tool_calls.py`](../smarti/agent/tool_calls.py), [`smarti/agent/tool_dispatch.py`](../smarti/agent/tool_dispatch.py) |
| Durable conversations | [`smarti/run_manager.py`](../smarti/run_manager.py), [`smarti/history.py`](../smarti/history.py), [runtime contract](conversation_runtime_architecture.md) |
| Local control plane | [`smarti/local_gateway.py`](../smarti/local_gateway.py), loopback authenticated `/v1` |
| Desktop UI | [`smarti/chat.py`](../smarti/chat.py), [`smarti/workspace_ui.py`](../smarti/workspace_ui.py), [`smarti/ui_pages.py`](../smarti/ui_pages.py) |
| Memory | [`smarti/managers.py`](../smarti/managers.py), [`smarti/memory_store.py`](../smarti/memory_store.py), [`smarti/memory_ui.py`](../smarti/memory_ui.py) |
| Browser | [`smarti/native_browser.py`](../smarti/native_browser.py), [`smarti/browser_control.py`](../smarti/browser_control.py), [`smarti/browser_profile.py`](../smarti/browser_profile.py) |
| Canvas | [`smarti/visual_canvas.py`](../smarti/visual_canvas.py), currently combines persisted model and Qt renderer |
| Windows integration | [`smarti/windows_notifications.py`](../smarti/windows_notifications.py), tray/single-instance code in `chat.py`/`app.py` |
| Packaging/update | [`packaging/smarti.spec`](../packaging/smarti.spec), [`packaging/smarti.iss`](../packaging/smarti.iss), [`smarti/updater.py`](../smarti/updater.py) |

Largest presentation-heavy modules are `smarti/chat.py` (~7,847 physical
lines), `smarti/ui_pages.py` (~6,372), and `smarti/workspace_ui.py` (~2,518).
Core-heavy modules include `smarti/managers.py`, `agent/file_tools.py`,
`agent/document_tools.py`, and `agent/model_context.py`. The migration must
separate ownership; it must not translate these files line-for-line.

### 4.2 External dependency groups

| Group | Current packages / purpose |
|---|---|
| Qt presentation | `PyQt6`, `PyQt6-WebEngine` |
| HTTP/providers | `requests`, `urllib3`, `certifi`, `httpx`, `aiohttp`, `truststore`, `cryptography`, `openai`, `litellm` |
| Browser/desktop control | `playwright`, `PyAutoGUI`, `uiautomation`, `pyperclip`, `pywin32` |
| Speech/audio | `SpeechRecognition`, `PyAudio`, `gTTS`, `edge-tts`, `pygame`, `keyboard` |
| Content/documents | `Markdown`, `beautifulsoup4`, `python-docx`, `PyPDF2`, `PyMuPDF`, `Pillow`, `pytesseract` |
| Local integration | `keyring`, `send2trash`, `windows-toasts` |
| Build | `pyinstaller`; Inno Setup 6 is an external packaging tool |

The packaged application also carries writable private Python and Node runtimes
for dynamic Python tools, Skills, and MCP packages.

## 5. Visible product surfaces and settings inventory

### 5.1 Primary Workspace

- Frameless RTL top-level window, custom titlebar, rounded-corner handling,
  minimum `720 x 560`, normally maximized.
- Central chat with safe Markdown, code blocks, copy/download/read-aloud actions,
  grouped thinking/tool progress, Canvas/file/artifact actions, and mixed RTL/LTR.
- Composer with multiline input, send/cancel/microphone state, model and autonomy
  selectors, plus menu, pending attachment tiles, paste and drag/drop.
- Right conversation drawer with new chat, search, pin, rename, delete, activity,
  unread state, and collapsed/expanded layouts.
- Left `WorkspaceWorkbench`, absent at startup, with repeatable Browser tabs and
  Files, Terminal, Artifacts, and Canvas surfaces. RTL Files place tree right and
  preview left.

### 5.2 Secondary surfaces

- Conversation history/search.
- Settings and management center.
- Workspace and browser preferences.
- Usage/cost statistics.
- Tools and connections: built-ins, custom tools, MCP, Skills.
- Memory management.
- Task Center.
- Smarti Diagnostic/Doctor and approved repairs.
- Developer trace and privacy-aware log view/export.
- About/legal/version/update presentation.
- First-run legal agreement; release notes and update dialogs.

### 5.3 Settings pages

The searchable, autosaving settings UI has five visible groups:

1. **AI models and providers:** API mode, provider/model discovery and selection,
   provider keys/sign-in, reasoning, endpoint/search configuration.
2. **Security and privacy:** autonomy profile, approvals/policy matrix, sandbox,
   allowed paths, upload/file/shell trust, SSL trust/custom CA/legacy mode,
   redaction and personal-data behavior.
3. **Tools and communication:** browser/computer automation, email, MCP, Skills,
   tool catalog/trust and related timeouts.
4. **Voice, appearance, and system:** dark/light/system theme, TTS/voice/hotkey,
   notifications/tray, Workbench/browser preferences, output/download/capture
   paths, and updates.
5. **Advanced and developer:** context budgets/compaction, loop/time limits,
   parallelism, model payload behavior, trace/logs, gateway and compatibility.

The source default schema currently has more than 170 top-level keys in
[`smarti/config.py`](../smarti/config.py). Point 10 must use a Core-owned schema
rather than duplicating this list in React.

## 6. Runtime and control-plane inventory

- `ConversationRunManager` serializes a conversation while allowing independent
  conversations to run concurrently.
- Runs, events, approvals, attention, read receipts, idempotency receipts,
  messages, sessions, and workspaces persist in SQLite.
- Foreground/background runs share the durable event stream; selected provider,
  model, settings, and origin conversation are bound at submission.
- Browser and computer automation are singleton leased resources.
- Approval requests survive asynchronously and are separate from unread state.
- Background tasks support current/new/dedicated conversation routing,
  recurrence, pause/resume/edit/delete, recovery, and notifications.
- The loopback `/v1` gateway uses a token, body limits, idempotent submission,
  session mapping, run state, cancellation, events, approvals, and receipts.
- Provider families include OpenAI, Codex sign-in, Anthropic, Gemini and multiple
  OpenAI-compatible/local providers; secrets use keyring/masked settings paths.
- Seventeen public built-in managers cover schema discovery, system/software,
  files, web, screen, background tasks, notifications, memory, Canvas, email,
  browser/computer automation, documents, extensions, and custom Python tools.
- MCP, Skills, dynamic dependency installation, custom Python tools, private
  Python/Node runtimes, policy, audit, Doctor, context compaction, usage/cost,
  memory capture/retrieval, voice and TTS remain Python responsibilities.

## 7. Browser, Canvas, files, terminal, and Windows behavior

- **Browser:** Windows native Chromium/Edge hosting preserves a Smarti-managed
  visible target and CDP automation. Persistent and Guest profiles are separate;
  profile import is copy-based and user-initiated, and never imports passwords.
  Toolbar/library behavior includes navigation, address/search, find, zoom,
  downloads, screenshots, history, bookmarks, capture/user-agent/device options,
  external open and clear data.
- **Canvas:** validated HTML/image/button artifacts persist with positions and
  conversation context. Remote images are opt-in. The persisted model is still
  coupled to Qt/WebEngine/native rendering and must be split in Point 2/13.
- **Files/artifacts:** scoped Workbench root, RTL tree/preview, text/Markdown,
  images, media, PDF/Office conversion previews, external-open fallback, artifact
  discovery, and safe agent file operations including reparse/path checks.
- **Terminal:** repeatable PowerShell tabs use piped subprocess I/O, working
  directory, input, restart/close, and cleanup. ConPTY is not claimed.
- **Voice/TTS:** global voice hotkey, listening overlay, microphone capture,
  beeps/timeouts/sensitivity, TTS voice/volume and message read-aloud.
- **Windows shell:** single instance, second-launch show/new-chat/voice/update
  routing, tray/close-to-tray/explicit quit, native notifications and activation,
  taskbar unread projection/flash, AUMID, modern manifest, and rounded corners.
- **Updater/install:** GitHub Releases check, semantic version comparison,
  installer-versus-portable asset selection and SHA-256 verification when the
  release digest exists. Current production recipe is PyInstaller `onedir` plus
  per-user Inno Setup, private runtimes, portable ZIP, and `%LOCALAPPDATA%`
  installation. Existing artifacts are not Authenticode-signed.

## 8. Visual baseline

All captures show an empty isolated profile in Hebrew RTL at Windows 125% scale.
They were visually inspected: chat is central, the conversation drawer is on the
right (expanded wide, compact narrow), and the left Workbench is absent until
requested. No clipping was observed in these four states.

| Theme/state | Generated path | PNG bytes |
|---|---|---:|
| Dark narrow `720x560` | `.codex-local/tauri-baseline/legacy-workspace-dark-narrow-720x560.png` | 85,918 |
| Dark wide `1440x900` | `.codex-local/tauri-baseline/legacy-workspace-dark-wide-1440x900.png` | 135,387 |
| Light narrow `720x560` | `.codex-local/tauri-baseline/legacy-workspace-light-narrow-720x560.png` | 60,808 |
| Light wide `1440x900` | `.codex-local/tauri-baseline/legacy-workspace-light-wide-1440x900.png` | 95,752 |

## 9. Stable feature-parity matrix

Statuses used now: `BASELINE-CODE`, `BASELINE-TEST`, `BASELINE-LIVE`,
`BASELINE-VISUAL`, `HISTORICAL-ONLY`, and `UNVERIFIED`. Later migration points
must update the same IDs; Point 17 must resolve every row.

| ID | Feature | Legacy evidence | New point | Final status |
|---|---|---|---:|---|
| SHL-001 | One-click GUI launch without console | `smarti_core.pyw`, `app.py` | 5 | BASELINE-CODE |
| SHL-002 | First-run legal agreement and splash | `legal.py`, `app.py` | 5 | BASELINE-CODE |
| SHL-003 | Central RTL chat surface | `chat.py`, four captures | 7 | BASELINE-VISUAL |
| SHL-004 | Right collapsible conversation drawer | `WorkspaceSidebar`, captures | 7 | BASELINE-VISUAL |
| SHL-005 | Empty-on-start left Workbench | `WorkspaceWorkbench`, workspace tests | 7 | BASELINE-TEST |
| SHL-006 | Narrow/wide responsive Workspace | `ChatWindow`, four captures | 7 | BASELINE-VISUAL |
| SHL-007 | Light/dark/system theme | `ui_styles.py`, settings | 7 | BASELINE-LIVE |
| SHL-008 | RTL with LTR technical islands | `chat.py`, `workspace_ui.py` | 7 | BASELINE-CODE |
| SHL-009 | Custom titlebar/window controls | `WorkspaceWindowTitleBar` | 15 | BASELINE-VISUAL |
| CHT-001 | New conversation and active title | `ChatWindow`, history tests | 8 | BASELINE-TEST |
| CHT-002 | Safe Markdown and links | `MessageBubble`, `CodeBlockWidget` | 8 | BASELINE-CODE |
| CHT-003 | Code copy/download/wrap/scroll | `CodeBlockWidget` | 8 | BASELINE-TEST |
| CHT-004 | Mixed user/assistant RTL alignment | chat RTL tests | 8 | BASELINE-TEST |
| CHT-005 | Tool/thinking progress groups | process-group UI tests | 8 | BASELINE-TEST |
| CHT-006 | Message copy/read-aloud/actions | `ChatMessageContainer` | 9 | BASELINE-CODE |
| CHT-007 | Long history paging and virtualization boundary | `history.py`, `ChatHistoryPage` | 8 | BASELINE-TEST |
| CHT-008 | Model/provider selector | `ChatWindow`, settings | 8 | BASELINE-CODE |
| CMP-001 | Multiline composer and keyboard send | `ChatWindow` | 9 | BASELINE-CODE |
| CMP-002 | Send/cancel/microphone state | composer controls | 9 | BASELINE-VISUAL |
| CMP-003 | Plus/action menu | composer controls | 9 | BASELINE-VISUAL |
| ATT-001 | File picker, drag/drop, paste | `attachments.py`, `chat.py` | 9 | BASELINE-CODE |
| ATT-002 | Pending previews and per-item removal | attachment widgets | 9 | BASELINE-CODE |
| ATT-003 | Sent attachment metadata/provider validation | `attachments.py` | 9 | BASELINE-TEST |
| HIS-001 | Conversation list/search | `ChatHistoryPage`, SQLite search tests | 8 | BASELINE-TEST |
| HIS-002 | Rename/delete/pin | history UI/store | 8 | BASELINE-TEST |
| HIS-003 | Session/message SQLite migration | `history.py`, history tests | 8 | BASELINE-TEST |
| RUN-001 | One run at a time per conversation | `run_manager.py` | 8 | BASELINE-TEST |
| RUN-002 | Independent conversations run concurrently | conversation tests | 8 | BASELINE-TEST |
| RUN-003 | Queue/cancel/interruption/recovery | run manager/history tests | 8 | BASELINE-TEST |
| RUN-004 | Durable ordered events and UI replay | run store tests | 8 | BASELINE-TEST |
| RUN-005 | Run-local provider/model/settings binding | conversation tests | 8 | BASELINE-TEST |
| RUN-006 | Durable attention separate from run state | attention tests | 8 | BASELINE-TEST |
| APR-001 | Durable approval request/resolve/deny | run manager/history | 8 | BASELINE-TEST |
| APR-002 | API-key-required interruption | UI/core callbacks | 9 | BASELINE-CODE |
| GAT-001 | Authenticated loopback `/v1` gateway | `local_gateway.py` | 4 | BASELINE-TEST |
| GAT-002 | Idempotent message submission | gateway tests | 4 | BASELINE-TEST |
| GAT-003 | Sessions/runs/events/cancel/approvals/receipts | gateway routes | 4 | BASELINE-CODE |
| SET-001 | Searchable settings/navigation | `SettingsPage` | 10 | BASELINE-CODE |
| SET-002 | Autosave/default/migration validation | `SettingsManager` | 10 | BASELINE-TEST |
| SET-003 | Provider/model discovery and validation | settings/workers | 10 | BASELINE-CODE |
| SET-004 | Masked secret set/paste/delete | settings/keyring tests | 10 | BASELINE-TEST |
| SET-005 | SSL system/custom/legacy trust modes | `ssl_compat.py`, SSL tests | 10 | BASELINE-TEST |
| SET-006 | Autonomy/policy/sandbox controls | settings/policy engine | 10 | BASELINE-CODE |
| SET-007 | Appearance/voice/notification/update preferences | settings/config | 10 | BASELINE-CODE |
| MGT-001 | Management center navigation | `ManagementCenterPage` | 11 | BASELINE-CODE |
| USE-001 | Usage/cost cached first paint and refresh | usage tests | 11 | BASELINE-TEST |
| MEM-001 | Automatic memory capture/retrieval | managers/memory tests | 11 | BASELINE-TEST |
| MEM-002 | Memory CRUD/filter/archive/restore | `memory_ui.py`, tests | 11 | BASELINE-TEST |
| MEM-003 | Encryption/masking/sensitivity/reveal policy | memory tests | 11 | BASELINE-TEST |
| TSK-001 | Task create/edit/pause/resume/delete | Task Center/scheduler | 11 | BASELINE-TEST |
| TSK-002 | Current/new/dedicated conversation routing | notification policy tests | 11 | BASELINE-TEST |
| TSK-003 | Recurrence, catch-up and recovery | background runtime | 11 | BASELINE-CODE |
| TOL-001 | Built-in tool catalog and lazy schemas | `config.py`, tool calls | 11 | BASELINE-TEST |
| TOL-002 | Custom Python tools | extensions/system tools | 11 | BASELINE-CODE |
| TOL-003 | MCP config/install/trust/private Node | extensions/system tools | 11 | BASELINE-TEST |
| TOL-004 | Skills registry/load/install/trust | extensions/Doctor tests | 11 | BASELINE-TEST |
| DIA-001 | Doctor checks and approved repairs | `doctor.py`, Doctor tests | 11 | BASELINE-TEST |
| DIA-002 | Developer trace and unified logs | trace/log tests | 11 | BASELINE-TEST |
| DIA-003 | Privacy-filtered diagnostic export | logging export tests | 11 | BASELINE-TEST |
| ABT-001 | About/legal/version/runtime state | `AboutPage` | 11 | BASELINE-CODE |
| FIL-001 | Scoped workspace root | `WorkspaceFilePanel` | 12 | BASELINE-CODE |
| FIL-002 | RTL tree right, preview left | workspace UI/tests | 12 | BASELINE-TEST |
| FIL-003 | Text/Markdown/image/media previews | workspace UI | 12 | BASELINE-CODE |
| FIL-004 | PDF/Office rendered previews | workspace/document tools | 12 | BASELINE-TEST |
| FIL-005 | Path/reparse/size/MIME safety | file tools tests | 12 | BASELINE-TEST |
| ART-001 | Artifact discovery/open/refresh | `WorkspaceArtifactsPanel` | 12 | BASELINE-CODE |
| TRM-001 | Multiple PowerShell tabs | `WorkspaceTerminalPanel` | 12 | BASELINE-CODE |
| TRM-002 | Stream/input/restart/cwd/cancel/cleanup | terminal panel/core subprocess | 12 | BASELINE-CODE |
| CAN-001 | Persisted validated Canvas schema | `visual_canvas.py` | 13 | BASELINE-TEST |
| CAN-002 | HTML/image/button rendering and positions | Canvas tests/UI | 13 | BASELINE-TEST |
| CAN-003 | Remote-image opt-in and local materialization | Canvas tests | 13 | BASELINE-TEST |
| CAN-004 | Repeated Canvas tabs/history/context | Canvas/workspace | 13 | BASELINE-TEST |
| BRW-001 | Integrated visible Chromium/Edge surface | native browser/workspace | 6 | BASELINE-CODE |
| BRW-002 | Visible target equals CDP automation target | browser controller contract | 6 | UNVERIFIED |
| BRW-003 | Persistent and Guest profile isolation | browser profile/runtime | 6 | BASELINE-TEST |
| BRW-004 | Copy-based profile import; no passwords | browser profile tests | 14 | BASELINE-TEST |
| BRW-005 | Navigation/address/find/zoom/toolbar | browser panel | 14 | BASELINE-CODE |
| BRW-006 | History/bookmarks/downloads/screenshots | browser panel/controller | 14 | BASELINE-CODE |
| BRW-007 | Device/user-agent/clear/open/preferences | browser panel/controller | 14 | BASELINE-CODE |
| BRW-008 | Repeated Browser tabs and cleanup | Workbench tests | 14 | BASELINE-TEST |
| BRW-009 | Private-host/network policy | browser tests | 14 | BASELINE-TEST |
| VOC-001 | Voice capture/listening overlay/cancel | chat/workers | 9 | BASELINE-CODE |
| VOC-002 | Global voice hotkey | chat/config | 15 | BASELINE-CODE |
| TTS-001 | TTS voice/volume/play/stop/read-aloud | speech/chat/settings | 9 | BASELINE-CODE |
| WIN-001 | Single instance and second-launch routing | `app.py` | 15 | BASELINE-CODE |
| WIN-002 | Tray, close-to-tray, explicit quit | `chat.py` | 15 | BASELINE-CODE |
| WIN-003 | Native notifications and activation routing | Windows notification tests | 15 | BASELINE-TEST |
| WIN-004 | Taskbar unread count/flash/ack semantics | Windows attention tests | 15 | BASELINE-TEST |
| WIN-005 | AUMID/manifest/rounded corners | packaging/Windows tests | 15 | BASELINE-TEST |
| WIN-006 | DPI/multi-monitor window restore | window code | 15 | UNVERIFIED |
| UPD-001 | GitHub update discovery/version selection | updater tests | 16 | BASELINE-TEST |
| UPD-002 | Installer/portable asset selection and digest | updater tests | 16 | BASELINE-TEST |
| PKG-001 | PyInstaller `onedir` GUI application | historical artifacts | 16 | HISTORICAL-ONLY |
| PKG-002 | Writable private Python and Node runtimes | packaging scripts | 16 | HISTORICAL-ONLY |
| PKG-003 | Per-user Inno installer | historical installer | 16 | HISTORICAL-ONLY |
| PKG-004 | Portable ZIP | historical ZIP | 16 | HISTORICAL-ONLY |
| PKG-005 | Clean-machine/install/upgrade/uninstall smoke | not run in Point 1 | 16 | UNVERIFIED |

## 10. Tests and known evidence gaps

### Passed in this baseline

- Focused runtime/history suite:
  `python -m unittest -v tests.test_conversation_runs tests.test_history_sqlite`
  — 18 tests passed in 3.523 s.
- Full suite: `python -m unittest discover -s tests -v` — 357 tests passed
  in 42.540 s.
- Live isolated source construction, four screenshots, startup/memory/CPU
  measurement, and clean runtime shutdown completed.
- Visual inspection passed for light/dark and narrow/wide at 125% DPI.

### Known defects, risks, and unverified claims

- `smarti.core` still imports Qt and the Qt Canvas transitively. This is the
  mandatory Point 2 defect, not an incidental warning.
- A new current-checkout package build and EXE/installer/portable smoke were
  explicitly skipped by the user. Existing artifacts predate the baseline
  commit and are unsigned; current package parity is unverified.
- No clean Windows 10/11 VM install, update, uninstall, or old-install upgrade
  was performed. Those remain Point 16 evidence.
- Screenshots were captured only at 125% display scale. Native browser focus,
  keyboard/IME, hide/show, and 100/150/200% DPI remain the Point 6 gate.
- `BRW-002` (visible browser target exactly equals automated CDP target) is not
  proven by source inspection or unit tests alone.
- The startup/memory sample uses an empty isolated profile and no managed
  browser; it is not representative of a long history or active browser.
- Rust is absent and no Tauri/React code exists, as required before Point 5.
- PyInstaller emitted non-fatal collection warnings for optional LiteLLM
  `fastapi` and platform-specific modules before the build was interrupted.
  They are not classified as product failures without a completed package
  smoke.

## 11. Completion boundary for later points

Point 2 may use this document as its source/parity reference. Package rows must
not be promoted from `HISTORICAL-ONLY` or `UNVERIFIED` until a current artifact
is built and actually exercised. Point 17 must leave no unresolved required ID.
