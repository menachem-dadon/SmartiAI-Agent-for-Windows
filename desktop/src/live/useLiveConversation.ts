import { useEffect, useRef, useState } from "react";
import { coreApi, encodePath } from "../coreApi";
import { subscribeSettingsChanges } from "../settingsChanges";
import { setLiveSpeechSuspended } from "../speechPlayback";
import type { ChatMessage, PendingAttachment } from "../chatTypes";
import { LiveAudio } from "./liveAudio";
import type { OrbState } from "./SmartyLiveOrb";

export type LiveProvider = { id: string; label: string; model: string; voices: string[]; voice: string; configured: boolean; inherited: boolean; masked: string };
export type LiveConfig = { provider: string; available: boolean; items: LiveProvider[] };
export type LiveTask = { id: string; run_id: string; status: string; pause_requested?: boolean };
type Session = { id: string; conversation_id: string; phase: string; error: string; tasks: LiveTask[] };
type Event = { sequence: number; type: string; phase?: string; message?: ChatMessage | string; audio?: string; rate?: number; task?: LiveTask; admission_id?: string; error?: string };
type Receipt = { accepted: boolean; admission_id?: string };
type Input = { audio?: string; text?: string; attachment_handles?: string[]; mic_muted?: boolean };
export type LiveController = ReturnType<typeof useLiveConversation>;

