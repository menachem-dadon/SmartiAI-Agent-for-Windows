export type CoreState = "starting" | "connecting" | "ready" | "crashed" | "fatal" | "repair" | "stopped";

export interface CoreSnapshot {
  state: CoreState;
  generation: number;
  pid: number | null;
  port: number | null;
  startedAt: string | null;
  lastError: string | null;
  stderrTail: string[];
}

const copy: Record<CoreState, { title: string; description: string; status: string }> = {
  starting: { title: "Smarti מתעוררת", description: "מכינים עבורך סביבת עבודה פרטית ומאובטחת.", status: "מפעיל את Smarti Core" },
  connecting: { title: "כמעט מוכנים", description: "נוצר חיבור מקומי מאובטח בין הממשק לבין ה־Core.", status: "מתחבר" },
  ready: { title: "Smarti מוכנה", description: "מעטפת שולחן העבודה מחוברת ל־Core ופועלת כתהליך אחד.", status: "מוכן" },
  crashed: { title: "ה־Core נעצר", description: "הממשק נשאר פתוח ואפשר להפעיל את Smarti Core מחדש בבטחה.", status: "נדרש שחזור" },
  fatal: { title: "לא הצלחנו להתחבר", description: "Smarti שמרה את פרטי התקלה כדי לעזור באבחון ובתיקון.", status: "שגיאת הפעלה" },
  repair: { title: "נדרשת התקנת תיקון", description: "רכיב ה־Core חסר או אינו תואם לגרסת הממשק.", status: "נדרש תיקון" },
  stopped: { title: "Smarti עצרה", description: "אפשר להפעיל מחדש את ה־Core בלי לסגור את החלון.", status: "מושהה" },
};

export function copyForState(state: CoreState, error: string | null) {
  const value = copy[state];
  return error && state !== "ready" ? { ...value, description: `${value.description} (${error})` } : value;
}
