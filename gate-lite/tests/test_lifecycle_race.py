"""Lifecycle race regression tests — gate-lite issue #1.

The reported race: `kill`/expiry could seal a terminal receipt while `exec_`
was between its state check and its spawn, so a process could start after the
seal and receipt ordering broke (termination before decision/execution).

These tests force the interleaving with a gated runner and assert the four
acceptance criteria from the issue:
  1. no process starts after a terminal or expiry seal;
  2. a pre-start race returns an explicit rejected/unknown outcome and emits
     no `task.execution`;
  3. receipt ordering is monotonic (decision → execution → termination);
  4. a kill request is bound to a slot/run generation, so a late start cannot
     consume an old request.
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys  # noqa: E402
from gate_lite.models import now_epoch  # noqa: E402
from gate_lite.orchestrator import ExecResult, Orchestrator  # noqa: E402


def make_orchestrator(state_dir: Path, runner) -> tuple[Orchestrator, str]:
    agent_did, _agent_key = keys.generate(keys.deterministic_seed("race-agent"))
    gate_did, gate_key = keys.generate(keys.deterministic_seed("race-gate"))
    orch = Orchestrator(
        state_dir, gate_id="race-gate", gate_key=gate_key, gate_did=gate_did, runner=runner
    )
    orch.add_tenant("race", [agent_did])
    return orch, agent_did


def wait_until(pred, timeout=5.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return False


def receipt_types(orch: Orchestrator, slot_id: str) -> list[str]:
    bundle = orch.receipt(orch.task_id_for(slot_id))
    return [r["type"] for r in bundle["receipts"]]


class GatedRunner:
    """Runner whose spawn and completion are gated by events.

    `gate_before_spawn` blocks the runner between the start reservation and
    `on_spawn` — exactly the window the issue describes. `live_pid` journals a
    live pid plus a no-op systemd unit so the kill path can be exercised
    without signalling the test process.
    """

    sandbox_class = "gated-test"

    def __init__(self, gate_before_spawn=False, live_pid=False):
        self.before_spawn = threading.Event()
        if gate_before_spawn:
            self.before_spawn.set()
        self.allow_spawn = threading.Event()
        self.spawned = threading.Event()
        self.release = threading.Event()
        self.live_pid = live_pid
        self.calls = 0

    def run(self, slot, payload_ref, on_spawn=None):
        self.calls += 1
        if self.before_spawn.is_set():
            self.allow_spawn.wait(5)
        pid = os.getpid() if self.live_pid else 4242
        unit = "gate-test-noop" if self.live_pid else None
        if on_spawn:
            on_spawn(pid, None, unit)
        self.spawned.set()
        self.release.wait(5)
        return ExecResult(
            exit_code=0,
            stdout_hash="sha256:gated",
            resources={},
            egress=[],
        )


class TestLifecycleRace(unittest.TestCase):
    def test_kill_during_start_defers_and_keeps_receipts_monotonic(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = GatedRunner(gate_before_spawn=True)
            orch, agent = make_orchestrator(Path(tmp), runner)
            issued = orch.pass_("race", agent)
            slot_id = issued["slot_id"]

            result: list = []
            thread = threading.Thread(
                target=lambda: result.append(orch.exec_("race", slot_id, "echo gated"))
            )
            thread.start()
            self.assertTrue(
                wait_until(
                    lambda: orch.registry.get_slot(slot_id)["state"] == "starting"
                ),
                "exec must reserve the slot before spawning",
            )

            killed = orch.kill("race", slot_id, wait_s=0.3)
            self.assertEqual(killed["outcome"], "deferred", killed)
            self.assertEqual(orch.registry.get_slot(slot_id)["state"], "starting")
            self.assertNotIn("task.termination", receipt_types(orch, slot_id))

            runner.allow_spawn.set()
            runner.release.set()
            thread.join(10)

            self.assertEqual(
                receipt_types(orch, slot_id),
                [
                    "session.pass.created",
                    "task.decision",
                    "task.execution",
                    "task.termination",
                ],
                "termination must follow execution (monotonic receipts)",
            )
            self.assertEqual(orch.registry.get_slot(slot_id)["state"], "terminated")
            self.assertEqual(result[0]["kill_signal"], "operator")

    def test_expiry_during_start_defers_to_post_run_seal(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = GatedRunner(gate_before_spawn=True)
            orch, agent = make_orchestrator(Path(tmp), runner)
            issued = orch.pass_("race", agent)
            slot_id = issued["slot_id"]

            thread = threading.Thread(
                target=lambda: orch.exec_("race", slot_id, "echo gated")
            )
            thread.start()
            self.assertTrue(
                wait_until(
                    lambda: orch.registry.get_slot(slot_id)["state"] == "starting"
                )
            )

            stale = orch.registry.get_slot(slot_id)
            stale["expires_at"] = now_epoch() - 1
            orch.registry.put_slot(stale)

            swept = orch.sweep_expired("race")
            self.assertEqual(swept["count"], 0, "sweep must not seal mid-start")
            self.assertEqual(orch.registry.get_slot(slot_id)["state"], "starting")

            runner.allow_spawn.set()
            runner.release.set()
            thread.join(10)

            types = receipt_types(orch, slot_id)
            self.assertEqual(
                types,
                [
                    "session.pass.created",
                    "task.decision",
                    "task.execution",
                    "task.termination",
                ],
            )
            self.assertEqual(orch.registry.get_slot(slot_id)["state"], "expired")
            bundle = orch.receipt(orch.task_id_for(slot_id))
            last = bundle["receipts"][-1]
            self.assertEqual(last["body"]["reason"], "time_expired")

    def test_stale_kill_request_cannot_bind_a_late_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = GatedRunner()
            orch, agent = make_orchestrator(Path(tmp), runner)
            issued = orch.pass_("race", agent)
            slot_id = issued["slot_id"]

            orch._write_kill_request(slot_id, "SIGTERM", 999)
            executed = orch.exec_("race", slot_id, "echo stale")
            self.assertNotIn("kill_signal", executed)
            self.assertEqual(
                receipt_types(orch, slot_id),
                ["session.pass.created", "task.decision", "task.execution"],
                "an old-generation request must not terminate a new run",
            )
            self.assertEqual(orch.registry.get_slot(slot_id)["state"], "active")

    def test_start_rejected_after_seal_emits_no_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = GatedRunner()
            orch, agent = make_orchestrator(Path(tmp), runner)
            issued = orch.pass_("race", agent)
            slot_id = issued["slot_id"]

            orch.terminate("race", slot_id)
            with self.assertRaises(ValueError):
                orch.exec_("race", slot_id, "echo nope")
            self.assertEqual(runner.calls, 0, "no process may start after a seal")
            self.assertEqual(
                receipt_types(orch, slot_id),
                ["session.pass.created", "task.termination"],
                "a rejected start emits no decision/execution",
            )

    def test_kill_live_run_terminates_after_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = GatedRunner(live_pid=True)
            orch, agent = make_orchestrator(Path(tmp), runner)
            issued = orch.pass_("race", agent)
            slot_id = issued["slot_id"]

            thread = threading.Thread(
                target=lambda: orch.exec_("race", slot_id, "echo live")
            )
            thread.start()
            self.assertTrue(wait_until(runner.spawned.is_set))

            threading.Timer(0.3, runner.release.set).start()
            killed = orch.kill("race", slot_id, wait_s=2.0)
            thread.join(10)

            self.assertEqual(killed["state"], "terminated", killed)
            self.assertEqual(
                receipt_types(orch, slot_id),
                [
                    "session.pass.created",
                    "task.decision",
                    "task.execution",
                    "task.termination",
                ],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
