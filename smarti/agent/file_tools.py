"""Safe, structured filesystem operations for ``file_manager``."""
from .shared import *

import codecs
import errno
import fnmatch
import struct
import stat as stat_module


FILE_MANAGER_READ_ACTIONS = {
    "list_directory",
    "search_files",
    "tree",
    "stat",
    "exists",
    "hash",
    "compare",
    "diff_text",
    "read_chunk",
    "disk_usage",
}

FILE_MANAGER_MUTATING_ACTIONS = {
    "mkdir",
    "copy",
    "move",
    "rename",
    "atomic_write_text",
    "append_text",
    "touch",
    "trash",
    "restore_from_trash",
    "zip",
    "unzip",
}

FILE_MANAGER_BATCH_ACTIONS = FILE_MANAGER_MUTATING_ACTIONS - {"restore_from_trash"}
FILE_MANAGER_CONFLICTS = {"fail", "rename", "overwrite"}
FILE_MANAGER_HASH_ALGORITHMS = {"sha256", "sha512", "blake2b"}
FILE_MANAGER_ENCODINGS = {
    "utf-8",
    "utf-8-sig",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "ascii",
    "latin-1",
    "cp1252",
    "cp1255",
}

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_WINDOWS_REPARSE_ATTRIBUTE = 0x400
_WINDOWS_HIDDEN_ATTRIBUTE = 0x2
_WINDOWS_READONLY_ATTRIBUTE = 0x1
_WINDOWS_DIRECTORY_ATTRIBUTE = 0x10
_FILE_CHUNK_SIZE = 1024 * 1024
_MAX_READ_CHUNK = 1024 * 1024
_MAX_DIFF_INPUT = 2 * 1024 * 1024
_MAX_ARCHIVE_ENTRIES = 10000
_MAX_ARCHIVE_UNCOMPRESSED = 4 * 1024 * 1024 * 1024
_MAX_FILE_QUERY_RESULTS = 10000
_MAX_FILE_QUERY_SCAN = 1000000
_MAX_FILE_QUERY_OUTPUT_CHARS = 10 * 1024 * 1024
_FILE_QUERY_FIELDS = {
    "path",
    "name",
    "relative_path",
    "extension",
    "depth",
    "exists",
    "type",
    "size",
    "created_at",
    "modified_at",
    "accessed_at",
    "hidden",
    "read_only",
    "is_symlink",
    "is_reparse_point",
    "link_target",
    "windows_kind",
    "mime_type",
    "title",
    "authors",
    "tags",
    "search_rank",
}
_FILE_QUERY_DETAIL_FIELDS = {
    "minimal": ("relative_path", "type"),
    "standard": ("relative_path", "type", "size", "modified_at"),
    "full": (
        "path",
        "name",
        "relative_path",
        "extension",
        "depth",
        "exists",
        "type",
        "size",
        "created_at",
        "modified_at",
        "accessed_at",
        "hidden",
        "read_only",
        "is_symlink",
        "is_reparse_point",
        "link_target",
        "windows_kind",
        "mime_type",
        "title",
        "authors",
        "tags",
        "search_rank",
    ),
}
_WINDOWS_SEARCH_COLUMNS = {
    "name": ("System.FileName", "text"),
    "extension": ("System.FileExtension", "text"),
    "size": ("System.Size", "size"),
    "created": ("System.DateCreated", "date"),
    "modified": ("System.DateModified", "date"),
    "accessed": ("System.DateAccessed", "date"),
    "kind": ("System.Kind", "text"),
    "mime_type": ("System.MIMEType", "text"),
    "title": ("System.Title", "text"),
    "author": ("System.Author", "text"),
    "tags": ("System.Keywords", "text"),
    "subject": ("System.Subject", "text"),
    "owner": ("System.FileOwner", "text"),
    "content": ("System.Search.Contents", "text"),
}
_WINDOWS_SEARCH_TEXT_OPERATORS = {"eq", "ne", "contains", "freetext", "prefix"}
_WINDOWS_SEARCH_ORDERED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte"}
_PUBLIC_PATH_KEYS = {
    "path", "paths", "source", "sources", "destination", "reads", "writes",
    "original_path", "metadata_path", "data_path", "link_target",
}


class _WindowsSearchUnavailable(RuntimeError):
    """Windows Search could not execute the requested indexed query."""


