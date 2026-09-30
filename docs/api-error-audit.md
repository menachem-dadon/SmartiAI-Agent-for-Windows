# בדיקת שגיאות API ותיקון מנגנון הספקים

תאריך: 30 בספטמבר 2026. היקף: כל 18 ספקי מודלי הטקסט הרשומים ב-Smarti, כולל מודל מקומי וחיבור Codex הרשמי. הבדיקה מכסה שליחת בקשות, אימות מפתחות, גילוי מודלים, פענוח תשובות, ניסיונות חוזרים, הצגה למשתמש ולוגים.

## השינוי המרכזי

לכל אבחון יש כעת `reason` מפורט, בנוסף לקטגוריה הכללית המשמשת את מנגנון ההתאוששות. קטלוג `smarti/api_error_catalog.py` כולל 102 סיבות עם הודעות נפרדות בעברית והנחיית פעולה. הקוד מעדיף קוד שגיאה ופרטים מובנים של הספק; משתמש בהודעת הספק להשלמת האבחון; ורק לאחר מכן מפעיל ברירת מחדל לפי HTTP.

ההודעה בצ'אט כוללת את הספק והמודל, קוד HTTP וקוד הספק, פרמטר בעייתי, מזהה בקשה, פרטי מכסה והסבר מקורי כאשר הם קיימים. שגיאה חדשה שאינה מוכרת מוצגת עם הפרטים המקוריים, במקום להיעלם מאחורי טקסט כללי. האבחון אינו יכול להסיק סיבה שהספק עצמו לא מסר.

בלוג, `API FAILURE` ו-`API STOP` כוללים את הסיבה המדויקת ואת הודעת המשתמש. הסתרת מפתחות מתבצעת לפני קיצור ההודעות, גם כאשר מסנן הפרטיות הכללי כבוי. גם מפתח חדש שטרם נשמר מוסתר בעת בדיקתו.

## כשלים שנמצאו ותוקנו

1. אובדן גוף שגיאה אמיתי: `requests.Response` מחזיר ערך בוליאני שקרי עבור HTTP 4xx/5xx. בחירה באמצעות `response or ...` זרקה את תגובת השגיאה ואת קוד הספק. הבחירה נעשית כעת לפי `None` בלבד.
2. בלבול במכסות Gemini: הודעת חיוב כללית מופיעה גם בהגבלת קצב חינמית זמנית. `QuotaFailure`, מזהה המכסה וערך המכסה מבחינים בין בקשות לדקה, טוקנים לדקה, מכסה יומית ומכסה אפסית. `RetryInfo` אינו הופך מכסה יומית לבעיה שנפתרת בהמתנה קצרה.
3. ניסיונות חוזרים מצטברים: ה-SDK ו-Smarti ניסו שוב בנפרד. בלקוחות OpenAI הוגדר `max_retries=0`, וההתאוששות מנוהלת במקום אחד. ההמתנה גדלה בהדרגה ומכבדת `Retry-After`, תאריך HTTP, אלפיות שנייה ו-Google `RetryInfo`. בקשת המתנה ארוכה נעצרת עם הסבר ואינה מקוצרת כדי לשלוח בקשה מוקדם מדי.
4. הצלחה מדומה: HTTP 200 עם מעטפת `error`, תשובה ריקה, JSON לא תקין, חסימת תוכן, עצירת בטיחות או פלט קטוע מזוהים ככשל. טקסט חלקי נשמר ומסומן כאשר היצירה נעצרה במגבלת פלט. קריאות לכלים עם ארגומנטים לא תקינים אינן מומרות למילון ריק ואינן מועברות לביצוע.
5. אי התאמה בין endpoints של OpenAI: משפחות Pro ו-Codex שדורשות Responses נשלחות דרך Responses, עם התאמת תמונות, reasoning, כלים ונתוני שימוש. אפשרויות המטמון העדכניות נשלחות באמצעות `extra_body`, כך ש-SDK שאינו מכיר פרמטר בשם אינו נכשל לפני שליחת הבקשה.
6. Anthropic: תקציב חשיבה ידני מוגבל כך שיישאר קטן מ-`max_tokens`. תקציב פלט שאינו מאפשר חשיבה ידנית נחסם מראש עם הודעה מתאימה.
7. Qwen: `insufficient_quota` של DashScope מזוהה כמגבלת קצב טוקנים, בהתאם לתיעוד הספק, בעוד שמכסה חינמית שהסתיימה מזוהה בנפרד. דחייה מפורשת של בקשה שאינה זורמת מפעילה שליחה ב-streaming ואיסוף התשובה לחוזה הקיים.
8. כתובת Qwen: נוספה `qwen_base_url` בממשקי React ו-PyQt, באימות, בגילוי המודלים ובבקשות. כתובת ריקה שומרת את ברירת המחדל הקיימת. כתובת ניתנת להחלפה בהתאם לאזור, למרחב העבודה ולמסלול המפתח. שינוי endpoint מונע שימוש חוזר בלקוח הישן; כתובת לא תקינה נחסמת עם אבחון מפורש.
9. זמן חיבור: זמן הקמת חיבור, כתיבה והמתנה לחיבור פנוי מוגבל בנפרד מזמן יצירת התשובה. הגבלת יצירת התשובה הקיימת נשמרה. לקוחות שנוצרו לבקשה בודדת נסגרים גם בכשל, והמתנת חיבור מחדש אינה מאפסת ניסיונות ללא גבול.
10. גילוי מודלים: נוספו pagination ל-Gemini ול-Anthropic, בדיקת סמן חוזר/חסר, אבחון קטלוג ריק ומעטפת שגיאה גם ב-HTTP 200. ב-Hugging Face המפתח נבדק מול `whoami-v2`, במקום להסתמך על קטלוג ציבורי. אימות זהות מוצלח וכשל מאוחר בקטלוג נשמרים כשתי תוצאות נפרדות; אזהרת הקטלוג מוצגת למשתמש.
11. Codex: אירועי JSONL מסוג `error` ו-`turn.failed` מפוענחים גם כאשר תהליך CLI הסתיים בקוד אפס. אירוע `turn.completed` מאוחר מבטל כשל ביניים שממנו Codex התאושש. המילה "token" לבדה אינה הופכת שגיאת מכסה לשגיאת התחברות.
12. gateway: אימות ספק עובר ל-worker כדי שלא לחסום את event loop. אימות שרת מקומי משתמש בהגדרה הפעילה `local_server_url`.
13. התאוששות מהקשר גדול: קיצור ההקשר מופעל עבור חריגה מחלון ההקשר בלבד. שגיאת גודל גוף בקשה או קובץ אינה גוררת קיצור שיחה שאינו מטפל בגורם.
14. החלפת ספק בממשק: תשובת קטלוג ישנה אינה מחליפה את רשימת המודלים או את הודעת השגיאה של הספק הנוכחי. כשיש מודלים בקטלוג אך טרם נבחר מודל, הממשק מציג "בחר מודל".

