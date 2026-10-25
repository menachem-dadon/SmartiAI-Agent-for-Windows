// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { coreApi } from "./coreApi";
import { invoke } from "@tauri-apps/api/core";
import { useConversationAttention } from "./conversationAttention";
import { rememberActiveConversation } from "./chatDrafts";
import type { AttentionItem, Approval, ChatMessage, Conversation, RunRecord } from "./chatTypes";

const native = vi.hoisted(() => ({
  handlers: new Map<string, (event: { payload: any }) => void>(),
  window: {
    isMaximized: async () => false,
    onResized: async () => () => {},
    onFocusChanged: async (handler: (event: { payload: boolean }) => void) => {
      native.handlers.set("focus", handler);
      return () => native.handlers.delete("focus");
    },
  },
}));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => native.window }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async (name: string, handler: any) => {
  native.handlers.set(name, handler);
  return () => native.handlers.delete(name);
} }));
vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
vi.mock("./Composer", () => ({ Composer: () => null }));
vi.mock("./WorkbenchPanels", () => ({ WorkbenchSurface: () => null }));
vi.mock("./workspaceMotion", async importOriginal => ({ ...await importOriginal<typeof import("./workspaceMotion")>(), useChatLayoutMotion: () => ({ current: null }) }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

let focused: boolean;
let hidden: boolean;
let attention: AttentionItem[];
let conversations: Conversation[];
let messages: Record<string, ChatMessage[]>;
let olderMessages: Record<string, ChatMessage[]>;
let approvals: Approval[];
let runs: RunRecord[];
let readGate: ReturnType<typeof deferred<void>> | null;
let messageGate: { session: string; gate: ReturnType<typeof deferred<void>> } | null;
const readCalls: Array<{ session: string; ids: string[] }> = [];

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  focused = true; hidden = false; readGate = null; messageGate = null;
  attention = ["b", "c"].map((session) => ({ id: `unread-${session}`, session_id: session, title: `chat-${session}`, kind: "response", run_id: `run-${session}`, run_status: "completed" }));
  conversations = ["a", "b", "c"].map((id) => ({ id, title: `chat-${id}`, message_count: 3 }));
  messages = Object.fromEntries(["a", "b", "c"].map((id) => [id, [
    { role: "assistant", content: `old-${id}` },
    { role: "user", content: `question-${id}` },
    { role: "assistant", content: `answer-${id}`, metadata: { run_id: `run-${id}` } },
  ]]));
  approvals = []; runs = []; olderMessages = {}; readCalls.length = 0;
  localStorage.clear(); sessionStorage.clear(); native.handlers.clear();
  vi.spyOn(document, "hasFocus").mockImplementation(() => focused);
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal("innerWidth", 1800);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const viewport = this.closest<HTMLElement>(".chat-stage");
    const top = this.classList.contains("message-content")
      ? (this.textContent?.startsWith("old-") ? 400 : 1300) - (viewport?.scrollTop || 0)
      : this.classList.contains("chat-message-row--assistant") ? 1500 - (viewport?.scrollTop || 0) : 100;
    return { top, bottom: top + 100, left: 0, right: 600, width: 600, height: 100, x: 0, y: top, toJSON() {} };
  });
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === "core_status") return { state: "ready", generation: 1, stderrTail: [] } as any;
    if (command === "core_health") return { ready: true } as any;
    return null;
  });
  vi.mocked(coreApi).mockImplementation(async (_method, path, body) => {
    const settings = { values: { updates_auto_check: false } };
    if (path === "/v2/management/legal") return { accepted: true } as any;
    if (path === "/v2/bootstrap") return {
      conversations, settings, pending_approvals: approvals,
      chat_models: { providers: [], provider: "local", model: "test" },
    } as any;
    if (path === "/v2/settings") return settings as any;
    if (path.startsWith("/v2/events/live")) return { items: [] } as any;
    if (path === "/v2/runs?limit=100") return { items: structuredClone(runs) } as any;
    if (path === "/v2/approvals") return { items: structuredClone(approvals) } as any;
    if (path.startsWith("/v2/runs/")) return { items: [] } as any;
    if (path.startsWith("/v2/conversations?")) {
      const query = new URLSearchParams(path.split("?")[1]).get("q");
      return { items: conversations.filter((item) => !query || item.title.includes(query)), attention_items: structuredClone(attention) } as any;
    }
    const session = path.split("/")[3];
    if (path.includes("/messages?")) {
      const before = path.includes("&before=");
      const snapshot = {
        session_id: session, messages: structuredClone(before ? olderMessages[session] : messages[session]),
        unread_attention_ids: attention.filter((item) => item.session_id === session).map((item) => item.id),
        total_count: 3, has_older: !before && Boolean(olderMessages[session]), older_count: 1, next_before_ordinal: before ? 0 : 48,
      };
      if (messageGate?.session === session) await messageGate.gate.promise;
      return snapshot as any;
    }
    if (path.endsWith("/read")) {
      const ids = (body as { attention_ids: string[] }).attention_ids;
      readCalls.push({ session, ids });
      if (readGate) await readGate.promise;
      attention = attention.filter((item) => item.session_id !== session || !ids.includes(item.id));
      return { marked_read: ids.length } as any;
    }
    throw new Error(`Unexpected request: ${path}`);
  });
});

