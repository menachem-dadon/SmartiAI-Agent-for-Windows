"""Builtin tool schemas and default Smarti settings."""
from .common import *
from .prompt_language import CANVAS_ENGLISH as _CANVAS_ENGLISH


# ==========================================
# Unified MCP/JSON Tool Definitions
# ==========================================
BUILTIN_TOOL_SCHEMAS = {
    "system_command": {
        "description": "Runs short PowerShell commands. Risky write/execution commands require approval and are blocked if they harm Smarti's core.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cwd": {"type": "string", "description": "Optional working directory for the command"},
                "timeout_seconds": {"type": "integer", "description": "Optional timeout override in seconds"},
                "command": {"type": "string", "description": 'The command to run'},
                "require_approval": {"type": "boolean", "description": 'Whether to explicitly ask the user for approval before execution'},
                "explanation": {"type": "string", "description": 'A brief explanation to the user of what the command does'}
            },
            "required": ["command"]
        }
    },
    "create_python_tool": {
        "description": 'Creates and saves a generic reusable Python tool in the repository. Create general parameterized code, not one-time code for a specific task.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": 'The tool name in English (without an extension).'},
                "code": {"type": "string", "description": 'The complete Python code. Write generic parameterized logic. The script receives a JSON object through sys.argv[1]. Use print to return results.'},
                "description": {"type": "string", "description": 'Pass a complete standard JSON Schema object here (as a String) describing the exact JSON structure the tool expects (type, description, properties, required).'},
                "require_approval": {"type": "boolean", "description": 'Whether the code is dangerous and requires approval.'}
            },
            "required": ["name", "code", "description"]
        }
    },
    "search_mcp": {
        "description": 'Search for new packages and capabilities in the global MCP registry (NPM).',
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": 'English search terms for the desired MCP package'}
            },
            "required": ["query"]
        }
    },
    "install_mcp": {
        "description": 'Installs an MCP package (server) that adds new capabilities. A pinned version is required, e.g. package@1.2.3 or @scope/package@1.2.3.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": 'The exact package name from NPM including a pinned version'}
            },
            "required": ["package"]
        }
    },
    "run_mcp": {
        "description": 'Runs a specific function from an installed MCP package.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": 'The exact MCP package name'},
                "function": {"type": "string", "description": 'The function name to execute from the package'},
                "arguments": {"type": "object", "description": 'The JSON object containing the parameters required by the function'}
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
        "description": 'Attaches a local image to the current agent-loop context. The agent analyzes it itself afterwards; there is no separate AI call.',
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": 'Full path to the image file'}},
            "required": ["path"]
        }
    },
    "schedule_background_task": {
        "description": 'Schedules a future action to run independently in the background. Supports one-time actions, recurring actions at minute intervals, or weekly actions on specific days. After calling this tool, do not execute the task now in the current conversation; only report that it was successfully scheduled.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "delay_minutes": {"type": "number", "description": 'Minutes to wait until the first run'},
                "prompt": {"type": "string", "description": 'The instruction to execute when the time arrives'},
                "repeat": {"type": "string", "enum": ["once", "interval", "weekly"], "description": 'once for a one-time task, interval for a recurring task, weekly for a task on selected weekdays'},
                "interval_minutes": {"type": "number", "description": 'Minutes between repeated runs when repeat=interval'},
                "days_of_week": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": 'An array of numbers from 0 (Monday) to 6 (Sunday) specifying execution weekdays when repeat=weekly'
                },
                "conversation_mode": {
                    "type": "string",
                    "enum": ["current", "new", "dedicated"],
                    "description": 'Conversation routing: current returns every run to the source conversation where the task was scheduled; new creates a new clean conversation each run; dedicated creates a dedicated conversation on the first run and reuses it for all subsequent cycles.'
                }
            },
            "required": ["delay_minutes", "prompt"]
        }
    },
    "list_background_tasks": {
        "description": 'Lists background tasks, status, execution time, and latest result.',
        "inputSchema": {"type": "object", "properties": {}}
    },
    "cancel_background_task": {
        "description": 'Cancels a background task by ID.',
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": 'The task ID'}},
            "required": ["id"]
        }
    },
    "retry_background_task": {
        "description": 'Reschedules an existing background task by ID.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": 'The task ID'},
                "delay_minutes": {"type": "number", "description": 'Minutes until the rescheduled run'}
            },
            "required": ["id"]
        }
    },
    "open_software": {
        "description": 'Opens installed software. Warning: only for opening system applications (such as Chrome, Word), not files!',
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": 'The software name'}},
            "required": ["name"]
        }
    },
    "open_file_or_folder": {
        "description": 'Opens files (video, Excel, images) or folders to show them to the user on screen.',
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": 'Full path to the file/folder'}},
            "required": ["path"]
        }
    },
    "trash_file_or_folder": {
        "description": 'Moves a file or folder to the Windows recycle bin. Use for all user-file deletion requests; it does not delete permanently.',
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": 'Full path to a file or folder to move to the recycle bin'}},
            "required": ["path"]
        }
    },
    "list_software": {
        "description": 'Lists software installed on the computer.',
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
        "description": 'Fast, current web search using a search engine. Returns online results.',
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    "get_weather": {
        "description": 'Checks weather and forecasts for any city or location worldwide using open weather services, without an API key.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": 'City or location name, in Hebrew or English'},
                "days": {"type": "integer", "description": 'Forecast days to return, 1 to 7. Use 2 for tomorrow'},
                "units": {"type": "string", "enum": ["metric", "imperial"], "description": 'metric for Celsius and km/h, imperial for Fahrenheit and mph'}
            },
            "required": ["location"]
        }
    },
    "smart_file_search": {
        "description": 'Quickly scans the computer for files by name.',
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": 'The filename to search for'}},
            "required": ["query"]
        }
    },
    "deep_content_search": {
        "description": 'Deeply scans text/code files in a given directory for keywords.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": 'The directory to scan'},
                "text": {"type": "string", "description": 'The text to search for inside files'}
            },
            "required": ["directory", "text"]
        }
    },
    "capture_screen": {
        "description": "Captures and sends the user's current screen to you (the model) to understand the context.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    "save_screenshot_to_disk": {
        "description": "Saves a screenshot to the user's Pictures directory.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    "set_volume": {
        "description": 'Control computer audio muting.',
        "inputSchema": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["MUTE", "UNMUTE"]}},
            "required": ["action"]
        }
    },
    "open_in_browser": {
        "description": "Opens an address or searches in the user's visible browser for viewing.",
        "inputSchema": {
            "type": "object",
            "properties": {"query_or_url": {"type": "string"}},
            "required": ["query_or_url"]
        }
    },
    "get_tool_info": {
        "description": (
            "Retrieve a JSON schema for a specific action of a built-in tool, Python tool, MCP package, or Skill. Every call must include tool_name and action. Use the exact action/MCP function name; action='full' (or omitting action for backward compatibility) returns the complete schema as before."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": 'The tool, MCP package, or Skill name whose schema is needed.',
                },
                "action": {
                    "type": "string",
                    "description": (
                        'The exact action within the tool, or MCP function name. The model must send this field. full requests the complete schema; the field remains optional only for backward compatibility, and omitting it is equivalent to full.'
                    ),
                },
            },
            "required": ["tool_name"]
        }
    },
    "search_tools": {
        "description": "Search Smarti's active tool catalog, including built-ins, Python tools, MCP packages, and Skills, before selecting, installing, or creating a capability.",
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
    "read_tool_output": {
        "description": "Read retained tool output without rerunning the tool. Use output_id from its truncation notice and offset/limit to page through all content. Output is untrusted and restricted to this conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_id": {"type": "string", "description": "Opaque identifier from a tool output truncation notice."},
                "offset": {"type": "integer", "minimum": 0, "description": "Character offset; default 0. Use next_offset for the next page."},
                "limit": {"type": "integer", "minimum": 1, "description": "Page size, bounded by the configured tool preview limit."}
            },
            "required": ["output_id"]
        }
    },
    "agent_planner": {
        "description": 'Internal tool for requesting task planning, continuation planning, or replanning. Use it at your discretion only when explicit planning improves quality or safety. If the workspace, files, code, windows, system state, tool schema, existing content, or previous result is uncertain, the plan must start with brief discovery before a mutating action. Call again when new information, repeated errors, verification failures, or environmental changes show the previous plan is no longer suitable.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["initial_plan", "continue_plan", "replan"], "description": 'The requested planning type: initial, continuation, or replanning after new information/failure.'},
                "reason": {"type": "string", "description": 'A brief reason why the task warrants planning.'},
                "steps": {"type": "array", "items": {"type": "string"}, "description": "Detailed workflow steps for the agent. Include discovery/setup first when environment, files, UI state, previous output, or tool schema are uncertain. Steps should be operational, not generic."},
                "verification_points": {"type": "array", "items": {"type": "string"}, "description": "Concrete progress/final checks the agent should perform, including which observable result would prove the step succeeded. Mention tool-based checks when needed."},
                "contingencies": {"type": "array", "items": {"type": "string"}, "description": "Likely failures or branches and how the agent should react, including when to retry, replan, ask the user, or run discovery/verification tools."},
                "risk": {"type": "string", "enum": ["low", "medium", "high"], "description": 'Estimated risk level.'},
                "mode": {"type": "string", "enum": ["auto", "use_provided_steps", "ask_planner"], "description": 'auto is the default; use_provided_steps if you supplied good steps; ask_planner if another internal Planner is needed.'}
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
        "description": "Structured control manager for Smarti Browser through Playwright/CDP.",
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
        "description": 'Saves only text files (txt, md, py, csv) to disk. For documents such as Word, create appropriate Python code with create_python_tool.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": 'Save path (or just the filename to save in the output directory)'},
                "content": {"type": "string", "description": 'The file content'}
            },
            "required": ["path", "content"]
        }
    },
    "read_local_document": {
        "description": 'Reads text from local files (.txt, .csv, .docx, .pdf).',
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": 'Full path to the file'}},
            "required": ["path"]
        }
    },
    "list_skills": {
        "description": 'Lists available Skills, including built-in, local, and ClawHub-installed Skills.',
        "inputSchema": {"type": "object", "properties": {}}
    },
    "search_skills": {
        "description": 'Searches for Skills only on ClawHub. The search filters suspicious results according to registry capabilities.',
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": 'Topic or capability to search for in English or Hebrew'}},
            "required": ["query"]
        }
    },
    "install_skill": {
        "description": 'Installs a Skill. The agent may install only from ClawHub; the user may manually install from a local directory if authorized.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["clawhub", "local"], "description": 'clawhub to install from the approved registry; local to install from a user-selected directory'},
                "id": {"type": "string", "description": 'The Skill identifier/slug/name on ClawHub'},
                "path": {"type": "string", "description": 'Path to a local Skill directory when source=local'}
            },
            "required": ["source"]
        }
    },
    "install_skill_requirements": {
        "description": 'Installs declared external Skill requirements, such as a CLI or Python package, only after user approval.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": 'The name of the Skill whose requirements are being installed'},
                "reason": {"type": "string", "description": 'A brief explanation of why installation is needed'}
            },
            "required": ["name"]
        }
    },
    "run_skill": {
        "description": 'Runs a high-level/workflow Skill. Before use, retrieve its schema through get_tool_info with the Skill name and its internal action as action, or full if it has no action field.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": 'The name of the Skill to run'},
                "arguments": {"type": "object", "description": 'Structured input according to the Skill schema'}
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
        "description": 'Updates long-term memory explicitly and in a controlled manner. Do not use free-text markers to update memory.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": 'The new memory to save'},
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
        "description": 'Runs read-only Git actions in a directory: status, diff, log, or show.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": 'Repository directory'},
                "operation": {"type": "string", "enum": ["status", "diff", "log", "show"], "description": 'Read-only Git action'},
                "ref": {"type": "string", "description": 'Optional ref for show/log'}
            },
            "required": ["path", "operation"]
        }
    },
    "run_project_check": {
        "description": 'Runs a limited project test/build command, with approval according to policy.',
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": 'Project directory'},
                "command": {"type": "string", "description": 'A test command such as pytest, npm test, python -m pytest, or npm run build'}
            },
            "required": ["path", "command"]
        }
    },
    "list_processes": {
        "description": 'Lists active processes in read-only mode.',
        "inputSchema": {"type": "object", "properties": {}}
    },
    "set_clipboard": {
        "description": 'Copies text to the Windows clipboard.',
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": 'The text to copy'}},
            "required": ["text"]
        }
    },

}

