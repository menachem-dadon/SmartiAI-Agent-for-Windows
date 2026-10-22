import { useEffect, useRef, useState } from "react";
import { coreApi, encodePath } from "../coreApi";
import { subscribeSettingsChanges } from "../settingsChanges";
import { setLiveSpeechSuspended } from "../speechPlayback";
import type { ChatMessage, PendingAttachment } from "../chatTypes";
import { LiveAudio } from "./liveAudio";
import { LiveActivity } from "./liveActivity";
import { LiveCaptions } from "./liveCaptions";
import { LiveTransport } from "./liveTransport";
import type { OrbState } from "./SmartyLiveOrb";

export type LiveProvider = { id: string; label: string; model: string; voices: string[]; voice: string; configured: boolean; inherited: boolean; masked: string };
export type LiveConfig = { provider: string; enabled: boolean; language: string; available: boolean; items: LiveProvider[];
  max_session_seconds?: number; daily_seconds_limit?: number };
export type LiveTask = { id: string; run_id: string; status: string; pause_requested?: boolean };
type Session = { id: string; conversation_id: string; phase: string; error: string; tasks: LiveTask[];
  next_input_sequence?: number; cursor?: number; audio_ms?: number; mic_muted?: boolean; output_muted?: boolean };
type Event = { sequence: number; type: string; phase?: string; message?: ChatMessage | string; audio?: string; rate?: number; start_ms?: number; end_ms?: number; task?: LiveTask; admission_id?: string; error?: string };
type Receipt = { accepted: boolean; admission_id?: string };
type Input = { audio?: string; text?: string; attachment_handles?: string[]; mic_muted?: boolean; playback_ms?: number; output_muted?: boolean;
  dropped_audio?: number[][]; provider_mode?: string; model_name?: string };
export type LiveController = ReturnType<typeof useLiveConversation>;

