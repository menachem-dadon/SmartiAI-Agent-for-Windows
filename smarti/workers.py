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
                if ambient_duration > 0:
                    self.status_signal.emit("מכוון רעש רקע...")
                    r.adjust_for_ambient_noise(source, duration=ambient_duration)
                if bool(self.settings.get("voice_beep_enabled", False)):
                    try: winsound.Beep(1000, 90)
                    except: pass
                self.status_signal.emit("מקשיב...")
                try: audio = r.listen(source, timeout=listen_timeout)
                except sr.WaitTimeoutError:
                    self.finished_signal.emit("")
                    return
                if bool(self.settings.get("voice_beep_enabled", False)):
                    try: winsound.Beep(800, 90)
                    except: pass
                self.status_signal.emit("מתמלל...")
                text = r.recognize_google(audio, language="he-IL").replace("סמרטי", "סמארטי").replace("סמארט", "סמארטי")
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


__all__ = [name for name in globals() if not name.startswith("__")]
