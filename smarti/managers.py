"""Settings, memory, policy, registry, and runtime manager classes."""
import math
from .common import *
from .config import *

class SettingsManager:
    """Schema-v2 settings migration with a clean reset of dangerous trust state."""
    DEPRECATED_CONTEXT_LIMIT_KEYS = {
        "agent_context_compact_after_loops",
        "agent_inline_history_message_limit",
        "agent_inline_history_chars",
        "conversation_history_limit",
        "max_inline_tool_feedback_chars",
        "max_inline_tool_error_chars",
    }
    PRESERVE_ON_V2_MIGRATION = {
        "api_mode", "local_server_url", "local_fast_mode_enabled", "shopping_list", "user_memory",
        "read_aloud_all", "read_aloud_voice_only", "tts_voice_id", "tts_volume",
        "voice_hotkey", "keep_running_in_tray",
        "voice_sensitivity", "voice_dynamic_energy_threshold", "voice_pause_threshold",
        "voice_listen_timeout", "voice_ambient_noise_duration",
        "voice_beep_enabled", "legal_acceptance"
    } | {f"selected_{provider}_model" for provider in MODEL_PROVIDER_ORDER}

    def __init__(self, settings_file, defaults):
        self.settings_file = settings_file
        self.defaults = defaults

    def backup_existing(self):
        if not os.path.exists(self.settings_file):
            return ""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = os.path.join(os.path.dirname(self.settings_file), f"smarti_settings.backup.{stamp}.json")
        shutil.copy2(self.settings_file, backup_path)
        return backup_path

    def decrypt_loaded_secrets(self, loaded):
        for key in SENSITIVE_SETTING_KEYS:
            value = loaded.get(key, "")
            if isinstance(value, str) and value.startswith(SECRET_PREFIX):
                loaded[key] = dpapi_unprotect_text(value)
        return loaded

    def sync_legacy_aliases(self, settings):
        privacy = settings.setdefault("privacy", {})
        if "redact_logs" not in privacy:
            privacy["redact_logs"] = bool(settings.get("privacy_redact_logs", True))
        settings["privacy_redact_logs"] = bool(privacy.get("redact_logs", True))
        if "default_output_dir" not in settings:
            legacy_dirs = settings.get("allowed_write_dirs") or []
            settings["default_output_dir"] = legacy_dirs[0] if isinstance(legacy_dirs, list) and legacy_dirs else OUTPUTS_DIR
        settings["allowed_write_dirs"] = [settings.get("default_output_dir") or OUTPUTS_DIR]
        settings.setdefault("background_jobs", settings.get("background_tasks", []))
        settings.setdefault("background_tasks", settings.get("background_jobs", []))
        mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
        settings["ssl_trust_mode"] = mode
        settings["ssl_custom_ca_path"] = str(settings.get("ssl_custom_ca_path") or "").strip()
        settings["ssl_legacy_insecure_allowed_hosts"] = normalize_legacy_hosts(
            settings.get("ssl_legacy_insecure_allowed_hosts", [])
        )
        settings["allow_insecure_ssl_compat"] = mode == SSL_MODE_LEGACY_INSECURE
        settings.setdefault("settings_schema_version", SETTINGS_SCHEMA_VERSION)
        return settings

    @staticmethod
    def migrate_long_task_defaults(settings):
        """Replace only the old shipped limits, preserving custom user values."""
        settings = copy.deepcopy(settings or {})
        try:
            migration_version = int(settings.get("long_task_defaults_version", 0) or 0)
        except Exception:
            migration_version = 0
        if migration_version >= 1:
            return settings, False
        if settings.get("max_agent_loops", 15) == 15:
            settings["max_agent_loops"] = 0
        if settings.get("max_total_task_seconds", 3600) == 3600:
            settings["max_total_task_seconds"] = 0
        if settings.get("preserve_current_task_tool_context", True) is True:
            settings["preserve_current_task_tool_context"] = False
        settings["long_task_defaults_version"] = 1
        return settings, True

    @staticmethod
    def migrate_model_selection_provenance(settings, prior_settings=None):
        """Record conservative provenance without guessing about legacy choices."""
        settings = copy.deepcopy(settings or {})
        prior_settings = prior_settings if isinstance(prior_settings, dict) else settings
        before = copy.deepcopy(settings)
        current_sources = settings.get("selected_model_source", {})
        prior_sources = prior_settings.get("selected_model_source", {})
        if not isinstance(current_sources, dict):
            current_sources = {}
        if not isinstance(prior_sources, dict):
            prior_sources = {}
        sources = {}
        valid_sources = {
            MODEL_SELECTION_SOURCE_DEFAULT,
            MODEL_SELECTION_SOURCE_USER,
        }
        for provider in MODEL_PROVIDER_ORDER:
            source = str(prior_sources.get(provider, "") or "").strip().lower()
            if source not in valid_sources:
                source = str(current_sources.get(provider, "") or "").strip().lower()
            if source not in valid_sources:
                selected_key = f"selected_{provider}_model"
                source = (
                    MODEL_SELECTION_SOURCE_USER
                    if str(prior_settings.get(selected_key, "") or "").strip()
                    else MODEL_SELECTION_SOURCE_DEFAULT
                )
            sources[provider] = source
        settings["selected_model_source"] = sources
        settings["model_selection_provenance_version"] = MODEL_SELECTION_PROVENANCE_VERSION
        return settings, settings != before

    @staticmethod
    def migrate_ssl_trust(settings):
        """Migrate the old global bypass to verified Windows trust.

        The old boolean was enabled by default, so it cannot prove that a user
        deliberately accepted an insecure mode.  Existing installations
        therefore move to the system store and may opt into a narrow emergency
        host list explicitly through the new UI.
        """
        settings = copy.deepcopy(settings or {})
        try:
            version = int(settings.get("ssl_trust_migration_version", 0) or 0)
        except Exception:
            version = 0
        changed = False
        if version < SSL_TRUST_MIGRATION_VERSION:
            old_insecure = bool(settings.get("allow_insecure_ssl_compat", False))
            explicit_mode = str(settings.get("ssl_trust_mode") or "").strip().lower()
            if explicit_mode not in SSL_TRUST_MODES:
                settings["ssl_trust_mode"] = SSL_MODE_SYSTEM
            else:
                settings["ssl_trust_mode"] = explicit_mode
            settings.setdefault("ssl_custom_ca_path", "")
            settings.setdefault("ssl_filter_setup_completed", False)
            settings.setdefault("ssl_legacy_insecure_allowed_hosts", [])
            settings["ssl_migrated_from_global_insecure"] = old_insecure
            settings["ssl_trust_migration_version"] = SSL_TRUST_MIGRATION_VERSION
            changed = True
        mode = normalize_ssl_trust_mode(settings.get("ssl_trust_mode"))
        hosts = normalize_legacy_hosts(settings.get("ssl_legacy_insecure_allowed_hosts", []))
        if settings.get("ssl_trust_mode") != mode:
            settings["ssl_trust_mode"] = mode
            changed = True
        if settings.get("ssl_legacy_insecure_allowed_hosts", []) != hosts:
            settings["ssl_legacy_insecure_allowed_hosts"] = hosts
            changed = True
        alias = mode == SSL_MODE_LEGACY_INSECURE
        if bool(settings.get("allow_insecure_ssl_compat", False)) != alias:
            settings["allow_insecure_ssl_compat"] = alias
            changed = True
        return settings, changed

    def migrate_or_merge(self, loaded):
        loaded = self.decrypt_loaded_secrets(copy.deepcopy(loaded or {}))
        prior_loaded = copy.deepcopy(loaded)
        if int(loaded.get("settings_schema_version", 0) or 0) != SETTINGS_SCHEMA_VERSION:
            backup_path = self.backup_existing()
            migrated = copy.deepcopy(self.defaults)
            for key in self.PRESERVE_ON_V2_MIGRATION:
                if key in loaded:
                    migrated[key] = copy.deepcopy(loaded[key])
            for key in SENSITIVE_SETTING_KEYS:
                if loaded.get(key):
                    migrated[key] = loaded.get(key)
            migrated["migration"] = {
                "from_schema_version": loaded.get("settings_schema_version", 1),
                "migrated_at": datetime.now().isoformat(timespec="seconds"),
                "backup_path": backup_path,
                "dangerous_trust_reset": True
            }
            migrated, _ = self.migrate_model_selection_provenance(
                migrated,
                prior_settings=prior_loaded,
            )
            return self.sync_legacy_aliases(migrated), True
        loaded, ssl_trust_changed = self.migrate_ssl_trust(loaded)
        loaded, long_task_changed = self.migrate_long_task_defaults(loaded)
        loaded, model_provenance_changed = self.migrate_model_selection_provenance(
            loaded,
            prior_settings=prior_loaded,
        )
        context_limits_changed = False
        for key in self.DEPRECATED_CONTEXT_LIMIT_KEYS:
            if key in loaded:
                loaded.pop(key, None)
                context_limits_changed = True
        return (
            self.sync_legacy_aliases(deep_merge_defaults(self.defaults, loaded)),
            bool(
                ssl_trust_changed
                or long_task_changed
                or model_provenance_changed
                or context_limits_changed
            ),
        )


