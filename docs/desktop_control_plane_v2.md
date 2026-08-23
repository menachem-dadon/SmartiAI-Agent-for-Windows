# Smarti Desktop Control Plane `/v2`

This document is the durable, plain-language summary of the typed contract
between the future trusted Tauri host and the headless Python Core. The
authoritative schema source is `smarti/control_plane_contract.py`; regenerate
the checked-in language-neutral and TypeScript artifacts with:

```powershell
python scripts/generate_desktop_contract.py
```

Generated consumers:

- `desktop-contract/v2.contract.json`
- `desktop-contract/v2.generated.d.ts`

## Trust boundary

- The listener binds only to `127.0.0.1` on the requested random port.
- Every route except the minimal health checks requires the per-launch bearer
  token. This token is intended for the trusted Rust host, not React storage.
- Browser-originated requests are accepted only from the explicit Tauri origin
  allowlist; native clients without an `Origin` header remain supported.
- The legacy `/v1` local/channel API remains available with its existing wire
  shapes and can continue using its separately configured stable credential.
- Request bodies are capped at 1 MiB and validated against the authoritative
  JSON Schemas. Mutating routes support `Idempotency-Key`.
- Settings snapshots never return plaintext stored secrets. Secret writes and
  deletes use explicit endpoints.
- Native-selected attachment paths are exchanged for random, expiring handles;
  conversation submission accepts handles instead of arbitrary frontend paths.

## Operations in ordinary language

| Need | Operation |
|---|---|
| Start the desktop | `GET /v2/bootstrap`, `/health`, `/version`, `/capabilities` |
| Browse conversations | list/search/create/read/rename/pin/delete under `/v2/conversations` |
| Read history | paginated `GET /v2/conversations/{session_id}/messages` |
| Send | `POST /v2/conversations/{session_id}/runs` |
| Cancel and inspect | `/v2/runs/{run_id}`, `/cancel`, and `/events` |
| Reconnect | authenticated WebSocket `/v2/events?after_event_id=...` |
| Approve or deny | list `/v2/approvals`; resolve an approval by ID |
| Mark read | `POST /v2/conversations/{session_id}/read` |
| Configure Smarti | safe schema/snapshot/patch under `/v2/settings` |
| Manage credentials | explicit set/delete under `/v2/settings/secrets/{secret_key}` |
| Validate providers | `/v2/providers/{provider}/validate` and `/models` |
| Model quick controls | read/update `/v2/providers/{provider}/reasoning`; read Codex usage at `/v2/providers/openai_codex_signin/quota` |
| Attach a file | register under `/v2/attachments`, then submit its opaque handle |
| Manage workspaces | list/create/update/delete under `/v2/workspaces` |

## Correlation and replay

Every `/v2` JSON response contains a `request_id`. The caller may supply it as
`X-Request-ID`; otherwise Core creates one. Run submissions persist that value
in run metadata, and every streamed durable event carries `request_id`,
`session_id`, `run_id`, per-run `sequence`, and global `event_id`.

The WebSocket cursor is the last processed global `event_id`. On reconnect the
client supplies `after_event_id`; Core replays only later durable events in
strict ascending order. A client may also scope the stream to one `session_id`.
Slow sends time out and disconnect without blocking the Core or losing durable
events, so the same cursor can be used again.

## Evidence boundary

Point 4 validates the Python API with a non-UI integration client. There is no
Tauri window, Rust proxy, visual QA, packaged sidecar, installer, LAN endpoint,
cloud endpoint, WhatsApp adapter, or arbitrary shell API in this point.
