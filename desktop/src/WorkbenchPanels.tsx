import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BrowserPanel, type BrowserActivity } from "./BrowserPanel";
import { CanvasPanel } from "./CanvasPanel";
import { coreApi, encodePath } from "./coreApi";
import {
  closeWorkbenchTab,
  openWorkbenchTab,
  reorderWorkbenchTabs,
  type WorkbenchSnapshot,
  type WorkbenchTab,
  type WorkbenchTabRecord,
} from "./workspaceState";
import { useDismissiblePopup } from "./popupDismissal";

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
const labels: Record<WorkbenchTab, string> = {
  browser: "דפדפן",
  files: "קבצים",
  terminal: "מסוף",
  canvas: "קנבס",
  artifacts: "תוצרים",
};
const icons: Record<WorkbenchTab, string> = {
  browser: "◎",
  files: "▤",
  terminal: ">_",
  canvas: "◇",
  artifacts: "▱",
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
  const setWorkspaceRoot = async () => {
    await coreApi("PATCH", "/v2/workbench/root", { path: draftRoot }, true);
    setPreview(null);
    await load();
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
          value={draftRoot}
          onChange={(event) => setDraftRoot(event.target.value)}
          title={root.path}
        />
        <button onClick={() => void setWorkspaceRoot()}>תיקייה</button>
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
          {!preview ? (
            <p>בחר קובץ מתיקיית העבודה</p>
          ) : preview.kind === "markdown" ? (
            <article className="markdown-preview" dir="auto">
              <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
                {preview.text || ""}
              </ReactMarkdown>
            </article>
          ) : preview.kind === "text" ? (
            <pre dir="auto">{preview.text}</pre>
          ) : preview.kind === "image" && preview.data_url ? (
            <img src={preview.data_url} alt={preview.name} />
          ) : preview.kind === "media" && preview.data_url ? (
            preview.mime_type.startsWith("audio/") ? (
              <audio src={preview.data_url} controls />
            ) : (
              <video src={preview.data_url} controls />
            )
          ) : preview.kind === "pdf" && preview.data_url ? (
            <iframe src={preview.data_url} title={preview.name} />
          ) : (
            <div>
              <h3>{preview.name}</h3>
              <p>
                אין תצוגה מקדימה בטוחה לסוג זה. אפשר לפתוח אותו בתוכנת ברירת
                המחדל.
              </p>
              <button onClick={() => void openExternal()}>פתיחה חיצונית</button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function ArtifactsPanel() {
  const [items, setItems] = useState<
    Array<{ name: string; path: string; size: number; modified_at: string }>
  >([]);
  const load = useCallback(
    async () =>
      setItems(
        (
          await coreApi<{ items: typeof items }>(
            "GET",
            "/v2/workbench/artifacts",
          )
        ).items,
      ),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="artifacts-panel">
      <header>
        <h2>תוצרים שנוצרו או עודכנו בשיחה</h2>
        <button onClick={() => void load()}>רענון</button>
      </header>
      <div>
        {items.map((item) => (
          <article key={item.path}>
            <b>{item.path}</b>
            <small>
              {new Date(item.modified_at).toLocaleString("he-IL")} ·{" "}
              {Math.ceil(item.size / 1024)} KB
            </small>
          </article>
        ))}
        {!items.length && <p>עדיין אין תוצרים בתיקיית העבודה</p>}
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

export function WorkbenchSurface({
  initial,
  visible,
  restored,
  onStateChange,
  onBrowserActivity,
  onClose,
  sessionId,
  onCanvasAction,
}: {
  initial: WorkbenchTab | null;
  visible: boolean;
  restored?: WorkbenchSnapshot | null;
  onStateChange?: (state: WorkbenchSnapshot) => void;
  onBrowserActivity?: (activity: BrowserActivity) => void;
  onClose: () => void;
  sessionId: string;
  onCanvasAction: (text: string) => void;
}) {
  const counter = useRef(0);
  const restoredApplied = useRef(Boolean(restored));
  const [tabs, setTabs] = useState<Tab[]>(() => restored?.tabs || []);
  const [active, setActive] = useState(() => restored?.active || "");
  const [menu, setMenu] = useState(false);
  const addMenu = useRef<HTMLDivElement | null>(null);
  const draggedTab = useRef("");
  useEffect(() => {
    if (restoredApplied.current || !restored) return;
    restoredApplied.current = true;
    setTabs(restored.tabs);
    setActive(restored.active);
    counter.current = Math.max(counter.current, restored.tabs.length);
  }, [restored]);
  useEffect(() => {
    if (!initial) return;
    const existing = tabs.find((tab) => tab.kind === initial);
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
        title: `${labels[kind]}${["files", "browser", "terminal"].includes(kind) && tabs.some((tab) => tab.kind === kind) ? ` ${number}` : ""}`,
      },
      forceNew,
    );
    setTabs(next.tabs);
    setActive(next.active);
    setMenu(false);
  };
  const close = (id: string) => {
    const next = closeWorkbenchTab({ tabs, active }, id);
    setTabs(next.tabs);
    setActive(next.active);
    if (!next.tabs.length) setTimeout(onClose, 0);
  };
  const reorder = (sourceId: string, targetId: string) => {
    const next = reorderWorkbenchTabs({ tabs, active }, sourceId, targetId);
    setTabs(next.tabs);
  };
  const current = tabs.find((tab) => tab.id === active);
  useDismissiblePopup({
    open: menu,
    roots: [addMenu],
    onDismiss: () => setMenu(false),
  });
  return (
    <>
      <header className="workbench-head" dir="ltr">
        <span className="workbench-context">Smarti</span>
        <div className="workbench-tabs" role="tablist">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={tab.id === active}
              onClick={() => setActive(tab.id)}
              draggable
              onDragStart={() => { draggedTab.current = tab.id; }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                reorder(draggedTab.current, tab.id);
                draggedTab.current = "";
              }}
            >
              <span>{icons[tab.kind]}</span>
              {tab.title}
              <i
                role="button"
                aria-label={`סגירת ${tab.title}`}
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
      </header>
      <div className="workbench-body">
        {!current && <div className="workbench-empty"><h2>מה תרצה לפתוח?</h2><button type="button" onClick={() => add("files", true)}>▣ קבצים</button><button type="button" onClick={() => add("browser", true)}>◎ דפדפן</button><button type="button" onClick={() => add("terminal", true)}>&gt;_ מסוף</button></div>}
        {tabs.map((tab) => <section className="workbench-panel" hidden={tab.id !== active} key={tab.id} aria-label={tab.title}>
          {tab.kind === "browser" && <BrowserPanel visible={visible && tab.id === active} onActivity={onBrowserActivity} />}
          {tab.kind === "files" && <FilesPanel />}
          {tab.kind === "terminal" && <TerminalPanel />}
          {tab.kind === "artifacts" && <ArtifactsPanel />}
          {tab.kind === "canvas" && <CanvasPanel sessionId={sessionId} onAction={onCanvasAction} />}
        </section>)}
      </div>
    </>
  );
}
