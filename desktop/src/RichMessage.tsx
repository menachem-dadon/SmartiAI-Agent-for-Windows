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
import {
  agentToolIconName,
  type AgentToolIconName,
} from "./agentToolIcons";

function contentIdentity(text: string) { let hash = 0; for (const character of text) hash = (hash * 31 + character.charCodeAt(0)) | 0; return String(hash); }

const copy = async (text: string) => navigator.clipboard.writeText(text);
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
  status: "preparing" | "waiting" | "running" | "finished" | "error";
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
    } else if (["tool_start", "tool_preparing", "tool_waiting"].includes(event.type)) {
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
      for (const [toolIndex, tool] of (event.tools || []).entries()) {
        const next = toolFrom(tool, event.type === "tool_preparing" ? "preparing" : event.type === "tool_waiting" ? "waiting" : "running", `${index}-${toolIndex}`);
        const existing = rows.flatMap(row => row.kind === "tools" ? row.tools : []).find(item => item.key === next.key);
        if (existing) Object.assign(existing, next); else current.tools.push(next);
      }
    } else if (event.type === "tool_finish") {
      for (const [resultIndex, result] of (event.results || []).entries()) {
        const record =
          result && typeof result === "object"
            ? (result as Record<string, unknown>)
            : {};
        const status = String(record.status || "").toLowerCase();
        const failed =
          Boolean(record.error) ||
          ["error", "failed", "crashed", "cancelled", "denied", "expired"].includes(status);
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
    const running = row.tools.filter((tool) => ["running", "preparing", "waiting"].includes(tool.status));
    row.running = running.length > 0;
    row.label = running.length
      ? running.length === 1
        ? `${running[0].status === "preparing" ? "מכין כלי" : running[0].status === "waiting" ? "ממתין לאישור הפעלת כלי" : "מריץ כלי"} ${running[0].name}`
        : `מריץ ${running.length} כלים במקביל`
      : row.tools.length === 1 ? "הורץ כלי 1" : `הורצו ${row.tools.length} כלים`;
  }
  return rows;
}

function AgentStatusText({ active, children }: { active: boolean; children: ReactNode }) {
  return <span className={`agent-status-text${active ? " is-shimmering" : ""}`}>{children}</span>;
}

