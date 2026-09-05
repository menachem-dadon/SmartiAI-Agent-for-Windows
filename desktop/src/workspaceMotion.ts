import { useLayoutEffect, useRef } from "react";

export const WORKSPACE_MOTION_MS = 320;
export const WORKSPACE_EASING = "cubic-bezier(.22,1,.36,1)";

export function reducedWorkspaceMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

// Commit the final chat width once, then move its painted layer. Animating the
// grid tracks would rewrap the entire conversation on every animation frame.
export function useChatLayoutMotion(revision: string) {
  const ref = useRef<HTMLElement>(null);
  const previous = useRef<DOMRect | null>(null);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const before = previous.current;
    previous.current = rect;
    if (!before || reducedWorkspaceMotion() || !element.animate) return;
    const offset = before.x + before.width / 2 - rect.x - rect.width / 2;
    if (Math.abs(offset) < 1) return;
    const animation = element.animate(
      [{ transform: `translateX(${offset}px)`, opacity: .85 }, { transform: "translateX(0)", opacity: 1 }],
      { duration: WORKSPACE_MOTION_MS, easing: WORKSPACE_EASING },
    );
    return () => animation.cancel();
  }, [revision]);
  return ref;
}
