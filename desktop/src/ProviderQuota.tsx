import { useCallback, useEffect, useRef, useState } from "react";
import { coreApi, encodePath } from "./coreApi";
import { quotaResetLabel } from "./quotaPresentation";

type Window = { remaining_percent?: number; resets_at?: number };
export type ProviderQuotaData = { available: boolean; plan_type?: string; five_hour?: Window; weekly?: Window;
  groups?: { name: string; buckets: { name?: string; window: string; remaining_fraction: number; reset_time: string }[] }[] };
const providers = ["openai_codex_signin", "anthropic_claude_code_signin", "google_antigravity_signin"];

export function quotaWindows(provider: string, model: string, quota?: ProviderQuotaData | null) {
  if (provider !== "google_antigravity_signin") return [
    { key: "five_hour", label: "5 שעות", period: "five_hour" as const, ...quota?.five_hour },
    { key: "weekly", label: "שבוע", period: "weekly" as const, ...quota?.weekly },
  ];
  const family = model.startsWith("gemini") ? "gemini" : model.startsWith("claude") ? "claude" : model.startsWith("gpt") ? "gpt" : "";
  const groups = quota?.groups || [];
  const matching = family ? groups.filter(group => group.name.toLowerCase().includes(family)) : [];
  return (matching.length ? matching : groups).flatMap((group, index) => group.buckets.map((bucket, i) => ({
    key: `${index}:${i}`, label: `${matching.length || groups.length === 1 ? "" : `${group.name} · `}${bucket.window === "5h" ? "5 שעות" : bucket.window === "weekly" || bucket.window === "7d" ? "שבוע" : bucket.name || bucket.window}`,
    period: bucket.window === "5h" ? "five_hour" as const : "weekly" as const,
    remaining_percent: bucket.remaining_fraction * 100,
    resets_at: Date.parse(bucket.reset_time) / 1000,
  })));
}

export function useProviderQuota(provider: string, model: string) {
  const [snapshot, setSnapshot] = useState<{ provider: string; data: ProviderQuotaData } | null>(null), [loading, setLoading] = useState(false), [error, setError] = useState(false);
  const data = snapshot?.provider === provider ? snapshot.data : null;
  const request = useRef({ provider, generation: 0, fetched: 0, loading: false });
  if (request.current.provider !== provider) request.current = { provider, generation: request.current.generation + 1, fetched: 0, loading: false };
  const refresh = useCallback(async (minimumAge = 15) => {
    const owner = request.current;
    if (!providers.includes(provider) || owner.loading || Date.now() - owner.fetched < minimumAge * 1000) return;
    owner.loading = true; setLoading(true); setError(false);
    try {
      const result = await coreApi<ProviderQuotaData>("GET", `/v2/providers/${encodePath(provider)}/quota`);
      if (request.current !== owner) return;
      setSnapshot({ provider, data: result }); owner.fetched = Date.now();
    } catch { if (request.current === owner) setError(true); }
    finally { if (request.current === owner) { owner.loading = false; setLoading(false); } }
  }, [provider]);
  useEffect(() => {
    setSnapshot(null); setError(false); setLoading(false);
    if (!providers.includes(provider)) return;
    const first = window.setTimeout(() => void refresh(), 1600);
    const timer = window.setInterval(() => void refresh(), 60_000);
    return () => { clearTimeout(first); clearInterval(timer); };
  }, [provider, refresh]);
  const status = error ? "לא ניתן לטעון את המכסה כרגע" : !data ? "טוען נתוני מכסה…"
    : !data.available ? "נתוני המכסה אינם זמינים כרגע" : `${data.plan_type ? `תוכנית ${data.plan_type} · ` : ""}${loading ? "מתעדכן…" : "מעודכן כעת"}`;
  const windows = quotaWindows(provider, model, data);
  const summary = providers.includes(provider) ? <section className="codex-quota-summary" aria-label={provider === "openai_codex_signin" ? "מכסת Codex שנותרה" : "מכסת המנוי שנותרה"} title={status}>
    {windows.length ? windows.map(item => {
      const value = data?.available ? item.remaining_percent : undefined;
      const remaining = typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value))) : null;
      const reset = quotaResetLabel(item.resets_at, item.period);
      const detail = remaining === null ? status : reset ? `איפוס: ${reset}` : "זמן האיפוס אינו זמין";
      return <div className={`quota-window ${remaining === null ? "" : remaining < 20 ? "is-low" : remaining < 50 ? "is-medium" : "is-good"}`} key={item.key}
        title={`${status} · ${detail}`} aria-label={`${item.label}: ${remaining === null ? "המכסה אינה זמינה" : `${remaining}% נותרו`}. ${detail}`}>
        <p><b>{item.label}</b><em>{remaining === null ? "—" : `${remaining}%`}</em></p>
        <i aria-hidden="true"><span style={{ width: `${remaining ?? 0}%` }} /></i>
        <small>{remaining === null ? loading ? "טוען…" : "לא זמין" : reset || "לא זמין"}</small>
      </div>;
    }) : <small className="quota-unavailable">{status}</small>}
  </section> : undefined;
  return { summary, refresh };
}
