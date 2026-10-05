// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ProviderPicker } from "./ProviderPicker";

afterEach(cleanup);

test("keyboard opens on the saved provider, selects from all providers and restores focus", async () => {
  const user = userEvent.setup(), onSelect = vi.fn(async () => {});
  render(<ProviderPicker value="openai" onSelect={onSelect} />);
  const trigger = screen.getByRole("button", { name: "ספק המודל: OpenAI" });
  trigger.focus(); await user.keyboard("{ArrowDown}");
  expect(screen.getAllByRole("option")).toHaveLength(18);
  expect(document.activeElement).toBe(screen.getByRole("option", { name: "OpenAI" }));
  await user.keyboard("{End}{Enter}");
  await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
  expect(onSelect).toHaveBeenCalledWith("local");
  expect(document.activeElement).toBe(trigger);
  await user.keyboard("{ArrowDown}{Escape}");
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(document.activeElement).toBe(trigger);
  expect(onSelect).toHaveBeenCalledTimes(1);
});

test("a failed save remains retryable and a pending choice cannot submit twice", async () => {
  let reject!: (error: Error) => void;
  const onSelect = vi.fn(() => new Promise<void>((_resolve, failed) => { reject = failed; }));
  render(<ProviderPicker value="gemini" onSelect={onSelect} />);
  fireEvent.click(screen.getByRole("button", { name: "ספק המודל: Google Gemini" }));
  const choice = screen.getByRole("option", { name: "OpenAI" });
  fireEvent.click(choice); fireEvent.click(choice);
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect((choice as HTMLButtonElement).disabled).toBe(true);
  await act(async () => reject(new Error("isolated save failure")));
  expect(screen.getByRole("alert").textContent).toContain("isolated save failure");
  expect(screen.getByRole("listbox")).toBeTruthy();
  expect((choice as HTMLButtonElement).disabled).toBe(false);
  onSelect.mockResolvedValueOnce(); fireEvent.click(choice);
  await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
  expect(onSelect).toHaveBeenCalledTimes(2);
});
