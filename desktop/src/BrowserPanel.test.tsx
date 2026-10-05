// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BrowserSnapshot } from "./browserState";

const mocks = vi.hoisted(() => ({
  coreApi: vi.fn(),
  invoke: vi.fn(),
  listen: vi.fn(),
  innerPosition: vi.fn(),
  scaleFactor: vi.fn(),
}));

vi.mock("@tauri-apps/api/core", () => ({ invoke: mocks.invoke }));
vi.mock("@tauri-apps/api/event", () => ({ listen: mocks.listen }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => ({
    innerPosition: mocks.innerPosition,
    scaleFactor: mocks.scaleFactor,
  }),
}));
vi.mock("@tauri-apps/plugin-opener", () => ({ openUrl: vi.fn() }));
vi.mock("./coreApi", () => ({ coreApi: mocks.coreApi }));

import { BrowserPanel } from "./BrowserPanel";
import { publishSettingsChange } from "./settingsChanges";

const snapshot: BrowserSnapshot = {
  tabs: [
    {
      tabId: "tab-00000001",
      targetId: "wv2-target-00000001",
      webviewLabel: "browser-00000001",
      profile: "persistent",
      url: "https://example.com/",
      title: "Example",
      loading: false,
      active: true,
      crashed: false,
      pinned: false,
      faviconUrl: "",
      audioPlaying: false,
    },
  ],
  activeTabId: "tab-00000001",
  transport: "webview2-in-process-cdp",
  remoteDebuggingPort: null,
};

class ResizeObserverStub {
  observe() {}
  disconnect() {}
}

let selectedMenuId: string | null;

const lastNativeVisibility = () => {
  const calls = mocks.invoke.mock.calls.filter(
    ([command]) => command === "browser_set_visible",
  );
  return calls[calls.length - 1]?.[1];
};
const lastNativeBounds = () => {
  const calls = mocks.invoke.mock.calls.filter(
    ([command]) => command === "browser_set_bounds",
  );
  return calls[calls.length - 1]?.[1];
};

