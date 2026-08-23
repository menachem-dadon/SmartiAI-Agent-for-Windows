import { invoke } from "@tauri-apps/api/core";

interface RawResponse { status: number; body: { data?: unknown; error?: string; detail?: string } }
export class CoreApiError extends Error { constructor(message: string, public status = 0) { super(message); } }

export async function coreApi<T>(method: string, path: string, body?: unknown, idempotent = false): Promise<T> {
  const response = await invoke<RawResponse>("core_api", { request: {
    method, path, body: body ?? null,
    idempotencyKey: idempotent ? crypto.randomUUID() : null,
  }});
  if (response.status < 200 || response.status >= 300 || response.body.error) {
    throw new CoreApiError(response.body.detail || response.body.error || `Core API ${response.status}`, response.status);
  }
  return response.body.data as T;
}

export function encodePath(value: string) { return encodeURIComponent(value); }

