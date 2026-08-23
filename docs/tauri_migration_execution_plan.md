# SmartiAI Tauri Migration Master Execution Plan

- Status: execution complete through Point 15; Point 16 is next
- Plan version: 1.2
- Plan date: 2026-08-20; browser architecture amended 2026-08-21; exact UI parity amended 2026-08-23
- Repository: `C:\Users\יהודית סיידון\Downloads\GitHub\SmartiAI-Agent-for-Windows`
- Current product target at plan creation: `V0.87.0`

This is the authoritative, standalone handoff for migrating SmartiAI's desktop
interface from PyQt6 to Tauri 2 + React + TypeScript while preserving the Python
agent runtime and the one-click Windows application experience.

Point numbers in this document are stable. Do not renumber existing points. If
the plan later needs an inserted task, add a suffix such as `Point 6A`.

**Binding browser amendment (2026-08-21):** the user explicitly rejected the
legacy technique of launching an installed Chrome/Edge window and reparenting
its HWND into Smarti. The target is now a first-class Smarti Browser: Smarti's
own polished React browser chrome surrounding Tauri-owned child WebViews backed
by WebView2 on Windows. Remote sites must look and behave like content inside a
real browser, not like an external browser window pasted over the application.
Sections 7.3, Point 6, and Point 14 below supersede any older native-Chromium
hosting language in historical handoffs. The supplied visual reference was the
clean Codex-style browser layout: compact tabs, omnibox/navigation, overflow
menu, downloads/history/settings, and a quiet content-first surface.

**Binding exact-UI amendment (2026-08-23):** the user requires the migrated
interface to reproduce the original PyQt interface one-to-one. The authoritative
specification is the legacy source code, not screenshots, subjective visual
similarity, a new component library, or a redesign proposal. For every existing
surface, read and map the actual widget/layout/style/state code and reproduce
its structure, geometry, spacing, typography, colors, assets, text, menus,
shortcuts, visibility rules, states, RTL/LTR behavior, persistence, and
interaction semantics. Screenshots are regression evidence only. This amendment
supersedes every older instruction to "refine", "modernize", "improve the
presentation", or reinterpret an existing UI. Internal React/Rust/Python
implementation may differ, but there may be no undocumented user-visible or
behavioral difference. Truly new surfaces with no PyQt equivalent, including
the explicitly approved built-in Smarti Browser architecture, must reuse the
exact established Smarti visual language unless the user separately approves a
different design.

## 1. Execution trigger for future Codex tasks

When this document is attached or present in the repository and the user says
in Hebrew or English to execute a numbered point, for example:

> עכשיו תבצע את נקודה 1

or:

> Execute Point 1 now

the executing Codex task must:

1. Read this entire document, not only the requested point.
2. Read the applicable `AGENTS.md` and `.codex-local/PROJECT_CONTEXT.md`.
3. Run `git status --short` and preserve all pre-existing user work.
4. Inspect the current checkout before trusting file names or historical line
   numbers in this plan.
5. For every UI-bearing point, read the complete relevant legacy PyQt classes,
   their parent composition, shared style/theme helpers, assets, signal/action
   wiring, responsive code, and persisted settings before changing React. Do
   not implement from screenshots or class names alone.
6. Execute only the requested point and its explicitly listed prerequisites or
   repairs. Do not begin the next point.
7. Do not execute two migration points in parallel.
8. Make reasonable implementation decisions within the point's architecture.
   Ask the user only if a missing choice would materially change product scope.
9. Run all acceptance checks required by the point.
10. Update the Execution Ledger in this file only after the point is genuinely
   complete. Record exact evidence, not a generic "tests passed" statement.
11. End with a self-contained handoff stating: outcome, files changed, tests,
    live/visual/package evidence, known limitations, Git status, and the next
    point number. Do not commit, push, publish, or create a release unless the
    user explicitly authorizes that separate action.

If the checkout has drifted, adapt the implementation to the current code while
preserving the architectural decisions and acceptance criteria in this plan.
Document the drift. Do not blindly restore old code or discard user changes.

## 2. Definition of completion and evidence levels

A point is complete only when its acceptance criteria are met and no required
work remains. Evidence types must remain separate:

- **Static evidence:** imports, compilation, type checks, lint, and diff checks.
- **Unit evidence:** focused deterministic tests.
- **Integration evidence:** communication between Python, Rust, and React or
  between runtime services.
- **Live evidence:** the behavior was exercised against a running application.
- **Visual evidence:** screenshots or direct layout inspection in required RTL,
  light/dark, sizing, and DPI states.
- **Source-parity evidence:** a code-derived map from each legacy PyQt class,
  layout, style rule, asset, signal, and conditional state to its Tauri
  implementation, with every intentional deviation listed and user-approved.
- **Package evidence:** the installed or portable artifact was actually built
  and smoke-tested on a clean machine or VM.
- **Release evidence:** signed artifacts, updater metadata, and upgrade paths
  were tested. A source build is not release evidence.

Never describe an unperformed evidence level as verified. A point that requires
package evidence is not complete because its source tests pass.

## 3. Execution ledger

The executing task for each point must update only its row after verification.
Allowed states are `PENDING`, `IN_PROGRESS`, `BLOCKED`, and `COMPLETE`.

