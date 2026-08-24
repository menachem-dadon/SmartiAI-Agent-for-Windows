# Point 16C whole-product and current-machine acceptance

- Evidence date: 2026-08-24 (Asia/Jerusalem)
- Product version: `0.87.0`
- Host scope: the user's current Windows 11 x64 computer
- Status: **BLOCKED — PARITY GATE REOPENED** after the user's 2026-08-24 visual check.
  Current-machine packaging passed separately, but Point 16C is not accepted
  and Point 17 remains forbidden.

This document is the final integration ledger for the recovered Tauri product.
The legacy PyQt code remains the one-to-one UI authority and remains runnable.
Screenshots are only regression evidence. The Python Core remains the sole
authority for the agent loop, tools, settings, history, memory and tasks.

## Stable feature-ID resolution

Every ID below remains listed in `tauri_migration_baseline.md`, but an
`IMPLEMENTED` capability status is not visual or behavioral parity acceptance.
All UI-facing grouped rows are provisional until their source-derived control,
state, action and reload audit is complete.

| IDs | Current implementation and acceptance evidence | Resolution |
|---|---|---|
| SHL-001, SHL-002, SHL-003, SHL-004, SHL-005, SHL-006, SHL-007, SHL-008, SHL-009 | Tauri window lifecycle, React Workspace, exact legacy value ledger, Core legal/settings state, Rust title/tray/window ownership, light/dark and narrow/wide fixtures, hidden source/package supervisor smoke | IMPLEMENTED |
| CHT-001, CHT-002, CHT-003, CHT-004, CHT-005, CHT-006, CHT-007, CHT-008, CMP-001, CMP-002, CMP-003, ATT-001, ATT-002, ATT-003, HIS-001, HIS-002, HIS-003 | `App`, `Composer`, `RichMessage`, scoped attachment bridge and `ChatSessionStore`; React interactions, full gateway/history suite and deterministic source/package chat run surviving reload/restart | IMPLEMENTED |
| RUN-001, RUN-002, RUN-003, RUN-004, RUN-005, RUN-006, APR-001, APR-002, GAT-001, GAT-002, GAT-003 | Unchanged Python `ConversationRunManager`, durable SQLite events/approvals/attention, compatible `/v1` plus authenticated generated `/v2`; full Python suite, Qt-free smoke and Rust-proxied product smoke | IMPLEMENTED |
| SET-001, SET-002, SET-003, SET-004, SET-005, SET-006, SET-007, MGT-001, USE-001 | Re-audit against `SettingsPage`, `ManagementCenterPage` and the original management pages is active. The earlier generic React form, self-authored fixture and string-presence tests were not parity evidence. Provider metadata, the dynamic `קבל מפתח` row and bidirectional missing-key dialog are being corrected and interaction-tested. | REOPENED — NOT ACCEPTED |
| MEM-001, MEM-002, MEM-003, TSK-001, TSK-002, TSK-003, TOL-001, TOL-002, TOL-003, TOL-004, DIA-001, DIA-002, DIA-003, ABT-001 | Python-owned memory, scheduler, built-in/custom/MCP/Skill tools, Diagnostic/repairs, privacy logs and About/legal/update, reached through authenticated management routes and covered by full/focused tests. The reopened audit additionally corrected character-split Skills, persistent trust/install errors, the full memory editor, non-blocking Qt-free Diagnostic execution and the duplicate agent-process rendering regression. | IMPLEMENTED; VISUAL/STATE AUDIT OPEN |
| FIL-001, FIL-002, FIL-003, FIL-004, FIL-005, ART-001, TRM-001, TRM-002 | Scoped Core Workbench root, RTL file tree/preview, bounded converters/artifacts and independent hidden UTF-8 PowerShell sessions; traversal/Hebrew-path and lifecycle tests | IMPLEMENTED |
| CAN-001, CAN-002, CAN-003, CAN-004 | Qt-free persisted Canvas model plus opaque-origin sandboxed React iframe, restrictive CSP, validated messages, remote-image opt-in and durable tab/history state | IMPLEMENTED |
| BRW-001, BRW-002, BRW-003, BRW-004, BRW-005, BRW-006, BRW-007, BRW-008, BRW-009 | Approved Tauri-owned WebView2 Smarti Browser, stable same-visible target, persistent/Guest isolation, copied profile import, governed chrome/actions and network policy; source and packaged browser smokes | IMPLEMENTED; BRW-001/002 use the approved Tauri architecture |
| VOC-001, VOC-002, TTS-001 | Shared Qt-free Python voice/TTS authority, independent native Tool overlay and Rust global-hotkey lifecycle; Core/controller, overlay geometry and hidden smoke checks | IMPLEMENTED |
| WIN-001, WIN-002, WIN-003, WIN-004, WIN-005, WIN-006 | Rust single-instance/tray/notifications/taskbar/AUMID/window placement and guarded monitor restore; Rust tests and hidden lifecycle smoke | IMPLEMENTED |
| UPD-001, UPD-002, PKG-001, PKG-002, PKG-003, PKG-004, PKG-005 | Fail-closed signed updater, Tauri GUI plus Qt-free PyInstaller Core, private runtimes, per-user NSIS and portable ZIP. PyInstaller-GUI/Inno were intentionally replaced by the approved Tauri/NSIS architecture. Clean-machine/install-over-existing/uninstall testing is explicitly outside the user-approved current-machine gate. | IMPLEMENTED or explicitly approved current-machine scope |

