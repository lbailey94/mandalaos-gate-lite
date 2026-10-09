"""Fail-closed tests for the exact local 0.5 Bubblewrap candidate profile."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gate_lite.orchestrator import (
    Orchestrator,
    RunnerProfileError,
    SandboxRunner,
    StubRunner,
)
from gate_lite import orchestrator as profile_module


class TestRunnerProfileFailClosed(unittest.TestCase):
    def make_runner(self, path: Path) -> SandboxRunner:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)
        return SandboxRunner(str(path))

    def test_missing_profile_is_unknown_and_refuses_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner"
            runner = self.make_runner(path)
            self.assertEqual(runner.sandbox_class, "unknown")
            self.assertIsNone(runner.profile_id)
            self.assertEqual(runner.profile_status, "unqualified")
            with self.assertRaisesRegex(RunnerProfileError, "no reviewed runner profile"):
                runner.run({}, "echo should-not-run", on_spawn=lambda *_: self.fail("spawned"))

    def test_missing_runner_executable_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RunnerProfileError, "identity unavailable"):
                SandboxRunner(str(Path(tmp) / "missing"))

    def test_matching_wrapper_still_requires_pinned_bwrap_and_jq(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner"
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o700)
            digest = SandboxRunner._digest(str(path))
            with patch.object(profile_module, "PROFILE_WRAPPER_SHA256", digest), patch.object(SandboxRunner, "_dependencies_match", return_value=True):
                runner = SandboxRunner(str(path))
                self.assertEqual(runner.sandbox_class, "bwrap")
                self.assertEqual(runner.profile_status, "locally_qualified")
                with patch.object(profile_module.shutil, "which", return_value=None):
                    with self.assertRaisesRegex(RunnerProfileError, "dependency identity mismatch: bwrap"):
                        runner.run({}, "echo should-not-run", on_spawn=lambda *_: self.fail("spawned"))

    def test_profile_binds_exact_argv_and_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner"
            runner = self.make_runner(path)
            first = runner.profile_for({"workspace": "/tmp/w"}, "echo first")
            second = runner.profile_for({"workspace": "/tmp/w"}, "echo second")
            self.assertEqual(first["executable_digest"], runner.runner_digest)
            self.assertEqual(first["profile_id"], profile_module.PROFILE_ID)
            self.assertNotEqual(first["invocation_digest"], second["invocation_digest"])

    def test_non_executable_runner_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner"
            path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaisesRegex(RunnerProfileError, "not runnable"):
                SandboxRunner(str(path))

    def test_changed_executable_fails_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner"
            runner = self.make_runner(path)
            path.write_text("#!/bin/sh\necho changed\n", encoding="utf-8")
            with self.assertRaisesRegex(RunnerProfileError, "identity changed"):
                runner.run({}, "echo should-not-run", on_spawn=lambda *_: self.fail("spawned"))

    def test_class_mismatch_fails_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.make_runner(Path(tmp) / "runner")
            runner.sandbox_class = "bwrap-landlock"
            with self.assertRaisesRegex(RunnerProfileError, "class mismatch"):
                runner.run({}, "echo should-not-run", on_spawn=lambda *_: self.fail("spawned"))

    def test_profile_identity_tampering_fails_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.make_runner(Path(tmp) / "runner")
            runner.profile_id = "urn:forged:profile"
            with self.assertRaisesRegex(RunnerProfileError, "profile identity mismatch"):
                runner.run({}, "echo should-not-run", on_spawn=lambda *_: self.fail("spawned"))

    def test_profile_status_tampering_fails_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.make_runner(Path(tmp) / "runner")
            runner.profile_status = "locally_qualified"
            with self.assertRaisesRegex(RunnerProfileError, "profile status mismatch"):
                runner.run({}, "echo should-not-run", on_spawn=lambda *_: self.fail("spawned"))

    def test_status_reports_runner_identity_and_stub_receipt_class_agrees(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "runner"
            runner = self.make_runner(runner_path)
            orch = Orchestrator(Path(tmp) / "state", runner=runner)
            orch.add_tenant("tenant", ["did:key:test"])
            issued = orch.pass_("tenant", "did:key:test")
            # A real run is refused, and no execution receipt is emitted.
            with self.assertRaises(RunnerProfileError):
                orch.exec_("tenant", issued["slot_id"], "echo blocked", token=issued["token"])
            # A second attempt with the same token must reach the profile gate
            # again, rather than fail as a replay of a token no run consumed.
            with self.assertRaises(RunnerProfileError):
                orch.exec_("tenant", issued["slot_id"], "echo blocked", token=issued["token"])
            status = orch.status("tenant", issued["slot_id"])["runner"]
            self.assertEqual(status["class"], "unknown")
            self.assertEqual(status["path"], str(runner_path.resolve()))
            self.assertEqual(status["executable_sha256"], runner.runner_digest)
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            self.assertFalse(any(r["type"] == "task.execution" for r in bundle["receipts"]))
            self.assertFalse(any(r["type"] == "task.decision" for r in bundle["receipts"]))

    def test_stub_status_identity_is_explicitly_simulated(self):
        with tempfile.TemporaryDirectory() as tmp:
            orch = Orchestrator(tmp, runner=StubRunner())
            orch.add_tenant("tenant", ["did:key:test"])
            issued = orch.pass_("tenant", "did:key:test")
            orch.exec_("tenant", issued["slot_id"], "echo simulated", token=issued["token"])
            info = orch.status("tenant", issued["slot_id"])["runner"]
            bundle = orch.receipt(orch.task_id_for(issued["slot_id"]))
            execution = next(r for r in bundle["receipts"] if r["type"] == "task.execution")
            self.assertEqual(info["class"], execution["body"]["sandbox_class"])
            self.assertTrue(info["simulated"])
            self.assertEqual(info["profile_status"], "simulated")
            self.assertEqual(bundle["spec"], "continuity-receipt/0.5")

    def test_cached_exec_cannot_bypass_unqualified_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.make_runner(Path(tmp) / "runner")
            orch = Orchestrator(Path(tmp) / "state", runner=runner)
            orch.add_tenant("tenant", ["did:key:test"])
            issued = orch.pass_("tenant", "did:key:test")
            slot_id = issued["slot_id"]
            orch.registry.remember(
                f"exec:tenant:{slot_id}:old",
                {"request": {"payload_ref": "echo old"}, "result": {"exit": 0}},
            )
            with self.assertRaises(RunnerProfileError):
                orch.exec_("tenant", slot_id, "echo old", idempotency_key="old", token=issued["token"])

    def test_unexpected_receipt_dependency_version_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("importlib.metadata.version", return_value="0.5.1"):
                with self.assertRaisesRegex(RuntimeError, "expected continuity-receipt==0.5.0"):
                    Orchestrator(tmp)

    def test_imported_receipt_code_must_support_pinned_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("gate_lite.orchestrator.records.SUPPORTED_SPECS", ()):
                with self.assertRaisesRegex(RuntimeError, "does not support.*continuity-receipt/0.5"):
                    Orchestrator(tmp)


if __name__ == "__main__":
    unittest.main()
