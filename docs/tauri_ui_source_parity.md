# Tauri Points 7-12 legacy-source UI parity specification

> **Recovery status: Point 16C parity gate REOPENED on 2026-08-24.** Direct user
> inspection of the current Tauri Settings surface showed that the React layout,
> controls and icons still do not match the authoritative PyQt implementation.
> The earlier `CURRENT MATCHED` claims and self-authored visual fixtures are not
> acceptance evidence. Every Point 16A/16B row is provisional until re-audited
> control-by-control against PyQt source and exercised through its bidirectional
> handler/Core/persistence path. Point 17 remains blocked and PyQt stays present.

> **Point 16C status override:** every `MATCHED`/`CURRENT MATCHED` cell in the
> dated matrices below is frozen historical evidence and is currently treated
> as `REOPENED — AUDIT OPEN`. The active non-self-referential ledger and exact
> manual checklist are in `tauri_point16c_source_audit.md`. No legacy status cell
> may close Point 16C until that ledger has no `AUDIT OPEN` or `BLOCKING GAP` row.

- Gate: historical Point 9A plus current recovery Point 16A
- Binding source date: 2026-08-24
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

The current daily implementation is in `desktop/src/App.tsx`, `Composer.tsx`,
`RichMessage.tsx`, `VoiceOverlayWindow.tsx`, `WorkbenchPanels.tsx`,
`BrowserPanel.tsx`, `App.css`, `legacyAssets.tsx`, `legacyUiParity.ts`,
`workspaceState.ts`, `chatState.ts`, the Rust Tauri host and the shared Python
history/run/voice/control-plane authorities, with colocated and gateway tests.

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

## Point 16A current daily control/state/action mapping (2026-08-24)

The rows below are the dated Point 16A implementation trace. Their old
`CURRENT MATCHED` cells are overridden to `REOPENED — AUDIT OPEN` by the Point
16C gate above. Each row remains useful for locating the action, bridge,
authority and reload path; it is not current acceptance.

### Shell, layout and Windows lifecycle

