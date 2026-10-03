export type BrowserProfile = "persistent" | "guest";
export type BrowserTab = { tabId: string; workspaceId?: string; targetId: string; webviewLabel: string; profile: BrowserProfile; url: string; title: string; loading: boolean; active: boolean; crashed: boolean; pinned: boolean; faviconUrl: string; audioPlaying: boolean };
export type BrowserSnapshot = { tabs: BrowserTab[]; activeTabId: string | null; transport: "webview2-in-process-cdp"; remoteDebuggingPort: number | null };
// Rust's browser_status reports tabs as an array. Older count-shaped data is
// accepted defensively; missing or malformed status is unknown, never zero.
export function browserTargetCount(snapshot: unknown): number | null {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) return null;
  const status = snapshot as { tabs?: unknown; target_count?: unknown };
  if (Array.isArray(status.tabs)) return status.tabs.length;
  for (const value of [status.target_count, status.tabs]) {
    if (typeof value !== "number" && (typeof value !== "string" || !value.trim())) continue;
    const count = Number(value);
    if (Number.isSafeInteger(count) && count >= 0) return count;
  }
  return null;
}
let requestSequence = 0;
export function activeTab(snapshot: BrowserSnapshot): BrowserTab | null { return snapshot.tabs.find((tab) => tab.tabId === snapshot.activeTabId) ?? null; }
export function workspaceBrowserTabs(snapshot: BrowserSnapshot, workspaceId: string): BrowserTab[] {
  return workspaceId ? snapshot.tabs.filter((tab) => tab.workspaceId === workspaceId) : snapshot.tabs;
}
export function workspaceActiveTab(snapshot: BrowserSnapshot, workspaceId: string, preferredId?: string): BrowserTab | null {
  const tabs = workspaceBrowserTabs(snapshot, workspaceId);
  return tabs.find((tab) => tab.tabId === snapshot.activeTabId)
    ?? tabs.find((tab) => tab.tabId === preferredId)
    ?? tabs[0] ?? null;
}
export function pageTitle(tab: BrowserTab): string {
  if (tab.crashed) return "הכרטיסייה קרסה";
  if (tab.title.trim() && tab.title !== "כרטיסייה חדשה") return tab.title;
  try { return new URL(tab.url).hostname.replace(/^www\./, "") || "כרטיסייה חדשה"; } catch { return "כרטיסייה חדשה"; }
}
export function nextRequestId(): string { requestSequence += 1; return `ui-${Date.now().toString(36)}-${requestSequence.toString(36).padStart(4, "0")}`; }
