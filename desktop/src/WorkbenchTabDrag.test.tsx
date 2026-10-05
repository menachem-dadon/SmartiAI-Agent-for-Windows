// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { WorkbenchSurface } from "./WorkbenchPanels";
import { coreApi } from "./coreApi";
import type { WorkbenchSnapshot } from "./workspaceState";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn(async () => true) }));
vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
vi.mock("./BrowserPanel", () => ({ BrowserPanel: () => <input aria-label="browser state" defaultValue="open page" />, forgetBrowserWorkspaceSession: vi.fn() }));
vi.mock("./CanvasPanel", () => ({ CanvasPanel: () => null }));

const initial: WorkbenchSnapshot = {
  tabs: [
    { id: "files-1", kind: "files", title: "קבצים" },
    { id: "browser-2", kind: "browser", title: "דפדפן" },
    { id: "terminal-3", kind: "terminal", title: "מסוף" },
  ],
  active: "browser-2",
};
let frameId: number;
let frames: Map<number, FrameRequestCallback>;
const rect = (left: number, width: number) => ({ left, right: left + width, top: 10, bottom: 48, width, height: 38, x: left, y: 10, toJSON() {} });
const order = () => screen.getAllByRole("tab").map((tab) => tab.dataset.tabId);
const row = () => screen.getByRole("tablist");
const pointer = (clientX: number, extras = {}) => ({ pointerId: 1, button: 0, clientX, clientY: 25, ...extras });

beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear();
  frames = new Map(); frameId = 0;
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal("PointerEvent", class extends MouseEvent {
    pointerId: number;
    isPrimary: boolean;
    constructor(type: string, options: PointerEventInit = {}) {
      super(type, options);
      this.pointerId = options.pointerId ?? 1;
      this.isPrimary = options.isPrimary ?? true;
    }
  });
  const captured = new WeakMap<HTMLElement, number>();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.getAttribute("role") === "tablist") return rect(100, this.clientWidth || 360);
    if (this.getAttribute("role") === "tab") {
      const wrapper = this.parentElement!;
      const parent = wrapper.parentElement!;
      const index = Array.from(parent.children).indexOf(wrapper);
      return rect(100 + index * 120 - parent.scrollLeft, 120);
    }
    return rect(0, 0);
  });
  Object.defineProperties(HTMLElement.prototype, {
    setPointerCapture: { configurable: true, value: function (this: HTMLElement, id: number) { captured.set(this, id); } },
    hasPointerCapture: { configurable: true, value: function (this: HTMLElement, id: number) { return captured.get(this) === id; } },
    releasePointerCapture: { configurable: true, value: function (this: HTMLElement) { captured.delete(this); } },
  });
  vi.mocked(coreApi).mockImplementation(async (_method, path) => {
    if (path === "/v2/workbench/tree?depth=3") return { root: { name: "test", path: "C:/test" }, items: [] } as any;
    if (path === "/v2/workbench/terminals") return { id: "terminal-session" } as any;
    return { items: [] } as any;
  });
});

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function start(snapshot = initial) {
  const onStateChange = vi.fn<(state: WorkbenchSnapshot) => void>();
  const props = { initial: null, visible: true, restored: snapshot, onStateChange, onClose: vi.fn(), closeIcon: "/close.svg", sessionId: "test", onCanvasAction: vi.fn() };
  const view = render(<WorkbenchSurface {...props} />);
  await waitFor(() => expect((screen.getByRole("textbox", { name: "פקודת PowerShell", hidden: true }) as HTMLInputElement).disabled).toBe(false));
  Object.defineProperties(row(), { clientWidth: { configurable: true, value: 360 }, scrollWidth: { configurable: true, value: snapshot.tabs.length * 120 } });
  return { ...view, props, onStateChange };
}

function drag(from: number, toX: number) {
  const source = screen.getAllByRole("tab")[from];
  fireEvent.pointerDown(source, pointer(160 + from * 120));
  fireEvent.pointerMove(row(), pointer(toX));
  return source;
}

test("shares one browser controller across browser workbench entries", async () => {
  await start({ ...initial, tabs: [...initial.tabs, { id: "browser-4", kind: "browser", title: "דפדפן נוסף" }] });
  const browser = screen.getByRole("textbox", { name: "browser state" });
  fireEvent.change(browser, { target: { value: "retained page" } });
  expect(document.querySelectorAll('[aria-label="browser state"]')).toHaveLength(1);
  fireEvent.click(screen.getByRole("tab", { name: /דפדפן נוסף/ }));
  expect(screen.getByRole("textbox", { name: "browser state" })).toBe(browser);
  fireEvent.click(screen.getByRole("button", { name: "סגירת דפדפן" }));
  expect(screen.getByRole("textbox", { name: "browser state" })).toBe(browser);
  expect((browser as HTMLInputElement).value).toBe("retained page");
});

