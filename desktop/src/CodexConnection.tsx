import { useEffect, useRef, useState } from "react";
import { Button } from "./design-system";
import { coreApi } from "./coreApi";
import { ManagementFeedback } from "./managementFeedback";
import { ProviderConnectionStatus } from "./ProviderConnectionStatus";

export function CodexConnection({ onChanged }: { onChanged: () => Promise<void> }) {
  const [state, setState] = useState("unchecked"), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    void coreApi<{ state: string }>("POST", "/v2/management/settings/actions", { action: "codex_status" }, true)
      .then(data => { if (!stopped) setState(data.state); }).catch(reason => { if (!stopped) setError(String(reason)); });
    return () => { stopped = true; mounted.current = false; };
  }, []);
  const action = async (name: string) => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const data = await coreApi<{ state: string; message: string }>("POST", "/v2/management/settings/actions", { action: name }, true);
      if (!mounted.current) return;
      setState(data.state);
      if (!["connected", "not_connected", "disconnected"].includes(data.state)) setError(data.message);
      await onChanged();
    } catch (reason) { if (mounted.current) setError(String(reason)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const connected = state === "connected";
  return <div className="provider-connection">
    <ProviderConnectionStatus state={state} busy={busy} />
    <ManagementFeedback message={error} />
    <div className="inline-actions codex-actions">
      <Button icon={connected ? "refresh" : "plug"} variant={connected ? "secondary" : "primary"} disabled={busy} onClick={() => void action("codex_check")}>{connected ? "בדוק חיבור" : "חבר ל-Smarti"}</Button>
      {!connected && <Button icon="external" disabled={busy} onClick={() => void action("codex_login")}>כניסה לחשבון</Button>}
      {connected && <Button icon="close" disabled={busy} title="מוציא מהחשבון גם בכלי Codex הרשמי" onClick={() => void action("codex_logout")}>יציאה מהחשבון</Button>}
    </div>
  </div>;
}
