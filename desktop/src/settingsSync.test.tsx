// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import App from "./App";
import { coreApi } from "./coreApi";
import { subscribeSettingsChanges } from "./settingsChanges";
import { RunSubmission } from "./runSubmission";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({
  isMaximized: async () => false,
  onResized: async () => () => {},
  onFocusChanged: async () => () => {},
}) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("./WorkbenchPanels", () => ({ WorkbenchSurface: () => null }));
vi.mock("./workspaceMotion", () => ({ useChatLayoutMotion: () => ({ current: null }) }));
vi.mock("./Composer", () => ({ Composer: (props: any) => <div>
  <output data-testid="composer">{JSON.stringify({
    conversationId: props.conversationId, draft: props.draft,
    provider: props.provider, model: props.model, reasoning: props.reasoningEffort,
    reasoningOptions: props.reasoningOptions,
    autonomy: props.autonomyMode, fast: props.localFastMode, favorites: props.favoriteModels,
    disabled: props.disabled,
  })}</output>
  <button onClick={props.onManageModels}>manage-models</button>
  <button onClick={() => props.onFavoriteModel({ provider: "openai", model: "openai-b" })}>chat-model</button>
  <button onClick={() => props.onFavoriteModel({ provider: "gemini", model: "gemini-b" })}>chat-model-gemini</button>
  <button onClick={() => props.onFavoriteModel({ provider: "gemini", model: "gemini-a" })}>chat-model-original</button>
  <button onClick={() => props.onReasoningEffort("high")}>chat-reasoning</button>
  <button onClick={() => props.onReasoningEffort("max")}>chat-reasoning-max</button>
  <button onClick={() => props.onReasoningEffort("medium")}>chat-reasoning-medium</button>
  <button onClick={() => void props.onSend("QA request").catch(() => {})}>chat-send</button>
</div> }));

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(done => { resolve = done; });
  return { promise, resolve };
}
let values: Record<string, any>;
let patchGate: ReturnType<typeof deferred> | null;
let bootstrapGate: ReturnType<typeof deferred> | null;
let failPatch: boolean;
let failUpdateCheck: boolean;
let reasoningContracts: Record<string, { reasoning_effort: string; reasoning_options: { value: string; label: string }[] }>;
const defaults = () => ({
  api_mode: "gemini", selected_gemini_model: "gemini-a", selected_openai_model: "openai-a",
  favorite_models: [], autonomy_mode: "balanced", local_fast_mode_enabled: false,
  updates_auto_check: false, ui_preferences: { theme_mode: "dark", keep: "saved" },
  voice_hotkey: "Ctrl+Shift+Space", keep_running_in_tray: true,
});
const reasoning = (provider = values.api_mode, model = values[`selected_${provider}_model`]) => reasoningContracts[`${provider}:${model}`] || ({
  reasoning_effort: values.effort || "auto",
  reasoning_options: [{ value: "auto", label: "אוטומטית" }, { value: "high", label: "גבוהה" }],
});
const composer = () => JSON.parse(screen.getByTestId("composer").textContent!);

