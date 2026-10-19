"""Runtime path resolution for source and packaged Smarti builds."""
import glob
import os
import shutil
import sys


APP_DATA_NAME = "SmartiAI"
RUNTIME_DIR_NAME = "runtime"


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _dedupe_paths(paths):
    seen = set()
    result = []
    for path in paths:
        if not path:
            continue
        try:
            normalized = os.path.normcase(os.path.abspath(path))
        except Exception:
            normalized = os.path.normcase(str(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(path)
    return result


class SmartiRuntime:
    """Single source of truth for bundled-runtime discovery."""

    def __init__(self):
        self.is_frozen = bool(getattr(sys, "frozen", False))
        self.force_bundled_runtime = _truthy(os.environ.get("SMARTI_FORCE_BUNDLED_RUNTIME"))
        self.install_dir = self._resolve_install_dir()
        self.resource_dir = self._resolve_resource_dir()
        self.app_dir = self.install_dir if self.is_frozen else self._source_root()
        runtime_override = os.environ.get("SMARTI_RUNTIME_DIR", "").strip()
        self.runtime_dir = os.path.abspath(os.path.expandvars(os.path.expanduser(runtime_override))) if runtime_override else os.path.join(self.install_dir, RUNTIME_DIR_NAME)
        self.user_data_dir = self._resolve_user_data_dir()

    def _source_root(self):
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _resolve_install_dir(self):
        if self.is_frozen:
            return os.path.dirname(os.path.abspath(sys.executable))
        return self._source_root()

    def _resolve_resource_dir(self):
        if self.is_frozen:
            return os.path.abspath(getattr(sys, "_MEIPASS", self.install_dir))
        return self._source_root()

    def _resolve_user_data_dir(self):
        override = os.environ.get("SMARTI_DATA_DIR", "").strip()
        candidates = []
        if override:
            candidates.append(os.path.abspath(os.path.expanduser(os.path.expandvars(override))))
        for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidates.append(os.path.join(base, APP_DATA_NAME))
        candidates.append(os.path.join(os.path.expanduser("~"), ".smarti"))
        for candidate in candidates:
            try:
                os.makedirs(candidate, exist_ok=True)
                return candidate
            except Exception:
                pass
        return self.app_dir

    def resource_path(self, *parts):
        return os.path.join(self.resource_dir, *parts)

    def runtime_path(self, *parts):
        return os.path.join(self.runtime_dir, *parts)

    def _private_runtime_enabled(self):
        return self.is_frozen or self.force_bundled_runtime

    def _first_existing(self, candidates):
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return None

    def _glob_first(self, pattern):
        matches = sorted(glob.glob(pattern))
        return matches[0] if matches else None

    def private_python_dir(self):
        if not self._private_runtime_enabled():
            return None
        candidates = [
            self.runtime_path("python"),
            self.runtime_path("python-embed"),
            self._glob_first(self.runtime_path("python-*")),
        ]
        return self._first_existing([path for path in candidates if path])

    def private_python_executable(self, prefer_console=True):
        override = os.environ.get("SMARTI_PYTHON_EXE", "").strip()
        if override and os.path.exists(override):
            return override
        python_dir = self.private_python_dir()
        if not python_dir:
            return None
        names = ("python.exe", "pythonw.exe") if prefer_console else ("pythonw.exe", "python.exe")
        return self._first_existing([os.path.join(python_dir, name) for name in names])

    def python_executable(self, prefer_console=True):
        private = self.private_python_executable(prefer_console=prefer_console)
        if private:
            return private
        if not self.is_frozen:
            exe = sys.executable
            if prefer_console and exe.lower().endswith("pythonw.exe"):
                candidate = os.path.join(os.path.dirname(exe), "python.exe")
                if os.path.exists(candidate):
                    return candidate
            return exe
        return shutil.which("python.exe") or shutil.which("python") or "python"

    def private_node_dir(self):
        if not self._private_runtime_enabled():
            return None
        candidates = [
            self.runtime_path("node"),
            self.runtime_path("nodejs"),
            self._glob_first(self.runtime_path("node-v*-win-x64")),
        ]
        return self._first_existing([path for path in candidates if path])

    def private_node_executable(self):
        override = os.environ.get("SMARTI_NODE_EXE", "").strip()
        if override and os.path.exists(override):
            return override
        node_dir = self.private_node_dir()
        return os.path.join(node_dir, "node.exe") if node_dir and os.path.exists(os.path.join(node_dir, "node.exe")) else None

    def private_npm_executable(self):
        override = os.environ.get("SMARTI_NPM_EXE", "").strip()
        if override and os.path.exists(override):
            return override
        node_dir = self.private_node_dir()
        if not node_dir:
            return None
        return self._first_existing([os.path.join(node_dir, "npm.cmd"), os.path.join(node_dir, "npm")])

    def private_npx_executable(self):
        override = os.environ.get("SMARTI_NPX_EXE", "").strip()
        if override and os.path.exists(override):
            return override
        node_dir = self.private_node_dir()
        if not node_dir:
            return None
        return self._first_existing([os.path.join(node_dir, "npx.cmd"), os.path.join(node_dir, "npx")])

    def python_scripts_dir(self):
        python_dir = self.private_python_dir()
        if not python_dir:
            return None
        return os.path.join(python_dir, "Scripts")

    def python_support_dirs(self):
        candidates = [
            self.resource_dir,
            os.path.join(self.install_dir, "python_support"),
            self.app_dir,
        ]
        return [path for path in _dedupe_paths(candidates) if path and os.path.isdir(path)]

    def managed_tool_dirs(self):
        dirs = [
            os.path.join(self.user_data_dir, "uv", "bin"),
            os.path.join(self.user_data_dir, "npm-global"),
            os.path.join(self.user_data_dir, "python-scripts"),
        ]
        user_profile = os.environ.get("USERPROFILE", "")
        appdata = os.environ.get("APPDATA", "")
        if user_profile:
            dirs.append(os.path.join(user_profile, ".local", "bin"))
        if appdata:
            dirs.append(os.path.join(appdata, "Python", "Scripts"))
        return _dedupe_paths(dirs)

    def path_prefixes(self):
        prefixes = []
        python_dir = self.private_python_dir()
        scripts_dir = self.python_scripts_dir()
        node_dir = self.private_node_dir()
        if python_dir:
            prefixes.append(python_dir)
        if scripts_dir:
            prefixes.append(scripts_dir)
        if node_dir:
            prefixes.append(node_dir)
        prefixes.extend(self.managed_tool_dirs())
        return _dedupe_paths(prefixes)

    def _with_prefixed_path(self, env):
        path_key = "Path" if "Path" in env else "PATH"
        current = env.get(path_key) or env.get("PATH") or ""
        parts = [part for part in current.split(os.pathsep) if part]
        merged = os.pathsep.join(_dedupe_paths(self.path_prefixes() + parts))
        env[path_key] = merged
        env["PATH"] = merged
        return env

    def subprocess_env(self, env=None):
        target = os.environ.copy() if env is None else dict(env)
        target.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        target.setdefault("PYTHONIOENCODING", "utf-8")
        target.setdefault("PYTHONUTF8", "1")
        target.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        target["SMARTI_FROZEN"] = "1" if self.is_frozen else "0"
        target["SMARTI_APP_DIR"] = self.app_dir
        target["SMARTI_RESOURCE_DIR"] = self.resource_dir
        target["SMARTI_RUNTIME_DIR"] = self.runtime_dir
        target["SMARTI_DATA_DIR"] = self.user_data_dir

        python_exe = self.private_python_executable()
        node_exe = self.private_node_executable()
        npm_exe = self.private_npm_executable()
        npx_exe = self.private_npx_executable()
        if python_exe:
            target["SMARTI_PYTHON_EXE"] = python_exe
        if node_exe:
            target["SMARTI_NODE_EXE"] = node_exe
        if npm_exe:
            target["SMARTI_NPM_EXE"] = npm_exe
        if npx_exe:
            target["SMARTI_NPX_EXE"] = npx_exe

        pip_cache = os.path.join(self.user_data_dir, "pip-cache")
        npm_cache = os.path.join(self.user_data_dir, "npm-cache")
        npm_prefix = os.path.join(self.user_data_dir, "npm-global")
        uv_tool_dir = os.path.join(self.user_data_dir, "uv", "tools")
        uv_bin_dir = os.path.join(self.user_data_dir, "uv", "bin")
        for directory in (pip_cache, npm_cache, npm_prefix, uv_tool_dir, uv_bin_dir):
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception:
                pass
        target.setdefault("PIP_CACHE_DIR", pip_cache)
        target.setdefault("npm_config_cache", npm_cache)
        target.setdefault("npm_config_prefix", npm_prefix)
        target.setdefault("UV_TOOL_DIR", uv_tool_dir)
        target.setdefault("UV_TOOL_BIN_DIR", uv_bin_dir)
        return self._with_prefixed_path(target)

    def which(self, name, env=None):
        name = str(name or "").strip()
        if not name:
            return None
        lower = os.path.basename(name).lower()
        private_map = {
            "python": self.private_python_executable(),
            "python.exe": self.private_python_executable(),
            "pythonw": self.private_python_executable(prefer_console=False),
            "pythonw.exe": self.private_python_executable(prefer_console=False),
            "node": self.private_node_executable(),
            "node.exe": self.private_node_executable(),
            "npm": self.private_npm_executable(),
            "npm.cmd": self.private_npm_executable(),
            "npx": self.private_npx_executable(),
            "npx.cmd": self.private_npx_executable(),
        }
        private = private_map.get(lower)
        if private and os.path.exists(private):
            return private
        search_env = self.subprocess_env(env)
        return shutil.which(name, path=search_env.get("PATH"))


SMARTI_RUNTIME = SmartiRuntime()


__all__ = ["SMARTI_RUNTIME", "SmartiRuntime"]
