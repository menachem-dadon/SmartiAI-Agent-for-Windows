# Smarti Browser foundation - Point 6 evidence

## Decision

The production transport selected by Point 6 is WebView2's in-process Chrome
DevTools Protocol through the Rust broker. Smarti does not start or reparent an
installed Chrome, Edge, Brave, Chromium, or Vivaldi window. It does not open a
remote-debugging port. Each tab has stable `tab-*`, `wv2-target-*`, and request
IDs, and both the React chrome and the Python `browser_automation_manager` route
through the same Rust-owned Tauri child WebView.

The React chrome is trusted. Remote pages are separate child WebViews whose
labels do not match the only Tauri capability (`main`). A hostile remote page
therefore has no command capability, Core token, arbitrary file access, or
trusted-browser-chrome origin. The Core receives only a random, per-desktop-run
loopback broker credential in its supervised environment; the token never enters
React or remote content. The bridge binds to `127.0.0.1`, rejects missing tokens,
has a 2 MiB request limit, and ends with the desktop process.

## Profiles and import

- Persistent mode uses Smarti's own durable `persistent-webview2` data folder.
- Every Guest tab uses an incognito WebView2 controller and a process-scoped,
  tab-specific cache folder. Browsing data is cleared and that folder is removed
  on close and desktop shutdown. Guest state is never copied into persistent.
- `scripts/tauri_browser_import_spike.py` discovers Chrome, Edge, Brave,
  Chromium, and Vivaldi profiles, reads copied History/Cookie databases, reads
  bookmarks, and reports only counts/reasons. It never reports URLs or cookie
  values, reads passwords, modifies a source profile, or bypasses v20/App-Bound
  Encryption. Compatible current-user cookies are only feasibility evidence;
  insertion through WebView2's cookie manager belongs to the Point 14 wizard.

## Structured automation coverage

| Capability | Point 6 foundation | Implementation |
|---|---|---|
| Snapshot and semantic refs | Implemented | `Runtime.evaluate` builds stable `data-smarti-ref` entries and returns title, URL, direction, text, and refs. |
| Navigate | Implemented | `Page.navigate` or Rust `Webview.navigate`; HTTP/HTTPS policy is retained in Python and Rust. |
| Click, fill/type, press, scroll, select, hover | Implemented | Ref/selector actions through `Runtime` and `Input` CDP domains. |
| Upload | Implemented | Approved Core paths only, then `DOM.getDocument/querySelector/setFileInputFiles`. |
| Download | Foundation/manual | Native WebView2 download behavior works; final manager, collision and danger policy are Point 14. |
| Screenshot and PDF | Implemented | `Page.captureScreenshot` and `Page.printToPDF`; Python writes only to its controlled capture directory. |
| Console and network | Implemented raw transport | `Console`, `Log`, and `Network` CDP domains are allowed; final event aggregation is Point 14. |
| Storage and cookies | Implemented raw transport | `Storage`, `Network`, and `Runtime` CDP domains; sensitive Python policy remains authoritative. |
| Evaluate and raw CDP | Implemented | Allowlisted CDP domains; no `SystemInfo` or process-wide escape surface. |

## Feature and compatibility matrix

| Area | Status | Point 6 result / limitation |
|---|---|---|
| Built-in tabs, omnibox, back/forward/reload, HTTPS state, menu | Implemented | Polished RTL React chrome around Tauri child WebViews; omnibox is LTR. |
| Focus, resize, hide/show, DPI | Implemented and smoke-covered | CSS logical bounds are synchronized through Rust and WebView focus/visibility APIs. Manual multi-monitor/DPI matrix remains required below. |
| Hebrew text/IME | Implemented and smoke-covered | Native WebView2 input plus automated Hebrew input proof. Manual IME composition is still a user-visible check. |
| Popups | Implemented foundation | `window.open` is denied as an unmanaged window and emitted to trusted chrome for governed-tab creation. |
| Persistent and Guest isolation | Implemented and smoke-covered | Reload persistence and fresh-Guest absence are measured by the live smoke. |
| Downloads/uploads | Foundation | Native download and CDP upload; the complete download library/policy is Point 14. |
| Crash/process recovery | Foundation | WebView state carries crash fields; full renderer-process event UX is deferred to Point 14. Core crash/restart remains Point 5 evidence. |
| OAuth | WebView2-dependent | Standard OAuth should be tested per provider; providers that reject embedded user agents may require explicit external completion, never a reparented browser. |
| Passkeys/WebAuthn | WebView2/OS-dependent | Requires a supported WebView2 Runtime, Windows Hello configuration, and a real relying party. No universal support claim. |
| Vendor sync/extensions/internal pages | Unsupported by WebView2 | No Edge/Chrome account sync, extension store, or vendor internal settings. Smarti-owned equivalents are Point 14 decisions. |
| Password import | Intentionally unsupported | Smarti never extracts or imports saved passwords. |
| History/bookmark/cookie import | Feasibility implemented | Counts-only safe spike; final library/cookie-manager insertion UI is Point 14. |
| Installer impact | Deferred | Source dependencies are locked; clean-machine runtime and installer size evidence is Point 16. |

## Repeatable checks

The confirming live development smoke on 2026-08-21 measured a 3.702-second
first tab, returned the same `tab-00000001` / `wv2-target-00000001` to the
visible UI and CDP action, entered `שלום מטאורי`, reported
`blocked:capability` from the hostile Tauri probe, retained persistent storage
after reload, returned null from both fresh Guest checks, routed a popup to a
governed tab, exposed the WebAuthn API, and captured an estimated 13,224 bytes.
Live visual QA also inspected Google in light and dark chrome, Hebrew input,
maximize/resize, the same-target footer proof, and a menu layout that moves the
native WebView instead of being hidden behind its z-order.

`docs/tauri_browser_import_spike_report.json` is the counts-only machine report:
Chrome and Edge history/bookmarks were readable from copies; compatible cookie
count was zero, with locked databases and 110 encrypted cookies reported as
skipped/error categories rather than bypassed. Brave, Chromium, and Vivaldi
were not installed/detected on the test machine.

Automated live gate:

```powershell
.\scripts\smoke_tauri_browser.ps1
```

Safe import report:

```powershell
python .\scripts\tauri_browser_import_spike.py --output .\browser-import-report.json
```

Manual QA must be recorded for light and dark themes and for display scales
100%, 125%, 150%, and 200%: create/switch/close tabs; Hebrew IME composition;
back/reload/find/print; popup-to-tab; harmless download and approved upload;
resize/maximize/minimize/restore; hide/show the browser surface; move between
monitors; normal restart persistence; Guest cleanup; OAuth and WebAuthn where
accounts/hardware are available. Record unsupported provider behavior honestly.