beforeEach(() => {
  values = defaults(); patchGate = null; bootstrapGate = null; failPatch = false; failUpdateCheck = false;
  reasoningContracts = {};
  localStorage.clear(); sessionStorage.clear();
  vi.stubGlobal("innerWidth", 1800);
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.mocked(invoke).mockReset();
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    if (command === "core_status") return { state: "ready", generation: 1, stderrTail: [] } as any;
    if (command === "core_health") return { ready: true } as any;
    if (command !== "core_api") return null;
    const { method, path, body } = args.request;
    let data: any = { items: [] };
    if (path === "/v2/management/legal") data = { accepted: true };
    if (path.startsWith("/v2/conversations?")) data = { items: [], attention_items: [] };
    if (path === "/v2/management/updates") {
      if (failUpdateCheck) return { status: 502, body: { error: "update_check_failed", detail: "offline" } } as any;
      data = { update: { version: "0.88.0", body: "new release" } };
    }
    if (path === "/v2/bootstrap") {
      data = structuredClone({
        conversations: [], pending_approvals: [], settings: { values },
        chat_models: { providers: [], provider: values.api_mode,
          model: values[`selected_${values.api_mode}_model`], ...reasoning() },
      });
      const gate = bootstrapGate; bootstrapGate = null;
      if (gate) await gate.promise;
    }
    if (path === "/v2/settings") {
      if (method === "PATCH") {
        if (failPatch) return { status: 400, body: { error: "save failed" } } as any;
        const gate = patchGate; patchGate = null;
        if (gate) await gate.promise;
        values = { ...values, ...body.values };
      }
      data = structuredClone({ values, secrets: {} });
    }
    if (path === "/v2/settings/schema") data = { providers: [], secret_help: {} };
    if (/\/providers\/[^/]+\/models$/.test(path)) {
      const provider = path.split("/")[3];
      data = { models: [`${provider}-a`, `${provider}-b`] };
    }
    if (path.includes("/reasoning")) {
      const provider = path.split("/")[3], model = method === "POST" ? body.model : new URLSearchParams(path.split("?")[1]).get("model");
      const contract = reasoningContracts[`${provider}:${model}`];
      if (method === "POST") {
        if (contract && !contract.reasoning_options.some(option => option.value === body.effort))
          return { status: 400, body: { error: "unsupported_reasoning_effort" } } as any;
        if (contract) contract.reasoning_effort = body.effort;
        else values.effort = body.effort;
      }
      data = structuredClone(reasoning(provider, model));
    }
    if (path === "/v2/management/settings/actions" && body.action === "reset") {
      values = defaults(); data = structuredClone({ values, secrets: {} });
    }
    return { status: 200, body: { data } } as any;
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function start() {
  render(<App />);
  await waitFor(() => expect(composer().model).toBe("gemini-a"));
}

test("search opens an older conversation outside the sidebar page and keeps its current title and actions", async () => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  HTMLElement.prototype.scrollIntoView = vi.fn();
  let pinned = false;
  const old = () => ({ id: "older-search-chat", title: "שיחה ישנה מהחיפוש", message_count: 2, pinned });
  const baseInvoke = vi.mocked(invoke).getMockImplementation()!;
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    const response = await baseInvoke(command, args) as any;
    if (command !== "core_api") return response;
    const { method, path, body } = args.request;
    if (path.startsWith("/v2/conversations?q=") && new URLSearchParams(path.split("?")[1]).get("q"))
      response.body.data = { items: [{ ...old(), match_kind: "content", match_ordinal: 0 }], attention_items: [] };
    if (path === "/v2/conversations/older-search-chat") {
      if (method === "PATCH") pinned = body.pinned;
      response.body.data = { conversation: old() };
    }
    if (path.startsWith("/v2/conversations/older-search-chat/messages"))
      response.body.data = path.includes("before=")
        ? { session_id: "older-search-chat", messages: [{ role: "user", content: "הודעה תואמת ישנה", message_id: "older-search-chat:0" }], total_count: 70, has_older: false, next_before_ordinal: null }
        : { session_id: "older-search-chat", messages: [{ role: "assistant", content: "תשובה אחרונה", message_id: "older-search-chat:69" }], total_count: 70, has_older: true, next_before_ordinal: 68 };
    return response;
  });
  await start();
  fireEvent.click(screen.getByRole("button", { name: "חיפוש בשיחות ובקבצים" }));
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "ישנה" } });
  fireEvent.click(await screen.findByRole("option"));
  await screen.findByRole("heading", { name: "שיחה ישנה מהחיפוש" });
  await screen.findByText("הודעה תואמת ישנה");
  await waitFor(() => expect(vi.mocked(invoke).mock.calls.some(([command, args]: any) => command === "core_api" && args.request.path === "/v2/conversations/older-search-chat")).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "פעולות שיחה" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "הצמד שיחה" }));
  await waitFor(() => expect(pinned).toBe(true));
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
  fireEvent.click(screen.getByRole("button", { name: "פעולות שיחה" }));
  await screen.findByRole("menuitem", { name: "בטל הצמדה" });
});
async function patch(next: Record<string, unknown>) {
  await act(async () => { await coreApi("PATCH", "/v2/settings", { values: next }, true); });
}
function distinctReasoningContracts() {
  const contract = (effort: string, levels: string[]) => ({ reasoning_effort: effort,
    reasoning_options: levels.map(value => ({ value, label: value })) });
  reasoningContracts = {
    "gemini:gemini-a": contract("medium", ["minimal", "medium", "high"]),
    "openai:openai-b": contract("medium", ["medium", "high", "max"]),
    "gemini:gemini-b": contract("high", ["low", "high"]),
  };
}