| Control/state | Authoritative PyQt source | Current Tauri handler/visual | Authority, persistence and reload effect | Evidence/status |
|---|---|---|---|---|
| Initial splash | `app.main`, `AnimatedSplash`; 500x310, radius 30, logo/title/subtitle/version, status and progress | `App` startup branch, `.status-card`; Tauri starts at exactly 500x310, undecorated, non-resizable and transparent | `CoreSupervisor` emits `core://state`; `desktop_finish_startup` changes the same window to a resizable Workspace only after health/bootstrap | Hidden supervisor smoke measured 500x310; inspected `startup-dark-500x310.png`; CURRENT MATCHED |
| Crash/fatal/repair | `finish_startup` error and startup status vocabulary | `copyForState`, startup recovery card, restart action and bounded redacted stderr tail | `core_restart` creates one new supervisor generation; live state is re-emitted and bootstrap is replayed | supervisor crash/restart smoke and Rust tests; CURRENT MATCHED + TAURI RECOVERY |
| Workspace window creation | `ChatWindow` minimum 720x560; screen minus 72, clamped to 920-1380 by 620-900; centered | `desktop_finish_startup`, custom 36 px title bar and `workspaceWindowReady` gate | guarded `window-placement.json`; `SMARTI_DATA_DIR` isolates placement in tests; restore validates dimensions/monitor visibility | hidden smoke measured 1380x792 on the current logical screen; Rust geometry test; CURRENT MATCHED |
| Title controls | `WorkspaceWindowTitleBar`; minimize, maximize/restore, close and double-click maximize | `WindowTitleBar`; `appWindow.minimize/toggleMaximize/close`, dynamic restore glyph/label | native Tauri window; close request flows through close-to-tray policy | frontend typecheck and Rust host compile/smoke; CURRENT MATCHED |
| Three-column ownership | `workspace_splitter`: Workbench left, chat center, drawer right, LTR splitter order | RTL grid with `workspaceColumns`; DOM order remains drawer/chat/Workbench | pure reducer restores open/closed state after Core bootstrap | `workspaceState.test.ts`; wide screenshots; CURRENT MATCHED |
| Source splitter sizing | `_workspace_open_sizes`: narrow below usable 920; otherwise `min(max(480, usable*0.52), usable-520)` | `workspaceOpenSizes`, grid columns and `.is-workbench-narrow` | recalculated on viewport/sidebar change; chat is hidden only in the source narrow branch | exact boundary/value tests and 1380/820 screenshots; CURRENT MATCHED |
| Manual Workbench resize | `QSplitter` one-pixel handle and `splitterMoved` refresh | `.workbench-resize-handle`, pointer capture and `clampWorkbenchResize`; double-click restores calculated width | transient like the source; persisted tab/open state is not conflated with a made-up splitter preference | computed state tests plus inspected wide layout; CURRENT MATCHED |
| Drawer expand/collapse | `WorkspaceSidebar.set_collapsed`, 286/58, responsive auto-collapse and manual preference | `toggleConversationDrawer`, rail/expanded branches and source assets | PATCH `/v2/settings` -> `ui_preferences.workspace_sidebar_collapsed`; bootstrap restores unless narrow | gateway settings coverage and narrow screenshot; CURRENT MATCHED |
| Theme | `apply_app_theme` and palette helpers; system/light/dark | `useTheme`, Core bootstrap `ui_preferences.theme_mode`, exact theme tokens/assets | Settings authority persists theme; local storage only prevents pre-bootstrap flash | theme unit tests and inspected light/dark screenshots; CURRENT MATCHED |
| Close/tray/activation | tray menu, close-to-tray, single instance and bring-to-front | `desktop_set_close_to_tray`, `desktop://activation`, `desktop_quit` | Rust `DesktopState`, single-instance plugin and native tray; no conversation is acknowledged by merely showing the app | 22 Rust tests and hidden supervisor smoke; CURRENT MATCHED + TAURI NATIVE |
| Unread/notification attention | `TaskbarAttentionController`, `WindowsNotificationCenter` | conversation projection invokes `desktop_set_unread` and scoped `desktop_notify` only while hidden | history unread count remains Core-owned; activation selects the supplied session before read receipt | Rust host compile plus history/gateway tests; CURRENT MATCHED + TAURI NATIVE |

### Conversation history

| Control/state | Authoritative PyQt source | React handler and operation | Python authority, persisted effect and reload | Evidence/status |
|---|---|---|---|---|
| Create conversation | `ChatWindow.start_new_chat`, `ChatHistoryPage` | `createConversation` -> POST `/v2/conversations` | `ChatSessionStore` creates the durable session; refreshed list selects its ID | full gateway/conversation tests; CURRENT MATCHED |
| Select/read | row click and `load_session` | `selectConversation`, GET paged messages, POST `/read` only for the active conversation | history loads the same session and acknowledges only its attention/unread state | gateway workflow and reload projection tests; CURRENT MATCHED |
| Older-message paging | initial 32/older 24 legacy batches | `loadOlder` uses `next_before_ordinal` and `mergeMessages` without duplication | `ChatSessionStore.get_messages_page`; ordinal cursor survives frontend reload | state and gateway pagination tests; CURRENT MATCHED |
| Delayed search | 40 ms `QTimer`, title/content query, clear action | query effect uses `legacyUi.historySearchDebounceMs`; GET `/v2/conversations?q=...` | Core/SQLite search is authoritative; empty query restores the complete ordered list | value test plus populated/no-result fixture; CURRENT MATCHED |
| Pin/unpin | source menu action and pinned-first order | `togglePinned` -> PATCH conversation `{pinned}` | Core session metadata persists and refreshed ordering comes from history | gateway CRUD coverage; CURRENT MATCHED |
| Rename | internal source dialog, non-empty title | `renameConversation` internal dialog -> PATCH `{title}` | Core persists sanitized title; active header and row refresh together | component/gateway coverage; CURRENT MATCHED |
| JSON export | `core.export_session` source action | `exportConversation` -> GET `/v2/conversations/{id}/export` -> `save_text_file` | `session_export_payload` generates the authoritative schema; native Windows COM save dialog chooses destination | gateway asserts payload; Rust native-save compile; CURRENT MATCHED |
| Delete | confirmation dialog then Core mutation | `deleteConversation` dialog -> DELETE conversation | Core deletes durable session data and selection falls to the next refreshed row | gateway CRUD and dialog branches; CURRENT MATCHED |
| Activity priority | history projection prioritizes API input, approval, cancelling, running, queued, unread | `activityState`, `ACTIVE_RUN_STATES`, exact spinner/attention/unread classes/tooltips | SQLite run query includes `waiting_for_input`; `needs_input` and unread are reprojected after reload | Python/API-interruption and frontend state tests; CURRENT MATCHED |
| Empty/no result/load/error | source empty history and reconnect states | separate `historyLoading`, `historyError`, empty history and query-no-result copy | failed refresh does not erase durable Core state; retry/reconnect refreshes the projection | deterministic React branches and screenshot fixture; CURRENT MATCHED |

