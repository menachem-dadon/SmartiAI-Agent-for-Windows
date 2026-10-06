# SmartiAI Desktop

The recovered Tauri 2 + React + TypeScript Smarti client. The Rust host owns the
Python Core lifecycle and its per-launch credential; frontend code receives
only narrow authenticated operations and never the bearer token.

## Active UI/UX work

The user authorized a premium/minimal redesign on 2026-10-02. Before UI work,
read [the complete plan](../docs/ui_ux_redesign_plan.md) and
[execution ledger / stage prompts](../docs/ui_ux_redesign_execution.md).
Start with UX-0, then UX-1's interactive prototype. Exact PyQt geometry,
palette and asset locks are historical; functionality, policy and persistence
remain required. Preparation is not implementation or cutover.

The shared plan/ledger are repository files. Local AGENTS.md and
.codex-local/PROJECT_CONTEXT.md may be absent in another checkout; these links
provide design authority without relying on local chat history.

## Development

From the repository root:

```powershell
.\scripts\run_tauri_dev.ps1
```

The command installs the exact `package-lock.json` dependency graph, launches
Vite/Tauri, and lets the Rust supervisor start `smarti_core_service.py`. A
WebView reload does not restart the Core. Closing the Tauri process asks the
Core to stop through its inherited stdin pipe and force-terminates it only after
the bounded grace period.

Development overrides:

- `SMARTI_PYTHON`: explicit Python executable.
- `SMARTI_PROJECT_ROOT`: checkout containing `smarti_core_service.py`.
- `SMARTI_CORE_BINARY`: packaged `smarti-core.exe` override.

The default capability grants no shell plugin and no filesystem plugin. The
Core bearer token remains private Rust state and is never serialized to React.

Keep the legacy PyQt launcher available for source comparison until Point 17.
Do not run source Tauri and another `npm run tauri dev` instance concurrently:
Vite deliberately uses fixed port `1420`. If startup reports that the port is
busy, close the existing Smarti development instance normally and retry.

## Checks

```powershell
npm test
npm run typecheck
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
cargo test --manifest-path src-tauri/Cargo.toml
..\scripts\smoke_tauri_supervisor.ps1
..\scripts\smoke_tauri_browser.ps1
```

The historical `python ..\scripts\verify_tauri_point16c.py` checks old parity
ledgers and is not the new redesign acceptance checker. Do not alter historical
statuses just to make it pass. The accepted redesign/source work closes in UX
ledger §42; functional/native/package evidence and release follow-ups keep their
separate scopes. `verify_ux6_acceptance.py --final` remains the strict all-level
gate, distinct from closing the source/UI project.

Future UI work reads plan §2.1 and `src/design-system/README.md`, reuses shared
components/tokens, and documents intentional changes to shared rules. Those
rules are defaults, not immutable constraints. Normal new controls extend the
accepted language; a task explicitly changing that language can update it.

For repeatable Windows builds from the repository root use
`pwsh -NoProfile -File .\scripts\build_and_package.ps1`.
Version, label, output path, compression, offline WebView2, signing and
prepare-only options are documented in [building Tauri](../docs/building_tauri.md).

The supervisor smoke opens the Tauri WebView hidden, verifies the real Python
Core readiness handshake and Rust health proxy, creates a deterministic
conversation/run without a paid provider request, reloads the WebView without
replacing the Core, proves that chat survives reload and Core restart, detects
an intentional crash, restarts one new Core, and shuts it down through the
inherited control pipe. The Browser smoke separately proves the same visible
and automated WebView2 target, hostile-page Tauri denial, persistent/Guest
isolation, governed popup routing, Hebrew input, resize/focus and screenshot.

## Internal visual fixtures

Development-only fixture routes render real React components without touching
the user's desktop or data:

- `?visual-fixture=point16a&theme=dark&workbench=1`
- `?visual-fixture=point16a&theme=light&workbench=0`
- `?visual-fixture=point16a&theme=dark&drawer=1` (compact-width drawer overlay)
- `?visual-fixture=point16b-management&theme=dark`
- `?visual-fixture=point16b-management&theme=light`
- `?visual-fixture=point16b-legal&theme=dark`

Use headless Edge/Chromium or the existing offscreen QA workflow at narrow and
wide viewport sizes. The active visual specification is
`docs/ui_ux_redesign_plan.md`. PyQt and the old source-parity map provide
functional inventory; fixture screenshots are regression evidence only.
UX-1 may add an isolated interactive prototype with candidate reusable
components and synthetic data. Label simulated actions; do not write personal
state or claim production integration from a self-authored mock.
