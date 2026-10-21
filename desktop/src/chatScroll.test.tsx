// @vitest-environment jsdom
import { useLayoutEffect, useRef } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { savedChatPosition, useChatScroll } from "./chatScroll";

afterEach(() => { cleanup(); sessionStorage.clear(); vi.restoreAllMocks(); });

function Chat({ session, ready = true }: { session: string; ready?: boolean }) {
  const viewport = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = viewport.current!;
    Object.defineProperties(node, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 900 },
      getBoundingClientRect: { configurable: true, value: () => ({ top: 0, bottom: 200 }) },
    });
    const row = node.querySelector<HTMLElement>("[data-message-id]");
    if (row) row.getBoundingClientRect = () => ({ top: -node.scrollTop, bottom: 900 - node.scrollTop } as DOMRect);
  });
  const scroll = useChatScroll(viewport, session, ready, session ? 1 : 0, session);
  return <><div ref={viewport} data-testid="viewport"><div className="message-list">{session && <div data-message-id="assistant:reply" data-run-id="reply">תשובה ארוכה</div>}</div></div>{scroll.hasNewContent && <button>גלילה לסוף</button>}</>;
}

test("new chat clears the down control and returning to the same chat restores its reading position", () => {
  const view = render(<Chat session="existing" />);
  const viewport = screen.getByTestId("viewport");
  viewport.scrollTop = 120;
  fireEvent.scroll(viewport);
  expect(screen.getByRole("button", { name: "גלילה לסוף" })).not.toBeNull();
  view.rerender(<Chat session="" ready={false} />);
  expect(screen.queryByRole("button", { name: "גלילה לסוף" })).toBeNull();
  expect(savedChatPosition("existing")?.top).toBe(120);
  viewport.scrollTop = 0;
  view.rerender(<Chat session="existing" />);
  expect(viewport.scrollTop).toBe(120);
  expect(screen.getByRole("button", { name: "גלילה לסוף" })).not.toBeNull();
  viewport.scrollTop = 700;
  fireEvent.scroll(viewport);
  expect(screen.queryByRole("button", { name: "גלילה לסוף" })).toBeNull();
});

test("a different conversation cannot show the previous chat's control while its history loads", () => {
  const view = render(<Chat session="existing" />);
  const viewport = screen.getByTestId("viewport");
  viewport.scrollTop = 120;
  fireEvent.scroll(viewport);
  expect(screen.getByRole("button", { name: "גלילה לסוף" })).not.toBeNull();
  view.rerender(<Chat session="other" ready={false} />);
  expect(screen.queryByRole("button", { name: "גלילה לסוף" })).toBeNull();
  view.rerender(<Chat session="other" />);
  expect(screen.queryByRole("button", { name: "גלילה לסוף" })).toBeNull();
});
