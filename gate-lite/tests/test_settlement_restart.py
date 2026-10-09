"""Settlement recovers execution hashes across independent CLI processes."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from continuity_receipt import keys
from continuity_receipt.canon import sha256_prefixed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gate_lite.orchestrator import Orchestrator, StubRunner  # noqa: E402


class TestSettlementRestart(unittest.TestCase):
    def test_delivery_response_hash_comes_from_persisted_execution_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            agent_did, _ = keys.generate(keys.deterministic_seed("settlement-restart-agent"))
            orch = Orchestrator(state, gate_id="settlement-restart", runner=StubRunner())
            orch.add_tenant("tenant", [agent_did])
            issued = orch.pass_("tenant", agent_did)
            execution_result = orch.exec_(
                "tenant", issued["slot_id"], "echo durable result", token=issued["token"]
            )
            bundle_before = orch.receipt(orch.task_id_for(issued["slot_id"]))
            execution = next(
                receipt for receipt in reversed(bundle_before["receipts"])
                if receipt["type"] == "task.execution"
            )
            expected_hash = execution["body"]["tool_calls"][0]["result_hash"]
            self.assertEqual(execution_result["stdout_hash"], expected_hash)

            # A new interpreter has no access to the first process's
            # _last_exec cache. It must read the persisted execution receipt.
            child_code = (
                "import json,sys; "
                "from gate_lite.orchestrator import Orchestrator; "
                "o=Orchestrator(sys.argv[1]); "
                "print(json.dumps(o.settle('tenant',sys.argv[2],'invoice','restart-invoice',0)))"
            )
            child_env = os.environ.copy()
            child_env["PYTHONPATH"] = str(ROOT) + os.pathsep + child_env.get("PYTHONPATH", "")
            completed = subprocess.run(
                [sys.executable, "-c", child_code, str(state), issued["slot_id"]],
                check=True, capture_output=True, text=True, env=child_env,
            )
            self.assertEqual(json.loads(completed.stdout)["type"], "settlement")
            bundle_after = orch.receipt(orch.task_id_for(issued["slot_id"]))
            delivery = next(
                receipt for receipt in reversed(bundle_after["receipts"])
                if receipt["type"] == "delivery.attestation"
            )
            self.assertEqual(delivery["body"]["response_hash"], expected_hash)
            self.assertNotEqual(delivery["body"]["response_hash"], sha256_prefixed(b"none"))

    def test_pre_execution_settlement_keeps_explicit_none_sentinel(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent_did, _ = keys.generate(keys.deterministic_seed("settlement-empty-agent"))
            orch = Orchestrator(Path(tmp) / "state", runner=StubRunner())
            orch.add_tenant("tenant", [agent_did])
            issued = orch.pass_("tenant", agent_did)
            orch.settle("tenant", issued["slot_id"], "invoice", "empty-invoice", 0)
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            delivery = next(r for r in bundle["receipts"] if r["type"] == "delivery.attestation")
            self.assertEqual(delivery["body"]["response_hash"], sha256_prefixed(b"none"))


if __name__ == "__main__":
    unittest.main()
