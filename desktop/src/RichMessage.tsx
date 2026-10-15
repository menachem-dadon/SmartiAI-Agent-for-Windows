import { memo, useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps, ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage, RunEvent } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { DesignSystemProvider, Icon, IconButton, MessageFrame, UserBubble, toolIcons } from "./design-system";
import "./chat.css";
import { MessageTable } from "./MessageTable";
import { useSpeechPlayback } from "./speechPlayback";
import { AttachmentLightbox } from "./AttachmentLightbox";
import { preserveDisclosure } from "./chatScroll";
import type { StreamState } from "./chatStreaming";
import { revealRange, streamReveal, type RevealRange } from "./streamReveal";
import type { AgentToolIconName } from "./agentToolIcons";
import { eventFromRun, mergeProcessEvents, processRows, processCaption, INTERFACE_LANGUAGE, type AgentEvent, type AgentProcessMetadata, type ProcessLanguage, type ToolView } from "./agentProcess";
export { processRows } from "./agentProcess";

function contentIdentity(text: string) { let hash = 0; for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) | 0; return String(hash); }

const copy = async (text: string) => navigator.clipboard.writeText(text);

function MessageCopyButton({ text, onError }: { text: string; onError: (reason: unknown) => void }) {
  const [copyCount, setCopyCount] = useState(0);
  useEffect(() => {
    if (!copyCount) return;
    const timer = setTimeout(() => setCopyCount(0), 2500);
    return () => clearTimeout(timer);
  }, [copyCount]);
  return <IconButton
    tooltip={false}
    icon={copyCount ? "check" : "copy"}
    label={copyCount ? "הועתק" : "העתק"}
    variant="ghost"
    onClick={() => void copy(text).then(() => setCopyCount(count => count + 1)).catch(reason => {
      setCopyCount(0);
      onError(reason);
    })}
  />;
}

