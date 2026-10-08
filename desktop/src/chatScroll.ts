import { useLayoutEffect, useRef, useState, type RefObject } from "react";
const key = "smarti.desktop.chat-scroll.v2";
type Position = { top: number; following: boolean; count: number; anchor?: string; offset?: number; block?: string; ordinal?: number; runId?: string; pending?: boolean; readComplete?: boolean; anchorRun?: string };
function userAnchor(user: HTMLElement) {
  const bubble = user.querySelector<HTMLElement>(".sds-user-bubble");
  const strip = user.querySelector<HTMLElement>(".sent-attachments");
  const target = bubble || strip || user, transform = getComputedStyle(target).transform;
  const shift = transform && transform !== "none" ? new DOMMatrixReadOnly(transform).m42 : 0;
  return (bubble || !strip ? target.getBoundingClientRect().top - shift - 16 : strip.getBoundingClientRect().bottom - 8);
}
export function savedChatPosition(sessionId: string): Position | undefined {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || "{}")[sessionId];
    if (value && Number.isFinite(value.top) && value.top >= 0 && Number.isFinite(value.count)) return value;
  } catch { /* A storage failure never interrupts chat. */ }
}

export function useChatScroll(viewport: RefObject<HTMLDivElement | null>, sessionId: string, ready: boolean, count: number, revision: unknown, newRun = "", activeRun = "", foreground = true) {
  const [hasNewContent, setHasNewContent] = useState(false);
  const [height, setHeight] = useState(0);
  const previous = useRef("");
  const position = useRef<Position>({ top: 0, following: false, count: 0 });
  const animation = useRef(0);
  const sent = useRef("");
  const current = useRef({ count, activeRun, foreground }); current.current = { count, activeRun, foreground };
  const cancel = () => { cancelAnimationFrame(animation.current); animation.current = 0; };
  const animate = (target: number) => {
    const node = viewport.current; if (!node) return;
    cancel();
    const from = node.scrollTop, start = performance.now();
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { node.scrollTop = target; return; }
    const frame = (now: number) => {
      const progress = Math.min(1, (now - start) / 180);
      node.scrollTop = from + (target - from) * (1 - Math.pow(1 - progress, 3));
      if (progress < 1) animation.current = requestAnimationFrame(frame); else animation.current = 0;
    };
    animation.current = requestAnimationFrame(frame);
  };
  useLayoutEffect(() => {
    const node = viewport.current;
    if (!node || !ready || !sessionId) return;
    const messages = () => Array.from(node.querySelectorAll<HTMLElement>("[data-message-id]"));
    let layoutWidth = node.clientWidth, layoutHeight = node.clientHeight;
    const contentBottom = () => {
      const last = messages().slice(-1)[0];
      return last ? last.getBoundingClientRect().bottom - node.getBoundingClientRect().top + node.scrollTop : 0;
    };
    const measure = () => {
      const rect = node.getBoundingClientRect();
      layoutWidth = node.clientWidth; layoutHeight = node.clientHeight;
      const footer = node.querySelector<HTMLElement>(".chat-input-panel");
      const bottom = Math.min(rect.bottom, footer?.getBoundingClientRect().top ?? rect.bottom);
      const available = Math.max(80, bottom - rect.top); setHeight(available);
      node.style.setProperty("--chat-available-height", `${available}px`);
      const lastUser = messages().filter(item => item.dataset.messageId?.startsWith("user:")).slice(-1)[0];
      const spacer = node.querySelector<HTMLElement>(".chat-turn-space");
      if (spacer && lastUser) {
        const turnHeight = contentBottom() - (userAnchor(lastUser) + 16 - rect.top + node.scrollTop);
        spacer.style.height = `${Math.max(0, available - turnHeight - 32)}px`;
      }
      setHasNewContent(contentBottom() > node.scrollTop + available + 4);
    };
    const capture = () => {
      const top = node.getBoundingClientRect().top;
      const anchor = messages().find(item => item.getBoundingClientRect().bottom > top + 4);
      const block = Array.from(anchor?.querySelectorAll<HTMLElement>("[data-reading-block]") || []).find(item => item.getBoundingClientRect().bottom > top + 4 && item.getClientRects().length);
      const runId = current.current.activeRun || messages().slice(-1)[0]?.dataset.runId || "";
      const assistant = messages().find(item => item.dataset.messageId === `assistant:${runId}`);
      const started = !!assistant?.querySelector(".message-content-body")?.textContent?.trim();
      const atEnd = contentBottom() <= node.scrollTop + (parseFloat(node.style.getPropertyValue("--chat-available-height")) || node.clientHeight) + 4;
      position.current = { top: node.scrollTop, following: atEnd, count: current.current.count,
        anchor: anchor?.dataset.messageId, offset: (block || anchor) ? (block || anchor)!.getBoundingClientRect().top - top : 0, block: block?.dataset.readingBlock, ordinal: Number(anchor?.dataset.messageOrdinal),
        anchorRun: anchor?.dataset.runId,
        runId, pending: !!current.current.activeRun && !started,
        readComplete: !current.current.activeRun && atEnd && ((!document.hidden && current.current.foreground) || position.current.readComplete && position.current.runId === runId) };
    };
    const save = () => {
      try {
        const positions = JSON.parse(sessionStorage.getItem(key) || "{}");
        positions[sessionId] = position.current;
        sessionStorage.setItem(key, JSON.stringify(positions));
      } catch { /* Preserve the mounted reading position. */ }
    };
    const restore = (saved: Position) => {
      const anchor = messages().find(item => item.dataset.messageId === (saved.pending ? `user:${saved.runId}` : saved.anchor)) || (Number.isFinite(saved.ordinal) ? messages().filter(item => item.dataset.messageOrdinal !== undefined).sort((a, b) => Math.abs(Number(a.dataset.messageOrdinal) - saved.ordinal!) - Math.abs(Number(b.dataset.messageOrdinal) - saved.ordinal!))[0] : undefined);
      if (saved.readComplete && saved.runId === (messages().slice(-1)[0]?.dataset.runId || "") && !current.current.activeRun) node.scrollTop = node.scrollHeight;
      else if (anchor) {
        const block = Array.from(anchor.querySelectorAll<HTMLElement>("[data-reading-block]")).find(item => item.dataset.readingBlock === saved.block);
        node.scrollTop += (saved.pending ? userAnchor(anchor) : (block || anchor).getBoundingClientRect().top - (saved.offset || 0)) - node.getBoundingClientRect().top;
      } else node.scrollTop = saved.top;
    };
    measure();
    if (previous.current !== sessionId) {
      cancel();
      const saved = savedChatPosition(sessionId);
      if (saved) restore(saved);
      else if (current.current.activeRun) restore({ top: 0, following: false, count, pending: true, runId: current.current.activeRun });
      else node.scrollTop = node.scrollHeight;
      previous.current = sessionId;
    }
    capture(); measure();
    const scroll = () => {
      const changedLayout = layoutWidth !== node.clientWidth || layoutHeight !== node.clientHeight;
      const saved = position.current;
      measure();
      // The browser can clamp scrollTop on resize before ResizeObserver runs.
      // That synthetic scroll must not overwrite the reader's logical anchor.
      if (changedLayout && !animation.current) restore({ ...saved, readComplete: false, pending: false });
      capture(); save();
    };
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      const saved = position.current;
      measure();
      if (!animation.current) { restore({ ...saved, readComplete: false, pending: false }); capture(); }
    });
    resize?.observe(node);
    const list = node.querySelector(".message-list");
    if (list) resize?.observe(list);
    const content = node.querySelector(".chat-scroll-content");
    if (content) resize?.observe(content);
    const listContent = node.querySelector(".chat-input-panel"); if (listContent) resize?.observe(listContent);
    node.addEventListener("scroll", scroll, { passive: true });
    node.addEventListener("wheel", cancel, { passive: true }); node.addEventListener("touchstart", cancel, { passive: true }); node.addEventListener("pointerdown", cancel);
    window.addEventListener("pagehide", save);
    return () => { save(); cancel(); resize?.disconnect(); node.removeEventListener("scroll", scroll); node.removeEventListener("wheel", cancel); node.removeEventListener("touchstart", cancel); node.removeEventListener("pointerdown", cancel); window.removeEventListener("pagehide", save); };
  }, [viewport, sessionId, ready]);
  useLayoutEffect(() => {
    const node = viewport.current;
    if (!node || !newRun || sent.current === newRun) return;
    const user = Array.from(node.querySelectorAll<HTMLElement>("[data-message-id]")).find(item => item.dataset.messageId === `user:${newRun}`);
    if (user) {
      sent.current = newRun;
      animate(node.scrollTop + userAnchor(user) - node.getBoundingClientRect().top);
    }
  }, [newRun, revision, height]);
  const follow = () => {
    const node = viewport.current;
    const last = node?.querySelector<HTMLElement>(".message-list")?.lastElementChild;
    if (node && last) animate(node.scrollTop + last.getBoundingClientRect().bottom - node.getBoundingClientRect().top - height);
  };
  return { hasNewContent, follow, height };
}