export function useLiveConversation(options: {
  coreReady: boolean; coreGeneration: number;
  beforeModelUse?: () => Promise<void>;
  conversation: string; provider: string; model: string; attachments: PendingAttachment[];
  onConversation: (id: string) => void; onMessage: (message: ChatMessage) => void;
  onNewUserMessage: (id: string) => void;
  onRefresh: () => void; onError: (message: string) => void;
}) {
  const current = useRef(options); current.current = options;
  const [config, setConfig] = useState<LiveConfig | null>(null);
  const [phase, setPhase] = useState("closed");
  const [micMuted, setMicMuted] = useState(false), [outputMuted, setOutputMuted] = useState(false);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [tasks, setTasks] = useState<LiveTask[]>([]);
  const level = useRef(0);
  const captions = useRef(new LiveCaptions());
  const [, redrawCaptions] = useState(0);
  const session = useRef<Session | null>(null), generation = useRef(0), audio = useRef<LiveAudio | null>(null);
  const sequence = useRef(0), queued = useRef(0), starting = useRef(false);
  const transport = useRef<LiveTransport | null>(null);
  const mounted = useRef(true);
  const startupOwner = useRef(""), taskBusy = useRef(false);
  const admissions = useRef(new Map<string, { resolve: () => void; reject: (error: Error) => void }>());
  const admitted = useRef(new Map<string, string>());
  const playbackMuted = useRef(false);
  useEffect(() => { setLiveSpeechSuspended(phase !== "closed"); return () => setLiveSpeechSuspended(false); }, [phase]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; void stop(); }; }, []);
  useEffect(() => {
    if (!options.coreReady) { setConfig(null); return; }
    let alive = true, revision = 0, attempts = 0, timer = 0;
    const refresh = async () => {
      const request = ++revision; window.clearTimeout(timer);
      try {
        const value = await coreApi<LiveConfig>("GET", "/v2/live/config");
        if (alive && request === revision) { attempts = 0; setConfig(value); }
      } catch {
        if (alive && request === revision) timer = window.setTimeout(refresh, Math.min(10000, 500 * 2 ** Math.min(attempts++, 5)));
      }
    };
    void refresh();
    const unsubscribe = subscribeSettingsChanges(() => { attempts = 0; void refresh(); });
    return () => { alive = false; revision++; window.clearTimeout(timer); unsubscribe(); };
  }, [options.coreReady, options.coreGeneration]);
  useEffect(() => {
    if ((session.current && options.conversation !== session.current.conversation_id) ||
        (starting.current && !session.current && options.conversation !== startupOwner.current)) void stop();
  }, [options.conversation]);
  const sendInput = (input: Input) => {
    const channel = transport.current;
    if (!session.current || !channel) return Promise.reject(new Error("הלייב אינו פעיל"));
    // Never queue seconds of stale microphone data behind HTTP/control receipts.
    if (input.audio && queued.current >= 12) return Promise.resolve<Receipt>({ accepted: true });
    queued.current++;
    return channel.send({ ...input, dropped_audio: audio.current?.droppedRanges, sequence: sequence.current++ })
      .finally(() => { queued.current--; });
  };
  async function stop() {
    generation.current++; starting.current = false;
    const owned = session.current; session.current = null;
    transport.current?.close(); transport.current = null;
    for (const pending of admissions.current.values()) pending.reject(new Error("הלייב נסגר לפני שההודעה עם הקבצים אושרה"));
    admissions.current.clear(); admitted.current.clear();
    audio.current?.dispose(); audio.current = null; level.current = 0;
    captions.current = new LiveCaptions();
    if (mounted.current) { setPhase("closed"); setOrbState("idle"); setTasks([]); }
    if (owned) {
      try { await coreApi("POST", `/v2/live/sessions/${owned.id}/stop`, {}); }
      catch (error) { if (mounted.current) current.current.onError(`לא התקבל אישור סגירת הלייב. החיבור ייסגר אוטומטית: ${String(error)}`); }
      current.current.onRefresh();
    }
  }
  const fail = (error: unknown) => { if (mounted.current) current.current.onError(String(error)); void stop(); };
  useEffect(() => {
    if (phase === "closed" || phase === "starting") return;
    const revision = generation.current;
    // Playback acknowledgement is distinct from generated text and vendor ACKs.
    // Also keep it flowing when the microphone is muted.
    const timer = window.setInterval(() => {
      if (generation.current === revision && !queued.current)
        void sendInput({ playback_ms: audio.current?.playedMs || 0, output_muted: playbackMuted.current }).catch(() => undefined);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [phase]);
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
    setPhase("starting"); setMicMuted(false); setOutputMuted(false); playbackMuted.current = false; taskBusy.current = false;
    captions.current = new LiveCaptions();
    const activity = new LiveActivity(), seenUsers = new Set<string>();
    const engine = new LiveAudio(value => { void sendInput({ audio: value, playback_ms: audio.current?.playedMs || 0,
      output_muted: playbackMuted.current }).catch(error => { if (generation.current === revision) current.current.onError(String(error)); }); }, (user, smarty) => {
      if (generation.current !== revision) return;
      const sample = activity.sample(user, smarty, performance.now(), taskBusy.current);
      level.current = sample.level;
      setOrbState(previous => previous === sample.state ? previous : sample.state);
    }, playedMs => { if (generation.current === revision && captions.current.tick(playedMs, playbackMuted.current)) redrawCaptions(value => value + 1); },
    message => { if (generation.current === revision) current.current.onError(message); });
    audio.current = engine;
    try {
      await engine.prepare();
      await current.current.beforeModelUse?.();
      if (revision !== generation.current) return;
      let owner = requested.conversation;
      if (!owner) owner = (await coreApi<{ conversation: { id: string } }>("POST", "/v2/conversations", {}, true)).conversation.id;
      const attachment_handles = await handles(requested.attachments, owner);
      if (revision !== generation.current) return;
      const opened = await coreApi<Session>("POST", "/v2/live/sessions", { conversation_id: owner, provider_mode: current.current.provider, model_name: current.current.model, attachment_handles });
      if (revision !== generation.current) { await coreApi("POST", `/v2/live/sessions/${opened.id}/stop`, {}); return; }
      session.current = opened; sequence.current = opened.next_input_sequence ?? 0;
      engine.rebase(opened.audio_ms || 0);
      engine.muteMic(Boolean(opened.mic_muted)); setMicMuted(Boolean(opened.mic_muted));
      engine.muteOutput(Boolean(opened.output_muted)); playbackMuted.current = Boolean(opened.output_muted); setOutputMuted(Boolean(opened.output_muted));
      current.current.onConversation(opened.conversation_id);
      if (opened.next_input_sequence) current.current.onRefresh();
      const channel = new LiveTransport(opened.id, opened.cursor || 0, () => {
        if (generation.current === revision) setPhase("reconnecting");
      });
      transport.current = channel; await channel.open();
      let cursor = opened.cursor || 0, began = false;
      while (revision === generation.current) {
        const page = await channel.next<Session & { events: Event[]; cursor: number; gap: boolean }>(cursor);
        if (revision !== generation.current) break;
        if (page.gap) { captions.current.interrupt(engine.playedMs); engine.rebase(page.audio_ms || 0); current.current.onRefresh(); }
        cursor = page.cursor;
        setTasks(previous => JSON.stringify(previous.map(task => [task.id, task.status, task.pause_requested])) === JSON.stringify(page.tasks.map(task => [task.id, task.status, task.pause_requested])) ? previous : page.tasks);
        setPhase(page.phase);
        taskBusy.current = page.tasks.some(task => !task.pause_requested && ["queued", "running", "waiting_for_approval", "waiting_for_input"].includes(task.status));
        for (const event of page.events) {
          if (event.type === "message" && event.message && typeof event.message !== "string") {
            const message: ChatMessage = { ...event.message, metadata: { ...event.message.metadata, live_reveal: true } };
            const id = String(message.metadata?.live_message_id || message.message_id || "");
            captions.current.update(message); captions.current.tick(engine.playedMs, playbackMuted.current);
            current.current.onMessage(message);
            if (message.role === "user" && id && !seenUsers.has(id)) {
              seenUsers.add(id); current.current.onNewUserMessage(id);
            }
          }
          if (event.type === "notice" && typeof event.message === "string") current.current.onError(event.message);
          if (event.type === "audio" && event.audio && !engine.play(event.audio, event.rate, event.start_ms)) current.current.onError("נוקה תור שמע שהתארך באופן חריג. השיחה והמשימה ממשיכות; התמלול המלא זמין בצ׳אט.");
          if (event.type === "interrupt") { captions.current.interrupt(engine.playedMs); engine.interrupt(); redrawCaptions(value => value + 1); }
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
  useEffect(() => {
    if (!session.current || phase !== "ready") return;
    let alive = true;
    void (async () => {
      await current.current.beforeModelUse?.();
      if (alive) await sendInput({ provider_mode: options.provider, model_name: options.model });
    })().catch(error => { if (alive) current.current.onError(String(error)); });
    return () => { alive = false; };
  }, [options.provider, options.model, phase]);
  const toggleMic = async () => {
    const revision = generation.current;
    const next = !micMuted;
    audio.current?.muteMic(next); setMicMuted(next);
    try { await sendInput({ mic_muted: next }); } catch (error) { if (generation.current === revision) fail(error); }
  };
  const toggleOutput = () => { const next = !outputMuted; playbackMuted.current = next; setOutputMuted(next); audio.current?.muteOutput(next); captions.current.tick(audio.current?.playedMs || 0, next); redrawCaptions(value => value + 1); };
  const send = async (text: string, attachments: PendingAttachment[]) => {
    const owned = session.current;
    if (!owned || phase !== "ready") throw new Error("יש להמתין להכנת מנוע הלייב");
    await current.current.beforeModelUse?.();
    await sendInput({ provider_mode: current.current.provider, model_name: current.current.model });
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
    micMuted, outputMuted, orbState, level, tasks, start, stop, toggleMic, toggleOutput, send, control,
    present: (message: ChatMessage) => captions.current.present(message) };
}
