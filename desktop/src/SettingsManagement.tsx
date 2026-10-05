import { Dialog, IconButton, Popover, PageHeader, SegmentedControl, SettingRow as SharedSettingRow, SettingsGroup, Switch, RangeField, LoadingState } from "./design-system";
import { ManagementFeedback } from "./managementFeedback";
import { ProviderPicker } from "./ProviderPicker";
import { Button, Textarea, Field, Icon, SelectField, SearchField } from "./design-system";
import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import { coreApi, encodePath } from "./coreApi";
import { useSpeechPlayback } from "./speechPlayback";
import type { ResolvedTheme, ThemePreference } from "./designSystem";


import {
  capabilityLabels,
  matchingSettings,
  patchForSetting,
  policyOptions,
  providerSecretKeys,
  readSetting,
  settingsSectionTitles,
  type SettingDefinition,
  type SettingsSection,
} from "./managementCatalog";

type Json = Record<string, unknown>;
type SecretState = Record<string, { configured: boolean; masked: string }>;
type SafeSettings = { values: Json; secrets: SecretState };
export type ProviderMetadata = {
  id: string;
  label: string;
  secret_key: string;
  help_url: string;
  key_instructions: string;
  requires_api_key: boolean;
};
type SettingsSchema = {
  providers: ProviderMetadata[];
  secret_help: Record<
    string,
    { label: string; help_url: string; key_instructions: string }
  >;
};
type CoreRequest = <T>(
  method: string,
  path: string,
  body?: unknown,
  idempotent?: boolean,
) => Promise<T>;
const asRows = (value: unknown): Json[] =>
  Array.isArray(value)
    ? value.filter((item): item is Json =>
        Boolean(item && typeof item === "object"),
      )
    : [];

export async function validateProviderKey({
  provider,
  secret,
  localUrl,
  request = coreApi,
}: {
  provider: string;
  secret: string;
  localUrl?: unknown;
  request?: CoreRequest;
}) {
  const normalized = secret.trim();
  if (!provider || !normalized) throw new Error("לא הוזן מפתח API");
  const result = await request<{
    ok: boolean;
    message: string;
    models: string[];
  }>(
    "POST",
    `/v2/providers/${encodePath(provider)}/validate`,
    { secret: normalized, local_url: localUrl },
    true,
  );
  if (!result.ok) throw new Error(result.message || "בדיקת תקינות נכשלה");
  return result;
}

export async function validateAndPersistProviderKey({
  provider,
  secretKey,
  secret,
  localUrl,
  request = coreApi,
}: {
  provider: string;
  secretKey: string;
  secret: string;
  localUrl?: unknown;
  request?: CoreRequest;
}) {
  const normalized = secret.trim();
  if (!secretKey) throw new Error("לא נמצא יעד מאובטח למפתח");
  const result = await validateProviderKey({
    provider,
    secret: normalized,
    localUrl,
    request,
  });
  await request(
    "PUT",
    `/v2/settings/secrets/${encodePath(secretKey)}`,
    { value: normalized },
    true,
  );
  return result;
}

function SourceSettingField({ label, help, children, className = "", dataPath }: {
  label: string; help: string; children: React.ReactNode; className?: string;
  dataPath?: string; advanced?: boolean; info?: boolean;
}) {
  return <section className={`source-settings-field ${className}`} data-setting-path={dataPath}>
    <SharedSettingRow title={label} description={help}><div className="source-settings-control">{children}</div></SharedSettingRow>
  </section>;
}

