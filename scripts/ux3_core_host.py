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
# Official account discovery must also stay outside the personal CLI profile.
os.environ["CODEX_HOME"] = str(Path(os.environ["SMARTI_DATA_DIR"]) / "codex-account")
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
if os.environ.get("CHAT_STREAM_QA") == "1":
    import base64
    qa_attachment = Path(os.environ["SMARTI_DATA_DIR"]) / "qa-attachment.png"
    qa_attachment.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=="))
    handshake["qa_attachment_path"] = str(qa_attachment)
    attachments = service.create_session(title="בדיקת צירופים")["id"]
    store.append_message("user", "הודעה ארוכה עם צירופים\n" + "\n".join(f"שורה {n}: טקסט בעברית עם English ועיצוב." for n in range(100)),
        metadata={"run_id": "qa-long-user", "attachments": [{"kind": "image", "name": f"image-{n}.png", "path": f"C:/isolated/image-{n}.png", "mime_type": "image/png"} for n in range(8)]}, session_id=attachments)
    store.append_message("assistant", "תשובה קצרה שהושלמה.", metadata={"run_status": "completed"}, session_id=attachments)
    links = service.create_session(title="בדיקת קישורים")["id"]
    store.append_message("user", "פתח את הקובץ שנוצר", session_id=links)
    store.append_message("assistant", "\n\n".join(f"פסקה {n}: תוכן ארוך לבדיקת שמירת מקום הקריאה." for n in range(35)) +
        "\n\n[קישור פגום](file:///C:/Users/%D7%99%D7%ห/Desktop/elad_weather.txt)" +
        "\n\n[קישור תקין](file:///C:/Users/%D7%99%D7%94%D7%95%D7%93%D7%99%D7%AA%20User/Desktop/elad_weather.txt)", session_id=links)
stress = None
if os.environ.get("UX6_STRESS_QA") == "1":
    stress = service.create_session(title="UX6 1000 messages")["id"]
    from ux6_stress_fixtures import seed_messages
    seed_messages(store, stress, 1000)

def generate(text, **_kwargs):
    context = core._execution_context
    run = context.run_id
    session = context.target_session_id
    manager = core.run_manager
    if os.environ.get("CHAT_STREAM_QA") == "1" and not text and _kwargs.get("attachments"):
        text = "stream-short"
    if os.environ.get("CHAT_STREAM_QA") == "1" and text.startswith("stream-"):
        from smarti.agent.streaming import LiveResponse
        live = LiveResponse(core.stream_callback)
        core._current_stream = live
        time.sleep(.6)  # Local server has not reported prefill/reasoning yet.
        live.status("prefill", 37)
        time.sleep(.6)
        live.status("thinking")
        time.sleep(.6)
        if text.startswith(("stream-tools", "stream-text-tool")):
            textual = text.startswith("stream-text-tool")
            tool_name = "create_python_tool" if textual else "canvas_manager"
            if textual:
                for char in '{"method":"create_python_tool","params":{"name":"generated_tool","code":"':
                    live.text(char)
                live.flush()
            else:
                live.text("בודק את קובץ הבדיקה")
                live.tool(0, tool_name)
            for _ in range(48 if textual else 16):
                core._raise_if_cancelled()
                if textual:
                    live.text("large_parameter_" * 2048)
                else:
                    live.tool(0, arguments="large_parameter_" * 2048)
                time.sleep(.08)
            if textual:
                live.text('"}}')
            live.finish(has_tools=True)
            core._emit_agent_process_event("report", text="בודק את קובץ הבדיקה")
            tool = core._agent_tool_event_item(tool_name, {}, event_id=live.calls["0"]["call_id"])
            core._emit_agent_process_event("tool_start", tools=[tool])
            accepted = manager.request_approval(run, session, "אישור בדיקת סטרימינג", "אישור מדומה בלבד; אין כתיבה או כלי חיצוני", "low")
            time.sleep(.6)
            core._emit_agent_process_event("tool_finish", results=[{**tool, "status": "ok" if accepted else "cancelled", "output": "בדיקת כלי הסתיימה"}])
            live = LiveResponse(core.stream_callback)
            core._current_stream = live
        pieces = [f"קטע {index}: תשובה חיה בעברית עם English וקישור.\n\n" for index in range(1, 51)] if text.startswith("stream-long") else ["תשובה ", "חיה ", "וסופית."]
        if text.startswith("stream-long"):
            pieces += ["| שם | ערך |\n|---|---|\n| עברית | 123 |\n\n", "```python\nprint('stream')\n```\n"]
        for piece in pieces:
            core._raise_if_cancelled()
            live.text(piece)
            time.sleep(.12)
        live.finish()
        return "".join(pieces)
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
workbench = {}
if os.environ.get("UX4_WORKBENCH_QA") == "1":
    from ux4_qa_fixtures import seed_workbench
    workbench = seed_workbench(service, sample)
print(json.dumps({**handshake, "sample": sample, "other": other, "stress": stress, "workbench": workbench}), flush=True)

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
