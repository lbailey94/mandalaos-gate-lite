# Gate-Lite Orchestrator Contract (DRAFT)

**Status:** design draft for Lucas — **v0 implemented 2026-09-17/18** in
`MANDALA_OS/gate-lite/` (35 tests green; acceptance G1–G6 + G8 pass, G7
partial; dogfood on the real runner 21/21 checks with a TRUSTED 6-receipt
bundle). This contract remains the authority for behavior; implementation
deviations are recorded in §14.
**Date:** 2026-09-17.
**Companions:** `MANDALA_GATES_FLEET_2026-09-17.md` (fleet/control-plane view),
`MULTI_TENANT_UNTRUSTED_V0_2_2026-09-17.md` (D1–D10),
`WHITEMAGIC/planning/specs/CONTINUITY_RECEIPT_v0_SPEC.md` (receipts).
**Scope:** the first buildable gate — one host, cooperative tenants, no
microVMs. Separate module and versioning from the Gen-2/WMv9 release train.

---

## 1. Purpose and honesty frame

A gate-lite lets cooperative tenants (our own agents first, then partners) run
time-boxed governed workloads through MCP, emitting Continuity Receipts.
Isolation is the Sovereign form — **shared-kernel containment
(bwrap/Landlock), the browser-sandbox trust class**. Gate-lite is never sold
as untrusted multi-tenant; that is gate-hard (v0.2, microVM floor).

## 2. Components

| Component | Role | Technology |
|---|---|---|
| `mandala-ctl` | lifecycle CLI + daemon | Rust (ACTUATOR contract first), systemd unit |
| Tenant registry | tenants, keys, quotas, AUP flags | per-host TOML + WM store (galaxy `mandala`) |
| Slot manager | allocates mandala slots, enforces slices | systemd slice per slot (`CPUQuota`, `MemoryMax`, `IOWeight`) |
| Store router | per-tenant WM store path + one-writer discipline | `store_busy` preflight (v9.1.9 seam) |
| Runner | executes tenant payload under containment | existing `landrun-sandbox` / `mandala-sandbox` (`--exec` contract) |
| Receipt emitter | writes Continuity Receipts per lifecycle/exec event | spec `continuity-receipt/0.1`; karma ledger hash chain |
| Control MCP | `mandala.*` tools on the gateway endpoint | existing MCP server + curated profile |
| Capacity accountant | leases, expiries, concurrency caps | local state + telemetry galaxy |

## 3. Domain objects

```
Tenant   { tenant_id, principal_did?, keys[], settlement_ref, aup_version, quotas }
Gate     { gate_id, class: gate-lite, region, capacity, policy_version }
Slot     { slot_id, tenant_id, state, slice, store_path, created_at, expires_at }
Pass     { pass_id, agent_id, principal_id, slot_id?, quotas, expires_at, token }
Lease    { lease_id, slot_id, holder, acquired_at, ttl, renewed_at }
```

## 4. Lifecycle state machine

```
requested ──place──► placed ──activate──► active ──snapshot?──► frozen
    │                  │                    │                      │
    └──deny──► denied  └──expire──► expired  └──terminate──► terminated ──► receipts sealed
```

Transitions are only callable by: the tenant (request/activate/terminate),
the orchestrator (place/expire/kill), or the gateway (on policy deny).
Every transition emits a receipt. Kill is always available to the operator
(`dharma|operator|quota|aup`) and lands in `task.termination.kill_signal`.

## 5. Control-plane MCP tools (v0)

All tools: idempotency key required (`Idempotency-Key` arg), JSON result,
errors as `{code, message, receipt_id?}`. Tool descriptions double as
discoverability copy.