export function ConfirmDialog({ title, description, confirmLabel = "אישור מפורש", danger = false, onCancel, onConfirm }: {
  title: string; description: string; confirmLabel?: string; danger?: boolean;
  onCancel: () => void; onConfirm: () => void | Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const guard = useRef(false), cancel = useRef<HTMLButtonElement>(null);
  const confirm = async () => {
    if (guard.current) return; guard.current = true; setBusy(true); setError("");
    try { if (await onConfirm() === false) setError("הפעולה נכשלה. אפשר לנסות שוב."); } catch (reason) { setError(`הפעולה נכשלה: ${String(reason)}`); }
    finally { guard.current = false; setBusy(false); }
  };
  return <Dialog open title={title} description={description} role="alertdialog" initialFocus={cancel} onClose={() => { if (!guard.current) onCancel(); }}>
    <ManagementFeedback message={error} />
    <footer className="sds-actions"><Button ref={cancel} disabled={busy} onClick={onCancel}>ביטול</Button>
      <Button variant={danger ? "danger" : "primary"} loading={busy} onClick={() => void confirm()}>{confirmLabel}</Button></footer>
  </Dialog>;
}

export function InputDialog({ title, label, initial = "", confirmLabel = "שמירה", multiline = true, onCancel, onConfirm }: {
  title: string; label: string; initial?: string; confirmLabel?: string; multiline?: boolean;
  onCancel: () => void; onConfirm: (value: string) => void | Promise<unknown>;
}) {
  const [value, setValue] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const guard = useRef(false);
  const submit = async () => {
    if (guard.current || !value.trim()) return; guard.current = true; setBusy(true); setError("");
    try { if (await onConfirm(value.trim()) === false) setError("הפעולה נכשלה. הפרטים נשמרו כאן; אפשר לנסות שוב."); } catch (reason) { setError(`הפעולה נכשלה: ${String(reason)}`); }
    finally { guard.current = false; setBusy(false); }
  };
  return <Dialog open title={title} onClose={() => { if (!guard.current) onCancel(); }}>
    <form onSubmit={event => { event.preventDefault(); void submit(); }}>
      {multiline ? <Textarea label={label} autoFocus value={value} disabled={busy} onChange={event => setValue(event.target.value)} />
        : <Field label={label} autoFocus dir="auto" value={value} disabled={busy} onChange={event => setValue(event.target.value)} />}
      <ManagementFeedback message={error} />
      <footer className="sds-actions"><Button disabled={busy} onClick={onCancel}>ביטול</Button>
        <Button type="submit" variant="primary" loading={busy} disabled={!value.trim()}>{confirmLabel}</Button></footer>
    </form>
  </Dialog>;
}

export function PageHero({ title, description, actions, children }: {
  title: string; description: string; actions?: React.ReactNode; children?: React.ReactNode;
}) {
  return <><PageHeader title={title} description={description} actions={actions} />{children}</>;
}

function SettingRow({
  definition,
  values,
  secrets,
  onSave,
  onSecretChanged,
  schema,
  theme: _theme,
}: {
  definition: SettingDefinition;
  values: Json;
  secrets: SecretState;
  onSave: (path: string, value: unknown) => Promise<void>;
  onSecretChanged: () => Promise<void>;
  schema: SettingsSchema;
  theme: ResolvedTheme;
}) {
  const raw = readSetting(values, definition.path);
  const displayed =
    definition.path === "max_agent_loops" && Number(raw) <= 0
      ? 31
      : definition.path === "background_recurring_catch_up_window_minutes" &&
          Number(raw) < 0
        ? 181
        : Array.isArray(raw)
          ? raw.join("; ")
          : (raw ?? "");
  const [draft, setDraft] = useState(String(displayed));
  const [secret, setSecret] = useState("");
  const [status, setStatus] = useState("");
  const saveTimer = useRef<number | null>(null);
  const controlDisabled =
    definition.path === "enable_canvas_remote_images" &&
    !Boolean(values.enable_web_canvas);
  const sourceProps = {
    label: definition.label,
    help: definition.help,
    dataPath: definition.path,
    advanced: Boolean(definition.advanced),
    info: definition.info,
  };
  useEffect(() => setDraft(String(displayed)), [displayed]);
  useEffect(
    () => () => {
      if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    },
    [],
  );
  const saveDraft = async (supplied?: string) => {
    const text = supplied ?? draft;
    let value: unknown = text;
    if (definition.control === "number" || definition.control === "range")
      value = Number(text);
    if (definition.path === "max_agent_loops" && Number(value) >= 31) value = 0;
    if (
      definition.path === "background_recurring_catch_up_window_minutes" &&
      Number(value) >= 181
    )
      value = -1;
    if (definition.path === "mcp_allowed_directories")
      value = text
        .split(";")
        .map((item) => item.trim())
        .filter(Boolean);
    setStatus("");
    try {
      await onSave(definition.path, value);
      setStatus("");
    } catch (reason) {
      setStatus(`השמירה נכשלה: ${String(reason)}`);
    }
  };
  const queueSave = (next: string) => {
    setDraft(next);
    if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      saveTimer.current = null;
      void saveDraft(next);
    }, 350);
  };
  const choosePath = async () => {
    try {
      const selected = await invoke<string | null>("pick_management_path", {
        kind: definition.control === "directory" ? "directory" : "file",
      });
      if (selected) {
        if (definition.multiple) {
          const next = [
            ...new Set([
              ...(Array.isArray(raw) ? raw.map(String) : []),
              selected,
            ]),
          ];
          setDraft(next.join("; "));
          setStatus("");
          await onSave(definition.path, next);
          setStatus("");
        } else {
          setDraft(selected);
          await saveDraft(selected);
        }
      }
    } catch (reason) {
      setStatus(`הבחירה נכשלה: ${String(reason)}`);
    }
  };
  if (definition.control === "secret") {
    const state = secrets[definition.path] || { configured: false, masked: "" };
    const help = schema.secret_help[definition.path];
    const persistSecret = async (next: string) => {
      setStatus("");
      try {
        if (next.trim())
          await coreApi(
            "PUT",
            `/v2/settings/secrets/${encodePath(definition.path)}`,
            { value: next.trim() },
            true,
          );
        else if (state.configured)
          await coreApi(
            "DELETE",
            `/v2/settings/secrets/${encodePath(definition.path)}`,
            {},
            true,
          );
        setSecret("");
        setStatus("");
        await onSecretChanged();
      } catch (reason) {
        setStatus(`השמירה נכשלה: ${String(reason)}`);
      }
    };
    const editSecret = (next: string) => {
      setSecret(next);
      setStatus("");
      if (saveTimer.current !== null) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => {
        saveTimer.current = null;
        void persistSecret(next);
      }, 350);
    };
    const paste = async () => {
      try {
        const value = (await navigator.clipboard.readText()).trim();
        if (!value) {
          setStatus("לוח ההעתקה אינו מכיל טקסט.");
          return;
        }
        editSecret(value);
      } catch (reason) {
        setStatus(`ההדבקה נכשלה: ${String(reason)}`);
      }
    };
    return (
      <SourceSettingField {...sourceProps} className="secret-field">
        <div className="secret-link-row">
          <Field label={definition.label} hiddenLabel
            type={definition.path === "email_address" ? "email" : "password"}
            dir="ltr"
            autoComplete="new-password"
            value={secret}
            onChange={(event) => editSecret(event.target.value)}
            onBlur={() => {
              if (saveTimer.current !== null) { window.clearTimeout(saveTimer.current); saveTimer.current = null; void persistSecret(secret); }
            }}
            placeholder={
              state.configured
                ? `מוגדר · ${state.masked || "••••"}`
                : "הדבקת ערך חדש"
            }
          />
          <IconButton icon="paste" label="הדבק ערך מלוח ההעתקה" type="button" onClick={() => void paste()} />
          <IconButton icon="trash" label="מחק ערך שמור" type="button" disabled={!secret && !state.configured} onClick={() => editSecret("")} />
          {help?.help_url && (
            <Button
              type="button"
              className="secret-help-link"
              onClick={() =>
                void invoke("open_chat_link", {
                  target: help.help_url,
                  local: false,
                })
              }
            >
              קבל מפתח
            </Button>
          )}
        </div>
        {help?.key_instructions && (
          <small className="secret-instructions">{help.key_instructions}</small>
        )}
        <ManagementFeedback message={status} />
      </SourceSettingField>
    );
  }
  if (definition.control === "directory") {
    const clear = async () => {
      setStatus("");
      try { await onSave(definition.path, definition.multiple ? [] : ""); setDraft(""); }
      catch (reason) { setStatus(`השמירה נכשלה: ${String(reason)}`); }
    };
    return (
      <SourceSettingField {...sourceProps}>
        <div className="source-directory-picker">
          <Field label={definition.label} hiddenLabel readOnly dir="ltr" value={draft} />
          <IconButton icon={"folder"} label={definition.multiple ? "הוסף תיקייה" : "בחר תיקייה"} type="button" onClick={() => void choosePath()} />
        </div>
        {definition.multiple && (
          <Button
            type="button"
            className="source-clear-paths"
            onClick={() => void clear()}
          >
            נקה
          </Button>
        )}
        <ManagementFeedback message={status} />
      </SourceSettingField>
    );
  }
  if (definition.control === "switch") {
    return <SourceSettingField {...sourceProps} className={controlDisabled ? "is-disabled" : ""}>
      <Switch label={definition.label} checked={Boolean(raw)} disabled={controlDisabled}
        onCheckedChange={checked => { setStatus(""); void onSave(definition.path, checked).catch(reason => setStatus(`השמירה נכשלה: ${String(reason)}`)); }} />
      <ManagementFeedback message={status} />
    </SourceSettingField>;
  }

  if (definition.control === "segmented") {
    const optionIcon = (value: string | number) => value === "locked_down" ? "lock" : value === "balanced" ? "shield" : value === "max_autonomy" ? "spark" : value === "light" ? "sun" : value === "dark" ? "moon" : value === "system" ? "screen" : undefined;
    return (
      <SourceSettingField {...sourceProps}>
        <SegmentedControl className="source-segmented" label={definition.label}>
          {definition.options?.map((option) => (
            <Button
              type="button"
              key={String(option.value)}
              aria-pressed={String(raw ?? "") === String(option.value)}
              className={
                String(raw ?? "") === String(option.value) ? "active" : ""
              }
              onClick={() => {
                setStatus("");
                void onSave(definition.path, option.value)
                  .then(() => setStatus(""))
                  .catch((reason) => setStatus(String(reason)));
              }}
            >
              {optionIcon(option.value) && (
                <Icon name={optionIcon(option.value)!} size={18} />
              )}
              <span>{option.label}</span>
            </Button>
          ))}
        </SegmentedControl>
        <ManagementFeedback message={status} />
      </SourceSettingField>
    );
  }
  if (definition.control === "select")
    return (
      <SourceSettingField {...sourceProps}>
        <SelectField label={definition.label} hiddenLabel
          value={String(raw ?? "")}
          onChange={(event) => {
            setStatus("");
            void onSave(definition.path, event.target.value)
              .then(() => setStatus(""))
              .catch((reason) => setStatus(String(reason)));
          }}
        >
          {definition.options?.map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </SelectField>
        <ManagementFeedback message={status} />
      </SourceSettingField>
    );
  if (definition.control === "range") {
    const rangeLabel =
      (definition.path === "max_agent_loops" && Number(draft) >= 31) ||
      (definition.path === "background_recurring_catch_up_window_minutes" &&
        Number(draft) >= 181)
        ? "ללא הגבלה"
        : definition.path === "voice_ambient_noise_duration" &&
            Number(draft) <= 0
          ? "כבוי"
          : `${draft} ${definition.suffix || ""}`.trim();
    return (
      <SourceSettingField {...sourceProps} className="range-field">
        <RangeField label={definition.label} value={Number(draft || definition.min || 0)} min={definition.min ?? 0} max={definition.max ?? 100} step={definition.step || 1}
          formatValue={() => rangeLabel} onValueChange={value => setDraft(String(value))}
          onPointerUp={event => void saveDraft(event.currentTarget.value)} onKeyUp={event => void saveDraft(event.currentTarget.value)} />
        <ManagementFeedback message={status} />
      </SourceSettingField>
    );
  }
  return (
    <SourceSettingField {...sourceProps}>
      <div>
        <Field label={definition.label} hiddenLabel
          dir={definition.control === "number" ? "ltr" : "auto"}
          type={definition.control === "number" ? "number" : "text"}
          min={definition.min}
          max={definition.max}
          step={definition.step}
          value={draft}
          onChange={(event) => queueSave(event.target.value)}
          onBlur={() => {
            if (saveTimer.current !== null)
              window.clearTimeout(saveTimer.current);
            saveTimer.current = null;
            void saveDraft();
          }}
        />
        {definition.suffix && <i>{definition.suffix}</i>}
        {["directory", "file"].includes(definition.control) && (
          <Button type="button" onClick={() => void choosePath()}>
            בחירה
          </Button>
        )}
      </div>
      <ManagementFeedback message={status} />
    </SourceSettingField>
  );
}