| Point | Short name | Status | Evidence / completion note |
|---:|---|---|---|
| 1 | Baseline and parity inventory | COMPLETE | `docs/tauri_migration_baseline.md`: 97 unique feature IDs; import probe loaded PyQt6 and `smarti.visual_canvas`; focused runtime/history 18/18 and full Python 357/357 passed; isolated live source capture recorded 4.963685 s ready, 203,157,504-byte working set, 5 s idle CPU sample, and visually inspected RTL light/dark 720x560 + 1440x900 screenshots at 125% DPI. A new package build/smoke was explicitly waived by the user on 2026-08-21; only clearly labeled historical V0.87.0 artifact sizes/hashes were recorded. |
| 2 | Pure-Python import boundary | COMPLETE | `smarti.common` is Qt-free; legacy Qt wildcard compatibility moved to `smarti.ui_common`; the persisted Canvas model moved to `smarti.canvas_model` and is shared by Core and the legacy renderer. Fresh-process `import smarti.core` loaded no `PyQt6`, `smarti.visual_canvas`, `smarti.native_browser`, or UI adapter modules. Focused import/runtime/history tests passed 28/28, full Python passed 359/359, `compileall`, `pip check`, and `git diff --check` passed. An isolated live legacy `SmartiCore` + `ChatWindow` opened and rendered RTL light/dark narrow/wide captures at 125% DPI; package validation was not required for this point. |
| 3 | Headless Core service entrypoint | COMPLETE | `smarti_core_service.py` + `SmartiCoreService` provide Qt-free `starting/ready/stopping/stopped/fatal` lifecycle, Core/run-manager/background-scheduler startup, Core event adapters, loopback health, parent-pipe/signal shutdown, and JSON readiness. Deterministic fresh-process smoke created a session, persisted `deterministic:hello`, and stopped cleanly with `qt_loaded=false`; focused runtime/background/recovery tests passed 73/73, full Python passed 363/363, `compileall`, `pip check`, and `git diff --check` passed. Isolated offscreen legacy `ChatWindow` startup remained visible and RTL. No package or visual migration evidence was required. |
| 4 | Versioned HTTP/WebSocket control plane | COMPLETE | Authenticated loopback `aiohttp` `/v2` now covers bootstrap/capabilities/version/health, workspace and conversation CRUD/search, paginated messages, submit/cancel/status/replay/read, approvals, masked settings and explicit secrets/provider models, scoped attachment handles, and cursor-based WebSocket replay while `/v1` remains compatible. `smarti/control_plane_contract.py` generates JSON + TypeScript definitions and `docs/desktop_control_plane_v2.md` summarizes operations. Point-specific gateway tests passed 5/5; focused runtime/history passed 26/26; full Python passed 367/367 on the confirming run, with `compileall`, Qt-free Core import, `pip check`, and `git diff --check` passing. A live isolated headless smoke used a random port/token to create a conversation, hide an attachment path behind a handle, complete `deterministic:hello`, replay 3 missed WebSocket events exactly, resolve an approval, and stop with `qt_loaded=false`. No Tauri UI, visual, package, LAN, cloud, WhatsApp, or shell-API evidence was required or claimed. |
| 5 | Tauri shell and Core supervisor | COMPLETE | `desktop/` contains locked Tauri 2.11.5 + React 19 + TypeScript/Vite sources, an RTL light/dark startup/recovery shell, restrictive CSP, and one minimal capability with no shell/filesystem plugin. The Rust supervisor keeps the random per-launch bearer token outside React, launches source Python or a packaged sidecar without a console, validates readiness identity/health, proxies narrow status/health/restart operations, retains one Core across WebView reload, captures redacted diagnostics, detects crashes, restarts one new generation, and shuts down over the inherited pipe. `scripts/run_tauri_dev.ps1` is the one-command developer entrypoint. Frontend tests passed 8/8, Rust tests 11/11, focused import-boundary tests 3/3, full Python 368/368, `typecheck`, Vite production build, `cargo check`, `compileall`, `pip check`, and `git diff --check` passed. A hidden real-process supervisor smoke proved initial Ready, duplicate prevention, same PID across an actual WebView reload, intentional crash detection, restart to generation 2, Rust-proxied health, and graceful stop. Live Windows Tauri validation showed no Core console; the user supplied a visually inspected light-theme Ready screenshot after using the recovery button, and the earlier live recovery state was also visually inspected. No installer/package evidence is claimed or required at this point. |
| 6 | Built-in Smarti Browser foundation gate | COMPLETE | `desktop/` now hosts a polished RTL React browser chrome around Rust-owned Tauri child WebViews/WebView2; no installed browser HWND or remote-debugging port is used. Stable tab/target/request IDs and the authenticated lifecycle-scoped Core bridge route both user controls and Python `browser_automation_manager` actions to the same visible target. The live gate proved `tab-00000001` = `wv2-target-00000001`, hostile-page Tauri denial, Hebrew input, popup-to-governed-tab routing, persistent reload state, fresh Guest cleanup, focus/resize/hide/show, WebAuthn API availability, and a 13,224-byte screenshot; first-tab latency was 3.702 s in the confirming development run. Light/dark, maximize and real Google rendering were visually inspected, including a live same-target proof. Safe installed-profile probing read copied Chrome/Edge history and bookmarks, skipped protected/locked cookies honestly, exposed no URL/cookie value/password, and recorded absent Brave/Chromium/Vivaldi. Frontend tests, Rust tests, production build, focused Python bridge/import tests, full Python, `compileall`, `pip check`, and `git diff --check` passed on the confirming run. Account-dependent OAuth/passkey registration, every physical DPI/multi-monitor configuration, complete download UX and packaged browser rerun remain explicitly documented for the user matrix/Point 14/16; no unsupported parity claim is made. |
| 7 | Design system and Workspace shell | COMPLETE | The Workspace architecture and browser visibility behavior are implemented. The PyQt `WorkspaceWindowTitleBar`, `WorkspaceSidebar`, `ChatHistoryPage`, top-bar layout, theme constants and responsive behavior are the authoritative specification. The prior source-parity correction restored original assets, dimensions, conversation metadata/cards, 24 px activity indicators, active/approval/unread states, collapsed-logo hover expansion, and conversation/profile menus, and automated checks passed. The new stricter 2026-08-23 one-to-one whole-surface audit is intentionally owned by Point 9A and is not claimed by this original completion row. |
| 8 | Chat vertical slice | COMPLETE | The React client now uses a Rust-owned authenticated `/v2` proxy that keeps the launch token out of WebView JavaScript and rejects non-`/v2`, traversal, remote-URL, and non-HTTP-method requests. The real Workspace covers bootstrap, empty-conversation persistence, search/create/rename/delete, active selection, paginated messages, per-conversation runs/cancellation, provider/model snapshots, durable HTTP event replay after reload/reconnect, semantic run/tool groups, approvals, and relevant-only read receipts. A deterministic fake-Core control-plane workflow covered create/list, scoped attachment, submit-to-completion, model snapshot, replay, approval and TTS without a paid call. Full Python passed 369/369; React state/component tests and Rust proxy tests passed in the combined Point 8/9 confirmation below. A minimal live Tauri run showed the real Core connected with persisted conversations and working chat controls; no paid live-provider request was sent. |
| 9 | Rich messages, composer, attachments, voice | COMPLETE | The user reported Point 9 complete on 2026-08-23. Rich-message, attachment, voice, TTS and cancellation behavior is implemented. The composer was rebuilt from the PyQt `PillInputFrame`, `PinnedActionButtonHost`, `DropdownPillButton`, `_quick_input_button_stylesheet`, and `update_action_btn_visuals` source: 40.5 px pill radius, exact internal margins, 17 px input, 52 px bottom-pinned action control, 42 px attachment control, 10 px control spacing, original gradients, favorite-model visibility rules, and autonomy icon/arrow menus. React tests, production build, focused Core settings behavior and Rust check passed. The new stricter 2026-08-23 one-to-one whole-surface audit is intentionally owned by Point 9A and is not claimed by this original completion row. |
| 9A | Exact legacy-code UI parity gate | COMPLETE | Completed 2026-08-23. `docs/tauri_ui_source_parity.md` is the binding source-derived traceability matrix. The Points 7-9 React/CSS surfaces were corrected against the enclosing PyQt composition and shared helpers, including responsive Workspace ownership, the user-directed approximately 35% wide-screen chat density, race-safe native browser bounds, themed Smarti scrollbars, right-aligned composer/process content, safe internet/local-file links, exact history/activity/message geometry, background-task prompts, message actions outside bubbles, durable/live agent reports and tool loops above the answer with elapsed work time, source assets and dialogs, gapless nested provider/model favorite picker, model reasoning choices, live Codex quota card, voice overlay and approval states. TypeScript, 33 frontend tests, production build, 21 focused Core/control-plane tests, generated-contract equality, 18 Rust tests/check and deliberately minimal focused live Tauri validation passed. Point 10 is next; no packaging or release proof is claimed. |
| 10 | Settings, providers, secrets and connection management | COMPLETE | Completed 2026-08-23. The Tauri management center reads a Core-owned schema generated from `DEFAULT_SETTINGS`, exposes Hebrew groups/search/advanced and restart metadata, provider/model discovery and validation, persisted system/light/dark preference, SSL trust-mode selection and warnings, and explicit secret set/delete controls. `/v2/settings` never returns plaintext secrets; only configured/masked metadata crosses the bridge. Settings updates remain Core-persisted and synchronize model, prompt, extension and SSL runtime state where applicable. The generated `/v2` contract, focused gateway integration and source-parity checks passed. |
| 11 | Tasks, Memory, Tools, Diagnostics, Usage, Logs and About | COMPLETE | Completed 2026-08-23. The profile management center now contains Core-backed task create/edit/cancel/retry/resume/delete flows with once/interval/weekly recurrence and conversation routing; masked memory search/details/explicit reveal/edit/archive/restore/delete; built-in enablement plus Python/MCP/Skill trust/install/refresh; quick/full diagnostics and explicitly confirmed repairs; cached-first usage; privacy-redacted logs by default with opt-in content and export; and version/runtime/About data. Internal RTL dialogs replace generic browser prompts. No paid provider call or per-feature computer-control QA was performed. |
| 12 | Files, Artifacts and Terminal Workbench | COMPLETE | Completed 2026-08-23. The on-demand multi-tab Workbench now supports Files, Artifacts, multiple Terminal sessions and the existing Browser, with duplicate-capable file/browser/terminal tabs. Python Core owns the selected/persisted workspace root, realpath containment, traversal/symlink rejection, depth/size limits, safe text/Markdown preview, image/audio/video/PDF data previews, cached Office-to-PDF conversion, artifact discovery and narrow external-open action. Core-owned hidden PowerShell sessions stream output, accept input, restart/close independently, clean up on gateway shutdown and preserve Hebrew paths through UTF-8. A real loopback integration exercised a Hebrew workspace, Markdown preview, traversal rejection and an actual PowerShell session. Point 13 was not started. |
| 13 | Sandboxed Canvas | COMPLETE | Completed 2026-08-23. The pure Qt-free Canvas model remains authoritative while authenticated conversation-scoped `/v2` routes list, materialize, update, close and reopen persisted artifacts. `CanvasPanel` renders each artifact in a stable Workbench tab through an opaque-origin `sandbox="allow-scripts"` iframe, restrictive per-document CSP, local image materialization, explicit HTTPS remote-image opt-in, bounded/source-validated messaging and a trusted parent confirmation before a Canvas action can enter chat. Active/closed history and layout survive reload; a Canvas error remains isolated. Malicious/CSP frontend fixtures and Core persistence/routes passed, and Canvas enablement no longer probes PyQt/WebEngine. |
| 14 | Full Smarti Browser surface | COMPLETE | Completed 2026-08-23. The Point 6 same-visible-target broker now provides ordered/pinned/duplicate/restored tabs, favicon/loading/audio/crash metadata, full navigation and RTL browser chrome, shortcuts, page commands, per-origin permissions, Smarti-owned persistent history/bookmarks/download history/session restore, strict Guest exclusion/cleanup, privacy controls, safe collision-aware download destinations with dangerous-extension blocking, and a selective detected-profile import wizard for copied history/bookmarks/compatible cookies without password extraction. Inactive WebViews are hidden/frozen, target IDs remain stable, and the support matrix documents WebView2/Tauri/vendor boundaries. A debug NSIS candidate was built; both development and bundled-candidate binary smoke proved the same visible `tab-00000001`/`wv2-target-00000001`, Tauri denial, profile isolation, governed popup, Hebrew input, persistence and screenshot. Clean installation and production sidecar packaging remain Point 16. |
| 15 | Windows desktop integration | COMPLETE | Completed 2026-08-23. Rust/Tauri now owns single-instance activation (`show`, `new-chat`, `voice`, scoped conversation and update shutdown), native tray/close-to-tray/explicit Quit, global voice shortcut lifecycle, WinRT conversation-scoped notification activation without implicit acknowledgement, durable unread taskbar overlay/flash, AUMID, rounded corners and guarded multi-monitor placement restore. Unit tests cover activation routing. A minimal live packaged-candidate check proved a second launch routes and exits, `WM_CLOSE` leaves the primary process alive in tray, `show` routes to it, and `update-shutdown` closes it cleanly with no remaining instance. No exhaustive computer-control, notification click-through or physical DPI/monitor matrix was run per the user's explicit quota-saving direction. |
| 16 | Packaging, updater, and old-install upgrade | PENDING | |
| 17 | Final cutover and PyQt removal | PENDING | |

## 4. Product intent

The migration is not a rewrite of SmartiAI and not a web site placed inside a
desktop window. It is a separation of the existing Python runtime from a new,
modern Windows desktop client.

The product must still feel like one installed application:

- The user launches `SmartiAI` from the Start menu, desktop, or tray.
- No console window is shown.
- The user never starts Python manually and never opens a localhost URL.
- Tauri starts and supervises the Python Core, displays a branded loading or
  recovery state, and shuts the Core down cleanly when the application exits.
- Closing the main window may keep Smarti in the tray according to the existing
  setting; it must not accidentally stop durable background work.
- Existing settings, secrets, history, memory, tasks, workspaces, attachments,
  Smarti-owned browser data, and audit data remain available or are migrated
  through an explicit, verified conversion.
- Smarti Browser is part of the application. It does not launch or visually
  embed the user's installed Chrome, Edge, Brave, or another top-level browser.

The Tauri migration is a framework/architecture migration, not a UI redesign.
The existing PyQt code is the authoritative visual, structural, behavioral, and
interaction specification. The final user must encounter the same interface:
component hierarchy, placement, dimensions, minimum/maximum sizes, stretch and
alignment behavior, margins, spacing, typography, palette, borders, radii,
gradients, shadows, icons, labels, tooltips, menus, indicators, animations,
focus/hover/pressed/disabled states, responsive transitions, shortcuts,
selection rules, and persisted UI choices. React may implement these details
differently internally, but must not reinterpret them. A screenshot can show
one state at one size; it cannot replace reading the code that produces all
states and sizes.

Where Qt and Web rendering differ, match the declared source values and the
resulting layout as closely as the platform permits, measure the remaining
difference, and record it. Any user-visible exception—however reasonable it may
seem—requires explicit user approval. Do not quietly substitute a “more modern”
control, icon family, spacing system, animation, card layout, or responsive
behavior. Security and accessibility fixes remain required, but should preserve
the original presentation unless a visible change is unavoidable and approved.

## 5. Non-negotiable product invariants

### 5.1 Workspace composition

- The chat remains the central, primary surface.
- The conversation drawer is on the right and can collapse.
- The left Workbench starts empty and opens only when Browser, Canvas, Files,
  Terminal, or Artifacts are needed.
- Opening a workbench surface must not replace or hide the chat by default.
- In RTL file views, the file tree remains on the right and the preview remains
  on the left.
- Settings, Tasks, Memory, Tools, Usage, Logs, Diagnostics, and About remain
  secondary management surfaces rather than permanent workbench panels.
- The same application must adapt between a relatively compact window and a
  wide Workspace without becoming a separate product mode.

### 5.2 Runtime and capability invariants

- Python remains authoritative for the agent loop, model providers, tools,
  policy, approvals, MCP, Skills, background tasks, memory, history, settings,
  secrets, browser-automation policy/action contracts, and Windows computer
  automation. Rust may execute narrow browser-host operations for Python
  through the authenticated browser broker; that does not transfer policy or
  tool authority to React.
- New foreground and background runs enter through
  `ConversationRunManager`; do not reintroduce GUI-owned agent execution.
- One conversation is serialized; independent conversations may run
  independently. Singleton browser and desktop-control resources remain leased.
- Durable execution state and unread-attention state remain separate.
- Approval requests remain durable and can be resolved asynchronously.
- Future WhatsApp or other channel adapters must authenticate external
  requests, map identities, and pass through normal Smarti policy and approval.
  They must never call tools directly.
- Interactive browser and desktop automation must stay in the logged-in user
  session. Do not put the complete interactive app into a Windows Service.

