// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { coreApi, CoreApiError } from "./coreApi";
import { closeBrowserWorkspace, openBrowserWorkspace } from "./browserWorkspaceLifecycle";
import { closeWorkbenchTerminal, WorkbenchTerminal } from "./WorkbenchTerminal";
import { readPanelSession, writePanelSession } from "./workbenchSession";
import { CanvasPanel } from "./CanvasPanel";
import { WorkbenchFiles } from "./WorkbenchFiles";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./coreApi", async original => ({ ...await original<typeof import("./coreApi")>(), coreApi: vi.fn() }));
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; };
beforeEach(() => { sessionStorage.clear(); vi.resetAllMocks(); });
afterEach(cleanup);

test("browser close waits for a pending open and closes only its workspace", async () => {
  const opening = deferred<any>();
  vi.mocked(invoke).mockImplementation(command => command === "browser_open" ? opening.promise : Promise.resolve(true as never));
  const start = openBrowserWorkspace("source", "persistent", "https://example.test");
  const close = closeBrowserWorkspace("source");
  expect(invoke).not.toHaveBeenCalledWith("browser_close_workspace", expect.anything());
  await expect(openBrowserWorkspace("source", "guest", "https://example.test")).rejects.toThrow("נסגרת");
  opening.resolve({ tabs: [], activeTabId: null }); await start; await close;
  expect(invoke).toHaveBeenLastCalledWith("browser_close_workspace", { workspaceId: "source" });
});

test("terminal close while creation is pending deletes the late process", async () => {
  const created = deferred<any>();
  vi.mocked(coreApi).mockImplementation(method => method === "POST" ? created.promise : Promise.resolve({} as never));
  const view = render(<WorkbenchTerminal tabId="late-terminal" />);
  const closing = closeWorkbenchTerminal("late-terminal"); view.unmount();
  created.resolve({ id: "late-process", running: true, output: "ready" }); await closing;
  expect(coreApi).toHaveBeenCalledWith("DELETE", "/v2/workbench/terminals/late-process", {}, true);
  expect(readPanelSession("late-terminal", null)).toBeNull();
});

test("terminal reload reattaches to the existing process and preserves an unsent command", async () => {
  writePanelSession("terminal-reload", { terminalId: "existing", output: "prior output", command: "Write-Output draft", history: [], cwd: "C:/qa", scroll: 0 });
  vi.mocked(coreApi).mockResolvedValue({ id: "existing", running: true, output: "new output" } as never);
  render(<WorkbenchTerminal tabId="terminal-reload" />);
  await waitFor(() => expect((screen.getByRole("textbox", { name: "פקודת PowerShell" }) as HTMLInputElement).disabled).toBe(false));
  expect((screen.getByRole("textbox", { name: "פקודת PowerShell" }) as HTMLInputElement).value).toBe("Write-Output draft");
  expect(screen.getByLabelText("פלט המסוף").textContent).toBe("prior outputnew output");
  expect(coreApi).not.toHaveBeenCalledWith("POST", "/v2/workbench/terminals", expect.anything(), true);
});

test("a disappeared terminal can be explicitly restarted instead of retrying a stale ID", async () => {
  writePanelSession("terminal-missing", { terminalId: "gone", output: "prior", command: "draft", history: [], cwd: "", scroll: 0 });
  vi.mocked(coreApi).mockImplementation(method => method === "GET" ? Promise.reject(new CoreApiError("terminal_session_not_found", 500)) : Promise.resolve({ id: "new", running: true } as never));
  render(<WorkbenchTerminal tabId="terminal-missing" />);
  await screen.findByRole("alert"); fireEvent.click(screen.getByRole("button", { name: "הפעל מחדש" }));
  await waitFor(() => expect(coreApi).toHaveBeenCalledWith("POST", "/v2/workbench/terminals", {}, true));
  expect((screen.getByRole("textbox", { name: "פקודת PowerShell" }) as HTMLInputElement).value).toBe("draft");
});

test("Canvas fetch ignores an earlier target response and keeps the exact referenced target", async () => {
  const old = deferred<any>();
  const artifact = (id: string) => ({ id, title: id, document: `<h1>${id}</h1>`, buttons: [], closed: false });
  vi.mocked(coreApi).mockImplementation((_method, path) => path.endsWith("/canvases") ? Promise.resolve({ items: [artifact("first"), artifact("second")] } as never) : path.endsWith("/first") ? old.promise : Promise.resolve({ canvas: artifact("second") } as never));
  const view = render(<CanvasPanel sessionId="owner-first" canvasId="first" onAction={() => {}} />);
  await waitFor(() => expect(coreApi).toHaveBeenCalledWith("GET", "/v2/conversations/owner-first/canvases/first"));
  view.rerender(<CanvasPanel sessionId="owner-second" canvasId="second" onAction={() => {}} />);
  // A new referenced target is authoritative even if the prior ID exists in both lists.
  await waitFor(() => expect(coreApi).toHaveBeenCalledWith("GET", "/v2/conversations/owner-second/canvases/second"));
  await act(async () => old.resolve({ canvas: artifact("first") }));
  expect(screen.getByTitle("second").getAttribute("sandbox")).toBe("allow-scripts");
});

test("a later successful directory load cannot hide a file preview failure", async () => {
  const directory = deferred<any>();
  vi.mocked(coreApi).mockImplementation((_method, path) => path.includes("/file?") ? Promise.reject(new Error("preview denied")) : path.includes("&path=") ? directory.promise : Promise.resolve({ root: { name: "qa", path: "C:/qa" }, items: [{ name: "note.md", path: "folder/note.md", kind: "file" }] } as never));
  render(<WorkbenchFiles id="file-error" />);
  fireEvent.click(await screen.findByRole("button", { name: "note.md" }));
  expect((await screen.findByRole("alert")).textContent).toContain("preview denied");
  await act(async () => directory.resolve({ root: { name: "qa", path: "C:/qa" }, items: [] }));
  expect(screen.getByRole("alert").textContent).toContain("preview denied");
});
