import { Dialog, EmptyState, IconButton, LoadingState, SearchField, Switch } from "./design-system";
import { ManagementFeedback } from "./managementFeedback";
import { Textarea, SelectField, Button, Field, NumberField, Checkbox } from "./design-system";
import { useCallback, useEffect, useRef, useState } from "react";
import { coreApi, encodePath } from "./coreApi";
import { InputDialog, PageHero } from "./SettingsManagement";

type Json = Record<string, unknown>;
const asRows = (value: unknown): Json[] =>
  Array.isArray(value)
    ? value.filter((item): item is Json =>
        Boolean(item && typeof item === "object"),
      )
    : [];

type MemoryEditorValues = {
  subject: string;
  content: string;
  memory_type: string;
  category: string;
  importance: number;
  ttl_hours: number;
  tags: string[];
  pinned: boolean;
};

const memoryTypes = [
  ["user", "פרטים והעדפות שלי"],
  ["long_term", "זיכרון לטווח ארוך"],
  ["short_term", "הקשר משיחות אחרונות"],
  ["tool", "תוצאות מכלים"],
] as const;
const memoryCategories = [
  ["general", "כללי"],
  ["identity", "זהות"],
  ["preference", "העדפה"],
  ["project", "פרויקט"],
  ["address", "כתובת"],
  ["phone", "טלפון"],
  ["email", "דוא״ל"],
  ["health", "בריאות"],
  ["work", "עבודה"],
  ["family", "משפחה"],
  ["birthday", "יום הולדת"],
] as const;

function existingTtl(entry: Json): { preset: string; custom: string } {
  if (!entry.expires_at) return { preset: "none", custom: "" };
  const hours = Math.max(
    1,
    Math.round((Date.parse(String(entry.expires_at)) - Date.now()) / 3_600_000),
  );
  if (!Number.isFinite(hours)) return { preset: "none", custom: "" };
  if (Math.abs(hours - 24) <= 1) return { preset: "day", custom: "" };
  if (Math.abs(hours - 168) <= 1) return { preset: "week", custom: "" };
  if (Math.abs(hours - 720) <= 1) return { preset: "month", custom: "" };
  return { preset: "custom", custom: String(hours) };
}

