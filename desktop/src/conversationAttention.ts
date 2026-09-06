import { useCallback, useRef, useState } from "react";
import { coreApi, encodePath } from "./coreApi";
import type { AttentionItem } from "./chatTypes";

/** One global projection feeds both the taskbar and the conversation dots. */
export function useConversationAttention(onError: (message: string) => void) {
  const [items, setItems] = useState<AttentionItem[]>([]);
  const snapshot = useRef(items);
  const acknowledged = useRef(new Set<string>());
  const pending = useRef(new Set<string>());
  const replace = useCallback((next: AttentionItem[]) => {
    snapshot.current = next;
    setItems(next.filter((item) =>
      !acknowledged.current.has(item.id) && !pending.current.has(item.id),
    ));
  }, []);
  const acknowledge = useCallback(async (sessionId: string, ids: string[]) => {
    const unread = ids.filter((id) =>
      !acknowledged.current.has(id) && !pending.current.has(id),
    );
    if (!unread.length) return;
    for (const id of unread) pending.current.add(id);
    replace(snapshot.current);
    try {
      await coreApi("POST", `/v2/conversations/${encodePath(sessionId)}/read`, {
        actor_id: "tauri-desktop", attention_ids: unread,
      }, true);
      // Keep successful receipts across late/out-of-order list responses.
      for (const id of unread) acknowledged.current.add(id);
    } catch (reason) {
      onError(`לא ניתן לשמור את מצב הקריאה: ${String(reason)}`);
    } finally {
      for (const id of unread) pending.current.delete(id);
      replace(snapshot.current);
    }
  }, [onError, replace]);
  return { items, replace, acknowledge };
}
