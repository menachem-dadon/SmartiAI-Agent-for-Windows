import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Button, ChoiceField } from "./design-system";
import { ManagementFeedback } from "./managementFeedback";
import { coreApi, encodePath } from "./coreApi";
import { ProviderConnectionStatus } from "./ProviderConnectionStatus";

export const subscriptionProviders = ["anthropic_claude_code_signin", "google_antigravity_signin"];
type Connection = { state: string; message: string; id?: string; operation_id?: string; install_url?: string; connection?: Connection;
  quota?: { available: boolean; groups: { name: string; buckets: { window: string; remaining_fraction: number; reset_time: string }[] }[] } };

export function SubscriptionConnection({ provider, strategy, onStrategyChange, onChanged }: {
  provider: string; strategy: string; onStrategyChange: (value: string) => Promise<void>; onChanged: () => Promise<void>;
}) {
  const [connection, setConnection] = useState<Connection>();
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [operation, setOperation] = useState("");
  const generation = useRef(0);
  const base = `/v2/providers/${encodePath(provider)}/connection`;
  const claude = provider === "anthropic_claude_code_signin";
  useEffect(() => {
    const revision = ++generation.current;
    setConnection(undefined); setError(""); setOperation(""); setBusy(false);
    void coreApi<Connection>("GET", base).then(result => {
      if (revision !== generation.current) return;
      setConnection(result); setOperation(result.operation_id || "");
    }).catch(reason => { if (revision === generation.current) setError(String(reason)); });
    return () => { generation.current++; };
  }, [base, strategy]);
  useEffect(() => {
    if (!operation) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await coreApi<Connection>("GET", `${base}/operations/${encodePath(operation)}`);
        if (stopped) return;
        setConnection(result.connection || result);
        if (result.state !== "running") { setOperation(""); await onChanged(); }
        else timer = setTimeout(() => void poll(), 1500);
      } catch (reason) {
        if (!stopped) {
          if ((reason as { status?: number })?.status === 404) {
            setOperation("");
            setError("פעולת ההתחברות אינה קיימת לאחר שינוי בחיבור. אפשר לבדוק חיבור או להתחבר מחדש.");
          } else {
            setError(`בדיקת ההתחברות נכשלה: ${String(reason)}`);
            timer = setTimeout(() => void poll(), 4000);
          }
        }
      }
    };
    timer = setTimeout(() => void poll(), 1000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [base, operation, onChanged]);
  const action = async (name: "login" | "check" | "disconnect" | "cancel") => {
    if (busy) return;
    const revision = generation.current;
    setBusy(true); setError("");
    try {
      const path = name === "cancel" ? `${base}/operations/${encodePath(operation)}/cancel` : `${base}/${name}`;
      const result = await coreApi<Connection>("POST", path, {}, true);
      if (revision !== generation.current) return;
      setConnection(result.connection || result);
      setOperation(result.state === "running" ? result.id || "" : "");
      if (result.state !== "running") await onChanged();
    } catch (reason) {
      if (revision === generation.current) setError(String(reason));
    } finally { if (revision === generation.current) setBusy(false); }
  };
  const blocked = connection?.state === "policy_conflict";
  const connected = connection?.state === "connected" || connection?.state === "configured";
  const needsHelp = connection && !["connected", "configured", "disconnected", "unchecked", "cancelled", "running", "login_in_progress"].includes(connection.state);
  return <div className="provider-connection">
    {claude && <ChoiceField label="שיטת התחברות ל־Claude Code" value={strategy}
      options={[{ value: "claude_login", label: "כניסה רגילה" }, { value: "setup_token_env", label: "אסימון מסביבת ההפעלה" }]}
      disabled={busy || Boolean(operation)} onValueChange={value => {
        setBusy(true); setError("");
        void onStrategyChange(value).catch(reason => setError(`שיטת ההתחברות לא נשמרה: ${String(reason)}`)).finally(() => setBusy(false));
      }} />}
    <ProviderConnectionStatus state={connection?.state} busy={busy || Boolean(operation)} />
    <ManagementFeedback message={error || (needsHelp ? connection.message : "")} />
    <div className="inline-actions codex-actions">
      <Button icon={connected ? "refresh" : "plug"} variant={connected ? "secondary" : "primary"} disabled={busy || Boolean(operation)} onClick={() => void action("check")}>{connected ? "בדוק חיבור" : "חבר לסמארטי"}</Button>
      {!connected && !blocked && connection?.state !== "missing_dependency" && (!claude || strategy === "claude_login") && <Button icon="external" disabled={busy || Boolean(operation)} onClick={() => void action("login")}>כניסה בכלי הרשמי</Button>}
      {operation ? <Button icon="stop" disabled={busy} onClick={() => void action("cancel")}>בטל</Button>
        : connected && <Button icon="close" disabled={busy} title="מנתק מסמארטי; החשבון בכלי הרשמי נשאר מחובר" onClick={() => void action("disconnect")}>נתק מסמארטי</Button>}
      {connection?.install_url && connection.state === "missing_dependency" && <Button icon="download" disabled={busy} onClick={() => {
        void invoke("open_chat_link", { target: connection.install_url, local: false })
          .catch(reason => setError(`פתיחת אתר ההתקנה נכשלה: ${String(reason)}`));
      }}>התקנה והנחיות</Button>}
    </div>
    {claude && strategy === "setup_token_env" && <p className="secret-instructions">
      במסוף של Claude Code הפעל <bdi>claude setup-token</bdi> והגדר <bdi>CLAUDE_CODE_OAUTH_TOKEN</bdi> בסביבת ההפעלה.
      לאחר שינוי האסימון הפעל מחדש את סמארטי. אין להדביק אותו כאן; הוא אינו נשמר בהגדרות.
    </p>}
  </div>;
}
