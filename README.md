# MandalaOS — gate-lite public-review snapshot

Status date: 2026-09-24. This is a curated, review-only snapshot of one slice
of the MandalaOS project. It is not a release and does not represent the whole
system.

## 0. Provenance of this revision

- **Current tested code pin:** private `mandala-os` `033e5ce` (86 tests green
  on a clean export; real-runner 0.4 bundle TRUSTED). See
  `gate-lite/evidence/outsider-2026-09-24-04/REPORT.md`. The public snapshot
  adds documentation and captured evidence after that tested code pin.
- **Historical tested code pin:** `ac078e2`, exercised with receipt spec 0.3.
  Its evidence remains under `gate-lite/evidence/outsider-2026-09-24/` and
  must retain that version label.
- **Claim boundary:** the outsider exercise was a **same-host clean-export
  reproduction by a collaborator with a pre-existing runner — not an
  unassisted stranger install**. A genuinely new tester on another machine
  remains a separate gate; this snapshot must not be read as that.
- The receipt format's current published revision is `continuity-receipt/0.4`
  (spec repo: github.com/lbailey94/continuity-receipt; also on PyPI). This
  snapshot **does not vendor the verifier** — it installs the published
  package as a dependency.

## 1. What this is

The **gate-lite** slice of MandalaOS: a governed-pass orchestrator that grants a
time/CPU/spend-bounded pass to a cooperating agent, supervises execution inside
a contained slot, and emits a **Continuity Receipt** bundle covering the full
task arc:

decision → authority → execution → delivery → termination → settlement

Receipts are Ed25519-signed hash-chained records (`continuity-receipt/0.4`)
checked by the published reference verifier. Operations: pass, exec, settle,
terminate, kill, snapshot, restore, sweep. Control surfaces: a `mandala-ctl`
CLI and an MCP server (stdio + loopback HTTP/SSE).

## 2. Honest status (2026-09-24)

| Claim | State |
|---|---|
| P0 slice | built and exercised end-to-end |
| Acceptance G1–G8 | pass (incl. G7 snapshot → destroy → recreate → restore roundtrip) |
| Test suite | **86 tests green** (`unittest`, clean export) |
| Authorization | tenant membership at issuance; required single-use token at exec; durable atomic replay (restart + concurrent requests); idempotency cache is authorization-first and tenant/slot scoped |
| Stub safety | exec and the MCP server refuse without a real runner unless `--demo`; `mandala.status` reports the effective runner |
| Outsider exercise | PASS 2026-09-24 against 0.4 pin `033e5ce` (clean export, real runner, bundle TRUSTED offline); earlier 0.3 run retained — both same-host reproductions, see §0 |
| Receipts | spec `0.4` via published PyPI `continuity-receipt 0.4.0` in the captured run (no vendored copy) |
| Dogfood | 33/33 checks on the real bwrap runner + systemd slices (2026-09-18 evidence) |
| Benchmark | 14/14 invariants, pre- and post-SQLite registry fix (2026-09-18 evidence) |
| Containment class | **shared-kernel** (bwrap/Landlock); described as such everywhere |
| Untrusted multi-tenant | **never sold as this** — that is gate-hard (microVM floor, not built) |

Claim labels are used deliberately: "built and exercised", not "production".
Evidence summaries, both benchmark reports, and the outsider exercise report
(with its friction log) are under `gate-lite/evidence/`; the working state and
known deviations are in `gate-lite/HANDOFF_2026-09-18.md` §9–§11 and
`design/GATE_LITE_ORCHESTRATOR_CONTRACT_2026-09-17.md` §14.
For a new project integration, start with
`gate-lite/INTEGRATION_CONTRACT.md`.

## 3. What is not here yet, and why

- **Gate-hard microVM floor** (KVM microVM per mandala, for untrusted tenants).
  Requires dedicated / bare-metal hosts; cheap VPS tiers have no nested
  virtualization. Design: `design/MULTI_TENANT_UNTRUSTED_V0_2_2026-09-17.md`.
- **WM-store + karma-ledger integration.** The orchestrator currently uses an
  indexed SQLite registry; migrating to the WhiteMagic store/ledger is a later
  integration choice, not a scaling need.
- **External anchor issuance.** Policy decided 2026-09-18: OpenTimestamps is
  the recommended default; public-chain anchors remain an optional peer type.
  The issuance step is not wired into gate-lite, and proof verification lives
  in the spec repo. Policy: the public spec repo's `ANCHORING.md`.
- **Slice/systemd mode and MCP transports** are covered by the test suite and
  the 2026-09-18 dogfood/benchmark evidence, but were not part of either
  2026-09-24 clean-export exercise (real runner only, by design).

## 4. How to run

From the snapshot root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e gate-lite          # pulls continuity-receipt from PyPI
cd gate-lite
../.venv/bin/python -m unittest discover -s tests -v
../.venv/bin/continuity-receipt-verify vectors/02_happy_full.json
# verify the captured outsider bundle offline
../.venv/bin/continuity-receipt-verify evidence/outsider-2026-09-24-04/bundle-task.json
# historical spec 0.3 exercise, verified with a compatible verifier
../.venv/bin/continuity-receipt-verify evidence/outsider-2026-09-24/bundle-task-*.json
```

Requires Python 3.11+. The real sandboxed execution path additionally needs
the external `mandala-sandbox` wrapper (Sovereign Edition:
`mandalaos-sovereign/modules/landlock-isolation.nix`) plus `bubblewrap`;
slice mode needs a systemd user session. See `gate-lite/README.md` for
CLI/MCP usage and `GATE_LITE_OUTSIDER_EXERCISE.md` for the exercise protocol.

## 5. Relationship to the public repositories

- **continuity-receipt** — the receipt format and reference verifier are
  published separately at github.com/lbailey94/continuity-receipt (Apache-2.0;
  also on PyPI). The format's current published revision is
  `continuity-receipt/0.4` (reference verifier supports 0.1–0.4). This snapshot
  installs the package from PyPI and does not vendor it.
- **WhiteMagic** — the governance/memory core:
  github.com/lbailey94/whitemagic (MIT).
- **mandalaos-sovereign** and **lakshmi** — remain **private for now**; they
  are not part of this snapshot.

## 6. AI-assisted development disclosure

The human maintainer (Lucas Bailey) is accountable for all content here. AI
collaborators worked under his direction on implementation, tests, benchmarks,
and documentation. Every status claim above is tied to a runnable test or
captured evidence in this tree; review them as such.

## 7. Starting point for a no-context review

`implementation/AI_BRIEFING_2026-09-15.md` is a self-contained briefing written
for a reviewer with no prior context; `REVIEW_NOTES.md` lists the specific
questions the maintainer most wants examined, plus what changed in this
revision.

## 8. The stack

> Local memory → governed execution → verifiable continuity

- [`whitemagic`](https://github.com/lbailey94/whitemagic) — local-first memory and session continuity for AI agents
- [`continuity-receipt`](https://github.com/lbailey94/continuity-receipt) — portable, offline-verifiable evidence for governed tasks (Apache-2.0)
- [`mandalaos-gate-lite`](https://github.com/lbailey94/mandalaos-gate-lite) — bounded agent execution that emits receipts (this review snapshot)
- [`whitemagic-plugins`](https://github.com/lbailey94/whitemagic-plugins) — client integrations and adapters

Each repository stands on its own: WhiteMagic does not require MandalaOS, and
Continuity Receipt does not require WhiteMagic. Three entrances — **use it** →
`whitemagic`; **review a protocol** → `continuity-receipt`; **attack the
security architecture** → `mandalaos-gate-lite`.
