import type { RunEvent } from "./chatTypes";
import { agentToolIconName, type AgentToolIconName } from "./agentToolIcons";
import type { StreamState } from "./chatStreaming";

export type AgentEvent = {
  type: string;
  id?: string;
  report_id?: string;
  request_id?: string;
  user_language?: "he" | "en";
  liveEventId?: number;
  text?: string;
  tools?: unknown[];
  results?: unknown[];
  group?: Record<string, unknown>;
};
export type ToolView = {
  key: string;
  name: string;
  icon: AgentToolIconName;
  status: "preparing" | "waiting" | "running" | "finished" | "error";
  query: string;
  output: string;
};
export type ProcessRow =
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
export type ProcessLanguage = "he" | "en";
// Fixed captions follow the application's Hebrew UI, not conversation metadata.
export const INTERFACE_LANGUAGE: ProcessLanguage = "he";
export type AgentProcessMetadata = { elapsed_seconds?: number; events?: AgentEvent[]; user_language?: ProcessLanguage };
export const processCaption = (language: ProcessLanguage, hebrew: string, english: string) => language === "en" ? english : hebrew;
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
      value.arguments_text ??
        value.arguments ??
        value.args ??
        value.input ??
        value.query,
    ),
    output: payloadText(
      value.output_text ??
        value.output ??
        value.result ??
        value.feedback ??
        value.message ??
        value.error,
    ),
  };
}
export function eventFromRun(event: RunEvent): AgentEvent | null {
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
        { ...event.payload, action: event.payload.action || event.payload.tool || event.payload.name },
      ],
    };
  if (event.event_type === "tool_finished")
    return {
      type: "tool_finish",
      liveEventId: event.event_id,
      results: [
        { ...event.payload, action: event.payload.action || event.payload.tool || event.payload.name },
      ],
    };
  if (event.event_type === "api_key_required")
    return { type: "api_key_wait", liveEventId: event.event_id };
  return null;
}
export function processRows(agentEvents: AgentEvent[], language: ProcessLanguage = INTERFACE_LANGUAGE): ProcessRow[] {
  const text = (he: string, en: string) => processCaption(language, he, en);
  const rows: ProcessRow[] = [];
  let current: Extract<ProcessRow, { kind: "tools" }> | null = null;
  const occurrences = new Map<string, number>();
  const reportKey = (event: AgentEvent, value: string) => {
    const identity = event.report_id || event.id || value;
    const occurrence = occurrences.get(identity) || 0;
    occurrences.set(identity, occurrence + 1);
    return `report-${identity}:${occurrence}`;
  };
  const groupFor = (tool: ToolView) => {
    if (!current || current.standalone) {
      current = { kind: "tools", key: `tools-${tool.key}`, standalone: false,
        label: "", icon: "row_status", tools: [], running: false };
      rows.push(current);
    }
    return current;
  };
  for (const [index, event] of agentEvents.entries()) {
    if (event.type === "api_key_wait") {
      rows.push({ kind: "report", key: reportKey(event, "api-key"), text: text("ממתין למפתח API", "Waiting for an API key") });
      current = null;
    } else if (event.type === "report") {
      const text = String(event.text || "").trim();
      // Older clients projected approval waits into process history. Permission
      // state is now owned by the durable approval queue, including on replay.
      if (/^(?:ממתין לאישור(?: משתמש)?|Waiting for user approval)\.{0,3}$/iu.test(text)) continue;
      if (text) rows.push({ kind: "report", key: reportKey(event, text), text });
      current = null;
    } else if (["tool_start", "tool_preparing", "tool_waiting"].includes(event.type)) {
      for (const [toolIndex, tool] of (event.tools || []).entries()) {
        const next = toolFrom(tool, event.type === "tool_preparing" ? "preparing" : event.type === "tool_waiting" ? "waiting" : "running", `${index}-${toolIndex}`);
        if (event.type === "tool_preparing" && (next.name === "כלי" || (tool as Record<string, unknown>)?.name_complete === false)) continue;
        const existing = rows.flatMap(row => row.kind === "tools" ? row.tools : []).find(item => item.key === next.key);
        if (existing) Object.assign(existing, next, { query: next.query || existing.query });
        else groupFor(next).tools.push(next);
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
                : tool.name === finished.name && ["preparing", "waiting", "running"].includes(tool.status),
          );
        if (existing) {
          Object.assign(existing, finished, {
            key: existing.key,
            name: finished.name === "כלי" ? existing.name : finished.name,
            query: finished.query || existing.query,
            icon: finished.icon === "row_status" ? existing.icon : finished.icon,
          });
        } else {
          groupFor(finished).tools.push(finished);
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
          (running ? text("מבצע פעילות", "Working") : text("הפעילות הסתיימה", "Activity finished")),
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
        ? `${running[0].status === "preparing" ? text("מכין כלי", "Preparing tool") : running[0].status === "waiting" ? text("ממתין לאישור הפעלת כלי", "Waiting for tool approval") : text("מריץ כלי", "Running tool")} ${running[0].name}`
        : text(`מריץ ${running.length} כלים במקביל`, `Running ${running.length} tools in parallel`)
      : row.tools.some(tool => tool.status === "error")
        ? row.tools.length === 1 ? text("הרצת כלי 1 נכשלה", "1 tool failed")
          : text(`הורצו ${row.tools.length} כלים; שגיאות: ${row.tools.filter(tool => tool.status === "error").length}`, `${row.tools.length} tools ran; errors: ${row.tools.filter(tool => tool.status === "error").length}`)
        : row.tools.length === 1 ? text("הורץ כלי 1", "Ran 1 tool") : text(`הורצו ${row.tools.length} כלים`, `Ran ${row.tools.length} tools`);
  }
  return rows;
}

/** Overlay live blocks by identity; legacy text matching must be unambiguous in both directions. */
export function mergeProcessEvents(events: AgentEvent[], stream?: StreamState, preparations = true): AgentEvent[] {
  const reports = Object.entries(stream?.blocks || {}).filter(([, block]) => block.kind === "text" && block.role === "report" && block.text?.trim());
  const normalized = (value: string) => value.replace(/\s+/g, " ").replace(/(?:\.{3}|…)$/, "").trim();
  const matches = new Map<string, number>();
  const claimed = new Set<number>();
  for (const [id, block] of reports) {
    const exact = events.map((event, index) => ({ event, index })).filter(({ event, index }) => !claimed.has(index) && event.type === "report" &&
      (event.report_id ? event.report_id === id : normalized(event.text || "") === normalized(block.text || "")));
    if (exact.length === 1) { matches.set(id, exact[0].index); claimed.add(exact[0].index); }
  }
  for (const [id, block] of reports) {
    if (matches.has(id)) continue;
    const candidates = events.map((event, index) => ({ event, index })).filter(({ event, index }) => !claimed.has(index) && !event.report_id && event.type === "report" && normalized(event.text || "") && normalized(block.text || "").startsWith(normalized(event.text || "")));
    if (candidates.length === 1 && reports.filter(([otherId, other]) => !matches.has(otherId) && normalized(other.text || "").startsWith(normalized(candidates[0].event.text || ""))).length === 1) {
      matches.set(id, candidates[0].index); claimed.add(candidates[0].index);
    }
  }
  const result = events.map((event, index) => {
    const match = reports.find(([id]) => matches.get(id) === index);
    return match ? { ...event, report_id: match[0], text: match[1].text } : event;
  });
  // An abandoned attempt's report belongs before the next durable report,
  // rather than after tools which were executed by that later attempt.
  for (let i = reports.length - 1; i >= 0; i--) {
    const [id, block] = reports[i];
    if (matches.has(id)) continue;
    const nextIds = new Set(reports.slice(i + 1).map(([key]) => key));
    const before = result.findIndex(event => Boolean(event.report_id && nextIds.has(event.report_id)) ||
      event.type === "tool_start" && (event.tools || []).some(tool => toolKey(tool as Record<string, unknown>, "").startsWith(`${id}:`)));
    result.splice(before < 0 ? result.length : before, 0, { type: "report", report_id: id, text: block.text });
  }
  if (preparations) {
    const existing = new Set(events.flatMap(event => [...event.tools || [], ...event.results || []]).map(item => toolKey(item as Record<string, unknown>, "")));
    for (const [id, block] of Object.entries(stream?.blocks || {})) {
      if (block.kind !== "tool" || !block.name?.trim() || block.name_complete === false || stream?.stage === "retry" ||
        (stream?.request_id && !(block.call_id || id).startsWith(`${stream.request_id}:`)) || existing.has(block.call_id || id)) continue;
      result.push({ type: "tool_preparing", tools: [{ call_id: block.call_id || id, action: block.name, arguments_text: block.arguments_text }] });
    }
  }
  return result;
}
