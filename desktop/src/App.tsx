import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { checkForUpdates } from "./updates";
import { ManagementCenter } from "./ManagementCenter";
import { validateProviderKey } from "./SettingsManagement";
import type { ManagementSection } from "./managementCatalog";
import { LegalAgreement, type LegalStatus } from "./LegalAgreement";
import { WorkbenchSurface, type WorkbenchHandle } from "./WorkbenchPanels";
import type { BrowserActivity } from "./BrowserPanel";
import { BrowserPreviewCard } from "./BrowserPreviewCard";
import {
  ACTIVE_RUN_STATES,
  mergeMessages,
  pendingApiKeyRequest,
  type ApiKeyRequest,
} from "./chatState";
import type {
  Approval,
  Bootstrap,
  ChatMessage,
  Conversation,
  ConversationList,
  MessagePage,
  ReasoningOption,
  RunEvent,
  RunRecord,
} from "./chatTypes";
import { Composer } from "./Composer";
import { coreApi, encodePath } from "./coreApi";
import { type CoreSnapshot } from "./coreState";
import {
  parseThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "./designSystem";
import { RichMessage } from "./RichMessage";
import { Alert, Button, DesignSystemProvider, Dialog, Field, Icon, IconButton, Menu } from "./design-system";
import { ChatSidebar, conversationActions } from "./ChatSidebar";
import { useChatDrafts, readActiveConversation, rememberActiveConversation, restoreActiveConversation } from "./chatDrafts";
import { savedChatPosition, useChatFooterFlow, useChatScroll } from "./chatScroll";
import { reduceStream, streamAnswer, type StreamState } from "./chatStreaming";
import { legacyAssets } from "./legacyAssets";
import {
  clampWorkbenchResize,
  initialWorkspaceState,
  workspaceColumns,
  workspaceWorkbenchWidth,
  workspaceReducer,
  type WorkbenchSnapshot,
  type WorkbenchTab,
} from "./workspaceState";
import { legacyUi, workspaceIsNarrow } from "./legacyUiParity";
import "./App.css";
import "./chat.css";
import "./workbench.css";
import { readWorkbenchSession, writeWorkbenchSession } from "./workbenchSession";
import { useChatLayoutMotion } from "./workspaceMotion";
import { useConversationAttention } from "./conversationAttention";
import { settingsRevision, subscribeSettingsChanges } from "./settingsChanges";
import { ConversationApprovals, useApprovalQueue } from "./conversationApprovals";
import { useReplyNavigation, type ReplyNavigation } from "./replyNavigation";
import { WindowTitleBar } from "./WindowTitleBar";
import { StartupFailure, useStartupWatchdog } from "./InterfaceRecovery";
import { setStartupVisible, updateStartupTheme } from "./startup";

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
const EMPTY_MESSAGE_EVENTS: RunEvent[] = [];
type FavoriteModel = { provider: string; model: string };

export function ApiKeyRequiredDialog({
  request,
  onCancel,
}: {
  request: ApiKeyRequest;
  onCancel: () => Promise<void>;
}) {
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [validating, setValidating] = useState(false);
  const providing = useRef(false);
  const provide = async () => {
    const value = draft.trim();
    if (!value || providing.current) return;
    providing.current = true; setValidating(true);
    setStatus("בודק את המפתח לפני שמירה…");
    try {
      await validateProviderKey({ provider: request.provider, secret: value });
      const result = await coreApi<{ accepted: boolean }>(
        "POST",
        `/v2/runs/${encodePath(request.runId)}/api-key`,
        { secret_key: request.secretKey, value },
        true,
      );
      if (!result.accepted) throw new Error("הבקשה אינה ממתינה עוד למפתח");
      setDraft("");
      setStatus("");
    } catch (reason) {
      setDraft(value);
      setStatus(
        `המפתח לא נשמר: ${reason instanceof Error ? reason.message : String(reason)}`,
      );
    } finally { providing.current = false; setValidating(false); }
  };
  const cancelRequest = async () => {
    if (providing.current) return;
    providing.current = true; setValidating(true);
    try { await onCancel(); } catch (reason) { setStatus(`לא ניתן לבטל: ${String(reason)}`); }
    finally { providing.current = false; setValidating(false); }
  };
  return (
    <Dialog open title={request.title} description={request.message} onClose={() => { if (!validating) void cancelRequest(); }}>
      <form
        className="chat-api-key"
        onSubmit={(event) => {
          event.preventDefault();
          void provide();
        }}
      >

        <b className="chat-api-key-provider">ספק פעיל: {request.providerLabel}</b>
          <Field label="מפתח API"
            autoFocus
            type="password"
            autoComplete="off"
            value={draft}
            placeholder="הדבק כאן את מפתח ה-API"
            onChange={(event) => {
              setDraft(event.target.value);
              setStatus("");
            }}
          />
        {request.helpUrl && (
          <button
            className="chat-api-key-help"
            type="button"
            onClick={() =>
              void invoke("open_chat_link", {
                target: request.helpUrl,
                local: false,
              })
            }
          >
            פתח דף הנפקת מפתחות API
          </button>
        )}
        {request.keyInstructions && (
          <p className="chat-api-key-instructions">{request.keyInstructions}</p>
        )}
        <p className="chat-api-key-note">
          המפתח יישמר כמו שאר המפתחות של סמארטי, ולא יוצג בלוגים.
        </p>
        {status && (
          <p className="chat-api-key-validation-status" role={status.startsWith("בודק") ? "status" : "alert"}>
            {status}
          </p>
        )}
        <footer>
          <Button disabled={validating} onClick={() => void cancelRequest()}>ביטול</Button>
          <Button type="submit" variant="primary" loading={validating} disabled={!draft.trim()}>שמירה והמשך</Button>
        </footer>
      </form>
    </Dialog>
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
  const setPreference = useCallback((next: ThemePreference) => {
    localStorage.setItem(THEME_STORAGE_KEY, next);
    setPreferenceState(next);
  }, []);
  return {
    preference,
    resolved: resolveTheme(preference, systemDark),
    setPreference,
  };
}

export default function App() {
  const [core, setCore] = useState<CoreSnapshot>(initialCore);
  const [healthOkay, setHealthOkay] = useState(false);
  const [startupError, setStartupError] = useState(false);
  const [workspace, dispatch] = useReducer(
    workspaceReducer,
    initialWorkspaceState,
  );
  const [managementOpen, setManagementOpen] = useState(false);
  const [managementSection, setManagementSection] =
    useState<ManagementSection | null>(null);
  const managementReturnFocus = useRef<HTMLElement | null>(null);
  const openManagement = useCallback((section: ManagementSection, trigger?: HTMLElement) => {
    // Capture before the chat becomes inert: WebView2 may blur it on commit.
    managementReturnFocus.current = trigger || (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setManagementSection(section);
  }, []);
  const { resolved, setPreference } = useTheme();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState("");
  const [activeId, setActiveIdState] = useState(readActiveConversation);
  const activeIdRef = useRef(activeId);
  const messageRequest = useRef(0);
  const loadedAttentionIds = useRef(new Set<string>());
  const listRequest = useRef(0);
  const runtimeListRequest = useRef(0);
  const navigationRevision = useRef(0);
  const navigationTarget = useRef("");
  const [navigation, setNavigation] = useState<ReplyNavigation | null>(null);
  const [loadedNavigationRevision, setLoadedNavigationRevision] = useState(0);
  const [readyNavigationRevision, setReadyNavigationRevision] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [newUserRun, setNewUserRun] = useState("");
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const [page, setPage] = useState<MessagePage | null>(null);
  const setActiveId = useCallback((id: string) => {
    if (activeIdRef.current !== id) {
      ++messageRequest.current;
      setMessages([]);
      messagesRef.current = [];
      setPage(null);
      loadedAttentionIds.current.clear();
    }
    activeIdRef.current = id;
    setActiveIdState(id);
    if (!rememberActiveConversation(id)) setError("לא ניתן לשמור את השיחה הפעילה לרענון. הטיוטות נשארות בבעלות השיחות שלהן.");
  }, []);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streams, setStreams] = useState<Record<string, StreamState>>({});
  const approvalQueue = useApprovalQueue();
  const [query, setQuery] = useState("");
  const queryRef = useRef(query);
  queryRef.current = query;
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const drafts = useChatDrafts(activeId, setError);
  const { attachments } = drafts.draft;
  const setAttachments = drafts.setAttachments;
  const attention = useConversationAttention(setError);
  const [foreground, setForeground] = useState(() => !document.hidden && document.hasFocus());
  const [availableUpdateVersion, setAvailableUpdateVersion] = useState("");
  const [reconnecting, setReconnecting] = useState(false);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [favoriteModels, setFavoriteModels] = useState<FavoriteModel[]>([]);
  const [modelSelectionSource, setModelSelectionSource] = useState<
    Record<string, unknown>
  >({});
  const [reasoningEffort, setReasoningEffort] = useState("auto");
  const [reasoningOptions, setReasoningOptions] = useState<ReasoningOption[]>(
    [],
  );
  const [autonomyMode, setAutonomyMode] = useState("balanced");
  const [localFastMode, setLocalFastMode] = useState(false);
  const [narrowWorkspace, setNarrowWorkspace] = useState(() =>
    workspaceIsNarrow(innerWidth),
  );
  const narrowWorkspaceRef = useRef(narrowWorkspace);
  const [viewportWidth, setViewportWidth] = useState(() => innerWidth);
  const [workbenchWidth, setWorkbenchWidth] = useState<number | null>(null);
  const [workspaceResizing, setWorkspaceResizing] = useState(false);
  const [initialWorkbench] = useState(readWorkbenchSession);
  const [workbenchExpanded, setWorkbenchExpanded] = useState(initialWorkbench.expanded);
  const workbenchTrigger = useRef<HTMLButtonElement>(null);
  const chatMotionRef = useChatLayoutMotion(`${workspace.workbenchOpen}:${workspace.conversationDrawerOpen}:${narrowWorkspace}:${workbenchExpanded}`);
  const [uiPreferences, setUiPreferences] = useState<Record<string, unknown>>(
    {},
  );
  const uiPreferencesRef = useRef<Record<string, unknown>>({});
  const [workbenchRestore, setWorkbenchRestore] =
    useState<WorkbenchSnapshot | null>(null);
  const [browserActivity, setBrowserActivity] =
    useState<BrowserActivity | null>(null);
  const workbenchRef = useRef<WorkbenchHandle>(null);
  const [dismissedBrowserPreview, setDismissedBrowserPreview] = useState("");
  useEffect(() => {
    if (workspace.workbenchOpen) setDismissedBrowserPreview("");
  }, [workspace.workbenchOpen]);
  const [bootstrapReady, setBootstrapReady] = useState(false);
  const restoredModelOwner = useRef("");
  const modelOperations = useRef<Promise<unknown>>(Promise.resolve());
  const [restoringModel, setRestoringModel] = useState(false);
  useEffect(() => {
    if (!bootstrapReady || restoredModelOwner.current === activeId) return;
    setRestoringModel(false);
    if (!activeId) { restoredModelOwner.current = ""; return; }
    restoredModelOwner.current = activeId;
    setRestoringModel(false);
    const selected = drafts.draft.selection;
    if (!selected || (selected.provider === provider && selected.model === model && selected.effort === reasoningEffort)) return;
    let disposed = false;
    setRestoringModel(true);
    void (async () => {
      const accepted = await selectFavoriteModel(selected);
      if (!accepted || disposed) return;
      if (!disposed && selected.effort !== "auto") {
        const available = await loadReasoning(selected.provider, selected.model, activeId);
        if (disposed) return;
        if (available.reasoning_options.some(option => option.value === selected.effort))
          await coreApi("POST", `/v2/providers/${encodePath(selected.provider)}/reasoning`, { model: selected.model, effort: selected.effort }, true);
      }
      const latest = await coreApi<Bootstrap>("GET", "/v2/bootstrap");
      if (!disposed) { syncSettings(latest); drafts.setSelection({ provider: selected.provider, model: selected.model, effort: latest.chat_models.reasoning_effort || "auto" }); }
    })().catch(reason => { if (!disposed) setError(`לא ניתן לשחזר את בחירת המודל: ${String(reason)}`); })
      .finally(() => { if (!disposed) setRestoringModel(false); });
    return () => { disposed = true; };
  }, [activeId, bootstrapReady]);
  const [workspaceWindowReady, setWorkspaceWindowReady] = useState(false);
  const [legalStatus, setLegalStatus] = useState<LegalStatus | null>(null);
  const [legalChecked, setLegalChecked] = useState(false);
  const startupDelayed = useStartupWatchdog(core.state === "ready" && (!workspaceWindowReady || !legalChecked));
  const [voiceHotkey, setVoiceHotkey] = useState("Ctrl+Shift+Space");

  const [keepRunningInTray, setKeepRunningInTray] = useState(true);
  const notifiedAttention = useRef(new Set<string>());
  const unreadUpdate = useRef(Promise.resolve());
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
  const saveUiPreferencePatch = useCallback(
    async (patch: Record<string, unknown>) => {
      const next = { ...uiPreferencesRef.current, ...patch };
      uiPreferencesRef.current = next;
      setUiPreferences(next);
      await coreApi(
        "PATCH",
        "/v2/settings",
        { values: { ui_preferences: next } },
        true,
      );
      return next;
    },
    [],
  );

  const loadMessages = useCallback(async (sessionId: string) => {
    if (!sessionId) {
      setMessages([]);
      setPage(null);
      return;
    }
    const request = ++messageRequest.current;
    const revision = navigationRevision.current;
    const targetRun = navigationTarget.current;
    const value = await coreApi<MessagePage>(
      "GET",
      `/v2/conversations/${encodePath(sessionId)}/messages?limit=48`,
    );
    if (sessionId !== activeIdRef.current || request !== messageRequest.current) return;
    // An older toast can refer to a reply outside the newest history page.
    // Include that page before positioning; pending runs are found by their user message.
    const savedCount = Math.max(savedChatPosition(sessionId)?.count || 0, messagesRef.current.length);
    const savedAnchorRun = savedChatPosition(sessionId)?.anchorRun;
    while (value.has_older && value.next_before_ordinal !== null &&
        ((targetRun && !value.messages.some(message => message.metadata?.run_id === targetRun)) ||
          value.messages.length < savedCount || (savedAnchorRun && !value.messages.some(message => message.metadata?.run_id === savedAnchorRun)))) {
      const older = await coreApi<MessagePage>("GET",
        `/v2/conversations/${encodePath(sessionId)}/messages?limit=48&before=${value.next_before_ordinal}`,
      );
      if (sessionId !== activeIdRef.current || request !== messageRequest.current) return;
      value.messages = mergeMessages(older.messages, value.messages);
      value.has_older = older.has_older;
      value.older_count = older.older_count;
      value.next_before_ordinal = older.next_before_ordinal;
    }
    navigationTarget.current = "";
    setLoadedNavigationRevision(revision);
    loadedAttentionIds.current = new Set(value.unread_attention_ids || []);
    setPage(value);
    setMessages(mergeMessages(messagesRef.current, value.messages));
  }, []);
  const refreshConversations = useCallback(async (search = queryRef.current) => {
    const request = ++listRequest.current;
    const data = await coreApi<ConversationList>(
      "GET", `/v2/conversations?q=${encodeURIComponent(search)}&limit=100`,
    );
    if (request !== listRequest.current) return null;
    setConversations(data.items);
    attention.replace(data.attention_items);
    return data;
  }, [attention.replace]);
  const refreshLists = useCallback(
    async (search = queryRef.current) => {
      const request = ++runtimeListRequest.current;
      const [conversationData, runData, approvalData] = await Promise.all([
        refreshConversations(search),
        coreApi<{ items: RunRecord[] }>("GET", "/v2/runs?limit=100"),
        coreApi<{ items: Approval[] }>("GET", "/v2/approvals"),
      ]);
      if (request === runtimeListRequest.current) {
        setRuns(runData.items);
        setStreams(current => { const next = { ...current }; for (const run of runData.items) if (run.metadata?.stream && (run.metadata.stream.cursor || 0) > (next[run.id]?.cursor || 0)) next[run.id] = run.metadata.stream; return next; });
        approvalQueue.replace(approvalData.items);
      }
      return conversationData;
    },
    [refreshConversations, approvalQueue.replace],
  );
  const syncSettings = useCallback((data: Bootstrap) => {
    const values = data.settings?.values || {};
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
    setProvider(data.chat_models.provider);
    setModel(data.chat_models.model);
    setReasoningEffort(data.chat_models.reasoning_effort || "auto");
    setReasoningOptions(data.chat_models.reasoning_options || []);
    setFavoriteModels(favorites);
    setModelSelectionSource(
      values.selected_model_source &&
        typeof values.selected_model_source === "object"
        ? (values.selected_model_source as Record<string, unknown>)
        : {},
    );
    setAutonomyMode(
      typeof values.autonomy_mode === "string"
        ? values.autonomy_mode
        : "balanced",
    );
    setLocalFastMode(Boolean(values.local_fast_mode_enabled));
    const preferences =
      values.ui_preferences && typeof values.ui_preferences === "object"
        ? (values.ui_preferences as Record<string, unknown>)
        : {};
    setVoiceHotkey(
      typeof values.voice_hotkey === "string"
        ? values.voice_hotkey
        : "Ctrl+Shift+Space",
    );
    setKeepRunningInTray(values.keep_running_in_tray !== false);
    uiPreferencesRef.current = preferences;
    setUiPreferences(preferences);
    const themeMode = String(preferences.theme_mode || "system");
    setPreference(
      themeMode === "light" || themeMode === "dark" ? themeMode : "system",
    );
    setAvailableUpdateVersion(String(values.updates_last_available_version || ""));
  }, [setPreference]);
  useEffect(() => {
    if (core.state !== "ready") return;
    let request = 0;
    let disposed = false;
    const unsubscribe = subscribeSettingsChanges(() => {
      const current = ++request;
      void coreApi<Bootstrap>("GET", "/v2/bootstrap")
        .then((data) => {
          if (!disposed && current === request) syncSettings(data);
        })
        .catch((reason) => {
          if (!disposed && current === request) setError(String(reason));
        });
    });
    return () => { disposed = true; unsubscribe(); };
  }, [core.state, core.generation, syncSettings]);
  const bootstrap = useCallback(async () => {
    setBootstrapReady(false);
    setReconnecting(false);
    const revision = settingsRevision();
    const data = await coreApi<Bootstrap>("GET", "/v2/bootstrap");
    const values = data.settings?.values || {};
    const preferences =
      values.ui_preferences && typeof values.ui_preferences === "object"
        ? (values.ui_preferences as Record<string, unknown>)
        : {};
    if (revision === settingsRevision()) syncSettings(data);
    setConversations(data.conversations);
    approvalQueue.replace(data.pending_approvals);
    setDisplayName(data.display_name || "");
    const restoredWorkbench = initialWorkbench.snapshot;
    setWorkbenchRestore(restoredWorkbench);
    const restoredTab =
      restoredWorkbench?.tabs.find(
        (item) => item.id === restoredWorkbench.active,
      )?.kind || null;
    dispatch({
      type: "restore-layout",
      conversations:
        !workspaceIsNarrow(innerWidth) &&
        !Boolean(preferences.workspace_sidebar_collapsed),
      workbench: initialWorkbench.open,
      tab: restoredTab,
    });
    const first = restoreActiveConversation(data.conversations, activeIdRef.current);
    setActiveId(first);
    if (first) await loadMessages(first);
    await refreshLists();
    setBootstrapReady(true);
  }, [loadMessages, refreshLists, setActiveId, syncSettings, initialWorkbench]);

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
      setBootstrapReady(false);
      setStartupError(false);
      setWorkspaceWindowReady(false);
      setLegalChecked(false);
      setLegalStatus(null);
      return () => {
        alive = false;
      };
    }
    void (async () => {
      try {
        const health = await invoke<{ ready: boolean }>("core_health");
        if (!alive) return;
        if (!health.ready) throw new Error("Core is not ready");
        setHealthOkay(true);
        const legal = await coreApi<LegalStatus>("GET", "/v2/management/legal");
        if (!alive) return;
        setLegalStatus(legal);
        setLegalChecked(true);
        if (legal.accepted) await bootstrap();
        if (alive) setWorkspaceWindowReady(true);
      } catch (reason) {
        if (alive) {
          setStartupError(true);
          setError(String(reason));
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [core.generation, core.state]);
  useEffect(() => {
    let frame = 0;
    let settled = 0;
    const applyResponsiveLayout = (syncWidePreference: boolean) => {
      const width = innerWidth;
      const narrow = workspaceIsNarrow(width);
      const breakpointChanged = narrowWorkspaceRef.current !== narrow;
      narrowWorkspaceRef.current = narrow;
      setViewportWidth((current) => (current === width ? current : width));
      setWorkbenchWidth(null);
      setNarrowWorkspace(narrow);
      if (breakpointChanged && narrow)
        dispatch({ type: "responsive-narrow" });
      else if (!narrow && (breakpointChanged || syncWidePreference))
        dispatch({
          type: "set-conversations",
          open: !Boolean(uiPreferences.workspace_sidebar_collapsed),
        });
    };
    const responsive = () => {
      setWorkspaceResizing(true);
      cancelAnimationFrame(frame);
      clearTimeout(settled);
      frame = requestAnimationFrame(() => applyResponsiveLayout(false));
      settled = window.setTimeout(() => setWorkspaceResizing(false), 150);
    };
    setWorkspaceResizing(false);
    applyResponsiveLayout(true);
    window.addEventListener("resize", responsive);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(settled);
      window.removeEventListener("resize", responsive);
    };
  }, [uiPreferences.workspace_sidebar_collapsed]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (core.state === "ready") {
        setHistoryLoading(true);
        setHistoryError("");
        void refreshLists(query)
          .catch((reason) => {
            setHistoryError(`לא ניתן לטעון את השיחות: ${String(reason)}`);
            setReconnecting(true);
          })
          .finally(() => setHistoryLoading(false));
      }
    }, legacyUi.historySearchDebounceMs);
    return () => clearTimeout(timer);
  }, [query, core.state]);
  useEffect(() => {
    if (core.state !== "ready" || !bootstrapReady) return;
    let stopped = false;
    const runAutomaticCheck = async () => {
      try {
        const safe = await coreApi<{ values: Record<string, unknown> }>(
          "GET",
          "/v2/settings",
        );
        if (safe.values.updates_auto_check === false) return;
        const lastChecked = Date.parse(
          String(safe.values.updates_last_checked_at || ""),
        );
        if (
          Number.isFinite(lastChecked) &&
          Date.now() - lastChecked < 55 * 60 * 1000
        ) {
          const known = String(
            safe.values.updates_last_available_version || "",
          );
          if (!stopped) setAvailableUpdateVersion(known);
          return;
        }
        const found = await checkForUpdates();
        if (stopped) return;
        const version = found?.version || "";
        setAvailableUpdateVersion(version);
      } catch {
        // A failed background check must not interrupt chat startup. Manual check shows the error.
      }
    };
    const first = window.setTimeout(() => void runAutomaticCheck(), 2600);
    const hourly = window.setInterval(
      () => void runAutomaticCheck(),
      60 * 60 * 1000,
    );
    return () => {
      stopped = true;
      window.clearTimeout(first);
      window.clearInterval(hourly);
    };
  }, [bootstrapReady, core.state]);
  useEffect(() => {
    if (!activeId || core.state !== "ready") return;
    let cancelled = false;
    const revision = navigationRevision.current;
    void Promise.all([
      loadMessages(activeId),
      navigation?.sessionId === activeId ? refreshLists() : Promise.resolve(),
    ])
      .then(() => {
        if (!cancelled) setReadyNavigationRevision(revision);
      })
      .catch((reason) => setError(String(reason)));
    return () => { cancelled = true; };
  }, [activeId, core.state, navigation, loadMessages, refreshLists]);
  useEffect(() => {
    let alive = true;
    const update = () => setForeground(!document.hidden && document.hasFocus());
    window.addEventListener("focus", update);
    window.addEventListener("blur", update);
    document.addEventListener("visibilitychange", update);
    const subscription = getCurrentWindow().onFocusChanged(({ payload }) => {
      if (alive) setForeground(payload && !document.hidden);
    });
    return () => {
      alive = false;
      window.removeEventListener("focus", update);
      window.removeEventListener("blur", update);
      document.removeEventListener("visibilitychange", update);
      void subscription.then((dispose) => dispose());
    };
  }, []);
  useEffect(() => {
    if (foreground && activeIdRef.current && core.state === "ready")
      void loadMessages(activeIdRef.current).catch((reason) => setError(String(reason)));
  }, [foreground, core.state, loadMessages]);
  useEffect(() => {
    if (!foreground || document.hidden || managementSection || !workspaceWindowReady ||
        core.state !== "ready" || !activeId || page?.session_id !== activeId) return;
    if (navigation?.sessionId === activeId && readyNavigationRevision !== navigation.revision) return;
    void attention.acknowledge(activeId, page.unread_attention_ids || []);
  }, [foreground, managementSection, workspaceWindowReady, core.state, activeId, page,
    navigation, readyNavigationRevision, attention.acknowledge]);
  const chatViewportRef = useReplyNavigation(
    navigation, page?.session_id || "",
    workspaceWindowReady && !managementSection && loadedNavigationRevision === navigation?.revision &&
      readyNavigationRevision === navigation?.revision,
  );
  const scroll = useChatScroll(chatViewportRef, activeId,
    workspaceWindowReady && !managementSection && page?.session_id === activeId,
    messages.length, messages, newUserRun, activeRunId, foreground);
  useEffect(() => {
    if (!newUserRun || !messages.some(message => message.role === "user" && message.metadata?.run_id === newUserRun)) return;
    const timer = window.setTimeout(() => setNewUserRun(""), 240);
    return () => window.clearTimeout(timer);
  }, [newUserRun, messages]);
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
    let polling = false;
    const poll = async () => {
      if (polling || stopped) return;
      polling = true;
      let delay = 0;
      try {
        const cursor = Number(sessionStorage.getItem(cursorKey) || 0);
        const data = await coreApi<{ items: RunEvent[] }>(
          "GET",
          `/v2/events/live?after_event_id=${cursor}`,
        );
        if (stopped) return;
        if (!data.items.length) delay = 250;
        let conversationData: ConversationList | null;
        if (data.items.length) {
          sessionStorage.setItem(
            cursorKey,
            String(Math.max(...data.items.map((item) => item.event_id))),
          );
          const streamEvents = data.items.filter(item => item.event_type === "run_stream");
          if (streamEvents.length) setStreams(current => {
            const next = { ...current };
            for (const event of streamEvents) next[event.run_id] = reduceStream(next[event.run_id], event);
            return next;
          });
          const structural = data.items.filter(item => item.event_type !== "run_stream");
          if (structural.length) setEvents((current) => [...new Map([...current, ...structural].map(item => [item.event_id, item])).values()].slice(-500));
          conversationData = structural.length ? await refreshLists() : null;
        } else conversationData = await refreshConversations();
        if (stopped) return;
        // Read receipts have no run event. Refresh the global projection even
        // during quiet polls, including reads from other clients and late attention.
        const unseenAttention = foreground && conversationData?.attention_items.some((item) =>
          item.session_id === activeId && !loadedAttentionIds.current.has(item.id),
        );
        if (activeId && (unseenAttention || data.items.some((item) => item.session_id === activeId && item.event_type !== "run_stream")))
          await loadMessages(activeId);
        setReconnecting(false);
      } catch {
        setReconnecting(true);
        await new Promise(resolve => window.setTimeout(resolve, 1000));
      } finally {
        polling = false;
        if (!stopped) timer = window.setTimeout(() => void poll(), delay);
      }
    };
    let timer = 0;
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [core.generation, core.state, activeId, foreground, refreshConversations, refreshLists, loadMessages]);
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      // Management and its dialogs own keyboard navigation while the chat is inert.
      if (event.defaultPrevented || managementSection) return;
      if (event.key === "Escape") {
        if (managementOpen) setManagementOpen(false);
        else if (narrowWorkspace && workspace.conversationDrawerOpen)
          dispatch({ type: "set-conversations", open: false });
        else if (workspace.workbenchOpen) {
          dispatch({ type: "close-workbench" });
        }
      }
      if (event.ctrlKey && event.key.toLowerCase() === "b") {
        event.preventDefault();
        dispatch(
          workspace.workbenchOpen
            ? { type: "close-workbench" }
            : narrowWorkspace
              ? {
                  type: "activate-narrow-surface",
                  surface: "workbench",
                  tab: null,
                }
              : { type: "open-workbench", tab: null },
        );
      }
      if (event.ctrlKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        void createConversation();
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [
    managementOpen,
    managementSection,
    narrowWorkspace,
    saveUiPreferencePatch,
    workspace.conversationDrawerOpen,
    workspace.workbenchOpen,
  ]);

  const activeConversation = conversations.find((item) => item.id === activeId);
  const activeRun = runs.find(
    (item) =>
      item.session_id === activeId && ACTIVE_RUN_STATES.has(item.status),
  );
  const activeEvents = events.filter((item) => item.session_id === activeId);
  const activeApprovals = approvalQueue.items.filter(
    (item) => item.session_id === activeId,
  );
  const chatFooterRef = useRef<HTMLDivElement>(null);
  const flowingFooter = useChatFooterFlow(chatViewportRef, chatFooterRef,
    `${activeId}:${activeApprovals.length}:${scroll.hasNewContent}:${workspaceWindowReady}:${managementSection}`);
  const activeApiKeyRequest = pendingApiKeyRequest(activeEvents.filter(event =>
    runs.some(run => run.id === event.run_id && run.status === "waiting_for_input")));
  const messageEvents = useMemo(() => {
    const grouped = new Map<string, RunEvent[]>();
    for (const event of events) if (event.session_id === activeId) {
      const row = grouped.get(event.run_id) || [];
      row.push(event); grouped.set(event.run_id, row);
    }
    return grouped;
  }, [events, activeId]);
  // Runtime and message requests can finish in different orders. Keep the
  // observed run mounted through that gap, using the Core's terminal record.
  const observedReplies = useRef<Record<string, string>>({});
  if (activeRun) observedReplies.current[activeId] = activeRun.id;
  const terminalReply = runs.find(run => run.id === observedReplies.current[activeId] &&
    ["completed", "failed"].includes(run.status));
  const displayRun = activeRun || terminalReply;
  const activeAssistantRecorded = Boolean(displayRun && messages.some(message =>
    message.role === "assistant" && message.metadata?.run_id === displayRun.id));

  const createConversation = async () => {
    try {
      const empty = conversations.find(item => !item.message_count && !item.is_busy);
      if (empty) { await selectConversation(empty.id); return; }
      const data = await coreApi<{ conversation: Conversation }>(
        "POST",
        "/v2/conversations",
        {},
        true,
      );
      setConversations((current) => [data.conversation, ...current]);
      setActiveId(data.conversation.id);
      setMessages([]);
      setPage(null);
      if (narrowWorkspace)
        dispatch({ type: "set-conversations", open: false });
    } catch (reason) {
      setError(String(reason));
    }
  };
  const selectConversation = async (id: string, runId?: string, alignReply = false) => {
    if (!restoringModel && provider && model) drafts.setSelection({ provider, model, effort: reasoningEffort });
    setManagementSection(null);
    setManagementOpen(false);
    navigationTarget.current = runId || "";
    setNavigation({ sessionId: id, revision: ++navigationRevision.current, runId, alignReply });
    setActiveId(id);
    if (narrowWorkspaceRef.current)
      dispatch({ type: "set-conversations", open: false });
  };
  const renameConversation = async (item: Conversation) => {
    setRenameValue(item.title);
    setDialogError(""); setConversationDialog({ kind: "rename", item });
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
    const payload = await coreApi<Record<string, unknown>>(
      "GET",
      `/v2/conversations/${encodePath(item.id)}/export`,
    );
    await invoke("save_text_file", {
      suggestedName: `${item.title || "smarti-chat"}.json`,
      contents: JSON.stringify(payload, null, 2),
    });
    setError("");
  };
  const deleteConversation = async (item: Conversation) => {
    if (item.is_busy) {
      setError("יש לעצור את הפעולה בשיחה לפני מחיקתה.");
      return;
    }
    setDialogError(""); setConversationDialog({ kind: "delete", item });
  };
  const dialogGuard = useRef(false);
  const dialogCancel = useRef<HTMLButtonElement>(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [dialogError, setDialogError] = useState("");
  const confirmConversationDialog = async () => {
    if (dialogGuard.current) return;
    dialogGuard.current = true; setDialogBusy(true); setDialogError("");
    try {
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
      drafts.remove(item.id);
    }
    setConversationDialog(null);
    await refreshLists();
    } catch (reason) { setDialogError(String(reason)); }
    finally { dialogGuard.current = false; setDialogBusy(false); }
  };
  const send = async (text: string, isVoice = false) => {
    setError("");
    const submittedAttachments = [...attachments];
    let sessionId = activeId;
    if (!sessionId) {
      const data = await coreApi<{ conversation: Conversation }>(
        "POST",
        "/v2/conversations",
        {},
        true,
      );
      sessionId = data.conversation.id;
    }
    const handles: string[] = [];
    for (const item of submittedAttachments) {
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
    const submitted = await coreApi<{ run_id: string }>(
      "POST",
      `/v2/conversations/${encodePath(sessionId)}/runs`,
      {
        text,
        attachment_handles: handles,
        provider_mode: provider,
        model_name: model,
        source: "tauri_desktop",
        is_voice: isVoice,
      },
      true,
    );
    setNewUserRun(submitted.run_id || "");
    setAttachments((current) => current.filter(item => !submittedAttachments.includes(item)));
    if (!activeId) { drafts.transfer("", sessionId); setActiveId(sessionId); }
    // A refresh failure must not restore a draft whose run was already accepted.
    try {
      await refreshLists();
      if (activeIdRef.current === sessionId) await loadMessages(sessionId);
    } catch (reason) {
      setError(`ההודעה נשלחה, אך רענון התצוגה נכשל: ${String(reason)}`);
    }
  };
  const sendCanvasAction = async (text: string, owner: string) => {
    if (!owner) throw new Error("חסרה השיחה שאליה שייך הקנבס.");
    await coreApi("POST", `/v2/conversations/${encodePath(owner)}/runs`, {
      text, attachment_handles: [], provider_mode: provider, model_name: model, source: "tauri_desktop", is_voice: false,
    }, true);
    await refreshLists();
    if (activeIdRef.current === owner) await loadMessages(owner);
  };
  const cancel = async (runId = activeRun?.id) => {
    if (runId)
      await coreApi(
        "POST",
        `/v2/runs/${encodePath(runId)}/cancel`,
        {},
        true,
      );
    await refreshLists();
  };
  const toggleConversationDrawer = async () => {
    const open = !workspace.conversationDrawerOpen;
    const previous = workspace;
    const closesWorkbench =
      narrowWorkspace && open && workspace.workbenchOpen;
    dispatch(
      closesWorkbench
        ? { type: "activate-narrow-surface", surface: "conversations" }
        : { type: "set-conversations", open },
    );
    const patch = narrowWorkspace ? null : { workspace_sidebar_collapsed: !open };
    if (!patch) return;
    try {
      await saveUiPreferencePatch(patch);
    } catch (reason) {
      dispatch({
        type: "restore-layout",
        conversations: previous.conversationDrawerOpen,
        workbench: previous.workbenchOpen,
        tab: previous.activeWorkbenchTab,
      });
      setError(`לא ניתן לשמור את מצב תפריט הצד: ${String(reason)}`);
    }
  };
  const loadOlder = async () => {
    if (!page?.next_before_ordinal || !activeId) return;
    const sessionId = activeId;
    const revision = navigationRevision.current;
    const older = await coreApi<MessagePage>(
      "GET",
      `/v2/conversations/${encodePath(activeId)}/messages?limit=48&before=${page.next_before_ordinal}`,
    );
    if (activeIdRef.current !== sessionId || navigationRevision.current !== revision) return;
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
    await approvalQueue.resolve(approval, approved);
    await refreshLists().catch((reason) => setError(String(reason)));
  };
  const loadReasoning = async (nextProvider: string, nextModel: string, owner = activeIdRef.current) => {
    const data = await coreApi<{
      reasoning_effort: string;
      reasoning_options: ReasoningOption[];
    }>(
      "GET",
      `/v2/providers/${encodePath(nextProvider)}/reasoning?model=${encodeURIComponent(nextModel)}`,
    );
    if (owner === activeIdRef.current) {
      setReasoningEffort(data.reasoning_effort || "auto");
      setReasoningOptions(data.reasoning_options || []);
    }
    return data;
  };
  const selectFavoriteModel = async (item: FavoriteModel) => {
    const owner = activeId;
    const operation = modelOperations.current.catch(() => undefined).then(async () => {
    if (owner !== activeIdRef.current) return false;
    const previousProvider = provider;
    const previousModel = model;
    setProvider(item.provider);
    setModel(item.model);
    try {
      await coreApi(
        "PATCH",
        "/v2/settings",
        {
          values: {
            api_mode: item.provider,
            [`selected_${item.provider}_model`]: item.model,
            selected_model_source: {
              ...modelSelectionSource,
              [item.provider]: "user",
            },
            model_selection_provenance_version: 1,
          },
        },
        true,
      );
      setModelSelectionSource((current) => ({
        ...current,
        [item.provider]: "user",
      }));
      const reasoning = await loadReasoning(item.provider, item.model, owner);
      drafts.setSelection({ ...item, effort: reasoning.reasoning_effort || "auto" });
      return true;
    } catch (reason) {
      if (owner === activeIdRef.current) {
        setProvider(previousProvider); setModel(previousModel);
        setError(`לא ניתן להחליף מודל: ${String(reason)}`);
      }
      return false;
    }
    });
    modelOperations.current = operation;
    return operation;
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
      drafts.setSelection({ provider, model, effort: data.reasoning_effort });
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
  const setWorkbenchOpen = useCallback(
    (open: boolean, tab: WorkbenchTab | null = null) => {
      if (!open) requestAnimationFrame(() => workbenchTrigger.current?.focus());
      dispatch(
        open
          ? narrowWorkspace
            ? { type: "activate-narrow-surface", surface: "workbench", tab }
            : { type: "open-workbench", tab }
          : { type: "close-workbench" },
      );
    },
    [narrowWorkspace],
  );
  const openMessageCanvas = useCallback((canvasId: string) => {
    workbenchRef.current?.openCanvas(activeId, canvasId);
    setWorkbenchOpen(true);
  }, [activeId, setWorkbenchOpen]);
  const dismissWorkspaceOverlay = () => {
    if (workspace.workbenchOpen) setWorkbenchOpen(false);
    else if (workspace.conversationDrawerOpen)
      dispatch({ type: "set-conversations", open: false });
  };
  const beginWorkbenchResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (narrowWorkspace || !workspace.workbenchOpen) return;
      event.preventDefault();
      const sidebarWidth = workspace.conversationDrawerOpen ? 240 : 72;
      setWorkspaceResizing(true);
      const startX = event.clientX;
      const match = workspaceColumns(
        workspace,
        viewportWidth,
        workbenchWidth,
      ).match(/ (\d+)px$/);
      const startWidth = Number(match?.[1] || 480);
      const move = (next: PointerEvent) => {
        setWorkbenchWidth(
          clampWorkbenchResize(
            viewportWidth,
            sidebarWidth,
            startWidth + next.clientX - startX,
          ),
        );
      };
      const stop = () => {
        setWorkspaceResizing(false);
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", stop);
        window.removeEventListener("pointercancel", stop);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", stop, { once: true });
      window.addEventListener("pointercancel", stop, { once: true });
    },
    [narrowWorkspace, viewportWidth, workbenchWidth, workspace],
  );
  const persistWorkbench = useCallback(
    (snapshot: WorkbenchSnapshot) => {
      if (!bootstrapReady) return;
      setWorkbenchRestore(snapshot);
    },
    [bootstrapReady],
  );
  useEffect(() => {
    if (bootstrapReady && workbenchRestore) writeWorkbenchSession({ owner: initialWorkbench.owner, snapshot: workbenchRestore, open: workspace.workbenchOpen, expanded: workbenchExpanded });
  }, [bootstrapReady, workbenchRestore, workspace.workbenchOpen, workbenchExpanded, initialWorkbench.owner]);
  useEffect(() => {
    if (core.state === "ready")
      void invoke("desktop_set_voice_hotkey", { shortcut: voiceHotkey }).catch(
        (reason) => setError(`קיצור הקול אינו זמין: ${String(reason)}`),
      );
  }, [core.state, voiceHotkey]);
  useEffect(() => {
    void invoke("desktop_set_close_to_tray", { enabled: keepRunningInTray });
  }, [keepRunningInTray]);
  useEffect(() => {
    const count = attention.items.length;
    // Native commands can finish out of order; keep overlay updates ordered.
    unreadUpdate.current = unreadUpdate.current
      .then(async () => { await invoke("desktop_set_unread", { count }); })
      .catch((reason) => setError(`לא ניתן לעדכן את מונה המשימות: ${String(reason)}`));
  }, [attention.items.length]);
  useEffect(() => {
    for (const item of attention.items) {
      if (notifiedAttention.current.has(item.id)) continue;
      notifiedAttention.current.add(item.id);
      if (!foreground)
        void invoke("desktop_notify", {
          title: ["approval", "api_key"].includes(item.kind) ? "Smarti ממתין להתייחסותך" : "תגובה חדשה מ־Smarti",
          body: item.title,
          sessionId: item.session_id,
          runId: item.run_id,
        });
    }
  }, [attention.items, foreground]);
  useEffect(() => {
    let alive = true;
    const subscription = listen<{ command: string; sessionId?: string; runId?: string }>(
      "desktop://activation",
      ({ payload }) => {
        if (!alive) return;
        if (payload.sessionId) void selectConversation(payload.sessionId, payload.runId, payload.command === "notification");
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

  const startupPending = core.state !== "ready" || !healthOkay || !workspaceWindowReady || !legalChecked || Boolean(legalStatus?.accepted && !bootstrapReady);
  const startupRecovery = core.state === "ready" && (startupError || startupDelayed);
  useLayoutEffect(() => {
    updateStartupTheme(resolved);
    setStartupVisible(startupPending && !startupRecovery);
    if (!startupPending) void invoke("desktop_finish_startup").catch(() => setStartupError(true));
  }, [resolved, startupPending, startupRecovery]);
  if (startupPending) return startupRecovery ? <StartupFailure theme={resolved} failed={startupError} /> : null;

  if (legalStatus && !legalStatus.accepted) {
    return (
      <LegalAgreement
        status={legalStatus}
        theme={resolved}
        onAccepted={async () => {
          await coreApi(
            "POST",
            "/v2/management/legal",
            { accepted: true, version: legalStatus.version },
            true,
          );
          setLegalStatus({ ...legalStatus, accepted: true });
          setWorkspaceWindowReady(false);
          try {
            await bootstrap();
            setWorkspaceWindowReady(true);
          } catch (reason) {
            setStartupError(true);
            setError(String(reason));
          }
        }}
      />
    );
  }

  const openWorkbench = (tab: WorkbenchTab) => setWorkbenchOpen(true, tab);
  const icons = legacyAssets(resolved);
  return (
    <DesignSystemProvider theme={resolved} className="chat-design"><main
      className={`smarti-app theme-${resolved}`}
      dir="rtl"
      data-theme={resolved}
    >
      <WindowTitleBar />
      <section
        className={`workspace ${workspace.workbenchOpen && workbenchExpanded ? "is-workbench-expanded" : ""} ${workspace.workbenchOpen ? "has-workbench" : ""} ${narrowWorkspace ? "is-overlay-layout" : ""} ${workspaceResizing ? "is-resizing" : ""}`}
        inert={Boolean(managementSection)}
        data-layout={narrowWorkspace ? "overlay" : "split"}
        style={{
          "--workbench-track-width": `${workbenchExpanded && workspace.workbenchOpen ? viewportWidth - (workspace.conversationDrawerOpen ? 240 : 72) : workspaceWorkbenchWidth(workspace, viewportWidth, workbenchWidth)}px`,
          gridTemplateColumns: workbenchExpanded && workspace.workbenchOpen && !narrowWorkspace
            ? `${workspace.conversationDrawerOpen ? "var(--drawer-width)" : "var(--rail-width)"} 0px minmax(0, 1fr)`
            : workspaceColumns(workspace, viewportWidth, workbenchWidth),
        } as CSSProperties}
      >
        <button
          type="button"
          className={`workspace-overlay-backdrop ${narrowWorkspace && (workspace.conversationDrawerOpen || workspace.workbenchOpen) ? "is-active" : ""}`}
          aria-label="סגירת החלונית הפתוחה"
          aria-hidden={
            !narrowWorkspace ||
            (!workspace.conversationDrawerOpen && !workspace.workbenchOpen)
          }
          tabIndex={
            narrowWorkspace &&
            (workspace.conversationDrawerOpen || workspace.workbenchOpen)
              ? 0
              : -1
          }
          onClick={dismissWorkspaceOverlay}
        />
        <ChatSidebar open={workspace.conversationDrawerOpen} logo={icons.logo}
          conversations={conversations} activeId={activeId} query={query}
          loading={historyLoading} error={historyError}
          unread={id => attention.items.filter(item => item.session_id === id).length}
          onToggle={() => void toggleConversationDrawer()} onCreate={() => void createConversation()}
          onQuery={setQuery} onSelect={id => void selectConversation(id)}
          onManagement={openManagement} actions={item => conversationActions(item, {
            pin: item => void togglePinned(item).catch(reason => setError(String(reason))),
            rename: item => void renameConversation(item),
            export: item => void exportConversation(item).catch(reason => setError(String(reason))),
            remove: item => void deleteConversation(item),
          })} />
        <section className="chat-column" ref={chatMotionRef} aria-label="צ׳אט מרכזי" inert={workspace.workbenchOpen && (workbenchExpanded || narrowWorkspace) ? true : undefined}>
          <div className="chat-toolbar">
            <div className="chat-toolbar-controls" dir="rtl">
              <Menu fitContent label="פעולות שיחה" items={activeConversation ? conversationActions(activeConversation, {
                pin: item => void togglePinned(item).catch(reason => setError(String(reason))),
                rename: item => void renameConversation(item),
                export: item => void exportConversation(item).catch(reason => setError(String(reason))),
                remove: item => void deleteConversation(item),
              }) : []} />
              <IconButton icon="panel" variant="ghost"
                ref={workbenchTrigger} label={workspace.workbenchOpen ? "סגירת סביבת העבודה" : "פתיחת סביבת העבודה"}
                onClick={() => setWorkbenchOpen(!workspace.workbenchOpen)} />
            </div>
            {availableUpdateVersion && (
              <button
                type="button"
                className="chat-update-available"
                onClick={() => openManagement("settings_appearance")}
              >
                <Icon name="refresh" />
                עדכון {availableUpdateVersion}
              </button>
            )}
            <h1>{activeConversation?.title || "שיחה חדשה"}</h1>

          </div>
          {error && (
            <div className="chat-error">
              <Alert tone="danger" title="הפעולה לא הושלמה" action={<Button variant="ghost" onClick={() => setError("")}>סגירה</Button>}>
                {error}
              </Alert>
            </div>
          )}
          <div
            ref={chatViewportRef}
            className={`chat-stage ${messages.length || activeRun ? "has-messages" : ""}`}
          >
            <div className="chat-scroll-content">
            <div className="chat-messages">
            {page?.has_older && (
              <Button variant="ghost" onClick={() => void loadOlder().catch(reason => setError(String(reason)))}>
                טעינת {page.older_count} הודעות קודמות
              </Button>
            )}
            {!messages.length && !activeRun ? (
              <div className="chat-welcome">
                <h2>
                  {displayName
                    ? `היי ${displayName}, במה תרצה שאתמקד?`
                    : "במה תרצה שאתמקד?"}
                </h2>
              </div>
            ) : (
              <div className="message-list">
                {[...messages, ...(displayRun && !activeAssistantRecorded ? [{ role: "assistant" as const, content: streamAnswer(streams[displayRun.id] || displayRun.metadata?.stream) || displayRun.response_text || "", metadata: { run_id: displayRun.id, is_error: displayRun.status === "failed" } }] : [])].map((message, index) => {
                  const runId = String(message.metadata?.run_id || "");
                  const messageActive = Boolean(
                    message.role === "assistant" &&
                    activeRun &&
                    runId === activeRun.id,
                  );
                  return (
                    <RichMessage
                      key={message.role === "assistant" && runId ? `run-${runId}` : `${message.role}:${message.created_at || index}:${message.content}`}
                      message={message}
                      isNew={message.role === "user" && runId === newUserRun}
                      events={
                        message.role === "assistant" && runId
                          ? messageEvents.get(runId) || EMPTY_MESSAGE_EVENTS
                          : EMPTY_MESSAGE_EVENTS
                      }
                      active={messageActive}
                      runStatus={runs.find(run => run.id === runId)?.status}
                      stream={streams[runId] || runs.find(run => run.id === runId)?.metadata?.stream}
                      viewportHeight={scroll.height}
                      theme={resolved}
                      onOpenCanvas={openMessageCanvas}
                    />
                  );
                })}

              </div>
            )}
          <div className="chat-turn-space" aria-hidden="true" />
          </div>
          <div ref={chatFooterRef} className={`chat-input-panel ${flowingFooter ? "is-flowing" : ""}`}>
          <ConversationApprovals
            items={activeApprovals}
            busy={approvalQueue.busy}
            errors={approvalQueue.errors}
            onResolve={(approval, approved) => void resolveApproval(approval, approved)}
          />
          {activeApiKeyRequest && (
            <ApiKeyRequiredDialog
              key={`${activeApiKeyRequest.runId}:${activeApiKeyRequest.secretKey}`}
              request={activeApiKeyRequest}
              onCancel={() => cancel(activeApiKeyRequest.runId)}
            />
          )}
          <Dialog open={!!conversationDialog}
            title={conversationDialog?.kind === "rename" ? "שינוי שם שיחה" : "מחיקת שיחה"}
            initialFocus={conversationDialog?.kind === "delete" ? dialogCancel : undefined}
            onClose={() => { if (!dialogBusy) setConversationDialog(null); }}>
            <form onSubmit={event => { event.preventDefault(); void confirmConversationDialog(); }}>
              {dialogError && <Alert tone="danger" title={dialogError} />}
              {conversationDialog?.kind === "rename"
                ? <Field autoFocus label="שם חדש" value={renameValue} onChange={event => setRenameValue(event.target.value)} />
                : <p>למחוק את השיחה הזו לצמיתות?</p>}
              <footer className="sds-actions"><button ref={dialogCancel} type="button" className="sds-button" disabled={dialogBusy} onClick={() => setConversationDialog(null)}>ביטול</button><Button loading={dialogBusy} type="submit" variant={conversationDialog?.kind === "delete" ? "danger" : "primary"}>אישור</Button></footer>
            </form>
          </Dialog>
          <div className="chat-composer-panel">
          {scroll.hasNewContent && <button type="button" className={`chat-new-content ${activeRun ? "is-generating" : ""}`} aria-label="גלילה לסוף התשובה" onClick={scroll.follow}><span className="chat-down-arrow"><Icon name="arrow" /></span>{activeRun && <span className="chat-stream-dots" aria-hidden="true"><i/><i/><i/></span>}</button>}
          <Composer
            theme={resolved}
            conversationId={activeId} draft={drafts.draft.text} onDraftChange={drafts.setText}
            disabled={reconnecting || restoringModel}
            running={Boolean(activeRun)}
            attachments={attachments}
            provider={provider}
            model={model}
            favoriteModels={favoriteModels}
            reasoningEffort={reasoningEffort}
            reasoningOptions={reasoningOptions}
            autonomyMode={autonomyMode}
            localFastMode={localFastMode}
            onFavoriteModel={async item => { await selectFavoriteModel(item); }}
            onReasoningEffort={changeReasoning}
            onManageModels={trigger => openManagement("settings_ai", trigger)}
            onAutonomyMode={changeAutonomy}
            onLocalFastMode={changeLocalFastMode}
            onAttachments={setAttachments}
            onSend={send}
            onCancel={() => void cancel().catch(reason => setError(String(reason)))}
          />
          </div>
          </div>
          </div>
          </div>
          {!workspace.workbenchOpen &&
            browserActivity &&
            dismissedBrowserPreview !== browserActivity.workspaceId &&
            workbenchRestore?.tabs.some((tab) => tab.kind === "browser" && tab.id === browserActivity.workspaceId) &&
            !["", "about:blank"].includes(browserActivity.url) && (
              <BrowserPreviewCard activity={browserActivity}
                onOpen={() => {
                  workbenchRef.current?.activateTab(browserActivity.workspaceId);
                  setWorkbenchOpen(true);
                }}
                onDismiss={() => setDismissedBrowserPreview(browserActivity.workspaceId)}
              />
            )}
        </section>
        <aside
          className={`workbench ${workspace.workbenchOpen ? "is-open" : ""}`}
          aria-label="Workbench"
          aria-hidden={!workspace.workbenchOpen}
          inert={!workspace.workbenchOpen ? true : undefined}
        >
          {workspace.workbenchOpen && !narrowWorkspace && !workbenchExpanded && (
            <div
              className="workbench-resize-handle"
              role="separator"
              aria-label="שינוי רוחב אזור העבודה"
              aria-orientation="vertical" tabIndex={0} aria-valuemin={320} aria-valuemax={viewportWidth - (workspace.conversationDrawerOpen ? 240 : 72) - 320} aria-valuenow={workspaceWorkbenchWidth(workspace, viewportWidth, workbenchWidth)}
              onKeyDown={event => {
                if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                  event.preventDefault(); const sidebar = workspace.conversationDrawerOpen ? 240 : 72;
                  setWorkbenchWidth(clampWorkbenchResize(viewportWidth, sidebar, event.key === "Home" ? 320 : event.key === "End" ? viewportWidth : workspaceWorkbenchWidth(workspace, viewportWidth, workbenchWidth) + (event.key === "ArrowRight" ? 24 : -24)));
                }
              }}
              onPointerDown={beginWorkbenchResize}
              onDoubleClick={() => setWorkbenchWidth(null)}
            />
          )}
          {bootstrapReady && (
            <WorkbenchSurface
              ref={workbenchRef}
              initial={workspace.activeWorkbenchTab}
              visible={workspace.workbenchOpen && !managementSection}
              motionRevision={`${workspace.workbenchOpen}:${narrowWorkspace}:${workspace.conversationDrawerOpen}:${workbenchExpanded}`}
              restored={workbenchRestore}
              onStateChange={persistWorkbench}
              onBrowserActivity={setBrowserActivity}
              sessionId={activeId}
              onCanvasAction={sendCanvasAction}
              onClose={() => setWorkbenchOpen(false)}
              closeIcon={icons.workbenchClose}
              showCloseControl={narrowWorkspace || workbenchExpanded}
              owner={initialWorkbench.owner}
              expanded={workbenchExpanded}
              onToggleExpanded={() => setWorkbenchExpanded(value => !value)}
            />
          )}
        </aside>
      </section>
      {managementSection && (
        <ManagementCenter
          initial={managementSection}
          returnFocus={managementReturnFocus.current}
          onClose={() => setManagementSection(null)}
          onOpenWorkbench={(tab) => {
            setManagementSection(null);
            openWorkbench(tab);
          }}
          setTheme={setPreference}
          theme={resolved}
        />
      )}
    </main></DesignSystemProvider>
  );
}
