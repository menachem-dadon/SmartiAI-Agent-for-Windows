// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { RichMessage } from "./RichMessage";
import { mergeProcessEvents, processRows, type AgentEvent } from "./agentProcess";
import { reduceStream, type StreamState } from "./chatStreaming";
import type { RunEvent } from "./chatTypes";

const message = { role: "assistant" as const, content: "", metadata: { run_id: "r" } };
const step = (id: number, value: AgentEvent): RunEvent => ({ event_id: id, sequence: id, run_id: "r", session_id: "s", created_at: "", event_type: "run_step", payload: { value } });
const call = (id = "request:0") => ({ action: "browser_automation_manager", event_id: id, arguments_text: '{"action":"open"}' });
const start: AgentEvent = { type: "tool_start", tools: [call()] };
const finish: AgentEvent = { type: "tool_finish", results: [{ ...call(), status: "ok", output_text: "SUCCESS" }] };
const stream = (name = "browser_automation_manager", name_complete = true): StreamState => ({ request_id: "request", stage: "tool", blocks: {
  request: { kind: "text", role: "report", text: "פותח את האתר" },
  "request:0": { kind: "tool", call_id: "request:0", name, name_complete, arguments_text: "partial" },
} });
beforeEach(() => sessionStorage.clear());
afterEach(cleanup);

