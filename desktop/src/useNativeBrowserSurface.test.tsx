// @vitest-environment jsdom
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
import { useNativeBrowserSurface } from "./useNativeBrowserSurface";
import type { BrowserViewportMode } from "./browserViewport";

let frames: Map<number, FrameRequestCallback>;
let frameId: number;
let bounds: DOMRect;
let resized: () => void;
function Surface({ visible = true, revision, side = false, find = false, resizing = false, tabId = "tab-1", mode = "auto" }: {
  visible?: boolean; revision?: string; side?: boolean; find?: boolean; resizing?: boolean; tabId?: string; mode?: BrowserViewportMode;
}) {
  const { viewportRef } = useNativeBrowserSurface(visible, revision, side, find, tabId, mode);
  return <div className={`workspace ${resizing ? "is-resizing" : ""}`}><aside className="workbench"><div ref={viewportRef} /></aside></div>;
}
const size = (width: number, height: number) => { bounds = { x: 12, y: 110, width, height } as DOMRect; };
const geometry = () => invoke.mock.calls.filter(([name]) => name === "browser_set_bounds").map(([, args]) => args.bounds);
const visibility = () => invoke.mock.calls.filter(([name]) => name === "browser_set_visible").map(([, args]) => args.visible);
const metrics = () => invoke.mock.calls.filter(([name]) => name === "browser_action").map(([, args]) => args.action);
const last = <T,>(items: T[]) => items[items.length - 1];
async function frame() {
  await act(async () => {
    const callbacks = [...frames.values()]; frames.clear();
    callbacks.forEach(callback => callback(0));
  });
}
beforeEach(() => {
  frames = new Map(); frameId = 0; size(800, 600);
  invoke.mockReset(); invoke.mockResolvedValue({});
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal("ResizeObserver", class { constructor(callback: () => void) { resized = callback; } observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(() => bounds);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("coalesces repeated resizes and updates the live page without hiding it", async () => {
  render(<Surface />); await frame(); invoke.mockClear();
  act(() => { size(540, 480); resized(); size(390, 700); resized(); fireEvent.resize(window); });
  expect(geometry()).toHaveLength(0);
  await frame();
  expect(geometry()).toEqual([{ x: 12, y: 110, width: 390, height: 700 }]);
  expect(visibility()).toEqual([]);
  expect(metrics()[0]).toMatchObject({ params: { width: 390, height: 700, mobile: true } });
});

it("does not wait for workspace motion when a window resize changes the breakpoint", async () => {
  const view = render(<Surface />); await frame(); invoke.mockClear();
  size(360, 510);
  view.rerender(<Surface revision="narrow" resizing />);
  await frame();
  expect(geometry()[0].width).toBe(360);
  expect(visibility()).toEqual([]);
});

it("keeps resizing while a mobile CDP request is slow", async () => {
  let finish!: () => void;
  invoke.mockImplementation((name: string) => name === "browser_action" ? new Promise<void>(resolve => { finish = resolve; }) : Promise.resolve());
  size(390, 700); render(<Surface />); await frame();
  size(420, 500); act(() => resized()); await frame();
  expect(geometry()).toHaveLength(2);
  expect(geometry()[1]).toMatchObject({ width: 420, height: 500 });
  expect(metrics()).toHaveLength(1);
  await act(async () => { finish(); });
  expect(metrics()[1].params).toMatchObject({ width: 420, height: 500 });
  await act(async () => { finish(); });
});

it("serializes native requests across effect changes and reveals only current bounds", async () => {
  let finish!: () => void;
  invoke.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
  const view = render(<Surface />); await frame();
  size(390, 600); view.rerender(<Surface find />); await frame();
  expect(geometry()).toHaveLength(1);
  await act(async () => { finish(); });
  expect(visibility()).toEqual([]);
  await frame();
  expect(geometry()[1]).toEqual({ x: 12, y: 156, width: 390, height: 554 });
  expect(visibility()).toEqual([true]);
});

it("continues updating mobile metrics during a drag with slower native acknowledgements", async () => {
  size(390, 700); render(<Surface />); await frame();
  let finish!: () => void;
  invoke.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
  size(410, 680); act(() => resized()); await frame();
  size(430, 660); act(() => resized()); await frame();
  await act(async () => { finish(); });
  expect(last(metrics()).params).toMatchObject({ width: 410, height: 680 });
  await frame();
  expect(last(metrics()).params).toMatchObject({ width: 430, height: 660 });
  expect(visibility()).toEqual([true]);
});

it("fits a short viewport and hides a collapsed surface instead of leaving stale content", async () => {
  size(240, 70); render(<Surface />); await frame();
  expect(geometry()[0]).toMatchObject({ width: 240, height: 70 });
  size(0, 0); act(() => resized()); await frame();
  expect(last(visibility())).toBe(false);
});

it("makes room for a phone side panel and restores the browser when closed", async () => {
  size(390, 600); const view = render(<Surface />); await frame();
  view.rerender(<Surface side />); await frame();
  expect(last(visibility())).toBe(false);
  expect(geometry()).toHaveLength(1);
  view.rerender(<Surface />); await frame();
  expect(last(visibility())).toBe(true);
  expect(last(geometry())?.width).toBe(390);
});

it("applies a newly selected tab's viewport without needing a window resize", async () => {
  size(390, 600); const view = render(<Surface />); await frame();
  view.rerender(<Surface tabId="tab-2" mode="desktop" />); await frame();
  expect(last(metrics())).toMatchObject({ tabId: "tab-2", method: "Emulation.clearDeviceMetricsOverride" });
});
