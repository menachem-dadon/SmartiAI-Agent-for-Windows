// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    callback(0);
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
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
  it("opens the ellipsis menu above WebView2 without hiding or resizing it", async () => {
    render(<BrowserPanel visible />);

    await waitFor(() =>
      expect(lastNativeVisibility()).toEqual({ visible: true }),
    );
    await waitFor(() =>
      expect(lastNativeBounds()).toEqual({
        bounds: { x: 10, y: 200, width: 800, height: 600 },
      }),
    );

    const trigger = screen.getByRole("button", { name: "תפריט דפדפן" });
    const browser = trigger.closest(".embedded-browser");
    expect(browser).not.toBeNull();
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
      mocks.invoke.mock.calls
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

    fireEvent.click(within(findForm!).getByRole("button", { name: "×" }));
    await waitFor(() =>
      expect(browser!.classList.contains("has-native-find-space")).toBe(false),
    );
  });
});
