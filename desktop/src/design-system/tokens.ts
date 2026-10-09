import type { CSSProperties } from "react";

// Single value source. CSS and rendered-contrast tests consume these same roles.
export const palettes = {
  light: {
    background: "#f3f4f6", surface: "#ffffff", surfaceMuted: "#f0f2f5",
    text: "#252b36", textMuted: "#606b7e", border: "#dde1e8", controlBorder: "#7c8594",
    accent: "#365ccd", accentHover: "#2e50b8", accentPressed: "#244397", onAccent: "#ffffff", accentSoft: "#edf1ff",
    action: "#397bfa", actionHover: "#2e6deb", actionPressed: "#255ed1", onAction: "#ffffff",
    success: "#28714b", warning: "#865b17", danger: "#b53645", dangerSoft: "#fff1f2", onDanger: "#ffffff",
    focus: "#606b7e", scrollbar: "#cbd0d8", overlay: "#00000066", shadowColor: "#20294318",
  },
  dark: {
    background: "#101319", surface: "#191d25", surfaceMuted: "#232935",
    text: "#edf0f7", textMuted: "#a5afc0", border: "#343c4b", controlBorder: "#8893a6",
    accent: "#a2baff", accentHover: "#b6c9ff", accentPressed: "#8eaaff", onAccent: "#101319", accentSoft: "#293654",
    action: "#397bfa", actionHover: "#2e6deb", actionPressed: "#255ed1", onAction: "#ffffff",
    success: "#91d3ac", warning: "#e5bd79", danger: "#ffb0b8", dangerSoft: "#39252b", onDanger: "#101319",
    focus: "#a5afc0", scrollbar: "#657084", overlay: "#00000099", shadowColor: "#00000055",
  },
} as const;

// Integration identity colors stay separate from Smarti's semantic palettes.
export const brandColors = {
  buyMeACoffee: { background: "#FFDD00", foreground: "#000000" },
} as const;

export const foundations = {
  font: { family: '"Segoe UI", Arial, sans-serif', mono: 'Consolas, "Courier New", monospace', caption: "13px", control: "14px", body: "16px", heading: "20px", display: "32px", line: "1.6", readingLine: "1.85" },
  space: { "1": "4px", "2": "8px", "3": "12px", "4": "16px", "6": "24px", "8": "32px", "12": "48px" },
  radius: { control: "10px", card: "16px", dialog: "16px", composer: "24px", pill: "999px" },
  size: { target: "40px", switchWidth: "44px", switchHeight: "26px", switchThumb: "18px", rangeTrack: "24px", number: "96px", icon: "18px", iconLarge: "24px", stroke: "1px", focus: "2px" },
  motion: { fast: "120ms", menu: "160ms", dialog: "200ms", panel: "260ms", entry: "180ms", ease: "cubic-bezier(.2,.8,.2,1)", linear: "linear" },
  shadow: { floating: "0 16px 48px var(--sds-color-shadow-color)" },
} as const;

export type DesignTheme = keyof typeof palettes;
export type ColorRole = keyof typeof palettes.light;
const kebab = (key: string) => key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
export function designTokenStyle(theme: DesignTheme): CSSProperties {
  const values: Record<string, string> = {};
  for (const [role, value] of Object.entries(palettes[theme])) values[`--sds-color-${kebab(role)}`] = value;
  for (const [brand, roles] of Object.entries(brandColors)) {
    for (const [role, value] of Object.entries(roles)) values[`--sds-brand-${kebab(brand)}-${kebab(role)}`] = value;
  }
  for (const [family, roles] of Object.entries(foundations)) {
    for (const [role, value] of Object.entries(roles)) values[`--sds-${family}-${kebab(role)}`] = value;
  }
  return values as CSSProperties;
}

export const textContrastRoles: ReadonlyArray<readonly [ColorRole, ColorRole]> = [
  ["text", "background"], ["text", "surface"], ["text", "surfaceMuted"], ["textMuted", "surface"], ["textMuted", "surfaceMuted"],
  ["textMuted", "background"], ["text", "accentSoft"], ["accent", "surface"], ["accent", "accentSoft"],
  ["onAccent", "accent"], ["onAccent", "accentHover"], ["onAccent", "accentPressed"],
  ["success", "surface"], ["warning", "surface"], ["danger", "dangerSoft"], ["onDanger", "danger"],
];