function SearchableModelPicker({ models, selected, loading, favorites, onSelect, onToggleFavorite }: {
  models: string[]; selected: string; loading: boolean; favorites: Json[]; theme: ResolvedTheme;
  onSelect: (model: string) => Promise<void>; onToggleFavorite: (model: string) => Promise<void>;
}) {
  const [query, setQuery] = useState(""), [error, setError] = useState("");
  const options = useRef<HTMLDivElement>(null);
  const allModels = useMemo(() => [...new Set([selected, ...models])].filter(Boolean), [models, selected]);
  const filtered = useMemo(() => {
    const terms = query.toLocaleLowerCase("en").split(/[^a-z0-9]+/).filter(Boolean);
    return allModels.filter(model => { const normalized = model.toLocaleLowerCase("en").replace(/[^a-z0-9]+/g, " ");
      return terms.every(term => normalized.includes(term) || normalized.replace(/ /g, "").includes(term)); });
  }, [query, allModels]);
  return <div className="source-model-picker"><Popover label={selected || (models.length ? "בחר מודל" : "לא נמצאו מודלים")}>
    {close => <div className="source-model-popup" onKeyDown={event => {
      const choices = [...(options.current?.querySelectorAll<HTMLButtonElement>('[role="option"]') || [])];
      const index = choices.indexOf(document.activeElement as HTMLButtonElement);
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key) && choices.length) {
        event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1 : event.key === "ArrowDown" ? (index + 1) % choices.length : (index - 1 + choices.length) % choices.length;
        choices[next].focus();
      }
    }}>
      <SearchField label="חפש מודל" hiddenLabel autoFocus placeholder="חפש מודל" value={query} onChange={event => setQuery(event.target.value)} />
      {loading && <LoadingState label="טוען מודלים…" />}
      <ManagementFeedback message={error} />
      <div ref={options} role="listbox" aria-label="מודלים">{filtered.slice(0,250).map(model => {
        const favorite = favorites.some(item => item.model === model);
        return <div key={model} className={model === selected ? "selected" : ""}>
          <IconButton icon={favorite ? "starFilled" : "star"} label={`${favorite ? "הסר" : "הוסף"} ${model} ${favorite ? "מהמועדפים" : "למועדפים"}`}
            onClick={() => void onToggleFavorite(model).catch(reason => setError(`שמירת המועדף נכשלה: ${String(reason)}`))} />
          <Button variant="ghost" role="option" aria-selected={model === selected} onClick={() => void onSelect(model).then(close).catch(reason => setError(`בחירת המודל נכשלה: ${String(reason)}`))}><bdi>{model}</bdi></Button>
        </div>;
      })}{!filtered.length && <p className="sds-hint">לא נמצאו מודלים</p>}</div>
    </div>}
  </Popover></div>;
}

