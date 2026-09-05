import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Composer } from "./Composer";
import { RichMessage } from "./RichMessage";
import { WorkbenchSurface } from "./WorkbenchPanels";
import type { ChatMessage, PendingAttachment } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import { workspaceIsNarrow } from "./legacyUiParity";
import {
  workspaceColumns,
  workspaceWorkbenchWidth,
  workspaceReducer,
  type WorkspaceState,
} from "./workspaceState";
import "./App.css";
import { useChatLayoutMotion, WORKSPACE_MOTION_MS } from "./workspaceMotion";

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

function Drawer({
  theme,
  expanded,
  onToggle,
}: {
  theme: ResolvedTheme;
  expanded: boolean;
  onToggle: () => void;
}) {
  const icons = legacyAssets(theme);
  return (
    <aside className={`conversation-drawer ${expanded ? "is-open" : "is-rail"}`} aria-label="שיחות">
      <div className="drawer-head">
        <button className="drawer-brand" type="button" aria-label={expanded ? "כיווץ תפריט הצד" : "פתיחת תפריט הצד"} onClick={onToggle}>
          <img className="drawer-logo" src={icons.logo} alt="" />
          <LegacyIcon src={icons.sidebarExpand} size={19} />
          <strong>SmartiAI</strong>
        </button>
        <button className="ui-icon-button drawer-collapse-control" type="button" aria-label="כיווץ תפריט הצד" aria-hidden={!expanded} tabIndex={expanded ? 0 : -1} onClick={onToggle}>
          <LegacyIcon src={icons.sidebarCollapse} />
        </button>
      </div>
      <button className="new-chat-button" type="button">
        <LegacyIcon src={icons.newChat} />
        <span>שיחה חדשה</span>
      </button>
      <div className="drawer-expanded-content" aria-hidden={!expanded}>
        <label className="conversation-search">
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
        </div>
      </div>
      <div className="profile-button"><span /><b>פרופיל משתמש</b></div>
    </aside>
  );
}

export function Point16AVisualFixture() {
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const theme: ResolvedTheme = params.get("theme") === "light" ? "light" : "dark";
  const requestedWorkbench = params.get("workbench") === "1";
  const requestedDrawer = params.get("drawer") === "1";
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [viewportWidth, setViewportWidth] = useState(() => innerWidth);
  const narrow = workspaceIsNarrow(viewportWidth);
  const previousNarrow = useRef(narrow);
  const [state, dispatch] = useReducer(workspaceReducer, undefined, () => ({
    conversationDrawerOpen: narrow ? requestedDrawer && !requestedWorkbench : true,
    workbenchOpen: requestedWorkbench,
    activeWorkbenchTab: requestedWorkbench ? "browser" : null,
  }) satisfies WorkspaceState);
  const [workbenchMounted, setWorkbenchMounted] = useState(
    state.workbenchOpen,
  );
  useEffect(() => {
    if (state.workbenchOpen) {
      setWorkbenchMounted(true);
      return;
    }
    const settled = window.setTimeout(() => setWorkbenchMounted(false), WORKSPACE_MOTION_MS + 34);
    return () => clearTimeout(settled);
  }, [state.workbenchOpen]);
  useEffect(() => {
    const responsive = () => setViewportWidth(innerWidth);
    window.addEventListener("resize", responsive);
    return () => window.removeEventListener("resize", responsive);
  }, []);
  useEffect(() => {
    if (previousNarrow.current === narrow) return;
    previousNarrow.current = narrow;
    dispatch(
      narrow
        ? { type: "responsive-narrow" }
        : { type: "set-conversations", open: true },
    );
  }, [narrow]);
  const toggleDrawer = () => {
    if (narrow && !state.conversationDrawerOpen)
      dispatch({ type: "activate-narrow-surface", surface: "conversations" });
    else
      dispatch({ type: "set-conversations", open: !state.conversationDrawerOpen });
  };
  const openWorkbench = () =>
    dispatch(
      narrow
        ? { type: "activate-narrow-surface", surface: "workbench", tab: "browser" }
        : { type: "open-workbench", tab: "browser" },
    );
  const closeWorkbench = () => dispatch({ type: "close-workbench" });
  const dismissOverlay = () =>
    state.workbenchOpen
      ? closeWorkbench()
      : dispatch({ type: "set-conversations", open: false });
  const chatMotionRef = useChatLayoutMotion(`${state.workbenchOpen}:${state.conversationDrawerOpen}:${narrow}`);
  const icons = legacyAssets(theme);
  return (
    <main className={`smarti-app theme-${theme}`} dir="rtl" data-theme={theme}>
      <header className="window-titlebar" dir="ltr">
        <div className="window-drag-region" />
        <button type="button">—</button><button type="button">□</button><button className="window-close" type="button">×</button>
      </header>
      <section
        className={`workspace ${state.workbenchOpen ? "has-workbench" : ""} ${narrow ? "is-overlay-layout" : ""}`}
        data-layout={narrow ? "overlay" : "split"}
        style={{ gridTemplateColumns: workspaceColumns(state, viewportWidth), "--workbench-track-width": `${workspaceWorkbenchWidth(state, viewportWidth)}px` } as CSSProperties}
      >
        <button
          type="button"
          className={`workspace-overlay-backdrop ${narrow && (state.conversationDrawerOpen || state.workbenchOpen) ? "is-active" : ""}`}
          aria-label="סגירת החלונית הפתוחה"
          aria-hidden={!narrow || (!state.conversationDrawerOpen && !state.workbenchOpen)}
          tabIndex={narrow && (state.conversationDrawerOpen || state.workbenchOpen) ? 0 : -1}
          onClick={dismissOverlay}
        />
        <Drawer theme={theme} expanded={state.conversationDrawerOpen} onToggle={toggleDrawer} />
        <section className="chat-column" ref={chatMotionRef}>
          <header className="chat-toolbar">
            <div className="chat-toolbar-controls">
              {!state.workbenchOpen && <button className="ui-icon-button chat-workbench-open-control" type="button" aria-label="פתיחת סביבת העבודה" onClick={openWorkbench}><LegacyIcon src={icons.workbenchOpen} /></button>}
            </div>
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
        <aside className={`workbench ${state.workbenchOpen ? "is-open" : ""}`} aria-hidden={!state.workbenchOpen}>
          {workbenchMounted && <WorkbenchSurface initial={null} visible={state.workbenchOpen} motionRevision={state.workbenchOpen} restored={{ tabs: [], active: "" }} sessionId="fixture" onCanvasAction={() => undefined} onClose={closeWorkbench} closeIcon={icons.workbenchClose} />}
        </aside>
      </section>
    </main>
  );
}
