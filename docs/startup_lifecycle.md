# Smarti startup and desktop ownership

The existing Tauri `main` window is created hidden. Rust prepares its centered,
monitor-based default size before showing it, then maximizes it if the last
session was maximized. Only this normal/maximized choice is persisted in
`window-placement.json`; manual sizes and positions are session-only. Legacy
coordinates and dimensions are ignored. Minimizing does not replace the last
choice, and restoring a maximized launch returns to the centered default size.
The lightweight HTML/boot entry paints one static centered icon against the shared theme
background before importing React. React keeps that surface until the Core
health check, legal state and required first-screen bootstrap have succeeded.
The handoff changes content without replacing or resizing the native window.

## Source runs and returning from sleep

`scripts/run_tauri_dev.ps1` uses built Web files by default. It builds them
before startup and `run_desktop_stable.mjs` serves an immutable private snapshot
for that launch. There is no Vite HMR client or development WebSocket in this
mode. The running Web files remain available even if another build replaces
`desktop/dist`. The native host and Core supervision are unchanged.

Vite's development client reloads the entire document after its WebSocket
disconnects and the server responds again. That connection can be interrupted
during sleep. Opt into this behavior with `-LiveReload` only for frontend coding;
normal source runs load UI changes on their next complete launch. Packaged
applications already use embedded built files and do not need this local server.

## Optional loading artwork

The loading artwork follows the resolved startup theme, including System mode:

- Light: **`desktop/public/loading-icon.png`**.
- Dark: **`desktop/public/loading-icon-dark.png`**.

Use a square PNG with a transparent background, preferably 256×256 or 512×512.
Keep the artwork centered with modest transparent margins. The visible symbol
is approximately 72×72 logical pixels, without motion or effects. The current
supplied dark image is an unchanged white-on-black PNG with broad margins;
its 118×118 display box and CSS screen blending keep the visible symbol close
to the light icon's size and merge the black margins into the shared background.
That sizing is specific to this artwork's margins.

There is no configuration change: a valid file is selected automatically before
the native window's first paint, without briefly displaying the original first.
If the selected theme's artwork is absent or cannot be decoded,
`assets/logo.png` remains visible with its original size and rendering. The
original artwork is preserved. Vite copies public artwork into the Web output;
add the PNG before your next build/package run. Existing installed packages
need rebuilding to include new artwork or these source changes. The packaging
source fingerprint includes `desktop/public`, so changes to this PNG also
invalidate stale frozen build inputs.

## Lifecycle

- Closing to the tray keeps the desktop host and Core alive together.
- Full quit, ordinary close with tray disabled, and main-window destruction
  exit the host and shut Core down through its existing stdin protocol.
- Unexpected Core termination or startup failure hides owned windows and exits
  the app, including its tray. A redacted reason is appended to
  `desktop-lifecycle.log` beside the native `window-placement.json`.
- On Windows, a private kill-on-close Job owns the launched Core and its child
  processes. An abrupt desktop termination closes that kernel handle. It never
  attaches to an unrelated existing process. Explicit child breakaway is allowed.
- The Core watches the parent pipe before initialization. EOF requests shutdown
  and bounds cleanup even if construction has stalled. A generation/state check
  also prevents a delayed launch becoming active after an ordinary quit/restart.
- Transient interface module/CSS fetch failures automatically reload only the
  WebView, at most twice (400ms and 1200ms after failure), while Core remains
  active. A failed ES module import is cached in the current document, so merely
  calling the same import again does not recover it. The counter is stored in
  sessionStorage per main/voice surface and cleared only when the first screen
  is ready or the user explicitly retries. Storage failure disables automatic
  navigation. Evaluation/render errors and exhausted retries retain the visible
  manual reload action. Console diagnostics contain only fixed stage/category
  and retry metadata, never exception messages, URLs, stacks or user content.
  A missing initial document is bounded by a native 30-second guard.
  Real failures are distinct from the icon-only normal loading state.

First-run consent uses the shared native HTML `Dialog`, buttons and checkbox,
with centered responsive composition, keyboard focus handling and internally
scrolling terms. The legal text, version and authenticated acceptance endpoint
retain their existing authority. Declining exits the entire desktop/Core.

## Focused verification

Run the startup/consent/recovery frontend tests, typecheck and Web build;
`cargo test --lib --locked`; and the headless Core/parent-control tests.
After a Web build, `scripts/verify_startup_native.ps1` builds an isolated QA
executable from current source and runs `verify_startup_native.cjs`. Its fresh
data, keyring/account isolation, evidence and screenshots live under
`.codex-local/startup/`. It does not control a personal instance or build an
installer. Native source QA and installer/portable acceptance stay separate.

For module-fetch recovery, build with `-BuildOnly -HttpFrontend`, then run
`node scripts/verify_startup_native.cjs --module-recovery`. It injects failed
requests in the owned QA WebView and checks automatic entry/App recovery,
bounded retries, explicit retry, evaluation errors and unchanged Core/window.
This mode serves the production Web build on a private loopback server because
WebView2's embedded custom protocol bypasses CDP Fetch interception. It leaves
the normal embedded frontend and the personal development server untouched.

`node scripts/verify_startup_native.cjs --resume` uses the normal snapshot server
with the isolated `-HttpFrontend` QA executable. It freezes and resumes the
renderer and interrupts/restores its connection, checking the same document,
draft, native window and Core. These controlled cases do not put the user's
computer to sleep and are separate from physical system-sleep evidence.

For focused window-mode regression checks, run the build with `-BuildOnly`,
then `node scripts/verify_startup_native.cjs --window-mode`. This verifies
legacy-state migration, centered defaults, repeated launches without growth,
manual resizing, maximize/restore, and quitting while minimized in QA data only.
