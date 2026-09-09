// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import App from "./App";
import { coreApi } from "./coreApi";
import { subscribeSettingsChanges } from "./settingsChanges";

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
    provider: props.provider, model: props.model, reasoning: props.reasoningEffort,
    autonomy: props.autonomyMode, fast: props.localFastMode, favorites: props.favoriteModels,
  })}</output>
  <button onClick={props.onManageModels}>manage-models</button>
  <button onClick={() => props.onFavoriteModel({ provider: "openai", model: "openai-b" })}>chat-model</button>
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
const defaults = () => ({
  api_mode: "gemini", selected_gemini_model: "gemini-a", selected_openai_model: "openai-a",
  favorite_models: [], autonomy_mode: "balanced", local_fast_mode_enabled: false,
  updates_auto_check: false, ui_preferences: { theme_mode: "dark", keep: "saved" },
  voice_hotkey: "Ctrl+Shift+Space", keep_running_in_tray: true,
});
const reasoning = () => ({
  reasoning_effort: values.effort || "auto",
  reasoning_options: [{ value: "auto", label: "אוטומטית" }, { value: "high", label: "גבוהה" }],
});
const composer = () => JSON.parse(screen.getByTestId("composer").textContent!);
const setting = (path: string) => document.querySelector<HTMLSelectElement>(`[data-setting-path="${path}"] select`)!;

beforeEach(() => {
  values = defaults(); patchGate = null; bootstrapGate = null; failPatch = false;
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
      if (method === "POST") values.effort = body.effort;
      data = reasoning();
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
async function patch(next: Record<string, unknown>) {
  await act(async () => { await coreApi("PATCH", "/v2/settings", { values: next }, true); });
}

describe("settings synchronization through the real API client", () => {
  test("updates provider while settings are open and model after a delayed save finishes after closing", async () => {
    await start();
    fireEvent.click(screen.getByText("manage-models"));
    await waitFor(() => expect(setting("api_mode")?.value).toBe("gemini"));
    fireEvent.change(setting("api_mode"), { target: { value: "openai" } });
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
    await waitFor(() => expect(setting("api_mode")?.value).toBe("openai"));
    expect(await screen.findByRole("button", { name: "openai-b" })).toBeTruthy();
    await waitFor(() => expect(setting("provider_reasoning_effort")).toBeTruthy());
    fireEvent.change(setting("provider_reasoning_effort"), { target: { value: "high" } });
    await waitFor(() => expect(composer().reasoning).toBe("high"));
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
    const toggle = document.querySelector<HTMLButtonElement>(".drawer-collapse-control");
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
