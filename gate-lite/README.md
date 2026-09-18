# gate-lite — P0 slice (Continuity Receipts + governed passes)

First buildable slice of the Mandala Gate program: a cooperative-tenant
orchestrator that issues governed passes and emits **Continuity Receipts**
(`continuity-receipt/0.1`). Separate module/versioning from the Gen-2/WMv9
release train (decision 2026-09-17).

**Honesty frame:** gate-lite isolation is the Sovereign form — shared-kernel
containment (bwrap/Landlock). It is never sold as untrusted multi-tenant; that
is gate-hard (microVM floor, v0.2).

## Layout

```
continuity_receipt/   receipt library + reference verifier (spec §7)
gate_lite/            orchestrator: pass → exec → settle → terminate
  ctl.py              mandala-ctl CLI
  mcp_server.py       MCP control surface (stdio + loopback HTTP/SSE)
tools/make_vectors.py generates the spec test vectors (0.1 + 0.2)
tools/dogfood_run.py  full CLI dogfood on the real runner, evidence capture
tools/install_sweep_timer.sh  systemd user timer for the expiry sweep
tests/                unittest suites (56 tests)
vectors/              generated bundles + INDEX.md
evidence/             dogfood runs (run.json, SUMMARY.md, bundles, transcript)
```

## Quick start

```bash
python3 tools/make_vectors.py
python3 -m unittest discover -s tests -v

CTL=gate_lite/ctl.py
python3 $CTL --state ./state tenant-add --tenant dogfood --agent did:key:zSmokeAgent1
python3 $CTL --state ./state pass --tenant dogfood --agent did:key:zSmokeAgent1 \
    --minutes 30 --spend-minor 1000
python3 $CTL --state ./state exec --tenant dogfood --slot <slot_id> \
    --payload-ref "echo hello"
python3 $CTL --state ./state settle --tenant dogfood --slot <slot_id> \
    --rail-ref inv-1 --minor 200
python3 $CTL --state ./state terminate --tenant dogfood --slot <slot_id>
python3 $CTL --state ./state receipt --task-id <task_id> --verdict
```

Standalone verification:

```bash
python3 -m continuity_receipt.verify vectors/02_happy_full.json
```

## MCP control surface

```bash
# stdio (one process per client)
python3 -m gate_lite.mcp_server --state ./state --tenant dogfood
# loopback HTTP (Streamable HTTP subset: POST /mcp, SSE when Accept asks)
python3 -m gate_lite.mcp_server --state ./state --tenant dogfood \
    --transport http --host 127.0.0.1 --port 8765 [--token <bearer>]
```

JSON-RPC 2.0 (`initialize`, `ping`, `tools/list`, `tools/call`) with no
third-party MCP SDK dependency. Tools: `mandala.pass`, `mandala.exec`,
`mandala.settle`, `mandala.terminate`, `mandala.kill`, `mandala.destroy`,
`mandala.status`, `mandala.list`, `mandala.receipt`, `mandala.templates`,
`mandala.snapshot`, `mandala.restore`, `mandala.sweep`. `mandala.receipt`
supports `verify: true`; tool failures
return structured `isError` results (`emitter_unavailable`, `not_found`,
`permission_denied`, `invalid`). The HTTP transport binds loopback only and
issues `Mcp-Session-Id` on initialize; optional bearer token via `--token`.

## Runner and containment

```bash
WM_GATELITE_RUNNER=~/.local/bin/mandala-sandbox python3 $CTL ...   # bwrap
WM_GATELITE_SLICE=1 WM_GATELITE_RUNNER=~/.local/bin/mandala-sandbox ...  # + systemd slice quotas
```

- Egress is default-deny: payloads are commands, or envelopes
  `{"program": "curl", "args": [...], "net": true, "egress": ["host"]}`.
  Undeclared attempts run without network and are recorded as denied in
  `task.execution.egress`; `net: true` needs declared destinations.
- The slot workspace is mounted writable at `/workspace` inside the sandbox
  (wrapper envelope `rw: true`), so payload artifacts land in
  `state/workspaces/<slot>/` and are captured by `mandala.snapshot`.
- Snapshot → destroy → recreate → restore is tested end-to-end (G7);
  `mandala.restore` verifies the artifact sha, extracts safely, and emits a
  `delivery.attestation`. `mandala.sweep` seals past-expiry slots with
  `time_expired` termination receipts (exec also self-seals on expiry).
- Selective disclosure: `python3 -m continuity_receipt.disclose
  redact|verify|reveal` — redaction re-signs the chain tail (issuance-time
  act), withheld salts verify PROVISIONAL, disclosed maps verify TRUSTED.
- Slice mode runs each exec as a transient systemd user service with
  `MemoryMax`, `MemorySwapMax=0`, `CPUQuota`, `RuntimeMaxSec`; `oom-kill` /
  `timeout` results become `task.termination` `kill_signal=quota`.
- Operator kill: `mandala-ctl kill` / `mandala.kill` stops a live run within
  `wait_s` (SIGTERM → SIGKILL) and records `kill_signal=operator` with latency.
