# Point 16C source-derived parity audit and manual checklist

- Authority: the current PyQt source, not screenshots and not a React fixture.
- Current status: **AUDIT GAPS REMAIN**. No row in this document is a
  Point 16C acceptance claim.
- Evidence vocabulary: `WIRED` means an implementation path exists and was
  exercised; `AUDIT OPEN` means visual/state/source comparison is incomplete;
  `BLOCKING GAP` means a known source control, state or test is still missing.
- The production `ManagementCenter` is the only visual fixture target. A second
  hand-authored management UI is forbidden.

## Confirmed non-visual regression remediation — 2026-08-24

The following failures found during the reopened audit were corrected in the
production implementation. These are wiring/runtime fixes, not a claim that the
remaining one-to-one visual audit is complete.

| Confirmed regression | Source-derived correction | Current evidence |
|---|---|---|
| A full Diagnostic scan could freeze the Tauri window and Windows recorded an `AppHangB1`; the Doctor also reached PyQt-owned modules and a `ToolRegistry` object was counted incorrectly | the Rust Core proxy now runs blocking loopback I/O outside the UI thread; Diagnostic refuses to compete with an active agent run; Doctor uses Qt-free Canvas/email services and supports the real registry service | full Python 381/381, Rust 22/22, Qt-free import and focused gateway/Doctor regressions pass |
| Agent-loop details were rendered above and below the user message | run events and stored agent-process data are attached only to the assistant message that owns the process view | production React regression test passes |
| Tools treated the human-readable result of `list_skills()` as a collection, producing one Skill card per character | the Python tools snapshot now reads structured Skill registry entries and real custom/MCP files; trust changes persist through the Core authority and failed installs surface as errors | snapshot and authenticated route regressions pass; no one-character rows in the production fixture |
| Tools used generic cards instead of the PyQt section/category/row controls | the production Tools page now follows the PyQt category headers, compact rows, toggles, add/remove controls, refresh behavior and themed assets | production-component light-theme headless render inspected; light/dark/exact-geometry side-by-side audit remains open |
| Reset-all settings, full memory create/edit metadata, active-provider model refresh and automatic update polling were missing or incomplete | restored the source reset confirmation/backup flow, memory editor fields, immediate `setup_model()` after active-secret changes and background updater checks | frontend/Python tests and production build pass; live external-provider/updater states remain open |

No live desktop control was used for this remediation. Visual evidence was
rendered headlessly from the production component.

## Settings source-to-runtime map

