"""Gate-lite orchestrator tests: dogfood pass → exec → settle → terminate."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, verify_bundle  # noqa: E402
from gate_lite.orchestrator import Orchestrator  # noqa: E402


def make_orchestrator(state_dir: Path) -> tuple[Orchestrator, str]:
    agent_did, _agent_key = keys.generate(keys.deterministic_seed("dogfood-agent"))
    gate_did, gate_key = keys.generate(keys.deterministic_seed("gate-test"))
    orch = Orchestrator(state_dir, gate_id="gate-test", gate_key=gate_key, gate_did=gate_did)
    orch.add_tenant("dogfood", [agent_did])
    return orch, agent_did


class TestGateLite(unittest.TestCase):
    def test_full_dogfood_flow_verifies_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_(
                "dogfood",
                agent_did,
                minutes=90,
                spend_cap={"minor": 1000, "currency": "USD"},
            )
            executed = orch.exec_("dogfood", issued["slot_id"], "echo hello")
            self.assertEqual(executed["exit"], 0)
            orch.settle("dogfood", issued["slot_id"], "invoice", "inv-9", 200)
            terminated = orch.terminate("dogfood", issued["slot_id"])

            bundle = orch.receipt(terminated["task_id"])
            result = verify_bundle(bundle)
            self.assertEqual(result.verdict, "TRUSTED", result.errors)
            types = result.summary["types"]
            self.assertIn("delivery.attestation", types)
            self.assertIn("settlement", types)
            self.assertIn("task.termination", types)

    def test_idempotent_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            first = orch.pass_("dogfood", agent_did, idempotency_key="p1")
            second = orch.pass_("dogfood", agent_did, idempotency_key="p1")
            self.assertEqual(first["pass_id"], second["pass_id"])

            exec_first = orch.exec_("dogfood", first["slot_id"], "echo x", idempotency_key="e1")
            exec_second = orch.exec_("dogfood", first["slot_id"], "echo x", idempotency_key="e1")
            self.assertEqual(exec_first["receipt_ids"], exec_second["receipt_ids"])

    def test_cross_tenant_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            orch.add_tenant("other", [agent_did])
            issued = orch.pass_("dogfood", agent_did)
            with self.assertRaises(PermissionError):
                orch.exec_("other", issued["slot_id"], "echo denied")

    def test_unknown_tenant_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            with self.assertRaises(KeyError):
                orch.pass_("nobody", agent_did)

    def test_spend_cap_enforced_at_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_(
                "dogfood", agent_did, spend_cap={"minor": 100, "currency": "USD"}
            )
            with self.assertRaises(ValueError):
                orch.settle("dogfood", issued["slot_id"], "invoice", "inv-over", 500)

    def test_cross_process_chain_continuity(self):
        """CLI reality: every command is a new process; chains must reload from disk."""
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            orch, agent_did = make_orchestrator(state)
            issued = orch.pass_("dogfood", agent_did)

            from continuity_receipt import keys as _keys
            from gate_lite.orchestrator import Orchestrator as _Orch

            _did, gate_key = _keys.generate(_keys.deterministic_seed("gate-test"))
            fresh = _Orch(state, gate_id="gate-test", gate_key=gate_key, gate_did=orch.gate_did)
            fresh.exec_("dogfood", issued["slot_id"], "echo across processes")
            fresh.terminate("dogfood", issued["slot_id"])

            bundle = fresh.receipt(fresh.task_id_for(issued["slot_id"]))
            result = verify_bundle(bundle)
            self.assertEqual(result.verdict, "TRUSTED", result.errors)
            self.assertEqual(
                result.summary["types"],
                ["session.pass.created", "task.decision", "task.execution", "task.termination"],
            )

    def test_receipt_persisted_and_pass_token_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            from gate_lite.tokens import verify_pass

            claims = verify_pass(issued["token"], orch.gate_did)
            self.assertEqual(claims["sub"], agent_did)
            orch.exec_("dogfood", issued["slot_id"], "echo y")
            terminated = orch.terminate("dogfood", issued["slot_id"])
            path = Path(tmp) / "receipts" / f"{terminated['task_id']}.json"
            self.assertTrue(path.exists())
            json.loads(path.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
