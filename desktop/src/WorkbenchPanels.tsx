import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BrowserPanel, forgetBrowserWorkspaceSession, type BrowserActivity } from "./BrowserPanel";
import { CanvasPanel } from "./CanvasPanel";
import { coreApi, encodePath } from "./coreApi";
import {
  closeWorkbenchTab,
  nextWorkbenchTabTitle,
  openWorkbenchTab,
  reorderWorkbenchTabs,
  workbenchLabels,
  type WorkbenchSnapshot,
  type WorkbenchTab,
  type WorkbenchTabRecord,
} from "./workspaceState";
import { useDismissiblePopup } from "./popupDismissal";
import { LegacyIcon } from "./legacyAssets";
import { IconButton } from "./ui";
import { useWorkbenchTabDrag } from "./useWorkbenchTabDrag";

type TreeItem = {
  name: string;
  path: string;
  kind: "directory" | "file";
  size?: number;
  children?: TreeItem[];
};
type FilePreview = {
  name: string;
  path: string;
  kind: string;
  mime_type: string;
  size: number;
  text?: string;
  data_url?: string;
};
type Tab = WorkbenchTabRecord;
const maxTabSequence = (tabs: Tab[]) => Math.max(0, ...tabs.map((tab) => {
  const match = tab.id.match(/-(\d+)$/);
  return match ? Number(match[1]) : 0;
}));
const labels = workbenchLabels;
const icons: Record<WorkbenchTab, string> = {
  browser: "◎",
  files: "▤",
  terminal: ">_",
  canvas: "◇",
  artifacts: "▱",
};
const launcherKinds: WorkbenchTab[] = ["files", "browser", "terminal", "canvas", "artifacts"];
const launcherIconPaths: Record<WorkbenchTab, string> = {
  files: "M3 7V5a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z M3 9h18",
  browser: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z M3 12h18 M12 3c-5 5-5 13 0 18 5-5 5-13 0-18Z",
  terminal: "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z M7 8l4 4-4 4 M14 16h3",
  canvas: "M4 3h16v14H4V3Z M12 17v4 M8 21h8 M7 13l4-4 3 3 3-5",
  artifacts: "M5 3h9l5 5v13H5V3Z M14 3v5h5 M8 12h8 M8 16h6",
};

