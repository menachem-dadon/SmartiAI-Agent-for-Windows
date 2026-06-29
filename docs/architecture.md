# SmartiAI Architecture

SmartiAI is a Python/PyQt6 desktop agent. The UI and application lifecycle live
in `smarti/app.py`, `smarti/chat.py`, and the UI helper modules. The agent
runtime is exposed as `smarti.core.SmartiCore` for compatibility, while the
implementation is split into focused domain mixins under `smarti/agent/`.

## Agent Runtime Modules

- `smarti/core.py`: compatibility facade that composes `SmartiCore`.
- `smarti/agent/lifecycle.py`: startup, extension catalog refresh, trust state,
  basic paths, and small runtime helpers.
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
`PyQt6-WebEngine` for the optional Live Visual Canvas. Build-only dependencies
stay in `requirements-build.txt`.
