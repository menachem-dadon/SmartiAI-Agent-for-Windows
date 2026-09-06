import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { modelMenuBounds, modelMenuContentViewport } from "./modelMenuPosition";

describe("model menu viewport placement", () => {
  test("fits narrow, short, zoomed and wide viewports at either edge", () => {
    for (const [width, height, left, top] of [
      [320, 480, 0, 0], [360, 320, 0, 0], [800, 600, 0, 0],
      [1920, 1080, 0, 0], [320, 280, 20, 70],
    ]) {
      for (const x of [left + 8, left + width - 90]) {
        for (const y of [top + 40, top + height - 70]) {
          const bounds = modelMenuBounds({ left: x, top: y, bottom: y + 40 }, { left, top, width, height }, 652);
          expect(bounds.left).toBeGreaterThanOrEqual(left + 8);
          expect(bounds.top).toBeGreaterThanOrEqual(top + 8);
          expect(bounds.left + bounds.width).toBeLessThanOrEqual(left + width - 8);
          expect(bounds.top + bounds.height).toBeLessThanOrEqual(top + height - 8);
          expect(bounds.height).toBeGreaterThan(0);
          expect(bounds.top + bounds.height <= y - 8 || bounds.top >= y + 48).toBe(true);
        }
      }
    }
  });

  test("keeps physical RTL columns and independent scroll areas at every breakpoint", () => {
    const css = readFileSync(new URL("./App.css", import.meta.url), "utf8");
    expect(css).not.toContain("model-provider-submenu");
    expect(css).toMatch(/\.model-menu-models\s*\{[^}]*grid-column:\s*1/);
    expect(css).toMatch(/\.model-menu-providers\s*\{[^}]*grid-column:\s*2/);
    expect(css).toMatch(/\.model-menu-list\s*\{[^}]*overflow-y:\s*auto/);
    expect(css).toMatch(/\.model-quick-menu\s*\{[^}]*position:\s*fixed/);
    const footer = css.match(/\.model-menu-footer\s*\{([^}]+)\}/)?.[1] || "";
    expect(footer).not.toMatch(/overflow|height:/);
    expect(css).not.toContain("--model-footer-height");
    expect(css).not.toContain("codex-quota-card");
  });

  test("keeps the menu header below the titlebar, including a short zoomed viewport", () => {
    for (const viewport of [
      { left: 0, top: 0, width: 752, height: 640 },
      { left: 0, top: 0, width: 360, height: 320 },
      { left: 20, top: 70, width: 320, height: 280 },
    ]) {
      const content = modelMenuContentViewport(viewport, 36);
      expect(content.top + content.height).toBe(viewport.top + viewport.height);
      const anchor = { left: viewport.left + 70, top: viewport.top + viewport.height - 64, bottom: viewport.top + viewport.height - 24 };
      const menu = modelMenuBounds(anchor, content, 504);
      expect(menu.top).toBeGreaterThanOrEqual(Math.max(36, viewport.top) + 8);
      expect(menu.top + menu.height).toBeLessThanOrEqual(anchor.top - 8);
    }
  });
});
