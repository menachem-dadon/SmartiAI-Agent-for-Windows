# SmartiAI Windows Packaging

Point 16 makes Tauri the production package while keeping the legacy PyQt
launcher available for comparison until Point 17.

## Production outputs

- Tauri 2 `smarti-desktop.exe` and a per-user NSIS setup executable.
- Qt-free PyInstaller `onedir` headless Core sidecar.
- private pinned Python and Node runtimes for Skills and MCP dependencies.
- portable ZIP, SHA-256 manifest and, for production builds, signed Tauri
  updater artifacts.

The canonical command from the repository root is:

```powershell
.\scripts\build_tauri_release.ps1 -Version 0.87.0
```

It validates the four version declarations, builds/stages every layer, rejects
Qt in the production Core/runtime, creates the NSIS/portable outputs and records
hashes and Authenticode status. `SMARTI_BUILD_WORK_DIR` can select a short work
path; final artifacts are copied to `release/`.

For an explicitly unsigned current-machine acceptance build, use:

```powershell
.\scripts\build_tauri_release.ps1 -Version 0.87.0 -AllowUnsignedLocal
```

This still runs the full packaged supervisor/chat smoke and the packaged
WebView2 Browser smoke. The resulting manifest contains both payloads under
`packageSmoke`; it is not merely a successful linker/build flag.

Production updater builds require `TAURI_SIGNING_PRIVATE_KEY`,
`SMARTI_UPDATER_PUBLIC_KEY` and `SMARTI_UPDATER_ENDPOINT`. Update signatures
and Windows Authenticode are independent. `-AllowUnsignedLocal` exists only for
local packaging evidence: it disables updater artifact creation and must never
be published or described as signed. `-OfflineInstaller` selects Tauri's full
offline WebView2 installer instead of the embedded bootstrapper.

## Runtime versions

Default Python and Node.js versions and the SHA-256 digests of every downloaded runtime/bootstrap file are pinned in `runtime-versions.json`. Update both the URL/version and verified digest for future releases, or override downloads for a single build with:

```powershell
$env:SMARTI_PYTHON_VERSION = "3.12.10"
$env:SMARTI_PYTHON_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$env:SMARTI_PYTHON_SHA256 = "<verified 64-character SHA-256>"
$env:SMARTI_NODE_VERSION = "22.23.2"
$env:SMARTI_NODE_URL = "https://nodejs.org/dist/v22.23.2/node-v22.23.2-win-x64.zip"
$env:SMARTI_NODE_SHA256 = "<verified 64-character SHA-256>"
# Optional only when overriding the pip bootstrap file:
$env:SMARTI_GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
$env:SMARTI_GET_PIP_SHA256 = "<verified 64-character SHA-256>"
.\scripts\build_tauri_release.ps1 -Version 0.87.0
```

## Installer behavior

The NSIS package installs per-user. Its hooks detect the old Inno Setup entry,
back up install-local legacy data under `%APPDATA%\SmartiAI\migration`, invoke
the old uninstaller silently and retain normal Smarti user-data paths. The Core
also prepares a one-time backup/import of compatible history, bookmarks and
cookies from the old native-Chromium profile. WebView2 is never pointed at that
profile in place and the source is never deleted.

## Release boundary

The About page uses Tauri's updater plugin and restarts only after a verified
download/install. Publishing, code-signing, updater hosting and clean Windows
10/11 VM matrices are separate release operations; this command does not imply
that they were performed.

Point 16C acceptance is intentionally current-machine and does not install over
the user's existing Smarti. The NSIS artifact is built and hashed, while the
portable tree is exercised from an isolated `SMARTI_DATA_DIR`. Clean install,
upgrade over the current PyQt/Inno copy, uninstall/reinstall and preservation of
live user data require separate explicit approval and a backup first.

## Build troubleshooting

- Run from the repository root; npm commands are executed in `desktop/` by the
  script.
- If Cargo is not on `PATH`, the script uses the current user's `.cargo\bin`.
- `CARGO_HTTP_CHECK_REVOKE=false` may be required on this machine when the
  Windows certificate-revocation check blocks Cargo downloads.
- Use a short ASCII `SMARTI_BUILD_WORK_DIR` only when path/tool limitations
  require it. The script confines its clean/reset operations to that work root.
- `-SkipRuntime` and `-SkipCoreBuild` are reuse switches, not proof shortcuts;
  the referenced prepared trees must exist and still pass the Qt-free checks.
- `-SkipPackageSmoke` intentionally removes package acceptance evidence and
  must not be used for a Point 16C completion build.
