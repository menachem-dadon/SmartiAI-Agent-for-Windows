export type BrowserProfile = "persistent" | "guest";
export type BrowserTab = { tabId: string; targetId: string; webviewLabel: string; profile: BrowserProfile; url: string; title: string; loading: boolean; active: boolean; crashed: boolean; pinned: boolean; faviconUrl: string; audioPlaying: boolean };
export type BrowserSnapshot = { tabs: BrowserTab[]; activeTabId: string | null; transport: "webview2-in-process-cdp"; remoteDebuggingPort: number | null };
let requestSequence = 0;
export function activeTab(snapshot: BrowserSnapshot): BrowserTab | null { return snapshot.tabs.find((tab) => tab.tabId === snapshot.activeTabId) ?? null; }
export function pageTitle(tab: BrowserTab): string {
  if (tab.crashed) return "הכרטיסייה קרסה";
  if (tab.title.trim() && tab.title !== "כרטיסייה חדשה") return tab.title;
  try { return new URL(tab.url).hostname.replace(/^www\./, "") || "כרטיסייה חדשה"; } catch { return "כרטיסייה חדשה"; }
}
export function nextRequestId(): string { requestSequence += 1; return `ui-${Date.now().toString(36)}-${requestSequence.toString(36).padStart(4, "0")}`; }