- Expiry sweep cadence: `tools/install_sweep_timer.sh --state ~/gate-state`
  installs a systemd user timer (default 15 min, `Persistent=true`) that runs
  one `sweep` pass; `--dry-run` prints the units, `--uninstall` removes them.
  Exec/kill/snapshot/restore still self-seal on expiry — the timer covers idle
  slots.
- Emitter is fail-closed: if a receipt cannot be written, exec is refused
  (`emitter_unavailable`), no work runs.

## Benchmarks

```bash
python3 tools/bench.py --out evidence/bench-<date> --profile standard   # quick|standard|deep
```

Six groups (receipt primitives, registry/multi-process, orchestrator flows,
real runner, MCP transports, soak) with warmup, auto-calibrated n, percentiles
and raw samples in `results.json`. The OOM quota-seal drill is opt-in
(`--oom`): memcg OOM kills make `gsd-housekeeping` pop "Application Stopped"
desktop notifications. The G2 acceptance tests still exercise the same kernel
path (one or two OOMs per `unittest` run). Latest:
`evidence/bench-2026-09-18-sqlite/` (14/14 invariants, 44s; baseline
`evidence/bench-2026-09-18/` kept for comparison). Headline medians on the
dogfood host (i5-8350U):

| Path | Median | Notes |
|---|---|---|
| Verify 6-receipt bundle | 1.26 ms (~790/s) | scales linearly; 100 receipts 22 ms |
| Full stub flow (4 ops, 6 receipts) | 5.4 ms | idempotent replay 0.07 ms |
| Gate exec via bwrap | 34.6 ms | raw wrapper 27.8 ms |
| Gate exec via systemd slice | 96.7 ms | per-exec unit startup |
| Operator kill | 51 ms (p95 1.1 s) | staged SIGTERM→SIGKILL; worst case = grace |
| OOM quota seal | 162 ms | memory hog under `MemoryMax` |
| MCP stdio ping / HTTP keep-alive ping | 0.04 ms / 0.42 ms | 8-client HTTP ≈ 1.7k calls/s |
| Snapshot / restore 50 MB workspace | 2.0 s / 0.51 s | gzip-bound, incompressible data |
| **Registry `get_slot` / `put_slot` at 10k slots** | **0.026 ms / 0.13 ms** | indexed SQLite (was 43 ms / 315 ms) |

**Top finding (fixed):** the JSON registry was O(total slots) per operation.
It is now indexed SQLite (`gate_lite/registry.py`, WAL + busy timeout, same
API, legacy `state.json` auto-import): reads and writes are flat from 100 to
10k slots, sweep 6.6 s → 0.45 s per 500 slots, soak drift 665% → −5%, full
standard benchmark 82 s → 44 s. WAL serializes writers (no lost updates at 16
parallel CLI writers). WM-store + karma-ledger integration remains a later
choice, not a scaling need. Earlier fixes from the same suite:
`TCP_NODELAY` on the MCP HTTP handler (41 ms → 0.42 ms keep-alive ping) and a
1 s SIGTERM grace before SIGKILL escalation (kill p95 5.1 s → 1.1 s).

## Status (2026-09-18)

- Receipt library + verifier: **done** — 20 vectors green (0.1 + 0.2); the
  spec is published at `github.com/lbailey94/continuity-receipt` (Apache-2.0),
  anchoring policy in `ANCHORING.md`.
- Orchestrator v0: pass/exec/settle/terminate/kill/snapshot, idempotency,
  tenant scoping, disk-backed chains across CLI processes, SQLite registry —
  **done**.
- MCP control surface: **done** — stdio + loopback HTTP/SSE, 13 tools
  (**56 tests total green**).
- Acceptance: **G1–G8 pass** (G7 now includes snapshot → destroy → recreate →
  restore roundtrip with runner-written artifacts). Snapshot is
  filesystem-only by decision.
- Dogfood: full CLI run on the real runner (evidence in `evidence/2026-09-18/`,
  33/33 checks) — pass → exec → **$0 settlement** → terminate → TRUSTED,
  egress deny, operator kill, OOM quota kill, expiry seal, restore roundtrip,
  selective disclosure, emitter drill; re-run green on the SQLite registry.
- Benchmarked: `tools/bench.py` + `evidence/bench-2026-09-18-sqlite/` (14/14
  invariants; registry scaling fixed).
- Expiry sweep cadence: **systemd user timer installer** (`tools/install_sweep_timer.sh`).
- Not yet: gate-hard (microVM floor), external-anchor issuance (policy decided;
  OTS proof verification is a 0.3 item), WM-store + karma-ledger registry
  integration. See `HANDOFF_2026-09-18.md` and
  `MANDALA_OS/design/GATE_LITE_ORCHESTRATOR_CONTRACT_2026-09-17.md` §14.

Requires Python 3.11+ and `cryptography` (Ed25519); runner needs `bubblewrap`
(+ `jq`), slice mode needs a systemd user session.
