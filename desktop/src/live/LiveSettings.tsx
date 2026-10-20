import { useEffect, useState } from "react";
import { ChoiceField, Field, IconButton, SettingRow, SettingsGroup } from "../design-system";
import { coreApi } from "../coreApi";
import { subscribeSettingsChanges } from "../settingsChanges";
import { useSecretAutosave } from "../useSecretAutosave";
import { readClipboardText } from "../clipboardText";
import type { LiveConfig } from "./useLiveConversation";

export function LiveSettings() {
  const [config, setConfig] = useState<LiveConfig | null>(null), [status, setStatus] = useState("");
  const load = async () => { setConfig(await coreApi<LiveConfig>("GET", "/v2/live/config")); };
  useEffect(() => { let mounted = true;
    const refresh = () => { void coreApi<LiveConfig>("GET", "/v2/live/config").then(value => { if (mounted) setConfig(value); }).catch(error => { if (mounted) setStatus(String(error)); }); };
    refresh(); const unsubscribe = subscribeSettingsChanges(refresh); return () => { mounted = false; unsubscribe(); };
  }, []);
  const provider = config?.provider || "", selected = config?.items?.find(item => item.id === provider);
  const key = `live_${provider}_api_key`;
  const secret = useSecretAutosave({ identity: key, delay: 900,
    persist: value => coreApi(value ? "PUT" : "DELETE", `/v2/settings/secrets/${key}`, value ? { value } : {}, true),
    onSaved: async () => { setStatus("מפתח הלייב נשמר. זמינות המודל תיבדק בפתיחת הלייב"); await load(); },
    onError: error => setStatus(`המפתח לא נשמר: ${String(error)}`),
  });
  const save = async (path: string, value: string) => {
    try { await coreApi("PATCH", "/v2/settings", { values: { [path]: value } }, true); await load(); setStatus(""); }
    catch (error) { setStatus(String(error)); }
  };
  return <SettingsGroup title="שיחת לייב" variant="plain">
    <SettingRow title="מודל לייב" description="שיחה קולית רציפה שמחוברת לסוכן ולכלים של סמארטי.">
      <ChoiceField label="מודל לייב" value={provider} options={[{ value: "", label: "ללא לייב" }, ...(config?.items || []).map(item => ({ value: item.id, label: item.label }))]} onValueChange={value => void save("live_provider", value)} />
    </SettingRow>
    {selected && <>
      <SettingRow title="מפתח API ללייב" description={selected.inherited ? "המפתח משותף אוטומטית עם מודלי הטקסט. הזנת מפתח כאן תיצור מפתח נפרד ללייב בלבד." : "מחיקת המפתח הנפרד תחזיר שימוש במפתח מודלי הטקסט, אם קיים."}>
        <div className="source-secret-input">
          <Field label="מפתח API ללייב" type="password" autoComplete="new-password" dir="ltr" value={secret.draft} placeholder={selected.masked || "הזן מפתח API"} onChange={event => { setStatus(""); secret.edit(event.target.value); }} onBlur={secret.flush} />
          <IconButton label="הדבקת מפתח לייב" icon="paste" variant="ghost" onClick={() => { void readClipboardText().then(value => secret.edit(value.trim())).catch(error => setStatus(String(error))); }} />
          <IconButton label="מחיקת מפתח לייב נפרד" icon="trash" variant="ghost" disabled={secret.busy || selected.inherited || !selected.configured} onClick={secret.remove} />
        </div>
      </SettingRow>
      <SettingRow title="קול הלייב" description={`${selected.model} · הבחירה תחול בפתיחת הלייב הבאה.`}>
        <ChoiceField label="קול הלייב" value={selected.voice} options={selected.voices.map(voice => ({ value: voice, label: voice }))} onValueChange={value => void save(`live_${provider}_voice`, value)} />
      </SettingRow>
    </>}
    {status && <p className="source-settings-hint" role="status">{status}</p>}
  </SettingsGroup>;
}
