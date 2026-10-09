import type { ChatMessage, Conversation, RunEvent } from "./chatTypes";

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
  const messages = new Map<string, ChatMessage>();
  for (const message of [...older, ...current]) {
    const run = message.role === "assistant" && message.metadata?.run_id;
    const identity = run ? `run:${run}` : message.created_at
      ? `${message.role}:${message.created_at}:${message.content}` : `${message.role}:${message.content}`;
    messages.set(identity, message);
  }
  const merged = [...messages.values()];
  // A refreshed page can include history earlier than the already mounted
  // page. Arrival order must not move those messages after the latest turn.
  const ordered = merged.map(message => {
    const id = message.message_id?.match(/^(.*):(\d+)$/);
    return { message, session: id?.[1], ordinal: id ? Number(id[2]) : NaN };
  });
  if (ordered.every(item => item.session && item.session === ordered[0]?.session && Number.isSafeInteger(item.ordinal))) {
    return ordered.sort((left, right) => left.ordinal - right.ordinal).map(item => item.message);
  }
  return merged;
}

export function recentConversations(conversations: Conversation[]) {
  return conversations.filter((conversation) =>
    Number(conversation.message_count || 0) > 0,
  );
}

export function semanticStep(event: RunEvent): string | null {
  const value = String(event.payload.value || event.payload.step || event.payload.status || "").trim();
  if (event.event_type === "run_step") return value || "מבצע שלב";
  if (event.event_type === "tool_started") return `מפעיל ${String(event.payload.tool || event.payload.name || "כלי")}`;
  if (event.event_type === "tool_finished") return `${String(event.payload.tool || event.payload.name || "הכלי")} הסתיים`;
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
