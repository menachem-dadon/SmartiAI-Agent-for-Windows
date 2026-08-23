export type WorkbenchTab = "browser" | "files" | "terminal" | "canvas" | "artifacts";

export interface WorkspaceState {
  conversationDrawerOpen: boolean;
  workbenchOpen: boolean;
  activeWorkbenchTab: WorkbenchTab | null;
}

export const initialWorkspaceState: WorkspaceState = {
  conversationDrawerOpen: true,
  workbenchOpen: false,
  activeWorkbenchTab: null,
};

export type WorkspaceAction =
  | { type: "toggle-conversations" }
  | { type: "set-conversations"; open: boolean }
  | { type: "open-workbench"; tab: WorkbenchTab }
  | { type: "close-workbench" }
  | { type: "responsive-narrow" };

export function workspaceReducer(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  if (action.type === "toggle-conversations") return { ...state, conversationDrawerOpen: !state.conversationDrawerOpen };
  if (action.type === "set-conversations") return { ...state, conversationDrawerOpen: action.open };
  if (action.type === "open-workbench") return { ...state, workbenchOpen: true, activeWorkbenchTab: action.tab };
  if (action.type === "close-workbench") return { ...state, workbenchOpen: false, activeWorkbenchTab: null };
  if (action.type === "responsive-narrow") return { ...state, conversationDrawerOpen: false };
  return state;
}

export function workspaceColumns(state: WorkspaceState): string {
  const sidebar = state.conversationDrawerOpen ? "var(--drawer-width)" : "var(--rail-width)";
  if (!state.workbenchOpen) return `${sidebar} minmax(0, 1fr) 0px`;
  return `${sidebar} minmax(440px, 35vw) minmax(420px, 1fr)`;
}
