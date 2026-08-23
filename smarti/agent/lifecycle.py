"""SmartiCore startup, extension catalog, trust, and basic path helpers."""
from .shared import *
from contextlib import contextmanager


class LifecycleMixin:
    _RUN_LOCAL_FIELDS = frozenset({
        "mode", "universal_client", "_universal_client_key",
        "codex_signin_provider",
        "system_prompt", "gemini_history", "universal_history",
        "recent_tool_observations", "tool_observations",
        "conversation_attachments", "conversation_summary",
        "tool_context_transcript", "_last_memory_update_result",
        "_pending_canvas_artifacts", "_current_agent_process_events",
        "_current_agent_process_started_at", "status_callback",
        "print_callback", "ask_user_callback", "api_key_callback",
        "step_callback",
        "_held_resource_locks",
    })

    def __getattribute__(self, name):
        if name in LifecycleMixin._RUN_LOCAL_FIELDS:
            try:
                execution_context = object.__getattribute__(self, "_execution_context")
                values = getattr(execution_context, "run_values", None)
                if isinstance(values, dict) and name in values:
                    return values[name]
            except (AttributeError, RuntimeError):
                pass
        return super().__getattribute__(name)

    def __setattr__(self, name, value):
        if name in LifecycleMixin._RUN_LOCAL_FIELDS:
            try:
                execution_context = object.__getattribute__(self, "_execution_context")
                values = getattr(execution_context, "run_values", None)
                if isinstance(values, dict):
                    values[name] = value
                    return
            except (AttributeError, RuntimeError):
                pass
        super().__setattr__(name, value)

    def _migrate_legacy_runtime_state(self):
        migrate_legacy_runtime_state()

    def __init__(
        self, *, local_gateway_token=None, local_gateway_port=None,
        local_gateway_required=False,
    ):
        self._migrate_legacy_runtime_state()
        self.settings_manager = SettingsManager(SETTINGS_FILE, DEFAULT_SETTINGS)
        self.settings = self._load_settings()
        self._secrets_pending_deletion = set()
        # Compatibility attribute retained for extensions written against the
        # former session-scoped design. The selected mode is now authoritative.
        self._ssl_legacy_insecure_session_enabled = (
            normalize_ssl_trust_mode(self.settings.get("ssl_trust_mode"))
            == SSL_MODE_LEGACY_INSECURE
        )
        self._ssl_last_certificate_error = ""
        _CURRENT_SETTINGS_REF["settings"] = self.settings
        self.chat_store = ChatSessionStore(CHAT_HISTORY_FILE)
        self.chat_store.ensure_active_session()
        self._pending_canvas_artifacts = []
        self._sync_ssl_compat_env()
        if self._normalize_autonomy_profile_settings():
            self._save_settings()
        self.installed_apps_cache = None
        self.installed_apps_index = None
        self.installed_apps_cache_at = 0
        self.browser_process = None
        self.browser_controller = SmartiBrowserController(self)
        self._execution_context = threading.local()
        self._background_threads = {}
        self._agent_lock = threading.RLock()
        self._conversation_locks = {}
        self._conversation_locks_guard = threading.RLock()
        self._resource_locks = {
            "browser": threading.Lock(),
            "computer": threading.Lock(),
        }
        self._background_lock = threading.RLock()
        self._active_process_lock = threading.RLock()
        self._tool_context_lock = threading.RLock()
        self._task_checkpoint_lock = threading.RLock()
        self._title_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="smarti-title",
        )
        self._pending_title_sessions = set()
        self._pending_title_lock = threading.RLock()
        self._usage_lock = threading.RLock()
        self._active_processes = set()
        self._active_processes_by_run = {}
        self._foreground_cancel_event = None
        self.cancel_event = threading.Event()
        self.recent_tool_observations = []
        self.tool_observations = []
        self.conversation_attachments = []
        self.conversation_summary = ""
        self.tool_context_transcript = []
        self._last_memory_update_result = {
            "changed": False, "count": 0, "actions": [], "memory_ids": [], "skipped": 0,
        }
        self._ensure_tools_dir()
        self.audit_logger = AuditLogger(AUDIT_LOG_FILE)
        self.policy_engine = PolicyEngine(self)
        self.tool_registry = ToolRegistry(self)
        self.memory_manager = SmartiMemoryManager(self)
        self.agent_runtime = AgentRuntime(self)
        self.mcp_manager = McpManager(self)
        self.skill_manager = SkillManager(self)
        self.background_scheduler = BackgroundScheduler(self)
        self.ui_state = UiState(self)
        # Google Drive is intentionally not initialized while the integration is hidden.
        self.google_drive = None
        self.system_prompt = self._load_system_prompt()
        self.setup_model()
        self._restore_active_chat_context()
        self.status_callback = None
        self.print_callback = None
        self.ask_user_callback = None 
        self.api_key_callback = None
        self.step_callback = None
        self.notification_callback = None
        self.tts_status_callback = None
        self.service_health_callback = None
        self.embedded_browser_activate_callback = None
        self.background_task_start_callback = None
        self.background_task_step_callback = None
        self.background_task_finish_callback = None
        self.tts_lock = threading.Lock()
        self._stop_speech_flag = False
        self._tts_is_playing = False
        self._background_cancel_events = {}
        self._extension_catalog_signature = None
        self._update_tools_config_from_files()
        if self._sync_trusted_mcp_packages():
            self._save_settings()
        self._load_skill_registry()
        self._ensure_mcp_config()
        self._extension_catalog_signature = self._extension_dirs_signature()
        self.system_prompt = self._load_system_prompt()
        self._execute_tool_impl = self.execute_tool
        self.execute_tool = self._execute_tool_with_audit
        self._background_resume_done = False
        from ..run_manager import ConversationRunManager
        self.run_manager = ConversationRunManager(self)
        self.local_gateway = None
        if local_gateway_required or self.settings.get("local_gateway_enabled", True):
            try:
                token = str(local_gateway_token or "")
                if not token:
                    token = self._ensure_secret_loaded("local_gateway_token")
                if not token:
                    token = secrets.token_urlsafe(32)
                    self.settings["local_gateway_token"] = token
                    self._save_settings()
                from ..local_gateway import SmartiLocalGateway
                self.local_gateway = SmartiLocalGateway(
                    self,
                    token,
                    port=(
                        local_gateway_port
                        if local_gateway_port is not None
                        else self.settings.get("local_gateway_port", 8765)
                    ),
                )
                if not self.local_gateway.start() and local_gateway_required:
                    raise RuntimeError("The required loopback control plane did not start")
            except Exception:
                logging.exception("Local gateway initialization failed")
                if local_gateway_required:
                    raise

    def local_gateway_credentials(self):
        gateway = getattr(self, "local_gateway", None)
        if not gateway:
            return None
        return {
            "base_url": f"http://127.0.0.1:{gateway.port}/v1",
            "token": str(gateway.token or ""),
        }

    def shutdown_runtime(self, wait=False):
        gateway = getattr(self, "local_gateway", None)
        if gateway:
            gateway.stop()
        manager = getattr(self, "run_manager", None)
        if manager:
            manager.shutdown(wait=bool(wait))
        self.shutdown_title_generation()

    def _conversation_lock(self, session_id):
        identifier = str(session_id or "__legacy__")
        with self._conversation_locks_guard:
            return self._conversation_locks.setdefault(identifier, threading.RLock())

    def capture_run_model_snapshot(self, provider_mode=None, model_name=None):
        """Freeze provider objects and model identity for one submitted run."""
        provider_mode = normalize_provider_name(
            provider_mode
            or getattr(self, "mode", "")
            or self.settings.get("api_mode", "gemini")
        )
        current_mode = normalize_provider_name(getattr(self, "mode", ""))
        snapshot = {
            "mode": provider_mode,
            "model_name": str(
                model_name
                or self.settings.get(f"selected_{provider_mode}_model")
                or provider_default_model(provider_mode)
                or "Local"
            ),
            "universal_client": None,
            "_universal_client_key": "",
            "codex_signin_provider": None,
        }
        if provider_mode == current_mode:
            snapshot["universal_client"] = getattr(self, "universal_client", None)
            snapshot["_universal_client_key"] = str(
                getattr(self, "_universal_client_key", "") or ""
            )
            snapshot["codex_signin_provider"] = getattr(
                self, "codex_signin_provider", None
            )
        elif provider_mode == CODEX_SIGNIN_PROVIDER:
            try:
                snapshot["codex_signin_provider"] = CodexSignInProvider(USER_DATA_DIR)
            except Exception:
                logging.exception("Could not prepare the submitted Codex runtime")
        return snapshot

    def _build_run_values(
        self, session_id, callbacks=None, exclude_run_id=None,
        runtime_snapshot=None,
    ):
        session = self.chat_store.session_metadata(session_id) or {}
        context = session.get("context", {}) if isinstance(session, dict) else {}
        base_prompt = object.__getattribute__(self, "system_prompt")
        snapshot = runtime_snapshot if isinstance(runtime_snapshot, dict) else {}
        run_mode = normalize_provider_name(
            snapshot.get("mode")
            or object.__getattribute__(self, "mode")
            or self.settings.get("api_mode", "gemini")
        )
        values = {
            "mode": run_mode,
            "universal_client": snapshot.get("universal_client"),
            "_universal_client_key": str(snapshot.get("_universal_client_key") or ""),
            "codex_signin_provider": snapshot.get("codex_signin_provider"),
            "system_prompt": str(context.get("system_prompt") or base_prompt or ""),
            "gemini_history": [],
            "universal_history": [],
            "recent_tool_observations": copy.deepcopy(context.get("recent_tool_observations", [])),
            "tool_observations": copy.deepcopy(context.get("tool_observations", [])),
            "conversation_attachments": normalize_attachments(context.get("conversation_attachments", [])),
            "conversation_summary": str(context.get("conversation_summary", "") or ""),
            "tool_context_transcript": copy.deepcopy(context.get("tool_context_transcript", [])),
            "_last_memory_update_result": {
                "changed": False, "count": 0, "actions": [], "memory_ids": [], "skipped": 0,
            },
            "_pending_canvas_artifacts": [],
            "_current_agent_process_events": [],
            "_current_agent_process_started_at": time.time(),
            "status_callback": None,
            "print_callback": None,
            "ask_user_callback": None,
            "api_key_callback": None,
            "step_callback": None,
            "_held_resource_locks": [],
        }
        saved_mode = normalize_provider_name(context.get("mode", ""))
        messages = self.chat_store.messages(session_id)
        if exclude_run_id:
            messages = [
                message for message in messages
                if str((message.get("metadata") or {}).get("run_id") or "") != str(exclude_run_id)
            ]
        if run_mode == "gemini":
            history = context.get("gemini_history") if saved_mode == "gemini" else None
            if not isinstance(history, list):
                history = self._messages_to_provider_history(messages, provider_mode=run_mode)
            values["gemini_history"] = copy.deepcopy(history)
        else:
            history = context.get("universal_history") if saved_mode != "gemini" else None
            if not isinstance(history, list) or not history:
                history = self._messages_to_provider_history(messages, provider_mode=run_mode)
            history = [copy.deepcopy(item) for item in history if isinstance(item, dict) and item.get("role") != "system"]
            history.insert(0, {"role": "system", "content": values["system_prompt"]})
            values["universal_history"] = history
        if isinstance(callbacks, dict):
            for name in ("status_callback", "print_callback", "ask_user_callback", "api_key_callback", "step_callback"):
                if name in callbacks:
                    values[name] = callbacks[name]
        return values

    @contextmanager
    def bind_run_context(
        self, run_id, session_id, cancel_event=None, callbacks=None,
        runtime_snapshot=None,
    ):
        """Bind all mutable conversation state to the current worker thread."""
        execution_context = self._execution_context
        previous = {
            "run_values": getattr(execution_context, "run_values", None),
            "run_id": getattr(execution_context, "run_id", None),
            "target_session_id": getattr(execution_context, "target_session_id", None),
            "cancel_event": getattr(execution_context, "cancel_event", None),
            "model_name": getattr(execution_context, "model_name", None),
        }
        execution_context.run_values = self._build_run_values(
            session_id,
            callbacks=callbacks,
            exclude_run_id=run_id,
            runtime_snapshot=runtime_snapshot,
        )
        execution_context.run_id = str(run_id or "")
        execution_context.target_session_id = str(session_id or "")
        execution_context.cancel_event = cancel_event or threading.Event()
        execution_context.model_name = str(
            (runtime_snapshot or {}).get("model_name")
            or self.settings.get(f"selected_{self.mode}_model")
            or provider_default_model(self.mode)
            or "Local"
        )
        try:
            self.system_prompt = self._load_system_prompt()
            yield execution_context.run_values
        finally:
            held = list(getattr(execution_context, "run_values", {}).get("_held_resource_locks", []))
            for lock in reversed(held):
                try:
                    lock.release()
                except RuntimeError:
                    pass
            for name, value in previous.items():
                if value is None:
                    try:
                        delattr(execution_context, name)
                    except AttributeError:
                        pass
                else:
                    setattr(execution_context, name, value)

    @contextmanager
    def run_resource_guard(self, resource_name):
        """Lease a singleton desktop resource for the lifetime of a managed run."""
        lock = self._resource_locks.setdefault(str(resource_name), threading.Lock())
        values = getattr(self._execution_context, "run_values", None)
        if isinstance(values, dict):
            held = values.setdefault("_held_resource_locks", [])
            if lock not in held:
                lock.acquire()
                held.append(lock)
            yield
            return
        with lock:
            yield

    def set_callbacks(self, status_cb, print_cb, ask_user_cb=None, step_cb=None, api_key_cb=None):
        self.status_callback = status_cb
        self.print_callback = print_cb
        if ask_user_cb: self.ask_user_callback = ask_user_cb
        if step_cb: self.step_callback = step_cb
        if api_key_cb: self.api_key_callback = api_key_cb

    def _emit_notification(self, kind, payload=None):
        callback = getattr(self, "notification_callback", None)
        if not callback:
            return False
        try:
            callback(kind, payload or {})
            return True
        except Exception:
            logging.exception("Notification callback failed.")
            return False

    def shutdown_title_generation(self):
        executor = getattr(self, "_title_executor", None)
        if executor is None:
            return
        self._title_executor = None
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            logging.exception("Could not stop the conversation-title executor cleanly.")

    def _ensure_tools_dir(self):
        if not os.path.exists(TOOLS_DIR): os.makedirs(TOOLS_DIR)
        if not os.path.exists(MCP_TOOLS_DIR): os.makedirs(MCP_TOOLS_DIR)
        if not os.path.exists(SKILLS_DIR): os.makedirs(SKILLS_DIR)
        if not os.path.exists(ATTACHMENTS_DIR): os.makedirs(ATTACHMENTS_DIR)
        if not os.path.exists(ASSETS_DIR): os.makedirs(ASSETS_DIR)
        if not os.path.exists(OUTPUTS_DIR): os.makedirs(OUTPUTS_DIR)

    def _extension_dirs_signature(self):
        signature = []
        roots = (
            (TOOLS_DIR, {".py", ".pyw", ".txt", ".json"}),
            (MCP_TOOLS_DIR, {".txt", ".pyw", ".json"}),
            (SKILLS_DIR, None),
        )
        for root, extensions in roots:
            try:
                root_abs = os.path.abspath(root)
                if not os.path.isdir(root_abs):
                    signature.append((root_abs, "missing"))
                    continue
                for cur, dirs, files in os.walk(root_abs):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    rel = os.path.relpath(cur, root_abs)
                    try:
                        signature.append((root_abs, rel, "dir", int(os.path.getmtime(cur))))
                    except Exception:
                        pass
                    for file in sorted(files):
                        ext = os.path.splitext(file)[1].lower()
                        if extensions is not None and ext not in extensions:
                            continue
                        path = os.path.join(cur, file)
                        try:
                            stat = os.stat(path)
                            signature.append((root_abs, rel, file, int(stat.st_mtime), int(stat.st_size)))
                        except Exception:
                            signature.append((root_abs, rel, file, "stat_error"))
            except Exception as exc:
                signature.append((str(root), "error", type(exc).__name__))
        return tuple(signature)

    def refresh_extension_catalogs(self, force=False, rebuild_prompt=True):
        self._ensure_tools_dir()
        signature = self._extension_dirs_signature()
        if not force and signature == getattr(self, "_extension_catalog_signature", None):
            return False
        if getattr(self, "tool_registry", None):
            self.tool_registry.ensure_registries()
        self._update_tools_config_from_files()
        self._load_skill_registry()
        self._sync_trusted_mcp_packages()
        self._ensure_mcp_config()
        self._extension_catalog_signature = signature
        if rebuild_prompt:
            self.system_prompt = self._load_system_prompt()
        self._emit_notification("extensions_changed", {"forced": bool(force)})
        return True

    def refresh_extension_catalogs_if_changed(self, rebuild_prompt=True):
        if not self.settings.get("skills_load_watch", True):
            return False
        return self.refresh_extension_catalogs(force=False, rebuild_prompt=rebuild_prompt)

    def _tool_context_guard(self):
        lock = getattr(self, "_tool_context_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._tool_context_lock = lock
        return lock

    def _looks_environment_dependent_query(self, query):
        text = str(query or "").lower()
        if not text.strip():
            return False
        if getattr(self, "memory_manager", None) and self.memory_manager._looks_live_or_temporal(text):
            return True
        current_terms = {
            "current", "currently", "now", "latest", "today", "status", "exists",
            "file", "files", "folder", "directory", "path", "screen", "window",
            "process", "processes", "installed", "log", "logs", "email", "inbox",
            "weather", "price", "schedule", "availability",
            "כרגע", "עכשיו", "היום", "עדכני", "אחרון", "סטטוס", "מצב",
            "קובץ", "קבצים", "תיקייה", "תיקיה", "נתיב", "מסך", "חלון",
            "תהליך", "תהליכים", "מותקן", "לוג", "לוגים", "אימייל", "מייל",
            "קיים", "נמצא", "רשימה", "תחזית", "מחיר", "זמינות"
        }
        return any(term in text for term in current_terms)

    def _normalize_autonomy_profile_settings(self):
        if self.settings.get("custom_permission_profile_enabled", False):
            changed = False
            try:
                level = int(self.settings.get("permission_level", 2) or 2)
            except Exception:
                level = 2
            if level not in {1, 2, 3}:
                self.settings["permission_level"] = 2
                changed = True
            if self.settings.get("autonomy_mode") != "custom":
                self.settings["autonomy_mode"] = "custom"
                changed = True
            self._normalize_policy_matrix()
            return changed
        key = self.settings.get("autonomy_mode", "balanced")
        profile = AUTONOMY_PROFILES.get(key)
        if not profile:
            try:
                level = int(self.settings.get("permission_level", 2) or 2)
            except Exception:
                level = 2
            key = {1: "locked_down", 2: "balanced", 3: "max_autonomy"}.get(level, "balanced")
            self.settings["autonomy_mode"] = key
            profile = AUTONOMY_PROFILES[key]
        changed = False

        if self.settings.get("permission_level") != profile["permission_level"]:
            self.settings["permission_level"] = profile["permission_level"]
            changed = True

        if key == "max_autonomy":
            matrix = self.settings.setdefault("policy_matrix", {})
            for cap in DEFAULT_POLICY_MATRIX:
                if matrix.get(cap) != "deny" and matrix.get(cap) != "allow":
                    matrix[cap] = "allow"
                    changed = True
            for setting_key in (
                "raw_shell_requires_approval",
                "marketplace_install_requires_approval",
                "require_approval_for_cloud_upload",
                "write_outside_allowed_dirs_requires_approval"
            ):
                if self.settings.get(setting_key) != profile[setting_key]:
                    self.settings[setting_key] = profile[setting_key]
                    changed = True
        return changed

    def set_tool_trust(self, kind, name, trusted, metadata=None):
        if not getattr(self, "tool_registry", None):
            return
        self.tool_registry.set_trust(kind, name, trusted, metadata=metadata)
        if kind == "custom":
            self.settings.setdefault("tools_config", {})[name] = bool(trusted)
        elif kind == "mcp":
            stem = mcp_pkg_to_file_stem(name)
            self.settings.setdefault("tools_config", {})[f"mcp_{stem}"] = bool(trusted)
            self._sync_trusted_mcp_packages()
            self._ensure_mcp_config()
        elif kind == "skill":
            self.settings.setdefault("skills_config", {})[name] = bool(trusted)
        self._save_settings()

    def _settings_trust_key(self, kind, name):
        if getattr(self, "tool_registry", None):
            return self.tool_registry._trust_key(kind, name)
        return f"{kind}:{safe_filename(name, kind)}"

    def _artifact_child_path(self, root, *parts):
        root_path = Path(root).resolve()
        target = root_path.joinpath(*[str(part) for part in parts]).resolve()
        if target != root_path and root_path not in target.parents:
            raise ValueError("Refusing to delete outside Smarti artifact directory.")
        return str(target)

    def _delete_artifact_file(self, root, filename, deleted):
        path = self._artifact_child_path(root, filename)
        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
            deleted.append(path)
        return path

    def _remove_tool_trust(self, kind, *names):
        trust = self.settings.setdefault("tool_trust", {})
        for name in names:
            if str(name or "").strip():
                trust.pop(self._settings_trust_key(kind, name), None)

    def delete_external_tool_artifact(self, kind, name):
        kind = str(kind or "").strip().lower()
        raw_name = str(name or "").strip()
        if kind == "custom":
            return self._delete_custom_tool_artifact(raw_name)
        if kind == "mcp":
            return self._delete_mcp_artifact(raw_name)
        if kind == "skill":
            return self._delete_skill_artifact(raw_name)
        return f"ERROR: Unsupported artifact type: {kind}"

    def _delete_custom_tool_artifact(self, name):
        tool_name = safe_filename(name, "tool")
        if not tool_name:
            return "ERROR: Missing tool name."
        os.makedirs(TOOLS_DIR, exist_ok=True)
        deleted = []
        for suffix in (".pyw", ".txt", ".manifest.json"):
            self._delete_artifact_file(TOOLS_DIR, f"{tool_name}{suffix}", deleted)
        pycache_dir = self._artifact_child_path(TOOLS_DIR, "__pycache__")
        if os.path.isdir(pycache_dir):
            for pattern in (f"{tool_name}.*.pyc", f"{tool_name}.pyc"):
                for path in glob.glob(os.path.join(pycache_dir, pattern)):
                    if self._path_in_roots(path, [pycache_dir]) and os.path.isfile(path):
                        os.remove(path)
                        deleted.append(path)
        self.settings.setdefault("tools_config", {}).pop(tool_name, None)
        self._remove_tool_trust("custom", tool_name)
        if getattr(self, "audit_logger", None):
            self.audit_logger.record("external_artifact_deleted", {"kind": "custom", "name": tool_name, "files": len(deleted)}, self.settings)
        self._save_settings()
        if not deleted:
            return f"ERROR: לא נמצאו קבצי כלי למחיקה עבור {tool_name}."
        return f"SUCCESS: נמחק כלי Python מותאם '{tool_name}' ({len(deleted)} קבצים)."

    def _delete_mcp_artifact(self, name):
        stem = mcp_pkg_to_file_stem(name)
        if not stem:
            return "ERROR: Missing MCP name."
        os.makedirs(MCP_TOOLS_DIR, exist_ok=True)
        registry = self.settings.setdefault("mcp_registry", {})
        entry = registry.get(stem, {}) if isinstance(registry.get(stem, {}), dict) else {}
        candidates = {stem, safe_filename(name, ""), mcp_pkg_to_file_stem(name)}
        for value in (entry.get("name", ""), entry.get("base_package", "")):
            if str(value or "").strip():
                candidates.add(mcp_pkg_to_file_stem(value))
        candidates = {safe_filename(item, "") for item in candidates if str(item or "").strip()}
        deleted = []
        for candidate in sorted(candidates):
            self._delete_artifact_file(MCP_TOOLS_DIR, f"{candidate}.txt", deleted)
            self._delete_artifact_file(MCP_TOOLS_DIR, f"{candidate}.pyw", deleted)
            self.settings.setdefault("tools_config", {}).pop(f"mcp_{candidate}", None)
            registry.pop(candidate, None)
            self._remove_tool_trust("mcp", candidate)

        aliases = self.settings.setdefault("mcp_package_aliases", {})
        package_configs = self.settings.setdefault("mcp_package_configs", {})
        package_candidates = set(candidates)
        for item in (entry.get("name", ""), entry.get("base_package", ""), name):
            if str(item or "").strip():
                package_candidates.add(str(item).strip())
                package_candidates.add(mcp_pkg_to_file_stem(item))
        for key in list(aliases.keys()):
            value = str(aliases.get(key, "") or "")
            if key in package_candidates or value in package_candidates or mcp_pkg_to_file_stem(value) in package_candidates:
                aliases.pop(key, None)
        for key in list(package_configs.keys()):
            if key in package_candidates or mcp_pkg_to_file_stem(key) in package_candidates:
                package_configs.pop(key, None)
        allowed = []
        for pkg in self.settings.get("allowed_mcp_packages", []):
            pkg_text = str(pkg or "").strip()
            if pkg_text and pkg_text not in package_candidates and mcp_pkg_to_file_stem(pkg_text) not in package_candidates:
                allowed.append(pkg)
        self.settings["allowed_mcp_packages"] = allowed
        self._ensure_mcp_config()
        if getattr(self, "audit_logger", None):
            self.audit_logger.record("external_artifact_deleted", {"kind": "mcp", "name": stem, "files": len(deleted)}, self.settings)
        self._save_settings()
        if not deleted:
            return f"ERROR: לא נמצאו קבצי MCP למחיקה עבור {stem}."
        return f"SUCCESS: נמחקה חבילת MCP '{stem}' ({len(deleted)} קבצים)."

    def _delete_skill_artifact(self, name):
        skill_name = safe_filename(name, "skill")
        if not skill_name:
            return "ERROR: Missing Skill name."
        registry = getattr(self, "skill_registry", None) or self._load_skill_registry()
        spec = registry.get(skill_name, {})
        if spec.get("source") == "builtin":
            return "ERROR: אי אפשר למחוק Skill מובנה."
        skill_path = spec.get("path") or os.path.join(SKILLS_DIR, skill_name)
        target = Path(self._abs_path(skill_path)).resolve()
        root = Path(SKILLS_DIR).resolve()
        if target == root or root not in target.parents:
            return "ERROR: Refusing to delete Skill outside Smarti skills directory."
        if not target.is_dir():
            return f"ERROR: תיקיית ה-Skill לא נמצאה: {skill_path}"
        shutil.rmtree(str(target))
        self.settings.setdefault("skills_config", {}).pop(skill_name, None)
        self.settings.setdefault("skill_registry", {}).pop(skill_name, None)
        self._remove_tool_trust("skill", skill_name)
        self._load_skill_registry()
        if getattr(self, "audit_logger", None):
            self.audit_logger.record("external_artifact_deleted", {"kind": "skill", "name": skill_name, "path": str(target)}, self.settings)
        self._save_settings()
        return f"SUCCESS: נמחק Skill '{skill_name}'."

    def _sync_trusted_mcp_packages(self):
        if not getattr(self, "tool_registry", None):
            return False
        changed = False
        registry = self.settings.setdefault("mcp_registry", {})
        tools_config = self.settings.setdefault("tools_config", {})
        known_stems = set(registry.keys())
        if os.path.exists(MCP_TOOLS_DIR):
            known_stems.update(f[:-4] for f in os.listdir(MCP_TOOLS_DIR) if f.endswith(".txt"))

        allowed = [str(pkg).strip() for pkg in self.settings.get("allowed_mcp_packages", []) if str(pkg).strip()]
        allowed_set = set(allowed)

        for stem in sorted(known_stems):
            entry = registry.setdefault(stem, {"name": stem})
            trust = self.tool_registry.trust_status("mcp", stem)
            enabled = bool(tools_config.get(f"mcp_{stem}", trust == "trusted"))
            if entry.get("trust") != trust:
                entry["trust"] = trust
                changed = True

            candidates = {stem, str(entry.get("name", "")).strip(), str(entry.get("base_package", "")).strip()}
            candidates = {pkg for pkg in candidates if pkg}
            if trust == "trusted" and enabled:
                for pkg in sorted(candidates):
                    if pkg not in allowed_set:
                        allowed.append(pkg)
                        allowed_set.add(pkg)
                        changed = True
            else:
                new_allowed = [pkg for pkg in allowed if pkg not in candidates]
                if len(new_allowed) != len(allowed):
                    allowed = new_allowed
                    allowed_set = set(allowed)
                    changed = True

        if self.settings.get("allowed_mcp_packages", []) != allowed:
            self.settings["allowed_mcp_packages"] = allowed
            changed = True
        return changed

    def _timeout(self, key, default):
        try: return max(5, int(self.settings.get(key, default)))
        except Exception: return default

    def _python_executable(self):
        return SMARTI_RUNTIME.python_executable(prefer_console=True)

    def _truncate_tool_output(self, text):
        limit = self._timeout("max_tool_output_chars", 100000)
        text = "" if text is None else str(text)
        if len(text) <= limit: return text
        return text[:limit] + f"\n\n[TRUNCATED: הוחזרו רק {limit} התווים הראשונים מתוך {len(text)} כדי לשמור על יציבות הלולאה.]"
