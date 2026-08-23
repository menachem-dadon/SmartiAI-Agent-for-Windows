# Smarti Browser product support matrix (Point 14)

This matrix describes the Smarti-owned WebView2 browser surface. It is not a
claim that WebView2 is Edge or Chrome. The visible user tab and the target used
by `browser_automation_manager` remain the same Rust-owned child WebView; no
installed browser window, external profile in place, or remote-debugging port
is used.

| Area | Smarti support | Boundary |
|---|---|---|
| Tabs and navigation | New, close, duplicate, drag-reorder, pin, recently-closed restore, persistent-session restore, titles, loading/crash/audio states, back/forward/reload/stop/home and LTR omnibox | Inactive WebViews are hidden and asked to enter the frozen lifecycle state. Restore is capped at 12 tabs. |
| Keyboard and focus | `Ctrl+L/T/W/Shift+T/F/D/R`, Alt+Left/Right, governed popup tabs and predictable active-target focus | Site-reserved shortcuts can still vary with WebView2 and IME configuration. |
| Page commands | Find, 25-500% zoom, full screenshot, print-to-PDF, copy address and open externally | Native print preview, device emulation and DevTools remain developer-oriented WebView2/CDP facilities rather than Edge UI. |
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

