# -*- coding: utf-8 -*-
"""Source launcher for Smarti.

Keep this file intentionally thin: double-clicking a .pyw file has no console,
so startup failures need to be captured before the full application imports.
"""
from pathlib import Path
import sys
import traceback


def _show_startup_error(error):
    log_path = Path(__file__).with_name("smarti_startup_error.log")
    try:
        log_path.write_text(
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
            encoding="utf-8",
        )
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            f"Smarti failed to start.\n\n{error}\n\nDetails were written to:\n{log_path}",
            "SmartiAI",
            0x10,
        )
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from smarti.app import main

        main()
    except SystemExit:
        raise
    except Exception as exc:
        _show_startup_error(exc)
        raise