### 5.3 Security invariants

- The React WebView is untrusted presentation code, not the authority to run
  shell commands or access arbitrary files.
- React receives no general shell permission and no broad filesystem scope.
- Secrets are never returned in settings snapshots. The UI receives masked
  metadata and explicit set/delete/reveal operations where supported.
- The desktop bridge binds only to `127.0.0.1`, uses a random port and
  per-launch secret, and rejects unauthorized origins and tokens.
- A future stable local-control token is a separate credential and audience
  from the per-launch desktop token.
- Canvas content is untrusted, sandboxed, isolated from Tauri APIs, and allowed
  to communicate only through a validated message schema.
- Local files displayed in the WebView use scoped handles or narrowly scoped
  asset routes, not an unrestricted local file server.
- Existing browser persistent and guest profiles remain explicitly separate.
- Arbitrary remote pages run in dedicated child WebViews with no Tauri command
  capability, desktop credential, host object, general filesystem access, or
  direct Core access. Browser chrome and remote content are separate trust
  domains even though they appear as one product.
- Production browser automation must not leave a stable, unauthenticated CDP
  endpoint exposed. Prefer in-process WebView2 CDP calls through the Rust
  broker. If a loopback debugging endpoint is required for Playwright, Point 6
  must make it random, lifecycle-scoped, inaccessible to remote hosts, and
  explicitly document the residual same-user risk.

### 5.4 Windows and installation invariants

- Initial parity target: supported x64 Windows 10 1803+ and Windows 11.
- ARM64 is a later, separately validated build target. Do not claim Windows 7,
  32-bit, or ARM64 support without their own artifacts and tests.
- Installation is per-user and does not require an administrator by default.
- Packaged Smarti retains private Python and Node runtimes for custom Python
  tools, Skill dependencies, and MCP packages.
- The UI development Node toolchain is not a runtime prerequisite for users.
- Existing application data paths are preserved. Smarti-owned legacy browser
  data is migrated safely into the new WebView2/Smarti data model; third-party
  source profiles are copied/read only after explicit consent and are never
  opened for in-place control or modified.
- Update signing and Windows Authenticode signing are separate requirements.

## 6. Current repository context at plan creation

Always revalidate this section before acting; it is a map, not a substitute for
the current checkout.

### 6.1 Runtime

- `smarti/core.py` is the compatibility facade composing `SmartiCore` from
  mixins in `smarti/agent/`.
- `smarti/agent/lifecycle.py` owns runtime initialization, run-local state,
  `ConversationRunManager`, and local-gateway startup.
- `smarti/run_manager.py` owns per-conversation queues, durable events,
  cancellation, and approvals.
- `smarti/history.py` owns the SQLite ledger for sessions, messages,
  workspaces, runs, events, approvals, attention, receipts, and idempotency.
- `smarti/local_gateway.py` provides an authenticated loopback HTTP `/v1` API.
- `docs/conversation_runtime_architecture.md` describes the current durable run
  contract.

### 6.2 Current Qt coupling that must be removed

- `smarti/agent/shared.py` imports `smarti/common.py`, managers, history,
  attachments, browser control, and `smarti/visual_canvas.py`.
- `smarti/common.py` imports PyQt widgets, core types, and graphics globally.
- `smarti/visual_canvas.py` mixes the pure persisted Canvas model with Qt
  widgets, WebEngine compatibility, native hosting, and HTTP bridging.
- Importing `smarti.core` currently loads PyQt6 and `smarti.visual_canvas`.
- `smarti/workers.py`, `smarti/updater.py`, and notification/UI modules contain
  useful non-UI behavior wrapped in `QThread`, signals, or widgets.
- At plan creation, directly UI-related modules total roughly 25,000 lines.
  This is an effort indicator only; the new UI must not copy all of that code.

### 6.3 Current desktop and Workbench

- `smarti/app.py` creates `QApplication`, legal/splash flow, single-instance
  handling, `SmartiCore`, and `ChatWindow`.
- `smarti/chat.py` owns the top-level window, chat, conversation history,
  message widgets, tray, voice overlay, run-event projection, and page routing.
- `smarti/workspace_ui.py` owns files, browser controls, terminal, artifacts,
  the left Workbench, and management-center composition.
- `smarti/ui_pages.py`, `smarti/memory_ui.py`, `smarti/ui_controls.py`, and
  `smarti/ui_styles.py` own management pages and shared Qt presentation.
- `smarti/windows_notifications.py` owns Windows toasts and taskbar attention.

### 6.4 Browser and Canvas

- On Windows, `smarti/native_browser.py` launches an installed Chromium/Edge
  app-mode window, reparents its native HWND into Qt, and preserves a loopback
  CDP endpoint. This accurately describes the legacy compatibility client, but
  it is explicitly rejected as the Tauri target by the 2026-08-21 amendment.
- `smarti/browser_control.py` uses Playwright/CDP structured actions against
  that same persistent profile and visible target. Preserve its user-visible
  action capabilities and Python policy contract, not its current host process.
- `smarti/browser_profile.py` provides copy-based, user-initiated import of
  compatible cookies, history, and bookmarks; passwords are never imported.
- Persistent Smarti and temporary guest profiles have different lifecycle and
  privacy requirements.
- The new browser must not require an installed Chrome/Edge executable. It uses
  the supported WebView2 Runtime and Smarti-owned profiles. History/bookmarks
  may be imported into Smarti's own browser library; compatible decryptable
  cookies may be added to the Smarti profile through WebView2's cookie API.
- Canvas artifacts persist validated HTML, images, buttons, positions, and
  context metadata. Their data model is reusable; their Qt renderer is not.

### 6.5 Packaging

- `packaging/smarti.spec` builds the current PyQt app with PyInstaller `onedir`.
- `packaging/smarti.iss` builds the current per-user Inno Setup installer.
- `scripts/build_release.ps1` prepares the app, private runtimes, portable ZIP,
  and installer.
- `scripts/prepare_runtime.ps1` installs a private Python runtime and a private
  Node runtime.
- `smarti/runtime.py` resolves source, frozen, runtime, resource, and data paths.
- `requirements.txt` currently includes PyQt6 and PyQt6-WebEngine in addition
  to Core/tool dependencies.

## 7. Target architecture

```text
SmartiAI.exe (Tauri 2 desktop process)
|
+-- React + TypeScript WebView
|   +-- central chat and composer
|   +-- right conversation drawer
|   +-- left on-demand Workbench
|   +-- management center
|   +-- Smarti Browser chrome, tabs, libraries, and settings
|   +-- design system, motion, RTL, light/dark
|
+-- Rust trusted desktop host
|   +-- window, tray, single instance, taskbar, notifications
|   +-- Core process supervisor and authenticated proxy
|   +-- updater, file dialogs, safe native opening
|   +-- WebView2 browser broker, profiles, downloads, and CDP bridge
|   +-- isolated Tauri child WebViews for remote browser content
|
+-- smarti-core.exe (headless Python sidecar)
    +-- SmartiCore and ConversationRunManager
    +-- models, tools, policy, MCP, Skills, memory, tasks
    +-- SQLite, settings, secrets, logs, diagnostics
    +-- browser/desktop automation and resource leases
    +-- versioned HTTP snapshots and WebSocket event stream
```

### 7.1 Process ownership

Tauri is the parent and user-facing process. It starts the Core with a random
loopback port and per-launch token, waits for an explicit readiness handshake,
and displays loading, retry, repair, or crash information without exposing a
console. It terminates or preserves the Core according to explicit tray/exit
semantics, never because the WebView merely reloads.

### 7.2 Communication

- HTTP is used for bootstrap, snapshots, paginated resources, and commands.
- WebSocket is used for run events, approvals, attention changes, diagnostics,
  terminal output, and future model deltas.
- Durable run events retain sequence identifiers so a client can reconnect and
  replay missed events without duplication.
- Rust holds the desktop credential and exposes narrow Tauri commands/events to
  React. Do not store the credential in LocalStorage, IndexedDB, or a frontend
  bundle.
- The existing `/v1` local gateway remains compatible while a versioned `/v2`
  desktop contract is introduced.

### 7.3 Browser decision

Build a first-class Smarti Browser; do not port the legacy installed-browser
HWND reparenting layer. The browser has two deliberately separated layers:

1. The main trusted React WebView renders Smarti-owned browser chrome: tabs,
   navigation, omnibox, menus, history, bookmarks, downloads, permissions, and
   settings.
2. Each remote page is rendered in a Tauri-owned child `Webview` positioned in
   the browser content viewport. On Windows this is an embedded WebView2
   control, not the user's Chrome/Edge window and not an iframe inside the
   trusted Smarti document.

Tauri 2 exposes child WebViews as a stable public API, including creation,
bounds, focus, visibility, zoom, cookies, and browsing-data clearing. The
current scaffold resolves Tauri 2.11.x, whose Rust `with_webview` hook also
provides the platform WebView2 handle. Pin at least the Tauri minor version when
using that platform hook, because its underlying WebView2 bindings may change
in Tauri minor releases.

Rust owns child-WebView lifecycle, popup/tab routing, profile selection,
downloads, permissions, and the narrow automation bridge. Python continues to
own the public browser tool, policy, leases, approvals, and structured action
contract. Point 6 must prove one production transport to the *same visible
WebView2 target*: preferably WebView2's in-process DevTools Protocol methods and
events through Rust; a random lifecycle-scoped loopback CDP connection for
Playwright is acceptable only if its security and packaging behavior are
measured and documented. Functional compatibility matters more than retaining
Playwright as an internal implementation detail.

Use a durable Smarti WebView2 profile for normal browsing and a separate
InPrivate/ephemeral profile or user-data directory for Guest. Never attach the
new browser to a third-party profile in place. Profile import is an explicit
copy/read/convert operation with a category-by-category result report.

Point 6 remains a mandatory gate because WebView2 intentionally differs from a
full Microsoft Edge product: vendor account sync, extensions, favorites UI,
some built-in browser features, and some embedded OAuth flows are unavailable.
The required result is a complete everyday Smarti browser like the supplied
Codex-style reference, not a false claim of bit-for-bit Edge/Chrome parity. If
a user-critical login or capability cannot work in WebView2, compare a truly
embedded CEF-class engine against size, security, maintenance, automation, and
simple-install requirements. Reparenting an external Chrome window is not an
allowed fallback.

### 7.4 Canvas decision

Split Canvas into a pure Python artifact model and a React renderer. Render each
artifact in a sandboxed iframe with a restrictive CSP. Canvas button/layout
messages cross the iframe boundary using validated `postMessage` payloads. The
iframe receives no Tauri object, desktop credential, shell permission, or broad
network access. Remote images remain opt-in.

### 7.5 Packaging decision

- Use a Tauri NSIS per-user installer for the final desktop application.
- Package the Python Core as a PyInstaller `onedir` sidecar. Avoid `onefile`
  extraction and antivirus/startup costs.
- Bundle the existing private Python and Node runtimes as application resources.
- Use the system Evergreen WebView2 with an embedded bootstrapper for the main
  online installer. Produce an offline-WebView2 installer only as a separate
  release artifact if required.
