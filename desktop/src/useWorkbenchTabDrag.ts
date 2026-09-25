import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";

type TabDrag = {
  id: string;
  pointerId: number;
  source: HTMLElement;
  startX: number;
  startScroll: number;
  centerX: number;
  width: number;
  maxScroll: number;
  clientX: number;
  clientY: number;
  moved: boolean;
};
type DragPreview = { id: string; target: string; side: "before" | "after"; offset: number };

// Pointer capture keeps tab sorting independent of native WebView file drops.
export function useWorkbenchTabDrag(enabled: boolean, onReorder: (source: string, target: string) => void) {
  const strip = useRef<HTMLDivElement>(null);
  const drag = useRef<TabDrag | null>(null);
  const frame = useRef(0);
  const suppressClick = useRef(false);
  const [preview, setPreview] = useState<DragPreview | null>(null);

  const measure = (): DragPreview | null => {
    const current = drag.current;
    const row = strip.current;
    if (!current?.moved || !row) return null;
    const bounds = row.getBoundingClientRect();
    const elements = Array.from(row.querySelectorAll<HTMLElement>("[data-tab-id]"));
    const sourceIndex = elements.findIndex((element) => element.dataset.tabId === current.id);
    if (sourceIndex < 0) return null;
    const inside = current.clientX >= bounds.left && current.clientX <= bounds.right
      && current.clientY >= bounds.top && current.clientY <= bounds.bottom;
    const center = current.centerX + current.clientX - current.startX;
    // Keep the translated tab inside the viewport so it cannot grow scrollWidth.
    const visualCenter = Math.max(bounds.left + current.width / 2, Math.min(bounds.right - current.width / 2, center));
    const offset = current.width > bounds.width ? 0
      : visualCenter - current.centerX + row.scrollLeft - current.startScroll;
    const targetIndex = elements.filter((element) => {
      if (element.dataset.tabId === current.id) return false;
      const rect = element.getBoundingClientRect();
      return center > rect.left + rect.width / 2;
    }).length;
    return {
      id: current.id,
      target: inside ? elements[targetIndex].dataset.tabId! : current.id,
      side: targetIndex > sourceIndex ? "after" : "before",
      offset,
    };
  };

  const scrollAtEdge = () => {
    const current = drag.current;
    const row = strip.current;
    if (!current?.moved || !row) return;
    const bounds = row.getBoundingClientRect();
    if (current.clientY >= bounds.top && current.clientY <= bounds.bottom
      && current.clientX >= bounds.left && current.clientX <= bounds.right) {
      const edge = Math.min(28, bounds.width / 4);
      const delta = current.clientX < bounds.left + edge ? -8
        : current.clientX > bounds.right - edge ? 8 : 0;
      const previous = row.scrollLeft;
      row.scrollLeft = Math.max(0, Math.min(current.maxScroll, previous + delta));
      if (row.scrollLeft !== previous) setPreview(measure());
    }
    frame.current = requestAnimationFrame(scrollAtEdge);
  };

  const reset = () => {
    const current = drag.current;
    drag.current = null;
    cancelAnimationFrame(frame.current);
    frame.current = 0;
    if (current?.source.hasPointerCapture(current.pointerId))
      current.source.releasePointerCapture(current.pointerId);
    setPreview(null);
  };

  useEffect(() => {
    if (!enabled) reset();
    const cancel = () => reset();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && drag.current) {
        event.preventDefault();
        reset();
      }
    };
    window.addEventListener("blur", cancel);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("blur", cancel);
      window.removeEventListener("keydown", escape);
      reset();
    };
  }, [enabled]);

  return {
    strip,
    preview,
    prepareClick() {
      if (!drag.current) suppressClick.current = false;
    },
    begin(event: ReactPointerEvent<HTMLElement>, id: string) {
      if (!enabled || event.button !== 0 || event.isPrimary === false || drag.current) return;
      suppressClick.current = false;
      const rect = event.currentTarget.getBoundingClientRect();
      drag.current = {
        id, pointerId: event.pointerId, source: event.currentTarget,
        startX: event.clientX, startScroll: strip.current?.scrollLeft || 0,
        centerX: rect.left + rect.width / 2,
        width: rect.width,
        maxScroll: Math.max(0, (strip.current?.scrollWidth || 0) - (strip.current?.clientWidth || 0)),
        clientX: event.clientX, clientY: event.clientY, moved: false,
      };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    move(event: ReactPointerEvent) {
      const current = drag.current;
      if (!current || event.pointerId !== current.pointerId) return;
      current.clientX = event.clientX;
      current.clientY = event.clientY;
      if (!current.moved && Math.abs(current.clientX - current.startX) < 6) return;
      current.moved = true;
      suppressClick.current = true;
      event.preventDefault();
      setPreview(measure());
      if (!frame.current) frame.current = requestAnimationFrame(scrollAtEdge);
    },
    end(event: ReactPointerEvent) {
      const current = drag.current;
      if (!current || event.pointerId !== current.pointerId) return;
      current.clientX = event.clientX;
      current.clientY = event.clientY;
      const result = measure();
      reset();
      if (result && result.id !== result.target) onReorder(result.id, result.target);
    },
    cancel(event: ReactPointerEvent) {
      if (event.pointerId === drag.current?.pointerId) reset();
    },
    click(event: ReactMouseEvent) {
      // A completed pointer drag also generates a click. Keep the active panel.
      if (suppressClick.current && event.detail !== 0) {
        event.preventDefault();
        event.stopPropagation();
        suppressClick.current = false;
      }
    },
  };
}
