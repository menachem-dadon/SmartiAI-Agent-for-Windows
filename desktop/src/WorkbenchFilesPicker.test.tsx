// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { invoke } from "@tauri-apps/api/core";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { WorkbenchSurface } from "./WorkbenchPanels";
import { coreApi } from "./coreApi";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
vi.mock("./BrowserPanel", () => ({ BrowserPanel: () => null }));
vi.mock("./CanvasPanel", () => ({ CanvasPanel: () => null }));

let rootPath: string;

beforeEach(() => {
  vi.clearAllMocks();
  rootPath = "C:/workspace";
  vi.mocked(coreApi).mockImplementation(async (method, path, body) => {
    if (method === "PATCH" && path === "/v2/workbench/root") {
      rootPath = (body as { path: string }).path;
      return { name: "selected", path: rootPath } as never;
    }
    if (path === "/v2/workbench/tree?depth=3") {
      return { root: { name: "selected", path: rootPath }, items: [] } as never;
    }
    return { items: [] } as never;
  });
  render(<WorkbenchSurface
    initial={null}
    visible
    restored={{ tabs: [{ id: "files-1", kind: "files", title: "קבצים" }], active: "files-1" }}
    onClose={vi.fn()}
    closeIcon="/close.svg"
    sessionId="test"
    onCanvasAction={vi.fn()}
  />);
});

afterEach(cleanup);

test("folder button opens the native directory picker and loads the chosen root", async () => {
  vi.mocked(invoke).mockResolvedValue("C:/chosen");
  await waitFor(() => expect(screen.getByRole<HTMLInputElement>("textbox", { name: "נתיב תיקיית העבודה" }).value).toBe("C:/workspace"));

  fireEvent.click(screen.getByRole("button", { name: "תיקייה" }));

  await waitFor(() => expect(invoke).toHaveBeenCalledWith("pick_management_path", { kind: "directory" }));
  await waitFor(() => expect(coreApi).toHaveBeenCalledWith("PATCH", "/v2/workbench/root", { path: "C:/chosen" }, true));
  await waitFor(() => expect(screen.getByRole<HTMLInputElement>("textbox", { name: "נתיב תיקיית העבודה" }).value).toBe("C:/chosen"));
});

test("canceling the picker keeps the current root", async () => {
  vi.mocked(invoke).mockResolvedValue(null);
  await waitFor(() => expect(screen.getByRole<HTMLInputElement>("textbox", { name: "נתיב תיקיית העבודה" }).value).toBe("C:/workspace"));

  fireEvent.click(screen.getByRole("button", { name: "תיקייה" }));

  await waitFor(() => expect(invoke).toHaveBeenCalledWith("pick_management_path", { kind: "directory" }));
  expect(coreApi).not.toHaveBeenCalledWith("PATCH", "/v2/workbench/root", expect.anything(), true);
  expect(screen.getByRole<HTMLInputElement>("textbox", { name: "נתיב תיקיית העבודה" }).value).toBe("C:/workspace");
});

test("a typed path can still be applied without opening the picker", async () => {
  const input = await screen.findByRole<HTMLInputElement>("textbox", { name: "נתיב תיקיית העבודה" });
  fireEvent.change(input, { target: { value: "C:/typed" } });
  fireEvent.click(screen.getByRole("button", { name: "החל" }));

  await waitFor(() => expect(coreApi).toHaveBeenCalledWith("PATCH", "/v2/workbench/root", { path: "C:/typed" }, true));
  expect(invoke).not.toHaveBeenCalled();
});
