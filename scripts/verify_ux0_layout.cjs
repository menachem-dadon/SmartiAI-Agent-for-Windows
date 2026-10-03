// Isolated browser QA of the real React fixture; no native app or user data.
// Requires Playwright (locally installed or resolved through NODE_PATH).
const { chromium } = require("playwright");
const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");

async function geometry(page) {
  return page.evaluate(() => {
    const bounds = (selector) => {
      const r = document.querySelector(selector).getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
    };
    const chat = bounds(".chat-column");
    const composer = bounds(".composer");
    const actions = bounds(".composer-actions");
    const primary = bounds(".composer-primary");
    const attachment = bounds(".composer-tool");
    const model = bounds(".model-quick-pill summary");
    const autonomy = bounds(".autonomy-quick-pill summary");
    const fastMode = document.querySelector(".local-fast-mode") ? bounds(".local-fast-mode") : null;
    const inside = (r, outer) => r.left >= outer.left - 0.5 && r.right <= outer.right + 0.5 && r.top >= outer.top - 0.5 && r.bottom <= outer.bottom + 0.5;
    const workspace = document.querySelector(".workspace");
    const open = workspace.classList.contains("has-workbench");
    const overlay = workspace.classList.contains("is-overlay-layout") && open;
    const hit = (selector, r) => document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2)?.closest(selector) === document.querySelector(selector);
    const workbenchGap = open && !overlay ? composer.left - bounds(".workbench").right : null;
    return {
      chat, composer, primary, attachment, model, autonomy, fastMode, overlay, workbenchGap,
      leftInset: composer.left - chat.left, rightInset: chat.right - composer.right,
      primaryLabel: document.querySelector(".composer-primary").getAttribute("aria-label"),
      contained: inside(composer, chat) && [primary, attachment, model, autonomy, ...(fastMode ? [fastMode] : [])].every(r => inside(r, composer)),
      reachable: overlay || (hit(".composer-primary", primary) && hit(".composer-tool", attachment)),
      anchoredSides: Math.abs(attachment.right - actions.right) < 0.5 && Math.abs(primary.left - actions.left) < 0.5,
      sameBaseline: Math.abs(primary.bottom - attachment.bottom) < 0.5,
      selectorsSideBySide: Math.abs(model.top - autonomy.top) < 0.5 && model.right <= autonomy.left + 0.5 && Math.min(model.width, autonomy.width) >= 40,
      selectorsReachable: overlay || (hit(".model-quick-pill summary", model) && hit(".autonomy-quick-pill summary", autonomy)),
    };
  });
}

async function dragWorkbench(page, x) {
  const handle = await page.getByRole("separator", { name: "שינוי רוחב אזור העבודה" }).boundingBox();
  await page.mouse.move(handle.x + handle.width / 2, handle.y + 100);
  await page.mouse.down();
  await page.mouse.move(x, handle.y + 100, { steps: 12 });
  await page.mouse.up();
  await page.waitForTimeout(50);
}

async function main() {
  const base = process.argv[2] || "http://127.0.0.1:1428";
  const output = path.resolve(process.argv[3] || ".codex-local/ux-0/layout");
  const baseline = process.argv.includes("--baseline");
  const selectorsOnly = process.argv.includes("--selectors-only");
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  const version = browser.version();
  const results = [];
  const record = (key, measured, expectedLabel, originalGap = null) => {
    results.push({ key, ...measured, correctLabel: measured.primaryLabel === expectedLabel,
      gapPreserved: originalGap === null || Math.abs(measured.workbenchGap - originalGap) < 0.5,
      regularGutters: measured.workbenchGap === null || (Math.abs(measured.leftInset - 28) < 0.5 && Math.abs(measured.rightInset - 28) < 0.5),
    });
  };
  try {
    for (const theme of (selectorsOnly ? [] : ["light", "dark"])) {
      for (const width of (baseline ? [500, 900, 1205, 1206, 1380, 1920] : [360, 500, 900, 1205, 1206, 1380, 1920])) {
        for (const workbench of [0, 1]) {
          for (const provider of (baseline ? ["openai"] : ["openai", "local"])) {
            for (const state of (baseline ? ["idle"] : ["idle", "draft", "running"])) {
              await page.setViewportSize({ width, height: 900 });
              await page.goto(`${base}/?visual-fixture=point16a&theme=${theme}&workbench=${workbench}&provider=${provider}&running=${state === "running" ? 1 : 0}`);
              await page.locator(".composer-primary").waitFor();
              if (state === "draft") await page.getByRole("textbox", { name: "הודעה" }).fill("טיוטת בדיקה\nMixed Hebrew / English 123");
              await page.waitForTimeout(350);
              const measured = await geometry(page);
              const key = `${theme}-${width}-workbench${workbench}-${provider}-${state}`;
              const expectedLabel = state === "running" ? "עצירה" : state === "draft" ? "שליחה" : "הכתבה קולית";
              record(key, measured, expectedLabel);
              if ([360, 1380].includes(width) && workbench && state === "idle") await page.screenshot({ path: path.join(output, `${key}.png`) });
              if (!baseline && workbench && !measured.overlay) {
                for (const [resize, x] of [["max", width - 4], ["min", 4]]) {
                  await dragWorkbench(page, x);
                  record(`${key}-resize-${resize}`, await geometry(page), expectedLabel, measured.workbenchGap);
                  if (width === 1380 && state === "idle") await page.screenshot({ path: path.join(output, `${key}-resize-${resize}.png`) });
                }
              }
            }
          }
        }
      }
    }
    if (!baseline) {
      for (const theme of ["light", "dark"]) {
        for (const model of ["Codex default", "A very long mixed מודל model name 1234567890"]) {
          for (const width of [500, 1380]) {
            await page.setViewportSize({ width, height: 900 });
            await page.goto(`${base}/?visual-fixture=point16a&theme=${theme}&workbench=1&model=${encodeURIComponent(model)}`);
            await page.locator(".composer-primary").waitFor();
            await page.waitForTimeout(350);
            const measured = await geometry(page);
            const key = `${theme}-${width}-${model === "Codex default" ? "codex-default" : "long-model"}`;
            record(key, measured, "הכתבה קולית");
            if (!measured.overlay) {
              for (const selector of [".model-quick-pill", ".autonomy-quick-pill"]) {
                await page.locator(`${selector} summary`).click();
                await assert.doesNotReject(() => page.waitForFunction(s => document.querySelector(s).open, selector));
                await page.keyboard.press("Escape");
                await page.waitForFunction(s => !document.querySelector(s).open && document.activeElement === document.querySelector(`${s} summary`), selector);
              }
              await page.screenshot({ path: path.join(output, `${key}.png`) });
              await dragWorkbench(page, width - 4);
              record(`${key}-resize-max`, await geometry(page), "הכתבה קולית", measured.workbenchGap);
            }
          }
        }
      }
    }
  } finally {
    await browser.close();
  }
  await fs.writeFile(path.join(output, "results.json"), JSON.stringify({ browser: version, viewportHeight: 900, deviceScaleFactor: 1, results }, null, 2));
  const failures = results.filter((r) => !r.contained || !r.reachable || !r.correctLabel || !r.anchoredSides || !r.sameBaseline || !r.selectorsSideBySide || !r.selectorsReachable || !r.gapPreserved || !r.regularGutters);
  console.log(JSON.stringify({ cases: results.length, failed: failures.length, failures, output }, null, 2));
  if (!baseline) assert.equal(failures.length, 0, "Composer controls must keep their sides, selectors in one row, bounds and spacing through splitter dragging");
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
