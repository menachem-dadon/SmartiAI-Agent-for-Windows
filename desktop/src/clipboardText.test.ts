// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { isTauri } from "@tauri-apps/api/core";
import { readText } from "@tauri-apps/plugin-clipboard-manager";
import { readClipboardText } from "./clipboardText";

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn() }));
vi.mock("@tauri-apps/plugin-clipboard-manager", () => ({ readText: vi.fn() }));
afterEach(() => vi.resetAllMocks());

it("grants only clipboard text reads to the trusted main WebView", () => {
  const permission = JSON.parse(readFileSync("src-tauri/capabilities/clipboard-read.json", "utf8"));
  expect(permission.webviews).toEqual(["main"]);
  expect(permission.windows).toBeUndefined();
  expect(permission.remote).toBeUndefined();
  expect(permission.local).not.toBe(false);
  expect(permission.permissions).toEqual(["clipboard-manager:allow-read-text"]);
  const shared = JSON.parse(readFileSync("src-tauri/capabilities/default.json", "utf8"));
  expect(shared.permissions.some((p: string) => p.startsWith("clipboard-manager:"))).toBe(false);
});

it("reads natively in Tauri without asking the browser for clipboard permission", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(readText).mockResolvedValue("native-text");
  const browserRead = vi.fn().mockRejectedValue(Error("browser permission prompt"));
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { readText: browserRead } });
  await expect(readClipboardText()).resolves.toBe("native-text");
  expect(readText).toHaveBeenCalledTimes(1);
  expect(browserRead).not.toHaveBeenCalled();
});

it("preserves browser permissions in a web preview", async () => {
  vi.mocked(isTauri).mockReturnValue(false);
  const browserRead = vi.fn().mockResolvedValue("web-text");
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { readText: browserRead } });
  await expect(readClipboardText()).resolves.toBe("web-text");
  expect(readText).not.toHaveBeenCalled();
});

it("surfaces native failures without falling back to a browser prompt", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(readText).mockRejectedValue(Error("clipboard unavailable"));
  const browserRead = vi.fn();
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { readText: browserRead } });
  await expect(readClipboardText()).rejects.toThrow("clipboard unavailable");
  expect(browserRead).not.toHaveBeenCalled();
});
