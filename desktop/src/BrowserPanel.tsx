import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  activeTab,
  nextRequestId,
  pageTitle,
  type BrowserProfile,
  type BrowserSnapshot,
  type BrowserTab,
} from "./browserState";
import { coreApi } from "./coreApi";
import { IconButton } from "./ui";

type HistoryEntry = {
  id: string;
  url: string;
  title: string;
  visitedAt: string;
  visits: number;
};
type Bookmark = { id: string; url: string; title: string; createdAt: string };
type Download = {
  id: string;
  phase: string;
  name?: string;
  url?: string;
  success?: boolean;
  createdAt: string;
};
type PermissionName =
  "camera" | "microphone" | "geolocation" | "notifications" | "clipboard-read";
type BrowserLibrary = {
  history: HistoryEntry[];
  bookmarks: Bookmark[];
  downloads: Download[];
};
type BrowserActionResult = { result: Record<string, unknown> };
type ImportSource = {
  id: string;
  browser_id: string;
  browser_name: string;
  profile_name: string;
};

const initialBrowser: BrowserSnapshot = {
  tabs: [],
  activeTabId: null,
  transport: "webview2-in-process-cdp",
  remoteDebuggingPort: null,
};
const emptyLibrary: BrowserLibrary = {
  history: [],
  bookmarks: [],
  downloads: [],
};
const libraryKey = "smarti-browser-library-v1";
const sessionKey = "smarti-browser-session-v1";
const permissionKey = "smarti-browser-permissions-v1";
const readJson = <T,>(key: string, fallback: T): T => {
  try {
    return JSON.parse(localStorage.getItem(key) || "") as T;
  } catch {
    return fallback;
  }
};
const saveFile = (base64: string, mime: string, name: string) => {
  const bytes = Uint8Array.from(atob(base64), (value) => value.charCodeAt(0));
  const href = URL.createObjectURL(new Blob([bytes], { type: mime }));
  const link = document.createElement("a");
  link.href = href;
  link.download = name;
  link.click();
  URL.revokeObjectURL(href);
};
export const browserProductCapabilities = {
  sameVisibleTarget: true,
  guestInPersistentLibrary: false,
  passwordImport: false,
  remoteDebuggingPort: null,
  maxRestoredTabs: 12,
} as const;

