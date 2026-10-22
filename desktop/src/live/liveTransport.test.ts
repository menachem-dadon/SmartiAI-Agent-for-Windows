// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { coreApi } from "../coreApi";
import { LiveTransport } from "./liveTransport";

const mock = vi.hoisted(() => ({ invoke: vi.fn(), channels: [] as { onmessage: (value: any) => void }[] }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: mock.invoke,
  Channel: class { onmessage = (_value: any) => {}; constructor() { mock.channels.push(this); } },
}));
vi.mock("../coreApi", async original => ({ ...await original<typeof import("../coreApi")>(), coreApi: vi.fn() }));
const opened: LiveTransport[] = [];
afterEach(() => { opened.forEach(item => item.close()); opened.length = 0; mock.channels.length = 0; mock.invoke.mockReset(); vi.mocked(coreApi).mockReset(); vi.useRealTimers(); });
function transport() { const value = new LiveTransport("a".repeat(32)); opened.push(value); return value; }

test("native audio queue is bounded and stale audio is dropped without replay", async () => {
  mock.invoke.mockImplementation(async command => command === "core_live_open" ? "opaque-native-id" : true);
  const value = transport(); await value.open();
  const results = Array.from({ length: 30 }, (_, sequence) => value.send({ sequence, audio: "AAA=" }));
  expect(mock.invoke.mock.calls.filter(call => call[0] === "core_live_send")).toHaveLength(16);
  value.close();
  const settled = await Promise.allSettled(results);
  expect(settled.filter(result => result.status === "rejected")).toHaveLength(16);
  expect(settled.filter(result => result.status === "fulfilled" && result.value.dropped)).toHaveLength(14);
  expect(mock.invoke.mock.calls.find(call => call[0] === "core_live_open")?.[1]).toMatchObject({ after: 0, sessionId: "a".repeat(32) });
});

test("native reconnect preserves cursor and retries a control with the same sequence", async () => {
  vi.useFakeTimers(); let opens = 0, sends = 0;
  mock.invoke.mockImplementation(async (command, args) => {
    if (command === "core_live_open") return `opaque-${++opens}`;
    if (command === "core_live_send") {
      if (!sends++) throw new Error("temporary socket failure");
      queueMicrotask(() => mock.channels[mock.channels.length - 1].onmessage({ type: "receipt", sequence: args.input.sequence, data: { accepted: true } }));
    }
    return true;
  });
  const value = transport(); await value.open();
  const page = value.next<{ cursor: number }>(0);
  mock.channels[0].onmessage({ type: "page", data: { cursor: 42 } });
  expect((await page).cursor).toBe(42);
  const next = value.next<{ cursor: number }>(42);
  const receipt = value.send({ sequence: 70, text: "one request" });
  await vi.advanceTimersByTimeAsync(400);
  mock.channels[mock.channels.length - 1].onmessage({ type: "page", data: { cursor: 43 } });
  expect((await next).cursor).toBe(43);
  expect((await receipt).accepted).toBe(true);
  expect(mock.invoke.mock.calls.filter(call => call[0] === "core_live_send").map(call => call[1].input.sequence)).toEqual([70, 70]);
  expect(mock.invoke.mock.calls.filter(call => call[0] === "core_live_open")[1][1].after).toBe(42);
});

test("HTTP compatibility retries control receipts and drops ambiguous audio once", async () => {
  vi.useFakeTimers(); mock.invoke.mockRejectedValue(new Error("older host"));
  const value = transport(); await value.open();
  vi.mocked(coreApi).mockRejectedValueOnce(new Error("temporary HTTP failure")).mockResolvedValue({ accepted: true });
  const receipt = value.send({ sequence: 9, text: "same request" });
  await vi.advanceTimersByTimeAsync(200);
  expect((await receipt).accepted).toBe(true);
  expect(vi.mocked(coreApi).mock.calls.map(call => (call[2] as any).sequence)).toEqual([9, 9]);
  vi.mocked(coreApi).mockClear(); vi.mocked(coreApi).mockRejectedValue(new Error("ambiguous audio"));
  expect((await value.send({ sequence: 10, audio: "AAA=" })).dropped).toBe(true);
  expect(coreApi).toHaveBeenCalledOnce();
});
