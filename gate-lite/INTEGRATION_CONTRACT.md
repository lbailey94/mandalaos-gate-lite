# Integrating a project with gate-lite (candidate 0.4)

This contract is for a cooperating agent whose workload can run through a
configured `mandala-sandbox` runner. The runner provides shared-kernel
containment; it is not an untrusted-tenant boundary. This document describes
the private `mandala-os` 0.4 candidate, not the public 0.3 review snapshot.

## Version and ownership boundaries

| Boundary | Owner | Record per run |
|---|---|---|
| Project workload | integrating project | source revision, payload or envelope digest |
| Pass and lifecycle | gate-lite | gate-lite commit, tenant, agent DID, slot and task IDs |
| Sandbox | Sovereign runner | executable path and SHA-256, containment class, slice setting |
| Receipt format and verification | `continuity-receipt` | installed package version, emitted `spec`, verifier verdict |

Use an isolated environment with Python 3.11+ and install `gate-lite` from a
pinned source revision. The package declares `continuity-receipt>=0.4.0`; an
evidence run must additionally record and hold the exact resolved dependency
version. Do not silently reuse qualification evidence after a dependency or
runner change.

## Minimum lifecycle

1. Configure a real runner (`--runner`/`--slice` or `WM_GATELITE_RUNNER`).
   Startup and exec refuse without one. `--demo` explicitly opts into a
   simulated runner and its results must be labeled simulation.
2. Register a tenant and its allowed agent DID. `mandala.pass` rejects an
   unregistered agent. Supply time and spend bounds appropriate to the
   project; retain the returned `slot_id` and single-use `token` securely.
3. Execute with the matching tenant, slot, payload, and token. A successful
   execution consumes the token; retry with a new pass or a matching
   `idempotency_key` for an already completed request. Reusing a key for a
   changed request is rejected. Inspect `mandala.status` for runner class,
   simulation flag, and path before interpreting results.
4. Settle and terminate the slot, including a zero-value settlement when no
   charge applies. Preserve the resulting `task_id`.
5. Export the receipt bundle and verify it offline with the published
   `continuity-receipt-verify` command. Record the verdict and exact verifier
   version beside the bundle. A `TRUSTED` verdict validates the protocol and
   configured policy checks; it does not establish that the issuer's factual
   claims were honest or that the workload ran in a microVM.

The copyable CLI flow is in [`README.md`](README.md#quick-start). MCP exposes
the same lifecycle over stdio or loopback HTTP through `mandala.pass`,
`mandala.exec`, `mandala.settle`, `mandala.terminate`, and `mandala.receipt`.
`mandala.exec` requires `token` in its schema. The project should treat a
token as a secret and avoid including it in logs, bundles, or support tickets.

## Acceptance for a new project adapter

- A clean install from the stated gate-lite commit completes the real-runner
  flow and records `task.execution.sandbox_class` other than `stub`.
- Missing or wrong agent, slot, tenant, or token is refused before execution;
  restart and concurrent replay behavior are covered by gate-lite's suite.
- The project captures its own output artifact, receipt bundle, dependency
  versions, and offline verifier result without copying the pass token.
- Any project-specific resource binds, network destinations, or store access
  are declared and tested in the runner envelope before claiming support.

Start with one project adapter and its evidence bundle. Promote additional
runner capabilities only after the corresponding containment and recovery
checks pass on the exact candidate.
