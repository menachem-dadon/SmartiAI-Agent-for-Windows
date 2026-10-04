import { useEffect, useRef, useState } from "react";
import { parseThemePreference, resolveTheme, type ThemePreference } from "../designSystem";
import { Alert, Badge, Button, Card, ConfirmDialog, DesignSystemProvider, Dialog, EmptyState, Field, HoverLabel, Icon, IconButton, LoadingState, Menu, MessageFrame, NumberField, PageHeader, RangeField, SearchField, SettingRow, SettingsGroup, Switch, Tabs, Textarea, UserBubble, iconNames, palettes, type DesignTheme, type IconFamily } from "../design-system";
import "./gallery.css";

export function Gallery() {
  const params = new URLSearchParams(location.search);
  const [preference, setPreference] = useState<ThemePreference>(parseThemePreference(params.get("theme") || "light"));
  const [systemDark, setSystemDark] = useState(() => matchMedia("(prefers-color-scheme: dark)").matches);
  const [narrow, setNarrow] = useState(params.get("narrow") === "1");
  const [iconFamily, setIconFamily] = useState<IconFamily>(params.get("icons") === "original" ? "original" : "tabler");
  const [reduced, setReduced] = useState(false);
  const [dir, setDir] = useState<"rtl" | "ltr">("rtl");
  const [tab, setTab] = useState(params.get("tab") || "controls");
  useEffect(() => { const query = matchMedia("(prefers-color-scheme: dark)"); const update = () => setSystemDark(query.matches); query.addEventListener("change", update); return () => query.removeEventListener("change", update); }, []);
  const theme = resolveTheme(preference, systemDark);
  return <DesignSystemProvider theme={theme} iconFamily={iconFamily} reducedMotion={reduced} dir={dir} className="gallery-root">
    <div className="gallery-toolbar"><span className="gallery-brand"><Icon name="layers" size={24} /><strong>Smarti</strong><span>מערכת העיצוב</span></span><div className="sds-actions" aria-label="אפשרויות תצוגה">
      {([['light', 'בהיר', 'sun'], ['dark', 'כהה', 'moon'], ['system', 'מערכת', 'screen']] as const).map(([value, label, icon]) => <Button key={value} variant={preference === value ? "primary" : "ghost"} icon={icon} aria-pressed={preference === value} onClick={() => setPreference(value)}>{label}</Button>)}
      <Button icon="panel" aria-pressed={narrow} onClick={() => setNarrow(!narrow)}>חלון צר</Button><Button icon="activity" aria-pressed={reduced} onClick={() => setReduced(!reduced)}>צמצום תנועה</Button><Button onClick={() => setDir(dir === "rtl" ? "ltr" : "rtl")}>{dir === "rtl" ? "LTR" : "RTL"}</Button>
      <Button aria-pressed={iconFamily === "tabler"} onClick={() => setIconFamily("tabler")}>Tabler SVG</Button><Button aria-pressed={iconFamily === "original"} onClick={() => setIconFamily("original")}>האייקונים המקוריים</Button>
    </div></div>
    <main className="gallery-frame" data-narrow={narrow}>
      <PageHeader eyebrow="SMARTI · UX-2" title="אותה שפה, בכל פעולה" description="פקדים ברורים, משטחים שקטים ומקום לתוכן." actions={<Badge tone="accent">{theme === "light" ? "בהיר" : "כהה"}</Badge>} />
      <Tabs label="דוגמאות רכיבים" active={tab} onSelect={setTab} tabs={[
        { id: "controls", label: "רכיבים", icon: "settings", panel: <Controls /> },
        { id: "message", label: "שיחה ותוצרים", icon: "spark", panel: <MessageExamples /> },
        { id: "states", label: "מצבי מערכת", icon: "activity", panel: <States /> },
        { id: "tokens", label: "ערכים ואייקונים", icon: "layers", panel: <Tokens theme={theme} /> },
      ]} />
    </main>
  </DesignSystemProvider>;
}

