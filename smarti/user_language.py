"""Presentation-only language helpers; never translate model/tool payloads."""
import re


def conversation_language(messages=(), text="", default="he"):
    """Select presentation language from user messages only; never alter content.

    Code, quoted material, paths and terse technical replies do not change the
    established conversation language.
    """
    language = default if default in {"he", "en"} else "he"
    texts = [str(item.get("content") or "") for item in messages
             if isinstance(item, dict) and item.get("role") == "user"]
    if text:
        texts.append(str(text))
    spoken_language = None
    for value in texts:
        value = re.sub(r"```.*?```|`[^`]*`|https?://\S+|[A-Za-z]:\\\S+", " ", value, flags=re.S)
        value = re.sub(r'"[^"\n]*"|“[^”\n]*”', " ", value)
        natural = None
        if re.search(r"[\u0590-\u05ff]", value):
            natural = "he"
        elif len(re.findall(r"\b[A-Za-z]{2,}\b", value.replace("_", ""))) >= 3:
            natural = "en"
        elif spoken_language is None and re.fullmatch(r"[A-Za-z][A-Za-z\s.!?]*", value.strip()):
            natural = "en"
        if natural and (spoken_language is None or natural != spoken_language):
            language = natural
        if natural:
            spoken_language = natural
        # Explicit response-language requests persist while the user's own
        # conversational language stays the same. Translation requests do not match.
        for target, hebrew_name, english_name in (("he", "עברית", "Hebrew"), ("en", "אנגלית", "English")):
            if (re.search(rf"(?:ענה|השב|דבר|תענה|תשיב|תדבר|נמשיך|נעבור)\s+(?:לי\s+)?(?:(?:רק|מעכשיו|מעתה)\s+)?ב{hebrew_name}|(?:עבור|תעבור|נעבור)\s+ל{hebrew_name}", value)
                    or re.search(rf"\b(?:answer|reply|respond|speak|continue)\s+(?:to me\s+)?(?:only\s+)?in {english_name}\b", value, re.I)):
                language = target
    return language


def presentation_text(hebrew, english, language="he"):
    """Select an application-owned caption, never a tool/model/user payload."""
    return english if language == "en" else hebrew


def user_text(core, hebrew, english):
    return presentation_text(hebrew, english, getattr(core, "_current_user_language", "he"))


