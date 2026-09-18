#!/usr/bin/env python3
"""mandala-ctl — gate-lite v0 CLI (pass / exec / terminate / verify)."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from continuity_receipt import verify_bundle  # noqa: E402
from gate_lite.orchestrator import EmitterError, Orchestrator, build_runner  # noqa: E402


def build_orchestrator(args) -> Orchestrator:
    runner_path = args.runner or os.environ.get("WM_GATELITE_RUNNER")
    slice_mode = args.slice or os.environ.get("WM_GATELITE_SLICE") == "1"
    return Orchestrator(
        args.state, gate_id=args.gate_id, runner=build_runner(runner_path, slice_mode)
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="mandala-ctl")
    parser.add_argument("--state", default="./gate-state")
    parser.add_argument("--gate-id", default="gate-lite-1")
    parser.add_argument("--runner", default=None, help="path to mandala-sandbox wrapper")
    parser.add_argument(
        "--slice",
        action="store_true",
        help="run payloads under a systemd user slice with cgroup quotas (G2)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    tenant = sub.add_parser("tenant-add")
    tenant.add_argument("--tenant", required=True)
    tenant.add_argument("--agent", action="append", required=True)

    pass_cmd = sub.add_parser("pass")
    pass_cmd.add_argument("--tenant", required=True)
    pass_cmd.add_argument("--agent", required=True)
    pass_cmd.add_argument("--minutes", type=int, default=90)
    pass_cmd.add_argument("--class", dest="slot_class", default="small")
    pass_cmd.add_argument("--spend-minor", type=int, default=0)
    pass_cmd.add_argument("--idempotency-key", default=None)

    exec_cmd = sub.add_parser("exec")
    exec_cmd.add_argument("--tenant", required=True)
    exec_cmd.add_argument("--slot", required=True)
    exec_cmd.add_argument("--payload-ref", required=True)
    exec_cmd.add_argument("--idempotency-key", default=None)

    settle = sub.add_parser("settle")
    settle.add_argument("--tenant", required=True)
    settle.add_argument("--slot", required=True)
    settle.add_argument("--rail", default="invoice")
    settle.add_argument("--rail-ref", required=True)
    settle.add_argument("--minor", type=int, required=True)

    term = sub.add_parser("terminate")
    term.add_argument("--tenant", required=True)
    term.add_argument("--slot", required=True)
    term.add_argument("--reason", default="completed")

    kill = sub.add_parser("kill")
    kill.add_argument("--tenant", required=True)
    kill.add_argument("--slot", required=True)
    kill.add_argument("--signal", default="SIGTERM")
    kill.add_argument("--wait", type=float, default=5.0, help="seconds before SIGKILL escalation")

    snap = sub.add_parser("snapshot")
    snap.add_argument("--tenant", required=True)
    snap.add_argument("--slot", required=True)

    restore = sub.add_parser("restore")
    restore.add_argument("--tenant", required=True)
    restore.add_argument("--slot", required=True)
    restore.add_argument("--snapshot", required=True, dest="snapshot_id")

    sweep = sub.add_parser("sweep")
    sweep.add_argument("--tenant", default=None)

    status = sub.add_parser("status")
    status.add_argument("--tenant", required=True)
    status.add_argument("--slot", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--tenant", required=True)

    receipt = sub.add_parser("receipt")
    receipt.add_argument("--task-id", required=True)
    receipt.add_argument("--verdict", action="store_true")

    args = parser.parse_args(argv)
    orch = build_orchestrator(args)

    try:
        if args.cmd == "tenant-add":
            output = orch.add_tenant(args.tenant, args.agent)
        elif args.cmd == "pass":
            spend_cap = {"minor": args.spend_minor, "currency": "USD"} if args.spend_minor else None
            output = orch.pass_(
                args.tenant,
                args.agent,
                minutes=args.minutes,
                slot_class=args.slot_class,
                spend_cap=spend_cap,
                idempotency_key=args.idempotency_key,
            )
        elif args.cmd == "exec":
            output = orch.exec_(
                args.tenant, args.slot, args.payload_ref, idempotency_key=args.idempotency_key
            )
        elif args.cmd == "settle":
            output = orch.settle(args.tenant, args.slot, args.rail, args.rail_ref, args.minor)
        elif args.cmd == "terminate":
            output = orch.terminate(args.tenant, args.slot, reason=args.reason)
        elif args.cmd == "kill":
            output = orch.kill(args.tenant, args.slot, signal_name=args.signal, wait_s=args.wait)
        elif args.cmd == "snapshot":
            output = orch.snapshot(args.tenant, args.slot)
        elif args.cmd == "restore":
            output = orch.restore(args.tenant, args.slot, args.snapshot_id)
        elif args.cmd == "sweep":
            output = orch.sweep_expired(args.tenant)
        elif args.cmd == "status":
            output = orch.status(args.tenant, args.slot)
        elif args.cmd == "list":
            output = orch.list_(args.tenant)
        elif args.cmd == "receipt":
            bundle = orch.receipt(args.task_id)
            output = verify_bundle(bundle).as_dict() if args.verdict else bundle
        else:  # pragma: no cover
            parser.error("unknown command")
    except EmitterError as exc:
        print(json.dumps({"error": str(exc), "code": "emitter_unavailable"}), file=sys.stderr)
        return 3
    except (KeyError, PermissionError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
