"""Reject acceptance claims with stale, missing or mis-scoped evidence."""
import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("ux6_acceptance_checker", Path(__file__).resolve().parents[1] / "scripts/verify_ux6_acceptance.py")
_checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_checker)
source_fingerprint, validate = _checker.source_fingerprint, _checker.validate


class UX6AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "docs").mkdir()
        (self.root / "docs/tauri_migration_baseline.md").write_text("\n".join(f"| SHL-{n:03} | action |" for n in range(1, 98)), encoding="utf-8")
        source = self.root / "desktop/src/App.tsx"
        source.parent.mkdir(parents=True)
        source.write_text("source before", encoding="utf-8")
        (self.root / "evidence.json").write_text('{"ok":true}', encoding="utf-8")
        ids = [f"SHL-{n:03}" for n in range(1, 98)] + [f"UX6-{name}" for name in ("LOAD", "A11Y", "DPI", "PERF", "OWNERS", "MOTION")]
        self.data = {"design_decision": "D58", "stage_status": "ACCEPTANCE_PENDING", "capabilities": [
            {"id": name, "owner": "QA", "action": "action", "authority": "Core", "required_levels": ["source"], "results": {"source": {"status": "OPEN", "gap": "still needs review"}}} for name in ids], "evidence": {}}

    def passed(self):
        data = copy.deepcopy(self.data)
        data["capabilities"][0]["results"]["source"] = {"status": "PASS", "evidence": ["test"]}
        data["evidence"]["test"] = {"level": "source", "result": "PASS", "scope": "explicit test", "capabilities": ["SHL-001"], "source_sha256": source_fingerprint(self.root), "artifact": "evidence.json", "sha256": hashlib.sha256((self.root / "evidence.json").read_bytes()).hexdigest()}
        return data

    def test_pending_map_is_valid_but_cannot_pass_final_gate(self):
        self.assertEqual(validate(self.data, self.root), [])
        self.assertTrue(validate(self.data, self.root, final=True))

    def test_stale_source_and_changed_artifact_are_rejected(self):
        data = self.passed()
        self.assertEqual(validate(data, self.root), [])
        (self.root / "desktop/src/App.tsx").write_text("source after", encoding="utf-8")
        self.assertTrue(any("different source" in e for e in validate(data, self.root)))
        (self.root / "evidence.json").write_text("changed", encoding="utf-8")
        self.assertTrue(any("hash mismatch" in e for e in validate(data, self.root)))

    def test_source_proof_cannot_claim_windows_or_an_uncovered_action(self):
        data = self.passed()
        data["evidence"]["test"]["level"] = "windows"
        self.assertTrue(any("cross-level" in e for e in validate(data, self.root)))
        data["evidence"]["test"]["level"] = "source"
        data["evidence"]["test"]["capabilities"] = ["SHL-002"]
        self.assertTrue(any("does not cover" in e for e in validate(data, self.root)))

    def test_missing_capability_and_outside_artifact_are_rejected(self):
        data = self.passed()
        data["capabilities"].pop(1)
        self.assertTrue(any("97 stable" in e for e in validate(data, self.root)))
        data["evidence"]["test"]["artifact"] = "../outside.json"
        self.assertTrue(any("outside checkout" in e for e in validate(data, self.root)))

    def test_scoped_central_closure_cannot_bypass_full_product_gate(self):
        data = self.passed()
        data["stage_status"] = "COMPLETE"
        self.assertTrue(any("central acceptance receipt" in e for e in validate(data, self.root)))
        receipt = {"scope":"source-and-accepted-ui","source_sha256":source_fingerprint(self.root),
                   "user_authorized_closure":True,"result":"PASS","release_accepted":False,
                   "pending_evidence_levels":len(data["capabilities"])-1}
        path = self.root / "closure.json"
        path.write_text(json.dumps(receipt),encoding="utf-8")
        data["central_acceptance"] = {"artifact":"closure.json","sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
        self.assertEqual(validate(data,self.root),[])
        self.assertTrue(validate(data,self.root,final=True))
        receipt["pending_evidence_levels"] = 0
        path.write_text(json.dumps(receipt),encoding="utf-8")
        data["central_acceptance"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertTrue(any("preserve remaining" in e for e in validate(data,self.root)))


if __name__ == "__main__":
    unittest.main()
