import { describe, expect, it } from "vitest";
import { activeTab, nextRequestId, pageTitle, type BrowserSnapshot, type BrowserTab } from "./browserState";
import { browserProductCapabilities } from "./BrowserPanel";
const tab = (overrides: Partial<BrowserTab> = {}): BrowserTab => ({ tabId: "tab-00000001", targetId: "wv2-target-00000001", webviewLabel: "browser-00000001", profile: "persistent", url: "https://example.com/path", title: "", loading: false, active: true, crashed: false, pinned: false, faviconUrl: "", audioPlaying: false, ...overrides });
describe("browser state", () => {
  it("selects by stable tab id rather than array index", () => { const snapshot: BrowserSnapshot = { tabs: [tab({ tabId: "two" }), tab({ tabId: "one" })], activeTabId: "one", transport: "webview2-in-process-cdp", remoteDebuggingPort: null }; expect(activeTab(snapshot)?.tabId).toBe("one"); });
  it("derives a quiet hostname title and reports crashes", () => { expect(pageTitle(tab())).toBe("example.com"); expect(pageTitle(tab({ crashed: true }))).toBe("הכרטיסייה קרסה"); });
  it("creates unique request ids", () => { const first = nextRequestId(); const second = nextRequestId(); expect(first).not.toBe(second); expect(first).toMatch(/^ui-[a-z0-9]+-[a-z0-9]{4}$/); });
  it("keeps Guest and password import outside the persistent library contract", () => { expect(browserProductCapabilities.guestInPersistentLibrary).toBe(false); expect(browserProductCapabilities.passwordImport).toBe(false); expect(browserProductCapabilities.remoteDebuggingPort).toBeNull(); });
});