| Tool | Args (required *) | Returns | Notes |
|---|---|---|---|
| `mandala.pass` | `minutes*`, `class*`, `tenant`, `budget_minor?`, `region?` | `{pass_id, endpoint, token, quotas, expires_at, receipt_id}` | the buyer entry point |
| `mandala.create` | `tenant*`, `template*`, `ttl_s*` | `{slot_id, state, receipt_id}` | slot allocation |
| `mandala.status` | `slot_id*` | `{state, quotas, usage, leases, last_receipt}` | read-only |
| `mandala.exec` | `slot_id*`, `payload_ref*`, `token*` | `{exit, stdout_hash, artifacts[], receipt_ids[]}` | runner-mediated; egress default-deny; token bound to agent + slot, single use (2026-09-24) |
| `mandala.kill` | `slot_id*`, `signal?`, `wait_s?` | `{state, kill_signal, receipt_id, exec_active}` | operator kill switch (SIGTERM→SIGKILL, latency recorded) |
| `mandala.snapshot` | `slot_id*` | `{snapshot_id, receipt_id, artifact, tree_hash}` | freeze for resume (gate-lite: filesystem workspace tar + `delivery.attestation`) |
| `mandala.restore` | `slot_id*`, `snapshot_id*` | `{snapshot_id, restored_hash, receipt_id}` | materialize into a `placed` slot (G7); safe extract + `delivery.attestation` |
| `mandala.sweep` | — | `{expired[], count}` | seal this tenant's past-expiry slots (`time_expired`) |
| `mandala.destroy` | `slot_id*`, `reason?` | `{state, receipt_id}` | triggers erasure per tenant policy |
| `mandala.list` | `tenant?`, `state?` | `{slots[]}` | tenant-scoped auth |
| `mandala.templates` | — | `{templates[]}` | from Nix closures/tenant configs |
| `mandala.receipt` | `receipt_id*` or `task_id*` | bundle | verifier-compatible export |

**Auth:** bearer pass token (agent) or tenant API key (operator). The gateway
is the only component that can widen a quota. Cross-tenant reads are denied by
construction (tenant-scoped queries + store router).

## 6. Pass token (v0)

Signed (Ed25519) compact JWS-like claims:

```json
{
  "iss": "gate:<gate_id>", "sub": "agent:<did>", "aud": "gate-lite",
  "mandala": { "class": "gate-lite", "slot_class": "small",
               "quotas": {"cpu_ms": 300000, "mem_mb": 1024, "wall_ms": 5400000}},
  "budget": {"minor": 0, "currency": "USD"},
  "policy_version": "2026-09-17.1", "exp": 1790000000,
  "jti": "urn:uuid:..."
}
```

Non-transferable; bound to `sub`; replayed `jti` rejected (cache in receipt
emitter). Settlement (if any) references the pass, not the token.

## 7. Storage and isolation (gate-lite, explicit)

- One WM store per tenant: `<gatestore>/tenants/<tenant_id>/`; index lock
  discipline via `store_busy` preflight (one writer; readers via read-only
  serve).
- Slot runs as tenant user under a systemd slice; filesystem access limited to
  the tenant store + scratch; `WM_SANDBOX_RUNNER` routes declared spawns
  through `landrun-sandbox`.
- Egress: default-deny; declared destinations logged; denials recorded in
  `task.execution.egress`.
- Disclosed limitation in every tenant contract: containment class, not
  hypervisor isolation; cooperative tenants only.

## 8. Receipts emission map

| Lifecycle event | Receipt type |
|---|---|
| pass issued / slot created | `session.pass.created` |
| policy evaluation before exec | `task.decision` |
| each exec + egress | `task.execution` |
| snapshot / artifact handoff | `delivery.attestation` (counterparty optional) |
| terminate/expire/kill | `task.termination` |
| settlement (invoiced key or x402 lane) | `settlement` |

Chain per task; `mandala.receipt` exports the bundle; the reference verifier
(separate module) validates it offline.

## 9. Policy hooks (Dharma economic profile, observe-first)

- Caps: per-pass wall/cpu/mem/spend; refusal classes (mining, spam, proxying)
  checked at `pass` and `create`, enforced by slice limits + egress deny.
- AUP version recorded on every tenant; change requires re-consent.
- No enforcement beyond containment in v0 without a zero-false-positive window
  (existing Yama doctrine); kill is manual/operator + quota-triggered only.

## 10. Failure modes and recovery

| Failure | Behavior |
|---|---|
| Orchestrator crash | leases expire; slots reach `expired`; receipts sealed on restart |
| Tenant writer collision | second writer refused (`store_busy`); message names the holder |
| Runaway workload | slice quota kills the slot; termination receipt `quota` |
| Gate restart | slots do not auto-resume; explicit `mandala.create` + optional snapshot restore |
| Receipt emitter failure | exec is refused (no unrecorded work) — fail-closed |

## 11. Acceptance tests (gate-lite)

- **G1** pass → exec → terminate produces a TRUSTED bundle (vector 1 path).
- **G2** quota overrun kills slot; termination reason `quota`.
- **G3** undeclared egress denied + recorded; no reachability.
- **G4** tenant A cannot read tenant B store or receipts (auth + path).
- **G5** idempotent replay of `mandala.pass`/`mandala.exec` creates no
  duplicate receipts.
- **G6** kill switch: operator termination within N seconds, receipt `operator`.
- **G7** snapshot → destroy → recreate → restore path documented and tested.
- **G8** receipt emitter down ⇒ exec refused (fail-closed), no silent work.

