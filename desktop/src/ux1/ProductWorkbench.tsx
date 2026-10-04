import { useEffect, useRef, useState, type ReactNode, type Ref } from "react";
import { invoke } from "@tauri-apps/api/core";
import { BrowserPanel } from "../BrowserPanel";
import { CanvasPanel } from "../CanvasPanel";
import { workbenchLabels, type WorkbenchTab } from "../workspaceState";
import { ArtifactsPanel, FilesPanel, TerminalPanel } from "./ProductPanels";
import { Button } from "./Button";
import { Icon, type IconName } from "./Icon";

export type WorkspaceResource = { id: string; title: string; url?: string };
export type WorkspaceRequest = { kind: WorkbenchTab | null; revision: number; resource?: WorkspaceResource };
type Tab = { id: number; kind: WorkbenchTab; resource?: WorkspaceResource; sessionId: string };
const launchKinds: WorkbenchTab[] = ["browser", "files", "terminal", "artifacts"];
const workbenchIcons: Record<WorkbenchTab, IconName> = { browser: "browser", files: "folder", terminal: "terminal", canvas: "canvas", artifacts: "file" };

// Each browser target is prepared through the isolated bridge, with a stable
// workspace owner and mounted source panel retained while its tab is hidden.
function BrowserResource({ tab, visible, revision }: { tab: Tab; visible: boolean; revision: number }) {
  const [ready, setReady] = useState(!tab.resource?.url);
  const [error, setError] = useState("");
  const [activity, setActivity] = useState("");
  useEffect(() => {
    let alive = true;
    if (tab.resource?.url) void invoke("browser_open", { profile: "persistent", url: tab.resource.url, workspaceId: `demo-workbench-${tab.id}` }).then(() => { if (alive) setReady(true); }).catch(reason => { if (alive) setError(String(reason)); });
    return () => { alive = false; };
  }, [tab.id, tab.resource?.url]);
  return <>{error && <p role="alert">{error}</p>}{ready && <BrowserPanel workspaceTabId={`demo-workbench-${tab.id}`} visible={visible} geometryRevision={revision.toString()} onActivity={value => setActivity(value?.url || "")} />}<div className="ux-browser-demo-page" aria-hidden="true"><h2>מקום להיפגש.<br />מרחב ליצור.</h2><p>{tab.resource?.title || "המרכז הקהילתי"}</p><bdi>{activity}</bdi></div></>;
}

