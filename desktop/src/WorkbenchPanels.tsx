import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BrowserPanel } from "./BrowserPanel";
import { CanvasPanel } from "./CanvasPanel";
import { coreApi, encodePath } from "./coreApi";
import type { WorkbenchTab } from "./workspaceState";

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
type Tab = { id: string; kind: WorkbenchTab; title: string };
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
  onClose,
  sessionId,
  onCanvasAction,
}: {
  initial: WorkbenchTab;
  onClose: () => void;
  sessionId: string;
  onCanvasAction: (text: string) => void;
}) {
  const counter = useRef(1);
  const [tabs, setTabs] = useState<Tab[]>(() => [
    { id: `${initial}-1`, kind: initial, title: labels[initial] },
  ]);
  const [active, setActive] = useState(`${initial}-1`);
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    if (!tabs.some((tab) => tab.kind === initial)) add(initial);
    else setActive(tabs.find((tab) => tab.kind === initial)!.id);
  }, [initial]);
  const add = (kind: WorkbenchTab) => {
    const number = ++counter.current;
    const id = `${kind}-${number}`;
    setTabs((current) => [
      ...current,
      {
        id,
        kind,
        title: `${labels[kind]}${["files", "browser", "terminal"].includes(kind) && current.some((tab) => tab.kind === kind) ? ` ${number}` : ""}`,
      },
    ]);
    setActive(id);
    setMenu(false);
  };
  const close = (id: string) => {
    setTabs((current) => {
      const next = current.filter((tab) => tab.id !== id);
      if (!next.length) setTimeout(onClose, 0);
      if (active === id && next.length) setActive(next[next.length - 1].id);
      return next;
    });
  };
  const current = tabs.find((tab) => tab.id === active);
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
        <div className="workbench-add">
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
                <button type="button" key={kind} onClick={() => add(kind)}>
                  <span>{icons[kind]}</span>
                  {labels[kind]}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>
      <div className="workbench-body">
        {current?.kind === "browser" && <BrowserPanel visible />}
        {current?.kind === "files" && <FilesPanel />}
        {current?.kind === "terminal" && <TerminalPanel />}
        {current?.kind === "artifacts" && <ArtifactsPanel />}
        {current?.kind === "canvas" && (
          <CanvasPanel sessionId={sessionId} onAction={onCanvasAction} />
        )}
      </div>
    </>
  );
}