### Chat timeline, run interruptions and message actions

| Control/state | Authoritative PyQt source | React handler/visual | Authority, persisted event and reload effect | Evidence/status |
|---|---|---|---|---|
| Welcome/active title | `WelcomeWidget`, active session title | `legacy-welcome`, `displayName`, elided RTL toolbar title | bootstrap supplies display name and session; selection/reload recalculates title | component/state tests; CURRENT MATCHED |
| User/assistant/system/error | `MessageBubble`, `ChatMessageContainer`; transparent assistant/system rules | `RichMessage` role/error branches; RTL user row now uses physical right via `flex-start` in RTL | stored messages/metadata choose role and error class after reload | `chatUi.test.tsx`; visual defect found and repaired by screenshot; CURRENT MATCHED |
| Markdown/mixed direction/links | source rich text and safe `file:///`/web links | `prepareMessageMarkdown`, `safeChatHref`, `open_chat_link`; code/path islands use LTR | Rust accepts only expected schemes/existing safe local paths and rejects executable extensions | React and Rust link tests; CURRENT MATCHED |
| Code copy/save | `CodeBlockWidget` copy/download buttons | copy uses clipboard; save invokes `save_text_file` with language extension | native Windows COM dialog writes only after explicit destination selection | component tests and Rust compile; CURRENT MATCHED |
| Sent/pending attachments | source attachment tiles/preview strip and attachment-first message order | `RichMessage`, `Composer`; picker/paste/drop/remove, staged previews and bounded errors | Rust staging hides filesystem paths behind Core attachment handles; run metadata/messages persist the final attachments | gateway attachment workflow and component tests; CURRENT MATCHED |
| Long user message | six source lines/rendered-height collapse | `ResizeObserver`, six-line mask and explicit expand/collapse action | expansion is view state; full durable message content is never truncated | value/component tests; CURRENT MATCHED |
| Background task | orange source prompt badge and durable reports | metadata projection, `⚡ משימת רקע`, agent process above answer | run events and `metadata.agent_process` survive reload/reconnect | Python run tests and message fixture; CURRENT MATCHED |
| Agent progress/tools/time | reports, ordinary/standalone tool groups, input/output and elapsed time | `processRows`, active shimmer, nested details and `formatAgentDuration` | cursor-replayed run events merge by event ID; stored final process replaces live-only state | run-event/component tests; CURRENT MATCHED |
| Copy/TTS | sibling actions outside bubble; assistant TTS start/stop | message copy; POST `/v2/audio/tts`, GET status, POST stop | shared Python TTS worker/service owns playback state | gateway TTS integration and component assertions; CURRENT MATCHED |
| Approval interruption | source approval dialog and run wait | approval card/dialog -> POST `/v2/approvals/{id}/resolve` | approval and run are persisted; refresh/reload restores pending approval before resolution | gateway approval workflow; CURRENT MATCHED |
| API-key interruption | `_handle_run_api_key_request`; wait without writing the secret into chat/history | `pendingApiKeyRequest`, password dialog, help/cancel, POST `/v2/runs/{id}/api-key` | `ConversationRunManager.request_api_key` transitions to durable `waiting_for_input`, emits secret-free required/submitted events, then resumes `running`; value remains in the provider secret authority, not events | focused manager/gateway tests assert wait, resume and no secret leakage; CURRENT MATCHED |
| Run/send/cancel/reconnect | queued/running/cancelling/completed/failed/cancelled states | `send`, `cancel`, `ACTIVE_RUN_STATES`, event poll/cursor merge and synthetic active assistant | Core run record and monotonic events are authoritative; WebView reload rebuilds state without replacing Core PID | Python run suite, chat state tests and hidden supervisor reload smoke; CURRENT MATCHED |
| Memory/Canvas message affordances | source memory-updated indicator and Canvas open cards | `memory-updated`, `canvas-open-card`, callback opens Canvas Workbench | message metadata/canvas model persists IDs and titles; reload rematerializes cards | `chatUi.test.tsx` and Canvas tests; CURRENT MATCHED |

