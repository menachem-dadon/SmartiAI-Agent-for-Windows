import { memo, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps, ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage, RunEvent } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { DesignSystemProvider, Icon, IconButton, MessageFrame, UserBubble, toolIcons } from "./design-system";
import "./chat.css";
import { legacyUi } from "./legacyUiParity";
import { MessageTable } from "./MessageTable";
import { useSpeechPlayback } from "./speechPlayback";
import {
  agentToolIconName,
  type AgentToolIconName,
} from "./agentToolIcons";

const copy = async (text: string) => navigator.clipboard.writeText(text);
const WINDOWS_PATH = /^[A-Za-z]:[\\/]/;
function localHref(value: string): string {
  const normalized = WINDOWS_PATH.test(value)
    ? `file:///${value.replace(/\\/g, "/")}`
    : value;
  return encodeURI(normalized).replace(/#/g, "%23");
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
  const pathname = decodeURIComponent(url.pathname).replace(/\//g, "\\");
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
  return source ? <img src={source} alt={name} /> : <span>IMG</span>;
}

type AgentEvent = {
  type: string;
  liveEventId?: number;
  text?: string;
  tools?: unknown[];
  results?: unknown[];
  group?: Record<string, unknown>;
};
type ToolView = {
  key: string;
  name: string;
  icon: AgentToolIconName;
  status: "running" | "finished" | "error";
  query: string;
  output: string;
};
type ProcessRow =
  | { kind: "report"; key: string; text: string }
  | {
      kind: "tools";
      key: string;
      standalone: boolean;
      label: string;
      icon: AgentToolIconName;
      tools: ToolView[];
      running: boolean;
    };
type AgentProcessMetadata = { elapsed_seconds?: number; events?: AgentEvent[] };

const payloadText = (value: unknown) =>
  typeof value === "string"
    ? value
    : value == null
      ? ""
      : JSON.stringify(value, null, 2);
const toolName = (item: Record<string, unknown>) =>
  String(
    item.effective_action || item.action || item.tool || item.name || "כלי",
  );
const toolKey = (item: Record<string, unknown>, fallback: string) =>
  String(
    item.event_id ||
      item.tool_call_id ||
      item.call_id ||
      `${toolName(item)}:${fallback}`,
  );
function toolFrom(
  item: unknown,
  status: ToolView["status"],
  fallback: string,
): ToolView {
  const value =
    item && typeof item === "object"
      ? (item as Record<string, unknown>)
      : { action: String(item || "כלי") };
  return {
    key: toolKey(value, fallback),
    name: toolName(value),
    icon: agentToolIconName(value),
    status,
    query: payloadText(
      value.arguments_text ||
        value.arguments ||
        value.args ||
        value.input ||
        value.query,
    ),
    output: payloadText(
      value.output_text ||
        value.output ||
        value.result ||
        value.feedback ||
        value.message ||
        value.error,
    ),
  };
}
function eventFromRun(event: RunEvent): AgentEvent | null {
  if (event.event_type === "run_step") {
    const value = event.payload.value;
    if (value && typeof value === "object")
      return { ...(value as AgentEvent), liveEventId: event.event_id };
    const text = String(value || event.payload.step || "").trim();
    return text ? { type: "report", text, liveEventId: event.event_id } : null;
  }
  if (event.event_type === "tool_started")
    return {
      type: "tool_start",
      liveEventId: event.event_id,
      tools: [
        { ...event.payload, action: event.payload.tool || event.payload.name },
      ],
    };
  if (event.event_type === "tool_finished")
    return {
      type: "tool_finish",
      liveEventId: event.event_id,
      results: [
        { ...event.payload, action: event.payload.tool || event.payload.name },
      ],
    };
  if (event.event_type === "api_key_required")
    return { type: "report", text: "ממתין למפתח API", liveEventId: event.event_id };
  return null;
}
export function processRows(agentEvents: AgentEvent[]): ProcessRow[] {
  const rows: ProcessRow[] = [];
  let current: Extract<ProcessRow, { kind: "tools" }> | null = null;
  for (const [index, event] of agentEvents.entries()) {
    if (event.type === "report") {
      const text = String(event.text || "").trim();
      // Older clients projected approval waits into process history. Permission
      // state is now owned by the durable approval queue, including on replay.
      if (/^ממתין לאישור(?: משתמש)?\.{0,3}$/u.test(text)) continue;
      if (text) rows.push({ kind: "report", key: `report-${index}`, text });
      current = null;
    } else if (event.type === "tool_start") {
      if (!current || current.standalone) {
        current = {
          kind: "tools",
          key: `tools-${index}`,
          standalone: false,
          label: "מריץ כלים",
          icon: "row_status",
          tools: [],
          running: true,
        };
        rows.push(current);
      }
      for (const [toolIndex, tool] of (event.tools || []).entries())
        current.tools.push(toolFrom(tool, "running", `${index}-${toolIndex}`));
    } else if (event.type === "tool_finish") {
      for (const [resultIndex, result] of (event.results || []).entries()) {
        const record =
          result && typeof result === "object"
            ? (result as Record<string, unknown>)
            : {};
        const status = String(record.status || "").toLowerCase();
        const failed =
          Boolean(record.error) ||
          ["error", "failed", "crashed", "cancelled"].includes(status);
        const finished = toolFrom(
          result,
          failed ? "error" : "finished",
          `${index}-${resultIndex}`,
        );
        // A report can arrive while tools are running. Match their original
        // rows, and finish only the reported calls (including parallel calls
        // to the same tool that complete out of order).
        const identity = record.event_id || record.tool_call_id || record.call_id;
        const existing = rows
          .flatMap((row) => row.kind === "tools" ? row.tools : [])
          .reverse()
          .find(
            (tool) =>
              identity
                ? tool.key === finished.key
                : tool.name === finished.name && tool.status === "running",
          );
        if (existing) {
          Object.assign(existing, finished, {
            key: existing.key,
            query: finished.query || existing.query,
          });
        } else {
          if (!current || current.standalone) {
            current = {
              kind: "tools",
              key: `tools-${index}`,
              standalone: false,
              label: "כלים הסתיימו",
              icon: "row_status",
              tools: [],
              running: false,
            };
            rows.push(current);
          }
          current.tools.push(finished);
        }
      }
    } else if (
      event.type === "tool_group_start" ||
      event.type === "tool_group_finish"
    ) {
      const group = event.group || {};
      const running = event.type === "tool_group_start";
      const label = String(
        event.text ||
          group.label ||
          group.title ||
          group.action ||
          (running ? "מבצע פעילות" : "הפעילות הסתיימה"),
      );
      const identity = String(
        group.id || group.event_id || group.action || index,
      );
      const existing = [...rows]
        .reverse()
        .find(
          (row): row is Extract<ProcessRow, { kind: "tools" }> =>
            row.kind === "tools" &&
            row.standalone &&
            row.key === `group-${identity}`,
        );
      if (existing) {
        existing.label = label;
        existing.icon = agentToolIconName(group);
        existing.running = running;
      } else
        rows.push({
          kind: "tools",
          key: `group-${identity}`,
          standalone: true,
          label,
          icon: agentToolIconName(group),
          tools: [],
          running,
        });
      current = null;
    }
  }
  for (const row of rows) {
    if (row.kind !== "tools" || row.standalone) continue;
    const running = row.tools.filter((tool) => tool.status === "running");
    row.running = running.length > 0;
    row.label = running.length
      ? running.length === 1
        ? `מריץ: ${running[0].name}`
        : `מריץ ${running.length} כלים במקביל`
      : row.tools.length === 1 ? "הורץ כלי 1" : `הורצו ${row.tools.length} כלים`;
  }
  return rows;
}

function AgentStatusText({ active, children }: { active: boolean; children: ReactNode }) {
  return <span className={`agent-status-text${active ? " is-shimmering" : ""}`}>{children}</span>;
}

function DelayedThinking() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setVisible(true), 300);
    return () => window.clearTimeout(timer);
  }, []);
  return visible
    ? <p className="agent-initial-thinking"><AgentStatusText active>חושב...</AgentStatusText></p>
    : null;
}

