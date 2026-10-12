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
