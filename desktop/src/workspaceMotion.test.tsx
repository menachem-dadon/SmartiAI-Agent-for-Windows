// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { useChatLayoutMotion, WORKSPACE_EASING, WORKSPACE_MOTION_MS } from "./workspaceMotion";

function Chat({ revision }: { revision: string }) {
  return <section ref={useChatLayoutMotion(revision)} />;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("uses the same duration for CSS and the native handoff fallback", () => {
  const css = readFileSync("src/App.css", "utf8");
  expect(css).toContain(`--motion-panel: ${WORKSPACE_MOTION_MS}ms`);
  expect(css).toContain(`--ease-premium: ${WORKSPACE_EASING}`);
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
