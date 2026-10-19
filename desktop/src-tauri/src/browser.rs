use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::time::Duration;
use std::time::Instant;
use tauri::{
    webview::{DownloadEvent, PageLoadEvent},
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, Rect, Webview, WebviewBuilder,
    WebviewUrl,
};

pub mod agent;

const CDP_TIMEOUT: Duration = Duration::from_secs(12);
const DEFAULT_URL: &str = "https://www.google.com/?hl=he";

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum BrowserProfile {
    Persistent,
    Guest,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct BrowserBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

impl BrowserBounds {
    fn validate(&self) -> Result<(), String> {
        if !self.x.is_finite()
            || !self.y.is_finite()
            || !self.width.is_finite()
            || !self.height.is_finite()
            // The native child slides off the left edge with the Workbench.
            // Keep coordinates bounded, but do not clamp a valid translation:
            // clamping/resizing here makes the page unfold in reverse.
            || self.x.abs() > 32_768.0
            || self.y < 0.0
            || self.y > 32_768.0
            || self.width < 1.0
            || self.height < 1.0
            || self.width > 16_384.0
            || self.height > 16_384.0
        {
            return Err("invalid browser bounds".into());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BrowserTab {
    pub tab_id: String,
    pub workspace_id: String,
    pub target_id: String,
    pub webview_label: String,
    pub profile: BrowserProfile,
    pub url: String,
    pub title: String,
    pub loading: bool,
    pub active: bool,
    pub crashed: bool,
    pub pinned: bool,
    pub favicon_url: String,
    pub audio_playing: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BrowserSnapshot {
    pub tabs: Vec<BrowserTab>,
    pub active_tab_id: Option<String>,
    pub transport: &'static str,
    pub remote_debugging_port: Option<u16>,
    pub agent: Option<agent::Activity>,
    pub agents: Vec<agent::Activity>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BrowserAction {
    pub request_id: String,
    pub tab_id: String,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BrowserActionResult {
    pub request_id: String,
    pub tab_id: String,
    pub target_id: String,
    pub method: String,
    pub result: Value,
}

struct BrowserInner {
    next_tab: u64,
    tabs: HashMap<String, BrowserTab>,
    tab_order: Vec<String>,
    recently_closed: Vec<(BrowserProfile, String, String)>,
    active_tab_id: Option<String>,
    bounds: BrowserBounds,
    surface_visible: bool,
    persistent_dir: PathBuf,
    guest_root: PathBuf,
}

#[derive(Clone)]
pub struct BrowserBroker {
    inner: Arc<Mutex<BrowserInner>>,
    bridge_stop: Arc<AtomicBool>,
    agent: Arc<agent::AgentState>,
}

pub struct BrowserBridgeEndpoint {
    pub port: u16,
    pub token: String,
}

impl BrowserBroker {
    fn surface_bounds(&self) -> Result<(BrowserBounds, bool), String> {
        let inner = self.inner.lock().map_err(|_| "browser broker mutex poisoned".to_string())?;
        Ok((presentation_bounds(&inner.bounds, inner.surface_visible), inner.surface_visible))
    }

    pub fn new(app_data_dir: PathBuf, cache_dir: PathBuf) -> Self {
        Self {
            inner: Arc::new(Mutex::new(BrowserInner {
                next_tab: 1,
                tabs: HashMap::new(),
                tab_order: Vec::new(),
                recently_closed: Vec::new(),
                active_tab_id: None,
                surface_visible: false,
                bounds: BrowserBounds {
                    x: 0.0,
                    y: 132.0,
                    width: 980.0,
                    height: 548.0,
                },
                persistent_dir: app_data_dir.join("browser").join("persistent-webview2"),
                guest_root: cache_dir.join(format!("browser-guest-{}", std::process::id())),
            })),
            bridge_stop: Arc::new(AtomicBool::new(false)),
            agent: Arc::new(agent::AgentState::default()),
        }
    }

    pub(crate) fn snapshot(&self) -> BrowserSnapshot {
        let inner = self.inner.lock().expect("browser broker mutex poisoned");
        let tabs = inner
            .tab_order
            .iter()
            .filter_map(|id| inner.tabs.get(id).cloned())
            .collect::<Vec<_>>();
        BrowserSnapshot {
            tabs,
            active_tab_id: inner.active_tab_id.clone(),
            transport: "webview2-in-process-cdp",
            remote_debugging_port: None,
            agent: self.agent.activity(),
            agents: self.agent.activities(),
        }
    }

    fn tab(&self, tab_id: &str) -> Result<BrowserTab, String> {
        self.inner
            .lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?
            .tabs
            .values().find(|tab| tab.tab_id == tab_id || tab.target_id == tab_id)
            .cloned()
            .ok_or_else(|| "browser tab not found".into())
    }

    fn update_page(&self, tab_id: &str, url: String, loading: bool) {
        if let Ok(mut inner) = self.inner.lock() {
            if let Some(tab) = inner.tabs.get_mut(tab_id) {
                tab.url = url;
                tab.loading = loading;
                tab.crashed = false;
            }
        }
    }

    fn update_title(&self, tab_id: &str, title: String) {
        if let Ok(mut inner) = self.inner.lock() {
            if let Some(tab) = inner.tabs.get_mut(tab_id) {
                tab.title = if title.trim().is_empty() {
                    "כרטיסייה חדשה".into()
                } else {
                    title
                };
            }
        }
    }

    fn update_metadata(&self, tab_id: &str, favicon_url: String, audio_playing: bool) {
        if let Ok(mut inner) = self.inner.lock() {
            if let Some(tab) = inner.tabs.get_mut(tab_id) {
                tab.favicon_url = favicon_url;
                tab.audio_playing = audio_playing;
            }
        }
    }

    fn mark_crashed(&self, tab_id: &str) {
        if let Ok(mut inner) = self.inner.lock() {
            if let Some(tab) = inner.tabs.get_mut(tab_id) {
                tab.crashed = true;
                tab.loading = false;
            }
        }
    }

    fn allocate_tab(
        &self,
        profile: BrowserProfile,
        url: String,
        workspace_id: Option<String>,
    ) -> Result<(BrowserTab, BrowserBounds, PathBuf), String> {
        let mut inner = self
            .inner
            .lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?;
        let ordinal = inner.next_tab;
        inner.next_tab += 1;
        let workspace_id = workspace_id.unwrap_or_else(|| {
            inner.active_tab_id.as_ref()
                .and_then(|id| inner.tabs.get(id))
                .map(|tab| tab.workspace_id.clone())
                .unwrap_or_default()
        });
        for tab in inner.tabs.values_mut() {
            tab.active = false;
        }
        let tab_id = format!("tab-{ordinal:08}");
        let tab = BrowserTab {
            tab_id: tab_id.clone(),
            workspace_id,
            target_id: format!("wv2-target-{ordinal:08}"),
            webview_label: format!("browser-{ordinal:08}"),
            profile,
            url,
            title: "כרטיסייה חדשה".into(),
            loading: true,
            active: true,
            crashed: false,
            pinned: false,
            favicon_url: String::new(),
            audio_playing: false,
        };
        let data_dir = match profile {
            BrowserProfile::Persistent => inner.persistent_dir.clone(),
            BrowserProfile::Guest => inner.guest_root.join(&tab_id),
        };
        let bounds = inner.bounds.clone();
        inner.active_tab_id = Some(tab_id.clone());
        inner.tab_order.push(tab_id.clone());
        inner.tabs.insert(tab_id, tab.clone());
        Ok((tab, bounds, data_dir))
    }

    fn rollback_tab(&self, tab_id: &str) {
        if let Ok(mut inner) = self.inner.lock() {
            inner.tabs.remove(tab_id);
            inner.tab_order.retain(|id| id != tab_id);
            inner.active_tab_id = inner.tab_order.last().cloned();
            let active = inner.active_tab_id.clone();
            for tab in inner.tabs.values_mut() {
                tab.active = Some(&tab.tab_id) == active.as_ref();
            }
        }
    }

    pub fn shutdown(&self) {
        self.bridge_stop.store(true, Ordering::Release);
        self.cleanup_guest();
    }

    pub fn cleanup_guest(&self) {
        let guest_root = self.inner.lock().ok().map(|inner| inner.guest_root.clone());
        if let Some(path) = guest_root {
            if path
                .file_name()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.starts_with("browser-guest-"))
            {
                let _ = std::fs::remove_dir_all(path);
            }
        }
    }
}

fn js_string(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".into())
}

fn cdp_for_tab(
    app: &AppHandle,
    tab: &BrowserTab,
    method: &str,
    params: Value,
) -> Result<Value, String> {
    let webview = app
        .get_webview(&tab.webview_label)
        .ok_or("visible browser target is unavailable")?;
    cdp_call(&webview, method.to_string(), params.to_string())
}

fn structured_action(app: &AppHandle, broker: &BrowserBroker, payload: Value) -> Result<Value, String> {
    agent::run(app, broker, payload)
}

fn read_http_request(stream: &mut TcpStream) -> Result<(String, Value), String> {
    // Windows accepted sockets inherit the listener's nonblocking mode. HTTP
    // headers/body often arrive in separate packets; WouldBlock is not EOF.
    stream.set_nonblocking(false).map_err(|error|error.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| error.to_string())?;
    let mut buffer = Vec::with_capacity(8192);
    let mut chunk = [0u8; 4096];
    let header_end;
    loop {
        let read = stream.read(&mut chunk).map_err(|error| error.to_string())?;
        if read == 0 {
            return Err("browser bridge request ended early".into());
        }
        buffer.extend_from_slice(&chunk[..read]);
        if let Some(index) = buffer.windows(4).position(|part| part == b"\r\n\r\n") {
            header_end = index + 4;
            break;
        }
        if buffer.len() > 64 * 1024 {
            return Err("browser bridge headers too large".into());
        }
    }
    let headers = String::from_utf8_lossy(&buffer[..header_end]);
    if headers.lines().next() != Some("POST /v1/action HTTP/1.1") {
        return Err("unsupported browser bridge route".into());
    }
    let token = headers
        .lines()
        .find_map(|line| line.strip_prefix("Authorization: Bearer "))
        .unwrap_or("")
        .trim()
        .to_string();
    let content_length = headers
        .lines()
        .find_map(|line| {
            let (name, value) = line.split_once(':')?;
            name.eq_ignore_ascii_case("content-length")
                .then(|| value.trim().parse::<usize>().ok())
                .flatten()
        })
        .unwrap_or(0);
    if content_length > 2 * 1024 * 1024 {
        return Err("browser bridge body too large".into());
    }
    while buffer.len() < header_end + content_length {
        let read = stream.read(&mut chunk).map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        buffer.extend_from_slice(&chunk[..read]);
    }
    let body = buffer
        .get(header_end..header_end + content_length)
        .ok_or("incomplete browser bridge body")?;
    let payload = serde_json::from_slice(body).map_err(|error| error.to_string())?;
    Ok((token, payload))
}

fn serve_bridge_connection(
    mut stream: TcpStream,
    app: &AppHandle,
    broker: &BrowserBroker,
    expected_token: &str,
) {
    let response = match read_http_request(&mut stream) {
        Ok((token, payload)) if token == expected_token => {
            structured_action(app, broker, payload).map_err(|error| error.to_string())
        }
        Ok(_) => Err("unauthorized browser bridge request".into()),
        Err(error) => Err(error),
    };
    let ok = response.is_ok();
    let body = serde_json::to_vec(&match response {
        Ok(value) => value,
        Err(error) => json!({"ok":false,"error":error}),
    })
    .unwrap_or_default();
    let status = if ok { "200 OK" } else { "400 Bad Request" };
    let _ = write!(stream, "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len());
    let _ = stream.write_all(&body);
}

pub fn start_core_bridge(
    app: AppHandle,
    broker: BrowserBroker,
) -> Result<BrowserBridgeEndpoint, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    listener
        .set_nonblocking(true)
        .map_err(|error| error.to_string())?;
    let port = listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port();
    let token = super::launch_token();
    let thread_token = token.clone();
    let stop = broker.bridge_stop.clone();
    std::thread::Builder::new()
        .name("smarti-browser-core-bridge".into())
        .spawn(move || {
            while !stop.load(Ordering::Acquire) {
                match listener.accept() {
                    Ok((stream, address)) if address.ip().is_loopback() => {
                        let connection_app=app.clone(); let connection_broker=broker.clone(); let connection_token=thread_token.clone();
                        std::thread::spawn(move || serve_bridge_connection(stream, &connection_app, &connection_broker, &connection_token));
                    }
                    Ok(_) => {}
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(Duration::from_millis(25))
                    }
                    Err(_) => break,
                }
            }
        })
        .map_err(|error| error.to_string())?;
    Ok(BrowserBridgeEndpoint { port, token })
}

fn start_smoke_site() -> Result<(u16, Arc<AtomicBool>), String> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    listener
        .set_nonblocking(true)
        .map_err(|error| error.to_string())?;
    let port = listener
        .local_addr()
        .map_err(|error| error.to_string())?
        .port();
    let stop = Arc::new(AtomicBool::new(false));
    let thread_stop = stop.clone();
    std::thread::spawn(move || {
        let html = r#"<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><title>בדיקת Smarti Browser</title><body><h1>עמוד בדיקה מבודד</h1><label>טקסט בעברית <input id="hebrew" autocomplete="off"></label><button id="popup" onclick="window.open('/popup','_blank')">חלון חדש</button><a id="download" download="smarti-safe.txt" href="data:text/plain,Smarti%20safe%20download">הורדה בטוחה</a><output id="authority">checking</output><script>(async()=>{let state='blocked:no-internals';try{if(window.__TAURI_INTERNALS__){await window.__TAURI_INTERNALS__.invoke('core_status');state='LEAKED';}}catch(e){state='blocked:capability';}document.querySelector('#authority').value=state;document.body.dataset.authority=state;})();</script></body></html>"#;
        while !thread_stop.load(Ordering::Acquire) {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let mut discard = [0u8; 2048];
                    let read = stream.read(&mut discard).unwrap_or(0);
                    let request=String::from_utf8_lossy(&discard[..read]);
                    let body = if request.starts_with("GET /fixture.txt ") {b"bridge download fixture".as_slice()}
                        else if request.starts_with("GET /agent ") {include_str!("browser/fixture.html").as_bytes()}
                        else if request.starts_with("GET /frame ") {b"<!doctype html><button aria-label='frame action'>Frame</button>".as_slice()}
                        else {html.as_bytes()};
                    let _ = write!(stream, "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Security-Policy: default-src 'self' data: 'unsafe-inline'\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", body.len());
                    let _ = stream.write_all(body);
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(20))
                }
                Err(_) => break,
            }
        }
    });
    Ok((port, stop))
}

fn runtime_value(result: &Value) -> Option<&Value> {
    result.pointer("/result/result/value").or_else(|| result.get("result"))
}

pub fn run_foundation_smoke(app: AppHandle, broker: BrowserBroker, result_path: PathBuf) {
    std::thread::Builder::new().name("smarti-browser-foundation-smoke".into()).spawn(move || {
        let result = (|| -> Result<Value, String> {
            let (site_port, site_stop) = start_smoke_site()?;
            let url = format!("http://127.0.0.1:{site_port}/");
            let started = Instant::now();
            let persistent = create_webview(&app, &broker, BrowserProfile::Persistent, &url, None)?;
            let first_tab = persistent.tabs.into_iter().find(|tab| tab.active).ok_or("persistent smoke tab missing")?;
            std::thread::sleep(Duration::from_secs(2));
            let first_tab_ms = started.elapsed().as_millis();

            let snapshot = structured_action(&app, &broker, json!({"action":"snapshot","tabId":first_tab.tab_id}))?;
            let snapshot_value = runtime_value(&snapshot).cloned().unwrap_or(Value::Null);
            let typed = cdp_for_tab(&app, &first_tab, "Runtime.evaluate", json!({
                "expression":"(() => { const el=document.querySelector('#hebrew'); el.focus(); el.value='שלום מטאורי'; el.dispatchEvent(new Event('input',{bubbles:true})); return el.value; })()",
                "returnByValue":true
            }))?;
            let authority = cdp_for_tab(&app, &first_tab, "Runtime.evaluate", json!({"expression":"document.body.dataset.authority || 'pending'","returnByValue":true}))?;
            cdp_for_tab(&app, &first_tab, "Runtime.evaluate", json!({"expression":"localStorage.setItem('smarti-point6','persistent-ok')","returnByValue":true}))?;
            let webview = app.get_webview(&first_tab.webview_label).ok_or("persistent WebView missing")?;
            webview.reload().map_err(|error| error.to_string())?;
            std::thread::sleep(Duration::from_secs(1));
            let persistent_storage = cdp_for_tab(&app, &first_tab, "Runtime.evaluate", json!({"expression":"localStorage.getItem('smarti-point6')","returnByValue":true}))?;

            let guest_snapshot = create_webview(&app, &broker, BrowserProfile::Guest, &url, None)?;
            let guest = guest_snapshot.tabs.into_iter().find(|tab| tab.active).ok_or("guest smoke tab missing")?;
            std::thread::sleep(Duration::from_secs(1));
            let guest_initial = cdp_for_tab(&app, &guest, "Runtime.evaluate", json!({"expression":"localStorage.getItem('smarti-point6')","returnByValue":true}))?;
            cdp_for_tab(&app, &guest, "Runtime.evaluate", json!({"expression":"localStorage.setItem('smarti-point6','guest-only')","returnByValue":true}))?;
            let guest_view = app.get_webview(&guest.webview_label).ok_or("guest WebView missing")?;
            guest_view.clear_all_browsing_data().map_err(|error| error.to_string())?;
            guest_view.close().map_err(|error| error.to_string())?;
            broker.rollback_tab(&guest.tab_id);
            let _ = std::fs::remove_dir_all(broker.inner.lock().map_err(|_| "browser broker mutex poisoned".to_string())?.guest_root.join(&guest.tab_id));

            let guest_two_snapshot = create_webview(&app, &broker, BrowserProfile::Guest, &url, None)?;
            let guest_two = guest_two_snapshot.tabs.into_iter().find(|tab| tab.active).ok_or("second guest smoke tab missing")?;
            std::thread::sleep(Duration::from_secs(1));
            let guest_after_close = cdp_for_tab(&app, &guest_two, "Runtime.evaluate", json!({"expression":"localStorage.getItem('smarti-point6')","returnByValue":true}))?;
            let guest_two_view = app.get_webview(&guest_two.webview_label).ok_or("second guest WebView missing")?;
            guest_two_view.hide().map_err(|error| error.to_string())?;
            guest_two_view.show().map_err(|error| error.to_string())?;
            guest_two_view.set_position(LogicalPosition::new(0.0, 132.0)).map_err(|error| error.to_string())?;
            guest_two_view.set_size(LogicalSize::new(900.0, 500.0)).map_err(|error| error.to_string())?;
            guest_two_view.set_focus().map_err(|error| error.to_string())?;
            let screenshot = cdp_for_tab(&app, &guest_two, "Page.captureScreenshot", json!({"format":"png"}))?;
            let webauthn = cdp_for_tab(&app, &guest_two, "Runtime.evaluate", json!({"expression":"typeof PublicKeyCredential === 'function'","returnByValue":true}))?;
            let tabs_before_popup = broker.snapshot().tabs.len();
            cdp_for_tab(&app, &guest_two, "Runtime.evaluate", json!({"expression":"window.open('/popup','_blank')","returnByValue":true,"userGesture":true}))?;
            let popup_deadline = Instant::now() + Duration::from_secs(5);
            while broker.snapshot().tabs.len() == tabs_before_popup && Instant::now() < popup_deadline {
                std::thread::sleep(Duration::from_millis(100));
            }
            let popup_routed_to_tab = broker.snapshot().tabs.len() == tabs_before_popup + 1;
            let same_target = snapshot.get("targetId") == Some(&Value::String(first_tab.target_id.clone()));
            let authority_value = authority.pointer("/result/value").and_then(Value::as_str).unwrap_or("pending");
            let typed_value = typed.pointer("/result/value").and_then(Value::as_str).unwrap_or("");
            let persistent_value = persistent_storage.pointer("/result/value").and_then(Value::as_str);
            let guest_initial_value = guest_initial.pointer("/result/value").and_then(Value::as_str);
            let guest_after_value = guest_after_close.pointer("/result/value").and_then(Value::as_str);
            let screenshot_bytes = screenshot.get("data").and_then(Value::as_str).map(|value| value.len() * 3 / 4).unwrap_or(0);
            let webauthn_api = webauthn.pointer("/result/value").and_then(Value::as_bool).unwrap_or(false);
            site_stop.store(true, Ordering::Release);
            Ok(json!({
                "ok": same_target && typed_value == "שלום מטאורי" && authority_value.starts_with("blocked") && persistent_value == Some("persistent-ok") && guest_initial_value.is_none() && guest_after_value.is_none() && screenshot_bytes > 1000 && popup_routed_to_tab,
                "transport":"webview2-in-process-cdp",
                "remote_debugging_port":null,
                "same_visible_target":same_target,
                "tab_id":first_tab.tab_id,
                "target_id":first_tab.target_id,
                "snapshot_title":snapshot_value.get("title"),
                "hebrew_input":typed_value,
                "remote_tauri_authority":authority_value,
                "persistent_storage_after_reload":persistent_value,
                "guest_storage_on_first_open":guest_initial_value,
                "guest_storage_after_close":guest_after_value,
                "hide_show_resize_focus":true,
                "screenshot_estimated_bytes":screenshot_bytes,
                "webauthn_api_available":webauthn_api,
                "popup_routed_to_governed_tab":popup_routed_to_tab,
                "first_tab_ms":first_tab_ms,
                "profile_dirs_separate":true
            }))
        })();
        let payload = match result { Ok(value) => value, Err(error) => json!({"ok":false,"error":error}) };
        if let Some(parent) = result_path.parent() { let _ = std::fs::create_dir_all(parent); }
        let _ = std::fs::write(&result_path, serde_json::to_vec_pretty(&payload).unwrap_or_default());
        app.exit(if payload.get("ok").and_then(Value::as_bool) == Some(true) { 0 } else { 1 });
    }).expect("failed to create browser foundation smoke thread");
}

fn normalize_url(input: &str) -> Result<String, String> {
    let input = input.trim();
    if input.is_empty() { return Ok(DEFAULT_URL.into()); }
    if input.eq_ignore_ascii_case("about:blank") { return Ok("about:blank".into()); }
    let candidate = if input.contains("://") {
        input.to_string()
    } else if input.contains('.') && !input.contains(' ') {
        format!("https://{input}")
    } else {
        format!("https://www.google.com/search?q={}", percent_encode(input))
    };
    let parsed = candidate
        .parse::<tauri::Url>()
        .map_err(|_| "invalid browser address".to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("Smarti Browser allows only http/https navigation".into());
    }
    Ok(parsed.to_string())
}

fn percent_encode(value: &str) -> String {
    value
        .bytes()
        .map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                (byte as char).to_string()
            }
            b' ' => "+".into(),
            _ => format!("%{byte:02X}"),
        })
        .collect()
}

