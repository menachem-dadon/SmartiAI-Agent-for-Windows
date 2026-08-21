# SmartiAI Tauri Migration Master Execution Plan

Status: approved execution plan; implementation has not started  
Plan version: 1.0  
Plan date: 2026-08-20  
Repository: `C:\Users\יהודית סיידון\Downloads\GitHub\SmartiAI-Agent-for-Windows`  
Current product target at plan creation: `V0.87.0`  

This is the authoritative, standalone handoff for migrating SmartiAI's desktop
interface from PyQt6 to Tauri 2 + React + TypeScript while preserving the Python
agent runtime and the one-click Windows application experience.

Point numbers in this document are stable. Do not renumber existing points. If
the plan later needs an inserted task, add a suffix such as `Point 6A`.

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
5. Execute only the requested point and its explicitly listed prerequisites or
   repairs. Do not begin the next point.
6. Do not execute two migration points in parallel.
7. Make reasonable implementation decisions within the point's architecture.
   Ask the user only if a missing choice would materially change product scope.
8. Run all acceptance checks required by the point.
9. Update the Execution Ledger in this file only after the point is genuinely
   complete. Record exact evidence, not a generic "tests passed" statement.
10. End with a self-contained handoff stating: outcome, files changed, tests,
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
| 1 | Baseline and parity inventory | PENDING | |
| 2 | Pure-Python import boundary | PENDING | |
| 3 | Headless Core service entrypoint | PENDING | |
| 4 | Versioned HTTP/WebSocket control plane | PENDING | |
| 5 | Tauri shell and Core supervisor | PENDING | |
| 6 | Embedded-browser feasibility gate | PENDING | |
| 7 | Design system and Workspace shell | PENDING | |
| 8 | Chat vertical slice | PENDING | |
| 9 | Rich messages, composer, attachments, voice | PENDING | |
| 10 | Settings and provider management | PENDING | |
| 11 | Tasks, memory, tools, diagnostics, usage | PENDING | |
| 12 | Files, artifacts, and terminal Workbench | PENDING | |
| 13 | Sandboxed Canvas | PENDING | |
| 14 | Full Smarti Browser surface | PENDING | |
| 15 | Windows desktop integration | PENDING | |
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
  browser profile, and audit data remain available.

The migration is also a product redesign. Preserve the information architecture
and Smarti visual identity, but do not reproduce every PyQt widget pixel for
pixel. Use the move to improve hierarchy, motion, typography, spacing,
responsiveness, polish, and consistency.

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
  secrets, browser automation, and Windows computer automation.
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

### 5.4 Windows and installation invariants

- Initial parity target: supported x64 Windows 10 1803+ and Windows 11.
- ARM64 is a later, separately validated build target. Do not claim Windows 7,
  32-bit, or ARM64 support without their own artifacts and tests.
- Installation is per-user and does not require an administrator by default.
- Packaged Smarti retains private Python and Node runtimes for custom Python
  tools, Skill dependencies, and MCP packages.
- The UI development Node toolchain is not a runtime prerequisite for users.
- Existing application data paths and browser profiles are preserved.
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
  CDP endpoint.
- `smarti/browser_control.py` uses Playwright/CDP structured actions against
  that same persistent profile and visible target.
- `smarti/browser_profile.py` provides copy-based, user-initiated import of
  compatible cookies, history, and bookmarks; passwords are never imported.
- Persistent Smarti and temporary guest profiles have different lifecycle and
  privacy requirements.
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
|   +-- design system, motion, RTL, light/dark
|
+-- Rust trusted desktop host
|   +-- window, tray, single instance, taskbar, notifications
|   +-- Core process supervisor and authenticated proxy
|   +-- updater, file dialogs, safe native opening
|   +-- native Chromium child-host integration
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

Do not base the required integrated browser on Tauri's unstable multiwebview
API. Preserve the dedicated installed Chromium/Edge process and CDP design.
Port the native child-window hosting layer from PyQt/ctypes to Rust/Win32 and
position it over a React-declared browser viewport. This design must be proven
by Point 6 before the main UI migration proceeds.

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

The new interface should be recognizably Smarti, but substantially more refined.

- Use CSS custom properties as semantic design tokens for color, typography,
  spacing, radii, shadows, blur, motion, and density.
- Maintain separate light and dark themes from the first component, not at the
  end of the migration.
- Prefer structured CSS or CSS modules over an uncontrolled accumulation of
  inline styles or utility classes. A small utility layer is acceptable.
- Use accessible headless primitives where useful, with an RTL audit rather
  than assuming a component library is RTL-correct.
- Use a consistent icon family and SVG assets; do not use text glyphs as final
  icons when a real icon is available.
- Use motion to explain state and hierarchy. Respect `prefers-reduced-motion`.
- Blur, glow, Mica/Acrylic, gradients, and transparency must have performant,
  readable fallbacks. Visual novelty must not reduce contrast or clarity.
- Avoid deep card nesting. Prefer a small number of clear surfaces with strong
  spacing and typography.
