import { useEffect, useRef, useState } from "react";
import { coreApi } from "./coreApi";
import { ConfirmDialog, PageHero } from "./SettingsManagement";

type Timeframe = "all" | "today" | "week" | "month";
type UsageModel = {
  model: string;
  tokens: number;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  cache_write_tokens: number;
  cost_usd: number | null;
  cost_status: "recorded" | "estimated" | "local" | "unavailable";
};
export type UsageSnapshot = {
  schema_version: 2;
  timeframe: Timeframe;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  cache_write_tokens: number;
  cost_usd: number | null;
  known_cost_usd: number;
  unpriced_models: number;
  pricing?: { refreshing: boolean; refresh_failed: boolean; cached: boolean; updated_at: string };
  models: UsageModel[];
};
const periods: [Timeframe, string][] = [
  ["today", "היום"], ["week", "7 ימים"], ["month", "30 ימים"], ["all", "כל התקופות"],
];
const cacheKey = (period: Timeframe) => `smarti.management.usage-v2.${period}`;
const count = (value: number) => Number(value || 0).toLocaleString("he-IL");
export function formatUsageCost(value: number | null) {
  if (value === null || !Number.isFinite(value)) return "לא זמין";
  if (value > 0 && value < 0.01) return "<$0.01";
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function readCache(period: Timeframe): UsageSnapshot | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(cacheKey(period)) || "null");
    return value?.schema_version === 2 && value.timeframe === period && Array.isArray(value.models) &&
      typeof value.total_tokens === "number" ? value : null;
  } catch { return null; }
}
function writeCache(period: Timeframe, value: UsageSnapshot) {
  try { sessionStorage.setItem(cacheKey(period), JSON.stringify(value)); } catch { /* Optional cache. */ }
}