## 12. Non-goals (v0)

No microVMs (gate-hard later), no untrusted tenants, no custody, no
arbitration, no cross-gate placement, no GPU.

## 13. Open items

1. `mandala.exec` payload format (inline vs `payload_ref` to content-addressed
   store) — recommend ref-only for auditability.
2. Slot sizing classes (small/medium) and default quotas for dogfood.
3. Whether `mandala.*` ships in the curated MCP profile (11-tool public
   surface) or a separate gate profile — recommend separate, opt-in.
4. Tenant key bootstrap (operator-issued vs DID self-registration) — operator
   -issued in v0.

## 14. Implementation notes and deviations (v0, 2026-09-17)

**Location:** `MANDALA_OS/gate-lite/` — Python 3.11+, `cryptography` (Ed25519).
Layout: `gate_lite/` (orchestrator + `ctl.py` CLI + MCP server),
`tools/make_vectors.py`, `tests/`, `vectors/`, `evidence/`. The receipt
library + reference verifier is the published PyPI package
`continuity-receipt` — not vendored (migration `77821a7`, 2026-09-23).

**Realized:**
- Lifecycle `pass_ → exec_ → settle → terminate` with per-transition receipts;
  plus `kill` (operator) and `snapshot` (filesystem). StubRunner default;
  SandboxRunner via `WM_GATELITE_RUNNER`; SliceRunner (`WM_GATELITE_SLICE=1`)
  wraps it in a transient systemd user service (dogfooded 2026-09-18).
- Egress default-deny via declared-execution envelopes; denials recorded in
  `task.execution.egress`; enforcement is the wrapper's netns unshare.
- Operator kill: run journal (`<state>/runs/<slot>.json`), kill request file,
  SIGTERM with SIGKILL escalation, `kill_signal=operator` + latency in the
  termination receipt; the registry is SQLite (WAL + busy timeout), so the
  kill process and the exec process observe one state without a sidecar lock.
- Fail-closed emitter: receipt writes are atomic; on write failure `_emit`
  raises `EmitterError` and rolls back the in-memory receipt, so exec refuses
  before any work runs.
- Expiry: exec (and kill/snapshot/restore) self-seal a past-expiry slot with
  `time_expired` and refuse further work; `mandala.sweep` seals a tenant's
  expired slots in one pass.
- Selective disclosure: `continuity_receipt.disclose` (redact with tail
  re-signing, attach/reveal maps, commit check) + CLI; redaction is an
  issuance-time act (vectors 07/08).
- Benchmarked (`tools/bench.py`; pre-fix evidence `gate-lite/evidence/bench-2026-09-18/`,
  post-fix `gate-lite/evidence/bench-2026-09-18-sqlite/`): 14/14 invariants in both;
  verify 6-receipt bundle 1.26 ms (linear), bwrap exec 34.6 ms, slice exec 96.7 ms,
  kill 51 ms median, stdio ping 0.04 ms / HTTP keep-alive 0.42 ms. Two fixes
  landed from the first pass: MCP HTTP `TCP_NODELAY`, and a 1 s SIGTERM grace
  before SIGKILL escalation in `kill()`. **Scaling item resolved 2026-09-18:**
  the JSON registry was O(total slots) per operation; it is now indexed SQLite
  (`registry.py`) — `get_slot` 43.2 → 0.026 ms and `put_slot` 314.6 → 0.13 ms
  at 10k slots (flat with store size), sweep 15× faster, full-standard
  benchmark 82 s → 44 s, dogfood 33/33.
- Idempotent replay for pass/exec (registry cache); tenant scoping enforced
  (`cross-tenant access denied`).
- Gate identity persisted in `<state>/gate.key` (0600); pass tokens
  compact-JWS with `jti` replay cache.

**Deviations from the contract text (documented, not drift):**
1. **Registry:** SQLite (`registry.db`, WAL + busy timeout) instead of TOML +
   WM store — the container changed, records are still opaque JSON payloads and
   the API is unchanged; legacy `state.json` is auto-imported on first open and
   left in place. WM-store migration deferred until the gate writes to the
   karma ledger directly.
2. **Chain persistence:** one bundle JSON per task under
   `<state>/receipts/<task_id>.json`, reloaded from disk by the orchestrator.
   Required because every CLI command is a separate process; a purely
   in-memory chain fragmented tasks across bundles (caught by smoke test and
   fixed; regression test: `test_cross_process_chain_continuity`).
