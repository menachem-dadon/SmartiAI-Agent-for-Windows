"""Official stdio protocol exercised locally; no login, network or model usage."""
import copy
import json
import os
import queue
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from smarti.agent.streaming import LiveResponse
from smarti.codex_signin import CodexSignInProvider, SMARTI_TURN_OUTPUT_SCHEMA
from smarti.codex_stream import complete_stream, _read_turn
from smarti.common import SmartiCancelled


SERVER = r'''
import json, sys, time
log, behavior = sys.argv[1:]
number = 0
def emit(value):
    print(json.dumps(value), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    with open(log, "a", encoding="utf-8") as file:
        file.write(json.dumps(request) + "\n")
    method = request.get("method")
    if method == "initialize":
        emit({"id": request["id"], "result": {}})
    elif method == "thread/start":
        emit({"id": request["id"], "result": {"thread": {"id": "fixture-thread"}}})
    elif method == "turn/start":
        number += 1
        emit({"id": request["id"], "result": {"turn": {"id": "turn-" + str(number)}}})
        if behavior == "wait":
            time.sleep(30)
            continue
        if behavior == "fail":
            emit({"method": "turn/completed", "params": {"turn": {"status": "failed", "error": {"message": "fixture failure"}}}})
            continue
        emit({"id": 1000 + number, "method": "item/commandExecution/requestApproval", "params": {}})
        value = {"kind": "final", "progress_report": None, "tool_calls": None, "final_answer": "fixture answer"}
        emit({"method": "item/agentMessage/delta", "params": {"delta": json.dumps(value)}})
        emit({"method": "thread/tokenUsage/updated", "params": {"tokenUsage": {"last": {"inputTokens": 100, "cachedInputTokens": 80, "outputTokens": 10, "totalTokens": 110}}}})
        emit({"method": "turn/completed", "params": {"turn": {"id": "turn-" + str(number), "status": "completed"}}})
'''


class CodexSessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.script = root / "server.py"
        self.script.write_text(SERVER, encoding="utf-8")
        self.logs, self.processes = [], []
        self.behavior = "normal"
        self.provider = CodexSignInProvider(root)
        self.provider._environment = lambda: dict(os.environ, CODEX_HOME=str(root))
        self.provider._find_executable = lambda: "fixture"
        popen = subprocess.Popen
        launch_lock = threading.Lock()

        def launch(_command, **options):
            with launch_lock:
                log = root / f"rpc-{len(self.logs)}.jsonl"
                self.logs.append(log)
            process = popen([sys.executable, "-u", str(self.script), str(log), self.behavior], **options)
            self.processes.append(process)
            return process

        patch = mock.patch("smarti.codex_stream.subprocess.Popen", side_effect=launch)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.cleanup_sessions)
        self.messages = [{"role": "system", "content": "binding instructions"}, {"role": "user", "content": "initial user request"}]

    def cleanup_sessions(self):
        for key in list(self.provider._stream_sessions):
            self.provider.close_stream_session(key)

    def turn(self, messages=None, key="run-a", cancel=None):
        return complete_stream(self.provider, messages or self.messages, "test-model", 5, "high", cancel,
                               LiveResponse(), SMARTI_TURN_OUTPUT_SCHEMA, session_key=key)

    def requests(self, index=0):
        return [json.loads(line) for line in self.logs[index].read_text(encoding="utf-8").splitlines()]

    def test_same_thread_sends_only_new_feedback_and_uploads_images_once(self):
        messages = copy.deepcopy(self.messages)
        messages[1]["content"] = [{"type": "text", "text": "initial user request"},
                                  {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}}]
        self.assertEqual(self.turn(messages)[0], "fixture answer")
        for index in range(2):
            messages.extend([{"role": "assistant", "content": f"translated tool call {index}"},
                             {"role": "user", "content": f"new tool feedback {index}"}])
            _, usage = self.turn(messages)
            self.assertEqual(usage["cached_prompt"], 80)
        self.cleanup_sessions()
        requests = self.requests()
        self.assertEqual(len(self.processes), 1)
        self.assertEqual(sum(r.get("method") == "thread/start" for r in requests), 1)
        turns = [r["params"] for r in requests if r.get("method") == "turn/start"]
        self.assertEqual(len(turns), 3)
        self.assertTrue(all(t["threadId"] == "fixture-thread" for t in turns))
        self.assertEqual([sum(i["type"] == "localImage" for i in t["input"]) for t in turns], [1, 0, 0])
        for index, turn in enumerate(turns[1:]):
            text = turn["input"][0]["text"]
            self.assertIn(f"new tool feedback {index}", text)
            self.assertNotIn("initial user request", text)
            self.assertNotIn("translated tool call", text)
        self.assertTrue(any(r.get("error", {}).get("code") == -32601 for r in requests))
        self.assertFalse(self.provider._stream_sessions)
        self.assertTrue(all(p.poll() is not None for p in self.processes))

    def test_compaction_or_instruction_change_replays_authoritative_context(self):
        for changed in ([self.messages[0], {"role": "user", "content": "compacted summary and latest request"}],
                        [{"role": "system", "content": "changed binding instructions"}, self.messages[1]]):
            with self.subTest(changed=changed):
                self.turn()
                before = len(self.processes)
                self.turn(changed)
                self.assertEqual(len(self.processes), before + 1)
                self.assertIsNotNone(self.processes[-2].poll())
                turn = next(r for r in self.requests(-1) if r.get("method") == "turn/start")
                self.assertIn(changed[1]["content"], turn["params"]["input"][0]["text"])
                self.cleanup_sessions()

    def test_parallel_runs_have_independent_context_and_cleanup(self):
        errors = []
        def run(key):
            try:
                self.turn(key=key)
            except BaseException as error:
                errors.append(error)
        threads = [threading.Thread(target=run, args=(key,)) for key in ("one", "two")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(8)
        self.assertFalse(errors)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(len(self.provider._stream_sessions), 2)
        first = self.provider._stream_sessions["one"]
        second = self.provider._stream_sessions["two"]
        self.assertIsNot(first.process, second.process)
        first_process = first.process
        self.provider.close_stream_session("one")
        self.assertIsNotNone(first_process.poll())
        self.assertIsNone(second.process.poll())

    def test_cancellation_and_failed_turn_destroy_uncertain_session(self):
        for behavior in ("wait", "fail"):
            with self.subTest(behavior=behavior):
                self.behavior = behavior
                cancel = threading.Event()
                timer = threading.Timer(.5, cancel.set)
                timer.start()
                try:
                    with self.assertRaises(SmartiCancelled if behavior == "wait" else Exception):
                        self.turn(cancel=cancel)
                finally:
                    timer.cancel()
                self.assertFalse(self.provider._stream_sessions)
                self.assertIsNotNone(self.processes[-1].poll())

    def test_old_session_cleanup_does_not_close_replacement(self):
        self.turn()
        current = self.provider._stream_sessions["run-a"]
        old = mock.Mock(lock=threading.RLock())
        self.provider.close_stream_session("run-a", old)
        old.close.assert_called_once()
        self.assertIs(self.provider._stream_sessions["run-a"], current)
        self.assertIsNone(current.process.poll())

    def test_usage_counts_all_inference_requests_without_recounting_prior_turns(self):
        incoming = queue.Queue()
        totals = {'inputTokens': 1000, 'cachedInputTokens': 800, 'outputTokens': 40, 'totalTokens': 1040}
        for consumed in (50, 100):
            incoming.put(json.dumps({'method': 'thread/tokenUsage/updated', 'params': {'tokenUsage': {
                'last': {'inputTokens': 50},
                'total': {'inputTokens': 1000 + consumed, 'cachedInputTokens': 800 + consumed,
                          'outputTokens': 40 + consumed, 'totalTokens': 1040 + consumed * 2}}}}))
        incoming.put(json.dumps({'method': 'item/agentMessage/delta', 'params': {'delta': json.dumps({
            'kind': 'final', 'final_answer': 'done', 'tool_calls': None, 'progress_report': None})}}))
        incoming.put(json.dumps({'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}}))
        _, usage = _read_turn(self.provider, None, incoming, lambda _: None, time.monotonic() + 2,
                              'fixture-thread', None, LiveResponse(), 'test-model', usage_totals=totals)
        self.assertEqual(usage, {'prompt': 100, 'cached_prompt': 100, 'completion': 100, 'total': 200, 'reasoning': 0})
        self.assertEqual(totals['inputTokens'], 1100)


if __name__ == "__main__":
    unittest.main()
