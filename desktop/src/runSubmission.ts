import { coreApi, CoreApiError, encodePath } from "./coreApi";

interface Submission {
  sessionId: string; text: string; attachments: { path: string; name: string; size?: number }[];
  provider: string; model: string; isVoice?: boolean;
}
interface Pending {
  key: string; sessionId: string; handles: string[]; provider: string; model: string; isVoice: boolean;
}
const storageKey = "smarti.pendingRunSubmissions.v1";
function sessionStore(): Storage | undefined {
  try { return globalThis.sessionStorage; } catch { return undefined; }
}

/** Retain the identity of a draft through ambiguous delivery failures/reloads.
 * Storage contains only hashes, IDs and provider/model names, never draft text,
 * attachment paths, connection tokens or provider credentials.
 */
export class RunSubmission {
  private pending: Record<string, Pending> = {};
  private inFlight = new Map<string, Promise<{ run_id: string; session_id: string }>>();
  constructor(private api: typeof coreApi = coreApi, private storage: Storage | undefined = sessionStore()) {
    try {
      const data = JSON.parse(storage?.getItem(storageKey) || "{}");
      if (data && typeof data === "object" && !Array.isArray(data)) this.pending = data;
    } catch { /* Memory still preserves identity when browser storage is unavailable. */ }
  }
  private save() {
    try { this.storage?.setItem(storageKey, JSON.stringify(this.pending)); } catch { /* Storage quota/privacy. */ }
  }
  async submit(input: Submission): Promise<{ run_id: string; session_id: string }> {
    for (const item of input.attachments) {
      if (item.size && item.size > 25 * 1024 * 1024) throw new Error(`${item.name}: הקובץ גדול מ־25MB`);
    }
    const identity = JSON.stringify([input.sessionId, input.text, input.attachments.map(item => item.path), !!input.isVoice]);
    const active = this.inFlight.get(identity);
    if (active) return active;
    const request = (async () => {
      const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(identity));
      const fingerprint = Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, "0")).join("");
      return this.deliver(input, fingerprint);
    })();
    this.inFlight.set(identity, request);
    try { return await request; } finally { this.inFlight.delete(identity); }
  }
  private async deliver(input: Submission, fingerprint: string): Promise<{ run_id: string; session_id: string }> {
    let pending = this.pending[fingerprint];
    if (!pending || typeof pending.key !== "string" || !Array.isArray(pending.handles)) {
      pending = this.pending[fingerprint] = {
        key: crypto.randomUUID(), sessionId: input.sessionId, handles: [],
        provider: input.provider, model: input.model, isVoice: !!input.isVoice,
      };
      this.save();
    }
    try {
      if (!pending.sessionId) {
        const created = await this.api<{ conversation: { id: string } }>("POST", "/v2/conversations", {}, `${pending.key}:conversation`);
        pending.sessionId = created.conversation.id;
        this.save();
      }
      for (let index = pending.handles.length; index < input.attachments.length; index++) {
        const data = await this.api<{ attachment: { handle: string } }>("POST", "/v2/attachments", {
          path: input.attachments[index].path, session_id: pending.sessionId,
        }, `${pending.key}:attachment:${index}`);
        pending.handles.push(data.attachment.handle);
        this.save();
      }
      const result = await this.api<{ run_id: string }>("POST", `/v2/conversations/${encodePath(pending.sessionId)}/runs`, {
        text: input.text, attachment_handles: pending.handles,
        provider_mode: pending.provider, model_name: pending.model, source: "tauri_desktop", is_voice: pending.isVoice,
      }, pending.key);
      delete this.pending[fingerprint];
      this.save();
      return { ...result, session_id: pending.sessionId };
    } catch (error) {
      // A validation rejection is definitive; transport/5xx outcomes are not.
      if (error instanceof CoreApiError && error.status >= 400 && error.status < 500) {
        delete this.pending[fingerprint];
        this.save();
      }
      throw error;
    }
  }
}
