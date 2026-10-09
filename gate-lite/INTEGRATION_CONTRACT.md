# Integrating a project with the gate-lite 0.5 review candidate

This contract describes the selective review candidate, not a release of the
whole MandalaOS system. Public main remains at the 0.4 posture until independent
port review and publication. Containment is shared-kernel Bubblewrap for
cooperating workloads; this is not a hostile-tenant or VM boundary.

## Version and ownership boundaries

| Boundary | Owner | Record per run |
|---|---|---|
| Workload | integrating project | source revision, payload/envelope digest, output artifact |
| Pass and lifecycle | gate-lite | exact source SHA, tenant, agent, slot/task IDs |
| Sandbox | operator/configured runner | wrapper and dependency hashes, profile ID/status, class, slice setting |
| Receipt verification | continuity-receipt | distribution and imported runtime versions, emitted spec, verdict |

Install Python 3.11+ and exactly `continuity-receipt==0.5.0`. Gate-lite checks
installed metadata, imported runtime version and `continuity-receipt/0.5`
support before creating state. Typed preflight failures include expected/found
values and an action; CLI exits 3, MCP returns structured tool errors. A changed
source, dependency, runner or configuration requires new evidence.

## Execution profile

The reviewed `bwrap-v1` profile requires exact wrapper, Bubblewrap and jq hashes
listed in [README.md](README.md#runner-egress-and-lifecycle). A match reports
`locally_qualified` and class `bwrap`; any unknown or changed identity refuses
before consuming a pass token or spawning the payload. This profile derives
from the bounded same-host private 0.5 exercise. The selective public port needs
its own exact-commit verification and independent review. Other host/tool builds
need separately reviewed profiles; do not change hashes merely to force success.

Explicit `--demo` selects simulation, class `none`. It does not qualify a runner.
The 2026-09-24 0.3/0.4 exercises and signed historical `bwrap-landlock` labels
remain evidence for their original pins; Bubblewrap alone does not establish
Landlock. The later accepted private source `8e84b25` and public packet `1357c14`
are separate pins in the [frozen exercise](evidence/frozen-source-2026-10-09/REPORT.md).

## Minimum adapter lifecycle

1. Start from a fresh exact-source export and new environment. Select the
   reviewed real runner, or explicitly mark the entire flow as simulation.
2. Register the tenant and allowed agent. Issue bounded time/spend quotas;
   retain the slot and token privately. Pass issuance rejects an unregistered agent.
3. Execute using the matching tenant, slot and token. Prefer CLI `--token-stdin`;
   MCP `mandala.exec` requires `token`. Successful exec consumes the JTI durably.
   Authorization precedes idempotency cache access; reuse a key only for the
   identical request in its tenant/slot scope.
4. Inspect the execution and following `state.commitment`. Commitment failure
   leaves `receipt_incomplete` for operator review; do not rerun the payload.
5. Settle and terminate, including explicit zero-value invoice settlement when
   appropriate. After restart, issuer delivery response binds the latest durable
   execution stdout digest. Before execution, the explicit `sha256("none")`
   sentinel remains. Neither case establishes external delivery or payment.
6. Export and verify the bundle offline. Record the exact source, dependencies,
   wrapper profile and verifier version alongside it. Independently recompute
   claimed state and invocation bindings from the exact captured inputs.

Keyed issuance caches the complete result including the plaintext token in the
private registry; lost unkeyed issuance cannot recover it. Keep runtime DBs,
keys, tokens, and keyed caches out of public evidence. The bounded capture tool
uses unkeyed issuance and exports only its privacy-checked observation snapshot.
Its source pin/status are operator assertions; verify provenance separately.

## Egress, recovery and verification limits

Default-deny uses a separate network namespace. Granting `net: true` with
specified destinations shares the whole network; destinations record intent
with `enforced: false`. This candidate adds no destination filtering or L2 proxy
profile. Workspace snapshots restore filesystem artifacts, not VM/process state.
Operator kill retains POSIX fallback when systemd is absent or fails.

TRUSTED validates signed chain structure and policy consistency, not factual
issuer honesty or actual containment. CLI, console and module verification share
one Python implementation. Mechanism probes, independent hash recomputation and
receipt conformance are separate evidence views. Wall/OOM quota qualification,
independent adoption, payment qualification, external delivery attestation,
hostile-tenant isolation and VM containment remain open.

## Adapter acceptance

Require exact-source ordinary tests, explicit real-profile acceptance, a captured
project output and TRUSTED bundle, and negative authorization/replay/restart
cases. Record actual skips and configuration; missing quota coverage does not
qualify quotas. Test project-specific resource binds, destinations and store
access before claiming support. Start with one adapter and its evidence bundle;
promote additional runner capabilities only after their exact-profile review.
