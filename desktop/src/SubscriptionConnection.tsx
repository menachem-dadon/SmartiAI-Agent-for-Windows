import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Button, ChoiceField } from "./design-system";
import { ManagementFeedback } from "./managementFeedback";
import { coreApi, encodePath } from "./coreApi";

export const subscriptionProviders = ["anthropic_claude_code_signin", "google_antigravity_signin"];
type Connection = { state: string; message: string; id?: string; operation_id?: string; install_url?: string; connection?: Connection };

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
      setConnection(result);
      setOperation(result.state === "running" ? result.id || "" : "");
      if (result.state !== "running") await onChanged();
    } catch (reason) {
      if (revision === generation.current) setError(String(reason));
    } finally { if (revision === generation.current) setBusy(false); }
  };
  const blocked = connection?.state === "policy_conflict";
  return <div>
    {claude && <ChoiceField label="שיטת התחברות ל־Claude Code" value={strategy}
      options={[{ value: "claude_login", label: "כניסה רגילה" }, { value: "setup_token_env", label: "אסימון מסביבת ההפעלה" }]}
      disabled={busy || Boolean(operation)} onValueChange={value => {
        setBusy(true); setError("");
        void onStrategyChange(value).catch(reason => setError(`שיטת ההתחברות לא נשמרה: ${String(reason)}`)).finally(() => setBusy(false));
      }} />}
    <ManagementFeedback message={error || connection?.message || "בודק את מצב רכיב החיבור…"} />
    <div className="inline-actions codex-actions">
      {claude && strategy === "claude_login" && <Button variant="primary" disabled={busy || Boolean(operation)} onClick={() => void action("login")}>התחבר עם Claude Code</Button>}
      <Button icon="plug" disabled={busy || Boolean(operation)} onClick={() => void action("check")}>בדוק חיבור</Button>
      {operation ? <Button disabled={busy} onClick={() => void action("cancel")}>בטל התחברות</Button>
        : <Button disabled={busy} onClick={() => void action("disconnect")}>נתק מסמארטי</Button>}
      {connection?.install_url && <Button disabled={busy} onClick={() => {
        void invoke("open_chat_link", { target: connection.install_url, local: false })
          .catch(reason => setError(`פתיחת אתר ההתקנה נכשלה: ${String(reason)}`));
      }}>התקנה והנחיות</Button>}
    </div>
    {claude && strategy === "setup_token_env" && <p className="secret-instructions">
      במסוף של Claude Code הפעל <bdi>claude setup-token</bdi> והגדר <bdi>CLAUDE_CODE_OAUTH_TOKEN</bdi> בסביבת ההפעלה.
      לאחר שינוי האסימון הפעל מחדש את סמארטי. אין להדביק אותו כאן; הוא אינו נשמר בהגדרות.
    </p>}
    <p className="secret-instructions">{claude ? "נדרש מנוי Claude מתאים; חשבון חינמי אינו כולל חיבור זה. הכלי הרשמי מנהל את פרטי הכניסה." : blocked ? "גילוי המודלים זמין לצורך אבחון; הוא אינו מעיד שהחיבור לשיחה מוכן." : "החיבור דורש רכיב רשמי ותמיכה בבידוד כלים."}
      {" "}מכסת המנוי אינה זמינה כאן. ניתוק מסמארטי אינו מוציא מהחשבון בכלי הרשמי.
    </p>
  </div>;
}
