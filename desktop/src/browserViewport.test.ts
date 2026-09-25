import { beforeEach, describe, expect, it, vi } from "vitest";
const { invoke } = vi.hoisted(() => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
import { createBrowserViewportSync, type BrowserViewport } from "./browserViewport";

const viewport: BrowserViewport = { tabId: "phone", width: 390, height: 700, mode: "auto" };
const actions = () => invoke.mock.calls.map(([, args]) => args.action);
beforeEach(() => { invoke.mockReset(); invoke.mockResolvedValue({}); });

describe("responsive page viewport", () => {
  it("uses actual phone dimensions and native DPI, including height-only resizes", async () => {
    const sync = createBrowserViewportSync(vi.fn());
    sync.request(viewport);
    await vi.waitFor(() => expect(actions()).toHaveLength(1));
    expect(actions()[0]).toMatchObject({ tabId: "phone", method: "Emulation.setDeviceMetricsOverride", params: { width: 390, height: 700, mobile: true, deviceScaleFactor: 0 } });
    sync.request({ ...viewport, height: 460 });
    await vi.waitFor(() => expect(actions()).toHaveLength(2));
    expect(actions()[1].params.height).toBe(460);
  });

  it("restores natural desktop sizing above the threshold and avoids redundant desktop calls", async () => {
    const sync = createBrowserViewportSync(vi.fn());
    sync.request({ ...viewport, width: 600 });
    await vi.waitFor(() => expect(actions()).toHaveLength(1));
    sync.request({ ...viewport, width: 601 });
    await vi.waitFor(() => expect(actions()).toHaveLength(2));
    expect(actions()[1].method).toBe("Emulation.clearDeviceMetricsOverride");
    sync.request({ ...viewport, width: 1200 });
    await Promise.resolve();
    expect(actions()).toHaveLength(2);
  });

  it("serializes slow CDP requests and drops intermediate resize dimensions", async () => {
    let finish!: () => void;
    invoke.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
    const sync = createBrowserViewportSync(vi.fn());
    sync.request(viewport);
    sync.request({ ...viewport, width: 410 });
    sync.request({ ...viewport, width: 430, height: 500 });
    expect(actions()).toHaveLength(1);
    finish();
    await vi.waitFor(() => expect(actions()).toHaveLength(2));
    expect(actions()[1].params).toMatchObject({ width: 430, height: 500 });
  });

  it("applies each tab's mode even at identical bounds", async () => {
    const sync = createBrowserViewportSync(vi.fn());
    sync.request(viewport);
    await vi.waitFor(() => expect(actions()).toHaveLength(1));
    sync.request({ ...viewport, tabId: "desktop", mode: "desktop" });
    await vi.waitFor(() => expect(actions()).toHaveLength(2));
    expect(actions()[1]).toMatchObject({ tabId: "desktop", method: "Emulation.clearDeviceMetricsOverride" });
    sync.request({ ...viewport, width: 900, mode: "mobile" });
    await vi.waitFor(() => expect(actions()).toHaveLength(3));
    expect(actions()[2].params.width).toBe(900);
  });

  it("drops pending work on hide and retries a failed target only on a new request", async () => {
    let fail!: (error: Error) => void;
    invoke.mockImplementationOnce(() => new Promise<void>((_, reject) => { fail = reject; }));
    const onError = vi.fn();
    const sync = createBrowserViewportSync(onError);
    sync.request(viewport);
    sync.request({ ...viewport, width: 430 });
    sync.suspend();
    fail(new Error("target closed"));
    await vi.waitFor(() => expect(onError).toHaveBeenCalledOnce());
    expect(actions()).toHaveLength(1);
    sync.request(viewport);
    await vi.waitFor(() => expect(actions()).toHaveLength(2));
  });
});
