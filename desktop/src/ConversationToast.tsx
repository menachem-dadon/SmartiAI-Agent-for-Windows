import { useEffect } from "react";
import type { AttentionItem } from "./chatTypes";
import { IconButton } from "./design-system";
import { attentionTitle, ConversationIndicator, needsAttention } from "./conversationIndicators";

export function ConversationToast({ item, suppressed, onDismiss, onOpen }: {
  item: AttentionItem | null; suppressed: boolean; onDismiss: () => void; onOpen: (item: AttentionItem) => void;
}) {
  useEffect(() => {
    if (!item) return;
    const timer = window.setTimeout(onDismiss, 5000);
    return () => window.clearTimeout(timer);
  }, [item, onDismiss]);
  if (!item || suppressed) return null;
  return <div className="conversation-toast" role="status" dir="rtl">
    <ConversationIndicator state={item.kind === "approval" ? "waiting_for_approval" : needsAttention(item) ? "waiting_for_input" : "unread"} />
    <div className="conversation-toast-copy"><strong>{attentionTitle(item)}</strong><span>{item.title}</span></div>
    <IconButton icon="external" variant="ghost" label="פתיחת השיחה" onClick={() => onOpen(item)} />
  </div>;
}
