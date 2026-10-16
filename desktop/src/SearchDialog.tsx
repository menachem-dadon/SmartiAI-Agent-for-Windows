import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { Conversation, ConversationList } from "./chatTypes";
import { coreApi } from "./coreApi";
import { Button, Dialog, Field, Icon } from "./design-system";
import { highlightParts, rankSearchFiles, rememberConversationVisit, suggestedConversations, type SearchFile } from "./searchState";
import "./search.css";

function Highlight({ text, query }: { text: string; query: string }) {
  return highlightParts(text, query).map((part, index) => part.match ? <mark key={index}>{part.text}</mark> : part.text);
}

type Props = {
  open: boolean; conversations: Conversation[]; onClose: () => void;
  onSelect: (item: Conversation) => void; onCreate: () => void; onFile: (path: string) => void;
};
type SearchResponse = { key: string; mode: "chats" | "files"; query: string; items: (Conversation | SearchFile)[]; truncated?: boolean };

export function SearchDialog(props: Props) {
  return props.open ? <SearchContent {...props} /> : null;
}

function SearchContent({ conversations, onClose, onSelect, onCreate, onFile }: Props) {
  const [mode, setMode] = useState<"chats" | "files">("chats");
  const [query, setQuery] = useState("");
  const [selection, setSelection] = useState(0);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [suggestionLimit, setSuggestionLimit] = useState(9);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLParagraphElement>(null);
  const actions = useRef<HTMLDivElement>(null);
  const listId = useId();
  const search = query.trim();
  const key = `${mode}:${search}`;
  const suggestions = suggestedConversations(conversations);
  const items = !search ? mode === "chats" ? suggestions.slice(0, suggestionLimit) : [] : response?.mode === mode ? response.items : [];
  const renderedQuery = search ? response?.query || "" : "";
  const pending = Boolean(search && (loading || response?.key !== key) && !error);

  useEffect(() => {
    let cancelled = false;
    setError(""); setLoading(Boolean(search));
    if (!search) { setResponse(null); return; }
    const timer = window.setTimeout(() => {
      const request = mode === "chats"
        ? coreApi<ConversationList>("GET", `/v2/conversations?q=${encodeURIComponent(search)}&matches=messages&limit=9`)
        : coreApi<{ items: SearchFile[]; truncated?: boolean }>("GET", `/v2/workbench/artifacts?q=${encodeURIComponent(search)}`);
      void request.then(data => {
        if (cancelled) return;
        const matches = mode === "chats" ? data.items.filter(item => Number((item as Conversation).message_count) > 0).slice(0, 9) : rankSearchFiles(data.items as SearchFile[], search);
        setResponse({ key, mode, query: search, items: matches, truncated: "truncated" in data && Boolean(data.truncated) });
        setSelection(0);
        if (list.current) list.current.scrollTop = 0;
      }).catch(reason => {
        if (!cancelled) setError(`לא ניתן לחפש כרגע: ${String(reason)}`);
      }).finally(() => { if (!cancelled) setLoading(false); });
    }, 180);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [mode, search, key, retry]);

  // Fit the suggestions around the two priority actions. Future quick actions
  // can follow this measured group and remain in the same scrollable body.
  useLayoutEffect(() => {
    if (search || mode !== "chats") return;
    const dialog = input.current?.closest("dialog");
    if (!dialog) return;
    const fit = () => {
      const row = list.current?.querySelector<HTMLElement>(".search-result");
      const rowHeight = row?.getBoundingClientRect().height || 32;
      const style = getComputedStyle(dialog);
      const available = window.innerHeight - dialog.getBoundingClientRect().top - 16 -
        (input.current?.closest(".search-input-row")?.getBoundingClientRect().height || 56) -
        (heading.current?.getBoundingClientRect().height || 30) - (actions.current?.getBoundingClientRect().height || 112) -
        parseFloat(style.paddingTop || "0") - parseFloat(style.paddingBottom || "0") - 4;
      setSuggestionLimit(Math.max(0, Math.min(9, Math.floor(available / rowHeight))));
    };
    fit();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    [input.current, actions.current, heading.current].forEach(node => { if (node) observer?.observe(node); });
    window.addEventListener("resize", fit);
    return () => { observer?.disconnect(); window.removeEventListener("resize", fit); };
  }, [search, mode, suggestions.length]);
  useEffect(() => { input.current?.focus(); }, [mode]);
  useEffect(() => { list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" }); }, [selection]);

  const changeMode = (next: typeof mode) => { setResponse(null); setMode(next); setQuery(""); setError(""); setSelection(0); };
  const choose = (item: Conversation | SearchFile) => {
    onClose();
    if ("id" in item) { rememberConversationVisit(item.id, true); onSelect(item); }
    else onFile(item.path);
  };
  const label = mode === "chats" ? "חיפוש בשיחות" : "חיפוש בקבצים ובתוצרים";
  return <Dialog open title={label} className="search-dialog" initialFocus={input} showCloseButton={false} onClose={onClose}>
    <div className="search-input-row">
      <Icon name="search" />
      <Field ref={input} label={label} hiddenLabel placeholder={mode === "chats" ? "חפש בשיחות" : "חפש בקבצים"}
        value={query} autoComplete="off" spellCheck={false} role="combobox" aria-expanded={items.length > 0} aria-controls={listId}
        aria-autocomplete="list" aria-activedescendant={items[selection] ? `${listId}-${selection}` : undefined}
        onChange={event => {
          if (!search && mode === "chats" && event.target.value.trim()) setResponse({ key: "chats:", mode, query: "", items: suggestions.slice(0, suggestionLimit) });
          setQuery(event.target.value); setError(""); setSelection(0);
        }}
        onKeyDown={event => {
          if (event.nativeEvent.isComposing) return;
          if ((event.key === "ArrowDown" || event.key === "ArrowUp") && items.length) {
            event.preventDefault(); setSelection(index => (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length);
          } else if (event.key === "Enter" && items[selection]) { event.preventDefault(); choose(items[selection]); }
        }} />
    </div>
    <div className="search-results" ref={list}>
      <p className="search-section-label" ref={heading}><span>{mode === "files" ? "קבצים ותוצרים" : search ? "שיחות" : "לחזור לשיחה"}</span>
        {pending && items.length > 0 && <span role="status" aria-label="מחפש…" className="search-heading-progress"><Icon name="loader" size={12} className="sds-spin" /></span>}
      </p>
      <div id={listId} role="listbox" aria-label={label} aria-busy={pending}>
        {items.map((item, index) => {
          const chat = "id" in item;
          const title = chat ? item.title : item.name;
          const detail = chat ? search && item.match_kind !== "title" ? item.search_preview || item.preview || "" : "" : item.path;
          return <button type="button" role="option" tabIndex={-1} id={`${listId}-${index}`} key={chat ? item.match_id || item.id : item.path}
            className="search-result" aria-selected={selection === index} onPointerMove={() => setSelection(index)} onClick={() => choose(item)}>
            <span className="search-result-copy"><span className="search-result-title" dir="auto"><Highlight text={title} query={renderedQuery} /></span>
              {detail && <span className="search-result-detail" dir="auto"><Highlight text={detail} query={renderedQuery} /></span>}</span>
          </button>;
        })}
      </div>
      {pending && !items.length && <div className="search-loading" role="status" aria-label="מחפש…"><Icon name="loader" size={24} className="sds-spin" /></div>}
      {!pending && !error && !items.length && <div className="search-feedback" role="status">{search ? "לא נמצאו תוצאות. נסו מילה אחרת." : mode === "files" ? "הקלידו שם קובץ כדי למצוא תוצר של סמארטי" : suggestions.length ? "" : "השיחות שלכם יופיעו כאן"}</div>}
      {error && <div className="search-error" role="alert"><span>{error}</span><Button variant="ghost" icon="refresh" onClick={() => setRetry(value => value + 1)}>ניסיון נוסף</Button></div>}
      {response?.key === key && response.truncated && <p className="search-section-label">יש תוצאות נוספות. נסו חיפוש ממוקד יותר.</p>}
      {!search && <div className="search-quick-actions"><div className="search-priority-actions" ref={actions}><p className="search-section-label">פעולות מהירות</p>
        {mode === "chats" ? <>
          <Button variant="ghost" icon="newChat" onClick={() => { onClose(); onCreate(); }}>שיחה חדשה</Button>
          <Button variant="ghost" icon="file" onClick={() => changeMode("files")}>חיפוש בקבצים</Button>
        </> : <Button variant="ghost" icon="history" onClick={() => changeMode("chats")}>חזרה לחיפוש בשיחות</Button>}
      </div></div>}
    </div>
  </Dialog>;
}
