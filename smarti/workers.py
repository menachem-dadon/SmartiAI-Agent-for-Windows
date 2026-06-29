"""Qt worker threads for agent, speech, TTS, and model loading."""
from .common import *

# ==========================================
# תהליכי רקע (QThreads) ל-GUI למניעת קפיאות
# ==========================================
class AgentWorker(QThread):
    finished_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    ask_confirm_signal = pyqtSignal(str, str, str)
    api_key_required_signal = pyqtSignal(str, str, str, str, str)
    step_signal = pyqtSignal(object)

    def __init__(self, core, user_text, attachments=None):
        super().__init__()
        self.core = core
        self.user_text = user_text
        self.attachments = attachments or []
        self.confirm_event = threading.Event()
        self.confirm_result = False
        self.api_key_event = threading.Event()
        self.api_key_result = ""

    def ask_user_gui(self, title, text, risk="medium"):
        self.confirm_result = False
        self.confirm_event.clear()
        self.ask_confirm_signal.emit(title, text, str(risk or "medium"))
        while not self.confirm_event.wait(0.1):
            if self.core._is_cancel_requested():
                return False
        return self.confirm_result

    def ask_api_key_gui(self, secret_key, provider_label, title, message, help_url):
        self.api_key_result = ""
        self.api_key_event.clear()
        self.api_key_required_signal.emit(secret_key, provider_label, title, message, help_url)
        while not self.api_key_event.wait(0.1):
            if self.core._is_cancel_requested():
                return ""
        return self.api_key_result

    def run(self):
        self.core.set_callbacks(
            status_cb=lambda msg: self.status_signal.emit(msg), 
            print_cb=self.core.print_callback,
            ask_user_cb=self.ask_user_gui,
            step_cb=lambda msg: self.step_signal.emit(msg),
            api_key_cb=self.ask_api_key_gui
        )
        try:
            response = self.core.send_message(self.user_text, attachments=self.attachments)
        except Exception as e:
            logging.exception("Agent worker crashed unexpectedly.")
            self.core._recover_after_agent_crash()
            response = f"ERROR_USER: אירעה תקלה פנימית במהלך ביצוע הפעולה. הפרטים נשמרו בלוגים לצורך בדיקה.\n{e}"
        self.finished_signal.emit(response)

