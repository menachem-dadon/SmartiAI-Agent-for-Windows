"""Application entry point for Smarti."""
from .ui_common import *
from .ui_styles import *
from .core import SmartiCore
from .chat import ChatWindow, AnimatedSplash
from .legal import LegalAgreementDialog, raw_settings_have_current_legal_acceptance, record_legal_acceptance
from .windows_notifications import ensure_windows_notification_identity
from .visual_canvas import prepare_webengine_runtime, register_canvas_scheme
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

INSTANCE_SERVER_NAME = "SmartiAI-Agent-for-Windows"
_UPDATE_MUTEX_HANDLE = None

class StartupWorker(QThread):
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object, str)

    def run(self):
        try:
            self.status_signal.emit("טוען הגדרות, זיכרון וכלים מקומיים...")
            migrate_legacy_runtime_state(include_files=False, include_directories=True)
            self.finished_signal.emit(SmartiCore(), "")
        except Exception as exc:
            logging.exception("Smarti startup failed.")
            self.finished_signal.emit(None, str(exc))


def _startup_command():
    args = {str(arg or "").strip().lower() for arg in sys.argv[1:]}
    if "--quit-for-update" in args or "/quit-for-update" in args:
        return "quit_for_update"
    return "voice" if "--voice" in args or "/voice" in args else "show_new_chat"

def _create_update_mutex():
    global _UPDATE_MUTEX_HANDLE
    if os.name != "nt":
        return None
    try:
        _UPDATE_MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, False, INSTANCE_SERVER_NAME)
    except Exception:
        _UPDATE_MUTEX_HANDLE = None
    return _UPDATE_MUTEX_HANDLE

def _send_command_to_existing_instance(command):
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_SERVER_NAME)
    if not socket.waitForConnected(1200):
        return False
    socket.write(str(command or "show_new_chat").encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True

def _create_instance_server():
    server = QLocalServer()
    if server.listen(INSTANCE_SERVER_NAME):
        return server
    QLocalServer.removeServer(INSTANCE_SERVER_NAME)
    if server.listen(INSTANCE_SERVER_NAME):
        return server
    logging.warning("Single-instance server could not start: %s", server.errorString())
    return None

def main():
    if "--smarti-webengine-probe" in sys.argv:
        from .webengine_probe import run_probe
        raise SystemExit(run_probe())
    try:
        ensure_windows_notification_identity()
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(SMARTI_APP_AUMID)
    except Exception:
        pass

    webengine_healthy = True
    if os.name == "nt":
        # Qt WebEngine is the real in-process Smarti Browser.  Probe it in a
        # disposable child first because a broken Chromium/graphics runtime can
        # terminate the process below Python's exception boundary.
        from .webengine_probe import probe_webengine_runtime
        webengine_healthy = probe_webengine_runtime()
    if webengine_healthy:
        prepare_webengine_runtime()
    register_canvas_scheme()
    app = QApplication(sys.argv)
    app.setApplicationName(SMARTI_APP_DISPLAY_NAME)
    app.setApplicationDisplayName(SMARTI_APP_DISPLAY_NAME)
    app.setOrganizationName(SMARTI_APP_DISPLAY_NAME)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setCursorFlashTime(1000)
    app.setFont(app_font(10))
    app.setQuitOnLastWindowClosed(False)
    apply_app_theme(app)

    instance_command = _startup_command()
    if _send_command_to_existing_instance(instance_command):
        sys.exit(0)
    instance_server = _create_instance_server()
    app._smarti_update_mutex_handle = _create_update_mutex()

    splash_size, border_width, radius = QSize(500, 310), 1, 30
    splash = AnimatedSplash(os.path.join(ASSETS_DIR, "logo.png"), splash_size, ACCENT_COLOR, border_width, radius, BG_COLOR)
    splash.center_on_screen()
    splash.show()
    app.processEvents()

    splash.set_status("בודק נתוני ריצה מקומיים...")
    migrate_legacy_runtime_state(include_directories=False)
    accepted_legal_this_run = False
    splash.set_status("בודק אישור תנאי שימוש...")
    if not raw_settings_have_current_legal_acceptance():
        splash.hide()
        legal_dialog = LegalAgreementDialog()
        if legal_dialog.exec() != QDialog.DialogCode.Accepted:
            splash.close()
            sys.exit(0)
        accepted_legal_this_run = True
        splash.show()
        splash.raise_()
        app.processEvents()

    startup_worker = StartupWorker()
    app._smarti_startup_worker = startup_worker
    app._smarti_splash = splash

    def finish_startup(core, error):
        if error or core is None:
            splash.finish(None)
            QMessageBox.critical(None, SMARTI_APP_DISPLAY_NAME, f"שגיאה בפתיחת סמארטי:\n{error}")
            app.quit()
            return
        if accepted_legal_this_run:
            splash.set_status("שומר אישור תנאי שימוש...")
            record_legal_acceptance(core)
        splash.set_status("מחיל ערכת תצוגה והגדרות...")
        apply_app_theme(app, settings=core.settings)
        splash.set_status("מכין את חלון השיחה...")
        window = ChatWindow(core)
        app._smarti_main_window = window
        if instance_server:
            splash.set_status("מחבר הפעלה יחידה של סמארטי...")
            window.attach_instance_server(instance_server)
        splash.set_status("מסיים פתיחה...")
        window.show()
        splash.finish(window)

    startup_worker.status_signal.connect(splash.set_status)
    startup_worker.finished_signal.connect(finish_startup)
    startup_worker.finished.connect(lambda: setattr(app, "_smarti_startup_worker", None))
    startup_worker.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
