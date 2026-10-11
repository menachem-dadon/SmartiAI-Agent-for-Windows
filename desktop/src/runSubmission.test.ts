import { beforeEach, describe, expect, it, vi } from "vitest";
import { coreApi, CoreApiError } from "./coreApi";
import { RunSubmission } from "./runSubmission";

const values = new Map<string, string>();
const storage: Storage = {
  get length() { return values.size; }, clear: () => values.clear(),
  getItem: key => values.get(key) ?? null, setItem: (key, value) => { values.set(key, value); },
  removeItem: key => { values.delete(key); }, key: index => [...values.keys()][index] ?? null,
};
beforeEach(() => { storage.clear(); });
const input = { sessionId: "", text: "private-draft", attachments: [], provider: "local", model: "original-model" };
function client(api: ReturnType<typeof vi.fn>) { return new RunSubmission(api as typeof coreApi, storage); }

describe("durable draft submission identity", () => {
  it("reuses conversation and run key after an ambiguous response and reload", async () => {
    const api = vi.fn().mockResolvedValueOnce({ conversation: { id: "owner" } }).mockRejectedValueOnce(new Error("response lost"));
    await expect(client(api).submit(input)).rejects.toThrow("response lost");
    const firstKey = api.mock.calls[1][3];
    expect(storage.getItem("smarti.pendingRunSubmissions.v1")).not.toContain(input.text);
    api.mockResolvedValueOnce({ run_id: "accepted-run" });
    const result = await client(api).submit({ ...input, model: "changed-after-send" });
    expect(result).toEqual({ run_id: "accepted-run", session_id: "owner" });
    expect(api.mock.calls).toHaveLength(3);
    expect(api.mock.calls[2][3]).toBe(firstKey);
    expect(api.mock.calls[2][2].model_name).toBe("original-model");
  });

  it("reuses the attachment command key if its accepted response is lost", async () => {
    const api = vi.fn().mockResolvedValueOnce({ conversation: { id: "owner" } }).mockRejectedValueOnce(new Error("attachment response lost"));
    const files = { ...input, attachments: [{ path: "C:/private/file.txt", name: "file.txt" }] };
    await expect(client(api).submit(files)).rejects.toThrow();
    const firstKey = api.mock.calls[1][3];
    expect(storage.getItem("smarti.pendingRunSubmissions.v1")).not.toContain(files.attachments[0].path);
    api.mockResolvedValueOnce({ attachment: { handle: "original-handle" } }).mockResolvedValueOnce({ run_id: "run" });
    await client(api).submit(files);
    expect(api.mock.calls[2][3]).toBe(firstKey);
    expect(api.mock.calls[3][2].attachment_handles).toEqual(["original-handle"]);
  });

  it("a deliberate identical send after success is a new operation", async () => {
    const api = vi.fn().mockResolvedValue({ run_id: "run" });
    const sender = client(api);
    await sender.submit({ ...input, sessionId: "owner" });
    await sender.submit({ ...input, sessionId: "owner" });
    expect(api.mock.calls[0][3]).not.toBe(api.mock.calls[1][3]);
  });

  it("keeps different conversations and edited drafts independent", async () => {
    const api = vi.fn().mockRejectedValue(new Error("disconnected"));
    const sender = client(api);
    for (const draft of [{ ...input, sessionId: "a" }, { ...input, sessionId: "b" }, { ...input, sessionId: "a", text: "edited" }]) {
      await expect(sender.submit(draft)).rejects.toThrow();
    }
    expect(new Set(api.mock.calls.map(call => call[3])).size).toBe(3);
  });

  it("a definitive validation rejection releases the pending identity", async () => {
    const api = vi.fn().mockRejectedValueOnce(new CoreApiError("validation", 400)).mockResolvedValueOnce({ run_id: "run" });
    const sender = client(api);
    const draft = { ...input, sessionId: "owner" };
    await expect(sender.submit(draft)).rejects.toThrow("validation");
    await sender.submit(draft);
    expect(api.mock.calls[0][3]).not.toBe(api.mock.calls[1][3]);
  });

  it("coalesces simultaneous sends of the same pending draft", async () => {
    const api = vi.fn().mockResolvedValue({ run_id: "run" });
    const sender = client(api);
    const draft = { ...input, sessionId: "owner" };
    const results = await Promise.all([sender.submit(draft), sender.submit(draft)]);
    expect(results[0]).toEqual(results[1]);
    expect(api).toHaveBeenCalledTimes(1);
  });
});