class FileToolsMixin:
    """Implementation behind the complete public ``file_manager`` contract."""

    def file_manager_operation(self, args):
        args = dict(args or {})
        action = str(args.get("action") or "").strip().lower()
        if action not in FILE_MANAGER_READ_ACTIONS | FILE_MANAGER_MUTATING_ACTIONS | {"batch"}:
            return f"ERROR: Unsupported file_manager action: {action or '(missing)'}"

        idempotency_key = str(args.get("idempotency_key") or "").strip()
        args_hash = hashlib.sha256(
            json.dumps(
                {key: value for key, value in args.items() if key != "idempotency_key"},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        cached = self._fm_idempotency_lookup(idempotency_key, args_hash)
        if cached is not None:
            return cached

        try:
            if action in FILE_MANAGER_READ_ACTIONS:
                result = self._fm_execute_read(action, args)
            elif action == "batch":
                result = self._fm_execute_batch(args)
            else:
                plan = self._fm_plan_mutation(action, args)
                self._fm_validate_plan_paths(plan)
                if bool(args.get("dry_run", False)):
                    result = {
                        "ok": True,
                        "status": "dry_run",
                        "action": action,
                        "plan": self._fm_public_plan(plan),
                    }
                else:
                    allowed, error = self._fm_authorize_plans([plan], action)
                    if not allowed:
                        return error
                    result = self._fm_execute_mutation(plan)
            result = self._fm_public_result(result)
            if action in {"search_files", "tree"}:
                output = json.dumps(
                    result,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                )
            else:
                output = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        except SmartiCancelled:
            raise
        except Exception as exc:
            output = f"ERROR: {type(exc).__name__}: {exc}"

        self._fm_idempotency_store(idempotency_key, args_hash, output)
        return output

    def _fm_idempotency_lookup(self, key, args_hash):
        if not key:
            return None
        cache = getattr(self, "_file_manager_idempotency", None)
        if not isinstance(cache, dict):
            cache = {}
            self._file_manager_idempotency = cache
        previous = cache.get(key)
        if not previous:
            return None
        if previous["args_hash"] != args_hash:
            return "ERROR: idempotency_key was already used with different arguments."
        return previous["output"]

    def _fm_idempotency_store(self, key, args_hash, output):
        if not key:
            return
        if str(output).startswith("ERROR:"):
            return
        try:
            payload = json.loads(output)
        except Exception:
            payload = {}
        if isinstance(payload, dict) and payload.get("status") in {"dry_run", "denied"}:
            return
        cache = getattr(self, "_file_manager_idempotency", None)
        if not isinstance(cache, dict):
            cache = {}
            self._file_manager_idempotency = cache
        cache[key] = {"args_hash": args_hash, "output": output, "created_at": time.time()}
        while len(cache) > 256:
            cache.pop(next(iter(cache)))

    def _fm_default_root(self):
        return self._sandbox_root() if self._sandbox_enabled() else self._default_output_dir()

    def _fm_resolve_path(self, value, *, destination=False, source_parent=None):
        raw = str(value or "").strip(' "\'')
        if not raw:
            raise ValueError("A path is required.")
        if "\x00" in raw:
            raise ValueError("A path may not contain a NUL character.")
        expanded = os.path.expandvars(os.path.expanduser(raw))
        if source_parent and not os.path.isabs(expanded) and not os.path.dirname(expanded):
            expanded = os.path.join(source_parent, expanded)
        elif not os.path.isabs(expanded):
            if destination:
                expanded = os.path.join(self._fm_default_root(), expanded)
            else:
                output_candidate = os.path.join(self._fm_default_root(), expanded)
                expanded = output_candidate if os.path.lexists(output_candidate) else expanded
        resolved = os.path.abspath(expanded)
        if os.name == "nt" and not resolved.startswith("\\\\?\\"):
            if destination:
                parent, leaf = os.path.split(resolved)
                resolved = os.path.join(self._fm_expand_windows_long_name(parent), leaf)
            else:
                resolved = self._fm_expand_windows_long_name(resolved)
            resolved = self._fm_extended_windows_path(resolved)
        return resolved

    @staticmethod
    def _fm_extended_windows_path(path, *, force=False):
        absolute = os.path.abspath(path)
        if absolute.startswith("\\\\?\\") or (not force and len(absolute) < 248):
            return absolute
        if absolute.startswith("\\\\"):
            return "\\\\?\\UNC\\" + absolute[2:]
        return "\\\\?\\" + absolute

    @staticmethod
    def _fm_display_path(path):
        text = str(path or "")
        if text.startswith("\\\\?\\UNC\\"):
            return "\\\\" + text[8:]
        if text.startswith("\\\\?\\"):
            return text[4:]
        return text

    def _fm_public_result(self, value, key=None):
        if isinstance(value, dict):
            return {
                item_key: self._fm_public_result(item, item_key)
                for item_key, item in value.items()
            }
        if isinstance(value, list):
            return [self._fm_public_result(item, key) for item in value]
        if isinstance(value, tuple):
            return [self._fm_public_result(item, key) for item in value]
        if isinstance(value, str) and key in _PUBLIC_PATH_KEYS:
            return self._fm_display_path(value)
        return value

    @staticmethod
    def _fm_expand_windows_long_name(path):
        """Expand 8.3 components even when the destination leaf does not exist yet."""
        absolute = os.path.abspath(path)
        existing = absolute
        suffix = []
        while existing and not os.path.lexists(existing):
            parent, name = os.path.split(existing)
            if not name or parent == existing:
                break
            suffix.append(name)
            existing = parent
        if not existing or not os.path.lexists(existing):
            return absolute
        try:
            get_long_path = ctypes.windll.kernel32.GetLongPathNameW
            get_long_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            get_long_path.restype = ctypes.c_uint
            required = get_long_path(existing, None, 0)
            if not required:
                return absolute
            buffer = ctypes.create_unicode_buffer(required + 1)
            written = get_long_path(existing, buffer, len(buffer))
            if not written:
                return absolute
            expanded = buffer.value
            for name in reversed(suffix):
                expanded = os.path.join(expanded, name)
            return expanded
        except Exception:
            return absolute

    def _fm_validate_destination_name(self, path):
        if os.name != "nt":
            return
        path = self._fm_display_path(path)
        drive, tail = os.path.splitdrive(os.path.abspath(path))
        for component in Path(tail).parts:
            if component in {"", os.sep, "\\", "/"}:
                continue
            if component.endswith((" ", ".")):
                raise ValueError(f"Windows destination component may not end in a space or dot: {component}")
            stem = component.split(".", 1)[0].upper()
            if stem in _WINDOWS_RESERVED_NAMES:
                raise ValueError(f"Windows reserved filename is not allowed: {component}")
            if any(ord(char) < 32 or char in '<>:"|?*' for char in component):
                raise ValueError(f"Invalid Windows destination component: {component}")

    @staticmethod
    def _fm_is_reparse(path):
        try:
            entry_stat = os.lstat(path)
        except OSError:
            return False
        attributes = int(getattr(entry_stat, "st_file_attributes", 0) or 0)
        return bool(
            os.path.islink(path)
            or stat_module.S_ISLNK(entry_stat.st_mode)
            or attributes & _WINDOWS_REPARSE_ATTRIBUTE
        )

    @staticmethod
    def _fm_is_hidden(path, entry_stat=None):
        name = os.path.basename(path)
        if name.startswith("."):
            return True
        try:
            entry_stat = entry_stat or os.lstat(path)
        except OSError:
            return False
        return bool(int(getattr(entry_stat, "st_file_attributes", 0) or 0) & _WINDOWS_HIDDEN_ATTRIBUTE)

    def _fm_guard_reparse_ancestors(self, path, *, include_leaf, follow_symlinks):
        if follow_symlinks:
            return
        candidate = os.path.abspath(path)
        if not include_leaf:
            candidate = os.path.dirname(candidate)
        existing = candidate
        while existing and not os.path.lexists(existing):
            parent = os.path.dirname(existing)
            if parent == existing:
                break
            existing = parent
        if not existing:
            return
        anchor = Path(existing).anchor
        current = existing
        checked = []
        while current and current != anchor:
            checked.append(current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        for item in reversed(checked):
            if self._fm_is_reparse(item):
                raise PermissionError(
                    f"Reparse point/symlink traversal is blocked by default: {item}. "
                    "Set follow_symlinks=true only for an explicitly reviewed path."
                )

    def _fm_validate_access_path(self, path, access, *, follow_symlinks=False, include_leaf=True):
        allowed, error = self._ensure_sandbox_path_allowed(self._fm_display_path(path), access)
        if not allowed:
            raise PermissionError(str(error).removeprefix("ERROR:").strip())
        self._fm_guard_reparse_ancestors(
            path,
            include_leaf=include_leaf,
            follow_symlinks=follow_symlinks,
        )

    @staticmethod
    def _fm_iso(timestamp):
        try:
            return datetime.fromtimestamp(timestamp).astimezone().isoformat()
        except Exception:
            return None

    def _fm_stat_path(self, path):
        exists = os.path.lexists(path)
        if not exists:
            return {"path": path, "exists": False}
        info = os.lstat(path)
        is_reparse = self._fm_is_reparse(path)
        if stat_module.S_ISDIR(info.st_mode):
            kind = "directory"
        elif stat_module.S_ISREG(info.st_mode):
            kind = "file"
        elif stat_module.S_ISLNK(info.st_mode):
            kind = "symlink"
        else:
            kind = "other"
        result = {
            "path": path,
            "exists": True,
            "type": kind,
            "size": int(info.st_size),
            "created_at": self._fm_iso(info.st_ctime),
            "modified_at": self._fm_iso(info.st_mtime),
            "accessed_at": self._fm_iso(info.st_atime),
            "hidden": self._fm_is_hidden(path, info),
            "read_only": not os.access(path, os.W_OK),
            "is_symlink": bool(os.path.islink(path)),
            "is_reparse_point": is_reparse,
        }
        if os.path.islink(path):
            try:
                result["link_target"] = os.readlink(path)
            except OSError:
                pass
        return result

    def _fm_stat_dir_entry(self, entry, *, minimal=False):
        """Return traversal or full public metadata using one cached DirEntry stat call."""
        info = entry.stat(follow_symlinks=False)
        attributes = int(getattr(info, "st_file_attributes", 0) or 0)
        is_symlink = bool(entry.is_symlink() or stat_module.S_ISLNK(info.st_mode))
        is_reparse = bool(is_symlink or attributes & _WINDOWS_REPARSE_ATTRIBUTE)
        if stat_module.S_ISDIR(info.st_mode):
            kind = "directory"
        elif stat_module.S_ISREG(info.st_mode):
            kind = "file"
        elif is_symlink:
            kind = "symlink"
        else:
            kind = "other"
        if minimal:
            return {
                "path": entry.path,
                "exists": True,
                "type": kind,
                "hidden": bool(
                    entry.name.startswith(".")
                    or attributes & _WINDOWS_HIDDEN_ATTRIBUTE
                ),
                "is_symlink": is_symlink,
                "is_reparse_point": is_reparse,
            }
        if os.name == "nt":
            read_only = bool(attributes & _WINDOWS_READONLY_ATTRIBUTE)
        else:
            writable_bits = stat_module.S_IWUSR | stat_module.S_IWGRP | stat_module.S_IWOTH
            read_only = not bool(info.st_mode & writable_bits)
        result = {
            "path": entry.path,
            "exists": True,
            "type": kind,
            "size": int(info.st_size),
            "created_at": self._fm_iso(info.st_ctime),
            "modified_at": self._fm_iso(info.st_mtime),
            "accessed_at": self._fm_iso(info.st_atime),
            "hidden": bool(entry.name.startswith(".") or attributes & _WINDOWS_HIDDEN_ATTRIBUTE),
            "read_only": read_only,
            "is_symlink": is_symlink,
            "is_reparse_point": is_reparse,
        }
        if is_symlink:
            try:
                result["link_target"] = os.readlink(entry.path)
            except OSError:
                pass
        return result

    def _fm_read_authorized(self, action, paths, capability, *, follow_symlinks=False):
        for path in paths:
            self._fm_validate_access_path(
                path,
                "read",
                follow_symlinks=follow_symlinks,
                include_leaf=action not in {"exists", "stat"},
            )
        details = "\n".join(f"- {path}" for path in paths[:20])
        allowed, error = self._ensure_capability_allowed(
            capability,
            "אישור קריאת קבצים" if capability == "file_read" else "בדיקת מערכת הקבצים",
            details,
            risk="medium" if capability == "file_read" else "low",
            audit_context={"manager": "file_manager", "sub_action": action},
        )
        if not allowed:
            raise PermissionError(str(error).removeprefix("ERROR:").strip())

    def _fm_execute_read(self, action, args):
        follow = bool(args.get("follow_symlinks", False))
        if action in {"compare", "diff_text"}:
            first = self._fm_resolve_path(args.get("source") or args.get("path"))
            second = self._fm_resolve_path(args.get("destination") or args.get("other_path"))
            paths = [first, second]
        else:
            raw_paths = args.get("paths")
            if isinstance(raw_paths, list) and raw_paths:
                paths = [self._fm_resolve_path(item) for item in raw_paths]
            else:
                paths = [self._fm_resolve_path(args.get("path") or args.get("source"))]
        capability = "file_search" if action in {
            "list_directory", "search_files", "tree", "stat", "exists", "disk_usage"
        } else "file_read"
        self._fm_read_authorized(action, paths, capability, follow_symlinks=follow)

        if len(paths) > 1 and action in {"stat", "exists", "hash", "disk_usage"}:
            items = []
            for path in paths:
                self._raise_if_cancelled()
                try:
                    items.append({"ok": True, **self._fm_read_one(action, path, args)})
                except Exception as exc:
                    items.append({"ok": False, "path": path, "error": f"{type(exc).__name__}: {exc}"})
            return {
                "ok": all(item["ok"] for item in items),
                "status": "success" if all(item["ok"] for item in items) else "partial",
                "action": action,
                "items": items,
            }
        if action == "compare":
            return self._fm_compare(paths[0], paths[1], args)
        if action == "diff_text":
            return self._fm_diff_text(paths[0], paths[1], args)
        return {"ok": True, "action": action, **self._fm_read_one(action, paths[0], args)}

    def _fm_read_one(self, action, path, args):
        if action == "exists":
            return self._fm_stat_path(path)
        if action == "stat":
            return self._fm_stat_path(path)
        if action == "list_directory":
            return self._fm_list_directory(path, args)
        if action == "search_files":
            return self._fm_search_files(path, args)
        if action == "tree":
            return self._fm_tree(path, args)
        if action == "hash":
            algorithm = self._fm_hash_algorithm(args)
            return self._fm_hash_path(path, algorithm, bool(args.get("follow_symlinks", False)))
        if action == "read_chunk":
            return self._fm_read_chunk(path, args)
        if action == "disk_usage":
            return self._fm_disk_usage(path, args)
        raise ValueError(f"Unsupported read action: {action}")

    def _fm_list_directory(self, path, args):
        if not os.path.isdir(path):
            raise NotADirectoryError(path)
        include_hidden = bool(args.get("include_hidden", False))
        limit = max(1, min(int(args.get("limit") or 500), 5000))
        entries = []
        with os.scandir(path) as iterator:
            ordered = sorted(iterator, key=lambda entry: entry.name.casefold())
        for entry in ordered:
            self._raise_if_cancelled()
            info = self._fm_stat_path(entry.path)
            if not include_hidden and info.get("hidden"):
                continue
            entries.append(info)
            if len(entries) >= limit:
                break
        return {
            "path": path,
            "entries": entries,
            "returned": len(entries),
            "truncated": len(entries) < sum(
                1 for entry in ordered
                if include_hidden or not self._fm_is_hidden(entry.path)
            ),
        }

    @staticmethod
    def _fm_arg_present(args, key):
        return key in args and args.get(key) not in (None, "")

    @staticmethod
    def _fm_string_list(value, key):
        if value in (None, ""):
            return []
        values = value if isinstance(value, list) else [value]
        result = []
        for item in values:
            text = str(item or "").strip()
            if text:
                result.append(text)
        if not result and value not in (None, "", []):
            raise ValueError(f"{key} must contain at least one non-empty string.")
        return result

    @staticmethod
    def _fm_parse_size(value, key):
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError(f"{key} must be a byte count or a size such as 10MB.")
        if isinstance(value, (int, float)):
            size = int(value)
        else:
            match = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)\s*(b|kb|kib|mb|mib|gb|gib|tb|tib)?\s*",
                str(value),
                flags=re.IGNORECASE,
            )
            if not match:
                raise ValueError(f"{key} must be a byte count or a size such as 10MB.")
            units = {
                "": 1,
                "b": 1,
                "kb": 1000,
                "kib": 1024,
                "mb": 1000 ** 2,
                "mib": 1024 ** 2,
                "gb": 1000 ** 3,
                "gib": 1024 ** 3,
                "tb": 1000 ** 4,
                "tib": 1024 ** 4,
            }
            size = int(float(match.group(1)) * units[(match.group(2) or "").lower()])
        if size < 0:
            raise ValueError(f"{key} cannot be negative.")
        return size

    @staticmethod
    def _fm_parse_timestamp(value, key, *, upper_bound=False):
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError(f"{key} must be an ISO-8601 date/time or Unix timestamp.")
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        date_only = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", text))
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"{key} must be an ISO-8601 date/time or Unix timestamp."
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        if date_only and upper_bound:
            parsed += timedelta(days=1)
            return parsed.timestamp() - 0.000001
        return parsed.timestamp()

    @staticmethod
    def _fm_glob_parts_match(path_parts, pattern_parts):
        memo = {}

        def match(path_index, pattern_index):
            key = (path_index, pattern_index)
            if key in memo:
                return memo[key]
            if pattern_index >= len(pattern_parts):
                result = path_index >= len(path_parts)
            elif pattern_parts[pattern_index] == "**":
                result = match(path_index, pattern_index + 1) or (
                    path_index < len(path_parts)
                    and match(path_index + 1, pattern_index)
                )
            else:
                result = (
                    path_index < len(path_parts)
                    and fnmatch.fnmatchcase(
                        path_parts[path_index],
                        pattern_parts[pattern_index],
                    )
                    and match(path_index + 1, pattern_index + 1)
                )
            memo[key] = result
            return result

        return match(0, 0)

    @classmethod
    def _fm_glob_match(cls, relative_path, name, pattern, *, case_sensitive=False, match_path=False):
        normalized_pattern = str(pattern or "").strip().replace("\\", "/").strip("/")
        if not normalized_pattern:
            return False
        normalized_relative = str(relative_path or "").replace("\\", "/").strip("/")
        candidate = normalized_relative if match_path or "/" in normalized_pattern else str(name or "")
        if not case_sensitive:
            candidate = candidate.casefold()
            normalized_pattern = normalized_pattern.casefold()
        if "/" not in normalized_pattern:
            return fnmatch.fnmatchcase(candidate, normalized_pattern)
        return cls._fm_glob_parts_match(
            tuple(part for part in candidate.split("/") if part),
            tuple(part for part in normalized_pattern.split("/") if part),
        )

    def _fm_file_query_spec(self, args, *, default_entry_type, default_max_depth):
        entry_type = str(args.get("entry_type") or default_entry_type).strip().lower()
        if entry_type not in {"any", "file", "directory", "symlink", "other"}:
            raise ValueError("entry_type must be any, file, directory, symlink, or other.")
        match_mode = str(args.get("match_mode") or "auto").strip().lower()
        if match_mode not in {"auto", "glob", "substring", "exact"}:
            raise ValueError("match_mode must be auto, glob, substring, or exact.")

        globs = self._fm_string_list(args.get("globs"), "globs")
        if self._fm_arg_present(args, "glob"):
            globs.append(str(args.get("glob")).strip())
        query = str(args.get("query") or "").strip()
        query_mode = match_mode
        if query and query_mode == "auto":
            query_mode = "glob" if any(char in query for char in "*?[") else "substring"
        elif query_mode == "auto":
            query_mode = "glob"

        extensions = set()
        for extension in self._fm_string_list(args.get("extensions"), "extensions"):
            normalized = extension.strip().lower()
            if normalized.startswith("*."):
                normalized = normalized[1:]
            elif not normalized.startswith("."):
                normalized = "." + normalized
            extensions.add(normalized)

        min_size = self._fm_parse_size(args.get("min_size"), "min_size")
        max_size = self._fm_parse_size(args.get("max_size"), "max_size")
        if min_size is not None and max_size is not None and min_size > max_size:
            raise ValueError("min_size cannot exceed max_size.")

        date_field = str(args.get("date_field") or "modified").strip().lower()
        if date_field not in {"created", "modified", "accessed"}:
            raise ValueError("date_field must be created, modified, or accessed.")
        ranges = {}
        for prefix in ("created", "modified", "accessed"):
            ranges[prefix] = (
                self._fm_parse_timestamp(args.get(f"{prefix}_after"), f"{prefix}_after"),
                self._fm_parse_timestamp(
                    args.get(f"{prefix}_before"),
                    f"{prefix}_before",
                    upper_bound=True,
                ),
            )
        generic_from = self._fm_parse_timestamp(args.get("date_from"), "date_from")
        generic_to = self._fm_parse_timestamp(args.get("date_to"), "date_to", upper_bound=True)
        lower, upper = ranges[date_field]
        ranges[date_field] = (
            max(value for value in (lower, generic_from) if value is not None)
            if lower is not None or generic_from is not None else None,
            min(value for value in (upper, generic_to) if value is not None)
            if upper is not None or generic_to is not None else None,
        )
        for prefix, (lower, upper) in ranges.items():
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{prefix} date lower bound cannot exceed its upper bound.")

        max_depth = max(0, min(int(args.get("max_depth") if args.get("max_depth") is not None else default_max_depth), 64))
        if args.get("recursive") is False:
            max_depth = 0
        min_depth = max(1, min(int(args.get("min_depth") or 1), 65))
        return {
            "entry_type": entry_type,
            "query": query,
            "query_mode": query_mode,
            "globs": globs,
            "exclude_globs": self._fm_string_list(args.get("exclude_globs"), "exclude_globs"),
            "extensions": extensions,
            "min_size": min_size,
            "max_size": max_size,
            "ranges": ranges,
            "case_sensitive": bool(args.get("case_sensitive", False)),
            "match_path": bool(args.get("match_path", False)),
            "include_hidden": bool(args.get("include_hidden", False)),
            "follow_symlinks": bool(args.get("follow_symlinks", False)),
            "max_depth": max_depth,
            "min_depth": min_depth,
        }

    def _fm_entry_excluded(self, info, spec):
        relative = info.get("relative_path", "")
        name = info.get("name", "")
        return any(
            self._fm_glob_match(
                relative,
                name,
                pattern,
                case_sensitive=spec["case_sensitive"],
                match_path=spec["match_path"],
            )
            for pattern in spec["exclude_globs"]
        )

    def _fm_entry_identity_matches(self, info, spec):
        """Apply filters that need no file metadata beyond name, path, and type."""
        if info.get("depth", 0) < spec["min_depth"]:
            return False
        if info.get("depth", 0) > spec["max_depth"] + 1:
            return False
        if spec["entry_type"] != "any" and info.get("type") != spec["entry_type"]:
            return False
        if spec["extensions"] and info.get("extension", "").lower() not in spec["extensions"]:
            return False
        if self._fm_entry_excluded(info, spec):
            return False

        relative = info.get("relative_path", "")
        name = info.get("name", "")
        query = spec["query"]
        if query:
            if spec["query_mode"] == "glob":
                matched = self._fm_glob_match(
                    relative,
                    name,
                    query,
                    case_sensitive=spec["case_sensitive"],
                    match_path=spec["match_path"],
                )
            else:
                candidate = relative if spec["match_path"] else name
                if not spec["case_sensitive"]:
                    candidate = candidate.casefold()
                    query = query.casefold()
                matched = candidate == query if spec["query_mode"] == "exact" else query in candidate
            if not matched:
                return False
        if spec["globs"] and not any(
            self._fm_glob_match(
                relative,
                name,
                pattern,
                case_sensitive=spec["case_sensitive"],
                match_path=spec["match_path"],
            )
            for pattern in spec["globs"]
        ):
            return False
        return True

    def _fm_entry_matches(self, info, spec):
        if not self._fm_entry_identity_matches(info, spec):
            return False

        if spec["min_size"] is not None or spec["max_size"] is not None:
            if info.get("type") != "file":
                return False
            size = int(info.get("size") or 0)
            if spec["min_size"] is not None and size < spec["min_size"]:
                return False
            if spec["max_size"] is not None and size > spec["max_size"]:
                return False

        timestamp_fields = {
            "created": "created_at",
            "modified": "modified_at",
            "accessed": "accessed_at",
        }
        for prefix, (lower, upper) in spec["ranges"].items():
            if lower is None and upper is None:
                continue
            raw_timestamp = info.get(timestamp_fields[prefix])
            try:
                timestamp = datetime.fromisoformat(str(raw_timestamp)).timestamp()
            except Exception:
                return False
            if lower is not None and timestamp < lower:
                return False
            if upper is not None and timestamp > upper:
                return False
        return True

    def _fm_walk_search_entries(self, path, spec, state):
        """
        Enumerate an exact filesystem search while delaying stat calls.

        Filename, extension, type, path glob, and exclusion filters are applied
        against cheap DirEntry data first. Directories still receive a metadata
        read when traversal decisions require hidden/reparse attributes, while
        non-candidate files never receive a full stat call.
        """
        follow_links = spec["follow_symlinks"]
        visited_directories = (
            {os.path.normcase(os.path.realpath(path))}
            if follow_links else set()
        )
        pending = [(path, "", 0)]
        pending_index = 0
        while pending_index < len(pending):
            current, relative_parent, parent_depth = pending[pending_index]
            pending_index += 1
            self._raise_if_cancelled()
            try:
                with os.scandir(current) as iterator:
                    children = sorted(iterator, key=lambda entry: entry.name.casefold())
            except OSError as exc:
                if current == path:
                    raise
                state["errors"] += 1
                if len(state["error_samples"]) < 5:
                    state["error_samples"].append(
                        {"path": current, "error": f"{type(exc).__name__}: {exc}"}
                    )
                continue

            for entry in children:
                self._raise_if_cancelled()
                if state["scanned"] >= state["scan_limit"]:
                    state["scan_truncated"] = True
                    return
                state["scanned"] += 1
                relative_path = (
                    os.path.join(relative_parent, entry.name)
                    if relative_parent else entry.name
                )
                depth = parent_depth + 1
                try:
                    is_symlink = bool(entry.is_symlink())
                    is_directory = bool(entry.is_dir(follow_symlinks=False))
                    is_file = bool(
                        not is_directory
                        and not is_symlink
                        and entry.is_file(follow_symlinks=False)
                    )
                except OSError as exc:
                    state["errors"] += 1
                    if len(state["error_samples"]) < 5:
                        state["error_samples"].append(
                            {"path": entry.path, "error": f"{type(exc).__name__}: {exc}"}
                        )
                    continue

                lightweight_type = (
                    "directory" if is_directory
                    else "symlink" if is_symlink
                    else "file" if is_file
                    else "other"
                )
                lightweight = {
                    "path": entry.path,
                    "name": entry.name,
                    "relative_path": relative_path,
                    "extension": (
                        os.path.splitext(entry.name)[1].lower()
                        if lightweight_type == "file" else ""
                    ),
                    "depth": depth,
                    "type": lightweight_type,
                }
                excluded = self._fm_entry_excluded(lightweight, spec)
                if excluded:
                    continue

                may_traverse_link = bool(is_symlink and follow_links)
                identity_match = self._fm_entry_identity_matches(lightweight, spec)
                needs_metadata = bool(is_directory or may_traverse_link or identity_match)
                if not needs_metadata:
                    continue

                try:
                    info = self._fm_stat_dir_entry(
                        entry,
                        minimal=bool(
                            (is_directory or may_traverse_link)
                            and not identity_match
                        ),
                    )
                    state["metadata_reads"] += 1
                except OSError as exc:
                    state["errors"] += 1
                    if len(state["error_samples"]) < 5:
                        state["error_samples"].append(
                            {"path": entry.path, "error": f"{type(exc).__name__}: {exc}"}
                        )
                    continue
                info.update({
                    "name": entry.name,
                    "relative_path": relative_path,
                    "extension": (
                        os.path.splitext(entry.name)[1].lower()
                        if info.get("type") == "file" else ""
                    ),
                    "depth": depth,
                })

                if spec["include_hidden"] or not info.get("hidden"):
                    if self._fm_entry_matches(info, spec):
                        yield info

                traversable_directory = info.get("type") == "directory"
                if (
                    follow_links
                    and info.get("is_reparse_point")
                    and not traversable_directory
                ):
                    try:
                        traversable_directory = entry.is_dir(follow_symlinks=True)
                    except OSError:
                        traversable_directory = False
                if not traversable_directory or parent_depth >= spec["max_depth"]:
                    continue
                if info.get("hidden") and not spec["include_hidden"]:
                    continue
                if info.get("is_reparse_point") and not follow_links:
                    continue
                if info.get("is_reparse_point"):
                    self._fm_validate_access_path(
                        entry.path,
                        "read",
                        follow_symlinks=True,
                        include_leaf=True,
                    )
                    real_child = os.path.normcase(os.path.realpath(entry.path))
                    if real_child in visited_directories:
                        state["errors"] += 1
                        if len(state["error_samples"]) < 5:
                            state["error_samples"].append(
                                {"path": entry.path, "error": "Directory link cycle skipped."}
                            )
                        continue
                    visited_directories.add(real_child)
                pending.append((entry.path, relative_path, depth))

    def _fm_walk_query_entries(self, path, spec, state):
        visited_directories = {os.path.normcase(os.path.realpath(path))}
        pending = [(path, 0)]
        pending_index = 0
        while pending_index < len(pending):
            current, parent_depth = pending[pending_index]
            pending_index += 1
            self._raise_if_cancelled()
            try:
                with os.scandir(current) as iterator:
                    children = sorted(iterator, key=lambda entry: entry.name.casefold())
            except OSError as exc:
                if current == path:
                    raise
                state["errors"] += 1
                if len(state["error_samples"]) < 5:
                    state["error_samples"].append(
                        {"path": current, "error": f"{type(exc).__name__}: {exc}"}
                    )
                continue
            for entry in children:
                self._raise_if_cancelled()
                if state["scanned"] >= state["scan_limit"]:
                    state["scan_truncated"] = True
                    return
                try:
                    info = self._fm_stat_dir_entry(entry)
                    state["metadata_reads"] += 1
                except OSError as exc:
                    state["errors"] += 1
                    if len(state["error_samples"]) < 5:
                        state["error_samples"].append(
                            {"path": entry.path, "error": f"{type(exc).__name__}: {exc}"}
                        )
                    continue
                state["scanned"] += 1
                info["name"] = entry.name
                info["relative_path"] = os.path.relpath(entry.path, path)
                info["extension"] = os.path.splitext(entry.name)[1].lower() if info.get("type") == "file" else ""
                info["depth"] = parent_depth + 1
                if not spec["include_hidden"] and info.get("hidden"):
                    continue
                excluded = self._fm_entry_excluded(info, spec)
                if not excluded and self._fm_entry_matches(info, spec):
                    yield info
                traversable_directory = info.get("type") == "directory"
                if (
                    spec["follow_symlinks"]
                    and info.get("is_reparse_point")
                    and not traversable_directory
                ):
                    try:
                        traversable_directory = entry.is_dir(follow_symlinks=True)
                    except OSError:
                        traversable_directory = False
                if not traversable_directory or parent_depth >= spec["max_depth"]:
                    continue
                if excluded:
                    continue
                if info.get("is_reparse_point") and not spec["follow_symlinks"]:
                    continue
                if info.get("is_reparse_point"):
                    self._fm_validate_access_path(
                        entry.path,
                        "read",
                        follow_symlinks=True,
                        include_leaf=True,
                    )
                real_child = os.path.normcase(os.path.realpath(entry.path))
                if real_child in visited_directories:
                    state["errors"] += 1
                    if len(state["error_samples"]) < 5:
                        state["error_samples"].append(
                            {"path": entry.path, "error": "Directory link cycle skipped."}
                        )
                    continue
                visited_directories.add(real_child)
                pending.append((entry.path, parent_depth + 1))

    @staticmethod
    def _fm_windows_sql_literal(value):
        return "'" + str(value or "").replace("'", "''") + "'"

    @staticmethod
    def _fm_windows_scope_url(path):
        normalized = os.path.abspath(path).replace("\\", "/")
        if normalized.startswith("//"):
            return "file:" + normalized
        return "file:" + normalized

    @staticmethod
    def _fm_windows_date_literal(timestamp):
        local_value = datetime.fromtimestamp(float(timestamp)).astimezone()
        # Windows Search SQL accepts its documented date form and a
        # space-separated local time; an ISO ``T`` separator silently matches
        # no rows on current Windows builds.
        return local_value.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _fm_glob_fixed_extension(pattern):
        normalized = str(pattern or "").strip().replace("\\", "/")
        leaf = normalized.rsplit("/", 1)[-1]
        _, extension = os.path.splitext(leaf)
        if not extension or any(char in extension for char in "*?["):
            return None
        return extension.lower()

    def _fm_windows_candidate_extensions(self, spec):
        constraints = []
        if spec["extensions"]:
            constraints.append(set(spec["extensions"]))
        if spec["query"] and spec["query_mode"] == "glob":
            extension = self._fm_glob_fixed_extension(spec["query"])
            if extension:
                constraints.append({extension})
        if spec["globs"]:
            extensions = {
                extension
                for extension in (
                    self._fm_glob_fixed_extension(pattern)
                    for pattern in spec["globs"]
                )
                if extension
            }
            if len(extensions) == len(spec["globs"]):
                constraints.append(extensions)
        if not constraints:
            return None
        candidates = set(constraints[0])
        for constraint in constraints[1:]:
            candidates.intersection_update(constraint)
        return candidates

    def _fm_windows_property_filter_clause(self, item):
        if not isinstance(item, dict):
            raise ValueError("windows_property_filters items must be objects.")
        alias = str(item.get("property") or "").strip().lower()
        if alias not in _WINDOWS_SEARCH_COLUMNS:
            raise ValueError(
                "Unsupported Windows Search property. Use one of: "
                + ", ".join(sorted(_WINDOWS_SEARCH_COLUMNS))
            )
        column, value_type = _WINDOWS_SEARCH_COLUMNS[alias]
        operator = str(item.get("operator") or "eq").strip().lower()
        value = item.get("value")
        if value in (None, ""):
            raise ValueError("Each Windows Search property filter requires a value.")

        if value_type == "size":
            if operator not in _WINDOWS_SEARCH_ORDERED_OPERATORS:
                raise ValueError(f"{alias} supports eq/ne/gt/gte/lt/lte.")
            literal = str(self._fm_parse_size(value, f"windows_property_filters.{alias}"))
        elif value_type == "date":
            if operator not in _WINDOWS_SEARCH_ORDERED_OPERATORS:
                raise ValueError(f"{alias} supports eq/ne/gt/gte/lt/lte.")
            timestamp = self._fm_parse_timestamp(
                value,
                f"windows_property_filters.{alias}",
            )
            literal = self._fm_windows_sql_literal(
                self._fm_windows_date_literal(timestamp)
            )
        else:
            if operator not in _WINDOWS_SEARCH_TEXT_OPERATORS:
                raise ValueError(f"{alias} supports eq/ne/contains/freetext/prefix.")
            literal = self._fm_windows_sql_literal(value)

        comparisons = {
            "eq": "=",
            "ne": "<>",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
        }
        if operator in comparisons:
            return f"{column} {comparisons[operator]} {literal}"
        if operator == "freetext":
            return f"FREETEXT({column}, {literal})"
        if operator == "prefix":
            prefix = str(value).replace('"', " ").strip()
            return (
                f"CONTAINS({column}, "
                f"{self._fm_windows_sql_literal(chr(34) + prefix + '*' + chr(34))})"
            )
        return f"CONTAINS({column}, {literal})"

    def _fm_windows_content_clause(self, args):
        query = str(args.get("content_query") or "").strip()
        if not query:
            return None
        mode = str(args.get("content_mode") or "freetext").strip().lower()
        if mode not in {"freetext", "contains", "phrase", "prefix"}:
            raise ValueError("content_mode must be freetext, contains, phrase, or prefix.")
        if mode == "freetext":
            return f"FREETEXT(*, {self._fm_windows_sql_literal(query)})"
        if mode == "contains":
            return f"CONTAINS(*, {self._fm_windows_sql_literal(query)})"
        cleaned = query.replace('"', " ").strip()
        if mode == "prefix":
            cleaned += "*"
        return (
            "CONTAINS(*, "
            + self._fm_windows_sql_literal(f'"{cleaned}"')
            + ")"
        )

    def _fm_build_windows_search_sql(self, path, args, spec, scan_limit):
        scope_column = "DIRECTORY" if spec["max_depth"] == 0 else "SCOPE"
        clauses = [
            f"{scope_column}={self._fm_windows_sql_literal(self._fm_windows_scope_url(path))}"
        ]
        candidate_extensions = self._fm_windows_candidate_extensions(spec)
        if candidate_extensions is not None:
            if not candidate_extensions:
                clauses.append("System.FileExtension='.__smarti_no_match__'")
            else:
                clauses.append(
                    "("
                    + " OR ".join(
                        "System.FileExtension="
                        + self._fm_windows_sql_literal(extension)
                        for extension in sorted(candidate_extensions)
                    )
                    + ")"
                )
        if (
            spec["query"]
            and spec["query_mode"] == "exact"
            and not spec["match_path"]
        ):
            clauses.append(
                "System.FileName="
                + self._fm_windows_sql_literal(spec["query"])
            )
        if spec["min_size"] is not None:
            clauses.append(f"System.Size >= {spec['min_size']}")
        if spec["max_size"] is not None:
            clauses.append(f"System.Size <= {spec['max_size']}")
        date_columns = {
            "created": "System.DateCreated",
            "modified": "System.DateModified",
            "accessed": "System.DateAccessed",
        }
        for prefix, (lower, upper) in spec["ranges"].items():
            column = date_columns[prefix]
            if lower is not None:
                clauses.append(
                    f"{column} >= "
                    + self._fm_windows_sql_literal(
                        self._fm_windows_date_literal(lower)
                    )
                )
            if upper is not None:
                clauses.append(
                    f"{column} <= "
                    + self._fm_windows_sql_literal(
                        self._fm_windows_date_literal(upper)
                    )
                )

        windows_kinds = self._fm_string_list(args.get("windows_kinds"), "windows_kinds")
        if windows_kinds:
            clauses.append(
                "("
                + " OR ".join(
                    "System.Kind=" + self._fm_windows_sql_literal(kind)
                    for kind in windows_kinds
                )
                + ")"
            )
        mime_types = self._fm_string_list(args.get("mime_types"), "mime_types")
        if mime_types:
            clauses.append(
                "("
                + " OR ".join(
                    "System.MIMEType=" + self._fm_windows_sql_literal(value)
                    for value in mime_types
                )
                + ")"
            )
        content_clause = self._fm_windows_content_clause(args)
        if content_clause:
            clauses.append(content_clause)
        property_filters = args.get("windows_property_filters") or []
        if not isinstance(property_filters, list):
            raise ValueError("windows_property_filters must be an array.")
        clauses.extend(
            self._fm_windows_property_filter_clause(item)
            for item in property_filters
        )

        columns = (
            "System.ItemUrl, System.FileName, System.FileExtension, System.Size, "
            "System.DateCreated, System.DateModified, System.DateAccessed, "
            "System.FileAttributes, System.ItemType, System.Kind, System.MIMEType, "
            "System.Title, System.Author, System.Keywords, System.Search.Rank"
        )
        return (
            f"SELECT TOP {min(scan_limit + 1, _MAX_FILE_QUERY_SCAN + 1)} "
            f"{columns} FROM SystemIndex WHERE "
            + " AND ".join(clauses)
        )

    @staticmethod
    def _fm_windows_search_service_status():
        if os.name != "nt":
            return "unsupported"
        try:
            import win32service
            import win32serviceutil

            status_code = int(win32serviceutil.QueryServiceStatus("WSearch")[1])
            names = {
                int(win32service.SERVICE_STOPPED): "stopped",
                int(win32service.SERVICE_START_PENDING): "start_pending",
                int(win32service.SERVICE_STOP_PENDING): "stop_pending",
                int(win32service.SERVICE_RUNNING): "running",
                int(win32service.SERVICE_CONTINUE_PENDING): "continue_pending",
                int(win32service.SERVICE_PAUSE_PENDING): "pause_pending",
                int(win32service.SERVICE_PAUSED): "paused",
            }
            return names.get(status_code, f"status_{status_code}")
        except Exception:
            return "unknown"

    def _fm_windows_search_rows(self, sql):
        if os.name != "nt":
            raise _WindowsSearchUnavailable(
                "Microsoft Windows Search is available only on Windows."
            )
        try:
            import pythoncom
            import win32com.client
        except Exception as exc:
            raise _WindowsSearchUnavailable(
                "pywin32 is required to query the Microsoft Windows Search service."
            ) from exc

        connection = None
        recordset = None
        initialized = False
        try:
            pythoncom.CoInitialize()
            initialized = True
            connection = win32com.client.Dispatch("ADODB.Connection")
            connection.Open(
                "Provider=Search.CollatorDSO;"
                "Extended Properties='Application=Windows';"
            )
            executed = connection.Execute(sql)
            recordset = executed[0] if isinstance(executed, tuple) else executed
            while not recordset.EOF:
                self._raise_if_cancelled()
                row = {}
                for index in range(recordset.Fields.Count):
                    field = recordset.Fields.Item(index)
                    row[str(field.Name).lower()] = field.Value
                yield row
                recordset.MoveNext()
        except SmartiCancelled:
            raise
        except Exception as exc:
            raise _WindowsSearchUnavailable(
                f"Microsoft Windows Search query failed: {exc}"
            ) from exc
        finally:
            if recordset is not None:
                try:
                    recordset.Close()
                except Exception:
                    pass
            if connection is not None:
                try:
                    connection.Close()
                except Exception:
                    pass
            if initialized:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _fm_windows_scope_is_indexed(self, path):
        item_url = self._fm_windows_scope_url(path)
        sql = (
            "SELECT TOP 1 System.ItemUrl FROM SystemIndex WHERE System.ItemUrl="
            + self._fm_windows_sql_literal(item_url)
        )
        rows = self._fm_windows_search_rows(sql)
        try:
            return next(rows, None) is not None
        finally:
            close = getattr(rows, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _fm_windows_item_url_to_path(value):
        parsed = urllib.parse.urlparse(str(value or ""))
        if parsed.scheme.lower() != "file":
            return ""
        decoded_path = urllib.parse.unquote(parsed.path or "")
        if parsed.netloc:
            return os.path.normpath(
                "\\\\" + parsed.netloc + "\\" + decoded_path.lstrip("/").replace("/", "\\")
            )
        if re.match(r"^/[A-Za-z]:/", decoded_path):
            decoded_path = decoded_path[1:]
        return os.path.normpath(decoded_path.replace("/", os.sep))

    @staticmethod
    def _fm_windows_index_iso(value):
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value))
            except Exception:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed.astimezone().isoformat()

    @staticmethod
    def _fm_windows_list_value(value):
        if value in (None, ""):
            return None
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if item not in (None, "")]
        return [str(value)]

    def _fm_windows_row_info(self, row, item_path):
        attributes = int(float(row.get("system.fileattributes") or 0))
        is_reparse = bool(attributes & _WINDOWS_REPARSE_ATTRIBUTE)
        if attributes & _WINDOWS_DIRECTORY_ATTRIBUTE:
            kind = "directory"
        elif is_reparse:
            kind = "symlink"
        else:
            kind = "file"
        info = {
            "path": item_path,
            "exists": True,
            "type": kind,
            "size": int(row.get("system.size") or 0),
            "created_at": self._fm_windows_index_iso(row.get("system.datecreated")),
            "modified_at": self._fm_windows_index_iso(row.get("system.datemodified")),
            "accessed_at": self._fm_windows_index_iso(row.get("system.dateaccessed")),
            "hidden": bool(attributes & _WINDOWS_HIDDEN_ATTRIBUTE),
            "read_only": bool(attributes & _WINDOWS_READONLY_ATTRIBUTE),
            "is_symlink": False,
            "is_reparse_point": is_reparse,
        }
        extras = {
            "windows_kind": self._fm_windows_list_value(row.get("system.kind")),
            "mime_type": row.get("system.mimetype"),
            "title": row.get("system.title"),
            "authors": self._fm_windows_list_value(row.get("system.author")),
            "tags": self._fm_windows_list_value(row.get("system.keywords")),
            "search_rank": (
                int(row.get("system.search.rank"))
                if row.get("system.search.rank") is not None else None
            ),
        }
        info.update({key: value for key, value in extras.items() if value is not None})
        return info

    def _fm_walk_windows_search_entries(self, path, args, spec, state, metadata):
        service_status = self._fm_windows_search_service_status()
        metadata["windows_search"]["service_status"] = service_status
        if service_status not in {"running", "unknown"}:
            raise _WindowsSearchUnavailable(
                f"Microsoft Windows Search service (WSearch) is {service_status}."
            )
        if str(args.get("search_backend") or "auto").strip().lower() == "auto":
            indexed_scope = self._fm_windows_scope_is_indexed(path)
            metadata["windows_search"]["root_present_in_index"] = indexed_scope
            if not indexed_scope:
                raise _WindowsSearchUnavailable(
                    "The requested root is not present in the Microsoft Windows Search index."
                )
        sql = self._fm_build_windows_search_sql(
            path,
            args,
            spec,
            state["scan_limit"],
        )
        if bool(args.get("include_search_diagnostics", False)):
            metadata["windows_search"]["sql"] = sql
        verify_results = bool(args.get("verify_index_results", True))
        started = time.perf_counter()
        indexed_candidates = 0
        verified_candidates = 0
        stale_skipped = 0
        normalized_root = os.path.normcase(os.path.abspath(path))
        try:
            for row in self._fm_windows_search_rows(sql):
                if indexed_candidates >= state["scan_limit"]:
                    state["scan_truncated"] = True
                    break
                indexed_candidates += 1
                item_path = self._fm_windows_item_url_to_path(
                    row.get("system.itemurl")
                )
                if not item_path:
                    stale_skipped += 1
                    continue
                item_path = os.path.abspath(item_path)
                try:
                    inside_root = (
                        os.path.commonpath([normalized_root, os.path.normcase(item_path)])
                        == normalized_root
                    )
                except ValueError:
                    inside_root = False
                if not inside_root:
                    stale_skipped += 1
                    continue
                try:
                    self._fm_guard_reparse_ancestors(
                        item_path,
                        include_leaf=True,
                        follow_symlinks=spec["follow_symlinks"],
                    )
                except PermissionError:
                    stale_skipped += 1
                    continue

                index_info = self._fm_windows_row_info(row, item_path)
                if verify_results:
                    if not os.path.lexists(item_path):
                        stale_skipped += 1
                        continue
                    try:
                        info = self._fm_stat_path(item_path)
                        state["metadata_reads"] += 1
                    except OSError:
                        stale_skipped += 1
                        continue
                    verified_candidates += 1
                    for key in (
                        "windows_kind", "mime_type", "title",
                        "authors", "tags", "search_rank",
                    ):
                        if key in index_info:
                            info[key] = index_info[key]
                else:
                    info = index_info

                relative_path = os.path.relpath(item_path, path)
                normalized_relative = relative_path.replace("\\", "/")
                depth = 0 if normalized_relative == "." else len(
                    [part for part in normalized_relative.split("/") if part]
                )
                info.update({
                    "name": os.path.basename(item_path),
                    "relative_path": relative_path,
                    "extension": (
                        os.path.splitext(item_path)[1].lower()
                        if info.get("type") == "file" else ""
                    ),
                    "depth": depth,
                })
                state["scanned"] += 1
                if not spec["include_hidden"] and info.get("hidden"):
                    continue
                if self._fm_entry_matches(info, spec):
                    yield info
        finally:
            metadata["windows_search"].update({
                "query_ms": round((time.perf_counter() - started) * 1000, 1),
                "indexed_candidates": indexed_candidates,
                "verified_candidates": verified_candidates if verify_results else None,
                "stale_or_invalid_skipped": stale_skipped,
            })

    def _fm_query_output_options(self, args, *, search_mode):
        detail_explicit = self._fm_arg_present(args, "detail")
        detail = str(args.get("detail") or "minimal").strip().lower()
        if detail not in _FILE_QUERY_DETAIL_FIELDS:
            raise ValueError("detail must be minimal, standard, or full.")
        fields = self._fm_string_list(args.get("fields"), "fields")
        invalid_fields = sorted(set(fields) - _FILE_QUERY_FIELDS)
        if invalid_fields:
            raise ValueError(f"Unsupported fields: {', '.join(invalid_fields)}")
        raw_format = str(args.get("output_format") or "").strip().lower()
        if not raw_format:
            raw_format = "records" if fields or (detail_explicit and detail != "minimal") else "paths"
        if raw_format not in {"paths", "records", "text"}:
            raise ValueError("output_format must be paths, records, or text.")
        if not fields:
            fields = list(_FILE_QUERY_DETAIL_FIELDS[detail])
            if search_mode:
                fields = ["path" if field == "relative_path" else field for field in fields]
        return raw_format, fields, detail

    @staticmethod
    def _fm_project_query_entry(info, fields):
        return {field: info.get(field) for field in fields if field in info}

    def _fm_render_query_entries(self, entries, args, *, search_mode):
        output_format, fields, detail = self._fm_query_output_options(args, search_mode=search_mode)
        if output_format == "records":
            rendered = [self._fm_project_query_entry(info, fields) for info in entries]
            return {"entries": rendered, "output_format": output_format, "detail": detail, "fields": fields}
        if output_format == "text":
            if search_mode:
                text = "\n".join(
                    self._fm_display_path(str(info.get("path") or ""))
                    for info in entries
                )
            else:
                lines = []
                for info in entries:
                    suffix = "/" if info.get("type") == "directory" else ""
                    lines.append(f"{'  ' * max(0, int(info.get('depth') or 1) - 1)}{info.get('name', '')}{suffix}")
                text = "\n".join(lines)
            return {"text": text, "output_format": output_format, "detail": detail}
        paths = []
        for info in entries:
            value = info.get("path") if search_mode else info.get("relative_path")
            value = str(value or "")
            if search_mode:
                value = self._fm_display_path(value)
            else:
                value = value.replace("\\", "/")
                if info.get("type") == "directory":
                    value += "/"
            paths.append(value)
        return {"entries": paths, "output_format": output_format, "detail": detail}

    def _fm_collect_query(
        self,
        path,
        args,
        *,
        search_mode,
        entry_provider=None,
        result_metadata=None,
    ):
        if not os.path.isdir(path):
            raise NotADirectoryError(path)
        default_entry_type = "file" if search_mode else "any"
        default_max_depth = 64 if search_mode else 4
        spec = self._fm_file_query_spec(
            args,
            default_entry_type=default_entry_type,
            default_max_depth=default_max_depth,
        )
        limit_default = 100 if search_mode else 200
        limit = max(1, min(int(args.get("limit") or limit_default), _MAX_FILE_QUERY_RESULTS))
        offset = max(0, min(int(args.get("offset") or 0), _MAX_FILE_QUERY_SCAN - 1))
        scan_limit = min(
            _MAX_FILE_QUERY_SCAN,
            max(
                offset + limit,
                min(int(args.get("scan_limit") or 50000), _MAX_FILE_QUERY_SCAN),
            ),
        )
        state = {
            "scanned": 0,
            "scan_limit": scan_limit,
            "scan_truncated": False,
            "errors": 0,
            "error_samples": [],
            "metadata_reads": 0,
        }
        if entry_provider is not None:
            source = entry_provider(path, args, spec, state)
        elif search_mode:
            source = self._fm_walk_search_entries(path, spec, state)
        else:
            source = self._fm_walk_query_entries(path, spec, state)
        matches = list(source)

        sort_by = str(
            args.get("sort_by")
            or ("search_rank" if search_mode and args.get("content_query") else "path")
        ).strip().lower()
        if sort_by not in {
            "path", "name", "type", "size", "created_at",
            "modified_at", "accessed_at", "search_rank",
        }:
            raise ValueError(
                "sort_by must be path, name, type, size, created_at, modified_at, "
                "accessed_at, or search_rank."
            )
        sort_order = str(
            args.get("sort_order")
            or ("desc" if sort_by == "search_rank" else "asc")
        ).strip().lower()
        if sort_order not in {"asc", "desc"}:
            raise ValueError("sort_order must be asc or desc.")

        def sort_key(info):
            value = info.get(sort_by)
            if sort_by == "path":
                value = info.get("relative_path")
            if isinstance(value, str):
                value = value if spec["case_sensitive"] else value.casefold()
            return (value is None, value)

        matches.sort(key=sort_key, reverse=sort_order == "desc")
        if bool(args.get("directories_first", False)):
            matches.sort(key=lambda info: info.get("type") != "directory")

        page = matches[offset:offset + limit]
        output_char_limit = max(
            2000,
            min(
                int(args.get("max_output_chars") or (60000 if search_mode else 40000)),
                _MAX_FILE_QUERY_OUTPUT_CHARS,
            ),
        )

        def build_result(selected, *, output_limited=False):
            page_truncated = offset + len(selected) < len(matches)
            truncated = bool(state["scan_truncated"] or page_truncated)
            rendered = self._fm_render_query_entries(selected, args, search_mode=search_mode)
            result = {
                "path": path,
                **rendered,
                "returned": len(selected),
                "matched": None if state["scan_truncated"] else len(matches),
                "matched_scanned": len(matches),
                "scanned": state["scanned"],
                "truncated": truncated,
                "next_offset": offset + len(selected) if page_truncated and selected else None,
                "limit": limit,
                "offset": offset,
                "max_depth": spec["max_depth"],
                "metadata_reads": state["metadata_reads"],
            }
            if result_metadata:
                result.update(result_metadata)
            if search_mode and result.get("search_backend_used") == "filesystem":
                result["completeness"] = (
                    "filesystem_partial"
                    if state["scan_truncated"] else "filesystem_exact"
                )
            if state["scan_truncated"]:
                result["scan_truncated"] = True
                result["scan_limit"] = scan_limit
            if state["errors"]:
                result["errors"] = state["errors"]
                result["error_samples"] = state["error_samples"]
            if output_limited:
                result["output_limited"] = True
                result["max_output_chars"] = output_char_limit
            if truncated:
                hints = [
                    "Refine glob/extensions/type/date/size/depth filters or request fewer fields."
                ]
                if state["scan_truncated"]:
                    hints.append("Raise scan_limit when matches beyond the scanned entries are required.")
                if page_truncated:
                    hints.append("Continue with offset=next_offset for the next result page.")
                if output_limited:
                    hints.append("Raise max_output_chars only when the larger result is necessary.")
                result["hint"] = " ".join(hints)
            return result

        def serialized_size(candidate):
            wrapped = {
                "ok": True,
                "action": "search_files" if search_mode else "tree",
                **candidate,
            }
            return len(json.dumps(
                self._fm_public_result(wrapped),
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ))

        result = build_result(page)
        serialized_length = serialized_size(result)
        if serialized_length <= output_char_limit or len(page) <= 1:
            return result

        low, high, best = 1, len(page) - 1, 1
        while low <= high:
            midpoint = (low + high) // 2
            candidate = build_result(page[:midpoint], output_limited=True)
            candidate_length = serialized_size(candidate)
            if candidate_length <= output_char_limit:
                best = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1
        return build_result(page[:best], output_limited=True)

    @staticmethod
    def _fm_has_windows_only_filters(args):
        return bool(
            str(args.get("content_query") or "").strip()
            or args.get("windows_kinds")
            or args.get("mime_types")
            or args.get("windows_property_filters")
        )

    def _fm_search_files(self, path, args):
        requested = str(args.get("search_backend") or "auto").strip().lower()
        if requested not in {"auto", "windows_search", "filesystem"}:
            raise ValueError(
                "search_backend must be auto, windows_search, or filesystem."
            )
        windows_only_filters = self._fm_has_windows_only_filters(args)
        if requested == "filesystem" and windows_only_filters:
            raise ValueError(
                "content_query/windows_kinds/mime_types/windows_property_filters "
                "require search_backend=windows_search or auto."
            )
        fallback_default = requested == "auto"
        fallback = bool(args.get("fallback_to_filesystem", fallback_default))
        use_windows = requested in {"auto", "windows_search"}
        if use_windows:
            metadata = {
                "search_backend_requested": requested,
                "search_backend_used": "windows_search",
                "completeness": (
                    "windows_index_verified_candidates"
                    if bool(args.get("verify_index_results", True))
                    else "windows_index"
                ),
                "catalog_scope": "indexed_items_only",
                "windows_search": {
                    "service": "Microsoft Windows Search",
                    "service_name": "WSearch",
                    "result_verification": (
                        "filesystem_metadata"
                        if bool(args.get("verify_index_results", True))
                        else "none"
                    ),
                },
            }

            def windows_provider(root, call_args, spec, state):
                return self._fm_walk_windows_search_entries(
                    root,
                    call_args,
                    spec,
                    state,
                    metadata,
                )

            try:
                return self._fm_collect_query(
                    path,
                    args,
                    search_mode=True,
                    entry_provider=windows_provider,
                    result_metadata=metadata,
                )
            except _WindowsSearchUnavailable as exc:
                if not fallback or windows_only_filters:
                    raise
                fallback_reason = str(exc)
        else:
            fallback_reason = None

        filesystem_metadata = {
            "search_backend_requested": requested,
            "search_backend_used": "filesystem",
            "search_strategy": "candidate_filters_before_metadata",
        }
        if fallback_reason:
            filesystem_metadata.update({
                "fallback_from": "windows_search",
                "fallback_reason": fallback_reason,
            })
        return self._fm_collect_query(
            path,
            args,
            search_mode=True,
            result_metadata=filesystem_metadata,
        )

    def _fm_tree(self, path, args):
        return self._fm_collect_query(path, args, search_mode=False)

    def _fm_hash_algorithm(self, args):
        algorithm = str(args.get("algorithm") or "sha256").strip().lower()
        if algorithm not in FILE_MANAGER_HASH_ALGORITHMS:
            raise ValueError(f"algorithm must be one of {sorted(FILE_MANAGER_HASH_ALGORITHMS)}")
        return algorithm

    def _fm_progress(self, label, completed, total=None):
        now = time.monotonic()
        last = float(getattr(self, "_file_manager_last_progress", 0.0) or 0.0)
        if now - last < 0.75 and (not total or completed < total):
            return
        self._file_manager_last_progress = now
        if self.status_callback:
            suffix = f" ({completed}/{total})" if total else f" ({completed})"
            self.status_callback(f"{label}{suffix}")

    def _fm_hash_file(self, path, algorithm):
        digest = hashlib.new(algorithm)
        total = 0
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            while True:
                self._raise_if_cancelled()
                chunk = handle.read(_FILE_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
                self._fm_progress("מחשב גיבוב קבצים", total, size)
        return digest.hexdigest(), total

    def _fm_hash_path(self, path, algorithm="sha256", follow_symlinks=False, *, include_entries=False):
        if not os.path.lexists(path):
            raise FileNotFoundError(path)
        if os.path.isfile(path):
            digest, size = self._fm_hash_file(path, algorithm)
            return {
                "path": path,
                "type": "file",
                "algorithm": algorithm,
                "hash": digest,
                "bytes": size,
                "items": 1,
            }
        if not os.path.isdir(path):
            raise ValueError(f"Hash supports files and directories only: {path}")
        manifest = []
        total_bytes = 0
        visited_directories = {os.path.normcase(os.path.realpath(path))}
        for root, dirs, files in os.walk(path, followlinks=follow_symlinks):
            self._raise_if_cancelled()
            if not follow_symlinks:
                for name in dirs:
                    child = os.path.join(root, name)
                    if self._fm_is_reparse(child):
                        raise PermissionError(f"Reparse point/symlink inside directory tree: {child}")
            else:
                safe_dirs = []
                for name in dirs:
                    child = os.path.join(root, name)
                    if self._fm_is_reparse(child):
                        self._fm_validate_access_path(
                            child,
                            "read",
                            follow_symlinks=True,
                            include_leaf=True,
                        )
                    real_child = os.path.normcase(os.path.realpath(child))
                    if real_child in visited_directories:
                        raise PermissionError(f"Directory link cycle blocked: {child}")
                    visited_directories.add(real_child)
                    safe_dirs.append(name)
                dirs[:] = safe_dirs
            dirs.sort(key=str.casefold)
            files.sort(key=str.casefold)
            for name in dirs:
                directory_path = os.path.join(root, name)
                relative = os.path.relpath(directory_path, path).replace("\\", "/") + "/"
                manifest.append({
                    "path": relative,
                    "type": "directory",
                    "hash": None,
                    "bytes": 0,
                })
            for name in files:
                file_path = os.path.join(root, name)
                if self._fm_is_reparse(file_path) and not follow_symlinks:
                    raise PermissionError(f"Reparse point/symlink inside directory tree: {file_path}")
                if self._fm_is_reparse(file_path):
                    self._fm_validate_access_path(
                        file_path,
                        "read",
                        follow_symlinks=True,
                        include_leaf=True,
                    )
                digest, size = self._fm_hash_file(file_path, algorithm)
                relative = os.path.relpath(file_path, path).replace("\\", "/")
                manifest.append({
                    "path": relative,
                    "type": "file",
                    "hash": digest,
                    "bytes": size,
                })
                total_bytes += size
        root_digest = hashlib.new(algorithm)
        for item in manifest:
            root_digest.update(
                f"{item['type']}\0{item['path']}\0{item['bytes']}\0{item['hash'] or ''}\n".encode(
                    "utf-8",
                    errors="surrogatepass",
                )
            )
        result = {
            "path": path,
            "type": "directory",
            "algorithm": algorithm,
            "hash": root_digest.hexdigest(),
            "bytes": total_bytes,
            "items": len(manifest),
        }
        if include_entries:
            result["entries"] = manifest
        return result

    def _fm_compare(self, first, second, args):
        algorithm = self._fm_hash_algorithm(args)
        first_hash = self._fm_hash_path(first, algorithm, bool(args.get("follow_symlinks", False)), include_entries=True)
        second_hash = self._fm_hash_path(second, algorithm, bool(args.get("follow_symlinks", False)), include_entries=True)
        result = {
            "ok": True,
            "action": "compare",
            "same": first_hash["hash"] == second_hash["hash"] and first_hash["type"] == second_hash["type"],
            "source": {key: value for key, value in first_hash.items() if key != "entries"},
            "destination": {key: value for key, value in second_hash.items() if key != "entries"},
        }
        if first_hash["type"] == second_hash["type"] == "directory":
            first_entries = {item["path"]: item for item in first_hash.get("entries", [])}
            second_entries = {item["path"]: item for item in second_hash.get("entries", [])}
            limit = max(1, min(int(args.get("limit") or 500), 5000))
            differences = []
            for relative in sorted(set(first_entries) | set(second_entries), key=str.casefold):
                left = first_entries.get(relative)
                right = second_entries.get(relative)
                if left == right:
                    continue
                differences.append({
                    "path": relative,
                    "status": "only_source" if right is None else "only_destination" if left is None else "changed",
                    "source_hash": left.get("hash") if left else None,
                    "destination_hash": right.get("hash") if right else None,
                })
            result["differences"] = differences[:limit]
            result["differences_total"] = len(differences)
            result["truncated"] = len(differences) > limit
        return result

    def _fm_encoding(self, args):
        encoding = str(args.get("encoding") or "utf-8").strip().lower().replace("_", "-")
        try:
            canonical = codecs.lookup(encoding).name.replace("_", "-")
        except LookupError as exc:
            raise ValueError(f"Unknown encoding: {encoding}") from exc
        aliases = {
            "iso8859-1": "latin-1",
            "windows-1252": "cp1252",
            "windows-1255": "cp1255",
        }
        canonical = aliases.get(canonical, canonical)
        if canonical not in FILE_MANAGER_ENCODINGS:
            raise ValueError(f"Unsupported safe text encoding: {encoding}")
        return canonical

    def _fm_read_chunk(self, path, args):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        offset = max(0, int(args.get("offset") or 0))
        limit = max(1, min(int(args.get("limit") or 65536), _MAX_READ_CHUNK))
        mode = str(args.get("mode") or "text").strip().lower()
        if mode not in {"text", "binary"}:
            raise ValueError("read_chunk mode must be text or binary.")
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            handle.seek(offset)
            data = handle.read(limit)
        result = {
            "path": path,
            "mode": mode,
            "offset": offset,
            "bytes_read": len(data),
            "total_bytes": size,
            "next_offset": offset + len(data),
            "eof": offset + len(data) >= size,
            "chunk_sha256": hashlib.sha256(data).hexdigest(),
        }
        if mode == "binary":
            result["base64"] = base64.b64encode(data).decode("ascii")
        else:
            encoding = self._fm_encoding(args)
            result["encoding"] = encoding
            result["text"] = data.decode(encoding, errors="replace")
        return result

    def _fm_diff_text(self, first, second, args):
        encoding = self._fm_encoding(args)
        for path in (first, second):
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            if os.path.getsize(path) > _MAX_DIFF_INPUT:
                raise ValueError(f"diff_text input exceeds {_MAX_DIFF_INPUT} bytes: {path}")
        with open(first, "r", encoding=encoding, errors="replace") as handle:
            first_lines = handle.readlines()
        with open(second, "r", encoding=encoding, errors="replace") as handle:
            second_lines = handle.readlines()
        diff = list(difflib.unified_diff(
            first_lines,
            second_lines,
            fromfile=first,
            tofile=second,
            lineterm="",
        ))
        limit = max(1, min(int(args.get("limit") or 1000), 10000))
        return {
            "ok": True,
            "action": "diff_text",
            "same": not diff,
            "source": first,
            "destination": second,
            "encoding": encoding,
            "diff": "\n".join(diff[:limit]),
            "lines_total": len(diff),
            "truncated": len(diff) > limit,
        }

    def _fm_disk_usage(self, path, args):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        selected_bytes = 0
        files = 0
        directories = 0
        if os.path.isfile(path):
            selected_bytes = os.path.getsize(path)
            files = 1
        else:
            follow = bool(args.get("follow_symlinks", False))
            visited_directories = {os.path.normcase(os.path.realpath(path))}
            for root, dirs, names in os.walk(path, followlinks=follow):
                self._raise_if_cancelled()
                if not follow:
                    dirs[:] = [
                        name for name in dirs
                        if not self._fm_is_reparse(os.path.join(root, name))
                    ]
                else:
                    safe_dirs = []
                    for name in dirs:
                        child = os.path.join(root, name)
                        if self._fm_is_reparse(child):
                            self._fm_validate_access_path(
                                child,
                                "read",
                                follow_symlinks=True,
                                include_leaf=True,
                            )
                        real_child = os.path.normcase(os.path.realpath(child))
                        if real_child in visited_directories:
                            continue
                        visited_directories.add(real_child)
                        safe_dirs.append(name)
                    dirs[:] = safe_dirs
                directories += len(dirs)
                for name in names:
                    file_path = os.path.join(root, name)
                    if self._fm_is_reparse(file_path) and not follow:
                        continue
                    if self._fm_is_reparse(file_path):
                        self._fm_validate_access_path(
                            file_path,
                            "read",
                            follow_symlinks=True,
                            include_leaf=True,
                        )
                    try:
                        selected_bytes += os.path.getsize(file_path)
                        files += 1
                    except OSError:
                        continue
                self._fm_progress("מחשב שימוש בדיסק", files + directories)
        volume = shutil.disk_usage(path if os.path.isdir(path) else os.path.dirname(path))
        return {
            "path": path,
            "selected_bytes": selected_bytes,
            "files": files,
            "directories": directories,
            "volume_total": volume.total,
            "volume_used": volume.used,
            "volume_free": volume.free,
        }

    def _fm_conflict(self, args):
        conflict = str(args.get("conflict") or "fail").strip().lower()
        if conflict not in FILE_MANAGER_CONFLICTS:
            raise ValueError(f"conflict must be one of {sorted(FILE_MANAGER_CONFLICTS)}")
        return conflict

    def _fm_plan_mutation(self, action, args):
        args = dict(args or {})
        follow = bool(args.get("follow_symlinks", False))
        conflict = self._fm_conflict(args)
        plan = {
            "action": action,
            "args": args,
            "reads": [],
            "writes": [],
            "follow_symlinks": follow,
            "conflict": conflict,
        }
        if bool(args.get("preserve_acl", False)):
            raise ValueError("preserve_acl is not supported; Smarti will not claim ACL preservation.")

        if action in {"mkdir", "atomic_write_text", "append_text", "touch"}:
            path = self._fm_resolve_path(args.get("path") or args.get("destination"), destination=True)
            self._fm_validate_destination_name(path)
            plan.update(path=path, writes=[path])
        elif action in {"copy", "move", "rename"}:
            source = self._fm_resolve_path(args.get("source") or args.get("path"))
            destination_value = args.get("destination")
            if action == "rename":
                destination = self._fm_resolve_path(
                    destination_value,
                    destination=True,
                    source_parent=os.path.dirname(source),
                )
                if os.path.normcase(os.path.dirname(source)) != os.path.normcase(os.path.dirname(destination)):
                    raise ValueError("rename must stay in the same directory; use move across directories.")
            else:
                destination = self._fm_resolve_path(destination_value, destination=True)
            self._fm_validate_destination_name(destination)
            plan.update(
                source=source,
                destination=destination,
                reads=[source],
                writes=[destination] + ([source] if action in {"move", "rename"} else []),
            )
        elif action == "trash":
            path = self._fm_resolve_path(args.get("path") or args.get("source"))
            plan.update(path=path, writes=[path])
        elif action == "restore_from_trash":
            record = self._fm_resolve_recycle_record(
                str(args.get("recycle_id") or "").strip(),
                args.get("path"),
            )
            destination = self._fm_resolve_path(
                args.get("destination") or record["original_path"],
                destination=True,
            )
            self._fm_validate_destination_name(destination)
            plan.update(
                destination=destination,
                writes=[destination],
                recycle_record=record,
            )
        elif action == "zip":
            raw_sources = args.get("paths")
            if not isinstance(raw_sources, list) or not raw_sources:
                raw_sources = [args.get("source") or args.get("path")]
            sources = [self._fm_resolve_path(item) for item in raw_sources]
            destination_value = args.get("destination")
            if not destination_value:
                destination_value = sources[0].rstrip("\\/") + ".zip"
            destination = self._fm_resolve_path(destination_value, destination=True)
            if os.path.splitext(destination)[1].lower() != ".zip":
                raise ValueError("zip destination must use the .zip extension.")
            self._fm_validate_destination_name(destination)
            plan.update(sources=sources, destination=destination, reads=sources, writes=[destination])
        elif action == "unzip":
            source = self._fm_resolve_path(args.get("source") or args.get("path"))
            destination = self._fm_resolve_path(args.get("destination"), destination=True)
            self._fm_validate_destination_name(destination)
            plan.update(source=source, destination=destination, reads=[source], writes=[destination])
        else:
            raise ValueError(f"Unsupported mutating action: {action}")
        return plan

    def _fm_validate_plan_paths(self, plan):
        follow = plan["follow_symlinks"]
        for path in plan["reads"]:
            self._fm_validate_access_path(path, "read", follow_symlinks=follow, include_leaf=True)
            if not os.path.lexists(path):
                raise FileNotFoundError(path)
        for path in plan["writes"]:
            include_leaf = os.path.lexists(path)
            self._fm_validate_access_path(path, "write", follow_symlinks=follow, include_leaf=include_leaf)
        action = plan["action"]
        source = plan.get("source")
        destination = plan.get("destination")
        if action == "trash" and not os.path.lexists(plan["path"]):
            raise FileNotFoundError(plan["path"])
        if source and action in {"copy", "move", "rename"}:
            if not os.path.lexists(source):
                raise FileNotFoundError(source)
            if os.path.isdir(source):
                source_real = os.path.realpath(source)
                destination_real = os.path.realpath(destination)
                try:
                    common = os.path.commonpath([source_real, destination_real])
                except ValueError:
                    common = ""
                if os.path.normcase(common) == os.path.normcase(source_real):
                    raise ValueError("A directory cannot be copied or moved into itself.")
        if action in {"mkdir", "atomic_write_text"}:
            original_path = plan["path"]
            if action == "mkdir" and plan["conflict"] == "overwrite" and os.path.lexists(original_path):
                raise ValueError("overwrite is not meaningful for an existing directory.")
            if action == "atomic_write_text" and os.path.isdir(original_path):
                raise IsADirectoryError(original_path)
            resolved_path = self._fm_resolve_conflict(original_path, plan["conflict"])
            plan["path"] = resolved_path
            plan["writes"] = [
                resolved_path if item == original_path else item
                for item in plan["writes"]
            ]
        elif destination and action in {
            "copy", "move", "rename", "restore_from_trash", "zip", "unzip",
        }:
            if (
                action in {"copy", "move", "rename", "zip"}
                and plan["conflict"] == "overwrite"
                and os.path.isdir(destination)
            ):
                raise ValueError("Atomic overwrite of an existing directory is not supported.")
            if action == "unzip" and plan["conflict"] == "overwrite" and os.path.lexists(destination):
                raise ValueError("Atomic overwrite of an existing extraction destination is not supported.")
            resolved_destination = self._fm_resolve_conflict(
                destination,
                plan["conflict"],
                source=source,
            )
            plan["destination"] = resolved_destination
            plan["writes"] = [
                resolved_destination if item == destination else item
                for item in plan["writes"]
            ]
        expected_hash = str(plan["args"].get("expected_hash") or "").strip().lower()
        if expected_hash:
            check_path = source or plan.get("path")
            if action == "restore_from_trash":
                check_path = plan["recycle_record"]["data_path"]
            elif action == "zip":
                if len(plan["sources"]) != 1:
                    raise ValueError("expected_hash with zip requires exactly one source.")
                check_path = plan["sources"][0]
            if check_path and os.path.exists(check_path):
                actual = self._fm_hash_path(check_path, "sha256", follow)["hash"].lower()
                if actual != expected_hash:
                    raise ValueError(f"expected_hash mismatch for {check_path}: expected {expected_hash}, observed {actual}")

    def _fm_public_plan(self, plan):
        public = {
            "action": plan["action"],
            "reads": list(plan["reads"]),
            "writes": list(plan["writes"]),
            "conflict": plan["conflict"],
            "follow_symlinks": plan["follow_symlinks"],
        }
        for key in ("path", "source", "destination", "sources"):
            if key in plan:
                public[key] = plan[key]
        if "recycle_record" in plan:
            public["recycle_id"] = plan["recycle_record"]["recycle_id"]
            public["original_path"] = plan["recycle_record"]["original_path"]
        return public

    def _fm_authorize_plans(self, plans, sub_action):
        writes = []
        reads = []
        overwrite = False
        risk = "medium"
        for plan in plans:
            writes.extend(plan["writes"])
            reads.extend(plan["reads"])
            overwrite = overwrite or plan["conflict"] == "overwrite"
            if plan["action"] in {"move", "rename", "trash", "restore_from_trash", "unzip"}:
                risk = "high"
        details = [
            f"פעולה: {sub_action}",
            f"מדיניות התנגשות: {'overwrite (מפורש)' if overwrite else plans[0]['conflict'] if plans else 'fail'}",
        ]
        if reads:
            details.append("מקורות:\n" + "\n".join(f"- {path}" for path in reads[:30]))
        if writes:
            details.append("נתיבים שישתנו:\n" + "\n".join(f"- {path}" for path in writes[:30]))
        allowed, error = self._ensure_capability_allowed(
            "file_write",
            "אישור פעולת קבצים",
            "\n\n".join(details),
            risk="high" if overwrite else risk,
            audit_context={"manager": "file_manager", "sub_action": sub_action},
        )
        if not allowed:
            return False, error
        if self._sandbox_enabled():
            return True, None

        allowed_roots = [
            self._abs_path(path)
            for path in (self.settings.get("allowed_write_dirs") or [])
            if str(path or "").strip()
        ]
        outside = [
            path for path in writes
            if allowed_roots and not self._path_in_roots(self._fm_display_path(path), allowed_roots)
        ]
        if (
            outside
            and self.settings.get("write_outside_allowed_dirs_requires_approval", True)
            and not self._is_max_autonomy_mode()
            and self._policy_decision("file_write") == "allow"
        ):
            extra_details = (
                "הפעולה משנה נתיבים מחוץ לתיקיות הכתיבה המועדפות:\n"
                + "\n".join(f"- {path}" for path in outside[:30])
                + "\n\nתיקיות מועדפות:\n"
                + "\n".join(f"- {path}" for path in allowed_roots[:10])
            )
            if not self._request_user_approval(
                "אישור כתיבה מחוץ לתיקיות המועדפות",
                extra_details,
                risk="high",
            ):
                return False, "ERROR: User denied writing outside allowed write directories."
        return True, None

    def _fm_execute_batch(self, args):
        operations = args.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ValueError("batch requires a non-empty operations array.")
        if len(operations) > 100:
            raise ValueError("batch supports at most 100 operations.")
        plans = []
        results = []
        top_dry_run = bool(args.get("dry_run", False))
        for index, item in enumerate(operations):
            self._raise_if_cancelled()
            if not isinstance(item, dict):
                results.append({"index": index, "ok": False, "error": "Operation must be an object."})
                continue
            item = {**args, **item}
            item.pop("operations", None)
            item.pop("idempotency_key", None)
            item["dry_run"] = top_dry_run
            action = str(item.get("action") or "").strip().lower()
            if action not in FILE_MANAGER_BATCH_ACTIONS:
                results.append({
                    "index": index,
                    "ok": False,
                    "action": action,
                    "error": f"Unsupported batch action: {action or '(missing)'}",
                })
                continue
            try:
                plan = self._fm_plan_mutation(action, item)
                self._fm_validate_plan_paths(plan)
                plans.append((index, plan))
                results.append({
                    "index": index,
                    "ok": True,
                    "action": action,
                    "status": "planned",
                    "plan": self._fm_public_plan(plan),
                })
            except Exception as exc:
                results.append({
                    "index": index,
                    "ok": False,
                    "action": action,
                    "error": f"{type(exc).__name__}: {exc}",
                })
        if top_dry_run:
            return {
                "ok": all(item["ok"] for item in results),
                "status": "dry_run" if all(item["ok"] for item in results) else "partial",
                "action": "batch",
                "items": results,
            }
        if not plans:
            return {"ok": False, "status": "failed", "action": "batch", "items": results}
        allowed, error = self._fm_authorize_plans([plan for _, plan in plans], "batch")
        if not allowed:
            return {
                "ok": False,
                "status": "denied",
                "action": "batch",
                "error": error,
                "items": results,
            }
        for index, plan in plans:
            self._raise_if_cancelled()
            try:
                observed = self._fm_execute_mutation(plan)
                results[index] = {
                    "index": index,
                    "ok": True,
                    "action": plan["action"],
                    "status": "success",
                    "result": observed,
                }
            except SmartiCancelled:
                raise
            except Exception as exc:
                results[index] = {
                    "index": index,
                    "ok": False,
                    "action": plan["action"],
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        succeeded = sum(1 for item in results if item.get("ok") and item.get("status") == "success")
        failed = len(results) - succeeded
        return {
            "ok": failed == 0,
            "status": "success" if failed == 0 else "partial" if succeeded else "failed",
            "action": "batch",
            "succeeded": succeeded,
            "failed": failed,
            "items": results,
        }

    def _fm_resolve_conflict(self, destination, conflict, *, source=None):
        if not os.path.lexists(destination):
            return destination
        if source and os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(destination)):
            if os.path.abspath(source) != os.path.abspath(destination):
                return destination
            raise ValueError("Source and destination are the same path.")
        if conflict == "fail":
            raise FileExistsError(destination)
        if conflict == "rename":
            return self._fm_unique_path(destination)
        return destination

    @staticmethod
    def _fm_unique_path(path):
        parent = os.path.dirname(path)
        name = os.path.basename(path)
        stem, suffix = os.path.splitext(name)
        for index in range(1, 10001):
            candidate = os.path.join(parent, f"{stem} ({index}){suffix}")
            if not os.path.lexists(candidate):
                return candidate
        raise FileExistsError(f"Could not allocate a conflict-free name for {path}")

    @staticmethod
    def _fm_create_parents(path, enabled):
        parent = os.path.dirname(path)
        if not parent:
            return
        if enabled:
            os.makedirs(parent, exist_ok=True)
        elif not os.path.isdir(parent):
            raise FileNotFoundError(f"Parent directory does not exist: {parent}")

    def _fm_execute_mutation(self, plan):
        self._raise_if_cancelled()
        action = plan["action"]
        args = plan["args"]
        conflict = plan["conflict"]
        create_parents = bool(args.get("create_parents", False))
        if action == "mkdir":
            path = self._fm_resolve_conflict(plan["path"], conflict)
            self._fm_create_parents(path, create_parents)
            os.mkdir(path)
            return {"ok": True, "action": action, "observed": self._fm_stat_path(path)}
        if action in {"atomic_write_text", "append_text"}:
            path = plan["path"]
            self._fm_validate_text_destination(path)
            if action == "atomic_write_text":
                path = self._fm_resolve_conflict(path, conflict)
            elif not os.path.exists(path):
                path = self._fm_resolve_conflict(path, conflict)
            self._fm_create_parents(path, create_parents)
            before = self._fm_stat_path(path)
            encoding = self._fm_encoding(args)
            content = str(args.get("content") or "")
            if action == "append_text" and os.path.exists(path):
                self._fm_atomic_append(path, content, encoding)
            else:
                self._fm_atomic_write(path, content, encoding, overwrite=conflict == "overwrite")
            observed_hash = self._fm_hash_path(path, "sha256")
            return {
                "ok": True,
                "action": action,
                "before": before,
                "observed": self._fm_stat_path(path),
                "hash": observed_hash["hash"],
                "bytes": observed_hash["bytes"],
                "encoding": encoding,
            }
        if action == "touch":
            path = plan["path"]
            self._fm_create_parents(path, create_parents)
            before = self._fm_stat_path(path)
            if not os.path.exists(path):
                with open(path, "xb"):
                    pass
            else:
                os.utime(path, None, follow_symlinks=False)
            return {"ok": True, "action": action, "before": before, "observed": self._fm_stat_path(path)}
        if action == "copy":
            destination = self._fm_copy_path(
                plan["source"],
                plan["destination"],
                conflict,
                create_parents=create_parents,
                preserve_timestamps=bool(args.get("preserve_timestamps", False)),
                follow_symlinks=plan["follow_symlinks"],
            )
            observed = self._fm_hash_path(destination, "sha256", plan["follow_symlinks"])
            return {"ok": True, "action": action, "source": plan["source"], "destination": destination, **observed}
        if action in {"move", "rename"}:
            case_only_rename = (
                action == "rename"
                and os.name == "nt"
                and os.path.normcase(plan["source"]) == os.path.normcase(plan["destination"])
                and os.path.abspath(plan["source"]) != os.path.abspath(plan["destination"])
            )
            destination = self._fm_move_path(
                plan["source"],
                plan["destination"],
                conflict,
                create_parents=create_parents,
                preserve_timestamps=bool(args.get("preserve_timestamps", False)),
                follow_symlinks=plan["follow_symlinks"],
            )
            observed = self._fm_hash_path(destination, "sha256", plan["follow_symlinks"])
            return {
                "ok": True,
                "action": action,
                "source": plan["source"],
                "source_exists_after": os.path.lexists(plan["source"]),
                "case_only_rename": case_only_rename,
                "destination": destination,
                **observed,
            }
        if action == "trash":
            before = self._fm_stat_path(plan["path"])
            response = self._move_path_to_recycle_bin(plan["path"])
            if str(response).startswith("ERROR"):
                raise OSError(response.removeprefix("ERROR:").strip())
            records = self._fm_find_recycle_records(original_path=plan["path"])
            latest = max(records, key=lambda item: item.get("deleted_at_timestamp", 0), default=None)
            return {
                "ok": True,
                "action": action,
                "before": before,
                "original_path": plan["path"],
                "exists_after": os.path.lexists(plan["path"]),
                "recycle_id": latest.get("recycle_id") if latest else None,
                "restore_available": bool(latest),
            }
        if action == "restore_from_trash":
            destination = self._fm_restore_record(
                plan["recycle_record"],
                plan["destination"],
                conflict,
                create_parents=create_parents,
            )
            return {
                "ok": True,
                "action": action,
                "recycle_id": plan["recycle_record"]["recycle_id"],
                "destination": destination,
                "observed": self._fm_stat_path(destination),
            }
        if action == "zip":
            destination = self._fm_create_zip(
                plan["sources"],
                plan["destination"],
                conflict,
                create_parents=create_parents,
                follow_symlinks=plan["follow_symlinks"],
            )
            observed = self._fm_hash_path(destination, "sha256")
            return {"ok": True, "action": action, "destination": destination, **observed}
        if action == "unzip":
            destination = self._fm_extract_zip(
                plan["source"],
                plan["destination"],
                conflict,
                create_parents=create_parents,
            )
            observed = self._fm_hash_path(destination, "sha256")
            return {"ok": True, "action": action, "source": plan["source"], "destination": destination, **observed}
        raise ValueError(f"Unsupported mutating action: {action}")

    @staticmethod
    def _fm_validate_text_destination(path):
        extension = os.path.splitext(path)[1].lower()
        if extension in BLOCKED_WRITE_EXTENSIONS:
            raise ValueError(f"Blocked executable/script extension for text write: {extension}")
        if extension and extension not in SAFE_TEXT_EXTENSIONS:
            raise ValueError(f"Unsupported safe text extension: {extension}")

    def _fm_install_temp_file(self, temporary, destination):
        os.replace(temporary, destination)

    def _fm_atomic_write(self, path, content, encoding, *, overwrite):
        if os.path.exists(path) and not overwrite:
            raise FileExistsError(path)
        temporary = None
        try:
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding=encoding,
                newline="",
                delete=False,
                dir=os.path.dirname(path),
                prefix=".smarti-",
                suffix=".tmp",
            )
            temporary = handle.name
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._fm_install_temp_file(temporary, path)
            temporary = None
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _fm_atomic_append(self, path, content, encoding):
        temporary = None
        try:
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=os.path.dirname(path),
                prefix=".smarti-",
                suffix=".tmp",
            )
            temporary = handle.name
            with handle:
                with open(path, "rb") as source_handle:
                    while True:
                        self._raise_if_cancelled()
                        chunk = source_handle.read(_FILE_CHUNK_SIZE)
                        if not chunk:
                            break
                        handle.write(chunk)
                append_encoding = encoding
                if encoding == "utf-16":
                    with open(path, "rb") as existing:
                        marker = existing.read(2)
                    append_encoding = "utf-16-be" if marker == b"\xfe\xff" else "utf-16-le"
                elif encoding == "utf-8-sig":
                    append_encoding = "utf-8"
                handle.write(content.encode(append_encoding))
                handle.flush()
                os.fsync(handle.fileno())
            self._fm_install_temp_file(temporary, path)
            temporary = None
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _fm_copy_path(
        self,
        source,
        destination,
        conflict,
        *,
        create_parents,
        preserve_timestamps,
        follow_symlinks,
    ):
        destination = self._fm_resolve_conflict(destination, conflict, source=source)
        self._fm_create_parents(destination, create_parents)
        if os.path.isdir(source):
            if os.path.lexists(destination) and conflict == "overwrite":
                raise ValueError("Atomic overwrite of an existing directory is not supported.")
            source_hash = self._fm_hash_path(source, "sha256", follow_symlinks)
            temporary = tempfile.mkdtemp(prefix=".smarti-", dir=os.path.dirname(destination))
            os.rmdir(temporary)
            try:
                copy_function = shutil.copy2 if preserve_timestamps else shutil.copyfile
                shutil.copytree(
                    source,
                    temporary,
                    symlinks=not follow_symlinks,
                    copy_function=copy_function,
                )
                copied_hash = self._fm_hash_path(temporary, "sha256", follow_symlinks)
                if source_hash["hash"] != copied_hash["hash"]:
                    raise OSError("Directory copy verification failed.")
                os.replace(temporary, destination)
                temporary = None
            finally:
                if temporary and os.path.exists(temporary):
                    shutil.rmtree(temporary, ignore_errors=True)
        else:
            temporary = None
            try:
                handle = tempfile.NamedTemporaryFile(
                    mode="wb",
                    delete=False,
                    dir=os.path.dirname(destination),
                    prefix=".smarti-",
                    suffix=".tmp",
                )
                temporary = handle.name
                digest = hashlib.sha256()
                total = 0
                with handle, open(source, "rb") as source_handle:
                    while True:
                        self._raise_if_cancelled()
                        chunk = source_handle.read(_FILE_CHUNK_SIZE)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        total += len(chunk)
                        self._fm_progress("מעתיק קובץ", total, os.path.getsize(source))
                    handle.flush()
                    os.fsync(handle.fileno())
                copied_hash, _ = self._fm_hash_file(temporary, "sha256")
                if copied_hash != digest.hexdigest():
                    raise OSError("File copy verification failed.")
                if preserve_timestamps:
                    shutil.copystat(source, temporary, follow_symlinks=False)
                self._fm_install_temp_file(temporary, destination)
                temporary = None
            finally:
                if temporary and os.path.exists(temporary):
                    try:
                        os.unlink(temporary)
                    except OSError:
                        pass
        return destination

    @staticmethod
    def _fm_same_volume(source, destination):
        if os.name == "nt":
            return os.path.splitdrive(source)[0].casefold() == os.path.splitdrive(destination)[0].casefold()
        source_device = os.stat(source).st_dev
        existing_parent = os.path.dirname(destination)
        while existing_parent and not os.path.exists(existing_parent):
            parent = os.path.dirname(existing_parent)
            if parent == existing_parent:
                break
            existing_parent = parent
        return source_device == os.stat(existing_parent or os.curdir).st_dev

    @staticmethod
    def _fm_remove_internal(path):
        if os.path.isdir(path) and not os.path.islink(path):
            if os.name == "nt" and not str(path).startswith("\\\\?\\"):
                absolute = os.path.abspath(path)
                path = "\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\") else "\\\\?\\" + absolute
            shutil.rmtree(path)
        else:
            os.unlink(path)

    def _fm_move_path(
        self,
        source,
        destination,
        conflict,
        *,
        create_parents,
        preserve_timestamps,
        follow_symlinks,
    ):
        destination = self._fm_resolve_conflict(destination, conflict, source=source)
        self._fm_create_parents(destination, create_parents)
        case_only = (
            os.name == "nt"
            and os.path.normcase(source) == os.path.normcase(destination)
            and os.path.abspath(source) != os.path.abspath(destination)
        )
        if case_only:
            temporary = self._fm_unique_path(os.path.join(os.path.dirname(source), f".smarti-case-{uuid.uuid4().hex}"))
            os.replace(source, temporary)
            try:
                os.replace(temporary, destination)
            except Exception:
                os.replace(temporary, source)
                raise
            return destination
        if self._fm_same_volume(source, destination):
            if os.path.isdir(destination) and conflict == "overwrite":
                raise ValueError("Atomic overwrite of an existing directory is not supported.")
            os.replace(source, destination)
            return destination
        backup = None
        copy_conflict = conflict
        if conflict == "overwrite" and os.path.lexists(destination):
            if os.path.isdir(destination):
                raise ValueError("Atomic overwrite of an existing directory is not supported.")
            backup = self._fm_unique_path(
                os.path.join(os.path.dirname(destination), f".smarti-overwrite-{uuid.uuid4().hex}.bak")
            )
            os.replace(destination, backup)
            copy_conflict = "fail"
        try:
            copied = self._fm_copy_path(
                source,
                destination,
                copy_conflict,
                create_parents=create_parents,
                preserve_timestamps=preserve_timestamps,
                follow_symlinks=follow_symlinks,
            )
        except Exception:
            if backup and os.path.lexists(backup):
                os.replace(backup, destination)
            raise
        source_hash = self._fm_hash_path(source, "sha256", follow_symlinks)
        destination_hash = self._fm_hash_path(copied, "sha256", follow_symlinks)
        if source_hash["hash"] != destination_hash["hash"]:
            self._fm_remove_internal(copied)
            if backup and os.path.lexists(backup):
                os.replace(backup, destination)
            raise OSError("Cross-volume move verification failed; source was retained.")
        try:
            self._fm_remove_internal(source)
        except Exception as exc:
            try:
                self._fm_remove_internal(copied)
                if backup and os.path.lexists(backup):
                    os.replace(backup, destination)
            except Exception as rollback_exc:
                raise OSError(
                    f"Source removal failed after verified copy, and destination rollback also failed: "
                    f"{exc}; rollback: {rollback_exc}"
                ) from exc
            raise OSError(f"Source removal failed after verified copy; destination was rolled back: {exc}") from exc
        if backup and os.path.lexists(backup):
            try:
                self._fm_remove_internal(backup)
            except OSError as exc:
                logging.warning("Cross-volume move left overwrite backup %s: %s", backup, exc)
        return copied

    @staticmethod
    def _fm_zip_member_is_symlink(info):
        mode = (int(info.external_attr) >> 16) & 0xFFFF
        return stat_module.S_ISLNK(mode)

    def _fm_safe_zip_target(self, root, member_name):
        normalized = str(member_name or "").replace("\\", "/")
        if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
            raise ValueError(f"Unsafe absolute zip member: {member_name}")
        parts = [part for part in normalized.split("/") if part not in {"", "."}]
        if any(part == ".." for part in parts):
            raise ValueError(f"Zip path traversal blocked: {member_name}")
        target = os.path.abspath(os.path.join(root, *parts))
        if os.path.commonpath([os.path.abspath(root), target]) != os.path.abspath(root):
            raise ValueError(f"Zip path traversal blocked: {member_name}")
        self._fm_validate_destination_name(target)
        return target

    def _fm_create_zip(self, sources, destination, conflict, *, create_parents, follow_symlinks):
        destination = self._fm_resolve_conflict(destination, conflict)
        self._fm_create_parents(destination, create_parents)
        temporary = None
        entry_count = 0
        archive_names = set()
        try:
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                delete=False,
                dir=os.path.dirname(destination),
                prefix=".smarti-",
                suffix=".zip",
            )
            temporary = handle.name
            handle.close()
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for source in sources:
                    if not os.path.lexists(source):
                        raise FileNotFoundError(source)
                    base_parent = os.path.dirname(source.rstrip("\\/"))
                    if os.path.isfile(source):
                        archive_name = os.path.basename(source)
                        archive_key = archive_name.casefold() if os.name == "nt" else archive_name
                        if archive_key in archive_names:
                            raise ValueError(f"Duplicate zip member name: {archive_name}")
                        archive_names.add(archive_key)
                        archive.write(source, archive_name)
                        entry_count += 1
                        if entry_count > _MAX_ARCHIVE_ENTRIES:
                            raise ValueError(f"zip supports at most {_MAX_ARCHIVE_ENTRIES} entries.")
                        continue
                    visited_directories = {os.path.normcase(os.path.realpath(source))}
                    for root, dirs, files in os.walk(source, followlinks=follow_symlinks):
                        self._raise_if_cancelled()
                        if not follow_symlinks:
                            for name in list(dirs):
                                child = os.path.join(root, name)
                                if self._fm_is_reparse(child):
                                    raise PermissionError(f"Reparse point/symlink inside zip source: {child}")
                        else:
                            safe_dirs = []
                            for name in dirs:
                                child = os.path.join(root, name)
                                if self._fm_is_reparse(child):
                                    self._fm_validate_access_path(
                                        child,
                                        "read",
                                        follow_symlinks=True,
                                        include_leaf=True,
                                    )
                                real_child = os.path.normcase(os.path.realpath(child))
                                if real_child in visited_directories:
                                    raise PermissionError(f"Directory link cycle blocked: {child}")
                                visited_directories.add(real_child)
                                safe_dirs.append(name)
                            dirs[:] = safe_dirs
                        directory_name = os.path.relpath(root, base_parent).replace("\\", "/").rstrip("/") + "/"
                        directory_key = directory_name.casefold() if os.name == "nt" else directory_name
                        if directory_key in archive_names:
                            raise ValueError(f"Duplicate zip member name: {directory_name}")
                        archive_names.add(directory_key)
                        archive.writestr(directory_name, b"")
                        entry_count += 1
                        if entry_count > _MAX_ARCHIVE_ENTRIES:
                            raise ValueError(f"zip supports at most {_MAX_ARCHIVE_ENTRIES} entries.")
                        for name in files:
                            file_path = os.path.join(root, name)
                            if self._fm_is_reparse(file_path) and not follow_symlinks:
                                raise PermissionError(f"Reparse point/symlink inside zip source: {file_path}")
                            if self._fm_is_reparse(file_path):
                                self._fm_validate_access_path(
                                    file_path,
                                    "read",
                                    follow_symlinks=True,
                                    include_leaf=True,
                                )
                            if os.path.abspath(file_path) in {
                                os.path.abspath(destination),
                                os.path.abspath(temporary),
                            }:
                                continue
                            archive_name = os.path.relpath(file_path, base_parent).replace("\\", "/")
                            archive_key = archive_name.casefold() if os.name == "nt" else archive_name
                            if archive_key in archive_names:
                                raise ValueError(f"Duplicate zip member name: {archive_name}")
                            archive_names.add(archive_key)
                            archive.write(file_path, archive_name)
                            entry_count += 1
                            if entry_count > _MAX_ARCHIVE_ENTRIES:
                                raise ValueError(f"zip supports at most {_MAX_ARCHIVE_ENTRIES} entries.")
                            self._fm_progress("יוצר ארכיון", entry_count)
            self._fm_install_temp_file(temporary, destination)
            temporary = None
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
        return destination

    def _fm_extract_zip(self, source, destination, conflict, *, create_parents):
        if not zipfile.is_zipfile(source):
            raise ValueError(f"Not a valid zip archive: {source}")
        destination = self._fm_resolve_conflict(destination, conflict)
        self._fm_create_parents(destination, create_parents)
        if os.path.lexists(destination) and conflict == "overwrite":
            raise ValueError("Atomic overwrite of an existing directory is not supported.")
        temporary = tempfile.mkdtemp(prefix=".smarti-", dir=os.path.dirname(destination))
        try:
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                if len(infos) > _MAX_ARCHIVE_ENTRIES:
                    raise ValueError(f"Archive exceeds {_MAX_ARCHIVE_ENTRIES} entries.")
                total_uncompressed = sum(max(0, int(info.file_size)) for info in infos)
                if total_uncompressed > _MAX_ARCHIVE_UNCOMPRESSED:
                    raise ValueError("Archive uncompressed size exceeds the safe limit.")
                targets = []
                seen_targets = set()
                for info in infos:
                    if self._fm_zip_member_is_symlink(info):
                        raise ValueError(f"Symlink entries are blocked during unzip: {info.filename}")
                    target = self._fm_safe_zip_target(temporary, info.filename)
                    target_key = os.path.normcase(target)
                    if target_key in seen_targets:
                        raise ValueError(f"Duplicate zip destination is blocked: {info.filename}")
                    seen_targets.add(target_key)
                    targets.append((info, target))
                for index, (info, target) in enumerate(targets, start=1):
                    self._raise_if_cancelled()
                    if info.is_dir():
                        os.makedirs(target, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with archive.open(info, "r") as source_handle, open(target, "wb") as target_handle:
                            shutil.copyfileobj(source_handle, target_handle, length=_FILE_CHUNK_SIZE)
                            target_handle.flush()
                            os.fsync(target_handle.fileno())
                    self._fm_progress("מחלץ ארכיון", index, len(targets))
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary and os.path.exists(temporary):
                shutil.rmtree(temporary, ignore_errors=True)
        return destination

    @staticmethod
    def _fm_parse_recycle_metadata(metadata_path):
        with open(metadata_path, "rb") as handle:
            data = handle.read()
        if len(data) < 24:
            raise ValueError("Recycle metadata is too short.")
        version, original_size, deleted_filetime = struct.unpack_from("<QQQ", data, 0)
        if version == 2:
            if len(data) < 28:
                raise ValueError("Recycle metadata v2 is incomplete.")
            char_count = struct.unpack_from("<I", data, 24)[0]
            raw_path = data[28:28 + max(0, char_count) * 2]
        elif version == 1:
            raw_path = data[24:24 + 520]
        else:
            raise ValueError(f"Unknown recycle metadata version: {version}")
        original_path = raw_path.decode("utf-16-le", errors="ignore").split("\x00", 1)[0]
        if not original_path:
            raise ValueError("Recycle metadata has no original path.")
        unix_seconds = (deleted_filetime - 116444736000000000) / 10000000
        name = os.path.basename(metadata_path)
        data_name = "$R" + name[2:]
        data_path = os.path.join(os.path.dirname(metadata_path), data_name)
        return {
            "original_path": os.path.abspath(original_path),
            "original_size": int(original_size),
            "deleted_at_timestamp": unix_seconds,
            "deleted_at": datetime.fromtimestamp(unix_seconds, timezone.utc).isoformat(),
            "metadata_path": metadata_path,
            "data_path": data_path,
            "recycle_id": hashlib.sha256(os.path.abspath(metadata_path).encode("utf-8")).hexdigest()[:24],
        }

    @staticmethod
    def _fm_windows_drives():
        if os.name != "nt":
            return []
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        return [f"{chr(65 + index)}:\\" for index in range(26) if mask & (1 << index)]

    def _fm_find_recycle_records(self, *, original_path=None):
        if os.name != "nt":
            return []
        expected = os.path.normcase(os.path.abspath(original_path)) if original_path else None
        records = []
        for drive in self._fm_windows_drives():
            recycle_root = os.path.join(drive, "$Recycle.Bin")
            try:
                sid_directories = list(os.scandir(recycle_root))
            except OSError:
                continue
            for sid_entry in sid_directories:
                if not sid_entry.is_dir(follow_symlinks=False):
                    continue
                try:
                    metadata_entries = [
                        entry.path for entry in os.scandir(sid_entry.path)
                        if entry.is_file(follow_symlinks=False) and entry.name.upper().startswith("$I")
                    ]
                except OSError:
                    continue
                for metadata_path in metadata_entries:
                    try:
                        record = self._fm_parse_recycle_metadata(metadata_path)
                    except Exception:
                        continue
                    if not os.path.lexists(record["data_path"]):
                        continue
                    if expected and os.path.normcase(record["original_path"]) != expected:
                        continue
                    records.append(record)
        return records

    def _fm_resolve_recycle_record(self, recycle_id, original_path):
        records = self._fm_find_recycle_records(
            original_path=(
                None
                if recycle_id
                else self._fm_resolve_path(original_path) if original_path else None
            )
        )
        if recycle_id:
            records = [record for record in records if record["recycle_id"] == recycle_id]
        if not records:
            raise FileNotFoundError("No matching item was found in the Windows Recycle Bin.")
        if len(records) > 1 and not recycle_id:
            candidates = ", ".join(record["recycle_id"] for record in records[:10])
            raise ValueError(f"Multiple matching Recycle Bin items found; specify recycle_id: {candidates}")
        return records[0]

    def _fm_restore_record(self, record, destination, conflict, *, create_parents):
        metadata_path = record["metadata_path"]
        data_path = record["data_path"]
        if not os.path.isfile(metadata_path) or not os.path.lexists(data_path):
            raise FileNotFoundError("Recycle Bin item is incomplete or no longer exists.")
        destination = self._fm_resolve_conflict(destination, conflict)
        self._fm_create_parents(destination, create_parents)
        restored = self._fm_move_path(
            data_path,
            destination,
            conflict,
            create_parents=create_parents,
            preserve_timestamps=True,
            follow_symlinks=False,
        )
        try:
            os.unlink(metadata_path)
        except Exception as exc:
            try:
                self._fm_move_path(
                    restored,
                    data_path,
                    "fail",
                    create_parents=True,
                    preserve_timestamps=True,
                    follow_symlinks=False,
                )
            except Exception as rollback_exc:
                raise OSError(
                    f"Recycle metadata cleanup failed after restore, and rollback failed: "
                    f"{exc}; rollback: {rollback_exc}"
                ) from exc
            raise OSError(f"Recycle metadata cleanup failed; restored data was rolled back: {exc}") from exc
        return restored
