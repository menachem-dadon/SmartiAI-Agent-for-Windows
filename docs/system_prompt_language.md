# Smarti system prompt language

Smarti uses English for application-owned model instructions by default. The
saved setting `system_prompt_language` accepts `en` and `he`; a missing setting
uses `en`. The original Hebrew templates remain available as a reversible backup.
The interface language remains Hebrew.

## Coverage and contracts

`smarti/prompt_language.py` contains paired static templates and translations of
built-in schema descriptions. Prompt construction selects a template before
inserting runtime values. Coverage includes:

- Full and local FastMode system prompts, provider tool-protocol guidance,
  permission and capability descriptions, memory guidance, background execution,
  notifications, files, computer automation, verification, and Canvas guidance.
- Built-in tool catalog descriptions, inline schemas, native provider schemas,
  `get_tool_info` action schemas, and validation/schema-retrieval guidance.
- Built-in Skill descriptions and schemas, Skill workflow wrappers, planner and
  evaluator instructions, fallback/replanning context, task-state guidance,
  tool-failure recovery, and internal-output recovery.
- Conversation title instructions. Titles follow the user's conversation
  language instead of requiring Hebrew.

Localization changes only static prose and known `description`/`title` schema
annotations. Tool names, routing, JSON keys, required fields, types, enums,
defaults, action scopes, validation, permissions, internal markers, and provider
protocols retain their contracts. The original schema objects are not modified.
Tool discovery searches both the Hebrew and English built-in descriptions.

User messages, memory entries, summaries, task observations, file content,
filenames, paths, URLs, and external Python/MCP/Skill instructions remain exact.
They can therefore contain Hebrew or other languages inside dynamic context.
English instructions do not require translating user data or rewriting external
schemas. Instructions that were already English remain English in both modes.

## User language policy

A prominent mandatory rule starts both the full and FastMode prompts, including
the Hebrew backup:

- Speak the user's language in progress reports, explanations, questions, and
  the final answer. Maintain that language throughout the conversation.
- Switch only when the user switches their conversational language or explicitly
  asks for another language. System/tool text, quotations, code, filenames,
  internal context, and model/provider changes are not requests to switch.
- A translation request changes the requested content's language, not the rest
  of the conversation. Use the established language when a message is ambiguous;
  in a new conversation use the user's natural-language message.
- Preserve literal code, identifiers, JSON, enums, paths, and URLs. Keep source
  text and user data exact unless the user requests translation of that content.
  Internal-output recovery also follows the established
  user language instead of forcing Hebrew.

The selected model still needs the ability to understand and produce the user's
language. Changing instruction language cannot add a missing model capability.

## Hebrew backup and persistence

In **הגדרות מתקדמות**, enable **הצג הגדרות מתקדמות** and find the **הנחיית מערכת**
group. **החזר את ההנחיה לעברית** saves `he`. It then becomes
**השתמש בהנחיה באנגלית**, which saves `en`. Search can reveal the field too.
The reference PyQt settings page provides the same backup action.

The desktop button uses the existing shared controls and scoped
`PATCH /v2/settings`. Core validates the value before applying any fields,
persists it through SettingsManager, and rebuilds the prompt. Save failure keeps
the prior displayed selection and supports retry; saving never resets settings,
memory, or conversation data. The choice survives settings migration and reload.

New source code is loaded on the next Core startup. Once loaded, the choice
applies to subsequent normal requests. An active request or a resumed checkpoint
can retain the prompt captured for that run; checkpoint data is not rewritten.

## Verification boundaries

Tests cover all built-in schema structures and action scopes, English prompt
branches, both language modes, template interpolation, untouched runtime and
external data, title/recovery language, and real gateway persistence/rejection
against temporary profiles. The Hebrew base prompt was compared with the prior
source across 48 setting combinations and was identical after excluding the new
language-policy prefix. Desktop tests cover persistence/reload, retry, search,
advanced visibility, and pending-save protection. Isolated Edge checks cover
light/dark, RTL, keyboard use, and widths 1280/360/280.

The execution ledger records actual test counts. These checks verify source,
contracts, and browser rendering. They do not establish quality improvement for
a live model, native acceptance, or a new installer/release.
