import { describe, expect, test } from "vitest";
import { contrastPairs, contrastRatio, parseThemePreference, resolveTheme, semanticTokens } from "./designSystem";

describe("Smarti design system", () => {
  test("declares every semantic token family required by Point 7", () => {
    expect(Object.keys(semanticTokens)).toEqual(["color", "radius", "space", "shadow", "blur", "motion", "density", "type"]);
    expect(semanticTokens.color).toContain("focus");
    expect(semanticTokens.color).toContain("danger");
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
});
