import type { AttentionItem, Conversation } from "./chatTypes";
import { Icon } from "./design-system";

export type ConversationIndicatorState = "running" | "queued" | "waiting_for_approval" | "waiting_for_input" | "problem" | "unread" | "idle";

export function isUnseenCompletion(item: AttentionItem) {
  return item.kind === "response" && item.run_status === "completed" && Boolean(item.run_id);
}

export function needsAttention(item: AttentionItem) {
  return Boolean(item.action_required) || item.kind === "interrupted" ||
    (item.kind === "response" && ["failed", "interrupted"].includes(item.run_status || ""));
}

export function attentionSummary(items: AttentionItem[]) {
  const action = items.filter(needsAttention);
  return {
    count: new Set(items.filter(isUnseenCompletion).map(item => item.run_id)).size,
    actionRequired: action.length > 0,
    state: (action.some(item => item.kind !== "approval") ? "waiting_for_input" : action.length ? "waiting_for_approval" :
      items.some(isUnseenCompletion) ? "unread" : "idle") as ConversationIndicatorState,
  };
}

export function conversationIndicator(item: Conversation, attention: AttentionItem[]): ConversationIndicatorState {
  const relevant = attention.filter(entry => entry.session_id === item.id);
  if (item.runtime_status === "waiting_for_input" || relevant.some(entry => entry.kind === "api_key" && entry.action_required)) return "waiting_for_input";
  if (item.runtime_status === "waiting_for_approval" || item.needs_input || relevant.some(entry => entry.kind === "approval" && entry.action_required)) return "waiting_for_approval";
  if (relevant.some(needsAttention)) return "problem";
  if (["running", "cancelling"].includes(item.runtime_status || "")) return "running";
  if (item.runtime_status === "queued") return "queued";
  if (item.is_busy) return "running";
  return relevant.some(isUnseenCompletion) ? "unread" : "idle";
}

export const indicatorLabels: Record<ConversationIndicatorState, string> = {
  running: "סמארטי עובד בשיחה הזאת", queued: "המשימה ממתינה בתור", waiting_for_approval: "נדרש אישורך להמשך",
  waiting_for_input: "נדרש קלט להמשך", problem: "הריצה נכשלה או נקטעה", unread: "תוצאה חדשה שטרם נצפתה", idle: "",
};

export function ConversationIndicator({ state, label = indicatorLabels[state] }: { state: ConversationIndicatorState; label?: string }) {
  if (state === "idle") return null;
  return <span role="img" aria-label={label} title={label} className={`conversation-activity ${state}`}>
    {state !== "unread" && <Icon size={14} name={state === "running" ? "loader" : state === "queued" ? "clock" : state === "waiting_for_approval" ? "questionCircle" : "exclamationCircle"} />}
  </span>;
}

export function attentionTitle(item: AttentionItem) {
  return item.kind === "approval" ? "נדרש אישורך להמשך" : item.kind === "api_key" ? "נדרש קלט להמשך" :
    needsAttention(item) ? "הריצה נכשלה או נקטעה" : "המשימה הסתיימה";
}
