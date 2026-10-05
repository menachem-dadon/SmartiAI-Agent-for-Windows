import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { coreApi } from "./coreApi";
import { browserTargetCount } from "./browserState";
import { Alert, Button, IconButton, PageHeader, SettingRow, SettingsGroup, Switch } from "./design-system";

type Json = Record<string, unknown>;
export function WorkspaceView({ onOpenWorkbench }: { onOpenWorkbench?: (tab: "browser" | "files") => void }) {
  const [root, setRoot] = useState<Json>({}), [browser, setBrowser] = useState<Json>({});
  const [prefs, setPrefs] = useState<Json>({}), [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const guard = useRef(false);
  const load = useCallback(async () => {
    try {
      const [rootInfo, safe] = await Promise.all([coreApi<Json>("GET", "/v2/workbench/root"), coreApi<{ values: Json }>("GET", "/v2/settings")]);
      setRoot(rootInfo); setPrefs((safe.values.ui_preferences as Json) || {}); setError("");
      try { const value = await invoke<unknown>("browser_status"); setBrowser(value && typeof value === "object" && !Array.isArray(value) ? value as Json : {}); }
      catch { setBrowser({}); }
    } catch (reason) { setError(String(reason)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const save = async (patch: Json) => {
    if (guard.current) return; guard.current = true; setBusy(true);
    try {
      // Core merges the patch: unrelated preferences cannot be overwritten by a
      // stale screen snapshot or concurrent shell update.
      const result = await coreApi<{ values: Json }>("PATCH", "/v2/settings", { values: { ui_preferences: patch } }, true);
      setPrefs((result.values.ui_preferences as Json) || { ...prefs, ...patch }); setError("");
    } catch (reason) { setError(String(reason)); }
    finally { guard.current = false; setBusy(false); }
  };
  const browserPath = String(browser.profile_dir || (root.root as Json)?.path || root.path || "");
  const count = browserTargetCount(browser);
  return <div className="workspace-preferences">
    <PageHeader title="סביבת עבודה ודפדפן" description="כלים לצד השיחה, עם ההעדפות והקבצים שלך." actions={<IconButton icon="refresh" label="רענן" disabled={busy} onClick={() => void load()} />} />
    {error && <Alert title="לא ניתן לעדכן את סביבת העבודה" tone="danger">{error}</Alert>}
    <SettingsGroup title="פתיחה וסרגל צד" description="גודל החלון ומיקומו נשמרים אוטומטית. אפשר להגדיל אותו מכפתור ההגדלה בכותרת.">
      <SettingRow title="סרגל השיחות פתוח בכניסה" description="מציג את רשימת השיחות המלאה במקום מצב אייקונים."><Switch label="סרגל השיחות פתוח בכניסה" disabled={busy} checked={!Boolean(prefs.workspace_sidebar_collapsed)} onCheckedChange={value => void save({ workspace_sidebar_collapsed: !value })} /></SettingRow>
    </SettingsGroup>
    <SettingsGroup title="קבצי העבודה" description="כאן נשמרים הקבצים והתוצרים של סמארטי.">
      <div className="workspace-folder-row"><div>
        <p className="workspace-folder-path"><bdi dir="ltr">{String((root.root as Json)?.path || root.path || "")}</bdi></p>
        <p className="sds-hint">הלשוניות נשמרות בזמן העבודה; בהפעלה חדשה מתחילים בלי לשוניות פתוחות.</p>
      </div><Button icon="folder" onClick={() => onOpenWorkbench?.("files")}>פתח קבצים</Button></div>
    </SettingsGroup>
    <SettingsGroup title="Smarti Browser" description={browser.available === false ? "WebView2 אינו זמין כרגע." : count === null ? "מספר יעדי הדפדפן אינו זמין כרגע. אפשר לנסות לרענן." : `יעדי דפדפן פעילים: ${count}`}>
      <div className="workspace-preferences-actions"><Button icon="browser" onClick={() => onOpenWorkbench?.("browser")}>פתח דפדפן</Button>
        <Button icon="download" onClick={() => onOpenWorkbench?.("browser")}>ייבוא מדפדפן קיים</Button>
        <Button icon="folder" disabled={!browserPath} onClick={() => void invoke("open_chat_link", { target: browserPath, local: true }).catch(reason => setError(String(reason)))}>פתח תיקיית נתונים</Button></div>
      <p className="sds-hint">ייבוא זמין בתפריט הדפדפן, עם בחירת מקור מפורשת.</p>
    </SettingsGroup>
  </div>;
}