export function UsageView() {
  const [timeframe, setTimeframe] = useState<Timeframe>("today");
  const [data, setData] = useState<UsageSnapshot | null>(() => readCache("today"));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [clearError, setClearError] = useState("");
  const generation = useRef(0);
  const clearPending = useRef(false);
  const snapshot = data?.timeframe === timeframe ? data : null;

  useEffect(() => {
    const current = ++generation.current;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    setData(readCache(timeframe));
    setUpdatedAt(null);
    setError("");
    if (clearing) return;
    setLoading(true);
    const load = async () => {
      try {
        const value = await coreApi<UsageSnapshot>("GET", `/v2/management/usage?timeframe=${timeframe}`);
        if (current !== generation.current) return;
        if (value?.schema_version !== 2) {
          throw new Error("שירות נתוני השימוש עדיין מריץ גרסה קודמת. יש לפתוח מחדש את Smarti כדי לטעון את העדכון.");
        }
        setData(value);
        writeCache(timeframe, value);
        setUpdatedAt(new Date());
        setLoading(false);
        setError("");
        attempts = 0;
        timer = setTimeout(() => void load(), value.pricing?.refreshing ? 1_000 : 15_000);
      } catch (reason) {
        if (current !== generation.current) return;
        if (attempts < 2) {
          timer = setTimeout(() => void load(), 800 * 2 ** attempts++);
        } else {
          setLoading(false);
          setError(reason instanceof Error && reason.message.startsWith("שירות נתוני השימוש")
            ? reason.message : "לא ניתן לטעון את נתוני השימוש כרגע. אפשר לנסות שוב.");
          timer = setTimeout(() => { attempts = 0; void load(); }, 15_000);
        }
      }
    };
    void load();
    return () => { generation.current++; clearTimeout(timer); };
  }, [timeframe, refresh, clearing]);

  const clear = async () => {
    if (clearPending.current) return;
    clearPending.current = true;
    generation.current++; // Discard any read that started before the deletion.
    setClearing(true);
    setClearError("");
    try {
      const value = await coreApi<UsageSnapshot>("DELETE", "/v2/management/usage", {}, true);
      for (const [period] of periods) {
        try { sessionStorage.removeItem(cacheKey(period)); } catch { /* Optional cache. */ }
      }
      setData({ ...value, timeframe });
      setConfirmClear(false);
    } catch {
      setClearError("ניקוי הנתונים נכשל. אפשר לנסות שוב.");
    } finally {
      clearPending.current = false;
      setClearing(false);
    }
  };

  const partial = Boolean(snapshot?.unpriced_models);
  return (
    <div className="management-page usage-page" dir="rtl">
      <PageHero title="שימוש ועלויות" description="סיכום הטוקנים והעלויות של השימוש ב־Smarti, לפי תקופה ומודל."
        actions={<button className="danger" disabled={clearing} onClick={() => { setClearError(""); setConfirmClear(true); }}>ניקוי נתונים</button>} />
      <div className="usage-toolbar">
        <div className="segmented" role="group" aria-label="תקופת שימוש">
          {periods.map(([id, label]) => <button key={id} className={timeframe === id ? "active" : ""}
            aria-pressed={timeframe === id} disabled={clearing} onClick={() => setTimeframe(id)}>{label}</button>)}
        </div>
        <div className="usage-refresh">
          <span role="status" aria-live="polite">{clearing ? "מנקה נתונים…" : loading ? (snapshot ? "מעדכן נתונים…" : "טוען נתוני שימוש…") :
            updatedAt ? `עודכן ב־${updatedAt.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}` : snapshot ? "מציג נתונים שמורים" : ""}</span>
          <button className="ui-button ui-button--secondary" disabled={loading || clearing} onClick={() => setRefresh(value => value + 1)}>רענון</button>
        </div>
      </div>
      {error && <p className="management-notice" role="alert">{error}{snapshot && " מוצגים הנתונים האחרונים שנשמרו."}</p>}
      <div className="usage-summary" aria-busy={loading}>
        <section className="usage-stat usage-stat--primary"><span>סה״כ טוקנים</span><strong dir="ltr">{snapshot ? count(snapshot.total_tokens) : "—"}</strong><small>{snapshot ? `${count(snapshot.models.length)} מודלים בתקופה שנבחרה` : "ממתין לנתונים"}</small></section>
        <section className="usage-stat"><span>קלט</span><strong dir="ltr">{snapshot ? count(snapshot.input_tokens) : "—"}</strong><small>כולל טוקנים מהמטמון</small></section>
        <section className="usage-stat"><span>פלט</span><strong dir="ltr">{snapshot ? count(snapshot.output_tokens) : "—"}</strong><small>טוקנים שנוצרו בתשובות</small></section>
        <section className="usage-stat usage-stat--cost"><span>{partial ? "עלות זמינה · סיכום חלקי" : "עלות מוערכת"}</span><strong dir="ltr">{snapshot ? formatUsageCost(partial ? snapshot.known_cost_usd : snapshot.cost_usd) : "—"}</strong><small>דולר ארה״ב (USD)</small></section>
      </div>
      {snapshot && <>
        <p className="usage-pricing-note" aria-live="polite">{snapshot.pricing?.refreshing && "מעדכן את תעריפי המודלים… העלויות יתעדכנו עם סיום הטעינה. "}{snapshot.pricing?.refresh_failed && "עדכון התעריפים אינו זמין כרגע. החישוב משתמש בתעריפים המקומיים הזמינים. "}העלות מבוססת על העלות שנרשמה או על התעריפים הזמינים, ועשויה להיות שונה מהחיוב בפועל.{partial && ` חסר תעריף עבור ${count(snapshot.unpriced_models)} מהמודלים; הם אינם כלולים בסיכום העלות.`}</p>
        {snapshot.models.length ? <section className="usage-details" aria-label="פירוט שימוש לפי מודל">
          <header><h3>פירוט לפי מודל</h3><span>{count(snapshot.models.length)} מודלים</span></header>
          <div className="usage-table-scroll"><table className="usage-table">
            <thead><tr><th scope="col">מודל</th><th scope="col">קלט</th><th scope="col">פלט</th><th scope="col">סה״כ טוקנים</th><th scope="col">עלות (USD)</th></tr></thead>
            <tbody>{snapshot.models.map(item => <tr key={item.model}>
              <th scope="row"><bdi title={item.model}>{item.model}</bdi>{Boolean(item.cached_input_tokens || item.cache_write_tokens) && <small>מתוך הקלט: {count(item.cached_input_tokens)} מהמטמון{item.cache_write_tokens ? ` · ${count(item.cache_write_tokens)} נכתבו למטמון` : ""}</small>}</th>
              <td><bdi>{count(item.input_tokens)}</bdi></td><td><bdi>{count(item.output_tokens)}</bdi></td><td className="usage-tokens-total"><bdi>{count(item.tokens)}</bdi></td>
              <td><bdi className={item.cost_usd === null ? "usage-unpriced" : "usage-model-cost"}>{formatUsageCost(item.cost_usd)}</bdi><small>{item.cost_status === "recorded" ? "עלות מתועדת" : item.cost_status === "local" ? "מודל מקומי" : item.cost_status === "unavailable" ? "חסר תעריף" : "מוערכת"}</small></td>
            </tr>)}</tbody>
          </table></div>
        </section> : <section className="usage-empty"><h3>אין שימוש בתקופה הזו</h3><p>נתוני שימוש יופיעו כאן אחרי שימוש במודלים.</p>{timeframe !== "all" && <button className="ui-button ui-button--secondary" onClick={() => setTimeframe("all")}>הצג את כל התקופות</button>}</section>}
      </>}
      {confirmClear && <ConfirmDialog title="ניקוי נתוני שימוש" danger
        description={clearError || "הנתונים המקומיים יאופסו לאחר יצירת גיבוי. פעולה זו אינה מוחקת היסטוריית שיחות."}
        confirmLabel={clearing ? "מנקה…" : "ניקוי הנתונים"}
        onCancel={() => { if (!clearPending.current) setConfirmClear(false); }} onConfirm={() => void clear()} />}
    </div>
  );
}
