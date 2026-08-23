# Windows desktop integration (Point 15)

The Tauri/Rust host now owns Windows application behavior. Qt is not involved.

- `tauri-plugin-single-instance` keeps one desktop process and routes `show`,
  `new-chat`, `voice`, `update-shutdown`, and scoped `--session=...` activation
  data into the trusted React shell.
- The native tray provides restore, new chat, voice, and explicit full quit.
  Ordinary window close hides Smarti to the tray without stopping Core or
  background work; only explicit Quit allows process shutdown.
- The configurable global voice shortcut is unregistered/re-registered by the
  Rust plugin and cleaned up with the desktop process.
- native Windows notifications do not mark attention as read. Conversation
  activation selects only the supplied session; read acknowledgement remains a
  separate authenticated Core command.
- durable unread totals are projected to the taskbar using a generated overlay
  count (capped visually at 99), title text and `FlashWindowEx` attention when
  Smarti is not focused.
- the Rust host sets `SmartiAI.Desktop` AUMID, Windows 11 rounded-corner
  preference, restores size/position only when it intersects a current monitor,
  and keeps the custom 36 px Tauri title/drag surface.

The notification provider and some window effects still depend on the user's
Windows notification/privacy policy. Multi-monitor and DPI automation cannot
substitute for the physical user matrix; the saved placement is guarded so a
removed monitor cannot strand the window off-screen.

