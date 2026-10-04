import { createContext, useContext } from "react";
import {
  IconActivity, IconAlertTriangle, IconArchive, IconArrowLeft, IconArrowRight,
  IconArrowUp, IconArrowsMaximize, IconArrowsMinimize, IconBell, IconBook,
  IconBrain, IconBrowser, IconChartBar, IconCheck, IconChecklist, IconChevronDown,
  IconClipboard, IconCode, IconCopy, IconDeviceDesktop, IconDeviceFloppy, IconDots,
  IconDownload, IconExternalLink, IconFile, IconFileExport, IconFolder, IconHistory,
  IconHome, IconInfoCircle, IconLayersIntersect, IconLayoutBoard, IconLayoutSidebarRight,
  IconLoader2, IconLock, IconMail, IconMessagePlus, IconMicrophone, IconMoon,
  IconPencil, IconPin, IconPlayerPause, IconPlayerPlay, IconPlayerStop, IconPlug,
  IconPlus, IconRefresh, IconSearch, IconSettings, IconShield, IconSparkles,
  IconStar, IconStarFilled, IconSun, IconTerminal2, IconTextWrap, IconTools,
  IconTrash, IconUser, IconVolume, IconWorld, IconX,
} from "@tabler/icons-react";
import { foundations, type DesignTheme } from "./tokens";

export const IconTheme = createContext<DesignTheme>("light");
export type IconFamily = "tabler" | "original";
export const IconFamilyContext = createContext<IconFamily>("tabler");
export const iconNames = ["plus", "send", "mic", "stop", "chevron", "search", "settings", "file", "expand", "shrink", "archive", "close", "check", "sun", "moon", "panel", "arrow", "copy", "download", "shield", "spark", "more", "newChat", "pin", "rename", "trash", "export", "speaker", "memory", "folder", "browser", "terminal", "canvas", "tools", "tasks", "usage", "activity", "refresh", "back", "forward", "external", "lock", "info", "star", "starFilled", "save", "wrap", "play", "pause", "user", "home", "history", "mail", "screen", "code", "globe", "bell", "layers", "plug", "paste", "book", "alert", "loader"] as const;
export type IconName = typeof iconNames[number];
// Static imports keep the published SVG geometry and allow Vite to remove unused icons.
// Physical arrow directions match the accepted v7 actions; caller-owned transforms stay intact.
// Both chevron families start down: rotate 90deg for collapsed-left, none for expanded-down.
export const tablerIcons = {
  plus: IconPlus, send: IconArrowUp, mic: IconMicrophone, stop: IconPlayerStop,
  chevron: IconChevronDown, search: IconSearch, settings: IconSettings, file: IconFile,
  expand: IconArrowsMaximize, shrink: IconArrowsMinimize, archive: IconArchive, close: IconX,
  check: IconCheck, sun: IconSun, moon: IconMoon, panel: IconLayoutSidebarRight,
  arrow: IconArrowLeft, copy: IconCopy, download: IconDownload, shield: IconShield,
  spark: IconSparkles, more: IconDots, newChat: IconMessagePlus, pin: IconPin,
  rename: IconPencil, trash: IconTrash, export: IconFileExport, speaker: IconVolume,
  memory: IconBrain, folder: IconFolder, browser: IconBrowser, terminal: IconTerminal2,
  canvas: IconLayoutBoard, tools: IconTools, tasks: IconChecklist, usage: IconChartBar,
  activity: IconActivity, refresh: IconRefresh, back: IconArrowLeft, forward: IconArrowRight,
  external: IconExternalLink, lock: IconLock, info: IconInfoCircle, star: IconStar,
  starFilled: IconStarFilled, save: IconDeviceFloppy, wrap: IconTextWrap, play: IconPlayerPlay,
  pause: IconPlayerPause, user: IconUser, home: IconHome, history: IconHistory,
  mail: IconMail, screen: IconDeviceDesktop, code: IconCode, globe: IconWorld,
  bell: IconBell, layers: IconLayersIntersect, plug: IconPlug, paste: IconClipboard,
  book: IconBook, alert: IconAlertTriangle, loader: IconLoader2,
};
const assets = import.meta.glob<string>("./icons/*.png", { eager: true, query: "?url", import: "default" });
export function rasterIcon(theme: DesignTheme, name: IconName): string { return assets[`./icons/${name}-${theme}.png`]; }
export const actionIcons = { create: "plus", edit: "rename", remove: "trash", refresh: "refresh", copy: "copy", speak: "speaker", send: "send", cancel: "stop", appearanceLight: "sun", appearanceDark: "moon", appearanceSystem: "screen", expand: "expand", collapse: "shrink" } satisfies Record<string, IconName>;
export const toolIcons: Record<string, IconName> = {
  agent_planner: "tasks", background_task_manager: "history", browser_automation_manager: "browser", canvas_manager: "canvas", computer_automation_manager: "screen", context_compaction: "layers", create_python_tool: "code", document_manager: "file", email_manager: "mail", extension_manager: "plug", file_manager: "folder", final_verifier: "check", get_tool_info: "info", mcp: "plug", memory_manager: "memory", notification_manager: "bell", row_status: "check", screen_manager: "screen", search_tools: "search", skill: "book", software_manager: "layers", system_manager: "terminal", web_manager: "globe",
};
export function Icon({ name, size = Number.parseInt(foundations.size.icon), className = "" }: { name: IconName; size?: number; className?: string }) {
  const theme = useContext(IconTheme);
  const family = useContext(IconFamilyContext);
  if (family === "original") return <img className={`sds-icon ${className}`} data-icon={name} data-icon-family={family} src={rasterIcon(theme, name)} width={size} height={size} alt="" aria-hidden="true" draggable={false} />;
  const Svg = tablerIcons[name];
  return <Svg className={`sds-icon ${className}`} data-icon={name} data-icon-family={family} size={size} stroke={2} aria-hidden="true" focusable="false" />;
}
