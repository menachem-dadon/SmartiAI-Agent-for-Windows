"""Builtin tool schemas and default Smarti settings."""
from .common import *


# ==========================================
# Unified MCP/JSON Tool Definitions
# ==========================================
BUILTIN_TOOL_SCHEMAS = {
    "system_command": {
        "description": "מריץ פקודות PowerShell קצרות. פקודות כתיבה/הרצה מסוכנות דורשות אישור ונחסמות אם הן פוגעות בליבת סמארטי.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Optional working directory for the command"},
                "timeout_seconds": {"type": "integer", "description": "Optional timeout override in seconds"},
                "command": {"type": "string", "description": "הפקודה להרצה"},
                "require_approval": {"type": "boolean", "description": "האם לבקש מהמשתמש אישור במפורש לפני ההרצה"},
                "explanation": {"type": "string", "description": "הסבר קצר למשתמש למה הפקודה עושה"}
            },
            "required": ["command"]
        }
    },
    "create_python_tool": {
        "description": "יוצר ושומר כלי פייתון גנרי ורב-פעמי למאגר. חובה ליצור קוד כללי שמקבל פרמטרים ולא קוד חד-פעמי למשימה ספציפית.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "שם הכלי באנגלית (ללא סיומת)."},
                "code": {"type": "string", "description": "קוד הפייתון המלא. חובה לכתוב לוגיקה גנרית מבוססת פרמטרים. הסקריפט יקבל אובייקט JSON דרך sys.argv[1]. השתמש ב-print להחזרת תוצאה."},
                "description": {"type": "string", "description": "חובה להעביר כאן אובייקט JSON Schema תקני ומלא (כמחרוזת String) שמתאר בדיוק את מבנה ה-JSON שהכלי מצפה לקבל (type, description, properties, required)."},
                "require_approval": {"type": "boolean", "description": "האם הקוד מסוכן ודורש אישור."}
            },
            "required": ["name", "code", "description"]
        }
    },
    "search_mcp": {
        "description": "חיפוש חבילות ויכולות חדשות במאגר ה-MCP העולמי (NPM).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "מילות חיפוש באנגלית לחבילת ה-MCP הרצויה"}
            },
            "required": ["query"]
        }
    },
    "install_mcp": {
        "description": "התקנת חבילת MCP (שרת) שמוסיפה יכולות חדשות למערכת. חובה להשתמש בגרסה נעולה, למשל package@1.2.3 או @scope/package@1.2.3.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "השם המדויק של החבילה ממאגר NPM כולל גרסה נעולה"}
            },
            "required": ["package"]
        }
    },
    "run_mcp": {
        "description": "מפעיל פונקציה ספציפית מתוך חבילת MCP מותקנת.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "שם חבילת ה-MCP המדויק"},
                "function": {"type": "string", "description": "שם הפונקציה להפעלה מתוך החבילה"},
                "arguments": {"type": "object", "description": "אובייקט ה-JSON עם הפרמטרים הנדרשים לפונקציה"}
            },
            "required": ["package", "function"]
        }
    },
    "read_website": {
        "description": "Reads clean text from one URL or crawls a same-site website. Use mode=page for a single page, mode=crawl for whole-site reading.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Starting URL."},
                "mode": {"type": "string", "enum": ["page", "crawl"], "default": "page", "description": "page reads one URL. crawl follows same-site links and optional sitemap URLs."},
                "max_pages": {"type": "integer", "default": 30, "description": "Maximum pages in crawl mode. Use 1 for a single page. Hard-capped internally."},
                "max_depth": {"type": "integer", "default": 2, "description": "Maximum link depth from the start page in crawl mode."},
                "max_total_chars": {"type": "integer", "default": 90000, "description": "Maximum total text characters returned across all pages."},
                "max_page_chars": {"type": "integer", "default": 12000, "description": "Maximum text characters returned per page."},
                "include_links": {"type": "boolean", "default": True, "description": "Include a compact discovered-link index."},
                "max_links": {"type": "integer", "default": 80, "description": "Maximum discovered links to include in output."},
                "same_domain": {"type": "boolean", "default": True, "description": "Restrict crawl to the starting domain."},
                "include_subdomains": {"type": "boolean", "default": False, "description": "When same_domain is true, also allow subdomains."},
                "include_patterns": {"type": "array", "items": {"type": "string"}, "description": "Optional regex or substring filters. URL must match one to be crawled."},
                "exclude_patterns": {"type": "array", "items": {"type": "string"}, "description": "Optional regex or substring filters. Matching URLs are skipped."},
                "respect_robots_txt": {"type": "boolean", "default": True, "description": "Respect robots.txt crawl rules when available."},
                "use_sitemap": {"type": "boolean", "default": True, "description": "In crawl mode, seed the crawl with sitemap.xml URLs when available."},
                "delay_seconds": {"type": "number", "default": 0.2, "description": "Polite delay between crawl requests."},
                "timeout_seconds": {"type": "integer", "default": 20, "description": "HTTP timeout per request."},
                "user_agent": {"type": "string", "description": "Optional custom User-Agent."}
            },
            "required": ["url"]
        }
    },
    "analyze_local_image": {
        "description": "מפעיל ראייה ממוחשבת (Vision) לקריאת תוכן וניתוח של תמונה מקומית במחשב.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "נתיב מלא לקובץ התמונה"}},
            "required": ["path"]
        }
    },
    "schedule_background_task": {
        "description": "מתזמן פעולה עתידית שתרוץ ברקע באופן עצמאי. ניתן ליצור פעולה חד-פעמית, פעולה מחזורית במרווח דקות, או פעולה שבועית בימים ספציפיים. שים לב: לאחר קריאה לכלי זה, אין לבצע את המשימה עצמה כעת בשיחה הנוכחית; יש רק לדווח למשתמש שהמשימה תוכננה בהצלחה.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "delay_minutes": {"type": "number", "description": "מספר הדקות להמתנה עד להרצה הראשונה"},
                "prompt": {"type": "string", "description": "ההוראה שיש לבצע כשהזמן יגיע"},
                "repeat": {"type": "string", "enum": ["once", "interval", "weekly"], "description": "once למשימה חד-פעמית, interval למשימה מחזורית, weekly למשימה שבועית בימים נבחרים"},
                "interval_minutes": {"type": "number", "description": "מרווח הדקות בין ריצות חוזרות כאשר repeat=interval"},
                "days_of_week": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "מערך של מספרים מ-0 (יום שני) עד 6 (יום ראשון) המייצג את ימי השבוע להרצה כאשר repeat=weekly"
                },
                "conversation_mode": {
                    "type": "string",
                    "enum": ["current", "new", "dedicated"],
                    "description": "אופן ניתוב השיחה: current (שיחה נוכחית), new (שיחה חדשה בכל הרצה), dedicated (שיחה קבועה ייעודית למשימה זו)"
                }
            },
            "required": ["delay_minutes", "prompt"]
        }
    },
    "list_background_tasks": {
        "description": "מציג את משימות הרקע, סטטוס, זמן ריצה ותוצאה אחרונה.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "cancel_background_task": {
        "description": "מבטל משימת רקע לפי מזהה.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "מזהה המשימה"}},
            "required": ["id"]
        }
    },
    "retry_background_task": {
        "description": "מתזמן מחדש משימת רקע קיימת לפי מזהה.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "מזהה המשימה"},
                "delay_minutes": {"type": "number", "description": "דקות עד להרצה מחדש"}
            },
            "required": ["id"]
        }
    },
    "open_software": {
        "description": "פותח תוכנה מותקנת. אזהרה: נועד רק לפתיחת תוכנות מערכת (כגון Chrome, Word) - לא לקבצים!",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "שם התוכנה"}},
            "required": ["name"]
        }
    },
    "open_file_or_folder": {
        "description": "הכלי האולטימטיבי לפתיחת קבצים (וידאו, אקסל, תמונות) או תיקיות כדי להציג אותם למשתמש במסך.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "נתיב מלא לקובץ/תיקייה"}},
            "required": ["path"]
        }
    },
    "trash_file_or_folder": {
        "description": "מעביר קובץ או תיקייה לסל המחזור של Windows. מיועד לכל בקשת מחיקה של קבצי משתמש; אינו מוחק לצמיתות.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "נתיב מלא לקובץ או לתיקייה להעברה לסל המחזור"}},
            "required": ["path"]
        }
    },
    "list_software": {
        "description": "מציג את התוכנות המותקנות במחשב.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional app name filter."},
                "limit": {"type": "integer", "description": "Maximum results."},
                "refresh": {"type": "boolean", "description": "Rebuild the cached app index."},
                "include_paths": {"type": "boolean", "description": "Include launch path/AppID details."},
                "format": {"type": "string", "enum": ["text", "json"], "description": "Output format."}
            }
        }
    },
    "internet_search": {
        "description": "חיפוש מהיר ועדכני ברשת באמצעות מנוע חיפוש. מחזיר תוצאות מקוונות.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    "get_weather": {
        "description": "בודק מזג אוויר ותחזית לכל עיר או מיקום בעולם באמצעות שירותי מזג אוויר פתוחים, ללא מפתח API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "שם עיר או מיקום, בעברית או באנגלית"},
                "days": {"type": "integer", "description": "מספר ימי תחזית להחזיר, 1 עד 7. עבור מחר השתמש ב-2"},
                "units": {"type": "string", "enum": ["metric", "imperial"], "description": "metric לצלזיוס וקמ״ש, imperial לפרנהייט ומייל לשעה"}
            },
            "required": ["location"]
        }
    },
    "smart_file_search": {
        "description": "סורק במהירות את המחשב לאיתור קבצים על פי שמם.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "שם הקובץ לחיפוש"}},
            "required": ["query"]
        }
    },
    "deep_content_search": {
        "description": "סורק עמוק בתוך קבצי טקסט/קוד בתיקייה מסוימת ומאתר מילות מפתח.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "התיקייה לסרוק בה"},
                "text": {"type": "string", "description": "הטקסט לחיפוש בתוך הקבצים"}
            },
            "required": ["directory", "text"]
        }
    },
    "capture_screen": {
        "description": "מצלם ומעביר אליך (המודל) את המסך הנוכחי של המשתמש להבנת ההקשר.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    "save_screenshot_to_disk": {
        "description": "שומר תמונת מסך לתיקיית התמונות של המשתמש.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    "set_volume": {
        "description": "שליטה בהשתקת השמע במחשב.",
        "inputSchema": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["MUTE", "UNMUTE"]}},
            "required": ["action"]
        }
    },
    "open_in_browser": {
        "description": "פותח כתובת או מבצע חיפוש בדפדפן הגלוי של המשתמש לצפייה.",
        "inputSchema": {
            "type": "object",
            "properties": {"query_or_url": {"type": "string"}},
            "required": ["query_or_url"]
        }
    },
    "get_tool_info": {
        "description": "שליפת סכמת JSON מלאה והוראות של כלי פייתון, MCP או כלי מורכב. חובה להפעיל לפני שימוש בכלי אם הסכמה שלו לא ידועה לך.",
        "inputSchema": {
            "type": "object",
            "properties": {"tool_name": {"type": "string", "description": "שם הכלי (או שם חבילת ה-MCP) שעבורו תרצה לקבל סכמה"}},
            "required": ["tool_name"]
        }
    },
    "search_tools": {
        "description": "חיפוש בקטלוג הכלים הפעילים של סמארטי, כולל כלים מובנים, כלי Python, חבילות MCP ומיומנויות, לפני בחירה, התקנה או יצירת יכולת.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Task, capability, tool name, package, or skill to search for."},
                "kind": {"type": "string", "enum": ["any", "builtin", "python", "mcp", "skill"], "description": "Optional catalog filter."},
                "include_disabled": {"type": "boolean", "description": "Include disabled or untrusted entries for diagnosis only."},
                "limit": {"type": "integer", "description": "Maximum results to return. Default 12."}
            }
        }
    },
    "agent_planner": {
        "description": "כלי פנימי לבקשת תכנון משימה, תכנון המשכי או תכנון מחדש. השתמש בו לפי שיקול דעתך רק כאשר תכנון מפורש ישפר איכות או בטיחות. אם יש אי-ודאות לגבי סביבת העבודה, קבצים, קוד, חלונות, מצב מערכת, סכמת כלי, תוכן קיים או תוצאה קודמת, התוכנית חייבת להתחיל ב-discovery קצר לפני פעולה משנה. ניתן לקרוא שוב לכלי כאשר מידע חדש, שגיאות חוזרות, כשלי אימות או שינויי סביבה מראים שהתוכנית הקודמת כבר אינה מתאימה.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["initial_plan", "continue_plan", "replan"], "description": "סוג התכנון המבוקש: ראשוני, המשכי, או תכנון מחדש אחרי מידע חדש/כשל."},
                "reason": {"type": "string", "description": "סיבה קצרה למה המשימה מצדיקה תכנון."},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "Detailed workflow steps for the agent. Include discovery/setup first when environment, files, UI state, previous output, or tool schema are uncertain. Steps should be operational, not generic."},
                "verification_points": {"type": "array", "items": {"type": "string"}, "description": "Concrete progress/final checks the agent should perform, including which observable result would prove the step succeeded. Mention tool-based checks when needed."},
                "contingencies": {"type": "array", "items": {"type": "string"}, "description": "Likely failures or branches and how the agent should react, including when to retry, replan, ask the user, or run discovery/verification tools."},
                "risk": {"type": "string", "enum": ["low", "medium", "high"], "description": "רמת סיכון משוערת."},
                "mode": {"type": "string", "enum": ["auto", "use_provided_steps", "ask_planner"], "description": "auto ברירת מחדל; use_provided_steps אם סיפקת צעדים טובים; ask_planner אם צריך Planner פנימי נוסף."}
            },
            "required": ["reason"]
        }
    },
    "email_manager": {
        "description": "Full IMAP/SMTP email tool: list folders, search, read, send, draft, reply, forward, mark, star, archive, move, copy, trash, delete, manage folders, and save attachments. For multi-message research, search metadata first and then read all selected UIDs in one bulk call; do not read many UIDs one by one.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list_folders", "search", "read", "send", "draft", "reply", "forward", "mark_read", "mark_unread", "star", "unstar", "archive", "trash", "delete", "move", "copy", "create_folder", "delete_folder", "rename_folder", "save_attachments"], "description": "Email operation to run."},
                "mailbox": {"type": "string", "description": "Source mailbox/folder. Defaults to INBOX."},
                "mailboxes": {"type": "array", "items": {"type": "string"}, "description": "Optional list of mailboxes to search."},
                "all_mailboxes": {"type": "boolean", "description": "Search every selectable mailbox. This can be slow and may return duplicate Gmail label copies."},
                "target_mailbox": {"type": "string", "description": "Destination mailbox for move/copy/archive/trash."},
                "folder": {"type": "string", "description": "Folder name for create/delete/rename."},
                "new_folder": {"type": "string", "description": "New folder name for rename_folder."},
                "uid": {"type": ["string", "integer"], "description": "Stable IMAP UID of one message."},
                "uids": {"type": "array", "items": {"type": ["string", "integer"]}, "description": "Stable IMAP UIDs for bulk operations. Prefer one read call with this field over serial read calls for each UID."},
                "query": {"type": "string", "description": "Search text or Gmail raw search query."},
                "from": {"type": "string", "description": "Optional sender search filter."},
                "to_filter": {"type": "string", "description": "Optional recipient search filter."},
                "subject_filter": {"type": "string", "description": "Optional subject search filter."},
                "since": {"type": "string", "description": "Optional date filter YYYY-MM-DD."},
                "before": {"type": "string", "description": "Optional date filter YYYY-MM-DD."},
                "unread": {"type": "boolean", "description": "Restrict search to unread messages."},
                "flagged": {"type": "boolean", "description": "Restrict search to starred/flagged messages."},
                "has_attachment": {"type": "boolean", "description": "Restrict search to messages with attachments where supported."},
                "count": {"type": "integer", "description": "Maximum number of messages to return. Default 10. Use 0 to return all matches."},
                "offset": {"type": "integer", "description": "Number of newest matching messages to skip."},
                "search_mode": {"type": "string", "enum": ["auto", "gmail", "imap", "scan"], "description": "auto uses Gmail/IMAP first and falls back to local header scanning when needed."},
                "scan_bodies": {"type": "boolean", "description": "When search_mode=scan, also inspect message bodies. Slower but deepest."},
                "scan_limit": {"type": "integer", "description": "Maximum messages to scan locally. 0 means no scan limit."},
                "include_body": {"type": "boolean", "description": "Include body text in search results. Keep false for broad discovery; fetch bodies afterward with a bulk read call to avoid oversized, truncated results."},
                "include_headers": {"type": "boolean", "description": "Include selected headers when reading."},
                "include_attachments": {"type": "boolean", "description": "Include attachment metadata."},
                "max_body_chars": {"type": "integer", "description": "Maximum body characters per message. For bulk reading, normally use 2000-4000; very large per-message limits create slow, truncated context and should be reserved for one specific message."},
                "to": {"type": ["string", "array"], "items": {"type": "string"}, "description": "Recipient(s) for send/reply/forward."},
                "cc": {"type": ["string", "array"], "items": {"type": "string"}, "description": "CC recipient(s)."},
                "bcc": {"type": ["string", "array"], "items": {"type": "string"}, "description": "BCC recipient(s)."},
                "subject": {"type": "string", "description": "Subject for send/draft."},
                "body": {"type": "string", "description": "Plain text body."},
                "html_body": {"type": "string", "description": "Optional HTML body. May be a fragment or a complete HTML document."},
                "direction": {"type": "string", "enum": ["auto", "rtl", "ltr"], "description": "Text direction for generated/styled HTML email. Use rtl for Hebrew."},
                "text_align": {"type": "string", "enum": ["auto", "right", "left", "center", "justify"], "description": "Text alignment for generated/styled HTML email."},
                "font_family": {"type": "string", "description": "Optional CSS font-family for generated HTML email."},
                "font_size_px": {"type": "integer", "description": "Optional base font size in pixels for generated HTML email."},
                "line_height": {"type": "string", "description": "Optional CSS line-height for generated HTML email, such as 1.6 or 24px."},
                "text_color": {"type": "string", "description": "Optional CSS text color for generated HTML email."},
                "background_color": {"type": "string", "description": "Optional CSS background color for generated HTML email."},
                "custom_css": {"type": "string", "description": "Optional extra CSS rules inserted into generated HTML email."},
                "content_mode": {"type": "string", "enum": ["auto", "plain", "html", "both"], "description": "auto sends HTML when html_body or style options are supplied; both sends plain text plus HTML alternative."},
                "from_name": {"type": "string", "description": "Optional per-message sender display name override."},
                "reply_to": {"type": ["string", "array"], "items": {"type": "string"}, "description": "Optional Reply-To address(es)."},
                "priority": {"type": "string", "enum": ["normal", "high", "low"], "description": "Optional message priority headers."},
                "request_read_receipt": {"type": "boolean", "description": "Request a read receipt when supported by the recipient client."},
                "headers": {"type": "object", "description": "Optional extra RFC 5322 headers. Core addressing headers are protected."},
                "attachments": {"type": "array", "items": {"type": "string"}, "description": "Local file paths to attach to outbound email."},
                "save_copy": {"type": "boolean", "description": "Append a copy of a sent message to Sent after SMTP send."},
                "output_dir": {"type": "string", "description": "Folder for save_attachments. Defaults to Smarti output folder."},
                "attachment_names": {"type": "array", "items": {"type": "string"}, "description": "Optional filenames to save from a message."},
                "confirm_destructive": {"type": "boolean", "description": "Must be true for permanent delete/delete_folder."}
            },
            "required": ["action"]
        }
    },
    "browser_automation_manager": {
        "description": "Structured control manager for Smarti dedicated persistent Chrome through Playwright/CDP.",
        "inputSchema": {
            "type": "object",
            "properties": {"action": {"type": "string", "description": "Browser action."}},
            "required": ["action"]
        }
    },
    "computer_automation_manager": {
        "description": "מנהל שליטה במחשב באמצעות Windows UI Automation (`auto`) ובמידת הצורך מקלדת/עכבר (`pa`).",
        "inputSchema": {
            "type": "object",
            "properties": {"action": {"type": "string", "description": "Computer automation action."}},
            "required": ["action"]
        }
    },
    "save_text_file": {
        "description": "שומר קבצי טקסט בלבד (txt, md, py, csv) לכונן. למסמכים כגון Word, צור קוד פייתון רלוונטי ב-create_python_tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "נתיב השמירה (או רק שם הקובץ לשמירה בתיקיית התוצרים)"},
                "content": {"type": "string", "description": "תוכן הקובץ"}
            },
            "required": ["path", "content"]
        }
    },
    "read_local_document": {
        "description": "קורא טקסט מקבצים מקומיים (.txt, .csv, .docx, .pdf).",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "נתיב מלא לקובץ"}},
            "required": ["path"]
        }
    },
    "list_skills": {
        "description": "מציג Skills זמינים, כולל Skills מובנים, מקומיים ו-Skills שהותקנו מ-ClawHub.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "search_skills": {
        "description": "מחפש Skills במאגר ClawHub בלבד. החיפוש מסנן תוצאות חשודות לפי יכולות המאגר.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "נושא או יכולת לחיפוש באנגלית או בעברית"}},
            "required": ["query"]
        }
    },
    "install_skill": {
        "description": "מתקין Skill. הסוכן רשאי להתקין רק מ-ClawHub; המשתמש יכול להתקין ידנית מתיקייה מקומית אם אישר זאת.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["clawhub", "local"], "description": "clawhub להתקנה מהמאגר המאושר; local להתקנה מתיקייה שהמשתמש בחר"},
                "id": {"type": "string", "description": "מזהה/slug/שם ה-Skill ב-ClawHub"},
                "path": {"type": "string", "description": "נתיב לתיקיית Skill מקומית כאשר source=local"}
            },
            "required": ["source"]
        }
    },
    "install_skill_requirements": {
        "description": "מתקין דרישות חיצוניות מוצהרות של Skill, כגון CLI או חבילת Python, רק לאחר אישור משתמש.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "שם ה-Skill שעבורו מתקינים דרישות"},
                "reason": {"type": "string", "description": "הסבר קצר למה ההתקנה נדרשת"}
            },
            "required": ["name"]
        }
    },
    "run_skill": {
        "description": "מפעיל Skill גבוה/תהליכי. חובה לשלוף סכמה דרך get_tool_info לפני שימוש אם אינך מכיר את הפרמטרים.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "שם ה-Skill להפעלה"},
                "arguments": {"type": "object", "description": "קלט מובנה לפי סכמת ה-Skill"}
            },
            "required": ["name"]
        }
    },
    "load_skill": {
        "description": "Loads the full instructions for a trusted Skill when the available_skills catalog clearly matches the task. Reading a Skill does not execute code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name from the available_skills catalog."},
                "task": {"type": "string", "description": "Brief task context so dependency guidance can be specific."}
            },
            "required": ["name"]
        }
    },
    "search_memory": {
        "description": "Search Smarti's structured memory with local RAG. Use this when a task may depend on prior preferences, tool history, project facts, or user facts. Treat results as context, not live truth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to retrieve from memory"},
                "memory_type": {"type": "string", "enum": ["any", "short_term", "long_term", "tool", "user"], "description": "Optional memory type filter"},
                "max_results": {"type": "integer", "description": "Maximum results to return, default 6"}
            },
            "required": ["query"]
        }
    },
    "update_memory": {
        "description": "מעדכן את הזיכרון ארוך הטווח באופן מפורש ומבוקר. אין להשתמש בסימני טקסט חופשי לעדכון זיכרון.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "הזיכרון החדש לשמירה"},
                "mode": {"type": "string", "enum": ["replace", "append", "clear"], "description": "replace מחליף, append מוסיף, clear מוחק"}
                ,"mode": {"type": "string", "enum": ["add", "append", "replace", "clear", "forget"], "description": "add/append saves, replace replaces a memory type, clear removes memories, forget removes by id"},
                "memory_type": {"type": "string", "enum": ["short_term", "long_term", "tool", "user"], "description": "Memory bucket. Default long_term."},
                "subject": {"type": "string", "description": "Short subject for retrieval and review"},
                "ttl_hours": {"type": "number", "description": "Expiry in hours. Use for short_term/tool/live/uncertain facts."},
                "importance": {"type": "number", "description": "1-5 retrieval priority. User preferences are usually 4-5."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional retrieval tags"},
                "memory_id": {"type": "string", "description": "Required for forget mode"}
            },
            "required": ["mode"]
        }
    },
    "git_status": {
        "description": "מריץ פעולות Git קריאה בלבד בתיקייה: status, diff, log או show.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "תיקיית repository"},
                "operation": {"type": "string", "enum": ["status", "diff", "log", "show"], "description": "פעולת Git קריאה בלבד"},
                "ref": {"type": "string", "description": "ref אופציונלי עבור show/log"}
            },
            "required": ["path", "operation"]
        }
    },
    "run_project_check": {
        "description": "מריץ פקודת בדיקה/Build מוגבלת בפרויקט, עם אישור לפי מדיניות.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "תיקיית הפרויקט"},
                "command": {"type": "string", "description": "פקודת בדיקה כגון pytest, npm test, python -m pytest או npm run build"}
            },
            "required": ["path", "command"]
        }
    },
    "list_processes": {
        "description": "מציג רשימת תהליכים פעילים באופן קריאה בלבד.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    "set_clipboard": {
        "description": "מעתיק טקסט ללוח הגזירים של Windows.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "הטקסט להעתקה"}},
            "required": ["text"]
        }
    },
    "extract_image_text": {
        "description": "OCR אופציונלי לתמונה מקומית באמצעות pytesseract אם מותקן.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "נתיב לתמונה"}},
            "required": ["path"]
        }
    }
}

