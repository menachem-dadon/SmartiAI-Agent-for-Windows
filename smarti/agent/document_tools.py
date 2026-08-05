"""Structured Word/DOCX creation, editing, export, and visual-render tools."""
from .shared import *


_WORD_FORMATS = {
    "doc": 0,
    "dot": 1,
    "txt": 2,
    "rtf": 6,
    "html": 10,
    "htm": 10,
    "mhtml": 9,
    "docx": 16,
    "docm": 13,
    "dotx": 14,
    "dotm": 15,
    "odt": 23,
}
_WORD_FIXED_FORMATS = {"pdf": 17, "xps": 18}
_WORD_BUILTIN_STYLES = {
    "normal": -1,
    "heading1": -2, "heading2": -3, "heading3": -4,
    "heading4": -5, "heading5": -6, "heading6": -7,
    "heading7": -8, "heading8": -9, "heading9": -10,
    "title": -63, "subtitle": -75, "quote": -181,
    "intensequote": -182, "listparagraph": -180,
}
_PYTHON_BLOCK_TYPES = {
    "paragraph", "heading", "title", "subtitle", "quote", "callout",
    "list", "table", "image", "page_break", "section_break", "toc", "field",
    "hyperlink", "bookmark", "header", "footer", "content_control",
}
_COM_ONLY_BLOCK_TYPES = {
    "comment", "footnote", "endnote", "text_box", "shape", "chart",
    "equation", "advanced_com",
}
_COM_ONLY_OPERATIONS = {
    "add_comment", "add_footnote", "add_endnote", "add_text_box",
    "add_shape", "add_chart", "add_equation", "track_changes",
    "accept_all_changes", "reject_all_changes", "protect", "unprotect",
    "advanced_com", "insert_file",
}
_ADVANCED_COM_BLOCKED = {
    "vbproject", "vbe", "macro", "macros", "run", "ddeexecute",
    "ddeinitiate", "dderequest", "oleobjects", "addoleobject", "addolecontrol",
    "commandbars", "addins", "comaddins", "followhyperlink", "sendmail",
    "route", "routingslip", "printout", "printpreview", "saveas", "saveas2",
    "exportasfixedformat", "exportasfixedformat2", "open", "opentext",
    "openold", "attachedtemplate", "linkformat", "executeexcel4macro",
    "save", "close", "quit", "wordbasic", "system", "tasks", "filedialog",
    "organizercopy", "organizerdelete", "sendforreview", "sendfaxoverinternet",
    "reply", "replyall", "forward",
}


