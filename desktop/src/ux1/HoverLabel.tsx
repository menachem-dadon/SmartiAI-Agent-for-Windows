import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";

// One readable line at rest. Overflow travels at 72px/s on hover/focus,
// without endpoint dwell, and respects reduced motion.
export function HoverLabel({ text }: { text: string }) {
  const viewport = useRef<HTMLSpanElement>(null);
  const content = useRef<HTMLSpanElement>(null);
  const [overflow, setOverflow] = useState(0);
  const [rtl, setRtl] = useState(true);
  useLayoutEffect(() => {
    const measure = () => {
      if (!viewport.current || !content.current) return;
      setOverflow(Math.max(0, content.current.scrollWidth - viewport.current.clientWidth));
      setRtl(getComputedStyle(viewport.current).direction === "rtl");
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (viewport.current) observer.observe(viewport.current);
    return () => observer.disconnect();
  }, [text]);
  return <span ref={viewport} className="ux-marquee" dir="auto" title={text} data-overflow={overflow > 1} style={{ "--marquee-shift": `${rtl ? overflow : -overflow}px`, "--marquee-duration": `${Math.max(1.2, overflow / 72)}s` } as CSSProperties}><span ref={content} className="ux-marquee-text">{text}</span></span>;
}
