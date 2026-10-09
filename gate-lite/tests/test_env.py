"""Controlled subprocess environments for tests that must not inherit runners."""
from __future__ import annotations

import os


# Keep this list broader than the current CLI inputs so a developer's class
# assertion/hint cannot silently turn a guard test into a real-runner test.
RUNNER_SELECTION_ENV = (
    "WM_GATELITE_RUNNER",
    "WM_GATELITE_SLICE",
    "WM_GATELITE_SANDBOX_CLASS",
    "WM_GATELITE_RUNNER_CLASS",
    "WM_GATELITE_CLASS",
    "WM_GATELITE_PROFILE",
    "WM_GATELITE_RUNNER_PROFILE",
    "WM_MANDALA_SANDBOX_CLASS",
    "WM_SANDBOX_CLASS",
    "GATE_LITE_SANDBOX_CLASS",
    "GATE_LITE_RUNNER_CLASS",
    "GATE_LITE_CLASS",
    "GATE_LITE_RUNNER_PROFILE",
)


def controlled_test_env(*, overrides: dict[str, str | None] | None = None) -> dict[str, str]:
    """Copy the current environment, clearing runner hints unless overridden.

    PATH and Python import-related values are preserved so subprocesses use the
    same interpreter and dependencies as the parent test process.
    """
    env = os.environ.copy()
    for name in RUNNER_SELECTION_ENV:
        env.pop(name, None)
    for name, value in (overrides or {}).items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env
