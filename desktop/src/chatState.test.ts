import { describe, expect, test } from "vitest";
import { ACTIVE_RUN_STATES, mergeMessages, pendingApiKeyRequest, semanticStep } from "./chatState";

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

test("projects the complete Core-owned API-key interruption until the same request is answered", () => {
  const required = { event_id: 10, sequence: 1, event_type: "api_key_required", session_id: "s", run_id: "r", payload: { secret_key: "openai_api_key", provider: "openai", provider_label: "OpenAI", title: "חסר מפתח", message: "הזן מפתח", help_url: "https://example.com/key", key_instructions: "צור מפתח והעתק אותו." }, created_at: "" };
  expect(pendingApiKeyRequest([required])).toEqual({ runId: "r", secretKey: "openai_api_key", provider: "openai", providerLabel: "OpenAI", title: "חסר מפתח", message: "הזן מפתח", helpUrl: "https://example.com/key", keyInstructions: "צור מפתח והעתק אותו." });
  expect(pendingApiKeyRequest([required, { ...required, event_id: 11, sequence: 2, event_type: "api_key_submitted", payload: { secret_key: "openai_api_key" } }])).toBeNull();
});