export function ProviderWorkflow({
  values,
  secrets,
  save,
  reload,
  schema,
  theme,
}: {
  values: Json;
  secrets: SecretState;
  save: (path: string, value: unknown) => Promise<void>;
  reload: () => Promise<void>;
  schema: SettingsSchema;
  theme: ResolvedTheme;
}) {
  const provider = String(values.api_mode || "gemini");
  const modelKey = `selected_${provider}_model`;
  const selectedModel = String(values[modelKey] || "");
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const modelLoadGeneration = useRef(0);
  const [keyDraft, setKeyDraft] = useState("");
  const [qwenUrlDraft, setQwenUrlDraft] = useState(String(values.qwen_base_url || ""));
  const [status, setStatus] = useState("");
  const validationTimer = useRef<number | null>(null);
  const validationGeneration = useRef(0);
  const favoriteOnLoadProvider = useRef("");
  const [reasoning, setReasoning] = useState<{
    reasoning_effort?: string;
    reasoning_options?: Array<{ value: string; label: string }>;
  }>({});
  const favorites = asRows(values.favorite_models);
  const secretKey = providerSecretKeys[provider];
  const providerMetadata = schema.providers.find(
    (item) => item.id === provider,
  );
  const refreshModels = useCallback(async () => {
    const generation = ++modelLoadGeneration.current;
    setModelsLoading(true);
    try {
      const data = await coreApi<{
        models: Array<string | { id?: string; name?: string }>;
        message?: string;
      }>("GET", `/v2/providers/${encodePath(provider)}/models`);
      if (generation !== modelLoadGeneration.current) return;
      setModels(
        data.models
          .map((item) =>
            typeof item === "string" ? item : item.id || item.name || "",
          )
          .filter(Boolean),
      );
      if (data.message) setStatus(data.message);
    } catch (reason) {
      if (generation !== modelLoadGeneration.current) return;
      setModels(selectedModel ? [selectedModel] : []);
      setStatus(String(reason));
    } finally {
      if (generation === modelLoadGeneration.current) setModelsLoading(false);
    }
  }, [provider, selectedModel]);
  useEffect(() => {
    void refreshModels();
    return () => { modelLoadGeneration.current += 1; };
  }, [refreshModels]);
  useEffect(() => {
    setQwenUrlDraft(String(values.qwen_base_url || ""));
  }, [values.qwen_base_url]);
  const saveQwenUrl = async () => {
    const url = qwenUrlDraft.trim().replace(/\/+$/, "");
    if (url === String(values.qwen_base_url || "")) return;
    if (url) {
      try {
        const parsed = new URL(url);
        if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password)
          throw new Error("invalid URL");
      } catch {
        setStatus("כתובת API של Qwen אינה תקינה. הזן כתובת HTTP או HTTPS מלאה ממסוף הספק.");
        return;
      }
    }
    try {
      await save("qwen_base_url", url);
      setQwenUrlDraft(url);
      await refreshModels();
    } catch (reason) {
      setStatus(String(reason));
    }
  };
  useEffect(() => {
    if (modelsLoading || favoriteOnLoadProvider.current !== provider) return;
    favoriteOnLoadProvider.current = "";
    const model = selectedModel || models[0] || "";
    if (
      !model ||
      favorites.some(
        (item) => item.provider === provider && item.model === model,
      )
    )
      return;
    void save("favorite_models", [{ provider, model }, ...favorites].slice(0, 60)).catch(reason => setStatus(`שמירת המועדף נכשלה: ${String(reason)}`));
  }, [favorites, models, modelsLoading, provider, save, selectedModel]);
  useEffect(() => {
    if (selectedModel)
      void coreApi<typeof reasoning>(
        "GET",
        `/v2/providers/${encodePath(provider)}/reasoning?model=${encodeURIComponent(selectedModel)}`,
      )
        .then(setReasoning)
        .catch(() => setReasoning({}));
  }, [provider, selectedModel]);
  useEffect(
    () => () => {
      if (validationTimer.current !== null)
        window.clearTimeout(validationTimer.current);
    },
    [],
  );
  const validateAndSaveKey = async (supplied = keyDraft) => {
    if (!secretKey || !supplied.trim()) return;
    if (validationTimer.current !== null) {
      window.clearTimeout(validationTimer.current);
      validationTimer.current = null;
    }
    const generation = ++validationGeneration.current;
    setStatus("בודק את המפתח לפני שמירה…");
    try {
      const result = await validateAndPersistProviderKey({
        provider,
        secretKey,
        secret: supplied,
        localUrl: values.local_server_url,
      });
      if (generation !== validationGeneration.current) return;
      setKeyDraft("");
      setModels(result.models || []);
      setStatus(`המפתח נבדק ונשמר: ${secrets[secretKey]?.masked || "••••"}${result.message ? ` — ${result.message}` : ""}`);
      await reload();
    } catch (reason) {
      if (generation === validationGeneration.current)
        setStatus(
          `המפתח לא נשמר: ${reason instanceof Error ? reason.message : String(reason)}`,
        );
    }
  };
  const editKey = (next: string) => {
    setKeyDraft(next);
    validationGeneration.current += 1;
    if (validationTimer.current !== null)
      window.clearTimeout(validationTimer.current);
    if (!next.trim()) {
      setStatus("המפתח יימחק בשמירה.");
      return;
    }
    setStatus("המפתח ייבדק לפני שמירה...");
    validationTimer.current = window.setTimeout(() => {
      validationTimer.current = null;
      void validateAndSaveKey(next);
    }, 900);
  };
  const pasteKey = async () => {
    try {
      const value = (await navigator.clipboard.readText()).trim();
      if (!value) {
        setStatus("לוח ההעתקה אינו מכיל טקסט.");
        return;
      }
      editKey(value);
    } catch (reason) {
      setStatus(`ההדבקה נכשלה: ${String(reason)}`);
    }
  };
  const removeKey = async () => {
    validationGeneration.current += 1;
    if (validationTimer.current !== null)
      window.clearTimeout(validationTimer.current);
    setKeyDraft("");
    if (secretKey && configured?.configured) {
      await coreApi(
        "DELETE",
        `/v2/settings/secrets/${encodePath(secretKey)}`,
        {},
        true,
      );
      setStatus("המפתח נמחק.");
      await reload();
    }
  };
  const validateExisting = async () => {
    setStatus("בודק חיבור…");
    try {
      const result = await coreApi<{
        ok: boolean;
        message: string;
        models: string[];
      }>("POST", `/v2/providers/${encodePath(provider)}/validate`, {}, true);
      setStatus(result.ok ? `החיבור תקין. ${result.message}` : result.message);
      if (result.ok) setModels(result.models || []);
    } catch (reason) {
      setStatus(String(reason));
    }
  };
  const toggleFavorite = async (model = selectedModel) => {
    const exists = favorites.some(
      (item) => item.provider === provider && item.model === model,
    );
    await save(
      "favorite_models",
      exists
        ? favorites.filter(
            (item) => !(item.provider === provider && item.model === model),
          )
        : [...favorites, { provider, model }],
    );
  };
  const codexAction = async (action: string) => {
    setStatus("מבצע פעולת Codex…");
    try {
      const data = await coreApi<{ state: string; message: string }>(
        "POST",
        "/v2/management/settings/actions",
        { action },
        true,
      );
      setStatus(data.message);
      await reload();
      if (action !== "codex_status") await refreshModels();
    } catch (reason) {
      setStatus(String(reason));
    }
  };
  useEffect(() => {
    if (provider === "openai_codex_signin") void codexAction("codex_status");
  }, [provider]);
  const configured = secretKey ? secrets[secretKey] : undefined;
  return (
    <div className="source-provider-workflow">
      <SourceSettingField
        label="ספק המודל"
        help="בחר את שירות ה-AI שסמארטי ישתמש בו לתשובות ולתכנון פעולות."
        dataPath="api_mode"
      >
        <ProviderPicker value={provider}
          onSelect={async next => {
            if (next === provider) return;
            if (next !== provider) favoriteOnLoadProvider.current = next;
            validationGeneration.current++; if (validationTimer.current !== null) window.clearTimeout(validationTimer.current);
            setKeyDraft(""); setStatus("");
            try { await save("api_mode", next); }
            catch (reason) { setStatus(`בחירת הספק נכשלה: ${String(reason)}`); throw reason; }
          }}
        />
      </SourceSettingField>
      {secretKey && (
        <>
          <SourceSettingField
            label="מפתח גישה לספק המודל"
            help="מפתח API הוא קוד גישה אישי שמאפשר לסמארטי לשלוח בקשות מאובטחות לספק המודל. הוא נדרש לספקים חיצוניים, נבדק מול הספק לפני שמירה ונשמר כמפתח מוסתר שלא מוצג בלוגים."
            className="provider-secret-field"
            dataPath="provider_api_key"
          >
            <div className="secret-link-row">
              <Field label="מפתח גישה לספק המודל" hiddenLabel
                type="password"
                autoComplete="new-password"
                value={keyDraft}
                onChange={(event) => editKey(event.target.value)}
                placeholder={
                  configured?.configured
                    ? `מוגדר · ${configured.masked}`
                    : "הדבקת מפתח API"
                }
              />
              <IconButton icon={"paste"} label="הדבק מפתח מלוח ההעתקה" className="icon-control" type="button" onClick={() => void pasteKey()} />
              <IconButton icon={"trash"} label="מחק מפתח שמור" className="icon-control" type="button" disabled={!keyDraft && !configured?.configured} onClick={() => void removeKey().catch(reason => setStatus(`מחיקת המפתח נכשלה: ${String(reason)}`))} />
              {providerMetadata?.help_url && (
                <Button
                  type="button"
                  className="secret-help-link"
                  onClick={() =>
                    void invoke("open_chat_link", {
                      target: providerMetadata.help_url,
                      local: false,
                    })
                  }
                >
                  קבל מפתח
                </Button>
              )}
        </div>
          </SourceSettingField>
          <ManagementFeedback message={status} />
          {providerMetadata?.key_instructions && (
            <p className="secret-instructions">
              {providerMetadata.key_instructions}
            </p>
          )}
          <div className="source-field-actions">
            <Button
              type="button"
              disabled={!keyDraft.trim()}
              onClick={() => void validateAndSaveKey()}
            >
              בדיקה ושמירה
            </Button>
            <Button type="button" onClick={() => void validateExisting()}>
              בדיקת החיבור
            </Button>
          </div>
        </>
      )}
      {provider === "qwen" && (
        <SourceSettingField
          label="כתובת API של Qwen"
          help="המפתח וכתובת השרת חייבים להשתייך לאותו אזור, מרחב עבודה ומסלול ב-Alibaba Model Studio. העתק את Base URL ממסוף הספק. שדה ריק משתמש בברירת המחדל של סין."
          dataPath="qwen_base_url"
        >
          <Field label="כתובת API של Qwen" hiddenLabel
            type="url"
            dir="ltr"
            value={qwenUrlDraft}
            placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
            onChange={(event) => setQwenUrlDraft(event.target.value)}
            onBlur={() => void saveQwenUrl()}
          />
        </SourceSettingField>
      )}
      {provider === "local" && (
        <SourceSettingField
          label="מפתח גישה לספק המודל"
          help="מפתח API אינו נדרש כאשר משתמשים בשרת מודל מקומי."
          dataPath="provider_api_key"
        >
          <div className="secret-link-row">
            <Field label="מפתח גישה לספק המודל" hiddenLabel
              type="password"
              disabled
              placeholder="לא נדרש מפתח למודל מקומי"
            />
            <IconButton icon={"paste"} label="הדבק מפתח מלוח ההעתקה" className="icon-control" type="button" disabled />
            <IconButton icon={"trash"} label="מחק מפתח שמור" className="icon-control" type="button" disabled />
          </div>
        </SourceSettingField>
      )}
      {provider === "openai_codex_signin" && (
        <>
          <SourceSettingField
            label="חיבור ChatGPT / Codex"
            help="התחברות רשמית עם חשבון ChatGPT או Codex. לא נשמרים סיסמה, API key או token בהגדרות של סמארטי."
            dataPath="codex_signin"
          >
            <ManagementFeedback message={status || "אפשר להתחבר באמצעות חשבון ChatGPT / Codex."} />
            <div className="inline-actions codex-actions">
              <Button type="button" variant="primary"
                className="primary"
                onClick={() => void codexAction("codex_login")}
              >
                התחבר עם ChatGPT / Codex
              </Button>
              <Button type="button" onClick={() => void codexAction("codex_check")}>
                בדוק חיבור
              </Button>
              <Button type="button" onClick={() => void codexAction("codex_logout")}>
                התנתק
              </Button>
            </div>
          </SourceSettingField>
          <p className="secret-instructions">
            חיבור זה משתמש ב-Codex sign-in הרשמי של OpenAI, כפוף למגבלות החשבון
            והתוכנית שלך, ועלול להשתנות לפי מדיניות OpenAI.
          </p>
        </>
      )}
      <SourceSettingField
        label="מודל"
        help="בחירת המודל הפעיל לשיחה. בחירה נשמרת גם כמועדף כדי שאפשר יהיה להחליף אליו במהירות מהצ'אט."
        dataPath="selected_provider_model"
      >
        <SearchableModelPicker
          models={models}
          selected={selectedModel}
          loading={modelsLoading}
          favorites={favorites.filter((item) => item.provider === provider)}
          theme={theme}
          onSelect={(model) => save(modelKey, model)}
          onToggleFavorite={toggleFavorite}
        />
      </SourceSettingField>
      {reasoning.reasoning_options?.length ? (
        <SourceSettingField
          label="עוצמת חשיבה"
          help="קובעת את עוצמת החשיבה של המודל הפעיל. האפשרויות מותאמות אוטומטית לחוזה של משפחת המודל; בחירה באוטומטית משאירה את השדה ריק ומשתמשת בברירת הספק."
          dataPath="provider_reasoning_effort"
        >
          <SelectField label="עוצמת חשיבה" hiddenLabel
            value={reasoning.reasoning_effort || "auto"}
            onChange={(event) =>
              void coreApi<typeof reasoning>(
                "POST",
                `/v2/providers/${encodePath(provider)}/reasoning`,
                { model: selectedModel, effort: event.target.value },
                true,
              ).then(setReasoning).catch(reason => setStatus(`שמירת החשיבה נכשלה: ${String(reason)}`))
            }
          >
            {reasoning.reasoning_options.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </SelectField>
        </SourceSettingField>
      ) : null}
    </div>
  );
}

