import { useContext } from "react";
import { IconTheme, rasterIcon } from "../design-system/icons";
export { rasterIcon, toolIcons } from "../design-system/icons";
import { toolIcons, type IconName } from "../design-system/icons";
export type { IconName } from "../design-system/icons";

export const PrototypeTheme = IconTheme;
const legacyNames: Record<string, IconName> = {
  autonomy_balanced: "shield", autonomy_full: "spark", autonomy_safe: "lock", copy_icon: "copy", menu_icon: "more", mic_icon: "mic", new_chat_icon: "newChat", plus_icon: "plus", rename_icon: "rename", search_icon: "search", sidebar_collapse_icon: "panel", sidebar_expand_icon: "panel", speaker_icon: "speaker", workbench_close_icon: "panel", workbench_open_icon: "panel", delete_icon: "trash", export_json_icon: "export", message_collapse_arrow: "chevron", send_icon: "send", stop_agent_icon: "stop", pin_icon: "pin", unpin_icon: "pin", agent_tool_status: "activity", code_download_icon: "download", file_icon: "file", voice_overlay_open: "external", close_icon: "close", canvas_close_icon: "close", about_icon: "info", back_icon: "back", doctor_icon: "activity", memory_management_icon: "memory", settings_icon: "settings", paste_icon: "paste", policy_icon: "shield", reset_icon: "refresh", save_done: "check", star_filled: "starFilled", star_empty: "star", connection_test_icon: "plug", check_updates_icon: "refresh", task_center_icon: "tasks", tools_icon: "tools", usage_icon: "usage", folder_icon: "folder", canvas_card_icon: "canvas", agent_tool_row_chevron: "chevron", theme_light: "sun", theme_dark: "moon",
};
export function candidateIconForAsset(src: string): IconName | undefined {
  const filename = src.split(/[?#]/)[0].split("/").pop()?.replace(/_(light|dark)\.png$/, "").replace(/\.png$/, "");
  if (!filename) return;
  if (filename.startsWith("agent_tool_")) return toolIcons[filename.slice(11)] ?? legacyNames[filename];
  return legacyNames[filename];
}
export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const theme = useContext(PrototypeTheme);
  return <img data-icon={name} className="ux-icon" src={rasterIcon(theme, name)} alt="" width={size} height={size} draggable={false} aria-hidden="true" />;
}
