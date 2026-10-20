import { expect, test } from "vitest";
import { liveTimeline } from "./liveTimeline";
import { mergeMessages } from "../chatState";
import type { ChatMessage, RunRecord } from "../chatTypes";

const message = (text: string, metadata: Record<string, unknown> = {}): ChatMessage => ({ role: "assistant", content: text, metadata });
const run = (task: string): RunRecord => ({ id: `run-${task}`, session_id: "chat", status: "running", user_text: "", metadata: { live_task_id: task } });

test("one task process moves after intermediate dialogue and before its final", () => {
  const rows = [message("Starting"), message("question"), message("answer")];
  expect(liveTimeline(rows, [run("one")]).map(row => row.content)).toEqual(["Starting", "question", "answer", ""]);
  const final = message("Finished", { live_task_id: "one", live_final: true });
  const timeline = liveTimeline([...rows, final, message("later")], [run("one")]);
  expect(timeline.map(row => row.content)).toEqual(["Starting", "question", "answer", "", "Finished", "later"]);
  expect(timeline[3].message_id).toBe("live-process:one");
});
test("separate tasks retain separate process blocks and executor prose is hidden", () => {
  const rows = [message("backend", { run_id: "run-one", live_backend: true }), message("first", { live_task_id: "one", live_final: true }), message("second", { live_task_id: "two", live_final: true })];
  const timeline = liveTimeline(rows, [run("one"), run("two")]);
  expect(timeline.map(row => row.content)).toEqual(["", "first", "", "second"]);
  expect(new Set(timeline.filter(row => row.metadata?.live_process).map(row => row.message_id)).size).toBe(2);
});
test("persisted process survives an older run falling outside the run-list window", () => {
  const rows = [message("", { live_process: true, live_task_id: "old", run_id: "old-run", agent_process: ["tool"] }), message("final", { live_task_id: "old", live_final: true })];
  expect(liveTimeline(rows, []).map(row => row.content)).toEqual(["", "final"]);
});
test("transcription updates replace a stable message instead of duplicating bubbles", () => {
  const before = message("I", { live_message_id: "utterance", live_partial: true });
  const after = message("I would like", { live_message_id: "utterance", live_partial: false });
  expect(mergeMessages([before], [after])).toEqual([after]);
});
