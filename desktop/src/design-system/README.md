# Smarti shared design system · UX-2

Authority: `docs/ui_ux_redesign_plan.md`, accepted UX-1 v7 and ledger §21–42.
UX-2 is complete within the shared-foundation scope; UX-3 product shell and chat
are complete within ledger §30 after product feedback D45–48 and closing review.
UX-4 is complete within ledger §34; UX-5 management/settings is complete within
§39 after user acceptance and independent review. UX-6 and the accepted design/source
project are COMPLETE within ledger §42 / D61. Source/native/assisted evidence keeps
its original scope in §40–41. Strict product/release acceptance, matching latest
packages and the overall Tauri migration remain separate; see `docs/ux6_closure.json`.
Preserve the
697px reading/composer cap, sticky input, draft/scroll owners, D48, and the real
workbench lifecycles D50–54. The shared chevron baseline is in §24.
Import product foundations from `src/design-system`; never from `src/ux1` or `src/ux2`.

## Preserve the accepted visual language (UX-D58)

The user accepted the language after UX-5 while reserving further layout and UI
refinements. Plan §2.1 and ledger §38 apply to every subsequent UI change,
including maintenance after UX-6. Routine fixes and new controls extend the
accepted language; changing the overall direction requires an explicit user
choice. This does not freeze layouts or prevent requested improvements.

Rules are a deliberate default, not immutable law. A task whose purpose includes
changing a shared rule or the design direction authorizes that change; record
its scope/reason and update the shared source, with no redundant approval step.
Ordinary new controls use the existing components and states. Do not invent a
new button style incidentally while implementing an unrelated feature.

