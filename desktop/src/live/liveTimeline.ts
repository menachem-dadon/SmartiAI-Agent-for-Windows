import type { ChatMessage, RunRecord } from "../chatTypes";

/** A task owns its process row; intervening conversation moves that row forward. */
function legacyTimeline(messages: ChatMessage[], runs: RunRecord[]): ChatMessage[] {
  const visible = messages.filter(message => !message.metadata?.live_backend && !message.metadata?.live_process);
  const taskMap = new Map(runs.filter(run => run.metadata?.live_task_id).map(run => [String(run.metadata!.live_task_id), run]));
  for (const message of messages.filter(message => message.metadata?.live_process)) {
    const id = String(message.metadata!.live_task_id);
    if (!taskMap.has(id)) taskMap.set(id, { id: String(message.metadata!.run_id), session_id: "", status: String(message.metadata!.live_run_status || "completed"), user_text: "", metadata: { live_task_id: id } });
  }
  const tasks = [...taskMap.values()];
  const insertions = new Map<number, ChatMessage[]>();
  for (const run of tasks) {
    const taskId = String(run.metadata!.live_task_id);
    const final = visible.findIndex(message => message.metadata?.live_task_id === taskId && message.metadata?.live_final);
    // Once final, a later task must not drag an earlier process below its answer.
    const position = final < 0 ? visible.length : final;
    const backend = messages.find(message => message.metadata?.live_process && message.metadata?.live_task_id === taskId) || messages.find(message => message.role === "assistant" && message.metadata?.run_id === run.id);
    const process = { live_answer_id: `live-answer:${taskId}`, run_id: run.id, live_run_status: run.status, agent_process: backend?.metadata?.agent_process,
      live_session_id: backend?.metadata?.live_session_id || run.metadata?.live_session_id };
    if (final >= 0) {
      visible[final] = { ...visible[final], metadata: { ...visible[final].metadata, ...process, live_answer_process: true } };
      continue;
    }
    const row: ChatMessage = { role: "assistant", content: "", message_id: `live-process:${taskId}`,
      metadata: { ...backend?.metadata, ...process, live_backend: false, live_process: true, live_task_id: taskId } };
    insertions.set(position, [...(insertions.get(position) || []), row]);
  }
  const ordered = visible.flatMap((message, index) => [...(insertions.get(index) || []), message]).concat(insertions.get(visible.length) || []);
  const result: ChatMessage[] = [];
  for (const message of ordered) {
    if (message.metadata?.live_answer_id) {
      const prefix: ChatMessage[] = [];
      let previous = result[result.length - 1];
      while (previous?.role === "assistant" && previous.metadata?.live_session_id &&
          previous.metadata.live_session_id === message.metadata.live_session_id &&
          !previous.metadata.live_final && !previous.metadata.live_answer_id &&
          (!previous.metadata.live_task_id || previous.metadata.live_task_id === message.metadata.live_task_id)) {
        prefix.unshift(result.pop()!); previous = result[result.length - 1];
      }
      result.push({ ...message, metadata: { ...message.metadata, live_prefix: prefix } });
    } else result.push(message);
  }
  return result;
}

/** Explicit execution segments own their anchors. Spoken captions can replace
 * the reserved result's content without moving its process past later turns. */
export function liveTimeline(messages: ChatMessage[], runs: RunRecord[]): ChatMessage[] {
  const modernRuns = new Set(runs.filter(run => run.metadata?.live_schema === 2).map(run => run.id));
  const segments = messages.filter(message => message.metadata?.live_schema === 2 && message.metadata.live_process);
  for (const segment of segments) modernRuns.add(String(segment.metadata?.run_id));
  if (!modernRuns.size) return legacyTimeline(messages, runs);
  const result = legacyTimeline(messages.filter(message => !segments.includes(message)), runs.filter(run => !modernRuns.has(run.id)));
  const insertions = new Map<number, ChatMessage[]>();
  for (const segment of segments) {
    const meta = segment.metadata!;
    const final = result.findIndex(row => row.metadata?.live_final && row.metadata.run_id === meta.run_id && row.metadata.live_segment_id === meta.live_segment_id);
    const process = { live_schema: 2, live_task_id: meta.live_task_id, run_id: meta.run_id,
      live_segment_id: meta.live_segment_id, live_segment_after: meta.live_segment_after,
      live_segment_before: meta.live_segment_before, live_run_status: meta.live_run_status,
      live_session_id: meta.live_session_id, agent_process: meta.agent_process,
      live_answer_id: `live-answer:${meta.live_segment_id}` };
    if (final >= 0) {
      result[final] = { ...result[final], metadata: { ...result[final].metadata, ...process, live_process: false, live_answer_process: true } };
    } else {
      const anchor = meta.live_segment_until_message;
      let position = anchor ? result.findIndex(row => row.metadata?.live_message_id === anchor || row.message_id === anchor) : result.length;
      if (position < 0) position = 0; // An older anchor may be on an unloaded history page.
      insertions.set(position, [...(insertions.get(position) || []), { ...segment, metadata: { ...meta, ...process } }]);
    }
  }
  const ordered = result.flatMap((row, index) => [...(insertions.get(index) || []), row]).concat(insertions.get(result.length) || []);
  const combined: ChatMessage[] = [];
  for (const row of ordered) {
    const prefix: ChatMessage[] = [];
    if (row.metadata?.live_schema === 2 && row.metadata.live_answer_id) {
      let previous = combined[combined.length - 1];
      while (previous?.role === "assistant" && previous.metadata?.live_session_id === row.metadata.live_session_id &&
          !previous.metadata?.live_final && !previous.metadata?.live_answer_id && previous.metadata?.live_session_id) {
        prefix.unshift(combined.pop()!); previous = combined[combined.length - 1];
      }
    }
    combined.push(prefix.length ? { ...row, metadata: { ...row.metadata, live_prefix: prefix } } : row);
  }
  return combined;
}