export function ProductWorkbench({ request, children, visible, expanded, toggleExpanded, expansionRef, sessionId, onCanvasAction }: {
  request: WorkspaceRequest; children: (showList: () => void) => ReactNode;
  visible: boolean; expanded: boolean; toggleExpanded: () => void; expansionRef: Ref<HTMLButtonElement>;
  sessionId: string; onCanvasAction: (text: string) => void;
}) {
  const [tabs, setTabs] = useState<Tab[]>(request.kind ? [{ id: 1, kind: request.kind, resource: request.resource, sessionId }] : []);
  const [active, setActive] = useState(request.kind ? 1 : 0);
  const [menu, setMenu] = useState(false);
  const [documentModes, setDocumentModes] = useState<Record<number, boolean>>({});
  const nextId = useRef(2);
  const dragId = useRef<number | null>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const addRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    setMenu(false);
    if (!request.kind) return;
    const kind = request.kind;
    const tab = tabs.find(t => t.kind === kind && t.resource?.id === request.resource?.id && (kind !== "canvas" || t.sessionId === sessionId));
    if (tab) setActive(tab.id);
    else { const id = nextId.current++; setTabs(prev => [...prev, { id, kind, resource: request.resource, sessionId }]); setActive(id); }
  }, [request.revision]);
  useEffect(() => {
    if (!menu) return;
    menuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const dismiss = (event: PointerEvent) => { if (!barRef.current?.contains(event.target as Node)) setMenu(false); };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [menu]);
  const current = tabs.find(t => t.id === active);
  function add(kind: WorkbenchTab) { const id = nextId.current++; setTabs(prev => [...prev, { id, kind, sessionId }]); setActive(id); setMenu(false); }
  function closeTab(id: number) {
    const index = tabs.findIndex(t => t.id === id), closing = tabs[index];
    const remaining = tabs.filter(t => t.id !== id);
    setTabs(remaining);
    if (active === id) {
      const next = remaining[Math.max(0, index - 1)]?.id ?? 0;
      setActive(next);
      requestAnimationFrame(() => (next ? barRef.current?.querySelector<HTMLButtonElement>(`[data-tab-id="${next}"]`) : addRef.current)?.focus());
    }
    if (closing?.kind === "browser") void invoke("browser_close_workspace", { workspaceId: `demo-workbench-${id}` });
    setMenu(false);
  }
  return <div className="ux-product-workbench">
    <div className="ux-workbench-bar" ref={barRef}>
      <div className="ux-workbench-tabs" role="tablist" aria-label="לשוניות סביבת העבודה">{tabs.map(t => <div key={t.id} className={t.id === active ? "is-active" : ""} draggable onDragStart={() => { dragId.current = t.id; }} onDragOver={event => event.preventDefault()} onDrop={event => {
        event.preventDefault(); const from = tabs.find(x => x.id === dragId.current);
        if (from && from.id !== t.id) { const next = tabs.filter(x => x.id !== from.id); next.splice(next.findIndex(x => x.id === t.id), 0, from); setTabs(next); }
      }}><button type="button" role="tab" data-tab-id={t.id} aria-selected={t.id === active} title={t.resource?.title} onClick={() => { setActive(t.id); setMenu(false); }} onKeyDown={event => {
        if (event.key === "Delete") { event.preventDefault(); closeTab(t.id); return; }
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault(); const index = tabs.findIndex(tab => tab.id === t.id);
        const target = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowLeft" ? 1 : -1) + tabs.length) % tabs.length;
        setActive(tabs[target].id); barRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[target]?.focus();
      }}><Icon name={workbenchIcons[t.kind]} /><span>{t.resource?.title || workbenchLabels[t.kind]}</span></button><Button icon="close" className="ux-tab-close" label={`סגירת לשונית ${t.resource?.title || workbenchLabels[t.kind]}`} onClick={() => closeTab(t.id)} /></div>)}</div>
      <div className="ux-workbench-actions"><Button ref={addRef} icon="plus" label="הוספת לשונית סביבת עבודה" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(!menu)} /><Button ref={expansionRef} icon={expanded ? "shrink" : "expand"} label={expanded ? "כיווץ סביבת העבודה" : "הרחבת סביבת העבודה"} aria-pressed={expanded} onClick={() => { toggleExpanded(); setMenu(false); }} /></div>
      {menu && <div className="ux-workbench-popover" ref={menuRef} role="menu" aria-label="הוספת לשונית" onKeyDown={event => {
        if (event.key === "Escape") { event.stopPropagation(); setMenu(false); addRef.current?.focus(); }
        const items = Array.from(menuRef.current!.querySelectorAll<HTMLButtonElement>("button"));
        if (["ArrowDown", "ArrowUp", "Home", "End", "Tab"].includes(event.key)) {
          event.preventDefault(); const index = items.indexOf(document.activeElement as HTMLButtonElement);
          const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" || (event.key === "Tab" && event.shiftKey) ? -1 : 1) + items.length) % items.length;
          items[next]?.focus();
        }
      }}>{launchKinds.map(kind => <Button role="menuitem" icon={workbenchIcons[kind]} key={kind} onClick={() => add(kind)}>{workbenchLabels[kind]}</Button>)}</div>}
    </div>
    {!current && <div className="ux-workbench-launcher"><span className="ux-eyebrow">סביבת העבודה</span><h2>בחר במה לעבוד</h2><p>פתח כלי לצד השיחה. אפשר לשלב כמה לשוניות ולעבור ביניהן.</p><div className="ux-workbench-launch-grid">{launchKinds.map(kind => <Button icon={workbenchIcons[kind]} key={kind} onClick={() => add(kind)}><span><strong>{workbenchLabels[kind]}</strong><small>{{ browser: "כתובת, ניווט וכלי דפדפן", files: "עיון בקבצים ותצוגה מקדימה", terminal: "פקודות ופלט", artifacts: "מסמכים וקבצים שנוצרו", canvas: "" }[kind]}</small></span><Icon name="chevron" size={16} /></Button>)}</div></div>}
    {tabs.map(t => <div className={`ux-workbench-content ${t.kind === "browser" ? "ux-browser-host" : ""}`} role="tabpanel" key={t.id} hidden={active !== t.id}>{t.kind === "files" ? <FilesPanel /> : t.kind === "canvas" ? <CanvasPanel sessionId={t.sessionId} onAction={onCanvasAction} /> : t.kind === "terminal" ? <TerminalPanel /> : t.kind === "browser" ? <BrowserResource tab={t} visible={visible && active === t.id} revision={request.revision} /> : <><div hidden={documentModes[t.id] ?? !!t.resource}><ArtifactsPanel onOpenSample={() => setDocumentModes(prev => ({ ...prev, [t.id]: true }))} /></div>{(documentModes[t.id] ?? !!t.resource) && active === t.id && <div className="ux-document-pane">{children(() => setDocumentModes(prev => ({ ...prev, [t.id]: false })))}</div>}</>}</div>)}
  </div>;
}
