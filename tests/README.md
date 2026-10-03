# Running Python tests safely

Run tests as package modules from the repository root:

```powershell
python -m unittest tests.test_codex_signin tests.test_settings_sync
python -m unittest discover -s tests -t .
```

`tests/__init__.py` selects a fresh temporary Smarti profile before importing
the runtime and installs an in-memory keyring. Inherited `SMARTI_DATA_DIR`
values are replaced, so tests cannot use a developer's real profile or saved
provider credentials. Attachment fixtures use explicit dummy credentials.

Do not import Smarti before importing the tests package. Test discovery must
include `-t .` so the package initialization runs before test modules.
