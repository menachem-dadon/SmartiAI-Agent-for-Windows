import type { Conversation } from "./chatTypes";
import type { ManagementSection } from "./managementCatalog";
import { activityState } from "./legacyUiParity";
import { recentConversations } from "./chatState";
import { HoverLabel, Icon, IconButton, Menu, SearchField, type MenuItem } from "./design-system";

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

export function ChatSidebar({ open, logo, conversations, activeId, query, loading, error, unread,
  onToggle, onCreate, onQuery, onSelect, actions, onManagement }: {
  open: boolean; logo: string; conversations: Conversation[]; activeId: string;
  query: string; loading: boolean; error: string; unread: (id: string) => number;
  onToggle: () => void; onCreate: () => void; onQuery: (query: string) => void;
  onSelect: (id: string) => void; actions: (item: Conversation) => MenuItem[];
  onManagement: (section: ManagementSection, trigger?: HTMLElement) => void;
}) {
  return <aside className={`conversation-drawer ${open ? "is-open" : "is-rail"}`} aria-label="שיחות">
    <div className="drawer-brand-row"><button className="drawer-brand" type="button" aria-label={open ? "כיווץ תפריט הצד" : "פתיחת תפריט הצד"} onClick={onToggle}>
      <span className="drawer-brand-mark"><img src={logo} alt="" /><Icon name="panel" size={24} /></span>
    </button>{open && <strong>SmartiAI</strong>}</div>
    <button className="new-chat-button" type="button" aria-label="שיחה חדשה" onClick={onCreate}><Icon name="newChat" size={24} />{open && <span>שיחה חדשה</span>}</button>
    {open && <div className="drawer-expanded-content">
      <SearchField label="חיפוש בשיחות" placeholder="חיפוש לפי שם או תוכן" value={query} onChange={event => onQuery(event.target.value)} />
      <div className="conversation-list">
        {loading && <p role="status">טוען שיחות…</p>}{error && <p role="alert">{error}</p>}
        {recentConversations(conversations).map(item => {
          const state = activityState({ ...item, unread_count: unread(item.id) });
          const title = state === "running" ? "סמארטי עובד בשיחה הזאת" : state === "waiting_for_approval" ? item.runtime_status === "waiting_for_input" ? "סמארטי ממתין למפתח API" : "סמארטי ממתין לאישור" : "התקבלה תשובה חדשה";
          return <div className={`conversation-row ${item.id === activeId ? "is-active" : ""}`} key={item.id}>
            <button className="conversation-select" type="button" aria-current={item.id === activeId ? "true" : undefined} onClick={() => onSelect(item.id)}><HoverLabel text={item.title} /></button>
            {item.pinned && <Icon name="pin" />}
            {state !== "idle" && <span role="img" aria-label={title} title={title} className={`conversation-activity ${state}`} />}
            <span className="history-actions"><Menu fitContent icon="more" label={`פעולות עבור ${item.title}`} items={actions(item)} /></span>
          </div>;
        })}
        {!recentConversations(conversations).length && <p className="drawer-empty">{query ? "לא נמצאו שיחות" : "עדיין אין שיחות"}</p>}
      </div>
    </div>}
    <nav className="drawer-management" aria-label="ניהול והגדרות">
      {([
        ["tasks", "tasks", "משימות"], ["memory", "memory", "זיכרונות"],
        ["tools", "tools", "כלים וחיבורים"], ["usage", "usage", "שימוש"],
        ["settings_ai", "settings", "הגדרות"],
      ] as const).map(([section, icon, label]) => open
        ? <button type="button" key={section} onClick={event => onManagement(section, event.currentTarget)}><Icon name={icon} /><span>{label}</span></button>
        : <IconButton key={section} icon={icon} label={label} variant="ghost" onClick={event => onManagement(section, event.currentTarget)} />)}
    </nav>
  </aside>;
}
