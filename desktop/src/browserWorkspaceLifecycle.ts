import { invoke } from "@tauri-apps/api/core";
import type { BrowserProfile, BrowserSnapshot } from "./browserState";

const opening = new Map<string, Set<Promise<BrowserSnapshot>>>();
const closing = new Set<string>();

export function openBrowserWorkspace(workspaceId: string, profile: BrowserProfile, url: string) {
  if (closing.has(workspaceId)) return Promise.reject(new Error("לשונית הדפדפן נסגרת"));
  const request = invoke<BrowserSnapshot>("browser_open", { workspaceId: workspaceId || undefined, profile, url });
  const requests = opening.get(workspaceId) || new Set<Promise<BrowserSnapshot>>();
  opening.set(workspaceId, requests); requests.add(request);
  const finished = () => { requests.delete(request); if (!requests.size) opening.delete(workspaceId); };
  void request.then(finished, finished);
  return request;
}

export async function closeBrowserWorkspace(workspaceId: string) {
  closing.add(workspaceId);
  try {
    await Promise.allSettled([...(opening.get(workspaceId) || [])]);
    await invoke("browser_close_workspace", { workspaceId });
  } finally { closing.delete(workspaceId); }
}
