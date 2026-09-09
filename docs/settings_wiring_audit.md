# בדיקת חיבור הגדרות והקראת תשובות — 9 בספטמבר 2026

הבדיקה כוללת את כל 69 השדות ב־`desktop/src/managementCatalog.ts`, את פעולות הספקים והמפתחות, ואת הגדרות Windows הנלוות. ״מחובר בקוד״ פירושו שנמצא מסלול מהפקד לשמירה ולצרכן בזמן העבודה. אין בכך אישור שבוצעה בדיקה חיה לכל ספק, מיקרופון, כלי או הגדרת מערכת.

## תקלות שתוקנו

- כשל ההקראה שוחזר ברשת המקומית: Edge החזיר `CERTIFICATE_VERIFY_FAILED` בגלל שרשרת תעודות הכוללת תעודה עצמית. ההקראה משתמשת כעת בהגדרת האמון של Smarti, כולל מאגר Windows ותעודת CA מותאמת. אין שינוי בהגדרות האמון השמורות של המשתמש.
- הגדרות ההקראה האוטומטית מחוברות כעת לסיום ריצה מוצלחת בממשק החדש. זיהוי קולי מועבר מה־Composer דרך חוזה הבקשה למטא־נתונים של הריצה. ריצות שבוטלו או נכשלו אינן מוקראות אוטומטית; טעינת היסטוריה אינה מפעילה הקראה חוזרת.
- התחלה, עצירה, החלפת תשובה, תצוגה מקדימה ושגיאות חולקות מצב שמע מזוהה. ביטול מסמן גם בקשות שממתינות להכנת השמע, וסגירת זרם Edge משחררת את חיבור הרשת.
- בבדיקה מול תהליך הליבה הפעיל נמצאה תקיעה בייבוא NumPy מתוך `pygame` על תהליכון ההקראה. הניגון ב־Windows עבר ל־MCI המובנה במערכת, ללא טעינת pygame/NumPy; בחירת קול, עוצמה ועצירה נשארות מחוברות.
- רענון ממשק הפיתוח יכול להשאיר שירות Python ישן פעיל, שדוחה את `owner_id`. מצב ההקראה כולל כעת גרסת פרוטוקול; הממשק מזהה שירות ישן ומרענן אותו דרך המפקח, רק כשאין ריצה או הקראה פעילה. אי־תאימות מתמשכת מוצגת כהודעה ברורה, ללא ניסיונות רענון אינסופיים.
- כשל בסינתזת Edge מפעיל את גיבוי Google כאשר הוא מותקן. תעבורת Google משתמשת במדיניות אימות התעודות של Smarti במקום ברירת המחדל הלא מאומתת של הספרייה.
- עוצמה של 1% מתורגמת ל־0.01; השתקה נשמרת, ושינוי עוצמה חל גם במהלך הניגון.
- המחוונים העשרוניים מקבלים גם מספר שלם תקין שנשלח ב־JSON, למשל 0 שניות כיול או שנייה אחת של הפסקת דיבור. ערך בוליאני אינו מתקבל כמספר.
- עדכון שדה מקונן בהעדפות או בתקציבים שומר את יתר הערכים העדכניים בשרת. מתג הסתרת הלוגים מעדכן גם את השדה המקביל תחת `privacy`, כדי שלא יתבטל בזמן השמירה.

## שני שדות שלא מחוברים בממשק החדש

| שדה | הממצא |
| --- | --- |
| `budgets.daily_cost_budget_usd` | נשמר בהגדרות, אך אין בקוד צרכן שמחשב או אוכף את יעד העלות. אין לראות בו מגבלת חיוב. תקציב הטוקנים הוא מנגנון נפרד שמחובר לבדיקות לפני בקשות מודל. |
| `permission_notification_timeout_seconds` | נקרא ב־`smarti/chat.py`, בממשק PyQt הישן. הממשק החדש מנהל בקשות הרשאה מתמשכות ב־`desktop/src/conversationApprovals.tsx` ואינו משתמש בשדה הזה. שינויו אינו משנה את משך בקשת ההרשאה בממשק החדש. |

שני הממצאים תועדו במסגרת הביקורת; לא נוסף מנגנון תקציב עלות ולא שונה משך החיים של בקשות הרשאה כחלק מתיקון ההקראה.

