// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { InterfaceRecovery } from "./InterfaceRecovery";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it("retains a visible accessible recovery action after rendering fails", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  function Broken(): never { throw new Error("private draft must not reach product copy"); }
  render(<InterfaceRecovery><Broken /></InterfaceRecovery>);
  expect(screen.getByRole("alert").textContent).toContain("הממשק לא נטען");
  expect(screen.getByRole("button", { name: "טעינת הממשק מחדש" })).toBeTruthy();
  expect(screen.queryByText(/private draft/)).toBeNull();
});