| PyQt control/state | Tauri production control and asset | Control -> handler -> bridge | Python authority -> persistence -> reload | Current evidence/status |
|---|---|---|---|---|
| `SettingsPage` toolbar, advanced switch, search results and five registered pages | `SettingsView`, `ManagementCenter`; `search_icon_*`, `save_done_*` | search result -> `activateSearchResult` -> persisted advanced state -> section navigation -> highlight | `GET/PATCH /v2/settings` -> settings manager -> safe snapshot reload | Rendered interaction test covers advanced cross-page search; geometry/theme audit remains `AUDIT OPEN` |
| Provider selector and dynamic key help | `ProviderWorkflow`; no invented provider glyph | provider change -> `save("api_mode")`; metadata from `GET /v2/settings/schema` | provider normalization/setup and settings persistence -> model reload | Provider list/help URL/instructions are Core-derived; full provider-by-provider live audit is `AUDIT OPEN` |
| `_make_secret_link_row`, `_update_provider_key_help`, `קבל מפתח`, paste, delete and masked state | password row; `paste_icon_*`, `delete_icon.png`; real external link | paste/edit -> debounce or explicit `validateAndSaveKey`; provider validate -> secret PUT; delete -> secret DELETE | Python provider validator and secret authority -> masked safe snapshot -> reload | Rendered interaction proves help URL, paste, validation-before-write, write and delete. Paid-provider calls remain `AUDIT OPEN` |
| Core-requested missing API key dialog | `pendingApiKeyRequest` in `App`; production `ApiKeyRequiredDialog` with provider explanation/link and password entry | durable event -> dialog -> provider validate -> `POST /v2/runs/{id}/api-key` | `ConversationRunManager` waits in `waiting_for_input`, secret authority saves, run resumes; events remain secret-free | Rendered production-component test proves help, invalid rejection, valid payload and resume POST; manager/gateway tests prove wait/resume/no leakage. Visual state audit remains `AUDIT OPEN` |
| Codex sign-in status/login/check/logout/warning | source-height three-button row and warning | button -> management settings action | `CodexSignInProvider` -> persisted selected provider/setup_model -> reload | Route exists; real account/browser states and exact busy/error controls remain `AUDIT OPEN` |
| Searchable model picker, loading/error, per-result favorite star | `SearchableModelPicker`; `star_empty_*`, `star_filled_*` | model -> settings patch; star -> favorite list patch; provider change favorites selected model after loading | Python model discovery/reasoning contract -> selected provider model/favorites -> reload and composer | Source controls exist; popup keyboard/error/large-list comparison and composer refresh integration remain `AUDIT OPEN` |
| Reasoning effort | provider-specific select | change -> provider reasoning POST | model-family contract -> provider reasoning setting -> reload | `WIRED`; all provider/model combinations remain `AUDIT OPEN` |
| Autonomy and detailed capability matrix | three-state `source-segmented`; autonomy assets and `policy_icon_*` | segment -> settings patch | Python policy normalization and live tool policy -> persisted matrix -> reload | Rendered interaction proves segmented payload; full capability/default/profile round-trip remains `AUDIT OPEN` |
| Sandbox/output/allowed/MCP directories | source-shaped read-only picker; `folder_icon_*` and clear action | native path picker -> settings patch | Python sandbox/path validation -> persistence -> reload | Native chooser is wired; denial, multi-root and reload interactions remain `AUDIT OPEN` |
| Canvas and remote HTTPS images | two switches; remote control disabled while Canvas is off | switch -> coupled settings patch | Python stores `enable_visual_surfaces`, `enable_web_canvas`, and forces remote images false when Canvas is off | Coupling implemented; rendered disabled/reload test remains `AUDIT OPEN` |
| SSL summary/editor/system/custom/legacy/ack/import/test/apply | `SslWorkflow`; no generic gear/glyph | choose/import -> Rust path picker -> `ssl_import_ca`; test -> `ssl_test`; apply -> settings patch | Python validates/imports CA, builds pending-mode SSL context, persists explicit mode -> reload | Focused gateway test covers pending legacy mode/import; rendered interaction and light/dark source geometry remain `AUDIT OPEN` |
| Email secrets and connection test | source fields; `paste_icon_*`, `delete_icon.png`, `connection_test_icon_*` | autosave secrets/fields; button -> `email_test` | Python email settings/test -> persisted values and masked secrets -> reload | Routes exist; success/failure and provider auto-detection interaction tests remain `AUDIT OPEN` |
| Voice/TTS controls and preview | Core voice list, source sliders/switches; `speaker_icon_*` | voice load -> `/v2/audio/tts/voices`; preview -> `/v2/audio/tts` | shared Python voice/TTS service -> settings persistence/status | Voice list and preview route are wired; audio-device/live-state parity remains `AUDIT OPEN` |
| Theme, tray, hotkey | segmented theme, switches and text; legacy assets | setting -> Core patch plus narrow native invoke where required | Python preferences plus Rust Windows lifecycle -> reload | `WIRED`; all error/conflict/system-theme states remain `AUDIT OPEN` |
| Update status pill and check button | always-visible status pill; `check_updates_icon_*` | check -> signed Tauri updater; result -> settings patch; install -> signed updater/relaunch | Rust updater owns download/signature; Python stores check time/available version -> reload | Source status/loading persistence restored; updater unavailable/error/available/install states remain `AUDIT OPEN` |
| Advanced unified log viewer | lazy 500-line view, older rows, export count/redaction, export icon and confirmed clear | GET logs; native save; confirmed `log_clear` action | Python reads unified rotations, sanitizes export and clears through the same `clear_unified_log_file` authority -> reload | Confirmation and Core action integration test exists; the Tauri copy deliberately preserves the PyQt dialog wording and shared-helper behavior. Visual/export interaction audit remains `AUDIT OPEN` |

