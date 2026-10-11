# Smarti system and presentation languages

Application-owned model instructions and fixed tool responses are permanently
English. System language is independent of the user's conversation language and
provider. There is no Hebrew system fallback or language toggle. Settings
migration removes the obsolete `system_prompt_language` preference, and the
gateway rejects attempts to set it.

## English model layer

The English source includes full and local FastMode prompts, native and inline
tool schemas, action-specific schema discovery and validation, permission and
sandbox feedback, memory and background-work guidance, planner/evaluator/recovery
instructions, Canvas policy, builtin Skill metadata and workflow instructions,
untrusted-output and Skill security wrappers, and fixed tool success/error text.
Generated computer automation and MCP wrappers emit English boilerplate too.
Owned provider exceptions use machine diagnostics when returned by a tool;
external error messages and response bodies remain exact.

Names, JSON keys, required fields, types, enums, defaults, action scopes, routing,
permissions, approval decisions, native tool protocols, and internal markers
retain their contracts. Source schema prose is English, rather than being
translated as runtime payloads. Tool discovery accepts both English descriptions
and the Hebrew presentation catalog so existing Hebrew searches still work.

## User language and truthful process display

The mandatory policy at the start of every system prompt requires responses,
questions, titles, and model progress reports in the user's language. It keeps
the conversation language until the user changes their conversational language
or explicitly requests another language. English instructions/tool output,
quotations, code, filenames, and provider changes cannot cause a switch. A content
translation request applies only to the requested content.

Fixed application captions follow the application's interface language, currently
Hebrew, independently of conversation language. This includes prompt processing,
thinking, tool states, duration units, input/output headings and placeholders,
planning/Skill/compaction status, network/key waits, application errors, and
application-generated fallback reports. The process panel retains RTL even for
English conversations. Conversation-language metadata does not select UI text.
No interface-language setting or translation model is introduced.

Model-authored answers and progress reports remain in the user's conversation
language and are displayed without translation. The English system policy also
explains that application-authored interface text cannot switch that language.
New runs retain their content-language hint; existing metadata and stored text
are not rewritten. General settings and tool descriptions remain Hebrew; exact
tool names remain unchanged.

**Input and output frames display the actual payloads,
without translation.** Existing redaction, display limits, and retained-output
retrieval continue to apply. Audit logs and retained tool context record the real
new English tool response, not a translated display substitute.

User messages, dynamic results, saved memories/summaries, file content, paths,
URLs, quotes, requested document/email/notification content, external Python/MCP
schemas, and third-party Skill instructions remain exact. They can contain Hebrew
or other languages. The selected model still needs to understand and produce the
user's language; English instructions do not add that capability.

## Forward-only behavior

No chat/tool history migration or translation is performed. Legacy messages and
process metadata keep their original content; fixed rendered captions follow the
Hebrew interface. A new request or resumed task uses the current English system
instruction in its live
request. Resuming replaces only that live system slot; old user messages, tool
results, and saved data retain their original text. Normal checkpoint lifecycle
and persistence continue as before.

## Verification

Tests cover English prompt branches and schemas, a schema-contract hash captured
before this change, bilingual tool discovery, security/native/local feedback,
tool and Skill returns, generated code, protocol repair, truthful audit/process
payloads, user-language continuity, removed settings, untouched saved history,
and resumption without repeating completed tools. React tests verify Hebrew UI
for both Hebrew and English conversations, exact model reports and answers, and
byte-equivalent strings in input/output frames. The execution
ledger records actual suite/build/restart results. These checks do not measure
quality improvements in a live local or cloud model and do not constitute a new
installer or release acceptance.
