// Publish only completed writes. A settings page may unmount while its save is
// still in flight, so synchronization belongs to the API, not the page lifecycle.
const listeners = new Set<() => void>();
let revision = 0;

export function settingsRevision() { return revision; }

export function subscribeSettingsChanges(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function publishSettingsChange(method: string, path: string, body?: unknown) {
  const action = body && typeof body === "object" && "action" in body
    ? String(body.action) : "";
  const changed =
    (method === "PATCH" && path === "/v2/settings") ||
    (["PUT", "DELETE"].includes(method) && path.startsWith("/v2/settings/secrets/")) ||
    (method === "POST" && /^\/v2\/providers\/[^/]+\/reasoning$/.test(path)) ||
    (method === "POST" && path === "/v2/management/settings/actions" &&
      ["reset", "codex_status", "codex_check", "codex_login", "codex_logout"].includes(action));
  if (!changed) return;
  revision += 1;
  for (const listener of listeners) listener();
}