### Composer and voice

| Control/state | Authoritative PyQt source | React handler/visual | Authority, persisted effect and reload | Evidence/status |
|---|---|---|---|---|
| Frame/input/actions | `PillInputFrame`, `PinnedActionButtonHost`; 112 min, 40.5 radius, 52/42 controls and bottom pin | exact CSS/value ledger; auto-height textarea; Enter send, Shift+Enter newline; mic/send/stop state | send creates a Core run; stop cancels that run; disabled/listening states block duplicate submission | layout/component tests and inspected screenshots; CURRENT MATCHED |
| Favorite-model visibility | source pill exists only when favorites are non-empty | `!!favoriteModels.length`, centered model text/arrow and nested popup | bootstrap reads `favorite_models`; no generic substitute is shown when empty | component tests; CURRENT MATCHED |
| Provider/model selection | provider submenu and favorite model action | `selectFavoriteModel` PATCHes `api_mode`, `selected_<provider>_model` and full `selected_model_source`, then refreshes bootstrap; failure rolls back | Core settings/setup_model becomes runtime authority; provenance and active selection survive reload | gateway settings behavior and React branches; CURRENT MATCHED |
| Reasoning/Codex quota | current-model effort choices and Codex two-window quota | `changeReasoning`, provider quota card/cache/refresh/reset copy | PATCH reasoning setting; authenticated provider quota endpoint remains Core-owned | quota UI/Core tests; CURRENT MATCHED |
| Autonomy | safe/balanced/autonomous profiles and custom display | autonomy pill/menu -> persisted settings patch | Core applies autonomy policy to later runs and bootstrap restores label | parity/component plus gateway settings tests; CURRENT MATCHED |
| Local FastMode | local-provider-only source toggle | local-only control -> PATCH `local_fast_mode_enabled`, rollback on error | Core settings persist; provider change recomputes visibility | component/settings coverage; CURRENT MATCHED |
| Picker/paste/drop | plus action, file picker, clipboard image and drag/drop | `picked`, `paste`, `drop`; size/type errors remain in the composer | `stage_attachment` writes bounded cache files; final attachment registration is Core-scoped | component/gateway attachment tests; CURRENT MATCHED |
| Voice recognition authority | `VoiceWorker` sensitivity, ambient calibration, beeps, `he-IL`, cancellation and auto-send transcript | Composer POSTs `/v2/audio/voice`, polls status and auto-sends the returned transcript; no Web Speech adapter remains | shared Qt-free `smarti.voice_service.recognize_voice`; legacy `VoiceWorker` delegates to the same service | controller/gateway tests and 123-test offscreen run; CURRENT MATCHED |
| Voice Tool window | `VoiceListeningOverlay`; independent frameless always-on-top Tool, 298 foreground/342 background by 70, original controls/asset | Rust creates trusted `voice-overlay` WebView, skip-taskbar, undecorated, non-resizable, always-on-top; `VoiceOverlayWindow` polls Core, cancels or focuses main | overlay closes when the shared voice session ends; no speech state is owned by the WebView | hidden smoke measured 342x70/native flags; Rust width test covers 298; inspected `voice-dark-298x70.png`; CURRENT MATCHED + TAURI NATIVE |

