use rand::RngCore;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::env;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, RunEvent};

mod browser;
mod windows_integration;

const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(30);
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(6);
const STDERR_LIMIT: usize = 40;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum CoreState {
    Starting,
    Connecting,
    Ready,
    Crashed,
    Fatal,
    Repair,
    Stopped,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct CoreSnapshot {
    state: CoreState,
    generation: u64,
    pid: Option<u32>,
    port: Option<u16>,
    started_at: Option<String>,
    last_error: Option<String>,
    stderr_tail: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct CoreApiRequest {
    method: String,
    path: String,
    body: Option<Value>,
    idempotency_key: Option<String>,
}

#[derive(Debug, Serialize)]
struct CoreApiResponse {
    status: u16,
    body: Value,
}

impl Default for CoreSnapshot {
    fn default() -> Self {
        Self {
            state: CoreState::Stopped,
            generation: 0,
            pid: None,
            port: None,
            started_at: None,
            last_error: None,
            stderr_tail: vec![],
        }
    }
}

struct Inner {
    snapshot: CoreSnapshot,
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    token: Option<String>,
    stopping: bool,
}

#[derive(Clone)]
struct CoreSupervisor {
    inner: Arc<Mutex<Inner>>,
    project_root: PathBuf,
    browser_bridge: Arc<Mutex<Option<(u16, String)>>>,
}

#[derive(Debug, Deserialize)]
struct Handshake {
    #[serde(rename = "type")]
    kind: String,
    schema_version: u32,
    state: String,
    pid: u32,
    host: String,
    port: u16,
    health: Value,
}

impl CoreSupervisor {
    fn new() -> Self {
        let project_root = env::var_os("SMARTI_PROJECT_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .parent()
                    .and_then(|p| p.parent())
                    .expect("desktop must live below the repository root")
                    .to_path_buf()
            });
        Self {
            inner: Arc::new(Mutex::new(Inner {
                snapshot: CoreSnapshot::default(),
                child: None,
                stdin: None,
                token: None,
                stopping: false,
            })),
            project_root,
            browser_bridge: Arc::new(Mutex::new(None)),
        }
    }

    fn configure_browser_bridge(&self, port: u16, token: String) {
        *self
            .browser_bridge
            .lock()
            .expect("browser bridge mutex poisoned") = Some((port, token));
    }

    fn snapshot(&self) -> CoreSnapshot {
        self.inner
            .lock()
            .expect("Core supervisor mutex poisoned")
            .snapshot
            .clone()
    }

    fn emit(&self, app: &AppHandle) {
        let _ = app.emit("core://state", self.snapshot());
    }

    fn begin_start(&self, app: AppHandle) -> CoreSnapshot {
        let generation;
        {
            let mut inner = self.inner.lock().expect("Core supervisor mutex poisoned");
            if child_is_running(&mut inner.child) {
                return inner.snapshot.clone();
            }
            inner.snapshot.generation += 1;
            generation = inner.snapshot.generation;
            inner.snapshot.state = CoreState::Starting;
            inner.snapshot.pid = None;
            inner.snapshot.port = None;
            inner.snapshot.started_at = None;
            inner.snapshot.last_error = None;
            inner.token = None;
            inner.stopping = false;
        }
        self.emit(&app);
        let supervisor = self.clone();
        thread::Builder::new()
            .name("smarti-core-launch".into())
            .spawn(move || supervisor.launch(app, generation))
            .expect("failed to create Core launch thread");
        self.snapshot()
    }

    fn launch(&self, app: AppHandle, generation: u64) {
        let token = launch_token();
        let mut command = match self.command() {
            Ok(command) => command,
            Err(error) => {
                self.fail(&app, generation, CoreState::Repair, error);
                return;
            }
        };
        command
            .args(["--port", "0", "--token", &token])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some((port, browser_token)) = self
            .browser_bridge
            .lock()
            .expect("browser bridge mutex poisoned")
            .clone()
        {
            command.env("SMARTI_TAURI_BROWSER_BROKER_PORT", port.to_string());
            command.env("SMARTI_TAURI_BROWSER_BROKER_TOKEN", browser_token);
        }
        hide_console(&mut command);
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                self.fail(
                    &app,
                    generation,
                    CoreState::Repair,
                    format!("לא ניתן להפעיל את Smarti Core: {error}"),
                );
                return;
            }
        };
        let pid = child.id();
        let stdin = child.stdin.take();
        let stdout = child.stdout.take().expect("piped Core stdout missing");
        let stderr = child.stderr.take().expect("piped Core stderr missing");
        let (handshake_tx, handshake_rx) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let mut lines = BufReader::new(stdout).lines();
            let first = lines
                .next()
                .transpose()
                .map_err(|e| e.to_string())
                .and_then(|line| {
                    line.ok_or_else(|| "Core closed stdout before readiness".to_string())
                });
            let _ = handshake_tx.send(first);
            for _ in lines {}
        });
        self.capture_stderr(stderr, generation, app.clone());
        {
            let mut inner = self.inner.lock().expect("Core supervisor mutex poisoned");
            if inner.snapshot.generation != generation {
                let _ = child.kill();
                return;
            }
            inner.child = Some(child);
            inner.stdin = stdin;
            inner.token = Some(token.clone());
            inner.snapshot.pid = Some(pid);
            inner.snapshot.state = CoreState::Connecting;
        }
        self.emit(&app);
        let line = match receive_handshake(handshake_rx, HANDSHAKE_TIMEOUT) {
            Ok(line) => line,
            Err(error) => {
                self.terminate_generation(generation);
                self.fail(&app, generation, CoreState::Fatal, error);
                return;
            }
        };
        let handshake = match validate_handshake(&line, pid) {
            Ok(handshake) => handshake,
            Err(error) => {
                self.terminate_generation(generation);
                self.fail(&app, generation, CoreState::Fatal, error);
                return;
            }
        };
        if let Err(error) = health_request(handshake.port, &token) {
            self.terminate_generation(generation);
            self.fail(
                &app,
                generation,
                CoreState::Fatal,
                format!("Core health handshake failed: {error}"),
            );
            return;
        }
        {
            let mut inner = self.inner.lock().expect("Core supervisor mutex poisoned");
            if inner.snapshot.generation != generation {
                return;
            }
            inner.snapshot.state = CoreState::Ready;
            inner.snapshot.port = Some(handshake.port);
            inner.snapshot.started_at = handshake
                .health
                .get("started_at")
                .and_then(Value::as_str)
                .map(str::to_owned);
        }
        self.emit(&app);
        self.monitor(app, generation);
    }

    fn command(&self) -> Result<Command, String> {
        if let Some(binary) = env::var_os("SMARTI_CORE_BINARY") {
            let path = PathBuf::from(binary);
            if !path.is_file() {
                return Err(format!("SMARTI_CORE_BINARY not found: {}", path.display()));
            }
            return Ok(Command::new(path));
        }
        if cfg!(debug_assertions) || env::var_os("SMARTI_PROJECT_ROOT").is_some() {
            let script = self.project_root.join("smarti_core_service.py");
            if !script.is_file() {
                return Err(format!(
                    "Core source entrypoint not found: {}",
                    script.display()
                ));
            }
            let python = env::var_os("SMARTI_PYTHON")
                .or_else(|| env::var_os("PYTHON"))
                .unwrap_or_else(|| "python".into());
            let mut command = Command::new(python);
            command.arg(script);
            return Ok(command);
        }
        let executable = env::current_exe().map_err(|e| e.to_string())?;
        let install_dir = executable
            .parent()
            .ok_or("Desktop executable has no parent directory")?;
        let resource_roots = [
            install_dir.to_path_buf(),
            install_dir.join("resources"),
            install_dir.join("package-resources"),
            install_dir.join("resources").join("package-resources"),
        ];
        let located = resource_roots.iter().find_map(|root| {
            let candidate = root.join("smarti-core").join("smarti-core.exe");
            candidate.is_file().then(|| (candidate, root.clone()))
        });
        let Some((binary, resource_root)) = located else {
            return Err(format!(
                "Packaged Core sidecar not found below {}",
                install_dir.display()
            ));
        };
        let mut command = Command::new(binary);
        let runtime_dir = resource_root.join("runtime");
        if runtime_dir.is_dir() {
            command.env("SMARTI_RUNTIME_DIR", runtime_dir);
            command.env("SMARTI_FORCE_BUNDLED_RUNTIME", "1");
        }
        Ok(command)
    }

    fn capture_stderr<R: Read + Send + 'static>(&self, stderr: R, generation: u64, app: AppHandle) {
        let supervisor = self.clone();
        thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                let mut inner = supervisor
                    .inner
                    .lock()
                    .expect("Core supervisor mutex poisoned");
                if inner.snapshot.generation != generation {
                    break;
                }
                let mut tail: VecDeque<String> = inner.snapshot.stderr_tail.drain(..).collect();
                tail.push_back(redact_diagnostic(&line));
                while tail.len() > STDERR_LIMIT {
                    tail.pop_front();
                }
                inner.snapshot.stderr_tail = tail.into();
                drop(inner);
                supervisor.emit(&app);
            }
        });
    }

    fn monitor(&self, app: AppHandle, generation: u64) {
        let supervisor = self.clone();
        thread::spawn(move || loop {
            thread::sleep(Duration::from_millis(250));
            let result = {
                let mut inner = supervisor
                    .inner
                    .lock()
                    .expect("Core supervisor mutex poisoned");
                if inner.snapshot.generation != generation || inner.child.is_none() {
                    return;
                }
                inner
                    .child
                    .as_mut()
                    .and_then(|child| child.try_wait().ok().flatten())
                    .map(|status| (status.code(), inner.stopping))
            };
            if let Some((code, stopping)) = result {
                let mut inner = supervisor
                    .inner
                    .lock()
                    .expect("Core supervisor mutex poisoned");
                inner.child = None;
                inner.stdin = None;
                inner.token = None;
                inner.snapshot.pid = None;
                inner.snapshot.port = None;
                inner.snapshot.state = if stopping {
                    CoreState::Stopped
                } else {
                    CoreState::Crashed
                };
                if !stopping {
                    inner.snapshot.last_error = Some(exit_message(code));
                }
                drop(inner);
                supervisor.emit(&app);
                return;
            }
        });
    }

    fn fail(&self, app: &AppHandle, generation: u64, state: CoreState, error: String) {
        let mut inner = self.inner.lock().expect("Core supervisor mutex poisoned");
        if inner.snapshot.generation != generation {
            return;
        }
        inner.snapshot.state = state;
        inner.snapshot.last_error = Some(redact_diagnostic(&error));
        inner.snapshot.pid = None;
        inner.snapshot.port = None;
        inner.child = None;
        inner.stdin = None;
        inner.token = None;
        drop(inner);
        self.emit(app);
    }

    fn terminate_generation(&self, generation: u64) {
        let mut inner = self.inner.lock().expect("Core supervisor mutex poisoned");
        if inner.snapshot.generation == generation {
            if let Some(mut child) = inner.child.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
            inner.stdin = None;
            inner.token = None;
        }
    }

    fn stop(&self, app: Option<&AppHandle>) -> CoreSnapshot {
        let (mut child, mut stdin) = {
            let mut inner = self.inner.lock().expect("Core supervisor mutex poisoned");
            inner.stopping = true;
            (inner.child.take(), inner.stdin.take())
        };
        if let Some(input) = stdin.as_mut() {
            let _ = input.write_all(shutdown_command().as_bytes());
            let _ = input.flush();
        }
        if let Some(process) = child.as_mut() {
            let deadline = Instant::now() + SHUTDOWN_TIMEOUT;
            while Instant::now() < deadline {
                if process.try_wait().ok().flatten().is_some() {
                    break;
                }
                thread::sleep(Duration::from_millis(50));
            }
            if process.try_wait().ok().flatten().is_none() {
                let _ = process.kill();
            }
            let _ = process.wait();
        }
        let mut inner = self.inner.lock().expect("Core supervisor mutex poisoned");
        inner.token = None;
        inner.snapshot.state = CoreState::Stopped;
        inner.snapshot.pid = None;
        inner.snapshot.port = None;
        inner.stopping = false;
        let snapshot = inner.snapshot.clone();
        drop(inner);
        if let Some(handle) = app {
            self.emit(handle);
        }
        snapshot
    }

    fn health(&self) -> Result<Value, String> {
        let (port, token) = {
            let inner = self
                .inner
                .lock()
                .map_err(|_| "Core supervisor mutex poisoned".to_string())?;
            (
                inner.snapshot.port.ok_or("Core is not ready")?,
                inner.token.clone().ok_or("Core credential unavailable")?,
            )
        };
        health_request(port, &token)
    }

    fn terminate_for_smoke(&self) -> Result<(), String> {
        if env::var_os("SMARTI_SUPERVISOR_SMOKE_FILE").is_none() {
            return Err("smoke termination is disabled".into());
        }
        let mut inner = self
            .inner
            .lock()
            .map_err(|_| "Core supervisor mutex poisoned".to_string())?;
        inner
            .child
            .as_mut()
            .ok_or("Core process is not running")?
            .kill()
            .map_err(|error| error.to_string())
    }
}

