import type { ChatMessage, RunEvent } from "./chatTypes";

export const ACTIVE_RUN_STATES = new Set(["queued", "running", "waiting_for_approval", "waiting_for_input", "cancelling"]);
export type ApiKeyRequest = {
  runId: string;
  secretKey: string;
  providerLabel: string;
  title: string;
  message: string;
  helpUrl: string;
  provider: string;
  keyInstructions: string;
};
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
  if (event.event_type === "api_key_required") return "ממתין למפתח API";
  if (event.event_type === "run_started") return "התחיל לעבוד";
  return null;
}

export function pendingApiKeyRequest(events: RunEvent[]): ApiKeyRequest | null {
  const resolved = new Set<string>();
  for (const event of [...events].sort((a, b) => b.event_id - a.event_id)) {
    const secretKey = String(event.payload.secret_key || "");
    const identity = `${event.run_id}:${secretKey}`;
    if (event.event_type === "api_key_submitted") {
      resolved.add(identity);
      continue;
    }
    if (event.event_type !== "api_key_required" || resolved.has(identity))
      continue;
    return {
      runId: event.run_id,
      secretKey,
      providerLabel: String(event.payload.provider_label || ""),
      title: String(event.payload.title || "חסר מפתח API"),
      message: String(event.payload.message || ""),
      helpUrl: String(event.payload.help_url || ""),
      provider: String(event.payload.provider || ""),
      keyInstructions: String(event.payload.key_instructions || ""),
    };
  }
  return null;
}