function Controls() {
  const [enabled, setEnabled] = useState(true); const [range, setRange] = useState(40); const [number, setNumber] = useState("30");
  const [title, setTitle] = useState("סיכום לקראת המפגש"); const [draft, setDraft] = useState(title); const [rename, setRename] = useState(false);
  const [confirm, setConfirm] = useState(false); const [confirmError, setConfirmError] = useState<string>(); const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState(""); const [note, setNote] = useState(""); const [result, setResult] = useState("");
  const input = useRef<HTMLInputElement>(null); const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const wait = () => { setBusy(true); timer.current = setTimeout(() => setBusy(false), 1500); };
  return <div className="gallery-grid">
    <SettingsGroup title="פעולות" description="מידה טבעית לכפתור, יעד קבוע לפעולת אייקון.">
      <div className="gallery-stack">
        <div className="sds-actions"><Button variant="primary" icon="save" loading={busy} onClick={wait}>שמירה</Button><Button icon="rename" onClick={() => { setDraft(title); setRename(true); }}>שינוי שם</Button><Button variant="ghost" icon="refresh" onClick={() => setResult("הבדיקה הסתיימה. החיבור זמין.")}>בדיקת חיבור</Button></div>
        <div className="sds-actions"><IconButton variant="primary" icon="send" label="שליחה" round onClick={wait} /><IconButton icon="mic" label="הכתבה" variant="primary" round /><IconButton icon="stop" label="עצירה" variant="primary" round onClick={() => { clearTimeout(timer.current); setBusy(false); }} /><IconButton icon="copy" label="העתקה" /><IconButton icon="download" label="הורדה" /><IconButton icon="refresh" label="רענון" disabled /></div>
        <div className="sds-actions"><Button disabled icon="save">לא זמין</Button><Button loading>טעינה</Button><Menu label="פעולות המסמך" items={[{ id: "edit", label: "שינוי שם", icon: "rename", onSelect: () => { setDraft(title); setRename(true); } }, { id: "export", label: "ייצוא", icon: "export", disabled: true, onSelect: () => undefined }, { id: "remove", label: "מחיקה", icon: "trash", tone: "danger", onSelect: () => { setConfirmError(undefined); setConfirm(true); } }]} /></div>
        <p className="sds-hint" data-example-title>{title}</p>{result && <Alert title={result} />}
      </div>
    </SettingsGroup>
    <SettingsGroup title="כתיבה וחיפוש" description="תווית, הסבר ושגיאה נשארים צמודים לשדה."><div className="gallery-stack">
      <SearchField label="חיפוש" placeholder="שם, תוכן או פעולה" value={search} onChange={(event) => setSearch(event.currentTarget.value)} />
      <Field label="שם" placeholder="איך לקרוא לפריט?" hint="עברית, English ומספרים באותה שורה." />
      <Field label="כתובת השירות" dir="ltr" defaultValue="https://example.com" error="לא ניתן להתחבר. בדוק את הכתובת ונסה שוב." />
      <Field label="שדה מושבת" disabled defaultValue="אינו זמין כרגע" />
      <Textarea label="הערות" value={note} onChange={(event) => setNote(event.currentTarget.value)} placeholder="מקום לטקסט ארוך..." />
    </div></SettingsGroup>
    <SettingsGroup title="העדפות" description="כלים והגדרות חולקים את אותו מתג.">
      <SettingRow title="הפעלת הכלי" description="בחירה מפורשת, עם מיקוד מקלדת נראה."><Switch label="הפעלת הכלי" checked={enabled} onCheckedChange={setEnabled} /></SettingRow>
      <SettingRow title="אפשרות שאינה זמינה"><Switch label="אפשרות שאינה זמינה" checked={false} disabled onCheckedChange={() => undefined} /></SettingRow>
      <SettingRow title="זמן המתנה" description="מספר קצר, ביחידות שנקבעו בשדה."><NumberField label="שניות" value={number} min={0} onChange={(event) => setNumber(event.currentTarget.value)} /></SettingRow>
      <SettingRow title="עוצמה"><RangeField label="עוצמת הקראה" min={0} max={100} value={range} onValueChange={setRange} formatValue={(value) => `${value}%`} /></SettingRow>
    </SettingsGroup>
    <SettingsGroup title="רשימות והקשר" description="פעולות גלויות גם במקלדת ובמגע."><div className="gallery-stack">
      <Button className="gallery-long-label"><Icon name="file" /><HoverLabel text="סיכום ארוך לקראת המפגש — Research notes and next steps 2026" /></Button>
      <div className="sds-actions"><Badge>לא ידוע</Badge><Badge tone="success">מחובר</Badge><Badge tone="warning">ממתין לאישור</Badge><Badge tone="danger">נכשל</Badge></div>
      <Button variant="danger" icon="trash" onClick={() => { setConfirmError(undefined); setConfirm(true); }}>מחיקת פריט</Button>
      <p className="sds-hint">Tab למעבר בין פקדים. Escape לסגירה. חצים לתפריטים וללשוניות.</p>
    </div></SettingsGroup>
    <Dialog open={rename} title="שינוי שם" description="השם המלא נשאר קריא גם בחלון צר." onClose={() => setRename(false)} initialFocus={input}>
      <form onSubmit={(event) => { event.preventDefault(); if (draft.trim()) { setTitle(draft); setRename(false); } }}><Field ref={input} label="שם המסמך" value={draft} onChange={(event) => setDraft(event.currentTarget.value)} /><footer className="sds-actions"><Button onClick={() => setRename(false)}>ביטול</Button><Button type="submit" variant="primary" disabled={!draft.trim()}>שמירה</Button></footer></form>
    </Dialog>
    <ConfirmDialog open={confirm} title="מחיקת הפריט?" description="הפריט יוסר מהרשימה. בדוק שבחרת בפריט הרצוי." confirmLabel={confirmError ? "ניסיון חוזר" : "מחיקה"} error={confirmError} onClose={() => setConfirm(false)} onConfirm={() => { if (confirmError) { setConfirm(false); setConfirmError(undefined); } else setConfirmError("המחיקה נכשלה. הפריט נשאר ברשימה."); }} />
  </div>;
}

