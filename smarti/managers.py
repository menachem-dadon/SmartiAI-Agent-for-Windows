"""Settings, memory, policy, registry, and runtime manager classes."""
import math
from .common import *
from .config import *
from .memory_store import MemorySQLiteStore

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
    def migrate_memory_retrieval_defaults(settings):
        """Translate the shipped v1 relevance scale to the bounded v2 scale."""
        settings = copy.deepcopy(settings or {})
        memory = settings.get("memory")
        if not isinstance(memory, dict) or not memory:
            return settings, False
        try:
            version = int(memory.get("retrieval_settings_version", 0) or 0)
        except Exception:
            version = 0
        if version >= 1:
            return settings, False
        before = copy.deepcopy(memory)
        # Replace only exact historical shipped defaults.  Deliberately tuned
        # user values remain untouched, except that an impossible >1 threshold
        # belongs to the old score scale and must be converted.
        replacements = {
            "max_results": (8, 3),
            "max_injected_chars": (4200, 1200),
            "user_memory_max_results": (8, 3),
            "user_memory_max_injected_chars": (2200, 1200),
            "non_tool_memory_max_results": (8, 3),
            "tool_memory_prompt_max_results": (3, 0),
            "tool_memory_prompt_max_chars": (1400, 0),
        }
        for key, (old_value, new_value) in replacements.items():
            if memory.get(key) == old_value:
                memory[key] = new_value
        try:
            old_threshold = float(memory.get("min_relevance_score", 4.2) or 4.2)
        except Exception:
            old_threshold = 4.2
        if old_threshold > 1.0 or old_threshold < 0.0:
            memory["min_relevance_score"] = 0.62
        memory["retrieval_settings_version"] = 1
        settings["memory"] = memory
        return settings, memory != before

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
        loaded, memory_retrieval_changed = self.migrate_memory_retrieval_defaults(loaded)
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
                or memory_retrieval_changed
                or model_provenance_changed
                or context_limits_changed
            ),
        )


