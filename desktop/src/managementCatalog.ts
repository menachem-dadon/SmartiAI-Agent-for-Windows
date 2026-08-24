export type ManagementSection =
  | "workspace"
  | "usage"
  | "tools"
  | "memory"
  | "tasks"
  | "diagnostics"
  | "logs"
  | "settings_ai"
  | "settings_security"
  | "settings_tools"
  | "settings_appearance"
  | "settings_advanced"
  | "about";

export type SettingsSection = Extract<ManagementSection, `settings_${string}`>;
export type SettingControl = "switch" | "segmented" | "text" | "number" | "range" | "select" | "secret" | "directory" | "file";

export type SettingOption = { value: string | number; label: string };
export type SettingDefinition = {
  path: string;
  section: SettingsSection;
  group: string;
  label: string;
  help: string;
  control: SettingControl;
  options?: SettingOption[];
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  advanced?: boolean;
  keywords?: string;
  providerWorkflow?: boolean;
  info?: boolean;
  multiple?: boolean;
};

export const managementNavigation: Array<{
  group: "ניהול" | "הגדרות";
  items: Array<{ id: ManagementSection; label: string; icon?: "tasks" | "memory" | "tools" | "doctor" | "usage" | "policy" }>;
}> = [
  {
    group: "ניהול",
    items: [
      { id: "workspace", label: "סביבת עבודה ודפדפן" },
      { id: "usage", label: "נתוני שימוש", icon: "usage" },
      { id: "tools", label: "כלים וחיבורים", icon: "tools" },
      { id: "memory", label: "זיכרונות", icon: "memory" },
      { id: "tasks", label: "מרכז משימות", icon: "tasks" },
      { id: "diagnostics", label: "Smarti Diagnostic", icon: "doctor" },
      { id: "logs", label: "מעקב למפתחים" },
    ],
  },
  {
    group: "הגדרות",
    items: [
      { id: "settings_ai", label: "מודלי AI וספקים" },
      { id: "settings_security", label: "אבטחה ופרטיות", icon: "policy" },
      { id: "settings_tools", label: "כלים ותקשורת", icon: "tools" },
      { id: "settings_appearance", label: "קול, מראה ומערכת" },
      { id: "settings_advanced", label: "מתקדם ומפתחים" },
    ],
  },
];

const yesNo: SettingOption[] = [
  { value: "allow", label: "אפשר" },
  { value: "ask", label: "שאל בכל פעם" },
  { value: "deny", label: "חסום" },
];

export const policyOptions = yesNo;

export const providerOptions: SettingOption[] = [
  ["gemini", "Google Gemini"], ["openai", "OpenAI"], ["openai_codex_signin", "OpenAI Codex Sign-in"],
  ["anthropic", "Anthropic"], ["openrouter", "OpenRouter"], ["groq", "Groq"], ["nvidia", "NVIDIA NIM"],
  ["cerebras", "Cerebras"], ["huggingface", "Hugging Face"], ["deepseek", "DeepSeek"], ["qwen", "Qwen"],
  ["zhipu", "Zhipu AI"], ["moonshot", "Moonshot AI"], ["mistral", "Mistral AI"], ["together", "Together AI"],
  ["perplexity", "Perplexity"], ["xai", "xAI"], ["local", "שרת מקומי"],
].map(([value, label]) => ({ value, label }));

export const providerSecretKeys: Record<string, string> = {
  gemini: "gemini_api_key", openai: "openai_api_key", anthropic: "anthropic_api_key",
  openrouter: "openrouter_api_key", groq: "groq_api_key", nvidia: "nvidia_api_key",
  cerebras: "cerebras_api_key", huggingface: "huggingface_api_key", deepseek: "deepseek_api_key",
  qwen: "qwen_api_key", zhipu: "zhipu_api_key", moonshot: "moonshot_api_key", mistral: "mistral_api_key",
  together: "together_api_key", perplexity: "perplexity_api_key", xai: "xai_api_key",
};

