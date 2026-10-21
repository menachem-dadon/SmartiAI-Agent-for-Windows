"""Isolated QA host: real Core/agent/tools, deterministic voice and inference.

Never imported by the product. No microphone, personal profile or paid provider.
"""
import asyncio
import base64
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests  # noqa: F401 -- profile and keyring isolation before Smarti imports
from smarti.core_service import SmartiCoreService
from smarti.live_voice import LiveSession


class VoiceSocket:
    closed = False
    def __init__(self, session): self.session = session
    async def close(self): self.closed = True
    async def send_json(self, data):
        session = self.session
        content = data.get("clientContent", {})
        text = "".join(part.get("text", "") for turn in content.get("turns", []) for part in turn.get("parts", []))
        if text.startswith("New user message"):
            request = text.split("\n", 2)[1]
            if "בדיקת כשל" in request:
                self.stall = True
                session.delivery_timeout = .4
            async def answer():
                if "בדיקת תזמון" in request:
                    await session.receive({"serverContent":{"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm;rate=24000","data":base64.b64encode(b"\0\0" * 72000).decode()}}]},"outputTranscription":{"text":"הדיבור הזה מופיע בקצב הניגון."},"turnComplete":True}})
                    return
                if "בדיקת שמע ארוך" in request:
                    for _ in range(3):
                        await session.receive({"serverContent":{"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm;rate=24000","data":base64.b64encode(b"\0\0" * 240000).decode()}}]}}})
                    await session.receive({"serverContent":{"outputTranscription":{"text":"בדיקת שמע ארוך הושלמה."},"turnComplete":True}})
                    return
                action = "start" if not session.active_task or "חדשה" in request else "update" if "עדכון" in request else "status"
                await session.receive({"serverContent": {"outputTranscription": {"text": "אני מפעיל את המשימה." if action == "start" else "אני איתך, הסוכן ממשיך לעבוד."}, "turnComplete": True}})
                if action != "status":
                    await session.receive({"toolCall": {"functionCalls": [{"id": uuid.uuid4().hex, "name": "smarty_task", "args": {"action": action, "instruction": request}}]}})
            asyncio.create_task(answer())
        for response in data.get("toolResponse", {}).get("functionResponses", []):
            if "result" in response.get("response", {}) and not response["response"].get("delivery") and response.get("willContinue") is False:
                task = session.delivery_task
                async def claim():
                    await session.receive({"toolCall": {"functionCalls": [{"id": uuid.uuid4().hex, "name": "smarty_task",
                        "args": {"action": "deliver", "task_id": task["id"], "run_id": task["run_id"]}}]}})
                asyncio.create_task(claim())
            if response.get("response", {}).get("delivery") == "accepted":
                if getattr(self, "stall", False):
                    self.stall = False
                    await session.receive({"serverContent": {"outputTranscription": {"text": "תשובה שנקטעה"}}})
                    return  # No turnComplete: exercise the real bounded fallback.
                await session.receive({"serverContent": {"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm;rate=24000","data":base64.b64encode(b"\0\0"*72001).decode()}}]}, "outputTranscription": {"text": "המשימה הסתיימה. קראתי את קובץ הבדיקה והכנתי את התוצאה."}, "turnComplete": True}})


async def connect(self):
    try:
        await self.authorize_files(self.gather_files())
        context = await asyncio.to_thread(self.context)
        self.emit("qa_context", bytes=len(context.encode('utf-8')))
        self.ws = VoiceSocket(self)
        await asyncio.sleep(.4)
        if self.closed: return
        self.phase = "ready"; self.emit("state", phase="ready")
        self.forwarder = asyncio.create_task(self.forward_events())
        self.finalizer = asyncio.create_task(self.deliver_finals())
        self.lease = asyncio.create_task(self.watch_lease())
        while not self.closed: await asyncio.sleep(.1)
    finally:
        await self.close(from_worker=True)


LiveSession.connect = connect
service = SmartiCoreService(token=os.environ["UX3_TEST_TOKEN"])
handshake = service.start()
core = service.core
core.settings.update(api_mode="local", selected_local_model="live-qa-model", live_provider="gemini", live_enabled=True,
                     live_gemini_api_key="isolated-fake-key", conversation_title_generation_mode="local",
                     prevent_sleep_during_active_task=False, read_aloud_all=True, updates_auto_check=False)
core.settings["ui_preferences"]["theme_mode"] = "light"
core.mode = "local"
core._ensure_active_provider_api_key = lambda: True
core._save_settings()
canary = Path(os.environ["SMARTI_DATA_DIR"]) / "live-canary.txt"
canary.write_text("SMARTI_LIVE_CANARY_42", encoding="utf-8")

def infer(model, messages, **kwargs):
    time.sleep(1.2)
    if core._execution_context.loop_iteration == 1:
        return json.dumps({"method": "tools/call", "params": {"name": "get_tool_info", "arguments": {"tool_name": "file_manager", "action": "read_document"}}}), {}
    if core._execution_context.loop_iteration == 2:
        return json.dumps({"method": "tools/call", "params": {"name": "file_manager", "arguments": {"action": "read_document", "path": str(canary)}}}), {}
    return "קראתי את הקובץ.\n\n```python\nprint('SMARTI_LIVE_CANARY_42')\n```\n\n| תוצאה | ערך |\n|---|---|\n| בדיקה | 42 |", {}

core._handle_api_request_with_retry = infer
sample = service.create_session(title="בדיקת לייב מבודדת")["id"]
print(json.dumps({**handshake, "sample": sample, "other": "", "stress": {}, "workbench": {}, "canary": str(canary)}), flush=True)

def control():
    try:
        for line in sys.stdin:
            if line.strip() == "shutdown": break
    finally:
        service.request_shutdown()
threading.Thread(target=control, daemon=True).start()
try:
    while not service.wait(.25): pass
finally:
    service.shutdown()
