"""CLI runner guard tests: exec refuses simulated execution unless --demo."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_ctl(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "gate_lite.ctl", *argv],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCtlRunnerGuard(unittest.TestCase):
    def test_exec_refuses_without_runner_or_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_ctl(
                "--state", tmp, "exec", "--tenant", "dogfood", "--slot", "slot-x",
                "--payload-ref", "echo hi", "--token", "dummy-token",
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("refusing to exec", proc.stderr)

    def test_slice_without_runner_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_ctl(
                "--state", tmp, "--slice", "exec", "--tenant", "dogfood", "--slot", "slot-x",
                "--payload-ref", "echo hi", "--token", "dummy-token",
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("requires a runner path", proc.stderr)

    def test_demo_flag_allows_stub_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            added = run_ctl(
                "--state", tmp, "tenant-add", "--tenant", "dogfood",
                "--agent", "did:key:zDemoAgent",
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            passed = run_ctl(
                "--state", tmp, "pass", "--tenant", "dogfood",
                "--agent", "did:key:zDemoAgent",
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            issued = json.loads(passed.stdout)

            proc = run_ctl(
                "--state", tmp, "--demo", "exec", "--tenant", "dogfood",
                "--slot", issued["slot_id"], "--payload-ref", "echo hi",
                "--token", issued["token"],
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["exit"], 0)
            self.assertIn("simulated execution", proc.stderr)

    def test_exec_requires_token_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_ctl(
                "--state", tmp, "--demo", "exec", "--tenant", "dogfood",
                "--slot", "slot-x", "--payload-ref", "echo hi",
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("--token", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