fn emit_snapshot(app: &AppHandle, broker: &BrowserBroker) {
    let _ = app.emit("browser://state", broker.snapshot());
}

fn safe_download_destination(app: &AppHandle, url: &tauri::Url) -> Result<PathBuf, String> {
    let directory = app
        .path()
        .download_dir()
        .map_err(|error| error.to_string())?;
    std::fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    let raw = url
        .path_segments()
        .and_then(|mut parts| parts.next_back())
        .filter(|name| !name.is_empty())
        .unwrap_or("download");
    let name = raw
        .chars()
        .map(|character| {
            if matches!(
                character,
                '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*'
            ) || character.is_control()
            {
                '_'
            } else {
                character
            }
        })
        .collect::<String>();
    let path = std::path::Path::new(&name);
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_lowercase();
    if [
        "exe", "msi", "msp", "bat", "cmd", "com", "scr", "ps1", "vbs", "js", "dll",
    ]
    .contains(&extension.as_str())
    {
        return Err("dangerous download type blocked by Smarti".into());
    }
    let stem = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("download");
    let suffix = path
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{value}"))
        .unwrap_or_default();
    for index in 0..10_000u32 {
        let candidate = directory.join(if index == 0 {
            format!("{stem}{suffix}")
        } else {
            format!("{stem} ({index}){suffix}")
        });
        if !candidate.exists() {
            return Ok(candidate);
        }
    }
    Err("download collision limit reached".into())
}

