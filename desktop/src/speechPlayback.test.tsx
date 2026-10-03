// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { RichMessage } from "./RichMessage";
import { SettingsView } from "./SettingsManagement";
import { Composer } from "./Composer";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
let speech: { protocol_version: number; request_id: string; owner_id: string; is_playing: boolean; error: string };
let failStart: boolean;
let legacyService: boolean;
let activeRun: boolean;
let voice: { session_id: string; active: boolean; status: string; transcript: string; error: string; cancelled: boolean };

beforeEach(() => {
  speech = { protocol_version: 1, request_id: "", owner_id: "", is_playing: false, error: "" };
  failStart = false;
  legacyService = false; activeRun = false;
  voice = { session_id: "voice", active: false, status: "", transcript: "בקשה קולית", error: "", cancelled: false };
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.mocked(invoke).mockReset();
  vi.mocked(invoke).mockImplementation(async (command, args: any) => {
    if (command === "core_restart") { legacyService = false; return { state: "ready" } as any; }
    if (command === "core_status") return { state: "ready" } as any;
    if (command !== "core_api") return null;
    const { path, body } = args.request;
    let data: any = { items: [] };
    if (path === "/v2/audio/tts") {
      if (failStart) return { status: 503, body: { detail: "מנוע ההקראה אינו מותקן" } } as any;
      speech = { protocol_version: 1, request_id: crypto.randomUUID(), owner_id: body.owner_id, is_playing: true, error: "" };
      data = speech;
    }
    if (path === "/v2/audio/tts/status") data = legacyService ? { is_playing: false } : speech;
    if (path.startsWith("/v2/runs?")) data = { items: activeRun ? [{ id: "active" }] : [] };
    if (path === "/v2/audio/tts/stop") {
      if (body.request_id === speech.request_id) speech = { ...speech, is_playing: false };
      data = speech;
    }
    if (path === "/v2/settings") data = { values: { tts_volume: 100, tts_voice_id: "co.il" }, secrets: {} };
    if (path === "/v2/settings/schema") data = { providers: [], secret_help: {} };
    if (path === "/v2/audio/voice") data = { session_id: "voice", active: true, status: "מקשיב" };
    if (path === "/v2/audio/voice/status") data = voice;
    return { status: 200, body: { data: structuredClone(data) } } as any;
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

test("manual answer speech starts, replaces another answer, and stops only its own request", async () => {
  render(<>
    <RichMessage message={{ role: "assistant", content: "תשובה ראשונה", metadata: { run_id: "one" } }} />
    <RichMessage message={{ role: "assistant", content: "תשובה שנייה", metadata: { run_id: "two" } }} />
  </>);
  fireEvent.click(screen.getAllByLabelText("הקרא בקול")[0]);
  await screen.findByLabelText("עצור הקראה");
  expect(speech.owner_id).toBe("run:one");
  fireEvent.click(screen.getByLabelText("הקרא בקול"));
  await waitFor(() => expect(speech.owner_id).toBe("run:two"));
  expect(screen.getAllByLabelText("עצור הקראה")).toHaveLength(1);
  const request = speech.request_id;
  fireEvent.click(screen.getByLabelText("עצור הקראה"));
  await waitFor(() => expect(screen.queryByLabelText("עצור הקראה")).toBeNull());
  expect(invoke).toHaveBeenCalledWith("core_api", expect.objectContaining({ request: expect.objectContaining({
    path: "/v2/audio/tts/stop", body: { request_id: request },
  }) }));
});

test("initial automatic speech connects to the answer and asynchronous engine errors are visible", async () => {
  speech = { protocol_version: 1, request_id: "auto", owner_id: "run:one", is_playing: true, error: "" };
  render(<RichMessage message={{ role: "assistant", content: "תשובה", metadata: { run_id: "one" } }} />);
  await screen.findByLabelText("עצור הקראה");
  speech = { ...speech, is_playing: false, error: "לא ניתן לפתוח התקן שמע" };
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("התקן שמע"), { timeout: 2000 });
  expect(screen.getByLabelText("הקרא בקול")).toBeTruthy();
});

test("an immediate start failure is shown next to the answer", async () => {
  failStart = true;
  render(<RichMessage message={{ role: "assistant", content: "תשובה" }} />);
  fireEvent.click(screen.getByLabelText("הקרא בקול"));
  expect((await screen.findByRole("alert")).textContent).toContain("אינו מותקן");
});

test("settings preview uses the same playback controls and displays errors", async () => {
  render(<SettingsView section="settings_appearance" theme="dark" setTheme={() => {}} policyOpen={false} setPolicyOpen={() => {}} />);
  const preview = await waitFor(() => {
    const field = document.querySelector<HTMLElement>('[data-setting-path="tts_preview"]');
    expect(field).toBeTruthy(); return field!;
  });
  fireEvent.click(within(preview).getByRole("button", { name: "השמע" }));
  await within(preview).findByRole("button", { name: "עצור הקראה" });
  expect(speech.owner_id).toBe("settings:tts-preview");
  fireEvent.click(within(preview).getByRole("button", { name: "עצור הקראה" }));
  await within(preview).findByRole("button", { name: "השמע" });
  failStart = true;
  await act(async () => { fireEvent.click(within(preview).getByRole("button", { name: "השמע" })); });
  expect(within(preview).getByRole("alert").textContent).toContain("אינו מותקן");
});

test("dictation marks the submitted request as voice input", async () => {
  const onSend = vi.fn(async () => {});
  render(<Composer attachments={[]} onAttachments={() => {}} onCancel={() => {}} onSend={onSend} />);
  fireEvent.click(screen.getByLabelText("הכתבה קולית"));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith("בקשה קולית", true), { timeout: 2000 });
});

test("dictation keeps its controls without routine input status text", async () => {
  voice = { ...voice, active: true, status: "מעבד…", transcript: "" };
  const onSend = vi.fn(async () => {});
  render(<Composer attachments={[]} onAttachments={() => {}} onCancel={() => {}} onSend={onSend} />);
  fireEvent.click(screen.getByLabelText("הכתבה קולית"));
  await screen.findByLabelText("הפסקת הכתבה");
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.queryByText(/מקשיב|מעבד…|אפשר לדבר עכשיו/)).toBeNull();
  fireEvent.click(screen.getByLabelText("הפסקת הכתבה"));
  await screen.findByLabelText("הכתבה קולית");
  expect(screen.queryByText("ההאזנה בוטלה")).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(onSend).not.toHaveBeenCalled();
});

test("dictation errors remain visible without submitting a transcript", async () => {
  voice = { ...voice, transcript: "", error: "לא ניתן לפתוח התקן שמע" };
  const onSend = vi.fn(async () => {});
  render(<Composer attachments={[]} onAttachments={() => {}} onCancel={() => {}} onSend={onSend} />);
  fireEvent.click(screen.getByLabelText("הכתבה קולית"));
  expect((await screen.findByRole("alert")).textContent).toContain("לא ניתן לפתוח התקן שמע");
  expect(onSend).not.toHaveBeenCalled();
});

test("an old live Core is refreshed before sending the new schema, only when idle", async () => {
  legacyService = true; activeRun = true;
  render(<RichMessage message={{ role: "assistant", content: "תשובה" }} />);
  fireEvent.click(screen.getByLabelText("הקרא בקול"));
  expect((await screen.findByRole("alert")).textContent).toContain("סיום המשימות");
  expect(invoke).not.toHaveBeenCalledWith("core_restart");
  expect(invoke).not.toHaveBeenCalledWith("core_api", expect.objectContaining({
    request: expect.objectContaining({ path: "/v2/audio/tts" }),
  }));
  activeRun = false;
  fireEvent.click(screen.getByLabelText("הקרא בקול"));
  await screen.findByLabelText("עצור הקראה");
  expect(invoke).toHaveBeenCalledWith("core_restart");
  expect(legacyService).toBe(false);
});
