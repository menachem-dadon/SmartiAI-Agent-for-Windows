import { useEffect, type RefObject } from "react";
import type { AttentionItem } from "./chatTypes";

/** A loaded page is not a read receipt: the final result must reach the viewport. */
export function visibleAttentionIds(viewport: HTMLElement, items: AttentionItem[], snapshotIds: string[]) {
  const bounds = viewport.getBoundingClientRect();
  if (bounds.height <= 0 || bounds.width <= 0) return [];
  const availableHeight = parseFloat(viewport.style.getPropertyValue("--chat-available-height")) || viewport.clientHeight || bounds.height;
  const top = Math.max(bounds.top, 0);
  const bottom = Math.min(bounds.bottom, bounds.top + availableHeight, window.innerHeight);
  const rows = Array.from(viewport.querySelectorAll<HTMLElement>('.chat-message-row--assistant[data-result-ready="true"]'));
  return items.filter(item => {
    if (!snapshotIds.includes(item.id)) return false;
    if (["approval", "api_key"].includes(item.kind)) {
      const panel = viewport.parentElement?.querySelector<HTMLElement>(item.kind === "approval" ? ".conversation-approvals" : ".chat-api-key");
      return Boolean(panel && panel.getBoundingClientRect().height > 0);
    }
    const matching = item.run_id ? rows.filter(row => row.dataset.runId === item.run_id) : rows;
    const row = matching[matching.length - 1];
    const target = row || (item.kind === "interrupted" ? Array.from(viewport.querySelectorAll<HTMLElement>("[data-run-id]")).find(row => row.dataset.runId === item.run_id) : undefined);
    if (!target) return false;
    const rect = target.getBoundingClientRect();
    return rect.height > 0 && rect.bottom > top && rect.bottom <= bottom + 2;
  }).map(item => item.id);
}

export function useVisibleConversationAttention(viewport: RefObject<HTMLDivElement | null>, sessionId: string, ready: boolean,
  items: AttentionItem[], snapshotIds: string[], acknowledge: (session: string, ids: string[]) => Promise<void>) {
  useEffect(() => {
    const node = viewport.current;
    if (!ready || !node || !items.length) return;
    let frame = 0;
    const check = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (document.hidden) return;
        const ids = visibleAttentionIds(node, items.filter(item => item.session_id === sessionId), snapshotIds);
        if (ids.length) void acknowledge(sessionId, ids);
      });
    };
    const observer = new ResizeObserver(check);
    observer.observe(node);
    if (node.firstElementChild) observer.observe(node.firstElementChild);
    node.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    check();
    return () => { cancelAnimationFrame(frame); observer.disconnect(); node.removeEventListener("scroll", check); window.removeEventListener("resize", check); };
  }, [viewport, sessionId, ready, items, snapshotIds, acknowledge]);
}