class SmartiMemoryManager:
    """Local structured memory with TTL and bounded RAG injection."""
    SCHEMA_VERSION = 5
    PROFILE_POLICY_VERSION = 5
    PRIVACY_POLICY_VERSION = 3
    AUTOMATIC_USE_POLICY_VERSION = 4
    QUALITY_POLICY_VERSION = 3
    MODEL_MEMORY_POLICY_VERSION = 2
    SCOPE_POLICY_VERSION = 1
    USER_WORK_CLEANUP_VERSION = 1
    VALID_TYPES = {"short_term", "long_term", "tool", "user"}
    MODEL_MEMORY_ACTIONS = {"add", "update", "delete"}
    MODEL_MEMORY_SOURCE_TYPES = {"user", "assistant", "tool", "web", "decision"}
    MODEL_MEMORY_CATEGORY_ALIASES = {
        "preferences": "preference",
        # Broad labels produced by models are not retrieval categories. Clear
        # them so deterministic content classification can recover address,
        # phone, identity, preference, and the other canonical categories.
        "personal": "",
        "personal_detail": "",
        "personal_details": "",
        "personal_info": "",
        "personal_information": "",
        "contact_detail": "",
        "contact_details": "",
        "contact_info": "",
        "contact_information": "",
        "user_detail": "",
        "user_details": "",
        "user_info": "",
        "user_information": "",
        "profile": "",
    }
    MODEL_MEMORY_BLOCK_RE = re.compile(
        r"<smarti_memory>\s*(.*?)\s*</smarti_memory>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    SENSITIVE_CATEGORIES = {"address", "phone", "email", "health"}
    NEVER_STORE_CATEGORIES = {"authentication_secret", "financial_secret"}
    RETRIEVER_NAME = "encrypted-scope-rerank-v4"
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
        "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
        "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
        "which", "what", "how", "when", "where", "who", "why", "this", "that", "these", "those",
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
            "preference", "prefer", "preferred", "favorite", "favourite", "taste", "tastes",
            "style", "likes", "dislikes", "always", "never",
            "\u05de\u05e2\u05d3\u05d9\u05e3", "\u05de\u05e2\u05d3\u05d9\u05e4\u05d4", "\u05d0\u05d5\u05d4\u05d1",
            "\u05d0\u05d5\u05d4\u05d1\u05ea", "\u05d0\u05d4\u05d5\u05d1", "\u05d0\u05d4\u05d5\u05d1\u05d4", "\u05de\u05d5\u05e2\u05d3\u05e3", "\u05de\u05d5\u05e2\u05d3\u05e4\u05ea", "\u05d8\u05e2\u05dd",
            "\u05e1\u05d2\u05e0\u05d5\u05df", "\u05ea\u05de\u05d9\u05d3",
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
        "refresh token", "bearer token", "session token", "otp", "2fa", "cvv",
        "credit card", "card number", "bank account", "iban",
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
        self._evidence_validation_cache = {}
        self.store = MemorySQLiteStore(path)
        if not self.store.has_snapshot():
            self.store.ensure_legacy_backup()
        self.data = self._load()
        self.data.setdefault("rejected", [])
        self._migrate_memory_v2_quality()
        self._migrate_project_scopes()
        self._migrate_legacy_user_memory()
        self._migrate_privacy_model()
        self._migrate_automatic_use_model()
        self._migrate_user_work_artifacts()
        self._migrate_profile_eligibility()
        self.prune_expired()
        self.prune_unused()
        self.backfill_critical_user_details()
        self._save()

    def _settings(self):
        cfg = self.core.settings.setdefault("memory", {})
        defaults = DEFAULT_SETTINGS.get("memory", {})
        for key, value in defaults.items():
            cfg.setdefault(key, copy.deepcopy(value))
        return cfg

    def _load(self):
        if self.store.has_snapshot():
            return self.store.load_snapshot()
        if not os.path.exists(self.path):
            return {
                "schema_version": self.SCHEMA_VERSION, "entries": [], "archive": [],
                "pending": [], "rejected": [], "stats": {},
            }
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("memory root must be an object")
            loaded.setdefault("schema_version", self.SCHEMA_VERSION)
            loaded.setdefault("entries", [])
            loaded.setdefault("archive", [])
            loaded.setdefault("pending", [])
            loaded.setdefault("rejected", [])
            loaded.setdefault("stats", {})
            if not isinstance(loaded["entries"], list):
                loaded["entries"] = []
            if not isinstance(loaded["archive"], list):
                loaded["archive"] = []
            if not isinstance(loaded["pending"], list):
                loaded["pending"] = []
            if not isinstance(loaded["rejected"], list):
                loaded["rejected"] = []
            loaded["schema_version"] = self.SCHEMA_VERSION
            return loaded
        except Exception as e:
            logging.error(f"Memory load failed; starting empty: {e}")
            return {
                "schema_version": self.SCHEMA_VERSION,
                "entries": [],
                "archive": [],
                "pending": [],
                "rejected": [],
                "stats": {"load_error": str(e)},
            }

    def _save(self):
        self.data["schema_version"] = self.SCHEMA_VERSION
        self.store.replace_snapshot(self.data)
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
            with open(self.export_path, "w", encoding="utf-8") as f:
                f.write("\n".join(rows).strip() + "\n")
        except Exception as e:
            logging.warning(f"Memory safe markdown export failed: {e}")

    def _entry_metadata(self, entry):
        metadata = entry.get("metadata") if isinstance(entry, dict) else None
        return metadata if isinstance(metadata, dict) else {}

    def _entry_category(self, entry):
        metadata = self._entry_metadata(entry)
        category = str(entry.get("category") or metadata.get("category") or "general").strip().lower()
        category = self.MODEL_MEMORY_CATEGORY_ALIASES.get(category, category)
        return category or "general"

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
        return "[Memory content protected with Windows DPAPI; plaintext omitted.]"

    def _public_entry(self, entry, *, reveal_sensitive=False, user_authorized=False):
        item = copy.deepcopy(entry or {})
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        category = self._entry_category(item)
        sensitivity = self._entry_sensitivity(item)
        plain = self._plain_content(item)
        item["category"] = category
        item["sensitivity"] = sensitivity
        item["version"] = int(item.get("version", 1) or 1)
        # DPAPI protects every persisted payload at rest. Sensitivity controls
        # masking and relevance, while the global memory switch controls model use.
        item["cloud_allowed"] = bool(item.get("cloud_allowed", metadata.get("cloud_allowed", False)))
        item["masked"] = sensitivity == "sensitive" and not (reveal_sensitive and user_authorized)
        item["content"] = plain if not item["masked"] else self._mask_sensitive_content(plain, category)
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
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except Exception:
            return None

    def _project_scope(self):
        """Compatibility alias: Smarti has no project-scoped memory container."""
        return "global"

    def _canonical_scope(self, scope, memory_type="long_term"):
        value = str(scope or "").strip()
        if value.startswith("project:") or os.path.isabs(value):
            return "global"
        if value and value != "global":
            if value.startswith(("conversation:", "user:")):
                return value
            return value[:500]
        return "user:default" if memory_type == "user" else "global"

    def _migrate_project_scopes(self):
        """Collapse the former CWD-derived pseudo-project scope into global memory."""
        stats = self.data.setdefault("stats", {})
        try:
            version = int(stats.get("scope_policy_version", 0) or 0)
        except Exception:
            version = 0
        if version >= self.SCOPE_POLICY_VERSION:
            return 0
        changed = 0
        for key in ("entries", "archive", "pending", "rejected"):
            for entry in self.data.setdefault(key, []):
                if str(entry.get("scope") or "").startswith("project:"):
                    entry["scope"] = "global"
                    changed += 1
        for entry in self._session_entries:
            if str(entry.get("scope") or "").startswith("project:"):
                entry["scope"] = "global"
                changed += 1
        stats["scope_policy_version"] = self.SCOPE_POLICY_VERSION
        stats["project_scopes_migrated"] = int(stats.get("project_scopes_migrated", 0) or 0) + changed
        return changed

    def _canonical_memory_text(self, text):
        value = self._normalize_text_for_search(self._strip_user_work_artifact(text))
        value = re.sub(
            r"^(?:recent exchange\.?\s*)?(?:explicit memory request from user|recent temporal context from user|user request|outcome)\s*:\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(r"\btool\s+[\w.-]+\s+returned\s+status\s*=\s*\w+\.?\s*preview\s*:\s*", "", value)
        value = re.sub(r"\s+", " ", value).strip(" .,:;-\u2013\u2014")
        return value

    def _canonical_key_for(self, entry, content=None):
        memory_type = self._normalize_type(entry.get("type", "long_term"))
        category = self._entry_category(entry)
        canonical = self._canonical_memory_text(self._plain_content(entry) if content is None else content)
        material = f"{memory_type}\0{category}\0{canonical}"
        return hashlib.sha256(material.encode("utf-8", "ignore")).hexdigest()

    def _near_duplicate_text(self, left, right):
        left_canonical = self._canonical_memory_text(left)
        right_canonical = self._canonical_memory_text(right)
        left_numbers = re.findall(r"\d+", left_canonical)
        right_numbers = re.findall(r"\d+", right_canonical)
        if (left_numbers or right_numbers) and left_numbers != right_numbers:
            return False
        left_tokens = set(self._tokenize_list(left_canonical, include_ngrams=False))
        right_tokens = set(self._tokenize_list(right_canonical, include_ngrams=False))
        if len(left_tokens) < 4 or len(right_tokens) < 4:
            return False
        overlap = len(left_tokens.intersection(right_tokens))
        containment = overlap / max(1, min(len(left_tokens), len(right_tokens)))
        jaccard = overlap / max(1, len(left_tokens.union(right_tokens)))
        return containment >= 0.92 and jaccard >= 0.78

    @staticmethod
    def _entry_quality_key(entry):
        source_rank = {
            "manual_ui": 7, "manual": 7, "explicit_tool": 6, "legacy_settings": 5,
            "critical_preflight": 4, "critical_backfill": 2, "conversation": 1,
            "background": 1, "tool_observation": 0,
        }
        return (
            bool(entry.get("pinned")),
            source_rank.get(str(entry.get("source") or ""), 3),
            int(entry.get("importance", 3) or 3),
            int(entry.get("helpful_count", 0) or 0),
            int(entry.get("used_count", 0) or 0),
            str(entry.get("updated_at") or entry.get("created_at") or ""),
        )

    def _archive_for_quality(self, entry, reason, **metadata):
        archived = copy.deepcopy(entry)
        archived["archived_at"] = self._now_iso()
        archived["archive_reason"] = str(reason)
        archived.setdefault("metadata", {}).update(metadata)
        archived["status"] = "archive"
        self.data.setdefault("archive", []).append(archived)

    def _migrate_memory_v2_quality(self):
        """Consolidate exact duplicates and remove transcript/tool traces from active memory."""
        stats = self.data.setdefault("stats", {})
        if int(stats.get("quality_policy_version", 0) or 0) >= self.QUALITY_POLICY_VERSION:
            for entry in self.data.get("entries", []) + self.data.get("archive", []):
                if isinstance(entry, dict):
                    entry.setdefault("canonical_key", self._canonical_key_for(entry))
                    entry["scope"] = self._canonical_scope(entry.get("scope"), entry.get("type"))
            return
        active = []
        grouped = {}
        archived_traces = 0
        duplicate_count = 0
        for raw in list(self.data.get("entries", [])):
            if not isinstance(raw, dict):
                continue
            entry = copy.deepcopy(raw)
            classification = self.classify_content(
                f"{entry.get('subject', '')} {self._plain_content(entry)}",
                self._entry_category(entry),
            )
            entry["category"] = classification["category"]
            entry["sensitivity"] = classification["sensitivity"]
            entry["scope"] = self._canonical_scope(entry.get("scope"), entry.get("type"))
            entry["canonical_key"] = self._canonical_key_for(entry)
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            entry["metadata"] = metadata
            metadata["category"] = classification["category"]
            metadata["sensitivity"] = classification["sensitivity"]
            source = str(entry.get("source") or "").lower()
            capture = str(metadata.get("capture") or "").lower()
            auto_trace = (
                entry.get("type") == "tool"
                or source == "tool_observation"
                or capture == "tool_continuity_retrievable"
                or (
                    source in {"conversation", "background"}
                    and capture not in {"explicit_user_request", "strict_inferred_capture"}
                )
                or (
                    entry.get("type") == "short_term"
                    and source in {"conversation", "background"}
                    and ("conversation" in capture or "temporal" in capture or "auto" in (entry.get("tags") or []))
                )
                or (
                    source == "critical_backfill"
                    and self._looks_one_time_action_request(self._plain_content(entry))
                )
                or (
                    source in {"conversation", "background"}
                    and self._looks_one_time_action_request(self._plain_content(entry))
                )
            )
            if auto_trace:
                self._archive_for_quality(
                    entry, "legacy_conversation_or_tool_trace",
                    v2_disposition="kept_as_history_evidence_not_active_memory",
                )
                archived_traces += 1
                continue
            grouped.setdefault((entry["scope"], entry["canonical_key"]), []).append(entry)
        for (_scope, _key), entries in grouped.items():
            entries.sort(key=self._entry_quality_key, reverse=True)
            keeper = entries[0]
            if len(entries) > 1:
                merged_ids = [str(item.get("id") or "") for item in entries[1:]]
                keeper.setdefault("metadata", {})["merged_duplicate_ids"] = merged_ids
                keeper["metadata"]["dedupe_count"] = len(entries)
                keeper["importance"] = max(int(item.get("importance", 3) or 3) for item in entries)
                keeper["tags"] = sorted({tag for item in entries for tag in (item.get("tags") or [])})[:12]
                for duplicate in entries[1:]:
                    self._archive_for_quality(
                        duplicate, "duplicate_consolidated",
                        duplicate_of=keeper.get("id"), canonical_key=keeper.get("canonical_key"),
                    )
            active.append(keeper)
        archive_groups = {}
        for raw in self.data.get("archive", []):
            if not isinstance(raw, dict):
                continue
            entry = copy.deepcopy(raw)
            entry["scope"] = self._canonical_scope(entry.get("scope"), entry.get("type"))
            entry["canonical_key"] = self._canonical_key_for(entry)
            archive_groups.setdefault((entry["scope"], entry["canonical_key"]), []).append(entry)
        active_by_key = {(entry["scope"], entry["canonical_key"]): entry for entry in active}
        consolidated_archive = []
        for key, entries in archive_groups.items():
            entries.sort(key=self._entry_quality_key, reverse=True)
            active_keeper = active_by_key.get(key)
            if active_keeper is not None:
                merged = active_keeper.setdefault("metadata", {}).setdefault("merged_duplicate_ids", [])
                for duplicate in entries:
                    duplicate_id = str(duplicate.get("id") or "")
                    if duplicate_id and duplicate_id not in merged:
                        merged.append(duplicate_id)
                active_keeper["metadata"]["dedupe_count"] = 1 + len(merged)
                duplicate_count += len(entries)
                continue
            keeper = entries[0]
            if len(entries) > 1:
                merged = keeper.setdefault("metadata", {}).setdefault("merged_duplicate_ids", [])
                for duplicate in entries[1:]:
                    duplicate_id = str(duplicate.get("id") or "")
                    if duplicate_id and duplicate_id not in merged:
                        merged.append(duplicate_id)
                keeper["metadata"]["dedupe_count"] = 1 + len(merged)
                keeper["metadata"]["merged_archive_reasons"] = sorted({
                    str(item.get("archive_reason") or "unknown") for item in entries
                })
                duplicate_count += len(entries) - 1
            consolidated_archive.append(keeper)
        self.data["archive"] = consolidated_archive
        self.data["entries"] = active
        stats["quality_policy_version"] = self.QUALITY_POLICY_VERSION
        stats["quality_migrated_at"] = self._now_iso()
        stats["duplicates_consolidated"] = duplicate_count
        stats["legacy_traces_archived"] = archived_traces
        stats["storage_backend"] = "sqlite-v2"

    def classify_content(self, content, category=""):
        """Return deterministic privacy metadata; secrets are never eligible for storage."""
        text = str(content or "")
        low = self._normalize_text_for_search(text)
        category = str(category or "").strip().lower()
        category = self.MODEL_MEMORY_CATEGORY_ALIASES.get(category, category)
        if category in {"general", "unknown"}:
            category = ""
        if category in self.NEVER_STORE_CATEGORIES:
            return {
                "category": category,
                "sensitivity": "sensitive",
                "store_allowed": False,
                "reason": "Secrets, authentication values, OTPs and payment credentials are never stored.",
            }
        secret_pattern = re.compile(
            r"(?i)(?:sk-[a-z0-9_-]{12,}|AIza[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{20,}|"
            r"eyJ[a-z0-9_-]{10,}\.[a-z0-9_-]{10,}\.[a-z0-9_-]{8,}|"
            r"(?:otp|2fa|cvv|password|passcode|api\s*key|access\s*token|refresh\s*token|"
            r"bearer\s*token|session\s*token|token|iban|bank\s*account)\s*[:=]\s*\S+|"
            r"(?:credit\s*card|card\s*number|bank\s*account|iban|כרטיס\s*אשראי|אשראי|"
            r"חשבון\s*בנק)[^\d]{0,30}\d(?:[\d\s-]{8,}\d))"
        )
        secret_value_context = re.search(
            r"(?i)(?:my\s+)?(?:password|passcode|api\s*key|access\s*token|refresh\s*token|"
            r"bearer\s*token|session\s*token|token|otp|2fa|cvv|credit\s*card|card\s*number|"
            r"bank\s*account|iban|סיסמ(?:ה|ת)|מפתח\s*api|טוקן|קוד\s*אימות|כרטיס\s*אשראי|"
            r"אשראי|חשבון\s*בנק)"
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
                    if self._contains_any(low, terms):
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
        """Encrypt every persisted memory while retaining its logical state."""
        with self._lock:
            stats = self.data.setdefault("stats", {})
            if int(stats.get("privacy_policy_version", 0) or 0) < self.PRIVACY_POLICY_VERSION:
                changed = 0
                purged = 0
                prohibited_refs = set()
                for collection in (
                    self.data.setdefault("entries", []), self.data.setdefault("archive", []),
                    self.data.setdefault("pending", []), self.data.setdefault("rejected", []),
                ):
                    for entry in collection:
                        if not isinstance(entry, dict):
                            continue
                        plain = self._plain_content(entry)
                        classification = (
                            self.classify_content(plain, self._entry_category(entry))
                            if plain
                            else {
                                "category": self._entry_category(entry),
                                "sensitivity": self._entry_sensitivity(entry),
                                "store_allowed": True,
                            }
                        )
                        if not classification.get("store_allowed", True):
                            prohibited_refs.add(id(entry))
                            purged += 1
                            continue
                        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                        entry["metadata"] = metadata
                        entry["category"] = classification["category"]
                        entry["sensitivity"] = classification["sensitivity"]
                        metadata["category"] = classification["category"]
                        metadata["sensitivity"] = classification["sensitivity"]
                        if not str(entry.get("content") or "").startswith(SECRET_PREFIX) and plain:
                            entry["content"] = self._protect_content(plain)
                            changed += 1
                        decryptable = bool(plain) or not str(entry.get("content") or "").startswith(SECRET_PREFIX)
                        metadata["encrypted"] = True
                        metadata["encryption_version"] = 1
                        metadata["automatic_context_eligible"] = decryptable
                        # The single global memory switch controls model use. A
                        # second per-category/per-entry consent layer made useful
                        # personal memory silently unusable.
                        metadata["cloud_allowed"] = decryptable
                        entry["cloud_allowed"] = decryptable
                if prohibited_refs:
                    for collection_name in ("entries", "archive", "pending", "rejected"):
                        self.data[collection_name] = [
                            entry for entry in self.data.get(collection_name, [])
                            if id(entry) not in prohibited_refs
                        ]
                memory_cfg = self._settings()
                for obsolete_key in (
                    "store_sensitive_personal_details", "sensitive_category_consent",
                    "health_memory_mode", "sensitive_memory_cloud_default",
                    "allow_sensitive_memory_in_prompt",
                ):
                    memory_cfg.pop(obsolete_key, None)
                stats["privacy_policy_version"] = self.PRIVACY_POLICY_VERSION
                stats["privacy_migrated_at"] = self._now_iso()
                stats["privacy_v3_protected_entries"] = changed
                stats["privacy_v3_prohibited_entries_removed"] = purged
                try:
                    self.core._save_settings()
                except Exception:
                    pass
                self._save()
            return
    def _migrate_automatic_use_model(self):
        """Remove the accidentally introduced review queue without losing data."""
        with self._lock:
            stats = self.data.setdefault("stats", {})
            pending = list(self.data.setdefault("pending", []))
            rejected = list(self.data.setdefault("rejected", []))
            policy_was_current = (
                int(stats.get("automatic_use_policy_version", 0) or 0)
                >= self.AUTOMATIC_USE_POLICY_VERSION
            )
            if policy_was_current and not pending and not rejected:
                return

            active = self.data.setdefault("entries", [])
            archive = self.data.setdefault("archive", [])
            active_keys = {
                (
                    self._canonical_scope(item.get("scope"), item.get("type")),
                    str(item.get("canonical_key") or self._canonical_key_for(item)),
                )
                for item in active if isinstance(item, dict)
            }
            activated = 0
            archived = 0
            for raw in pending:
                if not isinstance(raw, dict):
                    continue
                entry = copy.deepcopy(raw)
                metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
                entry["metadata"] = metadata
                entry.pop("status", None)
                entry.pop("pending_kind", None)
                entry.pop("pending_reason", None)
                metadata.pop("pending_reason", None)
                metadata.pop("review_state", None)
                entry["id"] = "mem_" + uuid.uuid4().hex[:12]
                entry["scope"] = self._canonical_scope(entry.get("scope"), entry.get("type"))
                entry["canonical_key"] = str(entry.get("canonical_key") or self._canonical_key_for(entry))
                key = (entry["scope"], entry["canonical_key"])
                if str(entry.get("content") or "").startswith(SECRET_PREFIX) and not self._plain_content(entry):
                    entry["archived_at"] = self._now_iso()
                    entry["archive_reason"] = "protected_memory_could_not_be_decrypted"
                    archive.append(entry)
                    archived += 1
                    continue
                classification = self.classify_content(
                    self._plain_content(entry), self._entry_category(entry)
                )
                if not classification.get("store_allowed", True):
                    entry["archived_at"] = self._now_iso()
                    entry["archive_reason"] = "removed_review_queue_prohibited_secret"
                    archive.append(entry)
                    archived += 1
                elif key not in active_keys:
                    metadata["consent_state"] = "approved"
                    metadata["automatic_context_eligible"] = True
                    active.append(entry)
                    active_keys.add(key)
                    activated += 1

            for raw in rejected:
                if not isinstance(raw, dict):
                    continue
                entry = copy.deepcopy(raw)
                entry.pop("status", None)
                entry["archived_at"] = entry.get("rejected_at") or self._now_iso()
                entry["archive_reason"] = "removed_review_queue_rejected_capture"
                archive.append(entry)
                archived += 1

            self.data["pending"] = []
            self.data["rejected"] = []
            stats.pop("pending_captures", None)
            stats.pop("privacy_pending_review", None)
            stats["automatic_use_policy_version"] = self.AUTOMATIC_USE_POLICY_VERSION
            stats["automatic_use_migrated_at"] = self._now_iso()
            stats["automatic_use_mode"] = "strict_capture_without_review"
            stats["review_queue_activated"] = activated
            stats["review_queue_archived"] = archived
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
        return tokens

    def _tokenize(self, text):
        return set(self._tokenize_list(text))

    def _entry_search_text(self, entry):
        metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
        retrieval_hints = metadata.get("retrieval_hints", [])
        if not isinstance(retrieval_hints, list):
            retrieval_hints = [retrieval_hints] if retrieval_hints else []
        return " ".join([
            str(entry.get("subject", "")),
            self._plain_content(entry),
            " ".join(entry.get("tags", []) or []),
            self._entry_category(entry),
            " ".join(str(item or "") for item in retrieval_hints[:8]),
        ])

    def _expanded_query_tokens(self, query):
        # Query expansion used to add dozens of generic words and Hebrew
        # character four-grams. Both produced convincing but unrelated hits.
        # FTS now receives only words the user actually supplied (plus a light
        # Hebrew stem emitted by _tokenize_list).
        tokens = {t for t in self._tokenize_list(query, include_ngrams=False) if len(t) >= 2}
        # A tiny domain-specific bilingual bridge is safer than the former
        # broad synonym expansion and keeps equivalent Hebrew/English project
        # questions comparable without introducing generic noise.
        aliases = {
            "database": {"מסד", "נתונים"},
            "databases": {"מסד", "נתונים"},
            "מסד": {"database"},
        }
        for token in tuple(tokens):
            tokens.update(aliases.get(token, ()))
        return tokens

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
            r"(?<![\u0590-\u05FF])(\u05d0\u05e0\u05d9|\u05e9\u05dc\u05d9|\u05dc\u05d9|\u05d0\u05e6\u05dc\u05d9|\u05d2\u05e8|\u05d2\u05e8\u05d4|\u05de\u05ea\u05d2\u05d5\u05e8\u05e8|\u05de\u05ea\u05d2\u05d5\u05e8\u05e8\u05ea)(?![\u0590-\u05FF])",
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

    def capture_critical_user_details(self, user_text, source="critical_preflight"):
        """Deprecated compatibility shim; mechanical capture is disabled."""
        return []
    def backfill_critical_user_details(self):
        # V1 repeatedly mined its own generated memories and amplified them on
        # every policy bump. V2 deliberately never backfills from memory text.
        stats = self.data.setdefault("stats", {})
        stats["critical_backfill_version"] = self.PROFILE_POLICY_VERSION
        stats.setdefault("critical_backfill_last_count", 0)
        return []

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

    def prune_unused(self):
        """Archive low-value inferred memories that have never proved useful."""
        with self._lock:
            now = datetime.now()
            cfg = self._settings()
            active = []
            archived = []
            for entry in self.data.setdefault("entries", []):
                metadata = self._entry_metadata(entry)
                source = str(entry.get("source") or "").lower()
                inferred = bool(metadata.get("inferred")) or source in {
                    "conversation", "background", "auto_inferred", "critical_preflight", "critical_backfill",
                }
                if not inferred or entry.get("pinned") or int(entry.get("helpful_count", 0) or 0) > 0:
                    active.append(entry)
                    continue
                days = cfg.get("project_memory_unused_days", 90) if str(entry.get("scope") or "").startswith("project:") else cfg.get("inferred_memory_unused_days", 30)
                try:
                    cutoff = now - timedelta(days=max(1.0, float(days or 30)))
                except Exception:
                    cutoff = now - timedelta(days=30)
                last_value = (
                    self._parse_dt(entry.get("last_used_at"))
                    or self._parse_dt(entry.get("last_injected_at"))
                    or self._parse_dt(entry.get("updated_at"))
                    or self._parse_dt(entry.get("created_at"))
                )
                if last_value and last_value < cutoff:
                    item = copy.deepcopy(entry)
                    item["status"] = "archive"
                    item["archived_at"] = self._now_iso()
                    item["archive_reason"] = "unused_inferred_memory"
                    archived.append(item)
                else:
                    active.append(entry)
            if archived:
                self.data["entries"] = active
                self.data.setdefault("archive", []).extend(archived)
            changed = len(archived)
            if changed:
                stats = self.data.setdefault("stats", {})
                stats["unused_archived"] = int(stats.get("unused_archived", 0) or 0) + len(archived)
                stats["last_retention_at"] = self._now_iso()
                self._save()
            return changed

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
            source="manual", confidence=0.75, scope="", tool_name="", volatile=None,
            metadata=None, category="", consent_state="approved", cloud_allowed=None,
            storage_mode="persistent", entry_id="", pinned=False, created_at="",
            updated_at="", expires_at=""):
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
        consent_state = str(consent_state or "approved")
        scope = self._canonical_scope(scope, memory_type)
        if ttl_hours is None:
            ttl_hours = self._ttl_for_type(memory_type, source=source)
        try:
            ttl_hours = float(ttl_hours) if ttl_hours not in (None, "") else None
        except Exception:
            ttl_hours = None
        now = datetime.now()
        created_dt = self._parse_dt(created_at) or now
        updated_dt = self._parse_dt(updated_at) or created_dt
        supplied_expiry = self._parse_dt(expires_at)
        expires_at = (
            supplied_expiry.isoformat(timespec="seconds")
            if supplied_expiry is not None
            else ((updated_dt + timedelta(hours=ttl_hours)).isoformat(timespec="seconds") if ttl_hours else None)
        )
        volatile = self._looks_live_or_temporal(content) if volatile is None else bool(volatile)
        try:
            importance = max(1, min(5, int(float(importance))))
        except Exception:
            importance = 3
        tags = self._coerce_tags(tags)
        subject = self._strip_user_work_artifact(subject)[:120] or self._derive_subject(content)
        if sensitivity == "sensitive":
            # Titles are stored and rendered as plaintext metadata, so they must
            # never repeat an email, phone number, address, or health detail.
            subject = self.CRITICAL_CATEGORY_LABELS.get(category, "Sensitive memory")
        fingerprint = hashlib.sha256(
            f"{memory_type}\0{scope}\0{subject.lower()}\0{content.lower()}".encode("utf-8", "ignore")
        ).hexdigest()
        canonical_key = self._canonical_key_for(
            {"type": memory_type, "category": category, "content": content}, content=content,
        )
        with self._lock:
            target_entries = self._session_entries if storage_mode == "session_only" else self.data.setdefault("entries", [])
            for entry in target_entries:
                same_canonical = (
                    entry.get("scope") == scope
                    and str(entry.get("canonical_key") or self._canonical_key_for(entry)) == canonical_key
                )
                near_duplicate = bool(
                    entry.get("scope") == scope
                    and entry.get("type") == memory_type
                    and self._entry_category(entry) == category
                    and self._near_duplicate_text(self._plain_content(entry), content)
                )
                if entry.get("fingerprint") == fingerprint or same_canonical or near_duplicate:
                    entry["updated_at"] = self._now_iso()
                    entry["expires_at"] = expires_at
                    entry["importance"] = max(int(entry.get("importance", 3)), importance)
                    entry["duplicate_count"] = int(entry.get("duplicate_count", 0) or 0) + 1
                    entry["last_source"] = source
                    entry["tags"] = sorted(set(entry.get("tags", []) or []) | set(tags))[:12]
                    entry["cloud_allowed"] = bool(entry.get("cloud_allowed")) or bool(cloud_allowed)
                    entry["canonical_key"] = canonical_key
                    if isinstance(metadata, dict) and metadata:
                        existing_metadata = entry.get("metadata")
                        if not isinstance(existing_metadata, dict):
                            existing_metadata = {}
                            entry["metadata"] = existing_metadata
                        existing_metadata.update(copy.deepcopy(metadata))
                        existing_metadata["cloud_allowed"] = bool(entry.get("cloud_allowed"))
                        existing_metadata["consent_state"] = consent_state
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
                "encrypted": storage_mode != "session_only",
                "encryption_version": 1 if storage_mode != "session_only" else 0,
                "why_saved": metadata.get("why_saved") or source,
            })
            stored_content = (
                self._protect_content(content[:6000])
                if storage_mode != "session_only"
                else content[:6000]
            )
            entry = {
                "id": entry_id,
                "type": memory_type,
                "scope": scope,
                "canonical_key": canonical_key,
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
                "created_at": created_dt.isoformat(timespec="seconds"),
                "updated_at": updated_dt.isoformat(timespec="seconds"),
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
            statuses = {"active", "archive", "session"}
        collections = {
            "active": self.data.get("entries", []),
            "archive": self.data.get("archive", []),
            "session": self._session_entries,
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
            if not entry:
                raise KeyError("memory_id not found")
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
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            metadata.update({
                "category": classification["category"],
                "sensitivity": classification["sensitivity"],
                "sensitive": classification["sensitivity"] == "sensitive",
                "encrypted": status != "session",
                "encryption_version": 1 if status != "session" else 0,
            })
            entry["metadata"] = metadata
            entry["content"] = (
                self._protect_content(content[:6000])
                if status != "session"
                else content[:6000]
            )
            entry["category"] = classification["category"]
            entry["sensitivity"] = classification["sensitivity"]
            if "subject" in changes:
                entry["subject"] = self._strip_user_work_artifact(changes.get("subject"))[:120] or self._derive_subject(content)
            if classification["sensitivity"] == "sensitive":
                entry["subject"] = self.CRITICAL_CATEGORY_LABELS.get(
                    classification["category"], "Sensitive memory"
                )
            if "memory_type" in changes:
                entry["type"] = self._normalize_type(changes.get("memory_type"))
            if "scope" in changes:
                entry["scope"] = self._canonical_scope(changes.get("scope"), entry.get("type"))
            if "importance" in changes:
                entry["importance"] = max(1, min(5, int(changes.get("importance") or 3)))
            if "confidence" in changes:
                entry["confidence"] = max(0.0, min(1.0, float(changes.get("confidence") or 0.75)))
            if "tags" in changes:
                entry["tags"] = self._coerce_tags(changes.get("tags"))
            if "volatile" in changes:
                entry["volatile"] = bool(changes.get("volatile"))
            if "cloud_allowed" in changes:
                entry["cloud_allowed"] = bool(changes.get("cloud_allowed"))
            else:
                entry["cloud_allowed"] = True
            metadata["cloud_allowed"] = bool(entry.get("cloud_allowed"))
            metadata["consent_state"] = "approved"
            if "pinned" in changes:
                entry["pinned"] = bool(changes.get("pinned"))
            if "expires_at" in changes:
                supplied_expiry = self._parse_dt(changes.get("expires_at"))
                entry["expires_at"] = (
                    supplied_expiry.isoformat(timespec="seconds") if supplied_expiry else None
                )
            elif "ttl_hours" in changes:
                ttl = changes.get("ttl_hours")
                entry["expires_at"] = (
                    (datetime.now() + timedelta(hours=float(ttl))).isoformat(timespec="seconds")
                    if ttl not in (None, "", 0, "0") else None
                )
            supplied_metadata = changes.get("metadata")
            if isinstance(supplied_metadata, dict):
                metadata.update(copy.deepcopy(supplied_metadata))
            if changes.get("last_source"):
                entry["last_source"] = str(changes.get("last_source"))[:120]
            if changes.get("tool_name"):
                entry["tool_name"] = str(changes.get("tool_name"))[:80]
            supplied_updated = self._parse_dt(changes.get("updated_at"))
            entry["updated_at"] = (
                supplied_updated.isoformat(timespec="seconds") if supplied_updated else self._now_iso()
            )
            entry["version"] = current_version + 1
            entry["fingerprint"] = hashlib.sha256(
                f"{entry.get('type')}\0{entry.get('scope')}\0{entry.get('subject', '').lower()}\0{content.lower()}".encode("utf-8", "ignore")
            ).hexdigest()
            entry["scope"] = self._canonical_scope(entry.get("scope"), entry.get("type"))
            entry["canonical_key"] = self._canonical_key_for(entry, content=content)
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
            if status == "session":
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
            scope = self._canonical_scope(entry.get("scope"), entry.get("type"))
            canonical_key = str(entry.get("canonical_key") or self._canonical_key_for(entry))
            if any(
                self._canonical_scope(item.get("scope"), item.get("type")) == scope
                and str(item.get("canonical_key") or self._canonical_key_for(item)) == canonical_key
                for item in self.data.get("entries", [])
            ):
                return False
            restored = entries.pop(index)
            before = copy.deepcopy(restored)
            restored.pop("archived_at", None)
            restored.pop("archive_reason", None)
            restored["updated_at"] = self._now_iso()
            restored["version"] = int(restored.get("version", 1) or 1) + 1
            restored["scope"] = scope
            restored["canonical_key"] = canonical_key
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
            all_entries = active + archive + list(self._session_entries)
            by_type = {}
            by_category = {}
            sensitive = 0
            for entry in all_entries:
                by_type[entry.get("type", "unknown")] = by_type.get(entry.get("type", "unknown"), 0) + 1
                category = self._entry_category(entry)
                by_category[category] = by_category.get(category, 0) + 1
                sensitive += self._entry_sensitivity(entry) == "sensitive"
            try:
                storage_bytes = sum(
                    os.path.getsize(candidate) for candidate in (self.path, self.store.path)
                    if os.path.exists(candidate)
                )
            except Exception:
                storage_bytes = 0
            return {
                "active": len(active),
                "archive": len(archive),
                "session": len(self._session_entries),
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
            "encrypted_content": bool(encrypted),
            "encrypted_sensitive": bool(encrypted),
            "entries": [],
            "archive": [],
        }
        with self._lock:
            for key, collection in (
                ("entries", self.data.get("entries", [])),
                ("archive", self.data.get("archive", [])),
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
        self._audit_memory_event("export", memory_id="", encrypted=bool(encrypted), count=sum(len(payload[k]) for k in ("entries", "archive")))
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
                    scope=entry.get("scope", ""),
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
                + len(self.data.get("rejected", []))
                + len(self._session_entries)
            )
            if memory_type:
                self.data["entries"] = [e for e in self.data.get("entries", []) if e.get("type") != memory_type]
                self.data["archive"] = [e for e in self.data.get("archive", []) if e.get("type") != memory_type]
                self.data["pending"] = [e for e in self.data.get("pending", []) if e.get("type") != memory_type]
                self.data["rejected"] = [e for e in self.data.get("rejected", []) if e.get("type") != memory_type]
                self._session_entries = [e for e in self._session_entries if e.get("type") != memory_type]
            else:
                self.data["entries"] = []
                self.data["archive"] = []
                self.data["pending"] = []
                self.data["rejected"] = []
                self._session_entries = []
            removed = (
                before - len(self.data["entries"]) - len(self.data["archive"])
                - len(self.data["pending"]) - len(self._session_entries)
                - len(self.data["rejected"])
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

    def _query_memory_categories(self, query):
        normalized = self._normalize_text_for_search(query)
        routes = {
            "identity": ("my name", "who am i", "call me", "מה השם שלי", "איך קוראים לי", "מי אני"),
            "birthday": ("my birthday", "date of birth", "יום ההולדת שלי", "תאריך הלידה שלי"),
            "preference": (
                "my preference", "what do i prefer", "what do i like", "what is my favorite",
                "favorite food", "favorite style", "ההעדפה שלי", "מה אני מעדיף", "מה אני מעדיפה",
                "מה אני אוהב", "מה אני אוהבת", "מה אני הכי אוהב", "מה אני הכי אוהבת",
                "המאכל האהוב עלי", "האוכל האהוב עלי", "הסגנון המועדף עלי",
            ),
            "address": ("my address", "where do i live", "הכתובת שלי", "איפה אני גר", "איפה אני גרה"),
            "phone": ("my phone", "my mobile", "הטלפון שלי", "הנייד שלי"),
            "email": ("my email", "email address", "האימייל שלי", "המייל שלי", "הדוא״ל שלי"),
            "health": ("my health", "my allergy", "my medication", "הבריאות שלי", "האלרגיה שלי", "התרופה שלי"),
            "work": ("my work", "where do i work", "העבודה שלי", "איפה אני עובד", "איפה אני עובדת"),
        }
        categories = {
            category for category, terms in routes.items()
            if any(self._normalize_text_for_search(term) in normalized for term in terms)
        }
        intent = self._query_intent(query)
        preference_subject = bool(
            self._has_user_ownership_signal(query)
            or re.search(r"(?:של|על)\s+המשתמש", normalized)
            or re.search(r"המשתמש.{0,35}(?:אוהב|אוהבת|מעדיף|מעדיפה)", normalized)
            or re.search(r"\b(?:the\s+user|user's)\b", normalized)
        )
        if intent.get("preference") and preference_subject:
            categories.add("preference")
        # Phrase lists cannot reasonably enumerate every natural possessive
        # form (for example, "מהי כתובת המגורים שלי?").  Route an owned
        # profile question by the user's actual category words, without the
        # broad synonym expansion that previously caused unrelated memories
        # to be injected.  Requiring an explicit first-person possessive keeps
        # generic questions about addresses or phone numbers from exposing a
        # saved personal detail.
        tokens = self._tokenize(query)
        if tokens.intersection({"my", "שלי"}):
            owned_category_terms = {
                "identity": {"name", "identity", "שם", "זהות"},
                "birthday": {"birthday", "birth", "הולדת", "לידה"},
                "preference": {"preference", "preferences", "העדפה", "העדפות"},
                "address": {"address", "street", "home", "כתובת", "רחוב", "מגורים"},
                "phone": {"phone", "mobile", "cell", "טלפון", "נייד"},
                "email": {"email", "mail", "אימייל", "מייל", "דואל"},
                "health": {"health", "medical", "allergy", "medication", "בריאות", "אלרגיה", "תרופה"},
                "work": {"work", "job", "employer", "עבודה", "מעסיק"},
            }
            for category, terms in owned_category_terms.items():
                normalized_terms = {
                    token
                    for term in terms
                    for token in self._tokenize(term)
                }
                if tokens.intersection(normalized_terms):
                    categories.add(category)
        return categories

    def _looks_global_style_preference(self, entry):
        if self._entry_category(entry) != "preference" or self._entry_sensitivity(entry) == "sensitive":
            return False
        text = self._normalize_text_for_search(self._entry_search_text(entry))
        style_terms = (
            "answer", "answers", "response", "responses", "reply", "replies",
            "concise", "brief", "verbose", "language", "tone", "format", "formatting",
            "markdown", "bullet", "explanation", "code style",
            "תשובה", "תשובות", "תענה", "ענה", "בקצרה", "תמציתי", "תמציתיות",
            "מפורט", "עברית", "אנגלית", "שפה", "טון", "סגנון", "פורמט",
            "רשימה", "נקודות", "הסבר", "אימוג",
        )
        return any(self._normalize_text_for_search(term) in text for term in style_terms)

    def _entry_recall_policy(self, entry):
        metadata = self._entry_metadata(entry)
        requested = str(metadata.get("recall_policy") or "").strip().lower()
        if requested == "always":
            if self._entry_category(entry) == "preference" and self._entry_sensitivity(entry) != "sensitive":
                return "always"
            return "relevant"
        if requested == "relevant":
            return "relevant"
        # Compatibility for style preferences saved before the model-authored
        # recall policy existed. New memories receive an explicit model choice.
        return "always" if self._looks_global_style_preference(entry) else "relevant"

    def _always_apply_memory_results(self, *, max_results=3, max_chars=600):
        try:
            max_results = max(0, min(8, int(max_results or 0)))
            max_chars = max(0, min(4000, int(max_chars or 0)))
        except Exception:
            return []
        if max_results <= 0 or max_chars <= 0:
            return []
        now = datetime.now()
        with self._lock:
            entries = list(self.data.get("entries", [])) + list(self._session_entries)
        candidates = []
        for entry in entries:
            if entry.get("type") not in {"user", "long_term"} or self._is_expired(entry, now):
                continue
            metadata = self._entry_metadata(entry)
            if not metadata.get("automatic_context_eligible", True) or not self._evidence_is_current(entry):
                continue
            if self._entry_recall_policy(entry) != "always":
                continue
            candidates.append(entry)
        candidates.sort(
            key=lambda entry: (
                bool(entry.get("pinned")),
                int(entry.get("importance", 3) or 3),
                float(entry.get("confidence", 0.75) or 0.75),
                str(entry.get("updated_at") or entry.get("created_at") or ""),
            ),
            reverse=True,
        )
        results = []
        used_chars = 0
        for entry in candidates:
            formatted = self._format_entry(entry, 1.0, reveal_sensitive=False)
            if used_chars + len(formatted) > max_chars:
                continue
            results.append({"score": 1.0, "entry": entry, "text": formatted})
            used_chars += len(formatted)
            if len(results) >= max_results:
                break
        return results

    def _search_v1_legacy(self, query, memory_types=None, max_results=None, max_chars=None, *, for_prompt=False):
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

    def _evidence_is_current(self, entry):
        metadata = self._entry_metadata(entry)
        if str(entry.get("validation_state") or metadata.get("validation_state") or "").lower() == "stale":
            return False
        evidence = metadata.get("evidence") if isinstance(metadata.get("evidence"), list) else []
        for item in evidence:
            if not isinstance(item, dict) or str(item.get("type") or "").lower() not in {"file", "path"}:
                continue
            reference = os.path.abspath(str(item.get("reference") or ""))
            if not reference or not os.path.exists(reference):
                return False
            expected_size = item.get("size")
            expected_mtime = item.get("mtime_ns")
            expected_digest = str(item.get("digest") or "").strip().lower()
            try:
                stat = os.stat(reference)
                if expected_size not in (None, "") and int(expected_size) != int(stat.st_size):
                    return False
                if expected_mtime not in (None, "") and int(expected_mtime) != int(stat.st_mtime_ns):
                    return False
                if expected_digest:
                    cache_key = (reference, int(stat.st_size), int(stat.st_mtime_ns), expected_digest)
                    valid = self._evidence_validation_cache.get(cache_key)
                    if valid is None:
                        digest = hashlib.sha256()
                        with open(reference, "rb") as handle:
                            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                                digest.update(chunk)
                        normalized_expected = expected_digest.removeprefix("sha256:")
                        valid = digest.hexdigest().lower() == normalized_expected
                        self._evidence_validation_cache[cache_key] = valid
                    if not valid:
                        return False
            except Exception:
                return False
        return True

    def search(self, query, memory_types=None, max_results=None, max_chars=None, *, for_prompt=False):
        """Read-only, scope-first encrypted-memory retrieval with a calibrated 0..1 score."""
        cfg = self._settings()
        if for_prompt and not cfg.get("enabled", True):
            return []
        try:
            max_results = max(0, min(20, int(max_results if max_results is not None else cfg.get("max_results", 3))))
        except Exception:
            max_results = 3
        try:
            max_chars = max(0, min(20000, int(max_chars if max_chars is not None else cfg.get("max_injected_chars", 1200))))
        except Exception:
            max_chars = 1200
        if max_results <= 0 or max_chars <= 0:
            return []
        if isinstance(memory_types, str):
            memory_types = None if memory_types in {"", "any"} else {self._normalize_type(memory_types)}
        elif memory_types:
            memory_types = {self._normalize_type(value) for value in memory_types}
        q = str(query or "").strip()
        q_tokens = self._expanded_query_tokens(q)
        if not q_tokens:
            return []
        q_normalized = self._normalize_text_for_search(q)
        intent = self._query_intent(q)
        routed_categories = self._query_memory_categories(q)
        allowed_scopes = ["user:default", "global"]
        # Memory payloads are encrypted at rest, including the SQLite store, so
        # relevance is calculated over the bounded decrypted in-process view.
        # The on-disk FTS table intentionally contains no memory plaintext.
        fts_rows = []
        bm25_by_id = {memory_id: rank for memory_id, rank in fts_rows}
        with self._lock:
            persistent = list(self.data.get("entries", []))
            session = list(self._session_entries)
            # Sensitive details remain restricted to category-relevant queries,
            # even though the global memory switch now authorizes their use.
            sensitive = [
                entry for entry in self.data.get("entries", [])
                if self._entry_sensitivity(entry) == "sensitive"
                and self._sensitive_entry_relevant(q, entry)
            ]
            routed = [
                entry for entry in self.data.get("entries", [])
                if (
                    self._entry_category(entry) in routed_categories
                    or (
                        intent.get("project")
                        and self._entry_category(entry) in {"project", "work"}
                    )
                )
            ]
        candidates = persistent + session + sensitive + routed
        now = datetime.now()
        try:
            min_score = float(cfg.get("min_relevance_score", 0.62) or 0.62)
        except Exception:
            min_score = 0.62
        # A few existing installations still carry the old 4.2-style score.
        # The current scorer is calibrated to 0..1, so fail safe even before
        # settings persistence has had a chance to run its migration.
        if not 0.0 <= min_score <= 1.0:
            min_score = 0.62
        scored = []
        seen_ids = set()
        for entry in candidates:
            entry_id = str(entry.get("id") or "")
            if not entry_id or entry_id in seen_ids or self._is_expired(entry, now):
                continue
            seen_ids.add(entry_id)
            if memory_types and entry.get("type") not in memory_types:
                continue
            scope = self._canonical_scope(entry.get("scope"), entry.get("type"))
            if scope not in allowed_scopes and not scope.startswith("conversation:"):
                continue
            if for_prompt:
                metadata = self._entry_metadata(entry)
                if not metadata.get("automatic_context_eligible", True):
                    continue
                if not self._evidence_is_current(entry):
                    continue
                if self._entry_sensitivity(entry) == "sensitive":
                    if not self._sensitive_entry_relevant(q, entry):
                        continue
            haystack = self._entry_search_text(entry)
            entry_tokens = self._tokenize(haystack)
            matched = q_tokens.intersection(entry_tokens)
            metadata = self._entry_metadata(entry)
            retrieval_hints = metadata.get("retrieval_hints", [])
            if not isinstance(retrieval_hints, list):
                retrieval_hints = [retrieval_hints] if retrieval_hints else []
            hint_tokens = self._tokenize(" ".join(str(item or "") for item in retrieval_hints[:8]))
            matched_hints = q_tokens.intersection(hint_tokens)
            hint_coverage = len(matched_hints) / max(1, len(q_tokens))
            category_match = self._entry_category(entry) in routed_categories
            project_route = bool(
                intent.get("project") and self._entry_category(entry) in {"project", "work"}
            )
            if not matched and not category_match and not project_route:
                continue
            coverage = len(matched) / max(1, len(q_tokens))
            precision = len(matched) / max(1, min(len(entry_tokens), len(q_tokens) * 3))
            exact_phrase = bool(q_normalized and len(q_normalized) >= 4 and q_normalized in self._normalize_text_for_search(haystack))
            rank = abs(float(bm25_by_id.get(entry_id, 4.0)))
            bm25_signal = 1.0 / (1.0 + rank)
            scope_signal = 0.8 if scope == "user:default" else 0.65
            confidence = max(0.0, min(1.0, float(entry.get("confidence", 0.75) or 0.75)))
            importance = max(1.0, min(5.0, float(entry.get("importance", 3) or 3))) / 5.0
            helpful = int(entry.get("helpful_count", 0) or 0)
            unhelpful = int(entry.get("unhelpful_count", 0) or 0)
            score = (
                0.55 * coverage
                + 0.58 * (1.0 if category_match else 0.0)
                + 0.30 * (1.0 if project_route else 0.0)
                + 0.24 * (1.0 if matched_hints else 0.0)
                + 0.32 * hint_coverage
                + 0.07 * precision
                + 0.10 * (1.0 if exact_phrase else 0.0)
                + 0.08 * bm25_signal
                + 0.08 * scope_signal
                + 0.07 * confidence
                + 0.05 * importance
                + min(0.05, helpful * 0.02)
                - min(0.35, unhelpful * 0.16)
            )
            if intent.get("live") and entry.get("volatile"):
                score *= 0.25
            score = max(0.0, min(1.0, score))
            if score < min_score:
                continue
            scored.append((score, entry))
        scored.sort(
            key=lambda item: (
                item[0],
                item[1].get("scope") == "user:default",
                item[1].get("helpful_count", 0),
                item[1].get("updated_at", ""),
            ),
            reverse=True,
        )
        results = []
        used_chars = 0
        seen_keys = set()
        for score, entry in scored:
            key = (entry.get("scope"), entry.get("canonical_key") or self._canonical_key_for(entry))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            formatted = self._format_entry(entry, score, reveal_sensitive=for_prompt)
            if used_chars + len(formatted) > max_chars:
                continue
            results.append({"score": score, "entry": entry, "text": formatted})
            used_chars += len(formatted)
            if len(results) >= max_results:
                break
        return results

    def _format_entry(self, entry, score, *, reveal_sensitive=False):
        raw_scope = str(entry.get("scope") or "global")
        scope_label = (
            "user" if raw_scope.startswith("user:")
            else ("conversation" if raw_scope.startswith("conversation:") else "global")
        )
        header = (
            f"- id={entry.get('id')} score={score:.2f} "
            f"scope={scope_label} subject={entry.get('subject') or 'memory'}"
        )
        content = re.sub(r"\s+", " ", self._plain_content(entry).strip())
        if self._entry_sensitivity(entry) == "sensitive" and not reveal_sensitive:
            content = self._mask_sensitive_content(content, self._entry_category(entry))
        if len(content) > 480:
            content = content[:480].rstrip() + "..."
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

    def _build_prompt_context_v1_legacy(self, query="", log_usage=False):
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

    def build_prompt_context(self, query="", log_usage=False):
        cfg = self._settings()
        if not cfg.get("enabled", True) or not cfg.get("rag_enabled", True):
            return "Saved memory is disabled."
        query = str(query or "").strip()
        total_budget = min(1050, int(cfg.get("max_injected_chars", 1200) or 1200))
        always_results = self._always_apply_memory_results(
            max_results=cfg.get("always_memory_max_results", 3),
            max_chars=min(total_budget, int(cfg.get("always_memory_max_chars", 600) or 600)),
        )
        semantic_results = self.search(
            query,
            memory_types={"user", "long_term"},
            max_results=cfg.get("max_results", 3),
            max_chars=total_budget,
            for_prompt=True,
        )
        always_ids = {
            str(result.get("entry", {}).get("id") or "")
            for result in always_results
        }
        semantic_results = [
            result for result in semantic_results
            if str(result.get("entry", {}).get("id") or "") not in always_ids
        ]
        results = always_results + semantic_results
        live_warning = ""
        if cfg.get("verify_live_data", True) and self._looks_live_or_temporal(query):
            live_warning = " Changing facts must be checked with a current source; saved memory is not current evidence."
        if results:
            sections = []
            if always_results:
                sections.append(
                    "Always-applied response preferences (apply silently unless the current request overrides them):\n"
                    + "\n".join(result["text"] for result in always_results)
                )
            if semantic_results:
                sections.append(
                    "Semantically relevant saved memory:\n"
                    + "\n".join(result["text"] for result in semantic_results)
                )
            body = "\n\n".join(sections)
            if len(body) > total_budget:
                body = body[:total_budget].rstrip() + "..."
            context = (
                "Relevant saved memory (advisory; the current user message and fresh evidence take precedence):\n"
                f"{body}{live_warning}"
            )
        else:
            context = f"No relevant saved memory was retrieved for this request.{live_warning}"
        if log_usage and cfg.get("log_rag_usage", True):
            entry_ids = [result.get("entry", {}).get("id") for result in results if result.get("entry", {}).get("id")]
            self._mark_injected(entry_ids)
            self.record_injection_usage(
                context, results_count=len(results), query=query, entry_ids=entry_ids,
            )
        return context

    def _mark_injected(self, entry_ids):
        ids = {str(value or "") for value in (entry_ids or []) if value}
        if not ids:
            return
        now = self._now_iso()
        with self._lock:
            for entry in self.data.get("entries", []):
                if str(entry.get("id") or "") in ids:
                    entry["selected_count"] = int(entry.get("selected_count", 0) or 0) + 1
                    entry["last_injected_at"] = now
                    entry["injection_count"] = int(entry.get("injection_count", 0) or 0) + 1
            for entry in self._session_entries:
                if str(entry.get("id") or "") in ids:
                    entry["selected_count"] = int(entry.get("selected_count", 0) or 0) + 1
                    entry["last_injected_at"] = now
                    entry["injection_count"] = int(entry.get("injection_count", 0) or 0) + 1

    def record_injection_usage(self, context, results_count=None, query="", entry_ids=None):
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
            self.store.record_retrieval(
                selected_ids=entry_ids or [], injected_ids=entry_ids or [], query=query,
                tokens=tokens, chars=len(str(context or "")),
            )
            self.core._log_usage("memory-rag/local", {"prompt": tokens, "completion": 0, "total": tokens})
        except Exception as e:
            logging.warning(f"Memory usage accounting failed: {e}")

    def extract_model_memory_decision(self, text):
        """Remove hidden memory envelopes and return their validated operation objects."""
        raw_text = str(text or "")
        blocks = self.MODEL_MEMORY_BLOCK_RE.findall(raw_text)
        cleaned = self.MODEL_MEMORY_BLOCK_RE.sub("", raw_text).strip()
        operations = []
        for raw_block in blocks:
            payload_text = str(raw_block or "").strip()
            payload_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", payload_text, flags=re.IGNORECASE)
            try:
                payload = json.loads(payload_text)
            except Exception as exc:
                logging.warning("Invalid model memory envelope ignored: %s", exc)
                continue
            raw_operations = payload.get("operations", []) if isinstance(payload, dict) else payload
            if not isinstance(raw_operations, list):
                continue
            for operation in raw_operations:
                if not isinstance(operation, dict):
                    logging.warning(
                        "Ignored model memory operation because it is not an object: %r",
                        operation,
                    )
                    continue
                normalized, repair = self._normalize_model_memory_operation(operation)
                if normalized is None:
                    logging.warning(
                        "Ignored model memory operation with no safe action inference: keys=%s",
                        sorted(str(key) for key in operation.keys()),
                    )
                    continue
                if repair:
                    logging.warning("Repaired model memory operation: %s", repair)
                operations.append(normalized)
                if len(operations) >= 6:
                    return cleaned, operations
        return cleaned, operations

    def _normalize_model_memory_operation(self, operation):
        """Repair only unambiguous envelope-shape mistakes after model selection."""
        raw = copy.deepcopy(operation) if isinstance(operation, dict) else {}
        action = str(raw.get("action") or "").strip().lower()
        if action in self.MODEL_MEMORY_ACTIONS:
            raw["action"] = action
            return raw, ""

        # Common LLM variant: {"add": { ...fields... }}. The model already
        # selected the semantic operation, so flattening it does not create a
        # mechanical memory decision.
        wrapped_actions = [
            candidate for candidate in self.MODEL_MEMORY_ACTIONS
            if isinstance(raw.get(candidate), dict)
        ]
        if len(wrapped_actions) == 1:
            action = wrapped_actions[0]
            normalized = {
                key: copy.deepcopy(value)
                for key, value in raw.items()
                if key != action
            }
            normalized.update(copy.deepcopy(raw[action]))
            normalized["action"] = action
            return normalized, f"flattened wrapped '{action}' object"

        # Another observed variant is a flat new-memory payload that omits
        # action. Content without a target can only mean add. With a target and
        # changed fields it can only mean update. Deletion is never inferred.
        has_content = bool(str(raw.get("content") or "").strip())
        has_target = bool(str(raw.get("memory_id") or raw.get("match") or "").strip())
        if has_content and not has_target:
            raw["action"] = "add"
            return raw, "inferred missing 'action=add' from flat new-memory payload"
        update_fields = {
            "content", "subject", "category", "scope", "memory_type",
            "importance", "confidence", "tags", "volatile", "expires_at",
            "refresh_validity", "tool_name", "recall_policy", "retrieval_hints",
        }
        if has_target and update_fields.intersection(raw):
            raw["action"] = "update"
            return raw, "inferred missing 'action=update' from targeted changed fields"
        return None, ""

    def _model_memory_scope(self, operation, memory_type="long_term"):
        scope = str((operation or {}).get("scope") or "").strip().lower()
        if scope in {"user", "profile", "user:default"} or memory_type == "user":
            return "user:default"
        return "global"

    def _model_memory_type(self, operation):
        requested = str((operation or {}).get("memory_type") or "").strip().lower()
        if requested == "user" or str((operation or {}).get("scope") or "").strip().lower() in {
            "user", "profile", "user:default",
        }:
            return "user"
        # Provenance belongs in source_type. Durable semantic memory remains
        # retrievable as long_term instead of becoming raw tool/conversation memory.
        return "long_term"

    @staticmethod
    def _normalize_retrieval_hints(value):
        if not isinstance(value, list):
            value = [value] if value else []
        hints = []
        seen = set()
        for item in value[:12]:
            hint = re.sub(r"\s+", " ", str(item or "")).strip()[:160]
            key = hint.casefold()
            if not hint or key in seen:
                continue
            seen.add(key)
            hints.append(hint)
            if len(hints) >= 8:
                break
        return hints

    def _model_memory_metadata(
        self,
        operation,
        *,
        session_id="",
        memory_type="",
        category="",
        sensitivity="ordinary",
        existing_metadata=None,
    ):
        operation = operation or {}
        existing = copy.deepcopy(existing_metadata) if isinstance(existing_metadata, dict) else {}
        source_type = str((operation or {}).get("source_type") or "assistant").strip().lower()
        if source_type not in self.MODEL_MEMORY_SOURCE_TYPES:
            source_type = "assistant"
        evidence = (operation or {}).get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [evidence] if evidence else []
        normalized_evidence = []
        for item in evidence[:6]:
            if isinstance(item, dict):
                normalized_evidence.append(copy.deepcopy(item))
            elif str(item or "").strip():
                normalized_evidence.append({"reference": str(item).strip()[:1000]})
        requested_recall = str(
            operation.get("recall_policy")
            or operation.get("retrieval_policy")
            or operation.get("application")
            or existing.get("recall_policy")
            or "relevant"
        ).strip().lower()
        recall_policy = requested_recall if requested_recall in {"always", "relevant"} else "relevant"
        canonical_category = self.MODEL_MEMORY_CATEGORY_ALIASES.get(
            str(category or operation.get("category") or "").strip().lower(),
            str(category or operation.get("category") or "").strip().lower(),
        )
        # Unconditional prompt injection is intentionally narrow: it is for
        # harmless response-style preferences, never personal details or other
        # facts that could leak to an unrelated network request.
        if recall_policy == "always" and (
            canonical_category != "preference" or str(sensitivity or "ordinary") == "sensitive"
        ):
            recall_policy = "relevant"
        raw_hints = (
            operation.get("retrieval_hints")
            if "retrieval_hints" in operation
            else existing.get("retrieval_hints", [])
        )
        metadata = existing
        metadata.update({
            "capture": "model_semantic_decision",
            "model_memory_policy_version": self.MODEL_MEMORY_POLICY_VERSION,
            "model_authored": True,
            "source_type": source_type,
            "why_saved": str(
                (operation or {}).get("why_saved")
                or (operation or {}).get("reason")
                or "Selected by the model as reusable memory."
            )[:1000],
            "validity_basis": str((operation or {}).get("validity_basis") or "")[:1000],
            "evidence": normalized_evidence,
            "source_conversation_id": str(session_id or "")[:120],
            "automatic_context_eligible": True,
            "profile_eligible": (memory_type or self._model_memory_type(operation)) == "user",
            "inferred": source_type != "user",
            "recall_policy": recall_policy,
            "retrieval_hints": self._normalize_retrieval_hints(raw_hints),
        })
        return metadata

    def _resolve_model_memory_target(self, operation):
        memory_id = str((operation or {}).get("memory_id") or "").strip()
        if memory_id:
            status, _entries, _index, entry = self._locate_entry(memory_id)
            return entry if status in {"active", "session"} else None
        match = self._canonical_memory_text((operation or {}).get("match") or "")
        if not match:
            return None
        requested_category = str((operation or {}).get("category") or "").strip().lower()
        requested_scope = str((operation or {}).get("scope") or "").strip().lower()
        candidates = []
        for entry in list(self.data.get("entries", [])) + list(self._session_entries):
            if requested_category and self._entry_category(entry) != requested_category:
                continue
            if requested_scope and self._canonical_scope(entry.get("scope"), entry.get("type")) != self._model_memory_scope(operation, entry.get("type")):
                continue
            content = self._canonical_memory_text(self._plain_content(entry))
            subject = self._canonical_memory_text(entry.get("subject") or "")
            if match in {content, subject}:
                candidates.append(entry)
        if len(candidates) == 1:
            return candidates[0]
        contained = []
        if len(match) >= 12:
            for entry in list(self.data.get("entries", [])) + list(self._session_entries):
                if requested_category and self._entry_category(entry) != requested_category:
                    continue
                if requested_scope and self._canonical_scope(entry.get("scope"), entry.get("type")) != self._model_memory_scope(operation, entry.get("type")):
                    continue
                content = self._canonical_memory_text(self._plain_content(entry))
                subject = self._canonical_memory_text(entry.get("subject") or "")
                if match in content or content in match or match in subject:
                    contained.append(entry)
        return contained[0] if len(contained) == 1 else None

    def _find_model_memory_duplicate(self, content, *, memory_type, category, scope):
        canonical_key = self._canonical_key_for(
            {"type": memory_type, "category": category, "content": content}, content=content,
        )
        for entry in list(self.data.get("entries", [])) + list(self._session_entries):
            if self._canonical_scope(entry.get("scope"), entry.get("type")) != scope:
                continue
            if entry.get("type") != memory_type:
                continue
            if self._entry_category(entry) != category:
                continue
            entry_key = str(entry.get("canonical_key") or self._canonical_key_for(entry))
            if entry_key == canonical_key or self._near_duplicate_text(self._plain_content(entry), content):
                return entry
        return None

    def _model_update_changes(self, entry, operation, metadata):
        changes = {}
        content = self._strip_user_work_artifact(
            operation.get("content", self._plain_content(entry))
        )
        if not content:
            return {}
        category = str(operation.get("category", self._entry_category(entry)) or "").strip().lower()
        classification = self.classify_content(content, category)
        if not classification.get("store_allowed", True):
            return {}
        if metadata.get("recall_policy") == "always" and (
            classification["category"] != "preference"
            or classification["sensitivity"] == "sensitive"
        ):
            metadata["recall_policy"] = "relevant"
        if self._canonical_memory_text(content) != self._canonical_memory_text(self._plain_content(entry)):
            changes["content"] = content
        if "subject" in operation:
            subject = self._strip_user_work_artifact(operation.get("subject"))[:120] or self._derive_subject(content)
            if self._canonical_memory_text(subject) != self._canonical_memory_text(entry.get("subject") or ""):
                changes["subject"] = subject
        memory_type = self._model_memory_type(operation)
        if "memory_type" in operation and memory_type != entry.get("type"):
            changes["memory_type"] = memory_type
        if "scope" in operation:
            scope = self._model_memory_scope(operation, memory_type)
            if scope != self._canonical_scope(entry.get("scope"), entry.get("type")):
                changes["scope"] = scope
        if "category" in operation and classification["category"] != self._entry_category(entry):
            changes["category"] = classification["category"]
        if "importance" in operation:
            importance = max(1, min(5, int(float(operation.get("importance") or 3))))
            if importance != int(entry.get("importance", 3) or 3):
                changes["importance"] = importance
        if "confidence" in operation:
            confidence = max(0.0, min(1.0, float(operation.get("confidence") or 0.75)))
            if abs(confidence - float(entry.get("confidence", 0.75) or 0.75)) >= 0.01:
                changes["confidence"] = confidence
        if "tags" in operation:
            tags = self._coerce_tags(operation.get("tags"))
            if set(tags) != set(entry.get("tags", []) or []):
                changes["tags"] = tags
        if "volatile" in operation and bool(operation.get("volatile")) != bool(entry.get("volatile")):
            changes["volatile"] = bool(operation.get("volatile"))
        existing_metadata = self._entry_metadata(entry)
        retrieval_metadata_changed = any(
            key in operation
            for key in ("recall_policy", "retrieval_policy", "application", "retrieval_hints")
        ) and any(
            metadata.get(key) != existing_metadata.get(key)
            for key in ("recall_policy", "retrieval_hints")
        )
        # A model-generated timestamp by itself must not keep refreshing a memory.
        # Validity changes are applied only when the model explicitly marks them intentional.
        if "expires_at" in operation and (changes or operation.get("refresh_validity") is True):
            expiry = self._parse_dt(operation.get("expires_at"))
            normalized_expiry = expiry.isoformat(timespec="seconds") if expiry else None
            if normalized_expiry != entry.get("expires_at"):
                changes["expires_at"] = normalized_expiry
        if changes or retrieval_metadata_changed:
            changes["metadata"] = metadata
            changes["updated_at"] = operation.get("updated_at") or self._now_iso()
            changes["last_source"] = "model_semantic_memory"
            if operation.get("tool_name"):
                changes["tool_name"] = operation.get("tool_name")
        return changes

    def apply_model_memory_operations(self, operations, *, session_id=""):
        """Apply model-authored semantic operations; return only actual data changes."""
        result = {"changed": False, "count": 0, "actions": [], "memory_ids": [], "skipped": 0}
        cfg = self._settings()
        if not cfg.get("enabled", True):
            return result
        for operation in list(operations or [])[:6]:
            if not isinstance(operation, dict):
                result["skipped"] += 1
                continue
            action = str(operation.get("action") or "").strip().lower()
            try:
                with self._lock:
                    if action == "add":
                        content = self._strip_user_work_artifact(operation.get("content"))
                        if not content:
                            result["skipped"] += 1
                            continue
                        memory_type = self._model_memory_type(operation)
                        scope = self._model_memory_scope(operation, memory_type)
                        classification = self.classify_content(content, operation.get("category", ""))
                        if not classification.get("store_allowed", True):
                            result["skipped"] += 1
                            continue
                        expiry = self._parse_dt(operation.get("expires_at"))
                        if bool(operation.get("volatile")) and expiry is None:
                            result["skipped"] += 1
                            continue
                        if expiry is not None and expiry <= datetime.now():
                            result["skipped"] += 1
                            continue
                        duplicate = self._find_model_memory_duplicate(
                            content,
                            memory_type=memory_type,
                            category=classification["category"],
                            scope=scope,
                        )
                        if duplicate is not None:
                            result["skipped"] += 1
                            continue
                        metadata = self._model_memory_metadata(
                            operation,
                            session_id=session_id,
                            memory_type=memory_type,
                            category=classification["category"],
                            sensitivity=classification["sensitivity"],
                        )
                        memory_id = self.add(
                            memory_type,
                            content,
                            subject=operation.get("subject", ""),
                            tags=operation.get("tags", []),
                            importance=operation.get("importance", 3),
                            source="model_semantic_memory",
                            confidence=operation.get("confidence", 0.75),
                            scope=scope,
                            tool_name=operation.get("tool_name", ""),
                            volatile=bool(operation.get("volatile", False)),
                            metadata=metadata,
                            category=classification["category"],
                            consent_state="approved",
                            cloud_allowed=True,
                            created_at=operation.get("created_at", ""),
                            updated_at=operation.get("updated_at", ""),
                            expires_at=operation.get("expires_at", ""),
                        )
                    elif action == "update":
                        entry = self._resolve_model_memory_target(operation)
                        if entry is None:
                            result["skipped"] += 1
                            continue
                        metadata = self._model_memory_metadata(
                            operation,
                            session_id=session_id,
                            memory_type=entry.get("type", ""),
                            category=self._entry_category(entry),
                            sensitivity=self._entry_sensitivity(entry),
                            existing_metadata=self._entry_metadata(entry),
                        )
                        changes = self._model_update_changes(entry, operation, metadata)
                        if not changes:
                            result["skipped"] += 1
                            continue
                        resulting_volatile = bool(changes.get("volatile", entry.get("volatile")))
                        resulting_expiry = self._parse_dt(
                            changes.get("expires_at", entry.get("expires_at"))
                        )
                        if resulting_volatile and resulting_expiry is None:
                            result["skipped"] += 1
                            continue
                        if resulting_expiry is not None and resulting_expiry <= datetime.now():
                            result["skipped"] += 1
                            continue
                        memory_id = str(entry.get("id") or "")
                        self.edit_entry(
                            memory_id,
                            expected_version=entry.get("version"),
                            user_authorized=True,
                            **changes,
                        )
                    elif action == "delete":
                        entry = self._resolve_model_memory_target(operation)
                        if entry is None:
                            result["skipped"] += 1
                            continue
                        memory_id = str(entry.get("id") or "")
                        if not self.forget(memory_id):
                            result["skipped"] += 1
                            continue
                    else:
                        result["skipped"] += 1
                        continue
                result["changed"] = True
                result["count"] += 1
                result["actions"].append(action)
                result["memory_ids"].append(memory_id)
            except Exception as exc:
                result["skipped"] += 1
                logging.warning("Model memory %s operation ignored: %s", action or "unknown", exc)
        return result

    def auto_capture_turn(self, user_text, final_response, tool_records=None, is_background_task=False):
        """Deprecated compatibility shim; mechanical turn capture is disabled."""
        return []
    def tool_search_text(self, query, memory_type="any", max_results=6):
        if not self._settings().get("enabled", True):
            return "MEMORY_DISABLED"
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
                if os.path.abspath(self.path) == os.path.abspath(UNIFIED_LOG_FILE):
                    logging.info("AUDIT | %s", line)
                else:
                    # Retain deterministic behavior for isolated integrations
                    # and tests which intentionally supply a custom sink.
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(line + "\n")
        except Exception as e:
            logging.exception("Audit log failed for event=%s: %s", event, e)


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
