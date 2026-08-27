import type { ResolvedTheme } from "./designSystem";

import agentPlannerDark from "../../assets/agent_tool_agent_planner_dark.png";
import agentPlannerLight from "../../assets/agent_tool_agent_planner_light.png";
import backgroundTaskManagerDark from "../../assets/agent_tool_background_task_manager_dark.png";
import backgroundTaskManagerLight from "../../assets/agent_tool_background_task_manager_light.png";
import browserAutomationManagerDark from "../../assets/agent_tool_browser_automation_manager_dark.png";
import browserAutomationManagerLight from "../../assets/agent_tool_browser_automation_manager_light.png";
import canvasManagerDark from "../../assets/agent_tool_canvas_manager_dark.png";
import canvasManagerLight from "../../assets/agent_tool_canvas_manager_light.png";
import computerAutomationManagerDark from "../../assets/agent_tool_computer_automation_manager_dark.png";
import computerAutomationManagerLight from "../../assets/agent_tool_computer_automation_manager_light.png";
import contextCompactionDark from "../../assets/agent_tool_context_compaction_dark.png";
import contextCompactionLight from "../../assets/agent_tool_context_compaction_light.png";
import createPythonToolDark from "../../assets/agent_tool_create_python_tool_dark.png";
import createPythonToolLight from "../../assets/agent_tool_create_python_tool_light.png";
import documentManagerDark from "../../assets/agent_tool_document_manager_dark.png";
import documentManagerLight from "../../assets/agent_tool_document_manager_light.png";
import emailManagerDark from "../../assets/agent_tool_email_manager_dark.png";
import emailManagerLight from "../../assets/agent_tool_email_manager_light.png";
import extensionManagerDark from "../../assets/agent_tool_extension_manager_dark.png";
import extensionManagerLight from "../../assets/agent_tool_extension_manager_light.png";
import fileManagerDark from "../../assets/agent_tool_file_manager_dark.png";
import fileManagerLight from "../../assets/agent_tool_file_manager_light.png";
import finalVerifierDark from "../../assets/agent_tool_final_verifier_dark.png";
import finalVerifierLight from "../../assets/agent_tool_final_verifier_light.png";
import getToolInfoDark from "../../assets/agent_tool_get_tool_info_dark.png";
import getToolInfoLight from "../../assets/agent_tool_get_tool_info_light.png";
import mcpDark from "../../assets/agent_tool_mcp_dark.png";
import mcpLight from "../../assets/agent_tool_mcp_light.png";
import memoryManagerDark from "../../assets/agent_tool_memory_manager_dark.png";
import memoryManagerLight from "../../assets/agent_tool_memory_manager_light.png";
import notificationManagerDark from "../../assets/agent_tool_notification_manager_dark.png";
import notificationManagerLight from "../../assets/agent_tool_notification_manager_light.png";
import rowStatusDark from "../../assets/agent_tool_row_status_dark.png";
import rowStatusLight from "../../assets/agent_tool_row_status_light.png";
import screenManagerDark from "../../assets/agent_tool_screen_manager_dark.png";
import screenManagerLight from "../../assets/agent_tool_screen_manager_light.png";
import searchToolsDark from "../../assets/agent_tool_search_tools_dark.png";
import searchToolsLight from "../../assets/agent_tool_search_tools_light.png";
import skillDark from "../../assets/agent_tool_skill_dark.png";
import skillLight from "../../assets/agent_tool_skill_light.png";
import softwareManagerDark from "../../assets/agent_tool_software_manager_dark.png";
import softwareManagerLight from "../../assets/agent_tool_software_manager_light.png";
import groupStatusDark from "../../assets/agent_tool_status_dark.png";
import groupStatusLight from "../../assets/agent_tool_status_light.png";
import systemManagerDark from "../../assets/agent_tool_system_manager_dark.png";
import systemManagerLight from "../../assets/agent_tool_system_manager_light.png";
import webManagerDark from "../../assets/agent_tool_web_manager_dark.png";
import webManagerLight from "../../assets/agent_tool_web_manager_light.png";

export type AgentToolIconName =
  | "agent_planner"
  | "background_task_manager"
  | "browser_automation_manager"
  | "canvas_manager"
  | "computer_automation_manager"
  | "context_compaction"
  | "create_python_tool"
  | "document_manager"
  | "email_manager"
  | "extension_manager"
  | "file_manager"
  | "final_verifier"
  | "get_tool_info"
  | "mcp"
  | "memory_manager"
  | "notification_manager"
  | "row_status"
  | "screen_manager"
  | "search_tools"
  | "skill"
  | "software_manager"
  | "system_manager"
  | "web_manager";