fn validate_cdp_method(method: &str) -> Result<(), String> {
    if matches!(method,"Browser.close"|"Browser.crash"|"Browser.crashGpuProcess") {return Err("browser-wide destructive CDP methods are blocked".into());}
    const ALLOWED_PREFIXES: &[&str] = &[
        "Accessibility.",
        "Browser.",
        "Console.",
        "CSS.",
        "DOM.",
        "DOMSnapshot.",
        "Emulation.",
        "Input.",
        "Log.",
        "Network.",
        "Page.",
        "Runtime.",
        "Storage.",
    ];
    if method.len() > 96
        || !ALLOWED_PREFIXES
            .iter()
            .any(|prefix| method.starts_with(prefix))
    {
        return Err("CDP method is outside the Smarti browser policy surface".into());
    }
    Ok(())
}

#[cfg(windows)]
fn cdp_call(webview: &Webview, method: String, params: String) -> Result<Value, String> {
    use webview2_com::CallDevToolsProtocolMethodCompletedHandler;
    use windows::core::HSTRING;

    validate_cdp_method(&method)?;
    let (sender, receiver) = mpsc::channel::<Result<String, String>>();
    webview
        .with_webview(move |platform| {
            let send_error = sender.clone();
            let result = (|| -> windows::core::Result<()> {
                let controller = platform.controller();
                let core = unsafe { controller.CoreWebView2()? };
                let callback = CallDevToolsProtocolMethodCompletedHandler::create(Box::new(
                    move |status, payload| {
                        let value = status.map(|_| payload).map_err(|error| error.to_string());
                        let _ = sender.send(value);
                        Ok(())
                    },
                ));
                let method = HSTRING::from(method);
                let params = HSTRING::from(params);
                unsafe { core.CallDevToolsProtocolMethod(&method, &params, &callback) }
            })();
            if let Err(error) = result {
                let _ = send_error.send(Err(error.to_string()));
            }
        })
        .map_err(|error| error.to_string())?;
    let payload = receiver.recv_timeout(CDP_TIMEOUT).map_err(|error| match error {
        mpsc::RecvTimeoutError::Timeout => "WebView2 CDP action timed out".to_string(),
        mpsc::RecvTimeoutError::Disconnected => "WebView2 CDP response channel closed before completion; inspect the target before retrying an action".to_string(),
    })??;
    serde_json::from_str(&payload)
        .map_err(|error| format!("invalid WebView2 CDP response: {error}"))
}