- Chat Markdown must not enable arbitrary raw HTML. Code blocks need copy,
  wrapping/scroll behavior, direction handling, and lazy syntax highlighting.
- Hebrew user-facing text remains natural and polished. Paths, code, terminal,
  URLs, model IDs, and technical values remain LTR inside the RTL shell.

## 9. Cross-cutting acceptance matrix

Every relevant point must validate the subset it changes.

### 9.1 Layout and visual states

- Light and dark themes.
- RTL shell and mixed RTL/LTR content.
- Minimum supported window near the current `720 x 560` constraint.
- Typical `1180 x 760` and wide/maximized Workspace.
- Windows display scale 100%, 125%, 150%, and 200% for native surfaces.
- Empty, loading, populated, error, offline/Core-crashed, approval, and running
  states.
- Reduced motion and keyboard-only navigation.

### 9.2 Runtime states

- No conversation, new conversation, long history, and paginated history.
- One run, queued runs, independent conversations, cancellation, restart
  interruption, waiting approval, denial, approval, timeout, and unread result.
- Core starts slowly, Core fails startup, Core crashes, WebView reloads, and
  desktop exits while work is active.
- Browser/computer singleton leases under concurrent conversations.

### 9.3 Security states

- Unauthorized local request, wrong origin/token, replayed idempotency key,
  oversized body, malformed schema, path traversal, symlink/reparse escape,
  Canvas XSS, unsafe URL, and secret masking.
- Frontend code must not be able to invoke arbitrary shell or read arbitrary
  user files through Tauri.

### 9.4 Performance

Point 1 establishes measured baselines. Later points must report total memory
across Tauri, Core, and managed Chromium, startup-to-ready time, idle CPU, chat
render time for a long conversation, and first-action latency where relevant.
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

### Point 6 - Prove the embedded Smarti Browser architecture

**Depends on:** Point 5 complete.  
**This is a mandatory go/no-go gate. Do not start Point 7 if Point 6 is blocked.**

**Objective**

Prove that Tauri can preserve Smarti's integrated visible Chromium surface and
Playwright/CDP capabilities without relying on unstable multiwebview APIs or an
external user-managed browser window.

**Required work**

1. Implement a minimal Rust/Win32 native-browser host based on the behavior of
   `smarti/native_browser.py`:
   - find a compatible installed Edge/Chrome/Chromium;
   - launch with loopback CDP and Smarti-managed profile;
   - identify the correct browser HWND and CDP target;
   - make it a child/sibling native surface inside the Tauri window;
   - position, resize, focus, show, hide, and close it safely.
2. Add a React browser viewport placeholder that reports physical/logical bounds
   to Rust and reserves toolbar space outside the native browser airspace.
3. Prove the persistent profile and a disposable guest profile, with guest data
   removed on close.
4. Connect the existing Python Playwright/CDP controller to the same target the
   user sees.
5. Exercise navigation, keyboard, Hebrew input/IME, mouse, focus transfer,
   clipboard, downloads, uploads, screenshots, cookies, clear-data, minimize,
   restore, maximize, workbench-tab hiding, multi-monitor movement, and display
   scale 100%, 125%, 150%, and 200%.
6. Add focused Rust/Python contract tests and a repeatable manual QA script.

**Acceptance**

- The browser is visibly integrated into the Tauri window.
- Playwright navigates and inspects exactly that visible target.
- Persistent and guest profiles are demonstrably separate.
- Focus, resize, DPI, minimize/restore, and hide/show are reliable.
- No unmanaged external top-level browser window is the normal UX.

If this cannot be made reliable, mark Point 6 `BLOCKED`, present measured
alternatives and tradeoffs, and stop. Do not silently downgrade the requirement
or continue building the remaining interface.

**User check**

Open the prototype, type Hebrew into a real website, resize/maximize the Smarti
window, switch away from and back to the Browser panel, and ask the test action
to navigate the visible page. Confirm there is no separate browser window.

**Out of scope**

No complete browser toolbar, library, import UI, or final styling.

### Point 7 - Build the design system and final Workspace shell

**Depends on:** Point 6 complete.

**Objective**

Establish the visual language and responsive Workspace composition before
moving feature-heavy screens.

**Required work**

1. Create semantic tokens for both themes: background, surface hierarchy,
   glass, border, text, muted text, accent, success, warning, danger, focus,
   code, radii, spacing, shadow, blur, motion, density, and typography.
2. Build accessible base components: buttons, icon buttons, fields, textarea,
   menus, tooltips, dialogs, sheets/drawers, tabs, scroll areas, badges,
   skeletons, alerts, cards, resizers, empty states, and focus management.
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
6. Produce light/dark screenshots at the required sizes and compare them with
   architectural, not pixel, parity from Point 1.

**Acceptance**

Component tests, type checks, Rust checks, and visual QA pass. The shell looks
like a modern Smarti redesign, not an unfinished web admin dashboard and not a
pixel copy of Qt. The left area is truly empty until requested.

