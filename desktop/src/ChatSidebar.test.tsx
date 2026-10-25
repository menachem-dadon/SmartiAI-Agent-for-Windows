// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ChatSidebar } from "./ChatSidebar";
import { SIDEBAR_MOTION_MS, WORKSPACE_EASING } from "./workspaceMotion";

const originalAnimate = HTMLElement.prototype.animate;
afterEach(() => {
  cleanup();
  HTMLElement.prototype.animate = originalAnimate;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function setup(open = false) {
  const animations: Array<{ cancel: ReturnType<typeof vi.fn>; onfinish: (() => void) | null }> = [];
  const animate = vi.fn((_keyframes: Keyframe[] | PropertyIndexedKeyframes, _options?: number | KeyframeAnimationOptions) => {
    const animation = { cancel: vi.fn(), onfinish: null as (() => void) | null };
    animations.push(animation);
    return animation;
  });
  HTMLElement.prototype.animate = animate as unknown as typeof originalAnimate;
  const listeners: Record<string, () => void> = {};
  const preference = { matches: false, addEventListener: vi.fn((event: string, callback: () => void) => { listeners[event] = callback; }), removeEventListener: vi.fn() };
  vi.stubGlobal("matchMedia", () => preference);
  vi.stubGlobal("innerWidth", 1280);
  vi.stubGlobal("innerHeight", 800);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ x: 1040, width: 240 } as DOMRect);
  let clipPath = "none";
  vi.spyOn(window, "getComputedStyle").mockImplementation(() => ({ getPropertyValue: () => "72px", get clipPath() { return clipPath; } }) as unknown as CSSStyleDeclaration);
  const props = { logo: "/logo.png", conversations: [], activeId: "", loading: false, error: "", attentionItems: [],
    onToggle: vi.fn(), onCreate: vi.fn(), onSearch: vi.fn(), onSelect: vi.fn(), actions: () => [], onManagement: vi.fn() };
  const view = render(<ChatSidebar {...props} open={open} />);
  const drawer = () => view.container.querySelector("aside")!;
  return { ...view, animations, animate, drawer, props, preference, listeners, setClip: (value: string) => { clipPath = value; }, update: (next: boolean, resizing = false) => view.rerender(<ChatSidebar {...props} open={next} resizing={resizing} />) };
}

it("reveals and closes the expanded drawer at the same restrained pace", () => {
  const ui = setup();
  expect(ui.animate).not.toHaveBeenCalled();
  ui.update(true);
  expect(ui.animate).toHaveBeenLastCalledWith(
    [{ clipPath: "inset(0px 0px 0px 168px)" }, { clipPath: "inset(0px 0px 0px 0px)" }],
    { duration: SIDEBAR_MOTION_MS, easing: WORKSPACE_EASING },
  );
  expect(SIDEBAR_MOTION_MS).toBeGreaterThan(260);
  expect(SIDEBAR_MOTION_MS).toBeLessThanOrEqual(340);
  act(() => ui.animations[0].onfinish?.());
  ui.update(false);
  expect(ui.animate).toHaveBeenLastCalledWith(
    [{ clipPath: "inset(0px 0px 0px 0px)" }, { clipPath: "inset(0px 0px 0px 168px)" }],
    { duration: SIDEBAR_MOTION_MS, easing: WORKSPACE_EASING },
  );
  expect(ui.drawer().classList.contains("is-closing")).toBe(true);
  expect(ui.drawer().querySelector(".drawer-expanded-content")?.hasAttribute("inert")).toBe(true);
  expect(screen.getByRole("button", { name: "פתיחת תפריט הצד" }).getAttribute("aria-expanded")).toBe("false");
  act(() => ui.animations[1].onfinish?.());
  expect(ui.drawer().classList.contains("is-rail")).toBe(true);
  expect(ui.drawer().querySelector(".drawer-expanded-content")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "חיפוש בשיחות ובקבצים" }));
  expect(ui.props.onSearch).toHaveBeenCalledOnce();
});

it("reverses a running close from the current painted edge", () => {
  const ui = setup(true);
  ui.update(false);
  const oldFinish = ui.animations[0].onfinish;
  ui.setClip("inset(0px 0px 0px 93px)");
  ui.update(true);
  expect(ui.animations[0].cancel).toHaveBeenCalledOnce();
  expect(ui.animate.mock.calls[1][0]).toEqual([{ clipPath: "inset(0px 0px 0px 93px)" }, { clipPath: "inset(0px 0px 0px 0px)" }]);
  act(() => oldFinish?.());
  expect(ui.drawer().dataset.state).toBe("open");
  act(() => ui.animations[1].onfinish?.());
  expect(ui.drawer().classList.contains("is-open")).toBe(true);
});

it.each(["reduce", "resize", "hidden"])("settles an interrupted close on %s without replay on return", reason => {
  const ui = setup(true);
  const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  ui.update(false);
  if (reason === "reduce") { ui.preference.matches = true; act(() => ui.listeners.change()); }
  if (reason === "resize") fireEvent.resize(window);
  if (reason === "hidden") { visibility.mockReturnValue("hidden"); fireEvent(document, new Event("visibilitychange")); }
  expect(ui.animations[0].cancel).toHaveBeenCalledOnce();
  expect(ui.drawer().classList.contains("is-rail")).toBe(true);
  ui.preference.matches = false;
  visibility.mockReturnValue("visible");
  ui.update(false);
  expect(ui.animate).toHaveBeenCalledOnce();
  ui.update(true);
  expect(ui.animate).toHaveBeenCalledTimes(2);
});

it("skips automatic resize changes and reduced-motion toggles", () => {
  const ui = setup(true);
  ui.update(false, true);
  expect(ui.animate).not.toHaveBeenCalled();
  expect(ui.drawer().classList.contains("is-rail")).toBe(true);
  ui.preference.matches = true;
  ui.update(true);
  ui.update(false);
  expect(ui.animate).not.toHaveBeenCalled();
  expect(ui.drawer().classList.contains("is-rail")).toBe(true);
});

it("cancels an unfinished drawer animation when unmounted", () => {
  const ui = setup();
  ui.update(true);
  ui.unmount();
  expect(ui.animations[0].cancel).toHaveBeenCalledOnce();
});