beforeEach(() => {
  mocks.coreApi.mockReset();
  mocks.coreApi.mockResolvedValue({ values: {} });
  mocks.listen.mockReset();
  mocks.listen.mockResolvedValue(() => undefined);
  mocks.innerPosition.mockReset();
  mocks.innerPosition.mockResolvedValue({ x: 100, y: 50 });
  mocks.scaleFactor.mockReset();
  mocks.scaleFactor.mockResolvedValue(1.5);
  selectedMenuId = null;
  mocks.invoke.mockReset();
  mocks.invoke.mockImplementation(async (command: string) => {
    if (command === "browser_status" || command === "browser_metadata")
      return snapshot;
    if (command === "desktop_popup_rtl_menu") return selectedMenuId;
    return undefined;
  });
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    return window.setTimeout(() => callback(performance.now()), 16);
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    x: 10,
    y: 200,
    width: 800,
    height: 600,
    top: 200,
    right: 810,
    bottom: 800,
    left: 10,
    toJSON: () => ({}),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("native browser overlay visibility", () => {
  it("creates a separate native page for a newly opened Workbench browser tab", async () => {
    let state: BrowserSnapshot = {
      ...snapshot,
      tabs: [{ ...snapshot.tabs[0], workspaceId: "browser-1", url: "https://one.test/" }],
    };
    mocks.invoke.mockImplementation(async (command: string, args?: { workspaceId?: string; tabId?: string }) => {
      if (command === "browser_status" || command === "browser_metadata") return state;
      if (command === "browser_open" && args?.workspaceId === "browser-2") {
        state = {
          ...state, activeTabId: "tab-00000002",
          tabs: [...state.tabs.map((tab) => ({ ...tab, active: false })), { ...snapshot.tabs[0], tabId: "tab-00000002", workspaceId: "browser-2", url: "https://www.google.com/?hl=he" }],
        };
        return state;
      }
      if (command === "browser_activate" && args?.tabId) {
        state = { ...state, activeTabId: args.tabId };
        return state;
      }
      return undefined;
    });
    const { rerender } = render(<BrowserPanel visible workspaceTabId="browser-1" />);
    await waitFor(() => expect((screen.getByRole("textbox", { name: "כתובת או חיפוש" }) as HTMLInputElement).value).toBe("https://one.test/"));
    rerender(<BrowserPanel visible workspaceTabId="browser-2" />);
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith("browser_open", expect.objectContaining({ workspaceId: "browser-2" })));
    await waitFor(() => expect((screen.getByRole("textbox", { name: "כתובת או חיפוש" }) as HTMLInputElement).value).toBe("https://www.google.com/?hl=he"));
    expect(state.tabs.map((tab) => tab.workspaceId)).toEqual(["browser-1", "browser-2"]);
  });
  it("keeps addresses and navigation independent across Workbench browser tabs", async () => {
    let state: BrowserSnapshot = {
      ...snapshot,
      tabs: [
        { ...snapshot.tabs[0], workspaceId: "browser-1", url: "https://one.test/", title: "One" },
        { ...snapshot.tabs[0], tabId: "tab-00000002", targetId: "wv2-target-00000002", webviewLabel: "browser-00000002", workspaceId: "browser-2", url: "https://two.test/", title: "Two", active: false },
      ],
    };
    mocks.invoke.mockImplementation(async (command: string, args?: { tabId?: string; url?: string }) => {
      if (command === "browser_status" || command === "browser_metadata") return state;
      if (command === "browser_activate" && args?.tabId) {
        state = { ...state, activeTabId: args.tabId, tabs: state.tabs.map((tab) => ({ ...tab, active: tab.tabId === args.tabId })) };
        return state;
      }
      if (command === "browser_navigate" && args?.tabId && args.url) {
        state = { ...state, tabs: state.tabs.map((tab) => tab.tabId === args.tabId ? { ...tab, url: args.url! } : tab) };
        return state;
      }
      return undefined;
    });
    const { rerender } = render(<BrowserPanel visible workspaceTabId="browser-1" />);
    await waitFor(() => expect((screen.getByRole("textbox", { name: "כתובת או חיפוש" }) as HTMLInputElement).value).toBe("https://one.test/"));
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    rerender(<BrowserPanel visible workspaceTabId="browser-2" />);
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith("browser_activate", { tabId: "tab-00000002" }));
    await waitFor(() => expect((screen.getByRole("textbox", { name: "כתובת או חיפוש" }) as HTMLInputElement).value).toBe("https://two.test/"));
    fireEvent.change(screen.getByRole("textbox", { name: "כתובת או חיפוש" }), { target: { value: "https://changed.test/" } });
    fireEvent.submit(screen.getByRole("textbox", { name: "כתובת או חיפוש" }).closest("form")!);
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith("browser_navigate", { tabId: "tab-00000002", url: "https://changed.test/" }));
    rerender(<BrowserPanel visible workspaceTabId="browser-1" />);
    await waitFor(() => expect((screen.getByRole("textbox", { name: "כתובת או חיפוש" }) as HTMLInputElement).value).toBe("https://one.test/"));
    expect(state.tabs[0].url).toBe("https://one.test/");
  });
  it("offers automatic mobile layout and lets the user override it for the current tab", async () => {
    vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockReturnValue({
      x: 10, y: 100, width: 390, height: 620, top: 100, right: 400, bottom: 720, left: 10,
      toJSON: () => ({}),
    });
    render(<BrowserPanel visible />);
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith("browser_action", {
      action: expect.objectContaining({ method: "Emulation.setDeviceMetricsOverride", params: { width: 390, height: 620, mobile: true, deviceScaleFactor: 0 } }),
    }));
    selectedMenuId = "browser-viewport-desktop";
    fireEvent.click(screen.getByRole("button", { name: "תפריט דפדפן" }));
    await waitFor(() => expect(mocks.invoke).toHaveBeenCalledWith("browser_action", {
      action: expect.objectContaining({ tabId: snapshot.activeTabId, method: "Emulation.clearDeviceMetricsOverride" }),
    }));
    const menu = mocks.invoke.mock.calls.find(([name]) => name === "desktop_popup_rtl_menu")![1].items;
    expect(menu).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: "browser-viewport-auto", text: "✓ תצוגה אוטומטית לפי הרוחב" }),
      expect.objectContaining({ id: "browser-viewport-mobile" }),
      expect.objectContaining({ id: "browser-viewport-desktop" }),
    ]));
    expect(mocks.invoke.mock.calls.some(([name]) => name === "browser_reload")).toBe(false);
  });

  it("updates developer tools after settings change without recreating the browser", async () => {
    render(<BrowserPanel visible />);
    await waitFor(() => expect(lastNativeVisibility()).toEqual({ visible: true }));
    const menuItems = async () => {
      // The native menu deliberately suppresses reopen clicks for 220 ms.
      await act(async () => { await new Promise(resolve => window.setTimeout(resolve, 230)); });
      const previous = mocks.invoke.mock.calls.filter(([command]) => command === "desktop_popup_rtl_menu").length;
      fireEvent.click(screen.getByRole("button", { name: "תפריט דפדפן" }));
      await waitFor(() => expect(mocks.invoke.mock.calls.filter(([command]) => command === "desktop_popup_rtl_menu")).toHaveLength(previous + 1));
      return mocks.invoke.mock.calls.filter(([command]) => command === "desktop_popup_rtl_menu")[previous][1].items;
    };
    expect(await menuItems()).not.toEqual(expect.arrayContaining([expect.objectContaining({ id: "browser-devtools" })]));
    mocks.coreApi.mockResolvedValue({ values: { enable_developer_trace: true } });
    await act(async () => { publishSettingsChange("PATCH", "/v2/settings"); });
    expect(await menuItems()).toEqual(expect.arrayContaining([expect.objectContaining({ id: "browser-devtools" })]));
    mocks.coreApi.mockResolvedValue({ values: { enable_developer_trace: false } });
    await act(async () => { publishSettingsChange("PATCH", "/v2/settings"); });
    expect(await menuItems()).not.toEqual(expect.arrayContaining([expect.objectContaining({ id: "browser-devtools" })]));
  });

  it("keeps native bounds idle during the CSS slide and positions only the final frame", async () => {
    const frame = (visible: boolean, revision: string) => <aside className="workbench"><BrowserPanel visible={visible} geometryRevision={revision} /></aside>;
    const { rerender } = render(frame(true, "open"));
    await new Promise((resolve) => window.setTimeout(resolve, 150));
    expect(lastNativeBounds()).toBeUndefined();
    expect(lastNativeVisibility()).toEqual({ visible: false });
    await waitFor(() => expect(lastNativeVisibility()).toEqual({ visible: true }));
    expect(mocks.invoke.mock.calls.filter(([command]) => command === "browser_set_bounds")).toHaveLength(1);
    rerender(frame(false, "closed"));
    expect(lastNativeVisibility()).toEqual({ visible: false });
    rerender(frame(true, "reopen"));
    await new Promise((resolve) => window.setTimeout(resolve, 100));
    rerender(frame(false, "reverse"));
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    expect(lastNativeVisibility()).toEqual({ visible: false });
    expect(mocks.invoke.mock.calls.filter(([command]) => command === "browser_set_bounds")).toHaveLength(1);
  });

  it("uses the CSS completion event instead of waiting for an unrelated timer", async () => {
    const { container } = render(<aside className="workbench"><BrowserPanel visible geometryRevision="open" /></aside>);
    const workbench = container.querySelector(".workbench")!;
    const event = new Event("transitionend", { bubbles: true });
    Object.defineProperty(event, "propertyName", { value: "transform" });
    fireEvent(workbench, event);
    await waitFor(() => expect(lastNativeVisibility()).toEqual({ visible: true }));
    const calls = mocks.invoke.mock.calls.filter(([command]) => command === "browser_set_bounds").length;
    await new Promise((resolve) => window.setTimeout(resolve, 400));
    expect(mocks.invoke.mock.calls.filter(([command]) => command === "browser_set_bounds")).toHaveLength(calls);
  });

  it("keeps a non-interactive cached page image available while the native surface is hidden", async () => {
    mocks.invoke.mockImplementation(async (command: string, args?: { action?: { method?: string } }) => {
      if (command === "browser_status" || command === "browser_metadata") return snapshot;
      if (command === "browser_action" && args?.action?.method === "Page.captureScreenshot")
        return { result: { data: "cached-page" } };
      return undefined;
    });
    const { container, rerender } = render(<BrowserPanel visible />);
    await waitFor(() => expect(container.querySelector(".browser-motion-preview")?.getAttribute("src")).toBe("data:image/jpeg;base64,cached-page"));
    rerender(<BrowserPanel visible={false} />);
    expect(container.querySelector(".browser-motion-preview")?.getAttribute("aria-hidden")).toBe("true");
    expect(lastNativeVisibility()).toEqual({ visible: false });
  });

  it("publishes the cached page with metadata and clears activity when the native target closes", async () => {
    const onActivity = vi.fn();
    let update: ((event: { payload: BrowserSnapshot }) => void) | undefined;
    let state: BrowserSnapshot = { ...snapshot, tabs: [{ ...snapshot.tabs[0], workspaceId: "browser-1" }] };
    mocks.listen.mockImplementation(async (event, callback) => {
      if (event === "browser://state") update = callback;
      return () => {};
    });
    mocks.invoke.mockImplementation(async (command: string, args?: { action?: { method?: string } }) => {
      if (command === "browser_status" || command === "browser_metadata") return state;
      if (command === "browser_action" && args?.action?.method === "Page.captureScreenshot")
        return { result: { data: "real-page" } };
      return undefined;
    });
    const { rerender } = render(<BrowserPanel visible workspaceTabId="browser-1" onActivity={onActivity} />);
    await waitFor(() => expect(onActivity).toHaveBeenLastCalledWith(expect.objectContaining({
      workspaceId: "browser-1", tabId: snapshot.activeTabId, previewDataUrl: "data:image/jpeg;base64,real-page",
    })));
    rerender(<BrowserPanel visible={false} workspaceTabId="browser-1" onActivity={onActivity} />);
    state = { ...state, tabs: [{ ...state.tabs[0], title: "Updated page title" }] };
    await act(async () => update?.({ payload: state }));
    expect(onActivity).toHaveBeenLastCalledWith(expect.objectContaining({ title: "Updated page title", previewDataUrl: "data:image/jpeg;base64,real-page" }));
    state = { ...state, tabs: [], activeTabId: null };
    await act(async () => update?.({ payload: state }));
    expect(onActivity).toHaveBeenLastCalledWith(null);
  });

  it("skips the transition delay when reduced motion is requested", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    render(<aside className="workbench"><BrowserPanel visible geometryRevision="open" /></aside>);
    await waitFor(() => expect(lastNativeVisibility()).toEqual({ visible: true }));
    expect(mocks.invoke.mock.calls.findIndex(([command]) => command === "browser_set_bounds")).toBeLessThan(mocks.invoke.mock.calls.findIndex(([command, args]) => command === "browser_set_visible" && args.visible));
  });

  it("does not reveal at rejected bounds and uses a bounded retry", async () => {
    let rejectBounds = true;
    mocks.invoke.mockImplementation(async (command: string) => {
      if (command === "browser_status" || command === "browser_metadata") return snapshot;
      if (command === "browser_set_bounds" && rejectBounds) throw new Error("bounds rejected");
      return undefined;
    });
    render(<BrowserPanel visible />);
    await waitFor(() => expect(lastNativeBounds()).toBeDefined());
    expect(mocks.invoke.mock.calls.some(([command, args]) => command === "browser_set_visible" && args.visible)).toBe(false);
    rejectBounds = false;
    await waitFor(() => expect(lastNativeVisibility()).toEqual({ visible: true }));
  });

  it("does not reveal after closing while the first bounds request is pending", async () => {
    let finishBounds: (() => void) | undefined;
    mocks.invoke.mockImplementation(async (command: string) => {
      if (command === "browser_status" || command === "browser_metadata") return snapshot;
      if (command === "browser_set_bounds") return new Promise<void>((resolve) => { finishBounds = resolve; });
      return undefined;
    });
    const { rerender } = render(<BrowserPanel visible />);
    await waitFor(() => expect(finishBounds).toBeDefined());
    rerender(<BrowserPanel visible={false} />);
    finishBounds!();
    await waitFor(() => expect(lastNativeVisibility()).toEqual({ visible: false }));
    expect(mocks.invoke.mock.calls.some(([command, args]) => command === "browser_set_visible" && args.visible)).toBe(false);
  });

  it("opens the ellipsis menu above WebView2 without hiding or resizing it", async () => {
    render(
      <BrowserPanel visible geometryRevision />,
    );

    await waitFor(() =>
      expect(lastNativeVisibility()).toEqual({ visible: true }),
    );
    await waitFor(() =>
      expect(lastNativeBounds()).toEqual({
        bounds: { x: 10, y: 200, width: 800, height: 600 },
      }),
    );
    const firstBoundsCall = mocks.invoke.mock.calls.findIndex(
      ([command]) => command === "browser_set_bounds",
    );
    const firstVisibleFrame = mocks.invoke.mock.calls.findIndex(
      ([command, args]) =>
        command === "browser_set_visible" && args.visible === true,
    );
    expect(firstBoundsCall).toBeGreaterThanOrEqual(0);
    expect(firstVisibleFrame).toBeGreaterThan(firstBoundsCall);

    const trigger = screen.getByRole("button", { name: "תפריט דפדפן" });
    const browser = trigger.closest(".embedded-browser");
    expect(browser).not.toBeNull();
    const beforeMenu = mocks.invoke.mock.calls.length;
    fireEvent.click(trigger);

    await waitFor(() =>
      expect(mocks.invoke).toHaveBeenCalledWith(
        "desktop_popup_rtl_menu",
        expect.objectContaining({
          x: 1315,
          y: 1256,
          items: expect.arrayContaining([
            expect.objectContaining({
              id: "browser-find",
              text: "חיפוש בדף",
              accelerator: "Ctrl+F",
            }),
            expect.objectContaining({ separator: true }),
          ]),
        }),
      ),
    );
    expect(browser!.classList.contains("has-native-menu-space")).toBe(false);
    expect(lastNativeVisibility()).toEqual({ visible: true });
    expect(lastNativeBounds()).toEqual({
      bounds: { x: 10, y: 200, width: 800, height: 600 },
    });
    expect(
      mocks.invoke.mock.calls.slice(beforeMenu)
        .filter(([command]) => command === "browser_set_visible")
        .every(([, args]) => args.visible === true),
    ).toBe(true);
    expect(
      mocks.invoke.mock.calls
        .filter(([command]) => command === "browser_set_bounds")
        .every(([, args]) => args.bounds.width === 800),
    ).toBe(true);

    const rtlMenuCall = mocks.invoke.mock.calls.find(
      ([command]) => command === "desktop_popup_rtl_menu",
    );
    expect(
      rtlMenuCall?.[1].items.every(
        (item: Record<string, unknown>) => !("action" in item),
      ),
    ).toBe(true);

    const firstMenuCallCount = mocks.invoke.mock.calls.filter(
      ([command]) => command === "desktop_popup_rtl_menu",
    ).length;
    fireEvent.click(trigger);
    expect(
      mocks.invoke.mock.calls.filter(
        ([command]) => command === "desktop_popup_rtl_menu",
      ),
    ).toHaveLength(firstMenuCallCount);

    await new Promise((resolve) => window.setTimeout(resolve, 230));
    selectedMenuId = "browser-find";
    fireEvent.click(trigger);
    await waitFor(() =>
      expect(screen.getByPlaceholderText("חיפוש בדף")).toBeTruthy(),
    );
    const findForm = screen.getByPlaceholderText("חיפוש בדף").closest("form");
    expect(findForm).not.toBeNull();
    expect(browser!.classList.contains("has-native-find-space")).toBe(true);
    expect(lastNativeVisibility()).toEqual({ visible: true });
    await waitFor(() =>
      expect(lastNativeBounds()).toEqual({
        bounds: { x: 10, y: 246, width: 800, height: 554 },
      }),
    );

    fireEvent.click(within(findForm!).getByRole("button", { name: "סגירת חיפוש בדף" }));
    await waitFor(() =>
      expect(browser!.classList.contains("has-native-find-space")).toBe(false),
    );
  });
});
