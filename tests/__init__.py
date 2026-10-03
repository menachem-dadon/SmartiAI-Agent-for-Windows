"""Keep unittest imports away from the user's Smarti profile and credentials."""
import atexit
import logging
import os
import sys
import tempfile


if "smarti.common" in sys.modules:
    raise RuntimeError(
        "Import tests before Smarti so user data can be isolated. "
        "Use python -m unittest discover -s tests -t ."
    )

# Replace inherited overrides too: a developer's SMARTI_DATA_DIR can point to
# their real profile. Set this before common.py resolves any persistence paths.
_profile = tempfile.TemporaryDirectory(prefix="smarti-unittest-", ignore_cleanup_errors=True)
os.environ["SMARTI_DATA_DIR"] = _profile.name

try:
    import keyring
    from keyring.backend import KeyringBackend
except ImportError:
    pass
else:
    class _TestKeyring(KeyringBackend):
        priority = 1

        def __init__(self):
            self._values = {}

        def get_password(self, service, username):
            return self._values.get((service, username))

        def set_password(self, service, username, password):
            self._values[service, username] = password

        def delete_password(self, service, username):
            self._values.pop((service, username), None)

    keyring.set_keyring(_TestKeyring())


def _cleanup_profile():
    logging.shutdown()
    _profile.cleanup()


atexit.register(_cleanup_profile)
