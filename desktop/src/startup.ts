import { designTokenStyle, parseThemePreference, resolveTheme, THEME_STORAGE_KEY, type ResolvedTheme } from "./designSystem";
import originalLogo from "../../assets/logo.png";

export const STARTUP_ICON_URL = `${import.meta.env.BASE_URL}loading-icon.png`;
export const DARK_STARTUP_ICON_URL = `${import.meta.env.BASE_URL}loading-icon-dark.png`;
export const ORIGINAL_STARTUP_ICON = originalLogo;

export function startupTheme(): ResolvedTheme {
  let preference = null;
  try { preference = localStorage.getItem(THEME_STORAGE_KEY); } catch { /* System theme remains available. */ }
  return resolveTheme(parseThemePreference(preference), window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
}

export function updateStartupTheme(theme: ResolvedTheme) {
  for (const [name, value] of Object.entries(designTokenStyle(theme))) {
    document.documentElement.style.setProperty(name, String(value));
  }
  document.documentElement.style.colorScheme = theme;
}

export function setStartupVisible(visible: boolean) {
  const surface = document.getElementById("smarti-startup");
  if (surface) { surface.hidden = !visible; surface.setAttribute("aria-busy", String(visible)); }
}

// Resolve the artwork before presenting the hidden native window, so valid
// custom artwork appears on its first paint. Missing/corrupt files use the original.
export async function prepareStartupIcon(target: HTMLImageElement, theme: ResolvedTheme = startupTheme()) {
  target.src = originalLogo;
  target.dataset.startupArtwork = "original";
  const custom = new Image();
  custom.src = theme === "dark" ? DARK_STARTUP_ICON_URL : STARTUP_ICON_URL;
  await custom.decode().then(() => {
    if (custom.naturalWidth > 0) {
      target.src = custom.src;
      target.dataset.startupArtwork = theme;
    }
  }).catch(() => {});
  await target.decode().catch(() => {});
}
