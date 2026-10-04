import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { coreApi } from "../coreApi";
import { browserTargetCount } from "../browserState";
import { Button } from "./Button";
import { Icon } from "./Icon";

type Json = Record<string, unknown>;

// UX-1 composition of WorkspaceView. Keep its Core preference paths, browser
// ownership and action callbacks; all commands still terminate in DemoBackend.
export function WorkspaceSurface({ onOpenWorkbench }: { onOpenWorkbench: (tab: "browser" | "files") => void }) {
  const [root, setRoot] = useState<Json>({});
  const [browser, setBrowser] = useState<Json>({});
  const [settings, setSettings] = useState<Json>({});
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const [info, safe] = await Promise.all([coreApi<Json>("GET", "/v2/workbench/root"), coreApi<{ values: Json }>("GET", "/v2/settings")]);
      setRoot(info); setSettings(safe.values); setError("");
      try { const snapshot = await invoke<unknown>("browser_status"); setBrowser(snapshot && typeof snapshot === "object" && !Array.isArray(snapshot) ? snapshot as Json : {}); }
      catch { setBrowser({}); }
    } catch { setError("לא ניתן לטעון את העדפות סביבת העבודה. אפשר לנסות לרענן."); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const prefs = settings.ui_preferences && typeof settings.ui_preferences === "object" ? settings.ui_preferences as Json : {};
  async function savePrefs(patch: Json) {
    const next = { ...prefs, ...patch };
    try { await coreApi("PATCH", "/v2/settings", { values: { ui_preferences: next } }, true); setSettings(current => ({ ...current, ui_preferences: next })); setError(""); }
    catch { setError("שינוי ההעדפות נכשל. אפשר לנסות שוב."); }
  }
  const path = String((root.root as Json)?.path || root.path || "");
  const browserPath = String(browser.profile_dir || path);
  const targetCount = browserTargetCount(browser);
  return <div className="ux-workspace-settings">
    <div className="ux-workspace-settings-toolbar"><Button icon="refresh" label="רענן" onClick={() => void load()} /></div>
    <section className="ux-settings-group"><header><h3>פתיחה וסרגל צד</h3><p>התאם את סביבת העבודה להרגלי השימוש שלך.</p></header>
      {[{ key: "workspace_start_maximized", title: "פתיחה בחלון מוגדל", detail: "מנצל את שטח העבודה של Windows.", checked: prefs.workspace_start_maximized !== false, invert: false }, { key: "workspace_sidebar_collapsed", title: "סרגל השיחות פתוח בכניסה", detail: "מציג את היסטוריית השיחות המלאה בפתיחה.", checked: !Boolean(prefs.workspace_sidebar_collapsed), invert: true }].map(item => <label key={item.key} className="ux-workspace-setting-row"><span><strong>{item.title}</strong><small>{item.detail}</small></span><span className="source-switch"><input aria-label={item.title} type="checkbox" checked={item.checked} onChange={event => void savePrefs({ [item.key]: item.invert ? !event.target.checked : event.target.checked })} /><span /></span></label>)}
    </section>
    <section className="ux-settings-group"><header><h3><Icon name="folder" />קבצים וסביבת העבודה</h3><p>גישה לקבצים ולתוכן שעליו עובדים.</p></header><div className="ux-workspace-setting-content"><span className="ux-eyebrow">תיקיית עבודה</span><bdi className="ux-workspace-path">{path}</bdi><div className="ux-action-row"><Button icon="folder" onClick={() => onOpenWorkbench("files")}>פתח קבצים</Button><Button icon="browser" onClick={() => onOpenWorkbench("browser")}>פתח דפדפן</Button></div></div></section>
    <section className="ux-settings-group"><header><h3><Icon name="browser" />Smarti Browser</h3><p>{browser.available === false ? "WebView2 אינו זמין כרגע." : targetCount === null ? "מספר יעדי הדפדפן אינו זמין כרגע. אפשר לנסות לרענן." : `יעדי דפדפן פעילים: ${targetCount}`}</p></header><div className="ux-workspace-setting-content ux-action-row"><Button icon="browser" onClick={() => onOpenWorkbench("browser")}>פתח את Smarti Browser</Button><Button icon="paste" onClick={() => onOpenWorkbench("browser")}>ייבוא מדפדפן קיים</Button><Button icon="folder" disabled={!browserPath} onClick={() => void invoke("open_chat_link", { target: browserPath, local: true }).catch(() => setError("פתיחת תיקיית הנתונים נכשלה."))}>פתח תיקיית נתונים</Button></div></section>
    {error && <p role="alert" className="ux-error">{error}</p>}
  </div>;
}
