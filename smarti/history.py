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


CHAT_HISTORY_SCHEMA_VERSION = 2
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
                CREATE INDEX IF NOT EXISTS idx_sessions_updated
                    ON sessions(pinned DESC, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_messages_session_ordinal
                    ON messages(session_id, ordinal);
                """
            )
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
            "title_generated", "title_user_edited", "messages", "context",
        }
        return {
            "id": str(session.get("id") or uuid.uuid4().hex),
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
                id, title, created_at, updated_at, pinned, title_generated,
                title_user_edited, context_json, extra_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["id"], session["title"], session["created_at"], session["updated_at"],
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
        result = copy.deepcopy(extra)
        result.update({
            "role": str(row["role"]),
            "content": str(row["content"] or ""),
            "created_at": str(row["created_at"] or ""),
            "metadata": _json_loads(row["metadata_json"], {}),
        })
        return result

    def _session(self, db, session_id, include_messages=True):
        row = db.execute("SELECT * FROM sessions WHERE id=?", (str(session_id or ""),)).fetchone()
        if not row:
            return None
        result = _json_loads(row["extra_json"], {})
        result.update({
            "id": str(row["id"]),
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

    def _create_session_row(self, db, session_id=None):
        now = _now_iso()
        session = {
            "id": str(session_id or uuid.uuid4().hex),
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

    def create_session(self, set_active=True):
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
            session_id = self._create_session_row(db)
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

    def list_sessions(self, query=""):
        query = str(query or "").strip()
        with self._lock, self._connect() as db:
            rows = db.execute(
                """
                SELECT s.*, COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON m.session_id=s.id
                GROUP BY s.id
                HAVING COUNT(m.id) > 0
                ORDER BY s.pinned DESC, s.updated_at DESC
                """
            ).fetchall()
            if not query:
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
                        "preview": _preview_text(_message_text(last_message)) or "אין הודעות עדיין",
                        "preview_source": _message_text(last_message),
                        "title_score": 0.0,
                        "content_score": 0.0,
                        "match_kind": "content",
                    })
                return records
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
            return records

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

    def export_session(self, session_id, target_path):
        with self._lock, self._connect() as db:
            session = self._session(db, session_id)
            if not session:
                raise ValueError("Session not found.")
            payload = {
                "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
                "exported_at": _now_iso(),
                "session": session,
            }
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as destination:
            json.dump(payload, destination, ensure_ascii=False, indent=2)
        return target_path
