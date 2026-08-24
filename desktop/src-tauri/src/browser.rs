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
    AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, Webview, WebviewBuilder, WebviewUrl,
};

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
            || self.x < 0.0
            || self.y < 0.0
            || self.width < 160.0
            || self.height < 120.0
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
    recently_closed: Vec<(BrowserProfile, String)>,
    active_tab_id: Option<String>,
    bounds: BrowserBounds,
    persistent_dir: PathBuf,
    guest_root: PathBuf,
}

#[derive(Clone)]
pub struct BrowserBroker {
    inner: Arc<Mutex<BrowserInner>>,
    bridge_stop: Arc<AtomicBool>,
}

pub struct BrowserBridgeEndpoint {
    pub port: u16,
    pub token: String,
}

impl BrowserBroker {
    pub fn new(app_data_dir: PathBuf, cache_dir: PathBuf) -> Self {
        Self {
            inner: Arc::new(Mutex::new(BrowserInner {
                next_tab: 1,
                tabs: HashMap::new(),
                tab_order: Vec::new(),
                recently_closed: Vec::new(),
                active_tab_id: None,
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
        }
    }

    fn tab(&self, tab_id: &str) -> Result<BrowserTab, String> {
        self.inner
            .lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?
            .tabs
            .get(tab_id)
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
    ) -> Result<(BrowserTab, BrowserBounds, PathBuf), String> {
        let mut inner = self
            .inner
            .lock()
            .map_err(|_| "browser broker mutex poisoned".to_string())?;
        let ordinal = inner.next_tab;
        inner.next_tab += 1;
        for tab in inner.tabs.values_mut() {
            tab.active = false;
        }
        let tab_id = format!("tab-{ordinal:08}");
        let tab = BrowserTab {
            tab_id: tab_id.clone(),
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

    pub fn cleanup_guest(&self) {
        self.bridge_stop.store(true, Ordering::Release);
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

fn active_tab_for_request(
    broker: &BrowserBroker,
    requested: Option<&str>,
) -> Result<BrowserTab, String> {
    if let Some(tab_id) = requested.filter(|value| !value.trim().is_empty()) {
        return broker.tab(tab_id);
    }
    let active = broker
        .snapshot()
        .active_tab_id
        .ok_or("no active Smarti Browser tab")?;
    broker.tab(&active)
}

fn js_string(value: &str) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "\"\"".into())
}

fn selector_for(payload: &Value) -> Result<String, String> {
    if let Some(selector) = payload
        .get("selector")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
    {
        return Ok(selector.to_string());
    }
    if let Some(reference) = payload
        .get("ref")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
    {
        return Ok(format!("[data-smarti-ref={}]", js_string(reference)));
    }
    Err("browser action requires selector or snapshot ref".into())
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

fn structured_action(
    app: &AppHandle,
    broker: &BrowserBroker,
    payload: Value,
) -> Result<Value, String> {
    let action = payload
        .get("action")
        .and_then(Value::as_str)
        .unwrap_or("snapshot")
        .replace('-', "_")
        .to_lowercase();
    if matches!(action.as_str(), "status" | "tabs") {
        return serde_json::to_value(broker.snapshot()).map_err(|error| error.to_string());
    }
    if matches!(action.as_str(), "open" | "start")
        && payload
            .get("newTab")
            .and_then(Value::as_bool)
            .unwrap_or(action == "open")
    {
        let url = payload
            .get("url")
            .or_else(|| payload.get("targetUrl"))
            .and_then(Value::as_str)
            .unwrap_or(DEFAULT_URL);
        return create_webview(app, broker, BrowserProfile::Persistent, url)
            .and_then(|value| serde_json::to_value(value).map_err(|error| error.to_string()));
    }
    let tab = active_tab_for_request(
        broker,
        payload
            .get("tabId")
            .or_else(|| payload.get("targetId"))
            .and_then(Value::as_str),
    )?;
    let result = match action.as_str() {
        "navigate" | "open" | "start" => {
            let url = payload
                .get("url")
                .or_else(|| payload.get("targetUrl"))
                .or_else(|| payload.get("query_or_url"))
                .and_then(Value::as_str)
                .ok_or("navigate requires url")?;
            let address = normalize_url(url)?;
            cdp_for_tab(app, &tab, "Page.navigate", json!({"url": address}))?
        }
        "snapshot" => {
            let expression = r#"(() => {
              let n=0; const refs={}; const rows=[];
              const candidates=[...document.querySelectorAll('a,button,input,textarea,select,[role],[contenteditable=true]')].slice(0,180);
              for(const el of candidates){ const r=`e${++n}`; el.setAttribute('data-smarti-ref',r); const role=el.getAttribute('role')||el.tagName.toLowerCase(); const name=(el.getAttribute('aria-label')||el.innerText||el.value||el.getAttribute('placeholder')||'').trim().slice(0,180); refs[r]={ref:r,role,name}; rows.push(`${r} ${role} ${name}`.trim()); }
              return {title:document.title,url:location.href,bodyText:(document.body?.innerText||'').slice(0,8000),snapshot:rows.join('\n'),refs,dir:document.dir||getComputedStyle(document.documentElement).direction};
            })()"#;
            cdp_for_tab(
                app,
                &tab,
                "Runtime.evaluate",
                json!({"expression": expression, "returnByValue": true}),
            )?
        }
        "evaluate" => {
            let expression = payload
                .get("script")
                .or_else(|| payload.get("expression"))
                .and_then(Value::as_str)
                .ok_or("evaluate requires script")?;
            cdp_for_tab(
                app,
                &tab,
                "Runtime.evaluate",
                json!({"expression": expression, "returnByValue": true, "awaitPromise": true}),
            )?
        }
        "click" | "hover" | "fill" | "type" | "select" => {
            let selector = selector_for(&payload)?;
            let selector_js = js_string(&selector);
            let value = payload
                .get("text")
                .or_else(|| payload.get("value"))
                .and_then(Value::as_str)
                .unwrap_or("");
            let value_js = js_string(value);
            let script = match action.as_str() {
                "click" => format!("(() => {{ const el=document.querySelector({selector_js}); if(!el) throw new Error('target not found'); el.scrollIntoView({{block:'center'}}); el.click(); return true; }})()"),
                "hover" => format!("(() => {{ const el=document.querySelector({selector_js}); if(!el) throw new Error('target not found'); el.dispatchEvent(new MouseEvent('mouseover',{{bubbles:true}})); return true; }})()"),
                "select" => format!("(() => {{ const el=document.querySelector({selector_js}); if(!el) throw new Error('target not found'); el.value={value_js}; el.dispatchEvent(new Event('change',{{bubbles:true}})); return el.value; }})()"),
                _ => format!("(() => {{ const el=document.querySelector({selector_js}); if(!el) throw new Error('target not found'); el.focus(); const set=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el),'value')?.set; if(set) set.call(el,{value_js}); else el.value={value_js}; el.dispatchEvent(new Event('input',{{bubbles:true}})); el.dispatchEvent(new Event('change',{{bubbles:true}})); return true; }})()"),
            };
            cdp_for_tab(
                app,
                &tab,
                "Runtime.evaluate",
                json!({"expression": script, "returnByValue": true}),
            )?
        }
        "press" => {
            let key = payload
                .get("key")
                .or_else(|| payload.get("text"))
                .and_then(Value::as_str)
                .unwrap_or("Enter");
            cdp_for_tab(
                app,
                &tab,
                "Input.dispatchKeyEvent",
                json!({"type":"keyDown","key":key}),
            )?;
            cdp_for_tab(
                app,
                &tab,
                "Input.dispatchKeyEvent",
                json!({"type":"keyUp","key":key}),
            )?
        }
        "scroll" | "scroll_into_view" => {
            let x = payload
                .get("deltaX")
                .or_else(|| payload.get("x"))
                .and_then(Value::as_f64)
                .unwrap_or(0.0);
            let y = payload
                .get("deltaY")
                .or_else(|| payload.get("y"))
                .and_then(Value::as_f64)
                .unwrap_or(600.0);
            cdp_for_tab(
                app,
                &tab,
                "Runtime.evaluate",
                json!({"expression":format!("window.scrollBy({x},{y})"),"returnByValue":true}),
            )?
        }
        "upload" => {
            let selector = selector_for(&payload)?;
            let paths = payload
                .get("paths")
                .or_else(|| payload.get("files"))
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            if paths.is_empty() {
                return Err("upload requires approved paths".into());
            }
            let doc = cdp_for_tab(app, &tab, "DOM.getDocument", json!({"depth":0}))?;
            let root = doc
                .pointer("/root/nodeId")
                .and_then(Value::as_i64)
                .ok_or("DOM root unavailable")?;
            let node = cdp_for_tab(
                app,
                &tab,
                "DOM.querySelector",
                json!({"nodeId":root,"selector":selector}),
            )?;
            let node_id = node
                .get("nodeId")
                .and_then(Value::as_i64)
                .filter(|id| *id > 0)
                .ok_or("upload target not found")?;
            cdp_for_tab(
                app,
                &tab,
                "DOM.setFileInputFiles",
                json!({"nodeId":node_id,"files":paths}),
            )?
        }
        "screenshot" => cdp_for_tab(
            app,
            &tab,
            "Page.captureScreenshot",
            json!({"format":"png","captureBeyondViewport":payload.get("fullPage").and_then(Value::as_bool).unwrap_or(false)}),
        )?,
        "pdf" => cdp_for_tab(
            app,
            &tab,
            "Page.printToPDF",
            json!({"printBackground":payload.get("printBackground").and_then(Value::as_bool).unwrap_or(true)}),
        )?,
        "cdp" => {
            let method = payload
                .get("method")
                .and_then(Value::as_str)
                .ok_or("cdp requires method")?;
            cdp_for_tab(
                app,
                &tab,
                method,
                payload.get("params").cloned().unwrap_or_else(|| json!({})),
            )?
        }
        _ => {
            return Err(format!(
                "Smarti Tauri browser action is not implemented in Point 6: {action}"
            ))
        }
    };
    Ok(
        json!({"ok":true,"action":action,"tabId":tab.tab_id,"targetId":tab.target_id,"result":result}),
    )
}

fn read_http_request(stream: &mut TcpStream) -> Result<(String, Value), String> {
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
                        serve_bridge_connection(stream, &app, &broker, &thread_token)
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
                    let _ = stream.read(&mut discard);
                    let body = html.as_bytes();
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
    result.pointer("/result/result/value")
}

pub fn run_foundation_smoke(app: AppHandle, broker: BrowserBroker, result_path: PathBuf) {
    std::thread::Builder::new().name("smarti-browser-foundation-smoke".into()).spawn(move || {
        let result = (|| -> Result<Value, String> {
            let (site_port, site_stop) = start_smoke_site()?;
            let url = format!("http://127.0.0.1:{site_port}/");
            let started = Instant::now();
            let persistent = create_webview(&app, &broker, BrowserProfile::Persistent, &url)?;
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

            let guest_snapshot = create_webview(&app, &broker, BrowserProfile::Guest, &url)?;
            let guest = guest_snapshot.tabs.into_iter().find(|tab| tab.active).ok_or("guest smoke tab missing")?;
            std::thread::sleep(Duration::from_secs(1));
            let guest_initial = cdp_for_tab(&app, &guest, "Runtime.evaluate", json!({"expression":"localStorage.getItem('smarti-point6')","returnByValue":true}))?;
            cdp_for_tab(&app, &guest, "Runtime.evaluate", json!({"expression":"localStorage.setItem('smarti-point6','guest-only')","returnByValue":true}))?;
            let guest_view = app.get_webview(&guest.webview_label).ok_or("guest WebView missing")?;
            guest_view.clear_all_browsing_data().map_err(|error| error.to_string())?;
            guest_view.close().map_err(|error| error.to_string())?;
            broker.rollback_tab(&guest.tab_id);
            let _ = std::fs::remove_dir_all(broker.inner.lock().map_err(|_| "browser broker mutex poisoned".to_string())?.guest_root.join(&guest.tab_id));

            let guest_two_snapshot = create_webview(&app, &broker, BrowserProfile::Guest, &url)?;
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
    if input.is_empty() {
        return Ok(DEFAULT_URL.into());
    }
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
    let payload = receiver
        .recv_timeout(CDP_TIMEOUT)
        .map_err(|_| "WebView2 CDP action timed out".to_string())??;
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
) -> Result<BrowserSnapshot, String> {
    let url = normalize_url(input)?;
    let parsed = url
        .parse::<tauri::Url>()
        .map_err(|error| error.to_string())?;
    let (tab, bounds, data_dir) = broker.allocate_tab(profile, url)?;
    std::fs::create_dir_all(&data_dir).map_err(|error| error.to_string())?;
    let parent = app
        .get_window("main")
        .ok_or("main Tauri window is unavailable")?;
    for existing in parent.webviews() {
        if existing.label().starts_with("browser-") {
            let _ = existing.hide();
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
    let download_app = app.clone();
    let download_profile = profile;
    let builder = WebviewBuilder::new(&tab.webview_label, WebviewUrl::External(parsed))
        .data_directory(data_dir)
        .incognito(profile == BrowserProfile::Guest)
        .on_navigation(|url| matches!(url.scheme(), "http" | "https" | "about"))
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
            std::thread::spawn(move || {
                let result = create_webview(&create_app, &create_broker, popup_profile, &popup_url);
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
) -> Result<BrowserSnapshot, String> {
    create_webview(&app, &broker, profile, &url)
}

#[tauri::command]
pub async fn browser_close(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
) -> Result<BrowserSnapshot, String> {
    let tab = broker.tab(&tab_id)?;
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
        inner.recently_closed.push((tab.profile, tab.url.clone()));
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
            let _ = webview.show();
            let _ = webview.set_focus();
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
    create_webview(&app, &broker, tab.profile, &tab.url)
}

#[tauri::command]
pub async fn browser_restore_closed(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
) -> Result<BrowserSnapshot, String> {
    let closed = broker
        .inner
        .lock()
        .map_err(|_| "browser broker mutex poisoned".to_string())?
        .recently_closed
        .pop();
    let (profile, url) = closed.ok_or("no recently closed browser tab")?;
    create_webview(&app, &broker, profile, &url)
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
    for tab in tabs {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            if tab.tab_id == tab_id {
                let _ = cdp_call(
                    &webview,
                    "Page.setWebLifecycleState".into(),
                    json!({"state":"active"}).to_string(),
                );
                webview.show().map_err(|error| error.to_string())?;
                webview.set_focus().map_err(|error| error.to_string())?;
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
    for tab in broker.snapshot().tabs {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            webview
                .set_position(LogicalPosition::new(bounds.x, bounds.y))
                .map_err(|error| error.to_string())?;
            webview
                .set_size(LogicalSize::new(bounds.width, bounds.height))
                .map_err(|error| error.to_string())?;
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
    let snapshot = broker.snapshot();
    for tab in snapshot.tabs {
        if let Some(webview) = app.get_webview(&tab.webview_label) {
            if visible && tab.active {
                let _ = cdp_call(
                    &webview,
                    "Page.setWebLifecycleState".into(),
                    json!({"state":"active"}).to_string(),
                );
                webview.show().map_err(|error| error.to_string())?;
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
    fn bounds_reject_overlay_and_resource_abuse() {
        assert!(BrowserBounds {
            x: 0.0,
            y: 0.0,
            width: 10.0,
            height: 10.0
        }
        .validate()
        .is_err());
        assert!(BrowserBounds {
            x: 0.0,
            y: 100.0,
            width: 900.0,
            height: 600.0
        }
        .validate()
        .is_ok());
    }

    #[test]
    fn stable_ids_do_not_depend_on_page_index() {
        let temp = std::env::temp_dir().join("smarti-browser-broker-test");
        let broker = BrowserBroker::new(temp.join("data"), temp.join("cache"));
        let (first, _, _) = broker
            .allocate_tab(BrowserProfile::Persistent, DEFAULT_URL.into())
            .unwrap();
        let (second, _, _) = broker
            .allocate_tab(BrowserProfile::Guest, DEFAULT_URL.into())
            .unwrap();
        assert_eq!(first.tab_id, "tab-00000001");
        assert_eq!(first.target_id, "wv2-target-00000001");
        assert_eq!(second.tab_id, "tab-00000002");
        assert_ne!(first.target_id, second.target_id);
    }

    #[test]
    fn product_tab_order_and_recently_closed_are_bounded() {
        let temp = std::env::temp_dir().join("smarti-browser-product-test");
        let broker = BrowserBroker::new(temp.join("data"), temp.join("cache"));
        let (first, _, _) = broker
            .allocate_tab(BrowserProfile::Persistent, "https://one.test".into())
            .unwrap();
        let (second, _, _) = broker
            .allocate_tab(BrowserProfile::Persistent, "https://two.test".into())
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