function MemoryEditorDialog({
  title,
  entry = {},
  onCancel,
  onConfirm,
}: {
  title: string;
  entry?: Json;
  onCancel: () => void;
  onConfirm: (values: MemoryEditorValues) => Promise<boolean>;
}) {
  const ttl = existingTtl(entry);
  const [content, setContent] = useState(String(entry.content || ""));
  const [category, setCategory] = useState(String(entry.category || "general"));
  const [advanced, setAdvanced] = useState(false);
  const [subject, setSubject] = useState(String(entry.subject || ""));
  const [memoryType, setMemoryType] = useState(
    String(entry.type || "long_term"),
  );
  const [importance, setImportance] = useState(Number(entry.importance || 3));
  const [ttlPreset, setTtlPreset] = useState(ttl.preset);
  const [customTtl, setCustomTtl] = useState(ttl.custom);
  const [tags, setTags] = useState(
    Array.isArray(entry.tags) ? entry.tags.map(String).join(", ") : "",
  );
  const [pinned, setPinned] = useState(Boolean(entry.pinned));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const guard = useRef(false);
  const submit = async () => {
    if (guard.current) return;
    if (!content.trim()) {
      setError("יש לכתוב מה סמארטי צריך לזכור.");
      return;
    }
    const ttlValues: Record<string, number> = {
      none: 0,
      day: 24,
      week: 168,
      month: 720,
    };
    const ttlHours =
      ttlPreset === "custom" ? Number(customTtl) : ttlValues[ttlPreset];
    if (
      ttlPreset === "custom" &&
      (!Number.isFinite(ttlHours) || Number(ttlHours) <= 0)
    ) {
      setError("יש להזין מספר שעות חיובי, או לבחור תקופה מוכנה.");
      return;
    }
    guard.current = true; setBusy(true); setError("");
    try { const ok = await onConfirm({
      subject: subject.trim(),
      content: content.trim(),
      memory_type: memoryType,
      category,
      importance,
      ttl_hours: ttlHours ?? 0,
      tags: tags
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      pinned,
    }); if (!ok) setError("השמירה נכשלה. הפרטים נשמרו כאן; אפשר לתקן ולנסות שוב."); }
    catch (reason) { setError(`השמירה נכשלה: ${String(reason)}`); }
    finally { guard.current = false; setBusy(false); }
  };
  return (
    <Dialog open title={title} onClose={() => { if (!guard.current) onCancel(); }}>
      <form
        className="memory-editor-dialog"

        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div>
          מה סמארטי צריך לזכור?
          <Textarea label="מה סמארטי צריך לזכור?" hiddenLabel
            autoFocus
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </div>
        <div>
          קטגוריה
          <SelectField label="קטגוריה" hiddenLabel
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            {memoryCategories.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </SelectField>
        </div>
        <Button
          type="button"
          className="source-secondary-button"
          onClick={() => setAdvanced((value) => !value)}
        >
          {advanced ? "סגור אפשרויות נוספות" : "אפשרויות נוספות"}
        </Button>
        {advanced && (
          <div className="memory-editor-advanced">
            <div>
              כותרת קצרה
              <Field label="כותרת קצרה" hiddenLabel
                value={subject}
                placeholder="לא חובה"
                onChange={(event) => setSubject(event.target.value)}
              />
            </div>
            <div>
              <div>
                סוג זיכרון
                <SelectField label="סוג זיכרון" hiddenLabel
                  value={memoryType}
                  onChange={(event) => setMemoryType(event.target.value)}
                >
                  {memoryTypes.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </SelectField>
              </div>
              <div>
                חשיבות
                <SelectField label="חשיבות" hiddenLabel
                  value={importance}
                  onChange={(event) =>
                    setImportance(Number(event.target.value))
                  }
                >
                  {[1, 2, 3, 4, 5].map((value) => (
                    <option key={value} value={value}>
                      {value} מתוך 5
                    </option>
                  ))}
                </SelectField>
              </div>
            </div>
            <div>
              לכמה זמן לשמור?
              <SelectField label="לכמה זמן לשמור?" hiddenLabel
                value={ttlPreset}
                onChange={(event) => setTtlPreset(event.target.value)}
              >
                <option value="none">ללא תפוגה</option>
                <option value="day">יום אחד</option>
                <option value="week">שבוע</option>
                <option value="month">30 יום</option>
                <option value="custom">תקופה אחרת…</option>
              </SelectField>
            </div>
            {ttlPreset === "custom" && (
              <div>
                מספר שעות
                <NumberField label="מספר שעות" hiddenLabel

                  min="1"
                  value={customTtl}
                  onChange={(event) => setCustomTtl(event.target.value)}
                />
              </div>
            )}
            <div>
              תגיות
              <Field label="תגיות" hiddenLabel
                value={tags}
                placeholder="למשל: פרויקט, כתיבה"
                onChange={(event) => setTags(event.target.value)}
              />
            </div>
            <div className="memory-editor-pin">
              <Switch label="הצג את הזיכרון בראש הרשימה"

                checked={pinned}
                onCheckedChange={(checked) => setPinned(checked)}
              />
              הצג את הזיכרון בראש הרשימה
            </div>
          </div>
        )}
        <ManagementFeedback message={error} />
        <footer>
          <Button disabled={busy} onClick={onCancel}>ביטול</Button>
          <Button type="submit" variant="primary" loading={busy}>שמירה</Button>
        </footer>
      </form>
    </Dialog>
  );
}

export function MemoryView() {
  const [data, setData] = useState<Json>({
    items: [],
    page: 1,
    pages: 1,
    stats: {},
  });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [type, setType] = useState("any");
  const [sensitivity, setSensitivity] = useState("any");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Json | null>(null);
  const [editing, setEditing] = useState<Json | null>(null);
  const [creating, setCreating] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [pathAction, setPathAction] = useState<"import" | "export" | null>(
    null,
  );
  const [clearConfirm, setClearConfirm] = useState(false);
  const [message, setMessage] = useState(""), [loading, setLoading] = useState(true);
  const readGeneration = useRef(0);
  const load = useCallback(async () => {
    const generation = ++readGeneration.current; setLoading(true);
    try {
      const result = await coreApi<Json>("GET", `/v2/management/memories?query=${encodeURIComponent(query)}&status=${statusFilter}&memory_type=${type}&sensitivity=${sensitivity}&page=${page}&page_size=8`);
      if (generation === readGeneration.current) { setData(result); setMessage(""); }
    } catch (reason) { if (generation === readGeneration.current) setMessage(`טעינת הזיכרונות נכשלה: ${String(reason)}`); }
    finally { if (generation === readGeneration.current) setLoading(false); }
  }, [query, statusFilter, type, sensitivity, page]);
  useEffect(() => { const timer = setTimeout(() => void load(), 220); return () => { clearTimeout(timer); readGeneration.current++; }; }, [load]);
  const act = async (id: unknown, action: string, extra: Json = {}) => {
    try {
      const result = await coreApi<Json>(
        action === "delete" ? "DELETE" : "PATCH",
        `/v2/management/memories/${encodePath(String(id))}`,
        { action, ...extra },
        true,
      );
      if (["details", "reveal"].includes(action)) { setSelected(result); setMessage(""); }
      else await load();
      return true;
    } catch (reason) {
      setMessage(`הפעולה נכשלה: ${String(reason)}`); return false;
    }
  };
  const collection = async (payload: Json) => {
    try {
      const result = await coreApi<Json>(
        "POST",
        "/v2/management/memories",
        payload,
        true,
      );
      setData(result);
      setSelectedIds([]);
      setMessage(""); return true;
    } catch (reason) {
      setMessage(`הפעולה נכשלה: ${String(reason)}`); return false;
    }
  };
  const beginEdit = async (item: Json) => {
    if (item.sensitivity === "sensitive") {
      const revealed = await coreApi<Json>(
        "PATCH",
        `/v2/management/memories/${encodePath(String(item.id))}`,
        { action: "reveal" },
        true,
      );
      setEditing(revealed);
    } else {
      setEditing(item);
    }
  };
  const items = asRows(data.items);
  const stats = (
    data.stats && typeof data.stats === "object" ? data.stats : {}
  ) as Json;
  return (
    <div className="management-page">
      <PageHero
        title="ניהול זיכרון"
        description="תוכן רגיש נשאר מוצפן וממוסך עד לחשיפה מפורשת. אפשר ליצור, לסנן, לערוך, לארכב, לייבא ולייצא."
        actions={<><IconButton icon="refresh" label="רענון זיכרונות" disabled={loading} onClick={() => void load()} /><IconButton icon="trash" label="ניקוי כל הזיכרונות" variant="danger" onClick={() => setClearConfirm(true)} /></>}
      >
        <div className="memory-stats">
          <span>פעילים {Number(stats.active || 0)}</span>
          <span>ארכיון {Number(stats.archive || 0)}</span>
          <span>רגישים {Number(stats.sensitive || 0)}</span>
        </div>
      </PageHero>
      <div className="memory-toolbar">
        <SearchField label="חיפוש בזיכרונות" hiddenLabel
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
          placeholder="חיפוש בזיכרון"
        />
        <SelectField label="מצב הזיכרון" hiddenLabel
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
        >
          <option value="active">פעילים</option>
          <option value="archive">ארכיון</option>
          <option value="all">הכול</option>
        </SelectField>
        <SelectField label="סוג הזיכרון" hiddenLabel value={type} onChange={(event) => { setType(event.target.value); setPage(1); }}>
          <option value="any">כל הסוגים</option>
          <option value="user">פרטים והעדפות</option>
          <option value="long_term">ארוך טווח</option>
          <option value="short_term">קצר טווח</option>
          <option value="tool">תוצאות כלים</option>
        </SelectField>
        <SelectField label="רגישות" hiddenLabel
          value={sensitivity}
          onChange={(event) => { setSensitivity(event.target.value); setPage(1); }}
        >
          <option value="any">כל רמות הרגישות</option>
          <option value="ordinary">רגיל</option>
          <option value="sensitive">רגיש</option>
        </SelectField>
      </div>
      <div className="inline-actions">
        <Button type="button" icon="plus" variant="primary" onClick={() => setCreating(true)}>זיכרון חדש</Button>
        <Button type="button" icon="download" onClick={() => setPathAction("import")}>ייבוא מוצפן</Button>
        <Button type="button" icon="export" onClick={() => setPathAction("export")}>ייצוא מוצפן</Button>
        {selectedIds.length > 0 && (
          <>
            <Button type="button"
              onClick={() =>
                void collection({ action: "bulk_archive", ids: selectedIds })
              }
            >
              ארכוב נבחרים
            </Button>
            <Button type="button"
              onClick={() =>
                void collection({ action: "bulk_restore", ids: selectedIds })
              }
            >
              שחזור נבחרים
            </Button>
            <Button type="button"
              onClick={() =>
                void collection({ action: "bulk_delete", ids: selectedIds })
              }
            >
              מחיקת נבחרים
            </Button>
          </>
        )}

      </div>
      <ManagementFeedback message={message} />
      {selected && (
        <article className="memory-details">
          <IconButton icon="close" label="סגור פרטי זיכרון" type="button" onClick={() => setSelected(null)} />
          <h3>{String(selected.subject || "פרטי זיכרון")}</h3>
          <p>{String(selected.masked_content || selected.content || "")}</p>
          <small>
            {String(selected.category || "")} · חשיבות{" "}
            {String(selected.importance || "")}
          </small>
          {selected.sensitivity === "sensitive" && !selected.content && (
            <Button type="button" onClick={() => void act(selected.id, "reveal")}>
              חשיפה מפורשת
            </Button>
          )}
        </article>
      )}
      {loading && <LoadingState label="טוען זיכרונות…" />}
      <div className="management-cards compact">
        {items.map((item) => (
          <article key={String(item.id)}>
            <header>
              <div>
                <Checkbox label={`בחר זיכרון ${String(item.subject || "זיכרון")}`}

                  checked={selectedIds.includes(String(item.id))}
                  onChange={(event) =>
                    setSelectedIds((current) =>
                      event.target.checked
                        ? [...current, String(item.id)]
                        : current.filter((id) => id !== String(item.id)),
                    )
                  }
                />{" "}
                <b>{String(item.subject || "זיכרון")}</b>
              </div>
              <span>
                {item.pinned ? "מוצמד" : String(item.sensitivity || "רגיל")}
              </span>
            </header>
            <p>{String(item.masked_content || item.content || "")}</p>
            <small>
              {String(item.type || "")} · {String(item.updated_at || "")}
            </small>
            <footer>
              <IconButton icon="info" label="פרטים" type="button" onClick={() => void act(item.id, "details")} />
              <IconButton icon="rename" label={item.sensitivity === "sensitive" ? "חשיפה ועריכה" : "עריכה"} type="button" onClick={() => void beginEdit(item).catch(reason => setMessage(`טעינת הזיכרון נכשלה: ${String(reason)}`))} />
              <IconButton icon="pin" label={item.pinned ? "בטל הצמדה" : "הצמד"} type="button" onClick={() =>
                  void act(item.id, "pin", { pinned: !item.pinned })
                } />
              <IconButton icon={item.status === "archive" ? "history" : "archive"} label={item.status === "archive" ? "שחזור" : "ארכוב"} type="button" onClick={() =>
                  void act(
                    item.id,
                    item.status === "archive" ? "restore" : "archive",
                  )
                } />
              <IconButton icon="trash" label="מחיקה" type="button" onClick={() => void act(item.id, "delete")} />
            </footer>
          </article>
        ))}
        {!loading && !items.length && <EmptyState icon="memory" title="לא נמצאו זיכרונות" description="סמארטי שומר מידע שביקשת לזכור. אפשר להוסיף זיכרון או לשנות את המסננים." /> }
      </div>
      <div className="pagination">
        <Button type="button"
          disabled={page <= 1}
          onClick={() => setPage((value) => value - 1)}
        >
          הקודם
        </Button>
        <span>
          עמוד {Number(data.page || page)} מתוך {Number(data.pages || 1)}
        </span>
        <Button type="button"
          disabled={page >= Number(data.pages || 1)}
          onClick={() => setPage((value) => value + 1)}
        >
          הבא
        </Button>
      </div>
      {creating && (
        <MemoryEditorDialog
          title="זיכרון חדש"
          onCancel={() => setCreating(false)}
          onConfirm={(values) => {
            return collection({ action: "create", ...values }).then(ok => { if (ok) setCreating(false); return ok; });
          }}
        />
      )}
      {editing && (
        <MemoryEditorDialog
          title="עריכת זיכרון"
          entry={editing}
          onCancel={() => setEditing(null)}
          onConfirm={(values) => {
            return act(editing.id, "edit", values).then(ok => { if (ok) setEditing(null); return ok; });
          }}
        />
      )}
      {pathAction && (
        <InputDialog
          title={
            pathAction === "import"
              ? "ייבוא זיכרון מוצפן"
              : "ייצוא זיכרון מוצפן"
          }
          label="נתיב מלא לקובץ"
          multiline={false}
          confirmLabel={pathAction === "import" ? "ייבוא" : "ייצוא"}
          onCancel={() => setPathAction(null)}
          onConfirm={(path) => {
            return collection({ action: pathAction, path }).then(ok => { if (ok) setPathAction(null); return ok; });
          }}
        />
      )}
      {clearConfirm && (
        <InputDialog
          title="ניקוי כל הזיכרונות"
          label="כדי לאשר הקלד/י: מחק הכול"
          confirmLabel="מחיקה"
          onCancel={() => setClearConfirm(false)}
          onConfirm={async (confirmation) => {
            if (confirmation !== "מחק הכול") throw new Error("הטקסט לא תאם; יש להקליד: מחק הכול");
            const ok = await collection({ action: "clear", confirmation });
            if (ok) setClearConfirm(false);
            return ok;
          }}
        />
      )}
    </div>
  );
}
