# SmartiAI wide-workspace icon assets

All files below are active asset names used by the wide workspace, unified
management center, custom window frame, and embedded browser. Upload both
theme variants to `assets/`:

- `<name>_dark.png` is shown in the dark theme (use a light foreground).
- `<name>_light.png` is shown in the light theme (use a dark foreground).

Use transparent RGBA PNGs at `64 x 64 px`, with the visible glyph centered in
an approximately `48 x 48 px` safe area. Do not bake a background, border,
shadow, hover state, or rounded square into the PNG; Qt supplies those states.
Keep every pair geometrically identical so theme changes do not make controls
jump. A single-color outline family with rounded terminals will fit the current
Smarti design best.

## Essential shell and window controls

- `workbench_open_icon_dark.png` / `workbench_open_icon_light.png` — open the left workspace; panel with an inward arrow.
- `workbench_close_icon_dark.png` / `workbench_close_icon_light.png` — collapse the left workspace; mirrored counterpart.
- `sidebar_expand_icon_dark.png` / `sidebar_expand_icon_light.png` — expand the right RTL sidebar; appears on logo hover while collapsed.
- `sidebar_collapse_icon_dark.png` / `sidebar_collapse_icon_light.png` — collapse the right RTL sidebar.
- `window_minimize_icon_dark.png` / `window_minimize_icon_light.png` — Windows minimize glyph.
- `window_maximize_icon_dark.png` / `window_maximize_icon_light.png` — single-window maximize glyph.
- `window_restore_icon_dark.png` / `window_restore_icon_light.png` — overlapping-window restore glyph.
- `window_close_icon_dark.png` / `window_close_icon_light.png` — title-bar close glyph.

## Workspace and tabs

- `workspace_files_icon_dark.png` / `workspace_files_icon_light.png` — workspace files tab.
- `workspace_browser_icon_dark.png` / `workspace_browser_icon_light.png` — embedded browser tab; globe outline.
- `workspace_terminal_icon_dark.png` / `workspace_terminal_icon_light.png` — terminal tab.
- `workspace_canvas_icon_dark.png` / `workspace_canvas_icon_light.png` — visual canvas tab.
- `workspace_artifacts_icon_dark.png` / `workspace_artifacts_icon_light.png` — generated artifacts tab.
- `workspace_add_tab_icon_dark.png` / `workspace_add_tab_icon_light.png` — add workspace tab.
- `workspace_tab_close_icon_dark.png` / `workspace_tab_close_icon_light.png` — close one workspace tab.

## Embedded browser toolbar

- `workspace_browser_back_icon_dark.png` / `workspace_browser_back_icon_light.png` — browser back.
- `workspace_browser_forward_icon_dark.png` / `workspace_browser_forward_icon_light.png` — browser forward.
- `workspace_browser_reload_icon_dark.png` / `workspace_browser_reload_icon_light.png` — reload.
- `workspace_browser_home_icon_dark.png` / `workspace_browser_home_icon_light.png` — Smarti browser start page.
- `browser_more_icon_dark.png` / `browser_more_icon_light.png` — browser-only three-dot menu.

## Embedded browser menu

- `browser_find_icon_dark.png` / `browser_find_icon_light.png` — find in page.
- `browser_zoom_icon_dark.png` / `browser_zoom_icon_light.png` — page zoom.
- `browser_device_icon_dark.png` / `browser_device_icon_light.png` — device/mobile toolbar.
- `browser_screenshot_icon_dark.png` / `browser_screenshot_icon_light.png` — take screenshot.
- `browser_import_icon_dark.png` / `browser_import_icon_light.png` — one-time profile import.
- `browser_passwords_icon_dark.png` / `browser_passwords_icon_light.png` — passwords/autofill information.
- `browser_downloads_icon_dark.png` / `browser_downloads_icon_light.png` — downloads.
- `browser_history_icon_dark.png` / `browser_history_icon_light.png` — history and bookmarks library.
- `browser_external_icon_dark.png` / `browser_external_icon_light.png` — open in the system browser.
- `browser_clear_data_icon_dark.png` / `browser_clear_data_icon_light.png` — clear browsing data.
- `browser_settings_icon_dark.png` / `browser_settings_icon_light.png` — browser settings.

## Unified management center

- `workspace_settings_icon_dark.png` / `workspace_settings_icon_light.png` — workspace and browser settings.
- `settings_ai_icon_dark.png` / `settings_ai_icon_light.png` — models and AI providers.
- `settings_security_icon_dark.png` / `settings_security_icon_light.png` — security and privacy.
- `settings_tools_icon_dark.png` / `settings_tools_icon_light.png` — tools and communication.
- `settings_appearance_icon_dark.png` / `settings_appearance_icon_light.png` — voice, appearance, and system.
- `settings_advanced_icon_dark.png` / `settings_advanced_icon_light.png` — advanced and developer settings.

Until a pair is supplied, Smarti uses a compact text fallback; it no longer
borrows an unrelated PNG for these newly introduced controls.
