import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { coreApi } from "./coreApi";
import { Alert, Button, EmptyState, Field, Icon, IconButton, LoadingState, Menu } from "./design-system";
import { readPanelSession, writePanelSession } from "./workbenchSession";

type TreeItem = { name: string; path: string; kind: "directory" | "file"; size?: number; children?: TreeItem[] };
type FilePreview = { name: string; path: string; kind: string; mime_type: string; size: number; text?: string; data_url?: string; converted_from?: string };
type Artifact = { name: string; path: string; size: number; modified_at: string };
const directoryOf = (path: string) => path.split("/").slice(0, -1).join("/");

function Tree({ items, selected, onOpen, onDirectory }: { items: TreeItem[]; selected: string; onOpen: (path: string) => void; onDirectory: (path: string) => void }) {
  return <ul className="file-tree">{items.map(item => <li key={item.path}>
    {item.kind === "directory" ? <details><summary><Icon name="chevron" size={16} /><Icon name="folder" size={18} /><span title={item.name}>{item.name}</span></summary>
      <Button variant="ghost" onClick={() => onDirectory(item.path)}>פתיחת {item.name}</Button>
      {item.children && <Tree items={item.children} selected={selected} onOpen={onOpen} onDirectory={onDirectory} />}</details>
      : <Button variant="ghost" aria-current={selected === item.path ? "true" : undefined} onClick={() => onOpen(item.path)}><Icon name="file" size={18} /><span title={item.name}>{item.name}</span><small>{item.size ? `${Math.ceil(item.size / 1024)} KB` : ""}</small></Button>}
  </li>)}</ul>;
}

function Preview({ preview, loading, selected, openExternal }: { preview: FilePreview | null; loading: boolean; selected: string; openExternal: () => void }) {
  if (loading) return <LoadingState label="טוען תצוגה מקדימה…" />;
  if (!preview) return <EmptyState icon="file" title={selected ? "התצוגה אינה זמינה" : "בחר קובץ לקריאה"} description={selected ? "אפשר לפתוח את הקובץ ביישום חיצוני או לנסות שוב." : "הקבצים ייפתחו כאן, לצד השיחה."} />;
  if (preview.kind === "markdown") return <article className="markdown-preview" dir="auto"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{preview.text || ""}</ReactMarkdown></article>;
  if (preview.kind === "text") return <pre dir="auto">{preview.text}</pre>;
  if (preview.kind === "image" && preview.data_url) return <img src={preview.data_url} alt={preview.name} />;
  if (preview.kind === "media" && preview.data_url) return preview.mime_type.startsWith("audio/") ? <audio src={preview.data_url} controls /> : <video src={preview.data_url} controls />;
  if (preview.kind === "pdf" && preview.data_url) return <iframe src={preview.data_url} title={preview.name} />;
  return <EmptyState icon="file" title={preview.name} description="אין תצוגה מקדימה בטוחה לסוג קובץ זה." action={<Button onClick={openExternal} icon="external">פתח באמצעות</Button>} />;
}

