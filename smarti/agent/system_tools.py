"""Weather, shell, git, project-check, process, clipboard, OCR, custom Python tool, and MCP execution tools."""
from .shared import *


class SystemToolsMixin:
    def _weather_code_text(self, code):
        try:
            code = int(code)
        except Exception:
            return "לא ידוע"
        mapping = {
            0: "שמיים בהירים",
            1: "בהיר ברובו",
            2: "מעונן חלקית",
            3: "מעונן",
            45: "ערפל",
            48: "ערפל קופא",
            51: "טפטוף קל",
            53: "טפטוף בינוני",
            55: "טפטוף חזק",
            56: "טפטוף קופא קל",
            57: "טפטוף קופא חזק",
            61: "גשם קל",
            63: "גשם בינוני",
            65: "גשם חזק",
            66: "גשם קופא קל",
            67: "גשם קופא חזק",
            71: "שלג קל",
            73: "שלג בינוני",
            75: "שלג חזק",
            77: "גרגרי שלג",
            80: "ממטרים קלים",
            81: "ממטרים בינוניים",
            82: "ממטרים חזקים",
            85: "ממטרי שלג קלים",
            86: "ממטרי שלג חזקים",
            95: "סופת רעמים",
            96: "סופת רעמים עם ברד קל",
            99: "סופת רעמים עם ברד חזק",
        }
        return mapping.get(code, f"קוד מזג אוויר {code}")

    def _get_json_with_curl_fallback(self, url, params=None, headers=None, timeout=20):
        params = params or {}
        headers = headers or {}
        try:
            res = self._run_cancelable_callable(lambda: self._request_get(url, params=params, headers=headers, timeout=timeout))
            res.raise_for_status()
            return res.json()
        except SmartiCancelled:
            raise
        except Exception as first_error:
            prepared = requests.Request("GET", url, params=params, headers=headers).prepare()
            curl_cmd = ["curl.exe", "-L", "-sS", "--max-time", str(int(timeout)), prepared.url]
            if self._allow_insecure_ssl():
                curl_cmd[1:1] = ["-k"]
            user_agent = headers.get("User-Agent") or headers.get("user-agent")
            if user_agent:
                curl_cmd[1:1] = ["-A", user_agent]
            completed = self._run_cancelable_subprocess(curl_cmd, text=True, encoding="utf-8", errors="replace", timeout=timeout + 5, creationflags=WIN_CREATE_NO_WINDOW)
            if completed.returncode != 0:
                raise Exception(f"{first_error}; curl fallback failed: {completed.stderr.strip()}")
            try:
                return json.loads(completed.stdout)
            except Exception as json_error:
                raise Exception(f"{first_error}; curl fallback returned non-JSON: {json_error}")

    def _geocode_weather_location(self, location):
        timeout = self._timeout("network_timeout_seconds", 20)
        try:
            osm = self._get_json_with_curl_fallback(
                "https://nominatim.openstreetmap.org/search",
                params={"q": location, "format": "json", "limit": 1, "accept-language": "he"},
                headers={"User-Agent": "Smarti/1.0"},
                timeout=timeout
            )
            if isinstance(osm, list) and osm:
                item = osm[0]
                return {
                    "latitude": float(item["lat"]),
                    "longitude": float(item["lon"]),
                    "display": item.get("display_name") or item.get("name") or location,
                }
        except Exception as e:
            logging.info(f"Nominatim geocode failed for weather location '{location}': {e}")
        geo_data = self._get_json_with_curl_fallback(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "he", "format": "json"},
            timeout=timeout
        )
        results = geo_data.get("results") or []
        if not results:
            return None
        place = results[0]
        display = ", ".join([str(x) for x in [place.get("name"), place.get("admin1"), place.get("country")] if x])
        return {"latitude": place["latitude"], "longitude": place["longitude"], "display": display or location}

    def get_weather_tool(self, location, days=2, units="metric"):
        location = str(location or "").strip()
        if not location:
            return "ERROR: Missing location."
        try:
            days = max(1, min(7, int(days or 2)))
        except Exception:
            days = 2
        units = str(units or "metric").lower()
        temp_unit = "fahrenheit" if units == "imperial" else "celsius"
        wind_unit = "mph" if units == "imperial" else "kmh"
        try:
            place = self._geocode_weather_location(location)
            if not place:
                return self._weather_wttr_fallback(location, days, units)
            params = {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": days,
                "temperature_unit": temp_unit,
                "wind_speed_unit": wind_unit,
            }
            data = self._get_json_with_curl_fallback(
                "https://api.open-meteo.com/v1/forecast",
                params=params,
                timeout=self._timeout("network_timeout_seconds", 20)
            )
            unit_temp = data.get("current_units", {}).get("temperature_2m", "°C" if units != "imperial" else "°F")
            unit_wind = data.get("current_units", {}).get("wind_speed_10m", "קמ״ש" if units != "imperial" else "mph")
            place_name = place.get("display") or location
            current = data.get("current", {}) or {}
            lines = [
                "WEATHER_FORECAST",
                f"מיקום: {place_name or location}",
                "מקור: Open-Meteo",
            ]
            if current:
                lines.append(
                    f"עכשיו ({current.get('time', '')}): {current.get('temperature_2m')} {unit_temp}, "
                    f"{self._weather_code_text(current.get('weather_code'))}, "
                    f"לחות {current.get('relative_humidity_2m')}%, רוח {current.get('wind_speed_10m')} {unit_wind}"
                )
            daily = data.get("daily", {}) or {}
            dates = daily.get("time", []) or []
            maxs = daily.get("temperature_2m_max", []) or []
            mins = daily.get("temperature_2m_min", []) or []
            codes = daily.get("weather_code", []) or []
            pops = daily.get("precipitation_probability_max", []) or []
            if dates:
                lines.append("תחזית יומית:")
                for idx, day in enumerate(dates[:days]):
                    hi = maxs[idx] if idx < len(maxs) else "?"
                    lo = mins[idx] if idx < len(mins) else "?"
                    code = codes[idx] if idx < len(codes) else None
                    pop = pops[idx] if idx < len(pops) else "?"
                    lines.append(f"- {day}: {self._weather_code_text(code)}, {lo}-{hi} {unit_temp}, סיכוי משקעים {pop}%")
            return "\n".join(lines)
        except Exception as e:
            try:
                return self._weather_wttr_fallback(location, days, units)
            except Exception as e2:
                return f"ERROR: Weather lookup failed: {e}; fallback failed: {e2}"

    def _weather_wttr_fallback(self, location, days=2, units="metric"):
        query = urllib.parse.quote(location.replace(" ", "+"), safe="+")
        suffix = "u" if str(units).lower() == "imperial" else "m"
        url = f"https://wttr.in/{query}?format=j1&{suffix}"
        data = self._get_json_with_curl_fallback(url, timeout=self._timeout("network_timeout_seconds", 20), headers={"User-Agent": "Smarti/1.0"})
        area = (((data.get("nearest_area") or [{}])[0]).get("areaName") or [{}])[0].get("value", location)
        current = (data.get("current_condition") or [{}])[0]
        temp_key = "temp_F" if str(units).lower() == "imperial" else "temp_C"
        wind_key = "windspeedMiles" if str(units).lower() == "imperial" else "windspeedKmph"
        unit_temp = "°F" if str(units).lower() == "imperial" else "°C"
        unit_wind = "mph" if str(units).lower() == "imperial" else "קמ״ש"
        lines = [
            "WEATHER_FORECAST",
            f"מיקום: {area}",
            "מקור: wttr.in",
            f"עכשיו: {current.get(temp_key)} {unit_temp}, {((current.get('weatherDesc') or [{}])[0]).get('value', '')}, לחות {current.get('humidity')}%, רוח {current.get(wind_key)} {unit_wind}",
        ]
        weather_days = data.get("weather") or []
        if weather_days:
            lines.append("תחזית יומית:")
            for item in weather_days[:max(1, min(7, int(days or 2)))]:
                hi = item.get("maxtempF" if str(units).lower() == "imperial" else "maxtempC")
                lo = item.get("mintempF" if str(units).lower() == "imperial" else "mintempC")
                hourly = item.get("hourly") or [{}]
                desc = ((hourly[len(hourly)//2].get("weatherDesc") or [{}])[0]).get("value", "")
                pop = hourly[len(hourly)//2].get("chanceofrain", "?")
                lines.append(f"- {item.get('date')}: {desc}, {lo}-{hi} {unit_temp}, סיכוי גשם {pop}%")
        return "\n".join(lines)

    def _skill_requirement_install_target(self, cmd):
        lower_cmd = str(cmd or "").lower()
        if not re.search(r'\b(uv\s+tool\s+install|pipx?\s+install|python(?:\.exe)?\s+-m\s+pip\s+install)\b', lower_cmd):
            return ""
        registry = getattr(self, "skill_registry", None) or self._load_skill_registry()
        for name, spec in (registry or {}).items():
            for entry in self._skill_install_entries(spec):
                package = str(entry.get("package") or "").strip().lower()
                if package and re.search(rf'(?<![A-Za-z0-9_.@/+~-]){re.escape(package)}(?![A-Za-z0-9_.@/+~-])', lower_cmd):
                    return name
        return ""

    def _parse_simple_command(self, cmd):
        try:
            return shlex.split(cmd, posix=False)
        except Exception:
            return []

    def _is_detached_gui_command(self, cmd):
        if not cmd:
            return False
        compact = cmd.strip()
        if re.search(r'[|;&<>`]', compact):
            return False
        tokens = self._parse_simple_command(compact)
        if not tokens:
            return False
        exe = os.path.basename(tokens[0].strip("\"'")).lower()
        gui_names = {
            "notepad", "notepad.exe", "calc", "calc.exe", "mspaint", "mspaint.exe",
            "write", "write.exe", "wordpad", "wordpad.exe", "snippingtool", "snippingtool.exe"
        }
        return exe in gui_names

    def _run_detached_gui_command(self, cmd):
        tokens = self._parse_simple_command(cmd)
        if not tokens:
            return "ERROR: Empty GUI command."
        exe = tokens[0].strip("\"'")
        args = [t.strip("\"'") for t in tokens[1:]]
        subprocess.Popen([exe] + args, env=self._subprocess_env(), creationflags=WIN_CREATE_NO_WINDOW)
        return f"SUCCESS: הופעל יישום GUI בלי להמתין לסגירתו: {exe}"

    def run_system_command(self, params, cwd=None, timeout_seconds=None):
        cmd = str(params[0]).strip() if params else ""
        if not cmd: return "ERROR: Empty command."
        working_dir = None
        if cwd:
            working_dir = self._abs_path(cwd)
            if not os.path.isdir(working_dir):
                return f"ERROR: Working directory not found: {working_dir}"
            sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(working_dir, "read")
            if not sandbox_ok:
                return sandbox_err
        if self._is_detached_gui_command(cmd):
            try:
                return self._run_detached_gui_command(cmd)
            except Exception as e:
                return f"ERROR: Failed to launch GUI app: {e}"
        if re.match(r'(?i)^\s*curl\s+', cmd):
            cmd = re.sub(r'(?i)^\s*curl\s+', 'curl.exe ', cmd, count=1)
        if self._allow_insecure_ssl() and re.match(r'(?i)^\s*curl(?:\.exe)?\s+', cmd) and not re.search(r'(?i)(^|\s)(-k|--insecure)(\s|$)', cmd):
            cmd = re.sub(r'(?i)^\s*curl(?:\.exe)?\s+', 'curl.exe -k ', cmd, count=1)
        try:
            timeout = max(5, int(timeout_seconds)) if timeout_seconds not in (None, "") else self._timeout("command_timeout_seconds", 60)
        except Exception:
            timeout = self._timeout("command_timeout_seconds", 60)
        try:
            ps_prefix = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); $OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            if self._allow_insecure_ssl():
                ps_prefix += "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }; "
            ps_cmd = ps_prefix + cmd
            completed = self._run_cancelable_subprocess(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], cwd=working_dir, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=WIN_CREATE_NO_WINDOW)
            output, err = (completed.stdout or "").strip(), (completed.stderr or "").strip()
            body = [f"EXIT_CODE: {completed.returncode}"]
            if working_dir: body.append(f"CWD: {working_dir}")
            if output: body.append("STDOUT:\n" + output)
            if err: body.append("STDERR:\n" + err)
            result = "\n\n".join(body)
            if completed.returncode != 0:
                return self._truncate_tool_output("ERROR: System command failed.\n" + result)
            return self._truncate_tool_output(result)
        except subprocess.TimeoutExpired: return f"ERROR: Timeout after {timeout}s."
        except SmartiCancelled:
            raise
        except Exception as e: return f"ERROR: {e}"

    def git_status_tool(self, path, operation="status", ref=""):
        root = self._abs_path(path)
        sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(root, "read")
        if not sandbox_ok: return sandbox_err
        if not os.path.isdir(root): return f"ERROR: Not a folder: {root}"
        op = str(operation or "status").lower()
        if op not in {"status", "diff", "log", "show"}:
            return "ERROR: Unsupported git operation."
        args = ["git", "-C", root]
        if op == "status":
            args += ["status", "--short", "--branch"]
        elif op == "diff":
            args += ["diff", "--", "."]
        elif op == "log":
            args += ["log", "--oneline", "--decorate", "-20"]
            if ref:
                args.append(str(ref))
        elif op == "show":
            args += ["show", "--stat", "--oneline", str(ref or "HEAD")]
        try:
            completed = self._run_cancelable_subprocess(args, text=True, encoding="utf-8", errors="replace", timeout=self._timeout("command_timeout_seconds", 60), creationflags=WIN_CREATE_NO_WINDOW)
            body = f"EXIT_CODE: {completed.returncode}\nSTDOUT:\n{(completed.stdout or '').strip()}\nSTDERR:\n{(completed.stderr or '').strip()}"
            return self._truncate_tool_output(("ERROR: Git command failed.\n" if completed.returncode else "") + body)
        except Exception as e:
            return f"ERROR: {e}"

    def run_project_check_tool(self, path, command):
        root = self._abs_path(path)
        sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(root, "read")
        if not sandbox_ok: return sandbox_err
        if not os.path.isdir(root): return f"ERROR: Not a folder: {root}"
        cmd = str(command or "").strip()
        if not self._project_check_command_allowed(cmd):
            return "ERROR: run_project_check מאפשר רק פקודות בדיקה/build מוכרות. השתמש ב-system_command עם אישור מפורש לפקודה אחרת."
        return self.run_system_command([cmd], cwd=root)

    def list_processes_tool(self):
        try:
            completed = self._run_cancelable_subprocess(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Process | Sort-Object CPU -Descending | Select-Object -First 80 ProcessName,Id,CPU,WorkingSet | Format-Table -AutoSize"],
                text=True, encoding="utf-8", errors="replace",
                timeout=self._timeout("command_timeout_seconds", 60), creationflags=WIN_CREATE_NO_WINDOW
            )
            return self._truncate_tool_output((completed.stdout or completed.stderr or "").strip())
        except Exception as e:
            return f"ERROR: {e}"

    def set_clipboard_tool(self, text):
        try:
            completed = self._run_cancelable_subprocess(["clip.exe"], input=str(text), text=True, encoding="utf-16le", errors="replace", timeout=10, creationflags=WIN_CREATE_NO_WINDOW)
            if completed.returncode != 0:
                return f"ERROR: Clipboard failed: {(completed.stderr or '').strip()}"
            return "SUCCESS: הטקסט הועתק ללוח הגזירים."
        except SmartiCancelled:
            raise
        except Exception as e:
            return f"ERROR: {e}"

    def extract_image_text_tool(self, path):
        path = str(path or "").strip(' "\'')
        if not os.path.exists(path): return f"ERROR: Not found: {path}"
        sandbox_ok, sandbox_err = self._ensure_sandbox_path_allowed(path, "read")
        if not sandbox_ok: return sandbox_err
        try:
            import pytesseract
            from PIL import Image
        except Exception:
            return "ERROR: OCR requires pytesseract and Pillow installed, plus the Tesseract engine in PATH."
        try:
            text = pytesseract.image_to_string(Image.open(path), lang="heb+eng")
            return "[UNTRUSTED_OCR_TEXT]\n" + self._truncate_tool_output(text.strip()[:15000])
        except Exception as e:
            return f"ERROR: {e}"

    def manage_python_tools(self, params):
        sub_action, name, _confirm, explanation, data = params
        tool_name = safe_filename(name)
        tool_path = os.path.join(TOOLS_DIR, f"{tool_name}.pyw")
        doc_path = os.path.join(TOOLS_DIR, f"{tool_name}.txt")

        if sub_action in {"save", "שמירה"}:
            code = strip_code_fences(data)
            if not code.strip(): return "ERROR: Empty code."
            try:
                schema_obj = json.loads(str(explanation).strip())
                if not isinstance(schema_obj, dict) or schema_obj.get("type") != "object":
                    return "ERROR: Tool description must be a valid JSON Schema object with type='object'."
            except Exception as e:
                return f"ERROR: Tool description must be valid JSON Schema. {e}"
            needs_confirm = normalize_bool_text(_confirm) or (self.settings.get("permission_level", 1) == 1) or (self.settings.get("permission_level", 1) == 2 and any(m in code.lower() for m in ["os.remove", "shutil.rmtree", "os.rmdir", "format ", "del "]))
            if needs_confirm and not self._request_user_approval("אישור שמירת כלי מסוכן", f"הכלי '{tool_name}' מכיל פעולות מסוכנות.\n\nהסבר: {explanation}", risk="high"): return "ERROR: Denied."
            try:
                os.makedirs(TOOLS_DIR, exist_ok=True)
                with open(tool_path, "w", encoding="utf-8") as f: f.write(code)
                with open(doc_path, "w", encoding="utf-8") as f: f.write(str(explanation).strip())
                self.settings.setdefault("tools_config", {})[tool_name] = True
                if getattr(self, "tool_registry", None):
                    self.tool_registry.ensure_custom_tool_manifest(tool_name)
                    self.tool_registry.set_trust("custom", tool_name, True, metadata={
                        "kind": "custom_python",
                        "risk": "high" if needs_confirm else "medium",
                        "hash": file_sha256(tool_path),
                        "schema_file": os.path.basename(doc_path),
                        "trusted_reason": "created_by_smarti_after_policy"
                    })
                self._save_settings()
                return f"SUCCESS: כלי פייתון נשמר והוא מוכן לשימוש ישיר: {tool_path}"
            except Exception as e: return f"ERROR: {e}"

        if sub_action in {"run", "הרצה"}:
            if not os.path.exists(tool_path): return f"ERROR: Not found: {tool_name}"
            if (self.settings.get("permission_level", 1) == 1 or normalize_bool_text(_confirm)) and not self._request_user_approval("אישור הרצת כלי", f"להריץ '{tool_name}'?", risk="medium"): return "ERROR: Denied."
            args = []
            try:
                payload = json.loads(str(data or "{}").strip())
                if isinstance(payload, dict): args = [json.dumps(payload, ensure_ascii=False)]
                elif isinstance(payload, list): args = [str(x) for x in payload]
                else: args = [str(payload)]
            except: args = [str(data)]
            timeout = self._timeout("tool_timeout_seconds", 120)
            try:
                completed = self._run_cancelable_subprocess([self._python_executable(), tool_path] + args, cwd=APP_DIR, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=WIN_CREATE_NO_WINDOW)
                return self._truncate_tool_output(f"EXIT_CODE: {completed.returncode}\nSTDOUT:\n{(completed.stdout or '').strip()}\nSTDERR:\n{(completed.stderr or '').strip()}")
            except subprocess.TimeoutExpired: return f"ERROR: Timeout after {timeout}s."
            except SmartiCancelled:
                raise
            except Exception as e: return f"ERROR: {e}"

    def _write_mcp_wrapper(self, pkg_name):
        os.makedirs(MCP_TOOLS_DIR, exist_ok=True)
        stem = mcp_pkg_to_file_stem(pkg_name)
        wrapper_path = os.path.join(MCP_TOOLS_DIR, f"{stem}.pyw")
        wrapper_code = r'''import sys, json, subprocess, shutil, os, io

# --- תיקון קריטי: הכרחת פייתון לכתוב ל-STDOUT בקידוד UTF-8 כדי למנוע קריסות cp1255 בווינדוס בעברית ---
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
# ----------------------------------------------------------------------------------------------------

WIN_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def get_npx():
    explicit = os.environ.get("SMARTI_NPX_EXE", "").strip()
    if explicit and os.path.exists(explicit):
        return explicit
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    return npx

def main():
    if len(sys.argv) < 3:
        print("MCP_ERROR: Missing arguments.")
        return 1
    pkg = sys.argv[1]
    cmd = sys.argv[2]
    npx_path = get_npx()
    if not npx_path:
        print("MCP_ERROR: Node.js (npx) is not installed.")
        return 1

    env = os.environ.copy()
    if env.get("SMARTI_ALLOW_INSECURE_SSL") == "1":
        env["PYTHONHTTPSVERIFY"] = "0"
        env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0"
        env["npm_config_strict_ssl"] = "false"
        env["GIT_SSL_NO_VERIFY"] = "true"
        env["CURL_SSL_NO_REVOKE"] = "1"
        env["YARN_ENABLE_STRICT_SSL"] = "false"
        env["PNPM_CONFIG_STRICT_SSL"] = "false"
        env["PIP_TRUSTED_HOST"] = "pypi.org files.pythonhosted.org pypi.python.org"
        env["UV_SYSTEM_CERTS"] = "true"
        env["UV_NATIVE_TLS"] = "true"
    else:
        env.pop("PYTHONHTTPSVERIFY", None)
        env.pop("NODE_TLS_REJECT_UNAUTHORIZED", None)
        env.pop("npm_config_strict_ssl", None)
        env.pop("GIT_SSL_NO_VERIFY", None)
        env.pop("CURL_SSL_NO_REVOKE", None)
        env.pop("YARN_ENABLE_STRICT_SSL", None)
        env.pop("PNPM_CONFIG_STRICT_SSL", None)
        env.pop("PIP_TRUSTED_HOST", None)
        env.pop("UV_SYSTEM_CERTS", None)
        env.pop("UV_NATIVE_TLS", None)

    try:
        server_args = json.loads(env.get("MCP_SERVER_ARGS", "[]"))
        if not isinstance(server_args, list):
            server_args = []
    except Exception:
        server_args = []

    proc = subprocess.Popen(
        [npx_path, "-y", pkg] + [str(x) for x in server_args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", env=env,
        creationflags=WIN_CREATE_NO_WINDOW
    )

    req_id = 1
    def send(method, params=None):
        nonlocal req_id
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        req_id += 1

    def notif(method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    try:
        send("initialize", {"protocolVersion": os.environ.get("MCP_PROTOCOL_VERSION", "2025-11-25"), "capabilities": {}, "clientInfo": {"name": "smarti_client", "version": "1.1"}})
        init_done = False
        result = None
        error_msg = None

        while True:
            if proc.poll() is not None:
                error_msg = proc.stderr.read()
                break
            line = proc.stdout.readline()
            if not line:
                error_msg = proc.stderr.read()
                break
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in resp:
                error_msg = str(resp["error"])
                break
            if "id" in resp and "result" in resp:
                if not init_done:
                    notif("notifications/initialized")
                    init_done = True
                    if cmd == "list":
                        send("tools/list")
                    elif cmd == "call":
                        if len(sys.argv) < 4:
                            error_msg = "Missing tool name."
                            break
                        raw_args = env.get("MCP_ARGS", "{}")
                        try:
                            parsed_args = json.loads(raw_args)
                        except Exception as e:
                            print(f"JSON_PARSE_ERROR: ה-JSON שנשלח אינו חוקי: {raw_args}. שגיאה: {e}")
                            return 1
                        send("tools/call", {"name": sys.argv[3], "arguments": parsed_args})
                    else:
                        error_msg = "Unknown MCP wrapper command."
                        break
                else:
                    result = resp["result"]
                    if isinstance(result, dict) and result.get("isError", False):
                        error_msg = "הכלי החזיר שגיאה פנימית: " + str(result)
                    break

        if result and not error_msg:
            if cmd == "list":
                tools = result.get("tools", [])
                
                # יצירת רשימה נקייה של סכמות JSON (הסטנדרט המדויק)
                mcp_tools_list = []
                for t in tools:
                    schema_obj = {
                        "name": t.get('name', ''),
                        "description": t.get('description', 'אין תיאור'),
                        "inputSchema": t.get("inputSchema", {})
                    }
                    mcp_tools_list.append(schema_obj)
                    
                print(json.dumps(mcp_tools_list, ensure_ascii=False, indent=2))
            elif cmd == "call":
                for c in result.get("content", []):
                    if isinstance(c, dict):
                        print(c.get("text", json.dumps(c, ensure_ascii=False)))
        else:
            print(f"MCP_ERROR: {error_msg}")
            return 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
'''
        with open(wrapper_path, "w", encoding="utf-8") as f:
            f.write(wrapper_code)
        return wrapper_path

    def _resolve_mcp_package(self, requested):
        requested = str(requested or "").strip()
        aliases = self.settings.setdefault("mcp_package_aliases", {})
        if requested in aliases:
            return aliases[requested]
        requested_stem = mcp_pkg_to_file_stem(requested)
        if requested_stem in aliases:
            return aliases[requested_stem]
        for installed in self.settings.get("allowed_mcp_packages", []):
            installed = str(installed or "").strip()
            base_pkg, _, _ = parse_npm_package_spec(installed)
            installed_keys = {
                installed,
                mcp_pkg_to_file_stem(installed),
                base_pkg or "",
                mcp_pkg_to_file_stem(base_pkg or "")
            }
            if requested in installed_keys or requested_stem in installed_keys:
                return installed
        if "/" in requested or requested.startswith("@"): return requested
        stem = mcp_pkg_to_file_stem(requested)
        candidates = [os.path.join(MCP_TOOLS_DIR, f"{requested}.txt"), os.path.join(MCP_TOOLS_DIR, f"{stem}.txt")]
        for path in candidates:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: first = f.readline()
                    match = re.search(r'ממאגר NPM\):\s*(.+?)\s*---', first)
                    if match: return match.group(1).strip()
                except: pass
        return requested

    def _remember_mcp_package_aliases(self, pkg_name):
        pkg_name = str(pkg_name or "").strip()
        if not pkg_name:
            return
        aliases = self.settings.setdefault("mcp_package_aliases", {})
        base_pkg, _, _ = parse_npm_package_spec(pkg_name)
        keys = {pkg_name, mcp_pkg_to_file_stem(pkg_name)}
        if base_pkg:
            keys.update({base_pkg, mcp_pkg_to_file_stem(base_pkg)})
        for key in keys:
            if key:
                aliases[key] = pkg_name

    def _mcp_doc_paths(self, pkg_name):
        resolved = self._resolve_mcp_package(pkg_name)
        stems = {mcp_pkg_to_file_stem(pkg_name), mcp_pkg_to_file_stem(resolved), str(pkg_name).strip(), str(resolved).strip()}
        return [os.path.join(MCP_TOOLS_DIR, f"{safe_filename(stem)}.txt") for stem in stems if stem]

    def _is_mcp_installed_locally(self, pkg_name):
        return any(os.path.exists(path) for path in self._mcp_doc_paths(pkg_name))

    def _run_mcp_wrapper(self, pkg_name, cmd, tool_name=None, json_args="{}"):
        pkg_name = self._resolve_mcp_package(pkg_name)
        wrapper_path = self._write_mcp_wrapper(pkg_name)
        env = self._mcp_env()
        env["SMARTI_ALLOW_INSECURE_SSL"] = "1" if self._allow_insecure_ssl() else "0"
        env["MCP_SERVER_ARGS"] = json.dumps(self._mcp_launch_args(pkg_name), ensure_ascii=False)
        env["MCP_PROTOCOL_VERSION"] = str(self.settings.get("mcp_protocol_version", "2025-11-25") or "2025-11-25")
        env["MCP_ARGS"] = json_args or "{}"
        args = [self._python_executable(), wrapper_path, pkg_name, cmd]
        if tool_name: args.append(tool_name)
        timeout = self._timeout("mcp_timeout_seconds", 60)
        try:
            completed = self._run_cancelable_subprocess(args, cwd=APP_DIR, env=env, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=WIN_CREATE_NO_WINDOW)
            if completed.returncode != 0: return self._truncate_tool_output(f"ERROR: MCP failed.\n{(completed.stdout or '').strip()}\n{(completed.stderr or '').strip()}".strip())
            return self._truncate_tool_output((completed.stdout or "").strip() or "SUCCESS: MCP completed.")
        except subprocess.TimeoutExpired: return f"ERROR: Timeout after {timeout}s."
        except SmartiCancelled:
            raise
        except Exception as e: return f"ERROR: MCP crashed: {e}"

    def search_mcp(self, query):
        query = str(query or "").strip()
        if not query: return "ERROR: Missing query."
        try:
            res = self._run_cancelable_callable(lambda: self._request_get(get_url(URL_NPM) + urllib.parse.quote(f"mcp {query}"), timeout=20))
            res.raise_for_status()
            packages = res.json().get("objects", [])[:8]
            if not packages: return f"לא נמצאו חבילות MCP עבור: {query}"
            lines = ["תוצאות MCP מ-NPM (בחר חבילה אמינה ואז התקן עם `install_mcp`):"]
            for item in packages:
                pkg = item.get("package", {})
                score = item.get("score", {}).get("final", 0)
                publisher = ((pkg.get("publisher") or {}).get("username") or (pkg.get("publisher") or {}).get("email") or "לא ידוע")
                links = pkg.get("links") or {}
                npm_link = links.get("npm", "")
                trust_hint = "גבוה יחסית" if score >= 0.75 else ("בינוני" if score >= 0.45 else "נמוך")
                lines.append(f"- {pkg.get('name', '')}@{pkg.get('version', '')} | אמון: {trust_hint} | ציון {score:.2f} | מפרסם: {publisher} | {npm_link} | {(pkg.get('description') or '').replace(chr(10), ' ')[:220]}")
            return "\n".join(lines)
        except Exception as e: return f"ERROR: {e}"

    def install_mcp(self, pkg_name):
        pkg_name = str(pkg_name or "").strip()
        base_pkg, version, pinned = parse_npm_package_spec(pkg_name)
        if not base_pkg: return "ERROR: Invalid package name."
        if self.settings.get("mcp_require_pinned_versions", True) and not pinned:
            return "ERROR: התקנת MCP דורשת גרסה נעולה, למשל package@1.2.3. חפש את הגרסה דרך search_mcp ואז נסה שוב."
        allowed = self.settings.setdefault("allowed_mcp_packages", [])
        
        guide = self._run_mcp_wrapper(pkg_name, "list")
        stem = mcp_pkg_to_file_stem(pkg_name)
        
        if guide.startswith("ERROR:"):
            # --- מנגנון ניקוי חכם ---
            orphaned_pyw = os.path.join(MCP_TOOLS_DIR, f"{stem}.pyw")
            try:
                if os.path.exists(orphaned_pyw): os.remove(orphaned_pyw)
            except: pass
            return guide
            
        try:
            with open(os.path.join(MCP_TOOLS_DIR, f"{stem}.txt"), "w", encoding="utf-8") as f: f.write(guide)
            self._remember_mcp_package_aliases(pkg_name)
            self.settings.setdefault("mcp_registry", {})[stem] = {
                "name": pkg_name,
                "base_package": base_pkg,
                "version": version or "",
                "trust": "trusted",
                "source": "npm",
                "protocol_version": str(self.settings.get("mcp_protocol_version", "2025-11-25") or "2025-11-25"),
                "installed_at": datetime.now().isoformat(timespec="seconds"),
                "schema_hash": hashlib.sha256(guide.encode("utf-8", "replace")).hexdigest()
            }
            if getattr(self, "tool_registry", None):
                self.tool_registry.set_trust("mcp", stem, True, metadata=self.settings["mcp_registry"][stem])
            if pkg_name not in allowed:
                allowed.append(pkg_name)
                self.refresh_extension_catalogs(force=True)
                self._save_settings()
            else:
                self.refresh_extension_catalogs(force=True)
                self._save_settings()
            return f"SUCCESS: MCP הותקן.\n\n{guide[:2500]}"
        except SmartiCancelled:
            raise
        except Exception as e: return f"ERROR: {e}"

    def run_mcp(self, params):
        pkg_name, tool_name, json_args = params
        resolved_pkg = self._resolve_mcp_package(pkg_name)
        allowed = self.settings.setdefault("allowed_mcp_packages", [])
        trusted = bool(getattr(self, "mcp_manager", None) and self.mcp_manager.is_trusted(resolved_pkg))
        installed = self._is_mcp_installed_locally(resolved_pkg) or self._is_mcp_installed_locally(pkg_name)
        if self.settings.get("external_code_requires_trust", True) and not trusted:
            return "ERROR: MCP package is installed but not trusted yet. אשר את חבילת ה-MCP במסך הכלים לפני הרצה."
        if resolved_pkg not in allowed and pkg_name not in allowed:
            if trusted and installed:
                if self._sync_trusted_mcp_packages():
                    self._save_settings()
                    self._ensure_mcp_config()
            else:
                return "ERROR: MCP package is not trusted/installed in Smarti policy."
        return self._run_mcp_wrapper(resolved_pkg, "call", tool_name, json_args)
