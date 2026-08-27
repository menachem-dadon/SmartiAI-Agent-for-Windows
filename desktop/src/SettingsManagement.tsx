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
import type { ResolvedTheme, ThemePreference } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import { useDismissiblePopup } from "./popupDismissal";
import {
  capabilityLabels,
  matchingSettings,
  patchForSetting,
  policyOptions,
  providerOptions,
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

function settingNeedsInfo(
  label: string,
  help: string,
  advanced = false,
  forced?: boolean,
) {
  if (forced !== undefined) return forced;
  if (advanced) return true;
  const text = `${label} ${help}`.toLocaleLowerCase("he");
  return [
    "api",
    "imap",
    "smtp",
    "ssl",
    "mcp",
    "shell",
    "tavily",
    "token",
    "port",
    "מפתח",
    "סיסמת",
    "שרת",
    "פורט",
    "ארגז חול",
    "הרשאות",
    "אוטונומי",
    "אישור",
    "חיבור",
    "כלים חיצוניים",
    "תאימות",
    "לוג",
    "trace",
    "אודיט",
  ].some((term) => text.includes(term));
}

function SettingsInfoButton({ label, help }: { label: string; help: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="settings-info-wrap"
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <button
        type="button"
        className="settings-info"
        aria-label={`מידע: ${label}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        i
      </button>
      {open && <span role="tooltip">{help}</span>}
    </span>
  );
}

function SourceSettingField({
  label,
  help,
  children,
  className = "",
  dataPath,
  advanced = false,
  info,
}: {
  label: string;
  help: string;
  children: React.ReactNode;
  className?: string;
  dataPath?: string;
  advanced?: boolean;
  info?: boolean;
}) {
  const showInfo = Boolean(
    help && settingNeedsInfo(label, help, advanced, info),
  );
  return (
    <section
      className={`source-settings-field ${className}`.trim()}
      data-setting-path={dataPath}
    >
      <header>
        <b>{label}</b>
        {showInfo && <SettingsInfoButton label={label} help={help} />}
      </header>
      <div className="source-settings-control">{children}</div>
    </section>
  );
}

export function ConfirmDialog({
  title,
  description,
  confirmLabel = "אישור מפורש",
  danger = false,
  onCancel,
  onConfirm,
}: {
  title: string;
  description: string;
  confirmLabel?: string;
  danger?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="legacy-dialog-backdrop" role="presentation">
      <div
        className="legacy-input-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
      >
        <h2>{title}</h2>
        <p>{description}</p>
        <footer>
          <button onClick={onCancel}>ביטול</button>
          <button className={danger ? "danger" : ""} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  );
}

export function InputDialog({
  title,
  label,
  initial = "",
  confirmLabel = "שמירה",
  multiline = true,
  onCancel,
  onConfirm,
}: {
  title: string;
  label: string;
  initial?: string;
  confirmLabel?: string;
  multiline?: boolean;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}) {
  const [value, setValue] = useState(initial);
  return (
    <div
      className="legacy-dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <form
        className="legacy-input-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onSubmit={(event) => {
          event.preventDefault();
          onConfirm(value.trim());
        }}
      >
        <h2>{title}</h2>
        <label>
          {label}
          {multiline ? (
            <textarea
              autoFocus
              dir="auto"
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          ) : (
            <input
              autoFocus
              dir="auto"
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          )}
        </label>
        <footer>
          <button type="button" onClick={onCancel}>
            ביטול
          </button>
          <button type="submit" disabled={!value.trim()}>
            {confirmLabel}
          </button>
        </footer>
      </form>
    </div>
  );
}

export function PageHero({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section className="management-hero">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
        {children}
      </div>
      {actions}
    </section>
  );
}

function SettingRow({
  definition,
  values,
  secrets,
  onSave,
  onSecretChanged,
  schema,
  theme,
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
    setStatus("שומר…");
    try {
      await onSave(definition.path, value);
      setStatus("נשמר");
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
          setStatus("שומר…");
          await onSave(definition.path, next);
          setStatus("נשמר");
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
    const icons = legacyAssets(theme);
    const persistSecret = async (next: string) => {
      setStatus("שומר…");
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
        setStatus(next.trim() ? "נשמר" : "נמחק");
        await onSecretChanged();
      } catch (reason) {
        setStatus(`השמירה נכשלה: ${String(reason)}`);
      }
    };
    const editSecret = (next: string) => {
      setSecret(next);
      setStatus("שומר…");
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
          <input
            type="password"
            autoComplete="new-password"
            value={secret}
            onChange={(event) => editSecret(event.target.value)}
            placeholder={
              state.configured
                ? `מוגדר · ${state.masked || "••••"}`
                : "הדבקת ערך חדש"
            }
          />
          <button
            className="icon-control"
            type="button"
            title="הדבק מפתח מלוח ההעתקה"
            aria-label="הדבק מפתח מלוח ההעתקה"
            onClick={() => void paste()}
          >
            <LegacyIcon src={icons.paste} size={19} />
          </button>
          <button
            className="icon-control"
            type="button"
            title="מחק מפתח שמור"
            aria-label="מחק מפתח שמור"
            disabled={!secret && !state.configured}
            onClick={() => editSecret("")}
          >
            <LegacyIcon src={icons.delete} size={17} />
          </button>
          {help?.help_url && (
            <button
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
            </button>
          )}
        </div>
        {help?.key_instructions && (
          <small className="secret-instructions">{help.key_instructions}</small>
        )}
        {status && (
          <small role="status" className="settings-status">
            {status}
          </small>
        )}
      </SourceSettingField>
    );
  }
  if (definition.control === "directory") {
    const icons = legacyAssets(theme);
    const clear = async () => {
      setDraft("");
      setStatus("שומר…");
      await onSave(definition.path, definition.multiple ? [] : "");
      setStatus("נשמר");
    };
    return (
      <SourceSettingField {...sourceProps}>
        <div className="source-directory-picker">
          <input readOnly dir="ltr" value={draft} />
          <button
            type="button"
            title={definition.multiple ? "הוסף תיקייה" : "בחר תיקייה"}
            aria-label={definition.multiple ? "הוסף תיקייה" : "בחר תיקייה"}
            onClick={() => void choosePath()}
          >
            <LegacyIcon src={icons.folder} size={20} />
          </button>
        </div>
        {definition.multiple && (
          <button
            type="button"
            className="source-clear-paths"
            onClick={() => void clear()}
          >
            נקה
          </button>
        )}
        {status && <small role="status">{status}</small>}
      </SourceSettingField>
    );
  }
  if (definition.control === "switch") {
    const showInfo = settingNeedsInfo(
      definition.label,
      definition.help,
      Boolean(definition.advanced),
      definition.info,
    );
    return (
      <section
        className={`source-settings-field source-checkbox-field${controlDisabled ? " is-disabled" : ""}`}
        data-setting-path={definition.path}
      >
        <label>
          <span className="source-switch">
            <input
              type="checkbox"
              checked={Boolean(raw)}
              disabled={controlDisabled}
              onChange={(event) => {
                setStatus("שומר…");
                void onSave(definition.path, event.target.checked)
                  .then(() => setStatus("נשמר"))
                  .catch((reason) => setStatus(String(reason)));
              }}
            />
            <span />
          </span>
          <b>{definition.label}</b>
          {showInfo && (
            <SettingsInfoButton
              label={definition.label}
              help={definition.help}
            />
          )}
        </label>
        {status && <small role="status">{status}</small>}
      </section>
    );
  }
  if (definition.control === "segmented") {
    const icons = legacyAssets(theme);
    const optionIcon = (value: string | number) =>
      value === "locked_down"
        ? icons.autonomySafe
        : value === "balanced"
          ? icons.autonomy
          : value === "max_autonomy"
            ? icons.autonomyFull
            : "";
    return (
      <SourceSettingField {...sourceProps}>
        <div className="source-segmented">
          {definition.options?.map((option) => (
            <button
              type="button"
              key={String(option.value)}
              className={
                String(raw ?? "") === String(option.value) ? "active" : ""
              }
              onClick={() => {
                setStatus("שומר…");
                void onSave(definition.path, option.value)
                  .then(() => setStatus("נשמר"))
                  .catch((reason) => setStatus(String(reason)));
              }}
            >
              {optionIcon(option.value) && (
                <LegacyIcon src={optionIcon(option.value)} size={18} />
              )}
              <span>{option.label}</span>
            </button>
          ))}
        </div>
        {status && <small role="status">{status}</small>}
      </SourceSettingField>
    );
  }
  if (definition.control === "select")
    return (
      <SourceSettingField {...sourceProps}>
        <select
          value={String(raw ?? "")}
          onChange={(event) => {
            setStatus("שומר…");
            void onSave(definition.path, event.target.value)
              .then(() => setStatus("נשמר"))
              .catch((reason) => setStatus(String(reason)));
          }}
        >
          {definition.options?.map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </select>
        {status && <small role="status">{status}</small>}
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
        <div>
          <input
            type="range"
            min={definition.min}
            max={definition.max}
            step={definition.step || 1}
            value={draft || definition.min || 0}
            onChange={(event) => setDraft(event.target.value)}
            onPointerUp={() => void saveDraft()}
            onKeyUp={() => void saveDraft()}
          />
          <output>{rangeLabel}</output>
        </div>
        {status && <small role="status">{status}</small>}
      </SourceSettingField>
    );
  }
  return (
    <SourceSettingField {...sourceProps}>
      <div>
        <input
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
          <button type="button" onClick={() => void choosePath()}>
            בחירה
          </button>
        )}
      </div>
      {status && <small role="status">{status}</small>}
    </SourceSettingField>
  );
}

function SearchableModelPicker({
  models,
  selected,
  loading,
  favorites,
  theme,
  onSelect,
  onToggleFavorite,
}: {
  models: string[];
  selected: string;
  loading: boolean;
  favorites: Json[];
  theme: ResolvedTheme;
  onSelect: (model: string) => Promise<void>;
  onToggleFavorite: (model: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const root = useRef<HTMLDivElement | null>(null);
  const icons = legacyAssets(theme);
  const allModels = useMemo(
    () => [...new Set([selected, ...models])].filter(Boolean),
    [models, selected],
  );
  const filtered = useMemo(() => {
    const terms = query
      .toLocaleLowerCase("en")
      .split(/[^a-z0-9]+/)
      .filter(Boolean);
    if (!terms.length) return allModels;
    return allModels.filter((model) => {
      const normalized = model
        .toLocaleLowerCase("en")
        .replace(/[^a-z0-9]+/g, " ");
      const compact = normalized.replace(/ /g, "");
      return terms.every(
        (term) => normalized.includes(term) || compact.includes(term),
      );
    });
  }, [allModels, query]);
  useDismissiblePopup({
    open,
    roots: [root],
    onDismiss: () => setOpen(false),
  });
  if (loading)
    return (
      <div className="source-model-loading" role="status">
        <span aria-hidden="true" />
        טוען מודלים...
      </div>
    );
  return (
    <div className="source-model-picker" ref={root}>
      <button
        type="button"
        className="source-model-picker-current"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {selected || "לא נמצאו מודלים"}
        <i aria-hidden="true" />
      </button>
      {open && (
        <div className="source-model-popup">
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false);
              if (event.key === "Enter" && filtered[0]) {
                void onSelect(filtered[0]);
                setOpen(false);
              }
            }}
            placeholder="חפש מודל"
            aria-label="חפש מודל"
          />
          <div role="listbox" aria-label="מודלים">
            {filtered.length ? (
              filtered.slice(0, 250).map((model) => {
                const favorite = favorites.some(
                  (item) => item.provider && item.model === model,
                );
                return (
                  <div
                    className={model === selected ? "selected" : ""}
                    key={model}
                  >
                    <button
                      type="button"
                      className="source-model-star"
                      title={favorite ? "הסר מהמועדפים" : "הוסף למועדפים"}
                      aria-label={`${favorite ? "הסר" : "הוסף"} ${model} ${favorite ? "מהמועדפים" : "למועדפים"}`}
                      onClick={() => void onToggleFavorite(model)}
                    >
                      <LegacyIcon
                        src={favorite ? icons.starFilled : icons.starEmpty}
                        size={18}
                      />
                    </button>
                    <button
                      type="button"
                      role="option"
                      aria-selected={model === selected}
                      onClick={() => {
                        void onSelect(model);
                        setOpen(false);
                      }}
                    >
                      {model}
                    </button>
                  </div>
                );
              })
            ) : (
              <p>לא נמצאו מודלים</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
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
  const [keyDraft, setKeyDraft] = useState("");
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
  const icons = legacyAssets(theme);
  const refreshModels = useCallback(async () => {
    setModelsLoading(true);
    try {
      const data = await coreApi<{
        models: Array<string | { id?: string; name?: string }>;
        message?: string;
      }>("GET", `/v2/providers/${encodePath(provider)}/models`);
      setModels(
        data.models
          .map((item) =>
            typeof item === "string" ? item : item.id || item.name || "",
          )
          .filter(Boolean),
      );
      if (data.message) setStatus(data.message);
    } catch (reason) {
      setModels(selectedModel ? [selectedModel] : []);
      setStatus(String(reason));
    } finally {
      setModelsLoading(false);
    }
  }, [provider, selectedModel]);
  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);
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
    void save(
      "favorite_models",
      [{ provider, model }, ...favorites].slice(0, 60),
    );
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
      setStatus(`מפתח תקין ושמור: ${secrets[secretKey]?.masked || "••••"}`);
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
        <select
          value={provider}
          onChange={(event) => {
            const next = event.target.value;
            if (next !== provider) favoriteOnLoadProvider.current = next;
            void save("api_mode", next);
          }}
        >
          {providerOptions.map((option) => (
            <option key={String(option.value)} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </select>
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
              <input
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
              <button
                className="icon-control"
                type="button"
                title="הדבק מפתח מלוח ההעתקה"
                aria-label="הדבק מפתח מלוח ההעתקה"
                onClick={() => void pasteKey()}
              >
                <LegacyIcon src={icons.paste} size={19} />
              </button>
              <button
                className="icon-control"
                type="button"
                title="מחק מפתח שמור"
                aria-label="מחק מפתח שמור"
                disabled={!keyDraft && !configured?.configured}
                onClick={() => void removeKey()}
              >
                <LegacyIcon src={icons.delete} size={17} />
              </button>
              {providerMetadata?.help_url && (
                <button
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
                </button>
              )}
            </div>
          </SourceSettingField>
          <p role="status" className="settings-status">
            {status ||
              (configured?.configured
                ? `מפתח שמור: ${configured.masked}`
                : "לא נשמר מפתח.")}
          </p>
          {providerMetadata?.key_instructions && (
            <p className="secret-instructions">
              {providerMetadata.key_instructions}
            </p>
          )}
          <div className="source-field-actions">
            <button
              type="button"
              disabled={!keyDraft.trim()}
              onClick={() => void validateAndSaveKey()}
            >
              בדיקה ושמירה
            </button>
            <button type="button" onClick={() => void validateExisting()}>
              בדיקת החיבור
            </button>
          </div>
        </>
      )}
      {provider === "local" && (
        <SourceSettingField
          label="מפתח גישה לספק המודל"
          help="מפתח API אינו נדרש כאשר משתמשים בשרת מודל מקומי."
          dataPath="provider_api_key"
        >
          <div className="secret-link-row">
            <input
              type="password"
              disabled
              placeholder="לא נדרש מפתח למודל מקומי"
            />
            <button
              className="icon-control"
              type="button"
              title="הדבק מפתח מלוח ההעתקה"
              aria-label="הדבק מפתח מלוח ההעתקה"
              disabled
            >
              <LegacyIcon src={icons.paste} size={19} />
            </button>
            <button
              className="icon-control"
              type="button"
              title="מחק מפתח שמור"
              aria-label="מחק מפתח שמור"
              disabled
            >
              <LegacyIcon src={icons.delete} size={17} />
            </button>
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
            <p className="settings-status">
              {status || "יש לבחור OpenAI Codex Sign-in כדי להתחבר."}
            </p>
            <div className="inline-actions codex-actions">
              <button
                className="primary"
                onClick={() => void codexAction("codex_login")}
              >
                התחבר עם
                <br />
                ChatGPT / Codex
              </button>
              <button onClick={() => void codexAction("codex_check")}>
                בדוק
                <br />
                חיבור
              </button>
              <button onClick={() => void codexAction("codex_logout")}>
                התנתק
              </button>
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
          <select
            value={reasoning.reasoning_effort || "auto"}
            onChange={(event) =>
              void coreApi<typeof reasoning>(
                "POST",
                `/v2/providers/${encodePath(provider)}/reasoning`,
                { model: selectedModel, effort: event.target.value },
                true,
              ).then(setReasoning)
            }
          >
            {reasoning.reasoning_options.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
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
            <div className="source-segmented">
              {policyOptions.map((option) => (
                <button
                  type="button"
                  key={String(option.value)}
                  className={
                    String(matrix[key] || "ask") === String(option.value)
                      ? "active"
                      : ""
                  }
                  onClick={() =>
                    void save("policy_matrix", {
                      ...matrix,
                      [key]: option.value,
                    })
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          </SourceSettingField>
        ))}
      </div>
    </div>
  );
}

function AdvancedDeveloperLogPanel({ theme }: { theme: ResolvedTheme }) {
  const [lines, setLines] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [limit, setLimit] = useState(500);
  const [exportLimit, setExportLimit] = useState(1000);
  const [hidePersonal, setHidePersonal] = useState(true);
  const [status, setStatus] = useState("טוען את הלוג המאוחד…");
  const [confirmClear, setConfirmClear] = useState(false);
  const icons = legacyAssets(theme);
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
    setConfirmClear(false);
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
    } catch (reason) {
      setStatus(`ניקוי הלוג נכשל: ${String(reason)}`);
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
          <button type="button" onClick={() => void load()}>
            רענן לוגים
          </button>
          <button type="button" disabled={limit >= 20_000} onClick={loadOlder}>
            טען 500 שורות קודמות
          </button>
          <button
            type="button"
            className="icon-control"
            title="ייצוא הלוג לקובץ טקסט"
            aria-label="ייצוא הלוג לקובץ טקסט"
            onClick={() => void exportLog()}
          >
            <LegacyIcon src={icons.exportJson} size={20} />
          </button>
          <button type="button" onClick={() => setConfirmClear(true)}>
            נקה לוג
          </button>
        </div>
        <div className="source-log-export">
          <label>
            כמות שורות לייצוא
            <select
              value={exportLimit}
              onChange={(event) => setExportLimit(Number(event.target.value))}
            >
              <option value="500">500 שורות אחרונות</option>
              <option value="1000">1,000 שורות אחרונות</option>
              <option value="2500">2,500 שורות אחרונות</option>
              <option value="5000">5,000 שורות אחרונות</option>
              <option value="10000">10,000 שורות אחרונות</option>
              <option value="0">כל הלוגים השמורים</option>
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={hidePersonal}
              onChange={(event) => setHidePersonal(event.target.checked)}
            />
            הסתר תוכן אישי
          </label>
        </div>
        <small role="status">{status}</small>
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
          onConfirm={() => void clearLog()}
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
  const [testing, setTesting] = useState(false);
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
      setStatus(result.message);
    } catch (reason) {
      setTested(false);
      setStatus(
        `הבדיקה נכשלה ולא בוצע מעבר אוטומטי למצב פחות בטוח: ${String(reason)}`,
      );
    } finally {
      setTesting(false);
    }
  };
  const persist = async () => {
    if (mode === "custom_ca" && !customPath) {
      setStatus("יש לבחור תחילה תעודת שורש ציבורית תקינה.");
      return;
    }
    if (mode === "legacy_insecure") {
      if (!ack) {
        setStatus("יש לאשר שהמשמעות של כיבוי אימות תעודות HTTPS ברורה.");
        return;
      }
      if (
        !window.confirm(
          "הבחירה מכבה באופן רחב את אימות תעודות HTTPS ב-Smarti ובכלים שמופעלים ממנו. להחיל את המצב הפחות בטוח?",
        )
      )
        return;
    }
    await saveValues({
      ssl_trust_mode: mode,
      ssl_custom_ca_path: customPath,
      ssl_filter_setup_completed: tested,
      ssl_legacy_insecure_allowed_hosts: [],
      ssl_trust_migration_version: 1,
      allow_insecure_ssl_compat: mode === "legacy_insecure",
    });
    setExpanded(false);
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
        <button
          type="button"
          onClick={() => {
            if (!expanded) resetEditor();
            setExpanded((value) => !value);
          }}
        >
          {expanded ? "ביטול" : "הגדר"}
          <i aria-hidden="true" />
        </button>
      </header>
      {expanded && (
        <div className="source-ssl-editor">
          <h3>בחירת דרך החיבור המאובטח</h3>
          <p>
            בכל חיבור HTTPS, סמארטי בודק את זהות השרת. ברשת עם סינון מומלץ
            להתחיל במאגר האישורים של Windows. רק אם האפשרות הזו אינה עובדת, אפשר
            לייבא תעודת שורש ציבורית שהתקבלה מספק הסינון.
          </p>
          <div className="source-segmented">
            {[
              ["system", "מאגר Windows"],
              ["custom_ca", "תעודה"],
              ["legacy_insecure", "ללא אימות"],
            ].map(([value, label]) => (
              <button
                type="button"
                key={value}
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
              </button>
            ))}
          </div>
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
                  <input
                    readOnly
                    dir="ltr"
                    value={customPath}
                    placeholder="לא נבחרה תעודה"
                  />
                  <button
                    type="button"
                    onClick={() => void chooseCertificate()}
                  >
                    בחירת תעודה
                  </button>
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
                <label className="danger-ack">
                  <input
                    type="checkbox"
                    checked={ack}
                    onChange={(event) => setAck(event.target.checked)}
                  />
                  ברור לי שבמצב זה אימות תעודות HTTPS כבוי בכל רכיבי Smarti
                </label>
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
              <button
                type="button"
                disabled={testing}
                onClick={() => void test()}
              >
                בדיקת חיבור
              </button>
              <span role="status">{status}</span>
            </div>
          </section>
          <footer>
            <button
              type="button"
              disabled={testing}
              onClick={() => {
                resetEditor();
                setExpanded(false);
              }}
            >
              ביטול
            </button>
            <button
              type="button"
              disabled={testing}
              onClick={() => void persist()}
            >
              שמירה והחלה
            </button>
          </footer>
        </div>
      )}
    </section>
  );
}

export function SettingsView({
  section,
  setTheme,
  theme,
  onNavigate,
  updateControls,
}: {
  section: SettingsSection;
  setTheme: (theme: ThemePreference) => void;
  theme: ResolvedTheme;
  onNavigate?: (section: SettingsSection) => void;
  updateControls?: React.ReactNode;
}) {
  const [data, setData] = useState<SafeSettings>({ values: {}, secrets: {} });
  const [schema, setSchema] = useState<SettingsSchema>({
    providers: [],
    secret_help: {},
  });
  const [ttsVoices, setTtsVoices] = useState<
    Array<{ value: string; label: string }>
  >([]);
  const [query, setQuery] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [saveStatus, setSaveStatus] = useState("מוכן");
  const [policyOpen, setPolicyOpen] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [pendingFocus, setPendingFocus] = useState("");
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [ttsPreviewText, setTtsPreviewText] = useState(
    "שלום, זו תצוגה מקדימה של הקול הנוכחי.",
  );
  const [emailTestStatus, setEmailTestStatus] = useState(
    "הבדיקה תרוץ רק בלחיצה.",
  );
  const load = useCallback(
    async () => setData(await coreApi<SafeSettings>("GET", "/v2/settings")),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    void coreApi<SettingsSchema>("GET", "/v2/settings/schema").then(setSchema);
  }, []);
  useEffect(() => {
    void coreApi<{ items: Array<{ id: string; name: string }> }>(
      "GET",
      "/v2/audio/tts/voices",
    ).then((data) =>
      setTtsVoices(
        data.items.map((item) => ({ value: item.id, label: item.name })),
      ),
    );
  }, []);
  useEffect(() => setPolicyOpen(false), [section]);
  useEffect(() => {
    const raw = data.values.settings_recent_searches;
    if (Array.isArray(raw))
      setRecentSearches(raw.map(String).filter(Boolean).slice(0, 8));
    setAdvanced(
      Boolean(
        (data.values.ui_preferences as Json | undefined)
          ?.settings_show_advanced,
      ),
    );
  }, [data.values.settings_recent_searches, data.values.ui_preferences]);
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
    setSaveStatus("שומר…");
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
    const persisted = await coreApi<SafeSettings>(
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
    setSaveStatus("נשמר");
  };
  const saveValues = async (values: Json) => {
    setSaveStatus("שומר…");
    const persisted = await coreApi<SafeSettings>(
      "PATCH",
      "/v2/settings",
      { values },
      true,
    );
    setData(persisted);
    setSaveStatus("נשמר");
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
  const previewTts = async () => {
    await coreApi("POST", "/v2/audio/tts", { text: ttsPreviewText }, true);
    setSaveStatus("מנגן תצוגה מקדימה…");
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
    } catch (reason) {
      setSaveStatus(`האיפוס נכשל: ${String(reason)}`);
    } finally {
      setResetConfirm(false);
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
    setAdvanced(checked);
    const preferences =
      data.values.ui_preferences &&
      typeof data.values.ui_preferences === "object"
        ? (data.values.ui_preferences as Json)
        : {};
    await save("ui_preferences", {
      ...preferences,
      settings_show_advanced: checked,
    });
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
  const icons = legacyAssets(theme);
  return (
    <div className="management-page settings-page source-settings-page">
      <div className="source-settings-head">
        <div className="source-save-state" role="status">
          <LegacyIcon src={icons.saveDone} size={18} />
          <span>
            {saveStatus === "מוכן" ? "אין שינויים חדשים" : saveStatus}
          </span>
        </div>
        <div className="source-advanced-pill">
          <span>הצג הגדרות מתקדמות</span>
          <label className="source-switch">
            <input
              type="checkbox"
              checked={advanced}
              title="מציג שדות טכניים כמו פורטים, SSL, מגבלות זמן, לוגים ומטריצת הרשאות."
              aria-label="הצג הגדרות מתקדמות"
              onChange={(event) =>
                void setAdvancedPersisted(event.target.checked)
              }
            />
            <span />
          </label>
        </div>
      </div>
      <div className="source-settings-search">
        <LegacyIcon src={icons.search} size={26} />
        <input
          value={query}
          onChange={(event) => {
            setPolicyOpen(false);
            setQuery(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && fields[0]) {
              event.preventDefault();
              void activateSearchResult(fields[0]);
            }
          }}
          placeholder="חפש הגדרה"
        />
      </div>
      <div className="source-settings-scroll">
        {!query && (
          <header className="source-settings-section-title">
            <h2>{policyOpen ? "שליטה מתקדמת ביכולות" : title.title}</h2>
            <span />
          </header>
        )}
        {query ? (
          <div className="source-search-results">
            <p>
              {fields.length
                ? `נמצאו ${fields.length} תוצאות. לחיצה תפתח ותסמן את ההגדרה.`
                : "לא נמצאו הגדרות. נסה מילה קרובה כמו מודל, קול, אימייל, אבטחה או תיקייה."}
            </p>
            {fields.slice(0, 40).map((definition) => (
              <button
                type="button"
                key={`${definition.section}:${definition.path}`}
                onClick={() => void activateSearchResult(definition)}
              >
                <b>{definition.label}</b>
                <small>
                  {settingsSectionTitles[definition.section].title}
                  {definition.advanced ? "  ·  מתקדם" : ""}
                </small>
              </button>
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
              <section className="source-settings-section" key={group}>
                {section !== "settings_ai" && <h3>{group}</h3>}
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
                              <button
                                type="button"
                                className="source-secondary-button"
                                onClick={() => setPolicyOpen(true)}
                              >
                                <LegacyIcon src={icons.policy} size={18} />
                                הגדרת התאמה אישית
                              </button>
                            </SourceSettingField>
                          )}
                        {definition.path === "email_password" && (
                          <SourceSettingField
                            label="בדיקת חיבור אימייל"
                            help="בודק התחברות ל-IMAP ול-SMTP לפי הפרטים שהוזנו. הבדיקה לא שולחת הודעה."
                            dataPath="email_connection_test"
                          >
                            <div className="source-email-test">
                              <span role="status">{emailTestStatus}</span>
                              <button
                                type="button"
                                className="source-secondary-button"
                                onClick={() => void testEmail()}
                              >
                                <LegacyIcon
                                  src={icons.connectionTest}
                                  size={18}
                                />
                                בדוק חיבור
                              </button>
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
                              <input
                                value={ttsPreviewText}
                                onChange={(event) =>
                                  setTtsPreviewText(event.target.value)
                                }
                              />
                              <button
                                type="button"
                                className="source-secondary-button"
                                onClick={() => void previewTts()}
                              >
                                <LegacyIcon src={icons.speaker} size={18} />
                                השמע
                              </button>
                            </div>
                          </SourceSettingField>
                        )}
                        {definition.path === "updates_auto_check" &&
                          updateControls}
                      </Fragment>
                    ))}
                </div>
              </section>
            ))}
            {section === "settings_advanced" && advanced && (
              <AdvancedDeveloperLogPanel theme={theme} />
            )}
            {section === "settings_advanced" && (
              <footer className="settings-footer">
                <button
                  type="button"
                  className="danger"
                  onClick={() => setResetConfirm(true)}
                >
                  אפס הגדרות
                </button>
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
          onConfirm={() => void resetSettings()}
        />
      )}
    </div>
  );
}
