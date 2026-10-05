// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { formatUsageCost, UsageView, type UsageSnapshot } from "./UsageView";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
const response = (data: UsageSnapshot) => ({ status: 200, body: { data } });
const snapshot = (timeframe: UsageSnapshot["timeframe"] = "today", model = "gemini-test"): UsageSnapshot => ({
  schema_version: 2, timeframe, total_tokens: 1500, input_tokens: 1000, output_tokens: 500,
  cached_input_tokens: 200, cache_write_tokens: 100, cost_usd: 0.001865,
  known_cost_usd: 0.001865, unpriced_models: 0,
  models: [{ model, tokens: 1500, input_tokens: 1000, output_tokens: 500,
    cached_input_tokens: 200, cache_write_tokens: 100, cost_usd: 0.001865, cost_status: "estimated" }],
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => { sessionStorage.clear(); vi.mocked(invoke).mockReset(); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe("usage loading through the desktop API", () => {
  test("waits for a delayed snapshot, defaults to today and removes memory/RAG", async () => {
    const pending = deferred<ReturnType<typeof response>>();
    vi.mocked(invoke).mockReturnValueOnce(pending.promise);
    render(<UsageView />);
    expect(screen.getByRole("status").textContent).toContain("טוען");
    expect(screen.queryByText("אין שימוש בתקופה הזו")).toBeNull();
    expect(vi.mocked(invoke).mock.calls[0][1]).toMatchObject({ request: { path: "/v2/management/usage?timeframe=today" } });
    await act(async () => pending.resolve(response(snapshot())));
    expect(await screen.findByText("gemini-test")).toBeTruthy();
    expect(screen.getByRole("table").textContent).toContain("1,500");
    expect(screen.getAllByText("<$0.01")).toHaveLength(2);
    expect(document.body.textContent).not.toMatch(/RAG|זיכרון מקומי|0\.001865/);
  });

  test("retries transient startup errors and polls after successful loading", async () => {
    vi.useFakeTimers();
    vi.mocked(invoke).mockRejectedValueOnce(new Error("starting")).mockResolvedValue(response(snapshot()));
    render(<UsageView />);
    await act(async () => {});
    await act(async () => { await vi.advanceTimersByTimeAsync(800); });
    expect(screen.getByText("gemini-test")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
    expect(invoke).toHaveBeenCalledTimes(3);
  });

  test("updates missing costs promptly when the background price refresh completes", async () => {
    vi.useFakeTimers();
    const pending = snapshot();
    pending.cost_usd = null; pending.known_cost_usd = 0; pending.unpriced_models = 1;
    pending.models[0].cost_usd = null; pending.models[0].cost_status = "unavailable";
    pending.pricing = { refreshing: true, refresh_failed: false, cached: false, updated_at: "" };
    const priced = snapshot();
    priced.pricing = { refreshing: false, refresh_failed: false, cached: true, updated_at: "2026-09-30" };
    vi.mocked(invoke).mockResolvedValueOnce(response(pending)).mockResolvedValue(response(priced));
    render(<UsageView />);
    await act(async () => {});
    expect(screen.getByText(/מעדכן את תעריפי המודלים/)).toBeTruthy();
    expect(screen.getByText("חסר תעריף")).toBeTruthy();
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(screen.queryByText(/מעדכן את תעריפי המודלים/)).toBeNull();
    expect(screen.queryByText("חסר תעריף")).toBeNull();
    expect(screen.getAllByText("<$0.01")).toHaveLength(2);
    expect(invoke).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
    expect(invoke).toHaveBeenCalledTimes(2);
  });

  test("keeps locally calculated costs visible when the price download is offline", async () => {
    const offline = snapshot();
    offline.pricing = { refreshing: false, refresh_failed: true, cached: true, updated_at: "2026-09-29" };
    vi.mocked(invoke).mockResolvedValue(response(offline));
    render(<UsageView />);
    expect(await screen.findByText(/החישוב משתמש בתעריפים המקומיים/)).toBeTruthy();
    expect(screen.getByText("gemini-test")).toBeTruthy();
    expect(screen.getAllByText("<$0.01")).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("shows a recoverable error instead of an empty zero result", async () => {
    vi.useFakeTimers();
    vi.mocked(invoke).mockRejectedValue(new Error("offline"));
    render(<UsageView />);
    await act(async () => { await vi.advanceTimersByTimeAsync(2400); });
    expect(screen.getByRole("alert").textContent).toContain("לא ניתן לטעון");
    expect(screen.queryByText("אין שימוש בתקופה הזו")).toBeNull();
    vi.mocked(invoke).mockResolvedValue(response(snapshot()));
    fireEvent.click(screen.getByRole("button", { name: "רענון" }));
    await act(async () => {});
    expect(screen.getByText("gemini-test")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("rejects stale timeframe responses and isolates cached periods", async () => {
    const old = deferred<ReturnType<typeof response>>();
    vi.mocked(invoke).mockReturnValueOnce(old.promise).mockResolvedValue(response(snapshot("all", "history-model")));
    sessionStorage.setItem("smarti.management.usage-v2.today", JSON.stringify(snapshot("today", "cached-model")));
    render(<UsageView />);
    expect(screen.getByText("cached-model")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "כל התקופות" }));
    expect(await screen.findByText("history-model")).toBeTruthy();
    await act(async () => old.resolve(response(snapshot("today", "late-model"))));
    expect(screen.queryByText("late-model")).toBeNull();
    expect(screen.queryByText("cached-model")).toBeNull();
    expect(JSON.parse(sessionStorage.getItem("smarti.management.usage-v2.all")!).timeframe).toBe("all");
  });

  test("offers all history from an empty period and distinguishes missing pricing", async () => {
    const partial = snapshot();
    partial.cost_usd = null; partial.unpriced_models = 1;
    partial.models[0].cost_usd = null; partial.models[0].cost_status = "unavailable";
    vi.mocked(invoke).mockResolvedValueOnce(response(partial)).mockResolvedValue(response({ ...snapshot("week"), total_tokens: 0, models: [] }));
    render(<UsageView />);
    expect(await screen.findByText("חסר תעריף")).toBeTruthy();
    expect(screen.getByText("לא זמין")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "7 ימים" }));
    expect(await screen.findByText("אין שימוש בתקופה הזו")).toBeTruthy();
    expect(screen.getByRole("button", { name: "הצג את כל התקופות" })).toBeTruthy();
  });

  test("storage failure does not discard a successful snapshot", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
    vi.mocked(invoke).mockResolvedValue(response(snapshot()));
    render(<UsageView />);
    expect(await screen.findByText("gemini-test")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("clears cached periods and ignores a read that finishes after clearing", async () => {
    const pending = deferred<ReturnType<typeof response>>();
    const empty = { ...snapshot(), total_tokens: 0, models: [], cost_usd: 0, known_cost_usd: 0 };
    vi.mocked(invoke).mockResolvedValueOnce(response(snapshot())).mockReturnValueOnce(pending.promise).mockResolvedValue(response(empty));
    sessionStorage.setItem("smarti.management.usage-v2.all", JSON.stringify(snapshot("all")));
    render(<UsageView />);
    await screen.findByText("gemini-test");
    fireEvent.click(screen.getByRole("button", { name: "רענון" }));
    fireEvent.click(screen.getByRole("button", { name: "ניקוי נתונים" }));
    fireEvent.click(screen.getByRole("button", { name: "ניקוי הנתונים" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    await act(async () => pending.resolve(response(snapshot("all", "stale-model"))));
    expect(screen.queryByText("stale-model")).toBeNull();
    expect(sessionStorage.getItem("smarti.management.usage-v2.all")).toBeNull();
    expect(screen.getByText("אין שימוש בתקופה הזו")).toBeTruthy();
  });

  test("reports clear failure and preserves the confirmation for retry", async () => {
    vi.mocked(invoke).mockImplementation(async (_command, args: any) => {
      if (args.request.method === "DELETE") throw new Error("backup failed");
      return response(snapshot()) as any;
    });
    render(<UsageView />);
    await screen.findByText("gemini-test");
    fireEvent.click(screen.getByRole("button", { name: "ניקוי נתונים" }));
    fireEvent.click(screen.getByRole("button", { name: "ניקוי הנתונים" }));
    expect(await screen.findByText(/ניקוי הנתונים נכשל/)).toBeTruthy();
    expect(screen.getByRole("alertdialog")).toBeTruthy();
  });

  test("rejects stale service data instead of showing false zeros", async () => {
    vi.useFakeTimers();
    const stale = { ...snapshot(), schema_version: undefined, total_tokens: 0 };
    vi.mocked(invoke).mockResolvedValue({ status: 200, body: { data: stale } } as any);
    sessionStorage.setItem("smarti.management.usage-v2.today", JSON.stringify(stale));
    render(<UsageView />);
    await act(async () => { await vi.advanceTimersByTimeAsync(2400); });
    expect(screen.getByRole("alert").textContent).toContain("יש לפתוח מחדש");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("$0.00")).toBeNull();
  });
});

test.each([[0, "$0.00"], [0.000003, "<$0.01"], [0.01, "$0.01"], [12.345, "$12.35"], [null, "לא זמין"]])(
  "formats %s with at most two decimal places", (value, expected) => expect(formatUsageCost(value as number | null)).toBe(expected),
);
