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
  expect(timeline.map(row => row.content)).toEqual(["Starting", "question", "answer", "Finished", "later"]);
  expect(timeline[3].metadata?.live_answer_process).toBe(true);
});
test("separate tasks retain separate process blocks and executor prose is hidden", () => {
  const rows = [message("backend", { run_id: "run-one", live_backend: true }), message("first", { live_task_id: "one", live_final: true }), message("second", { live_task_id: "two", live_final: true })];
  const timeline = liveTimeline(rows, [run("one"), run("two")]);
  expect(timeline.map(row => row.content)).toEqual(["first", "second"]);
  expect(new Set(timeline.map(row => row.metadata?.live_answer_id)).size).toBe(2);
});
test("persisted process survives an older run falling outside the run-list window", () => {
  const rows = [message("", { live_process: true, live_task_id: "old", run_id: "old-run", agent_process: ["tool"] }), message("final", { live_task_id: "old", live_final: true })];
  expect(liveTimeline(rows, []).map(row => row.content)).toEqual(["final"]);
  expect(liveTimeline(rows, [])[0].metadata?.agent_process).toEqual(["tool"]);
});
test("adjacent Live introduction, process and final form one answer without copying its introduction", () => {
  const intro = message("Starting now", { live_session_id: "live" });
  const process = message("", { live_session_id: "live", live_process: true, live_task_id: "one", run_id: "run-one", agent_process: { events: [] } });
  const final = message("Final\n```py\nprint(1)\n```", { live_session_id: "live", live_final: true, live_task_id: "one" });
  const rows = liveTimeline([intro, process, final], []);
  expect(rows).toHaveLength(1);
  expect(rows[0].metadata?.live_prefix).toEqual([intro]);
  expect(rows[0].content).toBe(final.content);
  expect(rows[0].metadata?.live_answer_id).toBe(liveTimeline([intro, process], [run("one")])[0].metadata?.live_answer_id);
});
test("an intervening user message keeps chronology and moves only the active task process forward", () => {
  const intro = message("Starting", { live_session_id: "live" });
  const user: ChatMessage = { role: "user", content: "question" };
  const reply = message("Working", { live_session_id: "live" });
  const process = message("", { live_session_id: "live", live_process: true, live_task_id: "one", run_id: "run-one" });
  const rows = liveTimeline([intro, user, reply, process], []);
  expect(rows.slice(0,2)).toEqual([intro,user]);
  expect(rows[2].metadata?.live_prefix).toEqual([reply]);
});
test("transcription updates replace a stable message instead of duplicating bubbles", () => {
  const before = message("I", { live_message_id: "utterance", live_partial: true });
  const after = message("I would like", { live_message_id: "utterance", live_partial: false });
  expect(mergeMessages([before], [after])).toEqual([after]);
});

test("modern execution segments keep final identity and stay before informational followups", () => {
  const process = message("", { live_schema: 2, live_session_id: "voice", live_message_id: "process-s1", live_process: true, live_task_id: "one", run_id: "r1", live_segment_id: "s1", live_run_status: "completed" });
  const final = message("Final", { live_schema: 2, live_session_id: "voice", live_message_id: "final-r1", live_final: true, live_task_id: "one", run_id: "r1", live_segment_id: "s1", live_delivery: "generated" });
  const later: ChatMessage = { role: "user", content: "Explain that answer", metadata: { live_message_id: "followup" } };
  const rows = liveTimeline([process, final, later], []);
  expect(rows.map(row => row.content)).toEqual(["Final", "Explain that answer"]);
  expect(rows[0].metadata?.live_message_id).toBe("final-r1");
  expect(rows[0].metadata?.live_delivery).toBe("generated");
  expect(rows[0].metadata?.live_answer_process).toBe(true);
});

test("a changed instruction and later continuation own separate process blocks", () => {
  const segment = (id: string, runId = "r1", until?: string) => message("", { live_schema: 2, live_session_id: "voice", live_process: true, live_task_id: "one", run_id: runId, live_segment_id: id, live_segment_until_message: until });
  const correction: ChatMessage = { role: "user", content: "Change destination", metadata: { live_message_id: "correction" } };
  const final = message("Final", { live_schema: 2, live_final: true, live_task_id: "one", run_id: "r1", live_segment_id: "s2" });
  const rows = liveTimeline([segment("s1", "r1", "correction"), correction, segment("s2"), final, segment("s3", "r2")], []);
  expect(rows.map(row => row.content)).toEqual(["", "Change destination", "Final", ""]);
  expect(rows.filter(row => row.metadata?.live_answer_id).map(row => row.metadata?.live_segment_id)).toEqual(["s1", "s2", "s3"]);
});
