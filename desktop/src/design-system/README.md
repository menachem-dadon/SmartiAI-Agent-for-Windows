# Smarti shared design system · UX-2

Authority: `docs/ui_ux_redesign_plan.md`, accepted UX-1 v7 and ledger §21–24.
UX-2 is complete within the shared-foundation scope; UX-3 is ready. Closing review,
the shared chevron baseline and the binding product handoff are in ledger §24.
Import product foundations from `src/design-system`; never from `src/ux1` or `src/ux2`.

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
personal preferences. Set it once around the converted surface. Its explicit
overlay host receives menus/tooltips through React portals; triggers are owned
refs. There is no DOM search for anchors, MutationObserver or raster replacement.
Keep the provider outside transformed/clipped native surfaces; a WebView2 window
still needs its existing hide/preview/final-bounds/show lifecycle.

| Component | Contract / integration responsibility |
|---|---|
| Button / IconButton / Icon | Native button props and explicit semantic icon; loading disables activation and exposes aria-busy. Icon actions have names and focus/hover tooltips. A round primary IconButton keeps the accepted blue/white action treatment in both themes, separately from text-button accent roles. Caller retains duplicate-send guards and domain cancellation. |
| Field / SearchField / NumberField / Textarea | Native control props, label, unique ID, hint/error associations and optional ref. Textarea defaults to dir=auto for Hebrew/English writing; callers may override it. Numbers stay short; parsing, validation, secrets masking and persistence stay with existing handlers. |
| RangeField | Controlled numeric value and synchronous onValueChange; native pointer/keyboard behavior, textual output and filled track. Caller supplies min/max/step/formatValue; 0 has no invented meaning. |
| Switch | Controlled checkbox with switch semantics; Space and disabled remain native. Track 44×26 inside a 44×40 target. Active thumb physically left in RTL, right in LTR. |
| Menu | Explicit item callbacks/disabled/tone; click toggles, outside interaction, Escape, Home/End, arrows, single-character lookup and Tab. Focus returns for Escape/selection; outside click preserves destination focus. No X. |
| Dialog / ConfirmDialog | Controlled open/onClose. Native HTML dialog provides modality; explicit Tab/Shift+Tab looping retains focus in the app. Unique title/description IDs; optional initialFocus; previous focus restored. A dialog-owned overlay host keeps tooltips in the top layer. Confirm focuses cancel, caller controls busy/error and closes only on actual success. No action is synthesized. |
| Tooltip | Focus/hover, associated description, hoverable overlay, Escape. Essential actions remain present on touch. Tooltip text cannot be the sole accessible name. |
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
