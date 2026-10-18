import { useId, useLayoutEffect, useRef, useState } from "react";
import type { Conversation } from "./chatTypes";
import type { ManagementSection } from "./managementCatalog";
import { activityState } from "./legacyUiParity";
import { recentConversations } from "./chatState";
import { HoverLabel, Icon, IconButton, Menu, type MenuItem } from "./design-system";
import { useConversationDrawerMotion } from "./workspaceMotion";

export function conversationActions(item: Conversation, handlers: {
  pin: (item: Conversation) => void; rename: (item: Conversation) => void;
  export: (item: Conversation) => void; remove: (item: Conversation) => void;
}): MenuItem[] {
  return [
    { id: "pin", label: item.pinned ? "בטל הצמדה" : "הצמד שיחה", icon: "pin", onSelect: () => handlers.pin(item) },
    { id: "rename", label: "שנה שם", icon: "rename", onSelect: () => handlers.rename(item) },
    { id: "export", label: "יצוא JSON", icon: "export", onSelect: () => handlers.export(item) },
    { id: "delete", label: "מחק שיחה", icon: "trash", tone: "danger", disabled: item.is_busy, onSelect: () => handlers.remove(item) },
  ];
}

export function ChatSidebar({ open, resizing = false, logo, conversations, activeId, loading, error, unread,
  onToggle, onCreate, onSearch, onSelect, actions, onManagement }: {
  open: boolean; resizing?: boolean; logo: string; conversations: Conversation[]; activeId: string;
  loading: boolean; error: string; unread: (id: string) => number;
  onToggle: () => void; onCreate: () => void; onSearch: () => void;
  onSelect: (id: string) => void; actions: (item: Conversation) => MenuItem[];
  onManagement: (section: ManagementSection, trigger?: HTMLElement) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [scrolled, setScrolled] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const listId = useId();
  const recent = recentConversations(conversations);
  const { ref, visibleOpen } = useConversationDrawerMotion(open, resizing);
  useLayoutEffect(() => { setScrolled((list.current?.scrollTop || 0) > 0); }, [open, expanded, recent.length]);
  return <aside ref={ref} className={`conversation-drawer ${visibleOpen ? "is-open" : "is-rail"}${visibleOpen && !open ? " is-closing" : ""}`} data-state={open ? "open" : "closed"} aria-label="שיחות">
    <div className="drawer-brand-row"><button className="drawer-brand" type="button" aria-expanded={open} aria-label={open ? "כיווץ תפריט הצד" : "פתיחת תפריט הצד"} onClick={onToggle}>
      <span className="drawer-brand-mark"><img src={logo} alt="" /><Icon name="panel" size={24} /></span>
    </button>{visibleOpen && <><strong>SmartiAI</strong><IconButton className="drawer-search" icon="search" label="חיפוש בשיחות ובקבצים" variant="ghost" disabled={!open} onClick={onSearch} /></>}</div>
    {!visibleOpen && <div className="drawer-rail-search"><IconButton icon="search" label="חיפוש בשיחות ובקבצים" variant="ghost" onClick={onSearch} /></div>}
    <button className="new-chat-button" type="button" aria-label="שיחה חדשה" onClick={onCreate}><Icon name="newChat" />{visibleOpen && <span>שיחה חדשה</span>}</button>
    {visibleOpen && <div className={`drawer-expanded-content ${scrolled ? "is-scrolled" : ""}`} inert={!open || undefined}>
      <div className="conversation-list" ref={list} onScroll={event => setScrolled(event.currentTarget.scrollTop > 0)}>
        <button className="recent-conversations-toggle" type="button" aria-expanded={expanded} aria-controls={listId} onClick={() => setExpanded(value => !value)}>
          <span>שיחות אחרונות</span><Icon name="chevron" size={16} />
        </button>
        <div id={listId} hidden={!expanded}>
        {loading && <p role="status">טוען שיחות…</p>}{error && <p role="alert">{error}</p>}
        {recent.map(item => {
          const state = activityState({ ...item, unread_count: unread(item.id) });
          const title = state === "running" ? "סמארטי עובד בשיחה הזאת" : state === "waiting_for_approval" ? item.runtime_status === "waiting_for_input" ? "סמארטי ממתין למפתח API" : "סמארטי ממתין לאישור" : "התקבלה תשובה חדשה";
          return <div className={`conversation-row ${item.id === activeId ? "is-active" : ""}`} key={item.id}>
            <button className="conversation-select" type="button" aria-current={item.id === activeId ? "true" : undefined} onClick={() => onSelect(item.id)}><HoverLabel text={item.title} /></button>
            {item.pinned && <Icon name="pin" />}
            {state !== "idle" && <span role="img" aria-label={title} title={title} className={`conversation-activity ${state}`} />}
            {open && <span className="history-actions"><Menu fitContent icon="more" label={`פעולות עבור ${item.title}`} items={actions(item)} /></span>}
          </div>;
        })}
        {!recent.length && !loading && !error && <p className="drawer-empty">עדיין אין שיחות</p>}
        </div>
      </div>
    </div>}
    <nav className="drawer-management" aria-label="ניהול והגדרות">
      {([
        ["tasks", "tasks", "משימות"], ["memory", "memory", "זיכרונות"],
        ["tools", "tools", "כלים וחיבורים"], ["usage", "usage", "שימוש"],
        ["settings_ai", "settings", "הגדרות"],
      ] as const).map(([section, icon, label]) => visibleOpen
        ? <button type="button" key={section} onClick={event => onManagement(section, event.currentTarget)}><Icon name={icon} /><span>{label}</span></button>
        : <IconButton key={section} icon={icon} label={label} variant="ghost" onClick={event => onManagement(section, event.currentTarget)} />)}
    </nav>
  </aside>;
}
