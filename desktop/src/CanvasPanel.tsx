import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { coreApi, encodePath } from "./coreApi";

type CanvasSummary = {
  id: string;
  title: string;
  created_at: string;
  closed: boolean;
};
type CanvasButton = {
  id: string;
  label: string;
  action?: string;
  target?: string;
};
type CanvasArtifact = CanvasSummary & {
  document: string;
  buttons: CanvasButton[];
  button_positions: Array<Record<string, unknown>>;
  remote_images_enabled: boolean;
};
type CanvasMessage = {
  channel?: unknown;
  kind?: unknown;
  canvasId?: unknown;
  payload?: unknown;
};

const MAX_MESSAGE_CHARS = 128_000;

export function securedCanvasDocument(
  document: string,
  canvasId: string,
  allowRemoteImages: boolean,
): string {
  const images = allowRemoteImages ? "data: blob: https:" : "data: blob:";
  const csp = `default-src 'none'; img-src ${images}; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; media-src data: blob:; font-src data:; object-src 'none'; frame-src 'none'; child-src 'none'; form-action 'none'; base-uri 'none'`;
  const bridge = `<meta http-equiv="Content-Security-Policy" content="${csp}"><meta name="referrer" content="no-referrer"><script>(()=>{const channel='smarti-canvas-v2';const canvasId=${JSON.stringify(canvasId)};const send=(kind,payload)=>parent.postMessage({channel,kind,canvasId,payload},'*');const positions=()=>{try{const root=document.documentElement.getBoundingClientRect();const buttons=Array.from(document.querySelectorAll('button,[role="button"],a')).slice(0,64).map((node,index)=>{const r=node.getBoundingClientRect();return{id:(node.id||('dom-button-'+(index+1))).slice(0,80),label:(node.innerText||node.getAttribute('aria-label')||'').trim().slice(0,160),x:Math.round(r.left-root.left),y:Math.round(r.top-root.top),width:Math.round(r.width),height:Math.round(r.height)}});send('layout',{buttons})}catch(error){send('error',{code:'layout_failed'})}};const ready=()=>{send('content-ready',{});positions();if(window.ResizeObserver)new ResizeObserver(positions).observe(document.documentElement);new MutationObserver(positions).observe(document.documentElement,{subtree:true,childList:true,attributes:true})};window.open=()=>null;document.addEventListener('click',event=>{const target=event.target&&event.target.closest&&event.target.closest('[data-smarti-action],button,[role="button"],a');if(!target)return;if(target.closest('a[href]'))event.preventDefault();if(!event.isTrusted)return;send('action',{id:(target.id||target.dataset.smartiAction||'').slice(0,80)})},true);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready,{once:true});else ready()})();</script>`;
  if (/<head[^>]*>/i.test(document))
    return document.replace(/<head[^>]*>/i, (head) => head + bridge);
  return `<!doctype html><html lang="he" dir="rtl"><head>${bridge}</head><body>${document}</body></html>`;
}

