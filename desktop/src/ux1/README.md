# UX-1 · full isolated interactive prototype

Design authority: SMARTI-UI-UX-2026 in `docs/ui_ux_redesign_plan.md`.
Current direction and evidence: execution ledger sections 20–21. Section 21
records the user's v7 direction acceptance and the independent closing review.
Sections 14–20 preserve the dated candidate history. UX-2 follows the accepted
prototype as its visual reference; its production foundations are a separate stage.

From `desktop`, run `npm run dev:ux1`, then open
<http://127.0.0.1:1432/ux-1.html>. An existing Tauri server on 1420 is independent.
The normal production build uses `index.html` and excludes this DEV-only entry.

Start with the visible `העיצוב החדש` guide. It explains the proposed structure
and links to the three representative work modes. Direct entries:

- `ux-1.html?v=7&screen=chat`: uninterrupted conversation, current answer in view.
- `ux-1.html?v=7&screen=split`: conversation right, empty tool launcher left.
- `ux-1.html?v=7&screen=settings`: dedicated management navigation, without chat history.

Use the UI as you use Smarti:
expand the activity, tools and input/output; copy or download code; open the
Workbench; explore every management page and enable advanced settings.

## Product fidelity

- `RichMessage`: actual nested process, reports, tool calls/results, Markdown,
  tables, code copy/download, message copy, TTS status and canvas cards.
- `SettingsSurface`: an explicit UX-1-only derivative of `SettingsManagement.tsx`.
  Provider/setting state, validation and handlers are unchanged; the screen adds
  topic groups, one heading owned by `ProductManagement`, and a
  composed search/advanced row. Routine save badges are omitted; errors and
  explicit validation/reset/update outcomes remain. It retains the full catalog,
  search, advanced settings, secret validation, reasoning, favorites, policy,
  SSL, email, speech, appearance, logs, resets and update controls.
  Reconcile this derivative into shared controls after direction acceptance;
  never ship it as a second settings implementation.
- `WorkspaceSurface`: explicit UX-1 derivative of WorkspaceView, with the same
  preference paths, Core PATCH, browser count/status and file/browser actions.
  Unified switches and three topic groups replace nested checkbox cards.
- `MessageSurface`: React-owned content references are inserted before the actual
  RichMessage action footer. Copy/TTS follow all outputs; the source renderer is
  unchanged. Approval continuation retains its DOM and expanded process state.
- Actual `MemoryView`, `TasksView`, `ToolsView`, `UsageView`,
  `DiagnosticsView`, `LogsView`, `AboutView`, `LegalAgreement`, `BrowserPanel`
  and `CanvasPanel`.
- `ProductPanels.tsx` preserves the technical file, artifact and terminal flows
  from `WorkbenchPanels.tsx`. It is an explicit temporary derivative with PNG
  tree icons. Reconcile it with the source component before any UX-4 migration.
- Candidate navigation, conversation actions, composer and document editing use
  local React state. The history supports creation, rename, pin, delete, export,
  content search, retained drafts and scroll. Workbench tabs can be added,
  selected, closed and reordered.
- New, original outline artwork replaces legacy icons throughout the demo.
  63 drawings are rasterized to 126 transparent light/dark PNGs. Rebuild with
  `python scripts/generate_ux1_icons.py` (Pillow); no SVG/font icons or additional
  UI dependency. The Smarti brand logo remains. Reused source controls receive
  scoped artwork replacement without replacing their handlers or semantics.
- General Workbench opening returns to its last active tab, or a launcher for
  Browser, Files, Terminal and Artifacts when no tabs remain. Canvas opens only
  from its dedicated chat card. Artifact/browser references open their content
  targets and reuse an existing matching tab. Each tab has a left X on hover or
  keyboard focus (always visible on touch), with Delete as a keyboard action.
  Expansion/shrink is a direct button; the icon-only global opening button also
  closes the Workbench. Closing it preserves tabs; reloading ends the demo session
  and clears them. Artifact list lives in the document menu; a generic Artifacts
  tab starts on the source list. Document edit/read has one control; copy/download
  live in its contextual menu.
- `ModelMenu`: Composer's two-column technical behavior with new candidate
  styling. Providers are on the right; the left shows their favorites. Browsing
  does not select a model. Favorite order and active fallback, keyboard transfer,
  reasoning and unknown account quota are preserved. Settings favorites share
  the same synthetic model keys across all 18 provider fixtures.
- Provider/model/history items have a single-line hover/focus marquee, disabled
  by reduced motion. All 36 demo models expose a reasoning control: the synthetic
  provider contract supports it; production must keep real provider capability
  checks. Policy is global in the synthetic settings and sits beside +. Empty
  new chats remain drafts until first submission, which inserts them at the top.
- Model delay defaults to 5 seconds, showing the source `חושב...` component.
  Change it in `תרחישים` (1/5/12/30 seconds). Stop invalidates delayed callbacks.
  Table and per-card memory/task actions use accessible icon-only controls.

## Isolation and simulated behavior

`main.tsx` installs `DemoBackend` before importing any product runtime/UI.
It replaces the Tauri bridge even when a real bridge is present. Core requests,
provider authentication/validation, settings, diagnostics, file pickers,
terminals, native menus, browser commands and speech operate only on synthetic
state. Unknown bridge paths fail explicitly and are recorded in a trace.