## מפת החיבורים

כל השדות הבאים מחוברים בקוד. שדות המופיעים יחד חולקים מסלול שמירה או צרכן; הרשימות כוללות את 67 השדות הנותרים בקטלוג.

| שדות | מסלול וצרכן |
| --- | --- |
| `api_mode`, `selected_provider_model`, `local_server_url` | `SettingsManagement.tsx` → `/v2/settings` → `local_gateway.py` → `setup_model` ב־`agent/model_context.py`; הבחירה חוזרת לצ'אט דרך bootstrap וסנכרון ההגדרות. `selected_provider_model` הוא פקד שממופה למפתח של הספק שנבחר. |
| `provider_api_key`, `codex_signin`, `provider_reasoning_effort` | תהליכים ייעודיים ב־`SettingsManagement.tsx`; נקודות הקצה למפתחות, התחברות ורמת חשיבה ב־`local_gateway.py`; צריכה ב־`agent/model_context.py` וב־`codex_signin.py`. אינם שמות של שלושה מפתחות רגילים בהגדרות. |
| `conversation_title_generation_mode` | `run_manager.py` ויצירת הכותרות ב־`agent/model_context.py`. |
| `local_fast_mode_enabled` | מסנכרן את פקד הצ'אט ונקרא ב־`agent/model_context.py`, `agent/messaging.py` ו־`agent/tool_calls.py`. |
| `tavily_api_key` | מסלול שמירת סוד; כלי החיפוש ב־`agent/productivity_tools.py`. |
| `autonomy_mode`, `custom_permission_profile_enabled` | מיפוי פרופיל ב־`local_gateway.py`, העדפות מדיניות ב־`agent/lifecycle.py` ומדיניות הביצוע ב־`agent/execution_policy.py`. |
| `sandbox_enabled`, `sandbox_root_dir`, `sandbox_allow_read_outside` | מדיניות נתיבים וביצוע ב־`agent/execution_policy.py` וב־`desktop_services.py`. |
| `default_output_dir`, `write_outside_allowed_dirs_requires_approval`, `require_approval_for_cloud_upload` | תיקיית פלט והכינוי `allowed_write_dirs`, ובדיקות הרשאה ב־`agent/execution_policy.py` ובכלי הקבצים. |
| `mcp_require_pinned_versions` | אימות הפעלת MCP ב־`agent/system_tools.py`. |
| `raw_shell_requires_approval`, `marketplace_install_requires_approval` | בניית מדיניות והרשאות ב־`managers.py` וב־`agent/lifecycle.py`. |
| `enable_browser_automation`, `enable_computer_control`, `enable_tool_search_catalog` | זמינות כלי המודל ב־`agent/model_context.py`, ושערי הפעולה ב־`agent/automation.py`, `browser_control.py` ו־`agent/tool_calls.py`. המערכת בונה את ההנחיות מחדש בתחילת בקשה. |
| `enable_web_canvas`, `enable_canvas_remote_images` | פקד Canvas מסנכרן גם `enable_visual_surfaces`; צריכה ב־`agent/model_context.py` ובמסלולי Canvas. |
| `enable_skills_beta`, `skill_install_unknown_scan_policy`, `enable_mcp_clawhub` | רענון קטלוגים ב־`local_gateway.py`; התקנה, סריקה והפעלת הרחבות ב־`agent/extensions.py`, `agent/model_context.py` ו־`agent/tool_dispatch.py`. |
| `email_address`, `email_password`, `email_from_name`, `email_imap_host`, `email_imap_port`, `email_imap_ssl`, `email_smtp_host`, `email_smtp_port`, `email_smtp_starttls`, `email_smtp_ssl`, `email_max_attachment_mb` | `agent/email_tools.py`; בדיקת חיבור ייעודית ב־`desktop_services.py`. הסיסמה נשמרת דרך מסלול הסודות. לא נשלח דואר בבדיקה זו. |
| `ui_preferences.theme_mode` | העדפות שמורות → סנכרון ב־`App.tsx` → מערכת העיצוב. |
| `read_aloud_all`, `read_aloud_voice_only` | `Composer.tsx` → בקשת ריצה → סיום מוצלח ב־`run_manager.py` → שירות ההקראה. |
| `tts_voice_id`, `tts_volume` | `agent/speech.py`; מצב השמע ב־`tts_service.py` ומעקב משותף ב־`speechPlayback.ts`. |
| `voice_sensitivity`, `voice_pause_threshold`, `voice_listen_timeout`, `voice_ambient_noise_duration`, `voice_dynamic_energy_threshold`, `voice_beep_enabled` | `VoiceSessionController` ו־`recognize_voice` ב־`voice_service.py` קוראים תמונת הגדרות חדשה בתחילת האזנה. |
| `updates_auto_check` | בדיקת עדכונים מתוזמנת ב־`App.tsx` קוראת את הערך השמור לפני הבדיקה. שינוי הערך חל בבדיקה המתוזמנת הבאה. |
| `ssl_trust_mode`, `ssl_custom_ca_path` | אימות וייבוא תעודות ב־`local_gateway.py`, `ssl_compat.py` והפעלת הגדרות הרשת ב־`agent/runtime_services.py`; כולל מנועי ההקראה לאחר התיקון. |
| `prevent_sleep_during_active_task` | מניעת שינה במהלך בקשה ב־`agent/messaging.py`. |
| `command_timeout_seconds`, `tool_timeout_seconds`, `mcp_timeout_seconds` | מגבלות המתנה בכלי ההפעלה ב־`agent/system_tools.py`, `agent/extensions.py` ובאוטומציה. |
| `max_total_task_seconds`, `codex_request_timeout_seconds`, `max_tool_output_chars` | מגבלות ריצה ובקשות ב־`agent/messaging.py`, `agent/model_context.py`, `agent/lifecycle.py` ו־`agent/web_content.py`. |
| `budgets.daily_token_budget` | בדיקות טוקנים לפני בקשת מודל ב־`agent/model_context.py`; 0 מבטל את התקרה. |
| `max_agent_loops`, `background_recurring_catch_up_window_minutes` | המחוונים ממפים ״ללא הגבלה״ ל־0 ול־‎-1 בהתאמה; צריכה ב־`agent/messaging.py` וב־`agent/background_runtime.py`. |
| `enable_developer_trace`, `audit_log_enabled`, `privacy_redact_logs` | ניהול Trace ואודיט ב־`managers.py`, סינון לוגים ב־`common.py` ו־`desktop_services.py`; תוקן סנכרון כינוי הפרטיות בעת שמירה. |
| `mcp_allowed_directories` | נשמר כרשימת תיקיות; מועבר לסביבת MCP ב־`agent/runtime_services.py`. |

