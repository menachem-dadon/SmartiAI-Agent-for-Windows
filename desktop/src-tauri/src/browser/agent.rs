//! Owned WebView2 agent transport. No remote-debugging listener or second browser.
use super::*;
use std::collections::VecDeque;
use std::sync::atomic::AtomicU64;

pub const PROTOCOL_VERSION: u32 = 2;
pub const ACTIONS: &[&str] = &[
    "doctor",
    "profiles",
    "status",
    "tabs",
    "start",
    "open",
    "navigate",
    "focus",
    "close",
    "close_tab",
    "close_browser",
    "close_all",
    "snapshot",
    "text",
    "find",
    "frames",
    "screenshot",
    "pdf",
    "click",
    "double_click",
    "click_coords",
    "hover",
    "fill",
    "type",
    "press",
    "select",
    "check",
    "drag",
    "scroll",
    "scroll_into_view",
    "wait",
    "resize",
    "console",
    "errors",
    "requests",
    "network",
    "trace",
    "dialog",
    "upload",
    "download",
    "cookies",
    "storage",
    "evaluate",
    "cdp",
    "show",
    "hide",
    "workspace",
    "pause",
    "resume",
    "stop",
    "back",
    "forward",
    "reload",
    "stop_loading",
    "duplicate",
    "pin",
    "reorder",
];

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Activity {
    pub tab_id: String,
    pub workspace_id: String,
    pub session_id: String,
    pub action: String,
    pub state: String,
    pub presentation: String,
}
#[derive(Default)]
struct Target {
    gate: Mutex<()>,
    paused: AtomicBool,
    user_paused: AtomicBool,
    generation: AtomicU64,
    events: Mutex<VecDeque<Value>>,
    subscribed: AtomicBool,
    presentation: Mutex<String>,
    run_id: Mutex<String>,
    expected_dialog: Mutex<Option<(u64, Value)>>,
}
#[derive(Default)]
pub struct AgentState {
    targets: Mutex<HashMap<String, Arc<Target>>>,
    sessions: Mutex<HashMap<String, String>>,
    owners: Mutex<HashMap<String, String>>,
    activity: Mutex<Option<Activity>>,
    activities: Mutex<HashMap<String, Activity>>,
    policies: Mutex<HashMap<String, Value>>,
    receipts: Mutex<HashMap<String, (String, Option<Value>)>>,
    presentations: Mutex<HashMap<String, Option<String>>>,
}
impl AgentState {
    pub fn activity(&self) -> Option<Activity> {
        self.activity.lock().ok()?.clone()
    }
    pub fn activities(&self) -> Vec<Activity> {
        self.activities.lock().unwrap().values().cloned().collect()
    }
    pub fn closed(&self, id: &str) {
        self.owners.lock().unwrap().remove(id);
        if let Some(target) = self.targets.lock().unwrap().remove(id) {
            target.generation.fetch_add(1, Ordering::AcqRel);
        }
        self.sessions
            .lock()
            .unwrap()
            .retain(|_, target| target != id);
        self.activities
            .lock()
            .unwrap()
            .retain(|_, activity| activity.tab_id != id);
        let mut latest = self.activity.lock().unwrap();
        if latest.as_ref().is_some_and(|a| a.tab_id == id) {
            *latest = None;
        }
    }
    fn target(&self, id: &str) -> Arc<Target> {
        self.targets
            .lock()
            .unwrap()
            .entry(id.into())
            .or_default()
            .clone()
    }
    pub fn running(&self, id: &str) -> bool {
        // Background sessions remain live between model tool calls. UI collapse
        // or tab switching must not freeze a document used by an agent.
        self.owners.lock().unwrap().contains_key(id)
    }
    pub fn record_download(&self, id: &str, value: Value) {
        let target = self.target(id);
        let mut events = target.events.lock().unwrap();
        if events.len() == 500 {
            events.pop_front();
        }
        events.push_back(json!({"method":"Browser.downloadFinished","params":value}));
    }
    pub fn navigation_allowed(&self, workspace: &str, url: &tauri::Url) -> bool {
        let policies = self.policies.lock().unwrap();
        let Some(policy) = policies.get(workspace) else {
            return true;
        };
        if url.as_str() == "about:blank" {
            return true;
        }
        let host = url
            .host_str()
            .unwrap_or("")
            .trim_end_matches('.')
            .to_lowercase();
        if policy["allowPrivate"] == true {
            return true;
        }
        let rules = if let Some(rules) = policy["allowedHosts"].as_array() {
            rules
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect::<Vec<_>>()
        } else {
            policy["allowedHosts"]
                .as_str()
                .unwrap_or("")
                .split([',', ';'])
                .map(str::to_string)
                .collect()
        };
        if rules.iter().any(|rule| {
            let rule = rule.trim().to_lowercase();
            host == rule
                || rule
                    .strip_prefix("*.")
                    .is_some_and(|suffix| host.ends_with(&format!(".{suffix}")))
        }) {
            return true;
        }
        if matches!(
            host.as_str(),
            "localhost" | "local" | "ip6-localhost" | "ip6-loopback"
        ) || host.ends_with(".local")
        {
            return false;
        }
        let host = host.trim_matches(['[', ']']);
        match host.parse::<std::net::IpAddr>() {
            Ok(std::net::IpAddr::V4(ip)) => {
                !(ip.is_private()
                    || ip.is_loopback()
                    || ip.is_link_local()
                    || ip.is_unspecified()
                    || ip.is_multicast()
                    || ip.is_broadcast()
                    || ip.octets()[0] == 0
                    || ip.octets()[0] >= 240)
            }
            Ok(std::net::IpAddr::V6(ip)) => {
                !(ip.is_loopback()
                    || ip.is_unspecified()
                    || ip.is_multicast()
                    || ip.is_unique_local()
                    || ip.is_unicast_link_local()
                    || ip
                        .to_ipv4_mapped()
                        .is_some_and(|v| v.is_private() || v.is_loopback() || v.is_link_local()))
            }
            Err(_) => true,
        }
    }
}

