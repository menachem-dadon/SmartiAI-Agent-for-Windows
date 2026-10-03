"""A test process must never inherit a real Smarti data profile."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class TestProfileIsolationTests(unittest.TestCase):
    def test_inherited_profile_and_keyring_are_replaced_before_runtime_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "smarti_settings.json"
            original = b'{"favorite_models": ["user-preference"]}'
            settings.write_bytes(original)
            environment = os.environ.copy()
            environment["SMARTI_DATA_DIR"] = directory
            script = """
import json
import tests
from smarti.common import USER_DATA_DIR, SETTINGS_FILE
from smarti.config import DEFAULT_SETTINGS
from smarti.core import SmartiCore
import keyring
import copy
core = SmartiCore.__new__(SmartiCore)
core.settings = copy.deepcopy(DEFAULT_SETTINGS)
core.settings['favorite_models'] = ['test-preference']
core._save_settings()
keyring.set_password('SmartiAI', 'isolation-test', 'test-only')
assert keyring.get_password('SmartiAI', 'isolation-test') == 'test-only'
print(json.dumps({'profile': USER_DATA_DIR, 'settings': SETTINGS_FILE,
                  'keyring': type(keyring.get_keyring()).__name__}))
"""
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                env=environment, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertNotEqual(os.path.abspath(report["profile"]), os.path.abspath(directory))
            self.assertEqual(report["keyring"], "_TestKeyring")
            self.assertEqual(settings.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [settings])


if __name__ == "__main__":
    unittest.main()
