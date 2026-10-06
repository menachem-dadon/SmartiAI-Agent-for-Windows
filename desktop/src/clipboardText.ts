import { isTauri } from "@tauri-apps/api/core";
import { readText } from "@tauri-apps/plugin-clipboard-manager";

// Called only by explicit paste actions. Native clipboard access avoids the
// browser origin permission prompt; ordinary web previews retain browser rules.
export function readClipboardText(): Promise<string> {
  return isTauri() ? readText() : navigator.clipboard.readText();
}