const WINDOWS_PATH = /^[A-Za-z]:[\\/]/;
function localHref(value: string): string {
  const normalized = WINDOWS_PATH.test(value)
    ? `file:///${value.replace(/\\/g, "/")}`
    : value;
  const encoded = encodeURI(normalized);
  // URLs already contain escaped UTF-8. A literal percent in a Windows
  // filename, however, must remain escaped rather than becoming URL syntax.
  return (WINDOWS_PATH.test(value) ? encoded : encoded.replace(/%25([\da-f]{2})/gi, "%$1")).replace(/#/g, "%23");
}
export function prepareMessageMarkdown(value: string): string {
  return value
    .replace(
      /\[([^\]]*)\]\(((?:file:\/{2,}|[A-Za-z]:[\\/])[^)\r\n]+)\)/gi,
      (_match, label: string, href: string) =>
        `[${label}](${localHref(href.trim())})`,
    )
    .replace(
      /`((?:file:\/+|[A-Za-z]:[\\/])[^`\r\n]+)`/gi,
      (_match, href: string) => {
        const clean = href.trim();
        const label =
          clean
            .replace(/[\\/]+$/, "")
            .split(/[\\/]/)
            .pop() || clean;
        return `[${label}](${localHref(clean)})`;
      },
    );
}
export function safeChatHref(value: string): string {
  const href = String(value || "").trim();
  return /^(?:https?:|mailto:|file:)/i.test(href) ? href : "";
}
function localPathFromHref(href: string): string {
  const url = new URL(href);
  let pathname: string;
  try { pathname = decodeURIComponent(url.pathname).replace(/\//g, "\\"); }
  catch { throw new Error("הקישור לקובץ מכיל קידוד לא תקין."); }
  if (url.hostname) return `\\\\${url.hostname}${pathname}`;
  return /^\\[A-Za-z]:/.test(pathname) ? pathname.slice(1) : pathname;
}
function codeText(children: unknown): string {
  return String(
    (children as { props?: { children?: unknown } })?.props?.children || "",
  ).replace(/\n$/, "");
}
function codeLanguage(children: unknown): string {
  return (
    String(
      (children as { props?: { className?: string } })?.props?.className || "",
    ).replace(/^language-/, "") || "text"
  );
}
export function codeDisplayLanguage(value: string): string {
  const language = String(value || "text").trim().toLowerCase() || "text";
  const display: Record<string, string> = {
    text: "Text",
    txt: "Text",
    python: "Python",
    py: "Python",
    javascript: "JavaScript",
    js: "JavaScript",
    typescript: "TypeScript",
    ts: "TypeScript",
    tsx: "TSX",
    jsx: "JSX",
    csharp: "C#",
    cs: "C#",
    cpp: "C++",
    "c++": "C++",
    json: "JSON",
    html: "HTML",
    css: "CSS",
    scss: "SCSS",
    sql: "SQL",
    xml: "XML",
    yaml: "YAML",
    yml: "YAML",
    jsonc: "JSONC",
    md: "Markdown",
    markdown: "Markdown",
    powershell: "PowerShell",
    pwsh: "PowerShell",
    ps1: "PowerShell",
    bash: "Bash",
    sh: "Shell",
    shell: "Shell",
    zsh: "Zsh",
    kotlin: "Kotlin",
    kt: "Kotlin",
    rust: "Rust",
    rs: "Rust",
    php: "PHP",
    ruby: "Ruby",
    rb: "Ruby",
  };
  return (
    display[language] ||
    language
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
}
async function downloadCode(text: string, language: string) {
  const extensions: Record<string, string> = {
    javascript: "js",
    typescript: "ts",
    python: "py",
    powershell: "ps1",
    bash: "sh",
    json: "json",
    html: "html",
    css: "css",
    sql: "sql",
  };
  await invoke("save_text_file", {
    suggestedName: `smarti_code.${extensions[language.toLowerCase()] || "txt"}`,
    contents: text,
  });
}
function SentImage({
  path,
  name,
  mimeType,
}: {
  path: string;
  name: string;
  mimeType?: string;
}) {
  const [source, setSource] = useState("");
  useEffect(() => {
    let alive = true;
    let objectUrl = "";
    void invoke<number[]>("read_attachment_preview", { path })
      .then((bytes) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(
          new Blob([new Uint8Array(bytes)], { type: mimeType || "image/png" }),
        );
        setSource(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [mimeType, path]);
  const [enlarged, setEnlarged] = useState(false);
  const [failed, setFailed] = useState(false);
  return <><button type="button" className="sent-image-button" disabled={!source || failed} aria-label={`הגדל תמונה: ${name}`} onClick={() => setEnlarged(true)}>
    {source && !failed ? <img src={source} alt={name} onError={() => setFailed(true)} /> : <span>{failed ? "לא ניתן להציג תמונה" : "טוען תמונה…"}</span>}
  </button>{enlarged && <AttachmentLightbox source={source} name={name} onClose={() => setEnlarged(false)} />}</>;
}

function StreamLetter({ node, ...props }: ComponentProps<"span"> & ExtraProps) {
  const started = Number(node?.properties?.["data-reveal-started"]);
  // Set the elapsed offset once per glyph. Updating it again on every token
  // would add elapsed time to an animation that is already progressing.
  const delay = useMemo(() => Number.isFinite(started) ? `-${Math.max(0, Date.now() - started)}ms` : undefined, [started]);
  return <span key={`${node?.properties?.["data-reveal-offset"]}:${started}`} {...props} style={{ ...props.style, animationDelay: delay }}/>;
}
const reportComponents: Components = { span: StreamLetter };
function StreamingReport({ text, active }: { text: string; active: boolean }) {
  // A remounted snapshot is already visible content, not a newly arrived chunk.
  const revealed = useRef<{ text: string; ranges: RevealRange[] }>({ text, ranges: [] });
  if (active && text !== revealed.current.text) {
    const previous = revealed.current.text;
    revealed.current = { text, ranges: text.startsWith(previous)
      ? [...revealed.current.ranges, revealRange(previous.length, text.length, revealed.current.ranges.slice(-1)[0])].slice(-48)
      : [revealRange(0, text.length)] };
  }
  return <ReactMarkdown components={reportComponents} rehypePlugins={active ? [[streamReveal, { ranges: revealed.current.ranges }]] : []}>{text}</ReactMarkdown>;
}

function AgentStatusText({ active, children }: { active: boolean; children: ReactNode }) {
  return <span className={`agent-status-text${active ? " is-shimmering" : ""}`}>{children}</span>;
}

function ToolStatusIndicator({ status }: { status?: ToolView["status"] }) {
  if (status === "preparing") return <i className="tool-state-indicator"><span className="tool-preparation-ring" aria-hidden="true" /></i>;
  if (status === "error" || status === "finished") return <i className={`tool-state-indicator${status === "error" ? " is-error" : ""}`}><Icon name={status === "error" ? "close" : "check"} size={16} /></i>;
  return null;
}

const toolTypeIcon = (icon: AgentToolIconName) => icon === "row_status" ? "tools" as const : toolIcons[icon] || "tools" as const;

function WaitingIndicator({ label, shimmer, immediate }: { label: string; shimmer: boolean; immediate: boolean }) {
  const [visible, setVisible] = useState(immediate);
  useEffect(() => { if (immediate) { setVisible(true); return; } const timer = setTimeout(() => setVisible(true), 300); return () => clearTimeout(timer); }, [immediate]);
  return visible ? <p className="agent-initial-thinking"><AgentStatusText active={shimmer}>{label}</AgentStatusText></p> : null;
}

export function formatAgentDuration(seconds: number, language: ProcessLanguage = INTERFACE_LANGUAGE): string {
  const safe = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  if (language === "en") return hours ? `${hours} h ${String(minutes).padStart(2, "0")} min ${String(secs).padStart(2, "0")} s`
    : minutes ? `${minutes} min ${String(secs).padStart(2, "0")} s` : `${secs} s`;
  if (hours)
    return `${hours} ${hours === 1 ? "שעה" : "שעות"} ${String(minutes).padStart(2, "0")} דק׳ ${String(secs).padStart(2, "0")} שנ׳`;
  if (minutes) return `${minutes} דק׳ ${String(secs).padStart(2, "0")} שנ׳`;
  return `${secs} שנ׳`;
}

function CodeFrame({ children, onCopy, onDownload }: { children: React.ReactNode; onCopy: (text: string) => Promise<void>; onDownload: (text: string, language: string) => Promise<void> }) {
  const [wrapped, setWrapped] = useState(false);
  const text = codeText(children); const language = codeLanguage(children);
  const [error, setError] = useState("");
  const execute = async (action: () => Promise<void>) => { setError(""); try { await action(); } catch (reason) { setError(`הפעולה לא הושלמה: ${String(reason)}`); } };
  return <div className={`code-frame ${wrapped ? "is-wrapped" : ""}`} dir="ltr"><div className="code-frame-head">
    <IconButton tooltip={false} icon="copy" label="העתק קוד" onClick={() => void execute(() => onCopy(text))} />
    <IconButton tooltip={false} icon="download" label="הורד קובץ" onClick={() => void execute(() => onDownload(text, language))} />
    <IconButton icon="wrap" label="גלישת שורות קוד" aria-pressed={wrapped} onClick={() => setWrapped(value => !value)} />
    <span>{codeDisplayLanguage(language)}</span></div><pre>{children}</pre>{error && <p className="message-link-error" role="alert">{error}</p>}</div>;
}

export const RichMessage = memo(function RichMessage({
  message,
  events = [],
  theme = "dark",
  active = false,
  runStatus,
  providerMode,
  onOpenCanvas,
  isNew = false,
  viewportHeight = 0,
  stream,
}: {
  message: ChatMessage;
  events?: RunEvent[];
  theme?: ResolvedTheme;
  active?: boolean;
  runStatus?: string;
  providerMode?: string;
  onOpenCanvas?: (canvasId: string) => void;
  isNew?: boolean;
  viewportHeight?: number;
  stream?: StreamState;
}) {
  const messageId = `${message.role}:${message.metadata?.run_id || message.message_id || `${message.created_at || ""}:${contentIdentity(message.content)}`}`;
  const preferencesKey = `smarti.chat.disclosures:${messageId}`;
  const storedPreferences = () => { try { return JSON.parse(sessionStorage.getItem(preferencesKey) || "{}"); } catch { return {}; } };
  const [preferences, setPreferences] = useState<Record<string, boolean>>(storedPreferences);
  const processManual = useRef(typeof preferences.process === "boolean");
  const [processOpen, setProcessOpen] = useState(preferences.process ?? active);
  const remember = (key: string, value: boolean) => setPreferences(current => {
    const next = { ...current, [key]: value }; try { sessionStorage.setItem(preferencesKey, JSON.stringify(next)); } catch { /* UI preference is optional. */ } return next;
  });
  const speechOwner = useId();
  const speech = useSpeechPlayback(message.metadata?.run_id
    ? `run:${message.metadata.run_id}` : `message:${speechOwner}`);
  const { speaking } = speech;
  const [userExpanded, setUserExpanded] = useState(preferences.user ?? false);
  const [userContentHeight, setUserContentHeight] = useState(0);
  const contentId = useId();
  const [, setElapsedTick] = useState(0);
  const [collapsible, setCollapsible] = useState(false);
  const [linkError, setLinkError] = useState("");
  const contentRef = useRef<HTMLDivElement>(null);
  const markdown = prepareMessageMarkdown(message.content);
  const revealed = useRef<{ text: string; ranges: RevealRange[] }>({ text: markdown, ranges: [] });
  if (active && markdown !== revealed.current.text) {
    const previous = revealed.current.text;
    revealed.current = { text: markdown, ranges: markdown.startsWith(previous)
      ? [...revealed.current.ranges, revealRange(previous.length, markdown.length, revealed.current.ranges.slice(-1)[0])].slice(-48)
      : [revealRange(0, markdown.length)] };
  }
  // Keep each table mounted while streamed content and elapsed time update.
  const renderTable = useMemo(() =>
    (props: ComponentProps<typeof MessageTable>) => <MessageTable {...props} theme={theme} />,
  [theme]);
  useEffect(() => {
    if (!processManual.current) setProcessOpen(active);
    if (!active) return;
    const timer = window.setInterval(
      () => setElapsedTick((value) => value + 1),
      1000,
    );
    return () => clearInterval(timer);
  }, [active]);
  const storedProcess =
    message.role === "assistant" &&
    message.metadata?.agent_process &&
    typeof message.metadata.agent_process === "object"
      ? (message.metadata.agent_process as AgentProcessMetadata)
      : null;
  const agentEvents = useMemo(() => {
    if (message.role !== "assistant") return [];
    // Initial run loading and replay polling can deliver the same event.
    // Count each tool call once so a duplicate start cannot keep it running.
    const live = [...new Map(events.map((event) => [event.event_id, event])).values()]
      .sort((left, right) => left.event_id - right.event_id)
      .map(eventFromRun)
      .filter((item): item is AgentEvent => Boolean(item));
    if (!storedProcess?.events?.length) return live;
    if (!active) return storedProcess.events;
    const identity = ({ liveEventId: _live, ...event }: AgentEvent) => event.id || JSON.stringify(event);
    const saved = new Set(storedProcess.events.map(identity));
    return [...storedProcess.events, ...live.filter(event => !saved.has(identity(event)))];
  }, [events, message.role, storedProcess, active]);
  const processText = (he: string, en: string) => processCaption(INTERFACE_LANGUAGE, he, en);
  const rows = useMemo(() => {
    // A user's message shares the run ID but never owns its activity. Saved
    // execution is authoritative; stream preparation includes unexecuted calls
    // from rejected attempts or batches that Core deliberately did not admit.
    if (message.role !== "assistant") return [];
    const result = processRows(mergeProcessEvents(agentEvents, stream, active));
    if (runStatus === "waiting_for_approval" && !agentEvents.some(event => event.type === "tool_waiting")) for (const row of result) if (row.kind === "tools") { for (const tool of row.tools) if (tool.status === "running") tool.status = "waiting"; const waiting = row.tools.find(tool => tool.status === "waiting"); if (waiting) row.label = processText(`ממתין לאישור הפעלת כלי ${waiting.name}`, `Waiting for tool approval ${waiting.name}`); }
    if (!active) for (const row of result) if (row.kind === "tools" && row.tools.some(tool => ["preparing", "running", "waiting"].includes(tool.status))) {
      for (const tool of row.tools) if (["preparing", "running", "waiting"].includes(tool.status)) tool.status = "error";
      row.running = false; row.label = runStatus === "cancelled" ? processText("הפעלת כלי נעצרה", "Tool execution stopped") : processText("הפעלת כלי לא הושלמה", "Tool execution did not finish");
    }
    return result;
  }, [agentEvents, stream, runStatus, active, message.role, storedProcess]);
  const activeRows = rows.filter(row => row.kind === "tools" && row.running);
  const ownerRow = activeRows.find(row => row.kind === "tools" && preferences[row.key]) || activeRows[0];
  const ownerTool = ownerRow?.kind === "tools" && preferences[ownerRow.key] ? ownerRow.tools.find(tool => ["running", "preparing", "waiting"].includes(tool.status))?.key : undefined;
  const canThink = active && message.role === "assistant" && !message.content &&
    stream?.stage !== "retry" &&
    (providerMode !== "local" || stream?.stage === "prefill" || stream?.stage === "thinking") &&
    (!runStatus || runStatus === "queued" || runStatus === "running") &&
    !rows.some((row) => row.kind === "tools" && row.running);
  const firstLiveAt = events
    .map((event) => Date.parse(event.created_at))
    .filter(Number.isFinite)
    .sort((a, b) => a - b)[0];
  const elapsed =
    storedProcess?.elapsed_seconds ??
    (active && firstLiveAt
      ? Math.max(0, Math.floor((Date.now() - firstLiveAt) / 1000))
      : 0);
  const retryLabel = active && stream?.stage === "retry" ? stream.status_text : undefined;
  // Announce semantic transitions, never report tokens, elapsed ticks or the
  // retry countdown. Native summary semantics continue to own disclosure.
  const toolRows = rows.filter(row => row.kind === "tools");
  const announcement = message.role !== "assistant" ? "" : retryLabel
    ? "בקשת המודל לא הושלמה. ממתין לניסיון נוסף."
    : (ownerRow?.kind === "tools" ? ownerRow.label : toolRows[toolRows.length - 1]?.label) || "";
  useLayoutEffect(() => {
    const node = contentRef.current;
    if (!node || message.role !== "user") {
      setCollapsible(false);
      return;
    }
    const measure = () => {
      // Measure the unclipped content so both directions have a real height
      // target, including after wrapping, fonts or embedded content change.
      const height = node.scrollHeight;
      setUserContentHeight(height);
      const available = viewportHeight || node.closest<HTMLElement>(".chat-stage")?.clientHeight || window.innerHeight;
      setCollapsible(height + 28 > available * .8);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [message.content, message.role, viewportHeight]);
  const isError =
    Boolean(message.metadata?.error || message.metadata?.is_error) ||
    /^שגיאה\s*:/u.test(message.content);
  const backgroundTask =
    message.role === "user" &&
    Boolean(
      message.metadata?.triggered_by_background ||
      message.metadata?.is_background_task,
    );
  const memoryUpdated =
    message.role === "assistant" && Boolean(message.metadata?.memory_updated);
  const canvases =
    message.role === "assistant" && Array.isArray(message.metadata?.canvases)
      ? (message.metadata.canvases as Array<Record<string, unknown>>).filter(
          (item) => !item.closed,
        )
      : [];
  const actionsAvailable =
    !active && Boolean(message.content.trim()) &&
    (message.role !== "assistant" || (!isError && (!(runStatus || message.metadata?.run_status) || (runStatus || message.metadata?.run_status) === "completed")));
  const openLink = useCallback(async (href: string) => {
    setLinkError("");
    try {
      const local = href.toLowerCase().startsWith("file:");
      await invoke("open_chat_link", {
        target: local ? localPathFromHref(href) : href,
        local,
      });
    } catch (reason) {
      setLinkError(`לא ניתן לפתוח את הקישור: ${String(reason)}`);
    }
  }, []);
  // Stable renderers keep the focused link and reading blocks mounted when
  // an asynchronous opening error (or an elapsed-time tick) updates this row.
  const markdownComponents = useMemo<Components>(() => ({
    table: renderTable,
    span: StreamLetter,
    p: ({ node, ...props }) => <p {...props} data-reading-block={node?.position?.start.offset}/>,
    li: ({ node, ...props }) => <li {...props} data-reading-block={node?.position?.start.offset}/>,
    h1: ({ node, ...props }) => <h1 {...props} data-reading-block={node?.position?.start.offset}/>,
    h2: ({ node, ...props }) => <h2 {...props} data-reading-block={node?.position?.start.offset}/>,
    h3: ({ node, ...props }) => <h3 {...props} data-reading-block={node?.position?.start.offset}/>,
    a: ({ href = "", node: _node, ...props }) => <a {...props} href={href} onClick={event => {
      event.preventDefault();
      if (href) void openLink(href);
    }}/>,
    code: ({ children, className, ...props }) => <code {...props} className={className} dir="ltr">{children}</code>,
    pre: ({ children }) => <CodeFrame onCopy={copy} onDownload={downloadCode}>{children}</CodeFrame>,
  }), [renderTable, openLink]);
  const attachmentStrip = !!message.attachments?.length && <div className="sent-attachments" dir="rtl">
    {message.attachments.map((item, index) => item.kind === "image" && item.path
      ? <span className="sent-image" key={`${item.name}-${index}`}><SentImage path={item.path} name={item.name} mimeType={item.mime_type} /></span>
      : <button type="button" className="attachment-tile" key={`${item.name}-${index}`} onClick={() => item.path && void invoke("open_chat_link", { target: item.path, local: true }).catch(reason => setLinkError(String(reason)))}><i><Icon name="file" size={24}/></i><b>{item.name}</b><small>{item.size ? `${Math.max(1, Math.round(item.size / 1024))} KB` : "File"}</small></button>)}
  </div>;
  const content = (<div
        className={`chat-message chat-message--${message.role} ${isError ? "is-error" : ""} ${backgroundTask ? "is-background-task" : ""}`}
      >
        {backgroundTask && (
          <strong className="background-task-badge">⚡ משימת רקע</strong>
        )}
        {!!message.content && (
          <div
            id={contentId}
            className={`message-content ${collapsible ? "is-collapsible" : ""} ${collapsible && !userExpanded ? "is-collapsed" : ""}`}
            style={collapsible ? { maxHeight: userExpanded ? userContentHeight : `max(1px, calc(${viewportHeight * .7 - 28}px - var(--sds-size-target) - 8px))` } : undefined}
          >
            <div ref={contentRef} className="message-content-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={active ? [[streamReveal, { ranges: revealed.current.ranges }]] : []}
                urlTransform={safeChatHref}
                components={markdownComponents}
              >
                {markdown}
              </ReactMarkdown>
            </div>
          </div>
        )}
        {speech.error && <p className="message-link-error" role="alert">{speech.error}</p>}
        {linkError && (
          <p className="message-link-error" role="alert">
            {linkError}
          </p>
        )}

      </div>);
  return (
    <DesignSystemProvider theme={theme} className="message-design"><article
      className={`chat-message-row chat-message-row--${message.role} ${backgroundTask ? "is-background-task" : ""}`}
      data-run-id={String(message.metadata?.run_id || "") || undefined}
      data-message-id={messageId}
      data-message-ordinal={message.message_id?.split(":").slice(-1)[0]}
      dir="auto"
    >
      <MessageFrame outputs={!!canvases.length && (
          <div className="message-canvases">
            {canvases.map((canvas, index) => (
              <article
                className="canvas-open-card"
                key={String(canvas.id || index)}
                dir="ltr"
              >
                <button
                  type="button"
                  onClick={() => onOpenCanvas?.(String(canvas.id || ""))}
                >
                  פתיחה
                </button>
                <div dir="rtl">
                  <strong>{String(canvas.title || "קנבס של סמארטי")}</strong>
                  <small>
                    {canvas.created_at
                      ? new Date(String(canvas.created_at)).toLocaleString(
                          "he-IL",
                          {
                            day: "numeric",
                            month: "long",
                            hour: "2-digit",
                            minute: "2-digit",
                          },
                        )
                      : "תאריך לא זמין"}
                  </small>
                </div>
                <Icon name="canvas" size={24} />
              </article>
            ))}
          </div>
        )} actions={actionsAvailable && (
        <div className="message-actions">
          <MessageCopyButton text={message.content} onError={reason => setLinkError(`ההעתקה נכשלה: ${String(reason)}`)} />
          {message.role === "assistant" && (
            <IconButton
              tooltip={false}
              icon={speaking ? "stop" : "speaker"} variant="ghost"
              label={speaking ? "עצור הקראה" : "הקרא בקול"}
              onClick={() => void speech.toggle(message.content)}
              disabled={speech.pending}
            />
          )}
          {memoryUpdated && (
            <span className="memory-updated">
              <Icon name="memory" />
              הזיכרון עודכן
            </span>
          )}
        </div>
      )}>
      {!!rows.length && (
        <details
          className="agent-process"
          dir="rtl"
          open={processOpen}
        >
          <summary onClick={event => { event.preventDefault(); processManual.current = true; preserveDisclosure(event.currentTarget, () => { setProcessOpen(!processOpen); remember("process", !processOpen); }); }}>
            <Icon name="chevron" size={16} className="process-chevron" />
            <AgentStatusText active={active && !processOpen}>
              {active ? processText("סמארטי עובד", "Smarti is working") : processText("סמארטי עבד", "Smarti worked")}{" "}
              {formatAgentDuration(elapsed)}
            </AgentStatusText>
            <Icon name="activity" size={20} />
          </summary>
          <div className="agent-process-details">
            {rows.map((row) =>
              row.kind === "report" ? (
                <div className="agent-report" key={row.key}>
                  <StreamingReport text={row.text} active={active}/>
                </div>
              ) : row.standalone ? (
                <p
                  className="agent-standalone"
                  key={row.key}
                >
                  <Icon name={toolIcons[row.icon] || "tools"} />
                  <AgentStatusText active={active && processOpen && ownerRow?.key === row.key}>{row.label}</AgentStatusText>
                </p>
              ) : (
                <details className="agent-tool-group" key={row.key} open={!!preferences[row.key]}>
                  <summary onClick={event => { event.preventDefault(); preserveDisclosure(event.currentTarget, () => remember(row.key, !preferences[row.key])); }}>
                    <Icon name="chevron" size={16} className="process-chevron" />
                    <ToolStatusIndicator status={row.tools.some(tool => tool.status === "preparing") ? "preparing" : row.tools.some(tool => tool.status === "error") ? "error" : undefined} />
                    <AgentStatusText active={active && processOpen && ownerRow?.key === row.key && !preferences[row.key]}>
                      {row.label}
                    </AgentStatusText>
                    <Icon name={row.tools.length === 1 ? toolTypeIcon(row.tools[0].icon) : "tools"} />
                  </summary>
                  <div>
                    {row.tools.map((tool) => (
                      <details className="agent-tool-row" key={tool.key} open={!!preferences[tool.key]}>
                        <summary onClick={event => { event.preventDefault(); preserveDisclosure(event.currentTarget, () => remember(tool.key, !preferences[tool.key])); }}>
                          <Icon name="chevron" size={16} className="process-chevron" />
                          <ToolStatusIndicator status={tool.status} />
                          <AgentStatusText active={active && processOpen && ownerTool === tool.key}>
                            {tool.status === "running"
                              ? processText("מריץ כלי", "Running tool")
                              : tool.status === "preparing" ? processText("מכין כלי", "Preparing tool")
                              : tool.status === "waiting" ? processText("ממתין לאישור הפעלת כלי", "Waiting for tool approval")
                              : tool.status === "error"
                                ? processText("שגיאה", "Error")
                                : processText("הסתיים", "Finished")}{" "}
                            {tool.name}
                          </AgentStatusText>
                          <Icon name={toolTypeIcon(tool.icon)} />
                        </summary>
                        <div>
                          <strong>{processText("קלט ופרמטרי הפעלה", "Input and parameters")}</strong>
                          <pre dir="ltr">{tool.query || processText("אין קלט.", "No input.")}</pre>
                          {["finished", "error"].includes(tool.status) && (
                            <>
                              <strong>{processText("פלט הכלי", "Tool output")}</strong>
                              <pre dir="ltr">{tool.output || processText("אין פלט.", "No output.")}</pre>
                            </>
                          )}
                        </div>
                      </details>
                    ))}
                  </div>
                </details>
              ),
            )}
          </div>
        </details>
      )}
      {message.role === "assistant" && <span className="sds-visually-hidden" role="status" aria-live="polite" aria-atomic="true">{announcement}</span>}
      {retryLabel && <WaitingIndicator immediate shimmer={!rows.length || processOpen && !ownerRow} label={retryLabel}/>}
      {canThink && <WaitingIndicator key={agentEvents.filter(event => event.type === "report").slice(-1)[0]?.liveEventId || "initial"} immediate={stream?.stage === "prefill" || stream?.stage === "thinking"} shimmer={!rows.length || processOpen && !ownerRow} label={stream?.stage === "prefill" ? `${processText("מעבד הנחיה", "Processing prompt")}${stream.percent == null ? "…" : `: ${stream.percent}%`}` : processText("חושב...", "Thinking...")}/>}
      {attachmentStrip}
      {message.role === "user" ? !!message.content && <UserBubble isNew={isNew}>
        {content}
        {collapsible && <div className="message-user-disclosure"><IconButton tooltip={false} icon="chevron" variant="ghost" className="message-expand-button" label={userExpanded ? "כווץ הודעה" : "הרחב הודעה"} aria-expanded={userExpanded} aria-controls={contentId} onClick={event => preserveDisclosure(event.currentTarget.closest<HTMLElement>(".sds-user-bubble") || event.currentTarget, () => { setUserExpanded(!userExpanded); remember("user", !userExpanded); })} /></div>}
      </UserBubble> : content}
      {message.role === "assistant" && (runStatus || message.metadata?.run_status) === "cancelled" && <p className="agent-initial-thinking">{processText("היצירה נעצרה. התשובה שהתקבלה עד העצירה נשמרה.", "Generation stopped. The answer received before stopping was saved.")}</p>}

      </MessageFrame>
    </article></DesignSystemProvider>
  );
});