// Disclosure controls stay at their exact screen coordinate even at the old
// scrollbar limit. The reserve is ignored when deciding if there is new text.
export function preserveDisclosure(control: HTMLElement, action?: () => void) {
  const stage = control.closest<HTMLElement>(".chat-stage");
  if (!stage) { action?.(); return; }
  const top = control.getBoundingClientRect().top;
  const reserve = stage.querySelector<HTMLElement>(".chat-turn-space");
  if (reserve) reserve.style.minHeight = `${Math.max(0, stage.scrollTop + stage.clientHeight - (stage.scrollHeight - reserve.offsetHeight))}px`;
  action?.();
  requestAnimationFrame(() => {
    stage.scrollTop += control.getBoundingClientRect().top - top;
    stage.dispatchEvent(new Event("scroll"));
  });
}

// Keep ordinary approvals beside the composer. If a queue or a short window
// cannot fit that footer, let the main chat scroll carry the approvals while
// the composer alone stays sticky. No approval card becomes a scroll container.
export function useChatFooterFlow(viewport: RefObject<HTMLDivElement | null>, footer: RefObject<HTMLDivElement | null>, revision: string) {
  const [flowing, setFlowing] = useState(false);
  useLayoutEffect(() => {
    const stage = viewport.current, panel = footer.current;
    if (!stage || !panel) return;
    const parts = Array.from(panel.children).filter((node): node is HTMLElement => node instanceof HTMLElement && (node.classList.contains("conversation-approvals") || node.classList.contains("chat-composer-panel")));
    const measure = () => {
      const height = parts.reduce((sum, node) => {
        const style = getComputedStyle(node);
        return sum + node.getBoundingClientRect().height + (parseFloat(style.marginTop) || 0) + (parseFloat(style.marginBottom) || 0);
      }, 8);
      setFlowing(height > stage.clientHeight - 40);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(stage); parts.forEach(node => observer?.observe(node));
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, [viewport, footer, revision]);
  return flowing;
}