function Tree({
  items,
  onOpen,
}: {
  items: TreeItem[];
  onOpen: (path: string) => void;
}) {
  return (
    <ul className="file-tree">
      {items.map((item) => (
        <li key={item.path}>
          {item.kind === "directory" ? (
            <details>
              <summary>▸ {item.name}</summary>
              {item.children && <Tree items={item.children} onOpen={onOpen} />}
            </details>
          ) : (
            <button onClick={() => onOpen(item.path)}>
              ▤ {item.name}
              <small>
                {item.size ? `${Math.ceil(item.size / 1024)} KB` : ""}
              </small>
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

function FilePreviewContent({
  preview,
  emptyText,
  onOpenExternal,
  externalLabel = "פתיחה חיצונית",
}: {
  preview: FilePreview | null;
  emptyText: string;
  onOpenExternal: () => void;
  externalLabel?: string;
}) {
  if (!preview) return <p>{emptyText}</p>;
  if (preview.kind === "markdown")
    return <article className="markdown-preview" dir="auto"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{preview.text || ""}</ReactMarkdown></article>;
  if (preview.kind === "text") return <pre dir="auto">{preview.text}</pre>;
  if (preview.kind === "image" && preview.data_url)
    return <img src={preview.data_url} alt={preview.name} />;
  if (preview.kind === "media" && preview.data_url)
    return preview.mime_type.startsWith("audio/")
      ? <audio src={preview.data_url} controls />
      : <video src={preview.data_url} controls />;
  if (preview.kind === "pdf" && preview.data_url)
    return <iframe src={preview.data_url} title={preview.name} />;
  return <div>
    <h3>{preview.name}</h3>
    <p>אין תצוגה מקדימה בטוחה לסוג קובץ זה.</p>
    <button onClick={onOpenExternal}>{externalLabel}</button>
  </div>;
}

function FilesPanel() {
  const [root, setRoot] = useState<{ name: string; path: string }>({
    name: "Smarti",
    path: "",
  });
  const [draftRoot, setDraftRoot] = useState("");
  const [items, setItems] = useState<TreeItem[]>([]);
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const data = await coreApi<{
      root: { name: string; path: string };
      items: TreeItem[];
    }>("GET", "/v2/workbench/tree?depth=3");
    setRoot(data.root);
    setDraftRoot(data.root.path);
    setItems(data.items);
  }, []);
  useEffect(() => {
    void load().catch((reason) => setError(String(reason)));
  }, [load]);
  const setWorkspaceRoot = async (path: string) => {
    try {
      await coreApi("PATCH", "/v2/workbench/root", { path }, true);
      setPreview(null);
      await load();
      setError("");
    } catch (reason) {
      setError(String(reason));
    }
  };
  const chooseWorkspaceRoot = async () => {
    try {
      const path = await invoke<string | null>("pick_management_path", { kind: "directory" });
      if (path) await setWorkspaceRoot(path);
    } catch (reason) {
      setError(String(reason));
    }
  };
  const open = async (path: string) => {
    try {
      setPreview(
        await coreApi<FilePreview>(
          "GET",
          `/v2/workbench/file?path=${encodeURIComponent(path)}`,
        ),
      );
      setError("");
    } catch (reason) {
      setError(String(reason));
    }
  };
  const openExternal = async () => {
    if (preview)
      await coreApi("POST", "/v2/workbench/open", { path: preview.path }, true);
  };
  return (
    <div className="files-panel">
      <header>
        <input
          dir="ltr"
          aria-label="נתיב תיקיית העבודה"
          value={draftRoot}
          onChange={(event) => setDraftRoot(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void setWorkspaceRoot(draftRoot); }}
          title={root.path}
        />
        <button type="button" onClick={() => void chooseWorkspaceRoot()}>תיקייה</button>
        <button type="button" onClick={() => void setWorkspaceRoot(draftRoot)}>החל</button>
        <button onClick={() => void load()}>רענון</button>
        <button disabled={!preview} onClick={() => void openExternal()}>
          פתיחה
        </button>
      </header>
      {error && <p className="workbench-error">{error}</p>}
      <div className="files-split">
        <aside>
          <Tree items={items} onOpen={(path) => void open(path)} />
        </aside>
        <section className="file-preview">
          <FilePreviewContent preview={preview} emptyText="בחר קובץ מתיקיית העבודה" onOpenExternal={() => void openExternal()} />
        </section>
      </div>
    </div>
  );
}

function ArtifactsPanel() {
  const [items, setItems] = useState<
    Array<{ name: string; path: string; size: number; modified_at: string }>
  >([]);
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [error, setError] = useState("");
  const [openingWith, setOpeningWith] = useState(false);
  const requestId = useRef(0);
  const load = useCallback(
    async () => {
      try {
        const data = await coreApi<{ items: typeof items }>("GET", "/v2/workbench/artifacts");
        setItems(data.items);
        setError("");
      } catch (reason) {
        setError(String(reason));
      }
    },
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const open = async (path: string) => {
    const id = ++requestId.current;
    setSelected(path);
    setPreview(null);
    setError("");
    try {
      const file = await coreApi<FilePreview>("GET", `/v2/workbench/file?path=${encodeURIComponent(path)}`);
      if (id === requestId.current) setPreview(file);
    } catch (reason) {
      if (id === requestId.current) setError(String(reason));
    }
  };
  const openWith = async () => {
    if (!selected || openingWith) return;
    setOpeningWith(true);
    try {
      const request = () => invoke<boolean>("desktop_open_with", { path: selected });
      try {
        await request();
      } catch (reason) {
        const oldSchema = import.meta.env.DEV && String(reason).includes("Additional properties are not allowed")
          && String(reason).includes("'action' was unexpected");
        if (!oldSchema) throw reason;
        await invoke("core_restart");
        let ready = false;
        for (let attempt = 0; attempt < 60; attempt += 1) {
          const state = await invoke<{ state: string }>("core_status");
          if (state.state === "ready") { ready = true; break; }
          if (["fatal", "repair", "crashed"].includes(state.state)) break;
          await new Promise((resolve) => window.setTimeout(resolve, 500));
        }
        if (!ready) throw new Error("לא ניתן להפעיל מחדש את שירות הקבצים.");
        await request();
      }
      setError("");
    } catch (reason) {
      setError(String(reason));
    } finally {
      setOpeningWith(false);
    }
  };
  return (
    <div className="artifacts-panel">
      <header>
        <h2>תוצרים שנוצרו או עודכנו בשיחה</h2>
        <button onClick={() => void load()}>רענון</button>
        <button disabled={!selected || openingWith} onClick={() => void openWith()}>{openingWith ? "פותח…" : "פתח באמצעות"}</button>
      </header>
      {error && <p className="workbench-error">{error}</p>}
      <div className="artifacts-split">
        <aside aria-label="רשימת תוצרים">
          {items.map((item) => (
            <button key={item.path} type="button" className="artifact-item" aria-current={selected === item.path ? "true" : undefined} onClick={() => void open(item.path)}>
              <b>{item.path}</b>
              <small>{new Date(item.modified_at).toLocaleString("he-IL")} · {Math.ceil(item.size / 1024)} KB</small>
            </button>
          ))}
          {!items.length && <p>עדיין אין תוצרים בתיקיית העבודה</p>}
        </aside>
        <section className="file-preview" aria-label="תצוגת תוצר">
          <FilePreviewContent preview={preview} emptyText={selected ? (error || "טוען תצוגה מקדימה…") : "בחר תוצר מהרשימה"} onOpenExternal={() => void openWith()} externalLabel="פתח באמצעות" />
        </section>
      </div>
    </div>
  );
}

function TerminalPanel({ onSession }: { onSession?: (id: string) => void }) {
  const [id, setId] = useState("");
  const [output, setOutput] = useState("Smarti Terminal\n");
  const [command, setCommand] = useState("");
  const [running, setRunning] = useState(false);
  const outputRef = useRef<HTMLPreElement>(null);
  const sessionRef = useRef("");
  const create = useCallback(async () => {
    const item = await coreApi<{ id: string }>(
      "POST",
      "/v2/workbench/terminals",
      {},
      true,
    );
    sessionRef.current = item.id;
    setId(item.id);
    setRunning(true);
    onSession?.(item.id);
  }, [onSession]);
  useEffect(() => {
    void create();
    return () => {
      if (sessionRef.current)
        void coreApi(
          "DELETE",
          `/v2/workbench/terminals/${encodePath(sessionRef.current)}`,
          {},
          true,
        );
    };
  }, []);
  useEffect(() => {
    if (!id || !running) return;
    const timer = window.setInterval(
      () =>
        void coreApi<{ output: string; running: boolean }>(
          "GET",
          `/v2/workbench/terminals/${encodePath(id)}`,
        ).then((data) => {
          if (data.output) setOutput((current) => current + data.output);
          setRunning(data.running);
        }),
      350,
    );
    return () => clearInterval(timer);
  }, [id, running]);
  useEffect(() => {
    if (outputRef.current)
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
  }, [output]);
  const send = async () => {
    if (!id || !command.trim()) return;
    const value = command;
    setOutput((current) => `${current}PS › ${value}\n`);
    setCommand("");
    const data = await coreApi<{ output: string; running: boolean }>(
      "POST",
      `/v2/workbench/terminals/${encodePath(id)}`,
      { action: "write", text: value },
      true,
    );
    if (data.output) setOutput((current) => current + data.output);
    setRunning(data.running);
  };
  const restart = async () => {
    if (!id) return;
    const item = await coreApi<{ id: string }>(
      "POST",
      `/v2/workbench/terminals/${encodePath(id)}`,
      { action: "restart" },
      true,
    );
    sessionRef.current = item.id;
    setId(item.id);
    setOutput("Smarti Terminal\n");
    setRunning(true);
  };
  return (
    <div className="terminal-panel" dir="ltr">
      <header>
        <span>{running ? "● פועל" : "■ הסתיים"}</span>
        <button onClick={() => void restart()}>הפעל מחדש</button>
      </header>
      <pre ref={outputRef}>{output}</pre>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <b>PS ›</b>
        <input
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          disabled={!running}
          aria-label="פקודת PowerShell"
        />
      </form>
    </div>
  );
}

export type WorkbenchHandle = { activateTab: (id: string) => void };

export function WorkbenchSurface({
  ref,
  initial,
  visible,
  motionRevision,
  restored,
  onStateChange,
  onBrowserActivity,
  onClose,
  closeIcon,
  sessionId,
  onCanvasAction,
}: {
  ref?: Ref<WorkbenchHandle>;
  initial: WorkbenchTab | null;
  visible: boolean;
  motionRevision?: boolean | string;
  restored?: WorkbenchSnapshot | null;
  onStateChange?: (state: WorkbenchSnapshot) => void;
  onBrowserActivity?: (activity: BrowserActivity | null) => void;
  onClose: () => void;
  closeIcon: string;
  sessionId: string;
  onCanvasAction: (text: string) => void;
}) {
  const counter = useRef(maxTabSequence(restored?.tabs || []));
  const restoredApplied = useRef(Boolean(restored));
  const [tabs, setTabs] = useState<Tab[]>(() => restored?.tabs || []);
  const [active, setActive] = useState(() => restored?.active || "");
  const [menu, setMenu] = useState(false);
  const addMenu = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (restoredApplied.current || !restored) return;
    restoredApplied.current = true;
    setTabs(restored.tabs);
    setActive(restored.active);
    counter.current = Math.max(counter.current, maxTabSequence(restored.tabs));
  }, [restored]);
  useEffect(() => {
    if (!initial) return;
    const existing = tabs.find((tab) => tab.id === active && tab.kind === initial)
      ?? tabs.find((tab) => tab.kind === initial);
    if (existing) setActive(existing.id);
    else add(initial);
  }, [initial]);
  useEffect(() => {
    onStateChange?.({ tabs, active });
  }, [tabs, active, onStateChange]);
  const add = (kind: WorkbenchTab, forceNew = false) => {
    const number = ++counter.current;
    const id = `${kind}-${number}`;
    const next = openWorkbenchTab(
      { tabs, active },
      {
        id,
        kind,
        title: nextWorkbenchTabTitle(tabs, kind, labels[kind]),
      },
      forceNew,
    );
    setTabs(next.tabs);
    setActive(next.active);
    setMenu(false);
  };
  const close = (id: string) => {
    if (tabs.some((tab) => tab.id === id && tab.kind === "browser")) {
      forgetBrowserWorkspaceSession(id);
      void invoke("browser_close_workspace", { workspaceId: id }).catch(() => undefined);
    }
    const next = closeWorkbenchTab({ tabs, active }, id);
    setTabs(next.tabs);
    setActive(next.active);
  };
  const reorder = (sourceId: string, targetId: string) => {
    setTabs((current) => reorderWorkbenchTabs({ tabs: current, active }, sourceId, targetId).tabs);
  };
  const tabDrag = useWorkbenchTabDrag(visible, reorder);
  const current = tabs.find((tab) => tab.id === active);
  useImperativeHandle(ref, () => ({
    activateTab: (id) => { if (tabs.some((tab) => tab.id === id)) setActive(id); },
  }), [tabs]);
  const reportBrowserActivity = useCallback((activity: BrowserActivity | null) => {
    onBrowserActivity?.(current?.kind === "browser" && activity?.workspaceId === current.id ? activity : null);
  }, [current?.id, current?.kind, onBrowserActivity]);
  useEffect(() => {
    if (current?.kind !== "browser") onBrowserActivity?.(null);
    return () => onBrowserActivity?.(null);
  }, [current?.id, current?.kind, onBrowserActivity]);
  useDismissiblePopup({
    open: menu,
    roots: [addMenu],
    onDismiss: () => setMenu(false),
  });
  return (
    <>
      <header className="workbench-head" dir="ltr">
        <span className="workbench-context">Smarti</span>
        <div
          className={`workbench-tabs${tabDrag.preview ? " is-dragging" : ""}`}
          role="tablist"
          ref={tabDrag.strip}
          onPointerDownCapture={tabDrag.prepareClick}
          onPointerMove={tabDrag.move}
          onPointerUp={tabDrag.end}
          onPointerCancel={tabDrag.cancel}
          onLostPointerCapture={tabDrag.cancel}
          onClickCapture={tabDrag.click}
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              data-tab-id={tab.id}
              className={tabDrag.preview?.id === tab.id ? "is-dragging" : undefined}
              data-drop-side={tabDrag.preview?.target === tab.id && tabDrag.preview.id !== tab.id ? tabDrag.preview.side : undefined}
              style={tabDrag.preview?.id === tab.id ? { transform: `translateX(${tabDrag.preview.offset}px)` } : undefined}
              aria-selected={tab.id === active}
              onClick={() => setActive(tab.id)}
              onPointerDown={(event) => tabDrag.begin(event, tab.id)}
              onDragStart={(event) => event.preventDefault()}
            >
              <span>{icons[tab.kind]}</span>
              {tab.title}
              <i
                role="button"
                aria-label={`סגירת ${tab.title}`}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  close(tab.id);
                }}
              >
                ×
              </i>
            </button>
          ))}
        </div>
        <div className="workbench-add" ref={addMenu}>
          <button
            type="button"
            aria-label="פתיחת לשונית"
            onClick={() => setMenu((open) => !open)}
          >
            +
          </button>
          {menu && (
            <div dir="rtl">
              {(
                [
                  "files",
                  "browser",
                  "terminal",
                  "canvas",
                  "artifacts",
                ] as WorkbenchTab[]
              ).map((kind) => (
                  <button type="button" key={kind} onClick={() => add(kind, true)}>
                  <span>{icons[kind]}</span>
                  {labels[kind]}
                </button>
              ))}
            </div>
          )}
        </div>
        <IconButton
          className="workbench-close-control"
          label="סגירת סביבת העבודה"
          onClick={onClose}
        >
          <LegacyIcon src={closeIcon} size={20} />
        </IconButton>
      </header>
      <div className="workbench-body">
        {!current && (
          <div className="workbench-empty" role="group" aria-label="מה תרצה לפתוח?">
            {launcherKinds.map((kind) => (
              <button type="button" key={kind} onClick={() => add(kind, true)}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                  <path d={launcherIconPaths[kind]} />
                </svg>
                <span>{labels[kind]}</span>
              </button>
            ))}
          </div>
        )}
        {tabs.some(tab => tab.kind === "browser") && (
          <section className="workbench-panel" hidden={current?.kind !== "browser"} aria-label="דפדפן">
            {/* One controller manages the native surface; each Workbench browser
                entry owns its own set of WebView2 tabs. */}
            <BrowserPanel workspaceTabId={current?.kind === "browser" ? current.id : ""} visible={visible && current?.kind === "browser"} geometryRevision={motionRevision} onActivity={reportBrowserActivity} />
          </section>
        )}
        {tabs.filter(tab => tab.kind !== "browser").map((tab) => <section className="workbench-panel" hidden={tab.id !== active} key={tab.id} aria-label={tab.title}>
          {tab.kind === "files" && <FilesPanel />}
          {tab.kind === "terminal" && <TerminalPanel />}
          {tab.kind === "artifacts" && <ArtifactsPanel />}
          {tab.kind === "canvas" && <CanvasPanel sessionId={sessionId} onAction={onCanvasAction} />}
        </section>)}
      </div>
    </>
  );
}