בנוסף לקטלוג, `voice_hotkey` ו־`keep_running_in_tray` מסונכרנים ב־`App.tsx` לפקודות Windows הייעודיות. העדפות סביבת העבודה והדפדפן מנוהלות ברכיבי סביבת העבודה ובמארח הדפדפן.

## ראיות והיקף אימות

- בדיקות יחידה ואינטגרציה: מנועי הקראה, בחירת קול, גיבוי, עוצמה, TLS, ביטול, החלפת בקשות, מצב שגיאה, מטא־נתונים של בקשה קולית, מצבי ההקראה האוטומטית, שמירה והעדפות מקוננות.
- בדיקות React: כפתורי תשובות ותצוגה מקדימה, מצב אוטומטי, שגיאות, שליחת הכתבה עם סימון קולי, סנכרון הגדרות וניהול.
- בדיקה ישירה מול שירותי הסינתזה: Edge יצר 12,528 בתים בקול העברי שנבחר; Google יצר 11,904 בתים. הניגון הסופי ב־Windows משתמש במנגנון MCI המובנה.
- בדיקה מול הליבה הפעילה בחלון ה־Debug של המשתמש: השירות רוענן, גרסת פרוטוקול ההקראה אומתה, ובקשת הקראה עם `owner_id` התקבלה והסתיימה בניגון ללא שגיאה. הבדיקה השתמשה במשפט סינתטי ובהגדרות השמע הקיימות; לא שונו הגדרות המשתמש.
- אלה ראיות לקוד המקור ולרכיבי השמע במחשב הזה. לא נבנה מתקין ולא נבדק EXE ארוז; לא בוצעה בדיקת דפדפן חיה או בדיקת מיקרופון.
