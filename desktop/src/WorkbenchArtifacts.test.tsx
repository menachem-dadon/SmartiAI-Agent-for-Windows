// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { WorkbenchSurface } from "./WorkbenchPanels";
import { coreApi, CoreApiError } from "./coreApi";
import { invoke } from "@tauri-apps/api/core";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("./coreApi", async (importOriginal) => {
  const original = await importOriginal<typeof import("./coreApi")>();
  return { ...original, coreApi: vi.fn() };
});
vi.mock("./BrowserPanel", () => ({ BrowserPanel: () => null }));
vi.mock("./CanvasPanel", () => ({ CanvasPanel: () => null }));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

function showArtifacts() {
  render(<WorkbenchSurface initial={null} visible onClose={() => {}} closeIcon="/close.svg"
    sessionId="test" onCanvasAction={() => {}}
    restored={{ tabs: [{ id: "artifacts-1", kind: "artifacts", title: "תוצרים" }], active: "artifacts-1" }} />);
}

describe("artifacts panel", () => {
  test.each([
    ["image", "image/png", "img"],
    ["pdf", "application/pdf", "iframe"],
    ["media", "video/mp4", "video"],
  ])("uses the built-in %s viewer", async (kind, mime_type, tag) => {
    vi.mocked(coreApi).mockImplementation(async (method, path) => {
      if (method === "GET" && path === "/v2/workbench/artifacts")
        return { items: [{ name: "sample", path: "sample", size: 4, modified_at: "2026-09-24T12:00:00" }] } as never;
      if (method === "GET" && path === "/v2/workbench/file?path=sample")
        return { name: "sample", path: "sample", kind, mime_type, size: 4, data_url: `data:${mime_type};base64,YQ==` } as never;
      return {} as never;
    });
    showArtifacts();
    fireEvent.click(await within(screen.getByLabelText("רשימת תוצרים")).findByRole("button", { name: /sample/ }));
    await waitFor(() => expect(screen.getByLabelText("תצוגת תוצר").querySelector(tag)).toBeTruthy());
  });

  test("opens a clicked artifact in the built-in viewer and requests the Windows Open With dialog", async () => {
    vi.mocked(coreApi).mockImplementation(async (method, path) => {
      if (method === "GET" && path === "/v2/workbench/artifacts")
        return { items: [{ name: "notes.md", path: "folder/notes.md", size: 12, modified_at: "2026-09-24T12:00:00" }] } as never;
      if (method === "GET" && path === "/v2/workbench/file?path=folder%2Fnotes.md")
        return { name: "notes.md", path: "folder/notes.md", kind: "markdown", mime_type: "text/markdown", size: 12, text: "# שלום" } as never;
      return {} as never;
    });
    showArtifacts();
    const list = screen.getByLabelText("רשימת תוצרים");
    fireEvent.click(await within(list).findByRole("button", { name: /folder\/notes.md/ }));
    await waitFor(() => expect(within(screen.getByLabelText("תצוגת תוצר")).getByRole("heading", { name: "שלום" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "פתח באמצעות" }));
    await waitFor(() => expect(coreApi).toHaveBeenCalledWith("POST", "/v2/workbench/open", { path: "folder/notes.md", action: "open_with" }, true));
  });

  test("keeps Open With available when a file cannot be previewed", async () => {
    vi.mocked(coreApi).mockImplementation(async (method, path) => {
      if (method === "GET" && path === "/v2/workbench/artifacts")
        return { items: [{ name: "large.pdf", path: "large.pdf", size: 100, modified_at: "2026-09-24T12:00:00" }] } as never;
      if (method === "GET" && path.startsWith("/v2/workbench/file?")) throw new Error("preview unavailable");
      return {} as never;
    });
    showArtifacts();
    fireEvent.click(await within(screen.getByLabelText("רשימת תוצרים")).findByRole("button", { name: /large.pdf/ }));
    await waitFor(() => expect(screen.getAllByText("Error: preview unavailable").length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("button", { name: "פתח באמצעות" }));
    await waitFor(() => expect(coreApi).toHaveBeenCalledWith("POST", "/v2/workbench/open", { path: "large.pdf", action: "open_with" }, true));
  });

  test("restarts a stale development Core and retries Open With once", async () => {
    let openAttempts = 0;
    vi.mocked(invoke).mockImplementation(async (command) => {
      if (command === "core_status") return { state: "ready" } as never;
      return {} as never;
    });
    vi.mocked(coreApi).mockImplementation(async (method, path) => {
      if (method === "GET" && path === "/v2/workbench/artifacts")
        return { items: [{ name: "sample.txt", path: "sample.txt", size: 4, modified_at: "2026-09-24T12:00:00" }] } as never;
      if (method === "GET" && path.startsWith("/v2/workbench/file?"))
        return { name: "sample.txt", path: "sample.txt", kind: "text", mime_type: "text/plain", size: 4, text: "text" } as never;
      if (method === "POST" && path === "/v2/workbench/open" && ++openAttempts === 1)
        throw new CoreApiError("Additional properties are not allowed ('action' was unexpected)", 400);
      return {} as never;
    });
    showArtifacts();
    fireEvent.click(await within(screen.getByLabelText("רשימת תוצרים")).findByRole("button", { name: /sample.txt/ }));
    fireEvent.click(screen.getByRole("button", { name: "פתח באמצעות" }));
    await waitFor(() => expect(openAttempts).toBe(2));
    expect(invoke).toHaveBeenCalledWith("core_restart");
    expect(invoke).toHaveBeenCalledWith("core_status");
  });
});
