// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useReplyNavigation, type ReplyNavigation } from "./replyNavigation";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

test("a message search aligns its own user message rather than the latest assistant reply and only once", () => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { top: this.dataset.top ? Number(this.dataset.top) : 100 } as DOMRect;
  });
  const request: ReplyNavigation = { sessionId: "chat", revision: 1, messageOrdinal: 0 };
  function Fixture({ revision }: { revision: number }) {
    const ref = useReplyNavigation(request, "chat", true);
    return <div ref={ref} data-testid="viewport" data-revision={revision}>
      <article data-message-ordinal="0"><div className="message-content" data-top="280">matching user message</div></article>
      <article className="chat-message-row--assistant" data-message-ordinal="40"><div className="message-content" data-top="600">latest reply</div></article>
    </div>;
  }
  const view = render(<Fixture revision={1} />);
  const viewport = screen.getByTestId("viewport");
  expect(viewport.scrollTop).toBe(164);
  viewport.dispatchEvent(new Event("wheel")); // cancels the one-frame follow-up
  viewport.scrollTop = 25; view.rerender(<Fixture revision={2} />);
  expect(viewport.scrollTop).toBe(25);
});
