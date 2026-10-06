// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { coreApi } from "./coreApi";
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
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.queryByText("מכין קבצים לצירוף…")).toBeNull();
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
  expect(screen.getByRole("alert").textContent).toContain("bad.txt: unavailable");
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
  expect((input as HTMLTextAreaElement).disabled).toBe(true);
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.queryByText("שולח…")).toBeNull();
  await act(async () => { pending.resolve(); });
  send.mockRejectedValueOnce(new Error("offline"));
  fireEvent.change(input, { target: { value: "retry draft" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect((input as HTMLTextAreaElement).value).toBe("retry draft"));
  expect(screen.getByRole("alert").textContent).toContain("ההודעה לא נשלחה: Error: offline");
  const retry = deferred<void>();
  send.mockImplementationOnce(() => retry.promise);
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.queryByRole("alert")).toBeNull();
  await act(async () => { retry.resolve(); });
});

test("a pending voice start is single and cannot attach to a different conversation", async () => {
  const pending = deferred<{session_id:string}>();
  vi.mocked(coreApi).mockImplementation((_method, path) => (path === "/v2/audio/voice" ? pending.promise : Promise.resolve({})) as never);
  vi.mocked(invoke).mockResolvedValue(undefined);
  const props = {attachments:[], onAttachments:vi.fn(), onSend:vi.fn(), onCancel:vi.fn()};
  const view=render(<Composer {...props} conversationId="a" />);
  fireEvent.click(screen.getByRole("button",{name:"הכתבה קולית"}));
  fireEvent.click(screen.getByRole("button",{name:"הכתבה קולית"}));
  expect(vi.mocked(coreApi).mock.calls.filter(([,path])=>path==="/v2/audio/voice")).toHaveLength(1);
  view.rerender(<Composer {...props} conversationId="b" />);
  await act(async()=>pending.resolve({session_id:"voice-a"}));
  expect(coreApi).toHaveBeenCalledWith("POST","/v2/audio/voice/stop",{},true);
  expect(invoke).not.toHaveBeenCalledWith("desktop_show_voice_overlay");
  expect(props.onSend).not.toHaveBeenCalled();
});

test("the voice hotkey obeys the current run and disabled state after rerender", async () => {
  vi.mocked(coreApi).mockResolvedValue({ session_id: "hotkey-voice", active: true });
  vi.mocked(invoke).mockResolvedValue(undefined);
  const props = { attachments: [], onAttachments: vi.fn(), onSend: vi.fn(), onCancel: vi.fn() };
  const view = render(<Composer {...props} />);
  view.rerender(<Composer {...props} running />);
  fireEvent(window, new Event("smarti:voice-hotkey"));
  expect(coreApi).not.toHaveBeenCalledWith("POST", "/v2/audio/voice", {}, true);
  view.rerender(<Composer {...props} disabled />);
  fireEvent(window, new Event("smarti:voice-hotkey"));
  expect(coreApi).not.toHaveBeenCalledWith("POST", "/v2/audio/voice", {}, true);
  view.rerender(<Composer {...props} />);
  await act(async () => { fireEvent(window, new Event("smarti:voice-hotkey")); });
  expect(coreApi).toHaveBeenCalledWith("POST", "/v2/audio/voice", {}, true);
  expect(invoke).toHaveBeenCalledWith("desktop_show_voice_overlay");
});

test.each(["שלום בדיקת הכתבה", ""])("voice completion with transcript %j releases listening and submits only speech", async transcript => {
  const state = {session_id:"voice-finished",active:false,transcript,error:"",cancelled:false};
  vi.mocked(coreApi).mockImplementation((_method,path) => Promise.resolve(path==="/v2/audio/voice" ? {...state,active:true} : state) as never);
  vi.mocked(invoke).mockResolvedValue(undefined);
  const onSend=vi.fn(async()=>{});
  render(<Composer draft="טיוטה שמורה" conversationId="voice-owner" attachments={[]} onAttachments={vi.fn()} onSend={onSend} onCancel={vi.fn()} />);
  fireEvent(window,new Event("smarti:voice-hotkey"));
  await waitFor(()=>expect(vi.mocked(coreApi).mock.calls.some(([,p])=>p==="/v2/audio/voice/status")).toBe(true));
  await waitFor(()=>expect((screen.getByRole("textbox",{name:"הודעה"}) as HTMLTextAreaElement).disabled).toBe(false));
  expect(invoke).toHaveBeenCalledWith("desktop_hide_voice_overlay");
  if(transcript){expect(onSend).toHaveBeenCalledTimes(1);expect(onSend).toHaveBeenCalledWith(transcript,true);}else {
    expect(onSend).not.toHaveBeenCalled();
    expect((screen.getByRole("textbox",{name:"הודעה"}) as HTMLTextAreaElement).value).toBe("טיוטה שמורה");
    expect(screen.queryByRole("alert")).toBeNull();
  }
});