BUILTIN_DYNAMIC_TOOLS = {
    "read_website": "קורא עמוד אינטרנט או זוחל אתר שלם בצורה מבוקרת.",
    "analyze_local_image": "ראייה ממוחשבת לקובץ מקומי.",
    "schedule_background_task": "תזמון פעולה מחזורית.",
    "list_background_tasks": "הצגת משימות רקע.",
    "cancel_background_task": "ביטול משימת רקע.",
    "retry_background_task": "הרצה מחדש של משימת רקע.",
    "open_software": "פתיחת תוכנה (למשל Chrome, Word).",
    "open_file_or_folder": "פותח קובץ או תיקייה באמצעות ברירת מחדל.",
    "list_software": "הצגת תוכנות מותקנות.",
    "get_weather": "מזג אוויר ותחזית גנרית לכל עיר או מיקום.",
    "smart_file_search": "סורק מהיר לאיתור קבצים לפי שם.",
    "deep_content_search": "חיפוש עמוק של טקסט בתוך קבצים.",
    "capture_screen": "צילום מסך והקשר חזותי.",
    "save_screenshot_to_disk": "שמירת צילום מסך כקובץ.",
    "set_volume": "השתקת השמע.",
    "email_manager": "Full email access through IMAP/SMTP. Use it for every email task: search/read by UID, send/draft/reply/forward, styled RTL/HTML messages, flags, archive/trash/delete/move/copy, folders, attachments. For Hebrew display-name searches use `from`, `subject_filter`, or `query`; auto mode falls back to local header scan. Use `count: 0` for all matches and preserve each result's `mailbox` when reading.",
    "browser_automation_manager": "Structured Chrome control manager through Smarti's persistent Playwright/CDP Chrome profile: stable tabs, accessibility snapshots/ref maps, act by ref, screenshots/PDF, console/errors/requests/trace, CDP, storage, dialogs, uploads, downloads, wait and evaluate.",
    "computer_automation_manager": "מנהל שליטה במחשב דרך Windows UI Automation (`auto`) ובמידת הצורך מקלדת/עכבר (`pa`).",
    "read_local_document": "קריאת טקסט מקבצי מסמכים.",
    "run_mcp": "הפעלת פונקציות מכלים חיצוניים שהותקנו.",
    "list_skills": "הצגת Skills זמינים.",
    "search_skills": "חיפוש Skills ב-ClawHub.",
    "install_skill": "התקנת Skill.",
    "install_skill_requirements": "התקנת דרישות חיצוניות של Skill.",
    "load_skill": "טעינת הוראות Skill.",
    "run_skill": "הרצת Skill.",
    "git_status": "Git קריאה בלבד: status, diff, log, show.",
    "run_project_check": "הרצת בדיקות או build בפרויקט תחת מדיניות.",
    "list_processes": "הצגת תהליכים פעילים.",
    "set_clipboard": "העתקת טקסט ללוח הגזירים.",
    "extract_image_text": "OCR אופציונלי מתמונה מקומית."
  }

