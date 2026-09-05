import { describe, expect, test } from "vitest";
import { closeWorkbenchTab, initialWorkspaceState, openWorkbenchTab, parseWorkbenchSnapshot, reorderWorkbenchTabs, workspaceColumns, workspaceOpenSizes, workspaceReducer, workspaceWorkbenchWidth } from "./workspaceState";

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
    expect(workspaceColumns(opened)).toBe("var(--drawer-width) minmax(0, 1fr) 568px");
    expect(workspaceReducer(opened, { type: "close-workbench" })).toEqual(initialWorkspaceState);
  });

  test("uses the PyQt split rule when wide and preserves chat beneath narrow overlays", () => {
    expect(workspaceOpenSizes(1380, 286)).toEqual({ narrow: false, workbench: 568, chat: 526 });
    expect(workspaceOpenSizes(1205, 286)).toEqual({ narrow: true, workbench: 919, chat: 919 });
    expect(workspaceOpenSizes(1206, 286)).toEqual({ narrow: false, workbench: 400, chat: 520 });

    const open = { conversationDrawerOpen: true, workbenchOpen: true, activeWorkbenchTab: "browser" as const };
    expect(workspaceColumns(open, 1205)).toBe("var(--rail-width) minmax(0, 1fr) 0px");
    expect(workspaceColumns(open, 1206)).toBe("var(--drawer-width) minmax(0, 1fr) 400px");
  });

  test("keeps the native surface width stable while only its reserved space closes", () => {
    const opened = { ...initialWorkspaceState, workbenchOpen: true };
    expect(workspaceWorkbenchWidth(opened, 1380)).toBe(568);
    expect(workspaceWorkbenchWidth(initialWorkspaceState, 1380)).toBe(568);
    expect(workspaceColumns(opened, 1380, 700)).toBe("var(--drawer-width) minmax(0, 1fr) 700px");
    expect(workspaceColumns(initialWorkspaceState, 1380, 700)).toBe("var(--drawer-width) minmax(0, 1fr) 0px");
  });

  test("narrow layout collapses the drawer but preserves an open Workbench", () => {
    const opened = { conversationDrawerOpen: true, workbenchOpen: true, activeWorkbenchTab: "files" as const };
    expect(workspaceReducer(opened, { type: "responsive-narrow" })).toEqual({ conversationDrawerOpen: false, workbenchOpen: true, activeWorkbenchTab: "files" });
  });

  test("the collapsed right rail can always expand again", () => {
    const compact = workspaceReducer(initialWorkspaceState, { type: "responsive-narrow" });
    expect(workspaceReducer(compact, { type: "toggle-conversations" }).conversationDrawerOpen).toBe(true);
  });

  test("does not create redundant layout state during repeated resize events", () => {
    const compact = workspaceReducer(initialWorkspaceState, { type: "responsive-narrow" });
    expect(workspaceReducer(compact, { type: "responsive-narrow" })).toBe(compact);
    expect(workspaceReducer(compact, { type: "set-conversations", open: false })).toBe(compact);
  });

  test("keeps compact drawers mutually exclusive above the chat", () => {
    const workbench = workspaceReducer(initialWorkspaceState, {
      type: "activate-narrow-surface",
      surface: "workbench",
      tab: "files",
    });
    expect(workbench).toEqual({
      conversationDrawerOpen: false,
      workbenchOpen: true,
      activeWorkbenchTab: "files",
    });
    expect(workspaceReducer(workbench, {
      type: "activate-narrow-surface",
      surface: "conversations",
    })).toEqual(initialWorkspaceState);
  });
});
