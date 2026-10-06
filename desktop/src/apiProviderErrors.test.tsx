// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ProviderWorkflow } from "./SettingsManagement";

afterEach(() => cleanup());

it("saves a complete Qwen regional endpoint on blur and rejects invalid drafts", async () => {
  const saves: Array<{ path: string; value: unknown }> = [];
  let modelRequests = 0;
  Object.defineProperty(window, "__TAURI_INTERNALS__", {
    configurable: true,
    value: { invoke: async (_command: string, args: Record<string, unknown>) => {
      const request = args.request as { path: string };
      if (request.path.endsWith("/models")) modelRequests += 1;
      return { status: 200, body: { data: { models: ["qwen-test"], reasoning_options: [] } } };
    } },
  });
  render(<ProviderWorkflow
    values={{ api_mode: "qwen", selected_qwen_model: "qwen-test", favorite_models: [] }}
    secrets={{}} save={async (path, value) => { saves.push({ path, value }); }}
    reload={async () => {}} schema={{ providers: [], secret_help: {} }} theme="dark"
  />);
  await waitFor(() => expect(modelRequests).toBe(1));
  const field = screen.getByPlaceholderText("https://dashscope.aliyuncs.com/compatible-mode/v1");
  fireEvent.change(field, { target: { value: "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/" } });
  expect(saves).toEqual([]);
  fireEvent.blur(field);
  await waitFor(() => expect(saves).toEqual([{ path: "qwen_base_url", value: "https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1" }]));
  await waitFor(() => expect(modelRequests).toBe(2));
  fireEvent.change(field, { target: { value: "invalid endpoint" } });
  fireEvent.blur(field);
  expect(saves).toHaveLength(1);
  expect(screen.getByText(/כתובת API של Qwen אינה תקינה/)).toBeTruthy();
});

it("shows an independently verified key's model catalog warning after saving", async () => {
  Object.defineProperty(window, "__TAURI_INTERNALS__", {
    configurable: true,
    value: { invoke: async (_command: string, args: Record<string, unknown>) => {
      const request = args.request as { path: string };
      const data = request.path.endsWith("/validate")
        ? { ok: true, message: "רשימת המודלים לא נטענה: חיבור הרשת נותק.", models: ["hf-test"] }
        : { models: ["hf-test"], reasoning_options: [] };
      return { status: 200, body: { data } };
    } },
  });
  render(<ProviderWorkflow
    values={{ api_mode: "huggingface", selected_huggingface_model: "hf-test", favorite_models: [] }}
    secrets={{}} save={async () => {}} reload={async () => {}}
    schema={{ providers: [], secret_help: {} }} theme="dark"
  />);
  fireEvent.change(screen.getByPlaceholderText(/מפתח/), { target: { value: "hf-secret" } });
  fireEvent.blur(screen.getByLabelText("מפתח גישה לספק המודל"));
  await waitFor(() => expect(screen.getByText(/המפתח נבדק ונשמר.*רשימת המודלים לא נטענה/)).toBeTruthy());
});

it("ignores an old provider catalog that arrives after switching provider", async () => {
  let resolveOld: (value: unknown) => void = () => {};
  const oldResponse = new Promise((resolve) => { resolveOld = resolve; });
  Object.defineProperty(window, "__TAURI_INTERNALS__", {
    configurable: true,
    value: { invoke: async (_command: string, args: Record<string, unknown>) => {
      const request = args.request as { path: string };
      if (request.path === "/v2/providers/openai/models") return oldResponse;
      return { status: 200, body: { data: { models: ["qwen-new"], reasoning_options: [] } } };
    } },
  });
  const props = { secrets: {}, save: async () => {}, reload: async () => {}, schema: { providers: [], secret_help: {} }, theme: "dark" as const };
  const page = render(<ProviderWorkflow {...props} values={{ api_mode: "openai", favorite_models: [] }} />);
  page.rerender(<ProviderWorkflow {...props} values={{ api_mode: "qwen", favorite_models: [] }} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "בחר מודל" })).toBeTruthy());
  resolveOld({ status: 200, body: { data: { models: ["old-openai-model"], message: "old provider error" } } });
  await oldResponse;
  fireEvent.click(screen.getByRole("button", { name: "בחר מודל" }));
  await waitFor(() => expect(screen.getByRole("option", { name: "qwen-new" })).toBeTruthy());
  expect(screen.queryByRole("option", { name: "old-openai-model" })).toBeNull();
  expect(screen.queryByText("old provider error")).toBeNull();
});
