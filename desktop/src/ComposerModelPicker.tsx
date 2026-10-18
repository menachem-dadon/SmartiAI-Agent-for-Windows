import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button, DesignSystemProvider, HoverLabel, Icon, IconButton, Tooltip } from "./design-system";
import type { ReasoningOption } from "./chatTypes";
import type { ResolvedTheme } from "./designSystem";
import { providerOptions } from "./managementCatalog";
import { ProviderIcon } from "./ProviderIcon";
import { useDismissiblePopup } from "./popupDismissal";
import { useModelMenuPosition } from "./modelMenuPosition";
import { modelDisplayName, reasoningDisplayName, reasoningModeOptions } from "./modelPresentation";
import { ReasoningBudgetControl } from "./ReasoningBudgetControl";

type Favorite = { provider: string; model: string };
type View = "effort" | "models";
type Props = {
  theme: ResolvedTheme; provider: string; model: string; favoriteModels: Favorite[];
  reasoningEffort: string; reasoningOptions: ReasoningOption[]; quota?: ReactNode;
  onOpen: () => void; onFavoriteModel: (item: Favorite) => void | Promise<void>;
  onReasoningEffort: (effort: string) => void | Promise<void>;
  onManageModels?: (trigger?: HTMLElement) => void;
  onSelected?: () => void;
};
const providerName = (value: string) => providerOptions.find(option => option.value === value)?.label || value;

function ReasoningSlider({ value, options, onChange, onPreviewChange }: {
  value: string; options: ReasoningOption[]; onChange: Props["onReasoningEffort"]; onPreviewChange: (value: string | null) => void;
}) {
  const slider = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState({ thumb: false, stop: -1 });
  const dragging = useRef(false), preview = useRef<string | null>(null), dragStart = useRef(value);
  const index = options.findIndex(option => option.value === value);
  const commitDrag = () => {
    if (!dragging.current) return;
    dragging.current = false;
    const next = preview.current;
    if (next !== null && next !== dragStart.current) void onChange(next);
  };
  return <div className="model-effort-control" dir="ltr">
    <div ref={slider} className="model-effort-slider" style={{ "--model-effort-position": options.length > 1 ? Math.max(0, index) / (options.length - 1) : 0 } as CSSProperties}
      onPointerLeave={() => setHover({ thumb: false, stop: -1 })}
      onPointerMove={event => {
        if (event.pointerType === "touch" || !slider.current) return;
        const rect = slider.current.getBoundingClientRect(), thumb = slider.current.querySelector<HTMLElement>(".model-effort-thumb")!.getBoundingClientRect();
        const half = parseFloat(getComputedStyle(slider.current).getPropertyValue("--model-effort-thumb-size")) / 2;
        const step = options.length > 1 ? (rect.width - 2 * half) / (options.length - 1) : 0;
        const stop = step > 0 ? Math.max(0, Math.min(options.length - 1, Math.round((event.clientX - rect.left - half) / step))) : 0;
        const next = { thumb: event.clientX >= thumb.left && event.clientX <= thumb.right && event.clientY >= thumb.top && event.clientY <= thumb.bottom,
          stop: Math.abs(event.clientX - rect.left - half - stop * step) <= 10 && Math.abs(event.clientY - rect.top - rect.height / 2) <= 12 ? stop : -1 };
        setHover(current => current.thumb === next.thumb && current.stop === next.stop ? current : next);
      }}>
      <span className="model-effort-track" aria-hidden="true"><span className="model-effort-fill" /></span>
      <span className={`model-effort-thumb${hover.thumb ? " is-hovered" : ""}`} aria-hidden="true" />
      <input className="model-effort-input" type="range" aria-label="עוצמת חשיבה" aria-valuetext={reasoningDisplayName(value, options)}
        min={0} max={Math.max(0, options.length - 1)} step={1} value={Math.max(0, index)} disabled={options.length < 2 || index < 0}

        onPointerDown={event => { dragging.current = true; dragStart.current = value; preview.current = null; event.currentTarget.setPointerCapture?.(event.pointerId); }}
        onPointerUp={commitDrag} onPointerCancel={commitDrag} onLostPointerCapture={commitDrag}
        onChange={event => {
          const next = options[event.currentTarget.valueAsNumber]?.value;
          if (!next) return;
          preview.current = next; onPreviewChange(next);
          if (!dragging.current) void onChange(next);
        }} />
      <span className="model-effort-stops" aria-hidden="true">{options.map((option, i) =>
        <i key={option.value} style={{ "--model-effort-stop-position": options.length > 1 ? i / (options.length - 1) : 0 } as CSSProperties} className={`${i <= index ? "is-filled" : ""}${i === index ? " is-current" : ""}${i === hover.stop ? " is-hovered" : ""}`} />)}</span>
    </div>
    <output className="sds-visually-hidden" aria-live="polite">{reasoningDisplayName(value, options)}</output>
  </div>;
}

