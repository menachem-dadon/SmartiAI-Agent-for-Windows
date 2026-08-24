import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { coreApi } from "./coreApi";
import type { ResolvedTheme } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import { ConfirmDialog, InputDialog, PageHero } from "./SettingsManagement";

type Json = Record<string, unknown>;
type SafeSettings = { values: Json };
const asRows = (value: unknown): Json[] =>
  Array.isArray(value)
    ? value.filter((item): item is Json =>
        Boolean(item && typeof item === "object"),
      )
    : [];
const relaunch = () => invoke("restart_after_update");

export function WorkspaceView({
  onOpenWorkbench,
}: {
  onOpenWorkbench?: (tab: "browser" | "files") => void;
}) {
  const [root, setRoot] = useState<Json>({});
  const [browser, setBrowser] = useState<Json>({});
  const [settings, setSettings] = useState<Json>({});
  const [status, setStatus] = useState("");
  const load = useCallback(async () => {
    const [rootInfo, safe] = await Promise.all([
      coreApi<Json>("GET", "/v2/workbench/root"),
      coreApi<SafeSettings>("GET", "/v2/settings"),
    ]);
    setRoot(rootInfo);
    setSettings(safe.values);
    try {
      setBrowser(await invoke<Json>("browser_status"));
    } catch {
      setBrowser({});
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const prefs =
    settings.ui_preferences && typeof settings.ui_preferences === "object"
      ? (settings.ui_preferences as Json)
      : {};
  const savePrefs = async (patch: Json) => {
    const next = { ...prefs, ...patch };
    await coreApi(
      "PATCH",
      "/v2/settings",
      { values: { ui_preferences: next } },
      true,
    );
    setSettings((current) => ({ ...current, ui_preferences: next }));
    setStatus("העדפות סביבת העבודה נשמרו.");
  };
  const browserPath = String(
    browser.profile_dir || (root.root as Json)?.path || root.path || "",
  );
  return (
    <div className="management-page">
      <PageHero
        title="סביבת עבודה ודפדפן"
        description="העדפות החלון והרכב סביבת העבודה נשמרות ב־Core; הדפדפן הוא WebView2 בבעלות Smarti."
        actions={<button onClick={() => void load()}>רענן</button>}
      />
      <section className="special-settings-card">
        <h3>פתיחה וסרגל צד</h3>
        <label className="management-field toggle-field">
          <span>
            <b>פתיחה בחלון מוגדל</b>
            <small>מתאים את חלון Smarti לשטח העבודה של Windows.</small>
          </span>
          <input
            type="checkbox"
            checked={prefs.workspace_start_maximized !== false}
            onChange={(event) =>
              void savePrefs({
                workspace_start_maximized: event.target.checked,
              })
            }
          />
        </label>
        <label className="management-field toggle-field">
          <span>
            <b>סרגל השיחות פתוח בכניסה</b>
            <small>מציג את רשימת השיחות המלאה במקום מצב אייקונים.</small>
          </span>
          <input
            type="checkbox"
            checked={!Boolean(prefs.workspace_sidebar_collapsed)}
            onChange={(event) =>
              void savePrefs({
                workspace_sidebar_collapsed: !event.target.checked,
              })
            }
          />
        </label>
      </section>
      <section className="special-settings-card">
        <header>
          <div>
            <h3>סביבת עבודה</h3>
            <p>
              שורש נוכחי:{" "}
              <span dir="ltr">
                {String((root.root as Json)?.path || root.path || "")}
              </span>
            </p>
          </div>
          <div className="inline-actions">
            <button onClick={() => onOpenWorkbench?.("files")}>
              פתח קבצים
            </button>
            <button onClick={() => onOpenWorkbench?.("browser")}>
              פתח דפדפן
            </button>
          </div>
        </header>
      </section>
      <section className="special-settings-card">
        <h3>Smarti Browser</h3>
        <p>
          {browser.available === false
            ? "WebView2 אינו זמין כרגע."
            : `יעדי דפדפן פעילים: ${Number(browser.target_count || browser.tabs || 0)}`}
        </p>
        <div className="inline-actions">
          <button onClick={() => onOpenWorkbench?.("browser")}>
            פתח את Smarti Browser
          </button>
          <button
            onClick={() => {
              onOpenWorkbench?.("browser");
              setStatus(
                "Smarti Browser נפתח. הייבוא זמין בתפריט הדפדפן, עם בחירת מקור מפורשת.",
              );
            }}
          >
            ייבוא מדפדפן קיים
          </button>
          <button
            disabled={!browserPath}
            onClick={() =>
              void invoke("open_chat_link", {
                target: browserPath,
                local: true,
              })
            }
          >
            פתח תיקיית נתונים
          </button>
        </div>
      </section>
      <p role="status" className="settings-status">
        {status}
      </p>
    </div>
  );
}

export function TasksView() {
  const [items, setItems] = useState<Json[]>([]);
  const [prompt, setPrompt] = useState("");
  const [delay, setDelay] = useState(5);
  const [repeat, setRepeat] = useState("once");
  const [weeklyDays, setWeeklyDays] = useState("0");
  const [conversationMode, setConversationMode] = useState("current");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Json | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Json | null>(null);
  const load = useCallback(
    async () =>
      setItems(
        (await coreApi<{ items: Json[] }>("GET", "/v2/management/tasks")).items,
      ),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const action = async (payload: Json) => {
    try {
      const result = await coreApi<{ items: Json[] }>(
        "POST",
        "/v2/management/tasks",
        payload,
        true,
      );
      setItems(result.items);
      setError("");
      return true;
    } catch (reason) {
      setError(String(reason));
      return false;
    }
  };
  const days = weeklyDays
    .split(",")
    .map((value) => Number.parseInt(value.trim(), 10))
    .filter((value) => Number.isInteger(value) && value >= 0 && value <= 6);
  return (
    <div className="management-page">
      <PageHero
        title="מרכז משימות"
        description="משימות חד־פעמיות ומחזוריות נשארות בבעלות Python Core ומנותבות לשיחה שנבחרה."
        actions={<button onClick={() => void load()}>רענן</button>}
      />
      <form
        className="task-create"
        onSubmit={(event) => {
          event.preventDefault();
          void action({
            action: "create",
            prompt,
            delay_minutes: delay,
            repeat,
            interval_minutes:
              repeat === "interval" ? Math.max(1, delay) : undefined,
            days_of_week: repeat === "weekly" ? days : undefined,
            conversation_mode: conversationMode,
          }).then((saved) => {
            if (saved) setPrompt("");
          });
        }}
      >
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="מה Smarti יבצע?"
          required
        />
        <label>
          בעוד{" "}
          <input
            type="number"
            min="0"
            value={delay}
            onChange={(event) => setDelay(Number(event.target.value))}
          />{" "}
          דקות
        </label>
        <select
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        >
          <option value="once">חד־פעמית</option>
          <option value="interval">מחזורית</option>
          <option value="weekly">שבועית</option>
        </select>
        {repeat === "weekly" && (
          <label>
            ימי שבוע
            <input
              dir="ltr"
              value={weeklyDays}
              onChange={(event) => setWeeklyDays(event.target.value)}
            />
          </label>
        )}
        <select
          value={conversationMode}
          onChange={(event) => setConversationMode(event.target.value)}
        >
          <option value="current">שיחת המקור</option>
          <option value="new">שיחה חדשה</option>
          <option value="dedicated">שיחה ייעודית</option>
        </select>
        <button>יצירת משימה</button>
      </form>
      {error && <p className="management-notice">{error}</p>}
      <div className="management-cards">
        {items.map((item) => (
          <article key={String(item.id)}>
            <header>
              <b>{String(item.prompt || item.message || "משימה")}</b>
              <span>{String(item.status)}</span>
            </header>
            <p>
              תזמון: {String(item.run_at || "")} · חזרה:{" "}
              {String(item.repeat || "once")} · ניתוב:{" "}
              {String(item.conversation_mode || "current")}
            </p>
            <small>
              תוצאה אחרונה: {String(item.last_result || "טרם הופעלה")}
            </small>
            <footer>
              <button onClick={() => setEditing(item)}>עריכה</button>
              {String(item.status) === "cancelled" && (
                <button
                  onClick={() => void action({ action: "resume", id: item.id })}
                >
                  המשך
                </button>
              )}
              <button
                disabled={["running", "cancelling"].includes(
                  String(item.status),
                )}
                onClick={() => void action({ action: "retry", id: item.id })}
              >
                הרץ שוב
              </button>
              <button
                disabled={
                  !["scheduled", "running"].includes(String(item.status))
                }
                onClick={() => void action({ action: "cancel", id: item.id })}
              >
                ביטול
              </button>
              <button
                disabled={["running", "cancelling"].includes(
                  String(item.status),
                )}
                onClick={() => setConfirmDelete(item)}
              >
                מחיקה
              </button>
            </footer>
          </article>
        ))}
        {!items.length && <p className="management-empty">אין משימות רקע.</p>}
      </div>
      {editing && (
        <InputDialog
          title="עריכת משימה"
          label="תוכן המשימה"
          initial={String(editing.prompt || editing.message || "")}
          onCancel={() => setEditing(null)}
          onConfirm={(value) => {
            void action({ action: "edit", id: editing.id, prompt: value });
            setEditing(null);
          }}
        />
      )}
      {confirmDelete && (
        <ConfirmDialog
          title="מחיקת משימה"
          description="למחוק את המשימה ואת התזמון שלה?"
          danger
          onCancel={() => setConfirmDelete(null)}
          onConfirm={() => {
            void action({ action: "delete", id: confirmDelete.id });
            setConfirmDelete(null);
          }}
        />
      )}
    </div>
  );
}

export function ToolsView({ theme }: { theme: ResolvedTheme }) {
  const [data, setData] = useState<{ builtins: Json[]; extensions: Json[] }>({
    builtins: [],
    extensions: [],
  });
  const [installChoice, setInstallChoice] = useState<"skill" | "mcp" | null>(
    null,
  );
  const [packageDialog, setPackageDialog] = useState(false);
  const [deleting, setDeleting] = useState<Json | null>(null);
  const [message, setMessage] = useState("");
  const icons = legacyAssets(theme);
  const load = useCallback(
    async () =>
      setData(
        await coreApi<{ builtins: Json[]; extensions: Json[] }>(
          "GET",
          "/v2/management/tools",
        ),
      ),
    [],
  );
  useEffect(() => {
    void load();
    const timer = window.setInterval(
      () => void load().catch(() => undefined),
      1800,
    );
    return () => window.clearInterval(timer);
  }, [load]);
  const action = async (payload: Json) => {
    try {
      setData(
        await coreApi<{ builtins: Json[]; extensions: Json[] }>(
          "POST",
          "/v2/management/tools",
          payload,
          true,
        ),
      );
      setMessage("הפעולה הושלמה והקטלוג נטען מחדש.");
      return true;
    } catch (reason) {
      setMessage(`הפעולה לא הושלמה: ${String(reason)}`);
      return false;
    }
  };
  const choosePath = async (
    actionName: "install_skill" | "install_custom" | "install_mcp",
    kind: "file" | "directory",
  ) => {
    setInstallChoice(null);
    try {
      const path = await invoke<string | null>("pick_management_path", {
        kind,
      });
      if (path) await action({ action: actionName, path });
    } catch (reason) {
      setMessage(`לא ניתן לבחור את קובץ ההתקנה: ${String(reason)}`);
    }
  };
  const builtinGroups = new Map<string, { label: string; items: Json[] }>();
  for (const item of data.builtins) {
    const category = String(item.category || "developer");
    const group = builtinGroups.get(category) || {
      label: String(item.category_label || category),
      items: [],
    };
    group.items.push(item);
    builtinGroups.set(category, group);
  }
  const extensions = data.extensions;
  const externalGroups = [
    {
      kind: "custom",
      title: "כלים חיצוניים",
      empty: "אין כלים חיצוניים מותקנים.",
      add: () => void choosePath("install_custom", "file"),
    },
    {
      kind: "mcp",
      title: "כלי MCP מותקנים",
      empty: "אין חבילות MCP מותקנות.",
      add: () => setInstallChoice("mcp"),
    },
    {
      kind: "skill",
      title: "מיומנויות מותקנות",
      empty: "אין מיומנויות מותקנות.",
      add: () => setInstallChoice("skill"),
    },
  ];
  const toggle = (item: Json, kind: string) =>
    void action(
      kind === "builtin"
        ? {
            action: "set_enabled",
            kind,
            name: item.name,
            enabled: !item.enabled,
          }
        : {
            action: "set_trust",
            kind,
            name: item.name,
            trusted: !item.enabled,
          },
    );
  const row = (item: Json, kind: string) => (
    <div
      className="source-tool-row"
      key={`${kind}:${String(item.name)}`}
      title={String(item.description || "")}
    >
      <label
        className="source-tool-toggle"
        title={Boolean(item.enabled) ? "כיבוי" : "הפעלה"}
      >
        <input
          type="checkbox"
          checked={Boolean(item.enabled)}
          onChange={() => toggle(item, kind)}
          aria-label={`${Boolean(item.enabled) ? "כבה" : "הפעל"} ${String(item.name)}`}
        />
      </label>
      {kind !== "builtin" && Boolean(item.removable) && (
        <button
          type="button"
          className="source-tool-delete"
          title="מחק לחלוטין"
          aria-label={`מחק ${String(item.name)}`}
          onClick={() => setDeleting(item)}
        >
          <LegacyIcon src={icons.delete} size={17} />
        </button>
      )}
      <button
        type="button"
        className="source-tool-name"
        onClick={() => toggle(item, kind)}
      >
        <b dir="auto">{String(item.label || item.name)}</b>
        {kind === "skill" && (
          <small>{String(item.source_label || "הותקן ידנית")}</small>
        )}
      </button>
    </div>
  );
  return (
    <div className="management-page source-tools-page">
      <PageHero
        title="ניהול כלים"
        description="כאן מנהלים אילו יכולות זמינות לסמארטי. התקנה ידנית זמינה מכפתור + ליד האזור המתאים."
        actions={
          <button
            className="source-tools-refresh"
            title="רענון קטלוג הכלים"
            aria-label="רענון קטלוג הכלים"
            onClick={() => void action({ action: "refresh" })}
          >
            <LegacyIcon src={icons.checkUpdates} size={22} />
          </button>
        }
      />
      <p role="status" className="settings-status">
        {message}
      </p>
      <section className="source-tools-section">
        <header>
          <h3>כלים מובנים</h3>
        </header>
        {[...builtinGroups.entries()].map(([category, group]) => (
          <div className="source-tools-category" key={category}>
            <h4>{group.label}</h4>
            {group.items.map((item) => row(item, "builtin"))}
          </div>
        ))}
        {!builtinGroups.size && (
          <p className="management-empty">לא נמצאו כלים מובנים.</p>
        )}
      </section>
      {externalGroups.map((group) => {
        const items = extensions.filter((item) => item.kind === group.kind);
        return (
          <section className="source-tools-section" key={group.kind}>
            <header>
              <button
                type="button"
                className="source-tools-add"
                title={`הוספה: ${group.title}`}
                aria-label={`הוספה: ${group.title}`}
                onClick={group.add}
              >
                <LegacyIcon src={icons.plus} size={22} />
              </button>
              <h3>{group.title}</h3>
            </header>
            {items.map((item) => row(item, group.kind))}
            {!items.length && (
              <p className="source-tools-empty">{group.empty}</p>
            )}
          </section>
        );
      })}
      {installChoice && (
        <div className="legacy-dialog-backdrop" role="presentation">
          <section
            className="legacy-input-dialog source-install-choice"
            role="dialog"
            aria-modal="true"
            aria-label={
              installChoice === "skill" ? "התקנת מיומנות" : "הוספת MCP"
            }
          >
            <h2>{installChoice === "skill" ? "התקנת מיומנות" : "הוספת MCP"}</h2>
            <p>מקור התקנה:</p>
            <div>
              {installChoice === "skill" ? (
                <>
                  <button
                    onClick={() => void choosePath("install_skill", "file")}
                  >
                    קובץ ZIP
                  </button>
                  <button
                    onClick={() =>
                      void choosePath("install_skill", "directory")
                    }
                  >
                    תיקייה
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => {
                      setInstallChoice(null);
                      setPackageDialog(true);
                    }}
                  >
                    חבילת npm נעולה
                  </button>
                  <button
                    onClick={() => void choosePath("install_mcp", "file")}
                  >
                    קובץ JSON
                  </button>
                </>
              )}
            </div>
            <footer>
              <button onClick={() => setInstallChoice(null)}>ביטול</button>
            </footer>
          </section>
        </div>
      )}
      {packageDialog && (
        <InputDialog
          title="הוספת MCP"
          label="שם חבילה עם גרסה, למשל @scope/server@1.2.3"
          confirmLabel="התקנה"
          onCancel={() => setPackageDialog(false)}
          onConfirm={(value) => {
            void action({ action: "install_mcp", package: value });
            setPackageDialog(false);
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="מחיקת הרחבה"
          description={`למחוק לחלוטין את ${String(deleting.name)}? הפריט יוסר מהדיסק ורישומי ההרשאות והאמון שלו ינוקו. לא ניתן לשחזר אותו מתוך סמארטי.`}
          danger
          onCancel={() => setDeleting(null)}
          onConfirm={() => {
            void action({
              action: "delete",
              kind: deleting.kind,
              name: deleting.name,
            });
            setDeleting(null);
          }}
        />
      )}
    </div>
  );
}

export function DiagnosticsView() {
  const [items, setItems] = useState<Json[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("עוד לא בוצעה בדיקה.");
  const [repairing, setRepairing] = useState<Json | null>(null);
  const [filter, setFilter] = useState("all");
  const [progress, setProgress] = useState(0);
  const scan = async (includeNetwork: boolean) => {
    setBusy(true);
    setProgress(0);
    setMessage("בודק את Python Core ואת מעטפת Tauri…");
    const poll = window.setInterval(() => {
      void coreApi<Json>("GET", "/v2/management/diagnostics")
        .then((state) => {
          const current = Number(state.current || 0);
          const total = Number(state.total || 0);
          if (total > 0) setProgress(Math.round((current / total) * 100));
          if (state.label)
            setMessage(`${String(state.label)} (${current}/${total})`);
        })
        .catch(() => undefined);
    }, 250);
    try {
      const [coreResults, desktopResults] = await Promise.all([
        coreApi<{ items: Json[] }>(
          "POST",
          "/v2/management/diagnostics",
          { action: "scan", include_network: includeNetwork },
          true,
        ),
        invoke<{ items: Json[] }>("desktop_diagnostic_snapshot"),
      ]);
      setProgress(100);
      setItems([...desktopResults.items, ...coreResults.items]);
      setMessage("הבדיקה הסתיימה. ניתן לסנן תוצאות ולפתוח פרטים טכניים.");
    } catch (reason) {
      const detail = String(reason);
      setMessage(
        detail.includes("diagnostic_blocked_while_agent_running")
          ? "אי אפשר להפעיל בדיקת בריאות בזמן שסמארטי מבצע משימה. יש להמתין לסיום המשימה או לעצור אותה ואז לנסות שוב."
          : `בדיקת הבריאות לא הושלמה: ${detail}`,
      );
    } finally {
      window.clearInterval(poll);
      setBusy(false);
    }
  };
  const repair = async () => {
    if (!repairing) return;
    await coreApi(
      "POST",
      "/v2/management/diagnostics",
      { action: "repair", repair_id: repairing.id },
      true,
    );
    setRepairing(null);
    await scan(false);
  };
  const filtered = items.filter(
    (item) =>
      filter === "all" ||
      (filter === "attention"
        ? ["error", "warning"].includes(String(item.status))
        : item.status === filter),
  );
  const errors = items.filter((item) => item.status === "error").length;
  const warnings = items.filter((item) => item.status === "warning").length;
  const score = items.length
    ? Math.max(0, 100 - errors * 24 - warnings * 9)
    : "—";
  const cancel = async () => {
    setMessage("שולח בקשת עצירה…");
    await coreApi(
      "POST",
      "/v2/management/diagnostics",
      { action: "cancel" },
      true,
    );
    setMessage("בקשת הביטול התקבלה; הבדיקה תסתיים בנקודת עצירה בטוחה.");
  };
  return (
    <div className="management-page">
      <section className="diagnostic-hero">
        <strong>{score}</strong>
        <div>
          <h2>Smarti Diagnostic</h2>
          <p>{message}</p>
          {busy && <progress value={progress} max="100" />}
        </div>
        <button disabled={busy} onClick={() => void scan(false)}>
          בדיקה מהירה
        </button>
        <button disabled={busy} onClick={() => void scan(true)}>
          בדיקה מלאה
        </button>
        <button disabled={!busy} onClick={() => void cancel()}>
          עצור
        </button>
      </section>
      <div className="diagnostic-filters">
        {[
          ["all", "הכול"],
          ["attention", "דורש תשומת לב"],
          ["pass", "תקין"],
          ["skipped", "דולג"],
        ].map(([id, label]) => (
          <button
            className={filter === id ? "active" : ""}
            key={id}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
        <span>
          {items.length} בדיקות · {errors} שגיאות · {warnings} אזהרות
        </span>
      </div>
      <div className="management-cards">
        {filtered.map((item) => (
          <article key={String(item.id)} className={`status-${item.status}`}>
            <header>
              <b>{String(item.title_he)}</b>
              <span>{String(item.status)}</span>
            </header>
            <p>{String(item.explanation_he)}</p>
            <details>
              <summary>פרטים טכניים</summary>
              <pre dir="ltr">{String(item.technical_detail)}</pre>
            </details>
            {Boolean(item.repair_action) && (
              <footer>
                <button
                  onClick={() => setRepairing(item.repair_action as Json)}
                >
                  {String((item.repair_action as Json).title_he)}
                </button>
              </footer>
            )}
          </article>
        ))}
      </div>
      {repairing && (
        <ConfirmDialog
          title="אישור תיקון"
          description={`לבצע את התיקון: ${String(repairing.title_he)}? רק הפעולה המתוארת תועבר ל־Python Core.`}
          onCancel={() => setRepairing(null)}
          onConfirm={() => void repair()}
        />
      )}
    </div>
  );
}

export function UsageView() {
  const cacheKey = "smarti.management.usage-cache";
  const [data, setData] = useState<Json>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(cacheKey) || "{}");
    } catch {
      return {};
    }
  });
  const [timeframe, setTimeframe] = useState("today");
  const [confirmClear, setConfirmClear] = useState(false);
  useEffect(() => {
    void coreApi<Json>(
      "GET",
      `/v2/management/usage?timeframe=${timeframe}`,
    ).then((value) => {
      setData(value);
      sessionStorage.setItem(cacheKey, JSON.stringify(value));
    });
  }, [timeframe]);
  const clear = async () => {
    const value = await coreApi<Json>(
      "DELETE",
      "/v2/management/usage",
      {},
      true,
    );
    setData(value);
    setConfirmClear(false);
    sessionStorage.removeItem(cacheKey);
  };
  const memory =
    data.memory && typeof data.memory === "object" ? (data.memory as Json) : {};
  return (
    <div className="management-page">
      <PageHero
        title="נתוני שימוש (טוקנים)"
        description="טעינה ראשונית מהמטמון המקומי ורענון אסינכרוני, ללא בקשת מודל."
        actions={
          <button className="danger" onClick={() => setConfirmClear(true)}>
            ניקוי נתונים
          </button>
        }
      >
        <div className="usage-total">
          <strong>
            {Number(data.total_tokens || 0).toLocaleString("he-IL")}
          </strong>{" "}
          טוקנים · עלות מתועדת ${Number(data.cost_usd || 0).toFixed(4)}
        </div>
      </PageHero>
      <div className="segmented">
        {[
          ["today", "היום"],
          ["week", "שבוע"],
          ["month", "חודש"],
          ["all", "הכול"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={timeframe === id ? "active" : ""}
            onClick={() => setTimeframe(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="management-cards compact">
        {asRows(data.models).map((item) => (
          <article key={String(item.model)}>
            <header>
              <b>{String(item.model)}</b>
              <span>{Number(item.tokens || 0).toLocaleString("he-IL")}</span>
            </header>
            <p>
              קלט {Number(item.input_tokens || 0).toLocaleString("he-IL")} · פלט{" "}
              {Number(item.output_tokens || 0).toLocaleString("he-IL")}
              <br />
              מטמון נקרא{" "}
              {Number(item.cached_input_tokens || 0).toLocaleString("he-IL")} ·
              מטמון נכתב{" "}
              {Number(item.cache_write_tokens || 0).toLocaleString("he-IL")}
            </p>
            <small>עלות מתועדת ${Number(item.cost_usd || 0).toFixed(4)}</small>
          </article>
        ))}
        {!asRows(data.models).length && (
          <p className="management-empty">אין נתוני שימוש לתקופה הזו.</p>
        )}
      </div>
      <section className="special-settings-card">
        <h3>זיכרון מקומי ו־RAG</h3>
        <p>
          פעילים {Number(memory.active || 0)} · בארכיון{" "}
          {Number(memory.archive || 0)} · רגישים {Number(memory.sensitive || 0)}{" "}
          · אחסון {Number(memory.storage_bytes || 0).toLocaleString("he-IL")}{" "}
          בתים
        </p>
      </section>
      {confirmClear && (
        <ConfirmDialog
          title="ניקוי נתוני שימוש"
          description="הנתונים המקומיים יאופסו לאחר יצירת גיבוי. פעולה זו אינה מוחקת היסטוריית שיחות."
          danger
          onCancel={() => setConfirmClear(false)}
          onConfirm={() => void clear()}
        />
      )}
    </div>
  );
}

export function LogsView() {
  const [lines, setLines] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [personal, setPersonal] = useState(false);
  const load = useCallback(async () => {
    const value = await coreApi<{ lines: string[]; path: string }>(
      "GET",
      `/v2/management/logs?limit=1000&personal=${personal ? "shown" : "hidden"}`,
    );
    setLines(value.lines);
    setPath(value.path);
  }, [personal]);
  useEffect(() => {
    void load();
  }, [load]);
  const exportLog = async () => {
    await invoke("save_text_file", {
      suggestedName: "SmartiAI-log.txt",
      contents: lines.join("\n"),
    });
  };
  return (
    <div className="management-page logs-page">
      <PageHero
        title="Developer Trace"
        description="התוכן האישי מוסתר כברירת מחדל; מטא־נתונים טכניים נשמרים."
        actions={
          <>
            <label>
              הצג תוכן אישי{" "}
              <input
                type="checkbox"
                checked={personal}
                onChange={(event) => setPersonal(event.target.checked)}
              />
            </label>
            <button onClick={() => void load()}>רענון</button>
            <button onClick={() => void exportLog()}>ייצוא</button>
          </>
        }
      >
        <span dir="ltr">{path}</span>
      </PageHero>
      <pre dir="ltr">{lines.join("\n") || "אין עדיין רשומות לוג."}</pre>
    </div>
  );
}

function relativeUpdateStatus(values: Json) {
  const available = String(values.updates_last_available_version || "").trim();
  if (available) return `עדכון זמין: גרסה ${available}`;
  const raw = String(values.updates_last_checked_at || "").trim();
  if (!raw) return "עדיין לא בוצעה בדיקת עדכונים.";
  const elapsed = Math.max(0, Date.now() - new Date(raw).getTime());
  const minutes = Math.floor(elapsed / 60_000);
  if (minutes < 1) return "בדיקה אחרונה: עכשיו";
  if (minutes < 60)
    return `בדיקה אחרונה: ${minutes === 1 ? "לפני דקה" : `לפני ${minutes} דקות`}`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24)
    return `בדיקה אחרונה: ${hours === 1 ? "לפני שעה" : `לפני ${hours} שעות`}`;
  const days = Math.floor(hours / 24);
  return `בדיקה אחרונה: ${days === 1 ? "אתמול" : `לפני ${days} ימים`}`;
}

export function UpdateControls({
  compact = false,
  theme = "dark",
}: {
  compact?: boolean;
  theme?: ResolvedTheme;
}) {
  const [update, setUpdate] = useState<Update | null>(null);
  const [status, setStatus] = useState("עדיין לא בוצעה בדיקת עדכונים.");
  const [checking, setChecking] = useState(false);
  const icons = legacyAssets(theme);
  useEffect(() => {
    void coreApi<SafeSettings>("GET", "/v2/settings")
      .then((safe) => setStatus(relativeUpdateStatus(safe.values)))
      .catch(() => undefined);
  }, []);
  const checkUpdate = async () => {
    setChecking(true);
    setStatus("בודק עדכונים...");
    try {
      const found = await check();
      setUpdate(found);
      const values = {
        updates_last_checked_at: new Date().toISOString(),
        updates_last_available_version: found?.version || "",
      };
      await coreApi("PATCH", "/v2/settings", { values }, true);
      setStatus(
        found ? `עדכון זמין: גרסה ${found.version}` : "בדיקה אחרונה: עכשיו",
      );
    } catch (reason) {
      setStatus(`בדיקת העדכון נכשלה: ${String(reason)}`);
    } finally {
      setChecking(false);
    }
  };
  const install = async () => {
    if (!update) return;
    setStatus("מוריד ומאמת חתימה…");
    try {
      await update.downloadAndInstall((event) => {
        if (event.event === "Finished")
          setStatus("העדכון אומת והותקן. מפעיל מחדש…");
      });
      await relaunch();
    } catch (reason) {
      setStatus(`העדכון נכשל ללא שינוי בגרסה המותקנת: ${String(reason)}`);
    }
  };
  return (
    <div className={compact ? "update-controls compact" : "update-controls"}>
      <span className="source-update-status" role="status">
        {status}
      </span>
      <button disabled={checking} onClick={() => void checkUpdate()}>
        <LegacyIcon src={icons.checkUpdates} size={18} />
        בדוק עדכונים עכשיו
      </button>
      {update && (
        <>
          <button onClick={() => void install()}>הורד והתקן</button>
          <button
            onClick={() => {
              setUpdate(null);
              setStatus("העדכון נדחה. לא בוצע שינוי.");
            }}
          >
            אחר כך
          </button>
        </>
      )}
      {update?.body && (
        <details>
          <summary>מה חדש</summary>
          <pre dir="auto">{update.body}</pre>
        </details>
      )}
    </div>
  );
}

export function AboutView({ theme }: { theme: ResolvedTheme }) {
  const [data, setData] = useState<Json>({});
  const icons = legacyAssets(theme);
  useEffect(() => {
    void coreApi<Json>("GET", "/v2/management/about").then(setData);
  }, []);
  const features = [
    "צ׳אט עם ספקי AI ומודלים מקומיים",
    "כלי Windows, קבצים ו־Office",
    "Smarti Browser ו־Canvas מבודד",
    "זיכרון מקומי מוצפן וממוסך",
    "משימות רקע ואישורים",
    "אבחון, פרטיות ועדכונים חתומים",
  ];
  return (
    <div className="management-page about-page">
      <section>
        <div className="about-logo-wrap">
          <img className="about-logo" src={icons.logo} alt="SmartiAI" />
        </div>
        <h2>{String(data.name || "Smarti AI Agent for Windows")}</h2>
        <p className="about-tagline">סוכן AI חכם ל־Windows</p>
        <b>גרסה {String(data.version || "")}</b>
        <p>{String(data.description || "")}</p>
        <small>
          Python {String(data.python || "")} · Control Plane{" "}
          {String(data.contract_version || "")}
        </small>
        <button
          onClick={() =>
            void invoke("open_chat_link", {
              target:
                "https://github.com/menachem-dadon/SmartiAI-Agent-for-Windows",
              local: false,
            })
          }
        >
          פתח את מאגר GitHub
        </button>
        <div className="about-feature-grid">
          {features.map((item) => (
            <article key={item}>{item}</article>
          ))}
        </div>
        <section className="about-examples">
          <h3>מה אפשר לעשות היום</h3>
          <p>
            לסכם מסמכים, ליצור תוצרים, לארגן קבצים, לחפש מידע, לעבוד בדפדפן,
            לשמור זיכרונות ולתזמן משימות.
          </p>
        </section>
        <section className="about-privacy">
          <h3>פרטיות ובטיחות</h3>
          <p>
            נתוני runtime נשמרים מקומית כברירת מחדל. מידע נשלח לצד שלישי רק כאשר
            משתמשים בספק, אתר או כלי חיצוני, ובכפוף למדיניות ההרשאות.
          </p>
        </section>
        <UpdateControls theme={theme} />
        <footer>
          פותח ע״י א.מ.ד. | 2026 |{" "}
          <a href="mailto:em0548438097@gmail.com">em0548438097@gmail.com</a>
        </footer>
      </section>
    </div>
  );
}