## Themed icon source map

| PyQt `themed_icon` / `set_themed_button_icon` intent | React mapping | State rule |
|---|---|---|
| back | `back_icon_light/dark.png` -> `legacyAssets.back` | theme-specific |
| search | `search_icon_light/dark.png` -> `legacyAssets.search` | theme-specific |
| saved state | `save_done_light/dark.png` -> `legacyAssets.saveDone` | theme-specific |
| paste secret | `paste_icon_light/dark.png` -> `legacyAssets.paste` | theme-specific; disabled with control |
| delete secret | `delete_icon.png` -> `legacyAssets.delete` | source has one shared danger asset |
| policy/safety | `policy_icon_light/dark.png` -> `legacyAssets.policy` | theme-specific; selected nav has CSS state |
| favorite model | `star_empty_*` / `star_filled_*` -> `legacyAssets.starEmpty/starFilled` | favorite state-specific and theme-specific |
| directory | `folder_icon_light/dark.png` -> `legacyAssets.folder` | theme-specific; disabled with picker |
| email test | `connection_test_icon_*` -> `legacyAssets.connectionTest` | theme-specific; busy/disabled CSS state still under audit |
| TTS preview | `speaker_icon_*` -> `legacyAssets.speaker` | theme-specific; playback state under audit |
| update check | `check_updates_icon_*` -> `legacyAssets.checkUpdates` | theme-specific; disabled while checking |
| log export | source fallback `export_log_icon/export_json_icon` -> `legacyAssets.exportJson` | theme-specific |
| navigation usage/tools/memory/tasks/doctor | matching tracked light/dark assets in `legacyAssets` | no icon is rendered where the PyQt registration has no icon |

No emoji, browser glyph, generic gear or letter placeholder may replace a
tracked asset in a source-owned control. Missing source icons stay absent.

## Whole-product reverse audit queue

| Surface | Required source/state audit | Status |
|---|---|---|
| Window, RTL, light/dark, title bar, tray/single instance/notification | hierarchy, exact geometry/assets, normal/maximized/narrow, hover/pressed/disabled, activation and persisted placement | `AUDIT OPEN` |
| History/sidebar/profile menus | empty/loading/error/search, pin/rename/export/delete, active/run/approval/unread, collapse/reload | `AUDIT OPEN` |
| Chat/timeline | every message role, Markdown/code/link, attachments, tool input/output, agent reports/time, error and interruption | `AUDIT OPEN` |
| Composer/favorite spinner/voice/approval | idle/listen/send/stop, model loading/favorites/reasoning/quota, autonomy/FastMode, attachment and keyboard paths | `AUDIT OPEN` |
| Workspace and Workbench | wide/narrow/splitter, tab order/persistence, files/artifacts/preview/terminal lifecycle | `AUDIT OPEN` |
| Browser | persistent/Guest separation, same-visible-target, chrome/actions/menus/import/privacy/error and no external browser HWND | `AUDIT OPEN` |
| Canvas | history/open/close/layout/actions, sandbox/CSP, remote-image policy and reload | `AUDIT OPEN` |
| Tools/MCP/Skills | catalog empty/loading/error/trust/install/pin/enable/remove/refresh and warnings | `AUDIT OPEN` |
| Memory | masked/reveal/filter/page/details/create/edit/pin/bulk/archive/restore/import/export/clear | `AUDIT OPEN` |
| Tasks | empty/list/loading/error/create/edit/schedule/routing/cancel/retry/resume/delete/result | `AUDIT OPEN` |
| Usage, Diagnostic, Trace, About/legal/update | every source state/action, privacy defaults, progress/cancel/repair, legal first-run gate and persistence | `AUDIT OPEN` |

