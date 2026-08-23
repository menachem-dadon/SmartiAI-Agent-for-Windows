/** Binding values extracted from the PyQt Points 7-9 implementation. */
export const legacyUi = {
  titleBarHeight: 36,
  sidebarExpandedWidth: 286,
  sidebarCollapsedWidth: 58,
  sidebarAnimationMs: 300,
  chatMaximumWidth: 1040,
  workbenchNarrowUsableWidth: 920,
  workbenchMinimumWidth: 480,
  chatMinimumWithWorkbench: 520,
  composerMinimumHeight: 112,
  composerRadius: 40.5,
  composerHorizontalGutter: 28,
  composerBottomGutter: 22,
  composerActionSize: 52,
  composerActionBottomGap: 7,
  attachmentButtonSize: 42,
  quickControlGap: 10,
  userBubbleWidthRatio: 0.76,
  userBubbleWidthOffset: 30,
  assistantBubbleWidthOffset: 52,
  messageActionSize: 36,
  messageActionRowHeight: 40,
  userCollapsedLines: 6,
  historySearchDebounceMs: 40,
  conversationRowHeight: 68,
  conversationRowGap: 10,
  activityIndicatorSize: 24,
  voiceOverlayExpandedWidth: 342,
  voiceOverlayCompactWidth: 298,
  voiceOverlayHeight: 70,
} as const;

export function workspaceIsNarrow(totalWidth: number, sidebarCollapsed = false): boolean {
  const sidebar = sidebarCollapsed ? legacyUi.sidebarCollapsedWidth : legacyUi.sidebarExpandedWidth;
  return Math.max(320, totalWidth - sidebar) < legacyUi.workbenchNarrowUsableWidth;
}

export function activityState(item: { runtime_status?: string; is_busy?: boolean; needs_input?: boolean; unread_count?: number }): "running" | "waiting_for_approval" | "unread" | "idle" {
  const runtime = String(item.runtime_status || "idle");
  if (runtime === "waiting_for_approval" || item.needs_input) return "waiting_for_approval";
  if (["queued", "running", "cancelling"].includes(runtime) || item.is_busy) return "running";
  if (item.unread_count) return "unread";
  return "idle";
}

export const autonomyLabels: Record<string, string> = {
  locked_down: "בטוח",
  balanced: "מאוזן",
  max_autonomy: "אוטונומי",
  custom: "מותאם אישית",
};
