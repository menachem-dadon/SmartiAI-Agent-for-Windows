# Tauri Points 7-12 legacy-source UI parity specification

- Gate: Point 9A
- Binding source date: 2026-08-23
- Scope: Workspace shell, conversation drawer, daily chat, rich messages,
  composer, attachments, approval, activity, voice and TTS surfaces, plus
  Settings, management-center pages and Files/Artifacts/Terminal Workbench.
- Rule: PyQt composition and shared helpers are authoritative. Screenshots are
  validation evidence only; they are not a substitute specification.

## Source inventory and reading boundary

The audit followed the enclosing composition rather than copying isolated CSS.

| Legacy path | Source read for this gate | Shared authority used |
|---|---|---|
| `smarti/app.py` | Complete application bootstrap, global RTL/theme, splash-to-`ChatWindow` composition | application font, theme, direction, startup ownership |
| `smarti/chat.py` | `WelcomeWidget`, `PillInputFrame`, `PinnedActionButtonHost`, `CodeBlockWidget`, `AttachmentTile`, `AttachmentPreviewStrip`, `AgentToolDetailWidget`, `AgentToolGroupWidget`, `MessageBubble`, `ChatMessageContainer`, `ConversationActivityIndicator`, `ChatHistoryPage`, `VoicePulseWidget`, `VoiceListeningOverlay`, complete `ChatWindow` Points 7-9 composition and state handlers | layout hierarchy, state rules, menus, actions, dynamic widths, shortcuts, text and styling |
| `smarti/workspace_ui.py` | `WorkspaceWindowTitleBar`, `SidebarNavButton`, `WorkspaceSidebar`, enclosing Workbench splitter sizing/visibility | title controls, sidebar hierarchy, collapse behavior and responsive ownership |
| `smarti/ui_controls.py` | `DropdownPillButton` paint/layout and shared input controls used by the audited surfaces | centered icon/text/arrow group, elision and enabled states |
| `smarti/ui_styles.py` | complete palette/export model plus application, tooltip, dialog and `QMenu` helpers used here | exact light/dark tokens, 12 px popup radius, menu item geometry, focus/hover/pressed colors |
| `smarti/ui_pages.py` | complete `ActionConfirmDialog` composition, size calculation, risk mapping, keyboard/default-button rules | approval dialog hierarchy and states |
| `smarti/history.py` | session/run/attention/approval projections consumed by history and chat | runtime priority, unread and pending-approval states |
| `smarti/workers.py` | `VoiceWorker` and `TTSWorker` state/status behavior | listening and playback state vocabulary |
| `smarti/ui_pages.py` | Settings, Task Center, Tools, Diagnostic, Usage, Developer Trace and About page composition | section hierarchy, Hebrew labels, state/actions and privacy defaults |
| `smarti/memory_ui.py` | Memory page, detail/reveal/edit/archive/delete dialogs | masked-first memory behavior and explicit sensitive-data reveal |
| `smarti/workspace_ui.py` | `WorkspaceWorkbench`, file tree/preview, artifacts and terminal panels | tab lifecycle, RTL tree/preview split and terminal interactions |
| `smarti/managers.py`, `smarti/agent/productivity_tools.py`, `smarti/doctor.py` | settings/memory/tool persistence, task semantics and diagnostic repairs | Python authority and mutation semantics |

The matching implementation is in `desktop/src/App.tsx`, `Composer.tsx`,
`RichMessage.tsx`, `App.css`, `legacyAssets.tsx`, `legacyUiParity.ts`,
`workspaceState.ts`, `chatState.ts` and their colocated tests.

## Binding source values

`desktop/src/legacyUiParity.ts` is the executable value ledger. Important
source-derived values are: 36 px title bar; 286/58 px expanded/collapsed
sidebar; 300 ms sidebar animation; 1040 px chat-body maximum; 920 px usable
responsive threshold; 480 px Workbench minimum and 520 px side-by-side chat
minimum; 28/22 px composer side/bottom gutters; 112 px composer minimum;
40.5 px composer radius; 52 px action control with 7 px bottom pin; 42 px
attachment control; 10 px control gap; 76% minus 30 px user-bubble maximum;
52 px assistant inset; 36/40 px message action/control-row geometry; six-line
user-message collapse; 68 px history rows with 10 px spacing; 24 px activity
indicator; and 342/298 by 70 px voice overlay sizes.

## Traceability matrix

`MATCHED` means source value and state behavior are represented in the current
React/CSS implementation and guarded by a named deterministic check.

