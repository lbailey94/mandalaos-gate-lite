"""Structured dependency and runner-profile refusal coverage."""
import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gate_lite.errors import PreflightError  # noqa: E402
from gate_lite.mcp_server import McpServer  # noqa: E402
from gate_lite.orchestrator import Orchestrator, SandboxRunner  # noqa: E402


class TestPreflightErrors(unittest.TestCase):
    def test_dependency_version_mismatch_has_stable_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("importlib.metadata.version", return_value="0.5.1"):
                with self.assertRaises(PreflightError) as caught:
                    Orchestrator(tmp)
        error = caught.exception.as_dict()
        self.assertEqual(error["error"], "dependency_version_mismatch")
        self.assertEqual(error["expected"], "continuity-receipt==0.5.0")
        self.assertEqual(error["found"], "0.5.1")
        self.assertTrue(error["action"])

    def test_missing_runtime_is_typed(self):
        import gate_lite.orchestrator as orchestrator
        missing = ModuleNotFoundError("continuity_receipt not found", name="continuity_receipt")
        with patch.object(orchestrator, "RECEIPT_IMPORT_ERROR", missing):
            with self.assertRaises(PreflightError) as caught:
                Orchestrator("unused")
        self.assertEqual(caught.exception.code, "dependency_missing")

    def test_imported_runtime_version_must_match_exact_distribution_before_state_creation(self):
        import gate_lite.orchestrator as orchestrator
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            self.assertIn("continuity-receipt/0.5", orchestrator.records.SUPPORTED_SPECS)
            with patch("importlib.metadata.version", return_value="0.5.0"):
                with patch.object(orchestrator, "RECEIPT_RUNTIME_VERSION", "0.4.0"):
                    with self.assertRaises(PreflightError) as caught:
                        Orchestrator(state)
            self.assertFalse(state.exists())
            self.assertFalse((state / "gate.key").exists())
        error = caught.exception.as_dict()
        self.assertEqual(error["error"], "dependency_runtime_mismatch")
        self.assertEqual(error["expected"], "continuity-receipt==0.5.0")
        self.assertEqual(error["found"], "0.4.0")
        self.assertEqual(error["action"], "reinstall continuity-receipt==0.5.0")

    def test_cli_imported_runtime_drift_is_typed_and_creates_no_state_or_key(self):
        code = (
            "import importlib.metadata,sys; "
            "importlib.metadata.version=lambda _: '0.5.0'; "
            "import gate_lite.orchestrator as o; o.RECEIPT_RUNTIME_VERSION='0.4.0'; "
            "from gate_lite.ctl import main; "
            "sys.exit(main(['--state',sys.argv[1],'status','--tenant','t','--slot','s']))"
        )
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            proc = subprocess.run(
                [sys.executable, "-c", code, str(state)], cwd=ROOT, capture_output=True,
                text=True, timeout=20, env=self.clean_env(),
            )
            self.assertFalse(state.exists())
            self.assertFalse((state / "gate.key").exists())
        self.assertEqual(proc.returncode, 3)
        error = json.loads(proc.stderr)
        self.assertEqual(error["error"], "dependency_runtime_mismatch")
        self.assertEqual(error["expected"], "continuity-receipt==0.5.0")
        self.assertEqual(error["found"], "0.4.0")
        self.assertNotIn("Traceback", proc.stderr)

    def test_mcp_imported_runtime_drift_is_typed_and_creates_no_state_or_key(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "mandala.status", "arguments": {"slot": "x"}}},
        ]
        code = (
            "import importlib.metadata,sys; "
            "importlib.metadata.version=lambda _: '0.5.0'; "
            "import gate_lite.orchestrator as o; o.RECEIPT_RUNTIME_VERSION='0.4.0'; "
            "from gate_lite.mcp_server import main; "
            "sys.exit(main(['--state',sys.argv[1],'--tenant','t','--demo']))"
        )
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            proc = subprocess.run(
                [sys.executable, "-c", code, str(state)], cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                capture_output=True, text=True, timeout=20, env=self.clean_env(),
            )
            self.assertFalse(state.exists())
            self.assertFalse((state / "gate.key").exists())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        responses = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2])
        refusal = json.loads(responses[1]["result"]["content"][0]["text"])
        self.assertEqual(refusal["error"], "dependency_runtime_mismatch")
        self.assertEqual(refusal["expected"], "continuity-receipt==0.5.0")
        self.assertEqual(refusal["found"], "0.4.0")

    def test_imported_runtime_must_support_pinned_spec(self):
        import gate_lite.orchestrator as orchestrator
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(orchestrator.records, "SUPPORTED_SPECS", ()):
                with self.assertRaises(PreflightError) as caught:
                    Orchestrator(tmp)
        self.assertEqual(caught.exception.code, "dependency_spec_unsupported")
        self.assertEqual(caught.exception.expected, "continuity-receipt/0.5")

    def test_disappearing_runner_dependency_is_a_typed_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner"
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
            # Establish the fixture's reviewed identity during inspection;
            # changing profile_id afterwards correctly hits the tamper guard.
            wrapper_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            with patch("gate_lite.orchestrator.PROFILE_WRAPPER_SHA256", wrapper_digest):
                with patch.object(SandboxRunner, "_dependencies_match", return_value=True):
                    runner = SandboxRunner(str(path))
            with patch("gate_lite.orchestrator.shutil.which", return_value="/missing/bwrap"):
                with patch.object(runner, "_digest", side_effect=[runner.runner_digest, OSError("vanished")]):
                    with self.assertRaises(PreflightError) as caught:
                        runner._require_profile()
        self.assertEqual(caught.exception.code, "runner_dependency_unavailable")
        self.assertEqual(caught.exception.expected, "sha256:e318903862396f96de3df57264e0158682b952fd3fb53ac23d876413e7b30f71")
        self.assertEqual(caught.exception.found, "unavailable")

    def test_cli_construction_refusal_is_json_without_traceback(self):
        code = (
            "import importlib.metadata,sys; "
            "importlib.metadata.version=lambda _: '0.5.1'; "
            "from gate_lite.ctl import main; "
            "sys.exit(main(['--state',sys.argv[1],'status','--tenant','t','--slot','s']))"
        )
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-c", code, tmp], cwd=ROOT, capture_output=True,
                text=True, timeout=20, env=self.clean_env(),
            )
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(json.loads(proc.stderr)["error"], "dependency_version_mismatch")
        self.assertNotIn("Traceback", proc.stderr)

    def test_mcp_startup_refusal_keeps_stdio_request_loop_alive(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "mandala.status", "arguments": {"slot": "x"}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "mandala.list", "arguments": {}}},
        ]
        code = (
            "import importlib.metadata,sys; "
            "importlib.metadata.version=lambda _: '0.5.1'; "
            "from gate_lite.mcp_server import main; "
            "sys.exit(main(['--state',sys.argv[1],'--tenant','t','--demo']))"
        )
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, "-c", code, tmp], cwd=ROOT,
                input="\n".join(json.dumps(item) for item in requests) + "\n",
                capture_output=True, text=True, timeout=20, env=self.clean_env(),
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        responses = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3])
        for response in responses[1:]:
            body = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(body["error"], "dependency_version_mismatch")
            self.assertIn("expected", body["detail"])

    def test_mcp_profile_refusal_precedes_token_burn_and_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "unreviewed-runner"
            marker = Path(tmp) / "payload-ran"
            runner_path.write_text(f"#!/bin/sh\ntouch {marker}\n")
            runner_path.chmod(0o755)
            orch = Orchestrator(Path(tmp) / "state", runner=SandboxRunner(str(runner_path)))
            agent = "did:key:profile-test"
            orch.add_tenant("tenant", [agent])
            server = McpServer(orch, "tenant")

            def call(name, arguments):
                response = server.handle({
                    "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                })
                return json.loads(response["result"]["content"][0]["text"])

            issued = call("mandala.pass", {"agent": agent})
            args = {
                "agent": agent, "slot": issued["slot_id"], "payload_ref": f"touch {marker}",
                "token": issued["token"],
            }
            refusal = call("mandala.exec", args)
            retry = call("mandala.exec", args)
            self.assertEqual(refusal["error"], "runner_profile_refused")
            self.assertEqual(retry["error"], "runner_profile_refused")
            self.assertEqual(refusal["expected"], "urn:mandala:runner-profile:bwrap-v1")
            self.assertTrue(refusal["action"])
            self.assertFalse(marker.exists())
            self.assertEqual(list(orch.runs_dir.iterdir()), [])

    @staticmethod
    def clean_env():
        env = os.environ.copy()
        env.pop("WM_GATELITE_RUNNER", None)
        env.pop("WM_GATELITE_SLICE", None)
        return env


if __name__ == "__main__":
    unittest.main()
