# Frozen private-source 0.5 exercise — preserved evidence

Source: private `mandala-os`
`8e84b2520b535d1452d4966d885411ee7aaea47d`, freshly fetched from the pushed
`codex/gate-lite-05-profile` branch. Candidate-commit CI run
[37872710238](https://github.com/lbailey94/mandala-os/actions/runs/37872710238)
passed with exact Continuity Receipt 0.5.0. No merged-tree claim is made.
The source repository requires authorized collaborator access; it was not
an anonymous private-source acquisition.

Wrapper: complete public packet
`1357c147410e2471872cb0658d93199457461e65`, acquired separately without credentials.
Six HTTP 200 downloads, all five manifest entries valid; executable digest
`f7da8d6c3809ac5adbc4631c82fb9327abdb69638715bb0ea1493dc79996411e`.
The full packet pin is distinct from wrapper-first commit `a843e61…` and later
metadata correction `75ebbd6…`. Neither the frozen packet nor the capture was
relabeled by those documentation fixes.

## Result and scope

PASS for a bounded same-host clean-export reproduction by collaborators.
The pristine tracked-file export matched all 258 tracked source files; installed
runtime modules matched the frozen commit. The seven-receipt bundle here has
SHA-256 `e6f6031492e80a221c266f3c28e64e717b748ecc4557dd2b0e03d1a4aa6b61f5`.
It verifies TRUSTED with the Python reference verifier. Capture checks and
independent recomputation passed for the original commitment snapshot/count/head,
canonical invocation, wrapper identity, fixed stdout, issuer delivery binding,
zero-value invoice settlement and termination.

| Check | Passed | Skipped | Failed |
|---|---:|---:|---:|
| Pristine ordinary suite | 131 | 6 | 0 |
| Pristine configured-environment suite | 131 | 6 | 0 |
| Explicit real Bubblewrap acceptance | 10 | 2 | 0 |
| Downloaded-wrapper argv capture tests | 6 | 0 | 0 |
| Fixed namespace/filesystem mechanism probe | PASS | — | 0 |

Wall/OOM quota cases were skipped. The probe compares namespace/filesystem
properties; it does not qualify all outbound routes. CLI, console and module
verification share one Python implementation. Two lanes independently recomputed
hash bindings; they are not two independent verifier implementations or adopters.
The issuer's response binding is not external delivery attestation, and a $0
invoice is not payment qualification. Independent adoption, hostile-tenant
isolation and VM containment remain open.

Lucas accepted this frozen exercise after the three wrapper documentation fixes
landed in public PR #11. That permits preparation of the selective public port;
independent port review and the public publication decision are separate gates.
The preserved independent review describes the state when it was written, including
then-pending human sign-off and metadata fixes. This report records the later
acceptance without changing that review or any raw evidence.

## Artifact map

- `bundle-task.json`, `verdict.json`, console/module outputs: original pristine
  capture and Python verification, preserved byte-for-byte.
- `commitment-state.json`, `invocation.json`, `checks.json`, `provenance.json`,
  `transcript.json`: original privacy-checked inputs and process capture. No runtime
  database, signing key or plaintext pass token is included. Paths are original
  same-host capture paths; they are not portable installation instructions.
- `parent-exercise-pristine-recomputation.json`: independently computed bindings.
- `source-provenance.json`, `acquisition.json`, `anonymous-manifest-check.log`:
  separate private source and anonymous public-wrapper acquisition records.
- `pristine-unit-*.log`, `acceptance-bwrap.log`, `wrapper-argv.log`,
  `mechanism-probe.json`: original check logs.
- `independent-frozen-evidence-review.md`: contemporaneous review of the pristine
  and earlier generated-fixture captures. The earlier capture remains preserved
  in the private workspace; only the pristine capture is curated here.
- `SHA256SUMS`: byte manifest of this selected evidence packet.

The old protocol's generator created 0.5 bundles in a disposable export while
retaining 0.4 index/delivery labels. This packet uses the second pristine capture
to avoid that ambiguity. The public port fixes generation with an explicit spec
and separate output directory, leaving historical vectors and old captures intact.

This evidence qualifies its private source pin and recorded environment. It is
not execution evidence for the selective public port. That candidate's checks
and source identity must be recorded separately after integration.
