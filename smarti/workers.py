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

    def _voice_sound_path(self, kind):
        names_by_kind = {
            "start": ("voice_listen_start", "voice_start", "listen_start"),
            "end": ("voice_listen_end", "voice_end", "listen_end"),
            "timeout": ("voice_listen_timeout", "voice_timeout", "listen_timeout"),
        }
        for stem in names_by_kind.get(str(kind or ""), ()):
            for ext in (".wav", ".mp3", ".ogg"):
                path = os.path.join(ASSETS_DIR, f"{stem}{ext}")
                if os.path.exists(path):
                    return path
        return ""

    def _play_fallback_voice_sound(self, kind):
        alias = {
            "start": "SystemAsterisk",
            "end": "SystemNotification",
            "timeout": "SystemExclamation",
        }.get(str(kind or ""), "SystemNotification")
        try:
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
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
        ext = os.path.splitext(path)[1].lower()
        if ext == ".wav":
            try:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            except Exception as exc:
                logging.warning(f"Voice sound failed ({path}): {exc}")
                self._play_fallback_voice_sound(kind)
                return

        def play_media_file():
            try:
                import pygame
                pygame.mixer.init()
                sound = pygame.mixer.Sound(path)
                channel = sound.play()
                while channel and channel.get_busy():
                    time.sleep(0.02)
            except Exception as exc:
                logging.warning(f"Voice media sound failed ({path}): {exc}")
                self._play_fallback_voice_sound(kind)
            finally:
                try:
                    pygame.mixer.quit()
                except Exception:
                    pass

        threading.Thread(target=play_media_file, daemon=True).start()

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
                self._play_voice_sound("start")
                self.status_signal.emit("מקשיב...")
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

class EmailConnectionTestWorker(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config, allow_insecure_ssl=False):
        super().__init__()
        self.config = copy.deepcopy(config or {})
        self.allow_insecure_ssl = bool(allow_insecure_ssl)

    def run(self):
        mail = None
        smtp = None
        try:
            cfg = self.config
            if not cfg.get("user") or not cfg.get("password"):
                raise ValueError("חסרים כתובת אימייל או סיסמת אפליקציה.")
            context = ssl._create_unverified_context() if self.allow_insecure_ssl else None
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
            self.finished_signal.emit(True, "חיבור האימייל תקין: IMAP ו-SMTP זמינים.")
        except Exception as e:
            self.finished_signal.emit(False, str(e))
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


__all__ = [name for name in globals() if not name.startswith("__")]