- Preserve current data directories and create an explicit upgrade path from
  the old Inno Setup installation identity.

## 8. Design direction

The target is an exact migration of the original interface, not a visual
reinterpretation. “Design system” in this plan means a faithful encoding of the
existing PyQt design constants and rules in web technology.

- Derive CSS custom properties from the actual values and conditional branches
  in `smarti/ui_styles.py`, `smarti/ui_controls.py`, `smarti/chat.py`,
  `smarti/workspace_ui.py`, `smarti/ui_pages.py`, `smarti/memory_ui.py`, and the
  relevant feature modules. Do not invent a replacement scale for color,
  typography, spacing, radii, shadows, blur, motion, or density.
- Reuse the original tracked icons and visual assets when technically suitable.
  If an asset must be converted to a web-compatible representation, preserve
  its shape, stroke, fill, viewbox, visual size, theme variant, and state logic.
- Reproduce the original widget/layout tree semantically: parent-child
  ownership, insertion order, direction, alignment, stretch factors, fixed and
  minimum dimensions, margins, spacing, clipping, scrolling, stacking, and
  show/hide rules. A flattened React DOM is acceptable only if it behaves and
  renders identically.
- Reproduce the complete state machine from code: empty/loading/error/running,
  hover/focus/pressed/disabled, active/inactive/unread/approval, expanded/
  collapsed, send/cancel, menu-open, attachment, voice/TTS, and persistence.
- Maintain the source light and dark themes exactly. A system-theme option may
  select between them but must not create a third unapproved theme.
- Component libraries may provide invisible accessibility/focus mechanics, but
  their default visuals, spacing, animation, portals, direction assumptions,
  and typography must not leak into the final interface.
- Do not add Mica, Acrylic, glass, glow, new gradients, new cards, new motion,
  changed corner radii, or different iconography unless that exact treatment is
  present in the PyQt source or explicitly approved later.
- Respect `prefers-reduced-motion` and accessibility requirements by suppressing
  or adapting motion without altering the normal-motion source-parity target.
- Chat Markdown must not enable arbitrary raw HTML. Code blocks need copy,
  wrapping/scroll behavior, direction handling, and lazy syntax highlighting.
- Hebrew user-facing text remains natural and polished. Paths, code, terminal,
  URLs, model IDs, and technical values remain LTR inside the RTL shell.
- Smarti Browser follows the supplied Codex-style visual intent: compact tabs,
  one calm toolbar/omnibox row, restrained borders and elevation, a spacious
  content surface, and a polished overflow menu. It must feel authored as part
  of Smarti in both themes, not like browser chrome from another application.
  This is an explicit new-surface exception because the rejected legacy HWND
  browser is not the design target; all surrounding Workspace integration must
  still match the original PyQt source exactly.

## 9. Cross-cutting acceptance matrix

Every relevant point must validate the subset it changes.

### 9.1 Source-code UI parity

- Before implementation, create or update a code-derived mapping that names the
  legacy PyQt classes/functions/constants/assets/settings and the corresponding
  React/CSS/Rust implementation. The mapping must cover conditional and dynamic
  paths, not only the default constructor state.
- Inspect the relevant source directly. Screenshots, memories, prior summaries,
  and the Point 1 baseline are supporting evidence and regression fixtures, not
  substitutes for the code.
- Preserve exact user-visible values and behaviors. At each required window
  size/theme/DPI, compare hierarchy, geometry, alignment, wrapping, clipping,
  scroll behavior, visibility, state transitions, menus, tooltips, keyboard and
  pointer behavior, and persisted state.
- Automated source-parity tests should assert stable design values, conditional
  state behavior, DOM/component roles, and representative geometry. Visual
  comparisons must exercise equivalent source and Tauri states.
- Toolkit font rasterization or native-control differences do not excuse layout
  drift. Match source-declared values first; measure any unavoidable rendered
  difference and list it for explicit user acceptance.
- Completion means zero undocumented differences. “Similar”, “recognizable”,
  “cleaner”, “more polished”, or “better for web” is not acceptance evidence.

### 9.2 Layout and visual states

- Light and dark themes.
- RTL shell and mixed RTL/LTR content.
- Minimum supported window near the current `720 x 560` constraint.
- Typical `1180 x 760` and wide/maximized Workspace.
- Windows display scale 100%, 125%, 150%, and 200% for native surfaces.
- Empty, loading, populated, error, offline/Core-crashed, approval, and running
  states.
- Reduced motion and keyboard-only navigation.

### 9.3 Runtime states

- No conversation, new conversation, long history, and paginated history.
- One run, queued runs, independent conversations, cancellation, restart
  interruption, waiting approval, denial, approval, timeout, and unread result.
- Core starts slowly, Core fails startup, Core crashes, WebView reloads, and
  desktop exits while work is active.
- Browser/computer singleton leases under concurrent conversations.
- Multiple browser tabs, popup-to-tab routing, persistent restart, Guest
  cleanup, a crashed content process, failed navigation, certificate/auth
  prompts, permission requests, uploads/downloads, and agent/user contention
  over the active tab.

### 9.4 Security states

- Unauthorized local request, wrong origin/token, replayed idempotency key,
  oversized body, malformed schema, path traversal, symlink/reparse escape,
  Canvas XSS, unsafe URL, and secret masking.
- Frontend code must not be able to invoke arbitrary shell or read arbitrary
  user files through Tauri.

### 9.5 Performance

Point 1 establishes measured baselines. Later points must report total memory
across Tauri, Core, and active WebView2 browser processes, startup-to-ready
time, idle CPU, chat render time for a long conversation, and first-action
latency where relevant.
A regression above 20% against the accepted baseline requires an explanation
and explicit acceptance; do not hide it by measuring only one process.

## 10. Global verification commands

Use the narrowest meaningful checks while implementing, then the full required
set for point completion. Adapt paths only if the implementation deliberately
changes them.

```powershell
python -m compileall -q smarti smarti_core.pyw sitecustomize.py
python -m unittest discover -s tests
python -m pip check
git diff --check
git status --short
```

After `desktop/` exists, expected frontend/Rust checks are:

```powershell
npm --prefix desktop test
npm --prefix desktop run typecheck
npm --prefix desktop run build
cargo check --manifest-path desktop/src-tauri/Cargo.toml
cargo test --manifest-path desktop/src-tauri/Cargo.toml
```

Point 5 must provide one repository-owned PowerShell command for running the
Tauri development app with its Python Core. Point 16 must provide one
repository-owned PowerShell command for producing the complete Windows release.
Do not make the user manually coordinate multiple terminals.

## 11. Execution points

The binding exact-UI amendment and Section 9.1 are inherited acceptance
criteria for every point that creates, migrates, or changes user-visible UI,
even when the individual point does not repeat them. Points 10-13 and 15 must
extend `docs/tauri_ui_source_parity.md` before implementation. Point 14 follows
the separately approved Smarti Browser visual exception while matching its
legacy Workspace placement, visibility, sizing, theme integration and commands.
Point 17 cannot delete the PyQt reference until every later UI surface has been
audited against the source.

### Point 1 - Establish the migration baseline and parity inventory

**Depends on:** Nothing. This is the mandatory starting point.

**Objective**

Create a reproducible baseline of the current PyQt product before changing its
architecture. This is the comparison target and the guard against silently
losing capabilities.

**Required work**

1. Revalidate current branch, dirty state, release version, Python/runtime
   versions, disk capacity, and available packaging tools.
2. Run the focused runtime/history tests and the full Python suite.
3. Record an import probe showing that `import smarti.core` currently loads
   PyQt6 and `smarti.visual_canvas`.
4. Create `docs/tauri_migration_baseline.md` containing:
   - exact commit and dirty-state boundary;
   - current module and dependency map;
   - all visible product surfaces and settings pages;
   - runtime/control-plane features;
   - browser, Canvas, files, terminal, voice/TTS, tray, notification, updater,
     packaging, and installation behavior;
   - known current defects and unverified claims;
   - measurable startup, memory, idle CPU, and artifact-size baselines.
5. Create a feature-parity table with a stable identifier for every feature and
   columns for legacy evidence, new implementation point, and final status.
6. Capture representative current screenshots in light/dark and narrow/wide
   RTL states. Store only useful, reasonably sized QA images in a dedicated
   ignored or documented QA location; do not add large binary noise to Git.
7. Build the current release and smoke-test its EXE and installer/portable
   artifacts on the current machine. Do not publish them. If packaging is
   blocked, exhaust in-scope fixes and mark the point `BLOCKED` with the exact
   blocker; do not pretend a source run is an equivalent baseline.

**Acceptance**

- Baseline and parity documents are complete and link to current code.
- Full tests and package smoke evidence are recorded separately.
- The current installer artifact path, size, and hash are recorded.
- No intentional product behavior is changed.

**User check**

Open the supplied baseline screenshots and the temporary baseline build. Verify
that the documented Workspace layout matches the Smarti you currently know and
that no major screen or capability is missing from the parity table.

**Out of scope**

No Tauri scaffolding and no Core refactor.

### Point 2 - Create a pure-Python Core import boundary

**Depends on:** Point 1 complete.

**Objective**

Make the Python runtime importable without loading PyQt or any UI renderer while
keeping the legacy PyQt application functional.

**Required work**

1. Split `smarti/common.py` responsibilities into a pure Core/runtime layer and
   a Qt UI layer. Prefer explicit imports in new code and reduce wildcard import
   coupling rather than copying the monolith.
2. Move constants, paths, standard-library imports, runtime resolution, network
   helpers, secret helpers, and shared non-UI utilities to the pure layer.
3. Keep Qt widgets, graphics, signals, palettes, icons, and UI helpers in the UI
   layer.
4. Split the pure Canvas artifact validation/context/materialization model from
   the Qt Canvas renderer and native host.
5. Ensure `smarti/agent/shared.py`, `smarti/core.py`, `smarti/history.py`,
   `smarti/run_manager.py`, `smarti/local_gateway.py`, `smarti/attachments.py`,
   and runtime managers do not import Qt directly or transitively.
6. Add import-boundary tests that fail if any `PyQt6` module or Qt Canvas/UI
   module appears in `sys.modules` after importing `smarti.core`.
7. Keep `python smarti_core.pyw` and existing PyQt tests working.

**Acceptance**

```powershell
python -c "import sys, smarti.core; assert not any(k == 'PyQt6' or k.startswith('PyQt6.') for k in sys.modules)"
```

passes in a fresh process, the full Python suite passes, and the legacy source
application still opens. PyQt remains installed during the transition.

**User check**

Open the legacy Smarti application and send one harmless message. Confirm that
the old UI still starts and that chat/history are intact.

**Out of scope**

No new server process, Tauri shell, or UI redesign.

### Point 3 - Add the headless Smarti Core service entrypoint

**Depends on:** Point 2 complete.

**Objective**

Run SmartiCore as a lifecycle-controlled, UI-independent user-session process
that can later be supervised by Tauri.

**Required work**

