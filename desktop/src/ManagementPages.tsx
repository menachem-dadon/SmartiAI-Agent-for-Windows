import { Dialog, EmptyState, IconButton, LoadingState, SearchField, Switch } from "./design-system";
import { builtinToolDescription } from "./toolDescriptions";
import { ManagementFeedback } from "./managementFeedback";
import { Button, Textarea, NumberField, SelectField, Field, Icon } from "./design-system";
import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { checkForUpdates, type AvailableUpdate } from "./updates";
import { coreApi } from "./coreApi";
import type { ResolvedTheme } from "./designSystem";
import { legacyAssets } from "./legacyAssets";
import { ConfirmDialog, InputDialog, PageHero } from "./SettingsManagement";
import { LEGAL_AGREEMENT_TEXT, type LegalStatus } from "./LegalAgreement";

type Json = Record<string, unknown>;
type SafeSettings = { values: Json };
const relaunch = () => invoke("restart_after_update");

export { WorkspaceView } from "./WorkspaceView";

export function TasksView() {
  const [items, setItems] = useState<Json[]>([]);
  const [prompt, setPrompt] = useState("");
  const [delay, setDelay] = useState(5);
  const [repeat, setRepeat] = useState("once");
  const [weeklyDays, setWeeklyDays] = useState("0");
  const [conversationMode, setConversationMode] = useState("dedicated");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Json | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Json | null>(null);
  const [creating, setCreating] = useState(false), [loading, setLoading] = useState(true), [query, setQuery] = useState("");
  const [pending, setPending] = useState(false), actionGuard = useRef(false);
  const load = useCallback(async () => {
    setLoading(true);
    try { setItems((await coreApi<{ items: Json[] }>("GET", "/v2/management/tasks")).items); setError(""); }
    catch (reason) { setError(`טעינת המשימות נכשלה: ${String(reason)}`); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const action = async (payload: Json) => {
    if (actionGuard.current) return false;
    actionGuard.current = true; setPending(true);
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
      setError(`הפעולה נכשלה: ${String(reason)}`);
      return false;
    } finally {
      actionGuard.current = false; setPending(false);
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
        description="משימות שנוצרות כאן ירוצו בשיחה ייעודית שתישמר בין הרצות, או בשיחה חדשה בכל הרצה."
        actions={<><IconButton icon="refresh" label="רענן" disabled={loading} onClick={() => void load()} /><Button icon="plus" variant="primary" onClick={() => setCreating(value => !value)}>{creating ? "סגור יצירה" : "משימה חדשה"}</Button></>}
      />
      <form
        className="task-create" hidden={!creating}
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
            if (saved) { setPrompt(""); setCreating(false); }
          });
        }}
      >
        <Textarea label="מה Smarti יבצע?" hiddenLabel
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="מה Smarti יבצע?"
          required
        />
        <div>
          בעוד{" "}
          <NumberField label="בעוד דקות" hiddenLabel

            min="0"
            value={delay}
            onChange={(event) => setDelay(Number(event.target.value))}
          />{" "}
          דקות
        </div>
        <SelectField label="חזרה" hiddenLabel
          value={repeat}
          onChange={(event) => setRepeat(event.target.value)}
        >
          <option value="once">חד־פעמית</option>
          <option value="interval">מחזורית</option>
          <option value="weekly">שבועית</option>
        </SelectField>
        {repeat === "weekly" && (
          <div>
            ימי שבוע
            <Field label="ימי שבוע" hiddenLabel
              dir="ltr"
              value={weeklyDays}
              onChange={(event) => setWeeklyDays(event.target.value)}
            />
          </div>
        )}
        <SelectField label="שיחת המשימה" hiddenLabel
          aria-label="שיחת המשימה"
          value={conversationMode}
          onChange={(event) => setConversationMode(event.target.value)}
        >
          <option value="dedicated">שיחה ייעודית למשימה</option>
          <option value="new">שיחה חדשה בכל הרצה</option>
        </SelectField>
        <Button type="submit" variant="primary" icon="plus" loading={pending}>יצירת משימה</Button>
      </form>
      {error && <ManagementFeedback message={error} />}
      <SearchField label="חיפוש במשימות" hiddenLabel placeholder="חיפוש במשימות" value={query} onChange={event => setQuery(event.target.value)} />
      {loading && <LoadingState label="טוען משימות…" />}
      <div className="management-cards">
        {items.filter(item => String(item.prompt || item.message || "").includes(query)).map((item) => (
          <article key={String(item.id)}>
            <header>
              <b>{String(item.prompt || item.message || "משימה")}</b>
              <span>{String(item.status)}</span>
            </header>
            <p>
              תזמון: {String(item.run_at || "")} · חזרה:{" "}
              {String(item.repeat || "once")} · ניתוב:{" "}
              {String(item.conversation_mode || "dedicated")}
            </p>
            <small>
              תוצאה אחרונה: {String(item.last_result || "טרם הופעלה")}
            </small>
            <footer>
              <IconButton icon="rename" label="עריכה" type="button" onClick={() => setEditing(item)} />
              {String(item.status) === "cancelled" && (
                <Button type="button"
                  onClick={() => void action({ action: "resume", id: item.id })}
                >
                  המשך
                </Button>
              )}
              <IconButton icon="play" label="הרץ שוב" type="button" disabled={["running", "cancelling"].includes(
                  String(item.status),
                )} onClick={() => void action({ action: "retry", id: item.id })} />
              <IconButton icon="stop" label="ביטול" type="button" disabled={
                  !["scheduled", "running"].includes(String(item.status))
                } onClick={() => void action({ action: "cancel", id: item.id })} />
              <IconButton icon="trash" label="מחיקה" type="button" disabled={["running", "cancelling"].includes(
                  String(item.status),
                )} onClick={() => setConfirmDelete(item)} />
            </footer>
          </article>
        ))}
        {!loading && !items.length && <EmptyState icon="tasks" title="אין משימות רקע" description="אפשר לבקש מסמארטי לבצע פעולה בהמשך ולבחור מתי היא תרוץ." action={<Button icon="plus" onClick={() => setCreating(true)}>משימה חדשה</Button>} />}
        {!loading && items.length > 0 && !items.some(item => String(item.prompt || item.message || "").includes(query)) && <EmptyState icon="search" title="אין תוצאות" description="נסה מילה אחרת מתוך תוכן המשימה." />}
      </div>
      {editing && (
        <InputDialog
          title="עריכת משימה"
          label="תוכן המשימה"
          initial={String(editing.prompt || editing.message || "")}
          onCancel={() => setEditing(null)}
          onConfirm={(value) => {
            return action({ action: "edit", id: editing.id, prompt: value }).then(ok => { if (ok) setEditing(null); return ok; });
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
            return action({ action: "delete", id: confirmDelete.id }).then(ok => { if (ok) setConfirmDelete(null); return ok; });
          }}
        />
      )}
    </div>
  );
}