export const capabilityLabels: Record<string, string> = {
  office_automation: "אוטומציית Microsoft Word מקומית", file_read: "קריאת קבצים מקומיים", file_search: "חיפוש קבצים ותוכן",
  file_write: "כתיבת קבצים", shell: "הרצת פקודות מערכת", python_tool_create: "יצירת כלי מותאם אישית",
  python_tool_run: "הרצת כלי מותאם אישית", mcp_search: "חיפוש כלי MCP", mcp_install: "התקנת כלי MCP",
  mcp_run: "הרצת כלי MCP", skill_search: "חיפוש מיומנויות", skill_install: "התקנת מיומנויות", skill_run: "הרצת מיומנויות",
  network: "גישה לאינטרנט", browser_open: "פתיחת דפדפן גלוי", file_open: "פתיחת קבצים ותיקיות", software_run: "הרצת תוכנה וקבצים",
  browser_automation: "אוטומציית דפדפן", computer_control: "אוטומציית מחשב דרך עץ הנגישות של Windows", email: "דואר אלקטרוני",
  screenshot: "צילום מסך", software_open: "פתיחת תוכנות", background_task: "משימות רקע", background_task_cancel: "ביטול משימות רקע",
  notification_send: "שליחת התראות Windows", calendar_write: "יצירת אירועי יומן", app_open: "פתיחת יישומי Windows",
  settings_open: "פתיחת הגדרות Windows", audio: "שמע והקראה",
};

