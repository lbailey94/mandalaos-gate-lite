"""CLI runner guard tests: exec refuses simulated execution unless --demo."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from test_env import controlled_test_env  # noqa: E402


def run_ctl(*argv: str, input_text=None, env_overrides: dict[str, str | None] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "gate_lite.ctl", *argv],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        input=input_text,
        timeout=30,
        env=controlled_test_env(overrides=env_overrides),
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

    def test_intentional_runner_and_slice_environment_is_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "runner"
            runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            runner.chmod(0o700)
            proc = run_ctl(
                "--state", tmp, "--slice", "tenant-add", "--tenant", "dogfood",
                "--agent", "did:key:zDemoAgent",
                env_overrides={"WM_GATELITE_RUNNER": str(runner), "WM_GATELITE_SLICE": "1"},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

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
                "--token-stdin",
                input_text=issued["token"] + "\n",
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

    def test_empty_stdin_token_is_structured_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_ctl(
                "--state", tmp, "--demo", "exec", "--tenant", "dogfood",
                "--slot", "slot-x", "--payload-ref", "echo hi", "--token-stdin",
                input_text="",
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stderr)["error"], "token_required")
            self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