BUILTIN_TOOL_SCHEMAS["computer_automation_manager"] = {
    "description": (
        "Stable Windows desktop control through Microsoft UI Automation. "
        "Prefer structured actions that inspect/find/invoke/set UIA elements. "
        "Raw code is an advanced fallback only; coordinate clicks are not part of the safe schema."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "inspect", "list_windows", "find", "get_focused",
                    "focus_window", "focus", "invoke", "click", "set_text",
                    "toggle", "select", "expand", "collapse",
                    "send_keys", "press", "hotkey", "code"
                ],
                "description": "Structured UIA action. Start with inspect/list_windows/find, then act on a resolved element."
            },
            "window": {"type": "string", "description": "Optional window title substring used as the search root."},
            "name": {"type": "string", "description": "Element accessible name substring."},
            "automation_id": {"type": "string", "description": "Exact UI Automation AutomationId."},
            "class_name": {"type": "string", "description": "ClassName substring. For window search this can identify the window."},
            "control_type": {"type": "string", "description": "Control type such as Button, Edit, MenuItem, CheckBox, ComboBox, Window."},
            "path": {"type": "string", "description": "Element path returned by inspect/find, for example 2/0/4. Prefer stable criteria when available."},
            "text": {"type": "string", "description": "Text for set_text, or key name fallback for press."},
            "keys": {"type": ["string", "array"], "items": {"type": "string"}, "description": "Keys for send_keys/hotkey/press. Hotkey may be a list like ['ctrl','s']."},
            "max_depth": {"type": "integer", "description": "Tree depth for inspect/find. Default 2 for inspect, 5 for find."},
            "limit": {"type": "integer", "description": "Maximum windows/elements returned."},
            "timeout": {"type": "number", "description": "Seconds to wait when locating a window."},
            "include_offscreen": {"type": "boolean", "description": "Include offscreen controls in inspect results. Defaults to false."},
            "dry_run": {"type": "boolean", "description": "Resolve the target and return it without performing a mutating action."},
            "allow_mouse_fallback": {"type": "boolean", "description": "Only for invoke when InvokePattern is unavailable. Uses the resolved element bounds, not guessed coordinates."},
            "allow_clipboard_fallback": {"type": "boolean", "description": "For set_text when ValuePattern is unavailable. Defaults to true after focusing the target."},
            "allow_global_keys": {"type": "boolean", "description": "Required for keyboard actions without a resolved target/window."},
            "allow_destructive": {"type": "boolean", "description": "Required when the resolved element name/id/class looks destructive, such as delete/remove/reset. Use dry_run first and require user approval."},
            "code": {"type": "string", "description": "Advanced Python fallback. Do not use unless structured UIA actions cannot express the task. No imports; preloaded: auto, pa, time, paste_text, list_windows, find_window, activate_window, send_keys, press, hotkey."}
        },
        "required": ["action"]
    }
}
BUILTIN_DYNAMIC_TOOLS["computer_automation_manager"] = "Structured Windows UI Automation manager: inspect/list/find UIA elements, then invoke/set/focus them without guessed coordinates."