export function WorkbenchFiles({ id, artifacts = false }: { id: string; artifacts?: boolean }) {
  const saved = useRef(readPanelSession(id, { selected: "", directory: "", treeWidth: 240, treeVisible: true, scroll: 0 }));
  const [root, setRoot] = useState({ name: "Smarti", path: "" });
  const [draftRoot, setDraftRoot] = useState("");
  const [items, setItems] = useState<TreeItem[]>([]);
  const [outputs, setOutputs] = useState<Artifact[]>([]);
  const [directory, setDirectory] = useState(saved.current.directory);
  const [selected, setSelected] = useState(saved.current.selected);
  const [previewRevision, setPreviewRevision] = useState(0);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [error, setError] = useState("");
  const [listError, setListError] = useState(""), [previewError, setPreviewError] = useState("");
  const [loading, setLoading] = useState(false);
  const [listing, setListing] = useState(true);
  const [busy, setBusy] = useState(false);
  const actionGuard = useRef(false);
  const [treeWidth, setTreeWidth] = useState(saved.current.treeWidth);
  const [treeVisible, setTreeVisible] = useState(saved.current.treeVisible);
  const requestId = useRef(0), listRequest = useRef(0);
  const content = useRef<HTMLElement>(null), split = useRef<HTMLDivElement>(null);
  const state = useRef(saved.current);
  state.current = { selected, directory, treeWidth, treeVisible, scroll: state.current.scroll };
  const persist = () => writePanelSession(id, state.current);
  useEffect(persist, [selected, directory, treeWidth, treeVisible]);
  const load = useCallback(async (folder = "") => {
    const request = ++listRequest.current; setListing(true);
    try {
      if (artifacts) {
        const result = await coreApi<{ root?: typeof root; items: Artifact[] }>("GET", "/v2/workbench/artifacts");
        if (request !== listRequest.current) return;
        if (result.root) { setRoot(result.root); setDraftRoot(result.root.path); }
        setOutputs(result.items);
      } else {
        const data = await coreApi<{ root: typeof root; items: TreeItem[] }>("GET", `/v2/workbench/tree?depth=3${folder ? `&path=${encodeURIComponent(folder)}` : ""}`);
        if (request !== listRequest.current) return;
        setRoot(data.root); setDraftRoot(data.root.path); setItems(data.items);
      }
      setListError("");
    } catch (reason) { if (request === listRequest.current) setListError(String(reason)); }
    finally { if (request === listRequest.current) setListing(false); }
  }, [artifacts]);
  useEffect(() => { void load(directory); }, [load, directory]);
  useEffect(() => {
    const request = ++requestId.current; setPreview(null); setPreviewError("");
    if (!selected) { setLoading(false); return; }
    setLoading(true);
    void coreApi<FilePreview>("GET", `/v2/workbench/file?path=${encodeURIComponent(selected)}`)
      .then(value => { if (request === requestId.current) { setPreview(value); setPreviewError(""); } })
      .catch(reason => { if (request === requestId.current) setPreviewError(String(reason)); })
      .finally(() => { if (request === requestId.current) setLoading(false); });
    return () => { ++requestId.current; };
  }, [selected, previewRevision]);
  useEffect(() => { if (content.current && preview) content.current.scrollTop = state.current.scroll; }, [preview]);
  const action = async (callback: () => Promise<unknown>) => {
    if (actionGuard.current) return;
    actionGuard.current = true; setBusy(true);
    try { await callback(); setError(""); } catch (reason) { setError(String(reason)); }
    finally { actionGuard.current = false; setBusy(false); }
  };
  const setWorkspaceRoot = (path: string) => action(async () => {
    await coreApi("PATCH", "/v2/workbench/root", { path }, true);
    ++requestId.current; setSelected(""); setPreview(null); setDirectory(""); await load();
  });
  const chooseRoot = () => action(async () => {
    const path = await invoke<string | null>("pick_management_path", { kind: "directory" });
    if (!path) return;
    await coreApi("PATCH", "/v2/workbench/root", { path }, true);
    ++requestId.current; setSelected(""); setPreview(null); setDirectory(""); await load();
  });
  const openWith = () => action(() => invoke("desktop_open_with", { path: selected }));
  const openExternal = () => action(() => coreApi("POST", "/v2/workbench/open", { path: selected }, true));
  const fullPath = root.path ? `${root.path.replace(/[\\/]+$/, "")}${root.path.includes("\\") ? "\\" : "/"}${selected.replace(/\//g, root.path.includes("\\") ? "\\" : "/")}` : selected;
  const save = () => action(async () => {
    if (!preview) return;
    if (preview.text !== undefined) await invoke("save_text_file", { suggestedName: preview.name, contents: preview.text });
    else if (preview.data_url) {
      const bytes = Array.from(Uint8Array.from(atob(preview.data_url.split(",")[1]), c => c.charCodeAt(0)));
      await invoke("save_binary_file", { suggestedName: preview.converted_from ? `${preview.name}.pdf` : preview.name, bytes });
    }
  });
  const resizeTree = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const pick = (path: string) => { state.current.scroll = 0; if (path === selected) setPreviewRevision(value => value + 1); setSelected(path); if (!artifacts) setDirectory(directoryOf(path)); };
  return <div className={`${artifacts ? "artifacts" : "files"}-panel workbench-files`}>
    <header className="workbench-toolbar">
      {!artifacts && <><Field label="נתיב תיקיית העבודה" className="workbench-path" dir="ltr" value={draftRoot} onChange={e => setDraftRoot(e.target.value)} onKeyDown={e => { if (e.key === "Enter") void setWorkspaceRoot(draftRoot); }} />
        <Button icon="folder" disabled={busy} onClick={() => void chooseRoot()}>תיקייה</Button><Button disabled={busy} onClick={() => void setWorkspaceRoot(draftRoot)}>החל</Button></>}
      {artifacts && <strong>תוצרים</strong>}
      <IconButton icon="refresh" label="רענון" disabled={listing} onClick={() => { void load(directory); setPreviewRevision(value => value + 1); }} />
      <IconButton icon="panel" label={treeVisible ? "הסתרת רשימת הקבצים" : "הצגת רשימת הקבצים"} aria-pressed={treeVisible} onClick={() => setTreeVisible(!treeVisible)} />
      <Button icon="external" disabled={!selected || busy} onClick={() => void openWith()}>פתח באמצעות</Button>
      <Menu label="פעולות קובץ" items={[
        { id: "open", label: "פתיחה ביישום ברירת המחדל", icon: "external", disabled: !selected || busy, onSelect: () => void openExternal() },
        { id: "save", label: "שמירת עותק", icon: "download", disabled: busy || !preview || (preview.text === undefined && !preview.data_url), onSelect: () => void save() },
        { id: "copy", label: "העתקת נתיב מלא", icon: "copy", disabled: !selected, onSelect: () => void action(() => navigator.clipboard.writeText(fullPath)) },
      ]} />
    </header>
    {(error || listError || previewError) && <Alert title="פעולת הקובץ נכשלה" tone="danger">{[error, listError, previewError].filter(Boolean).join("\n")}</Alert>}
    <nav className="file-breadcrumbs" aria-label="מסלול תיקיות">
      <Button variant="ghost" onClick={() => setDirectory("")}>{root.name}</Button>
      {directory.split("/").filter(Boolean).map((part, index, parts) => <Button key={index} variant="ghost" onClick={() => setDirectory(parts.slice(0, index + 1).join("/"))}><Icon name="chevron" size={14} /><bdi>{part}</bdi></Button>)}
      {selected && <span title={fullPath}><bdi>{preview?.name || selected.split("/").slice(-1)[0]}</bdi></span>}
    </nav>
    <div ref={split} className={`${artifacts ? "artifacts" : "files"}-split`} data-tree={treeVisible} style={{ "--file-tree-width": `${treeWidth}px` } as CSSProperties}>
      <section ref={content} className="file-preview" aria-label={artifacts ? "תצוגת תוצר" : "תצוגת קובץ"} onScroll={e => { state.current.scroll = e.currentTarget.scrollTop; persist(); }}>
        <Preview preview={preview} loading={loading} selected={selected} openExternal={() => void openWith()} />
      </section>
      {treeVisible && <><div role="separator" tabIndex={0} aria-label="שינוי רוחב רשימת הקבצים" aria-orientation="vertical" aria-valuemin={120} aria-valuemax={400} aria-valuenow={treeWidth} className="file-tree-resize" onPointerDown={resizeTree}
        onPointerMove={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) setTreeWidth(Math.max(120, Math.min(400, (split.current?.getBoundingClientRect().right || 0) - e.clientX))); }}
        onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} onKeyDown={e => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) { e.preventDefault(); setTreeWidth(e.key === "Home" ? 120 : e.key === "End" ? 400 : Math.max(120, Math.min(400, treeWidth + (e.key === "ArrowLeft" ? 24 : -24)))); } }} />
        <aside aria-label={artifacts ? "רשימת תוצרים" : "רשימת קבצים"}>
          {listing ? <LoadingState label="טוען קבצים…" /> : artifacts ? outputs.map(item => <Button key={item.path} variant="ghost" className="artifact-item" aria-current={selected === item.path ? "true" : undefined} onClick={() => pick(item.path)}><Icon name="file" /><span><b title={item.path}><bdi>{item.name}</bdi></b><small><bdi>{item.path}</bdi></small><small>{new Date(item.modified_at).toLocaleString("he-IL")} · {Math.ceil(item.size / 1024)} KB</small></span></Button>)
            : <Tree items={items} selected={selected} onOpen={pick} onDirectory={setDirectory} />}
          {!listing && !(artifacts ? outputs.length : items.length) && <EmptyState icon="folder" title={artifacts ? "עדיין אין תוצרים" : "התיקייה ריקה"} description="קבצים חדשים יופיעו לאחר רענון." />}
        </aside></>}
    </div>
  </div>;
}
