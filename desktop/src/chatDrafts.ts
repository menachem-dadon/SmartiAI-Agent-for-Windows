import { useCallback, useEffect, useRef, useState, type SetStateAction } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { PendingAttachment } from "./chatTypes";

const legacyKey = "smarti.desktop.chat-drafts.v1";
const storageKey = "smarti.desktop.chat-drafts.v2";
const activeKey = "smarti.desktop.active-conversation.v1";
const launchKey = "smarti.desktop.chat-launch.v1";
export function readActiveConversation(): string {
  try { return sessionStorage.getItem(activeKey) || ""; } catch { return ""; }
}
export function rememberActiveConversation(id: string): boolean {
  try {
    if (id) sessionStorage.setItem(activeKey, id); else sessionStorage.removeItem(activeKey);
    return true;
  } catch { return false; }
}
export function beginChatLaunch(id: string | null): boolean {
  if (!id) return false;
  try {
    if (sessionStorage.getItem(launchKey) === id) return false;
    sessionStorage.setItem(launchKey, id);
    rememberActiveConversation("");
  } catch { /* Storage lifetime must not turn a new host into a reload. */ }
  return true;
}
export function restoreActiveConversation(conversations: readonly { id: string }[], wanted: string): string {
  // Only recover a selection made in this WebView session. A fresh launch (or
  // a deleted selection) starts with a blank chat, regardless of saved history.
  return conversations.some(item => item.id === wanted) ? wanted : "";
}
export type DraftModel = { provider: string; model: string; effort: string; endpoint?: string };
export type ChatDraft = { text: string; attachments: PendingAttachment[]; selection?: DraftModel };
const empty = (): ChatDraft => ({ text: "", attachments: [] });
const ownerKey = (id: string) => id || "new";
const serialize = (value: unknown) => JSON.stringify(value, (key, item) => key === "previewUrl" ? undefined : item);

// Unsent UI state persists across native launches. Messages/settings remain
// owned by Core; secret dialogs never use this store. Files are stored natively.
export function readDrafts(): Record<string, ChatDraft> {
  let raw: string | null = null;
  try { raw = localStorage.getItem(storageKey); } catch { /* Try legacy recovery. */ }
  try {
    raw ??= sessionStorage.getItem(legacyKey);
    const value = JSON.parse(raw || "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).flatMap(([id, raw]) => {
      if (!raw || typeof raw !== "object") return [];
      const draft = raw as ChatDraft;
      return [[id, { text: typeof draft.text === "string" ? draft.text : "",
        attachments: Array.isArray(draft.attachments) ? draft.attachments.filter(item =>
          item && typeof item.path === "string" && typeof item.name === "string").map(item => ({ ...item, draftId: item.draftId || crypto.randomUUID() })) : [],
        selection: draft.selection && typeof draft.selection.provider === "string" && typeof draft.selection.model === "string" && typeof draft.selection.effort === "string" ? draft.selection : undefined }]];
    }));
  } catch { return {}; }
}

export function useChatDrafts(sessionId: string, onStorageError: (message: string) => void) {
  const [records, setRecords] = useState(readDrafts);
  const current = useRef(records);
  const errorHandler = useRef(onStorageError);
  errorHandler.current = onStorageError;
  const owner = ownerKey(sessionId);
  const write = useCallback((update: (value: Record<string, ChatDraft>) => Record<string, ChatDraft>) => {
    const next = update(current.current);
    current.current = next;
    setRecords(next);
    let saved = false;
    try { localStorage.setItem(storageKey, serialize(next)); saved = true; }
    catch { errorHandler.current("לא ניתן לשמור את הטיוטה לסגירה מלאה. הטיוטה נשארת פתוחה; העתק אותה לפני יציאה."); }
    try { sessionStorage.setItem(legacyKey, serialize(next)); } catch { /* Durable copy is authoritative. */ }
    return saved;
  }, []);
  useEffect(() => {
    if (Object.keys(current.current).length) write(value => value);
    if (!("__TAURI_INTERNALS__" in window)) return;
    let disposed = false;
    for (const [id, draft] of Object.entries(current.current)) for (const attachment of draft.attachments) {
      void invoke<string>("retain_draft_attachment", { path: attachment.path }).then(path => {
        if (disposed) return;
        if (!path) throw new Error("missing attachment");
        write(value => {
          const latest = value[id];
          if (!latest || !latest.attachments.some(item => item.path === attachment.path)) return value;
          return { ...value, [id]: { ...latest, attachments: latest.attachments.map(item => item.path === attachment.path ? { ...item, path, submissionPath: item.submissionPath || item.path, error: undefined } : item) } };
        });
      }).catch(() => {
        if (disposed) return;
        write(value => {
          const latest = value[id];
          if (!latest) return value;
          return { ...value, [id]: { ...latest, attachments: latest.attachments.map(item => item.path === attachment.path ? { ...item, error: "הקובץ המצורף אינו זמין. הסר אותו וצרף אותו מחדש." } : item) } };
        });
      });
    }
    return () => { disposed = true; };
  }, [write]);
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
  const snapshot = useCallback((id: string) => current.current[ownerKey(id)] || empty(), []);
  const accept = useCallback((from: string, to: string, submitted: ChatDraft, text: string, follow: boolean) => write(value => {
    const key = ownerKey(from), latest = value[key] || empty();
    const rest = { ...latest, text: latest.text === submitted.text && submitted.text === text ? "" : latest.text,
      attachments: latest.attachments.filter(item => !submitted.attachments.some(sent => sent.draftId ? sent.draftId === item.draftId : sent.path === item.path)) };
    // An explicit new-chat navigation while delivering keeps the shared draft.
    return !from && follow ? { ...value, [to]: rest, new: empty() } : { ...value, [key]: rest };
  }), [write]);
  const remove = useCallback((id: string) => write(value => {
    const next = { ...value }; delete next[id]; return next;
  }), [write]);
  return { draft: records[owner] || empty(), setText, setSelection, setAttachments, transfer, remove, snapshot, accept };
}
