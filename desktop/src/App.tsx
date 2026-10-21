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
  loadRunEventHistory,
  mergeActivityEvents,
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
import { CoreApiError, coreApi, encodePath } from "./coreApi";
import { RunSubmission } from "./runSubmission";
import { composerInteractionRevision } from "./composerFocus";
import { type CoreSnapshot } from "./coreState";
import {
  parseThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "./designSystem";
import { RichMessage } from "./RichMessage";
import { useLiveConversation } from "./live/useLiveConversation";
import { liveTimeline } from "./live/liveTimeline";
import { LiveOrb } from "./live/LiveOrb";
import { Alert, Button, DesignSystemProvider, Dialog, Field, Icon, IconButton, Menu } from "./design-system";
import { ChatSidebar, conversationActions } from "./ChatSidebar";
import { SearchDialog } from "./SearchDialog";
import { rememberConversationVisit } from "./searchState";
import { useChatDrafts, readActiveConversation, rememberActiveConversation, restoreActiveConversation, beginChatLaunch } from "./chatDrafts";
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
import { interfaceReady } from "./interfaceModule";
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
  onResolved,
}: {
  request: ApiKeyRequest;
  onCancel: () => Promise<void>;
  onResolved?: (interaction: number) => void;
}) {
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [validating, setValidating] = useState(false);
  const providing = useRef(false);
  const provide = async () => {
    const value = draft.trim();
    if (!value || providing.current) return;
    providing.current = true; setValidating(true);
    const interaction = composerInteractionRevision();
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
      onResolved?.(interaction);
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
    const interaction = composerInteractionRevision();
    try { await onCancel(); onResolved?.(interaction); } catch (reason) { setStatus(`לא ניתן לבטל: ${String(reason)}`); }
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
  const [runSubmission] = useState(() => new RunSubmission());
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
  const [composerFocusRequest, setComposerFocusRequest] = useState(0);
  const requestComposerFocus = useCallback(() => setComposerFocusRequest(value => value + 1), []);
  const [activeId, setActiveIdState] = useState(readActiveConversation);
  const activeIdRef = useRef(activeId);
  const messageRequest = useRef(0);
  const loadedAttentionIds = useRef(new Set<string>());
  const listRequest = useRef(0);
  const runtimeListRequest = useRef(0);
  const navigationRevision = useRef(0);
  const navigationTarget = useRef("");
  const navigationOrdinal = useRef<number | undefined>(undefined);
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
  const [syncingSubmissions, setSyncingSubmissions] = useState<Set<string>>(() => new Set());
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streams, setStreams] = useState<Record<string, StreamState>>({});
  const approvalQueue = useApprovalQueue();
  const [searchOpen, setSearchOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const drafts = useChatDrafts(activeId, setError);
  const { attachments } = drafts.draft;
  const setAttachments = drafts.setAttachments;
  const attention = useConversationAttention(setError);
  const [foreground, setForeground] = useState(() => !document.hidden && document.hasFocus());
  const [availableUpdateVersion, setAvailableUpdateVersion] = useState("");
  const [reconnecting, setReconnecting] = useState(false);
  const [modelSelection, setModelSelection] = useState({
    provider: "", model: "", reasoningEffort: "", reasoningOptions: [] as ReasoningOption[],
  });
  const { provider, model, reasoningEffort, reasoningOptions } = modelSelection;
  const selectionRef = useRef(modelSelection);
  const confirmedSelection = useRef(modelSelection);
  const selectionVersion = useRef(0), modelGeneration = useRef(0), pendingSelectionWrites = useRef(0);
  const selectionSave = useRef<Promise<boolean>>(Promise.resolve(true));
  const renderedSelectionSave = selectionSave.current;
  const renderedModelGeneration = modelGeneration.current;
  const applySelection = useCallback((next: typeof modelSelection) => {
    selectionRef.current = next;
    setModelSelection(next);
  }, []);
  const [displayName, setDisplayName] = useState("");
  const [favoriteModels, setFavoriteModels] = useState<FavoriteModel[]>([]);
  const modelSelectionSource = useRef<Record<string, unknown>>({});
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
  const chatMotionRef = useChatLayoutMotion(`${workspace.workbenchOpen}:${workspace.conversationDrawerOpen}:${narrowWorkspace}:${workbenchExpanded}`, workspaceResizing);
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
  const modelOperations = useRef<Promise<boolean>>(Promise.resolve(true));
  const reasoningOperations = useRef<Promise<unknown>>(Promise.resolve());
  const latestReasoningWrites = useRef(new Map<string, number>());
  const pendingReasoning = useRef(new Map<string, { effort: string; previous: string; settled: boolean; endpoint?: string }>());
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
        const option = available.reasoning_options.find(option => option.value === selected.effort);
        if (option && (selected.provider !== "local" || selected.endpoint === option.endpoint))
          await coreApi("POST", `/v2/providers/${encodePath(selected.provider)}/reasoning`, { model: selected.model, effort: selected.effort, ...(option.endpoint ? { endpoint: option.endpoint } : {}) }, true);
      }
      const selectionTicket = selectionVersion.current;
      const latest = await coreApi<Bootstrap>("GET", "/v2/bootstrap");
      if (!disposed && selectionTicket === selectionVersion.current) { syncSettings(latest, selectionTicket); drafts.setSelection({ provider: selected.provider, model: selected.model, effort: latest.chat_models.reasoning_effort || "", endpoint: latest.chat_models.reasoning_options?.[0]?.endpoint }); }
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
    const targetOrdinal = navigationOrdinal.current;
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
          (targetOrdinal !== undefined && !value.messages.some(message => message.message_id === `${sessionId}:${targetOrdinal}`)) ||
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
    navigationOrdinal.current = undefined;
    setLoadedNavigationRevision(revision);
    loadedAttentionIds.current = new Set(value.unread_attention_ids || []);
    setPage(value);
    setMessages(mergeMessages(messagesRef.current, value.messages));
  }, []);
  const refreshConversations = useCallback(async (search = "") => {
    const request = ++listRequest.current;
    const data = await coreApi<ConversationList>(
      "GET", `/v2/conversations?q=${encodeURIComponent(search)}&limit=100`,
    );
    if (request !== listRequest.current) return null;
    // A search can open a conversation beyond the sidebar's first page.
    // Keep its title and actions backed by current Core metadata on refresh.
    const selected = activeIdRef.current;
    if (selected && !data.items.some(item => item.id === selected)) {
      try {
        const detail = await coreApi<{ conversation: Conversation | null }>("GET", `/v2/conversations/${encodePath(selected)}`);
        if (request !== listRequest.current) return null;
        if (selected === activeIdRef.current && detail.conversation) data.items.push(detail.conversation);
      } catch (reason) {
        if (!(reason instanceof CoreApiError && reason.status === 404)) throw reason;
        if (selected === activeIdRef.current) { setActiveId(""); requestComposerFocus(); }
      }
    }
    if (request !== listRequest.current) return null;
    setConversations(data.items.filter(item => item.message_count !== 0 || item.is_busy));
    attention.replace(data.attention_items);
    return data;
  }, [attention.replace, setActiveId, requestComposerFocus]);
  const refreshLists = useCallback(
    async (search = "") => {
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
  const syncSettings = useCallback((data: Bootstrap, selectionTicket = selectionVersion.current) => {
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
    // A refresh started before a local intent must not undo its optimistic UI,
    // even if its response arrives after the save has completed.
    if (!pendingSelectionWrites.current && selectionTicket === selectionVersion.current) {
      ++selectionVersion.current; ++modelGeneration.current;
      const next = { provider: data.chat_models.provider, model: data.chat_models.model,
        reasoningEffort: data.chat_models.reasoning_effort || "", reasoningOptions: data.chat_models.reasoning_options || [] };
      confirmedSelection.current = next;
      selectionSave.current = Promise.resolve(true);
      applySelection(next);
      modelSelectionSource.current = values.selected_model_source && typeof values.selected_model_source === "object"
        ? values.selected_model_source as Record<string, unknown> : {};
    }
    setFavoriteModels(favorites);
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
  }, [setPreference, applySelection]);
  useEffect(() => {
    if (core.state !== "ready") return;
    let request = 0;
    let disposed = false;
    const unsubscribe = subscribeSettingsChanges(() => {
      const current = ++request;
      const selectionTicket = selectionVersion.current;
      void coreApi<Bootstrap>("GET", "/v2/bootstrap")
        .then((data) => {
          if (!disposed && current === request) syncSettings(data, selectionTicket);
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
    const selectionTicket = selectionVersion.current;
    const data = await coreApi<Bootstrap>("GET", "/v2/bootstrap");
    const values = data.settings?.values || {};
    const preferences =
      values.ui_preferences && typeof values.ui_preferences === "object"
        ? (values.ui_preferences as Record<string, unknown>)
        : {};
    if (revision === settingsRevision()) syncSettings(data, selectionTicket);
    setConversations(data.conversations.filter(item => item.message_count !== 0 || item.is_busy));
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
    const freshLaunch = beginChatLaunch(await invoke<string | null>("desktop_launch_id"));
    const first = restoreActiveConversation(data.conversations, freshLaunch ? "" : activeIdRef.current);
    setActiveId(first);
    requestComposerFocus();
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
      if (document.visibilityState === "hidden" || innerWidth <= 0 || innerHeight <= 0) return;
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
      if (document.visibilityState === "hidden" || innerWidth <= 0 || innerHeight <= 0) return;
      setWorkspaceResizing(true);
      cancelAnimationFrame(frame);
      clearTimeout(settled);
      frame = requestAnimationFrame(() => applyResponsiveLayout(false));
      settled = window.setTimeout(() => setWorkspaceResizing(false), 150);
    };
    setWorkspaceResizing(false);
    applyResponsiveLayout(true);
    window.addEventListener("resize", responsive);
    document.addEventListener("visibilitychange", responsive);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(settled);
      window.removeEventListener("resize", responsive);
      document.removeEventListener("visibilitychange", responsive);
    };
  }, [uiPreferences.workspace_sidebar_collapsed]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (core.state === "ready") {
        setHistoryLoading(true);
        setHistoryError("");
        void refreshLists()
          .catch((reason) => {
            setHistoryError(`לא ניתן לטעון את השיחות: ${String(reason)}`);
            setReconnecting(true);
          })
          .finally(() => setHistoryLoading(false));
      }
    }, legacyUi.historySearchDebounceMs);
    return () => clearTimeout(timer);
  }, [core.state]);
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
    if (!bootstrapReady || !activeId || core.state !== "ready") return;
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
  }, [activeId, bootstrapReady, core.state, navigation, loadMessages, refreshLists]);
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
    if (!newUserRun || !messages.some(message => message.role === "user" && (message.metadata?.live_message_id || message.metadata?.run_id) === newUserRun)) return;
    const timer = window.setTimeout(() => setNewUserRun(""), 240);
    return () => window.clearTimeout(timer);
  }, [newUserRun, messages]);
  useEffect(() => {
    if (!activeRunId || core.state !== "ready") return;
    let stopped = false;
    let timer = 0;
    const load = () => loadRunEventHistory(
      after => coreApi<{ items: RunEvent[] }>("GET", `/v2/runs/${encodePath(activeRunId)}/events?after_sequence=${after}&limit=500`),
      items => setEvents(current => mergeActivityEvents(current, items)),
      () => !stopped,
    ).catch(() => { if (!stopped) timer = window.setTimeout(() => void load(), 1000); });
    void load();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [activeRunId, core.state, core.generation]);
  useEffect(() => {
    if (core.state !== "ready" || !bootstrapReady) return;
    let stopped = false;
    let polling = false;
    let liveEvents = true;
    const poll = async () => {
      if (polling || stopped) return;
      polling = true;
      let delay = 0;
      try {
        const cursor = Number(sessionStorage.getItem(cursorKey) || 0);
        let data: { items: RunEvent[] };
        try {
          data = await coreApi("GET", `/v2/events/${liveEvents ? "live" : "replay"}?after_event_id=${cursor}`);
        } catch (reason) {
          // Vite can update React while the supervised Python process still
          // runs the previous API. Missing live support is not a disconnection.
          if (!liveEvents || !(reason instanceof CoreApiError) || ![404, 405].includes(reason.status)) throw reason;
          liveEvents = false;
          data = await coreApi("GET", `/v2/events/replay?after_event_id=${cursor}`);
        }
        if (stopped) return;
        delay = liveEvents ? (data.items.length ? 0 : 250) : 1200;
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
          if (structural.length) setEvents((current) => mergeActivityEvents(current, structural));
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
  }, [core.generation, core.state, bootstrapReady, activeId, foreground, refreshConversations, refreshLists, loadMessages]);
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
        void desktopActions.current.createConversation();
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
      item.session_id === activeId && !item.metadata?.live_permission && ACTIVE_RUN_STATES.has(item.status),
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
  const promptNavigationRevision = navigationRevision.current;
  const restorePromptFocus = (interaction: number) => {
    if (activeIdRef.current === activeId && navigationRevision.current === promptNavigationRevision &&
        interaction === composerInteractionRevision()) requestComposerFocus();
  };
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
    ["completed", "failed", "cancelled", "interrupted"].includes(run.status));
  const displayRun = activeRun || terminalReply;
  const activeAssistantRecorded = Boolean(displayRun && messages.some(message =>
    message.role === "assistant" && message.metadata?.run_id === displayRun.id));
  const live = useLiveConversation({ conversation: activeId, provider, model, attachments,
    onConversation: id => setActiveId(id),
    onMessage: message => setMessages(current => mergeMessages(current, [message])),
    onNewUserMessage: setNewUserRun,
    onRefresh: () => { void refreshLists(); if (activeIdRef.current) void loadMessages(activeIdRef.current); },
    onError: setError,
  });
  const timeline = liveTimeline([...messages, ...(displayRun && !activeAssistantRecorded && !displayRun.metadata?.live_task_id
    ? [{ role: "assistant" as const, content: streamAnswer(streams[displayRun.id] || displayRun.metadata?.stream) || displayRun.response_text || "", metadata: { run_id: displayRun.id, user_language: displayRun.metadata?.user_language, is_error: displayRun.status === "failed" } }] : [])], runs.filter(run => run.session_id === activeId));

  const createConversation = async () => {
    if (!restoringModel && provider && model) drafts.setSelection({ provider, model, effort: reasoningEffort, endpoint: reasoningOptions.find(option => option.value === reasoningEffort)?.endpoint });
    ++navigationRevision.current;
    navigationTarget.current = ""; navigationOrdinal.current = undefined;
    setNavigation(null);
    setManagementSection(null); setManagementOpen(false); setSearchOpen(false);
    setActiveId(""); setMessages([]); setPage(null);
    if (narrowWorkspaceRef.current) dispatch({ type: "set-conversations", open: false });
    if (narrowWorkspaceRef.current || workbenchExpanded) dispatch({ type: "close-workbench" });
    requestComposerFocus();
  };
  const selectConversation = async (id: string, runId?: string, alignReply = false, messageOrdinal?: number) => {
    rememberConversationVisit(id);
    if (!restoringModel && provider && model) drafts.setSelection({ provider, model, effort: reasoningEffort, endpoint: reasoningOptions.find(option => option.value === reasoningEffort)?.endpoint });
    setManagementSection(null);
    setManagementOpen(false);
    navigationTarget.current = runId || "";
    navigationOrdinal.current = messageOrdinal;
    setNavigation({ sessionId: id, revision: ++navigationRevision.current, runId, alignReply, messageOrdinal });
    setActiveId(id);
    if (narrowWorkspaceRef.current || workbenchExpanded) dispatch({ type: "close-workbench" });
    requestComposerFocus();
    if (narrowWorkspaceRef.current)
      dispatch({ type: "set-conversations", open: false });
  };
  const renameConversation = async (item: Conversation) => {
    setRenameValue(item.title);
    setDialogError(""); setConversationDialog({ kind: "rename", item });
  };
  const desktopActions = useRef({ createConversation, selectConversation });
  desktopActions.current = { createConversation, selectConversation };
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
        requestComposerFocus();
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
    const sourceId = activeIdRef.current, revision = navigationRevision.current;
    const intent = composerInteractionRevision();
    const submittedDraft = drafts.snapshot(sourceId);
    const submittedAttachments = [...submittedDraft.attachments];
    const unavailable = submittedAttachments.find(item => item.error);
    if (unavailable) throw new Error(`${unavailable.name}: ${unavailable.error}`);
    if (live.active) {
      await live.send(text, submittedAttachments);
      drafts.accept(sourceId, sourceId, submittedDraft, text, activeIdRef.current === sourceId);
      return;
    }
    if (!await renderedSelectionSave) throw new Error("בחירת המודל לא נשמרה. יש לבחור מודל לפני השליחה.");
    await reasoningOperations.current;
    const submitted = await runSubmission.submit({
      sessionId: sourceId, text, attachments: submittedAttachments, provider, model, isVoice,
    });
    const sessionId = submitted.session_id;
    setSyncingSubmissions(current => new Set(current).add(sessionId));
    const follow = activeIdRef.current === sourceId && navigationRevision.current === revision;
    const saved = drafts.accept(sourceId, sessionId, submittedDraft, text, follow);
    if (saved) runSubmission.acknowledge(submitted);
    if (follow) {
      setNewUserRun(submitted.run_id || "");
      if (!sourceId) setActiveId(sessionId);
      if (intent === composerInteractionRevision()) requestComposerFocus();
    }
    // A refresh failure must not restore a draft whose run was already accepted.
    void (async () => { try {
      await refreshLists();
      if (activeIdRef.current === sessionId) await loadMessages(sessionId);
    } catch (reason) {
      setError(`ההודעה נשלחה, אך רענון התצוגה נכשל: ${String(reason)}`);
    } finally {
      setSyncingSubmissions(current => { const next = new Set(current); next.delete(sessionId); return next; });
    } })();
  };
  const sendCanvasAction = async (text: string, owner: string) => {
    if (!owner) throw new Error("חסרה השיחה שאליה שייך הקנבס.");
    if (!await renderedSelectionSave) throw new Error("בחירת המודל לא נשמרה. יש לבחור מודל לפני השליחה.");
    await reasoningOperations.current;
    const result = await runSubmission.submit({ sessionId: owner, text, attachments: [], provider, model });
    runSubmission.acknowledge(result);
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
    const interaction = composerInteractionRevision();
    if (await approvalQueue.resolve(approval, approved)) restorePromptFocus(interaction);
    await refreshLists().catch((reason) => setError(String(reason)));
  };
  const loadReasoning = async (nextProvider: string, nextModel: string, owner = activeIdRef.current) => {
    const ticket = selectionVersion.current;
    const key = JSON.stringify([nextProvider, nextModel]), pendingAtRead = pendingReasoning.current.get(key);
    const data = await coreApi<{
      reasoning_effort: string;
      reasoning_options: ReasoningOption[];
    }>(
      "GET",
      `/v2/providers/${encodePath(nextProvider)}/reasoning?model=${encodeURIComponent(nextModel)}`,
    );
    const current = selectionRef.current;
    const requested = pendingReasoning.current.get(key) || pendingAtRead;
    const requestedSupported = requested && data.reasoning_options.some(option => option.value === requested.effort && (nextProvider !== "local" || option.endpoint === requested.endpoint));
    const acknowledged = requestedSupported && requested.settled ? requested.effort : data.reasoning_effort || "";
    if (owner === activeIdRef.current && ticket === selectionVersion.current &&
        current.provider === nextProvider && current.model === nextModel) {
      const effort = requestedSupported ? requested.effort : acknowledged;
      const next = { ...current, reasoningEffort: effort, reasoningOptions: data.reasoning_options || [] };
      applySelection(next);
      if (confirmedSelection.current.provider === nextProvider && confirmedSelection.current.model === nextModel)
        confirmedSelection.current = { ...next, reasoningEffort: acknowledged };
    }
    return { ...data, reasoning_effort: acknowledged };
  };
  const selectFavoriteModel = async (item: FavoriteModel) => {
    const owner = activeId;
    const generation = ++modelGeneration.current;
    ++selectionVersion.current;
    const ownsSelection = () => owner === activeIdRef.current && generation === modelGeneration.current;
    // Replace the complete contract at once; never offer the previous model's
    // stops under the new name. Read its local contract before the slower save.
    applySelection({ ...item, reasoningEffort: "", reasoningOptions: [] });
    ++pendingSelectionWrites.current;
    let loadedContract: Awaited<ReturnType<typeof loadReasoning>> | undefined;
    const contract = loadReasoning(item.provider, item.model, owner).then(data => { loadedContract = data; }).catch(reason => {
      if (ownsSelection()) setError(`לא ניתן לטעון אפשרויות חשיבה: ${String(reason)}`);
    });
    const operation = modelOperations.current.catch(() => undefined).then(async () => {
    if (owner !== activeIdRef.current) return false;
    try {
      await coreApi(
        "PATCH",
        "/v2/settings",
        {
          values: {
            api_mode: item.provider,
            [`selected_${item.provider}_model`]: item.model,
            selected_model_source: {
              ...modelSelectionSource.current,
              [item.provider]: "user",
            },
            model_selection_provenance_version: 1,
          },
        },
        true,
      );
      modelSelectionSource.current = { ...modelSelectionSource.current, [item.provider]: "user" };
      confirmedSelection.current = { ...item, reasoningEffort: loadedContract?.reasoning_effort || "",
        reasoningOptions: loadedContract?.reasoning_options || [] };
      return true;
    } catch (reason) {
      if (ownsSelection()) {
        ++selectionVersion.current; ++modelGeneration.current;
        const previous = confirmedSelection.current;
        selectionSave.current = Promise.resolve(true);
        applySelection(previous);
        if (!previous.reasoningOptions.length && previous.model)
          void loadReasoning(previous.provider, previous.model, owner).catch(() => {});
        setError(`לא ניתן להחליף מודל: ${String(reason)}`);
      }
      return false;
    }
    });
    modelOperations.current = operation;
    selectionSave.current = operation;
    return Promise.all([operation, contract]).then(([accepted]) => {
      if (accepted && ownsSelection()) drafts.setSelection({ ...item, effort: selectionRef.current.reasoningEffort, endpoint: selectionRef.current.reasoningOptions[0]?.endpoint });
      return accepted;
    }).finally(() => { --pendingSelectionWrites.current; });
  };
  const changeReasoning = async (effort: string) => {
    const owner = activeId;
    const generation = renderedModelGeneration;
    const ownsSelection = () => owner === activeIdRef.current && generation === modelGeneration.current &&
      provider === selectionRef.current.provider && model === selectionRef.current.model;
    const requestedOption = reasoningOptions.find(option => option.value === effort);
    if (!requestedOption) return;
    const ticket = ++selectionVersion.current, key = JSON.stringify([provider, model]);
    latestReasoningWrites.current.set(key, ticket);
    const pendingPrevious = pendingReasoning.current.get(key);
    const requested = { effort, previous: pendingPrevious?.endpoint === requestedOption.endpoint ? pendingPrevious?.previous || reasoningEffort : reasoningEffort, settled: false, endpoint: requestedOption.endpoint };
    pendingReasoning.current.set(key, requested);
    const ownsModel = () => owner === activeIdRef.current && provider === selectionRef.current.provider && model === selectionRef.current.model &&
      (provider !== "local" || requestedOption.endpoint === selectionRef.current.reasoningOptions[0]?.endpoint);
    if (ownsSelection()) {
      applySelection({ ...selectionRef.current, reasoningEffort: effort });
      drafts.setSelection({ provider, model, effort, endpoint: requestedOption.endpoint });
    }
    const modelSave = renderedSelectionSave;
    ++pendingSelectionWrites.current;
    const operation = reasoningOperations.current.catch(() => undefined).then(async () => {
    // Model selection and effort writes share a persistence barrier. Keep the
    // newest unsent effort per model instead of writing every intermediate stop.
    if (!await modelSave) {
      if (latestReasoningWrites.current.get(key) === ticket) pendingReasoning.current.delete(key);
      return;
    }
    if (latestReasoningWrites.current.get(key) !== ticket) return;
    try {
      const data = await coreApi<{ reasoning_effort: string }>(
        "POST",
        `/v2/providers/${encodePath(provider)}/reasoning`,
        { model, effort, ...(requestedOption.endpoint ? { endpoint: requestedOption.endpoint } : {}) },
        true,
      );
      if (confirmedSelection.current.provider === provider && confirmedSelection.current.model === model &&
          (provider !== "local" || requestedOption.endpoint === confirmedSelection.current.reasoningOptions[0]?.endpoint))
        confirmedSelection.current = { ...confirmedSelection.current, reasoningEffort: data.reasoning_effort };
      requested.effort = data.reasoning_effort;
      requested.settled = true;
      const pending = pendingReasoning.current.get(key);
      if (pending) pending.previous = data.reasoning_effort;
      if (latestReasoningWrites.current.get(key) === ticket) pendingReasoning.current.delete(key);
      if (ownsModel() && latestReasoningWrites.current.get(key) === ticket) {
        applySelection({ ...selectionRef.current, reasoningEffort: data.reasoning_effort });
        drafts.setSelection({ provider, model, effort: data.reasoning_effort, endpoint: requestedOption.endpoint });
      }
    } catch (reason) {
      requested.effort = requested.previous;
      requested.settled = true;
      if (latestReasoningWrites.current.get(key) === ticket) pendingReasoning.current.delete(key);
      if (ownsModel() && latestReasoningWrites.current.get(key) === ticket) {
        const previous = requested.previous;
        applySelection({ ...selectionRef.current, reasoningEffort: previous });
        drafts.setSelection({ provider, model, effort: previous, endpoint: requestedOption.endpoint });
        setError(`לא ניתן לעדכן עוצמת חשיבה: ${String(reason)}`);
      }
    }
    }).finally(() => { --pendingSelectionWrites.current; });
    reasoningOperations.current = operation;
    return operation;
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
      if (!open && (narrowWorkspace || workbenchExpanded)) requestComposerFocus();
      else if (!open) requestAnimationFrame(() => workbenchTrigger.current?.focus());
      dispatch(
        open
          ? narrowWorkspace
            ? { type: "activate-narrow-surface", surface: "workbench", tab }
            : { type: "open-workbench", tab }
          : { type: "close-workbench" },
      );
    },
    [narrowWorkspace, workbenchExpanded, requestComposerFocus],
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
        if (payload.sessionId) void desktopActions.current.selectConversation(payload.sessionId, payload.runId, payload.command === "notification");
        if (payload.command === "new-chat") void desktopActions.current.createConversation();
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

  useEffect(() => {
    let alive = true;
    const subscription = listen<{ workspaceId: string; tabId: string; sessionId?: string; mode: string; operation?: string; requestId?: string }>("browser://presentation", ({ payload }) => {
      if (!alive) return;
      const apply = async () => {
        if (payload.mode === "visible") {
          workbenchRef.current?.openBrowser(payload.workspaceId);
          setDismissedBrowserPreview("");
          setWorkbenchOpen(true);
          if (payload.operation === "expand") setWorkbenchExpanded(true);
          else if (payload.operation === "split") setWorkbenchExpanded(false);
          try { await invoke("browser_activate", { tabId: payload.tabId }); }
          catch { return; }
        } else {
          if (payload.mode === "hidden" && workbenchRestore?.active === payload.workspaceId) setWorkbenchOpen(false);
          setDismissedBrowserPreview(payload.mode === "hidden" ? payload.workspaceId : "");
        }
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
        if (payload.requestId) void invoke("browser_presentation_ack", { requestId: payload.requestId }).catch(() => undefined);
      };
      if (payload.sessionId && payload.sessionId !== activeId) {
        // Quiet/background work in another conversation must not move the user.
        if (payload.mode !== "visible") return;
        void selectConversation(payload.sessionId)
          .then(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())))
          .then(apply).catch(() => undefined);
      } else void apply().catch(() => undefined);
    });
    return () => { alive = false; void subscription.then(dispose => dispose()); };
  }, [activeId, setWorkbenchOpen, workbenchRestore?.active]);

  const startupPending = core.state !== "ready" || !healthOkay || !workspaceWindowReady || !legalChecked || Boolean(legalStatus?.accepted && !bootstrapReady);
  const startupRecovery = core.state === "ready" && (startupError || startupDelayed);
  useLayoutEffect(() => {
    updateStartupTheme(resolved);
    setStartupVisible(startupPending && !startupRecovery);
    if (!startupPending) {
      interfaceReady();
      void invoke("desktop_finish_startup").catch(() => setStartupError(true));
    }
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
        <ChatSidebar open={workspace.conversationDrawerOpen} resizing={workspaceResizing} logo={icons.logo}
          conversations={conversations} activeId={activeId}
          loading={historyLoading} error={historyError}
          unread={id => attention.items.filter(item => item.session_id === id).length}
          onToggle={() => void toggleConversationDrawer()} onCreate={() => void createConversation()}
          onSearch={() => setSearchOpen(true)} onSelect={id => void selectConversation(id)}
          onManagement={openManagement} actions={item => conversationActions(item, {
            pin: item => void togglePinned(item).catch(reason => setError(String(reason))),
            rename: item => void renameConversation(item),
            export: item => void exportConversation(item).catch(reason => setError(String(reason))),
            remove: item => void deleteConversation(item),
          })} />
        <section className="chat-column" ref={chatMotionRef} aria-label="צ׳אט מרכזי" inert={workspace.workbenchOpen && (workbenchExpanded || narrowWorkspace) ? true : undefined}>
          <div className="chat-toolbar">
            <div className="chat-toolbar-controls" dir="rtl">
              {activeConversation && <Menu fitContent label="פעולות שיחה" items={conversationActions(activeConversation, {
                pin: item => void togglePinned(item).catch(reason => setError(String(reason))),
                rename: item => void renameConversation(item),
                export: item => void exportConversation(item).catch(reason => setError(String(reason))),
                remove: item => void deleteConversation(item),
              })} />}
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
                    ? `היי ${displayName}, במה אוכל לעזור?`
                    : "היי, במה אוכל לעזור?"}
                </h2>
              </div>
            ) : (
              <div className="message-list">
                {timeline.map((message, index) => {
                  const runId = String(message.metadata?.run_id || "");
                  const messageActive = Boolean(
                    message.role === "assistant" &&
                    runs.some(run => run.id === runId && ACTIVE_RUN_STATES.has(run.status)),
                  );
                  return (
                    <RichMessage
                      key={String(message.metadata?.live_answer_id || message.metadata?.live_message_id || message.message_id || (message.role === "assistant" && runId ? `run-${runId}` : `${message.role}:${message.created_at || index}:${message.content}`))}
                      message={message}
                      isNew={message.role === "user" && (message.metadata?.live_message_id || runId) === newUserRun}
                      events={
                        message.role === "assistant" && runId
                          ? messageEvents.get(runId) || EMPTY_MESSAGE_EVENTS
                          : EMPTY_MESSAGE_EVENTS
                      }
                      active={messageActive || Boolean(message.metadata?.live_partial)}
                      runStatus={runs.find(run => run.id === runId)?.status}
                      providerMode={runs.find(run => run.id === runId)?.metadata?.provider_mode}
                      stream={message.role === "assistant" ? streams[runId] || runs.find(run => run.id === runId)?.metadata?.stream : undefined}
                      viewportHeight={scroll.height}
                      theme={resolved}
                      onOpenCanvas={openMessageCanvas}
                      pauseRequested={Boolean(runs.find(run => run.id === runId)?.metadata?.pause_requested)}
                      paused={Boolean(runs.find(run => run.id === runId)?.metadata?.paused)}
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
              onResolved={restorePromptFocus}
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
          <div className={`chat-composer-panel${live.ready ? " has-live-orb" : ""}`}>
          {scroll.hasNewContent && <button type="button" className={`chat-new-content ${activeRun ? "is-generating" : ""}`} aria-label="גלילה לסוף התשובה" onClick={scroll.follow}><span className="chat-down-arrow"><Icon name="arrow" /></span>{activeRun && <span className="chat-stream-dots" aria-hidden="true"><i/><i/><i/></span>}</button>}
          {live.ready && <LiveOrb state={live.orbState} level={live.level} />}
          <Composer
            live={live}
            theme={resolved}
            focusRequest={composerFocusRequest}
            focusAllowed={!managementSection && !searchOpen && !conversationDialog && !activeApiKeyRequest && !activeApprovals.length && !(workspace.workbenchOpen && (workbenchExpanded || narrowWorkspace)) && !(narrowWorkspace && workspace.conversationDrawerOpen)}
            conversationId={activeId} draft={drafts.draft.text} onDraftChange={drafts.setText}
            disabled={reconnecting || restoringModel}
            running={Boolean(activeRun)}
            sendPending={syncingSubmissions.has(activeId)}
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
        </section>
          {(!workspace.workbenchOpen || workbenchRestore?.tabs.find(tab => tab.id === workbenchRestore.active)?.kind !== "browser") &&
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
      <SearchDialog open={searchOpen} conversations={conversations} onClose={() => setSearchOpen(false)}
        onSelect={item => {
          setConversations(current => current.some(conversation => conversation.id === item.id) ? current : [...current, item]);
          void selectConversation(item.id, undefined, false, item.match_ordinal);
          void refreshConversations().catch(reason => setError(String(reason)));
        }} onCreate={() => void createConversation()}
        onFile={path => { workbenchRef.current?.openFile(path); setWorkbenchOpen(true); }} />
      {managementSection && (
        <ManagementCenter
          initial={managementSection}
          returnFocus={managementReturnFocus.current}
          restoreFocus={false}
          onClose={() => { setManagementSection(null); requestComposerFocus(); }}
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