## כיסוי לפי ספק

כל הספקים משתמשים באותו אבחון בסיסי לאימות, הרשאות, תשלום, קצב, הקשר, HTTP, רשת, TLS, timeout ושגיאות שרת. בדיקות החוזה מריצות את מטריצת סטטוסי HTTP עבור כל ספק. בקשות ענן אמיתיות לא הופעלו במסגרת הבדיקה.

| ספק | מסלול וכיסוי ייחודי |
| --- | --- |
| Google Gemini | generateContent; QuotaFailure/RetryInfo/ErrorInfo; כל סיבות העצירה המתועדות; pagination |
| OpenAI | Chat Completions ו-Responses למשפחות המתאימות; קודי קרדיט ותקרות ארגון/פרויקט; reasoning ומטמון |
| OpenAI Codex / ChatGPT | CLI רשמי בלבד; התחברות, מכסת חשבון, כשל תהליך ו-JSONL |
| Anthropic | Messages; שגיאות מובנות; תקציב חשיבה, חסימה ופלט קטוע; pagination |
| OpenRouter | OpenAI compatible; שגיאת HTTP 200; metadata.error_type; מכסת מפתח, קרדיט ותקציב בקשות פעילות |
| Groq | OpenAI compatible; קיבולת 498; תלות כלי 424; כשל שרת/קצב |
| NVIDIA NIM | OpenAI compatible; חוזה משותף ובדיקות בקשה ואבחון |
| Cerebras | OpenAI compatible; חוזה משותף ובדיקות בקשה ואבחון |
| Hugging Face | OpenAI compatible; אימות זהות עצמאי; הפרדה בין אימות לקטלוג |
| DeepSeek | OpenAI compatible; יתרה, קצב ועומס |
| Alibaba Qwen | OpenAI compatible; קודי DashScope; מכסה חינמית לעומת קצב טוקנים; streaming; endpoint לפי מסוף הספק |
| Zhipu GLM | OpenAI compatible; קודים עסקיים נפרדים מ-HTTP; יתרה, מנוי, הרשאות וחלונות מכסה |
| Moonshot Kimi | OpenAI compatible; יתרה ומכסה; אבחון משותף |
| Mistral AI | OpenAI compatible; אבחון ובדיקות חוזה משותף |
| Together AI | OpenAI compatible; HTTP 403 עם חריגת הקשר נבדק בנפרד מהרשאות; 524/529 |
| Perplexity | OpenAI compatible; אימות, קצב, שגיאות סטטוס וחיבור |
| xAI | OpenAI compatible; פענוח גוף שגיאה וקודי HTTP |
| שרת מקומי | OpenAI compatible; כתובת/פורט לא תקינים, שרת שאינו פועל וקטלוג ללא מודל טעון |