test("a fresh launch opens a blank chat while retaining existing history and its drafts", async () => {
  const previous = { id: "previous", title: "Previous conversation", message_count: 2 };
  sessionStorage.setItem("smarti.desktop.chat-drafts.v1", JSON.stringify({
    previous: { text: "Previous draft", attachments: [] },
  }));
  const baseInvoke = vi.mocked(invoke).getMockImplementation()!;
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    const response = await baseInvoke(command, args) as any;
    if (command === "core_api") {
      const path = args.request.path;
      if (path === "/v2/bootstrap") response.body.data.conversations = [previous];
      if (path.startsWith("/v2/conversations?"))
        response.body.data = { items: [previous], attention_items: [] };
      if (path.startsWith("/v2/conversations/previous/messages"))
        response.body.data = { session_id: "previous", messages: [], total_count: 2, has_older: false };
    }
    return response;
  });

  await start();
  expect(composer()).toMatchObject({ conversationId: "", draft: "" });
  expect(screen.getByRole("heading", { name: "שיחה חדשה" })).toBeTruthy();
  expect(screen.getByText("Previous conversation")).toBeTruthy();
  expect(vi.mocked(invoke).mock.calls.some(([command, args]: any) =>
    command === "core_api" && args.request.path.startsWith("/v2/conversations/previous/messages"))).toBe(false);
  expect(JSON.parse(sessionStorage.getItem("smarti.desktop.chat-drafts.v1")!).previous.text).toBe("Previous draft");
});

test.each([404, 405])("a Core without the live route (%s) uses replay and leaves the composer available", async (status) => {
  const baseInvoke = vi.mocked(invoke).getMockImplementation()!;
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    if (command === "core_api" && args.request.path.startsWith("/v2/events/live"))
      return { status, body: { detail: "live route unavailable" } } as any;
    return baseInvoke(command, args);
  });
  await start();
  await waitFor(() => expect(vi.mocked(invoke).mock.calls.some(([command, args]: any) =>
    command === "core_api" && args.request.path.startsWith("/v2/events/replay"))).toBe(true));
  expect(composer().disabled).toBe(false);
  await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 1250)); });
  expect(vi.mocked(invoke).mock.calls.filter(([command, args]: any) =>
    command === "core_api" && args.request.path.startsWith("/v2/events/live")).length).toBe(1);
  expect(composer().disabled).toBe(false);
});

test("a real live transport failure keeps its reconnect state and recovers through the live route", async () => {
  let failing = true;
  const baseInvoke = vi.mocked(invoke).getMockImplementation()!;
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    if (failing && command === "core_api" && args.request.path.startsWith("/v2/events/live"))
      return { status: 503, body: { detail: "transport unavailable" } } as any;
    return baseInvoke(command, args);
  });
  await start();
  await waitFor(() => expect(composer().disabled).toBe(true));
  expect(vi.mocked(invoke).mock.calls.some(([command, args]: any) =>
    command === "core_api" && args.request.path.startsWith("/v2/events/replay"))).toBe(false);
  failing = false;
  await waitFor(() => expect(composer().disabled).toBe(false), { timeout: 2500 });
});