### Workbench, Browser, Files, Terminal and Canvas

| Control/state | Authoritative PyQt source | React/native handler | Authority, persistence and reload | Evidence/status |
|---|---|---|---|---|
| Frame/empty state | `WorkspaceWorkbench`; 8 px outer margin/padding, 18 radius, 46 header, original empty actions | `WorkbenchSurface`, `.workbench-*`, source labels/actions | Workbench component remains mounted after bootstrap even when its column is closed | screenshots/component build; CURRENT MATCHED |
| Tab focus/repeat/singleton | repeated Files/Browser/Terminal; one Canvas/Artifacts; movable tabs and next-tab selection on close | `openWorkbenchTab`, `reorderWorkbenchTabs`, `closeWorkbenchTab`, draggable tab buttons and plus menu | snapshot stores ordered `{id,kind,title}` plus active ID; bootstrap validates and restores up to 20 tabs | `workspaceState.test.ts`; CURRENT MATCHED |
| Open/close persistence | source Workbench on-demand lifecycle and visible active tab | `setWorkbenchOpen`, `persistWorkbench`; inactive panels are hidden, not unmounted | `ui_preferences.workspace_workbench_open/workspace_workbench`; Core reload restores active kind/tab order | state/settings tests; CURRENT MATCHED |
| Files | selected root, tree right/preview left, safe preview/open | `FilesPanel` -> Workbench tree/file/open routes | `WorkspaceScope` enforces realpath/traversal/symlink/size/depth boundaries and persists root | real Hebrew-workspace integration within 123 tests; CURRENT MATCHED |
| Artifacts | generated-file inventory/open | `ArtifactsPanel` route and actions | Core artifact discovery and safe external-open authority | Workspace integration tests; CURRENT MATCHED |
| Terminal | independent hidden UTF-8 PowerShell sessions with input/restart/close | each terminal tab owns a mounted `TerminalPanel`; inactive tabs retain session reference | `TerminalRegistry` owns process lifecycle/output/cwd and cleans up on gateway shutdown | real PowerShell/Hebrew cwd test; CURRENT MATCHED |
| Canvas | singleton active/closed Canvas tab, layout/actions | `CanvasPanel`, message Canvas card opens/focuses Workbench | conversation-scoped Canvas model/routes persist/reopen materialized artifacts; action re-enters chat only after trusted confirmation | Canvas/frontend/Python tests; CURRENT MATCHED + SANDBOX HARDENED |
| Smarti Browser lifecycle | legacy integrated browser within Workbench; approved Tauri-owned same-visible-target architecture | every Browser tab remains mounted; only active+visible WebView is shown; repeated tabs and same target broker retained | Rust `BrowserBroker` owns tab/target/profile state; no external Chrome/Edge HWND or remote-debug port | browser state/Rust tests and historical same-target smoke; CURRENT MATCHED + APPROVED TAURI ARCHITECTURE |
| Background browser preview | source 236x142 preview while browser has activity and Workbench closes | hidden browser screenshot activity updates `browser-preview-card`; expand reopens Browser | CDP screenshot comes from the same broker target at bounded cadence; activity survives panel hiding | compiled frontend/Rust browser tests and current source audit; CURRENT MATCHED |
| Browser source/screenshot saves | source page-source and screenshot save actions | `BrowserPanel` invokes `save_text_file`/`save_binary_file` | same visible target supplies data; native Windows dialog chooses the destination | Rust compile/browser policy tests; CURRENT MATCHED |

