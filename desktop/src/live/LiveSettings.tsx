import { useEffect, useState } from "react";
import { ChoiceField, Field, IconButton, SettingRow, SettingsGroup, Switch } from "../design-system";
import { coreApi } from "../coreApi";
import { subscribeSettingsChanges } from "../settingsChanges";
import { useSecretAutosave } from "../useSecretAutosave";
import { readClipboardText } from "../clipboardText";
import type { LiveConfig } from "./useLiveConversation";

export function LiveSettings() {
  const [config, setConfig] = useState<LiveConfig | null>(null), [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const load = async () => { setConfig(await coreApi<LiveConfig>("GET", "/v2/live/config")); };
  useEffect(() => { let mounted = true;
    const refresh = () => { void coreApi<LiveConfig>("GET", "/v2/live/config").then(value => { if (mounted) setConfig(value); }).catch(error => { if (mounted) setStatus(String(error)); }); };
    refresh(); const unsubscribe = subscribeSettingsChanges(refresh); return () => { mounted = false; unsubscribe(); };
  }, []);
  const provider = config?.provider || "", selected = config?.items?.find(item => item.id === provider);
  const disabled = !config?.enabled || saving;
  const key = `live_${provider}_api_key`;
  const secret = useSecretAutosave({ identity: key, delay: 900,
    persist: value => coreApi(value ? "PUT" : "DELETE", `/v2/settings/secrets/${key}`, value ? { value } : {}, true),
    onSaved: async () => { setStatus("מפתח הלייב נשמר. זמינות המודל תיבדק בפתיחת הלייב"); await load(); },
    onError: error => setStatus(`המפתח לא נשמר: ${String(error)}`),
  });
  const save = async (path: string, value: string | boolean) => {
    const confirmed = config;
    if (path === "live_enabled") setConfig(current => current ? { ...current, enabled: Boolean(value) } : current);
    setSaving(true);
    try { await coreApi("PATCH", "/v2/settings", { values: { [path]: value } }, true); await load(); setStatus(""); }
    catch (error) { setConfig(confirmed); setStatus(String(error)); }
    finally { setSaving(false); }
  };
  return <SettingsGroup title="מצב Live" hideHeader>
    <div className="live-settings">
      <SettingRow title="אפשר מצב Live" description="שיחה קולית רציפה שמחוברת לסוכן ולכלים של סמארטי.">
        <Switch label="אפשר מצב Live" checked={Boolean(config?.enabled)} disabled={!config || saving} onCheckedChange={value => void save("live_enabled", value)} />
      </SettingRow>
      <div className="source-settings-field"><SettingRow title="מודל לייב">
        <div className="source-settings-control"><ChoiceField label="מודל לייב" hiddenLabel disabled={disabled} value={provider} options={[{ value: "", label: "בחר ספק לייב" }, ...(config?.items || []).map(item => ({ value: item.id, label: item.label }))]} onValueChange={value => void save("live_provider", value)} /></div>
      </SettingRow></div>
      <div className="source-settings-field"><SettingRow title="שפת הלייב" description="העדפת השפה לדיבור ולזיהוי. תחול בפתיחת הלייב הבאה; זיהוי השפה עדיין תלוי בספק.">
        <div className="source-settings-control"><ChoiceField label="שפת הלייב" hiddenLabel disabled={disabled} value={config?.language || "he"} options={[{ value: "he", label: "עברית" }, { value: "en", label: "אנגלית" }, { value: "auto", label: "זיהוי אוטומטי" }]} onValueChange={value => void save("live_language", value)} /></div>
      </SettingRow></div>
    {selected && <>
      <div className="source-key-setting"><section className="source-settings-field provider-secret-field" data-setting-path="live_api_key">
        <SettingRow title="מפתח API ללייב" description={selected.inherited ? "המפתח משותף אוטומטית עם מודלי הטקסט. הזנת מפתח כאן תיצור מפתח נפרד ללייב בלבד." : "מחיקת המפתח הנפרד תחזיר שימוש במפתח מודלי הטקסט, אם קיים."}>
          <div className="source-settings-control"><div className="secret-link-row secret-link-row--stacked">
            <Field label="מפתח API ללייב" hiddenLabel fitContent disabled={disabled} type="password" autoComplete="new-password" dir="ltr" value={secret.draft} placeholder={selected.masked || "הדבקת מפתח API"} onChange={event => { setStatus(""); secret.edit(event.target.value); }} onBlur={secret.flush} aria-busy={secret.busy || undefined}
              inputAction={<IconButton label="הדבקת מפתח לייב" icon="paste" variant="ghost" disabled={disabled} onClick={() => { void readClipboardText().then(value => { if (value.trim()) secret.edit(value.trim()); }).catch(error => setStatus(String(error))); }} />} />
            <IconButton label="מחיקת מפתח לייב נפרד" icon="trash" variant="danger" disabled={disabled || secret.busy || (!secret.draft && (selected.inherited || !selected.configured))} onClick={secret.remove} />
          </div></div>
        </SettingRow>
      </section></div>
      <div className="source-settings-field"><SettingRow title="קול הלייב" description={`${selected.model} · הבחירה תחול בפתיחת הלייב הבאה.`}>
        <div className="source-settings-control"><ChoiceField label="קול הלייב" hiddenLabel disabled={disabled} value={selected.voice} options={selected.voices.map(voice => ({ value: voice, label: voice }))} onValueChange={value => void save(`live_${provider}_voice`, value)} /></div>
      </SettingRow></div>
    </>}
    {status && <p className="source-settings-hint" role="status">{status}</p>}
    </div>
  </SettingsGroup>;
}
