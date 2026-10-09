# Independent frozen exercise evidence review

Review date: 2026-10-09  
Scope: read-only recomputation of the bounded Gate-lite 0.5 captures in `exercise/` and `exercise-pristine/`, their frozen source/archive relationship and installed Python package, and the anonymously acquired public wrapper packet.

## Verdict

Both saved captures, `exercise/` and `exercise-pristine/`, are internally consistent for a bounded, same-host rehearsal. I independently recomputed the seven-receipt state commitment, runner invocation digest, fixed stdout hash, delivery-to-execution hash binding, and wrapper digest for each. The transcripts record successful unkeyed pass issuance, a fixed no-network `echo`, zero-minor invoice settlement, and termination. The pass token is explicitly redacted; I found no JWT-shaped value or private-key marker in either exported exercise.

My independent recomputation confirms the saved bindings, but the evidence does not establish independent adoption or qualification by an independently implemented verifier. It also does not establish external delivery, issuer honesty, hostile-tenant isolation, or payment qualification. The API and CLI `TRUSTED` results use the same Python verifier implementation, as the capture provenance states. The delivery receipt is self-issued: its counterparty is the same DID as the issuer, and the evidence records no external attestation. The zero settlement is a local rehearsal value, not payment evidence.

## Recomputed bindings

| Check | `exercise/` | `exercise-pristine/` |
|---|---|---|
| Receipt chain | Seven receipt types end in `task.termination`; saved verdict is `TRUSTED`. | Same seven receipt types and verdict. |
| Registry commitment count | Saved count `3` equals the sum of the five saved top-level collection lengths (`3`). | Saved count `3` equals the recomputed sum (`3`). |
| Registry commitment digest | Recomputed canonical JSON SHA-256: `sha256:187eb145c5d2ab681abf8534892eeff09bb749c91f308eda622fb7214730dbe8`; matches `state.commitment`. | Recomputed canonical JSON SHA-256: `sha256:3f0332f9f35259c5800fed1c41c2b23050290598219b8ac57c8a26634e9c75d2`; matches `state.commitment`. |
| Invocation digest | Recomputed canonical JSON SHA-256: `sha256:7056d1805d6649d4c906d773c1b3fcaa8cc02bbdf1a23230374008eec62a7613`; matches `task.execution`. | Recomputed canonical JSON SHA-256: `sha256:a9fad7234f167f453cb228c89b989d668c212abb234e370ecb0d01df9170b03c`; matches `task.execution`. |
| Fixed stdout | `hello from gate-lite 0.5 rehearsal\n` hashes to `sha256:9f59b53267f2c28054c2b951bfbbb6602482b168e0540debb2f8bcbe15e8243f`; matches execution and delivery hashes. | Same fixed output and matching hash bindings. |
| Wrapper identity | Execution digest matches downloaded bytes: `sha256:f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e`. | Same digest matches downloaded bytes. |
| Settlement and termination | Amount is 0 USD minor units; final receipt terminates the task. | Same. |
| Privacy scan | No JWT-shaped string or `PRIVATE KEY-----` marker. Pass token is recorded as `"<redacted>"`; a non-secret pass-token identifier and JTI remain in registry/receipts. | Same scan result and redaction; non-secret pass-token identifier and JTI remain. |

The recomputed values agree with `parent-recomputation.json` and the capture checks. The capture implementation’s relevant mechanics are visible in `source/gate-lite/tools/capture_outsider_05.py:48-67,100-150`: it rejects a nonempty idempotency cache, supplies the observed reload state to the original commitment method, sends the pass only on child stdin, redacts it from the transcript, and compares the receipt bindings.

## Source and wrapper identity

`source-provenance.json:2-8` identifies private candidate commit `8e84b2520b535d1452d4966d885411ee7aaea47d`, the authorized collaborator fetch, archive digest `19d66b43cc7f6efcc1ca7de37a2ae98900166dc0e11a59d8e5c61ced55c04588`, and CI run `37872710238`, explicitly marked as a candidate commit with no merged tree. I confirmed `private-source-mirror/FETCH_HEAD` resolves to that commit and compared every member of `source.tar` with the commit’s Git blobs: all 258 tracked files match with no missing paths. I also compared all 258 tracked paths in `pristine-source/` against the same commit; `fixture-and-source-comparison.json` records zero pristine-export differences.

The protocol working export at `source/` has 11 generated `gate-lite/vectors/*.json` differences from the frozen archive; `vector-generation.log` records their generation. These are intentional protocol-step outputs, not stale or missing source bytes. The generated files contain spec 0.5 receipts, while the frozen commit/archive contains the prior spec 0.4 fixtures. The other 247 tracked files match the frozen commit, and the capture tool plus all eight installed `gate_lite` Python files match it. The pristine extraction therefore removes source-export ambiguity for the second capture, while the first capture preserves the regenerated protocol fixtures as separate evidence.

There is a version-label mismatch to clarify in the generator path: `gate-lite/tools/make_vectors.py:2,76,227` and `gate-lite/README.md:20-21` describe or label the vectors as historical spec 0.4, while the recorded regeneration produced JSON bundles whose `spec` fields say `continuity-receipt/0.5`. The regenerated `vectors/INDEX.md` still titles itself spec 0.4. Clarify whether the generator is intended to migrate these fixtures to 0.5 or preserve 0.4 coverage, then align its comments, `spec_ref`, index, and generated data. Until then, report the generated vector set as protocol-step output with mixed version labels, not as a clean 0.4 or 0.5 corpus.

The pristine and protocol-generated source trees each ran 137 unit tests with six skips in both clean and configured runs, according to `pristine-unit-clean.log`, `pristine-unit-configured.log`, `unit-clean.log`, and `unit-configured.log`. The two fresh exercise captures both pass the same 11 capture assertions; the transcripts contain different generated task IDs, as expected for separate runs.

The wrapper was acquired through the anonymous public packet at immutable complete-packet commit `1357c147410e2471872cb0658d93199457461e65`. `acquisition.json` records HTTP 200 for all six packet files, a passing five-entry manifest, and mode 755; I independently reran `sha256sum -c` and matched the executable digest above. The downloaded executable also byte-matches the candidate source’s `gate-lite/runners/bwrap-v1/mandala-sandbox`. This establishes anonymous public wrapper acquisition on the existing host, not adoption by an independent host or reviewer.

The capture’s `source_status: "pushed-frozen"` is an operator-supplied label, not a tool-verified fact (`exercise/provenance.json:2-5`). The private fetch and source archive provide separate local provenance for the source commit. The source provenance also states that CI qualified a candidate commit and not a merged tree.

## Limits and publication metadata

`exercise/provenance.json:19-27` correctly calls the verifier a Python reference whose CLI/API share an implementation, records the absence of external delivery attestation, and excludes independent adoption, hostile-tenant isolation, payment qualification, and issuer honesty. `verdict.json`’s `TRUSTED` status should be read within those bounds.

The complete-packet bytes and hashes check out at `1357c147…`, while the public packet metadata still has unresolved inconsistencies documented in `public-wrapper-audit.md`: the README also offers wrapper-first commit `a843e61…` as a complete-packet pin even though it lacks metadata files; the public source-attribution text still describes the packet as unpublished; and the README’s “qualified” wording conflicts with the public 0.4 fail-closed runtime documentation. Human publication approval has not been given; these metadata findings remain pending.
