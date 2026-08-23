import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import type { PendingAttachment, ReasoningOption } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import { autonomyLabels } from "./legacyUiParity";
import { coreApi } from "./coreApi";

interface ComposerProps {
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
  onAutonomyMode?: (mode: string) => void | Promise<void>;
  onLocalFastMode?: (enabled: boolean) => void | Promise<void>;
  onAttachments: (items: PendingAttachment[]) => void;
  onSend: (text: string) => Promise<void>;
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
const modelLabel = (value: string) =>
  value.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
const providerLabels: Record<string, string> = {
  gemini: "Google Gemini",
  openai: "OpenAI",
  openai_codex_signin: "OpenAI Codex Sign-in",
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
  groq: "Groq",
  nvidia: "NVIDIA",
  cerebras: "Cerebras",
  huggingface: "Hugging Face",
  deepseek: "DeepSeek",
  qwen: "Qwen",
  zhipu: "Zhipu AI",
  moonshot: "Moonshot AI",
  mistral: "Mistral",
  together: "Together AI",
  perplexity: "Perplexity",
  xai: "xAI",
  local: "מודל מקומי",
};
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
function resetText(timestamp?: number): string {
  if (!timestamp) return "";
  const remaining = Math.max(0, Math.floor(timestamp - Date.now() / 1000));
  if (remaining < 60) return "איפוס בקרוב";
  const minutes = Math.max(1, Math.floor(remaining / 60));
  if (minutes < 60) return `איפוס בעוד ${minutes} דק׳`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24)
    return `איפוס בעוד ${hours} שע׳${restMinutes ? ` ו-${restMinutes} דק׳` : ""}`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return `איפוס בעוד ${days} ימים${restHours ? ` ו-${restHours} שע׳` : ""}`;
}
export function Composer({
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
  onAutonomyMode = () => {},
  onLocalFastMode = () => {},
  onAttachments,
  onSend,
  onCancel,
}: ComposerProps) {
  type SpeechRecognitionLike = {
    lang: string;
    continuous: boolean;
    onresult: (event: {
      results: ArrayLike<{ 0: { transcript: string } }>;
    }) => void;
    onend: () => void;
    onerror: () => void;
    start: () => void;
    stop: () => void;
  };
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [status, setStatus] = useState("");
  const [quota, setQuota] = useState<CodexQuota | null>(null);
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [quotaError, setQuotaError] = useState("");
  const quotaFetchedAt = useRef(0);
  const area = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const modelMenu = useRef<HTMLDetailsElement>(null);
  const autonomyMenu = useRef<HTMLDetailsElement>(null);
  const activeRecognition = useRef<SpeechRecognitionLike | null>(null);
  useEffect(
    () => () => {
      activeRecognition.current?.stop();
      activeRecognition.current = null;
    },
    [],
  );
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
  const picked = async (files: FileList | null) => {
    if (!files?.length) return;
    try {
      onAttachments([
        ...attachments,
        ...(await Promise.all(Array.from(files).map(pastedFile))),
      ]);
      setStatus("");
    } catch (reason) {
      setStatus(String(reason));
    }
    if (picker.current) picker.current.value = "";
  };
  const paste = async (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files);
    if (!files.length) return;
    event.preventDefault();
    onAttachments([
      ...attachments,
      ...(await Promise.all(files.map(pastedFile))),
    ]);
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    const files = Array.from(event.dataTransfer.files);
    if (files.length)
      void Promise.all(files.map(pastedFile)).then((items) =>
        onAttachments([...attachments, ...items]),
      );
  };
  const send = async () => {
    if ((!text.trim() && !attachments.length) || disabled) return;
    const value = text;
    setText("");
    try {
      await onSend(value);
    } catch {
      setText(value);
    }
  };
  const key = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  };
  const stopListening = (cancelled = true) => {
    activeRecognition.current?.stop();
    activeRecognition.current = null;
    setListening(false);
    setStatus(cancelled ? "ההאזנה בוטלה" : "");
    area.current?.focus();
  };
  const listen = () => {
    if (activeRecognition.current) {
      stopListening();
      return;
    }
    const Recognition = (
      window as unknown as {
        webkitSpeechRecognition?: new () => SpeechRecognitionLike;
      }
    ).webkitSpeechRecognition;
    if (!Recognition) {
      setStatus("זיהוי קולי אינו זמין ב־WebView זה");
      return;
    }
    const recognizer = new Recognition();
    activeRecognition.current = recognizer;
    recognizer.lang = "he-IL";
    recognizer.continuous = false;
    recognizer.onresult = (event) =>
      setText(
        (current) =>
          `${current}${current ? " " : ""}${event.results[0][0].transcript}`,
      );
    recognizer.onend = () => {
      activeRecognition.current = null;
      setListening(false);
      setStatus("");
    };
    recognizer.onerror = () => {
      activeRecognition.current = null;
      setListening(false);
      setStatus("לא ניתן היה לזהות דיבור");
    };
    setListening(true);
    setStatus("אפשר לדבר עכשיו");
    recognizer.start();
  };
  useEffect(() => {
    const activate = () => listen();
    window.addEventListener("smarti:voice-hotkey", activate);
    return () => window.removeEventListener("smarti:voice-hotkey", activate);
  }, []);
  const icons = legacyAssets(theme);
  const canSend = Boolean(text.trim() || attachments.length);
  const menuKey = (
    event: KeyboardEvent<HTMLElement>,
    menu: HTMLDetailsElement | null,
  ) => {
    if (event.key === "Escape") {
      event.preventDefault();
      menu?.removeAttribute("open");
      (menu?.querySelector("summary") as HTMLElement | null)?.focus();
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const activeProvider = document.activeElement?.closest(
        ".model-provider-submenu",
      );
      const target = activeProvider?.querySelector<HTMLElement>(
        '[role="menuitemradio"]',
      );
      if (target) {
        event.preventDefault();
        target.focus();
      }
    }
  };
  return (
    <div
      className={`composer ${running ? "is-running" : ""}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={drop}
    >
      {listening && (
        <section
          className="voice-listening-overlay"
          role="status"
          aria-live="polite"
        >
          <button
            type="button"
            aria-label="בטל האזנה"
            title="בטל האזנה"
            onClick={() => stopListening()}
          >
            <LegacyIcon src={icons.close} size={18} />
          </button>
          <button
            type="button"
            aria-label="פתח את סמארטי"
            title="פתח את סמארטי"
            onClick={() => area.current?.focus()}
          >
            <LegacyIcon src={icons.voiceOverlayOpen} size={18} />
          </button>
          <div>
            <strong>האזנה פעילה</strong>
            <span>{status || "אפשר לדבר עכשיו"}</span>
          </div>
          <img src={icons.voiceListening} alt="" />
        </section>
      )}
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
                    onAttachments(
                      attachments.filter((_, position) => position !== index),
                    )
                  }
                >
                  ×
                </button>
              </span>
            ) : (
              <span className="pending-file" key={`${item.path}-${index}`}>
                <i>
                  <LegacyIcon src={icons.file} size={28} />
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
                    onAttachments(
                      attachments.filter((_, position) => position !== index),
                    )
                  }
                >
                  ×
                </button>
              </span>
            ),
          )}
        </div>
      )}
      <textarea
        ref={area}
        rows={1}
        value={text}
        disabled={disabled || running}
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
                : canSend
                  ? "שליחה"
                  : listening
                    ? "הפסקת הכתבה"
                    : "הכתבה קולית"
            }
            disabled={disabled && !running}
            onClick={running ? onCancel : canSend ? () => void send() : listen}
          >
            <LegacyIcon
              src={running ? icons.stop : canSend ? icons.send : icons.mic}
              size={28}
            />
          </button>
        </span>
        {!!favoriteModels.length && (
          <details
            ref={modelMenu}
            className="quick-pill model-quick-pill"
            onToggle={(event) => {
              if (event.currentTarget.open) void refreshQuota(15);
            }}
            onKeyDown={(event) => menuKey(event, modelMenu.current)}
          >
            <summary title="מודלים מועדפים">
              <span>{modelLabel(model || provider || "מודל")}</span>
              <LegacyIcon src={icons.dropdown} size={13} />
            </summary>
            <div
              className="quick-pill-menu model-quick-menu"
              role="menu"
              aria-label="מודלים מועדפים"
              dir="rtl"
            >
              {!!reasoningOptions.length && (
                <>
                  <p className="model-menu-header">עוצמת חשיבה</p>
                  {reasoningOptions.map((item) => (
                    <button
                      type="button"
                      role="menuitemradio"
                      aria-checked={item.value === reasoningEffort}
                      className={
                        item.value === reasoningEffort ? "is-selected" : ""
                      }
                      key={item.value}
                      onClick={() => {
                        modelMenu.current?.removeAttribute("open");
                        void onReasoningEffort(item.value);
                      }}
                    >
                      <span>{item.label}</span>
                    </button>
                  ))}
                  <hr />
                </>
              )}
              {provider === "openai_codex_signin" && (
                <>
                  <section
                    className="codex-quota-card"
                    aria-label="מכסת Codex שנותרה"
                  >
                    <strong>מכסת Codex שנותרה</strong>
                    <span title={quotaError}>
                      {quotaError
                        ? "לא ניתן לטעון את המכסה כרגע"
                        : !quota
                          ? "טוען נתוני מכסה…"
                          : quotaLoading
                            ? `תוכנית ${quota.plan_type || ""} · מתעדכן…`
                            : `תוכנית ${quota.plan_type || ""}${quota.plan_type ? " · " : ""}מעודכן כעת`}
                    </span>
                    {(["five_hour", "weekly"] as const).map((key) => {
                      const windowData = quota?.[key];
                      if (!windowData) return null;
                      const remaining = Math.max(
                        0,
                        Math.min(
                          100,
                          Math.round(windowData.remaining_percent || 0),
                        ),
                      );
                      return (
                        <div className="quota-window" key={key}>
                          <p>
                            <b>{key === "five_hour" ? "5 שעות" : "שבוע"}</b>
                            <em
                              className={
                                remaining < 20
                                  ? "is-low"
                                  : remaining < 50
                                    ? "is-medium"
                                    : "is-good"
                              }
                            >
                              {remaining}% נותרו
                            </em>
                          </p>
                          <i>
                            <span
                              className={
                                remaining < 20
                                  ? "is-low"
                                  : remaining < 50
                                    ? "is-medium"
                                    : "is-good"
                              }
                              style={{ width: `${remaining}%` }}
                            />
                          </i>
                          <small>{resetText(windowData.resets_at)}</small>
                        </div>
                      );
                    })}
                  </section>
                  <hr />
                </>
              )}
              {Array.from(
                new Set(favoriteModels.map((item) => item.provider)),
              ).map((favoriteProvider) => (
                <div className="model-provider-submenu" key={favoriteProvider}>
                  <button type="button" aria-haspopup="menu">
                    <span>
                      {providerLabels[favoriteProvider] || favoriteProvider}
                    </span>
                    <LegacyIcon src={icons.dropdown} size={13} />
                  </button>
                  <div
                    role="menu"
                    aria-label={
                      providerLabels[favoriteProvider] || favoriteProvider
                    }
                  >
                    {favoriteModels
                      .filter((item) => item.provider === favoriteProvider)
                      .map((item) => (
                        <button
                          type="button"
                          role="menuitemradio"
                          aria-checked={
                            item.provider === provider && item.model === model
                          }
                          className={
                            item.provider === provider && item.model === model
                              ? "is-selected"
                              : ""
                          }
                          key={`${item.provider}:${item.model}`}
                          onClick={() => {
                            modelMenu.current?.removeAttribute("open");
                            void onFavoriteModel(item);
                          }}
                        >
                          <span>{modelLabel(item.model)}</span>
                        </button>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          </details>
        )}
        <details ref={autonomyMenu} className="quick-pill autonomy-quick-pill">
          <summary title="פרופיל בטיחות">
            <LegacyIcon
              src={
                autonomyMode === "locked_down"
                  ? icons.autonomySafe
                  : autonomyMode === "max_autonomy"
                    ? icons.autonomyFull
                    : icons.autonomy
              }
              size={18}
            />
            <span>
              {autonomyLabels[autonomyMode] || autonomyLabels.balanced}
            </span>
            <LegacyIcon src={icons.dropdown} size={13} />
          </summary>
          <div className="quick-pill-menu autonomy-menu" dir="rtl">
            <button
              type="button"
              className={autonomyMode === "locked_down" ? "is-selected" : ""}
              onClick={() => {
                autonomyMenu.current?.removeAttribute("open");
                void onAutonomyMode("locked_down");
              }}
            >
              <LegacyIcon src={icons.autonomySafe} size={18} />
              בטוח
            </button>
            <button
              type="button"
              className={autonomyMode === "balanced" ? "is-selected" : ""}
              onClick={() => {
                autonomyMenu.current?.removeAttribute("open");
                void onAutonomyMode("balanced");
              }}
            >
              <LegacyIcon src={icons.autonomy} size={18} />
              מאוזן
            </button>
            <button
              type="button"
              className={autonomyMode === "max_autonomy" ? "is-selected" : ""}
              onClick={() => {
                autonomyMenu.current?.removeAttribute("open");
                void onAutonomyMode("max_autonomy");
              }}
            >
              <LegacyIcon src={icons.autonomyFull} size={18} />
              אוטונומי
            </button>
          </div>
        </details>
        {provider.toLowerCase() === "local" && (
          <label
            className={`local-fast-mode ${localFastMode ? "is-enabled" : ""}`}
            title="מצב הקשר חסכוני למודלים מקומיים קטנים או לחומרה חלשה"
          >
            <span>FastMode</span>
            <input
              type="checkbox"
              checked={localFastMode}
              onChange={(event) => void onLocalFastMode(event.target.checked)}
            />
            <i />
          </label>
        )}
        <span className="composer-spacer" />
        {status && (
          <span className="voice-status" role="status" dir="rtl">
            {status}
          </span>
        )}
        <button
          className="composer-tool"
          type="button"
          aria-label="צירוף קובץ"
          onClick={() => picker.current?.click()}
        >
          <LegacyIcon src={icons.plus} size={24} />
        </button>
      </div>
    </div>
  );
}
