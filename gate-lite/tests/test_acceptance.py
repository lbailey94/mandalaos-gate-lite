"""Acceptance tests G2/G3/G6/G8 + snapshot, on the real containment wrapper.

G2 quota kill (systemd slice), G3 egress deny (bwrap netns), G6 operator kill,
G8 fail-closed emitter. Real-runner tests skip when the host lacks bwrap /
mandala-sandbox / a running systemd user manager.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, verify_bundle  # noqa: E402
from gate_lite.mcp_server import McpServer  # noqa: E402
from gate_lite.orchestrator import (  # noqa: E402
    EmitterError,
    ExecResult,
    Orchestrator,
    SandboxRunner,
    SliceRunner,
)

WRAPPER = (
    os.environ.get("WM_GATELITE_RUNNER")
    or shutil.which("mandala-sandbox")
    or str(Path.home() / ".local" / "bin" / "mandala-sandbox")
)
HAS_SANDBOX = Path(WRAPPER).exists() and shutil.which("bwrap") is not None


def systemd_user_ok() -> bool:
    if not (shutil.which("systemd-run") and shutil.which("systemctl")):
        return False
    try:
        probe = subprocess.run(
            ["systemctl", "--user", "is-system-running"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.stdout.strip() in ("running", "degraded")


HAS_SYSTEMD = systemd_user_ok()


def make_orchestrator(state: Path, runner=None) -> tuple[Orchestrator, str]:
    agent_did, _ = keys.generate(keys.deterministic_seed("dogfood-agent"))
    gate_did, gate_key = keys.generate(keys.deterministic_seed("gate-test"))
    orch = Orchestrator(state, gate_id="gate-test", gate_key=gate_key, gate_did=gate_did, runner=runner)
    orch.add_tenant("dogfood", [agent_did])
    return orch, agent_did


def payload_text(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


class SpyRunner:
    sandbox_class = "spy"

    def __init__(self):
        self.calls = 0

    def run(self, slot, payload_ref, on_spawn=None) -> ExecResult:
        self.calls += 1
        return ExecResult(exit_code=0, stdout_hash="sha256:spy", resources={}, egress=[])


@unittest.skipIf(os.geteuid() == 0, "chmod-based fault injection is bypassed by root")
class TestFailClosedEmitter(unittest.TestCase):
    """G8: receipt emitter down ⇒ exec refused, no work runs."""

    def test_exec_refused_when_emitter_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            spy = SpyRunner()
            orch, agent = make_orchestrator(state, runner=spy)
            issued = orch.pass_("dogfood", agent)
            receipts = state / "receipts"
            os.chmod(receipts, 0o500)
            try:
                with self.assertRaises(EmitterError):
                    orch.exec_("dogfood", issued["slot_id"], "echo nope", token=issued["token"])
            finally:
                os.chmod(receipts, 0o700)

            self.assertEqual(spy.calls, 0)
            self.assertEqual(orch.status("dogfood", issued["slot_id"])["slot"]["state"], "placed")
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            self.assertEqual([r["type"] for r in bundle["receipts"]], ["session.pass.created"])

            recovered = orch.exec_("dogfood", issued["slot_id"], "echo ok", token=issued["token"])
            self.assertEqual(recovered["exit"], 0)
            self.assertEqual(spy.calls, 1)

    def test_mcp_reports_emitter_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            orch, agent = make_orchestrator(state, runner=SpyRunner())
            issued = orch.pass_("dogfood", agent)
            server = McpServer(orch, "dogfood")
            os.chmod(state / "receipts", 0o500)
            try:
                response = server.handle(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "mandala.exec",
                            "arguments": {
                                "agent": agent,
                                "slot": issued["slot_id"],
                                "payload_ref": "echo x",
                                "token": issued["token"],
                            },
                        },
                    }
                )
            finally:
                os.chmod(state / "receipts", 0o700)
            self.assertTrue(response["result"]["isError"])
            self.assertEqual(payload_text(response)["error"], "emitter_unavailable")


class TestOperatorKillIdle(unittest.TestCase):
    """G6 (idle lane): operator kill of a slot with no live run."""

    def test_kill_idle_slot_records_operator(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp))
            issued = orch.pass_("dogfood", agent)
            killed = orch.kill("dogfood", issued["slot_id"])
            self.assertEqual(killed["kill_signal"], "operator")
            self.assertFalse(killed["exec_active"])
            self.assertEqual(orch.status("dogfood", issued["slot_id"])["slot"]["state"], "terminated")
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            termination = bundle["receipts"][-1]
            self.assertEqual(termination["type"], "task.termination")
            self.assertEqual(termination["body"]["kill_signal"], "operator")
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")


@unittest.skipUnless(HAS_SANDBOX, f"needs bwrap + mandala-sandbox ({WRAPPER})")
class TestOperatorKillLive(unittest.TestCase):
    """G6: kill a live sandboxed run within N seconds; receipt `operator`."""

    def test_kill_stops_live_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            orch, agent = make_orchestrator(state, runner=SandboxRunner(WRAPPER))
            issued = orch.pass_("dogfood", agent, minutes=1)

            outcome: dict = {}
            failure: dict = {}

            def run_exec():
                try:
                    outcome.update(
                        orch.exec_("dogfood", issued["slot_id"], "sleep 30", token=issued["token"])
                    )
                except Exception as exc:  # noqa: BLE001 - surfaced by the test
                    failure["exc"] = exc

            worker = threading.Thread(target=run_exec)
            worker.start()
            run_file = state / "runs" / f"{issued['slot_id']}.json"
            deadline = time.time() + 10
            while time.time() < deadline and not run_file.exists():
                time.sleep(0.05)
            self.assertTrue(run_file.exists(), "run was never journaled")

            killer, _ = make_orchestrator(state, runner=SandboxRunner(WRAPPER))
            started = time.time()
            killed = killer.kill("dogfood", issued["slot_id"], wait_s=5.0)
            elapsed_ms = int((time.time() - started) * 1000)
            worker.join(timeout=10)

            self.assertFalse(worker.is_alive(), "exec did not stop after kill")
            self.assertEqual(failure, {})
            self.assertTrue(killed["exec_active"])
            self.assertEqual(killed["kill_signal"], "operator")
            self.assertLess(elapsed_ms, 5000)
            self.assertNotEqual(outcome.get("exit"), 0)
            self.assertEqual(outcome.get("kill_signal"), "operator")

            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            termination = bundle["receipts"][-1]
            self.assertEqual(termination["type"], "task.termination")
            self.assertEqual(termination["body"]["kill_signal"], "operator")
            self.assertLess(termination["body"]["operator_kill_latency_ms"], 5000)
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")


@unittest.skipUnless(HAS_SANDBOX, f"needs bwrap + mandala-sandbox ({WRAPPER})")
class TestEgressDeny(unittest.TestCase):
    """G3: undeclared egress denied + recorded; no reachability."""

    def test_net_without_declared_destinations_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp), runner=SandboxRunner(WRAPPER))
            issued = orch.pass_("dogfood", agent, minutes=1)
            payload_ref = json.dumps(
                {
                    "program": "curl",
                    "args": ["-sS", "-m", "5", "https://example.com"],
                    "net": True,
                    "egress": [],
                }
            )
            executed = orch.exec_("dogfood", issued["slot_id"], payload_ref, token=issued["token"])
            self.assertNotEqual(executed["exit"], 0)

            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            execution = next(r for r in bundle["receipts"] if r["type"] == "task.execution")
            egress = execution["body"]["egress"]
            self.assertEqual(egress[0]["destination"], "undeclared")
            self.assertFalse(egress[0]["allowed"])
            self.assertEqual(egress[0]["bytes"], 0)

    def test_declared_but_unpermitted_destination_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, agent = make_orchestrator(Path(tmp), runner=SandboxRunner(WRAPPER))
            issued = orch.pass_("dogfood", agent, minutes=1)
            payload_ref = json.dumps(
                {
                    "program": "curl",
                    "args": ["-sS", "-m", "5", "https://example.com"],
                    "egress": ["example.com"],
                }
            )
            executed = orch.exec_("dogfood", issued["slot_id"], payload_ref, token=issued["token"])
            self.assertNotEqual(executed["exit"], 0)
            self.assertIn("stderr_hash", executed)

            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            execution = next(r for r in bundle["receipts"] if r["type"] == "task.execution")
            egress = execution["body"]["egress"]
            self.assertEqual(egress[0]["destination"], "example.com")
            self.assertFalse(egress[0]["allowed"])
            self.assertEqual(egress[0]["bytes"], 0)
            orch.terminate("dogfood", issued["slot_id"])
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")


@unittest.skipUnless(HAS_SANDBOX and HAS_SYSTEMD, "needs bwrap + sandbox + systemd user manager")
class TestQuotaKill(unittest.TestCase):
    """G2: quota overrun kills the slot (not the host); termination `quota`."""

    def make_slice_orchestrator(self, state: Path) -> tuple[Orchestrator, str, dict]:
        orch, agent = make_orchestrator(state, runner=SliceRunner(WRAPPER))
        issued = orch.pass_("dogfood", agent, minutes=1)
        return orch, agent, issued

    def shrink(self, orch: Orchestrator, slot_id: str, **quotas) -> None:
        slot = orch.registry.get_slot(slot_id)
        slot["quotas"].update(quotas)
        orch.registry.put_slot(slot)

    @unittest.skipUnless(
        os.environ.get("GATE_LITE_QUOTA_TESTS") == "1",
        "intentionally trips the kernel OOM killer (host notification noise); "
        "set GATE_LITE_QUOTA_TESTS=1 to run",
    )
    def test_memory_overrun_kills_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, _agent, issued = self.make_slice_orchestrator(Path(tmp))
            slot_id = issued["slot_id"]
            self.shrink(orch, slot_id, mem_mb=96)
            payload_ref = json.dumps(
                {"program": "python3", "args": ["-c", "x=bytearray(512*1024*1024); print(len(x))"]}
            )
            executed = orch.exec_("dogfood", slot_id, payload_ref, token=issued["token"])
            self.assertEqual(executed.get("kill_signal"), "quota")
            self.assertEqual(executed.get("reason"), "quota")
            self.assertEqual(orch.status("dogfood", slot_id)["slot"]["state"], "terminated")

            bundle = orch.receipt(orch.task_id_for(slot_id))
            termination = bundle["receipts"][-1]
            self.assertEqual(termination["body"]["kill_signal"], "quota")
            self.assertEqual(termination["body"]["killed_by"], "memory_max")
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")

    def test_wall_overrun_kills_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch, _agent, issued = self.make_slice_orchestrator(Path(tmp))
            slot_id = issued["slot_id"]
            self.shrink(orch, slot_id, wall_ms=2000)
            executed = orch.exec_("dogfood", slot_id, "sleep 30", token=issued["token"])
            self.assertEqual(executed.get("kill_signal"), "quota")
            bundle = orch.receipt(orch.task_id_for(slot_id))
            termination = bundle["receipts"][-1]
            self.assertEqual(termination["body"]["killed_by"], "wall")
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")


@unittest.skipUnless(HAS_SANDBOX, f"needs bwrap + mandala-sandbox ({WRAPPER})")
class TestWorkspaceRoundtrip(unittest.TestCase):
    """G7: runner-written artifacts land in the slot workspace, survive snapshot/restore."""

    def test_sandbox_write_snapshot_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            orch, agent = make_orchestrator(state, runner=SandboxRunner(WRAPPER))
            issued = orch.pass_("dogfood", agent, minutes=2)
            payload_ref = json.dumps(
                {
                    "program": "python3",
                    "args": ["-c", "open('/workspace/artifact.txt','w').write('from the sandbox')"],
                }
            )
            executed = orch.exec_("dogfood", issued["slot_id"], payload_ref, token=issued["token"])
            self.assertEqual(executed["exit"], 0, executed)
            workspace = state / "workspaces" / issued["slot_id"]
            self.assertEqual((workspace / "artifact.txt").read_text(encoding="utf-8"), "from the sandbox")

            snap = orch.snapshot("dogfood", issued["slot_id"])
            orch.terminate("dogfood", issued["slot_id"], reason="destroyed")

            recreated = orch.pass_("dogfood", agent, minutes=2)
            restored = orch.restore("dogfood", recreated["slot_id"], snap["snapshot_id"])
            self.assertEqual(restored["restored_hash"], snap["tree_hash"])
            restored_file = state / "workspaces" / recreated["slot_id"] / "artifact.txt"
            self.assertEqual(restored_file.read_text(encoding="utf-8"), "from the sandbox")


class TestSnapshot(unittest.TestCase):
    """G7 lane: filesystem snapshot freezes the slot and lands a receipt."""

    def test_snapshot_freezes_and_attests_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            orch, agent = make_orchestrator(state)
            issued = orch.pass_("dogfood", agent)
            orch.exec_("dogfood", issued["slot_id"], "echo snap", token=issued["token"])
            workspace = state / "workspaces" / issued["slot_id"]
            (workspace / "note.txt").write_text("dogfood artifact", encoding="utf-8")

            snap = orch.snapshot("dogfood", issued["slot_id"])
            self.assertEqual(snap["state"], "frozen")
            archive = Path(snap["artifact"]["path"])
            self.assertTrue(archive.exists())
            import tarfile

            with tarfile.open(archive) as tar:
                self.assertIn("note.txt", tar.getnames())

            with self.assertRaises(ValueError):
                orch.exec_("dogfood", issued["slot_id"], "echo frozen", token=issued["token"])

            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            attestations = [r for r in bundle["receipts"] if r["type"] == "delivery.attestation"]
            self.assertEqual(len(attestations), 1)
            self.assertEqual(attestations[0]["body"]["artifact"]["sha256"], snap["artifact"]["sha256"])

            orch.terminate("dogfood", issued["slot_id"])
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            self.assertEqual(verify_bundle(bundle).verdict, "TRUSTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