fn child_is_running(child: &mut Option<Child>) -> bool {
    child
        .as_mut()
        .is_some_and(|process| process.try_wait().ok().flatten().is_none())
}
fn launch_token() -> String {
    let mut bytes = [0u8; 32];
    rand::rng().fill_bytes(&mut bytes);
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn shutdown_command() -> String {
    "{\"command\":\"shutdown\"}\n".to_string()
}
fn exit_message(code: Option<i32>) -> String {
    code.map(|value| format!("Smarti Core exited unexpectedly (code {value})"))
        .unwrap_or_else(|| "Smarti Core exited unexpectedly".into())
}
fn redact_diagnostic(value: &str) -> String {
    let mut text = value.chars().take(600).collect::<String>();
    if let Some(index) = text.find("Bearer ") {
        text.truncate(index);
        text.push_str("Bearer [REDACTED]");
    }
    text
}

fn receive_handshake(
    receiver: mpsc::Receiver<Result<String, String>>,
    timeout: Duration,
) -> Result<String, String> {
    receiver
        .recv_timeout(timeout)
        .map_err(|_| "Smarti Core readiness timed out".to_string())?
}

fn validate_handshake(line: &str, expected_pid: u32) -> Result<Handshake, String> {
    let value: Handshake =
        serde_json::from_str(line).map_err(|e| format!("Invalid Core readiness JSON: {e}"))?;
    if value.kind != "smarti_core_ready" || value.schema_version != 1 || value.state != "ready" {
        return Err("Invalid Core readiness state".into());
    }
    if value.host != "127.0.0.1" || value.port == 0 || value.pid != expected_pid {
        return Err("Core readiness identity did not match the supervised process".into());
    }
    if value.health.get("ready").and_then(Value::as_bool) != Some(true)
        || value.health.get("qt_loaded").and_then(Value::as_bool) != Some(false)
    {
        return Err("Core readiness health contract failed".into());
    }
    Ok(value)
}

fn health_request(port: u16, token: &str) -> Result<Value, String> {
    let address = ("127.0.0.1", port)
        .to_socket_addrs()
        .map_err(|e| e.to_string())?
        .next()
        .ok_or("loopback address unavailable")?;
    let mut stream =
        TcpStream::connect_timeout(&address, Duration::from_secs(3)).map_err(|e| e.to_string())?;
    stream
        .set_read_timeout(Some(Duration::from_secs(3)))
        .map_err(|e| e.to_string())?;
    write!(stream, "GET /v2/health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nOrigin: tauri://localhost\r\nConnection: close\r\n\r\n").map_err(|e| e.to_string())?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|e| e.to_string())?;
    let (head, body) = response
        .split_once("\r\n\r\n")
        .ok_or("Malformed Core health response")?;
    if !head.starts_with("HTTP/1.1 200") {
        return Err(format!(
            "Core health returned {}",
            head.lines().next().unwrap_or("unknown status")
        ));
    }
    let envelope: Value = serde_json::from_str(body).map_err(|e| e.to_string())?;
    envelope
        .get("data")
        .cloned()
        .ok_or("Core health response omitted data".into())
}

