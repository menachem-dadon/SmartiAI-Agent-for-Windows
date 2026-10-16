// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import { coreApi } from "./coreApi";
import { DesignSystemProvider } from "./design-system";
import { SearchDialog } from "./SearchDialog";
import { highlightParts, rememberConversationVisit, suggestedConversations } from "./searchState";
import { ChatSidebar } from "./ChatSidebar";
import type { Conversation } from "./chatTypes";
import { rankSearchFiles } from "./searchState";

vi.mock("./coreApi", () => ({ coreApi: vi.fn() }));
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  HTMLElement.prototype.scrollIntoView = vi.fn();
});
beforeEach(() => { vi.useFakeTimers(); vi.mocked(coreApi).mockReset(); localStorage.clear(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const conversations = [{ id: "a", title: "תכנון ממשק", message_count: 2 }, { id: "b", title: "סיכום פגישה", message_count: 4 }];
const tick = async () => { await act(async () => { await vi.advanceTimersByTimeAsync(200); }); };
function setup(available: Conversation[] = conversations) {
  const select = vi.fn(), file = vi.fn(), create = vi.fn();
  function Fixture() {
    const [open, setOpen] = useState(false);
    return <DesignSystemProvider theme="light"><button onClick={() => setOpen(true)}>חיפוש</button>
      <SearchDialog open={open} conversations={available} onClose={() => setOpen(false)} onSelect={select} onCreate={create} onFile={file} />
    </DesignSystemProvider>;
  }
  render(<Fixture />); fireEvent.click(screen.getByRole("button", { name: "חיפוש" }));
  return { select, file, create, input: screen.getByRole("combobox") };
}

test("suggestions prioritize searched and visited chats, ignore deleted and empty chats, and deduplicate", () => {
  rememberConversationVisit("b", true); rememberConversationVisit("a"); rememberConversationVisit("deleted", true);
  expect(suggestedConversations([...conversations, { id: "empty", title: "ריקה", message_count: 0 }]).map(item => item.id)).toEqual(["b", "a"]);
  rememberConversationVisit("b");
  expect(suggestedConversations(conversations).map(item => item.id)).toEqual(["b", "a"]);
});

test("literal highlighting handles punctuation, repeated matches and HTML as text", () => {
  expect(highlightParts("A+B <script> a+b", "a+b")).toEqual([{ text: "A+B", match: true }, { text: " <script> ", match: false }, { text: "a+b", match: true }]);
});

test("opens with focused input, suggestions and quick actions; selection uses keyboard and restores focus", () => {
  const { input, select } = setup();
  expect(document.activeElement).toBe(input);
  expect(screen.getAllByRole("option")).toHaveLength(2);
  expect(coreApi).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "ArrowDown" }); fireEvent.keyDown(input, { key: "Enter" });
  expect(select).toHaveBeenCalledWith(conversations[1]);
  expect(screen.queryByRole("dialog")).toBeNull();
  // fireEvent does not focus the trigger as a browser click does.
});

test("debounces queries, discards stale success/failure and highlights matching message snippets", async () => {
  let oldResolve!: (value: unknown) => void;
  vi.mocked(coreApi).mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve; }));
  const { input } = setup();
  fireEvent.change(input, { target: { value: "ישן" } }); await tick();
  vi.mocked(coreApi).mockResolvedValueOnce({ items: [{ id: "b", title: "תכנון חיפוש", search_preview: "תוכן חיפוש בהודעה קודמת", message_count: 4 }] });
  fireEvent.change(input, { target: { value: "חיפוש" } });
  expect(screen.getAllByRole("option")).toHaveLength(2);
  expect(screen.getByRole("status", { name: "מחפש…" }).className).toBe("search-heading-progress"); await tick();
  await act(async () => { oldResolve({ items: [{ id: "old", title: "תוצאה ישנה", message_count: 1 }] }); });
  expect(screen.getByRole("option").textContent).toContain("תוכן חיפוש");
  expect(document.querySelectorAll("mark")).toHaveLength(2);
  expect(coreApi).toHaveBeenLastCalledWith("GET", expect.stringContaining(encodeURIComponent("חיפוש")));
});

test("file search is scoped to artifacts, opens the result, and handles errors with retry", async () => {
  const { file } = setup();
  fireEvent.click(screen.getByRole("button", { name: "חיפוש בקבצים" }));
  const input = screen.getByRole("combobox");
  expect(document.activeElement).toBe(input);
  expect(coreApi).not.toHaveBeenCalled();
  vi.mocked(coreApi).mockRejectedValueOnce(new Error("offline"));
  fireEvent.change(input, { target: { value: "תקציב" } }); await tick();
  expect(screen.getByRole("alert").textContent).toContain("offline");
  vi.mocked(coreApi).mockResolvedValueOnce({ items: [{ name: "תקציב.xlsx", path: "reports/תקציב.xlsx", size: 100, modified_at: "2026-10-16" }] });
  fireEvent.click(screen.getByRole("button", { name: "ניסיון נוסף" })); await tick();
  expect(coreApi).toHaveBeenLastCalledWith("GET", `/v2/workbench/artifacts?q=${encodeURIComponent("תקציב")}`);
  fireEvent.keyDown(input, { key: "Enter" });
  expect(file).toHaveBeenCalledWith("reports/תקציב.xlsx");
});

