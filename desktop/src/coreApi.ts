import { invoke } from "@tauri-apps/api/core";
import { publishSettingsChange } from "./settingsChanges";

interface RawResponse { status: number; body: { data?: unknown; error?: string; detail?: string } }
export class CoreApiError extends Error { constructor(message: string, public status = 0) { super(message); } }
const pendingMutations = new Map<string, string>();

export async function coreApi<T>(method: string, path: string, body?: unknown, idempotent: boolean | string = false): Promise<T> {
  const identity = idempotent === true ? JSON.stringify([method, path, body ?? null]) : "";
  const key = typeof idempotent === "string" ? idempotent : idempotent ? pendingMutations.get(identity) || crypto.randomUUID() : null;
  if (identity && key) pendingMutations.set(identity, key);
  const response = await invoke<RawResponse>("core_api", { request: {
    method, path, body: body ?? null,
    idempotencyKey: key,
  }});
  if (identity && response.status < 500) pendingMutations.delete(identity);
  if (response.status < 200 || response.status >= 300 || response.body.error) {
    const message = response.body.detail === "model_required"
      ? "יש לבחור מודל בהגדרות הספק לפני שליחת הודעה."
      : response.body.detail || response.body.error || `Core API ${response.status}`;
    throw new CoreApiError(message, response.status);
  }
  publishSettingsChange(method, path, body);
  return response.body.data as T;
}

export function encodePath(value: string) { return encodeURIComponent(value); }
