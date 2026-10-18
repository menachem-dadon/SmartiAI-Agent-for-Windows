// @vitest-environment jsdom
import { useRef } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useComposerFocus } from "./composerFocus";

function Harness({ owner = "a", ticket = 0, blocked = false, allowed = true }) {
  const area = useRef<HTMLTextAreaElement>(null);
  const request = useComposerFocus(area, owner, ticket, blocked, allowed);
  return <><textarea ref={area} aria-label="draft" disabled={blocked} /><button onClick={request}>write</button><input aria-label="other" /></>;
}
beforeEach(() => {
  vi.spyOn(document, "hasFocus").mockReturnValue(true);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  vi.useFakeTimers();
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const settle = () => act(() => { vi.runOnlyPendingTimers(); });

test("startup and repeated explicit navigation focus without selecting or scrolling the draft", () => {
  const focus = vi.spyOn(HTMLTextAreaElement.prototype, "focus");
  const view = render(<Harness />);
  const area = screen.getByLabelText("draft") as HTMLTextAreaElement;
  expect(document.activeElement).toBe(area);
  expect(focus).toHaveBeenLastCalledWith({ preventScroll: true });
  area.value = "שמור"; area.setSelectionRange(2, 2);
  screen.getByLabelText("other").focus();
  view.rerender(<Harness ticket={1} />);
  expect(document.activeElement).toBe(area);
  expect(area.selectionStart).toBe(2);
  screen.getByLabelText("other").focus();
  view.rerender(<Harness owner="b" ticket={2} />);
  expect(document.activeElement).toBe(area);
});
test("a pending request waits for readiness and a closed dialog", () => {
  const dialog = document.createElement("dialog"); dialog.setAttribute("open", ""); document.body.append(dialog);
  const view = render(<Harness blocked />);
  view.rerender(<Harness ticket={1} />);
  expect(document.activeElement).not.toBe(screen.getByLabelText("draft"));
  dialog.remove(); fireEvent(window, new Event("smarti:modal-change")); settle();
  expect(document.activeElement).toBe(screen.getByLabelText("draft"));
});
test("user interaction cancels late autofocus and background updates do not steal focus", () => {
  const view = render(<Harness blocked />);
  const other = screen.getByLabelText("other");
  fireEvent.pointerDown(other); other.focus();
  view.rerender(<Harness />);
  expect(document.activeElement).toBe(other);
  view.rerender(<Harness owner="b" />);
  expect(document.activeElement).toBe(other);
  view.rerender(<Harness owner="b" ticket={1} />);
  expect(document.activeElement).toBe(screen.getByLabelText("draft"));
});
test("temporary input blocking restores focus when readiness returns", () => {
  const view = render(<Harness />);
  const area = screen.getByLabelText("draft");
  expect(document.activeElement).toBe(area);
  view.rerender(<Harness blocked />);
  view.rerender(<Harness />);
  expect(document.activeElement).toBe(area);
});
test("a closing inert model menu does not delay returning to typing", () => {
  const layer = document.createElement("div");
  layer.setAttribute("inert", ""); layer.setAttribute("aria-hidden", "true");
  layer.innerHTML = '<div role="menu"></div>';
  document.body.append(layer);
  render(<Harness />);
  expect(document.activeElement).toBe(screen.getByLabelText("draft"));
  layer.remove();
});
test("hidden or covered chat waits; returning to an existing control preserves its focus", () => {
  const view = render(<Harness allowed={false} />);
  view.rerender(<Harness ticket={1} allowed={false} />);
  expect(document.activeElement).not.toBe(screen.getByLabelText("draft"));
  view.rerender(<Harness ticket={1} />);
  expect(document.activeElement).toBe(screen.getByLabelText("draft"));
  const other = screen.getByLabelText("other"); fireEvent.pointerDown(other); other.focus();
  fireEvent(window, new Event("focus")); settle();
  expect(document.activeElement).toBe(other);
});