afterEach(() => {
  cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.clearAllMocks(); vi.unstubAllGlobals();
});

const row = (session: string) => screen.getByText(`chat-${session}`, { selector: ".conversation-select span" }).closest(".conversation-row")!;
const open = (session: string) => fireEvent.click(row(session).querySelector("button")!);
const badge = () => vi.mocked(invoke).mock.calls.filter(([name]) => name === "desktop_set_unread").slice(-1)[0]?.[1];
async function revealResult() {
  const viewport = document.querySelector<HTMLElement>(".chat-stage")!;
  await act(async () => { await new Promise(resolve => requestAnimationFrame(resolve)); });
  viewport.scrollTop = 1450;
  fireEvent.scroll(viewport);
  await act(async () => { await new Promise(resolve => requestAnimationFrame(resolve)); });
}
async function start() {
  // Read/notification scenarios begin with an explicitly selected conversation.
  rememberActiveConversation("a");
  render(<App />);
  await screen.findByText("answer-a");
  await waitFor(() => expect(badge()).toEqual({ count: attention.filter(item => item.run_status === "completed").length, actionRequired: attention.some(item => item.action_required) }));
}

test("new conversation remains an unsent draft until the first message", async () => {
  await start();
  const request = vi.mocked(coreApi).getMockImplementation()!;
  vi.mocked(coreApi).mockImplementation(async (method, path, body, mutation) => {
    if (method === "POST" && path === "/v2/conversations") {
      const conversation = { id: "new", title: "שיחה חדשה", message_count: 0 };
      conversations.unshift(conversation);
      messages.new = [];
      return { conversation } as any;
    }
    return request(method, path, body, mutation);
  });
  fireEvent.click(screen.getByRole("button", { name: "שיחה חדשה" }));
  await screen.findByRole("heading", { name: "שיחה חדשה" });
  expect(vi.mocked(coreApi).mock.calls.some(([method, path]) => method === "POST" && path === "/v2/conversations")).toBe(false);
});

test("an unseen result remains unread while reading older content", async () => {
  await start();
  open("b");
  await screen.findByText("answer-b");
  await act(async () => { await new Promise(resolve => requestAnimationFrame(resolve)); });
  expect(readCalls.some(call => call.session === "b")).toBe(false);
  expect(row("b").querySelector(".conversation-activity.unread")).not.toBeNull();
  await revealResult();
  await waitFor(() => expect(readCalls).toContainEqual({ session: "b", ids: ["unread-b"] }));
});

test("a new result in another foreground chat offers the compact icon navigation", async () => {
  await start();
  attention.push({ id: "new-c", session_id: "c", run_id: "run-c", kind: "response", run_status: "completed", title: "chat-c" });
  await screen.findByRole("button", { name: "פתיחת השיחה" }, { timeout: 4000 });
  expect(document.querySelector(".conversation-toast")).not.toBeNull();
  expect(vi.mocked(invoke).mock.calls.some(([name]) => name === "desktop_notify")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "פתיחת השיחה" }));
  await screen.findByText("answer-c");
  expect(document.querySelector(".conversation-toast")).toBeNull();
});

test("viewing a pending request preserves its action marker until it is resolved", async () => {
  const { result } = renderHook(() => useConversationAttention(vi.fn()));
  const pending = { id: "pending", session_id: "b", run_id: "run-b", title: "request", kind: "approval", action_required: true };
  act(() => result.current.replace([pending]));
  await act(async () => result.current.acknowledge("b", [pending.id]));
  expect(result.current.items).toEqual([pending]);
  act(() => result.current.replace([]));
  expect(result.current.items).toEqual([]);
});