| Surface/state | Legacy source specification | React/CSS implementation and check | Status |
|---|---|---|---|
| Global RTL and themes | `app.main`, `apply_app_theme`, `THEME_PALETTES`; app RTL, Segoe UI, exact dark/light palette | `App`, `useTheme`, `.theme-dark/.theme-light`; `designSystem.test.ts`, `legacyUiParity.test.ts` | MATCHED |
| Window title bar | `WorkspaceWindowTitleBar`; LTR, 36 px, 46x36 controls, minimize/maximize/restore/close, double-click maximize | `WindowTitleBar`, `.window-titlebar`; source labels and native Tauri window calls | MATCHED |
| Workspace order | `QSplitter`: Workbench left, chat center, sidebar right; Workbench starts at zero | `workspaceColumns`, RTL grid; `workspaceState.test.ts` | MATCHED |
| Responsive Workspace | usable width below 920 collapses sidebar; open Workbench owns the narrow surface and chat is hidden; at wide/full size the user-directed reading-density correction gives chat about 35vw (440 px floor) and the Workbench the remainder; native browser bounds serialize resize updates so an older animation frame cannot overrun the chat | `workspaceColumns`, `workspaceIsNarrow`, `.has-workbench`, `BrowserPanel` latest-bounds synchronization; workspace tests and minimal 1536 px live check | MATCHED + USER ADJUSTMENT |
| Sidebar shell | `WorkspaceSidebar`; 286/58 width, 10/12/10/10 margins, 8 gap, original logo/assets and profile at bottom | `conversation-drawer`, `drawer-head`, `legacyAssets`; parity/component tests | MATCHED |
| Sidebar collapse | brand/collapse controls, collapsed logo changes to expand icon on hover, history hidden, manual state persisted at `ui_preferences.workspace_sidebar_collapsed` | `toggleConversationDrawer`, rail hover CSS, `/v2/settings` patch | MATCHED |
| New conversation | 42 px RTL nav row, original icon/text and action | `.new-chat-button`, `createConversation`; UI/workspace tests | MATCHED |
| History search | LTR frame around RTL field, 20 px radius, 48 px height, original search asset/text, clear and 40 ms delayed query | `.conversation-search`, `legacyUi.historySearchDebounceMs`, `legacyUiParity.test.ts` | MATCHED |
| History rows | 68 px, 10 px gap, gradient/active border, title 14/800, metadata 11, pin, 28 px action menu | conversation row JSX/CSS and real session projection | MATCHED |
| Activity states | `runtime_status` priority: approval, cancelling, running, queued; then unread; 24 px spinner/approval, 10 px unread dot and source tooltips | `activityState`, `.conversation-activity`; `legacyUiParity.test.ts` | MATCHED |
| Conversation menu | pin/unpin, rename, JSON export, separator, delete; RTL 12 px rounded popup and 9/30/9/10 item padding | `.conversation-menu`, internal rename/delete dialogs; component/parity tests | MATCHED |
| Profile menu | usage, settings, diagnostic, separator, about; RTL and anchored above profile control | `.profile-menu` and source text/order | MATCHED |
| Chat top bar | 58 px LTR row, menu then Workbench control then optional update then RTL elided title; original assets | `.chat-toolbar`, `.chat-toolbar-controls`, `App` | MATCHED |
| Empty chat | centered `WelcomeWidget`, max 860, source greeting, 26 px bold and RTL wrapping | `.legacy-welcome`, `displayName` greeting | MATCHED |
| Timeline | chat body is centered and capped to a readable `clamp(520px,35vw,760px)` when Workbench is closed, fills the approximately 35vw chat column with 14 px gutters when open, keeps RTL top alignment and the older-page control | `.chat-stage`, `.message-list`, `.has-workbench`, `loadOlder` | USER ADJUSTMENT |
| User message | right anchored, 76% minus 30 px max, 20/16 margins, 22 px radius, exact theme gradients/border/text/shadow | `RichMessage`, user CSS; parity values and chat component tests | MATCHED |
| Background-task prompt | user prompt is explicitly marked `⚡ משימת רקע` and uses the source orange translucent surface/border instead of the ordinary user gradient | `RichMessage` metadata projection and `.is-background-task`; durable-history live state | MATCHED |
| Assistant/system/error | assistant transparent, 10/8 margins and 52 px inset; system is transparent/muted; errors use danger text without an extra card | `RichMessage` role/error classes | MATCHED |
| Long user message | natural rendered height or more than six source lines; six-line cap, opacity fade, expand/collapse action and labels | `ResizeObserver` measurement, mask, `legacyUi.userCollapsedLines` | MATCHED |
| Markdown and mixed direction | rich/selectable text, RTL paragraphs, isolated LTR code/paths, safe HTTP/HTTPS/mail links and percent-encoded `file:///` links; opening routes through a narrow Rust command that rejects missing, relative and executable local targets | `prepareMessageMarkdown`, `safeChatHref`, `open_chat_link`; React and Rust link-policy tests | MATCHED |
| Code block | 14/12/14/16 margins, 8 gap, 22 radius, exact dark/light surfaces, 28 px copy/download buttons, language and 340 px maximum editor | `.code-frame`, source assets and handlers; `chatUi.test.tsx` | MATCHED |
| Sent attachments | attachments precede final text; images 180-360 and contain-fit; files 300-430x72 with 50 px preview | `RichMessage` attachment-first hierarchy and attachment CSS | MATCHED |
| Pending attachments | 82 px horizontal strip; 68 px images; 270-430x68 files; 22 px remove action | `Composer` pending strip and source geometry CSS | MATCHED |
| Agent process | transparent right-aligned RTL group above the assistant answer; durable `metadata.agent_process` and active run events restore reports, ordinary/standalone tool loops, exact elapsed work time, live shimmer and final collapsed state | `agent-process`, `processRows`, active-run event replay and synthetic assistant placeholder; chat component test and durable-history live state | MATCHED |
| Tool detail | per-tool running/finished/error label; nested input/output panels, 8 px radius, RTL labels and LTR selectable data | `toolViews`, `.agent-tool-row`; representative event component test | MATCHED |
| Message actions | reserved 40 px sibling row outside the message bubble; copy, user collapse or assistant TTS; 36 px controls, 6 gap, hover/focus reveal; no non-source retry action | `chat-message-row`, `message-actions`, `RichMessage`; explicit sibling/order assertions in `chatUi.test.tsx` | MATCHED |
| TTS | assistant-only start/stop, source labels/icons, active danger state, Core-owned `/v2/audio/tts` and status polling | `RichMessage.speak`; component and control-plane tests | MATCHED |
| Composer frame | centered readable-width frame matching the user-adjusted chat column, 112 minimum, exact 40.5 radius, 10/8/12/8 margins, gradient/hover/border/shadow | `.composer`, `.has-workbench`, `legacyUi`; parity test | MATCHED + USER ADJUSTMENT |
| Composer input | right-aligned source placeholder, automatic direction once text exists, 17 px font, 4/10 padding, Enter sends and Shift+Enter inserts newline, disabled during run | `Composer` textarea and keyboard handler; `chatUi.test.tsx` | MATCHED |
| Send/listen/cancel | 52 px bottom-pinned action, mic when empty, send when text/attachment, stop while running, source gradients/tooltips and disabled state | action host/button classes and state selection | MATCHED |
| Favorite-model control | hidden with no favorites; centered text/arrow; source dynamic bounds; main popup contains current-model reasoning choices, Codex quota and nested provider/model menus; the child overlaps the parent by 2 px so pointer travel has no hover-dead gap; keyboard/Escape and short-window in-flow behavior remain | `model-quick-pill`, `model-provider-submenu`; `chatUi.test.tsx`, short-height media rule | MATCHED |
| Codex quota | shown only for active `openai_codex_signin`; loading/error/refresh states, 15 s cache guard, 60 s external-usage refresh, plan, 5-hour/week remaining bars and reset text | `Composer.refreshQuota`, `.codex-quota-card`, authenticated `/v2/providers/openai_codex_signin/quota`; React and Core integration tests | MATCHED |
| Autonomy control | source icon/text/arrow and three profile actions; custom display preserved; styled popup and persisted Core update | `autonomy-quick-pill`, `autonomyLabels`; parity/component tests | MATCHED |
| Local FastMode | visible only for local provider, 122x42 control, source label/tooltip/checked colors and persisted setting | `.local-fast-mode`, `changeLocalFastMode` | MATCHED |
| Voice/listening | mic idle action; listening title/status, cancel/open controls, original 42 px animated asset and 342/298x70 surface; error/disabled statuses | `Composer` recognition state and `.voice-listening-overlay`; source asset and parity test | MATCHED |
| Approval | modal 430x340 target, 14 px card margin, exact hierarchy/text/risk variants, selectable details, hint, reject/accept, default accept and modal focus | approval JSX/CSS, `autoFocus`, `/v2/approvals/.../resolve` | MATCHED |
| Shared icons/tooltips/menus | themed legacy assets; 12 px popup radius; 14 px popup font; hover/pressed/selected states; no generic browser prompt/confirm | `legacyAssets`, popup CSS, internal dialogs | MATCHED |
| Smarti scrollbars | all Smarti-owned scroll surfaces use thin rounded accent-tinted thumbs, transparent tracks/corners and theme-aware hover color instead of generic WebView controls | global standard/WebKit scrollbar rules; minimal dark-theme live check | MATCHED |