1. Add a focused headless entrypoint/module separate from `smarti_core.pyw`.
2. Provide explicit startup, ready, health, shutdown, and fatal-startup states.
3. Start `SmartiCore`, `ConversationRunManager`, background scheduler, and the
   control plane without creating QApplication, windows, tray icons, or dialogs.
4. Replace any required `QThread` or signal dependency in Core-owned behavior
   with standard threads, futures, asyncio, or callbacks. Qt worker adapters may
   remain for the legacy UI.
5. Ensure API-key requests, approvals, notification intents, voice/TTS status,
   and browser-activation requests are represented as Core events or service
   operations, never synchronous GUI assumptions.
6. Add graceful shutdown and restart recovery tests. A Core crash must leave
   durable run state consistent with the existing interruption contract.
7. Add a development smoke command that starts the service without a console UI
   dependency and reports a machine-readable readiness handshake.

**Acceptance**

- The headless service starts and answers health in a fresh process without Qt.
- It can create a session, submit a deterministic/fake-provider run, persist the
  result, and shut down cleanly.
- Background and restart-recovery tests pass.
- Legacy PyQt startup still works.

**User check**

No normal user-facing check is required yet. Review the final report for a live
headless smoke result and confirmation that no window or console interaction was
needed to control the service.

**Out of scope**

No Tauri application and no remote Internet exposure.

### Point 4 - Implement the versioned desktop control plane

**Depends on:** Point 3 complete.

**Objective**

Provide the complete, typed UI-to-Core contract required by the future desktop
client while keeping the existing `/v1` gateway compatible.

**Required work**

1. Introduce a versioned `/v2` contract. Prefer the already-installed
   `aiohttp` stack for HTTP and WebSocket rather than adding a large web
   framework without need.
2. Define validated request/response/event schemas and a durable contract
   document. Generate or maintain TypeScript-compatible definitions from one
   authoritative schema source.
3. Provide at least:
   - bootstrap, capabilities, health, and version;
   - workspace and conversation CRUD/list/search;
   - paginated messages and history projection;
   - run submit, cancel, status, event replay, and attention/read receipts;
   - pending approval list and resolve;
   - safe settings schema, masked values, patch, secret set/delete, provider
     validation, and model discovery;
   - attachment registration and scoped file handles;
   - event subscription over authenticated WebSocket.
4. Preserve `/v1` behavior and tests for future local/WhatsApp integrations.
5. Use a random port and per-launch desktop token supplied by the supervisor.
   Preserve a separate opt-in stable local-control credential if currently
   enabled.
6. Add origin/auth, body-size, pagination, validation, idempotency, reconnect,
   replay, ordering, slow-client, disconnect, and secret-leak tests.
7. Correlate every command and event with request ID, session ID, and run ID
   where applicable so diagnostics can cross Python/Rust/React boundaries.

**Acceptance**

A non-UI integration client can perform a complete conversation lifecycle,
disconnect, reconnect using its last sequence, receive exactly the missed
events, resolve an approval, and never receive a plaintext stored secret.

**User check**

Review the generated API summary. You should be able to identify plain-language
operations for send, cancel, approve, conversations, settings, and attachments.
No browser window is expected yet.

**Out of scope**

No LAN binding, cloud endpoint, WhatsApp implementation, or arbitrary remote
shell API.

### Point 5 - Create the Tauri shell and supervise the Python Core

**Depends on:** Point 4 complete.

**Objective**

Create the first real Tauri 2 + React + TypeScript desktop application and make
it launch the headless Core as one product.

**Required work**

1. Create `desktop/` with Tauri 2, React, TypeScript, Vite, locked npm and Cargo
   dependencies, and repository-owned development/build scripts.
2. Build a minimal RTL application shell with branded startup, connecting,
   ready, Core-crashed, retry, and repair states.
3. Implement a Rust Core supervisor for development Python and packaged sidecar
   modes. It owns the per-launch token, port, readiness handshake, process
   handle, stderr/log capture, restart, and shutdown.
4. Proxy narrow Core operations/events through Rust. React must not receive the
   Core bearer token.
5. Configure a restrictive CSP and minimal Tauri capabilities. Do not grant
   generic shell execution or whole-home filesystem access.
6. Implement development hot reload without killing an active Core merely
   because the WebView reloads.
7. Add one PowerShell developer command that prepares/runs both sides and emits
   clear failure diagnostics.
8. Add unit/integration tests for handshake, slow startup, invalid handshake,
   crash, restart, duplicate Core, WebView reload, and graceful exit.

**Acceptance**

Double-clicking or using one repository command opens one Tauri window, starts
one Core without a visible console, reports ready, calls health through the Rust
bridge, survives a frontend reload, and presents a useful recovery screen after
an intentionally terminated Core.

**User check**

Open the Tauri development build using the one command supplied by Codex. You
should see a polished Smarti loading screen followed by a simple connected shell;
no console or localhost address should be part of the product interaction.

**Out of scope**

No complete chat, Workbench, embedded browser, tray, or installer yet.

### Point 6 - Prove the built-in Smarti Browser foundation

**Depends on:** Point 5 complete.  
**This is a mandatory go/no-go gate. Do not start Point 7 if Point 6 is blocked.**

**Objective**

Prove a real, polished, built-in Smarti Browser foundation using Tauri child
WebViews/WebView2. The prototype must look like one browser product, accept
normal user browsing, and expose the same visible page to Smarti automation.
It must not launch, strip, reparent, overlay, or visually embed an installed
Chrome/Edge/Brave window.

**Required work**

1. Create a focused React prototype based on the supplied visual intent:
   compact tab strip and new-tab control, back/forward/reload, LTR omnibox,
   security/loading state, overflow menu, and an intentionally quiet content
   surface. Validate both Smarti themes and Hebrew RTL surrounding layout.
2. Create remote content as one or more Tauri child `Webview` instances backed
   by WebView2. Rust must own create/close, bounds, focus, visibility, z-order,
   navigation, popup-to-tab routing, and process-failure recovery. Do not use a
   remote iframe in the trusted Smarti WebView.
3. Give remote-content WebViews zero general Tauri capabilities. Prove that a
   hostile test page cannot invoke Smarti commands, read the desktop token,
   access arbitrary local files, or impersonate the trusted browser chrome.
4. Implement a narrow Rust browser broker shared by the React chrome and the
   Python Core. Define stable tab/profile/target IDs and request IDs so user and
   agent actions address exactly the same visible page without relying on page
   index races.
5. Select and prove the automation transport:
   - prefer WebView2 `CallDevToolsProtocolMethod` and protocol events through
     Rust with Python retaining the structured browser action contract; or
   - if Playwright over remote CDP is materially more capable, use a random,
     loopback-only, lifecycle-scoped endpoint and document same-user exposure,
     discovery, authentication limitations, cleanup, and packaged behavior.
   Preserve at least snapshot/semantic refs, navigate, click, type/fill/press,
   scroll, select, hover, upload, download, screenshot/PDF, console, network,
   storage/cookies, evaluate, and raw-CDP capability or a documented equivalent.
6. Prove a durable Smarti profile and an isolated Guest/InPrivate profile.
   Normal cookies, permissions, local storage, cache, autofill preferences, and
   session state persist only in the normal profile; Guest data is removed on
   close and is never merged into normal browsing.
7. Build an import feasibility spike against copied test profiles from Chrome,
   Edge, Brave, Chromium, and Vivaldi where installed:
   - import history and bookmarks into Smarti's own searchable browser library;
   - import cookies into the Smarti WebView2 profile only when they can be
     decrypted by supported current-user mechanisms and accepted by the
     WebView2 cookie manager;
   - never write to, lock, launch automation against, or browse in the source
     profile;
   - do not bypass Chrome App-Bound Encryption and do not silently extract or
     import saved passwords;
   - produce a safe report with selected source/category, imported/skipped/
     failed counts and reasons, without logging cookie values or sensitive URLs.
8. Exercise navigation, tabs, popups, keyboard shortcuts, Hebrew input/IME,
   mouse, clipboard, find, zoom, print, permissions, downloads/uploads,
   screenshots, clear-data, minimize/restore/maximize, Workbench hide/show,
   multi-monitor movement, and display scale 100%, 125%, 150%, and 200%.
9. Test representative real sites and login classes, including a site using
   passkeys/WebAuthn where available and an OAuth flow. Record WebView2/vendor
   limitations explicitly. If a user-critical flow is blocked, evaluate a
   truly embedded engine before accepting the architecture; never fall back to
   an externally reparented browser window.
10. Record startup/first-tab latency, total WebView2 process memory, inactive
    tab behavior, crash recovery, and installer impact. Add focused Rust,
    TypeScript, Python contract/security tests and a repeatable manual QA script.

**Acceptance**

- The result looks and behaves like a coherent built-in browser, not a patched
  external window. It works on a machine with WebView2 Runtime but no installed
  Chrome/Edge browser executable selected as a host.
- User controls and Smarti automation navigate and inspect exactly the same
  visible target, with stable tab/target ownership and the required structured
  action coverage.
- Persistent and guest profiles are demonstrably separate.
- Focus, Hebrew IME, resize, DPI, minimize/restore, hide/show, downloads,
  popups, and process recovery are reliable.
- The import spike demonstrates history/bookmark import and reports cookie
  compatibility honestly. Encryption-protected cookies being skipped is an
  expected documented limitation, not permission to weaken or bypass security.
- Remote pages have no Smarti/Tauri authority, and no production-stable CDP
  port or secret browser data is exposed.
- A browser feature/compatibility matrix identifies required, implemented,
  deferred-to-Point-14, unsupported-by-WebView2, and blocked items. No critical
  daily-browsing or Smarti-automation requirement is silently omitted.

If this cannot be made reliable, mark Point 6 `BLOCKED`, present measured
alternatives and tradeoffs, and stop. Do not silently downgrade the requirement
or continue building the remaining interface. A truly embedded alternative may
be proposed; the legacy external-Chrome HWND technique may not be proposed as
the final design.

**User check**

Open the prototype and browse it as you would the reference: create/switch/close
tabs, enter a URL, type Hebrew into a real site, use back/reload/find/zoom/menu,
download a harmless file, resize/maximize Smarti, and collapse/reopen the
Workbench. Then ask Smarti to act on that same visible page. Restart normal mode
and confirm its state persists; repeat in Guest and confirm it does not. Run the
test-profile import and inspect the category counts. At no point should an
installed Chrome/Edge window appear, flash, overlap Smarti, or show foreign
browser chrome.

**Out of scope**

The prototype need not yet contain the final history/bookmark/download manager,
complete import wizard, final settings pages, or production-perfect styling;
those belong to Point 14. No vendor account sync, extension ecosystem, automatic
password extraction/import, or claim of exact Edge/Chrome feature parity.

### Point 7 - Build the design system and final Workspace shell

**Depends on:** Point 6 complete.

**Objective**

Encode and reproduce the exact existing PyQt visual language and responsive
Workspace composition before moving feature-heavy screens. This point does not
authorize a new Tauri-specific look.

**Required work**

1. Extract semantic tokens for both themes from the actual PyQt constants,
   palettes, stylesheets, widget initialization and conditional styling:
   background, surface hierarchy, glass, border, text, muted text, accent,
   success, warning, danger, focus, code, radii, spacing, shadow, blur, motion,
   density, and typography. Record the source symbol for every value.