BUILTIN_TOOL_SCHEMAS["system_manager"] = {
    "description": "Unified local system tool. Use this for shell commands, project checks, git read-only status, process listing, clipboard text, and audio mute/unmute.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["run_command", "git_status", "run_project_check", "list_processes", "set_clipboard", "set_volume"], "description": "System operation to run."},
            "command": {"type": "string", "description": "PowerShell command for run_command, or test/build command for run_project_check."},
            "cwd": {"type": "string", "description": "Optional working directory for run_command."},
            "timeout_seconds": {"type": "integer", "description": "Optional command timeout override."},
            "require_approval": {"type": "boolean", "description": "Force explicit user approval before running command."},
            "explanation": {"type": "string", "description": "Short user-facing reason for the command."},
            "path": {"type": "string", "description": "Project/repository path for git_status or run_project_check."},
            "operation": {"type": "string", "enum": ["status", "diff", "log", "show"], "description": "Read-only git operation."},
            "ref": {"type": "string", "description": "Optional git ref for log/show."},
            "text": {"type": "string", "description": "Text for set_clipboard."},
            "volume_action": {"type": "string", "enum": ["MUTE", "UNMUTE"], "description": "Audio action for set_volume."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["software_manager"] = {
    "description": "Unified software launcher and installed-app discovery tool. Use list/find before open when the app name is uncertain.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "find", "open", "refresh"], "description": "Software operation."},
            "name": {"type": "string", "description": "App/program name to open."},
            "query": {"type": "string", "description": "Optional app search/filter text for list/find."},
            "limit": {"type": "integer", "description": "Maximum apps or matches to return."},
            "refresh": {"type": "boolean", "description": "Rebuild the app index before running."},
            "include_paths": {"type": "boolean", "description": "Include launch paths/AppIDs in output."},
            "format": {"type": "string", "enum": ["text", "json"], "description": "Output format. Default text."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["file_manager"] = {
    "description": "Unified file tool for safe open, text save, document read, filename search, content search, OCR, attaching local files to model context, and moving files/folders to the recycle bin.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["open", "save_text", "read_document", "search_files", "search_content", "extract_image_text", "attach", "trash"], "description": "File operation. Use attach to send a local file into the next model turn when the active provider supports it. Use trash for delete requests; it moves to Recycle Bin."},
            "path": {"type": "string", "description": "File/folder path for open, save_text, read_document, extract_image_text, attach, or trash."},
            "content": {"type": "string", "description": "Text content for save_text."},
            "query": {"type": "string", "description": "Filename query for search_files."},
            "directory": {"type": "string", "description": "Directory for search_content."},
            "text": {"type": "string", "description": "Text to search for in search_content."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["web_manager"] = {
    "description": "Unified web/network tool for search, reading a URL, opening a browser, and weather lookup.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "read", "open", "weather"], "description": "Web operation."},
            "query": {"type": "string", "description": "Search query, browser query, or weather location."},
            "url": {"type": "string", "description": "URL for read/open."},
            "query_or_url": {"type": "string", "description": "Browser query or URL for open."},
            "mode": {"type": "string", "enum": ["page", "crawl"], "description": "For action=read: page reads one URL; crawl reads multiple same-site pages."},
            "max_pages": {"type": "integer", "description": "For action=read crawl mode: maximum pages to fetch. Default 30."},
            "max_depth": {"type": "integer", "description": "For action=read crawl mode: maximum link depth. Default 2."},
            "max_total_chars": {"type": "integer", "description": "For action=read: total returned text character budget. Default 90000."},
            "max_page_chars": {"type": "integer", "description": "For action=read: character budget per page. Default 12000."},
            "include_links": {"type": "boolean", "description": "For action=read: include discovered links. Default true."},
            "max_links": {"type": "integer", "description": "For action=read: maximum discovered links in output. Default 80."},
            "same_domain": {"type": "boolean", "description": "For action=read crawl mode: restrict to starting domain. Default true."},
            "include_subdomains": {"type": "boolean", "description": "For action=read crawl mode: include subdomains. Default false."},
            "include_patterns": {"type": "array", "items": {"type": "string"}, "description": "For action=read crawl mode: optional URL allow filters."},
            "exclude_patterns": {"type": "array", "items": {"type": "string"}, "description": "For action=read crawl mode: optional URL deny filters."},
            "respect_robots_txt": {"type": "boolean", "description": "For action=read crawl mode: respect robots.txt. Default true."},
            "use_sitemap": {"type": "boolean", "description": "For action=read crawl mode: seed from sitemap.xml. Default true."},
            "delay_seconds": {"type": "number", "description": "For action=read crawl mode: delay between requests. Default 0.2."},
            "timeout_seconds": {"type": "integer", "description": "For action=read: HTTP timeout per request. Default 20."},
            "user_agent": {"type": "string", "description": "For action=read: optional custom User-Agent."},
            "location": {"type": "string", "description": "Weather location."},
            "days": {"type": "integer", "description": "Weather forecast days, 1-7."},
            "units": {"type": "string", "enum": ["metric", "imperial"], "description": "Weather units."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["screen_manager"] = {
    "description": "Unified screen and image-context tool for screenshot capture, saving screenshots, and local image analysis.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["capture", "save_screenshot", "analyze_image"], "description": "Screen/image operation."},
            "path": {"type": "string", "description": "Local image path for analyze_image."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["background_task_manager"] = {
    "description": "Unified background task tool for schedule, list, cancel, edit, and retry. "
                   "IMPORTANT: When scheduling/editing a task for the future, DO NOT execute the user's prompt request in the current turn. Only call this tool and report success.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["schedule", "list", "cancel", "edit", "retry"], "description": "Background task operation."},
            "delay_minutes": {"type": "number", "description": "Minutes until run/retry/edit rescheduled start."},
            "prompt": {"type": "string", "description": "Instruction to run later."},
            "repeat": {"type": "string", "enum": ["once", "interval", "weekly"], "description": "Repeat mode: once, interval, weekly."},
            "interval_minutes": {"type": "number", "description": "Minutes between repeated runs when repeat=interval."},
            "days_of_week": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Array of numbers from 0 (Monday) to 6 (Sunday) for repeat=weekly."
            },
            "conversation_mode": {
                "type": "string",
                "enum": ["current", "new", "dedicated"],
                "description": "Routing mode: current (same chat), new (new chat each run), dedicated (same persistent run chat)."
            },
            "id": {"type": "string", "description": "Task id for cancel/retry/edit."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["notification_manager"] = {
    "description": "Unified Windows notifications, reminders, calendar-event, and Windows Calendar/Clock opening tool. Use for attention-grabbing reminders and user-visible Windows toasts; chat messages should still be sent normally.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["send_toast", "schedule_reminder", "list_reminders", "cancel_reminder", "create_calendar_event", "open_windows_app"], "description": "Notification/reminder/calendar operation."},
            "title": {"type": "string", "description": "Notification, reminder, or calendar event title."},
            "body": {"type": "string", "description": "Notification body."},
            "message": {"type": "string", "description": "Reminder or notification message."},
            "kind": {"type": "string", "enum": ["default", "reminder", "alarm", "important"], "description": "Windows toast tone/audio scenario."},
            "open_button": {"type": "boolean", "description": "Whether to include an Open Smarti button."},
            "delay_minutes": {"type": "number", "description": "Minutes until a scheduled reminder appears."},
            "repeat": {"type": "string", "enum": ["once", "interval"], "description": "Reminder repeat mode."},
            "interval_minutes": {"type": "number", "description": "Minutes between repeated reminders when repeat=interval."},
            "id": {"type": "string", "description": "Reminder/background task id for cancellation."},
            "target": {"type": "string", "enum": ["calendar", "clock", "alarms", "notification_settings", "focus_settings"], "description": "Windows app/settings target for open_windows_app."},
            "start": {"type": "string", "description": "Calendar event start time in ISO local format, e.g. 2026-06-03T15:30:00."},
            "end": {"type": "string", "description": "Calendar event end time in ISO local format."},
            "duration_minutes": {"type": "number", "description": "Calendar event duration if end is omitted."},
            "location": {"type": "string", "description": "Calendar event location."},
            "notes": {"type": "string", "description": "Calendar event notes/description."},
            "open": {"type": "boolean", "description": "Open the generated .ics calendar event file after creation."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["memory_manager"] = {
    "description": "Unified memory tool for search and update. Use only for durable or task-continuity memory.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "update"], "description": "Memory operation."},
            "query": {"type": "string", "description": "Search query."},
            "mode": {"type": "string", "enum": ["add", "append", "replace", "clear", "forget"], "description": "Update mode."},
            "content": {"type": "string", "description": "Memory content for add/append/replace."},
            "memory_type": {"type": "string", "enum": ["any", "short_term", "long_term", "tool", "user"], "description": "Memory bucket/filter."},
            "subject": {"type": "string", "description": "Short memory subject."},
            "ttl_hours": {"type": "number", "description": "Optional expiry in hours."},
            "importance": {"type": "integer", "description": "1-5 importance."},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
            "memory_id": {"type": "string", "description": "Entry id for forget."},
            "max_results": {"type": "integer", "description": "Maximum search results."}
        },
        "required": ["action"]
    }
}

BUILTIN_TOOL_SCHEMAS["extension_manager"] = {
    "description": "Unified extensions tool for MCP packages and Skills. Schema lookup is still required before run_mcp or run_skill.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search_mcp", "install_mcp", "run_mcp", "list_skills", "search_skills", "install_skill", "install_skill_requirements", "load_skill", "run_skill"], "description": "Extension operation."},
            "query": {"type": "string", "description": "Search query for search_mcp/search_skills."},
            "package": {"type": "string", "description": "MCP package name."},
            "function": {"type": "string", "description": "MCP function name."},
            "arguments": {"type": "object", "description": "Arguments for run_mcp or run_skill."},
            "source": {"type": "string", "description": "Skill source, usually clawhub."},
            "id": {"type": "string", "description": "Skill id/slug for install_skill."},
            "path": {"type": "string", "description": "Local skill path when explicitly approved."},
            "name": {"type": "string", "description": "Skill name for load_skill, run_skill, or install_skill_requirements."},
            "reason": {"type": "string", "description": "Reason for installing requirements."}
        },
        "required": ["action"]
    }
}

CANVAS_MANAGER_MODEL_GUIDANCE = """
חוזה שימוש לקנבס חזותי חי:
1. ברירת המחדל היא תשובת צ'אט רגילה. השתמש בקנבס רק לבקשה מפורשת לקנבס/לוח/דשבורד/טופס/תרשים/מצגת/ממשק אינטראקטיבי, או כאשר אינטראקציה אמיתית אינה מתאימה לבועת צ'אט. אל תיצור קנבס לברכה, תשובה רגילה, סיכום קצר, רשימה, טבלת Markdown או עדכון סטטוס.
2. כאשר קנבס מתאים, אסוף את המידע ובנה אותו אוטומטית לפני התשובה הסופית: לחיצה של המשתמש על הכפתור אחר כך רק פותחת את הקנבס שכבר נשמר, ואינה פותחת סבב מודל או צורכת טוקנים.
3. ממשק הכלי קצר ומדויק: `canvas_manager` מקבל שדות עליונים בלבד — `action` (`create`/`update`/`close`), `canvas_id` לעדכון או סגירה, `title`, `html`, ואופציונלית `css`, `javascript`, `buttons`, `images`. ב-`create` חובה `action:"create"`, `title` ו-`html`; אין לעטוף אותם ב-`data`, `content` או אובייקט אחר. ב-`update` השתמש ב-`canvas_id` הפעיל ובתוכן המלא המעודכן. אין צורך לבקש `get_tool_info` בשביל פעולה רגילה זו. כל טקסט שמוצג למשתמש — דיווחי התקדמות, כותרות הקנבס והתשובה — יישאר בשפת המשתמש; בשיחה עברית כתוב עברית. שאילתות חיפוש וקוד יכולים להיות באנגלית כשנחוץ.
4. הממשק מוסיף בעצמו כפתור מעוצב מתחת להודעה אחרי יצירה מוצלחת. אל תנסה ליצור פקד Markdown או קישור `canvas://`; מותר בהחלט לכתוב משפט טבעי המזמין את המשתמש לפתוח את הקנבס. אם יש כבר קנבס מתאים, עדכן אותו במקום ליצור עותק; צור קנבס נוסף רק כאשר המשתמש ביקש תוצר נפרד.
5. איכות חזותית היא חלק מהתוצר, לא קישוט: אל תסתפק בטבלה שטוחה. בנה חוויית editorial / product עדכנית עם היררכיה ברורה, פתיח בעל מסר, כרטיסי תוכן, צבעים וטיפוגרפיה עקביים, רווח לבן, מצבי hover/focus ומבנה רספונסיבי. צור סיפור חזותי המתאים לנושא עם מבט־על, ניווט, פרטים והרחבה.
6. השתמש בגילוי הדרגתי ובפקדים רק כשהם משרתים את התוכן: טאבים, מסננים, אקורדיונים, תפריטי בחירה, מתגים, סליידרים, timeline או תצוגת־פרטים. כל פקד חייב לשנות מצב או תוכן בפועל; אל תייצר פקדי־דמה. שמור על נגישות, RTL כשהתוכן עברי, וניווט מקלדת בסיסי.
7. אם המשתמש לא ביקש קנבס אך למשימה יש ערך חזותי או אינטראקטיבי גבוה וברור, מותר להציע פעם אחת ובמשפט קצר הדגמה חזותית. הצע רק כשיש תועלת קונקרטית מעבר לצ'אט, יש מספיק תוכן להדגמה, וההצעה טבעית להמשך השיחה. אל תציע עבור הודעות שגרתיות, תשובות קצרות, או אחרי שהמשתמש כבר סירב; אל תחזור על אותה הצעה באותה משימה. צור קנבס במקרה זה רק אחרי הסכמה מפורשת של המשתמש.
8. HTML/CSS/JavaScript מקומיים ועצמאיים בלבד: אין CDN, הורדות, חלונות חדשים או גישה למערכת. לתמונות השתמש ב-SVG מקומי בתוך HTML או ב-`images` עם `data_url` מסוג `data:image/...`, שאליו מפנים כ-`smarti-image://<id>`. URL של תמונת רשת מותר רק אם ההנחיה הפעילה מאשרת זאת במפורש. פעולת משתמש בתוך הקנבס נשלחת רק מ-event אמיתי באמצעות `window.SmartiCanvas.send(action, data)`.
9. גבול אימות מחייב: עד שהתשובה הסופית נשלחת, כפתור פתיחת הקנבס עדיין לא נוסף והקנבס אינו מוצג. לכן אל תנסה לפתוח אותו, לצלם אותו, או לאמת אותו חזותית באמצעות `screen_manager`, `browser_automation_manager`, `computer_automation_manager` או כלי צילום/מסך אחר. לפני הקריאה ל-`canvas_manager`, בדוק את ה-HTML/CSS/JavaScript הגולמיים, מבנה התוכן, RTL, נגישות בסיסית והפקדים. אחרי תשובת SUCCESS של create/update, התייחס לקבלת המקור ולשמירתו כהשלמת האימות האפשרי בשלב זה וסיים בתשובה סופית. אימות חזותי אפשרי רק בסבב מאוחר יותר, אחרי שהמשתמש פתח את הקנבס וביקש במפורש לבדוק אותו.
10. בתשובה הסופית תאר בקצרה מה נבנה, בלי להדפיס HTML או JavaScript.
""".strip()

CANVAS_MANAGER_COMPACT_GUIDANCE = """
קנבס הוא תוצר חזותי/אינטראקטיבי אופציונלי, לא ברירת מחדל. צור אותו לבקשה מפורשת
לקנבס/לוח/דשבורד/טופס/תרשים/ממשק, או רק כשבועת צ'אט אינה יכולה לבטא היטב את
האינטראקציה; אחרת ענה בצ'אט. אם רק נראה שעשוי להועיל, הצע פעם אחת וצור רק אחרי
הסכמה. הקריאה הישירה היא `canvas_manager` עם action create/update/close ושדות עליונים
title/html/css/javascript/buttons/images; אין צורך ב-get_tool_info לשימוש רגיל.
בנה HTML/CSS/JS מקומיים, נגישים, רספונסיביים ו-RTL לפי הצורך, עם היררכיה ופקדים
אמיתיים—not פקדי דמה. אין CDN, הורדות, חלונות חדשים או גישת מערכת; תמונות לפי מדיניות
התמונות הפעילה. אמת את המקור, התוכן והפקדים לפני הקריאה. באותו סבב אין עדיין תצוגה
או כפתור פתיחה, ולכן אסור לבקש צילום מסך/אימות חזותי; SUCCESS מאשר שמירת המקור.
התשובה הסופית מתארת בקצרה מה נבנה ואינה מדפיסה קוד.
""".strip()

BUILTIN_TOOL_SCHEMAS["canvas_manager"] = {
    "description": (
        "Creates or updates the optional local Live Visual Canvas shown beside chat. Default to normal chat; use only for an explicit visual/interactive request or when chat cannot express the interaction. "
        "The HTML/CSS/JavaScript runs in an isolated local canvas with network, files, downloads, popups, and media permissions blocked. "
        "A successful create adds an Open Canvas button only after the final assistant response; before then the rendered canvas is unavailable, so validate the raw source and never request a screenshot or visual UI check in the same turn. The button only opens the already-created artifact and never calls the model. "
        "For a user form/button, JavaScript may call window.SmartiCanvas.send(action, data); this submits plain user data back through the normal agent run."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "update", "close"], "description": "Canvas operation."},
            "canvas_id": {"type": "string", "description": "Required for update or close; returned by create."},
            "title": {"type": "string", "description": "Short Hebrew title displayed above the canvas."},
            "html": {"type": "string", "description": "Complete local HTML, or body markup when css/javascript are supplied separately."},
            "css": {"type": "string", "description": "Optional local CSS when html is body markup."},
            "javascript": {"type": "string", "description": "Optional local JavaScript. Do not fetch URLs, open windows, or use system APIs. For user input use window.SmartiCanvas.send(action, data)."},
            "images": {
                "type": "array",
                "description": "Optional declared images. Use data_url for embedded data:image content; use url only when remote canvas images are explicitly enabled. Reference it in html as smarti-image://<id>.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"}, "data_url": {"type": "string"}, "url": {"type": "string"}, "alt": {"type": "string"}, "caption": {"type": "string"}
                    },
                    "required": ["id"]
                }
            },
            "buttons": {
                "type": "array",
                "description": "Optional declared interactive buttons and their intended positions; actual rendered positions are saved automatically.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"}, "label": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"},
                        "width": {"type": "number"}, "height": {"type": "number"}, "action": {"type": "string"}, "target": {"type": "string"}
                    }
                }
            }
        },
        "required": ["action"]
    }
}

