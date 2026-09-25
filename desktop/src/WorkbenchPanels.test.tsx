// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { coreApi } from "./coreApi";
import { BrowserPanel } from "./BrowserPanel";

vi.mock("@tauri-apps/api/core", () => ({ invoke: async (command: string) => {
  if (command === "core_status") return { state: "ready", generation: 1, stderrTail: [] };
  if (command === "core_health") return { ready: true };
  return null;
} }));
vi.mock("@tauri-apps/api/window", () => ({ getCurrentWindow: () => ({
  isMaximized: async () => false,
  onResized: async () => () => {},
  onFocusChanged: async () => () => {},
}) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: async () => () => {} }));
vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
vi.mock("./Composer", () => ({ Composer: () => null }));
vi.mock("./BrowserPanel", () => ({ BrowserPanel: vi.fn(() => <div>browser-content</div>), forgetBrowserWorkspaceSession: vi.fn() }));
vi.mock("./CanvasPanel", () => ({ CanvasPanel: () => <div>canvas-content</div> }));
vi.mock("./workspaceMotion", () => ({ useChatLayoutMotion: () => ({ current: null }) }));

let preferences: Record<string, unknown>;

beforeEach(() => {
  preferences = {};
  localStorage.clear(); sessionStorage.clear();
  vi.clearAllMocks();
  vi.stubGlobal("innerWidth", 1800);
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.mocked(coreApi).mockImplementation(async (method, path, body) => {
    const settings = () => ({ values: { updates_auto_check: false, ui_preferences: preferences } });
    if (path === "/v2/management/legal") return { accepted: true } as any;
    if (path === "/v2/bootstrap") return {
      conversations: [], pending_approvals: [], settings: settings(),
      chat_models: { providers: [], provider: "local", model: "test" },
    } as any;
    if (path === "/v2/settings") {
      if (method === "PATCH") preferences = (body as any).values.ui_preferences;
      return settings() as any;
    }
    if (path.startsWith("/v2/conversations?")) return { items: [], attention_items: [] } as any;
    if (path === "/v2/workbench/tree?depth=3")
      return { root: { name: "Smarti", path: "C:/workspace" }, items: [] } as any;
    if (path === "/v2/workbench/terminals") return { id: "terminal-test" } as any;
    return { items: [] } as any;
  });
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const launcher = () => screen.getByRole("group", { name: "מה תרצה לפתוח?" });
const workbench = () => screen.getByLabelText("Workbench");
const workbenchRequests = () => vi.mocked(coreApi).mock.calls.filter(([, path]) => path.startsWith("/v2/workbench/"));

async function start() {
  render(<App />);
  await waitFor(() => expect(document.querySelector(".workbench-empty")).toBeTruthy());
}

describe("Workbench launcher through the app shell", () => {
  test.each([
    [1800, "button"], [1800, "shortcut"], [900, "button"], [900, "shortcut"],
  ] as const)("opens an empty chooser at %i px using %s without starting a tool", async (width, trigger) => {
    vi.stubGlobal("innerWidth", width);
    await start();
    if (trigger === "button") fireEvent.click(screen.getByRole("button", { name: "פתיחת סביבת העבודה" }));
    else fireEvent.keyDown(window, { key: "b", ctrlKey: true });

    expect(within(launcher()).getAllByRole("button").map((button) => button.textContent))
      .toEqual(["קבצים", "דפדפן", "מסוף", "קנבס", "תוצרים"]);
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(BrowserPanel).not.toHaveBeenCalled();
    expect(workbenchRequests()).toHaveLength(0);
    await waitFor(() => expect(preferences.workspace_workbench_open).toBe(true));
  });

  test.each([
    ["קבצים", "/v2/workbench/tree?depth=3"],
    ["מסוף", "/v2/workbench/terminals"],
    ["תוצרים", "/v2/workbench/artifacts"],
  ])("starts %s only after choosing it", async (label, path) => {
    await start();
    fireEvent.click(screen.getByRole("button", { name: "פתיחת סביבת העבודה" }));
    expect(workbenchRequests()).toHaveLength(0);
    fireEvent.click(within(launcher()).getByRole("button", { name: label }));
    await waitFor(() => expect(workbenchRequests().some(([, requestPath]) => requestPath === path)).toBe(true));
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    expect(screen.queryByRole("group", { name: "מה תרצה לפתוח?" })).toBeNull();
    expect(BrowserPanel).not.toHaveBeenCalled();
  });

  test("returns to the chooser after closing the last tab and keeps it empty on reopen", async () => {
    await start();
    fireEvent.click(screen.getByRole("button", { name: "פתיחת סביבת העבודה" }));
    fireEvent.click(within(launcher()).getByRole("button", { name: "דפדפן" }));
    expect(screen.getByText("browser-content")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "סגירת דפדפן" }));
    expect(launcher()).toBeTruthy();
    await waitFor(() => expect(preferences.workspace_workbench).toEqual({ tabs: [], active: "" }));
    expect(workbench().getAttribute("aria-hidden")).toBe("false");
    expect(preferences.workspace_workbench_open).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "סגירת סביבת העבודה" }));
    fireEvent.click(screen.getByRole("button", { name: "פתיחת סביבת העבודה" }));
    expect(launcher()).toBeTruthy();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    fireEvent.click(within(launcher()).getByRole("button", { name: "קנבס" }));
    expect(screen.getByText("canvas-content")).toBeTruthy();
  });

  test("uses per-kind tab numbers and reuses a title after its tab closes", async () => {
    await start();
    fireEvent.click(screen.getByRole("button", { name: "פתיחת סביבת העבודה" }));
    fireEvent.click(within(launcher()).getByRole("button", { name: "דפדפן" }));
    const add = (label: string) => {
      const menu = within(document.querySelector(".workbench-add")!);
      fireEvent.click(menu.getByRole("button", { name: "פתיחת לשונית" }));
      fireEvent.click(menu.getByRole("button", { name: new RegExp(`${label}$`) }));
    };
    add("קבצים");
    add("דפדפן");
    expect(vi.mocked(BrowserPanel).mock.lastCall?.[0].workspaceTabId).toBe("browser-3");
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent?.replace("×", "").trim()))
      .toEqual(["◎דפדפן", "▤קבצים", "◎דפדפן 2"]);
    fireEvent.click(screen.getByRole("button", { name: "סגירת דפדפן" }));
    add("דפדפן");
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent?.replace("×", "").trim()))
      .toEqual(["▤קבצים", "◎דפדפן 2", "◎דפדפן"]);
  });

  test("keeps restored tab IDs unique while numbering their titles from open tabs", async () => {
    preferences = { workspace_workbench_open: true, workspace_workbench: {
      tabs: [{ id: "browser-8", kind: "browser", title: "דפדפן" }], active: "browser-8",
    } };
    render(<App />);
    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(1));
    const menu = within(document.querySelector(".workbench-add")!);
    fireEvent.click(menu.getByRole("button", { name: "פתיחת לשונית" }));
    fireEvent.click(menu.getByRole("button", { name: /דפדפן$/ }));
    expect(screen.getAllByRole("tab").map((tab) => tab.dataset.tabId)).toEqual(["browser-8", "browser-9"]);
    expect(screen.getByRole("button", { name: "סגירת דפדפן 2" })).toBeTruthy();
  });

  test("restores an open empty Workbench after restarting", async () => {
    preferences = { workspace_workbench_open: true, workspace_workbench: { tabs: [], active: "" } };
    await start();
    expect(launcher()).toBeTruthy();
    expect(workbench().getAttribute("aria-hidden")).toBe("false");
    expect(BrowserPanel).not.toHaveBeenCalled();
    expect(workbenchRequests()).toHaveLength(0);
  });

  test("reopens saved tabs without adding or switching to a browser", async () => {
    preferences = { workspace_workbench_open: false, workspace_workbench: {
      tabs: [{ id: "canvas-1", kind: "canvas", title: "קנבס" }], active: "canvas-1",
    } };
    render(<App />);
    await waitFor(() => expect(document.querySelector(".workbench-panel")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "פתיחת סביבת העבודה" }));
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    expect(screen.getByText("canvas-content")).toBeTruthy();
    expect(BrowserPanel).not.toHaveBeenCalled();
  });
});
