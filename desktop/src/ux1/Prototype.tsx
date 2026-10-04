import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { artifactName, artifactText, attachmentName, conversations, makeMessages, models, policies, type Message, type RunState, type Theme, richMarkdown, demoProcess } from "./data";
import { Icon, PrototypeTheme } from "./Icon";
import { Button } from "./Button";
import { ProductWorkbench, type WorkspaceRequest, type WorkspaceResource } from "./ProductWorkbench";
import { MessageSurface } from "./MessageSurface";
import { HoverLabel } from "./HoverLabel";
import { ProductManagement } from "./ProductManagement";
import { ModelMenu } from "./ModelMenu";
import { coreApi } from "../coreApi";
import { modelMenuBounds } from "../modelMenuPosition";
import { useRasterIcons } from "./useRasterIcons";
import { type ManagementSection } from "../managementCatalog";
import type { WorkbenchTab } from "../workspaceState";
import smartiLogo from "../../../assets/logo.png";
import { RichMessage } from "../RichMessage";
import "../App.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./prototype.css";

type Chat = { draft: string; attachments: string[]; model: string; reasoning: string; state: RunState; thinking: boolean; messages: Message[] };
type PopupKind = "models" | "policy" | "attachments" | "scenarios" | "history" | "conversation" | "rename" | "guide" | "voice";
type PopupState = { kind: PopupKind; anchor: HTMLButtonElement } | null;
const busy = (state: RunState) => ["running", "waiting_for_approval", "waiting_for_input"].includes(state);
const stateLabels: Record<RunState, string> = { idle: "מוכן להתחיל", running: "מארגן את ההמלצות", waiting_for_approval: "ממתין לאישור שלך", waiting_for_input: "נדרש פרט נוסף", completed: "תוכנית העבודה מוכנה", failed: "הפעולה לא הושלמה", cancelled: "העבודה הופסקה" };


// Development-only dialog: keyboard containment, Escape and return to trigger.
function Popup({ title, anchor, close, children, centered, wide, actions, modal = true }: { title: string; anchor: HTMLButtonElement; close: () => void; children: ReactNode; centered?: boolean; wide?: boolean; actions?: ReactNode; modal?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [placement, setPlacement] = useState(() => ({ rect: anchor.getBoundingClientRect(), width: window.innerWidth, height: window.innerHeight }));
  useLayoutEffect(() => {
    const updatePlacement = () => setPlacement({ rect: anchor.getBoundingClientRect(), width: window.innerWidth, height: window.innerHeight });
    updatePlacement();
    const observer = new ResizeObserver(updatePlacement); observer.observe(anchor);
    window.addEventListener("resize", updatePlacement);
    window.visualViewport?.addEventListener("resize", updatePlacement);
    return () => { observer.disconnect(); window.removeEventListener("resize", updatePlacement); window.visualViewport?.removeEventListener("resize", updatePlacement); };
  }, [anchor]);
  const { rect, width: viewportWidth, height: viewportHeight } = placement;
  const width = Math.min(wide ? 530 : 420, viewportWidth - 24);
  const below = rect.top < viewportHeight / 2;
  const menuBounds = modelMenuBounds(rect, { left: 4, top: document.querySelector(".ux-demo-bar")?.getBoundingClientRect().bottom || 0, width: viewportWidth - 8, height: viewportHeight - (document.querySelector(".ux-demo-bar")?.getBoundingClientRect().bottom || 0) }, viewportHeight);
  const style: CSSProperties = centered ? { width, left: "50%", top: "50%", transform: "translate(-50%, -50%)", maxHeight: viewportHeight - 48 } : wide ? { width, left: menuBounds.left, bottom: viewportHeight - menuBounds.top - menuBounds.height, maxHeight: menuBounds.height } : { width, right: Math.max(12, Math.min(viewportWidth - rect.right, viewportWidth - width - 12)), ...(below ? { top: rect.bottom + 8, maxHeight: viewportHeight - rect.bottom - 24 } : { bottom: viewportHeight - rect.top + 8, maxHeight: rect.top - 24 }) };
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>(centered ? "input" : "input, button:not([disabled]), select")?.focus();
    return () => { if (anchor.isConnected) anchor.focus(); };
  }, [anchor, centered]);
  useEffect(() => {
    if (modal) return;
    const dismiss = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!ref.current?.contains(target) && !anchor.contains(target)) close();
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [anchor, modal, close]);
  return <div className={`ux-popup-layer ${modal ? '' : 'ux-popover-layer'}`} onPointerDown={e => { if (modal && e.target === e.currentTarget) close(); }}>
    <div ref={ref} className={`ux-popup ${wide ? "ux-popup-models" : ""} ${centered ? "ux-popup-centered" : ""}`} role="dialog" aria-modal={modal} aria-label={title} style={style} onKeyDown={e => {
      if (e.key === "Escape") { e.stopPropagation(); close(); }
      if (modal && e.key === "Tab") {
        const focusable = Array.from(ref.current!.querySelectorAll<HTMLElement>("button:not([disabled]), input, select, textarea, [tabindex='0']"));
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }}>
      <div className="ux-popup-title"><strong>{title}</strong><div>{actions}{modal && <Button icon="close" label="סגירת התפריט" onClick={close} />}</div></div>{children}
    </div>
  </div>;
}

