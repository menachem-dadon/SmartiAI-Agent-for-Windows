// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { check } from "@tauri-apps/plugin-updater";
import { coreApi } from "./coreApi";
import { checkForUpdates } from "./updates";
import { UpdateControls } from "./ManagementPages";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: vi.fn() }));
vi.mock("./coreApi", () => ({ coreApi: vi.fn() }));

beforeEach(() => {
  vi.mocked(invoke).mockReset().mockResolvedValue(false);
  vi.mocked(check).mockReset();
  vi.mocked(coreApi).mockReset().mockImplementation(async (_method, path) => {
    if (path === "/v2/management/updates") return { update: null } as any;
    return { values: {} } as any;
  });
});
afterEach(cleanup);

test("unsigned builds discover through Core and record a successful check", async () => {
  expect(await checkForUpdates()).toBeNull();
  expect(check).not.toHaveBeenCalled();
  expect(coreApi).toHaveBeenCalledWith("GET", "/v2/management/updates");
  expect(coreApi).toHaveBeenCalledWith("PATCH", "/v2/settings", { values: {
    updates_last_checked_at: expect.any(String), updates_last_available_version: "",
  } }, true);
});

test("signed builds retain the signature-verifying installer", async () => {
  vi.mocked(invoke).mockResolvedValue(true);
  const installer = { version: "0.88.0", body: "notes", downloadAndInstall: vi.fn() };
  vi.mocked(check).mockResolvedValue(installer as any);
  expect(await checkForUpdates()).toEqual({ version: "0.88.0", body: "notes", installer });
  expect(check).toHaveBeenCalledWith({ timeout: 25_000 });
  expect(coreApi).not.toHaveBeenCalledWith("GET", "/v2/management/updates");
});

test("overlapping manual and automatic requests share one check", async () => {
  const first = checkForUpdates();
  expect(checkForUpdates()).toBe(first);
  await first;
  expect(coreApi).toHaveBeenCalledTimes(2);
});

test.each([false, true])("failed discovery is not persisted (signed=%s) and can be retried", async signed => {
  vi.mocked(invoke).mockResolvedValue(signed);
  if (signed) vi.mocked(check).mockRejectedValueOnce(new Error("feed unavailable")).mockResolvedValue(null);
  else vi.mocked(coreApi).mockRejectedValueOnce(new Error("GitHub unavailable"));
  await expect(checkForUpdates()).rejects.toThrow("unavailable");
  expect(vi.mocked(coreApi).mock.calls.some(([method]) => method === "PATCH")).toBe(false);
  expect(await checkForUpdates()).toBeNull();
});

test("manual button completes in an unsigned build and becomes available again", async () => {
  render(<UpdateControls />);
  fireEvent.click(screen.getByRole("button", { name: "בדוק עדכונים עכשיו" }));
  await screen.findByText("בדיקה אחרונה: עכשיו");
  expect((screen.getByRole("button", { name: "בדוק עדכונים עכשיו" }) as HTMLButtonElement).disabled).toBe(false);
});

test("a GitHub release exposes notes and its page without offering unsigned installation", async () => {
  vi.mocked(coreApi).mockImplementation(async (_method, path) => path === "/v2/management/updates"
    ? { update: { version: "0.88.0", body: "new release", releaseUrl: "https://github.com/menachem-dadon/SmartiAI-Agent-for-Windows/releases/tag/V0.88.0" } } as any
    : { values: {} } as any);
  render(<UpdateControls />);
  fireEvent.click(screen.getByRole("button", { name: "בדוק עדכונים עכשיו" }));
  await screen.findByText("עדכון זמין: גרסה 0.88.0");
  expect(screen.getByText("new release")).toBeTruthy();
  expect(screen.getByRole("button", { name: "עמוד הגרסה" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "הורד והתקן" })).toBeNull();
});

test("manual failure shows the reason and re-enables the button", async () => {
  render(<UpdateControls />);
  await waitFor(() => expect(coreApi).toHaveBeenCalledWith("GET", "/v2/settings"));
  vi.mocked(coreApi).mockRejectedValueOnce(new Error("offline"));
  fireEvent.click(screen.getByRole("button", { name: "בדוק עדכונים עכשיו" }));
  await screen.findByText(/בדיקת העדכון נכשלה:.*offline/);
  expect((screen.getByRole("button", { name: "בדוק עדכונים עכשיו" }) as HTMLButtonElement).disabled).toBe(false);
});
