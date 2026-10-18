// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import { useChatDrafts, readDrafts, readActiveConversation, rememberActiveConversation, restoreActiveConversation, beginChatLaunch } from "./chatDrafts";
import { mergeMessages } from "./chatState";
beforeEach(() => { sessionStorage.clear(); localStorage.clear(); });
afterEach(cleanup);
describe("UX-3 conversation recovery", () => {
  test("native relaunch resets selection but preserves existing and shared new drafts", () => {
    const view = renderHook(() => useChatDrafts("", () => {}));
    act(() => { view.result.current.setText("פתיחה\nנשמרת"); view.result.current.setAttachments([{ name: "a.png", path: "C:/durable/a.png", kind: "image" }]); });
    expect(beginChatLaunch("first")).toBe(true);
    rememberActiveConversation("existing");
    expect(beginChatLaunch("first")).toBe(false);
    expect(readActiveConversation()).toBe("existing");
    view.unmount(); sessionStorage.clear();
    expect(beginChatLaunch("second")).toBe(true);
    const recovered = renderHook(() => useChatDrafts("", () => {}));
    expect(recovered.result.current.draft.text).toBe("פתיחה\nנשמרת");
    expect(recovered.result.current.draft.attachments[0].path).toBe("C:/durable/a.png");
    expect(readActiveConversation()).toBe("");
  });
  test("acceptance clears only the submitted revision and files, including after navigation", () => {
    const view = renderHook(({ id }) => useChatDrafts(id, () => {}), { initialProps: { id: "" } });
    const first = { name: "a", path: "C:/a", draftId: "a" }, second = { name: "b", path: "C:/b", draftId: "b" };
    act(() => { view.result.current.setText("submitted"); view.result.current.setAttachments([first]); });
    const submitted = view.result.current.snapshot("");
    act(() => { view.result.current.setText("newer"); view.result.current.setAttachments([first, second]); });
    view.rerender({ id: "other" });
    act(() => { view.result.current.setText("other draft"); view.result.current.accept("", "accepted", submitted, "submitted", false); });
    expect(readDrafts().new.text).toBe("newer");
    expect(readDrafts().new.attachments.map(item => item.path)).toEqual(["C:/b"]);
    expect(view.result.current.draft.text).toBe("other draft");
  });
  test("accepted first send starts the next shared draft empty and preserves newer typing in the real chat", () => {
    const view = renderHook(() => useChatDrafts("", () => {}));
    act(() => view.result.current.setText("first"));
    const submitted = view.result.current.snapshot("");
    act(() => view.result.current.setText("next message"));
    act(() => view.result.current.accept("", "real", submitted, "first", true));
    expect(readDrafts().real.text).toBe("next message");
    expect(readDrafts().new.text).toBe("");
  });
  test("reload retains the selected draft owner when a newer conversation exists, with safe deletion fallback", () => {
    const view = renderHook(() => useChatDrafts("older", () => {}));
    act(() => view.result.current.setText("older owned draft"));
    expect(rememberActiveConversation("older")).toBe(true);
    view.unmount();
    const restored = restoreActiveConversation([{ id: "newer" }, { id: "older" }], readActiveConversation());
    expect(restored).toBe("older");
    const recovered = renderHook(() => useChatDrafts(restored, () => {}));
    expect(recovered.result.current.draft.text).toBe("older owned draft");
    expect(restoreActiveConversation([{ id: "newer" }], restored)).toBe("");
    expect(restoreActiveConversation([], restored)).toBe("");
    expect(rememberActiveConversation("")).toBe(true);
    expect(readActiveConversation()).toBe("");
  });
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
