export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "smarti.desktop.theme";

export { palettes, foundations, designTokenStyle, textContrastRoles } from "./design-system/tokens";
import { palettes, foundations, textContrastRoles } from "./design-system/tokens";

export const semanticTokens = {
  color: Object.keys(palettes.light),
  ...Object.fromEntries(Object.entries(foundations).map(([family, roles]) => [family, Object.keys(roles)])),
} as const;

export function resolveTheme(preference: ThemePreference, systemDark: boolean): ResolvedTheme {
  return preference === "system" ? (systemDark ? "dark" : "light") : preference;
}

export function parseThemePreference(value: string | null): ThemePreference {
  return value === "light" || value === "dark" || value === "system" ? value : "system";
}

function linearChannel(hex: string): number {
  const value = Number.parseInt(hex, 16) / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

export function contrastRatio(foreground: string, background: string): number {
  const luminance = (hex: string) => {
    const normalized = hex.replace("#", "");
    const channels = normalized.length === 3
      ? normalized.split("").map((part) => `${part}${part}`)
      : [normalized.slice(0, 2), normalized.slice(2, 4), normalized.slice(4, 6)];
    return 0.2126 * linearChannel(channels[0]) + 0.7152 * linearChannel(channels[1]) + 0.0722 * linearChannel(channels[2]);
  };
  const light = Math.max(luminance(foreground), luminance(background));
  const dark = Math.min(luminance(foreground), luminance(background));
  return (light + 0.05) / (dark + 0.05);
}

export const contrastPairs = {
  light: textContrastRoles.map(([fg, bg]) => [palettes.light[fg], palettes.light[bg]] as const),
  dark: textContrastRoles.map(([fg, bg]) => [palettes.dark[fg], palettes.dark[bg]] as const),
};
