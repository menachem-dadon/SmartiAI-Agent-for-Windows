import { invoke } from "@tauri-apps/api/core";
import { nextRequestId } from "./browserState";

export type BrowserViewportMode = "auto" | "mobile" | "desktop";
export const PHONE_VIEWPORT_WIDTH = 600;
export type BrowserViewport = { tabId: string; width: number; height: number; mode: BrowserViewportMode };

// CDP can take longer than a native resize. Keep a separate, serial lane with
// only the newest requested viewport, so it never holds up window geometry.
export function createBrowserViewportSync(onError: (error: unknown) => void, onSuccess: () => void = () => {}) {
  let pending: BrowserViewport | null = null;
  let running = false;
  const applied = new Map<string, string>();
  const flush = async () => {
    if (running) return;
    running = true;
    try {
      while (pending) {
        const viewport = pending;
        pending = null;
        const mobile = viewport.mode === "mobile" ||
          (viewport.mode === "auto" && viewport.width <= PHONE_VIEWPORT_WIDTH);
        const params = mobile ? {
          width: viewport.width, height: viewport.height,
          deviceScaleFactor: 0, mobile: true,
        } : {};
        const key = JSON.stringify(params);
        if (applied.get(viewport.tabId) === key) continue;
        try {
          await invoke("browser_action", { action: {
            requestId: nextRequestId(), tabId: viewport.tabId,
            method: mobile ? "Emulation.setDeviceMetricsOverride" : "Emulation.clearDeviceMetricsOverride",
            params,
          } });
          applied.set(viewport.tabId, key);
          onSuccess();
        } catch (error) {
          // A later resize/activation can retry; never spin on a failed target.
          onError(error);
        }
      }
    } finally { running = false; }
  };
  return {
    request(viewport: BrowserViewport) { pending = viewport; void flush(); },
    suspend() { pending = null; },
  };
}