2. Build accessible base components that reproduce the corresponding PyQt
   controls exactly: buttons, icon buttons, fields, textarea, menus, tooltips,
   dialogs, sheets/drawers, tabs, scroll areas, badges, skeletons, alerts,
   cards, resizers, empty states, and focus management. Do not accept library
   defaults as the Smarti design.
3. Implement the permanent composition:
   - central chat column;
   - collapsible right conversation drawer;
   - empty/collapsed left Workbench that hosts dynamic tabs;
   - top/window controls and management navigation;
   - compact and wide responsive rules.
4. Preserve RTL placement while applying LTR islands for code, paths, URLs,
   model IDs, and terminal text.
5. Add theme persistence, system-theme option, reduced motion, keyboard
   navigation, and contrast tests.
6. Read the corresponding PyQt widget/layout/style implementations, produce
   light/dark screenshots at the required sizes, and compare both structure and
   visual details with the Point 1 baseline. Screenshots alone are not an
   adequate design specification.

**Acceptance**

Component tests, type checks, Rust checks, and visual QA pass. The Tauri shell
matches the original PyQt Workspace, including its collapsed/expanded sidebar,
top controls, menus, activity indicators, composer geometry and responsive
states. The left area is truly empty until requested.

**User check**

Review the supplied light/dark narrow/wide screenshots alongside the matching
PyQt source components. Confirm the chat is central, conversations are on the
right, the Workbench is on the left and empty by default, and controls retain
the original Smarti geometry and behavior.

**Out of scope**

No full production feature pages; mock content is acceptable only inside
isolated component previews.

### Point 8 - Deliver the real chat vertical slice

**Depends on:** Point 7 complete.

**Objective**

Make the Tauri app useful for a complete real conversation while preserving the
durable runtime model.

**Required work**

1. Connect bootstrap, workspaces, conversation list/search/create/rename/delete,
   paginated messages, attention state, and active conversation selection.
2. Render user/assistant messages with safe Markdown, mixed direction, code
   blocks, copy actions, timestamps/metadata where appropriate, and long-history
   virtualization or measured pagination.
3. Implement send, queued/running state, cancel, session switching during runs,
   independent conversation activity, final response, failure, interruption,
   and reconnect/replay.
4. Render semantic run steps and tool start/finish groups from Core events.
5. Implement durable approval UI for active and background conversations,
   including risk level, allow/deny, notification marker, and reconnection.
6. Implement model/provider selection using Core-owned values. Do not duplicate
   provider truth in the frontend.
7. Preserve the current rule that visible reading clears only the relevant
   conversation's attention.
8. Add fake-provider deterministic E2E coverage plus one live configured-provider
   smoke if credentials are already available. Never require paid calls for the
   deterministic test suite.

**Acceptance**

A user can keep one conversation running, switch to another, start independent
work, return, resolve an approval, cancel one run without cancelling another,
restart/reconnect, and see accurate durable history and attention.

**User check**

Run two harmless conversations, switch between them while one is active, cancel
only one, and verify the other completes. Trigger a safe approval flow and check
that approve/deny works and the unread marker clears only when viewed.

**Out of scope**

No attachment composer, voice, full management center, or Workbench content.

### Point 9 - Migrate rich messages, composer, attachments, voice, and TTS

**Depends on:** Point 8 complete.

**Objective**

Reach exact source-code-derived daily chat/composer parity without redesigning
or “improving” its presentation.

**Required work**

1. Reconstruct the final responsive composer from its PyQt classes, layout
   constants, stylesheets and update functions: multiline input, exact geometry
   and nesting, send/cancel state, keyboard behavior, action menu, model
   indicator, drag/drop, paste, and file picker.
2. Preserve pending attachment previews, per-item removal, sent attachment
   metadata, image/media thumbnails, provider capability validation, and local
   paths/handles without exposing unrestricted filesystem access.
3. Complete rich message actions: copy, code copy, read aloud, retry where
   supported, artifact/file open, and accessible tool detail expansion.
4. Migrate voice capture/listening/cancel/status behavior and TTS playback/state.
   Core-owned audio services must not depend on Qt; WebView media permissions
   must be minimal if browser capture is used.
5. Preserve API-key-required and permission-required interruption behavior as
   durable service requests, not blocking calls from the Core thread.
6. Test large files, unsupported types, cancelled selection, pasted images,
   Hebrew filenames, long RTL prompts, long code, and active-run composer states.

**Acceptance**

The full chat/composer workflow works with keyboard, mouse, drag/drop, paste,
attachments, voice, TTS, tool cards, and mixed RTL/LTR content. Its appearance,
geometry, responsive behavior, menus, icons and state transitions match the
authoritative PyQt source with zero undocumented differences. Secret and file
boundaries remain enforced.

**User check**

Attach a Hebrew-named text file and an image, remove one before sending, paste an
image, send the request, copy a code block, and try voice/TTS. Confirm the UI is
clear in both themes and no permission prompt is hidden behind the window.

**Out of scope**

No Settings or Workbench file browser implementation.

### Point 9A - Audit and correct exact legacy-code UI parity

**Depends on:** The functional implementation of Points 7, 8, and 9.
**This is a mandatory parity gate. Do not start Point 10 until Point 9A is complete.**

**Objective**

Apply the binding 2026-08-23 requirement retroactively to every user-visible
surface already migrated in Points 7-9. Prove that the Workspace shell,
conversation drawer, chat, rich messages, composer, attachments, approvals,
activity/tool states, voice and TTS reproduce the original PyQt interface from
code one-to-one, rather than merely resembling selected screenshots.

**Required work**

1. Create `docs/tauri_ui_source_parity.md` as the durable source-derived UI
   specification and traceability matrix. For every migrated component, record:
   - legacy module, class/function, relevant constants and shared style helpers;
   - parent/child hierarchy and ordering;
   - layout direction, alignment, stretch, margins, spacing, fixed/min/max size;
   - font, palette, border, radius, gradient, shadow, icon/asset and text;
   - visibility/enabled rules and every interactive state;
   - signal/action/menu/shortcut behavior and persisted settings;
   - matching React component, CSS/token/test and current parity status.
2. Read the complete relevant legacy paths, including the enclosing composition
   and shared helpers—not only isolated class definitions. At minimum cover
   `smarti/app.py`, `smarti/chat.py`, `smarti/workspace_ui.py`,
   `smarti/ui_controls.py`, `smarti/ui_styles.py`, and the legacy modules used
   by messages, approvals, attachments, voice/TTS and history.
3. Audit the current Tauri implementation against the matrix. Remove redesign
   residue, generic web-library defaults, guessed values, screenshot-only
   approximations, substituted assets, altered text, extra cards/motion/effects,
   and simplified or missing states.
4. Correct the Tauri Workspace, drawer, message timeline, composer and shared
   primitives until source values and behaviors match. Preserve the approved
   Tauri process/security architecture; parity concerns presentation and user
   interaction, not reintroducing Qt ownership into Core.
5. Exercise every code-controlled state: empty/populated/long history, collapsed
   and expanded drawer, active/inactive/unread/running/approval conversations,
   user/assistant/system/tool/error messages, code/Markdown/mixed direction,
   idle/sending/cancelling composer, attachments, model/autonomy menus,
   responsive narrow/wide transitions, voice/listening/TTS and disabled/error
   states.
6. Add deterministic parity tests for extracted design values, visibility/state
   rules, menus/shortcuts, direction, responsive thresholds and representative
   rendered geometry. Use legacy offscreen/runtime captures and Tauri captures
   of equivalent states in light/dark at minimum, typical and wide sizes.
7. Produce a deviation ledger. The point cannot complete while it contains an
   unapproved user-visible difference. A toolkit-imposed difference must include
   measurements, technical cause, attempted remedies and explicit user approval.

**Acceptance**

- `docs/tauri_ui_source_parity.md` covers every Points 7-9 surface and links
  both sides of the implementation.
- Every row is `MATCHED` or carries explicit user-approved deviation evidence;
  no row is merely “visually similar”.
- Source-value/state tests, frontend tests, type checks, Rust checks, relevant
  Python tests and equivalent-state visual QA pass.
- The original PyQt app remains runnable for comparison through Point 16.
- No screenshot was treated as the sole specification for a dynamic component.

**User check**

Open the legacy PyQt and Tauri applications side by side in the same theme and
window size. Compare the title/top controls, drawer expanded and collapsed,
conversation cards/states, chat messages/tool groups, composer states and
menus. Repeat in the other theme and a narrow/wide size. Navigation, hover,
clicks, keyboard shortcuts, send/cancel, attachments and voice/TTS should feel
and appear the same. Review every entry in the deviation ledger; Point 9A is not
complete until you approve any listed visible exception.

**Out of scope**

No Settings, management-center, Workbench file/terminal, Canvas, final Browser,
Windows integration or packaging implementation. Point 9A may establish shared
parity primitives required by those later points.

### Point 10 - Migrate Settings, providers, secrets, and connection management

**Depends on:** Point 9A complete.

**Objective**

Move configuration to a schema-driven management UI without leaking secrets or
duplicating runtime validation rules.

**Required work**

1. Implement Settings navigation and search with human-readable Hebrew groups.
2. Migrate provider/API mode, model discovery/selection, connection validation,
   API-key-required flow, endpoint settings, and provider-specific guidance.
3. Migrate secret fields with masked status, paste/set, delete, explicit reveal
   only where policy permits, and no plaintext values in frontend logs/state.
4. Migrate SSL trust modes, custom certificate import/validation, explicit
   legacy-insecure compatibility, and clear warnings.
5. Migrate appearance, language/direction, voice/TTS, notifications, browser,
   workspace, autonomy/policy, attachment, context, cost, and update preferences
   that currently exist.
6. Use Core-provided setting schemas, validation errors, defaults, and restart
   requirements. Do not hard-code a second settings model in React.
7. Test migrations from existing user settings and unknown/legacy fields.

**Acceptance**

Every current user-facing setting appears in the parity matrix as migrated,
intentionally retired with justification, or deferred to a later named point.
Changing a setting updates Core behavior and survives restart. No plaintext
secret enters serialized frontend state or logs.

**User check**

Switch light/dark/system theme, change a harmless preference, restart Smarti,
and confirm it persists. Inspect provider and SSL screens in Hebrew and verify
secret fields show status without revealing stored values.

**Out of scope**

No task/memory/tool/diagnostic content beyond links or empty management routes.

### Point 11 - Migrate Tasks, Memory, Tools, Diagnostics, Usage, Logs, and About

**Depends on:** Point 10 complete.

**Objective**

Complete the secondary management center while keeping business/runtime logic in
Python.

**Required work**

1. Migrate Task Center, including current/new/dedicated conversation routing,
   recurrence, edits, pause/resume, deletion, run status, and responsive cards.
2. Migrate Memory management, filters, details, edit/delete, sensitivity cues,
   masking/reveal behavior, and compact RTL cards without confusing UI CRUD with
   automatic capture/retrieval proof.
3. Migrate built-in/custom tools, Skills, MCP configuration/status/install
   operations, extension refresh, and trust warnings.
