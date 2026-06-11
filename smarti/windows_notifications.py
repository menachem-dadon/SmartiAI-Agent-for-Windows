"""Windows toast notifications and polished in-app fallback popups."""
from .common import *
from .ui_styles import *
from .ui_controls import apply_soft_shadow

try:
    import winreg
except Exception:
    winreg = None
try:
    from ctypes import wintypes
except Exception:
    wintypes = None

from PyQt6.QtCore import QObject


def ensure_windows_notification_identity():
    if platform.system() != "Windows" or winreg is None:
        return False
    try:
        icon_path = os.path.join(ASSETS_DIR, "smarti.ico")
        key_path = f"SOFTWARE\\Classes\\AppUserModelId\\{SMARTI_APP_AUMID}"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, SMARTI_APP_DISPLAY_NAME)
            if os.path.exists(icon_path):
                winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(Path(icon_path).resolve()))
        return True
    except Exception as exc:
        logging.warning("Could not register SmartiAI notification identity: %s", exc)
        return False


class TaskbarAttentionController(QObject):
    FLASHW_STOP = 0x00000000
    FLASHW_TRAY = 0x00000002
    FLASHW_TIMERNOFG = 0x0000000C

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._flashing = False

    def request_attention(self):
        if platform.system() != "Windows" or wintypes is None:
            return False
        if not self.window or self.window.isActiveWindow():
            return False
        hwnd = self._window_handle()
        if not hwnd:
            return False
        if self._flash(hwnd, self.FLASHW_TRAY | self.FLASHW_TIMERNOFG):
            self._flashing = True
            return True
        return False

    def stop(self):
        if not self._flashing or platform.system() != "Windows" or wintypes is None:
            self._flashing = False
            return False
        hwnd = self._window_handle()
        self._flashing = False
        if not hwnd:
            return False
        return self._flash(hwnd, self.FLASHW_STOP)

    def _window_handle(self):
        try:
            return int(self.window.winId())
        except Exception:
            return 0

    def _flash(self, hwnd, flags):
        class FLASHWINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("hwnd", wintypes.HWND),
                ("dwFlags", wintypes.DWORD),
                ("uCount", wintypes.UINT),
                ("dwTimeout", wintypes.DWORD),
            ]

        info = FLASHWINFO(
            ctypes.sizeof(FLASHWINFO),
            hwnd,
            flags,
            0,
            0,
        )
        try:
            return bool(ctypes.windll.user32.FlashWindowEx(ctypes.byref(info)))
        except Exception as exc:
            logging.warning("Taskbar flashing failed: %s", exc)
            return False


