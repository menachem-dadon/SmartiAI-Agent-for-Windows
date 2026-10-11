import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { coreApi } from "./coreApi";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
beforeEach(() => { vi.mocked(invoke).mockReset(); });
const ok = { status: 200, body: { data: { created: true } } };

it("keeps a task creation key after a transport failure but renews it after success", async () => {
  vi.mocked(invoke).mockRejectedValueOnce(new Error("response lost")).mockResolvedValue(ok);
  const body = { action: "create", prompt: "unique task transport" };
  await expect(coreApi("POST", "/v2/management/tasks", body, true)).rejects.toThrow("response lost");
  await coreApi("POST", "/v2/management/tasks", body, true);
  await coreApi("POST", "/v2/management/tasks", body, true);
  const keys = vi.mocked(invoke).mock.calls.map(call => (call[1] as any).request.idempotencyKey);
  expect(keys[0]).toBe(keys[1]);
  expect(keys[2]).not.toBe(keys[1]);
});

it("keeps the key after a server error and drops it after a definitive rejection", async () => {
  vi.mocked(invoke).mockResolvedValueOnce({ status: 500, body: { error: "storage failed" } })
    .mockResolvedValueOnce({ status: 400, body: { error: "invalid draft" } }).mockResolvedValue(ok);
  const body = { action: "create", prompt: "unique task server" };
  await expect(coreApi("POST", "/v2/management/tasks", body, true)).rejects.toThrow();
  await expect(coreApi("POST", "/v2/management/tasks", body, true)).rejects.toThrow();
  await coreApi("POST", "/v2/management/tasks", body, true);
  const keys = vi.mocked(invoke).mock.calls.map(call => (call[1] as any).request.idempotencyKey);
  expect(keys[0]).toBe(keys[1]);
  expect(keys[2]).not.toBe(keys[1]);
});

it("uses an explicit durable submission key unchanged", async () => {
  vi.mocked(invoke).mockResolvedValue(ok);
  await coreApi("POST", "/v2/conversations/owner/runs", { text: "draft" }, "stored-run-key");
  expect((vi.mocked(invoke).mock.calls[0][1] as any).request.idempotencyKey).toBe("stored-run-key");
});
