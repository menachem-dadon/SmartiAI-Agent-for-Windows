// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { BrowserTab } from "./browserState";
import { useBrowserPreview } from "./useBrowserPreview";

const tab: BrowserTab = {
  tabId: "tab-1", workspaceId: "browser-1", targetId: "target-1", webviewLabel: "wv-1",
  profile: "persistent", url: "https://one.test/", title: "One", loading: false,
  active: true, crashed: false, pinned: false, faviconUrl: "", audioPlaying: false,
};
const advance = async (ms: number) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); };
beforeEach(() => { vi.useFakeTimers(); Object.defineProperty(document, "hidden", { configurable: true, value: false }); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

test("captures a real image before collapse and keeps it through metadata updates and transient failures", async () => {
  const capture = vi.fn().mockResolvedValue({ result: { data: "first-image" } });
  const { result, rerender } = renderHook(({ current }) => useBrowserPreview(current, capture), { initialProps: { current: tab } });
  await advance(150);
  expect(result.current.preview?.dataUrl).toBe("data:image/jpeg;base64,first-image");
  rerender({ current: { ...tab, title: "Updated title", faviconUrl: "new.ico" } });
  expect(result.current.preview?.dataUrl).toContain("first-image");
  capture.mockRejectedValueOnce(new Error("temporary failure"));
  await advance(2500);
  expect(result.current.preview?.dataUrl).toContain("first-image");
  capture.mockResolvedValue({ result: { data: "updated-image" } });
  await advance(2500);
  expect(result.current.preview?.dataUrl).toContain("updated-image");
  expect(result.current.error).toBe("");
});

test("discards a late screenshot after navigation and serializes captures for the new target", async () => {
  let finish: (value: { result: { data: string } }) => void = () => {};
  const capture = vi.fn().mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }))
    .mockResolvedValue({ result: { data: "new-page" } });
  const { result, rerender } = renderHook(({ current }) => useBrowserPreview(current, capture), { initialProps: { current: tab } });
  await advance(150);
  rerender({ current: { ...tab, tabId: "tab-2", url: "https://two.test/" } });
  await advance(150);
  expect(capture).toHaveBeenCalledTimes(1);
  await act(async () => { finish({ result: { data: "stale-page" } }); });
  expect(result.current.preview?.tabId).toBe("tab-2");
  expect(result.current.preview?.dataUrl).toContain("new-page");
  expect(capture).toHaveBeenCalledTimes(2);
});

test("clears closed targets immediately and ignores their pending captures", async () => {
  let finish: (value: { result: { data: string } }) => void = () => {};
  const capture = vi.fn(() => new Promise<{ result: { data: string } }>((resolve) => { finish = resolve; }));
  const { result, rerender } = renderHook(({ current }: { current: BrowserTab | null }) => useBrowserPreview(current, capture), { initialProps: { current: tab as BrowserTab | null } });
  await advance(150);
  rerender({ current: null });
  await act(async () => { finish({ result: { data: "closed-page" } }); });
  await advance(5000);
  expect(result.current.preview).toBeNull();
  expect(capture).toHaveBeenCalledTimes(1);
});

test("skips loading and crashed pages, and pauses while the app document is hidden", async () => {
  const capture = vi.fn().mockResolvedValue({ result: { data: "ready" } });
  const { result, rerender } = renderHook(({ current }) => useBrowserPreview(current, capture), { initialProps: { current: { ...tab, loading: true } } });
  await advance(5000);
  expect(capture).not.toHaveBeenCalled();
  rerender({ current: { ...tab, crashed: true } });
  await advance(5000);
  expect(capture).not.toHaveBeenCalled();
  Object.defineProperty(document, "hidden", { configurable: true, value: true });
  rerender({ current: tab });
  await advance(150);
  expect(capture).not.toHaveBeenCalled();
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
  await advance(2500);
  expect(result.current.preview?.dataUrl).toContain("ready");
});

test("rejects an empty capture and retries without displaying a fake image", async () => {
  const capture = vi.fn().mockResolvedValueOnce({ result: { data: "" } }).mockResolvedValue({ result: { data: "retry-image" } });
  const { result } = renderHook(() => useBrowserPreview(tab, capture));
  await advance(150);
  expect(result.current.preview).toBeNull();
  expect(result.current.error).toContain("אינה זמינה");
  await advance(2500);
  expect(result.current.preview?.dataUrl).toContain("retry-image");
});