export function ToolsView({ theme: _theme }: { theme: ResolvedTheme }) {
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
  const [loading, setLoading] = useState(true), [query, setQuery] = useState("");
  const [pending, setPending] = useState(false), actionGuard = useRef(false);
  const load = useCallback(async () => {
    try { setData(await coreApi<{ builtins: Json[]; extensions: Json[] }>("GET", "/v2/management/tools")); }
    catch (reason) { setMessage(`טעינת הכלים נכשלה: ${String(reason)}`); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    void load();
    const timer = window.setInterval(
      () => void load().catch(() => undefined),
      1800,
    );
    return () => window.clearInterval(timer);
  }, [load]);
  const action = async (payload: Json) => {
    if (actionGuard.current) return false;
    actionGuard.current = true; setPending(true);
    try {
      setData(
        await coreApi<{ builtins: Json[]; extensions: Json[] }>(
          "POST",
          "/v2/management/tools",
          payload,
          true,
        ),
      );
      setMessage("");
      return true;
    } catch (reason) {
      setMessage(`הפעולה לא הושלמה: ${String(reason)}`);
      return false;
    } finally {
      actionGuard.current = false; setPending(false);
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
  for (const item of data.builtins.filter(item => `${item.name} ${item.label} ${item.description} ${builtinToolDescription(String(item.name))}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()))) {
    const category = String(item.category || "developer");
    const group = builtinGroups.get(category) || {
      label: String(item.category_label || category),
      items: [],
    };
    group.items.push(item);
    builtinGroups.set(category, group);
  }
  const extensions = data.extensions.filter(item => `${item.name} ${item.description} ${item.source_label}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
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
      data-kind={kind}
      key={`${kind}:${String(item.name)}`}
      title={kind === "builtin" ? builtinToolDescription(String(item.name)) : String(item.description || "")}
    >
      <div
        className="source-tool-toggle"
        title={Boolean(item.enabled) ? "כיבוי" : "הפעלה"}
      >
        <Switch label={`${Boolean(item.enabled) ? "כבה" : "הפעל"} ${String(item.name)}`}
          checked={Boolean(item.enabled)}
          disabled={pending}
          onCheckedChange={() => toggle(item, kind)}
          aria-label={`${Boolean(item.enabled) ? "כבה" : "הפעל"} ${String(item.name)}`}
        />
      </div>
      {kind !== "builtin" && Boolean(item.removable) && (
        <div className="source-tool-delete"><IconButton icon="trash" label={`מחק ${String(item.name)}`} type="button" onClick={() => setDeleting(item)} /></div>
      )}
      <Button
        type="button"
        className="source-tool-name"
        dir="rtl"
        disabled={pending}
        onClick={() => toggle(item, kind)}
      >
        <b dir="auto">{String(item.label || item.name)}</b>
        <small>{kind === "builtin" ? builtinToolDescription(String(item.name)) : String(item.description || "")}</small>
        {kind === "skill" && (
          <small>{String(item.source_label || "הותקן ידנית")}</small>
        )}
      </Button>
    </div>
  );
  return (
    <div className="management-page source-tools-page">
      <PageHero
        title="ניהול כלים"
        description="כאן מנהלים אילו יכולות זמינות לסמארטי. התקנה ידנית זמינה מכפתור + ליד האזור המתאים."
        actions={
          <IconButton icon={"refresh"} label="רענון קטלוג הכלים" type="button" className="source-tools-refresh" onClick={() => void action({ action: "refresh" })} />
        }
      />
      <SearchField label="חיפוש כלים וחיבורים" hiddenLabel placeholder="חיפוש כלים וחיבורים" value={query} onChange={event => setQuery(event.target.value)} />
      {loading && <LoadingState label="טוען כלים וחיבורים…" />}
      <ManagementFeedback message={message} />
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
              <h3>{group.title}</h3>
              <IconButton icon={"plus"} label={`הוספה: ${group.title}`} type="button" className="source-tools-add" onClick={group.add} />
            </header>
            {items.map((item) => row(item, group.kind))}
            {!items.length && (
              <p className="source-tools-empty">{group.empty}</p>
            )}
          </section>
        );
      })}
      {installChoice && (
        <Dialog open title={installChoice === "skill" ? "התקנת מיומנות" : "הוספת MCP"} onClose={() => setInstallChoice(null)}>
          <section className="source-install-choice">
            <p>מקור התקנה:</p>
            <div>
              {installChoice === "skill" ? (
                <>
                  <Button type="button"
                    onClick={() => void choosePath("install_skill", "file")}
                  >
                    קובץ ZIP
                  </Button>
                  <Button type="button"
                    onClick={() =>
                      void choosePath("install_skill", "directory")
                    }
                  >
                    תיקייה
                  </Button>
                </>
              ) : (
                <>
                  <Button type="button"
                    onClick={() => {
                      setInstallChoice(null);
                      setPackageDialog(true);
                    }}
                  >
                    חבילת npm נעולה
                  </Button>
                  <Button type="button"
                    onClick={() => void choosePath("install_mcp", "file")}
                  >
                    קובץ JSON
                  </Button>
                </>
              )}
            </div>
            <footer>
              <IconButton icon="stop" label="ביטול" type="button" onClick={() => setInstallChoice(null)} />
            </footer>
          </section>
        </Dialog>
      )}
      {packageDialog && (
        <InputDialog
          title="הוספת MCP"
          label="שם חבילה עם גרסה, למשל @scope/server@1.2.3"
          confirmLabel="התקנה"
          onCancel={() => setPackageDialog(false)}
          onConfirm={(value) => {
            return action({ action: "install_mcp", package: value }).then(ok => { if (ok) setPackageDialog(false); return ok; });
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
            return action({ action: "delete", kind: deleting.kind, name: deleting.name }).then(ok => { if (ok) setDeleting(null); return ok; });
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
    setMessage("בודק את המערכת…");
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
      <PageHero title="אבחון המערכת" description="בדיקות מערכת, תוצאות ותיקונים באישור מפורש." />
      <section className="diagnostic-hero">
        <strong>{score}</strong>
        <div>
          <ManagementFeedback message={message} />
          {busy && <progress value={progress} max="100" />}
        </div>
        <Button type="button" disabled={busy} onClick={() => void scan(false)}>
          בדיקה מהירה
        </Button>
        <Button type="button" disabled={busy} onClick={() => void scan(true)}>
          בדיקה מלאה
        </Button>
        <Button type="button" disabled={!busy} onClick={() => void cancel().catch(reason => setMessage(`בקשת העצירה נכשלה: ${String(reason)}`))}>
          עצור
        </Button>
      </section>
      <div className="diagnostic-filters">
        {[
          ["all", "הכול"],
          ["attention", "דורש תשומת לב"],
          ["pass", "תקין"],
          ["skipped", "דולג"],
        ].map(([id, label]) => (
          <Button type="button"
            className={filter === id ? "active" : ""}
            key={id}
            onClick={() => setFilter(id)}
          >
            {label}
          </Button>
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
                <Button type="button"
                  onClick={() => setRepairing(item.repair_action as Json)}
                >
                  {String((item.repair_action as Json).title_he)}
                </Button>
              </footer>
            )}
          </article>
        ))}
      </div>
      {repairing && (
        <ConfirmDialog
          title="אישור תיקון"
          description={`לבצע את התיקון: ${String(repairing.title_he)}? רק הפעולה המתוארת תבוצע.`}
          onCancel={() => setRepairing(null)}
          onConfirm={repair}
        />
      )}
    </div>
  );
}

export { UsageView } from "./UsageView";

export function LogsView() {
  const [lines, setLines] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [personal, setPersonal] = useState(false), [query, setQuery] = useState(""), [error, setError] = useState("");
  const load = useCallback(async () => {
    const value = await coreApi<{ lines: string[]; path: string }>(
      "GET",
      `/v2/management/logs?limit=1000&personal=${personal ? "shown" : "hidden"}`,
    );
    setLines(value.lines);
    setPath(value.path);
    setError("");
  }, [personal]);
  useEffect(() => {
    void load().catch(reason => setError(`טעינת הלוג נכשלה: ${String(reason)}`));
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
        title="מעקב למפתחים"
        description="התוכן האישי מוסתר כברירת מחדל; מטא־נתונים טכניים נשמרים."
        actions={
          <>
            <div>
              הצג תוכן אישי{" "}
              <Switch label="הצג תוכן אישי"

                checked={personal}
                onCheckedChange={(checked) => setPersonal(checked)}
              />
            </div>
            <IconButton icon="refresh" label="רענון" type="button" onClick={() => void load().catch(reason => setError(`טעינת הלוג נכשלה: ${String(reason)}`))} />
            <Button type="button" onClick={() => void exportLog().catch(reason => setError(`ייצוא הלוג נכשל: ${String(reason)}`))}>ייצוא</Button>
          </>
        }
      >
        <span dir="ltr">{path}</span>
      </PageHero>
      <ManagementFeedback message={error} />
      <SearchField label="חיפוש בלוג" hiddenLabel placeholder="חיפוש בלוג" value={query} onChange={event => setQuery(event.target.value)} />
      <pre dir="ltr">{lines.filter(line => line.toLocaleLowerCase().includes(query.toLocaleLowerCase())).join("\n") || "אין רשומות להצגה."}</pre>
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
  theme: _theme = "dark",
}: {
  compact?: boolean;
  theme?: ResolvedTheme;
}) {
  const [update, setUpdate] = useState<AvailableUpdate | null>(null);
  const [status, setStatus] = useState("עדיין לא בוצעה בדיקת עדכונים.");
  const [checking, setChecking] = useState(false);
  const operation = useRef(false);
  useEffect(() => {
    void coreApi<SafeSettings>("GET", "/v2/settings")
      .then((safe) => setStatus(relativeUpdateStatus(safe.values)))
      .catch(() => undefined);
  }, []);
  const checkUpdate = async () => {
    if (operation.current) return; operation.current = true;
    setChecking(true);
    setStatus("בודק עדכונים...");
    try {
      const found = await checkForUpdates();
      setUpdate(found);
      setStatus(
        found ? `עדכון זמין: גרסה ${found.version}` : "בדיקה אחרונה: עכשיו",
      );
    } catch (reason) {
      setStatus(`בדיקת העדכון נכשלה: ${String(reason)}`);
    } finally {
      setChecking(false);
      operation.current = false;
    }
  };
  const install = async () => {
    if (!update?.installer || operation.current) return;
    operation.current = true; setChecking(true);
    setStatus("מוריד ומאמת חתימה…");
    try {
      await update.installer.downloadAndInstall((event) => {
        if (event.event === "Finished")
          setStatus("העדכון אומת והותקן. מפעיל מחדש…");
      });
      await relaunch();
    } catch (reason) {
      setStatus(`העדכון נכשל ללא שינוי בגרסה המותקנת: ${String(reason)}`);
    } finally {
      operation.current = false; setChecking(false);
    }
  };
  return (
    <div className={compact ? "update-controls compact" : "update-controls"}>
      <ManagementFeedback message={status} />
      <Button type="button" disabled={checking} onClick={() => void checkUpdate()}>
        <Icon name={"refresh"} size={18} />
        בדוק עדכונים עכשיו
      </Button>
      {update && (
        <>
          {update.installer && (
            <Button type="button" loading={checking} onClick={() => void install()}>הורד והתקן</Button>
          )}
          {update.releaseUrl && (
            <Button type="button" onClick={() => void invoke("open_chat_link", {
              target: update.releaseUrl, local: false,
            }).catch((reason) => setStatus(`פתיחת עמוד הגרסה נכשלה: ${String(reason)}`))}>
              עמוד הגרסה
            </Button>
          )}
          <Button type="button"
            disabled={checking}
            onClick={() => {
              setUpdate(null);
              setStatus("העדכון נדחה. לא בוצע שינוי.");
            }}
          >
            אחר כך
          </Button>
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
  const [data, setData] = useState<Json>({}), [error, setError] = useState("");
  const [legal, setLegal] = useState<LegalStatus | null>(null);
  const load = useCallback(async () => {
    setError("");
    await Promise.allSettled([
      coreApi<Json>("GET", "/v2/management/about").then(setData).catch(reason => setError(`טעינת פרטי התוכנה נכשלה: ${String(reason)}`)),
      coreApi<LegalStatus>("GET", "/v2/management/legal").then(setLegal).catch(reason => setError(`טעינת ההסכמה נכשלה: ${String(reason)}`)),
    ]);
  }, []);
  useEffect(() => { void load(); }, [load]);
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
      <PageHero title="אודות והסכמות" description="מידע על התוכנה, תנאי השימוש ועדכונים." actions={<IconButton icon="refresh" label="רענון פרטי התוכנה" onClick={() => void load()} />} />
      <ManagementFeedback message={error} />
      <section>
        <div className="about-logo-wrap">
          <img className="about-logo" src={legacyAssets(theme).logo} alt="SmartiAI" />
        </div>
        <h2>{String(data.name || "Smarti AI Agent for Windows")}</h2>
        <p className="about-tagline">סוכן AI חכם ל־Windows</p>
        <b>גרסה {String(data.version || "")}</b>
        <p>{String(data.description || "")}</p>
        <small>
          Python {String(data.python || "")} · Control Plane{" "}
          {String(data.contract_version || "")}
        </small>
        <Button
          className="about-support-button"
          dir="rtl"
          aria-label="קנה לי קפה! — תמיכה בפיתוח סמארטי דרך Buy Me a Coffee (נפתח בדפדפן)"
          onClick={() =>
            void invoke("open_chat_link", {
              target: "https://www.buymeacoffee.com/EMD.Dev",
              local: false,
            }).catch(reason => setError(`פתיחת עמוד התמיכה נכשלה: ${String(reason)}`))
          }
        >
          <img className="about-support-logo" src="/brands/buy-me-a-coffee.svg" alt="" aria-hidden="true" />
          <span>קנה לי קפה!</span>
        </Button>
        <Button type="button"
          onClick={() =>
            void invoke("open_chat_link", {
              target:
                "https://github.com/menachem-dadon/SmartiAI-Agent-for-Windows",
              local: false,
            })
          }
        >
          פתח את מאגר GitHub
        </Button>
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
        <details className="about-agreement">
          <summary>מדיניות פרטיות ותנאי שימוש</summary>
          {legal && <p>{legal.accepted ? "ההסכמה לגרסה הנוכחית שמורה" : "נדרשת הסכמה לגרסה הנוכחית"} · {legal.version}</p>}
          <pre dir="rtl">{LEGAL_AGREEMENT_TEXT}</pre>
        </details>
        <UpdateControls theme={theme} />
        <footer>
          פותח ע״י א.מ.ד. | 2026 |{" "}
          <a href="mailto:em0548438097@gmail.com">em0548438097@gmail.com</a>
        </footer>
      </section>
    </div>
  );
}
