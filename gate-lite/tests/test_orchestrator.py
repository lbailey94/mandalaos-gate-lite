"""Gate-lite orchestrator tests: dogfood pass → exec → settle → terminate."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, verify_bundle  # noqa: E402
from gate_lite.orchestrator import Orchestrator, PassError  # noqa: E402


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
            executed = orch.exec_("dogfood", issued["slot_id"], "echo hello", token=issued["token"])
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

            exec_first = orch.exec_(
                "dogfood", first["slot_id"], "echo x", idempotency_key="e1", token=first["token"]
            )
            exec_second = orch.exec_(
                "dogfood", first["slot_id"], "echo x", idempotency_key="e1", token=first["token"]
            )
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
            fresh.exec_("dogfood", issued["slot_id"], "echo across processes", token=issued["token"])
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
            orch.exec_("dogfood", issued["slot_id"], "echo y", token=issued["token"])
            terminated = orch.terminate("dogfood", issued["slot_id"])
            path = Path(tmp) / "receipts" / f"{terminated['task_id']}.json"
            self.assertTrue(path.exists())
            json.loads(path.read_text())


    def test_pass_claims_and_receipt_binding(self):
        """S2b: the pass token carries pass/slot/mandate identity and the
        receipt's session.pass.created commits the token (pass_token_id)."""
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            from gate_lite.tokens import verify_pass
            from continuity_receipt.canon import sha256_prefixed

            claims = verify_pass(issued["token"], orch.gate_did)
            self.assertEqual(claims["pass_id"], issued["pass_id"])
            self.assertEqual(claims["slot_id"], issued["slot_id"])
            expected_mandate = sha256_prefixed(f"mandate:{issued['pass_id']}".encode())
            self.assertEqual(claims["mandate_ref"], expected_mandate)

            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            body = bundle["receipts"][0]["body"]
            self.assertEqual(body["mandate_ref"], expected_mandate)
            self.assertEqual(
                body["pass_token_id"], sha256_prefixed(issued["token"].encode("ascii"))
            )


    def test_status_reports_effective_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            status = orch.status("dogfood", issued["slot_id"])
            self.assertEqual(status["runner"]["class"], "stub")
            self.assertTrue(status["runner"]["simulated"])


    def test_pass_rejects_unregistered_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, _agent_did = make_orchestrator(Path(tmp))
            with self.assertRaises(PassError) as ctx:
                orch.pass_("dogfood", "did:key:zNobody")
            self.assertEqual(ctx.exception.code, "agent_not_registered")

    def test_exec_requires_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            with self.assertRaises(PassError) as ctx:
                orch.exec_("dogfood", issued["slot_id"], "echo no-token")
            self.assertEqual(ctx.exception.code, "token_required")

    def test_exec_rejects_token_for_other_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            with self.assertRaises(PassError) as ctx:
                orch.exec_(
                    "dogfood",
                    issued["slot_id"],
                    "echo other",
                    token=issued["token"],
                    agent_id="did:key:zOther",
                )
            self.assertEqual(ctx.exception.code, "token_subject_mismatch")
            # A rejected attempt must not burn the token.
            executed = orch.exec_("dogfood", issued["slot_id"], "echo ok", token=issued["token"])
            self.assertEqual(executed["exit"], 0)

    def test_replay_rejected_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            orch, agent_did = make_orchestrator(state)
            issued = orch.pass_("dogfood", agent_did)
            first = orch.exec_("dogfood", issued["slot_id"], "echo once", token=issued["token"])
            self.assertEqual(first["exit"], 0)

            _did, gate_key = keys.generate(keys.deterministic_seed("gate-test"))
            restarted = Orchestrator(
                state, gate_id="gate-test", gate_key=gate_key, gate_did=orch.gate_did
            )
            with self.assertRaises(PassError) as ctx:
                restarted.exec_(
                    "dogfood", issued["slot_id"], "echo again", token=issued["token"]
                )
            self.assertEqual(ctx.exception.code, "pass_replayed")

    def test_replay_holds_under_concurrent_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            workers = 8
            barrier = threading.Barrier(workers)
            outcomes: list[tuple[str, object]] = []

            def attempt():
                barrier.wait()
                try:
                    outcomes.append(
                        (
                            "ok",
                            orch.exec_(
                                "dogfood", issued["slot_id"], "echo race", token=issued["token"]
                            ),
                        )
                    )
                except PassError as exc:
                    outcomes.append(("err", exc.code))

            threads = [threading.Thread(target=attempt) for _ in range(workers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(15)

            self.assertEqual(len(outcomes), workers, outcomes)
            winners = [o for o in outcomes if o[0] == "ok"]
            replays = [o for o in outcomes if o[1] == "pass_replayed"]
            self.assertEqual(len(winners), 1, outcomes)
            self.assertEqual(len(replays), workers - 1, outcomes)


    def test_exec_idempotent_replay_requires_token(self):
        """#203: cached exec results must not be returned without authorization."""
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            first = orch.exec_(
                "dogfood",
                issued["slot_id"],
                "echo cached",
                idempotency_key="k1",
                token=issued["token"],
            )
            self.assertEqual(first["exit"], 0)
            with self.assertRaises(PassError) as ctx:
                orch.exec_("dogfood", issued["slot_id"], "echo cached", idempotency_key="k1")
            self.assertEqual(ctx.exception.code, "token_required")

    def test_exec_idempotent_replay_denies_cross_tenant(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            orch.add_tenant("other", [agent_did])
            issued = orch.pass_("dogfood", agent_did)
            orch.exec_(
                "dogfood",
                issued["slot_id"],
                "echo cached",
                idempotency_key="k1",
                token=issued["token"],
            )
            with self.assertRaises(PermissionError):
                orch.exec_(
                    "other",
                    issued["slot_id"],
                    "echo cached",
                    idempotency_key="k1",
                    token=issued["token"],
                )

    def test_exec_idempotency_keys_are_tenant_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            orch.add_tenant("other", [agent_did])
            first = orch.pass_("dogfood", agent_did)
            second = orch.pass_("other", agent_did)
            a = orch.exec_(
                "dogfood", first["slot_id"], "echo a", idempotency_key="shared", token=first["token"]
            )
            b = orch.exec_(
                "other", second["slot_id"], "echo b", idempotency_key="shared", token=second["token"]
            )
            self.assertEqual(a["slot_id"], first["slot_id"])
            self.assertEqual(b["slot_id"], second["slot_id"])

    def test_exec_idempotency_key_rejects_changed_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent_did)
            orch.exec_(
                "dogfood", issued["slot_id"], "echo one", idempotency_key="k1", token=issued["token"]
            )
            with self.assertRaises(ValueError) as ctx:
                orch.exec_(
                    "dogfood", issued["slot_id"], "echo two", idempotency_key="k1", token=issued["token"]
                )
            self.assertIn("different request", str(ctx.exception))

    def test_pass_idempotent_replay_requires_membership(self):
        """#204: cached passes (with tokens) must not bypass membership."""
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            first = orch.pass_("dogfood", agent_did, idempotency_key="p1")
            with self.assertRaises(PassError) as ctx:
                orch.pass_("dogfood", "did:key:zNobody", idempotency_key="p1")
            self.assertEqual(ctx.exception.code, "agent_not_registered")
            with self.assertRaises(KeyError):
                orch.pass_("nobody", agent_did, idempotency_key="p1")
            again = orch.pass_("dogfood", agent_did, idempotency_key="p1")
            self.assertEqual(again["pass_id"], first["pass_id"])
            self.assertEqual(again["token"], first["token"])

    def test_pass_idempotency_keys_are_tenant_agent_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_a = make_orchestrator(Path(tmp))
            agent_b, _ = keys.generate(keys.deterministic_seed("dogfood-agent-2"))
            orch.add_tenant("dogfood", [agent_a, agent_b])
            a = orch.pass_("dogfood", agent_a, idempotency_key="shared")
            b = orch.pass_("dogfood", agent_b, idempotency_key="shared")
            self.assertNotEqual(a["pass_id"], b["pass_id"])
            self.assertNotEqual(a["token"], b["token"])

    def test_pass_idempotency_key_rejects_changed_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent_did = make_orchestrator(Path(tmp))
            orch.pass_("dogfood", agent_did, minutes=30, idempotency_key="p1")
            with self.assertRaises(ValueError) as ctx:
                orch.pass_("dogfood", agent_did, minutes=60, idempotency_key="p1")
            self.assertIn("different request", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
