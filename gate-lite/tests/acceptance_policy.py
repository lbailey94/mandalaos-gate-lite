"""Explicit opt-in and exact-profile checks for real-runner acceptance tests."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from gate_lite.orchestrator import PROFILE_ID, RunnerProfileError, SandboxRunner


REAL_RUNNER_OPT_IN = "GATE_LITE_REAL_RUNNER_TESTS"
QUOTA_OPT_IN = "GATE_LITE_QUOTA_TESTS"


@dataclass(frozen=True)
class AcceptancePolicy:
    runner_path: str | None
    runner_enabled: bool
    runner_skip_reason: str | None
    quota_enabled: bool
    quota_skip_reason: str | None


def _requested(name: str) -> bool:
    value = os.environ.get(name, "")
    if value not in ("", "0", "1"):
        raise RuntimeError(f"{name} must be unset, 0, or 1 (got {value!r})")
    return value == "1"


def acceptance_policy() -> AcceptancePolicy:
    runner_requested = _requested(REAL_RUNNER_OPT_IN)
    quota_requested = _requested(QUOTA_OPT_IN)

    if not runner_requested:
        runner_path = None
        runner_enabled = False
        runner_reason = f"set {REAL_RUNNER_OPT_IN}=1 to run real bwrap acceptance tests"
    else:
        configured = os.environ.get("WM_GATELITE_RUNNER")
        runner_path = configured or shutil.which("mandala-sandbox")
        if not runner_path:
            raise RuntimeError(
                f"{REAL_RUNNER_OPT_IN}=1 requires WM_GATELITE_RUNNER or mandala-sandbox on PATH"
            )
        try:
            runner = SandboxRunner(runner_path)
        except (OSError, RunnerProfileError) as exc:
            raise RuntimeError(f"{REAL_RUNNER_OPT_IN}=1 requested an invalid runner profile: {exc}") from exc
        if (
            runner.profile_id != PROFILE_ID
            or runner.profile_status != "locally_qualified"
            or runner.sandbox_class != "bwrap"
        ):
            raise RuntimeError(
                f"{REAL_RUNNER_OPT_IN}=1 requested an invalid runner profile: exact reviewed "
                "wrapper, bwrap, and jq identities do not match the pinned profile"
            )
        # Re-check at setup time: this is the exact dependency/profile predicate
        # SandboxRunner enforces again immediately before every payload spawn.
        try:
            runner._require_profile()
        except (OSError, RunnerProfileError) as exc:
            raise RuntimeError(f"{REAL_RUNNER_OPT_IN}=1 requested an invalid runner profile: {exc}") from exc
        runner_enabled = True
        runner_reason = None

    systemd_ready = bool(shutil.which("systemd-run") and shutil.which("systemctl"))
    if systemd_ready:
        import subprocess

        try:
            probe = subprocess.run(
                ["systemctl", "--user", "is-system-running"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            systemd_ready = probe.stdout.strip() in ("running", "degraded")
        except (OSError, subprocess.TimeoutExpired):
            systemd_ready = False

    if not runner_requested:
        quota_reason = f"set {REAL_RUNNER_OPT_IN}=1 and {QUOTA_OPT_IN}=1 to run systemd quota tests"
    elif not quota_requested:
        quota_reason = f"set {QUOTA_OPT_IN}=1 to run systemd quota tests"
    elif not systemd_ready:
        quota_reason = "systemd quota tests require systemd-run, systemctl, and a running user manager"
    else:
        quota_reason = None

    return AcceptancePolicy(
        runner_path=runner_path,
        runner_enabled=runner_enabled,
        runner_skip_reason=runner_reason,
        quota_enabled=runner_enabled and quota_requested and systemd_ready,
        quota_skip_reason=quota_reason,
    )