function WaitingIndicator({ label, shimmer, immediate }: { label: string; shimmer: boolean; immediate: boolean }) {
  const [visible, setVisible] = useState(immediate);
  useEffect(() => { if (immediate) { setVisible(true); return; } const timer = setTimeout(() => setVisible(true), 300); return () => clearTimeout(timer); }, [immediate]);
  return visible ? <p className="agent-initial-thinking"><AgentStatusText active={shimmer}>{label}</AgentStatusText></p> : null;
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
    if (storedProcess?.events?.length) return storedProcess.events;
    // Initial run loading and replay polling can deliver the same event.
    // Count each tool call once so a duplicate start cannot keep it running.
    return [...new Map(events.map((event) => [event.event_id, event])).values()]
      .map(eventFromRun)
      .filter((item): item is AgentEvent => Boolean(item));
  }, [events, message.role, storedProcess]);
  const rows = useMemo(() => {
    const pending: AgentEvent[] = [];
    const reports = Object.values(stream?.blocks || {}).filter(block => block.kind === "text" && block.role === "report" && block.text?.trim());
    const normalized = (text: string) => text.replace(/\s+/g, " ").replace(/\.\.\.$/, "").trim();
    const renderedEvents = agentEvents.map(event => event.type === "report"
      ? { ...event, text: reports.find(block => normalized(block.text || "").startsWith(normalized(event.text || "")))?.text || event.text } : event);
    const existingIds = new Set(agentEvents.flatMap(event => [...event.tools || [], ...event.results || []]).map(item => toolKey(item as Record<string, unknown>, "")));
    for (const [id, block] of Object.entries(stream?.blocks || {})) {
      if (block.kind === "tool" && !existingIds.has(block.call_id || id)) pending.push({ type: "tool_preparing", tools: [{ call_id: block.call_id || id, name: block.name, arguments_text: block.arguments_text }] });
      if (block.kind === "text" && block.role === "report" && block.text?.trim() && !agentEvents.some(event => event.type === "report" && normalized(block.text || "").startsWith(normalized(event.text || "")))) pending.push({ type: "report", text: block.text });
    }
    const result = processRows([...renderedEvents, ...pending]);
    if (runStatus === "waiting_for_approval" && !agentEvents.some(event => event.type === "tool_waiting")) for (const row of result) if (row.kind === "tools") { for (const tool of row.tools) if (tool.status === "running") tool.status = "waiting"; const waiting = row.tools.find(tool => tool.status === "waiting"); if (waiting) row.label = `ממתין לאישור הפעלת כלי ${waiting.name}`; }
    if (!active) for (const row of result) if (row.kind === "tools" && row.tools.some(tool => ["preparing", "running", "waiting"].includes(tool.status))) {
      for (const tool of row.tools) if (["preparing", "running", "waiting"].includes(tool.status)) tool.status = "error";
      row.running = false; row.label = runStatus === "cancelled" ? "הפעלת כלי נעצרה" : "הפעלת כלי לא הושלמה";
    }
    return result;
  }, [agentEvents, stream, runStatus, active]);
  const activeRows = rows.filter(row => row.kind === "tools" && row.running);
  const ownerRow = activeRows.find(row => row.kind === "tools" && preferences[row.key]) || activeRows[0];
  const ownerTool = ownerRow?.kind === "tools" && preferences[ownerRow.key] ? ownerRow.tools.find(tool => ["running", "preparing", "waiting"].includes(tool.status))?.key : undefined;
  const canThink = active && message.role === "assistant" && !message.content &&
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
        </div>
      )}>
      {!!rows.length && (
        <details
          className="agent-process"
          open={processOpen}
        >
          <summary onClick={event => { event.preventDefault(); processManual.current = true; preserveDisclosure(event.currentTarget, () => { setProcessOpen(!processOpen); remember("process", !processOpen); }); }}>
            <Icon name="chevron" size={16} className="process-chevron" />
            <AgentStatusText active={active && !processOpen}>
              {active ? "סמארטי עובד" : "סמארטי עבד"}{" "}
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
                    <AgentStatusText active={active && processOpen && ownerRow?.key === row.key && !preferences[row.key]}>
                      {row.tools.some(tool => tool.status === "preparing") && <span className="tool-preparation-ring" aria-hidden="true"/>}
                      {row.label}
                    </AgentStatusText>
                    <Icon name={row.running && row.tools.filter(tool => tool.status === "running").length === 1
                      ? toolIcons[row.tools.find(tool => tool.status === "running")!.icon] || "tools" : "tools"} />
                  </summary>
                  <div>
                    {row.tools.map((tool) => (
                      <details className="agent-tool-row" key={tool.key} open={!!preferences[tool.key]}>
                        <summary onClick={event => { event.preventDefault(); preserveDisclosure(event.currentTarget, () => remember(tool.key, !preferences[tool.key])); }}>
                          <Icon name="chevron" size={16} className="process-chevron" />
                          <AgentStatusText active={active && processOpen && ownerTool === tool.key}>
                            {tool.status === "preparing" ? <span className="tool-preparation-ring" aria-hidden="true"/> : null}
                            {tool.status === "running"
                              ? "מריץ כלי"
                              : tool.status === "preparing" ? "מכין כלי"
                              : tool.status === "waiting" ? "ממתין לאישור הפעלת כלי"
                              : tool.status === "error"
                                ? "שגיאה"
                                : "הסתיים"}{" "}
                            {tool.name}
                          </AgentStatusText>
                          <Icon name={toolIcons[tool.icon] || "tools"} />
                        </summary>
                        <div>
                          <strong>קלט ופרמטרי הפעלה</strong>
                          <pre dir="ltr">{tool.query || "אין קלט."}</pre>
                          {["finished", "error"].includes(tool.status) && (
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
      {canThink && <WaitingIndicator key={agentEvents.filter(event => event.type === "report").slice(-1)[0]?.liveEventId || "initial"} immediate={stream?.stage === "prefill" || stream?.stage === "thinking"} shimmer={!rows.length || processOpen && !ownerRow} label={stream?.stage === "prefill" ? `מעבד הנחיה${stream.percent == null ? "…" : `: ${stream.percent}%`}` : "חושב..."}/>}
      {attachmentStrip}
      {message.role === "user" ? !!message.content && <UserBubble isNew={isNew}>
        {content}
        {collapsible && <div className="message-user-disclosure"><IconButton tooltip={false} icon="chevron" variant="ghost" className="message-expand-button" label={userExpanded ? "כווץ הודעה" : "הרחב הודעה"} aria-expanded={userExpanded} aria-controls={contentId} onClick={event => preserveDisclosure(event.currentTarget.closest<HTMLElement>(".sds-user-bubble") || event.currentTarget, () => { setUserExpanded(!userExpanded); remember("user", !userExpanded); })} /></div>}
      </UserBubble> : content}
      {message.role === "assistant" && (runStatus || message.metadata?.run_status) === "cancelled" && <p className="agent-initial-thinking">היצירה נעצרה. התשובה שהתקבלה עד העצירה נשמרה.</p>}

      </MessageFrame>
    </article></DesignSystemProvider>
  );
});