### Point 16A evidence boundary

- Frontend: TypeScript, 44 Vitest checks and production Vite build passed.
- Core/legacy preservation: 123 focused Python tests passed across conversation
  runs, SQLite history, Workspace, Canvas, Codex quota and memory with
  `QT_QPA_PLATFORM=offscreen`; the PyQt launcher/classes were imported and
  exercised rather than removed.
- Native host: `cargo fmt --check` and 22 offline Rust tests passed. The hidden
  Tauri supervisor smoke proved initial 500x310 shell, current-screen 1380x792
  Workspace, non-visible 342x70 always-on-top voice window, Core duplicate
  prevention, WebView reload PID preservation, crash/restart and graceful stop.
- Visual: the inspected local evidence set contains
  `startup-dark-500x310.png`, `voice-dark-298x70.png`,
  `wide-dark-workbench.png`, `wide-light-chat.png` and
  `narrow-dark-workbench.png` under `.codex-local/point16a-evidence`.
- No automated mouse, keyboard or focused-window control was used. No installed
  package, signed release, microphone-hardware capture, paid provider call or
  cross-machine compatibility claim is made. Point 16B is recorded separately
  below; whole-product/package acceptance remains Point 16C.

## Point 16B current Settings and management control/state/action mapping (2026-08-24)

The rows below were previously labelled `CURRENT MATCHED`, but the Point 16C
user review invalidated that acceptance claim. They are reopened pending a
source-derived control/state/icon/interaction audit; the older Points 10-12
table remains historical only.

