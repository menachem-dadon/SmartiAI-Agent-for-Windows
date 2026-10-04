import { cloneElement, createContext, useContext, useEffect, useId, useLayoutEffect, useRef, useState, type ButtonHTMLAttributes, type CSSProperties, type HTMLAttributes, type InputHTMLAttributes, type ReactElement, type ReactNode, type RefObject, type TextareaHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import { designTokenStyle, type DesignTheme } from "./tokens";
import { Icon, IconTheme, IconFamilyContext, type IconFamily, type IconName } from "./icons";
import "./system.css";

type Direction = "rtl" | "ltr";
const DesignContext = createContext<{ theme: DesignTheme; dir: Direction; reduced: boolean; host: HTMLDivElement | null }>({ theme: "light", dir: "rtl", reduced: false, host: null });
export function DesignSystemProvider({ theme, iconFamily = "tabler", dir = "rtl", reducedMotion = false, children, className = "" }: { theme: DesignTheme; iconFamily?: IconFamily; dir?: Direction; reducedMotion?: boolean; children: ReactNode; className?: string }) {
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  return <DesignContext.Provider value={{ theme, dir, reduced: reducedMotion, host }}><IconTheme.Provider value={theme}><IconFamilyContext.Provider value={iconFamily}>
    <div className={`sds-root ${className}`} data-theme={theme} data-reduced-motion={reducedMotion} dir={dir} style={designTokenStyle(theme)}>{children}<div ref={setHost} className="sds-overlay-host" /></div>
  </IconFamilyContext.Provider></IconTheme.Provider></DesignContext.Provider>;
}

function Overlay({ children }: { children: ReactNode }) {
  const { host } = useContext(DesignContext);
  return host ? createPortal(children, host) : null;
}
function useFloating(anchor: RefObject<HTMLElement | null>, open: boolean, width: number) {
  const [position, setPosition] = useState({ top: 0, left: 0, maxHeight: 400, transform: "none" });
  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      if (!anchor.current) return;
      const rect = anchor.current.getBoundingClientRect();
      const actualWidth = Math.min(width, window.innerWidth - 32);
      const below = window.innerHeight - rect.bottom - 24;
      const above = rect.top - 24;
      const useAbove = below < 180 && above > below;
      setPosition({ left: Math.max(16, Math.min(rect.right - actualWidth, window.innerWidth - actualWidth - 16)), top: useAbove ? rect.top - 8 : rect.bottom + 8, maxHeight: Math.max(40, useAbove ? above : below), transform: useAbove ? "translateY(-100%)" : "none" });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, [anchor, open, width]);
  return position;
}

export function Tooltip({ label, children }: { label: string; children: ReactElement<{ "aria-describedby"?: string }> }) {
  const id = useId();
  const anchor = useRef<HTMLSpanElement>(null);
  const [hover, setHover] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const enterHover = () => { clearTimeout(hoverTimer.current); setHover(true); setDismissed(false); };
  const leaveHover = () => { clearTimeout(hoverTimer.current); hoverTimer.current = setTimeout(() => setHover(false), 180); };
  useEffect(() => () => clearTimeout(hoverTimer.current), []);
  const open = (hover || focused) && !dismissed;
  const position = useFloating(anchor, open, 220);
  useEffect(() => {
    if (!open) return;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setDismissed(true); };
    document.addEventListener("keydown", escape, true);
    return () => document.removeEventListener("keydown", escape, true);
  }, [open]);
  const describedBy = [children.props["aria-describedby"], open ? id : undefined].filter(Boolean).join(" ") || undefined;
  return <span className="sds-tooltip-anchor" ref={anchor} onPointerEnter={(event) => { if (event.pointerType !== "touch") enterHover(); }} onPointerLeave={leaveHover} onFocus={() => { setFocused(true); setDismissed(false); }} onBlur={() => setFocused(false)}>
    {cloneElement(children, { "aria-describedby": describedBy })}
    {open && <Overlay><span id={id} role="tooltip" className="sds-tooltip" style={position} onPointerEnter={enterHover} onPointerLeave={leaveHover}>{label}</span></Overlay>}
  </span>;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; icon?: IconName; loading?: boolean };