#[cfg(not(windows))]
fn cdp_call(_webview: &Webview, _method: String, _params: String) -> Result<Value, String> {
    Err("the Smarti Browser foundation requires WebView2 on Windows".into())
}

fn create_webview(
    app: &AppHandle,
    broker: &BrowserBroker,
    profile: BrowserProfile,
    input: &str,
    workspace_id: Option<String>,
) -> Result<BrowserSnapshot, String> {
    create_webview_with_presentation(app, broker, profile, input, workspace_id, true)
}

fn create_webview_with_presentation(
    app: &AppHandle, broker: &BrowserBroker, profile: BrowserProfile,
    input: &str, workspace_id: Option<String>, activate: bool,
) -> Result<BrowserSnapshot, String> {
    let previous = broker.snapshot().active_tab_id;
    let url = normalize_url(input)?;
    let parsed = url
        .parse::<tauri::Url>()
        .map_err(|error| error.to_string())?;
    let (tab, _, data_dir) = broker.allocate_tab(profile, url, workspace_id)?;
    if !activate {
        let mut inner=broker.inner.lock().map_err(|_|"browser mutex poisoned")?;
        inner.active_tab_id=previous;
        let active=inner.active_tab_id.clone();
        for tab in inner.tabs.values_mut(){tab.active=Some(&tab.tab_id)==active.as_ref();}
    }
    let (mut bounds, _) = broker.surface_bounds()?;
    if !activate { bounds=presentation_bounds(&bounds,false); }
    std::fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;
    let parent = app
        .get_window("main")
        .ok_or("main Tauri window is unavailable")?;
    for existing in parent.webviews() {
        if activate && existing.label().starts_with("browser-") {
            if let Some(tab) = broker.snapshot().tabs.iter().find(|tab|tab.webview_label==existing.label() && broker.agent.running(&tab.tab_id)) {
                let _ = set_webview_bounds(&existing, &presentation_bounds(&bounds, false));
                let _ = existing.show();
                let _ = tab;
            } else {
                let _ = existing.hide();
                let _ = cdp_call(&existing, "Page.setWebLifecycleState".into(), json!({"state":"frozen"}).to_string());
            }
        }
    }

    let load_broker = broker.clone();
    let load_app = app.clone();
    let load_tab = tab.tab_id.clone();
    let title_broker = broker.clone();
    let title_app = app.clone();
    let title_tab = tab.tab_id.clone();
    let popup_app = app.clone();
    let popup_broker = broker.clone();
    let popup_profile = profile;
    let popup_workspace = tab.workspace_id.clone();
    let navigation_broker=broker.clone();
    let navigation_workspace=tab.workspace_id.clone();
    let download_broker=broker.clone();
    let download_tab=tab.tab_id.clone();
    let download_app = app.clone();
    let download_profile = profile;
    let builder = WebviewBuilder::new(&tab.webview_label, WebviewUrl::External(parsed))
        .data_directory(data_dir)
        .incognito(profile == BrowserProfile::Guest)
        .on_navigation(move |url| matches!(url.scheme(), "http" | "https" | "about") && navigation_broker.agent.navigation_allowed(&navigation_workspace,url))
        .on_page_load(move |_webview, payload| {
            load_broker.update_page(
                &load_tab,
                payload.url().to_string(),
                payload.event() == PageLoadEvent::Started,
            );
            emit_snapshot(&load_app, &load_broker);
        })
        .on_document_title_changed(move |_webview, title| {
            title_broker.update_title(&title_tab, title);
            emit_snapshot(&title_app, &title_broker);
        })
        .on_download(move |_webview, event| {
            match &event {
                DownloadEvent::Finished {url,path,success}=>download_broker.agent.record_download(&download_tab,json!({"url":url,"path":path,"success":success})),
                _=>{},
            }
            match event {
                DownloadEvent::Requested { url, destination } => match safe_download_destination(&download_app, &url) {
                    Ok(path) => { *destination = path.clone(); let _ = download_app.emit("browser://download", json!({"phase":"requested","profile":download_profile,"url":url,"name":path.file_name().and_then(|name| name.to_str()).unwrap_or("download")})); true }
                    Err(error) => { let _ = download_app.emit("browser://download", json!({"phase":"blocked","profile":download_profile,"url":url,"error":error})); false }
                },
                DownloadEvent::Finished { url, path, success } => { let _ = download_app.emit("browser://download", json!({"phase":"finished","profile":download_profile,"url":url,"name":path.as_ref().and_then(|value| value.file_name()).and_then(|name| name.to_str()),"success":success})); true }
                _ => true,
            }
        })
        .on_new_window(move |url, _features| {
            let popup_url = url.to_string();
            let event_app = popup_app.clone();
            let create_app = popup_app.clone();
            let create_broker = popup_broker.clone();
            let create_workspace = popup_workspace.clone();
            std::thread::spawn(move || {
                let result = create_webview(&create_app, &create_broker, popup_profile, &popup_url, Some(create_workspace));
                let _ = event_app.emit("browser://popup-opened", json!({"ok":result.is_ok()}));
            });
            tauri::webview::NewWindowResponse::Deny
        });

    let result = parent.add_child(
        builder,
        LogicalPosition::new(bounds.x, bounds.y),
        LogicalSize::new(bounds.width, bounds.height),
    );
    let webview = match result {
        Ok(webview) => webview,
        Err(error) => {
            broker.rollback_tab(&tab.tab_id);
            return Err(error.to_string());
        }
    };
    #[cfg(windows)]
    {
        use webview2_com::ProcessFailedEventHandler;
        let crash_broker = broker.clone();
        let crash_app = app.clone();
        let crash_tab = tab.tab_id.clone();
        webview
            .with_webview(move |platform| {
                let controller = platform.controller();
                if let Ok(core) = unsafe { controller.CoreWebView2() } {
                    let reload_core = core.clone();
                    let handler =
                        ProcessFailedEventHandler::create(Box::new(move |_sender, _args| {
                            crash_broker.mark_crashed(&crash_tab);
                            emit_snapshot(&crash_app, &crash_broker);
                            let _ = unsafe { reload_core.Reload() };
                            Ok(())
                        }));
                    let mut token = 0i64;
                    let _ = unsafe { core.add_ProcessFailed(&handler, &mut token) };
                }
            })
            .map_err(|error| error.to_string())?;
    }
    emit_snapshot(app, broker);
    Ok(broker.snapshot())
}

