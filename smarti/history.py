"""Durable SQLite chat-session storage with lossless legacy JSON import."""
from .common import *

import sqlite3


class _ClosingConnection(sqlite3.Connection):
    """Commit/rollback like sqlite3's context manager, then release Windows locks."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


CHAT_HISTORY_SCHEMA_VERSION = 3
DEFAULT_CHAT_TITLE = "שיחה חדשה"
DEFAULT_WELCOME_MESSAGE = (
    "שלום, אני סמארטי - סוכן AI למחשב Windows. אני יכול לענות, לחפש מידע, "
    "לעבוד עם קבצים, דפדפן, תוכנות וכלים, ולנהל תהליכים רב-שלביים עד לתוצאה. "
    "מה נרצה לעשות?"
)


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _clean_title(value):
    title = re.sub(r"\s+", " ", str(value or "")).strip()
    title = re.sub(r'^[#"\':\-–—\s]+|[#"\':\-–—\s]+$', "", title).strip()
    return (title[:64].rstrip() or DEFAULT_CHAT_TITLE)


def _message_text(message):
    if not isinstance(message, dict):
        return ""
    metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
    if metadata.get("ui_only"):
        return ""
    text = str(message.get("content", "") or "")
    attachments = metadata.get("attachments", []) if isinstance(metadata.get("attachments"), list) else []
    if attachments:
        names = " ".join(str(item.get("name", "")) for item in attachments if isinstance(item, dict))
        text = f"{text} {names}".strip()
    return text


def _preview_text(value, limit=170):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[: max(0, limit - 3)].rstrip() + "..."
    return text


def _time_score(value):
    try:
        return datetime.fromisoformat(str(value or "")).timestamp()
    except Exception:
        return 0.0


def _normalize_search_text(value):
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\u0590-\u05ff]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _fuzzy_score(query, target):
    query = _normalize_search_text(query)
    target = _normalize_search_text(target)
    if not query or not target:
        return 0.0
    if query in target:
        return 1.0
    target_words = target.split()
    scores = []
    for word in query.split():
        if not word:
            continue
        if word in target:
            scores.append(0.94)
            continue
        candidates = [
            candidate
            for candidate in target_words
            if abs(len(candidate) - len(word)) <= max(3, len(word) // 2)
        ]
        if not candidates:
            candidates = target_words[:80]
        best = 0.0
        for candidate in candidates[:140]:
            best = max(best, difflib.SequenceMatcher(None, word, candidate).ratio())
        scores.append(best)
    return sum(scores) / max(1, len(scores))


def _json_object(value):
    if isinstance(value, dict):
        return copy.deepcopy(value)
    return {}


def _json_loads(value, fallback):
    try:
        loaded = json.loads(str(value or ""))
        if isinstance(loaded, type(fallback)):
            return loaded
    except Exception:
        pass
    return copy.deepcopy(fallback)


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ChatSessionStore:
    """SQLite-backed store preserving the original public session API.

    ``path`` remains the legacy JSON path for compatibility. The database lives
    beside it as ``*.sqlite3``; the JSON file is imported atomically and kept
    untouched as a recovery source.
    """

    def __init__(self, path=CHAT_HISTORY_FILE):
        self.legacy_path = os.path.abspath(path)
        root, extension = os.path.splitext(self.legacy_path)
        self.path = root + ".sqlite3" if extension.lower() == ".json" else self.legacy_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._initialize()
        self._migrate_legacy_json()
        self.ensure_active_session()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=15.0, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        return connection

    def _ensure_column(self, db, table, column, declaration):
        columns = {str(row["name"]) for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if str(column) not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _initialize(self):
        with self._lock, self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS store_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    title_generated INTEGER NOT NULL DEFAULT 0,
                    title_user_edited INTEGER NOT NULL DEFAULT 0,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    extra_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    extra_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(session_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    root_path TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    workspace_id TEXT REFERENCES workspaces(id) ON DELETE SET NULL,
                    source TEXT NOT NULL DEFAULT 'desktop',
                    status TEXT NOT NULL,
                    user_text TEXT NOT NULL DEFAULT '',
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    response_text TEXT NOT NULL DEFAULT '',
                    error_text TEXT NOT NULL DEFAULT '',
                    queued_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS attention_items (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL DEFAULT 'response',
                    created_at TEXT NOT NULL,
                    read_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(run_id, kind)
                );
                CREATE TABLE IF NOT EXISTS read_receipts (
                    actor_id TEXT NOT NULL,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    last_seen_event_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(actor_id, session_id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'pending',
                    title TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL DEFAULT '',
                    risk_level TEXT NOT NULL DEFAULT 'normal',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    payload_hash TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    resolved_at TEXT,
                    decision_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    scope TEXT NOT NULL,
                    key TEXT NOT NULL,
                    response_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    PRIMARY KEY(scope, key)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                    ON sessions(pinned DESC, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_session_ordinal
                    ON messages(session_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_runs_session_status
                    ON runs(session_id, status, queued_at);
                CREATE INDEX IF NOT EXISTS idx_runs_status_queued
                    ON runs(status, queued_at);
                CREATE INDEX IF NOT EXISTS idx_run_events_run_sequence
                    ON run_events(run_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_attention_unread
                    ON attention_items(read_at, session_id);
                CREATE INDEX IF NOT EXISTS idx_approvals_pending
                    ON approvals(status, session_id);
                """
            )
            self._ensure_column(db, "sessions", "workspace_id", "TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace_id, updated_at DESC)")
            db.execute(
                "INSERT OR REPLACE INTO store_meta(key, value) VALUES('schema_version', ?)",
                (str(CHAT_HISTORY_SCHEMA_VERSION),),
            )

    def _meta(self, db, key, default=""):
        row = db.execute("SELECT value FROM store_meta WHERE key=?", (str(key),)).fetchone()
        return str(row["value"]) if row else default

    def _set_meta(self, db, key, value):
        db.execute(
            "INSERT OR REPLACE INTO store_meta(key, value) VALUES(?, ?)",
            (str(key), str(value)),
        )

    def _ensure_session(self, db, session_id=None, set_active=False):
        target = str(session_id or "")
        if target and db.execute("SELECT 1 FROM sessions WHERE id=?", (target,)).fetchone():
            return target
        target = self._create_session_row(db, session_id=target or None)
        if set_active:
            self._set_meta(db, "active_session_id", target)
        return target

    def _normalize_message(self, message, fallback_time):
        if not isinstance(message, dict):
            return None
        role = str(message.get("role") or "").strip().lower()
        if role not in {"user", "assistant", "system"}:
            role = "assistant"
        metadata = _json_object(message.get("metadata"))
        if metadata.get("ui_only") or metadata.get("kind") == "welcome":
            return None
        known = {"role", "content", "created_at", "metadata"}
        return {
            "role": role,
            "content": str(message.get("content", "") or ""),
            "created_at": str(message.get("created_at") or fallback_time),
            "metadata": metadata,
            "extra": {key: copy.deepcopy(value) for key, value in message.items() if key not in known},
        }

    def _normalize_session(self, session):
        now = _now_iso()
        created = str(session.get("created_at") or now)
        updated = str(session.get("updated_at") or created)
        messages = []
        for message in session.get("messages", []) or []:
            normalized = self._normalize_message(message, updated)
            if normalized:
                messages.append(normalized)
        known = {
            "id", "title", "created_at", "updated_at", "pinned",
            "title_generated", "title_user_edited", "messages", "context", "workspace_id",
        }
        return {
            "id": str(session.get("id") or uuid.uuid4().hex),
            "workspace_id": str(session.get("workspace_id") or ""),
            "title": _clean_title(session.get("title") or DEFAULT_CHAT_TITLE),
            "created_at": created,
            "updated_at": updated,
            "pinned": bool(session.get("pinned", False)),
            "title_generated": bool(session.get("title_generated", False)),
            "title_user_edited": bool(session.get("title_user_edited", False)),
            "messages": messages,
            "context": _json_object(session.get("context")),
            "extra": {key: copy.deepcopy(value) for key, value in session.items() if key not in known},
        }

    def _insert_normalized_session(self, db, session, replace=False):
        command = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        db.execute(
            f"""
            {command} INTO sessions(
                id, workspace_id, title, created_at, updated_at, pinned, title_generated,
                title_user_edited, context_json, extra_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["id"], session.get("workspace_id") or None,
                session["title"], session["created_at"], session["updated_at"],
                int(session["pinned"]), int(session["title_generated"]),
                int(session["title_user_edited"]), _json_dumps(session["context"]),
                _json_dumps(session.get("extra", {})),
            ),
        )
        if db.execute("SELECT changes() AS count").fetchone()["count"]:
            for ordinal, message in enumerate(session.get("messages", [])):
                db.execute(
                    """
                    INSERT INTO messages(
                        session_id, ordinal, role, content, created_at,
                        metadata_json, extra_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session["id"], ordinal, message["role"], message["content"],
                        message["created_at"], _json_dumps(message["metadata"]),
                        _json_dumps(message.get("extra", {})),
                    ),
                )

    def _migrate_legacy_json(self):
        if not os.path.isfile(self.legacy_path):
            return
        with self._lock:
            try:
                stat = os.stat(self.legacy_path)
                fingerprint = f"{stat.st_size}:{stat.st_mtime_ns}"
                with self._connect() as db:
                    if self._meta(db, "legacy_json_import") == fingerprint:
                        return
                    with open(self.legacy_path, "r", encoding="utf-8") as source:
                        payload = json.load(source)
                    if not isinstance(payload, dict):
                        raise ValueError("Legacy chat history root is not an object.")
                    sessions = [
                        self._normalize_session(item)
                        for item in payload.get("sessions", [])
                        if isinstance(item, dict)
                    ]
                    db.execute("BEGIN IMMEDIATE")
                    for session in sessions:
                        self._insert_normalized_session(db, session)
                    active_id = str(payload.get("active_session_id") or "")
                    if active_id and db.execute(
                        "SELECT 1 FROM sessions WHERE id=?", (active_id,)
                    ).fetchone():
                        self._set_meta(db, "active_session_id", active_id)
                    root_extra = {
                        key: copy.deepcopy(value)
                        for key, value in payload.items()
                        if key not in {"schema_version", "active_session_id", "sessions"}
                    }
                    if root_extra:
                        self._set_meta(db, "legacy_root_extra_json", _json_dumps(root_extra))
                    self._set_meta(db, "legacy_json_import", fingerprint)
                    self._set_meta(db, "legacy_json_schema_version", payload.get("schema_version", ""))
                    db.commit()
            except Exception as error:
                logging.warning(f"Chat history JSON migration skipped safely: {error}")

    def _row_message(self, row):
        extra = _json_loads(row["extra_json"], {})
        metadata = _json_loads(row["metadata_json"], {})
        result = copy.deepcopy(extra)
        result.update({
            "role": str(row["role"]),
            "content": str(row["content"] or ""),
            "created_at": str(row["created_at"] or ""),
            "metadata": metadata,
        })
        if isinstance(metadata.get("attachments"), list):
            result["attachments"] = copy.deepcopy(metadata["attachments"])
        return result

    def _session(self, db, session_id, include_messages=True):
        row = db.execute("SELECT * FROM sessions WHERE id=?", (str(session_id or ""),)).fetchone()
        if not row:
            return None
        result = _json_loads(row["extra_json"], {})
        result.update({
            "id": str(row["id"]),
            "workspace_id": str(row["workspace_id"] or ""),
            "title": str(row["title"] or DEFAULT_CHAT_TITLE),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "pinned": bool(row["pinned"]),
            "title_generated": bool(row["title_generated"]),
            "title_user_edited": bool(row["title_user_edited"]),
            "context": _json_loads(row["context_json"], {}),
        })
        if include_messages:
            rows = db.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY ordinal",
                (result["id"],),
            ).fetchall()
            result["messages"] = [self._row_message(item) for item in rows]
        else:
            result["messages"] = []
        return result

    def _active_id(self, db):
        return self._meta(db, "active_session_id")

    def _latest_id(self, db):
        row = db.execute("SELECT id FROM sessions ORDER BY updated_at DESC LIMIT 1").fetchone()
        return str(row["id"]) if row else ""

    def _create_session_row(self, db, session_id=None, workspace_id=None):
        now = _now_iso()
        session = {
            "id": str(session_id or uuid.uuid4().hex),
            "workspace_id": str(workspace_id or ""),
            "title": DEFAULT_CHAT_TITLE,
            "created_at": now,
            "updated_at": now,
            "pinned": False,
            "title_generated": False,
            "title_user_edited": False,
            "messages": [],
            "context": {},
            "extra": {},
        }
        self._insert_normalized_session(db, session)
        return session["id"]

    @property
    def data(self):
        """Compatibility snapshot for older call sites; never used for writes."""
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT id FROM sessions ORDER BY updated_at DESC").fetchall()
            return {
                "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
                "active_session_id": self._active_id(db),
                "sessions": [self._session(db, row["id"]) for row in rows],
            }

    def has_session(self, session_id):
        with self._lock, self._connect() as db:
            return bool(db.execute("SELECT 1 FROM sessions WHERE id=?", (str(session_id or ""),)).fetchone())

    def ensure_active_session(self):
        with self._lock, self._connect() as db:
            session_id = self._active_id(db)
            session = self._session(db, session_id) if session_id else None
            if session:
                return session
            session_id = self._latest_id(db) or self._create_session_row(db)
            self._set_meta(db, "active_session_id", session_id)
            return self._session(db, session_id)

    def active_session(self):
        return self.ensure_active_session()

    def session_metadata(self, session_id=None):
        """Return session fields and message count without materializing message bodies."""
        with self._lock, self._connect() as db:
            target = str(session_id or self._active_id(db))
            session = self._session(db, target, include_messages=False)
            if not session:
                return None
            count = db.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE session_id=?",
                (target,),
            ).fetchone()["count"]
            session["message_count"] = int(count or 0)
            return session

    def active_session_metadata(self):
        metadata = self.session_metadata()
        if metadata:
            return metadata
        self.ensure_active_session()
        return self.session_metadata()

    def create_session(self, set_active=True, workspace_id=None):
        with self._lock, self._connect() as db:
            active_id = self._active_id(db)
            if set_active and active_id:
                count = db.execute(
                    "SELECT COUNT(*) AS count FROM messages WHERE session_id=?", (active_id,)
                ).fetchone()["count"]
                if not count:
                    now = _now_iso()
                    db.execute(
                        """
                        UPDATE sessions
                        SET title=?, updated_at=?, title_generated=0,
                            title_user_edited=0, context_json='{}'
                        WHERE id=?
                        """,
                        (DEFAULT_CHAT_TITLE, now, active_id),
                    )
                    return self._session(db, active_id)
            session_id = self._create_session_row(db, workspace_id=workspace_id)
            if set_active:
                self._set_meta(db, "active_session_id", session_id)
            return self._session(db, session_id)

    def set_active(self, session_id):
        with self._lock, self._connect() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (str(session_id or ""),)).fetchone():
                return False
            self._set_meta(db, "active_session_id", session_id)
            return True

    def messages(self, session_id=None):
        with self._lock, self._connect() as db:
            target = str(session_id or self._active_id(db))
            session = self._session(db, target)
            return session.get("messages", []) if session else []

    def append_message(self, role, content, metadata=None, session_id=None, created_at=None):
        """Append one durable message without requiring a complete user/assistant turn."""
        normalized_role = str(role or "assistant").strip().lower()
        if normalized_role not in {"user", "assistant", "system"}:
            normalized_role = "assistant"
        with self._lock, self._connect() as db:
            target = self._ensure_session(db, session_id, set_active=not bool(session_id))
            ordinal = int(db.execute(
                "SELECT COALESCE(MAX(ordinal), -1) + 1 AS next FROM messages WHERE session_id=?",
                (target,),
            ).fetchone()["next"])
            now = str(created_at or _now_iso())
            db.execute(
                """
                INSERT INTO messages(session_id, ordinal, role, content, created_at, metadata_json)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (target, ordinal, normalized_role, str(content or ""), now, _json_dumps(_json_object(metadata))),
            )
            db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, target))
            return ordinal

    def messages_page(self, session_id=None, before_ordinal=None, limit=32):
        """Read one chronological page, newest first when no cursor is supplied."""
        try:
            page_limit = max(1, min(500, int(limit or 32)))
        except (TypeError, ValueError):
            page_limit = 32
        with self._lock, self._connect() as db:
            target = str(session_id or self._active_id(db))
            if not target or not db.execute(
                "SELECT 1 FROM sessions WHERE id=?",
                (target,),
            ).fetchone():
                return {
                    "session_id": target,
                    "messages": [],
                    "total_count": 0,
                    "has_older": False,
                    "older_count": 0,
                    "next_before_ordinal": None,
                }
            params = [target]
            where = "session_id=?"
            if before_ordinal is not None:
                try:
                    cursor = int(before_ordinal)
                except (TypeError, ValueError):
                    cursor = None
                if cursor is not None:
                    where += " AND ordinal<?"
                    params.append(cursor)
            params.append(page_limit)
            # Capture attention before messages while holding the store lock. A
            # later completion must not be acknowledged by this page's receipt.
            unread_attention_ids = [str(row["id"]) for row in db.execute(
                "SELECT id FROM attention_items WHERE session_id=? AND read_at IS NULL",
                (target,),
            )] if before_ordinal is None else []
            rows = db.execute(
                f"SELECT * FROM messages WHERE {where} ORDER BY ordinal DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            rows = list(reversed(rows))
            messages = [self._row_message(row) for row in rows]
            next_cursor = int(rows[0]["ordinal"]) if rows else None
            older_count = 0
            if next_cursor is not None:
                older_count = int(db.execute(
                    "SELECT COUNT(*) AS count FROM messages WHERE session_id=? AND ordinal<?",
                    (target, next_cursor),
                ).fetchone()["count"] or 0)
            total_count = int(db.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE session_id=?",
                (target,),
            ).fetchone()["count"] or 0)
            return {
                "session_id": target,
                "messages": messages,
                "total_count": total_count,
                "has_older": older_count > 0,
                "older_count": older_count,
                "next_before_ordinal": next_cursor,
                "unread_attention_ids": unread_attention_ids,
            }

    def _summary_for_session(self, session, query=""):
        messages = session.get("messages", []) or []
        last_message = next((message for message in reversed(messages) if _message_text(message).strip()), {})
        preview = _preview_text(_message_text(last_message)) or "אין הודעות עדיין"
        title_score = _fuzzy_score(query, session.get("title", "")) if query else 0.0
        content_blob = "\n".join(_message_text(message) for message in messages)
        content_score = _fuzzy_score(query, content_blob) if query else 0.0
        return {
            "id": session.get("id", ""),
            "title": session.get("title", DEFAULT_CHAT_TITLE),
            "created_at": session.get("created_at", ""),
            "updated_at": session.get("updated_at", ""),
            "pinned": bool(session.get("pinned", False)),
            "message_count": len(messages),
            "preview": preview,
            "preview_source": _message_text(last_message),
            "title_score": title_score,
            "content_score": content_score,
            "match_kind": "title" if title_score >= max(0.55, content_score) else "content",
        }

    def _enrich_session_records(self, db, records):
        """Add orthogonal execution and attention state to sidebar records."""
        if not records:
            return records
        identifiers = [str(record.get("id") or "") for record in records]
        placeholders = ",".join("?" for _ in identifiers)
        active_states = {"queued", "running", "waiting_for_approval", "waiting_for_input", "cancelling"}
        rows = db.execute(
            f"""
            SELECT session_id, status, queued_at
            FROM runs
            WHERE session_id IN ({placeholders})
              AND status IN ('queued', 'running', 'waiting_for_approval', 'waiting_for_input', 'cancelling')
            ORDER BY queued_at
            """,
            identifiers,
        ).fetchall()
        priority = {"waiting_for_input": 5, "waiting_for_approval": 4, "cancelling": 3, "running": 2, "queued": 1}
        status_by_session = {}
        count_by_session = {}
        for row in rows:
            session_id = str(row["session_id"])
            status = str(row["status"])
            count_by_session[session_id] = count_by_session.get(session_id, 0) + 1
            current = status_by_session.get(session_id, "")
            if priority.get(status, 0) > priority.get(current, 0):
                status_by_session[session_id] = status
        unread_rows = db.execute(
            f"""
            SELECT session_id, COUNT(*) AS unread_count
            FROM attention_items
            WHERE read_at IS NULL AND session_id IN ({placeholders})
            GROUP BY session_id
            """,
            identifiers,
        ).fetchall()
        unread_by_session = {
            str(row["session_id"]): int(row["unread_count"] or 0)
            for row in unread_rows
        }
        for record in records:
            session_id = str(record.get("id") or "")
            status = status_by_session.get(session_id, "idle")
            record["runtime_status"] = status
            record["active_run_count"] = count_by_session.get(session_id, 0)
            record["unread_count"] = unread_by_session.get(session_id, 0)
            record["needs_input"] = status in {"waiting_for_approval", "waiting_for_input"}
            record["is_busy"] = status in active_states
        return records

    def list_sessions(self, query="", include_preview=True, include_empty=False):
        query = str(query or "").strip()
        with self._lock, self._connect() as db:
            visible_activity = """
                EXISTS(
                    SELECT 1 FROM messages m WHERE m.session_id=s.id
                ) OR EXISTS(
                    SELECT 1 FROM runs r
                    WHERE r.session_id=s.id
                      AND r.status IN ('queued', 'running', 'waiting_for_approval', 'waiting_for_input', 'cancelling')
                ) OR EXISTS(
                    SELECT 1 FROM attention_items a
                    WHERE a.session_id=s.id AND a.read_at IS NULL
                )
            """
            if include_empty is True:
                visibility = ""
            elif include_empty == "latest":
                visibility = f"""
                    WHERE ({visible_activity}) OR s.title_user_edited=1 OR s.id=(
                        SELECT newest.id FROM sessions newest
                        ORDER BY newest.updated_at DESC, newest.rowid DESC LIMIT 1
                    )
                """
            else:
                visibility = f"""
                WHERE EXISTS(
                    SELECT 1 FROM messages m WHERE m.session_id=s.id
                ) OR EXISTS(
                    SELECT 1 FROM runs r
                    WHERE r.session_id=s.id
                      AND r.status IN ('queued', 'running', 'waiting_for_approval', 'waiting_for_input', 'cancelling')
                ) OR EXISTS(
                    SELECT 1 FROM attention_items a
                    WHERE a.session_id=s.id AND a.read_at IS NULL
                )
                """
            rows = db.execute(
                f"""
                SELECT s.id, s.title, s.created_at, s.updated_at, s.pinned,
                       (
                           SELECT COUNT(*)
                           FROM messages counted
                           WHERE counted.session_id=s.id
                       ) AS message_count
                FROM sessions s
                {visibility}
                ORDER BY s.pinned DESC, s.updated_at DESC
                """
            ).fetchall()
            if not query:
                last_by_session = {}
                if include_preview:
                    last_rows = db.execute(
                        """
                        SELECT m.*
                        FROM messages m
                        JOIN (
                            SELECT session_id, MAX(ordinal) AS ordinal
                            FROM messages
                            GROUP BY session_id
                        ) latest
                          ON latest.session_id=m.session_id
                         AND latest.ordinal=m.ordinal
                        """
                    ).fetchall()
                    last_by_session = {
                        str(item["session_id"]): self._row_message(item)
                        for item in last_rows
                    }
                records = []
                for row in rows:
                    last_message = last_by_session.get(str(row["id"]), {})
                    records.append({
                        "id": str(row["id"]),
                        "title": str(row["title"] or DEFAULT_CHAT_TITLE),
                        "created_at": str(row["created_at"] or ""),
                        "updated_at": str(row["updated_at"] or ""),
                        "pinned": bool(row["pinned"]),
                        "message_count": int(row["message_count"] or 0),
                        "preview": (
                            _preview_text(_message_text(last_message)) or "אין הודעות עדיין"
                            if include_preview else ""
                        ),
                        "preview_source": _message_text(last_message) if include_preview else "",
                        "title_score": 0.0,
                        "content_score": 0.0,
                        "match_kind": "content",
                    })
                return self._enrich_session_records(db, records)

            # Most searches are literal substrings. Let SQLite narrow those in
            # one pass (including attachment names in metadata) instead of
            # loading every message of every session and running fuzzy matching
            # for each keystroke. Fuzzy matching remains the typo fallback.
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            exact_rows = db.execute(
                """
                SELECT s.id,
                       CASE WHEN s.title LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END AS title_match,
                       MAX(CASE WHEN m.content LIKE ? ESCAPE '\\'
                                     OR m.metadata_json LIKE ? ESCAPE '\\'
                                THEN 1 ELSE 0 END) AS content_match
                FROM sessions s
                LEFT JOIN messages m ON m.session_id=s.id
                GROUP BY s.id
                HAVING title_match=1 OR content_match=1
                """,
                (pattern, pattern, pattern),
            ).fetchall()
            if exact_rows:
                match_by_id = {str(item["id"]): item for item in exact_rows}
                matched_rows = [row for row in rows if str(row["id"]) in match_by_id]
                matched_ids = [str(row["id"]) for row in matched_rows]
                placeholders = ",".join("?" for _ in matched_ids)
                last_by_session = {}
                if include_preview:
                    last_rows = db.execute(
                        f"""
                        SELECT m.*
                        FROM messages m
                        JOIN (
                            SELECT session_id, MAX(ordinal) AS ordinal
                            FROM messages
                            WHERE session_id IN ({placeholders})
                            GROUP BY session_id
                        ) latest
                          ON latest.session_id=m.session_id
                         AND latest.ordinal=m.ordinal
                        """,
                        matched_ids,
                    ).fetchall()
                    last_by_session = {
                        str(item["session_id"]): self._row_message(item)
                        for item in last_rows
                    }
                records = []
                for row in matched_rows:
                    session_id = str(row["id"])
                    match = match_by_id[session_id]
                    last_message = last_by_session.get(session_id, {})
                    title_match = bool(match["title_match"])
                    records.append({
                        "id": session_id,
                        "title": str(row["title"] or DEFAULT_CHAT_TITLE),
                        "created_at": str(row["created_at"] or ""),
                        "updated_at": str(row["updated_at"] or ""),
                        "pinned": bool(row["pinned"]),
                        "message_count": int(row["message_count"] or 0),
                        "preview": (
                            _preview_text(_message_text(last_message)) or "אין הודעות עדיין"
                            if include_preview else ""
                        ),
                        "preview_source": _message_text(last_message) if include_preview else "",
                        "title_score": 1.0 if title_match else 0.0,
                        "content_score": 0.0 if title_match else 1.0,
                        "match_kind": "title" if title_match else "content",
                    })
                records.sort(
                    key=lambda record: (
                        0 if record["match_kind"] == "title" else 1,
                        not record["pinned"],
                        -_time_score(record.get("updated_at", "")),
                    )
                )
                return self._enrich_session_records(db, records)

            records = [self._summary_for_session(self._session(db, row["id"]), query=query) for row in rows]
            records = [
                record
                for record in records
                if max(record["title_score"], record["content_score"]) >= 0.48
            ]
            records.sort(
                key=lambda record: (
                    0 if record["match_kind"] == "title" else 1,
                    not record["pinned"],
                    -max(record["title_score"] * 1.4, record["content_score"]),
                    -_time_score(record.get("updated_at", "")),
                )
            )
            return self._enrich_session_records(db, records)

    def should_generate_title_for_next_turn(self, session_id=None):
        with self._lock, self._connect() as db:
            session_id = str(session_id or self._active_id(db))
            row = db.execute(
                "SELECT title_user_edited, title_generated FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if not row or row["title_user_edited"] or row["title_generated"]:
                return False
            count = db.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE session_id=? AND role='user'",
                (session_id,),
            ).fetchone()["count"]
            return int(count or 0) == 0

    def add_turn(
        self, user_text, assistant_text, assistant_raw=None, is_error=False,
        title="", context=None, user_metadata=None, assistant_metadata=None,
        welcome_text=None, session_id=None,
    ):
        with self._lock, self._connect() as db:
            target_id = str(session_id or self._active_id(db))
            if not target_id or not db.execute(
                "SELECT 1 FROM sessions WHERE id=?", (target_id,)
            ).fetchone():
                target_id = self._create_session_row(db, session_id=session_id)
                if not session_id:
                    self._set_meta(db, "active_session_id", target_id)
            ordinal = int(db.execute(
                "SELECT COALESCE(MAX(ordinal), -1) + 1 AS next FROM messages WHERE session_id=?",
                (target_id,),
            ).fetchone()["next"])
            now = _now_iso()
            user_meta = _json_object(user_metadata)
            if str(user_text or "").strip() or user_meta.get("attachments"):
                db.execute(
                    """
                    INSERT INTO messages(session_id, ordinal, role, content, created_at, metadata_json)
                    VALUES(?, ?, 'user', ?, ?, ?)
                    """,
                    (target_id, ordinal, str(user_text or ""), now, _json_dumps(user_meta)),
                )
                ordinal += 1
            if str(assistant_text or "").strip():
                assistant_meta = _json_object(assistant_metadata)
                assistant_meta["is_error"] = bool(is_error)
                if assistant_raw is not None and assistant_raw != assistant_text:
                    assistant_meta["raw"] = str(assistant_raw)
                db.execute(
                    """
                    INSERT INTO messages(session_id, ordinal, role, content, created_at, metadata_json)
                    VALUES(?, ?, 'assistant', ?, ?, ?)
                    """,
                    (target_id, ordinal, str(assistant_text or ""), now, _json_dumps(assistant_meta)),
                )
            updates = ["updated_at=?"]
            values = [now]
            if title:
                row = db.execute(
                    "SELECT title_user_edited FROM sessions WHERE id=?", (target_id,)
                ).fetchone()
                if row and not row["title_user_edited"]:
                    updates.extend(["title=?", "title_generated=1"])
                    values.append(_clean_title(title))
            if isinstance(context, dict):
                updates.append("context_json=?")
                values.append(_json_dumps(context))
            values.append(target_id)
            db.execute(f"UPDATE sessions SET {', '.join(updates)} WHERE id=?", values)
            return self._session(db, target_id)

    def update_context(self, context, session_id=None):
        if not isinstance(context, dict):
            return False
        with self._lock, self._connect() as db:
            target = str(session_id or self._active_id(db))
            result = db.execute(
                "UPDATE sessions SET context_json=? WHERE id=?",
                (_json_dumps(context), target),
            )
            return bool(result.rowcount)

    def update_canvas_layout(self, canvas_id, button_positions, session_id=None):
        canvas_id = str(canvas_id or "").strip()
        if not canvas_id or not isinstance(button_positions, list):
            return False
        with self._lock, self._connect() as db:
            target = str(session_id or self._active_id(db))
            rows = db.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY ordinal DESC",
                (target,),
            ).fetchall()
            for row in rows:
                metadata = _json_loads(row["metadata_json"], {})
                canvases = metadata.get("canvases") if isinstance(metadata, dict) else None
                if not isinstance(canvases, list):
                    continue
                for canvas in canvases:
                    if isinstance(canvas, dict) and str(canvas.get("id") or "") == canvas_id:
                        canvas["button_positions"] = copy.deepcopy(button_positions)
                        canvas["layout_updated_at"] = _now_iso()
                        now = _now_iso()
                        db.execute(
                            "UPDATE messages SET metadata_json=? WHERE id=?",
                            (_json_dumps(metadata), row["id"]),
                        )
                        db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, target))
                        return True
        return False

    def update_canvas_state(self, canvas_id, *, closed, session_id=None):
        """Persist open/closed Canvas state without depending on a UI renderer."""
        canvas_id = str(canvas_id or "").strip()
        if not canvas_id:
            return False
        with self._lock, self._connect() as db:
            target = str(session_id or self._active_id(db))
            rows = db.execute(
                "SELECT * FROM messages WHERE session_id=? ORDER BY ordinal DESC", (target,),
            ).fetchall()
            for row in rows:
                metadata = _json_loads(row["metadata_json"], {})
                canvases = metadata.get("canvases") if isinstance(metadata, dict) else None
                if not isinstance(canvases, list):
                    continue
                for canvas in canvases:
                    if isinstance(canvas, dict) and str(canvas.get("id") or "") == canvas_id:
                        canvas["closed"] = bool(closed)
                        canvas["state_updated_at"] = _now_iso()
                        db.execute(
                            "UPDATE messages SET metadata_json=? WHERE id=?",
                            (_json_dumps(metadata), row["id"]),
                        )
                        db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now_iso(), target))
                        return True
        return False

    def apply_generated_title(self, session_id, title):
        cleaned = _clean_title(title)
        if not cleaned or cleaned == DEFAULT_CHAT_TITLE:
            return False
        with self._lock, self._connect() as db:
            result = db.execute(
                """
                UPDATE sessions
                SET title=?, title_generated=1, updated_at=?
                WHERE id=? AND title_user_edited=0 AND title_generated=0
                """,
                (cleaned, _now_iso(), str(session_id or "")),
            )
            return bool(result.rowcount)

    def apply_provisional_title(self, session_id, title):
        """Show a collision-free first-turn title while an AI title is generated."""
        cleaned = _clean_title(title)
        if not cleaned or cleaned == DEFAULT_CHAT_TITLE:
            return ""
        target = str(session_id or "")
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT title_user_edited, title_generated FROM sessions WHERE id=?",
                (target,),
            ).fetchone()
            if not row or row["title_user_edited"] or row["title_generated"]:
                return ""
            existing = {
                str(item["title"] or "").strip().casefold()
                for item in db.execute(
                    "SELECT title FROM sessions WHERE id<>?",
                    (target,),
                ).fetchall()
            }
            candidate = cleaned
            suffix_index = 2
            while candidate.casefold() in existing:
                suffix = f" ({suffix_index})"
                candidate = cleaned[: max(1, 64 - len(suffix))].rstrip() + suffix
                suffix_index += 1
            result = db.execute(
                """
                UPDATE sessions
                SET title=?, updated_at=?
                WHERE id=? AND title_user_edited=0 AND title_generated=0
                """,
                (candidate, _now_iso(), target),
            )
            return candidate if result.rowcount else ""

    def apply_initial_title(self, session_id, title):
        """Assign an immediate, collision-free title from the first user turn."""
        cleaned = _clean_title(title)
        if not cleaned or cleaned == DEFAULT_CHAT_TITLE:
            return ""
        target = str(session_id or "")
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT title_user_edited, title_generated FROM sessions WHERE id=?",
                (target,),
            ).fetchone()
            if not row or row["title_user_edited"] or row["title_generated"]:
                return ""
            existing = {
                str(item["title"] or "").strip().casefold()
                for item in db.execute(
                    "SELECT title FROM sessions WHERE id<>?",
                    (target,),
                ).fetchall()
            }
            candidate = cleaned
            suffix_index = 2
            while candidate.casefold() in existing:
                suffix = f" ({suffix_index})"
                candidate = (cleaned[: max(1, 64 - len(suffix))].rstrip() + suffix)
                suffix_index += 1
            result = db.execute(
                """
                UPDATE sessions
                SET title=?, title_generated=1, updated_at=?
                WHERE id=? AND title_user_edited=0 AND title_generated=0
                """,
                (candidate, _now_iso(), target),
            )
            return candidate if result.rowcount else ""

    def rename_session(self, session_id, title):
        cleaned = _clean_title(title)
        with self._lock, self._connect() as db:
            result = db.execute(
                """
                UPDATE sessions
                SET title=?, title_user_edited=1, title_generated=?
                WHERE id=?
                """,
                (
                    cleaned,
                    int(bool(cleaned and cleaned != DEFAULT_CHAT_TITLE)),
                    str(session_id or ""),
                ),
            )
            return bool(result.rowcount)

    def set_pinned(self, session_id, pinned):
        with self._lock, self._connect() as db:
            result = db.execute(
                "UPDATE sessions SET pinned=? WHERE id=?",
                (int(bool(pinned)), str(session_id or "")),
            )
            return bool(result.rowcount)

    def delete_session(self, session_id):
        with self._lock, self._connect() as db:
            session_id = str(session_id or "")
            result = db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            if not result.rowcount:
                return False
            if self._active_id(db) == session_id:
                replacement = self._latest_id(db) or self._create_session_row(db)
                self._set_meta(db, "active_session_id", replacement)
            return True

    # ------------------------------------------------------------------
    # Durable execution ledger

    def create_workspace(self, title="", root_path="", metadata=None, workspace_id=None):
        now = _now_iso()
        identifier = str(workspace_id or uuid.uuid4().hex)
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO workspaces(id, title, root_path, created_at, updated_at, metadata_json)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    str(title or DEFAULT_CHAT_TITLE),
                    str(root_path or ""),
                    now,
                    now,
                    _json_dumps(_json_object(metadata)),
                ),
            )
        return identifier

    def list_workspaces(self):
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM workspaces ORDER BY updated_at DESC").fetchall()
            return [
                {
                    "id": str(row["id"]),
                    "title": str(row["title"] or ""),
                    "root_path": str(row["root_path"] or ""),
                    "created_at": str(row["created_at"] or ""),
                    "updated_at": str(row["updated_at"] or ""),
                    "metadata": _json_loads(row["metadata_json"], {}),
                }
                for row in rows
            ]

    def workspace(self, workspace_id):
        target = str(workspace_id or "")
        return next(
            (item for item in self.list_workspaces() if item["id"] == target),
            None,
        )

    def update_workspace(self, workspace_id, *, title=None, root_path=None, metadata=None):
        target = str(workspace_id or "")
        updates = []
        values = []
        if title is not None:
            updates.append("title=?")
            values.append(str(title or DEFAULT_CHAT_TITLE))
        if root_path is not None:
            updates.append("root_path=?")
            values.append(str(root_path or ""))
        if metadata is not None:
            updates.append("metadata_json=?")
            values.append(_json_dumps(_json_object(metadata)))
        if not updates:
            return self.workspace(target)
        updates.append("updated_at=?")
        values.append(_now_iso())
        values.append(target)
        with self._lock, self._connect() as db:
            result = db.execute(
                f"UPDATE workspaces SET {', '.join(updates)} WHERE id=?",
                tuple(values),
            )
            if not result.rowcount:
                return None
        return self.workspace(target)

    def delete_workspace(self, workspace_id):
        target = str(workspace_id or "")
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE sessions SET workspace_id=NULL, updated_at=? WHERE workspace_id=?",
                (_now_iso(), target),
            )
            result = db.execute("DELETE FROM workspaces WHERE id=?", (target,))
            return bool(result.rowcount)

    def assign_session_workspace(self, session_id, workspace_id=None):
        with self._lock, self._connect() as db:
            workspace_value = str(workspace_id or "")
            if workspace_value and not db.execute(
                "SELECT 1 FROM workspaces WHERE id=?", (workspace_value,)
            ).fetchone():
                return False
            result = db.execute(
                "UPDATE sessions SET workspace_id=?, updated_at=? WHERE id=?",
                (workspace_value or None, _now_iso(), str(session_id or "")),
            )
            return bool(result.rowcount)

    def create_run(
        self, session_id, user_text="", attachments=None, source="desktop",
        metadata=None, workspace_id=None, run_id=None,
    ):
        identifier = str(run_id or uuid.uuid4().hex)
        now = _now_iso()
        with self._lock, self._connect() as db:
            target = self._ensure_session(db, session_id, set_active=not bool(session_id))
            resolved_workspace_id = str(workspace_id or "")
            if not resolved_workspace_id:
                session_row = db.execute(
                    "SELECT workspace_id FROM sessions WHERE id=?",
                    (target,),
                ).fetchone()
                resolved_workspace_id = str(session_row["workspace_id"] or "") if session_row else ""
            db.execute(
                """
                INSERT INTO runs(
                    id, session_id, workspace_id, source, status, user_text,
                    attachments_json, queued_at, updated_at, metadata_json
                ) VALUES(?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    target,
                    resolved_workspace_id or None,
                    str(source or "desktop"),
                    str(user_text or ""),
                    _json_dumps(list(attachments or [])),
                    now,
                    now,
                    _json_dumps(_json_object(metadata)),
                ),
            )
            db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, target))
            self._append_run_event_locked(db, identifier, "run_queued", {"source": str(source or "desktop")}, now)
        return identifier

    def _append_run_event_locked(self, db, run_id, event_type, payload=None, created_at=None):
        sequence = int(db.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS next FROM run_events WHERE run_id=?",
            (str(run_id or ""),),
        ).fetchone()["next"])
        now = str(created_at or _now_iso())
        cursor = db.execute(
            """
            INSERT INTO run_events(run_id, sequence, event_type, payload_json, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (str(run_id or ""), sequence, str(event_type or "event"), _json_dumps(_json_object(payload)), now),
        )
        return int(cursor.lastrowid), sequence

    def append_run_event(self, run_id, event_type, payload=None):
        with self._lock, self._connect() as db:
            if not db.execute("SELECT 1 FROM runs WHERE id=?", (str(run_id or ""),)).fetchone():
                return None
            event_id, sequence = self._append_run_event_locked(db, run_id, event_type, payload)
            return {"id": event_id, "sequence": sequence}

    def transition_run(
        self, run_id, status, response_text=None, error_text=None,
        metadata_patch=None, expected_statuses=None,
    ):
        status = str(status or "").strip().lower()
        allowed = {
            "queued", "running", "waiting_for_approval", "waiting_for_input", "cancelling",
            "completed", "failed", "cancelled", "interrupted",
        }
        if status not in allowed:
            raise ValueError(f"Unsupported run status: {status}")
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (str(run_id or ""),)).fetchone()
            if not row:
                return False
            current = str(row["status"] or "")
            if expected_statuses and current not in {str(item) for item in expected_statuses}:
                return False
            now = _now_iso()
            updates = ["status=?", "updated_at=?"]
            values = [status, now]
            if status == "running" and not row["started_at"]:
                updates.append("started_at=?")
                values.append(now)
            if status in {"completed", "failed", "cancelled", "interrupted"}:
                updates.append("finished_at=?")
                values.append(now)
            if response_text is not None:
                updates.append("response_text=?")
                values.append(str(response_text or ""))
            if error_text is not None:
                updates.append("error_text=?")
                values.append(str(error_text or ""))
            if isinstance(metadata_patch, dict):
                metadata = _json_loads(row["metadata_json"], {})
                metadata.update(copy.deepcopy(metadata_patch))
                updates.append("metadata_json=?")
                values.append(_json_dumps(metadata))
            values.append(str(run_id or ""))
            db.execute(f"UPDATE runs SET {', '.join(updates)} WHERE id=?", tuple(values))
            self._append_run_event_locked(
                db,
                run_id,
                f"run_{status}",
                {"previous_status": current},
                now,
            )
            return True

    def request_run_cancel(self, run_id):
        with self._lock, self._connect() as db:
            row = db.execute("SELECT status FROM runs WHERE id=?", (str(run_id or ""),)).fetchone()
            if not row or str(row["status"]) in {"completed", "failed", "cancelled", "interrupted"}:
                return False
            now = _now_iso()
            status = "cancelled" if str(row["status"]) == "queued" else "cancelling"
            finished = now if status == "cancelled" else None
            db.execute(
                "UPDATE runs SET cancel_requested=1, status=?, updated_at=?, finished_at=COALESCE(?, finished_at) WHERE id=?",
                (status, now, finished, str(run_id or "")),
            )
            self._append_run_event_locked(db, run_id, "cancel_requested", {"status": status}, now)
            return True

    def _run_record(self, row):
        if not row:
            return None
        return {
            "id": str(row["id"]),
            "session_id": str(row["session_id"]),
            "workspace_id": str(row["workspace_id"] or ""),
            "source": str(row["source"] or "desktop"),
            "status": str(row["status"] or ""),
            "user_text": str(row["user_text"] or ""),
            "attachments": _json_loads(row["attachments_json"], []),
            "response_text": str(row["response_text"] or ""),
            "error_text": str(row["error_text"] or ""),
            "queued_at": str(row["queued_at"] or ""),
            "started_at": str(row["started_at"] or ""),
            "finished_at": str(row["finished_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "cancel_requested": bool(row["cancel_requested"]),
            "metadata": _json_loads(row["metadata_json"], {}),
        }

    def run(self, run_id):
        with self._lock, self._connect() as db:
            return self._run_record(db.execute("SELECT * FROM runs WHERE id=?", (str(run_id or ""),)).fetchone())

    def list_runs(self, session_id=None, statuses=None, limit=100):
        clauses = []
        values = []
        if session_id:
            clauses.append("session_id=?")
            values.append(str(session_id))
        if statuses:
            normalized = [str(item) for item in statuses]
            clauses.append(f"status IN ({','.join('?' for _ in normalized)})")
            values.extend(normalized)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        values.append(max(1, min(1000, int(limit or 100))))
        with self._lock, self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM runs {where} ORDER BY queued_at DESC LIMIT ?",
                tuple(values),
            ).fetchall()
            return [self._run_record(row) for row in rows]

    def run_events(self, run_id, after_sequence=0, limit=500):
        with self._lock, self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM run_events
                WHERE run_id=? AND sequence>?
                ORDER BY sequence LIMIT ?
                """,
                (str(run_id or ""), int(after_sequence or 0), max(1, min(2000, int(limit or 500)))),
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "run_id": str(row["run_id"]),
                    "sequence": int(row["sequence"]),
                    "event_type": str(row["event_type"]),
                    "payload": _json_loads(row["payload_json"], {}),
                    "created_at": str(row["created_at"] or ""),
                }
                for row in rows
            ]

    def events_after(self, after_event_id=0, session_id=None, limit=500):
        """Return the durable cross-run stream used by reconnecting desktop clients."""
        clauses = ["e.id>?"]
        values = [max(0, int(after_event_id or 0))]
        if session_id:
            clauses.append("r.session_id=?")
            values.append(str(session_id))
        values.append(max(1, min(2000, int(limit or 500))))
        with self._lock, self._connect() as db:
            rows = db.execute(
                f"""
                SELECT e.*, r.session_id, r.metadata_json AS run_metadata_json
                FROM run_events e
                JOIN runs r ON r.id=e.run_id
                WHERE {' AND '.join(clauses)}
                ORDER BY e.id
                LIMIT ?
                """,
                tuple(values),
            ).fetchall()
            return [
                {
                    "event_id": int(row["id"]),
                    "run_id": str(row["run_id"]),
                    "session_id": str(row["session_id"]),
                    "sequence": int(row["sequence"]),
                    "event_type": str(row["event_type"]),
                    "request_id": str(
                        _json_loads(row["run_metadata_json"], {}).get("request_id") or ""
                    ),
                    "payload": _json_loads(row["payload_json"], {}),
                    "created_at": str(row["created_at"] or ""),
                }
                for row in rows
            ]

    def recover_incomplete_runs(self):
        """Make crash state explicit and return queued work that is safe to resume."""
        with self._lock, self._connect() as db:
            now = _now_iso()
            stale = db.execute(
                "SELECT id FROM runs WHERE status IN ('running', 'waiting_for_approval', 'waiting_for_input', 'cancelling')"
            ).fetchall()
            for row in stale:
                run_id = str(row["id"])
                db.execute(
                    "UPDATE runs SET status='interrupted', finished_at=?, updated_at=?, error_text=? WHERE id=?",
                    (now, now, "Smarti stopped before this run completed.", run_id),
                )
                self._append_run_event_locked(db, run_id, "run_interrupted", {"reason": "runtime_restart"}, now)
                db.execute(
                    """
                    UPDATE approvals
                    SET status='cancelled', resolved_at=?, decision_json=?
                    WHERE run_id=? AND status='pending'
                    """,
                    (now, _json_dumps({"reason": "runtime_restart"}), run_id),
                )
                session_row = db.execute("SELECT session_id FROM runs WHERE id=?", (run_id,)).fetchone()
                if session_row:
                    db.execute(
                        """
                        INSERT OR IGNORE INTO attention_items(
                            id, session_id, run_id, kind, created_at, metadata_json
                        ) VALUES(?, ?, ?, 'interrupted', ?, ?)
                        """,
                        (
                            uuid.uuid4().hex,
                            str(session_row["session_id"]),
                            run_id,
                            now,
                            _json_dumps({"reason": "runtime_restart"}),
                        ),
                    )
            queued = db.execute("SELECT * FROM runs WHERE status='queued' ORDER BY queued_at").fetchall()
            return [self._run_record(row) for row in queued]

    # ------------------------------------------------------------------
    # Attention, read receipts, and approvals

    def create_attention(self, session_id, run_id=None, kind="response", metadata=None):
        now = _now_iso()
        identifier = uuid.uuid4().hex
        with self._lock, self._connect() as db:
            target = self._ensure_session(db, session_id)
            try:
                db.execute(
                    """
                    INSERT INTO attention_items(id, session_id, run_id, kind, created_at, metadata_json)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        identifier,
                        target,
                        str(run_id) if run_id else None,
                        str(kind or "response"),
                        now,
                        _json_dumps(_json_object(metadata)),
                    ),
                )
            except sqlite3.IntegrityError:
                row = db.execute(
                    "SELECT id FROM attention_items WHERE run_id=? AND kind=?",
                    (str(run_id or ""), str(kind or "response")),
                ).fetchone()
                return str(row["id"]) if row else ""
        return identifier

    def unread_attention_items(self):
        """Global attention snapshot, independent of sidebar search and paging."""
        with self._lock, self._connect() as db:
            return [dict(row) for row in db.execute(
                """
                SELECT a.id, a.session_id, a.run_id, a.kind, s.title
                FROM attention_items a JOIN sessions s ON s.id=a.session_id
                WHERE a.read_at IS NULL ORDER BY a.rowid
                """
            )]

    def mark_session_read(self, session_id, actor_id="desktop", attention_ids=None):
        now = _now_iso()
        with self._lock, self._connect() as db:
            target = str(session_id or "")
            if not db.execute("SELECT 1 FROM sessions WHERE id=?", (target,)).fetchone():
                return 0
            clause = ""
            identifiers = [] if attention_ids is None else list(dict.fromkeys(attention_ids))
            if attention_ids is not None:
                if not identifiers:
                    return 0
                clause = f" AND id IN ({','.join('?' for _ in identifiers)})"
            result = db.execute(
                "UPDATE attention_items SET read_at=? WHERE session_id=? AND read_at IS NULL" + clause,
                (now, target, *identifiers),
            )
            last_event = db.execute(
                """
                SELECT COALESCE(MAX(e.id), 0) AS event_id
                FROM run_events e JOIN runs r ON r.id=e.run_id
                WHERE r.session_id=?
                """,
                (target,),
            ).fetchone()["event_id"]
            db.execute(
                """
                INSERT INTO read_receipts(actor_id, session_id, last_seen_event_id, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(actor_id, session_id) DO UPDATE SET
                    last_seen_event_id=excluded.last_seen_event_id,
                    updated_at=excluded.updated_at
                """,
                (str(actor_id or "desktop"), target, int(last_event or 0), now),
            )
            return int(result.rowcount or 0)

    def unread_count(self, session_id=None):
        with self._lock, self._connect() as db:
            if session_id:
                row = db.execute(
                    "SELECT COUNT(*) AS count FROM attention_items WHERE read_at IS NULL AND session_id=?",
                    (str(session_id),),
                ).fetchone()
            else:
                row = db.execute("SELECT COUNT(*) AS count FROM attention_items WHERE read_at IS NULL").fetchone()
            return int(row["count"] or 0)

    def create_approval(
        self, run_id, session_id, title="", prompt="", risk_level="normal",
        payload=None, payload_hash="", expires_at=None, approval_id=None,
    ):
        identifier = str(approval_id or uuid.uuid4().hex)
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO approvals(
                    id, run_id, session_id, status, title, prompt, risk_level,
                    payload_json, payload_hash, created_at, expires_at
                ) VALUES(?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier, str(run_id), str(session_id), str(title or ""),
                    str(prompt or ""), str(risk_level or "normal"),
                    _json_dumps(_json_object(payload)), str(payload_hash or ""),
                    _now_iso(), str(expires_at) if expires_at else None,
                ),
            )
        return identifier

    def resolve_approval(self, approval_id, decision, decision_metadata=None):
        normalized = str(decision or "").strip().lower()
        if normalized not in {"approved", "denied", "cancelled", "expired"}:
            raise ValueError("Unsupported approval decision")
        with self._lock, self._connect() as db:
            result = db.execute(
                """
                UPDATE approvals
                SET status=?, resolved_at=?, decision_json=?
                WHERE id=? AND status='pending'
                """,
                (
                    normalized, _now_iso(), _json_dumps(_json_object(decision_metadata)),
                    str(approval_id or ""),
                ),
            )
            return bool(result.rowcount)

    def pending_approvals(self, session_id=None):
        values = []
        where = "status='pending'"
        if session_id:
            where += " AND session_id=?"
            values.append(str(session_id))
        with self._lock, self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM approvals WHERE {where} ORDER BY created_at",
                tuple(values),
            ).fetchall()
            return [
                {
                    "id": str(row["id"]),
                    "run_id": str(row["run_id"]),
                    "session_id": str(row["session_id"]),
                    "status": str(row["status"]),
                    "title": str(row["title"] or ""),
                    "prompt": str(row["prompt"] or ""),
                    "risk_level": str(row["risk_level"] or "normal"),
                    "payload": _json_loads(row["payload_json"], {}),
                    "payload_hash": str(row["payload_hash"] or ""),
                    "created_at": str(row["created_at"] or ""),
                    "expires_at": str(row["expires_at"] or ""),
                }
                for row in rows
            ]

    def idempotency_response(self, scope, key):
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT response_json, expires_at FROM idempotency_keys WHERE scope=? AND key=?",
                (str(scope or "default"), str(key or "")),
            ).fetchone()
            if not row:
                return None
            expires_at = str(row["expires_at"] or "")
            if expires_at:
                try:
                    if datetime.fromisoformat(expires_at) <= datetime.now():
                        db.execute(
                            "DELETE FROM idempotency_keys WHERE scope=? AND key=?",
                            (str(scope or "default"), str(key or "")),
                        )
                        return None
                except Exception:
                    pass
            return _json_loads(row["response_json"], {})

    def save_idempotency_response(self, scope, key, response, ttl_hours=24):
        if not str(key or "").strip():
            return False
        now = datetime.now()
        expires_at = (now + timedelta(hours=max(1, int(ttl_hours or 24)))).isoformat(timespec="seconds")
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO idempotency_keys(scope, key, response_json, created_at, expires_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    str(scope or "default"), str(key), _json_dumps(_json_object(response)),
                    now.isoformat(timespec="seconds"), expires_at,
                ),
            )
            return True

    def export_session(self, session_id, target_path):
        payload = self.session_export_payload(session_id)
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as destination:
            json.dump(payload, destination, ensure_ascii=False, indent=2)
        return target_path

    def session_export_payload(self, session_id):
        """Return the same Core-owned JSON payload used by the legacy save flow."""
        with self._lock, self._connect() as db:
            session = self._session(db, session_id)
            if not session:
                raise ValueError("Session not found.")
            return {
                "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
                "exported_at": _now_iso(),
                "session": session,
            }
