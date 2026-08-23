export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "smarti.desktop.theme";

export const semanticTokens = {
  color: ["background", "surface", "surfaceRaised", "glass", "border", "text", "muted", "accent", "success", "warning", "danger", "focus", "code"],
  radius: ["xs", "sm", "md", "lg", "xl", "pill"],
  space: ["1", "2", "3", "4", "5", "6", "8", "10"],
  shadow: ["soft", "raised", "dialog"],
  blur: ["surface", "dialog"],
  motion: ["fast", "normal", "slow"],
  density: ["compact", "comfortable"],
  type: ["family", "mono", "caption", "body", "title", "display"],
} as const;

export function resolveTheme(preference: ThemePreference, systemDark: boolean): ResolvedTheme {
  return preference === "system" ? (systemDark ? "dark" : "light") : preference;
}

export function parseThemePreference(value: string | null): ThemePreference {
  return value === "light" || value === "dark" || value === "system" ? value : "system";
}

function linearChannel(hex: string): number {
  const value = Number.parseInt(hex, 16) / 255;
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
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
  light: [["#20212a", "#f8f8fb"], ["#5e6170", "#ffffff"], ["#ffffff", "#654fd4"]],
  dark: [["#f3f3f7", "#17181d"], ["#a9abb6", "#202126"], ["#ffffff", "#725dde"]],
} as const;