test("a late chat-search failure cannot replace file results after switching modes", async () => {
  let rejectOld!: (reason: Error) => void;
  vi.mocked(coreApi).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectOld = reject; }));
  const { input } = setup();
  fireEvent.change(input, { target: { value: "ישן" } }); await tick();
  fireEvent.change(input, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "חיפוש בקבצים" }));
  vi.mocked(coreApi).mockResolvedValueOnce({ items: [{ name: "report.pdf", path: "report.pdf", size: 5, modified_at: "2026-10-16" }] });
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "report" } }); await tick();
  await act(async () => { rejectOld(new Error("stale failure")); });
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("option").textContent).toContain("report.pdf");
});

test("recent heading collapses the list and divider tracks scroll without filtering history", () => {
  render(<DesignSystemProvider theme="light"><ChatSidebar open logo="/logo.png" conversations={conversations} activeId="" loading={false} error="" unread={() => 0}
    onToggle={vi.fn()} onCreate={vi.fn()} onSearch={vi.fn()} onSelect={vi.fn()} actions={() => []} onManagement={vi.fn()} /></DesignSystemProvider>);
  expect(screen.queryByRole("searchbox")).toBeNull();
  const heading = screen.getByRole("button", { name: "שיחות אחרונות" });
  fireEvent.click(heading); expect(heading.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByRole("button", { name: "תכנון ממשק" })).toBeNull();
  fireEvent.click(heading);
  const list = document.querySelector(".conversation-list")!;
  fireEvent.scroll(list, { target: { scrollTop: 35 } }); expect(document.querySelector(".is-scrolled")).not.toBeNull();
  fireEvent.scroll(list, { target: { scrollTop: 0 } }); expect(document.querySelector(".is-scrolled")).toBeNull();
});

test("empty search has up to nine suggestions, exact placeholder, no X buttons and no result icons", () => {
  setup(Array.from({ length: 14 }, (_, i) => ({ id: String(i), title: `שיחה ${i}`, message_count: 2, pinned: true })));
  expect(screen.getAllByRole("option")).toHaveLength(9);
  expect(screen.getByRole("combobox").getAttribute("placeholder")).toBe("חפש בשיחות");
  expect(screen.queryByRole("button", { name: "סגירה" })).toBeNull();
  expect(screen.queryByRole("button", { name: "ניקוי החיפוש" })).toBeNull();
  expect(document.querySelector(".search-result .sds-icon")).toBeNull();
});

test("quick actions disappear as soon as typing begins, old matches remain until replaced", async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(coreApi).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const { input } = setup();
  fireEvent.change(input, { target: { value: "תכנון" } });
  expect(screen.queryByRole("button", { name: "שיחה חדשה" })).toBeNull();
  expect(screen.queryByRole("button", { name: "חיפוש בקבצים" })).toBeNull();
  expect(screen.getAllByRole("option")).toHaveLength(2); await tick();
  await act(async () => { resolve({ items: [{ ...conversations[0], match_kind: "title", search_preview: "תוכן שלא אמור להיות מוצג" }] }); });
  expect(screen.getAllByRole("option")).toHaveLength(1);
  expect(document.querySelector(".search-result-detail")).toBeNull();
  fireEvent.change(input, { target: { value: "" } });
  expect(screen.getByRole("button", { name: "חיפוש בקבצים" })).toBeTruthy();
});

test("search with no previous matches uses the larger centered progress ring", async () => {
  vi.mocked(coreApi).mockResolvedValueOnce({ items: [] });
  const { input } = setup([]);
  fireEvent.change(input, { target: { value: "abc" } });
  expect(screen.getByRole("status", { name: "מחפש…" }).className).toBe("search-loading");
  await tick(); expect(screen.getByRole("status").textContent).toContain("לא נמצאו תוצאות");
});

test("separate message matches retain their own identity and ordinal, and results are capped at nine", async () => {
  vi.mocked(coreApi).mockResolvedValueOnce({ items: Array.from({ length: 12 }, (_, i) => ({
    ...conversations[0], match_id: `a:message:${i}`, match_kind: "content", match_ordinal: i, search_preview: `תוכן מתאים ${i}`,
  })) });
  const { input, select } = setup();
  fireEvent.change(input, { target: { value: "תוכן" } }); await tick();
  expect(screen.getAllByRole("option")).toHaveLength(9);
  fireEvent.click(screen.getAllByRole("option")[2]);
  expect(select).toHaveBeenCalledWith(expect.objectContaining({ id: "a", match_ordinal: 2 }));
  expect(coreApi).toHaveBeenCalledWith("GET", expect.stringContaining("matches=messages&limit=9"));
});

test("multi-word highlights and file ranking favor filenames and cap the result list", () => {
  expect(highlightParts("תקציב פרויקט שנתי", "שנתי תקציב").filter(part => part.match).map(part => part.text)).toEqual(["תקציב", "שנתי"]);
  const files = Array.from({ length: 14 }, (_, i) => ({ name: `file-${i}`, path: `report/file-${i}`, size: 1, modified_at: "2026-10-16" }));
  const ranked = rankSearchFiles([...files, { name: "report", path: "old/report", size: 1, modified_at: "2020-01-01" }], "report");
  expect(ranked).toHaveLength(9); expect(ranked[0].name).toBe("report");
});
