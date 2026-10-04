import { Icon, type IconName } from "./Icon";

export function Button({ children, icon, label, className = "", ...props }: React.ComponentProps<"button"> & { icon?: IconName; label?: string }) {
  return <button type="button" className={`ux-button ${className}`} aria-label={label} title={label} {...props}>{icon && <Icon name={icon} />}{children}</button>;
}
