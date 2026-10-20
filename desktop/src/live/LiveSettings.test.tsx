// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { coreApi } from "../coreApi";
import { LiveSettings } from "./LiveSettings";
vi.mock("../coreApi", () => ({ coreApi: vi.fn() }));
vi.mock("../settingsChanges", () => ({ subscribeSettingsChanges: () => () => {} }));
afterEach(cleanup);
test("the dedicated switch disables every Live control and preserves provider, language and inherited key", async () => {
  let enabled = true, language = "he";
  vi.mocked(coreApi).mockImplementation(async (method, _path, body: any) => {
    if (method === "PATCH") {
      if ("live_enabled" in body.values) enabled = body.values.live_enabled;
      if ("live_language" in body.values) language = body.values.live_language;
    }
    return { enabled, language, provider: "gemini", available: enabled, items: [{ id: "gemini", label: "GEMINI LIVE", model: "gemini-3.8-live", voice: "Kore", voices: ["Kore"], configured: true, inherited: true, masked: "••••shared" }] } as any;
  });
  const { container } = render(<LiveSettings />);
  const toggle = await screen.findByRole("switch", { name: "אפשר מצב Live" });
  await waitFor(() => expect((toggle as HTMLInputElement).checked).toBe(true));
  const key = screen.getByLabelText("מפתח API ללייב") as HTMLInputElement;
  expect(key.placeholder).toBe("••••shared");
  expect(key.closest(".secret-link-row--stacked")?.querySelector(".sds-field-group .sds-icon-button")).toBeTruthy();
  fireEvent.click(toggle);
  await waitFor(() => expect((toggle as HTMLInputElement).checked).toBe(false));
  for (const control of container.querySelectorAll<HTMLInputElement | HTMLButtonElement>("input,button")) if (control !== toggle) expect(control.disabled).toBe(true);
  fireEvent.click(toggle);
  await waitFor(() => expect((toggle as HTMLInputElement).checked).toBe(true));
  expect(key.disabled).toBe(false);
  expect(key.placeholder).toBe("••••shared");
  expect(screen.getByRole("button", { name: /שפת הלייב/ }).textContent).toContain("עברית");
});
test("a failed enable save restores the disabled controls and reports the failure", async () => {
  vi.mocked(coreApi).mockImplementation(async method => {
    if (method === "PATCH") throw new Error("save unavailable");
    return { enabled: false, language: "he", provider: "", available: false, items: [] } as any;
  });
  render(<LiveSettings />);
  const toggle = await screen.findByRole("switch", { name: "אפשר מצב Live" });
  await waitFor(() => expect((toggle as HTMLInputElement).disabled).toBe(false));
  fireEvent.click(toggle);
  await screen.findByText(/save unavailable/);
  expect((toggle as HTMLInputElement).checked).toBe(false);
  expect((screen.getByRole("button", { name: "שפת הלייב" }) as HTMLButtonElement).disabled).toBe(true);
});
