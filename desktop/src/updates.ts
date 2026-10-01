import { invoke } from "@tauri-apps/api/core";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { coreApi } from "./coreApi";

export type AvailableUpdate = {
  version: string;
  body?: string;
  releaseUrl?: string;
  installer?: Update;
};

let pendingCheck: Promise<AvailableUpdate | null> | null = null;

// Manual and automatic checks use the same discovery and persistence path.
// Sharing an in-flight request also avoids simultaneous GitHub/feed requests.
export function checkForUpdates(): Promise<AvailableUpdate | null> {
  if (pendingCheck) return pendingCheck;
  pendingCheck = discoverAndRecord().finally(() => { pendingCheck = null; });
  return pendingCheck;
}

async function discoverAndRecord(): Promise<AvailableUpdate | null> {
  const signed = await invoke<boolean>("signed_updates_configured");
  let found: AvailableUpdate | null;
  if (signed) {
    const installer = await check({ timeout: 25_000 });
    found = installer ? {
      version: installer.version, body: installer.body, installer,
    } : null;
  } else {
    const result = await coreApi<{ update: AvailableUpdate | null }>(
      "GET", "/v2/management/updates",
    );
    found = result.update;
  }
  await coreApi("PATCH", "/v2/settings", { values: {
    updates_last_checked_at: new Date().toISOString(),
    updates_last_available_version: found?.version || "",
  } }, true);
  return found;
}
