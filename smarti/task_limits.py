"""Task deadlines and bounded subprocess capture, independent of presentation."""
import threading
import time


class TaskCancellation:
    """A deadline cancels this task without marking a user cancellation."""
    def __init__(self, user_event, seconds):
        self.user_event = user_event
        self.expired = threading.Event()
        self._deadline_lock = threading.RLock()
        self._timer_revision = 0
        self._paused_remaining = None
        self.deadline = time.monotonic() + seconds if seconds else None
        self.timer = threading.Timer(seconds, self._expire, args=(0,)) if seconds else None
        if self.timer:
            self.timer.daemon = True
            self.timer.start()

    def _expire(self, revision):
        with self._deadline_lock:
            if revision == self._timer_revision and self.deadline is not None:
                self.expired.set()

    def suspend(self):
        with self._deadline_lock:
            if self.deadline is not None:
                self._paused_remaining = max(0, self.deadline - time.monotonic())
                self.deadline = None
                self._timer_revision += 1
                if self.timer:
                    self.timer.cancel()

    def resume(self):
        with self._deadline_lock:
            if self._paused_remaining is None:
                return
            remaining, self._paused_remaining = self._paused_remaining, None
            self.deadline = time.monotonic() + remaining
            self.timer = threading.Timer(remaining, self._expire, args=(self._timer_revision,))
            self.timer.daemon = True
            self.timer.start()

    def is_set(self):
        return self.user_event.is_set() or self.expired.is_set()

    def set(self):
        self.user_event.set()

    def wait(self, timeout=None):
        end = time.monotonic() + timeout if timeout is not None else None
        while not self.is_set():
            if end is not None and time.monotonic() >= end:
                return False
            self.user_event.wait(min(0.05, max(0, end - time.monotonic())) if end else 0.05)
        return True

    def close(self):
        with self._deadline_lock:
            self._timer_revision += 1
            if self.timer:
                self.timer.cancel()


class BoundedCapture:
    """Bound memory and model previews; archive overflow instead of discarding it."""
    def __init__(self, proc, limit, input_value=None, archive_factory=None, keep_full=False):
        self.limit = limit
        self.parts = [[], []]
        self.sizes = [0, 0]
        self.totals = [0, 0]
        self.archives = [None, None]
        self.archive_factory = archive_factory
        self.keep_full = keep_full
        self.failure = None
        self.done = [threading.Event(), threading.Event()]
        for index, pipe in enumerate((proc.stdout, proc.stderr)):
            threading.Thread(target=self._read, args=(index, pipe), daemon=True).start()
        if proc.stdin is not None:
            def write():
                try:
                    proc.stdin.write(input_value)
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    proc.stdin.close()
            threading.Thread(target=write, daemon=True).start()

    def _read(self, index, pipe):
        try:
            while True:
                part = pipe.read(65536)
                if not part:
                    break
                if self.totals[index] + len(part) > self.limit and self.archive_factory:
                    if self.archives[index] is None:
                        self.archives[index] = self.archive_factory()
                        self.archives[index].write("".join(self.parts[index]))
                    self.archives[index].write(part)
                self.totals[index] += len(part)
                keep = part if self.keep_full else part[:max(0, self.limit - self.sizes[index])]
                if keep:
                    self.parts[index].append(keep)
                    self.sizes[index] += len(keep)
        except Exception as exc:
            self.failure = exc
        finally:
            pipe.close()
            self.done[index].set()

    def ready(self):
        return all(event.is_set() for event in self.done)

    def output(self, text, full=False):
        if self.failure:
            raise OSError("Could not retain full subprocess output") from self.failure
        result = []
        for index in range(2):
            value = ("" if text else b"").join(self.parts[index])
            if self.totals[index] > self.limit and not self.keep_full:
                archive = self.archives[index]
                if archive and full:
                    result.append(archive.full_text())
                    continue
                if archive and text:
                    value = archive.preview(self.limit)
                retrieval = f"; read_tool_output output_id={archive.output_id} offset={self.limit} to retrieve the rest" if archive else "; full output unavailable"
                marker = f"\n[TRUNCATED: captured {self.limit} of {self.totals[index]} characters{retrieval}]"
                value = marker.lstrip("\n") + "\n" + value if text else marker.encode("ascii") + value
            result.append(value)
        return result
