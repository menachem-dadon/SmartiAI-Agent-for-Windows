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

## Optional loading artwork

Place your minimalist icon at **`desktop/public/loading-icon.png`**.
Use a square PNG with a transparent background, preferably 256×256 or 512×512.
Keep the artwork centered with modest transparent margins. It is displayed at
72×72 logical pixels with its aspect ratio preserved, without motion or effects.
It must remain readable against both the light and dark Smarti backgrounds.

There is no configuration change: a valid file is selected automatically before
the native window's first paint, without briefly displaying the original first.
If it is absent or cannot be decoded, `assets/logo.png` remains visible. The
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
- Interface/module failures retain a visible reload action while Core remains
  active. A missing initial document is bounded by a native 30-second guard.
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

For focused window-mode regression checks, run the build with `-BuildOnly`,
then `node scripts/verify_startup_native.cjs --window-mode`. This verifies
legacy-state migration, centered defaults, repeated launches without growth,
manual resizing, maximize/restore, and quitting while minimized in QA data only.