## Points 10-12 traceability extension

| Surface/state | Legacy/Core source specification | Tauri implementation and deterministic check | Status |
|---|---|---|---|
| Settings shell | Settings categories, Hebrew labels, search, advanced fields and restart implications | `ManagementCenter.SettingsView`; Core-derived `/v2/settings/schema`; `managementUi.test.ts` and gateway schema test | MATCHED |
| Providers and secrets | provider choice/model discovery/connection validation; secrets remain in Core persistence | masked metadata plus explicit `PUT/DELETE /v2/settings/secrets`; no plaintext read route | MATCHED |
| SSL and appearance | secure trust modes, legacy-insecure warning, system/light/dark persistence | schema option controls, warning and persisted `ui_preferences.theme_mode` | MATCHED |
| Task Center | one-time, interval and weekly schedules; edit/cancel/retry/resume/delete and conversation routing | Core-backed task actions and internal edit dialog | MATCHED |
| Memory | masked-first list/search/details, explicit reveal and CRUD/archive lifecycle | Core-backed memory routes and explicit reveal control | MATCHED |
| Tools/extensions | built-in enablement and extension discovery/trust/install/refresh | Core registry/settings actions for built-ins, Python tools, MCP and Skills | MATCHED |
| Diagnostics | quick/full scan, technical detail and user-confirmed repair | background Core diagnostic execution, long native proxy timeout and internal confirmation dialog | MATCHED |
| Usage, logs and About | cached usage, privacy-first trace/export and version/runtime information | cached-first usage, redacted-by-default log route and Core version snapshot | MATCHED |
| Workbench tabs | on-demand tabs with duplicate file/browser/terminal workflows | `WorkbenchPanels.WorkbenchSurface`; existing browser panel plus multi-tab state | MATCHED |
| Scoped Files | selected root, RTL tree right/preview left, traversal-safe previews and external open | `WorkspaceScope` realpath containment, symlink/size/depth policy, React file panel | MATCHED |
| Preview formats and artifacts | text/Markdown, media/PDF/Office and generated-file discovery | safe Markdown rendering, data previews, cached Office PDF and artifact inventory | MATCHED |
| Multiple terminals | independent session creation/input/stream/restart/close and shutdown cleanup | `TerminalRegistry` hidden UTF-8 PowerShell sessions; live loopback integration test with Hebrew cwd | MATCHED |

