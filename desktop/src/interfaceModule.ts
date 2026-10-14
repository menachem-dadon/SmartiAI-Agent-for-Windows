type InterfaceModule = "entry" | "app";
const RETRY_KEY = "smarti.desktop.interface-retry";
const RETRY_DELAYS = [400, 1200];
let reloadTimer: number | undefined;

// Chromium caches a rejected ES module in the current document. Repeating the
// same import (including React.lazy) cannot repair it; a new document can.
export function isModuleFetchFailure(error: unknown): boolean {
  return error instanceof Error && /failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed|unable to preload css for/i.test(error.message);
}

function retryKey() {
  return `${RETRY_KEY}.${new URLSearchParams(location.search).get("voice-overlay") === "1" ? "voice" : "main"}`;
}

export function recoverInterfaceModule(error: unknown, phase: InterfaceModule): boolean {
  if (!isModuleFetchFailure(error)) {
    console.error("Smarti interface module failed", { phase, kind: "evaluation" });
    return false;
  }
  if (reloadTimer !== undefined) return true;
  let attempt = RETRY_DELAYS.length;
  try {
    const saved = sessionStorage.getItem(retryKey());
    attempt = saved === null ? 0 : /^[0-2]$/.test(saved) ? Number(saved) : RETRY_DELAYS.length;
    if (attempt < RETRY_DELAYS.length) sessionStorage.setItem(retryKey(), String(attempt + 1));
  } catch {
    // Persisting the budget is required before navigating, including when a
    // read succeeds but the write is denied or the quota has been exhausted.
    attempt = RETRY_DELAYS.length;
  }
  const retry = attempt < RETRY_DELAYS.length;
  // Fixed metadata only: module URLs, exceptions, stacks and user data stay out.
  console.warn("Smarti interface module fetch failed", { phase, attempt, retry });
  if (retry) reloadTimer = window.setTimeout(() => window.location.reload(), RETRY_DELAYS[attempt]);
  return retry;
}

export async function loadInterfaceModule<T>(load: () => Promise<T>, phase: InterfaceModule): Promise<T> {
  try { return await load(); }
  catch (error) {
    if (recoverInterfaceModule(error, phase)) {
      // Keep the startup icon/Suspense visible until navigation. Do not retry a
      // partially evaluated module or restart Core and its background work.
      return new Promise<T>(() => {});
    }
    throw error;
  }
}

export function interfaceReady() {
  if (reloadTimer !== undefined) window.clearTimeout(reloadTimer);
  reloadTimer = undefined;
  try { sessionStorage.removeItem(retryKey()); } catch { /* Optional UI state. */ }
}

export function reloadInterface() {
  interfaceReady();
  window.location.reload();
}
