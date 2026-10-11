// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { SettingsView } from "./SettingsManagement";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
let values: Record<string, unknown>;
let rejectSave = false;
let holdSave: Promise<void> | undefined;

beforeEach(() => {
  values = { system_prompt_language: "en", api_mode: "local", user_memory: "keep",
    ui_preferences: { settings_show_advanced: true, keep: "saved" } };
  rejectSave = false;
  holdSave = undefined;
  vi.mocked(invoke).mockReset();
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    if (command !== "core_api") return null;
    const { method, path, body } = args.request;
    let data: unknown = { items: [] };
    if (path === "/v2/settings") {
      if (method === "PATCH") {
        if (holdSave) await holdSave;
        if (rejectSave) return { status: 500, body: { detail: "disk unavailable" } } as any;
        values = { ...values, ...body.values };
      }
      data = { values: structuredClone(values), secrets: {} };
    }
    if (path === "/v2/settings/schema") data = { providers: [], secret_help: {} };
    if (path.startsWith("/v2/management/logs?")) data = { lines: [], path: "" };
    if (path === "/v2/audio/tts/status") data = { protocol_version: 1, is_playing: false };
    return { status: 200, body: { data } } as any;
  });
});
afterEach(cleanup);

function view() {
  return <SettingsView section="settings_advanced" theme="dark" setTheme={() => {}}
    policyOpen={false} setPolicyOpen={() => {}} />;
}
const patches = () => vi.mocked(invoke).mock.calls.filter(([command, args]: any) =>
  command === "core_api" && args.request.method === "PATCH" && args.request.path === "/v2/settings");

test("restores Hebrew and returns to English through a scoped persisted PATCH", async () => {
  const { unmount } = render(view());
  fireEvent.click(await screen.findByRole("button", { name: "החזר את ההנחיה לעברית" }));
  await screen.findByRole("button", { name: "השתמש בהנחיה באנגלית" });
  expect((patches()[0][1] as any).request.body).toEqual({ values: { system_prompt_language: "he" } });
  expect(values.user_memory).toBe("keep");
  expect(values.ui_preferences).toEqual({ settings_show_advanced: true, keep: "saved" });
  unmount();
  render(view());
  fireEvent.click(await screen.findByRole("button", { name: "השתמש בהנחיה באנגלית" }));
  await screen.findByRole("button", { name: "החזר את ההנחיה לעברית" });
  expect((patches()[1][1] as any).request.body).toEqual({ values: { system_prompt_language: "en" } });
});

test("failed saves retain the active language and allow retry", async () => {
  rejectSave = true;
  render(view());
  fireEvent.click(await screen.findByRole("button", { name: "החזר את ההנחיה לעברית" }));
  await waitFor(() => expect(document.body.textContent).toContain("השמירה נכשלה"));
  expect(values.system_prompt_language).toBe("en");
  rejectSave = false;
  fireEvent.click(screen.getByRole("button", { name: "החזר את ההנחיה לעברית" }));
  await screen.findByRole("button", { name: "השתמש בהנחיה באנגלית" });
});

test("hides the backup with advanced settings and exposes it through search", async () => {
  values.ui_preferences = { settings_show_advanced: false };
  render(view());
  await screen.findByRole("switch", { name: "הצג הגדרות מתקדמות" });
  expect(screen.queryByRole("button", { name: "החזר את ההנחיה לעברית" })).toBeNull();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "הנחיית מערכת" } });
  fireEvent.click(await screen.findByRole("button", { name: /שפת הנחיית המערכת/ }));
  await screen.findByRole("button", { name: "החזר את ההנחיה לעברית" });
});

test("prevents repeated toggles while persistence is pending", async () => {
  let release!: () => void;
  holdSave = new Promise<void>(resolve => { release = resolve; });
  render(view());
  const button = await screen.findByRole<HTMLButtonElement>("button", { name: "החזר את ההנחיה לעברית" });
  fireEvent.click(button);
  expect(button.disabled).toBe(true);
  fireEvent.click(button);
  expect(patches()).toHaveLength(1);
  release();
  await screen.findByRole("button", { name: "השתמש בהנחיה באנגלית" });
});