# Google Drive is parked until the OAuth flow is reliable enough for end users.
# Keep the implementation in smarti/google_drive.py and SmartiCore.google_drive_manager
# for a future re-enable, but do not register it as a visible tool now.

BROWSER_AUTOMATION_ACTIONS = [
    "doctor", "status", "start", "stop", "profiles", "tabs",
    "open", "focus", "close", "navigate", "snapshot", "screenshot",
    "act", "console", "errors", "requests", "network", "trace",
    "storage", "cookies", "upload", "download", "dialog", "evaluate",
    "pdf", "cdp", "click", "clickCoords", "type", "fill", "press",
    "hover", "select", "wait", "scroll", "scrollIntoView", "resize",
    "close_tab", "close_browser", "close_all"
]

BROWSER_AUTOMATION_PROPERTIES = {
    "url": {"type": "string", "description": "URL for open/navigate/start."},
    "targetUrl": {"type": "string", "description": "Alias for url."},
    "profile": {"type": "string", "enum": ["smarti"], "description": "Browser profile. Only Smarti's persistent Playwright/CDP Chrome profile is supported."},
    "targetId": {"type": "string", "description": "Tab/window target id from tabs/snapshot results."},
    "tabId": {"type": "string", "description": "Alias for targetId."},
    "ref": {"type": "string", "description": "Stable element ref from snapshot, for example e12."},
    "snapshotEpoch": {"type": ["integer", "string"], "description": "Snapshot epoch returned with the ref. When supplied, the action verifies the ref belongs to that snapshot."},
    "refEpoch": {"type": ["integer", "string"], "description": "Alias for snapshotEpoch."},
    "allowStaleRef": {"type": "boolean", "description": "Advanced escape hatch: skip snapshotEpoch validation for a ref. Avoid unless recovering manually."},
    "refs": {"type": "string", "enum": ["aria", "dom"], "description": "Snapshot ref mode. aria uses accessibility-tree refs plus DOM actionable refs; dom is lighter."},
    "snapshotFormat": {"type": "string", "description": "Optional snapshot format hint, usually aria or dom."},
    "selector": {"type": "string", "description": "CSS selector fallback when no ref is available."},
    "role": {"type": "string", "description": "ARIA role locator fallback, usually with name."},
    "name": {"type": "string", "description": "Accessible name for role locator, or computer UI element name."},
    "textSelector": {"type": "string", "description": "Visible text locator fallback."},
    "request": {"type": "object", "description": "For action=act: nested action request with kind plus ref/selector/text/etc."},
    "kind": {"type": "string", "description": "For action=act: click/type/press/hover/select/upload/wait/evaluate/etc."},
    "text": {"type": "string", "description": "Text to type/fill, visible text to wait for, or key name for press."},
    "value": {"description": "Value for fill/select/storage/cookie operations."},
    "keys": {"type": ["string", "array"], "items": {"type": "string"}, "description": "Key or key sequence for press."},
    "label": {"type": "string", "description": "Visible select option label."},
    "index": {"type": "integer", "description": "Select option index."},
    "x": {"type": "number", "description": "Viewport x coordinate for clickCoords or scroll delta alias."},
    "y": {"type": "number", "description": "Viewport y coordinate for clickCoords or scroll delta alias."},
    "deltaX": {"type": "number", "description": "Horizontal scroll delta."},
    "deltaY": {"type": "number", "description": "Vertical scroll delta."},
    "width": {"type": "integer", "description": "Viewport width for resize."},
    "height": {"type": "integer", "description": "Viewport height for resize."},
    "path": {"type": "string", "description": "Output path for screenshot/pdf or upload file path."},
    "paths": {"type": "array", "items": {"type": "string"}, "description": "Local files for upload."},
    "files": {"type": "array", "items": {"type": "string"}, "description": "Alias for paths."},
    "timeoutMs": {"type": "integer", "description": "Wait/action timeout in milliseconds."},
    "timeMs": {"type": "integer", "description": "Fixed wait duration in milliseconds."},
    "limit": {"type": "integer", "description": "Maximum snapshot elements/log entries."},
    "maxChars": {"type": "integer", "description": "Maximum compact snapshot characters."},
    "bodyChars": {"type": "integer", "description": "Maximum page body characters in snapshot."},
    "maxBodyChars": {"type": "integer", "description": "Maximum request/response body preview characters for requests."},
    "htmlChars": {"type": "integer", "description": "Maximum per-element HTML characters in snapshot."},
    "urls": {"type": "boolean", "description": "Include href/src in snapshot elements."},
    "includeUrls": {"type": "boolean", "description": "Alias for urls."},
    "includeHidden": {"type": "boolean", "description": "Include hidden/offscreen candidates in snapshot."},
    "fullPage": {"type": "boolean", "description": "Capture beyond viewport for screenshots when supported."},
    "clip": {"type": "object", "description": "Viewport clip for screenshot: x/y/width/height.", "properties": {"x": {"type": "number"}, "y": {"type": "number"}, "width": {"type": "number"}, "height": {"type": "number"}}},
    "labels": {"type": "boolean", "description": "Draw numbered element-ref overlays on screenshot and return annotations."},
    "annotate": {"type": "boolean", "description": "Alias for labels."},
    "includeBody": {"type": "boolean", "description": "Include captured fetch/XHR request/response body previews for action=requests."},
    "responseBody": {"type": "boolean", "description": "Alias for includeBody."},
    "captureMs": {"type": "integer", "description": "For requests/trace: actively capture DevTools events for this many milliseconds."},
    "reload": {"type": "boolean", "description": "For requests/trace: reload the page while capturing DevTools events."},
    "live": {"type": "boolean", "description": "For requests: briefly listen to live CDP Network events without reloading."},
    "record": {"type": "boolean", "description": "For trace: record a Chrome DevTools trace artifact."},
    "save": {"type": "boolean", "description": "Alias for record for trace artifacts."},
    "traceCategories": {"type": "string", "description": "Optional Chrome trace categories for action=trace record mode."},
    "includeValues": {"type": "boolean", "description": "For cookies, include cookie values. Defaults false/redacted."},
    "storage": {"type": "string", "enum": ["local", "session", "cookies"], "description": "Storage target."},
    "op": {"type": "string", "enum": ["get", "list", "set", "add", "delete", "remove", "clear"], "description": "Storage/cookie operation."},
    "operation": {"type": "string", "description": "Alias for op."},
    "key": {"type": "string", "description": "Storage key or cookie name."},
    "script": {"type": "string", "description": "JavaScript for evaluate/wait function."},
    "expression": {"type": "string", "description": "Alias for script."},
    "function": {"type": "string", "description": "JavaScript predicate for wait."},
    "method": {"type": "string", "description": "Chrome DevTools Protocol method for action=cdp, for example Runtime.evaluate."},
    "params": {"type": "object", "description": "Chrome DevTools Protocol params object for action=cdp."},
    "urlContains": {"type": "string", "description": "URL substring to wait for."},
    "waitUntil": {"type": "string", "enum": ["commit", "domcontentloaded", "load", "networkidle"], "description": "Navigation wait state."},
    "state": {"type": "string", "description": "Load state for action=wait."},
    "accept": {"type": "boolean", "description": "Accept or dismiss current dialog."},
    "expectDialog": {"type": "boolean", "description": "Install a dialog handler around the triggering action."},
    "promptText": {"type": "string", "description": "Text to enter into prompt dialogs."},
    "expectDownload": {"type": "boolean", "description": "Wrap click action in a Playwright download wait."},
    "downloadPath": {"type": "string", "description": "Destination file path for expected download."},
    "submit": {"type": "boolean", "description": "Press Enter after type/fill."},
    "clear": {"type": "boolean", "description": "Clear field before type/fill."},
    "slowly": {"type": "boolean", "description": "Type character by character."},
    "delay": {"type": "number", "description": "Delay between slow typing characters."},
    "delayMs": {"type": "integer", "description": "Delay between slow typing characters in milliseconds."},
    "newTab": {"type": "boolean", "description": "Open/navigate in a new tab."},
    "cleanup": {"type": "boolean", "description": "For tabs: close extra tabs after selecting the current tab."},
    "closeOthers": {"type": "boolean", "description": "For tabs: close all tabs except the selected/current tab."},
    "noSnapshot": {"type": "boolean", "description": "Skip post-action page snapshot."},
    "printBackground": {"type": "boolean", "description": "Print CSS backgrounds in PDF."},
    "landscape": {"type": "boolean", "description": "PDF landscape mode."},
}

