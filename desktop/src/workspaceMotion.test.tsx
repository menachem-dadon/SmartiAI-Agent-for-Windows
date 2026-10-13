// @vitest-environment jsdom
import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { useChatLayoutMotion, WORKSPACE_EASING, WORKSPACE_MOTION_MS } from "./workspaceMotion";
import { foundations } from "./design-system/tokens";

function Chat({ revision, resizing = false }: { revision: string; resizing?: boolean }) {
  return <section ref={useChatLayoutMotion(revision, resizing)} />;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("uses the same duration for CSS and the native handoff fallback", () => {
  const css = readFileSync("src/chat.css", "utf8");
  expect(css).toContain("--motion-panel: var(--sds-motion-panel)");
  expect(css).toContain("--ease-premium: var(--sds-motion-ease)");
  expect(`${WORKSPACE_MOTION_MS}ms`).toBe(foundations.motion.panel);
  expect(WORKSPACE_EASING).toBe(foundations.motion.ease);
});

it("cancels an in-flight animation immediately when motion reduction changes", () => {
  const cancel = vi.fn(), add = vi.fn(), remove = vi.fn();
  const preference = { matches: false, addEventListener: add, removeEventListener: remove };
  vi.stubGlobal("matchMedia", () => preference);
  const original = HTMLElement.prototype.animate;
  HTMLElement.prototype.animate = vi.fn(() => ({ cancel })) as unknown as typeof original;
  try {
    const bounds = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
    bounds.mockReturnValue({ x: 0, width: 1000 } as DOMRect);
    const { rerender, unmount } = render(<Chat revision="closed" />);
    bounds.mockReturnValue({ x: 500, width: 500 } as DOMRect);
    rerender(<Chat revision="open" />);
    preference.matches = true;
    act(() => add.mock.calls[0][1]());
    expect(cancel).toHaveBeenCalledOnce();
    unmount();
    expect(cancel).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledWith("change", add.mock.calls[0][1]);
  } finally { HTMLElement.prototype.animate = original; }
});

it("animates only the painted chat layer and cancels a replaced motion", () => {
  const cancel = vi.fn();
  const animate = vi.fn(() => ({ cancel }));
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  const original = HTMLElement.prototype.animate;
  HTMLElement.prototype.animate = animate as unknown as typeof original;
  try {
    const bounds = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
    bounds.mockReturnValue({ x: 0, width: 1000 } as DOMRect);
    const { rerender, unmount } = render(<Chat revision="closed" />);
    bounds.mockReturnValue({ x: 500, width: 500 } as DOMRect);
    rerender(<Chat revision="open" />);
    expect(animate).toHaveBeenCalledWith(
      [{ transform: "translateX(-250px)", opacity: .85 }, { transform: "translateX(0)", opacity: 1 }],
      { duration: WORKSPACE_MOTION_MS, easing: WORKSPACE_EASING },
    );
    unmount();
    expect(cancel).toHaveBeenCalledOnce();
  } finally { HTMLElement.prototype.animate = original; }
});

it("keeps minimize and restore still, then animates the next panel toggle from restored bounds", () => {
  const cancel = vi.fn();
  const animate = vi.fn(() => ({ cancel }));
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  vi.stubGlobal("innerWidth", 1600);
  vi.stubGlobal("innerHeight", 900);
  const original = HTMLElement.prototype.animate;
  HTMLElement.prototype.animate = animate as unknown as typeof original;
  try {
    const bounds = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
    bounds.mockReturnValue({ x: 0, width: 1000 } as DOMRect);
    const { rerender } = render(<Chat revision="closed" />);
    bounds.mockReturnValue({ x: 500, width: 500 } as DOMRect);
    rerender(<Chat revision="open" />);
    expect(animate).toHaveBeenCalledOnce();

    vi.stubGlobal("innerWidth", 0);
    vi.stubGlobal("innerHeight", 0);
    bounds.mockReturnValue({ x: 0, width: 0 } as DOMRect);
    fireEvent.resize(window);
    rerender(<Chat revision="open" resizing />);
    expect(cancel).toHaveBeenCalledOnce();

    vi.stubGlobal("innerWidth", 1600);
    vi.stubGlobal("innerHeight", 900);
    bounds.mockReturnValue({ x: 0, width: 1000 } as DOMRect);
    fireEvent.resize(window);
    rerender(<Chat revision="open" />);
    expect(animate).toHaveBeenCalledOnce();

    bounds.mockReturnValue({ x: 500, width: 500 } as DOMRect);
    rerender(<Chat revision="closed" />);
    expect(animate).toHaveBeenLastCalledWith(
      [{ transform: "translateX(-250px)", opacity: .85 }, { transform: "translateX(0)", opacity: 1 }],
      { duration: WORKSPACE_MOTION_MS, easing: WORKSPACE_EASING },
    );
    expect(animate).toHaveBeenCalledTimes(2);
  } finally { HTMLElement.prototype.animate = original; }
});

it("does not animate automatic breakpoint changes or the resize settling render", () => {
  const animate = vi.fn(() => ({ cancel: vi.fn() }));
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  const original = HTMLElement.prototype.animate;
  HTMLElement.prototype.animate = animate as unknown as typeof original;
  try {
    const bounds = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
    bounds.mockReturnValue({ x: 0, width: 1000 } as DOMRect);
    const { rerender } = render(<Chat revision="wide" />);
    bounds.mockReturnValue({ x: 0, width: 500 } as DOMRect);
    rerender(<Chat revision="narrow" resizing />);
    bounds.mockReturnValue({ x: 0, width: 600 } as DOMRect);
    rerender(<Chat revision="narrow" />);
    expect(animate).not.toHaveBeenCalled();
    bounds.mockReturnValue({ x: 300, width: 300 } as DOMRect);
    rerender(<Chat revision="narrow-panel" />);
    expect(animate).toHaveBeenCalledWith(
      [{ transform: "translateX(-150px)", opacity: .85 }, { transform: "translateX(0)", opacity: 1 }],
      { duration: WORKSPACE_MOTION_MS, easing: WORKSPACE_EASING },
    );
  } finally { HTMLElement.prototype.animate = original; }
});

it("cancels motion when hidden and does not replay layout changes on return", () => {
  const cancel = vi.fn();
  const animate = vi.fn(() => ({ cancel }));
  const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  const original = HTMLElement.prototype.animate;
  HTMLElement.prototype.animate = animate as unknown as typeof original;
  try {
    const bounds = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect");
    bounds.mockReturnValue({ x: 0, width: 1000 } as DOMRect);
    const { rerender } = render(<Chat revision="closed" />);
    bounds.mockReturnValue({ x: 500, width: 500 } as DOMRect);
    rerender(<Chat revision="open" />);
    visibility.mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    bounds.mockReturnValue({ x: 0, width: 0 } as DOMRect);
    rerender(<Chat revision="hidden-change" />);
    expect(cancel).toHaveBeenCalledOnce();
    visibility.mockReturnValue("visible");
    bounds.mockReturnValue({ x: 0, width: 1000 } as DOMRect);
    fireEvent(document, new Event("visibilitychange"));
    rerender(<Chat revision="hidden-change" resizing />);
    rerender(<Chat revision="hidden-change" />);
    expect(animate).toHaveBeenCalledOnce();
  } finally { HTMLElement.prototype.animate = original; }
});
