# Smarti Browser product support matrix (Point 14)

This matrix describes the Smarti-owned WebView2 browser surface. It is not a
claim that WebView2 is Edge or Chrome. The visible user tab and the target used
by `browser_automation_manager` remain the same Rust-owned child WebView; no
installed browser window, external profile in place, or remote-debugging port
is used.

| Area | Smarti support | Boundary |
|---|---|---|
| Tabs and navigation | New, close, duplicate, drag-reorder, pin, recently-closed restore, persistent-session restore, titles, loading/crash/audio states, back/forward/reload/stop/home and LTR omnibox | Ordinary inactive WebViews can freeze. Agent-owned targets remain live offscreen between calls and when the workspace closes. Restore is capped at 12 tabs. |
| Keyboard and focus | `Ctrl+L/T/W/Shift+T/F/D/R`, Alt+Left/Right, governed popup tabs and predictable active-target focus | Site-reserved shortcuts can still vary with WebView2 and IME configuration. |
| Page commands | Find, 25-500% zoom, full screenshot, print-to-PDF, copy address and open externally | Native print preview, device emulation and DevTools remain developer-oriented WebView2/CDP facilities rather than Edge UI. |
| Responsive viewport | Live window/splitter resizing; automatic mobile viewport at content widths up to 600 CSS px; per-tab Auto/Mobile/Desktop override; compact toolbar and full-width panels on phones | Mobile metrics follow actual available width/height and native DPI. This does not rewrite a site's fixed desktop layout or automatically change its user agent/reload a form; the separate mobile User Agent command is available for server-selected mobile sites. |
| Library | Smarti-owned searchable-ready history data, bookmarks, recently closed tabs and persistent session | Guest navigation/downloads never enter the persistent library. The current UI lists and opens records; richer folder/tag organization is not vendor-synced. |
| Downloads | Smarti-selected Windows Downloads destination, collision-safe names, dangerous executable/script extension blocking and requested/finished/failed history | Tauri's stable WebView download hook does not expose pause/resume/progress or a portable cancel handle; Smarti does not claim those controls. Browser/OS safe-browsing remains the second protection layer. |
| Profiles and privacy | Smarti persistent WebView2 data plus per-tab incognito Guest directories; clear-profile action and complete Guest cleanup | No vendor account sync. Smarti never reads or displays password values. |
| Site permissions | Per-origin camera, microphone, location, notifications and clipboard decisions through the visible tab's WebView2 CDP target | Certificate/client-certificate and OS privacy prompts remain WebView2/Windows owned. |
| Profile import | User chooses a detected Chrome, Edge, Brave, Chromium or Vivaldi profile and independently selects history, bookmarks and compatible cookies | Source databases are copied before reading and never changed. App-bound/v20 or otherwise undecryptable cookies are skipped; normal sign-in is required. Password import is absent by design. |
| Automation | Existing Python policy/lease/audit path and Rust broker operate on stable `tab-*` / `wv2-target-*` IDs | Uploads and sensitive actions remain Core-authorized; React receives no broker token. |
| Media/PDF/popups/errors | WebView2 media/PDF/fullscreen behaviors, popup-to-tab governance, loading/crash state and network-page errors | DRM, codecs, WebAuthn, embedded OAuth and enterprise certificate behavior depend on the installed WebView2 Runtime and site/provider policy. |
| Vendor features | Not supported | Chrome/Edge extensions, vendor profile sync, internal settings pages, Collections, vendor translation, immersive reader and extension stores are not presented as working. |

The profile library is stored by trusted Smarti chrome, while WebView2 owns
site storage. Guest library writes are rejected in the React state transition,
and the Core import response is accepted only over the authenticated Tauri
proxy. Compatible cookie values are passed directly to `Network.setCookies`
for the persistent visible tab and are never rendered in the import report.

Responsive implementation (2026-09-13): `WorkbenchSurface` mounts one browser
controller for the shared Rust broker. `useNativeBrowserSurface` coalesces
native bounds in animation frames and keeps CDP metrics in a separate serial
queue that discards intermediate sizes. Only opening/closing uses the cached
preview handoff; ordinary resizing does not hide the live page. Width is no
longer a Workbench transition. Hidden native tabs receive the latest bounds
when activated. The Workspace can be resized down to 360 by 320 logical pixels;
at phone window widths the Workbench fills the window's workspace area.