| Control/state | Authoritative PyQt source behavior | Current Tauri handler/visual | Authority, persistence and reload effect | Evidence/status |
|---|---|---|---|---|
| Management shell/navigation | `ManagementCenterPage` registration, 250 px right menu, `ניהול` then `הגדרות`, exact ordered entries, lazy page ownership and profile-menu About | Production `ManagementCenter` now follows the source hierarchy and renders tracked assets only where PyQt registers an icon | React navigation/reload wiring exists, but every state still requires source comparison | REOPENED — AUDIT OPEN |
| Five Settings pages/search | separate AI, Security, Tools, Appearance and Advanced pages; Hebrew label/help/control/advanced metadata, cross-page search, recent searches, saved/error states | Production `SettingsManagement` renders source-shaped controls and actual search-result navigation; the self-authored fixture is no longer used as a design oracle | authenticated `GET/PATCH /v2/settings`; advanced-navigation interaction passes | REOPENED — detailed ledger still has open rows |
| Provider/model/reasoning | provider selector, model discovery/favorites, loading/error state, reasoning effort and connection validation | source-shaped provider flow, searchable model popup, loading state and themed favorite stars | Python provider discovery and persistence remain authoritative; provider-by-provider coverage remains incomplete | REOPENED — AUDIT OPEN |
| Secrets and Codex | `_make_secret_link_row`, dynamic `קבל מפתח`, provider instructions, themed paste/delete controls, validation-before-save and Codex flows | schema-driven dynamic help/instructions, tracked paste/delete assets, Codex controls and production runtime missing-key dialog | rendered tests prove Settings help/paste/validate/write/delete and Core-requested invalid/valid/resume payload; durable Core test proves wait/resume/no secret leakage | REOPENED — visual/account-state audit remains open |
| Permissions/sandbox/paths | autonomy presets, segmented capability matrix, approval rules, sandbox/default-output/allowed-directory native pickers and warnings | `PolicyMatrix`, source-labeled security controls, `pick_management_path` | Core owns `policy_matrix`, sandbox validation and live prompt/tool-policy rebuild; native picker returns only the user-selected path | REOPENED — AUDIT OPEN |
| SSL/network safety | system/custom-CA/legacy-insecure modes, explicit danger acknowledgement, CA picker and connection test | `SslWorkflow`, internal confirmation and settings action | Core validates trust mode/path, persists it, rebuilds SSL behavior and executes the bounded test; reload restores selected mode | REOPENED — rendered workflow and visual audit open |
| Tools/email/MCP/Skills | browser/computer permissions, email fields/test, catalog toggles, install/trust/enable/remove and extension warnings | `SettingsManagement`, `ToolsView`, internal install/remove dialogs | Python registry, extension catalog and email test remain authoritative; refresh/reload returns current trust and enablement | REOPENED — AUDIT OPEN |
| Voice/theme/Windows/update | TTS voice/volume/preview, recognition thresholds, global hotkey, theme, tray, update preference/releases/install/deferral | appearance page, `UpdateControls`, native preview/hotkey/tray invokes and Tauri updater | Python voice/settings and Rust Windows/updater commands apply live effects; theme and preferences persist and restore | REOPENED — AUDIT OPEN |
| Workspace/browser preferences | source Workspace start/sidebar state, root display and Smarti-owned browser actions | `WorkspaceView` and Workbench activation actions | `ui_preferences`, scoped Core workspace root and Rust `BrowserBroker` remain authoritative; mount refreshes each snapshot | REOPENED — AUDIT OPEN |
| Memory | masked list, create/details/reveal/edit/pin/filter/page/select/bulk/archive/restore/import/export/clear confirmations | `MemoryManagement` with page size 8, explicit sensitive reveal and internal dialogs | Python memory manager performs CRUD/encryption/export/import and returns filtered/paged masked snapshots | REOPENED — full source/state/action audit open |
| Tasks | empty/list/result states, recurrence, routing, cancel/retry/resume/edit/delete | `TasksView` and Core task actions | Python background task service owns schedule/checkpoint/result; every action reloads the authoritative task list | REOPENED — full source/state/action audit open |
| Usage/logs/About/legal/update | today/week/month/all tokens/cost/cache/memory, clear-with-backup; privacy-first trace/export; full capabilities/version; release notes; first-run 18-clause acceptance gate | `UsageView`, `LogsView`, `AboutView`, `UpdateControls`, `LegalAgreement` | Core owns usage/log/privacy/legal acceptance and backups; Rust owns native export/updater; legal acceptance gates chat bootstrap and persists current version | REOPENED — full source/state/action audit open |
| Smarti Diagnostic | exact check progress, filters/summary/detail, cancel, approved repair/result plus new architecture checks | `DiagnosticsView` polls `GET /v2/management/diagnostics`; POST scan/cancel/repair; Rust `desktop_diagnostic_snapshot` adds supervisor, contract/auth, sidecar/writable paths, WebView2/browser, CSP/capabilities, Windows integration, signature and stale-child checks | one shared Python `SmartiDiagnostic` owns checks/cancellation/repairs/logging; Rust owns Tauri health snapshot; repairs remain confirmation-gated | REOPENED — full source/state/action audit open |

Point 16B evidence boundaries: 47 frontend tests, 58 focused
Core/gateway/doctor tests, 29 memory-management tests, production build,
generated-contract equality, Python compilation, Rust `cargo check`, and two
inspected local RTL fixtures passed. This is not installed-package,
signed-release, paid-provider, clean-machine or cross-machine evidence. Point
16C remains the package and whole-product acceptance gate.

## Points 10-12 historical traceability extension