describe("conversation read state and reply navigation", () => {
  test("clears the dot and decrements only its taskbar count before the receipt finishes", async () => {
    await start();
    readGate = deferred<void>();
    open("b");
    await screen.findByText("answer-b");
    await revealResult();
    await waitFor(() => expect(badge()).toEqual({ count: 1, actionRequired: false }));
    expect(row("b").querySelector(".conversation-activity.unread")).toBeNull();
    expect(row("c").querySelector(".conversation-activity.unread")).not.toBeNull();
    expect(readCalls).toEqual([{ session: "b", ids: ["unread-b"] }]);
    await act(async () => readGate!.resolve());
  });

  test("keeps the global count while search results exclude unread conversations", async () => {
    await start();
    fireEvent.click(screen.getByRole("button", { name: "חיפוש בשיחות ובקבצים" }));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "chat-a" } });
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    expect(screen.getByRole("option").textContent).toContain("chat-a");
    expect(badge()).toEqual({ count: 2, actionRequired: false });
  });

  test("does not read a background window and acknowledges it on return to the foreground", async () => {
    focused = false;
    attention.push({ id: "unread-a", session_id: "a", kind: "response", title: "chat-a", run_id: "run-a", run_status: "completed" });
    await start();
    expect(readCalls).toEqual([]);
    expect(row("a").querySelector(".conversation-activity.unread")).not.toBeNull();
    focused = true;
    fireEvent.focus(window);
    await revealResult();
    await waitFor(() => expect(readCalls).toContainEqual({ session: "a", ids: ["unread-a"] }));
    expect(badge()).toEqual({ count: 2, actionRequired: false });
  });

  test("ordinary selection preserves reading while notifications explicitly align the reply", async () => {
    await start();
    open("b");
    await screen.findByText("answer-b");
    const viewport = document.querySelector<HTMLElement>(".chat-stage")!;
    await waitFor(() => expect(viewport.scrollTop).toBe(0));
    // Let the one-frame layout correction settle, then scroll manually.
    await act(async () => { await new Promise((resolve) => requestAnimationFrame(resolve)); });
    viewport.scrollTop = 250;
    fireEvent.scroll(viewport);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1300)); });
    expect(viewport.scrollTop).toBe(250);
    await act(async () => native.handlers.get("desktop://activation")!({ payload: { command: "notification", sessionId: "b" } }));
    expect(viewport.scrollTop).toBe(1184);
    viewport.scrollTop = 0;
    fireEvent.scroll(viewport);
    await act(async () => open("b"));
    expect(viewport.scrollTop).toBe(0);
  });

  test("quiet polls discover a completion in the already-open conversation and synchronize its receipt", async () => {
    await start();
    attention.push({ id: "late-a", session_id: "a", kind: "response", title: "chat-a", run_id: "run-a", run_status: "completed" });
    messages.a.push({ role: "assistant", content: "new-answer-a" });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1250)); });
    expect(screen.getByText("new-answer-a")).toBeDefined();
    await revealResult();
    await waitFor(() => expect(readCalls).toContainEqual({ session: "a", ids: ["late-a"] }));
    expect(readCalls).toContainEqual({ session: "a", ids: ["late-a"] });
    expect(row("a").querySelector(".conversation-activity.unread")).toBeNull();
    expect(badge()).toEqual({ count: 2, actionRequired: false });
  });

  test("an older notification loads and positions its own reply beyond the latest page", async () => {
    messages.b = messages.b.slice(1);
    olderMessages.b = [{ role: "assistant", content: "old-b", metadata: { run_id: "older-run" } }];
    await start();
    await act(async () => native.handlers.get("desktop://activation")!({ payload: {
      command: "notification", sessionId: "b", runId: "older-run",
    } }));
    await screen.findByText("old-b");
    expect(screen.getByText("answer-b")).toBeDefined();
    await waitFor(() => expect(document.querySelector<HTMLElement>(".chat-stage")!.scrollTop).toBe(284));
  });

  test("ignores messages and receipts from a slower conversation after a rapid switch", async () => {
    await start();
    const gate = deferred<void>();
    messageGate = { session: "b", gate };
    open("b");
    await waitFor(() => expect(vi.mocked(coreApi).mock.calls.some(([, path]) => path.includes("/b/messages"))).toBe(true));
    open("c");
    await screen.findByText("answer-c");
    await act(async () => gate.resolve());
    expect(screen.queryByText("answer-b")).toBeNull();
    expect(readCalls.some((call) => call.session === "b")).toBe(false);
    expect(row("b").querySelector(".conversation-activity.unread")).not.toBeNull();
  });

  test("notification activation shows the pending approval and the start of its active response", async () => {
    runs = [{ id: "run-b", session_id: "b", status: "waiting_for_approval", user_text: "question" }];
    approvals = [{ id: "approval-b", run_id: "run-b", session_id: "b", title: "Approve file", prompt: "Allow this action", risk_level: "low", created_at: "" }];
    conversations[1].needs_input = true;
    attention[0].kind = "approval"; attention[0].action_required = true; attention[0].run_status = "waiting_for_approval";
    await start();
    await act(async () => native.handlers.get("desktop://activation")!({ payload: { command: "notification", sessionId: "b" } }));
    const panel = await screen.findByRole("region", { name: "בקשות הרשאה" });
    expect(within(panel).getByText("Approve file")).toBeDefined();
    expect(document.querySelector(".chat-input-panel")!.contains(panel)).toBe(true);
    expect(panel.querySelector('[aria-modal="true"]')).toBeNull();
    await waitFor(() => expect(document.querySelector<HTMLElement>(".chat-stage")!.scrollTop).toBe(1184));
    expect(readCalls).toContainEqual({ session: "b", ids: ["unread-b"] });
    // Reading the request never resolves the underlying permission.
    expect(row("b").querySelector(".conversation-activity.waiting_for_approval")).not.toBeNull();
    expect(vi.mocked(coreApi).mock.calls.some(([, path]) => path.endsWith("/resolve"))).toBe(false);
  });
});