export function PolicyMatrix({
  values,
  save,
}: {
  values: Json;
  save: (path: string, value: unknown) => Promise<void>;
}) {
  const matrix =
    values.policy_matrix && typeof values.policy_matrix === "object"
      ? (values.policy_matrix as Json)
      : {};
  return (
    <div className="source-policy-page">
      <p className="source-settings-hint">
        הפרופיל הראשי מספיק לרוב השימושים. כאן אפשר לדייק יכולות בודדות בלי
        להפוך את כל מסך האבטחה למסובך.
      </p>
      <div>
        {Object.entries(capabilityLabels).map(([key, label]) => (
          <SourceSettingField
            key={key}
            label={label}
            help="בחר אם סמארטי יוכל להשתמש ביכולת הזו, יבקש אישור בכל פעם, או יחסום אותה לחלוטין."
          >
            <SegmentedControl className="source-segmented" label={label}>
              {policyOptions.map((option) => (
                <Button
                  type="button"
                  key={String(option.value)}
                  aria-pressed={String(matrix[key] || "ask") === String(option.value)}
                  className={
                    String(matrix[key] || "ask") === String(option.value)
                      ? "active"
                      : ""
                  }
                  onClick={() =>
                    void save("policy_matrix", {
                      ...matrix,
                      [key]: option.value,
                    }).catch(() => undefined)
                  }
                >
                  {option.label}
                </Button>
              ))}
            </SegmentedControl>
          </SourceSettingField>
        ))}
      </div>
    </div>
  );
}

function AdvancedDeveloperLogPanel({ theme: _theme }: { theme: ResolvedTheme }) {
  const [lines, setLines] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [limit, setLimit] = useState(500);
  const [exportLimit, setExportLimit] = useState(1000);
  const [hidePersonal, setHidePersonal] = useState(true);
  const [status, setStatus] = useState("טוען את הלוג המאוחד…");
  const [confirmClear, setConfirmClear] = useState(false);
  const load = useCallback(
    async (requested = limit) => {
      setStatus("טוען לוגים…");
      try {
        const result = await coreApi<{ lines: string[]; path: string }>(
          "GET",
          `/v2/management/logs?limit=${requested}&personal=shown`,
        );
        setLines(result.lines);
        setPath(result.path);
        setStatus(
          `מוצגות ${result.lines.length.toLocaleString("he-IL")} השורות האחרונות. קבצים ישנים יותר נטענים רק לפי דרישה.`,
        );
      } catch (reason) {
        setStatus(`טעינת הלוג נכשלה: ${String(reason)}`);
      }
    },
    [limit],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const loadOlder = () =>
    setLimit((current) => Math.min(20_000, current + 500));
  const exportLog = async () => {
    setStatus("מכין עותק לייצוא…");
    try {
      const result = await coreApi<{ lines: string[] }>(
        "GET",
        `/v2/management/logs?limit=${exportLimit}&personal=${hidePersonal ? "hidden" : "shown"}`,
      );
      const stamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "-");
      const header = [
        "SmartiAI Unified Diagnostic Log Export",
        `Exported: ${new Date().toISOString()}`,
        `Requested lines: ${exportLimit <= 0 ? "all retained logs" : exportLimit}`,
        `Exported lines: ${result.lines.length}`,
        `Personal content hidden: ${hidePersonal ? "yes" : "no"}`,
        "",
      ];
      await invoke("save_text_file", {
        suggestedName: `SmartiAI-log-${stamp}.txt`,
        contents: [...header, ...result.lines].join("\n"),
      });
      setStatus("העותק הועבר לחלון שמירה של Windows.");
    } catch (reason) {
      setStatus(`ייצוא הלוג נכשל: ${String(reason)}`);
    }
  };
  const clearLog = async () => {
    setStatus("מנקה את הלוג המאוחד…");
    try {
      await coreApi(
        "POST",
        "/v2/management/settings/actions",
        { action: "log_clear", confirmation: "נקה לוג" },
        true,
      );
      setLimit(500);
      await load(500);
      setConfirmClear(false);
      return true;
    } catch (reason) {
      setStatus(`ניקוי הלוג נכשל: ${String(reason)}`);
      return false;
    }
  };
  return (
    <SourceSettingField
      label="לוג מאוחד"
      help="צפייה עצלה וייצוא של אירועי הסוכן, ספקי ה-AI, זמן הריצה, האבטחה, האבחון והמיומנויות מקובץ מתחלף אחד."
      dataPath="developer_unified_log"
      advanced
    >
      <div className="source-developer-log">
        <div className="source-log-actions">
          <Button type="button" onClick={() => void load()}>
            רענן לוגים
          </Button>
          <Button type="button" disabled={limit >= 20_000} onClick={loadOlder}>
            טען 500 שורות קודמות
          </Button>
          <IconButton icon={"export"} label="ייצוא הלוג לקובץ טקסט" type="button" className="icon-control" onClick={() => void exportLog()} />
          <Button type="button" onClick={() => setConfirmClear(true)}>
            נקה לוג
          </Button>
        </div>
        <div className="source-log-export">
          <div>
            כמות שורות לייצוא
            <SelectField label="כמות שורות לייצוא" hiddenLabel
              value={exportLimit}
              onChange={(event) => setExportLimit(Number(event.target.value))}
            >
              <option value="500">500 שורות אחרונות</option>
              <option value="1000">1,000 שורות אחרונות</option>
              <option value="2500">2,500 שורות אחרונות</option>
              <option value="5000">5,000 שורות אחרונות</option>
              <option value="10000">10,000 שורות אחרונות</option>
              <option value="0">כל הלוגים השמורים</option>
            </SelectField>
          </div>
          <div>
            <Switch label="הסתר תוכן אישי"

              checked={hidePersonal}
              onCheckedChange={(checked) => setHidePersonal(checked)}
            />
            הסתר תוכן אישי
          </div>
        </div>
        <ManagementFeedback message={status} />
        <code dir="ltr">{path}</code>
        <pre dir="ltr">
          {[
            "=== SmartiAI Unified Log ===",
            ...(lines.length ? lines : ["אין עדיין רשומות לוג."]),
          ].join("\n")}
        </pre>
      </div>
      {confirmClear && (
        <ConfirmDialog
          title="ניקוי לוג"
          description="לנקות את הלוג המאוחד של סמארטי? הפעולה תמחק את הקובץ הפעיל בלבד. קובצי סבב ישנים יישארו עד להחלפתם האוטומטית."
          confirmLabel="נקה"
          danger
          onCancel={() => setConfirmClear(false)}
          onConfirm={clearLog}
        />
      )}
    </SourceSettingField>
  );
}