export function Button({ className = "", variant = "secondary", icon, loading = false, disabled, children, ...props }: ButtonProps) {
  return <button type="button" {...props} disabled={disabled || loading} aria-busy={loading || undefined} className={`sds-button sds-button--${variant} ${className}`}>{loading ? <Icon name="loader" className="sds-spin" /> : icon && <Icon name={icon} />}{children}</button>;
}
export function IconButton({ label, icon, round = false, ...props }: Omit<ButtonProps, "children" | "icon"> & { label: string; icon: IconName; round?: boolean }) {
  return <Tooltip label={label}><Button {...props} aria-label={label} icon={icon} className={`sds-icon-button ${round ? "sds-round" : ""} ${round && props.variant === "primary" ? "sds-main-action" : ""} ${props.className || ""}`} /></Tooltip>;
}

type FieldProps = InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string; ref?: RefObject<HTMLInputElement | null> };
export function Field({ label, hint, error, className = "", id: suppliedId, ...props }: FieldProps) {
  const generatedId = useId();
  const id = suppliedId || generatedId;
  const description = [props["aria-describedby"], hint ? `${id}-hint` : undefined, error ? `${id}-error` : undefined].filter(Boolean).join(" ") || undefined;
  return <div className={`sds-field-group ${className}`}><label htmlFor={id}>{label}</label><input {...props} id={id} className="sds-field" aria-invalid={error ? true : props["aria-invalid"]} aria-describedby={description} />{hint && <p className="sds-hint" id={`${id}-hint`}>{hint}</p>}{error && <p className="sds-field-error" id={`${id}-error`} role="alert">{error}</p>}</div>;
}
export function SearchField(props: Omit<FieldProps, "type">) { return <div className="sds-search"><Icon name="search" /><Field {...props} type="search" /></div>; }
export function NumberField(props: Omit<FieldProps, "type">) { return <Field {...props} type="number" className={`sds-number ${props.className || ""}`} />; }
export function Textarea({ label, hint, error, id: suppliedId, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string }) {
  const generatedId = useId(); const id = suppliedId || generatedId;
  return <div className="sds-field-group"><label htmlFor={id}>{label}</label><textarea dir="auto" {...props} id={id} className={`sds-field sds-textarea ${props.className || ""}`} aria-invalid={!!error || undefined} aria-describedby={[props["aria-describedby"], hint ? `${id}-hint` : undefined, error ? `${id}-error` : undefined].filter(Boolean).join(" ") || undefined} />{hint && <p className="sds-hint" id={`${id}-hint`}>{hint}</p>}{error && <p role="alert" className="sds-field-error" id={`${id}-error`}>{error}</p>}</div>;
}
export function Switch({ label, checked, onCheckedChange, disabled, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "checked" | "onChange"> & { label: string; checked: boolean; onCheckedChange: (value: boolean) => void }) {
  return <span className="sds-switch"><input {...props} aria-label={label} role="switch" type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onCheckedChange(event.currentTarget.checked)} /><span className="sds-switch-track" aria-hidden="true"><span className="sds-switch-thumb" /></span></span>;
}
export function RangeField({ label, value, min, max, step = 1, onValueChange, formatValue = String, disabled, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "min" | "max" | "step" | "onChange"> & { label: string; value: number; min: number; max: number; step?: number; onValueChange: (value: number) => void; formatValue?: (value: number) => string }) {
  const id = useId(); const { dir } = useContext(DesignContext);
  const fill = max > min ? Math.max(0, Math.min(100, (value - min) / (max - min) * 100)) : 0;
  return <div className="sds-range-field"><label htmlFor={id}>{label}</label><div><input {...props} id={id} type="range" className="sds-range" disabled={disabled} value={value} min={min} max={max} step={step} aria-valuetext={formatValue(value)} style={{ "--sds-range-fill": `${fill}%`, "--sds-range-direction": dir === "rtl" ? "to left" : "to right" } as CSSProperties} onChange={(event) => onValueChange(event.currentTarget.valueAsNumber)} /><output htmlFor={id}><bdi>{formatValue(value)}</bdi></output></div></div>;
}

export type MenuItem = { id: string; label: string; icon?: IconName; disabled?: boolean; tone?: "danger"; onSelect: () => void };
export function Menu({ label, icon = "more", items, children }: { label: string; icon?: IconName; items: MenuItem[]; children?: ReactNode }) {
  const [open, setOpen] = useState(false); const id = useId();
  const trigger = useRef<HTMLButtonElement>(null); const menu = useRef<HTMLDivElement>(null); const openingKey = useRef<"first" | "last">("first");
  const position = useFloating(trigger, open, 240);
  const dismiss = (restore: boolean) => { setOpen(false); if (restore) trigger.current?.focus(); };
  useLayoutEffect(() => {
    if (open && menu.current) { const buttons = menu.current.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'); buttons[openingKey.current === "last" ? buttons.length - 1 : 0]?.focus(); }
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) dismiss(false); };
    const focusOutside = (event: FocusEvent) => { if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside); document.addEventListener("focusin", focusOutside);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("focusin", focusOutside); };
  }, [open]);
  return <><button ref={trigger} type="button" className={`sds-button ${children ? "" : "sds-icon-button"}`} aria-label={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} title={label} onClick={() => { openingKey.current = "first"; setOpen(!open); }} onKeyDown={(event) => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); openingKey.current = event.key === "ArrowUp" ? "last" : "first"; setOpen(true); } }}>{children}<Icon name={icon} /></button>
    {open && <Overlay><div ref={menu} id={id} role="menu" aria-label={label} className="sds-menu" style={position} onKeyDown={(event) => {
      const buttons = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || []);
      const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) { event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length; buttons[next]?.focus(); }
      else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); dismiss(true); }
      else if (event.key === "Tab") {
        // Menu items are roving; resume the page Tab order from the trigger.
        trigger.current?.focus(); setOpen(false);
      } else if (event.key.length === 1 && !event.ctrlKey && !event.altKey && event.key !== " ") { const matches = [...buttons.slice(index + 1), ...buttons.slice(0, index + 1)]; matches.find((button) => button.textContent?.trim().toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()))?.focus(); }
    }}>{items.map((item) => <button key={item.id} type="button" role="menuitem" tabIndex={-1} disabled={item.disabled} className={item.tone === "danger" ? "sds-danger-text" : ""} onClick={() => { dismiss(true); item.onSelect(); }}>{item.icon && <Icon name={item.icon} />}{item.label}</button>)}</div></Overlay>}
  </>;
}