const field = (definition: SettingDefinition) => definition;
export const settingDefinitions: SettingDefinition[] = [
  field({ path: "api_mode", section: "settings_ai", group: "ספק ומודל", label: "ספק המודל", help: "בחר את שירות ה-AI שסמארטי ישתמש בו לתשובות ולתכנון פעולות.", control: "select", options: providerOptions, keywords: "provider vendor engine gemini openai anthropic local openrouter groq nvidia cerebras huggingface deepseek qwen zhipu moonshot mistral together perplexity xai", providerWorkflow: true }),
  field({ path: "provider_api_key", section: "settings_ai", group: "ספק ומודל", label: "מפתח גישה לספק המודל", help: "מפתח API הוא קוד גישה אישי שמאפשר לסמארטי לשלוח בקשות מאובטחות לספק המודל. הוא נדרש לספקים חיצוניים, נבדק מול הספק לפני שמירה ונשמר כמפתח מוסתר שלא מוצג בלוגים.", control: "secret", keywords: "api key token secret validate connection authentication login billing", providerWorkflow: true }),
  field({ path: "codex_signin", section: "settings_ai", group: "ספק ומודל", label: "חיבור ChatGPT / Codex", help: "התחברות רשמית עם חשבון ChatGPT או Codex. לא נשמרים סיסמה, API key או token בהגדרות של סמארטי.", control: "text", keywords: "openai codex chatgpt sign in oauth login connect disconnect token credential manager", providerWorkflow: true }),
  field({ path: "selected_provider_model", section: "settings_ai", group: "ספק ומודל", label: "מודל", help: "בחירת המודל הפעיל לשיחה. בחירה נשמרת גם כמועדף כדי שאפשר יהיה להחליף אליו במהירות מהצ'אט.", control: "select", keywords: "favorite favourite star quick switch chat model picker spinner llm", providerWorkflow: true }),
  field({ path: "provider_reasoning_effort", section: "settings_ai", group: "ספק ומודל", label: "עוצמת חשיבה", help: "קובעת את עוצמת החשיבה של המודל הפעיל. האפשרויות מותאמות אוטומטית לחוזה של משפחת המודל; בחירה באוטומטית משאירה את השדה ריק ומשתמשת בברירת הספק.", control: "select", keywords: "codex openai gemini anthropic reasoning effort thinking level budget", providerWorkflow: true }),
  field({ path: "conversation_title_generation_mode", section: "settings_ai", group: "ספק ומודל", label: "יצירת כותרת לשיחה", help: "כבר בתחילת השיחה סמארטי מציג שם זמני ייחודי. כברירת מחדל המודל יוצר במקביל כותרת יפה ומדויקת על בסיס הבקשה הראשונה; אפשר לבחור בכותרת מקומית כדי לחסוך פנייה נוספת למודל.", control: "select", options: [{ value: "ai", label: "המודל יוצר כותרת יפה וייחודית" }, { value: "local", label: "כותרת מיידית ללא פנייה למודל" }], keywords: "conversation chat title ai automatic local unique כותרת שיחה אוטומטית מודל" }),
  field({ path: "local_server_url", section: "settings_ai", group: "ספק ומודל", label: "כתובת שרת מקומי למודל מקומי", help: "רלוונטי כשמשתמשים במודל מקומי, למשל דרך LM Studio או שרת תואם OpenAI.", control: "text", keywords: "localhost url" }),
  field({ path: "local_fast_mode_enabled", section: "settings_ai", group: "ספק ומודל", label: "הפעל FastMode למודלים מקומיים", help: "מצמצם את חוזה המערכת ואת קטלוג הכלים הקבוע, וטוען סכמות רק לפי צורך. כל היכולות נשארות זמינות. המצב אינו מופעל כברירת מחדל.", control: "switch" }),
  field({ path: "tavily_api_key", section: "settings_ai", group: "ספק ומודל", label: "מפתח חיפוש באינטרנט (Tavily)", help: "מאפשר לסמארטי לבצע חיפוש אינטרנט כאשר נדרש מידע עדכני.", control: "secret" }),

  field({ path: "autonomy_mode", section: "settings_security", group: "הרשאות", label: "פרופיל בטיחות", help: "קובע כמה סמארטי יכול לפעול לבד: בטוח מבקש יותר אישורים, מאוזן מתאים לרוב העבודה, ואוטונומי מאפשר יותר רצף פעולה.", control: "segmented", options: [{ value: "locked_down", label: "בטוח" }, { value: "balanced", label: "מאוזן" }, { value: "max_autonomy", label: "אוטונומי" }], info: true }),
  field({ path: "custom_permission_profile_enabled", section: "settings_security", group: "הרשאות", label: "התאמה אישית של הרשאות", help: "מאפשר להגדיר הרשאות פרטניות במקום לבחור פרופיל בטיחות כללי.", control: "switch", info: true }),
  field({ path: "sandbox_enabled", section: "settings_security", group: "ארגז חול", label: "הפעל ארגז חול", help: "מגביל את סמארטי לתיקייה אחת. מצב זה מתאים לעבודה בטוחה על פרויקט או תיקייה מוגדרת.", control: "switch", info: true }),
  field({ path: "sandbox_root_dir", section: "settings_security", group: "ארגז חול", label: "תיקיית ארגז החול", help: "בחר את התיקייה שבה סמארטי רשאי לעבוד כאשר ארגז החול פעיל.", control: "directory", info: true }),
  field({ path: "sandbox_allow_read_outside", section: "settings_security", group: "ארגז חול", label: "אפשר קריאה מחוץ לארגז החול", help: "מאפשר לסמארטי לקרוא קבצים מחוץ לארגז החול, אך עדיין חוסם כתיבה, שינוי ומחיקה מחוץ אליו.", control: "switch", advanced: true }),
  field({ path: "default_output_dir", section: "settings_security", group: "קבצים ונתונים", label: "תיקיית ברירת מחדל ליצירת קבצים", help: "כאשר ביקשת ליצור או לשמור קובץ בלי לציין מיקום, סמארטי ישמור אותו כאן. זו לא מגבלת הרשאה ולא ארגז חול.", control: "directory", info: true }),
  field({ path: "write_outside_allowed_dirs_requires_approval", section: "settings_security", group: "קבצים ונתונים", label: "אישור לפני כתיבה מחוץ לתיקיית הפלט", help: "כאשר האפשרות פעילה, סמארטי יבקש אישור לפני כתיבה מחוץ לתיקיית הפלט. באוטונומיה מלאה האפשרות נכבית אוטומטית, אלא אם ארגז חול פעיל.", control: "switch" }),
  field({ path: "require_approval_for_cloud_upload", section: "settings_security", group: "קבצים ונתונים", label: "אישור לפני שליחת נתונים למודל חיצוני", help: "כאשר האפשרות פעילה, סמארטי יבקש אישור לפני שליחת קבצים, צילום מסך או אימייל למודל חיצוני.", control: "switch", info: true }),
  field({ path: "mcp_require_pinned_versions", section: "settings_security", group: "קבצים ונתונים", label: "דרוש גרסה קבועה לכלי MCP", help: "מחייב התקנת כלים חיצוניים בגרסה קבועה, כדי למנוע שינוי לא צפוי בהתנהגות הכלי.", control: "switch", advanced: true }),
  field({ path: "raw_shell_requires_approval", section: "settings_security", group: "קבצים ונתונים", label: "דרוש אישור לפקודות Shell בסיכון גבוה", help: "גם במצב אוטונומי, פקודות מערכת בסיכון גבוה יעצרו לאישור משתמש.", control: "switch", advanced: true }),
  field({ path: "marketplace_install_requires_approval", section: "settings_security", group: "קבצים ונתונים", label: "דרוש אישור להתקנת MCP ומיומנויות", help: "מונע התקנה שקטה של קוד חיצוני חדש ממאגרי MCP או מיומנויות.", control: "switch", advanced: true }),

  field({ path: "enable_browser_automation", section: "settings_tools", group: "כלים מקומיים ותצוגות", label: "שליטה בדפדפן", help: "שולט ב-Smarti Browser המובנה דרך Playwright/CDP. הפרופיל נפרד מדפדפנים אחרים במחשב ושומר התחברויות שבוצעו בו או יובאו אליו.", control: "switch" }),
  field({ path: "enable_computer_control", section: "settings_tools", group: "כלים מקומיים ותצוגות", label: "שליטה במחשב", help: "קריאת עץ הנגישות של Windows ופעולה על רכיבים מזוהים.", control: "switch" }),
  field({ path: "enable_tool_search_catalog", section: "settings_tools", group: "כלים מקומיים ותצוגות", label: "קטלוג חיפוש כלים חכם", help: "מאפשר לסוכן לחפש בקטלוג הכלים הפנימי לפני בחירה, התקנה או יצירת כלי חדש.", control: "switch", info: true }),
  field({ path: "enable_web_canvas", section: "settings_tools", group: "כלים מקומיים ותצוגות", label: "קנבס חזותי", help: "מוסיף קנבס HTML מקומי ומבודד לצד הצ'אט עבור בקשות חזותיות מפורשות בלבד. הקנבס חוסם רשת, קבצים חיצוניים, הורדות וחלונות קופצים.", control: "switch", info: true }),
  field({ path: "enable_canvas_remote_images", section: "settings_tools", group: "כלים מקומיים ותצוגות", label: "אפשר תמונות HTTPS מהרשת בתוך קנבס", help: "מאפשר רק טעינת תמונות HTTPS שנבחרו לקנבס. ניווט, הורדות, קבצים, חלונות קופצים ושאר בקשות הרשת נותרים חסומים.", control: "switch", info: true }),
  field({ path: "enable_skills_beta", section: "settings_tools", group: "מיומנויות", label: "מיומנויות", help: "תהליכי עבודה שמכוונים את סמארטי איך להשתמש בכלים קיימים וב-MCP.", control: "switch", info: true }),
  field({ path: "skill_install_unknown_scan_policy", section: "settings_tools", group: "מיומנויות", label: "מדיניות סריקה לא חד-משמעית של מיומנות", help: "מה לעשות כאשר ClawHub לא מחזיר תשובת סריקה חד-משמעית: לאפשר התקנה עם אזהרה או לחסום.", control: "select", options: [{ value: "allow_with_warning", label: "אפשר עם אזהרה" }, { value: "block", label: "חסום התקנה" }], advanced: true }),
  field({ path: "enable_mcp_clawhub", section: "settings_tools", group: "MCP", label: "חבילות MCP", help: "שימוש בחבילות MCP שמרחיבות את סמארטי, בכפוף להרשאות.", control: "switch", info: true }),
  field({ path: "email_address", section: "settings_tools", group: "אימייל", label: "כתובת אימייל", help: "כתובת האימייל שממנה סמארטי יקרא או ישלח הודעות, אם אישרת שימוש באימייל.", control: "text" }),
  field({ path: "email_password", section: "settings_tools", group: "אימייל", label: "סיסמת אפליקציה לאימייל", help: "סיסמת אפליקציה ייעודית לחשבון האימייל. אל תשתמש בסיסמה הראשית של החשבון.", control: "secret" }),
  field({ path: "email_from_name", section: "settings_tools", group: "אימייל", label: "שם שולח", help: "שם תצוגה אופציונלי שיופיע בשדה From.", control: "text" }),
  field({ path: "email_imap_host", section: "settings_tools", group: "אימייל", label: "IMAP host", help: "ריק = זיהוי אוטומטי לפי כתובת האימייל.", control: "text", advanced: true }),
  field({ path: "email_imap_port", section: "settings_tools", group: "אימייל", label: "IMAP port", help: "ברירת מחדל נפוצה: 993.", control: "number", min: 1, max: 65535, advanced: true }),
  field({ path: "email_imap_ssl", section: "settings_tools", group: "אימייל", label: "Email IMAP SSL", help: "מומלץ להשאיר פעיל לרוב ספקי האימייל.", control: "switch", advanced: true }),
  field({ path: "email_smtp_host", section: "settings_tools", group: "אימייל", label: "SMTP host", help: "ריק = זיהוי אוטומטי לפי כתובת האימייל.", control: "text", advanced: true }),
  field({ path: "email_smtp_port", section: "settings_tools", group: "אימייל", label: "SMTP port", help: "ברירת מחדל נפוצה: 587.", control: "number", min: 1, max: 65535, advanced: true }),
  field({ path: "email_smtp_starttls", section: "settings_tools", group: "אימייל", label: "Email SMTP STARTTLS", help: "מומלץ להשאיר פעיל עבור SMTP בפורט 587.", control: "switch", advanced: true }),
  field({ path: "email_smtp_ssl", section: "settings_tools", group: "אימייל", label: "Email SMTP SSL", help: "הפעל רק אם הספק דורש SMTP SSL ישיר, לרוב בפורט 465.", control: "switch", advanced: true }),
  field({ path: "email_max_attachment_mb", section: "settings_tools", group: "אימייל", label: "גודל מצורף מקסימלי (MB)", help: "מגבלת בטיחות לשליחת קבצים מצורפים.", control: "number", min: 1, max: 100, suffix: "MB", advanced: true }),

  field({ path: "ui_preferences.theme_mode", section: "settings_appearance", group: "מראה", label: "מצב תצוגה", help: "בחר מצב כהה, בהיר או התאמה אוטומטית להגדרת המערכת של Windows.", control: "segmented", options: [{ value: "dark", label: "כהה" }, { value: "system", label: "מערכת" }, { value: "light", label: "בהיר" }] }),
  field({ path: "read_aloud_all", section: "settings_appearance", group: "קול", label: "הקראה קולית לכל התשובות", help: "כאשר האפשרות פעילה, סמארטי יקריא בקול את כל התשובות.", control: "switch" }),
  field({ path: "read_aloud_voice_only", section: "settings_appearance", group: "קול", label: "הקראה קולית רק לאחר זיהוי קולי", help: "כאשר האפשרות פעילה, הקריאה הקולית תופעל בעיקר לאחר פנייה קולית מצד המשתמש.", control: "switch", advanced: true }),
  field({ path: "tts_voice_id", section: "settings_appearance", group: "קול", label: "קול הקראה", help: "בחירת קול עברי. קולות Edge זמינים כאשר חבילת edge-tts מותקנת; Google TTS נשאר כגיבוי.", control: "select", options: [] }),
  field({ path: "tts_volume", section: "settings_appearance", group: "קול", label: "עוצמת הקראה", help: "שולט בעוצמת השמע בזמן ההקראה.", control: "range", min: 0, max: 100, suffix: "%" }),
  field({ path: "voice_sensitivity", section: "settings_appearance", group: "האזנה", label: "רגישות מיקרופון", help: "ערך גבוה מזהה דיבור חלש מהר יותר; בסביבה רועשת כדאי להוריד מעט.", control: "range", min: 1, max: 100, suffix: "%" }),
  field({ path: "voice_pause_threshold", section: "settings_appearance", group: "האזנה", label: "סיום אחרי שקט", help: "כמה זמן של שקט יסיים את ההאזנה וישלח את התמלול לעיבוד.", control: "range", min: 0.3, max: 5, step: 0.1, suffix: "שניות", advanced: true }),
  field({ path: "voice_listen_timeout", section: "settings_appearance", group: "האזנה", label: "המתנה לתחילת דיבור", help: "כמה זמן לחכות לדיבור אחרי הפעלת ההאזנה לפני ביטול.", control: "range", min: 1, max: 30, suffix: "שניות", advanced: true }),
  field({ path: "voice_ambient_noise_duration", section: "settings_appearance", group: "האזנה", label: "כיול רעש רקע לפני האזנה", help: "0 מתחיל הכי מהר. הגדלה משפרת דיוק בסביבה רועשת אבל מוסיפה השהיה.", control: "range", min: 0, max: 3, step: 0.1, suffix: "שניות", advanced: true }),
  field({ path: "voice_dynamic_energy_threshold", section: "settings_appearance", group: "האזנה", label: "התאמת רגישות אוטומטית לרעש רקע", help: "מאפשר לספריית הזיהוי לשנות את סף הרגישות תוך כדי עבודה לפי רעש הרקע.", control: "switch", advanced: true }),
  field({ path: "voice_beep_enabled", section: "settings_appearance", group: "האזנה", label: "צליל בתחילת וסיום האזנה", help: "משמיע צלילי האזנה קצרים מהנכסים בתחילת האזנה, בסיום האזנה ובביטול מחוסר דיבור.", control: "switch", advanced: true }),
  field({ path: "updates_auto_check", section: "settings_appearance", group: "עדכונים", label: "בדוק עדכונים אוטומטית", help: "כשאפשרות זו פעילה, סמארטי בודק עדכונים ברקע אחרי הפתיחה ולאחר מכן פעם בשעה. אם נמצאה גרסה חדשה, כפתור העדכון מופיע בראש הצ'אט.", control: "switch", info: true }),

  field({ path: "ssl_trust_mode", section: "settings_advanced", group: "מתקדם", label: "אמון HTTPS ורשת מסוננת", help: "המצב הפעיל ומקור האמון מוצגים כאן תמיד. אפשר להשתמש במאגר Windows, לייבא תעודת שורש ציבורית של ספק הסינון, או לבחור במפורש תאימות ישנה ללא אימות תעודות.", control: "select", options: [{ value: "system", label: "מאגר התעודות של Windows" }, { value: "custom_ca", label: "תעודת CA מותאמת" }, { value: "legacy_insecure", label: "תאימות ישנה ללא אימות מלא" }], advanced: true, keywords: "ssl tls certificate ca windows trust network filter proxy תעודה סינון רשת" }),
  field({ path: "ssl_custom_ca_path", section: "settings_advanced", group: "מתקדם", label: "קובץ תעודה מותאם", help: "קובץ PEM או CRT שיצורף למאגר האמון.", control: "file", advanced: true }),
  field({ path: "prevent_sleep_during_active_task", section: "settings_advanced", group: "מתקדם", label: "מנע שינה של המחשב בזמן משימה פעילה", help: "משאיר את Windows ער בזמן שסמארטי מבצע משימה פעילה, ומשחרר את הבקשה מיד בסיום או בביטול. המסך עדיין יכול להיכבות.", control: "switch", advanced: true }),
  field({ path: "command_timeout_seconds", section: "settings_advanced", group: "מתקדם", label: "זמן המתנה לפקודות מחשב (שניות)", help: "משך הזמן המקסימלי שסמארטי ימתין לפקודת מערכת לפני עצירה.", control: "number", min: 5, max: 86400, suffix: "שניות", advanced: true }),
  field({ path: "tool_timeout_seconds", section: "settings_advanced", group: "מתקדם", label: "זמן המתנה לכלים מותאמים אישית (שניות)", help: "משך הזמן המקסימלי להרצת כלי מותאם אישית לפני שסמארטי מפסיק אותו.", control: "number", min: 5, max: 86400, suffix: "שניות", advanced: true }),
  field({ path: "mcp_timeout_seconds", section: "settings_advanced", group: "מתקדם", label: "זמן המתנה לכלי MCP (שניות)", help: "משך הזמן המקסימלי שסמארטי ימתין לתשובה מכלי MCP.", control: "number", min: 5, max: 86400, suffix: "שניות", advanced: true }),
  field({ path: "max_total_task_seconds", section: "settings_advanced", group: "מתקדם", label: "זמן כולל מקסימלי למשימה (שניות)", help: "0 פירושו ללא מגבלת זמן כוללת, כך שמשימות יכולות להימשך שעות. ערך חיובי עוצר את המשימה לאחר מספר השניות שהוגדר.", control: "number", min: 0, max: 604800, suffix: "שניות", advanced: true }),
  field({ path: "codex_request_timeout_seconds", section: "settings_advanced", group: "מתקדם", label: "זמן המתנה לתשובת Codex יחידה (שניות)", help: "מתאים גם לרמות חשיבה עמוקות. ברירת המחדל היא 30 דקות; אפשר להגדיל למשימות חריגות.", control: "number", min: 30, max: 86400, suffix: "שניות", advanced: true }),
  field({ path: "permission_notification_timeout_seconds", section: "settings_advanced", group: "מתקדם", label: "זמן הצגת התראת הרשאה (שניות)", help: "0 פירושו ללא הגבלה: חלון ההרשאה והודעת Windows יישארו מסונכרנים עד לאישור או דחייה.", control: "number", min: 0, max: 86400, suffix: "שניות", advanced: true }),
  field({ path: "max_tool_output_chars", section: "settings_advanced", group: "מתקדם", label: "מגבלת תווים בתוצאת כלי", help: "מגביל את אורך פלט הכלים שנשלח חזרה למודל, כדי לשמור על יציבות ועל עלויות נמוכות.", control: "number", min: 1000, max: 1000000, suffix: "תווים", advanced: true }),
  field({ path: "budgets.daily_token_budget", section: "settings_advanced", group: "מתקדם", label: "תקציב טוקנים יומי", help: "0 פירושו ללא מגבלה קשיחה כרגע; הנתון נשמר לשימוש במדיניות תקציב.", control: "number", min: 0, max: 1000000000, advanced: true }),
  field({ path: "budgets.daily_cost_budget_usd", section: "settings_advanced", group: "מתקדם", label: "תקציב עלות יומי בדולר", help: "0 פירושו ללא מגבלה קשיחה כרגע; מוצג למעקב ובקרת עלויות.", control: "number", min: 0, max: 100000, step: 0.01, suffix: "$", advanced: true }),
  field({ path: "max_agent_loops", section: "settings_advanced", group: "מתקדם", label: "מספר סבבי פעולה מקסימלי", help: "קובע כמה פעמים סמארטי יכול לחשוב, לבחור כלי ולעבד תוצאה באותה בקשה. הערך העליון מאפשר עבודה ללא מגבלת סבבים.", control: "range", min: 4, max: 31, advanced: true }),
  field({ path: "background_recurring_catch_up_window_minutes", section: "settings_advanced", group: "מתקדם", label: "הרצת משימה מחזורית אחרי פספוס", help: "כמה זמן אחרי השעה המתוכננת עדיין מותר לסמארטי להריץ משימה שהוחמצה. בקצה הסליידר: ללא הגבלה. לאחר מכן המשימה חוזרת לשעה הקבועה.", control: "range", min: 0, max: 181, suffix: "דקות", advanced: true }),
  field({ path: "enable_developer_trace", section: "settings_advanced", group: "מפתחים ולוגים", label: "הצג Trace למפתחים", help: "שומר Trace פנימי של תכנון, בחירת כלים, תוצאות ביניים ותשובה סופית.", control: "switch", advanced: true }),
  field({ path: "audit_log_enabled", section: "settings_advanced", group: "מפתחים ולוגים", label: "שמור יומן אודיט לפעולות כלים", help: "שומר יומן אודיט מקומי של החלטות הרשאה, התחלת כלים וסיום כלים.", control: "switch", advanced: true }),
  field({ path: "privacy_redact_logs", section: "settings_advanced", group: "מפתחים ולוגים", label: "הסתר מפתחות וסיסמאות בקובצי הלוג", help: "מסתיר מפתחות, סיסמאות ופרטים רגישים מקובצי הלוג ככל האפשר.", control: "switch", advanced: true }),
  field({ path: "mcp_allowed_directories", section: "settings_advanced", group: "מפתחים ולוגים", label: "תיקיות גישה לכלי MCP", help: "שורשי תיקיות שמותר להעביר לכלי MCP כתיאום גישה. כאשר ארגז חול פעיל, ארגז החול גובר על ההגדרה הזו.", control: "directory", advanced: true, multiple: true }),
];

