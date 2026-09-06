import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage, RunEvent } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import { coreApi } from "./coreApi";
import { IconButton } from "./ui";
import { legacyUi } from "./legacyUiParity";
import {
  agentToolGroupIcon,
  agentToolIcon,
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
    if (value && typeof value === "object") return value as AgentEvent;
    const text = String(value || event.payload.step || "").trim();
    return text ? { type: "report", text } : null;
  }
  if (event.event_type === "tool_started")
    return {
      type: "tool_start",
      tools: [
        { ...event.payload, action: event.payload.tool || event.payload.name },
      ],
    };
  if (event.event_type === "tool_finished")
    return {
      type: "tool_finish",
      results: [
        { ...event.payload, action: event.payload.tool || event.payload.name },
      ],
    };
  if (event.event_type === "approval_requested")
    return { type: "report", text: "ממתין לאישור" };
  if (event.event_type === "api_key_required")
    return { type: "report", text: "ממתין למפתח API" };
  return null;
}
export function processRows(agentEvents: AgentEvent[]): ProcessRow[] {
  const rows: ProcessRow[] = [];
  let current: Extract<ProcessRow, { kind: "tools" }> | null = null;
  for (const [index, event] of agentEvents.entries()) {
    if (event.type === "report") {
      const text = String(event.text || "").trim();
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
      const count = current.tools.length;
      current.label =
        count === 1
          ? `מריץ: ${current.tools[0].name}`
          : `מריץ ${count} כלים במקביל`;
      current.running = true;
    } else if (event.type === "tool_finish") {
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
        const existing = [...current.tools]
          .reverse()
          .find(
            (tool) =>
              tool.key === finished.key ||
              (tool.name === finished.name && tool.status === "running"),
          );
        if (existing) Object.assign(existing, finished);
        else current.tools.push(finished);
      }
      for (const tool of current.tools)
        if (tool.status === "running") tool.status = "finished";
      current.running = false;
      const count = current.tools.length;
      current.label = count === 1 ? "הורץ כלי 1" : `הורצו ${count} כלים`;
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
  return rows;
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

export function RichMessage({
  message,
  events = [],
  theme = "dark",
  active = false,
  onOpenCanvas,
}: {
  message: ChatMessage;
  events?: RunEvent[];
  theme?: ResolvedTheme;
  active?: boolean;
  onOpenCanvas?: (canvasId: string) => void;
}) {
  const [processOpen, setProcessOpen] = useState(active);
  const [speaking, setSpeaking] = useState(false);
  const [userExpanded, setUserExpanded] = useState(false);
  const [, setElapsedTick] = useState(0);
  const [collapsible, setCollapsible] = useState(false);
  const [linkError, setLinkError] = useState("");
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!speaking) return;
    const timer = window.setInterval(() => {
      void coreApi<{ is_playing: boolean }>("GET", "/v2/audio/tts/status").then(
        (state) => {
          if (!state.is_playing) setSpeaking(false);
        },
      );
    }, 900);
    return () => clearInterval(timer);
  }, [speaking]);
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
  const speak = async () => {
    if (speaking) {
      await coreApi("POST", "/v2/audio/tts/stop", {}, true);
      setSpeaking(false);
      return;
    }
    setSpeaking(true);
    try {
      await coreApi("POST", "/v2/audio/tts", { text: message.content }, true);
    } catch {
      setSpeaking(false);
    }
  };
  const storedProcess =
    message.role === "assistant" &&
    message.metadata?.agent_process &&
    typeof message.metadata.agent_process === "object"
      ? (message.metadata.agent_process as AgentProcessMetadata)
      : null;
  const agentEvents = useMemo(
    () =>
      message.role !== "assistant"
        ? []
        : storedProcess?.events?.length
          ? storedProcess.events
          : events
              .map(eventFromRun)
              .filter((item): item is AgentEvent => Boolean(item)),
    [events, message.role, storedProcess],
  );
  const rows = useMemo(() => processRows(agentEvents), [agentEvents]);
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
      setCollapsible(
        message.content.split("\n").length > legacyUi.userCollapsedLines ||
          node.scrollHeight > line * legacyUi.userCollapsedLines + 2,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [message.content, message.role]);
  const icons = legacyAssets(theme);
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
  return (
    <article
      className={`chat-message-row chat-message-row--${message.role} ${backgroundTask ? "is-background-task" : ""}`}
      data-run-id={String(message.metadata?.run_id || "") || undefined}
      dir="auto"
    >
      {active && !rows.length && !message.content && (
        <p className="agent-initial-thinking is-shimmering">חושב...</p>
      )}
      {!!rows.length && (
        <details
          className="agent-process"
          open={processOpen}
          onToggle={(event) => setProcessOpen(event.currentTarget.open)}
        >
          <summary>
            <LegacyIcon src={icons.dropdown} size={16} />
            <span className={active ? "is-shimmering" : ""}>
              {active ? "סמארטי עובד" : "סמארטי עבד"}{" "}
              {formatAgentDuration(elapsed)}
            </span>
          </summary>
          <div className="agent-process-details">
            {rows.map((row) =>
              row.kind === "report" ? (
                <p className="agent-report" key={row.key}>
                  {row.text}
                </p>
              ) : row.standalone ? (
                <p
                  className={
                    row.running
                      ? "agent-standalone is-shimmering"
                      : "agent-standalone"
                  }
                  key={row.key}
                >
                  <LegacyIcon src={agentToolIcon(theme, row.icon)} size={16} />
                  {row.label}
                </p>
              ) : (
                <details className="agent-tool-group" key={row.key}>
                  <summary>
                    <LegacyIcon src={icons.dropdown} size={14} />
                    <span className={row.running ? "is-shimmering" : ""}>
                      {row.label}
                    </span>
                    <LegacyIcon
                      src={
                        row.running &&
                        row.tools.filter((tool) => tool.status === "running")
                          .length === 1
                          ? agentToolIcon(
                              theme,
                              row.tools.find(
                                (tool) => tool.status === "running",
                              )!.icon,
                            )
                          : agentToolGroupIcon(theme)
                      }
                      size={16}
                    />
                  </summary>
                  <div>
                    {row.tools.map((tool) => (
                      <details className="agent-tool-row" key={tool.key}>
                        <summary>
                          <LegacyIcon src={icons.dropdown} size={14} />
                          <span>
                            {tool.status === "running"
                              ? "רץ"
                              : tool.status === "error"
                                ? "שגיאה"
                                : "הסתיים"}{" "}
                            · {tool.name}
                          </span>
                          <LegacyIcon
                            src={agentToolIcon(theme, tool.icon)}
                            size={16}
                          />
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
      <div
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
                    <LegacyIcon src={icons.file} size={28} />
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
            ref={contentRef}
            className={`message-content ${collapsible && !userExpanded ? "is-collapsed" : ""}`}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              urlTransform={safeChatHref}
              components={{
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
                pre: ({ children }) => {
                  const text = codeText(children);
                  const language = codeLanguage(children);
                  return (
                    <div className="code-frame" dir="ltr">
                      <div className="code-frame-head">
                        <button
                          type="button"
                          aria-label="העתק קוד"
                          onClick={() => void copy(text)}
                        >
                          <LegacyIcon src={icons.copy} size={18} />
                        </button>
                        <button
                          type="button"
                          aria-label="הורד קובץ"
                          onClick={() => void downloadCode(text, language)}
                        >
                          <LegacyIcon src={icons.codeDownload} size={18} />
                        </button>
                        <span>{codeDisplayLanguage(language)}</span>
                      </div>
                      <pre>{children}</pre>
                    </div>
                  );
                },
              }}
            >
              {prepareMessageMarkdown(message.content)}
            </ReactMarkdown>
          </div>
        )}
        {linkError && (
          <p className="message-link-error" role="alert">
            {linkError}
          </p>
        )}
        {!!canvases.length && (
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
                <LegacyIcon src={icons.canvas} size={30} />
              </article>
            ))}
          </div>
        )}
      </div>
      {actionsAvailable && (
        <div className="message-actions">
          <IconButton label="העתק" onClick={() => void copy(message.content)}>
            <LegacyIcon src={icons.copy} size={22} />
          </IconButton>
          {message.role === "assistant" && (
            <IconButton
              label={speaking ? "עצור הקראה" : "הקרא בקול"}
              onClick={() => void speak()}
            >
              {speaking ? "■" : <LegacyIcon src={icons.speaker} size={22} />}
            </IconButton>
          )}
          {memoryUpdated && (
            <span className="memory-updated">
              <LegacyIcon src={icons.agentMemory} size={15} />
              הזיכרון עודכן
            </span>
          )}
          {collapsible && (
            <IconButton
              label={userExpanded ? "כווץ הודעה" : "הרחב הודעה"}
              onClick={() => setUserExpanded((value) => !value)}
            >
              <LegacyIcon src={icons.dropdown} size={18} />
            </IconButton>
          )}
        </div>
      )}
    </article>
  );
}
