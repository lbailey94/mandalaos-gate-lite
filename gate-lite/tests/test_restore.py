"""G7 restore + expiry sweep tests."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, verify_bundle  # noqa: E402
from gate_lite.orchestrator import Orchestrator, tree_hash  # noqa: E402


def make_orchestrator(state: Path) -> tuple[Orchestrator, str]:
    agent_did, _ = keys.generate(keys.deterministic_seed("dogfood-agent"))
    gate_did, gate_key = keys.generate(keys.deterministic_seed("gate-test"))
    orch = Orchestrator(state, gate_id="gate-test", gate_key=gate_key, gate_did=gate_did)
    orch.add_tenant("dogfood", [agent_did])
    return orch, agent_did


class TestRestore(unittest.TestCase):
    def test_snapshot_destroy_recreate_restore_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            orch, agent = make_orchestrator(state)
            issued = orch.pass_("dogfood", agent, minutes=10)
            workspace = state / "workspaces" / issued["slot_id"]
            (workspace / "artifact.txt").write_text("restore payload", encoding="utf-8")
            (workspace / "nested").mkdir()
            (workspace / "nested" / "note.txt").write_text("nested", encoding="utf-8")
            before = tree_hash(workspace)

            orch.exec_("dogfood", issued["slot_id"], "echo seed")
            snap = orch.snapshot("dogfood", issued["slot_id"])
            orch.terminate("dogfood", issued["slot_id"], reason="destroyed")

            recreated = orch.pass_("dogfood", agent, minutes=10)
            restored = orch.restore("dogfood", recreated["slot_id"], snap["snapshot_id"])
            self.assertEqual(restored["restored_hash"], before)
            restored_ws = state / "workspaces" / recreated["slot_id"]
            self.assertEqual((restored_ws / "artifact.txt").read_text(encoding="utf-8"), "restore payload")
            self.assertEqual((restored_ws / "nested" / "note.txt").read_text(encoding="utf-8"), "nested")

            executed = orch.exec_("dogfood", recreated["slot_id"], "echo restored")
            self.assertEqual(executed["exit"], 0)
            terminated = orch.terminate("dogfood", recreated["slot_id"])
            bundle = orch.receipt(terminated["task_id"])
            attestations = [r for r in bundle["receipts"] if r["type"] == "delivery.attestation"]
            self.assertEqual(len(attestations), 1)
            self.assertEqual(attestations[0]["body"]["artifact"]["kind"], "filesystem-restore")
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")

            original = orch.receipt(orch.task_id_for(issued["slot_id"]))
            original_attestations = [r for r in original["receipts"] if r["type"] == "delivery.attestation"]
            self.assertEqual(original_attestations[0]["body"]["artifact"]["kind"], "filesystem-tar.gz")

    def test_cross_tenant_restore_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp))
            orch.add_tenant("other", [agent])
            issued = orch.pass_("dogfood", agent)
            snap = orch.snapshot("dogfood", issued["slot_id"])
            other = orch.pass_("other", agent)
            with self.assertRaises(PermissionError):
                orch.restore("other", other["slot_id"], snap["snapshot_id"])

    def test_tampered_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent)
            snap = orch.snapshot("dogfood", issued["slot_id"])
            Path(snap["artifact"]["path"]).write_bytes(b"tampered")
            recreated = orch.pass_("dogfood", agent)
            with self.assertRaises(ValueError):
                orch.restore("dogfood", recreated["slot_id"], snap["snapshot_id"])

    def test_restore_requires_placed_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent)
            snap = orch.snapshot("dogfood", issued["slot_id"])
            with self.assertRaises(ValueError):
                orch.restore("dogfood", issued["slot_id"], snap["snapshot_id"])


class TestExpirySweep(unittest.TestCase):
    def _force_expiry(self, orch: Orchestrator, slot_id: str) -> None:
        slot = orch.registry.get_slot(slot_id)
        slot["expires_at"] = 1
        orch.registry.put_slot(slot)

    def test_sweep_seals_expired_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent, minutes=1)
            self._force_expiry(orch, issued["slot_id"])
            result = orch.sweep_expired("dogfood")
            self.assertEqual(result["count"], 1)
            self.assertEqual(orch.status("dogfood", issued["slot_id"])["slot"]["state"], "expired")
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            termination = bundle["receipts"][-1]
            self.assertEqual(termination["body"]["reason"], "time_expired")
            self.assertNotIn("kill_signal", termination["body"])
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")

            self.assertEqual(orch.sweep_expired("dogfood")["count"], 0)

    def test_exec_refused_after_expiry(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent, minutes=1)
            self._force_expiry(orch, issued["slot_id"])
            with self.assertRaises(ValueError) as ctx:
                orch.exec_("dogfood", issued["slot_id"], "echo late")
            self.assertIn("expired", str(ctx.exception))
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            self.assertEqual(bundle["receipts"][-1]["type"], "task.termination")
            self.assertEqual(bundle["receipts"][-1]["body"]["reason"], "time_expired")

    def test_sweep_scoped_to_tenant(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp))
            orch.add_tenant("other", [agent])
            mine = orch.pass_("dogfood", agent)
            theirs = orch.pass_("other", agent)
            self._force_expiry(orch, mine["slot_id"])
            self._force_expiry(orch, theirs["slot_id"])
            self.assertEqual(orch.sweep_expired("dogfood")["count"], 1)
            self.assertEqual(orch.status("dogfood", mine["slot_id"])["slot"]["state"], "expired")
            self.assertEqual(orch.status("other", theirs["slot_id"])["slot"]["state"], "placed")


class TestKeyHardening(unittest.TestCase):
    def test_gate_key_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            Orchestrator(Path(tmp), gate_id="gate-test")
            mode = stat.S_IMODE(os.stat(Path(tmp) / "gate.key").st_mode)
            self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