## Deterministic state coverage

- Empty/populated history and no-result copy are covered by Workspace/component
  rendering and Core conversation tests.
- Active/inactive, pin, running, cancelling, waiting-for-approval and unread
  projection is covered by `activityState` plus existing Core history/run tests.
- User/assistant/system/error, Markdown, code, attachment and tool-running states
  are represented by `RichMessage` classes and component fixtures.
- Idle/send/listen/run composer selection, favorite visibility, reasoning,
  nested provider/model menus, Codex quota loading/error/data branches,
  autonomy/custom labels, local-only FastMode and pending attachments are
  deterministic React branches.
- Narrow/wide, collapsed/expanded and Workbench-open transitions are pure state
  helpers/reducer branches.

## Deviation ledger

There are no open user-visible deviations in the Points 7-13 surfaces. The DOM,
WebView2 speech-recognition adapter and Tauri native-window calls necessarily
replace Qt objects internally, but they do not introduce a listed visual
exception: source hierarchy, copy, assets, sizes and interactive states above
remain the binding behavior. Point 13 keeps Canvas in the stable Workbench tab,
preserves the legacy action confirmation/layout contract and replaces Qt/
WebEngine with a CSP-constrained `sandbox="allow-scripts"` iframe. The full
Browser and Windows support boundaries are recorded separately in
`tauri_browser_support_matrix.md` and `tauri_windows_integration.md`; packaging
remains outside this source-parity gate.

## Points 13-15 traceability extension

