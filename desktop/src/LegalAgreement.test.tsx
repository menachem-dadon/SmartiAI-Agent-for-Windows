// @vitest-environment jsdom
import { beforeAll, afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { LEGAL_AGREEMENT_TEXT, LegalAgreement } from "./LegalAgreement";
const { invoke } = vi.hoisted(() => ({ invoke: vi.fn().mockResolvedValue(undefined) }));
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
vi.mock("./WindowTitleBar", () => ({ WindowTitleBar: () => null }));
const status = { accepted:false, version:"test-version", effective_date:"2026-10-08", title:"תנאי שימוש" };
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function() { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function() { this.removeAttribute("open"); };
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("requires an explicit checkbox, preserves all terms and prevents duplicate acceptance", async () => {
  let finish!: () => void;
  const accept = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  render(<LegalAgreement status={status} theme="light" onAccepted={accept} />);
  const button = screen.getByRole("button", {name:"אני מסכים"}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(screen.getByLabelText("מסמך מדיניות פרטיות ותנאי שימוש").textContent).toContain(LEGAL_AGREEMENT_TEXT.replace(/^.*?\n/, ""));
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(button); fireEvent.click(button);
  expect(accept).toHaveBeenCalledTimes(1);
  expect(button.disabled).toBe(true);
  finish();
});

it("keeps the user's confirmation and offers retry after a save failure", async () => {
  const accept = vi.fn().mockRejectedValueOnce(new Error("private exception")).mockResolvedValue(undefined);
  render(<LegalAgreement status={status} theme="dark" onAccepted={accept} />);
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", {name:"אני מסכים"}));
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent).not.toContain("private exception");
  expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole("button", {name:"אני מסכים"}));
  await waitFor(() => expect(accept).toHaveBeenCalledTimes(2));
});

it("rejecting the terms exits the desktop without accepting", () => {
  const accept = vi.fn();
  render(<LegalAgreement status={status} theme="light" onAccepted={accept} />);
  fireEvent.click(screen.getByRole("button", {name:"לא מסכים — סגירה"}));
  expect(invoke).toHaveBeenCalledWith("desktop_quit");
  expect(accept).not.toHaveBeenCalled();
});
