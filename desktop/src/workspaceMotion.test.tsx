// @vitest-environment jsdom
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { useChatLayoutMotion, WORKSPACE_EASING, WORKSPACE_MOTION_MS } from "./workspaceMotion";
import { foundations } from "./design-system/tokens";

function Chat({ revision }: { revision: string }) {
  return <section ref={useChatLayoutMotion(revision)} />;
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
