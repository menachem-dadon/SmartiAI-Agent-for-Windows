import { useCallback, useEffect, useLayoutEffect, useRef, type RefObject } from "react";
let interactionRevision = 0;
export const composerInteractionRevision = () => interactionRevision;

/** One-shot intent, never a focus effect tied to streaming or polling. */
export function useComposerFocus(area: RefObject<HTMLTextAreaElement | null>, owner: string | undefined,
  ticket: number, blocked: boolean, allowed: boolean) {
  const pending = useRef(true), lastOwner = useRef(owner), previousTicket = useRef(ticket), previousBlocked = useRef(blocked);
  const state = useRef({ blocked, allowed, owner });
  // Capture before React disables/blurs the native textarea during commit.
  const restoreAfterBlocking = blocked && !previousBlocked.current && document.activeElement === area.current;
  state.current = { blocked, allowed, owner };
  const attempt = useCallback(() => {
    const node = area.current;
    if (!pending.current || !node || state.current.blocked || !state.current.allowed || document.hidden || !document.hasFocus()) return;
    if (node.closest('[inert], [aria-hidden="true"]') || Array.from(document.querySelectorAll('dialog[open], [role="menu"], [role="listbox"], .model-quick-pill [aria-expanded="true"]'))
      .some(layer => !layer.closest('[inert], [aria-hidden="true"]'))) return;
    pending.current = false;
    node.focus({ preventScroll: true });
  }, [area]);
  const request = useCallback(() => { pending.current = true; requestAnimationFrame(attempt); }, [attempt]);
  useLayoutEffect(() => {
    if (lastOwner.current !== owner) { lastOwner.current = owner; pending.current = false; }
    if (previousTicket.current !== ticket) { previousTicket.current = ticket; pending.current = true; }
    if (restoreAfterBlocking) pending.current = true;
    previousBlocked.current = blocked;
    attempt();
  }, [blocked, allowed, owner, ticket, attempt, area]);
  useEffect(() => {
    let frame = 0;
    const retry = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(attempt); };
    const interact = (event: Event) => {
      ++interactionRevision;
      if (event.target instanceof Node && event.target !== area.current) pending.current = false;
    };
    const resume = () => {
      const active = document.activeElement;
      if (active === document.body || active === area.current) pending.current = true;
      retry();
    };
    document.addEventListener("pointerdown", interact, true);
    document.addEventListener("keydown", interact, true);
    window.addEventListener("smarti:modal-change", retry);
    window.addEventListener("focus", resume);
    document.addEventListener("visibilitychange", retry);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointerdown", interact, true);
      document.removeEventListener("keydown", interact, true);
      window.removeEventListener("smarti:modal-change", retry);
      window.removeEventListener("focus", resume);
      document.removeEventListener("visibilitychange", retry);
    };
  }, [area, attempt]);
  return request;
}