pub fn normalize(action: &str) -> String {
    let mut result = String::new();
    for c in action.chars() {
        if c.is_ascii_uppercase() && !result.is_empty() {
            result.push('_');
        }
        result.push(if c == '-' {
            '_'
        } else {
            c.to_ascii_lowercase()
        });
    }
    match result.as_str() {
        "dblclick" => "double_click".into(),
        "clickcoords" => "click_coords".into(),
        "scrollintoview" => "scroll_into_view".into(),
        _ => result,
    }
}
fn string<'a>(payload: &'a Value, key: &str) -> &'a str {
    payload.get(key).and_then(Value::as_str).unwrap_or("")
}
fn number(payload: &Value, key: &str, default: f64) -> f64 {
    payload.get(key).and_then(Value::as_f64).unwrap_or(default)
}
fn eval(
    app: &AppHandle,
    tab: &BrowserTab,
    payload: &Value,
    expression: String,
    object: bool,
) -> Result<Value, String> {
    let mut params = json!({"expression":expression,"returnByValue":!object,"awaitPromise":true});
    if !string(payload, "frameId").is_empty() {
        let world = cdp_for_tab(
            app,
            tab,
            "Page.createIsolatedWorld",
            json!({"frameId":payload["frameId"],"worldName":"SmartiAgent"}),
        )?;
        params["contextId"] = world["executionContextId"].clone();
    } else {
        let tree = cdp_for_tab(app, tab, "Page.getFrameTree", json!({}))?;
        let frame = tree
            .pointer("/frameTree/frame/id")
            .ok_or("FRAME_UNAVAILABLE")?;
        let world = cdp_for_tab(
            app,
            tab,
            "Page.createIsolatedWorld",
            json!({"frameId":frame,"worldName":"SmartiAgent"}),
        )?;
        params["contextId"] = world["executionContextId"].clone();
    }
    let result = cdp_for_tab(app, tab, "Runtime.evaluate", params)?;
    if result.get("exceptionDetails").is_some() {
        return Err(result
            .pointer("/exceptionDetails/exception/description")
            .and_then(Value::as_str)
            .or_else(|| {
                result
                    .pointer("/exceptionDetails/text")
                    .and_then(Value::as_str)
            })
            .unwrap_or("JAVASCRIPT_EXCEPTION")
            .into());
    }
    if object {
        Ok(result["result"].clone())
    } else {
        Ok(result
            .pointer("/result/value")
            .cloned()
            .unwrap_or(Value::Null))
    }
}
fn dom(app: &AppHandle, tab: &BrowserTab, payload: &Value, op: &str) -> Result<Value, String> {
    let mut request = payload.clone();
    request["op"] = json!(op);
    eval(
        app,
        tab,
        payload,
        format!("({})({})", include_str!("dom.js"), request),
        op == "object",
    )
}
fn ensure_live(app: &AppHandle, broker: &BrowserBroker, tab: &BrowserTab) -> Result<(), String> {
    let view = app.get_webview(&tab.webview_label).ok_or("TARGET_CLOSED")?;
    if !tab.active {
        // Do not hold the broker mutex across a native UI dispatch: page-load
        // and title callbacks acquire the same mutex on the UI thread.
        let bounds = broker.inner.lock().map_err(|_| "browser broker mutex poisoned")?.bounds.clone();
        set_webview_bounds(
            &view,
            &presentation_bounds(&bounds, false),
        )?;
    }
    view.show().map_err(|e| e.to_string())?;
    cdp_for_tab(
        app,
        tab,
        "Page.setWebLifecycleState",
        json!({"state":"active"}),
    )?;
    Ok(())
}
fn check(target: &Target, generation: u64) -> Result<(), String> {
    if target.generation.load(Ordering::Acquire) != generation {
        return Err("CANCELLED: user stopped or took control; do not retry".into());
    }
    if target.paused.load(Ordering::Acquire) {
        return Err("PAUSED: user controls this tab; wait for resume".into());
    }
    Ok(())
}
fn wait_dom(
    app: &AppHandle,
    tab: &BrowserTab,
    payload: &Value,
    target: &Target,
    generation: u64,
    op: &str,
) -> Result<Value, String> {
    let deadline = Instant::now()
        + Duration::from_millis(number(payload, "timeoutMs", 10000.0).clamp(0.0, 30000.0) as u64);
    let mut previous = None;
    loop {
        check(target, generation)?;
        match dom(app, tab, payload, op) {
            Ok(value) => {
                if op != "prepare" || previous.as_ref() == Some(&value["box"]) {
                    return Ok(value);
                }
                previous = Some(value["box"].clone());
            }
            Err(error)
                if error.contains("STALE_REF")
                    || error.contains("AMBIGUOUS")
                    || error.contains("TARGET_REQUIRED") =>
            {
                return Err(error)
            }
            Err(error) if Instant::now() >= deadline => {
                return Err(format!("ACTIONABILITY_TIMEOUT: {error}"))
            }
            Err(_) => {}
        }
        if Instant::now() >= deadline {
            return Err("TARGET_UNSTABLE".into());
        }
        std::thread::sleep(Duration::from_millis(90));
    }
}
fn modifiers(payload: &Value) -> i64 {
    payload
        .get("modifiers")
        .and_then(Value::as_array)
        .map(|a| {
            a.iter().fold(0, |bits, v| {
                bits | match v.as_str().unwrap_or("").to_lowercase().as_str() {
                    "alt" => 1,
                    "control" | "ctrl" => 2,
                    "meta" => 4,
                    "shift" => 8,
                    _ => 0,
                }
            })
        })
        .unwrap_or(0)
}
fn press(app: &AppHandle, tab: &BrowserTab, key: &str) -> Result<Value, String> {
    let parts = key.split('+').collect::<Vec<_>>();
    let key = parts.last().copied().unwrap_or("Enter");
    let mask = parts
        .iter()
        .take(parts.len().saturating_sub(1))
        .fold(0, |n, v| {
            n | match v.to_lowercase().as_str() {
                "control" | "ctrl" => 2,
                "alt" => 1,
                "shift" => 8,
                "meta" => 4,
                _ => 0,
            }
        });
    let vk = match key {
        "Enter" => 13,
        "Tab" => 9,
        "Backspace" => 8,
        "Delete" => 46,
        "Escape" => 27,
        "ArrowLeft" => 37,
        "ArrowUp" => 38,
        "ArrowRight" => 39,
        "ArrowDown" => 40,
        "Home" => 36,
        "End" => 35,
        "PageUp" => 33,
        "PageDown" => 34,
        "Space" | " " => 32,
        _ => key
            .chars()
            .next()
            .map(|c| c.to_ascii_uppercase() as u32)
            .unwrap_or(0),
    };
    let mut params = json!({"type":"keyDown","key":if key=="Space" {" "} else {key},"windowsVirtualKeyCode":vk,"modifiers":mask});
    if mask == 0 && (key == "Enter" || key.len() == 1 || key == "Space") {
        params["text"] = json!(if key == "Enter" {
            "\r"
        } else if key == "Space" {
            " "
        } else {
            key
        });
    }
    cdp_for_tab(app, tab, "Input.dispatchKeyEvent", params)?;
    cdp_for_tab(
        app,
        tab,
        "Input.dispatchKeyEvent",
        json!({"type":"keyUp","key":key,"windowsVirtualKeyCode":vk,"modifiers":mask}),
    )
}
fn mouse(
    app: &AppHandle,
    tab: &BrowserTab,
    payload: &Value,
    x: f64,
    y: f64,
    kind: &str,
    count: i64,
) -> Result<Value, String> {
    cdp_for_tab(
        app,
        tab,
        "Input.dispatchMouseEvent",
        json!({"type":kind,"x":x,"y":y,"button":if kind=="mouseMoved" {"none"} else {payload.get("button").and_then(Value::as_str).unwrap_or("left")},"clickCount":count,"modifiers":modifiers(payload)}),
    )
}
fn frame_offset(app: &AppHandle, tab: &BrowserTab, payload: &Value) -> Result<(f64, f64), String> {
    if string(payload, "frameId").is_empty() {
        return Ok((0.0, 0.0));
    }
    // CDP Input coordinates are relative to the top viewport. Native DOM box
    // models give the owning frame's content quadrilateral in that viewport.
    let owner = cdp_for_tab(
        app,
        tab,
        "DOM.getFrameOwner",
        json!({"frameId":payload["frameId"]}),
    )?;
    let model = cdp_for_tab(
        app,
        tab,
        "DOM.getBoxModel",
        json!({"backendNodeId":owner["backendNodeId"]}),
    )?;
    let quad = model
        .pointer("/model/content")
        .and_then(Value::as_array)
        .ok_or("FRAME_BOX_UNAVAILABLE")?;
    Ok((
        quad[0].as_f64().unwrap_or(0.0),
        quad[1].as_f64().unwrap_or(0.0),
    ))
}
fn snapshot(app: &AppHandle, tab: &BrowserTab, payload: &Value) -> Result<Value, String> {
    let mut value = dom(app, tab, payload, "snapshot")?;
    value["tabId"] = json!(tab.tab_id);
    value["targetId"] = json!(tab.target_id);
    if string(payload, "refs") != "dom" && string(payload, "snapshotFormat") != "dom" {
        let ax = cdp_for_tab(
            app,
            tab,
            "Accessibility.getFullAXTree",
            if payload.get("frameId").is_some() {
                json!({"frameId":payload["frameId"]})
            } else {
                json!({})
            },
        )?;
        // Preserve parent/child relationships, states and ignored containers:
        // these are structural data, not a duplicate of actionable DOM refs.
        value["accessibility"] = ax["nodes"].clone();
    }
    Ok(value)
}