## קבוצות אבחון

- מפתח חסר, נדחה, פג, בוטל; התחברות Codex; אימות דו-שלבי.
- הרשאות מודל/חשבון/IP/אזור; חסימת מדיניות והגבלת חשבון.
- קרדיט, מכסה חינמית/יומית/אפסית, הוצאה ברמת ארגון/פרויקט/מפתח, מכסות ומנויים של חבילות קידוד.
- בקשות/טוקנים/בקשות מקבילות, תקציב בקשות פעילות ו-Retry-After.
- חלון הקשר, גודל בקשה, מגבלת פלט, פרמטרים, schema של כלי, היסטוריה, קבצים ומודאליות.
- מודל חסר/שהוסר, endpoint לא מתאים, חובה להשתמש ב-Responses או ב-streaming.
- תשובה ריקה/פגומה/קטועה; חסימת בטיחות, תוכן אסור, מידע אישי, recitation, שפה ותמונות; קריאות כלי וחתימות חשיבה.
- DNS, פרוקסי, סירוב/איפוס חיבור; connect/read/write/pool/gateway timeout.
- תעודה שפגה, שם שרת שאינו תואם, שרשרת אמון, תצורת TLS ופרוטוקול TLS.
- שגיאת שרת פנימית, עומס, שירות לא זמין וכשל upstream.

הרשימה המלאה וההודעות נמצאות ב-`smarti/api_error_catalog.py`, והוא המקור המחייב.

## אימות

- `python -m unittest discover -s tests -q`: כל 509 בדיקות Python עברו.
- `npm run test -- src/apiProviderErrors.test.tsx src/managementUi.test.ts src/settingsSync.test.tsx`: כל 18 בדיקות הממשק הממוקדות עברו.
- `npm run build`: TypeScript ו-build ייצור של Vite עברו; נשארה אזהרת גודל bundle.
- `git diff --check`: עבר.
- הבדיקות החדשות משתמשות בתגובות `requests.Response` אמיתיות, ב-SDK OpenAI המותקן, בשרת HTTP מקומי וב-fixtures לכל הספקים, ללא מפתחות ענן או חיובים.

בדיקות TLS משתמשות בשרת stdlib מקומי ומחזירות את גלובלי הלקוח אחרי הקמתו. כך טעינת truststore של Windows בבדיקות אחרות אינה שוברת את שרת הבדיקה. מנגנון אימות התעודות של היישום נשמר.

## מה עדיין דורש אימות אצל משתמש

אין גישה למכסות ולחיוב של חשבונות המשתמשים. לא ניתן לחדש קרדיט, להפעיל מכסה חינמית למודל שהספק אינו מציע, או להחזיר מודל שהספק הסיר באמצעות שינוי מקומי בקוד. המנגנון מסביר את הכשל ואת הפעולה הנדרשת.

טרם בוצע smoke test עם חשבון ענן אמיתי בכל ספק או ניסיון בסביבת רשת מסוננת של משתמש. לכן בדיקות החוזה וה-build אינן אישור לכך שכל מודל זמין לכל חשבון. זמינות endpoints ומודלים תלויה גם באזור ובמסלול. פירוט התיעוד של NVIDIA/Cerebras/Moonshot לא היה נגיש במלואו במהלך הסקירה; הכיסוי שלהם מבוסס על מסלול OpenAI compatible ועל בדיקות החוזה המשותף.

## מקורות רשמיים שנבדקו

- [OpenAI — error codes](https://developers.openai.com/api/docs/guides/error-codes), [GPT-5 Pro](https://developers.openai.com/api/docs/models/gpt-5-pro), [prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
- [Google — troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting), [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), [generateContent ו-FinishReason](https://ai.google.dev/api/generate-content).
- [Anthropic — API errors](https://platform.claude.com/docs/en/api/errors).
- [Alibaba Model Studio — error codes, regions and endpoint mismatch](https://help.aliyun.com/en/model-studio/error-code).
- [OpenRouter — errors and debugging](https://openrouter.ai/docs/api_reference/errors-and-debugging).
- [Z.AI — business error codes](https://docs.z.ai/api-reference/api-code.md).
- [Together — error codes](https://docs.together.ai/docs/error-codes), [DeepSeek — error codes](https://api-docs.deepseek.com/quick_start/error_codes/), [Groq — errors](https://console.groq.com/docs/errors).
- [Perplexity — SDK error handling](https://docs.perplexity.ai/docs/sdk/error-handling.md), [xAI — debugging](https://docs.x.ai/developers/debugging), [Mistral — migration guides](https://docs.mistral.ai/resources/migration-guides).