BUILTIN_TOOL_SCHEMAS["browser_automation_manager"] = {
    "description": (
        "Structured browser automation manager for Smarti's persistent Chrome profile. Prefer snapshot -> act by ref. "
        "Supports profiles, stable tabs, accessibility snapshots/ref maps, navigation, screenshots, PDF, console/errors/requests/trace, CDP, storage/cookies, dialogs, upload, "
        "downloads, wait, and JavaScript evaluate. profile='smarti' uses Smarti's persistent Playwright/CDP browser. Raw Python browser code is not used."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": BROWSER_AUTOMATION_ACTIONS, "description": "Structured browser action."},
            **BROWSER_AUTOMATION_PROPERTIES,
        },
        "required": ["action"]
    },
}

BUILTIN_DYNAMIC_TOOLS.update({
    "system_manager": "Unified system: run_command, git_status, run_project_check, list_processes, set_clipboard, set_volume.",
    "software_manager": "Unified software launcher: list/find/open/refresh installed apps with cached discovery.",
    "file_manager": "Unified files: open, save_text, read_document, search_files, search_content, extract_image_text, attach local files to context, trash-to-Recycle-Bin.",
    "web_manager": "Unified web: search, page/site read/crawl, open, weather.",
    "screen_manager": "Unified screen/image context: capture, save_screenshot, analyze_image.",
    "background_task_manager": "Unified background tasks: schedule, list, cancel, retry.",
    "notification_manager": "Unified Windows toasts, reminders, calendar events, Calendar/Clock/settings opening.",
    "memory_manager": "Unified memory: search and update.",
    "extension_manager": "Unified MCP and Skills operations.",
    "search_tools": "Search Smarti's effective catalog before selecting, installing, or creating a tool.",
    "canvas_manager": "Live Visual Canvas for an explicit visual or interactive request. Use the compact canvas contract in the system instructions; a successful create adds a native Open Canvas button without another model call.",
    "browser_automation_manager": "Browser automation manager via Smarti's persistent Playwright/CDP Chrome profile: profiles, tabs, accessibility refs, act by ref, screenshots, PDF, console/errors/requests/trace, CDP, storage, dialogs, uploads, downloads, wait, evaluate.",
    "computer_automation_manager": "Computer automation manager via Windows UI Automation: inspect/list/find UIA elements, then invoke/set/focus them without guessed coordinates."
})

