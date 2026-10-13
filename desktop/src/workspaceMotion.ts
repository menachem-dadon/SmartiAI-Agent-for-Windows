import { useLayoutEffect, useRef } from "react";
import { foundations } from "./design-system/tokens";

export const WORKSPACE_MOTION_MS = Number.parseFloat(foundations.motion.panel);
export const WORKSPACE_EASING = foundations.motion.ease;

export function reducedWorkspaceMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

// Commit the final chat width once, then move its painted layer. Animating the
// grid tracks would rewrap the entire conversation on every animation frame.
export function useChatLayoutMotion(revision: string, resizing = false) {
  const ref = useRef<HTMLElement>(null);
  const previous = useRef<DOMRect | null>(null);
  const previousRevision = useRef(revision);
  const motion = useRef<Animation | null>(null);
  useLayoutEffect(() => {
    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const cancel = () => { motion.current?.cancel(); motion.current = null; };
    const reset = () => { cancel(); previous.current = null; };
    const reduce = () => {
      if (preference?.matches) cancel();
    };
    // Native minimization can temporarily resize the WebView to zero. Never
    // reuse that geometry, or resume a panel animation when the window returns.
    const visibility = () => { if (document.visibilityState === "hidden") reset(); };
    preference?.addEventListener?.("change", reduce);
    window.addEventListener("resize", reset);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      preference?.removeEventListener?.("change", reduce);
      window.removeEventListener("resize", reset);
      document.removeEventListener("visibilitychange", visibility);
      cancel();
    };
  }, []);
  useLayoutEffect(() => {
    const changed = previousRevision.current !== revision;
    previousRevision.current = revision;
    const element = ref.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    if (document.visibilityState === "hidden" || innerWidth <= 0 || innerHeight <= 0 || rect.width <= 0) {
      previous.current = null;
      return;
    }
    const before = previous.current;
    previous.current = rect;
    // Resizing and its settled render only rebase the final geometry. Panel
    // changes made while the viewport is stable retain their normal motion.
    if (!changed || resizing || !before || reducedWorkspaceMotion() || !element.animate) return;
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
  }, [revision, resizing]);
  return ref;
}
