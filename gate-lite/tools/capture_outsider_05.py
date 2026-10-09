#!/usr/bin/env python3
"""Capture a bounded 0.5 CLI rehearsal with tokens confined to process memory.

The execution child observes the exact Registry.reload() snapshot consumed by
the production commitment method. It does not change the returned snapshot or
commitment. Evidence excludes the signing key and runtime database. This tool
records the supplied source SHA/status; remotely frozen qualification requires
the operator to verify that provenance before invoking it on a fresh export.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def digest_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def execution_child(args) -> int:
    from gate_lite import ctl
    from gate_lite.orchestrator import Orchestrator

    original = Orchestrator._state_commitment

    def observed_commitment(self):
        reload_registry = self.registry.reload

        def observed_reload():
            state = reload_registry()
            # This capture intentionally uses unkeyed issuance; never export a
            # keyed issuance cache that could contain a plaintext pass token.
            if state.get("idempotency"):
                raise ValueError("capture refuses a registry with idempotency cache entries")
            write_json(Path(args.commitment_snapshot), state)
            return state

        self.registry.reload = observed_reload
        try:
            return original(self)
        finally:
            self.registry.reload = reload_registry

    Orchestrator._state_commitment = observed_commitment
    return ctl.main([
        "--state", args.state, "--runner", args.runner,
        "exec", "--tenant", "outsider", "--slot", args.slot,
        "--payload-ref", "echo hello from gate-lite 0.5 rehearsal",
        "--token-stdin",
    ])


def capture(args) -> int:
    from continuity_receipt import verify_bundle
    from continuity_receipt.canon import canonical_bytes, sha256_prefixed
    from gate_lite.orchestrator import SandboxRunner, _plan_envelope, parse_payload

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.chmod(out, 0o700)
    runner = Path(args.runner).resolve(strict=True)
    profile = SandboxRunner(str(runner))
    profile._require_profile()
    transcript = []
    token = None
    env = dict(os.environ)
    for name in ("WM_GATELITE_RUNNER", "WM_GATELITE_SLICE", "WM_SANDBOX_CLASS",
                 "WM_MANDALA_SANDBOX_CLASS", "GATE_LITE_REAL_RUNNER_TESTS",
                 "GATE_LITE_QUOTA_TESTS"):
        env.pop(name, None)
    env["PYTHONPATH"] = str(ROOT)

    def cli(arguments, *, stdin=None, child=False, record=True):
        if child:
            command = [sys.executable, str(Path(__file__).resolve()), *arguments]
        else:
            command = [sys.executable, "-m", "gate_lite.ctl", "--state", str(state),
                       "--runner", str(runner), *arguments]
        proc = subprocess.run(command, input=stdin, capture_output=True,
                              text=True, env=env, cwd=ROOT, timeout=60)
        if record:
            stdout, stderr = proc.stdout, proc.stderr
            if token:
                stdout = stdout.replace(token, "<redacted>")
                stderr = stderr.replace(token, "<redacted>")
            transcript.append({"argv": command, "exit": proc.returncode,
                               "stdout": stdout, "stderr": stderr})
        if proc.returncode:
            raise RuntimeError(f"capture command failed (exit {proc.returncode}): "
                               f"{proc.stderr.replace(token, '<redacted>') if token else proc.stderr}")
        return json.loads(proc.stdout)

    try:
        with tempfile.TemporaryDirectory(prefix="mandala-05-capture-") as private:
            state = Path(private) / "state"
            snapshot = Path(private) / "commitment.json"
            cli(["tenant-add", "--tenant", "outsider", "--agent", "did:key:zOutsiderRehearsal05"])
            issued = cli(["pass", "--tenant", "outsider", "--agent", "did:key:zOutsiderRehearsal05",
                          "--minutes", "10", "--spend-minor", "1000"], record=False)
            token = issued.pop("token")
            transcript.append({"operation": "pass (unkeyed)", "exit": 0,
                               "result": {**issued, "token": "<redacted>"}})
            slot = issued["slot_id"]
            executed = cli(["--exec-child", "--state", str(state), "--runner", str(runner),
                            "--slot", slot, "--commitment-snapshot", str(snapshot)],
                           stdin=token + "\n", child=True)
            if executed["exit"] != 0:
                raise RuntimeError("fixed no-network payload did not exit zero")
            cli(["settle", "--tenant", "outsider", "--slot", slot,
                 "--rail", "invoice", "--rail-ref", "local-rehearsal-05", "--minor", "0"])
            terminated = cli(["terminate", "--tenant", "outsider", "--slot", slot])
            verdict = cli(["receipt", "--task-id", terminated["task_id"], "--verdict"])
            bundle = cli(["receipt", "--task-id", terminated["task_id"]])
            receipts = {r["type"]: r for r in bundle["receipts"]}
            commitment_state = json.loads(snapshot.read_text())
            commitment = receipts["state.commitment"]["body"]
            execution = receipts["task.execution"]["body"]
            payload = "echo hello from gate-lite 0.5 rehearsal"
            plan = parse_payload(payload)
            plan["workspace"] = str(state / "workspaces" / slot)
            invocation = ["--exec", _plan_envelope(plan)]
            checks = {
                "payload_exit_zero": executed["exit"] == 0,
                "bundle_trusted": verify_bundle(bundle).verdict == "TRUSTED",
                "cli_verdict_trusted": verdict["verdict"] == "TRUSTED",
                "class_bwrap": execution["sandbox_class"] == "bwrap",
                "wrapper_digest": execution["runner_profile"]["executable_digest"] == digest_file(runner),
                "invocation_digest": execution["runner_profile"]["invocation_digest"] == sha256_prefixed(canonical_bytes(invocation)),
                "commitment_count": commitment["count"] == sum(len(v) for v in commitment_state.values()),
                "commitment_head": commitment["head_digest"] == sha256_prefixed(canonical_bytes(commitment_state)),
                "settlement_minor_zero": receipts["settlement"]["body"]["amount"]["minor"] == 0,
                "delivery_binds_execution_result": receipts["delivery.attestation"]["body"]["response_hash"] == executed["stdout_hash"],
                "terminated": verdict["summary"]["terminated"],
            }
            artifacts = {
                "bundle-task.json": bundle,
                "verdict.json": verdict,
                "commitment-state.json": commitment_state,
                "invocation.json": invocation,
                "checks.json": checks,
                "transcript.json": transcript,
            }
            versions = {}
            for name in ("continuity-receipt", "cryptography", "cffi", "pycparser"):
                try:
                    versions[name] = importlib.metadata.version(name)
                except importlib.metadata.PackageNotFoundError:
                    versions[name] = "not-installed"

            artifacts["provenance.json"] = {
                "source_sha": args.source_sha, "source_status": args.source_status,
                "source_provenance": "operator assertion; not verified by this tool",
                "disposition": "bounded same-host rehearsal; not independent adoption",
                "python": sys.version.split()[0], "platform": platform.platform(),
                "dependencies": versions, "wrapper_sha256": digest_file(runner),
                "tool_sha256": {name: digest_file(Path(shutil.which(name))) for name in ("bwrap", "jq")},
                "verifier": "Python reference; CLI/API share implementation",
                "commitment_capture": "observed Registry.reload snapshot supplied to original _state_commitment",
                "external_delivery_attestation": "absent; issuer records its own result binding",
                "scope_excluded": ["independent adoption", "hostile-tenant isolation", "payment qualification", "issuer honesty"],
            }
            # Reject rather than silently sanitize evidence: edits would make
            # a signed or commitment-bound artifact impossible to recompute.
            for name, value in artifacts.items():
                text = json.dumps(value)
                if token in text or re.search(r"eyJ[\w-]*\.[\w-]+\.[\w-]+", text) or "PRIVATE KEY-----" in text:
                    raise RuntimeError(f"privacy check failed for {name}; evidence not exported")
            for name, value in artifacts.items():
                write_json(out / name, value)
            if not all(checks.values()):
                raise RuntimeError("capture checks failed; inspect checks.json")
            print(json.dumps({"out": str(out), "checks": checks, "source_status": args.source_status}, indent=2))
            return 0
    finally:
        token = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument("--runner", required=True)
    parser.add_argument("--source-sha")
    parser.add_argument("--source-status", choices=("local-reviewed", "pushed-frozen"), default="local-reviewed")
    parser.add_argument("--exec-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--state", help=argparse.SUPPRESS)
    parser.add_argument("--slot", help=argparse.SUPPRESS)
    parser.add_argument("--commitment-snapshot", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.exec_child:
        if not all((args.state, args.slot, args.commitment_snapshot)):
            parser.error("execution child requires state, slot and snapshot path")
        return execution_child(args)
    if not args.out or not args.source_sha or not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        parser.error("capture requires --out and a full 40-character --source-sha")
    return capture(args)


if __name__ == "__main__":
    sys.exit(main())
