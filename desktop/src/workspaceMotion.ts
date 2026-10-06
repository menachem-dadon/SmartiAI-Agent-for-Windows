import { useLayoutEffect, useRef } from "react";
import { foundations } from "./design-system/tokens";

export const WORKSPACE_MOTION_MS = Number.parseFloat(foundations.motion.panel);
export const WORKSPACE_EASING = foundations.motion.ease;

export function reducedWorkspaceMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

// Commit the final chat width once, then move its painted layer. Animating the
// grid tracks would rewrap the entire conversation on every animation frame.
export function useChatLayoutMotion(revision: string) {
  const ref = useRef<HTMLElement>(null);
  const previous = useRef<DOMRect | null>(null);
  const motion = useRef<Animation | null>(null);
  useLayoutEffect(() => {
    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const reduce = () => {
      if (preference?.matches) { motion.current?.cancel(); motion.current = null; }
    };
    preference?.addEventListener?.("change", reduce);
    return () => preference?.removeEventListener?.("change", reduce);
  }, []);
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
    motion.current = animation;
    return () => {
      if (motion.current === animation) { animation.cancel(); motion.current = null; }
    };
  }, [revision]);
  return ref;
}
