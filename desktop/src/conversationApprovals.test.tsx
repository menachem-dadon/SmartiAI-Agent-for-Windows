// @vitest-environment jsdom
import { act, cleanup, render, renderHook, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useApprovalQueue } from "./conversationApprovals";
import { coreApi } from "./coreApi";
import { RichMessage } from "./RichMessage";
import type { Approval, RunEvent } from "./chatTypes";

vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const approval: Approval = { id: "a", run_id: "r", session_id: "s", title: "Action", prompt: "Details", risk_level: "low", created_at: "" };
const other = { ...approval, id: "b", session_id: "other" };

test("deduplicates requests, prevents duplicate decisions, and ignores stale snapshots after success", async () => {
  const { result } = renderHook(() => useApprovalQueue());
  act(() => result.current.replace([approval, other, approval]));
  expect(result.current.items).toHaveLength(2);
  let finish!: () => void;
  vi.mocked(coreApi).mockImplementation(() => new Promise((resolve) => { finish = () => resolve({ resolved: true }); }));
  let decision!: Promise<void>;
  act(() => { decision = result.current.resolve(approval, true); });
  await act(async () => { await result.current.resolve(approval, false); });
  expect(coreApi).toHaveBeenCalledTimes(1);
  expect(result.current.busy.has(approval.id)).toBe(true);
  await act(async () => { finish(); await decision; });
  act(() => result.current.replace([approval, other]));
  expect(result.current.items).toEqual([other]);
  expect(result.current.busy.size).toBe(0);
});

test("keeps a failed decision attached to its own request and allows retry", async () => {
  const { result } = renderHook(() => useApprovalQueue());
  act(() => result.current.replace([approval, other]));
  vi.mocked(coreApi).mockRejectedValueOnce(new Error("offline"));
  await act(async () => result.current.resolve(approval, false));
  expect(result.current.items).toEqual([approval, other]);
  expect(result.current.errors.a).toContain("offline");
  expect(result.current.errors.b).toBeUndefined();
  expect(result.current.busy.size).toBe(0);
  vi.mocked(coreApi).mockResolvedValueOnce({ resolved: true });
  await act(async () => result.current.resolve(approval, false));
  expect(result.current.items).toEqual([other]);
  expect(result.current.errors.a).toBeUndefined();
});

test("reloading restores pending requests; server cancellation or expiry removes them", () => {
  const first = renderHook(() => useApprovalQueue());
  act(() => first.result.current.replace([approval, other]));
  first.unmount();
  const second = renderHook(() => useApprovalQueue());
  act(() => second.result.current.replace([approval, other]));
  expect(second.result.current.items).toEqual([approval, other]);
  act(() => second.result.current.replace([other]));
  expect(second.result.current.items).toEqual([other]);
});

test("approval lifecycle events never create process reports before or after a decision", () => {
  const events: RunEvent[] = ["approval_requested", "approval_resolved"].map((event_type, index) => ({
    event_id: index + 1, sequence: index + 1, event_type, run_id: "r", session_id: "s", created_at: "",
    payload: { approval_id: "a", approved: true },
  }));
  const message = { role: "assistant" as const, content: "", metadata: { run_id: "r" } };
  const view = render(<RichMessage message={message} events={[events[0]]} active runStatus="waiting_for_approval" />);
  expect(view.container.querySelector(".agent-process")).toBeNull();
  expect(screen.queryByText(/ממתין לאישור/u)).toBeNull();
  view.rerender(<RichMessage message={{ ...message, content: "Done" }} events={events} />);
  expect(view.container.querySelector(".agent-process")).toBeNull();
  expect(screen.queryByText(/ממתין לאישור/u)).toBeNull();
});

test("old saved approval status reports are omitted while real tool history remains", () => {
  const view = render(<RichMessage message={{ role: "assistant", content: "Done", metadata: { agent_process: { events: [
    { type: "tool_start", tools: [{ action: "search", event_id: "tool" }] },
    { type: "report", text: "ממתין לאישור" },
    { type: "report", text: "ממתין לאישור משתמש..." },
    { type: "tool_finish", results: [{ action: "search", event_id: "tool" }] },
  ] } } }} />);
  expect(screen.queryByText(/ממתין לאישור/u)).toBeNull();
  expect(view.container.querySelectorAll(".agent-tool-row")).toHaveLength(1);
  expect(screen.getByText("הסתיים search")).toBeDefined();
});
