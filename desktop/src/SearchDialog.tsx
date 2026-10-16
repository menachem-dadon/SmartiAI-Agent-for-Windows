import { useEffect, useId, useRef, useState } from "react";
import type { Conversation, ConversationList } from "./chatTypes";
import { coreApi } from "./coreApi";
import { Button, Dialog, Field, Icon, IconButton } from "./design-system";
import { highlightParts, rememberConversationVisit, suggestedConversations, type SearchFile } from "./searchState";
import "./search.css";

function Highlight({ text, query }: { text: string; query: string }) {
  return highlightParts(text, query).map((part, index) => part.match ? <mark key={index}>{part.text}</mark> : part.text);
}

type Props = {
  open: boolean; conversations: Conversation[]; onClose: () => void;
  onSelect: (item: Conversation) => void; onCreate: () => void; onFile: (path: string) => void;
};

export function SearchDialog(props: Props) {
  return props.open ? <SearchContent {...props} /> : null;
}

function SearchContent({ conversations, onClose, onSelect, onCreate, onFile }: Props) {
  const [mode, setMode] = useState<"chats" | "files">("chats");
  const [query, setQuery] = useState("");
  const [selection, setSelection] = useState(0);
  const [response, setResponse] = useState<{ key: string; items: (Conversation | SearchFile)[]; truncated?: boolean } | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const listId = useId();
  const search = query.trim();
  const key = `${mode}:${search}`;
  const items = !search ? mode === "chats" ? suggestedConversations(conversations) : [] : response?.key === key ? response.items : [];
  const pending = Boolean(search && (loading || response?.key !== key) && !error);

  useEffect(() => {
    let cancelled = false;
    setError(""); setSelection(0); setLoading(Boolean(search));
    if (list.current) list.current.scrollTop = 0;
    if (!search) { setResponse(null); return; }
    const timer = window.setTimeout(() => {
      const request = mode === "chats"
        ? coreApi<ConversationList>("GET", `/v2/conversations?q=${encodeURIComponent(search)}&limit=100`)
        : coreApi<{ items: SearchFile[]; truncated?: boolean }>("GET", `/v2/workbench/artifacts?q=${encodeURIComponent(search)}`);
      void request.then(data => {
        if (!cancelled) setResponse({ key, items: mode === "chats" ? data.items.filter(item => Number((item as Conversation).message_count) > 0) : data.items, truncated: "truncated" in data ? Boolean(data.truncated) : "total" in data && Number(data.total) > data.items.length });
      }).catch(reason => {
        if (!cancelled) { setError(`לא ניתן לחפש כרגע: ${String(reason)}`); setResponse({ key, items: [] }); }
      }).finally(() => { if (!cancelled) setLoading(false); });
    }, 180);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [mode, search, key, retry]);

  useEffect(() => { input.current?.focus(); }, [mode]);
  useEffect(() => { list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" }); }, [selection]);

  const changeMode = (next: typeof mode) => { setMode(next); setQuery(""); setError(""); setSelection(0); };
  const choose = (item: Conversation | SearchFile) => {
    onClose();
    if ("id" in item) { rememberConversationVisit(item.id, true); onSelect(item); }
    else onFile(item.path);
  };
  const label = mode === "chats" ? "חיפוש בשיחות" : "חיפוש בקבצים ובתוצרים";
  return <Dialog open title={label} className="search-dialog" initialFocus={input} onClose={onClose}>
    <div className="search-input-row">
      <Icon name="search" />
      <Field ref={input} label={label} hiddenLabel placeholder={mode === "chats" ? "חיפוש בכותרות ובתוכן השיחות" : "חיפוש לפי שם קובץ או נתיב"}
        value={query} autoComplete="off" spellCheck={false} role="combobox" aria-expanded={items.length > 0} aria-controls={listId}
        aria-autocomplete="list" aria-activedescendant={items[selection] ? `${listId}-${selection}` : undefined}
        onChange={event => { setQuery(event.target.value); setError(""); setSelection(0); }}
        onKeyDown={event => {
          if (event.nativeEvent.isComposing) return;
          if ((event.key === "ArrowDown" || event.key === "ArrowUp") && items.length) {
            event.preventDefault(); setSelection(index => (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length);
          } else if (event.key === "Enter" && items[selection]) { event.preventDefault(); choose(items[selection]); }
        }} />
      {query && <IconButton icon="close" label="ניקוי החיפוש" variant="ghost" tooltip={false} onClick={() => { setQuery(""); setError(""); input.current?.focus(); }} />}
    </div>
    <div className="search-results" ref={list}>
      <p className="search-section-label">{mode === "files" ? "קבצים ותוצרים" : search ? "שיחות" : "לחזור לשיחה"}</p>
      <div id={listId} role="listbox" aria-label={label} aria-busy={pending}>
        {items.map((item, index) => {
          const chat = "id" in item;
          const title = chat ? item.title : item.name;
          const detail = chat ? search ? item.search_preview || item.preview || "" : "" : item.path;
          return <button type="button" role="option" tabIndex={-1} id={`${listId}-${index}`} key={chat ? item.id : item.path}
            className="search-result" aria-selected={selection === index} onPointerMove={() => setSelection(index)} onClick={() => choose(item)}>
            <Icon name={chat ? "history" : "file"} size={20} />
            <span className="search-result-copy"><span className="search-result-title" dir="auto"><Highlight text={title} query={search} /></span>
              {detail && <span className="search-result-detail" dir="auto"><Highlight text={detail} query={search} /></span>}</span>
            {chat && item.pinned && <Icon name="pin" size={16} />}
          </button>;
        })}
      </div>
      <div className="search-feedback" role="status" aria-live="polite">
        {pending ? "מחפש…" : !error && !items.length ? search ? "לא נמצאו תוצאות. נסו מילה אחרת." : mode === "files" ? "הקלידו שם קובץ כדי למצוא תוצר של סמארטי" : "השיחות שלכם יופיעו כאן" : ""}
      </div>
      {error && <div className="search-error" role="alert"><span>{error}</span><Button variant="ghost" icon="refresh" onClick={() => setRetry(value => value + 1)}>ניסיון נוסף</Button></div>}
      {response?.key === key && response.truncated && <p className="search-section-label">יש תוצאות נוספות. נסו חיפוש ממוקד יותר.</p>}
      {!search && mode === "chats" && <div className="search-quick-actions"><p className="search-section-label">פעולות מהירות</p>
        <Button variant="ghost" icon="newChat" onClick={() => { onClose(); onCreate(); }}>שיחה חדשה</Button>
        <Button variant="ghost" icon="file" onClick={() => changeMode("files")}>חיפוש קבצים ותוצרים</Button>
      </div>}
    </div>
    {(search || mode === "files") && <div className="search-mode-actions"><Button variant="ghost" icon={mode === "files" ? "history" : "file"} onClick={() => changeMode(mode === "files" ? "chats" : "files")}>{mode === "files" ? "חזרה לחיפוש בשיחות" : "חיפוש קבצים ותוצרים"}</Button></div>}
  </Dialog>;
}
