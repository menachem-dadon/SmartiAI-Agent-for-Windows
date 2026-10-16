// @vitest-environment jsdom
import { createRef } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { coreApi } from "./coreApi";
import { WorkbenchSurface, type WorkbenchHandle } from "./WorkbenchPanels";
import { DesignSystemProvider } from "./design-system";
vi.mock("./coreApi", () => ({ coreApi: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn().mockResolvedValue({}) }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn().mockResolvedValue(() => {}) }));
vi.mock("./BrowserPanel", () => ({ BrowserPanel: () => null }));
afterEach(cleanup);

test("search result opens the real file viewer at the selected path while preserving existing tabs", async () => {
  sessionStorage.clear();
  vi.mocked(coreApi).mockImplementation(async (_method, path) => {
    if (path.startsWith("/v2/workbench/file?")) return { name: "תקציב.md", path: "reports/תקציב.md", kind: "markdown", text: "# תוצר החיפוש", size: 24, mime_type: "text/markdown" };
    return { root: { name: "Smarti", path: "C:/outputs" }, items: [] };
  });
  const ref = createRef<WorkbenchHandle>();
  render(<DesignSystemProvider theme="light"><WorkbenchSurface ref={ref} initial={null} visible restored={{ tabs: [{ id: "existing", kind: "files", title: "קבצים" }], active: "existing" }}
    sessionId="chat" onCanvasAction={() => {}} onClose={() => {}} /></DesignSystemProvider>);
  act(() => { ref.current!.openFile("reports/תקציב.md"); });
  await screen.findByRole("heading", { name: "תוצר החיפוש" });
  expect(screen.getAllByRole("tab")).toHaveLength(2);
  expect(screen.getByRole("tab", { name: "תקציב.md" }).getAttribute("aria-selected")).toBe("true");
  await waitFor(() => expect(coreApi).toHaveBeenCalledWith("GET", `/v2/workbench/file?path=${encodeURIComponent("reports/תקציב.md")}`));
});
