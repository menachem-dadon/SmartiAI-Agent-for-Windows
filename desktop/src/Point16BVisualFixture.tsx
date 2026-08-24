import { LegalAgreement } from "./LegalAgreement";
import { ManagementCenter } from "./ManagementCenter";
import type { ResolvedTheme } from "./designSystem";
import type { ManagementSection } from "./managementCatalog";

type FixtureRequest = { method: string; path: string; body?: unknown };

const fixtureSettings = {
  values: {
    api_mode: "gemini",
    selected_gemini_model: "gemini-3.6-flash",
    favorite_models: [{ provider: "gemini", model: "gemini-3.6-flash" }],
    conversation_title_generation_mode: "ai",
    local_server_url: "http://localhost:1234/v1",
    local_fast_mode_enabled: false,
    ui_preferences: { settings_show_advanced: false, theme_mode: "dark" },
  },
  secrets: {
    gemini_api_key: { configured: true, masked: "••••3092" },
    tavily_api_key: { configured: false, masked: "" },
  },
};

const fixtureSchema = {
  providers: [
    {
      id: "gemini",
      label: "Google Gemini",
      secret_key: "gemini_api_key",
      help_url: "https://aistudio.google.com/apikey",
      key_instructions:
        "התחבר ל-Google AI Studio, לחץ Create API key, בחר או צור פרויקט והעתק את המפתח.",
      requires_api_key: true,
    },
  ],
  secret_help: {
    tavily_api_key: {
      label: "Tavily",
      help_url: "https://app.tavily.com/home",
      key_instructions: "התחבר ל-Tavily Platform והעתק מפתח מהדשבורד.",
    },
  },
};

function installFixtureBackend() {
  const fixtureWindow = window as typeof window & {
    __TAURI_INTERNALS__?: {
      invoke: (
        command: string,
        args?: Record<string, unknown>,
      ) => Promise<unknown>;
    };
  };
  if (fixtureWindow.__TAURI_INTERNALS__) return;
  fixtureWindow.__TAURI_INTERNALS__ = {
    invoke: async (command, args = {}) => {
      if (command !== "core_api") return null;
      const request = (args.request || {}) as FixtureRequest;
      let data: unknown = {};
      if (request.path === "/v2/settings") {
        if (request.method === "PATCH") {
          const body =
            request.body && typeof request.body === "object"
              ? (request.body as { values?: Record<string, unknown> })
              : {};
          Object.assign(fixtureSettings.values, body.values || {});
        }
        data = fixtureSettings;
      } else if (request.path === "/v2/settings/schema") data = fixtureSchema;
      else if (request.path === "/v2/audio/tts/voices")
        data = { items: [{ id: "co.il", name: "גוגל (gTTS)" }] };
      else if (request.path.includes("/models"))
        data = { models: ["gemini-3.6-flash", "gemini-3.6-pro"] };
      else if (request.path.includes("/reasoning"))
        data = { reasoning_effort: "auto", reasoning_options: [] };
      else if (request.path.startsWith("/v2/management/logs"))
        data = {
          path: "C:\\SmartiAI\\smarti_agent.log",
          lines: [
            "2026-08-24 14:00:00 | INFO | SmartiAI fixture contract is ready",
          ],
        };
      else if (request.path === "/v2/management/tools")
        data = {
          builtins: [
            {
              name: "get_tool_info",
              label: "מידע על כלי וסכמות",
              category: "schema",
              category_label: "מידע ועזרה",
              enabled: true,
            },
            {
              name: "file_manager",
              label: "ניהול קבצים",
              category: "files",
              category_label: "קבצים",
              enabled: true,
            },
            {
              name: "extension_manager",
              label: "ניהול הרחבות, MCP ומיומנויות",
              category: "extensions",
              category_label: "הרחבות",
              enabled: true,
            },
          ],
          extensions: [
            {
              kind: "custom",
              name: "project_report",
              label: "project_report",
              enabled: true,
              removable: true,
            },
            {
              kind: "mcp",
              name: "@modelcontextprotocol/server-filesystem",
              label: "@modelcontextprotocol/server-filesystem",
              enabled: false,
              removable: true,
            },
            {
              kind: "skill",
              name: "analyze_project",
              label: "analyze_project",
              source_label: "מובנה",
              enabled: true,
              removable: false,
            },
            {
              kind: "skill",
              name: "document-review",
              label: "document-review",
              source_label: "הותקן ידנית",
              enabled: true,
              removable: true,
            },
          ],
        };
      else if (request.path === "/v2/management/settings/actions")
        data = { ok: true, message: "פעולת fixture הושלמה." };
      return { status: 200, body: { data } };
    },
  };
}

export function Point16BVisualFixture({
  page = "management",
}: {
  page?: "management" | "legal";
}) {
  installFixtureBackend();
  const params = new URLSearchParams(location.search);
  const theme: ResolvedTheme =
    params.get("theme") === "light" ? "light" : "dark";
  const initial = (params.get("section") || "settings_ai") as ManagementSection;
  fixtureSettings.values.ui_preferences.settings_show_advanced =
    params.get("advanced") === "1";
  fixtureSettings.values.ui_preferences.theme_mode = theme;
  if (page === "legal")
    return (
      <LegalAgreement
        status={{
          accepted: false,
          version: "privacy-disclaimer-2026-06-02-v1",
          effective_date: "2026-06-02",
          title: "מדיניות פרטיות ותנאי שימוש",
        }}
        theme={theme}
        onAccepted={async () => {}}
      />
    );
  return (
    <main className={`smarti-app theme-${theme}`} dir="rtl">
      <ManagementCenter
        initial={initial}
        theme={theme}
        setTheme={() => {}}
        onClose={() => {}}
      />
    </main>
  );
}
