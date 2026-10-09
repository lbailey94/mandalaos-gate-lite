#!/usr/bin/env python3
"""Bubblewrap subset adapted from Sovereign 9a0faf1 tests/test_sandbox_argv.py.

Local paths adapted, Landrun cases excluded, and partial-output shim repaired.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / "runners" / "bwrap-v1"


class SandboxArgvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.capture = self.directory / "argv.json"
        capture_script = self.directory / "capture"
        capture_script.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "with open(os.environ['ARGV_CAPTURE'], 'w') as f: json.dump(sys.argv[1:], f)\n"
        )
        capture_script.chmod(0o755)
        self.capture_script = str(capture_script)
        (self.directory / "bwrap").symlink_to(capture_script)

    def run_wrapper(self, script, envelope):
        env = os.environ.copy()
        env["PATH"] = f"{self.directory}:{env['PATH']}"
        env["ARGV_CAPTURE"] = str(self.capture)
        env["WM_SANDBOX_LANDRUN"] = self.capture_script
        env["HOME"] = "/nonexistent"
        result = subprocess.run(
            ["bash", str(ROOT / script), "--exec", json.dumps(envelope)],
            env=env, text=True, capture_output=True,
        )
        captured = json.loads(self.capture.read_text()) if self.capture.exists() else None
        return result, captured

    def test_bwrap_preserves_exact_argument_bytes(self):
        args = ["", "line1\nline2", "tab\tvalue", "ends-with-newline\n"]
        result, captured = self.run_wrapper("mandala-sandbox", {
            "program": "tool", "args": args,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        # bwrap's own argv ends in --, followed by the exact payload argv.
        self.assertEqual(captured[-(len(args) + 1):], ["tool", *args])

    def test_bwrap_writable_workspace_is_explicit_and_scoped(self):
        workspace = self.directory / "workspace"
        workspace.mkdir()
        for writable, flag in ((False, "--ro-bind"), (True, "--bind")):
            self.capture.unlink(missing_ok=True)
            result, captured = self.run_wrapper("mandala-sandbox", {
                "program": "tool", "args": [], "workspace": str(workspace), "rw": writable,
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn([flag, str(workspace), "/workspace"],
                          [captured[i:i + 3] for i in range(len(captured) - 2)])

    def test_bwrap_rejects_missing_writable_workspace_and_nonboolean_rw(self):
        for envelope in (
            {"program": "tool", "workspace": str(self.directory / "missing"), "rw": True},
            {"program": "tool", "rw": "true"},
        ):
            self.capture.unlink(missing_ok=True)
            result, captured = self.run_wrapper("mandala-sandbox", envelope)
            self.assertEqual(result.returncode, 64, result.stderr)
            self.assertIsNone(captured)


    def test_non_string_args_and_malformed_json_fail_before_runner(self):
        for raw in ('{"program":"tool","args":["ok",7]}', '{bad json'):
            env = os.environ.copy()
            env["PATH"] = f"{self.directory}:{env['PATH']}"
            env["ARGV_CAPTURE"] = str(self.capture)
            env["WM_SANDBOX_LANDRUN"] = self.capture_script
            proc = subprocess.run(["bash", str(ROOT / "mandala-sandbox"), "--exec", raw],
                                  env=env, text=True, capture_output=True)
            self.assertEqual(proc.returncode, 64)
            self.assertFalse(self.capture.exists())


    def test_null_args_and_nul_values_fail_closed(self):
        for envelope in (
            {"program": "tool", "args": None},
            {"program": "tool", "args": ["has\x00nul"]},
            {"program": "bad\x00program", "args": []},
        ):
            result, captured = self.run_wrapper("mandala-sandbox", envelope)
            self.assertEqual(result.returncode, 64)
            self.assertIsNone(captured)

    def test_jq_failure_after_partial_output_does_not_spawn_runner(self):
        fake_jq = self.directory / "jq"
        fake_jq.write_text("#!/usr/bin/python3\nimport os, sys\nos.write(1, b\"tool\\0true\\0\\0partial\\0\")\nsys.exit(23)\n")
        fake_jq.chmod(0o755)
        for script in ("mandala-sandbox",):
            env = os.environ.copy()
            env["PATH"] = f"{self.directory}:{env['PATH']}"
            env["ARGV_CAPTURE"] = str(self.capture)
            env["WM_SANDBOX_LANDRUN"] = self.capture_script
            env["HOME"] = "/nonexistent"
            before = set(self.directory.iterdir())
            proc = subprocess.run(
                ["bash", str(ROOT / script), "--exec", '{"program":"tool","args":["x"]}'],
                env=env, text=True, capture_output=True,
            )
            self.assertEqual(proc.returncode, 64, proc.stderr)
            self.assertFalse(self.capture.exists())
            self.assertEqual(set(self.directory.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