Focused automated coverage includes rapid and height-only resizing, pending
native/CDP requests, tab changes, mobile/desktop overrides, narrow side panels,
short/collapsed viewports, and the single controller across Workbench entries.
These checks establish scheduling/state behavior, not perceived native-window
smoothness; no live visual acceptance or installer validation is claimed.

## Agent protocol 2 (2026-10-12)

Core now uses the authenticated native broker for doctor/profiles/readiness as
well as actions. An installed Chrome, Playwright process or debugging listener
is unnecessary on this path. `doctor` returns the actual capabilities and
transport. The engine and user view share each Rust-owned WebView2 target.

| Area | Implemented behavior | Boundary |
|---|---|---|
| Read and locate | Paged DOM text, role/name/CSS/text locators, document-scoped node references, optional native accessibility tree, frames and open shadow roots | Refs expire on navigation/removal; ambiguous matches fail. Closed shadow roots require other inspection or visual input. |
| Act and verify | Trusted CDP mouse/keyboard input, fill versus append, hover, select, check, drag, nested scroll and explicit condition waits; observed page state after mutations | Observation proves the resulting page state, not business success. Native select sets selection and dispatches change; it does not emulate an OS select menu. |
| Visual and files | Real image attachment to the model, full/element screenshot, PDF, approved file upload and completed download artifacts in Core's controlled directory | Screenshot labels are reference metadata, not drawn numeric overlays. Native downloads also retain their normal Downloads file. |
| Diagnostics | Native console/errors/network/dialog subscriptions and bounded diagnostic event export | Trace is bounded CDP events, not a Chrome performance trace. Network bodies/headers are not automatically captured. |
| Workspace and background | Explicit visible/preview/hidden presentation; open/activate/expand/split/collapse/close; live offscreen targets and session ownership | Quiet work in another conversation preserves the user's current UI. An acknowledged presentation request confirms UI handling, not a screenshot proof. App exit ends these in-process browser sessions. |
| User control and recovery | Pause/resume/stop, generation fences, target serialization, cancellation routing, bounded request receipts and rejection of conflicting/in-flight repeats | Cancellation cannot undo already dispatched input. Lost results require observation before another mutation; receipts last only for the current process. |
| Privacy and policy | Persistent/guest separation, password-value redaction, redacted cookie/storage values by default, Core approval paths and native navigation policy | This is not comprehensive network interception or DNS-rebinding protection. Login, 2FA and CAPTCHA remain user steps; no account-blocking guarantee is made. |

The permanent model guidance stays short; detailed parameters are supplied by
`get_tool_info` for the selected action. Legacy transport code remains for
compatibility but is not used when Tauri's broker is available. Personal Chrome
extension control is outside this change.