#[tauri::command]
pub fn browser_status(broker: tauri::State<'_, BrowserBroker>) -> BrowserSnapshot {
    broker.snapshot()
}

#[tauri::command]
pub async fn browser_open(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    profile: BrowserProfile,
    url: String,
    workspace_id: Option<String>,
) -> Result<BrowserSnapshot, String> {
    create_webview(&app, &broker, profile, &url, workspace_id)
}

#[tauri::command]
pub async fn browser_close(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
) -> Result<BrowserSnapshot, String> {
    let tab = broker.tab(&tab_id)?;
    broker.agent.closed(&tab.tab_id);
    if let Some(webview) = app.get_webview(&tab.webview_label) {
        webview.close().map_err(|error| error.to_string())?;
    }
    let (next, guest_path) = {
        let mut inner = broker
            .inner
            .lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?;
        inner.tabs.remove(&tab_id);
        inner.tab_order.retain(|id| id != &tab_id);
        inner.recently_closed.push((tab.profile, tab.url.clone(), tab.workspace_id.clone()));
        if inner.recently_closed.len() > 32 {
            inner.recently_closed.remove(0);
        }
        let next = inner.tab_order.last().cloned();
        inner.active_tab_id = next.clone();
        for item in inner.tabs.values_mut() {
            item.active = Some(&item.tab_id) == next.as_ref();
        }
        let guest = (tab.profile == BrowserProfile::Guest).then(|| inner.guest_root.join(&tab_id));
        (next, guest)
    };
    if let Some(path) = guest_path {
        let _ = std::fs::remove_dir_all(path);
    }
    if let Some(next) = next {
        let next_tab = broker.tab(&next)?;
        if let Some(webview) = app.get_webview(&next_tab.webview_label) {
            let (bounds, visible) = broker.surface_bounds()?;
            set_webview_bounds(&webview, &bounds)?;
            let _ = webview.show();
            let _ = cdp_call(&webview, "Page.setWebLifecycleState".into(), json!({"state":"active"}).to_string());
            if visible { let _ = webview.set_focus(); }
        }
    }
    emit_snapshot(&app, &broker);
    Ok(broker.snapshot())
}

#[tauri::command]
pub async fn browser_duplicate(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
) -> Result<BrowserSnapshot, String> {
    let tab = broker.tab(&tab_id)?;
    create_webview(&app, &broker, tab.profile, &tab.url, Some(tab.workspace_id))
}

#[tauri::command]
pub async fn browser_restore_closed(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    workspace_id: Option<String>,
) -> Result<BrowserSnapshot, String> {
    let closed = {
        let mut inner = broker.inner.lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?;
        if let Some(workspace_id) = workspace_id {
            inner.recently_closed.iter().rposition(|item| item.2 == workspace_id)
                .map(|index| inner.recently_closed.remove(index))
        } else {
            inner.recently_closed.pop()
        }
    };
    let (profile, url, workspace_id) = closed.ok_or("no recently closed browser tab")?;
    create_webview(&app, &broker, profile, &url, Some(workspace_id))
}

#[tauri::command]
pub async fn browser_close_workspace(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    workspace_id: String,
) -> Result<BrowserSnapshot, String> {
    if workspace_id.is_empty() {
        return Err("workspace browser id is required".into());
    }
    let ids = broker.snapshot().tabs.into_iter()
        .filter(|tab| tab.workspace_id == workspace_id)
        .map(|tab| tab.tab_id)
        .collect::<Vec<_>>();
    for tab_id in ids {
        browser_close(app.clone(), broker.clone(), tab_id).await?;
    }
    Ok(broker.snapshot())
}

#[tauri::command]
pub async fn browser_reorder(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
    index: usize,
) -> Result<BrowserSnapshot, String> {
    let mut inner = broker
        .inner
        .lock()
        .map_err(|_| "browser broker mutex poisoned".to_string())?;
    if !inner.tabs.contains_key(&tab_id) {
        return Err("browser tab not found".into());
    }
    inner.tab_order.retain(|id| id != &tab_id);
    let target = index.min(inner.tab_order.len());
    inner.tab_order.insert(target, tab_id);
    drop(inner);
    emit_snapshot(&app, &broker);
    Ok(broker.snapshot())
}

#[tauri::command]
pub async fn browser_pin(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
    pinned: bool,
) -> Result<BrowserSnapshot, String> {
    let mut inner = broker
        .inner
        .lock()
        .map_err(|_| "browser broker mutex poisoned".to_string())?;
    let tab = inner.tabs.get_mut(&tab_id).ok_or("browser tab not found")?;
    tab.pinned = pinned;
    drop(inner);
    emit_snapshot(&app, &broker);
    Ok(broker.snapshot())
}

#[tauri::command]
pub async fn browser_stop(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
) -> Result<(), String> {
    let tab = broker.tab(&tab_id)?;
    let webview = app
        .get_webview(&tab.webview_label)
        .ok_or("browser target is unavailable")?;
    cdp_call(&webview, "Page.stopLoading".into(), "{}".into()).map(|_| ())
}

#[tauri::command]
pub async fn browser_clear_profile(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    profile: BrowserProfile,
) -> Result<BrowserSnapshot, String> {
    let tabs = broker
        .snapshot()
        .tabs
        .into_iter()
        .filter(|tab| tab.profile == profile)
        .collect::<Vec<_>>();
    for tab in tabs {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            webview
                .clear_all_browsing_data()
                .map_err(|error| error.to_string())?;
        }
    }
    if profile == BrowserProfile::Guest {
        browser_clear_guest(app, broker).await
    } else {
        Ok(broker.snapshot())
    }
}

#[tauri::command]
pub async fn browser_activate(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
) -> Result<BrowserSnapshot, String> {
    let selected = broker.tab(&tab_id)?;
    let tabs = broker.snapshot().tabs;
    let (bounds, visible) = broker.surface_bounds()?;
    for tab in tabs {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            if tab.tab_id == tab_id {
                set_webview_bounds(&webview, &bounds)?;
                let _ = cdp_call(
                    &webview,
                    "Page.setWebLifecycleState".into(),
                    json!({"state":"active"}).to_string(),
                );
                webview.show().map_err(|error| error.to_string())?;
                if visible { webview.set_focus().map_err(|error| error.to_string())?; }
            } else if broker.agent.running(&tab.tab_id) {
                set_webview_bounds(&webview, &presentation_bounds(&bounds, false))?;
                webview.show().map_err(|error| error.to_string())?;
            } else {
                let _ = webview.hide();
                let _ = cdp_call(
                    &webview,
                    "Page.setWebLifecycleState".into(),
                    json!({"state":"frozen"}).to_string(),
                );
            }
        }
    }
    {
        let mut inner = broker
            .inner
            .lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?;
        inner.active_tab_id = Some(selected.tab_id.clone());
        for tab in inner.tabs.values_mut() {
            tab.active = tab.tab_id == selected.tab_id;
        }
    }
    emit_snapshot(&app, &broker);
    Ok(broker.snapshot())
}