Window-local in-memory Storage objects replace local/sessionStorage for reused
screen caches. They cannot read or write the real browser storage. All demo
state resets on reload. The adapter never stores a supplied API-key value.

Downloads create real browser downloads containing only synthetic code, text,
JSON, PNG or PDF. Browser content and captures are synthetic, and commands do
not open sites, accounts, OS processes, files or microphone services.
Code/build or headless browser results do not prove native Tauri/WebView2,
Windows DPI, screen-reader, real-model or packaged-release behavior.

Candidate styles import the source stylesheet only in this separate entry,
then scope the proposed appearance to `.ux-prototype`. Do not ship them as a
second production stylesheet. UX-2 is ready to implement the shared foundations.

## Accepted screen language

The v7 stylesheet was accepted as one coherent design. Neutral surfaces,
quiet borders, a restrained blue accent, natural button widths and clear text
hierarchy apply to conversation, documents, settings and all management pages.
Legacy screen geometry is not the design authority; existing controls supply
interaction mechanics and the capability inventory.

Chat and split view have different compositions but preserve drafts and activity.
Management has its own navigation in three groups: preferences, work, system.
Settings use labelled topic groups rather than a continuous old field layout.
Task creation opens from `משימה חדשה`; the complete existing form and its handlers
stay mounted. Narrow management uses horizontally scrollable navigation; narrow
Workbench shows one work surface and restores chat on close. No settings are
removed to reduce visual density.

## Reproducible verification

At the repository root, with the server running:

`node scripts/verify_ux1_prototype.cjs`

Playwright can be resolved via the bundled Node runtime's `NODE_PATH`; no new
project dependency is required. The script blocks remote traffic and verifies
source process folding/content, actual code download, every management route,
provider workflows, source CRUD/diagnostic actions, raster assets, narrow layouts,
composer reachability, drafts, large conversations and bridge isolation, plus
control density, duplicate prevention, contextual document actions, new source
artwork and actual workspace closing/restoration across the layout matrix.
Results/screenshots are written under `.codex-local/ux-1/qa/full` by default.
Pass a separate output directory as the third argument to preserve earlier
results. The original v7 results use `feedback-next16/full`; independent closing
evidence uses `acceptance-2026-10-04/full`. The checks also verify separate management
navigation, one page heading, real setting groups, the physical RTL switch
position, progressive task creation and the three representative guide routes.

`node scripts/verify_ux1_feedback.cjs` records the previous v5/16-point round;
its expected empty-chat and Workbench interactions are historical. Its previous
evidence remains in `feedback-16`. The v6 verification is
`node scripts/verify_ux1_feedback21.cjs`, historically covering all 21 additional corrections:
delayed source thinking, all models' reasoning, single-line motion, empty drafts,
chronological insertion, brand swap, global policy, content references and tab
lifetime/closure, direct expansion, settings without save badges, semantic action
icons, theme icons, interpolated sliders and clear update controls. It also checks
physical RTL geometry, reduced motion, CSV download, autosave and action handlers,
plus light/dark layouts at 360/900/1380. Evidence is written to
`.codex-local/ux-1/qa/feedback-21/focused`.

The previous 16-point round included
physical arrow directions, fixed history controls with real overflowing history,
centered rename save/cancel, matching switches, compact numbers, range keyboard
and pointer saving (including unlimited sentinel), model favorites and selection,
all provider catalogs and narrow light/dark popups. Evidence is written to
`.codex-local/ux-1/qa/feedback-16/focused`. Native range thumb visibility is reviewed
in screenshots; Chromium does not expose its shadow pseudo-element reliably via
`getComputedStyle`. Earlier evidence folders are preserved.


## Accepted v7 reference

`node scripts/verify_ux1_feedback_v7.cjs` covers the latest 16 requests (98 checks),
with evidence in `.codex-local/ux-1/qa/feedback-next16/focused`. The broad current
script passes 472 checks across 132 layouts. Its labels reflect v7; v5/v6 focused
scripts retain historical UI labels and earlier reports.

Popovers have no X, toggle from their trigger, dismiss on outside click, and
preserve Escape/focus return. Only actual modal dialogs contain focus. The brand
toggles the sidebar in both states at identical coordinates; collapsed new chat
stays aligned and management actions form a bottom column ending in Settings.
Provider counts and review annotations are removed. Fixtures and commands stay
isolated even though the UI omits synthetic/demo warnings at the user's request.
This does not claim real provider, audio, filesystem or native execution.

Long names travel linearly at 72px/s without endpoint dwell. User messages use
four rounded corners, physical right alignment and the light blue action tint.
Newly sent bubbles animate for 180ms once, then consume their entry flag; existing
history and reduced motion remain still. Table buttons use centered 18px PNGs in
40px squares. Refresh/clear and memory toolbar actions retain source handlers,
accessible labels and tooltips. Generic success notices are quiet; errors and
meaningful explicit results remain visible. UX-1 is complete within the isolated
prototype scope; UX-2 is ready. Use ledger section 21 for the current evidence,
open product checks and the binding handoff. The closing focused run is in
`.codex-local/ux-1/acceptance-2026-10-04/focused-ready`.

UX-2 must turn this reference into shared semantic tokens and React controls,
including explicit icon props and message content slots. DOM decoration,
temporary source derivatives and the mock bridge are prototype techniques;
they must not become parallel production implementations. Real provider
capabilities, policy persistence, chat state and native ownership remain owned
by their existing Core/Rust contracts and the later implementation stages.