class SmartiMemoryManager:
    """Local structured memory with TTL and bounded RAG injection."""
    SCHEMA_VERSION = 4
    PROFILE_POLICY_VERSION = 4
    PRIVACY_POLICY_VERSION = 1
    AUTOMATIC_USE_POLICY_VERSION = 1
    USER_WORK_CLEANUP_VERSION = 1
    VALID_TYPES = {"short_term", "long_term", "tool", "user"}
    SENSITIVE_CATEGORIES = {"address", "phone", "email", "health"}
    NEVER_STORE_CATEGORIES = {"authentication_secret", "financial_secret"}
    RETRIEVER_NAME = "local-hebrew-weighted-v2"
    HEBREW_FINALS = str.maketrans({
        "\u05da": "\u05db",
        "\u05dd": "\u05de",
        "\u05df": "\u05e0",
        "\u05e3": "\u05e4",
        "\u05e5": "\u05e6",
    })
    HEBREW_STOPWORDS = {
        "\u05d0\u05d5", "\u05d0\u05d6", "\u05d0\u05ea", "\u05d6\u05d4", "\u05d6\u05d5",
        "\u05d4\u05d5\u05d0", "\u05d4\u05d9\u05d0", "\u05d4\u05dd", "\u05d4\u05df", "\u05d4\u05d9\u05d4",
        "\u05d9\u05e9", "\u05dc\u05d0", "\u05db\u05df", "\u05e9\u05dc", "\u05e2\u05dc", "\u05e2\u05dd",
        "\u05db\u05dc", "\u05db\u05de\u05d4", "\u05de\u05d4", "\u05de\u05d9", "\u05d0\u05d9\u05da",
        "\u05d0\u05dd", "\u05d1\u05d5", "\u05d1\u05d4", "\u05dc\u05d9", "\u05dc\u05da", "\u05dc\u05d5",
    }
    SEARCH_EXPANSION_GROUPS = {
        "identity": {
            "identity", "profile", "name", "called", "whoami", "aboutme",
            "\u05d6\u05d4\u05d5\u05ea", "\u05e4\u05e8\u05d5\u05e4\u05d9\u05dc", "\u05e9\u05de\u05d9",
            "\u05e9\u05dd", "\u05e7\u05d5\u05e8\u05d0\u05d9\u05dd", "\u05de\u05d9\u05d0\u05e0\u05d9",
        },
        "address": {
            "address", "home", "live", "where", "street", "city",
            "\u05db\u05ea\u05d5\u05d1\u05ea", "\u05d1\u05d9\u05ea", "\u05d2\u05e8", "\u05d2\u05e8\u05d4",
            "\u05de\u05d2\u05d5\u05e8\u05d9\u05dd", "\u05de\u05ea\u05d2\u05d5\u05e8\u05e8", "\u05d0\u05d9\u05e4\u05d4",
            "\u05e8\u05d7\u05d5\u05d1", "\u05e2\u05d9\u05e8",
        },
        "preference": {
            "preference", "prefer", "style", "likes", "dislikes", "always", "never",
            "\u05de\u05e2\u05d3\u05d9\u05e3", "\u05de\u05e2\u05d3\u05d9\u05e4\u05d4", "\u05d0\u05d5\u05d4\u05d1",
            "\u05d0\u05d5\u05d4\u05d1\u05ea", "\u05e1\u05d2\u05e0\u05d5\u05df", "\u05ea\u05de\u05d9\u05d3",
            "\u05d0\u05e3\u05e4\u05e2\u05dd", "\u05d4\u05e2\u05d3\u05e4\u05d5\u05ea",
        },
        "tool": {
            "tool", "tools", "command", "ran", "result", "error", "log",
            "\u05db\u05dc\u05d9", "\u05db\u05dc\u05d9\u05dd", "\u05e4\u05e7\u05d5\u05d3\u05d4",
            "\u05d4\u05e8\u05e6\u05d4", "\u05ea\u05d5\u05e6\u05d0\u05d4", "\u05e9\u05d2\u05d9\u05d0\u05d4",
        },
        "continuity": {
            "previous", "last", "again", "continue", "earlier", "conversation",
            "\u05e7\u05d5\u05d3\u05dd", "\u05d0\u05d7\u05e8\u05d5\u05df", "\u05e9\u05d5\u05d1",
            "\u05d4\u05de\u05e9\u05da", "\u05e9\u05d9\u05d7\u05d4", "\u05dc\u05e4\u05e0\u05d9",
        },
        "project": {
            "project", "repo", "repository", "codebase", "file", "folder", "task",
            "\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8", "\u05de\u05d0\u05d2\u05e8", "\u05e7\u05d5\u05d3",
            "\u05e7\u05d5\u05d1\u05e5", "\u05ea\u05d9\u05e7\u05d9\u05d9\u05d4", "\u05de\u05e9\u05d9\u05de\u05d4",
        },
    }
    LIVE_DATA_TERMS = {
        "today", "tonight", "tomorrow", "yesterday", "now", "current", "latest",
        "weather", "forecast", "price", "rate", "stock", "news", "score",
        "traffic", "schedule", "status", "availability", "deadline",
        "היום", "הלילה", "מחר", "אתמול", "עכשיו", "כרגע", "עדכני", "אחרון",
        "מזג", "תחזית", "מחיר", "שער", "מניה", "חדשות", "תוצאה", "לו\"ז",
        "זמנים", "סטטוס", "זמינות"
    }
    USER_MEMORY_TERMS = {
        "remember", "prefer", "preference", "my name", "call me", "i am",
        "תזכור", "זכור", "קוראים לי", "שמי", "אני מעדיף", "אני מעדיפה",
        "אני אוהב", "אני אוהבת", "אל תשכח", "חשוב לי"
    }

    DO_NOT_REMEMBER_TERMS = {
        "do not remember", "don't remember", "dont remember", "do not save", "don't save",
        "forget this", "temporary only", "\u05d0\u05dc \u05ea\u05d6\u05db\u05d5\u05e8",
        "\u05d0\u05dc \u05ea\u05e9\u05de\u05d5\u05e8", "\u05dc\u05d0 \u05dc\u05e9\u05de\u05d5\u05e8",
        "\u05e8\u05e7 \u05d6\u05de\u05e0\u05d9"
    }
    SECRET_DETAIL_TERMS = {
        "password", "passcode", "api key", "apikey", "secret key", "access token",
        "refresh token", "otp", "2fa", "cvv", "credit card", "card number",
        "\u05e1\u05d9\u05e1\u05de\u05d4", "\u05e1\u05d9\u05e1\u05de\u05ea", "\u05de\u05e4\u05ea\u05d7 api",
        "\u05d8\u05d5\u05e7\u05df", "\u05e7\u05d5\u05d3 \u05d0\u05d9\u05de\u05d5\u05ea", "\u05d0\u05e9\u05e8\u05d0\u05d9"
    }
    CRITICAL_USER_DETAIL_RULES = [
        ("address", "user", 5, ["address", "home address", "street address", "i live at", "i live in", "my home is",
                               "\u05db\u05ea\u05d5\u05d1\u05ea", "\u05db\u05ea\u05d5\u05d1\u05ea \u05d4\u05de\u05d2\u05d5\u05e8\u05d9\u05dd", "\u05d0\u05e0\u05d9 \u05d2\u05e8", "\u05d0\u05e0\u05d9 \u05d2\u05e8\u05d4",
                               "\u05d0\u05e0\u05d9 \u05de\u05ea\u05d2\u05d5\u05e8\u05e8", "\u05d0\u05e0\u05d9 \u05de\u05ea\u05d2\u05d5\u05e8\u05e8\u05ea", "\u05e8\u05d7\u05d5\u05d1", "\u05d3\u05d9\u05e8\u05d4", "\u05de\u05d9\u05e7\u05d5\u05d3"]),
        ("phone", "user", 5, ["phone", "phone number", "mobile", "cell", "\u05d8\u05dc\u05e4\u05d5\u05df", "\u05e0\u05d9\u05d9\u05d3", "\u05de\u05e1\u05e4\u05e8 \u05d4\u05d8\u05dc\u05e4\u05d5\u05df"]),
        ("email", "user", 5, ["email", "e-mail", "mail address", "\u05d0\u05d9\u05de\u05d9\u05d9\u05dc", "\u05de\u05d9\u05d9\u05dc", "\u05d3\u05d5\u05d0\u05dc"]),
        ("identity", "user", 5, ["my name is", "call me", "i am called", "\u05e7\u05d5\u05e8\u05d0\u05d9\u05dd \u05dc\u05d9", "\u05e9\u05de\u05d9", "\u05ea\u05e7\u05e8\u05d0 \u05dc\u05d9"]),
        ("birthday", "user", 5, ["birthday", "date of birth", "i was born", "\u05d9\u05d5\u05dd \u05d4\u05d5\u05dc\u05d3\u05ea", "\u05ea\u05d0\u05e8\u05d9\u05da \u05dc\u05d9\u05d3\u05d4", "\u05e0\u05d5\u05dc\u05d3\u05ea\u05d9"]),
        ("family", "user", 4, ["my wife", "my husband", "my son", "my daughter", "my mother", "my father",
                              "\u05d0\u05e9\u05ea\u05d9", "\u05d1\u05e2\u05dc\u05d9", "\u05d4\u05d1\u05df \u05e9\u05dc\u05d9", "\u05d4\u05d1\u05ea \u05e9\u05dc\u05d9", "\u05d0\u05de\u05d0 \u05e9\u05dc\u05d9", "\u05d0\u05d1\u05d0 \u05e9\u05dc\u05d9"]),
        ("health", "user", 5, ["allergy", "allergic", "medication", "medical", "\u05d0\u05dc\u05e8\u05d2", "\u05ea\u05e8\u05d5\u05e4\u05d4", "\u05e8\u05e4\u05d5\u05d0\u05d9"]),
        ("work", "long_term", 4, ["i work at", "i work for", "i work as", "my job", "my company", "my employer", "\u05d0\u05e0\u05d9 \u05e2\u05d5\u05d1\u05d3 \u05d1", "\u05d0\u05e0\u05d9 \u05e2\u05d5\u05d1\u05d3\u05ea \u05d1", "\u05de\u05e7\u05d5\u05dd \u05d4\u05e2\u05d1\u05d5\u05d3\u05d4 \u05e9\u05dc\u05d9", "\u05d4\u05de\u05e2\u05e1\u05d9\u05e7 \u05e9\u05dc\u05d9", "\u05d4\u05d7\u05d1\u05e8\u05d4 \u05e9\u05dc\u05d9"]),
        ("preference", "user", 4, ["i prefer", "i like", "i don't like", "always use", "never use",
                                  "\u05d0\u05e0\u05d9 \u05de\u05e2\u05d3\u05d9\u05e3", "\u05d0\u05e0\u05d9 \u05de\u05e2\u05d3\u05d9\u05e4\u05d4", "\u05d0\u05e0\u05d9 \u05d0\u05d5\u05d4\u05d1", "\u05ea\u05de\u05d9\u05d3", "\u05d0\u05e3 \u05e4\u05e2\u05dd"]),
    ]
    CRITICAL_CATEGORY_LABELS = {
        "address": "כתובת המשתמש",
        "phone": "טלפון המשתמש",
        "email": "דוא״ל המשתמש",
        "identity": "פרטי זהות של המשתמש",
        "birthday": "יום ההולדת של המשתמש",
        "family": "פרט משפחתי של המשתמש",
        "health": "מידע בריאותי של המשתמש",
        "work": "פרט תעסוקתי של המשתמש",
        "preference": "העדפת המשתמש",
    }

    def __init__(self, core, path=MEMORY_FILE):
        self.core = core
        self.path = path
        self.export_path = MEMORY_EXPORT_FILE if os.path.abspath(path) == os.path.abspath(MEMORY_FILE) else os.path.splitext(path)[0] + ".md"
        self._lock = threading.RLock()
        self._session_entries = []
        self._undo_stack = []
        self.data = self._load()
        self._migrate_legacy_user_memory()
        self._migrate_privacy_model()
        self._migrate_automatic_use_model()
        self._migrate_user_work_artifacts()
        self._migrate_profile_eligibility()
        self.prune_expired()
        self.backfill_critical_user_details()

    def _settings(self):
        cfg = self.core.settings.setdefault("memory", {})
        defaults = DEFAULT_SETTINGS.get("memory", {})
        for key, value in defaults.items():
            cfg.setdefault(key, copy.deepcopy(value))
        return cfg

    def _load(self):
        if not os.path.exists(self.path):
            return {"schema_version": self.SCHEMA_VERSION, "entries": [], "archive": [], "pending": [], "stats": {}}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("memory root must be an object")
            loaded.setdefault("schema_version", self.SCHEMA_VERSION)
            loaded.setdefault("entries", [])
            loaded.setdefault("archive", [])
            loaded.setdefault("pending", [])
            loaded.setdefault("stats", {})
            if not isinstance(loaded["entries"], list):
                loaded["entries"] = []
            if not isinstance(loaded["archive"], list):
                loaded["archive"] = []
            if not isinstance(loaded["pending"], list):
                loaded["pending"] = []
            loaded["schema_version"] = self.SCHEMA_VERSION
            return loaded
        except Exception as e:
            logging.error(f"Memory load failed; starting empty: {e}")
            return {
                "schema_version": self.SCHEMA_VERSION,
                "entries": [],
                "archive": [],
                "pending": [],
                "stats": {"load_error": str(e)},
            }

    def _save(self):
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.path}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            last_error = None
            for attempt in range(5):
                try:
                    os.replace(tmp_path, self.path)
                    last_error = None
                    break
                except PermissionError as e:
                    last_error = e
                    time.sleep(0.025 * (attempt + 1))
            if last_error is not None:
                raise last_error
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
        self._export_markdown_safe()

    def _export_markdown(self):
        try:
            now = datetime.now()
            rows = [
                "# Smarti Memory",
                "",
                "Human-readable export of smarti_memory.json. Edit through Smarti when possible.",
                "",
            ]
            active = [e for e in self.data.get("entries", []) if not self._is_expired(e, now)]
            for memory_type in ["user", "long_term", "short_term", "tool"]:
                items = [e for e in active if e.get("type") == memory_type]
                if not items:
                    continue
                rows.append(f"## {memory_type}")
                for entry in sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True):
                    expires = entry.get("expires_at") or "never"
                    subject = entry.get("subject") or "memory"
                    rows.append(f"- `{entry.get('id')}` | importance={entry.get('importance', 3)} | expires={expires} | {subject}")
                    rows.append(f"  {self._markdown_content(entry)}")
                rows.append("")
            archived = [
                entry for entry in self.data.get("archive", [])
                if isinstance(entry, dict)
            ]
            if archived:
                rows.extend(["## archive", ""])
                for entry in archived:
                    rows.append(
                        f"- `{entry.get('id')}` | type={entry.get('type')} | "
                        f"archived={entry.get('archived_at') or 'unknown'} | "
                        f"reason={entry.get('archive_reason') or 'unknown'}"
                    )
                    rows.append(f"  {self._markdown_content(entry)}")
                rows.append("")
            with open(self.export_path, "w", encoding="utf-8") as f:
                f.write("\n".join(rows).strip() + "\n")
        except Exception as e:
            logging.warning(f"Memory markdown export failed: {e}")

    def _export_markdown_safe(self):
        """Write the convenience Markdown view without sensitive plaintext."""
        try:
            now = datetime.now()
            rows = [
                "# Smarti Memory",
                "",
                "Human-readable export of smarti_memory.json. Edit through Smarti when possible.",
                "",
            ]
            active = [e for e in self.data.get("entries", []) if not self._is_expired(e, now)]
            for memory_type in ["user", "long_term", "short_term", "tool"]:
                items = [e for e in active if e.get("type") == memory_type]
                if not items:
                    continue
                rows.append(f"## {memory_type}")
                for entry in sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True):
                    expires = entry.get("expires_at") or "never"
                    subject = entry.get("subject") or "memory"
                    rows.append(
                        f"- `{entry.get('id')}` | importance={entry.get('importance', 3)} | "
                        f"expires={expires} | {subject}"
                    )
                    rows.append(f"  {self._markdown_content(entry)}")
                rows.append("")
            archived = [entry for entry in self.data.get("archive", []) if isinstance(entry, dict)]
            if archived:
                rows.extend(["## archive", ""])
                for entry in archived:
                    rows.append(
                        f"- `{entry.get('id')}` | type={entry.get('type')} | "
                        f"archived={entry.get('archived_at') or 'unknown'} | "
                        f"reason={entry.get('archive_reason') or 'unknown'}"
                    )
                    rows.append(f"  {self._markdown_content(entry)}")
                rows.append("")
            pending = [entry for entry in self.data.get("pending", []) if isinstance(entry, dict)]
            if pending:
                rows.extend(["## pending review", ""])
                for entry in pending:
                    rows.append(
                        f"- `{entry.get('id')}` | category={entry.get('category') or 'unknown'} | "
                        f"sensitivity={entry.get('sensitivity') or 'ordinary'} | "
                        f"captured={entry.get('created_at') or 'unknown'}"
                    )
                    rows.append("  [Pending user review; content omitted from Markdown export.]")
                rows.append("")
            with open(self.export_path, "w", encoding="utf-8") as f:
                f.write("\n".join(rows).strip() + "\n")
        except Exception as e:
            logging.warning(f"Memory safe markdown export failed: {e}")

    def _entry_metadata(self, entry):
        metadata = entry.get("metadata") if isinstance(entry, dict) else None
        return metadata if isinstance(metadata, dict) else {}

    def _entry_category(self, entry):
        metadata = self._entry_metadata(entry)
        return str(entry.get("category") or metadata.get("category") or "general").strip().lower()

    def _entry_sensitivity(self, entry):
        metadata = self._entry_metadata(entry)
        explicit = str(entry.get("sensitivity") or metadata.get("sensitivity") or "").strip().lower()
        if explicit in {"ordinary", "sensitive"}:
            return explicit
        if metadata.get("sensitive") or self._entry_category(entry) in self.SENSITIVE_CATEGORIES:
            return "sensitive"
        return "ordinary"

    def _plain_content(self, entry):
        content = str((entry or {}).get("content") or "")
        metadata = self._entry_metadata(entry or {})
        if metadata.get("encrypted") or content.startswith(SECRET_PREFIX):
            return dpapi_unprotect_text(content)
        return content

    def _protect_content(self, content):
        protected = dpapi_protect_text(str(content or ""))
        if not protected:
            raise RuntimeError("Sensitive memory could not be protected with Windows DPAPI.")
        return protected

    def _mask_sensitive_content(self, content, category=""):
        text = re.sub(r"\s+", " ", str(content or "")).strip()
        category = str(category or "").lower()
        if category == "email":
            match = re.search(r"([\w.+-])[^\s@]*@([\w.-]+)", text)
            if match:
                return f"{match.group(1)}••••@{match.group(2)}"
        if category == "phone":
            digits = re.sub(r"\D", "", text)
            if digits:
                return f"••••••{digits[-4:]}"
        return "מידע רגיש מוגן ••••"

    def _markdown_content(self, entry):
        if self._entry_sensitivity(entry) == "sensitive":
            return "[Sensitive memory protected; plaintext omitted.]"
        return re.sub(r"\s+", " ", self._plain_content(entry)).strip()

    def _public_entry(self, entry, *, reveal_sensitive=False, user_authorized=False):
        item = copy.deepcopy(entry or {})
        category = self._entry_category(item)
        sensitivity = self._entry_sensitivity(item)
        plain = self._plain_content(item)
        item["category"] = category
        item["sensitivity"] = sensitivity
        item["version"] = int(item.get("version", 1) or 1)
        # Stored memories are always eligible for use with the configured model.
        # Sensitive values remain DPAPI-protected at rest and are only retrieved
        # when they are relevant to the current request.
        item["cloud_allowed"] = True
        item["masked"] = sensitivity == "sensitive" and not (reveal_sensitive and user_authorized)
        item["content"] = plain if not item["masked"] else self._mask_sensitive_content(plain, category)
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata.pop("encrypted", None)
        item["metadata"] = metadata
        return item

    def _audit_memory_event(self, event, entry=None, **extra):
        payload = {
            "manager": "memory_manager",
            "event": str(event or ""),
            "memory_id": str((entry or {}).get("id") or extra.pop("memory_id", "")),
            "category": self._entry_category(entry or {}) if entry else str(extra.pop("category", "")),
            "sensitivity": self._entry_sensitivity(entry or {}) if entry else str(extra.pop("sensitivity", "")),
        }
        payload.update({k: v for k, v in extra.items() if k not in {"content", "plaintext"}})
        try:
            logger = getattr(self.core, "audit_logger", None)
            if logger:
                logger.record("memory_management", payload, self.core.settings)
        except Exception:
            pass

    def _now_iso(self):
        return datetime.now().isoformat(timespec="seconds")

    def _parse_dt(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    def classify_content(self, content, category=""):
        """Return deterministic privacy metadata; secrets are never eligible for storage."""
        text = str(content or "")
        low = self._normalize_text_for_search(text)
        category = str(category or "").strip().lower()
        if category in {"general", "unknown"}:
            category = ""
        secret_pattern = re.compile(
            r"(?i)(?:sk-[a-z0-9_-]{12,}|AIza[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{20,}|"
            r"(?:otp|2fa|cvv|password|passcode|api\s*key|access\s*token|refresh\s*token)\s*[:=]\s*\S+|"
            r"(?:credit\s*card|card\s*number|כרטיס\s*אשראי|אשראי)[^\d]{0,30}\d(?:[\d\s-]{10,}\d))"
        )
        secret_value_context = re.search(
            r"(?i)(?:my\s+)?(?:password|passcode|api\s*key|access\s*token|refresh\s*token|otp|2fa|cvv|"
            r"credit\s*card|card\s*number|סיסמ(?:ה|ת)|מפתח\s*api|טוקן|קוד\s*אימות|כרטיס\s*אשראי|אשראי)"
            r"\s*(?:is|הוא|היא|:|=)\s*\S+",
            text,
        )
        if secret_pattern.search(text) or secret_value_context:
            return {
                "category": "authentication_secret",
                "sensitivity": "sensitive",
                "store_allowed": False,
                "reason": "Secrets, authentication values, OTPs and payment credentials are never stored.",
            }
        if not category:
            if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
                category = "email"
            elif re.search(r"(?i)(?:phone|mobile|cell|tel|טלפון|נייד)[^\d+]{0,30}\+?\d[\d\s().-]{6,}\d", text):
                category = "phone"
            else:
                for candidate, _memory_type, _importance, terms in self.CRITICAL_USER_DETAIL_RULES:
                    if candidate in self.SENSITIVE_CATEGORIES and self._contains_any(low, terms):
                        category = candidate
                        break
        category = category or "general"
        sensitivity = "sensitive" if category in self.SENSITIVE_CATEGORIES else "ordinary"
        return {
            "category": category,
            "sensitivity": sensitivity,
            "store_allowed": True,
            "reason": "Sensitive personal detail" if sensitivity == "sensitive" else "Ordinary memory",
        }

    def _migrate_privacy_model(self):
        """Encrypt and quarantine legacy sensitive entries without deleting them."""
        with self._lock:
            stats = self.data.setdefault("stats", {})
            if int(stats.get("privacy_policy_version", 0) or 0) >= self.PRIVACY_POLICY_VERSION:
                return
            pending = self.data.setdefault("pending", [])
            migrated_pending = []
            active = []
            changed = 0
            try:
                for entry in list(self.data.get("entries", [])):
                    if not isinstance(entry, dict):
                        continue
                    plain = self._plain_content(entry)
                    classification = self.classify_content(plain, self._entry_category(entry))
                    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                    entry["metadata"] = metadata
                    entry["category"] = classification["category"]
                    entry["sensitivity"] = classification["sensitivity"]
                    entry["version"] = int(entry.get("version", 1) or 1)
                    entry.setdefault("pinned", False)
                    entry.setdefault("source_conversation_id", str(metadata.get("source_conversation_id") or "")[:120])
                    entry.setdefault("source_message_id", str(metadata.get("source_message_id") or "")[:120])
                    entry.setdefault("cloud_allowed", classification["sensitivity"] != "sensitive")
                    metadata["category"] = classification["category"]
                    metadata["sensitivity"] = classification["sensitivity"]
                    metadata.setdefault("consent_state", "approved" if classification["sensitivity"] == "ordinary" else "pending_review")
                    metadata.setdefault("why_saved", entry.get("source") or "legacy memory")
                    if classification["sensitivity"] == "sensitive":
                        if not str(entry.get("content") or "").startswith(SECRET_PREFIX):
                            entry["content"] = self._protect_content(plain)
                            changed += 1
                        metadata["encrypted"] = True
                        metadata["encryption_version"] = 1
                        metadata["automatic_context_eligible"] = False
                        metadata["profile_eligible"] = False
                        entry["cloud_allowed"] = False
                        entry["pending_kind"] = "privacy_migration"
                        entry["pending_reason"] = (
                            "Existing sensitive memory was protected and removed from active retrieval until reviewed."
                        )
                        migrated_pending.append(entry)
                        changed += 1
                    else:
                        active.append(entry)
                self.data["entries"] = active
                existing_pending_ids = {str(item.get("id")) for item in pending if isinstance(item, dict)}
                pending.extend(item for item in migrated_pending if str(item.get("id")) not in existing_pending_ids)
                for entry in self.data.get("archive", []):
                    if not isinstance(entry, dict):
                        continue
                    plain = self._plain_content(entry)
                    classification = self.classify_content(plain, self._entry_category(entry))
                    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                    entry["metadata"] = metadata
                    entry["category"] = classification["category"]
                    entry["sensitivity"] = classification["sensitivity"]
                    entry["version"] = int(entry.get("version", 1) or 1)
                    entry.setdefault("pinned", False)
                    entry.setdefault("source_conversation_id", str(metadata.get("source_conversation_id") or "")[:120])
                    entry.setdefault("source_message_id", str(metadata.get("source_message_id") or "")[:120])
                    metadata["category"] = classification["category"]
                    metadata["sensitivity"] = classification["sensitivity"]
                    if classification["sensitivity"] == "sensitive":
                        if not str(entry.get("content") or "").startswith(SECRET_PREFIX):
                            entry["content"] = self._protect_content(plain)
                            changed += 1
                        metadata["encrypted"] = True
                        metadata["encryption_version"] = 1
                        entry["cloud_allowed"] = False
                stats["privacy_policy_version"] = self.PRIVACY_POLICY_VERSION
                stats["privacy_migrated_at"] = self._now_iso()
                stats["privacy_pending_review"] = len(migrated_pending)
                self.data["schema_version"] = self.SCHEMA_VERSION
                self._save()
            except Exception as e:
                stats["privacy_migration_error"] = str(e)
                logging.error(f"Memory privacy migration failed safely: {e}")
                raise

    def _migrate_automatic_use_model(self):
        """Remove review gates while retaining local encryption and secret blocking."""
        with self._lock:
            stats = self.data.setdefault("stats", {})
            policy_was_current = (
                int(stats.get("automatic_use_policy_version", 0) or 0)
                >= self.AUTOMATIC_USE_POLICY_VERSION
            )
            changed = 0
            moved = 0
            active = self.data.setdefault("entries", [])
            had_pending = bool(self.data.setdefault("pending", []))
            active_ids = {str(entry.get("id") or "") for entry in active if isinstance(entry, dict)}
            for entry in list(active) + list(self.data.setdefault("archive", [])):
                if not isinstance(entry, dict):
                    continue
                metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                entry["metadata"] = metadata
                if entry.get("cloud_allowed") is not True:
                    entry["cloud_allowed"] = True
                    changed += 1
                if metadata.get("cloud_allowed") is not True:
                    metadata["cloud_allowed"] = True
                    changed += 1
                if metadata.get("consent_state") != "approved":
                    metadata["consent_state"] = "approved"
                    changed += 1
                entry.pop("pending_kind", None)
                entry.pop("pending_reason", None)

            for pending in list(self.data.setdefault("pending", [])):
                if not isinstance(pending, dict):
                    continue
                entry = copy.deepcopy(pending)
                metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                entry["metadata"] = metadata
                entry["cloud_allowed"] = True
                metadata["cloud_allowed"] = True
                metadata["consent_state"] = "approved"
                metadata["approved_by"] = "automatic_memory_policy"
                metadata["approved_at"] = self._now_iso()
                entry.pop("pending_kind", None)
                entry.pop("pending_reason", None)
                memory_id = str(entry.get("id") or "")
                if not memory_id or memory_id not in active_ids:
                    active.append(entry)
                    if memory_id:
                        active_ids.add(memory_id)
                    moved += 1
            self.data["pending"] = []
            stats["pending_captures"] = 0
            if not policy_was_current or changed or moved or had_pending:
                stats["automatic_use_policy_version"] = self.AUTOMATIC_USE_POLICY_VERSION
                stats["automatic_use_migrated_at"] = self._now_iso()
                stats["automatic_use_moved_from_pending"] = moved
                stats["automatic_use_updated_entries"] = changed
            memory_cfg = self._settings()
            settings_changed = (
                memory_cfg.get("store_sensitive_personal_details") is not True
                or memory_cfg.get("sensitive_category_consent") != {
                    "address": True, "phone": True, "email": True, "health": True,
                }
                or memory_cfg.get("health_memory_mode") != "persistent"
                or memory_cfg.get("sensitive_memory_cloud_default") is not True
            )
            memory_cfg["store_sensitive_personal_details"] = True
            memory_cfg["sensitive_category_consent"] = {
                "address": True, "phone": True, "email": True, "health": True,
            }
            memory_cfg["health_memory_mode"] = "persistent"
            memory_cfg["sensitive_memory_cloud_default"] = True
            if settings_changed:
                try:
                    self.core._save_settings()
                except Exception:
                    pass
            if not policy_was_current or changed or moved or had_pending:
                self._save()

    @staticmethod
    def _strip_user_work_artifact(text):
        return re.sub(
            r"\bUser\s+work\b\s*:?\s*",
            "",
            str(text or ""),
            flags=re.IGNORECASE,
        ).strip()

    def _migrate_user_work_artifacts(self):
        """Remove the old recursive English marker from generated stored records."""
        with self._lock:
            stats = self.data.setdefault("stats", {})
            if int(stats.get("user_work_cleanup_version", 0) or 0) >= self.USER_WORK_CLEANUP_VERSION:
                return
            changed = 0
            for collection in (self.data.get("entries", []), self.data.get("archive", []), self.data.get("pending", [])):
                for entry in collection:
                    if not isinstance(entry, dict):
                        continue
                    subject = str(entry.get("subject") or "")
                    plain = self._plain_content(entry)
                    if not (
                        re.search(r"\bUser\s+work\b", subject, flags=re.IGNORECASE)
                        or re.search(r"\bUser\s+work\b", plain, flags=re.IGNORECASE)
                    ):
                        continue
                    cleaned_content = self._strip_user_work_artifact(plain)
                    cleaned_subject = self._strip_user_work_artifact(subject)
                    if not cleaned_content:
                        cleaned_content = plain.replace("User work", "").strip()
                    if not cleaned_subject:
                        cleaned_subject = self._derive_subject(cleaned_content)
                    sensitive = self._entry_sensitivity(entry) == "sensitive"
                    entry["content"] = self._protect_content(cleaned_content) if sensitive else cleaned_content
                    entry["subject"] = cleaned_subject[:120]
                    entry["fingerprint"] = hashlib.sha256(
                        f"{entry.get('type')}\0{entry.get('scope')}\0{entry.get('subject', '').lower()}\0{cleaned_content.lower()}".encode("utf-8", "ignore")
                    ).hexdigest()
                    entry["version"] = int(entry.get("version", 1) or 1) + 1
                    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                    metadata["user_work_artifact_removed"] = True
                    entry["metadata"] = metadata
                    changed += 1
            stats["user_work_cleanup_version"] = self.USER_WORK_CLEANUP_VERSION
            stats["user_work_cleanup_at"] = self._now_iso()
            stats["user_work_cleanup_count"] = changed
            self._save()

    def _normalize_type(self, memory_type):
        value = str(memory_type or "long_term").strip().lower().replace("-", "_")
        aliases = {
            "short": "short_term",
            "shortterm": "short_term",
            "long": "long_term",
            "longterm": "long_term",
            "tools": "tool",
            "profile": "user",
            "user_memory": "user",
            "any": "long_term",
        }
        value = aliases.get(value, value)
        return value if value in self.VALID_TYPES else "long_term"

    def _coerce_tags(self, tags):
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,;]\s*", tags) if t.strip()]
        if not isinstance(tags, list):
            return []
        return [safe_filename(str(t), "tag").lower()[:40] for t in tags if str(t).strip()][:12]

    def _normalize_text_for_search(self, text):
        text = unicodedata.normalize("NFKC", str(text or "").lower())
        text = "".join(ch for ch in text if not (0x0591 <= ord(ch) <= 0x05C7))
        text = text.translate(self.HEBREW_FINALS)
        text = re.sub(r"[\"'`´׳״]+", " ", text)
        text = re.sub(r"[\u200e\u200f\u202a-\u202e]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _hebrew_light_stem(self, token):
        token = str(token or "")
        if not re.fullmatch(r"[\u0590-\u05FF]+", token):
            return token
        stem = token
        for prefix in ("\u05db\u05e9", "\u05d5\u05d4", "\u05d1\u05d4", "\u05dc\u05d4", "\u05de\u05d4", "\u05e9\u05d4"):
            if len(stem) >= 6 and stem.startswith(prefix):
                stem = stem[len(prefix):]
                break
        if len(stem) >= 5 and stem[0] in "\u05d5\u05d4\u05d1\u05dc\u05db\u05de":
            stem = stem[1:]
        if len(stem) >= 6 and stem.startswith("\u05e9"):
            stem = stem[1:]
        for suffix in ("\u05d9\u05d5\u05ea", "\u05d9\u05dd", "\u05d5\u05ea", "\u05d9\u05ea", "\u05e0\u05d5", "\u05db\u05dd", "\u05db\u05e0", "\u05d9\u05d4", "\u05d9\u05d5", "\u05d9"):
            if len(stem) - len(suffix) >= 3 and stem.endswith(suffix):
                stem = stem[:-len(suffix)]
                break
        return stem or token

    def _tokenize_list(self, text, *, include_ngrams=True):
        normalized = self._normalize_text_for_search(text)
        raw_tokens = re.findall(r"[a-z0-9_+-]{2,}|[\u0590-\u05FF]{2,}", normalized, flags=re.UNICODE)
        tokens = []
        for token in raw_tokens:
            if token in self.HEBREW_STOPWORDS:
                continue
            tokens.append(token)
            stem = self._hebrew_light_stem(token)
            if stem != token and len(stem) >= 2 and stem not in self.HEBREW_STOPWORDS:
                tokens.append(stem)
            if include_ngrams and re.fullmatch(r"[\u0590-\u05FF]{5,}", token):
                tokens.extend(token[i:i + 4] for i in range(0, max(0, len(token) - 3)))
        return tokens

    def _tokenize(self, text):
        return set(self._tokenize_list(text))

    def _entry_search_text(self, entry):
        memory_type = str(entry.get("type", ""))
        type_terms = {
            "user": "user profile identity preference personal address phone email family health",
            "long_term": "long term durable project preference decision recurring fact",
            "short_term": "recent conversation continuity previous last request",
            "tool": "tool command result observation error status run",
        }.get(memory_type, "")
        metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
        return " ".join([
            str(entry.get("subject", "")),
            self._plain_content(entry),
            " ".join(entry.get("tags", []) or []),
            str(entry.get("tool_name", "")),
            str(metadata.get("category", "")),
            type_terms,
        ])

    def _expanded_query_tokens(self, query):
        normalized_query = self._normalize_text_for_search(query)
        tokens = set(self._tokenize_list(normalized_query))
        compact_query = normalized_query.replace(" ", "")
        for terms in self.SEARCH_EXPANSION_GROUPS.values():
            normalized_terms = {self._normalize_text_for_search(t).replace(" ", "") for t in terms}
            if tokens.intersection(normalized_terms) or any(term and term in compact_query for term in normalized_terms):
                tokens.update(normalized_terms)
                for term in terms:
                    tokens.update(self._tokenize_list(term, include_ngrams=False))
        return {t for t in tokens if len(t) >= 2}

    def _query_intent(self, query):
        normalized_query = self._normalize_text_for_search(query)
        compact_query = normalized_query.replace(" ", "")
        tokens = self._expanded_query_tokens(query)
        intent = {
            "profile": False,
            "preference": False,
            "tool": False,
            "continuity": False,
            "project": False,
            "live": self._looks_live_or_temporal(query),
        }
        group_hits = {}
        for group, terms in self.SEARCH_EXPANSION_GROUPS.items():
            normalized_terms = {self._normalize_text_for_search(t).replace(" ", "") for t in terms}
            group_hits[group] = bool(tokens.intersection(normalized_terms) or any(term and term in compact_query for term in normalized_terms))
        intent["profile"] = group_hits.get("identity") or group_hits.get("address") or bool(re.search(r"\b(my|me|about me|who am i)\b", normalized_query))
        intent["preference"] = group_hits.get("preference")
        intent["tool"] = group_hits.get("tool")
        intent["continuity"] = group_hits.get("continuity")
        intent["project"] = group_hits.get("project")
        return intent

    def _memory_type_boost(self, memory_type, intent, *, has_match):
        boost = 0.0
        if memory_type == "user":
            boost += 3.5 if (intent.get("profile") or intent.get("preference")) else 0.4
        elif memory_type == "tool":
            boost += 2.6 if intent.get("tool") else (-1.0 if not has_match else 0.0)
        elif memory_type == "short_term":
            boost += 2.0 if intent.get("continuity") else 0.2
        elif memory_type == "long_term":
            boost += 1.6 if (intent.get("project") or intent.get("preference")) else 0.6
        return boost

    def _looks_live_or_temporal(self, text):
        low = str(text or "").lower()
        return any(term in low for term in self.LIVE_DATA_TERMS)

    def _looks_user_memory(self, text):
        low = str(text or "").lower()
        return any(term in low for term in self.USER_MEMORY_TERMS)

    def _durable_preference_signal(self, text):
        low = self._normalize_text_for_search(text)
        signals = (
            "i prefer", "i like", "i dislike", "from now on", "next time",
            "always use", "never use", "remember that",
            "אני מעדיף", "אני מעדיפה", "אני אוהב", "אני אוהבת",
            "מהיום", "מעכשיו", "בכל פעם", "תמיד", "אף פעם",
            "להבא", "תזכור ש", "זכור ש",
        )
        return any(self._normalize_text_for_search(signal) in low for signal in signals)

    def _looks_one_time_action_request(self, text):
        low = self._normalize_text_for_search(text)
        action_terms = (
            "check now", "fix now", "open now", "send now", "search now",
            "please check", "please fix", "please open", "please send",
            "write", "create", "save", "generate", "download", "install", "run", "build",
            "תבדוק", "שתבדוק", "בדוק עכשיו", "תקן", "שתתקן",
            "פתח", "שתפתח", "שלח", "שתשלח", "חפש", "שתחפש",
            "צור", "שתיצור", "כתוב", "שתכתוב", "שמור", "שתשמור",
            "הורד", "שתוריד", "התקן", "שתתקין", "הרץ", "שתריץ",
            "בנה", "שתבנה", "עדכן", "שתעדכן",
            "תעשה", "שתעשה", "תפעיל", "שתפעיל",
        )
        return any(self._normalize_text_for_search(term) in low for term in action_terms)

    def _automatic_context_eligible(self, entry):
        if not isinstance(entry, dict):
            return False
        metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
        if "automatic_context_eligible" in metadata:
            return bool(metadata.get("automatic_context_eligible"))
        content = str(entry.get("content", "") or "")
        return not self._looks_one_time_action_request(content)

    def _automatic_profile_eligible(self, entry):
        if not isinstance(entry, dict) or entry.get("type") != "user":
            return False
        metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
        category = str(metadata.get("category", "") or "").strip().lower()
        source = str(entry.get("source", "") or "").strip().lower()
        tags = {str(tag or "").strip().lower() for tag in (entry.get("tags") or [])}
        content = str(entry.get("content", "") or "")
        if source in {"manual", "legacy_settings"} or "manual" in tags:
            return True
        if category in {"identity", "address", "phone", "email", "birthday", "family", "health"}:
            return True
        if category == "preference":
            return self._durable_preference_signal(content)
        if "critical" in tags and self._has_user_ownership_signal(content):
            return True
        if source.startswith("critical_") and self._has_user_ownership_signal(content):
            return True
        if source not in {"conversation", "background"} and "auto" not in tags:
            return True
        return False

    def _migrate_profile_eligibility(self):
        """Annotate old memories conservatively; never delete or rewrite content."""
        with self._lock:
            stats = self.data.setdefault("stats", {})
            if int(stats.get("profile_policy_version", 0) or 0) >= self.PROFILE_POLICY_VERSION:
                return
            changed = 0
            for entry in self.data.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                metadata = entry.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                    entry["metadata"] = metadata
                memory_type = str(entry.get("type", "") or "")
                source = str(entry.get("source", "") or "").strip().lower()
                tags = {str(tag or "").strip().lower() for tag in (entry.get("tags") or [])}
                content = str(entry.get("content", "") or "")
                auto_generated = (
                    source in {"conversation", "background", "tool_observation"}
                    or "auto" in tags
                    or memory_type == "tool"
                )
                continuity_only = bool(
                    auto_generated
                    and (
                        memory_type == "tool"
                        or "temporal" in tags
                        or bool(entry.get("volatile"))
                        or self._looks_one_time_action_request(content)
                    )
                )
                context_eligible = not continuity_only
                if metadata.get("automatic_context_eligible") is False:
                    context_eligible = False
                if memory_type == "user":
                    profile_eligible = self._automatic_profile_eligible(entry)
                    if metadata.get("profile_eligible") != bool(profile_eligible):
                        metadata["profile_eligible"] = bool(profile_eligible)
                        changed += 1
                    if not profile_eligible:
                        metadata["profile_review_reason"] = (
                            "Preserved and searchable, but excluded from unconditional profile injection."
                        )
                if metadata.get("automatic_context_eligible") != bool(context_eligible):
                    metadata["automatic_context_eligible"] = bool(context_eligible)
                    changed += 1
                if metadata.get("continuity_only") != continuity_only:
                    metadata["continuity_only"] = continuity_only
                    changed += 1
                metadata.pop("prompt_eligible", None)
                metadata["profile_policy_version"] = self.PROFILE_POLICY_VERSION
                if not context_eligible:
                    metadata["context_review_reason"] = (
                        "Preserved for explicit search and continuity requests, but excluded from "
                        "unconditional context because it is an old action or conversation trace."
                    )
            stats["profile_policy_version"] = self.PROFILE_POLICY_VERSION
            stats["profile_policy_migrated_at"] = self._now_iso()
            stats["profile_policy_annotated"] = changed
            self._save()

    def _contains_any(self, text, terms):
        low = str(text or "").lower()
        return any(str(term).lower() in low for term in terms)

    def _has_user_ownership_signal(self, text):
        low = str(text or "").lower()
        if re.search(r"\b(my|mine|me|i|i'm|i am)\b", low):
            return True
        return bool(re.search(
            r"(^|\s)(\u05d0\u05e0\u05d9|\u05e9\u05dc\u05d9|\u05dc\u05d9|\u05d0\u05e6\u05dc\u05d9|\u05d2\u05e8|\u05d2\u05e8\u05d4|\u05de\u05ea\u05d2\u05d5\u05e8\u05e8|\u05de\u05ea\u05d2\u05d5\u05e8\u05e8\u05ea)(\s|$)",
            low,
        ))

    def _address_has_value(self, text):
        low = str(text or "").lower()
        if self._contains_any(low, [
            "street", "address is", "i live at",
            "\u05e8\u05d7\u05d5\u05d1", "\u05de\u05d9\u05e7\u05d5\u05d3", "\u05d3\u05d9\u05e8\u05d4",
            "\u05db\u05ea\u05d5\u05d1\u05ea \u05d4\u05de\u05d2\u05d5\u05e8\u05d9\u05dd"
        ]):
            return True
        if re.search(r"\bi live in\s+\S+", low):
            return True
        if re.search(r"(\u05d0\u05e0\u05d9\s+\u05d2\u05e8\u05d4?|\u05d0\u05e0\u05d9\s+\u05de\u05ea\u05d2\u05d5\u05e8\u05e8(?:\u05ea)?)\s+\u05d1[\w\u0590-\u05FF-]+", low):
            return not self._contains_any(low, ["where do i live", "\u05d0\u05d9\u05e4\u05d4 \u05d0\u05e0\u05d9 \u05d2\u05e8", "\u05d0\u05d9\u05da \u05d0\u05ea\u05d4 \u05d9\u05d5\u05d3\u05e2"])
        return False

    def _work_has_value(self, text):
        """Require an actual first-person employment fact, not a loose word match."""
        low = self._normalize_text_for_search(text)
        return bool(re.search(
            r"(?:\bi\s+work\s+(?:at|for|as)\s+\S+|"
            r"\bmy\s+(?:job|company|employer)\s+(?:is|at)\s+\S+|"
            r"(?:אני\s+עובד(?:ת)?\s+ב|מקום\s+העבודה\s+שלי\s+הוא|"
            r"המעסיק\s+שלי\s+הוא|החברה\s+שלי\s+היא)\s*\S+)",
            low,
        ))

    def _split_memory_candidate_spans(self, text):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not text:
            return []
        parts = re.split(r"(?<=[.!?؟])\s+|[\r\n]+", text)
        spans = []
        for part in parts:
            part = part.strip(" \t-–—:;,.!?؟")
            if not part:
                continue
            if len(part) <= 520:
                spans.append(part)
            else:
                spans.append(part[:520].rstrip() + "...")
        if text and text not in spans and len(text) <= 900:
            spans.append(text)
        return spans[:12]

    def _extract_regex_personal_details(self, text):
        details = []
        raw = str(text or "")
        for match in re.finditer(r"[\w.\-+%]+@[\w.\-]+\.[A-Za-z]{2,}", raw):
            context = raw[max(0, match.start() - 90):match.end() + 40]
            if not self._has_user_ownership_signal(context):
                continue
            details.append(("email", "user", 5, f"דוא״ל המשתמש: {match.group(0)}"))
        phone_context_re = re.compile(
            r"(?i)(?:phone|mobile|cell|tel|\u05d8\u05dc\u05e4\u05d5\u05df|\u05e0\u05d9\u05d9\u05d3)[^\d+]{0,30}(\+?\d[\d\s().-]{6,}\d)"
        )
        for match in phone_context_re.finditer(raw):
            context = raw[max(0, match.start() - 90):match.end() + 40]
            if not self._has_user_ownership_signal(context):
                continue
            details.append(("phone", "user", 5, f"טלפון המשתמש: {match.group(1).strip()}"))
        return details

    def extract_critical_user_memories(self, user_text):
        cfg = self._settings()
        if not cfg.get("capture_critical_user_details", True):
            return []
        text = str(user_text or "").strip()
        if not text or self._contains_any(text, self.DO_NOT_REMEMBER_TERMS):
            return []
        candidates = []
        max_chars = int(cfg.get("critical_capture_max_chars", 1800) or 1800)
        for category, memory_type, importance, terms in self.CRITICAL_USER_DETAIL_RULES:
            if category in {"phone", "email"}:
                continue
            for span in self._split_memory_candidate_spans(text):
                if not self._contains_any(span, terms):
                    continue
                if category in {"address", "phone", "email", "birthday", "health"} and not self._has_user_ownership_signal(span):
                    continue
                if category == "preference" and not self._durable_preference_signal(span):
                    continue
                if category == "address" and not self._address_has_value(span):
                    continue
                if category == "work" and not self._work_has_value(span):
                    continue
                if self._contains_any(span, self.SECRET_DETAIL_TERMS):
                    continue
                label = self.CRITICAL_CATEGORY_LABELS.get(category, "פרט על המשתמש")
                content = f"{label}: {span[:max_chars]}"
                candidates.append({
                    "memory_type": memory_type,
                    "content": content,
                    "subject": label,
                    "tags": ["auto", "critical", category],
                    "importance": importance,
                    "category": category,
                    "sensitive": category in {"address", "phone", "email", "health"},
                    "profile_eligible": (
                        category != "preference"
                        or self._durable_preference_signal(span)
                    ),
                    "automatic_context_eligible": True,
                })
                break
        for category, memory_type, importance, content in self._extract_regex_personal_details(text):
            if self._contains_any(content, self.SECRET_DETAIL_TERMS):
                continue
            candidates.append({
                "memory_type": memory_type,
                "content": content[:max_chars],
                "subject": self.CRITICAL_CATEGORY_LABELS.get(category, "פרט על המשתמש"),
                "tags": ["auto", "critical", category],
                "importance": importance,
                "category": category,
                "sensitive": True,
                "profile_eligible": True,
                "automatic_context_eligible": True,
            })
        deduped = []
        seen = set()
        for item in candidates:
            key = (item["category"], re.sub(r"\s+", " ", item["content"].lower()))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:10]

    def queue_pending_capture(self, memory_type, content, *, subject="", tags=None,
                              importance=3, source="capture", category="", confidence=0.75,
                              metadata=None):
        # Compatibility entry point for older callers. Captures are stored
        # immediately; there is no user-review queue in the current model.
        return self.add(
            memory_type,
            content,
            subject=subject,
            tags=tags,
            importance=importance,
            source=source,
            category=category,
            confidence=confidence,
            metadata=metadata,
            consent_state="approved",
            cloud_allowed=True,
            storage_mode="persistent",
        )

    def capture_critical_user_details(self, user_text, source="critical_preflight"):
        added = []
        for item in self.extract_critical_user_memories(user_text):
            category = item["category"]
            common = {
                "subject": item["subject"],
                "tags": item["tags"],
                "importance": item["importance"],
                "source": source,
                "confidence": 0.88,
                "category": category,
                "metadata": {
                    "category": category,
                    "sensitive": bool(item.get("sensitive", False)),
                    "capture": "deterministic_preflight",
                    "profile_eligible": bool(item.get("profile_eligible", True)),
                    "automatic_context_eligible": bool(item.get("automatic_context_eligible", True)),
                    "profile_policy_version": self.PROFILE_POLICY_VERSION,
                    "why_saved": "Detected as a reusable personal detail from the user's message.",
                },
            }
            entry_id = self.add(
                item["memory_type"],
                item["content"],
                volatile=False,
                consent_state="approved",
                cloud_allowed=True,
                storage_mode="persistent",
                **common,
            )
            if entry_id:
                added.append(entry_id)
        if added:
            logging.info(f"MEMORY | critical_capture | added_or_refreshed={len(added)}")
        return added

    def backfill_critical_user_details(self):
        cfg = self._settings()
        if not cfg.get("capture_critical_user_details", True):
            return []
        stats = self.data.setdefault("stats", {})
        if int(stats.get("critical_backfill_version", 0) or 0) >= self.PROFILE_POLICY_VERSION:
            return []
        added = []
        for entry in list(self.data.get("entries", [])):
            if entry.get("type") not in {"short_term", "long_term"}:
                continue
            metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
            source = str(entry.get("source") or "").strip().lower()
            tags = {str(tag or "").strip().lower() for tag in (entry.get("tags") or [])}
            # Never feed a memory produced by this backfill into the next
            # policy migration. Older versions did so after each policy bump,
            # producing chains such as "User work: User work ...".
            if (
                metadata.get("capture") == "deterministic_preflight"
                or source in {"critical_preflight", "critical_backfill"}
                or "critical" in tags
            ):
                continue
            content = self._plain_content(entry)
            match = re.search(r"User request:\s*(.*?)(?:\s+Outcome:|$)", content, flags=re.DOTALL)
            text = match.group(1).strip() if match else " ".join(str(entry.get(key, "")) for key in ("subject", "content"))
            added.extend(self.capture_critical_user_details(text, source="critical_backfill"))
        stats["critical_backfill_version"] = self.PROFILE_POLICY_VERSION
        stats["critical_backfill_last_count"] = len(added)
        stats["critical_backfill_last_at"] = self._now_iso()
        try:
            self._save()
        except Exception:
            pass
        return added

    def _is_expired(self, entry, now=None):
        now = now or datetime.now()
        expires = self._parse_dt(entry.get("expires_at"))
        return bool(expires and expires <= now)

    def _ttl_for_type(self, memory_type, source=None):
        cfg = self._settings()
        if memory_type == "short_term":
            return float(cfg.get("short_term_default_ttl_hours", 12) or 12)
        if memory_type == "tool":
            return float(cfg.get("tool_memory_ttl_hours", 72) or 72)
        if source == "conversation":
            return float(cfg.get("conversation_ttl_hours", 168) or 168)
        return None

    def prune_expired(self):
        with self._lock:
            now = datetime.now()
            active = []
            archived = []
            for entry in self.data.get("entries", []):
                if self._is_expired(entry, now):
                    preserved = copy.deepcopy(entry)
                    preserved["archived_at"] = self._now_iso()
                    preserved["archive_reason"] = "expired"
                    archived.append(preserved)
                else:
                    active.append(entry)
            if archived:
                self.data["entries"] = active
                self.data.setdefault("archive", []).extend(archived)
                stats = self.data.setdefault("stats", {})
                stats["expired_archived"] = int(stats.get("expired_archived", 0)) + len(archived)
                stats["last_pruned_at"] = self._now_iso()
                self._save()
            return len(archived)

    def _migrate_legacy_user_memory(self):
        legacy = str(self.core.settings.get("user_memory", "") or "").strip()
        if not legacy or self.core.settings.get("_structured_memory_migrated"):
            return
        self.add(
            "user",
            legacy,
            subject="Legacy user memory",
            tags=["legacy", "user"],
            importance=5,
            source="legacy_settings",
            confidence=0.85,
        )
        self.core.settings["_structured_memory_migrated"] = True
        try:
            self.core._save_settings()
        except Exception:
            pass

    def add(self, memory_type, content, *, subject="", tags=None, ttl_hours=None, importance=3,
            source="manual", confidence=0.75, scope="global", tool_name="", volatile=None,
            metadata=None, category="", consent_state="approved", cloud_allowed=None,
            storage_mode="persistent", entry_id="", pinned=False):
        content = self._strip_user_work_artifact(content)
        if not content:
            return None
        memory_type = self._normalize_type(memory_type)
        metadata = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}
        classification = self.classify_content(content, category or metadata.get("category", ""))
        if not classification.get("store_allowed", True):
            raise ValueError(classification.get("reason") or "This content cannot be stored in memory.")
        category = classification["category"]
        sensitivity = classification["sensitivity"]
        cloud_allowed = True
        consent_state = "approved"
        if ttl_hours is None:
            ttl_hours = self._ttl_for_type(memory_type, source=source)
        try:
            ttl_hours = float(ttl_hours) if ttl_hours not in (None, "") else None
        except Exception:
            ttl_hours = None
        now = datetime.now()
        expires_at = (now + timedelta(hours=ttl_hours)).isoformat(timespec="seconds") if ttl_hours else None
        volatile = self._looks_live_or_temporal(content) if volatile is None else bool(volatile)
        try:
            importance = max(1, min(5, int(float(importance))))
        except Exception:
            importance = 3
        tags = self._coerce_tags(tags)
        subject = self._strip_user_work_artifact(subject)[:120] or self._derive_subject(content)
        fingerprint = hashlib.sha256(
            f"{memory_type}\0{scope}\0{subject.lower()}\0{content.lower()}".encode("utf-8", "ignore")
        ).hexdigest()
        with self._lock:
            target_entries = self._session_entries if storage_mode == "session_only" else self.data.setdefault("entries", [])
            for entry in target_entries:
                if entry.get("fingerprint") == fingerprint:
                    entry["updated_at"] = self._now_iso()
                    entry["expires_at"] = expires_at
                    entry["importance"] = max(int(entry.get("importance", 3)), importance)
                    entry["access_count"] = int(entry.get("access_count", 0)) + 1
                    entry["last_source"] = source
                    entry["tags"] = sorted(set(entry.get("tags", []) or []) | set(tags))[:12]
                    entry["cloud_allowed"] = True
                    if isinstance(metadata, dict) and metadata:
                        existing_metadata = entry.get("metadata")
                        if not isinstance(existing_metadata, dict):
                            existing_metadata = {}
                            entry["metadata"] = existing_metadata
                        existing_metadata.update(copy.deepcopy(metadata))
                        existing_metadata["cloud_allowed"] = True
                        existing_metadata["consent_state"] = "approved"
                    entry["version"] = int(entry.get("version", 1) or 1) + 1
                    if storage_mode != "session_only":
                        self._save()
                    return entry.get("id")
            entry_id = str(entry_id or "").strip() or "mem_" + uuid.uuid4().hex[:12]
            metadata.update({
                "category": category,
                "sensitivity": sensitivity,
                "sensitive": sensitivity == "sensitive",
                "consent_state": consent_state,
                "cloud_allowed": bool(cloud_allowed),
                "encrypted": sensitivity == "sensitive" and storage_mode != "session_only",
                "encryption_version": 1 if sensitivity == "sensitive" and storage_mode != "session_only" else 0,
                "why_saved": metadata.get("why_saved") or source,
            })
            stored_content = (
                self._protect_content(content[:6000])
                if sensitivity == "sensitive" and storage_mode != "session_only"
                else content[:6000]
            )
            entry = {
                "id": entry_id,
                "type": memory_type,
                "scope": scope or "global",
                "subject": subject,
                "content": stored_content,
                "category": category,
                "sensitivity": sensitivity,
                "cloud_allowed": bool(cloud_allowed),
                "pinned": bool(pinned),
                "version": 1,
                "tags": tags,
                "importance": importance,
                "confidence": max(0.0, min(1.0, float(confidence or 0.75))),
                "source": source,
                "tool_name": str(tool_name or "")[:80],
                "volatile": volatile,
                "created_at": now.isoformat(timespec="seconds"),
                "updated_at": now.isoformat(timespec="seconds"),
                "expires_at": expires_at,
                "fingerprint": fingerprint,
                "access_count": 0,
                "source_conversation_id": str(metadata.get("source_conversation_id") or "")[:120],
                "source_message_id": str(metadata.get("source_message_id") or "")[:120],
                "metadata": metadata,
            }
            target_entries.append(entry)
            stats = self.data.setdefault("stats", {})
            stats["total_added"] = int(stats.get("total_added", 0)) + 1
            stats["last_added_at"] = self._now_iso()
            if storage_mode != "session_only":
                self._save()
            self._audit_memory_event("add", entry, storage_mode=storage_mode)
            return entry_id

    def _derive_subject(self, content):
        text = re.sub(r"\s+", " ", str(content or "")).strip()
        return text[:80] + ("..." if len(text) > 80 else "")

    def _locate_entry(self, memory_id):
        memory_id = str(memory_id or "").strip()
        collections = (
            ("active", self.data.setdefault("entries", [])),
            ("archive", self.data.setdefault("archive", [])),
            ("session", self._session_entries),
            ("pending", self.data.setdefault("pending", [])),
        )
        for status, entries in collections:
            for index, entry in enumerate(entries):
                if str(entry.get("id") or "") == memory_id:
                    return status, entries, index, entry
        return None, None, None, None

    def list_entries(self, *, query="", memory_type="any", status="active", category="",
                     sensitivity="any", source="", date_range="any", expiry="any",
                     max_results=200, sort_by="updated_desc",
                     reveal_sensitive=False, user_authorized=False):
        self.prune_expired()
        statuses = {str(status or "active").strip().lower()}
        if "all" in statuses:
            statuses = {"active", "archive", "session", "pending"}
        collections = {
            "active": self.data.get("entries", []),
            "archive": self.data.get("archive", []),
            "session": self._session_entries,
            "pending": self.data.get("pending", []),
        }
        normalized_query = self._normalize_text_for_search(query)
        normalized_source = str(source or "").strip().lower()
        normalized_category = str(category or "").strip().lower()
        normalized_sensitivity = str(sensitivity or "any").strip().lower()
        normalized_type = str(memory_type or "any").strip().lower()
        normalized_date_range = str(date_range or "any").strip().lower()
        normalized_expiry = str(expiry or "any").strip().lower()
        date_days = {"7d": 7, "30d": 30, "90d": 90}.get(normalized_date_range)
        now = datetime.now()
        rows = []
        with self._lock:
            for item_status in statuses:
                for entry in list(collections.get(item_status, [])):
                    if normalized_type not in {"", "any"} and entry.get("type") != self._normalize_type(normalized_type):
                        continue
                    if normalized_category and self._entry_category(entry) != normalized_category:
                        continue
                    if normalized_sensitivity not in {"", "any"} and self._entry_sensitivity(entry) != normalized_sensitivity:
                        continue
                    if normalized_source and normalized_source not in str(entry.get("source") or "").lower():
                        continue
                    updated = self._parse_dt(entry.get("updated_at")) or self._parse_dt(entry.get("created_at"))
                    if date_days and updated and updated < now - timedelta(days=date_days):
                        continue
                    expires = self._parse_dt(entry.get("expires_at"))
                    if normalized_expiry == "never" and expires is not None:
                        continue
                    if normalized_expiry == "expiring" and (
                        expires is None or expires < now or expires > now + timedelta(days=7)
                    ):
                        continue
                    if normalized_expiry == "expired" and not (
                        entry.get("archive_reason") == "expired" or (expires is not None and expires <= now)
                    ):
                        continue
                    if normalized_query:
                        haystack = self._normalize_text_for_search(
                            " ".join((
                                str(entry.get("subject") or ""),
                                self._plain_content(entry),
                                " ".join(entry.get("tags") or []),
                                self._entry_category(entry),
                                str(entry.get("source") or ""),
                            ))
                        )
                        if normalized_query not in haystack and not self._tokenize(normalized_query).intersection(self._tokenize(haystack)):
                            continue
                    public = self._public_entry(
                        entry,
                        reveal_sensitive=reveal_sensitive,
                        user_authorized=user_authorized,
                    )
                    public["status"] = item_status
                    rows.append(public)
        reverse = not str(sort_by or "updated_desc").endswith("_asc")
        field = "importance" if str(sort_by).startswith("importance") else (
            "created_at" if str(sort_by).startswith("created") else "updated_at"
        )
        rows.sort(key=lambda item: item.get(field, 0) or 0, reverse=reverse)
        rows.sort(key=lambda item: bool(item.get("pinned", False)), reverse=True)
        try:
            limit = max(1, min(1000, int(max_results or 200)))
        except Exception:
            limit = 200
        return rows[:limit]

    def get_entry(self, memory_id, *, reveal_sensitive=False, user_authorized=False):
        with self._lock:
            status, _entries, _index, entry = self._locate_entry(memory_id)
            if not entry:
                return None
            public = self._public_entry(
                entry,
                reveal_sensitive=reveal_sensitive,
                user_authorized=user_authorized,
            )
            public["status"] = status
            return public

    def edit_entry(self, memory_id, *, expected_version=None, user_authorized=False, **changes):
        with self._lock:
            status, entries, index, entry = self._locate_entry(memory_id)
            if not entry or status == "pending":
                raise KeyError("memory_id not found or is pending review")
            current_version = int(entry.get("version", 1) or 1)
            if expected_version not in (None, "") and int(expected_version) != current_version:
                raise RuntimeError(
                    f"Memory changed concurrently (expected version {expected_version}, current {current_version})."
                )
            before = copy.deepcopy(entry)
            content = self._strip_user_work_artifact(
                changes.get("content", self._plain_content(entry))
            )
            if not content:
                raise ValueError("Memory content cannot be empty.")
            category = str(changes.get("category", self._entry_category(entry)) or "").strip().lower()
            classification = self.classify_content(content, category)
            if not classification.get("store_allowed", True):
                raise ValueError(classification.get("reason") or "This content cannot be stored.")
            if classification["sensitivity"] == "sensitive" and not user_authorized:
                raise PermissionError("Only the user-facing memory page may edit sensitive memory.")
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            metadata.update({
                "category": classification["category"],
                "sensitivity": classification["sensitivity"],
                "sensitive": classification["sensitivity"] == "sensitive",
                "encrypted": classification["sensitivity"] == "sensitive" and status != "session",
                "encryption_version": 1 if classification["sensitivity"] == "sensitive" and status != "session" else 0,
            })
            entry["metadata"] = metadata
            entry["content"] = (
                self._protect_content(content[:6000])
                if classification["sensitivity"] == "sensitive" and status != "session"
                else content[:6000]
            )
            entry["category"] = classification["category"]
            entry["sensitivity"] = classification["sensitivity"]
            if "subject" in changes:
                entry["subject"] = self._strip_user_work_artifact(changes.get("subject"))[:120] or self._derive_subject(content)
            if "memory_type" in changes:
                entry["type"] = self._normalize_type(changes.get("memory_type"))
            if "importance" in changes:
                entry["importance"] = max(1, min(5, int(changes.get("importance") or 3)))
            if "tags" in changes:
                entry["tags"] = self._coerce_tags(changes.get("tags"))
            entry["cloud_allowed"] = True
            metadata["cloud_allowed"] = True
            metadata["consent_state"] = "approved"
            if "pinned" in changes:
                entry["pinned"] = bool(changes.get("pinned"))
            if "ttl_hours" in changes:
                ttl = changes.get("ttl_hours")
                entry["expires_at"] = (
                    (datetime.now() + timedelta(hours=float(ttl))).isoformat(timespec="seconds")
                    if ttl not in (None, "", 0, "0") else None
                )
            entry["updated_at"] = self._now_iso()
            entry["version"] = current_version + 1
            entry["fingerprint"] = hashlib.sha256(
                f"{entry.get('type')}\0{entry.get('scope')}\0{entry.get('subject', '').lower()}\0{content.lower()}".encode("utf-8", "ignore")
            ).hexdigest()
            self._undo_stack.append({"action": "edit", "status": status, "entry": before})
            self._undo_stack = self._undo_stack[-20:]
            if status != "session":
                self._save()
            self._audit_memory_event("edit", entry, version=entry["version"])
            return self._public_entry(entry)

    def archive_entry(self, memory_id, reason="manual"):
        with self._lock:
            status, entries, index, entry = self._locate_entry(memory_id)
            if not entry or status not in {"active", "session"}:
                return False
            before = copy.deepcopy(entry)
            archived = entries.pop(index)
            if status == "session" and self._entry_sensitivity(archived) == "sensitive":
                archived["content"] = self._protect_content(self._plain_content(archived))
                archived.setdefault("metadata", {})["encrypted"] = True
            archived["archived_at"] = self._now_iso()
            archived["archive_reason"] = str(reason or "manual")[:120]
            archived["version"] = int(archived.get("version", 1) or 1) + 1
            self.data.setdefault("archive", []).append(archived)
            self._undo_stack.append({"action": "archive", "from_status": status, "entry": before})
            self._undo_stack = self._undo_stack[-20:]
            self._save()
            self._audit_memory_event("archive", archived, reason=archived["archive_reason"])
            return True

    def restore_entry(self, memory_id):
        with self._lock:
            status, entries, index, entry = self._locate_entry(memory_id)
            if not entry or status != "archive":
                return False
            restored = entries.pop(index)
            before = copy.deepcopy(restored)
            restored.pop("archived_at", None)
            restored.pop("archive_reason", None)
            restored["updated_at"] = self._now_iso()
            restored["version"] = int(restored.get("version", 1) or 1) + 1
            self.data.setdefault("entries", []).append(restored)
            self._undo_stack.append({"action": "restore", "entry": before})
            self._undo_stack = self._undo_stack[-20:]
            self._save()
            self._audit_memory_event("restore", restored)
            return True

    def undo_last(self):
        with self._lock:
            if not self._undo_stack:
                return False
            undo = self._undo_stack.pop()
            entry = copy.deepcopy(undo.get("entry") or {})
            memory_id = str(entry.get("id") or "")
            status, entries, index, _current = self._locate_entry(memory_id)
            if entries is not None and index is not None:
                entries.pop(index)
            target_status = undo.get("status") or undo.get("from_status")
            if undo.get("action") == "restore":
                target_status = "archive"
            target = {
                "archive": self.data.setdefault("archive", []),
                "session": self._session_entries,
                "pending": self.data.setdefault("pending", []),
            }.get(target_status, self.data.setdefault("entries", []))
            target.append(entry)
            if target_status != "session":
                self._save()
            self._audit_memory_event("undo", entry, reverted_action=undo.get("action"))
            return True

    def memory_stats(self):
        with self._lock:
            active = list(self.data.get("entries", []))
            archive = list(self.data.get("archive", []))
            pending = list(self.data.get("pending", []))
            all_entries = active + archive + pending + list(self._session_entries)
            by_type = {}
            by_category = {}
            sensitive = 0
            for entry in all_entries:
                by_type[entry.get("type", "unknown")] = by_type.get(entry.get("type", "unknown"), 0) + 1
                category = self._entry_category(entry)
                by_category[category] = by_category.get(category, 0) + 1
                sensitive += self._entry_sensitivity(entry) == "sensitive"
            try:
                storage_bytes = os.path.getsize(self.path) if os.path.exists(self.path) else 0
            except Exception:
                storage_bytes = 0
            return {
                "active": len(active),
                "archive": len(archive),
                "session": len(self._session_entries),
                "pending": len(pending),
                "sensitive": int(sensitive),
                "by_type": by_type,
                "by_category": by_category,
                "storage_bytes": storage_bytes,
                "undo_available": bool(self._undo_stack),
                "stats": copy.deepcopy(self.data.get("stats", {})),
            }

    def export_memory(self, path, *, encrypted=True, include_sensitive=True):
        path = os.path.abspath(str(path or "").strip())
        if not path:
            raise ValueError("Export path is required.")
        payload = {
            "format": "smarti-memory-export-v1",
            "created_at": self._now_iso(),
            "encrypted_sensitive": bool(encrypted),
            "entries": [],
            "archive": [],
            "pending": [],
        }
        with self._lock:
            for key, collection in (
                ("entries", self.data.get("entries", [])),
                ("archive", self.data.get("archive", [])),
                ("pending", self.data.get("pending", [])),
            ):
                for entry in collection:
                    item = copy.deepcopy(entry)
                    if self._entry_sensitivity(item) == "sensitive":
                        if not include_sensitive:
                            continue
                        if encrypted:
                            if not str(item.get("content") or "").startswith(SECRET_PREFIX):
                                item["content"] = self._protect_content(self._plain_content(item))
                                item.setdefault("metadata", {})["encrypted"] = True
                        else:
                            item["content"] = self._mask_sensitive_content(
                                self._plain_content(item), self._entry_category(item)
                            )
                            item["redacted"] = True
                    payload[key].append(item)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        self._audit_memory_event("export", memory_id="", encrypted=bool(encrypted), count=sum(len(payload[k]) for k in ("entries", "archive", "pending")))
        return path

    def import_memory(self, path, *, user_authorized=False):
        path = os.path.abspath(str(path or "").strip())
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict) or payload.get("format") != "smarti-memory-export-v1":
            raise ValueError("Unsupported memory export format.")
        imported = 0
        skipped = 0
        for entry in payload.get("entries", []):
            if not isinstance(entry, dict) or entry.get("redacted"):
                skipped += 1
                continue
            plain = self._plain_content(entry)
            sensitivity = self._entry_sensitivity(entry)
            if sensitivity == "sensitive" and not user_authorized:
                skipped += 1
                continue
            try:
                entry_id = self.add(
                    entry.get("type", "long_term"),
                    plain,
                    subject=entry.get("subject", ""),
                    tags=entry.get("tags", []),
                    importance=entry.get("importance", 3),
                    source="memory_import",
                    confidence=entry.get("confidence", 0.75),
                    category=self._entry_category(entry),
                    consent_state="approved",
                    cloud_allowed=bool(entry.get("cloud_allowed", False)),
                    metadata={**self._entry_metadata(entry), "imported_at": self._now_iso()},
                )
                imported += bool(entry_id)
            except Exception:
                skipped += 1
        self._audit_memory_event("import", memory_id="", imported=int(imported), skipped=int(skipped))
        return {"imported": int(imported), "skipped": int(skipped)}

    def clear(self, memory_type=None):
        memory_type = self._normalize_type(memory_type) if memory_type else None
        with self._lock:
            before = (
                len(self.data.get("entries", []))
                + len(self.data.get("archive", []))
                + len(self.data.get("pending", []))
                + len(self._session_entries)
            )
            if memory_type:
                self.data["entries"] = [e for e in self.data.get("entries", []) if e.get("type") != memory_type]
                self.data["archive"] = [e for e in self.data.get("archive", []) if e.get("type") != memory_type]
                self.data["pending"] = [e for e in self.data.get("pending", []) if e.get("type") != memory_type]
                self._session_entries = [e for e in self._session_entries if e.get("type") != memory_type]
            else:
                self.data["entries"] = []
                self.data["archive"] = []
                self.data["pending"] = []
                self._session_entries = []
            removed = (
                before - len(self.data["entries"]) - len(self.data["archive"])
                - len(self.data["pending"]) - len(self._session_entries)
            )
            stats = self.data.setdefault("stats", {})
            stats["total_cleared"] = int(stats.get("total_cleared", 0)) + removed
            stats["last_cleared_at"] = self._now_iso()
            self._save()
            return removed

    def forget(self, memory_id):
        memory_id = str(memory_id or "").strip()
        if not memory_id:
            return False
        with self._lock:
            status, entries, index, entry = self._locate_entry(memory_id)
            if entry is not None:
                entries.pop(index)
                if status != "session":
                    self._save()
                self._audit_memory_event("forget", entry, previous_status=status)
                return True
            return False

    def _sensitive_entry_relevant(self, query, entry):
        category = self._entry_category(entry)
        normalized = self._normalize_text_for_search(query)
        category_terms = {
            "address": ("address", "street", "where do i live", "כתובת", "רחוב", "איפה אני גר"),
            "phone": ("phone", "mobile", "call me", "טלפון", "נייד", "המספר שלי"),
            "email": ("email", "mail address", "אימייל", "מייל", "דואר אלקטרוני"),
            "health": ("health", "medical", "allergy", "medication", "בריאות", "רפואי", "אלרג", "תרופה"),
        }
        return any(self._normalize_text_for_search(term) in normalized for term in category_terms.get(category, ()))

    def search(self, query, memory_types=None, max_results=None, max_chars=None, *, for_prompt=False):
        started = time.time()
        self.prune_expired()
        cfg = self._settings()
        max_results = int(max_results or cfg.get("max_results", 8) or 8)
        max_chars = int(max_chars or cfg.get("max_injected_chars", 4200) or 4200)
        min_score = float(cfg.get("min_relevance_score", 4.2) or 4.2)
        if isinstance(memory_types, str):
            memory_types = None if memory_types in {"", "any"} else {self._normalize_type(memory_types)}
        elif memory_types:
            memory_types = {self._normalize_type(t) for t in memory_types}
        now = datetime.now()
        q = str(query or "")
        q_tokens = self._expanded_query_tokens(q)
        q_token_count = max(1, len(q_tokens))
        q_normalized = self._normalize_text_for_search(q)
        intent = self._query_intent(q)
        live_query = intent.get("live")
        scored = []
        with self._lock:
            entries = list(self.data.get("entries", [])) + list(self._session_entries)
        prepared = []
        doc_freq = {}
        for entry in entries:
            if self._is_expired(entry, now):
                continue
            if memory_types and entry.get("type") not in memory_types:
                continue
            if self._entry_sensitivity(entry) == "sensitive":
                if for_prompt and not self._sensitive_entry_relevant(q, entry):
                    continue
            haystack = self._entry_search_text(entry)
            tokens = self._tokenize(haystack)
            prepared.append((entry, haystack, tokens))
            for token in tokens:
                doc_freq[token] = doc_freq.get(token, 0) + 1
        doc_count = max(1, len(prepared))
        for entry, haystack, tokens in prepared:
            matched_tokens = q_tokens & tokens
            overlap = len(matched_tokens)
            has_match = bool(overlap)
            if q_tokens and not has_match:
                if not (intent.get("profile") and entry.get("type") == "user"):
                    continue
            if not q_tokens and not (entry.get("type") == "user" and int(entry.get("importance", 3) or 3) >= 4):
                continue
            updated = self._parse_dt(entry.get("updated_at")) or self._parse_dt(entry.get("created_at")) or now
            age_hours = max(0.0, (now - updated).total_seconds() / 3600.0)
            recency = max(0.0, 4.0 - (age_hours / 12.0)) if entry.get("type") in {"short_term", "tool"} else max(0.0, 1.0 - (age_hours / 720.0))
            importance = float(entry.get("importance", 3) or 3)
            confidence = float(entry.get("confidence", 0.75) or 0.75)
            haystack_normalized = self._normalize_text_for_search(haystack)
            exact_bonus = 3.0 if q_normalized and q_normalized in haystack_normalized else 0.0
            weighted_overlap = sum(1.0 + math.log((doc_count + 1.0) / (doc_freq.get(token, 0) + 1.0)) for token in matched_tokens)
            coverage = overlap / q_token_count
            type_bonus = self._memory_type_boost(entry.get("type"), intent, has_match=has_match)
            score = (weighted_overlap * 4.4) + (coverage * 3.2) + recency + importance + confidence + exact_bonus + type_bonus
            if not q_tokens:
                score = importance + recency + type_bonus
            if live_query and entry.get("volatile"):
                score *= 0.35
            if q_tokens and score < min_score:
                continue
            scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        used_chars = 0
        seen = set()
        for score, entry in scored:
            content = self._plain_content(entry)
            if not content.strip():
                continue
            dedupe = hashlib.sha1(content.lower().encode("utf-8", "ignore")).hexdigest()
            if dedupe in seen:
                continue
            seen.add(dedupe)
            formatted = self._format_entry(entry, score, reveal_sensitive=for_prompt)
            if used_chars + len(formatted) > max_chars and results:
                continue
            results.append({"score": score, "entry": entry, "text": formatted})
            used_chars += len(formatted)
            if len(results) >= max_results:
                break
        with self._lock:
            ids = {r["entry"].get("id") for r in results}
            type_counts = {}
            for entry in self.data.get("entries", []):
                if entry.get("id") in ids:
                    entry["access_count"] = int(entry.get("access_count", 0)) + 1
                    entry["last_accessed_at"] = self._now_iso()
                    memory_type = entry.get("type", "unknown")
                    type_counts[memory_type] = type_counts.get(memory_type, 0) + 1
            for entry in self._session_entries:
                if entry.get("id") in ids:
                    entry["access_count"] = int(entry.get("access_count", 0)) + 1
                    entry["last_accessed_at"] = self._now_iso()
            stats = self.data.setdefault("stats", {})
            stats["searches"] = int(stats.get("searches", 0)) + 1
            stats["last_search_at"] = self._now_iso()
            stats["last_retriever"] = self.RETRIEVER_NAME
            stats["last_query_preview"] = q[:180]
            stats["last_results_count"] = len(results)
            stats["last_retrieved_chars"] = used_chars
            stats["last_retrieved_types"] = type_counts
            stats["last_retrieved_ids"] = [r["entry"].get("id") for r in results]
            stats["last_search_ms"] = int((time.time() - started) * 1000)
            self._save()
        return results

    def _format_entry(self, entry, score, *, reveal_sensitive=False):
        created = entry.get("created_at", "?")
        expires = entry.get("expires_at") or "never"
        tags = ", ".join(entry.get("tags", []) or [])
        volatile = " volatile-verify" if entry.get("volatile") else ""
        source = entry.get("source") or "unknown"
        tool = f" tool={entry.get('tool_name')}" if entry.get("tool_name") else ""
        header = (
            f"- id={entry.get('id')} type={entry.get('type')} score={score:.2f}"
            f" importance={entry.get('importance', 3)} source={source}{tool}"
            f" created={created} expires={expires}{volatile}"
        )
        if tags:
            header += f" tags={tags}"
        content = re.sub(r"\s+", " ", self._plain_content(entry).strip())
        if self._entry_sensitivity(entry) == "sensitive" and not reveal_sensitive:
            content = self._mask_sensitive_content(content, self._entry_category(entry))
        if len(content) > 900:
            content = content[:900].rstrip() + "..."
        return f"{header}\n  {content}"

    def _entry_age_hours(self, entry):
        updated = self._parse_dt(entry.get("updated_at")) or self._parse_dt(entry.get("created_at"))
        if not updated:
            return None
        return max(0.0, (datetime.now() - updated).total_seconds() / 3600.0)

    def _tool_memory_relevant_for_prompt(self, query):
        cfg = self._settings()
        if not cfg.get("tool_memory_requires_relevance", True):
            return True
        intent = self._query_intent(query)
        if intent.get("continuity") or intent.get("tool"):
            return True
        q = str(query or "").lower()
        continuity_terms = [
            "continue", "again", "previous", "earlier", "same", "last time", "tool", "result",
            "\u05d4\u05de\u05e9\u05da", "\u05d4\u05e7\u05d5\u05d3\u05dd", "\u05d4\u05e7\u05d5\u05d3\u05de\u05ea",
            "\u05e9\u05d5\u05d1", "\u05d0\u05d5\u05ea\u05d5", "\u05d0\u05d5\u05ea\u05d4", "\u05ea\u05d5\u05e6\u05d0\u05d4",
            "\u05db\u05dc\u05d9", "\u05db\u05dc\u05d9\u05dd",
        ]
        return any(term in q for term in continuity_terms)

    def _join_memory_sections(self, sections, max_chars):
        parts = []
        used = 0
        for title, results in sections:
            if not results:
                continue
            body = "\n".join(r["text"] for r in results)
            block = f"{title}:\n{body}"
            if parts and used + len(block) + 2 > max_chars:
                remaining = max(0, max_chars - used - 80)
                if remaining > 300:
                    parts.append(block[:remaining].rstrip() + "\n[Memory section shortened due to prompt budget.]")
                break
            parts.append(block)
            used += len(block) + 2
        return "\n\n".join(parts)

    def build_prompt_context(self, query="", log_usage=False):
        cfg = self._settings()
        if not cfg.get("enabled", True):
            return "Memory is disabled."
        if not cfg.get("rag_enabled", True):
            return "Memory RAG is disabled. Use search_memory if the user explicitly asks to inspect memory."
        query = str(query or "")
        query_intent = self._query_intent(query)
        explicit_continuity = bool(query_intent.get("continuity"))
        max_chars = int(cfg.get("max_injected_chars", 4200) or 4200)
        seen_ids = set()

        def unique(results):
            unique_results = []
            for result in results or []:
                entry_id = result.get("entry", {}).get("id")
                if entry_id and entry_id in seen_ids:
                    continue
                if entry_id:
                    seen_ids.add(entry_id)
                unique_results.append(result)
            return unique_results

        user_results = []
        if cfg.get("always_include_user_memory", True):
            user_candidates = self.search(
                "",
                memory_types="user",
                max_results=cfg.get("user_memory_max_results", 8),
                max_chars=cfg.get("user_memory_max_injected_chars", 2200),
                for_prompt=True,
            )
            user_results = unique([
                result
                for result in user_candidates
                if (
                    not isinstance(result.get("entry", {}).get("metadata"), dict)
                    or result.get("entry", {}).get("metadata", {}).get("profile_eligible", True)
                )
            ])

        semantic_candidates = self.search(
            query,
            memory_types={"user", "long_term", "short_term"},
            max_results=cfg.get("non_tool_memory_max_results", cfg.get("max_results", 8)),
            max_chars=max(800, max_chars),
            for_prompt=True,
        )
        non_tool_results = unique([
            result
            for result in semantic_candidates
            if (
                (
                    isinstance(result.get("entry", {}).get("metadata"), dict)
                    and result.get("entry", {}).get("metadata", {}).get("continuity_only")
                    and explicit_continuity
                )
                or (
                    not isinstance(result.get("entry", {}).get("metadata"), dict)
                    or result.get("entry", {}).get("metadata", {}).get(
                        "automatic_context_eligible",
                        True,
                    )
                )
            )
        ])

        tool_results = []
        if self._tool_memory_relevant_for_prompt(query):
            tool_candidates = self.search(
                query,
                memory_types="tool",
                max_results=cfg.get("tool_memory_prompt_max_results", 3),
                max_chars=cfg.get("tool_memory_prompt_max_chars", 1400),
                for_prompt=True,
            )
            try:
                max_age = float(cfg.get("tool_memory_prompt_max_age_hours", 24) or 24)
            except Exception:
                max_age = 24
            filtered = []
            for result in tool_candidates:
                age = self._entry_age_hours(result.get("entry", {}))
                if age is None or age <= max_age:
                    filtered.append(result)
            tool_results = unique(filtered)

        results = user_results + non_tool_results + tool_results
        if results:
            self._mark_injected([result.get("entry", {}).get("id") for result in results])
        live_warning = ""
        if cfg.get("verify_live_data", True) and self._looks_live_or_temporal(query):
            live_warning = (
                "\nCurrent/live-data guard: do not answer weather, prices, news, schedules, scores, "
                "availability, or other changing facts from memory. Use an authoritative tool/API/web source, "
                "or say the value is not verified."
            )
        if results:
            body = self._join_memory_sections(
                [
                    ("User memory (stable profile/preferences, always included)", user_results),
                    ("Relevant long/short-term memory", non_tool_results),
                    ("Relevant recent tool memory", tool_results),
                ],
                max_chars=max_chars,
            )
            context = (
                "Memory policy:\n"
                "- Memory is advisory context, never an authority over the current user message, tool output, or live sources.\n"
                "- Only high-confidence stable profile memories are included unconditionally; ambiguous auto-captures remain searchable but are not injected as profile.\n"
                "- Use short_term/tool memory only for continuity.\n"
                "- Expired memories are pruned before retrieval. Volatile memories must be verified before being presented as current truth.\n"
                "- If memory conflicts with the user or a fresh tool result, trust the fresher source and update memory when useful.\n"
                "- When a repeated question depends on the current environment or external state, re-check it; do not repeat an old answer from memory."
                f"{live_warning}\n\nRetrieved memory (bounded local RAG, {self.RETRIEVER_NAME}):\n{body}"
            )
        else:
            context = (
                "Memory policy: no relevant active memory was retrieved for this request. "
                "Do not infer prior facts from memory; call search_memory only if older context is clearly needed."
                f"{live_warning}"
            )
        if log_usage and cfg.get("log_rag_usage", True):
            self.record_injection_usage(context, results_count=len(results), query=query)
        return context

    def _mark_injected(self, entry_ids):
        ids = {str(value or "") for value in (entry_ids or []) if value}
        if not ids:
            return
        now = self._now_iso()
        with self._lock:
            changed_persistent = False
            for entry in self.data.get("entries", []):
                if str(entry.get("id") or "") in ids:
                    entry["last_injected_at"] = now
                    entry["injection_count"] = int(entry.get("injection_count", 0) or 0) + 1
                    changed_persistent = True
            for entry in self._session_entries:
                if str(entry.get("id") or "") in ids:
                    entry["last_injected_at"] = now
                    entry["injection_count"] = int(entry.get("injection_count", 0) or 0) + 1
            if changed_persistent:
                self._save()

    def record_injection_usage(self, context, results_count=None, query=""):
        tokens = estimate_text_tokens(context)
        if tokens <= 0:
            return
        stats = self.data.setdefault("stats", {})
        stats["injected_tokens_estimate"] = int(stats.get("injected_tokens_estimate", 0)) + tokens
        stats["last_injected_tokens"] = tokens
        stats["last_injected_chars"] = len(str(context or ""))
        stats["last_injected_at"] = self._now_iso()
        stats["injections"] = int(stats.get("injections", 0)) + 1
        if results_count is not None:
            stats["last_injected_results_count"] = int(results_count)
        if query:
            stats["last_injected_query_preview"] = str(query)[:180]
        stats["last_retriever"] = self.RETRIEVER_NAME
        try:
            self._save()
            self.core._log_usage("memory-rag/local", {"prompt": tokens, "completion": 0, "total": tokens})
        except Exception as e:
            logging.warning(f"Memory usage accounting failed: {e}")

    def _should_capture_exchange(self, user_text, final_response, tool_records=None):
        text = f"{user_text}\n{final_response}"
        if self._contains_any(text, self.DO_NOT_REMEMBER_TERMS):
            return False
        if self._looks_user_memory(user_text) or self._looks_live_or_temporal(user_text):
            return True
        if tool_records:
            return True
        intent = self._query_intent(user_text)
        if intent.get("continuity") or intent.get("project") or intent.get("preference"):
            return True
        durable_terms = [
            "remember for next time", "from now on", "next time", "always", "never",
            "project", "repo", "file", "saved", "created", "updated", "fixed",
            "\u05de\u05e2\u05db\u05e9\u05d9\u05d5", "\u05dc\u05e4\u05e2\u05dd \u05d4\u05d1\u05d0\u05d4",
            "\u05ea\u05de\u05d9\u05d3", "\u05d0\u05e3 \u05e4\u05e2\u05dd", "\u05e4\u05e8\u05d5\u05d9\u05e7\u05d8",
            "\u05e7\u05d5\u05d1\u05e5", "\u05e9\u05de\u05e8", "\u05e0\u05e9\u05de\u05e8", "\u05e2\u05d3\u05db\u05df",
            "\u05ea\u05d9\u05e7\u05df", "\u05d4\u05de\u05e9\u05da",
        ]
        return self._contains_any(text, durable_terms)

    def auto_capture_turn(self, user_text, final_response, tool_records=None, is_background_task=False):
        cfg = self._settings()
        if not cfg.get("enabled", True) or not cfg.get("auto_capture", True):
            return []
        user_text = str(user_text or "").strip()
        final_response = str(final_response or "").strip()
        if not user_text:
            return []
        added = []
        source = "background" if is_background_task else "conversation"
        explicit = self._looks_user_memory(user_text)
        temporal = self._looks_live_or_temporal(user_text)
        if explicit:
            automatic_context_eligible = (
                self._durable_preference_signal(user_text)
                and not self._looks_one_time_action_request(user_text)
            )
            added_id = self.add(
                "long_term",
                f"Explicit memory request from user: {user_text[:1400]}",
                subject=self._derive_subject(user_text),
                tags=["auto", "explicit_memory_request"],
                importance=4,
                source=source,
                confidence=0.72,
                metadata={
                    "profile_eligible": False,
                    "automatic_context_eligible": automatic_context_eligible,
                    "capture": "explicit_request_retrievable",
                    "profile_policy_version": self.PROFILE_POLICY_VERSION,
                    "note": (
                        "Preserved for explicit search. Automatic context is allowed only for durable "
                        "non-action content; deterministic profile facts are stored separately."
                    ),
                },
            )
            if added_id:
                added.append(added_id)
        if temporal:
            ttl = 3 if any(t in user_text.lower() for t in ["weather", "forecast", "מזג", "תחזית"]) else None
            added_id = self.add(
                "short_term",
                f"Recent temporal context from user: {user_text[:1200]}",
                subject=self._derive_subject(user_text),
                tags=["auto", "temporal"],
                ttl_hours=ttl,
                importance=2,
                source=source,
                confidence=0.55,
                volatile=True,
                metadata={
                    "automatic_context_eligible": False,
                    "continuity_only": True,
                    "profile_policy_version": self.PROFILE_POLICY_VERSION,
                    "capture": "temporal_continuity_retrievable",
                },
            )
            if added_id:
                added.append(added_id)
        if cfg.get("aggressive_capture", True) and len(user_text) >= 24 and self._should_capture_exchange(user_text, final_response, tool_records):
            outcome = re.sub(r"\s+", " ", final_response)[:900]
            content = f"Recent exchange. User request: {user_text[:1000]}"
            if outcome and not outcome.startswith("ERROR_USER"):
                content += f" Outcome: {outcome}"
            continuity_only = bool(
                temporal or self._looks_one_time_action_request(user_text)
            )
            added_id = self.add(
                "short_term",
                content,
                subject=self._derive_subject(user_text),
                tags=["auto", "conversation"],
                ttl_hours=cfg.get("conversation_ttl_hours", 168),
                importance=2,
                source=source,
                confidence=0.55,
                volatile=temporal,
                metadata={
                    "automatic_context_eligible": not continuity_only,
                    "continuity_only": continuity_only,
                    "profile_policy_version": self.PROFILE_POLICY_VERSION,
                    "capture": "conversation_context_retrievable",
                },
            )
            if added_id:
                added.append(added_id)
        for record in (tool_records or [])[-8:]:
            action = str(record.get("tool", "") or "")
            if not action or action in {"get_tool_info", "search_memory", "update_memory", "memory_manager"}:
                continue
            preview = str(record.get("preview", "") or "")[:1400]
            status = str(record.get("status", "ok") or "ok")
            volatile_tool = action in {"get_weather", "internet_search", "email_manager"} or self._looks_live_or_temporal(preview)
            ttl = 3 if action in {"get_weather", "email_manager"} else cfg.get("tool_memory_ttl_hours", 72)
            added_id = self.add(
                "tool",
                f"Tool {action} returned status={status}. Preview: {preview}",
                subject=f"{action} {status}",
                tags=["tool", action],
                ttl_hours=ttl,
                importance=3 if status == "error" else 2,
                source="tool_observation",
                confidence=0.8 if status != "error" else 0.65,
                tool_name=action,
                volatile=volatile_tool,
                metadata={
                    "automatic_context_eligible": False,
                    "continuity_only": True,
                    "profile_policy_version": self.PROFILE_POLICY_VERSION,
                    "capture": "tool_continuity_retrievable",
                },
            )
            if added_id:
                added.append(added_id)
        if added:
            logging.info(f"MEMORY | auto_capture | added={len(added)}")
        return added

    def tool_search_text(self, query, memory_type="any", max_results=6):
        results = self.search(query, memory_types=memory_type, max_results=max_results, max_chars=8000)
        if not results:
            return "NO_MEMORY_RESULTS"
        return "MEMORY_RESULTS\n" + "\n".join(r["text"] for r in results)