type ThemePair = { light: string; dark: string };
type ToolDescriptor = Record<string, unknown>;

const ICONS: Record<AgentToolIconName, ThemePair> = {
  agent_planner: { light: agentPlannerLight, dark: agentPlannerDark },
  background_task_manager: {
    light: backgroundTaskManagerLight,
    dark: backgroundTaskManagerDark,
  },
  browser_automation_manager: {
    light: browserAutomationManagerLight,
    dark: browserAutomationManagerDark,
  },
  canvas_manager: { light: canvasManagerLight, dark: canvasManagerDark },
  computer_automation_manager: {
    light: computerAutomationManagerLight,
    dark: computerAutomationManagerDark,
  },
  context_compaction: {
    light: contextCompactionLight,
    dark: contextCompactionDark,
  },
  create_python_tool: { light: createPythonToolLight, dark: createPythonToolDark },
  document_manager: { light: documentManagerLight, dark: documentManagerDark },
  email_manager: { light: emailManagerLight, dark: emailManagerDark },
  extension_manager: { light: extensionManagerLight, dark: extensionManagerDark },
  file_manager: { light: fileManagerLight, dark: fileManagerDark },
  final_verifier: { light: finalVerifierLight, dark: finalVerifierDark },
  get_tool_info: { light: getToolInfoLight, dark: getToolInfoDark },
  mcp: { light: mcpLight, dark: mcpDark },
  memory_manager: { light: memoryManagerLight, dark: memoryManagerDark },
  notification_manager: {
    light: notificationManagerLight,
    dark: notificationManagerDark,
  },
  row_status: { light: rowStatusLight, dark: rowStatusDark },
  screen_manager: { light: screenManagerLight, dark: screenManagerDark },
  search_tools: { light: searchToolsLight, dark: searchToolsDark },
  skill: { light: skillLight, dark: skillDark },
  software_manager: { light: softwareManagerLight, dark: softwareManagerDark },
  system_manager: { light: systemManagerLight, dark: systemManagerDark },
  web_manager: { light: webManagerLight, dark: webManagerDark },
};

const MAIN_TOOL_ICONS = new Set<AgentToolIconName>([
  "agent_planner",
  "background_task_manager",
  "browser_automation_manager",
  "canvas_manager",
  "computer_automation_manager",
  "create_python_tool",
  "document_manager",
  "email_manager",
  "extension_manager",
  "file_manager",
  "get_tool_info",
  "memory_manager",
  "notification_manager",
  "screen_manager",
  "search_tools",
  "software_manager",
  "system_manager",
  "web_manager",
]);
const MCP_ACTIONS = new Set(["search_mcp", "install_mcp", "run_mcp"]);
const SKILL_ACTIONS = new Set([
  "list_skills",
  "search_skills",
  "install_skill",
  "install_skill_requirements",
  "load_skill",
  "run_skill",
]);
const STAGE_ALIASES: Record<string, AgentToolIconName> = {
  agent_verifier: "final_verifier",
  final_verifier: "final_verifier",
  smarti_final_verifier: "final_verifier",
  context_compaction: "context_compaction",
};

const toolName = (value: unknown) => String(value || "").trim();

export function agentToolIconName(item: unknown): AgentToolIconName {
  const tool = item && typeof item === "object" ? (item as ToolDescriptor) : {};
  const action = toolName(tool.action);
  const effective = toolName(tool.effective_action);
  const args =
    tool.arguments && typeof tool.arguments === "object"
      ? (tool.arguments as ToolDescriptor)
      : {};
  const managerAction = toolName(args.action);
  const actionNames = new Set([action, effective, managerAction].filter(Boolean));

  if (action === "extension_manager") {
    if (MCP_ACTIONS.has(managerAction)) return "mcp";
    if (SKILL_ACTIONS.has(managerAction)) return "skill";
  }
  if ([...actionNames].some((name) => MCP_ACTIONS.has(name))) return "mcp";
  if ([...actionNames].some((name) => SKILL_ACTIONS.has(name))) return "skill";

  for (const name of [effective, action]) {
    if (STAGE_ALIASES[name]) return STAGE_ALIASES[name];
    if (MAIN_TOOL_ICONS.has(name as AgentToolIconName))
      return name as AgentToolIconName;
  }
  return "row_status";
}

export function agentToolIcon(
  theme: ResolvedTheme,
  icon: AgentToolIconName,
): string {
  return ICONS[icon][theme];
}

export function agentToolGroupIcon(theme: ResolvedTheme): string {
  return theme === "dark" ? groupStatusDark : groupStatusLight;
}
