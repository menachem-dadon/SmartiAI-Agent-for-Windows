# Point 16 packaging and release evidence

- Evidence date: 2026-08-24 (Asia/Jerusalem)
- Product version: `0.87.0`
- Candidate type: local unsigned Tauri/NSIS and portable evidence only
- Point state: local packaging foundation `COMPLETE` under the user's
  2026-08-24 current-computer validation policy; final recovered-product and
  package acceptance moved to Point 16C

## Implemented release path

`scripts/build_tauri_release.ps1` is the canonical one-command pipeline. It
checks the version in Python, npm, Cargo and Tauri; builds a Qt-free PyInstaller
`onedir` Core sidecar; prepares pinned private Python and Node runtimes; stages
Tauri resources; builds a per-user NSIS package and portable ZIP; and emits
SHA-256 and Authenticode evidence. Production updater builds fail closed unless
the Tauri private signing key, updater public key and endpoint are supplied.

The package includes an NSIS preinstall hook which detects the old Inno Setup
uninstaller, backs up install-local legacy data before invoking it, and records
the transition. The headless Core separately prepares an idempotent backup and
compatible history/bookmark/cookie import from `SmartiChromeProfile`; WebView2
never opens that directory in place and the source is not deleted.

## Local artifact evidence

The exact artifact sizes and hashes below are from the final generated
`release/SmartiAI-Agent-for-Windows-0.87.0-manifest.json`:

| Artifact | Bytes | SHA-256 | Signature status |
|---|---:|---|---|
| `release/SmartiAI-Agent-for-Windows-0.87.0-Setup.exe` | `246657470` | `d0b51a35986be68e4267b6ea93fdbbd4f5a90f6e101a521d0088948c902e0b33` | `NotSigned` |
| `release/SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip` | `446217457` | `e860a1c48f2d095c52420a34b5afb2351650fa8b22d7eab8ee89ed9913ac0703` | no Authenticode claim |

The build used the embedded WebView2 bootstrapper. A separate offline WebView2
mode is implemented by the `-OfflineInstaller` release switch but was not built
in this local evidence run.

## Verification performed

- Qt-free Core import and Python `compileall` passed.
- dependency preparation passed `pip check`; the build asserted that neither
  the Core sidecar nor private runtime contained PyQt/Qt.
- React TypeScript/Vite production build passed and all 40 Vitest checks passed.
- focused browser-migration test passed; all seven LocalGateway integration
  tests passed, including generated-contract equality.
- all 374 Python tests ran: 373 passed, while the first headless subprocess
  smoke exceeded its 30-second timeout under concurrent Release linking. Its
  isolated rerun and the stronger packaged supervisor smoke passed.
- the hidden packaged smoke reached Core Ready, rejected a duplicate Core,
  retained its PID over WebView reload, detected an intentional crash,
  restarted as generation 2 and shut down gracefully.
- no computer-control click-through or broad live UI QA was performed.

## Optional cross-machine/release evidence not performed

| Scenario | Windows 10 clean VM | Windows 11 clean VM | Current machine |
|---|---|---|---|
| clean install, WebView2 present/missing | NOT RUN | NOT RUN | NOT CLAIMED |
| upgrade from current PyQt/Inno install | NOT RUN | NOT RUN | source hook only |
| signed in-place Tauri update | NOT RUN | NOT RUN | signing inputs absent |
| cancel/corrupt/invalid-signature update | NOT RUN | NOT RUN | deterministic UX/source only |
| portable chat/browser/tool smoke | NOT RUN | NOT RUN | supervisor smoke only |
| uninstall, retained data, reinstall | NOT RUN | NOT RUN | NOT CLAIMED |

This host exposes no Hyper-V cmdlets, and the required updater signing variables
were absent. The candidate is also Authenticode `NotSigned`. The user decided on
2026-08-24 that clean Windows/VM matrices are not migration gates and that final
functional/package acceptance will be performed on the current computer after
UI recovery in Point 16C. This document therefore records Point 16's packaging
foundation as complete without calling the artifacts signed or claiming broad
Windows compatibility. Publishing to GitHub Releases was not requested and was
not performed.

## Deferred or optional release-hardening actions

1. When a signed public release is desired, supply protected Tauri
   update-signing and Windows Authenticode credentials plus the production
   updater endpoint, then build and verify signed artifacts.
2. If broad Windows certification is desired later, execute the matrix above on
   clean x64 Windows 10 and 11 machines. Its absence does not block Points
   16A-17 and must remain documented as unverified portability evidence.
3. Add a custom Hebrew Tauri NSIS message file if fully translated installer
   chrome is required; the current NSIS run warns that Tauri-specific Hebrew
   messages fall back rather than being custom-translated.
