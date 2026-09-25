// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { Composer } from "./Composer";
import type { PendingAttachment } from "./chatTypes";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./coreApi", () => ({ coreApi: vi.fn(async () => ({})) }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function file(name: string) {
  const value = new File(["sample"], name, { type: "text/plain" });
  Object.defineProperty(value, "arrayBuffer", { value: async () => new ArrayBuffer(6) });
  return value;
}

function Harness({ send = async () => {} }: { send?: () => Promise<void> }) {
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  return <Composer attachments={attachments} onAttachments={setAttachments}
    onSend={send} onCancel={() => {}} />;
}

test("concurrent picker and paste retain both files and block early submission", async () => {
  const first = deferred<string>();
  const second = deferred<string>();
  vi.mocked(invoke).mockImplementation((_name, args) =>
    ((args as { name: string }).name === "first.txt" ? first.promise : second.promise) as never);
  const send = vi.fn(async () => {});
  const { container } = render(<Harness send={send} />);
  const input = screen.getByLabelText("הודעה");
  fireEvent.change(input, { target: { value: "inspect" } });
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [file("first.txt")] } });
  fireEvent.paste(input, { clipboardData: { files: [file("second.txt")] } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(send).not.toHaveBeenCalled();
  await act(async () => { second.resolve("C:/second.txt"); });
  expect(screen.getByLabelText("הסרת second.txt")).toBeTruthy();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(send).not.toHaveBeenCalled();
  await act(async () => { first.resolve("C:/first.txt"); });
  expect(screen.getByLabelText("הסרת first.txt")).toBeTruthy();
  expect(screen.getByLabelText("הסרת second.txt")).toBeTruthy();
  fireEvent.click(screen.getByLabelText("שליחה"));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
});

test("mixed drop preserves successful files when another file fails", async () => {
  vi.mocked(invoke).mockImplementation((_name, args) => {
    const name = (args as { name: string }).name;
    return (name === "bad.txt" ? Promise.reject(new Error("bad.txt: unavailable")) : Promise.resolve(`C:/${name}`)) as never;
  });
  const { container } = render(<Harness />);
  fireEvent.drop(container.querySelector(".composer")!, { dataTransfer: { files: [file("good.txt"), file("bad.txt")] } });
  await waitFor(() => expect(screen.getByLabelText("הסרת good.txt")).toBeTruthy());
  expect(screen.queryByLabelText("הסרת bad.txt")).toBeNull();
  expect(screen.getByRole("status").textContent).toContain("bad.txt: unavailable");
});

test("repeated send events cannot submit one draft twice and failures retain it", async () => {
  const pending = deferred<void>();
  const send = vi.fn(() => pending.promise);
  render(<Harness send={send} />);
  const input = screen.getByLabelText("הודעה");
  fireEvent.change(input, { target: { value: "inspect" } });
  fireEvent.keyDown(input, { key: "Enter" });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(send).toHaveBeenCalledTimes(1);
  await act(async () => { pending.resolve(); });
  send.mockRejectedValueOnce(new Error("offline"));
  fireEvent.change(input, { target: { value: "retry draft" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect((input as HTMLTextAreaElement).value).toBe("retry draft"));
});
