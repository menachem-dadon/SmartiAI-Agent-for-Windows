import { useEffect, useRef, useState } from "react";
import { coreApi, CoreApiError, encodePath } from "./coreApi";
import { Alert, Field, IconButton } from "./design-system";
import { forgetPanelSession, readPanelSession, writePanelSession } from "./workbenchSession";

type Terminal = { id: string; running: boolean; output?: string; cwd?: string };
type Recovery = { terminalId: string; output: string; command: string; history: string[]; cwd: string; scroll: number };
const pending = new Map<string, Promise<Terminal>>();
export async function closeWorkbenchTerminal(tabId: string) {
  const created = await pending.get(tabId);
  const id = created?.id || readPanelSession<Recovery | null>(tabId, null)?.terminalId;
  if (id) await coreApi("DELETE", `/v2/workbench/terminals/${encodePath(id)}`, {}, true);
  pending.delete(tabId); forgetPanelSession(tabId);
}

export function WorkbenchTerminal({ tabId }: { tabId: string }) {
  const recovery = useRef(readPanelSession<Recovery>(tabId, { terminalId: "", output: "", command: "", history: [], cwd: "", scroll: 0 }));
  const [terminalId, setTerminalId] = useState(recovery.current.terminalId);
  const [output, setOutput] = useState(recovery.current.output);
  const [command, setCommand] = useState(recovery.current.command);
  const [history, setHistory] = useState(recovery.current.history);
  const [cwd, setCwd] = useState(recovery.current.cwd);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const guard = useRef(false), follow = useRef(true), historyIndex = useRef(-1);
  const outputRef = useRef<HTMLPreElement>(null);
  recovery.current = { terminalId, output, command, history, cwd, scroll: recovery.current.scroll };
  const persist = () => writePanelSession(tabId, recovery.current);
  useEffect(persist, [terminalId, output, command, history, cwd]);
  const receive = (item: Terminal) => {
    setTerminalId(item.id); setRunning(item.running !== false); if (item.cwd) setCwd(item.cwd);
    if (item.output) setOutput(current => (current + item.output).slice(-256_000));
    recovery.current.terminalId = item.id; persist();
  };
  useEffect(() => {
    let alive = true;
    const attach = async () => {
      if (recovery.current.terminalId) return coreApi<Terminal>("GET", `/v2/workbench/terminals/${encodePath(recovery.current.terminalId)}`);
      if (!pending.has(tabId)) pending.set(tabId, coreApi<Terminal>("POST", "/v2/workbench/terminals", {}, true).then(item => {
        const cached = readPanelSession<Recovery>(tabId, recovery.current);
        writePanelSession(tabId, { ...cached, terminalId: item.id, cwd: item.cwd || cached.cwd, output: (cached.output + (item.output || "")).slice(-256_000) });
        return item;
      }));
      try { return await pending.get(tabId)!; } finally { pending.delete(tabId); }
    };
    void attach().then(item => { if (alive) receive(item); }).catch(reason => {
      if (alive) {
        if (reason instanceof CoreApiError && (reason.status === 404 || reason.message === "terminal_session_not_found")) setTerminalId("");
        setError(String(reason));
      }
    });
    return () => { alive = false; };
  }, [tabId]);
  useEffect(() => {
    if (!terminalId || !running) return;
    let disposed = false, timer = 0;
    const poll = async () => {
      try {
        const item = await coreApi<Terminal>("GET", `/v2/workbench/terminals/${encodePath(terminalId)}`);
        if (!disposed) receive(item);
      } catch (reason) { if (!disposed) { setError(String(reason)); setRunning(false); } }
      if (!disposed) timer = window.setTimeout(poll, 350);
    };
    timer = window.setTimeout(poll, 350);
    return () => { disposed = true; clearTimeout(timer); };
  }, [terminalId, running]);
  useEffect(() => { if (outputRef.current) outputRef.current.scrollTop = follow.current ? outputRef.current.scrollHeight : recovery.current.scroll; }, [output]);
  const action = async (callback: () => Promise<void>) => {
    if (guard.current) return; guard.current = true; setBusy(true);
    try { await callback(); setError(""); } catch (reason) { setError(String(reason)); }
    finally { guard.current = false; setBusy(false); }
  };
  const send = () => action(async () => {
    if (!terminalId || !running || !command.trim()) return;
    const value = command;
    const item = await coreApi<Terminal>("POST", `/v2/workbench/terminals/${encodePath(terminalId)}`, { action: "write", text: value }, true);
    setOutput(current => `${current}PS › ${value}\n`); setCommand(""); setHistory(current => [...current, value].slice(-100)); historyIndex.current = -1; receive(item);
  });
  const restart = () => action(async () => {
    const item = terminalId ? await coreApi<Terminal>("POST", `/v2/workbench/terminals/${encodePath(terminalId)}`, { action: "restart" }, true)
      : await coreApi<Terminal>("POST", "/v2/workbench/terminals", {}, true);
    setOutput(""); receive(item);
  });
  const stop = () => action(async () => { await closeWorkbenchTerminal(tabId); setTerminalId(""); setRunning(false); });
  return <div className="terminal-panel" dir="ltr">
    <header className="workbench-toolbar" dir="rtl"><span>{running ? "פועל" : error ? "המסוף אינו זמין" : "הסתיים"}</span><bdi title={cwd}>{cwd}</bdi>
      <IconButton icon="stop" tooltip={false} label="עצירת המסוף" disabled={!running || busy} onClick={() => void stop()} />
      <IconButton icon="refresh" label="הפעל מחדש" disabled={busy} onClick={() => void restart()} />
      <IconButton icon="trash" label="ניקוי התצוגה" onClick={() => setOutput("")} /></header>
    {error && <Alert title="פעולת המסוף נכשלה" tone="danger">{error}</Alert>}
    <pre ref={outputRef} tabIndex={0} aria-label="פלט המסוף" onScroll={e => { const node = e.currentTarget; follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 32; recovery.current.scroll = node.scrollTop; persist(); }}>{output}</pre>
    <form onSubmit={e => { e.preventDefault(); void send(); }}><b>PS ›</b><Field label="פקודת PowerShell" dir="ltr" value={command} disabled={!running || busy} onChange={e => setCommand(e.target.value)} onKeyDown={e => {
      if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); const index = historyIndex.current < 0 ? history.length : historyIndex.current; historyIndex.current = Math.max(0, Math.min(history.length, index + (e.key === "ArrowUp" ? -1 : 1))); setCommand(history[historyIndex.current] || ""); }
      if (e.ctrlKey && e.key.toLowerCase() === "l") { e.preventDefault(); setOutput(""); }
    }} /><IconButton icon="send" label="הרצת פקודה" disabled={!running || !command.trim() || busy} onClick={() => void send()} /></form>
  </div>;
}
