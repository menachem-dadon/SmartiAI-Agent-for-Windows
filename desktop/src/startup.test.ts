// @vitest-environment jsdom
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { ORIGINAL_STARTUP_ICON, prepareStartupIcon, setStartupVisible, startupTheme, updateStartupTheme } from "./startup";
import { palettes, THEME_STORAGE_KEY } from "./designSystem";
beforeAll(() => { HTMLImageElement.prototype.decode = () => Promise.resolve(); });
afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); document.body.replaceChildren(); });

it.each(["missing", "corrupt"])("keeps the original icon when custom artwork is %s", async () => {
  const target = document.createElement("img");
  vi.spyOn(HTMLImageElement.prototype, "decode").mockImplementation(function(this: HTMLImageElement) {
    return this === target ? Promise.resolve() : Promise.reject(new Error("unavailable"));
  });
  await prepareStartupIcon(target);
  expect(target.getAttribute("src")).toBe(ORIGINAL_STARTUP_ICON);
});

it("waits for the optional icon to decode before allowing the first native paint", async () => {
  const target = document.createElement("img");
  let complete!: () => void;
  vi.spyOn(HTMLImageElement.prototype, "decode").mockImplementation(function(this: HTMLImageElement) {
    if (this === target) return Promise.resolve();
    Object.defineProperty(this, "naturalWidth", { value: 256 });
    return new Promise<void>(resolve => { complete = resolve; });
  });
  let prepared = false;
  const preparation = prepareStartupIcon(target).then(() => { prepared = true; });
  await Promise.resolve();
  expect(prepared).toBe(false);
  expect(target.getAttribute("src")).toBe(ORIGINAL_STARTUP_ICON);
  complete(); await preparation;
  expect(prepared).toBe(true);
  expect(target.src).toMatch(/loading-icon\.png$/);
});

it("uses the persisted theme and the shared background values before React", () => {
  localStorage.setItem(THEME_STORAGE_KEY, "dark");
  expect(startupTheme()).toBe("dark");
  updateStartupTheme(startupTheme());
  expect(document.documentElement.style.getPropertyValue("--sds-color-background")).toBe(palettes.dark.background);
});

it("retains one startup surface through loading and hides it at the handoff", () => {
  document.body.innerHTML = '<div id="smarti-startup"><img alt=""></div>';
  const surface = document.getElementById("smarti-startup")!;
  setStartupVisible(true); expect(surface.hidden).toBe(false);
  setStartupVisible(false); expect(surface.hidden).toBe(true);
  setStartupVisible(true); expect(document.getElementById("smarti-startup")).toBe(surface);
  expect(surface.textContent).toBe("");
});