| Surface/state | Legacy/Core source specification | Tauri implementation and deterministic check | Status |
|---|---|---|---|
| Canvas history/model | `canvas_model.py`, active/closed history, layout and context injection | authenticated per-conversation Canvas routes and `CanvasPanel`; Python persistence tests | MATCHED |
| Canvas isolation | legacy secured document and trusted action bridge | opaque-origin sandbox, restrictive CSP, source/schema/size checks and trusted confirmation card; `CanvasPanel.test.ts` | MATCHED + HARDENED |
| Browser chrome | `WorkspaceBrowserPanel` RTL surface and Point 6 stable target | `BrowserPanel`, ordered Rust broker, keyboard/menu/library/privacy/import surfaces; browser state and Rust tests | MATCHED + EXTENDED |
| Windows shell | legacy tray, hotkey, notifications, taskbar attention and custom titlebar | `windows_integration.rs`, Tauri plugins and existing React titlebar; Rust activation tests plus minimal single-instance/close-to-tray live smoke | MATCHED |

## Verification evidence (2026-08-23)

- Frontend: TypeScript check, 33 Vitest checks and production Vite build passed.
- Core/control plane: 21 focused `tests/test_conversation_runs.py` checks passed,
  including real route integration fixtures for reasoning selection and both
  Codex quota windows; generated `/v2` JSON and TypeScript artifacts match the
  authoritative schema.
- Native host: 18 Rust tests and `cargo check` passed, including external-link
  scheme validation and executable local-link rejection.
- Minimal live validation: one restarted Tauri development window loaded the
  nested model menu from the updated Python Core. The visible Codex card showed
  the live `plus` plan, remaining percentage and reset time without the stale
  `not_found` response. This was intentionally a single focused live check per
  the user's quota-saving instruction, not an exhaustive per-feature UI pass.
- Focused remediation validation: one maximized live window showed the native
  Google WebView ending at the Workbench boundary while chat remained visible;
  the same durable conversation exposed background-task prompts and the full
  report/tool timeline with elapsed time before its assistant answer. No broad
  click-through or per-feature computer-control pass was performed.
- Evidence boundary: no installer, packaged executable, OAuth matrix or release
  artifact was tested or claimed by Point 9A.

## Points 10-12 verification evidence (2026-08-23)

- Core: all 372 Python tests passed, including seven focused LocalGateway tests
  and a real loopback Files/Terminal exercise under a Hebrew workspace path.
- Frontend: TypeScript, 37 Vitest tests and the Vite production build passed.
- Native host: 18 Rust tests and `cargo check` passed.
- Static/runtime hygiene: generated JSON/TypeScript control-plane artifacts,
  Python `compileall`, `pip check` and `git diff --check` passed.
- Live boundary: the terminal/API integration was the only new live behavior
  check. No computer-control click-through, paid provider call, installer,
  packaged executable or release artifact was tested or claimed.

## Points 13-15 verification evidence (2026-08-23)

- Core: all 373 Python tests passed; the 35 focused Canvas/control-plane tests
  cover Qt-free Canvas enablement, persistence, layout and the new Canvas and
  browser-import routes. `compileall` and `pip check` passed.
- Frontend: all 40 Vitest tests passed; TypeScript and the Vite production build
  passed, including hostile Canvas/CSP and Browser state fixtures.
- Native host: all 21 Rust tests passed, including broker ordering/recently
  closed behavior and scoped second-launch activation parsing.
- Live Browser: one development smoke and one bundled-candidate binary smoke
  proved the same visible and automated WebView2 target, hostile-page Tauri
  denial, persistent/Guest isolation, popup governance, Hebrew input,
  hide/show/resize/focus and a 13,224-byte screenshot. The confirming bundled
  candidate opened its first tab in 2.706 seconds.
- Package boundary: a debug NSIS candidate
  `SmartiAI_0.87.0_x64-setup.exe` was built successfully. Its patched candidate
  binary passed the Browser smoke against the source Core; the installer was
  not installed on a clean machine and the production Core/private-runtime
  bundle is intentionally owned by Point 16, so this is not release evidence.
- Minimal Windows live check: `WM_CLOSE` preserved the primary process in the
  tray, a second `show` launch routed and exited, and `update-shutdown` ended the
  primary process cleanly with no remaining desktop instance. No exhaustive
  per-feature computer control, notification click, paid account, physical DPI
  or multi-monitor matrix was run, following the user's quota-saving request.
- Hygiene: generated contract equality is covered by the Python suite and
  `git diff --check` passed. No commit, release or updater operation was made.
