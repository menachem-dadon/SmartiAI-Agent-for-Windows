import { workspaceIsNarrow } from "./legacyUiParity";

export type WorkbenchTab = "browser" | "files" | "terminal" | "canvas" | "artifacts";

export interface WorkspaceState {
  conversationDrawerOpen: boolean;
  workbenchOpen: boolean;
  activeWorkbenchTab: WorkbenchTab | null;
}

export type WorkbenchTabRecord = { id: string; kind: WorkbenchTab; title: string };
export type WorkbenchSnapshot = { tabs: WorkbenchTabRecord[]; active: string };

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
  | { type: "activate-narrow-surface"; surface: "conversations"; tab?: never }
  | { type: "activate-narrow-surface"; surface: "workbench"; tab: WorkbenchTab }
  | { type: "restore-layout"; conversations: boolean; workbench: boolean; tab: WorkbenchTab | null }
  | { type: "responsive-narrow" };

export function workspaceReducer(state: WorkspaceState, action: WorkspaceAction): WorkspaceState {
  if (action.type === "toggle-conversations") return { ...state, conversationDrawerOpen: !state.conversationDrawerOpen };
  if (action.type === "set-conversations")
    return state.conversationDrawerOpen === action.open
      ? state
      : { ...state, conversationDrawerOpen: action.open };
  if (action.type === "open-workbench") return { ...state, workbenchOpen: true, activeWorkbenchTab: action.tab };
  if (action.type === "close-workbench")
    return !state.workbenchOpen && state.activeWorkbenchTab === null
      ? state
      : { ...state, workbenchOpen: false, activeWorkbenchTab: null };
  if (action.type === "activate-narrow-surface") {
    if (action.surface === "conversations")
      return { conversationDrawerOpen: true, workbenchOpen: false, activeWorkbenchTab: null };
    return { conversationDrawerOpen: false, workbenchOpen: true, activeWorkbenchTab: action.tab };
  }
  if (action.type === "restore-layout") return { conversationDrawerOpen: action.conversations, workbenchOpen: action.workbench, activeWorkbenchTab: action.workbench ? action.tab : null };
  if (action.type === "responsive-narrow")
    return state.conversationDrawerOpen
      ? { ...state, conversationDrawerOpen: false }
      : state;
  return state;
}

const workbenchKinds = new Set<WorkbenchTab>(["browser", "files", "terminal", "canvas", "artifacts"]);
export function parseWorkbenchSnapshot(value: unknown): WorkbenchSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const record = value as { tabs?: unknown; active?: unknown };
  if (!Array.isArray(record.tabs)) return null;
  const tabs = record.tabs.slice(0, 20).flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as Record<string, unknown>;
    const kind = String(candidate.kind || "") as WorkbenchTab;
    const id = String(candidate.id || "").slice(0, 100);
    if (!id || !workbenchKinds.has(kind)) return [];
    return [{ id, kind, title: String(candidate.title || kind).slice(0, 100) }];
  });
  const active = String(record.active || "");
  return { tabs, active: tabs.some((item) => item.id === active) ? active : tabs[0]?.id || "" };
}

export function openWorkbenchTab(
  state: WorkbenchSnapshot,
  tab: WorkbenchTabRecord,
  forceNew = false,
): WorkbenchSnapshot {
  const existing = state.tabs.find((item) => item.kind === tab.kind);
  const singleton = tab.kind === "canvas" || tab.kind === "artifacts";
  if (existing && (!forceNew || singleton))
    return { ...state, active: existing.id };
  return { tabs: [...state.tabs, tab], active: tab.id };
}

export function closeWorkbenchTab(
  state: WorkbenchSnapshot,
  id: string,
): WorkbenchSnapshot {
  const index = state.tabs.findIndex((item) => item.id === id);
  if (index < 0) return state;
  const tabs = state.tabs.filter((item) => item.id !== id);
  if (state.active !== id) return { tabs, active: state.active };
  return { tabs, active: tabs[Math.min(index, tabs.length - 1)]?.id || "" };
}

export function reorderWorkbenchTabs(
  state: WorkbenchSnapshot,
  sourceId: string,
  targetId: string,
): WorkbenchSnapshot {
  const source = state.tabs.findIndex((item) => item.id === sourceId);
  const target = state.tabs.findIndex((item) => item.id === targetId);
  if (source < 0 || target < 0 || source === target) return state;
  const tabs = [...state.tabs];
  const [moved] = tabs.splice(source, 1);
  tabs.splice(target, 0, moved);
  return { ...state, tabs };
}

export function workspaceOpenSizes(totalWidth: number, sidebarWidth: number): {
  narrow: boolean;
  workbench: number;
  chat: number;
} {
  const usable = Math.max(320, Math.trunc(totalWidth) - Math.trunc(sidebarWidth));
  const narrow = usable < 920;
  if (narrow) return { narrow, workbench: usable, chat: usable };
  const workbench = Math.min(Math.max(480, Math.trunc(usable * 0.52)), usable - 520);
  return { narrow, workbench, chat: usable - workbench };
}

export function clampWorkbenchResize(
  totalWidth: number,
  sidebarWidth: number,
  desiredWidth: number,
): number {
  const usable = Math.max(320, Math.trunc(totalWidth) - Math.trunc(sidebarWidth));
  return Math.max(320, Math.min(Math.trunc(desiredWidth), usable - 320));
}

// The surface keeps its open size while translating out of view. Only the
// reserved grid track collapses, so native pages do not reflow during toggles.
export function workspaceWorkbenchWidth(
  state: WorkspaceState,
  totalWidth = 1380,
  workbenchOverride: number | null = null,
): number {
  const sidebarWidth = state.conversationDrawerOpen ? 286 : 58;
  return workbenchOverride === null
    ? workspaceOpenSizes(totalWidth, sidebarWidth).workbench
    : clampWorkbenchResize(totalWidth, sidebarWidth, workbenchOverride);
}

export function workspaceColumns(
  state: WorkspaceState,
  totalWidth = 1380,
  workbenchOverride: number | null = null,
): string {
  if (workspaceIsNarrow(totalWidth))
    return "var(--rail-width) minmax(0, 1fr) 0px";
  const sidebar = state.conversationDrawerOpen ? "var(--drawer-width)" : "var(--rail-width)";
  if (!state.workbenchOpen) return `${sidebar} minmax(0, 1fr) 0px`;
  const workbench = workspaceWorkbenchWidth(state, totalWidth, workbenchOverride);
  return `${sidebar} minmax(0, 1fr) ${workbench}px`;
}