class SmartiGlassToast(QWidget):
    reply_submitted = pyqtSignal(str)
    permission_answered = pyqtSignal(object)
    activated = pyqtSignal()
    dismissed = pyqtSignal()

    def __init__(
        self,
        title,
        body,
        *,
        kind="notice",
        reply=False,
        permission=False,
        parent=None,
    ):
        super().__init__(parent)
        self.kind = kind
        self.reply_enabled = bool(reply)
        self.permission_enabled = bool(permission)
        self._closed_by_action = False
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setFixedWidth(430)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("SmartiGlassToastCard")
        apply_soft_shadow(card, blur=32, y=10, alpha=44)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        close_btn = QPushButton("x")
        close_btn.setObjectName("SmartiGlassClose")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self._close_clicked)
        header.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignLeft)
        header.addStretch()

        app_name = QLabel(SMARTI_APP_DISPLAY_NAME)
        app_name.setObjectName("SmartiGlassAppName")
        header.addWidget(app_name, 0, Qt.AlignmentFlag.AlignVCenter)

        icon = QLabel()
        icon.setObjectName("SmartiGlassAppIcon")
        icon.setFixedSize(24, 24)
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(
                24, 24,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon.setPixmap(pix)
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        logo = QLabel()
        logo.setObjectName("SmartiGlassBodyIcon")
        logo.setFixedSize(52, 52)
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(
                52, 52,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        content_row.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        title_lbl = QLabel(str(title or SMARTI_APP_DISPLAY_NAME))
        title_lbl.setObjectName("SmartiGlassTitle")
        title_lbl.setWordWrap(True)
        body_lbl = QLabel(str(body or ""))
        body_lbl.setObjectName("SmartiGlassBody")
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_col.addWidget(title_lbl)
        text_col.addWidget(body_lbl)
        content_row.addLayout(text_col, 1)
        layout.addLayout(content_row)

        if self.reply_enabled:
            reply_row = QHBoxLayout()
            reply_row.setSpacing(8)
            self.reply_edit = QLineEdit()
            self.reply_edit.setObjectName("SmartiGlassReply")
            self.reply_edit.setPlaceholderText("כתוב תגובה")
            self.reply_edit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            self.reply_edit.returnPressed.connect(self._submit_reply)
            send_btn = QPushButton("שלח")
            send_btn.setObjectName("SmartiGlassPrimary")
            send_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            send_btn.clicked.connect(self._submit_reply)
            reply_row.addWidget(send_btn)
            reply_row.addWidget(self.reply_edit, 1)
            layout.addLayout(reply_row)

        if self.permission_enabled:
            actions = QHBoxLayout()
            actions.setSpacing(8)
            actions.addStretch()
            reject_btn = QPushButton("דחה")
            reject_btn.setObjectName("SmartiGlassReject")
            reject_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            reject_btn.clicked.connect(lambda: self._answer_permission(False))
            accept_btn = QPushButton("אשר")
            accept_btn.setObjectName("SmartiGlassPrimary")
            accept_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            accept_btn.clicked.connect(lambda: self._answer_permission(True))
            actions.addWidget(reject_btn)
            actions.addWidget(accept_btn)
            layout.addLayout(actions)

        self.setStyleSheet(self._stylesheet())

    def _stylesheet(self):
        if CURRENT_THEME == "dark":
            glass = GLASS_STRONG_COLOR
            line = SOFT_LINE_COLOR
            field = GLASS_COLOR
        else:
            glass = GLASS_STRONG_COLOR
            line = SOFT_LINE_COLOR
            field = GLASS_COLOR
        return f"""
            QFrame#SmartiGlassToastCard {{
                background: {glass};
                border: 1px solid {line};
                border-radius: 20px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {TEXT_COLOR};
                font-family: 'Segoe UI', Arial;
            }}
            QLabel#SmartiGlassAppName {{
                color: {MUTED_TEXT_COLOR};
                font-size: 12px;
                font-weight: 700;
            }}
            QLabel#SmartiGlassTitle {{
                color: {TEXT_COLOR};
                font-size: 15px;
                font-weight: 800;
            }}
            QLabel#SmartiGlassBody {{
                color: {MUTED_TEXT_COLOR};
                font-size: 13px;
                line-height: 1.35;
            }}
            QLabel#SmartiGlassBodyIcon {{
                background: {ACCENT_TINT};
                border: 1px solid {line};
                border-radius: 16px;
            }}
            QLineEdit#SmartiGlassReply {{
                background: {field};
                color: {FIELD_TEXT_COLOR};
                border: 1px solid {line};
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 13px;
                selection-background-color: {ACCENT_TINT_STRONG};
            }}
            QLineEdit#SmartiGlassReply:focus {{
                background: {FIELD_HOVER_COLOR};
                border-color: {ACCENT_PINK_COLOR};
            }}
            QPushButton {{
                font-family: 'Segoe UI', Arial;
                border: 1px solid transparent;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: 800;
            }}
            QPushButton#SmartiGlassPrimary {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_COLOR}, stop:0.52 {ACCENT_PINK_COLOR}, stop:1 {ACCENT_SECONDARY_COLOR});
                color: {ACCENT_TEXT_COLOR};
            }}
            QPushButton#SmartiGlassPrimary:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {BRAND_ACCENT_COLOR}, stop:0.52 {BRAND_PINK_COLOR}, stop:1 {BRAND_SECONDARY_COLOR});
            }}
            QPushButton#SmartiGlassReject {{
                background: {field};
                color: {TEXT_COLOR};
                border-color: {line};
            }}
            QPushButton#SmartiGlassReject:hover,
            QPushButton#SmartiGlassClose:hover {{
                background: {HOVER_TINT};
            }}
            QPushButton#SmartiGlassClose {{
                background: transparent;
                color: {MUTED_TEXT_COLOR};
                padding: 0;
                font-size: 13px;
                font-weight: 700;
            }}
        """

    def show_toast(self):
        self.adjustSize()
        self._move_to_notification_corner()
        self.show()
        self.raise_()
        if self.reply_enabled and hasattr(self, "reply_edit"):
            self.reply_edit.setFocus(Qt.FocusReason.OtherFocusReason)

    def _move_to_notification_corner(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        margin = 16
        self.resize(min(self.width(), available.width() - margin * 2), self.height())
        self.move(
            available.right() - self.width() - margin,
            available.bottom() - self.height() - margin,
        )

    def _submit_reply(self):
        text = self.reply_edit.text().strip() if hasattr(self, "reply_edit") else ""
        if not text:
            return
        self._closed_by_action = True
        self.hide()
        self.reply_submitted.emit(text)
        self.deleteLater()

    def _answer_permission(self, approved):
        self._closed_by_action = True
        self.hide()
        self.permission_answered.emit(bool(approved))
        self.deleteLater()

    def _close_clicked(self):
        if self.permission_enabled and not self._closed_by_action:
            self.permission_answered.emit(False)
        else:
            self.dismissed.emit()
        self.hide()
        self.deleteLater()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.reply_enabled and not self.permission_enabled:
            self.activated.emit()
            self.hide()
            self.deleteLater()
            return
        super().mouseReleaseEvent(event)


class WindowsNotificationCenter(QObject):
    reply_requested = pyqtSignal(str)
    activate_requested = pyqtSignal()
    attention_cleared = pyqtSignal()
    conversation_switch_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._native_ready = None
        self._native_error = ""
        self._toaster = None
        self._api = None
        self._native_toasts = []
        self._fallback_toasts = []

    def available_status(self):
        return "native" if self._ensure_native() else f"fallback: {self._native_error or 'native unavailable'}"

    def _ensure_native(self):
        if self._native_ready is not None:
            return self._native_ready
        self._native_ready = False
        if platform.system() != "Windows":
            self._native_error = "not Windows"
            return False
        try:
            ensure_windows_notification_identity()
            from windows_toasts import (
                InteractableWindowsToaster,
                Toast,
                ToastAudio,
                ToastButton,
                ToastButtonColour,
                ToastDisplayImage,
                ToastDuration,
                ToastImagePosition,
                ToastInputTextBox,
                ToastScenario,
                AudioSource,
            )

            self._api = {
                "Toast": Toast,
                "ToastAudio": ToastAudio,
                "ToastButton": ToastButton,
                "ToastButtonColour": ToastButtonColour,
                "ToastDisplayImage": ToastDisplayImage,
                "ToastDuration": ToastDuration,
                "ToastImagePosition": ToastImagePosition,
                "ToastInputTextBox": ToastInputTextBox,
                "ToastScenario": ToastScenario,
                "AudioSource": AudioSource,
            }
            self._toaster = InteractableWindowsToaster(
                SMARTI_APP_DISPLAY_NAME,
                notifierAUMID=SMARTI_APP_AUMID,
            )
            self._native_ready = True
        except Exception as exc:
            self._native_error = str(exc)
            logging.warning("Native Windows toast notifications are unavailable: %s", exc)
        return self._native_ready

    def _plain_text(self, text, limit=360):
        cleaned = html.unescape(str(text or ""))
        cleaned = re.sub(r"```.*?```", "קטע קוד", cleaned, flags=re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > limit:
            cleaned = cleaned[: max(0, limit - 3)].rstrip() + "..."
        return cleaned

    def _logo_image(self):
        if not self._api:
            return None
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if not os.path.exists(logo_path):
            return None
        try:
            return self._api["ToastDisplayImage"].fromPath(
                logo_path,
                altText=SMARTI_APP_DISPLAY_NAME,
                position=self._api["ToastImagePosition"].AppLogo,
                circleCrop=False,
            )
        except Exception:
            return None

    def _track_native_toast(self, toast):
        self._native_toasts.append(toast)

        def cleanup():
            try:
                self._native_toasts.remove(toast)
            except ValueError:
                pass

        QTimer.singleShot(300000, cleanup)
        return cleanup

    def _event_arguments(self, event_args):
        return str(getattr(event_args, "arguments", "") or getattr(event_args, "argument", "") or "")

    def _event_inputs(self, event_args):
        inputs = getattr(event_args, "inputs", None)
        if inputs is None:
            inputs = getattr(event_args, "input", None)
        if inputs is None:
            return {}
        if isinstance(inputs, dict):
            return inputs
        try:
            return dict(inputs)
        except Exception:
            values = {}
            for key in ("replyText", "snoozeTime"):
                try:
                    values[key] = inputs[key]
                except Exception:
                    try:
                        values[key] = inputs.lookup(key)
                    except Exception:
                        pass
            return values

    def _action_name(self, arguments):
        query = str(arguments or "").replace("&amp;", "&").lstrip("?")
        try:
            parsed = urllib.parse.parse_qs(query)
            if parsed.get("action"):
                return parsed["action"][0]
        except Exception:
            pass
        if "action=" in query:
            return query.split("action=", 1)[1].split("&", 1)[0]
        return query

    def show_response(self, response):
        title = "סמארטי השיב"
        body = self._plain_text(response, 360) or "התשובה מוכנה."
        if self._ensure_native():
            try:
                api = self._api
                reply_input = api["ToastInputTextBox"]("replyText", "", "כתוב תגובה")
                toast = api["Toast"](
                    [title, body],
                    duration=api["ToastDuration"].Long,
                    audio=api["ToastAudio"](api["AudioSource"].IM),
                    group="smartiai-responses",
                    expiration_time=datetime.now() + timedelta(minutes=30),
                )
                logo = self._logo_image()
                if logo:
                    toast.AddImage(logo)
                toast.AddInput(reply_input)
                toast.AddAction(api["ToastButton"](
                    "שלח",
                    "action=reply",
                    relatedInput=reply_input,
                    colour=api["ToastButtonColour"].Green,
                ))

                cleanup = self._track_native_toast(toast)

                def activated(event_args):
                    arguments = self._event_arguments(event_args)
                    action = self._action_name(arguments)
                    inputs = self._event_inputs(event_args)
                    reply = str(inputs.get("replyText") or inputs.get("reply") or "").strip()
                    if action == "reply" and reply:
                        self.attention_cleared.emit()
                        self.reply_requested.emit(reply)
                    else:
                        self.attention_cleared.emit()
                        self.activate_requested.emit()
                    cleanup()

                def dismissed(_event_args):
                    self.attention_cleared.emit()
                    cleanup()

                toast.on_activated = activated
                toast.on_dismissed = dismissed
                self._toaster.show_toast(toast)
                return True
            except Exception as exc:
                logging.warning("Native response toast failed: %s", exc)
        self._show_fallback(title, body, reply=True)
        return False

    def show_permission_request(self, title, details, risk="medium", callback=None):
        heading = "בקשת הרשאה"
        body = self._plain_text(f"{title}\n{details}", 620) or str(title or heading)
        if self._ensure_native():
            try:
                api = self._api
                toast = api["Toast"](
                    [heading, body],
                    duration=api["ToastDuration"].Long,
                    scenario=api["ToastScenario"].Reminder,
                    audio=api["ToastAudio"](api["AudioSource"].Reminder),
                    group="smartiai-permissions",
                    expiration_time=datetime.now() + timedelta(minutes=20),
                )
                logo = self._logo_image()
                if logo:
                    toast.AddImage(logo)
                toast.AddAction(api["ToastButton"](
                    "דחה",
                    "action=deny",
                    colour=api["ToastButtonColour"].Red,
                ))
                toast.AddAction(api["ToastButton"](
                    "אשר",
                    "action=approve",
                    colour=api["ToastButtonColour"].Green,
                ))
                settled = {"done": False}
                cleanup = self._track_native_toast(toast)

                def settle(value):
                    if settled["done"]:
                        return
                    settled["done"] = True
                    cleanup()
                    self.attention_cleared.emit()
                    if callback:
                        callback(value)

                def activated(event_args):
                    action = self._action_name(self._event_arguments(event_args))
                    if action == "approve":
                        settle(True)
                    elif action == "deny":
                        settle(False)
                    else:
                        self.activate_requested.emit()
                        settle(None)

                def dismissed(_event_args):
                    settle(False)

                toast.on_activated = activated
                toast.on_dismissed = dismissed
                self._toaster.show_toast(toast)
                return True
            except Exception as exc:
                logging.warning("Native permission toast failed: %s", exc)
        self._show_fallback(heading, body, permission=True, permission_callback=callback)
        return True

    def show_notice(self, title, body, *, kind="default", open_button=True):
        title = self._plain_text(title, 90) or SMARTI_APP_DISPLAY_NAME
        body = self._plain_text(body, 520) or "יש עדכון מסמארטי."
        if self._ensure_native():
            try:
                api = self._api
                scenario = api["ToastScenario"].Default
                audio_source = api["AudioSource"].Default
                looping = False
                if kind == "reminder":
                    scenario = api["ToastScenario"].Reminder
                    audio_source = api["AudioSource"].Reminder
                elif kind == "alarm":
                    scenario = api["ToastScenario"].Alarm
                    audio_source = api["AudioSource"].Alarm
                    looping = True
                elif kind == "important" and hasattr(api["ToastScenario"], "Important"):
                    scenario = api["ToastScenario"].Important
                toast = api["Toast"](
                    [title, body],
                    duration=api["ToastDuration"].Long,
                    scenario=scenario,
                    audio=api["ToastAudio"](audio_source, looping=looping),
                    group=f"smartiai-{kind}",
                    expiration_time=datetime.now() + timedelta(hours=4),
                )
                logo = self._logo_image()
                if logo:
                    toast.AddImage(logo)
                if open_button:
                    toast.AddAction(api["ToastButton"]("פתח את סמארטי", "action=open"))
                cleanup = self._track_native_toast(toast)

                def activated(_event_args):
                    self.attention_cleared.emit()
                    self.activate_requested.emit()
                    cleanup()

                def dismissed(_event_args):
                    self.attention_cleared.emit()
                    cleanup()

                toast.on_activated = activated
                toast.on_dismissed = dismissed
                self._toaster.show_toast(toast)
                return True
            except Exception as exc:
                logging.warning("Native notice toast failed: %s", exc)
        self._show_fallback(title, body)
        return False

    def show_background_task_notification(self, title, body, conversation_id):
        title = self._plain_text(title, 90) or SMARTI_APP_DISPLAY_NAME
        body = self._plain_text(body, 520) or "ההרצה הסתיימה בהצלחה."
        if self._ensure_native():
            try:
                api = self._api
                toast = api["Toast"](
                    [title, body],
                    duration=api["ToastDuration"].Long,
                    audio=api["ToastAudio"](api["AudioSource"].Default),
                    group="smartiai-background",
                    expiration_time=datetime.now() + timedelta(hours=4),
                )
                logo = self._logo_image()
                if logo:
                    toast.AddImage(logo)
                if conversation_id:
                    toast.AddAction(api["ToastButton"]("פתח שיחה", f"action=switch&id={conversation_id}"))
                cleanup = self._track_native_toast(toast)

                def activated(event_args):
                    arguments = self._event_arguments(event_args)
                    self.attention_cleared.emit()
                    if "action=switch" in arguments and conversation_id:
                        self.conversation_switch_requested.emit(conversation_id)
                    else:
                        self.activate_requested.emit()
                    cleanup()

                def dismissed(_event_args):
                    self.attention_cleared.emit()
                    cleanup()

                toast.on_activated = activated
                toast.on_dismissed = dismissed
                self._toaster.show_toast(toast)
                return True
            except Exception as exc:
                logging.warning("Native background notification failed: %s", exc)
        
        # Fallback GlassToast
        toast = SmartiGlassToast(title, body)
        self._fallback_toasts.append(toast)
        def cleanup():
            try: self._fallback_toasts.remove(toast)
            except ValueError: pass
        toast.destroyed.connect(lambda *_: cleanup())
        toast.activated.connect(lambda: (self.attention_cleared.emit(), self.conversation_switch_requested.emit(conversation_id) if conversation_id else self.activate_requested.emit()))
        toast.dismissed.connect(self.attention_cleared)
        toast.show_toast()
        return False

    def _show_fallback(self, title, body, *, reply=False, permission=False, permission_callback=None):
        toast = SmartiGlassToast(title, body, reply=reply, permission=permission)
        self._fallback_toasts.append(toast)

        def cleanup():
            try:
                self._fallback_toasts.remove(toast)
            except ValueError:
                pass

        toast.destroyed.connect(lambda *_: cleanup())
        toast.reply_submitted.connect(lambda text: (self.attention_cleared.emit(), self.reply_requested.emit(text)))
        toast.activated.connect(lambda: (self.attention_cleared.emit(), self.activate_requested.emit()))
        toast.dismissed.connect(self.attention_cleared)
        if permission:
            toast.permission_answered.connect(lambda value: (self.attention_cleared.emit(), permission_callback(value) if permission_callback else None))
        toast.show_toast()
        return toast
