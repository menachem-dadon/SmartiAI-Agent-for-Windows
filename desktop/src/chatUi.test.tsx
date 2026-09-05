import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { Composer } from "./Composer";
import {
  codeDisplayLanguage,
  formatAgentDuration,
  prepareMessageMarkdown,
  RichMessage,
  safeChatHref,
} from "./RichMessage";
import { agentToolIcon, agentToolIconName } from "./agentToolIcons";
import { WorkbenchSurface } from "./WorkbenchPanels";

const chatStyles = readFileSync(new URL("./App.css", import.meta.url), "utf8");

describe("rich daily chat UI", () => {
  test("formats code-language labels with their conventional casing", () => {
    const html = renderToStaticMarkup(
      <RichMessage
        message={{ role: "assistant", content: "```python\nprint('ok')\n```" }}
      />,
    );

    expect(html).toContain(">Python</span>");
    expect(html).not.toContain(">PYTHON</span>");
    expect(codeDisplayLanguage("js")).toBe("JavaScript");
    expect(codeDisplayLanguage("typescript")).toBe("TypeScript");
    expect(codeDisplayLanguage("html")).toBe("HTML");
    expect(codeDisplayLanguage("php")).toBe("PHP");
    expect(codeDisplayLanguage("powershell")).toBe("PowerShell");
  });

  test("uses a full-width scroll viewport with transparent, non-clipping content gutters", () => {
    expect(chatStyles).toContain("--chat-content-width:");
    expect(chatStyles).toMatch(
      /\.chat-stage\.has-messages\s*\{[^}]*width:\s*100%[^}]*overflow-x:\s*hidden[^}]*overflow-y:\s*auto/s,
    );
    expect(chatStyles).toMatch(
      /\.message-list\s*\{[^}]*width:\s*calc\(var\(--chat-content-width\) \+ 56px\)[^}]*padding:\s*0 28px 10px[^}]*overflow:\s*visible[^}]*background:\s*transparent/s,
    );
    expect(chatStyles).toMatch(
      /\.chat-message-row\s*\{[^}]*overflow:\s*visible/s,
    );
    expect(chatStyles).toMatch(
      /\.composer\s*\{[^}]*width:\s*var\(--chat-content-width\)/s,
    );
    expect(chatStyles).toMatch(
      /\.agent-tool-row pre\s*\{[^}]*width:\s*100%[^}]*max-width:\s*100%[^}]*overflow:\s*auto/s,
    );
  });

  test("keeps compact side surfaces above a visible chat instead of replacing it", () => {
    expect(chatStyles).toMatch(
      /\.workspace\.is-overlay-layout\s*\{[^}]*position:\s*relative[^}]*grid-template-columns:\s*var\(--rail-width\) minmax\(0,1fr\) 0/s,
    );
    expect(chatStyles).toMatch(
      /\.conversation-drawer\s*\{[^}]*position:\s*absolute[^}]*right:\s*0[^}]*width:\s*min\(var\(--drawer-width\)[^}]*transition:\s*clip-path/s,
    );
    expect(chatStyles).toMatch(
      /\.conversation-drawer\.is-rail\s*\{[^}]*clip-path:\s*inset\(0 0 0 calc\(100% - var\(--rail-width\)\)\)/s,
    );
    expect(chatStyles).toMatch(
      /\.conversation-drawer\.is-rail \.drawer-collapse-control\s*\{[^}]*pointer-events:\s*none/s,
    );
    expect(chatStyles).not.toMatch(/transition:[^;}]*(?:grid-template-columns|max-width|flex-basis|backdrop-filter)/);
    expect(chatStyles).not.toContain("will-change: width");
    expect(chatStyles).toMatch(
      /\.workspace\.is-overlay-layout \.workbench\s*\{[^}]*position:\s*absolute[^}]*left:\s*8px[^}]*grid-column:\s*auto[^}]*pointer-events:\s*none[^}]*transform:/s,
    );
    expect(chatStyles).toMatch(
      /\.workspace\.is-overlay-layout \.workbench\.is-open\s*\{[^}]*pointer-events:\s*auto[^}]*transform:\s*translateX\(0\)/s,
    );
    expect(chatStyles).not.toContain(".workspace.is-workbench-narrow .chat-column { visibility: hidden; }");
    const workbenchMotion = chatStyles.match(/\.workspace\.is-overlay-layout \.workbench\s*\{([^}]*)\}/)?.[1];
    expect(workbenchMotion).not.toContain("scale(");
    expect(workbenchMotion).toContain("opacity: 1");
    expect(chatStyles).toContain("--ease-premium:");
    expect(chatStyles).toMatch(
      /\.workspace\.is-overlay-layout \.workspace-overlay-backdrop\.is-active\s*\{[^}]*opacity:\s*1[^}]*pointer-events:\s*auto/s,
    );
  });

  test("keeps the Workbench close control inside its own header", () => {
    const html = renderToStaticMarkup(
      <WorkbenchSurface
        initial={null}
        visible
        restored={{ tabs: [], active: "" }}
        closeIcon="/close.svg"
        sessionId="test"
        onCanvasAction={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(html).toContain('class="ui-icon-button workbench-close-control"');
    expect(html).toContain('aria-label="סגירת סביבת העבודה"');
  });

  test("uses the original per-tool icon mapping with safe fallbacks", () => {
    const publicTools = [
      "get_tool_info",
      "search_tools",
      "system_manager",
      "software_manager",
      "file_manager",
      "web_manager",
      "screen_manager",
      "background_task_manager",
      "notification_manager",
      "memory_manager",
      "canvas_manager",
      "email_manager",
      "browser_automation_manager",
      "computer_automation_manager",
      "document_manager",
      "extension_manager",
      "create_python_tool",
    ] as const;
    for (const action of publicTools)
      expect(agentToolIconName({ action })).toBe(action);

    const fileIcon = agentToolIconName({
      action: "file_manager",
      effective_action: "filesystem_operation",
      arguments: { action: "atomic_write_text" },
    });
    expect(fileIcon).toBe("file_manager");
    expect(agentToolIcon("light", fileIcon)).not.toBe(
      agentToolIcon("light", "row_status"),
    );
    expect(
      agentToolIconName({
        action: "extension_manager",
        arguments: { action: "run_mcp" },
      }),
    ).toBe("mcp");
    expect(
      agentToolIconName({
        action: "extension_manager",
        arguments: { action: "load_skill" },
      }),
    ).toBe("skill");
    expect(agentToolIconName({ action: "unknown_tool" })).toBe("row_status");
  });

  test("renders safe markdown, mixed direction, tool details and message actions", () => {
    const html = renderToStaticMarkup(
      <RichMessage
        message={{
          role: "assistant",
          content: "שלום `C:\\work` <script>alert(1)</script>",
        }}
        events={[
          {
            event_id: 1,
            sequence: 1,
            event_type: "tool_started",
            session_id: "s",
            run_id: "r",
            payload: { tool: "search", arguments: { q: "Smarti" } },
            created_at: "",
          },
        ]}
      />,
    );
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain('dir="ltr"');
    expect(html).toContain("מריץ: search");
    expect(html).toContain("agent-process");
    expect(html).not.toContain("message-meta");
    expect(html).toContain('aria-label="העתק"');
    expect(html).toContain("הקרא בקול");
    expect(html).not.toContain("נסה שוב");
  });

  test("never attaches agent process events to the user message that started a run", () => {
    const html = renderToStaticMarkup(
      <RichMessage
        message={{
          role: "user",
          content: "בצע בדיקה",
          metadata: { run_id: "r" },
        }}
        events={[
          {
            event_id: 1,
            sequence: 1,
            event_type: "tool_started",
            session_id: "s",
            run_id: "r",
            payload: { tool: "search" },
            created_at: "",
          },
        ]}
      />,
    );
    expect(html).not.toContain("agent-process");
    expect(html).not.toContain("מריץ: search");
  });

  test("restores durable reports, tool loops and elapsed work time", () => {
    const html = renderToStaticMarkup(
      <RichMessage
        message={{
          role: "assistant",
          content: "הושלם",
          metadata: {
            agent_process: {
              elapsed_seconds: 65,
              events: [
                { type: "report", text: "בודק את המאגר" },
                {
                  type: "tool_start",
                  tools: [
                    {
                      action: "internet_search",
                      event_id: "one",
                      arguments_text: '{"q":"Smarti"}',
                    },
                  ],
                },
                {
                  type: "tool_finish",
                  results: [
                    {
                      action: "internet_search",
                      event_id: "one",
                      output_text: "נמצא",
                    },
                  ],
                },
              ],
            },
          },
        }}
      />,
    );
    expect(html).toContain("סמארטי עבד 1 דק׳ 05 שנ׳");
    expect(html).toContain("בודק את המאגר");
    expect(html).toContain("הורץ כלי 1");
    expect(html).toContain("internet_search");
    expect(html).toContain("נמצא");
    expect(html.indexOf("agent-process")).toBeLessThan(
      html.indexOf("chat-message chat-message--assistant"),
    );
    expect(formatAgentDuration(3661)).toBe("1 שעה 01 דק׳ 01 שנ׳");
  });

  test("keeps user actions outside the bubble and styles background task prompts", () => {
    const html = renderToStaticMarkup(
      <RichMessage
        message={{
          role: "user",
          content: "בדיקה חוזרת",
          metadata: { triggered_by_background: true },
        }}
      />,
    );
    expect(html).toContain("background-task-badge");
    expect(html).toContain("⚡ משימת רקע");
    expect(html.indexOf("message-actions")).toBeGreaterThan(
      html.lastIndexOf("chat-message--user"),
    );
    expect(html).toMatch(/<\/div><div class="message-actions">/);
  });

  test("projects persisted memory and Canvas metadata into the original message actions", () => {
    const html = renderToStaticMarkup(
      <RichMessage
        message={{
          role: "assistant",
          content: "מוכן",
          metadata: {
            memory_updated: true,
            canvases: [
              {
                id: "canvas-1",
                title: "לוח עבודה",
                created_at: "2026-08-24T01:00:00",
                closed: false,
              },
            ],
          },
        }}
      />,
    );
    expect(html).toContain("הזיכרון עודכן");
    expect(html).toContain("canvas-open-card");
    expect(html).toContain("לוח עבודה");
    expect(html).toContain("פתיחה");
  });

  test("restores safe local-file and internet message links", () => {
    const source =
      "[פתיחת קובץ](file:///C:/Users/Smarti User/Downloads/report.pdf) וגם [אתר](https://example.com)";
    const markdown = prepareMessageMarkdown(source);
    const html = renderToStaticMarkup(
      <RichMessage message={{ role: "assistant", content: source }} />,
    );
    expect(markdown).toContain("Smarti%20User");
    expect(html).toContain(
      'href="file:///C:/Users/Smarti%20User/Downloads/report.pdf"',
    );
    expect(html).toContain('href="https://example.com"');
    expect(safeChatHref("javascript:alert(1)")).toBe("");
  });

  test("renders active-run composer with Hebrew attachment preview and cancellation", () => {
    const html = renderToStaticMarkup(
      <Composer
        running
        attachments={[
          { path: "staged", name: "תמונה בעברית.png", kind: "image" },
        ]}
        onAttachments={() => undefined}
        onSend={async () => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(html).toContain("תמונה בעברית.png");
    expect(html).toContain("הסרת תמונה בעברית.png");
    expect(html).toContain("בקש כל דבר");
    expect(html).toContain('dir="rtl"');
    expect(html).toContain("מאוזן");
    expect(html).toContain("עצירה");
  });

  test("mirrors the original favorite-model and autonomy dropdown pills", () => {
    const html = renderToStaticMarkup(
      <Composer
        attachments={[]}
        provider="gemini"
        model="gemini-2.5-pro"
        favoriteModels={[{ provider: "gemini", model: "gemini-2.5-pro" }]}
        reasoningEffort="high"
        reasoningOptions={[
          { value: "auto", label: "אוטומטי" },
          { value: "high", label: "גבוהה" },
        ]}
        autonomyMode="locked_down"
        onAttachments={() => undefined}
        onSend={async () => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(html).toContain("model-quick-pill");
    expect(html).toContain("gemini 2.5 pro");
    expect(html).toContain("model-provider-submenu");
    expect(html).toContain("Google Gemini");
    expect(html).toContain('aria-haspopup="menu"');
    expect(html).toContain("עוצמת חשיבה");
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("autonomy-quick-pill");
    expect(html).toContain("בטוח");
    expect(html).toContain("אוטונומי");
  });

  test("keeps the source Codex quota card inside the nested favorite-model menu", () => {
    const html = renderToStaticMarkup(
      <Composer
        attachments={[]}
        provider="openai_codex_signin"
        model="Codex default"
        favoriteModels={[
          { provider: "openai_codex_signin", model: "Codex default" },
          { provider: "gemini", model: "gemini-2.5-pro" },
        ]}
        onAttachments={() => undefined}
        onSend={async () => undefined}
        onCancel={() => undefined}
      />,
    );
    expect(html).toContain("codex-quota-card");
    expect(html).toContain("מכסת Codex שנותרה");
    expect(html).toContain("טוען נתוני מכסה");
    expect(html).toContain("OpenAI Codex Sign-in");
    expect(html).toContain("Google Gemini");
  });
});
