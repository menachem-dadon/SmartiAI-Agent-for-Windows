// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { quotaWindows, useProviderQuota } from "./ProviderQuota";
import { coreApi } from "./coreApi";
vi.mock("./coreApi", () => ({ coreApi: vi.fn(), encodePath: encodeURIComponent }));
afterEach(() => { cleanup(); vi.mocked(coreApi).mockReset(); vi.useRealTimers(); });
const agy = "google_antigravity_signin", claude = "anthropic_claude_code_signin";
function Harness({ provider }: { provider: string }) {
  const quota = useProviderQuota(provider, "gemini-3.8-flash-high");
  return <><button onClick={() => void quota.refresh(0)}>load</button>{quota.summary}</>;
}
test("quota windows follow the active family and preserve real reset times", () => {
  const result = quotaWindows(agy, "gemini-3.8-flash", { available: true, groups: [
    { name: "Gemini Models", buckets: [{ window: "5h", remaining_fraction: .25, reset_time: "2026-10-20T12:00:00Z" }] },
    { name: "Claude Models", buckets: [{ window: "weekly", remaining_fraction: .75, reset_time: "" }] },
  ] });
  expect(result).toHaveLength(1);
  expect(result[0].remaining_percent).toBe(25);
  expect(result[0].resets_at).toBe(Date.parse("2026-10-20T12:00:00Z") / 1000);
});
test("dedicated Argon quotas replace general Gemini quotas only for Argon", () => {
  const quota = { available: true, groups: [
    { name: "Gemini Models", buckets: [{ window: "5h", remaining_fraction: .9, reset_time: "" }] },
    { name: "Claude and GPT models", buckets: [{ window: "weekly", remaining_fraction: .8, reset_time: "" }] },
    { name: "Gemini 4 Argon", buckets: [{ window: "weekly", remaining_fraction: .7, reset_time: "" }] },
  ] };
  expect(quotaWindows(agy, "gemini-4-argon-high", quota).map(row => row.remaining_percent)).toEqual([70]);
  expect(quotaWindows(agy, "gemini-3.8-flash-low", quota).map(row => row.remaining_percent)).toEqual([90]);
  expect(quotaWindows(agy, "claude-sonnet-5-5-low", quota).map(row => row.remaining_percent)).toEqual([80]);
  expect(quotaWindows(agy, "gpt-oss-120b-medium", quota).map(row => row.remaining_percent)).toEqual([80]);
  expect(quotaWindows(agy, "gemini-4-argon", { ...quota, groups: quota.groups.slice(0, 2) })[0].remaining_percent).toBe(90);
  expect(quotaWindows(agy, "gemini-3.8-flash", { ...quota, groups: quota.groups.slice(2) })).toEqual([]);
});
test("a late response for another provider cannot overwrite current quotas", async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(coreApi).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  vi.mocked(coreApi).mockResolvedValueOnce({ available: true, five_hour: { remaining_percent: 42 } });
  const view = render(<Harness provider={agy} />);
  fireEvent.click(screen.getByText("load"));
  view.rerender(<Harness provider={claude} />);
  await act(async () => fireEvent.click(screen.getByText("load")));
  expect(screen.getByText("42%")).toBeTruthy();
  await act(async () => resolve({ available: true, five_hour: { remaining_percent: 99 } }));
  expect(screen.queryByText("99%")).toBeNull();
  expect(vi.mocked(coreApi).mock.calls[1][1]).toContain(claude);
});
test("unavailable quotas never invent a remaining percentage", async () => {
  vi.mocked(coreApi).mockResolvedValue({ available: false });
  render(<Harness provider={claude} />);
  await act(async () => fireEvent.click(screen.getByText("load")));
  expect(screen.queryByText(/\d+%/)).toBeNull();
  expect(screen.getAllByText("לא זמין")).toHaveLength(2);
});
test("a quota for another model is unavailable rather than a successful empty summary", async () => {
  vi.mocked(coreApi).mockResolvedValue({ available: true, groups: [
    { name: "Gemini 4 Argon", buckets: [{ window: "weekly", remaining_fraction: .7, reset_time: "" }] },
  ] });
  render(<Harness provider={agy} />);
  await act(async () => fireEvent.click(screen.getByText("load")));
  expect(screen.getByText("נתוני המכסה אינם זמינים כרגע")).toBeTruthy();
  expect(screen.queryByText("70%")).toBeNull();
});
