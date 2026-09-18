# Review notes (one page)

You are reviewing a curated snapshot. Everything runs offline; start with the
commands in `README.md` §4. Priorities, in the maintainer's order:

## a. Does the receipt / evaluation model hold up?

- Verdict semantics (TRUSTED / PROVISIONAL / INSUFFICIENT_EVIDENCE /
  UNTRUSTED) and what each does and does not promise:
  `gate-lite/continuity_receipt/verify.py:218`,
  `design/GATE_LITE_ORCHESTRATOR_CONTRACT_2026-09-17.md` §7–§8.
- Chain model, canonicalization, commit fields:
  `gate-lite/continuity_receipt/records.py:72`, `canon.py:6`, `canon.py:37`.
- Erasure / redaction: erased content → INSUFFICIENT_EVIDENCE; withheld salt →
  PROVISIONAL; disclosed map → TRUSTED — `gate-lite/vectors/INDEX.md` (07, 08,
  09), `verify.py:173`, `disclose.py:98`, `disclose.py:135`.
- Cross-record obligations: `verify.py:123`; vectors 04 and 06.
- Questions: is PROVISIONAL right for withheld disclosure? Can a re-signed
  redaction change meaning? Does one gate key across all receipt types
  (`gate-lite/gate_lite/orchestrator.py:350`) weaken attribution?

## b. Is the containment / claim framing honest?

- Is "shared-kernel containment (bwrap/Landlock); never sold as untrusted
  multi-tenant" stated consistently? `gate-lite/README.md`,
  `design/MULTI_TENANT_UNTRUSTED_V0_2_2026-09-17.md` §1.
- Read the known deviations (`gate-lite/HANDOFF_2026-09-18.md` §3,
  `GATE_LITE_ORCHESTRATOR_CONTRACT_*.md` §14) — does any widen the claim?

## c. Correctness review of `gate-lite/`

- Registry concurrency: `gate-lite/gate_lite/registry.py:64` (SQLite WAL,
  thread-local connections, legacy import `:121`).
- State machine and terminality: `gate_lite/orchestrator.py:25`, expiry gate
  `:649`, lifecycle `:325`–`800`.
- Kill/escalation `:802`; expiry seal `:988`; sweep `:998`.
- Snapshot/restore safety: `_safe_extract` `:49`, restore `:936`,
  `tests/test_restore.py`.
- Fail-closed emitter: `EmitterError` `:30`; G8 row in
  `gate-lite/evidence/2026-09-18/SUMMARY.md`.
- Suite: `gate-lite/tests/` (acceptance, registry, orchestrator, disclose,
  restore, vectors, MCP, HTTP).

## d. What would you attack first?

- TRUSTED for a chain with reordered or cross-tenant receipts; check tenant
  scoping in `orchestrator.py`.
- Race the kill/expiry window against a starting exec; probe frozen/expired
  edges (`orchestrator.py:649`, `:802`, `:988`).
- Smuggle or rewrite content through re-signed redactions
  (`disclose.py:81` `_resign_tail`).
- Claim drift between docs and code — the project's own recurring question
  (`CURRENT_REALITY_2026-09-13.md`).

Report findings as `file:line`; honest failure reports are wanted, not polish.