// WebView2 stops rendering when hidden. Keep only the active page rendering
// outside the client area so its thumbnail stays real without covering chat
// or stealing focus. Preserve viewport size across collapse/expansion.
fn presentation_bounds(bounds: &BrowserBounds, visible: bool) -> BrowserBounds {
    if visible { return bounds.clone(); }
    BrowserBounds { x: -bounds.width - 32.0, y: 0.0, ..bounds.clone() }
}

fn set_webview_bounds(webview: &Webview, bounds: &BrowserBounds) -> Result<(), String> {
    webview
        .set_bounds(Rect {
            position: LogicalPosition::new(bounds.x, bounds.y).into(),
            size: LogicalSize::new(bounds.width, bounds.height).into(),
        })
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn browser_set_bounds(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    bounds: BrowserBounds,
) -> Result<(), String> {
    bounds.validate()?;
    {
        broker
            .inner
            .lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?
            .bounds = bounds.clone();
    }
    // Hidden tabs adopt the latest shared bounds just before they are shown.
    // Resizing them all here makes drag latency grow with the tab count.
    for tab in broker.snapshot().tabs.into_iter().filter(|tab| tab.active) {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            set_webview_bounds(&webview, &broker.surface_bounds()?.0)?;
        }
    }
    Ok(())
}

#[tauri::command]
pub async fn browser_set_visible(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    visible: bool,
) -> Result<(), String> {
    broker.inner.lock().map_err(|_| "browser broker mutex poisoned".to_string())?.surface_visible = visible;
    let snapshot = broker.snapshot();
    for tab in snapshot.tabs {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            if tab.active {
                set_webview_bounds(&webview, &broker.surface_bounds()?.0)?;
                // Visibility/geometry must not wait for a frozen page's CDP
                // response (which can take seconds). Queue the native show first.
                webview.show().map_err(|error| error.to_string())?;
                let _ = cdp_call(
                    &webview,
                    "Page.setWebLifecycleState".into(),
                    json!({"state":"active"}).to_string(),
                );
            } else if broker.agent.running(&tab.tab_id) {
                let bounds=broker.inner.lock().map_err(|_|"browser broker mutex poisoned")?.bounds.clone();
                set_webview_bounds(&webview, &presentation_bounds(&bounds,false))?;
                webview.show().map_err(|error|error.to_string())?;
            } else {
                webview.hide().map_err(|error| error.to_string())?;
                let _ = cdp_call(
                    &webview,
                    "Page.setWebLifecycleState".into(),
                    json!({"state":"frozen"}).to_string(),
                );
            }
        }
    }
    Ok(())
}

#[tauri::command]
pub async fn browser_navigate(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
    url: String,
) -> Result<BrowserSnapshot, String> {
    let tab = broker.tab(&tab_id)?;
    let address = normalize_url(&url)?;
    let parsed = address
        .parse::<tauri::Url>()
        .map_err(|error| error.to_string())?;
    app.get_webview(&tab.webview_label)
        .ok_or("visible browser target is unavailable")?
        .navigate(parsed)
        .map_err(|error| error.to_string())?;
    Ok(broker.snapshot())
}

