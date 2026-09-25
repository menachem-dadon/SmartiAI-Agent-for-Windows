# Attachment pipeline

Updated 2026-09-10.

Direct attachments and `file_manager action=attach` use the same provider content
builder. The tool accepts either `path` or `paths`, including mixed file types.
It performs policy checks and returns an internal attachment envelope; the agent
loop consumes that envelope, appends real content blocks to its next model
request, and continues the original task. The tool does not invoke a separate
model to describe a file. Old single-file envelopes remain readable.

Mixed tool-result batches preserve images and document contents alongside ordinary
tool text. Each attachment is labelled by filename. File contents remain untrusted
data. The inventory distinguishes local availability from content supplied to the
model and tells the agent to analyze already supplied images directly.

## Content supplied to the model

| Input | Content path |
| --- | --- |
| PNG/JPEG/WebP/GIF images | Native image blocks for Gemini, Anthropic, OpenAI, and compatible vision adapters; ephemeral `--image` inputs for Codex sign-in. Actual model vision support is still required. |
| Other decodable image formats | Pillow conversion to PNG; unsupported codecs report an error. Multiple-frame conversions explicitly disclose that only the first frame is included. |
| PDF | Native PDF for Gemini, Anthropic, and OpenAI; text extraction for other adapters. Extracted text explicitly excludes page graphics and scanned text. |
| Audio/video | Native Gemini media inputs. Other current adapters report that this content was not included. |
| Text, code, CSV, JSON | Bounded text, including UTF-8/BOM and UTF-16. Truncation is explicit. |
| DOCX/DOCM, XLSX/XLSM, PPTX/PPTM, ODT/ODS/ODP | Local XML extraction of text, spreadsheet cell values/formulas, and slide text. Embedded media and layout are explicitly excluded. No Office automation or macro execution. |
| ZIP | Bounded member inventory, explicitly distinguished from member contents. |
| Other binary/legacy formats | Per-file unsupported-content warning. A local path alone is not reported as analyzed content. |

The default per-file inline/processing limit is 25 MiB, matching desktop staging.
Existing explicit settings are preserved. Text extraction defaults to 10,000
characters with a truncation marker; document XML expansion is bounded to 16 MiB.
Provider/model limits on combined payload size and modalities still apply.
Missing, denied, oversized, or unextractable files do not discard valid peers.

The desktop waits for in-flight file staging before sending, merges concurrently
completed picker/paste/drop batches, blocks duplicate submits, and preserves files
added during a submit. Failed refreshes after accepted runs do not restore the
already sent draft.

The main Tauri window sets `dragDropEnabled: false` so Windows file drops reach
the composer's HTML5 `onDrop` handler and use the same staging path as picker and
paste. Tauri's default native drop handler intercepts those events before React
can receive them. This window configuration takes effect after rebuilding and
restarting the desktop host; a frontend hot reload alone is insufficient.

## Incident and verification

The 2026-09-10 00:28 run asked “מה בתמונה?” with a 2,264-byte PNG using Gemini.
Persisted run events showed `file_manager / extract_image_text` without a result,
followed by repeated cancellation requests. A read-only process stack inspection
identified the agent worker blocked loading NumPy through `pytesseract`.

The OCR tool has been removed from implementation, schemas, routing, UI descriptions,
and packaging imports. Calls retained in older conversations are rejected with guidance
to use `file_manager action=attach`. The main model reads Hebrew text directly from
the supplied image, without an OCR engine or a separate AI analysis task.

`tests/test_attachments.py` verifies both attachment entrances, mixed result batches,
provider request payloads, Codex image inputs and temporary-file cleanup, partial
failures, document extraction, rejection of retired OCR calls, direct image answers
without tool execution, and continuation
through the real `send_message` loop with a mocked model transport.
`desktop/src/composerAttachments.test.tsx` covers asynchronous staging and submit races.
These are local tests; they do not establish a successful paid provider request or
an installed release build.

Provider format references: [OpenAI file inputs](https://developers.openai.com/api/docs/guides/file-inputs),
[Codex image flags](https://learn.chatgpt.com/docs/developer-commands?surface=cli),
and [Gemini file input](https://ai.google.dev/gemini-api/docs/file-input-methods).
