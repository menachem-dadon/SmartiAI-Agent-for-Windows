import { useRef, useState, useSyncExternalStore } from "react";
import { invoke } from "@tauri-apps/api/core";
import { coreApi } from "./coreApi";

interface SpeechState {
  protocol_version: number;
  request_id: string;
  owner_id: string;
  is_playing: boolean;
  error: string;
}
const idle: SpeechState = { protocol_version: 1, request_id: "", owner_id: "", is_playing: false, error: "" };
let state = idle;
let revision = 0;
let timer: ReturnType<typeof setInterval> | undefined;
let polling = false;
let refreshAttempted = false;
let refreshPromise: Promise<SpeechState> | undefined;
const listeners = new Set<() => void>();
const snapshot = () => state;
function publish(next: SpeechState) {
  state = next;
  for (const listener of listeners) listener();
}

function isLegacySpeech(next: SpeechState) {
  return typeof next?.is_playing === "boolean" && next.protocol_version !== 1;
}

async function synchronizeSpeechService(next: SpeechState): Promise<SpeechState> {
  if (!isLegacySpeech(next)) return next;
  if (refreshPromise) return refreshPromise;
  const outdated = "שירות ההקראה עדיין בגרסה הישנה. יש להפעיל מחדש את Smarti כדי לטעון את התיקון.";
  if (refreshAttempted) throw new Error(outdated);
  refreshPromise = (async () => {
    // A Vite refresh can replace React while the supervised Python process
    // still holds the old request schema. Restart only an idle Core, through
    // its normal graceful shutdown path; never interrupt an active run.
    const runs = await coreApi<{ items: unknown[] }>("GET",
      "/v2/runs?status=queued&status=running&status=waiting_for_approval&status=waiting_for_input&limit=1");
    if (!Array.isArray(runs?.items) || runs.items.length || next.is_playing)
      throw new Error("שירות ההקראה זקוק לרענון. נסה שוב לאחר סיום המשימות וההקראה הפעילות.");
    refreshAttempted = true;
    await invoke("core_restart");
    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      const core = await invoke<{ state: string }>("core_status");
      if (core.state === "ready") {
        const fresh = await coreApi<SpeechState>("GET", "/v2/audio/tts/status");
        if (isLegacySpeech(fresh)) throw new Error(outdated);
        return fresh;
      }
      if (["fatal", "crashed", "stopped"].includes(core.state)) break;
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    throw new Error("שירות ההקראה לא סיים לעלות. אפשר לנסות שוב לאחר שהאפליקציה מוכנה.");
  })();
  try { return await refreshPromise; }
  finally { refreshPromise = undefined; }
}

async function poll() {
  if (polling) return;
  polling = true;
  const current = revision;
  try {
    const next = await synchronizeSpeechService(await coreApi<SpeechState>("GET", "/v2/audio/tts/status"));
    if (current === revision && listeners.size && typeof next?.is_playing === "boolean") publish(next);
  } catch (reason) {
    if (current === revision && listeners.size && state.is_playing)
      publish({ ...state, is_playing: false, error: `לא ניתן לבדוק את מצב ההקראה: ${String(reason)}` });
  } finally { polling = false; }
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (!timer) {
    timer = setInterval(() => void poll(), 900);
    void poll();
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      clearInterval(timer); timer = undefined;
      revision += 1;
      state = idle;
    }
  };
}

// A single poll serves every message and the settings preview. Ownership also
// connects automatic answer speech to its existing message's stop button.
export function useSpeechPlayback(ownerId: string) {
  const current = useSyncExternalStore(subscribe, snapshot, () => idle);
  const [pending, setPending] = useState(false);
  const [localError, setLocalError] = useState("");
  const inFlight = useRef(false);
  const speaking = current.owner_id === ownerId && current.is_playing;
  const error = localError || (current.owner_id === ownerId ? current.error : "");
  const toggle = async (text: string) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true); setLocalError("");
    const operation = ++revision;
    try {
      await synchronizeSpeechService(await coreApi<SpeechState>("GET", "/v2/audio/tts/status"));
      const next = speaking
        ? await coreApi<SpeechState>("POST", "/v2/audio/tts/stop", { request_id: current.request_id }, true)
        : await coreApi<SpeechState>("POST", "/v2/audio/tts", { text, owner_id: ownerId }, true);
      if (operation === revision) {
        revision += 1; // Discard status reads that began during this command.
        publish(next);
      }
    } catch (reason) {
      setLocalError(`ההקראה נכשלה: ${String(reason)}`);
    } finally {
      inFlight.current = false; setPending(false);
    }
  };
  return { speaking, pending, error, toggle };
}