describe("settings synchronization through the real API client", () => {
  test.each([false, true])("preserves sidebar preference %s through zero-size minimize and restore", async (collapsed) => {
    values.ui_preferences.workspace_sidebar_collapsed = collapsed;
    await start();
    const drawer = () => document.querySelector(".conversation-drawer")!;
    await waitFor(() => expect(drawer().classList.contains("is-open")).toBe(!collapsed));
    const preferences = structuredClone(values.ui_preferences);
    for (const [width, height] of [[0, 0], [1800, 900]]) {
      vi.stubGlobal("innerWidth", width);
      vi.stubGlobal("innerHeight", height);
      await act(async () => {
        fireEvent.resize(window);
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      });
      expect(drawer().classList.contains("is-open")).toBe(!collapsed);
      expect(document.querySelector(".workspace")?.classList.contains("is-overlay-layout")).toBe(false);
      expect(values.ui_preferences).toEqual(preferences);
    }
  });

  test("ignores hidden viewport changes and applies real narrow resizing on return", async () => {
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    await start();
    const drawer = () => document.querySelector(".conversation-drawer")!;
    expect(drawer().classList.contains("is-open")).toBe(true);
    visibility.mockReturnValue("hidden");
    vi.stubGlobal("innerWidth", 900);
    await act(async () => {
      fireEvent(document, new Event("visibilitychange"));
      fireEvent.resize(window);
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    });
    expect(drawer().classList.contains("is-open")).toBe(true);
    visibility.mockReturnValue("visible");
    fireEvent(document, new Event("visibilitychange"));
    await waitFor(() => expect(drawer().classList.contains("is-open")).toBe(false));
    expect(document.querySelector(".workspace")?.classList.contains("is-overlay-layout")).toBe(true);
    vi.stubGlobal("innerWidth", 1800);
    fireEvent.resize(window);
    await waitFor(() => expect(drawer().classList.contains("is-open")).toBe(true));
    expect(values.ui_preferences.workspace_sidebar_collapsed).toBeUndefined();
  });

  test("automatic update discovery records success and displays the available version", async () => {
    values.updates_auto_check = true;
    await start();
    await waitFor(() => expect(values.updates_last_available_version).toBe("0.88.0"), { timeout: 4000 });
    expect(values.updates_last_checked_at).toEqual(expect.any(String));
    expect(screen.getByText("עדכון 0.88.0")).toBeTruthy();
  });

  test("a failed automatic check preserves the last successful result", async () => {
    values.updates_auto_check = true;
    values.updates_last_checked_at = "2020-01-01T00:00:00Z";
    values.updates_last_available_version = "0.87.1";
    failUpdateCheck = true;
    await start();
    await waitFor(() => expect(vi.mocked(invoke).mock.calls.some(([command, args]: any) =>
      command === "core_api" && args.request.path === "/v2/management/updates")).toBe(true), { timeout: 4000 });
    expect(values.updates_last_checked_at).toBe("2020-01-01T00:00:00Z");
    expect(values.updates_last_available_version).toBe("0.87.1");
  });

  test("a recent automatic check uses the saved version without another network check", async () => {
    values.updates_auto_check = true;
    values.updates_last_checked_at = new Date().toISOString();
    values.updates_last_available_version = "0.88.0";
    await start();
    await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 2800)); });
    expect(vi.mocked(invoke).mock.calls.some(([command, args]: any) =>
      command === "core_api" && args.request.path === "/v2/management/updates")).toBe(false);
    expect(screen.getByText("עדכון 0.88.0")).toBeTruthy();
  });

  test.each(["button", "Escape"])("returns from custom permissions to security settings using %s and retains saved permissions", async (backAction) => {
    values.custom_permission_profile_enabled = true;
    values.autonomy_mode = "custom";
    values.policy_matrix = { file_write: "ask" };
    await start();
    fireEvent.click(screen.getByText("manage-models"));
    fireEvent.click(screen.getByRole("button", { name: "אבטחה ופרטיות" }));
    fireEvent.click(await screen.findByRole("button", { name: "הגדרת התאמה אישית" }));
    expect(screen.getByRole("heading", { name: "שליטה מתקדמת ביכולות" })).toBeTruthy();
    const writeCapability = screen.getByText("כתיבת קבצים").closest("section")!;
    fireEvent.click(within(writeCapability).getByRole("button", { name: "חסום" }));
    await waitFor(() => expect(values.policy_matrix.file_write).toBe("deny"));

    const goBack = () => {
      if (backAction === "button") fireEvent.click(screen.getByRole("button", { name: "חזרה לאבטחה ופרטיות" }));
      else fireEvent.keyDown(document, { key: "Escape" });
    };
    goBack();
    expect(screen.getByRole("region", { name: "הגדרות וניהול" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "אבטחה ופרטיות" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "שליטה מתקדמת ביכולות" })).toBeNull();
    expect(screen.getByRole("button", { name: "אבטחה ופרטיות" }).className).toContain("active");

    fireEvent.click(screen.getByRole("button", { name: "הגדרת התאמה אישית" }));
    const savedCapability = screen.getByText("כתיבת קבצים").closest("section")!;
    expect(within(savedCapability).getByRole("button", { name: "חסום" }).className).toContain("active");
    fireEvent.click(screen.getByRole("button", { name: "קול, מראה ומערכת" }));
    fireEvent.click(screen.getByRole("button", { name: "אבטחה ופרטיות" }));
    expect(screen.getByRole("heading", { name: "אבטחה ופרטיות" })).toBeTruthy();
    if (backAction === "button") fireEvent.click(screen.getByRole("button", { name: "חזרה לצ׳אט" }));
    else fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("region", { name: "הגדרות וניהול" })).toBeNull();
    expect(values.policy_matrix.file_write).toBe("deny");
  });

  test("updates provider while settings are open and model after a delayed save finishes after closing", async () => {
    await start();
    fireEvent.click(screen.getByText("manage-models"));
    fireEvent.click(await screen.findByRole("button", { name: "ספק המודל: Google Gemini" }));
    fireEvent.click(screen.getByRole("option", { name: "OpenAI" }));
    await waitFor(() => expect(composer().provider).toBe("openai"));
    fireEvent.click(await screen.findByRole("button", { name: "openai-a" }));
    const gate = deferred(); patchGate = gate;
    fireEvent.click(screen.getByRole("option", { name: "openai-b" }));
    fireEvent.click(screen.getByLabelText("חזרה לצ׳אט"));
    expect(composer().model).toBe("openai-a");
    await act(async () => { gate.resolve(); });
    await waitFor(() => expect(composer().model).toBe("openai-b"));
  });

  test("retains chat-to-settings synchronization and applies reasoning changes without closing settings", async () => {
    await start();
    fireEvent.click(screen.getByText("chat-model"));
    await waitFor(() => expect(values.selected_openai_model).toBe("openai-b"));
    fireEvent.click(screen.getByText("manage-models"));
    await screen.findByRole("button", { name: "ספק המודל: OpenAI" });
    expect(await screen.findByRole("button", { name: "openai-b" })).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "עוצמת חשיבה" }));
    fireEvent.click(screen.getByRole("option", { name: "High" }));
    await waitFor(() => expect(composer().reasoning).toBe("high"));
  });

  test("loads the new provider's contract before its slow save and orders immediate reasoning behind that save", async () => {
    distinctReasoningContracts(); await start();
    const gate = deferred(); patchGate = gate;
    fireEvent.click(screen.getByText("chat-model"));
    await waitFor(() => expect(composer()).toMatchObject({ provider: "openai", model: "openai-b", reasoning: "medium" }));
    expect(composer().reasoningOptions.map((option: any) => option.value)).toEqual(["medium", "high", "max"]);
    expect(values.api_mode).toBe("gemini");
    fireEvent.click(screen.getByText("chat-reasoning"));
    expect(composer().reasoning).toBe("high");
    const posts = () => vi.mocked(invoke).mock.calls.filter(([command, args]: any) =>
      command === "core_api" && args.request.method === "POST" && args.request.path.includes("/reasoning"));
    expect(posts()).toHaveLength(0);
    await act(async () => gate.resolve());
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect((posts()[0][1] as any).request).toMatchObject({ path: "/v2/providers/openai/reasoning", body: { model: "openai-b", effort: "high" } });
    await waitFor(() => expect(reasoningContracts["openai:openai-b"].reasoning_effort).toBe("high"));
    expect(screen.queryByText(/unsupported_reasoning_effort/)).toBeNull();
  });

  test("hides old stops during a slow contract read and ignores that read after a second model selection", async () => {
    distinctReasoningContracts(); await start();
    const gate = deferred(), baseInvoke = vi.mocked(invoke).getMockImplementation()!;
    vi.mocked(invoke).mockImplementation(async (command, args: any) => {
      if (command === "core_api" && args.request.method === "GET" && args.request.path.includes("/providers/openai/reasoning")) {
        const result = await baseInvoke(command, args); await gate.promise; return result;
      }
      return baseInvoke(command, args);
    });
    fireEvent.click(screen.getByText("chat-model"));
    expect(composer()).toMatchObject({ model: "openai-b", reasoning: "", reasoningOptions: [] });
    fireEvent.click(screen.getByText("chat-reasoning"));
    fireEvent.click(screen.getByText("chat-model-gemini"));
    await waitFor(() => expect(composer()).toMatchObject({ provider: "gemini", model: "gemini-b", reasoning: "high" }));
    await act(async () => gate.resolve());
    expect(composer().reasoningOptions.map((option: any) => option.value)).toEqual(["low", "high"]);
    expect(composer().model).toBe("gemini-b");
  });

  test("keeps the latest reasoning optimistic and skips superseded unsent levels", async () => {
    distinctReasoningContracts(); await start();
    fireEvent.click(screen.getByText("chat-model"));
    await waitFor(() => expect(composer().reasoning).toBe("medium"));
    const gate = deferred(), baseInvoke = vi.mocked(invoke).getMockImplementation()!, writes: string[] = [];
    vi.mocked(invoke).mockImplementation(async (command, args: any) => {
      if (command === "core_api" && args.request.method === "POST" && args.request.path.includes("/reasoning")) {
        writes.push(args.request.body.effort); if (writes.length === 1) await gate.promise;
      }
      return baseInvoke(command, args);
    });
    fireEvent.click(screen.getByText("chat-reasoning"));
    await waitFor(() => expect(writes).toEqual(["high"]));
    fireEvent.click(screen.getByText("chat-reasoning-max"));
    fireEvent.click(screen.getByText("chat-reasoning-medium"));
    expect(composer().reasoning).toBe("medium");
    await act(async () => gate.resolve());
    await waitFor(() => expect(writes).toEqual(["high", "medium"]));
    await waitFor(() => expect(reasoningContracts["openai:openai-b"].reasoning_effort).toBe("medium"));
    expect(composer().reasoning).toBe("medium");
  });

  test("a settings refresh received during a reasoning save cannot erase the latest intent", async () => {
    distinctReasoningContracts(); await start();
    const refreshGate = deferred(), writeGate = deferred(), baseInvoke = vi.mocked(invoke).getMockImplementation()!;
    let refreshStarted = false;
    vi.mocked(invoke).mockImplementation(async (command, args: any) => {
      if (command === "core_api" && args.request.method === "POST" && args.request.path.includes("/reasoning")) await writeGate.promise;
      if (command === "core_api" && args.request.path === "/v2/bootstrap" && !refreshStarted) {
        const result = await baseInvoke(command, args); refreshStarted = true; await refreshGate.promise; return result;
      }
      return baseInvoke(command, args);
    });
    await patch({ local_fast_mode_enabled: true });
    await waitFor(() => expect(refreshStarted).toBe(true));
    fireEvent.click(screen.getByText("chat-reasoning"));
    expect(composer().reasoning).toBe("high");
    await act(async () => refreshGate.resolve());
    expect(composer()).toMatchObject({ model: "gemini-a", reasoning: "high", fast: true });
    await act(async () => writeGate.resolve());
    await waitFor(() => expect(reasoningContracts["gemini:gemini-a"].reasoning_effort).toBe("high"));
  });

  test("sending immediately after choosing an effort waits for that effort to be saved", async () => {
    distinctReasoningContracts(); await start();
    const submittedEfforts: string[] = [];
    vi.spyOn(RunSubmission.prototype, "submit").mockImplementation(async () => {
      submittedEfforts.push(reasoningContracts["gemini:gemini-a"].reasoning_effort);
      return { session_id: "qa-session", run_id: "qa-run" };
    });
    const gate = deferred(), baseInvoke = vi.mocked(invoke).getMockImplementation()!;
    vi.mocked(invoke).mockImplementation(async (command, args: any) => {
      if (command === "core_api" && args.request.method === "POST" && args.request.path.includes("/reasoning")) await gate.promise;
      return baseInvoke(command, args);
    });
    fireEvent.click(screen.getByText("chat-reasoning"));
    fireEvent.click(screen.getByText("chat-send"));
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 30)); });
    expect(submittedEfforts).toEqual([]);
    await act(async () => gate.resolve());
    await waitFor(() => expect(submittedEfforts).toEqual(["high"]));
  });

  test("rolls a failed model save back to its complete confirmed contract", async () => {
    distinctReasoningContracts(); await start();
    failPatch = true;
    fireEvent.click(screen.getByText("chat-model"));
    await waitFor(() => expect(screen.getByText(/לא ניתן להחליף מודל/)).toBeTruthy());
    expect(composer()).toMatchObject({ provider: "gemini", model: "gemini-a", reasoning: "medium" });
    expect(composer().reasoningOptions.map((option: any) => option.value)).toEqual(["minimal", "medium", "high"]);
    failPatch = false;
    fireEvent.click(screen.getByText("chat-reasoning"));
    await waitFor(() => expect(reasoningContracts["gemini:gemini-a"].reasoning_effort).toBe("high"));
  });

  test("a failed effort after a pending model save rolls back to the saved effort, not its optimistic value", async () => {
    distinctReasoningContracts(); await start();
    const gate = deferred(); patchGate = gate;
    const baseInvoke = vi.mocked(invoke).getMockImplementation()!;
    vi.mocked(invoke).mockImplementation(async (command, args: any) => {
      if (command === "core_api" && args.request.method === "POST" && args.request.path.includes("/reasoning"))
        return { status: 500, body: { error: "save failed" } } as any;
      return baseInvoke(command, args);
    });
    fireEvent.click(screen.getByText("chat-model"));
    await waitFor(() => expect(composer().reasoning).toBe("medium"));
    fireEvent.click(screen.getByText("chat-reasoning"));
    expect(composer().reasoning).toBe("high");
    await act(async () => gate.resolve());
    await waitFor(() => expect(screen.getByText(/לא ניתן לעדכן עוצמת חשיבה/)).toBeTruthy());
    expect(composer()).toMatchObject({ model: "openai-b", reasoning: "medium" });
  });

  test("returning to a model preserves its pending effort even if its contract read arrives after the write", async () => {
    distinctReasoningContracts(); await start();
    const writeGate = deferred(), readGate = deferred(), baseInvoke = vi.mocked(invoke).getMockImplementation()!;
    let readStarted = false;
    vi.mocked(invoke).mockImplementation(async (command, args: any) => {
      if (command === "core_api" && args.request.method === "POST" && args.request.path.includes("/reasoning")) await writeGate.promise;
      if (command === "core_api" && args.request.method === "GET" && args.request.path.includes("model=gemini-a")) {
        const result = await baseInvoke(command, args); readStarted = true; await readGate.promise; return result;
      }
      return baseInvoke(command, args);
    });
    fireEvent.click(screen.getByText("chat-reasoning"));
    await waitFor(() => expect(composer().reasoning).toBe("high"));
    fireEvent.click(screen.getByText("chat-model"));
    await waitFor(() => expect(composer()).toMatchObject({ model: "openai-b", reasoning: "medium" }));
    fireEvent.click(screen.getByText("chat-model-original"));
    await waitFor(() => expect(readStarted).toBe(true));
    await act(async () => writeGate.resolve());
    await waitFor(() => expect(reasoningContracts["gemini:gemini-a"].reasoning_effort).toBe("high"));
    await act(async () => readGate.resolve());
    expect(composer()).toMatchObject({ provider: "gemini", model: "gemini-a", reasoning: "high" });
    expect(composer().reasoningOptions.map((option: any) => option.value)).toEqual(["minimal", "medium", "high"]);
  });

  test("an old model's delayed reasoning response does not overwrite the newly selected model", async () => {
    await start();
    const gate = deferred(), baseInvoke = vi.mocked(invoke).getMockImplementation()!;
    vi.mocked(invoke).mockImplementation(async (command, args: any) => {
      if (command === "core_api" && args.request.method === "POST" && args.request.path.includes("/reasoning")) {
        await gate.promise;
        return { status: 200, body: { data: { reasoning_effort: "high" } } } as any;
      }
      return baseInvoke(command, args);
    });
    fireEvent.click(screen.getByText("chat-reasoning"));
    await waitFor(() => expect(composer().reasoning).toBe("high"));
    fireEvent.click(screen.getByText("chat-model"));
    await waitFor(() => expect(composer()).toMatchObject({ model: "openai-b", reasoning: "auto" }));
    await act(async () => gate.resolve());
    expect(composer()).toMatchObject({ provider: "openai", model: "openai-b", reasoning: "auto" });
  });

  test("refreshes favorites, safety, FastMode, native preferences and theme, preserving them in later chat writes and resetting them", async () => {
    await start();
    const favorites = [{ provider: "local", model: "local-b" }];
    await patch({ favorite_models: favorites, autonomy_mode: "full", local_fast_mode_enabled: true,
      voice_hotkey: "Ctrl+Alt+V", keep_running_in_tray: false,
      ui_preferences: { theme_mode: "light", keep: "new-value" } });
    await waitFor(() => expect(composer()).toMatchObject({ autonomy: "full", fast: true, favorites }));
    expect(document.querySelector(".smarti-app")?.getAttribute("data-theme")).toBe("light");
    expect(invoke).toHaveBeenCalledWith("desktop_set_voice_hotkey", { shortcut: "Ctrl+Alt+V" });
    expect(invoke).toHaveBeenCalledWith("desktop_set_close_to_tray", { enabled: false });
    // The next layout write must merge the freshly saved preferences.
    const toggle = document.querySelector<HTMLButtonElement>(".drawer-brand");
    if (!toggle) throw new Error("missing conversation sidebar toggle");
    fireEvent.click(toggle);
    await waitFor(() => expect(values.ui_preferences.workspace_sidebar_collapsed).toBeDefined());
    expect(values.ui_preferences).toMatchObject({ theme_mode: "light", keep: "new-value" });
    await act(async () => { await coreApi("POST", "/v2/management/settings/actions", { action: "reset" }, true); });
    await waitFor(() => expect(composer()).toMatchObject({ autonomy: "balanced", fast: false, favorites: [] }));
    expect(document.querySelector(".smarti-app")?.getAttribute("data-theme")).toBe("dark");
    expect(invoke).toHaveBeenCalledWith("desktop_set_close_to_tray", { enabled: true });
  });

  test("ignores an older refresh arriving after a newer saved selection", async () => {
    await start();
    const gate = deferred(); bootstrapGate = gate;
    await patch({ api_mode: "openai" });
    await patch({ selected_openai_model: "openai-b" });
    await waitFor(() => expect(composer().model).toBe("openai-b"));
    await act(async () => { gate.resolve(); });
    expect(composer().model).toBe("openai-b");
  });

  test("publishes only successful setting mutations, including secrets and Codex actions", async () => {
    const changed = vi.fn(); const unsubscribe = subscribeSettingsChanges(changed);
    try {
      await coreApi("GET", "/v2/settings");
      await coreApi("POST", "/v2/providers/openai/models", {});
      await coreApi("POST", "/v2/management/settings/actions", { action: "email_test" });
      failPatch = true;
      await expect(coreApi("PATCH", "/v2/settings", { values: {} })).rejects.toThrow("save failed");
      expect(changed).not.toHaveBeenCalled();
      await coreApi("PUT", "/v2/settings/secrets/openai_api_key", { value: "test-only" });
      await coreApi("POST", "/v2/management/settings/actions", { action: "codex_login" });
      expect(changed).toHaveBeenCalledTimes(2);
    } finally { unsubscribe(); }
  });
});