Color roles are intentionally distinct: regular primary `Button` uses `accent`
(light #365ccd); the conversation send/microphone/stop circle uses `action`
(#397bfa). The deeper and brighter blues belong to one semantic palette. Dark
`accent` is #a2baff for contrast, while `action` remains #397bfa. Future controls
choose a role by function, not an isolated color literal. A requested unification
updates these shared roles and their consumers deliberately.

Reuse the semantic tokens, typography, spacing, corners, icon families, focus,
control states and restrained motion. Reuse existing primitives first. Extend
the shared foundation for a shared need; keep local composition CSS scoped and
token-based. Do not add another palette, control family, global App.css override
layer, or copied prototype renderer. Preserve later accepted decisions over
superseded prototype details.

For material visual changes, check the affected product beside an accepted
surface in light/dark and wide/narrow layouts with physical RTL. Interaction
changes also check keyboard, focus/Escape and reduced motion where applicable.
Record relevant screenshots/checks and retain functional persistence/ownership
coverage. A shared primitive change must cover its other affected consumers.
Document intentional changes to a shared rule in the plan and ledger with scope
and reason. A source/build pass alone does not establish visual or native quality.

## Single sources and scope

- `tokens.ts`: light/dark semantic palettes, typography, 4/8/12/16/24/32/48 spacing,
  corners, targets, separators, shadow and motion. `designTokenStyle()` projects
  the same values into CSS properties. `designSystem.ts` keeps the existing theme
  preference/storage-key/contrast API and re-exports these values. It has no second palette.
- `system.css`: component rules consume those properties. Importing the shared
  components loads this stylesheet; it is scoped to `.sds-root` and `sds-*` classes.
- `icons.tsx`: all 63 semantic roles map to the official Tabler React SVG
  components (`@tabler/icons-react` pinned to 3.48.0). Inline SVG inherits
  currentColor, uses a 24×24 viewBox and stroke 2; filled favorites stay filled.
  Static imports keep unused library icons out of production bundles.
- `icons/`: all 126 original v7 PNGs are preserved unchanged as the reversible
  original family. UX-1 remains the original visual reference. No files were deleted.
- `primitives.tsx`: presentation and interaction only. No Core, Tauri, fixtures,
  token/secrets storage, network, model requests or domain persistence.
- `src/ux2`: DEV-only gallery. Normal `vite build` continues to use `index.html`.
  The gallery's edits/results are synthetic state in memory and reset on reload.

Segoe UI and Arial are system fallbacks. No font files are copied or distributed.
All 63 original drawings (126 PNGs) were authored in this repository; they retain
the repository's existing license and required notices in root `LICENSE`.
`NOTICE.md` records both families' provenance. The user's later SVG request
supersedes the earlier PNG-only requirement (ledger UX-D40 and §23).
Tabler is MIT licensed; its complete notice is in
`desktop/public/licenses/tabler-icons-MIT.txt`, copied into dist by Vite and
embedded with frontendDist by Tauri. The official React dependency is used for
SVG rendering only; no CDN, icon-font, account or runtime network is required.
The gallery is excluded from the product build.
The existing Tauri release script copies the root LICENSE into the portable
directory (`scripts/build_tauri_release.ps1`); its frontendDist is `desktop/dist`.
The existing repository license remains unchanged; Tabler's MIT terms apply to
its own artwork. No packaging recipe was changed.
Rebuild artwork with `python scripts/generate_ux1_icons.py` (Pillow), which now
writes the canonical shared directory. This is a development helper only.

## Usage

The default family is Tabler SVG. To restore the preserved artwork, pass
`iconFamily="original"` to DesignSystemProvider; `iconFamily="tabler"` switches
back without replacing component instances or resetting caller state.
The DEV gallery offers both buttons and `?icons=original` for comparison. This
does not introduce a persisted product preference. The semantic mapping in
icons.tsx covers every existing action/tool role; send remains ArrowUp, back
ArrowLeft, forward ArrowRight and chevron ChevronDown, preserving physical v7
directions and caller transforms. Both chevron families start down; rotate 90deg
for collapsed-left and leave unrotated for expanded-down. The closing review
normalized this baseline so family switching preserves folding directions.
Icon accessible names belong to their action
controls; SVG artwork is aria-hidden and never focusable.

```tsx
import { DesignSystemProvider, Button, SettingRow, Switch, MessageFrame } from "./design-system";

<DesignSystemProvider theme={resolvedTheme} dir="rtl" reducedMotion={reducedMotion}>
  <SettingRow title="הפעלת הכלי">
    <Switch label="הפעלת הכלי" checked={settings.enabled}
      onCheckedChange={saveThroughExistingHandler} />
  </SettingRow>
  <MessageFrame outputs={artifactCards} actions={existingCopyAndTtsActions}>
    {safeMessageContentAndAgentProcess}
  </MessageFrame>
  <Button variant="primary" loading={submitting} onClick={existingSendHandler}>שליחה</Button>
</DesignSystemProvider>
```

The provider accepts the existing resolved theme; it neither reads nor writes
personal preferences. Set it once around the converted surface. Menus/tooltips
use a themed body-level portal to escape sidebar clipping and stacking contexts;
native dialogs retain their own overlay host in the browser's top layer. Triggers
are owned refs. There is no DOM search for anchors, MutationObserver or raster replacement.
Keep the provider outside transformed/clipped native surfaces; a WebView2 window
still needs its existing hide/preview/final-bounds/show lifecycle.

| Component | Contract / integration responsibility |
|---|---|
| Button / IconButton / Icon | Native button props and explicit semantic icon; loading disables activation and exposes aria-busy. Icon actions retain names; tooltip=false removes redundant hints for copy/TTS/close/download. Stop uses the official filled Tabler square; original PNGs remain intact. A round primary IconButton keeps the accepted blue/white action treatment in both themes, separately from text-button accent roles. Caller retains duplicate-send guards and domain cancellation. |
| Field / SearchField / NumberField / Textarea | Native control props, label, unique ID, hint/error associations and optional ref. Textarea defaults to dir=auto for Hebrew/English writing; callers may override it. Numbers stay short; parsing, validation, secrets masking and persistence stay with existing handlers. |
| RangeField | Controlled numeric value and synchronous onValueChange; native pointer/keyboard behavior, textual output and filled track. Caller supplies min/max/step/formatValue; 0 has no invented meaning. |
| Switch | Controlled checkbox with switch semantics; Space and disabled remain native. Track 44×26 inside a 44×40 target. Active thumb physically left in RTL, right in LTR. |
| Menu | Explicit item callbacks/disabled/tone; click toggles, outside interaction, Escape, Home/End, arrows, single-character lookup and Tab. Focus returns for Escape/selection; outside click preserves destination focus. No X. Optional `description` appears below the label and is linked by `aria-describedby`, retaining a short accessible name. Optional `fitContent` uses intrinsic width and measures the surface for positioning, retaining viewport limits and shared padding. Current/history conversation actions (D62) and safety profiles (D64) opt in; other menus retain the default width. |
| Dialog / ConfirmDialog | Controlled open/onClose. Native HTML dialog provides modality; explicit Tab/Shift+Tab looping retains focus in the app. Unique title/description IDs; optional initialFocus; previous focus restored. A dialog-owned overlay host keeps tooltips in the top layer. Confirm focuses cancel, caller controls busy/error and closes only on actual success. No action is synthesized. |
| Tooltip | Keyboard focus/hover, associated description and Escape. Natural content width within the viewport, immediate pointer-leave dismissal, and no focus hint retained after a mouse click. Essential actions remain present on touch. Tooltip text cannot be the sole accessible name. |
| Tabs | Controlled active/onSelect with explicit panels. RTL-aware arrows, Home/End, roving tab stops, linked panels; hidden panels remain mounted to preserve drafts and state. Caller must give a valid enabled active ID. |
| PageHeader / SettingsGroup / SettingRow / Card | Slots for hierarchy, adjacent descriptions and controls. Wrap based on available container width, not old PyQt constants. |
| Alert / Badge / EmptyState / LoadingState | Distinguish actual errors, explicit results, empty content and loading. Errors use role=alert; loading has text and aria-busy. Do not add routine save-success copy. |
| MessageFrame / UserBubble / HoverLabel | Outputs precede ALL copy/TTS actions by slot order. Bubble physically right even for English; isNew is consumed after 240ms and history does not replay it. Long names move on focus/hover at 72px/s; full title is available, motion reduction is honored. |

`Button` loading does not replace a real async guard. `ConfirmDialog` never owns
policy approval, secret interruption or deletion semantics. Pass real status and
callbacks; retain useful failures and recovery instead of assuming success.

## Migration map — remove old rules when each surface is converted

| Current layer | Replacement / owner |
|---|---|
| Competing App.css theme values and old designSystem contrast literals | tokens.ts is the sole **new** value source; old contrast literals replaced now. Delete legacy theme selectors as UX-3/4/5 convert each surface, after preserving its behavior. Product screens are not recolored in UX-2. |
| ui.tsx / ui-* classes | Transitional controls for unconverted product screens only. Replace imports and remove their relevant App.css rules by region in UX-3–5. No new component or gallery uses this layer. Do not globally re-export new components under old names with incompatible props. |
| legacyAssets / agentToolIcons / ux1 useRasterIcons | Explicit Icon/actionIcons/toolIcons props in converted regions, Tabler SVG by default. Original PNG source preserved as a reversible family; UX-1 and unconverted product screens retain their existing renderers. |
| ux1 SettingsSurface / WorkspaceSurface / ProductPanels | Reference inventory; reconcile layout with SettingsManagement/WorkspaceView/WorkbenchPanels and shared slots in UX-4/5. Never import or maintain those derivatives in the product. |
| ux1 MessageSurface DOM portal placement | MessageFrame outputs/actions slots around the actual renderer in UX-3. Retain Markdown security, agent process identity/expansion and all output/attachment handlers. No copied renderer. |
| Historical exact token-family key/order test | Replaced in designSystem.test.ts by matched theme-role/CSS projection tests and neutral boundary/focus contrast. Persisted/system theme tests retained. |
| Historical PyQt geometry tests | Remain until their product region changes. New rendered bounds, actual 40px targets, RTL sides, keyboard/modal behavior and composed color tests live in verify_ux2_design_system.cjs. No behavior/policy/persistence test was removed or disabled. |

## Binding handoff to UX-3–5

- UX-3: retain empty drafts outside history until first content; new conversation
  rises to top. Fixed history search/create/brand coordinates, global policy next
  to +, provider favorites and real reasoning eligibility, readable menus, drafts
  during runs under existing send guards. Approval continues the same process
  and expansion state. Preserve cancel/replay/scroll/attachments and voice owners.
- UX-4: last active tab or four empty tool entries; Canvas opens only from chat.
  Close panel keeps tabs within a session; next app session starts empty (D28).
  Explicitly reconcile current persisted snapshots with that rule without deleting
  personal artifacts/files, disconnecting background targets or breaking workspace_id.
  Keep native target ownership, permission scope, iframe/CSP and terminal lifecycle.
- UX-5: use original setting/save/validate-before-save handlers and masks, actual
  provider catalog/eligibility, global policy authority, silent routine successes
  and visible errors/explicit test outcomes. Keep all advanced/conditional actions.
- UX-6: real screen reader, Windows DPI/text scaling, native product performance
  and package acceptance. Browser viewport checks are not Windows DPI evidence.

## Examples and verification

From desktop: `npm run dev:ux2`; open `http://127.0.0.1:1434/ux-2.html`.
Use light/dark/system, narrow container, motion reduction and RTL/LTR controls.
Direct links: `?theme=dark`, `?narrow=1`, `?tab=message`, `?tab=states`, `?tab=tokens`.
Add `&icons=original` to restore the preserved family in the gallery.
Keyboard: Tab, Shift+Tab, menu arrows/Home/End/Escape, native range arrows,
Space on switches; try rename and failed confirmation/retry. No personal writes.

Focused tests: `npm test -- src/designSystem.test.ts src/design-system/primitives.test.tsx src/design-system/icons.test.tsx --maxWorkers=1`.
Browser QA from root: `node scripts/verify_ux2_design_system.cjs http://127.0.0.1:1434 .codex-local/ux-2/qa`.
Resolve Playwright via NODE_PATH from the bundled runtime; no project dependency.
The verifier measures composed rendered text colors, targets, sides, keyboard,
modal focus, narrow bounds and reduced motion. SVG stroke/fill colors are measured
from rendered shapes; original PNG colors are measured separately. Ledger §22/23
records results before and after the user's icon change; §24 records the current
independent closing evidence and the remaining product checks.

UX-3 product QA from root: `node scripts/verify_ux3_product.cjs http://127.0.0.1:1437 .codex-local/ux-3/product-review`.
Start an owned Vite server on a free private port first. This runs real product
React with authenticated Core in a temporary profile and an in-memory keyring
installed before runtime imports by tests/__init__.py. Only model generation is
deterministic and native IPC is adapted for Edge. It never uses the personal Core.
An optional fourth argument is a frozen v7 URL or a prior report with references;
comparisons are omitted without it, and reports distinguish browser from native.
`verify_ux3_native.cjs` requires a separately prepared QA Tauri app identified as
ai.smarti.ux3native, ux3-native.exe, its own SMARTI_DATA_DIR/keyring and CDP port,
and `.codex-local/ux-3/native-ui.pid`. It verifies the process/identifier before
reload or Core writes; it is not a launcher or a package verifier. Existing native
evidence/setup and its limits are in ledger §25–30. Never point it at the personal app.

## UX-4 product workbench (ledger §31–34)

WorkbenchSurface, WorkbenchFiles, WorkbenchTerminal, CanvasPanel, BrowserPanel,
BrowserPreviewCard and WorkspaceView now use these controls and semantic colors.
`workbench.css` owns the converted surfaces; `management.css` now owns management
composition. Button supports a React 19 button ref. Menu's optional `onOpenChange` reports
its HTML overlay so a native child surface can hide during the overlay.

`workbenchSession.ts` stores only session UI recovery. It ignores old Core tab
snapshots without deleting them. A random owner prefixes new workspace IDs;
browser hydration reattaches live broker owners and never launches stored URLs.
Canvas references retain conversation/target IDs. Terminal recovery retains the
actual process ID and closes it only on an explicit tab close or stop.
Native window actions use `get_window("main")`: a host with browser children is
no longer a Tauri WebviewWindow, although its Windows window still exists.

From the repository root, with bundled Playwright available via NODE_PATH:
`node scripts/verify_ux4_product.cjs http://localhost:1420 .codex-local/ux-4/product-final`.
The host selects a workspace under its temporary SMARTI_DATA_DIR **before writing
fixtures**; data/profile isolation alone does not isolate the default Documents
workspace. The ledger records the first-run isolation mistake and recovery.

`pwsh -NoProfile -File scripts/prepare_ux4_native.ps1` prepares a separate QA app,
data directory and in-memory keyring; it never launches the personal profile.
`node scripts/verify_ux4_native.cjs http://127.0.0.1:19446 .codex-local/ux-4/native-final --skip-open-with`
checks real IPC, PowerShell and WebView2. That flag explicitly leaves Windows
Open With unverified in that automated report. Strict mode only recognizes a
classic HWND dialog; a modern composited picker can appear as an overlay without
a separately discoverable window. Its probe failure cannot prove UI absence.
Ledger §34 records the GUI-thread dispatch repair, the user's actual observation
of the chooser and Escape cancellation, and separate read-only checks that the
button recovered without a file error or Core restart. This is human-assisted
native acceptance, not an automated picker or application-selection test.
Keep Core path validation off the UI thread and the shell chooser on the owning
GUI STA/message loop. Do not report an API success code, interim broker window,
or mocked false result as proof of a user selection.
The native verifier leaves the QA app running for inspection; quit only after
checking its identifier and process. These scripts are not package verification.
`node scripts/verify_ux4_relaunch.cjs`
checks a real quit/relaunch with the same QA data and verifies empty session tabs
alongside retained Core artifacts/preferences. It quits the QA app when finished.
`pwsh -NoProfile -File scripts/restart_ux4_native.ps1` reopens that same isolated
QA profile for inspection after validating the prepared executable and manifest.

## UX-5 management/settings (ledger §35–39, complete within stage scope)

ManagementCenter, SettingsManagement, ManagementPages, MemoryManagement,
UsageView and LegalAgreement use the shared controls and semantic colors.
Navigation labels remain present in the horizontally scrolling narrow layout.
The chat/workbench stay mounted and inert while management is active; native
browser visibility follows that state through the existing broker lifecycle.
No product module imports a UX-1/2 fixture or renderer. Original PNG assets remain.
The obsolete `ui-*` management rules and competing theme palettes are removed.

Additional shared contracts:

| Control | Contract |
|---|---|
| Field / Textarea / SearchField | Optional `hiddenLabel` hides the real associated label visually; it never removes the accessible name. |
| SelectField | Native select, associated label and help/error IDs; preserves native keyboard operation and caller values. |
| ChoiceField | Controlled `value` / `options` / `onValueChange` for styled settings choices. Reuses Popover/Button/Icon and the provider picker's spacing, selected row and check. All labels share a hidden intrinsic grid cell, so the trigger keeps the widest rendered label's width across selection; the popup matches it and both respect available space. Opens on the saved enabled value (or first enabled option), supports arrows/Home/End/character lookup, explicit Enter/Space/click selection, Escape/Tab and outside dismissal. The real label, selected-value description, help/error IDs and disabled choices stay accessible. Caller owns saving and errors. D65 covers reasoning, conversation title, TTS voice and skill scan policy settings. |
| Checkbox | Native checkbox for explicit opt-in and bulk selection; toggled preferences use Switch. |
| Popover | Body portal within the design provider, viewport bounds, focus departure/outside-pointer dismissal, Escape returns to trigger. Boundary Tab resumes from trigger. Optional `triggerContent` preserves a separate accessible label; ArrowDown/Up can open. `triggerProps` supports an associated ID, class, disabled state and help/error attributes; the trigger announces the popup's dialog role. `matchTriggerWidth` opts into the trigger's rendered width, updating on resize with viewport limits; `className` scopes product composition on the popup. Default width stays 380px. Caller keeps options, search and async selection authority. |
| Dialog | Escape stops propagation to app shortcuts while preserving native cancel/close. Closing an inner dialog retains management and restores its trigger focus. |
| SegmentedControl | One semantic group and shared frame for existing mutually exclusive buttons. Caller retains values, `aria-pressed`, click handlers and persistence; native Tab/Space/Enter remain available. |

UX-D64 / ledger §45 uses `src/autonomyProfiles.ts` for safety names/descriptions
in Composer and the settings catalog. The optional shared `sds-option-copy` /
`sds-option-description` hierarchy keeps descriptions muted and on their own line.
Safety settings opt into a vertical segmented group with the same copy; theme and
other segmented controls retain their layout. Intrinsic menu width includes the
longest description and shared padding only, wrapping within viewport limits.
Profile IDs, custom mode and authenticated Core persistence remain unchanged.

Settings autosave stays silent on success. Protected email_address uses the
existing secret route, never a safe-settings PATCH or plaintext readback.
Provider keys still validate before persistence. Memory's no-expiry value is 0
as required by the existing numeric contract. Mutation dialogs retain drafts
and report errors until the caller confirms actual success. Workspace startup
describes D53's saved normal bounds without changing historical preference data.
About can display the same full agreement text and real consent state.

UX-D56 / ledger §36 refines management copy and physical RTL layout. Built-in
tool descriptions are concise Hebrew product copy in `toolDescriptions.ts`;
Core schemas and execution descriptions remain unchanged. Tool names align
right even when their text is English; remove sits between name and switch.
Navigation no longer has a separate screen search. Management search is half
width and right aligned; destructive memory/usage actions stay by refresh.
FastMode and its model selector share one unwrapped group. Only the visible
FastMode text is hidden in the narrowest container; the accessible name and
hover hint remain, and the selector keeps a 40px target.

`--feedback` on the UX-5 browser/native verifiers checks physical sides, shared
frames, header actions, search width and local-model control adjacency. Browser
QA adds three synthetic extension rows for custom/MCP/skill layout only; their
installation and trust authority are not claimed as native test evidence.

UX-D57 / ledger §37 adds the supplied provider artwork in `src/provider-icons/`
to the settings provider picker. `ProviderPicker` uses shared Popover/Button,
all 18 catalog values and the existing save handler. Decorative 20px icons sit
physically right of bidi-isolated names; monochrome masks inherit theme text
and color assets stay unchanged. No icon library or runtime network is added.
The supplied MIT notice is in `public/licenses/lobe-icons-MIT.txt`; see NOTICE.
`scripts/verify_ux5_provider_icons.cjs` checks the guarded isolated Windows app,
asset loading, geometry, keyboard, real provider persistence and reload.

UX-D63 / ledger §44 sizes the provider trigger from all catalog labels overlaid
in an aria-hidden CSS grid, using the actual font rather than a fixed pixel width
or character count. The popup opts into `matchTriggerWidth`. Space for the
selection mark is reserved in every row; 8px popup/row padding and 16px trigger
padding keep the longest label fully readable at the same compact width.
Selection, errors and font-size changes preserve the width rule; other Popover
consumers keep their default sizing. The provider's grid track and hidden sizing
labels can shrink within the field, so enlarged text in a narrow window does not
create horizontal scrolling; labels retain the existing ellipsis when space runs out.

Product QA: start an owned Vite server on 1439, then run
`node scripts/verify_ux5_product.cjs http://127.0.0.1:1439 .codex-local/ux-5/product-review-final-fixed`.
It uses actual React/Core with temporary data/keyring/workspace before imports;
Edge adapts native IPC and generation is deterministic. This is not native proof.

Native trial: `pwsh -NoProfile -File scripts/prepare_ux5_native.ps1` prepares
ux5-native.exe / ai.smarti.ux5native with its own profile, keyring and workspace.
It uses a distinct QA library name, Vite 1439 and unused CDP port 19457.
The verifiers check executable, URL and actual app identifier before mutation.
`node scripts/verify_ux5_native.cjs http://127.0.0.1:19457 .codex-local/ux-5/native-final`
checks real Rust/Core/WebView2, rendered management pages and physical RTL.
`node scripts/verify_ux5_relaunch.cjs` additionally measures the native child
window moving outside the client area during management and returning with the
same owner, then verifies actual process restart, disk settings and consent.
`pwsh -NoProfile -File scripts/restart_ux5_native.ps1` reopens the same closed QA
profile; it validates identity and refuses a port owned by another process.
Reports contain no auth tokens or personal content. The keyring is deliberately
temporary; do not enter personal credentials in this trial. All native evidence
is at the measured 125% DPI. Real providers/OAuth/audio, other DPI/text scaling,
screen reader, Office/system pickers/performance and signed packages remain UX-6.

`node scripts/verify_ux4_window_regressions.cjs .codex-local/ux-4/regression-native`
requires a prepared, closed QA app. It reproduces a legacy maximized placement
inside QA data, verifies normal startup and real caption minimize/maximize/restore
and relaunch, checks actual Windows icon fonts, and opens management pages in
wide/narrow light/dark layouts without changing settings in the personal profile.
It quits QA on completion. Window maximization is kept within the current app
session; saving geometry preserves the last normal window bounds.

## UX-6 quality and acceptance (source/UI complete; release gate separate)

D58 remains binding. Workspace motion reads `foundations.motion.panel` (260ms)
and `motion.ease`; legacy chat motion roles alias the same shared variables.
Live reduced-motion changes cancel painted animation and native bounds settling.
Management captures its persistent trigger before the chat becomes inert;
hidden chat menus do not own Escape. Narrow container layout uses shared spacing
and40px targets. No replacement palette/icon language is introduced.

`InterfaceRecovery` uses shared loading, alert and button components. Module/render
errors offer explicit interface reload. A ready-Core startup delayed15s offers
the same action; it never automatically restarts Core. The initial HTML/entry
script and the original UX5 blank-screen cause are outside this recovery proof.
Active conversation, drafts and scroll retain WebView-session ownership; new app
instances still start empty workbench tabs under D50. Identical idle speech status
must not notify every historical message; owner/error/playback changes still do.

Start with `docs/ux6_acceptance.md`, `docs/ux6_quality_report.md` and the per-action
JSON map. Raw files live under `.codex-local/ux-6`; the tracked aggregate preserves
source/binary identity and distinguishes earlier measurements from the final delta.
Do not relabel a prior native run as a newly tested binary. `--final` intentionally
fails while human/platform/package gaps remain; it never marks a stage complete.

Core suite: `python -m unittest discover -s tests -t . -v` from repo root.
The `-t .` is required to import the tests isolation package before runtime.
See the documented excluded-run incident; never count that run as isolated proof.
Frontend commands run in `desktop/`. Use focused regressions after a small delta,
and avoid repeated full matrices after the user asks to perform easier OS checks.

Native built trial: build frontend, then prepare the guarded QA app with
`pwsh -NoProfile -File scripts/prepare_ux6_native.ps1 -Mode built`.
For an existing owned profile, use `-ReuseProfile`; close that QA process first.
After automated UI checks, quit QA and reopen with
`pwsh -NoProfile -File scripts/restart_ux6_native.ps1 -Mode built -LiveProviders`,
then `node scripts/show_ux6_trial.cjs`. The marker identifies isolated data.
Provider keys are ephemeral; account files use private CODEX_HOME. Stop UI
automation before the user enters credentials. See the user checklist for
actual DPI/text size, screen reader, mic/audio, account and system chooser tests.

For Vite/native dev diagnostics use a frozen owned source snapshot and unused
ports, preserving existing1420/1439 processes. Native `invoke` is read-only;
attempted monkeypatch instrumentation is ineffective, not a product failure or
fault-injection PASS. Direct CDP leaves the Vite shared worker intact.

Unsigned packaging uses an owned ASCII checkout/data/build directory, the
canonical build script and explicit local-only allowance. NSIS zlib is an owned
QA config override, not a production default. Packaged smokes with explicit
private data bypass single-instance forwarding and create fresh evidence paths.
No installer execution, personal upgrade/uninstall, signing/release, PyQt removal
or Point17 follows from UX-6 acceptance work. The central source/UI closing review
is recorded in §42. Routine future packaging uses `scripts/build_and_package.ps1`
and `docs/building_tauri.md`, not a one-stage frozen UX-6 build helper.

Voice follow-up: `desktop_show_voice_overlay` must stay async. Tauri2.11.5
documents Windows deadlock when WebviewWindowBuilder runs in a synchronous
command. Composer awaits this command before polling voice completion; source
tests alone do not cover the native first-window creation. Use fresh isolated
`-Mode voice` QA and `verify_ux6_voice_overlay.cjs` for that bounded check. The
voice trial uses real mic/transcription with a deterministic model response and
no account. Keep the live-provider QA profile untouched; request only the three
speech/silence/cancel checks, not another broad matrix.

Canonical packaged smoke uses a child environment dictionary with other smoke
flags/source overrides removed. On current .NET, a restored null value can leave
an empty variable; inherited empty flags previously ran two smoke harnesses and
raced exit. Preserve recipe-only changes separately from compiled GUI/Core input
identity. Reuse passing proof only for exact unchanged executable/Core/artifact
hashes; rerun the failed case only. No GUI rebuild for a child-env recipe-only fix.