export function ComposerModelPicker({ theme, provider, model, favoriteModels, reasoningEffort: savedEffort, reasoningOptions: suppliedOptions, quota, onOpen, onFavoriteModel, onReasoningEffort, onManageModels, onSelected }: Props) {
  const root = useRef<HTMLSpanElement>(null), trigger = useRef<HTMLButtonElement>(null), popup = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View | null>(null), [present, setPresent] = useState(false);
  const [previewEffort, setPreviewEffort] = useState<string | null>(null);
  const reasoningOptions = reasoningModeOptions(previewEffort ?? savedEffort, suppliedOptions);
  const reasoningEffort = reasoningOptions.some(option => option.value === savedEffort) ? savedEffort
    : reasoningOptions.find(option => option.value === "medium" || option.value === "budget:medium")?.value || reasoningOptions[0]?.value || "";
  const effortRevision = useRef(0), mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { ++effortRevision.current; setPreviewEffort(null); }, [provider, model]);
  const saveEffort = (effort: string) => {
    const revision = ++effortRevision.current, change = onReasoningEffort;
    setPreviewEffort(effort);
    // App owns persistence order. Deliver every intent immediately so a pending
    // write never delays the next optimistic selection or captures another model.
    const operation = Promise.resolve().then(() => change(effort));
    return operation.finally(() => {
      if (mounted.current && revision === effortRevision.current) setPreviewEffort(null);
    });
  };
  const lastView = useRef<View>("effort"), [browsedProvider, setBrowsedProvider] = useState(provider);
  const [metrics, setMetrics] = useState({ width: 360, row: 44, header: 48, quota: 76, effort: 128, local: 0, note: 44 });
  const id = useId(), open = view !== null;
  if (view) lastView.current = view;
  const shownView = view || lastView.current;
  const menuModels = provider && model && !favoriteModels.some(item => item.provider === provider && item.model === model)
    ? [{ provider, model }, ...favoriteModels] : favoriteModels;
  const providers = Array.from(new Set(menuModels.map(item => item.provider)));
  const shownProvider = providers.includes(browsedProvider) ? browsedProvider : providers[0] || "";
  const rowCount = Math.min(7, Math.max(1, providers.length, ...providers.map(p => menuModels.filter(item => item.provider === p).length)));
  const preferredHeight = shownView === "effort" ? metrics.effort + metrics.local + (quota ? metrics.quota : 0)
    : metrics.header + rowCount * (metrics.row + 2) + 22 + (quota ? metrics.quota : 0) + (!favoriteModels.length ? metrics.note : 0);
  const bounds = useModelMenuPosition(open || present, trigger, preferredHeight, shownView === "effort" ? 280 : metrics.width, shownView === "effort");
  const close = (restoreFocus = false) => { setView(null); if (restoreFocus) trigger.current?.focus(); };
  useDismissiblePopup({ open, roots: [root, popup], onDismiss: () => close() });
  useEffect(() => {
    if (open) { setPresent(true); return; }
    const duration = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0
      : parseFloat(getComputedStyle(root.current!).getPropertyValue("--sds-motion-menu")) || 160;
    const timer = window.setTimeout(() => setPresent(false), duration);
    return () => clearTimeout(timer);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const outsideFocus = (event: FocusEvent) => {
      if (!root.current?.contains(event.target as Node) && !popup.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("focusin", outsideFocus);
    return () => document.removeEventListener("focusin", outsideFocus);
  }, [open]);
  useLayoutEffect(() => {
    if (!view) return;
    const focus = view === "effort" ? '.model-effort-model'
      : '.model-menu-models [aria-checked="true"], .model-menu-providers [aria-pressed="true"]';
    (popup.current?.querySelector<HTMLElement>(focus) || popup.current?.querySelector<HTMLElement>("button"))?.focus();
  }, [view]);
  useLayoutEffect(() => {
    if (!open || !popup.current) return;
    const measure = () => {
      const node = popup.current!;
      const widths = Array.from(node.querySelectorAll<HTMLElement>(".model-menu-width-labels bdi")).map(label => label.offsetWidth);
      const height = (selector: string, fallback: number) => node.querySelector<HTMLElement>(selector)?.offsetHeight || fallback;
      const next = { width: Math.max(280, Math.min(460, Math.max(0, ...widths) + 120)),
        row: Math.max(40, ...Array.from(node.querySelectorAll<HTMLElement>(".model-menu-list button")).map(button => button.offsetHeight)), header: height(".model-menu-title", 48),
        quota: height(".model-picker-quota", 50) + (parseFloat(getComputedStyle(node.querySelector(".model-picker-quota") || node).marginTop) || 0), effort: height(".model-effort-content", 76) + 20,
        local: node.querySelector(".model-picker-local-controls") ? height(".model-picker-local-controls", 0) + 4 : 0, note: height(".model-menu-empty", 36) + 8 };
      setMetrics(current => Object.keys(next).every(key => current[key as keyof typeof next] === next[key as keyof typeof next]) ? current : next);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    for (const node of popup.current.querySelectorAll(".model-menu-width-labels, .model-effort-content, .model-menu-title, .model-picker-quota, .model-picker-local-controls")) observer?.observe(node);
    return () => observer?.disconnect();
  }, [open, shownView, provider, model, favoriteModels, reasoningOptions.length, quota]);
  const keyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (event.key === "Tab") {
      const controls = [...(popup.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") || [])];
      if (target === controls[event.shiftKey ? 0 : controls.length - 1]) close(true);
      return;
    }
    if (shownView !== "models") return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const next = event.key === "ArrowLeft" ? '.model-menu-models [role="menuitemradio"]'
        : '.model-menu-providers [aria-pressed="true"]';
      popup.current?.querySelector<HTMLElement>(next)?.focus(); event.preventDefault();
    } else if (["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key) && target.closest(".model-menu-list")) {
      const buttons = [...target.closest(".model-menu-list")!.querySelectorAll<HTMLButtonElement>("button")];
      const index = buttons.indexOf(target as HTMLButtonElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next]?.focus(); event.preventDefault();
    }
  };
  const name = modelDisplayName(provider, model || provider || "בחר מודל");
  return <span ref={root} className="model-quick-pill">
    <Button ref={trigger} variant="ghost" className="model-picker-trigger" aria-label="בחירת מודל" aria-haspopup="dialog"
      aria-expanded={open} aria-controls={open ? id : undefined} aria-describedby={`${id}-selection`} onClick={() => {
        if (open) close(); else { setBrowsedProvider(provider); setView("effort"); onOpen(); }
      }} onKeyDown={event => {
        if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); setView("effort"); setBrowsedProvider(provider); onOpen(); }
      }}>
      <Icon name="chevron" size={16} /><span id={`${id}-selection`} className="model-picker-trigger-copy" dir="ltr"><HoverLabel text={name} />
        {!!reasoningOptions.length && <span className="model-picker-effort-name">
          <span className="model-picker-effort-width-labels" aria-hidden="true">{reasoningOptions.map(option => <bdi key={option.value}>{reasoningDisplayName(option.value, reasoningOptions)}</bdi>)}</span>
          <bdi>{reasoningDisplayName(previewEffort ?? reasoningEffort, reasoningOptions)}</bdi>
        </span>}</span>
    </Button>
    {(open || present) && createPortal(<DesignSystemProvider theme={theme}><div ref={popup} id={id} role="dialog"
      aria-label={shownView === "effort" ? "מודל ועוצמת חשיבה" : "מודלים מועדפים"} aria-hidden={!open || undefined} inert={!open || undefined}
      className={`model-quick-menu model-picker-frame${!open ? " is-closing" : ""}${bounds && bounds.height < 190 ? " is-tight" : ""}${shownView === "effort" ? " is-effort" : ""}`}
      style={bounds || undefined} onKeyDown={keyDown}>
      <div key={shownView} className={`model-picker-surface${shownView === "effort" ? " model-picker-surface--effort" : ""}`} onAnimationEnd={event => { if (event.target === event.currentTarget && !open) setPresent(false); }}>
        {shownView === "effort" ? <div className="model-effort-content">
          <div className="model-effort-header">
            <Button variant="ghost" className="model-effort-model" aria-label="פתיחת המודלים המועדפים" onClick={() => setView("models")}>
              {!!reasoningOptions.length && <bdi className="model-effort-value">{reasoningDisplayName(previewEffort ?? reasoningEffort, reasoningOptions)}</bdi>}
              <span className="model-effort-model-name"><HoverLabel text={name} /><Icon name="chevron" size={14} /></span>
            </Button>
            {onManageModels && <IconButton label="הגדרות מודלים ומועדפים" icon="settings" variant="ghost" tooltip={false}
              onClick={() => { close(); onManageModels(trigger.current || undefined); }} />}
          </div>
          {!!reasoningOptions.length && <ReasoningSlider key={`${provider}:${model}`} value={previewEffort ?? reasoningEffort} options={reasoningOptions} onChange={saveEffort} onPreviewChange={setPreviewEffort} />}
        </div> : <>
          <header className="model-menu-title"><IconButton label="חזרה לעוצמת החשיבה" icon="chevron" variant="ghost" tooltip={false} className="model-menu-back" onClick={() => setView("effort")} />
            <strong>מודלים מועדפים</strong>{onManageModels && <IconButton label="הגדרות מודלים ומועדפים" icon="settings" variant="ghost" tooltip={false}
              onClick={() => { close(); onManageModels(trigger.current || undefined); }} />}</header>
          <div className="model-menu-columns">
            <section className="model-menu-models" aria-label="מודלים של הספק"><div className="model-menu-list" role="menu" aria-label={providerName(shownProvider) || "מודלים"} key={shownProvider}>
              {menuModels.filter(item => item.provider === shownProvider).map(item => <Button variant="ghost" role="menuitemradio"
                aria-checked={item.provider === provider && item.model === model} className={item.provider === provider && item.model === model ? "is-selected" : ""}
                key={`${item.provider}:${item.model}`} onClick={() => { close(true); void onFavoriteModel(item); onSelected?.(); }}>
                <HoverLabel text={modelDisplayName(item.provider, item.model)} /><Icon name="check" className="model-menu-check" /></Button>)}
            </div></section>
            <section className="model-menu-providers" aria-label="ספקים"><div className="model-menu-list">
              {providers.map(p => <Tooltip key={p} label={providerName(p)} placement="right"><Button variant="ghost" aria-label={providerName(p)} aria-pressed={shownProvider === p}
                onMouseEnter={() => setBrowsedProvider(p)} onFocus={() => setBrowsedProvider(p)} onClick={() => setBrowsedProvider(p)}><ProviderIcon value={p} /></Button></Tooltip>)}
            </div></section>
          </div>
          <div className="model-menu-width-labels" aria-hidden="true">{menuModels.map(item => <bdi key={`${item.provider}:${item.model}`}>{modelDisplayName(item.provider, item.model)}</bdi>)}</div>
          {!favoriteModels.length && <p className="model-menu-empty">אפשר להוסיף מודלים מועדפים בהגדרות</p>}
        </>}
        {shownView === "effort" && provider === "local" && suppliedOptions.some(option => option.value.startsWith("budget:")) && <div className="model-picker-local-controls">
          <ReasoningBudgetControl value={previewEffort ?? reasoningEffort} options={suppliedOptions} onChange={saveEffort} />
        </div>}
        {quota && <div className="model-picker-quota">{quota}</div>}
      </div>
    </div></DesignSystemProvider>, document.body)}
  </span>;
}
