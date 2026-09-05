import { useLayoutEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { reducedWorkspaceMotion, WORKSPACE_MOTION_MS } from "./workspaceMotion";

// Native WebView2 is not part of the DOM compositor. During a CSS transition
// its cached image is painted by React; position the live surface only at rest.
export function useNativeBrowserSurface(
  visible: boolean,
  revision: boolean | string | undefined,
  sidePanel: boolean,
  find: boolean,
) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const revealed = useRef(false);
  const previousMotion = useRef<{ visible: boolean; revision: typeof revision } | null>(null);
  const [boundsReady, setBoundsReady] = useState(false);
  useLayoutEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    let disposed = false;
    let frame = 0;
    let timer = 0;
    let moving = false;
    let inFlight = false;
    let dirty = false;
    let retries = 0;
    let lastBounds = "";
    const transitions = new Set<string>();
    const motionChanged = previousMotion.current?.revision !== revision || previousMotion.current?.visible !== visible;
    previousMotion.current = { visible, revision };
    const workbench = element.closest(".workbench");
    const hide = () => {
      revealed.current = false;
      void invoke("browser_set_visible", { visible: false }).catch(() => undefined);
    };
    const flush = async () => {
      if (disposed || !visible || moving) return;
      if (inFlight) { dirty = true; return; }
      const rect = element.getBoundingClientRect();
      if (rect.x < 0 || rect.width < 160 || rect.height < 120) return;
      const rightInset = sidePanel ? Math.min(360, rect.width - 160) : 0;
      const topInset = find ? Math.min(46, rect.height - 120) : 0;
      const bounds = { x: Math.round(rect.x), y: Math.round(rect.y + topInset), width: Math.round(rect.width - rightInset), height: Math.round(rect.height - topInset) };
      const key = JSON.stringify(bounds);
      if (key === lastBounds && revealed.current) return;
      inFlight = true;
      try {
        await invoke("browser_set_bounds", { bounds });
        if (disposed || moving) return;
        lastBounds = key;
        retries = 0;
        setBoundsReady(true);
        if (!revealed.current) {
          revealed.current = true;
          void invoke("browser_set_visible", { visible: true }).catch(() => {
            revealed.current = false;
          });
        }
      } catch {
        // Bounded retries, not a permanent animation/IPC loop.
        if (!disposed && ++retries <= 2) timer = window.setTimeout(sync, 80);
      } finally {
        inFlight = false;
        if (dirty && !disposed) { dirty = false; sync(); }
      }
    };
    const sync = () => {
      if (disposed || frame) return;
      frame = requestAnimationFrame(() => { frame = 0; void flush(); });
    };
    const settle = () => {
      clearTimeout(timer);
      moving = false;
      sync();
    };
    const startMotion = () => {
      if (!moving) hide();
      moving = true;
      clearTimeout(timer);
      timer = window.setTimeout(settle, WORKSPACE_MOTION_MS + 34);
    };
    const transition = (event: Event) => {
      const change = event as TransitionEvent;
      if (event.target !== workbench || !["transform", "width"].includes(change.propertyName)) return;
      if (event.type === "transitionrun") {
        transitions.add(change.propertyName);
        startMotion();
      } else {
        transitions.delete(change.propertyName);
        if (event.type === "transitionend" && transitions.size === 0) settle();
      }
      // A cancellation may be a reversal. Its new transitionrun or the fallback
      // deadline settles the latest state; never reveal the cancelled state.
    };
    if (!visible) {
      hide();
      setBoundsReady(false);
      return () => { disposed = true; };
    }
    if (workbench && motionChanged && revision !== undefined && !reducedWorkspaceMotion()) startMotion();
    else sync();
    const observer = new ResizeObserver(() => { if (!moving) sync(); });
    observer.observe(element);
    workbench?.addEventListener("transitionrun", transition);
    workbench?.addEventListener("transitionend", transition);
    workbench?.addEventListener("transitioncancel", transition);
    window.addEventListener("resize", sync);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      clearTimeout(timer);
      observer.disconnect();
      workbench?.removeEventListener("transitionrun", transition);
      workbench?.removeEventListener("transitionend", transition);
      workbench?.removeEventListener("transitioncancel", transition);
      window.removeEventListener("resize", sync);
    };
  }, [visible, revision, sidePanel, find]);
  return { viewportRef, boundsReady };
}
