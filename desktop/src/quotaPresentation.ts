export function quotaResetLabel(timestamp: number | undefined, period: "five_hour" | "weekly", now = Date.now()) {
  if (!timestamp || !Number.isFinite(timestamp)) return "";
  const date = new Date(timestamp * 1000);
  if (!Number.isFinite(date.getTime())) return "";
  if (period === "five_hour" || (date.getTime() >= now && date.getTime() - now <= 86_400_000)) {
    return new Intl.DateTimeFormat("he-IL", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
  }
  return new Intl.DateTimeFormat("he-IL", { day: "numeric", month: "short" }).format(date);
}
