import type { ChatMessage, RunEvent } from "./chatTypes";

export const ACTIVE_RUN_STATES = new Set(["queued", "running", "waiting_for_approval", "cancelling"]);
export function mergeMessages(older: ChatMessage[], current: ChatMessage[]) {
  const seen = new Set<string>();
  return [...older, ...current].filter((message) => {
    const key = `${message.role}|${message.created_at || ""}|${message.content}`;
    if (seen.has(key)) return false; seen.add(key); return true;
  });
}
export function semanticStep(event: RunEvent): string | null {
  const value = String(event.payload.value || event.payload.step || event.payload.status || "").trim();
  if (event.event_type === "run_step") return value || "מבצע שלב";
  if (event.event_type === "tool_started") return `מפעיל ${String(event.payload.tool || event.payload.name || "כלי")}`;
  if (event.event_type === "tool_finished") return `${String(event.payload.tool || event.payload.name || "הכלי")} הסתיים`;
  if (event.event_type === "approval_requested") return "ממתין לאישור";
  if (event.event_type === "run_started") return "התחיל לעבוד";
  return null;
}

