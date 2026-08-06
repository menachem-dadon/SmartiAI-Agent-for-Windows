# SmartiAI Agent for Windows

עברית: [מעבר לגרסה העברית](#עברית)

SmartiAI Agent for Windows is a local-first desktop AI agent for practical work on a Windows computer. It combines a Hebrew RTL chat interface, configurable model providers, local memory, file and web tools, browser and desktop automation, email handling, background tasks, notifications, custom tools, MCP packages, and Skills.

Smarti is designed to help operate the computer while keeping the user in control. Sensitive actions are visible, configurable, and can require approval before they run.

Current release target: `V0.87.0`.

## Highlights

- Agentic task execution with planning, step-by-step progress, tool feedback, retries, and final verification.
- Local file work: open files and folders, write text files, read documents, search names and content, analyze images, extract OCR text, attach files to the active model context, and move files to the Recycle Bin.
- Web tools: internet search, webpage reading, browser opening, weather lookup, and website scraping with polite crawl controls.
- Screen context: screenshot capture, screenshot saving, and local image analysis.
- Windows control: discover installed applications, open software, inspect UI elements, invoke buttons, set text fields, send keys/hotkeys, use the clipboard, and manage audio mute state.
- Browser automation through Playwright/CDP against Smarti's persistent Chrome profile, with page-state extraction and form/navigation helpers.
- Email over IMAP/SMTP: search, read, draft, send, reply, forward, archive, trash/delete, move/copy, manage folders, flags, styled RTL/HTML messages, and attachments.
- Background work: one-time and recurring tasks, reminders, retry/cancel/edit flows, Windows toast notifications, and calendar event file creation.
- Local memory with user, short-term, long-term, and tool memory buckets, including expiry and Markdown export.
- Extensibility through custom Python tools, MCP packages, and Skills with controlled install/run permissions.
- Usage tracking, developer logs, runtime traces, audit logs, and optional cost estimates through `litellm`.

## Built-In Tool Areas

| Area | What Smarti can do |
| --- | --- |
| System | Controlled PowerShell, project checks, read-only Git status/diff/log/show, process listing, clipboard updates, and mute/unmute. |
| Software | Index installed Windows applications, find the best match, and open apps. |
| Files | Open, save, read, search, OCR, attach local files to context, and move user files to the Recycle Bin. |
| Web | Search the internet, read URLs, open browser targets, fetch weather, and scrape websites. |
| Screen | Capture, save, and analyze screenshots or local images. |
| Automation | Playwright/CDP browser automation and structured Windows UI Automation. |
| Email | IMAP/SMTP mailbox search, reading, sending, drafts, replies, forwarding, folders, flags, archiving, deletion, and attachments. |
| Tasks & Notifications | Background tasks, recurring work, reminders, Windows toasts, calendar events, and Calendar/Clock/settings launch targets. |
| Memory | Search, add, update, replace, clear, expire, or forget local memories. |
| Extensions | Custom Python tools, MCP package search/install/run, and Skill search/install/run. |

## Example Use Cases

- "Find the newest invoice PDF in Downloads, summarize it, and save the summary."
- "Search this repository for the desktop automation implementation and explain the flow."
- "Open the browser, fill this form, submit it, and tell me what happened."
- "Check unread client emails, draft a professional reply, and leave it for review."
- "Take a screenshot and explain what is visible on the screen."
- "Remind me tomorrow morning to continue this release task."
- "Create a reusable Python tool for this file-processing workflow."
- "Search current web results, read the best source, and summarize it with a link."
- "Remember that I prefer concise Hebrew answers for this project."

## Model Support

Smarti supports multiple providers from the settings screen:

- Google Gemini
- OpenAI
- Anthropic
- OpenRouter
- Groq
- NVIDIA NIM
- Cerebras
- Hugging Face
- DeepSeek
- Alibaba Qwen / DashScope
- Zhipu GLM
- Moonshot Kimi
- Mistral AI
- Together AI
- Perplexity
- xAI
- Local OpenAI-compatible servers, such as LM Studio

API keys can be stored through Keyring or Windows DPAPI. Local OpenAI-compatible servers can be configured without a cloud API key.

## Safety and Control

Smarti is built around explicit control rather than blind automation. Sensitive capabilities are governed by settings, policy checks, and approval prompts. You can enable or disable tool groups, choose autonomy level, require approval for shell commands and extension installs, configure sandbox roots, redact logs, and control cloud-upload behavior.

Actions such as writing files, running commands, controlling the desktop, reading or sending email, using screenshots, installing external tools, or uploading local content to a cloud model are treated as sensitive and may require user approval.

## Quick Start

Requirements for source runs: Windows, Python 3.10 or newer, and Git if you want to use Git tools.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python smarti_core.pyw
```

To run without a console window:

```powershell
pythonw smarti_core.pyw
```

## Optional Capabilities

- Browser automation requires Google Chrome.
- MCP support requires Node.js and `npx` when running from source. Packaged releases include a private Node.js runtime.
- Voice input requires a working microphone, `SpeechRecognition`, `keyboard`, and `PyAudio`.
- OCR requires `pytesseract`, `Pillow`, and a system Tesseract OCR installation available in `PATH`.
- Usage-cost estimates are richer when `litellm` is installed.
- Live Visual Canvas is experimental and off by default. The WebEngine dependency is included in `requirements.txt`; enable **קנבס חזותי מתקדם** under Settings → Tools & Communication → Advanced. It uses an isolated local WebEngine profile; network, external files, downloads, popups, and media permissions are blocked by default. The separate **אפשר תמונות HTTPS מהרשת בתוך קנבס** setting permits HTTPS image resources only; navigation and every other external request remain blocked.
- Packaged releases include a private Python runtime used for custom Python tools, MCP support, and Skill dependency installs.

## Building a Windows Release

The repeatable release recipe lives in `scripts/` and `packaging/`. Build artifacts, downloaded runtimes, and generated installers are ignored by Git.

For the current release:

```powershell
.\scripts\build_release.ps1 -Version 0.87.0
```

The build script:

- verifies that `APP_VERSION` matches the requested release version;
- creates or updates the build virtual environment;
- installs `requirements.txt` and `requirements-build.txt`;
- prepares private Python and Node runtimes and verifies their pinned SHA-256 digests;
- runs `pip check` for the build environment and private runtime;
- packages the app with PyInstaller;
- force-resynchronizes `assets\` into the bundled `_internal\assets` folder and verifies the copied files by SHA-256;
- validates the release layout and installer path lengths;
- creates a portable ZIP and, when Inno Setup 6 is installed, a setup EXE.

For a fully clean rebuild:

```powershell
.\scripts\build_release.ps1 -Version 0.87.0 -Clean -ForceRuntime
```

Release outputs are written to `release\`:

- `SmartiAI-Agent-for-Windows-0.87.0-Setup.exe`
- `SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip`

## Automatic Updates

Smarti checks GitHub Releases, compares the latest release tag against `APP_VERSION`, and downloads the correct Windows asset for the current install type.

For `V0.87.0`, publish a GitHub release tagged `V0.87.0` or `0.87.0` and attach:

- `SmartiAI-Agent-for-Windows-0.87.0-Setup.exe`
- `SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip`

Installed copies prefer a setup EXE. Portable copies prefer a portable ZIP. When GitHub provides a release asset digest, Smarti uses it for SHA-256 verification.

## Project Structure

```text
smarti_core.pyw          Source launcher and main entry point
smarti/                  Modular application code
  app.py                 Startup, splash screen, legal gate, and main window setup
  core.py                Compatibility facade that composes SmartiCore from domain mixins
  agent/                 SmartiCore domain modules: lifecycle, policy, tool calls, automation, email, web, memory, TTS
  runtime.py             Source vs packaged runtime and private toolchain resolution
  config.py              Tool schemas, categories, and default settings
  chat.py                Chat UI, tray behavior, voice input, updates, notifications, and background-task UI
  ui_pages.py            Settings, tools, task center, usage, developer logs, and about pages
  managers.py            Settings migration, memory, policy, audit, MCP, Skills, and tool registries
  workers.py             QThreads for agent work, voice, TTS, model loading, and validation
docs/                    Architecture notes and maintainer-facing documentation
assets/                  Logo, icons, fonts, sounds, and UI assets
packaging/               PyInstaller spec, Inno Setup script, and runtime version recipe
scripts/                 Release build and private runtime preparation scripts
```

## Local Data

On Windows, new installs store runtime data under `%APPDATA%\SmartiAI` by default. Generated output files go to `Documents\Smarti_Outputs` when the Documents folder exists. Legacy project-root runtime files are copied forward on first run and left in place.

Common local files include settings, usage data, memory, chat history, logs, custom tools, MCP tools, Skills, browser session data, and attachment cache data. Sensitive and generated paths are excluded from Git.

## License

Smarti is no longer licensed under the MIT License for new versions.

Starting from version V0.69.0, Smarti is licensed under the:

**PolyForm Noncommercial License 1.0.0**

This means:

- Smarti may be used for personal, educational, research, experimental, hobby, or other noncommercial purposes.
- Smarti may not be used for any commercial purpose without a separate written commercial license from the copyright holder.
- Commercial use includes use by a company, business, startup, contractor, consultant, service provider, paid product, SaaS service, commercial product integration, internal business use, resale, commercial distribution, repackaging, white-labeling, or any use intended to generate revenue or commercial advantage.
- Anyone who wants to use Smarti commercially must obtain prior written permission and a separate commercial license.

Earlier versions of Smarti that were previously published under the MIT License remain available under the MIT License for those specific versions only. This license change applies only to new versions published after this change.

The software is provided as is, without any warranty of any kind. Use of Smarti is entirely at the user's own risk. The copyright holder is not responsible or liable for any damage, data loss, file deletion, malfunction, privacy issue, security incident, financial loss, legal violation, incorrect action by an AI model, incorrect action by a tool, command, script, plugin, Skill, integration, third-party service, or any other harm caused directly or indirectly by installing, using, modifying, distributing, integrating, or operating the software.

Smarti may include or enable autonomous actions, computer control, command execution, file access, network access, third-party tools, artificial intelligence models, and automation of sensitive operations. The user is responsible for reviewing, supervising, limiting permissions, creating backups, using a sandbox or test environment when appropriate, and approving the software's actions.

For the full license terms, see the `LICENSE` file.

---

## עברית

SmartiAI Agent for Windows הוא סוכן AI שולחני לעבודה מעשית על מחשב Windows. הוא משלב ממשק צ'אט עברי מימין לשמאל, ספקי מודלים ניתנים להגדרה, זיכרון מקומי, כלי קבצים ורשת, אוטומציית דפדפן ושולחן עבודה, ניהול אימייל, משימות רקע, התראות, כלים מותאמים אישית, חבילות MCP ו-Skills.

סמארטי נועד לעזור להפעיל את המחשב תוך שמירה על שליטה מלאה של המשתמש. פעולות רגישות מוצגות בצורה שקופה, ניתנות להגדרה, ויכולות לדרוש אישור לפני הרצה.

יעד הגרסה הנוכחי: `V0.87.0`.

## יכולות מרכזיות

- ביצוע משימות Agentic עם תכנון, התקדמות שלב-אחר-שלב, משוב מכלים, ניסיונות חוזרים ואימות סופי.
- עבודה עם קבצים מקומיים: פתיחה, כתיבת קבצי טקסט, קריאת מסמכים, חיפוש לפי שם ותוכן, ניתוח תמונות, OCR, צירוף קבצים להקשר המודל, והעברה לסל המחזור.
- כלי רשת: חיפוש באינטרנט, קריאת דפי אתר, פתיחה בדפדפן, מזג אוויר ו-scraping עם בקרות זחילה מנומסות.
- הקשר מסך: צילום מסך, שמירת צילום מסך וניתוח תמונות מקומיות.
- שליטה ב-Windows: גילוי תוכנות מותקנות, פתיחת אפליקציות, בדיקת רכיבי ממשק, לחיצה על כפתורים, מילוי שדות, שליחת מקשים וקיצורים, שימוש בלוח ההעתקה וניהול מצב השתקת שמע.
- אוטומציית דפדפן דרך Playwright/CDP מול פרופיל Chrome הקבוע של סמארטי, עם חילוץ מצב דף, ניווט ועבודה עם טפסים.
- ניהול אימייל דרך IMAP/SMTP: חיפוש, קריאה, טיוטות, שליחה, תשובה, העברה, ארכוב, מחיקה, העברה/העתקה בין תיקיות, דגלים, הודעות HTML/RTL וקבצים מצורפים.
- עבודה ברקע: משימות חד-פעמיות וחוזרות, תזכורות, עריכה/ביטול/הרצה מחדש, התראות Windows ויצירת קבצי אירוע ליומן.
- זיכרון מקומי עם סוגי זיכרון למשתמש, טווח קצר, טווח ארוך וכלים, כולל תפוגה וייצוא Markdown.
- הרחבות דרך כלי Python מותאמים אישית, חבילות MCP ו-Skills עם בקרות התקנה והרצה.
- מעקב שימוש, לוגים למפתחים, runtime trace, audit log והערכת עלויות אופציונלית דרך `litellm`.

## אזורי כלים מובנים

| תחום | מה סמארטי יכול לעשות |
| --- | --- |
| מערכת | PowerShell מבוקר, בדיקות פרויקט, Git לקריאה בלבד, רשימת תהליכים, לוח העתקה והשתקה/ביטול השתקה. |
| תוכנות | אינדוקס אפליקציות מותקנות, התאמת שם לפתיחה, ופתיחת תוכנות. |
| קבצים | פתיחה, שמירה, קריאה, חיפוש, OCR, צירוף קבצים להקשר והעברה לסל המחזור. |
| רשת | חיפוש באינטרנט, קריאת URL, פתיחה בדפדפן, מזג אוויר ו-scraping. |
| מסך | צילום, שמירה וניתוח של צילומי מסך או תמונות מקומיות. |
| אוטומציה | אוטומציית דפדפן Playwright/CDP ואוטומציית Windows UI מובנית. |
| אימייל | חיפוש, קריאה, שליחה, טיוטות, תשובות, העברה, תיקיות, דגלים, ארכוב, מחיקה וקבצים מצורפים. |
| משימות והתראות | משימות רקע, עבודה חוזרת, תזכורות, התראות Windows, אירועי יומן ופתיחת Calendar/Clock/settings. |
| זיכרון | חיפוש, הוספה, עדכון, החלפה, ניקוי, תפוגה ושכחה של זיכרונות מקומיים. |
| הרחבות | כלי Python מותאמים, חיפוש/התקנה/הרצת MCP, וחיפוש/התקנה/הרצת Skills. |

## דוגמאות שימוש

- "מצא את קובץ החשבונית האחרון ב-Downloads, סכם אותו ושמור את הסיכום."
- "חפש בפרויקט איפה ממומשת אוטומציית שולחן העבודה והסבר את הזרימה."
- "פתח את הדפדפן, מלא את הטופס הזה, שלח אותו וספר לי מה קרה."
- "בדוק הודעות לא נקראות מלקוח, כתוב טיוטת תשובה מקצועית והשאר אותה לבדיקה."
- "צלם את המסך והסבר מה מופיע בו."
- "תזכיר לי מחר בבוקר להמשיך את משימת השחרור הזו."
- "צור כלי Python חוזר לתהליך עיבוד הקבצים הזה."
- "חפש מידע עדכני ברשת, קרא את המקור הכי טוב וסכם עם קישור."
- "זכור שאני מעדיף תשובות עבריות קצרות בפרויקט הזה."

## תמיכה במודלים

סמארטי תומך בספקי מודלים רבים מתוך מסך ההגדרות:

- Google Gemini
- OpenAI
- Anthropic
- OpenRouter
- Groq
- NVIDIA NIM
- Cerebras
- Hugging Face
- DeepSeek
- Alibaba Qwen / DashScope
- Zhipu GLM
- Moonshot Kimi
- Mistral AI
- Together AI
- Perplexity
- xAI
- שרתים מקומיים תואמי OpenAI, כמו LM Studio

אפשר לשמור מפתחות דרך Keyring או Windows DPAPI. שרתים מקומיים תואמי OpenAI יכולים לעבוד ללא מפתח ענן.

## בטיחות ושליטה

סמארטי בנוי סביב שליטה מפורשת ולא אוטומציה עיוורת. יכולות רגישות נשלטות דרך הגדרות, מדיניות פנימית ובקשות אישור. אפשר להפעיל או לכבות קבוצות כלים, לבחור רמת אוטונומיה, לדרוש אישור לפקודות shell ולהתקנת הרחבות, להגדיר שורשי sandbox, לטשטש לוגים ולשלוט בהתנהגות העלאת תוכן מקומי למודל ענן.

פעולות כמו כתיבת קבצים, הרצת פקודות, שליטה בשולחן העבודה, קריאה או שליחה של אימייל, שימוש בצילומי מסך, התקנת כלים חיצוניים או העלאת תוכן מקומי למודל ענן נחשבות רגישות ועשויות לדרוש אישור מפורש.

## התחלה מהירה

דרישות להרצה מהמקור: Windows, Python 3.10 ומעלה, ו-Git אם רוצים להשתמש בכלי Git.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python smarti_core.pyw
```

להרצה ללא חלון קונסול:

```powershell
pythonw smarti_core.pyw
```

## יכולות אופציונליות

- אוטומציית דפדפן דורשת Google Chrome.
- MCP דורש Node.js ו-`npx` בהרצה מהמקור. חבילות הפצה כוללות runtime פרטי של Node.js.
- קלט קולי דורש מיקרופון פעיל, `SpeechRecognition`, `keyboard` ו-`PyAudio`.
- OCR דורש `pytesseract`, `Pillow` והתקנת Tesseract OCR במערכת וזמינות דרך `PATH`.
- הערכות עלות שימוש עשירות יותר כאשר `litellm` מותקן.
- חבילות הפצה כוללות runtime פרטי של Python עבור כלי Python דינמיים, MCP והתקנת דרישות Skills.

## בניית הפצה ל-Windows

מתכון ההפצה נמצא תחת `scripts/` ו-`packaging/`. תוצרי build, runtimes שהורדו וקבצי התקנה נוצרים מקומית ומוחרגים מ-Git.

לגרסה הנוכחית:

```powershell
.\scripts\build_release.ps1 -Version 0.87.0
```

סקריפט הבנייה:

- מוודא ש-`APP_VERSION` תואם לגרסת ההפצה;
- יוצר או מעדכן את סביבת הבנייה;
- מתקין את `requirements.txt` ואת `requirements-build.txt`;
- מכין runtimes פרטיים של Python ו-Node ומאמת את חתימות ה-SHA-256 המקובעות שלהם;
- מריץ `pip check` לסביבת הבנייה ול-runtime הפרטי;
- אורז את האפליקציה עם PyInstaller;
- מסנכרן מחדש את `assets\` אל `_internal\assets` בחבילה ומאמת את הקבצים שהועתקו ב-SHA-256;
- מאמת את מבנה ההפצה ואורכי הנתיבים;
- יוצר ZIP נייד, ואם Inno Setup 6 מותקן גם קובץ Setup.

לבנייה נקייה לחלוטין:

```powershell
.\scripts\build_release.ps1 -Version 0.87.0 -Clean -ForceRuntime
```

התוצרים נכתבים אל `release\`:

- `SmartiAI-Agent-for-Windows-0.87.0-Setup.exe`
- `SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip`

## עדכונים אוטומטיים

סמארטי בודק את GitHub Releases, משווה את תגית הגרסה האחרונה מול `APP_VERSION`, ומוריד את קובץ Windows המתאים לסוג ההתקנה הנוכחי.

עבור `V0.87.0`, יש לפרסם GitHub Release עם תגית `V0.87.0` או `0.87.0` ולצרף:

- `SmartiAI-Agent-for-Windows-0.87.0-Setup.exe`
- `SmartiAI-Agent-for-Windows-0.87.0-win-x64-portable.zip`

עותקים מותקנים יעדיפו קובץ Setup. עותקים ניידים יעדיפו ZIP נייד. כאשר GitHub מספק digest לקובץ release, סמארטי משתמש בו לאימות SHA-256.

## מבנה הפרויקט

```text
smarti_core.pyw          מפעיל מקור ונקודת הכניסה הראשית
smarti/                  קוד האפליקציה המודולרי
  app.py                 פתיחה, מסך Splash, אישור משפטי והכנת החלון הראשי
  core.py                חזית תאימות שמרכיבה את SmartiCore ממודולים תחומיים
  agent/                 מודולי SmartiCore: אתחול, מדיניות, קריאות כלים, אוטומציה, אימייל, web, זיכרון ו-TTS
  runtime.py             זיהוי מקור/הפצה ופתרון runtimes פרטיים
  config.py              סכמות כלים, קטגוריות והגדרות ברירת מחדל
  chat.py                צ'אט, מגש מערכת, קול, עדכונים, התראות וממשק משימות רקע
  ui_pages.py            הגדרות, כלים, מרכז משימות, שימוש, לוגים ואודות
  managers.py            מיגרציית הגדרות, זיכרון, מדיניות, audit, MCP, Skills ורישומי כלים
  workers.py             QThreads לעבודת סוכן, קול, TTS, טעינת מודלים ואימות
docs/                    הערות ארכיטקטורה ותיעוד לתחזוקה
assets/                  לוגו, אייקונים, פונטים, צלילים ונכסי UI
packaging/               מתכון PyInstaller, סקריפט Inno Setup וגרסאות runtime
scripts/                 סקריפטי בנייה והכנת runtime פרטי
```

## נתונים מקומיים

ב-Windows, התקנות חדשות שומרות נתוני Runtime תחת `%APPDATA%\SmartiAI` כברירת מחדל. קבצי פלט נוצרים תחת `Documents\Smarti_Outputs` כאשר תיקיית Documents קיימת. קבצי Runtime ישנים משורש הפרויקט מועתקים קדימה בהפעלה הראשונה ונשארים במקומם.

נתונים מקומיים כוללים הגדרות, שימוש, זיכרון, היסטוריית שיחות, לוגים, כלים מותאמים, כלי MCP, Skills, נתוני סשן דפדפן ומטמון קבצים מצורפים. נתיבים רגישים ונוצרים מוחרגים מ-Git.

## רישיון

סמארטי כבר אינה מופצת ברישיון MIT עבור גרסאות חדשות.

החל מגרסה V0.69.0, סמארטי מופצת תחת:

**PolyForm Noncommercial License 1.0.0**

המשמעות:

- מותר להשתמש בסמארטי לשימוש אישי, לימודי, מחקרי, ניסיוני, תחביבי או לא-מסחרי אחר.
- אסור להשתמש בסמארטי לכל שימוש מסחרי ללא רישיון מסחרי נפרד ובכתב מבעל הזכויות.
- שימוש מסחרי כולל שימוש על ידי חברה, עסק, סטארטאפ, יועץ, נותן שירותים, מוצר בתשלום, שירות SaaS, שילוב במוצר מסחרי, שימוש פנימי בעסק, מכירה, הפצה מסחרית, אריזה מחדש, White Label או כל שימוש שנועד לייצר הכנסה או יתרון מסחרי.
- מי שרוצה להשתמש בסמארטי באופן מסחרי חייב לקבל אישור ורישיון מסחרי נפרד מראש ובכתב.

גרסאות ישנות של סמארטי שפורסמו בעבר תחת רישיון MIT נשארות כפופות לרישיון MIT עבור אותן גרסאות בלבד. שינוי הרישיון חל רק על גרסאות חדשות שפורסמו לאחר שינוי זה.

התוכנה מסופקת כפי שהיא, ללא כל אחריות מכל סוג שהוא. השימוש בסמארטי נעשה באחריות המשתמש בלבד. בעל הזכויות אינו אחראי לכל נזק, אובדן מידע, מחיקת קבצים, תקלה, פגיעה בפרטיות, אירוע אבטחה, הפסד כספי, הפרת חוק, פעולה שגויה של מודל AI, פעולה שגויה של כלי, פקודה, סקריפט, תוסף, Skill, אינטגרציה או שירות צד שלישי, או כל נזק אחר שייגרם במישרין או בעקיפין כתוצאה מהתקנה, שימוש, שינוי, הפצה, שילוב או הפעלה של התוכנה.

סמארטי עשויה לכלול או לאפשר פעולות אוטונומיות, שליטה במחשב, הרצת פקודות, גישה לקבצים, שימוש ברשת, שימוש בכלי צד שלישי, שימוש במודלי בינה מלאכותית ואוטומציה של פעולות רגישות. המשתמש אחראי לבדוק, לפקח, להגביל הרשאות, לבצע גיבויים, להשתמש בסביבת בדיקה לפי הצורך, ולאשר את פעולות התוכנה.

לפרטים המלאים יש לעיין בקובץ `LICENSE`.
