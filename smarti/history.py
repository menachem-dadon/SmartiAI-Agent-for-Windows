"""Persistent chat-session storage and fuzzy search."""
from .common import *

CHAT_HISTORY_SCHEMA_VERSION = 1
DEFAULT_CHAT_TITLE = "שיחה חדשה"


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _clean_title(value):
    title = re.sub(r"\s+", " ", str(value or "")).strip()
    title = re.sub(r'^[#"\':\-–—\s]+|[#"\':\-–—\s]+$', "", title).strip()
    return (title[:64].rstrip() or DEFAULT_CHAT_TITLE)


def _message_text(message):
    if not isinstance(message, dict):
        return ""
    text = str(message.get("content", "") or "")
    metadata = message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}
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
        candidates = [candidate for candidate in target_words if abs(len(candidate) - len(word)) <= max(3, len(word) // 2)]
        if not candidates:
            candidates = target_words[:80]
        best = 0.0
        for candidate in candidates[:140]:
            ratio = difflib.SequenceMatcher(None, word, candidate).ratio()
            if ratio > best:
                best = ratio
        scores.append(best)
    return sum(scores) / max(1, len(scores))


class ChatSessionStore:
    def __init__(self, path=CHAT_HISTORY_FILE):
        self.path = path
        self._lock = threading.RLock()
        self.data = {"schema_version": CHAT_HISTORY_SCHEMA_VERSION, "active_session_id": "", "sessions": []}
        self._load()

    def _load(self):
        with self._lock:
            try:
                if os.path.exists(self.path):
                    with open(self.path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.data = loaded
            except Exception as e:
                logging.warning(f"Chat history load failed; starting with empty history: {e}")
                self.data = {"schema_version": CHAT_HISTORY_SCHEMA_VERSION, "active_session_id": "", "sessions": []}
            self.data["schema_version"] = CHAT_HISTORY_SCHEMA_VERSION
            self.data["sessions"] = [self._normalize_session(item) for item in self.data.get("sessions", []) if isinstance(item, dict)]
            if not self._session_by_id(self.data.get("active_session_id")):
                latest = self._latest_session()
                self.data["active_session_id"] = latest.get("id", "") if latest else ""

    def _save(self):
        with self._lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp_path = f"{self.path}.tmp"
            data = copy.deepcopy(self.data)
            data["sessions"] = [session for session in data.get("sessions", []) if session.get("messages")]
            if not any(session.get("id") == data.get("active_session_id") for session in data["sessions"]):
                data["active_session_id"] = ""
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)

    def _normalize_session(self, session):
        now = _now_iso()
        session_id = str(session.get("id") or uuid.uuid4().hex)
        messages = []
        for message in session.get("messages", []) or []:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "").strip().lower()
            if role not in {"user", "assistant", "system"}:
                role = "assistant"
            messages.append({
                "role": role,
                "content": str(message.get("content", "") or ""),
                "created_at": str(message.get("created_at") or session.get("updated_at") or now),
                "metadata": copy.deepcopy(message.get("metadata", {}) if isinstance(message.get("metadata"), dict) else {}),
            })
        return {
            "id": session_id,
            "title": _clean_title(session.get("title") or DEFAULT_CHAT_TITLE),
            "created_at": str(session.get("created_at") or now),
            "updated_at": str(session.get("updated_at") or now),
            "pinned": bool(session.get("pinned", False)),
            "title_generated": bool(session.get("title_generated", False)),
            "title_user_edited": bool(session.get("title_user_edited", False)),
            "messages": messages,
            "context": copy.deepcopy(session.get("context", {}) if isinstance(session.get("context"), dict) else {}),
        }

    def _session_by_id(self, session_id):
        session_id = str(session_id or "")
        for session in self.data.get("sessions", []):
            if session.get("id") == session_id:
                return session
        return None

    def _latest_session(self):
        sessions = self.data.get("sessions", [])
        if not sessions:
            return None
        return sorted(sessions, key=lambda item: str(item.get("updated_at", "")), reverse=True)[0]

    def _new_session(self):
        now = _now_iso()
        return {
            "id": uuid.uuid4().hex,
            "title": DEFAULT_CHAT_TITLE,
            "created_at": now,
            "updated_at": now,
            "pinned": False,
            "title_generated": False,
            "title_user_edited": False,
            "messages": [],
            "context": {},
        }

    def ensure_active_session(self):
        with self._lock:
            session = self._session_by_id(self.data.get("active_session_id"))
            if session:
                return copy.deepcopy(session)
            session = self._new_session()
            self.data.setdefault("sessions", []).append(session)
            self.data["active_session_id"] = session["id"]
            self._save()
            return copy.deepcopy(session)

    def active_session(self):
        with self._lock:
            session = self._session_by_id(self.data.get("active_session_id"))
            if not session:
                return self.ensure_active_session()
            return copy.deepcopy(session)

    def create_session(self, set_active=True):
        with self._lock:
            current = self._session_by_id(self.data.get("active_session_id"))
            if set_active and current and not current.get("messages"):
                current["updated_at"] = _now_iso()
                current["context"] = {}
                current["title"] = DEFAULT_CHAT_TITLE
                current["title_generated"] = False
                current["title_user_edited"] = False
                self._save()
                return copy.deepcopy(current)
            session = self._new_session()
            self.data.setdefault("sessions", []).append(session)
            if set_active:
                self.data["active_session_id"] = session["id"]
            self._save()
            return copy.deepcopy(session)

    def set_active(self, session_id):
        with self._lock:
            session = self._session_by_id(session_id)
            if not session:
                return False
            self.data["active_session_id"] = session["id"]
            self._save()
            return True

    def messages(self, session_id=None):
        with self._lock:
            session = self._session_by_id(session_id or self.data.get("active_session_id"))
            return copy.deepcopy(session.get("messages", [])) if session else []

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
        with self._lock:
            sessions = [session for session in self.data.get("sessions", []) if session.get("messages")]
            records = [self._summary_for_session(session, query=query) for session in sessions]
            query = str(query or "").strip()
            if query:
                records = [record for record in records if max(record["title_score"], record["content_score"]) >= 0.48]
                records.sort(
                    key=lambda record: (
                        0 if record["match_kind"] == "title" else 1,
                        not record["pinned"],
                        -max(record["title_score"] * 1.4, record["content_score"]),
                        -_time_score(record.get("updated_at", "")),
                    )
                )
                return records
            records.sort(key=lambda record: (not record["pinned"], str(record.get("updated_at", ""))), reverse=False)
            pinned = [record for record in records if record["pinned"]]
            unpinned = [record for record in records if not record["pinned"]]
            pinned.sort(key=lambda record: str(record.get("updated_at", "")), reverse=True)
            unpinned.sort(key=lambda record: str(record.get("updated_at", "")), reverse=True)
            return pinned + unpinned

    def should_generate_title_for_next_turn(self):
        with self._lock:
            session = self._session_by_id(self.data.get("active_session_id"))
            if not session or session.get("title_user_edited") or session.get("title_generated"):
                return False
            user_messages = [m for m in session.get("messages", []) if m.get("role") == "user"]
            return len(user_messages) == 0

    def add_turn(self, user_text, assistant_text, assistant_raw=None, is_error=False, title="", context=None, user_metadata=None, assistant_metadata=None):
        with self._lock:
            session = self._session_by_id(self.data.get("active_session_id"))
            if not session:
                session = self._new_session()
                self.data.setdefault("sessions", []).append(session)
                self.data["active_session_id"] = session["id"]
            now = _now_iso()
            metadata = copy.deepcopy(user_metadata if isinstance(user_metadata, dict) else {})
            if str(user_text or "").strip() or metadata.get("attachments"):
                session.setdefault("messages", []).append({
                    "role": "user",
                    "content": str(user_text or ""),
                    "created_at": now,
                    "metadata": metadata,
                })
            if str(assistant_text or "").strip():
                metadata = copy.deepcopy(assistant_metadata if isinstance(assistant_metadata, dict) else {})
                metadata["is_error"] = bool(is_error)
                if assistant_raw is not None and assistant_raw != assistant_text:
                    metadata["raw"] = str(assistant_raw)
                session.setdefault("messages", []).append({
                    "role": "assistant",
                    "content": str(assistant_text or ""),
                    "created_at": now,
                    "metadata": metadata,
                })
            if title and not session.get("title_user_edited"):
                session["title"] = _clean_title(title)
                session["title_generated"] = True
            if isinstance(context, dict):
                session["context"] = copy.deepcopy(context)
            session["updated_at"] = now
            self._save()
            return copy.deepcopy(session)

    def update_context(self, context, session_id=None):
        if not isinstance(context, dict):
            return False
        with self._lock:
            session = self._session_by_id(session_id or self.data.get("active_session_id"))
            if not session:
                return False
            session["context"] = copy.deepcopy(context)
            self._save()
            return True

    def rename_session(self, session_id, title):
        with self._lock:
            session = self._session_by_id(session_id)
            if not session:
                return False
            session["title"] = _clean_title(title)
            session["title_user_edited"] = True
            session["title_generated"] = bool(session["title"] and session["title"] != DEFAULT_CHAT_TITLE)
            self._save()
            return True

    def set_pinned(self, session_id, pinned):
        with self._lock:
            session = self._session_by_id(session_id)
            if not session:
                return False
            session["pinned"] = bool(pinned)
            self._save()
            return True

    def delete_session(self, session_id):
        with self._lock:
            session_id = str(session_id or "")
            original_count = len(self.data.get("sessions", []))
            self.data["sessions"] = [session for session in self.data.get("sessions", []) if session.get("id") != session_id]
            if len(self.data["sessions"]) == original_count:
                return False
            if self.data.get("active_session_id") == session_id:
                latest = self._latest_session()
                if latest:
                    self.data["active_session_id"] = latest["id"]
                else:
                    session = self._new_session()
                    self.data["sessions"].append(session)
                    self.data["active_session_id"] = session["id"]
            self._save()
            return True

    def export_session(self, session_id, target_path):
        with self._lock:
            session = self._session_by_id(session_id)
            if not session:
                raise ValueError("Session not found.")
            payload = {
                "schema_version": CHAT_HISTORY_SCHEMA_VERSION,
                "exported_at": _now_iso(),
                "session": copy.deepcopy(session),
            }
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return target_path
