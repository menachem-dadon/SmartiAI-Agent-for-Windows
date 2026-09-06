use serde::{Deserialize, Serialize};
use std::fs;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, PhysicalPosition, PhysicalSize,
    WebviewUrl, WebviewWindow, WebviewWindowBuilder, Window, WindowEvent,
};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
#[cfg(not(windows))]
use tauri_plugin_notification::NotificationExt;

pub struct DesktopState {
    quitting: AtomicBool,
    close_to_tray: AtomicBool,
    workspace_ready: AtomicBool,
    unread_count: AtomicU32,
}

impl Default for DesktopState {
    fn default() -> Self {
        Self {
            quitting: AtomicBool::new(false),
            close_to_tray: AtomicBool::new(true),
            workspace_ready: AtomicBool::new(false),
            unread_count: AtomicU32::new(u32::MAX),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DesktopActivation {
    pub command: String,
    pub session_id: String,
    pub run_id: Option<String>,
    pub arguments: Vec<String>,
}

const WINDOW_LAYOUT_VERSION: u32 = 1;

#[derive(Debug, Clone, Deserialize, Serialize)]
struct WindowPlacement {
    #[serde(default)]
    layout_version: u32,
    x: i32,
    y: i32,
    width: u32,
    height: u32,
    maximized: bool,
}

impl WindowPlacement {
    fn can_restore(&self) -> bool {
        self.layout_version == WINDOW_LAYOUT_VERSION
            && (1..=8192).contains(&self.width)
            && (1..=8192).contains(&self.height)
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RtlMenuItem {
    id: Option<String>,
    text: Option<String>,
    enabled: Option<bool>,
    separator: Option<bool>,
    accelerator: Option<String>,
}

fn validate_rtl_menu_items(items: &[RtlMenuItem]) -> Result<(), String> {
    if items.is_empty() || items.len() > 64 {
        return Err("Native menu must contain between 1 and 64 items".into());
    }
    let mut ids = Vec::new();
    for item in items {
        if item.separator.unwrap_or(false) {
            continue;
        }
        let id = item.id.as_deref().unwrap_or("");
        let text = item.text.as_deref().unwrap_or("");
        if id.is_empty() || id.len() > 80 || ids.iter().any(|existing| existing == &id) {
            return Err("Native menu item IDs must be unique and non-empty".into());
        }
        if text.is_empty() || text.chars().count() > 160 || text.contains('\0') {
            return Err("Native menu item text is invalid".into());
        }
        if item
            .accelerator
            .as_deref()
            .is_some_and(|value| value.chars().count() > 40 || value.contains('\0'))
        {
            return Err("Native menu accelerator is invalid".into());
        }
        ids.push(id);
    }
    Ok(())
}

#[cfg(windows)]
fn popup_rtl_menu_windows(
    window: &Window,
    items: &[RtlMenuItem],
    x: i32,
    y: i32,
) -> Result<Option<String>, String> {
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::{LPARAM, WPARAM};
    use windows::Win32::UI::WindowsAndMessaging::{
        AppendMenuW, CreatePopupMenu, DestroyMenu, PostMessageW, SetForegroundWindow,
        TrackPopupMenu, MF_GRAYED, MF_SEPARATOR, MF_STRING, TPM_LAYOUTRTL, TPM_NONOTIFY,
        TPM_RETURNCMD, TPM_RIGHTALIGN, WM_NULL,
    };

    let hwnd = window.hwnd().map_err(|error| error.to_string())?;
    let menu = unsafe { CreatePopupMenu() }.map_err(|error| error.to_string())?;
    let result = (|| -> Result<Option<String>, String> {
        let mut actions = Vec::new();
        let mut command_id = 1usize;
        for item in items {
            if item.separator.unwrap_or(false) {
                unsafe { AppendMenuW(menu, MF_SEPARATOR, 0, PCWSTR::null()) }
                    .map_err(|error| error.to_string())?;
                continue;
            }
            let id = item.id.as_deref().expect("validated menu item ID");
            let mut label = item
                .text
                .as_deref()
                .expect("validated menu item text")
                .to_string();
            if let Some(accelerator) = item.accelerator.as_deref() {
                label.push('\t');
                label.push_str(accelerator);
            }
            let wide: Vec<u16> = label.encode_utf16().chain(std::iter::once(0)).collect();
            let flags = if item.enabled.unwrap_or(true) {
                MF_STRING
            } else {
                MF_STRING | MF_GRAYED
            };
            unsafe { AppendMenuW(menu, flags, command_id, PCWSTR(wide.as_ptr())) }
                .map_err(|error| error.to_string())?;
            actions.push((command_id, id.to_string()));
            command_id += 1;
        }
        unsafe {
            let _ = SetForegroundWindow(hwnd);
        }
        let selected = unsafe {
            TrackPopupMenu(
                menu,
                TPM_RIGHTALIGN | TPM_RETURNCMD | TPM_LAYOUTRTL | TPM_NONOTIFY,
                x,
                y,
                None,
                hwnd,
                None,
            )
        };
        // TrackPopupMenu owns a modal input loop. Posting WM_NULL after it returns is
        // the documented Win32 hand-off that releases the owner cleanly, including
        // when the user dismisses the menu by clicking its trigger or elsewhere.
        let _ = unsafe { PostMessageW(Some(hwnd), WM_NULL, WPARAM(0), LPARAM(0)) };
        let selected = selected.0.max(0) as usize;
        Ok(actions
            .into_iter()
            .find_map(|(command, id)| (command == selected).then_some(id)))
    })();
    let _ = unsafe { DestroyMenu(menu) };
    result
}

#[tauri::command]
pub fn desktop_popup_rtl_menu(
    window: Window,
    items: Vec<RtlMenuItem>,
    x: i32,
    y: i32,
) -> Result<Option<String>, String> {
    validate_rtl_menu_items(&items)?;
    #[cfg(windows)]
    {
        popup_rtl_menu_windows(&window, &items, x, y)
    }
    #[cfg(not(windows))]
    {
        let _ = (window, items, x, y);
        Err("Native RTL menu is available only on Windows".into())
    }
}

pub fn show_main(app: &AppHandle, activation: DesktopActivation) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
        let _ = window.request_user_attention(None);
    }
    let _ = app.emit("desktop://activation", activation);
}

pub fn activation_from_args(arguments: Vec<String>) -> DesktopActivation {
    let mut command = "show".to_string();
    let mut session_id = String::new();
    for item in &arguments {
        let normalized = item.trim_start_matches(['-', '/']).to_lowercase();
        if matches!(
            normalized.as_str(),
            "new-chat" | "voice" | "update-shutdown" | "show"
        ) {
            command = normalized;
        }
        if let Some(value) = item.strip_prefix("--session=") {
            session_id = value.chars().take(200).collect();
        }
    }
    DesktopActivation {
        command,
        session_id,
        run_id: None,
        arguments: arguments
            .into_iter()
            .take(32)
            .map(|item| item.chars().take(500).collect())
            .collect(),
    }
}

fn placement_path(app: &AppHandle) -> Option<std::path::PathBuf> {
    if let Some(data_dir) = std::env::var_os("SMARTI_DATA_DIR") {
        return Some(
            std::path::PathBuf::from(data_dir)
                .join("tauri-desktop")
                .join("data")
                .join("window-placement.json"),
        );
    }
    app.path()
        .app_data_dir()
        .ok()
        .map(|path| path.join("window-placement.json"))
}

fn save_placement(app: &AppHandle, window: &WebviewWindow) {
    if window.is_minimized().unwrap_or(false) {
        return;
    }
    let (Ok(position), Ok(size), Ok(maximized)) = (
        window.outer_position(),
        window.outer_size(),
        window.is_maximized(),
    ) else {
        return;
    };
    let placement = WindowPlacement {
        layout_version: WINDOW_LAYOUT_VERSION,
        x: position.x,
        y: position.y,
        width: size.width,
        height: size.height,
        maximized,
    };
    let Some(path) = placement_path(app) else {
        return;
    };
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(encoded) = serde_json::to_vec(&placement) {
        let _ = fs::write(path, encoded);
    }
}

fn restore_placement(app: &AppHandle, window: &WebviewWindow) -> bool {
    let Some(path) = placement_path(app) else {
        return false;
    };
    let Ok(data) = fs::read(path) else {
        return false;
    };
    let Ok(value) = serde_json::from_slice::<WindowPlacement>(&data) else {
        return false;
    };
    // Apply the wide default once for pre-existing compact placements. Subsequent
    // user resizes keep their normal persistence behavior.
    if !value.can_restore() {
        return false;
    }
    let visible = window.available_monitors().ok().is_some_and(|monitors| {
        monitors.iter().any(|monitor| {
            let area = monitor.work_area();
            let p = area.position;
            let s = area.size;
            (value.x as i64) < p.x as i64 + s.width as i64
                && (value.y as i64) < p.y as i64 + s.height as i64
                && value.x as i64 + 120 > p.x as i64
                && value.y as i64 + 80 > p.y as i64
        })
    });
    if !visible {
        // A disconnected monitor must use the full default-size path, rather
        // than merely centering the still-small startup shell.
        return false;
    }
    if window
        .set_position(PhysicalPosition::new(value.x, value.y))
        .is_err()
        || window
            .set_size(PhysicalSize::new(value.width, value.height))
            .is_err()
    {
        return false;
    }
    !value.maximized || window.maximize().is_ok()
}

#[cfg(windows)]
fn apply_windows_identity(window: &WebviewWindow) {
    use windows::core::HSTRING;
    use windows::Win32::Graphics::Dwm::{DwmSetWindowAttribute, DWMWA_WINDOW_CORNER_PREFERENCE};
    use windows::Win32::UI::Shell::SetCurrentProcessExplicitAppUserModelID;
    let _ = unsafe { SetCurrentProcessExplicitAppUserModelID(&HSTRING::from("SmartiAI.Desktop")) };
    if let Ok(hwnd) = window.hwnd() {
        let preference: u32 = 2;
        let _ = unsafe {
            DwmSetWindowAttribute(
                hwnd,
                DWMWA_WINDOW_CORNER_PREFERENCE,
                (&preference as *const u32).cast(),
                std::mem::size_of::<u32>() as u32,
            )
        };
    }
}

#[cfg(not(windows))]
fn apply_windows_identity(_window: &WebviewWindow) {}

pub fn setup(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let window = app
        .get_webview_window("main")
        .ok_or("main window missing")?;
    apply_windows_identity(&window);
    let app_for_window = app.clone();
    window.on_window_event(move |event| match event {
        WindowEvent::Moved(_) | WindowEvent::Resized(_) => {
            if app_for_window
                .state::<DesktopState>()
                .workspace_ready
                .load(Ordering::Acquire)
            {
                if let Some(window) = app_for_window.get_webview_window("main") {
                    save_placement(&app_for_window, &window);
                }
            }
        }
        WindowEvent::CloseRequested { api, .. }
            if !app_for_window
                .state::<DesktopState>()
                .quitting
                .load(Ordering::Acquire)
                && app_for_window
                    .state::<DesktopState>()
                    .close_to_tray
                    .load(Ordering::Acquire) =>
        {
            api.prevent_close();
            if let Some(window) = app_for_window.get_webview_window("main") {
                let _ = window.hide();
            }
            let _ = app_for_window.emit("desktop://hidden-to-tray", ());
        }
        _ => {}
    });

    let show = MenuItem::with_id(app, "show", "פתיחת SmartiAI", true, None::<&str>)?;
    let new_chat = MenuItem::with_id(app, "new-chat", "שיחה חדשה", true, None::<&str>)?;
    let voice = MenuItem::with_id(app, "voice", "קלט קולי", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "יציאה מלאה", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &new_chat, &voice, &quit])?;
    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or("application icon missing")?;
    TrayIconBuilder::new()
        .icon(icon)
        .tooltip("SmartiAI")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "quit" => {
                app.state::<DesktopState>()
                    .quitting
                    .store(true, Ordering::Release);
                app.exit(0);
            }
            "new-chat" | "voice" | "show" => show_main(
                app,
                DesktopActivation {
                    command: event.id().as_ref().to_string(),
                    session_id: String::new(),
                    run_id: None,
                    arguments: vec![],
                },
            ),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } | TrayIconEvent::DoubleClick {
                    button: MouseButton::Left,
                    ..
                }
            ) {
                show_main(
                    tray.app_handle(),
                    DesktopActivation {
                        command: "show".into(),
                        session_id: String::new(),
                        run_id: None,
                        arguments: vec![],
                    },
                );
            }
        })
        .build(app)?;
    Ok(())
}

