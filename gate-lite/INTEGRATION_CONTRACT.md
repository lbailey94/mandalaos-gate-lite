# Integrating a project with gate-lite (public curated snapshot, receipt 0.4)

This contract describes the public, review-only gate-lite snapshot. It is not a
release and does not represent the full MandalaOS system. Gate-lite's current
containment class is shared-kernel; it is not an untrusted-tenant boundary.

## Version and ownership boundaries

| Boundary | Owner | Record per run |
|---|---|---|
| Project workload | integrating project | source revision, payload or envelope digest |
| Pass and lifecycle | gate-lite | gate-lite commit, tenant, agent DID, slot and task IDs |
| Sandbox | configured runner | executable path and SHA-256, observed containment class, slice setting |
| Receipt format and verification | `continuity-receipt` | installed distribution version, imported runtime version, emitted `spec`, verifier verdict |

Use Python 3.11+ and install this snapshot's `gate-lite` package in an isolated
environment. Its dependency is pinned to exactly `continuity-receipt==0.4.0`.
At startup, gate-lite checks that the installed distribution metadata and
imported runtime both report `0.4.0`, and that the imported runtime supports
the pinned receipt spec. A mismatch stops startup. Do not silently reuse
qualification evidence after changing the gate-lite source, receipt package,
runner, or runner configuration.

## Current execution status

The curated snapshot does not currently qualify a real runner. A configured
runner is reported as `unknown` / `unqualified`; real `mandala.exec` refuses it
before consuming the pass token or spawning the payload. `--demo` explicitly
selects simulated execution, and its outputs must be labeled simulation. Do
not present a demo run as sandboxed execution.

The 2026-09-24 real-runner 0.4 exercise is historical evidence for its recorded
private source pin and environment. It does not qualify the current curated
source revision. Earlier 0.3 evidence remains labeled as 0.3. Both exercises
were same-host clean-export reproductions by a collaborator with a pre-existing
runner, not unassisted stranger installs or independent-host qualification.

## Minimum lifecycle for a simulation

1. Start the CLI or MCP server with `--demo`. A real-runner flow is held until
   a runner is qualified for the exact source and its observed containment
   class matches the reviewed profile.
2. Register a tenant and its allowed agent DID. `mandala.pass` rejects an
   unregistered agent. Set time and spend bounds appropriate to the project;
   retain the returned `slot_id` and single-use `token` securely.
3. Execute with the matching tenant, slot, payload, and token. A successful
   simulated execution consumes the token. Reuse an idempotency key only for
   the same request. Inspect `mandala.status` and label results as simulated.
4. Settle and terminate the slot, including a zero-value settlement when no
   charge applies. Preserve the resulting `task_id`.
5. Export the receipt bundle and verify it offline with the published
   `continuity-receipt-verify` command. Record the verdict and exact verifier
   version beside the bundle. `TRUSTED` validates protocol and configured
   policy checks; it does not prove the workload ran in a real sandbox or that
   the issuer's factual claims are true.

The copyable CLI flow is in [`README.md`](README.md#quick-start). MCP exposes
the lifecycle over stdio or loopback HTTP through `mandala.pass`,
`mandala.exec`, `mandala.settle`, `mandala.terminate`, and `mandala.receipt`.
`mandala.exec` requires `token` in its schema. Treat tokens as secrets; do not
include them in logs, bundles, or support tickets.

## Egress and containment limits

The curated snapshot does not implement destination-level egress enforcement.
Declared destinations are recorded intent, not an allowlist. When network
access is granted by the current wrapper, it is whole-network; receipts mark
those destinations `enforced: false`. Do not claim L2, proxy-only, or
destination-filtered egress for this snapshot.

The documented bwrap/Landlock containment is shared-kernel isolation. Correct
the reported class to observed evidence: a Bubblewrap-only runner must not be
reported as `bwrap-landlock`. This snapshot does not provide a microVM boundary
or establish safety for mutually untrusted tenants.

## Acceptance for a real project adapter

- A future reviewed qualification identifies an exact gate-lite source
  revision, receipt package/runtime version, runner executable and sidecars,
  observed containment class, and configuration.
- The runner is qualified against that exact profile before a pass token is
  consumed or a payload is spawned; missing, changed, or mismatched identity
  fails closed.
- A clean install completes the real-runner lifecycle and captures the
  project's output artifact, receipt bundle, dependency versions, and offline
  verifier result without copying the pass token.
- Missing or wrong agent, slot, tenant, or token is refused before execution;
  restart and concurrent replay behavior are covered by the suite.
- Any project-specific resource binds, network destinations, or store access
  are declared and tested in the runner envelope before claiming support.

Start with one adapter and its evidence bundle. Promote additional runner
capabilities only after their containment and recovery checks pass on the exact
candidate.
