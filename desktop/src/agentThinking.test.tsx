// @vitest-environment jsdom
import type { ComponentProps } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { RichMessage } from "./RichMessage";
import type { RunEvent } from "./chatTypes";

const message = { role: "assistant" as const, content: "", metadata: { run_id: "r" } };
function run(events: RunEvent[] = [], props: Partial<ComponentProps<typeof RichMessage>> = {}) {
  return <RichMessage message={message} active runStatus="running" events={events} {...props} />;
}
function event(sequence: number, event_type: string, payload: Record<string, unknown>): RunEvent {
  return { sequence, event_id: sequence, event_type, payload, run_id: "r", session_id: "s", created_at: "" };
}
function step(sequence: number, value: Record<string, unknown>) {
  return event(sequence, "run_step", { value });
}
function advance(ms: number) {
  act(() => { vi.advanceTimersByTime(ms); });
}
const thinking = () => screen.queryByText("חושב...");

beforeEach(() => { sessionStorage.clear(); vi.useFakeTimers(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("agent thinking indicator", () => {
  test("uses thinking while waiting for cloud tokens and preserves real local prefill", () => {
    const view = render(run([], { stream: { stage: "waiting", blocks: {} } }));
    advance(300);
    expect(thinking()?.classList.contains("is-shimmering")).toBe(true);
    expect(screen.queryByText("ממתין לתשובה…")).toBeNull();
    view.rerender(run([], { stream: { stage: "prefill", percent: 37, blocks: {} } }));
    expect(screen.getByText("מעבד הנחיה: 37%")).toBeTruthy();
    expect(thinking()).toBeNull();
    view.rerender(run([], { stream: { stage: "thinking", blocks: {} } }));
    expect(thinking()).not.toBeNull();
    expect(view.container.querySelectorAll(".is-shimmering")).toHaveLength(1);
  });

  test("waits 300ms after sending, without restarting for status or thinking events", () => {
    const events: RunEvent[] = [];
    const view = render(run(events));
    expect(thinking()).toBeNull();
    advance(100);
    events.push(step(1, { type: "thinking" }));
    view.rerender(run([...events]));
    advance(100);
    events.push(event(2, "run_status", { value: "חושב..." }));
    view.rerender(run([...events]));
    advance(99);
    expect(thinking()).toBeNull();
    advance(1);
    expect(thinking()).not.toBeNull();
    expect(thinking()?.classList.contains("is-shimmering")).toBe(true);
    view.rerender(run([...events]));
    expect(thinking()).not.toBeNull();
  });

  test("restarts the pause for each report and places thinking below the process", () => {
    const view = render(run());
    advance(300);
    expect(thinking()).not.toBeNull();
    const events = [step(1, { type: "report", text: "בודק את הנתונים" })];
    view.rerender(run(events));
    expect(thinking()).toBeNull();
    advance(299);
    expect(thinking()).toBeNull();
    advance(1);
    const process = view.container.querySelector(".agent-process")!;
    expect(process.contains(thinking())).toBe(false);
    expect(process.compareDocumentPosition(thinking()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    events.push(step(2, { type: "report", text: "מצאתי את הנתונים" }));
    view.rerender(run([...events]));
    expect(thinking()).toBeNull();
    advance(300);
    expect(thinking()).not.toBeNull();
  });

  test("returns between sequential tool turns even without a new report", () => {
    const events = [step(1, { type: "tool_start", tools: [{ action: "search", event_id: "one" }] })];
    const view = render(run(events));
    advance(2000);
    expect(thinking()).toBeNull();
    events.push(
      step(2, { type: "tool_finish", results: [{ action: "search", event_id: "one" }] }),
      step(3, { type: "thinking" }),
    );
    view.rerender(run([...events]));
    advance(299);
    expect(thinking()).toBeNull();
    advance(1);
    expect(thinking()).not.toBeNull();

    events.push(step(4, { type: "tool_start", tools: [{ action: "read", event_id: "two" }] }));
    view.rerender(run([...events]));
    expect(thinking()).toBeNull();
    advance(1500);
    expect(thinking()).toBeNull();
    events.push(step(5, { type: "tool_finish", results: [{ action: "read", event_id: "two" }] }));
    view.rerender(run([...events]));
    advance(299);
    expect(thinking()).toBeNull();
    advance(1);
    expect(thinking()).not.toBeNull();
  });

  test("waits for every parallel call, including identical tools finishing out of order across reports", () => {
    const events = [step(1, { type: "tool_start", parallel: true, tools: [
      { action: "search", event_id: "one", arguments_text: "first query" },
      { action: "search", event_id: "two", arguments_text: "second query" },
    ] })];
    const view = render(run(events));
    events.push(
      step(2, { type: "thinking" }),
      step(3, { type: "tool_finish", results: [{ action: "search", event_id: "one", output_text: "first result" }] }),
      step(4, { type: "report", text: "ממתין לחיפוש הנוסף" }),
    );
    view.rerender(run([...events]));
    advance(2000);
    expect(thinking()).toBeNull();
    const tools = view.container.querySelectorAll(".agent-tool-row");
    expect(tools).toHaveLength(2);
    expect(tools[0].textContent).toContain("הסתיים");
    expect(tools[0].textContent).toContain("first query");
    expect(tools[0].textContent).toContain("first result");
    expect(tools[1].textContent).toContain("מריץ כלי");
    events.push(step(5, { type: "tool_finish", results: [{ action: "search", event_id: "two", status: "error" }] }));
    view.rerender(run([...events]));
    advance(299);
    expect(thinking()).toBeNull();
    advance(1);
    expect(thinking()).not.toBeNull();
    expect(view.container.querySelectorAll(".agent-tool-row")).toHaveLength(2);
    expect(screen.getByText("שגיאה search")).toBeTruthy();
  });

  test("also waits for individually delivered tool events without call IDs", () => {
    const events = [
      event(1, "tool_started", { tool: "search" }),
      event(2, "tool_started", { tool: "read" }),
      event(3, "tool_finished", { tool: "read" }),
    ];
    const view = render(run(events));
    advance(1500);
    expect(thinking()).toBeNull();
    events.push(event(4, "tool_finished", { tool: "search" }));
    view.rerender(run([...events]));
    advance(300);
    expect(thinking()).not.toBeNull();
  });

  test("does not count replayed tool starts twice or restart thinking on replay", () => {
    const started = step(1, { type: "tool_start", tools: [{ action: "search", event_id: "one" }] });
    const finished = step(2, { type: "tool_finish", results: [{ action: "search", event_id: "one" }] });
    const events = [started, { ...started }, finished];
    const view = render(run(events));
    advance(300);
    expect(thinking()).not.toBeNull();
    expect(view.container.querySelectorAll(".agent-tool-row")).toHaveLength(1);
    view.rerender(run([...events, { ...started }, { ...finished }]));
    expect(thinking()).not.toBeNull();
  });

  test("transfers exactly one shimmer from group to the first active visible tool", () => {
    const events = [step(1, { type: "tool_start", tools: [
      { action: "search", event_id: "one" },
      { action: "read", event_id: "two" },
    ] })];
    const view = render(run(events));
    const group = view.container.querySelector<HTMLDetailsElement>(".agent-tool-group")!;
    const groupText = () => group.querySelector("summary .agent-status-text")!;
    expect(groupText().classList.contains("is-shimmering")).toBe(true);
    fireEvent.click(group.querySelector("summary")!);
    expect(group.open).toBe(true);
    expect(groupText().classList.contains("is-shimmering")).toBe(false);
    expect(screen.getByText("מריץ כלי search").classList.contains("is-shimmering")).toBe(true);
    expect(screen.getByText("מריץ כלי read").classList.contains("is-shimmering")).toBe(false);

    events.push(step(2, { type: "tool_finish", results: [{ action: "search", event_id: "one" }] }));
    view.rerender(run([...events]));
    expect(group.open).toBe(true);
    expect(groupText().classList.contains("is-shimmering")).toBe(false);
    expect(screen.getByText("הסתיים search").classList.contains("is-shimmering")).toBe(false);
    expect(screen.getAllByText("מריץ כלי read").filter(node => node.classList.contains("is-shimmering"))).toHaveLength(1);

    events.push(step(3, { type: "tool_finish", results: [{ action: "read", event_id: "two" }] }));
    view.rerender(run([...events]));
    expect(groupText().classList.contains("is-shimmering")).toBe(false);
    expect(group.querySelector(".is-shimmering")).toBeNull();
    advance(300);
    expect(thinking()?.classList.contains("is-shimmering")).toBe(true);
    view.rerender(run(events, { active: false }));
    expect(view.container.querySelector(".is-shimmering")).toBeNull();
  });

  test("hides during standalone activity and delays its return after completion", () => {
    const events = [step(1, { type: "tool_group_start", group: { id: "compact", label: "מארגן את ההקשר" } })];
    const view = render(run(events));
    advance(1500);
    expect(thinking()).toBeNull();
    events.push(step(2, { type: "tool_group_finish", group: { id: "compact", label: "ההקשר מוכן" } }));
    view.rerender(run([...events]));
    advance(299);
    expect(thinking()).toBeNull();
    advance(1);
    expect(thinking()).not.toBeNull();
  });

  test("cancels pending timers when a tool starts or a final answer arrives", () => {
    const view = render(run());
    advance(200);
    const events = [step(1, { type: "tool_start", tools: [{ action: "search" }] })];
    view.rerender(run(events));
    advance(500);
    expect(thinking()).toBeNull();
    events.push(step(2, { type: "tool_finish", results: [{ action: "search" }] }));
    view.rerender(run([...events]));
    advance(200);
    view.rerender(run(events, { message: { ...message, content: "הושלם" } }));
    advance(500);
    expect(thinking()).toBeNull();
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  test.each(["waiting_for_approval", "waiting_for_input", "cancelling", "cancelled", "failed", "completed"])(
    "hides thinking immediately while %s", (runStatus) => {
      const view = render(run());
      advance(300);
      expect(thinking()).not.toBeNull();
      view.rerender(run([], { runStatus }));
      expect(thinking()).toBeNull();
      advance(1500);
      expect(thinking()).toBeNull();
    },
  );

  test("never shows thinking in inactive history and cleans up its delay on unmount", () => {
    const view = render(run([], { active: false }));
    advance(1500);
    expect(thinking()).toBeNull();
    view.rerender(run());
    advance(200);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