export function Dialog({ open, title, description, children, onClose, initialFocus, role = "dialog" }: { open: boolean; title: string; description?: string; children: ReactNode; onClose: () => void; initialFocus?: RefObject<HTMLElement | null>; role?: "dialog" | "alertdialog" }) {
  return open ? <DialogContent title={title} description={description} onClose={onClose} initialFocus={initialFocus} role={role}>{children}</DialogContent> : null;
}
function DialogContent({ title, description, children, onClose, initialFocus, role }: Omit<Parameters<typeof Dialog>[0], "open">) {
  const dialog = useRef<HTMLDialogElement>(null); const titleId = useId(); const descId = useId();
  const design = useContext(DesignContext);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  useLayoutEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = dialog.current;
    node?.showModal();
    (initialFocus?.current || node)?.focus();
    return () => { node?.close(); if (previous?.isConnected) previous.focus(); };
  }, [initialFocus]);
  return <DesignContext.Provider value={{ ...design, host }}><dialog ref={dialog} className="sds-dialog" role={role} tabIndex={-1} aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descId : undefined} onCancel={(event) => { event.preventDefault(); onClose(); }} onKeyDown={(event) => {
    if (event.key !== "Tab") return;
    const node = event.currentTarget;
    const focusable = Array.from(node.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex]:not([tabindex="-1"])')).filter((element) => !element.closest('[hidden],[inert]') && element.getClientRects().length && getComputedStyle(element).visibility !== "hidden");
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (!first) { event.preventDefault(); node.focus(); }
    else if (event.shiftKey && (document.activeElement === first || document.activeElement === node)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === node)) { event.preventDefault(); first.focus(); }
  }} onClick={(event) => { const r = event.currentTarget.getBoundingClientRect(); if (event.target === event.currentTarget && (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom)) onClose(); }}>
    <header><h2 id={titleId}>{title}</h2><IconButton variant="ghost" icon="close" label="סגירה" onClick={onClose} /></header>{description && <p className="sds-hint" id={descId}>{description}</p>}{children}
    <div ref={setHost} className="sds-overlay-host" />
  </dialog></DesignContext.Provider>;
}
export function ConfirmDialog({ open, title, description, confirmLabel, onConfirm, onClose, busy = false, error }: { open: boolean; title: string; description: string; confirmLabel: string; onConfirm: () => void; onClose: () => void; busy?: boolean; error?: string }) {
  const cancel = useRef<HTMLButtonElement>(null);
  return <Dialog open={open} title={title} description={description} role="alertdialog" initialFocus={cancel} onClose={() => { if (!busy) onClose(); }}>{error && <Alert tone="danger" title={error} />}<footer className="sds-actions"><button ref={cancel} type="button" className="sds-button" disabled={busy} onClick={onClose}>ביטול</button><Button variant="danger" loading={busy} onClick={onConfirm}>{confirmLabel}</Button></footer></Dialog>;
}

