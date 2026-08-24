import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { coreApi } from "./coreApi";
import { parseThemePreference, resolveTheme, THEME_STORAGE_KEY } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import "./App.css";

type VoiceState = {
  active: boolean;
  status: string;
  error: string;
};

function titleFor(status: string): string {
  if (status.includes("מפעיל") || status.includes("פותח")) return "מפעיל האזנה";
  if (status.includes("מתמלל") || status.includes("מעבד")) return "מעבד קול";
  if (status.includes("מפסיק")) return "מפסיק האזנה";
  return "האזנה פעילה";
}

export function VoiceOverlayWindow({ fixture = false }: { fixture?: boolean }) {
  const preference = parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY));
  const theme = resolveTheme(preference, matchMedia("(prefers-color-scheme: dark)").matches);
  const expanded = new URLSearchParams(location.search).get("expanded") === "1";
  const [status, setStatus] = useState("אפשר לדבר עכשיו");
  const icons = legacyAssets(theme);
  useEffect(() => {
    if (fixture) return;
    let stopped = false;
    const poll = async () => {
      try {
        const state = await coreApi<VoiceState>("GET", "/v2/audio/voice/status");
        if (stopped) return;
        setStatus(state.error || state.status || "אפשר לדבר עכשיו");
        if (!state.active) void invoke("desktop_hide_voice_overlay");
      } catch {
        if (!stopped) void invoke("desktop_hide_voice_overlay");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 300);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [fixture]);
  const cancel = async () => {
    try {
      await coreApi("POST", "/v2/audio/voice/stop", {}, true);
    } finally {
      await invoke("desktop_hide_voice_overlay");
    }
  };
  return (
    <main className={`voice-overlay-root theme-${theme}`} data-theme={theme}>
      <section className="voice-listening-overlay" role="status" aria-live="polite">
        <button type="button" aria-label="בטל האזנה" title="בטל האזנה" onClick={() => void cancel()}>
          <LegacyIcon src={icons.close} size={18} />
        </button>
        {expanded && <button type="button" aria-label="פתח את סמארטי" title="פתח את סמארטי" onClick={() => void invoke("desktop_focus_main")}>
          <LegacyIcon src={icons.voiceOverlayOpen} size={18} />
        </button>}
        <div>
          <strong>{titleFor(status)}</strong>
          <span>{status || "אפשר לדבר עכשיו"}</span>
        </div>
        <img src={icons.voiceListening} alt="" />
      </section>
    </main>
  );
}
