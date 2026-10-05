// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { useChatDrafts, readDrafts } from "./chatDrafts";
import { mergeMessages } from "./chatState";
beforeEach(() => sessionStorage.clear());
afterEach(cleanup);
describe("UX-3 conversation recovery", () => {
  test("separates drafts and attachments; a late attachment belongs to its captured conversation", () => {
    const view = renderHook(({ id }) => useChatDrafts(id, () => {}), { initialProps: { id: "a" } });
    const oldAttachments = view.result.current.setAttachments;
    act(() => view.result.current.setText("טיוטה ראשונה"));
    view.rerender({ id: "b" });
    act(() => { view.result.current.setText("draft B"); oldAttachments(items => [...items, { name: "a.txt", path: "C:/qa/a.txt" }]); });
    expect(view.result.current.draft.text).toBe("draft B");
    expect(view.result.current.draft.attachments).toEqual([]);
    view.rerender({ id: "a" });
    expect(view.result.current.draft.text).toBe("טיוטה ראשונה");
    expect(view.result.current.draft.attachments[0].name).toBe("a.txt");
  });
  test("recovers text, paths and selection on reload without retaining temporary blob URLs", () => {
    const view = renderHook(() => useChatDrafts("a", () => {}));
    act(() => { view.result.current.setText("recovery"); view.result.current.setAttachments([{ name: "image.png", path: "C:/qa/image.png", previewUrl: "blob:temporary" }]); view.result.current.setSelection({ provider: "local", model: "valid", effort: "auto" }); });
    view.unmount();
    const restored = renderHook(() => useChatDrafts("a", () => {}));
    expect(restored.result.current.draft.text).toBe("recovery");
    expect(restored.result.current.draft.attachments[0].previewUrl).toBeUndefined();
    expect(restored.result.current.draft.selection?.model).toBe("valid");
  });
  test("transfers only the accepted unowned draft and removes only a deleted conversation", () => {
    const view = renderHook(() => useChatDrafts("", () => {}));
    act(() => view.result.current.setText("scratch"));
    act(() => view.result.current.transfer("", "accepted"));
    expect(readDrafts().accepted.text).toBe("scratch");
    expect(readDrafts().new).toBeUndefined();
    act(() => view.result.current.remove("accepted"));
    expect(readDrafts().accepted).toBeUndefined();
  });
  test("replay updates the same assistant identity instead of duplicating streamed content", () => {
    const user = { role: "user" as const, content: "start", created_at: "one" };
    const older = { role: "assistant" as const, content: "partial", metadata: { run_id: "r" }, created_at: "two" };
    const latest = { ...older, content: "completed" };
    expect(mergeMessages([user, older], [user, latest])).toEqual([user, latest]);
  });
});

// Imported history may contain multiple messages with the same timestamp.
test("keeps distinct messages sharing a timestamp", () => {
  expect(mergeMessages([{role:"user",content:"first",created_at:"same"}], [{role:"user",content:"second",created_at:"same"}])).toHaveLength(2);
});
