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

test("mount reads a cached status with no automatic check or credential input", async () => {
  api.mockResolvedValue({ state: "disconnected", message: "cancelled verbose details" });
  render(<SubscriptionConnection {...props()} />);
  await screen.findByText("לא מחובר");
  expect(screen.queryByText("cancelled verbose details")).toBeNull();
  expect(screen.getByRole("button", { name: "חבר לסמארטי" })).toBeTruthy();
  expect(document.querySelector("input")).toBeNull();
  expect(api).toHaveBeenCalledTimes(1);
  expect(api.mock.calls[0][0]).toBe("GET");
});

test("a blocked provider retains a useful error with no official login button", async () => {
  api.mockResolvedValue({ state: "policy_conflict", message: "כלי הספק אינם מבודדים" });
  render(<SubscriptionConnection {...props(google)} />);
  await screen.findByText("כלי הספק אינם מבודדים");
  expect(screen.queryByRole("button", { name: "כניסה בכלי הרשמי" })).toBeNull();
});

test("a connected Antigravity has compact status, no quota or onboarding button", async () => {
  api.mockResolvedValue({ state: "connected", message: "verbose connected", quota: { available: true, groups: [
    { name: "Gemini Models", buckets: [{ window: "weekly", remaining_fraction: .85 }] },
  ] } });
  render(<SubscriptionConnection {...props(google)} />);
  await screen.findByText("מחובר");
  expect(screen.queryByText("verbose connected")).toBeNull();
  expect(screen.queryByText(/85%/)).toBeNull();
  expect(screen.queryByRole("button", { name: "כניסה בכלי הרשמי" })).toBeNull();
  expect(screen.getByRole("button", { name: "בדוק חיבור" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "נתק מסמארטי" })).toBeTruthy();
});

test("the token route retains instructions without secret capture or login", async () => {
  api.mockResolvedValue({ state: "disconnected", message: "offline" });
  render(<SubscriptionConnection {...props()} strategy="setup_token_env" />);
  await screen.findByText("לא מחובר");
  expect(screen.getByText("claude setup-token")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "כניסה בכלי הרשמי" })).toBeNull();
  expect(document.querySelector("input")).toBeNull();
});

test("a late status cannot overwrite another provider", async () => {
  let resolve!: (value: unknown) => void;
  api.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  api.mockResolvedValue({ state: "connected", message: "Google current" });
  const view = render(<SubscriptionConnection {...props()} />);
  view.rerender(<SubscriptionConnection {...props(google)} />);
  await screen.findByText("מחובר");
  await act(async () => resolve({ state: "account_ineligible", message: "Claude stale" }));
  expect(screen.queryByText("Claude stale")).toBeNull();
});

test("login is deduplicated and cancellation returns to a quiet disconnected state", async () => {
  api.mockResolvedValueOnce({ state: "disconnected", message: "offline" });
  api.mockResolvedValueOnce({ id: "operation-1", state: "running", message: "waiting" });
  api.mockResolvedValueOnce({ state: "cancelled", message: "ההתחברות בוטלה" });
  render(<SubscriptionConnection {...props()} />);
  await screen.findByText("לא מחובר");
  const login = screen.getByRole("button", { name: "כניסה בכלי הרשמי" });
  fireEvent.click(login); fireEvent.click(login);
  await screen.findByRole("button", { name: "בטל" });
  expect(api.mock.calls.filter(call => String(call[1]).endsWith("/login"))).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "בטל" }));
  await screen.findByText("לא מחובר");
  expect(screen.queryByText("ההתחברות בוטלה")).toBeNull();
  expect(api.mock.calls[2][1]).toContain("/operations/operation-1/cancel");
});

test("check failure releases the button for retry", async () => {
  api.mockResolvedValueOnce({ state: "disconnected", message: "offline" });
  api.mockRejectedValueOnce(new Error("isolated failure"));
  render(<SubscriptionConnection {...props()} />);
  await screen.findByText("לא מחובר");
  fireEvent.click(screen.getByRole("button", { name: "חבר לסמארטי" }));
  await screen.findByText(/isolated failure/);
  await waitFor(() => expect((screen.getByRole("button", { name: "חבר לסמארטי" }) as HTMLButtonElement).disabled).toBe(false));
});

test("lost operations stop polling and release controls", async () => {
  vi.useFakeTimers();
  api.mockResolvedValueOnce({ state: "disconnected", message: "offline" });
  api.mockResolvedValueOnce({ id: "old-operation", state: "running", message: "waiting" });
  api.mockRejectedValueOnce(Object.assign(new Error("not_found"), { status: 404 }));
  render(<SubscriptionConnection {...props()} />);
  await act(async () => {});
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "כניסה בכלי הרשמי" })));
  await act(async () => vi.advanceTimersByTimeAsync(1100));
  expect(screen.queryByRole("button", { name: "בטל" })).toBeNull();
  expect((screen.getByRole("button", { name: "חבר לסמארטי" }) as HTMLButtonElement).disabled).toBe(false);
  await act(async () => vi.advanceTimersByTimeAsync(10000));
  expect(api).toHaveBeenCalledTimes(3);
});
