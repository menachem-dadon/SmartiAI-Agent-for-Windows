import { useEffect, useRef, useState } from "react";
import type { ManagementSection, SettingsSection } from "../managementCatalog";
import { MemoryView } from "../MemoryManagement";
import { LegalAgreement } from "../LegalAgreement";
import { AboutView, DiagnosticsView, LogsView, TasksView, ToolsView, UpdateControls, UsageView } from "../ManagementPages";
import type { ResolvedTheme, ThemePreference } from "../designSystem";
import { WorkspaceSurface } from "./WorkspaceSurface";
import { SettingsSurface } from "./SettingsSurface";
import { Icon, type IconName } from "./Icon";
import { Button } from "./Button";

const pages: Record<ManagementSection, { title: string; description: string; icon: IconName }> = {
  settings_ai: { title: "ספקים ומודלים", description: "חיבור הספקים, בחירת המודלים והאופן שבו סמארטי עובד איתך.", icon: "spark" },
  settings_security: { title: "הרשאות ופרטיות", description: "בחר מה סמארטי רשאי לעשות, מתי לבקש אישור ואיזה מידע לשתף.", icon: "shield" },
  settings_tools: { title: "כלים ותקשורת", description: "העדפות הכלים, חיבורי אימייל והתנהגות הפעולות בסביבת העבודה.", icon: "tools" },
  settings_appearance: { title: "קול, מראה ומערכת", description: "התאם את ההקראה, ההכתבה והמראה להרגלי העבודה שלך.", icon: "sun" },
  settings_advanced: { title: "הגדרות מתקדמות", description: "חיבורים מאובטחים, מגבלות עבודה ואפשרויות למפתחים.", icon: "settings" },
  tasks: { title: "משימות", description: "תכנון עבודה להמשך, מועדי הרצה ותוצאות. לכל משימה נשמרת השיחה שלה.", icon: "tasks" },
  memory: { title: "זיכרונות", description: "המידע שסמארטי שומר לשימוש חוזר. אפשר לבדוק, לערוך ולבחור מה להשאיר.", icon: "memory" },
  tools: { title: "כלים וחיבורים", description: "כלים מובנים, כלים אישיים, MCP ומיומנויות — עם שליטה בזמינות ובאמון.", icon: "tools" },
  usage: { title: "נתוני שימוש", description: "טוקנים ועלויות לפי תקופה ומודל. מידע חלקי ועלויות משוערות מסומנים במפורש.", icon: "usage" },
  workspace: { title: "סביבת העבודה", description: "העדפות חלון, קבצים ודפדפן. אפשר לפתוח את אזור העבודה מכאן.", icon: "panel" },
  diagnostics: { title: "אבחון", description: "בדיקת תקינות, הסבר לממצאים ופעולות תיקון לפי הצורך.", icon: "activity" },
  logs: { title: "לוגים ומעקב", description: "פרטי ריצות וכלים, חיפוש וייצוא. הגדרות תוכן אישי נשארות בשליטתך.", icon: "terminal" },
  about: { title: "אודות סמארטי", description: "גרסה, עדכונים, פרטיות ותנאי שימוש.", icon: "info" },
};
const navigation: { label: string; items: ManagementSection[] }[] = [
  { label: "העדפות", items: ["settings_ai", "settings_security", "settings_tools", "settings_appearance", "settings_advanced"] },
  { label: "ניהול העבודה", items: ["tasks", "memory", "tools", "usage", "workspace"] },
  { label: "מערכת", items: ["diagnostics", "logs", "about"] },
];

export function ProductManagement({ initial, theme, setTheme, openWorkbench }: { initial: ManagementSection; theme: ResolvedTheme; setTheme: (theme: ThemePreference) => void; openWorkbench: (tab: "browser" | "files") => void }) {
  const [section, setSection] = useState<ManagementSection>(initial);
  const [policyOpen, setPolicyOpen] = useState(false);
  const [legal, setLegal] = useState(false);
  const [createTask, setCreateTask] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => { const close = () => setLegal(false); window.addEventListener("ux1-demo-quit", close); return () => window.removeEventListener("ux1-demo-quit", close); }, []);
  useEffect(() => { setSection(initial); setPolicyOpen(false); setCreateTask(false); }, [initial]);
  useEffect(() => { if (createTask) body.current?.querySelector<HTMLTextAreaElement>(".task-create textarea")?.focus(); }, [createTask]);
  const navigate = (next: ManagementSection) => { setSection(next); setPolicyOpen(false); setLegal(false); setCreateTask(false); body.current?.scrollTo({ top: 0 }); };
  const page = pages[section];
  return <div className="ux-product-management">
    <nav aria-label="ניהול והגדרות"><div className="ux-management-nav-title"><Icon name="settings" /><strong>ניהול והגדרות</strong></div>{navigation.map(group => <div key={group.label}><h3>{group.label}</h3>{group.items.map(id => <button key={id} data-section={id} aria-current={section === id ? "page" : undefined} onClick={() => navigate(id)}><Icon name={pages[id].icon} />{pages[id].title}</button>)}</div>)}</nav>
    <div className="ux-management-body" ref={body} data-section={section} data-create-task={createTask}>
      <header className="ux-page-heading"><div><span className="ux-eyebrow">{section.startsWith("settings_") ? "העדפות" : "ניהול העבודה"}</span><h1>{page.title}</h1><p>{page.description}</p></div>{section === "tasks" && <Button className={createTask ? "" : "ux-primary"} icon={createTask ? "close" : "plus"} onClick={() => setCreateTask(!createTask)}>{createTask ? "סגירת יצירת משימה" : "משימה חדשה"}</Button>}</header>
      {legal && <div className="ux-legal-preview"><LegalAgreement theme={theme} status={{ accepted: false, version: "privacy-disclaimer-2026-06-02-v1", effective_date: "2026-06-02", title: "מדיניות פרטיות ותנאי שימוש" }} onAccepted={async () => { setLegal(false); }} /></div>}
      {section === "workspace" && <WorkspaceSurface onOpenWorkbench={openWorkbench} />}
      {section === "usage" && <UsageView />}
      {section === "tools" && <ToolsView theme={theme} />}
      {section === "memory" && <MemoryView />}
      {section === "tasks" && <TasksView />}
      {section === "diagnostics" && <DiagnosticsView />}
      {section === "logs" && <LogsView />}
      {section === "about" && <><AboutView theme={theme} /><Button icon="shield" onClick={() => setLegal(true)}>תצוגת מסך ההסכמה</Button></>}
      {section.startsWith("settings_") && <SettingsSurface section={section as SettingsSection} theme={theme} setTheme={setTheme} onNavigate={navigate} policyOpen={policyOpen} setPolicyOpen={setPolicyOpen} updateControls={<UpdateControls compact theme={theme} />} />}
    </div>
  </div>;
}
