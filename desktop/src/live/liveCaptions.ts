import type { ChatMessage } from "../chatTypes";
type Caption = { canonical: ChatMessage; visible: ChatMessage; frozen?: boolean };

/** Presentation only: canonical transcripts stay complete in Core/history. */
export class LiveCaptions {
  private rows = new Map<string, Caption>();
  private played = 0;
  private muted = false;
  private key(message: ChatMessage) { return String(message.metadata?.live_message_id || ""); }
  update(message: ChatMessage) {
    if (message.role !== "assistant" || !this.key(message) || message.metadata?.live_process) return;
    const previous = this.rows.get(this.key(message));
    this.rows.set(this.key(message), { canonical: message, visible: previous?.visible || message, frozen: previous?.frozen });
    this.tick(this.played, this.muted);
  }
  tick(playedMs: number, muted = this.muted) {
    this.played = playedMs; this.muted = muted;
    let changed = false;
    for (const row of this.rows.values()) {
      if (row.frozen) continue;
      const message = row.canonical, meta = message.metadata || {};
      const start = Number(meta.live_audio_start_ms || 0), end = Number(meta.live_audio_end_ms || 0);
      const spoken = Number(meta.live_spoken_length ?? message.content.length);
      let length = message.content.length;
      if (!muted && this.played < end) {
        let previousText = 0, previousTime = start;
        length = 0;
        const cues = Array.isArray(meta.live_audio_cues) ? meta.live_audio_cues as { text_end: number; audio_end_ms: number }[] : [];
        for (const cue of [...cues, { text_end: spoken, audio_end_ms: end }]) {
          if (cue.audio_end_ms <= previousTime || cue.text_end <= previousText) continue;
          if (this.played >= cue.audio_end_ms) length = cue.text_end;
          else {
            length = previousText + Math.floor((cue.text_end - previousText) * Math.max(0, this.played - previousTime) / (cue.audio_end_ms - previousTime));
            break;
          }
          previousText = cue.text_end; previousTime = cue.audio_end_ms;
        }
        // Reveal complete words; existing streamReveal supplies their fade.
        const prefix = message.content.slice(0, length);
        const boundary = prefix.search(/\S+$/u);
        if (boundary >= 0 && length < spoken && /\S/u.test(message.content[length] || "")) length = boundary;
      } else if (!muted && meta.live_partial && end <= start) length = 0;
      const partial = Boolean(meta.live_partial || length < message.content.length);
      const next = { ...message, content: message.content.slice(0, length), metadata: { ...meta, live_partial: partial, live_presenting: partial } };
      if (row.visible.content !== next.content || row.visible.metadata?.live_partial !== partial) changed = true;
      row.visible = next;
    }
    return changed;
  }
  present(message: ChatMessage) { return this.rows.get(this.key(message))?.visible || message; }
  interrupt(playedMs: number) {
    this.tick(playedMs);
    for (const row of this.rows.values()) if (row.visible.metadata?.live_partial) {
      row.frozen = true;
      row.visible = { ...row.visible, metadata: { ...row.visible.metadata, live_partial: false, live_presenting: false } };
    }
  }
}
