import { useState } from "react";
import type { ResolvedTheme, ThemePreference } from "./designSystem";
import { LegacyIcon, legacyAssets } from "./legacyAssets";
import {
  managementNavigation,
  settingDefinitions,
  type ManagementSection,
  type SettingsSection,
} from "./managementCatalog";
import { SettingsView } from "./SettingsManagement";
import { MemoryView } from "./MemoryManagement";
import {
  AboutView,
  DiagnosticsView,
  LogsView,
  TasksView,
  ToolsView,
  UpdateControls,
  UsageView,
  WorkspaceView,
} from "./ManagementPages";

export function ManagementCenter({
  initial = "settings_ai",
  onClose,
  onOpenWorkbench,
  setTheme,
  theme,
}: {
  initial?: ManagementSection;
  onClose: () => void;
  onOpenWorkbench?: (tab: "browser" | "files") => void;
  setTheme: (theme: ThemePreference) => void;
  theme: ResolvedTheme;
}) {
  const [section, setSection] = useState<ManagementSection>(initial);
  const icons = legacyAssets(theme);
  return (
    <div
      className="management-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="הגדרות וניהול"
    >
      <header>
        <button onClick={onClose} aria-label="חזרה לצ׳אט">
          <LegacyIcon src={icons.back} size={21} />
        </button>
        <h1>הגדרות וניהול</h1>
      </header>
      <div className="management-layout">
        <nav aria-label="ניווט הגדרות וניהול">
          {managementNavigation.map((group) => (
            <section key={group.group}>
              <small>{group.group}</small>
              {group.items.map((item) => (
                <button
                  key={item.id}
                  className={section === item.id ? "active" : ""}
                  onClick={() => setSection(item.id)}
                >
                  {item.icon && <LegacyIcon src={icons[item.icon]} size={19} />}
                  <span>{item.label}</span>
                </button>
              ))}
            </section>
          ))}
        </nav>
        <main>
          {section === "workspace" && (
            <WorkspaceView onOpenWorkbench={onOpenWorkbench} />
          )}
          {section === "tasks" && <TasksView />}
          {section === "memory" && <MemoryView />}
          {section === "tools" && <ToolsView theme={theme} />}
          {section === "diagnostics" && <DiagnosticsView />}
          {section === "usage" && <UsageView />}
          {section === "logs" && <LogsView />}
          {section.startsWith("settings_") && (
            <SettingsView
              section={section as SettingsSection}
              setTheme={setTheme}
              theme={theme}
              onNavigate={setSection}
              updateControls={<UpdateControls compact theme={theme} />}
            />
          )}
          {section === "about" && <AboutView theme={theme} />}
        </main>
      </div>
    </div>
  );
}

export const point16BVisibleSettings = settingDefinitions.map(
  (item) => item.label,
);