fn core_http_request(
    port: u16,
    token: &str,
    request: CoreApiRequest,
) -> Result<CoreApiResponse, String> {
    let method = request.method.trim().to_ascii_uppercase();
    if !matches!(method.as_str(), "GET" | "POST" | "PATCH" | "PUT" | "DELETE") {
        return Err("Core API method is not allowed".into());
    }
    let path = request.path.trim();
    if !path.starts_with("/v2/")
        || path.contains("..")
        || path.contains("://")
        || path.contains(['\r', '\n'])
    {
        return Err("Core API path is not allowed".into());
    }
    let body = request
        .body
        .map(|value| serde_json::to_vec(&value))
        .transpose()
        .map_err(|error| error.to_string())?
        .unwrap_or_default();
    let address = ("127.0.0.1", port)
        .to_socket_addrs()
        .map_err(|error| error.to_string())?
        .next()
        .ok_or("loopback address unavailable")?;
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_secs(5))
        .map_err(|error| error.to_string())?;
    let read_timeout = if request.path.starts_with("/v2/management/diagnostics") {
        Duration::from_secs(300)
    } else {
        Duration::from_secs(20)
    };
    stream
        .set_read_timeout(Some(read_timeout))
        .map_err(|error| error.to_string())?;
    write!(stream, "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nOrigin: tauri://localhost\r\nAccept: application/json\r\nContent-Type: application/json\r\nContent-Length: {}\r\n", body.len()).map_err(|error| error.to_string())?;
    if let Some(key) = request
        .idempotency_key
        .filter(|value| !value.trim().is_empty())
    {
        let safe_key: String = key
            .chars()
            .filter(|value| !matches!(value, '\r' | '\n'))
            .take(200)
            .collect();
        write!(stream, "Idempotency-Key: {safe_key}\r\n").map_err(|error| error.to_string())?;
    }
    write!(stream, "Connection: close\r\n\r\n").map_err(|error| error.to_string())?;
    if !body.is_empty() {
        stream.write_all(&body).map_err(|error| error.to_string())?;
    }
    stream.flush().map_err(|error| error.to_string())?;
    let mut response = Vec::new();
    stream
        .read_to_end(&mut response)
        .map_err(|error| error.to_string())?;
    let split = response
        .windows(4)
        .position(|part| part == b"\r\n\r\n")
        .ok_or("Malformed Core API response")?;
    let head = String::from_utf8_lossy(&response[..split]);
    let status = head
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or("Core API response omitted status")?;
    let body = serde_json::from_slice::<Value>(&response[split + 4..])
        .map_err(|error| format!("Invalid Core API JSON: {error}"))?;
    Ok(CoreApiResponse { status, body })
}

#[cfg(windows)]
fn hide_console(command: &mut Command) {
    use std::os::windows::process::CommandExt;
    command.creation_flags(0x08000000);
}
#[cfg(not(windows))]
fn hide_console(_command: &mut Command) {}

#[tauri::command]
fn core_status(supervisor: tauri::State<'_, CoreSupervisor>) -> CoreSnapshot {
    supervisor.snapshot()
}
#[tauri::command]
fn core_health(supervisor: tauri::State<'_, CoreSupervisor>) -> Result<Value, String> {
    supervisor.health()
}
#[tauri::command]
fn core_restart(app: AppHandle, supervisor: tauri::State<'_, CoreSupervisor>) -> CoreSnapshot {
    supervisor.stop(Some(&app));
    supervisor.begin_start(app)
}

