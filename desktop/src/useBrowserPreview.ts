import { useEffect, useRef, useState } from "react";
import type { BrowserTab } from "./browserState";

type Capture = (tab: BrowserTab, method: string, params: Record<string, unknown>) => Promise<{ result: Record<string, unknown> }>;
type Preview = { tabId: string; url: string; dataUrl: string };

// Share the real page image between the collapsed card and Workbench motion.
// A single lane prevents overlapping CDP captures, including across tab changes.
export function useBrowserPreview(tab: BrowserTab | null, capture: Capture) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const lane = useRef<Promise<unknown> | null>(null);
  const latest = useRef(tab);
  latest.current = tab;
  useEffect(() => {
    setError("");
    if (!tab || tab.loading || tab.crashed || !/^https?:/i.test(tab.url)) return;
    let stopped = false;
    let timer = 0;
    const tick = async () => {
      if (lane.current) await lane.current.catch(() => undefined);
      if (stopped) return;
      if (!document.hidden) {
        const request = capture(tab, "Page.captureScreenshot", {
          format: "jpeg", quality: 80, fromSurface: true, captureBeyondViewport: false,
        });
        lane.current = request;
        try {
          const result = await request;
          const data = result.result.data;
          if (typeof data !== "string" || !data) throw new Error("empty browser capture");
          if (!stopped && latest.current?.tabId === tab.tabId && latest.current.url === tab.url) {
            setPreview({ tabId: tab.tabId, url: tab.url, dataUrl: `data:image/jpeg;base64,${data}` });
            setError("");
          }
        } catch {
          if (!stopped) setError("התצוגה המקדימה אינה זמינה כרגע");
        } finally {
          if (lane.current === request) lane.current = null;
        }
      }
      if (!stopped) timer = window.setTimeout(() => void tick(), 2500);
    };
    timer = window.setTimeout(() => void tick(), 150);
    return () => { stopped = true; clearTimeout(timer); };
  }, [tab?.tabId, tab?.url, tab?.loading, tab?.crashed, capture]);
  return {
    preview: preview?.tabId === tab?.tabId && preview?.url === tab?.url ? preview : null,
    error,
  };
}
