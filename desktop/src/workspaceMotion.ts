import { useLayoutEffect, useRef, useState } from "react";
import { foundations } from "./design-system/tokens";

export const WORKSPACE_MOTION_MS = Number.parseFloat(foundations.motion.panel);
export const WORKSPACE_EASING = foundations.motion.ease;
export const SIDEBAR_MOTION_MS = Number.parseFloat(foundations.motion.sidebar);

export function reducedWorkspaceMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

// Keep the expanded layout through exit; reveal its paint without reflowing
// labels or moving the rail icons. The grid still commits its final size once.
export function useConversationDrawerMotion(open: boolean, resizing = false) {
  const ref = useRef<HTMLElement>(null);
  const [present, setPresent] = useState(open);
  const requested = useRef(open);
  const previous = useRef(open);
  const motion = useRef<Animation | null>(null);
  const interruptedClip = useRef<string | null>(null);
  requested.current = open;
  useLayoutEffect(() => {
    const preference = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const settle = () => {
      if (motion.current) { motion.current.onfinish = null; motion.current.cancel(); motion.current = null; }
      interruptedClip.current = null;
      previous.current = requested.current;
      setPresent(requested.current);
    };
    const reduce = () => { if (preference?.matches) settle(); };
    const visibility = () => { if (document.visibilityState === "hidden") settle(); };
    preference?.addEventListener?.("change", reduce);
    window.addEventListener("resize", settle);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      preference?.removeEventListener?.("change", reduce);
      window.removeEventListener("resize", settle);
      document.removeEventListener("visibilitychange", visibility);
      if (motion.current) { motion.current.onfinish = null; motion.current.cancel(); motion.current = null; }
    };
  }, []);
  useLayoutEffect(() => {
    const changed = previous.current !== open;
    previous.current = open;
    const element = ref.current;
    if (!element) return;
    if (resizing || document.visibilityState === "hidden" || innerWidth <= 0 || innerHeight <= 0 || reducedWorkspaceMotion() || !element.animate) {
      interruptedClip.current = null;
      setPresent(open);
      return;
    }
    if (!changed) return;
    const width = element.getBoundingClientRect().width;
    if (width <= 0) { setPresent(open); return; }
    if (open) setPresent(true);
    const rail = Number.parseFloat(getComputedStyle(element).getPropertyValue("--rail-width"));
    if (!Number.isFinite(rail)) { setPresent(open); return; }
    const expandedClip = "inset(0px 0px 0px 0px)";
    const railClip = `inset(0px 0px 0px ${Math.max(0, width - rail)}px)`;
    const from = interruptedClip.current || (open ? railClip : expandedClip);
    interruptedClip.current = null;
    const animation = element.animate(
      [{ clipPath: from }, { clipPath: open ? expandedClip : railClip }],
      { duration: SIDEBAR_MOTION_MS, easing: WORKSPACE_EASING },
    );
    motion.current = animation;
    animation.onfinish = () => {
      if (motion.current !== animation) return;
      motion.current = null;
      setPresent(open);
      animation.cancel();
    };
    return () => {
      if (motion.current !== animation) return;
      const clip = getComputedStyle(element).clipPath;
      interruptedClip.current = clip && clip !== "none" ? clip : null;
      motion.current = null;
      animation.onfinish = null;
      animation.cancel();
    };
  }, [open, resizing]);
  return { ref, visibleOpen: open || present };
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