4. Migrate diagnostics/Doctor, repair approval, progress, results, and exact log
   location. Keep repair operations Core-owned and policy-gated.
5. Migrate usage/cost data with cached first paint and asynchronous refresh.
6. Migrate developer trace and privacy-aware log viewing/export. Personal-content
   filtering remains on by default while provider/category/code/retry/request-ID
   details remain useful.
7. Migrate About, legal information, version, dependency/runtime status, update
   notice presentation, and relevant help links.
8. Add responsive, long-content, empty/loading/error, and light/dark tests.

**Acceptance**

The complete management-center parity section is resolved, long cards do not
clip, all writes go through validated Core operations, and privacy defaults are
preserved.

**User check**

Open each management section in Hebrew. Create a harmless one-time task, view a
memory without revealing sensitive data, inspect Tools and Diagnostics, and
export a filtered diagnostic log. Confirm nothing clips in a narrower window.

**Out of scope**

No Files/Terminal/Canvas/Browser Workbench implementation.

### Point 12 - Migrate Files, Artifacts, and Terminal Workbench surfaces

**Depends on:** Point 11 complete.

**Objective**

Deliver secure, on-demand non-browser Workbench productivity surfaces.

**Required work**

1. Implement dynamic Workbench tab lifecycle and resizable chat/workbench
   composition. The Workbench remains absent until opened.
2. Implement scoped workspace-root selection and persistence through Core.
3. Implement an RTL file tree on the right and preview on the left for:
   - text/code with size limits and direction handling;
   - safe Markdown;
   - images;
   - audio/video;
   - PDF and Office page previews using existing conversion capabilities;
   - unknown types with safe external-open fallback.
4. Use Core-scoped file handles/routes with root, path traversal, reparse-point,
   size, MIME, and lifetime checks. Do not grant React the user's whole home.
5. Implement Artifacts discovery/open/refresh and connection from chat results.
6. Implement multiple PowerShell terminal tabs with Core-owned subprocess
   sessions, streamed output, input, restart, working directory, cancellation,
   and cleanup. Match the current piped-shell capability first; ConPTY is an
   optional later enhancement, not a reason to lose current parity.
7. Test Hebrew paths, long paths, inaccessible files, symlinks/reparse points,
   large files, binary files, failed conversions, process exit, and app shutdown.

**Acceptance**

Files, previews, artifacts, and multiple terminal tabs work without broad Tauri
filesystem or shell capabilities. Closing tabs and exiting Smarti release all
processes and scoped handles.

**User check**

Choose a test folder with Hebrew names, open text/Markdown/image/PDF files,
confirm the tree is on the right, run `Get-Location` in two terminal tabs, close
one, and verify the other remains active.

**Out of scope**

No Canvas renderer and no final Browser product surface.

### Point 13 - Migrate Canvas to a sandboxed React renderer

**Depends on:** Point 12 complete.

**Objective**

Preserve Canvas artifacts and interaction while removing Qt/WebEngine coupling
and improving security and presentation.

**Required work**

1. Use the pure Canvas model extracted in Point 2 as the authoritative validator
   and persisted format. Preserve schema migration and conversation context.
2. Render Canvas in a stable Workbench tab using a sandboxed iframe and
   restrictive document CSP.
3. Materialize images without duplicating large data in history. Preserve
   opt-in HTTPS remote-image behavior and local data-image size limits.
4. Implement validated parent/iframe messaging for button positions, button
   actions, content-ready, errors, resizing, and future safe interaction.
5. Prevent access to Tauri APIs, desktop tokens, local files, parent DOM,
   arbitrary navigation, popups, and non-approved network requests.
6. Preserve active/closed Canvas history, reload, context injection, artifacts,
   theme presentation where appropriate, and failure isolation.
7. Add malicious HTML/JS, CSP, postMessage spoof, oversized payload, remote
   image, history reload, and visual tests.

**Acceptance**

Existing Canvas fixtures/artifacts render and interact correctly, malicious
fixtures cannot access the desktop bridge or local files, and a Canvas failure
cannot crash or replace the main Smarti UI.

**User check**

Create/open a Canvas with buttons and an image, switch tabs, restart Smarti, and
confirm it reloads. Check that links/popups or unexpected local-file access are
blocked and that closing Canvas does not resize the whole application.

**Out of scope**

No final Smarti Browser toolbar/library.

### Point 14 - Complete the Smarti Browser product surface

**Depends on:** Points 6 and 13 complete.

**Objective**

Turn the proven Tauri/WebView2 foundation into a polished, secure, browser-class
Smarti Browser that is comfortable for normal user browsing and for agent
automation. Its existing PyQt Smarti Browser surface is the visual baseline;
new browser capabilities must extend that RTL design without replacing the
application with an unrelated visual language.

**Required work**

1. Complete the tab model and chrome: new/close/duplicate/reorder/pin/restore,
   tab titles/favicons/loading/audio/crash state, back/forward/reload/stop/home,
   LTR address/search omnibox, security/error state, keyboard shortcuts, focus
   order, and responsive behavior in the RTL Workspace.
2. Complete everyday browser commands and menus: find in page, zoom, print,
   screenshot, save/capture where supported, copy/share address, view source or
   DevTools behind an explicit developer setting, open externally, user agent,
   device mode, and per-site permissions.
3. Build Smarti-owned searchable history and bookmark libraries plus session/
   recently-closed restoration. Record navigation from all Smarti Browser tabs
   without leaking private Guest entries into the persistent library.
4. Build the download manager: safe destination selection, progress, pause/
   resume/cancel where WebView2 supports it, collision handling, open/show in
   folder, dangerous-file policy, completed/failed history, and cleanup.
5. Complete persistent/Guest profile controls, privacy explanation, permission
   review, cookie/site-data controls, cache/history/autofill/password-autosave
   clearing, and complete Guest cleanup. Password autosave inside the new Smarti
   profile may be offered as an explicit setting; Smarti must never read or
   display stored password values.
6. Implement the user-initiated import wizard for detected Chrome, Edge, Brave,
   Chromium, and Vivaldi profiles. Let the user choose source profile and
   history/bookmarks/cookies separately, copy source databases before reading,
   never modify the source, show imported/skipped/failed counts and reasons,
   and support retry. Add history/bookmarks to Smarti's library and compatible
   decryptable cookies through WebView2's cookie manager. Do not bypass
   application-bound encryption; blocked sessions require normal sign-in inside
   Smarti. Do not claim password import.
7. Handle window.open/popups as governed tabs, JavaScript dialogs, basic auth,
   certificates, client certificates where required, camera/microphone/
   clipboard/location/notification permissions, downloads/uploads, fullscreen,
   PDF viewing/printing, media, renderer crashes, offline and network errors.
8. Support multiple concurrent Browser tabs with resource-aware suspension or
   unloading of inactive tabs, predictable restore, stable target ownership,
   profile isolation, and correct cleanup. Do not create an unbounded WebView2
   process/memory leak.
9. Preserve the complete public `browser_automation_manager` contract. Python
   continues to authorize, lease, and audit actions; the Rust broker executes
   them against the selected visible WebView2 tab. User activity, agent activity,
   takeover/focus, cancellation, and sensitive upload/permission approvals must
   be understandable and race-safe.
10. Publish a browser support matrix in repository documentation. Clearly label
    WebView2/vendor limitations such as browser extensions, vendor profile sync,
    Edge/Chrome internal settings pages, built-in collections/translation/
    immersive-reader features, and embedded OAuth restrictions. Implement a
    Smarti-owned equivalent only when it is a required accepted feature; never
    present an absent vendor feature as working.
11. Run the complete Point 6 security, profile/import, site compatibility,
    DPI/focus/keyboard/automation/performance matrix again on the final UI and
    in a packaged candidate, not only the prototype.

**Acceptance**

Every required Browser item in the parity/support matrices is resolved, the
visible user-controlled and automated target is the same, normal daily browsing
is credible, profile privacy boundaries are intact, and package-level browser
smoke passes. The product has no dependency on reparenting an installed browser
window and makes no unsupported claim of full Edge/Chrome vendor parity.

**User check**

Use Smarti Browser for a representative normal session: several tabs, search and
direct URLs, a login, back/forward, find, zoom, print/PDF, media, permissions,
upload and download. Restart persistent mode and verify tabs/session/history;
repeat in Guest and verify no private state persists. Import a test profile and
confirm the report and searchable history/bookmarks, while accepting that some
encrypted cookies may require signing in again. Finally ask Smarti to inspect
and act on the exact visible page and confirm that no external browser appears.

**Out of scope**

No control of a third-party browser profile in place, no automatic password
extraction/import, no Chrome/Edge extension store, and no vendor-account profile
sync unless separately designed and explicitly approved.

### Point 15 - Complete Windows desktop integration

**Depends on:** Point 14 complete.

**Objective**

Restore the native Windows behaviors that make Smarti one desktop application
rather than a localhost client, matching the legacy user-visible controls,
settings and interaction rules exactly. Architecture-only changes may improve
reliability, but must not silently redesign the interface.

**Required work**

1. Implement single-instance behavior and route second-launch commands such as
   show, new chat, voice, notification activation, and update shutdown.
2. Implement Tray icon/menu, close-to-tray, explicit Quit, restore/front, and
   durable-background-work behavior.
3. Migrate global voice hotkey and its settings/cleanup.
4. Implement native notifications for responses, background tasks, approvals,
   reminders, and supported reply/activation actions. Activation opens the
   correct conversation and does not acknowledge unrelated notifications.
5. Project durable unread count onto taskbar attention/badge and preserve
   flash/acknowledgement semantics.
6. Implement window effects, rounded corners, titlebar/drag regions, taskbar
   identity/AUMID, DPI awareness, multi-monitor restore, and accessible native
   fallbacks.
7. Ensure native behavior is owned by Rust/Tauri or a narrowly justified
   user-session component, not by Qt.

**Acceptance**

Single instance, tray, close/quit, hotkey, notifications, activation routing,
taskbar count, window effects, DPI, and multi-monitor tests pass live. No
background run is accidentally acknowledged or terminated.

**User check**

Close Smarti to the tray during a harmless run, restore it, launch Smarti again,
trigger the voice hotkey, and click a notification for a non-active
conversation. Confirm only one app exists and the correct conversation opens.

**Out of scope**

No final installer/updater migration or PyQt deletion.

### Point 16 - Build the production package, updater, and old-install migration

**Depends on:** Point 15 complete.

**Objective**

Deliver a simple, supportable Windows installation and update path containing
Tauri, the headless Core, and Smarti's private runtimes.

**Required work**

1. Split dependency sets so final Core/private runtime installs no PyQt or
   PyQt-WebEngine unless the temporary legacy fallback package explicitly needs
   them.
2. Build the Core as PyInstaller `onedir` sidecar and include all dynamic imports,
   assets, certificates, browser-broker/automation helpers, and runtime path
   behavior required by packaged operation. Bundle Playwright browser machinery
   only if Point 6 selected it as part of the production WebView2 transport.
3. Bundle private Python and Node runtimes with pinned versions and checksums,
   retaining writable user caches and Skill/MCP dependency behavior.
