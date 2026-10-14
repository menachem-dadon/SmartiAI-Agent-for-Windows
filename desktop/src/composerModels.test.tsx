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

async function openEffort() {
  fireEvent.click(screen.getByLabelText("בחירת מודל"));
  await waitFor(() => expect(screen.getByRole("dialog", { name: "מודל ועוצמת חשיבה" }).parentElement?.parentElement).toBe(document.body));
  return screen.getByRole("dialog", { name: "מודל ועוצמת חשיבה" });
}
async function openModels() {
  await openEffort();
  fireEvent.click(screen.getByRole("button", { name: "פתיחת המודלים המועדפים" }));
  return screen.getByRole("dialog", { name: "מודלים מועדפים" });
}

describe("composer model selection", () => {
  test("shortens only local paths and sends the original favorite identity", async () => {
    const localModel = String.raw`C:\models\vendor\Qwen-35-Q4.gguf`;
    const thirdParty = "qwen/Qwen-35-Coder";
    const onFavoriteModel = vi.fn();
    render(<Composer {...callbacks} attachments={[]} provider="local" model={localModel}
      favoriteModels={[{ provider: "local", model: localModel }, { provider: "openrouter", model: thirdParty }]}
      onFavoriteModel={onFavoriteModel} />);
    expect(screen.getByLabelText("בחירת מודל").textContent).toContain("Qwen 35 Q4.gguf");
    expect(screen.getByLabelText("בחירת מודל").textContent).not.toContain("C:");
    await openModels();
    fireEvent.mouseEnter(screen.getByRole("button", { name: "OpenRouter" }));
    expect(screen.getByRole("menuitemradio", { name: "qwen/Qwen 35 Coder" })).toBeTruthy();
    fireEvent.mouseEnter(screen.getByRole("button", { name: "שרת מקומי" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Qwen 35 Q4.gguf" }));
    expect(onFavoriteModel).toHaveBeenCalledWith({ provider: "local", model: localModel });
  });

  test("uses only the model's available reasoning stops and previews a drag before writing", async () => {
    const onReasoningEffort = vi.fn();
    render(<Composer {...callbacks} attachments={[]} provider="gemini" model="gemini-3.6-flash"
      reasoningEffort="auto" reasoningOptions={[{ value: "auto", label: "אוטומטית" }, { value: "minimal", label: "מינימלית" }, { value: "high", label: "גבוהה" }]}
      onReasoningEffort={onReasoningEffort} />);
    const popup = await openEffort();
    const slider = screen.getByRole("slider", { name: "עוצמת חשיבה" });
    expect(slider.getAttribute("max")).toBe("2");
    expect(popup.querySelectorAll(".model-effort-stops i")).toHaveLength(3);
    fireEvent.pointerDown(slider, { pointerId: 1 });
    fireEvent.change(slider, { target: { value: "1" } });
    expect(slider.getAttribute("aria-valuetext")).toBe("Minimal");
    expect(within(popup).getByText("Minimal", { selector: ".model-effort-value" })).toBeTruthy();
    expect(onReasoningEffort).not.toHaveBeenCalled();
    fireEvent.change(slider, { target: { value: "2" } });
    fireEvent.pointerUp(slider, { pointerId: 1 });
    await waitFor(() => expect(onReasoningEffort).toHaveBeenCalledExactlyOnceWith("high"));
  });

  test("does not invent a reasoning control for a model without reasoning options", async () => {
    render(<Composer {...callbacks} attachments={[]} provider="local" model="local-model" />);
    await openEffort();
    expect(screen.queryByRole("slider")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "פתיחת המודלים המועדפים" }));
    expect(screen.getByRole("menuitemradio", { name: "local model" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "חזרה לעוצמת החשיבה" }));
    expect(screen.getByRole("dialog", { name: "מודל ועוצמת חשיבה" })).toBeTruthy();
  });

  test("finishes queued reasoning writes in order after dismissal and reopening", async () => {
    let finish!: () => void;
    const onReasoningEffort = vi.fn().mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; })).mockResolvedValue(undefined);
    render(<Composer {...callbacks} attachments={[]} provider="openai" model="gpt-model" reasoningEffort="auto"
      reasoningOptions={[{ value: "auto", label: "Auto" }, { value: "high", label: "High" }, { value: "max", label: "Max" }]}
      onReasoningEffort={onReasoningEffort} />);
    await openEffort();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "1" } });
    await waitFor(() => expect(onReasoningEffort).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByRole("slider"), { target: { value: "2" } });
    fireEvent.pointerDown(document.body);
    await waitFor(() => expect(document.querySelector(".model-picker-frame")).toBeNull());
    await openEffort();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "0" } });
    await act(async () => finish());
    await waitFor(() => expect(onReasoningEffort.mock.calls.map(call => call[0])).toEqual(["high", "max", "auto"]));
  });

  test("keeps the active model, reasoning and settings reachable without favorites", async () => {
    const onReasoningEffort = vi.fn();
    const onManageModels = vi.fn();
    render(<Composer {...callbacks} attachments={[]} provider="openai_codex_signin"
      model="gpt-6-astra" favoriteModels={[]} reasoningEffort="auto"
      reasoningOptions={[{ value: "auto", label: "אוטומטית" }, { value: "max", label: "מקסימלית" }]}
      onReasoningEffort={onReasoningEffort} onManageModels={onManageModels} />);
    const trigger = screen.getByLabelText("בחירת מודל");
    await openEffort();
    expect(screen.queryByRole("menuitemradio")).toBeNull();
    expect(screen.getByRole("slider", { name: "עוצמת חשיבה" }).getAttribute("aria-valuetext")).toBe("Auto");
    fireEvent.change(screen.getByRole("slider"), { target: { value: "1" } });
    await waitFor(() => expect(onReasoningEffort).toHaveBeenCalledWith("max"));
    await waitFor(() => expect((screen.getByRole("button", { name: "פתיחת המודלים המועדפים" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "פתיחת המודלים המועדפים" }));
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("region", { name: "מכסת Codex שנותרה" })).toBeTruthy();
    expect(screen.getByRole("menuitemradio", { name: "gpt 6 astra" }).getAttribute("aria-checked")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "הגדרות מודלים ומועדפים" }));
    expect(onManageModels).toHaveBeenCalledOnce();
    expect(onManageModels).toHaveBeenCalledWith(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
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
    expect(screen.getByLabelText("בחירת מודל").getAttribute("aria-expanded")).toBe("false");
  });

  test("offers model settings even before a model or favorites are configured", async () => {
    const onManageModels = vi.fn();
    render(<Composer {...callbacks} attachments={[]} onManageModels={onManageModels} />);
    await openModels();
    fireEvent.click(screen.getByRole("button", { name: "הגדרות מודלים ומועדפים" }));
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
    const provider = screen.getByRole("button", { name: /שרת מקומי/ });
    fireEvent.pointerDown(provider);
    fireEvent.click(provider);
    expect(screen.getByLabelText("בחירת מודל").getAttribute("aria-expanded")).toBe("true");
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
    expect(screen.getByRole("button", { name: "הגדרות מודלים ומועדפים" }).closest("header")).toBeTruthy();
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