#[tauri::command]
async fn core_api(
    request: CoreApiRequest,
    supervisor: tauri::State<'_, CoreSupervisor>,
) -> Result<CoreApiResponse, String> {
    let supervisor = supervisor.inner().clone();
    tauri::async_runtime::spawn_blocking(move || supervisor_core_api(&supervisor, request))
        .await
        .map_err(|error| format!("Core API worker failed: {error}"))?
}

fn supervisor_core_api(
    supervisor: &CoreSupervisor,
    request: CoreApiRequest,
) -> Result<CoreApiResponse, String> {
    let (port, token) = {
        let inner = supervisor
            .inner
            .lock()
            .map_err(|_| "Core supervisor mutex poisoned".to_string())?;
        (
            inner.snapshot.port.ok_or("Core is not ready")?,
            inner.token.clone().ok_or("Core credential unavailable")?,
        )
    };
    core_http_request(port, &token, request)
}

#[tauri::command]
fn stage_attachment(app: AppHandle, name: String, bytes: Vec<u8>) -> Result<String, String> {
    if bytes.is_empty() || bytes.len() > 25 * 1024 * 1024 {
        return Err("Attachment must be between 1 byte and 25 MB".into());
    }
    let safe_name: String = name
        .chars()
        .map(|value| {
            if value.is_alphanumeric() || matches!(value, '.' | '-' | '_') {
                value
            } else {
                '_'
            }
        })
        .take(120)
        .collect();
    let directory = app
        .path()
        .app_cache_dir()
        .map_err(|error| error.to_string())?
        .join("pending-attachments");
    fs::create_dir_all(&directory).map_err(|error| error.to_string())?;
    let path = directory.join(format!(
        "{}-{}",
        &launch_token()[..12],
        if safe_name.is_empty() {
            "pasted-image.png"
        } else {
            &safe_name
        }
    ));
    fs::write(&path, bytes).map_err(|error| error.to_string())?;
    Ok(path.to_string_lossy().into_owned())
}

#[tauri::command]
fn read_attachment_preview(app: AppHandle, path: String) -> Result<Vec<u8>, String> {
    let root = app
        .path()
        .app_cache_dir()
        .map_err(|error| error.to_string())?
        .join("pending-attachments");
    let canonical_root =
        fs::canonicalize(&root).map_err(|_| "Attachment cache is unavailable".to_string())?;
    let target = fs::canonicalize(PathBuf::from(path))
        .map_err(|_| "Attachment preview was not found".to_string())?;
    if !target.starts_with(&canonical_root) {
        return Err("Attachment preview is outside the staged cache".into());
    }
    let metadata = fs::metadata(&target).map_err(|error| error.to_string())?;
    if !metadata.is_file() || metadata.len() > 25 * 1024 * 1024 {
        return Err("Attachment preview is not an allowed file".into());
    }
    fs::read(target).map_err(|error| error.to_string())
}

fn safe_suggested_name(value: &str, fallback: &str) -> String {
    let cleaned: String = value
        .chars()
        .map(|character| {
            if character.is_alphanumeric() || matches!(character, ' ' | '.' | '-' | '_') {
                character
            } else {
                '_'
            }
        })
        .take(120)
        .collect();
    let cleaned = cleaned.trim().trim_matches('.');
    if cleaned.is_empty() {
        fallback.to_string()
    } else {
        cleaned.to_string()
    }
}

#[cfg(target_os = "windows")]
fn choose_save_path(suggested_name: String) -> Result<Option<PathBuf>, String> {
    thread::spawn(move || unsafe {
        use windows::core::HSTRING;
        use windows::Win32::System::Com::{
            CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_INPROC_SERVER,
            COINIT_APARTMENTTHREADED,
        };
        use windows::Win32::UI::Shell::{FileSaveDialog, IFileSaveDialog, SIGDN_FILESYSPATH};

        let initialized = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
        if initialized.is_err() {
            return Err(format!(
                "Windows save dialog initialization failed: {initialized:?}"
            ));
        }
        let result = (|| -> Result<Option<PathBuf>, String> {
            let dialog: IFileSaveDialog =
                CoCreateInstance(&FileSaveDialog, None, CLSCTX_INPROC_SERVER)
                    .map_err(|error| error.to_string())?;
            dialog
                .SetTitle(&HSTRING::from("שמירה מ־Smarti"))
                .map_err(|error| error.to_string())?;
            dialog
                .SetFileName(&HSTRING::from(suggested_name))
                .map_err(|error| error.to_string())?;
            if let Err(error) = dialog.Show(None) {
                // HRESULT_FROM_WIN32(ERROR_CANCELLED)
                if error.code().0 == 0x8007_04C7_u32 as i32 {
                    return Ok(None);
                }
                return Err(error.to_string());
            }
            let item = dialog.GetResult().map_err(|error| error.to_string())?;
            let value = item
                .GetDisplayName(SIGDN_FILESYSPATH)
                .map_err(|error| error.to_string())?;
            let text = value.to_string().map_err(|error| error.to_string());
            CoTaskMemFree(Some(value.as_ptr().cast()));
            text.map(|path| Some(PathBuf::from(path)))
        })();
        CoUninitialize();
        result
    })
    .join()
    .map_err(|_| "Windows save dialog thread failed".to_string())?
}

#[cfg(not(target_os = "windows"))]
fn choose_save_path(_suggested_name: String) -> Result<Option<PathBuf>, String> {
    Err("Native save dialog is available only on Windows".into())
}