function SslWorkflow({
  values,
  saveValues,
}: {
  values: Json;
  saveValues: (values: Json) => Promise<void>;
}) {
  const persistedMode = String(values.ssl_trust_mode || "system");
  const [expanded, setExpanded] = useState(false);
  const [mode, setMode] = useState(persistedMode);
  const [customPath, setCustomPath] = useState(
    String(values.ssl_custom_ca_path || ""),
  );
  const [certificateDetail, setCertificateDetail] = useState(
    customPath
      ? "נבחרה תעודה מיובאת."
      : "לא נבחר קובץ. אפשר לבחור את תעודת השורש הציבורית של ספק הסינון.",
  );
  const [ack, setAck] = useState(false);
  const [tested, setTested] = useState(
    Boolean(values.ssl_filter_setup_completed),
  );
  const [testing, setTesting] = useState(false), [insecureConfirm, setInsecureConfirm] = useState(false);
  const [status, setStatus] = useState("טרם בוצעה בדיקה עבור הבחירה הנוכחית.");
  const resetEditor = () => {
    setMode(String(values.ssl_trust_mode || "system"));
    setCustomPath(String(values.ssl_custom_ca_path || ""));
    setTested(Boolean(values.ssl_filter_setup_completed));
    setAck(false);
    setStatus("טרם בוצעה בדיקה עבור הבחירה הנוכחית.");
  };
  const chooseCertificate = async () => {
    const selected = await invoke<string | null>("pick_management_path", {
      kind: "file",
    });
    if (!selected) return;
    setStatus("מייבא ומאמת את התעודה…");
    try {
      const result = await coreApi<{
        ok: boolean;
        path: string;
        message: string;
        metadata?: { name?: string; expires?: string; fingerprint?: string };
      }>(
        "POST",
        "/v2/management/settings/actions",
        { action: "ssl_import_ca", source_path: selected },
        true,
      );
      setCustomPath(result.path);
      const metadata = result.metadata || {};
      setCertificateDetail(
        [
          metadata.name ? `תעודה: ${metadata.name}` : "התעודה אומתה",
          metadata.expires ? `בתוקף עד ${metadata.expires}` : "",
          metadata.fingerprint
            ? `SHA-256 ${metadata.fingerprint.slice(0, 16)}…${metadata.fingerprint.slice(-8)}`
            : "",
          result.message,
        ]
          .filter(Boolean)
          .join(" · "),
      );
      setTested(false);
      setStatus("התעודה יובאה ואומתה. מומלץ לבצע בדיקת חיבור.");
    } catch (reason) {
      setCustomPath("");
      setTested(false);
      setCertificateDetail(`לא ניתן לייבא את התעודה: ${String(reason)}`);
      setStatus("ייבוא התעודה נכשל.");
    }
  };
  const test = async () => {
    if (mode === "custom_ca" && !customPath) {
      setStatus("יש לבחור תחילה תעודת שורש ציבורית תקינה.");
      return;
    }
    if (mode === "legacy_insecure" && !ack) {
      setStatus("יש לאשר תחילה שהמשמעות של חיבור ללא אימות תעודות ברורה.");
      return;
    }
    setTesting(true);
    setStatus("בודק את החיבור ברקע…");
    try {
      const result = await coreApi<{
        ok: boolean;
        verified: boolean;
        message: string;
      }>(
        "POST",
        "/v2/management/settings/actions",
        {
          action: "ssl_test",
          ssl_trust_mode: mode,
          ssl_custom_ca_path: customPath,
        },
        true,
      );
      setTested(Boolean(result.verified));
      setStatus(result.ok ? result.message : `הבדיקה נכשלה: ${result.message}`);
    } catch (reason) {
      setTested(false);
      setStatus(
        `הבדיקה נכשלה ולא בוצע מעבר אוטומטי למצב פחות בטוח: ${String(reason)}`,
      );
    } finally {
      setTesting(false);
    }
  };
  const persist = async (confirmedInsecure = false) => {
    if (mode === "custom_ca" && !customPath) {
      setStatus("יש לבחור תחילה תעודת שורש ציבורית תקינה.");
      return;
    }
    if (mode === "legacy_insecure") {
      if (!ack) {
        setStatus("יש לאשר שהמשמעות של כיבוי אימות תעודות HTTPS ברורה.");
        return;
      }
      if (!confirmedInsecure) { setInsecureConfirm(true); return; }
    }
    await saveValues({
      ssl_trust_mode: mode,
      ssl_custom_ca_path: customPath,
      ssl_filter_setup_completed: tested,
      ssl_legacy_insecure_allowed_hosts: [],
      ssl_trust_migration_version: 1,
      allow_insecure_ssl_compat: mode === "legacy_insecure",
    });
    setInsecureConfirm(false); setExpanded(false);
  };
  const summary =
    persistedMode === "custom_ca"
      ? {
          mode: "תעודת סינון מיובאת",
          status: Boolean(values.ssl_filter_setup_completed)
            ? "אימות HTTPS פעיל · החיבור עבר את הבדיקה האחרונה"
            : "אימות HTTPS פעיל · מומלץ לבצע בדיקת חיבור",
          detail: `תעודה בשימוש: ${String(values.ssl_custom_ca_path || "לא נבחרה תעודה")}`,
        }
      : persistedMode === "legacy_insecure"
        ? {
            mode: "תאימות ישנה ללא אימות תעודות",
            status: "אזהרה: אימות HTTPS כבוי באופן רחב",
            detail:
              "אין תעודת CA בשימוש. Smarti וכלי הרשת שמופעלים ממנו מקבלים חיבורי HTTPS בלי לאמת את זהות השרת.",
          }
        : {
            mode: "מאגר האישורים של Windows",
            status: Boolean(values.ssl_filter_setup_completed)
              ? "אימות HTTPS פעיל · החיבור עבר את הבדיקה האחרונה"
              : "אימות HTTPS פעיל · האפשרות המומלצת לרשת מסוננת",
            detail:
              "מקור האמון: מאגר האישורים המקומי של Windows, כולל תעודות סינון שמותקנות במערכת.",
          };
  return (
    <section
      className={`source-ssl-card ${persistedMode === "legacy_insecure" ? "danger" : ""}`}
      data-setting-path="ssl_trust_mode"
    >
      <header>
        <div>
          <small>המצב הפעיל כעת</small>
          <h3>{summary.mode}</h3>
          <b>{summary.status}</b>
          <p>{summary.detail}</p>
        </div>
        <Button
          type="button"
          onClick={() => {
            if (!expanded) resetEditor();
            setExpanded((value) => !value);
          }}
        >
          {expanded ? "ביטול" : "הגדר"}
          <i aria-hidden="true" />
        </Button>
      </header>
      {expanded && (
        <div className="source-ssl-editor">
          <h3>בחירת דרך החיבור המאובטח</h3>
          <p>
            בכל חיבור HTTPS, סמארטי בודק את זהות השרת. ברשת עם סינון מומלץ
            להתחיל במאגר האישורים של Windows. רק אם האפשרות הזו אינה עובדת, אפשר
            לייבא תעודת שורש ציבורית שהתקבלה מספק הסינון.
          </p>
          <SegmentedControl className="source-segmented" label="דרך החיבור המאובטח">
            {[
              ["system", "מאגר Windows"],
              ["custom_ca", "תעודה"],
              ["legacy_insecure", "ללא אימות"],
            ].map(([value, label]) => (
              <Button
                type="button"
                key={value}
                aria-pressed={mode === value}
                className={mode === value ? "active" : ""}
                onClick={() => {
                  setMode(value);
                  setTested(false);
                  setStatus(
                    value === "legacy_insecure"
                      ? "במצב ללא אימות, הבדיקה יכולה לאשר קישוריות בלבד — לא את זהות השרת."
                      : "הבדיקה תאשר ש-Smarti מצליח לזהות את שרשרת האישורים של השרת.",
                  );
                }}
              >
                {label}
              </Button>
            ))}
          </SegmentedControl>
          <section className="source-ssl-mode">
            {mode === "system" ? (
              <>
                <h4>מומלץ: מאגר האישורים של Windows</h4>
                <p>
                  כדי לאמת את שרשרת האישורים, סמארטי משתמש במאגר של Windows. כך
                  נעשה שימוש גם בתעודות של נטפרי, רימון וכדומה שכבר מותקנות
                  במערכת, בלי לבחור קובץ.
                </p>
                <b>אימות זהות השרת נשאר פעיל</b>
              </>
            ) : mode === "custom_ca" ? (
              <>
                <h4>תעודת שורש ציבורית של ספק הסינון</h4>
                <p>
                  מיועד למקרה שבו מאגר Windows עדיין אינו מספיק. יש לבחור קובץ
                  CER, CRT או PEM ציבורי שקיבלת מספק הסינון. Smarti דוחה מפתח
                  פרטי ותעודת שרת רגילה.
                </p>
                <div>
                  <Field label="קובץ תעודה" hiddenLabel
                    readOnly
                    dir="ltr"
                    value={customPath}
                    placeholder="לא נבחרה תעודה"
                  />
                  <Button
                    type="button"
                    onClick={() => void chooseCertificate().catch(reason => setStatus(`בחירת התעודה נכשלה: ${String(reason)}`))}
                  >
                    בחירת תעודה
                  </Button>
                </div>
                <small>{certificateDetail}</small>
              </>
            ) : (
              <>
                <h4>תאימות ישנה — חיבור ללא אימות תעודות</h4>
                <p>
                  אפשרות זו מחזירה את התנהגות ה-SSL הישנה של Smarti: אימות
                  תעודות HTTPS מכובה באופן רחב ב-Smarti, בדפדפן האוטומציה ובכלי
                  שורת הפקודה שמופעלים ממנו.
                </p>
                <strong>
                  זהות השרת לא תיבדק, ולכן מסנן או גורם אחר ברשת עלולים להתחזות
                  לשירות. יש להשתמש באפשרות זו רק אם מאגר Windows וייבוא תעודה
                  אינם פותרים את הבעיה.
                </strong>
                <div className="danger-ack">
                  <Switch label="ברור לי שבמצב זה אימות תעודות HTTPS כבוי בכל רכיבי Smarti"

                    checked={ack}
                    onCheckedChange={(checked) => setAck(checked)}
                  />
                  ברור לי שבמצב זה אימות תעודות HTTPS כבוי בכל רכיבי Smarti
                </div>
              </>
            )}
          </section>
          <section className="source-ssl-test">
            <h4>בדיקת החיבור</h4>
            <p>
              הבדיקה מתחברת לכתובת ציבורית קבועה של Google בלי לשלוח מפתח API,
              תוכן שיחה או מידע אישי.
            </p>
            <code>https://www.gstatic.com/generate_204</code>
            <div>
              <Button
                type="button"
                disabled={testing}
                onClick={() => void test()}
              >
                בדיקת חיבור
              </Button>
              <ManagementFeedback message={status} />
            </div>
          </section>
          <footer>
            <Button
              type="button"
              disabled={testing}
              onClick={() => {
                resetEditor();
                setExpanded(false);
              }}
            >
              ביטול
            </Button>
            <Button
              type="button"
              disabled={testing}
              onClick={() => void persist().catch(reason => setStatus(`השמירה נכשלה: ${String(reason)}`))}
            >
              שמירה והחלה
            </Button>
          </footer>
        </div>
      )}
      {insecureConfirm && <ConfirmDialog title="כיבוי אימות תעודות HTTPS" description="הבחירה מכבה באופן רחב את אימות תעודות HTTPS ב־Smarti ובכלים שמופעלים ממנו. להחיל את המצב הפחות בטוח?" danger confirmLabel="החלה ללא אימות" onCancel={() => setInsecureConfirm(false)} onConfirm={() => persist(true)} />}
    </section>
  );
}

