import { useEffect, useRef, useState } from "react";
import { SmartyLiveOrb, type OrbState } from "./SmartyLiveOrb";

const labels: Record<OrbState, string> = { idle: "לייב מוכן", listening: "מקשיב", userSpeaking: "מקשיב לך", smartySpeaking: "סמארטי מדבר", thinking: "סמארטי חושב" };
export function LiveOrb({ state, level }: { state: OrbState; level: { current: number } }) {
  const canvas = useRef<HTMLCanvasElement>(null), orb = useRef<SmartyLiveOrb | null>(null);
  const [fallback, setFallback] = useState(false);
  useEffect(() => {
    const node = canvas.current!;
    const lost = () => setFallback(true);
    node.addEventListener("webglcontextlost", lost);
    try { orb.current = new SmartyLiveOrb(canvas.current!); } catch { setFallback(true); }
    return () => { node.removeEventListener("webglcontextlost", lost); orb.current?.destroy(); orb.current = null; };
  }, []);
  // RMS modulation reads state through a separate frame to avoid recreating GL.
  useEffect(() => { orb.current?.setState(state); let frame = 0;
    const tick = () => { if (state === "userSpeaking" || state === "smartySpeaking") orb.current?.feedAudioLevel(level.current); frame = requestAnimationFrame(tick); };
    frame = requestAnimationFrame(tick); return () => cancelAnimationFrame(frame);
  }, [state, level]);
  return <div className={`live-orb-area${fallback ? " is-fallback" : ""}`} data-state={state}>
    <canvas ref={canvas} className="live-orb" aria-hidden="true" />
    <span className="live-orb-label" role="status">{labels[state]}</span>
  </div>;
}
