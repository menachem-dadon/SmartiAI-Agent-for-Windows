import { useLayoutEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { reducedWorkspaceMotion, WORKSPACE_MOTION_MS } from "./workspaceMotion";
import { createBrowserViewportSync, PHONE_VIEWPORT_WIDTH, type BrowserViewportMode } from "./browserViewport";

// Native WebView2 is not part of the DOM compositor. During a CSS transition
// its cached image is painted by React during opening/closing. User resizing
// keeps the live page visible and coalesces native geometry once per frame.
export function useNativeBrowserSurface(
  visible: boolean,
  revision: boolean | string | undefined,
  sidePanel: boolean,
  find: boolean,
  tabId: string | null = null,
  mode: BrowserViewportMode = "auto",
) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const revealed = useRef(false);
  const previousMotion = useRef<{ visible: boolean; revision: typeof revision } | null>(null);
  const [boundsReady, setBoundsReady] = useState(false);
  const [viewportError, setViewportError] = useState("");
  const viewportSync = useRef<ReturnType<typeof createBrowserViewportSync> | null>(null);
  const mounted = useRef(true);
  if (!viewportSync.current) viewportSync.current = createBrowserViewportSync(
    error => { if (mounted.current) setViewportError(`התאמת התצוגה נכשלה: ${String(error)}`); },
    () => { if (mounted.current) setViewportError(""); },
  );
  useLayoutEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; viewportSync.current?.suspend(); };
  }, []);
  const target = useRef({ tabId, mode });
  target.current = { tabId, mode };
  const requestSync = useRef<(() => void) | null>(null);
  const boundsLane = useRef<{ busy: boolean; pending: (() => void) | null }>({ busy: false, pending: null });
  useLayoutEffect(() => { viewportSync.current?.suspend(); requestSync.current?.(); }, [tabId, mode]);
  useLayoutEffect(() => {
    const element = viewportRef.current;
    if (!element) return;
    let disposed = false;
    let frame = 0;
    let timer = 0;
    let moving = false;
    let dirty = false;
    let retries = 0;
    let lastBounds = "";
    let generation = 0;
    const transitions = new Set<string>();
    const motionChanged = previousMotion.current?.revision !== revision || previousMotion.current?.visible !== visible;
    previousMotion.current = { visible, revision };
    const workbench = element.closest(".workbench");
    const resizing = () => Boolean(workbench?.closest(".workspace.is-resizing"));
    const hide = () => {
      generation++;
      revealed.current = false;
      viewportSync.current?.suspend();
      void invoke("browser_set_visible", { visible: false }).catch(() => undefined);
    };
    const flush = async () => {
      if (disposed || !visible || moving) return;
      const rect = element.getBoundingClientRect();
      if (rect.x < 0 || rect.y < 0 || rect.width < 1 || rect.height < 1 || (sidePanel && rect.width <= PHONE_VIEWPORT_WIDTH)) {
        hide();
        setBoundsReady(false);
        return;
      }
      if (boundsLane.current.busy) { dirty = true; boundsLane.current.pending = sync; return; }
      const rightInset = sidePanel ? Math.min(360, rect.width - 160) : 0;
      const topInset = find ? Math.min(46, rect.height - 1) : 0;
      const bounds = { x: Math.round(rect.x), y: Math.round(rect.y + topInset), width: Math.round(rect.width - rightInset), height: Math.round(rect.height - topInset) };
      const key = JSON.stringify({ ...bounds, tabId: target.current.tabId });
      const syncViewport = () => {
        const { tabId, mode } = target.current;
        if (tabId) viewportSync.current?.request({ tabId, mode, width: bounds.width, height: bounds.height });
      };
      if (key === lastBounds && revealed.current) { syncViewport(); return; }
      boundsLane.current.busy = true;
      const requestGeneration = generation;
      try {
        await invoke("browser_set_bounds", { bounds });
        if (disposed || moving || requestGeneration !== generation) return;
        lastBounds = key;
        retries = 0;
        // A live surface must keep receiving page metrics during a continuous
        // drag even if another native resize is queued. Only its first reveal
        // waits for the newest bounds.
        if (!revealed.current && boundsLane.current.pending) return;
        setBoundsReady(true);
        if (!revealed.current) {
          revealed.current = true;
          void invoke("browser_set_visible", { visible: true }).catch(() => {
            revealed.current = false;
          });
        }
        syncViewport();
      } catch {
        // Bounded retries, not a permanent animation/IPC loop.
        if (!disposed && ++retries <= 2) timer = window.setTimeout(sync, 80);
      } finally {
        boundsLane.current.busy = false;
        const pending = boundsLane.current.pending;
        boundsLane.current.pending = null;
        pending?.();
        if (dirty && !disposed) { dirty = false; sync(); }
      }
    };
    const sync = () => {
      if (disposed || frame) return;
      frame = requestAnimationFrame(() => { frame = 0; void flush(); });
    };
    requestSync.current = sync;
    const settle = () => {
      clearTimeout(timer);
      moving = false;
      sync();
    };
    const startMotion = () => {
      if (!moving) hide();
      moving = true;
      setBoundsReady(false);
      clearTimeout(timer);
      timer = window.setTimeout(settle, WORKSPACE_MOTION_MS + 34);
    };
    const transition = (event: Event) => {
      const change = event as TransitionEvent;
      if (event.target !== workbench || change.propertyName !== "transform") return;
      if (resizing()) { settle(); return; }
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
      return () => { disposed = true; cancelAnimationFrame(frame); };
    }
    if (workbench && motionChanged && revision !== undefined && !resizing() && !reducedWorkspaceMotion()) startMotion();
    else sync();
    const observer = new ResizeObserver(() => { if (!moving) sync(); });
    observer.observe(element);
    workbench?.addEventListener("transitionrun", transition);
    workbench?.addEventListener("transitionend", transition);
    workbench?.addEventListener("transitioncancel", transition);
    window.addEventListener("resize", sync);
    window.visualViewport?.addEventListener("resize", sync);
    window.addEventListener("scroll", sync, true);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      clearTimeout(timer);
      observer.disconnect();
      viewportSync.current?.suspend();
      workbench?.removeEventListener("transitionrun", transition);
      workbench?.removeEventListener("transitionend", transition);
      workbench?.removeEventListener("transitioncancel", transition);
      window.removeEventListener("resize", sync);
      window.visualViewport?.removeEventListener("resize", sync);
      window.removeEventListener("scroll", sync, true);
    };
  }, [visible, revision, sidePanel, find]);
  return { viewportRef, boundsReady, viewportError };
}