## Manual PyQt/Tauri side-by-side checklist

Use a test data directory for Tauri and do not install over the active PyQt
installation. Put both windows on the same monitor, size and Windows scale.
Repeat visual rows once in dark and once in light mode.

1. Window: compare initial size, title bar height/order/icons, corners, minimum
   size, maximize/restore, close-to-tray and reopen state.
2. Sidebar: compare expanded and collapsed widths, logo/collapse hover, new-chat
   row, search/clear, empty/no-result/populated history, active/pinned/unread/
   running/approval rows, row menu order and profile menu order.
3. Chat: compare empty greeting; user, assistant, system and error messages;
   long-message collapse; code block copy/save; web/file links; image/file
   attachments; agent process and tool details; copy and TTS actions.
4. Composer: compare empty/listening/text/attachment/running states, Enter and
   Shift+Enter, favorite-model hidden/loading/populated popup, star changes,
   reasoning, Codex quota, autonomy, local FastMode and drag/paste/remove.
5. Missing key: start a run with an unconfigured provider. Confirm the Tauri
   dialog contains the same provider explanation and `קבל מפתח` URL, rejects an
   invalid key without saving, saves a valid key, resumes/retries the run and
   does not add the key to chat/history/log output.
6. Management shell: compare 64 px header, back control, 250 px menu, group and
   item order, selected/hover states, scroll behavior and every mapped icon.
7. AI Settings: compare provider order, Codex row, dynamic key link/instructions,
   paste/delete/validation/error/saved states, model loading/search/favorites,
   reasoning, local URL/FastMode, title mode and Tavily row.
8. Security Settings: compare both segmented profiles, custom switch, full
   capability matrix, all approval switches, sandbox/output/write-directory
   pickers, warnings and reset/reload behavior.
9. Tools Settings: compare browser/computer/MCP/Skills/Canvas controls, dependent
   remote-image disabled state, email ordinary/advanced fields, secrets and all
   email test states.
10. Appearance Settings: compare theme segments and immediate icon swap, TTS
    voice/loading/volume/preview, listening sliders and switches, hotkey/tray/
    notification controls, update status/check/available/install states.
11. Advanced Settings: compare collapsed/expanded SSL for all three modes,
    certificate import details, test/ack/save/cancel/error, every timeout/budget/
    unlimited slider, MCP paths, unified log actions/export options/text area and
    reset-with-backup.
12. Workspace management: compare root display/change, default Workbench/browser
    actions, persisted sidebar/Workbench state and error copy.
13. Usage, Tools, Memory, Tasks, Diagnostic, Trace and About: traverse every
    empty/loading/error/populated/action/confirmation branch listed in the
    reverse audit queue; close and reopen each page to verify authoritative reload.
14. Workbench: open duplicate Files/Browser/Terminal tabs plus singleton Canvas/
    Artifacts; reorder, switch, close, reopen and reload. Exercise one safe file
    preview/open, one terminal command/restart and one artifact.
15. Browser: compare persistent and Guest sessions separately; navigate/back/
    forward/reload/home, menus/library/download/privacy/import, hide/reopen and
    same-target persistence. Confirm no external Chrome/Edge/Brave window opens.
16. Canvas: open from chat, move/activate a control, close/reopen from history,
    test blocked navigation/download/file access and remote-image opt-in.
17. Persistence: change one setting in every category, pin a conversation/model,
    open Workbench tabs, close to tray, restart Core/Tauri and confirm all state
    reloads from the Python/native authorities without duplicated or lost data.

Any mismatch keeps Point 16C blocked and must be added as a named row above.