class VoiceWorker(QThread):
    finished_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    _sound_lock = threading.Lock()

    def __init__(self, settings=None):
        super().__init__()
        self.settings = copy.deepcopy(settings or {})
        self._cancel_requested = threading.Event()

    def request_stop(self):
        self._cancel_requested.set()

    def _setting_float(self, key, default, minimum, maximum):
        try:
            value = float(self.settings.get(key, default))
        except Exception:
            value = default
        return max(minimum, min(maximum, value))

    def _setting_int(self, key, default, minimum, maximum):
        try:
            value = int(float(self.settings.get(key, default)))
        except Exception:
            value = default
        return max(minimum, min(maximum, value))

    def _energy_threshold_from_sensitivity(self):
        sensitivity = self._setting_int("voice_sensitivity", 70, 1, 100)
        ratio = (100 - sensitivity) / 99.0
        return int(50 + (4000 - 50) * (ratio ** 2.3))

    def _voice_sound_path(self, kind, extensions=(".mp3", ".wav")):
        names_by_kind = {
            "start": ("voice_listen_start", "voice_start", "listen_start"),
            "end": ("voice_listen_end", "voice_end", "listen_end"),
            "timeout": ("voice_listen_timeout", "voice_timeout", "listen_timeout"),
        }
        for stem in names_by_kind.get(str(kind or ""), ()):
            for ext in extensions:
                path = os.path.join(ASSETS_DIR, f"{stem}{ext}")
                if os.path.exists(path):
                    return path
        return ""

    def _mci_send(self, command):
        result = ctypes.windll.winmm.mciSendStringW(str(command), None, 0, None)
        if result:
            buffer = ctypes.create_unicode_buffer(256)
            try:
                ctypes.windll.winmm.mciGetErrorStringW(result, buffer, len(buffer))
            except Exception:
                pass
            message = buffer.value or f"MCI error {result}"
            raise RuntimeError(message)

    def _play_mp3_voice_sound(self, path):
        alias = f"smarti_voice_{uuid.uuid4().hex}"
        opened = False
        try:
            self._mci_send(f'open "{path}" type mpegvideo alias {alias}')
            opened = True
            self._mci_send(f"play {alias} wait")
        finally:
            if opened:
                try:
                    self._mci_send(f"close {alias}")
                except Exception:
                    pass

    def _play_fallback_voice_sound(self, kind):
        alias = {
            "start": "SystemAsterisk",
            "end": "SystemNotification",
            "timeout": "SystemExclamation",
        }.get(str(kind or ""), "SystemNotification")
        try:
            with self._sound_lock:
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_NOSTOP)
        except Exception:
            try:
                winsound.MessageBeep()
            except Exception:
                pass

    def _play_voice_sound(self, kind):
        if not bool(self.settings.get("voice_beep_enabled", True)):
            return
        path = self._voice_sound_path(kind)
        if not path:
            self._play_fallback_voice_sound(kind)
            return
        try:
            with self._sound_lock:
                if os.path.splitext(path)[1].lower() == ".mp3":
                    self._play_mp3_voice_sound(path)
                else:
                    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_NOSTOP)
        except Exception as exc:
            logging.warning(f"Voice sound failed ({path}): {exc}")
            wav_path = self._voice_sound_path(kind, extensions=(".wav",))
            if wav_path and wav_path != path:
                try:
                    with self._sound_lock:
                        winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_NOSTOP)
                    return
                except Exception as wav_exc:
                    logging.warning(f"Voice WAV fallback failed ({wav_path}): {wav_exc}")
            self._play_fallback_voice_sound(kind)

    def _play_voice_sound_background(self, kind):
        if not bool(self.settings.get("voice_beep_enabled", True)):
            return
        threading.Thread(
            target=lambda: self._play_voice_sound(kind),
            name=f"SmartiVoiceSound-{kind}",
            daemon=True,
        ).start()

    def run(self):
        if not SPEECH_INSTALLED:
            self.finished_signal.emit("")
            return
        try:
            import speech_recognition as sr
        except ImportError:
            self.finished_signal.emit("")
            return
        r = sr.Recognizer()
        r.energy_threshold = self._energy_threshold_from_sensitivity()
        r.dynamic_energy_threshold = bool(self.settings.get("voice_dynamic_energy_threshold", False))
        r.pause_threshold = self._setting_float("voice_pause_threshold", 0.8, 0.3, 5.0)
        r.non_speaking_duration = max(0.1, min(1.0, r.pause_threshold / 2.0))
        listen_timeout = self._setting_float("voice_listen_timeout", 6, 1, 30)
        ambient_duration = self._setting_float("voice_ambient_noise_duration", 0.0, 0.0, 3.0)
        try:
            self.status_signal.emit("פותח מיקרופון...")
            with sr.Microphone() as source:
                if self._cancel_requested.is_set():
                    self.finished_signal.emit("")
                    return
                if ambient_duration > 0:
                    self.status_signal.emit("מכוון רעש רקע...")
                    r.adjust_for_ambient_noise(source, duration=ambient_duration)
                if self._cancel_requested.is_set():
                    self.finished_signal.emit("")
                    return
                self.status_signal.emit("מקשיב...")
                self._play_voice_sound_background("start")
                try: audio = r.listen(source, timeout=listen_timeout)
                except sr.WaitTimeoutError:
                    self._play_voice_sound("timeout")
                    self.finished_signal.emit("")
                    return
                if self._cancel_requested.is_set():
                    self.finished_signal.emit("")
                    return
                self._play_voice_sound("end")
                self.status_signal.emit("מתמלל...")
                text = r.recognize_google(audio, language="he-IL").replace("סמרטי", "סמארטי").replace("סמארט", "סמארטי")
                if self._cancel_requested.is_set():
                    text = ""
                self.finished_signal.emit(text)
        except Exception:
            logging.exception("Voice recognition failed.")
            self.finished_signal.emit("")

class TTSWorker(QThread):
    def __init__(self, core, text):
        super().__init__()
        self.core = core
        self.text = text
    def run(self): self.core.speak_text(self.text)

class FetchModelsWorker(QThread):
    finished_signal = pyqtSignal(list)
    def __init__(self, provider, api_key, url, allow_insecure_ssl=False):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.url = url
        self.allow_insecure_ssl = bool(allow_insecure_ssl)

    def _request_kwargs(self):
        return ssl_request_kwargs(self.allow_insecure_ssl)

    def run(self):
        models, _, _ = fetch_text_models_for_provider(
            self.provider,
            self.api_key,
            self.url,
            self.allow_insecure_ssl,
            validate_key=False,
        )
        self.finished_signal.emit(models)

class ApiKeyValidationWorker(QThread):
    finished_signal = pyqtSignal(str, str, bool, str, list)

    def __init__(self, provider, api_key, url, allow_insecure_ssl=False):
        super().__init__()
        self.provider = normalize_provider_name(provider)
        self.api_key = sanitize_secret_value(api_key)
        self.url = url
        self.allow_insecure_ssl = bool(allow_insecure_ssl)

    def run(self):
        models, ok, message = fetch_text_models_for_provider(
            self.provider,
            self.api_key,
            self.url,
            self.allow_insecure_ssl,
            validate_key=True,
        )
        self.finished_signal.emit(self.provider, self.api_key, bool(ok), str(message or ""), models)


