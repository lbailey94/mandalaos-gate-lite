"""Keep vector generation explicit and preserve the historical 0.4 corpus."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from continuity_receipt import verify_bundle  # noqa: E402
import make_vectors  # noqa: E402


EXPECTED = {
    "01_happy_minimal.json": ("TRUSTED", None, False),
    "02_happy_full.json": ("TRUSTED", None, False),
    "03_tampered_body.json": ("UNTRUSTED", "bad_signature", False),
    "04_missing_termination.json": ("UNTRUSTED", "missing_termination", False),
    "05_cap_exceeded.json": ("UNTRUSTED", "cap_exceeded", False),
    "06_delivery_before_settlement.json": ("UNTRUSTED", "delivery_before_settlement", False),
    "07_redacted_no_disclosure.json": ("PROVISIONAL", None, False),
    "08_redacted_disclosed.json": ("TRUSTED", None, False),
    "09_erased_content.json": ("INSUFFICIENT_EVIDENCE", None, False),
    "10a_anchor_invalid.json": ("UNTRUSTED", "anchor_invalid", False),
    "10b_anchor_missing.json": ("PROVISIONAL", None, True),
}


class TestMakeVectors(unittest.TestCase):
    def test_each_supported_spec_is_used_throughout_generated_corpus(self):
        for spec in make_vectors.SPECS:
            with self.subTest(spec=spec), tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir) / "vectors"
                make_vectors.generate_vectors(output_dir, spec)

                index = (output_dir / "INDEX.md").read_text(encoding="utf-8")
                self.assertIn(f"# Continuity Receipt spec {spec.rsplit('/', 1)[1]}", index)
                self.assertIn(f"--spec {spec.rsplit('/', 1)[1]} --out <output-dir>", index)

                self.assertEqual(set(EXPECTED), {path.name for path in output_dir.glob("*.json")})
                for name, (verdict, code, require_anchor) in EXPECTED.items():
                    bundle = json.loads((output_dir / name).read_text(encoding="utf-8"))
                    self.assertEqual(bundle["spec"], spec, name)
                    self.assertTrue(bundle["receipts"], name)
                    self.assertTrue(all(receipt["spec"] == spec for receipt in bundle["receipts"]), name)
                    for receipt in bundle["receipts"]:
                        if receipt["type"] == "delivery.attestation":
                            self.assertEqual(receipt["body"]["spec_ref"], spec, name)

                    result = verify_bundle(bundle, require_anchor=require_anchor)
                    self.assertEqual(result.verdict, verdict, f"{spec} {name}: {result.errors}")
                    if code:
                        self.assertIn(code, result.codes(), f"{spec} {name}: {result.codes()}")

    def test_historical_vectors_cannot_be_selected_as_output(self):
        vector_dir = ROOT / "vectors"
        before = {path.name: path.read_bytes() for path in vector_dir.iterdir() if path.is_file()}
        with self.assertRaises(ValueError):
            make_vectors.generate_vectors(vector_dir, "continuity-receipt/0.5")
        after = {path.name: path.read_bytes() for path in vector_dir.iterdir() if path.is_file()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
