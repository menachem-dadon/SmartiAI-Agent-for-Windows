// Technical flow copied from WorkbenchPanels for isolated candidate styling.
// Keep this derivative visible in the coverage ledger until UX-4 consolidation.
import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { coreApi, encodePath } from "../coreApi";
import { Icon } from "./Icon";
import { Button } from "./Button";
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
              <summary><Icon name="folder" /> {item.name}</summary>
              {item.children && <Tree items={item.children} onOpen={onOpen} />}
            </details>
          ) : (
            <button onClick={() => onOpen(item.path)}>
              <Icon name="file" /> {item.name}
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

export function FilesPanel() {
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

export function ArtifactsPanel({ onOpenSample }: { onOpenSample?: () => void }) {
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
        {onOpenSample && <Button icon="file" label="פתיחת מסמך" onClick={onOpenSample} />}
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

export function TerminalPanel({ onSession }: { onSession?: (id: string) => void }) {
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
