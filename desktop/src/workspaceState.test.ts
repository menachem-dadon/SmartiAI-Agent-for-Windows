import { describe, expect, test } from "vitest";
import { closeWorkbenchTab, initialWorkspaceState, openWorkbenchTab, parseWorkbenchSnapshot, reorderWorkbenchTabs, workspaceColumns, workspaceOpenSizes, workspaceReducer } from "./workspaceState";

describe("Workspace shell state", () => {
  test("starts with a central chat, right drawer, and truly empty left Workbench", () => {
    expect(initialWorkspaceState).toEqual({ conversationDrawerOpen: true, workbenchOpen: false, activeWorkbenchTab: null });
    expect(workspaceColumns(initialWorkspaceState)).toContain("0px");
  });

  test("restores, focuses, repeats, reorders and closes persisted tabs", () => {
    const restored = parseWorkbenchSnapshot({ tabs: [
      { id: "browser-1", kind: "browser", title: "דפדפן" },
      { id: "terminal-2", kind: "terminal", title: "מסוף" },
    ], active: "browser-1" })!;
    const focused = openWorkbenchTab(restored, { id: "browser-3", kind: "browser", title: "דפדפן 3" });
    expect(focused.tabs).toHaveLength(2);
    expect(focused.active).toBe("browser-1");
    const repeated = openWorkbenchTab(focused, { id: "browser-3", kind: "browser", title: "דפדפן 3" }, true);
    expect(repeated.tabs).toHaveLength(3);
    const reordered = reorderWorkbenchTabs(repeated, "browser-3", "browser-1");
    expect(reordered.tabs[0].id).toBe("browser-3");
    const closed = closeWorkbenchTab({ ...reordered, active: "browser-3" }, "browser-3");
    expect(closed.active).toBe("browser-1");
  });

  test("opens one dynamic tab and clears it completely on close", () => {
    const opened = workspaceReducer(initialWorkspaceState, { type: "open-workbench", tab: "browser" });
    expect(opened).toMatchObject({ workbenchOpen: true, activeWorkbenchTab: "browser" });
    expect(workspaceColumns(opened)).toBe("var(--drawer-width) minmax(0, 526px) 568px");
    expect(workspaceReducer(opened, { type: "close-workbench" })).toEqual(initialWorkspaceState);
  });

  test("uses the exact PyQt 52 percent splitter rule and narrow fallback", () => {
    expect(workspaceOpenSizes(1380, 286)).toEqual({ narrow: false, workbench: 568, chat: 526 });
    expect(workspaceOpenSizes(1205, 286)).toEqual({ narrow: true, workbench: 919, chat: 0 });
    expect(workspaceOpenSizes(1206, 286)).toEqual({ narrow: false, workbench: 400, chat: 520 });
  });

  test("narrow layout collapses the drawer but preserves an open Workbench", () => {
    const opened = { conversationDrawerOpen: true, workbenchOpen: true, activeWorkbenchTab: "files" as const };
    expect(workspaceReducer(opened, { type: "responsive-narrow" })).toEqual({ conversationDrawerOpen: false, workbenchOpen: true, activeWorkbenchTab: "files" });
  });

  test("the collapsed right rail can always expand again", () => {
    const compact = workspaceReducer(initialWorkspaceState, { type: "responsive-narrow" });
    expect(workspaceReducer(compact, { type: "toggle-conversations" }).conversationDrawerOpen).toBe(true);
  });
});
