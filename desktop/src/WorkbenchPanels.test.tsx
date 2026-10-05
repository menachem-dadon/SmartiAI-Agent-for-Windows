// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
const workbenchRequests = () => vi.mocked(coreApi).mock.calls.filter(([, path]) => path.startsWith("/v2/workbench/"));

async function start() {
  render(<App />);
  await waitFor(() => expect(document.querySelector(".workbench-empty")).toBeTruthy());
}

describe("Workbench session lifecycle through the product shell", () => {
  const cache = () => JSON.parse(sessionStorage.getItem("smarti-workbench-session-v2")!);
  const seed = (snapshot: unknown, open = false) => sessionStorage.setItem("smarti-workbench-session-v2", JSON.stringify({ owner: "qa", snapshot, open, expanded: false }));
  const openPanel = () => fireEvent.click(screen.getByRole("button", { name: "פתיחת סביבת העבודה" }));
  const add = (name: string) => { fireEvent.click(screen.getByRole("button", { name: "פתיחת לשונית" })); fireEvent.click(screen.getByRole("menuitem", { name })); };

  test.each([[1800, "button"], [1800, "shortcut"], [900, "button"], [900, "shortcut"]] as const)("opens exactly four empty entries at %i via %s without starting a tool", async (width, trigger) => {
    vi.stubGlobal("innerWidth", width); await start();
    if (trigger === "button") openPanel(); else fireEvent.keyDown(window, { key: "b", ctrlKey: true });
    expect(within(launcher()).getAllByRole("button").map(button => button.textContent)).toEqual(["דפדפן", "קבצים", "מסוף", "תוצרים"]);
    expect(screen.queryAllByRole("tab")).toHaveLength(0); expect(BrowserPanel).not.toHaveBeenCalled(); expect(workbenchRequests()).toHaveLength(0);
    expect(preferences.workspace_workbench).toBeUndefined();
  });
  test.each([["קבצים", "/v2/workbench/tree?depth=3"], ["מסוף", "/v2/workbench/terminals"], ["תוצרים", "/v2/workbench/artifacts"]])("starts %s only after choosing it", async (label, path) => {
    await start(); openPanel(); expect(workbenchRequests()).toHaveLength(0);
    fireEvent.click(within(launcher()).getByRole("button", { name: label }));
    await waitFor(() => expect(workbenchRequests().some(([, request]) => request === path)).toBe(true));
    expect(screen.getAllByRole("tab")).toHaveLength(1); expect(screen.queryByRole("group", { name: "מה תרצה לפתוח?" })).toBeNull();
  });
  test("preserves the last active tab and native owner on panel close/reopen and WebView reload", async () => {
    seed({ tabs: [{ id: "browser-1", kind: "browser", title: "דפדפן" }, { id: "browser-2", kind: "browser", title: "דפדפן 2" }], active: "browser-2" }, true);
    const view = render(<App />);
    await waitFor(() => expect(vi.mocked(BrowserPanel).mock.lastCall?.[0].workspaceTabId).toBe("browser-2"));
    const activity = { workspaceId: "browser-2", tabId: "tab-2", title: "Second browser", url: "https://two.test/", loading: false, previewDataUrl: "data:image/jpeg;base64,page" };
    await act(async () => vi.mocked(BrowserPanel).mock.lastCall?.[0].onActivity?.(activity));
    fireEvent.click(screen.getByRole("button", { name: "סגירת סביבת העבודה" }));
    expect(screen.getByRole("img", { name: "תצוגה מקדימה של Second browser" }).getAttribute("src")).toBe(activity.previewDataUrl);
    fireEvent.click(screen.getByRole("button", { name: "סגירת התצוגה המקדימה" }));
    await act(async () => vi.mocked(BrowserPanel).mock.lastCall?.[0].onActivity?.(activity));
    expect(screen.queryByLabelText("תצוגה מקדימה של הדפדפן")).toBeNull();
    openPanel(); expect(screen.getByRole("tab", { name: "דפדפן 2" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "סגירת סביבת העבודה" }));
    fireEvent.click(screen.getByRole("button", { name: "פתיחת Second browser" }));
    expect(vi.mocked(BrowserPanel).mock.lastCall?.[0].workspaceTabId).toBe("browser-2");
    await waitFor(() => expect(cache().snapshot.active).toBe("browser-2"));
    view.unmount(); render(<App />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "דפדפן 2" }).getAttribute("aria-selected")).toBe("true"));
  });
  test("a new WebView starts empty despite legacy Core snapshots, retaining all personal preferences", async () => {
    preferences = { workspace_workbench_open: true, workspace_workbench: { tabs: [{ id: "browser-8", kind: "browser", title: "דפדפן" }], active: "browser-8" }, unrelated: "preserve" };
    await start(); openPanel(); expect(launcher()).toBeTruthy(); expect(BrowserPanel).not.toHaveBeenCalled();
    expect(preferences.unrelated).toBe("preserve"); expect((preferences.workspace_workbench as any).tabs[0].id).toBe("browser-8");
  });
  test("closes the final tab, rejects its late preview, and returns to the empty chooser", async () => {
    await start(); openPanel(); fireEvent.click(within(launcher()).getByRole("button", { name: "דפדפן" }));
    const props = vi.mocked(BrowserPanel).mock.lastCall?.[0];
    const activity = { workspaceId: props!.workspaceTabId!, tabId: "tab-1", title: "Closed", url: "https://closed.test/", loading: false };
    fireEvent.click(screen.getByRole("button", { name: "סגירת דפדפן" }));
    await waitFor(() => expect(launcher()).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "סגירת סביבת העבודה" }));
    await act(async () => props?.onActivity?.(activity)); expect(screen.queryByLabelText("תצוגה מקדימה של הדפדפן")).toBeNull();
    openPanel(); expect(launcher()).toBeTruthy(); expect(cache().snapshot).toEqual({ tabs: [], active: "" });
  });
  test("adds repeatable tabs through the shared menu, reuses titles, and keeps IDs unique", async () => {
    seed({ tabs: [{ id: "browser-8", kind: "browser", title: "דפדפן" }], active: "browser-8" }, true);
    render(<App />); await screen.findByRole("tab", { name: "דפדפן" }); add("קבצים"); add("דפדפן");
    expect(screen.getAllByRole("tab").map(tab => tab.textContent)).toEqual(["דפדפן", "קבצים", "דפדפן 2"]);
    const ids = screen.getAllByRole("tab").map(tab => tab.dataset.tabId); expect(new Set(ids).size).toBe(3);
    fireEvent.click(screen.getByRole("button", { name: "סגירת דפדפן" })); await waitFor(() => expect(screen.queryByRole("tab", { name: "דפדפן" })).toBeNull()); add("דפדפן");
    expect(screen.getAllByRole("tab").map(tab => tab.textContent)).toEqual(["קבצים", "דפדפן 2", "דפדפן"]);
  });
  test("expands and returns to split mode without remounting the selected panel", async () => {
    await start(); openPanel(); fireEvent.click(within(launcher()).getByRole("button", { name: "קבצים" }));
    const field = screen.getByRole("textbox", { name: "נתיב תיקיית העבודה" }); fireEvent.change(field, { target: { value: "draft path" } });
    fireEvent.click(screen.getByRole("button", { name: "הרחבת סביבת העבודה" }));
    expect(document.querySelector(".chat-column")?.hasAttribute("inert")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "חזרה לעבודה משולבת" }));
    expect(screen.getByRole("textbox", { name: "נתיב תיקיית העבודה" })).toBe(field); expect((field as HTMLInputElement).value).toBe("draft path");
    expect(document.querySelector(".chat-column")?.hasAttribute("inert")).toBe(false);
  });
});
