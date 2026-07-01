# SmartiAI Windows Packaging

This folder contains the release recipe for SmartiAI Agent for Windows.

## What gets built

- `SmartiAI.exe` from the Python/PyQt application using PyInstaller.
- `runtime/python`, a private Python embeddable runtime with `pip`, Smarti requirements, and `uv`.
- `runtime/node`, a private Node.js runtime with `npm` and `npx` for MCP packages.
- A portable ZIP under `release/`.
- A setup EXE under `release/` when Inno Setup 6 is installed.

The application EXE, setup EXE, and installer shortcuts use `assets/smarti.ico`.

## Build locally

From the repository root:

```powershell
.\scripts\build_release.ps1 -Version 0.81.1
```

For a clean rebuild:

```powershell
.\scripts\build_release.ps1 -Version 0.81.1 -Clean -ForceRuntime
```

The generated `build/`, `dist/`, `.build-cache/`, `.venv-build/`, and `release/` folders are intentionally ignored by Git.

The build script uses a short working directory, `C:\SmartiAI-build` when writable, to avoid Windows Long Path failures in large dependencies. Override it with `SMARTI_BUILD_WORK_DIR` when needed. Final artifacts are still copied to `release/` in the repository.

The release script verifies that `APP_VERSION` matches the requested release version. The runtime preparation step verifies developer/build dependencies with `pip check`, verifies the private runtime dependencies with `pip check`, prunes packaging-only `litellm` benchmark/static output files that can exceed classic Windows path limits, and then the release script force-resynchronizes `assets\` into `_internal\assets`, verifies the copied assets by SHA-256, and checks that the installer file layout stays within the path budget before creating the ZIP or setup EXE.

## Runtime versions

Default Python and Node.js versions are pinned in `runtime-versions.json`. Update that file for future releases, or override downloads for a single build with:

```powershell
$env:SMARTI_PYTHON_VERSION = "3.12.10"
$env:SMARTI_PYTHON_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
$env:SMARTI_NODE_VERSION = "22.16.0"
$env:SMARTI_NODE_URL = "https://nodejs.org/dist/v22.16.0/node-v22.16.0-win-x64.zip"
.\scripts\build_release.ps1 -Version 0.81.1
```

## Installer behavior

The Inno Setup installer defaults to `%LOCALAPPDATA%\SmartiAI` and does not require admin rights. This keeps the private Python runtime writable so Smarti can install dynamic Skill dependencies and continue downloading/running MCP packages through its private Node.js runtime. Existing installs may continue using their previous app directory during silent upgrades.

## GitHub release updates

Smarti checks `https://api.github.com/repos/menachem-dadon/SmartiAI-Agent-for-Windows/releases/latest`, compares the release tag to `APP_VERSION`, and downloads the attached Windows asset that matches the current install type. Installed copies prefer an asset whose name contains `setup` and ends with `.exe`; portable ZIP copies prefer an asset whose name contains `portable` and ends with `.zip`. Publish the release with tag `V0.81.1` or `0.81.1`, attach `SmartiAI-Agent-for-Windows-0.81.1-Setup.exe`, and also attach `SmartiAI-Agent-for-Windows-0.81.1-win-x64-portable.zip`. GitHub's release asset digest is used for SHA-256 verification when available.
