import { useLayoutEffect, useState, type RefObject } from "react";

type Viewport = { left: number; top: number; width: number; height: number };
type Anchor = { left: number; top: number; bottom: number };

export function modelMenuContentViewport(viewport: Viewport, titlebarBottom: number) {
  const bottom = viewport.top + viewport.height;
  const top = Math.min(bottom, Math.max(viewport.top, titlebarBottom));
  return { ...viewport, top, height: bottom - top };
}

export function modelMenuBounds(anchor: Anchor, viewport: Viewport, preferredHeight: number) {
  const gap = 8;
  const width = Math.min(530, Math.max(0, viewport.width - gap * 2));
  const minTop = viewport.top + gap;
  const maxBottom = viewport.top + viewport.height - gap;
  const above = Math.max(0, Math.min(maxBottom, anchor.top - gap) - minTop);
  const below = Math.max(0, maxBottom - Math.max(minTop, anchor.bottom + gap));
  const opensAbove = above >= below;
  const height = Math.min(preferredHeight, opensAbove ? above : below);
  const left = Math.max(viewport.left + gap,
    Math.min(anchor.left, viewport.left + viewport.width - width - gap));
  const top = opensAbove
    ? Math.max(minTop, Math.min(maxBottom, anchor.top - gap) - height)
    : Math.min(maxBottom - height, Math.max(minTop, anchor.bottom + gap));
  return { left, top, width, height };
}

export function useModelMenuPosition(
  open: boolean, anchor: RefObject<HTMLDetailsElement | null>, preferredHeight: number,
) {
  const [bounds, setBounds] = useState<ReturnType<typeof modelMenuBounds> | null>(null);
  useLayoutEffect(() => {
    if (!open) return;
    const trigger = anchor.current?.querySelector("summary");
    if (!trigger) return;
    const update = () => {
      const viewport = window.visualViewport;
      const contentViewport = modelMenuContentViewport({
        left: viewport?.offsetLeft || 0, top: viewport?.offsetTop || 0,
        width: viewport?.width || window.innerWidth, height: viewport?.height || window.innerHeight,
      }, document.querySelector(".window-titlebar")?.getBoundingClientRect().bottom || 0);
      const next = modelMenuBounds(trigger.getBoundingClientRect(), contentViewport, preferredHeight);
      setBounds(current => current && Object.keys(next).every(
        key => current[key as keyof typeof next] === next[key as keyof typeof next],
      ) ? current : next);
    };
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(trigger);
    const composer = anchor.current?.closest(".composer");
    if (composer) observer?.observe(composer);
    const titlebar = document.querySelector(".window-titlebar");
    if (titlebar) observer?.observe(titlebar);
    // Layout movement, zoom and the on-screen keyboard can all move the anchor.
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [open, anchor, preferredHeight]);
  return bounds;
}