USER_DESCRIPTIONS = {
    'A brief explanation of why installation is needed': 'הסבר קצר למה ההתקנה נדרשת',
    'A brief explanation to the user of what the command does': 'הסבר קצר למשתמש למה הפקודה עושה',
    'A brief reason why the task warrants planning.': 'סיבה קצרה למה המשימה מצדיקה תכנון.',
    'A test command such as pytest, npm test, python -m pytest, or npm run build': 'פקודת בדיקה כגון pytest, npm test, python -m pytest או npm run build',
    'An array of numbers from 0 (Monday) to 6 (Sunday) specifying execution weekdays when repeat=weekly': 'מערך של מספרים מ-0 (יום שני) עד 6 (יום ראשון) המייצג את ימי השבוע להרצה כאשר repeat=weekly',
    'Attaches a local image to the current agent-loop context. The agent analyzes it itself afterwards; there is no separate AI call.': 'מצרף תמונה מקומית להקשר של לולאת הסוכן הנוכחית. הסוכן מנתח אותה בעצמו בהמשך; אין קריאת AI נפרדת.',
    'Cancel a background task.': 'ביטול משימת רקע.',
    'Cancels a background task by ID.': 'מבטל משימת רקע לפי מזהה.',
    "Captures and sends the user's current screen to you (the model) to understand the context.": 'מצלם ומעביר אליך (המודל) את המסך הנוכחי של המשתמש להבנת ההקשר.',
    'Checks weather and forecasts for any city or location worldwide using open weather services, without an API key.': 'בודק מזג אוויר ותחזית לכל עיר או מיקום בעולם באמצעות שירותי מזג אוויר פתוחים, ללא מפתח API.',
    'City or location name, in Hebrew or English': 'שם עיר או מיקום, בעברית או באנגלית',
    'Computer vision for a local file.': 'ראייה ממוחשבת לקובץ מקומי.',
    'Control computer audio muting.': 'שליטה בהשתקת השמע במחשב.',
    'Conversation routing: current returns every run to the source conversation where the task was scheduled; new creates a new clean conversation each run; dedicated creates a dedicated conversation on the first run and reuses it for all subsequent cycles.': 'אופן ניתוב השיחה: current מחזיר כל הרצה לשיחת המקור שממנה המשימה תוזמנה; new יוצר שיחה חדשה ונקייה בכל הרצה; dedicated יוצר שיחה ייעודית חדשה בהרצה הראשונה ומשתמש בה שוב בכל המחזורים הבאים.',
    'Copies text to the Windows clipboard.': 'מעתיק טקסט ללוח הגזירים של Windows.',
    'Copy text to the clipboard.': 'העתקת טקסט ללוח הגזירים.',
    'Creates a custom Python tool from code and a parameter schema.': 'יוצר כלי פייתון מותאם אישית מתוך קוד וסכמת פרמטרים.',
    'Creates and saves a generic reusable Python tool in the repository. Create general parameterized code, not one-time code for a specific task.': 'יוצר ושומר כלי פייתון גנרי ורב-פעמי למאגר. חובה ליצור קוד כללי שמקבל פרמטרים ולא קוד חד-פעמי למשימה ספציפית.',
    'Deep search for text inside files.': 'חיפוש עמוק של טקסט בתוך קבצים.',
    'Deeply scans text/code files in a given directory for keywords.': 'סורק עמוק בתוך קבצי טקסט/קוד בתיקייה מסוימת ומאתר מילות מפתח.',
    'Desired number of results': 'כמות תוצאות רצויה',
    'ERROR: The tool schema is not a valid object schema.': 'ERROR: סכמת הכלי אינה סכמת object חוקית.',
    'English search terms for the desired MCP package': 'מילות חיפוש באנגלית לחבילת ה-MCP הרצויה',
    'Estimated risk level.': 'רמת סיכון משוערת.',
    'Execute functions from installed external tools.': 'הפעלת פונקציות מכלים חיצוניים שהותקנו.',
    'Executes a function from installed MCP as part of an organized workflow.': 'מפעיל פונקציה מתוך MCP מותקן כחלק מתהליך עבודה מסודר.',
    'Fast, current web search using a search engine. Returns online results.': 'חיפוש מהיר ועדכני ברשת באמצעות מנוע חיפוש. מחזיר תוצאות מקוונות.',
    'Forecast days to return, 1 to 7. Use 2 for tomorrow': 'מספר ימי תחזית להחזיר, 1 עד 7. עבור מחר השתמש ב-2',
    'Full path to a file or folder to move to the recycle bin': 'נתיב מלא לקובץ או לתיקייה להעברה לסל המחזור',
    'Full path to the file': 'נתיב מלא לקובץ',
    'Full path to the file/folder': 'נתיב מלא לקובץ/תיקייה',
    'Full path to the image file': 'נתיב מלא לקובץ התמונה',
    'Generic weather and forecasts for any city or location.': 'מזג אוויר ותחזית גנרית לכל עיר או מיקום.',
    "Install a Skill's external requirements.": 'התקנת דרישות חיצוניות של Skill.',
    'Install a Skill.': 'התקנת Skill.',
    'Installs a Skill. The agent may install only from ClawHub; the user may manually install from a local directory if authorized.': 'מתקין Skill. הסוכן רשאי להתקין רק מ-ClawHub; המשתמש יכול להתקין ידנית מתיקייה מקומית אם אישר זאת.',
    'Installs an MCP package (server) that adds new capabilities. A pinned version is required, e.g. package@1.2.3 or @scope/package@1.2.3.': 'התקנת חבילת MCP (שרת) שמוסיפה יכולות חדשות למערכת. חובה להשתמש בגרסה נעולה, למשל package@1.2.3 או @scope/package@1.2.3.',
    'Installs declared external Skill requirements, such as a CLI or Python package, only after user approval.': 'מתקין דרישות חיצוניות מוצהרות של Skill, כגון CLI או חבילת Python, רק לאחר אישור משתמש.',
    'Internal tool for requesting task planning, continuation planning, or replanning. Use it at your discretion only when explicit planning improves quality or safety. If the workspace, files, code, windows, system state, tool schema, existing content, or previous result is uncertain, the plan must start with brief discovery before a mutating action. Call again when new information, repeated errors, verification failures, or environmental changes show the previous plan is no longer suitable.': 'כלי פנימי לבקשת תכנון משימה, תכנון המשכי או תכנון מחדש. השתמש בו לפי שיקול דעתך רק כאשר תכנון מפורש ישפר איכות או בטיחות. אם יש אי-ודאות לגבי סביבת העבודה, קבצים, קוד, חלונות, מצב מערכת, סכמת כלי, תוכן קיים או תוצאה קודמת, התוכנית חייבת להתחיל ב-discovery קצר לפני פעולה משנה. ניתן לקרוא שוב לכלי כאשר מידע חדש, שגיאות חוזרות, כשלי אימות או שינויי סביבה מראים שהתוכנית הקודמת כבר אינה מתאימה.',
    'List active processes.': 'הצגת תהליכים פעילים.',
    'List available Skills.': 'הצגת Skills זמינים.',
    'List background tasks.': 'הצגת משימות רקע.',
    'List installed software.': 'הצגת תוכנות מותקנות.',
    'Lists active processes in read-only mode.': 'מציג רשימת תהליכים פעילים באופן קריאה בלבד.',
    'Lists available Skills, including built-in, local, and ClawHub-installed Skills.': 'מציג Skills זמינים, כולל Skills מובנים, מקומיים ו-Skills שהותקנו מ-ClawHub.',
    'Lists background tasks, status, execution time, and latest result.': 'מציג את משימות הרקע, סטטוס, זמן ריצה ותוצאה אחרונה.',
    'Lists software installed on the computer.': 'מציג את התוכנות המותקנות במחשב.',
    'Load Skill instructions.': 'טעינת הוראות Skill.',
    'Minutes between repeated runs when repeat=interval': 'מרווח הדקות בין ריצות חוזרות כאשר repeat=interval',
    'Minutes to wait until the first run': 'מספר הדקות להמתנה עד להרצה הראשונה',
    'Minutes until the rescheduled run': 'דקות עד להרצה מחדש',
    'Moves a file or folder to the Windows recycle bin. Use for all user-file deletion requests; it does not delete permanently.': 'מעביר קובץ או תיקייה לסל המחזור של Windows. מיועד לכל בקשת מחיקה של קבצי משתמש; אינו מוחק לצמיתות.',
    'Mute audio.': 'השתקת השמע.',
    'Open an application (e.g. Chrome, Word).': 'פתיחת תוכנה (למשל Chrome, Word).',
    'Opens a file or folder with its default application.': 'פותח קובץ או תיקייה באמצעות ברירת מחדל.',
    "Opens an address or searches in the user's visible browser for viewing.": 'פותח כתובת או מבצע חיפוש בדפדפן הגלוי של המשתמש לצפייה.',
    'Opens files (video, Excel, images) or folders to show them to the user on screen.': 'הכלי האולטימטיבי לפתיחת קבצים (וידאו, אקסל, תמונות) או תיקיות כדי להציג אותם למשתמש במסך.',
    'Opens installed software. Warning: only for opening system applications (such as Chrome, Word), not files!': 'פותח תוכנה מותקנת. אזהרה: נועד רק לפתיחת תוכנות מערכת (כגון Chrome, Word) - לא לקבצים!',
    'Optional inspection focus': 'מוקד אופציונלי לבדיקה',
    'Optional ref for show/log': 'ref אופציונלי עבור show/log',
    'Pass a complete standard JSON Schema object here (as a String) describing the exact JSON structure the tool expects (type, description, properties, required).': 'חובה להעביר כאן אובייקט JSON Schema תקני ומלא (כמחרוזת String) שמתאר בדיוק את מבנה ה-JSON שהכלי מצפה לקבל (type, description, properties, required).',
    'Path to a local Skill directory when source=local': 'נתיב לתיקיית Skill מקומית כאשר source=local',
    'Performs a web search and returns an initial source summary.': 'מבצע חיפוש אינטרנט ומחזיר סיכום מקורות ראשוני.',
    'Project directory': 'תיקיית הפרויקט',
    'Project directory to scan': 'תיקיית הפרויקט לסריקה',
    'Quick scanner to locate files by name.': 'סורק מהיר לאיתור קבצים לפי שם.',
    'Quickly scans the computer for files by name.': 'סורק במהירות את המחשב לאיתור קבצים על פי שמם.',
    'Read text from document files.': 'קריאת טקסט מקבצי מסמכים.',
    'Read-only Git action': 'פעולת Git קריאה בלבד',
    'Read-only Git: status, diff, log, show.': 'Git קריאה בלבד: status, diff, log, show.',
    'Reads a web page or crawls an entire website in a controlled manner.': 'קורא עמוד אינטרנט או זוחל אתר שלם בצורה מבוקרת.',
    'Reads text from local files (.txt, .csv, .docx, .pdf).': 'קורא טקסט מקבצים מקומיים (.txt, .csv, .docx, .pdf).',
    'Repository directory': 'תיקיית repository',
    'Reschedule a background task.': 'הרצה מחדש של משימת רקע.',
    'Reschedules an existing background task by ID.': 'מתזמן מחדש משימת רקע קיימת לפי מזהה.',
    "Retrieve a JSON schema for a specific action of a built-in tool, Python tool, MCP package, or Skill. Every call must include tool_name and action. Use the exact action/MCP function name; action='full' (or omitting action for backward compatibility) returns the complete schema as before.": "שליפת סכמת JSON עבור פעולה מסוימת של כלי מובנה, כלי Python, חבילת MCP או Skill. בכל קריאה יש לשלוח tool_name וגם action. השתמש בשם הפעולה/פונקציית MCP המדויקת; action='full' (או השמטת action לצורכי תאימות לאחור) מחזיר את הסכמה המלאה כפי שהוחזרה בעבר.",
    'Run a Skill.': 'הרצת Skill.',
    'Run project tests or a build under policy.': 'הרצת בדיקות או build בפרויקט תחת מדיניות.',
    'Runs a build/test command and returns key errors for analysis and repair.': 'מריץ פקודת build/test ומחזיר שגיאות מרכזיות לפענוח ותיקון.',
    'Runs a high-level/workflow Skill. Before use, retrieve its schema through get_tool_info with the Skill name and its internal action as action, or full if it has no action field.': 'מפעיל Skill גבוה/תהליכי. לפני שימוש יש לשלוף סכמה דרך get_tool_info עם שם ה-Skill ו-action של הפעולה הפנימית שלו, או full אם אין לו שדה פעולה.',
    'Runs a limited project test/build command, with approval according to policy.': 'מריץ פקודת בדיקה/Build מוגבלת בפרויקט, עם אישור לפי מדיניות.',
    'Runs a specific function from an installed MCP package.': 'מפעיל פונקציה ספציפית מתוך חבילת MCP מותקנת.',
    'Runs read-only Git actions in a directory: status, diff, log, or show.': 'מריץ פעולות Git קריאה בלבד בתיקייה: status, diff, log או show.',
    "Runs short PowerShell commands. Risky write/execution commands require approval and are blocked if they harm Smarti's core.": 'מריץ פקודות PowerShell קצרות. פקודות כתיבה/הרצה מסוכנות דורשות אישור ונחסמות אם הן פוגעות בליבת סמארטי.',
    'Save a screenshot as a file.': 'שמירת צילום מסך כקובץ.',
    'Save path (or just the filename to save in the output directory)': 'נתיב השמירה (או רק שם הקובץ לשמירה בתיקיית התוצרים)',
    "Saves a screenshot to the user's Pictures directory.": 'שומר תמונת מסך לתיקיית התמונות של המשתמש.',
    'Saves only text files (txt, md, py, csv) to disk. For documents such as Word, create appropriate Python code with create_python_tool.': 'שומר קבצי טקסט בלבד (txt, md, py, csv) לכונן. למסמכים כגון Word, צור קוד פייתון רלוונטי ב-create_python_tool.',
    'Scans a project directory, maps key files, and returns an initial overview.': 'סורק תיקיית פרויקט, ממפה קבצים מרכזיים ומחזיר תמונת מצב ראשונית.',
    'Schedule a recurring action.': 'תזמון פעולה מחזורית.',
    'Schedules a future action to run independently in the background. Supports one-time actions, recurring actions at minute intervals, or weekly actions on specific days. After calling this tool, do not execute the task now in the current conversation; only report that it was successfully scheduled.': 'מתזמן פעולה עתידית שתרוץ ברקע באופן עצמאי. ניתן ליצור פעולה חד-פעמית, פעולה מחזורית במרווח דקות, או פעולה שבועית בימים ספציפיים. שים לב: לאחר קריאה לכלי זה, אין לבצע את המשימה עצמה כעת בשיחה הנוכחית; יש רק לדווח למשתמש שהמשימה תוכננה בהצלחה.',
    'Screen capture and visual context.': 'צילום מסך והקשר חזותי.',
    "Search Smarti's active tool catalog, including built-ins, Python tools, MCP packages, and Skills, before selecting, installing, or creating a capability.": 'חיפוש בקטלוג הכלים הפעילים של סמארטי, כולל כלים מובנים, כלי Python, חבילות MCP ומיומנויות, לפני בחירה, התקנה או יצירת יכולת.',
    'Search for Skills on ClawHub.': 'חיפוש Skills ב-ClawHub.',
    'Search for new packages and capabilities in the global MCP registry (NPM).': 'חיפוש חבילות ויכולות חדשות במאגר ה-MCP העולמי (NPM).',
    'Search topic': 'נושא החיפוש',
    'Searches for Skills only on ClawHub. The search filters suspicious results according to registry capabilities.': 'מחפש Skills במאגר ClawHub בלבד. החיפוש מסנן תוצאות חשודות לפי יכולות המאגר.',
    'Structured input according to the Skill schema': 'קלט מובנה לפי סכמת ה-Skill',
    'The JSON object containing the parameters required by the function': 'אובייקט ה-JSON עם הפרמטרים הנדרשים לפונקציה',
    'The Skill identifier/slug/name on ClawHub': 'מזהה/slug/שם ה-Skill ב-ClawHub',
    'The build or test command to execute': 'פקודת build או test להרצה',
    'The command to run': 'הפקודה להרצה',
    'The complete Python code. Write generic parameterized logic. The script receives a JSON object through sys.argv[1]. Use print to return results.': 'קוד הפייתון המלא. חובה לכתוב לוגיקה גנרית מבוססת פרמטרים. הסקריפט יקבל אובייקט JSON דרך sys.argv[1]. השתמש ב-print להחזרת תוצאה.',
    'The directory to scan': 'התיקייה לסרוק בה',
    'The exact MCP package name': 'שם חבילת ה-MCP המדויק',
    'The exact action within the tool, or MCP function name. The model must send this field. full requests the complete schema; the field remains optional only for backward compatibility, and omitting it is equivalent to full.': 'הפעולה המדויקת בתוך הכלי, או שם פונקציית MCP. המודל חייב לשלוח שדה זה. הערך full מבקש את הסכמה המלאה; השדה נשאר אופציונלי רק לתאימות לאחור, והשמטתו שקולה ל-full.',
    'The exact package name from NPM including a pinned version': 'השם המדויק של החבילה ממאגר NPM כולל גרסה נעולה',
    'The file content': 'תוכן הקובץ',
    'The filename to search for': 'שם הקובץ לחיפוש',
    'The function name to execute from the package': 'שם הפונקציה להפעלה מתוך החבילה',
    'The instruction to execute when the time arrives': 'ההוראה שיש לבצע כשהזמן יגיע',
    'The name of the Skill to run': 'שם ה-Skill להפעלה',
    'The name of the Skill whose requirements are being installed': 'שם ה-Skill שעבורו מתקינים דרישות',
    'The new memory to save': 'הזיכרון החדש לשמירה',
    'The requested planning type: initial, continuation, or replanning after new information/failure.': 'סוג התכנון המבוקש: ראשוני, המשכי, או תכנון מחדש אחרי מידע חדש/כשל.',
    'The software name': 'שם התוכנה',
    'The task ID': 'מזהה המשימה',
    'The text to copy': 'הטקסט להעתקה',
    'The text to search for inside files': 'הטקסט לחיפוש בתוך הקבצים',
    'The tool name in English (without an extension).': 'שם הכלי באנגלית (ללא סיומת).',
    'The tool, MCP package, or Skill name whose schema is needed.': 'שם הכלי, חבילת ה-MCP או ה-Skill שעבורו נדרשת סכמה.',
    'Topic or capability to search for in English or Hebrew': 'נושא או יכולת לחיפוש באנגלית או בעברית',
    'Updates long-term memory explicitly and in a controlled manner. Do not use free-text markers to update memory.': 'מעדכן את הזיכרון ארוך הטווח באופן מפורש ומבוקר. אין להשתמש בסימני טקסט חופשי לעדכון זיכרון.',
    'Whether the code is dangerous and requires approval.': 'האם הקוד מסוכן ודורש אישור.',
    'Whether to explicitly ask the user for approval before execution': 'האם לבקש מהמשתמש אישור במפורש לפני ההרצה',
    'auto is the default; use_provided_steps if you supplied good steps; ask_planner if another internal Planner is needed.': 'auto ברירת מחדל; use_provided_steps אם סיפקת צעדים טובים; ask_planner אם צריך Planner פנימי נוסף.',
    'clawhub to install from the approved registry; local to install from a user-selected directory': 'clawhub להתקנה מהמאגר המאושר; local להתקנה מתיקייה שהמשתמש בחר',
    'metric for Celsius and km/h, imperial for Fahrenheit and mph': 'metric לצלזיוס וקמ״ש, imperial לפרנהייט ומייל לשעה',
    'once for a one-time task, interval for a recurring task, weekly for a task on selected weekdays': 'once למשימה חד-פעמית, interval למשימה מחזורית, weekly למשימה שבועית בימים נבחרים',
}


def user_description(text, language="he"):
    return text if language == "en" else USER_DESCRIPTIONS.get(text, text)
