import { useCallback, useEffect, useState } from "react";
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
  ttl_hours: number | null;
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
  onConfirm: (values: MemoryEditorValues) => void;
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
  const submit = () => {
    if (!content.trim()) {
      setError("יש לכתוב מה סמארטי צריך לזכור.");
      return;
    }
    const ttlValues: Record<string, number | null> = {
      none: null,
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
    onConfirm({
      subject: subject.trim(),
      content: content.trim(),
      memory_type: memoryType,
      category,
      importance,
      ttl_hours: ttlHours ?? null,
      tags: tags
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      pinned,
    });
  };
  return (
    <div className="legacy-dialog-backdrop" role="presentation">
      <form
        className="legacy-input-dialog memory-editor-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <h2>{title}</h2>
        <label>
          מה סמארטי צריך לזכור?
          <textarea
            autoFocus
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        <label>
          קטגוריה
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            {memoryCategories.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="source-secondary-button"
          onClick={() => setAdvanced((value) => !value)}
        >
          {advanced ? "סגור אפשרויות נוספות" : "אפשרויות נוספות"}
        </button>
        {advanced && (
          <div className="memory-editor-advanced">
            <label>
              כותרת קצרה
              <input
                value={subject}
                placeholder="לא חובה"
                onChange={(event) => setSubject(event.target.value)}
              />
            </label>
            <div>
              <label>
                סוג זיכרון
                <select
                  value={memoryType}
                  onChange={(event) => setMemoryType(event.target.value)}
                >
                  {memoryTypes.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                חשיבות
                <select
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
                </select>
              </label>
            </div>
            <label>
              לכמה זמן לשמור?
              <select
                value={ttlPreset}
                onChange={(event) => setTtlPreset(event.target.value)}
              >
                <option value="none">ללא תפוגה</option>
                <option value="day">יום אחד</option>
                <option value="week">שבוע</option>
                <option value="month">30 יום</option>
                <option value="custom">תקופה אחרת…</option>
              </select>
            </label>
            {ttlPreset === "custom" && (
              <label>
                מספר שעות
                <input
                  type="number"
                  min="1"
                  value={customTtl}
                  onChange={(event) => setCustomTtl(event.target.value)}
                />
              </label>
            )}
            <label>
              תגיות
              <input
                value={tags}
                placeholder="למשל: פרויקט, כתיבה"
                onChange={(event) => setTags(event.target.value)}
              />
            </label>
            <label className="memory-editor-pin">
              <input
                type="checkbox"
                checked={pinned}
                onChange={(event) => setPinned(event.target.checked)}
              />
              הצג את הזיכרון בראש הרשימה
            </label>
          </div>
        )}
        {error && (
          <p className="management-notice" role="alert">
            {error}
          </p>
        )}
        <footer>
          <button type="button" onClick={onCancel}>
            ביטול
          </button>
          <button type="submit">שמירה</button>
        </footer>
      </form>
    </div>
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
  const [message, setMessage] = useState("");
  const load = useCallback(async () => {
    setData(
      await coreApi<Json>(
        "GET",
        `/v2/management/memories?query=${encodeURIComponent(query)}&status=${statusFilter}&memory_type=${type}&sensitivity=${sensitivity}&page=${page}&page_size=8`,
      ),
    );
  }, [query, statusFilter, type, sensitivity, page]);
  useEffect(() => {
    const timer = setTimeout(() => void load(), 220);
    return () => clearTimeout(timer);
  }, [load]);
  const act = async (id: unknown, action: string, extra: Json = {}) => {
    try {
      const result = await coreApi<Json>(
        action === "delete" ? "DELETE" : "PATCH",
        `/v2/management/memories/${encodePath(String(id))}`,
        { action, ...extra },
        true,
      );
      if (["details", "reveal"].includes(action)) setSelected(result);
      else await load();
      setMessage("הפעולה הושלמה.");
    } catch (reason) {
      setMessage(String(reason));
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
      setMessage("הפעולה הושלמה.");
    } catch (reason) {
      setMessage(String(reason));
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
      >
        <div className="memory-stats">
          <span>פעילים {Number(stats.active || 0)}</span>
          <span>ארכיון {Number(stats.archive || 0)}</span>
          <span>רגישים {Number(stats.sensitive || 0)}</span>
        </div>
      </PageHero>
      <div className="memory-toolbar">
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
          placeholder="חיפוש בזיכרון"
        />
        <select
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
        >
          <option value="active">פעילים</option>
          <option value="archive">ארכיון</option>
          <option value="all">הכול</option>
        </select>
        <select value={type} onChange={(event) => setType(event.target.value)}>
          <option value="any">כל הסוגים</option>
          <option value="user">פרטים והעדפות</option>
          <option value="long_term">ארוך טווח</option>
          <option value="short_term">קצר טווח</option>
          <option value="tool">תוצאות כלים</option>
        </select>
        <select
          value={sensitivity}
          onChange={(event) => setSensitivity(event.target.value)}
        >
          <option value="any">כל רמות הרגישות</option>
          <option value="ordinary">רגיל</option>
          <option value="sensitive">רגיש</option>
        </select>
      </div>
      <div className="inline-actions">
        <button onClick={() => setCreating(true)}>זיכרון חדש</button>
        <button onClick={() => setPathAction("import")}>ייבוא מוצפן</button>
        <button onClick={() => setPathAction("export")}>ייצוא מוצפן</button>
        {selectedIds.length > 0 && (
          <>
            <button
              onClick={() =>
                void collection({ action: "bulk_archive", ids: selectedIds })
              }
            >
              ארכוב נבחרים
            </button>
            <button
              onClick={() =>
                void collection({ action: "bulk_restore", ids: selectedIds })
              }
            >
              שחזור נבחרים
            </button>
            <button
              onClick={() =>
                void collection({ action: "bulk_delete", ids: selectedIds })
              }
            >
              מחיקת נבחרים
            </button>
          </>
        )}
        <button className="danger" onClick={() => setClearConfirm(true)}>
          ניקוי כל הזיכרונות
        </button>
      </div>
      <p role="status" className="settings-status">
        {message}
      </p>
      {selected && (
        <article className="memory-details">
          <button onClick={() => setSelected(null)}>×</button>
          <h3>{String(selected.subject || "פרטי זיכרון")}</h3>
          <p>{String(selected.masked_content || selected.content || "")}</p>
          <small>
            {String(selected.category || "")} · חשיבות{" "}
            {String(selected.importance || "")}
          </small>
          {selected.sensitivity === "sensitive" && !selected.content && (
            <button onClick={() => void act(selected.id, "reveal")}>
              חשיפה מפורשת
            </button>
          )}
        </article>
      )}
      <div className="management-cards compact">
        {items.map((item) => (
          <article key={String(item.id)}>
            <header>
              <label>
                <input
                  type="checkbox"
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
              </label>
              <span>
                {item.pinned ? "מוצמד" : String(item.sensitivity || "רגיל")}
              </span>
            </header>
            <p>{String(item.masked_content || item.content || "")}</p>
            <small>
              {String(item.type || "")} · {String(item.updated_at || "")}
            </small>
            <footer>
              <button onClick={() => void act(item.id, "details")}>
                פרטים
              </button>
              <button onClick={() => void beginEdit(item)}>
                {item.sensitivity === "sensitive" ? "חשיפה ועריכה" : "עריכה"}
              </button>
              <button
                onClick={() =>
                  void act(item.id, "pin", { pinned: !item.pinned })
                }
              >
                {item.pinned ? "בטל הצמדה" : "הצמד"}
              </button>
              <button
                onClick={() =>
                  void act(
                    item.id,
                    item.status === "archive" ? "restore" : "archive",
                  )
                }
              >
                {item.status === "archive" ? "שחזור" : "ארכוב"}
              </button>
              <button onClick={() => void act(item.id, "delete")}>מחיקה</button>
            </footer>
          </article>
        ))}
        {!items.length && (
          <p className="management-empty">לא נמצאו זיכרונות.</p>
        )}
      </div>
      <div className="pagination">
        <button
          disabled={page <= 1}
          onClick={() => setPage((value) => value - 1)}
        >
          הקודם
        </button>
        <span>
          עמוד {Number(data.page || page)} מתוך {Number(data.pages || 1)}
        </span>
        <button
          disabled={page >= Number(data.pages || 1)}
          onClick={() => setPage((value) => value + 1)}
        >
          הבא
        </button>
      </div>
      {creating && (
        <MemoryEditorDialog
          title="זיכרון חדש"
          onCancel={() => setCreating(false)}
          onConfirm={(values) => {
            void collection({ action: "create", ...values });
            setCreating(false);
          }}
        />
      )}
      {editing && (
        <MemoryEditorDialog
          title="עריכת זיכרון"
          entry={editing}
          onCancel={() => setEditing(null)}
          onConfirm={(values) => {
            void act(editing.id, "edit", values);
            setEditing(null);
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
            void collection({ action: pathAction, path });
            setPathAction(null);
          }}
        />
      )}
      {clearConfirm && (
        <InputDialog
          title="ניקוי כל הזיכרונות"
          label="כדי לאשר הקלד/י: מחק הכול"
          confirmLabel="מחיקה"
          onCancel={() => setClearConfirm(false)}
          onConfirm={(confirmation) => {
            if (confirmation === "מחק הכול")
              void collection({ action: "clear", confirmation });
            else setMessage("הטקסט לא תאם; דבר לא נמחק.");
            setClearConfirm(false);
          }}
        />
      )}
    </div>
  );
}
