// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { coreApi } from "./coreApi";
import { invoke } from "@tauri-apps/api/core";
import { useConversationAttention } from "./conversationAttention";
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
vi.mock("./workspaceMotion", () => ({ useChatLayoutMotion: () => ({ current: null }) }));

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
  focused = true; hidden = false; readGate = null; messageGate = null;
  attention = ["b", "c"].map((session) => ({ id: `unread-${session}`, session_id: session, title: `chat-${session}`, kind: "response" }));
  conversations = ["a", "b", "c"].map((id) => ({ id, title: `chat-${id}`, message_count: 3 }));
  messages = Object.fromEntries(["a", "b", "c"].map((id) => [id, [
    { role: "assistant", content: `old-${id}` },
    { role: "user", content: `question-${id}` },
    { role: "assistant", content: `answer-${id}` },
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
    if (path.startsWith("/v2/events/replay")) return { items: [] } as any;
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

const row = (session: string) => screen.getByText(`chat-${session}`, { selector: "strong" }).closest(".conversation-row")!;
const open = (session: string) => fireEvent.click(row(session).querySelector("button")!);
const badge = () => vi.mocked(invoke).mock.calls.filter(([name]) => name === "desktop_set_unread").slice(-1)[0]?.[1];
async function start() {
  render(<App />);
  await screen.findByText("answer-a");
  await waitFor(() => expect(badge()).toEqual({ count: attention.length }));
}

describe("conversation read state and reply navigation", () => {
  test("clears the dot and decrements only its taskbar count before the receipt finishes", async () => {
    await start();
    readGate = deferred<void>();
    open("b");
    await screen.findByText("answer-b");
    await waitFor(() => expect(badge()).toEqual({ count: 1 }));
    expect(row("b").querySelector(".has-unread")).toBeNull();
    expect(row("c").querySelector(".has-unread")).not.toBeNull();
    expect(readCalls).toEqual([{ session: "b", ids: ["unread-b"] }]);
    await act(async () => readGate!.resolve());
  });

  test("keeps the global count while sidebar search hides unread conversations", async () => {
    await start();
    fireEvent.change(screen.getByRole("textbox", { name: "חיפוש בשיחות" }), { target: { value: "chat-a" } });
    await waitFor(() => expect(screen.queryByText("chat-b", { selector: "strong" })).toBeNull());
    expect(badge()).toEqual({ count: 2 });
  });

  test("does not read a background window and acknowledges it on return to the foreground", async () => {
    focused = false;
    attention.push({ id: "unread-a", session_id: "a", kind: "response", title: "chat-a" });
    await start();
    expect(readCalls).toEqual([]);
    expect(row("a").querySelector(".has-unread")).not.toBeNull();
    focused = true;
    fireEvent.focus(window);
    await waitFor(() => expect(readCalls).toContainEqual({ session: "a", ids: ["unread-a"] }));
    expect(badge()).toEqual({ count: 2 });
  });

  test("aligns to the answer on recent-list and repeated notification activation, without polling scroll jumps", async () => {
    await start();
    open("b");
    await screen.findByText("answer-b");
    const viewport = document.querySelector<HTMLElement>(".chat-stage")!;
    await waitFor(() => expect(viewport.scrollTop).toBe(1184));
    // Let the one-frame layout correction settle, then scroll manually.
    await act(async () => { await new Promise((resolve) => requestAnimationFrame(resolve)); });
    viewport.scrollTop = 250;
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1300)); });
    expect(viewport.scrollTop).toBe(250);
    await act(async () => native.handlers.get("desktop://activation")!({ payload: { command: "notification", sessionId: "b" } }));
    expect(viewport.scrollTop).toBe(1184);
    viewport.scrollTop = 0;
    await act(async () => open("b"));
    expect(viewport.scrollTop).toBe(1184);
  });

  test("quiet polls discover a completion in the already-open conversation and synchronize its receipt", async () => {
    await start();
    attention.push({ id: "late-a", session_id: "a", kind: "response", title: "chat-a" });
    messages.a.push({ role: "assistant", content: "new-answer-a" });
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 1250)); });
    expect(screen.getByText("new-answer-a")).toBeDefined();
    expect(readCalls).toContainEqual({ session: "a", ids: ["late-a"] });
    expect(row("a").querySelector(".has-unread")).toBeNull();
    expect(badge()).toEqual({ count: 2 });
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
    expect(row("b").querySelector(".has-unread")).not.toBeNull();
  });

  test("notification activation shows the pending approval and the start of its active response", async () => {
    runs = [{ id: "run-b", session_id: "b", status: "waiting_for_approval", user_text: "question" }];
    approvals = [{ id: "approval-b", run_id: "run-b", session_id: "b", title: "Approve file", prompt: "Allow this action", risk_level: "low", created_at: "" }];
    conversations[1].needs_input = true;
    attention[0].kind = "approval";
    await start();
    await act(async () => native.handlers.get("desktop://activation")!({ payload: { command: "notification", sessionId: "b" } }));
    await screen.findByRole("dialog", { name: "Approve file" });
    await waitFor(() => expect(document.querySelector<HTMLElement>(".chat-stage")!.scrollTop).toBe(1384));
    expect(readCalls).toContainEqual({ session: "b", ids: ["unread-b"] });
    // Reading the request never resolves the underlying permission.
    expect(row("b").querySelector(".needs-input")).not.toBeNull();
    expect(vi.mocked(coreApi).mock.calls.some(([, path]) => path.endsWith("/resolve"))).toBe(false);
  });
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
