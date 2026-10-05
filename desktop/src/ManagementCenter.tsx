import { useCallback, useEffect, useRef, useState } from "react";
import type { ResolvedTheme, ThemePreference } from "./designSystem";
import { Button, Icon, type IconName } from "./design-system";
import "./management.css";
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
  const [policyOpen, setPolicyOpen] = useState(false);
  const back = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    back.current?.focus();
    return () => { if (previous?.isConnected) previous.focus(); };
  }, []);
  const navigate = (target: ManagementSection) => {
    setPolicyOpen(false);
    setSection(target);
  };
  const goBack = useCallback(() => {
    if (policyOpen) setPolicyOpen(false);
    else onClose();
  }, [policyOpen, onClose]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || document.querySelector('dialog[open], [role="menu"], [role="listbox"]')) return;
      event.preventDefault();
      event.stopPropagation();
      goBack();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [goBack]);
  const backLabel = policyOpen ? "חזרה לאבטחה ופרטיות" : "חזרה לצ׳אט";
  const sectionIcons: Record<ManagementSection, IconName> = {
    tasks: "tasks", memory: "memory", tools: "tools", usage: "usage", workspace: "browser",
    diagnostics: "activity", logs: "code", settings_ai: "plug", settings_security: "shield",
    settings_tools: "mail", settings_appearance: "speaker", settings_advanced: "settings", about: "info",
  };
  return (
    <div
      className="management-overlay"
      role="region"
      aria-label="הגדרות וניהול"
    >
      <header>
        <Button variant="ghost" ref={back} onClick={goBack} icon="forward" aria-label={backLabel}>{backLabel}</Button>
      </header>
      <div className="management-layout">
        <nav aria-label="ניווט הגדרות וניהול">
          {managementNavigation.map((group) => (
            <section key={group.group}>
              <small>{group.group}</small>
              {group.items.map((item) => (
                <Button variant="ghost"
                  key={item.id}
                  className={section === item.id ? "active" : ""}
                  aria-label={item.label}
                  aria-current={section === item.id ? "page" : undefined}
                  onClick={() => navigate(item.id)}
                >
                  <Icon name={sectionIcons[item.id]} />
                  <span>{item.label}</span>
                </Button>
              ))}
            </section>
          ))}
          <Button variant="ghost" className={section === "about" ? "active" : ""} aria-current={section === "about" ? "page" : undefined} onClick={() => navigate("about")} icon="info">אודות והסכמות</Button>
        </nav>
        <main className="management-scroll-viewport">
          <div className="management-content-shell">
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
                onNavigate={navigate}
                policyOpen={policyOpen}
                setPolicyOpen={setPolicyOpen}
                updateControls={<UpdateControls compact theme={theme} />}
              />
            )}
            {section === "about" && <AboutView theme={theme} />}
          </div>
        </main>
      </div>
    </div>
  );
}

export const point16BVisibleSettings = settingDefinitions.map(
  (item) => item.label,
);
