import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { IconButton } from "./design-system";
import type { BrowserAgentActivity } from "./browserState";

export function BrowserAgentControls({ agent }: { agent: BrowserAgentActivity }) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const paused = agent.state === "paused" || agent.state === "stopped";
  const control = async (action: string) => {
    setPending(true);
    try { await invoke("browser_agent_control", { tabId: agent.tabId, action }); setError(""); }
    catch { setError("לא ניתן לעדכן את השליטה בכרטיסייה"); }
    finally { setPending(false); }
  };
  return <div className="browser-agent-controls" dir="rtl">
    <span role="status">{paused ? "השליטה אצלך" : agent.state === "running" ? "Smarti עובד בדפדפן" : agent.state === "error" ? "הפעולה נעצרה" : "הדפדפן מוכן להמשך"}</span>
    <IconButton icon={paused ? "play" : "pause"} label={paused ? "החזרת השליטה ל־Smarti" : "השהיה והעברת השליטה אליי"} disabled={pending} onClick={() => void control(paused ? "resume" : "pause")} />
    {!paused && <IconButton icon="stop" label="עצירת פעולות Smarti בכרטיסייה" disabled={pending} onClick={() => void control("stop")} />}
    {error && <small role="alert">{error}</small>}
  </div>;
}
