# Review notes (one page)

You are reviewing a curated snapshot. Everything runs offline; start with the
commands in `README.md` §4. Priorities, in the maintainer's order:

## What changed in this revision (2026-09-24)

- The current review code pin is private `mandala-os` `033e5ce`. Its clean
  export emits spec 0.4, passed 86 tests, and produced a real-runner bundle
  that verified TRUSTED with the published 0.4.0 verifier. See
  `gate-lite/evidence/outsider-2026-09-24-04/REPORT.md`.
- The 0.3 exercise and bundle from the prior snapshot remain intact as
  historical evidence. This snapshot also adds a future-project integration
  contract without changing the tested gate-lite code after `033e5ce`.
- Historical 0.3 code pin `ac078e2`; later documentation/evidence revisions `e7d40f5`,
  `a4553b0`, `9fb406c`, `c42320d` — no gate-lite code changed after the pin.
- The 0.1-era **vendored verifier is gone**: current receipts are spec `0.4`
  via the published PyPI package `continuity-receipt` (0.4.0 exercised). Verifier
  internals now live in the spec repo
  (github.com/lbailey94/continuity-receipt).
- New since the 2026-09-18 snapshot: **authorization contract** (tenant
  membership at issuance, required single-use token at exec, durable atomic
  replay), **stub safety** (no silent simulated execution), **idempotency
  scoping** (authorization before cache), and the **outsider exercise**
  evidence (`gate-lite/evidence/outsider-2026-09-24/REPORT.md`) with its
  claim boundary: same-host clean-export reproduction by a collaborator with
  a pre-existing runner — not an unassisted stranger install.

## a. Does the receipt / evaluation model hold up?

- Verdict semantics (TRUSTED / PROVISIONAL / INSUFFICIENT_EVIDENCE /
  UNTRUSTED) and what each does and does not promise: the spec repo's
  `continuity_receipt/verify.py`; `design/GATE_LITE_ORCHESTRATOR_CONTRACT_2026-09-17.md`
  §7–§8.
- Chain model, canonicalization, commit fields: spec repo `records.py`,
  `canon.py`.
- Erasure / redaction: erased content → INSUFFICIENT_EVIDENCE; withheld salt →
  PROVISIONAL; disclosed map → TRUSTED — `gate-lite/vectors/INDEX.md` (07, 08,
  09); the disclosure CLI ships in the spec repo
  (`continuity-receipt-disclose`).
- Cross-record obligations: spec verifier; vectors 04 and 06.
- Questions: is PROVISIONAL right for withheld disclosure? Can a re-signed
  redaction change meaning? Does one gate key across all receipt types
  (`gate-lite/gate_lite/orchestrator.py`, gate key setup) weaken attribution?

## b. Is the containment / claim framing honest?

- Is "shared-kernel containment (bwrap/Landlock); never sold as untrusted
  multi-tenant" stated consistently? `gate-lite/README.md`,
  `design/MULTI_TENANT_UNTRUSTED_V0_2_2026-09-17.md` §1, `README.md` §0–§3.
- Read the known deviations (`gate-lite/HANDOFF_2026-09-18.md` §3 and §9–§11,
  contract §14) — does any widen the claim? Does the outsider claim boundary
  (`README.md` §0, protocol §6) hold up?

## c. Correctness review of `gate-lite/`

- **Authorization path (new):** `pass_` `orchestrator.py:645`,
  `_verify_exec_token` `:777`, `_consume_exec_jti` `:808`, `exec_` `:815`;
  durable replay `registry.py:286` (`consume_jti` / `release_jti` /
  `jti_consumed`); structured `PassError` codes `orchestrator.py:45`.
- Registry concurrency: `gate-lite/gate_lite/registry.py` (SQLite WAL,
  thread-local connections, legacy import `:127`, CAS `:202`).
- State machine and terminality: `orchestrator.py` lifecycle, expiry gate,
  blocked states; kill/escalation `:1074`; expiry seal / sweep `:1300`.
- Snapshot/restore safety: `_safe_extract` `:70`, restore `:1221`,
  `tests/test_restore.py`.
- Fail-closed emitter: `EmitterError` `:41`; G8 row in
  `gate-lite/evidence/2026-09-18/SUMMARY.md`.
- Replay and idempotency regressions: `tests/test_orchestrator.py`
  (`test_replay_*`, `test_exec_idempotent_*`, `test_pass_idempotent_*`),
  `tests/test_registry.py` (`test_consume_jti_*`).

## d. The outsider exercise

- Read `gate-lite/evidence/outsider-2026-09-24/REPORT.md` (friction log and
  claim boundary) and re-verify the captured bundle offline:
  `.venv/bin/continuity-receipt-verify gate-lite/evidence/outsider-2026-09-24/bundle-task-*.json`.