export function Prototype() {
  const initialScreen = new URLSearchParams(location.search).get("screen");
  const [theme, setTheme] = useState<Theme>(() => new URLSearchParams(location.search).get("theme") === "dark" ? "dark" : "light");
  useRasterIcons(theme);
  const [reduced, setReduced] = useState(false);
  const [compact, setCompact] = useState(false);
  const [count, setCount] = useState(200);
  const [active, setActive] = useState("community");
  const [conversationList, setConversationList] = useState(conversations.map(c => ({ ...c, pinned: c.id === "community" })));
  const [conversationTarget, setConversationTarget] = useState("community");
  const [renameDraft, setRenameDraft] = useState("");
  const [voiceDraft, setVoiceDraft] = useState("אני רוצה לסכם את תוכנית העבודה וליצור מסמך המלצות.");
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [managementSection, setManagementSection] = useState<ManagementSection>("settings_ai");
  const [workbenchRequest, setWorkbenchRequest] = useState<WorkspaceRequest>({ kind: null, revision: 0 });
  const [globalPolicy, setGlobalPolicy] = useState("balanced");
  const [modelDelay, setModelDelay] = useState(5000);
  const [fastMode, setFastMode] = useState(false);
  const [chats, setChats] = useState<Record<string, Chat>>(() => Object.fromEntries(conversations.map(c => [c.id, { draft: "", attachments: c.id === "code" ? [attachmentName] : [], model: c.id === "code" ? "codex" : "gpt", reasoning: "רגילה", thinking: false, state: c.state, messages: makeMessages(c.id, 200) }])));
  const [popup, setPopup] = useState<PopupState>(null);
  const modalPopup = !!popup && !['models', 'policy', 'attachments', 'conversation', 'history'].includes(popup.kind);
  const [query, setQuery] = useState("");
  const [favorites, setFavorites] = useState<string[]>(["gpt", "codex", "gemini", "local"]);
  const [page, setPage] = useState<"chat" | "settings">(initialScreen === "settings" ? "settings" : "chat");
  const [artifactOpen, setArtifactOpen] = useState(initialScreen === "split");
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [documentText, setDocumentText] = useState(artifactText);
  const [saveState, setSaveState] = useState<"clean" | "dirty" | "saving" | "failed" | "saved">("clean");
  const [failSave, setFailSave] = useState(true);
  const [providerConnected, setProviderConnected] = useState(false);
  const [notice, setNotice] = useState("");
  const [newContent, setNewContent] = useState(false);
  const [workWidth, setWorkWidth] = useState(1000);
  const [artifactWidth, setArtifactWidth] = useState(520);
  const workRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const artifactTrigger = useRef<HTMLButtonElement>(null);
  const artifactOrigin = useRef<HTMLElement | null>(null);
  const artifactClose = useRef<HTMLButtonElement>(null);
  const settingsTrigger = useRef<HTMLButtonElement>(null);
  const pendingNew = useRef<string | null>(null);
  const newId = useRef(0);
  const followEnd = useRef(true);
  const scrollPositions = useRef<Record<string, number>>({});
  const lastContent = useRef({ active, length: chats[active].messages.length });
  const runGeneration = useRef<Record<string, number>>({});
  const timers = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  const chat = chats[active];
  const singleArtifact = artifactOpen && (expanded || workWidth < 940);
  const selectedModel = models.find(m => m.id === chat.model)!;
  const connected = selectedModel.connected || (selectedModel.providerId === "gemini" && providerConnected);
  const modelLabel = selectedModel.providerId === "openai_codex_signin" ? "Codex · חשיבה" : selectedModel.providerId === "local" ? "Local" : selectedModel.providerId === "gemini" ? "Gemini" : selectedModel.providerId === "openai" ? "GPT" : selectedModel.provider;
  const policy = policies.find(p => p.id === globalPolicy)!;
  const update = (patch: Partial<Chat>, id = active) => setChats(prev => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  function later(action: () => void, ms: number) {
    const timer = setTimeout(() => { timers.current.delete(timer); action(); }, ms);
    timers.current.add(timer);
  }
  useEffect(() => () => { timers.current.forEach(clearTimeout); }, []);
  useEffect(() => {
    const feedback = (event: Event) => setNotice(String((event as CustomEvent).detail));
    const onSettings = () => setProviderConnected(true);
    window.addEventListener("ux1-demo-feedback", feedback);
    window.addEventListener("ux1-provider-connected", onSettings);
    return () => { window.removeEventListener("ux1-demo-feedback", feedback); window.removeEventListener("ux1-provider-connected", onSettings); };
  }, []);
  useLayoutEffect(() => {
    const observer = new ResizeObserver(entries => setWorkWidth(entries[0].contentRect.width));
    if (workRef.current) observer.observe(workRef.current);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => {
    const viewport = scrollRef.current;
    if (!viewport) return;
    const messages = viewport.querySelectorAll<HTMLElement>(".ux-message");
    const latest = messages[messages.length - 1];
    viewport.scrollTop = scrollPositions.current[active] ?? (latest ? latest.offsetTop - viewport.offsetTop - 20 : 0);
    followEnd.current = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop < 60;
    setNewContent(false);
  }, [active, count]); // Draft/scroll are per conversation; content is never remounted for panel/settings.
  useLayoutEffect(() => {
    const previous = lastContent.current;
    lastContent.current = { active, length: chat.messages.length };
    if (previous.active !== active || previous.length === chat.messages.length) return;
    if (followEnd.current) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    else setNewContent(true);
  }, [active, chat.messages.length]);
  useLayoutEffect(() => {
    if (page === "chat" && !singleArtifact && followEnd.current) {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    }
  }, [workWidth, artifactOpen, singleArtifact, page]);
  useEffect(() => {
    document.documentElement.style.colorScheme = theme;
  }, [theme]);
  useEffect(() => {
    const activity = scrollRef.current?.querySelector('.ux-activity');
    if (!activity || page !== 'chat') return;
    let frame = 0;
    const observer = new MutationObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (followEnd.current) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
      });
    });
    observer.observe(activity, { childList: true, subtree: true });
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [active, page, singleArtifact]);
  useEffect(() => {
    void coreApi<{ values: { autonomy_mode?: string } }>("GET", "/v2/settings").then(result => setGlobalPolicy(result.values.autonomy_mode || "balanced"));
  }, [page]);
  function chooseConversation(id: string) { setActive(id); setPopup(null); }
  function newConversation() {
    const existing = pendingNew.current;
    const id = existing && !chats[existing]?.messages.length ? existing : `demo-${Date.now()}-${++newId.current}`;
    if (id !== existing) setChats(prev => ({ ...prev, [id]: { draft: "", attachments: [], model: chat.model, reasoning: chat.reasoning, thinking: false, state: "idle", messages: [] } }));
    pendingNew.current = id;
    setActive(id); setPopup(null);
    requestAnimationFrame(() => draftRef.current?.focus());
  }
  function conversationActions(id: string, anchor: HTMLButtonElement) {
    const conversation = conversationList.find(c => c.id === id);
    if (!conversation) return;
    setConversationTarget(id); setRenameDraft(conversation.title); open("conversation", anchor);
  }
  function deleteConversation(id: string) {
    const remaining = conversationList.filter(c => c.id !== id);
    setConversationList(remaining);
    if (active === id) { if (remaining.length) setActive(remaining[0].id); else newConversation(); }
    setPopup(null);
  }
  function exportConversation(id: string) {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ title: conversationList.find(c => c.id === id)?.title, messages: chats[id].messages, demo: true }, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "smarti-conversation.json"; a.click(); later(() => URL.revokeObjectURL(url), 1000);
  }
  function openWorkbench(kind: WorkbenchTab | null = null, resource?: WorkspaceResource) { setWorkbenchRequest(prev => ({ kind, resource, revision: prev.revision + 1 })); setArtifactOpen(true); setPage("chat"); }
  function openManagement(section: ManagementSection = "settings_ai") { setManagementSection(section); setPage("settings"); }
  async function choosePolicy(id: string) {
    try {
      await coreApi("PATCH", "/v2/settings", { values: { autonomy_mode: id, custom_permission_profile_enabled: id === "custom" } });
      setGlobalPolicy(id); setPopup(null);
      if (id === "custom") openManagement("settings_security");
    } catch { setNotice("שינוי מדיניות הבטיחות נכשל. אפשר לנסות שוב."); }
  }
  function open(kind: PopupKind, anchor: HTMLButtonElement) {
    if (popup?.kind === kind && popup.anchor === anchor) { setPopup(null); return; }
    setPopup({ kind, anchor });
    if (kind === "models") void coreApi<{ values: { favorite_models?: { provider: string; model: string }[] } }>("GET", "/v2/settings").then(result => {
      const saved = result.values.favorite_models ?? [];
      setFavorites(saved.map(item => models.find(model => item.provider === model.providerId && item.model === model.modelKey)?.id).filter((id): id is string => !!id));
    }).catch(() => setNotice("לא ניתן לטעון את מועדפים. אפשר לפתוח שוב את התפריט."));
  }
  function showArtifact(event?: React.MouseEvent<HTMLButtonElement>) { artifactOrigin.current = event?.currentTarget ?? artifactTrigger.current; openWorkbench(); }
  function closeArtifact() { setArtifactOpen(false); setExpanded(false); requestAnimationFrame(() => (artifactOrigin.current?.isConnected ? artifactOrigin.current : artifactTrigger.current)?.focus()); }
  useEffect(() => {
    if (singleArtifact && page === "chat") artifactClose.current?.focus();
  }, [singleArtifact, page]);
  function setScenario(state: RunState) {
    const id = active, generation = runGeneration.current[id] = (runGeneration.current[id] ?? 0) + 1;
    update({ state, thinking: state === "running" }); setPopup(null);
    if (state === "running") later(() => setChats(prev => runGeneration.current[id] === generation ? { ...prev, [id]: { ...prev[id], thinking: false } } : prev), modelDelay);
  }
  function cancel() { runGeneration.current[active] = (runGeneration.current[active] ?? 0) + 1; update({ state: "cancelled", thinking: false }); }
  function send() {
    if (busy(chat.state) || !connected || (!chat.draft.trim() && !chat.attachments.length)) return;
    const id = active;
    const generation = runGeneration.current[id] = (runGeneration.current[id] ?? 0) + 1;
    const text = chat.draft.trim() || "בדוק את המסמך המצורף.";
    if (!conversationList.some(c => c.id === id)) setConversationList(prev => [{ id, title: text.replace(/\s+/g, " ").slice(0, 90), detail: "היום", state: "running", pinned: false }, ...prev]);
    if (pendingNew.current === id) pendingNew.current = null;
    followEnd.current = true;
    update({ draft: "", attachments: [], state: "running", thinking: true, messages: [...chat.messages, { id: `${id}-${generation}`, role: "user", text, attachments: chat.attachments, enter: true }] });
    later(() => setChats(prev => ({ ...prev, [id]: { ...prev[id], messages: prev[id].messages.map(message => message.id === `${id}-${generation}` ? { ...message, enter: false } : message) } })), 240);
    later(() => setChats(prev => runGeneration.current[id] === generation && prev[id].state === "running" ? { ...prev, [id]: { ...prev[id], thinking: false } } : prev), modelDelay);
    later(() => setChats(prev => runGeneration.current[id] !== generation || prev[id].state !== "running" ? prev : ({ ...prev, [id]: { ...prev[id], state: "waiting_for_approval", thinking: false } })), modelDelay + 1800);
  }
  function approve() {
    const id = active;
    const generation = runGeneration.current[id] = (runGeneration.current[id] ?? 0) + 1;
    update({ state: "running", thinking: false });
    later(() => setChats(prev => runGeneration.current[id] !== generation || prev[id].state !== "running" ? prev : ({ ...prev, [id]: { ...prev[id], state: "completed", thinking: false, messages: [...prev[id].messages, { id: `${id}-answer-${Date.now()}`, role: "assistant", text: "הפעולה אושרה. הכנתי מסמך עם ההמלצות ומוקדי העבודה.", rich: true }] } })), modelDelay);
  }
  function saveDocument() {
    if (saveState === "saving") return;
    setSaveState("saving");
    later(() => setSaveState(failSave ? "failed" : "saved"), 600);
  }
  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); } catch { setNotice("הדפדפן חסם העתקה. אפשר לבחור ולהעתיק את הטקסט ידנית."); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([documentText], { type: "text/markdown;charset=utf-8" }));
    const a = document.createElement("a"); a.href = url; a.download = artifactName; a.click();
    later(() => URL.revokeObjectURL(url), 1000);
  }
  function changeCount(next: number) {
    scrollPositions.current = {};
    setCount(next);
    setChats(prev => Object.fromEntries(Object.entries(prev).map(([id, c]) => [id, c.messages.length ? { ...c, messages: makeMessages(id, next) } : c])));
  }
  const history = <div className="ux-history"><Button icon="newChat" className="ux-new-chat" aria-label="שיחה חדשה" onClick={newConversation}>שיחה חדשה</Button><label className="ux-search"><Icon name="search" /><input aria-label="חיפוש בשיחות" placeholder="חיפוש בשיחות" value={query} onChange={e => setQuery(e.target.value)} /></label><div className="ux-history-group">סביבת עבודה אישית</div><div className="ux-history-scroll"><nav aria-label="שיחות">{conversationList.filter(c => `${c.title} ${c.detail} ${chats[c.id].messages.map(m => m.text).join(" ")}`.toLowerCase().includes(query.toLowerCase())).map(c => <div key={c.id} className={`ux-conversation-row ${c.id === active ? "is-active" : ""}`}><button className={`ux-conversation ${c.id === active ? "is-active" : ""}`} aria-current={c.id === active ? "page" : undefined} onClick={() => chooseConversation(c.id)}><HoverLabel text={c.title} />{c.pinned && <Icon name="pin" size={14} />}{busy(chats[c.id].state) && <span className="ux-status-dot" />}</button><Button icon="more" className="ux-conversation-menu-trigger" label={`פעולות עבור ${c.title}`} onClick={e => conversationActions(c.id, e.currentTarget)} /></div>)}</nav></div></div>;

  return <PrototypeTheme.Provider value={theme}><div className={`ux-prototype ${compact ? "ux-compact" : ""} ${reduced ? "ux-reduced" : ""}`} data-theme={theme} dir="rtl">
    <div className="ux-demo-bar" inert={modalPopup}><div><Button icon="info" label="מדריך התנסות" onClick={e => open("guide", e.currentTarget)}>העיצוב החדש</Button><Button icon={theme === "light" ? "moon" : "sun"} label={theme === "light" ? "מעבר למצב כהה" : "מעבר למצב בהיר"} onClick={() => setTheme(theme === "light" ? "dark" : "light")} /><Button icon="more" label="תרחישי התנסות" onClick={e => open("scenarios", e.currentTarget)}>תרחישים</Button></div></div>
    {notice && <div className="ux-notice" role="status"><span>{notice}</span><Button icon="close" label="סגירת הודעה" onClick={() => setNotice("")} /></div>}
    <div className={`ux-shell ${drawerOpen ? "" : "ux-rail"}`} data-page={page} inert={modalPopup}>
      <aside className="ux-sidebar" hidden={page === "settings"}><div className="ux-brand"><button type="button" className="ux-brand-reopen" aria-label={drawerOpen ? "כיווץ סרגל השיחות" : "הרחבת סרגל השיחות"} onClick={() => setDrawerOpen(!drawerOpen)}><img className="ux-brand-logo" src={smartiLogo} alt="סמארטי" /><Icon name="panel" /></button><span>Smarti<span className="ux-brand-sub">מרחב לרעיונות ולעבודה</span></span></div><div className="ux-history-content">{history}</div><div className="ux-sidebar-bottom"><Button icon="tasks" label="מרכז משימות" onClick={() => openManagement("tasks")} /><Button icon="memory" label="זיכרונות" onClick={() => openManagement("memory")} /><Button icon="tools" label="כלים וחיבורים" onClick={() => openManagement("tools")} /><Button icon="usage" label="נתוני שימוש" onClick={() => openManagement("usage")} /><Button ref={settingsTrigger} className="ux-settings-trigger" aria-label="הגדרות וספקים" icon="settings" onClick={() => openManagement()}>הגדרות וספקים</Button></div></aside>
      <main className="ux-main">
        <header className="ux-topbar"><div>{page === "settings" ? <Button icon="forward" onClick={() => { setPage("chat"); requestAnimationFrame(() => settingsTrigger.current?.focus()); }}>חזרה לשיחה</Button> : <><Button icon="panel" label="פתיחת רשימת שיחות" className="ux-mobile-history" onClick={e => open("history", e.currentTarget)} /><strong>{conversationList.find(c => c.id === active)?.title || "שיחה חדשה"}</strong><span className="ux-mode-label">{singleArtifact ? "קריאה מורחבת" : artifactOpen ? "עבודה משולבת" : "שיחה"}</span></>}</div><div>{page === "chat" && <><Button icon="more" className="ux-conversation-menu-trigger" label="פעולות שיחה" disabled={!conversationList.some(c => c.id === active)} onClick={e => conversationActions(active, e.currentTarget)} /><Button icon="panel" label={artifactOpen ? "סגירת סביבת העבודה" : "פתיחת סביבת העבודה"} aria-pressed={artifactOpen} ref={artifactTrigger} onClick={event => artifactOpen ? closeArtifact() : showArtifact(event)} /></>}</div></header>
        <div className="ux-work-area" ref={workRef} hidden={page !== "chat"} data-artifact={artifactOpen} data-single={singleArtifact} style={{ "--artifact-width": `${Math.max(350, Math.min(artifactWidth, workWidth - 480))}px` } as CSSProperties}>
          <section className="ux-chat" aria-label="שיחה" hidden={singleArtifact}>
            {artifactOpen && !singleArtifact && <div className="ux-chat-mode"><Icon name="spark" size={16} />שיחה</div>}
            <div className="ux-messages" ref={scrollRef} onScroll={e => {
              if (page !== "chat" || singleArtifact) return;
              const el = e.currentTarget; followEnd.current = el.scrollHeight - el.clientHeight - el.scrollTop < 60;
              scrollPositions.current[active] = el.scrollTop; if (followEnd.current) setNewContent(false);
            }}>
              <div className="ux-conversation-intro" hidden={chat.messages.length > 0}><span className="ux-eyebrow">מרעיון לתוכנית</span><h1>במה נעבוד היום?</h1><p>כתוב בקשה, ונבנה יחד את הצעד הבא.</p></div>
              {chat.messages.map(message => <MessageSurface role={message.role} enter={message.enter} key={message.id} references={message.rich ? <div className="ux-workspace-references" aria-label="תוכן בסביבת העבודה"><Button className="ux-workspace-reference" icon="file" onClick={() => openWorkbench("artifacts", { id: `${active}-recommendations`, title: "תוכנית עבודה" })}><span><strong>תוכנית העבודה למרכז הקהילתי</strong><small>מסמך Markdown · פתיחה בסביבת העבודה</small></span><Icon name="chevron" /></Button><Button className="ux-workspace-reference" icon="browser" onClick={() => openWorkbench("browser", { id: "demo-community-site", title: "המרכז הקהילתי", url: "https://community.example/" })}><span><strong>המרכז הקהילתי</strong><small>דף שנבדק בדפדפן · פתיחה בסביבת העבודה</small></span><Icon name="chevron" /></Button></div> : undefined}>
<RichMessage theme={theme} message={{ role: message.role, content: message.text + (message.rich ? richMarkdown : ""), attachments: message.attachments?.map(name => ({ name, kind: "file", size: 8192 })), metadata: message.rich ? { agent_process: demoProcess(), memory_updated: true, canvases: [{ id: "demo-plan", title: "תוכנית עבודה למרכז הקהילתי", kind: "markdown" }] } : undefined }} onOpenCanvas={canvas => openWorkbench("canvas", { id: canvas, title: "קנבס" })} />
</MessageSurface>)}
              <div className="ux-activity" data-state={chat.state} aria-live="polite" hidden={chat.state === "idle" || chat.state === "completed"}><div className="ux-activity-summary" hidden={chat.thinking}><span className={`ux-state-mark ${busy(chat.state) ? "is-busy" : ""}`}><Icon name={chat.state === "completed" ? "check" : "spark"} /></span><strong>{stateLabels[chat.state]}</strong></div>
                {chat.state !== "idle" ? <RichMessage key={active} theme={theme} active={chat.state === "running"} runStatus={chat.state} message={{ role: "assistant", content: "", metadata: { ...(chat.thinking ? {} : { agent_process: demoProcess(chat.state) }), run_id: "demo-active" } }} /> : null}
                {chat.state === "waiting_for_approval" && <div className="ux-approval"><span className="ux-eyebrow">נדרש אישור</span><h3>ליצור את מסמך תוכנית העבודה?</h3><p>הפעולה תיצור מסמך בסביבת העבודה. אפשר לבדוק את תוכנו לפני הורדה.</p><div className="ux-resource" dir="ltr">workspace:/community/plan-2027.md</div><div className="ux-action-row"><Button className="ux-primary" icon="check" onClick={approve}>אישור לפעולה הזו</Button><Button onClick={cancel}>דחייה</Button></div></div>}
                {chat.state === "waiting_for_input" && <div className="ux-approval"><h3>כמה מפגשים נכלול בתוכנית?</h3><label className="ux-inline-field">מספר מפגשים<select aria-label="מספר מפגשים"><option>2</option><option>4</option><option>6</option></select></label><Button onClick={approve}>המשך</Button></div>}
                {chat.state === "failed" && <div role="alert" className="ux-error">הספק לא הגיב. הטיוטה נשמרת; אפשר לנסות שוב.<Button onClick={() => update({ state: "idle" })}>ניסיון חוזר</Button></div>}
              </div>
            </div>
            {newContent && <Button className="ux-new-content" onClick={() => { followEnd.current = true; scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }); setNewContent(false); }}>לתוכן החדש ↓</Button>}
            <div className="ux-composer-area">
              <div className="ux-composer">
                {chat.attachments.length > 0 && <div className="ux-attachments">{chat.attachments.map(name => <div className="ux-attachment" key={name}><Icon name="file" /><span title={name}><bdi>{name}</bdi></span><Button icon="close" label={`הסרת ${name}`} onClick={() => update({ attachments: chat.attachments.filter(a => a !== name) })} /></div>)}</div>}
                {!connected && <div className="ux-error" role="alert">הספק מנותק. בחר מודל מחובר או פתח את ההגדרות.<Button onClick={() => openManagement()}>ספקים</Button></div>}
                <textarea ref={draftRef} aria-label="כתיבת הודעה" rows={2} placeholder="על מה נעבוד עכשיו?" value={chat.draft} onChange={e => update({ draft: e.target.value })} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }} />
                <div className="ux-composer-controls">
                  <div className="ux-primary-actions">{busy(chat.state) ? <Button icon="stop" label="עצירה" className="ux-send" onClick={cancel} /> : chat.draft.trim() || chat.attachments.length ? <Button icon="send" label="שליחת הודעה" className="ux-send" disabled={!connected} onClick={send} /> : <Button icon="mic" label="הכתבה" className="ux-send" onClick={e => open("voice", e.currentTarget)} />}</div>
                  <div className="ux-selectors" dir="ltr"><Button className="ux-model-trigger" aria-haspopup="dialog" icon="spark" title={selectedModel.name} onClick={e => open("models", e.currentTarget)}><Icon name="chevron" size={14} /><bdi>{modelLabel}</bdi></Button><Button className="ux-policy-trigger" aria-haspopup="dialog" icon="shield" title="מדיניות הבטיחות הכללית של סמארטי" onClick={e => open("policy", e.currentTarget)}>{policy.name}</Button></div>
                  <Button icon="plus" label="צירוף קובץ" aria-haspopup="dialog" onClick={e => open("attachments", e.currentTarget)} />
                </div>
              </div>{selectedModel.providerId === "local" && <label className="ux-fast-mode"><input type="checkbox" checked={fastMode} onChange={e => setFastMode(e.target.checked)} /><Icon name="activity" size={14} /> Fast mode</label>}<div className="ux-composer-hint">Enter לשליחה, Shift+Enter לשורה חדשה</div>
            </div>
          </section>
          {artifactOpen && !singleArtifact && <div className="ux-splitter" role="separator" aria-label="שינוי רוחב סביבת העבודה" aria-orientation="vertical" aria-valuemin={350} aria-valuemax={Math.max(350, workWidth - 480)} aria-valuenow={Math.round(Math.max(350, Math.min(artifactWidth, workWidth - 480)))} tabIndex={0} onKeyDown={e => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) { e.preventDefault(); setArtifactWidth(e.key === "Home" ? 350 : e.key === "End" ? workWidth - 480 : Math.max(350, Math.min(workWidth - 480, artifactWidth + (e.key === "ArrowRight" ? 24 : -24)))); } }} onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) { const left = workRef.current!.getBoundingClientRect().left; setArtifactWidth(Math.max(350, Math.min(workWidth - 480, e.clientX - left))); } }} onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />}
          <section className="ux-artifact" hidden={!artifactOpen} aria-label="סביבת העבודה"><ProductWorkbench visible={artifactOpen && page === "chat"} request={workbenchRequest} expansionRef={artifactClose} expanded={expanded} toggleExpanded={() => setExpanded(!expanded)} sessionId={active} onCanvasAction={text => { update({ draft: text }); closeArtifact(); }}>{showList => <>
            <header className="ux-document-bar"><div className="ux-artifact-title"><span><strong>תוכנית עבודה</strong><small title={artifactName}><bdi>{artifactName}</bdi></small></span></div><div className="ux-action-row"><Button icon={editing ? "file" : "rename"} label={editing ? "קריאת מסמך" : "עריכת מסמך"} aria-pressed={editing} onClick={() => setEditing(!editing)}>{editing ? "קריאה" : "עריכה"}</Button><details className="ux-document-actions" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) e.currentTarget.open = false; }} onKeyDown={e => { if (e.key === "Escape") { e.currentTarget.open = false; e.currentTarget.querySelector("summary")?.focus(); } }}><summary aria-label="פעולות מסמך" title="פעולות מסמך"><Icon name="more" /></summary><div><Button icon="layers" label="רשימת תוצרים" onClick={event => { showList(); event.currentTarget.closest("details")?.removeAttribute("open"); }}>רשימת תוצרים</Button><Button icon="copy" label="העתקת מסמך" onClick={e => { void copy(documentText); e.currentTarget.closest("details")?.removeAttribute("open"); }}>העתקה</Button><Button icon="download" label="הורדת מסמך" onClick={e => { download(); e.currentTarget.closest("details")?.removeAttribute("open"); }}>הורדה</Button></div></details></div></header>
            {editing ? <textarea className="ux-document-editor" aria-label="עריכת מסמך" value={documentText} onChange={e => { setDocumentText(e.target.value); setSaveState("dirty"); }} /> : <div className="ux-document-scroll"><div className="ux-document"><div className="ux-document-kicker">COMMUNITY / 2027</div><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{ a: ({ children }) => <span>{children}</span>, p: ({ children }) => <p dir="auto">{children}</p>, pre: ({ children }) => <pre dir="ltr">{children}</pre> }}>{documentText}</ReactMarkdown></div></div>}
            {(editing || ["dirty", "saving", "failed"].includes(saveState)) && <footer className="ux-artifact-footer"><span aria-live="polite">{saveState === "clean" ? "" : saveState === "dirty" ? "שינויים שטרם נשמרו" : saveState === "saving" ? "שומר…" : saveState === "saved" ? "" : "השמירה נכשלה"}</span><Button disabled={saveState === "saving"} onClick={saveDocument}>{saveState === "failed" ? "ניסיון חוזר" : "שמירה"}</Button></footer>}
            {saveState === "failed" && <div className="ux-error" role="alert">השמירה נכשלה. הטקסט נשמר לעריכה ולניסיון חוזר.<Button onClick={() => { setFailSave(false); setSaveState("dirty"); }}>אפשר ניסיון מוצלח</Button></div>}
          </>}</ProductWorkbench></section>
        </div>
        {page === "settings" && <div className="ux-management-root"><ProductManagement initial={managementSection} theme={theme} setTheme={value => setTheme(value === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : value)} openWorkbench={openWorkbench} /></div>}
      </main>
    </div>

    {popup && <Popup modal={modalPopup} key={popup.kind} centered={popup.kind === "rename"} wide={popup.kind === "models"} actions={popup.kind === "models" ? <Button icon="settings" label="ניהול ספקים ומועדפים" onClick={() => { setPopup(null); openManagement(); }} /> : undefined} title={{ models: "מודלים מועדפים", rename: "שם השיחה", policy: "מדיניות הבטיחות של סמארטי", attachments: "צירוף קובץ", scenarios: "תרחישי התנסות", history: "שיחות", conversation: "פעולות שיחה", guide: "העיצוב החדש — להתנסות", voice: "הכתבה" }[popup.kind]} anchor={popup.anchor} close={() => setPopup(null)}>
      {popup.kind === "history" && <div className="ux-history-popup">{history}<Button icon="settings" onClick={() => { setPopup(null); openManagement(); }}>הגדרות וספקים</Button></div>}
      {popup.kind === "guide" && <div className="ux-guide-content"><p>שלושה מצבי עבודה, עם אותה שפה: משטחים ניטרליים, טקסט קריא, הפרדה עדינה והדגשה כחולה לפעולה ולבחירה.</p><ol><li><strong>שיחה:</strong> מרחב רציף לקריאה ולכתיבה. הפעילות מתקפלת בשלוש רמות: ריצה, קבוצת כלים וכלי — עם כל הדיווחים, הקלט והפלט. קוד ניתן להעתקה ולהורדה.</li><li><strong>עבודה משולבת:</strong> שיחה מימין וסביבת עבודה משמאל, כל אחת באזור עצמאי. פתיחה רגילה מציגה מסך בחירה לדפדפן, קבצים, מסוף ותוצרים. קנבס נפתח מההפניה בצ׳אט. סרגל אחד ללשוניות וסגירה; פעולות המסמך צמודות למסמך.</li><li><strong>הגדרות:</strong> מסך ניהול עצמאי, עם כותרת אחת וקבוצות לפי נושא. חיפוש עוזר להגיע גם להגדרות המתקדמות. אותה שפה ממשיכה במשימות, שימוש ואבחון.</li></ol><div className="ux-guide-routes"><Button icon="spark" onClick={() => { setPopup(null); setPage("chat"); setArtifactOpen(false); setExpanded(false); }}>1 · התנסות בשיחה</Button><Button icon="panel" onClick={() => { setPopup(null); setExpanded(false); openWorkbench(); }}>2 · התנסות בעבודה משולבת</Button><Button icon="settings" onClick={() => { setPopup(null); openManagement(); }}>3 · התנסות בהגדרות</Button><Button icon="newChat" onClick={newConversation}>ניסיון בשיחה חדשה</Button></div><p className="ux-popup-note"></p></div>}
      {popup.kind === "voice" && <><p className="ux-popup-note">אפשר לערוך את התמלול ולשלב בטיוטה.</p><textarea aria-label="תמלול" value={voiceDraft} onChange={e => setVoiceDraft(e.target.value)} /><Button icon="mic" onClick={() => { update({ draft: `${chat.draft}${chat.draft ? "\n" : ""}${voiceDraft}` }); setPopup(null); }}>הוספת התמלול לטיוטה</Button></>}
      {popup.kind === "conversation" && <div className="ux-conversation-menu"><Button icon="rename" onClick={() => setPopup({ kind: "rename", anchor: popup.anchor })}>שינוי שם</Button><Button icon="pin" onClick={() => { setConversationList(list => list.map(c => c.id === conversationTarget ? { ...c, pinned: !c.pinned } : c)); setPopup(null); }}>{conversationList.find(c => c.id === conversationTarget)?.pinned ? "ביטול הצמדה" : "הצמדה"}</Button><Button icon="export" onClick={() => { exportConversation(conversationTarget); setPopup(null); }}>ייצוא שיחה ל־JSON</Button><Button icon="trash" onClick={() => deleteConversation(conversationTarget)}>מחיקת שיחה</Button></div>}
      {popup.kind === "rename" && <form className="ux-rename-form" onSubmit={event => { event.preventDefault(); if (!renameDraft.trim()) return; setConversationList(list => list.map(c => c.id === conversationTarget ? { ...c, title: renameDraft.trim() } : c)); setPopup(null); }}><label>שם השיחה<input aria-label="שם שיחה" value={renameDraft} onChange={event => setRenameDraft(event.target.value)} /></label><div className="ux-action-row"><Button onClick={() => setPopup(null)}>ביטול</Button><Button type="submit" className="ux-primary" disabled={!renameDraft.trim()}>שמירה</Button></div></form>}
      {popup.kind === "models" && <ModelMenu selected={chat.model} favorites={favorites} reasoning={chat.reasoning} onSelect={id => { update({ model: id }); setPopup(null); }} onReasoning={reasoning => update({ reasoning })} />}
      {popup.kind === "policy" && <><p className="ux-popup-note">מדיניות כללית לכל סמארטי</p>{policies.map(p => <button className="ux-menu-option" key={p.id} aria-pressed={globalPolicy === p.id} onClick={() => void choosePolicy(p.id)}><Icon name="shield" /><span><strong>{p.name}</strong><small>{p.detail}</small></span>{globalPolicy === p.id && <Icon name="check" />}</button>)}</>}
      {popup.kind === "attachments" && <><p className="ux-popup-note">בחר קובץ לצירוף.</p><Button icon="file" className="ux-attachment-choice" onClick={() => { update({ attachments: [attachmentName] }); setPopup(null); }}><bdi>{attachmentName}</bdi></Button></>}
      {popup.kind === "scenarios" && <><p className="ux-popup-note"></p><div className="ux-scenario-grid">{(["idle", "running", "waiting_for_approval", "waiting_for_input", "completed", "failed", "cancelled"] as RunState[]).map(state => <Button key={state} aria-pressed={chat.state === state} onClick={() => setScenario(state)}>{stateLabels[state]}</Button>)}</div><label className="ux-inline-field">השהיית מודל<select aria-label="השהיית מודל" value={modelDelay} onChange={event => setModelDelay(Number(event.target.value))}><option value={1000}>שנייה</option><option value={5000}>5 שניות</option><option value={12000}>12 שניות</option><option value={30000}>30 שניות</option></select></label><label className="ux-inline-field">תוכן עמוס<select aria-label="כמות הודעות" value={count} onChange={e => changeCount(Number(e.target.value))}><option value={200}>200 הודעות</option><option value={1000}>1,000 הודעות</option></select></label><label className="ux-inline-field">כשל שמירה<input type="checkbox" checked={failSave} onChange={e => setFailSave(e.target.checked)} /></label><label className="ux-inline-field">צמצום תנועה<input type="checkbox" checked={reduced} onChange={e => setReduced(e.target.checked)} /></label><label className="ux-inline-field">תצוגה קומפקטית<input type="checkbox" checked={compact} onChange={e => setCompact(e.target.checked)} /></label></>}
    </Popup>}
  </div></PrototypeTheme.Provider>;
}
