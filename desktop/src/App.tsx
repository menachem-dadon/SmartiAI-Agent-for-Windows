import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { ManagementCenter } from "./ManagementCenter";
import { WorkbenchSurface } from "./WorkbenchPanels";
import { ACTIVE_RUN_STATES, mergeMessages } from "./chatState";
import type {
  Approval,
  Bootstrap,
  ChatMessage,
  Conversation,
  MessagePage,
  PendingAttachment,
  ReasoningOption,
  RunEvent,
  RunRecord,
} from "./chatTypes";
import { Composer } from "./Composer";
import { coreApi, encodePath } from "./coreApi";
import { copyForState, type CoreSnapshot } from "./coreState";
import {
  parseThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "./designSystem";
import { RichMessage } from "./RichMessage";
import { Alert, Button, IconButton } from "./ui";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import {
  initialWorkspaceState,
  workspaceColumns,
  workspaceReducer,
  type WorkbenchTab,
} from "./workspaceState";
import { activityState, legacyUi, workspaceIsNarrow } from "./legacyUiParity";
import "./App.css";

const initialCore: CoreSnapshot = {
  state: "starting",
  generation: 0,
  pid: null,
  port: null,
  startedAt: null,
  lastError: null,
  stderrTail: [],
};
const cursorKey = "smarti.desktop.event-cursor";
type FavoriteModel = { provider: string; model: string };

function conversationMeta(item: Conversation): string {
  let date = "";
  if (item.updated_at) {
    const value = new Date(item.updated_at);
    if (!Number.isNaN(value.getTime()))
      date = value.toLocaleString("he-IL", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
  }
  return `${date}${date ? " · " : ""}${item.message_count || 0} הודעות`;
}

function WindowTitleBar() {
  const appWindow = getCurrentWindow();
  return (
    <header
      className="window-titlebar"
      dir="ltr"
      onDoubleClick={() => void appWindow.toggleMaximize()}
    >
      <div className="window-drag-region" data-tauri-drag-region />
      <button
        type="button"
        aria-label="מזער"
        onClick={() => void appWindow.minimize()}
      >
        ─
      </button>
      <button
        type="button"
        aria-label="הגדלה"
        onClick={() => void appWindow.toggleMaximize()}
      >
        □
      </button>
      <button
        type="button"
        className="window-close"
        aria-label="סגירה"
        onClick={() => void appWindow.close()}
      >
        ×
      </button>
    </header>
  );
}

function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    parseThemePreference(localStorage.getItem(THEME_STORAGE_KEY)),
  );
  const [systemDark, setSystemDark] = useState(
    () => matchMedia("(prefers-color-scheme: dark)").matches,
  );
  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const update = () => setSystemDark(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const setPreference = (next: ThemePreference) => {
    localStorage.setItem(THEME_STORAGE_KEY, next);
    setPreferenceState(next);
  };
  return {
    preference,
    resolved: resolveTheme(preference, systemDark),
    setPreference,
  };
}

export default function App() {
  const [core, setCore] = useState<CoreSnapshot>(initialCore);
  const [busy, setBusy] = useState(false);
  const [, setHealthOkay] = useState(false);
  const [workspace, dispatch] = useReducer(
    workspaceReducer,
    initialWorkspaceState,
  );
  const [managementOpen, setManagementOpen] = useState(false);
  const [managementSection, setManagementSection] = useState<
    | "settings"
    | "tasks"
    | "memory"
    | "tools"
    | "diagnostics"
    | "usage"
    | "logs"
    | "about"
    | null
  >(null);
  const { resolved, setPreference } = useTheme();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [page, setPage] = useState<MessagePage | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [reconnecting, setReconnecting] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [favoriteModels, setFavoriteModels] = useState<FavoriteModel[]>([]);
  const [reasoningEffort, setReasoningEffort] = useState("auto");
  const [reasoningOptions, setReasoningOptions] = useState<ReasoningOption[]>(
    [],
  );
  const [autonomyMode, setAutonomyMode] = useState("balanced");
  const [localFastMode, setLocalFastMode] = useState(false);
  const [narrowWorkspace, setNarrowWorkspace] = useState(() =>
    workspaceIsNarrow(innerWidth),
  );
  const [uiPreferences, setUiPreferences] = useState<Record<string, unknown>>(
    {},
  );
  const [voiceHotkey, setVoiceHotkey] = useState("Ctrl+Shift+Space");
  const [keepRunningInTray, setKeepRunningInTray] = useState(true);
  const notifiedUnread = useRef<Record<string, number>>({});
  const [conversationDialog, setConversationDialog] = useState<{
    kind: "rename" | "delete";
    item: Conversation;
  } | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const activeRunId =
    runs.find(
      (item) =>
        item.session_id === activeId && ACTIVE_RUN_STATES.has(item.status),
    )?.id || "";
  const refreshCore = useCallback(
    async () => setCore(await invoke<CoreSnapshot>("core_status")),
    [],
  );

  const loadMessages = useCallback(async (sessionId: string) => {
    if (!sessionId) {
      setMessages([]);
      setPage(null);
      return;
    }
    const value = await coreApi<MessagePage>(
      "GET",
      `/v2/conversations/${encodePath(sessionId)}/messages?limit=48`,
    );
    setPage(value);
    setMessages(value.messages);
  }, []);
  const refreshLists = useCallback(
    async (search = query) => {
      const [conversationData, runData, approvalData] = await Promise.all([
        coreApi<{ items: Conversation[] }>(
          "GET",
          `/v2/conversations?q=${encodeURIComponent(search)}&limit=100`,
        ),
        coreApi<{ items: RunRecord[] }>("GET", "/v2/runs?limit=100"),
        coreApi<{ items: Approval[] }>("GET", "/v2/approvals"),
      ]);
      setConversations(conversationData.items);
      setRuns(runData.items);
      setApprovals(approvalData.items);
    },
    [query],
  );
  const bootstrap = useCallback(async () => {
    setReconnecting(false);
    const data = await coreApi<Bootstrap>("GET", "/v2/bootstrap");
    const values = data.settings?.values || {};
    const preferences =
      values.ui_preferences && typeof values.ui_preferences === "object"
        ? (values.ui_preferences as Record<string, unknown>)
        : {};
    const favorites = Array.isArray(values.favorite_models)
      ? values.favorite_models.filter((item): item is FavoriteModel =>
          Boolean(
            item &&
              typeof item === "object" &&
              typeof (item as FavoriteModel).provider === "string" &&
              typeof (item as FavoriteModel).model === "string",
          ),
        )
      : [];
    setConversations(data.conversations);
    setApprovals(data.pending_approvals);
    setProvider(data.chat_models.provider);
    setModel(data.chat_models.model);
    setReasoningEffort(data.chat_models.reasoning_effort || "auto");
    setReasoningOptions(data.chat_models.reasoning_options || []);
    setDisplayName(data.display_name || "");
    setFavoriteModels(favorites);
    setAutonomyMode(
      typeof values.autonomy_mode === "string"
        ? values.autonomy_mode
        : "balanced",
    );
    setLocalFastMode(Boolean(values.local_fast_mode_enabled));
    setVoiceHotkey(
      typeof values.voice_hotkey === "string"
        ? values.voice_hotkey
        : "Ctrl+Shift+Space",
    );
    setKeepRunningInTray(values.keep_running_in_tray !== false);
    setUiPreferences(preferences);
    dispatch({
      type: "set-conversations",
      open:
        !workspaceIsNarrow(innerWidth) &&
        !Boolean(preferences.workspace_sidebar_collapsed),
    });
    const first = activeId || data.conversations[0]?.id || "";
    setActiveId(first);
    if (first) await loadMessages(first);
    await refreshLists();
  }, [activeId, loadMessages, refreshLists]);

  useEffect(() => {
    let alive = true;
    const listener = listen<CoreSnapshot>("core://state", ({ payload }) => {
      if (alive) setCore(payload);
    });
    void refreshCore();
    return () => {
      alive = false;
      void listener.then((dispose) => dispose());
    };
  }, [refreshCore]);
  useEffect(() => {
    let alive = true;
    if (core.state !== "ready") {
      setHealthOkay(false);
      return () => {
        alive = false;
      };
    }
    void invoke<{ ready: boolean }>("core_health")
      .then((health) => {
        if (alive) {
          setHealthOkay(Boolean(health.ready));
          void bootstrap().catch((reason) => setError(String(reason)));
        }
      })
      .catch(() => {
        if (alive) setHealthOkay(false);
      });
    return () => {
      alive = false;
    };
  }, [core.generation, core.state]);
  useEffect(() => {
    const responsive = () => {
      const narrow = workspaceIsNarrow(innerWidth);
      setNarrowWorkspace(narrow);
      if (narrow) dispatch({ type: "responsive-narrow" });
      else if (!Boolean(uiPreferences.workspace_sidebar_collapsed))
        dispatch({ type: "set-conversations", open: true });
    };
    responsive();
    window.addEventListener("resize", responsive);
    return () => window.removeEventListener("resize", responsive);
  }, [uiPreferences.workspace_sidebar_collapsed]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (core.state === "ready")
        void refreshLists(query).catch(() => setReconnecting(true));
    }, legacyUi.historySearchDebounceMs);
    return () => clearTimeout(timer);
  }, [query, core.state]);
  useEffect(() => {
    if (!activeId || core.state !== "ready") return;
    void loadMessages(activeId)
      .then(() =>
        coreApi(
          "POST",
          `/v2/conversations/${encodePath(activeId)}/read`,
          { actor_id: "tauri-desktop" },
          true,
        ),
      )
      .then(() => refreshLists())
      .catch((reason) => setError(String(reason)));
  }, [activeId, core.state]);
  useEffect(() => {
    if (!activeRunId || core.state !== "ready") return;
    void coreApi<{ items: RunEvent[] }>(
      "GET",
      `/v2/runs/${encodePath(activeRunId)}/events?after_sequence=0&limit=500`,
    )
      .then((data) =>
        setEvents((current) => {
          const merged = new Map<number, RunEvent>();
          for (const item of [...current, ...data.items])
            merged.set(item.event_id, item);
          return [...merged.values()]
            .sort((left, right) => left.event_id - right.event_id)
            .slice(-500);
        }),
      )
      .catch(() => undefined);
  }, [activeRunId, core.state]);
  useEffect(() => {
    if (core.state !== "ready") return;
    let stopped = false;
    const poll = async () => {
      try {
        const cursor = Number(sessionStorage.getItem(cursorKey) || 0);
        const data = await coreApi<{ items: RunEvent[] }>(
          "GET",
          `/v2/events/replay?after_event_id=${cursor}`,
        );
        if (data.items.length) {
          sessionStorage.setItem(
            cursorKey,
            String(Math.max(...data.items.map((item) => item.event_id))),
          );
          setEvents((current) => [...current, ...data.items].slice(-500));
          await refreshLists();
          if (
            activeId &&
            data.items.some((item) => item.session_id === activeId)
          )
            await loadMessages(activeId);
        }
        setReconnecting(false);
      } catch {
        setReconnecting(true);
      }
    };
    void poll();
    const timer = window.setInterval(() => {
      if (!stopped) void poll();
    }, 1200);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [core.generation, core.state, activeId]);
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (managementSection) setManagementSection(null);
        else {
          setManagementOpen(false);
          if (workspace.workbenchOpen) dispatch({ type: "close-workbench" });
        }
      }
      if (event.ctrlKey && event.key.toLowerCase() === "b") {
        event.preventDefault();
        dispatch(
          workspace.workbenchOpen
            ? { type: "close-workbench" }
            : { type: "open-workbench", tab: "browser" },
        );
      }
      if (event.ctrlKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        void createConversation();
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [workspace.workbenchOpen, managementSection]);

  const activeConversation = conversations.find((item) => item.id === activeId);
  const activeRun = runs.find(
    (item) =>
      item.session_id === activeId && ACTIVE_RUN_STATES.has(item.status),
  );
  const activeEvents = events.filter((item) => item.session_id === activeId);
  const activeApprovals = approvals.filter(
    (item) => item.session_id === activeId,
  );
  const eventsForRun = (runId: string) =>
    activeEvents.filter((item) => item.run_id === runId);
  const activeAssistantRecorded = Boolean(
    activeRun &&
      messages.some(
        (message) =>
          message.role === "assistant" &&
          String(message.metadata?.run_id || "") === activeRun.id,
      ),
  );
  const createConversation = async () => {
    try {
      const data = await coreApi<{ conversation: Conversation }>(
        "POST",
        "/v2/conversations",
        { title: "שיחה חדשה" },
        true,
      );
      setConversations((current) => [data.conversation, ...current]);
      setActiveId(data.conversation.id);
      setMessages([]);
      setPage(null);
      setAttachments([]);
    } catch (reason) {
      setError(String(reason));
    }
  };
  const selectConversation = async (id: string) => {
    setActiveId(id);
    setAttachments([]);
  };
  const renameConversation = async (item: Conversation) => {
    setRenameValue(item.title);
    setConversationDialog({ kind: "rename", item });
  };
  const togglePinned = async (item: Conversation) => {
    await coreApi(
      "PATCH",
      `/v2/conversations/${encodePath(item.id)}`,
      { pinned: !item.pinned },
      true,
    );
    await refreshLists();
  };
  const exportConversation = async (item: Conversation) => {
    let before: number | null = null;
    let collected: ChatMessage[] = [];
    do {
      const suffix: string = before ? `&before=${before}` : "";
      const chunk: MessagePage = await coreApi<MessagePage>(
        "GET",
        `/v2/conversations/${encodePath(item.id)}/messages?limit=500${suffix}`,
      );
      collected = mergeMessages(chunk.messages, collected);
      before = chunk.has_older ? chunk.next_before_ordinal : null;
    } while (before);
    const blob = new Blob(
      [JSON.stringify({ conversation: item, messages: collected }, null, 2)],
      { type: "application/json" },
    );
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = `${item.title.replace(/[\\/:*?"<>|]/g, "_") || "smarti-chat"}.json`;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
  };
  const deleteConversation = async (item: Conversation) => {
    if (item.is_busy) {
      setError("יש לעצור את הפעולה בשיחה לפני מחיקתה.");
      return;
    }
    setConversationDialog({ kind: "delete", item });
  };
  const confirmConversationDialog = async () => {
    if (!conversationDialog) return;
    const { item, kind } = conversationDialog;
    if (kind === "rename") {
      if (!renameValue.trim()) return;
      await coreApi(
        "PATCH",
        `/v2/conversations/${encodePath(item.id)}`,
        { title: renameValue.trim() },
        true,
      );
    } else {
      await coreApi(
        "DELETE",
        `/v2/conversations/${encodePath(item.id)}`,
        {},
        true,
      );
      if (activeId === item.id) {
        setActiveId("");
        setMessages([]);
      }
    }
    setConversationDialog(null);
    await refreshLists();
  };
  const send = async (text: string) => {
    setError("");
    let sessionId = activeId;
    if (!sessionId) {
      const data = await coreApi<{ conversation: Conversation }>(
        "POST",
        "/v2/conversations",
        {},
        true,
      );
      sessionId = data.conversation.id;
      setActiveId(sessionId);
    }
    const handles: string[] = [];
    for (const item of attachments) {
      if (item.size && item.size > 25 * 1024 * 1024)
        throw new Error(`${item.name}: הקובץ גדול מ־25MB`);
      const data = await coreApi<{ attachment: { handle: string } }>(
        "POST",
        "/v2/attachments",
        { path: item.path, session_id: sessionId },
        true,
      );
      handles.push(data.attachment.handle);
    }
    await coreApi(
      "POST",
      `/v2/conversations/${encodePath(sessionId)}/runs`,
      {
        text,
        attachment_handles: handles,
        provider_mode: provider,
        model_name: model,
        source: "tauri_desktop",
      },
      true,
    );
    setAttachments([]);
    await refreshLists();
    await loadMessages(sessionId);
  };
  const cancel = async () => {
    if (activeRun)
      await coreApi(
        "POST",
        `/v2/runs/${encodePath(activeRun.id)}/cancel`,
        {},
        true,
      );
    await refreshLists();
  };
  const toggleConversationDrawer = async () => {
    const open = !workspace.conversationDrawerOpen;
    dispatch({ type: "set-conversations", open });
    const next = { ...uiPreferences, workspace_sidebar_collapsed: !open };
    setUiPreferences(next);
    try {
      await coreApi(
        "PATCH",
        "/v2/settings",
        { values: { ui_preferences: next } },
        true,
      );
    } catch (reason) {
      dispatch({ type: "set-conversations", open: !open });
      setUiPreferences(uiPreferences);
      setError(`לא ניתן לשמור את מצב תפריט הצד: ${String(reason)}`);
    }
  };
  const loadOlder = async () => {
    if (!page?.next_before_ordinal || !activeId) return;
    const older = await coreApi<MessagePage>(
      "GET",
      `/v2/conversations/${encodePath(activeId)}/messages?limit=48&before=${page.next_before_ordinal}`,
    );
    setMessages((current) => mergeMessages(older.messages, current));
    setPage((current) =>
      current
        ? {
            ...current,
            has_older: older.has_older,
            older_count: older.older_count,
            next_before_ordinal: older.next_before_ordinal,
          }
        : older,
    );
  };
  const resolveApproval = async (approval: Approval, approved: boolean) => {
    await coreApi(
      "POST",
      `/v2/approvals/${encodePath(approval.id)}/resolve`,
      { approved },
      true,
    );
    await refreshLists();
  };
  const changeProvider = async (next: string) => {
    setProvider(next);
    setModel("");
    try {
      const data = await coreApi<{
        models: Array<string | { id?: string; name?: string }>;
      }>("GET", `/v2/providers/${encodePath(next)}/models`);
      const values = data.models
        .map((item) =>
          typeof item === "string" ? item : item.id || item.name || "",
        )
        .filter(Boolean);
      setModel(values[0] || "");
    } catch (reason) {
      setError(`לא ניתן לטעון מודלים: ${String(reason)}`);
    }
  };
  const loadReasoning = async (nextProvider: string, nextModel: string) => {
    const data = await coreApi<{
      reasoning_effort: string;
      reasoning_options: ReasoningOption[];
    }>(
      "GET",
      `/v2/providers/${encodePath(nextProvider)}/reasoning?model=${encodeURIComponent(nextModel)}`,
    );
    setReasoningEffort(data.reasoning_effort || "auto");
    setReasoningOptions(data.reasoning_options || []);
  };
  const selectFavoriteModel = async (item: FavoriteModel) => {
    if (item.provider !== provider) await changeProvider(item.provider);
    setModel(item.model);
    try {
      await loadReasoning(item.provider, item.model);
    } catch {
      setReasoningEffort("auto");
      setReasoningOptions([]);
    }
  };
  const changeReasoning = async (effort: string) => {
    const previous = reasoningEffort;
    setReasoningEffort(effort);
    try {
      const data = await coreApi<{ reasoning_effort: string }>(
        "POST",
        `/v2/providers/${encodePath(provider)}/reasoning`,
        { model, effort },
        true,
      );
      setReasoningEffort(data.reasoning_effort);
    } catch (reason) {
      setReasoningEffort(previous);
      setError(`לא ניתן לעדכן עוצמת חשיבה: ${String(reason)}`);
    }
  };
  const changeAutonomy = async (next: string) => {
    const previous = autonomyMode;
    setAutonomyMode(next);
    try {
      await coreApi(
        "PATCH",
        "/v2/settings",
        { values: { autonomy_mode: next } },
        true,
      );
    } catch (reason) {
      setAutonomyMode(previous);
      setError(`לא ניתן לעדכן פרופיל בטיחות: ${String(reason)}`);
    }
  };
  const changeLocalFastMode = async (next: boolean) => {
    const previous = localFastMode;
    setLocalFastMode(next);
    try {
      await coreApi(
        "PATCH",
        "/v2/settings",
        { values: { local_fast_mode_enabled: next } },
        true,
      );
    } catch (reason) {
      setLocalFastMode(previous);
      setError(`לא ניתן לעדכן FastMode: ${String(reason)}`);
    }
  };
  const retryCore = async () => {
    setBusy(true);
    try {
      setCore(await invoke<CoreSnapshot>("core_restart"));
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (core.state === "ready")
      void invoke("desktop_set_voice_hotkey", { shortcut: voiceHotkey }).catch(
        (reason) => setError(`קיצור הקול אינו זמין: ${String(reason)}`),
      );
  }, [core.state, voiceHotkey]);
  useEffect(() => { void invoke("desktop_set_close_to_tray", { enabled: keepRunningInTray }); }, [keepRunningInTray]);
  useEffect(() => {
    const unread = conversations.reduce(
      (sum, item) => sum + Number(item.unread_count || 0),
      0,
    );
    void invoke("desktop_set_unread", { count: unread });
    for (const item of conversations) {
      const current = Number(item.unread_count || 0);
      const previous = notifiedUnread.current[item.id] || 0;
      if (current > previous && document.hidden)
        void invoke("desktop_notify", {
          title: "תגובה חדשה מ־Smarti",
          body: item.title,
          sessionId: item.id,
        });
      notifiedUnread.current[item.id] = current;
    }
  }, [conversations]);
  useEffect(() => {
    let alive = true;
    const subscription = listen<{ command: string; sessionId?: string }>(
      "desktop://activation",
      ({ payload }) => {
        if (!alive) return;
        if (payload.sessionId) setActiveId(payload.sessionId);
        if (payload.command === "new-chat") void createConversation();
        if (payload.command === "voice")
          window.dispatchEvent(new Event("smarti:voice-hotkey"));
        if (payload.command === "update-shutdown") void invoke("desktop_quit");
      },
    );
    return () => {
      alive = false;
      void subscription.then((dispose) => dispose());
    };
  }, []);

  if (core.state !== "ready") {
    const copy = copyForState(core.state, core.lastError);
    const failed = ["crashed", "fatal", "repair"].includes(core.state);
    return (
      <main
        className={`startup-shell theme-${resolved}`}
        dir="rtl"
        data-state={core.state}
      >
        <section className="status-card" aria-live="polite">
          <div className="splash-brand">
            <img src={legacyAssets(resolved).logo} alt="" />
            <div>
              <h1>SmartiAI</h1>
              <p>סוכן AI חכם ל-Windows</p>
              <small>גרסה 0.87.0 • Python Core • Windows</small>
            </div>
          </div>
          <div className="splash-spacer" />
          <p className="splash-status">
            {failed ? copy.status : copy.description}
          </p>
          <div className="splash-progress">
            <i />
          </div>
          {failed && (
            <div className="recovery">
              <Button variant="primary" onClick={retryCore} disabled={busy}>
                {busy ? "מנסה שוב…" : "הפעל מחדש"}
              </Button>
              {core.stderrTail.length > 0 && (
                <pre dir="ltr">{core.stderrTail.slice(-3).join("\n")}</pre>
              )}
            </div>
          )}
        </section>
      </main>
    );
  }

  const openWorkbench = (tab: WorkbenchTab) =>
    dispatch({ type: "open-workbench", tab });
  const icons = legacyAssets(resolved);
  return (
    <main
      className={`smarti-app theme-${resolved}`}
      dir="rtl"
      data-theme={resolved}
    >
      <WindowTitleBar />
      <section
        className={`workspace ${workspace.workbenchOpen ? "has-workbench" : ""} ${narrowWorkspace && workspace.workbenchOpen ? "is-workbench-narrow" : ""}`}
        style={{ gridTemplateColumns: workspaceColumns(workspace) }}
      >
        <aside
          className={`conversation-drawer ${workspace.conversationDrawerOpen ? "is-open" : "is-rail"}`}
          aria-label="שיחות"
        >
          <div className="drawer-head">
            <button
              className="drawer-brand"
              type="button"
              aria-label={
                workspace.conversationDrawerOpen
                  ? "כיווץ תפריט הצד"
                  : "פתיחת תפריט הצד"
              }
              onClick={() => void toggleConversationDrawer()}
            >
              <img className="drawer-logo" src={icons.logo} alt="" />
              <LegacyIcon src={icons.sidebarExpand} size={19} />
              <strong>SmartiAI</strong>
            </button>
            {workspace.conversationDrawerOpen && (
              <IconButton
                label="כיווץ תפריט הצד"
                onClick={() => void toggleConversationDrawer()}
              >
                <LegacyIcon src={icons.sidebarCollapse} />
              </IconButton>
            )}
          </div>
          <button
            className="new-chat-button"
            type="button"
            onClick={() => void createConversation()}
          >
            <LegacyIcon src={icons.newChat} />
            <span>שיחה חדשה</span>
          </button>
          {workspace.conversationDrawerOpen && (
            <>
              <label className="conversation-search">
                <LegacyIcon src={icons.search} size={26} />
                <input
                  dir="rtl"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="חיפוש לפי שם או תוכן"
                  aria-label="חיפוש בשיחות"
                />
                {query && (
                  <button
                    className="conversation-search-clear"
                    type="button"
                    aria-label="ניקוי חיפוש"
                    onClick={() => setQuery("")}
                  >
                    ×
                  </button>
                )}
              </label>
              <div className="conversation-list">
                {conversations.map((item) => {
                  const state = activityState(item);
                  return (
                    <div
                      className={`conversation-row ${item.id === activeId ? "is-active" : ""}`}
                      key={item.id}
                    >
                      <button
                        className="conversation-select"
                        type="button"
                        onClick={() => void selectConversation(item.id)}
                      >
                        <span>
                          <strong>{item.title}</strong>
                          <small>{conversationMeta(item)}</small>
                        </span>
                      </button>
                      {item.pinned && <LegacyIcon src={icons.pin} size={16} />}
                      {state !== "idle" && (
                        <span
                          title={
                            state === "running"
                              ? "סמארטי עובד בשיחה הזאת"
                              : state === "waiting_for_approval"
                                ? "סמארטי ממתין לאישור"
                                : "התקבלה תשובה חדשה"
                          }
                          className={`conversation-activity ${state === "running" ? "is-busy" : state === "waiting_for_approval" ? "needs-input" : "has-unread"}`}
                        />
                      )}
                      <details className="conversation-menu">
                        <summary aria-label={`פעולות עבור ${item.title}`}>
                          <LegacyIcon src={icons.menu} size={18} />
                        </summary>
                        <div>
                          <button
                            type="button"
                            onClick={() => void togglePinned(item)}
                          >
                            <LegacyIcon
                              src={item.pinned ? icons.unpin : icons.pin}
                              size={15}
                            />
                            {item.pinned ? "בטל הצמדה" : "הצמד שיחה"}
                          </button>
                          <button
                            type="button"
                            onClick={() => void renameConversation(item)}
                          >
                            <LegacyIcon src={icons.rename} size={15} />
                            שנה שם
                          </button>
                          <button
                            type="button"
                            onClick={() => void exportConversation(item)}
                          >
                            <LegacyIcon src={icons.exportJson} size={15} />
                            יצוא JSON
                          </button>
                          <hr />
                          <button
                            type="button"
                            onClick={() => void deleteConversation(item)}
                          >
                            <LegacyIcon src={icons.delete} size={15} />
                            מחק שיחה
                          </button>
                        </div>
                      </details>
                    </div>
                  );
                })}
                {!conversations.length && (
                  <p className="drawer-empty">לא נמצאו שיחות</p>
                )}
              </div>
            </>
          )}
          <details className="profile-menu">
            <summary className="profile-button" aria-label="פרופיל והגדרות">
              <span aria-hidden="true" />
              {workspace.conversationDrawerOpen && <b>פרופיל משתמש</b>}
            </summary>
            <div>
              <button
                type="button"
                onClick={() => setManagementSection("usage")}
              >
                נתוני שימוש
              </button>
              <button
                type="button"
                onClick={() => setManagementSection("settings")}
              >
                הגדרות וניהול
              </button>
              <button
                type="button"
                onClick={() => setManagementSection("diagnostics")}
              >
                Smarti Diagnostic
              </button>
              <hr />
              <button
                type="button"
                onClick={() => setManagementSection("about")}
              >
                אודות
              </button>
            </div>
          </details>
        </aside>
        <section className="chat-column" aria-label="צ׳אט מרכזי">
          <div className="chat-toolbar">
            <div className="chat-toolbar-controls" dir="ltr">
              <IconButton
                label="פעולות שיחה"
                aria-expanded={managementOpen}
                onClick={() => setManagementOpen((open) => !open)}
              >
                <LegacyIcon src={icons.menu} size={26} />
              </IconButton>
              <IconButton
                label={
                  workspace.workbenchOpen
                    ? "כיווץ אזור העבודה"
                    : "פתיחת אזור העבודה"
                }
                onClick={() =>
                  workspace.workbenchOpen
                    ? dispatch({ type: "close-workbench" })
                    : openWorkbench("browser")
                }
              >
                <LegacyIcon
                  src={
                    workspace.workbenchOpen
                      ? icons.workbenchClose
                      : icons.workbenchOpen
                  }
                />
              </IconButton>
            </div>
            <h1>{activeConversation?.title || "שיחה חדשה"}</h1>
            {managementOpen && (
              <div className="legacy-management-menu">
                {activeConversation ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void togglePinned(activeConversation)}
                    >
                      <LegacyIcon
                        src={
                          activeConversation.pinned ? icons.unpin : icons.pin
                        }
                        size={18}
                      />
                      {activeConversation.pinned ? "בטל הצמדה" : "הצמד שיחה"}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        void renameConversation(activeConversation)
                      }
                    >
                      <LegacyIcon src={icons.rename} size={18} />
                      שנה שם
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        void exportConversation(activeConversation)
                      }
                    >
                      <LegacyIcon src={icons.exportJson} size={18} />
                      יצוא JSON
                    </button>
                    <hr />
                    <button
                      type="button"
                      onClick={() =>
                        void deleteConversation(activeConversation)
                      }
                    >
                      <LegacyIcon src={icons.delete} size={18} />
                      מחק שיחה
                    </button>
                  </>
                ) : (
                  <span>אין פעולות זמינות</span>
                )}
              </div>
            )}
          </div>
          {error && (
            <div className="chat-error">
              <Alert tone="danger" title="הפעולה לא הושלמה">
                {error}
                <button onClick={() => setError("")}>סגירה</button>
              </Alert>
            </div>
          )}
          <div
            className={`chat-stage ${messages.length || activeRun ? "has-messages" : ""}`}
          >
            {page?.has_older && (
              <Button variant="ghost" onClick={() => void loadOlder()}>
                טעינת {page.older_count} הודעות קודמות
              </Button>
            )}
            {!messages.length && !activeRun ? (
              <div className="legacy-welcome">
                <h2>
                  {displayName
                    ? `היי ${displayName}, במה תרצה שאתמקד?`
                    : "במה תרצה שאתמקד?"}
                </h2>
              </div>
            ) : (
              <div className="message-list">
                {messages.map((message, index) => {
                  const runId = String(message.metadata?.run_id || "");
                  const messageActive = Boolean(
                    activeRun && runId === activeRun.id,
                  );
                  return (
                    <RichMessage
                      key={`${message.created_at}-${index}`}
                      message={message}
                      events={runId ? eventsForRun(runId) : []}
                      active={messageActive}
                      theme={resolved}
                    />
                  );
                })}
                {activeRun && !activeAssistantRecorded && (
                  <RichMessage
                    key={`active-${activeRun.id}`}
                    message={{
                      role: "assistant",
                      content: "",
                      metadata: { run_id: activeRun.id },
                    }}
                    events={eventsForRun(activeRun.id)}
                    active
                    theme={resolved}
                  />
                )}
              </div>
            )}
          </div>
          {!!activeApprovals.length &&
            (() => {
              const approval = activeApprovals[0];
              const risk =
                approval.risk_level === "high"
                  ? "סיכון גבוה"
                  : approval.risk_level === "low"
                    ? "סיכון נמוך"
                    : "סיכון בינוני";
              return (
                <div className="action-confirm-backdrop">
                  <section
                    className={`action-confirm-card risk-${approval.risk_level}`}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="approval-title"
                  >
                    <div className="action-confirm-head">
                      <span>!</span>
                      <div>
                        <small>בקשת הרשאה</small>
                        <h2 id="approval-title">
                          {approval.title || "אישור פעולה"}
                        </h2>
                        <b>{risk}</b>
                      </div>
                    </div>
                    <h3>פרטי הפעולה</h3>
                    <pre dir="auto" tabIndex={0}>
                      {approval.prompt}
                    </pre>
                    <p>אשר רק אם הפעולה תואמת למה שביקשת מסמארטי לבצע.</p>
                    <footer>
                      <button
                        type="button"
                        className="reject"
                        onClick={() => void resolveApproval(approval, false)}
                      >
                        דחה
                      </button>
                      <button
                        type="button"
                        className="accept"
                        autoFocus
                        onClick={() => void resolveApproval(approval, true)}
                      >
                        אשר
                      </button>
                    </footer>
                  </section>
                </div>
              );
            })()}
          {conversationDialog && (
            <div
              className="legacy-dialog-backdrop"
              onMouseDown={(event) => {
                if (event.target === event.currentTarget)
                  setConversationDialog(null);
              }}
            >
              <form
                className="legacy-input-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="conversation-dialog-title"
                onSubmit={(event) => {
                  event.preventDefault();
                  void confirmConversationDialog();
                }}
              >
                <h2 id="conversation-dialog-title">
                  {conversationDialog.kind === "rename"
                    ? "שינוי שם שיחה"
                    : "מחיקת שיחה"}
                </h2>
                {conversationDialog.kind === "rename" ? (
                  <label>
                    שם חדש:
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                    />
                  </label>
                ) : (
                  <p>למחוק את השיחה הזו לצמיתות?</p>
                )}
                <footer>
                  <button
                    type="button"
                    onClick={() => setConversationDialog(null)}
                  >
                    ביטול
                  </button>
                  <button
                    type="submit"
                    autoFocus={conversationDialog.kind === "delete"}
                  >
                    אישור
                  </button>
                </footer>
              </form>
            </div>
          )}
          <Composer
            theme={resolved}
            disabled={reconnecting}
            running={Boolean(activeRun)}
            attachments={attachments}
            provider={provider}
            model={model}
            favoriteModels={favoriteModels}
            reasoningEffort={reasoningEffort}
            reasoningOptions={reasoningOptions}
            autonomyMode={autonomyMode}
            localFastMode={localFastMode}
            onFavoriteModel={selectFavoriteModel}
            onReasoningEffort={changeReasoning}
            onAutonomyMode={changeAutonomy}
            onLocalFastMode={changeLocalFastMode}
            onAttachments={setAttachments}
            onSend={send}
            onCancel={() => void cancel()}
          />
        </section>
        <aside
          className={`workbench ${workspace.workbenchOpen ? "is-open" : ""}`}
          aria-label="Workbench"
          aria-hidden={!workspace.workbenchOpen}
        >
          {workspace.workbenchOpen && workspace.activeWorkbenchTab && (
            <WorkbenchSurface
              initial={workspace.activeWorkbenchTab}
              sessionId={activeId}
              onCanvasAction={(text) => void send(text)}
              onClose={() => dispatch({ type: "close-workbench" })}
            />
          )}
        </aside>
      </section>
      {managementSection && (
        <ManagementCenter
          initial={managementSection}
          onClose={() => setManagementSection(null)}
          setTheme={setPreference}
        />
      )}
    </main>
  );
}
