"""Source/version preparation tests; never compile, install or read personal profiles."""
from pathlib import Path
import json
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("smarti_tauri_packaging", REPO / "scripts/prepare_tauri_package.py")
_packaging = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_packaging)
normalize_version, prepare, validate_label, VERSION_FILES = _packaging.normalize_version, _packaging.prepare, _packaging.validate_label, _packaging.VERSION_FILES


@unittest.skipUnless(sys.platform == "win32", "Windows packaging orchestration")
class TauriPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smarti-package-test-",dir="C:/")
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.root = self.base / "repo"
        self.root.mkdir()
        data = {
            "smarti/common.py": 'APP_VERSION = "V0.87.0"\r\n',
            "desktop/package.json": '{"name":"smarti-desktop","version":"0.87.0"}',
            "desktop/package-lock.json": '{"version":"0.87.0","packages":{"":{"version":"0.87.0"},"node_modules/example":{"version":"0.87.0"}}}',
            "desktop/src-tauri/tauri.conf.json": '{"version":"0.87.0"}',
            "desktop/src-tauri/Cargo.toml": '[package]\nname = "smarti-desktop"\nversion = "0.87.0"\n[dependencies]\nexample = "0.87.0"\n',
            "desktop/src-tauri/Cargo.lock": '[[package]]\nname = "example"\nversion = "0.87.0"\n\n[[package]]\nname = "smarti-desktop"\nversion = "0.87.0"\n',
            "desktop/src/App.tsx": 'export default "test fixture";',
        }
        for name, value in data.items():
            path = self.root / name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(value.encode("utf-8"))
        for name in ("build_and_package.ps1","prepare_tauri_package.py","tauri_source_manifest.py","build_tauri_release.ps1"):
            path = self.root / "scripts" / name
            path.parent.mkdir(exist_ok=True)
            shutil.copy2(REPO / "scripts" / name,path)
        subprocess.run(["git","init","-q",str(self.root)],check=True)
        subprocess.run(["git","-c","core.autocrlf=false","add","."],cwd=self.root,check=True)
        self.before = {name:(self.root/name).read_bytes() for name in VERSION_FILES}

    def test_override_updates_all_application_versions_only_in_snapshot(self):
        receipt = prepare(self.root,self.base/"work",self.base/"output","V0.99.1","בדיקה")
        d = json.loads(receipt.read_text(encoding="utf-8"))
        source = Path(d["source"])
        self.assertEqual(d["version"],"0.99.1")
        self.assertEqual(set(d["version_files_changed"]),set(VERSION_FILES))
        self.assertEqual({name:(self.root/name).read_bytes() for name in VERSION_FILES},self.before)
        self.assertIn('V0.99.1',(source/"smarti/common.py").read_text())
        lock = json.loads((source/"desktop/package-lock.json").read_text())
        self.assertEqual(lock["packages"][""]["version"],"0.99.1")
        self.assertEqual(lock["packages"]["node_modules/example"]["version"],"0.87.0")
        self.assertIn('name = "example"\nversion = "0.87.0"',(source/"desktop/src-tauri/Cargo.lock").read_text())
        self.assertEqual(d["label"],"בדיקה")
        self.assertFalse(Path(d["output"]).exists())

    def test_default_version_preserves_original_bytes_and_each_build_is_distinct(self):
        a = json.loads(prepare(self.root,self.base/"work",self.base/"output").read_text())
        b = json.loads(prepare(self.root,self.base/"work",self.base/"output").read_text())
        self.assertEqual(a["version_files_changed"],[])
        self.assertEqual(a["source_sha256"],a["working_tree_source_sha256"])
        self.assertNotEqual(a["work"],b["work"])
        self.assertEqual({name:(self.root/name).read_bytes() for name in VERSION_FILES},self.before)

    def test_invalid_version_label_and_in_repository_work_are_rejected(self):
        for value in ("preview","01.2.3","1.2.3-beta","65536.0.0"):
            with self.assertRaises(ValueError):normalize_version(value)
        for value in ("../escape","bad/name","trailing."):
            with self.assertRaises(ValueError):validate_label(value)
        with self.assertRaises(ValueError):prepare(self.root,self.root/"work",self.base/"output")

    def test_powershell_prepare_only_does_not_build_and_keeps_source_unchanged(self):
        result = subprocess.run(["pwsh","-NoProfile","-File",str(self.root/"scripts/build_and_package.ps1"),
                                 "-Version","0.99.2","-Label","preview","-WorkRoot",str(self.base/"work"),
                                 "-OutputDirectory",str(self.base/"output"),"-PrepareOnly"],capture_output=True,text=True,check=True)
        self.assertIn("no compilation",result.stdout)
        self.assertFalse((self.base/"output").exists())
        self.assertEqual({name:(self.root/name).read_bytes() for name in VERSION_FILES},self.before)

    def mock_builder(self, passed: bool):
        # Test double only: text payloads, no Core, Tauri build or executable launch.
        value = "$true" if passed else "$false"
        (self.root/"scripts/build_tauri_release.ps1").write_text('''
param([string]$Version,[string]$InstallerCompression,[switch]$AllowUnsignedLocal,[switch]$OfflineInstaller,[switch]$SkipPackageSmoke)
$repo=Split-Path $PSScriptRoot -Parent
$release=Join-Path $repo 'release'
New-Item -ItemType Directory -Path $release|Out-Null
$artifacts=@()
foreach($suffix in @('Setup.exe','win-x64-portable.zip')){
 $p=Join-Path $release "SmartiAI-Agent-for-Windows-$Version-$suffix"
 Set-Content -LiteralPath $p -Value 'UNIT TEST TEXT PAYLOAD; NOT A PACKAGE'
 $artifacts+=@{path=$p;sha256=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash;bytes=(Get-Item $p).Length}
}
$report=@{version=$Version;artifacts=$artifacts;packageSmoke=@{requested=$true;passed=PASS_VALUE};testCompression=$InstallerCompression;testOffline=[bool]$OfflineInstaller}
$report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $release "SmartiAI-Agent-for-Windows-$Version-manifest.json")
'''.replace('PASS_VALUE',value),encoding='utf-8')

    def test_wrapper_publishes_matching_metadata_and_options_with_a_mock_builder(self):
        self.mock_builder(True)
        subprocess.run(["pwsh","-NoProfile","-File",str(self.root/"scripts/build_and_package.ps1"),
                        "-Version","0.99.3","-Label","preview","-WorkRoot",str(self.base/"work"),
                        "-OutputDirectory",str(self.base/"output"),"-InstallerCompression","zlib","-OfflineInstaller"],
                       capture_output=True,text=True,check=True)
        report_path = next((self.base/"output").rglob('*-manifest.json'))
        report = json.loads(report_path.read_text(encoding='utf-8-sig'))
        self.assertEqual(report['version'],'0.99.3')
        self.assertEqual(report['label'],'preview')
        self.assertEqual(report['testCompression'],'zlib')
        self.assertTrue(report['testOffline'])
        self.assertTrue(report['packageSmoke']['passed'])
        self.assertIn('source_sha256',report)
        self.assertTrue(all(Path(a['path']).is_relative_to(self.base/'output') for a in report['artifacts']))
        self.assertEqual({name:(self.root/name).read_bytes() for name in VERSION_FILES},self.before)

    def test_wrapper_rejects_failed_mock_smoke_without_publishing(self):
        self.mock_builder(False)
        result = subprocess.run(["pwsh","-NoProfile","-File",str(self.root/"scripts/build_and_package.ps1"),
                                 "-WorkRoot",str(self.base/"work"),"-OutputDirectory",str(self.base/"output")],
                                capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((self.base/'output').exists())


if __name__ == "__main__":
    unittest.main()