describe("Workbench pointer tab sorting", () => {
  test.each([[0, 425, ["browser-2", "terminal-3", "files-1"]], [2, 135, ["terminal-3", "files-1", "browser-2"]]])(
    "moves tab %i in the physical drag direction and preserves the active panel", async (index, x, expected) => {
      const { onStateChange } = await start();
      const browser = screen.getByRole("textbox", { name: "browser state" });
      fireEvent.change(browser, { target: { value: "unsaved page state" } });
      const source = drag(index as number, x as number);
      expect(source.classList.contains("is-dragging")).toBe(true);
      expect(row().querySelector("[data-drop-side]")).toBeTruthy();
      fireEvent.pointerUp(row(), pointer(x as number));
      // Browsers emit a click after the pointer sequence, even after a drag.
      fireEvent.click(source, { detail: 1 });
      expect(order()).toEqual(expected);
      expect(onStateChange).toHaveBeenLastCalledWith({ tabs: expect.any(Array), active: "browser-2" });
      expect(screen.getByRole("textbox", { name: "browser state" })).toBe(browser);
      expect((browser as HTMLInputElement).value).toBe("unsaved page state");
      expect(vi.mocked(coreApi).mock.calls.filter(([method, path]) => method === "POST" && path === "/v2/workbench/terminals")).toHaveLength(1);
      expect(vi.mocked(coreApi).mock.calls.some(([method]) => method === "DELETE")).toBe(false);
      expect(frames.size).toBe(0);
      expect(source.hasPointerCapture(1)).toBe(false);
    },
  );

  test("treats small movement as a normal tab click and excludes the close control", async () => {
    await start();
    const source = drag(0, 163);
    fireEvent.pointerUp(row(), pointer(163));
    fireEvent.click(source, { detail: 1 });
    expect(source.getAttribute("aria-selected")).toBe("true");
    expect(order()).toEqual(initial.tabs.map((tab) => tab.id));
    const close = screen.getByRole("button", { name: "סגירת קבצים" });
    fireEvent.pointerDown(close, pointer(180));
    fireEvent.pointerMove(row(), pointer(400));
    expect(row().classList.contains("is-dragging")).toBe(false);
    fireEvent.click(close, { detail: 1 });
    expect(order()).toEqual(["browser-2", "terminal-3"]);
  });

  test.each(["escape", "pointercancel", "lostpointercapture", "blur", "hide", "outside"])(
    "cancels a drag on %s and permits the next gesture", async (reason) => {
      const { rerender, props } = await start();
      const source = drag(0, 425);
      if (reason === "escape") fireEvent.keyDown(window, { key: "Escape" });
      if (reason === "pointercancel") fireEvent.pointerCancel(row(), pointer(425));
      if (reason === "lostpointercapture") fireEvent.lostPointerCapture(row(), pointer(425));
      if (reason === "blur") fireEvent.blur(window);
      if (reason === "hide") rerender(<WorkbenchSurface {...props} visible={false} />);
      fireEvent.pointerUp(row(), pointer(425, reason === "outside" ? { clientY: 100 } : {}));
      fireEvent.click(source, { detail: 1 });
      expect(order()).toEqual(initial.tabs.map((tab) => tab.id));
      expect(frames.size).toBe(0);
      expect(row().querySelector("[data-drop-side]")).toBeNull();
      if (reason === "hide") rerender(<WorkbenchSurface {...props} />);
      drag(0, 425);
      fireEvent.pointerUp(row(), pointer(425));
      expect(order()).toEqual(["browser-2", "terminal-3", "files-1"]);
    },
  );

  test("ignores secondary buttons and other pointers during a drag", async () => {
    await start();
    const source = screen.getAllByRole("tab")[0];
    fireEvent.pointerDown(source, pointer(160, { button: 2 }));
    fireEvent.pointerMove(row(), pointer(425));
    expect(row().classList.contains("is-dragging")).toBe(false);
    drag(0, 425);
    fireEvent.pointerUp(row(), pointer(425, { pointerId: 2 }));
    expect(order()).toEqual(initial.tabs.map((tab) => tab.id));
    expect(row().classList.contains("is-dragging")).toBe(true);
    fireEvent.pointerUp(row(), pointer(425));
    expect(order()).toEqual(["browser-2", "terminal-3", "files-1"]);
  });

  test("allows closing a tab after cancellation without a synthetic click", async () => {
    await start();
    drag(0, 425);
    fireEvent.pointerCancel(row(), pointer(425));
    const close = screen.getByRole("button", { name: "סגירת קבצים" });
    fireEvent.pointerDown(close, pointer(180));
    fireEvent.pointerUp(close, pointer(180));
    fireEvent.click(close, { detail: 1 });
    expect(order()).toEqual(["browser-2", "terminal-3"]);
  });

  test("releases pointer capture and the scrolling loop when unmounted", async () => {
    const { unmount } = await start();
    const source = drag(0, 425);
    expect(frames.size).toBe(1);
    unmount();
    expect(source.hasPointerCapture(1)).toBe(false);
    expect(frames.size).toBe(0);
  });

  test("scrolls an overflowing strip at the edge and emits a restorable order", async () => {
    const snapshot: WorkbenchSnapshot = { ...initial, tabs: [...initial.tabs, { id: "files-4", kind: "files", title: "קבצים 4" }] };
    const { onStateChange, unmount } = await start(snapshot);
    drag(0, 455);
    // Transformed content must never allow the scrolling range to grow mid-drag.
    Object.defineProperty(row(), "scrollWidth", { configurable: true, value: 1000 });
    for (let tick = 0; tick < 16; tick++) act(() => {
      const callbacks = [...frames.values()]; frames.clear();
      callbacks.forEach((callback) => callback(tick * 16));
    });
    expect(row().scrollLeft).toBe(120);
    fireEvent.pointerUp(row(), pointer(455));
    expect(order()).toEqual(["browser-2", "terminal-3", "files-4", "files-1"]);
    const saved = onStateChange.mock.lastCall![0];
    unmount();
    await start(saved);
    expect(order()).toEqual(saved.tabs.map((tab) => tab.id));
    expect(screen.getAllByRole("tab").find((tab) => tab.getAttribute("aria-selected") === "true")?.dataset.tabId).toBe("browser-2");
  });
});
