//! Authenticated loopback Live transport. Credentials never cross IPC.
use serde_json::{json, Value};
use std::collections::HashMap;
use std::net::TcpStream;
use std::sync::{mpsc, Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::ipc::Channel;
use tungstenite::{client::IntoClientRequest, Error, Message};

#[derive(Clone)]
struct Writer {
    control: mpsc::SyncSender<Option<Value>>,
    audio: mpsc::SyncSender<(Instant, Value)>,
}

#[derive(Clone, Default)]
pub struct LiveStreams(Arc<Mutex<HashMap<String, Writer>>>);

fn valid_session(id: &str) -> bool {
    id.len() == 32 && id.bytes().all(|c| c.is_ascii_hexdigit())
}

#[tauri::command]
pub async fn core_live_open(
    session_id: String, after: u64, events: Channel<Value>,
    supervisor: tauri::State<'_, super::CoreSupervisor>,
    streams: tauri::State<'_, LiveStreams>,
) -> Result<String, String> {
    if !valid_session(&session_id) { return Err("Invalid Live identity".into()); }
    let (port, token, generation) = {
        let inner = supervisor.inner.lock().map_err(|_| "Core state unavailable")?;
        (inner.snapshot.port.ok_or("Core not ready")?, inner.token.clone().ok_or("Core credential unavailable")?, inner.snapshot.generation)
    };
    let streams = streams.inner().clone();
    let core = supervisor.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut request = format!("ws://127.0.0.1:{port}/v2/live/sessions/{session_id}/stream?after={after}")
            .into_client_request().map_err(|_| "Invalid Live endpoint")?;
        request.headers_mut().insert("Authorization", format!("Bearer {token}").parse().map_err(|_| "Invalid credential")?);
        request.headers_mut().insert("Origin", "tauri://localhost".parse().unwrap());
        let tcp = TcpStream::connect_timeout(&([127,0,0,1], port).into(), Duration::from_secs(3))
            .map_err(|_| "Live connection unavailable")?;
        tcp.set_read_timeout(Some(Duration::from_secs(3))).map_err(|_| "Live read unavailable")?;
        tcp.set_write_timeout(Some(Duration::from_secs(3))).map_err(|_| "Live write unavailable")?;
        tcp.set_nodelay(true).map_err(|_| "Live socket unavailable")?;
        let (mut socket, _) = tungstenite::client(request, tcp).map_err(|_| "Live connection rejected")?;
        socket.get_mut().set_read_timeout(Some(Duration::from_millis(15))).map_err(|_| "Live read unavailable")?;
        let (control, commands) = mpsc::sync_channel::<Option<Value>>(32);
        let (audio, frames) = mpsc::sync_channel::<(Instant, Value)>(12);
        let id = super::launch_token();
        {
            let mut writers = streams.0.lock().map_err(|_| "Live state unavailable")?;
            if writers.len() >= 8 { return Err("Too many Live transports".into()); }
            writers.insert(id.clone(), Writer { control, audio });
        }
        let owned = id.clone();
        std::thread::spawn(move || {
            let result = (|| -> Result<(), String> {
                loop {
                    if core.inner.lock().map(|inner| inner.snapshot.generation != generation).unwrap_or(true) {
                        return Err("Core restarted".into());
                    }
                    for _ in 0..8 {
                        match commands.try_recv() {
                            Ok(None) | Err(mpsc::TryRecvError::Disconnected) => { let _ = socket.close(None); return Ok(()); }
                            Ok(Some(value)) => socket.send(Message::Text(value.to_string().into())).map_err(|_| "Live write interrupted")?,
                            Err(mpsc::TryRecvError::Empty) => break,
                        }
                    }
                    if let Ok((created, value)) = frames.try_recv() {
                        // Speech recorded long ago must not delay current controls.
                        if created.elapsed() <= Duration::from_millis(800) {
                            socket.send(Message::Text(value.to_string().into())).map_err(|_| "Live audio interrupted")?;
                        } else {
                            let _ = events.send(json!({"type":"receipt", "sequence":value["sequence"], "data":{"accepted":true,"dropped":true}}));
                        }
                    }
                    match socket.read() {
                        Ok(Message::Text(text)) => {
                            let value: Value = serde_json::from_str(&text).map_err(|_| "Invalid Live event")?;
                            events.send(value).map_err(|_| "Live UI detached")?;
                        }
                        Ok(Message::Close(_)) | Err(Error::ConnectionClosed) | Err(Error::AlreadyClosed) => return Ok(()),
                        Ok(_) => {},
                        Err(Error::Io(error)) if matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) => {},
                        Err(_) => return Err("Live stream interrupted".into()),
                    }
                }
            })();
            if let Ok(mut writers) = streams.0.lock() { writers.remove(&owned); }
            let _ = events.send(json!({"type":"transport_closed", "error":result.err()}));
        });
        Ok(id)
    }).await.map_err(|_| "Live worker failed".to_string())?
}

#[tauri::command]
pub fn core_live_send(id: String, input: Value, streams: tauri::State<'_, LiveStreams>) -> Result<bool, String> {
    if !input.is_object() || input.to_string().len() > 1_200_000 { return Err("Invalid Live input".into()); }
    let writer = streams.0.lock().map_err(|_| "Live state unavailable")?.get(&id).cloned().ok_or("Live transport detached")?;
    if input.get("audio").is_some() {
        match writer.audio.try_send((Instant::now(), input)) {
            Ok(_) => Ok(true), Err(mpsc::TrySendError::Full(_)) => Ok(false), Err(_) => Err("Live transport detached".into()),
        }
    } else {
        writer.control.try_send(Some(input)).map(|_| true).map_err(|_| "Live controls busy".into())
    }
}

#[tauri::command]
pub fn core_live_close(id: String, streams: tauri::State<'_, LiveStreams>) {
    if let Ok(mut writers) = streams.0.lock() {
        if let Some(writer) = writers.remove(&id) { let _ = writer.control.try_send(None); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn accepts_only_scoped_session_ids() {
        assert!(valid_session("0123456789abcdef0123456789abcdef"));
        for id in ["../health", "x", "0123456789abcdef0123456789abcdeg"] { assert!(!valid_session(id)); }
    }
}
