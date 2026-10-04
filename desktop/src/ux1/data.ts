export type RunState = "idle" | "running" | "waiting_for_approval" | "waiting_for_input" | "completed" | "failed" | "cancelled";
export type Theme = "light" | "dark";
export const artifactName = "תוכנית העבודה למרכז הקהילתי — סקירה והמלצות לשנת 2027.md";
export const attachmentName = "community-center_2027_תקציב-ותוכנית-עבודה.pdf";
export const artifactText = `# מקום לעבוד, מרחב להיפגש

תוכנית עבודה למרכז קהילתי · אוקטובר 2026

## הרעיון
מרכז קהילתי טוב נותן מקום ליוזמה. אנחנו מתחילים משלוש פעולות פשוטות: מקשיבים לתושבים, פותחים מרחב למפגש ובודקים מה עובד.

## שלושה מוקדי עבודה
1. מרחב פתוח: שעות קבועות ללמידה, עבודה ומפגש.
2. סדנאות קטנות: קבוצות של עד 12 משתתפים, עם הרשמה פשוטה.
3. קשר רציף: עדכון חודשי בעברית ובאנגלית, עם דרך ברורה לתת משוב.

## Working principles
Start small. Make the next step clear. Measure participation and listen before expanding.

## תוכנית ראשונית
| שלב | פעולה | תוצאה |
| --- | --- | --- |
| הקשבה | שיחות עם תושבים | שלושה צרכים מרכזיים |
| ניסיון | שתי סדנאות פתוחות | משוב ממשתתפים |
| התאמה | שינוי שעות ותוכן | תוכנית מעודכנת |

## שאלות להמשך
אילו שעות נוחות לתושבים? מי ירצה להוביל מפגש? איך נוכל לשמור על נגישות גם למי שאינו משתמש בכלים דיגיטליים?

${Array.from({ length: 12 }, (_, i) => `## הערת עבודה ${i + 1}\nהתחלה ממוקדת מאפשרת לבדוק את איכות המפגש, לתעד את המשוב ולשפר את התוכנית בהדרגה.`).join("\n\n")}`;
const primaryModels = [
  { id: "gpt", provider: "OpenAI", providerId: "openai", modelKey: "gpt-demo", name: "GPT", detail: "כללי · כתיבה וניתוח", connected: true },
  { id: "codex", provider: "OpenAI · חשבון ChatGPT", providerId: "openai_codex_signin", modelKey: "openai_codex_signin-demo", name: "Codex · Reasoning model — Advanced reasoning for software development", detail: "קוד וניתוח · רמת חשיבה לבחירה", connected: true },
  { id: "gemini", provider: "Google", providerId: "gemini", modelKey: "gemini-demo", name: "Gemini", detail: "הספק מנותק", connected: false },
  { id: "local", provider: "מקומי", providerId: "local", modelKey: "local-demo", name: "Local · עברית / English", detail: "מצב מקומי", connected: true },
];
const demoProviderLabels: Record<string, string> = { openai: "OpenAI", openai_codex_signin: "OpenAI · חשבון ChatGPT", gemini: "Google", anthropic: "Anthropic", openrouter: "OpenRouter", groq: "Groq", nvidia: "NVIDIA", cerebras: "Cerebras", huggingface: "Hugging Face", deepseek: "DeepSeek", qwen: "Qwen", zhipu: "Zhipu", moonshot: "Moonshot", mistral: "Mistral", together: "Together", perplexity: "Perplexity", xai: "xAI", local: "מקומי" };
// Same synthetic catalog keys as DemoBackend/provider settings. Favorites added
// there are selectable here; labels and connection state remain demo fixtures.
export const models = [...primaryModels, ...Object.entries(demoProviderLabels).flatMap(([providerId, provider]) => [providerId === "openai" ? "gpt-demo" : `${providerId}-demo`, `${providerId}-reasoning-demo`].filter(modelKey => !primaryModels.some(model => model.providerId === providerId && model.modelKey === modelKey)).map(modelKey => ({ id: `${providerId}/${modelKey}`, provider, providerId, modelKey, name: `${provider} · ${modelKey.includes("reasoning") ? "Reasoning" : "Chat"}`, detail: modelKey.includes("reasoning") ? "מודל חשיבה" : "מודל כללי", connected: providerId !== "gemini" })))];
export const policies = [
  { id: "locked_down", name: "בטוח", detail: "פעולות מוגבלות; אישור לפני פעולות רגישות." },
  { id: "balanced", name: "מאוזן", detail: "עבודה שוטפת, עם אישור לפעולות בעלות השפעה." },
  { id: "max_autonomy", name: "אוטונומי", detail: "יותר פעולות עצמאיות, בכפוף למדיניות הקיימת." },
  { id: "custom", name: "מותאם אישית", detail: "ההרשאות נקבעות במסך המדיניות." },
];
export const conversations = [
  { id: "community", title: "מרחב חדש לקהילה", detail: "תוכנית עבודה · היום", state: "completed" as RunState },
  { id: "research", title: "מחקר לקראת הסדנה", detail: "ממתין לאישור · היום", state: "waiting_for_approval" as RunState },
  { id: "code", title: "Data pipeline / בדיקת קוד", detail: "מקורות וניתוח · אתמול", state: "idle" as RunState },
];
export type Message = { enter?: boolean; id: string; role: "user" | "assistant"; text: string; rich?: boolean; attachments?: string[] };
export const richMarkdown = `
1. **פותחים מרחב.** מפגש שבועי עם מקום ללמידה ולעבודה משותפת.
2. **מתחילים בקטן.** שתי סדנאות ניסיון, ואז משוב והתאמה.
3. **שומרים על קשר.** עדכון חודשי ושאלות קצרות לתושבים.

| שלב | פעולה | מדד | Working note |
| --- | --- | --- | --- |
| הקשבה | שיחות עם תושבים | 12 interviews | Discover needs before planning |
| ניסיון | סדנאות פתוחות | שני מפגשים | Small groups, useful feedback |

\`\`\`python
summary = {"participation": 24, "next_step": "listen, test, improve", "community_feedback": "Make room for everyone — גם בעברית"}
print(summary["next_step"])
\`\`\`
`;
// Same serialized process contract consumed by the product's RichMessage.
export function demoProcess(state: RunState = "completed") {
  const finished = !["running", "waiting_for_approval", "waiting_for_input"].includes(state);
  return { elapsed_seconds: 12, events: [
    { type: "report", text: "אבדוק את מסמך התוכנית ואת טבלת התקציב, ואז אארגן את ההמלצות." },
    { type: "tool_group_finish", group: { id: "demo-plan", action: "agent_planner", label: "תכנון פעולות העבודה" } },
    { type: "tool_start", tools: [
      { tool_call_id: "demo-read-1", action: "file_manager", arguments: { action: "read", path: "workspace:/community/budget_2027.csv" } },
      { tool_call_id: "demo-read-2", action: "file_manager", arguments: { action: "read", path: "workspace:/community/plan-2027.md" } },
    ] },
    { type: "report", text: "קראתי את התקציב. אני משווה את מספר המפגשים לתוכנית העבודה." },
    { type: "tool_finish", results: [
      { tool_call_id: "demo-read-1", action: "file_manager", output: "category,amount\nmeetings,1200\nequipment,800", status: "success" },
      { tool_call_id: "demo-read-2", action: "file_manager", output: "# תוכנית עבודה\nארבעה מפגשים ושתי סדנאות פתוחות", status: "success" },
    ] },
    { type: "tool_start", tools: [{ tool_call_id: "demo-document", action: "document_manager", arguments: { action: "create", format: "markdown", path: "workspace:/community/recommendations.md" } }] },
    ...(finished ? [
      { type: "tool_start", tools: [{ tool_call_id: "demo-browser", action: "browser_automation_manager", arguments: { action: "open", url: "https://community.example/" } }] },
      { type: "tool_finish", results: [{ tool_call_id: "demo-browser", action: "browser_automation_manager", status: "success", output: "עמוד המרכז הקהילתי" }] },
    ] : []),
    ...(finished ? [{ type: "tool_finish", results: [{ tool_call_id: "demo-document", action: "document_manager", status: state === "failed" ? "error" : state === "cancelled" ? "cancelled" : "success", output: state === "failed" ? "שגיאת ספק: provider_unavailable" : state === "cancelled" ? "הפעולה הופסקה" : "נוצר מסמך ובו שלושה מוקדי עבודה וטבלת פעולות" }] }, { type: "report", text: state === "completed" ? "תוכנית העבודה מוכנה. אפשר לפתוח אותה בסביבת העבודה." : "העבודה נעצרה; פרטי הפעולות נשמרו." }] : []),
  ] };
}
export function makeMessages(id: string, count: number): Message[] {
  const older = Array.from({ length: count - 2 }, (_, i): Message => ({
    id: `${id}-${i}`, role: i % 2 ? "assistant" : "user",
    text: i % 2 ? `הערת מחקר ${Math.ceil((i + 1) / 2)}: כדאי להתחיל בניסוי קטן, לאסוף משוב ולעדכן את ההמלצות. Working note: keep the next step clear.` : `נבחן גם את שלב ${Math.floor(i / 2) + 1} בתוכנית. איך נוכל להפוך את המפגש לנגיש יותר?`,
  }));
  return [...older,
    { id: `${id}-brief`, role: "user", text: "בוא נבנה תוכנית עבודה למרכז קהילתי. חשוב לי שההמלצות יהיו מעשיות, ושהמסמך יהיה נוח לקריאה גם בעברית וגם באנגלית." },
    { id: `${id}-result`, role: "assistant", text: "הכנתי כיוון ראשוני שמתחיל באנשים ובמפגש. שלושת מוקדי העבודה הם מרחב פתוח, סדנאות קטנות וקשר רציף עם התושבים.", rich: true },
  ];
}

export const modelDisplayName = (key: string) => models.find(model => model.modelKey === key)?.name || key;