3. **Endpoint scheme:** `gate://<gate_id>/<slot_id>` stays the logical
   endpoint; the MCP surface now also serves loopback HTTP (Streamable HTTP
   subset: `POST /mcp`, SSE response when `Accept: text/event-stream`,
   `Mcp-Session-Id` on initialize, optional bearer `--token`; GET → 405).
4. **Settlement:** `settle()` emits the delivery attestation itself when
   `gated_on_delivery` (the gate attests response hashes), and refuses amounts
   above the pass spend cap before emission. Dogfood settles at $0.
5. **MCP control surface** (§5): **wired 2026-09-17, extended 2026-09-18** —
   `gate_lite/mcp_server.py`, JSON-RPC 2.0, 11 tools
    pass/exec/settle/terminate/**kill**/destroy/status/list/receipt/templates/
    **snapshot**; `mandala.create` folded into `mandala.pass` for v0; token
    subject + expiry checked on exec when a token is supplied (**superseded
    2026-09-24 — the token is now required, see item 9**); tool failures
    return structured `isError` (`emitter_unavailable`, `not_found`,
    `permission_denied`, `invalid`).
6. **Snapshot semantics (operator decision 2026-09-18):** filesystem snapshot
   only — the slot workspace (mounted writable at `/workspace` in the runner)
   is tarred to `<state>/snapshots/<slot>/<snapshot_id>.tar.gz` and attested
   via `delivery.attestation` (`artifact` carries snapshot id, sha256, bytes;
   the registry keeps a snapshot index with `tree_hash`); slot state becomes
   `frozen` and exec is refused. `mandala.restore` materializes a snapshot
   into a `placed` slot with sha verification, safe extraction (path-traversal
   / link rejection) and a second `delivery.attestation`
   (`kind: filesystem-restore`); the G7 path snapshot → destroy → recreate →
   restore is tested with runner-written artifacts. A frozen store image
   remains gate-hard scope.
7. **Quota kill detection:** slice mode reads `Result`/`MemoryPeak` from the
   transient unit; `oom-kill` → `killed_by=memory_max`, `timeout` →
   `killed_by=wall`, both → termination `reason=quota`, `kill_signal=quota`.
   `CPUQuota` is a rate throttle, not a kill. `systemd-run --pipe` is
   required for stdout capture; on this systemd (255) a signal-killed payload
   is reported as `rc=0/success` through `--pipe`, so operator kills are
   proven by the kill request + termination receipt + latency, not payload rc.
8. **Runner payloads:** plain commands or envelopes
   `{"program", "args", "net", "egress"}`. `net: true` without declared
   destinations is treated as undeclared and denied (recorded as
   `destination: "undeclared"`).
9. **Authorization contract (2026-09-24):** pass issuance enforces
   `Tenant.agents` membership (`agent_not_registered`); `mandala.exec`
   requires a pass token bound to the slot's pass and agent
   (`token_required`, `token_invalid`, `pass_expired`,
   `token_subject_mismatch`, `token_slot_mismatch`, `pass_replayed`); jti
   replay is durable and atomic (`consumed_tokens` in the SQLite registry,
   survives restarts and concurrent requests); attempts rejected before work
   starts release the token. CLI `exec --token` and the MCP `token` field are
   required; cross-tenant slot denial unchanged.

**Acceptance status (2026-09-18):** G1 PASS (TRUSTED bundle), G2 PASS
(memory + wall overrun kill the slot via systemd slice, `quota`), G3 PASS
(undeclared / declared-but-unpermitted egress denied and recorded, no
reachability), G4 PASS (cross-tenant denied), G5 PASS (idempotent replay),
G6 PASS (operator kill end-to-end in 291 ms, `operator`), G7 **PASS**
(snapshot → destroy → recreate → restore tested with runner-written
artifacts; filesystem-only by decision; store image remains gate-hard),
G8 PASS (emitter down ⇒ exec refused, runner never invoked).

**Tests:** 49 green — 5 receipt-library vectors/primitives (incl. the
11-vector sweep), 7 orchestrator, 6 MCP, 10 acceptance (G8 fault injection,
idle/live G6, G3 ×2, G2 ×2, snapshot, workspace roundtrip), 8 HTTP
transport, 5 selective-disclosure, 8 restore/expiry/key. Dogfood driver
`tools/dogfood_run.py` reports 33/33 checks on the real runner; evidence in
`gate-lite/evidence/2026-09-18/`.

**Update 2026-09-24:** suite 79 tests green (authorization contract, stub
safety, spec 0.3 emission via PyPI — no vendored copy); details in
`HANDOFF_2026-09-18.md` §9–§10.
