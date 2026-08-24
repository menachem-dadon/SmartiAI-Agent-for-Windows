import { useMemo, useState } from "react";
import { Composer } from "./Composer";
import { RichMessage } from "./RichMessage";
import { WorkbenchSurface } from "./WorkbenchPanels";
import type { ChatMessage, PendingAttachment } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import { workspaceColumns, type WorkspaceState } from "./workspaceState";
import "./App.css";

const messages: ChatMessage[] = [
  {
    role: "user",
    content: "תכין לי סיכום קצר של תיקיית הפרויקט ותשמור על מבנה RTL ברור.",
    created_at: "2026-08-24T08:12:00+03:00",
  },
  {
    role: "assistant",
    content: "בשמחה. **מצאתי שלושה אזורים עיקריים:**\n\n- אפליקציית Windows\n- שכבת Core מקומית\n- סביבת Workbench עם דפדפן, קבצים ומסוף\n\n```powershell\npython -m unittest tests.test_workspace\n```",
    created_at: "2026-08-24T08:12:08+03:00",
    metadata: {
      memory_updated: true,
      agent_process: {
        elapsed_seconds: 8,
        events: [
          { type: "report", text: "סורק את מבנה הפרויקט" },
          { type: "tool_group_finish", text: "הסריקה הושלמה", group: { id: "scan" } },
        ],
      },
    },
  },
];

function Drawer({ theme, expanded }: { theme: ResolvedTheme; expanded: boolean }) {
  const icons = legacyAssets(theme);
  return (
    <aside className={`conversation-drawer ${expanded ? "is-open" : "is-rail"}`} aria-label="שיחות">
      <div className="drawer-head">
        <button className="drawer-brand" type="button">
          <img className="drawer-logo" src={icons.logo} alt="" />
          {expanded && <strong>SmartiAI</strong>}
        </button>
      </div>
      <button className="new-chat-button" type="button">
        <LegacyIcon src={icons.newChat} />
        {expanded && <span>שיחה חדשה</span>}
      </button>
      {expanded && <><label className="conversation-search">
          <LegacyIcon src={icons.search} size={26} />
          <input value="" readOnly placeholder="חיפוש לפי שם או תוכן" />
        </label>
        <div className="conversation-list">
        <div className="conversation-row is-active">
          <button className="conversation-select" type="button">
            <span><strong>בדיקת תאימות יומית</strong><small>24.08.2026, 08:12 · 2 הודעות</small></span>
          </button>
          <LegacyIcon src={icons.pin} size={16} />
        </div>
        <div className="conversation-row">
          <button className="conversation-select" type="button">
            <span><strong>Smarti Browser</strong><small>23.08.2026, 19:40 · 14 הודעות</small></span>
          </button>
          <span className="conversation-activity has-unread" />
        </div>
        </div></>}
      <div className="profile-button"><span />{expanded && <b>פרופיל משתמש</b>}</div>
    </aside>
  );
}

export function Point16AVisualFixture() {
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const theme: ResolvedTheme = params.get("theme") === "light" ? "light" : "dark";
  const workbenchOpen = params.get("workbench") === "1";
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const narrow = innerWidth - 286 < 920;
  const state: WorkspaceState = {
    conversationDrawerOpen: !narrow,
    workbenchOpen,
    activeWorkbenchTab: workbenchOpen ? "browser" : null,
  };
  const icons = legacyAssets(theme);
  return (
    <main className={`smarti-app theme-${theme}`} dir="rtl" data-theme={theme}>
      <header className="window-titlebar" dir="ltr">
        <div className="window-drag-region" />
        <button type="button">—</button><button type="button">□</button><button className="window-close" type="button">×</button>
      </header>
      <section
        className={`workspace ${workbenchOpen ? "has-workbench" : ""} ${narrow && workbenchOpen ? "is-workbench-narrow" : ""}`}
        style={{ gridTemplateColumns: workspaceColumns(state, innerWidth) }}
      >
        <Drawer theme={theme} expanded={!narrow} />
        <section className="chat-column">
          <header className="chat-toolbar">
            <div className="chat-toolbar-controls"><button className="ui-icon-button" type="button"><LegacyIcon src={icons.workbenchOpen} /></button></div>
            <h1>בדיקת תאימות יומית</h1>
          </header>
          <div className="chat-stage has-messages">
            <div className="message-list">
              {messages.map((message, index) => <RichMessage message={message} theme={theme} key={index} />)}
            </div>
          </div>
          <Composer
            theme={theme}
            attachments={attachments}
            provider="openai"
            model="gpt-5.6-sol"
            favoriteModels={[{ provider: "openai", model: "gpt-5.6-sol" }]}
            reasoningEffort="high"
            reasoningOptions={[{ value: "high", label: "גבוהה" }]}
            autonomyMode="balanced"
            localFastMode
            onAttachments={setAttachments}
            onSend={async () => undefined}
            onCancel={() => undefined}
          />
        </section>
        <aside className={`workbench ${workbenchOpen ? "is-open" : ""}`} aria-hidden={!workbenchOpen}>
          {workbenchOpen && <WorkbenchSurface initial={null} visible restored={{ tabs: [], active: "" }} sessionId="fixture" onCanvasAction={() => undefined} onClose={() => undefined} />}
        </aside>
      </section>
    </main>
  );
}
