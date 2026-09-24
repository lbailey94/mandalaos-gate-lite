"""Selective disclosure tests (P1): redact, attach/reveal, commit checks."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, verify_bundle  # noqa: E402
from continuity_receipt.disclose import attach, redact, reveal  # noqa: E402
from gate_lite.orchestrator import Orchestrator  # noqa: E402


def make_bundle(state: Path) -> tuple[dict, tuple]:
    agent_did, _ = keys.generate(keys.deterministic_seed("dogfood-agent"))
    gate_did, gate_key = keys.generate(keys.deterministic_seed("gate-test"))
    orch = Orchestrator(state, gate_id="gate-test", gate_key=gate_key, gate_did=gate_did)
    orch.add_tenant("dogfood", [agent_did])
    (state / "gate.key").write_bytes(keys.private_raw(gate_key))
    issued = orch.pass_("dogfood", agent_did, spend_cap={"minor": 1000, "currency": "USD"})
    orch.exec_("dogfood", issued["slot_id"], "echo disclose", token=issued["token"])
    orch.settle("dogfood", issued["slot_id"], "invoice", "inv-disclose", 200)
    terminated = orch.terminate("dogfood", issued["slot_id"])
    return orch.receipt(terminated["task_id"]), (gate_key, gate_did)


def public_path(bundle: dict) -> str:
    index = next(i for i, r in enumerate(bundle["receipts"]) if r["type"] == "delivery.attestation")
    return f"receipts[{index}].body.spec_ref"


class TestDisclosure(unittest.TestCase):
    def test_redact_then_attach_verifies_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, signer = make_bundle(Path(tmp))
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")
            path = public_path(bundle)
            index = int(path.split("[")[1].split("]")[0])
            redacted, disclosure = redact(bundle, [path], signer=signer)
            self.assertIn("redacted", redacted["receipts"][index]["body"]["spec_ref"])
            self.assertIn("commit", redacted["receipts"][index]["body"]["spec_ref"])
            self.assertEqual(disclosure[path]["value"], "continuity-receipt/0.3")

            result = verify_bundle(redacted)
            self.assertEqual(result.verdict, "PROVISIONAL")
            self.assertIn(f"redacted_without_disclosure:{path}", result.provisional_reasons)

            disclosed = attach(redacted, disclosure)
            self.assertEqual(verify_bundle(disclosed).verdict, "TRUSTED")

    def test_tampered_disclosure_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, signer = make_bundle(Path(tmp))
            path = public_path(bundle)
            redacted, disclosure = redact(bundle, [path], signer=signer)
            disclosure[path]["value"] = "not-the-original"
            result = verify_bundle(attach(redacted, disclosure))
            self.assertEqual(result.verdict, "UNTRUSTED")
            self.assertIn("commit_mismatch", result.codes())

    def test_required_field_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, signer = make_bundle(Path(tmp))
            with self.assertRaises(ValueError):
                redact(bundle, ["receipts[0].body.gate_id"], signer=signer)

    def test_reveal_subset_stays_provisional(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle, signer = make_bundle(Path(tmp))
            spec_ref = public_path(bundle)
            observed = f"receipts[{len(bundle['receipts']) - 1}].body.observed"
            redacted, disclosure = redact(bundle, [spec_ref, observed], signer=signer)
            both = reveal(redacted, disclosure, [spec_ref, observed])
            self.assertEqual(verify_bundle(both).verdict, "TRUSTED")

            only_spec = reveal(redacted, disclosure, [spec_ref])
            result = verify_bundle(only_spec)
            self.assertEqual(result.verdict, "PROVISIONAL")
            self.assertIn(f"redacted_without_disclosure:{observed}", result.provisional_reasons)

    def test_cli_redact_verify_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            bundle, signer = make_bundle(state)
            path = public_path(bundle)
            bundle_file = state / "bundle.json"
            redacted_file = state / "redacted.json"
            map_file = state / "map.json"
            bundle_file.write_text(json.dumps(bundle), encoding="utf-8")

            redact_step = subprocess.run(
                [
                    sys.executable, "-m", "continuity_receipt.disclose", "redact",
                    "--bundle", str(bundle_file), "--path", path,
                    "--out", str(redacted_file), "--map", str(map_file),
                    "--gate-key", str(state / "gate.key"),
                ],
                cwd=str(ROOT), capture_output=True, text=True,
            )
            self.assertEqual(redact_step.returncode, 0, redact_step.stderr)

            without_map = subprocess.run(
                [sys.executable, "-m", "continuity_receipt.disclose", "verify", "--bundle", str(redacted_file)],
                cwd=str(ROOT), capture_output=True, text=True,
            )
            self.assertEqual(without_map.returncode, 1)
            self.assertEqual(json.loads(without_map.stdout)["verdict"], "PROVISIONAL")

            with_map = subprocess.run(
                [
                    sys.executable, "-m", "continuity_receipt.disclose", "verify",
                    "--bundle", str(redacted_file), "--map", str(map_file),
                ],
                cwd=str(ROOT), capture_output=True, text=True,
            )
            self.assertEqual(with_map.returncode, 0, with_map.stderr)
            self.assertEqual(json.loads(with_map.stdout)["verdict"], "TRUSTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
