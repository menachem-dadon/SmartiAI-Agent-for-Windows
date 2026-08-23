import { describe, expect, test } from "vitest";
import { activityState, autonomyLabels, legacyUi, workspaceIsNarrow } from "./legacyUiParity";

describe("Point 9A source-derived parity contract", () => {
  test("locks PyQt geometry and responsive values", () => {
    expect(legacyUi).toMatchObject({
      titleBarHeight: 36, sidebarExpandedWidth: 286, sidebarCollapsedWidth: 58,
      chatMaximumWidth: 1040, workbenchNarrowUsableWidth: 920,
      composerMinimumHeight: 112, composerRadius: 40.5,
      composerActionSize: 52, attachmentButtonSize: 42, quickControlGap: 10,
      userCollapsedLines: 6, conversationRowHeight: 68, activityIndicatorSize: 24,
      voiceOverlayExpandedWidth: 342, voiceOverlayHeight: 70,
    });
    expect(workspaceIsNarrow(1205)).toBe(true);
    expect(workspaceIsNarrow(1206)).toBe(false);
    expect(legacyUi.chatMaximumWidth - legacyUi.composerHorizontalGutter * 2).toBe(984);
  });

  test("projects activity priority and original autonomy labels", () => {
    expect(activityState({ runtime_status: "waiting_for_approval", is_busy: true, needs_input: true, unread_count: 2 })).toBe("waiting_for_approval");
    expect(activityState({ runtime_status: "cancelling", is_busy: true })).toBe("running");
    expect(activityState({ needs_input: true, unread_count: 2 })).toBe("waiting_for_approval");
    expect(activityState({ unread_count: 2 })).toBe("unread");
    expect(activityState({})).toBe("idle");
    expect(autonomyLabels).toEqual({ locked_down: "בטוח", balanced: "מאוזן", max_autonomy: "אוטונומי", custom: "מותאם אישית" });
  });

  test("keeps the original nested menu and voice overlay geometry", () => {
    expect(legacyUi.voiceOverlayExpandedWidth).toBe(342);
    expect(legacyUi.voiceOverlayCompactWidth).toBe(298);
    expect(legacyUi.voiceOverlayHeight).toBe(70);
  });
});
