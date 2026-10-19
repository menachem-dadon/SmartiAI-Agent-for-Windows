// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { SubscriptionConnection } from "./SubscriptionConnection";
import { coreApi } from "./coreApi";

vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
const api = vi.mocked(coreApi);
const claude = "anthropic_claude_code_signin", google = "google_antigravity_signin";
beforeEach(() => api.mockReset());
afterEach(() => { cleanup(); vi.useRealTimers(); });
const props = (provider = claude) => ({ provider, strategy: "claude_login", onChanged: vi.fn(async () => {}), onStrategyChange: vi.fn(async () => {}) });

test("Claude uses official login controls with no credential input", async () => {
  api.mockResolvedValue({ state: "disconnected", message: "יש להתחבר למנוי מתאים" });
  render(<SubscriptionConnection {...props()} />);
  await screen.findByText("יש להתחבר למנוי מתאים");
  expect(screen.getByRole("button", { name: "התחבר עם Claude Code" })).toBeTruthy();
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(document.querySelector('input[type="password"]')).toBeNull();
  expect(api).toHaveBeenCalledTimes(1);
  expect(api.mock.calls[0][0]).toBe("GET");
});

test("Antigravity displays the real isolation blocker and never presents a working login", async () => {
  api.mockResolvedValue({ state: "policy_conflict", message: "כלי הספק אינם מבודדים" });
  render(<SubscriptionConnection {...props(google)} />);
  await screen.findByText("כלי הספק אינם מבודדים");
  expect(screen.queryByRole("button", { name: /התחבר/ })).toBeNull();
  expect(screen.getByText(/גילוי המודלים זמין לצורך אבחון/)).toBeTruthy();
});

test("token strategy has instructions and no secret capture or automatic login", async () => {
  api.mockResolvedValue({ state: "disconnected", message: "חסר אסימון בסביבה" });
  render(<SubscriptionConnection {...props()} strategy="setup_token_env" />);
  await screen.findByText("חסר אסימון בסביבה");
  expect(screen.getByText("claude setup-token")).toBeTruthy();
  expect(screen.getByText("CLAUDE_CODE_OAUTH_TOKEN")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "התחבר עם Claude Code" })).toBeNull();
  expect(document.querySelector("input")).toBeNull();
});

test("a response for a previously selected provider cannot overwrite the current connection", async () => {
  let resolve!: (value: unknown) => void;
  api.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  api.mockResolvedValue({ state: "policy_conflict", message: "Google current" });
  const view = render(<SubscriptionConnection {...props()} />);
  view.rerender(<SubscriptionConnection {...props(google)} />);
  await screen.findByText("Google current");
  await act(async () => resolve({ state: "connected", message: "Claude stale" }));
  expect(screen.queryByText("Claude stale")).toBeNull();
});

test("login is deduplicated while pending and exposes operation cancellation", async () => {
  api.mockResolvedValueOnce({ state: "disconnected", message: "offline" });
  api.mockResolvedValueOnce({ id: "operation-1", state: "running", message: "השלם כניסה" });
  api.mockResolvedValueOnce({ state: "cancelled", message: "בוטל" });
  const callbacks = props();
  render(<SubscriptionConnection {...callbacks} />);
  await screen.findByText("offline");
  const login = screen.getByRole("button", { name: "התחבר עם Claude Code" });
  fireEvent.click(login); fireEvent.click(login);
  await screen.findByRole("button", { name: "בטל התחברות" });
  expect(api.mock.calls.filter(call => String(call[1]).endsWith("/login"))).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "בטל התחברות" }));
  await screen.findByText("בוטל");
  expect(api.mock.calls[2][1]).toContain("/operations/operation-1/cancel");
  expect(callbacks.onChanged).toHaveBeenCalledTimes(1);
});

test("a failed connection action preserves the controls for retry", async () => {
  api.mockResolvedValueOnce({ state: "disconnected", message: "offline" });
  api.mockRejectedValueOnce(new Error("isolated failure"));
  render(<SubscriptionConnection {...props()} />);
  await screen.findByText("offline");
  fireEvent.click(screen.getByRole("button", { name: "בדוק חיבור" }));
  await screen.findByText(/isolated failure/);
  await waitFor(() => expect((screen.getByRole("button", { name: "בדוק חיבור" }) as HTMLButtonElement).disabled).toBe(false));
});

test("a lost operation after Core restart stops polling and releases login controls", async () => {
  vi.useFakeTimers();
  api.mockResolvedValueOnce({ state: "disconnected", message: "offline" });
  api.mockResolvedValueOnce({ id: "old-operation", state: "running", message: "waiting" });
  api.mockRejectedValueOnce(Object.assign(new Error("connection_operation_not_found"), { status: 404 }));
  render(<SubscriptionConnection {...props()} />);
  await act(async () => {});
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "התחבר עם Claude Code" })));
  await act(async () => vi.advanceTimersByTimeAsync(1100));
  expect(screen.queryByRole("button", { name: "בטל התחברות" })).toBeNull();
  expect((screen.getByRole("button", { name: "התחבר עם Claude Code" }) as HTMLButtonElement).disabled).toBe(false);
  await act(async () => vi.advanceTimersByTimeAsync(10000));
  expect(api).toHaveBeenCalledTimes(3);
});