pub fn run(app: &AppHandle, broker: &BrowserBroker, mut payload: Value) -> Result<Value, String> {
    if !payload.is_object() {
        return Err("INVALID_REQUEST: expected an object".into());
    }
    // A caller can safely retrieve a lost response with the same requestId.
    // Reusing it with different arguments is rejected; in-flight requests never
    // execute twice. The cache is bounded and lives only for this app session.
    let id = string(&payload, "requestId").to_string();
    if !id.is_empty() && !matches!(string(&payload, "action"), "screenshot" | "pdf") {
        let encoded = payload.to_string();
        let mut receipts = broker.agent.receipts.lock().unwrap();
        if let Some((original, response)) = receipts.get(&id) {
            if original != &encoded {
                return Err("REQUEST_ID_CONFLICT".into());
            }
            return response
                .clone()
                .ok_or_else(|| "REQUEST_IN_FLIGHT: do not replay this action".into());
        }
        if receipts.len() >= 64 {
            if let Some(old) = receipts
                .iter()
                .find(|(_, (_, value))| value.is_some())
                .map(|(id, _)| id.clone())
            {
                receipts.remove(&old);
            }
        }
        receipts.insert(id.clone(), (encoded, None));
        drop(receipts);
        let result = run_inner(app, broker, payload.take());
        let response = match result {
            Ok(value) => value,
            Err(error) => json!({"ok":false,"error":error,"requestId":id}),
        };
        if let Some((_, cached)) = broker.agent.receipts.lock().unwrap().get_mut(&id) {
            *cached = Some(response.clone());
        }
        return Ok(response);
    }
    run_inner(app, broker, payload)
}
fn run_inner(app: &AppHandle, broker: &BrowserBroker, mut payload: Value) -> Result<Value, String> {
    if string(&payload, "action") == "act" {
        let request = payload
            .get("request")
            .and_then(Value::as_object)
            .ok_or("act requires request")?
            .clone();
        for (key, value) in request {
            payload[key] = value;
        }
        payload["action"] = payload
            .get("kind")
            .cloned()
            .unwrap_or_else(|| json!("snapshot"));
    }
    let action = normalize(if string(&payload, "action").is_empty() {
        "snapshot"
    } else {
        string(&payload, "action")
    });
    payload["action"] = json!(action);
    if !ACTIONS.contains(&action.as_str()) {
        return Err(format!("UNSUPPORTED_ACTION: {action}"));
    }
    if matches!(action.as_str(), "doctor" | "status" | "tabs" | "profiles") {
        return Ok(
            json!({"ok":true,"protocolVersion":PROTOCOL_VERSION,"ready":true,"transport":"webview2-in-process-cdp","remoteDebuggingPort":null,"capabilities":ACTIONS,"tabs":broker.snapshot().tabs,"activeTabId":broker.snapshot().active_tab_id,"agent":broker.agent.activity(),"agents":broker.agent.activities(),"profiles":[{"id":"smarti","persistent":true},{"id":"guest","persistent":false}]}),
        );
    }
    if action == "workspace" && string(&payload, "operation") == "list" {
        return Ok(
            json!({"ok":true,"workspaces":broker.snapshot().tabs.iter().map(|tab|json!({"workspaceId":tab.workspace_id,"tabId":tab.tab_id,"active":tab.active})).collect::<Vec<_>>()}),
        );
    }
    let session = if string(&payload, "sessionId").is_empty() {
        "__legacy__".to_string()
    } else {
        string(&payload, "sessionId").to_string()
    };
    let owner = if string(&payload, "workspaceId").is_empty() {
        format!("browser-agent-{session}")
    } else {
        string(&payload, "workspaceId").to_string()
    };
    let owned_tabs = broker.snapshot().tabs;
    if owned_tabs.iter().any(|tab| {
        tab.workspace_id == owner
            && broker
                .agent
                .owners
                .lock()
                .unwrap()
                .get(&tab.tab_id)
                .is_some_and(|other| other != &session)
    }) {
        return Err("TARGET_BUSY: another conversation owns this workspace".into());
    }
    let requested = payload
        .get("tabId")
        .or_else(|| payload.get("targetId"))
        .and_then(Value::as_str)
        .filter(|id| !id.is_empty());
    let remembered = broker.agent.sessions.lock().unwrap().get(&session).cloned();
    let mut tab = requested
        .and_then(|id| broker.tab(id).ok())
        .or_else(|| remembered.as_deref().and_then(|id| broker.tab(id).ok()));
    if requested.is_some()
        && tab.as_ref().is_none_or(|t| {
            Some(t.tab_id.as_str()) != requested && Some(t.target_id.as_str()) != requested
        })
    {
        return Err("TARGET_CLOSED: request a new tabs list".into());
    }
    if action == "open"
        && payload
            .get("newTab")
            .and_then(Value::as_bool)
            .unwrap_or(true)
    {
        tab = None;
    }
    if let Some(policy) = payload.get("navigationPolicy") {
        broker
            .agent
            .policies
            .lock()
            .unwrap()
            .insert(owner.clone(), policy.clone());
    }
    if tab.is_none()
        && matches!(
            action.as_str(),
            "start" | "open" | "navigate" | "show" | "workspace"
        )
    {
        let profile = if string(&payload, "profile") == "guest" {
            BrowserProfile::Guest
        } else {
            BrowserProfile::Persistent
        };
        let snapshot = create_webview_with_presentation(
            app,
            broker,
            profile,
            "about:blank",
            Some(owner.clone()),
            false,
        )?;
        tab = snapshot
            .tabs
            .into_iter()
            .rev()
            .find(|t| t.workspace_id == owner);
    }
    let tab = tab.ok_or("NO_TARGET: use start or open first")?;
    // UI controls carry explicit authority; model actions are session fenced.
    if !payload
        .get("userControl")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        let tabs = broker.snapshot().tabs;
        let mut owners = broker.agent.owners.lock().unwrap();
        if owners
            .get(&tab.tab_id)
            .is_some_and(|other| other != &session)
            || tabs.iter().any(|candidate| {
                candidate.workspace_id == tab.workspace_id
                    && owners
                        .get(&candidate.tab_id)
                        .is_some_and(|other| other != &session)
            })
        {
            return Err("TARGET_BUSY: another conversation owns this tab".into());
        }
        owners.insert(tab.tab_id.clone(), session.clone());
    }
    if let Some(policy) = payload.get("navigationPolicy") {
        broker
            .agent
            .policies
            .lock()
            .unwrap()
            .insert(tab.workspace_id.clone(), policy.clone());
    }
    let target = broker.agent.target(&tab.tab_id);
    if matches!(action.as_str(), "pause" | "stop" | "resume") {
        let user_control = payload
            .get("userControl")
            .and_then(Value::as_bool)
            .unwrap_or(false);
        if action == "resume" && target.user_paused.load(Ordering::Acquire) && !user_control {
            return Err("USER_CONTROL_REQUIRED: the user paused this tab; resume it using the browser control".into());
        }
        if action == "stop"
            && !string(&payload, "runId").is_empty()
            && *target.run_id.lock().unwrap() != string(&payload, "runId")
        {
            return Ok(
                json!({"ok":true,"state":"superseded","message":"old run cancellation ignored"}),
            );
        }
        if action != "resume" {
            target.generation.fetch_add(1, Ordering::AcqRel);
        }
        target.paused.store(action != "resume", Ordering::Release);
        if user_control {
            target
                .user_paused
                .store(action != "resume", Ordering::Release);
        }
        if let Ok(mut activity) = broker.agent.activity.lock() {
            if let Some(a) = activity.as_mut().filter(|a| a.tab_id == tab.tab_id) {
                a.state = if action == "resume" {
                    "ready"
                } else if action == "stop" {
                    "stopped"
                } else {
                    "paused"
                }
                .into();
            }
        }
        for activity in broker
            .agent
            .activities
            .lock()
            .unwrap()
            .values_mut()
            .filter(|a| a.tab_id == tab.tab_id)
        {
            activity.state = if action == "resume" {
                "ready"
            } else if action == "stop" {
                "stopped"
            } else {
                "paused"
            }
            .into();
        }
        emit_snapshot(app, broker);
        return Ok(
            json!({"ok":true,"tabId":tab.tab_id,"state":if action=="resume"{"ready"}else if action=="stop"{"stopped"}else{"paused"}}),
        );
    }
    let _lease = target
        .gate
        .try_lock()
        .map_err(|_| "TARGET_BUSY: an action is already running; do not replay mutations")?;
    if !string(&payload, "runId").is_empty() {
        // A later Core run may continue after cancellation. A user's takeover
        // remains fenced until the user explicitly returns browser control.
        if *target.run_id.lock().unwrap() != string(&payload, "runId")
            && !target.user_paused.load(Ordering::Acquire)
        {
            target.paused.store(false, Ordering::Release);
        }
        *target.run_id.lock().unwrap() = string(&payload, "runId").into();
    }
    let generation = target.generation.load(Ordering::Acquire);
    let read_only = matches!(
        action.as_str(),
        "snapshot"
            | "text"
            | "find"
            | "frames"
            | "screenshot"
            | "pdf"
            | "show"
            | "hide"
            | "workspace"
            | "focus"
            | "console"
            | "errors"
            | "requests"
            | "network"
            | "trace"
            | "download"
    );
    if !read_only {
        check(&target, generation)?;
    }
    broker
        .agent
        .sessions
        .lock()
        .unwrap()
        .insert(session.clone(), tab.tab_id.clone());
    ensure_live(app, broker, &tab)?;
    subscribe(app, &tab, target.clone())?;
    let presentation = {
        let mut mode = target.presentation.lock().unwrap();
        if let Some(value) = payload.get("presentation").and_then(Value::as_str) {
            if !matches!(value, "preview" | "hidden" | "visible") {
                return Err("INVALID_PRESENTATION".into());
            }
            *mode = value.into();
        }
        if mode.is_empty() {
            *mode = "preview".into();
        }
        mode.clone()
    };
    let activity = Activity {
        tab_id: tab.tab_id.clone(),
        workspace_id: tab.workspace_id.clone(),
        session_id: session.clone(),
        action: action.clone(),
        state: if target.paused.load(Ordering::Acquire) {
            "paused"
        } else {
            "running"
        }
        .into(),
        presentation: presentation.clone(),
    };
    *broker.agent.activity.lock().unwrap() = Some(activity.clone());
    broker
        .agent
        .activities
        .lock()
        .unwrap()
        .insert(session.clone(), activity);
    emit_snapshot(app, broker);
    if payload.get("expectDialog").and_then(Value::as_bool) == Some(true) {
        *target.expected_dialog.lock().unwrap() = Some((
            generation,
            json!({"accept":payload.get("accept").and_then(Value::as_bool).unwrap_or(true),"promptText":payload.get("promptText").and_then(Value::as_str).unwrap_or("")}),
        ));
    }
    let result = execute(app, broker, &tab, &payload, &target, generation, &action);
    target.expected_dialog.lock().unwrap().take();
    if let Some(activity) = broker.agent.activities.lock().unwrap().get_mut(&session) {
        if activity.state == "running" {
            activity.state = if result.is_ok() { "ready" } else { "error" }.into();
        }
    }
    if let Some(activity) = broker.agent.activity.lock().unwrap().as_mut() {
        if activity.tab_id == tab.tab_id && activity.state == "running" {
            activity.state = if result.is_ok() { "ready" } else { "error" }.into();
        }
    }
    emit_snapshot(app, broker);
    let result = result?;
    if !read_only
        && !matches!(
            action.as_str(),
            "close" | "close_tab" | "close_browser" | "close_all"
        )
    {
        check(&target, generation)?;
    }
    if payload.get("presentation").is_some()
        && !matches!(action.as_str(), "show" | "hide" | "focus" | "workspace")
    {
        app.emit("browser://presentation",json!({"workspaceId":tab.workspace_id,"tabId":tab.tab_id,"sessionId":session,"mode":presentation})).map_err(|e|e.to_string())?;
    }
    let phase = result
        .get("phase")
        .cloned()
        .unwrap_or_else(|| json!("executed"));
    let page_result = matches!(action.as_str(), "navigate" | "open" | "start");
    let mut response = json!({"ok":true,"protocolVersion":PROTOCOL_VERSION,"action":action,"tabId":tab.tab_id,"targetId":tab.target_id,"workspaceId":tab.workspace_id,"phase":phase});
    if page_result {
        if payload.get("noSnapshot").and_then(Value::as_bool) != Some(true) {
            response["page"] = result;
        }
        response["verification"] = json!("observed");
    } else {
        response["result"] = result;
    }
    let pending_dialog = t_dialog(&target);
    if let Some(dialog) = pending_dialog {
        response["dialog"] = dialog;
        if payload.get("expectDialog").and_then(Value::as_bool) == Some(true) {
            cdp_for_tab(
                app,
                &tab,
                "Page.handleJavaScriptDialog",
                json!({"accept":payload.get("accept").and_then(Value::as_bool).unwrap_or(true),"promptText":payload.get("promptText").and_then(Value::as_str).unwrap_or("")}),
            )?;
        } else {
            response["verification"] = json!("waiting-for-dialog");
            return Ok(response);
        }
    }
    if !payload
        .get("noSnapshot")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        && matches!(
            action.as_str(),
            "click"
                | "double_click"
                | "fill"
                | "type"
                | "press"
                | "select"
                | "check"
                | "drag"
                | "scroll"
                | "hover"
        )
    {
        match snapshot(app, &tab, &payload) {
            Ok(page) => {
                response["page"] = page;
                response["verification"] = json!("observed");
            }
            Err(error) => {
                response["verification"] = json!("unavailable");
                response["snapshotError"] = json!(error);
            }
        }
    }
    Ok(response)
}
fn t_dialog(target: &Target) -> Option<Value> {
    let events = target.events.lock().unwrap();
    let latest = events
        .iter()
        .rev()
        .find(|event| string(event, "method").starts_with("Page.javascriptDialog"))?;
    (string(latest, "method") == "Page.javascriptDialogOpening").then(|| latest["params"].clone())
}
fn execute(
    app: &AppHandle,
    broker: &BrowserBroker,
    tab: &BrowserTab,
    p: &Value,
    t: &Target,
    g: u64,
    a: &str,
) -> Result<Value, String> {
    match a {
        "back" | "forward" => {
            let history = cdp_for_tab(app, tab, "Page.getNavigationHistory", json!({}))?;
            let index =
                history["currentIndex"].as_i64().unwrap_or(0) + if a == "back" { -1 } else { 1 };
            let entry = history["entries"]
                .as_array()
                .and_then(|entries| {
                    if index >= 0 {
                        entries.get(index as usize)
                    } else {
                        None
                    }
                })
                .ok_or("NO_HISTORY_ENTRY")?;
            cdp_for_tab(
                app,
                tab,
                "Page.navigateToHistoryEntry",
                json!({"entryId":entry["id"]}),
            )
        }
        "reload" => cdp_for_tab(app, tab, "Page.reload", json!({})),
        "stop_loading" => cdp_for_tab(app, tab, "Page.stopLoading", json!({})),
        "duplicate" => serde_json::to_value(create_webview_with_presentation(
            app,
            broker,
            tab.profile,
            &tab.url,
            Some(tab.workspace_id.clone()),
            false,
        )?)
        .map_err(|e| e.to_string()),
        "pin" => {
            broker
                .inner
                .lock()
                .unwrap()
                .tabs
                .get_mut(&tab.tab_id)
                .ok_or("TARGET_CLOSED")?
                .pinned = p.get("pinned").and_then(Value::as_bool).unwrap_or(true);
            Ok(json!({"pinned":broker.tab(&tab.tab_id)?.pinned}))
        }
        "reorder" => {
            let mut inner = broker.inner.lock().unwrap();
            let slots = inner
                .tab_order
                .iter()
                .enumerate()
                .filter_map(|(i, id)| {
                    inner
                        .tabs
                        .get(id)
                        .filter(|t| t.workspace_id == tab.workspace_id)
                        .map(|_| i)
                })
                .collect::<Vec<_>>();
            let mut group = slots
                .iter()
                .map(|i| inner.tab_order[*i].clone())
                .collect::<Vec<_>>();
            group.retain(|id| id != &tab.tab_id);
            let index = (number(p, "index", 0.0).max(0.0) as usize).min(group.len());
            group.insert(index, tab.tab_id.clone());
            for (slot, id) in slots.into_iter().zip(group.iter()) {
                inner.tab_order[slot] = id.clone();
            }
            Ok(json!({"tabOrder":group}))
        }
        "start"
            if p.get("url")
                .or_else(|| p.get("targetUrl"))
                .or_else(|| p.get("query_or_url"))
                .is_none() =>
        {
            snapshot(app, tab, p)
        }
        "start" | "open" | "navigate" => {
            let raw = p
                .get("url")
                .or_else(|| p.get("targetUrl"))
                .or_else(|| p.get("query_or_url"))
                .and_then(Value::as_str)
                .unwrap_or("about:blank");
            let wait_until = match string(p, "waitUntil") {
                "" => "domcontentloaded",
                "commit" | "domcontentloaded" | "load" => string(p, "waitUntil"),
                _ => {
                    return Err(
                        "UNSUPPORTED_WAIT_STATE: use commit, domcontentloaded or load".into(),
                    )
                }
            };
            let result = cdp_for_tab(
                app,
                tab,
                "Page.navigate",
                json!({"url":normalize_url(raw)?}),
            )?;
            if let Some(error) = result.get("errorText") {
                return Err(format!("NAVIGATION_FAILED: {error}"));
            }
            let deadline = Instant::now()
                + Duration::from_millis(number(p, "timeoutMs", 10000.0).clamp(0.0, 30000.0) as u64);
            while Instant::now() < deadline {
                check(t, g)?;
                let frame = cdp_for_tab(app, tab, "Page.getFrameTree", json!({}))?;
                let committed = result.get("loaderId").is_none_or(|loader| {
                    frame.pointer("/frameTree/frame/loaderId") == Some(loader)
                });
                if committed {
                    if let Ok(page) = dom(app, tab, p, "snapshot") {
                        let ready = match wait_until {
                            "commit" => true,
                            "load" => page["readyState"] == "complete",
                            _ => page["readyState"] != "loading",
                        };
                        if ready && (page["url"] != "about:blank" || raw == "about:blank") {
                            return snapshot(app, tab, p);
                        }
                    }
                }
                std::thread::sleep(Duration::from_millis(100));
            }
            Err("NAVIGATION_TIMEOUT: new document readiness was not observed; inspect before retrying".into())
        }
        "snapshot" | "find" => snapshot(app, tab, p),
        "text" => dom(app, tab, p, "text"),
        "frames" => cdp_for_tab(app, tab, "Page.getFrameTree", json!({})),
        "evaluate" => {
            let expression = p
                .get("script")
                .or_else(|| p.get("expression"))
                .and_then(Value::as_str)
                .ok_or("evaluate requires script")?;
            // User evaluation uses the page's main world (isolated world is for
            // Smarti references only), preserving website JS inspection.
            let value = cdp_for_tab(
                app,
                tab,
                "Runtime.evaluate",
                json!({"expression":expression,"returnByValue":true,"awaitPromise":true}),
            )?;
            if value.get("exceptionDetails").is_some() {
                Err(format!(
                    "JAVASCRIPT_EXCEPTION: {}",
                    value["exceptionDetails"]
                ))
            } else {
                Ok(value["result"]["value"].clone())
            }
        }
        "cdp" => cdp_for_tab(
            app,
            tab,
            string(p, "method"),
            p.get("params").cloned().unwrap_or_else(|| json!({})),
        ),
        "screenshot" => {
            let full = p.get("fullPage").and_then(Value::as_bool).unwrap_or(false);
            let mut params = json!({"format":"png","captureBeyondViewport":full});
            if let Some(clip) = p.get("clip") {
                params["clip"] = clip.clone();
                params["clip"]["scale"] = json!(1);
            } else if p.get("ref").is_some() || p.get("selector").is_some() {
                let info = dom(app, tab, p, "scroll")?;
                params["clip"] = info["box"].clone();
                params["clip"]["scale"] = json!(1);
            } else if full {
                let metrics = cdp_for_tab(app, tab, "Page.getLayoutMetrics", json!({}))?;
                params["clip"] = metrics["cssContentSize"].clone();
                params["clip"]["scale"] = json!(1);
            }
            let mut image = cdp_for_tab(app, tab, "Page.captureScreenshot", params)?;
            if p.get("labels").and_then(Value::as_bool).unwrap_or(false) {
                image["annotations"] = snapshot(app, tab, p)?["refs"].clone();
                image["annotationMode"] = json!("metadata");
            }
            Ok(image)
        }
        "pdf" => cdp_for_tab(
            app,
            tab,
            "Page.printToPDF",
            json!({"printBackground":p.get("printBackground").and_then(Value::as_bool).unwrap_or(true),"landscape":p.get("landscape").and_then(Value::as_bool).unwrap_or(false)}),
        ),
        "click" | "double_click" | "hover" | "click_coords" | "check" | "drag" => {
            let point = if a == "click_coords" {
                json!({"x":number(p,"x",0.0),"y":number(p,"y",0.0)})
            } else {
                wait_dom(app, tab, p, t, g, "prepare")?
            };
            if a == "check"
                && point["checked"].as_bool()
                    == Some(p.get("checked").and_then(Value::as_bool).unwrap_or(true))
            {
                return Ok(json!({"changed":false,"verified":true}));
            }
            let (ox, oy) = frame_offset(app, tab, p)?;
            let x = number(&point, "x", 0.0) + ox;
            let y = number(&point, "y", 0.0) + oy;
            mouse(app, tab, p, x, y, "mouseMoved", 0)?;
            check(t, g)?;
            if a == "hover" {
                return Ok(point);
            }
            let count = if a == "double_click" { 2 } else { 1 };
            mouse(app, tab, p, x, y, "mousePressed", 1)?;
            if a == "drag" {
                let mut dest = p.clone();
                dest["ref"] = p.get("toRef").cloned().unwrap_or(Value::Null);
                dest["selector"] = p.get("toSelector").cloned().unwrap_or(Value::Null);
                let endpoint = wait_dom(app, tab, &dest, t, g, "prepare")?;
                let ex = number(&endpoint, "x", 0.0) + ox;
                let ey = number(&endpoint, "y", 0.0) + oy;
                for i in 1..=12 {
                    check(t, g)?;
                    cdp_for_tab(
                        app,
                        tab,
                        "Input.dispatchMouseEvent",
                        json!({"type":"mouseMoved","button":"left","buttons":1,"x":x+(ex-x)*i as f64/12.0,"y":y+(ey-y)*i as f64/12.0}),
                    )?;
                }
                mouse(app, tab, p, ex, ey, "mouseReleased", 1)?;
            } else {
                mouse(app, tab, p, x, y, "mouseReleased", 1)?;
                if count == 2 {
                    mouse(app, tab, p, x, y, "mousePressed", 2)?;
                    mouse(app, tab, p, x, y, "mouseReleased", 2)?;
                }
            }
            if a == "check" {
                let value = dom(app, tab, p, "describe")?;
                if value["checked"].as_bool()
                    != Some(p.get("checked").and_then(Value::as_bool).unwrap_or(true))
                {
                    return Err("CHECK_NOT_VERIFIED".into());
                }
            }
            Ok(json!({"input":"trusted-cdp","point":point}))
        }
        "fill" | "type" => {
            wait_dom(app, tab, p, t, g, "prepare")?;
            dom(app, tab, p, "focus")?;
            if a == "fill" {
                press(app, tab, "Control+A")?;
                press(app, tab, "Backspace")?;
            }
            check(t, g)?;
            let value = p
                .get("text")
                .or_else(|| p.get("value"))
                .and_then(Value::as_str)
                .unwrap_or("");
            cdp_for_tab(app, tab, "Input.insertText", json!({"text":value}))?;
            let observed = dom(app, tab, p, "describe")?;
            if a == "fill"
                && observed["value"] != "[redacted]"
                && observed
                    .get("value")
                    .and_then(Value::as_str)
                    .is_some_and(|v| v != value)
            {
                return Err("FILL_NOT_VERIFIED".into());
            }
            Ok(json!({"input":"trusted-cdp","target":observed}))
        }
        "press" => {
            if p.get("ref").is_some() || p.get("selector").is_some() || p.get("role").is_some() {
                wait_dom(app, tab, p, t, g, "prepare")?;
                dom(app, tab, p, "focus")?;
            }
            press(
                app,
                tab,
                p.get("key")
                    .or_else(|| p.get("text"))
                    .and_then(Value::as_str)
                    .unwrap_or("Enter"),
            )
        }
        "select" => {
            wait_dom(app, tab, p, t, g, "prepare")?;
            dom(app, tab, p, "select")
        }
        "scroll_into_view" => dom(app, tab, p, "scroll"),
        "scroll" => {
            let point = if p.get("ref").is_some() || p.get("selector").is_some() {
                wait_dom(app, tab, p, t, g, "prepare")?
            } else {
                json!({"x":320,"y":240})
            };
            let (ox, oy) = frame_offset(app, tab, p)?;
            cdp_for_tab(
                app,
                tab,
                "Input.dispatchMouseEvent",
                json!({"type":"mouseWheel","x":number(&point,"x",320.0)+ox,"y":number(&point,"y",240.0)+oy,"deltaX":number(p,"deltaX",0.0),"deltaY":number(p,"deltaY",number(p,"y",600.0))}),
            )
        }
        "wait" => {
            let deadline = Instant::now()
                + Duration::from_millis(number(p, "timeoutMs", 10000.0).clamp(0.0, 30000.0) as u64);
            loop {
                check(t, g)?;
                let ok = if p.get("ref").is_some()
                    || p.get("selector").is_some()
                    || p.get("role").is_some()
                {
                    match dom(app, tab, p, "describe") {
                        Ok(v) => match string(p, "state") {
                            "hidden" => !v["visible"].as_bool().unwrap_or(false),
                            "attached" => true,
                            "detached" => false,
                            _ => v["visible"].as_bool().unwrap_or(false),
                        },
                        Err(error)
                            if error.contains("AMBIGUOUS_TARGET")
                                || error.contains("STALE_REF") =>
                        {
                            return Err(error)
                        }
                        Err(error) => {
                            error.contains("TARGET_NOT_FOUND")
                                && matches!(string(p, "state"), "hidden" | "detached")
                        }
                    }
                } else {
                    let v = dom(app, tab, p, "snapshot")?;
                    if p.get("text").is_some() {
                        v["bodyText"]
                            .as_str()
                            .unwrap_or("")
                            .contains(string(p, "text"))
                    } else if p.get("url").is_some() {
                        v["url"].as_str().unwrap_or("").contains(string(p, "url"))
                    } else {
                        if matches!(string(p, "state"), "load" | "complete") {
                            v["readyState"] == "complete"
                        } else {
                            v["readyState"] != "loading"
                        }
                    }
                };
                if ok {
                    return Ok(json!({"conditionMet":true}));
                }
                if Instant::now() >= deadline {
                    return Err("WAIT_TIMEOUT: condition not observed".into());
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }
        "resize" => cdp_for_tab(
            app,
            tab,
            "Emulation.setDeviceMetricsOverride",
            json!({"width":number(p,"width",980.0).clamp(200.0,4096.0) as u64,"height":number(p,"height",548.0).clamp(200.0,4096.0) as u64,"deviceScaleFactor":1,"mobile":false}),
        ),
        "console" | "errors" | "requests" | "network" | "trace" | "download" => {
            if a == "download"
                && (p.get("ref").is_some()
                    || p.get("selector").is_some()
                    || p.get("role").is_some())
            {
                check(t, g)?;
                let before = t
                    .events
                    .lock()
                    .unwrap()
                    .iter()
                    .filter(|e| string(e, "method") == "Browser.downloadFinished")
                    .count();
                execute(app, broker, tab, p, t, g, "click")?;
                let deadline = Instant::now()
                    + Duration::from_millis(
                        number(p, "timeoutMs", 10000.0).clamp(0.0, 30000.0) as u64
                    );
                loop {
                    check(t, g)?;
                    let events = t.events.lock().unwrap();
                    let finished = events
                        .iter()
                        .filter(|e| string(e, "method") == "Browser.downloadFinished")
                        .collect::<Vec<_>>();
                    if finished.len() > before {
                        let value = finished.last().unwrap()["params"].clone();
                        if value["success"] != true {
                            return Err("DOWNLOAD_FAILED".into());
                        }
                        return Ok(value);
                    }
                    drop(events);
                    if Instant::now() >= deadline {
                        return Err("DOWNLOAD_TIMEOUT: no completed download observed".into());
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }
            }
            if p.get("reload").and_then(Value::as_bool).unwrap_or(false) {
                check(t, g)?;
                cdp_for_tab(app, tab, "Page.reload", json!({}))?;
            }
            if a == "trace" && string(p, "operation") == "start" {
                t.events.lock().unwrap().clear();
            }
            let capture = number(p, "captureMs", 0.0).clamp(0.0, 5000.0) as u64;
            let deadline = Instant::now() + Duration::from_millis(capture);
            while Instant::now() < deadline {
                check(t, g)?;
                std::thread::sleep(Duration::from_millis(100));
            }
            let offset = number(p, "offset", 0.0).max(0.0) as usize;
            let limit = number(p, "limit", 100.0).clamp(1.0, 500.0) as usize;
            let events = t.events.lock().unwrap();
            let filtered = events
                .iter()
                .filter(|e| {
                    let method = string(e, "method");
                    match a {
                        "console" => method == "Runtime.consoleAPICalled",
                        "errors" => {
                            method == "Runtime.exceptionThrown" || method == "Network.loadingFailed"
                        }
                        "requests" | "network" => method.starts_with("Network."),
                        "download" => method.starts_with("Browser.download"),
                        _ => true,
                    }
                })
                .collect::<Vec<_>>();
            Ok(
                json!({"events":filtered.iter().skip(offset).take(limit).collect::<Vec<_>>(),"offset":offset,"total":filtered.len(),"hasMore":offset+limit<filtered.len(),"capacity":500,"traceKind":"bounded-cdp-events"}),
            )
        }
        "dialog" => {
            let op = string(p, "operation");
            if matches!(op, "list" | "get" | "") && p.get("accept").is_none() {
                let events = t.events.lock().unwrap();
                return Ok(
                    json!({"events":events.iter().filter(|e|string(e,"method").starts_with("Page.javascriptDialog")).collect::<Vec<_>>() }),
                );
            }
            if !matches!(op, "" | "handle" | "accept" | "dismiss") {
                return Err("INVALID_DIALOG_OPERATION".into());
            }
            cdp_for_tab(
                app,
                tab,
                "Page.handleJavaScriptDialog",
                json!({"accept":if op=="dismiss"{false}else{p.get("accept").and_then(Value::as_bool).unwrap_or(true)},"promptText":p.get("text").and_then(Value::as_str).unwrap_or("")}),
            )
        }
        "upload" => {
            let object = dom(app, tab, p, "object")?;
            let paths = p
                .get("paths")
                .or_else(|| p.get("files"))
                .and_then(Value::as_array)
                .filter(|v| !v.is_empty())
                .ok_or("upload requires approved local paths")?;
            let result = cdp_for_tab(
                app,
                tab,
                "DOM.setFileInputFiles",
                json!({"objectId":object["objectId"],"files":paths}),
            );
            let _ = cdp_for_tab(
                app,
                tab,
                "Runtime.releaseObject",
                json!({"objectId":object["objectId"]}),
            );
            result
        }
        "cookies" => {
            let op = string(p, "operation");
            if op == "clear" {
                return cdp_for_tab(app, tab, "Network.clearBrowserCookies", json!({}));
            }
            if matches!(op, "remove" | "delete") {
                if string(p, "key").is_empty() {
                    return Err("cookie removal requires key".into());
                }
                return cdp_for_tab(
                    app,
                    tab,
                    "Network.deleteCookies",
                    json!({"name":p["key"],"url":tab.url}),
                );
            }
            if matches!(op, "set" | "add") {
                if p.get("cookies").is_none() {
                    return Err("cookie set requires cookies array".into());
                }
                return cdp_for_tab(
                    app,
                    tab,
                    "Network.setCookies",
                    json!({"cookies":p["cookies"]}),
                );
            }
            if !matches!(op, "" | "get" | "list") {
                return Err("INVALID_COOKIE_OPERATION".into());
            }
            let mut value = cdp_for_tab(app, tab, "Network.getCookies", json!({"urls":[tab.url]}))?;
            if !p
                .get("includeValues")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                if let Some(cookies) = value["cookies"].as_array_mut() {
                    for cookie in cookies {
                        cookie["value"] = json!("[redacted]");
                    }
                }
            }
            Ok(value)
        }
        "storage" => {
            let kind = if string(p, "kind") == "session" {
                "sessionStorage"
            } else {
                "localStorage"
            };
            let op = string(p, "operation");
            let expression = match op {
                "set" | "add" => format!(
                    "{kind}.setItem({},{})",
                    js_string(string(p, "key")),
                    js_string(
                        &p.get("value")
                            .map(|v| v
                                .as_str()
                                .map(str::to_string)
                                .unwrap_or_else(|| v.to_string()))
                            .unwrap_or_default()
                    )
                ),
                "remove" | "delete" => {
                    format!("{kind}.removeItem({})", js_string(string(p, "key")))
                }
                "clear" => format!("{kind}.clear()"),
                "" | "get" | "list" => format!(
                    "Object.keys({kind}).map(key=>({{key,value:{}}}))",
                    if p.get("includeValues")
                        .and_then(Value::as_bool)
                        .unwrap_or(false)
                    {
                        format!("{kind}.getItem(key)")
                    } else {
                        "'[redacted]'".into()
                    }
                ),
                _ => return Err("INVALID_STORAGE_OPERATION".into()),
            };
            eval(app, tab, p, expression, false)
        }
        "show" | "hide" | "focus" | "workspace" => {
            let operation = if a == "workspace" {
                string(p, "operation")
            } else {
                a
            };
            if operation == "close" {
                return execute(app, broker, tab, p, t, g, "close_browser");
            }
            let mode = if matches!(operation, "hide" | "collapse") {
                "hidden"
            } else if operation == "preview" {
                "preview"
            } else {
                "visible"
            };
            *t.presentation.lock().unwrap() = mode.into();
            for activity in broker
                .agent
                .activities
                .lock()
                .unwrap()
                .values_mut()
                .filter(|a| a.tab_id == tab.tab_id)
            {
                activity.presentation = mode.into();
            }
            if let Some(activity) = broker
                .agent
                .activity
                .lock()
                .unwrap()
                .as_mut()
                .filter(|a| a.tab_id == tab.tab_id)
            {
                activity.presentation = mode.into();
            }
            let request_id = if string(p, "requestId").is_empty() {
                format!("view-{:016x}", rand::random::<u64>())
            } else {
                string(p, "requestId").to_string()
            };
            broker
                .agent
                .presentations
                .lock()
                .unwrap()
                .insert(request_id.clone(), None);
            let session = broker
                .agent
                .activities()
                .iter()
                .find(|a| a.tab_id == tab.tab_id)
                .map(|a| a.session_id.clone());
            app.emit("browser://presentation",json!({"requestId":request_id,"workspaceId":tab.workspace_id,"tabId":tab.tab_id,"sessionId":session,"mode":mode,"operation":operation})).map_err(|e|e.to_string())?;
            let deadline = Instant::now() + Duration::from_secs(2);
            let mut phase = "requested";
            while Instant::now() < deadline {
                if broker
                    .agent
                    .presentations
                    .lock()
                    .unwrap()
                    .get(&request_id)
                    .is_some_and(|value| value.is_some())
                {
                    phase = "accepted";
                    break;
                }
                std::thread::sleep(Duration::from_millis(40));
            }
            broker
                .agent
                .presentations
                .lock()
                .unwrap()
                .remove(&request_id);
            Ok(json!({"presentation":mode,"phase":phase,"workspaceId":tab.workspace_id}))
        }
        "close" | "close_tab" | "close_browser" | "close_all" => {
            let close = if matches!(a, "close_all" | "close_browser") {
                broker
                    .snapshot()
                    .tabs
                    .into_iter()
                    .filter(|candidate| candidate.workspace_id == tab.workspace_id)
                    .collect::<Vec<_>>()
            } else {
                vec![tab.clone()]
            };
            let ids = close.iter().map(|t| t.tab_id.clone()).collect::<Vec<_>>();
            for candidate in close {
                if let Some(view) = app.get_webview(&candidate.webview_label) {
                    view.close().map_err(|e| e.to_string())?;
                }
                broker.rollback_tab(&candidate.tab_id);
                broker.agent.closed(&candidate.tab_id);
            }
            if !broker
                .snapshot()
                .tabs
                .iter()
                .any(|t| t.workspace_id == tab.workspace_id)
            {
                let _ = app.emit(
                    "browser://workspace-closed",
                    json!({"workspaceId":tab.workspace_id}),
                );
            }
            Ok(json!({"closed":ids}))
        }
        _ => Err(format!("UNSUPPORTED_ACTION: {a}")),
    }
}

fn subscribe(app: &AppHandle, tab: &BrowserTab, target: Arc<Target>) -> Result<(), String> {
    if target.subscribed.swap(true, Ordering::AcqRel) {
        return Ok(());
    }
    #[cfg(windows)]
    {
        use webview2_com::{
            CallDevToolsProtocolMethodCompletedHandler, CoTaskMemPWSTR,
            DevToolsProtocolEventReceivedEventHandler,
        };
        use windows::core::HSTRING;
        let view = app.get_webview(&tab.webview_label).ok_or("TARGET_CLOSED")?;
        view.with_webview(move |platform| {
            if let Ok(core) = unsafe { platform.controller().CoreWebView2() } {
                for method in [
                    "Runtime.consoleAPICalled",
                    "Runtime.exceptionThrown",
                    "Network.requestWillBeSent",
                    "Network.responseReceived",
                    "Network.loadingFailed",
                    "Page.javascriptDialogOpening",
                    "Page.javascriptDialogClosed",
                    "Browser.downloadWillBegin",
                    "Browser.downloadProgress",
                ] {
                    if let Ok(receiver) =
                        unsafe { core.GetDevToolsProtocolEventReceiver(&HSTRING::from(method)) }
                    {
                        let store = target.clone();
                        let dialog_core=core.clone();
                        let handler = DevToolsProtocolEventReceivedEventHandler::create(Box::new(
                            move |_, args| {
                                if let Some(args) = args {
                                    let mut raw = windows::core::PWSTR::null();
                                    if unsafe { args.ParameterObjectAsJson(&mut raw) }.is_ok() {
                                        let owned = CoTaskMemPWSTR::from(raw);
                                        let value =
                                            serde_json::from_str::<Value>(&owned.to_string())
                                                .unwrap_or(Value::Null);
                                        // The triggering Input command can wait for JS to
                                        // finish. Resolve an explicitly expected dialog on
                                        // its event, before awaiting that Input response.
                                        if method=="Page.javascriptDialogOpening" {
                                            let expected=store.expected_dialog.lock().unwrap().take();
                                            if let Some((generation,params))=expected {
                                                if !store.paused.load(Ordering::Acquire)&&store.generation.load(Ordering::Acquire)==generation {
                                                    let callback=CallDevToolsProtocolMethodCompletedHandler::create(Box::new(|_,_|Ok(())));
                                                    let _=unsafe{dialog_core.CallDevToolsProtocolMethod(&HSTRING::from("Page.handleJavaScriptDialog"),&HSTRING::from(params.to_string()),&callback)};
                                                }
                                            }
                                        }
                                        let mut events = store.events.lock().unwrap();
                                        if events.len() == 500 {
                                            events.pop_front();
                                        }
                                        events.push_back(
                                            json!({"method":method,"params":sanitize_event(value)}),
                                        );
                                    }
                                }
                                Ok(())
                            },
                        ));
                        let mut token = 0i64;
                        let _ = unsafe {
                            receiver.add_DevToolsProtocolEventReceived(&handler, &mut token)
                        };
                    }
                }
            }
        })
        .map_err(|e| e.to_string())?;
        cdp_for_tab(app, tab, "Runtime.enable", json!({}))?;
        cdp_for_tab(
            app,
            tab,
            "Network.enable",
            json!({"maxTotalBufferSize":1048576,"maxResourceBufferSize":131072}),
        )?;
        cdp_for_tab(app, tab, "Page.enable", json!({}))?;
    }
    Ok(())
}
fn sanitize_event(mut value: Value) -> Value {
    // Network events may contain credentials and POST data. Never feed them to
    // the model or renderer as part of routine diagnostics.
    if let Some(request) = value.get_mut("request").and_then(Value::as_object_mut) {
        request.remove("postData");
        request.remove("headers");
    }
    if let Some(response) = value.get_mut("response").and_then(Value::as_object_mut) {
        response.remove("headers");
    }
    let encoded = value.to_string();
    if encoded.len() > 16000 {
        json!({"truncated":true,"summary":encoded.chars().take(4000).collect::<String>()})
    } else {
        value
    }
}

#[tauri::command]
pub fn browser_presentation_ack(broker: tauri::State<'_, BrowserBroker>, request_id: String) {
    if let Some(value) = broker
        .agent
        .presentations
        .lock()
        .unwrap()
        .get_mut(&request_id)
    {
        *value = Some("accepted".into());
    }
}

#[tauri::command]
pub async fn browser_agent_control(
    app: AppHandle,
    broker: tauri::State<'_, BrowserBroker>,
    tab_id: String,
    action: String,
) -> Result<Value, String> {
    if !matches!(action.as_str(), "pause" | "resume" | "stop") {
        return Err("invalid user control".into());
    }
    run(
        &app,
        &broker,
        json!({"tabId":tab_id,"action":action,"userControl":true}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn aliases() {
        assert_eq!(normalize("clickCoords"), "click_coords");
        assert_eq!(normalize("scrollIntoView"), "scroll_into_view");
        assert_eq!(normalize("double-click"), "double_click");
    }
    #[test]
    fn pause_fences_inflight() {
        let target = Target::default();
        let g = target.generation.load(Ordering::Acquire);
        assert!(check(&target, g).is_ok());
        target.generation.fetch_add(1, Ordering::AcqRel);
        assert!(check(&target, g).unwrap_err().contains("CANCELLED"));
    }
    #[test]
    fn redacts_network() {
        let event = sanitize_event(
            json!({"request":{"headers":{"Cookie":"secret"},"postData":"private","url":"https://example.org"}}),
        );
        assert!(event["request"].get("headers").is_none());
        assert!(event["request"].get("postData").is_none());
    }
}