#[tauri::command]
pub fn desktop_finish_startup(app: AppHandle) -> Result<(), String> {
    let state = app.state::<DesktopState>();
    if state.workspace_ready.load(Ordering::Acquire) {
        return Ok(());
    }
    let window = app
        .get_webview_window("main")
        .ok_or("main window missing")?;
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| window.primary_monitor().ok().flatten());
    let (width, height) = monitor
        .as_ref()
        .map(|monitor| {
            let scale = monitor.scale_factor().max(0.5);
            let size = monitor.work_area().size;
            workspace_default_size(size.width as f64 / scale, size.height as f64 / scale)
        })
        .unwrap_or((1180.0, 760.0));
    window
        .set_min_size(Some(LogicalSize::new(width.min(720.0), height.min(560.0))))
        .map_err(|error| error.to_string())?;
    window
        .set_resizable(true)
        .map_err(|error| error.to_string())?;
    if !restore_placement(&app, &window) {
        window.unmaximize().map_err(|error| error.to_string())?;
        window
            .set_size(LogicalSize::new(width, height))
            .map_err(|error| error.to_string())?;
        if let Some(monitor) = monitor {
            let area = monitor.work_area();
            let scale = monitor.scale_factor().max(0.5);
            window
                .set_position(PhysicalPosition::new(
                    area.position.x
                        + ((area.size.width as f64 - width * scale) / 2.0).round() as i32,
                    area.position.y
                        + ((area.size.height as f64 - height * scale) / 2.0).round() as i32,
                ))
                .map_err(|error| error.to_string())?;
        } else {
            window.center().map_err(|error| error.to_string())?;
        }
    }
    state.workspace_ready.store(true, Ordering::Release);
    save_placement(&app, &window);
    Ok(())
}

