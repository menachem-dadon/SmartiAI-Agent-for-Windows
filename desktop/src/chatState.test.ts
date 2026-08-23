import { describe, expect, test } from "vitest";
import { ACTIVE_RUN_STATES, mergeMessages, semanticStep } from "./chatState";

describe("durable chat state", () => {
  test("keeps concurrent active states scoped by run", () => {
    expect(ACTIVE_RUN_STATES.has("running")).toBe(true);
    expect(ACTIVE_RUN_STATES.has("waiting_for_approval")).toBe(true);
    expect(ACTIVE_RUN_STATES.has("completed")).toBe(false);
  });

  test("merges paginated messages without replay duplicates", () => {
    const older = [{ role: "user" as const, content: "ישן", created_at: "1" }];
    const current = [{ role: "user" as const, content: "ישן", created_at: "1" }, { role: "assistant" as const, content: "חדש", created_at: "2" }];
    expect(mergeMessages(older, current).map((item) => item.content)).toEqual(["ישן", "חדש"]);
  });

  test("renders semantic tool activity", () => {
    expect(semanticStep({ event_id: 1, sequence: 1, event_type: "tool_started", session_id: "s", run_id: "r", payload: { tool: "search" }, created_at: "" })).toBe("מפעיל search");
  });
});