class AuditLogger:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()

    def record(self, event, payload=None, settings=None):
        settings = settings or {}
        if not settings.get("audit_log_enabled", True):
            return
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": payload or {}
        }
        try:
            line = json.dumps(record, ensure_ascii=False, default=str)
            line = redact_sensitive_text(line, settings)
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:
            logging.warning(f"Audit log failed: {e}")


class PolicyEngine:
    def __init__(self, core):
        self.core = core

    def decision(self, capability, *, risk="medium"):
        settings = self.core.settings
        snapshot = getattr(self.core._execution_context, "policy_snapshot", None)
        if self.core._is_background_context() and isinstance(snapshot, dict):
            snap_value = str(snapshot.get(capability, "")).lower()
            if snap_value in POLICY_ACTIONS:
                return snap_value
        matrix = self.core._normalize_policy_matrix()
        decision = matrix.get(capability, DEFAULT_POLICY_MATRIX.get(capability, "ask"))
        if settings.get("permission_level", 1) == 1 and decision == "allow" and capability not in {"file_search", "mcp_search", "browser_open", "software_open", "audio"}:
            return "ask"
        if settings.get("permission_level", 1) == 3 and decision == "ask":
            return "allow"
        return decision

    def force_approval_for(self, capability, risk):
        if risk != "high":
            return False
        max_autonomy = (
            self.core.settings.get("permission_level", 1) == 3
            and self.core.settings.get("autonomy_mode") == "max_autonomy"
        )
        if capability == "shell":
            return bool(self.core.settings.get("raw_shell_requires_approval", True))
        if capability in {"mcp_install", "skill_install"}:
            return bool(self.core.settings.get("marketplace_install_requires_approval", True))
        if capability in {"software_run"}:
            if max_autonomy:
                return False
            return True
        return False


