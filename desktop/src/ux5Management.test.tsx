// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { InputDialog } from "./SettingsManagement";
import { MemoryView } from "./MemoryManagement";
import { TasksView } from "./ManagementPages";
import { coreApi } from "./coreApi";
import { settingDefinitions } from "./managementCatalog";
vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

test("protected email address is routed with other secrets", () => {
  expect(settingDefinitions.find(field => field.path === "email_address")?.control).toBe("secret");
});
test("failed input operation retains draft and prevents duplicate requests", async () => {
  let resolve!: (value: boolean) => void;
  const onConfirm = vi.fn(() => new Promise<boolean>(done => { resolve = done; }));
  render(<InputDialog title="ייבוא" label="נתיב" initial="C:/qa/encrypted.json" onCancel={vi.fn()} onConfirm={onConfirm} />);
  const submit = screen.getByRole("button", { name: "שמירה" });
  fireEvent.click(submit); fireEvent.click(submit);
  expect(onConfirm).toHaveBeenCalledTimes(1);
  await act(async () => resolve(false));
  expect(screen.getByRole("alert").textContent).toContain("הפעולה נכשלה");
  expect((screen.getByRole("textbox", { name: "נתיב" }) as HTMLInputElement).value).toBe("C:/qa/encrypted.json");
  expect((submit as HTMLButtonElement).disabled).toBe(false);
});
test("memory without expiry uses the numeric Core sentinel and retains failed edit", async () => {
  vi.mocked(coreApi).mockImplementation(async method => {
    if (method === "GET") return { items: [], page: 1, pages: 1, stats: {} };
    throw new Error("isolated persistence failure");
  });
  render(<MemoryView />);
  fireEvent.click(screen.getByRole("button", { name: "זיכרון חדש" }));
  const dialog = screen.getByRole("dialog");
  const content = within(dialog).getByRole("textbox");
  fireEvent.change(content, { target: { value: "synthetic retained draft" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "שמירה" }));
  await waitFor(() => expect(within(dialog).getByRole("alert")).toBeTruthy());
  expect(coreApi).toHaveBeenCalledWith("POST", "/v2/management/memories", expect.objectContaining({ action: "create", ttl_hours: 0 }), true);
  expect((content as HTMLTextAreaElement).value).toBe("synthetic retained draft");
});
test("slow task creation cannot create duplicates and failure leaves form open", async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(coreApi).mockImplementation(method => method === "GET" ? Promise.resolve({ items: [] }) : new Promise((_resolve, failed) => { reject = failed; }));
  render(<TasksView />);
  fireEvent.click(screen.getAllByRole("button", { name: "משימה חדשה" })[0]);
  fireEvent.change(screen.getByPlaceholderText("מה Smarti יבצע?"), { target: { value: "synthetic task" } });
  const submit = screen.getByRole("button", { name: "יצירת משימה" });
  fireEvent.click(submit); fireEvent.click(submit);
  expect(vi.mocked(coreApi).mock.calls.filter(call => call[0] === "POST")).toHaveLength(1);
  await act(async () => reject(new Error("isolated failure")));
  expect(screen.getByRole("alert").textContent).toContain("הפעולה נכשלה");
  expect((screen.getByPlaceholderText("מה Smarti יבצע?") as HTMLTextAreaElement).value).toBe("synthetic task");
});