def _json_text(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _clamp(value, minimum, maximum, default):
    try:
        return max(minimum, min(maximum, float(value)))
    except Exception:
        return default


def _safe_color(value, default="000000"):
    text = str(value or default).strip().lstrip("#")
    return text.upper() if re.fullmatch(r"[0-9a-fA-F]{6}", text) else default


def _safe_com_result(value, depth=0):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if depth >= 2:
        return str(value)[:500]
    if isinstance(value, (list, tuple)):
        return [_safe_com_result(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {
            str(key)[:100]: _safe_com_result(item, depth + 1)
            for key, item in list(value.items())[:100]
        }
    for attr in ("Name", "Title", "Text", "Count"):
        try:
            item = getattr(value, attr)
            if not callable(item):
                return {"type": type(value).__name__, attr.lower(): str(item)[:1000]}
        except Exception:
            pass
    return {"type": type(value).__name__, "value": str(value)[:1000]}


class _WordComSession:
    """Owns one isolated WINWORD instance and only ever kills that instance."""

    def __init__(self, timeout_seconds=180, visible=False):
        self.timeout_seconds = int(_clamp(timeout_seconds, 15, 1800, 180))
        self.visible = bool(visible)
        self.pythoncom = None
        self.app = None
        self.document = None
        self.pid = None
        self.timer = None
        self.timed_out = False

    def __enter__(self):
        try:
            import pythoncom
            import win32com.client
        except Exception as exc:
            raise RuntimeError("Word COM requires pywin32 on Windows.") from exc
        self.pythoncom = pythoncom
        pythoncom.CoInitialize()
        try:
            self.app = win32com.client.DispatchEx("Word.Application")
            self.app.Visible = self.visible
            self.app.DisplayAlerts = 0
            # msoAutomationSecurityForceDisable. Never execute document macros.
            self.app.AutomationSecurity = 3
            try:
                self.app.Options.ConfirmConversions = False
                self.app.Options.SaveInterval = 0
            except Exception:
                pass
            try:
                import win32process
                _thread_id, self.pid = win32process.GetWindowThreadProcessId(int(self.app.Hwnd))
            except Exception:
                self.pid = None
            self.timer = threading.Timer(self.timeout_seconds, self._on_timeout)
            self.timer.daemon = True
            self.timer.start()
            return self
        except Exception:
            pythoncom.CoUninitialize()
            raise

    def _on_timeout(self):
        self.timed_out = True
        if not self.pid:
            return
        try:
            import win32api
            import win32con
            handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, int(self.pid))
            try:
                win32api.TerminateProcess(handle, 1)
            finally:
                handle.Close()
        except Exception:
            logging.exception("Could not terminate Smarti-owned WINWORD after timeout.")

    def new_document(self, template_path=""):
        kwargs = {"NewTemplate": False, "DocumentType": 0, "Visible": self.visible}
        if template_path:
            kwargs["Template"] = template_path
        self.document = self.app.Documents.Add(**kwargs)
        return self.document

    def open_document(self, path, read_only=False, password=""):
        kwargs = {
            "FileName": path,
            "ConfirmConversions": False,
            "ReadOnly": bool(read_only),
            "AddToRecentFiles": False,
            "Visible": self.visible,
            "OpenAndRepair": True,
            "NoEncodingDialog": True,
        }
        if password:
            kwargs["PasswordDocument"] = password
        self.document = self.app.Documents.Open(**kwargs)
        return self.document

    def close_document(self, save_changes=False):
        if self.document is None:
            return
        try:
            self.document.Close(SaveChanges=-1 if save_changes else 0)
        except Exception:
            pass
        self.document = None

    def __exit__(self, exc_type, exc, tb):
        if self.timer:
            self.timer.cancel()
        self.close_document(False)
        if self.app is not None:
            try:
                self.app.Quit(SaveChanges=0)
            except Exception:
                pass
        self.app = None
        if self.pythoncom is not None:
            try:
                self.pythoncom.CoUninitialize()
            except Exception:
                pass
        if self.timed_out and exc_type is None:
            raise TimeoutError(f"Microsoft Word exceeded the {self.timeout_seconds}-second timeout.")
        return False


class DocumentToolsMixin:
    """Safe, structured document automation with COM and python-docx engines."""

    def document_manager_tool(self, args):
        args = args if isinstance(args, dict) else {}
        action = str(args.get("action") or "").strip().lower()
        if action not in {"doctor", "create", "edit", "inspect", "render", "export", "compare"}:
            return "ERROR: document_manager action must be doctor, create, edit, inspect, render, export, or compare."
        try:
            if action == "doctor":
                return _json_text(self._document_doctor())

            engine = self._document_choose_engine(action, args)
            capabilities = ["file_read"] if action in {"inspect", "render", "export", "compare", "edit"} else []
            if action in {"create", "edit", "render", "export", "compare"}:
                capabilities.append("file_write")
            if engine in {"com", "libreoffice"} or action == "compare":
                capabilities.append("office_automation")
            if action in {"create", "edit"} and (args.get("render_after") or args.get("export_formats")):
                post_engine = self._document_choose_engine(
                    "export",
                    {"path": args.get("output_path") or args.get("path"), "format": "pdf", "engine": "auto"},
                )
                if post_engine in {"com", "libreoffice"}:
                    capabilities.append("office_automation")
            advanced = self._document_has_advanced_com(args)
            risk = "high" if advanced or action == "compare" else "medium"
            details = self._document_permission_details(action, args, engine)
            allowed, error = self._ensure_capabilities_allowed(
                capabilities,
                "אישור עבודה עם מסמך Word",
                details,
                risk=risk,
                audit_context={"tool": "document_manager", "action": action, "engine": engine},
            )
            if not allowed:
                return error

            if action == "create":
                return _json_text(self._document_create(args, engine))
            if action == "edit":
                return _json_text(self._document_edit(args, engine))
            if action == "inspect":
                return _json_text(self._document_inspect(args, engine))
            if action == "render":
                return _json_text(self._document_render(args, engine))
            if action == "export":
                return _json_text(self._document_export(args, engine))
            return _json_text(self._document_compare(args))
        except Exception as exc:
            logging.exception("document_manager failed")
            return f"ERROR: document_manager {action} failed: {exc}"

    def _document_permission_details(self, action, args, engine):
        paths = [
            args.get("path"), args.get("output_path"), args.get("template_path"),
            args.get("other_path"), args.get("output_dir"),
        ]
        visible_paths = "\n".join(str(item) for item in paths if item)
        return f"פעולה: {action}\nמנוע: {engine}\n{visible_paths}".strip()

    def _document_doctor(self):
        word = self._word_com_available()
        libreoffice = self._find_soffice()
        try:
            import docx
            python_docx = getattr(docx, "__version__", "installed")
        except Exception:
            python_docx = None
        try:
            import fitz
            pymupdf = getattr(fitz, "VersionBind", "installed")
        except Exception:
            pymupdf = None
        return {
            "status": "ok",
            "platform": platform.system(),
            "word_com": word,
            "python_docx": python_docx,
            "libreoffice": libreoffice,
            "pymupdf": pymupdf,
            "default_language": "he-IL",
            "default_direction": "rtl",
            "ui_automation": False,
            "security": {
                "macros": "force-disabled",
                "vba_ole_and_external_links": "blocked",
                "existing_document_backup": "enabled-by-default",
            },
        }

    @staticmethod
    def _word_com_available():
        if platform.system() != "Windows":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID") as key:
                value, _kind = winreg.QueryValueEx(key, None)
            return bool(str(value).strip())
        except Exception:
            return False

    @staticmethod
    def _find_soffice():
        candidates = [
            shutil.which("soffice"),
            shutil.which("libreoffice"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "LibreOffice", "program", "soffice.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "LibreOffice", "program", "soffice.exe"),
        ]
        return next((os.path.abspath(item) for item in candidates if item and os.path.isfile(item)), None)

    def _document_choose_engine(self, action, args):
        requested = str(args.get("engine") or "auto").strip().lower()
        if requested not in {"auto", "com", "python", "libreoffice"}:
            raise ValueError("engine must be auto, com, python, or libreoffice.")
        if requested != "auto":
            if requested == "com" and not self._word_com_available():
                raise RuntimeError("Microsoft Word COM is unavailable. Install/licence Microsoft Word or use engine='python'.")
            if requested == "libreoffice" and not self._find_soffice():
                raise RuntimeError("LibreOffice/soffice is unavailable.")
            return requested
        if action == "compare":
            if not self._word_com_available():
                raise RuntimeError("Document comparison currently requires Microsoft Word COM.")
            return "com"
        source_ext = os.path.splitext(str(args.get("path") or ""))[1].lower()
        output_ext = os.path.splitext(str(args.get("output_path") or ""))[1].lower()
        template_ext = os.path.splitext(str(args.get("template_path") or ""))[1].lower()
        if action in {"inspect", "render"} and source_ext == ".pdf":
            return "python"
        if action == "inspect" and source_ext not in {"", ".docx"}:
            if not self._word_com_available():
                raise RuntimeError("Inspecting legacy/template Word formats requires Microsoft Word COM.")
            return "com"
        if action == "edit" and (source_ext not in {"", ".docx"} or output_ext not in {"", ".docx"}):
            if not self._word_com_available():
                raise RuntimeError("Editing legacy/template Word formats requires Microsoft Word COM.")
            return "com"
        if action == "create" and (output_ext not in {"", ".docx"} or template_ext not in {"", ".docx"}):
            if not self._word_com_available():
                raise RuntimeError("Creating legacy/template Word formats requires Microsoft Word COM.")
            return "com"
        if action in {"render", "export"}:
            fmt = str(args.get("format") or "pdf").lower().lstrip(".")
            if fmt in {"pdf", "xps", "rtf", "html", "htm", "odt", "doc"} and self._word_com_available():
                return "com"
            if self._find_soffice():
                return "libreoffice"
        if self._document_needs_com(args):
            if not self._word_com_available():
                raise RuntimeError("The requested Word feature requires Microsoft Word COM, but Word is unavailable.")
            return "com"
        return "python"

    @staticmethod
    def _document_needs_com(args):
        plan = args.get("document") if isinstance(args.get("document"), dict) else {}
        blocks = plan.get("blocks") or plan.get("sections") or []
        for block in blocks if isinstance(blocks, list) else []:
            if isinstance(block, dict) and str(block.get("type") or "paragraph").lower() in _COM_ONLY_BLOCK_TYPES:
                return True
        for operation in args.get("operations") or []:
            if isinstance(operation, dict) and str(operation.get("op") or operation.get("type") or "").lower() in _COM_ONLY_OPERATIONS:
                return True
        return False

    @staticmethod
    def _document_has_advanced_com(args):
        for operation in args.get("operations") or []:
            if isinstance(operation, dict) and str(operation.get("op") or operation.get("type") or "").lower() == "advanced_com":
                return True
        plan = args.get("document") if isinstance(args.get("document"), dict) else {}
        return any(
            isinstance(block, dict) and str(block.get("type") or "").lower() == "advanced_com"
            for block in (plan.get("blocks") or [])
        )

    def _document_resolve_path(self, value, *, mode="read", default_name=""):
        text = os.path.expandvars(os.path.expanduser(str(value or "").strip().strip('"')))
        if not text:
            if not default_name:
                raise ValueError("A file path is required.")
            text = default_name
        if not os.path.isabs(text):
            base = self._sandbox_root() if self._sandbox_enabled() else OUTPUTS_DIR
            text = os.path.join(base, text)
        path = os.path.abspath(text)
        sandbox_ok, sandbox_error = self._ensure_sandbox_path_allowed(path, "read" if mode == "read" else "write")
        if not sandbox_ok:
            raise PermissionError(sandbox_error)
        if mode == "read" and not os.path.isfile(path):
            raise FileNotFoundError(path)
        if mode != "read":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    @staticmethod
    def _document_temp_path(output_path):
        root, ext = os.path.splitext(output_path)
        return f"{root}.smarti-{uuid.uuid4().hex[:10]}{ext or '.docx'}"

    @staticmethod
    def _document_backup(path):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        root, ext = os.path.splitext(path)
        candidate = f"{root}.backup-{stamp}{ext}"
        counter = 2
        while os.path.exists(candidate):
            candidate = f"{root}.backup-{stamp}-{counter}{ext}"
            counter += 1
        shutil.copy2(path, candidate)
        return candidate

    def _document_prepare_output(self, path, overwrite=False, backup_existing=False):
        if not os.path.exists(path):
            return None
        if not overwrite:
            raise FileExistsError(f"Output already exists: {path}. Set overwrite=true to replace it.")
        return self._document_backup(path) if backup_existing else None

    def _document_create(self, args, engine):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = self._document_resolve_path(
            args.get("output_path") or args.get("path"),
            mode="write",
            default_name=f"document-{stamp}.docx",
        )
        if os.path.splitext(output)[1].lower() not in {".docx", ".docm", ".dotx", ".dotm", ".rtf", ".doc"}:
            raise ValueError("create output must be a Word document path (.docx/.docm/.dotx/.dotm/.rtf/.doc).")
        replaced_backup = self._document_prepare_output(output, bool(args.get("overwrite")), backup_existing=True)
        template = ""
        if args.get("template_path"):
            template = self._document_resolve_path(args.get("template_path"), mode="read")
        plan = args.get("document") if isinstance(args.get("document"), dict) else {}
        if engine == "com":
            result = self._com_create_document(output, template, plan, args)
        elif engine == "python":
            if os.path.splitext(output)[1].lower() != ".docx" or (template and os.path.splitext(template)[1].lower() != ".docx"):
                raise ValueError("The independent python engine creates DOCX from DOCX templates only; use engine='com' for other Word formats.")
            result = self._python_create_document(output, template, plan)
        else:
            raise ValueError("LibreOffice is an export/render engine; use python or com for create.")
        result.update({"engine": engine, "output_path": output, "replaced_file_backup": replaced_backup})
        result.update(self._document_post_actions(output, args))
        return result

    def _document_edit(self, args, engine):
        source = self._document_resolve_path(args.get("path"), mode="read")
        output = self._document_resolve_path(args.get("output_path") or source, mode="write")
        in_place = os.path.normcase(source) == os.path.normcase(output)
        backup = None
        if in_place and args.get("backup", True):
            backup = self._document_backup(source)
        elif not in_place:
            self._document_prepare_output(output, bool(args.get("overwrite")), backup_existing=True)
        operations = args.get("operations") or []
        if not isinstance(operations, list) or not operations:
            raise ValueError("edit requires a non-empty operations array.")
        if engine == "com":
            result = self._com_edit_document(source, output, operations, args)
        elif engine == "python":
            if os.path.splitext(source)[1].lower() != ".docx" or os.path.splitext(output)[1].lower() != ".docx":
                raise ValueError("The independent python edit engine supports DOCX only; use engine='com' for other Word formats.")
            result = self._python_edit_document(source, output, operations)
        else:
            raise ValueError("LibreOffice is an export/render engine; use python or com for edit.")
        result.update({"engine": engine, "output_path": output, "backup_path": backup})
        result.update(self._document_post_actions(output, args))
        return result

    def _document_post_actions(self, path, args):
        payload = {}
        exports = args.get("export_formats") or []
        if isinstance(exports, str):
            exports = [exports]
        if exports:
            payload["exports"] = []
            for fmt in exports[:8]:
                fmt = str(fmt).lower().lstrip(".")
                target = os.path.splitext(path)[0] + "." + fmt
                if os.path.normcase(target) == os.path.normcase(path):
                    target = os.path.splitext(path)[0] + "-export." + fmt
                self._document_prepare_output(target, bool(args.get("overwrite")), backup_existing=True)
                engine = self._document_choose_engine("export", {"path": path, "format": fmt, "engine": "auto"})
                payload["exports"].append(self._document_export_internal(path, target, fmt, engine, args))
        if args.get("render_after"):
            render_args = {
                "path": path,
                "output_dir": args.get("output_dir"),
                "dpi": args.get("dpi", 144),
                "include_pdf": True,
                "page_limit": args.get("page_limit", 100),
            }
            render_engine = self._document_choose_engine("render", {**render_args, "engine": "auto"})
            payload["render"] = self._document_render(render_args, render_engine)
        return payload

    # ------------------------- python-docx engine -------------------------

    @staticmethod
    def _python_imports():
        try:
            import docx
            from docx.enum.section import WD_ORIENT, WD_SECTION_START
            from docx.enum.style import WD_STYLE_TYPE
            from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
            from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
            from docx.shared import Cm, Pt, RGBColor
        except Exception as exc:
            raise RuntimeError("python-docx is required for the independent DOCX engine.") from exc
        return locals()

    def _python_create_document(self, output, template, plan):
        api = self._python_imports()
        docx = api["docx"]
        document = docx.Document(template or None)
        self._python_apply_plan(document, plan, api)
        temp = self._document_temp_path(output)
        try:
            document.save(temp)
            os.replace(temp, output)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        return {"status": "created", "blocks": len(plan.get("blocks") or plan.get("sections") or [])}

    def _python_apply_plan(self, document, plan, api):
        self._python_set_core_properties(document, plan.get("metadata") or {})
        self._python_configure_defaults(document, plan, api)
        self._python_set_page_layout(document, plan.get("page") or {}, api)
        for style in plan.get("styles") or []:
            if isinstance(style, dict):
                self._python_define_style(document, style, api)
        if isinstance(plan.get("header"), dict):
            self._python_set_header_footer(document, "header", plan["header"], api)
        if isinstance(plan.get("footer"), dict):
            self._python_set_header_footer(document, "footer", plan["footer"], api)
        self._python_add_blocks(document, plan.get("blocks") or plan.get("sections") or [], api)
        settings = plan.get("settings") or {}
        if settings.get("update_fields_on_open", True):
            self._python_mark_fields_for_update(document, api)

    @staticmethod
    def _python_set_core_properties(document, metadata):
        props = document.core_properties
        mapping = {
            "title": "title", "subject": "subject", "author": "author",
            "keywords": "keywords", "comments": "comments", "category": "category",
        }
        for key, attr in mapping.items():
            if key in metadata:
                setattr(props, attr, str(metadata[key]))
        if not props.language:
            props.language = str(metadata.get("language") or "he-IL")

    def _python_configure_defaults(self, document, plan, api):
        Pt, RGBColor, qn = api["Pt"], api["RGBColor"], api["qn"]
        defaults = plan.get("defaults") or {}
        font_name = str(defaults.get("font") or "Arial")
        font_size = _clamp(defaults.get("font_size_pt"), 6, 72, 11)
        normal = document.styles["Normal"]
        normal.font.name = font_name
        normal.font.size = Pt(font_size)
        normal.font.color.rgb = RGBColor.from_string(_safe_color(defaults.get("color")))
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
        normal.element.rPr.rFonts.set(qn("w:cs"), font_name)
        normal.paragraph_format.space_after = Pt(_clamp(defaults.get("space_after_pt"), 0, 72, 6))
        normal.paragraph_format.line_spacing = _clamp(defaults.get("line_spacing"), 0.8, 3, 1.15)
        for name, size, color in (
            ("Title", 26, "17365D"), ("Subtitle", 14, "4F6275"),
            ("Heading 1", 18, "17365D"), ("Heading 2", 15, "2F5597"),
            ("Heading 3", 12, "365F91"),
        ):
            try:
                style = document.styles[name]
                style.font.name = font_name
                style.font.size = Pt(size)
                style.font.color.rgb = RGBColor.from_string(color)
                style.element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
                style.element.rPr.rFonts.set(qn("w:cs"), font_name)
            except Exception:
                pass

    def _python_set_page_layout(self, document, page, api, sections=None):
        Cm, WD_ORIENT = api["Cm"], api["WD_ORIENT"]
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        size = str(page.get("size") or "A4").upper()
        orientation = str(page.get("orientation") or "portrait").lower()
        margins = page.get("margins_cm") or {}
        for section in (sections if sections is not None else document.sections):
            if size == "A4":
                width, height = Cm(21.0), Cm(29.7)
            elif size in {"LETTER", "US LETTER"}:
                width, height = Cm(21.59), Cm(27.94)
            else:
                width = Cm(_clamp(page.get("width_cm"), 5, 100, 21.0))
                height = Cm(_clamp(page.get("height_cm"), 5, 100, 29.7))
            if orientation == "landscape":
                section.orientation = WD_ORIENT.LANDSCAPE
                width, height = height, width
            else:
                section.orientation = WD_ORIENT.PORTRAIT
            section.page_width, section.page_height = width, height
            section.top_margin = Cm(_clamp(margins.get("top"), 0, 10, 2.5))
            section.bottom_margin = Cm(_clamp(margins.get("bottom"), 0, 10, 2.5))
            section.left_margin = Cm(_clamp(margins.get("left"), 0, 10, 2.0))
            section.right_margin = Cm(_clamp(margins.get("right"), 0, 10, 2.0))
            section.gutter = Cm(_clamp(page.get("gutter_cm"), 0, 10, 0))
            section.header_distance = Cm(_clamp(page.get("header_distance_cm"), 0, 10, 1.25))
            section.footer_distance = Cm(_clamp(page.get("footer_distance_cm"), 0, 10, 1.25))
            section.different_first_page_header_footer = bool(page.get("different_first_page", False))
            bidi = section._sectPr.find(qn("w:bidi"))
            if page.get("rtl", True):
                if bidi is None:
                    bidi = OxmlElement("w:bidi")
                    section._sectPr.append(bidi)
                bidi.set(qn("w:val"), "1")
            elif bidi is not None:
                section._sectPr.remove(bidi)

    def _python_define_style(self, document, spec, api):
        WD_STYLE_TYPE = api["WD_STYLE_TYPE"]
        name = str(spec.get("name") or "").strip()
        if not name:
            raise ValueError("Style requires a name.")
        try:
            style = document.styles[name]
        except KeyError:
            style_type = WD_STYLE_TYPE.CHARACTER if str(spec.get("type") or "paragraph").lower() == "character" else WD_STYLE_TYPE.PARAGRAPH
            style = document.styles.add_style(name, style_type)
        self._python_apply_font(style.font, spec, api)
        if hasattr(style, "paragraph_format"):
            self._python_apply_paragraph_format(style.paragraph_format, spec, api)
        if spec.get("based_on"):
            try:
                style.base_style = document.styles[str(spec["based_on"])]
            except Exception:
                pass

    def _python_add_blocks(self, container, blocks, api):
        if not isinstance(blocks, list):
            raise ValueError("document.blocks must be an array.")
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type") or "paragraph").lower()
            if kind not in _PYTHON_BLOCK_TYPES:
                raise ValueError(f"Block type '{kind}' requires engine='com'.")
            if kind in {"paragraph", "heading", "title", "subtitle", "quote", "callout", "hyperlink", "bookmark", "field"}:
                self._python_add_text_block(container, block, kind, api)
            elif kind == "list":
                self._python_add_list(container, block, api)
            elif kind == "table":
                self._python_add_table(container, block, api)
            elif kind == "image":
                self._python_add_image(container, block, api)
            elif kind == "page_break":
                container.add_page_break()
            elif kind == "section_break":
                start = str(block.get("start") or "new_page").lower()
                enum = {
                    "continuous": api["WD_SECTION_START"].CONTINUOUS,
                    "even_page": api["WD_SECTION_START"].EVEN_PAGE,
                    "odd_page": api["WD_SECTION_START"].ODD_PAGE,
                }.get(start, api["WD_SECTION_START"].NEW_PAGE)
                section = container.add_section(enum)
                if block.get("page"):
                    self._python_set_page_layout(container, block.get("page") or {}, api, sections=[section])
            elif kind == "toc":
                self._python_ensure_toc_styles(container, api)
                paragraph = container.add_paragraph()
                self._python_set_paragraph(paragraph, block, api)
                self._python_add_field(paragraph, str(block.get("code") or 'TOC \\o "1-3" \\h \\z \\u'), "Table of Contents", api)
            elif kind in {"header", "footer"}:
                self._python_set_header_footer(container, kind, block, api)
            elif kind == "content_control":
                paragraph = container.add_paragraph()
                self._python_add_content_control(paragraph, block, api)
                self._python_set_paragraph(paragraph, block, api)

    def _python_add_text_block(self, container, block, kind, api):
        style = block.get("style")
        if not style:
            if kind == "heading":
                style = f"Heading {int(_clamp(block.get('level'), 1, 9, 1))}"
            elif kind == "title":
                style = "Title"
            elif kind == "subtitle":
                style = "Subtitle"
            elif kind == "quote":
                style = "Intense Quote"
        try:
            paragraph = container.add_paragraph(style=style) if style else container.add_paragraph()
        except Exception:
            paragraph = container.add_paragraph()
        runs = block.get("runs")
        if isinstance(runs, list):
            for run_spec in runs:
                if not isinstance(run_spec, dict):
                    run_spec = {"text": str(run_spec)}
                if run_spec.get("hyperlink"):
                    self._python_add_hyperlink(paragraph, str(run_spec.get("text") or ""), str(run_spec["hyperlink"]), run_spec, api)
                elif run_spec.get("field"):
                    self._python_add_field(paragraph, str(run_spec["field"]), str(run_spec.get("text") or ""), api)
                else:
                    run = paragraph.add_run(str(run_spec.get("text") or ""))
                    self._python_apply_run(run, run_spec, api)
        elif kind == "hyperlink":
            self._python_add_hyperlink(paragraph, str(block.get("text") or block.get("url") or ""), str(block.get("url") or ""), block, api)
        elif kind == "field":
            self._python_add_field(paragraph, str(block.get("code") or ""), str(block.get("text") or ""), api)
        else:
            run = paragraph.add_run(str(block.get("text") or ""))
            self._python_apply_run(run, block, api)
        if kind == "bookmark":
            self._python_wrap_bookmark(paragraph, str(block.get("name") or "bookmark"), api)
        self._python_set_paragraph(paragraph, block, api)
        return paragraph

    def _python_ensure_toc_styles(self, document, api):
        """Create RTL TOC styles before Word materializes field results."""
        WD_STYLE_TYPE, OxmlElement, qn = api["WD_STYLE_TYPE"], api["OxmlElement"], api["qn"]
        section = document.sections[0]
        content_width_twips = max(
            720,
            int((section.page_width - section.left_margin - section.right_margin) / 635),
        )
        normal = document.styles["Normal"]
        for level in range(1, 10):
            name = f"TOC {level}"
            try:
                style = document.styles[name]
            except KeyError:
                style = document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            style.base_style = normal
            style.font.name = normal.font.name or "Arial"
            style.font.size = normal.font.size
            p_pr = style.element.get_or_add_pPr()
            bidi = p_pr.find(qn("w:bidi"))
            if bidi is None:
                bidi = OxmlElement("w:bidi")
                p_pr.append(bidi)
            bidi.set(qn("w:val"), "1")
            jc = p_pr.find(qn("w:jc"))
            if jc is None:
                jc = OxmlElement("w:jc")
                p_pr.append(jc)
            jc.set(qn("w:val"), "left")  # physical right after bidi mirroring
            tabs = p_pr.find(qn("w:tabs"))
            if tabs is None:
                tabs = OxmlElement("w:tabs")
                p_pr.append(tabs)
            for existing in list(tabs):
                tabs.remove(existing)
            tab = OxmlElement("w:tab")
            tab.set(qn("w:val"), "right")
            tab.set(qn("w:leader"), "dot")
            tab.set(qn("w:pos"), str(content_width_twips))
            tabs.append(tab)
            if level > 1:
                style.paragraph_format.left_indent = api["Cm"](0.45 * (level - 1))

    def _python_set_paragraph(self, paragraph, spec, api):
        WD_ALIGN_PARAGRAPH, OxmlElement, qn = api["WD_ALIGN_PARAGRAPH"], api["OxmlElement"], api["qn"]
        rtl = bool(spec.get("rtl", True))
        alignment = str(spec.get("alignment") or ("right" if rtl else "left")).lower()
        # In WordprocessingML, Word mirrors the physical left/right meaning of
        # w:jc for bidi paragraphs.  Swap only those two values so callers keep
        # using visual alignment names ("right" means the right page margin).
        xml_alignment = {"left": "right", "right": "left"}.get(alignment, alignment) if rtl else alignment
        paragraph.alignment = {
            "left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
        }.get(xml_alignment, WD_ALIGN_PARAGRAPH.LEFT if rtl else WD_ALIGN_PARAGRAPH.RIGHT)
        self._python_apply_paragraph_format(paragraph.paragraph_format, spec, api)
        p_pr = paragraph._p.get_or_add_pPr()
        bidi = p_pr.find(qn("w:bidi"))
        if rtl:
            if bidi is None:
                bidi = OxmlElement("w:bidi")
                p_pr.append(bidi)
            bidi.set(qn("w:val"), "1")
        elif bidi is not None:
            p_pr.remove(bidi)
        if spec.get("keep_with_next"):
            keep = OxmlElement("w:keepNext")
            p_pr.append(keep)
        if spec.get("page_break_before"):
            p_pr.append(OxmlElement("w:pageBreakBefore"))

    def _python_apply_paragraph_format(self, fmt, spec, api):
        Pt, Cm = api["Pt"], api["Cm"]
        for key, attr in (
            ("space_before_pt", "space_before"), ("space_after_pt", "space_after"),
        ):
            if key in spec:
                setattr(fmt, attr, Pt(_clamp(spec[key], 0, 300, 0)))
        if "line_spacing" in spec:
            fmt.line_spacing = _clamp(spec["line_spacing"], 0.5, 5, 1.15)
        for key, attr in (
            ("left_indent_cm", "left_indent"), ("right_indent_cm", "right_indent"),
            ("first_line_indent_cm", "first_line_indent"),
        ):
            if key in spec:
                setattr(fmt, attr, Cm(_clamp(spec[key], -10, 30, 0)))
        if "keep_together" in spec:
            fmt.keep_together = bool(spec["keep_together"])
        if "widow_control" in spec:
            fmt.widow_control = bool(spec["widow_control"])

    def _python_apply_font(self, font, spec, api):
        Pt, RGBColor = api["Pt"], api["RGBColor"]
        if spec.get("font"):
            font.name = str(spec["font"])
        if spec.get("font_size_pt") is not None:
            font.size = Pt(_clamp(spec["font_size_pt"], 1, 400, 11))
        for key, attr in (
            ("bold", "bold"), ("italic", "italic"), ("underline", "underline"),
            ("strike", "strike"), ("superscript", "superscript"), ("subscript", "subscript"),
        ):
            if key in spec:
                setattr(font, attr, bool(spec[key]))
        if spec.get("color"):
            font.color.rgb = RGBColor.from_string(_safe_color(spec["color"]))

    def _python_apply_run(self, run, spec, api):
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        self._python_apply_font(run.font, spec, api)
        font_name = str(spec.get("font") or run.font.name or "Arial")
        r_pr = run._r.get_or_add_rPr()
        r_fonts = r_pr.get_or_add_rFonts()
        r_fonts.set(qn("w:cs"), font_name)
        r_fonts.set(qn("w:eastAsia"), font_name)
        lang = r_pr.find(qn("w:lang"))
        if lang is None:
            lang = OxmlElement("w:lang")
            r_pr.append(lang)
        lang.set(qn("w:val"), str(spec.get("language") or "he-IL"))
        lang.set(qn("w:bidi"), str(spec.get("language") or "he-IL"))
        if spec.get("rtl", True):
            rtl = OxmlElement("w:rtl")
            rtl.set(qn("w:val"), "1")
            r_pr.append(rtl)

    def _python_add_hyperlink(self, paragraph, text, url, spec, api):
        if not re.match(r"^(https?|mailto):", url, flags=re.I):
            raise ValueError("Hyperlinks must use http, https, or mailto.")
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        relationship = paragraph.part.relate_to(
            url,
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
            is_external=True,
        )
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("r:id"), relationship)
        run = paragraph.add_run(text)
        self._python_apply_run(run, spec, api)
        r_pr = run._r.get_or_add_rPr()
        if not spec.get("color"):
            color = OxmlElement("w:color")
            color.set(qn("w:val"), "0563C1")
            r_pr.append(color)
        if "underline" not in spec:
            underline = OxmlElement("w:u")
            underline.set(qn("w:val"), "single")
            r_pr.append(underline)
        hyperlink.append(run._r)
        paragraph._p.append(hyperlink)

    def _python_add_list(self, container, block, api):
        ordered = bool(block.get("ordered", False))
        items = block.get("items") or []
        if not isinstance(items, list) or not items:
            raise ValueError("list.items must be a non-empty array.")
        for raw_item in items:
            item = raw_item if isinstance(raw_item, dict) else {"text": str(raw_item)}
            level = int(_clamp(item.get("level"), 0, 8, 0))
            base_style = "List Number" if item.get("ordered", ordered) else "List Bullet"
            style = item.get("style") or (base_style if level == 0 else f"{base_style} {min(level + 1, 3)}")
            paragraph = self._python_add_text_block(container, {**block, **item, "style": style}, "paragraph", api)
            if level > 2:
                paragraph.paragraph_format.left_indent = api["Cm"](0.63 * (level - 2))

    @staticmethod
    def _python_add_field(paragraph, code, display_text, api):
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        instruction = OxmlElement("w:instrText")
        instruction.set(qn("xml:space"), "preserve")
        instruction.text = code
        separate = OxmlElement("w:fldChar")
        separate.set(qn("w:fldCharType"), "separate")
        text_node = OxmlElement("w:t")
        text_node.text = display_text
        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        for element in (begin, instruction, separate, text_node, end):
            run = OxmlElement("w:r")
            run.append(element)
            paragraph._p.append(run)

    @staticmethod
    def _python_wrap_bookmark(paragraph, name, api):
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        clean = re.sub(r"[^A-Za-z0-9_]", "_", name)[:40] or "bookmark"
        bookmark_id = str(abs(hash((clean, paragraph.text))) % 2000000000)
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), bookmark_id)
        start.set(qn("w:name"), clean)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), bookmark_id)
        paragraph._p.insert(0, start)
        paragraph._p.append(end)

    def _python_add_table(self, container, block, api):
        Cm, WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT = api["Cm"], api["WD_CELL_VERTICAL_ALIGNMENT"], api["WD_TABLE_ALIGNMENT"]
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        rows = block.get("rows") or []
        if not isinstance(rows, list) or not rows:
            raise ValueError("table.rows must be a non-empty array.")
        normalized = [row if isinstance(row, list) else list(row.values()) if isinstance(row, dict) else [row] for row in rows]
        columns = max(len(row) for row in normalized)
        table = container.add_table(rows=len(normalized), cols=columns)
        try:
            table.style = str(block.get("style") or "Table Grid")
        except Exception:
            pass
        table.alignment = {
            "left": WD_TABLE_ALIGNMENT.LEFT, "center": WD_TABLE_ALIGNMENT.CENTER,
            "right": WD_TABLE_ALIGNMENT.RIGHT,
        }.get(str(block.get("alignment") or "right").lower(), WD_TABLE_ALIGNMENT.RIGHT)
        table.autofit = bool(block.get("autofit", False))
        widths = block.get("column_widths_cm") or []
        header_rows = int(_clamp(block.get("header_rows"), 0, len(normalized), 1))
        for row_index, values in enumerate(normalized):
            for col_index in range(columns):
                cell = table.cell(row_index, col_index)
                value = values[col_index] if col_index < len(values) else ""
                spec = value if isinstance(value, dict) else {"text": value}
                cell.text = ""
                paragraph = cell.paragraphs[0]
                run = paragraph.add_run(str(spec.get("text") or ""))
                merged = {**block.get("cell_defaults", {}), **spec}
                if row_index < header_rows:
                    merged.setdefault("bold", True)
                self._python_apply_run(run, merged, api)
                self._python_set_paragraph(paragraph, merged, api)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                if col_index < len(widths):
                    cell.width = Cm(_clamp(widths[col_index], 0.5, 50, 3))
                tc_pr = cell._tc.get_or_add_tcPr()
                if merged.get("fill"):
                    shading = OxmlElement("w:shd")
                    shading.set(qn("w:fill"), _safe_color(merged["fill"], "FFFFFF"))
                    tc_pr.append(shading)
            if row_index < header_rows:
                tr_pr = table.rows[row_index]._tr.get_or_add_trPr()
                tr_pr.append(OxmlElement("w:tblHeader"))
        tbl_pr = table._tbl.tblPr
        bidi_visual = OxmlElement("w:bidiVisual")
        bidi_visual.set(qn("w:val"), "1" if block.get("rtl", True) else "0")
        tbl_pr.append(bidi_visual)
        for merge in block.get("merges") or []:
            if not isinstance(merge, dict):
                continue
            start_row = int(merge.get("from_row", merge.get("row", 0)))
            start_col = int(merge.get("from_column", merge.get("column", 0)))
            end_row = int(merge.get("to_row", start_row))
            end_col = int(merge.get("to_column", start_col))
            if not (0 <= start_row <= end_row < len(normalized) and 0 <= start_col <= end_col < columns):
                raise ValueError("table merge coordinates are out of range.")
            table.cell(start_row, start_col).merge(table.cell(end_row, end_col))
        return table

    def _python_add_image(self, container, block, api):
        path = self._document_resolve_path(block.get("path"), mode="read")
        Cm, WD_ALIGN_PARAGRAPH = api["Cm"], api["WD_ALIGN_PARAGRAPH"]
        paragraph = container.add_paragraph()
        paragraph.alignment = {
            "left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
        }.get(str(block.get("alignment") or "center").lower(), WD_ALIGN_PARAGRAPH.CENTER)
        run = paragraph.add_run()
        kwargs = {}
        if block.get("width_cm") is not None:
            kwargs["width"] = Cm(_clamp(block["width_cm"], 0.1, 100, 10))
        if block.get("height_cm") is not None:
            kwargs["height"] = Cm(_clamp(block["height_cm"], 0.1, 100, 10))
        shape = run.add_picture(path, **kwargs)
        if block.get("alt_text"):
            doc_pr = shape._inline.docPr
            doc_pr.set("descr", str(block["alt_text"])[:1000])
            doc_pr.set("title", str(block.get("title") or block["alt_text"])[:255])
        return paragraph

    def _python_set_header_footer(self, document, kind, spec, api):
        for section in document.sections:
            story = section.header if kind == "header" else section.footer
            paragraph = story.paragraphs[0]
            paragraph.clear()
            if spec.get("runs"):
                for item in spec["runs"]:
                    item = item if isinstance(item, dict) else {"text": str(item)}
                    if item.get("field"):
                        self._python_add_field(paragraph, str(item["field"]), str(item.get("text") or ""), api)
                    else:
                        run = paragraph.add_run(str(item.get("text") or ""))
                        self._python_apply_run(run, item, api)
            else:
                run = paragraph.add_run(str(spec.get("text") or ""))
                self._python_apply_run(run, spec, api)
                if spec.get("page_number"):
                    paragraph.add_run(" ")
                    self._python_add_field(paragraph, "PAGE", "1", api)
            self._python_set_paragraph(paragraph, spec, api)

    def _python_add_content_control(self, paragraph, spec, api):
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        sdt = OxmlElement("w:sdt")
        sdt_pr = OxmlElement("w:sdtPr")
        alias = OxmlElement("w:alias")
        alias.set(qn("w:val"), str(spec.get("title") or "Content"))
        tag = OxmlElement("w:tag")
        tag.set(qn("w:val"), str(spec.get("tag") or "smarti"))
        sdt_pr.extend([alias, tag, OxmlElement("w:text")])
        content = OxmlElement("w:sdtContent")
        run = paragraph.add_run(str(spec.get("text") or spec.get("placeholder") or ""))
        self._python_apply_run(run, spec, api)
        content.append(run._r)
        sdt.extend([sdt_pr, content])
        paragraph._p.append(sdt)

    @staticmethod
    def _python_mark_fields_for_update(document, api):
        OxmlElement, qn = api["OxmlElement"], api["qn"]
        settings = document.settings.element
        existing = settings.find(qn("w:updateFields"))
        if existing is None:
            existing = OxmlElement("w:updateFields")
            settings.append(existing)
        existing.set(qn("w:val"), "true")

    def _python_edit_document(self, source, output, operations):
        api = self._python_imports()
        document = api["docx"].Document(source)
        counts = {}
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            op = str(operation.get("op") or operation.get("type") or "").lower()
            if op in _COM_ONLY_OPERATIONS:
                raise ValueError(f"Operation '{op}' requires engine='com'.")
            if op == "replace_text":
                old = str(operation.get("find") or operation.get("old") or "")
                new = str(operation.get("replace") if "replace" in operation else operation.get("new") or "")
                if not old:
                    raise ValueError("replace_text requires find.")
                counts[op] = counts.get(op, 0) + self._python_replace_text(document, old, new, bool(operation.get("case_sensitive")))
            elif op in {"append_blocks", "append"}:
                blocks = operation.get("blocks") or []
                self._python_add_blocks(document, blocks, api)
                counts[op] = counts.get(op, 0) + len(blocks)
            elif op == "delete_paragraph":
                paragraph = self._python_select_paragraph(document, operation.get("selector") or operation)
                paragraph._element.getparent().remove(paragraph._element)
                counts[op] = counts.get(op, 0) + 1
            elif op == "format_paragraph":
                paragraph = self._python_select_paragraph(document, operation.get("selector") or operation)
                self._python_set_paragraph(paragraph, operation.get("format") or operation, api)
                for run in paragraph.runs:
                    self._python_apply_run(run, operation.get("format") or operation, api)
                counts[op] = counts.get(op, 0) + 1
            elif op == "set_page_layout":
                self._python_set_page_layout(document, operation.get("page") or operation, api)
                counts[op] = counts.get(op, 0) + 1
            elif op == "define_style":
                self._python_define_style(document, operation.get("style") or operation, api)
                counts[op] = counts.get(op, 0) + 1
            elif op in {"set_header", "set_footer"}:
                self._python_set_header_footer(document, op.split("_")[1], operation, api)
                counts[op] = counts.get(op, 0) + 1
            elif op == "update_fields":
                self._python_mark_fields_for_update(document, api)
                counts[op] = counts.get(op, 0) + 1
            elif op == "set_properties":
                self._python_set_core_properties(document, operation.get("properties") or operation)
                counts[op] = counts.get(op, 0) + 1
            else:
                raise ValueError(f"Unsupported python edit operation: {op}")
        temp = self._document_temp_path(output)
        try:
            document.save(temp)
            os.replace(temp, output)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        return {"status": "edited", "operation_counts": counts}

    def _python_iter_paragraphs(self, document):
        for paragraph in document.paragraphs:
            yield paragraph
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        yield paragraph
        for section in document.sections:
            for story in (section.header, section.footer):
                for paragraph in story.paragraphs:
                    yield paragraph

    def _python_replace_text(self, document, old, new, case_sensitive=False):
        count = 0
        pattern = re.compile(re.escape(old), 0 if case_sensitive else re.IGNORECASE)
        for paragraph in self._python_iter_paragraphs(document):
            runs = list(paragraph.runs)
            combined = "".join(run.text for run in runs)
            matches = list(pattern.finditer(combined))
            if not matches:
                continue
            starts = []
            cursor = 0
            for run in runs:
                starts.append(cursor)
                cursor += len(run.text)
            for match in reversed(matches):
                start, end = match.span()
                start_index = next(index for index, offset in enumerate(starts) if offset + len(runs[index].text) > start)
                end_index = next(index for index, offset in enumerate(starts) if offset + len(runs[index].text) >= end)
                start_offset = start - starts[start_index]
                end_offset = end - starts[end_index]
                if start_index == end_index:
                    text = runs[start_index].text
                    runs[start_index].text = text[:start_offset] + new + text[end_offset:]
                else:
                    runs[start_index].text = runs[start_index].text[:start_offset] + new
                    for index in range(start_index + 1, end_index):
                        runs[index].text = ""
                    runs[end_index].text = runs[end_index].text[end_offset:]
            count += len(matches)
        return count

    @staticmethod
    def _python_select_paragraph(document, selector):
        selector = selector if isinstance(selector, dict) else {}
        if selector.get("paragraph_index") is not None:
            index = int(selector["paragraph_index"])
            if index < 0 or index >= len(document.paragraphs):
                raise IndexError("paragraph_index is out of range.")
            return document.paragraphs[index]
        text = str(selector.get("find") or selector.get("contains") or "")
        occurrence = max(1, int(selector.get("occurrence") or 1))
        seen = 0
        for paragraph in document.paragraphs:
            if text in paragraph.text:
                seen += 1
                if seen == occurrence:
                    return paragraph
        raise ValueError("Paragraph selector did not match.")

    # -------------------------- Word COM engine ---------------------------

    def _com_create_document(self, output, template, plan, args):
        temp = self._document_temp_path(output)
        try:
            with _WordComSession(args.get("timeout_seconds", 180), args.get("visible", False)) as session:
                document = session.new_document(template)
                self._com_apply_plan(document, plan, args)
                self._com_save_document(document, temp, output)
                session.close_document(False)
            os.replace(temp, output)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        return {"status": "created", "blocks": len(plan.get("blocks") or plan.get("sections") or [])}

    def _com_edit_document(self, source, output, operations, args):
        temp = self._document_temp_path(output)
        results = []
        try:
            with _WordComSession(args.get("timeout_seconds", 180), args.get("visible", False)) as session:
                document = session.open_document(source, password=str(args.get("password") or ""))
                for operation in operations:
                    if isinstance(operation, dict):
                        results.append(self._com_apply_operation(document, operation, args))
                try:
                    self._com_prepare_toc_styles(document)
                    document.Fields.Update()
                except Exception:
                    pass
                self._com_save_document(document, temp, output)
                session.close_document(False)
            os.replace(temp, output)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        return {"status": "edited", "operations": results}

    def _com_apply_plan(self, document, plan, args):
        self._com_set_properties(document, plan.get("metadata") or {})
        self._com_set_page_layout(document, plan.get("page") or {})
        defaults = plan.get("defaults") or {}
        self._com_configure_styles(document, defaults)
        for style in plan.get("styles") or []:
            if isinstance(style, dict):
                self._com_define_style(document, style)
        if isinstance(plan.get("header"), dict):
            self._com_set_header_footer(document, "header", plan["header"])
        if isinstance(plan.get("footer"), dict):
            self._com_set_header_footer(document, "footer", plan["footer"])
        self._com_add_blocks(document, plan.get("blocks") or plan.get("sections") or [], args)
        if (plan.get("settings") or {}).get("track_changes"):
            document.TrackRevisions = True
        try:
            self._com_prepare_toc_styles(document)
            document.Fields.Update()
        except Exception:
            pass

    @staticmethod
    def _com_set_properties(document, metadata):
        mapping = {
            "title": "Title", "subject": "Subject", "author": "Author",
            "keywords": "Keywords", "comments": "Comments", "category": "Category",
        }
        for key, prop_name in mapping.items():
            if key not in metadata:
                continue
            try:
                document.BuiltInDocumentProperties(prop_name).Value = str(metadata[key])
            except Exception:
                pass

    def _com_set_page_layout(self, document, page, sections=None):
        size = str(page.get("size") or "A4").upper()
        orientation = str(page.get("orientation") or "portrait").lower()
        margins = page.get("margins_cm") or {}
        selected_sections = sections or [document.Sections(index) for index in range(1, int(document.Sections.Count) + 1)]
        for section in selected_sections:
            setup = section.PageSetup
            setup.PaperSize = 7 if size == "A4" else 2 if size in {"LETTER", "US LETTER"} else setup.PaperSize
            setup.Orientation = 1 if orientation == "landscape" else 0
            setup.TopMargin = self._cm_to_points(margins.get("top", 2.5))
            setup.BottomMargin = self._cm_to_points(margins.get("bottom", 2.5))
            setup.LeftMargin = self._cm_to_points(margins.get("left", 2.0))
            setup.RightMargin = self._cm_to_points(margins.get("right", 2.0))
            setup.Gutter = self._cm_to_points(page.get("gutter_cm", 0))
            setup.HeaderDistance = self._cm_to_points(page.get("header_distance_cm", 1.25))
            setup.FooterDistance = self._cm_to_points(page.get("footer_distance_cm", 1.25))
            setup.DifferentFirstPageHeaderFooter = bool(page.get("different_first_page", False))
            setup.OddAndEvenPagesHeaderFooter = bool(page.get("different_odd_even", False))
            try:
                setup.SectionDirection = 0 if page.get("rtl", True) else 1
            except Exception:
                pass

    @staticmethod
    def _cm_to_points(value):
        return _clamp(value, -100, 1000, 0) * 72.0 / 2.54

    def _com_configure_styles(self, document, defaults):
        font = str(defaults.get("font") or "Arial")
        size = _clamp(defaults.get("font_size_pt"), 6, 72, 11)
        for style_ref, font_size, bold, color in (
            (-1, size, False, "000000"), (-63, 26, True, "17365D"),
            (-75, 14, False, "4F6275"), (-2, 18, True, "17365D"),
            (-3, 15, True, "2F5597"), (-4, 12, True, "365F91"),
        ):
            try:
                style = document.Styles(style_ref)
                style.Font.Name = font
                style.Font.NameBi = font
                style.Font.Size = font_size
                style.Font.SizeBi = font_size
                style.Font.Bold = bold
                style.Font.Color = self._com_rgb(color)
                style.ParagraphFormat.ReadingOrder = 0
                style.ParagraphFormat.Alignment = 2
            except Exception:
                pass
        self._com_prepare_toc_styles(document)

    @staticmethod
    def _com_prepare_toc_styles(document):
        try:
            rtl = int(document.Sections(1).PageSetup.SectionDirection) == 0
        except Exception:
            rtl = False
        if not rtl:
            return
        for style_ref in range(-20, -29, -1):  # wdStyleTOC1 through wdStyleTOC9
            try:
                style = document.Styles(style_ref)
                style.ParagraphFormat.ReadingOrder = 0
                style.ParagraphFormat.Alignment = 2
            except Exception:
                pass

    def _com_define_style(self, document, spec):
        name = str(spec.get("name") or "").strip()
        if not name:
            raise ValueError("Style requires a name.")
        try:
            style = document.Styles(self._com_style_ref(name))
        except Exception:
            style = document.Styles.Add(Name=name, Type=1 if str(spec.get("type") or "paragraph") == "paragraph" else 2)
        self._com_apply_font(style.Font, spec)
        self._com_apply_paragraph_format(style.ParagraphFormat, spec)
        if spec.get("based_on"):
            try:
                style.BaseStyle = self._com_style_ref(spec["based_on"])
            except Exception:
                pass

    @staticmethod
    def _com_style_ref(value):
        if isinstance(value, int):
            return value
        text = str(value or "").strip()
        folded = re.sub(r"[\s_-]+", "", text).casefold()
        return _WORD_BUILTIN_STYLES.get(folded, text)

    @staticmethod
    def _com_rgb(value):
        text = _safe_color(value)
        red, green, blue = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
        return red | (green << 8) | (blue << 16)

    def _com_apply_font(self, font, spec):
        if spec.get("font"):
            font.Name = str(spec["font"])
            font.NameBi = str(spec["font"])
        if spec.get("font_size_pt") is not None:
            size = _clamp(spec["font_size_pt"], 1, 400, 11)
            font.Size = size
            font.SizeBi = size
        for key, attr in (
            ("bold", "Bold"), ("italic", "Italic"), ("underline", "Underline"),
            ("strike", "StrikeThrough"), ("superscript", "Superscript"), ("subscript", "Subscript"),
        ):
            if key in spec:
                setattr(font, attr, bool(spec[key]))
        if spec.get("color"):
            font.Color = self._com_rgb(spec["color"])

    def _com_apply_paragraph_format(self, fmt, spec):
        alignment = str(spec.get("alignment") or ("right" if spec.get("rtl", True) else "left")).lower()
        fmt.Alignment = {"left": 0, "center": 1, "right": 2, "justify": 3}.get(alignment, 2)
        fmt.ReadingOrder = 0 if spec.get("rtl", True) else 1
        for key, attr in (
            ("space_before_pt", "SpaceBefore"), ("space_after_pt", "SpaceAfter"),
        ):
            if key in spec:
                setattr(fmt, attr, _clamp(spec[key], 0, 300, 0))
        if "line_spacing" in spec:
            fmt.LineSpacingRule = 5
            fmt.LineSpacing = 12 * _clamp(spec["line_spacing"], 0.5, 5, 1.15)
        for key, attr in (
            ("left_indent_cm", "LeftIndent"), ("right_indent_cm", "RightIndent"),
            ("first_line_indent_cm", "FirstLineIndent"),
        ):
            if key in spec:
                setattr(fmt, attr, self._cm_to_points(spec[key]))
        if "keep_with_next" in spec:
            fmt.KeepWithNext = bool(spec["keep_with_next"])
        if "keep_together" in spec:
            fmt.KeepTogether = bool(spec["keep_together"])
        if "widow_control" in spec:
            fmt.WidowControl = bool(spec["widow_control"])
        if "page_break_before" in spec:
            fmt.PageBreakBefore = bool(spec["page_break_before"])

    def _com_add_blocks(self, document, blocks, args, anchor=None):
        for block in blocks if isinstance(blocks, list) else []:
            if isinstance(block, dict):
                self._com_add_block(document, block, args, anchor)

    def _com_end_range(self, document):
        end = max(0, int(document.Content.End) - 1)
        return document.Range(end, end)

    def _com_add_block(self, document, block, args, anchor=None):
        kind = str(block.get("type") or "paragraph").lower()
        target = anchor.Duplicate if anchor is not None else self._com_end_range(document)
        try:
            target.Collapse(0)
        except Exception:
            pass
        if kind in {"paragraph", "heading", "title", "subtitle", "quote", "callout", "hyperlink", "bookmark", "field"}:
            start = int(target.Start)
            runs = block.get("runs")
            if isinstance(runs, list):
                for item in runs:
                    item = item if isinstance(item, dict) else {"text": str(item)}
                    run_start = int(target.End)
                    text = str(item.get("text") or "")
                    target.InsertAfter(text)
                    run_range = document.Range(run_start, run_start + len(text))
                    self._com_apply_font(run_range.Font, item)
                    run_range.LanguageID = 1037
                    if item.get("hyperlink"):
                        url = str(item["hyperlink"])
                        if not re.match(r"^(https?|mailto):", url, flags=re.I):
                            raise ValueError("Hyperlinks must use http, https, or mailto.")
                        document.Hyperlinks.Add(Anchor=run_range, Address=url, TextToDisplay=text)
            elif kind == "hyperlink":
                url = str(block.get("url") or "")
                if not re.match(r"^(https?|mailto):", url, flags=re.I):
                    raise ValueError("Hyperlinks must use http, https, or mailto.")
                document.Hyperlinks.Add(Anchor=target, Address=url, TextToDisplay=str(block.get("text") or url))
            elif kind == "field":
                document.Fields.Add(Range=target, Type=-1, Text=str(block.get("code") or ""), PreserveFormatting=True)
            else:
                text = str(block.get("text") or "")
                target.InsertAfter(text)
            end = int(target.End)
            paragraph_range = document.Range(start, end)
            paragraph = paragraph_range.Paragraphs(1)
            if kind == "heading":
                paragraph.Range.Style = -int(_clamp(block.get('level'), 1, 9, 1)) - 1
            elif kind == "title":
                paragraph.Range.Style = -63
            elif kind == "subtitle":
                paragraph.Range.Style = -75
            elif kind == "quote":
                paragraph.Range.Style = -181
            elif block.get("style"):
                paragraph.Range.Style = self._com_style_ref(block["style"])
            self._com_apply_font(paragraph.Range.Font, block)
            self._com_apply_paragraph_format(paragraph.Format, block)
            paragraph.Range.LanguageID = 1037
            if kind == "bookmark":
                document.Bookmarks.Add(re.sub(r"\W", "_", str(block.get("name") or "bookmark"))[:40], paragraph_range)
            paragraph.Range.InsertParagraphAfter()
            return
        if kind == "list":
            items = block.get("items") or []
            if not isinstance(items, list) or not items:
                raise ValueError("list.items must be a non-empty array.")
            start = int(target.Start)
            texts = [str(item.get("text") or "") if isinstance(item, dict) else str(item) for item in items]
            target.InsertAfter("\r".join(texts))
            list_range = document.Range(start, start + len("\r".join(texts)))
            if block.get("ordered", False):
                list_range.ListFormat.ApplyNumberDefault()
            else:
                list_range.ListFormat.ApplyBulletDefault()
            for index, raw_item in enumerate(items, 1):
                item = raw_item if isinstance(raw_item, dict) else {"text": str(raw_item)}
                paragraph = list_range.Paragraphs(index)
                merged = {**block, **item}
                self._com_apply_font(paragraph.Range.Font, merged)
                self._com_apply_paragraph_format(paragraph.Format, merged)
                paragraph.Range.LanguageID = 1037
                for _level in range(int(_clamp(item.get("level"), 0, 8, 0))):
                    paragraph.Range.ListFormat.ListIndent()
            list_range.InsertParagraphAfter()
            return
        if kind == "table":
            rows = block.get("rows") or []
            normalized = [row if isinstance(row, list) else list(row.values()) if isinstance(row, dict) else [row] for row in rows]
            if not normalized:
                raise ValueError("table.rows must be non-empty.")
            cols = max(len(row) for row in normalized)
            table = document.Tables.Add(target, len(normalized), cols)
            try:
                table.Style = str(block.get("style") or "Table Grid")
            except Exception:
                pass
            table.TableDirection = 0 if block.get("rtl", True) else 1
            table.Rows.Alignment = {"left": 0, "center": 1, "right": 2}.get(str(block.get("alignment") or "right").lower(), 2)
            widths = block.get("column_widths_cm") or []
            header_rows = int(_clamp(block.get("header_rows"), 0, len(normalized), 1))
            for row_index, values in enumerate(normalized, 1):
                for col_index in range(1, cols + 1):
                    value = values[col_index - 1] if col_index <= len(values) else ""
                    spec = value if isinstance(value, dict) else {"text": value}
                    cell = table.Cell(row_index, col_index)
                    cell.Range.Text = str(spec.get("text") or "")
                    merged = {**block.get("cell_defaults", {}), **spec}
                    if row_index <= header_rows:
                        merged.setdefault("bold", True)
                    self._com_apply_font(cell.Range.Font, merged)
                    self._com_apply_paragraph_format(cell.Range.ParagraphFormat, merged)
                    cell.VerticalAlignment = 1
                    if col_index <= len(widths):
                        cell.Width = self._cm_to_points(widths[col_index - 1])
                    if merged.get("fill"):
                        cell.Shading.BackgroundPatternColor = self._com_rgb(merged["fill"])
                if row_index <= header_rows:
                    table.Rows(row_index).HeadingFormat = True
            for merge in block.get("merges") or []:
                if not isinstance(merge, dict):
                    continue
                start_row = int(merge.get("from_row", merge.get("row", 0))) + 1
                start_col = int(merge.get("from_column", merge.get("column", 0))) + 1
                end_row = int(merge.get("to_row", start_row - 1)) + 1
                end_col = int(merge.get("to_column", start_col - 1)) + 1
                if not (1 <= start_row <= end_row <= len(normalized) and 1 <= start_col <= end_col <= cols):
                    raise ValueError("table merge coordinates are out of range.")
                table.Cell(start_row, start_col).Merge(table.Cell(end_row, end_col))
            self._com_end_range(document).InsertParagraphAfter()
            return
        if kind == "image":
            image_path = self._document_resolve_path(block.get("path"), mode="read")
            shape = document.InlineShapes.AddPicture(FileName=image_path, LinkToFile=False, SaveWithDocument=True, Range=target)
            if block.get("width_cm") is not None:
                shape.Width = self._cm_to_points(block["width_cm"])
            if block.get("height_cm") is not None:
                shape.Height = self._cm_to_points(block["height_cm"])
            try:
                shape.AlternativeText = str(block.get("alt_text") or "")
                shape.Title = str(block.get("title") or "")
            except Exception:
                pass
            target.ParagraphFormat.Alignment = {"left": 0, "center": 1, "right": 2}.get(str(block.get("alignment") or "center").lower(), 1)
            target.InsertParagraphAfter()
            return
        if kind == "page_break":
            target.InsertBreak(7)
            return
        if kind == "section_break":
            target.InsertBreak({"continuous": 3, "even_page": 4, "odd_page": 5}.get(str(block.get("start") or "new_page").lower(), 2))
            if block.get("page"):
                try:
                    affected = [target.Sections(1)]
                except Exception:
                    affected = [document.Sections(document.Sections.Count)]
                self._com_set_page_layout(document, block.get("page") or {}, sections=affected)
            return
        if kind == "toc":
            document.TablesOfContents.Add(
                Range=target, UseHeadingStyles=True,
                UpperHeadingLevel=int(block.get("upper_level") or 1),
                LowerHeadingLevel=int(block.get("lower_level") or 3),
                UseHyperlinks=True, HidePageNumbersInWeb=True,
            )
            target.InsertParagraphAfter()
            return
        if kind in {"header", "footer"}:
            self._com_set_header_footer(document, kind, block)
            return
        if kind == "comment":
            comment_range = self._com_select_range(document, block.get("selector") or {})
            document.Comments.Add(Range=comment_range, Text=str(block.get("text") or ""))
            return
        if kind in {"footnote", "endnote"}:
            note_range = self._com_select_range(document, block.get("selector") or {})
            collection = document.Footnotes if kind == "footnote" else document.Endnotes
            collection.Add(Range=note_range, Text=str(block.get("text") or ""))
            return
        if kind == "content_control":
            control = document.ContentControls.Add(Type=int(block.get("control_type") or 0), Range=target)
            control.Title = str(block.get("title") or "")
            control.Tag = str(block.get("tag") or "")
            control.Range.Text = str(block.get("text") or block.get("placeholder") or "")
            self._com_apply_font(control.Range.Font, block)
            self._com_apply_paragraph_format(control.Range.ParagraphFormat, block)
            control.Range.LanguageID = 1037
            return
        if kind == "text_box":
            shape = document.Shapes.AddTextbox(
                Orientation=1,
                Left=self._cm_to_points(block.get("left_cm", 2)),
                Top=self._cm_to_points(block.get("top_cm", 2)),
                Width=self._cm_to_points(block.get("width_cm", 8)),
                Height=self._cm_to_points(block.get("height_cm", 3)),
                Anchor=target,
            )
            shape.TextFrame.TextRange.Text = str(block.get("text") or "")
            self._com_apply_font(shape.TextFrame.TextRange.Font, block)
            self._com_apply_paragraph_format(shape.TextFrame.TextRange.ParagraphFormat, block)
            return
        if kind == "shape":
            shape = document.Shapes.AddShape(
                Type=int(block.get("shape_type") or 1),
                Left=self._cm_to_points(block.get("left_cm", 2)),
                Top=self._cm_to_points(block.get("top_cm", 2)),
                Width=self._cm_to_points(block.get("width_cm", 5)),
                Height=self._cm_to_points(block.get("height_cm", 3)),
                Anchor=target,
            )
            if block.get("text"):
                shape.TextFrame.TextRange.Text = str(block["text"])
                self._com_apply_font(shape.TextFrame.TextRange.Font, block)
                self._com_apply_paragraph_format(shape.TextFrame.TextRange.ParagraphFormat, block)
            if block.get("fill"):
                shape.Fill.ForeColor.RGB = self._com_rgb(block["fill"])
            if block.get("line_color"):
                shape.Line.ForeColor.RGB = self._com_rgb(block["line_color"])
            if block.get("line_weight_pt") is not None:
                shape.Line.Weight = _clamp(block["line_weight_pt"], 0, 20, 1)
            if block.get("rotation") is not None:
                shape.Rotation = _clamp(block["rotation"], -360, 360, 0)
            return
        if kind == "chart":
            chart_type = int(block.get("chart_type") or 51)
            document.InlineShapes.AddChart2(-1, chart_type, target)
            return
        if kind == "equation":
            text = str(block.get("text") or "")
            target.Text = text
            equation_range = document.OMaths.Add(target)
            equation_range.OMaths(1).BuildUp()
            return
        if kind == "advanced_com":
            self._com_advanced(document, block, args)
            return
        raise ValueError(f"Unsupported COM block type: {kind}")

    def _com_set_header_footer(self, document, kind, spec):
        for section_index in range(1, int(document.Sections.Count) + 1):
            section = document.Sections(section_index)
            stories = section.Headers if kind == "header" else section.Footers
            story_type = {"primary": 1, "first": 2, "even": 3}.get(str(spec.get("variant") or "primary").lower(), 1)
            story = stories(story_type)
            story.LinkToPrevious = bool(spec.get("link_to_previous", False))
            story.Range.Text = str(spec.get("text") or "")
            self._com_apply_font(story.Range.Font, spec)
            self._com_apply_paragraph_format(story.Range.ParagraphFormat, spec)
            if spec.get("page_number"):
                story.Range.InsertAfter(" ")
                insertion = story.Range.Duplicate
                insertion.Collapse(0)
                story.Range.Fields.Add(Range=insertion, Type=33, PreserveFormatting=True)

    def _com_select_range(self, document, selector):
        selector = selector if isinstance(selector, dict) else {}
        if selector.get("bookmark"):
            name = str(selector["bookmark"])
            if not document.Bookmarks.Exists(name):
                raise ValueError(f"Bookmark not found: {name}")
            return document.Bookmarks(name).Range.Duplicate
        if selector.get("paragraph_index") is not None:
            index = int(selector["paragraph_index"]) + 1
            if index < 1 or index > int(document.Paragraphs.Count):
                raise IndexError("paragraph_index is out of range.")
            return document.Paragraphs(index).Range.Duplicate
        if selector.get("table_index") is not None:
            table = document.Tables(int(selector["table_index"]) + 1)
            if selector.get("row") is not None and selector.get("column") is not None:
                result = table.Cell(int(selector["row"]) + 1, int(selector["column"]) + 1).Range.Duplicate
                result.End = max(result.Start, result.End - 1)
                return result
            return table.Range.Duplicate
        if selector.get("start") is not None or selector.get("end") is not None:
            start = int(selector.get("start") or 0)
            end = int(selector.get("end") if selector.get("end") is not None else start)
            if start < 0 or end < start or end > int(document.Content.End):
                raise ValueError("Invalid character range selector.")
            return document.Range(start, end)
        find_text = str(selector.get("find") or selector.get("text") or "")
        if find_text:
            occurrence = max(1, int(selector.get("occurrence") or 1))
            search = document.Content.Duplicate
            for _index in range(occurrence):
                search.Find.ClearFormatting()
                found = search.Find.Execute(
                    FindText=find_text,
                    MatchCase=bool(selector.get("case_sensitive", False)),
                    MatchWholeWord=bool(selector.get("whole_word", False)),
                    Forward=True,
                    Wrap=0,
                )
                if not found:
                    raise ValueError(f"Text selector did not match occurrence {occurrence}: {find_text}")
                if _index + 1 < occurrence:
                    search.SetRange(search.End, document.Content.End)
            return search
        return document.Content.Duplicate

    def _com_apply_operation(self, document, operation, args):
        op = str(operation.get("op") or operation.get("type") or "").lower()
        if op in {"append", "append_blocks"}:
            blocks = operation.get("blocks") or []
            self._com_add_blocks(document, blocks, args)
            return {"op": op, "count": len(blocks)}
        if op in {"insert", "insert_blocks"}:
            target = self._com_select_range(document, operation.get("selector") or {})
            target.Collapse(1 if str(operation.get("position") or "before").lower() == "before" else 0)
            blocks = operation.get("blocks") or []
            self._com_add_blocks(document, blocks, args, target)
            return {"op": op, "count": len(blocks)}
        if op == "replace_text":
            target = self._com_select_range(document, operation.get("selector") or {})
            old = str(operation.get("find") or operation.get("old") or "")
            if not old:
                raise ValueError("replace_text requires find.")
            new = str(operation.get("replace") if "replace" in operation else operation.get("new") or "")
            replaced = target.Find.Execute(
                FindText=old, MatchCase=bool(operation.get("case_sensitive", False)),
                MatchWholeWord=bool(operation.get("whole_word", False)),
                ReplaceWith=new, Replace=2 if operation.get("replace_all", True) else 1,
                Forward=True, Wrap=0,
            )
            return {"op": op, "matched": bool(replaced)}
        if op in {"format", "format_range", "format_paragraph"}:
            target = self._com_select_range(document, operation.get("selector") or {})
            spec = operation.get("format") or operation
            self._com_apply_font(target.Font, spec)
            self._com_apply_paragraph_format(target.ParagraphFormat, spec)
            target.LanguageID = 1037
            return {"op": op, "status": "ok"}
        if op in {"delete", "delete_range", "delete_paragraph"}:
            target = self._com_select_range(document, operation.get("selector") or operation)
            target.Delete()
            return {"op": op, "status": "ok"}
        if op == "set_page_layout":
            self._com_set_page_layout(document, operation.get("page") or operation)
            return {"op": op, "status": "ok"}
        if op == "define_style":
            self._com_define_style(document, operation.get("style") or operation)
            return {"op": op, "status": "ok"}
        if op in {"set_header", "set_footer"}:
            self._com_set_header_footer(document, op.split("_")[1], operation)
            return {"op": op, "status": "ok"}
        if op == "set_properties":
            self._com_set_properties(document, operation.get("properties") or operation)
            return {"op": op, "status": "ok"}
        if op == "update_fields":
            self._com_prepare_toc_styles(document)
            document.Fields.Update()
            for index in range(1, int(document.TablesOfContents.Count) + 1):
                document.TablesOfContents(index).Update()
            return {"op": op, "status": "ok"}
        if op == "track_changes":
            document.TrackRevisions = bool(operation.get("enabled", True))
            return {"op": op, "enabled": bool(document.TrackRevisions)}
        if op == "accept_all_changes":
            document.AcceptAllRevisions()
            return {"op": op, "status": "ok"}
        if op == "reject_all_changes":
            document.RejectAllRevisions()
            return {"op": op, "status": "ok"}
        if op == "protect":
            document.Protect(
                Type=int(operation.get("protection_type") or 3),
                NoReset=True,
                Password=str(operation.get("password") or ""),
                UseIRM=False,
                EnforceStyleLock=bool(operation.get("enforce_style_lock", False)),
            )
            return {"op": op, "status": "ok"}
        if op == "unprotect":
            document.Unprotect(Password=str(operation.get("password") or ""))
            return {"op": op, "status": "ok"}
        if op in {"add_comment", "add_footnote", "add_endnote"}:
            target = self._com_select_range(document, operation.get("selector") or {})
            text = str(operation.get("text") or "")
            if op == "add_comment":
                document.Comments.Add(Range=target, Text=text)
            elif op == "add_footnote":
                document.Footnotes.Add(Range=target, Text=text)
            else:
                document.Endnotes.Add(Range=target, Text=text)
            return {"op": op, "status": "ok"}
        if op in {"add_text_box", "add_shape", "add_chart", "add_equation"}:
            block_type = op.replace("add_", "")
            self._com_add_block(document, {**operation, "type": block_type}, args)
            return {"op": op, "status": "ok"}
        if op == "insert_file":
            file_path = self._document_resolve_path(operation.get("path"), mode="read")
            target = self._com_select_range(document, operation.get("selector") or {})
            target.Collapse(0)
            target.InsertFile(FileName=file_path, ConfirmConversions=False, Link=False, Attachment=False)
            return {"op": op, "status": "ok", "path": file_path}
        if op == "advanced_com":
            return {"op": op, "result": self._com_advanced(document, operation, args)}
        raise ValueError(f"Unsupported COM edit operation: {op}")

    def _com_advanced(self, document, operation, args):
        if not args.get("allow_advanced_com"):
            raise PermissionError("advanced_com requires allow_advanced_com=true in the document_manager call.")
        root_name = str(operation.get("root") or "document").lower()
        if root_name == "document":
            target = document
        elif root_name == "application":
            target = document.Application
        elif root_name == "options":
            target = document.Application.Options
        else:
            raise ValueError("advanced_com root must be document, application, or options.")
        for step in operation.get("path") or []:
            if isinstance(step, str):
                member, index = step, None
            elif isinstance(step, dict):
                member, index = str(step.get("member") or ""), step.get("index")
            else:
                raise ValueError("advanced_com path entries must be strings or {member,index} objects.")
            self._validate_com_member(member)
            target = getattr(target, member)
            if index is not None:
                target = target.Item(index) if hasattr(target, "Item") else target(index)
        member = str(operation.get("member") or "")
        self._validate_com_member(member)
        mode = str(operation.get("mode") or "get").lower()
        if mode == "get":
            result = getattr(target, member)
        elif mode == "set":
            setattr(target, member, operation.get("value"))
            result = getattr(target, member)
        elif mode == "call":
            method = getattr(target, member)
            values = operation.get("args") or []
            named = operation.get("kwargs") or {}
            if not isinstance(values, list) or not isinstance(named, dict):
                raise ValueError("advanced_com call args must be an array and kwargs an object.")
            result = method(*values, **named)
        else:
            raise ValueError("advanced_com mode must be get, set, or call.")
        return _safe_com_result(result)

    @staticmethod
    def _validate_com_member(member):
        name = str(member or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", name):
            raise ValueError(f"Unsafe COM member name: {name!r}")
        folded = name.casefold()
        blocked_tokens = (
            "vbproject", "macro", "oleobject", "commandbar", "addins", "wordbasic",
            "dde", "organizer", "print", "sendmail", "sendfax", "followhyperlink",
            "filedialog",
        )
        if folded in _ADVANCED_COM_BLOCKED or any(token in folded for token in blocked_tokens):
            raise PermissionError(f"COM member '{name}' is blocked by Smarti document safety policy.")

    def _com_save_document(self, document, temp_path, desired_path):
        fmt = os.path.splitext(desired_path)[1].lower().lstrip(".") or "docx"
        if fmt in _WORD_FIXED_FORMATS:
            document.ExportAsFixedFormat(OutputFileName=temp_path, ExportFormat=_WORD_FIXED_FORMATS[fmt], OpenAfterExport=False)
        elif fmt in _WORD_FORMATS:
            document.SaveAs2(
                FileName=temp_path,
                FileFormat=_WORD_FORMATS[fmt],
                AddToRecentFiles=False,
                EmbedTrueTypeFonts=True,
                AddBiDiMarks=True,
            )
        else:
            raise ValueError(f"Unsupported Word output format: {fmt}")

    # --------------------- inspect / export / render ----------------------

    def _document_inspect(self, args, engine):
        path = self._document_resolve_path(args.get("path"), mode="read")
        if os.path.splitext(path)[1].lower() == ".pdf":
            return self._inspect_pdf(path, args)
        if engine == "com":
            return self._com_inspect_document(path, args)
        if os.path.splitext(path)[1].lower() != ".docx":
            raise ValueError("The independent python inspect engine supports DOCX only; use engine='com' for other Word formats.")
        return self._python_inspect_document(path, args)

    def _com_inspect_document(self, path, args):
        paragraph_limit = max(0, min(1000, int(args.get("paragraph_limit") or 200)))
        include_text = bool(args.get("include_text", True))
        with _WordComSession(args.get("timeout_seconds", 180), args.get("visible", False)) as session:
            document = session.open_document(path, read_only=True, password=str(args.get("password") or ""))
            paragraph_count = int(document.Paragraphs.Count)
            paragraphs = []
            if include_text:
                for index in range(1, min(paragraph_count, paragraph_limit) + 1):
                    paragraph = document.Paragraphs(index)
                    text = str(paragraph.Range.Text or "").rstrip("\r\x07")
                    paragraphs.append({
                        "index": index - 1,
                        "style": str(paragraph.Style),
                        "text": text[:4000],
                        "alignment": int(paragraph.Format.Alignment),
                        "reading_order": "rtl" if int(paragraph.Format.ReadingOrder) == 0 else "ltr",
                    })
            sections = []
            for index in range(1, int(document.Sections.Count) + 1):
                setup = document.Sections(index).PageSetup
                sections.append({
                    "width_pt": round(float(setup.PageWidth), 3),
                    "height_pt": round(float(setup.PageHeight), 3),
                    "orientation": "landscape" if int(setup.Orientation) == 1 else "portrait",
                    "direction": "rtl" if int(setup.SectionDirection) == 0 else "ltr",
                    "margins_pt": {
                        "top": round(float(setup.TopMargin), 3),
                        "bottom": round(float(setup.BottomMargin), 3),
                        "left": round(float(setup.LeftMargin), 3),
                        "right": round(float(setup.RightMargin), 3),
                    },
                })
            properties = {}
            for key, name in (
                ("title", "Title"), ("subject", "Subject"), ("author", "Author"),
                ("keywords", "Keywords"), ("comments", "Comments"), ("category", "Category"),
            ):
                try:
                    properties[key] = str(document.BuiltInDocumentProperties(name).Value or "")
                except Exception:
                    pass
            rtl_sample_limit = min(paragraph_count, 2000)
            rtl_count = sum(
                1 for index in range(1, rtl_sample_limit + 1)
                if int(document.Paragraphs(index).Format.ReadingOrder) == 0
            )
            result = {
                "status": "ok",
                "engine": "com",
                "path": path,
                "format": os.path.splitext(path)[1].lower().lstrip("."),
                "paragraph_count": paragraph_count,
                "table_count": int(document.Tables.Count),
                "section_count": int(document.Sections.Count),
                "inline_shape_count": int(document.InlineShapes.Count),
                "shape_count": int(document.Shapes.Count),
                "field_count": int(document.Fields.Count),
                "comment_count": int(document.Comments.Count),
                "footnote_count": int(document.Footnotes.Count),
                "endnote_count": int(document.Endnotes.Count),
                "content_control_count": int(document.ContentControls.Count),
                "rtl_paragraph_count": rtl_count,
                "rtl_count_sampled_paragraphs": rtl_sample_limit,
                "track_revisions": bool(document.TrackRevisions),
                "protection_type": int(document.ProtectionType),
                "properties": properties,
                "sections": sections,
                "paragraphs": paragraphs,
                "truncated": paragraph_count > paragraph_limit,
            }
            session.close_document(False)
            return result

    def _python_inspect_document(self, path, args):
        api = self._python_imports()
        document = api["docx"].Document(path)
        paragraph_limit = max(0, min(1000, int(args.get("paragraph_limit") or 200)))
        include_text = bool(args.get("include_text", True))
        paragraphs = []
        if include_text:
            for index, paragraph in enumerate(document.paragraphs[:paragraph_limit]):
                paragraphs.append({
                    "index": index,
                    "style": paragraph.style.name if paragraph.style else "",
                    "text": paragraph.text[:4000],
                })
        sections = []
        for section in document.sections:
            sections.append({
                "width_cm": round(section.page_width.cm, 3) if section.page_width else None,
                "height_cm": round(section.page_height.cm, 3) if section.page_height else None,
                "orientation": str(section.orientation),
                "margins_cm": {
                    "top": round(section.top_margin.cm, 3) if section.top_margin else None,
                    "bottom": round(section.bottom_margin.cm, 3) if section.bottom_margin else None,
                    "left": round(section.left_margin.cm, 3) if section.left_margin else None,
                    "right": round(section.right_margin.cm, 3) if section.right_margin else None,
                },
            })
        with zipfile.ZipFile(path, "r") as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8", "replace")
            names = archive.namelist()
        return {
            "status": "ok",
            "path": path,
            "format": os.path.splitext(path)[1].lower().lstrip("."),
            "paragraph_count": len(document.paragraphs),
            "table_count": len(document.tables),
            "section_count": len(document.sections),
            "inline_shape_count": len(document.inline_shapes),
            "comment_part": "word/comments.xml" in names,
            "footnote_part": "word/footnotes.xml" in names,
            "endnote_part": "word/endnotes.xml" in names,
            "field_count": document_xml.count("w:fldChar"),
            "rtl_paragraph_count": document_xml.count("w:bidi"),
            "sections": sections,
            "paragraphs": paragraphs,
            "truncated": len(document.paragraphs) > paragraph_limit,
        }

    @staticmethod
    def _inspect_pdf(path, args):
        try:
            import fitz
        except Exception as exc:
            raise RuntimeError("PyMuPDF is required to inspect PDF output.") from exc
        document = fitz.open(path)
        try:
            return {
                "status": "ok", "path": path, "format": "pdf", "page_count": document.page_count,
                "pages": [
                    {"page": index + 1, "width_pt": page.rect.width, "height_pt": page.rect.height, "text_chars": len(page.get_text())}
                    for index, page in enumerate(document)
                ],
            }
        finally:
            document.close()

    def _document_export(self, args, engine):
        source = self._document_resolve_path(args.get("path"), mode="read")
        fmt = str(args.get("format") or os.path.splitext(str(args.get("output_path") or ""))[1] or "pdf").lower().lstrip(".")
        output = self._document_resolve_path(
            args.get("output_path"), mode="write",
            default_name=os.path.splitext(os.path.basename(source))[0] + "." + fmt,
        )
        self._document_prepare_output(output, bool(args.get("overwrite")), backup_existing=True)
        return self._document_export_internal(source, output, fmt, engine, args)

    def _document_export_internal(self, source, output, fmt, engine, args):
        if os.path.normcase(source) == os.path.normcase(output):
            raise ValueError("Export output_path must differ from the source path.")
        temp = self._document_temp_path(output)
        try:
            if engine == "com":
                with _WordComSession(args.get("timeout_seconds", 180), args.get("visible", False)) as session:
                    document = session.open_document(source, read_only=True, password=str(args.get("password") or ""))
                    try:
                        self._com_prepare_toc_styles(document)
                        document.Fields.Update()
                    except Exception:
                        pass
                    self._com_save_document(document, temp, output)
                    session.close_document(False)
            elif engine == "libreoffice":
                produced = self._libreoffice_convert(source, os.path.dirname(temp), fmt)
                shutil.move(produced, temp)
            elif engine == "python":
                if fmt == "docx":
                    shutil.copy2(source, temp)
                elif fmt == "txt":
                    api = self._python_imports()
                    document = api["docx"].Document(source)
                    with open(temp, "w", encoding="utf-8-sig", newline="") as handle:
                        handle.write("\n".join(paragraph.text for paragraph in document.paragraphs))
                else:
                    raise ValueError(f"python engine cannot export {fmt}; use com or libreoffice.")
            else:
                raise ValueError(f"Unsupported export engine: {engine}")
            os.replace(temp, output)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        return {"status": "exported", "engine": engine, "format": fmt, "output_path": output}

    def _libreoffice_convert(self, source, output_dir, fmt):
        soffice = self._find_soffice()
        if not soffice:
            raise RuntimeError("LibreOffice/soffice is unavailable.")
        os.makedirs(output_dir, exist_ok=True)
        profile = os.path.join(tempfile.gettempdir(), f"smarti-lo-{uuid.uuid4().hex}")
        profile_url = pathlib.Path(profile).as_uri()
        command = [
            soffice, "--headless", "--nologo", "--nodefault", "--nofirststartwizard",
            f"-env:UserInstallation={profile_url}", "--convert-to", fmt, "--outdir", output_dir, source,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode != 0:
                raise RuntimeError((completed.stderr or completed.stdout or "LibreOffice conversion failed")[:2000])
            expected = os.path.join(output_dir, os.path.splitext(os.path.basename(source))[0] + "." + fmt)
            if not os.path.isfile(expected):
                candidates = sorted(pathlib.Path(output_dir).glob(f"*.{fmt}"), key=lambda item: item.stat().st_mtime, reverse=True)
                if not candidates:
                    raise RuntimeError("LibreOffice did not produce the requested output file.")
                expected = str(candidates[0])
            return expected
        finally:
            shutil.rmtree(profile, ignore_errors=True)

    def _document_render(self, args, engine):
        source = self._document_resolve_path(args.get("path"), mode="read")
        stem = os.path.splitext(os.path.basename(source))[0]
        output_dir = self._document_resolve_path(
            args.get("output_dir"), mode="write",
            default_name=f"{stem}-render-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        )
        os.makedirs(output_dir, exist_ok=True)
        if os.path.splitext(source)[1].lower() == ".pdf":
            pdf_path = source
            export_info = None
        else:
            pdf_path = os.path.join(output_dir, stem + ".pdf")
            render_engine = engine
            if render_engine == "python":
                raise ValueError("The python engine can rasterize an existing PDF but cannot render DOCX directly. Use engine='auto', 'com', or 'libreoffice'.")
            export_info = self._document_export_internal(source, pdf_path, "pdf", render_engine, {**args, "overwrite": True})
        try:
            import fitz
        except Exception as exc:
            raise RuntimeError("PyMuPDF is required to render document pages to PNG for visual QA.") from exc
        dpi = int(_clamp(args.get("dpi"), 72, 300, 144))
        page_limit = int(_clamp(args.get("page_limit"), 1, 500, 100))
        document = fitz.open(pdf_path)
        images = []
        warnings = []
        try:
            if document.page_count > page_limit:
                raise ValueError(f"Document has {document.page_count} pages; page_limit is {page_limit}.")
            matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            for index, page in enumerate(document):
                image_path = os.path.join(output_dir, f"page-{index + 1:03d}.png")
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                pixmap.save(image_path)
                text_chars = len(page.get_text().strip())
                if text_chars == 0:
                    warnings.append(f"Page {index + 1} contains no extractable text; verify that it is intentional or image-only.")
                images.append({
                    "page": index + 1, "path": image_path,
                    "width_px": pixmap.width, "height_px": pixmap.height,
                    "text_chars": text_chars,
                })
        finally:
            document.close()
        pdf_retained = True
        if export_info is not None and not bool(args.get("include_pdf", True)):
            os.remove(pdf_path)
            pdf_retained = False
            export_info = {**export_info, "output_path": None, "retained": False}
        elif export_info is not None:
            export_info = {**export_info, "retained": True}
        return {
            "status": "rendered",
            "engine": engine,
            "source_path": source,
            "pdf_path": pdf_path if pdf_retained else None,
            "pdf_retained": pdf_retained,
            "output_dir": output_dir,
            "page_count": len(images),
            "pages": images,
            "warnings": warnings,
            "visual_qa_required": True,
            "next_step": "Use screen_manager action=analyze_image on every page PNG, then edit and re-render if any visual defect is found.",
            "export": export_info,
        }

    def _document_compare(self, args):
        original_path = self._document_resolve_path(args.get("path"), mode="read")
        revised_path = self._document_resolve_path(args.get("other_path"), mode="read")
        output = self._document_resolve_path(
            args.get("output_path"), mode="write",
            default_name=f"comparison-{datetime.now().strftime('%Y%m%d-%H%M%S')}.docx",
        )
        self._document_prepare_output(output, bool(args.get("overwrite")), backup_existing=True)
        temp = self._document_temp_path(output)
        timeout = args.get("timeout_seconds", 240)
        with _WordComSession(timeout, args.get("visible", False)) as session:
            original = session.app.Documents.Open(FileName=original_path, ReadOnly=True, AddToRecentFiles=False, Visible=False)
            revised = session.app.Documents.Open(FileName=revised_path, ReadOnly=True, AddToRecentFiles=False, Visible=False)
            compared = None
            try:
                compared = session.app.CompareDocuments(
                    OriginalDocument=original,
                    RevisedDocument=revised,
                    Destination=2,
                    Granularity=1,
                    CompareFormatting=True,
                    CompareCaseChanges=True,
                    CompareWhitespace=True,
                    CompareTables=True,
                    CompareHeaders=True,
                    CompareFootnotes=True,
                    CompareTextboxes=True,
                    CompareFields=True,
                    CompareComments=True,
                    CompareMoves=True,
                    RevisedAuthor=str(args.get("revised_author") or "Smarti"),
                    IgnoreAllComparisonWarnings=True,
                )
                compared.SaveAs2(FileName=temp, FileFormat=16, AddToRecentFiles=False, EmbedTrueTypeFonts=True, AddBiDiMarks=True)
            finally:
                if compared is not None:
                    try:
                        compared.Close(SaveChanges=0)
                    except Exception:
                        pass
                try:
                    revised.Close(SaveChanges=0)
                except Exception:
                    pass
                try:
                    original.Close(SaveChanges=0)
                except Exception:
                    pass
        os.replace(temp, output)
        return {"status": "compared", "engine": "com", "output_path": output, "original_path": original_path, "revised_path": revised_path}