export function useLiveConversation(options: {
  conversation: string; provider: string; model: string; attachments: PendingAttachment[];
  onConversation: (id: string) => void; onMessage: (message: ChatMessage) => void;
  onRefresh: () => void; onError: (message: string) => void;
}) {
  const current = useRef(options); current.current = options;
  const [config, setConfig] = useState<LiveConfig | null>(null);
  const [phase, setPhase] = useState("closed");
  const [micMuted, setMicMuted] = useState(false), [outputMuted, setOutputMuted] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [tasks, setTasks] = useState<LiveTask[]>([]);
  const level = useRef(0), levels = useRef({ user: 0, smarty: 0 });
  const session = useRef<Session | null>(null), generation = useRef(0), audio = useRef<LiveAudio | null>(null);
  const sequence = useRef(0), writes = useRef(Promise.resolve()), queued = useRef(0), starting = useRef(false);
  const mounted = useRef(true);
  const startupOwner = useRef(""), taskBusy = useRef(false);
  const admissions = useRef(new Map<string, { resolve: () => void; reject: (error: Error) => void }>());
  const admitted = useRef(new Map<string, string>());
  useEffect(() => { setLiveSpeechSuspended(phase !== "closed"); return () => setLiveSpeechSuspended(false); }, [phase]);
  const refresh = () => { void coreApi<LiveConfig>("GET", "/v2/live/config").then(value => { if (mounted.current) setConfig(value); }).catch(() => undefined); };
  useEffect(() => { mounted.current = true; refresh(); const unsubscribe = subscribeSettingsChanges(refresh); return () => { mounted.current = false; unsubscribe(); void stop(); }; }, []);
  useEffect(() => {
    if ((session.current && options.conversation !== session.current.conversation_id) ||
        (starting.current && !session.current && options.conversation !== startupOwner.current)) void stop();
  }, [options.conversation]);
  const sendInput = (input: Input) => {
    const owned = session.current, revision = generation.current, order = sequence.current++;
    if (!owned) return Promise.reject(new Error("הלייב אינו פעיל"));
    if (++queued.current > 30) { queued.current--; return Promise.reject(new Error("שליחת השמע מתעכבת; יש לחדש את הלייב")); }
    const write = writes.current.then(async () => {
      if (revision !== generation.current) return;
      return await coreApi<Receipt>("POST", `/v2/live/sessions/${owned.id}/input`, { ...input, sequence: order });
    });
    writes.current = write.then(() => undefined, () => undefined);
    return write.finally(() => { queued.current--; });
  };
  async function stop() {
    generation.current++; starting.current = false;
    const owned = session.current; session.current = null;
    for (const pending of admissions.current.values()) pending.reject(new Error("הלייב נסגר לפני שההודעה עם הקבצים אושרה"));
    admissions.current.clear(); admitted.current.clear();
    audio.current?.dispose(); audio.current = null; level.current = 0;
    if (mounted.current) { setPhase("closed"); setOrbState("idle"); setTasks([]); }
    if (owned) {
      try { await coreApi("POST", `/v2/live/sessions/${owned.id}/stop`, {}); }
      catch (error) { if (mounted.current) current.current.onError(`לא התקבל אישור סגירת הלייב. החיבור ייסגר אוטומטית: ${String(error)}`); }
      current.current.onRefresh();
    }
  }
  const fail = (error: unknown) => { if (mounted.current) current.current.onError(String(error)); void stop(); };
  const handles = async (attachments: PendingAttachment[], owner: string) => {
    const registered: string[] = [];
    for (const item of attachments) {
      if (item.error) throw new Error(`${item.name}: ${item.error}`);
      const result = await coreApi<{ attachment: { handle: string } }>("POST", "/v2/attachments", { path: item.path, session_id: owner }, true);
      registered.push(result.attachment.handle);
    }
    return registered;
  };
  async function start() {
    if (starting.current || session.current) return;
    starting.current = true; const revision = ++generation.current;
    const requested = { ...current.current, attachments: [...current.current.attachments] };
    startupOwner.current = requested.conversation;
    setPhase("starting"); setMicMuted(false); setOutputMuted(false); levels.current = { user: 0, smarty: 0 };
    const engine = new LiveAudio(value => { void sendInput({ audio: value }).catch(error => { if (generation.current === revision) fail(error); }); }, (value, speaker) => {
      if (generation.current !== revision) return;
      levels.current[speaker] = value;
      const speaking = levels.current.smarty > .003;
      level.current = speaking ? levels.current.smarty : levels.current.user;
      setOrbState(speaking ? "smartySpeaking" : levels.current.user > .025 ? "userSpeaking" : taskBusy.current ? "thinking" : "listening");
    });
    audio.current = engine;
    try {
      await engine.prepare();
      if (revision !== generation.current) return;
      let owner = requested.conversation;
      if (!owner) owner = (await coreApi<{ conversation: { id: string } }>("POST", "/v2/conversations", {}, true)).conversation.id;
      const attachment_handles = await handles(requested.attachments, owner);
      if (revision !== generation.current) return;
      const opened = await coreApi<Session>("POST", "/v2/live/sessions", { conversation_id: owner, provider_mode: requested.provider, model_name: requested.model, attachment_handles });
      if (revision !== generation.current) { await coreApi("POST", `/v2/live/sessions/${opened.id}/stop`, {}); return; }
      session.current = opened; sequence.current = 0; writes.current = Promise.resolve();
      current.current.onConversation(opened.conversation_id);
      let cursor = 0, began = false;
      while (revision === generation.current) {
        const page = await coreApi<Session & { events: Event[]; cursor: number; gap: boolean }>("GET", `/v2/live/sessions/${opened.id}/events?after=${cursor}`);
        if (revision !== generation.current) break;
        if (page.gap) { engine.interrupt(); current.current.onRefresh(); }
        cursor = page.cursor;
        setTasks(previous => JSON.stringify(previous.map(task => [task.id, task.status, task.pause_requested])) === JSON.stringify(page.tasks.map(task => [task.id, task.status, task.pause_requested])) ? previous : page.tasks);
        setPhase(page.phase);
        taskBusy.current = page.tasks.some(task => !task.pause_requested && ["queued", "running", "waiting_for_approval", "waiting_for_input"].includes(task.status));
        for (const event of page.events) {
          if (event.type === "message" && event.message && typeof event.message !== "string") current.current.onMessage(event.message);
          if (event.type === "notice" && typeof event.message === "string") current.current.onError(event.message);
          if (event.type === "audio" && event.audio) engine.play(event.audio, event.rate);
          if (event.type === "interrupt") engine.interrupt();
          if (event.type === "input_accepted" && event.admission_id) {
            const pending = admissions.current.get(event.admission_id);
            if (pending) { admissions.current.delete(event.admission_id); if (event.error) pending.reject(new Error(event.error)); else pending.resolve(); }
            else admitted.current.set(event.admission_id, event.error || "");
          }
        }
        if (page.phase === "ready" && !began) { began = true; engine.begin(); setOrbState("listening"); }
        if (page.phase === "closed") { if (page.error) current.current.onError(page.error); await stop(); break; }
      }
    } catch (error) { if (revision === generation.current) fail(error); }
    finally { if (revision === generation.current) starting.current = false; }
  }
  const toggleMic = async () => {
    const revision = generation.current;
    const next = !micMuted;
    audio.current?.muteMic(next); setMicMuted(next);
    try { await sendInput({ mic_muted: next }); } catch (error) { if (generation.current === revision) fail(error); }
  };
  const toggleOutput = () => { const next = !outputMuted; setOutputMuted(next); audio.current?.muteOutput(next); };
  const send = async (text: string, attachments: PendingAttachment[]) => {
    const owned = session.current;
    if (!owned || phase !== "ready") throw new Error("יש להמתין להכנת מנוע הלייב");
    const receipt = await sendInput({ text, attachment_handles: await handles(attachments, owned.conversation_id) });
    if (receipt?.admission_id) {
      const id = receipt.admission_id;
      if (admitted.current.has(id)) { const error = admitted.current.get(id); admitted.current.delete(id); if (error) throw new Error(error); }
      else await new Promise<void>((resolve, reject) => admissions.current.set(id, { resolve, reject }));
    }
  };
  const control = async (task: LiveTask, action: "pause" | "resume" | "cancel") => {
    if (!session.current) return;
    try { await coreApi("POST", `/v2/live/sessions/${encodePath(session.current.id)}/control`, { task_id: task.id, action }); }
    catch (error) { current.current.onError(String(error)); }
  };
  return { available: Boolean(config?.available), active: phase !== "closed", ready: phase === "ready", phase,
    micMuted, outputMuted, orbState, level, tasks, start, stop, toggleMic, toggleOutput, send, control };
}