export const settingsSectionTitles: Record<SettingsSection, { title: string; subtitle: string }> = {
  settings_ai: { title: "מודלי AI וספקים", subtitle: "בחירת ספק, מודל, רמת חשיבה וחיבור מאובטח." },
  settings_security: { title: "אבטחה ופרטיות", subtitle: "הרשאות, ארגז חול, תיקיות ומדיניות מידע." },
  settings_tools: { title: "כלים ותקשורת", subtitle: "דפדפן, Windows, Skills, MCP ודואר אלקטרוני." },
  settings_appearance: { title: "קול, מראה ומערכת", subtitle: "ערכת נושא, הקראה, קלט קולי, התראות ועדכונים." },
  settings_advanced: { title: "מתקדם ומפתחים", subtitle: "SSL, זמני ריצה, תקציבי הקשר ולוגים." },
};

export function readSetting(values: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((current, key) => current && typeof current === "object" ? (current as Record<string, unknown>)[key] : undefined, values);
}

export function patchForSetting(values: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const [root, nested] = path.split(".", 2);
  if (!nested) return { [root]: value };
  const current = values[root] && typeof values[root] === "object" ? values[root] as Record<string, unknown> : {};
  return { [root]: { ...current, [nested]: value } };
}

export function matchingSettings(section: SettingsSection, query: string, advanced: boolean): SettingDefinition[] {
  const normalized = query.trim().toLocaleLowerCase("he");
  return settingDefinitions.filter((item) => {
    if (!normalized && item.section !== section) return false;
    if (!normalized && !advanced && item.advanced) return false;
    if (!normalized) return true;
    return `${item.label} ${item.help} ${item.group} ${item.keywords || ""}`.toLocaleLowerCase("he").includes(normalized);
  });
}
