import type { RunEvent } from "./chatTypes";

export type StreamBlock = { kind: "text" | "tool"; text?: string; role?: "answer" | "report"; call_id?: string; name?: string; status?: string; arguments_text?: string };
export type StreamState = { cursor?: number; request_id?: string; stage: string; percent?: number | null; blocks: Record<string, StreamBlock> };
export function reduceStream(previous: StreamState | undefined, event: RunEvent): StreamState {
  if (event.event_type !== "run_stream" || event.event_id <= (previous?.cursor || 0)) return previous || { stage: "waiting", blocks: {} };
  const state: StreamState = { ...previous, stage: previous?.stage || "waiting", blocks: { ...previous?.blocks }, cursor: event.event_id };
  const values = (event.payload.value as { events?: Array<Record<string, unknown>> })?.events || [];
  for (const value of values) {
    const request = String(value.request_id || ""), id = String(value.block_id || request);
    if (value.kind === "request_start") {
      state.request_id = request; state.stage = "waiting"; state.percent = null;
      state.blocks = Object.fromEntries(Object.entries(state.blocks).filter(([, block]) => block.role === "report" || block.kind === "tool"));
    } else if (request === state.request_id) {
      if (value.kind === "stage") { state.stage = String(value.provider_stage); state.percent = typeof value.percent === "number" ? value.percent : null; }
      else if (value.kind === "text_delta" || value.kind === "text_replace") {
        state.blocks[id] = { kind: "text", role: value.role === "report" ? "report" : state.blocks[id]?.role || "answer", text: (value.kind === "text_delta" ? state.blocks[id]?.text || "" : "") + String(value.text || "") };
        state.stage = "text";
      } else if (value.kind === "tool_preparing") {
        state.blocks[id] = { kind: "tool", call_id: String(value.call_id), name: String(value.name || ""), status: "preparing", arguments_text: String(value.arguments_text || "") };
        state.stage = "tool";
      } else if ((value.kind === "request_end" || value.kind === "text_role") && state.blocks[id]) state.blocks[id] = { ...state.blocks[id], role: value.role as "answer" | "report" };
    }
  }
  return state;
}
export function streamAnswer(state?: StreamState): string {
  return Object.values(state?.blocks || {}).filter(block => block.kind === "text" && block.role !== "report").map(block => block.text || "").join("\n");
}
