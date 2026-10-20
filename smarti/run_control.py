"""Cooperative run control. A pause never abandons an in-flight tool batch."""
import threading


class RunControl:
    def __init__(self):
        self.condition = threading.Condition()
        self.paused = False
        self.waiting = False
        self.revision = 0
        self.updates = []

    def change(self, action, text="", attachments=None):
        with self.condition:
            if action == "pause":
                self.paused = True
            elif action == "resume":
                self.paused = False
            elif action == "update":
                if not str(text).strip():
                    raise ValueError("נדרשת הנחיה לעדכון המשימה")
                self.revision += 1
                self.updates.append({"revision": self.revision, "text": str(text), "attachments": list(attachments or [])})
            else:
                raise ValueError("פעולת שליטה לא מוכרת")
            self.condition.notify_all()
            return self.revision

    def boundary(self, cancelled, on_pause, on_resume):
        with self.condition:
            if self.paused:
                self.waiting = True
                on_pause()
                try:
                    while self.paused and not cancelled():
                        self.condition.wait(.1)
                finally:
                    self.waiting = False
                if not cancelled():
                    on_resume()
            result, self.updates = self.updates, []
            return result