**User check**

Review the supplied light/dark narrow/wide screenshots. Confirm the chat is
central, conversations are on the right, the Workbench is on the left and empty
by default, and the overall visual identity feels like an upgraded Smarti.

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

Reach full daily chat-composer parity and improve its presentation.

**Required work**

1. Build the final responsive composer: multiline input, send/cancel state,
   keyboard behavior, action menu, model indicator, drag/drop, paste, and file
   picker.
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
attachments, voice, TTS, tool cards, and mixed RTL/LTR content. Secret and file
boundaries remain enforced.

**User check**

Attach a Hebrew-named text file and an image, remove one before sending, paste an
image, send the request, copy a code block, and try voice/TTS. Confirm the UI is
clear in both themes and no permission prompt is hidden behind the window.

**Out of scope**

No Settings or Workbench file browser implementation.

### Point 10 - Migrate Settings, providers, secrets, and connection management

**Depends on:** Point 9 complete.

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

Turn the proven native host into the full polished, secure Smarti Browser panel.

**Required work**

1. Implement final toolbar and state: back, forward, reload/stop, home, address
   and search, loading/security state, error state, find, zoom, and menu.
2. Preserve persistent/guest switching with explicit privacy explanation and
   complete guest cleanup.
3. Migrate user-initiated profile discovery/import for compatible cookies,
   history, and bookmarks. Never import passwords or modify source profiles.
4. Implement searchable history/bookmark library, downloads, capture path,
   device mode, screenshots, user agent, clear data, external open, and browser
   preferences.
5. Support repeated Browser tabs/panels as current Workbench behavior requires,
   with correct CDP target ownership and cleanup.
6. Ensure Python browser automation activates the visible browser, uses the same
   persistent target, obeys network/private-host policy, and serializes singleton
   leases across conversations.
7. Run the complete Point 6 DPI/focus/keyboard/automation matrix again on the
   final UI and in a packaged candidate, not only the prototype.

**Acceptance**

Every Browser item in the parity matrix is resolved, the visible and automated
target is the same, profile privacy boundaries are intact, and package-level
browser smoke passes.

**User check**

Browse normally in persistent mode, restart and verify the session persists;
repeat in Guest and verify it does not. Import from a test browser profile,
search history/bookmarks, download a file, take a screenshot, and ask Smarti to
navigate the same visible page.

**Out of scope**

No general-purpose password manager and no control of the user's ordinary
Chrome profile in place.

### Point 15 - Complete Windows desktop integration

**Depends on:** Point 14 complete.

**Objective**

Restore and improve the native Windows behaviors that make Smarti one desktop
application rather than a localhost client.

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
   assets, certificates, Playwright helpers, and runtime path behavior required
   by packaged operation.
3. Bundle private Python and Node runtimes with pinned versions and checksums,
   retaining writable user caches and Skill/MCP dependency behavior.
4. Produce a Tauri NSIS per-user installer and portable ZIP. Configure WebView2
   embedded bootstrapper for the primary installer and an optional separate
   offline installer if required.
5. Preserve data paths, browser profile, AUMID/identity, shortcuts, protocol
   behavior, and settings. Implement and test detection/removal/upgrade from the
   old Inno Setup installation without deleting user data.
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
   Node, Rust, npm, or repository files; exercise both WebView2-present and
   WebView2-missing installation paths.

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
2. Make Tauri the default source and packaged launcher.
3. Remove legacy PyQt UI modules, Qt adapters, WebEngine compatibility paths,
   PyQt requirements, PyInstaller UI entrypoint, Inno-only packaging, dead
   assets, and transition feature flags that are no longer needed.
4. Preserve pure Python behavior extracted from former UI modules and ensure no
   Core import/runtime path loads Qt.
5. Update README, architecture, contributor setup, tests, packaging docs,
   screenshots, troubleshooting, and release notes to the final product.
6. Run full Python, frontend, Rust, integration, security, visual, browser,
   package, clean-install, and upgrade suites again after deletion.
7. Compare final performance and artifact metrics to Point 1 and document every
   meaningful improvement or regression.
8. Produce the final release candidate and a complete evidence-backed handoff.
   Do not publish without explicit user authorization.

**Acceptance**

- The parity matrix has no unresolved required feature.
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
confirm that the architecture is familiar while the presentation is materially
more polished.

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
6. Do not replace the integrated browser with a normal external browser window
   without explicit user approval. Point 6 exists to prevent that downgrade.
7. If a point reveals that a later point's assumptions are invalid, update this
   plan with an added stable subpoint and explanation; do not renumber or
   silently broaden the active point.
8. If tests fail for apparently unrelated reasons, reproduce them in isolation
   and against the pre-point state before attributing or ignoring them.
9. Never use source/offscreen tests to claim installer, WebView2, native HWND,
   DPI, notification, updater, or packaged browser success.

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
- Current Tauri `WebviewBuilder` status:
  <https://docs.rs/tauri/latest/tauri/webview/struct.WebviewBuilder.html>
