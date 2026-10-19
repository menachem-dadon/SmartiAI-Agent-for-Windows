import { useRef, useState, type CSSProperties, type InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "min" | "max" | "step" | "onChange" | "dir"> & {
  value: number; min: number; max: number; step?: number; dir?: "rtl" | "ltr";
  stops?: number[]; sliderClassName?: string; onValueChange: (value: number) => void;
};

/** Native range interaction with the shared reasoning slider's visual surface. */
export function Slider({ value, min, max, step = 1, dir = "rtl", stops = [], sliderClassName = "", onValueChange, ...props }: Props) {
  const slider = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState({ thumb: false, stop: -1 });
  const position = (next: number) => max > min ? Math.max(0, Math.min(1, (next - min) / (max - min))) : 0;
  return <div ref={slider} dir={dir} className={`sds-slider ${sliderClassName}`}
    style={{ "--sds-slider-position": position(value) } as CSSProperties}
    onPointerLeave={() => setHover({ thumb: false, stop: -1 })}
    onPointerMove={event => {
      if (props.disabled || event.pointerType === "touch" || !slider.current) return;
      const rect = slider.current.getBoundingClientRect(), thumb = slider.current.querySelector<HTMLElement>(".sds-slider-thumb")!.getBoundingClientRect();
      const half = parseFloat(getComputedStyle(slider.current).getPropertyValue("--sds-slider-thumb-size")) / 2;
      const distance = dir === "rtl" ? rect.right - event.clientX : event.clientX - rect.left;
      const stop = Math.abs(event.clientY - rect.top - rect.height / 2) <= 12
        ? stops.findIndex(next => Math.abs(distance - half - position(next) * (rect.width - 2 * half)) <= 10) : -1;
      const next = { thumb: event.clientX >= thumb.left && event.clientX <= thumb.right && event.clientY >= thumb.top && event.clientY <= thumb.bottom, stop };
      setHover(current => current.thumb === next.thumb && current.stop === next.stop ? current : next);
    }}>
    <span className="sds-slider-track" aria-hidden="true"><span className="sds-slider-fill" /></span>
    <span className={`sds-slider-thumb${hover.thumb ? " is-hovered" : ""}`} aria-hidden="true" />
    <input {...props} className={`sds-slider-input ${props.className || ""}`} type="range" dir={dir} min={min} max={max} step={step} value={value}
      onChange={event => onValueChange(event.currentTarget.valueAsNumber)} />
    {!!stops.length && <span className="sds-slider-stops" aria-hidden="true">{stops.map((next, i) =>
      <i key={next} style={{ "--sds-slider-stop-position": position(next) } as CSSProperties}
        className={`${next <= value ? "is-filled" : ""}${next === value ? " is-current" : ""}${i === hover.stop ? " is-hovered" : ""}`} />)}</span>}
  </div>;
}
