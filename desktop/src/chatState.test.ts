import { describe, expect, test } from "vitest";
import {
  ACTIVE_RUN_STATES,
  loadRunEventHistory,
  mergeActivityEvents,
  mergeMessages,
  pendingApiKeyRequest,
  recentConversations,
  semanticStep,
} from "./chatState";
import type { RunEvent } from "./chatTypes";

describe("durable chat state", () => {
  test("restores every page of a long run while preserving live results and excluding token traffic", async () => {
    const event = (id: number, event_type = "run_step"): RunEvent => ({ event_id: id, sequence: id, event_type, run_id: "r", session_id: "s", payload: {}, created_at: "" });
    const all = Array.from({ length: 1203 }, (_, index) => event(index + 1, index % 3 === 0 ? "run_stream" : "run_step"));
    let merged = [event(1204)];
    const cursors: number[] = [];
    await loadRunEventHistory(async after => {
      cursors.push(after); return { items: all.filter(event => event.sequence > after).slice(0, 500) };
    }, items => { merged = mergeActivityEvents(merged, items); });
    expect(cursors).toEqual([0, 500, 1000]);
    expect(merged.length).toBe(803);
    expect(merged[0].event_id).toBe(2); expect(merged[merged.length - 1]?.event_id).toBe(1204);
    expect(mergeActivityEvents(merged, merged)).toEqual(merged);
  });

  test("a late page from a different conversation or Core generation cannot update the current view", async () => {
    let current = true, consumed = false;
    await loadRunEventHistory(async () => { current = false; return { items: [{ sequence: 1 } as RunEvent] }; }, () => { consumed = true; }, () => current);
    expect(consumed).toBe(false);
  });
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

  test("late history pages keep Core message order while updating the same streamed reply", () => {
    const older = { role: "user" as const, content: "older page", message_id: "session:47", created_at: "same" };
    const user = { role: "user" as const, content: "latest question", message_id: "session:100", created_at: "same" };
    const partial = { role: "assistant" as const, content: "partial", message_id: "session:101", metadata: { run_id: "reply" } };
    const final = { ...partial, content: "final" };
    expect(mergeMessages([user, partial], [older, user, final])).toEqual([older, user, final]);
    expect(mergeMessages([older, user, final], [user, final])).toEqual([older, user, final]);
  });

  test("keeps a new conversation out of recents until its first message is stored", () => {
    const empty = { id: "empty", title: "שיחה חדשה", message_count: 0 };
    const started = { id: "started", title: "שלום", message_count: 1 };

    expect(recentConversations([empty, started])).toEqual([started]);
    expect(recentConversations([{ ...empty, message_count: 1 }])).toEqual([
      { ...empty, message_count: 1 },
    ]);
  });

  test("renders semantic tool activity", () => {
    expect(semanticStep({ event_id: 1, sequence: 1, event_type: "tool_started", session_id: "s", run_id: "r", payload: { tool: "search" }, created_at: "" })).toBe("מפעיל search");
  });
});

test("projects the complete Core-owned API-key interruption until the same request is answered", () => {
  const required = { event_id: 10, sequence: 1, event_type: "api_key_required", session_id: "s", run_id: "r", payload: { secret_key: "openai_api_key", provider: "openai", provider_label: "OpenAI", title: "חסר מפתח", message: "הזן מפתח", help_url: "https://example.com/key", key_instructions: "צור מפתח והעתק אותו." }, created_at: "" };
  expect(pendingApiKeyRequest([required])).toEqual({ runId: "r", secretKey: "openai_api_key", provider: "openai", providerLabel: "OpenAI", title: "חסר מפתח", message: "הזן מפתח", helpUrl: "https://example.com/key", keyInstructions: "צור מפתח והעתק אותו." });
  expect(pendingApiKeyRequest([required, { ...required, event_id: 11, sequence: 2, event_type: "api_key_submitted", payload: { secret_key: "openai_api_key" } }])).toBeNull();
});
