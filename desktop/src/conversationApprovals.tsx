import { useCallback, useRef, useState } from "react";
import { coreApi, encodePath } from "./coreApi";
import { Button, Icon } from "./design-system";
import type { Approval } from "./chatTypes";

// Mounted at App scope: navigation and tool-event replay never own or discard
// permission requests. The Core's durable queue is the source of truth.
export function useApprovalQueue() {
  const [items, setItems] = useState<Approval[]>([]);
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const inFlight = useRef(new Set<string>());
  const resolved = useRef(new Set<string>());
  const replace = useCallback((snapshot: Approval[]) => {
    setItems([...new Map(snapshot.map((item) => [item.id, item])).values()]
      .filter((item) => !resolved.current.has(item.id)));
  }, []);
  const resolve = useCallback(async (approval: Approval, approved: boolean) => {
    const id = approval.id;
    if (inFlight.current.has(id) || resolved.current.has(id)) return;
    inFlight.current.add(id);
    setBusy(new Set(inFlight.current));
    setErrors((current) => { const next = { ...current }; delete next[id]; return next; });
    try {
      await coreApi("POST", `/v2/approvals/${encodePath(id)}/resolve`, { approved }, true);
      resolved.current.add(id);
      setItems((current) => current.filter((item) => item.id !== id));
    } catch (reason) {
      setErrors((current) => ({ ...current, [id]: `לא ניתן לשלוח את ההחלטה: ${String(reason)}` }));
    } finally {
      inFlight.current.delete(id);
      setBusy(new Set(inFlight.current));
    }
  }, []);
  return { items, busy, errors, replace, resolve };
}

export function ConversationApprovals({ items, busy, errors, onResolve }: {
  items: Approval[];
  busy: Set<string>;
  errors: Record<string, string>;
  onResolve: (approval: Approval, approved: boolean) => void;
}) {
  if (!items.length) return null;
  return (
    <section className="conversation-approvals" aria-label="בקשות הרשאה" dir="rtl">
      <header><strong>ממתין לאישור שלך</strong><span>{items.length === 1 ? "בקשה אחת ממתינה" : `${items.length} בקשות ממתינות`}</span></header>
      <div className="conversation-approval-list">
        {items.map((approval) => (
          <details className={`conversation-approval risk-${approval.risk_level}`} key={approval.id} open>
            <summary>
              <Icon name="shield" /><strong>{approval.title || "אישור פעולה"}</strong>
              <span>{approval.risk_level === "high" ? "סיכון גבוה" : approval.risk_level === "low" ? "סיכון נמוך" : "סיכון בינוני"}</span>
            </summary>
            <pre dir="rtl" tabIndex={0}>{approval.prompt.replace(/\n[\t ]*\n+/g, "\n")}</pre>
            {errors[approval.id] && <p role="alert">{errors[approval.id]}</p>}
            <footer>
              <Button variant="ghost" disabled={busy.has(approval.id)} onClick={() => onResolve(approval, false)}>דחה</Button>
              <Button variant="primary" loading={busy.has(approval.id)} onClick={() => onResolve(approval, true)}>אשר</Button>
              {busy.has(approval.id) && <span role="status">שולח החלטה...</span>}
            </footer>
          </details>
        ))}
      </div>
    </section>
  );
}