class ToolRegistry:
    def __init__(self, core):
        self.core = core

    def _trust_key(self, kind, name):
        return f"{kind}:{safe_filename(name, kind)}"

    def trust_entry(self, kind, name):
        return self.core.settings.setdefault("tool_trust", {}).get(self._trust_key(kind, name), {})

    def trust_status(self, kind, name, default="untrusted_legacy"):
        return str(self.trust_entry(kind, name).get("trust", default))

    def is_trusted(self, kind, name):
        return self.trust_status(kind, name) == "trusted"

    def set_trust(self, kind, name, trusted, metadata=None):
        key = self._trust_key(kind, name)
        entry = self.core.settings.setdefault("tool_trust", {}).setdefault(key, {})
        entry.update(metadata or {})
        entry["trust"] = "trusted" if trusted else "disabled"
        entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
        return entry

    def _custom_manifest_path(self, tool_name):
        return os.path.join(TOOLS_DIR, f"{safe_filename(tool_name)}.manifest.json")

    def ensure_custom_tool_manifest(self, tool_name):
        tool_name = safe_filename(tool_name)
        tool_path = os.path.join(TOOLS_DIR, f"{tool_name}.pyw")
        doc_path = os.path.join(TOOLS_DIR, f"{tool_name}.txt")
        manifest_path = self._custom_manifest_path(tool_name)
        manifest = {
            "schema_version": 1,
            "name": tool_name,
            "kind": "custom_python",
            "trust": "untrusted_legacy",
            "risk": "high",
            "permissions": ["python_tool_run"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "hash": file_sha256(tool_path) if os.path.exists(tool_path) else "",
            "schema_file": os.path.basename(doc_path) if os.path.exists(doc_path) else ""
        }
        changed = False
        if not os.path.exists(manifest_path):
            try:
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
                changed = True
            except Exception as e:
                logging.warning(f"Failed writing tool manifest for {tool_name}: {e}")
        trust = self.core.settings.setdefault("tool_trust", {})
        key = self._trust_key("custom", tool_name)
        if key not in trust:
            trust[key] = copy.deepcopy(manifest)
            changed = True
        return changed

    def ensure_registries(self):
        changed = False
        self.core.settings.setdefault("tool_trust", {})
        self.core.settings.setdefault("mcp_registry", {})
        self.core.settings.setdefault("skill_registry", {})
        if os.path.exists(TOOLS_DIR):
            for f in os.listdir(TOOLS_DIR):
                if f.endswith(".pyw"):
                    changed = self.ensure_custom_tool_manifest(f[:-4]) or changed
        if os.path.exists(MCP_TOOLS_DIR):
            for f in os.listdir(MCP_TOOLS_DIR):
                if f.endswith(".txt"):
                    stem = f[:-4]
                    entry = self.core.settings["mcp_registry"].setdefault(stem, {})
                    if not entry:
                        entry.update({
                            "name": stem,
                            "trust": "untrusted_legacy",
                            "source": "legacy_local",
                            "registered_at": datetime.now().isoformat(timespec="seconds")
                        })
                        changed = True
                    key = self._trust_key("mcp", stem)
                    if key not in self.core.settings["tool_trust"]:
                        self.core.settings["tool_trust"][key] = copy.deepcopy(entry)
                        changed = True
        if os.path.exists(SKILLS_DIR):
            for item in os.listdir(SKILLS_DIR):
                skill_dir = os.path.join(SKILLS_DIR, item)
                if os.path.isdir(skill_dir):
                    name = safe_filename(item, "skill")
                    entry = self.core.settings["skill_registry"].setdefault(name, {})
                    if not entry:
                        entry.update({
                            "name": name,
                            "trust": "untrusted_legacy",
                            "source": "legacy_local",
                            "registered_at": datetime.now().isoformat(timespec="seconds")
                        })
                        changed = True
                    key = self._trust_key("skill", name)
                    if key not in self.core.settings["tool_trust"]:
                        self.core.settings["tool_trust"][key] = copy.deepcopy(entry)
                        changed = True
        return changed


class AgentRuntime:
    def __init__(self, core):
        self.core = core

    def trace(self, stage, detail=""):
        if not self.core.settings.get("enable_developer_trace", True):
            return
        item = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "stage": stage,
            "detail": redact_sensitive_text(str(detail or ""), self.core.settings)[:1800]
        }
        trace = self.core.settings.setdefault("_runtime_trace", [])
        trace.append(item)
        del trace[:-80]
        logging.info(f"TRACE | {item['stage']} | {item['detail']}")

    def _tool_call_entry(self, text, start, end, raw):
        return {
            "json_str": raw.strip(),
            "raw": raw,
            "start": start,
            "end": end,
            "pre_text": text[:start].strip(),
        }

    def _tool_call_entries_from_obj(self, text, start, end, raw, obj):
        if isinstance(obj, dict) and obj.get("method") == "tools/call":
            return [self._tool_call_entry(text, start, end, raw)]
        if isinstance(obj, dict):
            method = str(obj.get("method", "") or "").strip()
            if method in BUILTIN_TOOL_SCHEMAS:
                params = obj.get("params", {})
                if not isinstance(params, dict):
                    params = {}
                arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else params
                call_obj = {"method": "tools/call", "params": {"name": method, "arguments": arguments if isinstance(arguments, dict) else {}}}
                call_raw = json.dumps(call_obj, ensure_ascii=False)
                return [self._tool_call_entry(text, start, end, call_raw)]
        calls = []
        raw_calls = []
        if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list):
            raw_calls = obj.get("tool_calls", [])
        elif isinstance(obj, list):
            raw_calls = obj
        for item in raw_calls:
            if not isinstance(item, dict):
                continue
            if item.get("method") == "tools/call":
                call_obj = item
            else:
                function_obj = item.get("function") if isinstance(item.get("function"), dict) else {}
                name = item.get("name") or item.get("tool") or item.get("action") or function_obj.get("name")
                args = item.get("arguments", item.get("args", item.get("input", function_obj.get("arguments", {}))))
                if not name:
                    continue
                if isinstance(args, str):
                    try:
                        parsed_args = json.loads(args)
                        args = parsed_args if isinstance(parsed_args, dict) else {}
                    except Exception:
                        args = {}
                call_obj = {"method": "tools/call", "params": {"name": name, "arguments": args if isinstance(args, dict) else {}}}
            call_raw = json.dumps(call_obj, ensure_ascii=False)
            calls.append(self._tool_call_entry(text, start, end, call_raw))
        return calls

    def extract_tool_calls(self, text):
        text = text or ""
        blocks = list(re.finditer(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE))
        calls = []
        for m in blocks:
            raw = m.group(1)
            try:
                obj = json.loads(raw)
                calls.extend(self._tool_call_entries_from_obj(text, m.start(), m.end(), raw, obj))
            except Exception:
                if '"tools/call"' in raw:
                    calls.append(self._tool_call_entry(text, m.start(), m.end(), raw))
        if calls:
            first = calls[0]
            last = calls[-1]
            return {
                "json_str": calls[0]["json_str"],
                "pre_text": text[:first["start"]].strip(),
                "is_tool_call_intent": True,
                "tool_turn_text": text[:last["end"]].strip(),
                "extra_tool_blocks": max(0, len(calls) - 1),
                "tool_calls": calls,
            }
        decoder = json.JSONDecoder()
        scan_from = 0
        for idx, ch in enumerate(text):
            if idx < scan_from:
                continue
            if ch != "{":
                continue
            try:
                obj, end = decoder.raw_decode(text[idx:])
            except Exception:
                continue
            raw = text[idx:idx + end]
            entries = self._tool_call_entries_from_obj(text, idx, idx + end, raw, obj)
            if entries:
                calls.extend(entries)
                scan_from = idx + end
        if calls:
            return {
                "json_str": calls[0]["json_str"],
                "pre_text": text[:calls[0]["start"]].strip(),
                "is_tool_call_intent": True,
                "tool_turn_text": text[:calls[-1]["end"]].strip(),
                "extra_tool_blocks": max(0, len(calls) - 1),
                "tool_calls": calls,
            }
        return {"json_str": "", "pre_text": "", "is_tool_call_intent": False, "tool_turn_text": text, "extra_tool_blocks": 0, "tool_calls": []}

    def extract_tool_call(self, text):
        parsed = self.extract_tool_calls(text)
        parsed["extra_tool_blocks"] = max(0, len(parsed.get("tool_calls", []) or []) - 1)
        return parsed

    def _canonicalize_for_similarity(self, value):
        if isinstance(value, dict):
            return {str(k).strip().lower(): self._canonicalize_for_similarity(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]).lower())}
        if isinstance(value, list):
            return [self._canonicalize_for_similarity(v) for v in value]
        if isinstance(value, str):
            text = unicodedata.normalize("NFKC", value)
            text = re.sub(r'\s+', ' ', text).strip().lower()
            text = re.sub(r'["\'`]+', '', text)
            text = re.sub(r'([\\/]){2,}', r'\1', text)
            return text
        return value

    def similarity_signature(self, action, args_dict):
        normalized_obj = self._canonicalize_for_similarity(args_dict or {})
        normalized = json.dumps(normalized_obj, sort_keys=True, ensure_ascii=False, default=str)
        normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
        return f"{str(action or '').strip().lower()}:{normalized[:3000]}"

    def is_similar_repeat(self, signatures, signature):
        recent = signatures[-10:]
        strong_hits = 0
        weak_hits = 0
        for previous in recent:
            ratio = difflib.SequenceMatcher(None, previous, signature).ratio()
            if ratio >= 0.985:
                strong_hits += 1
            elif ratio >= 0.93:
                weak_hits += 1
        return strong_hits >= 2 or (strong_hits >= 1 and weak_hits >= 1) or weak_hits >= 3


class McpManager:
    def __init__(self, core):
        self.core = core

    def is_trusted(self, pkg_name):
        resolved = self.core._resolve_mcp_package(pkg_name)
        keys = {pkg_name, resolved, mcp_pkg_to_file_stem(pkg_name), mcp_pkg_to_file_stem(resolved)}
        return any(self.core.tool_registry.is_trusted("mcp", key) for key in keys if key)


class SkillManager:
    def __init__(self, core):
        self.core = core

    def is_trusted(self, name, spec=None):
        if spec and spec.get("source") == "builtin":
            return True
        return self.core.tool_registry.is_trusted("skill", name)


class BackgroundScheduler:
    TERMINAL = {"done", "failed", "cancelled"}

    def __init__(self, core):
        self.core = core

    def policy_snapshot(self):
        matrix = self.core._normalize_policy_matrix()
        return {cap: self.core._policy_decision(cap) for cap in matrix}


class UiState:
    def __init__(self, core):
        self.core = core

__all__ = [name for name in globals() if not name.startswith("__")]