class CodexSignInWorker(QThread):
    """Keep the official Codex browser login and status checks off the GUI thread."""

    finished_signal = pyqtSignal(str, str, str)

    def __init__(self, action):
        super().__init__()
        self.action = str(action or "status")

    def run(self):
        from .codex_signin import CodexSignInProvider

        provider = CodexSignInProvider(USER_DATA_DIR)
        try:
            if self.action == "login":
                result = provider.login()
            elif self.action == "check":
                result = provider.check_connection()
            elif self.action == "logout":
                result = provider.logout()
            else:
                result = provider.connection_status()
            self.finished_signal.emit(self.action, result.state, result.message)
        except Exception as exc:
            logging.exception("Codex sign-in worker failed.")
            self.finished_signal.emit(self.action, "unavailable", str(exc))

def test_email_connection(config, allow_insecure_ssl=False):
    """Test IMAP and SMTP without sending, changing, or reading a message."""
    mail = None
    smtp = None
    try:
        cfg = copy.deepcopy(config or {})
        if not cfg.get("user") or not cfg.get("password"):
            raise ValueError("חסרים כתובת אימייל או סיסמת אפליקציה.")
        context = ssl._create_unverified_context() if allow_insecure_ssl else None
        if cfg.get("imap_ssl", True):
            if context:
                mail = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], timeout=30, ssl_context=context)
            else:
                mail = imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], timeout=30)
        else:
            mail = imaplib.IMAP4(cfg["imap_host"], cfg["imap_port"], timeout=30)
        mail.login(cfg["user"], cfg["password"])
        status, data = mail.list()
        if status != "OK":
            raise RuntimeError(f"IMAP list failed: {data}")
        try:
            mail.logout()
        except Exception:
            pass
        mail = None

        if cfg["smtp_ssl"]:
            if context is not None:
                smtp = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=30, context=context)
            else:
                smtp = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=30)
        else:
            smtp = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=30)
            smtp.ehlo()
            if cfg["smtp_starttls"]:
                if context is not None:
                    smtp.starttls(context=context)
                else:
                    smtp.starttls()
                smtp.ehlo()
        smtp.login(cfg["user"], cfg["password"])
        return True, "חיבור האימייל תקין: IMAP ו-SMTP זמינים."
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            if mail is not None:
                mail.logout()
        except Exception:
            pass
        try:
            if smtp is not None:
                smtp.quit()
        except Exception:
            pass


class EmailConnectionTestWorker(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config, allow_insecure_ssl=False):
        super().__init__()
        self.config = copy.deepcopy(config or {})
        self.allow_insecure_ssl = bool(allow_insecure_ssl)

    def run(self):
        ok, message = test_email_connection(self.config, self.allow_insecure_ssl)
        self.finished_signal.emit(ok, message)


class DiagnosticCheckWorker(QThread):
    """Run Smarti Diagnostic checks outside the GUI event loop."""

    progress_signal = pyqtSignal(int, int, str)
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(list, str, bool)
    failed_signal = pyqtSignal(str)

    def __init__(self, core, include_network=False):
        super().__init__()
        self.core = core
        self.include_network = bool(include_network)
        self._doctor = None

    def request_stop(self):
        if self._doctor is not None:
            self._doctor.request_stop()

    def run(self):
        try:
            # Local import avoids a workers <-> doctor module import cycle.
            from .doctor import SmartiDiagnostic

            self._doctor = SmartiDiagnostic(self.core)
            results = self._doctor.run(
                include_network=self.include_network,
                progress_callback=lambda current, total, label: self.progress_signal.emit(current, total, label),
                result_callback=lambda result: self.result_signal.emit(result.to_dict()),
            )
            self.finished_signal.emit(
                [result.to_dict() for result in results],
                self._doctor.log_path,
                self._doctor._cancelled(),
            )
        except Exception as exc:
            logging.exception("Diagnostic worker failed.")
            self.failed_signal.emit(str(exc))
        finally:
            self._doctor = None


class DiagnosticRepairWorker(QThread):
    """Perform an already-approved Smarti Diagnostic repair away from the GUI thread."""

    finished_signal = pyqtSignal(str)
    failed_signal = pyqtSignal(str)

    def __init__(self, core, action_id):
        super().__init__()
        self.core = core
        self.action_id = str(action_id or "")

    def run(self):
        try:
            from .doctor import SmartiDiagnostic

            message = SmartiDiagnostic(self.core).perform_repair(self.action_id)
            self.finished_signal.emit(str(message or "התיקון הסתיים."))
        except Exception as exc:
            logging.exception("Diagnostic repair failed.")
            self.failed_signal.emit(str(exc))


__all__ = [name for name in globals() if not name.startswith("__")]