| Surface/state | Legacy/Core source specification | Tauri implementation and deterministic check | Status |
|---|---|---|---|
| Settings shell | Settings categories, Hebrew labels, search, advanced fields and restart implications | Historical implementation trace only; `managementUi.test.ts` string assertions are not visual or interaction acceptance | HISTORICAL / REOPENED |
| Providers and secrets | provider choice/model discovery/connection validation; secrets remain in Core persistence | Core routes exist, but the exact Settings help/paste/delete/validation composition and request dialog flow are under re-audit | HISTORICAL / REOPENED |
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

There are no open user-visible deviations in the Point 16A daily surfaces. DOM
objects and Tauri native windows replace Qt widgets internally; voice
recognition itself is again the shared Python authority, and the independent
voice overlay retains the source Tool-window behavior. Canvas keeps the stable
Workbench tab and replaces Qt/WebEngine with a CSP-constrained
`sandbox="allow-scripts"` iframe. The approved Browser remains a Tauri-owned
WebView2 target instead of an external browser HWND. These architectural
substitutions preserve the mapped hierarchy, copy, assets, sizes, actions and
durable state above. Settings/management claims are covered by the current
Point 16B ledger above. Browser and Windows support boundaries remain in
`tauri_browser_support_matrix.md` and `tauri_windows_integration.md`; package
acceptance remains Point 16C.

## Points 13-15 traceability extension

| Surface/state | Legacy/Core source specification | Tauri implementation and deterministic check | Status |
|---|---|---|---|
| Canvas history/model | `canvas_model.py`, active/closed history, layout and context injection | authenticated per-conversation Canvas routes and `CanvasPanel`; Python persistence tests | MATCHED |
| Canvas isolation | legacy secured document and trusted action bridge | opaque-origin sandbox, restrictive CSP, source/schema/size checks and trusted confirmation card; `CanvasPanel.test.ts` | MATCHED + HARDENED |
| Browser chrome | `WorkspaceBrowserPanel` RTL surface and Point 6 stable target | `BrowserPanel`, ordered Rust broker, keyboard/menu/library/privacy/import surfaces; browser state and Rust tests | MATCHED + EXTENDED |
| Windows shell | legacy tray, hotkey, notifications, taskbar attention and custom titlebar | `windows_integration.rs`, Tauri plugins and existing React titlebar; Rust activation tests plus minimal single-instance/close-to-tray live smoke | MATCHED |

## Points 10-15 source-parity remediation (2026-08-23)

The first implementation of Points 10-15 reused generic dashboard cards and
placeholder glyphs. That shell was not an exact rendering of the legacy PyQt
composition and has been replaced. The remediation is derived from the source
classes listed above, not from screenshots:

- `ManagementCenter` now follows the PyQt management window: a 64 px header,
  42 px themed back control, 250 px navigation rail, 42 px navigation rows,
  original Hebrew grouping/order and the tracked legacy assets. About uses the
  original 184 px Smarti mark rather than a generated letter mark.
- settings, task, memory, tools, diagnostics, usage, trace and About pages reuse
  the PyQt section widths, 12 px card radius, form hierarchy, compact action
  geometry, RTL alignment and established light/dark palette. The updater is a
  new Point 16 state inside About and deliberately inherits those controls.
- `WorkspaceWorkbench` follows the PyQt 8 px outer margin, 18 px container
  radius, 46 px header, 38 px tabs, 12 px tab radius and 38% RTL file-tree/
  preview split. Terminal, Artifacts and Canvas reuse the same source surfaces;
  the full Browser retains its approved Point 14 architecture inside that exact
  Workbench frame.
- the React implementation is in `ManagementCenter.tsx`,
  `WorkbenchPanels.tsx`, `legacyAssets.tsx` and the final source-parity override
  block in `App.css`. No PyQt source or fallback launcher was removed.

The deterministic frontend suite guards labels, hierarchy and behavior. The
source map above is the visual evidence for this remediation; no broad live
computer-control walkthrough is claimed or required by the user.

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