export function SettingsView({
  section,
  setTheme,
  theme,
  onNavigate,
  policyOpen,
  setPolicyOpen,
  updateControls,
}: {
  section: SettingsSection;
  setTheme: (theme: ThemePreference) => void;
  theme: ResolvedTheme;
  onNavigate?: (section: SettingsSection) => void;
  policyOpen: boolean;
  setPolicyOpen: (open: boolean) => void;
  updateControls?: React.ReactNode;
}) {
  const [loadedData, setData] = useState<SafeSettings | null>(null);
  const data = loadedData ?? { values: {}, secrets: {} };
  const [loadError, setLoadError] = useState("");
  const [schema, setSchema] = useState<SettingsSchema>({
    providers: [],
    secret_help: {},
  });
  const [ttsVoices, setTtsVoices] = useState<
    Array<{ value: string; label: string }>
  >([]);
  const [query, setQuery] = useState("");
  const advanced = Boolean(
    (data.values.ui_preferences as Json | undefined)?.settings_show_advanced,
  );
  const [saveStatus, setSaveStatus] = useState("");
  const [resetConfirm, setResetConfirm] = useState(false);
  const [pendingFocus, setPendingFocus] = useState("");
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [ttsPreviewText, setTtsPreviewText] = useState(
    "שלום, זו תצוגה מקדימה של הקול הנוכחי.",
  );
  const speechPreview = useSpeechPlayback("settings:tts-preview");
  const [emailTestStatus, setEmailTestStatus] = useState(
    "הבדיקה תרוץ רק בלחיצה.",
  );
  const load = useCallback(
    async () => {
      setLoadError("");
      setData(await coreApi<SafeSettings>("GET", "/v2/settings"));
    },
    [],
  );
  useEffect(() => {
    void load().catch((reason) => setLoadError(String(reason)));
  }, [load]);
  useEffect(() => {
    void coreApi<SettingsSchema>("GET", "/v2/settings/schema").then(setSchema).catch(reason => setLoadError(`טעינת קטלוג ההגדרות נכשלה: ${String(reason)}`));
  }, []);
  useEffect(() => {
    void coreApi<{ items: Array<{ id: string; name: string }> }>(
      "GET",
      "/v2/audio/tts/voices",
    ).then((data) =>
      setTtsVoices(
        data.items.map((item) => ({ value: item.id, label: item.name })),
      ),
    ).catch(reason => setLoadError(`טעינת קולות נכשלה: ${String(reason)}`));
  }, []);
  useEffect(() => {
    const raw = data.values.settings_recent_searches;
    if (Array.isArray(raw))
      setRecentSearches(raw.map(String).filter(Boolean).slice(0, 8));
  }, [data.values.settings_recent_searches]);
  useEffect(() => {
    if (!pendingFocus) return;
    const frame = window.requestAnimationFrame(() => {
      const target = [
        ...document.querySelectorAll<HTMLElement>("[data-setting-path]"),
      ].find((item) => item.dataset.settingPath === pendingFocus);
      if (!target) return;
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      target.classList.add("source-setting-highlight");
      window.setTimeout(
        () => target.classList.remove("source-setting-highlight"),
        1450,
      );
      setPendingFocus("");
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pendingFocus, section, data.values]);
  const save = async (path: string, value: unknown) => {
    setSaveStatus("");
    let patch = patchForSetting(data.values, path, value);
    if (path === "autonomy_mode")
      patch = { ...patch, custom_permission_profile_enabled: false };
    if (path === "custom_permission_profile_enabled")
      patch = { ...patch, autonomy_mode: value ? "custom" : "balanced" };
    if (path === "enable_web_canvas")
      patch = {
        ...patch,
        enable_visual_surfaces: Boolean(value),
        ...(!value ? { enable_canvas_remote_images: false } : {}),
      };
    if (path === "default_output_dir")
      patch = { ...patch, allowed_write_dirs: [String(value || "")] };
    if (path === "updates_auto_check")
      patch = { ...patch, updates_check_interval_hours: 1 };
    try { const persisted = await coreApi<SafeSettings>(
      "PATCH",
      "/v2/settings",
      { values: patch },
      true,
    );
    setData(persisted);
    if (path === "ui_preferences.theme_mode")
      setTheme(value as ThemePreference);
    if (path === "voice_hotkey")
      await invoke("desktop_set_voice_hotkey", { shortcut: value });
    if (path === "keep_running_in_tray")
      await invoke("desktop_set_close_to_tray", { enabled: value });
    setSaveStatus("");
    } catch (reason) { setSaveStatus(`השמירה נכשלה: ${String(reason)}`); throw reason; }
  };
  const saveValues = async (values: Json) => {
    setSaveStatus("");
    try { const persisted = await coreApi<SafeSettings>(
      "PATCH",
      "/v2/settings",
      { values },
      true,
    );
    setData(persisted);
    setSaveStatus("");
    } catch (reason) { setSaveStatus(`השמירה נכשלה: ${String(reason)}`); throw reason; }
  };
  const fields = useMemo(
    () => matchingSettings(section, query, advanced),
    [section, query, advanced],
  );
  const groups = useMemo(() => {
    const result = new Map<string, SettingDefinition[]>();
    for (const item of fields)
      result.set(item.group, [...(result.get(item.group) || []), item]);
    return [...result.entries()];
  }, [fields]);
  const testEmail = async () => {
    setEmailTestStatus("בודק IMAP ו־SMTP בלי לשלוח הודעה…");
    const result = await coreApi<{ ok: boolean; message: string }>(
      "POST",
      "/v2/management/settings/actions",
      { action: "email_test" },
      true,
    );
    setEmailTestStatus(
      result.ok ? result.message : `החיבור נכשל: ${result.message}`,
    );
  };
  const resetSettings = async () => {
    setSaveStatus("מאפס…");
    try {
      const result = await coreApi<SafeSettings & { backup_path?: string }>(
        "POST",
        "/v2/management/settings/actions",
        { action: "reset" },
        true,
      );
      setData(result);
      const preferences =
        result.values.ui_preferences &&
        typeof result.values.ui_preferences === "object"
          ? (result.values.ui_preferences as Json)
          : {};
      setTheme(String(preferences.theme_mode || "system") as ThemePreference);
      await Promise.all([
        invoke("desktop_set_voice_hotkey", {
          shortcut: result.values.voice_hotkey,
        }).catch(() => undefined),
        invoke("desktop_set_close_to_tray", {
          enabled: result.values.keep_running_in_tray,
        }).catch(() => undefined),
      ]);
      setSaveStatus(
        result.backup_path
          ? `ההגדרות אופסו. גיבוי: ${result.backup_path}`
          : "ההגדרות אופסו לברירת המחדל",
      );
      setResetConfirm(false);
      return true;
    } catch (reason) {
      setSaveStatus(`האיפוס נכשל: ${String(reason)}`);
      return false;
    }
  };
  const rememberSearch = async () => {
    const normalized = query.trim();
    if (normalized.length < 2) return;
    const next = [
      normalized,
      ...recentSearches.filter((item) => item !== normalized),
    ].slice(0, 8);
    setRecentSearches(next);
    await save("settings_recent_searches", next);
  };
  const setAdvancedPersisted = async (checked: boolean) => {
    const preferences =
      data.values.ui_preferences &&
      typeof data.values.ui_preferences === "object"
        ? (data.values.ui_preferences as Json)
        : {};
    const nextPreferences = {
      ...preferences,
      settings_show_advanced: checked,
    };
    setData({
      ...data,
      values: { ...data.values, ui_preferences: nextPreferences },
    });
    try { await save("ui_preferences", nextPreferences); }
    catch (reason) { setData(data); throw reason; }
  };
  const activateSearchResult = async (definition: SettingDefinition) => {
    await rememberSearch();
    if (definition.advanced && !advanced) await setAdvancedPersisted(true);
    setPolicyOpen(false);
    setPendingFocus(definition.path);
    setQuery("");
    onNavigate?.(definition.section);
  };
  const title = settingsSectionTitles[section];
  // Mount the controls only after their values and visibility arrive together.
  if (!loadedData)
    return (
      <div className="management-page settings-page source-settings-page">
        {loadError ? (
          <>
            <ManagementFeedback message={`טעינת ההגדרות נכשלה: ${loadError}`} />
            <Button type="button" onClick={() => void load().catch((reason) => setLoadError(String(reason)))}>
              נסה שוב
            </Button>
          </>
        ) : (
          <LoadingState label="טוען הגדרות…" />
        )}
      </div>
    );
  return (
    <div className="management-page settings-page source-settings-page">
      <ManagementFeedback message={loadError} />
      <div className="source-settings-head">
        <ManagementFeedback message={saveStatus} />
        <SharedSettingRow title="הצג הגדרות מתקדמות" description="שדות טכניים, מגבלות זמן והרשאות מפורטות.">
          <Switch label="הצג הגדרות מתקדמות" checked={advanced} onCheckedChange={checked => void setAdvancedPersisted(checked).catch(reason => setSaveStatus(`השמירה נכשלה: ${String(reason)}`))} />
        </SharedSettingRow>
      </div>
      <div className="source-settings-search">
        <SearchField label="חפש הגדרה" hiddenLabel
          value={query}
          onChange={(event) => {
            setPolicyOpen(false);
            setQuery(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && fields[0]) {
              event.preventDefault();
              void activateSearchResult(fields[0]).catch(() => undefined);
            }
          }}
          placeholder="חפש הגדרה"
        />
      </div>
      <div className="source-settings-scroll">
        {!query && (
          <PageHeader title={policyOpen ? "שליטה מתקדמת ביכולות" : title.title} description={title.subtitle} />
        )}
        {query ? (
          <div className="source-search-results">
            <p>
              {fields.length
                ? `נמצאו ${fields.length} תוצאות. לחיצה תפתח ותסמן את ההגדרה.`
                : "לא נמצאו הגדרות. נסה מילה קרובה כמו מודל, קול, אימייל, אבטחה או תיקייה."}
            </p>
            {fields.slice(0, 40).map((definition) => (
              <Button
                type="button"
                key={`${definition.section}:${definition.path}`}
                onClick={() => void activateSearchResult(definition).catch(() => undefined)}
              >
                <b>{definition.label}</b>
                <small>
                  {settingsSectionTitles[definition.section].title}
                  {definition.advanced ? "  ·  מתקדם" : ""}
                </small>
              </Button>
            ))}
          </div>
        ) : policyOpen ? (
          <PolicyMatrix values={data.values} save={save} />
        ) : (
          <>
            {section === "settings_ai" && !query && (
              <ProviderWorkflow
                values={data.values}
                secrets={data.secrets}
                save={save}
                reload={load}
                schema={schema}
                theme={theme}
              />
            )}
            {section === "settings_advanced" && !query && advanced && (
              <SslWorkflow values={data.values} saveValues={saveValues} />
            )}
            {groups.map(([group, definitions]) => (
              <SettingsGroup title={group} key={group}>
                <div className="management-fields">
                  {definitions
                    .filter((definition) => !definition.providerWorkflow)
                    .filter(
                      (definition) =>
                        !["ssl_trust_mode", "ssl_custom_ca_path"].includes(
                          definition.path,
                        ),
                    )
                    .filter(
                      (definition) =>
                        definition.path !== "local_fast_mode_enabled" ||
                        String(data.values.api_mode || "gemini") === "local",
                    )
                    .map((definition) => (
                      <Fragment key={definition.path}>
                        <SettingRow
                          definition={
                            definition.path === "tts_voice_id"
                              ? { ...definition, options: ttsVoices }
                              : definition
                          }
                          values={data.values}
                          secrets={data.secrets}
                          onSave={save}
                          onSecretChanged={load}
                          schema={schema}
                          theme={theme}
                        />
                        {definition.path ===
                          "custom_permission_profile_enabled" &&
                          Boolean(
                            data.values.custom_permission_profile_enabled,
                          ) && (
                            <SourceSettingField
                              label="טבלת יכולות מפורטת"
                              help="לוח מתקדם לקביעה פרטנית אם סמארטי ישאל, ירשה או יחסום כל יכולת."
                            >
                              <Button
                                type="button"
                                className="source-secondary-button"
                                onClick={() => setPolicyOpen(true)}
                              >
                                <Icon name={"shield"} size={18} />
                                הגדרת התאמה אישית
                              </Button>
                            </SourceSettingField>
                          )}
                        {definition.path === "email_password" && (
                          <SourceSettingField
                            label="בדיקת חיבור אימייל"
                            help="בודק התחברות ל-IMAP ול-SMTP לפי הפרטים שהוזנו. הבדיקה לא שולחת הודעה."
                            dataPath="email_connection_test"
                          >
                            <div className="source-email-test">
                              <ManagementFeedback message={emailTestStatus} />
                              <Button
                                type="button"
                                className="source-secondary-button"
                                onClick={() => void testEmail().catch(reason => setEmailTestStatus(`הבדיקה נכשלה: ${String(reason)}`))}
                              >
                                <Icon
                                  name={"plug"}
                                  size={18}
                                />
                                בדוק חיבור
                              </Button>
                            </div>
                          </SourceSettingField>
                        )}
                        {definition.path === "tts_volume" && (
                          <SourceSettingField
                            label="תצוגה מקדימה"
                            help="משמיע את הטקסט לפי הקול והעוצמה שמוגדרים כרגע."
                            dataPath="tts_preview"
                          >
                            <div className="source-tts-preview">
                              <Field label="תצוגה מקדימה" hiddenLabel
                                value={ttsPreviewText}
                                onChange={(event) =>
                                  setTtsPreviewText(event.target.value)
                                }
                              />
                              <Button
                                type="button"
                                className="source-secondary-button"
                                onClick={() => void speechPreview.toggle(ttsPreviewText)}
                                disabled={speechPreview.pending}
                              >
                                <Icon name={"speaker"} size={18} />
                                {speechPreview.speaking ? "עצור הקראה" : "השמע"}
                              </Button>
                            </div>
                            {speechPreview.error && <p role="alert">{speechPreview.error}</p>}
                          </SourceSettingField>
                        )}
                        {definition.path === "updates_auto_check" &&
                          updateControls}
                      </Fragment>
                    ))}
                </div>
              </SettingsGroup>
            ))}
            {section === "settings_advanced" && advanced && (
              <AdvancedDeveloperLogPanel theme={theme} />
            )}
            {section === "settings_advanced" && (
              <footer className="settings-footer">
                <Button variant="danger"
                  type="button"
                  className="danger"
                  onClick={() => setResetConfirm(true)}
                >
                  אפס הגדרות
                </Button>
                <small>
                  מאפס גם מפתחות, הרשאות כלים, תיקיות והגדרות מפתחים; לפני
                  האיפוס נוצר גיבוי.
                </small>
              </footer>
            )}
            {!fields.filter((definition) => !definition.providerWorkflow)
              .length &&
              section !== "settings_ai" && (
                <p className="management-empty">
                  אין הגדרות להצגה במצב הנוכחי.
                </p>
              )}
          </>
        )}
      </div>
      {resetConfirm && (
        <ConfirmDialog
          title="איפוס הגדרות"
          description="לאפס את כל ההגדרות וההרשאות לברירת המחדל של סמארטי? הפעולה תאפס גם מפתחות, הרשאות כלים, טבלת יכולות, תיקיות והגדרות מפתחים. ייווצר גיבוי לקובץ ההגדרות הנוכחי."
          confirmLabel="אפס"
          danger
          onCancel={() => setResetConfirm(false)}
          onConfirm={resetSettings}
        />
      )}
    </div>
  );
}
