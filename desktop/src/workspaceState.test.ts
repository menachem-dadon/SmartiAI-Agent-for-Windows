import { describe, expect, test } from "vitest";
import { initialWorkspaceState, workspaceColumns, workspaceReducer } from "./workspaceState";

describe("Workspace shell state", () => {
  test("starts with a central chat, right drawer, and truly empty left Workbench", () => {
    expect(initialWorkspaceState).toEqual({ conversationDrawerOpen: true, workbenchOpen: false, activeWorkbenchTab: null });
    expect(workspaceColumns(initialWorkspaceState)).toContain("0px");
  });

  test("opens one dynamic tab and clears it completely on close", () => {
    const opened = workspaceReducer(initialWorkspaceState, { type: "open-workbench", tab: "browser" });
    expect(opened).toMatchObject({ workbenchOpen: true, activeWorkbenchTab: "browser" });
    expect(workspaceColumns(opened)).toContain("minmax(440px, 35vw)");
    expect(workspaceColumns(opened)).toContain("minmax(420px, 1fr)");
    expect(workspaceReducer(opened, { type: "close-workbench" })).toEqual(initialWorkspaceState);
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