export function Tabs({ label, tabs, active, onSelect }: { label: string; tabs: Array<{ id: string; label: string; icon?: IconName; disabled?: boolean; panel: ReactNode }>; active: string; onSelect: (id: string) => void }) {
  const id = useId(); const { dir } = useContext(DesignContext);
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const enabled = tabs.filter((tab) => !tab.disabled);
  return <div className="sds-tabs"><div role="tablist" aria-label={label}>{tabs.map((tab) => <button type="button" ref={(node) => { if (node) refs.current.set(tab.id, node); else refs.current.delete(tab.id); }} key={tab.id} role="tab" id={`${id}-${tab.id}-tab`} aria-controls={`${id}-${tab.id}-panel`} aria-selected={active === tab.id} tabIndex={active === tab.id ? 0 : -1} disabled={tab.disabled} onClick={() => onSelect(tab.id)} onKeyDown={(event) => {
    const index = enabled.findIndex((item) => item.id === tab.id);
    let next: number | undefined;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = enabled.length - 1;
    if (event.key === "ArrowRight") next = (index + (dir === "rtl" ? -1 : 1) + enabled.length) % enabled.length;
    if (event.key === "ArrowLeft") next = (index + (dir === "rtl" ? 1 : -1) + enabled.length) % enabled.length;
    if (next !== undefined) { event.preventDefault(); refs.current.get(enabled[next].id)?.focus(); onSelect(enabled[next].id); }
  }}>{tab.icon && <Icon name={tab.icon} />}{tab.label}</button>)}</div>{tabs.map((tab) => <div key={tab.id} role="tabpanel" tabIndex={0} id={`${id}-${tab.id}-panel`} aria-labelledby={`${id}-${tab.id}-tab`} hidden={active !== tab.id}>{tab.panel}</div>)}</div>;
}