BUILTIN_DYNAMIC_TOOLS = {
    "read_website": 'Reads a web page or crawls an entire website in a controlled manner.',
    "analyze_local_image": 'Computer vision for a local file.',
    "schedule_background_task": 'Schedule a recurring action.',
    "list_background_tasks": 'List background tasks.',
    "cancel_background_task": 'Cancel a background task.',
    "retry_background_task": 'Reschedule a background task.',
    "open_software": 'Open an application (e.g. Chrome, Word).',
    "open_file_or_folder": 'Opens a file or folder with its default application.',
    "list_software": 'List installed software.',
    "get_weather": 'Generic weather and forecasts for any city or location.',
    "smart_file_search": 'Quick scanner to locate files by name.',
    "deep_content_search": 'Deep search for text inside files.',
    "capture_screen": 'Screen capture and visual context.',
    "save_screenshot_to_disk": 'Save a screenshot as a file.',
    "set_volume": 'Mute audio.',
    "email_manager": "Full email access through IMAP/SMTP. Use it for every email task: search/read by UID, send/draft/reply/forward, styled RTL/HTML messages, flags, archive/trash/delete/move/copy, folders, attachments. For Hebrew display-name searches use `from`, `subject_filter`, or `query`; auto mode falls back to local header scan. Use `count: 0` for all matches and preserve each result's `mailbox` when reading.",
    "browser_automation_manager": "Structured control of Smarti's embedded persistent browser through the native CDP bridge: stable tabs, accessibility snapshots/ref maps, act by ref, screenshots/PDF, console/errors/requests/trace, CDP, storage, dialogs, uploads, downloads, wait and evaluate.",
    "computer_automation_manager": "מנהל שליטה במחשב דרך Windows UI Automation (`auto`) ובמידת הצורך מקלדת/עכבר (`pa`).",
    "read_local_document": 'Read text from document files.',
    "run_mcp": 'Execute functions from installed external tools.',
    "list_skills": 'List available Skills.',
    "search_skills": 'Search for Skills on ClawHub.',
    "install_skill": 'Install a Skill.',
    "install_skill_requirements": "Install a Skill's external requirements.",
    "load_skill": 'Load Skill instructions.',
    "run_skill": 'Run a Skill.',
    "git_status": 'Read-only Git: status, diff, log, show.',
    "run_project_check": 'Run project tests or a build under policy.',
    "list_processes": 'List active processes.',
    "set_clipboard": 'Copy text to the clipboard.',
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

FILE_MANAGER_ACTIONS = [
    "open", "save_text", "read_document", "search_files", "search_content",
    "attach", "list_directory", "tree", "stat", "exists",
    "hash", "compare", "diff_text", "read_chunk", "disk_usage", "mkdir", "copy",
    "move", "rename", "atomic_write_text", "append_text", "touch", "batch",
    "trash", "restore_from_trash", "zip", "unzip",
]

FILE_MANAGER_MUTATING_ACTIONS = {
    "mkdir", "copy", "move", "rename", "atomic_write_text", "append_text",
    "touch", "trash", "restore_from_trash", "zip", "unzip",
}

FILE_MANAGER_OPERATION_PROPERTIES = {
    "action": {
        "type": "string",
        "enum": FILE_MANAGER_ACTIONS,
        "description": (
            "Filesystem operation. trash is the only public deletion operation and moves items "
            "to the Windows Recycle Bin; permanent delete is not exposed."
        ),
    },
    "path": {
        "type": "string",
        "description": (
            "Exact primary file/folder path. Required as the search root for search_files "
            "and as the root directory for tree."
        ),
    },
    "source": {"type": "string", "description": "Source path for copy, move, rename, compare, diff_text, zip, or unzip."},
    "destination": {"type": "string", "description": "Destination path for copy, move, rename, restore, zip, or unzip."},
    "other_path": {"type": "string", "description": "Second path alias for compare or diff_text."},
    "paths": {"type": "array", "items": {"type": "string"}, "description": "Multiple paths for attach, multi-read or zip operations. attach accepts mixed file types in one call."},
    "content": {"type": "string", "description": "Text content for save_text, atomic_write_text, or append_text."},
    "query": {
        "type": "string",
        "description": (
            "For search_files/tree: filename query. In match_mode=auto (default), wildcard "
            "queries use glob semantics (*, ?, [], and ** path segments); plain text is a substring."
        ),
    },
    "glob": {
        "type": "string",
        "description": "One include glob for search_files/tree, such as *.docx or reports/**/*.pdf.",
    },
    "globs": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Include entries matching any of these glob patterns.",
    },
    "exclude_globs": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Exclude matching entries and prune matching directories, for example [\".git\", \"node_modules/**\"].",
    },
    "extensions": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Allowed file extensions, with or without a leading dot, for example [\"docx\", \".doc\"].",
    },
    "match_mode": {
        "type": "string",
        "enum": ["auto", "glob", "substring", "exact"],
        "description": "How query is matched. Default auto; glob/globs are always glob patterns.",
    },
    "match_path": {
        "type": "boolean",
        "description": "Match query and separator-free globs against the relative path instead of only the basename.",
    },
    "case_sensitive": {
        "type": "boolean",
        "description": "Use case-sensitive filename matching. Default false for predictable Windows searches.",
    },
    "entry_type": {
        "type": "string",
        "enum": ["any", "file", "directory", "symlink", "other"],
        "description": "Filter result type. Default file for search_files and any for tree.",
    },
    "min_size": {
        "type": "string",
        "description": "Minimum file size as a string containing bytes or a unit, for example \"1024\", \"10MB\", or \"4KiB\".",
    },
    "max_size": {
        "type": "string",
        "description": "Maximum file size as a string containing bytes or a unit, for example \"500000\", \"2GB\", or \"500KiB\".",
    },
    "date_field": {
        "type": "string",
        "enum": ["created", "modified", "accessed"],
        "description": "Timestamp used by date_from/date_to. Default modified.",
    },
    "date_from": {
        "type": "string",
        "description": "Inclusive ISO-8601 lower date bound on date_field. A YYYY-MM-DD value starts at local midnight.",
    },
    "date_to": {
        "type": "string",
        "description": "Inclusive ISO-8601 upper date bound on date_field. A YYYY-MM-DD value includes the whole local day.",
    },
    "created_after": {"type": "string", "description": "Inclusive ISO-8601 creation-time lower bound."},
    "created_before": {"type": "string", "description": "Inclusive ISO-8601 creation-time upper bound."},
    "modified_after": {"type": "string", "description": "Inclusive ISO-8601 modification-time lower bound."},
    "modified_before": {"type": "string", "description": "Inclusive ISO-8601 modification-time upper bound."},
    "accessed_after": {"type": "string", "description": "Inclusive ISO-8601 access-time lower bound."},
    "accessed_before": {"type": "string", "description": "Inclusive ISO-8601 access-time upper bound."},
    "directory": {"type": "string", "description": "Directory for search_content."},
    "text": {"type": "string", "description": "Text to search for in search_content."},
    "recursive": {
        "type": "boolean",
        "description": (
            "For search_files, recurse below the root (default true). False restricts results to direct "
            "children. Choose from user intent: direct-folder wording can justify false, while requests "
            "for all matching files may reasonably include subfolders; this is guidance, not a forced rule."
        ),
    },
    "search_backend": {
        "type": "string",
        "enum": ["auto", "windows_search", "filesystem"],
        "description": (
            "search_files engine. auto prefers the Microsoft Windows Search indexing service (WSearch) "
            "and falls back when possible; windows_search explicitly queries its SystemIndex; filesystem "
            "performs an exact candidate-first directory scan and is not limited by index coverage."
        ),
    },
    "fallback_to_filesystem": {
        "type": "boolean",
        "description": (
            "If Windows Search is unavailable, fall back to the exact candidate-first filesystem engine. "
            "Default true for search_backend=auto and false for an explicit windows_search request. "
            "Windows-only content/property filters cannot be preserved by the fallback."
        ),
    },
    "verify_index_results": {
        "type": "boolean",
        "description": (
            "For Windows Search, stat and re-filter each indexed candidate against the live filesystem. "
            "Default true. This rejects stale hits but cannot discover files missing from the Windows index."
        ),
    },
    "content_query": {
        "type": "string",
        "description": (
            "Indexed full-text query for Microsoft Windows Search. Supports Office and other formats for "
            "which Windows has an installed content filter. Requires auto/windows_search."
        ),
    },
    "content_mode": {
        "type": "string",
        "enum": ["freetext", "contains", "phrase", "prefix"],
        "description": (
            "Windows indexed-content semantics. freetext (default) uses linguistic matching; contains "
            "accepts Windows Search CONTAINS grammar; phrase is exact phrase matching; prefix matches a phrase prefix."
        ),
    },
    "windows_kinds": {
        "type": "array",
        "items": {"type": "string"},
        "description": (
            "Filter System.Kind in the Microsoft Windows Search index, for example document, picture, "
            "music, video, email, folder, program, contact, calendar, task, note, link, or recordedtv."
        ),
    },
    "mime_types": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Filter indexed System.MIMEType values in Microsoft Windows Search.",
    },
    "windows_property_filters": {
        "type": "array",
        "description": (
            "Additional safe structured Windows Search SystemIndex predicates. Supported aliases: "
            "name, extension, size, created, modified, accessed, kind, mime_type, title, author, "
            "tags, subject, owner, content."
        ),
        "items": {
            "type": "object",
            "properties": {
                "property": {
                    "type": "string",
                    "enum": [
                        "name", "extension", "size", "created", "modified", "accessed",
                        "kind", "mime_type", "title", "author", "tags", "subject", "owner", "content",
                    ],
                },
                "operator": {
                    "type": "string",
                    "enum": ["eq", "ne", "gt", "gte", "lt", "lte", "contains", "freetext", "prefix"],
                },
                "value": {"type": "string"},
            },
            "required": ["property", "value"],
        },
    },
    "include_search_diagnostics": {
        "type": "boolean",
        "description": (
            "Include the generated read-only Windows Search SQL for diagnostics. Default false to save tokens."
        ),
    },
    "dry_run": {"type": "boolean", "description": "Resolve, validate, and preview a mutation without changing files."},
    "conflict": {"type": "string", "enum": ["fail", "rename", "overwrite"], "description": "Destination conflict policy. Default fail. overwrite must be explicit and approved."},
    "create_parents": {"type": "boolean", "description": "Create missing destination parent directories."},
    "expected_hash": {"type": "string", "description": "Expected SHA-256 of the source/current file or tree before mutation."},
    "algorithm": {"type": "string", "enum": ["sha256", "sha512", "blake2b"], "description": "Hash algorithm. Default sha256."},
    "encoding": {"type": "string", "description": "Safe text encoding. Default utf-8."},
    "mode": {"type": "string", "enum": ["text", "binary"], "description": "read_chunk output mode. Binary chunks are returned as base64."},
    "offset": {
        "type": "integer",
        "description": "Byte offset for read_chunk; result offset for paged search_files/tree output.",
    },
    "limit": {
        "type": "integer",
        "description": "Bounded result/chunk/item limit. search_files defaults to 100; tree defaults to 200; maximum 10000.",
    },
    "scan_limit": {
        "type": "integer",
        "description": "Maximum filesystem entries inspected by search_files/tree. Default 50000, maximum 1000000.",
    },
    "max_output_chars": {
        "type": "integer",
        "description": (
            "Hard character budget for search_files/tree output before paging. Defaults to 60000 "
            "for search_files and 40000 for tree; may be raised explicitly when full output is necessary."
        ),
    },
    "max_depth": {
        "type": "integer",
        "description": "Maximum directory recursion depth: 0 returns direct children only. Default 64 for search_files and 4 for tree.",
    },
    "min_depth": {
        "type": "integer",
        "description": "Minimum returned depth below the root. Direct children are depth 1.",
    },
    "sort_by": {
        "type": "string",
        "enum": [
            "path", "name", "type", "size", "created_at",
            "modified_at", "accessed_at", "search_rank",
        ],
        "description": (
            "Sort search_files/tree matches. Default path; indexed content_query defaults to search_rank."
        ),
    },
    "sort_order": {
        "type": "string",
        "enum": ["asc", "desc"],
        "description": "Sort direction. Default asc.",
    },
    "directories_first": {
        "type": "boolean",
        "description": "Keep directories before other result types after sorting.",
    },
    "detail": {
        "type": "string",
        "enum": ["minimal", "standard", "full"],
        "description": (
            "Metadata preset for record output. minimal is path/type, standard adds size/modified time, "
            "full preserves complete stat metadata. Default minimal."
        ),
    },
    "fields": {
        "type": "array",
        "items": {
            "type": "string",
            "enum": [
                "path", "name", "relative_path", "extension", "depth", "exists",
                "type", "size", "created_at", "modified_at", "accessed_at", "hidden",
                "read_only", "is_symlink", "is_reparse_point", "link_target",
                "windows_kind", "mime_type", "title", "authors", "tags", "search_rank",
            ],
        },
        "description": "Exact record fields to return; overrides detail and implies output_format=records unless a format is explicit.",
    },
    "output_format": {
        "type": "string",
        "enum": ["paths", "records", "text"],
        "description": (
            "search_files/tree output shape. paths (default) is the lowest-token structured list; "
            "records returns selected metadata; text returns one compact line per result."
        ),
    },
    "include_hidden": {"type": "boolean", "description": "Include hidden files in directory results."},
    "follow_symlinks": {"type": "boolean", "description": "Follow symlinks/reparse points only after explicit review. Default false."},
    "idempotency_key": {"type": "string", "description": "Task-stable key that prevents repeating the same mutation in the current runtime."},
    "preserve_timestamps": {"type": "boolean", "description": "Preserve supported file timestamps during copy/move. Default false."},
    "preserve_acl": {"type": "boolean", "description": "Reserved. ACL preservation is rejected until explicitly supported and tested."},
    "recycle_id": {"type": "string", "description": "Opaque recycle identifier returned by trash; use it to disambiguate restore_from_trash."},
}

