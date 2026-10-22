import { Channel, invoke } from "@tauri-apps/api/core";
import { coreApi, CoreApiError } from "../coreApi";

type Receipt = { accepted: boolean; admission_id?: string; dropped?: boolean };
type Envelope = { type: string; data?: unknown; sequence?: number; error?: string };
const delay = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms));
export const transientLiveError = (error: unknown) => !(error instanceof CoreApiError) || ![400,401,403,404,409].includes(error.status);

/** Rust owns the authenticated socket. HTTP is compatibility for an older host
 * or isolated web fixtures; the webview never receives a port or bearer. */
export class LiveTransport {
  private id = "";
  private native = false;
  private closed = false;
  private opening: Promise<void> | null = null;
  private pages: unknown[] = [];
  private waiting: { resolve: (value: unknown) => void; reject: (error: unknown) => void } | null = null;
  private pending = new Map<number, { resolve: (value: Receipt) => void; reject: (error: unknown) => void; timer: number }>();
  private cursor: number;
  private epoch = 0;
  constructor(private session: string, after = 0, private onRecovering: () => void = () => {}) { this.cursor = after; }
  get persistent() { return this.native; }
  async open() {
    try { await this.attach(); this.native = true; }
    catch { this.native = false; }
  }
  private attach(): Promise<void> {
    if (this.opening) return this.opening;
    const epoch = ++this.epoch;
    this.opening = (async () => {
      const events = new Channel<Envelope>();
      events.onmessage = event => {
        if (this.closed || epoch !== this.epoch) return;
        if (event.type === "page") {
          if (this.waiting) { const target = this.waiting; this.waiting = null; target.resolve(event.data); }
          else { this.pages.push(event.data); if (this.pages.length > 64) { this.pages = []; this.detached(new Error("Live UI stream fell behind")); } }
        } else if (event.type === "receipt" && event.sequence !== undefined) {
          const receipt = this.pending.get(event.sequence);
          if (receipt) { this.pending.delete(event.sequence); window.clearTimeout(receipt.timer);
            if (event.error) receipt.reject(new CoreApiError(event.error, 409)); else receipt.resolve(event.data as Receipt); }
        } else if (event.type === "transport_closed") this.detached(new Error(event.error || "Live transport detached"));
      };
      const id = await invoke<string>("core_live_open", { sessionId: this.session, after: this.cursor, events });
      if (!id) throw new Error("Live stream is unavailable in this host");
      if (this.closed || epoch !== this.epoch) { void invoke("core_live_close", { id }).catch(() => undefined); throw new Error("Live attachment was superseded"); }
      this.id = id;
    })().finally(() => { this.opening = null; });
    return this.opening;
  }
  private detached(error: Error) {
    this.epoch++;
    if (this.id) void invoke("core_live_close", { id: this.id }).catch(() => undefined);
    this.id = ""; this.pages = []; if (!this.closed) this.onRecovering();
    for (const item of this.pending.values()) { window.clearTimeout(item.timer); item.reject(error); }
    this.pending.clear();
    this.waiting?.reject(error); this.waiting = null;
  }
  async next<T extends { cursor: number }>(after: number): Promise<T> {
    this.cursor = after;
    let error: unknown;
    for (let attempt = 0; attempt < 5 && !this.closed; attempt++) {
      try {
        if (!this.native) return await coreApi<T>("GET", `/v2/live/sessions/${this.session}/events?after=${after}`);
        if (!this.id) await this.attach();
        if (this.pages.length) return this.pages.shift() as T;
        return await new Promise<T>((resolve, reject) => { this.waiting = { resolve: value => resolve(value as T), reject }; });
      } catch (failure) {
        error = failure;
        if (!transientLiveError(failure)) throw failure;
        this.onRecovering();
        await delay(Math.min(2000, 200 * 2 ** attempt));
      }
    }
    throw error || new Error("Live transport closed");
  }
  async send(input: Record<string, unknown> & { sequence: number }): Promise<Receipt> {
    for (let attempt = 0; ; attempt++) {
      try { return await this.sendOnce(input); }
      catch (error) {
        if (this.closed || !transientLiveError(error)) throw error;
        if (typeof input.audio === "string") return { accepted: true, dropped: true };
        if (attempt >= 2) throw error;
        this.detached(new Error(String(error)));
        await delay(200 * 2 ** attempt);
      }
    }
  }
  private async sendOnce(input: Record<string, unknown> & { sequence: number }): Promise<Receipt> {
    if (this.closed) throw new Error("Live transport closed");
    const audio = typeof input.audio === "string";
    if (!this.native) {
      // Audio has an ambiguous outcome on a failed request: drop it. Controls
      // retain their sequence and can be safely retried against Core receipts.
      try { return await coreApi<Receipt>("POST", `/v2/live/sessions/${this.session}/input`, input); }
      catch (error) { if (audio && transientLiveError(error)) { this.onRecovering(); return { accepted: true, dropped: true }; } throw error; }
    }
    if (!this.id) { if (audio) return { accepted: true, dropped: true }; await this.attach(); }
    if (audio && this.pending.size >= 16) return { accepted: true, dropped: true };
    return await new Promise<Receipt>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(input.sequence);
        if (audio) { resolve({ accepted: true, dropped: true }); this.detached(new Error("Live audio acknowledgement timed out")); }
        else { reject(new Error("לא התקבל אישור קלט לייב; הטיוטה נשמרה")); this.detached(new Error("Live control acknowledgement timed out")); }
      }, audio ? 4000 : 15000);
      this.pending.set(input.sequence, { resolve, reject, timer });
      void invoke<boolean>("core_live_send", { id: this.id, input }).then(accepted => {
        if (!accepted) { window.clearTimeout(timer); this.pending.delete(input.sequence);
          if (audio) resolve({ accepted: true, dropped: true }); else reject(new Error("Live control queue is full")); }
      }).catch(error => {
        window.clearTimeout(timer); this.pending.delete(input.sequence);
        if (audio) { resolve({ accepted: true, dropped: true }); this.detached(new Error(String(error))); } else reject(error);
      });
    });
  }
  close() {
    if (this.closed) return;
    this.closed = true; this.epoch++;
    this.detached(new Error("Live transport closed")); this.pages = [];
  }
}