test("multiple permissions survive switching conversations and answering out of order", async () => {
  approvals = [
    { id: "a-first", run_id: "run-a", session_id: "a", title: "First action", prompt: "First details", risk_level: "low", created_at: "" },
    { id: "a-second", run_id: "run-a", session_id: "a", title: "Second action", prompt: "Second details", risk_level: "high", created_at: "" },
    { id: "b-first", run_id: "run-b", session_id: "b", title: "Other conversation", prompt: "Other details", risk_level: "low", created_at: "" },
  ];
  const request = vi.mocked(coreApi).getMockImplementation()!;
  const gate = deferred<void>();
  vi.mocked(coreApi).mockImplementation(async (method, path, body, mutation) => {
    if (method === "POST" && path.endsWith("/resolve")) {
      await gate.promise;
      approvals = approvals.filter((item) => !path.includes(`/${item.id}/`));
      return { resolved: true } as any;
    }
    return request(method, path, body, mutation);
  });
  await start();
  expect(screen.getByText("First action")).toBeDefined();
  expect(screen.getByText("Second action")).toBeDefined();
  expect(screen.queryByText("Other conversation")).toBeNull();
  const second = screen.getByText("Second action").closest("details")!;
  fireEvent.click(within(second).getByRole("button", { name: "אשר" }));
  expect(within(second).getByRole<HTMLButtonElement>("button", { name: "דחה" }).disabled).toBe(true);
  open("b");
  await screen.findByText("Other conversation");
  expect(screen.queryByText("First action")).toBeNull();
  await act(async () => gate.resolve());
  expect(screen.getByText("Other conversation")).toBeDefined();
  open("a");
  await screen.findByText("First action");
  expect(screen.queryByText("Second action")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "דחה" }));
  await waitFor(() => expect(screen.queryByRole("region", { name: "בקשות הרשאה" })).toBeNull());
  expect(coreApi).toHaveBeenCalledWith("POST", "/v2/approvals/a-second/resolve", { approved: true }, true);
  expect(coreApi).toHaveBeenCalledWith("POST", "/v2/approvals/a-first/resolve", { approved: false }, true);
  open("b");
  await screen.findByText("Other conversation");
});

test("stale snapshots cannot resurrect a receipt, while failed receipts restore the dot and can be retried", async () => {
  const onError = vi.fn();
  const { result } = renderHook(() => useConversationAttention(onError));
  const first = [...attention];
  act(() => result.current.replace(first));
  readGate = deferred<void>();
  let read!: Promise<void>;
  act(() => { read = result.current.acknowledge("b", ["unread-b"]); });
  act(() => result.current.replace(first));
  expect(result.current.items.map((item) => item.id)).toEqual(["unread-c"]);
  await act(async () => { readGate!.resolve(); await read; });
  act(() => result.current.replace(first));
  expect(result.current.items.map((item) => item.id)).toEqual(["unread-c"]);
  readGate = deferred<void>();
  act(() => { read = result.current.acknowledge("c", ["unread-c"]); });
  await act(async () => { readGate!.reject(new Error("offline")); await read; });
  expect(result.current.items.map((item) => item.id)).toEqual(["unread-c"]);
  expect(onError).toHaveBeenCalledOnce();
  readGate = null;
  await act(async () => result.current.acknowledge("c", ["unread-c"]));
  expect(result.current.items).toEqual([]);
});
