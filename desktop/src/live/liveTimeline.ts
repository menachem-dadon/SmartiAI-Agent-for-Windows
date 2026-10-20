import type { ChatMessage, RunRecord } from "../chatTypes";

/** A task owns its process row; intervening conversation moves that row forward. */
export function liveTimeline(messages: ChatMessage[], runs: RunRecord[]): ChatMessage[] {
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
    const row: ChatMessage = { role: "assistant", content: "", message_id: `live-process:${taskId}`,
      metadata: { ...backend?.metadata, live_backend: false, live_process: true, live_task_id: taskId, run_id: run.id, agent_process: backend?.metadata?.agent_process } };
    insertions.set(position, [...(insertions.get(position) || []), row]);
  }
  return visible.flatMap((message, index) => [...(insertions.get(index) || []), message]).concat(insertions.get(visible.length) || []);
}