BUILTIN_TOOL_SCHEMAS["file_manager"] = {
    "description": (
        "Complete safe filesystem manager: inspect/list/tree/stat/exists/hash/compare/diff/read chunks/disk usage; "
        "mkdir/copy/move/rename/atomic text write/append/touch/batch; safe zip/unzip; attach/open/read/search; "
        "attach accepts path or paths and supplies file contents to the current agent loop for continued analysis; "
        "it does not call another model or return an AI description. Analyze already attached images directly, "
        "including Hebrew text extraction. Supports reversible trash/restore. Mutations resolve exact paths, default to conflict=fail, are cancelable, "
        "and return observed per-item metadata. Permanent delete is not available."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            **FILE_MANAGER_OPERATION_PROPERTIES,
            "operations": {
                "type": "array",
                "description": "For action=batch: up to 100 explicit mutation objects with per-item results.",
                "items": {
                    "type": "object",
                    "properties": FILE_MANAGER_OPERATION_PROPERTIES,
                    "required": ["action"],
                },
            },
        },
        "required": ["action"],
    },
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
    "description": "Unified screen and image-context tool for screenshot capture and saving screenshots. analyze_image supplies the image to the current agent loop; it does not run a separate analysis task. For multiple local files use file_manager action=attach with paths.",
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
                "description": "Routing contract: current returns every run to the origin chat captured when scheduled (not whichever chat is active later); new creates a clean chat for every run; dedicated creates a separate chat on the first run and reuses it for every later cycle and retry."
            },
            "id": {"type": "string", "description": "Task id for cancel/retry/edit."}
        },
        "required": ["action"]
    }
}

