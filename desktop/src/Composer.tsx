import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
  type Dispatch,
  type SetStateAction,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import type { PendingAttachment, ReasoningOption } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { DesignSystemProvider, Icon, Menu, Switch } from "./design-system";
import "./chat.css";
import { ComposerModelPicker } from "./ComposerModelPicker";
import { useProviderQuota } from "./ProviderQuota";
import { autonomyLabels, autonomyProfiles } from "./autonomyProfiles";
import { coreApi } from "./coreApi";
import { composerInteractionRevision, useComposerFocus } from "./composerFocus";
import type { LiveController } from "./live/useLiveConversation";

interface ComposerProps {
  live?: LiveController;
  draft?: string;
  onDraftChange?: (text: string) => void;
  conversationId?: string;
  focusRequest?: number;
  focusAllowed?: boolean;
  theme?: ResolvedTheme;
  disabled?: boolean;
  running?: boolean;
  sendPending?: boolean;
  attachments: PendingAttachment[];
  provider?: string;
  model?: string;
  favoriteModels?: Array<{ provider: string; model: string }>;
  reasoningEffort?: string;
  reasoningOptions?: ReasoningOption[];
  autonomyMode?: string;
  localFastMode?: boolean;
  onFavoriteModel?: (item: {
    provider: string;
    model: string;
  }) => void | Promise<void>;
  onReasoningEffort?: (effort: string) => void | Promise<void>;
  onManageModels?: (trigger?: HTMLElement) => void;
  onAutonomyMode?: (mode: string) => void | Promise<void>;
  onLocalFastMode?: (enabled: boolean) => void | Promise<void>;
  onAttachments: Dispatch<SetStateAction<PendingAttachment[]>>;
  onSend: (text: string, isVoice?: boolean) => Promise<void>;
  onCancel: () => void;
}

