#!/usr/bin/env python3
"""Self-contained barrier repro for gate-lite issue #1 invariants.

Runs the lifecycle race tests (temp dirs only — no live systems, no network)
and prints an invariant -> test mapping with PASS/FAIL. Exit 0 only when every
invariant holds.

Usage:
    python3 gate-lite/tools/barrier_repro.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # gate-lite/

INVARIANTS = [
    (
        "no process starts after a terminal seal",
        "test_start_rejected_after_seal_emits_no_execution",
    ),
    (
        "pre-start kill race returns an explicit outcome (no task.execution)",
        "test_kill_during_start_defers_and_keeps_receipts_monotonic",
    ),
    (
        "expiry during a start defers to a post-run seal",
        "test_expiry_during_start_defers_to_post_run_seal",
    ),
    (
        "receipt ordering is monotonic (decision -> execution -> termination)",
        "test_kill_live_run_terminates_after_execution",
    ),
    (
        "kill requests are bound to the run generation",
        "test_stale_kill_request_cannot_bind_a_late_start",
    ),
]


def main() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_lifecycle_race.py", "-q", "-rA"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    outcomes: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        for status in ("PASSED", "FAILED", "ERROR"):
            if line.startswith(status + " "):
                outcomes[line.split("::")[-1]] = status

    print("invariant coverage:")
    all_green = True
    for description, test in INVARIANTS:
        status = outcomes.get(test, "MISSING")
        all_green = all_green and status == "PASSED"
        print(f"  [{status:7}] {description}  ({test})")
    print(f"pytest exit: {proc.returncode}")
    return 0 if all_green and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