LEGACY_BUILTIN_TOOLS = {
    "system_command", "git_status", "run_project_check", "list_processes", "set_clipboard", "set_volume",
    "open_software", "list_software",
    "open_file_or_folder", "save_text_file", "read_local_document", "smart_file_search", "deep_content_search", "extract_image_text",
    "internet_search", "read_website", "open_in_browser", "get_weather",
    "capture_screen", "save_screenshot_to_disk", "analyze_local_image",
    "schedule_background_task", "list_background_tasks", "cancel_background_task", "retry_background_task",
    "search_memory", "update_memory",
    "search_mcp", "install_mcp", "run_mcp", "list_skills", "search_skills", "install_skill", "install_skill_requirements", "load_skill", "run_skill",
}

PUBLIC_BUILTIN_TOOLS = [
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
    "extension_manager",
    "create_python_tool"
]

TOOL_CATEGORY_LABELS = {
    "schema": "Schema/help",
    "system": "System",
    "software": "Software",
    "files": "Files",
    "web": "Web",
    "screen": "Screen",
    "tasks": "Background tasks",
    "memory": "Memory",
    "visual": "Visual canvas",
    "email": "Email",
    "automation": "Automation",
    "extensions": "Extensions",
    "developer": "Developer"
}

TOOL_CATEGORIES = {
    "agent_planner": "schema",
    "get_tool_info": "schema",
    "search_tools": "schema",
    "system_manager": "system",
    "software_manager": "software",
    "file_manager": "files",
    "web_manager": "web",
    "screen_manager": "screen",
    "background_task_manager": "tasks",
    "notification_manager": "tasks",
    "memory_manager": "memory",
    "canvas_manager": "visual",
    "email_manager": "email",
    "browser_automation_manager": "automation",
    "computer_automation_manager": "automation",
    "extension_manager": "extensions",
    "create_python_tool": "developer"
}

BUILT_IN_TOOLS = list(BUILTIN_TOOL_SCHEMAS.keys())