export function BrowserPanel({ visible }: { visible: boolean }) {
  const [browser, setBrowser] = useState<BrowserSnapshot>(initialBrowser);
  const [hydrated, setHydrated] = useState(false);
  const [address, setAddress] = useState("");
  const [notice, setNotice] = useState("");
  const [findText, setFindText] = useState("");
  const [libraryQuery, setLibraryQuery] = useState("");
  const [showFind, setShowFind] = useState(false);
  const [panel, setPanel] = useState<
    "" | "library" | "downloads" | "privacy" | "import"
  >("");
  const [library, setLibrary] = useState<BrowserLibrary>(() =>
    readJson(libraryKey, emptyLibrary),
  );
  const [zoom, setZoom] = useState(100);
  const [deviceMode, setDeviceMode] = useState(false);
  const [mobileUserAgent, setMobileUserAgent] = useState(false);
  const [developerEnabled, setDeveloperEnabled] = useState(false);
  const [sources, setSources] = useState<ImportSource[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [importing, setImporting] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const addressRef = useRef<HTMLInputElement>(null);
  const initialTabRequested = useRef(false);
  const legacyMigrationAttempted = useRef(false);
  const browserRef = useRef(browser);
  browserRef.current = browser;
  useEffect(() => {
    void coreApi<{ values?: Record<string, unknown> }>(
      "GET",
      "/v2/settings",
    ).then((settings) =>
      setDeveloperEnabled(Boolean(settings.values?.enable_developer_trace)),
    );
  }, []);
  const persistLibrary = (update: (value: BrowserLibrary) => BrowserLibrary) =>
    setLibrary((current) => {
      const next = update(current);
      localStorage.setItem(libraryKey, JSON.stringify(next));
      return next;
    });
  const refresh = useCallback(async () => {
    setBrowser(await invoke<BrowserSnapshot>("browser_status"));
    setHydrated(true);
  }, []);
  useEffect(() => {
    if (!visible) return;
    const timer = window.setInterval(() => {
      const tab = activeTab(browserRef.current);
      if (tab && !tab.loading) {
        void invoke<BrowserSnapshot>("browser_metadata", { tabId: tab.tabId })
          .then(setBrowser)
          .catch(() => undefined);
      }
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [visible]);
  const runCdp = useCallback(
    async (
      tab: BrowserTab,
      method: string,
      params: Record<string, unknown> = {},
    ) =>
      invoke<BrowserActionResult>("browser_action", {
        action: {
          requestId: nextRequestId(),
          tabId: tab.tabId,
          method,
          params,
        },
      }),
    [],
  );
  useEffect(() => {
    if (!visible || !hydrated || legacyMigrationAttempted.current) return;
    const tab = activeTab(browserRef.current);
    if (!tab || tab.profile !== "persistent") return;
    legacyMigrationAttempted.current = true;
    void coreApi<{
      status?: string;
      history?: Array<{ url: string; title?: string; last_visit_at?: string; visit_count?: number }>;
      bookmarks?: Array<{ url: string; title?: string }>;
      cookies?: Array<Record<string, unknown>>;
      counts?: Record<string, number>;
    }>("GET", "/v2/browser/legacy-migration").then(async (data) => {
      if (data.status !== "prepared") return;
      persistLibrary((current) => ({
        ...current,
        history: [
          ...(data.history || []).map((item) => ({
            id: crypto.randomUUID(), url: item.url, title: item.title || item.url,
            visitedAt: item.last_visit_at || new Date().toISOString(), visits: item.visit_count || 1,
          })),
          ...current.history,
        ].slice(0, 5000),
        bookmarks: [
          ...(data.bookmarks || []).map((item) => ({
            id: crypto.randomUUID(), url: item.url, title: item.title || item.url,
            createdAt: new Date().toISOString(),
          })),
          ...current.bookmarks,
        ],
      }));
      if (data.cookies?.length) await runCdp(tab, "Network.setCookies", { cookies: data.cookies });
      await coreApi("POST", "/v2/browser/legacy-migration", { action: "applied" }, true);
      setNotice(`נתוני Smarti Browser הישן שוחזרו מגיבוי: ${data.history?.length || 0} רשומות היסטוריה, ${data.bookmarks?.length || 0} סימניות.`);
    }).catch((reason) => {
      legacyMigrationAttempted.current = false;
      setNotice(`מיגרציית הדפדפן הישן לא הושלמה: ${String(reason)}`);
    });
  }, [visible, hydrated, browser.tabs.length, runCdp]);
  const recordNavigation = useCallback((snapshot: BrowserSnapshot) => {
    const tab = activeTab(snapshot);
    if (
      !tab ||
      tab.profile === "guest" ||
      tab.loading ||
      !/^https?:/i.test(tab.url)
    )
      return;
    persistLibrary((current) => {
      const existing = current.history.find((item) => item.url === tab.url);
      const next: HistoryEntry = {
        id: existing?.id || crypto.randomUUID(),
        url: tab.url,
        title: pageTitle(tab),
        visitedAt: new Date().toISOString(),
        visits: (existing?.visits || 0) + 1,
      };
      return {
        ...current,
        history: [
          next,
          ...current.history.filter((item) => item.url !== tab.url),
        ].slice(0, 5000),
      };
    });
  }, []);
  useEffect(() => {
    let alive = true;
    const stateListener = listen<BrowserSnapshot>(
      "browser://state",
      ({ payload }) => {
        if (!alive) return;
        setBrowser(payload);
        setHydrated(true);
        recordNavigation(payload);
        const persistent = payload.tabs
          .filter((tab) => tab.profile === "persistent")
          .map((tab) => ({ url: tab.url, pinned: tab.pinned }));
        if (persistent.length)
          localStorage.setItem(sessionKey, JSON.stringify(persistent));
      },
    );
    const downloadListener = listen<Record<string, unknown>>(
      "browser://download",
      ({ payload }) => {
        if (payload.profile === "guest") return;
        const phase = String(payload.phase || "progress");
        persistLibrary((current) => ({
          ...current,
          downloads: [
            {
              id: crypto.randomUUID(),
              phase,
              name: String(payload.name || ""),
              url: String(payload.url || ""),
              success:
                typeof payload.success === "boolean"
                  ? payload.success
                  : undefined,
              createdAt: new Date().toISOString(),
            },
            ...current.downloads,
          ].slice(0, 200),
        }));
      },
    );
    void refresh();
    return () => {
      alive = false;
      void invoke("browser_set_visible", { visible: false }).catch(
        () => undefined,
      );
      void stateListener.then((dispose) => dispose());
      void downloadListener.then((dispose) => dispose());
    };
  }, [refresh, recordNavigation]);
  useEffect(() => {
    void invoke("browser_set_visible", { visible }).catch(() => undefined);
  }, [visible]);
  useEffect(() => {
    if (
      !visible ||
      !hydrated ||
      initialTabRequested.current ||
      browser.tabs.length > 0
    )
      return;
    initialTabRequested.current = true;
    const stored = readJson<Array<{ url: string; pinned?: boolean }>>(
      sessionKey,
      [],
    );
    const restore = async () => {
      try {
        if (stored.length) {
          for (const item of stored.slice(0, 12)) {
            const state = await invoke<BrowserSnapshot>("browser_open", {
              profile: "persistent",
              url: item.url,
            });
            const tab = activeTab(state);
            if (tab && item.pinned)
              await invoke("browser_pin", { tabId: tab.tabId, pinned: true });
          }
        } else
          await invoke("browser_open", {
            profile: "persistent",
            url: "https://www.google.com/?hl=he",
          });
        await refresh();
      } catch (error) {
        initialTabRequested.current = false;
        setNotice(String(error));
      }
    };
    void restore();
  }, [browser.tabs.length, hydrated, visible, refresh]);
  useEffect(() => {
    const element = viewportRef.current;
    if (!element || !visible) return;
    let frame = 0;
    let inFlight = false;
    let dirty = false;
    let disposed = false;
    let lastBounds = "";
    const flush = async () => {
      if (disposed) return;
      if (inFlight) {
        dirty = true;
        return;
      }
      const rect = element.getBoundingClientRect();
      if (rect.width < 160 || rect.height < 120) return;
      const bounds = {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      };
      const key = `${bounds.x}:${bounds.y}:${bounds.width}:${bounds.height}`;
      if (key === lastBounds) return;
      inFlight = true;
      lastBounds = key;
      try {
        await invoke("browser_set_bounds", { bounds });
      } catch {
        lastBounds = "";
      } finally {
        inFlight = false;
        if (dirty && !disposed) {
          dirty = false;
          void flush();
        }
      }
    };
    const sync = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => void flush());
    };
    const observer = new ResizeObserver(sync);
    observer.observe(element);
    window.addEventListener("resize", sync);
    sync();
    const settled = window.setTimeout(sync, 380);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      clearTimeout(settled);
      observer.disconnect();
      window.removeEventListener("resize", sync);
    };
  }, [visible]);
  const current = useMemo(() => activeTab(browser), [browser]);
  useEffect(() => {
    if (current) setAddress(current.url);
  }, [current?.tabId, current?.url]);
  const newTab = useCallback(
    async (
      profile: BrowserProfile = "persistent",
      url = "https://www.google.com/?hl=he",
    ) =>
      setBrowser(
        await invoke<BrowserSnapshot>("browser_open", { profile, url }),
      ),
    [],
  );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (current)
      setBrowser(
        await invoke<BrowserSnapshot>("browser_navigate", {
          tabId: current.tabId,
          url: address,
        }),
      );
  };
  const historyMove = async (tab: BrowserTab, direction: "back" | "forward") =>
    runCdp(tab, "Runtime.evaluate", {
      expression: `history.${direction}()`,
      returnByValue: true,
    });
  const closeTab = async (tab: BrowserTab) => {
    if (tab.pinned) {
      setNotice("בטל הצמדה לפני סגירת הכרטיסייה.");
      return;
    }
    setBrowser(
      await invoke<BrowserSnapshot>("browser_close", { tabId: tab.tabId }),
    );
  };
  const bookmark = () => {
    if (!current || current.profile === "guest") return;
    persistLibrary((value) => ({
      ...value,
      bookmarks: value.bookmarks.some((item) => item.url === current.url)
        ? value.bookmarks.filter((item) => item.url !== current.url)
        : [
            {
              id: crypto.randomUUID(),
              url: current.url,
              title: pageTitle(current),
              createdAt: new Date().toISOString(),
            },
            ...value.bookmarks,
          ],
    }));
  };
  const find = async () => {
    if (!current || !findText) return;
    await runCdp(current, "Runtime.evaluate", {
      expression: `window.find(${JSON.stringify(findText)},false,false,true,false,false,false)`,
      returnByValue: true,
    });
    setNotice(`חיפוש: ${findText}`);
  };
  const setPageZoom = async (next: number) => {
    if (!current) return;
    const safe = Math.max(25, Math.min(500, next));
    setZoom(safe);
    await runCdp(current, "Runtime.evaluate", {
      expression: `document.documentElement.style.zoom=${JSON.stringify(`${safe}%`)}`,
      returnByValue: true,
    });
  };
  const capture = async (pdf = false) => {
    if (!current) return;
    const result = await runCdp(
      current,
      pdf ? "Page.printToPDF" : "Page.captureScreenshot",
      pdf
        ? { printBackground: true }
        : { format: "png", captureBeyondViewport: true },
    );
    const data = String(result.result.data || "");
    if (!data) throw new Error("capture returned no data");
    saveFile(
      data,
      pdf ? "application/pdf" : "image/png",
      `smarti-${Date.now()}.${pdf ? "pdf" : "png"}`,
    );
  };
  const toggleDeviceMode = async () => {
    if (!current) return;
    if (deviceMode)
      await runCdp(current, "Emulation.clearDeviceMetricsOverride");
    else
      await runCdp(current, "Emulation.setDeviceMetricsOverride", {
        width: 390,
        height: 844,
        deviceScaleFactor: 2,
        mobile: true,
      });
    setDeviceMode(!deviceMode);
  };
  const saveSource = async () => {
    if (!current) return;
    const result = await runCdp(current, "Runtime.evaluate", {
      expression: "document.documentElement.outerHTML",
      returnByValue: true,
    });
    const html = String(
      (result.result as { result?: { value?: unknown } }).result?.value || "",
    );
    const href = URL.createObjectURL(
      new Blob([html], { type: "text/html;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = href;
    link.download = `source-${Date.now()}.html`;
    link.click();
    URL.revokeObjectURL(href);
  };
  const toggleUserAgent = async () => {
    if (!current) return;
    const mobile = !mobileUserAgent;
    await runCdp(current, "Network.setUserAgentOverride", {
      userAgent: mobile
        ? "Mozilla/5.0 (Linux; Android 14; SmartiAI Mobile) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"
        : navigator.userAgent,
    });
    setMobileUserAgent(mobile);
    await invoke("browser_reload", { tabId: current.tabId });
  };
  const openLibraryUrl = async (url: string) => {
    setPanel("");
    if (current)
      setBrowser(
        await invoke("browser_navigate", { tabId: current.tabId, url }),
      );
    else await newTab("persistent", url);
  };
  const permission = async (
    name: PermissionName,
    setting: "granted" | "denied" | "prompt",
  ) => {
    if (!current) return;
    const origin = new URL(current.url).origin;
    await runCdp(current, "Browser.setPermission", {
      permission: { name },
      setting,
      origin,
    });
    const all = readJson<Record<string, string>>(permissionKey, {});
    all[`${origin}:${name}`] = setting;
    localStorage.setItem(permissionKey, JSON.stringify(all));
    setNotice(`${name}: ${setting}`);
  };
  const loadSources = async () => {
    const data = await coreApi<{ items: ImportSource[] }>(
      "GET",
      "/v2/browser/import/sources",
    );
    setSources(data.items);
    setSourceId(data.items[0]?.id || "");
    setPanel("import");
  };
  const importProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setImporting(true);
    try {
      const data = await coreApi<{
        history: Array<{
          url: string;
          title: string;
          last_visit_at?: string;
          visit_count?: number;
        }>;
        bookmarks: Array<{ url: string; title: string }>;
        cookies: Array<Record<string, unknown>>;
        cookie_stats: Record<string, unknown>;
      }>(
        "POST",
        "/v2/browser/import",
        {
          source_id: sourceId,
          history: form.has("history"),
          bookmarks: form.has("bookmarks"),
          cookies: form.has("cookies"),
        },
        true,
      );
      persistLibrary((value) => ({
        ...value,
        history: [
          ...data.history.map((item) => ({
            id: crypto.randomUUID(),
            url: item.url,
            title: item.title,
            visitedAt: item.last_visit_at || new Date().toISOString(),
            visits: item.visit_count || 1,
          })),
          ...value.history,
        ].slice(0, 5000),
        bookmarks: [
          ...data.bookmarks.map((item) => ({
            id: crypto.randomUUID(),
            url: item.url,
            title: item.title,
            createdAt: new Date().toISOString(),
          })),
          ...value.bookmarks,
        ],
      }));
      if (data.cookies.length && current?.profile === "persistent")
        await runCdp(current, "Network.setCookies", { cookies: data.cookies });
      setNotice(
        `הייבוא הושלם: ${data.history.length} היסטוריה, ${data.bookmarks.length} סימניות, ${data.cookies.length} cookies. סיסמאות אינן מיובאות.`,
      );
      setPanel("");
    } finally {
      setImporting(false);
    }
  };
  useEffect(() => {
    if (!visible) return;
    const keyboard = (event: KeyboardEvent) => {
      const tab = activeTab(browserRef.current);
      if (event.ctrlKey && event.key.toLowerCase() === "l") {
        event.preventDefault();
        addressRef.current?.focus();
        addressRef.current?.select();
      } else if (event.ctrlKey && event.key.toLowerCase() === "t") {
        event.preventDefault();
        void newTab();
      } else if (
        event.ctrlKey &&
        event.shiftKey &&
        event.key.toLowerCase() === "t"
      ) {
        event.preventDefault();
        void invoke<BrowserSnapshot>("browser_restore_closed")
          .then(setBrowser)
          .catch((error) => setNotice(String(error)));
      } else if (event.ctrlKey && event.key.toLowerCase() === "w" && tab) {
        event.preventDefault();
        void closeTab(tab);
      } else if (event.ctrlKey && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setShowFind(true);
      } else if (event.ctrlKey && event.key.toLowerCase() === "d") {
        event.preventDefault();
        bookmark();
      } else if (event.ctrlKey && event.key.toLowerCase() === "r" && tab) {
        event.preventDefault();
        void invoke("browser_reload", { tabId: tab.tabId });
      } else if (event.altKey && event.key === "ArrowLeft" && tab)
        void historyMove(tab, "back");
      else if (event.altKey && event.key === "ArrowRight" && tab)
        void historyMove(tab, "forward");
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [visible, newTab, current, library]);
  return (
    <div className="embedded-browser">
      <div className="browser-tabs" role="tablist" aria-label="כרטיסיות דפדפן">
        {browser.tabs.map((tab, index) => (
          <button
            key={tab.tabId}
            draggable
            role="tab"
            aria-selected={tab.active}
            onDragStart={(event) =>
              event.dataTransfer.setData("text/plain", tab.tabId)
            }
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              void invoke<BrowserSnapshot>("browser_reorder", {
                tabId: event.dataTransfer.getData("text/plain"),
                index,
              }).then(setBrowser);
            }}
            onClick={() =>
              void invoke<BrowserSnapshot>("browser_activate", {
                tabId: tab.tabId,
              }).then(setBrowser)
            }
          >
            <span className={tab.profile === "guest" ? "guest-dot" : "tab-dot"}>
              {tab.crashed
                ? "!"
                : tab.audioPlaying
                  ? "♪"
                  : tab.loading
                    ? "◌"
                    : tab.pinned
                      ? "◆"
                      : "●"}
            </span>
            <span>{pageTitle(tab)}</span>
            <i
              onClick={(event) => {
                event.stopPropagation();
                void closeTab(tab);
              }}
            >
              ×
            </i>
          </button>
        ))}
        <IconButton label="כרטיסייה חדשה" onClick={() => void newTab()}>
          ＋
        </IconButton>
      </div>
      <div className="browser-toolbar" dir="ltr">
        <IconButton
          label="חזרה"
          onClick={() => current && void historyMove(current, "back")}
        >
          ←
        </IconButton>
        <IconButton
          label="קדימה"
          onClick={() => current && void historyMove(current, "forward")}
        >
          →
        </IconButton>
        <IconButton
          label={current?.loading ? "עצירה" : "רענון"}
          onClick={() =>
            current &&
            void invoke(current.loading ? "browser_stop" : "browser_reload", {
              tabId: current.tabId,
            })
          }
        >
          {current?.loading ? "×" : "↻"}
        </IconButton>
        <IconButton
          label="בית"
          onClick={() =>
            current &&
            void invoke<BrowserSnapshot>("browser_navigate", {
              tabId: current.tabId,
              url: "https://www.google.com/?hl=he",
            }).then(setBrowser)
          }
        >
          ⌂
        </IconButton>
        <form onSubmit={submit}>
          <span
            title={
              current?.url.startsWith("https:")
                ? "חיבור HTTPS"
                : "חיבור לא מאובטח"
            }
          >
            {current?.url.startsWith("https:") ? "▣" : "ⓘ"}
          </span>
          <input
            ref={addressRef}
            aria-label="כתובת או חיפוש"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            spellCheck={false}
          />
        </form>
        <IconButton label="סימנייה" onClick={bookmark}>
          ☆
        </IconButton>
        <details className="browser-menu">
          <summary aria-label="תפריט דפדפן">⋮</summary>
          <div dir="rtl">
            <button onClick={() => void newTab("guest")}>כרטיסיית Guest</button>
            <button
              onClick={() =>
                current &&
                void invoke<BrowserSnapshot>("browser_duplicate", {
                  tabId: current.tabId,
                }).then(setBrowser)
              }
            >
              שכפול כרטיסייה
            </button>
            <button
              onClick={() =>
                current &&
                void invoke<BrowserSnapshot>("browser_pin", {
                  tabId: current.tabId,
                  pinned: !current.pinned,
                }).then(setBrowser)
              }
            >
              {current?.pinned ? "ביטול הצמדה" : "הצמדה"}
            </button>
            <button onClick={() => setShowFind(true)}>חיפוש בדף</button>
            <button onClick={() => void setPageZoom(zoom + 10)}>
              הגדלה ({zoom}%)
            </button>
            <button onClick={() => void setPageZoom(zoom - 10)}>הקטנה</button>
            <button onClick={() => void capture(false)}>צילום מסך</button>
            <button onClick={() => void capture(true)}>הדפסה / PDF</button>
            <button onClick={() => void saveSource()}>שמירת מקור הדף</button>
            <button onClick={() => void toggleDeviceMode()}>
              {deviceMode ? "יציאה ממצב מכשיר" : "מצב מכשיר"}
            </button>
            <button onClick={() => void toggleUserAgent()}>
              {mobileUserAgent ? "User Agent רגיל" : "User Agent נייד"}
            </button>
            {developerEnabled && (
              <button
                onClick={() =>
                  current &&
                  void invoke("browser_open_devtools", {
                    tabId: current.tabId,
                    developerEnabled: true,
                  })
                }
              >
                Developer Tools
              </button>
            )}
            <button
              onClick={() =>
                current && void navigator.clipboard.writeText(current.url)
              }
            >
              העתקת כתובת
            </button>
            <button onClick={() => current && void openUrl(current.url)}>
              פתיחה חיצונית
            </button>
            <button onClick={() => setPanel("library")}>
              היסטוריה וסימניות
            </button>
            <button onClick={() => setPanel("downloads")}>הורדות</button>
            <button onClick={() => setPanel("privacy")}>פרטיות והרשאות</button>
            <button onClick={() => void loadSources()}>ייבוא פרופיל</button>
          </div>
        </details>
      </div>
      {showFind && (
        <form
          className="browser-find"
          onSubmit={(event) => {
            event.preventDefault();
            void find();
          }}
        >
          <input
            autoFocus
            value={findText}
            onChange={(event) => setFindText(event.target.value)}
            placeholder="חיפוש בדף"
          />
          <button>הבא</button>
          <button type="button" onClick={() => setShowFind(false)}>
            ×
          </button>
        </form>
      )}
      <div
        className="browser-viewport"
        ref={viewportRef}
        aria-label="תוכן הדפדפן"
      >
        {browser.tabs.length === 0 && <span>פותח את Smarti Browser…</span>}
      </div>
      <div className="browser-status">
        {notice ||
          `${current?.profile === "guest" ? "Guest זמני" : "פרופיל Smarti מתמשך"} · אותו יעד גלוי ומאושר לאוטומציה`}
      </div>
      {panel && (
        <aside className="browser-side-panel" dir="rtl">
          <header>
            <h3>
              {panel === "library"
                ? "היסטוריה וסימניות"
                : panel === "downloads"
                  ? "הורדות"
                  : panel === "privacy"
                    ? "פרטיות והרשאות"
                    : "ייבוא פרופיל"}
            </h3>
            <button onClick={() => setPanel("")}>×</button>
          </header>
          {panel === "library" && (
            <>
              <input
                value={libraryQuery}
                onChange={(event) => setLibraryQuery(event.target.value)}
                placeholder="חיפוש בהיסטוריה ובסימניות"
                aria-label="חיפוש בספריית הדפדפן"
              />
              <h4>סימניות</h4>
              {library.bookmarks
                .filter((item) =>
                  `${item.title} ${item.url}`
                    .toLocaleLowerCase()
                    .includes(libraryQuery.toLocaleLowerCase()),
                )
                .slice(0, 100)
                .map((item) => (
                  <button
                    key={item.id}
                    onClick={() => void openLibraryUrl(item.url)}
                  >
                    {item.title || item.url}
                  </button>
                ))}
              <h4>היסטוריה</h4>
              {library.history
                .filter((item) =>
                  `${item.title} ${item.url}`
                    .toLocaleLowerCase()
                    .includes(libraryQuery.toLocaleLowerCase()),
                )
                .slice(0, 200)
                .map((item) => (
                  <button
                    key={item.id}
                    onClick={() => void openLibraryUrl(item.url)}
                  >
                    <span>{item.title}</span>
                    <small>
                      {new Date(item.visitedAt).toLocaleString("he-IL")}
                    </small>
                  </button>
                ))}
            </>
          )}
          {panel === "downloads" && (
            <>
              {library.downloads.map((item) => (
                <p key={item.id}>
                  {item.name || item.url || "הורדה"} · {item.phase} ·{" "}
                  {new Date(item.createdAt).toLocaleTimeString("he-IL")}{" "}
                  {item.success === false ? "נכשלה" : ""}
                </p>
              ))}
              {!library.downloads.length && <p>אין הורדות עדיין.</p>}
            </>
          )}
          {panel === "privacy" && (
            <>
              <p>
                Guest נמחק בסגירה ואינו נכנס להיסטוריה או לסימניות של Smarti.
                Smarti אינו קורא או מציג סיסמאות.
              </p>
              <button
                onClick={() =>
                  void invoke("browser_clear_profile", {
                    profile: current?.profile || "persistent",
                  }).then(refresh)
                }
              >
                ניקוי נתוני הפרופיל הנוכחי
              </button>
              {(
                [
                  "camera",
                  "microphone",
                  "geolocation",
                  "notifications",
                  "clipboard-read",
                ] as PermissionName[]
              ).map((name) => (
                <div className="permission-row" key={name}>
                  <span>{name}</span>
                  <button onClick={() => void permission(name, "granted")}>
                    אפשר
                  </button>
                  <button onClick={() => void permission(name, "denied")}>
                    חסום
                  </button>
                  <button onClick={() => void permission(name, "prompt")}>
                    שאל
                  </button>
                </div>
              ))}
            </>
          )}
          {panel === "import" && (
            <form onSubmit={importProfile}>
              <select
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}
              >
                {sources.map((source) => (
                  <option key={source.id} value={source.id}>
                    {source.browser_name} — {source.profile_name}
                  </option>
                ))}
              </select>
              <label>
                <input name="history" type="checkbox" defaultChecked /> היסטוריה
              </label>
              <label>
                <input name="bookmarks" type="checkbox" defaultChecked />{" "}
                סימניות
              </label>
              <label>
                <input name="cookies" type="checkbox" /> Cookies תואמים
              </label>
              <p>
                המקור מועתק לפני קריאה ולעולם אינו משתנה. הצפנה חסומה תדווח
                כדילוג; אין ייבוא סיסמאות.
              </p>
              <button disabled={!sourceId || importing}>
                {importing ? "מייבא…" : "ייבוא"}
              </button>
            </form>
          )}
        </aside>
      )}
    </div>
  );
}
