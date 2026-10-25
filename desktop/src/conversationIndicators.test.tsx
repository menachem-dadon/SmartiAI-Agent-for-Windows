// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { AttentionItem } from "./chatTypes";
import { attentionSummary, ConversationIndicator, conversationIndicator } from "./conversationIndicators";
import { visibleAttentionIds } from "./visibleConversationAttention";
import { ConversationToast } from "./ConversationToast";
import { ChatSidebar } from "./ChatSidebar";

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const completed: AttentionItem = { id: "done", session_id: "s", run_id: "r", kind: "response", run_status: "completed", title: "שיחה לדוגמה" };

test("counts successful runs once and keeps pending actions separate from viewing", () => {
  const failed = { ...completed, id: "failed", run_id: "failed-run", run_status: "failed" };
  const pending = { ...completed, id: "permission", kind: "approval", action_required: true, read_at: "seen" };
  expect(attentionSummary([completed, { ...completed, id: "duplicate" }, failed, pending,
    { ...completed, id: "cancelled", run_id: "cancelled-run", run_status: "cancelled" }])).toEqual({ count: 1, actionRequired: true, state: "waiting_for_input" });
  expect(attentionSummary([completed])).toEqual({ count: 1, actionRequired: false, state: "unread" });
  expect(attentionSummary([{ ...completed, run_status: undefined }]).count).toBe(0);
});

test("uses distinct activity shapes and leaves the ring spinning through cancellation", () => {
  const states = ["running", "cancelling", "queued", "waiting_for_approval", "waiting_for_input"];
  expect(states.map(runtime_status => conversationIndicator({ id: "s", title: "", runtime_status }, [])))
    .toEqual(["running", "running", "queued", "waiting_for_approval", "waiting_for_input"]);
  const { container } = render(<>{["running", "queued", "waiting_for_approval", "waiting_for_input", "problem", "unread"].map(state =>
    <ConversationIndicator key={state} state={state as Parameters<typeof ConversationIndicator>[0]["state"]} />)}</>);
  expect(container.querySelector(".running [data-icon=loader]")).not.toBeNull();
  expect(container.querySelector(".queued [data-icon=clock]")).not.toBeNull();
  expect(container.querySelector(".waiting_for_approval [data-icon=questionCircle]")).not.toBeNull();
  expect(container.querySelector(".problem [data-icon=exclamationCircle]")).not.toBeNull();
  expect(container.querySelector(".unread")?.children.length).toBe(0);
});

test("only acknowledges the visible final result and only from the captured page", () => {
  const viewport = document.createElement("div");
  viewport.innerHTML = '<article class="chat-message-row--assistant" data-run-id="r" data-result-ready="true"></article>';
  viewport.getBoundingClientRect = () => ({ top: 100, bottom: 500, width: 600, height: 400 } as DOMRect);
  const reply = viewport.firstElementChild as HTMLElement;
  reply.getBoundingClientRect = () => ({ top: 300, bottom: 700, height: 400 } as DOMRect);
  expect(visibleAttentionIds(viewport, [completed], ["done"])).toEqual([]);
  reply.setAttribute("data-result-ready", "false");
  reply.getBoundingClientRect = () => ({ top: 120, bottom: 220, height: 100 } as DOMRect);
  expect(visibleAttentionIds(viewport, [completed], ["done"])).toEqual([]);
  reply.setAttribute("data-result-ready", "true");
  reply.getBoundingClientRect = () => ({ top: -100, bottom: 450, height: 550 } as DOMRect);
  expect(visibleAttentionIds(viewport, [completed], ["done"])).toEqual(["done"]);
  expect(visibleAttentionIds(viewport, [completed, { ...completed, id: "late" }], ["done"])).toEqual(["done"]);
  reply.getBoundingClientRect = () => ({ top: -400, bottom: 80, height: 480 } as DOMRect);
  expect(visibleAttentionIds(viewport, [completed], ["done"])).toEqual([]);
});

test("shows one summary mark only on the existing collapsed controls", () => {
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  const props = { open: true, logo: "/logo.png", conversations: [], activeId: "", loading: false, error: "", attentionItems: [completed],
    onToggle: vi.fn(), onCreate: vi.fn(), onSearch: vi.fn(), onSelect: vi.fn(), actions: () => [], onManagement: vi.fn() };
  const { container, rerender } = render(<ChatSidebar {...props} />);
  const recent = screen.getByRole("button", { name: "שיחות אחרונות" });
  expect(recent.querySelector(".conversation-activity")).toBeNull();
  fireEvent.click(recent);
  expect(recent.querySelectorAll(".conversation-activity.unread")).toHaveLength(1);
  const pending = { ...completed, kind: "approval", action_required: true };
  rerender(<ChatSidebar {...props} attentionItems={[completed, pending]} />);
  expect(recent.querySelector(".unread")).toBeNull();
  expect(recent.querySelector("[data-icon=questionCircle]")).not.toBeNull();
  rerender(<ChatSidebar {...props} open={false} attentionItems={[completed, pending]} />);
  expect(container.querySelectorAll(".drawer-attention .conversation-activity")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "פתיחת תפריט הצד" }));
  expect(props.onToggle).toHaveBeenCalledOnce();
  expect(props.onSelect).not.toHaveBeenCalled();
});

test("compact notification has only an icon action and expires after five seconds", () => {
  vi.useFakeTimers();
  const onDismiss = vi.fn(), onOpen = vi.fn();
  render(<ConversationToast item={completed} suppressed={false} onDismiss={onDismiss} onOpen={onOpen} />);
  const button = screen.getByRole("button", { name: "פתיחת השיחה" });
  expect(button.textContent).toBe("");
  fireEvent.click(button);
  expect(onOpen).toHaveBeenCalledWith(completed);
  act(() => vi.advanceTimersByTime(4999));
  expect(onDismiss).not.toHaveBeenCalled();
  act(() => vi.advanceTimersByTime(1));
  expect(onDismiss).toHaveBeenCalledOnce();
});
