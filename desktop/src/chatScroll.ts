import { useLayoutEffect, useRef, useState, type RefObject } from "react";
const key = "smarti.desktop.chat-scroll.v1";
type Position = { top: number; following: boolean; count: number };
export function savedChatPosition(sessionId: string): Position | undefined {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) || "{}")[sessionId];
    if (value && Number.isFinite(value.top) && value.top >= 0 && Number.isFinite(value.count)) return value;
  } catch { /* A storage failure never interrupts chat. */ }
}

export function useChatScroll(viewport: RefObject<HTMLDivElement | null>, sessionId: string, ready: boolean, count: number, revision: unknown) {
  const [hasNewContent, setHasNewContent] = useState(false);
  const following = useRef(false);
  const previous = useRef("");
  const lastHeight = useRef(0);
  const lastTop = useRef(0);
  useLayoutEffect(() => {
    const node = viewport.current;
    if (!node || !ready || !sessionId) return;
    const changed = previous.current !== sessionId;
    if (changed) {
      const saved = savedChatPosition(sessionId);
      following.current = saved?.following ?? false;
      if (saved) node.scrollTop = saved.following ? node.scrollHeight : saved.top;
      previous.current = sessionId;
      setHasNewContent(false);
    } else if (node.scrollHeight > lastHeight.current + 2) {
      if (following.current) node.scrollTop = node.scrollHeight;
      else setHasNewContent(true);
    }
    lastHeight.current = node.scrollHeight;
    lastTop.current = node.scrollTop;
    const save = () => {
      try {
        const positions = JSON.parse(sessionStorage.getItem(key) || "{}");
        positions[sessionId] = { top: lastTop.current, following: following.current, count };
        sessionStorage.setItem(key, JSON.stringify(positions));
      } catch { /* Preserve the mounted reading position. */ }
    };
    const scroll = () => {
      following.current = node.scrollHeight - node.clientHeight - node.scrollTop < 48;
      lastTop.current = node.scrollTop;
      if (following.current) setHasNewContent(false);
      save();
    };
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      if (following.current) node.scrollTop = node.scrollHeight;
      else node.scrollTop = lastTop.current;
      lastHeight.current = node.scrollHeight;
    });
    resize?.observe(node);
    const list = node.querySelector(".message-list");
    if (list) resize?.observe(list);
    const content = node.querySelector(".chat-scroll-content");
    if (content) resize?.observe(content);
    node.addEventListener("scroll", scroll, { passive: true });
    window.addEventListener("pagehide", save);
    return () => { save(); resize?.disconnect(); node.removeEventListener("scroll", scroll); window.removeEventListener("pagehide", save); };
  }, [viewport, sessionId, ready, count, revision]);
  const follow = () => {
    const node = viewport.current;
    following.current = true;
    if (node) node.scrollTop = node.scrollHeight;
    setHasNewContent(false);
  };
  return { hasNewContent, follow };
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
