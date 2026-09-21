# MandalaOS — gate-lite public-review snapshot

Status date: 2026-09-18. This is a curated, review-only snapshot of one slice of
the MandalaOS project. It is not a release and does not represent the whole
system.

## 1. What this is

The **gate-lite** slice of MandalaOS: a governed-pass orchestrator that grants a
time/CPU/spend-bounded pass to a cooperating agent, supervises execution inside
a contained slot, and emits a **Continuity Receipt** bundle covering the full
task arc:

decision → authority → execution → delivery → termination → settlement

Receipts are Ed25519-signed hash-chained records (`continuity-receipt/0.1`)
checked by a standalone reference verifier. Operations: pass, exec, settle,
terminate, kill, snapshot, restore, sweep. Control surfaces: a `mandala-ctl`
CLI and an MCP server (stdio + loopback HTTP/SSE).

## 2. Honest status (2026-09-18)

| Claim | State |
|---|---|
| P0 slice | built and exercised end-to-end |
| Acceptance G1–G8 | pass (incl. G7 snapshot → destroy → recreate → restore roundtrip) |
| Test suite | 56 tests green (`unittest`) |
| Dogfood | 33/33 checks on the real bwrap runner + systemd slices |
| Benchmark | 14/14 invariants, pre- and post-SQLite registry fix |
| Containment class | **shared-kernel** (bwrap/Landlock); described as such everywhere |
| Untrusted multi-tenant | **never sold as this** — that is gate-hard (microVM floor, not built) |

Claim labels are used deliberately: "built and exercised", not "production".
Evidence summaries and both benchmark reports are under `gate-lite/evidence/`;
the working state and known deviations are in `gate-lite/HANDOFF_2026-09-18.md`.

## 3. What is not here yet, and why

- **Gate-hard microVM floor** (KVM microVM per mandala, for untrusted tenants).
  Requires dedicated / bare-metal hosts; cheap VPS tiers have no nested
  virtualization. Design: `design/MULTI_TENANT_UNTRUSTED_V0_2_2026-09-17.md`.
- **WM-store + karma-ledger integration.** The orchestrator currently uses an
  indexed SQLite registry; migrating to the WhiteMagic store/ledger is a later
  integration choice, not a scaling need.
- **External anchor issuance.** Policy decided 2026-09-18: OpenTimestamps is
  the recommended default; public-chain anchors remain an optional peer type.
  The issuance step and 0.3 proof verification are not built. Policy lives in
  the public spec repo's `ANCHORING.md`.

## 4. How to run

From `gate-lite/`:

```bash
python3 -m unittest discover -s tests -v
python3 -m continuity_receipt.verify vectors/02_happy_full.json
```

Requires Python 3.11+ and `cryptography`. The real sandboxed execution path
additionally needs `bubblewrap`; slice mode needs a systemd user session. See
`gate-lite/README.md` for CLI/MCP usage.

## 5. Relationship to the public repositories

- **continuity-receipt** — the receipt format and reference verifier are
  published separately at github.com/lbailey94/continuity-receipt (Apache-2.0;
  also on PyPI). The format's current published revision is
  `continuity-receipt/0.2` (backward compatible with 0.1); this snapshot
  vendors the 0.1-era verifier under `gate-lite/continuity_receipt/`.
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
questions the maintainer most wants examined.

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
