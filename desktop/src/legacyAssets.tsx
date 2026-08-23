import type { ResolvedTheme } from "./designSystem";

import logo from "../../assets/logo.png";
import autonomyDark from "../../assets/autonomy_balanced_dark.png";
import autonomyLight from "../../assets/autonomy_balanced_light.png";
import autonomyFullDark from "../../assets/autonomy_full_dark.png";
import autonomyFullLight from "../../assets/autonomy_full_light.png";
import autonomySafeDark from "../../assets/autonomy_safe_dark.png";
import autonomySafeLight from "../../assets/autonomy_safe_light.png";
import copyDark from "../../assets/copy_icon_dark.png";
import copyLight from "../../assets/copy_icon_light.png";
import menuDark from "../../assets/menu_icon_dark.png";
import menuLight from "../../assets/menu_icon_light.png";
import micDark from "../../assets/mic_icon_dark.png";
import micLight from "../../assets/mic_icon_light.png";
import newChatDark from "../../assets/new_chat_icon_dark.png";
import newChatLight from "../../assets/new_chat_icon_light.png";
import plusDark from "../../assets/plus_icon_dark.png";
import plusLight from "../../assets/plus_icon_light.png";
import renameDark from "../../assets/rename_icon_dark.png";
import renameLight from "../../assets/rename_icon_light.png";
import searchDark from "../../assets/search_icon_dark.png";
import searchLight from "../../assets/search_icon_light.png";
import sidebarCollapseDark from "../../assets/sidebar_collapse_icon_dark.png";
import sidebarCollapseLight from "../../assets/sidebar_collapse_icon_light.png";
import sidebarExpandDark from "../../assets/sidebar_expand_icon_dark.png";
import sidebarExpandLight from "../../assets/sidebar_expand_icon_light.png";
import speakerDark from "../../assets/speaker_icon_dark.png";
import speakerLight from "../../assets/speaker_icon_light.png";
import workbenchCloseDark from "../../assets/workbench_close_icon_dark.png";
import workbenchCloseLight from "../../assets/workbench_close_icon_light.png";
import workbenchOpenDark from "../../assets/workbench_open_icon_dark.png";
import workbenchOpenLight from "../../assets/workbench_open_icon_light.png";
import deleteIcon from "../../assets/delete_icon.png";
import exportDark from "../../assets/export_json_icon_dark.png";
import exportLight from "../../assets/export_json_icon_light.png";
import dropdownDark from "../../assets/message_collapse_arrow_dark.png";
import dropdownLight from "../../assets/message_collapse_arrow_light.png";
import sendIcon from "../../assets/send_icon.png";
import stopIcon from "../../assets/stop_agent_icon.png";
import pinDark from "../../assets/pin_icon_dark.png";
import pinLight from "../../assets/pin_icon_light.png";
import unpinDark from "../../assets/unpin_icon_dark.png";
import unpinLight from "../../assets/unpin_icon_light.png";
import agentToolDark from "../../assets/agent_tool_status_dark.png";
import agentToolLight from "../../assets/agent_tool_status_light.png";
import codeDownloadDark from "../../assets/code_download_icon_dark.png";
import codeDownloadLight from "../../assets/code_download_icon_light.png";
import fileDark from "../../assets/file_icon_dark.png";
import fileLight from "../../assets/file_icon_light.png";
import voiceListening from "../../assets/voice_listening.gif";
import voiceOverlayOpenDark from "../../assets/voice_overlay_open_dark.png";
import voiceOverlayOpenLight from "../../assets/voice_overlay_open_light.png";
import closeIcon from "../../assets/close_icon.png";
import aboutDark from "../../assets/about_icon_dark.png";
import aboutLight from "../../assets/about_icon_light.png";
import backDark from "../../assets/back_icon_dark.png";
import backLight from "../../assets/back_icon_light.png";
import doctorDark from "../../assets/doctor_icon_dark.png";
import doctorLight from "../../assets/doctor_icon_light.png";
import memoryDark from "../../assets/memory_management_icon_dark.png";
import memoryLight from "../../assets/memory_management_icon_light.png";
import settingsDark from "../../assets/settings_icon_dark.png";
import settingsLight from "../../assets/settings_icon_light.png";
import tasksDark from "../../assets/task_center_icon_dark.png";
import tasksLight from "../../assets/task_center_icon_light.png";
import toolsDark from "../../assets/tools_icon_dark.png";
import toolsLight from "../../assets/tools_icon_light.png";
import usageDark from "../../assets/usage_icon_dark.png";
import usageLight from "../../assets/usage_icon_light.png";
import folderDark from "../../assets/folder_icon_dark.png";
import folderLight from "../../assets/folder_icon_light.png";
import canvasDark from "../../assets/canvas_card_icon_dark.png";
import canvasLight from "../../assets/canvas_card_icon_light.png";

const themed = <T,>(theme: ResolvedTheme, light: T, dark: T): T => theme === "dark" ? dark : light;

export const legacyAssets = (theme: ResolvedTheme) => ({
  logo,
  autonomy: themed(theme, autonomyLight, autonomyDark),
  autonomyFull: themed(theme, autonomyFullLight, autonomyFullDark),
  autonomySafe: themed(theme, autonomySafeLight, autonomySafeDark),
  copy: themed(theme, copyLight, copyDark),
  menu: themed(theme, menuLight, menuDark),
  mic: themed(theme, micLight, micDark),
  newChat: themed(theme, newChatLight, newChatDark),
  plus: themed(theme, plusLight, plusDark),
  rename: themed(theme, renameLight, renameDark),
  search: themed(theme, searchLight, searchDark),
  sidebarCollapse: themed(theme, sidebarCollapseLight, sidebarCollapseDark),
  sidebarExpand: themed(theme, sidebarExpandLight, sidebarExpandDark),
  speaker: themed(theme, speakerLight, speakerDark),
  workbenchClose: themed(theme, workbenchCloseLight, workbenchCloseDark),
  workbenchOpen: themed(theme, workbenchOpenLight, workbenchOpenDark),
  delete: deleteIcon,
  dropdown: themed(theme, dropdownLight, dropdownDark),
  exportJson: themed(theme, exportLight, exportDark),
  pin: themed(theme, pinLight, pinDark),
  unpin: themed(theme, unpinLight, unpinDark),
  agentTool: themed(theme, agentToolLight, agentToolDark),
  codeDownload: themed(theme, codeDownloadLight, codeDownloadDark),
  file: themed(theme, fileLight, fileDark),
  voiceListening,
  voiceOverlayOpen: themed(theme, voiceOverlayOpenLight, voiceOverlayOpenDark),
  close: closeIcon,
  send: sendIcon,
  stop: stopIcon,
  about: themed(theme, aboutLight, aboutDark),
  back: themed(theme, backLight, backDark),
  doctor: themed(theme, doctorLight, doctorDark),
  memory: themed(theme, memoryLight, memoryDark),
  settings: themed(theme, settingsLight, settingsDark),
  tasks: themed(theme, tasksLight, tasksDark),
  tools: themed(theme, toolsLight, toolsDark),
  usage: themed(theme, usageLight, usageDark),
  folder: themed(theme, folderLight, folderDark),
  canvas: themed(theme, canvasLight, canvasDark),
});

export function LegacyIcon({ src, alt = "", size = 18 }: { src: string; alt?: string; size?: number }) {
  return <img className="legacy-icon" src={src} alt={alt} width={size} height={size} draggable={false} />;
}
