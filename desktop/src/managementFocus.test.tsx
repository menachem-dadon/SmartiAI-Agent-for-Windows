// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ManagementCenter } from "./ManagementCenter";
vi.mock("./SettingsManagement", () => ({ SettingsView: () => null }));
vi.mock("./MemoryManagement", () => ({ MemoryView: () => null }));
vi.mock("./ManagementPages", () => ({ AboutView: () => null, DiagnosticsView: () => null, LogsView: () => null, TasksView: () => null, ToolsView: () => null, UpdateControls: () => null, UsageView: () => null, WorkspaceView: () => null }));
afterEach(cleanup);

it("returns focus to the captured trigger even when inert has already blurred it", () => {
  const trigger = document.createElement("button");
  document.body.append(trigger);
  trigger.focus(); trigger.blur();
  const view = render(<ManagementCenter theme="dark" setTheme={vi.fn()} onClose={vi.fn()} returnFocus={trigger} />);
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "חזרה לצ׳אט" }));
  view.unmount(); expect(document.activeElement).toBe(trigger);
  trigger.remove();
});

it("ignores a hidden or inert chat menu while retaining Escape ownership of a live picker", () => {
  const onClose = vi.fn();
  const menu = document.createElement("div"); menu.innerHTML = '<div hidden><div role="menu">hidden models</div></div><div inert><div role="listbox">inert chat</div></div>';
  document.body.append(menu);
  render(<ManagementCenter theme="dark" setTheme={vi.fn()} onClose={onClose} />);
  fireEvent.keyDown(document, { key: "Escape" }); expect(onClose).toHaveBeenCalledTimes(1);
  const picker = document.createElement("div"); picker.setAttribute("role", "listbox"); menu.append(picker);
  fireEvent.keyDown(document, { key: "Escape" }); expect(onClose).toHaveBeenCalledTimes(1);
  picker.remove(); menu.remove();
});
