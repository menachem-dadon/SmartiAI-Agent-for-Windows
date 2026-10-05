// @vitest-environment jsdom
import { Profiler } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { SettingsView } from "./SettingsManagement";
import type { SettingsSection } from "./managementCatalog";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

let values: Record<string, unknown>;
let loadGate: Promise<void> | undefined;
let failLoad: boolean;

beforeEach(() => {
  values = {
    api_mode: "openai", selected_openai_model: "saved-model",
    email_imap_host: "imap.example.test",
    ui_preferences: { settings_show_advanced: true, theme_mode: "dark", keep: "saved" },
  };
  loadGate = undefined;
  failLoad = false;
  vi.mocked(invoke).mockReset();
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    if (command !== "core_api") return null;
    const { method, path, body } = args.request;
    let data: unknown = { items: [] };
    if (path === "/v2/settings") {
      if (method === "GET") {
        if (loadGate) await loadGate;
        if (failLoad) return { status: 503, body: { detail: "temporarily unavailable" } } as any;
      } else if (method === "PATCH") {
        values = { ...values, ...body.values };
      }
      data = { values: structuredClone(values), secrets: {} };
    }
    if (path === "/v2/settings/schema") data = { providers: [], secret_help: {} };
    if (path.endsWith("/models")) data = { models: ["saved-model"] };
    if (path.includes("/reasoning")) data = { reasoning_options: [] };
    if (path.startsWith("/v2/management/logs?")) data = { lines: [], path: "" };
    if (path === "/v2/audio/tts/status") data = { protocol_version: 1, is_playing: false };
    return { status: 200, body: { data } } as any;
  });
});
afterEach(() => cleanup());

const sections: SettingsSection[] = [
  "settings_ai", "settings_security", "settings_tools", "settings_appearance", "settings_advanced",
];
const requests = (method: string, path: string) => vi.mocked(invoke).mock.calls.filter(
  ([command, args]: any) => command === "core_api" && args.request.method === method && args.request.path === path,
);
function view(section: SettingsSection) {
  return <SettingsView section={section} theme="dark" setTheme={() => {}}
    policyOpen={false} setPolicyOpen={() => {}} />;
}

test.each(sections)("%s displays the saved advanced mode on its first populated render", async (section) => {
  let release!: () => void;
  loadGate = new Promise<void>(resolve => { release = resolve; });
  const modes: boolean[] = [];
  render(<Profiler id="settings" onRender={() => {
    const toggle = screen.queryByRole<HTMLInputElement>("switch", { name: "הצג הגדרות מתקדמות" });
    if (toggle) modes.push(toggle.checked);
  }}>{view(section)}</Profiler>);

  expect(document.querySelector("[data-setting-path]")).toBeNull();
  expect(screen.queryByRole("switch", { name: "הצג הגדרות מתקדמות" })).toBeNull();
  expect(screen.getByText("טוען הגדרות…")).toBeTruthy();
  expect(requests("GET", "/v2/providers/gemini/models")).toHaveLength(0);
  await act(async () => { release(); });

  await screen.findByRole("switch", { name: "הצג הגדרות מתקדמות" });
  expect(modes.length).toBeGreaterThan(0);
  expect(modes.every(Boolean)).toBe(true);
  expect(requests("GET", "/v2/settings")).toHaveLength(1);
  expect(requests("PATCH", "/v2/settings")).toHaveLength(0);
  if (section === "settings_ai") {
    await waitFor(() => expect(requests("GET", "/v2/providers/openai/models")).toHaveLength(1));
    expect(requests("GET", "/v2/providers/gemini/models")).toHaveLength(0);
  }
  if (section === "settings_tools") {
    const input = document.querySelector<HTMLInputElement>('[data-setting-path="email_imap_host"] input');
    expect(input?.value).toBe("imap.example.test");
  }
});

test.each([false, undefined])("keeps advanced settings hidden for saved mode %s", async (mode) => {
  values.ui_preferences = { settings_show_advanced: mode };
  render(view("settings_tools"));
  const toggle = await screen.findByRole<HTMLInputElement>("switch", { name: "הצג הגדרות מתקדמות" });
  expect(toggle.checked).toBe(false);
  expect(document.querySelector('[data-setting-path="email_imap_host"]')).toBeNull();
});

test("persists advanced changes, preserves other preferences and retains the mode across categories", async () => {
  const { rerender } = render(view("settings_tools"));
  const toggle = await screen.findByRole<HTMLInputElement>("switch", { name: "הצג הגדרות מתקדמות" });
  fireEvent.click(toggle);
  expect(toggle.checked).toBe(false);
  expect(document.querySelector('[data-setting-path="email_imap_host"]')).toBeNull();
  await waitFor(() => expect(values.ui_preferences).toEqual({
    settings_show_advanced: false, theme_mode: "dark", keep: "saved",
  }));
  rerender(view("settings_security"));
  expect(toggle.checked).toBe(false);
  fireEvent.click(toggle);
  expect(toggle.checked).toBe(true);
  await waitFor(() => expect(values.ui_preferences).toEqual({
    settings_show_advanced: true, theme_mode: "dark", keep: "saved",
  }));
  rerender(view("settings_tools"));
  expect(document.querySelector('[data-setting-path="email_imap_host"]')).toBeTruthy();
  expect(requests("GET", "/v2/settings")).toHaveLength(1);
});

test("retries a failed initial load without exposing default settings", async () => {
  failLoad = true;
  render(view("settings_tools"));
  expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
  expect(document.querySelector("[data-setting-path]")).toBeNull();
  failLoad = false;
  fireEvent.click(screen.getByRole("button", { name: "נסה שוב" }));
  expect((await screen.findByRole<HTMLInputElement>("switch", { name: "הצג הגדרות מתקדמות" })).checked).toBe(true);
  expect(requests("GET", "/v2/settings")).toHaveLength(2);
});
