import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { closeBrowserWorkspace } from "./browserWorkspaceLifecycle";
import { BrowserPanel, type BrowserActivity } from "./BrowserPanel";
import { CanvasPanel } from "./CanvasPanel";
import { WorkbenchFiles } from "./WorkbenchFiles";
import { closeWorkbenchTerminal, WorkbenchTerminal } from "./WorkbenchTerminal";
import { closeWorkbenchTab, nextWorkbenchTabTitle, openWorkbenchTab, reorderWorkbenchTabs, workbenchLabels, type WorkbenchSnapshot, type WorkbenchTab } from "./workspaceState";
import { Button, Icon, IconButton, Menu, Alert, type IconName } from "./design-system";
import { useWorkbenchTabDrag } from "./useWorkbenchTabDrag";
import { forgetPanelSession } from "./workbenchSession";

const launcherKinds: WorkbenchTab[] = ["browser", "files", "terminal", "artifacts"];
const icons: Record<WorkbenchTab, IconName> = { browser: "browser", files: "folder", terminal: "terminal", canvas: "canvas", artifacts: "file" };
export type WorkbenchHandle = { activateTab: (id: string) => void; openCanvas: (sessionId: string, canvasId: string) => void };

export function WorkbenchSurface({ ref, initial, visible, motionRevision, restored, onStateChange, onBrowserActivity, onClose, showCloseControl = true, sessionId, onCanvasAction, owner = "", expanded = false, onToggleExpanded }: {
  ref?: Ref<WorkbenchHandle>; initial: WorkbenchTab | null; visible: boolean; motionRevision?: boolean | string;
  restored?: WorkbenchSnapshot | null; onStateChange?: (state: WorkbenchSnapshot) => void;
  onBrowserActivity?: (activity: BrowserActivity | null) => void; onClose: () => void; closeIcon?: string; showCloseControl?: boolean;
  sessionId: string; onCanvasAction: (text: string, sessionId: string) => void | Promise<void>;
  owner?: string; expanded?: boolean; onToggleExpanded?: () => void;
}) {
  const counter = useRef(Math.max(0, ...(restored?.tabs || []).map(tab => Number(tab.id.match(/-(\d+)$/)?.[1] || 0))));
  const restoredApplied = useRef(Boolean(restored));
  const [snapshot, setSnapshot] = useState<WorkbenchSnapshot>(() => restored || { tabs: [], active: "" });
  const { tabs, active } = snapshot;
  const [error, setError] = useState("");
  const [overlay, setOverlay] = useState(false);
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const surface = useRef<HTMLDivElement>(null);
  const closing = useRef(new Set<string>());
  const [closingIds, setClosingIds] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!restored || restoredApplied.current) return;
    restoredApplied.current = true; setSnapshot(restored);
    counter.current = Math.max(counter.current, ...restored.tabs.map(tab => Number(tab.id.match(/-(\d+)$/)?.[1] || 0)));
  }, [restored]);
  const add = (kind: WorkbenchTab, forceNew = false, target?: { sessionId: string; targetId: string }) => {
    const id = `${owner ? `${owner}:` : ""}${kind}-${++counter.current}`;
    setSnapshot(current => openWorkbenchTab(current, { id, kind, title: nextWorkbenchTabTitle(current.tabs, kind, workbenchLabels[kind]), ...(kind === "canvas" ? target || { sessionId } : {}) }, forceNew));
  };
  useEffect(() => { if (initial) add(initial); }, [initial]);
  useEffect(() => { onStateChange?.(snapshot); }, [snapshot, onStateChange]);
  const focusTab = (id: string) => requestAnimationFrame(() => buttons.current.get(id)?.focus());
  const close = async (id: string) => {
    if (closing.current.has(id)) return;
    const tab = tabs.find(item => item.id === id); if (!tab) return;
    closing.current.add(id);
    setClosingIds(new Set(closing.current));
    try {
      if (tab.kind === "browser") await closeBrowserWorkspace(id);
      if (tab.kind === "terminal") await closeWorkbenchTerminal(id);
      forgetPanelSession(id);
      setSnapshot(current => closeWorkbenchTab(current, id)); setError("");
      requestAnimationFrame(() => surface.current?.querySelector<HTMLButtonElement>('[role="tab"][aria-selected="true"], .workbench-empty button')?.focus());
    } catch (reason) { setError(`לא ניתן לסגור את הלשונית: ${String(reason)}`); }
    finally { closing.current.delete(id); setClosingIds(new Set(closing.current)); }
  };
  const reorder = (source: string, target: string) => setSnapshot(current => reorderWorkbenchTabs(current, source, target));
  const drag = useWorkbenchTabDrag(visible, reorder);
  const current = tabs.find(tab => tab.id === active);
  useImperativeHandle(ref, () => ({
    activateTab: id => setSnapshot(current => current.tabs.some(tab => tab.id === id) ? { ...current, active: id } : current),
    openCanvas: (source, target) => add("canvas", false, { sessionId: source, targetId: target }),
  }), [owner, sessionId]);
  const reportBrowserActivity = useCallback((activity: BrowserActivity | null) => {
    onBrowserActivity?.(current?.kind === "browser" && activity?.workspaceId === current.id ? activity : null);
  }, [current?.id, current?.kind, onBrowserActivity]);
  useEffect(() => { if (current?.kind !== "browser") onBrowserActivity?.(null); return () => onBrowserActivity?.(null); }, [current?.id, current?.kind, onBrowserActivity]);
  useEffect(() => {
    if (visible && showCloseControl) surface.current?.querySelector<HTMLButtonElement>(".workbench-return")?.focus();
  }, [visible, showCloseControl]);
  return <div className="workbench-surface" ref={surface}>
    <header className="workbench-head" dir="ltr">
      <div className={`workbench-tabs${drag.preview ? " is-dragging" : ""}`} role="tablist" aria-label="לשוניות סביבת העבודה" ref={drag.strip}
        onPointerDownCapture={drag.prepareClick} onPointerMove={drag.move} onPointerUp={drag.end} onPointerCancel={drag.cancel} onLostPointerCapture={drag.cancel} onClickCapture={drag.click}>
        {tabs.map((tab, index) => <div key={tab.id} className={`workbench-tab${active === tab.id ? " is-active" : ""}`}>
          <IconButton icon="close" tooltip={false} className="workbench-tab-close" label={`סגירת ${tab.title}`} onPointerDown={event => event.stopPropagation()} onClick={() => void close(tab.id)} />
          <Button role="tab" variant="ghost" id={`workbench-tab-${tab.id}`} ref={node => { if (node) buttons.current.set(tab.id, node); else buttons.current.delete(tab.id); }} data-tab-id={tab.id}
            aria-controls={`workbench-panel-${tab.id}`} aria-selected={tab.id === active} tabIndex={tab.id === active ? 0 : -1}
            className={drag.preview?.id === tab.id ? "is-dragging" : undefined} data-drop-side={drag.preview?.target === tab.id && drag.preview.id !== tab.id ? drag.preview.side : undefined}
            style={drag.preview?.id === tab.id ? { transform: `translateX(${drag.preview.offset}px)` } : undefined}
            onClick={() => setSnapshot(current => ({ ...current, active: tab.id }))} onPointerDown={event => drag.begin(event, tab.id)} onDragStart={event => event.preventDefault()}
            onKeyDown={event => {
              if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
                event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
                if (event.ctrlKey && ["ArrowRight", "ArrowLeft"].includes(event.key)) reorder(tab.id, tabs[next].id);
                else setSnapshot(current => ({ ...current, active: tabs[next].id }));
                focusTab(event.ctrlKey ? tab.id : tabs[next].id);
              }
              if (event.key === "Delete") { event.preventDefault(); void close(tab.id); }
            }}><span dir="auto" title={tab.title}>{tab.title}</span><Icon name={icons[tab.kind]} size={18} /></Button>
        </div>)}
      </div>
      <div className="workbench-add"><Menu label="פתיחת לשונית" icon="plus" onOpenChange={setOverlay} items={launcherKinds.map(kind => ({ id: kind, label: workbenchLabels[kind], icon: icons[kind], onSelect: () => add(kind, true) }))} /></div>
      {onToggleExpanded && <IconButton icon={expanded ? "shrink" : "expand"} label={expanded ? "חזרה לעבודה משולבת" : "הרחבת סביבת העבודה"} onClick={onToggleExpanded} />}
      {showCloseControl && <IconButton className="workbench-return" icon="panel" label="סגירת סביבת העבודה" onClick={onClose} />}
    </header>
    {error && <Alert title="פעולת הלשונית נכשלה" tone="danger">{error}</Alert>}
    <div className="workbench-body">
      {!current && <div className="workbench-empty" role="group" aria-label="מה תרצה לפתוח?"><h2>סביבת העבודה</h2><p>פתח כלי לצד השיחה</p>{launcherKinds.map(kind => <Button variant="ghost" icon={icons[kind]} key={kind} onClick={() => add(kind, true)}>{workbenchLabels[kind]}</Button>)}</div>}
      {tabs.some(tab => tab.kind === "browser") && <section className="workbench-panel" role="tabpanel" id={current?.kind === "browser" ? `workbench-panel-${current.id}` : undefined} aria-labelledby={current?.kind === "browser" ? `workbench-tab-${current.id}` : undefined} hidden={current?.kind !== "browser"} aria-label="דפדפן">
        <BrowserPanel workspaceTabId={current?.kind === "browser" ? current.id : ""} visible={visible && current?.kind === "browser" && !closingIds.has(current.id)} obscured={overlay} geometryRevision={motionRevision} onActivity={reportBrowserActivity} />
      </section>}
      {tabs.filter(tab => tab.kind !== "browser").map(tab => <section className="workbench-panel" role="tabpanel" id={`workbench-panel-${tab.id}`} aria-labelledby={`workbench-tab-${tab.id}`} hidden={tab.id !== active} key={tab.id} aria-label={tab.title}>
        {tab.kind === "files" && <WorkbenchFiles id={tab.id} />}
        {tab.kind === "terminal" && <WorkbenchTerminal tabId={tab.id} />}
        {tab.kind === "artifacts" && <WorkbenchFiles id={tab.id} artifacts />}
        {tab.kind === "canvas" && <CanvasPanel sessionId={tab.sessionId || sessionId} canvasId={tab.targetId} onAction={text => onCanvasAction(text, tab.sessionId || sessionId)} />}
      </section>)}
    </div>
  </div>;
}
