import { capabilityLabels, providerOptions, providerSecretKeys, settingDefinitions } from "../managementCatalog";
import { toolLabels } from "./toolLabels";
import { artifactName, artifactText } from "./data";
import type { BrowserSnapshot, BrowserTab } from "../browserState";

type Json = Record<string, unknown>;
type Request = { method: string; path: string; body?: Json };
const clone = <T,>(value: T): T => structuredClone(value);
const object = (value: unknown): Json => value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
function merge(target: Json, patch: Json) {
  for (const [key, value] of Object.entries(patch)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      target[key] = object(target[key]); merge(target[key] as Json, value as Json);
    } else target[key] = clone(value);
  }
}
function setPath(target: Json, path: string, value: unknown) {
  const keys = path.split("."); let parent = target;
  for (const key of keys.slice(0, -1)) { parent[key] ??= {}; parent = parent[key] as Json; }
  parent[keys[keys.length - 1]] = value;
}
const values: Json = {};
for (const field of settingDefinitions) setPath(values, field.path,
  field.control === "switch" ? false : field.options?.[0]?.value ?? (field.control === "number" || field.control === "range" ? field.min ?? 1 : ""));
merge(values, {
  api_mode: "openai", selected_openai_model: "gpt-demo", selected_gemini_model: "gemini-demo",
  favorite_models: [{ provider: "openai", model: "gpt-demo" }, { provider: "openai_codex_signin", model: "openai_codex_signin-demo" }, { provider: "gemini", model: "gemini-demo" }, { provider: "local", model: "local-demo" }], local_server_url: "http://127.0.0.1:1234/v1",
  ui_preferences: { settings_show_advanced: false, theme_mode: "light", workbench_root: "workspace:/community" },
  policy_matrix: Object.fromEntries(Object.keys(capabilityLabels).map(key => [key, "ask"])),
  ssl_trust_mode: "system", tts_voice: "he-demo", voice_hotkey: "Ctrl+Shift+Space",
});
const defaults = clone(values);
const secrets: Record<string, { configured: boolean; masked: string }> = Object.fromEntries(
  Object.values(providerSecretKeys).map(key => [key, { configured: true, masked: "••••A1B2" }]),
);
const settings = () => clone({ values, secrets });
const demoModels = (provider: string) => provider === "local" ? ["local-demo", "local-reasoning-demo"] : [`${provider === "openai" ? "gpt" : provider}-demo`, `${provider}-reasoning-demo`];
const reasoning = new Map<string, string>();
let tasks: Json[] = [
  { id: "task-1", prompt: "סיכום שבועי של מפגשי הקהילה", status: "paused", repeat: "weekly", run_at: "2026-10-05T09:00:00", conversation_mode: "dedicated", target_conversation_id: "demo-task", days_of_week: [0, 2] },
  { id: "task-2", prompt: "בדיקת טבלת התקציב", status: "failed", repeat: "once", run_at: "2026-10-04T10:00:00", conversation_mode: "new", error: "הספק לא הגיב. אפשר לנסות שוב." },
];
let memories: Json[] = [
  { id: "memory-1", subject: "העדפות כתיבה", content: "מסמכים בעברית ובאנגלית, עם המלצות מעשיות.", type: "user", category: "preference", sensitivity: "normal", status: "active", importance: 4, tags: ["כתיבה", "קהילה"], pinned: true, created_at: "2026-10-03T10:00:00", updated_at: "2026-10-03T10:00:00" },
  { id: "memory-2", subject: "איש קשר", content: "contact@community.example", type: "long_term", category: "email", sensitivity: "sensitive", status: "active", importance: 3, tags: ["קהילה"], pinned: false },
  { id: "memory-3", subject: "תכנון קודם", content: "מפגש ניסיוני בארכיון", type: "short_term", category: "project", sensitivity: "normal", status: "archive", importance: 2, tags: [] },
];
const builtins: Json[] = ["agent_planner", "file_manager", "web_manager", "browser_automation_manager", "canvas_manager", "memory_manager", "document_manager", "background_task_manager", "computer_automation_manager", "email_manager", "screen_manager", "notification_manager", "software_manager", "system_manager", "search_tools", "get_tool_info", "extension_manager", "create_python_tool", "final_verifier", "context_compaction"].map(name => ({ name, label: toolLabels[name] ?? name, category: name.includes("manager") ? "management" : "agent", category_label: name.includes("manager") ? "ניהול ופעולות" : "סוכן וכלים", enabled: true }));
let extensions: Json[] = [
  { name: "community_report", label: "community_report", kind: "custom", enabled: true, trusted: false, removable: true, source_label: "כלי אישי" },
  { name: "@community/filesystem", label: "@community/filesystem", kind: "mcp", enabled: true, removable: true },
  { name: "document-review", label: "document-review", kind: "skill", enabled: true, removable: true, source_label: "הותקן ידנית" },
  { name: "analyze_project", label: "analyze_project", kind: "skill", enabled: true, removable: false, source_label: "מובנה" },
];
let logs = ["2026-10-04 10:00:00 | INFO | [INFO] Session ready", "2026-10-04 10:00:01 | INFO | [INFO] file_manager: read budget_2027.csv", "2026-10-04 10:00:02 | WARNING | [INFO] Provider disconnected"];
let repaired = false;
let usageCleared = false;
let speech: Json = { is_playing: false, owner_id: null, request_id: null, protocol_version: 1, error: "", core_instance_id: "ux1-demo" };
let sequence = 10;
let workRoot = "workspace:/community";
const terminals = new Map<string, { running: boolean }>();
const browser: BrowserSnapshot = { tabs: [], activeTabId: null, transport: "webview2-in-process-cdp", remoteDebuggingPort: null };
let lastClosed: BrowserTab | undefined;
const browserHistory = new Map<string, { urls: string[]; index: number }>();
const canvas = { id: "demo-plan", title: "תוכנית עבודה למרכז הקהילתי", created_at: "2026-10-03T10:00:00", closed: false, document: '<div dir="rtl" style="font:18px Segoe UI;padding:32px;color:#222a35;background:#f7f8fa"><h1>מרחב לרעיונות ולעבודה</h1><p>תוכנית מפגשים</p><button id="demo-next">תכנן את המפגש הבא</button><p>בחר את הצעד הבא בתוכנית.</p></div>', buttons: [{ id: "demo-next", label: "תכנן את המפגש הבא", action: "message", target: "בנה תוכנית למפגש הבא" }], button_positions: [], remote_images_enabled: false };
export const demoTrace: { command: string; method?: string; path?: string; action?: string; unsupported?: boolean }[] = [];
const feedback = (message: string) => window.dispatchEvent(new CustomEvent("ux1-demo-feedback", { detail: message }));
export function downloadDemo(contents: string, name: string) {
  const url = URL.createObjectURL(new Blob([contents], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function memorySnapshot(url = new URL("http://demo.invalid/")) {
  const query = url.searchParams.get("query") ?? "";
  const status = url.searchParams.get("status") ?? "active";
  const type = url.searchParams.get("memory_type") ?? "any";
  const sensitivity = url.searchParams.get("sensitivity") ?? "any";
  const filtered = memories.filter(item => `${item.subject} ${item.content} ${item.tags}`.includes(query) && (status === "all" || item.status === status) && (type === "any" || item.type === type) && (sensitivity === "any" || item.sensitivity === sensitivity));
  const page = Number(url.searchParams.get("page") || 1);
  return { items: filtered.slice((page - 1) * 8, page * 8).map(item => item.sensitivity === "sensitive" ? { ...item, content: "", masked_content: "•••••• · תוכן רגיש" } : item), page, pages: Math.max(1, Math.ceil(filtered.length / 8)), total: filtered.length, stats: { total: memories.length, active: memories.filter(i => i.status === "active").length, archived: memories.filter(i => i.status === "archive").length, sensitive: memories.filter(i => i.sensitivity === "sensitive").length } };
}
async function core(request: Request): Promise<unknown> {
  const { method } = request; const body = object(request.body);
  const url = new URL(request.path, "http://demo.invalid"); const path = decodeURIComponent(url.pathname);
  if (path === "/v2/settings/schema") return {
    providers: providerOptions.map(p => ({ id: p.value, label: p.label, secret_key: providerSecretKeys[p.value], requires_api_key: !["local", "openai_codex_signin"].includes(String(p.value)), help_url: "https://providers.example/", key_instructions: "הזן את מפתח הספק ובדוק את החיבור." })),
    secret_help: { tavily_api_key: { label: "Tavily", key_instructions: "מפתח לחיפוש ברשת" } },
  };
  if (path === "/v2/settings") { if (method === "PATCH") merge(values, object(body.values)); return settings(); }
  if (path.startsWith("/v2/settings/secrets/")) {
    const key = path.slice(path.lastIndexOf("/") + 1); secrets[key] = { configured: method !== "DELETE", masked: method === "DELETE" ? "" : "••••A1B2" }; return settings();
  }
  if (path === "/v2/audio/tts/voices") return { items: [{ id: "he-demo", name: "עברית" }, { id: "en-demo", name: "English" }] };
  if (path === "/v2/audio/tts/status") return speech;
  if (path === "/v2/audio/tts/stop") { speech = { ...speech, is_playing: false }; return speech; }
  if (path === "/v2/audio/tts") { speech = { ...speech, is_playing: true, owner_id: body.owner_id, request_id: `demo-${++sequence}` }; feedback(""); return speech; }
  if (path === "/v2/runs") return { items: [] };
  if (path.startsWith("/v2/providers/")) {
    const provider = path.split("/")[3];
    if (path.endsWith("/models")) return { models: demoModels(provider), message: "" };
    if (path.endsWith("/reasoning")) { const key = `${provider}:${body.model || url.searchParams.get("model") || ""}`; if (method === "POST") reasoning.set(key, String(body.effort)); return { reasoning_effort: reasoning.get(key) ?? "auto", reasoning_options: ["auto", "low", "medium", "high"].map(value => ({ value, label: value === "auto" ? "אוטומטי" : value })) }; }
    if (path.endsWith("/validate")) {
      if (body.secret === "bad-demo") return { ok: false, models: [], message: "המפתח נדחה. הזן ערך אחר כדי לנסות שוב; המפתח הקודם לא שונה." };
      if (provider === "gemini") window.dispatchEvent(new Event("ux1-provider-connected"));
      return { ok: true, models: demoModels(provider), message: "בדיקת החיבור הצליחה." };
    }
  }
  if (path === "/v2/management/settings/actions") {
    if (body.action === "reset") { for (const key of Object.keys(values)) delete values[key]; merge(values, clone(defaults)); return { ...settings(), backup_path: "workspace:/settings-backup.json" }; }
    if (body.action === "log_clear") logs = ["[INFO] Log cleared"];
    if (body.action === "ssl_import_ca") return { ok: true, path: "workspace:/root-ca.pem", message: "תעודת אישור", metadata: { name: "Smarti CA", expires: "2027-12-31", fingerprint: "D".repeat(64) } };
    return { ok: true, verified: true, state: "signed_in", message: "", ...settings() };
  }
  if (path === "/v2/workbench/root") { if (method === "PATCH") workRoot = String(body.path || workRoot); return { root: { name: "community", path: workRoot }, path: workRoot }; }
  if (path === "/v2/workbench/tree") return { root: { name: "community", path: workRoot }, items: [{ name: "documents", path: `${workRoot}/documents`, kind: "directory", children: [{ name: "plan-2027.md", path: `${workRoot}/documents/plan-2027.md`, kind: "file", size: 4800 }] }, ...["readme.md", "budget_2027.csv", "summary.py"].map(name => ({ name, path: `${workRoot}/${name}`, kind: "file", size: 1200 }))] };
  if (path === "/v2/workbench/file") {
    const file = url.searchParams.get("path") || "plan-2027.md";
    return { name: file.slice(file.lastIndexOf("/") + 1), path: file, kind: file.endsWith(".md") ? "markdown" : "text", mime_type: "text/plain", size: 4800, text: file.endsWith(".csv") ? "category,amount\nmeetings,1200\nequipment,800" : file.endsWith(".py") ? 'summary = {"meetings": 4}\nprint(summary)' : artifactText };
  }
  if (path === "/v2/workbench/artifacts") return { items: [{ name: artifactName, path: `${workRoot}/plan-2027.md`, size: 4800, modified_at: "2026-10-03T10:00:00" }, { name: "summary.py", path: `${workRoot}/summary.py`, size: 72, modified_at: "2026-10-03T10:00:00" }] };
  if (path === "/v2/workbench/open") { feedback(""); return { ok: true }; }
  if (path === "/v2/workbench/terminals" || path.startsWith("/v2/workbench/terminals/")) {
    let id = path.slice(path.lastIndexOf("/") + 1);
    if (path === "/v2/workbench/terminals" || body.action === "restart") { id = `demo-terminal-${++sequence}`; terminals.set(id, { running: true }); return { id }; }
    const session = terminals.get(id) ?? { running: false };
    if (method === "DELETE") session.running = false;
    const text = String(body.text || "");
    const output = body.action === "write" ? (text === "pwd" ? workRoot : text === "ls" || text === "dir" ? "readme.md\nbudget_2027.csv\nsummary.py" : text.startsWith("echo ") ? text.slice(5) : "[INFO] Command accepted.") + "\n" : "";
    return { output, running: session.running };
  }
  if (/^\/v2\/conversations\/[^/]+\/canvases/.test(path)) {
    if (path.endsWith("/canvases")) return { items: [canvas] };
    if (method === "PATCH" && ["close", "reopen"].includes(String(body.action))) canvas.closed = body.action === "close";
    if (method === "POST") { feedback(""); return { ok: true, message: "הפעולה הועברה לשיחה" }; }
    return { canvas: { ...canvas, remote_images_enabled: url.searchParams.get("allow_remote_images") === "true" } };
  }
  if (path === "/v2/browser/legacy-migration") return { status: "applied" };
  if (path === "/v2/browser/import/sources") return { items: [{ id: "demo-edge", browser_id: "edge", browser_name: "Edge", profile_name: "פרופיל אישי" }] };
  if (path === "/v2/browser/import") return { history: [{ url: "https://community.example/", title: "עמוד מיובא" }], bookmarks: [{ url: "https://community.example/", title: "המרכז הקהילתי" }], cookies: [], cookie_stats: { imported: 0 } };
  if (path === "/v2/management/tasks") {
    if (method === "POST") {
      if (body.action === "create") tasks.push({ ...body, id: `task-${++sequence}`, status: "scheduled", run_at: "2026-10-05T09:00:00", target_conversation_id: `demo-task-${sequence}` });
      else if (body.action === "delete") tasks = tasks.filter(t => t.id !== body.id);
      else tasks = tasks.map(t => t.id !== body.id ? t : { ...t, ...(body.action === "edit" ? { prompt: body.prompt } : { status: body.action === "cancel" ? "cancelled" : "scheduled" }) });
    }
    return { items: clone(tasks) };
  }
  if (path === "/v2/management/tools") {
    if (method === "POST") {
      if (body.action === "set_enabled" || body.action === "set_trust") for (const item of [...builtins, ...extensions]) if (item.name === body.name) { item.enabled = body.action === "set_trust" ? body.trusted : body.enabled; if (body.action === "set_trust") item.trusted = body.trusted; }
      if (body.action === "delete") extensions = extensions.filter(i => i.name !== body.name);
      if (String(body.action).startsWith("install_")) extensions.push({ name: String(body.package || `demo-extension-${++sequence}`), label: String(body.package || `demo-extension-${sequence}`), kind: String(body.action).replace("install_", ""), enabled: true, removable: true, source_label: "מותקן" });
    }
    return { builtins: clone(builtins), extensions: clone(extensions) };
  }
  if (path.startsWith("/v2/management/memories/")) {
    const id = path.slice(path.lastIndexOf("/") + 1); const item = memories.find(i => i.id === id);
    if (!item) throw new Error("הרשומה לא נמצאה");
    if (method === "DELETE") memories = memories.filter(i => i.id !== id);
    else if (body.action === "archive" || body.action === "restore") item.status = body.action === "archive" ? "archive" : "active";
    else if (body.action === "pin" || body.action === "unpin") item.pinned = body.action === "pin";
    else if (body.action === "edit" || body.action === "update") merge(item, { ...body, type: body.memory_type ?? item.type });
    return body.action === "details" && item.sensitivity === "sensitive" ? { ...clone(item), content: "", masked_content: "•••••• · תוכן רגיש" } : clone(item);
  }
  if (path === "/v2/management/memories") {
    if (method === "POST") {
      if (body.action === "create") memories.push({ ...body, id: `memory-${++sequence}`, type: body.memory_type, status: "active", sensitivity: "normal", created_at: new Date().toISOString() });
      if (body.action === "clear") memories = [];
      const ids = Array.isArray(body.ids) ? body.ids : [];
      if (body.action === "bulk_delete") memories = memories.filter(i => !ids.includes(i.id));
      if (body.action === "bulk_archive" || body.action === "bulk_restore") memories.forEach(i => { if (ids.includes(i.id)) i.status = body.action === "bulk_archive" ? "archive" : "active"; });
      if (body.action === "export") downloadDemo(JSON.stringify(memories, null, 2), "smarti-memories.json");
      if (body.action === "import") memories.push({ id: `memory-${++sequence}`, subject: "זיכרון מיובא", content: "תוכן מיובא", type: "long_term", status: "active", sensitivity: "normal", tags: [] });
    }
    return memorySnapshot(url);
  }
  if (path === "/v2/management/diagnostics") {
    if (body.action === "repair") repaired = true;
    if (method === "GET") return { current: 3, total: 3, label: "בדיקות תקינות" };
    return { items: [
      { id: "demo-core", title_he: "חיבור Core", explanation_he: "החיבור זמין.", status: "pass", details: { mode: "ready" } },
      { id: "demo-provider", title_he: "הספק מנותק", explanation_he: repaired ? "החיבור זמין" : "אין חיבור לספק. אפשר לבדוק ולחבר מחדש.", status: repaired ? "pass" : "warning", technical_detail: "provider: gemini; code: disconnected", repair_action: { id: "demo-provider", title_he: "חיבור ספק" }, details: { provider: "gemini", code: "disconnected" } },
      { id: "demo-network", title_he: "בדיקת רשת", explanation_he: body.include_network ? "החיבור זמין" : "הבדיקה המלאה מציגה גם רשת", status: body.include_network ? "pass" : "skipped" },
    ] };
  }
  if (path === "/v2/management/logs") return { path: "workspace:/smarti.log", lines: logs.filter(line => line.includes(url.searchParams.get("query") || "")) };
  if (path === "/v2/management/usage") {
    if (method === "DELETE") usageCleared = true;
    const timeframe = url.searchParams.get("timeframe") ?? "all";
    const count = usageCleared ? 0 : timeframe === "today" ? 1200 : 12400;
    return { schema_version: 2, timeframe, total_tokens: count, input_tokens: Math.round(count * .8), output_tokens: Math.round(count * .2), cached_input_tokens: Math.round(count * .15), cache_write_tokens: 0, cost_usd: usageCleared ? 0 : null, known_cost_usd: usageCleared ? 0 : .42, unpriced_models: usageCleared ? 0 : 1, pricing: { cached: true, refreshing: false, updated_at: "2026-10-03T00:00:00" }, models: usageCleared ? [] : [
      { model: "GPT", tokens: Math.round(count * .7), input_tokens: Math.round(count * .5), output_tokens: Math.round(count * .2), cached_input_tokens: 180, cache_write_tokens: 0, cost_usd: .42, cost_status: "estimated" },
      { model: "Codex", tokens: Math.round(count * .2), input_tokens: Math.round(count * .2), output_tokens: 0, cached_input_tokens: 0, cache_write_tokens: 0, cost_usd: null, cost_status: "unavailable" },
      { model: "Local", tokens: Math.round(count * .1), input_tokens: Math.round(count * .1), output_tokens: 0, cached_input_tokens: 0, cache_write_tokens: 0, cost_usd: 0, cost_status: "local" },
    ] };
  }
  if (path === "/v2/management/updates") return { update: { version: "0.88.0", body: "שיפורי יציבות ועדכוני ממשק", releaseUrl: "https://releases.example/" } };
  if (path === "/v2/management/about") return { name: "SmartiAI", version: "0.87.0", description: "מרחב לרעיונות ולעבודה", python: "3.12", contract_version: "v2" };
  throw new Error(`מסלול אינו זמין: ${method} ${path}`);
}

// Deliberately replaces even an existing native bridge: this entry cannot reach
// the personal Core, native filesystem, OS actions, accounts or provider APIs.
export function installDemoBackend() {
  if (!import.meta.env.DEV) throw new Error("UX-1 is development-only");
  for (const name of ["localStorage", "sessionStorage"]) {
    const store = new Map<string, string>();
    const storage: Storage = { get length() { return store.size; }, key: index => [...store.keys()][index] ?? null, getItem: key => store.get(key) ?? null, setItem: (key, value) => { store.set(String(key), String(value)); }, removeItem: key => { store.delete(key); }, clear: () => store.clear() };
    Object.defineProperty(window, name, { value: storage, configurable: true });
  }
  const demoWindow = window as typeof window & { __TAURI_INTERNALS__?: unknown; __TAURI_EVENT_PLUGIN_INTERNALS__?: unknown; __UX1_DEMO__?: unknown };
  demoWindow.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener: () => {} };
  demoWindow.__UX1_DEMO__ = { trace: demoTrace, settings, isolated: true };
  const callbacks = new Map<number, unknown>();
  demoWindow.__TAURI_INTERNALS__ = { metadata: { currentWindow: { label: "ux1-demo" }, currentWebview: { label: "ux1-demo", windowLabel: "ux1-demo" } }, transformCallback: (callback: unknown) => { const id = ++sequence; callbacks.set(id, callback); return id; }, unregisterCallback: (id: number) => callbacks.delete(id), invoke: async (command: string, args: Json = {}) => {
    const request = args.request as Request | undefined;
    const trace = { command, ...(request ? { method: request.method, path: request.path, action: String(request.body?.action || "") } : {}) };
    demoTrace.push(trace);
    try {
      if (command === "core_api" && request) return { status: 200, body: { data: clone(await core(request)) } };
      if (command === "signed_updates_configured") return false;
      if (command === "save_text_file") { downloadDemo(String(args.contents || ""), String(args.suggestedName || "smarti.txt")); return "workspace:/download"; }
      if (command === "pick_management_path") { feedback(""); return args.kind === "directory" ? "workspace:/community" : "workspace:/sample.json"; }
      if (command === "browser_status" || command === "browser_metadata") return clone(browser);
      if (command === "browser_open" || command === "browser_duplicate" || command === "browser_restore_closed") {
        const original = command === "browser_restore_closed" ? lastClosed : browser.tabs.find(t => t.tabId === args.tabId);
        const id = `demo-browser-${++sequence}`;
        const tab: BrowserTab = { tabId: id, workspaceId: String(args.workspaceId || original?.workspaceId || ""), targetId: id, webviewLabel: id, profile: args.profile === "guest" ? "guest" : "persistent", url: String(args.url || original?.url || "https://community.example.invalid"), title: "מרכז קהילתי", loading: false, active: true, crashed: false, pinned: false, faviconUrl: "", audioPlaying: false };
        browser.tabs.push(tab); browser.activeTabId = id; browserHistory.set(id, { urls: [tab.url], index: 0 }); return clone(browser);
      }
      if (command === "browser_activate") { browser.activeTabId = String(args.tabId); return clone(browser); }
      if (command === "browser_navigate") {
        const tab = browser.tabs.find(t => t.tabId === args.tabId); if (tab) { tab.url = String(args.url); const h = browserHistory.get(tab.tabId)!; h.urls = [...h.urls.slice(0, h.index + 1), tab.url]; h.index++; } return clone(browser);
      }
      if (command === "browser_close" || command === "browser_close_workspace") { lastClosed = browser.tabs.find(t => t.tabId === args.tabId); browser.tabs = browser.tabs.filter(t => command === "browser_close" ? t.tabId !== args.tabId : t.workspaceId !== args.workspaceId); browser.activeTabId = browser.tabs[0]?.tabId ?? null; return clone(browser); }
      if (command === "browser_pin") { const tab = browser.tabs.find(t => t.tabId === args.tabId); if (tab) tab.pinned = Boolean(args.pinned); return clone(browser); }
      if (command === "browser_reorder") { const ids = (args.tabIds || args.order || []) as string[]; browser.tabs.sort((a, b) => ids.indexOf(a.tabId) - ids.indexOf(b.tabId)); return clone(browser); }
      if (["browser_reload", "browser_stop", "browser_set_bounds", "browser_set_visible", "browser_clear_profile", "browser_open_devtools"].includes(command)) return clone(browser);
      if (command === "browser_action") {
        const action = object(args.action); const params = object(action.params); const h = browserHistory.get(String(action.tabId));
        if (action.method === "Page.getNavigationHistory") return { result: { currentIndex: h?.index ?? 0, entries: (h?.urls || []).map((url, id) => ({ id, url, title: "המרכז הקהילתי" })) } };
        if (action.method === "Page.navigateToHistoryEntry" && h) { h.index = Number(params.entryId); const tab = browser.tabs.find(t => t.tabId === action.tabId); if (tab) tab.url = h.urls[h.index]; return { result: {} }; }
        if (action.method === "Page.captureScreenshot") { const c = document.createElement("canvas"); c.width = 800; c.height = 500; const ctx = c.getContext("2d")!; ctx.fillStyle = "#f7f8fa"; ctx.fillRect(0, 0, 800, 500); ctx.fillStyle = "#222a35"; ctx.font = "30px Segoe UI"; ctx.fillText("Community workspace", 50, 180); return { result: { data: c.toDataURL(params.format === "jpeg" ? "image/jpeg" : "image/png").split(",")[1] } }; }
        if (action.method === "Page.printToPDF") { feedback(""); return { result: { data: demoPdfBase64() } }; }
        if (action.method === "Runtime.evaluate") return { result: { result: { value: String(params.expression).includes("outerHTML") ? canvas.document : true } } };
        if (["Browser.setPermission", "Network.setUserAgentOverride", "Network.setCookies", "Emulation.setDeviceMetricsOverride", "Emulation.clearDeviceMetricsOverride"].includes(String(action.method))) return { result: {} };
        throw new Error(`פעולת דפדפן חסרה: ${action.method}`);
      }
      if (command === "save_binary_file") { const bytes = args.bytes as number[]; const url = URL.createObjectURL(new Blob([new Uint8Array(bytes)])); const a = document.createElement("a"); a.href = url; a.download = String(args.suggestedName); a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); return "workspace:/download"; }
      if (command === "plugin:event|listen") return ++sequence;
      if (command === "plugin:event|unlisten") return true;
      if (command === "plugin:window|inner_position") return { x: 0, y: 0 };
      if (command === "plugin:window|scale_factor") return 1;
      if (command === "desktop_popup_rtl_menu") return showDemoMenu(args);
      if (command === "desktop_quit") { window.dispatchEvent(new Event("ux1-demo-quit")); feedback(""); return true; }
      if (command === "desktop_diagnostic_snapshot") return { items: [{ id: "demo-desktop", title_he: "מעטפת שולחן העבודה", explanation_he: "המעטפת זמינה.", status: "pass", details: { native: false } }] };
      if (command === "core_status") return { state: "ready", instance_id: "ux1-demo" };
      if (["desktop_set_voice_hotkey", "desktop_set_close_to_tray", "open_chat_link", "desktop_open_with", "plugin:opener|open_url", "restart_after_update", "core_restart"].includes(command)) { feedback(""); return true; }
      throw new Error(`פקודה אינה זמינה: ${command}`);
    } catch (reason) {
      (trace as typeof trace & { unsupported: boolean }).unsupported = true;
      if (command === "core_api") return { status: 501, body: { error: { code: "ux1_missing_fixture", message: String(reason) } } };
      throw reason;
    }
  } };
}

function showDemoMenu(args: Json): Promise<string | null> {
  return new Promise(resolve => {
    const overlay = document.createElement("div"); overlay.className = "ux-native-menu-layer";
    const menu = document.createElement("div"); menu.className = "ux-native-menu"; menu.role = "dialog"; menu.ariaLabel = "תפריט דפדפן"; menu.dir = "rtl";
    const root = document.querySelector(".ux-prototype")!; const close = (id: string | null) => { overlay.remove(); resolve(id); };
    const cancel = document.createElement("button"); cancel.textContent = "סגירה"; cancel.onclick = () => close(null); menu.append(cancel);
    for (const item of (args.items || []) as Json[]) { if (item.separator) { menu.append(document.createElement("hr")); continue; } const button = document.createElement("button"); button.textContent = String(item.text || ""); button.disabled = item.enabled === false; button.onclick = () => close(String(item.id)); menu.append(button); }
    overlay.append(menu); root.append(overlay); overlay.onclick = e => { if (e.target === overlay) close(null); }; overlay.onkeydown = e => { if (e.key === "Escape") close(null); }; cancel.focus();
  });
}

function demoPdfBase64() {
  const stream = "BT /F1 18 Tf 50 750 Td (Community workspace) Tj ET";
  const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`];
  let pdf = "%PDF-1.4\n"; const offsets = [0];
  objects.forEach((object, index) => { offsets.push(pdf.length); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = pdf.length;
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return btoa(pdf);
}
