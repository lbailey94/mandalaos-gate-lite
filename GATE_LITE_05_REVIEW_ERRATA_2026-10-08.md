> **Later disposition (2026-10-09):** the private repairs are pushed at
> `8e84b25`; the complete wrapper packet is public at `1357c14` under its scoped
> MIT license. The frozen-source exercise has been accepted for selective-port
> preparation. Public metadata fixes landed in PR #11 (`75ebbd6`). Independent
> public-port review and publication remain separate gates. The original errata
> below retains its contemporaneous local-candidate wording.

# October 8 handoff errata and repair disposition

This note accompanies the original opencode review and run A/B records. Their
signed bundles and raw transcripts remain historical and unchanged.

- Run A used installed wrapper de273…; run B used qualified wrapper f7da….
- Run A validated the token before profile refusal, but refused before token
  consumption and process spawn. A pass receipt existed; no task.execution or
  final task bundle was captured.
- Three verification commands share Python code and include a historical 0.4
  synthetic fixture. They are not three independent implementations.
- Run B's saved tests.log is the failing configured-environment run. Its clean
  rerun has a transcript summary; retain separate full logs in future captures.
- receipt-task-execution.json is a projection; the signed receipt is in the bundle.
- The transcript's initial no-token statements describe the stopped session,
  not its appended successful continuation. Mode-600 temporary token handling
  was documented; do not claim tokens were never written anywhere.
- Unkeyed issuance can lose a token, while keyed issuance caches/returns it in
  private registry state. Single-use JTI enforcement is a separate property.
- The older capture's delivery hash is sha256("none"), not its actual execution
  output. Repairs bind future issuer response hashes to persisted execution.
  Existing evidence remains bounded $0 lifecycle evidence, not delivery/payment
  qualification.
- F8 documentation already existed. F6 is the protocol update reference.
- The second-laptop packet's old draft pins are historical; fresh gates need
  current frozen pins and another administered host.

Candidate repairs preserve the qualified 0.5 profile and commitment behavior,
add exact 0.5.0 dependency refusals, isolate unit tests, expose real acceptance
opt-ins, preserve honest egress and POSIX termination behavior, and prepare a
bundled byte-identical wrapper with provenance. Its public license declaration,
pushed-source exercise, public curation and human sign-off are later gates.
