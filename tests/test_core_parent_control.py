import io
import threading
import unittest
from unittest.mock import Mock, patch

from smarti_core_service import _ParentControl, _monitor_stdin


class CoreParentControlTests(unittest.TestCase):
    def test_shutdown_during_initialization_is_reapplied_after_start_clears_event(self):
        parent = _ParentControl()
        parent.request_shutdown()
        service = Mock()
        service.stopped = threading.Event()
        service.request_shutdown.side_effect = service.stopped.set
        parent.bind(service)
        service.stopped.clear()  # Core service start() resets its own event.
        parent.bind(service)
        self.assertTrue(service.stopped.is_set())
        self.assertTrue(parent.stopping.is_set())

    def test_explicit_parent_shutdown_is_cooperative(self):
        parent = _ParentControl()
        with patch('smarti_core_service.sys.stdin', io.StringIO('{"command":"shutdown"}\n')), patch('smarti_core_service.threading.Timer') as timer:
            _monitor_stdin(parent)
        self.assertTrue(parent.stopping.is_set())
        timer.assert_not_called()

    def test_closed_parent_pipe_bounds_shutdown_even_before_core_exists(self):
        parent = _ParentControl()
        with patch('smarti_core_service.sys.stdin', io.StringIO('')), patch('smarti_core_service.threading.Timer') as timer:
            _monitor_stdin(parent)
        self.assertTrue(parent.stopping.is_set())
        self.assertEqual(timer.call_args.args[0], 8)
        timer.return_value.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
