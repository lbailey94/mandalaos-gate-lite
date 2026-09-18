#!/usr/bin/env python3
"""Gate-lite dogfood run: full CLI flow on the real runner, evidence captured.

Drives `mandala-ctl` as separate processes (the real operator surface) with
WM_GATELITE_RUNNER + WM_GATELITE_SLICE=1: pass → exec → $0 settle → terminate →
verify, plus snapshot, egress deny, operator kill, quota kill, and the
fail-closed emitter drill. Writes run.json, transcript.txt, receipts/, and
SUMMARY.md under the evidence directory.

Run: python3 tools/dogfood_run.py --out evidence/2026-09-18
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import keys, verify_bundle  # noqa: E402

WRAPPER = (
    os.environ.get("WM_GATELITE_RUNNER")
    or shutil.which("mandala-sandbox")
    or str(Path.home() / ".local" / "bin" / "mandala-sandbox")
)
AGENT_DID, _ = keys.generate(keys.deterministic_seed("dogfood-agent"))


def host_facts() -> dict:
    def out(cmd, **kwargs):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10, **kwargs).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None

    return {
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "bwrap": out(["bwrap", "--version"]),
        "systemd": out(["systemctl", "--version"]),
        "runner": WRAPPER,
        "slice_mode": True,
        "git_head": out(["git", "rev-parse", "HEAD"], cwd=str(Path(ROOT).parents[0])),
    }


class Dogfood:
    def __init__(self, out_dir: Path):
        self.out = out_dir
        self.state = out_dir / "state"
        self.receipts_out = out_dir / "receipts"
        self.receipts_out.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict] = []
        self.checks: list[tuple[str, str, bool, str]] = []
        self.env = dict(os.environ)
        self.env["WM_GATELITE_RUNNER"] = WRAPPER
        self.env["WM_GATELITE_SLICE"] = "1"

    def cli(self, *args: str, timeout: float = 120) -> dict:
        cmd = [sys.executable, "-m", "gate_lite.ctl", "--state", str(self.state), *args]
        started = time.time()
        proc = subprocess.run(cmd, cwd=str(ROOT), env=self.env, capture_output=True, text=True, timeout=timeout)
        step = {
            "cmd": "mandala-ctl " + " ".join(args),
            "rc": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ms": int((time.time() - started) * 1000),
        }
        self.steps.append(step)
        return step

    def cli_json(self, *args: str, timeout: float = 120) -> dict:
        step = self.cli(*args, timeout=timeout)
        if step["rc"] != 0:
            raise RuntimeError(f"{step['cmd']} failed rc={step['rc']}: {step['stderr']}")
        return json.loads(step["stdout"])

    def module(self, module: str, *args: str, timeout: float = 120) -> dict:
        cmd = [sys.executable, "-m", module, *args]
        started = time.time()
        proc = subprocess.run(cmd, cwd=str(ROOT), env=self.env, capture_output=True, text=True, timeout=timeout)
        step = {
            "cmd": " ".join(cmd[1:]),
            "rc": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "ms": int((time.time() - started) * 1000),
        }
        self.steps.append(step)
        return step

    def check(self, drill: str, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((drill, name, ok, detail))

    def save_bundle(self, label: str, task_id: str) -> dict:
        bundle = json.loads((self.state / "receipts" / f"{task_id}.json").read_text(encoding="utf-8"))
        (self.receipts_out / f"{label}-{task_id}.json").write_text(
            json.dumps(bundle, indent=2) + "\n", encoding="utf-8"
        )
        return bundle

    def verdict(self, label: str, task_id: str) -> dict:
        bundle = self.save_bundle(label, task_id)
        return verify_bundle(bundle).as_dict()


def flow_standard(run: Dogfood) -> str:
    run.cli_json("tenant-add", "--tenant", "dogfood", "--agent", AGENT_DID)
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "30", "--spend-minor", "1000")
    executed = run.cli_json("exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", "echo hello")
    run.check("G1", "exec exit 0", executed["exit"] == 0, f"stdout_hash={executed['stdout_hash']}")
    run.check("G1", "exec inside slice quota", executed.get("kill_signal") is None, "no quota/operator kill")
    settled = run.cli_json(
        "settle", "--tenant", "dogfood", "--slot", issued["slot_id"],
        "--rail", "invoice", "--rail-ref", "dogfood-0001", "--minor", "0",
    )
    run.check("G1", "$0 settlement recorded", settled["body"]["amount"]["minor"] == 0, settled["body"]["rail_ref"])
    terminated = run.cli_json("terminate", "--tenant", "dogfood", "--slot", issued["slot_id"])
    receipt = run.cli_json("receipt", "--task-id", terminated["task_id"], "--verdict")
    run.check("G1", "bundle TRUSTED (6 receipts)",
              receipt["verdict"] == "TRUSTED" and receipt["summary"]["receipts"] == 6,
              receipt["verdict"])
    task_id = terminated["task_id"]
    run.save_bundle("g1", task_id)
    return task_id


def flow_snapshot(run: Dogfood) -> str:
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "10")
    executed = run.cli_json(
        "exec", "--tenant", "dogfood", "--slot", issued["slot_id"],
        "--payload-ref", json.dumps({"program": "python3", "args": ["-c", "print(6*7)"]}),
    )
    snap = run.cli_json("snapshot", "--tenant", "dogfood", "--slot", issued["slot_id"])
    run.check("G7/snapshot", "frozen + artifact", snap["state"] == "frozen" and Path(snap["artifact"]["path"]).exists(),
              f"{snap['snapshot_id']} {snap['artifact']['bytes']}B")
    refused = run.cli("exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", "echo frozen")
    run.check("G7/snapshot", "exec refused while frozen", refused["rc"] == 2 and "frozen" in refused["stderr"],
              refused["stderr"].strip())
    terminated = run.cli_json("terminate", "--tenant", "dogfood", "--slot", issued["slot_id"])
    verdict = run.verdict("snapshot", terminated["task_id"])
    run.check("G7/snapshot", "bundle TRUSTED", verdict["verdict"] == "TRUSTED", json.dumps(verdict["errors"]))
    return terminated["task_id"]


def flow_restore(run: Dogfood) -> str:
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "5")
    payload_ref = json.dumps(
        {
            "program": "python3",
            "args": ["-c", "open('/workspace/artifact.txt','w').write('written inside the sandbox')"],
        }
    )
    executed = run.cli_json("exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", payload_ref)
    run.check("G7/restore", "runner wrote workspace artifact", executed["exit"] == 0, executed["stdout_hash"])
    snap = run.cli_json("snapshot", "--tenant", "dogfood", "--slot", issued["slot_id"])
    run.cli_json("terminate", "--tenant", "dogfood", "--slot", issued["slot_id"], "--reason", "destroyed")

    recreated = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "5")
    restored = run.cli_json(
        "restore", "--tenant", "dogfood", "--slot", recreated["slot_id"], "--snapshot", snap["snapshot_id"]
    )
    run.check(
        "G7/restore", "workspace restored byte-identical",
        restored["restored_hash"] == snap["tree_hash"], restored["restored_hash"],
    )
    artifact = run.state / "workspaces" / recreated["slot_id"] / "artifact.txt"
    run.check(
        "G7/restore", "artifact content present",
        artifact.exists() and artifact.read_text(encoding="utf-8") == "written inside the sandbox", str(artifact),
    )
    restored_exec = run.cli_json(
        "exec", "--tenant", "dogfood", "--slot", recreated["slot_id"], "--payload-ref", "echo restored"
    )
    run.check("G7/restore", "exec in restored slot", restored_exec["exit"] == 0, restored_exec["stdout_hash"])
    terminated = run.cli_json("terminate", "--tenant", "dogfood", "--slot", recreated["slot_id"])
    verdict = run.verdict("g7-restore", terminated["task_id"])
    run.check("G7/restore", "bundle TRUSTED", verdict["verdict"] == "TRUSTED", json.dumps(verdict["errors"]))
    return terminated["task_id"]


def flow_expiry(run: Dogfood) -> str:
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "0")
    time.sleep(1.1)
    late = run.cli("exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", "echo late")
    run.check("G7/expiry", "exec refused after expiry", late["rc"] == 2 and "expired" in late["stderr"],
              late["stderr"].strip())
    status = run.cli_json("status", "--tenant", "dogfood", "--slot", issued["slot_id"])
    run.check("G7/expiry", "slot sealed as expired", status["slot"]["state"] == "expired", status["slot"]["state"])
    task_id = run_task_id_for_slot(run, issued["slot_id"])
    verdict = run.verdict("g7-expiry", task_id)
    bundle = json.loads((run.state / "receipts" / f"{task_id}.json").read_text())
    termination = bundle["receipts"][-1]
    run.check("G7/expiry", "termination time_expired", termination["body"]["reason"] == "time_expired",
              json.dumps(termination["body"]))
    run.check("G7/expiry", "bundle TRUSTED", verdict["verdict"] == "TRUSTED", json.dumps(verdict["errors"]))
    return task_id


def flow_egress_deny(run: Dogfood) -> str:
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "5")
    payload_ref = json.dumps(
        {"program": "curl", "args": ["-sS", "-m", "5", "https://example.com"], "net": True, "egress": []}
    )
    executed = run.cli_json("exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", payload_ref)
    run.check("G3", "undeclared egress denied (non-zero exit)", executed["exit"] != 0, f"exit={executed['exit']}")
    terminated = run.cli_json("terminate", "--tenant", "dogfood", "--slot", issued["slot_id"])
    verdict = run.verdict("g3", terminated["task_id"])
    bundle = json.loads((run.state / "receipts" / f"{terminated['task_id']}.json").read_text())
    execution = next(r for r in bundle["receipts"] if r["type"] == "task.execution")
    entry = execution["body"]["egress"][0]
    run.check("G3", "denial recorded in task.execution.egress",
              entry["allowed"] is False and entry["bytes"] == 0, json.dumps(entry))
    run.check("G3", "bundle TRUSTED", verdict["verdict"] == "TRUSTED", json.dumps(verdict["errors"]))
    return terminated["task_id"]


def flow_kill(run: Dogfood) -> str:
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "5")
    cmd = [
        sys.executable, "-m", "gate_lite.ctl", "--state", str(run.state),
        "exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", "sleep 30",
    ]
    worker = subprocess.Popen(cmd, cwd=str(ROOT), env=run.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    run_file = run.state / "runs" / f"{issued['slot_id']}.json"
    deadline = time.time() + 15
    while time.time() < deadline and not run_file.exists():
        time.sleep(0.05)
    run.check("G6", "run journaled", run_file.exists(), str(run_file))

    started = time.time()
    killed = run.cli_json("kill", "--tenant", "dogfood", "--slot", issued["slot_id"], "--wait", "5")
    elapsed_ms = int((time.time() - started) * 1000)
    worker_out, _worker_err = worker.communicate(timeout=30)
    exec_report = json.loads(worker_out) if worker_out.strip() else {}
    run.check("G6", "kill within 5s", elapsed_ms < 5000, f"{elapsed_ms}ms")
    run.check("G6", "kill_signal=operator", killed["kill_signal"] == "operator" and killed["exec_active"],
              json.dumps(killed))
    run.check("G6", "run stopped and journal cleared",
              not run_file.exists() and exec_report.get("kill_signal") == "operator",
              f"exit={exec_report.get('exit')} signal={exec_report.get('kill_signal')}")
    task_id = run_task_id_for_slot(run, issued["slot_id"])
    verdict = run.verdict("g6", task_id)
    bundle = json.loads((run.state / "receipts" / f"{task_id}.json").read_text())
    termination = bundle["receipts"][-1]
    run.check("G6", "termination receipt operator",
              termination["body"].get("kill_signal") == "operator",
              json.dumps({k: termination["body"][k] for k in ("kill_signal", "operator_kill_latency_ms") if k in termination["body"]}))
    run.check("G6", "bundle TRUSTED", verdict["verdict"] == "TRUSTED", json.dumps(verdict["errors"]))
    return task_id


def flow_quota_kill(run: Dogfood) -> str:
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "1")
    payload_ref = json.dumps(
        {"program": "python3", "args": ["-c", "x=bytearray(2*1024**3); print(len(x))"]}
    )
    step = run.cli(
        "exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", payload_ref, timeout=180
    )
    executed = json.loads(step["stdout"]) if step["rc"] == 0 else {}
    run.check("G2", "memory overrun killed slot", executed.get("kill_signal") == "quota",
              f"exit={executed.get('exit')} reason={executed.get('reason')}")
    task_id = run_task_id_for_slot(run, issued["slot_id"])
    verdict = run.verdict("g2", task_id)
    bundle = json.loads((run.state / "receipts" / f"{task_id}.json").read_text())
    termination = bundle["receipts"][-1]
    run.check("G2", "termination quota/memory_max",
              termination["body"].get("kill_signal") == "quota" and termination["body"].get("killed_by") == "memory_max",
              json.dumps(termination["body"]))
    run.check("G2", "bundle TRUSTED", verdict["verdict"] == "TRUSTED", json.dumps(verdict["errors"]))
    return task_id


def run_task_id_for_slot(run: Dogfood, slot_id: str) -> str:
    status = run.cli_json("status", "--tenant", "dogfood", "--slot", slot_id)
    return status["slot"]["task_id"]


def flow_disclosure(run: Dogfood, task_id: str) -> None:
    bundle_path = run.state / "receipts" / f"{task_id}.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    index = next(i for i, r in enumerate(bundle["receipts"]) if r["type"] == "delivery.attestation")
    path = f"receipts[{index}].body.spec_ref"
    redacted_file = run.out / "g1-redacted.json"
    map_file = run.out / "g1-disclosure.json"

    redacted = run.module(
        "continuity_receipt.disclose", "redact",
        "--bundle", str(bundle_path), "--path", path,
        "--out", str(redacted_file), "--map", str(map_file),
        "--gate-key", str(run.state / "gate.key"),
    )
    run.check("P1/disclosure", "redact re-signs the tail", redacted["rc"] == 0, redacted["stderr"].strip())

    withheld = run.module("continuity_receipt.disclose", "verify", "--bundle", str(redacted_file))
    withheld_verdict = json.loads(withheld["stdout"])["verdict"] if withheld["stdout"].strip() else ""
    run.check("P1/disclosure", "salt withheld -> PROVISIONAL",
              withheld["rc"] == 1 and withheld_verdict == "PROVISIONAL", withheld_verdict)

    disclosed = run.module(
        "continuity_receipt.disclose", "verify",
        "--bundle", str(redacted_file), "--map", str(map_file),
    )
    disclosed_verdict = json.loads(disclosed["stdout"])["verdict"] if disclosed["stdout"].strip() else ""
    run.check("P1/disclosure", "disclosed -> TRUSTED",
              disclosed["rc"] == 0 and disclosed_verdict == "TRUSTED", disclosed_verdict)


def flow_fail_closed(run: Dogfood) -> None:
    issued = run.cli_json("pass", "--tenant", "dogfood", "--agent", AGENT_DID, "--minutes", "5")
    receipts_dir = run.state / "receipts"
    os.chmod(receipts_dir, 0o500)
    try:
        step = run.cli("exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", "echo unrecorded")
    finally:
        os.chmod(receipts_dir, 0o700)
    error = json.loads(step["stderr"]) if step["stderr"].strip() else {}
    run.check("G8", "exec refused (rc=3, emitter_unavailable)",
              step["rc"] == 3 and error.get("code") == "emitter_unavailable", step["stderr"].strip())

    recovered = run.cli_json("exec", "--tenant", "dogfood", "--slot", issued["slot_id"], "--payload-ref", "echo recovered")
    run.check("G8", "emitter restored, exec proceeds", recovered["exit"] == 0, recovered["stdout_hash"])
    run.cli_json("terminate", "--tenant", "dogfood", "--slot", issued["slot_id"])


def main() -> int:
    parser = argparse.ArgumentParser(prog="gate-lite-dogfood")
    parser.add_argument("--out", default=str(ROOT / "evidence" / "2026-09-18"))
    args = parser.parse_args()
    out = Path(args.out).resolve()
    state = out / "state"
    if state.exists():
        shutil.rmtree(state)
    out.mkdir(parents=True, exist_ok=True)

    run = Dogfood(out)
    started = time.time()
    flows = [flow_standard, flow_snapshot, flow_restore, flow_expiry, flow_egress_deny, flow_kill, flow_quota_kill]
    tasks = {}
    for flow in flows:
        tasks[flow.__name__] = flow(run)
    flow_disclosure(run, tasks["flow_standard"])
    flow_fail_closed(run)

    passed = sum(1 for _, _, ok, _ in run.checks if ok)
    total = len(run.checks)
    summary = {
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_s": round(time.time() - started, 2),
        "host": host_facts(),
        "checks": [{"drill": d, "check": n, "ok": ok, "detail": detail} for d, n, ok, detail in run.checks],
        "passed": passed,
        "total": total,
        "tasks": tasks,
        "steps": run.steps,
    }
    (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Gate-lite dogfood evidence — {summary['started_at']}",
        "",
        f"Host: {summary['host']['platform']} · bwrap {summary['host']['bwrap']}",
        f"Runner: `{WRAPPER}` (slice mode: WM_GATELITE_SLICE=1)",
        f"Checks: **{passed}/{total}** in {summary['duration_s']}s",
        "",
        "| Drill | Check | Result | Detail |",
        "|---|---|---|---|",
    ]
    for drill, name, ok, detail in run.checks:
        lines.append(f"| {drill} | {name} | {'PASS' if ok else 'FAIL'} | {detail} |")
    lines += [
        "",
        "Receipt bundles: `receipts/` · machine log: `run.json` · CLI transcript: `transcript.txt`",
        "",
        "Verify any bundle offline:",
        "`python3 -m continuity_receipt.verify receipts/<file>.json`",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (out / "transcript.txt").open("w", encoding="utf-8") as handle:
        for step in run.steps:
            handle.write(f"$ {step['cmd']}   (rc={step['rc']}, {step['ms']}ms)\n")
            if step["stdout"]:
                handle.write(step["stdout"] if step["stdout"].endswith("\n") else step["stdout"] + "\n")
            if step["stderr"]:
                handle.write("[stderr] " + step["stderr"])

    print(json.dumps({"passed": passed, "total": total, "out": str(out)}))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
