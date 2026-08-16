# Smarti conversation runtime

This document describes the runtime contract introduced for concurrent conversations. The desktop UI is a consumer of this runtime; it is no longer the owner of an agent execution.

## Core hierarchy

```text
Workspace
  Conversation (sessions)
    Message
    Run
      RunEvent
      Approval
      AttentionItem
      Artifact / tool metadata
```

A conversation may have many queued runs, but only one run in that conversation may execute at a time. Independent conversations start independently with no Smarti-imposed global count limit. Provider rate limits, local-model server capacity, available memory, and singleton desktop resources can still create natural back-pressure or provider errors; they do not prevent unrelated conversations from being submitted.

The execution state and the attention state are deliberately separate:

- `queued`, `running`, `waiting_for_approval`, and `cancelling` describe work.
- An unread `attention_item` means the user has something new to see.
- Opening a conversation marks only that conversation's attention items as read.
- The Windows taskbar count is a projection of the durable unread count, not an in-memory notification counter.

## Persistence and recovery

`ChatSessionStore` owns the SQLite ledger. Schema version 3 adds:

- `workspaces`
- `runs`
- `run_events`
- `approvals`
- `attention_items`
- `read_receipts`
- `idempotency_keys`

Every state change is written before a UI event is emitted. A process restart marks a run that was executing as `interrupted`, cancels an approval that can no longer continue safely, and creates an unread interruption item. A queued run is safe to restore and submit to the scheduler.

## Isolation and resource rules

Conversation-specific mutable state is bound to the worker thread:

- submitted provider, model and configured provider client
- model history and system prompt
- conversation summary and tool transcript
- attachments and tool observations
- callbacks and cancellation event
- process/tool event metadata
- memory and canvas result metadata

Parallel tool worker threads inherit this run context explicitly. Process cancellation is tracked by run ID so stopping one conversation does not terminate processes owned by another conversation.

The Smarti browser and Windows computer-control surface are singleton resources. A run leases either resource until it completes. This prevents two conversations from manipulating the same browser profile or desktop at the same time while still allowing independent model and read-only work to proceed concurrently.

## UI event contract

`ConversationRunManager` emits dictionaries with:

```json
{
  "event_type": "run_started",
  "run_id": "...",
  "session_id": "...",
  "payload": {},
  "created_at": "..."
}
```

Important event types are `run_available`, `run_started`, `run_status`, `run_step`, `approval_requested`, and `run_finished`.

The history sidebar projects these events from SQLite:

- animated progress arc: queued/running/cancelling
- approval marker: waiting for approval
- dot: final response or interruption not yet viewed
- highlighted card: currently selected conversation (there is no “active” execution badge)

## Local gateway

When `local_gateway_enabled` is true, Smarti starts an HTTP API on loopback only. Runtime connection metadata (without the secret) is written to `local-gateway.json` in the Smarti data directory. The bearer token is stored using the same Windows Credential Manager/DPAPI path as provider secrets.

All endpoints except `/v1/health` require:

```http
Authorization: Bearer <token>
```

Mutation endpoints accept `Idempotency-Key`. Supported routes:

- `GET /v1/health`
- `GET|POST /v1/sessions`
- `GET|POST /v1/workspaces`
- `POST /v1/sessions/{session_id}/messages`
- `POST /v1/sessions/{session_id}/read`
- `GET /v1/runs?session_id=...&status=...`
- `GET /v1/runs/{run_id}/events?after=...`
- `POST /v1/runs/{run_id}/cancel`
- `GET /v1/approvals`
- `POST /v1/approvals/{approval_id}/resolve`
- `POST /v1/channels/{channel}/messages`

The channel route is an authenticated ingress adapter for a future WhatsApp or other transport connector. A connector must validate its own webhook signature and map the remote identity before forwarding to loopback. Smarti's normal policy and durable approval flow still applies; channel code must never call tools directly.

## Compatibility

The legacy synchronous `SmartiCore.send_message()` API remains available. It now locks only the target conversation. Existing chat history, title generation, memory capture, canvases, notifications, speech, and background-task APIs remain readable. The built-in background scheduler submits work through the same run manager instead of switching the globally active desktop conversation.
