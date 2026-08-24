// @vitest-environment jsdom
import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  capabilityLabels,
  managementNavigation,
  matchingSettings,
  patchForSetting,
  readSetting,
  settingDefinitions,
} from "./managementCatalog";
import {
  PolicyMatrix,
  ProviderWorkflow,
  validateAndPersistProviderKey,
} from "./SettingsManagement";
import { ManagementCenter } from "./ManagementCenter";
import { ApiKeyRequiredDialog } from "./App";
import { ToolsView } from "./ManagementPages";

type InvokeCall = { command: string; args: Record<string, unknown> };
afterEach(() => cleanup());

describe("Point 16C source-derived settings behavior", () => {
  it("keeps the PyQt ManagementCenter registration order and source icon fallbacks", () => {
    expect(managementNavigation.map((group) => group.group)).toEqual([
      "ניהול",
      "הגדרות",
    ]);
    expect(
      managementNavigation[0].items.map((item) => [item.label, item.icon]),
    ).toEqual([
      ["סביבת עבודה ודפדפן", undefined],
      ["נתוני שימוש", "usage"],
      ["כלים וחיבורים", "tools"],
      ["זיכרונות", "memory"],
      ["מרכז משימות", "tasks"],
      ["Smarti Diagnostic", "doctor"],
      ["מעקב למפתחים", undefined],
    ]);
    expect(
      managementNavigation[1].items.map((item) => [item.label, item.icon]),
    ).toEqual([
      ["מודלי AI וספקים", undefined],
      ["אבטחה ופרטיות", "policy"],
      ["כלים ותקשורת", "tools"],
      ["קול, מראה ומערכת", undefined],
      ["מתקדם ומפתחים", undefined],
    ]);
  });

  it("builds nested Core patches and cross-section search without flattening settings", () => {
    const values = {
      ui_preferences: { theme_mode: "dark", keep: true },
      budgets: { daily_token_budget: 0 },
    };
    expect(
      patchForSetting(values, "ui_preferences.theme_mode", "light"),
    ).toEqual({ ui_preferences: { theme_mode: "light", keep: true } });
    expect(patchForSetting(values, "budgets.daily_token_budget", 5000)).toEqual(
      { budgets: { daily_token_budget: 5000 } },
    );
    expect(readSetting(values, "ui_preferences.theme_mode")).toBe("dark");
    expect(
      matchingSettings("settings_ai", "SSL", true).some(
        (item) => item.path === "ssl_trust_mode",
      ),
    ).toBe(true);
    // Source behavior: advanced results remain searchable while hidden; selecting one
    // enables advanced settings before navigation/highlighting.
    expect(
      matchingSettings("settings_ai", "MCP", false).some(
        (item) => item.advanced,
      ),
    ).toBe(true);
    expect(
      settingDefinitions.every(
        (field) => field.label !== field.path && field.help.length > 8,
      ),
    ).toBe(true);
  });

  it("validates against the provider before sending the secret to Core persistence", async () => {
    const calls: Array<{ method: string; path: string; body: unknown }> = [];
    const request = async <T>(
      method: string,
      path: string,
      body?: unknown,
    ): Promise<T> => {
      calls.push({ method, path, body });
      return (
        path.endsWith("/validate")
          ? { ok: true, message: "תקין", models: ["gpt-test"] }
          : {}
      ) as T;
    };
    await validateAndPersistProviderKey({
      provider: "openai",
      secretKey: "openai_api_key",
      secret: "  secret-value  ",
      request,
    });
    expect(calls).toEqual([
      {
        method: "POST",
        path: "/v2/providers/openai/validate",
        body: { secret: "secret-value", local_url: undefined },
      },
      {
        method: "PUT",
        path: "/v2/settings/secrets/openai_api_key",
        body: { value: "secret-value" },
      },
    ]);
  });

  it("renders the PyQt policy matrix as three-state segmented controls and persists the selected capability", async () => {
    const saves: Array<{ path: string; value: unknown }> = [];
    render(
      React.createElement(PolicyMatrix, {
        values: { policy_matrix: { filesystem_write: "ask" } },
        save: async (path: string, value: unknown) => {
          saves.push({ path, value });
        },
      }),
    );
    const rows = screen.getAllByText("שאל בכל פעם");
    expect(rows.length).toBeGreaterThan(1);
    const [firstKey, firstLabel] = Object.entries(capabilityLabels)[0];
    const firstCapability = screen.getByText(firstLabel).closest("section");
    expect(firstCapability?.querySelector("select")).toBeNull();
    fireEvent.click(
      firstCapability!.querySelector(".source-segmented button")!,
    );
    await waitFor(() =>
      expect(saves[0]).toEqual({
        path: "policy_matrix",
        value: expect.objectContaining({ [firstKey]: "allow" }),
      }),
    );
  });

  it("renders PyQt-style search results, enables advanced and navigates to the real target control", async () => {
    const state = {
      values: {
        api_mode: "gemini",
        selected_gemini_model: "gemini-test",
        ui_preferences: { settings_show_advanced: false },
        settings_recent_searches: [] as string[],
        ssl_trust_mode: "system",
        ssl_custom_ca_path: "",
        ssl_filter_setup_completed: false,
      },
      secrets: { gemini_api_key: { configured: true, masked: "••••1234" } },
    };
    const calls: Array<{
      method: string;
      path: string;
      body?: { values?: Record<string, unknown> };
    }> = [];
    (
      HTMLElement.prototype as HTMLElement & { scrollIntoView: () => void }
    ).scrollIntoView = () => {};
    (
      window as typeof window & {
        __TAURI_INTERNALS__: {
          invoke: (
            command: string,
            args?: Record<string, unknown>,
          ) => Promise<unknown>;
        };
      }
    ).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown> = {}) => {
        if (command !== "core_api") return null;
        const request = args.request as {
          method: string;
          path: string;
          body?: { values?: Record<string, unknown> };
        };
        calls.push(request);
        let data: unknown = {};
        if (request.path === "/v2/settings" && request.method === "GET")
          data = state;
        else if (
          request.path === "/v2/settings" &&
          request.method === "PATCH"
        ) {
          Object.assign(state.values, request.body?.values || {});
          data = state;
        } else if (request.path === "/v2/settings/schema")
          data = { providers: [], secret_help: {} };
        else if (request.path === "/v2/audio/tts/voices") data = { items: [] };
        else if (request.path.endsWith("/models"))
          data = { models: ["gemini-test"] };
        else if (request.path.includes("/reasoning"))
          data = { reasoning_options: [] };
        return { status: 200, body: { data } };
      },
    };
    render(
      React.createElement(ManagementCenter, {
        initial: "settings_ai",
        theme: "dark",
        setTheme: () => {},
        onClose: () => {},
      }),
    );
    const search = await screen.findByPlaceholderText("חפש הגדרה");
    fireEvent.change(search, { target: { value: "SSL" } });
    expect(screen.getByText(/נמצאו \d+ תוצאות/)).toBeTruthy();
    expect(screen.queryByText("חיפושים אחרונים")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: /אמון HTTPS ורשת מסוננת/ }),
    );
    await waitFor(() =>
      expect(screen.getByText("המצב הפעיל כעת")).toBeTruthy(),
    );
    expect(screen.queryByText("קובץ תעודה מותאם")).toBeNull();
    expect(
      screen.getByRole("button", { name: "מתקדם ומפתחים" }).className,
    ).toContain("active");
    expect(
      calls.some(
        (call) =>
          call.method === "PATCH" &&
          Boolean(
            (
              call.body?.values?.ui_preferences as
                { settings_show_advanced?: boolean } | undefined
            )?.settings_show_advanced,
          ),
      ),
    ).toBe(true);
  });

  it("wires the rendered Settings secret controls to help, paste, validate, save and delete", async () => {
    const calls: InvokeCall[] = [];
    (
      window as typeof window & {
        __TAURI_INTERNALS__: {
          invoke: (
            command: string,
            args?: Record<string, unknown>,
          ) => Promise<unknown>;
        };
      }
    ).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown> = {}) => {
        calls.push({ command, args });
        if (command !== "core_api") return null;
        const request = args.request as {
          method: string;
          path: string;
          body?: unknown;
        };
        let data: unknown = {};
        if (request.path.endsWith("/models")) data = { models: ["gpt-test"] };
        else if (request.path.includes("/reasoning"))
          data = { reasoning_options: [] };
        else if (request.path.endsWith("/validate"))
          data = { ok: true, message: "תקין", models: ["gpt-test"] };
        return { status: 200, body: { data } };
      },
    };
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { readText: async () => "pasted-secret" },
    });
    let reloads = 0;
    render(
      React.createElement(ProviderWorkflow, {
        values: {
          api_mode: "openai",
          selected_openai_model: "gpt-test",
          favorite_models: [],
        },
        secrets: { openai_api_key: { configured: true, masked: "••••1234" } },
        save: async () => {},
        reload: async () => {
          reloads += 1;
        },
        schema: {
          providers: [
            {
              id: "openai",
              label: "OpenAI",
              secret_key: "openai_api_key",
              help_url: "https://platform.openai.com/api-keys",
              key_instructions: "צור מפתח והעתק אותו.",
              requires_api_key: true,
            },
          ],
          secret_help: {},
        },
        theme: "dark",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "קבל מפתח" }));
    expect(calls[calls.length - 1]).toMatchObject({
      command: "open_chat_link",
      args: { target: "https://platform.openai.com/api-keys", local: false },
    });

    fireEvent.click(
      screen.getByRole("button", { name: "הדבק מפתח מלוח ההעתקה" }),
    );
    await waitFor(() =>
      expect(screen.getByDisplayValue("pasted-secret")).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("button", { name: "בדיקה ושמירה" }));
    await waitFor(() => expect(reloads).toBe(1));
    const coreRequests = calls
      .filter((call) => call.command === "core_api")
      .map(
        (call) =>
          call.args.request as { method: string; path: string; body?: unknown },
      );
    expect(coreRequests).toContainEqual(
      expect.objectContaining({
        method: "POST",
        path: "/v2/providers/openai/validate",
        body: expect.objectContaining({ secret: "pasted-secret" }),
      }),
    );
    expect(coreRequests).toContainEqual(
      expect.objectContaining({
        method: "PUT",
        path: "/v2/settings/secrets/openai_api_key",
        body: { value: "pasted-secret" },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "מחק מפתח שמור" }));
    await waitFor(() => expect(reloads).toBe(2));
    expect(
      calls.some(
        (call) =>
          call.command === "core_api" &&
          (call.args.request as { method: string; path: string }).method ===
            "DELETE" &&
          (call.args.request as { method: string; path: string }).path ===
            "/v2/settings/secrets/openai_api_key",
      ),
    ).toBe(true);
  });

  it("renders the Core-requested key dialog, rejects invalid input, then validates and resumes the waiting run", async () => {
    const calls: InvokeCall[] = [];
    (
      window as typeof window & {
        __TAURI_INTERNALS__: {
          invoke: (
            command: string,
            args?: Record<string, unknown>,
          ) => Promise<unknown>;
        };
      }
    ).__TAURI_INTERNALS__ = {
      invoke: async (command: string, args: Record<string, unknown> = {}) => {
        calls.push({ command, args });
        if (command !== "core_api") return null;
        const request = args.request as {
          method: string;
          path: string;
          body?: { secret?: string };
        };
        let data: unknown = {};
        if (request.path === "/v2/providers/openai/validate")
          data =
            request.body?.secret === "valid-key"
              ? { ok: true, message: "תקין", models: ["gpt-test"] }
              : { ok: false, message: "מפתח לא תקין", models: [] };
        if (request.path === "/v2/runs/run-1/api-key")
          data = { accepted: true };
        return { status: 200, body: { data } };
      },
    };
    let cancelled = false;
    render(
      React.createElement(ApiKeyRequiredDialog, {
        request: {
          runId: "run-1",
          secretKey: "openai_api_key",
          provider: "openai",
          providerLabel: "OpenAI",
          title: "חסר מפתח API",
          message: "יש להזין מפתח כדי להמשיך.",
          helpUrl: "https://platform.openai.com/api-keys",
          keyInstructions: "צור מפתח והעתק אותו.",
        },
        onCancel: () => {
          cancelled = true;
        },
      }),
    );
    expect(screen.getByRole("dialog", { name: "חסר מפתח API" })).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "פתח דף הנפקת מפתחות API" }),
    );
    expect(calls[calls.length - 1]).toMatchObject({
      command: "open_chat_link",
      args: { target: "https://platform.openai.com/api-keys", local: false },
    });
    const input = screen.getByPlaceholderText("הדבק כאן את מפתח ה-API");
    fireEvent.change(input, { target: { value: "invalid-key" } });
    fireEvent.click(screen.getByRole("button", { name: "שמירה והמשך" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("מפתח לא תקין"),
    );
    expect(
      calls.some(
        (call) =>
          call.command === "core_api" &&
          (call.args.request as { path: string }).path ===
            "/v2/runs/run-1/api-key",
      ),
    ).toBe(false);
    fireEvent.change(input, { target: { value: "valid-key" } });
    fireEvent.click(screen.getByRole("button", { name: "שמירה והמשך" }));
    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.command === "core_api" &&
            (call.args.request as { path: string }).path ===
              "/v2/runs/run-1/api-key",
        ),
      ).toBe(true),
    );
    const resumeRequest = calls.find(
      (call) =>
        call.command === "core_api" &&
        (call.args.request as { path: string }).path ===
          "/v2/runs/run-1/api-key",
    )!.args.request as { body: unknown };
    expect(resumeRequest.body).toEqual({
      secret_key: "openai_api_key",
      value: "valid-key",
    });
    fireEvent.click(screen.getByRole("button", { name: "ביטול" }));
    expect(cancelled).toBe(true);
  });

  it("renders complete Skill names as source-style rows instead of splitting a text report into letters", async () => {
    (
      window as typeof window & {
        __TAURI_INTERNALS__: {
          invoke: (
            command: string,
            args?: Record<string, unknown>,
          ) => Promise<unknown>;
        };
      }
    ).__TAURI_INTERNALS__ = {
      invoke: async (command: string, _args: Record<string, unknown> = {}) => {
        if (command !== "core_api") return null;
        return {
          status: 200,
          body: {
            data: {
              builtins: [
                {
                  name: "file_manager",
                  label: "ניהול קבצים",
                  category: "files",
                  category_label: "קבצים",
                  enabled: true,
                },
              ],
              extensions: [
                {
                  kind: "skill",
                  name: "document-review",
                  label: "document-review",
                  source_label: "הותקן ידנית",
                  enabled: true,
                  removable: true,
                },
                {
                  kind: "skill",
                  name: "analyze_project",
                  label: "analyze_project",
                  source_label: "מובנה",
                  enabled: true,
                  removable: false,
                },
              ],
            },
          },
        };
      },
    };
    render(React.createElement(ToolsView, { theme: "dark" }));
    expect(await screen.findByText("document-review")).toBeTruthy();
    expect(screen.getByText("analyze_project")).toBeTruthy();
    expect(screen.getByText("כלים מובנים")).toBeTruthy();
    expect(screen.getByText("מיומנויות מותקנות")).toBeTruthy();
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: /מחק/ })).toHaveLength(1);
  });
});