function MessageExamples() {
  const [documentOpen, setDocumentOpen] = useState(false); const [newBubble, setNewBubble] = useState(0);
  const [text, setText] = useState("Can we keep the document and next steps together?");
  return <Card className="gallery-reading"><div className="gallery-stack"><UserBubble>נרכז את התוכנית ואת הצעדים הבאים במקום אחד.</UserBubble><UserBubble key={newBubble} isNew={newBubble > 0}>{text}</UserBubble>
    <MessageFrame outputs={<><Button className="gallery-output" icon="file" onClick={() => setDocumentOpen(true)}><span><strong>סיכום המפגש.md</strong><small>מסמך · קריאה ועריכה</small></span><Icon name="forward" /></Button><Button className="gallery-output" icon="browser" onClick={() => setDocumentOpen(true)}><span><strong>מקורות להמשך</strong><small><bdi>example.com/research</bdi></small></span><Icon name="forward" /></Button></>} actions={<><IconButton icon="copy" label="העתקת התשובה" /><IconButton icon="speaker" label="הקראת התשובה" disabled /></>}>
      <p>הכנתי מסמך קצר שמחבר בין הרעיונות לבין הפעולות הבאות. אפשר לפתוח אותו לצד השיחה ולחזור לכאן להמשך.</p><p>לשמות מעורבים נשמר הכיוון: <bdi>C:\Projects\Research\notes-2026.md</bdi></p>
      <pre className="gallery-code" dir="ltr">{'const nextStep = "שיחה עם הצוות";\nconsole.log(nextStep);'}</pre>
    </MessageFrame>
    <Textarea label="כתיבת הודעה" value={text} onChange={(event) => setText(event.currentTarget.value)} /><div className="sds-actions"><Button icon="send" variant="primary" onClick={() => setNewBubble((value) => value + 1)}>הצגת הודעה חדשה</Button></div>
    </div><Dialog open={documentOpen} title="סיכום המפגש" onClose={() => setDocumentOpen(false)}><p>שלושה צעדים: להקשיב, לנסות בקבוצה קטנה ולשפר לפי המשוב.</p></Dialog></Card>;
}
function States() {
  const [error, setError] = useState(true);
  return <div className="gallery-grid"><SettingsGroup title="משוב ותוצאות"><div className="gallery-stack">
    {error && <Alert tone="danger" title="השמירה נכשלה" action={<Button onClick={() => setError(false)}>ניסיון חוזר</Button>}>הטקסט נשאר כאן. בדוק את החיבור ונסה שוב.</Alert>}
    <Alert tone="warning" title="נדרש אישור">בדוק את הפעולה ואת המשאב לפני ההמשך.</Alert><Alert tone="info" title="נתוני המכסה אינם זמינים">אפשר לבדוק שוב מאוחר יותר.</Alert><Alert tone="success" title="בדיקת החיבור הסתיימה">הספק זמין לפעולה.</Alert>
  </div></SettingsGroup><SettingsGroup title="טעינה"><LoadingState label="טוען פריטים" skeleton /></SettingsGroup><Card><EmptyState title="מקום לעבודה הבאה" description="פתח קובץ או בחר כלי כדי להתחיל." action={<Button icon="plus" onClick={() => setError(true)}>יצירת פריט</Button>} /></Card><SettingsGroup title="לא זמין"><EmptyState icon="plug" title="הספק מנותק" description="חבר ספק כדי להמשיך." action={<Button icon="plug">חיבור ספק</Button>} /></SettingsGroup></div>;
}
function Tokens({ theme }: { theme: DesignTheme }) {
  return <div className="gallery-stack"><SettingsGroup title="צבעים לפי תפקיד"><div className="gallery-swatches">{Object.entries(palettes[theme]).filter(([role]) => !["overlay", "shadowColor"].includes(role)).map(([role, color]) => <div key={role}><span style={{ background: color }} /><strong><bdi>{role}</bdi></strong><small><bdi>{color}</bdi></small></div>)}</div></SettingsGroup><SettingsGroup title="אייקונים"><div className="gallery-icons">{iconNames.map((name) => <div key={name}><Icon name={name} size={24} /><small><bdi>{name}</bdi></small></div>)}</div></SettingsGroup></div>;
}
