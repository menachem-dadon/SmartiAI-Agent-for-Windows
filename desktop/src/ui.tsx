import { type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";

export function Button({ className = "", variant = "secondary", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  return <button type="button" className={`ui-button ui-button--${variant} ${className}`} {...props} />;
}

export function IconButton({ label, tooltip, className = "", children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; tooltip?: string; children: ReactNode }) {
  return <button type="button" className={`ui-icon-button ${className}`} aria-label={label} data-tooltip={tooltip || label} {...props}>{children}</button>;
}

export function Field(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`ui-field ${props.className || ""}`} {...props} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`ui-textarea ${props.className || ""}`} {...props} />;
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "accent" | "success" | "warning" | "danger"; children: ReactNode }) {
  return <span className={`ui-badge ui-badge--${tone}`}>{children}</span>;
}

export function Card({ className = "", ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={`ui-card ${className}`} {...props} />;
}

export function Alert({ tone = "info", title, children }: { tone?: "info" | "success" | "warning" | "danger"; title: string; children?: ReactNode }) {
  return <div className={`ui-alert ui-alert--${tone}`} role="status"><strong>{title}</strong>{children && <span>{children}</span>}</div>;
}

export function EmptyState({ icon, title, description, action }: { icon: ReactNode; title: string; description: string; action?: ReactNode }) {
  return <div className="ui-empty"><span className="ui-empty__icon" aria-hidden="true">{icon}</span><h2>{title}</h2><p>{description}</p>{action}</div>;
}

export function Skeleton({ width = "100%" }: { width?: string }) {
  return <span className="ui-skeleton" style={{ width }} aria-hidden="true" />;
}

export function Tabs({ label, tabs, active, onSelect }: { label: string; tabs: Array<{ id: string; label: string }>; active: string; onSelect: (id: string) => void }) {
  return <div className="ui-tabs" role="tablist" aria-label={label}>{tabs.map((tab) => <button type="button" role="tab" aria-selected={active === tab.id} key={tab.id} onClick={() => onSelect(tab.id)}>{tab.label}</button>)}</div>;
}

export function Menu({ label, children }: { label: string; children: ReactNode }) {
  return <div className="ui-menu" role="menu" aria-label={label}>{children}</div>;
}

export function Dialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return <div className="ui-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="ui-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header><h2 id="dialog-title">{title}</h2><IconButton label="סגירה" onClick={onClose}>×</IconButton></header>{children}</section></div>;
}

export function Drawer({ title, open, children, onClose }: { title: string; open: boolean; children: ReactNode; onClose: () => void }) {
  return <aside className={`ui-drawer ${open ? "is-open" : ""}`} aria-hidden={!open}><header><h2>{title}</h2><IconButton label="סגירה" onClick={onClose}>×</IconButton></header><div className="ui-scroll-area">{children}</div></aside>;
}

export function Resizer({ label }: { label: string }) {
  return <div className="ui-resizer" role="separator" aria-label={label} aria-orientation="vertical" tabIndex={0} />;
}