Automated ledger validation is owned by
`python scripts/verify_tauri_point16c.py`. It must fail while any current parity
row is `REOPENED`; a green package manifest cannot override that failure.

## Source-parity closure

Source-parity closure has **not** been reached. The prior 66-row `CURRENT
MATCHED` claim was reopened because it relied in part on self-authored fixtures,
string presence and page-level assertions that passed while the visible Tauri
screen differed materially from PyQt. Every current row is provisional until
its named PyQt hierarchy, geometry, controls, themed assets, states, handlers,
Core route, persistence and reload path have source-derived evidence.

The old broad `MATCHED` tables remain dated historical context and are not
counted by the Point 16C verifier or acceptance claim.

The active source-to-runtime map, icon map, exact blocking gaps and line-by-line
manual comparison are in `tauri_point16c_source_audit.md`. All whole-product
surfaces remain `AUDIT OPEN`; an `IMPLEMENTED` feature row is not parity.

The 2026-08-24 non-visual remediation suite currently passes 381 Python tests,
49 production React tests, 22 Rust tests and the production frontend build.
This closes the named runtime/wiring regressions only; it does not close the
remaining source-derived visual/state rows or authorize Point 17.

## Automated and live evidence

Final exact counts, artifact hashes and smoke payloads are recorded after the
one-command build in `tauri_point16_release_evidence.md` and the Point 16C
completion record in `tauri_migration_execution_plan.md`.

Evidence categories remain separate:

- static/unit/integration: full Python, Frontend, Rust, generated contract,
  compilation, Qt-free import, dependency and ledger checks;
- source live: hidden Tauri supervisor plus deterministic chat/run/reload/Core
  restart and a separate same-visible-target WebView2 browser smoke;
- visual: internal/offscreen captures are regression aids only. A fixture must
  render the production component and a mocked Core contract; it may not build
  a second hand-authored UI and compare the new design to itself;
- package: fresh one-command NSIS/portable build, Qt-free layout, hashes,
  Authenticode state, packaged supervisor/chat and packaged browser smoke;
- release: not claimed because the local artifacts are unsigned and no public
  updater metadata, publication or Windows Authenticode credentials were used.

The recorded package hashes were produced before the latest reopened-parity UI
remediation in this task. They prove the packaging pipeline and packaged smoke
only; they are not a package of the current working tree and must be rebuilt
after the source audit closes.

## Manual user acceptance before Point 17

Run either source Tauri with `scripts/run_tauri_dev.ps1` or extract the final
portable ZIP to a new test folder. Do not install over the current Smarti and do
not use its live data for this check.

Use the 17-step, state-specific checklist in
`tauri_point16c_source_audit.md#manual-pyqttauri-side-by-side-checklist`. The old
four-line sample was too broad to detect missing controls, icons or reverse
Core-to-UI flows and is no longer acceptance evidence.

Success means the window looks and behaves like the PyQt source in the same
state, no original control is absent or decorative, and no external Chrome/Edge
window appears. Report any difference in this same task. Point 17 remains
forbidden until this user-visible result is accepted.

## Honest limitations

- No clean Windows/VM, every physical DPI/monitor combination, WebView2-missing
  host, install-over-existing, uninstaller or broad compatibility matrix was
  run. The user explicitly chose current-machine acceptance for the migration.
- The local artifacts remain `NotSigned`; the production updater stays disabled
  and fails closed without signing inputs.
- No paid provider call, real microphone capture, account-dependent OAuth/
  passkey registration or public release was performed.