export function PageHeader({ title, description, eyebrow, actions }: { title: string; description?: string; eyebrow?: string; actions?: ReactNode }) {
  return <header className="sds-page-header"><div>{eyebrow && <p className="sds-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="sds-hint">{description}</p>}</div>{actions && <div className="sds-actions">{actions}</div>}</header>;
}
export function SettingsGroup({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  const id = useId(); return <section className="sds-settings-group" aria-labelledby={id}><header><h2 id={id}>{title}</h2>{description && <p className="sds-hint">{description}</p>}</header>{children}</section>;
}
export function SettingRow({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return <div className="sds-setting-row"><div><strong>{title}</strong>{description && <p className="sds-hint">{description}</p>}</div><div className="sds-setting-control">{children}</div></div>;
}
export function Alert({ title, children, tone = "info", action }: { title: string; children?: ReactNode; tone?: "info" | "success" | "warning" | "danger"; action?: ReactNode }) {
  return <div className={`sds-alert sds-alert--${tone}`} role={tone === "danger" ? "alert" : "status"}><Icon name={tone === "danger" || tone === "warning" ? "alert" : tone === "success" ? "check" : "info"} /><div><strong>{title}</strong>{children && <div>{children}</div>}{action}</div></div>;
}
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "accent" | "success" | "warning" | "danger" }) { return <span className={`sds-badge sds-badge--${tone}`}>{children}</span>; }
export function EmptyState({ title, description, icon = "folder", action }: { title: string; description: string; icon?: IconName; action?: ReactNode }) { return <div className="sds-empty"><Icon name={icon} size={24} /><h3>{title}</h3><p className="sds-hint">{description}</p>{action}</div>; }
export function LoadingState({ label, skeleton = false }: { label: string; skeleton?: boolean }) { return <div className="sds-loading" role="status" aria-label={label} aria-busy="true"><div><Icon name="loader" className="sds-spin" /><span>{label}</span></div>{skeleton && <div className="sds-skeleton" aria-hidden="true"><span /><span /><span /></div>}</div>; }
export function Card({ children, className = "", ...props }: HTMLAttributes<HTMLElement>) { return <section {...props} className={`sds-card ${className}`}>{children}</section>; }

// Explicit composition: content (including process), then ALL outputs, then actions.
export function MessageFrame({ children, outputs, actions }: { children: ReactNode; outputs?: ReactNode; actions?: ReactNode }) { return <article className="sds-message"><div className="sds-message-content">{children}</div>{outputs && <div className="sds-message-outputs">{outputs}</div>}{actions && <footer className="sds-message-actions">{actions}</footer>}</article>; }
export function UserBubble({ children, isNew = false }: { children: ReactNode; isNew?: boolean }) {
  const [entering, setEntering] = useState(isNew);
  useEffect(() => { setEntering(isNew); if (!isNew) return; const timer = setTimeout(() => setEntering(false), 240); return () => clearTimeout(timer); }, [isNew]);
  return <div className={`sds-user-bubble ${entering ? "sds-user-bubble--new" : ""}`} dir="auto">{children}</div>;
}
export function HoverLabel({ text }: { text: string }) {
  const viewport = useRef<HTMLSpanElement>(null); const content = useRef<HTMLSpanElement>(null);
  const [travel, setTravel] = useState({ distance: 0, rtl: true });
  useLayoutEffect(() => {
    const measure = () => { if (viewport.current && content.current) setTravel({ distance: Math.max(0, content.current.scrollWidth - viewport.current.clientWidth), rtl: getComputedStyle(viewport.current).direction === "rtl" }); };
    measure(); const observer = new ResizeObserver(measure); if (viewport.current) observer.observe(viewport.current);
    return () => observer.disconnect();
  }, [text]);
  return <span ref={viewport} className="sds-hover-label" title={text} dir="auto" data-overflow={travel.distance > 1} style={{ "--sds-label-shift": `${travel.rtl ? travel.distance : -travel.distance}px`, "--sds-label-duration": `${Math.max(1.2, travel.distance / 72)}s` } as CSSProperties}><span ref={content}>{text}</span></span>;
}
