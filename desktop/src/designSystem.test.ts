import { describe, expect, test } from "vitest";
import { contrastPairs, contrastRatio, designTokenStyle, foundations, palettes, parseThemePreference, resolveTheme, semanticTokens } from "./designSystem";

describe("Smarti design system", () => {
  test("provides matching semantic roles for both themes and CSS consumers", () => {
    expect(Object.keys(palettes.dark).sort()).toEqual(Object.keys(palettes.light).sort());
    expect(semanticTokens.color).toEqual(Object.keys(palettes.light));
    expect(semanticTokens.color).toContain("focus");
    expect(semanticTokens.color).toContain("danger");
    for (const theme of ["light", "dark"] as const) {
      const style = designTokenStyle(theme) as Record<string, string>;
      expect(style["--sds-color-surface"]).toBe(palettes[theme].surface);
      expect(style["--sds-color-text-muted"]).toBe(palettes[theme].textMuted);
      expect(style["--sds-size-target"]).toBe(foundations.size.target);
    }
  });

  test("resolves persisted and system themes safely", () => {
    expect(parseThemePreference("unexpected")).toBe("system");
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("light", true)).toBe("light");
  });

  test("primary text and controls meet WCAG AA contrast", () => {
    for (const pairs of Object.values(contrastPairs)) {
      for (const [foreground, background] of pairs) expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(4.5);
    }
  });

  test("neutral field boundaries and focus remain perceptible on adjacent surfaces", () => {
    for (const palette of Object.values(palettes)) {
      for (const action of [palette.action, palette.actionHover, palette.actionPressed]) {
        expect(contrastRatio(palette.onAction, action)).toBeGreaterThanOrEqual(3);
      }
      for (const background of [palette.surface, palette.surfaceMuted, palette.background]) {
        expect(contrastRatio(palette.controlBorder, background)).toBeGreaterThanOrEqual(3);
        expect(contrastRatio(palette.focus, background)).toBeGreaterThanOrEqual(3);
      }
    }
  });
});