export function CanvasPanel({
  sessionId,
  onAction,
}: {
  sessionId: string;
  onAction: (text: string) => void;
}) {
  const [items, setItems] = useState<CanvasSummary[]>([]);
  const [selected, setSelected] = useState("");
  const [canvas, setCanvas] = useState<CanvasArtifact | null>(null);
  const [allowRemote, setAllowRemote] = useState(false);
  const [pendingAction, setPendingAction] = useState<CanvasButton | null>(null);
  const [notice, setNotice] = useState("");
  const frameRef = useRef<HTMLIFrameElement>(null);
  const layoutTimer = useRef<number | null>(null);
  const refresh = useCallback(async () => {
    if (!sessionId) {
      setItems([]);
      setCanvas(null);
      return;
    }
    const result = await coreApi<{ items: CanvasSummary[] }>(
      "GET",
      `/v2/conversations/${encodePath(sessionId)}/canvases`,
    );
    setItems(result.items);
    setSelected((current) =>
      result.items.some((item) => item.id === current)
        ? current
        : result.items.find((item) => !item.closed)?.id ||
          result.items[0]?.id ||
          "",
    );
  }, [sessionId]);
  useEffect(() => {
    void refresh().catch((error) => setNotice(String(error)));
  }, [refresh]);
  useEffect(() => {
    if (!selected) {
      setCanvas(null);
      return;
    }
    const suffix = allowRemote ? "?allow_remote_images=true" : "";
    void coreApi<{ canvas: CanvasArtifact }>(
      "GET",
      `/v2/conversations/${encodePath(sessionId)}/canvases/${encodePath(selected)}${suffix}`,
    )
      .then(({ canvas: value }) => {
        setCanvas(value);
        setPendingAction(null);
      })
      .catch((error) => setNotice(String(error)));
  }, [selected, sessionId, allowRemote]);
  useEffect(() => {
    const receive = (event: MessageEvent<CanvasMessage>) => {
      if (
        event.source !== frameRef.current?.contentWindow ||
        !canvas ||
        event.data?.channel !== "smarti-canvas-v2" ||
        event.data.canvasId !== canvas.id
      )
        return;
      let encoded = "";
      try {
        encoded = JSON.stringify(event.data);
      } catch {
        return;
      }
      if (encoded.length > MAX_MESSAGE_CHARS) return;
      if (event.data.kind === "content-ready") {
        setNotice("");
        return;
      }
      if (event.data.kind === "error") {
        setNotice("שגיאה מבודדת בתוך הקנבס");
        return;
      }
      if (event.data.kind === "layout") {
        const buttons = (event.data.payload as { buttons?: unknown })?.buttons;
        if (!Array.isArray(buttons) || buttons.length > 64) return;
        if (layoutTimer.current) window.clearTimeout(layoutTimer.current);
        layoutTimer.current = window.setTimeout(
          () =>
            void coreApi(
              "PATCH",
              `/v2/conversations/${encodePath(sessionId)}/canvases/${encodePath(canvas.id)}`,
              { action: "layout", button_positions: buttons },
              true,
            ).catch(() => undefined),
          250,
        );
      }
      if (event.data.kind === "action") {
        const id = String((event.data.payload as { id?: unknown })?.id || "");
        const approved = canvas.buttons.find((button) => button.id === id);
        if (approved) setPendingAction(approved);
      }
    };
    window.addEventListener("message", receive);
    return () => {
      window.removeEventListener("message", receive);
      if (layoutTimer.current) window.clearTimeout(layoutTimer.current);
    };
  }, [canvas, sessionId]);
  const srcDoc = useMemo(
    () =>
      canvas
        ? securedCanvasDocument(canvas.document, canvas.id, allowRemote)
        : "",
    [canvas, allowRemote],
  );
  const setClosed = async (closed: boolean) => {
    if (!canvas) return;
    await coreApi(
      "PATCH",
      `/v2/conversations/${encodePath(sessionId)}/canvases/${encodePath(canvas.id)}`,
      { action: closed ? "close" : "reopen" },
      true,
    );
    await refresh();
  };
  const confirmAction = () => {
    if (!canvas || !pendingAction) return;
    onAction(
      `[נתוני משתמש מהקנבס ${canvas.id}]\n${JSON.stringify({ action: pendingAction.action || pendingAction.id, target: pendingAction.target || "", id: pendingAction.id }, null, 2)}`,
    );
    setPendingAction(null);
  };
  return (
    <div className="canvas-panel">
      <header>
        <select
          aria-label="בחירת קנבס"
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
        >
          {items.map((item) => (
            <option key={item.id} value={item.id}>
              {item.closed ? "(סגור) " : ""}
              {item.title}
            </option>
          ))}
        </select>
        <label>
          <input
            type="checkbox"
            checked={allowRemote}
            onChange={(event) => setAllowRemote(event.target.checked)}
          />{" "}
          תמונות HTTPS
        </label>
        <button onClick={() => void refresh()}>רענון</button>
        {canvas && (
          <button onClick={() => void setClosed(!canvas.closed)}>
            {canvas.closed ? "פתיחה מחדש" : "סגירה"}
          </button>
        )}
      </header>
      {notice && <p className="workbench-error">{notice}</p>}
      {!canvas ? (
        <p className="canvas-empty">אין Canvas בשיחה הנוכחית.</p>
      ) : (
        <>
          <iframe
            ref={frameRef}
            title={canvas.title}
            sandbox="allow-scripts"
            referrerPolicy="no-referrer"
            srcDoc={srcDoc}
          />
          <footer>
            <span>Renderer מבודד · ללא Tauri API, קבצים, ניווט או popups</span>
          </footer>
        </>
      )}
      {pendingAction && (
        <div className="canvas-action-confirm" role="dialog" aria-modal="true">
          <p>
            הקנבס ביקש להפעיל: <b>{pendingAction.label}</b>
          </p>
          <button onClick={() => setPendingAction(null)}>ביטול</button>
          <button onClick={confirmAction}>שליחה לסמארטי</button>
        </div>
      )}
    </div>
  );
}

export const canvasSecurityPolicy = {
  sandbox: "allow-scripts",
  maxMessageChars: MAX_MESSAGE_CHARS,
  channel: "smarti-canvas-v2",
} as const;