NOTIFICATION_ACTION_ALIASES = {
    "notify": "send_toast",
    "send_notification": "send_toast",
    "remind": "schedule_reminder",
    "list": "list_reminders",
    "cancel": "cancel_reminder",
    "calendar_event": "create_calendar_event",
    "open_calendar": "open_windows_app",
    "open_clock": "open_windows_app",
    "open_alarms": "open_windows_app",
    "open_notification_settings": "open_windows_app",
    "open_focus_settings": "open_windows_app",
}

NOTIFICATION_TARGET_BY_ACTION = {
    "open_calendar": "calendar",
    "open_clock": "clock",
    "open_alarms": "alarms",
    "open_notification_settings": "notification_settings",
    "open_focus_settings": "focus_settings",
}

NOTIFICATION_TARGET_URIS = {
    "calendar": ("outlookcal:", "ms-calendar:"),
    "clock": ("ms-clock:",),
    "alarms": ("ms-clock:",),
    "notification_settings": ("ms-settings:notifications",),
    "focus_settings": (
        "ms-settings:quiethours",
        "ms-settings:quietmomentsscheduled",
        "ms-settings:notifications",
    ),
}

# This is the authoritative action-level policy map for notification_manager.
# Optional capabilities are added only when their matching side effect is requested.
NOTIFICATION_ACTION_POLICY = {
    "list_reminders": {
        "capabilities": (),
        "audit_capability": "safe_read",
        "risk": "low",
    },
    "send_toast": {
        "capabilities": ("notification_send",),
        "risk": "low",
    },
    "schedule_reminder": {
        "capabilities": ("background_task",),
        "risk": "medium",
    },
    "cancel_reminder": {
        "capabilities": ("background_task_cancel",),
        "risk": "medium",
    },
    "create_calendar_event": {
        "capabilities": ("calendar_write",),
        "optional_capabilities": {"open": "file_open"},
        "risk": "medium",
    },
    "open_windows_app": {
        "target_capabilities": {
            "calendar": "app_open",
            "clock": "app_open",
            "alarms": "app_open",
            "notification_settings": "settings_open",
            "focus_settings": "settings_open",
        },
        "risk": "low",
    },
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
    "description": "Inspect or transfer local memory. Per-turn add/update/delete decisions use the hidden final-response memory envelope, not this tool.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "get", "search", "export", "import", "stats"], "description": "Read-only inspection or explicit import/export operation."},
            "query": {"type": "string", "description": "Search query."},
            "memory_type": {"type": "string", "enum": ["any", "short_term", "long_term", "tool", "user"], "description": "Memory bucket/filter."},
            "memory_id": {"type": "string", "description": "Stable memory entry ID."},
            "status": {"type": "string", "enum": ["active", "archive", "session", "all"], "description": "State filter."},
            "category": {"type": "string", "description": "Category filter or explicit category."},
            "sensitivity": {"type": "string", "enum": ["ordinary", "sensitive", "any"], "description": "Sensitivity filter."},
            "source": {"type": "string", "description": "Source filter."},
            "date_range": {"type": "string", "enum": ["any", "7d", "30d", "90d"], "description": "Created/updated date filter."},
            "expiry": {"type": "string", "enum": ["any", "expiring", "never", "expired"], "description": "Expiry filter."},
            "path": {"type": "string", "description": "Import/export path."},
            "encrypted": {"type": "boolean", "description": "Export memory content in its encrypted-at-rest form."},
            "max_results": {"type": "integer", "description": "Maximum results."}
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

CANVAS_MANAGER_MODEL_GUIDANCE = _CANVAS_ENGLISH["full"]

CANVAS_MANAGER_COMPACT_GUIDANCE = _CANVAS_ENGLISH["compact"]

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
    "close_tab", "close_browser", "close_all", "text", "find", "frames",
    "double_click", "check", "drag", "show", "hide", "workspace", "pause", "resume",
    "click_coords", "scroll_into_view", "back", "forward", "reload", "stop_loading", "duplicate", "pin", "reorder"
]

