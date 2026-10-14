import { invoke, isTauri } from "@tauri-apps/api/core";
import { prepareStartupIcon, setStartupVisible, startupTheme, updateStartupTheme } from "./startup";
import { loadInterfaceModule, reloadInterface } from "./interfaceModule";
import "./startup.css";
import "./design-system/system.css";

async function boot() {
  const overlay = new URLSearchParams(location.search).get("voice-overlay") === "1";
  const theme = startupTheme();
  updateStartupTheme(theme);
  if (overlay) setStartupVisible(false);
  else {
    const icon = document.getElementById("smarti-startup-icon") as HTMLImageElement;
    await prepareStartupIcon(icon, theme);
    await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    if (isTauri()) await invoke("desktop_present_startup");
  }
  await loadInterfaceModule(() => import("./main"), "entry");
}

void boot().catch(() => {
  console.error("Smarti initial interface failed", { phase: "startup" });
  // This fallback also works when React's own entry module cannot be imported.
  // Use shared styles and fixed product copy; never expose exception/draft data.
  setStartupVisible(false);
  const root = document.getElementById("root")!;
  root.className = "sds-root startup-failure";
  root.dir = "rtl";
  const alert = document.createElement("section");
  alert.className = "sds-alert";
  alert.setAttribute("role", "alert");
  const body = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = "הממשק לא נטען";
  const copy = document.createElement("p");
  copy.textContent = "אפשר לטעון את הממשק מחדש או לסגור את סמארטי.";
  const actions = document.createElement("footer");
  actions.className = "sds-actions";
  for (const [label, callback] of [["טעינת הממשק מחדש", reloadInterface], ["סגירת סמארטי", () => { if (isTauri()) void invoke("desktop_quit"); }]] as const) {
    const button = document.createElement("button");
    button.className = "sds-button";
    button.textContent = label;
    button.addEventListener("click", callback);
    actions.append(button);
  }
  body.append(title, copy, actions);
  alert.append(body);
  root.replaceChildren(alert);
});
