"""Transactional storage and local full-text indexing for Smarti Memory V2."""

import copy
import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_object(value, default=None):
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else copy.deepcopy(default or {})
        except Exception:
            pass
    return copy.deepcopy(default or {})


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        result = super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return result


class MemorySQLiteStore:
    """SQLite primary store with JSON-compatible encrypted snapshots."""

    SCHEMA_VERSION = 3

    def __init__(self, legacy_path):
        self.legacy_path = os.path.abspath(str(legacy_path))
        root, extension = os.path.splitext(self.legacy_path)
        self.path = root + ".sqlite3" if extension.lower() == ".json" else self.legacy_path + ".sqlite3"
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15.0, factory=_ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def _initialize(self):
        with self._lock, self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=NORMAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_records (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    canonical_key TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    validation_state TEXT NOT NULL DEFAULT 'unverified',
                    last_validated_at TEXT,
                    selected_count INTEGER NOT NULL DEFAULT 0,
                    injection_count INTEGER NOT NULL DEFAULT 0,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    helpful_count INTEGER NOT NULL DEFAULT 0,
                    unhelpful_count INTEGER NOT NULL DEFAULT 0,
                    last_injected_at TEXT,
                    last_used_at TEXT,
                    record_json TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_active_canonical
                    ON memory_records(scope, canonical_key) WHERE status='active';
                CREATE INDEX IF NOT EXISTS idx_memory_scope_status
                    ON memory_records(status, scope, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_retention
                    ON memory_records(status, last_used_at, last_injected_at, updated_at);
                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    canonical_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    candidate_json TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_candidate_canonical
                    ON memory_candidates(scope, canonical_key) WHERE status='pending';
                CREATE TABLE IF NOT EXISTS memory_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    digest TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(memory_id, evidence_type, reference)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_evidence_memory
                    ON memory_evidence(memory_id);
                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT,
                    event TEXT NOT NULL,
                    query_preview TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_events_memory
                    ON memory_events(memory_id, created_at DESC);
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    id UNINDEXED,
                    subject,
                    content,
                    tags,
                    category,
                    scope UNINDEXED,
                    tokenize='unicode61 remove_diacritics 2'
                );
                """
            )
            try:
                previous_version = int(self._meta(db, "schema_version", "0") or 0)
            except Exception:
                previous_version = 0
            if previous_version < 3:
                db.execute("DROP TABLE IF EXISTS memory_fts")
                db.execute(
                    """CREATE VIRTUAL TABLE memory_fts USING fts5(
                        id UNINDEXED, subject, content, tags, category, scope UNINDEXED,
                        tokenize='unicode61 remove_diacritics 2'
                    )"""
                )
            self._set_meta(db, "schema_version", str(self.SCHEMA_VERSION))

    def _meta(self, db, key, default=""):
        row = db.execute("SELECT value FROM memory_meta WHERE key=?", (str(key),)).fetchone()
        return str(row["value"]) if row else default

    def _set_meta(self, db, key, value):
        db.execute(
            "INSERT OR REPLACE INTO memory_meta(key, value) VALUES(?, ?)",
            (str(key), str(value)),
        )

    def has_snapshot(self):
        with self._lock, self._connect() as db:
            records = db.execute("SELECT 1 FROM memory_records LIMIT 1").fetchone()
            candidates = db.execute("SELECT 1 FROM memory_candidates LIMIT 1").fetchone()
            return bool(records or candidates or self._meta(db, "snapshot_initialized"))

    def ensure_legacy_backup(self):
        """Create one recovery copy before the first V2 import/migration."""
        if not os.path.exists(self.legacy_path):
            return ""
        with self._lock, self._connect() as db:
            existing = self._meta(db, "legacy_backup_path")
            if existing and os.path.exists(existing):
                return existing
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            root, extension = os.path.splitext(self.legacy_path)
            target = f"{root}.pre-memory-v2-{stamp}{extension or '.json'}"
            shutil.copy2(self.legacy_path, target)
            self._set_meta(db, "legacy_backup_path", target)
            self._set_meta(db, "legacy_backup_at", datetime.now().isoformat(timespec="seconds"))
            return target

    @staticmethod
    def _overlay_record_columns(entry, row):
        item = copy.deepcopy(entry)
        for key in (
            "selected_count", "injection_count", "used_count", "helpful_count",
            "unhelpful_count", "last_injected_at", "last_used_at",
            "validation_state", "last_validated_at",
        ):
            value = row[key]
            if value not in (None, "") or key.endswith("_count"):
                item[key] = value
        item["canonical_key"] = str(row["canonical_key"] or item.get("canonical_key") or "")
        return item

    def load_snapshot(self):
        with self._lock, self._connect() as db:
            data = {
                "schema_version": self.SCHEMA_VERSION,
                "entries": [],
                "archive": [],
                "pending": [],
                "rejected": [],
                "stats": _json_object(self._meta(db, "stats_json", "{}")),
            }
            for row in db.execute("SELECT * FROM memory_records ORDER BY updated_at DESC"):
                entry = self._overlay_record_columns(_json_object(row["record_json"]), row)
                entry["status"] = str(row["status"])
                if row["status"] == "active":
                    data["entries"].append(entry)
                else:
                    data["archive"].append(entry)
            for row in db.execute("SELECT * FROM memory_candidates ORDER BY updated_at DESC"):
                candidate = _json_object(row["candidate_json"])
                candidate["status"] = str(row["status"])
                target = "pending" if row["status"] == "pending" else "rejected"
                data[target].append(candidate)
            data["stats"]["storage_backend"] = "sqlite-v2"
            data["stats"]["sqlite_path"] = self.path
            return data

    @staticmethod
    def _record_values(entry, status):
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        return (
            str(entry.get("id") or ""), str(status), str(entry.get("type") or "long_term"),
            str(entry.get("scope") or "global"), str(entry.get("canonical_key") or entry.get("id") or ""),
            str(entry.get("subject") or ""), str(entry.get("content") or ""),
            str(entry.get("category") or metadata.get("category") or "general"),
            str(entry.get("sensitivity") or metadata.get("sensitivity") or "ordinary"),
            str(entry.get("source") or "unknown"), str(entry.get("created_at") or ""),
            str(entry.get("updated_at") or entry.get("created_at") or ""), entry.get("expires_at"),
            str(entry.get("validation_state") or metadata.get("validation_state") or "unverified"),
            entry.get("last_validated_at"), int(entry.get("selected_count", 0) or 0),
            int(entry.get("injection_count", 0) or 0), int(entry.get("used_count", 0) or 0),
            int(entry.get("helpful_count", 0) or 0), int(entry.get("unhelpful_count", 0) or 0),
            entry.get("last_injected_at"), entry.get("last_used_at"), _json_dumps(entry),
        )

    def replace_snapshot(self, data):
        """Persist one complete logical mutation in one SQLite transaction."""
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM memory_fts")
            db.execute("DELETE FROM memory_evidence")
            db.execute("DELETE FROM memory_records")
            db.execute("DELETE FROM memory_candidates")
            sql = """
                INSERT INTO memory_records(
                    id,status,type,scope,canonical_key,subject,content,category,sensitivity,
                    source,created_at,updated_at,expires_at,validation_state,last_validated_at,
                    selected_count,injection_count,used_count,helpful_count,unhelpful_count,
                    last_injected_at,last_used_at,record_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """
            for status, collection in (("active", data.get("entries", [])), ("archive", data.get("archive", []))):
                for entry in collection:
                    if not isinstance(entry, dict) or not entry.get("id"):
                        continue
                    db.execute(sql, self._record_values(entry, status))
                    # Persisted memory content is DPAPI-protected. Never accept a
                    # transient plaintext override here: it would leave a second,
                    # unencrypted copy in SQLite's FTS table.
                    plain_content = str(entry.get("content") or "")
                    if not plain_content.startswith("DPAPI:"):
                        db.execute(
                            "INSERT INTO memory_fts(id,subject,content,tags,category,scope) VALUES(?,?,?,?,?,?)",
                            (
                                str(entry.get("id")), str(entry.get("subject") or ""), plain_content,
                                " ".join(str(tag) for tag in (entry.get("tags") or [])),
                                str(entry.get("category") or "general"), str(entry.get("scope") or "global"),
                            ),
                        )
                    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                    for evidence in metadata.get("evidence", []) if isinstance(metadata.get("evidence"), list) else []:
                        if not isinstance(evidence, dict) or not evidence.get("reference"):
                            continue
                        db.execute(
                            """INSERT OR IGNORE INTO memory_evidence(
                                memory_id,evidence_type,reference,digest,metadata_json,created_at
                            ) VALUES(?,?,?,?,?,?)""",
                            (
                                str(entry.get("id")), str(evidence.get("type") or "reference"),
                                str(evidence.get("reference")), str(evidence.get("digest") or ""),
                                _json_dumps(evidence.get("metadata") or {}),
                                str(evidence.get("created_at") or entry.get("created_at") or ""),
                            ),
                        )
            for status, collection in (("pending", data.get("pending", [])), ("rejected", data.get("rejected", []))):
                for candidate in collection:
                    if not isinstance(candidate, dict) or not candidate.get("id"):
                        continue
                    db.execute(
                        """INSERT INTO memory_candidates(
                            id,status,scope,canonical_key,created_at,updated_at,candidate_json
                        ) VALUES(?,?,?,?,?,?,?)""",
                        (
                            str(candidate.get("id")), status, str(candidate.get("scope") or "global"),
                            str(candidate.get("canonical_key") or candidate.get("id")),
                            str(candidate.get("created_at") or ""),
                            str(candidate.get("updated_at") or candidate.get("created_at") or ""),
                            _json_dumps(candidate),
                        ),
                    )
            self._set_meta(db, "stats_json", _json_dumps(data.get("stats", {})))
            self._set_meta(db, "snapshot_initialized", "1")
            self._set_meta(db, "snapshot_updated_at", datetime.now().isoformat(timespec="seconds"))

    def search_fts(self, tokens, *, scopes=None, memory_types=None, limit=48):
        tokens = [str(token).replace('"', "").strip() for token in (tokens or []) if str(token).strip()]
        if not tokens:
            return []
        query = " OR ".join(f'"{token}"' for token in tokens[:24])
        conditions = ["memory_fts MATCH ?", "r.status='active'"]
        params = [query]
        scopes = [str(scope) for scope in (scopes or []) if str(scope)]
        if scopes:
            conditions.append("r.scope IN (%s)" % ",".join("?" for _ in scopes))
            params.extend(scopes)
        memory_types = [str(value) for value in (memory_types or []) if str(value)]
        if memory_types:
            conditions.append("r.type IN (%s)" % ",".join("?" for _ in memory_types))
            params.extend(memory_types)
        params.append(max(1, min(200, int(limit or 48))))
        with self._lock, self._connect() as db:
            rows = db.execute(
                f"""SELECT r.id, bm25(memory_fts, 0.0, 2.2, 1.0, 0.35, 0.25, 0.2) AS rank
                    FROM memory_fts JOIN memory_records r ON r.id=memory_fts.id
                    WHERE {' AND '.join(conditions)} ORDER BY rank LIMIT ?""",
                tuple(params),
            ).fetchall()
            return [(str(row["id"]), float(row["rank"] or 0.0)) for row in rows]

    def record_retrieval(self, *, selected_ids=None, injected_ids=None, query="", tokens=0, chars=0):
        now = datetime.now().isoformat(timespec="seconds")
        selected_ids = [str(value) for value in (selected_ids or []) if value]
        injected_ids = [str(value) for value in (injected_ids or []) if value]
        with self._lock, self._connect() as db:
            for memory_id in selected_ids:
                db.execute(
                    "UPDATE memory_records SET selected_count=selected_count+1 WHERE id=?",
                    (memory_id,),
                )
                db.execute(
                    "INSERT INTO memory_events(memory_id,event,query_preview,metadata_json,created_at) VALUES(?,?,?,?,?)",
                    (memory_id, "selected", str(query)[:180], "{}", now),
                )
            for memory_id in injected_ids:
                db.execute(
                    """UPDATE memory_records SET injection_count=injection_count+1,
                       last_injected_at=? WHERE id=?""",
                    (now, memory_id),
                )
                db.execute(
                    "INSERT INTO memory_events(memory_id,event,query_preview,metadata_json,created_at) VALUES(?,?,?,?,?)",
                    (memory_id, "injected", str(query)[:180], _json_dumps({"tokens": int(tokens), "chars": int(chars)}), now),
                )

    def record_feedback(self, memory_id, feedback, query=""):
        feedback = str(feedback or "").strip().lower()
        columns = {
            "used": ("used_count", "last_used_at"),
            "helpful": ("helpful_count", "last_used_at"),
            "unhelpful": ("unhelpful_count", None),
            "stale": ("unhelpful_count", None),
        }
        if feedback not in columns:
            raise ValueError("Unsupported memory feedback.")
        now = datetime.now().isoformat(timespec="seconds")
        count_column, time_column = columns[feedback]
        assignment = f"{count_column}={count_column}+1"
        params = []
        if time_column:
            assignment += f", {time_column}=?"
            params.append(now)
        params.append(str(memory_id))
        with self._lock, self._connect() as db:
            result = db.execute(f"UPDATE memory_records SET {assignment} WHERE id=?", tuple(params))
            if not result.rowcount:
                return False
            db.execute(
                "INSERT INTO memory_events(memory_id,event,query_preview,metadata_json,created_at) VALUES(?,?,?,?,?)",
                (str(memory_id), feedback, str(query)[:180], "{}", now),
            )
            return True
