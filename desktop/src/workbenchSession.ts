import { parseWorkbenchSnapshot, type WorkbenchSnapshot } from "./workspaceState";

// WebView session storage survives reload, but a new application WebView starts
// empty. Old Core preferences are deliberately left intact and no longer read
// as launchable tabs. Native/background owners are never closed by hydration.
const key = "smarti-workbench-session-v2";
export type WorkbenchSession = { snapshot: WorkbenchSnapshot; open: boolean; expanded: boolean; owner: string };
export function readWorkbenchSession(): WorkbenchSession {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || "null");
    const snapshot = parseWorkbenchSnapshot(value?.snapshot);
    if (snapshot && typeof value.owner === "string" && value.owner)
      return { snapshot, owner: value.owner, open: Boolean(value.open), expanded: Boolean(value.expanded) };
  } catch { /* A restricted/damaged cache must not block the product. */ }
  return { snapshot: { tabs: [], active: "" }, open: false, expanded: false, owner: crypto.randomUUID() };
}
export function writeWorkbenchSession(value: WorkbenchSession) {
  try { sessionStorage.setItem(key, JSON.stringify(value)); } catch { /* In-memory tabs remain usable. */ }
}
export function readPanelSession<T>(id: string, fallback: T): T {
  try { return JSON.parse(sessionStorage.getItem(`smarti-workbench-panel:${id}`) || "null") ?? fallback; }
  catch { return fallback; }
}
export function writePanelSession(id: string, value: unknown) {
  try { sessionStorage.setItem(`smarti-workbench-panel:${id}`, JSON.stringify(value)); } catch { /* cache only */ }
}
export function forgetPanelSession(id: string) {
  try { sessionStorage.removeItem(`smarti-workbench-panel:${id}`); } catch { /* cache only */ }
}
