# gate-lite — Continuity Receipt 0.5 review candidate

Gate-lite is a cooperative-workload orchestrator: pass → execute → settle →
terminate. This selective public port is a local review candidate. Public main's
0.4 hold remains the published posture until independent port review and the
publication decision. See [the root source/evidence boundary](../README.md).

The package requires Python 3.11+ and exactly `continuity-receipt==0.5.0` from
PyPI. Distribution metadata, imported runtime version and supported spec are
checked before state/key creation. New bundles use `continuity-receipt/0.5`;
committed `vectors/` remain historical 0.4 compatibility fixtures.

## Layout

```
gate_lite/                  CLI, MCP, registry, tokens, orchestrator
runners/bwrap-v1/            public MIT wrapper packet and provenance
tools/capture_outsider_05.py token-safe bounded CLI capture
tools/test_sandbox_argv.py   wrapper argv tests using a capture shim
tools/qualify_bwrap_runner.py fixed namespace/filesystem probe
tools/make_vectors.py       explicit-version generation into separate output
tests/                      hermetic unit tests and opt-in real acceptance
vectors/                    preserved historical spec-0.4 corpus
evidence/                   dated captures, each bound to its own source pin
```

## Install and ordinary checks

From `gate-lite/`:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pip check
PY=.venv/bin/python
"$PY" -m unittest discover -s tests -v
"$PY" tools/test_sandbox_argv.py -v
.venv/bin/continuity-receipt-verify vectors/02_happy_full.json
```

The ordinary suite clears ambient runner/slice/class hints in absence/demo tests.
It does not qualify a real host. Real acceptance requires
`GATE_LITE_REAL_RUNNER_TESTS=1` and a runner matching the exact profile; an
explicitly requested invalid profile fails preflight. Quota cases additionally
require `GATE_LITE_QUOTA_TESTS=1` and a ready systemd user manager. The wall/OOM
drills remain unqualified in the accepted October 9 exercise.

## CLI lifecycle and tokens

For a simulated flow, start Python with `--demo` at exec. Real execution needs
an explicitly selected qualified runner. `pass` returns the slot and token;
keep the token out of argv, transcripts, and shell tracing. The copyable real
flow in [protocol v2](../GATE_LITE_OUTSIDER_EXERCISE.md) uses the capture tool:

```bash
RUNNER=$(realpath runners/bwrap-v1/mandala-sandbox)
SOURCE_SHA=<full-tested-source-sha>
"$PY" tools/capture_outsider_05.py --out /path/to/new-evidence-directory \
  --runner "$RUNNER" --source-sha "$SOURCE_SHA" --source-status local-reviewed
```

This bounded tool uses separate CLI processes for tenant-add, unkeyed pass,
fixed no-network exec, $0 invoice settlement, termination, and verification. It
keeps the issuance token in memory, sends it on stdin, redacts issuance output,
and exports neither the SQLite runtime database nor signing key. Its source
SHA/status are operator assertions: record fresh-export and remote provenance
separately before using `pushed-frozen`.

Direct exec accepts mutually exclusive `--token-stdin` and `--token`. MCP requires
`token` in `mandala.exec`. Tokens bind agent and slot, and successful execution
consumes the JTI durably across restarts. Tenant membership is checked at issuance;
idempotency cache lookup follows authorization and is tenant/slot scoped. Keyed
pass issuance caches its complete result, including the plaintext token, in the
private runtime registry. The capture uses unkeyed issuance; a lost unkeyed token
requires a fresh pass. Single use does not mean tokens never persist in runtime
state. Never export the database or a keyed issuance cache as public evidence.

## Runner, egress and lifecycle

The included wrapper is the public byte-identical MIT packet described in
[runners/bwrap-v1/README.md](runners/bwrap-v1/README.md). The exact profile binds:

| Component | SHA-256 |
|---|---|
| wrapper | `f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e` |
| bwrap | `e318903862396f96de3df57264e0158682b952fd3fb53ac23d876413e7b30f71` |
| jq | `59cfd58d7e470b103aede0e7589cfea929e45ee27f5471f08aa9676ac7bfc566` |

A match reports `urn:mandala:runner-profile:bwrap-v1`, `locally_qualified`, and
class `bwrap`. Unknown, changed, or mismatched identities fail before token
consumption or spawn. Hash checks identify the reviewed builds; they do not
independently prove their behavior. Another host/tool build needs new reviewed
profile evidence. The original public 0.4 runtime refuses this wrapper because
its class vocabulary cannot honestly describe Bubblewrap alone.

```bash
RUNNER=$(realpath runners/bwrap-v1/mandala-sandbox)
GATE_LITE_REAL_RUNNER_TESTS=1 WM_GATELITE_RUNNER="$RUNNER" \
  "$PY" -m unittest discover -s tests -p test_acceptance.py -v
```

- Commands default to no network. Envelopes can request `net: true` with an
  `egress` list. A grant shares the whole network; entries record intent with
  `enforced: false`. No destination allowlist or L2 proxy profile is added.
- The workspace is writable at `/workspace` for exec and captured by snapshot.
  Restore verifies the artifact digest and extracts safely. Snapshots preserve
  filesystem artifacts, not VM/process state.
- Operator kill uses systemd when successful, then POSIX process-group/PID
  fallback when systemd is absent or refuses. Expiry self-seals; the optional
  sweep timer covers idle slots.
- Each successful exec emits execution then a state commitment over one exact
  registry snapshot. Commitment failure holds the slot as `receipt_incomplete`
  for operator review, preventing payload rerun.
- Settlement recovers the latest signed execution stdout digest after restart.
  Pre-execution settlement uses the explicit `sha256("none")` sentinel. This is
  the issuer's result binding, not external delivery or payment proof.

## MCP

```bash
"$PY" -m gate_lite.mcp_server --state ./state --tenant dogfood --demo
"$PY" -m gate_lite.mcp_server --state ./state --tenant dogfood --demo \
  --transport http --host 127.0.0.1 --port 8765
```

Omit `--demo` and select `--runner <path>` for the qualified real profile.
The server refuses absent-runner startup unless demo is explicit. Typed dependency
or runner startup failures keep JSON-RPC alive and return structured `isError`
results to tool calls. CLI typed refusals exit 3 and report error, expected,
found and action fields. HTTP binds loopback; its optional bearer token and MCP
session are distinct from the single-use execution token.

Tools include pass, pass.verify, exec, settle, terminate, kill, destroy, status,
list, receipt, templates, snapshot, restore, and sweep. `mandala.receipt` supports
`verify: true`. The CLI verifier, console verifier and module verifier share the
same Python implementation.

## Fixtures and evidence

Do not regenerate `vectors/`. It is the preserved historical 0.4 corpus. To
create an explicitly labeled new corpus, use a fresh output directory:

```bash
"$PY" tools/make_vectors.py --spec 0.5 --out /path/to/new-vectors-05
.venv/bin/continuity-receipt-verify /path/to/new-vectors-05/02_happy_full.json
```

The accepted frozen private-source exercise is under
[evidence/frozen-source-2026-10-09](evidence/frozen-source-2026-10-09/REPORT.md).
Older 0.3/0.4 outsider bundles and benchmark/dogfood captures retain their source
and environment labels. Historical `bwrap-landlock` labels are signed issuer
claims; the portable wrapper establishes Bubblewrap only. Older dated acceptance
and benchmark results do not qualify this candidate's quotas or another host.

Shared-kernel containment, TRUSTED receipts and issuer result bindings leave
wall/OOM qualification, independent adoption, payment qualification, external
delivery attestation, hostile-tenant isolation and VM containment open.