#[tauri::command]
pub async fn browser_reload(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
) -> Result<(), String> {
    let tab = broker.tab(&tab_id)?;
    app.get_webview(&tab.webview_label)
        .ok_or("browser target is unavailable")?
        .reload()
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn browser_action(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    action: BrowserAction,
) -> Result<BrowserActionResult, String> {
    if action.request_id.len() < 8 || action.request_id.len() > 96 {
        return Err("invalid browser request id".into());
    }
    let tab = broker.tab(&action.tab_id)?;
    let webview = app
        .get_webview(&tab.webview_label)
        .ok_or("visible browser target is unavailable")?;
    let result = cdp_call(&webview, action.method.clone(), action.params.to_string())?;
    Ok(BrowserActionResult {
        request_id: action.request_id,
        tab_id: tab.tab_id,
        target_id: tab.target_id,
        method: action.method,
        result,
    })
}

#[tauri::command]
pub async fn browser_metadata(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
) -> Result<BrowserSnapshot, String> {
    let tab = broker.tab(&tab_id)?;
    let value = cdp_for_tab(
        &app,
        &tab,
        "Runtime.evaluate",
        json!({
            "expression": "(() => ({ favicon: document.querySelector('link[rel~=icon]')?.href || '', audioPlaying: [...document.querySelectorAll('audio,video')].some((media) => !media.paused && !media.ended) }))()",
            "returnByValue": true
        }),
    )?;
    let metadata = value
        .pointer("/result/result/value")
        .or_else(|| value.pointer("/result/value"))
        .unwrap_or(&Value::Null);
    broker.update_metadata(
        &tab_id,
        metadata
            .get("favicon")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        metadata
            .get("audioPlaying")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    );
    emit_snapshot(&app, &broker);
    Ok(broker.snapshot())
}

#[tauri::command]
pub async fn browser_open_devtools(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
    developer_enabled: bool,
) -> Result<(), String> {
    if !developer_enabled {
        return Err("browser developer tools are disabled in Smarti settings".into());
    }
    let tab = broker.tab(&tab_id)?;
    let webview = app
        .get_webview(&tab.webview_label)
        .ok_or("browser target is unavailable")?;
    webview.open_devtools();
    Ok(())
}

#[tauri::command]
pub async fn browser_clear_guest(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
) -> Result<BrowserSnapshot, String> {
    let guests = broker
        .snapshot()
        .tabs
        .into_iter()
        .filter(|tab| tab.profile == BrowserProfile::Guest)
        .collect::<Vec<_>>();
    for tab in guests {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            let _ = webview.clear_all_browsing_data();
            let _ = webview.close();
        }
        broker.rollback_tab(&tab.tab_id);
    }
    broker.cleanup_guest();
    emit_snapshot(&app, &broker);
    Ok(broker.snapshot())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bridge_reads_fragmented_request_from_nonblocking_listener() {
        let listener=TcpListener::bind(("127.0.0.1",0)).unwrap();
        listener.set_nonblocking(true).unwrap();
        let address=listener.local_addr().unwrap();
        let client=std::thread::spawn(move||{
            let mut stream=TcpStream::connect(address).unwrap();
            stream.write_all(b"POST /v1/action HTTP/1.1\r\nAuthorization: Bearer fixture\r\n").unwrap();
            std::thread::sleep(Duration::from_millis(30));
            let body=b"{\"action\":\"doctor\"}";
            write!(stream,"Content-Length: {}\r\n\r\n",body.len()).unwrap();
            std::thread::sleep(Duration::from_millis(30));
            stream.write_all(body).unwrap();
        });
        let mut stream=loop {match listener.accept(){Ok((stream,_))=>break stream,Err(error)if error.kind()==std::io::ErrorKind::WouldBlock=>std::thread::sleep(Duration::from_millis(2)),Err(error)=>panic!("{error}")}};
        let (token,payload)=read_http_request(&mut stream).unwrap();
        assert_eq!(token,"fixture");assert_eq!(payload["action"],"doctor");
        client.join().unwrap();
    }

    #[cfg(all(windows, feature = "native-preview-test"))]
    #[test]
    #[ignore = "requires installed WebView2; runs an isolated hidden native window"]
    fn native_collapsed_preview_updates_and_closes() {
        let root = std::env::temp_dir().join(format!("smarti-preview-test-{:016x}", rand::random::<u64>()));
        let broker = BrowserBroker::new(root.join("data"), root.join("cache"));
        let (sender, receiver) = mpsc::channel();
        let mut context = tauri::generate_context!();
        context.config_mut().identifier = "ai.smarti.preview-regression".into();
        context.config_mut().app.windows.clear();
        let app = tauri::Builder::default().any_thread().manage(broker.clone())
            .setup(move |app| {
                tauri::WindowBuilder::new(app, "main").visible(false).skip_taskbar(true)
                    .inner_size(980.0, 700.0).build()?;
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    let result = (|| -> Result<(usize, usize), String> {
                        let (port, stop) = start_smoke_site()?;
                        let outcome = (|| -> Result<(usize, usize), String> {
                            // The first agent request must work without a tab
                            // already warmed by UI metadata or direct CDP calls.
                            let cold = structured_action(&handle, &broker, json!({
                                "action":"start", "sessionId":"cold-session", "profile":"guest",
                                "url":format!("http://127.0.0.1:{port}/agent"), "presentation":"visible"
                            }))?;
                            if cold["page"]["url"] == "about:blank" || cold["page"]["refs"].as_object().is_none() {
                                return Err(format!("cold browser start did not observe the page: {cold}"));
                            }
                            structured_action(&handle, &broker, json!({"action":"close_tab", "tabId":cold["tabId"], "sessionId":"cold-session"}))?;
                            let state = create_webview(&handle, &broker, BrowserProfile::Guest,
                                &format!("http://127.0.0.1:{port}/"), Some("preview-owner".into()))?;
                            let tab = state.tabs.into_iter().find(|tab| tab.active).ok_or("missing preview target")?;
                            let deadline = Instant::now() + Duration::from_secs(20);
                            loop {
                                let ready = cdp_for_tab(&handle, &tab, "Runtime.evaluate", json!({
                                    "expression":"Boolean(document.querySelector('#hebrew'))", "returnByValue":true
                                }))?;
                                if ready.pointer("/result/value").and_then(Value::as_bool) == Some(true) { break; }
                                if Instant::now() > deadline { return Err("preview page did not load".into()); }
                                std::thread::sleep(Duration::from_millis(100));
                            }
                            // Exercise the production collapse path, with the parent hidden too.
                            tauri::async_runtime::block_on(browser_set_visible(handle.clone(), handle.state::<BrowserBroker>(), false))?;
                            let bounds = broker.surface_bounds()?.0;
                            if bounds.x + bounds.width >= 0.0 { return Err("preview overlaps chat".into()); }
                            let mut images = Vec::new();
                            for color in ["#b32121", "#163caa"] {
                                cdp_for_tab(&handle, &tab, "Runtime.evaluate", json!({
                                    "expression":format!("document.documentElement.style.background='{color}'; document.body.style.background='{color}'; document.body.style.color='white';"),
                                    "returnByValue":true
                                }))?;
                                std::thread::sleep(Duration::from_millis(150));
                                let image = cdp_for_tab(&handle, &tab, "Page.captureScreenshot", json!({
                                    "format":"jpeg", "quality":80, "fromSurface":true, "captureBeyondViewport":false
                                }))?;
                                images.push(image.get("data").and_then(Value::as_str).unwrap_or("").to_string());
                            }
                            if images[0].len() < 1000 || images[0] == images[1] { return Err("collapsed screenshots are empty or do not update".into()); }
                            let call = |payload: Value| -> Result<Value,String> {
                                let mut payload=payload; payload["tabId"]=json!(tab.tab_id); payload["sessionId"]=json!("fixture-session");
                                let action=payload["action"].clone();
                                structured_action(&handle,&broker,payload).map_err(|error|format!("fixture {action}: {error}"))
                            };
                            let initial=call(json!({"action":"start","url":format!("http://127.0.0.1:{port}/agent")}))?;
                            if initial["page"]["url"]=="about:blank" || initial.get("result").is_some() || initial.pointer("/page/refs").and_then(Value::as_object).is_none(){return Err(format!("start did not return one loaded page observation: {initial}"));}
                            call(json!({"action":"wait","selector":"#message"}))?;
                            let page=call(json!({"action":"snapshot","refs":"aria"}))?;
                            if page.to_string().contains("never-return-this"){return Err("password leaked into snapshot".into());}
                            let reference=page["result"]["refs"].as_object().ok_or("missing refs")?.values()
                                .find(|value|value["name"]=="אהבתי").and_then(|value|value["ref"].as_str()).ok_or("missing button ref")?.to_string();
                            call(json!({"action":"click","ref":reference,"snapshotEpoch":page["result"]["snapshotEpoch"]}))?;
                            call(json!({"action":"wait","text":"trusted-success"}))?;
                            call(json!({"action":"fill","selector":"#message","text":"שלום Smarti"}))?;
                            call(json!({"action":"type","selector":"#message","text":"!"}))?;
                            let typed=call(json!({"action":"evaluate","script":"document.body.dataset.typed"}))?;
                            if typed["result"]!="שלום Smarti!"{return Err(format!("trusted typing failed: {typed}"));}
                            if call(json!({"action":"click","role":"button","name":"כפול","timeoutMs":500})).is_ok(){return Err("ambiguous locator silently clicked".into());}
                            call(json!({"action":"check","selector":"#checked","checked":true}))?;
                            call(json!({"action":"select","selector":"#choice","value":"b"}))?;
                            call(json!({"action":"click","selector":"#shadow-button"}))?;
                            call(json!({"action":"click","selector":"#deep"}))?;
                            let frame=call(json!({"action":"frames"}))?;
                            let frame_id=frame.pointer("/result/frameTree/childFrames/0/frame/id").and_then(Value::as_str).ok_or("missing child frame")?;
                            call(json!({"action":"click","frameId":frame_id,"role":"button","name":"frame action"}))?;
                            let id="trusted-once";
                            let once=json!({"action":"click","selector":"#trusted","requestId":id});
                            let first=call(once.clone())?;if call(once)?!=first{return Err("receipt replay differed".into());}
                            if call(json!({"action":"evaluate","script":"throw new Error('intentional')"})).is_ok(){return Err("JS exception reported success".into());}
                            call(json!({"action":"pause","userControl":true}))?;
                            if call(json!({"action":"click","selector":"#trusted"})).is_ok(){return Err("paused target accepted input".into());}
                            if call(json!({"action":"resume"})).is_ok(){return Err("model overrode user's takeover".into());}
                            call(json!({"action":"resume","userControl":true}))?;
                            call(json!({"action":"navigate","url":format!("http://127.0.0.1:{port}/agent")}))?;
                            if call(json!({"action":"click","ref":reference})).is_ok(){return Err("stale document ref accepted".into());}
                            let shot=call(json!({"action":"screenshot","fullPage":true}))?;
                            if shot.pointer("/result/data").and_then(Value::as_str).unwrap_or("").len()<1000{return Err("agent screenshot empty".into());}
                            let console=call(json!({"action":"console"}))?;
                            if !console.to_string().contains("fixture-console"){return Err("native console event missing".into());}
                            let alias=structured_action(&handle,&broker,json!({"action":"snapshot","targetId":tab.target_id,"sessionId":"fixture-session"}))?;
                            if alias["tabId"]!=tab.tab_id{return Err("targetId alias routed to wrong tab".into());}
                            let blank=structured_action(&handle,&broker,json!({"action":"start","sessionId":"second-session","profile":"guest"}))?;
                            if blank.pointer("/page/url").and_then(Value::as_str)!=Some("about:blank"){return Err(format!("start opened a website instead of blank: {blank}"));}
                            if structured_action(&handle,&broker,json!({"action":"click","selector":"#trusted","tabId":tab.tab_id,"sessionId":"second-session"})).is_ok(){return Err("second session stole target".into());}
                            let extra=structured_action(&handle,&broker,json!({"action":"open","newTab":true,"url":"about:blank","sessionId":"fixture-session","profile":"guest"}))?;
                            if structured_action(&handle,&broker,json!({"action":"click","selector":"#trusted","tabId":tab.tab_id,"sessionId":"second-session"})).is_ok(){return Err("opening a new tab lost ownership of the old tab".into());}
                            structured_action(&handle,&broker,json!({"action":"close_tab","tabId":extra["tabId"],"sessionId":"fixture-session"}))?;
                            tauri::async_runtime::block_on(browser_activate(handle.clone(), handle.state::<BrowserBroker>(), blank["tabId"].as_str().ok_or("blank target missing")?.into()))?;
                            tauri::async_runtime::block_on(browser_set_visible(handle.clone(), handle.state::<BrowserBroker>(), false))?;
                            call(json!({"action":"click","selector":"#trusted"}))?;
                            call(json!({"action":"wait","text":"trusted-success"}))?;
                            structured_action(&handle,&broker,json!({"action":"close_tab","tabId":blank["tabId"],"sessionId":"second-session"}))?;
                            call(json!({"action":"click","selector":"#dialog","expectDialog":true,"accept":false}))?;
                            if call(json!({"action":"evaluate","script":"document.body.dataset.dialog"}))?["result"]!="false" {return Err("dialog dismissal did not reach the page".into());}
                            let endpoint=start_core_bridge(handle.clone(),broker.clone())?;
                            let script=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../scripts/verify_native_browser_bridge.py");
                            let output=std::process::Command::new("python").arg(script)
                                .env("SMARTI_TAURI_BROWSER_BROKER_PORT",endpoint.port.to_string())
                                .env("SMARTI_TAURI_BROWSER_BROKER_TOKEN",endpoint.token)
                                .env("SMARTI_TEST_BROWSER_TAB",tab.tab_id.clone()).env("PYTHONUTF8","1").output().map_err(|e|e.to_string())?;
                            if !output.status.success(){return Err(format!("Core bridge regression failed: {}\n{}",String::from_utf8_lossy(&output.stdout),String::from_utf8_lossy(&output.stderr)));}
                            println!("{}",String::from_utf8_lossy(&output.stdout).trim());
                            println!("native agent verified: trusted click/type, password redaction, ambiguity, check/select, shadow DOM, nested scroll, frames, receipts, exceptions, pause and stale refs");
                            tauri::async_runtime::block_on(browser_close(handle.clone(), handle.state::<BrowserBroker>(), tab.tab_id.clone()))?;
                            if !broker.snapshot().tabs.is_empty() || broker.tab(&tab.tab_id).is_ok() { return Err("closed preview target survived".into()); }
                            broker.cleanup_guest();
                            if broker.bridge_stop.load(Ordering::Acquire) {return Err("guest cleanup stopped the bridge".into());}
                            broker.shutdown();
                            Ok((images[0].len(), images[1].len()))
                        })();
                        stop.store(true, Ordering::Release);
                        outcome
                    })();
                    let _ = sender.send(result);
                    handle.exit(0);
                });
                Ok(())
            }).build(context).expect("build hidden WebView2 test app");
        app.run_return(|_, _| {});
        let result = receiver.recv_timeout(Duration::from_secs(1)).expect("native preview result");
        let sizes = result.expect("native preview must render changed page content and close its target");
        println!("collapsed screenshot base64 sizes: {} -> {}", sizes.0, sizes.1);
    }

    #[test]
    fn collapsed_preview_preserves_viewport_and_stays_outside_chat() {
        let bounds = BrowserBounds { x: 14.0, y: 200.0, width: 800.0, height: 600.0 };
        let collapsed = presentation_bounds(&bounds, false);
        assert!(collapsed.x + collapsed.width < 0.0);
        assert_eq!((collapsed.width, collapsed.height), (bounds.width, bounds.height));
        assert!(collapsed.validate().is_ok());
        assert_eq!(presentation_bounds(&bounds, true), bounds);
    }

    #[test]
    fn url_policy_accepts_web_and_searches_plain_text() {
        assert_eq!(
            normalize_url("example.com").unwrap(),
            "https://example.com/"
        );
        assert!(normalize_url("שלום עולם")
            .unwrap()
            .starts_with("https://www.google.com/search?q="));
        assert!(normalize_url("file:///C:/secret.txt").is_err());
    }

    #[test]
    fn cdp_policy_is_narrow_but_covers_structured_actions() {
        for method in [
            "Accessibility.getFullAXTree",
            "Page.navigate",
            "Input.dispatchKeyEvent",
            "Network.getCookies",
            "Runtime.evaluate",
        ] {
            assert!(validate_cdp_method(method).is_ok(), "{method}");
        }
        assert!(validate_cdp_method("SystemInfo.getProcessInfo").is_err());
    }

    #[test]
    fn bounds_allow_offscreen_horizontal_motion_but_reject_resource_abuse() {
        assert!(BrowserBounds {
            x: 0.0,
            y: 0.0,
            width: 10.0,
            height: 10.0
        }
        .validate()
        .is_ok());
        assert!(BrowserBounds {
            x: 0.0,
            y: 100.0,
            width: 900.0,
            height: 600.0
        }
        .validate()
        .is_ok());
        let sliding = BrowserBounds {
            x: -920.0,
            y: 110.0,
            width: 900.0,
            height: 600.0,
        };
        assert!(sliding.validate().is_ok());
        for x in [f64::NAN, f64::INFINITY, -32_769.0, 32_769.0] {
            assert!(BrowserBounds {
                x,
                ..sliding.clone()
            }
            .validate()
            .is_err());
        }
        for y in [-1.0, 32_769.0] {
            assert!(BrowserBounds {
                y,
                ..sliding.clone()
            }
            .validate()
            .is_err());
        }
        for width in [0.0, -1.0, 16_385.0, f64::INFINITY] {
            assert!(BrowserBounds {
                width,
                ..sliding.clone()
            }
            .validate()
            .is_err());
        }
        for height in [0.0, -1.0, 16_385.0, f64::NAN] {
            assert!(BrowserBounds {
                height,
                ..sliding.clone()
            }
            .validate()
            .is_err());
        }
    }

    #[test]
    fn stable_ids_do_not_depend_on_page_index() {
        let temp = std::env::temp_dir().join("smarti-browser-broker-test");
        let broker = BrowserBroker::new(temp.join("data"), temp.join("cache"));
        let (first, _, _) = broker
            .allocate_tab(BrowserProfile::Persistent, DEFAULT_URL.into(), None)
            .unwrap();
        let (second, _, _) = broker
            .allocate_tab(BrowserProfile::Guest, DEFAULT_URL.into(), None)
            .unwrap();
        assert_eq!(first.tab_id, "tab-00000001");
        assert_eq!(first.target_id, "wv2-target-00000001");
        assert_eq!(second.tab_id, "tab-00000002");
        assert_ne!(first.target_id, second.target_id);
    }

    #[test]
    fn workspace_tabs_keep_their_owner_when_opening_more_pages() {
        let temp = std::env::temp_dir().join("smarti-browser-workspace-test");
        let broker = BrowserBroker::new(temp.join("data"), temp.join("cache"));
        let (first, _, _) = broker.allocate_tab(
            BrowserProfile::Persistent, "https://one.test".into(), Some("browser-1".into()),
        ).unwrap();
        let (second, _, _) = broker.allocate_tab(
            BrowserProfile::Persistent, "https://two.test".into(), Some("browser-2".into()),
        ).unwrap();
        let (same_workspace, _, _) = broker.allocate_tab(
            BrowserProfile::Persistent, "https://three.test".into(), None,
        ).unwrap();
        assert_eq!(first.workspace_id, "browser-1");
        assert_eq!(second.workspace_id, "browser-2");
        assert_eq!(same_workspace.workspace_id, "browser-2");
    }

    #[test]
    fn product_tab_order_and_recently_closed_are_bounded() {
        let temp = std::env::temp_dir().join("smarti-browser-product-test");
        let broker = BrowserBroker::new(temp.join("data"), temp.join("cache"));
        let (first, _, _) = broker
            .allocate_tab(BrowserProfile::Persistent, "https://one.test".into(), None)
            .unwrap();
        let (second, _, _) = broker
            .allocate_tab(BrowserProfile::Persistent, "https://two.test".into(), None)
            .unwrap();
        assert_eq!(
            broker
                .snapshot()
                .tabs
                .iter()
                .map(|tab| tab.tab_id.as_str())
                .collect::<Vec<_>>(),
            vec![first.tab_id.as_str(), second.tab_id.as_str()]
        );
        broker.rollback_tab(&first.tab_id);
        assert_eq!(broker.snapshot().tabs[0].tab_id, second.tab_id);
    }
}
