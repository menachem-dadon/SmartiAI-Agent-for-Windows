// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { SettingsView } from "./SettingsManagement";
import { RichMessage, processRows } from "./RichMessage";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
afterEach(() => { cleanup(); sessionStorage.clear(); vi.mocked(invoke).mockReset(); });

test("advanced settings never expose the removed Hebrew system backup", async () => {
  vi.mocked(invoke).mockImplementation(async (_command, args: any) => {
    const { path } = args.request;
    const data = path === "/v2/settings"
      ? { values: { system_prompt_language: "he", ui_preferences: { settings_show_advanced: true } }, secrets: {} }
      : path === "/v2/settings/schema" ? { providers: [], secret_help: {} }
      : path.startsWith("/v2/management/logs?") ? { lines: [], path: "" } : { items: [] };
    return { status: 200, body: { data } } as any;
  });
  render(<SettingsView section="settings_advanced" theme="dark" setTheme={() => {}}
    policyOpen={false} setPolicyOpen={() => {}} />);
  await screen.findByRole("switch", { name: "הצג הגדרות מתקדמות" });
  expect(screen.queryByText("שפת הנחיית המערכת")).toBeNull();
  expect(screen.queryByRole("button", { name: "החזר את ההנחיה לעברית" })).toBeNull();
  expect(screen.queryByRole("button", { name: "השתמש בהנחיה באנגלית" })).toBeNull();
});

const rawInput = '{"action":"open","query":"כתובת בעברית"}';
const rawOutput = "SUCCESS: Website opened.\nשם האתר בעברית {0}";
const events = [
  { type: "tool_start", tools: [{ action: "web_manager", arguments_text: rawInput, event_id: "t1" }] },
  { type: "tool_finish", results: [{ action: "web_manager", output_text: rawOutput, status: "ok", event_id: "t1" }] },
];

test.each(["he", "en"] as const)("%s conversation metadata keeps Hebrew UI and exact tool frames", language => {
  const { container } = render(<RichMessage message={{ role: "assistant", content: language === "he" ? "האתר נפתח." : "The website is open.",
    metadata: { agent_process: { user_language: language, elapsed_seconds: 2, events } } }} />);
  const frames = container.querySelectorAll(".agent-tool-row pre");
  expect([...frames].map(frame => frame.textContent)).toEqual([rawInput, rawOutput]);
  expect(container.querySelector(".agent-process")?.getAttribute("dir")).toBe("rtl");
  expect(screen.getByText("פלט הכלי")).toBeTruthy();
  expect(container.textContent).toContain("הסתיים web_manager");
  expect(container.textContent).toContain("הורץ כלי 1");
  expect(container.textContent).toContain("סמארטי עבד 2 שנ׳");
  expect(container.textContent).toContain(language === "he" ? "האתר נפתח." : "The website is open.");
});

test("legacy process history retains Hebrew captions and original English payloads", () => {
  const rows = processRows(events);
  expect(rows[0].kind === "tools" && rows[0].label).toBe("הורץ כלי 1");
  expect(rows[0].kind === "tools" && rows[0].tools[0].output).toBe(rawOutput);
  const english = processRows(events, "en");
  expect(english[0].kind === "tools" && english[0].tools[0].query).toBe(rawInput);
  expect(events[1].results?.[0].output_text).toBe(rawOutput);
});

test("English runs keep the Hebrew prefill caption before their first report", () => {
  render(<RichMessage message={{ role: "assistant", content: "", metadata: { user_language: "en" } }}
    active runStatus="running" providerMode="local" stream={{ stage: "prefill", percent: 37, blocks: {} }} />);
  expect(screen.getByText("מעבד הנחיה: 37%")).toBeTruthy();
  expect(screen.queryByText(/Processing prompt/)).toBeNull();
});

test.each(["he", "en"] as const)("%s runs keep the API key wait caption in Hebrew", language => {
  render(<RichMessage message={{ role: "assistant", content: "", metadata: { user_language: language } }}
    active runStatus="waiting_for_input" events={[{ event_id: 1, sequence: 1, created_at: "2026-10-11T12:00:00Z", run_id: "r1", session_id: "s1", event_type: "api_key_required", payload: {} }]} />);
  expect(screen.getByText("ממתין למפתח API")).toBeTruthy();
});

test("English runs keep Hebrew thinking and tool captions without translating model reports", () => {
  const report = "I am checking the current page.";
  const { container } = render(<RichMessage message={{ role: "assistant", content: "", metadata: { user_language: "en" } }}
    active runStatus="running" providerMode="openai" events={[
      { event_id: 1, sequence: 1, created_at: "2026-10-11T12:00:00Z", run_id: "r1", session_id: "s1", event_type: "run_started", payload: { user_language: "en" } },
      { event_id: 2, sequence: 2, created_at: "2026-10-11T12:00:01Z", run_id: "r1", session_id: "s1", event_type: "run_step", payload: { value: { type: "report", user_language: "en", text: report } } },
    ]} stream={{ stage: "thinking", blocks: {} }} />);
  expect(screen.getByText("חושב...")).toBeTruthy();
  expect(container.querySelector(".agent-process")?.getAttribute("dir")).toBe("rtl");
  expect(container.textContent).toContain(report);
  expect(container.textContent).toContain("סמארטי עובד");
});

test("English runs keep Hebrew stopped and empty-frame placeholders", () => {
  const { container } = render(<RichMessage message={{ role: "assistant", content: "Partial English answer.",
    metadata: { user_language: "en", agent_process: { user_language: "en", events: [
      { type: "tool_finish", results: [{ action: "web_manager", status: "ok" }] },
    ] } } }} runStatus="cancelled" />);
  expect(screen.getByText("אין קלט.")).toBeTruthy();
  expect(screen.getByText("אין פלט.")).toBeTruthy();
  expect(screen.getByText("היצירה נעצרה. התשובה שהתקבלה עד העצירה נשמרה.")).toBeTruthy();
  expect(container.textContent).toContain("Partial English answer.");
});