describe("agent process continuity", () => {
  test("waits for a complete raw name before rendering a preparation or its ring", () => {
    const view = render(<RichMessage message={message} active stream={stream("")} />);
    expect(view.container.querySelector(".agent-tool-group")).toBeNull();
    view.rerender(<RichMessage message={message} active stream={stream("browser_auto", false)} />);
    expect(view.container.querySelector(".agent-tool-group")).toBeNull();
    view.rerender(<RichMessage message={message} active stream={stream()} />);
    expect(view.container.querySelector(".agent-tool-row>summary")?.textContent).toBe("מכין כלי browser_automation_manager");
    expect(view.container.querySelector(".tool-preparation-ring")).not.toBeNull();
    expect(view.container.querySelector(".agent-tool-row>summary")?.lastElementChild?.getAttribute("data-icon")).toBe("browser");
  });

  test("keeps the same expanded DOM through preparation, reports, execution, result, next tool and saved history", () => {
    const view = render(<RichMessage message={message} active stream={stream()} />);
    const group = view.container.querySelector<HTMLDetailsElement>(".agent-tool-group")!;
    fireEvent.click(group.querySelector("summary")!);
    const tool = group.querySelector<HTMLDetailsElement>(".agent-tool-row")!;
    fireEvent.click(tool.querySelector("summary")!);
    const report: AgentEvent = { type: "report", report_id: "request", text: "פותח את האתר" };
    const events = [step(1, { type: "thinking" }), step(2, report), step(3, start)];
    const props = { message, active: true, stream: stream() };
    view.rerender(<RichMessage {...props} events={events} />);
    expect(view.container.querySelector(".agent-tool-group")).toBe(group);
    expect(group.open).toBe(true); expect(tool.open).toBe(true);
    view.rerender(<RichMessage {...props} events={[...events, step(4, finish)]} />);
    expect(group.open).toBe(true); expect(tool.open).toBe(true);
    expect(tool.textContent).toContain("SUCCESS");
    const next: AgentEvent = { type: "tool_start", tools: [call("next:0")] };
    const saved = [report, start, finish, { type: "report", text: "ממשיך" }, next] as AgentEvent[];
    view.rerender(<RichMessage {...props} events={saved.map((value, i) => step(i + 2, value))} />);
    expect(view.container.querySelector(".agent-tool-group")).toBe(group);
    view.rerender(<RichMessage message={{ ...message, content: "הושלם", metadata: { ...message.metadata, agent_process: { events: [report, start, finish] } } }} stream={stream()} runStatus="completed" />);
    expect(view.container.querySelector(".agent-tool-group")).toBe(group);
    expect(group.open).toBe(true); expect(tool.open).toBe(true);
    view.unmount();
    const restored = render(<RichMessage message={{ ...message, metadata: { ...message.metadata, agent_process: { events: [report, start, finish] } } }} runStatus="completed" />);
    expect(restored.container.querySelector<HTMLDetailsElement>(".agent-tool-group")?.open).toBe(true);
  });

  test("never overwrites a later report with an earlier report sharing its prefix", () => {
    const events: AgentEvent[] = [{ type: "report", report_id: "first", text: "אני פותח את האתר ומנווט לנושא האחרון" }, start, finish,
      { type: "report", report_id: "last", text: "אני פותח את האתר" }];
    const state: StreamState = { stage: "text", blocks: {
      first: { kind: "text", role: "report", text: events[0].text },
      retry: { kind: "text", role: "report", text: "ניסיון קודם" },
      last: { kind: "text", role: "report", text: events[3].text },
    } };
    const merged = mergeProcessEvents(events, state);
    expect(merged.filter(event => event.type === "report").map(event => event.text)).toEqual([events[0].text, "ניסיון קודם", events[3].text]);
    expect(merged.indexOf(finish)).toBeLessThan(merged.findIndex(event => event.report_id === "retry"));
    const legacy = events.map(({ report_id: _id, ...event }) => event);
    expect(mergeProcessEvents(legacy, state).filter(event => event.type === "report").map(event => event.text)).toEqual([events[0].text, "ניסיון קודם", events[3].text]);
  });

  test("retry removes only unexecuted preparation and announces a stable status without countdown spam", () => {
    const retry = (id: number, text: string): RunEvent => ({ ...step(id, start), event_type: "run_stream", payload: { value: { events: [{ kind: "retry_wait", request_id: "request", text }] } } });
    const state = reduceStream(stream(), retry(5, "ממתין 33 שניות לניסיון נוסף"));
    const view = render(<RichMessage message={message} active runStatus="running" stream={state} events={[step(1, { ...start, tools: [call("old")] }), step(2, { ...finish, results: [{ ...call("old"), status: "ok" }] })]} />);
    expect(view.container.querySelectorAll(".agent-tool-row")).toHaveLength(1);
    expect(view.container.querySelector(".tool-preparation-ring")).toBeNull();
    expect(view.container.textContent).toContain("ממתין 33 שניות");
    const announcement = view.container.querySelector('[role="status"]')!;
    const before = announcement.textContent;
    view.rerender(<RichMessage message={message} active stream={reduceStream(state, retry(6, "ממתין 32 שניות לניסיון נוסף"))} />);
    expect(announcement.textContent).toBe(before);
  });

  test("keeps identity and parameters for out-of-order parallel results and a result with no repeated name", () => {
    const rows = processRows([{ type: "tool_start", tools: [call("a"), call("b")] },
      { type: "tool_finish", results: [{ ...call("b"), output: false, status: "ok" }] },
      { type: "tool_finish", results: [{ event_id: "a", output: 0, status: "error" }] }]);
    const row = rows[0]; if (row.kind !== "tools") throw Error("missing tools");
    expect(row.tools.map(tool => [tool.key, tool.name, tool.status, tool.output])).toEqual([
      ["a", "browser_automation_manager", "error", "0"], ["b", "browser_automation_manager", "finished", "false"],
    ]);
    expect(row.label).toContain("שגיאות: 1"); expect(row.running).toBe(false);
    expect(row.tools[0].query).toBe('{"action":"open"}');
    const waiting = processRows([{ type: "tool_waiting", tools: [{ action: "browser_automation_manager" }] },
      { type: "tool_finish", results: [{ action: "browser_automation_manager", status: "denied" }] }]);
    expect(waiting[0].kind === "tools" && waiting[0].tools).toHaveLength(1);
    expect(waiting[0].kind === "tools" && waiting[0].running).toBe(false);
  });
});
