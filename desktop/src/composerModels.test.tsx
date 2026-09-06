// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Composer } from "./Composer";
import { coreApi } from "./coreApi";

vi.mock("./coreApi", () => ({ coreApi: vi.fn(async () => ({ available: false })) }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const callbacks = {
  onAttachments: () => {}, onSend: async () => {}, onCancel: () => {},
};

async function openModels() {
  fireEvent.click(screen.getByLabelText("בחירת מודל"));
  await waitFor(() => expect(screen.getByRole("dialog", { name: "מודלים מועדפים" }).parentElement).toBe(document.body));
  return screen.getByRole("dialog", { name: "מודלים מועדפים" });
}

describe("composer model selection", () => {
  test("keeps the active model, reasoning and settings reachable without favorites", async () => {
    const onReasoningEffort = vi.fn();
    const onManageModels = vi.fn();
    render(<Composer {...callbacks} attachments={[]} provider="openai_codex_signin"
      model="gpt-6-astra" favoriteModels={[]} reasoningEffort="high"
      reasoningOptions={[{ value: "auto", label: "אוטומטית" }, { value: "max", label: "מקסימלית" }]}
      onReasoningEffort={onReasoningEffort} onManageModels={onManageModels} />);
    const trigger = screen.getByLabelText("בחירת מודל");
    await openModels();
    expect(trigger.closest("details")!.open).toBe(true);
    expect(screen.getByRole("region", { name: "מכסת Codex שנותרה" })).toBeTruthy();
    expect(screen.getByRole("menuitemradio", { name: "gpt 6 astra" }).getAttribute("aria-checked")).toBe("true");
    fireEvent.change(screen.getByLabelText("עוצמת חשיבה"), { target: { value: "max" } });
    expect(onReasoningEffort).toHaveBeenCalledWith("max");
    fireEvent.click(screen.getByRole("menuitem", { name: "הגדרות מודלים ומועדפים" }));
    expect(onManageModels).toHaveBeenCalledOnce();
    expect(trigger.closest("details")!.open).toBe(false);
  });

  test("shows favorites added after startup and selects their provider and model", async () => {
    const onFavoriteModel = vi.fn();
    const props = { ...callbacks, attachments: [], provider: "gemini", model: "gemini-3.7-flash", onFavoriteModel };
    const { rerender } = render(<Composer {...props} />);
    rerender(<Composer {...props} favoriteModels={[{ provider: "openai_codex_signin", model: "gpt-6-astra" }]} />);
    await openModels();
    fireEvent.mouseEnter(screen.getByRole("button", { name: /OpenAI Codex Sign-in/ }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "gpt 6 astra" }));
    expect(onFavoriteModel).toHaveBeenCalledWith({ provider: "openai_codex_signin", model: "gpt-6-astra" });
    expect(screen.getByLabelText("בחירת מודל").closest("details")!.open).toBe(false);
  });

  test("offers model settings even before a model or favorites are configured", async () => {
    const onManageModels = vi.fn();
    render(<Composer {...callbacks} attachments={[]} onManageModels={onManageModels} />);
    await openModels();
    fireEvent.click(screen.getByRole("menuitem", { name: "הגדרות מודלים ומועדפים" }));
    expect(onManageModels).toHaveBeenCalledOnce();
  });

  test("switches 7, 3 and 1 models without moving or recreating the provider rows or menu bounds", async () => {
    const favorites = [
      ...Array.from({ length: 7 }, (_, i) => ({ provider: "local", model: `local-${i}` })),
      ...Array.from({ length: 3 }, (_, i) => ({ provider: "anthropic", model: `claude-${i}` })),
      { provider: "gemini", model: "gemini-flash" },
    ];
    render(<Composer {...callbacks} attachments={[]} provider="local" model="local-0" favoriteModels={favorites} />);
    const popup = await openModels();
    const providers = screen.getByRole("region", { name: "ספקים" });
    const rows = within(providers).getAllByRole("button");
    const bounds = popup.getAttribute("style");
    const models = screen.getByRole("region", { name: "מודלים של הספק" });
    for (const [index, count] of [[0, 7], [1, 3], [2, 1], [0, 7]]) {
      fireEvent.mouseEnter(rows[index]);
      expect(within(models).getAllByRole("menuitemradio")).toHaveLength(count);
      expect(within(providers).getAllByRole("button")).toEqual(rows);
      expect(popup.getAttribute("style")).toBe(bounds);
      expect(rows[index].getAttribute("aria-pressed")).toBe("true");
    }
  });

  test("supports touch, keyboard navigation and dismissal across the portaled menu", async () => {
    const select = vi.fn();
    render(<Composer {...callbacks} attachments={[]} provider="gemini" model="gemini-flash"
      favoriteModels={[{ provider: "local", model: "local-model" }]}
      onFavoriteModel={select} />);
    await openModels();
    const provider = screen.getByRole("button", { name: /מודל מקומי/ });
    fireEvent.pointerDown(provider);
    fireEvent.click(provider);
    expect(screen.getByLabelText("בחירת מודל").closest("details")!.open).toBe(true);
    fireEvent.keyDown(provider, { key: "ArrowLeft" });
    const model = screen.getByRole("menuitemradio", { name: "local model" });
    expect(document.activeElement).toBe(model);
    fireEvent.keyDown(model, { key: "ArrowRight" });
    expect(document.activeElement).toBe(provider);
    fireEvent.keyDown(provider, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(screen.getByLabelText("בחירת מודל"));
    await openModels();
    fireEvent.pointerDown(document.body);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(select).not.toHaveBeenCalled();
  });

  test("keeps quota loading, zero and reset times in the compact summary without changing menu bounds", async () => {
    let resolveQuota!: (value: unknown) => void;
    vi.mocked(coreApi).mockReturnValueOnce(new Promise(resolve => { resolveQuota = resolve; }));
    render(<Composer {...callbacks} attachments={[]} provider="openai_codex_signin" model="gpt-6-astra"
      favoriteModels={[{ provider: "openai_codex_signin", model: "gpt-6-astra" }]}
      onManageModels={() => {}} />);
    const popup = await openModels();
    const bounds = popup.getAttribute("style");
    const summary = screen.getByRole("region", { name: "מכסת Codex שנותרה" });
    expect(within(summary).getAllByText("—")).toHaveLength(2);
    expect(within(summary).queryByText("0% נותרו")).toBeNull();
    const reset = Math.floor(Date.now() / 1000) + 3600;
    await act(async () => resolveQuota({ available: true, plan_type: "plus",
      five_hour: { remaining_percent: 41, resets_at: reset }, weekly: { remaining_percent: 0, resets_at: reset + 86400 },
    }));
    expect(within(summary).getByText("41% נותרו")).toBeTruthy();
    expect(within(summary).getByText("0% נותרו")).toBeTruthy();
    expect(summary.querySelectorAll('[title*="איפוס בעוד"]')).toHaveLength(2);
    expect(summary.title).toContain("plus");
    expect(popup.getAttribute("style")).toBe(bounds);
    expect(screen.getByRole("menuitem", { name: "הגדרות מודלים ומועדפים" }).closest("header")).toBeTruthy();
  });

  test("places the actual popup below the titlebar and uses compact controls in a short window", async () => {
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(320);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return this.classList.contains("window-titlebar")
        ? new DOMRect(0, 0, 360, 36) : new DOMRect(90, 256, 120, 40);
    });
    render(<><header className="window-titlebar" /><Composer {...callbacks} attachments={[]}
      provider="openai_codex_signin" model="gpt-6-astra" onManageModels={() => {}} /></>);
    const popup = await openModels();
    expect(parseFloat(popup.style.top)).toBeGreaterThanOrEqual(44);
    expect(parseFloat(popup.style.top) + parseFloat(popup.style.height)).toBeLessThanOrEqual(248);
    expect(popup.classList.contains("is-compact")).toBe(true);
  });
});