DEFAULT_SETTINGS = {
    "settings_schema_version": SETTINGS_SCHEMA_VERSION,
    "autonomy_mode": "balanced",
    "api_mode": "gemini",
    "gemini_api_key": "",
    "openai_api_key": "",
    "anthropic_api_key": "",
    "openrouter_api_key": "",
    "groq_api_key": "",
    "nvidia_api_key": "",
    "cerebras_api_key": "",
    "huggingface_api_key": "",
    "deepseek_api_key": "",
    "qwen_api_key": "",
    "zhipu_api_key": "",
    "moonshot_api_key": "",
    "mistral_api_key": "",
    "together_api_key": "",
    "perplexity_api_key": "",
    "xai_api_key": "",
    "tavily_api_key": "",
    "email_address": "",
    "email_password": "",
    "email_from_name": "",
    "email_imap_host": "",
    "email_imap_port": 993,
    "email_imap_ssl": True,
    "email_smtp_host": "",
    "email_smtp_port": 587,
    "email_smtp_ssl": False,
    "email_smtp_starttls": True,
    "email_drafts_mailbox": "",
    "email_sent_mailbox": "",
    "email_archive_mailbox": "",
    "email_trash_mailbox": "",
    "email_max_attachment_mb": 20,
    "selected_gemini_model": "gemini-3.1-flash-lite",
    "selected_openai_model": "gpt-5.4",
    "selected_openai_codex_signin_model": "Codex default",
    "selected_anthropic_model": "claude-opus-4-7",
    "selected_local_model": "",
    "selected_openrouter_model": "openai/gpt-5.4",
    "selected_groq_model": "openai/gpt-oss-120b",
    "selected_nvidia_model": "nvidia/llama-3.3-nemotron-super-49b-v1",
    "selected_cerebras_model": "gpt-oss-120b",
    "selected_huggingface_model": "openai/gpt-oss-120b",
    "selected_deepseek_model": "deepseek-v4-flash",
    "selected_qwen_model": "qwen-plus",
    "selected_zhipu_model": "glm-5.1",
    "selected_moonshot_model": "kimi-k2.6",
    "selected_mistral_model": "mistral-large-latest",
    "selected_together_model": "openai/gpt-oss-20b",
    "selected_perplexity_model": "sonar-pro",
    "selected_xai_model": "grok-4",
    "local_server_url": "http://localhost:1234/v1",
    "shopping_list": [],
    "user_memory": "",
    "read_aloud_all": False,
    "read_aloud_voice_only": True,
    "tts_voice_id": "edge:he-IL-HilaNeural",
    "tts_volume": 100,
    "voice_hotkey": "alt+v",
    "keep_running_in_tray": True,
    "updates_auto_check": True,
    "updates_check_interval_hours": 1,
    "updates_last_checked_at": "",
    "updates_last_available_version": "",
    "voice_sensitivity": 70,
    "voice_dynamic_energy_threshold": False,
    "voice_pause_threshold": 0.8,
    "voice_listen_timeout": 6,
    "voice_ambient_noise_duration": 0.0,
    "voice_beep_enabled": True,
    "enable_mcp_clawhub": False,
    "enable_skills_beta": True,
    "enable_tool_search_catalog": True,
    "skills_load_watch": True,
    "skill_install_unknown_scan_policy": "allow_with_warning",
    "skills_config": {},
    "enable_browser_automation": False,
    "enable_computer_control": False,
    "enable_visual_surfaces": False,
    "enable_web_canvas": False,
    "enable_canvas_remote_images": False,
    "max_agent_loops": 0,
    "enable_hierarchical_agent": True,
    # Kept under its historical key for settings compatibility. This value is
    # now prompt-only guidance for a typical complex task, not a hard quota.
    "max_agent_evaluations_per_task": 4,
    "allow_unlimited_agent_evaluations": True,
    # Context is compacted only under model-window token pressure. A value of
    # zero lets Smarti infer the active model window; exact or provider-wide
    # overrides can be supplied in agent_model_context_window_overrides.
    "agent_model_context_window_tokens": 0,
    "agent_model_context_window_overrides": {},
    "agent_context_compaction_trigger_ratio": 0.82,
    "agent_context_compaction_target_ratio": 0.55,
    "agent_context_recent_fraction": 0.30,
    "agent_context_output_reserve_tokens": 16384,
    "preserve_current_task_tool_context": False,
    "active_task_checkpoint_enabled": True,
    "network_auto_resume_enabled": True,
    "network_reconnect_wait_minutes": 180,
    "attachment_inline_max_mb": 20,
    "attachment_text_excerpt_chars": 10000,
    "conversation_attachments_limit": 80,
    "max_parallel_tool_calls": 4,
    "recent_tool_observations_limit": 40,
    "tool_context_transcript": [],
    "max_tool_context_entries": 400,
    "max_tool_context_chars": 120000,
    "max_tool_context_output_chars": 12000,
    "max_tool_context_prompt_chars": 30000,
    "historical_tool_context_recent_entries": 12,
    "historical_tool_context_relevant_entries": 8,
    "historical_tool_context_output_chars": 2200,
    "historical_tool_context_min_score": 2.0,
    "browser_snapshot_body_chars": 4000,
    "browser_snapshot_element_limit": 80,
    "browser_snapshot_html_chars": 500,
    "browser_snapshot_max_chars": 12000,
    "browser_allow_private_network": False,
    "browser_allowed_hosts": [],
    "browser_capture_dir": "",
    "browser_download_dir": "",
    "email_default_read_body_chars": 6000,
    "email_multi_read_body_chars": 3000,
    "privacy_redact_logs": True,
    "permission_level": 2,
    "custom_permission_profile_enabled": False,
    "policy_matrix": copy.deepcopy(DEFAULT_POLICY_MATRIX),
    "tool_trust": {},
    "mcp_registry": {},
    "skill_registry": {},
    "background_jobs": [],
    "background_recurring_catch_up_window_minutes": 15,
    "favorite_models": [],
    "settings_recent_searches": [],
    "ui_preferences": {
        "developer_trace": True,
        "sanitize_html": True,
        "lazy_settings_pages": True,
        "theme_mode": "dark",
        "settings_show_advanced": False
    },
    "privacy": {
        "redact_logs": True,
        "sanitize_html": True,
        "audit_enabled": True
    },
    "budgets": {
        "daily_token_budget": 0,
        "daily_cost_budget_usd": 0,
        "warn_when_budget_exceeded": True,
        "daily_token_warning_thresholds": [0.7, 0.85, 0.95],
        "budget_exclude_local_accounting": True
    },
    "enable_developer_trace": True,
    "audit_log_enabled": True,
    "legal_acceptance": {
        "accepted": False,
        "version": "",
        "accepted_at": "",
        "accepted_app_version": "",
        "document_title": ""
    },
    "safe_file_open_mode": "block_executables",
    "raw_shell_requires_approval": True,
    "marketplace_install_requires_approval": True,
    "permission_notification_timeout_seconds": 0,
    "external_code_requires_trust": True,
    "allow_autonomous_mcp_install": False,
    "mcp_env_allowlist": copy.deepcopy(DEFAULT_MCP_ENV_ALLOWLIST),
    "max_total_task_seconds": 0,
    "codex_request_timeout_seconds": 1800,
    "codex_protocol_repair_attempts": 2,
    "anthropic_prompt_cache_mode": "auto",
    "long_task_defaults_version": 1,
    "prevent_sleep_during_active_task": True,
    "conversation_summary": "",
    "memory": {
        "enabled": True,
        "auto_capture": True,
        "aggressive_capture": True,
        "rag_enabled": True,
        "always_include_user_memory": True,
        "user_memory_max_results": 8,
        "user_memory_max_injected_chars": 2200,
        "non_tool_memory_max_results": 6,
        "tool_memory_prompt_max_results": 3,
        "tool_memory_prompt_max_chars": 1400,
        "tool_memory_prompt_max_age_hours": 24,
        "tool_memory_requires_relevance": True,
        "max_results": 8,
        "max_injected_chars": 4200,
        "min_relevance_score": 4.2,
        "short_term_default_ttl_hours": 12,
        "conversation_ttl_hours": 168,
        "tool_memory_ttl_hours": 72,
        "capture_critical_user_details": True,
        "store_sensitive_personal_details": True,
        "critical_capture_max_chars": 1800,
        "verify_live_data": True,
        "log_rag_usage": True
    },
    "require_approval_for_cloud_upload": True,
    "mcp_require_pinned_versions": True,
    "mcp_protocol_version": "2025-11-25",
    "mcp_package_configs": {},
    "mcp_package_aliases": {},
    "max_concurrent_agents": 1,
    "ssl_trust_mode": SSL_MODE_SYSTEM,
    "ssl_custom_ca_path": "",
    "ssl_filter_setup_completed": False,
    "ssl_legacy_insecure_allowed_hosts": [],
    "ssl_trust_migration_version": SSL_TRUST_MIGRATION_VERSION,
    # Migration alias only. Runtime trust decisions use ssl_trust_mode and the
    # The legacy host list remains only for backward-compatible settings reads;
    # the explicit compatibility mode is now global and the UI always clears it.
    "allow_insecure_ssl_compat": False,
    "command_timeout_seconds": 60,
    "tool_timeout_seconds": 120,
    "mcp_timeout_seconds": 60,
    "max_tool_output_chars": 100000,
    "write_outside_allowed_dirs_requires_approval": True,
    "sandbox_enabled": False,
    "sandbox_root_dir": OUTPUTS_DIR,
    "sandbox_allow_read_outside": False,
    "default_output_dir": OUTPUTS_DIR,
    "allowed_write_dirs": [OUTPUTS_DIR],
    "mcp_allowed_directories": [APP_DIR],
    "allowed_mcp_packages": [],
    "background_tasks": [],
    "tools_config": {tool: True for tool in BUILT_IN_TOOLS}
}

# ==========================================
# פונקציות עזר UI
# ==========================================

__all__ = [name for name in globals() if not name.startswith("__")]
