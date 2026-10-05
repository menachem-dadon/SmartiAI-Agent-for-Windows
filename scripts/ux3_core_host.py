"""Isolated real Core host for UX-3 browser QA; only model generation is deterministic.

Never imported by the product. tests installs a temporary profile and in-memory
keyring before any runtime imports. The bearer stays in the parent Node process.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests  # noqa: F401 - intentional pre-import profile/keyring isolation
from smarti.core_service import SmartiCoreService

service = SmartiCoreService(token=os.environ["UX3_TEST_TOKEN"])
handshake = service.start()
core = service.core
core.settings.update({"api_mode": "local", "selected_local_model": "ux3-local",
                      "conversation_title_generation_mode": "local", "updates_auto_check": False,
                      "favorite_models": [{"provider": "local", "model": "ux3-local"}, {"provider": "openai", "model": "qa-model"}],
                      "ui_preferences": {"theme_mode": "light"}})
core._save_settings()
store = core.chat_store
sample = service.create_session(title="מחקר לקראת המפגש")["id"]
for index in range(200):
    store.append_message("user" if index % 2 == 0 else "assistant",
                         f"הודעה {index} — Hebrew and English, שיחה ארוכה.", session_id=sample)
store.append_message("assistant", "## תוכנית העבודה\n\nתוכן מעורב בעברית ובאנגלית.\n\n```python\nprint('hello')\n```\n\n| שם | ערך |\n|---|---|\n| בדיקה | 42 |", session_id=sample)
store.append_message("assistant", "פעילות כלים שמורה", session_id=sample, metadata={
    "agent_process": {"elapsed_seconds": 3, "events": [
        {"type": "report", "text": "בודק קובץ"},
        {"type": "tool_start", "tools": [{"action": "file_manager", "event_id": "qa-stored", "arguments_text": "long_input_" + "x" * 16000}]},
        {"type": "tool_finish", "results": [{"action": "file_manager", "event_id": "qa-stored", "output": "long_output_" + "y" * 16000}]},
    ]}})
other = service.create_session(title="שיחה נוספת")["id"]
store.append_message("user", "תוכן ראשון", session_id=other)

def generate(text, **_kwargs):
    context = core._execution_context
    run = context.run_id
    session = context.target_session_id
    manager = core.run_manager
    if text.startswith("visual"):
        time.sleep(1.6)
        manager._emit("run_step", run, session, {"value": {"type": "report", "text": "בודק את פריסת תהליך העבודה"}})
        manager._emit("run_step", run, session, {"value": {"type": "tool_start", "tools": [{"action": "file_manager", "event_id": "qa-visual", "arguments_text": "{}"}]}})
        time.sleep(10)
        manager._emit("run_step", run, session, {"value": {"type": "tool_finish", "results": [{"action": "file_manager", "event_id": "qa-visual", "output": "בדיקת פריסה הושלמה"}]}})
        return "בדיקת תצוגה הסתיימה"
    manager._emit("run_step", run, session, {"value": {"type": "report", "text": "בודק את הבקשה"}})
    time.sleep(0.8)
    if text.startswith("approve"):
        manager._emit("run_step", run, session, {"value": {"type": "tool_start", "tools": [{"action": "file_manager", "event_id": "qa-file", "arguments_text": "{}"}]}})
        prompt = "action: atomic_write_text\n\n\nמדיניות: fail\n\nנתיב: C:/isolated/qa.txt\n\nהשפעה: יצירת תוצר"
        if text.startswith("approve-long"):
            prompt += "\n" + "\n".join(f"פרט {n}: " + "טקסט " * 8 for n in range(100))
        accepted = manager.request_approval(run, session, "אישור כתיבת קובץ", prompt, "low")
        manager._emit("run_step", run, session, {"value": {"type": "tool_finish", "results": [{"action": "file_manager", "event_id": "qa-file", "output": "אושר" if accepted else "נדחה"}]}})
        return "הפעולה אושרה" if accepted else "הפעולה נדחתה"
    if text.startswith("key"):
        manager.request_api_key(run, session, "openai_api_key", "OpenAI", "חסר מפתח API", "נדרש מפתח להמשך בדיקת התהליך")
        return "המתנה למפתח הסתיימה"
    if text.startswith("fail"):
        return "ERROR_USER: הספק אינו זמין בבדיקת הכשל המבודדת. אפשר לנסות שוב."
    if text.startswith("wait"):
        for _ in range(600):
            if context.cancel_event.is_set(): break
            time.sleep(0.1)
    return "תשובה: " + text

core.send_message = generate
print(json.dumps({**handshake, "sample": sample, "other": other}), flush=True)

def control():
    try:
        for line in sys.stdin:
            if line.strip() == "shutdown": break
    finally:
        service.request_shutdown()

threading.Thread(target=control, daemon=True).start()
try:
    while not service.wait(0.25): pass
finally:
    service.stop()
