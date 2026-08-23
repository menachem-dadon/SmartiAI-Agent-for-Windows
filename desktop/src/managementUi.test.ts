import { describe, expect, it } from "vitest";
import management from "./ManagementCenter.tsx?raw";
import workbench from "./WorkbenchPanels.tsx?raw";
import tauriConfig from "../src-tauri/tauri.conf.json";

describe("Points 10-12 management and workbench source parity", () => {
  it("keeps secrets masked and makes reveal explicit", () => {
    expect(management).toContain('type="password"');
    expect(management).toContain("חשיפה מפורשת");
    expect(management).not.toContain("reveal_secret");
  });

  it("exposes all legacy management routes and privacy defaults", () => {
    for (const label of ["מרכז משימות", "ניהול זיכרון", "ניהול כלים", "Smarti Diagnostic", "נתוני שימוש", "Developer Trace", "אודות"]) expect(management).toContain(label);
    expect(management).toContain('useState(false)');
    expect(management).toContain('personal ? "shown" : "hidden"');
  });

  it("keeps the RTL tree on the right and supports independent terminal tabs", () => {
    expect(workbench).toContain("files-split");
    expect(workbench).toContain("TerminalPanel");
    expect(workbench).toContain("/v2/workbench/terminals");
    expect(workbench).toContain('className="files-split"');
    expect(workbench).toContain('dir="ltr"');
    expect(tauriConfig.app.security.csp).toContain("media-src 'self' blob: data:");
    expect(tauriConfig.app.security.csp).toContain("frame-src 'self' blob: data:");
  });

  it("has narrow-window management and workbench rules", () => {
    expect(management).toContain('className="management-layout"');
    expect(management).toContain('className="management-field');
  });
});