export function formatAgentDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds || 0));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
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
  onOpenCanvas,
  isNew = false,
}: {
  message: ChatMessage;
  events?: RunEvent[];
  theme?: ResolvedTheme;
  active?: boolean;
  runStatus?: string;
  onOpenCanvas?: (canvasId: string) => void;
  isNew?: boolean;
}) {
  const [processOpen, setProcessOpen] = useState(active);
  const speechOwner = useId();
  const speech = useSpeechPlayback(message.metadata?.run_id
    ? `run:${message.metadata.run_id}` : `message:${speechOwner}`);
  const { speaking } = speech;
  const [userExpanded, setUserExpanded] = useState(false);
  const [userContentHeight, setUserContentHeight] = useState(0);
  const contentId = useId();
  const [, setElapsedTick] = useState(0);
  const [collapsible, setCollapsible] = useState(false);
  const [linkError, setLinkError] = useState("");
  const contentRef = useRef<HTMLDivElement>(null);
  // Keep each table mounted while streamed content and elapsed time update.
  const renderTable = useMemo(() =>
    (props: ComponentProps<typeof MessageTable>) => <MessageTable {...props} theme={theme} />,
  [theme]);
  useEffect(() => {
    if (!active) {
      setProcessOpen(false);
      return;
    }
    setProcessOpen(true);
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
    if (storedProcess?.events?.length) return storedProcess.events;
    // Initial run loading and replay polling can deliver the same event.
    // Count each tool call once so a duplicate start cannot keep it running.
    return [...new Map(events.map((event) => [event.event_id, event])).values()]
      .map(eventFromRun)
      .filter((item): item is AgentEvent => Boolean(item));
  }, [events, message.role, storedProcess]);
  const rows = useMemo(() => processRows(agentEvents), [agentEvents]);
  const canThink = active && message.role === "assistant" && !message.content &&
    (!runStatus || runStatus === "queued" || runStatus === "running") &&
    !rows.some((row) => row.kind === "tools" && row.running);
  // Reset the short pause when visible process content changes. Repeated
  // thinking/status events and ordinary rerenders must not postpone it.
  let lastActivityIndex = agentEvents.length - 1;
  while (lastActivityIndex >= 0 && ![
    "report", "tool_start", "tool_finish", "tool_group_start", "tool_group_finish",
  ].includes(agentEvents[lastActivityIndex].type)) lastActivityIndex -= 1;
  const thinkingKey = `${String(message.metadata?.run_id || "")}:${
    agentEvents[lastActivityIndex]?.liveEventId ?? lastActivityIndex
  }`;
  const firstLiveAt = events
    .map((event) => Date.parse(event.created_at))
    .filter(Number.isFinite)
    .sort((a, b) => a - b)[0];
  const elapsed =
    storedProcess?.elapsed_seconds ??
    (active && firstLiveAt
      ? Math.max(0, Math.floor((Date.now() - firstLiveAt) / 1000))
      : 0);
  useLayoutEffect(() => {
    const node = contentRef.current;
    if (!node || message.role !== "user") {
      setCollapsible(false);
      return;
    }
    const measure = () => {
      const line = Number.parseFloat(getComputedStyle(node).lineHeight) || 23;
      // Measure the unclipped content so both directions have a real height
      // target, including after wrapping, fonts or embedded content change.
      const height = node.scrollHeight;
      setUserContentHeight(height);
      setCollapsible(
        message.content.split("\n").length > legacyUi.userCollapsedLines ||
          height > line * legacyUi.userCollapsedLines + 2,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [message.content, message.role]);
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
    !active && Boolean(message.content.trim() || message.attachments?.length);
  const openLink = async (href: string) => {
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
  };
  const content = (<div
        className={`chat-message chat-message--${message.role} ${isError ? "is-error" : ""} ${backgroundTask ? "is-background-task" : ""}`}
      >
        {backgroundTask && (
          <strong className="background-task-badge">⚡ משימת רקע</strong>
        )}
        {!!message.attachments?.length && (
          <div className="sent-attachments">
            {message.attachments.map((item, index) =>
              item.kind === "image" && item.path ? (
                <span className="sent-image" key={`${item.name}-${index}`}>
                  <SentImage
                    path={item.path}
                    name={item.name}
                    mimeType={item.mime_type}
                  />
                </span>
              ) : (
                <span className="attachment-tile" key={`${item.name}-${index}`}>
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
                </span>
              ),
            )}
          </div>
        )}
        {!!message.content && (
          <div
            id={contentId}
            className={`message-content ${collapsible ? "is-collapsible" : ""} ${collapsible && !userExpanded ? "is-collapsed" : ""}`}
            style={collapsible ? { maxHeight: userExpanded ? userContentHeight : 146 } : undefined}
          >
            <div ref={contentRef} className="message-content-body">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                urlTransform={safeChatHref}
                components={{
                  table: renderTable,
                  a: ({ href = "", node: _node, ...props }) => (
                    <a
                      {...props}
                      href={href}
                      onClick={(event) => {
                        event.preventDefault();
                        if (href) void openLink(href);
                      }}
                    />
                  ),
                  code: ({ children, className, ...props }) => (
                    <code {...props} className={className} dir="ltr">
                      {children}
                    </code>
                  ),
                  pre: ({ children }) => <CodeFrame onCopy={copy} onDownload={downloadCode}>{children}</CodeFrame>,
                }}
              >
                {prepareMessageMarkdown(message.content)}
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
          <IconButton tooltip={false} icon="copy" label="העתק" variant="ghost" onClick={() => void copy(message.content).catch(reason => setLinkError(`ההעתקה נכשלה: ${String(reason)}`))} />
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
          {collapsible && (
            <IconButton
              icon="chevron" variant="ghost" className="message-expand-button"
              label={userExpanded ? "כווץ הודעה" : "הרחב הודעה"}
              aria-expanded={userExpanded}
              aria-controls={contentId}
              onClick={() => setUserExpanded((value) => !value)}
            />
          )}
        </div>
      )}>
      {!!rows.length && (
        <details
          className="agent-process"
          open={processOpen}
          onToggle={(event) => setProcessOpen(event.currentTarget.open)}
        >
          <summary>
            <Icon name="chevron" size={16} className="process-chevron" />
            <AgentStatusText active={active}>
              {active ? "סמארטי עובד" : "סמארטי עבד"}{" "}
              {formatAgentDuration(elapsed)}
            </AgentStatusText>
            <Icon name="activity" size={20} />
          </summary>
          <div className="agent-process-details">
            {rows.map((row) =>
              row.kind === "report" ? (
                <p className="agent-report" key={row.key}>
                  {row.text}
                </p>
              ) : row.standalone ? (
                <p
                  className="agent-standalone"
                  key={row.key}
                >
                  <Icon name={toolIcons[row.icon] || "tools"} />
                  <AgentStatusText active={active && row.running}>{row.label}</AgentStatusText>
                </p>
              ) : (
                <details className="agent-tool-group" key={row.key}>
                  <summary>
                    <Icon name="chevron" size={16} className="process-chevron" />
                    <AgentStatusText active={active && row.running}>
                      {row.label}
                    </AgentStatusText>
                    <Icon name={row.running && row.tools.filter(tool => tool.status === "running").length === 1
                      ? toolIcons[row.tools.find(tool => tool.status === "running")!.icon] || "tools" : "tools"} />
                  </summary>
                  <div>
                    {row.tools.map((tool) => (
                      <details className="agent-tool-row" key={tool.key}>
                        <summary>
                          <Icon name="chevron" size={16} className="process-chevron" />
                          <AgentStatusText active={active && tool.status === "running"}>
                            {tool.status === "running"
                              ? "רץ"
                              : tool.status === "error"
                                ? "שגיאה"
                                : "הסתיים"}{" "}
                            · {tool.name}
                          </AgentStatusText>
                          <Icon name={toolIcons[tool.icon] || "tools"} />
                        </summary>
                        <div>
                          <strong>קלט ופרמטרי הפעלה</strong>
                          <pre dir="ltr">{tool.query || "אין קלט."}</pre>
                          {tool.status !== "running" && (
                            <>
                              <strong>פלט הכלי</strong>
                              <pre dir="ltr">{tool.output || "אין פלט."}</pre>
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
      {canThink && <DelayedThinking key={thinkingKey} />}
      {message.role === "user" ? <UserBubble isNew={isNew}>{content}</UserBubble> : content}

      </MessageFrame>
    </article></DesignSystemProvider>
  );
});
