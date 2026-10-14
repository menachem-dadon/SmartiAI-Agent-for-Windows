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
import { quotaResetLabel } from "./quotaPresentation";
import { autonomyLabels, autonomyProfiles } from "./autonomyProfiles";
import { coreApi } from "./coreApi";

interface ComposerProps {
  draft?: string;
  onDraftChange?: (text: string) => void;
  conversationId?: string;
  theme?: ResolvedTheme;
  disabled?: boolean;
  running?: boolean;
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
type QuotaWindow = {
  remaining_percent: number;
  resets_at?: number;
  window_minutes?: number;
};
type CodexQuota = {
  available: boolean;
  plan_type?: string;
  five_hour?: QuotaWindow | null;
  weekly?: QuotaWindow | null;
  fetched_at?: number;
};
type VoiceState = {
  session_id: string;
  active: boolean;
  status: string;
  transcript: string;
  error: string;
  cancelled: boolean;
};
export function Composer({
  draft,
  onDraftChange,
  conversationId,
  theme = "dark",
  disabled,
  running,
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
  const [submitting, setSubmitting] = useState(false);
  const [quota, setQuota] = useState<CodexQuota | null>(null);
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [quotaError, setQuotaError] = useState("");
  const quotaFetchedAt = useRef(0);
  const area = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
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
  const refreshQuota = async (minimumAgeSeconds = 0) => {
    if (
      provider !== "openai_codex_signin" ||
      quotaLoading ||
      (quotaFetchedAt.current &&
        Date.now() - quotaFetchedAt.current < minimumAgeSeconds * 1000)
    )
      return;
    setQuotaLoading(true);
    setQuotaError("");
    try {
      const data = await coreApi<CodexQuota>(
        "GET",
        "/v2/providers/openai_codex_signin/quota",
      );
      setQuota(data);
      quotaFetchedAt.current = Date.now();
    } catch (reason) {
      setQuotaError(String(reason));
    } finally {
      setQuotaLoading(false);
    }
  };
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
  useEffect(() => {
    if (provider !== "openai_codex_signin") {
      setQuota(null);
      setQuotaError("");
      return;
    }
    const first = window.setTimeout(() => void refreshQuota(15), 1600);
    const timer = window.setInterval(() => void refreshQuota(15), 60_000);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [provider]);
  const stageFiles = async (files: File[]) => {
    if (!files.length) return;
    stagingCount.current += 1;
    setStaging(stagingCount.current);
    try {
      const results = await Promise.allSettled(files.map(pastedFile));
      const added = results.flatMap((result) => result.status === "fulfilled" ? [result.value] : []);
      onAttachments((current) => [...current, ...added]);
      setError(results.flatMap((result) => result.status === "rejected" ? [String(result.reason)] : []).join("\n"));
    } finally {
      stagingCount.current -= 1;
      setStaging(stagingCount.current);
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
    if ((!text.trim() && !attachments.length) || disabled || running || listening || startingVoice.current || sending.current || stagingCount.current) return;
    sending.current = true;
    setSubmitting(true);
    setError("");
    const value = text;
    setText("");
    try {
      await onSend(value);
    } catch (reason) {
      setText(value);
      setError(`ההודעה לא נשלחה: ${String(reason)}`);
    } finally {
      sending.current = false;
      setSubmitting(false);
    }
  };
  const key = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  };
  const stopListening = async () => {
    try {
      await coreApi("POST", "/v2/audio/voice/stop", {}, true);
      await invoke("desktop_hide_voice_overlay");
      setListening(false); setError(""); area.current?.focus();
    } catch (reason) { setError(`לא ניתן להפסיק הכתבה: ${String(reason)}`); }
  };
  const listen = async () => {
    if (running || disabled || startingVoice.current || sending.current || stagingCount.current) return;
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
        void invoke("desktop_hide_voice_overlay");
        if (state.error) {
          setError(state.error);
          return;
        }
        if (state.transcript && voiceConsumed.current !== state.session_id) {
          voiceConsumed.current = state.session_id;
          setText("");
          try {
            await onSend(state.transcript, true);
          } catch (reason) {
            setText(state.transcript);
            setError(`התמלול לא נשלח: ${String(reason)}`);
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
  const quotaStatus = quotaError ? "לא ניתן לטעון את המכסה כרגע"
    : !quota ? "טוען נתוני מכסה…"
    : !quota.available ? "נתוני המכסה אינם זמינים כרגע"
    : `${quota.plan_type ? `תוכנית ${quota.plan_type} · ` : ""}${quotaLoading ? "מתעדכן…" : "מעודכן כעת"}`;
  const quotaSummary = provider === "openai_codex_signin" ? (
    <section className="codex-quota-summary" aria-label="מכסת Codex שנותרה" title={quotaStatus}>
      {(["five_hour", "weekly"] as const).map(key => {
        const windowData = quota?.[key];
        const value = windowData?.remaining_percent;
        const remaining = typeof value === "number" && Number.isFinite(value)
          ? Math.max(0, Math.min(100, Math.round(value))) : null;
        const label = key === "five_hour" ? "5 שעות" : "שבוע";
        const reset = quotaResetLabel(windowData?.resets_at, key);
        const detail = remaining === null ? quotaStatus : reset ? `איפוס: ${reset}` : "זמן האיפוס אינו זמין";
        const tone = remaining === null ? "" : remaining < 20 ? "is-low" : remaining < 50 ? "is-medium" : "is-good";
        return (
          <div className={`quota-window ${tone}`} key={key} title={`${quotaStatus} · ${detail}`}
            aria-label={`${label}: ${remaining === null ? "המכסה אינה זמינה" : `${remaining}% נותרו`}. ${detail}`}>
            <p><b>{label}</b><em>{remaining === null ? "—" : `${remaining}%`}</em></p>
            <i aria-hidden="true"><span style={{ width: `${remaining ?? 0}%` }} /></i>
            <small>{remaining === null ? (quotaLoading ? "טוען…" : "לא זמין") : reset || "לא זמין"}</small>
          </div>
        );
      })}
    </section>
  ) : undefined;
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
                {item.previewUrl ? (
                  <img src={item.previewUrl} alt="" />
                ) : (
                  <i>IMG</i>
                )}
                <button
                  type="button"
                  aria-label={`הסרת ${item.name}`}
                  onClick={() =>
                    onAttachments((current) => current.filter((attachment) => attachment !== item))
                  }
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
                  onClick={() =>
                    onAttachments((current) => current.filter((attachment) => attachment !== item))
                  }
                >
                  <Icon name="close" size={18} />
                </button>
              </span>
            ),
          )}
        </div>
      )}
      {error && <p className="composer-error" role="alert" dir="rtl">{error}</p>}
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
          <button
            className={`composer-primary ${canSend ? "can-send" : ""} ${listening ? "is-listening" : ""}`}
            type="button"
            aria-label={
              running
                ? "עצירה"
                : listening
                  ? "הפסקת הכתבה"
                  : canSend
                    ? "שליחה"
                    : "הכתבה קולית"
            }
            aria-busy={voiceStarting || submitting || undefined}
            disabled={!running && (disabled || voiceStarting || submitting || staging > 0)}
            onClick={
              running
                ? onCancel
                : listening
                  ? () => void stopListening()
                  : canSend
                  ? () => void send()
                  : () => void listen()
            }
          >
            <Icon name={running || listening ? "stop" : canSend ? "send" : "mic"} size={24} />
          </button>
        </span>
        <div className="composer-controls">
          <div className="composer-selectors">
            <div className="composer-model-controls">
            <ComposerModelPicker theme={theme} provider={provider} model={model} favoriteModels={favoriteModels}
              reasoningEffort={reasoningEffort} reasoningOptions={reasoningOptions} quota={quotaSummary}
              onOpen={() => void refreshQuota(15)} onFavoriteModel={onFavoriteModel}
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