async function pastedFile(file: File): Promise<PendingAttachment> {
  if (file.size > 25 * 1024 * 1024)
    throw new Error(`${file.name}: הקובץ גדול מ־25MB`);
  const bytes = Array.from(new Uint8Array(await file.arrayBuffer()));
  const path = await invoke<string>("stage_attachment", {
    name: file.name || "pasted-image.png",
    bytes,
  });
  return {
    draftId: crypto.randomUUID(),
    name: file.name || "תמונה שהודבקה.png",
    path,
    mime_type: file.type,
    kind: file.type.startsWith("image/") ? "image" : "file",
    size: file.size,
    previewUrl: file.type.startsWith("image/")
      ? URL.createObjectURL(file)
      : undefined,
  };
}
type VoiceState = {
  session_id: string;
  active: boolean;
  status: string;
  transcript: string;
  error: string;
  cancelled: boolean;
};
function DraftImage({ item }: { item: PendingAttachment }) {
  const [source, setSource] = useState(item.previewUrl || "");
  useEffect(() => {
    if (item.previewUrl) { setSource(item.previewUrl); return; }
    let disposed = false, url = "";
    setSource("");
    void invoke<number[]>("read_attachment_preview", { path: item.path }).then(bytes => {
      if (disposed) return;
      url = URL.createObjectURL(new Blob([new Uint8Array(bytes)], { type: item.mime_type || "image/png" }));
      setSource(url);
    }).catch(() => undefined);
    return () => { disposed = true; if (url) URL.revokeObjectURL(url); };
  }, [item.path, item.previewUrl, item.mime_type]);
  return source ? <img src={source} alt={item.name} /> : <i aria-label={`תמונה: ${item.name}`}>IMG</i>;
}
export function Composer({
  live,
  draft,
  onDraftChange,
  conversationId,
  focusRequest = 0,
  focusAllowed = true,
  theme = "dark",
  disabled,
  running,
  sendPending = false,
  attachments,
  provider = "",
  model = "",
  favoriteModels = [],
  reasoningEffort = "auto",
  reasoningOptions = [],
  autonomyMode = "balanced",
  localFastMode = false,
  onFavoriteModel = () => {},
  onReasoningEffort = () => {},
  onManageModels,
  onAutonomyMode = () => {},
  onLocalFastMode = () => {},
  onAttachments,
  onSend,
  onCancel,
}: ComposerProps) {
  const [localText, setLocalText] = useState("");
  const text = draft ?? localText;
  const setText = (value: string) => { if (onDraftChange) onDraftChange(value); else setLocalText(value); };
  const [listening, setListening] = useState(false);
  const startingVoice = useRef(false);
  const [voiceStarting, setVoiceStarting] = useState(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [error, setError] = useState("");
  const [staging, setStaging] = useState(0);
  const stagingCount = useRef(0);
  const sending = useRef(false);
  const [submittingOwner, setSubmittingOwner] = useState<string | null>(null);
  const submitting = submittingOwner === (conversationId || "new");
  const { summary: quotaSummary, refresh: refreshQuota } = useProviderQuota(provider, model);
  const area = useRef<HTMLTextAreaElement>(null);
  const requestFocus = useComposerFocus(area, conversationId, focusRequest,
    Boolean(disabled || listening || voiceStarting || submitting), focusAllowed);
  const textRef = useRef(text); textRef.current = text;
  const picker = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const input = picker.current;
    input?.addEventListener("cancel", requestFocus);
    return () => input?.removeEventListener("cancel", requestFocus);
  }, [requestFocus]);
  const voiceSession = useRef("");
  const voiceConsumed = useRef("");
  const owner = useRef(conversationId);
  useEffect(() => {
    setError("");
    if (owner.current !== conversationId && voiceSession.current) {
      voiceSession.current = "";
      setListening(false);
      void coreApi("POST", "/v2/audio/voice/stop", {}, true).catch(() => undefined);
      void invoke("desktop_hide_voice_overlay").catch(() => undefined);
    }
    owner.current = conversationId;
  }, [conversationId]);
  useLayoutEffect(() => {
    const node = area.current;
    if (!node) return;
    const fit = () => {
      node.style.height = "0px";
      // A wrapped placeholder is not draft content. It must not leave an
      // empty composer expanded after an initially narrow layout settles.
      node.style.height = `${Math.min(150, Math.max(38, node.value ? node.scrollHeight : 38))}px`;
    };
    fit();
    let width = node.clientWidth;
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(() => {
      if (node.clientWidth === width) return;
      width = node.clientWidth;
      fit();
    });
    observer?.observe(node);
    return () => observer?.disconnect();
  }, [text]);
  const stageFiles = async (files: File[]) => {
    if (!files.length) { requestFocus(); return; }
    const stageOwner = conversationId;
    const intent = composerInteractionRevision();
    stagingCount.current += 1;
    setStaging(stagingCount.current);
    try {
      const results = await Promise.allSettled(files.map(pastedFile));
      const added = results.flatMap((result) => result.status === "fulfilled" ? [result.value] : []);
      onAttachments((current) => [...current, ...added]);
      if (owner.current === stageOwner) setError(results.flatMap((result) => result.status === "rejected" ? [String(result.reason)] : []).join("\n"));
    } finally {
      stagingCount.current -= 1;
      setStaging(stagingCount.current);
      if (owner.current === stageOwner && intent === composerInteractionRevision()) requestFocus();
    }
  };
  const picked = async (files: FileList | null) => {
    await stageFiles(Array.from(files || []));
    if (picker.current) picker.current.value = "";
  };
  const paste = async (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files);
    if (!files.length) return;
    event.preventDefault();
    await stageFiles(files);
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    const files = Array.from(event.dataTransfer.files);
    void stageFiles(files);
  };
  const send = async () => {
    if ((!text.trim() && !attachments.length) || disabled || (running && !live?.active) || (live?.active && !live.ready) || sendPending || listening || startingVoice.current || sending.current || stagingCount.current) return;
    sending.current = true;
    setSubmittingOwner(conversationId || "new");
    setError("");
    const value = text;
    const sendOwner = conversationId;
    const intent = composerInteractionRevision();
    try {
      await onSend(value);
      if (!onDraftChange && owner.current === sendOwner && textRef.current === value) setText("");
    } catch (reason) {
      if (owner.current === sendOwner) setError(`ההודעה לא נשלחה: ${String(reason)}`);
    } finally {
      sending.current = false;
      setSubmittingOwner(null);
      if (owner.current === sendOwner && intent === composerInteractionRevision()) requestFocus();
    }
  };
  const key = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };
  const stopListening = async () => {
    try {
      await coreApi("POST", "/v2/audio/voice/stop", {}, true);
      await invoke("desktop_hide_voice_overlay");
      setListening(false); setError(""); requestFocus();
    } catch (reason) { setError(`לא ניתן להפסיק הכתבה: ${String(reason)}`); }
  };
  const listen = async () => {
    if (running || disabled || sendPending || startingVoice.current || sending.current || stagingCount.current) return;
    if (listening) {
      await stopListening();
      return;
    }
    const voiceOwner = owner.current;
    startingVoice.current = true; setVoiceStarting(true);
    setError("");
    try {
      const state = await coreApi<VoiceState>(
        "POST",
        "/v2/audio/voice",
        {},
        true,
      );
      if (!mounted.current || owner.current !== voiceOwner) {
        await coreApi("POST", "/v2/audio/voice/stop", {}, true);
        return;
      }
      voiceSession.current = state.session_id;
      voiceConsumed.current = "";
      await invoke("desktop_show_voice_overlay");
      setListening(true);
    } catch (reason) {
      void coreApi("POST", "/v2/audio/voice/stop", {}, true).catch(
        () => undefined,
      );
      setListening(false);
      void invoke("desktop_hide_voice_overlay");
      setError(`לא ניתן להפעיל זיהוי קולי: ${String(reason)}`);
    } finally { startingVoice.current = false; if (mounted.current) setVoiceStarting(false); }
  };
  useEffect(() => {
    if (!listening) return;
    let stopped = false;
    const poll = async () => {
      try {
        const state = await coreApi<VoiceState>(
          "GET",
          "/v2/audio/voice/status",
        );
        if (stopped || state.session_id !== voiceSession.current) return;
        setError("");
        if (state.active) return;
        setListening(false);
        requestFocus();
        void invoke("desktop_hide_voice_overlay");
        if (state.error) {
          setError(state.error);
          return;
        }
        if (state.transcript && voiceConsumed.current !== state.session_id) {
          voiceConsumed.current = state.session_id;
          try {
            await onSend(state.transcript, true);
          } catch (reason) {
            if (owner.current === conversationId) {
              if (!textRef.current) setText(state.transcript);
              setError(`התמלול לא נשלח: ${String(reason)}`);
            }
          }
        }
      } catch (reason) {
        if (!stopped) {
          setListening(false);
          void invoke("desktop_hide_voice_overlay");
          setError(`האזנה נפסקה: ${String(reason)}`);
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 350);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [listening, onSend]);
  const currentVoiceAction = useRef(listen);
  currentVoiceAction.current = listen;
  useEffect(() => {
    const activate = () => void currentVoiceAction.current();
    window.addEventListener("smarti:voice-hotkey", activate);
    return () => window.removeEventListener("smarti:voice-hotkey", activate);
  }, []);
  const canSend = Boolean(text.trim() || attachments.length);
  const separateLiveAction = Boolean(live?.available || live?.active);
  const liveAction = running && !live?.active ? "stop" : live?.active && !live.ready ? "loading"
    : canSend ? "send" : live?.active ? "close" : "start";
  return (
    <DesignSystemProvider theme={theme} className="composer-design"><div
      className={`composer ${running ? "is-running" : ""}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={drop}
    >
      {!!attachments.length && (
        <div className="pending-attachments">
          {attachments.map((item, index) =>
            item.kind === "image" ? (
              <span className="pending-image" key={`${item.path}-${index}`}>
                <DraftImage item={item} />
                <button
                  type="button"
                  aria-label={`הסרת ${item.name}`}
                  onClick={() => { onAttachments(current => current.filter(attachment => attachment !== item)); requestFocus(); }}
                >
                  <Icon name="close" size={18} />
                </button>
              </span>
            ) : (
              <span className="pending-file" key={`${item.path}-${index}`}>
                <i>
                  <Icon name="file" size={24} />
                </i>
                <b>{item.name}</b>
                <small>
                  File
                  {item.size
                    ? ` · ${Math.max(1, Math.round(item.size / 1024))} KB`
                    : ""}
                </small>
                <button
                  type="button"
                  aria-label={`הסרת ${item.name}`}
                  onClick={() => { onAttachments(current => current.filter(attachment => attachment !== item)); requestFocus(); }}
                >
                  <Icon name="close" size={18} />
                </button>
              </span>
            ),
          )}
        </div>
      )}
      {error && <p className="composer-error" role="alert" dir="rtl">{error}</p>}
      {attachments.filter(item => item.error).map(item => <p key={item.path} className="composer-error" role="alert" dir="rtl">{item.name}: {item.error}</p>)}
      <textarea
        ref={area}
        rows={1}
        value={text}
        disabled={disabled || listening || voiceStarting || submitting}
        placeholder="בקש כל דבר"
        onChange={(event) => setText(event.target.value)}
        onKeyDown={key}
        onPaste={paste}
        aria-label="הודעה"
        dir={text.trim() ? "auto" : "rtl"}
      />
      <input
        ref={picker}
        className="attachment-picker"
        type="file"
        multiple
        tabIndex={-1}
        onChange={(event) => void picked(event.target.files)}
      />
      <div className="composer-actions" dir="ltr">
        <span className="action-button-host">
          {(live?.available || live?.active) && <button className="composer-primary live-toggle" type="button"
            aria-label={liveAction === "send" ? "שליחה" : liveAction === "stop" ? "עצירה" : live.active ? "סגירת לייב" : "פתיחת לייב"}
            aria-busy={liveAction === "loading" || liveAction === "send" && submitting || undefined}
            disabled={Boolean(["send", "start"].includes(liveAction) && (disabled || listening || voiceStarting || submitting || sendPending || staging > 0))}
            onClick={() => {
              if (liveAction === "stop") { onCancel(); requestFocus(); }
              else if (liveAction === "send") void send();
              else if (live.active) void live.stop(); else void live.start();
            }}>
            {liveAction !== "start" ? <Icon name={liveAction === "loading" || submitting ? "loader" : liveAction === "send" ? "send" : liveAction === "stop" ? "stop" : "close"} size={22} /> : <svg className="sds-icon" data-icon="voice" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 10v4m4-7v10m4-14v18m4-14v10m4-7v4" /></svg>}
          </button>}
          <button
            className={`composer-primary ${separateLiveAction ? "is-plain-mic" : ""} ${canSend && !separateLiveAction ? "can-send" : ""} ${listening ? "is-listening" : ""}`}
            hidden={live?.active}
            type="button"
            aria-label={
              running && !separateLiveAction
                ? "עצירה"
                : listening
                  ? "הפסקת הכתבה"
                  : canSend && !separateLiveAction
                    ? "שליחה"
                    : "הכתבה קולית"
            }
            aria-busy={voiceStarting || submitting || undefined}
            disabled={separateLiveAction ? running || disabled || voiceStarting || submitting || sendPending || staging > 0 : !running && (disabled || voiceStarting || submitting || sendPending || staging > 0)}
            onClick={
              running && !separateLiveAction
                ? () => { onCancel(); requestFocus(); }
                : listening
                  ? () => void stopListening()
                  : canSend && !separateLiveAction
                  ? () => void send()
                  : () => void listen()
            }
          >
            <Icon name={(running && !separateLiveAction) || listening ? "stop" : canSend && !separateLiveAction ? "send" : "mic"} size={24} />
          </button>
          {live?.ready && <>
            <button className={`composer-tool live-mute ${live.outputMuted ? "is-muted" : ""}`} type="button" aria-label={live.outputMuted ? "ביטול השתקת סמארטי" : "השתקת סמארטי"} aria-pressed={live.outputMuted} onClick={live.toggleOutput}><Icon name="speaker" /></button>
            <button className={`composer-tool live-mute ${live.micMuted ? "is-muted" : ""}`} type="button" aria-label={live.micMuted ? "ביטול השתקת המיקרופון" : "השתקת המיקרופון"} aria-pressed={live.micMuted} onClick={() => void live.toggleMic()}><Icon name="mic" /></button>
          </>}
        </span>
        <div className="composer-controls">
          <div className="composer-selectors">
            <div className="composer-model-controls">
            <ComposerModelPicker theme={theme} provider={provider} model={model} favoriteModels={favoriteModels}
              reasoningEffort={reasoningEffort} reasoningOptions={reasoningOptions} quota={quotaSummary}
              onOpen={() => void refreshQuota(15)} onFavoriteModel={onFavoriteModel} onSelected={requestFocus}
              onReasoningEffort={onReasoningEffort} onManageModels={onManageModels} />
            {provider.toLowerCase() === "local" && (
              <label className="local-fast-mode" dir="rtl" title="FastMode"><span className="local-fast-mode-caption">FastMode</span><Switch label="FastMode" checked={localFastMode} onCheckedChange={value => void onLocalFastMode(value)} /></label>
            )}
            </div>
            <span className="autonomy-quick-pill"><Menu label="פרופיל בטיחות" icon="shield" fitContent items={autonomyProfiles.map(profile => ({
              id: profile.value, label: profile.label, description: profile.description, icon: profile.icon,
              onSelect: () => void onAutonomyMode(profile.value),
            }))}><span>{autonomyLabels[autonomyMode] || autonomyLabels.balanced}</span></Menu></span>
          </div>
        </div>
        <button
          className="composer-tool"
          type="button"
          aria-label="צירוף קובץ"
          onClick={() => picker.current?.click()}
        >
          <Icon name="plus" size={24} />
        </button>
      </div>
    </div></DesignSystemProvider>
  );
}
