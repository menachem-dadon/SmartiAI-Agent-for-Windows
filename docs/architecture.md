# SmartiAI Architecture

SmartiAI is a Python/PyQt6 desktop agent. The UI and application lifecycle live
in `smarti/app.py`, `smarti/chat.py`, and the UI helper modules. The agent
runtime is exposed as `smarti.core.SmartiCore` for compatibility, while the
implementation is split into focused domain mixins under `smarti/agent/`.

## Desktop Workspace

- `smarti/chat.py` owns the central conversation surface and composes the
  top-level Workspace shell.
- `smarti/workspace_ui.py` provides the collapsible conversation sidebar, the
  dynamic left work area, file/document/media previews, embedded browser, terminal,
  conversation-artifact list, and the lazy settings-and-management hub.
- `smarti/native_browser.py` embeds an app-mode Chromium native window as a Qt
  child on Windows while preserving a loopback-only CDP endpoint for Playwright.
- `smarti/browser_profile.py` implements explicit, copy-based one-time import
  of compatible cookies, history, and bookmarks into Smarti Browser. It never
  imports passwords or modifies the source profile.
- `smarti/webengine_probe.py` retains a crash-isolated compatibility check for
  non-Windows WebEngine paths. Windows avoids native WebEngine startup crashes
  by using the native Chromium child host directly.
- The canvas uses a temporary native Chromium host and tokenized loopback HTTP
  bridge with a restrictive CSP. Smarti Browser uses a persistent native
  profile and exposes its visible target on port 49223 for Playwright/CDP.

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

The root `smarti_core.pyw` remains the source launcher. It intentionally imports
only `smarti.app.main` at runtime so double-click startup failures can be logged
to `smarti_startup_error.log` instead of disappearing silently under `pythonw`.

## Dependency Layout

Runtime dependencies are consolidated in `requirements.txt`, including
compatible PyQt 6.11 bindings, the WebEngine compatibility path, and Playwright
for structured browser automation. Windows browser/canvas rendering uses the
installed Chromium engine through `smarti/native_browser.py`.
Build-only dependencies stay in `requirements-build.txt`.
