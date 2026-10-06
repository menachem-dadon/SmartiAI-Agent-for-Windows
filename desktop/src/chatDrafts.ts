import { useCallback, useRef, useState, type SetStateAction } from "react";
import type { PendingAttachment } from "./chatTypes";

const storageKey = "smarti.desktop.chat-drafts.v1";
const activeKey = "smarti.desktop.active-conversation.v1";
export function readActiveConversation(): string {
  try { return sessionStorage.getItem(activeKey) || ""; } catch { return ""; }
}
export function rememberActiveConversation(id: string): boolean {
  try {
    if (id) sessionStorage.setItem(activeKey, id); else sessionStorage.removeItem(activeKey);
    return true;
  } catch { return false; }
}
export function restoreActiveConversation(conversations: readonly { id: string }[], wanted: string): string {
  return conversations.some(item => item.id === wanted) ? wanted : conversations[0]?.id || "";
}
export type DraftModel = { provider: string; model: string; effort: string };
export type ChatDraft = { text: string; attachments: PendingAttachment[]; selection?: DraftModel };
const empty = (): ChatDraft => ({ text: "", attachments: [] });

// UI recovery only, scoped to this WebView session. Submitted messages and all
// domain settings remain owned by Core. Secret dialogs never use this store.
export function readDrafts(): Record<string, ChatDraft> {
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) || "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).flatMap(([id, raw]) => {
      if (!raw || typeof raw !== "object") return [];
      const draft = raw as ChatDraft;
      return [[id, { text: typeof draft.text === "string" ? draft.text : "",
        attachments: Array.isArray(draft.attachments) ? draft.attachments.filter(item =>
          item && typeof item.path === "string" && typeof item.name === "string") : [],
        selection: draft.selection && typeof draft.selection.provider === "string" && typeof draft.selection.model === "string" && typeof draft.selection.effort === "string" ? draft.selection : undefined }]];
    }));
  } catch { return {}; }
}

export function useChatDrafts(sessionId: string, onStorageError: (message: string) => void) {
  const [records, setRecords] = useState(readDrafts);
  const current = useRef(records);
  const errorHandler = useRef(onStorageError);
  errorHandler.current = onStorageError;
  const owner = sessionId || "new";
  const write = useCallback((update: (value: Record<string, ChatDraft>) => Record<string, ChatDraft>) => {
    const next = update(current.current);
    current.current = next;
    setRecords(next);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(next, (key, value) =>
        key === "previewUrl" ? undefined : value));
    } catch { errorHandler.current("לא ניתן לשמור את הטיוטה לרענון. הטיוטה נשארת פתוחה; העתק אותה לפני סגירת החלון."); }
  }, []);
  const setText = useCallback((text: string) => write(value => ({ ...value,
    [owner]: { ...(value[owner] || empty()), text } })), [owner, write]);
  const setSelection = useCallback((selection: DraftModel) => write(value => ({ ...value,
    [owner]: { ...(value[owner] || empty()), selection } })), [owner, write]);
  const setAttachments = useCallback((action: SetStateAction<PendingAttachment[]>) => write(value => {
    const draft = value[owner] || empty();
    return { ...value, [owner]: { ...draft, attachments: typeof action === "function" ? action(draft.attachments) : action } };
  }), [owner, write]);
  const transfer = useCallback((from: string, to: string) => write(value => {
    if (!value[from || "new"]) return value;
    const next = { ...value, [to]: value[from || "new"] };
    delete next[from || "new"];
    return next;
  }), [write]);
  const remove = useCallback((id: string) => write(value => {
    const next = { ...value }; delete next[id]; return next;
  }), [write]);
  return { draft: records[owner] || empty(), setText, setSelection, setAttachments, transfer, remove };
}
