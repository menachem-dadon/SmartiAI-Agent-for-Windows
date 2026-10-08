import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('startup_manifest', Path(__file__).resolve().parents[1] / 'scripts/tauri_source_manifest.py')
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)


class StartupArtworkManifestTests(unittest.TestCase):
    def test_optional_public_artwork_is_part_of_the_frozen_source_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = manifest.source_fingerprint(root)
            artwork = root / 'desktop/public/loading-icon.png'
            artwork.parent.mkdir(parents=True)
            artwork.write_bytes(b'first-artwork')
            self.assertIn('desktop/public/loading-icon.png', manifest.source_inputs(root))
            first = manifest.source_fingerprint(root)
            self.assertNotEqual(first, baseline)
            artwork.write_bytes(b'replacement-artwork')
            self.assertNotEqual(manifest.source_fingerprint(root), first)


if __name__ == '__main__':
    unittest.main()
