# SmartiAI Architecture

SmartiAI is in the final transition from a Python/PyQt6 desktop client to a
Tauri 2 + React Windows client around the same Python agent runtime. The Tauri
client is the packaged migration target; the PyQt client remains runnable and
is the authoritative one-to-one UI specification until Point 17 is explicitly
approved. The agent/runtime API remains `smarti.core.SmartiCore`, implemented by
focused domain mixins under `smarti/agent/`.

## Desktop product boundary

- `desktop/src/` owns the React Workspace: RTL chat, right conversation drawer,
  left on-demand Workbench, composer, management center and source-derived
  light/dark presentation.
- `desktop/src-tauri/` is the trusted Windows host. It owns the application
  window, single instance, tray, notifications/taskbar attention, file dialogs,
  updater, Core supervision and Tauri-owned child WebViews.
- `smarti_core_service.py` starts one Qt-free Python Core sidecar. The Core owns
  the agent loop, tools, policy, history, settings/secrets, memory, tasks,
  diagnostics and every other business/runtime operation.
- Rust holds the random per-launch bearer token and exposes only narrow Tauri
  commands. React reaches Python through the authenticated loopback `/v2`
  contract; the credential never enters frontend storage or serialized state.
- `smarti/control_plane_contract.py` is the authoritative contract generator;
  `desktop-contract/v2.contract.json` and `v2.generated.d.ts` must remain equal
  to it.

## Workspace, Browser and Canvas

- `desktop/src/App.tsx`, `Composer.tsx`, `RichMessage.tsx` and
  `WorkbenchPanels.tsx` reproduce the PyQt composition and state behavior. The
  granular code-derived map is `docs/tauri_ui_source_parity.md`.
- `desktop/src-tauri/src/browser.rs` owns Smarti Browser tabs and WebView2 child
  WebViews. User controls and Python automation address the same stable visible
  target through the in-process CDP broker; no installed Chrome/Edge HWND and
  no stable remote-debugging port is embedded.
- Persistent and Guest browser profiles are distinct. Profile import is
  explicit and copy-based, never modifies a third-party source profile and
  never extracts passwords.
- `smarti/canvas_model.py` is the Qt-free persisted Canvas authority.
  `desktop/src/CanvasPanel.tsx` renders it in an opaque-origin
  `sandbox="allow-scripts"` iframe with restrictive CSP and validated messages.
- The legacy modules `smarti/chat.py`, `smarti/workspace_ui.py`,
  `smarti/native_browser.py`, `smarti/visual_canvas.py`, `smarti/ui_pages.py`
  and related helpers remain available only as the comparison client through
  Point 16C/user acceptance. Their internal browser host is not the Tauri
  architecture.

## Agent Runtime Modules

- `smarti/core.py`: compatibility facade that composes `SmartiCore`.
- `smarti/agent/shared.py`: shared imports and integration dependencies used by
  the domain mixins.
- `smarti/agent/lifecycle.py`: startup, extension catalog refresh, trust state,
  basic paths, and small runtime helpers.
- `smarti/agent/browser_runtime.py`: persistent browser process helpers used by
  browser automation.
- `smarti/agent/execution_policy.py`: cancellation, subprocess execution,
  sandbox and autonomy policy checks, tool observations, and schema validation.
- `smarti/agent/tool_calls.py`: tool-call normalization, validation, batching,
  planner/task state, and compact model feedback.
- `smarti/agent/runtime_services.py`: SSL/network helpers, MCP launch
  environment, command classification, step text, and crash/cancel recovery.
- `smarti/agent/background_runtime.py`: background task resume, recurrence,
  dedupe, and worker-thread scheduling.
- `smarti/agent/extensions.py`: custom tools, MCP installs, Skills/Clawhub, and
  installed software discovery.
- `smarti/agent/model_context.py`: model setup, chat/session persistence,
  settings and secrets, token budgets, system prompt, API retry, and final
  response verification.
- `smarti/agent/messaging.py`: attachment payload handling and the main
  `send_message` loop.
- `smarti/agent/automation.py`: browser entrypoint and Windows UI/computer
  automation helpers.
- `smarti/agent/tool_dispatch.py`: audited built-in tool dispatch.
- `smarti/agent/system_tools.py`: weather, shell, git, project-check, process,
  clipboard, OCR, custom Python tool, and MCP execution tools.
- `smarti/agent/web_content.py`: website scraping and local document/image
  reading tools.
- `smarti/agent/email_tools.py`: email configuration, IMAP/SMTP helpers, search,
  send, folders, and attachments.
- `smarti/agent/productivity_tools.py`: internet search, local search, app/web
  opening, reminders, notifications, public background-task APIs, and memory
  tools.
- `smarti/agent/speech.py`: text-to-speech cleanup, synthesis, and playback.

## Compatibility Notes

Existing imports should continue to use:

```python
from smarti.core import SmartiCore
```

The root `smarti_core.pyw` remains the legacy source launcher through Point 16C
and imports only `smarti.app.main` at runtime. Tauri source development uses
`scripts/run_tauri_dev.ps1`; the packaged application starts the headless Core
itself and does not expose a console or localhost page.

## Dependency and package layout

- `requirements-core.txt` is the Qt-free production Core/private-runtime set.
- `requirements.txt` retains PyQt only for the comparison client until Point 17.
- `requirements-build.txt` contains build tooling for the PyInstaller `onedir`
  Core sidecar.
- `scripts/build_tauri_release.ps1` stages the sidecar and pinned private
  Python/Node runtimes, builds the per-user Tauri NSIS package and portable ZIP,
  runs hidden product/browser smokes and emits hashes/signature evidence.
- The updater fails closed without its signing key, public key and endpoint.
  Windows Authenticode and Tauri updater signing are separate release concerns.
