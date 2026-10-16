import { useLayoutEffect, useRef } from "react";

export interface ReplyNavigation { sessionId: string; revision: number; runId?: string; alignReply?: boolean; messageOrdinal?: number; }

/** Align once after the requested conversation has rendered, never on polling. */
export function useReplyNavigation(
  request: ReplyNavigation | null,
  loadedSessionId: string,
  ready: boolean,
) {
  const viewport = useRef<HTMLDivElement>(null);
  const applied = useRef<ReplyNavigation | null>(null);
  useLayoutEffect(() => {
    const container = viewport.current;
    if (!container || !ready || !request || request === applied.current ||
        request.sessionId !== loadedSessionId || (!request.runId && !request.alignReply && request.messageOrdinal === undefined)) return;
    applied.current = request;
    const align = () => {
      const replies = container.querySelectorAll<HTMLElement>(".chat-message-row--assistant");
      const reply = request.messageOrdinal !== undefined
        ? Array.from(container.querySelectorAll<HTMLElement>("[data-message-ordinal]")).find(row => Number(row.dataset.messageOrdinal) === request.messageOrdinal)
        : (request.runId && Array.from(replies).find((row) => row.dataset.runId === request.runId)) || replies[replies.length - 1];
      if (request.messageOrdinal !== undefined && !reply) return;
      const target = reply?.querySelector<HTMLElement>(".message-content") || reply;
      container.scrollTop = target
        ? Math.max(0, container.scrollTop + target.getBoundingClientRect().top -
            container.getBoundingClientRect().top - 16)
        : 0;
    };
    align();
    // Completed process details collapse in an effect; align after that layout.
    const frame = requestAnimationFrame(align);
    const cancel = () => cancelAnimationFrame(frame);
    container.addEventListener("wheel", cancel, { once: true, passive: true });
    container.addEventListener("pointerdown", cancel, { once: true });
    return () => {
      cancel();
      container.removeEventListener("wheel", cancel);
      container.removeEventListener("pointerdown", cancel);
    };
  }, [request, loadedSessionId, ready]);
  return viewport;
}
