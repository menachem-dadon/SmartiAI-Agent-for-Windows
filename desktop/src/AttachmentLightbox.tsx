import { useEffect, useRef, useState } from "react";
import { Dialog } from "./design-system";

export function AttachmentLightbox({ source, name, onClose }: { source: string; name: string; onClose: () => void }) {
  const viewport = useRef<HTMLDivElement>(null), image = useRef<HTMLImageElement>(null);
  const [closing, setClosing] = useState(false);
  const close = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? onClose() : setClosing(true);
  useEffect(() => { if (!closing) return; const timer = setTimeout(onClose, 160); return () => clearTimeout(timer); }, [closing, onClose]);
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const current = useRef(view); current.current = view;
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ distance?: number; scale: number; x: number; y: number; px: number; py: number; outside: boolean; moved: boolean }>({ scale: 1, x: 0, y: 0, px: 0, py: 0, outside: false, moved: false });
  const adjust = (scale: number, x = current.current.x, y = current.current.y) => {
    const box = viewport.current, img = image.current;
    scale = Math.max(1, Math.min(8, scale));
    const maxX = Math.max(0, ((img?.offsetWidth || 0) * scale - (box?.clientWidth || 0)) / 2);
    const maxY = Math.max(0, ((img?.offsetHeight || 0) * scale - (box?.clientHeight || 0)) / 2);
    setView({ scale, x: Math.max(-maxX, Math.min(maxX, x)), y: Math.max(-maxY, Math.min(maxY, y)) });
  };
  useEffect(() => {
    const node = viewport.current;
    const wheel = (event: WheelEvent) => { event.preventDefault(); adjust(current.current.scale * Math.exp(-event.deltaY * .002)); };
    node?.addEventListener("wheel", wheel, { passive: false });
    const resize = () => adjust(current.current.scale);
    window.addEventListener("resize", resize);
    return () => { node?.removeEventListener("wheel", wheel); window.removeEventListener("resize", resize); };
  }, []);
  return <Dialog open title={name} className={`attachment-lightbox ${closing ? "is-closing" : ""}`} initialFocus={viewport} onClose={close}>
    <div ref={viewport} className="attachment-lightbox-view" tabIndex={0} aria-label="תמונה מוגדלת. זום בגלגלת, בצביטה או במקשי פלוס ומינוס. איפוס במקש אפס." onKeyDown={event => {
      if (["+", "=", "-", "0"].includes(event.key)) { event.preventDefault(); adjust(event.key === "0" ? 1 : current.current.scale * (event.key === "-" ? .8 : 1.25)); }
    }} onPointerDown={event => {
      pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const points = [...pointers.current.values()];
      gesture.current = { ...current.current, px: event.clientX, py: event.clientY,
        outside: event.target === event.currentTarget, moved: points.length > 1,
        distance: points.length === 2 ? Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y) : undefined };
      event.currentTarget.setPointerCapture(event.pointerId);
    }} onPointerMove={event => {
      if (!pointers.current.has(event.pointerId)) return;
      pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const points = [...pointers.current.values()], start = gesture.current;
      if (points.length > 1 || Math.hypot(event.clientX - start.px, event.clientY - start.py) > 4) start.moved = true;
      if (points.length === 2 && start.distance) adjust(start.scale * Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y) / start.distance);
      else if (current.current.scale > 1) adjust(start.scale, start.x + event.clientX - start.px, start.y + event.clientY - start.py);
    }} onPointerUp={event => {
      const start = gesture.current;
      const dragged = start.moved || Math.hypot(event.clientX - start.px, event.clientY - start.py) > 4;
      pointers.current.delete(event.pointerId);
      if (!pointers.current.size && start.outside && !dragged) close();
      const remaining = [...pointers.current.values()][0];
      if (remaining) gesture.current = { ...current.current, px: remaining.x, py: remaining.y, outside: false, moved: true };
    }} onPointerCancel={event => pointers.current.delete(event.pointerId)}>
      <img ref={image} src={source} alt={name} draggable={false} style={{ transform: `translate(${view.x}px,${view.y}px) scale(${view.scale})` }} onDoubleClick={() => adjust(current.current.scale === 1 ? 2 : 1)} />
    </div>
  </Dialog>;
}
