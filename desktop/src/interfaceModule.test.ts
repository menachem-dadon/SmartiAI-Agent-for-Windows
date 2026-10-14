import { afterEach, beforeEach, expect, it, vi } from "vitest";

const key = "smarti.desktop.interface-retry.main";
const saved = new Map<string, string>();
let timers: Array<{ callback: () => void; delay: number }>;
let reload: ReturnType<typeof vi.fn>;
let storage: { getItem: ReturnType<typeof vi.fn>; setItem: ReturnType<typeof vi.fn>; removeItem: ReturnType<typeof vi.fn> };
const failure = () => new TypeError("Failed to fetch dynamically imported module: http://localhost/assets/main.js?private-value");

beforeEach(() => {
  vi.resetModules(); saved.clear(); timers = []; reload = vi.fn();
  storage = {
    getItem: vi.fn((name: string) => saved.get(name) ?? null),
    setItem: vi.fn((name: string, value: string) => { saved.set(name, value); }),
    removeItem: vi.fn((name: string) => { saved.delete(name); }),
  };
  vi.stubGlobal("sessionStorage", storage);
  vi.stubGlobal("location", { search: "" });
  vi.stubGlobal("window", {
    location: { reload },
    setTimeout: vi.fn((callback: () => void, delay: number) => { timers.push({ callback, delay }); return timers.length; }),
    clearTimeout: vi.fn(),
  });
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("navigates to a fresh document after a fetch failure instead of repeating the cached failed import", async () => {
  const { loadInterfaceModule } = await import("./interfaceModule");
  const load = vi.fn().mockRejectedValue(failure());
  let settled = false;
  void loadInterfaceModule(load, "entry").then(() => { settled = true; });
  await Promise.resolve(); await Promise.resolve();
  expect(load).toHaveBeenCalledTimes(1);
  expect(settled).toBe(false);
  expect(saved.get(key)).toBe("1");
  expect(timers[0].delay).toBe(400);
  timers[0].callback(); expect(reload).toHaveBeenCalledTimes(1);
  expect(JSON.stringify(vi.mocked(console.warn).mock.calls)).not.toContain("private-value");
});

it("bounds retries across full document reloads and entry/App failures", async () => {
  for (let attempt = 0; attempt < 2; attempt++) {
    vi.resetModules();
    const { recoverInterfaceModule } = await import("./interfaceModule");
    expect(recoverInterfaceModule(failure(), attempt === 0 ? "entry" : "app")).toBe(true);
    // More than one rejection in this document still requests only one reload.
    expect(recoverInterfaceModule(failure(), "app")).toBe(true);
  }
  vi.resetModules();
  const { loadInterfaceModule } = await import("./interfaceModule");
  const error = failure();
  await expect(loadInterfaceModule(() => Promise.reject(error), "entry")).rejects.toBe(error);
  expect(timers).toHaveLength(2);
  expect(saved.get(key)).toBe("2");
});

it("does not replenish the budget when main imports but the first screen is still loading", async () => {
  saved.set(key, "2");
  const { loadInterfaceModule } = await import("./interfaceModule");
  await expect(loadInterfaceModule(() => Promise.resolve({}), "entry")).resolves.toEqual({});
  await expect(loadInterfaceModule(() => Promise.reject(failure()), "app")).rejects.toThrow();
  expect(timers).toHaveLength(0);
});

it("clears the budget after a ready screen and allows an explicit manual reload", async () => {
  saved.set(key, "2");
  const { interfaceReady, reloadInterface, recoverInterfaceModule } = await import("./interfaceModule");
  interfaceReady(); expect(saved.has(key)).toBe(false);
  expect(recoverInterfaceModule(failure(), "entry")).toBe(true);
  reloadInterface();
  expect(window.clearTimeout).toHaveBeenCalled();
  expect(saved.has(key)).toBe(false);
  expect(reload).toHaveBeenCalledTimes(1);
});

it.each(["read", "write"])("retains manual recovery when session storage %s is unavailable", async (operation) => {
  storage[operation === "read" ? "getItem" : "setItem"].mockImplementation(() => { throw new Error("storage denied"); });
  const { recoverInterfaceModule } = await import("./interfaceModule");
  expect(recoverInterfaceModule(failure(), "entry")).toBe(false);
  expect(timers).toHaveLength(0);
});

it("keeps render/evaluation errors visible and never retries unrelated TypeErrors", async () => {
  const { loadInterfaceModule } = await import("./interfaceModule");
  for (const error of [new SyntaxError("bad code"), new TypeError("Cannot read properties of undefined"), new Error("private draft")]) {
    await expect(loadInterfaceModule(() => Promise.reject(error), "app")).rejects.toBe(error);
  }
  expect(timers).toHaveLength(0);
  expect(JSON.stringify(vi.mocked(console.error).mock.calls)).not.toContain("private draft");
});

it("covers stylesheet fetch failures and keeps the voice window budget separate", async () => {
  saved.set(key, "2");
  vi.stubGlobal("location", { search: "?voice-overlay=1" });
  const { recoverInterfaceModule } = await import("./interfaceModule");
  expect(recoverInterfaceModule(new Error("Unable to preload CSS for /assets/voice.css"), "entry")).toBe(true);
  expect(saved.get(key)).toBe("2");
  expect(saved.get("smarti.desktop.interface-retry.voice")).toBe("1");
});

it("does not start a new loop with a corrupted stored retry budget", async () => {
  saved.set(key, "invalid");
  const { recoverInterfaceModule } = await import("./interfaceModule");
  expect(recoverInterfaceModule(failure(), "entry")).toBe(false);
  expect(timers).toHaveLength(0);
});
