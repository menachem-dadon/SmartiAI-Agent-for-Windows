import os

file_path = r"c:\Users\יהודית סיידון\Downloads\GitHub\SmartiAI-Agent-for-Windows\smarti\windows_notifications.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

target_signals = """class WindowsNotificationCenter(QObject):
    reply_requested = pyqtSignal(str)
    activate_requested = pyqtSignal()
    attention_cleared = pyqtSignal()"""

replacement_signals = """class WindowsNotificationCenter(QObject):
    reply_requested = pyqtSignal(str)
    activate_requested = pyqtSignal()
    attention_cleared = pyqtSignal()
    conversation_switch_requested = pyqtSignal(str)"""

content = content.replace(target_signals, replacement_signals)

target_end = """                self._toaster.show_toast(toast)
                return True
            except Exception as exc:
                logging.warning("Native notice toast failed: %s", exc)
        self._show_fallback(title, body)
        return False"""

replacement_end = """                self._toaster.show_toast(toast)
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
        return False"""

show_notice_idx = content.find("def show_notice")
target_idx = content.find(target_end, show_notice_idx)
if target_idx != -1:
    content = content[:target_idx] + replacement_end + content[target_idx + len(target_end):]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully updated windows_notifications.py!")
else:
    print("Could not find target_end in show_notice!")
