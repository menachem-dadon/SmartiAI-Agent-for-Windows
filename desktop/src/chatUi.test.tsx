import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import { Composer } from "./Composer";
import {
  formatAgentDuration,
  prepareMessageMarkdown,
  RichMessage,
  safeChatHref,
} from "./RichMessage";

describe("rich daily chat UI", () => {
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