4. Produce a Tauri NSIS per-user installer and portable ZIP. Configure WebView2
   embedded bootstrapper for the primary installer and an optional separate
   offline installer if required.
5. Preserve data paths, AUMID/identity, shortcuts, protocol behavior, settings,
   and Smarti-owned browser data. Implement a one-time, backed-up migration from
   the legacy native-Chromium Smarti profile into the new Smarti library/
   WebView2 profile where compatible; never point WebView2 at the old profile
   in place. Implement and test detection/removal/upgrade from the old Inno
   Setup installation without deleting user data.
6. Integrate the Tauri updater with mandatory update signatures, GitHub/static
   metadata, safe restart, and rollback/error UX. Treat update signing separately
   from Windows Authenticode signing.
7. Provide one `scripts/` PowerShell release command that builds all required
   layers, validates version synchronization, checks layout/path budgets, and
   writes hashes/manifests.
8. Test clean install, upgrade from current PyQt installer, in-place Tauri
   update, cancelled update, corrupted/signature-invalid update, portable mode,
   uninstall, and reinstall.
9. Smoke on clean x64 Windows 10 and Windows 11 VMs without developer Python,
   Node, Rust, npm, repository files, or an installed Chrome/Edge browser host;
   exercise both WebView2-present and WebView2-missing installation paths.

**Acceptance**

Exact installer and portable artifact paths, sizes, SHA-256 hashes, signature
status, VM matrix, startup/browser/chat/tool smoke, upgrade result, and remaining
limitations are recorded. No artifact may be called signed if Authenticode was
not actually applied and verified.

**User check**

On a disposable Windows account or VM, install over the old Smarti version,
launch from the Start menu, confirm history/settings remain, run a harmless chat
and browser action, close/reopen, and uninstall. There must be no console or
manual runtime setup.

**Out of scope**

No publication to GitHub Releases unless explicitly authorized.

### Point 17 - Final cutover, parity audit, and PyQt removal

**Depends on:** Point 16 complete.

**Objective**

Make Tauri the only production UI, remove transition debt, and prove the final
release without losing Smarti capabilities.

**Required work**

1. Audit every stable feature ID from Point 1. Resolve each as implemented,
   intentionally changed with user acceptance, or explicitly unsupported with a
   blocker. No silent omissions.
2. Re-audit every row in `docs/tauri_ui_source_parity.md` against the final
   legacy source before deleting it. Resolve later-point Settings, management,
   Workbench, Canvas and Windows surfaces with the same code-derived standard;
   zero undocumented user-visible differences may remain.
3. Make Tauri the default source and packaged launcher.
4. Remove legacy PyQt UI modules, Qt adapters, WebEngine compatibility paths,
   PyQt requirements, PyInstaller UI entrypoint, Inno-only packaging, dead
   assets, and transition feature flags that are no longer needed.
5. Preserve pure Python behavior extracted from former UI modules and ensure no
   Core import/runtime path loads Qt.
6. Update README, architecture, contributor setup, tests, packaging docs,
   screenshots, troubleshooting, and release notes to the final product.
7. Run full Python, frontend, Rust, integration, security, source-parity,
   visual, browser,
   package, clean-install, and upgrade suites again after deletion.
8. Compare final performance and artifact metrics to Point 1 and document every
   meaningful improvement or regression.
9. Produce the final release candidate and a complete evidence-backed handoff.
   Do not publish without explicit user authorization.

**Acceptance**

- The parity matrix has no unresolved required feature.
- The source-parity matrix has no unmatched or unapproved visible/behavioral
  difference from the final legacy PyQt source.
- No production dependency or import of PyQt remains.
- Source, installed, portable, browser, update, and old-install upgrade tests
  pass with exact evidence.
- Smarti still launches as one simple Windows application.
- The repository contains no accidental generated build artifacts or stale
  transition code.

**User check**

Use the final installer as an ordinary user. Verify the complete daily flow:
launch, chat, parallel conversation, approval, attachment, settings, task,
memory, files, terminal, Canvas, Browser automation, notification/tray, restart,
and update check. Compare the final screenshots and experience with Point 1 and
the matching legacy source application. Confirm that the migrated interface is
one-to-one in structure, geometry, styling, states and interaction—not merely
familiar or subjectively more polished.

**Out of scope**

Publishing the release candidate, creating a public release, or beginning new
post-migration product features without a separate explicit request.

## 12. Failure and rollback rules

1. Keep the legacy PyQt client working through Point 16. Do not delete it early
   to make a test pass.
2. Use additive database migrations with backups/transactions where applicable.
   Never make a schema change that prevents the currently released Smarti from
   reading data without an explicit compatibility decision.
3. Do not share one mutable provider/session state across runs to simplify the
   bridge. Preserve run-local binding.
4. Do not replace durable approvals with modal-only React dialogs.
5. Do not expose Python tools as direct Tauri commands. All agent and remote
   actions pass through Core policy.
6. Do not port, preserve, or revive the legacy technique of reparenting an
   installed Chrome/Edge/Brave window into Smarti. Point 6 requires a true
   Tauri-owned WebView2 browser surface. An external browser may be offered only
   as an explicit one-off "Open externally" command, never as Smarti Browser.
7. If a point reveals that a later point's assumptions are invalid, update this
   plan with an added stable subpoint and explanation; do not renumber or
   silently broaden the active point.
8. If tests fail for apparently unrelated reasons, reproduce them in isolation
   and against the pre-point state before attributing or ignoring them.
9. Never use source/offscreen tests to claim installer, WebView2 child-WebView,
   profile import, cookie compatibility, DPI, notification, updater, or
   packaged browser success.
10. Never treat screenshots as the authoritative UI specification. Do not
    replace reading the relevant PyQt code with image matching, a remembered
    description, or subjective design judgment. Do not accept an unapproved
    visible deviation because it looks newer, cleaner, or easier to implement
    in React.

## 13. Required handoff format after every point

The final response for a point must use this information, in Hebrew unless a
technical identifier requires English:

```text
Point N: COMPLETE | BLOCKED

Outcome:
- What is now true.

Changed:
- Exact files and architectural effects.

Verification:
- Static checks.
- Focused tests with counts.
- Full tests with counts.
- Source-parity map/tests and deviation status for UI-bearing points.
- Live validation.
- Visual validation.
- Package validation.

User verification:
- 2-6 simple steps the user can perform.
- What success looks like.

Limitations / unverified:
- Explicit evidence boundaries and blockers.

Repository state:
- Branch/commit.
- `git status --short` summary.
- Commit/push status.

Next:
- The next allowed point number, but do not execute it.
```

## 14. Hebrew operator guide for the user

### איך לפתוח כל משימה

1. פתח משימה חדשה באותו פרויקט מקומי של SmartiAI ובאותה תיקיית repository.
2. ודא שאינך יוצר Worktree מקביל. הנקודות מבוצעות לפי הסדר באותו checkout.
3. צרף את המסמך הזה, או ודא שהוא קיים ב־`docs/` בגרסה המעודכנת.
4. כתוב רק: `עכשיו תבצע את נקודה N`.
5. אל תפתח את נקודה N+1 לפני שהמשימה הקודמת דיווחה `COMPLETE` ועדכנה את טבלת
   ה־Execution Ledger במסמך.
6. לאחר נקודה 9 יש לבצע את נקודה 9A, ורק אחריה את נקודה 10. בנקודות ממשק ודא
   שהדיווח כולל השוואה לקוד PyQt המקורי ולא רק לצילומי מסך.

### מה לבדוק בסיום

- חפש בתחילת התשובה `Point N: COMPLETE`. אם כתוב `BLOCKED`, אל תתקדם.
- ודא שמופיעים שמות הבדיקות ומספר הבדיקות, ולא רק המשפט "הכול עבר".
- ודא שמופרד במפורש מה נבדק בקוד, מה נבדק חי, מה נבדק חזותית ומה נבדק
  במתקין.
- בצע את סעיף `User check` של הנקודה. אם משהו אינו תואם, המשך באותה שיחה ובקש
  לתקן; אל תפתח עדיין את הנקודה הבאה.
- אם הכול תקין, פתח משימה חדשה לנקודה הבאה.

### שמירת שינויים בין משימות

המשימות חייבות לעבוד באותה תיקייה מקומית כדי שהשינויים מנקודה קודמת יהיו
זמינים לנקודה הבאה. המסמך אינו מחליף את קבצי הקוד עצמם. אין צורך לבצע commit
אחרי כל נקודה כדי להמשיך באותו checkout, אך commit מקומי לאחר נקודה מאומתת הוא
checkpoint שימושי אם תבקש אותו במפורש. אל תבקש push או release אלא כאשר אתה
באמת רוצה לפרסם.

### אם קודקס מבקש החלטה

ברוב המקרים המסמך והקוד אמורים להספיק. אם נשאלת שאלה שמשנה מוצר, אבטחה, תמיכה
בגרסאות Windows או ויתור על יכולת קיימת, אל תנחש. עצור ובקש הסבר בעברית לפני
אישור. שאלות טכניות פנימיות שאינן משנות את התוצאה אמורות להיפתר על ידי קודקס.

## 15. References

Repository references:

- `.codex-local/PROJECT_CONTEXT.md`
- `docs/architecture.md`
- `docs/conversation_runtime_architecture.md`
- `smarti/core.py`
- `smarti/agent/shared.py`
- `smarti/agent/lifecycle.py`
- `smarti/run_manager.py`
- `smarti/history.py`
- `smarti/local_gateway.py`
- `smarti/chat.py`
- `smarti/workspace_ui.py`
- `smarti/ui_controls.py`
- `smarti/ui_styles.py`
- `smarti/ui_pages.py`
- `smarti/memory_ui.py`
- `smarti/native_browser.py`
- `smarti/browser_control.py`
- `smarti/browser_profile.py`
- `smarti/visual_canvas.py`
- `packaging/README.md`
- `scripts/build_release.ps1`

External technical references to revalidate at implementation time:

- Tauri sidecars: <https://v2.tauri.app/develop/sidecar/>
- Tauri Windows installer and WebView2 modes:
  <https://v2.tauri.app/distribute/windows-installer/>
- Tauri updater: <https://v2.tauri.app/plugin/updater/>
- Tauri permissions/capabilities:
  <https://v2.tauri.app/learn/security/using-plugin-permissions/>
- Tauri child WebView JavaScript API:
  <https://v2.tauri.app/reference/javascript/api/namespacewebview/>
- Tauri Rust `Webview` and platform `with_webview` access:
  <https://docs.rs/tauri/latest/tauri/webview/struct.Webview.html>
- WebView2 API overview and browser-feature differences:
  <https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/overview-features-apis>
  <https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/browser-features>
- WebView2 user-data folders, profiles, cookies, and data clearing:
  <https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/user-data-folder>
  <https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/multi-profile-support>
  <https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/clear-browsing-data>
- WebView2 Chrome DevTools Protocol support:
  <https://learn.microsoft.com/en-us/microsoft-edge/webview2/how-to/chromium-devtools-protocol>
- Chrome App-Bound cookie encryption on Windows:
  <https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html>
