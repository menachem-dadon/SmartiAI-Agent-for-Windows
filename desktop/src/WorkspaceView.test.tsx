// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { WorkspaceView } from "./ManagementPages";
import { browserTargetCount } from "./browserState";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
let browserStatus: unknown;
let statusFails: boolean;
beforeEach(() => {
  browserStatus = { tabs: [] };
  statusFails = false;
  vi.mocked(invoke).mockReset();
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    if (command === "browser_status") {
      if (statusFails) throw new Error("status unavailable");
      return browserStatus;
    }
    if (command === "core_api") {
      const data = args.request.path === "/v2/settings"
        ? { values: { ui_preferences: {} } } : { root: { path: "fixture" } };
      return { status: 200, body: { data } };
    }
    throw new Error(`Unexpected command ${command}`);
  });
});
afterEach(() => cleanup());

test.each([
  [null, null],
  [undefined, null],
  ["invalid", null],
  [[], null],
  [{ tabs: [] }, 0],
  [{ tabs: [{ tabId: "one" }, { tabId: "two" }] }, 2],
  [{ tabs: ["one"], target_count: 99 }, 1],
  [{ target_count: 0, tabs: 4 }, 0],
  [{ target_count: "3" }, 3],
  [{ tabs: 2 }, 2],
  [{ tabs: "2" }, 2],
  [{}, null],
  [{ tabs: null }, null],
  [{ target_count: "", tabs: {} }, null],
  [{ target_count: "invalid" }, null],
  [{ target_count: Number.NaN }, null],
  [{ target_count: Infinity }, null],
  [{ target_count: -1 }, null],
  [{ target_count: 1.5 }, null],
  [{ target_count: false }, null],
  [{ target_count: Number.MAX_SAFE_INTEGER + 1 }, null],
])("reports a real target count or unknown for %j", (status, expected) => {
  expect(browserTargetCount(status)).toBe(expected);
});

test("renders Rust tab arrays, including zero, and refreshes without NaN", async () => {
  browserStatus = { tabs: [{ tabId: "one" }, { tabId: "two" }] };
  render(<WorkspaceView />);
  await screen.findByText("יעדי דפדפן פעילים: 2");
  browserStatus = { tabs: [] };
  fireEvent.click(screen.getByRole("button", { name: "רענן" }));
  await screen.findByText("יעדי דפדפן פעילים: 0");
  expect(document.body.textContent).not.toContain("NaN");
});

test("a status failure or malformed result is unknown rather than zero", async () => {
  statusFails = true;
  render(<WorkspaceView />);
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("browser_status"));
  expect(screen.getByText(/מספר יעדי הדפדפן אינו זמין/)).toBeTruthy();
  expect(screen.queryByText("יעדי דפדפן פעילים: 0")).toBeNull();
  statusFails = false;
  browserStatus = { tabs: "invalid" };
  fireEvent.click(screen.getByRole("button", { name: "רענן" }));
  await waitFor(() => expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === "browser_status")).toHaveLength(2));
  expect(screen.getByText(/מספר יעדי הדפדפן אינו זמין/)).toBeTruthy();
});

test.each([null, "invalid", []])("handles a malformed top-level browser status %j", async (status) => {
  browserStatus = status;
  render(<WorkspaceView />);
  await waitFor(() => expect(invoke).toHaveBeenCalledWith("browser_status"));
  expect(screen.getByText(/מספר יעדי הדפדפן אינו זמין/)).toBeTruthy();
});

test("retains unavailable status and the real workbench navigation callbacks", async () => {
  browserStatus = { available: false };
  const open = vi.fn();
  render(<WorkspaceView onOpenWorkbench={open} />);
  await screen.findByText("WebView2 אינו זמין כרגע.");
  fireEvent.click(screen.getByRole("button", { name: "פתח קבצים" }));
  fireEvent.click(screen.getByRole("button", { name: "פתח את Smarti Browser" }));
  expect(open.mock.calls).toEqual([["files"], ["browser"]]);
});