BROWSER_AUTOMATION_PROPERTIES = {
    "url": {"type": "string", "description": "URL for open/navigate/start."},
    "pinned": {"type": "boolean", "description": "Desired pin state for a tab."},
    "requestId": {"type": "string", "description": "Optional stable action identity to retrieve an uncertain response without repeating a mutation."},
    "presentation": {"type": "string", "enum": ["preview", "hidden", "visible"], "description": "preview by default; hidden for quiet tasks; visible opens the same target for the user."},
    "workspaceId": {"type": "string", "description": "Owned browser workspace from results. Normally inferred from this conversation."},
    "frameId": {"type": "string", "description": "Frame from frames; selectors and refs are resolved inside this frame, including cross-origin frames."},
    "offset": {"type": "integer", "minimum": 0, "description": "Pagination offset."},
    "textOffset": {"type": "integer", "minimum": 0, "description": "Body text pagination offset for snapshot."},
    "nth": {"type": "integer", "minimum": 0, "description": "Explicit match index; ambiguous locators fail by default."},
    "exact": {"type": "boolean", "description": "Match the accessible name or text exactly."},
    "button": {"type": "string", "enum": ["left", "right", "middle"]},
    "modifiers": {"type": "array", "items": {"type": "string", "enum": ["Alt", "Control", "Meta", "Shift"]}},
    "checked": {"type": "boolean", "description": "Desired checked state; defaults true."},
    "toRef": {"type": "string", "description": "Destination ref for drag."},
    "toSelector": {"type": "string", "description": "Destination CSS selector for drag."},
    "values": {"type": "array", "items": {"type": "string"}, "description": "Select option values or labels."},
    "key": {"type": "string", "description": "Key or chord, e.g. Control+A or Enter."},
    "cookies": {"type": "array", "items": {"type": "object"}, "description": "Approved cookies for operation=set."},
    "targetUrl": {"type": "string", "description": "Alias for url."},
    "profile": {"type": "string", "enum": ["smarti", "guest"], "description": "Browser profile. Automation uses Smarti's persistent embedded profile."},
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
        "Structured browser automation manager for Smarti's persistent embedded browser profile. Prefer snapshot -> act by ref. "
        "Supports profiles, stable tabs, accessibility snapshots/ref maps, navigation, screenshots, PDF, console/errors/requests/trace, CDP, storage/cookies, dialogs, upload, "
        "downloads, wait, and JavaScript evaluate. profile='smarti' uses Smarti's persistent built-in WebView2 browser. Raw Python browser code is not used."
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

DOCUMENT_MANAGER_ACTIONS = (
    "doctor", "create", "edit", "inspect", "render", "visual_qa", "export", "compare",
)
DOCUMENT_MANAGER_BLOCK_TYPES = (
    "paragraph", "heading", "title", "subtitle", "quote", "callout", "list",
    "table", "image", "page_break", "section_break", "toc", "field",
    "hyperlink", "bookmark", "header", "footer", "content_control", "comment",
    "footnote", "endnote", "text_box", "shape", "chart", "equation", "advanced_com",
)
DOCUMENT_MANAGER_BLOCK_SCHEMA = {
    "type": "object",
    "description": "One structured document block. Properties not listed here remain available for the extensive formatting model described by get_tool_info.",
    "properties": {
        "type": {"type": "string", "enum": DOCUMENT_MANAGER_BLOCK_TYPES},
        "text": {"type": "string"},
        "runs": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
        "control_type": {
            "type": ["string", "integer"],
            "description": (
                "Content-control kind as a Word numeric constant or friendly name: rich_text, plain_text, picture, combo_box, "
                "dropdown_list, building_block_gallery, date, group, checkbox, repeating_section."
            ),
        },
        "checked": {"type": "boolean", "description": "Initial checkbox state for control_type=checkbox."},
        "items": {"type": "array", "description": "List items or content-control choices."},
        "chart_type": {
            "type": ["string", "integer"],
            "description": (
                "Chart kind as an Excel numeric constant or friendly name, including column_clustered, column_stacked, "
                "bar_clustered, line, line_markers, pie, doughnut, area, scatter, radar, and their documented variants."
            ),
        },
        "categories": {"type": "array", "description": "Chart category labels."},
        "series": {
            "type": "array",
            "description": "Chart series as [{name, values:[...]}]; value counts must match categories.",
            "items": {"type": "object", "additionalProperties": True},
        },
        "legend_position": {
            "type": ["string", "integer"],
            "description": "Chart legend position: bottom, corner, left, right, top, or a numeric Office constant.",
        },
        "url": {"type": "string", "description": "External hyperlink URL. Only http, https, and mailto are allowed."},
        "anchor": {"type": "string", "description": "Internal Word bookmark target for an in-document hyperlink or field."},
        "name": {"type": "string", "description": "Bookmark, style, or series name depending on block type."},
        "field_type": {
            "type": "string",
            "enum": [
                "AUTHOR", "COMMENTS", "CREATEDATE", "DATE", "FILENAME", "FILESIZE", "KEYWORDS",
                "LASTSAVEDBY", "NUMCHARS", "NUMPAGES", "NUMWORDS", "PAGE", "PAGEREF", "REF", "REVNUM",
                "SAVEDATE", "SECTION", "SECTIONPAGES", "SEQ", "STYLEREF", "SUBJECT", "TIME", "TITLE", "TOC",
            ],
            "description": "Safe Word field type; format adds a date/number picture switch where applicable.",
        },
        "code": {"type": "string", "description": "Explicit safe Word field code; external/dynamic field families are rejected."},
        "format": {"type": "string", "description": "Word field display format, for example dd/MM/yyyy."},
        "reference_text": {"type": "string", "description": "Optional custom footnote/endnote reference mark."},
        "selector": {"type": "object", "additionalProperties": True},
    },
    "additionalProperties": True,
}
DOCUMENT_MANAGER_PROPERTIES = {
    "engine": {
        "type": "string", "enum": ["auto", "com", "python", "libreoffice"],
        "default": "auto",
        "description": "Prefer auto: it selects python-docx for portable authoring and Word COM only for Word-only features/fidelity. Explicit engine pinning remains available; libreoffice is export/render only.",
    },
    "path": {"type": "string", "description": "Input document path, or output path alias for create."},
    "output_path": {"type": "string", "description": "Destination document/export path. Relative paths resolve inside Smarti outputs or the active sandbox."},
    "other_path": {"type": "string", "description": "Revised document path for compare."},
    "template_path": {"type": "string", "description": "Optional local DOCX/DOTX template for create."},
    "document": {
        "type": "object",
        "description": (
            "Structured document plan. Supports metadata, defaults, page, styles, header, footer, settings, and blocks/sections. "
            "Blocks include paragraph/heading/title/subtitle/quote/callout/list/table/image/page_break/section_break/toc/field/hyperlink/bookmark/header/footer/content_control; "
            "COM also supports comment/footnote/endnote/text_box/shape/chart/equation/advanced_com. Hebrew he-IL and RTL are defaults."
        ),
        "properties": {
            "metadata": {"type": "object", "additionalProperties": True},
            "defaults": {"type": "object", "additionalProperties": True},
            "page": {"type": "object", "additionalProperties": True},
            "styles": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            "header": {"type": "object", "additionalProperties": True},
            "footer": {"type": "object", "additionalProperties": True},
            "settings": {"type": "object", "additionalProperties": True},
            "blocks": {"type": "array", "items": DOCUMENT_MANAGER_BLOCK_SCHEMA},
            "sections": {"type": "array", "items": DOCUMENT_MANAGER_BLOCK_SCHEMA},
        },
        "additionalProperties": True,
    },
    "operations": {
        "type": "array",
        "description": (
            "Ordered edit operations. Portable: replace_text (including find/replace strings longer than Word Find's 255-character limit), append_blocks, insert_blocks, "
            "delete_paragraph, format_paragraph, set_page_layout, define_style, set_header, set_footer, update_fields, set_properties. COM additionally: format_range, "
            "delete_range, comments/notes, shapes/charts/equations, track/accept/reject changes, protect/unprotect, insert_file, advanced_com. Selectors support "
            "paragraph_index, find+occurrence, bookmark, character start/end, or table_index+row+column."
        ),
        "items": {"type": "object", "additionalProperties": True},
    },
    "format": {
        "type": "string",
        "enum": ["docx", "doc", "dotx", "docm", "dotm", "rtf", "txt", "html", "htm", "mhtml", "odt", "pdf", "xps"],
        "description": "Export format.",
    },
    "output_dir": {"type": "string", "description": "Directory for rendered page PNGs and QA PDF."},
    "export_formats": {
        "type": "array", "items": {"type": "string"},
        "description": "Optional formats to export immediately after create/edit, such as [\"pdf\"].",
    },
    "render_after": {"type": "boolean", "default": False, "description": "Render every page to PNG after create/edit for model visual QA."},
    "dpi": {"type": "integer", "default": 144, "description": "Render DPI, clamped to 72-300."},
    "page_limit": {"type": "integer", "default": 100, "description": "Maximum pages to render, clamped to 1-500."},
    "include_pdf": {"type": "boolean", "default": True, "description": "Retain the intermediate/final QA PDF."},
    "include_text": {"type": "boolean", "default": True, "description": "Include paragraph text in inspect output."},
    "paragraph_limit": {"type": "integer", "default": 200, "description": "Maximum paragraphs returned by inspect."},
    "backup": {"type": "boolean", "default": True, "description": "For in-place edits, create a timestamped backup first. Defaults true."},
    "overwrite": {"type": "boolean", "default": False, "description": "Allow replacing an existing destination. Replaced Word files are backed up."},
    "visible": {"type": "boolean", "default": False, "description": "Show the isolated Word COM window. This is not UI automation."},
    "timeout_seconds": {"type": "integer", "default": 180, "description": "COM/office timeout, clamped to 15-1800 seconds."},
    "allow_advanced_com": {
        "type": "boolean", "default": False,
        "description": "Explicitly enable structured advanced_com operations. VBA/macros, OLE, printing, sending, external opens/links, add-ins, and raw code remain blocked.",
    },
    "password": {"type": "string", "description": "Optional transient document protection/open password. Never store it in plans or logs."},
    "revised_author": {"type": "string", "description": "Revision author name for compare output."},
}
BUILTIN_TOOL_SCHEMAS["document_manager"] = {
    "description": (
        "Full structured Word document manager. Creates and edits Hebrew/RTL DOCX independently with python-docx/OOXML, uses isolated Microsoft Word COM for Word-only features, "
        "inspects, compares, converts/exports (including PDF/XPS), renders every page to PNG, and exposes each rendered page to the model through its own visual_qa action. No Word UI automation. "
        "Use get_tool_info(action=...) before each operation; load the built-in document_authoring Skill for planning/design policy on substantial documents."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": DOCUMENT_MANAGER_ACTIONS, "description": "Document operation."},
            **DOCUMENT_MANAGER_PROPERTIES,
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}

DOCUMENT_MANAGER_ACTION_GUIDANCE = {
    "doctor": "Use {\"action\":\"doctor\"} to detect Word COM, python-docx, LibreOffice, and PyMuPDF without launching Word.",
    "create": (
        "Create example: "
        '{"action":"create","engine":"auto","output_path":"report.docx","document":{'
        '"metadata":{"title":"דו״ח מסכם","author":"..."},'
        '"defaults":{"font":"Arial","font_size_pt":11},'
        '"page":{"size":"A4","orientation":"portrait","margins_cm":{"top":2.5,"bottom":2.5,"left":2,"right":2}},'
        '"styles":[{"name":"My Heading","type":"paragraph","based_on":"Heading 1","font_size_pt":18,"bold":true,"color":"17365D"}],'
        '"header":{"text":"שם המסמך"},"footer":{"text":"עמוד","page_number":true,"alignment":"center"},'
        '"blocks":[{"type":"title","text":"דו״ח מסכם"},{"type":"heading","level":1,"text":"מבוא"},'
        '{"type":"paragraph","runs":[{"text":"טקסט בעברית "},{"text":"English","rtl":false,"italic":true}]},'
        '{"type":"table","header_rows":1,"column_widths_cm":[5,9],"rows":[["נושא","פירוט"],["א׳","תוכן"]]},'
        '{"type":"toc"}]},"export_formats":["pdf"],"render_after":true}. '
        "Paragraph/run fields include style, font, font_size_pt, bold, italic, underline, strike, color, language, rtl, alignment, spacing, line_spacing, indents, keep/widow/page-break options. "
        "Lists use items (strings or {text,level,...}) plus ordered. Table cells may be strings or objects with text plus formatting/fill; merges use zero-based from_row/from_column/to_row/to_column. "
        "Portable blocks: paragraph, heading, title, subtitle, quote, callout, list, table, image, page_break, section_break, toc, field, hyperlink, bookmark, header, footer, content_control. "
        "COM adds comment, footnote, endnote, text_box, shape, chart, equation, and advanced_com. "
        "Use content_control control_type names such as checkbox (checked:true), chart_type names such as column_clustered, "
        "hyperlink anchor for internal bookmarks, and field_type+format for fields; numeric Office constants also remain supported."
    ),
    "edit": (
        "Edit example: "
        '{"action":"edit","path":"C:\\\\...\\\\report.docx","operations":['
        '{"op":"replace_text","find":"ישן","replace":"חדש","replace_all":true},'
        '{"op":"format_paragraph","selector":{"find":"כותרת","occurrence":1},"format":{"color":"17365D","bold":true}},'
        '{"op":"append_blocks","blocks":[{"type":"heading","level":1,"text":"נספח"}]},{"op":"update_fields"}],"render_after":true}. '
        "Selectors: paragraph_index; find/text+occurrence; bookmark; character start/end; or table_index+row+column (indices are zero-based). "
        "Portable operations include append_blocks and insert_blocks. Long literal find/replace strings are supported in both Python and COM; COM transparently bypasses Word Find's 255-character parameter limit. "
        "COM-only operations include format_range, delete_range, add_comment/footnote/endnote/text_box/shape/chart/equation, track_changes, accept/reject changes, protect/unprotect, insert_file, advanced_com. "
        "advanced_com: {op:'advanced_com',root:'document|application|options',path:[{member:'Sections',index:1},'PageSetup'],mode:'get|set|call',member:'...',value:...,args:[],kwargs:{}} and allow_advanced_com=true. "
        "Raw code, VBA/macros, OLE, printing, sending, add-ins, external opens/links, SaveAs, and export COM members remain blocked."
    ),
    "inspect": "Returns text/style indices, page geometry, tables/shapes, fields, RTL markers, and structural comment/note parts. It does not replace visual QA.",
    "render": "Exports to PDF and creates page-001.png etc. Review every returned PNG with document_manager action=visual_qa, fix defects, then re-render and review every page again.",
    "visual_qa": "Supplies one page PNG returned by document_manager render to the model for visual inspection. Call once for every rendered page; this is not a desktop screenshot or Word UI automation.",
    "export": "Supports Word DOC/DOCX/DOTX/DOCM/DOTM/RTF/TXT/HTML/MHTML/ODT/PDF/XPS through COM, LibreOffice fallback, and python DOCX/TXT. output_path must differ from source.",
    "compare": "Word COM only: path is original, other_path is revised, output_path receives a Word tracked-comparison DOCX; sources open read-only.",
}

# Property allowlists used by get_tool_info(action=...) to expose only the
# parameters relevant to one operation. The canonical full schemas above stay
# unchanged; missing action or action="full" therefore remains fully backward
# compatible. Keep this table complete for every public manager action.
_FILE_QUERY_FIELDS = (
    "path", "query", "glob", "globs", "exclude_globs", "extensions",
    "match_mode", "match_path", "case_sensitive", "entry_type", "min_size",
    "max_size", "date_field", "date_from", "date_to", "created_after",
    "created_before", "modified_after", "modified_before", "accessed_after",
    "accessed_before", "recursive", "search_backend", "fallback_to_filesystem",
    "verify_index_results", "content_query", "content_mode", "windows_kinds",
    "mime_types", "windows_property_filters", "include_search_diagnostics",
    "offset", "limit", "scan_limit", "max_output_chars", "max_depth",
    "min_depth", "sort_by", "sort_order", "directories_first", "detail",
    "fields", "output_format", "include_hidden", "follow_symlinks",
)
_FILE_TREE_FIELDS = tuple(
    field for field in _FILE_QUERY_FIELDS
    if field not in {
        "search_backend", "fallback_to_filesystem", "verify_index_results",
        "content_query", "content_mode", "windows_kinds", "mime_types",
        "windows_property_filters", "include_search_diagnostics",
    }
)
_FILE_MUTATION_FIELDS = (
    "dry_run", "conflict", "create_parents", "expected_hash",
    "idempotency_key", "preserve_timestamps", "preserve_acl",
)
_EMAIL_MESSAGE_FIELDS = (
    "to", "cc", "bcc", "subject", "body", "html_body", "direction",
    "text_align", "font_family", "font_size_px", "line_height", "text_color",
    "background_color", "custom_css", "content_mode", "from_name", "reply_to",
    "priority", "request_read_receipt", "headers", "attachments", "save_copy",
)
_EMAIL_SEARCH_FIELDS = (
    "mailbox", "mailboxes", "all_mailboxes", "query", "from", "to_filter",
    "subject_filter", "since", "before", "unread", "flagged",
    "has_attachment", "count", "offset", "search_mode", "scan_bodies",
    "scan_limit", "include_body", "max_body_chars",
)
_EMAIL_TARGET_FIELDS = ("mailbox", "uid", "uids")
_BROWSER_TAB_FIELDS = ("requestId", "profile", "targetId", "tabId", "workspaceId", "presentation", "frameId")
_BROWSER_REF_FIELDS = (
    "requestId", "targetId", "tabId", "ref", "snapshotEpoch", "refEpoch", "allowStaleRef",
    "selector", "role", "name", "textSelector", "nth", "exact", "frameId", "presentation",
)
_BROWSER_ACTION_TAIL = (
    "timeoutMs", "expectDialog", "promptText", "expectDownload",
    "downloadPath", "noSnapshot", "button", "modifiers",
)
_COMPUTER_TARGET_FIELDS = (
    "window", "name", "automation_id", "class_name", "control_type", "path",
    "timeout", "dry_run", "allow_destructive",
)

TOOL_ACTION_FIELDS = {
    "system_manager": {
        "run_command": ("command", "cwd", "timeout_seconds", "require_approval", "explanation"),
        "git_status": ("path", "operation", "ref"),
        "run_project_check": ("path", "command"),
        "list_processes": (),
        "set_clipboard": ("text",),
        "set_volume": ("volume_action",),
    },
    "software_manager": {
        "list": ("query", "limit", "refresh", "include_paths", "format"),
        "find": ("query", "limit", "refresh", "include_paths", "format"),
        "open": ("name",),
        "refresh": ("query", "limit", "refresh", "include_paths", "format"),
    },
    "file_manager": {
        "open": ("path",),
        "save_text": ("path", "content"),
        "read_document": ("path",),
        "search_files": _FILE_QUERY_FIELDS,
        "search_content": ("directory", "text"),
        "attach": ("path", "paths"),
        "list_directory": (
            "path", "offset", "limit", "sort_by", "sort_order",
            "directories_first", "detail", "fields", "output_format",
            "include_hidden", "follow_symlinks",
        ),
        "tree": _FILE_TREE_FIELDS,
        "stat": ("path", "paths", "follow_symlinks"),
        "exists": ("path", "paths", "follow_symlinks"),
        "hash": ("path", "paths", "algorithm", "follow_symlinks"),
        "compare": ("source", "destination", "other_path", "algorithm", "follow_symlinks"),
        "diff_text": ("source", "destination", "other_path", "encoding", "max_output_chars"),
        "read_chunk": ("path", "mode", "offset", "limit", "encoding"),
        "disk_usage": ("path", "paths", "follow_symlinks"),
        "mkdir": ("path",) + _FILE_MUTATION_FIELDS,
        "copy": ("source", "destination") + _FILE_MUTATION_FIELDS,
        "move": ("source", "destination") + _FILE_MUTATION_FIELDS,
        "rename": ("source", "destination") + _FILE_MUTATION_FIELDS,
        "atomic_write_text": ("path", "content", "encoding") + _FILE_MUTATION_FIELDS,
        "append_text": ("path", "content", "encoding") + _FILE_MUTATION_FIELDS,
        "touch": ("path",) + _FILE_MUTATION_FIELDS,
        "batch": ("operations", "dry_run", "idempotency_key"),
        "trash": ("path", "paths", "dry_run", "expected_hash", "idempotency_key"),
        "restore_from_trash": (
            "path", "recycle_id", "destination", "dry_run", "conflict",
            "create_parents", "idempotency_key",
        ),
        "zip": ("source", "path", "paths", "destination") + _FILE_MUTATION_FIELDS,
        "unzip": ("source", "destination") + _FILE_MUTATION_FIELDS,
    },
    "web_manager": {
        "search": ("query",),
        "read": (
            "url", "query", "mode", "max_pages", "max_depth",
            "max_total_chars", "max_page_chars", "include_links", "max_links",
            "same_domain", "include_subdomains", "include_patterns",
            "exclude_patterns", "respect_robots_txt", "use_sitemap",
            "delay_seconds", "timeout_seconds", "user_agent",
        ),
        "open": ("query_or_url", "url", "query"),
        "weather": ("location", "query", "days", "units"),
    },
    "screen_manager": {
        "capture": (),
        "save_screenshot": (),
        "analyze_image": ("path",),
    },
    "background_task_manager": {
        "schedule": ("delay_minutes", "prompt", "repeat", "interval_minutes", "days_of_week", "conversation_mode"),
        "list": (),
        "cancel": ("id",),
        "edit": ("id", "delay_minutes", "prompt", "repeat", "interval_minutes", "days_of_week", "conversation_mode"),
        "retry": ("id", "delay_minutes"),
    },
    "notification_manager": {
        "send_toast": ("title", "body", "message", "kind", "open_button"),
        "schedule_reminder": ("title", "message", "delay_minutes", "repeat", "interval_minutes"),
        "list_reminders": (),
        "cancel_reminder": ("id",),
        "create_calendar_event": ("title", "start", "end", "duration_minutes", "location", "notes", "open"),
        "open_windows_app": ("target",),
    },
    "memory_manager": {
        "list": ("query", "memory_type", "status", "category", "sensitivity", "source", "date_range", "expiry", "max_results"),
        "get": ("memory_id",),
        "search": ("query", "memory_type", "max_results"),
        "export": ("path", "encrypted"),
        "import": ("path",),
        "stats": (),
    },
    "canvas_manager": {
        "create": ("title", "html", "css", "javascript", "images", "buttons"),
        "update": ("canvas_id", "title", "html", "css", "javascript", "images", "buttons"),
        "close": ("canvas_id",),
    },
    "extension_manager": {
        "search_mcp": ("query",),
        "install_mcp": ("package",),
        "run_mcp": ("package", "function", "arguments"),
        "list_skills": (),
        "search_skills": ("query",),
        "install_skill": ("source", "id", "path"),
        "install_skill_requirements": ("name", "reason"),
        "load_skill": ("name",),
        "run_skill": ("name", "arguments"),
    },
    "email_manager": {
        "list_folders": (),
        "search": _EMAIL_SEARCH_FIELDS,
        "read": _EMAIL_TARGET_FIELDS + ("include_headers", "include_attachments", "max_body_chars"),
        "send": _EMAIL_MESSAGE_FIELDS,
        "draft": _EMAIL_MESSAGE_FIELDS,
        "reply": _EMAIL_TARGET_FIELDS + _EMAIL_MESSAGE_FIELDS,
        "forward": _EMAIL_TARGET_FIELDS + _EMAIL_MESSAGE_FIELDS,
        "mark_read": _EMAIL_TARGET_FIELDS,
        "mark_unread": _EMAIL_TARGET_FIELDS,
        "star": _EMAIL_TARGET_FIELDS,
        "unstar": _EMAIL_TARGET_FIELDS,
        "archive": _EMAIL_TARGET_FIELDS + ("target_mailbox",),
        "trash": _EMAIL_TARGET_FIELDS + ("target_mailbox",),
        "delete": _EMAIL_TARGET_FIELDS + ("confirm_destructive",),
        "move": _EMAIL_TARGET_FIELDS + ("target_mailbox",),
        "copy": _EMAIL_TARGET_FIELDS + ("target_mailbox",),
        "create_folder": ("folder",),
        "delete_folder": ("folder", "confirm_destructive"),
        "rename_folder": ("folder", "new_folder"),
        "save_attachments": _EMAIL_TARGET_FIELDS + ("output_dir", "attachment_names"),
    },
    "browser_automation_manager": {
        "back": _BROWSER_TAB_FIELDS,
        "forward": _BROWSER_TAB_FIELDS,
        "reload": _BROWSER_TAB_FIELDS,
        "stop_loading": _BROWSER_TAB_FIELDS,
        "duplicate": _BROWSER_TAB_FIELDS,
        "pin": _BROWSER_TAB_FIELDS + ("pinned",),
        "reorder": _BROWSER_TAB_FIELDS + ("index",),
        "double_click": _BROWSER_REF_FIELDS + _BROWSER_ACTION_TAIL,
        "click_coords": _BROWSER_TAB_FIELDS + ("x", "y") + _BROWSER_ACTION_TAIL,
        "scroll_into_view": _BROWSER_REF_FIELDS + ("noSnapshot",),
        "check": _BROWSER_REF_FIELDS + ("checked",) + _BROWSER_ACTION_TAIL,
        "drag": _BROWSER_REF_FIELDS + ("toRef", "toSelector") + _BROWSER_ACTION_TAIL,
        "text": _BROWSER_REF_FIELDS + ("offset", "limit"),
        "find": _BROWSER_REF_FIELDS + ("offset", "limit", "bodyChars"),
        "frames": _BROWSER_TAB_FIELDS,
        "show": _BROWSER_TAB_FIELDS,
        "hide": _BROWSER_TAB_FIELDS,
        "workspace": _BROWSER_TAB_FIELDS + ("operation",),
        "pause": _BROWSER_TAB_FIELDS,
        "resume": _BROWSER_TAB_FIELDS,
        "doctor": (),
        "status": ("profile",),
        "start": _BROWSER_TAB_FIELDS + ("url", "targetUrl", "noSnapshot"),
        "stop": _BROWSER_TAB_FIELDS,
        "profiles": (),
        "tabs": _BROWSER_TAB_FIELDS + ("cleanup", "closeOthers"),
        "open": _BROWSER_TAB_FIELDS + ("url", "targetUrl", "newTab", "waitUntil", "timeoutMs", "noSnapshot"),
        "focus": _BROWSER_TAB_FIELDS,
        "close": _BROWSER_TAB_FIELDS,
        "navigate": _BROWSER_TAB_FIELDS + ("url", "targetUrl", "newTab", "waitUntil", "timeoutMs", "noSnapshot"),
        "snapshot": _BROWSER_TAB_FIELDS + (
            "refs", "snapshotFormat", "limit", "maxChars", "bodyChars",
            "htmlChars", "urls", "includeUrls", "includeHidden", "offset", "textOffset",
        ),
        "screenshot": _BROWSER_REF_FIELDS + ("path", "fullPage", "clip", "labels", "annotate"),
        "act": _BROWSER_REF_FIELDS + (
            "request", "kind", "text", "value", "keys", "label", "index",
            "x", "y", "deltaX", "deltaY", "path", "paths", "files", "timeMs",
            "state", "script", "function", "urlContains", "submit", "clear",
            "slowly", "delay", "delayMs",
        ) + _BROWSER_ACTION_TAIL,
        "console": _BROWSER_TAB_FIELDS + ("limit",),
        "errors": _BROWSER_TAB_FIELDS + ("limit",),
        "requests": _BROWSER_TAB_FIELDS + ("limit", "includeBody", "responseBody", "maxBodyChars", "captureMs", "reload", "live"),
        "network": _BROWSER_TAB_FIELDS + ("limit", "includeBody", "responseBody", "maxBodyChars", "captureMs", "reload", "live"),
        "trace": _BROWSER_TAB_FIELDS + ("captureMs", "reload", "record", "save", "path", "traceCategories"),
        "storage": _BROWSER_TAB_FIELDS + ("kind", "storage", "op", "operation", "key", "value", "includeValues"),
        "cookies": _BROWSER_TAB_FIELDS + ("op", "operation", "cookies", "key", "value", "includeValues"),
        "upload": _BROWSER_REF_FIELDS + ("path", "paths", "files", "timeoutMs", "noSnapshot"),
        "download": _BROWSER_REF_FIELDS + ("path", "downloadPath", "timeoutMs", "noSnapshot"),
        "dialog": _BROWSER_TAB_FIELDS + ("operation", "accept", "promptText", "timeoutMs"),
        "evaluate": _BROWSER_TAB_FIELDS + ("script", "expression", "timeoutMs", "noSnapshot"),
        "pdf": _BROWSER_TAB_FIELDS + ("path", "printBackground", "landscape"),
        "cdp": _BROWSER_TAB_FIELDS + ("method", "params"),
        "click": _BROWSER_REF_FIELDS + _BROWSER_ACTION_TAIL,
        "clickCoords": _BROWSER_TAB_FIELDS + ("x", "y") + _BROWSER_ACTION_TAIL,
        "type": _BROWSER_REF_FIELDS + ("text", "value", "submit", "clear", "slowly", "delay", "delayMs") + _BROWSER_ACTION_TAIL,
        "fill": _BROWSER_REF_FIELDS + ("text", "value", "submit", "clear") + _BROWSER_ACTION_TAIL,
        "press": _BROWSER_REF_FIELDS + ("key", "keys", "text") + _BROWSER_ACTION_TAIL,
        "hover": _BROWSER_REF_FIELDS + _BROWSER_ACTION_TAIL,
        "select": _BROWSER_REF_FIELDS + ("value", "values", "label", "index") + _BROWSER_ACTION_TAIL,
        "wait": _BROWSER_REF_FIELDS + ("text", "url", "urlContains", "state", "timeMs", "timeoutMs"),
        "scroll": _BROWSER_REF_FIELDS + ("x", "y", "deltaX", "deltaY", "noSnapshot"),
        "scrollIntoView": _BROWSER_REF_FIELDS + ("noSnapshot",),
        "resize": _BROWSER_TAB_FIELDS + ("width", "height", "noSnapshot"),
        "close_tab": _BROWSER_TAB_FIELDS,
        "close_browser": _BROWSER_TAB_FIELDS,
        "close_all": _BROWSER_TAB_FIELDS,
    },
    "computer_automation_manager": {
        "inspect": _COMPUTER_TARGET_FIELDS + ("max_depth", "limit", "include_offscreen"),
        "list_windows": ("limit",),
        "find": _COMPUTER_TARGET_FIELDS + ("max_depth", "limit", "include_offscreen"),
        "get_focused": (),
        "focus_window": ("window", "class_name", "timeout", "dry_run"),
        "focus": _COMPUTER_TARGET_FIELDS,
        "invoke": _COMPUTER_TARGET_FIELDS + ("allow_mouse_fallback",),
        "click": _COMPUTER_TARGET_FIELDS + ("allow_mouse_fallback",),
        "set_text": _COMPUTER_TARGET_FIELDS + ("text", "allow_clipboard_fallback"),
        "toggle": _COMPUTER_TARGET_FIELDS,
        "select": _COMPUTER_TARGET_FIELDS,
        "expand": _COMPUTER_TARGET_FIELDS,
        "collapse": _COMPUTER_TARGET_FIELDS,
        "send_keys": _COMPUTER_TARGET_FIELDS + ("keys", "allow_global_keys"),
        "press": _COMPUTER_TARGET_FIELDS + ("keys", "text", "allow_global_keys"),
        "hotkey": _COMPUTER_TARGET_FIELDS + ("keys", "allow_global_keys"),
        "code": ("code",),
    },
    "document_manager": {
        "doctor": (),
        "create": (
            "output_path", "path", "engine", "template_path", "document",
            "overwrite", "visible", "timeout_seconds", "export_formats",
            "render_after", "output_dir", "dpi", "page_limit",
            "allow_advanced_com",
        ),
        "edit": (
            "path", "output_path", "engine", "operations", "backup", "overwrite",
            "visible", "timeout_seconds", "password", "export_formats",
            "render_after", "output_dir", "dpi", "page_limit",
            "allow_advanced_com",
        ),
        "inspect": ("path", "engine", "include_text", "paragraph_limit", "password"),
        "render": (
            "path", "engine", "output_dir", "dpi", "page_limit", "include_pdf",
            "visible", "timeout_seconds", "password",
        ),
        "visual_qa": ("path",),
        "export": (
            "path", "output_path", "format", "engine", "overwrite", "visible",
            "timeout_seconds", "password",
        ),
        "compare": (
            "path", "other_path", "output_path", "overwrite", "visible",
            "timeout_seconds", "revised_author",
        ),
    },
}

BUILTIN_DYNAMIC_TOOLS.update({
    "system_manager": "Unified system: run_command, git_status, run_project_check, list_processes, set_clipboard, set_volume.",
    "software_manager": "Unified software launcher: list/find/open/refresh installed apps with cached discovery.",
    "file_manager": "Complete safe filesystem manager: inspect/list/tree/stat/hash/compare/diff/chunks/disk usage; mkdir/copy/move/rename/atomic write/append/touch/batch; zip/unzip; open/read/search; reversible trash/restore. attach accepts path or paths (mixed types) and supplies contents to this agent loop for your analysis, without calling another model. Analyze already supplied images directly. No permanent delete.",
    "web_manager": "Unified web: search, page/site read/crawl, open, weather.",
    "screen_manager": "Unified screen/image context: capture, save_screenshot, analyze_image.",
    "background_task_manager": "Unified background tasks: schedule, list, cancel, retry.",
    "notification_manager": "Unified Windows toasts, reminders, calendar events, Calendar/Clock/settings opening.",
    "memory_manager": "Inspect/search or import/export local memory; semantic add/update/delete is embedded in final responses.",
    "extension_manager": "Unified MCP and Skills operations.",
    "search_tools": "Search Smarti's effective catalog before selecting, installing, or creating a tool.",
    "canvas_manager": "Live Visual Canvas for an explicit visual or interactive request. Use the compact canvas contract in the system instructions; a successful create adds a native Open Canvas button without another model call.",
    "browser_automation_manager": "Browser automation manager via Smarti's owned built-in WebView2 browser: profiles, tabs, accessibility refs, act by ref, screenshots, PDF, console/errors/requests/trace, CDP, storage, dialogs, uploads, downloads, wait, evaluate.",
    "computer_automation_manager": "Computer automation manager via Windows UI Automation: inspect/list/find UIA elements, then invoke/set/focus them without guessed coordinates.",
    "document_manager": "Structured Word/DOCX authoring, editing, COM automation, export/conversion, inspection, comparison, and page-PNG visual QA; Hebrew/RTL by default.",
})

LEGACY_BUILTIN_TOOLS = {
    "system_command", "git_status", "run_project_check", "list_processes", "set_clipboard", "set_volume",
    "open_software", "list_software",
    "open_file_or_folder", "save_text_file", "read_local_document", "smart_file_search", "deep_content_search",
    "internet_search", "read_website", "open_in_browser", "get_weather",
    "capture_screen", "save_screenshot_to_disk", "analyze_local_image",
    "schedule_background_task", "list_background_tasks", "cancel_background_task", "retry_background_task",
    "search_memory", "update_memory",
    "search_mcp", "install_mcp", "run_mcp", "list_skills", "search_skills", "install_skill", "install_skill_requirements", "load_skill", "run_skill",
}

PUBLIC_BUILTIN_TOOLS = [
    "get_tool_info",
    "search_tools",
    "read_tool_output",
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
    "documents": "Documents",
    "extensions": "Extensions",
    "developer": "Developer"
}

TOOL_CATEGORIES = {
    "agent_planner": "schema",
    "get_tool_info": "schema",
    "search_tools": "schema",
    "read_tool_output": "schema",
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
    "document_manager": "documents",
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
    "qwen_base_url": "",
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
    **{f"selected_{provider}_model": provider_default_model(provider) for provider in MODEL_PROVIDER_ORDER},
    "codex_reasoning_effort": "auto",
    "selected_model_source": {
        provider: MODEL_SELECTION_SOURCE_DEFAULT
        for provider in MODEL_PROVIDER_ORDER
    },
    "model_selection_provenance_version": MODEL_SELECTION_PROVENANCE_VERSION,
    "model_reasoning_efforts": {
        "gemini": {},
        "openai": {},
        "anthropic": {},
    },
    "local_server_url": "http://localhost:1234/v1",
    # Generate a concise, distinctive title as soon as the first turn starts.
    # "local" remains available for users who prefer zero extra model calls.
    "conversation_title_generation_mode": "ai",
    # Opt-in only: a local endpoint does not imply a small model or weak hardware.
    "local_fast_mode_enabled": False,
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
    "attachment_inline_max_mb": 25,
    "attachment_text_excerpt_chars": 10000,
    "conversation_attachments_limit": 80,
    "max_parallel_tool_calls": 4,
    "max_concurrent_conversation_runs": 0,
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
    "browser_embedded_primary": True,
    "browser_profile_import": {},
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
        "settings_show_advanced": False,
        "workspace_start_maximized": True,
        "workspace_sidebar_collapsed": False,
        "workspace_workbench_collapsed": True,
        "workspace_default_panel": "files"
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
        "retrieval_settings_version": 1,
        "enabled": True,
        "auto_capture": True,
        "aggressive_capture": False,
        "inferred_memory_unused_days": 30,
        "project_memory_unused_days": 90,
        "rag_enabled": True,
        "always_include_user_memory": False,
        "user_memory_max_results": 3,
        "user_memory_max_injected_chars": 1200,
        "non_tool_memory_max_results": 3,
        "tool_memory_prompt_max_results": 0,
        "tool_memory_prompt_max_chars": 0,
        "tool_memory_prompt_max_age_hours": 24,
        "tool_memory_requires_relevance": True,
        "max_results": 3,
        "max_injected_chars": 1200,
        "always_memory_max_results": 3,
        "always_memory_max_chars": 600,
        "min_relevance_score": 0.62,
        "short_term_default_ttl_hours": 12,
        "conversation_ttl_hours": 168,
        "tool_memory_ttl_hours": 72,
        "capture_critical_user_details": True,
        "sensitive_memory_encryption": "dpapi",
        "memory_management_refresh_seconds": 3,
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
    "approval_wait_timeout_seconds": 86400,
    "local_gateway_enabled": True,
    "local_gateway_port": 8765,
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
