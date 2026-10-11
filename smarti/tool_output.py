"""Core-owned encrypted tool output, scoped to the originating conversation."""
import re
import uuid

from . import common


class ToolOutputWriter:
    def __init__(self, store, session_id, settings):
        self.store = store
        self.session_id = session_id
        self.settings = settings
        self.output_id = uuid.uuid4().hex
        self.offset = 0
        self.ordinal = 0

    def write(self, text):
        for start in range(0, len(text), 65536):
            chunk = text[start:start + 65536]
            encrypted = common.dpapi_protect_text(chunk)
            if not encrypted or not encrypted.startswith(common.SECRET_PREFIX):
                raise OSError("Cannot encrypt retained tool output")
            with self.store._lock, self.store._connect() as db:
                db.execute("INSERT INTO tool_output_chunks VALUES (?, ?, ?, ?, ?, ?)",
                           (self.output_id, self.session_id, self.ordinal, self.offset, len(chunk), encrypted.encode("ascii")))
            self.offset += len(chunk)
            self.ordinal += 1

    def preview(self, limit):
        page = read_tool_output(self.store, self.session_id, self.output_id, 0, limit, self.settings)
        return page.split("\n", 1)[1]

    def full_text(self):
        # Internal parsers require the original JSON/protocol, not a model
        # preview. This path is never exposed through the retrieval tool.
        with self.store._lock, self.store._connect() as db:
            rows = db.execute("SELECT encrypted_text FROM tool_output_chunks WHERE output_id=? AND session_id=? ORDER BY ordinal",
                              (self.output_id, self.session_id)).fetchall()
        return "".join(_decrypt(row[0]) for row in rows)


def _decrypt(value):
    # Ciphertext is binary so credential redaction cannot accidentally edit a
    # base64 sequence that happens to match a short configured password.
    return common.dpapi_unprotect_text(value.decode("ascii") if isinstance(value, bytes) else value)


def read_tool_output(store, session_id, output_id, offset, limit, settings):
    if not re.fullmatch(r"[a-f0-9]{32}", output_id):
        return "ERROR: Invalid output_id."
    if offset < 0 or limit <= 0:
        return "ERROR: offset must be nonnegative and limit must be positive."
    # Include neighboring characters so a page boundary cannot reveal a
    # credential fragment that would be redacted in the complete output.
    common.redact_secret_values("", settings)
    with common._REDACTION_SECRETS_LOCK:
        secrets = tuple(common._KNOWN_REDACTION_SECRETS)
    padding = max((len(secret) for secret in secrets), default=4096) + 4096
    with store._lock, store._connect() as db:
        total = db.execute("SELECT MAX(start_char + char_count) FROM tool_output_chunks WHERE output_id=? AND session_id=?",
                           (output_id, session_id)).fetchone()[0]
        if total is None:
            return "ERROR: Retained output not found in this conversation."
        rows = db.execute("""SELECT start_char, encrypted_text FROM tool_output_chunks
            WHERE output_id=? AND session_id=? AND start_char < ? AND start_char + char_count > ? ORDER BY ordinal""",
                          (output_id, session_id, offset + limit + padding, max(0, offset - padding))).fetchall()
    text = "".join(_decrypt(row["encrypted_text"]) for row in rows)
    base = rows[0]["start_char"] if rows else total
    start, end = max(0, offset - base), min(len(text), max(0, offset - base) + limit)
    spans = [match.span() for secret in secrets for match in re.finditer(re.escape(secret), text)]
    spans += [match.span() for match in re.finditer(r"(?i)\b(?:Bearer|Basic)\s+[a-z0-9._~+/-]{12,}=*", text)]
    for left, right in sorted(spans):
        if left < start < right:
            start = right
        if left < end < right:
            end = right
    end = max(start, end)
    body = common.redact_secret_values(text[start:end], settings)
    next_offset = min(total, base + end)
    return (f"output_id={output_id} offset={offset} total_chars={total} "
            f"next_offset={next_offset if next_offset < total else 'end'}\n{body}")