fn workspace_default_size(available_width: f64, available_height: f64) -> (f64, f64) {
    (
        (available_width * 0.84)
            .round()
            .max(720.0)
            .min((available_width - 32.0).max(1.0)),
        (available_height * 0.8)
            .round()
            .max(560.0)
            .min((available_height - 32.0).max(1.0)),
    )
}

fn voice_overlay_position(main: &WebviewWindow, width: f64) -> LogicalPosition<f64> {
    let scale = main.scale_factor().unwrap_or(1.0).max(0.5);
    let position = main.outer_position().unwrap_or(PhysicalPosition::new(0, 0));
    let size = main.outer_size().unwrap_or(PhysicalSize::new(980, 680));
    let main_x = position.x as f64 / scale;
    let main_y = position.y as f64 / scale;
    let main_width = size.width as f64 / scale;
    let mut y = main_y - 82.0;
    if y < 8.0 {
        y = main_y + 12.0;
    }
    LogicalPosition::new((main_x + (main_width - width) / 2.0).max(8.0), y.max(8.0))
}

#[tauri::command]
pub fn desktop_show_voice_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("voice-overlay") {
        window.show().map_err(|error| error.to_string())?;
        return Ok(());
    }
    create_voice_overlay(&app, true).map(|_| ())
}

pub(crate) fn create_voice_overlay(app: &AppHandle, show: bool) -> Result<WebviewWindow, String> {
    let main = app
        .get_webview_window("main")
        .ok_or("main window missing")?;
    let main_foreground = main.is_visible().unwrap_or(false)
        && !main.is_minimized().unwrap_or(false)
        && main.is_focused().unwrap_or(false);
    let expanded = !main_foreground;
    let width = voice_overlay_width(main_foreground);
    let url = WebviewUrl::App(
        format!("index.html?voice-overlay=1&expanded={}", u8::from(expanded)).into(),
    );
    let overlay = WebviewWindowBuilder::new(app, "voice-overlay", url)
        .title("SmartiAI Voice")
        .inner_size(width, 70.0)
        .min_inner_size(width, 70.0)
        .max_inner_size(width, 70.0)
        .resizable(false)
        .decorations(false)
        .transparent(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .focused(false)
        .visible(false)
        .build()
        .map_err(|error| error.to_string())?;
    overlay
        .set_position(voice_overlay_position(&main, width))
        .map_err(|error| error.to_string())?;
    if show {
        overlay.show().map_err(|error| error.to_string())?;
    }
    Ok(overlay)
}

fn voice_overlay_width(main_foreground: bool) -> f64 {
    if main_foreground {
        298.0
    } else {
        342.0
    }
}

#[tauri::command]
pub fn desktop_hide_voice_overlay(app: AppHandle) {
    if let Some(window) = app.get_webview_window("voice-overlay") {
        let _ = window.close();
    }
}

#[tauri::command]
pub fn desktop_focus_main(app: AppHandle) -> Result<(), String> {
    let main = app
        .get_webview_window("main")
        .ok_or("main window missing")?;
    main.show().map_err(|error| error.to_string())?;
    main.unminimize().map_err(|error| error.to_string())?;
    main.set_focus().map_err(|error| error.to_string())
}

#[tauri::command]
pub fn desktop_set_voice_hotkey(app: AppHandle, shortcut: String) -> Result<(), String> {
    app.global_shortcut()
        .unregister_all()
        .map_err(|error| error.to_string())?;
    let value = shortcut.trim();
    if value.is_empty() {
        return Ok(());
    }
    app.global_shortcut()
        .on_shortcut(value, |app, _shortcut, event| {
            if event.state == ShortcutState::Pressed {
                show_main(
                    app,
                    DesktopActivation {
                        command: "voice".into(),
                        session_id: String::new(),
                        run_id: None,
                        arguments: vec![],
                    },
                );
            }
        })
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn desktop_set_close_to_tray(app: AppHandle, enabled: bool) {
    app.state::<DesktopState>()
        .close_to_tray
        .store(enabled, Ordering::Release);
}

#[tauri::command]
pub fn desktop_notify(
    app: AppHandle,
    title: String,
    body: String,
    session_id: String,
    run_id: Option<String>,
) -> Result<(), String> {
    let title: String = title.chars().take(160).collect();
    let body: String = body.chars().take(1000).collect();
    #[cfg(windows)]
    {
        let activation_app = app.clone();
        let activation_session = session_id.clone();
        let activation_run = run_id.clone();
        tauri_winrt_notification::Toast::new("SmartiAI.Desktop")
            .title(&title)
            .text1(&body)
            .add_button("פתח את השיחה", "open")
            .on_activated(move |_action| {
                show_main(
                    &activation_app,
                    DesktopActivation {
                        command: "notification".into(),
                        session_id: activation_session.clone(),
                        run_id: activation_run.clone(),
                        arguments: vec![],
                    },
                );
                Ok(())
            })
            .show()
            .map_err(|error| error.to_string())?;
    }
    #[cfg(not(windows))]
    app.notification()
        .builder()
        .title(title)
        .body(body)
        .show()
        .map_err(|error| error.to_string())?;
    // The session remains pending until an explicit activation/read command;
    // displaying a toast never acknowledges unrelated attention items.
    let _ = app.emit(
        "desktop://notification-created",
        DesktopActivation {
            command: "notification".into(),
            session_id,
            run_id,
            arguments: vec![],
        },
    );
    Ok(())
}

#[tauri::command]
pub fn desktop_set_unread(app: AppHandle, count: u32) -> Result<(), String> {
    let state = app.state::<DesktopState>();
    if state.unread_count.load(Ordering::Acquire) == count {
        return Ok(());
    }
    let window = app
        .get_webview_window("main")
        .ok_or("main window missing")?;
    let taskbar_title = if count == 0 {
        "SmartiAI".to_string()
    } else {
        format!("SmartiAI ({count})")
    };
    window
        .set_title(&taskbar_title)
        .map_err(|error| error.to_string())?;
    let badge = if count > 0 { Some(crate::taskbar_badge::unread_badge(count)?) } else { None };
    window
        .set_overlay_icon(badge)
        .map_err(|error| error.to_string())?;
    #[cfg(windows)]
    if count == 0 || !window.is_focused().unwrap_or(false) {
        use windows::Win32::UI::WindowsAndMessaging::{
            FlashWindowEx, FLASHWINFO, FLASHW_ALL, FLASHW_STOP, FLASHW_TIMERNOFG,
        };
        if let Ok(hwnd) = window.hwnd() {
            let info = FLASHWINFO {
                cbSize: std::mem::size_of::<FLASHWINFO>() as u32,
                hwnd,
                dwFlags: if count == 0 { FLASHW_STOP } else { FLASHW_ALL | FLASHW_TIMERNOFG },
                uCount: 3,
                dwTimeout: 0,
            };
            let _ = unsafe { FlashWindowEx(&info) };
        }
    }
    state.unread_count.store(count, Ordering::Release);
    let _ = app.emit("desktop://unread", count);
    Ok(())
}

#[tauri::command]
pub fn desktop_quit(app: AppHandle) {
    app.state::<DesktopState>()
        .quitting
        .store(true, Ordering::Release);
    app.exit(0);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn second_launch_arguments_route_one_scoped_command() {
        let activation = activation_from_args(vec![
            "smarti.exe".into(),
            "--voice".into(),
            "--session=chat-42".into(),
        ]);
        assert_eq!(activation.command, "voice");
        assert_eq!(activation.session_id, "chat-42");
    }

    #[test]
    fn unknown_second_launch_defaults_to_show() {
        assert_eq!(
            activation_from_args(vec!["smarti.exe".into()]).command,
            "show"
        );
    }

    #[test]
    fn workspace_default_scales_with_available_work_area() {
        assert_eq!(workspace_default_size(1920.0, 1040.0), (1613.0, 832.0));
        assert_eq!(workspace_default_size(2560.0, 1400.0), (2150.0, 1120.0));
        // A 4K work area at 200% DPI has the same logical size as Full HD.
        assert_eq!(
            workspace_default_size(3840.0 / 2.0, 2080.0 / 2.0),
            (1613.0, 832.0)
        );
        assert_eq!(workspace_default_size(1024.0, 728.0), (860.0, 582.0));
        assert_eq!(workspace_default_size(800.0, 600.0), (720.0, 560.0));
        assert_eq!(workspace_default_size(640.0, 480.0), (608.0, 448.0));
    }

    #[test]
    fn old_placements_reset_once_and_new_user_sizes_remain_restorable() {
        let mut placement: WindowPlacement =
            serde_json::from_str(r#"{"x":100,"y":100,"width":720,"height":560,"maximized":false}"#)
                .unwrap();
        assert!(!placement.can_restore());
        placement.layout_version = WINDOW_LAYOUT_VERSION;
        let saved = serde_json::to_vec(&placement).unwrap();
        let restored: WindowPlacement = serde_json::from_slice(&saved).unwrap();
        assert!(restored.can_restore());
        assert_eq!((restored.width, restored.height), (720, 560));
    }

    #[test]
    fn legacy_voice_window_sizes_are_exact() {
        assert_eq!(voice_overlay_width(true), 298.0);
        assert_eq!(voice_overlay_width(false), 342.0);
    }

    #[test]
    fn rtl_native_menu_rejects_duplicate_action_ids() {
        let items = vec![
            RtlMenuItem {
                id: Some("same".into()),
                text: Some("ראשון".into()),
                enabled: Some(true),
                separator: None,
                accelerator: None,
            },
            RtlMenuItem {
                id: Some("same".into()),
                text: Some("שני".into()),
                enabled: Some(true),
                separator: None,
                accelerator: None,
            },
        ];
        assert!(validate_rtl_menu_items(&items).is_err());
    }
}
