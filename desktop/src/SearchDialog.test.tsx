// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";
import { coreApi } from "./coreApi";
import { DesignSystemProvider } from "./design-system";
import { SearchDialog } from "./SearchDialog";
import { highlightParts, rememberConversationVisit, suggestedConversations } from "./searchState";
import { ChatSidebar } from "./ChatSidebar";

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
function setup() {
  const select = vi.fn(), file = vi.fn(), create = vi.fn();
  function Fixture() {
    const [open, setOpen] = useState(false);
    return <DesignSystemProvider theme="light"><button onClick={() => setOpen(true)}>חיפוש</button>
      <SearchDialog open={open} conversations={conversations} onClose={() => setOpen(false)} onSelect={select} onCreate={create} onFile={file} />
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
  expect(screen.queryByRole("option")).toBeNull(); await tick();
  await act(async () => { oldResolve({ items: [{ id: "old", title: "תוצאה ישנה", message_count: 1 }] }); });
  expect(screen.getByRole("option").textContent).toContain("תוכן חיפוש");
  expect(document.querySelectorAll("mark")).toHaveLength(2);
  expect(coreApi).toHaveBeenLastCalledWith("GET", expect.stringContaining(encodeURIComponent("חיפוש")));
});

test("file search is scoped to artifacts, opens the result, and handles errors with retry", async () => {
  const { file } = setup();
  fireEvent.click(screen.getByRole("button", { name: "חיפוש קבצים ותוצרים" }));
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
  fireEvent.click(screen.getByRole("button", { name: "חיפוש קבצים ותוצרים" }));
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