The transport choice follows WebView2's [native CDP API](https://learn.microsoft.com/en-us/microsoft-edge/webview2/how-to/chromium-devtools-protocol).
Behavioral references include [Playwright actionability](https://playwright.dev/docs/actionability),
[Playwright MCP snapshots](https://github.com/microsoft/playwright-mcp),
[Claude Desktop browsing](https://code.claude.com/docs/en/desktop#browse-external-sites),
[OpenClaw browser tools](https://docs.openclaw.ai/tools/browser/agent-tools), and
[Codex browser documentation](https://learn.chatgpt.com/docs/browser). These
public contracts informed the implementation; they are not claims about private
agent internals or full feature parity.

## Agent efficiency and context (D89 plus context/cache correction, 2026-10-13)

Browser arguments now preserve every documented field before validation. Legacy
snake-case aliases become the single public camel-case spelling; pagination,
presentation, select values, frame/epoch targeting and receipt IDs are retained.
Unknown fields are rejected rather than silently dropped. `start` with a URL
waits for the new document, like navigation, and returns one `page` observation.

Native observations now preserve the complete page text by default, element
geometry/tags, heading levels, parent references, form values/options and the
full native accessibility tree with node identities, hierarchy and states.
The same applies to navigation observations. There is no automatic 2,000-character
excerpt or generic 100,000-character tool-output slice. Explicit `bodyChars`,
`textOffset` and paged `text` remain available when deliberately requested;
actionable refs still use explicit paging with `hasMore` and a total count.
`snapshotFormat=dom` or `refs=dom` deliberately skips the native AX tree.

Compact JSON removes a redundant ref field, an exactly reproducible textual
rendering of refs and an exactly equal duplicate page/result. Distinct action
results, enriched snapshots and accessibility nodes are retained. Only text in
explicit ad-provider containers is filtered, and only if it occurs once; forms,
editable content and dialogs are protected. This does not change the site or
remove interactive elements. `detail=full` and `action=text` return unfiltered
text. When Core's conversation store is present, the original observation is
encrypted and its `fullOutput` handle can be read with `read_tool_output` only
in that conversation. Failure to archive preserves the original response rather
than turning an already executed action into an apparent failure. Observations
remain untrusted content and password/credential redaction remains effective.

The agent's repeat/similarity guard is removed, including checkpoint counters.
Native request receipts still return the original result for the same action ID:
this avoids accidental transport re-execution and does not block new calls.
Configured task/iteration limits and user cancellation remain effective.
Ordinary browsing approval explicitly covers the current task and is reused only
within that run; deny policies and sensitive actions are evaluated each time.

Tool discovery remains on demand. The compact shared instruction recommends
`get_tool_info action=full` once when multiple actions of a manager will be used;
it does not preload managers or skills. Error feedback uses the applicable native
action schema instead of exposing an unrelated legacy/full contract.

Codex agent requests now share one ephemeral model-only App Server process and
thread per run. Later `turn/start` requests send only new Core feedback/images;
the server already retains its own assistant responses. Core tool execution,
approvals, official account authentication and model/reasoning selections remain
authoritative. Changed instructions/model, edited history or Core compaction
start a fresh thread with the authoritative context. Completion, cancellation
and errors close the owned process. Distinct runs have separate threads.
Cumulative token-usage deltas count all inference requests in a turn without
recounting older turns; session-reuse counts are logged without prompt content.

All providers trigger semantic compaction at 85% of the resolved model context
window. The old 128,000-token working-set cap and persisted earlier trigger
ratios no longer lower this threshold. Model-specific capacity overrides and the
known model capacity table determine the window; unknown models retain a
conservative provider fallback. Token pressure is estimated and calibrated
against reported input tokens, so this is not a claim of exact tokenization.
Exact current user messages, attachments, loaded schemas and task state retain
their preservation rules. Compaction uses a small internal request without tools
or the agent stream/session. No new UI control or system-prompt section was added.

Codex receives per-process context-window and 85% automatic-compaction settings;
personal account configuration is untouched. Context calibration uses the most
recent inference input, while billing/telemetry still counts all inference
requests in the turn through cumulative deltas. Its model-only processes do not
load the account's unrelated personal memories.

OpenAI API requests now cache the growing conversation, including browser/tool
results, on both Chat Completions and Responses. Current models use native
implicit caching plus stable system/recent-tool cache boundaries and a stable
run key; older models retain their native cache contract. Standalone summaries
and titles avoid paid cache writes where supported. Unsupported controls are
removed before retry without changing text or images. Anthropic's existing
off/auto/always preference controls its native automatic history caching;
Gemini retains native implicit caching. Content-free `API CACHE` records measure
input, cached reads, cache writes, uncached input, output and weighted cumulative
hit rates separately by run/provider/model/purpose.

An isolated real WebView2 test verified full text including an article's final
marker, geometry, AX hierarchy, cautious ad filtering and protected form/banner
content, plus the existing trusted-input/artifact/cancellation checks. Four live
Codex requests (`gpt-6.1-sol`, low reasoning) then consumed captured native fixture
observations, with the last three reusing the same ephemeral thread. Cached-input
hit rates were 0%, 56.95%, 71.15% and 77.39%; the weighted aggregate was 61.98%
(140,416 cached tokens out of 226,555 input tokens; 173 output tokens). This is
an actual transport/cache measurement, not an autonomous website-task benchmark
or proof of subscription-quota savings. The opt-in script
`scripts/measure_browser_cache.py` reproduces at most four calls; native capture
is enabled with `SMARTI_TEST_BROWSER_OBSERVATIONS` when running
`scripts/test_tauri_browser_preview.ps1`. Local page payloads/reports are not
committed.

References: [Codex App Server thread continuation](https://learn.chatgpt.com/docs/app-server#start-a-turn),
[Codex context configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[OpenAI agent prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching#multi-turn-agent),
[Gemini caching](https://ai.google.dev/gemini-api/docs/generate-content/caching),
and [Anthropic automatic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching#automatic-caching).
These contracts and measurements support the changes; they do not guarantee a
particular cache hit rate or total cost reduction for future tasks.
