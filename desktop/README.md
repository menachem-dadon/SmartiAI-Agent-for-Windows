# SmartiAI Desktop

The Point 5 Tauri 2 + React + TypeScript shell. The Rust host owns the Python
Core lifecycle and its per-launch credential; frontend code receives only
narrow status, health, and restart commands.

## Development

From the repository root:

```powershell
.\scripts\run_tauri_dev.ps1
```

The command installs the exact `package-lock.json` dependency graph, launches
Vite/Tauri, and lets the Rust supervisor start `smarti_core_service.py`. A
WebView reload does not restart the Core. Closing the Tauri process asks the
Core to stop through its inherited stdin pipe and force-terminates it only after
the bounded grace period.

Development overrides:

- `SMARTI_PYTHON`: explicit Python executable.
- `SMARTI_PROJECT_ROOT`: checkout containing `smarti_core_service.py`.
- `SMARTI_CORE_BINARY`: packaged `smarti-core.exe` override.

The default capability grants no shell plugin and no filesystem plugin. The
Core bearer token remains private Rust state and is never serialized to React.

## Checks

```powershell
npm test
npm run typecheck
npm run build
cargo check --manifest-path src-tauri/Cargo.toml
cargo test --manifest-path src-tauri/Cargo.toml
..\scripts\smoke_tauri_supervisor.ps1
```

The supervisor smoke opens the Tauri WebView hidden, verifies the real Python
Core readiness handshake and Rust health proxy, reloads the WebView without
replacing the Core, detects an intentional Core crash, restarts one new Core,
and shuts it down through the inherited control pipe.