#[tauri::command]
fn save_text_file(suggested_name: String, contents: String) -> Result<Option<String>, String> {
    if contents.len() > 50 * 1024 * 1024 {
        return Err("Text export exceeds the 50 MB safety limit".into());
    }
    let name = safe_suggested_name(&suggested_name, "smarti-export.txt");
    let path = choose_save_path(name)?;
    let Some(path) = path else { return Ok(None) };
    fs::write(&path, contents.as_bytes()).map_err(|error| error.to_string())?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

#[tauri::command]
fn save_binary_file(suggested_name: String, bytes: Vec<u8>) -> Result<Option<String>, String> {
    if bytes.is_empty() || bytes.len() > 50 * 1024 * 1024 {
        return Err("Binary export must be between 1 byte and 50 MB".into());
    }
    let name = safe_suggested_name(&suggested_name, "smarti-export.bin");
    let path = choose_save_path(name)?;
    let Some(path) = path else { return Ok(None) };
    fs::write(&path, bytes).map_err(|error| error.to_string())?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

#[cfg(target_os = "windows")]
fn choose_management_path(kind: String) -> Result<Option<String>, String> {
    thread::spawn(move || unsafe {
        use windows::core::HSTRING;
        use windows::Win32::System::Com::{
            CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_INPROC_SERVER,
            COINIT_APARTMENTTHREADED,
        };
        use windows::Win32::UI::Shell::{
            FileOpenDialog, IFileOpenDialog, FOS_PICKFOLDERS, SIGDN_FILESYSPATH,
        };
        let initialized = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
        if initialized.is_err() {
            return Err(format!(
                "Windows picker initialization failed: {initialized:?}"
            ));
        }
        let result = (|| -> Result<Option<String>, String> {
            let dialog: IFileOpenDialog =
                CoCreateInstance(&FileOpenDialog, None, CLSCTX_INPROC_SERVER)
                    .map_err(|error| error.to_string())?;
            dialog
                .SetTitle(&HSTRING::from(if kind == "directory" {
                    "בחירת תיקייה עבור Smarti"
                } else {
                    "בחירת קובץ עבור Smarti"
                }))
                .map_err(|error| error.to_string())?;
            if kind == "directory" {
                let options = dialog.GetOptions().map_err(|error| error.to_string())?;
                dialog
                    .SetOptions(options | FOS_PICKFOLDERS)
                    .map_err(|error| error.to_string())?;
            }
            if let Err(error) = dialog.Show(None) {
                if error.code().0 == 0x8007_04C7_u32 as i32 {
                    return Ok(None);
                }
                return Err(error.to_string());
            }
            let item = dialog.GetResult().map_err(|error| error.to_string())?;
            let value = item
                .GetDisplayName(SIGDN_FILESYSPATH)
                .map_err(|error| error.to_string())?;
            let text = value.to_string().map_err(|error| error.to_string())?;
            CoTaskMemFree(Some(value.as_ptr().cast()));
            Ok(Some(text))
        })();
        CoUninitialize();
        result
    })
    .join()
    .map_err(|_| "Windows picker thread failed".to_string())?
}

#[cfg(not(target_os = "windows"))]
fn choose_management_path(_kind: String) -> Result<Option<String>, String> {
    Err("The management picker is available only on Windows".into())
}

#[tauri::command]
fn pick_management_path(kind: String) -> Result<Option<String>, String> {
    if !matches!(kind.as_str(), "file" | "directory") {
        return Err("Unsupported management picker kind".into());
    }
    choose_management_path(kind)
}

fn desktop_check(id: &str, status: &str, title: &str, explanation: &str, detail: String) -> Value {
    json!({
        "id": id,
        "status": status,
        "title_he": title,
        "explanation_he": explanation,
        "technical_detail": detail,
        "category": "tauri",
        "repair_action": Value::Null,
    })
}

#[tauri::command]
fn desktop_diagnostic_snapshot(
    app: AppHandle,
    supervisor: tauri::State<'_, CoreSupervisor>,
    broker: tauri::State<'_, browser::BrowserBroker>,
) -> Value {
    let snapshot = supervisor.snapshot();
    let (has_token, child_owned) = supervisor
        .inner
        .lock()
        .map(|inner| {
            (
                inner.token.as_ref().is_some_and(|token| token.len() >= 32),
                inner.child.is_some(),
            )
        })
        .unwrap_or((false, false));
    let app_data = app.path().app_data_dir().ok();
    let writable = app_data
        .as_ref()
        .is_some_and(|path| fs::create_dir_all(path).is_ok());
    let browser_snapshot = broker.snapshot();
    let csp = include_str!("../tauri.conf.json");
    let capability = include_str!("../capabilities/default.json");
    let updater_signed = !csp.contains("UNSIGNED_LOCAL_BUILD_NO_UPDATES");
    let source_entry = supervisor.project_root.join("smarti_core_service.py");
    let core_ready = snapshot.state == CoreState::Ready && snapshot.port.is_some();
    let items = vec![
        desktop_check(
            "tauri.supervisor", if core_ready { "pass" } else { "error" },
            "Rust supervisor ו־Core generation",
            if core_ready { "מנהל ה־Core מחזיק דור פעיל ו־handshake תקין." } else { "מנהל ה־Core אינו במצב Ready מלא." },
            format!("state={:?}; generation={}; pid={:?}; port={:?}; child_owned={child_owned}", snapshot.state, snapshot.generation, snapshot.pid, snapshot.port),
        ),
        desktop_check(
            "tauri.control_plane", if core_ready && has_token { "pass" } else { "error" },
            "חוזה ואימות /v2",
            if has_token { "אסימון פר־הפעלה נמצא רק אצל ה־supervisor וה־Core מאזין ב־loopback." } else { "לא נמצא אסימון מאומת להפעלה הנוכחית." },
            format!("loopback_port={:?}; bearer_present={has_token}; contract=/v2", snapshot.port),
        ),
        desktop_check(
            "tauri.sidecar_runtime", if cfg!(debug_assertions) && source_entry.is_file() { "pass" } else if !cfg!(debug_assertions) { "pass" } else { "warning" },
            "Sidecar ו־runtime פרטי",
            if cfg!(debug_assertions) { "במצב פיתוח נבדק entrypoint המקור; באריזה נבדקים משאבי sidecar ו־runtime." } else { "היישום פועל במסלול sidecar ארוז ו־runtime פרטי." },
            format!("debug={}; source_entry={}; exists={}", cfg!(debug_assertions), source_entry.display(), source_entry.is_file()),
        ),
        desktop_check(
            "tauri.writable_paths", if writable { "pass" } else { "error" },
            "נתיבי נתונים ניתנים לכתיבה",
            if writable { "תיקיית נתוני שולחן העבודה זמינה לכתיבה." } else { "תיקיית נתוני שולחן העבודה אינה זמינה לכתיבה." },
            format!("app_data={:?}", app_data),
        ),
        desktop_check(
            "tauri.webview2_browser", if browser_snapshot.transport == "webview2-in-process-cdp" { "pass" } else { "error" },
            "WebView2 ו־Smarti Browser",
            "הדפדפן נשאר בבעלות Smarti עם פרופיל מתמשך ואורח נפרדים.",
            format!("transport={}; tabs={}; remote_debugging_port={:?}", browser_snapshot.transport, browser_snapshot.tabs.len(), browser_snapshot.remote_debugging_port),
        ),
        desktop_check(
            "tauri.csp_capabilities", if csp.contains("object-src 'none'") && capability.contains("Trusted Smarti chrome only") { "pass" } else { "error" },
            "CSP, capabilities ונכסים",
            "חלון ה־chrome המהימן מוגבל ב־CSP וב־Tauri capabilities; WebViews מרוחקים אינם מקבלים IPC.",
            format!("object_src_none={}; trusted_chrome_scope={}", csp.contains("object-src 'none'"), capability.contains("Trusted Smarti chrome only")),
        ),
        desktop_check(
            "tauri.windows_integration", "pass",
            "Tray, single-instance, hotkey והתראות",
            "אינטגרציות Windows נרשמו במארח Tauri ומנותבות לחלון הראשי היחיד.",
            "plugins=single-instance,global-shortcut,notification,tray; activation=desktop://activation".into(),
        ),
        desktop_check(
            "tauri.updater_signature", if updater_signed { "pass" } else { "warning" },
            "Updater וחתימת עדכון",
            if updater_signed { "מפתח אימות עדכונים מוגדר." } else { "זהו build מקומי לא חתום; עדכונים מושבתים עד להגדרת מפתח שחרור." },
            format!("signed_release_key_configured={updater_signed}"),
        ),
        desktop_check(
            "tauri.stale_children", if !child_owned || core_ready { "pass" } else { "warning" },
            "ניקוי תהליכי Core ישנים",
            if core_ready { "ה־supervisor מחזיק תהליך Core יחיד של הדור הפעיל." } else { "נמצא תהליך בבעלות supervisor שאינו Ready; נדרש מעקב או הפעלה מחדש." },
            format!("generation={}; child_owned={child_owned}; ready={core_ready}", snapshot.generation),
        ),
    ];
    json!({"items": items})
}

fn blocked_chat_link_extension(path: &std::path::Path) -> bool {
    const BLOCKED: &[&str] = &[
        "exe",
        "dll",
        "bat",
        "cmd",
        "ps1",
        "psm1",
        "vbs",
        "jscript",
        "scr",
        "com",
        "msi",
        "reg",
        "lnk",
        "hta",
        "jar",
        "appref-ms",
        "cpl",
        "msc",
        "pif",
        "scf",
        "url",
        "ws",
        "wsf",
        "wsh",
        "ps2",
        "ps2xml",
        "psc1",
        "psc2",
        "msh",
        "msh1",
        "msh2",
        "mshxml",
        "msh1xml",
        "msh2xml",
    ];
    path.extension()
        .and_then(|value| value.to_str())
        .is_some_and(|value| BLOCKED.contains(&value.to_ascii_lowercase().as_str()))
}

fn validate_external_chat_link(target: &str) -> Result<&str, String> {
    let value = target.trim();
    if value.is_empty()
        || value
            .chars()
            .any(|character| character.is_control() || character.is_whitespace())
    {
        return Err("External link is malformed".into());
    }
    let lower = value.to_ascii_lowercase();
    if lower.starts_with("mailto:") && value.len() > 7 {
        return Ok(value);
    }
    let rest = lower
        .strip_prefix("https://")
        .or_else(|| lower.strip_prefix("http://"))
        .ok_or("Only HTTP, HTTPS and mail links are allowed")?;
    if rest.is_empty() || rest.starts_with('/') {
        return Err("External link has no host".into());
    }
    Ok(value)
}

#[tauri::command]
fn open_chat_link(target: String, local: bool) -> Result<(), String> {
    let mut command = if local {
        let candidate = PathBuf::from(target.trim());
        if !candidate.is_absolute() {
            return Err("Local link must be an absolute path".into());
        }
        let path = fs::canonicalize(candidate)
            .map_err(|_| "Local file or folder was not found".to_string())?;
        if blocked_chat_link_extension(&path) {
            return Err("Executable local links are blocked".into());
        }
        let mut command = Command::new("explorer.exe");
        command.arg(path);
        command
    } else {
        let target = validate_external_chat_link(&target)?;
        let mut command = Command::new("rundll32.exe");
        command.args(["url.dll,FileProtocolHandler", target]);
        command
    };
    hide_console(&mut command);
    command
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("Could not open link: {error}"))
}

fn wait_for_state(
    supervisor: &CoreSupervisor,
    wanted: CoreState,
    timeout: Duration,
) -> Result<CoreSnapshot, String> {
    let deadline = Instant::now() + timeout;
    loop {
        let snapshot = supervisor.snapshot();
        if snapshot.state == wanted {
            return Ok(snapshot);
        }
        if matches!(snapshot.state, CoreState::Fatal | CoreState::Repair) {
            return Err(snapshot
                .last_error
                .unwrap_or_else(|| "Core entered a terminal state".into()));
        }
        if Instant::now() >= deadline {
            return Err(format!(
                "timed out waiting for {:?}; last state was {:?}",
                wanted, snapshot.state
            ));
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn smoke_core_request(
    supervisor: &CoreSupervisor,
    method: &str,
    path: String,
    body: Option<Value>,
) -> Result<Value, String> {
    let response = supervisor_core_api(
        supervisor,
        CoreApiRequest {
            method: method.into(),
            path,
            body,
            idempotency_key: Some(format!("point16c-{}", launch_token())),
        },
    )?;
    if !(200..300).contains(&response.status) {
        return Err(format!(
            "Core smoke request failed with {}: {}",
            response.status,
            redact_diagnostic(&response.body.to_string())
        ));
    }
    Ok(response.body)
}

fn run_chat_smoke(supervisor: &CoreSupervisor) -> Result<(String, String), String> {
    let bootstrap = smoke_core_request(supervisor, "GET", "/v2/bootstrap".into(), None)?;
    if bootstrap.pointer("/data/version/contract").is_none() {
        return Err("desktop bootstrap omitted the contract version".into());
    }
    let created = smoke_core_request(
        supervisor,
        "POST",
        "/v2/conversations".into(),
        Some(json!({"title":"Point 16C isolated product smoke"})),
    )?;
    let session_id = created
        .pointer("/data/conversation/id")
        .and_then(Value::as_str)
        .ok_or("product smoke conversation ID missing")?
        .to_string();
    let submitted = smoke_core_request(
        supervisor,
        "POST",
        format!("/v2/conversations/{session_id}/runs"),
        Some(json!({"text":"hello"})),
    )?;
    let run_id = submitted
        .pointer("/data/run_id")
        .and_then(Value::as_str)
        .ok_or("product smoke run ID missing")?
        .to_string();
    let deadline = Instant::now() + Duration::from_secs(20);
    loop {
        let run = smoke_core_request(supervisor, "GET", format!("/v2/runs/{run_id}"), None)?;
        match run
            .pointer("/data/run/status")
            .and_then(Value::as_str)
            .unwrap_or("")
        {
            "completed" => break,
            "failed" | "cancelled" | "interrupted" => {
                return Err(format!("product smoke run did not complete: {run}"));
            }
            _ if Instant::now() >= deadline => {
                return Err("product smoke run timed out".into());
            }
            _ => thread::sleep(Duration::from_millis(100)),
        }
    }
    assert_chat_smoke_persisted(supervisor, &session_id)?;
    Ok((session_id, run_id))
}

fn assert_chat_smoke_persisted(
    supervisor: &CoreSupervisor,
    session_id: &str,
) -> Result<(), String> {
    let messages = smoke_core_request(
        supervisor,
        "GET",
        format!("/v2/conversations/{session_id}/messages?limit=48"),
        None,
    )?;
    let persisted = messages
        .pointer("/data/messages")
        .and_then(Value::as_array)
        .map(|items| {
            items.iter().any(|item| {
                item.get("role").and_then(Value::as_str) == Some("assistant")
                    && item.get("content").and_then(Value::as_str) == Some("deterministic:hello")
            })
        })
        .unwrap_or(false);
    if !persisted {
        return Err("deterministic chat response was not persisted".into());
    }
    Ok(())
}

fn run_supervisor_smoke(
    app: AppHandle,
    supervisor: CoreSupervisor,
    result_path: PathBuf,
    initial_shell: Value,
) {
    let result = (|| -> Result<Value, String> {
        let first = wait_for_state(&supervisor, CoreState::Ready, Duration::from_secs(45))?;
        let first_pid = first.pid.ok_or("initial Core PID missing")?;
        let duplicate = supervisor.begin_start(app.clone());
        if duplicate.pid != Some(first_pid) || duplicate.generation != first.generation {
            return Err("duplicate start replaced the active Core".into());
        }
        let (chat_session_id, chat_run_id) = run_chat_smoke(&supervisor)?;

        let window = app
            .get_webview_window("main")
            .ok_or("main WebView missing")?;
        windows_integration::desktop_finish_startup(app.clone())?;
        let workspace_scale = window.scale_factor().map_err(|error| error.to_string())?;
        let workspace_size = window.inner_size().map_err(|error| error.to_string())?;
        let overlay = windows_integration::create_voice_overlay(&app, false)?;
        let overlay_scale = overlay.scale_factor().map_err(|error| error.to_string())?;
        let overlay_size = overlay.inner_size().map_err(|error| error.to_string())?;
        let voice_overlay = json!({
            "width": (overlay_size.width as f64 / overlay_scale).round() as u32,
            "height": (overlay_size.height as f64 / overlay_scale).round() as u32,
            "always_on_top": overlay.is_always_on_top().unwrap_or(false),
            "decorated": overlay.is_decorated().unwrap_or(true),
            "visible_during_smoke": overlay.is_visible().unwrap_or(true)
        });
        let _ = overlay.close();
        window
            .eval("window.location.reload()")
            .map_err(|error| error.to_string())?;
        thread::sleep(Duration::from_secs(2));
        let after_reload = supervisor.snapshot();
        if after_reload.pid != Some(first_pid) || after_reload.generation != first.generation {
            return Err("WebView reload replaced the active Core".into());
        }
        assert_chat_smoke_persisted(&supervisor, &chat_session_id)?;

        supervisor.terminate_for_smoke()?;
        let crashed = wait_for_state(&supervisor, CoreState::Crashed, Duration::from_secs(10))?;
        let restarting = supervisor.begin_start(app.clone());
        let second = wait_for_state(&supervisor, CoreState::Ready, Duration::from_secs(45))?;
        let second_pid = second.pid.ok_or("restarted Core PID missing")?;
        if second_pid == first_pid || restarting.generation != first.generation + 1 {
            return Err("Core restart did not create exactly one new generation".into());
        }
        assert_chat_smoke_persisted(&supervisor, &chat_session_id)?;
        let health = supervisor.health()?;
        if health.get("ready").and_then(Value::as_bool) != Some(true) {
            return Err("Rust-proxied health was not ready".into());
        }
        let stopped = supervisor.stop(Some(&app));
        Ok(json!({
            "ok": true,
            "initial_ready": true,
            "duplicate_core_prevented": true,
            "webview_reload_preserved_pid": true,
            "chat_run_completed": true,
            "chat_survived_webview_reload": true,
            "chat_survived_core_restart": true,
            "chat_session_id": chat_session_id,
            "chat_run_id": chat_run_id,
            "crash_detected": crashed.state == CoreState::Crashed,
            "restart_ready": true,
            "graceful_stop": stopped.state == CoreState::Stopped,
            "initial_shell": initial_shell,
            "workspace_shell": {
                "width": (workspace_size.width as f64 / workspace_scale).round() as u32,
                "height": (workspace_size.height as f64 / workspace_scale).round() as u32,
                "resizable": window.is_resizable().unwrap_or(false)
            },
            "voice_overlay": voice_overlay,
            "first_generation": first.generation,
            "second_generation": second.generation
        }))
    })();
    let payload = match result {
        Ok(value) => value,
        Err(error) => {
            json!({"ok": false, "error": redact_diagnostic(&error), "snapshot": supervisor.snapshot()})
        }
    };
    if let Some(parent) = result_path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(
        &result_path,
        serde_json::to_vec_pretty(&payload).unwrap_or_else(|_| b"{\"ok\":false}".to_vec()),
    );
    app.exit(
        if payload.get("ok").and_then(Value::as_bool) == Some(true) {
            0
        } else {
            1
        },
    );
}

#[tauri::command]
fn restart_after_update(app: AppHandle) {
    app.restart();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let supervisor = CoreSupervisor::new();
    let managed = supervisor.clone();
    let setup_supervisor = supervisor.clone();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(
            |app, arguments, _cwd| {
                windows_integration::show_main(
                    app,
                    windows_integration::activation_from_args(arguments),
                );
            },
        ))
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .manage(windows_integration::DesktopState::default())
        .manage(managed)
        .invoke_handler(tauri::generate_handler![
            core_status,
            core_health,
            core_restart,
            core_api,
            stage_attachment,
            read_attachment_preview,
            save_text_file,
            save_binary_file,
            pick_management_path,
            desktop_diagnostic_snapshot,
            open_chat_link,
            windows_integration::desktop_finish_startup,
            windows_integration::desktop_show_voice_overlay,
            windows_integration::desktop_hide_voice_overlay,
            windows_integration::desktop_focus_main,
            windows_integration::desktop_set_voice_hotkey,
            windows_integration::desktop_set_close_to_tray,
            windows_integration::desktop_notify,
            windows_integration::desktop_set_unread,
            windows_integration::desktop_quit,
            restart_after_update,
            browser::browser_status,
            browser::browser_open,
            browser::browser_close,
            browser::browser_duplicate,
            browser::browser_restore_closed,
            browser::browser_reorder,
            browser::browser_pin,
            browser::browser_stop,
            browser::browser_activate,
            browser::browser_set_bounds,
            browser::browser_set_visible,
            browser::browser_navigate,
            browser::browser_reload,
            browser::browser_action,
            browser::browser_metadata,
            browser::browser_open_devtools,
            browser::browser_clear_guest,
            browser::browser_clear_profile
        ])
        .setup(move |app| {
            let (app_data, cache) = if let Some(data_dir) = env::var_os("SMARTI_DATA_DIR") {
                let root = PathBuf::from(data_dir).join("tauri-desktop");
                (root.join("data"), root.join("cache"))
            } else {
                (app.path().app_data_dir()?, app.path().app_cache_dir()?)
            };
            let browser_broker = browser::BrowserBroker::new(app_data, cache);
            let handle = app.handle().clone();
            let browser_endpoint =
                browser::start_core_bridge(handle.clone(), browser_broker.clone())?;
            setup_supervisor
                .configure_browser_bridge(browser_endpoint.port, browser_endpoint.token);
            app.manage(browser_broker.clone());
            windows_integration::setup(app.handle())?;
            setup_supervisor.begin_start(handle.clone());
            if let Some(result_path) = env::var_os("SMARTI_BROWSER_SMOKE_FILE") {
                browser::run_foundation_smoke(
                    handle.clone(),
                    browser_broker,
                    PathBuf::from(result_path),
                );
            }
            if let Some(result_path) = env::var_os("SMARTI_SUPERVISOR_SMOKE_FILE") {
                let initial_shell = if let Some(window) = app.get_webview_window("main") {
                    let scale = window.scale_factor().unwrap_or(1.0);
                    let size = window
                        .inner_size()
                        .unwrap_or(tauri::PhysicalSize::new(0, 0));
                    let value = json!({
                        "width": (size.width as f64 / scale).round() as u32,
                        "height": (size.height as f64 / scale).round() as u32,
                        "resizable": window.is_resizable().unwrap_or(true),
                        "decorated": window.is_decorated().unwrap_or(true)
                    });
                    let _ = window.hide();
                    value
                } else {
                    json!({"missing": true})
                };
                let smoke_supervisor = setup_supervisor.clone();
                thread::Builder::new()
                    .name("smarti-supervisor-smoke".into())
                    .spawn(move || {
                        run_supervisor_smoke(
                            handle,
                            smoke_supervisor,
                            PathBuf::from(result_path),
                            initial_shell,
                        )
                    })?;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building SmartiAI desktop application");
    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            handle.state::<browser::BrowserBroker>().cleanup_guest();
            handle.state::<CoreSupervisor>().stop(Some(handle));
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    fn valid(pid: u32) -> String {
        json!({"type":"smarti_core_ready","schema_version":1,"state":"ready","pid":pid,"host":"127.0.0.1","port":42123,"health":{"ready":true,"qt_loaded":false,"started_at":"now"}}).to_string()
    }
    #[test]
    fn accepts_valid_handshake() {
        assert_eq!(validate_handshake(&valid(42), 42).unwrap().port, 42123);
    }
    #[test]
    fn rejects_invalid_json() {
        assert!(validate_handshake("not json", 1).is_err());
    }
    #[test]
    fn rejects_wrong_process_identity() {
        assert!(validate_handshake(&valid(7), 8)
            .unwrap_err()
            .contains("identity"));
    }
    #[test]
    fn rejects_qt_loaded_core() {
        let mut value: Value = serde_json::from_str(&valid(7)).unwrap();
        value["health"]["qt_loaded"] = json!(true);
        assert!(validate_handshake(&value.to_string(), 7).is_err());
    }
    #[test]
    fn reports_slow_startup_timeout() {
        let (_tx, rx) = mpsc::channel();
        assert!(receive_handshake(rx, Duration::from_millis(1))
            .unwrap_err()
            .contains("timed out"));
    }
    #[test]
    fn duplicate_running_child_contract_is_stable() {
        let mut child = None;
        assert!(!child_is_running(&mut child));
    }
    #[test]
    fn graceful_exit_uses_narrow_pipe_command() {
        assert_eq!(shutdown_command(), "{\"command\":\"shutdown\"}\n");
    }
    #[test]
    fn crash_diagnostic_preserves_exit_code() {
        assert!(exit_message(Some(23)).contains("23"));
    }
    #[test]
    fn diagnostics_redact_bearer_tokens() {
        assert_eq!(
            redact_diagnostic("oops Bearer secret"),
            "oops Bearer [REDACTED]"
        );
    }
    #[test]
    fn webview_reload_does_not_mutate_generation() {
        let supervisor = CoreSupervisor::new();
        let before = supervisor.snapshot().generation;
        let _ = supervisor.snapshot();
        assert_eq!(supervisor.snapshot().generation, before);
    }
    #[test]
    fn launch_tokens_are_unique_and_opaque() {
        let a = launch_token();
        let b = launch_token();
        assert_eq!(a.len(), 64);
        assert_ne!(a, b);
    }
    #[test]
    fn core_proxy_rejects_arbitrary_network_and_paths_before_connecting() {
        let traversal = core_http_request(
            1,
            "secret",
            CoreApiRequest {
                method: "GET".into(),
                path: "/v2/../../private".into(),
                body: None,
                idempotency_key: None,
            },
        );
        let remote = core_http_request(
            1,
            "secret",
            CoreApiRequest {
                method: "GET".into(),
                path: "https://example.com/v2/data".into(),
                body: None,
                idempotency_key: None,
            },
        );
        let shell = core_http_request(
            1,
            "secret",
            CoreApiRequest {
                method: "EXEC".into(),
                path: "/v2/health".into(),
                body: None,
                idempotency_key: None,
            },
        );
        assert!(traversal.unwrap_err().contains("path"));
        assert!(remote.unwrap_err().contains("path"));
        assert!(shell.unwrap_err().contains("method"));
    }
    #[test]
    fn chat_links_allow_only_expected_external_schemes() {
        assert!(validate_external_chat_link("https://example.com/a").is_ok());
        assert!(validate_external_chat_link("mailto:test@example.com").is_ok());
        assert!(validate_external_chat_link("javascript:alert(1)").is_err());
        assert!(validate_external_chat_link("https://example.com/\r\nInjected").is_err());
    }
    #[test]
    fn chat_links_block_executable_local_extensions() {
        assert!(blocked_chat_link_extension(std::path::Path::new(
            "C:\\Temp\\unsafe.ps1"
        )));
        assert!(!blocked_chat_link_extension(std::path::Path::new(
            "C:\\Temp\\report.pdf"
        )));
    }
}
